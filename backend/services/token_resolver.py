"""HF token resolver — AUTH-01, AUTH-03, AUTH-06.

Resolution priority (highest → lowest):

  1. openbao — the user's OpenBao KV v2 secret (`services.openbao`), only when
               the user turned that source on; read at use time, kept in
               memory only. Unreachable/sealed/denied falls through below.
  2. app     — `settings_store.get_hf_token()` (encrypted in SQLite)
  3. env     — `HF_TOKEN` or the legacy `HUGGING_FACE_HUB_TOKEN` env var
  4. hf-cli  — the selected local Hub token file (`HF_TOKEN_PATH`), read
               only: the app never writes it (a plaintext file)

For each candidate, the resolver calls whoami on huggingface.co itself
(`hf_auth.canonical_whoami`, never a configured mirror) to verify the token
is live; any HTTP error (401, 403, network) skips to
the next source. Results are cached per (source, token-sha256) for 300
seconds so repeat reads from the UI/dub_core don't hammer the HF API.

Replaces every bare `os.environ.get("HF_TOKEN")` call site in the backend
(per Pitfall #1 in 01-RESEARCH.md and the grep gate in 01-01-PLAN.md
Task 2 verification).
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import threading
import time
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger("omnivoice.token_resolver")

Source = Literal["openbao", "app", "env", "hf-cli"]
_PRIORITY: tuple[Source, ...] = ("openbao", "app", "env", "hf-cli")

_CACHE_TTL_SECONDS = 300.0  # UI "Test now" busts it via GET /hf-token/state?fresh=1.


@dataclass(frozen=True)
class ResolvedToken:
    token: str
    source: Source
    username: Optional[str]


@dataclass(frozen=True)
class SourceState:
    source: Source
    set: bool
    masked: Optional[str]
    whoami_user: Optional[str]
    whoami_ok: Optional[bool]
    error: Optional[str] = None  # openbao only: unreachable | sealed | denied | not_found | ...


# ── module-level cache ────────────────────────────────────────────────────

_VALIDATION_CACHE: dict[tuple[Source, str], tuple[float, Optional[str]]] = {}
_CACHE_LOCK = threading.Lock()


def invalidate_cache() -> None:
    """Drop the whoami validation cache. Called by the Settings UI "Test now"
    button (GET /api/settings/hf-token/state?fresh=1), by save/clear API
    endpoints, and by on_401()."""
    with _CACHE_LOCK:
        _VALIDATION_CACHE.clear()
    from services import openbao
    openbao.invalidate_cache()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── source readers ────────────────────────────────────────────────────────


def _read_app() -> Optional[str]:
    try:
        from services import settings_store
        return settings_store.get_hf_token()
    except Exception:
        logger.exception("settings_store read failed")
        return None


def _clean_token(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.replace("\r", "").replace("\n", "").strip() or None


def _read_env() -> Optional[str]:
    # HF docs explicitly accept either name; user may have either exported.
    val = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    return _clean_token(val)


def _read_hf_cli() -> Optional[str]:
    try:
        from huggingface_hub import constants
        return _clean_token(Path(constants.HF_TOKEN_PATH).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        logger.warning("Could not read the local Hugging Face token file")
        return None


def _openbao_enabled() -> bool:
    try:
        from services import openbao
        return openbao.load().enabled
    except Exception:
        logger.exception("OpenBao settings read failed")
        return False


def _read_openbao_state() -> tuple[Optional[str], Optional[str]]:
    """(token, error kind). Never raises: a broken secret store must not
    break generation — the next source is used instead."""
    from services import openbao
    try:
        return _clean_token(openbao.hf_token()), None
    except openbao.OpenBaoError as exc:
        logger.warning("OpenBao token source unavailable (%s): %s", exc.kind, exc)
        return None, exc.kind
    except Exception as exc:
        logger.warning("OpenBao token source failed (%s)", type(exc).__name__)
        return None, "error"


def _read_openbao() -> Optional[str]:
    return _read_openbao_state()[0]


def _sources() -> tuple[Source, ...]:
    """The cascade; OpenBao is part of it only once the user turned it on."""
    return _PRIORITY if _openbao_enabled() else tuple(s for s in _PRIORITY if s != "openbao")


_READERS: dict[Source, callable] = {  # type: ignore[type-arg]
    "openbao": _read_openbao,
    "app": _read_app,
    "env": _read_env,
    "hf-cli": _read_hf_cli,
}


# ── whoami validation ─────────────────────────────────────────────────────


def _validate(source: Source, token: str) -> Optional[str]:
    """Returns the validated whoami username, or None if the token is invalid.

    Caches results for `_CACHE_TTL_SECONDS` per (source, token-hash) so the
    Settings panel's repeated state() calls don't hit the HF API every load.
    """
    key = (source, _hash(token))
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _VALIDATION_CACHE.get(key)
    if cached is not None:
        ts, username = cached
        if now - ts < _CACHE_TTL_SECONDS:
            return username

    from services.hf_auth import canonical_whoami
    try:
        info = canonical_whoami(token)
        name = (info or {}).get("name") if isinstance(info, dict) else None
        with _CACHE_LOCK:
            _VALIDATION_CACHE[key] = (now, name)
        return name
    except Exception as exc:
        # Any failure — HfHubHTTPError 401/403, network — disqualifies this source.
        # Cache the negative result so we don't slam the API in tight loops;
        # the cache TTL is bounded so transient failures still recover.
        with _CACHE_LOCK:
            _VALIDATION_CACHE[key] = (now, None)
        logger.debug("whoami failed for source=%s: %s", source, exc)
        return None


def _mask(token: str) -> str:
    """`hf_…<last 3>` — what the Settings UI shows in the "currently set"
    field. We never reveal the full token in any read API."""
    if not token:
        return ""
    tail = token[-3:] if len(token) >= 3 else token
    return f"hf_…{tail}"


# ── public API ────────────────────────────────────────────────────────────


def resolve(skip: frozenset[Source] = frozenset()) -> Optional[ResolvedToken]:
    """Return the highest-priority valid token, or None if all sources are
    empty/invalid. `skip` excludes specific sources — used by `on_401()`
    when a previously-resolved token started returning 401 mid-job."""
    for source in _sources():
        if source in skip:
            continue
        token = _READERS[source]()
        if not token:
            continue
        username = _validate(source, token)
        if username is None and not _all_validation_skipped():
            # Token present but whoami failed — log once at debug and try
            # the next source. We do NOT log the token (the redactor would
            # mask it anyway, but no need to even emit it).
            continue
        return ResolvedToken(token=token, source=source, username=username)
    return None


def _all_validation_skipped() -> bool:
    """Hook left here as a no-op for now. Originally intended to allow
    network-disabled environments to bypass whoami; left in for future
    extension and explicit so reviewers see the choice."""
    return False


def on_401(active_source: Source) -> Optional[ResolvedToken]:
    """AUTH-06: when the active source started returning 401 mid-job (e.g.
    the user rotated the token externally), invalidate the cache and try
    resolving again while skipping the offending source."""
    invalidate_cache()
    return resolve(skip=frozenset({active_source}))


def state(*, validate: bool = False) -> dict:
    """Return one SourceState per priority position so the Settings UI can
    render the cascade table. Includes a masked token + whoami result;
    never includes the raw token. Reads are local unless validation is explicitly
    requested — except the OpenBao row, which (only when the user turned it on)
    reads the user's configured OpenBao address, cached in memory."""
    rows: list[SourceState] = []
    active: Optional[Source] = None
    for source in _sources():
        error = None
        if source == "openbao":
            token, error = _read_openbao_state()
        else:
            token = _READERS[source]()
        if token:
            username = _validate(source, token) if validate else None
            ok = (username is not None) if validate else None
            rows.append(SourceState(
                source=source,
                set=True,
                masked=_mask(token),
                whoami_user=username,
                whoami_ok=ok,
            ))
            if active is None and ok:
                active = source
        else:
            rows.append(SourceState(
                source=source,
                set=False,
                masked=None,
                whoami_user=None,
                whoami_ok=False,
                error=error,
            ))
    return {"sources": rows, "active": active}


