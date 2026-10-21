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
ENGINE_OPS = {"synthesize", "transcribe"}
# uv builds engine venvs when the node has none on PATH (pinned + verified).
UV_VERSION = "0.12.19"
UV_SHA256 = {
    "x86_64": "23bf5552d220e0842b65c862097b2ebaeba0064b74eda5e565e77fd25969d8c8",
    "aarch64": "0804e9b164c64b6914182d5920c08551958a095986f10a3731056df701126436",
}
INSTALL_TIMEOUT_S = 3600
# Job logs keep the base64 result; prune ours once nobody can still need them.
# Longer than any run's hard cap, so a quiet job's own log is never removed.
LOG_RETENTION_S = 6 * 3600
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
    last_beat = time.monotonic()
    with open(path, "a+") as fh:
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TaskError("cache", f"timed out waiting for cache lock {name!r}")
                if time.monotonic() - last_beat >= 10:
                    last_beat = time.monotonic()
                    proto.emit_progress(sys.stdout, "installing", None, f"waiting for another job ({name})")
                time.sleep(0.5)
        try:
            yield path
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _run_logged(argv: list, env: Dict[str, str], timeout: float, stage: str) -> None:
    """Run an install step, echoing its output (escaped) into the job log."""
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    pump = threading.Thread(target=_pump_text, args=(proc.stdout, sys.stderr), daemon=True)
    pump.start()
    deadline = time.monotonic() + timeout
    while True:
        try:
            rc = proc.wait(timeout=10)
            break
        except subprocess.TimeoutExpired:
            if time.monotonic() > deadline:
                proc.kill()
                proc.wait()
                raise TaskError(stage, f"{Path(argv[0]).name} timed out after {timeout:.0f}s")
            # Liveness for the backend's silence deadline and GPU-pool budget.
            proto.emit_progress(sys.stdout, "installing", None, f"still running {Path(argv[0]).name}")
    pump.join(timeout=5)
    if rc != 0:
        raise TaskError(stage, f"{Path(argv[0]).name} {argv[1] if len(argv) > 1 else ''} failed with exit code {rc}")


def find_uv() -> str:
    found = shutil.which("uv")
    if found:
        return found
    target = cache_root() / "bin" / f"uv-{UV_VERSION}"
    if target.exists():
        return str(target)
    import hashlib  # noqa: PLC0415
    import tarfile  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    arch = platform.machine()
    if arch not in UV_SHA256:
        raise TaskError("install", f"no uv build for {arch}; install uv on the cluster nodes")
    name = f"uv-{arch}-unknown-linux-gnu"
    url = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{name}.tar.gz"
    with cache_lock("uv"):
        if target.exists():
            return str(target)
        proto.emit_progress(sys.stdout, "installing", None, f"downloading uv {UV_VERSION}")
        with urllib.request.urlopen(url, timeout=120) as resp:
            blob = resp.read()
        if hashlib.sha256(blob).hexdigest() != UV_SHA256[arch]:
            raise TaskError("install", "downloaded uv failed its checksum")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=__import__("io").BytesIO(blob)) as tf:
            member = tf.extractfile(f"{name}/uv")
            if member is None:
                raise TaskError("install", "uv archive has no uv binary")
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(member.read())
            tmp.chmod(0o755)
            tmp.replace(target)
    return str(target)


_HAS_NVIDIA: Optional[bool] = None


def has_nvidia() -> bool:
    """Whether this node has a usable NVIDIA GPU (cached per job).

    Hardware, not visibility: Ray hides GPUs from jobs that asked for none,
    yet a venv built on a GPU node must get CUDA wheels. ``nvidia-smi -L``
    must succeed and list a GPU (a container with the driver mounted but no
    device prints "No devices were found").
    """
    global _HAS_NVIDIA
    if _HAS_NVIDIA is None:
        smi = shutil.which("nvidia-smi")
        ok = False
        if smi:
            try:
                env = {k: v for k, v in os.environ.items() if k != "CUDA_VISIBLE_DEVICES"}
                out = subprocess.run([smi, "-L"], capture_output=True, text=True, timeout=20, env=env)
                ok = out.returncode == 0 and "GPU " in out.stdout
            except (OSError, subprocess.SubprocessError):
                ok = False
        _HAS_NVIDIA = ok
    return _HAS_NVIDIA


