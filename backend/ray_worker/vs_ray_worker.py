"""Entry point of one VoiceStudio Ray job (runs on the Ray cluster).

The backend zips this file, ``vs_ray_protocol.py``, the engine sidecar code
and the run's inputs into a Ray ``working_dir`` package, then submits

    python vs_ray_worker.py --task task.json

through the dashboard Jobs API. One job is one run: the engine sidecar is
started, used, and the job exits — process exit is what returns the GPU
memory, so nothing outlives the run.

Engines speak the same length-prefixed JSON wire protocol as
``services/subprocess_backend.py`` (see ``engines/_echo/main.py``), so an
engine sidecar runs unchanged here.

Stdlib-only on purpose: it must start under the cluster's bare Python.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import shutil
import signal
import struct
import re
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vs_ray_protocol as proto  # noqa: E402

MAX_FRAME_BYTES = 64 * 1024 * 1024
TASK_VERSION = 1
# Engines runnable in this package: engine id -> sidecar script (relative).
ENGINES = {"_echo": "engines/_echo/main.py"}
ENGINE_OPS = {"synthesize", "transcribe"}
# Job logs keep the base64 result; prune ours once nobody can still need them.
LOG_RETENTION_S = 30 * 60
# Not inherited by engine code: cluster credentials and anything secret-like.
_ENGINE_ENV_DENY = re.compile(r"^(RAY_AUTH_TOKEN|RAY_JOB_CONFIG_JSON_ENV_VAR|.*(TOKEN|SECRET|PASSWORD).*)$", re.I)


class TaskError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def cache_root() -> Path:
    root = Path(os.environ.get("VS_RAY_CACHE") or Path.home() / ".cache" / "voicestudio-ray")
    root.mkdir(parents=True, exist_ok=True)
    return root


@contextlib.contextmanager
def cache_lock(name: str, timeout: float = 1800.0) -> Iterator[Path]:
    """Exclusive cross-process lock for one cache entry (engine install, weights).

    Two jobs that start after a pod restart must not install the same engine
    venv or download the same weights at once.
    """
    import fcntl  # noqa: PLC0415 - POSIX only; Ray clusters run Linux

    locks = cache_root() / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    path = locks / f"{name}.lock"
    deadline = time.monotonic() + timeout
    with open(path, "a+") as fh:
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TaskError("cache", f"timed out waiting for cache lock {name!r}")
                time.sleep(0.5)
        try:
            yield path
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _die_with_parent() -> None:
    """preexec_fn: kill the sidecar if this worker dies (Linux only)."""
    try:
        import ctypes  # noqa: PLC0415

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def _pump_text(src, dst) -> None:
    for raw in iter(src.readline, b""):
        dst.write(raw.decode("utf-8", "backslashreplace"))
        dst.flush()


class Sidecar:
    """One engine sidecar process speaking the length-prefixed protocol."""

    def __init__(self, engine: str, workdir: Path, env: Dict[str, str]) -> None:
        script = ENGINES.get(engine)
        if script is None:
            raise TaskError("engine", f"engine {engine!r} is not available in this package")
        python = env.get("VS_ENGINE_PYTHON") or sys.executable
        self.proc = subprocess.Popen(
            [python, str(workdir / script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(workdir),
            env=env,
            preexec_fn=_die_with_parent if sys.platform.startswith("linux") else None,
        )
        # Ray's /logs endpoint decodes the log as strict UTF-8 and fails for
        # good on one stray byte, so engine stderr is re-emitted escaped.
        self._pump = threading.Thread(target=_pump_text, args=(self.proc.stderr, sys.stderr), daemon=True)
        self._pump.start()
        ready = self.recv()
        if not ready or ready.get("op") != "ready":
            raise TaskError("engine", f"engine {engine!r} did not report ready: {ready!r}")

    def send(self, obj: Dict[str, Any]) -> None:
        body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        assert self.proc.stdin is not None
        self.proc.stdin.write(struct.pack("!I", len(body)) + body)
        self.proc.stdin.flush()

    def recv(self) -> Optional[Dict[str, Any]]:
        assert self.proc.stdout is not None
        header = self.proc.stdout.read(4)
        if len(header) < 4:
            return None
        (n,) = struct.unpack("!I", header)
        if n > MAX_FRAME_BYTES:
            raise TaskError("engine", f"frame too large: {n}")
        body = self.proc.stdout.read(n)
        if len(body) < n:
            raise TaskError("engine", "engine closed its pipe mid-frame")
        return json.loads(body.decode("utf-8"))

    def call(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        self.send(msg)
        reply = self.recv()
        if reply is None:
            raise TaskError("engine", f"engine exited (code {self.proc.poll()}) during {msg.get('op')!r}")
        if reply.get("op") == "error":
            raise TaskError(str(reply.get("stage", "engine")), str(reply.get("message", "engine error")))
        return reply

    def close(self, timeout: float = 10.0) -> None:
        if self.proc.poll() is None:
            with contextlib.suppress(Exception):
                self.send({"op": "shutdown"})
                if self.proc.stdin:
                    self.proc.stdin.close()
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def probe() -> Dict[str, Any]:
    """Describe this node for the settings page's connection test."""
    info: Dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "cache_dir": str(cache_root()),
        "cache_free_gb": round(shutil.disk_usage(cache_root()).free / 1e9, 1),
        "gpus": [],
    }
    if shutil.which("nvidia-smi"):
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20,
        )
        for line in out.stdout.strip().splitlines():
            name, total, used, free = [p.strip() for p in line.split(",")]
            info["gpus"].append({"name": name, "total_mb": int(total), "used_mb": int(used), "free_mb": int(free)})
    return info