def save_app_token(token: str) -> None:
    """Persist token to the encrypted settings store only.

    The plaintext Hub CLI token file (``HF_TOKEN_PATH``) is never written:
    every backend Hub call passes the resolved token explicitly, and the
    file stays the user's own ``hf auth login`` (read as the hf-cli source).
    """
    if not token:
        clear_app_token()
        return
    from services import settings_store
    settings_store.set_hf_token(token)
    invalidate_cache()


def clear_hf_cli_tokens() -> None:
    """Remove recognized Hub token files without refreshing or revoking tokens."""
    from core.config import HF_CLI_TOKEN_PATHS
    from huggingface_hub import constants

    # Hub's active path remains authoritative if imported before app config.
    paths = set(HF_CLI_TOKEN_PATHS) | {constants.HF_TOKEN_PATH}
    failed = False
    for token_path in paths:
        path = Path(token_path)
        for target in (path, path.parent / "stored_tokens"):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                failed = True
    invalidate_cache()
    if failed:
        raise OSError("Could not clear all local Hugging Face token files")


def clear_app_token(also_clear_hf_cli: bool = False) -> None:
    """Clear the encrypted app token, optionally recognized local Hub files."""
    from services import settings_store
    settings_store.clear_hf_token()
    if also_clear_hf_cli:
        clear_hf_cli_tokens()
    invalidate_cache()
