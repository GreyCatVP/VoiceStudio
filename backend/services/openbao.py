"""OpenBao (Vault-compatible, KV v2) as an opt-in source for the Hugging Face token.

Off by default. When the user turns it on in Settings → Credentials, the token
resolver reads the HF token from ``{addr}/v1/{mount}/data/{path}`` (field
``field``) at use time and keeps it in memory only, for ``_CACHE_TTL`` seconds.
Nothing is sent anywhere unless the source is on, and requests go only to the
configured address. The OpenBao access token is Fernet-encrypted by
settings_store and never returned to the UI — only ``has_token`` is.
Unsealing is the server's job; a sealed server is reported as ``sealed``.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

import httpx

KEY_ENABLED = "openbao.enabled"
KEY_ADDR = "openbao.addr"
KEY_MOUNT = "openbao.mount"
KEY_PATH = "openbao.path"
KEY_FIELD = "openbao.field"
SECRET_TOKEN = "openbao_token"
ENV_ADDR = "OMNIVOICE_OPENBAO_ADDR"
ENV_TOKEN = "OMNIVOICE_OPENBAO_TOKEN"

DEFAULT_ADDR = "http://127.0.0.1:8200"
DEFAULT_MOUNT = "secret"
DEFAULT_FIELD = "token"
TIMEOUT_S = 5.0
_CACHE_TTL = 300.0
_FAIL_TTL = 30.0  # an unreachable server is not retried on every model load
_SEGMENT = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_SECRET_PATH = re.compile(r"^[A-Za-z0-9._-]{1,128}(/[A-Za-z0-9._-]{1,128}){0,15}$")


class OpenBaoError(Exception):
    """``kind`` is one of: not_configured, unreachable, sealed, denied, not_found, error."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class OpenBaoSettings:
    enabled: bool = False
    addr: str = DEFAULT_ADDR
    mount: str = DEFAULT_MOUNT
    path: str = ""
    field: str = DEFAULT_FIELD
    has_token: bool = False
    env_pinned: Tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.addr and self.path and self.has_token)

    def public(self) -> Dict[str, Any]:
        out = asdict(self)
        out["env_pinned"] = list(self.env_pinned)
        return out


def normalize_addr(value: str) -> str:
    """A credential-free http(s)://host[:port]; plain HTTP only on loopback."""
    from services.ray_jobs.settings import normalize_dashboard_url  # noqa: PLC0415

    try:
        return normalize_dashboard_url(value)
    except ValueError:
        raise ValueError("OpenBao address must be a credential-free http(s)://host[:port], "
                         "and HTTPS unless it is on this computer") from None


def _valid(value: str, pattern: re.Pattern, what: str) -> str:
    value = (value or "").strip().strip("/")
    if not pattern.match(value) or ".." in value.split("/"):
        raise ValueError(f"OpenBao {what} may only use letters, digits, '.', '_', '-' (and '/' in the path)")
    return value


def load() -> OpenBaoSettings:
    from services import settings_store  # noqa: PLC0415

    pinned = []
    addr = os.environ.get(ENV_ADDR)
    if addr:
        pinned.append("addr")
    else:
        addr = settings_store.get_text(KEY_ADDR) or DEFAULT_ADDR
    try:
        addr = normalize_addr(addr)
    except ValueError:
        addr = ""
    if os.environ.get(ENV_TOKEN):
        pinned.append("token")
    has_token = bool(os.environ.get(ENV_TOKEN)) or SECRET_TOKEN in settings_store.list_secret_names()
    return OpenBaoSettings(
        enabled=settings_store.get_text(KEY_ENABLED) == "1",
        addr=addr,
        mount=settings_store.get_text(KEY_MOUNT) or DEFAULT_MOUNT,
        path=settings_store.get_text(KEY_PATH) or "",
        field=settings_store.get_text(KEY_FIELD) or DEFAULT_FIELD,
        has_token=has_token,
        env_pinned=tuple(pinned),
    )


def save(changes: Dict[str, Any]) -> OpenBaoSettings:
    """Validate and persist the given fields (None = unchanged). Nothing is
    written unless every field validates; raises ValueError otherwise."""
    from services import settings_store  # noqa: PLC0415

    text: Dict[str, str] = {}
    if changes.get("enabled") is not None:
        text[KEY_ENABLED] = "1" if changes["enabled"] else "0"
    if changes.get("addr") is not None:
        text[KEY_ADDR] = normalize_addr(changes["addr"]) or DEFAULT_ADDR
    if changes.get("mount") is not None:
        text[KEY_MOUNT] = _valid(changes["mount"], _SEGMENT, "mount")
    if changes.get("path") is not None:
        text[KEY_PATH] = _valid(changes["path"], _SECRET_PATH, "secret path") if changes["path"].strip() else ""
    if changes.get("field") is not None:
        text[KEY_FIELD] = _valid(changes["field"], _SEGMENT, "field")
    token = changes.get("token")
    if token is not None:
        token = token.strip()
        if token and not re.fullmatch(r"[\x21-\x7e]{1,4096}", token):
            raise ValueError("The OpenBao token must be printable ASCII")
    for key, value in text.items():
        settings_store.set_text(key, value)
    if token is not None:
        settings_store.set_secret(SECRET_TOKEN, token)  # '' clears
    invalidate_cache()
    return load()


