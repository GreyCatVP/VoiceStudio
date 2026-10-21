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
    kind: str = "tts"  # "tts" | "asr"
    # (arcname, path under backend/) shipped at the package root: stdlib-only
    # backend modules a sidecar imports.
    extra_files: Tuple[Tuple[str, str], ...] = ()
    # Install recipe for engines without a SidecarSpec (same shape as one
    # derived by install_recipe, minus "key").
    recipe: Optional[Dict[str, Any]] = None


# The isolated faster-whisper sidecar imports these (cudnn8/device_caps are
# optional, execstack is not); all stdlib-only.
_ASR_CORE_FILES = tuple((f"core/{n}", f"core/{n}") for n in
                        ("__init__.py", "execstack.py", "cudnn8.py", "device_caps.py", "gpu_inventory.py"))
# The desktop stack's versions (uv.lock). ctranslate2 4.4 needs cuDNN 8, which
# core/cudnn8.py finds under <site-packages>/cudnn8_compat; torch lets
# core.device_caps see the GPU (without it the sidecar falls back to CPU).
_FASTER_WHISPER_RECIPE: Dict[str, Any] = {
    "venv_args": ["--python", "3.11"],
    "install_args": ["faster-whisper==1.2.1", "ctranslate2==4.4.0"],
    "torch_pins": ["torch==2.11.0"],
    "target_installs": [{"site_rel": "cudnn8_compat", "args": ["nvidia-cudnn-cu12==8.9.7.29"], "variants": ["cuda"]}],
    # Repair CTranslate2's executable-stack flag first (newer kernels refuse
    # it), exactly as the sidecar does before importing.
    "probe_code": ("import sys; sys.path.insert(0, {workdir_repr}); "
                   "from core.execstack import ensure_ctranslate2_loadable; "
                   "ok, why = ensure_ctranslate2_loadable(); assert ok, why; "
                   "import faster_whisper, ctranslate2"),
    "install_revision": "ray-asr-v1",
}


RAY_ENGINES: Dict[str, RayEngine] = {
    # Test engine: stdlib-only, runs under the cluster's own Python.
    "_echo": RayEngine("_echo", "_echo", ("main.py",), "main.py", gpu=False),
    # CPU (onnxruntime); pins its weights revision through constants.py.
    "supertonic3": RayEngine("supertonic3", "supertonic3", ("sidecar.py", "constants.py"), "sidecar.py", gpu=False),
    "voxcpm2": RayEngine("voxcpm2", "voxcpm2_subprocess", ("main.py",), "main.py", gpu=True),
    # Source-checkout engines: the cluster fetches the pinned source (and, for
    # indextts2/cosyvoice, the pinned weights) into its cache.
    "moss-tts-nano": RayEngine("moss-tts-nano", "moss_tts_nano_subprocess", ("main.py",), "main.py", gpu=True),
    "indextts2": RayEngine("indextts2", "indextts", ("main.py",), "main.py", gpu=True),
    "cosyvoice": RayEngine("cosyvoice", "cosyvoice_subprocess", ("main.py",), "main.py", gpu=True),
    "confucius4-tts": RayEngine("confucius4-tts", "confucius4", ("main.py",), "main.py", gpu=True),
    "moss-tts-v15": RayEngine("moss-tts-v15", "moss_tts_v15", ("main.py",), "main.py", gpu=True),
    "dots-tts": RayEngine("dots-tts", "dots_tts", ("main.py",), "main.py", gpu=True),
    # ASR used by dubbing: the crash-isolated faster-whisper sidecar.
    "faster-whisper-isolated": RayEngine(
        "faster-whisper-isolated", "_asr_sidecar", ("main.py",), "main.py", gpu=True, kind="asr",
        extra_files=_ASR_CORE_FILES, recipe=_FASTER_WHISPER_RECIPE),
}

# Only GitHub archives are fetched by the cluster installer.
_SOURCE_HOSTS = ("https://github.com/", "https://codeload.github.com/")
HF_HUB_PIN = "huggingface_hub==1.28.0"  # the app's locked version


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

    engine = RAY_ENGINES.get(engine_id)
    if engine is not None and engine.recipe is not None:
        recipe = {k: v for k, v in engine.recipe.items() if k != "torch_pins"}
        pins = engine.recipe.get("torch_pins") or []
        recipe["cuda_args"] = [f"{p}+cu128" for p in pins] + (list(UV_PIP_CU128_ARGS) if pins else [])
        recipe["cpu_args"] = [f"{p}+cpu" for p in pins] + (list(UV_PIP_CPU_ARGS) if pins else [])
        recipe["key"] = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:16]
        return recipe
    spec = get_spec(engine_id)
    if spec is None:
        raise ValueError(f"{engine_id} has no install recipe")
    files: Dict[str, str] = {}
    install = [_inline_local_file(arg, files) for arg in spec.install_args]
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
    if spec.has_source:
        recipe["source"] = _source(spec.tarball_url, spec.source_revision, spec.source_required_path or spec.source_manifest)
        recipe["source"]["dirname"] = spec.checkout_dirname
        recipe["extra_sources"] = [
            {"path": extra.path, **_source(extra.tarball_url, extra.revision, extra.required_path)}
            for extra in (getattr(spec, "extra_sources", None) or ())
        ]
        recipe["env_var"] = spec.env_var  # the worker points it at the node's checkout
    if engine_id == "dots-tts":
        from engines.dots_tts.install import COMPATIBLE_NAME, KNOWN_BROKEN_PINS  # noqa: PLC0415

        recipe["pin_rewrites"] = [{"file": "constraints/recommended.txt", "out": f"constraints/{COMPATIBLE_NAME}",
                                   "pins": [list(p) for p in KNOWN_BROKEN_PINS]}]
        recipe["install_args"] = [a.replace("constraints/recommended.txt", f"constraints/{COMPATIBLE_NAME}")
                                  for a in recipe["install_args"]]
    if spec.weights_repo_id:
        recipe["weights"] = {
            "repo_id": spec.weights_repo_id, "revision": spec.weights_revision, "subdir": spec.weights_subdir,
            "allow_patterns": list(spec.weights_allow_patterns or ()) or None,
            "config_names": list(spec.weights_config_names), "hf_hub": HF_HUB_PIN,
        }
    if files:
        recipe["files"] = files
    # Content key: a changed pin installs into a fresh venv next to the old one.
    recipe["key"] = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:16]
    return recipe


def _source(url: str, revision: Optional[str], required_path: Optional[str]) -> Dict[str, Any]:
    if not url or not url.startswith(_SOURCE_HOSTS):
        raise ValueError(f"source archive {url!r} is not a GitHub archive")
    return {"tarball_url": url, "revision": revision or "", "required_path": required_path or ""}


def _inline_local_file(arg: str, files: Dict[str, str]) -> str:
    """An install argument naming a file shipped with the app (cosyvoice's
    trimmed requirements) becomes ``{files}/<name>`` with its content inlined:
    the absolute local path means nothing on a cluster node."""
    from pathlib import Path  # noqa: PLC0415

    backend = Path(__file__).resolve().parents[2]
    if "{" in arg or not arg.startswith("/"):
        return arg
    path = Path(arg).resolve()
    if backend not in path.parents or not path.is_file():
        return arg
    name = f"{path.parent.name}-{path.name}"
    files[name] = path.read_text(encoding="utf-8")
    return "{files}/" + name
