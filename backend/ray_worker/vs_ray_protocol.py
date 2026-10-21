"""Log-line protocol between a Ray job worker and the VoiceStudio backend.

The backend talks to a remote Ray head only through the dashboard's HTTPS
Jobs API, so the job's driver log is the one channel back. The worker prints
marker lines on stdout; the backend fetches ``/api/jobs/<id>/logs`` and parses
them. Everything else in the log (engine chatter, tracebacks) is ignored.

    @@VSRAY1 PROGRESS {"stage": "...", "fraction": 0.5, "message": "..."}
    @@VSRAY1 ERROR {"stage": "...", "message": "..."}
    @@VSRAY1 RESULT_BEGIN {"sha256": "...", "size": N, "chunks": K}
    @@VSRAY1 R <index> <base64 of zlib(JSON result) slice>
    @@VSRAY1 RESULT_END <sha256>

Binary payloads (audio) travel inside the JSON result as base64 strings; the
whole result is zlib-compressed before it is split into lines.

Stdlib-only on purpose: this file is shipped verbatim inside the job package
and imported by the backend, so it must run under any Python >= 3.9.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import zlib
from dataclasses import dataclass, field
from typing import Any, Dict, IO, List, Optional

MARK = "@@VSRAY1"
CHUNK_CHARS = 64 * 1024
# Compressed result bytes; the base64 text in the log is ~4/3 of this.
MAX_RESULT_BYTES = 50 * 1024 * 1024
# Decompressed JSON; base64 audio barely compresses, so 4x is generous.
MAX_INFLATED_BYTES = 4 * MAX_RESULT_BYTES


class ProtocolError(ValueError):
    """The job log carried a malformed or incomplete result."""


def _line(stream: IO[str], kind: str, body: str) -> None:
    stream.write(f"{MARK} {kind} {body}\n")
    stream.flush()


def emit_progress(stream: IO[str], stage: str, fraction: Optional[float] = None, message: str = "") -> None:
    payload: Dict[str, Any] = {"stage": stage, "message": message}
    if fraction is not None:
        payload["fraction"] = max(0.0, min(1.0, float(fraction)))
    _line(stream, "PROGRESS", json.dumps(payload, separators=(",", ":")))


def emit_error(stream: IO[str], stage: str, message: str) -> None:
    _line(stream, "ERROR", json.dumps({"stage": stage, "message": message}, separators=(",", ":")))


def encode_result(result: Dict[str, Any], max_bytes: int = MAX_RESULT_BYTES) -> List[str]:
    """Return the marker lines (without newlines) that carry ``result``."""
    packed = zlib.compress(json.dumps(result, separators=(",", ":")).encode("utf-8"), 6)
    if len(packed) > max_bytes:
        raise ProtocolError(f"result is {len(packed)} bytes compressed; limit is {max_bytes}")
    digest = hashlib.sha256(packed).hexdigest()
    text = base64.b64encode(packed).decode("ascii")
    chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)] or [""]
    head = json.dumps({"sha256": digest, "size": len(packed), "chunks": len(chunks)}, separators=(",", ":"))
    lines = [f"{MARK} RESULT_BEGIN {head}"]
    lines += [f"{MARK} R {i} {c}" for i, c in enumerate(chunks)]
    lines.append(f"{MARK} RESULT_END {digest}")
    return lines


def emit_result(stream: IO[str], result: Dict[str, Any], max_bytes: int = MAX_RESULT_BYTES) -> None:
    for line in encode_result(result, max_bytes):
        stream.write(line + "\n")
    stream.flush()


def b64_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64_bytes(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


@dataclass
class ParsedLog:
    progress: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None


MAX_EVENTS = 1000
MAX_EVENT_CHARS = 4096
_HEX64 = frozenset("0123456789abcdef")


def _event(body: str) -> Optional[Dict[str, Any]]:
    """A PROGRESS/ERROR body as a flat dict of scalars, or None if malformed."""
    if len(body) > MAX_EVENT_CHARS:
        return None
    try:
        obj = json.loads(body)
    except (ValueError, RecursionError):
        return None
    if not isinstance(obj, dict):
        return None
    return {str(k): v for k, v in obj.items() if isinstance(v, (str, int, float, bool)) or v is None}


def _marker_lines(text: str):
    for raw in text.splitlines():
        # Ray may prefix driver lines (e.g. with a timestamp); find the marker.
        at = raw.find(MARK + " ")
        if at >= 0:
            kind, _, body = raw[at + len(MARK) + 1:].partition(" ")
            yield kind, body


def parse_events(text: str) -> ParsedLog:
    """Progress and error events only; cheap enough to run while a job is live."""
    out = ParsedLog()
    for kind, body in _marker_lines(text):
        if kind == "PROGRESS" and len(out.progress) < MAX_EVENTS:
            event = _event(body)
            if event is not None:
                out.progress.append(event)
        elif kind == "ERROR" and len(out.errors) < MAX_EVENTS:
            event = _event(body)
            out.errors.append(event if event is not None else {"stage": "unknown", "message": body[:MAX_EVENT_CHARS]})
    return out


def parse_log(text: str, max_bytes: int = MAX_RESULT_BYTES) -> ParsedLog:
    """Extract progress, errors and the (verified) result from a finished job log.

    The log is untrusted: every malformed input raises ProtocolError.
    """
    out = parse_events(text)
    max_chunks = (max_bytes * 4 // 3) // CHUNK_CHARS + 2
    head: Optional[Dict[str, Any]] = None
    chunks: Dict[int, str] = {}
    try:
        for kind, body in _marker_lines(text):
            if kind == "RESULT_BEGIN":
                head = _check_head(body, max_bytes, max_chunks)
                chunks = {}
            elif kind == "R" and head is not None:
                idx_text, _, data = body.partition(" ")
                idx = int(idx_text)
                if not 0 <= idx < head["chunks"] or len(data) > CHUNK_CHARS:
                    raise ProtocolError(f"result chunk {idx} is out of range")
                chunks[idx] = data
            elif kind == "RESULT_END" and head is not None:
                out.result = _assemble(head, chunks, body.strip())
                head = None
    except ProtocolError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, binascii.Error) as exc:
        raise ProtocolError(f"malformed result: {type(exc).__name__}") from exc
    if head is not None:
        raise ProtocolError("result started but RESULT_END is missing (log truncated?)")
    return out


def _check_head(body: str, max_bytes: int, max_chunks: int) -> Dict[str, Any]:
    head = json.loads(body)
    if not isinstance(head, dict):
        raise ProtocolError("result header is not an object")
    size, n, digest = head.get("size"), head.get("chunks"), head.get("sha256")
    if not isinstance(size, int) or not 0 <= size <= max_bytes:
        raise ProtocolError(f"result size {size!r} exceeds limit {max_bytes}")
    if not isinstance(n, int) or not 1 <= n <= max_chunks:
        raise ProtocolError(f"result chunk count {n!r} is out of range")
    if not isinstance(digest, str) or len(digest) != 64 or not set(digest) <= _HEX64:
        raise ProtocolError("result header has no valid sha256")
    return {"size": size, "chunks": n, "sha256": digest}


def _assemble(head: Dict[str, Any], chunks: Dict[int, str], end_digest: str) -> Dict[str, Any]:
    n = head["chunks"]
    if len(chunks) != n:
        raise ProtocolError(f"result is missing chunks ({len(chunks)} of {n})")
    packed = base64.b64decode("".join(chunks[i] for i in range(n)).encode("ascii"), validate=True)
    digest = hashlib.sha256(packed).hexdigest()
    if digest != head["sha256"] or digest != end_digest:
        raise ProtocolError("result checksum mismatch")
    if len(packed) != head["size"]:
        raise ProtocolError("result size mismatch")
    # Bound the inflated size so a hostile cluster cannot send a zip bomb.
    inflater = zlib.decompressobj()
    raw = inflater.decompress(packed, MAX_INFLATED_BYTES)
    if inflater.unconsumed_tail or not inflater.eof:
        raise ProtocolError(f"result inflates past {MAX_INFLATED_BYTES} bytes")
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise ProtocolError("result is not an object")
    return result
