"""f5-tts-thai: VIZINTZOR/F5-TTS-THAI on the remote GPU only.

A Thai + English fine-tune of SWivid/F5-TTS that clones a voice from a short
reference clip and its transcript. It has no local install path: the engine is
available only when it is routed to a Ray cluster or Modal (Settings → Remote
GPU), where ``engines/f5_tts_thai/main.py`` runs in its own venv.

The model conditions on 2-8 s of reference audio paired with the words spoken
in it. The app prepares both before the job leaves: a longer clip is cut to
its best 8 s window with the installed recognizer (the same ranking OmniVoice
uses for its 15 s passage), and a short clip without a transcript is
transcribed. Without a reference the sidecar uses the model card's sample
voice.
"""
from __future__ import annotations

import logging
import math
import os
from pathlib import Path

from services.subprocess_backend import ReferenceScopeMixin, SubprocessBackend

logger = logging.getLogger("omnivoice.f5_tts_thai")

ENGINE_ID = "f5-tts-thai"
REMOTE_ONLY_REASON = (
    "F5-TTS-THAI runs only on a remote GPU: turn on f5-tts-thai in Settings → Remote GPU."
)


class F5TTSThaiBackend(ReferenceScopeMixin, SubprocessBackend):
    """F5-TTS-THAI, sent to the remote GPU for every synthesis."""
    supports_float_transport = True
    supports_generation_seed = True

    id = ENGINE_ID
    display_name = "F5-TTS-THAI (Thai + English, voice cloning, remote GPU)"
    supports_cloning = True
    gpu_compat = ("cuda",)
    _DEFAULT_SAMPLE_RATE = 24_000
    # The model card: reference clips should be 2-8 s long.
    max_ref_seconds = 8.0
    ref_strategy = "best_window"

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        from services.subprocess_backend import ray_routed

        if not ray_routed(cls.id):
            return False, REMOTE_ONLY_REASON
        return True, "ready"

    @classmethod
    def venv_python(cls) -> Path:
        raise RuntimeError(REMOTE_ONLY_REASON)

    @classmethod
    def sidecar_script(cls) -> Path:
        return Path(__file__).resolve().parent / "main.py"

    @property
    def recv_timeout_s(self) -> float:
        # Silence deadline on the cluster: the sidecar heartbeats while the
        # checkpoint downloads, loads and renders, re-arming it each time.
        try:
            v = float(os.environ.get("OMNIVOICE_F5_TTS_THAI_RECV_TIMEOUT_S", "900"))
        except (TypeError, ValueError):
            return 900.0
        return max(30.0, v) if math.isfinite(v) else 900.0

    @property
    def sample_rate(self) -> int:
        return self._DEFAULT_SAMPLE_RATE

    @property
    def supported_languages(self) -> list[str]:
        return ["th", "en"]

    # -- reference handling (a hook, so a Ray batch prepares every item) ----
    def _prepare_generate_kwargs(self, text: str, kw: dict) -> dict:
        audio = kw.get("ref_audio")
        if not isinstance(audio, str) or not audio:
            return kw  # the sidecar's sample voice
        from services.tts_backend import best_reference_window, reference_duration_s

        state = self._ref_state()
        duration = reference_duration_s(audio)
        if duration is not None and duration > self.max_ref_seconds:
            # A whole-clip transcript cannot be aligned with a window of it.
            selected = best_reference_window(audio, self.max_ref_seconds)
            if selected is None:
                raise RuntimeError(
                    f"F5-TTS-THAI clones from at most {self.max_ref_seconds:.0f} seconds of reference audio. "
                    f"This clip is {duration:.1f} s and no installed speech-to-text model could pick and "
                    "transcribe a passage of it: install one in Settings → Models, or use a 2-8 s clip "
                    "with its transcript."
                )
            state["passages"].append(selected[0])
            kw["ref_audio"], kw["ref_text"] = selected
            return kw
        if not (kw.get("ref_text") or "").strip():
            if audio not in state["texts"]:
                state["texts"][audio] = self._transcribe_reference(audio)
            if not state["texts"][audio]:
                raise RuntimeError(
                    "F5-TTS-THAI needs the words spoken in the reference clip. Type its transcript, "
                    "or install a speech-to-text model in Settings → Models so VoiceStudio can transcribe it."
                )
            kw["ref_text"] = state["texts"][audio]
        return kw

    @staticmethod
    def _transcribe_reference(audio: str):
        try:
            from services.asr_backend import transcribe_reference

            return (transcribe_reference(audio) or "").strip() or None
        except Exception:  # noqa: BLE001 - reported as a missing transcript
            logger.warning("reference transcript resolution failed")
            return None


__all__ = ["ENGINE_ID", "F5TTSThaiBackend", "REMOTE_ONLY_REASON"]
