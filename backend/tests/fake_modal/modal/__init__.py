"""A stand-in for the Modal SDK, for the driver's tests: a "sandbox" is a
local directory and its exec is a local subprocess. FAKE_MODAL_ROOT holds the
sandbox paths (/job, /vs-cache); FAKE_MODAL_LOG records the calls as JSON lines.
"""
import json
import os
import shutil
import subprocess
import sys

from . import exception  # noqa: F401

_ROOT = os.environ.get("FAKE_MODAL_ROOT", "")


def _record(event, **data):
    log = os.environ.get("FAKE_MODAL_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": event, **data}) + "\n")


def _local(path):
    for remote in ("/job", "/vs-cache"):
        if path == remote or path.startswith(remote + "/"):
            return os.path.join(_ROOT, remote.strip("/"), path[len(remote):].lstrip("/"))
    return path


class App:
    app_id = "ap-fake"

    @staticmethod
    def lookup(name, create_if_missing=False):
        if os.environ.get("MODAL_TOKEN_ID") != "ak-good":
            raise exception.AuthError("Token missing or invalid")
        _record("app", name=name)
        return App()


class Volume:
    @staticmethod
    def from_name(name, create_if_missing=False, version=None):
        _record("volume", name=name, version=version)
        return Volume()

    def hydrate(self):
        return self


class Image:
    @staticmethod
    def debian_slim(python_version=None):
        return Image()

    def apt_install(self, *packages):
        return self

    def add_local_file(self, local_path, remote_path, copy=False):
        _record("image_file", remote=remote_path, copy=copy)
        return self

    def run_commands(self, *commands):
        _record("image_build", commands=list(commands))
        return self


def _chunks(stream, size=37):
    while True:
        data = stream.read(size)
        if not data:
            return
        yield data


class _Proc:
    """Streams come back in arbitrary chunks, not lines, as with Modal."""

    def __init__(self, popen):
        self._p = popen
        self.stdout = _chunks(popen.stdout)
        self.stderr = _chunks(popen.stderr)

    def wait(self):
        return self._p.wait()


class _Filesystem:
    def copy_from_local(self, local, remote):
        target = _local(remote)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(local, target)


class Sandbox:
    object_id = "sb-fake"

    def __init__(self):
        self.filesystem = _Filesystem()
        self._procs = []

    @staticmethod
    def create(*args, **kwargs):
        _record("create", args=list(args), gpu=kwargs.get("gpu"), cpu=kwargs.get("cpu"),
                timeout=kwargs.get("timeout"), tags=kwargs.get("tags"), volumes=sorted(kwargs.get("volumes") or {}))
        for remote in ("/job", "/vs-cache"):
            os.makedirs(_local(remote), exist_ok=True)
        return Sandbox()

    def exec(self, *args, workdir=None, env=None):
        argv = [sys.executable if a == "python3" else _local(a) for a in args]
        if argv[0] == "sync":
            argv = [sys.executable, "-c", "pass"]
        full_env = dict(os.environ)
        full_env.update({k: _local(v) for k, v in (env or {}).items()})
        full_env.pop("PYTHONPATH", None)  # the worker must not see this fake
        popen = subprocess.Popen(argv, cwd=_local(workdir or "/job"), env=full_env, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._procs.append(popen)
        _record("exec", argv=list(args), env=sorted((env or {}).keys()))
        return _Proc(popen)

    def terminate(self):
        _record("terminate")
        for popen in self._procs:
            if popen.poll() is None:
                popen.kill()
