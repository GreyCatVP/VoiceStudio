"""pyannote speaker diarization as a Ray job (dub transcription).

The pipeline is gated on Hugging Face, and no token ever reaches a cluster:
the job carries the user's locally installed, licence-accepted checkpoints
(~32 MB) and a 16 kHz mono FLAC of the recording (speaker identity is global,
so the whole file goes in one job). The result is rebuilt as a
``pyannote.core.Annotation`` so every existing consumer works unchanged; the
same job returns WeSpeaker embeddings for the ASR phrases, for the two-speaker
recovery that used to reach into the local pipeline.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

ENGINE_ID = "pyannote"
SAMPLE_RATE = 16000
MIN_PHRASE_S = 0.75  # the recovery's own threshold
from services.ray_jobs.package import MAX_PACKAGE_BYTES  # noqa: E402


def routed():
    """Ray settings when pyannote diarization should run on the cluster, else None."""
    try:
        from services.diarization_runtime import PYANNOTE, selected_backend
        from services.ray_jobs.settings import route_for
    except Exception:  # noqa: BLE001
        return None
    if selected_backend() != PYANNOTE:
        return None
    return route_for(ENGINE_ID)


_BUNDLE = (
    ("config_path.yaml", "pyannote/speaker-diarization-3.1", "config.yaml"),
    ("segmentation_path.bin", "pyannote/segmentation-3.0", "pytorch_model.bin"),
    ("embedding_path.bin", "pyannote/wespeaker-voxceleb-resnet34-LM", "pytorch_model.bin"),
)


def _local_bundle_paths() -> dict:
    """The installed pipeline files: {input name: path}. Raises if missing."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.constants import HF_HUB_CACHE

    from services.hf_revisions import installed_revision

    return {name: hf_hub_download(repo_id=repo, filename=filename,
                                  revision=installed_revision(repo, HF_HUB_CACHE), local_files_only=True)
            for name, repo, filename in _BUNDLE}


def bundle_installed() -> bool:
    try:
        return all(os.path.isfile(p) for p in _local_bundle_paths().values())
    except Exception:  # noqa: BLE001 - not installed (or unreadable): the caller says so
        return False


def _local_bundle() -> dict:
    """The installed pipeline files: {input name: bytes}."""
    out = {}
    for name, path in _local_bundle_paths().items():
        with open(path, "rb") as fh:
            out[name] = fh.read()
    return out


def _flac_16k_mono(path: str) -> tuple[bytes, float]:
    """16 kHz mono FLAC (lossless; used for parity checks)."""
    return _encode_16k_mono(path, "FLAC")


def _encode_16k_mono(path: str, fmt: str = "OPUS") -> tuple[bytes, float]:
    """The recording at 16 kHz mono, as Opus (~2-4 KB/s: hours fit in one job
    package) or FLAC (lossless). FLAC if Opus fails."""
    import soundfile as sf
    import torch

    data, sr = sf.read(path, dtype="float32", always_2d=True)
    mono = torch.from_numpy(data.mean(axis=1).copy())
    if sr != SAMPLE_RATE:
        import torchaudio.functional as AF
        mono = AF.resample(mono, sr, SAMPLE_RATE)
    buf = io.BytesIO()
    if fmt == "OPUS":
        try:
            sf.write(buf, mono.numpy(), SAMPLE_RATE, format="OGG", subtype="OPUS")
            return buf.getvalue(), mono.shape[-1] / SAMPLE_RATE
        except Exception:  # noqa: BLE001 - a libsndfile without Opus
            buf = io.BytesIO()
    sf.write(buf, mono.numpy(), SAMPLE_RATE, format="FLAC", subtype="PCM_16")
    return buf.getvalue(), mono.shape[-1] / SAMPLE_RATE


class RayPyannotePipeline:
    """Callable like a pyannote Pipeline: ``pipe(audio_path, num_speakers=N)``."""

    def __init__(self, ray_cfg, phrases: Optional[list] = None, cancelled=None) -> None:
        self.ray_cfg = ray_cfg
        self.phrases = phrases or []
        self.cancelled = cancelled
        self._embeddings: dict = {}

    def __call__(self, audio_path: str, num_speakers: Optional[int] = None):
        from pyannote.core import Annotation, Segment

        from services.ray_jobs.jobs import engine_task, run_engine_job

        bundle = _local_bundle()
        budget = MAX_PACKAGE_BYTES - 2 * 1024 * 1024 - sum(map(len, bundle.values()))
        # Lossless whenever it fits: Opus shifted speaker turns measurably
        # (DER 0.12 vs the local run on an H200); only very long recordings need it.
        audio, seconds = _encode_16k_mono(str(audio_path), "FLAC")
        name = "audio_path.flac"
        if len(audio) > budget:
            audio, seconds = _encode_16k_mono(str(audio_path), "OPUS")
            name = "audio_path.ogg"
        spans = [(float(p["start"]), float(p["end"])) for p in self.phrases
                 if p.get("text") and float(p.get("end", 0)) - float(p.get("start", 0)) >= MIN_PHRASE_S]
        params = {"num_speakers": int(num_speakers) if num_speakers else None, "phrases": spans or None}
        if len(audio) > budget:
            raise RuntimeError(f"this recording ({seconds / 60:.0f} min) is too long for one Ray diarization job")
        inputs = {**bundle, name: audio}
        task = engine_task(ENGINE_ID, self.ray_cfg, "diarize", params, inputs=inputs)
        reply = run_engine_job(ENGINE_ID, self.ray_cfg, task, timeout=3600.0 + 2.0 * seconds,
                               idle_timeout=600.0 + seconds, cancelled=self.cancelled).result
        if reply.get("op") != "diarization" or not isinstance(reply.get("turns"), list):
            raise RuntimeError("pyannote Ray job returned a malformed result")
        annotation = Annotation()
        for turn in reply["turns"]:
            # The track keeps overlapping speakers on the same span apart.
            annotation[Segment(float(turn["start"]), float(turn["end"])), turn.get("track", "_")] = str(turn["speaker"])
        vectors = reply.get("phrase_embeddings") or []
        self._embeddings = {self._key(s, e): v for (s, e), v in zip(spans, vectors) if v is not None}
        return annotation

    @staticmethod
    def _key(start: float, end: float) -> tuple:
        return (round(float(start), 3), round(float(end), 3))

    def phrase_embedding(self, start: float, end: float):
        """The WeSpeaker embedding the job computed for an ASR phrase, or None."""
        import numpy as np

        vec = self._embeddings.get(self._key(start, end))
        return None if vec is None else np.asarray(vec, dtype=np.float32)