def _access_token() -> Optional[str]:
    from services import settings_store  # noqa: PLC0415

    return os.environ.get(ENV_TOKEN) or settings_store.get_secret(SECRET_TOKEN)


def _request(cfg: OpenBaoSettings, token: str, method: str, api_path: str,
             transport: Optional[httpx.BaseTransport]) -> Dict[str, Any]:
    url = f"{cfg.addr}/v1/{api_path}"
    try:
        with httpx.Client(timeout=TIMEOUT_S, transport=transport, follow_redirects=False) as client:
            r = client.request(method, url, headers={"X-Vault-Token": token})
    except httpx.HTTPError:
        raise OpenBaoError("unreachable", f"Could not reach OpenBao at {cfg.addr}") from None
    errors = " ".join(str(e) for e in (_json(r).get("errors") or []))
    if r.status_code == 503 or "sealed" in errors.lower():
        raise OpenBaoError("sealed", "OpenBao is sealed; it must be unsealed (ideally auto-unseal) on the server")
    if r.status_code in (401, 403):
        raise OpenBaoError("denied", "OpenBao denied access: the token is invalid, expired, "
                                     "or its policy cannot read this path")
    if r.status_code == 404:
        raise OpenBaoError("not_found", "No secret at that mount and path")
    if r.status_code != 200:
        raise OpenBaoError("error", f"OpenBao answered HTTP {r.status_code}")
    return _json(r)


def _json(r: httpx.Response) -> Dict[str, Any]:
    try:
        body = r.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _secret_path(cfg: OpenBaoSettings) -> str:
    return f"{quote(cfg.mount, safe='')}/data/{quote(cfg.path, safe='/')}"


def _fetch(cfg: OpenBaoSettings, token: str, transport: Optional[httpx.BaseTransport]) -> str:
    data = (_request(cfg, token, "GET", _secret_path(cfg), transport).get("data") or {}).get("data") or {}
    value = data.get(cfg.field) if isinstance(data, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise OpenBaoError("not_found", f"The secret has no '{cfg.field}' field")
    return value.strip()


# ── in-memory cache: (config + token hash) → (time, token or error) ──────────

_CACHE: Dict[str, Tuple[float, Any]] = {}
_LOCK = threading.Lock()


def invalidate_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def hf_token(transport: Optional[httpx.BaseTransport] = None) -> Optional[str]:
    """The HF token from OpenBao, or None when the source is off.

    Raises OpenBaoError when it is on but the secret cannot be read. Never
    persists the value; successes are cached in memory for five minutes.
    """
    cfg = load()
    if not cfg.active:
        return None
    token = _access_token()
    if not token:
        raise OpenBaoError("not_configured", "Set an OpenBao token first")
    key = hashlib.sha256("\0".join((cfg.addr, cfg.mount, cfg.path, cfg.field, token)).encode()).hexdigest()
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        ts, value = cached
        if now - ts < (_FAIL_TTL if isinstance(value, OpenBaoError) else _CACHE_TTL):
            if isinstance(value, OpenBaoError):
                raise value
            return value
    try:
        value = _fetch(cfg, token, transport)
    except OpenBaoError as exc:
        with _LOCK:
            _CACHE[key] = (now, exc)
        raise
    with _LOCK:
        _CACHE[key] = (now, value)
    return value


def test_connection(transport: Optional[httpx.BaseTransport] = None) -> Dict[str, Any]:
    """Read the saved secret once, uncached. Never returns the value — only a
    masked tail. Always returns a result dict (never raises)."""
    from services.token_resolver import _mask  # noqa: PLC0415

    cfg = load()
    token = _access_token()
    if not cfg.addr or not cfg.path or not token:
        return {"ok": False, "kind": "not_configured",
                "message": "Set the OpenBao address, secret path and token first"}
    out: Dict[str, Any] = {"ok": False}
    try:
        try:
            info = _request(cfg, token, "GET", "auth/token/lookup-self", transport).get("data") or {}
            # Lets the page warn about a token that will expire (0 = never).
            out["ttl"] = info.get("ttl")
            out["renewable"] = bool(info.get("renewable"))
        except OpenBaoError as exc:
            if exc.kind != "denied":  # a token without the default policy may not look itself up
                raise
        out["masked"] = _mask(_fetch(cfg, token, transport))
        out.update(ok=True, kind="ok")
    except OpenBaoError as exc:
        out.update(kind=exc.kind, message=str(exc))
    except Exception as exc:  # never let a test crash the settings page
        out.update(kind="error", message=type(exc).__name__)
    invalidate_cache()
    return out