def ensure_engine_venv(engine: str, recipe: Dict[str, Any]) -> str:
    """Build (once per recipe) the engine's venv in the cache; return its python."""
    key = str(recipe.get("key") or "")
    if not re.fullmatch(r"[0-9a-f]{8,64}", key) or not re.fullmatch(r"[A-Za-z0-9_.-]+", engine):
        raise TaskError("install", "invalid install recipe")
    # The wheel variant is part of the path: a venv built with CPU torch on a
    # GPU-less node must never be reused on a GPU node (shared caches).
    variant_name = "cuda" if has_nvidia() else "cpu"
    root = cache_root() / "engines" / engine / f"{key}-{variant_name}"
    python = root / ".venv" / "bin" / "python"
    marker = root / ".installed"
    if marker.exists() and python.exists():
        return str(python)
    with cache_lock(f"engine-{engine}", timeout=INSTALL_TIMEOUT_S):
        if marker.exists() and python.exists():
            return str(python)
        uv = find_uv()
        # Package builds and the import probe run third-party code: no
        # cluster credentials, same as the engine itself.
        env = {k: v for k, v in os.environ.items() if not _ENGINE_ENV_DENY.match(k)}
        env.update({
            "UV_NO_CONFIG": "1",  # never pick up a stray pyproject's constraints
            "UV_CACHE_DIR": str(cache_root() / "uv-cache"),
            "UV_PYTHON_INSTALL_DIR": str(cache_root() / "python"),
        })
        root.mkdir(parents=True, exist_ok=True)
        proto.emit_progress(sys.stdout, "installing", 0.05, f"creating {engine} environment")
        _run_logged([uv, "venv", "--clear", str(root / ".venv"), *recipe.get("venv_args", [])], env, 600, "install")
        variant = recipe.get(f"{variant_name}_args") or []
        proto.emit_progress(sys.stdout, "installing", 0.15, f"installing {engine} packages")
        _run_logged([uv, "pip", "install", "--python", str(python), *recipe.get("install_args", []), *variant],
                    env, INSTALL_TIMEOUT_S, "install")
        proto.emit_progress(sys.stdout, "installing", 0.9, f"verifying {engine}")
        _run_logged([str(python), "-c", str(recipe.get("probe_code") or "pass")], env, 300, "install")
        marker.write_text(f"{engine}\n{key}\n{time.time():.0f}\n")
    return str(python)


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

    def __init__(self, engine: str, script: Path, workdir: Path, env: Dict[str, str]) -> None:
        python = env.get("VS_ENGINE_PYTHON") or sys.executable
        self.proc = subprocess.Popen(
            [python, str(script)],
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
        while True:
            reply = self.recv()
            if reply is None:
                raise TaskError("engine", f"engine exited (code {self.proc.poll()}) during {msg.get('op')!r}")
            if reply.get("op") == "progress":
                # Model downloads/loads and generation heartbeats.
                pct = reply.get("percent")
                frac = float(pct) / 100.0 if isinstance(pct, (int, float)) else None
                proto.emit_progress(sys.stdout, f"engine:{reply.get('stage', 'working')}", frac,
                                    str(reply.get("message") or ""))
                continue
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
    info["has_nvidia"] = has_nvidia()
    info["uv"] = shutil.which("uv") or ""
    if info["has_nvidia"]:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            out = None
        for line in (out.stdout.strip().splitlines() if out is not None and out.returncode == 0 else []):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 4:
                continue
            nums = [int(p) if p.isdigit() else None for p in parts[1:]]  # "[N/A]" on MIG/vGPU
            info["gpus"].append({"name": parts[0], "total_mb": nums[0], "used_mb": nums[1], "free_mb": nums[2]})
    return info


def _engine_env(task: Dict[str, Any]) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not _ENGINE_ENV_DENY.match(k)}
    # Weights persist across jobs in the cluster cache (until the pod goes).
    env.setdefault("HF_HOME", str(cache_root() / "hf"))
    env.update({str(k): str(v) for k, v in (task.get("env") or {}).items()})
    return env


