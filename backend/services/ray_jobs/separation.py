"""Demucs vocals/background separation as Ray jobs (dub ingest, mic clean-up).

The track goes in 120 s windows with 5 s of context on each side, as FLAC
(the job package is capped at 100 MB, results at 50 MB); the cluster returns
each window's trimmed vocals (mono) and bed (stereo) as FLAC, normalised with
the whole track's statistics so the windows join without seams. Several
windows share a job (one model load); a job the worker cuts short at its
result budget continues with the rest.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

ENGINE_ID = "demucs"
HTDEMUCS_REVISION = "cbc8a9b1a87023b7fd74e7b3412e6321c0eab003"  # adefossez/HTDemucs, reviewed 2026-10-21
SAMPLE_RATE = 44100
WINDOW_S = 90.0  # two stereo FLAC stems per window stay well under the result cap
PAD_S = 5.0
MAX_INPUT_BYTES = 80 * 1024 * 1024


def _flac(audio, sample_rate: int) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="FLAC", subtype="PCM_16")
    return buf.getvalue()


def _windows(frames: int, sample_rate: int):
    core, pad = int(WINDOW_S * sample_rate), int(PAD_S * sample_rate)
    out = []
    for start in range(0, max(frames, 1), core):
        end = min(frames, start + core)
        a, b = max(0, start - pad), min(frames, end + pad)
        out.append((a, b, start - a, b - end))
    return out


def separate_on_ray(ray_cfg, src_path: str, vocals_out: str, bed_out: str, *,
                    on_progress: Optional[Callable[[float], None]] = None, cancelled=None) -> None:
    """Write ``vocals_out`` and ``bed_out`` (44.1 kHz stereo, like the CLI)."""
    import numpy as np
    import soundfile as sf
    import torch

    from services.ray_jobs.jobs import engine_task, run_engine_job

    data, sr = sf.read(src_path, dtype="float32", always_2d=True)  # (T, C)
    wav = torch.from_numpy(data.T.copy())
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    wav = wav[:2]
    if sr != SAMPLE_RATE:
        import torchaudio.functional as AF
        wav = AF.resample(wav, sr, SAMPLE_RATE)
    ref = wav.mean(0)
    mean, std = float(ref.mean()), float(ref.std()) or 1.0
    windows = _windows(wav.shape[-1], SAMPLE_RATE)
    payloads = [_flac(wav[:, a:b].numpy().T, SAMPLE_RATE) for a, b, _, _ in windows]
    vocals_parts: list = [None] * len(windows)
    bed_parts: list = [None] * len(windows)
    pending = list(range(len(windows)))
    done = 0

    def progress(event: dict) -> None:
        if on_progress is None:
            return
        stage = event.get("stage")
        if stage == "item_done":
            return
        frac = float(event.get("fraction") or 0.0) if stage == "engine:separating" else 0.0
        on_progress(min(1.0, (done + frac) / len(windows)))

    while pending:
        group, size = [], 0
        for i in pending:
            if group and size + len(payloads[i]) > MAX_INPUT_BYTES:
                break
            group.append(i)
            size += len(payloads[i])
        items = [{"audio_path": f"@w{i}", "pad_l": windows[i][2], "pad_r": windows[i][3]} for i in group]
        params = {"call": "separate", "shared": {"revision": HTDEMUCS_REVISION, "mean": mean, "std": std},
                  "items": items}
        task = engine_task(ENGINE_ID, ray_cfg, "batch", params, inputs={f"w{i}.flac": payloads[i] for i in group})
        seconds = sum((windows[i][1] - windows[i][0]) / SAMPLE_RATE for i in group)
        result = run_engine_job(ENGINE_ID, ray_cfg, task, timeout=3600.0 + 4.0 * seconds,
                                idle_timeout=600.0 + 2.0 * WINDOW_S, on_progress=progress,
                                cancelled=cancelled).result
        replies = result.get("results")
        if result.get("op") != "batch" or not isinstance(replies, list) or not replies or len(replies) > len(group):
            raise RuntimeError("demucs Ray batch returned a malformed result")
        for i, reply in zip(group, replies):
            if not isinstance(reply, dict) or reply.get("op") != "separated":
                msg = reply.get("message") if isinstance(reply, dict) else "malformed item"
                raise RuntimeError(f"demucs separation failed on the cluster: {msg}")
            vocals, _ = sf.read(io.BytesIO(base64.b64decode(reply["vocals_b64"])), dtype="float32", always_2d=True)
            bed, _ = sf.read(io.BytesIO(base64.b64decode(reply["bed_b64"])), dtype="float32", always_2d=True)
            vocals_parts[i], bed_parts[i] = vocals, bed
            done += 1
            if on_progress is not None:
                on_progress(done / len(windows))
        pending = pending[len(replies):]
    sf.write(vocals_out, np.concatenate(vocals_parts, axis=0), SAMPLE_RATE, subtype="PCM_16")
    sf.write(bed_out, np.concatenate(bed_parts, axis=0), SAMPLE_RATE, subtype="PCM_16")
