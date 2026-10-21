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
# Never forwarded to a cluster: desktop containment markers break nested
# spawns there, device pinning belongs to Ray, and secrets would be visible
# to anyone who can read the job's runtime_env in the dashboard.
_DENY_ENV = re.compile(r"^(OMNIVOICE_DESKTOP_.*|CUDA_VISIBLE_DEVICES|.*(TOKEN|SECRET|PASSWORD|KEY).*)$", re.I)

ProgressFn = Callable[[Dict[str, Any]], Optional[Awaitable[None]]]


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
    test_mode: bool = False

    def payload(self) -> Dict[str, Any]:
        bad = sorted(k for k in self.env if _DENY_ENV.match(k))
        if bad:
            raise ValueError(f"refusing to send env vars {bad} to the Ray cluster")
        out: Dict[str, Any] = {"v": 1, "op": self.op, "engine": self.engine,
                               "params": dict(self.params), "env": dict(self.env)}
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
        self.keep_failed_jobs = keep_failed_jobs
        self.cache_dir = cache_dir
        self.python = python
        # Strong references: a cleanup must outlive the run that started it.
        self._cleanups: Set[asyncio.Task] = set()

    async def run(
        self,
        task: RayTask,
        *,
        timeout: Optional[float] = None,
        on_progress: Optional[ProgressFn] = None,
        submission_prefix: str = "vs",
    ) -> RayJobResult:
        """Run ``task`` as one job; ``timeout`` covers upload, queueing and execution."""
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
                if not await self.client.package_exists(uri):
                    await self.client.upload_package(uri, data)
                submitted = True  # before the POST: a cancel mid-request must still stop it
                await self.client.submit_job(
                    entrypoint=f"{self.python} {WORKER_ARGS}",
                    submission_id=sid,
                    runtime_env={"working_dir": uri, "env_vars": env_vars},
                    metadata={"app": "voicestudio", "op": task.op, "engine": task.engine},
                    entrypoint_num_cpus=task.num_cpus,
                    entrypoint_num_gpus=task.num_gpus,
                    entrypoint_memory=task.memory_bytes,
                )
                logger.info("ray job %s submitted (%s/%s)", sid, task.engine, task.op)
                status, logs = await self._wait(sid, on_progress)
                terminal = True
            result = await self._finish(sid, status, logs, started)
            await self._cleanup_later(sid, stop=False, delete=True)
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

    async def _wait(self, sid: str, on_progress: Optional[ProgressFn]):
        seen = errors = 0
        last_progress = 0.0
        while True:
            try:
                status = str((await self.client.job_info(sid)).get("status"))
                if status in TERMINAL_STATUSES:
                    logs = await self.client.job_logs(sid)
                    if on_progress is not None:
                        for event in proto.parse_events(logs).progress[seen:]:
                            await self._notify(on_progress, event)
                    return status, logs
                if on_progress is not None and time.monotonic() - last_progress >= self.progress_interval:
                    last_progress = time.monotonic()
                    events = proto.parse_events(await self.client.job_logs(sid)).progress
                    for event in events[seen:]:
                        await self._notify(on_progress, event)
                    seen = len(events)
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

    # -- cleanup -----------------------------------------------------------
    async def drain(self, timeout: Optional[float] = None) -> None:
        """Wait for outstanding stop/delete work (call on backend shutdown)."""
        if self._cleanups:
            await asyncio.wait(list(self._cleanups), timeout=timeout)

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
        return True

    def _cleanup_detached(self, sid: str, *, stop: bool, delete: bool) -> asyncio.Task:
        task = asyncio.get_running_loop().create_task(self._cleanup(sid, stop=stop, delete=delete))
        self._cleanups.add(task)
        task.add_done_callback(self._cleanups.discard)
        return task

    async def _cleanup_later(self, sid: str, *, stop: bool, delete: bool) -> None:
        # Shielded: a cancel arriving now must not drop the delete.
        await asyncio.shield(self._cleanup_detached(sid, stop=stop, delete=delete))

    async def _cleanup(self, sid: str, *, stop: bool, delete: bool) -> None:
        try:
            if stop and not await self._wait_stopped(sid):
                return
            if delete:
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
