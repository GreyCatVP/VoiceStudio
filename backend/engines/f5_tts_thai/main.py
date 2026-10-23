"""F5-TTS-THAI sidecar for Ray / Modal jobs (VIZINTZOR/F5-TTS-THAI).

Self-contained: stdlib at import time, the engine venv (f5-tts-th, torch,
vocos) inside the handlers. Loads the model the way f5_tts_th.tts.TTS("v1")
does, but from pinned Hugging Face revisions instead of cached_path's
unpinned ``main``. The backend prepares the reference (at most 8 s, with its
transcript) before the job is sent, so no ASR runs here; without a reference
the model card's sample voice is used.

Wire protocol: length-prefixed JSON over stdin/stdout, as engines/_echo/main.py
(synthesize -> audio, with progress frames while loading and rendering).
"""
from __future__ import annotations

import base64
import contextlib
import json
import os
import struct
import sys
import threading
import traceback

MAX_FRAME_BYTES = 64 * 1024 * 1024
MODEL_REPO = "VIZINTZOR/F5-TTS-THAI"
MODEL_REVISION = "af023c707f4208e5fc1fce59c1fd1501cfc3fc22"
CHECKPOINT_FILE = "model_1000000.pt"  # the 1M-step EMA checkpoint f5-tts-th "v1" loads
VOCAB_FILE = "vocab.txt"
VOCODER_REPO = "charactr/vocos-mel-24khz"
VOCODER_REVISION = "0feb3fdd929bcd6649e0e7c5a688cf7dd012ef21"
# f5_tts_th.tts.TTS("v1")'s DiT configuration for this checkpoint.
MODEL_CFG = {"dim": 1024, "depth": 22, "heads": 16, "ff_mult": 2, "text_dim": 512,
             "text_mask_padding": False, "conv_layers": 4, "pe_attn_head": 1}
SAMPLE_REF_FILE = "sample/ref_audio.wav"
SAMPLE_REF_TEXT = "ฉันเดินทางไปเที่ยวที่จังหวัดเชียงใหม่ในช่วงฤดูหนาวเพื่อสัมผัสอากาศเย็นสบาย"
SAMPLE_RATE = 24000
NFE_STEPS = 32
CFG_STRENGTH = 2.0

_send_lock = threading.Lock()
_engine = None  # (model, vocoder, infer_process, preprocess_ref_audio_text)


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


@contextlib.contextmanager
def _heartbeat(out, stage: str, message: str):
    """Progress frames every 10 s: imports, downloads, load and render are silent."""
    stop = threading.Event()

    def beat():
        while not stop.wait(10):
            _send(out, {"op": "progress", "stage": stage, "message": message})

    threading.Thread(target=beat, daemon=True).start()
    try:
        yield
    finally:
        stop.set()


def _load(out):
    global _engine
    if _engine is not None:
        return _engine
    with _heartbeat(out, "loading_model", MODEL_REPO):  # before the heavy imports
        from huggingface_hub import hf_hub_download
        from f5_tts_th.utils_infer import infer_process, load_model, load_vocoder, preprocess_ref_audio_text

        ckpt = hf_hub_download(MODEL_REPO, CHECKPOINT_FILE, revision=MODEL_REVISION)
        vocab = hf_hub_download(MODEL_REPO, VOCAB_FILE, revision=MODEL_REVISION)
        hf_hub_download(VOCODER_REPO, "config.yaml", revision=VOCODER_REVISION)
        vocoder_bin = hf_hub_download(VOCODER_REPO, "pytorch_model.bin", revision=VOCODER_REVISION)
        model = load_model(MODEL_CFG, ckpt, mel_spec_type="vocos", vocab_file=vocab)
        vocoder = load_vocoder("vocos", is_local=True, local_path=os.path.dirname(vocoder_bin))
        _engine = (model, vocoder, infer_process, preprocess_ref_audio_text)
    return _engine


def _reference(msg: dict):
    """(ref_audio path, ref_text) from the request, or the sample voice."""
    ref_audio = msg.get("ref_audio") or None
    ref_text = (msg.get("ref_text") or "").strip()
    if ref_audio is None:
        from huggingface_hub import hf_hub_download

        return hf_hub_download(MODEL_REPO, SAMPLE_REF_FILE, revision=MODEL_REVISION), SAMPLE_REF_TEXT
    if not ref_text:
        # f5-tts-th would otherwise download Whisper and transcribe here.
        raise ValueError("synthesize: a reference clip needs its transcript ('ref_text')")
    return ref_audio, ref_text


def _speed(msg: dict) -> float:
    try:
        speed = float(msg.get("speed") or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return min(2.0, max(0.5, speed)) if speed == speed else 1.0


def _pcm_b64(wave, audio_format: str):
    import numpy as np

    arr = np.clip(np.asarray(wave, dtype=np.float32).reshape(-1), -1.0, 1.0)
    if audio_format == "f32le":
        pcm = arr.astype("<f4").tobytes()
    else:
        pcm = (arr * 32767.0).astype("<i2").tobytes()
    return base64.b64encode(pcm).decode("ascii"), int(arr.shape[0])


def _synthesize(out, msg: dict) -> dict:
    text = msg.get("text")
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("synthesize: missing or non-string 'text'")
    ref_audio, ref_text = _reference(msg)
    model, vocoder, infer_process, preprocess = _load(out)
    with _heartbeat(out, "generating", "f5-tts-thai"):
        if msg.get("seed") is not None:
            import torch

            torch.manual_seed(int(msg["seed"]) % (2 ** 63))
        # shortcut: a requested 'duration' is not mapped to F5's fix_duration
        # (it spans every text chunk); the app fits timing after synthesis.
        ref_audio, ref_text = preprocess(ref_audio, ref_text, show_info=lambda *_a, **_k: None)
        try:
            wave, sample_rate, _ = infer_process(ref_audio, ref_text, text.strip(), model, vocoder,
                                                 mel_spec_type="vocos", show_info=lambda *_a, **_k: None,
                                                 progress=None, nfe_step=NFE_STEPS, cfg_strength=CFG_STRENGTH,
                                                 speed=_speed(msg))
        finally:
            with contextlib.suppress(OSError):
                os.remove(ref_audio)  # preprocess wrote a temporary copy
    if wave is None:
        raise RuntimeError("F5-TTS-THAI produced no audio")
    audio_format = msg.get("audio_format") if msg.get("audio_format") in ("s16le", "f32le") else "s16le"
    pcm, n = _pcm_b64(wave, audio_format)
    return {"op": "audio", "audio_pcm_b64": pcm, "audio_format": audio_format,
            "sample_rate": int(sample_rate or SAMPLE_RATE), "n_samples": n}


def main() -> int:
    stdin = sys.stdin.buffer
    _frame_fd = os.dup(1)  # a private frame channel; library prints go to stderr
    os.dup2(2, 1)
    out = os.fdopen(_frame_fd, "wb")
    _send(out, {"op": "ready", "engine": "f5-tts-thai"})
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
            elif op == "synthesize":
                _send(out, _synthesize(out, msg))
            elif op == "shutdown":
                return 0
            else:
                _send(out, {"op": "error", "stage": "dispatch", "message": f"unknown op: {op!r}"})
        except Exception as exc:
            traceback.print_exc()
            _send(out, {"op": "error", "stage": "synthesize", "message": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    sys.exit(main())
