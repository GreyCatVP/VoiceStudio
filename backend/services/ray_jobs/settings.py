"""Remote execution settings: persisted in settings_store, overridable by env.

Off by default. When enabled, the engines listed in ``engines`` run remotely
on the chosen ``provider`` — jobs on a Ray cluster, or sandboxes on Modal —
and everything else stays local. Secrets (the Ray auth token, the Cloudflare
Access client secret, the Modal token) are Fernet-encrypted by settings_store
and never returned to the UI — only ``has_*`` flags are.
"""
from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

from services.ray_jobs.engines import RAY_ENGINES

KEY_ENABLED = "ray.enabled"
KEY_URL = "ray.dashboard_url"
KEY_CF_ID = "ray.cf_access_client_id"
KEY_ENGINES = "ray.engines"
KEY_NUM_GPUS = "ray.num_gpus"
KEY_NUM_CPUS = "ray.num_cpus"
KEY_CACHE_DIR = "ray.cache_dir"
KEY_PYTHON = "ray.python"
KEY_KEEP_FAILED = "ray.keep_failed_jobs"
KEY_PROVIDER = "ray.provider"
KEY_MODAL_GPU = "modal.gpu"
KEY_MODAL_APP = "modal.app"
KEY_MODAL_VOLUME = "modal.volume"
SECRET_TOKEN = "ray_auth_token"
SECRET_CF = "ray_cf_access_client_secret"
SECRET_MODAL_ID = "modal_token_id"
SECRET_MODAL_SECRET = "modal_token_secret"

ENV_URL = "OMNIVOICE_RAY_DASHBOARD_URL"
ENV_TOKEN = "OMNIVOICE_RAY_AUTH_TOKEN"
ENV_MODAL_ID = "OMNIVOICE_MODAL_TOKEN_ID"
ENV_MODAL_SECRET = "OMNIVOICE_MODAL_TOKEN_SECRET"

PROVIDERS = ("ray", "modal")
# Modal GPU types (https://modal.com/docs/guide/gpu); "" runs GPU engines on CPU.
MODAL_GPUS = ("T4", "L4", "A10", "L40S", "A100-40GB", "A100-80GB", "H100", "H200", "B200")
DEFAULT_MODAL_GPU = "L4"
_SAFE_MODAL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

DEFAULT_NUM_GPUS = 0.1  # a share of one GPU for GPU engines (Ray bookkeeping); 0 = run on CPU
DEFAULT_NUM_CPUS = 2.0
_SAFE_PATH = re.compile(r"^/[A-Za-z0-9_./-]*$")
_SAFE_PYTHON = re.compile(r"^[A-Za-z0-9_./-]+$")
# Engines the UI offers (the test engine is not one of them).
SELECTABLE_ENGINES: Tuple[str, ...] = tuple(e for e in RAY_ENGINES if not e.startswith("_"))


@dataclass(frozen=True)
class RaySettings:
    enabled: bool = False
    dashboard_url: str = ""
    cf_access_client_id: str = ""
    engines: Tuple[str, ...] = ()
    num_gpus: float = DEFAULT_NUM_GPUS
    num_cpus: float = DEFAULT_NUM_CPUS
    cache_dir: str = ""
    python: str = "python"
    keep_failed_jobs: bool = True
    has_token: bool = False
    has_cf_secret: bool = False
    env_pinned: Tuple[str, ...] = field(default_factory=tuple)
    provider: str = "ray"
    modal_gpu: str = DEFAULT_MODAL_GPU
    modal_app: str = "voicestudio"
    modal_volume: str = "voicestudio-cache"
    has_modal_token: bool = False

    @property
    def active(self) -> bool:
        if self.provider == "modal":
            return self.enabled and self.has_modal_token
        return self.enabled and bool(self.dashboard_url)

    def gpu_request(self, gpu_engine: bool) -> Optional[float]:
        """GPUs to request for one job: Ray takes the configured share (0 = CPU);
        Modal one GPU of the chosen type, none when "CPU only" is chosen."""
        if not gpu_engine:
            return None
        if self.provider == "modal":
            return 1.0 if self.modal_gpu else None
        return self.num_gpus or None

    @property
    def target(self) -> str:
        """Where jobs run: keys per-target caches such as "engine installed"."""
        if self.provider == "modal":
            return f"modal:{self.modal_app}/{self.modal_volume}"
        return self.dashboard_url

    def public(self) -> Dict[str, Any]:
        out = asdict(self)
        out["engines"] = list(self.engines)
        out["env_pinned"] = list(self.env_pinned)
        out["modal_gpus"] = list(MODAL_GPUS)
        out["available_engines"] = [
            {"id": e, "gpu": RAY_ENGINES[e].gpu, "kind": RAY_ENGINES[e].kind} for e in SELECTABLE_ENGINES
        ]
        return out


