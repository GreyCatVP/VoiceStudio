"""Demucs source-separation sidecar (Ray jobs): the dub's vocals/background split.

Wire protocol: length-prefixed JSON over stdin/stdout, as engines/_echo/main.py.

    -> {"op": "separate", "audio_path": "<window.flac>", "revision": "<sha>",
        "mean": m, "std": s, "pad_l": n, "pad_r": n}
    <- {"op": "separated", "sample_rate": 44100, "frames": N,
        "vocals_b64": <FLAC mono>, "bed_b64": <FLAC stereo>}

Same model and semantics as the CLI the local path runs
(`demucs.separate --two-stems vocals -n htdemucs`): htdemucs, shifts=1,
overlap=0.25, the bed is the SUM of the non-vocal stems ("--other-method
add"). The backend sends windows with context pads and the whole track's
normalisation, so the trimmed windows join seamlessly. Stdlib at the top
level; torch/demucs/soundfile come from this engine's venv.
"""
from __future__ import annotations

import base64
import io
import json
import os
import struct
import sys
import threading
import traceback

MAX_FRAME_BYTES = 64 * 1024 * 1024
REPO = "adefossez/HTDemucs"
_send_lock = threading.Lock()
_model = None
_model_key = None
_device = None


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


def _load(out, revision: str):
    """htdemucs at a pinned hub revision (demucs.hf.get_hf_model takes none)."""
    global _model, _model_key, _device
    if _model_key == revision:
        return
    import torch
    import yaml
    from demucs.apply import BagOfModels
    from demucs.hf import load_safetensors_model
    from huggingface_hub import hf_hub_download

    _send(out, {"op": "progress", "stage": "loading", "message": "loading htdemucs"})
    rev = revision or None
    with open(hf_hub_download(REPO, "htdemucs.yaml", revision=rev)) as fh:
        bag = yaml.safe_load(fh)
    models = [load_safetensors_model(hf_hub_download(REPO, f"{sig}.safetensors", revision=rev))
              for sig in bag["models"]]
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    _model = BagOfModels(models, bag.get("weights"), bag.get("segment")).eval()
    _model_key = revision


def _flac_b64(audio, sample_rate: int) -> str:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="FLAC", subtype="PCM_16")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _separate(out, msg: dict) -> dict:
    import numpy as np
    import soundfile as sf
    import torch
    from demucs.apply import apply_model

    _load(out, str(msg.get("revision") or ""))
    data, sr = sf.read(str(msg["audio_path"]), dtype="float32", always_2d=True)  # (T, C)
    if sr != _model.samplerate:
        raise ValueError(f"expected {_model.samplerate} Hz input, got {sr}")
    wav = torch.from_numpy(data.T.copy())
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)  # demucs is stereo; mono duplicates, as convert_audio does
    wav = wav[:2]
    mean, std = float(msg.get("mean", 0.0)), float(msg.get("std", 1.0)) or 1.0

    def callback(info: dict) -> None:
        length = max(1, int(info.get("audio_length") or 1))
        pct = 100.0 * min(1.0, float(info.get("segment_offset") or 0) / length)
        _send(out, {"op": "progress", "stage": "separating", "percent": round(pct, 1)})

    with torch.inference_mode():
        sources = apply_model(_model, ((wav - mean) / std)[None], shifts=1, split=True, overlap=0.25,
                              device=_device, callback=callback, progress=False)[0]
    sources = sources * std + mean
    names = list(_model.sources)
    vocals = sources[names.index("vocals")]
    bed = sum(sources[i] for i, name in enumerate(names) if name != "vocals")
    pad_l, pad_r = int(msg.get("pad_l") or 0), int(msg.get("pad_r") or 0)
    end = vocals.shape[-1] - pad_r
    vocals, bed = vocals[:, pad_l:end], bed[:, pad_l:end]
    # Stereo stems like the CLI's; clamped (per-file rescale would make the
    # windows' levels jump).
    vocals_np = vocals.clamp(-1, 1).cpu().numpy().T
    bed_np = bed.clamp(-1, 1).cpu().numpy().T
    if _device == "cuda":
        torch.cuda.empty_cache()
    return {"op": "separated", "sample_rate": sr, "frames": int(vocals_np.shape[0]),
            "vocals_b64": _flac_b64(vocals_np.astype(np.float32), sr),
            "bed_b64": _flac_b64(bed_np.astype(np.float32), sr), "device": _device}


def main() -> int:
    stdin = sys.stdin.buffer
    _frame_fd = os.dup(1)  # a private frame channel; library prints go to stderr
    os.dup2(2, 1)
    out = os.fdopen(_frame_fd, "wb")
    _send(out, {"op": "ready", "engine": "demucs"})
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
            elif op == "separate":
                _send(out, _separate(out, msg))
            elif op == "shutdown":
                return 0
            else:
                _send(out, {"op": "error", "stage": "dispatch", "message": f"unknown op: {op!r}"})
        except Exception as exc:
            traceback.print_exc()
            _send(out, {"op": "error", "stage": "separate", "message": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    sys.exit(main())
