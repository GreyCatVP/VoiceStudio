"""Crash-isolated ASR backends (Wave 4.2 / Spec 7).

Native ASR engines (the whisper.cpp / CTranslate2 class) can segfault on GPU
teardown — a process-level crash that takes the whole backend down with it.
Running them in a child process turns that segfault into a *failed job*: the
sidecar dies, the parent surfaces a decorated error, and the next request
respawns a fresh sidecar.

This reuses ``SubprocessBackend``'s wire protocol + lifecycle (spawn, ready
handshake, length-prefixed JSON, GPU-slot acquire, and — critically —
respawn-on-dead-process: ``_spawn`` relaunches whenever the previous child
isn't alive). We add a ``transcribe`` op alongside the TTS ``synthesize`` op;
the TTS ``generate`` surface is stubbed since an ASR sidecar never synthesizes.

The base is engine-agnostic; concrete subclasses point ``sidecar_script()`` at
an engine runner. ``IsolatedFasterWhisperBackend`` wraps faster-whisper (the
CTranslate2 engine with the documented GPU-teardown crash) using the parent
venv — faster-whisper is already a dependency, so no separate venv is needed,
only process isolation.
"""

from __future__ import annotations

import logging
import math
import os
import sys
import threading
from pathlib import Path

from services.subprocess_backend import (
    _RAY_INSTALL_ALLOWANCE_S,
    RECV_TIMEOUT_S,
    SubprocessBackend,
    _ray_route,
    ray_routed,
)

logger = logging.getLogger("omnivoice.asr.subprocess")

# A model load + transcription can take a while on CPU for a long clip; give
# the transcribe round-trip more headroom than the TTS default. Configurable via
# OMNIVOICE_ASR_RECV_TIMEOUT_S (#2103).
ASR_RECV_TIMEOUT_S = 600.0


# Silent weight download in the warm-up job (large-v3 is ~3 GB).
_RAY_ASR_WARM_IDLE_S = 1800.0
_RAY_WARM: set = set()
# Package cap is 100 MB: clips per job are bounded by size and count.
_RAY_ASR_MAX_BYTES = 80 * 1024 * 1024
_RAY_ASR_MAX_CLIPS = 64


_RAY_ASR_PIECE_S = 1800.0
_RAY_ASR_SR = 16000


def _clip_seconds(path) -> float:
    try:
        import soundfile as sf
        return float(sf.info(str(path)).duration)
    except Exception:
        return os.path.getsize(path) / (_RAY_ASR_SR * 2.0)  # 16 kHz s16 guess


def _merge_pieces(results: list, offsets: list) -> dict:
    segments, chunks = [], []
    language = None
    for result, offset in zip(results, offsets):
        language = language or result.get("language")
        for seg in result.get("segments") or []:
            seg = dict(seg)
            for key in ("start", "end"):
                if isinstance(seg.get(key), (int, float)):
                    seg[key] = seg[key] + offset
            if isinstance(seg.get("words"), list):
                seg["words"] = [{**w, **{k: w[k] + offset for k in ("start", "end") if isinstance(w.get(k), (int, float))}}
                                for w in seg["words"] if isinstance(w, dict)]
            segments.append(seg)
        for chunk in result.get("chunks") or []:
            ts = chunk.get("timestamp") or (None, None)
            chunks.append({"text": chunk.get("text", ""),
                           "timestamp": tuple(t + offset if isinstance(t, (int, float)) else t for t in ts)})
    return {"segments": segments, "chunks": chunks, "language": language or "unknown",
            "text": " ".join((s.get("text") or "").strip() for s in segments).strip()}


