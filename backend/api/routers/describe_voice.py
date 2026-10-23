"""Voice-design "describe your voice" API (issue #317).

Maps a free-text voice description onto the existing design parameter space
via the deterministic keyword mapper in ``core.describe_voice``. Pure CPU +
stdlib for English, so it imports and responds instantly in any environment.

The mapper only knows English words. A description in another script (Thai,
at least) is first translated to English with the app's own translation path:
Typhoon Translate when it is routed to the remote GPU, else the translator
chosen in Settings → Models → Translation. With neither, today's mapping of
the original text is returned and the UI asks for an English description.
"""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.describe_voice import description_language, parse_description

logger = logging.getLogger("omnivoice.describe_voice")
router = APIRouter()

_TRANSLATIONS: "OrderedDict[tuple, str]" = OrderedDict()
_TRANSLATIONS_MAX = 64


class DescribeRequest(BaseModel):
    description: str = Field(default="", max_length=2000)
    # Translate a non-English description before mapping it.
    translate: bool = True


def _translators(language: str) -> list[str]:
    """Translation providers to try for ``language`` -> English, best first."""
    from core import prefs
    from services import translation_engines
    from services.subprocess_backend import ray_routed

    out = []
    if language == "th" and ray_routed("typhoon-translate"):
        out.append("typhoon")
    configured = str(prefs.get("translation_backend", "argos"))
    if configured not in out and (configured != "typhoon" or language == "th"):
        try:
            if translation_engines.is_ready(configured):
                out.append(configured)
        except Exception:  # noqa: BLE001 - an unusable translator is skipped
            logger.debug("translation engine probe failed", exc_info=True)
    return out


async def _translate(text: str, language: str, provider: str) -> str | None:
    """English text from the dub translation path, or None when it failed."""
    key = (provider, language, text)
    if key in _TRANSLATIONS:
        _TRANSLATIONS.move_to_end(key)
        return _TRANSLATIONS[key]
    from api.routers.dub_translate import dub_translate
    from schemas.requests import TranslateRequest, TranslateSegment

    req = TranslateRequest(segments=[TranslateSegment(id="description", text=text)], target_lang="en",
                           source_lang=language, provider=provider, quality="fast")
    try:
        result = await dub_translate(req)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - licence gate, engine errors: try the next one
        logger.info("description translation via %s failed", provider, exc_info=True)
        return None
    rows = result.get("translated") if isinstance(result, dict) else None  # a JSONResponse is an error
    row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
    english = (row.get("text") or "").strip()
    if row.get("error") or not english or description_language(english) is not None:
        return None  # untranslated or still not English
    _TRANSLATIONS[key] = english
    while len(_TRANSLATIONS) > _TRANSLATIONS_MAX:
        _TRANSLATIONS.popitem(last=False)
    return english


async def _unless_disconnected(request: Request, coro):
    """Run ``coro``; cancel it when the client goes away (the UI re-describes
    on every pause in typing, and a remote translation job is not free)."""
    task = asyncio.ensure_future(coro)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.5)
            if done:
                return task.result()
            if await request.is_disconnected():
                task.cancel()
                return None
    finally:
        if not task.done():
            task.cancel()


@router.post("/design/describe")
async def describe_voice(req: DescribeRequest, request: Request) -> dict:
    """Parse a free-text description into design attrs + a validator-safe instruct.

    Response shape::

        {
          "attrs":     {"Gender": "female", "Age": "elderly", ... or "Auto"},
          "instruct":  "female, elderly, low pitch, british accent",
          "matched":   [{"category": "Age", "token": "elderly", "phrase": "elderly"}, ...],
          "unmatched": ["warm", "slightly raspy"]
        }

    A non-English description adds ``language`` (e.g. "th"), ``translated``
    (the English text that was mapped, or null) and ``translator`` (the
    provider id, or null). ``translated`` null means no translator could
    translate it: the original text was mapped as before.
    """
    language = description_language(req.description)
    if language is None:
        return parse_description(req.description)
    english = translator = None
    if req.translate:
        for provider in _translators(language):
            english = await _unless_disconnected(request, _translate(req.description.strip(), language, provider))
            if english:
                translator = provider
                break
            if await request.is_disconnected():
                break
    result = parse_description(english or req.description)
    return {**result, "language": language, "translated": english, "translator": translator}
