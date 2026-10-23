"""Batch dub "Preserve background audio" mixes over the separated background.

Batch used to lay the dub over the video's full original audio (speech
included). It now runs the dub ingest's Demucs step (``separate_stems``: Ray
when routed, else the local CLI) and mixes over the background stem, falling
back — with a job warning — to the full audio when separation fails.
"""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import pytest

from test_dub_batch_engine_selection import (  # noqa: F401 — pytest fixtures
    batch_job_env,
    fake_registry,
    no_omnivoice_model_manager,
)


@pytest.fixture
def env(batch_job_env, fake_registry, no_omnivoice_model_manager, monkeypatch):
    b, make_job = batch_job_env
    fake = fake_registry("fake-batch-sep", supports_cloning=False)
    monkeypatch.setenv("OMNIVOICE_TTS_BACKEND", "fake-batch-sep")
    commands: list[list[str]] = []
    import subprocess

    inner = subprocess.run

    def _recording_run(cmd, *a, **kw):
        commands.append([str(c) for c in cmd])
        return inner(cmd, *a, **kw)

    monkeypatch.setattr("subprocess.run", _recording_run)
    return b, make_job, fake, commands


def _mix_command(commands):
    return next(c for c in reversed(commands) if c[-1].endswith("output_en.mp4"))


def test_mix_uses_the_background_stem(env, monkeypatch):
    b, make_job, fake, commands = env
    job = make_job("jobSep")
    seen = []

    async def _fake_separate(job_id, src, work_dir, vocals_path, no_vocals_path):
        yield 50
        seen.append(dict(job["progress"]))
        open(vocals_path, "wb").close()
        open(no_vocals_path, "wb").close()

    monkeypatch.setattr("services.dub_pipeline.separate_stems", _fake_separate)
    asyncio.run(b._run_batch_pipeline("jobSep", job))

    assert seen[0]["stage"] == "separate" and seen[0]["percent"] == 32
    mix = _mix_command(commands)
    inputs = [mix[i + 1] for i, a in enumerate(mix) if a == "-i"]
    assert inputs[2].endswith("no_vocals.wav")  # third input = 2:a
    graph = mix[mix.index("-filter_complex") + 1]
    assert "[2:a]" in graph and "[0:a]" not in graph
    assert not job.get("warnings")
    assert "en" in job["outputs"]


def test_failed_separation_falls_back_with_a_warning(env, monkeypatch):
    b, make_job, fake, commands = env
    job = make_job("jobNoSep")

    async def _no_demucs(*a, **kw):
        raise RuntimeError("No module named demucs")
        yield  # pragma: no cover — makes this an async generator

    monkeypatch.setattr("services.dub_pipeline.separate_stems", _no_demucs)
    asyncio.run(b._run_batch_pipeline("jobNoSep", job))

    assert job["warnings"] == [
        f"{b.SEPARATION_FALLBACK_WARNING} (No module named demucs)"
    ]
    mix = _mix_command(commands)
    assert not any(a.endswith("no_vocals.wav") for a in mix)
    assert "[0:a]" in mix[mix.index("-filter_complex") + 1]
    assert "en" in job["outputs"]


def test_ray_route_runs_separate_on_ray(env, monkeypatch, tmp_path):
    b, make_job, fake, commands = env
    job = make_job("jobRay")
    batch_dir = tmp_path / "batch" / "jobRay"
    batch_dir.mkdir(parents=True)
    (batch_dir / "audio.wav").write_bytes(b"RIFF")  # extraction is faked
    cfg = object()
    calls = []

    def _fake_on_ray(ray_cfg, src, vocals_out, bed_out, *, on_progress=None, cancelled=None):
        calls.append((ray_cfg, src))
        on_progress(0.5)
        open(vocals_out, "wb").close()
        open(bed_out, "wb").close()

    monkeypatch.setattr(
        "services.ray_jobs.settings.route_for",
        lambda engine: cfg if engine == "demucs" else None,
    )
    monkeypatch.setattr("services.ray_jobs.separation.separate_on_ray", _fake_on_ray)
    asyncio.run(b._run_batch_pipeline("jobRay", job))

    assert calls == [(cfg, str(batch_dir / "audio.wav"))]
    assert any(a.endswith("no_vocals.wav") for a in _mix_command(commands))
    assert not job.get("warnings")


def test_cancel_during_separation_stops_it(env, monkeypatch):
    b, make_job, fake, commands = env
    job = make_job("jobCancel")
    stopped = []

    async def _slow_separate(*a, **kw):
        job["status"] = "cancelled"  # the cancel endpoint only flips this
        try:
            yield 10
            await asyncio.sleep(3600)
        finally:
            stopped.append(True)

    monkeypatch.setattr("services.dub_pipeline.separate_stems", _slow_separate)
    asyncio.run(asyncio.wait_for(b._run_batch_pipeline("jobCancel", job), 10))

    assert stopped == [True]
    assert not fake.calls  # never reached TTS
    assert not any(c[-1].endswith(".mp4") for c in commands)
    assert not job.get("warnings")


def test_progress_is_weighted_by_stage():
    from api.routers.batch import _overall_percent

    one = {"langs": ["th"], "preserve_bg": True}
    steps = [
        ("extract", 0), ("extract", 1), ("transcribe", 1), ("separate", 0.5),
        ("separate", 1), ("translate", 0), ("generate", 0.5), ("mix", 0), ("mix", 1),
    ]
    values = [_overall_percent(one, s, f) for s, f in steps]
    assert values == sorted(values)
    assert values[2] == 25 and values[-1] == 100
    assert 0 < _overall_percent(one, "generate", 0.5) < 100  # one language still moves

    no_bg = {"langs": ["th"], "preserve_bg": False}
    assert _overall_percent(no_bg, "translate", 0) == 25  # no separation slice

    two = {"langs": ["th", "en"], "preserve_bg": True}
    assert _overall_percent(two, "mix", 1, lang_idx=0) == 70
    assert _overall_percent(two, "translate", 0, lang_idx=1) == 70
    assert _overall_percent(two, "mix", 1, lang_idx=1) == 100
