"""Which engine sidecars can run as Ray jobs, and how the cluster installs them.

An engine qualifies when its sidecar script is self-contained (stdlib plus
its own venv's packages, no imports from this backend) and its venv comes
from PyPI pins alone. The install recipe is derived from the engine's
``SidecarSpec`` so the cluster builds the same venv the local installer does.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class RayEngine:
    engine_id: str
    directory: str  # under backend/engines/
    files: Tuple[str, ...]  # shipped with every job
    entry: str  # sidecar script, one of ``files``
    gpu: bool  # needs a GPU share on the cluster
    env: Tuple[Tuple[str, str], ...] = ()  # non-secret env the sidecar needs


RAY_ENGINES: Dict[str, RayEngine] = {
    # Test engine: stdlib-only, runs under the cluster's own Python.
    "_echo": RayEngine("_echo", "_echo", ("main.py",), "main.py", gpu=False),
    # CPU (onnxruntime); pins its weights revision through constants.py.
    "supertonic3": RayEngine("supertonic3", "supertonic3", ("sidecar.py", "constants.py"), "sidecar.py", gpu=False),
    "voxcpm2": RayEngine("voxcpm2", "voxcpm2_subprocess", ("main.py",), "main.py", gpu=True),
}


def ray_engine(engine_id: str) -> Optional[RayEngine]:
    return RAY_ENGINES.get(engine_id)


def install_recipe(engine_id: str) -> Optional[Dict[str, Any]]:
    """The JSON recipe the worker uses to build the engine venv, or None.

    None means the engine runs under the cluster's own Python (``_echo``).
    """
    if engine_id == "_echo":
        return None
    from core.torch_indexes import UV_PIP_CPU_ARGS, UV_PIP_CU128_ARGS  # noqa: PLC0415
    from services.sidecar_install import get_spec  # noqa: PLC0415

    spec = get_spec(engine_id)
    if spec.has_source:
        raise ValueError(f"{engine_id} installs from a source checkout; not supported on Ray yet")
    install = list(spec.install_args)
    if spec.torch_pins:
        cuda = [f"{pin}+cu128" for pin in spec.torch_pins] + list(UV_PIP_CU128_ARGS)
        cpu = [f"{pin}+cpu" for pin in spec.torch_pins] + list(UV_PIP_CPU_ARGS)
    elif spec.cpu_torch_index:
        cuda = cpu = list(UV_PIP_CPU_ARGS)
    elif spec.uses_cuda_index:
        cuda, cpu = list(UV_PIP_CU128_ARGS), []
    else:
        cuda = cpu = []
    recipe: Dict[str, Any] = {
        "venv_args": list(spec.venv_args),
        "install_args": install,
        "cuda_args": cuda,
        "cpu_args": cpu,
        "probe_code": spec.probe_code or f"import {spec.probe_module}",
        "install_revision": getattr(spec, "install_revision", None) or "",
    }
    # Content key: a changed pin installs into a fresh venv next to the old one.
    recipe["key"] = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:16]
    return recipe
