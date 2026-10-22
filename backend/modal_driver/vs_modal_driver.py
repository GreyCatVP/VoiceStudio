"""Run one VoiceStudio job package in a Modal Sandbox (the Modal provider).

The backend starts this script in a uv-managed environment that has the
``modal`` SDK (never in the app's own venv) and talks to it over JSON lines:

    stdin  <- {"op": "run", ...} or {"op": "probe", ...}, then optionally "cancel"
    stdout -> {"t": "status", "s": "..."}       lifecycle (creating, uploading, running)
              {"t": "out", "l": "<line>"}        the worker's stdout (protocol frames)
              {"t": "exit", "code": n, "stderr": "<tail>"}
              {"t": "probe", "ok": true, ...}
              {"t": "error", "kind": "auth" | "not_found" | "error", "message": "..."}

A sandbox mirrors a Ray job: one container per run that starts the same
stdlib-only worker on the same package, and ends (``terminate``) when the
run does, so the GPU is released and billing stops. Engine environments,
uv's cache and model downloads persist on a Modal Volume between runs.
Credentials arrive as MODAL_TOKEN_ID / MODAL_TOKEN_SECRET in this process's
environment; they are never passed into the sandbox.
"""
from __future__ import annotations

import collections
import json
import sys
import threading
import traceback

CACHE_MOUNT = "/vs-cache"
JOB_DIR = "/job"
# Engine environments live in the image, not on the volume: a venv is tens of
# thousands of small files, and every file lookup on a Modal Volume is a
# network round trip (a cold `import torch` from it took minutes). The volume
# keeps what is read as a few large files: model weights.
ENGINE_CACHE = "/opt/vs-cache"
PYTHON_VERSION = "3.12"
# Build tools for engines that compile wheels; ffmpeg/libsndfile for audio I/O.
APT_PACKAGES = ("build-essential", "git", "curl", "ca-certificates", "ffmpeg", "libsndfile1")
UNPACK_AND_RUN = (
    "import os, sys, zipfile\n"
    "zipfile.ZipFile('package.zip').extractall('.')\n"
    "os.remove('package.zip')\n"
    "os.execv(sys.executable, [sys.executable, 'vs_ray_worker.py', '--task', 'task.json'])\n"
)

_out_lock = threading.Lock()


def emit(obj: dict) -> None:
    with _out_lock:
        sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def _kind(exc: BaseException) -> str:
    import modal.exception as mexc

    if isinstance(exc, mexc.AuthError):
        return "auth"
    if isinstance(exc, mexc.NotFoundError):
        return "not_found"
    return "error"


def _app_and_volume(req: dict):
    import modal

    app = modal.App.lookup(str(req.get("app") or "voicestudio"), create_if_missing=True)
    # v2: uv hard-links its cache into engine envs; v1 volumes refuse hard links.
    volume = modal.Volume.from_name(str(req.get("volume") or "voicestudio-cache"), create_if_missing=True, version=2)
    return app, volume


def probe(req: dict) -> None:
    app, volume = _app_and_volume(req)
    volume.hydrate()
    emit({"t": "probe", "ok": True, "app_id": getattr(app, "app_id", None)})


def run(req: dict, cancel: threading.Event) -> None:
    import modal

    emit({"t": "status", "s": "creating"})
    app, volume = _app_and_volume(req)
    image = modal.Image.debian_slim(python_version=PYTHON_VERSION).apt_install(*APT_PACKAGES)
    if req.get("install_package_path"):
        # One image per install recipe (Modal caches it by content): the
        # worker's own install op, run at build time.
        cuda = "VS_RAY_ASSUME_NVIDIA=1 " if req.get("gpu") else ""
        image = image.add_local_file(str(req["install_package_path"]), "/opt/vs/install.zip", copy=True).run_commands(
            "cd /opt/vs && python3 -c \"import zipfile; zipfile.ZipFile('install.zip').extractall('install')\"",
            f"cd /opt/vs/install && {cuda}VS_RAY_CACHE={ENGINE_CACHE} PYTHONUNBUFFERED=1 "
            "python3 vs_ray_worker.py --task task.json")
    kwargs = {}
    if req.get("gpu"):
        kwargs["gpu"] = str(req["gpu"])
    if req.get("cpu"):
        kwargs["cpu"] = float(req["cpu"])
    if req.get("memory_mb"):
        kwargs["memory"] = int(req["memory_mb"])
    sandbox = modal.Sandbox.create(
        "sleep", "infinity", app=app, image=image, volumes={CACHE_MOUNT: volume}, workdir=JOB_DIR,
        timeout=int(req.get("timeout") or 3600), tags={"app": "voicestudio", "engine": str(req.get("engine") or ""),
                                                     "op": str(req.get("op") or "")}, **kwargs)
    terminated = threading.Event()

    def terminate() -> None:
        if not terminated.is_set():
            terminated.set()
            try:
                sandbox.terminate()
            except Exception:  # already gone
                pass

    def watch_cancel() -> None:
        cancel.wait()
        terminate()

    threading.Thread(target=watch_cancel, daemon=True).start()
    try:
        emit({"t": "status", "s": "uploading", "sandbox_id": sandbox.object_id})
        sandbox.filesystem.copy_from_local(str(req["package_path"]), f"{JOB_DIR}/package.zip")
        if cancel.is_set():
            return
        emit({"t": "status", "s": "running"})
        env = {str(k): str(v) for k, v in (req.get("env") or {}).items()}
        env["VS_RAY_CACHE"] = ENGINE_CACHE
        env.setdefault("HF_HOME", f"{CACHE_MOUNT}/hf")  # runtime weight downloads persist
        proc = sandbox.exec("python3", "-c", UNPACK_AND_RUN, workdir=JOB_DIR, env=env)
        tail: "collections.deque[str]" = collections.deque(maxlen=60)

        def drain_stderr() -> None:
            try:
                for chunk in proc.stderr:
                    tail.extend(chunk.splitlines())
            except Exception:
                pass

        err_thread = threading.Thread(target=drain_stderr, daemon=True)
        err_thread.start()
        # The stream yields chunks, not lines: re-split so no frame is cut in two.
        pending = ""
        for chunk in proc.stdout:
            pending += chunk
            *lines, pending = pending.split("\n")
            for line in lines:
                emit({"t": "out", "l": line})
        if pending:
            emit({"t": "out", "l": pending})
        code = proc.wait()
        err_thread.join(timeout=5)
        if not terminated.is_set():
            try:  # persist new engine environments / downloads on the volume
                sandbox.exec("sync", CACHE_MOUNT).wait()
            except Exception:
                pass
        emit({"t": "exit", "code": code, "stderr": "\n".join(tail)[-6000:]})
    finally:
        terminate()


def main() -> int:
    first = sys.stdin.readline()
    try:
        req = json.loads(first)
    except ValueError:
        emit({"t": "error", "kind": "error", "message": "bad request"})
        return 2
    cancel = threading.Event()

    def read_control() -> None:
        for line in sys.stdin:
            if line.strip() == "cancel":
                cancel.set()
                return
        cancel.set()  # the backend went away: never leave a GPU running

    threading.Thread(target=read_control, daemon=True).start()
    try:
        if req.get("op") == "probe":
            probe(req)
        else:
            run(req, cancel)
    except BaseException as exc:  # report, then exit non-zero
        traceback.print_exc(file=sys.stderr)
        try:
            kind = _kind(exc)
        except Exception:
            kind = "error"
        emit({"t": "error", "kind": kind, "message": f"{type(exc).__name__}: {exc}"[:2000]})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