def _engine_script(task: Dict[str, Any], workdir: Path) -> Path:
    entry = str(task.get("entry") or "")
    engines_dir = (workdir / "engines").resolve()
    script = (workdir / entry).resolve()
    if not entry or engines_dir not in script.parents or not script.is_file():
        raise TaskError("engine", f"engine {task.get('engine')!r} is not available in this package")
    return script


def run_task(task: Dict[str, Any], workdir: Path) -> Dict[str, Any]:
    if int(task.get("v", 0)) != TASK_VERSION:
        raise TaskError("task", f"unsupported task version {task.get('v')!r}")
    op = task.get("op")
    if op == "probe":
        return {"op": "probe", "node": probe()}
    if op not in ENGINE_OPS and op not in ("_hold", "install", "batch"):
        raise TaskError("task", f"unknown op {op!r}")

    deadline = os.environ.get("VS_RAY_DEADLINE")
    if deadline and time.time() > float(deadline):
        raise TaskError("deadline", "the run's deadline passed while the job was queued")
    engine = str(task.get("engine") or "")
    env = _engine_env(task)
    recipe = task.get("install")
    if recipe:
        env["VS_ENGINE_PYTHON"] = ensure_engine_venv(engine, recipe)
    if op == "install":
        return {"op": "installed", "engine": engine, "key": (recipe or {}).get("key")}
    script = _engine_script(task, workdir)
    proto.emit_progress(sys.stdout, "engine_start", 0.05, engine)
    sidecar = Sidecar(engine, script, workdir, env)
    try:
        proto.emit_progress(sys.stdout, "engine_ready", 0.3, engine)
        if op == "_hold":
            # Test hook: keep the engine alive so stop/cancel can be exercised.
            if not task.get("test_mode"):
                raise TaskError("task", "_hold is test-only")
            print(f"vs_ray_worker: holding sidecar pid {sidecar.proc.pid}", flush=True)
            time.sleep(float(task.get("params", {}).get("seconds", 60)))
            return {"op": "_hold"}
        inputs = _input_paths(task, workdir)
        if op == "batch":
            return _run_batch(sidecar, dict(task.get("params") or {}), inputs)
        params = dict(task.get("params") or {})
        params.update(inputs)
        reply = sidecar.call({"op": op, **params})
        proto.emit_progress(sys.stdout, "engine_done", 0.95, engine)
        return reply
    finally:
        sidecar.close()


def _input_paths(task: Dict[str, Any], workdir: Path) -> Dict[str, str]:
    """Param name -> absolute path of each shipped input file."""
    inputs_dir = (workdir / "inputs").resolve()
    out: Dict[str, str] = {}
    for name, rel in (task.get("inputs") or {}).items():
        path = (workdir / rel).resolve()
        if inputs_dir not in path.parents:
            raise TaskError("task", f"input {name!r} is outside the package inputs")
        out[name] = str(path)
    return out


def _run_batch(sidecar: "Sidecar", params: Dict[str, Any], inputs: Dict[str, str]) -> Dict[str, Any]:
    """Many calls on ONE engine process: the model loads once for all items.

    ``params``: {"call": <engine op>, "shared": {...}, "items": [{...}, ...]}.
    A string value "@<param>" in an item names a shipped input file.
    Per-item failures are reported per item; if the engine process dies, the
    remaining items fail without a restart.
    """
    call = params.get("call")
    if call not in ENGINE_OPS:
        raise TaskError("task", f"unknown batch call {call!r}")
    shared = dict(params.get("shared") or {})
    items = params.get("items") or []
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise TaskError("task", "batch items must be objects")

    def resolve(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("@"):
            if value[1:] not in inputs:
                raise TaskError("task", f"batch item names a missing input {value!r}")
            return inputs[value[1:]]
        return value

    results: list = []
    for index, item in enumerate(items):
        if sidecar.proc.poll() is not None:
            results.append({"op": "error", "stage": "engine", "message": "engine exited earlier in the batch"})
            continue
        msg = {"op": call, **shared, **{k: resolve(v) for k, v in item.items()}}
        try:
            results.append(sidecar.call(msg))
        except TaskError as exc:
            results.append({"op": "error", "stage": exc.stage, "message": str(exc)})
        proto.emit_progress(sys.stdout, "item_done", (index + 1) / max(1, len(items)), f"{index + 1}/{len(items)}")
    return {"op": "batch", "results": results}


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
