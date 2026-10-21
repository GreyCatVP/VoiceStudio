"""Build the working_dir package for one Ray job.

The zip holds the worker, the shared protocol module, the engine sidecar code
and the run's input files. It is content-addressed exactly like Ray's own
``get_uri_for_package`` (``gcs://_ray_pkg_<sha1>.zip``), with fixed timestamps
so identical runs reuse one upload.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[2]
WORKER_DIR = BACKEND_DIR / "ray_worker"
ENGINES_DIR = BACKEND_DIR / "engines"

# Ray's default GCS package limit is ~512 MiB; stay well below it.
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
_ZIP_DATE = (2020, 1, 1, 0, 0, 0)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _add(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname, date_time=_ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


def build_package(task: Mapping[str, Any], inputs: Mapping[str, bytes]) -> Tuple[str, bytes, Dict[str, Any]]:
    """Return ``(uri, zip_bytes, task_with_input_paths)``.

    Input names are ``<param>[.<ext>]``: the worker passes the file's path as
    ``params[<param>]`` and the extension stays for format sniffing.
    """
    from services.ray_jobs.engines import ray_engine  # noqa: PLC0415

    engine_id = task.get("engine")
    engine = ray_engine(engine_id) if engine_id else None
    if engine_id and engine is None:
        raise ValueError(f"engine {engine_id!r} cannot run on Ray yet")
    task = dict(task)
    input_paths: Dict[str, str] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in ("vs_ray_worker.py", "vs_ray_protocol.py"):
            _add(zf, name, (WORKER_DIR / name).read_bytes())
        if engine is not None:
            for rel in engine.files:
                _add(zf, f"engines/{engine.directory}/{rel}", (ENGINES_DIR / engine.directory / rel).read_bytes())
            task["entry"] = f"engines/{engine.directory}/{engine.entry}"
        for name in sorted(inputs):
            if not _SAFE_NAME.match(name) or name.startswith("."):
                raise ValueError(f"unsafe input name {name!r}")
            param = name.split(".", 1)[0]
            if param in input_paths:
                raise ValueError(f"two inputs for parameter {param!r}")
            _add(zf, f"inputs/{name}", inputs[name])
            input_paths[param] = f"inputs/{name}"
        task["inputs"] = input_paths
        _add(zf, "task.json", json.dumps(task, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    data = buf.getvalue()
    if len(data) > MAX_PACKAGE_BYTES:
        raise ValueError(f"job package is {len(data)} bytes; limit is {MAX_PACKAGE_BYTES}")
    uri = f"gcs://_ray_pkg_{hashlib.sha1(data).hexdigest()}.zip"
    return uri, data, task