def _align_locally(result: dict, path) -> dict:
    """wav2vec2 forced alignment here, as WhisperX and the MLX backend do:
    the cluster's faster-whisper word times are +/-100-300 ms, the aligner's
    +/-10-30 ms, and lip-sync depends on them. Never fails a transcript, and
    only uses an aligner already installed: a remote run never downloads one."""
    if os.environ.get("OMNIVOICE_RAY_ASR_ALIGN", "1") == "0" or not result.get("segments"):
        return result
    try:
        from services.asr_backend import _decode_audio_16k_mono, aligner_installed, forced_align
        language = result.get("language") or "en"
        if not aligner_installed(language):
            logger.info("local forced alignment skipped: no installed aligner for %r", language)
            return result
        aligned = forced_align(result["segments"], _decode_audio_16k_mono(str(path)), language)
    except Exception as exc:  # noqa: BLE001
        logger.info("local forced alignment skipped: %s", exc)
        return result
    if aligned is result["segments"]:
        return result
    result = dict(result, segments=aligned)
    result["chunks"] = [{"text": seg.get("text", ""), "timestamp": (seg.get("start"), seg.get("end"))}
                        for seg in aligned]
    return result


def _clip_groups(paths: list) -> list:
    groups: list = [[]]
    size = 0
    for path in paths:
        n = os.path.getsize(path)
        if groups[-1] and (size + n > _RAY_ASR_MAX_BYTES or len(groups[-1]) >= _RAY_ASR_MAX_CLIPS):
            groups.append([])
            size = 0
        groups[-1].append(path)
        size += n
    return [g for g in groups if g]


