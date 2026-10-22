"""Hub Whisper checkpoints that faster-whisper loads only after a CTranslate2 conversion.

Some ASR models ship in Transformers format only (no CTranslate2 build on the
Hub). The faster-whisper engines convert such a checkpoint once, at the pinned
revision, into the HF cache next to its download, then load the converted
directory. The same code runs in the app, in the local isolated sidecar and in
the Ray/Modal sidecar, so it stays stdlib-only at import time (the sidecar runs
with a clean import path); huggingface_hub and the CTranslate2 converter
(which needs transformers + torch) import lazily, only when converting.

The per-model decode settings live here too: the measured chunk length is
part of what makes the model accurate, so every engine must apply it.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

# repo id -> conversion pin and decode settings. The revision must equal the
# model's runtime_revision in config/model_licenses.json (a test checks it);
# it is duplicated because the sidecar cannot read the backend config.
CONVERTED_MODELS = {
    "typhoon-ai/typhoon-whisper-turbo": {
        "revision": "3c03fa84c26f172944422ceb8a4e88a2dbc08b10",
        # Thai CER on 40 TVSpeech clips (H200): 12.4% with the default 30 s
        # window (long clips lose their last quarter), 5.2% batched at 15 s.
        "chunk_length": 15,
        "batch_size": 8,
    },
}

_COPY_FILES = ("tokenizer.json", "preprocessor_config.json")
_DOWNLOAD_PATTERNS = ["*.json", "*.safetensors", "*.txt"]
_MARKER = ".voicestudio-ct2-complete"
_QUANTIZATION = "float16"  # CTranslate2 re-quantizes at load (int8 on CPU)
_STALE_TMP_S = 6 * 3600
_HEARTBEAT_S = 10.0

Progress = Callable[[str], None]


def model_settings(name: Optional[str]) -> Optional[dict]:
    """The conversion/decode settings for a repo id, or None for ordinary models."""
    return CONVERTED_MODELS.get(str(name or "").strip())


def _hub_cache() -> Path:
    from huggingface_hub import constants  # noqa: PLC0415 - honours HF_HOME / HF_HUB_CACHE

    return Path(constants.HF_HUB_CACHE)


def converted_dir(repo_id: str, revision: str, cache: Optional[Path] = None) -> Path:
    """Where the conversion of ``repo_id``@``revision`` lives.

    Inside the repo's own HF cache folder, so deleting the model in the Model
    Catalogue removes its conversion too (the HF cache scanner ignores it).
    """
    root = Path(cache) if cache is not None else _hub_cache()
    return root / ("models--" + repo_id.replace("/", "--")) / "voicestudio-ct2" / f"{revision}-{_QUANTIZATION}"


def is_converted(path: Path, repo_id: str, revision: str) -> bool:
    try:
        marker = (Path(path) / _MARKER).read_text(encoding="utf-8").split("\n")
    except OSError:
        return False
    return marker[:2] == [repo_id, revision] and (Path(path) / "model.bin").is_file()


def _download(repo_id: str, revision: str) -> str:
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    try:  # an installed copy converts offline, without asking the Hub
        return snapshot_download(repo_id, revision=revision, allow_patterns=_DOWNLOAD_PATTERNS,
                                 local_files_only=True)
    except Exception:  # noqa: BLE001 - not (fully) cached: download it, resumably
        return snapshot_download(repo_id, revision=revision, allow_patterns=_DOWNLOAD_PATTERNS)


def _convert(source: str, out: str) -> None:
    from ctranslate2.converters import TransformersConverter  # noqa: PLC0415 - needs transformers + torch

    TransformersConverter(source, copy_files=list(_COPY_FILES), load_as_float16=True).convert(
        out, quantization=_QUANTIZATION, force=True)


def _drop_stale_tmp(final: Path) -> None:
    for tmp in final.parent.glob(final.name + ".tmp-*"):
        try:
            if time.time() - tmp.stat().st_mtime > _STALE_TMP_S:
                shutil.rmtree(tmp, ignore_errors=True)
        except OSError:
            pass


def ensure_converted(repo_id: str, *, progress: Optional[Progress] = None, cache: Optional[Path] = None,
                     download: Callable[[str, str], str] = _download,
                     convert: Callable[[str, str], None] = _convert) -> str:
    """Return the CTranslate2 directory for a converted model, converting it first if needed.

    Atomic: the conversion goes to a private temp dir that is renamed into
    place only once complete, so a crash or a concurrent job never leaves a
    half-written model where the engine looks. The download is resumable (HF
    cache). ``progress`` is called every few seconds while it works, so a
    sidecar can heartbeat through a silence deadline.
    """
    settings = model_settings(repo_id)
    if settings is None:
        raise ValueError(f"{repo_id!r} is not a model VoiceStudio converts")
    revision = settings["revision"]
    final = converted_dir(repo_id, revision, cache)
    if is_converted(final, repo_id, revision):
        return str(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    _drop_stale_tmp(final)
    tmp = final.parent / f"{final.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    stage = ["downloading"]
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(_HEARTBEAT_S):
            progress(f"{stage[0]} {repo_id} for faster-whisper")  # type: ignore[misc]

    beater = threading.Thread(target=beat, daemon=True) if progress else None
    if beater:
        progress(f"preparing {repo_id} for faster-whisper (one time)")  # type: ignore[misc]
        beater.start()
    try:
        source = download(repo_id, revision)
        stage[0] = "converting"
        convert(source, str(tmp))
        if not (tmp / "model.bin").is_file():
            raise RuntimeError(f"converting {repo_id} produced no model.bin")
        (tmp / _MARKER).write_text(f"{repo_id}\n{revision}\n", encoding="utf-8")
        try:
            os.rename(tmp, final)
        except OSError:
            if not is_converted(final, repo_id, revision):
                # A leftover without a marker (from an older layout) blocks the rename.
                shutil.rmtree(final, ignore_errors=True)
                os.rename(tmp, final)
            # else: a concurrent job finished first; its copy is identical.
    finally:
        stop.set()
        if beater:
            beater.join()  # no heartbeat frame may interleave with the next reply
        shutil.rmtree(tmp, ignore_errors=True)
    return str(final)


def transcribe(model, audio, name: Optional[str], **kwargs):
    """``model.transcribe`` with the model's measured decode settings.

    A model with a chunk length runs through faster-whisper's batched pipeline
    (VAD-cut windows of that length); the rest keep the plain call.
    """
    settings = model_settings(name)
    if not settings or not settings.get("chunk_length"):
        return model.transcribe(audio, **kwargs)
    from faster_whisper import BatchedInferencePipeline  # noqa: PLC0415

    return BatchedInferencePipeline(model=model).transcribe(
        audio, chunk_length=settings["chunk_length"], batch_size=settings.get("batch_size", 8), **kwargs)
