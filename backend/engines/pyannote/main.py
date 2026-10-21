"""pyannote speaker-diarization sidecar (Ray jobs).

Wire protocol: length-prefixed JSON over stdin/stdout, as engines/_echo/main.py.

    -> {"op": "diarize", "audio_path": "<16 kHz mono FLAC>", "config_path": "<config.yaml>",
        "segmentation_path": "<.bin>", "embedding_path": "<.bin>",
        "num_speakers": null | int, "phrases": null | [[start, end], ...]}
    <- {"op": "diarization", "turns": [{"start": s, "end": e, "speaker": "SPEAKER_00"}, ...],
        "phrase_embeddings": null | [[float, ...], ...]}

The checkpoints are the user's locally installed copies, shipped with the job
(the pipeline is gated on Hugging Face and no token ever reaches a cluster);
the config is rewritten here to point at them, as services/diarization_local.py
does locally. ``phrases`` asks for the WeSpeaker embedding of each span, for
the backend's two-speaker recovery. Stdlib at the top level.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import threading
import traceback

MAX_FRAME_BYTES = 64 * 1024 * 1024
_send_lock = threading.Lock()


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


def _allow_checkpoint_globals() -> None:
    """torch>=2.6's secure unpickler: the inert classes pyannote checkpoints
    carry (the same allowlist as WhisperXBackend._allow_vad_pickle_globals)."""
    import argparse
    import collections
    import enum
    import pathlib
    import typing

    import numpy as np
    import torch
    import torch.serialization as ts

    allow = [argparse.Namespace, collections.OrderedDict, collections.defaultdict, typing.Any,
             enum.Enum, enum.IntEnum, enum.Flag, enum.IntFlag, torch.Size,
             list, dict, tuple, set, frozenset, int, float, bool, str, bytes, bytearray, complex,
             type(None), slice, range, np.ndarray, np.dtype, np.int8, np.int16, np.int32, np.int64,
             np.uint8, np.uint16, np.uint32, np.uint64, np.float16, np.float32, np.float64, np.bool_,
             pathlib.PurePath, pathlib.PurePosixPath, pathlib.Path, pathlib.PosixPath]
    try:
        from torch.torch_version import TorchVersion
        allow.append(TorchVersion)
    except Exception:
        pass
    for modname in ("numpy._core.multiarray", "numpy.core.multiarray"):
        try:
            mod = __import__(modname, fromlist=["_reconstruct", "scalar"])
            allow += [getattr(mod, a) for a in ("_reconstruct", "scalar") if hasattr(mod, a)]
        except Exception:
            pass
    try:
        import omegaconf.base as ocb
        import omegaconf.nodes as ocn
        from omegaconf.dictconfig import DictConfig
        from omegaconf.listconfig import ListConfig
        allow += [ListConfig, DictConfig]
        for mod in (ocn, ocb):
            allow += [o for o in vars(mod).values() if isinstance(o, type) and o.__module__ == mod.__name__]
    except Exception:
        pass
    try:
        from pyannote.audio.core.model import Introspection, Output
        from pyannote.audio.core.task import Problem, Resolution, Specifications
        allow += [Introspection, Output, Problem, Resolution, Specifications]
    except Exception:
        pass
    ts.add_safe_globals(allow)


def _token_kwarg_compat() -> None:
    """pyannote 3.x passes use_auth_token, which huggingface_hub 1.x removed."""
    import functools

    import huggingface_hub as hf

    for name in ("hf_hub_download", "snapshot_download"):
        orig = getattr(hf, name, None)
        if orig is None or getattr(orig, "_vs_shim", False):
            continue

        @functools.wraps(orig)
        def wrapped(*a, _orig=orig, **kw):
            if "use_auth_token" in kw:
                kw.setdefault("token", kw.pop("use_auth_token"))
            return _orig(*a, **kw)

        wrapped._vs_shim = True
        setattr(hf, name, wrapped)


def _diarize(out, msg: dict) -> dict:
    import soundfile as sf
    import torch
    import yaml

    _token_kwarg_compat()
    _allow_checkpoint_globals()
    from pyannote.audio import Pipeline
    from pyannote.core import Segment

    config = yaml.safe_load(open(msg["config_path"], encoding="utf-8"))
    params = config["pipeline"]["params"]
    params["segmentation"] = str(msg["segmentation_path"])
    params["embedding"] = str(msg["embedding_path"])
    config_path = os.path.join(os.path.dirname(str(msg["audio_path"])), "pipeline.yaml")
    with open(config_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh)
    _send(out, {"op": "progress", "stage": "loading", "message": "loading pyannote"})
    pipeline = Pipeline.from_pretrained(config_path)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        pipeline.to(torch.device("cuda"))

    data, sr = sf.read(str(msg["audio_path"]), dtype="float32", always_2d=True)
    waveform = torch.from_numpy(data.mean(axis=1, keepdims=True).T.copy())  # (1, T)
    audio = {"waveform": waveform, "sample_rate": sr}

    def hook(step_name, step_artifact, file=None, total=None, completed=None):
        if total:
            _send(out, {"op": "progress", "stage": f"diarizing:{step_name}",
                        "percent": round(100.0 * (completed or 0) / total, 1)})

    kwargs = {"hook": hook}
    if msg.get("num_speakers"):
        kwargs["num_speakers"] = int(msg["num_speakers"])
    annotation = pipeline(audio, **kwargs)
    turns = [{"start": float(t.start), "end": float(t.end), "track": str(track), "speaker": str(label)}
             for t, track, label in annotation.itertracks(yield_label=True)]

    embeddings = None
    if msg.get("phrases"):
        # Optional (the backend's speaker recovery): never lose the turns to it.
        import numpy as np
        try:
            embedding_model = pipeline._embedding
            duration = waveform.shape[-1] / sr
            embeddings = []
            for start, end in msg["phrases"]:
                start, end = max(0.0, float(start)), min(duration, float(end))
                if end - start <= 0.0:
                    embeddings.append(None)
                    continue
                seg = Segment(start, end)
                crop, _ = pipeline._audio.crop(audio, seg, duration=seg.duration, mode="pad")
                vec = np.asarray(embedding_model(crop[None])).reshape(-1)
                embeddings.append([float(x) for x in vec])
        except Exception:
            traceback.print_exc()
            embeddings = None
    if device == "cuda":
        torch.cuda.empty_cache()
    return {"op": "diarization", "turns": turns, "phrase_embeddings": embeddings, "device": device}


def main() -> int:
    stdin = sys.stdin.buffer
    _frame_fd = os.dup(1)  # a private frame channel; library prints go to stderr
    os.dup2(2, 1)
    out = os.fdopen(_frame_fd, "wb")
    _send(out, {"op": "ready", "engine": "pyannote"})
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
            elif op == "diarize":
                _send(out, _diarize(out, msg))
            elif op == "shutdown":
                return 0
            else:
                _send(out, {"op": "error", "stage": "dispatch", "message": f"unknown op: {op!r}"})
        except Exception as exc:
            traceback.print_exc()
            _send(out, {"op": "error", "stage": "diarize", "message": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    sys.exit(main())
