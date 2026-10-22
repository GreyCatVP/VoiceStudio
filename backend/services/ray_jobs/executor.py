"""Run one model step as one Ray job and return its result.

    package -> upload (if new) -> submit -> poll status + logs -> parse result

The job's exit is the teardown: its process (and the engine sidecar it
started) ends, so the GPU memory goes back to the cluster after every run.
Every way out of ``run`` that leaves the job unfinished — cancellation, the
deadline, a dashboard error, a malformed log — stops the job, because a job
nobody is waiting for would otherwise keep holding its GPU.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Set

from ray_worker import vs_ray_protocol as proto
from services.ray_jobs.client import TERMINAL_STATUSES, RayJobsClient, RayJobsError
from services.ray_jobs.package import build_package

logger = logging.getLogger(__name__)

WORKER_ARGS = "vs_ray_worker.py --task task.json"
SWEEP_INTERVAL_S = 600.0
SWEEP_MIN_AGE_S = 120.0
# Never forwarded to a cluster: desktop containment markers break nested
# spawns there, device pinning belongs to Ray, and secrets would be visible
# to anyone who can read the job's runtime_env in the dashboard.
_DENY_ENV = re.compile(r"^(OMNIVOICE_DESKTOP_.*|CUDA_VISIBLE_DEVICES|.*(TOKEN|SECRET|PASSWORD|KEY).*)$", re.I)

ProgressFn = Callable[[Dict[str, Any]], Optional[Awaitable[None]]]


class ExecutorRetired(RuntimeError):
    """The executor was replaced (settings changed); use the current one."""


class RayJobFailed(RuntimeError):
    def __init__(self, message: str, *, submission_id: str, status: str, stage: str = "job") -> None:
        super().__init__(message)
        self.submission_id = submission_id
        self.status = status
        self.stage = stage


@dataclass(frozen=True)
class RayTask:
    op: str
    engine: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    inputs: Mapping[str, bytes] = field(default_factory=dict)
    env: Mapping[str, str] = field(default_factory=dict)
    num_gpus: Optional[float] = None
    num_cpus: Optional[float] = None
    memory_bytes: Optional[int] = None
    install: Optional[Mapping[str, Any]] = None  # engines.install_recipe()
    test_mode: bool = False

    def payload(self) -> Dict[str, Any]:
        bad = sorted(k for k in self.env if _DENY_ENV.match(k))
        if bad:
            raise ValueError(f"refusing to send env vars {bad} to the Ray cluster")
        out: Dict[str, Any] = {"v": 1, "op": self.op, "engine": self.engine,
                               "params": dict(self.params), "env": dict(self.env)}
        if self.install:
            out["install"] = dict(self.install)
        if self.test_mode:
            out["test_mode"] = True
        return out


@dataclass
class RayJobResult:
    submission_id: str
    result: Dict[str, Any]
    progress: list
    seconds: float


def _transient(exc: RayJobsError) -> bool:
    return exc.kind == "network" or (exc.kind == "http" and (exc.status or 0) >= 500)


class RayJobsExecutor:
    def __init__(
        self,
        client: RayJobsClient,
        *,
        poll_interval: float = 1.0,
        progress_interval: float = 2.0,
        stop_grace: float = 30.0,
        pending_watch: float = 3600.0,
        max_transient_errors: int = 8,
        delete_grace: float = 10.0,
        keep_failed_jobs: bool = True,
        cache_dir: Optional[str] = None,
        python: str = "python",
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", python):
            raise ValueError(f"unsafe cluster python {python!r}")
        self.client = client
        self.poll_interval = poll_interval
        self.progress_interval = progress_interval
        self.stop_grace = stop_grace
        self.pending_watch = pending_watch
        self.max_transient_errors = max_transient_errors
        self.delete_grace = delete_grace
        self.keep_failed_jobs = keep_failed_jobs
        self.cache_dir = cache_dir
        self.python = python
        # Strong references: a cleanup must outlive the run that started it.
        self._cleanups: Set[asyncio.Task] = set()
        self._runs: Set[asyncio.Task] = set()
        self.retired = False
        self._last_sweep = float("-inf")
        self._nodes: Optional[list] = None
        self._nodes_at = float("-inf")

    async def run(
        self,
        task: RayTask,
        *,
        timeout: Optional[float] = None,
        idle_timeout: Optional[float] = None,
        on_progress: Optional[ProgressFn] = None,
        submission_prefix: str = "vs",
    ) -> RayJobResult:
        """Run ``task`` as one job.

        ``timeout`` caps the whole run (upload, queueing, execution).
        ``idle_timeout`` is a silence deadline while the job RUNS: it is
        re-armed by every progress event, like a local sidecar's receive
        deadline, so a long but active install or download is not cut off.
        """
        if self.retired:
            raise ExecutorRetired("Ray settings changed; retry with the current executor")
        if time.monotonic() - self._last_sweep > SWEEP_INTERVAL_S:
            self._last_sweep = time.monotonic()
            self._track(asyncio.get_running_loop().create_task(self.sweep_finished()))
        me = asyncio.current_task()
        if me is not None:
            self._runs.add(me)
        try:
            return await self._run(task, timeout=timeout, idle_timeout=idle_timeout,
                                   on_progress=on_progress, submission_prefix=submission_prefix)
        finally:
            self._runs.discard(me)

    async def _run(self, task: RayTask, *, timeout: Optional[float], idle_timeout: Optional[float],
                   on_progress: Optional[ProgressFn], submission_prefix: str) -> RayJobResult:
        await self._check_placement(task)
        uri, data, _ = build_package(task.payload(), task.inputs)
        sid = f"{submission_prefix}-{task.engine or task.op}-{uuid.uuid4().hex[:12]}".replace("_", "")
        env_vars = {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8:backslashreplace"}
        if self.cache_dir:
            env_vars["VS_RAY_CACHE"] = self.cache_dir
        if timeout is not None:
            # The worker refuses to start an engine after this, so a job that
            # sat in the queue past its caller's patience does no GPU work.
            env_vars["VS_RAY_DEADLINE"] = f"{time.time() + timeout:.0f}"
        started = time.monotonic()
        submitted = terminal = False
        try:
            async with asyncio.timeout(timeout):
                await self._ensure_package(uri, data)
                submitted = True  # before the POST: a cancel mid-request must still stop it
                await self.client.submit_job(
                    entrypoint=f"{self._python_cmd()} {WORKER_ARGS}",
                    submission_id=sid,
                    runtime_env={"working_dir": uri, "env_vars": env_vars},
                    metadata={"app": "voicestudio", "op": task.op, "engine": task.engine},
                    entrypoint_num_cpus=task.num_cpus,
                    entrypoint_num_gpus=task.num_gpus,
                    entrypoint_memory=task.memory_bytes,
                )
                logger.info("ray job %s submitted (%s/%s)", sid, task.engine, task.op)
                status, logs = await self._wait(sid, on_progress, idle_timeout)
                terminal = True
            result = await self._finish(sid, status, logs, started)
            self._cleanup_detached(sid, stop=False, delete=True)
            return result
        except BaseException:
            if submitted and not terminal:
                # Send the stop before letting the cancellation/error escape:
                # a detached task alone could be cancelled with the loop.
                accepted = await asyncio.shield(self._send_stop(sid))
                if accepted:
                    self._cleanup_detached(sid, stop=True, delete=not self.keep_failed_jobs)
            elif terminal and not self.keep_failed_jobs:
                self._cleanup_detached(sid, stop=False, delete=True)
            raise

    async def _ensure_package(self, uri: str, data: bytes) -> None:
        """Upload the package unless the cluster has it. Retried on transient
        errors (a proxy's 524 on a large upload): content-addressed, so safe."""
        for attempt in range(1, 4):
            try:
                if not await self.client.package_exists(uri):
                    await self.client.upload_package(uri, data)
                return
            except RayJobsError as exc:
                if not _transient(exc) or attempt == 3:
                    raise
                logger.info("ray package upload: transient error (%d/3): %s", attempt, exc)
                await asyncio.sleep(2.0 * attempt)

    def _python_cmd(self) -> str:
        """The cluster interpreter. The default picks python3, else python:
        images differ (a KServe pod has no ``python``), and the stdlib-only
        worker runs on any Python >= 3.9. Ray runs the entrypoint via sh."""
        if self.python in ("python", "auto"):
            return '"$(command -v python3 || command -v python)"'
        return self.python

    async def _check_placement(self, task: RayTask) -> None:
        """Refuse a job the cluster can never schedule.

        Ray keeps such a job PENDING (and ignores a stop) until its start
        timeout, so a GPU engine on a CPU-only cluster would just hang.
        """
        if (not task.num_gpus and not task.num_cpus) or os.environ.get("OMNIVOICE_RAY_SKIP_PLACEMENT_CHECK") == "1":
            return  # (skip on autoscaling clusters whose GPU nodes start on demand)
        if self._nodes is None or time.monotonic() - self._nodes_at > 60:
            try:
                self._nodes = await self.client.node_resources()
                self._nodes_at = time.monotonic()
            except (RayJobsError, RuntimeError):
                return  # cannot tell; let Ray decide
        if not self._nodes:
            return  # unknown, not "no resources"
        need_gpu, need_cpu = float(task.num_gpus or 0), float(task.num_cpus or 0)
        # One job runs on one node: some single node must hold the request.
        if any(n.get("GPU", 0.0) >= need_gpu and n.get("CPU", 0.0) >= need_cpu for n in self._nodes):
            return
        best_gpu = max(n.get("GPU", 0.0) for n in self._nodes)
        best_cpu = max(n.get("CPU", 0.0) for n in self._nodes)
        if need_gpu and best_gpu < need_gpu:
            raise RayJobFailed(
                f"No Ray node has {need_gpu:g} GPU(s) for {task.engine or task.op} (the largest has {best_gpu:g}). "
                "Add a GPU node, or set the GPU share to 0 in Settings → Ray cluster to run on CPU.",
                submission_id="", status="REFUSED", stage="placement")
        raise RayJobFailed(
            f"No Ray node has {need_cpu:g} CPU(s) together with {need_gpu:g} GPU(s) for one job "
            f"(largest: {best_cpu:g} CPU, {best_gpu:g} GPU); lower the CPUs per job in Settings → Ray cluster.",
            submission_id="", status="REFUSED", stage="placement")

    async def _wait(self, sid: str, on_progress: Optional[ProgressFn], idle_timeout: Optional[float] = None):
        seen = errors = 0
        last_fetch = 0.0
        last_activity = time.monotonic()
        last_status = ""
        while True:
            try:
                status = str((await self.client.job_info(sid)).get("status"))
                if status != last_status:
                    last_status, last_activity = status, time.monotonic()
                if status in TERMINAL_STATUSES:
                    logs = await self.client.job_logs(sid)
                    if on_progress is not None:
                        for event in proto.parse_events(logs).progress[seen:]:
                            await self._notify(on_progress, event)
                    return status, logs
                watching = on_progress is not None or idle_timeout is not None
                if watching and time.monotonic() - last_fetch >= self.progress_interval:
                    last_fetch = time.monotonic()
                    events = proto.parse_events(await self.client.job_logs(sid)).progress
                    if len(events) > seen:
                        last_activity = time.monotonic()
                    if on_progress is not None:
                        for event in events[seen:]:
                            await self._notify(on_progress, event)
                    seen = len(events)
                # Queue time (PENDING) is bounded by ``timeout`` only.
                if idle_timeout is not None and status == "RUNNING" and time.monotonic() - last_activity > idle_timeout:
                    raise TimeoutError(f"Ray job {sid} made no progress for {idle_timeout:.0f}s")
                errors = 0
            except RayJobsError as exc:
                errors += 1
                if not _transient(exc) or errors > self.max_transient_errors:
                    raise
                logger.info("ray job %s: transient dashboard error (%d): %s", sid, errors, exc)
                await asyncio.sleep(min(self.poll_interval * 2 ** errors, 10.0))
                continue
            await asyncio.sleep(self.poll_interval)

    @staticmethod
    async def _notify(on_progress: ProgressFn, event: Dict[str, Any]) -> None:
        try:
            maybe = on_progress(event)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception:  # a UI callback must not abort the run
            logger.warning("ray job progress callback failed", exc_info=True)

    async def _finish(self, sid: str, status: str, logs: str, started: float) -> RayJobResult:
        if status != "SUCCEEDED":
            events = proto.parse_events(logs)
            err = events.errors[-1] if events.errors else {}
            info = await self._safe_info(sid)
            raise RayJobFailed(
                str(err.get("message") or info.get("message") or f"Ray job ended {status}"),
                submission_id=sid, status=status, stage=str(err.get("stage", "job")),
            )
        try:
            parsed = await asyncio.to_thread(proto.parse_log, logs)
        except proto.ProtocolError as exc:
            raise RayJobFailed(f"unreadable job result: {exc}", submission_id=sid, status=status, stage="result") from exc
        if parsed.result is None:
            raise RayJobFailed("job succeeded without a result", submission_id=sid, status=status, stage="result")
        return RayJobResult(sid, parsed.result, parsed.progress, time.monotonic() - started)

    async def _safe_info(self, sid: str) -> Dict[str, Any]:
        try:
            return await self.client.job_info(sid)
        except RayJobsError:
            return {}

    async def aclose(self) -> None:
        await self.client.aclose()

    # -- cleanup -----------------------------------------------------------
    async def drain(self, timeout: Optional[float] = None) -> None:
        """Wait for outstanding stop/delete work (call on backend shutdown)."""
        if self._cleanups:
            await asyncio.wait(list(self._cleanups), timeout=timeout)

    async def wait_idle(self, timeout: Optional[float] = None) -> None:
        """Retire, then wait until no run or cleanup is left (before closing the client).

        Re-checks after every wait: a run that slipped in before ``retired``
        was set, or a cleanup a finishing run just started, is waited for too.
        """
        self.retired = True
        deadline = None if timeout is None else time.monotonic() + timeout
        me = asyncio.current_task()
        while True:
            pending = [t for t in (*self._runs, *self._cleanups) if t is not me and not t.done()]
            if not pending:
                return
            left = None if deadline is None else deadline - time.monotonic()
            if left is not None and left <= 0:
                return
            await asyncio.wait(pending, timeout=left)

    async def sweep_finished(self, min_age_s: float = SWEEP_MIN_AGE_S) -> int:
        """Delete this app's finished jobs that nobody deleted.

        Catches what an in-process delete cannot: jobs whose cleanup was cut
        short by shutdown or a crash, and the records Ray writes back when a
        job is deleted while its supervisor is still exiting. Failed jobs are
        kept while ``keep_failed_jobs`` is set (for the dashboard), except
        those write-backs, which carry no metadata.
        """
        try:
            jobs = await self.client.list_jobs()
        except Exception as exc:  # background housekeeping: never raise
            logger.debug("ray job sweep skipped: %s", exc)
            return 0
        now_ms = time.time() * 1000
        removed = 0
        for job in jobs:
            if not isinstance(job, dict):
                continue
            sid = str(job.get("submission_id") or "")
            ended = job.get("end_time")
            if not sid.startswith("vs-") or job.get("status") not in TERMINAL_STATUSES:
                continue
            if not isinstance(ended, (int, float)) or now_ms - float(ended) < min_age_s * 1000:
                continue
            meta = job.get("metadata")
            ours = isinstance(meta, dict) and meta.get("app") == "voicestudio"
            if ours and job.get("status") == "FAILED" and self.keep_failed_jobs:
                continue
            try:
                await self.client.delete_job(sid)
                removed += 1
            except Exception:
                continue
        return removed

    async def _send_stop(self, sid: str) -> bool:
        """Ask Ray to stop ``sid``; False if Ray never accepted the job."""
        try:
            async with asyncio.timeout(15):
                await self.client.stop_job(sid)
        except RayJobsError as exc:
            if exc.kind == "not_found":
                return False
            logger.info("ray job %s: stop request failed, will retry: %s", sid, exc)
        except TimeoutError:
            logger.info("ray job %s: stop request timed out, will retry", sid)
        except RuntimeError as exc:  # e.g. the client was closed under us
            logger.warning("ray job %s: could not send stop: %s", sid, exc)
        return True

    def _cleanup_detached(self, sid: str, *, stop: bool, delete: bool) -> asyncio.Task:
        return self._track(asyncio.get_running_loop().create_task(self._cleanup(sid, stop=stop, delete=delete)))

    def _track(self, task: asyncio.Task) -> asyncio.Task:
        self._cleanups.add(task)
        task.add_done_callback(self._cleanups.discard)
        return task

    async def _cleanup(self, sid: str, *, stop: bool, delete: bool) -> None:
        try:
            if stop and not await self._wait_stopped(sid):
                return
            if delete:
                # Ray reports a terminal status before the job's supervisor
                # actor exits; deleting the record in that window makes Ray's
                # monitor write it back as a ghost "supervisor actor died"
                # FAILED job. Let the supervisor finish first.
                # (If this is cut short, sweep_finished removes it later.)
                await asyncio.sleep(self.delete_grace)
                await self.client.delete_job(sid)
        except RayJobsError as exc:
            if exc.kind != "not_found":
                logger.warning("ray job %s cleanup failed: %s", sid, exc)
        except Exception:
            logger.exception("ray job %s cleanup crashed", sid)

    async def _wait_stopped(self, sid: str) -> bool:
        """Wait until Ray reports the stopped ``sid`` finished.

        A job still PENDING on resources cannot act on a stop until it is
        scheduled, so keep watching (re-sending the stop) instead of giving
        up — otherwise it would start its entrypoint later, unsupervised.
        """
        begin = time.monotonic()
        last_stop = begin
        while True:
            await asyncio.sleep(0.5)
            try:
                status = str((await self.client.job_info(sid)).get("status"))
            except RayJobsError as exc:
                if exc.kind == "not_found":
                    return False
                status = "UNKNOWN"
            if status in TERMINAL_STATUSES:
                return True
            limit = self.pending_watch if status in ("PENDING", "UNKNOWN") else self.stop_grace
            if time.monotonic() - begin > limit:
                logger.warning("ray job %s still %s after %.0fs; giving up", sid, status, limit)
                return False
            if time.monotonic() - last_stop > 15:
                last_stop = time.monotonic()
                try:
                    await self.client.stop_job(sid)
                except RayJobsError:
                    pass
