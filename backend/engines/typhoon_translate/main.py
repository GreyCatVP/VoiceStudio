"""Typhoon Translate 1.5 sidecar (Ray jobs): Thai <-> English dub translation.

Wire protocol: length-prefixed JSON over stdin/stdout, as engines/nllb/main.py.

    -> {"op": "translate", "model": "...", "revision": "...", "src": "English",
        "groups": [{"tgt": "Thai", "texts": [...]}, ...],
        "rules": ["Translate \"X\" as \"Y\".", ...], "batch_size": null}
    <- {"op": "translated", "groups": [{"tgt": ..., "texts": [...], "errors": [null | "msg", ...]}],
        "device": "cuda"}

The model (a Qwen3-4B instruct fine-tune) takes the model card's chat prompt;
``rules`` become its numbered rules (a glossary rule only for the rows that
contain its term). Generation is greedy and batched with
left padding, a width from free GPU memory, and a token budget scaled to the
longest input. A failed batch is retried row by row, and a failed row keeps
its source text with an error. Stdlib at the top level: torch and transformers
are imported inside the handler, from this engine's own venv.
"""
from __future__ import annotations

import json
import os
import re
import struct
import sys
import threading
import time
import traceback

MAX_FRAME_BYTES = 64 * 1024 * 1024
_MAX_BATCH = 32
LANGUAGES = ("English", "Thai")
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
        raise OSError(f"frame too large: {n}")
    body = stream.read(n)
    if len(body) < n:
        raise OSError("short read")
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


def build_prompt(text: str, src: str, tgt: str, rules=()) -> str:
    """The model card's user message, with numbered rules when there are any."""
    if (src, tgt) not in (("English", "Thai"), ("Thai", "English")):
        raise ValueError(f"Typhoon Translate supports English<->Thai only, not {src}->{tgt}")
    rules = [str(r).strip() for r in rules or () if str(r).strip()]
    if not rules:
        return (f"Translate the following {src} text into {tgt} and return only the translated text.\n"
                f"Source Text:\n{text}")
    numbered = "\n".join(f"{i}. {rule}" for i, rule in enumerate(rules, 1))
    return (f"Translate the following {src} text into {tgt}, strictly following the rules below "
            f"and return only the translated text.\nRules:\n{numbered}\nSource Text:\n{text}")


_TERM_RULE = re.compile(r'\ATranslate "(.+)" as ".*"\.\Z', re.DOTALL)


def rules_for(text: str, rules) -> list:
    """The rules that concern this text: a glossary rule (Translate "X" as "Y".)
    only when X occurs in it, so a term never leaks into an unrelated line;
    any other rule always."""
    folded = text.casefold()
    keep = []
    for rule in rules or ():
        term = _TERM_RULE.match(str(rule).strip())
        if term is None or term.group(1).casefold() in folded:
            keep.append(rule)
    return keep


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_LEADING_LABEL = re.compile(r"\A\s*(?:source text|translated text)\s*:\s*", re.IGNORECASE)
_TRAILING_ECHO = re.compile(r"\n\s*source text\s*:.*\Z", re.IGNORECASE | re.DOTALL)
_QUOTES = (('"', '"'), ("“", "”"), ("'", "'"), ("‘", "’"))


def clean_output(text: str, source: str) -> str:
    """Drop a reasoning block, an echoed "Source Text:" (with the source) before
    or after the translation, and wrapping quotes the source did not have."""
    out = _THINK.sub("", text or "").strip()
    label = _LEADING_LABEL.match(out)
    if label:
        out = out[label.end():].lstrip()
        if source.strip() and out.startswith(source.strip()):
            out = out[len(source.strip()):].lstrip()
            out = _LEADING_LABEL.sub("", out, count=1).lstrip()
    out = _TRAILING_ECHO.sub("", out).strip()
    src = source.strip()
    for left, right in _QUOTES:
        if len(out) >= 2 and out[0] == left and out[-1] == right and not (src[:1] == left and src[-1:] == right):
            out = out[1:-1].strip()
            break
    return out


def _width(device: str, override) -> int:
    import torch

    if override:
        return max(1, min(_MAX_BATCH, int(override)))
    if device != "cuda":
        return 4
    free_gib = torch.cuda.mem_get_info()[0] / 2 ** 30
    return 32 if free_gib >= 40 else 16 if free_gib >= 20 else 8 if free_gib >= 10 else 4


def _load(out, model_id: str, revision: str):
    global _model, _tokenizer, _device, _loaded_key
    if _loaded_key == (model_id, revision):
        return
    with _Heartbeat(out, "loading", f"loading {model_id}"):  # imports too: slow from a cold volume
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision or None)
        tokenizer.padding_side = "left"  # decoder-only batches pad on the left
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        dtype = torch.bfloat16 if _device == "cuda" else torch.float32
        model = AutoModelForCausalLM.from_pretrained(model_id, revision=revision or None, dtype=dtype)
        _model, _tokenizer = model.to(_device).eval(), tokenizer
    _loaded_key = (model_id, revision)


def _translate(out, msg: dict) -> dict:
    _load(out, str(msg.get("model")), str(msg.get("revision") or ""))
    import torch

    src = str(msg.get("src"))
    rules = [str(r) for r in msg.get("rules") or []]
    width = _width(_device, msg.get("batch_size"))
    # Blank rows pass through untranslated, so they are not part of the work.
    total = sum(1 for g in msg.get("groups") or [] for t in g.get("texts") or [] if str(t).strip())
    done = 0

    def generate(texts, tgt):
        messages = [[{"role": "user", "content": build_prompt(t, src, tgt, rules_for(t, rules))}] for t in texts]
        prompts = [_tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=True, enable_thinking=False)
                   for m in messages]
        inputs = _tokenizer(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(_device)
        longest = max(len(_tokenizer(t, add_special_tokens=False)["input_ids"]) for t in texts)
        # Thai takes more tokens than English; the cap keeps a runaway row bounded.
        budget = min(2048, 64 + 4 * longest)
        with torch.inference_mode():
            tokens = _model.generate(**inputs, max_new_tokens=budget, do_sample=False,
                                     pad_token_id=_tokenizer.pad_token_id)
        decoded = _tokenizer.batch_decode(tokens[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        if len(decoded) != len(texts):
            raise RuntimeError("translation returned a different number of rows")
        cleaned = [clean_output(d, t) for d, t in zip(decoded, texts)]
        if not all(cleaned):
            raise RuntimeError("empty translation")
        return cleaned

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
    _send(out, {"op": "ready", "engine": "typhoon-translate"})
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
