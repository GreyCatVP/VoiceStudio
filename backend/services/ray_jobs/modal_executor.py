"""Run one model step in a Modal Sandbox: the Modal provider of remote execution.

Same contract as ``RayJobsExecutor.run``: the same job package and stdlib
worker, the same result frames, the same errors. The Modal SDK is not an app
dependency: ``modal_driver/vs_modal_driver.py`` runs in a uv-managed
environment that pins it, and this executor talks to it over JSON lines.
One sandbox per run, terminated when the run ends (also on cancellation,
timeout or a crash of this process: the driver terminates the sandbox when
its stdin closes), so the GPU is released and billing stops.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ray_worker import vs_ray_protocol as proto
from services.ray_jobs.executor import ExecutorRetired, ProgressFn, RayJobFailed, RayJobResult, RayTask
from services.ray_jobs.package import build_package

logger = logging.getLogger(__name__)

MODAL_SDK = "modal==1.6.2"
DRIVER_PYTHON = "3.12"
DRIVER = Path(__file__).resolve().parents[2] / "modal_driver" / "vs_modal_driver.py"
# Sandbox lifetime beyond the caller's deadline (container start, upload).
_LIFETIME_MARGIN_S = 600
_MAX_LIFETIME_S = 24 * 3600
_CANCEL_GRACE_S = 30.0


class ModalUnavailable(RuntimeError):
    """uv (which provides the Modal SDK environment) is missing."""


def _driver_command() -> List[str]:
    from services.sidecar_install import _locate_uv  # noqa: PLC0415

    uv = _locate_uv()
    if not uv:
        raise ModalUnavailable("Modal needs uv to install its SDK; uv was not found")
    return [uv, "run", "--quiet", "--no-project", "--python", DRIVER_PYTHON, "--with", MODAL_SDK,
            "python", "-I", str(DRIVER)]


def _driver_env(token_id: str, token_secret: str) -> Dict[str, str]:
    from core.config import DATA_DIR  # noqa: PLC0415
    from services.sidecar_install import uv_subprocess_env  # noqa: PLC0415

    env = uv_subprocess_env(Path(DATA_DIR))
    # Only the credentials this run needs; a profile in ~/.modal.toml never applies.
    for key in [k for k in env if k.startswith("MODAL_")]:
        env.pop(key)
    env.update(MODAL_TOKEN_ID=token_id, MODAL_TOKEN_SECRET=token_secret, PYTHONUNBUFFERED="1")
    return env


class _Driver:
    """One driver process: request in, JSON lines out, "cancel" to stop."""

    def __init__(self, request: Dict[str, Any], env: Dict[str, str]) -> None:
        self.request = request
        self.env = env
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.stderr_tail: List[str] = []

    async def __aenter__(self) -> "_Driver":
        self.proc = await asyncio.create_subprocess_exec(
            *_driver_command(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=self.env, limit=64 * 1024 * 1024)
        self._stderr_task = asyncio.get_running_loop().create_task(self._drain_stderr())
        self.proc.stdin.write((json.dumps(self.request) + "\n").encode())
        await self.proc.stdin.drain()
        return self

    async def _drain_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        async for raw in self.proc.stderr:
            self.stderr_tail = (self.stderr_tail + [raw.decode("utf-8", "replace").rstrip()])[-40:]

    async def messages(self):
        assert self.proc is not None and self.proc.stdout is not None
        async for raw in self.proc.stdout:
            try:
                yield json.loads(raw)
            except ValueError:
                continue  # not ours (a library print)

    async def cancel(self) -> None:
        """Ask the driver to terminate the sandbox, then make sure it exits."""
        proc = self.proc
        if proc is None or proc.returncode is not None:
            return
        with contextlib.suppress(Exception):
            proc.stdin.write(b"cancel\n")
            await proc.stdin.drain()
        try:
            await asyncio.wait_for(proc.wait(), _CANCEL_GRACE_S)
        except asyncio.TimeoutError:
            logger.warning("modal driver did not exit after cancel; killing it")
            with contextlib.suppress(ProcessLookupError):
                proc.kill()

    async def __aexit__(self, *exc) -> None:
        proc = self.proc
        if proc is None:
            return
        if proc.returncode is None:
            # Closing stdin makes the driver terminate the sandbox and exit.
            with contextlib.suppress(Exception):
                proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), _CANCEL_GRACE_S)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
        self._stderr_task.cancel()
        with contextlib.suppress(BaseException):
            await self._stderr_task


class ModalExecutor:
    def __init__(self, *, token_id: str, token_secret: str, gpu: str = "", app: str = "voicestudio",
                 volume: str = "voicestudio-cache") -> None:
        self.token_id = token_id
        self.token_secret = token_secret
        self.gpu = gpu
        self.app = app
        self.volume = volume
        self.retired = False
        self._runs: Set[asyncio.Task] = set()
        self._cleanups: Set[asyncio.Task] = set()  # runtime shutdown symmetry with RayJobsExecutor

    def _env(self) -> Dict[str, str]:
        return _driver_env(self.token_id, self.token_secret)

    async def probe(self, timeout: float = 120.0) -> Dict[str, Any]:
        """Check the credentials (and create the app and volume if missing)."""
        request = {"op": "probe", "app": self.app, "volume": self.volume}
        async with asyncio.timeout(timeout):
            async with _Driver(request, self._env()) as driver:
                async for msg in driver.messages():
                    if msg.get("t") == "probe":
                        return msg
                    if msg.get("t") == "error":
                        raise RayJobFailed(str(msg.get("message")), submission_id="", status=str(msg.get("kind")).upper(),
                                           stage="modal")
                raise RayJobFailed("Modal driver exited without an answer: " + " | ".join(driver.stderr_tail[-3:]),
                                   submission_id="", status="FAILED", stage="modal")

    async def run(self, task: RayTask, *, timeout: Optional[float] = None, idle_timeout: Optional[float] = None,
                  on_progress: Optional[ProgressFn] = None, submission_prefix: str = "vs") -> RayJobResult:
        if self.retired:
            raise ExecutorRetired("Modal settings changed; retry with the current executor")
        me = asyncio.current_task()
        if me is not None:
            self._runs.add(me)
        try:
            return await self._run(task, timeout=timeout, idle_timeout=idle_timeout, on_progress=on_progress,
                                   submission_prefix=submission_prefix)
        finally:
            self._runs.discard(me)

    async def _run(self, task: RayTask, *, timeout, idle_timeout, on_progress, submission_prefix) -> RayJobResult:
        _, data, _ = build_package(task.payload(), task.inputs)
        sid = f"{submission_prefix}-{task.engine or task.op}-{uuid.uuid4().hex[:12]}".replace("_", "")
        env = {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8:backslashreplace"}
        if timeout is not None:
            env["VS_RAY_DEADLINE"] = f"{time.time() + timeout:.0f}"
        lifetime = min(_MAX_LIFETIME_S, int((timeout or 6 * 3600) + _LIFETIME_MARGIN_S))
        started = time.monotonic()
        fd, package_path = tempfile.mkstemp(prefix="vs-modal-", suffix=".zip")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            request = {
                "op": "run", "app": self.app, "volume": self.volume, "package_path": package_path,
                "gpu": self.gpu if task.num_gpus else "", "cpu": task.num_cpus,
                "memory_mb": int(task.memory_bytes / 2 ** 20) if task.memory_bytes else None,
                "timeout": lifetime, "env": env, "engine": task.engine, "op_name": task.op,
            }
            async with _Driver(request, self._env()) as driver:
                try:
                    async with asyncio.timeout(timeout):
                        code, stderr, logs = await self._follow(driver, sid, on_progress, idle_timeout)
                except BaseException:
                    await asyncio.shield(driver.cancel())
                    raise
        finally:
            with contextlib.suppress(OSError):
                os.remove(package_path)
        return self._finish(sid, code, stderr, logs, started)

    async def _follow(self, driver: _Driver, sid: str, on_progress: Optional[ProgressFn],
                      idle_timeout: Optional[float]):
        lines: List[str] = []
        running = False
        last_activity = time.monotonic()
        messages = driver.messages().__aiter__()
        while True:
            wait = None
            if idle_timeout is not None and running:
                wait = max(0.1, idle_timeout - (time.monotonic() - last_activity))
            try:
                msg = await asyncio.wait_for(messages.__anext__(), wait)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Modal job {sid} made no progress for {idle_timeout:.0f}s") from None
            except StopAsyncIteration:
                raise RayJobFailed("Modal driver exited unexpectedly: " + " | ".join(driver.stderr_tail[-3:]),
                                   submission_id=sid, status="FAILED", stage="modal") from None
            kind = msg.get("t")
            if kind == "status":
                running = msg.get("s") == "running"
                last_activity = time.monotonic()
                logger.info("modal job %s: %s", sid, msg.get("s"))
            elif kind == "out":
                line = str(msg.get("l", ""))
                lines.append(line)
                if line.startswith(proto.MARK + " PROGRESS"):  # one frame per line
                    last_activity = time.monotonic()
                    if on_progress is not None:
                        for event in proto.parse_events(line).progress:
                            await self._notify(on_progress, event)
            elif kind == "exit":
                return int(msg.get("code", 1)), str(msg.get("stderr") or ""), "\n".join(lines)
            elif kind == "error":
                raise RayJobFailed(f"Modal {msg.get('kind')} error: {msg.get('message')}", submission_id=sid,
                                   status=str(msg.get("kind") or "error").upper(), stage="modal")

    @staticmethod
    async def _notify(on_progress: ProgressFn, event: Dict[str, Any]) -> None:
        try:
            maybe = on_progress(event)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception:
            logger.warning("modal job progress callback failed", exc_info=True)

    @staticmethod
    def _finish(sid: str, code: int, stderr: str, logs: str, started: float) -> RayJobResult:
        if code != 0:
            events = proto.parse_events(logs)
            err = events.errors[-1] if events.errors else {}
            detail = err.get("message") or (stderr.strip().splitlines() or [f"exit code {code}"])[-1]
            raise RayJobFailed(str(detail), submission_id=sid, status="FAILED", stage=str(err.get("stage", "job")))
        try:
            parsed = proto.parse_log(logs)
        except proto.ProtocolError as exc:
            raise RayJobFailed(f"unreadable job result: {exc}", submission_id=sid, status="SUCCEEDED",
                               stage="result") from exc
        if parsed.result is None:
            raise RayJobFailed("job succeeded without a result", submission_id=sid, status="SUCCEEDED", stage="result")
        return RayJobResult(sid, parsed.result, parsed.progress, time.monotonic() - started)

    async def wait_idle(self, timeout: Optional[float] = None) -> None:
        self.retired = True
        pending = [t for t in self._runs if not t.done() and t is not asyncio.current_task()]
        if pending:
            await asyncio.wait(pending, timeout=timeout)

    async def drain(self, timeout: Optional[float] = None) -> None:
        return None

    async def aclose(self) -> None:
        return None
