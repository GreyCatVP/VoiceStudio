"""NLLB translation sidecar (Ray jobs): the dub translator off the backend process.

Wire protocol: length-prefixed JSON over stdin/stdout, as engines/_echo/main.py.

    -> {"op": "translate", "model": "...", "revision": "...", "src": "eng_Latn",
        "groups": [{"tgt": "tha_Thai", "texts": [...]}, ...],
        "decode_options": {"num_beams": 5}, "max_length": 400, "batch_size": null}
    <- {"op": "translated", "groups": [{"tgt": ..., "texts": [...], "errors": [null | "msg", ...]}],
        "device": "cuda"}

Batching mirrors api/routers/dub_translate.py: a width from free GPU memory
and the beam count; a failed batch is retried row by row, and a failed row
keeps its source text with an error. Stdlib at the top level: torch and
transformers are imported inside the handler, from this engine's own venv.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import threading
import time
import traceback

MAX_FRAME_BYTES = 64 * 1024 * 1024
_MAX_BATCH = 32
_send_lock = threading.Lock()
_model = None
_tokenizer = None
_device = None
_loaded_key = None


def _send(stream, obj: dict) -> None:
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    with _send_lock:
        stream.write(struct.pack("!I", len(body)))
        stream.write(body)
        stream.flush()


def _recv(stream):
    header = stream.read(4)
    if len(header) < 4:
        return None
    (n,) = struct.unpack("!I", header)
    if n > MAX_FRAME_BYTES:
        raise IOError(f"frame too large: {n}")
    body = stream.read(n)
    if len(body) < n:
        raise IOError("short read")
    return json.loads(body.decode("utf-8"))


class _Heartbeat:
    """Progress frames while a silent step (download, load) runs."""

    def __init__(self, out, stage: str, message: str) -> None:
        self.out, self.stage, self.message = out, stage, message
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stop.wait(10):
            _send(self.out, {"op": "progress", "stage": self.stage, "message": self.message})

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop.set()


def _widths(device: str, num_beams: int, override) -> int:
    """dub_translate._nllb_batch_size / _nllb_hypothesis_budget, here."""
    import torch

    if override:
        return max(1, min(_MAX_BATCH, int(override)))
    batch, budget = 4, 16
    if device == "cuda":
        free_gib = torch.cuda.mem_get_info()[0] / 2 ** 30
        batch, budget = (24, 64) if free_gib >= 16 else (12, 32) if free_gib >= 8 else (8, 16)
    return max(1, min(batch, budget // max(1, num_beams)))


def _load(out, model_id: str, revision: str):
    global _model, _tokenizer, _device, _loaded_key
    if _loaded_key == (model_id, revision):
        return
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    with _Heartbeat(out, "loading", f"loading {model_id}"):
        _tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision or None)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_id, revision=revision or None)
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = model.to(_device).eval()
    _loaded_key = (model_id, revision)


def _translate(out, msg: dict) -> dict:
    import torch

    _load(out, str(msg.get("model")), str(msg.get("revision") or ""))
    decode = {k: int(v) for k, v in (msg.get("decode_options") or {}).items() if k in ("num_beams",)}
    max_length = int(msg.get("max_length") or 400)
    width = _widths(_device, decode.get("num_beams", 1), msg.get("batch_size"))
    total = sum(len(g.get("texts") or []) for g in msg.get("groups") or [])
    done = 0
    _tokenizer.src_lang = str(msg.get("src"))

    def generate(texts, tgt):
        inputs = _tokenizer(texts, return_tensors="pt", padding=True).to(_device)
        with torch.inference_mode():
            tokens = _model.generate(**inputs, forced_bos_token_id=_tokenizer.convert_tokens_to_ids(tgt),
                                     max_length=max_length, **decode)
        decoded = _tokenizer.batch_decode(tokens, skip_special_tokens=True)
        if len(decoded) != len(texts):
            raise RuntimeError("translation returned a different number of rows")
        return decoded

    groups_out = []
    for group in msg.get("groups") or []:
        tgt = str(group.get("tgt"))
        texts = [str(t) for t in group.get("texts") or []]
        results, errors = list(texts), [None] * len(texts)
        todo = [i for i, t in enumerate(texts) if t.strip()]  # blanks pass through
        for start in range(0, len(todo), width):
            idx = todo[start:start + width]
            try:
                for i, text in zip(idx, generate([texts[i] for i in idx], tgt)):
                    results[i] = text
            except Exception:  # retry row by row; keep per-row errors
                if _device == "cuda":
                    torch.cuda.empty_cache()
                for i in idx:
                    try:
                        results[i] = generate([texts[i]], tgt)[0]
                    except Exception as exc:
                        errors[i] = f"{type(exc).__name__}: {exc}"
            done += len(idx)
            # A real unit of work (not a timer): its own stage, credited as progress.
            _send(out, {"op": "progress", "stage": "translating", "percent": round(100.0 * done / max(1, total), 1)})
        groups_out.append({"tgt": tgt, "texts": results, "errors": errors})
    return {"op": "translated", "groups": groups_out, "device": _device}


def main() -> int:
    stdin = sys.stdin.buffer
    _frame_fd = os.dup(1)  # a private frame channel; library prints go to stderr
    os.dup2(2, 1)
    out = os.fdopen(_frame_fd, "wb")
    _send(out, {"op": "ready", "engine": "nllb"})
    while True:
        try:
            msg = _recv(stdin)
        except Exception as exc:
            _send(out, {"op": "error", "stage": "recv", "message": f"{type(exc).__name__}: {exc}"})
            return 1
        if msg is None:
            return 0
        op = msg.get("op")
        try:
            if op == "ping":
                _send(out, {"op": "pong"})
            elif op == "translate":
                started = time.monotonic()
                reply = _translate(out, msg)
                reply["seconds"] = round(time.monotonic() - started, 2)
                _send(out, reply)
            elif op == "shutdown":
                return 0
            else:
                _send(out, {"op": "error", "stage": "dispatch", "message": f"unknown op: {op!r}"})
        except Exception as exc:
            traceback.print_exc()
            stage = "load" if _loaded_key is None else "translate"
            _send(out, {"op": "error", "stage": stage, "message": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    sys.exit(main())