def normalize_dashboard_url(value: str) -> str:
    """A credential-free dashboard URL; plain HTTP only on loopback."""
    base = (value or "").strip().rstrip("/")
    if not base:
        return ""
    try:
        parsed = urlsplit(base)
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid Ray dashboard URL") from exc
    scheme = parsed.scheme.lower()
    if (scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        raise ValueError("Ray dashboard URL must be a credential-free http(s)://host[:port]")
    host = parsed.hostname.lower()
    loopback = host == "localhost"
    if not loopback:
        try:
            address = ipaddress.ip_address(host)
            loopback = (getattr(address, "ipv4_mapped", None) or address).is_loopback
        except ValueError:
            loopback = False
    if scheme == "http" and not loopback:
        # The auth token travels on every request.
        raise ValueError("A remote Ray dashboard must use HTTPS")
    return base


def _float(text: Optional[str], default: float, lo: float, hi: float) -> float:
    try:
        value = float(text) if text not in (None, "") else default
    except ValueError:
        return default
    return min(max(value, lo), hi)


def load() -> RaySettings:
    from services import settings_store  # noqa: PLC0415

    pinned = []
    url = os.environ.get(ENV_URL)
    if url:
        pinned.append("dashboard_url")
    else:
        url = settings_store.get_text(KEY_URL) or ""
    try:
        url = normalize_dashboard_url(url)
    except ValueError:
        url = ""
    engines = tuple(e for e in (settings_store.get_text(KEY_ENGINES) or "").split(",")
                    if e in SELECTABLE_ENGINES)
    secrets = set(settings_store.list_secret_names())
    has_token = bool(os.environ.get(ENV_TOKEN)) or SECRET_TOKEN in secrets
    if os.environ.get(ENV_TOKEN):
        pinned.append("token")
    cache_dir = settings_store.get_text(KEY_CACHE_DIR) or ""
    python = settings_store.get_text(KEY_PYTHON) or "python"
    provider = settings_store.get_text(KEY_PROVIDER) or "ray"
    modal_gpu = settings_store.get_text(KEY_MODAL_GPU)
    modal_app = settings_store.get_text(KEY_MODAL_APP) or "voicestudio"
    modal_volume = settings_store.get_text(KEY_MODAL_VOLUME) or "voicestudio-cache"
    has_modal_token = (bool(os.environ.get(ENV_MODAL_ID) and os.environ.get(ENV_MODAL_SECRET))
                       or {SECRET_MODAL_ID, SECRET_MODAL_SECRET} <= secrets)
    if os.environ.get(ENV_MODAL_ID):
        pinned.append("modal_token")
    return RaySettings(
        enabled=settings_store.get_text(KEY_ENABLED) == "1",
        dashboard_url=url,
        cf_access_client_id=settings_store.get_text(KEY_CF_ID) or "",
        engines=engines,
        num_gpus=_float(settings_store.get_text(KEY_NUM_GPUS), DEFAULT_NUM_GPUS, 0.0, 8.0),
        num_cpus=_float(settings_store.get_text(KEY_NUM_CPUS), DEFAULT_NUM_CPUS, 0.1, 64.0),
        cache_dir=cache_dir if _SAFE_PATH.match(cache_dir) else "",
        python=python if _SAFE_PYTHON.match(python) else "python",
        keep_failed_jobs=settings_store.get_text(KEY_KEEP_FAILED) != "0",
        has_token=has_token,
        has_cf_secret=SECRET_CF in secrets,
        env_pinned=tuple(pinned),
        provider=provider if provider in PROVIDERS else "ray",
        modal_gpu=(DEFAULT_MODAL_GPU if modal_gpu is None
                   else modal_gpu if modal_gpu in MODAL_GPUS or modal_gpu == "" else DEFAULT_MODAL_GPU),
        modal_app=modal_app if _SAFE_MODAL_NAME.match(modal_app) else "voicestudio",
        modal_volume=modal_volume if _SAFE_MODAL_NAME.match(modal_volume) else "voicestudio-cache",
        has_modal_token=has_modal_token,
    )


def save(changes: Dict[str, Any]) -> RaySettings:
    """Validate and persist the given fields (None = unchanged); return the new state.

    Raises ValueError with a user-facing message on invalid input; nothing is
    written unless every field validates.
    """
    from services import settings_store  # noqa: PLC0415

    text: Dict[str, str] = {}
    secrets: Dict[str, str] = {}
    if changes.get("dashboard_url") is not None:
        text[KEY_URL] = normalize_dashboard_url(changes["dashboard_url"])
    if changes.get("enabled") is not None:
        text[KEY_ENABLED] = "1" if changes["enabled"] else "0"
    if changes.get("engines") is not None:
        unknown = sorted(set(changes["engines"]) - set(SELECTABLE_ENGINES))
        if unknown:
            raise ValueError(f"Engines not available on Ray: {', '.join(unknown)}")
        text[KEY_ENGINES] = ",".join(e for e in SELECTABLE_ENGINES if e in set(changes["engines"]))
    for key, name, lo, hi in ((KEY_NUM_GPUS, "num_gpus", 0.0, 8.0), (KEY_NUM_CPUS, "num_cpus", 0.1, 64.0)):
        if changes.get(name) is not None:
            value = float(changes[name])
            if not lo <= value <= hi:
                raise ValueError(f"{name} must be between {lo} and {hi}")
            text[key] = repr(value)
    if changes.get("cache_dir") is not None:
        cache_dir = changes["cache_dir"].strip()
        if cache_dir and not _SAFE_PATH.match(cache_dir):
            raise ValueError("Cluster cache directory must be an absolute path")
        text[KEY_CACHE_DIR] = cache_dir
    if changes.get("python") is not None:
        python = changes["python"].strip() or "python"
        if not _SAFE_PYTHON.match(python):
            raise ValueError("Cluster Python must be a command name or path")
        text[KEY_PYTHON] = python
    if changes.get("provider") is not None:
        if changes["provider"] not in PROVIDERS:
            raise ValueError(f"Unknown provider: {changes['provider']}")
        text[KEY_PROVIDER] = changes["provider"]
    if changes.get("modal_gpu") is not None:
        if changes["modal_gpu"] not in MODAL_GPUS and changes["modal_gpu"] != "":
            raise ValueError(f"Unknown Modal GPU type: {changes['modal_gpu']}")
        text[KEY_MODAL_GPU] = changes["modal_gpu"]
    for name, key in (("modal_app", KEY_MODAL_APP), ("modal_volume", KEY_MODAL_VOLUME)):
        if changes.get(name) is not None:
            value = changes[name].strip()
            if not _SAFE_MODAL_NAME.match(value):
                raise ValueError(f"{name} must be 1-64 letters, digits, '.', '_' or '-'")
            text[key] = value
    if changes.get("keep_failed_jobs") is not None:
        text[KEY_KEEP_FAILED] = "1" if changes["keep_failed_jobs"] else "0"
    if changes.get("cf_access_client_id") is not None:
        text[KEY_CF_ID] = changes["cf_access_client_id"].strip()
    for name, secret in (("auth_token", SECRET_TOKEN), ("cf_access_client_secret", SECRET_CF),
                         ("modal_token_id", SECRET_MODAL_ID), ("modal_token_secret", SECRET_MODAL_SECRET)):
        if changes.get(name) is not None:
            secrets[secret] = changes[name].strip()
    for secret in (SECRET_MODAL_ID, SECRET_MODAL_SECRET):
        if secrets.get(secret) and not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secrets[secret]):
            raise ValueError("A Modal token id/secret looks like ak-... / as-... (from `modal token new`)")
    # Validate secrets as header values before writing anything.
    from services.ray_jobs.client import RayAuth  # noqa: PLC0415

    RayAuth(ray_token=secrets.get(SECRET_TOKEN) or None,
            cf_access_client_secret=secrets.get(SECRET_CF) or None,
            cf_access_client_id=text.get(KEY_CF_ID) or None)
    for key, value in text.items():
        settings_store.set_text(key, value)
    for name, value in secrets.items():
        settings_store.set_secret(name, value)  # '' clears
    return load()