class SubprocessASRBackend(SubprocessBackend):
    """Crash-isolated ASR over the SubprocessBackend protocol.

    Concrete subclasses set ``id`` / ``display_name`` and override
    ``venv_python()`` / ``sidecar_script()``. They are registered in the ASR
    registry (``services.asr_backend._REGISTRY``); the registry uses
    ``is_available()`` + ``transcribe()`` duck-typed, so subclassing the TTS
    ``SubprocessBackend`` is fine.
    """

    # ── TTS surface stubs (an ASR sidecar never synthesizes) ───────────────
    @property
    def sample_rate(self) -> int:  # pragma: no cover - unused
        return self._DEFAULT_SAMPLE_RATE

    @property
    def supported_languages(self) -> list[str]:  # pragma: no cover - unused
        return ["multi"]

    def generate(self, text: str, **kw):  # pragma: no cover - unused
        raise NotImplementedError("ASR sidecar does not synthesize speech")

    def ensure_loaded(self) -> None:
        """Prove the lazy ASR sidecar is ready for the shared loader.

        Ray-routed: install the engine on the cluster and warm its weights
        there (a 1 s silent clip), under the loader's keep-alive rather than a
        short per-chunk transcribe budget."""
        ray_cfg = _ray_route(self.id)
        if ray_cfg is not None:
            self._ray_warm_up(ray_cfg)
            return
        with self._lock:
            self._spawn()

    # ── ASR surface ────────────────────────────────────────────────────────
    @staticmethod
    def _device() -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return "cpu"

    @property
    def recv_timeout_s(self) -> float:
        """Wall-clock timeout in seconds waiting for an ASR sidecar response (#2103)."""
        try:
            v = float(os.environ.get("OMNIVOICE_ASR_RECV_TIMEOUT_S", str(ASR_RECV_TIMEOUT_S)))
        except (ValueError, TypeError):
            return ASR_RECV_TIMEOUT_S
        if not math.isfinite(v):
            return ASR_RECV_TIMEOUT_S
        return max(30.0, v)

    def supports_translation(self) -> bool:
        # Same model resolution as the sidecar (_asr_sidecar/main.py).
        from services.asr_backend import faster_whisper_model_id, whisper_checkpoint_translates
        return whisper_checkpoint_translates(
            os.environ.get("ASR_MODEL_FW") or faster_whisper_model_id()
        )

    # ── Ray: one job per call or per batch of clips ────────────────────────
    def transcribe_many(self, audio_paths: list, *, word_timestamps: bool = True,
                        language: str | None = None, initial_prompt: str | None = None,
                        temperature: float | None = None, task: str = "transcribe",
                        return_exceptions: bool = False) -> list:
        """Transcribe several clips; on Ray, in as few jobs as fit (one model load each).

        ``return_exceptions``: a failed clip (or a failed group of clips)
        yields its exception in place of a result instead of failing all."""
        kwargs = dict(word_timestamps=word_timestamps, language=language,
                      initial_prompt=initial_prompt, temperature=temperature, task=task)
        ray_cfg = _ray_route(self.id)
        if ray_cfg is None:
            out = []
            for p in audio_paths:
                try:
                    out.append(self.transcribe(p, **kwargs))
                except Exception as exc:
                    if not return_exceptions:
                        raise
                    out.append(exc)
            return out
        self._ray_warm_up(ray_cfg)
        from services.asr_backend import whisper_request_options
        request = whisper_request_options(language, initial_prompt, temperature, task)
        out = []
        for group in _clip_groups(list(audio_paths)):
            try:
                out.extend(self._transcribe_via_ray(ray_cfg, group, word_timestamps, request,
                                                    return_exceptions=return_exceptions))
            except Exception as exc:
                if not return_exceptions:
                    raise
                out.extend([exc] * len(group))
        return out

    def _ray_env(self) -> dict:
        from services.asr_backend import _offline_asr_repo
        repo = _offline_asr_repo(self.id)
        if not repo or os.path.isabs(repo) or os.path.exists(repo):
            raise RuntimeError(
                f"{self.id} on the Ray cluster needs a Hugging Face model id, not a local "
                f"folder ({repo!r}); choose a hub model in Settings → Speech recognition."
            )
        return {"ASR_MODEL_FW": repo}

    def _transcribe_via_ray(self, ray_cfg, paths: list, word_timestamps: bool, request: dict,
                            idle_timeout: float | None = None, return_exceptions: bool = False) -> list:
        from services.performance_profiles import asr_decode_defaults
        from services.ray_jobs.engines import install_recipe, ray_engine
        from services.ray_jobs.executor import RayTask

        inputs: dict = {}
        items = []
        for i, path in enumerate(paths):
            suffix = Path(path).suffix.lower()[:8] or ".wav"
            inputs[f"audio_path__{i}{suffix}"] = Path(path).read_bytes()  # now: callers delete temp clips
            items.append({"audio_path": f"@audio_path__{i}"})
        shared = {"word_timestamps": bool(word_timestamps), "decode_options": asr_decode_defaults(),
                  **({"request_options": request} if request else {})}
        engine = ray_engine(self.id)
        # The sidecar is silent while it transcribes: the deadline must cover
        # the longest clip (3x real time, generous for CPU nodes).
        idle = idle_timeout or (self.recv_timeout_s + 3.0 * max(_clip_seconds(p) for p in paths))
        task = RayTask(
            op="batch", engine=self.id, params={"call": "transcribe", "shared": shared, "items": items},
            inputs=inputs, install=install_recipe(self.id), env=self._ray_env(),
            num_gpus=ray_cfg.gpu_request(bool(engine and engine.gpu)), num_cpus=ray_cfg.num_cpus,
        )
        result = self._run_ray_job(ray_cfg, task, timeout=_RAY_INSTALL_ALLOWANCE_S + 2 * idle * len(paths),
                                   idle_timeout=idle)
        replies = result.result.get("results")
        if result.result.get("op") != "batch" or not isinstance(replies, list) or len(replies) != len(paths):
            raise RuntimeError(f"{self.id} Ray batch returned a malformed result")
        out = []
        for path, reply in zip(paths, replies):
            try:
                result = self._normalise_reply(reply if isinstance(reply, dict) else {})
                out.append(_align_locally(result, path) if word_timestamps else result)
            except RuntimeError as exc:
                if not return_exceptions:
                    raise
                out.append(exc)
        return out

    def _transcribe_long_via_ray(self, audio_path: str, **kwargs) -> dict:
        """A long file: 16 kHz mono pieces (each under the job package cap),
        transcribed in one batch, merged back onto the file's timeline."""
        import tempfile

        import soundfile as sf
        import torch
        import torchaudio.functional as AF

        data, sr = sf.read(audio_path, dtype="float32", always_2d=True)
        mono = torch.from_numpy(data.mean(axis=1).copy())
        if sr != _RAY_ASR_SR:
            mono = AF.resample(mono, sr, _RAY_ASR_SR)
        piece = int(_RAY_ASR_PIECE_S * _RAY_ASR_SR)
        with tempfile.TemporaryDirectory() as tmp:
            paths, offsets = [], []
            for i, start in enumerate(range(0, mono.shape[0], piece)):
                path = os.path.join(tmp, f"piece{i}.wav")
                sf.write(path, mono[start:start + piece].numpy(), _RAY_ASR_SR, subtype="PCM_16")
                paths.append(path)
                offsets.append(start / _RAY_ASR_SR)
            results = self.transcribe_many(paths, **kwargs)
        return _merge_pieces(results, offsets)

    def _ray_warm_up(self, ray_cfg) -> None:
        from services.ray_jobs.engines import install_recipe
        recipe = install_recipe(self.id) or {}
        # Keyed on the model actually sent (the selected hub id) and the build.
        key = (ray_cfg.target, ray_cfg.cache_dir, self.id, self._ray_env()["ASR_MODEL_FW"], recipe.get("key"))
        if key in _RAY_WARM:
            return
        import tempfile
        import wave
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "silence.wav"
            with wave.open(str(clip), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"\0\0" * 16000)
            # The model download is silent in the sidecar: a generous deadline.
            self._transcribe_via_ray(ray_cfg, [str(clip)], False, {}, idle_timeout=_RAY_ASR_WARM_IDLE_S)
        _RAY_WARM.add(key)

    def _normalise_reply(self, reply: dict, device: str | None = None) -> dict:
        if reply.get("op") == "error":
            raise RuntimeError(
                f"{self.id} ASR sidecar error (device={device or 'ray'}): {reply.get('message')!r}"
            )
        if reply.get("op") != "segments":
            raise RuntimeError(
                f"{self.id} ASR sidecar returned unexpected op: {reply.get('op')!r}"
            )
        result = reply.get("result") or {"segments": [], "language": "unknown"}
        # The sidecar returns only `segments`; callers such as Dub read
        # `chunks`, so normalise like the in-process backends do (#2786).
        if "chunks" not in result:
            result["chunks"] = [
                {"text": seg.get("text", ""),
                 "timestamp": (seg.get("start"), seg.get("end"))}
                for seg in result.get("segments") or []
            ]
        return result

    def transcribe(self, audio_path: str, *, word_timestamps: bool = True,
                   language: str | None = None, initial_prompt: str | None = None,
                   temperature: float | None = None,
                   task: str = "transcribe") -> dict:
        """Transcribe ``audio_path`` in the sidecar. Returns the engine's
        result dict ({"segments": [...], "language": ...}).

        A sidecar crash mid-transcription raises a RuntimeError decorated with
        the engine id + device (so the failure is attributable, not a bare
        broken-pipe) — and the *next* call respawns a fresh sidecar via
        ``_spawn``'s dead-process check. Acquires a GPU-pool slot for the
        duration, released even if the child dies (the base's try/finally).
        Ray-routed: one cluster job, no local slot or sidecar."""
        if _ray_route(self.id) is not None:
            kwargs = dict(word_timestamps=word_timestamps, language=language,
                          initial_prompt=initial_prompt, temperature=temperature, task=task)
            if _clip_seconds(audio_path) > _RAY_ASR_PIECE_S or os.path.getsize(audio_path) > _RAY_ASR_MAX_BYTES:
                return self._transcribe_long_via_ray(audio_path, **kwargs)
            return self.transcribe_many([audio_path], **kwargs)[0]
        # On-pool callers (run_transcribe_guarded dispatches via run_in_executor
        # on the GPU pool) already own a pool slot; re-acquiring would
        # self-deadlock on a 1-worker (MPS) pool, so skip it. Off-pool callers
        # hold a real slot for the whole transcription via _occupy. Mirrors
        # SubprocessBackend.generate()'s path-aware slot block.
        from services.model_manager import running_on_gpu_pool
        _held = None
        slot_future = None
        if not running_on_gpu_pool():
            from services.model_manager import _get_gpu_pool
            pool = _get_gpu_pool()
            _held = threading.Event()
            _acquired = threading.Event()

            def _occupy():
                _acquired.set()
                _held.wait()

            slot_future = pool.submit(_occupy)

        try:
            if _held is not None and not _acquired.wait(timeout=10):
                if slot_future is not None:
                    slot_future.cancel()
                raise TimeoutError("timed out waiting for a free GPU worker")
            timeout_s = self.recv_timeout_s
            with self._lock:
                self._spawn()
                from services.performance_profiles import asr_decode_defaults
                from services.asr_backend import whisper_request_options
                request = whisper_request_options(
                    language, initial_prompt, temperature, task)
                self._send({
                    "op": "transcribe",
                    "audio_path": str(audio_path),
                    "word_timestamps": bool(word_timestamps),
                    "decode_options": asr_decode_defaults(),
                    # Sent only when set, so a frame without them is
                    # byte-identical to before.
                    **({"request_options": request} if request else {}),
                })
                reply = self._recv_with_timeout(timeout_s)
                # A one-time model conversion heartbeats with progress frames;
                # each re-arms the deadline, a silent wedge still times out.
                while reply is not None and reply.get("op") == "progress":
                    reply = self._recv_with_timeout(timeout_s)
                timed_out = self._last_recv_timed_out
                if not reply:
                    # EOF can arrive before Windows updates poll(); retire the
                    # stale handle so an immediate retry respawns the sidecar.
                    self.shutdown()
                    if timed_out:
                        raise RuntimeError(
                            f"{self.id} ASR sidecar exceeded receive timeout "
                            f"({timeout_s:g}s); killed mid-transcription "
                            f"(device={self._device()}) — retry or raise "
                            f"OMNIVOICE_ASR_RECV_TIMEOUT_S."
                        )
                    # Pipe closed mid-transcription → the child crashed.
                    raise RuntimeError(
                        f"{self.id} ASR sidecar crashed mid-transcription "
                        f"(device={self._device()}); the job failed but the backend "
                        f"stayed up — retry to respawn a fresh sidecar."
                    )
            return self._normalise_reply(reply, device=self._device())
        finally:
            if _held is not None:
                _held.set()