def _engine_env(task: Dict[str, Any]) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not _ENGINE_ENV_DENY.match(k)}
    env.update({str(k): str(v) for k, v in (task.get("env") or {}).items()})
    return env


def run_task(task: Dict[str, Any], workdir: Path) -> Dict[str, Any]:
    if int(task.get("v", 0)) != TASK_VERSION:
        raise TaskError("task", f"unsupported task version {task.get('v')!r}")
    op = task.get("op")
    if op == "probe":
        return {"op": "probe", "node": probe()}
    if op not in ENGINE_OPS and op != "_hold":
        raise TaskError("task", f"unknown op {op!r}")

    deadline = os.environ.get("VS_RAY_DEADLINE")
    if deadline and time.time() > float(deadline):
        raise TaskError("deadline", "the run's deadline passed while the job was queued")
    engine = str(task.get("engine") or "")
    proto.emit_progress(sys.stdout, "engine_start", 0.05, engine)
    sidecar = Sidecar(engine, workdir, _engine_env(task))
    try:
        proto.emit_progress(sys.stdout, "engine_ready", 0.3, engine)
        if op == "_hold":
            # Test hook: keep the engine alive so stop/cancel can be exercised.
            if not task.get("test_mode"):
                raise TaskError("task", "_hold is test-only")
            print(f"vs_ray_worker: holding sidecar pid {sidecar.proc.pid}", flush=True)
            time.sleep(float(task.get("params", {}).get("seconds", 60)))
            return {"op": "_hold"}
        params = dict(task.get("params") or {})
        inputs_dir = (workdir / "inputs").resolve()
        for name, rel in (task.get("inputs") or {}).items():
            path = (workdir / rel).resolve()
            if inputs_dir not in path.parents:
                raise TaskError("task", f"input {name!r} is outside the package inputs")
            params[name] = str(path)
        reply = sidecar.call({"op": op, **params})
        proto.emit_progress(sys.stdout, "engine_done", 0.95, engine)
        return reply
    finally:
        sidecar.close()


def prune_old_job_logs(now: Optional[float] = None) -> int:
    """Delete our finished jobs' driver logs (they hold result audio)."""
    logs = Path(os.environ.get("VS_RAY_LOG_DIR") or "/tmp/ray/session_latest/logs")
    if not logs.is_dir():
        return 0
    now = time.time() if now is None else now
    removed = 0
    for path in logs.glob("job-driver-vs-*.log"):
        with contextlib.suppress(OSError):
            if now - path.stat().st_mtime > LOG_RETENTION_S:
                path.unlink()
                removed += 1
    return removed


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    args = parser.parse_args(argv)
    workdir = Path(__file__).resolve().parent
    # Ray stops a job with SIGTERM; turn it into a normal exit so the sidecar
    # is closed by the finally blocks (PDEATHSIG covers SIGKILL).
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="backslashreplace")
    with contextlib.suppress(Exception):
        prune_old_job_logs()
    stage = "task"
    try:
        task = json.loads((workdir / args.task).read_text("utf-8"))
        proto.emit_progress(sys.stdout, "start", 0.0, str(task.get("op")))
        result = run_task(task, workdir)
        stage = "result"
        proto.emit_result(sys.stdout, result)
        return 0
    except TaskError as exc:
        proto.emit_error(sys.stdout, exc.stage, str(exc))
    except SystemExit:
        raise
    except Exception as exc:  # report, then fail the job
        traceback.print_exc()
        proto.emit_error(sys.stdout, stage, f"{type(exc).__name__}: {exc}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
