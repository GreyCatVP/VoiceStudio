"""A sidecar that crashes natively during its cold load is respawned once.

On Windows a torch sidecar loading its model while another app (ComfyUI) loads
multi-GB models can die with 0xC0000005 in torch_cpu.dll / c10.dll: no Python
traceback, just EOF. Every request then failed with a bare "sidecar closed pipe
mid-generate". The request had produced nothing yet, so it is replayed once on
a fresh sidecar, and the error now names the native crash when it repeats.
"""
from __future__ import annotations

import base64
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.subprocess_backend import SubprocessBackend  # noqa: E402

ACCESS_VIOLATION = 0xC0000005  # what Popen.poll() returns on Windows


class _Backend(SubprocessBackend):
    id = "plain"
    cold_load_crash_retry_delay_s = 0.0

    @classmethod
    def is_available(cls):
        return True, "ok"

    @property
    def sample_rate(self):
        return 24000

    @property
    def supported_languages(self):
        return ["multi"]


class _Proc:
    def __init__(self, exit_code):
        self.exit_code = exit_code
        self.dead = False

    def poll(self):
        return self.exit_code if self.dead else None


def _audio_frame():
    pcm = (np.zeros(240, dtype="<i2")).tobytes()
    return {"op": "audio", "audio_pcm_b64": base64.b64encode(pcm).decode(),
            "audio_format": "s16le", "sample_rate": 24000, "n_samples": 240}


def _wire(monkeypatch, backend, script, exit_code=ACCESS_VIOLATION):
    """Each spawn gets a fresh proc; ``script`` lists, per spawn, the frames
    it sends (None = the process dies there)."""
    spawns = []

    def fake_spawn():
        if backend._proc is not None and backend._proc.poll() is None:
            return
        backend._proc = _Proc(exit_code)
        spawns.append(list(script[len(spawns)]))

    def fake_recv(timeout_s):
        backend._last_recv_timed_out = False
        frame = spawns[-1].pop(0)
        if frame is None:
            backend._proc.dead = True
        return frame

    monkeypatch.setattr(backend, "_spawn", fake_spawn)
    monkeypatch.setattr(backend, "_send", lambda msg: None)
    monkeypatch.setattr(backend, "_recv_with_timeout", fake_recv)
    monkeypatch.setattr(backend, "_reap_unusable_process", lambda proc: None)
    return spawns


def test_native_crash_during_cold_load_is_respawned_once(monkeypatch):
    b = _Backend()
    loading = {"op": "progress", "stage": "loading_model", "percent": 0}
    spawns = _wire(monkeypatch, b, [[loading, None], [loading, _audio_frame()]])

    wav = b.generate("hello")

    assert len(spawns) == 2
    assert wav.shape == (1, 240)
    b._proc = None


def test_repeated_cold_load_crash_names_the_native_crash(monkeypatch):
    b = _Backend()
    loading = {"op": "progress", "stage": "loading_model", "percent": 0}
    spawns = _wire(monkeypatch, b, [[loading, None], [loading, None], [_audio_frame()]])

    with pytest.raises(RuntimeError) as exc:
        b.generate("hello")

    assert len(spawns) == 2  # one replay, not a loop
    message = str(exc.value)
    assert "sidecar closed pipe mid-generate" in message  # callers match on it
    assert "0xC0000005" in message and "access violation" in message
    b._proc = None


def test_crash_after_generating_started_is_not_replayed(monkeypatch):
    b = _Backend()
    generating = {"op": "progress", "stage": "generating", "percent": 5}
    spawns = _wire(monkeypatch, b, [[generating, None], [_audio_frame()]])

    with pytest.raises(RuntimeError, match="closed pipe mid-generate"):
        b.generate("hello")
    assert len(spawns) == 1
    b._proc = None


def test_clean_exit_is_not_replayed(monkeypatch):
    b = _Backend()
    spawns = _wire(monkeypatch, b, [[None], [_audio_frame()]], exit_code=0)

    with pytest.raises(RuntimeError, match="closed pipe mid-generate"):
        b.generate("hello")
    assert len(spawns) == 1
    b._proc = None