class IsolatedFasterWhisperBackend(SubprocessASRBackend):
    """faster-whisper (CTranslate2) in a child process — opt-in.

    CTranslate2's GPU teardown can segfault (the endemic faster-whisper crash);
    running it isolated keeps that from killing the backend. Uses the PARENT
    venv (faster-whisper is already installed) — only the process boundary is
    new. Select with ``OMNIVOICE_ASR_BACKEND=faster-whisper-isolated``.
    """

    id = "faster-whisper-isolated"
    display_name = "Faster-Whisper (crash-isolated subprocess)"
    # Same engine as FasterWhisperBackend, so the same device support — the
    # sidecar picks cuda/cpu itself via `_device()`. Without this the registry
    # default ("cpu",) would dishonestly report cpu_only routing on CUDA hosts.
    gpu_compat = ("cuda", "cpu")

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        if ray_routed(cls.id):  # installed and run on the Ray cluster
            return True, "runs on the Ray cluster"
        from core.execstack import ensure_ctranslate2_loadable

        ok, detail = ensure_ctranslate2_loadable()
        if not ok:
            return False, f"faster-whisper cannot load CTranslate2: {detail}"
        try:
            import faster_whisper  # noqa: F401
        except Exception as e:
            return False, f"faster-whisper not installed: {e}"
        if not cls.sidecar_script().is_file():
            return False, f"ASR sidecar script missing at {cls.sidecar_script()}"
        # Same CTranslate2 engine, same cuDNN 8 requirement (#1371). Crash
        # isolation means a missing cuDNN 8 kills only the child — so instead of
        # a dead backend the user gets a sidecar that fails every transcribe
        # with no explanation. Report it here, where Model Catalogue shows it.
        from services.asr_backend import _ctranslate2_cudnn_ok

        return _ctranslate2_cudnn_ok()

    @classmethod
    def venv_python(cls) -> Path:
        # faster-whisper lives in the parent venv — isolation is process-only.
        return Path(sys.executable)

    @classmethod
    def sidecar_script(cls) -> Path:
        return Path(__file__).resolve().parents[1] / "engines" / "_asr_sidecar" / "main.py"