def auth() -> "Any":
    from services import settings_store  # noqa: PLC0415
    from services.ray_jobs.client import RayAuth  # noqa: PLC0415

    return RayAuth(
        ray_token=os.environ.get(ENV_TOKEN) or settings_store.get_secret(SECRET_TOKEN),
        cf_access_client_id=settings_store.get_text(KEY_CF_ID) or None,
        cf_access_client_secret=settings_store.get_secret(SECRET_CF),
    )


def modal_credentials() -> Tuple[str, str]:
    """(token id, token secret) for Modal; env wins over the stored pair."""
    from services import settings_store  # noqa: PLC0415

    if os.environ.get(ENV_MODAL_ID) and os.environ.get(ENV_MODAL_SECRET):
        return os.environ[ENV_MODAL_ID], os.environ[ENV_MODAL_SECRET]
    return (settings_store.get_secret(SECRET_MODAL_ID) or "", settings_store.get_secret(SECRET_MODAL_SECRET) or "")


def route_for(engine_id: str) -> Optional[RaySettings]:
    """The settings to run ``engine_id`` on Ray with, or None to run it locally."""
    if engine_id not in RAY_ENGINES:
        return None
    try:
        cfg = load()
    except Exception:  # settings unreadable: never break local generation
        return None
    if not cfg.active or engine_id not in cfg.engines:
        return None
    return cfg
