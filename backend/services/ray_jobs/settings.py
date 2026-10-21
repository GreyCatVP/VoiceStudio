"""Ray execution settings: persisted in settings_store, overridable by env.

Off by default. When enabled, the engines listed in ``engines`` run as Ray
jobs on the configured cluster; everything else stays local. Secrets (the
Ray auth token, the Cloudflare Access client secret) are Fernet-encrypted by
settings_store and never returned to the UI — only ``has_*`` flags are.
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
SECRET_TOKEN = "ray_auth_token"
SECRET_CF = "ray_cf_access_client_secret"

ENV_URL = "OMNIVOICE_RAY_DASHBOARD_URL"
ENV_TOKEN = "OMNIVOICE_RAY_AUTH_TOKEN"

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

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.dashboard_url)

    def public(self) -> Dict[str, Any]:
        out = asdict(self)
        out["engines"] = list(self.engines)
        out["env_pinned"] = list(self.env_pinned)
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
    if changes.get("keep_failed_jobs") is not None:
        text[KEY_KEEP_FAILED] = "1" if changes["keep_failed_jobs"] else "0"
    if changes.get("cf_access_client_id") is not None:
        text[KEY_CF_ID] = changes["cf_access_client_id"].strip()
    for name, secret in (("auth_token", SECRET_TOKEN), ("cf_access_client_secret", SECRET_CF)):
        if changes.get(name) is not None:
            secrets[secret] = changes[name].strip()
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
