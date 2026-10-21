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

# Engine id -> files (relative to backend/engines/<id>/) shipped with the job.
ENGINE_FILES: Dict[str, Tuple[str, ...]] = {"_echo": ("main.py",)}


def _add(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname, date_time=_ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


def build_package(task: Mapping[str, Any], inputs: Mapping[str, bytes]) -> Tuple[str, bytes, Dict[str, Any]]:
    """Return ``(uri, zip_bytes, task_with_input_paths)``."""
    engine = task.get("engine")
    if engine and engine not in ENGINE_FILES:
        raise ValueError(f"engine {engine!r} cannot run on Ray yet")
    task = dict(task)
    input_paths: Dict[str, str] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in ("vs_ray_worker.py", "vs_ray_protocol.py"):
            _add(zf, name, (WORKER_DIR / name).read_bytes())
        if engine:
            for rel in ENGINE_FILES[engine]:
                _add(zf, f"engines/{engine}/{rel}", (ENGINES_DIR / engine / rel).read_bytes())
        for name in sorted(inputs):
            if not _SAFE_NAME.match(name) or name in {".", ".."}:
                raise ValueError(f"unsafe input name {name!r}")
            _add(zf, f"inputs/{name}", inputs[name])
            input_paths[name] = f"inputs/{name}"
        task["inputs"] = input_paths
        _add(zf, "task.json", json.dumps(task, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    data = buf.getvalue()
    if len(data) > MAX_PACKAGE_BYTES:
        raise ValueError(f"job package is {len(data)} bytes; limit is {MAX_PACKAGE_BYTES}")
    uri = f"gcs://_ray_pkg_{hashlib.sha1(data).hexdigest()}.zip"
    return uri, data, task
