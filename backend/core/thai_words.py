"""Whole Thai words from faster-whisper's sub-word word timestamps.

Thai has no spaces between words, so faster-whisper's "words" for Thai are
BPE pieces ("ข", "อง", "ก", "าร"), which breaks subtitles and dub alignment.
:func:`merge_thai_words` regroups them on PyThaiNLP (newmm) word boundaries.

Stdlib-only at import (the isolated ASR sidecar runs with a clean import
path); pythainlp imports lazily and its absence leaves the words unchanged.
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

Tokenize = Callable[[str], List[str]]


def _newmm(text: str) -> List[str]:
    from pythainlp.tokenize import word_tokenize  # noqa: PLC0415

    return word_tokenize(text, engine="newmm", keep_whitespace=True)


def merge_thai_words(words: list, tokenize: Optional[Tokenize] = None) -> list:
    """Regroup sub-word pieces (dicts with word/start/end[/probability]) into words.

    A word starts at the piece holding its first character and ends at the
    piece holding its last; a piece split across two words is shared. The
    probability is the lowest of the pieces. Whitespace is dropped, except a
    leading space, which marks a word that follows a gap. Returns ``words``
    unchanged when they cannot be merged (no tokenizer, odd input).
    """
    if not words:
        return words
    try:
        text = "".join(str(w["word"]) for w in words)
        tokens = (tokenize or _newmm)(text)
    except Exception as exc:  # noqa: BLE001 - worse word grouping beats no transcript
        logger.info("Thai word merge skipped: %s", exc)
        return words
    if "".join(tokens) != text:
        return words
    owner = []  # character offset -> index of the piece it came from
    for i, w in enumerate(words):
        owner.extend([i] * len(str(w["word"])))
    merged, pos, gap = [], 0, False
    for token in tokens:
        start, pos = pos, pos + len(token)
        if not token.strip():
            gap = True
            continue
        pieces = words[owner[start]:owner[pos - 1] + 1]
        word = {"word": (" " if gap else "") + token,
                "start": pieces[0]["start"], "end": max(p["end"] for p in pieces)}
        probs = [p["probability"] for p in pieces if isinstance(p.get("probability"), (int, float))]
        if probs:
            word["probability"] = min(probs)
        if merged and word["start"] < merged[-1]["end"]:  # a shared piece: keep times monotonic
            word["start"] = min(merged[-1]["end"], word["end"])
        merged.append(word)
        gap = False
    return merged


def merge_segment_words(segments: list, language: Optional[str]) -> list:
    """Apply :func:`merge_thai_words` to each segment's words when the language is Thai."""
    if (language or "").lower() not in ("th", "thai"):
        return segments
    for seg in segments:
        if isinstance(seg, dict) and seg.get("words"):
            seg["words"] = merge_thai_words(seg["words"])
    return segments
