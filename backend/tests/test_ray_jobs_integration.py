"""Ray Jobs executor against a real Ray head (opt-in).

Runs only when VS_RAY_TEST_URL points at a dashboard, e.g.

    VS_RAY_TEST_URL=http://127.0.0.1:8265 VS_RAY_TEST_TOKEN=... pytest backend/tests/test_ray_jobs_integration.py

The process-teardown check additionally needs the head on this machine.
"""
import asyncio
import os
import re
import time
from urllib.parse import urlparse

import pytest

from services.ray_jobs import RayAuth, RayJobsClient, RayJobsExecutor, RayTask

URL = os.environ.get("VS_RAY_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="VS_RAY_TEST_URL not set")


def _client():
    return RayJobsClient(URL, RayAuth(ray_token=os.environ.get("VS_RAY_TEST_TOKEN") or None))


def test_cluster_is_reachable_and_authenticated():
    async def go():
        async with _client() as c:
            return await c.version(), await c.cluster_metadata()

    version, meta = asyncio.run(go())
    assert version["ray_version"] and meta["pythonVersion"]


def test_probe_job_describes_the_node():
    async def go():
        async with _client() as c:
            ex = RayJobsExecutor(c, poll_interval=0.5)
            res = await ex.run(RayTask(op="probe"), timeout=180)
            await ex.drain(timeout=60)
            return res

    res = asyncio.run(go())
    assert res.result["node"]["python"]


def test_echo_synthesis_round_trip_through_a_real_job():
    async def go():
        async with _client() as c:
            ex = RayJobsExecutor(c, poll_interval=0.5)
            stages = []
            res = await ex.run(RayTask(op="synthesize", engine="_echo", params={"text": "hi", "sample_rate": 22050}),
                               timeout=180, on_progress=lambda e: stages.append(e["stage"]))
            await ex.drain(timeout=60)  # deletion waits out the supervisor's exit
            jobs = {j.get("submission_id"): j.get("status") for j in await c.list_jobs()}
            return res, stages, jobs

    res, stages, jobs = asyncio.run(go())
    assert res.result["op"] == "audio" and res.result["n_samples"] == 22050
    assert "engine_ready" in stages
    assert res.submission_id not in jobs  # deleted after success
    # ...without Ray writing it back as a ghost "supervisor actor died" job
    assert not any(sid.startswith("vs-echo-") and st == "FAILED" for sid, st in jobs.items() if sid == res.submission_id)


@pytest.mark.skipif(not URL or urlparse(URL or "").hostname not in {"127.0.0.1", "localhost"},
                    reason="needs the Ray head on this machine to inspect processes")
def test_cancel_stops_the_job_and_kills_the_engine_process():
    async def go():
        async with _client() as c:
            ex = RayJobsExecutor(c, poll_interval=0.5, keep_failed_jobs=False)
            task = asyncio.create_task(ex.run(RayTask(op="_hold", engine="_echo", test_mode=True,
                                                      params={"seconds": 300})))
            pid = None
            deadline = time.monotonic() + 120
            while pid is None and time.monotonic() < deadline:
                await asyncio.sleep(1)
                for job in await c.list_jobs():
                    sid = job.get("submission_id") or ""
                    if sid.startswith("vs-echo-") and job.get("status") == "RUNNING":
                        m = re.search(r"holding sidecar pid (\d+)", await c.job_logs(sid))
                        if m:
                            pid = int(m.group(1))
            assert pid, "engine sidecar never started"
            assert os.path.exists(f"/proc/{pid}")
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await ex.drain(timeout=60)
            return pid

    pid = asyncio.run(go())
    deadline = time.monotonic() + 30
    while os.path.exists(f"/proc/{pid}") and time.monotonic() < deadline:
        time.sleep(0.5)
    assert not os.path.exists(f"/proc/{pid}"), f"engine pid {pid} survived the job stop"


ENGINES = set(filter(None, os.environ.get("VS_RAY_TEST_ENGINES", "").split(",")))


@pytest.mark.skipif("supertonic3" not in ENGINES,
                    reason="set VS_RAY_TEST_ENGINES=supertonic3 (installs ~1 GB on the cluster)")
def test_supertonic3_installs_and_synthesizes_on_the_cluster():
    """Real engine, real cluster: venv install via uv, weights download, speech."""
    from core.db import init_db
    from engines.supertonic3.backend import Supertonic3Backend
    from services.ray_jobs import runtime
    from services.ray_jobs import settings as ray_settings

    init_db()
    ray_settings.save({"enabled": True, "dashboard_url": URL, "engines": ["supertonic3"],
                       "auth_token": os.environ.get("VS_RAY_TEST_TOKEN") or "",
                       "keep_failed_jobs": True})
    try:
        backend = Supertonic3Backend()
        started = time.monotonic()
        backend.ensure_ready()  # install job
        install_s = time.monotonic() - started
        audio = backend.generate("Hello from the Ray cluster.", lang="en")
        assert audio.ndim == 2 and audio.shape[0] == 1
        seconds = audio.shape[1] / backend.sample_rate
        assert 0.5 < seconds < 20, seconds
        assert float(audio.abs().max()) > 0.01  # not silence
        print(f"install {install_s:.0f}s, {seconds:.2f}s of audio")
    finally:
        ray_settings.save({"enabled": False, "auth_token": ""})
        runtime.shutdown()


@pytest.mark.skipif("supertonic3" not in ENGINES, reason="set VS_RAY_TEST_ENGINES=supertonic3")
def test_supertonic3_batch_renders_many_sentences_in_one_job(monkeypatch):
    from core.db import init_db
    from engines.supertonic3.backend import Supertonic3Backend
    from services import subprocess_backend as sb
    from services.ray_jobs import runtime
    from services.ray_jobs import settings as ray_settings

    init_db()
    runtime.reopen_for_tests()
    ray_settings.save({"enabled": True, "dashboard_url": URL, "engines": ["supertonic3"],
                       "auth_token": os.environ.get("VS_RAY_TEST_TOKEN") or ""})
    jobs = []
    real = sb.SubprocessBackend._run_ray_job

    def counting(self, cfg, task, **kw):
        jobs.append(task.op)
        return real(self, cfg, task, **kw)

    monkeypatch.setattr(sb.SubprocessBackend, "_run_ray_job", counting)
    try:
        backend = Supertonic3Backend()
        assert backend.has_native_batch
        texts = ["The first sentence.", "A second one, a little longer.", "And the third."]
        started = time.monotonic()
        out = backend.generate_batch(texts, language="en")
        took = time.monotonic() - started
        assert jobs == ["batch"]  # one job for all three
        assert len(out) == 3 and all(float(a.abs().max()) > 0.01 for a in out)
        print(f"3 sentences in one job: {took:.1f}s")
    finally:
        ray_settings.save({"enabled": False, "auth_token": ""})
        runtime.shutdown()
        runtime.reopen_for_tests()


@pytest.mark.skipif("moss-tts-nano" not in ENGINES,
                    reason="set VS_RAY_TEST_ENGINES=moss-tts-nano (source install, several GB)")
def test_moss_tts_nano_installs_from_source_and_synthesizes_on_the_cluster():
    """A source-checkout engine end to end: GitHub archive, editable install
    into a node venv, env var pointing at the node checkout, speech out."""
    from core.db import init_db
    from engines.moss_tts_nano_subprocess import MossTTSNanoSubprocessBackend
    from services.ray_jobs import runtime
    from services.ray_jobs import settings as ray_settings

    init_db()
    runtime.reopen_for_tests()
    ray_settings.save({"enabled": True, "dashboard_url": URL, "engines": ["moss-tts-nano"],
                       # A CPU-only test head: GPU share 0 runs the engine on CPU.
                       "num_gpus": float(os.environ.get("VS_RAY_TEST_NUM_GPUS", "0")),
                       "auth_token": os.environ.get("VS_RAY_TEST_TOKEN") or ""})
    try:
        ok, why = MossTTSNanoSubprocessBackend.is_available()
        assert ok, why
        backend = MossTTSNanoSubprocessBackend()
        started = time.monotonic()
        backend.ensure_ready()
        install_s = time.monotonic() - started
        audio = backend.generate("Hello from a source checkout on the Ray cluster.", language="en")
        assert audio.ndim == 2 and float(audio.abs().max()) > 0.01
        print(f"moss-tts-nano: install {install_s:.0f}s, {audio.shape[1] / backend.sample_rate:.2f}s of audio")
    finally:
        ray_settings.save({"enabled": False, "auth_token": ""})
        runtime.shutdown()
        runtime.reopen_for_tests()


@pytest.mark.skipif("faster-whisper-isolated" not in ENGINES or "supertonic3" not in ENGINES,
                    reason="set VS_RAY_TEST_ENGINES=supertonic3,faster-whisper-isolated")
def test_speech_round_trip_tts_then_asr_on_the_cluster(tmp_path, monkeypatch):
    """Supertonic-3 speaks on the cluster, faster-whisper (tiny, CPU) transcribes
    it on the cluster: both directions, one warm-up, batched transcription."""
    import soundfile as sf
    import torchaudio.functional as AF
    from core.db import init_db
    from engines.supertonic3.backend import Supertonic3Backend
    from services.ray_jobs import runtime
    from services.ray_jobs import settings as ray_settings
    from services.subprocess_asr import IsolatedFasterWhisperBackend

    monkeypatch.setenv("ASR_MODEL_FW", "tiny")
    init_db()
    runtime.reopen_for_tests()
    ray_settings.save({"enabled": True, "dashboard_url": URL,
                       "engines": ["supertonic3", "faster-whisper-isolated"],
                       "num_gpus": float(os.environ.get("VS_RAY_TEST_NUM_GPUS", "0")),
                       "auth_token": os.environ.get("VS_RAY_TEST_TOKEN") or ""})
    try:
        tts = Supertonic3Backend()
        clips = []
        for i, text in enumerate(["Hello world, this is a test.", "Good morning everyone."]):
            audio = tts.generate(text, language="en")
            wav = AF.resample(audio, tts.sample_rate, 16000)[0].numpy()
            path = tmp_path / f"clip{i}.wav"
            sf.write(path, wav, 16000)
            clips.append(str(path))
        asr = IsolatedFasterWhisperBackend()
        assert type(asr).is_available()[0]
        started = time.monotonic()
        asr.ensure_loaded()  # install + weights warm-up
        warm_s = time.monotonic() - started
        results = asr.transcribe_many(clips, word_timestamps=True)
        texts = [" ".join(c["text"] for c in r["chunks"]).lower() for r in results]
        print(f"asr warm-up {warm_s:.0f}s; transcripts: {texts}")
        assert "hello" in texts[0] and "world" in texts[0]
        assert "morning" in texts[1]
    finally:
        ray_settings.save({"enabled": False, "auth_token": ""})
        runtime.shutdown()
        runtime.reopen_for_tests()
