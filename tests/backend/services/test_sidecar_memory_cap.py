"""Memory-cap sidecar recycling.

A long-running sidecar can grow its host memory until the OS commit limit is
reached. With a cap set, the reaper tick shuts down a sidecar at or above it
and the next request respawns one. These tests drive the stdlib-only echo
sidecar (no torch) and assert the recycler (a) measures a live sidecar,
(b) recycles one over the cap and a fresh one respawns, (c) never touches one
with an op in flight, and (d) leaves sidecars alone when disabled or under cap.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from services.subprocess_backend import (
    SubprocessBackend,
    _sidecar_memory_mb,
    recycle_oversized_sidecars,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ECHO_SCRIPT = REPO_ROOT / "backend" / "engines" / "_echo" / "main.py"


class EchoBackend(SubprocessBackend):
    id = "_echo_memcap"
    display_name = "Echo (memory cap test)"
    sample_rate = 24000
    supported_languages = ["en"]

    @classmethod
    def is_available(cls):
        return (True, "ready") if ECHO_SCRIPT.is_file() else (False, "missing")

    @classmethod
    def venv_python(cls):
        return Path(sys.executable)

    @classmethod
    def sidecar_script(cls):
        return ECHO_SCRIPT


@pytest.fixture
def echo():
    b = EchoBackend()
    yield b
    try:
        b.shutdown()
    except Exception:
        pass


def _spawn_alive(b: EchoBackend) -> None:
    ok, _ = b.health_check()
    assert ok
    assert b._proc is not None and b._proc.poll() is None


def _alive(b: EchoBackend) -> bool:
    return b._proc is not None and b._proc.poll() is None


def test_measures_live_sidecar(echo):
    _spawn_alive(echo)
    assert _sidecar_memory_mb(echo._proc) > 0


def test_unknown_process_measures_zero():
    assert _sidecar_memory_mb(None) == 0.0


def test_recycles_sidecar_over_cap_then_respawns(echo):
    _spawn_alive(echo)
    pid = echo._proc.pid

    assert recycle_oversized_sidecars(max_mb=1.0) >= 1
    assert not _alive(echo)

    ok, _ = echo.health_check()
    assert ok
    assert _alive(echo) and echo._proc.pid != pid


def test_skips_busy_sidecar(echo):
    _spawn_alive(echo)
    assert echo._lock.acquire(blocking=False)
    try:
        recycle_oversized_sidecars(max_mb=1.0)
        assert _alive(echo)
    finally:
        echo._lock.release()


def test_under_cap_is_left_alone(echo):
    _spawn_alive(echo)
    recycle_oversized_sidecars(max_mb=1_000_000.0)
    assert _alive(echo)


def test_disabled_at_nonpositive_cap(echo):
    _spawn_alive(echo)
    assert recycle_oversized_sidecars(max_mb=0) == 0
    assert recycle_oversized_sidecars(max_mb=-1) == 0
    assert _alive(echo)
