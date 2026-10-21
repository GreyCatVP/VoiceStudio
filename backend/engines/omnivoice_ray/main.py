"""OmniVoice (VoiceStudio's own TTS) sidecar for Ray jobs.

Self-contained, unlike engines/omnivoice_subprocess/main.py (which runs on the
app's interpreter and imports backend services): the job package ships the
repo's ``omnivoice`` inference modules next to this script, and the engine
venv provides torch/transformers. The reference transcript is resolved by the
backend before the job is sent, so no ASR runs here.

Wire protocol: length-prefixed JSON over stdin/stdout, as engines/_echo/main.py
(synthesize -> audio, with progress frames while the model loads).
"""
from __future__ import annotations

import base64
import json
import os
import struct
import sys
import threading
import traceback

MAX_FRAME_BYTES = 64 * 1024 * 1024
DEFAULT_CHECKPOINT = "k2-fsa/OmniVoice"
_GEN_KW = ("language", "instruct", "duration", "num_step", "guidance_scale", "speed", "denoise",
           "postprocess_output", "preprocess_prompt", "t_shift", "layer_penalty_factor",
           "position_temperature", "class_temperature", "audio_chunk_duration", "audio_chunk_threshold")
_send_lock = threading.Lock()
_model = None

# The package root (holding omnivoice/) is this job's working dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


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


def _load(out):
    global _model
    if _model is not None:
        return _model
    import torch
    from omnivoice.models.omnivoice import OmniVoice
    from omnivoice.utils.dtype import tts_dtype_name

    checkpoint = os.environ.get("VS_OMNIVOICE_CHECKPOINT") or DEFAULT_CHECKPOINT  # resolved by the backend
    device = "cuda" if torch.cuda.is_available() else "cpu"
    stop = threading.Event()

    def beat():  # downloads and the load are silent: keep the deadline informed
        while not stop.wait(10):
            _send(out, {"op": "progress", "stage": "loading_model", "message": checkpoint})

    threading.Thread(target=beat, daemon=True).start()
    try:
        _model = OmniVoice.from_pretrained(checkpoint, device_map=device,
                                           dtype=getattr(torch, tts_dtype_name(device)), load_asr=False)
    finally:
        stop.set()
    return _model


def _pcm_b64(audio, audio_format: str):
    import numpy as np

    arr = np.asarray(audio.detach().to("cpu").float().numpy(), dtype=np.float32).squeeze()
    while arr.ndim > 1:
        arr = arr.mean(axis=int(np.argmin(arr.shape)))
    arr = np.clip(arr, -1.0, 1.0)
    if audio_format == "f32le":
        pcm = arr.astype("<f4").tobytes()
    else:
        pcm = (arr * 32767.0).astype("<i2").tobytes()
    return base64.b64encode(pcm).decode("ascii"), int(arr.shape[0])


def _synthesize(out, msg: dict) -> dict:
    text = msg.get("text")
    if not text or not isinstance(text, str):
        raise ValueError("synthesize: missing or non-string 'text'")
    model = _load(out)
    if msg.get("seed") is not None:
        import torch
        torch.manual_seed(int(msg["seed"]))
    gen_kw = {k: msg[k] for k in _GEN_KW if k in msg}
    audios = model.generate(text=text, ref_audio=msg.get("ref_audio") or None,
                            ref_text=msg.get("ref_text") or None, **gen_kw)
    audio = audios[0] if isinstance(audios, (list, tuple)) else audios
    audio_format = msg.get("audio_format") if msg.get("audio_format") in ("s16le", "f32le") else "s16le"
    pcm, n = _pcm_b64(audio, audio_format)
    return {"op": "audio", "audio_pcm_b64": pcm, "audio_format": audio_format,
            "sample_rate": int(getattr(model, "sampling_rate", 24000)), "n_samples": n}


def main() -> int:
    stdin = sys.stdin.buffer
    _frame_fd = os.dup(1)  # a private frame channel; library prints go to stderr
    os.dup2(2, 1)
    out = os.fdopen(_frame_fd, "wb")
    _send(out, {"op": "ready", "engine": "omnivoice"})
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
