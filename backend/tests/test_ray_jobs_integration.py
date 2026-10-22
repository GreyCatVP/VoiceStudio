"""Remote execution against a real Ray head or a real Modal account (opt-in).

Runs only when VS_RAY_TEST_URL points at a dashboard, e.g.

    VS_RAY_TEST_URL=http://127.0.0.1:8265 VS_RAY_TEST_TOKEN=... pytest backend/tests/test_ray_jobs_integration.py

or, for Modal (bills the account; the engine tests then run in Modal sandboxes):

    VS_MODAL_TEST=1 VS_MODAL_TOKEN_ID=ak-... VS_MODAL_TOKEN_SECRET=as-... VS_MODAL_GPU=L4 pytest ...

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
MODAL = os.environ.get("VS_MODAL_TEST") == "1"
pytestmark = pytest.mark.skipif(not (URL or MODAL), reason="VS_RAY_TEST_URL / VS_MODAL_TEST not set")
ray_only = pytest.mark.skipif(MODAL, reason="talks to the Ray dashboard directly")


@pytest.fixture(autouse=True)
def _modal_provider(monkeypatch):
    """With VS_MODAL_TEST=1 the engine tests' Ray settings become Modal ones."""
    if not MODAL:
        return
    from services.ray_jobs import settings as ray_settings

    real = ray_settings.save

    def save(changes):
        changes = {k: v for k, v in changes.items() if k not in ("dashboard_url", "auth_token")}
        changes.update(provider="modal", modal_gpu=os.environ.get("VS_MODAL_GPU", "L4"),
                       modal_token_id=os.environ["VS_MODAL_TOKEN_ID"],
                       modal_token_secret=os.environ["VS_MODAL_TOKEN_SECRET"])
        return real(changes)

    monkeypatch.setattr(ray_settings, "save", save)


def _client():
    return RayJobsClient(URL, RayAuth(ray_token=os.environ.get("VS_RAY_TEST_TOKEN") or None))


@ray_only
def test_cluster_is_reachable_and_authenticated():
    async def go():
        async with _client() as c:
            return await c.version(), await c.cluster_metadata()

    version, meta = asyncio.run(go())
    assert version["ray_version"] and meta["pythonVersion"]


@ray_only
def test_probe_job_describes_the_node():
    async def go():
        async with _client() as c:
            ex = RayJobsExecutor(c, poll_interval=0.5)
            res = await ex.run(RayTask(op="probe"), timeout=180)
            await ex.drain(timeout=60)
            return res

    res = asyncio.run(go())
    assert res.result["node"]["python"]


@ray_only
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


@ray_only
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


@pytest.mark.skipif("nllb" not in ENGINES, reason="set VS_RAY_TEST_ENGINES=nllb (downloads ~2.5 GB on the cluster)")
def test_nllb_translates_a_dub_in_one_cluster_job():
    from types import SimpleNamespace
    from api.routers.dub_translate import _translate_nllb_on_ray
    from core.db import init_db
    from services.ray_jobs import runtime
    from services.ray_jobs import settings as ray_settings

    init_db()
    runtime.reopen_for_tests()
    ray_settings.save({"enabled": True, "dashboard_url": URL, "engines": ["nllb"],
                       "num_gpus": float(os.environ.get("VS_RAY_TEST_NUM_GPUS", "0")),
                       "auth_token": os.environ.get("VS_RAY_TEST_TOKEN") or ""})
    try:
        seg = lambda i, t: SimpleNamespace(id=i, text=t, target_lang=None)
        rows = [(0, seg(0, "Good morning, my friend."), "tha_Thai"), (1, seg(1, "  "), "tha_Thai"),
                (2, seg(2, "The weather is beautiful today."), "fra_Latn")]
        out = _translate_nllb_on_ray(ray_settings.load(), rows, "eng_Latn", {})
        print("nllb:", out)
        assert [r["id"] for r in out] == [0, 1, 2] and out[1]["text"] == "  "
        assert not any(r.get("error") for r in out)
        assert any("฀" <= ch <= "๿" for ch in out[0]["text"])  # Thai script
        assert "beau" in out[2]["text"].lower() or "temps" in out[2]["text"].lower()
    finally:
        ray_settings.save({"enabled": False, "auth_token": ""})
        runtime.shutdown()
        runtime.reopen_for_tests()


@pytest.mark.skipif("demucs" not in ENGINES, reason="set VS_RAY_TEST_ENGINES=demucs")
def test_demucs_separates_speech_from_music_across_windows(tmp_path, monkeypatch):
    import numpy as np
    import soundfile as sf
    from core.db import init_db
    from services.ray_jobs import runtime, separation
    from services.ray_jobs import settings as ray_settings

    speech_src = os.environ.get("VS_RAY_TEST_SPEECH")
    if not speech_src or not os.path.exists(speech_src):
        pytest.skip("set VS_RAY_TEST_SPEECH to a speech WAV")
    monkeypatch.setattr(separation, "WINDOW_S", 20.0)  # several windows on a short track
    speech, sr = sf.read(speech_src, dtype="float32", always_2d=True)
    speech = speech.mean(1)
    import torch, torchaudio.functional as AF
    speech = AF.resample(torch.from_numpy(speech), sr, 44100).numpy()
    total = 45 * 44100
    voice = np.zeros(total, dtype=np.float32)
    for start in range(0, total - len(speech), len(speech) + 44100):
        voice[start:start + len(speech)] = speech
    t = np.arange(total) / 44100
    music = 0.15 * (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 277.2 * t) + np.sin(2 * np.pi * 329.6 * t)) / 3
    mix = np.stack([voice + music, voice + music], axis=1).astype(np.float32)
    src = tmp_path / "mix.wav"
    sf.write(src, mix, 44100)

    init_db()
    runtime.reopen_for_tests()
    ray_settings.save({"enabled": True, "dashboard_url": URL, "engines": ["demucs"],
                       "num_gpus": float(os.environ.get("VS_RAY_TEST_NUM_GPUS", "0")),
                       "auth_token": os.environ.get("VS_RAY_TEST_TOKEN") or ""})
    seen = []
    try:
        started = time.monotonic()
        separation.separate_on_ray(ray_settings.load(), str(src), str(tmp_path / "v.wav"), str(tmp_path / "b.wav"),
                                   on_progress=seen.append)
        took = time.monotonic() - started
        vocals, _ = sf.read(tmp_path / "v.wav", dtype="float32")
        bed, _ = sf.read(tmp_path / "b.wav", dtype="float32", always_2d=True)
        assert vocals.shape == (total, 2) and bed.shape == (total, 2)
        corr = lambda a, b: float(np.corrcoef(a, b)[0, 1])
        print(f"demucs: {took:.0f}s; corr(vocals.mean(1), voice)={corr(vocals.mean(1), voice):.2f} corr(bed, music)={corr(bed.mean(1), music):.2f}")
        assert corr(vocals.mean(1), voice) > 0.8 and corr(bed.mean(1), music) > 0.8
        assert seen and seen[-1] == 1.0
    finally:
        ray_settings.save({"enabled": False, "auth_token": ""})
        runtime.shutdown()
        runtime.reopen_for_tests()


@pytest.mark.skipif("pyannote" not in ENGINES or "supertonic3" not in ENGINES,
                    reason="set VS_RAY_TEST_ENGINES=supertonic3,pyannote and VS_RAY_TEST_PYANNOTE_DIR")
def test_pyannote_tells_two_speakers_apart_on_the_cluster(tmp_path, monkeypatch):
    """Two Supertonic-3 voices take turns; diarization on the cluster with the
    checkpoints shipped from this machine (never a token)."""
    import numpy as np
    import soundfile as sf
    from core.db import init_db
    from engines.supertonic3.backend import Supertonic3Backend
    from services.ray_jobs import diarization, runtime
    from services.ray_jobs import settings as ray_settings

    bundle_dir = os.environ.get("VS_RAY_TEST_PYANNOTE_DIR")
    if not bundle_dir:
        pytest.skip("set VS_RAY_TEST_PYANNOTE_DIR (config.yaml, segmentation.bin, embedding.bin)")
    read = lambda n: open(os.path.join(bundle_dir, n), "rb").read()
    monkeypatch.setattr(diarization, "_local_bundle", lambda: {
        "config_path.yaml": read("config.yaml"), "segmentation_path.bin": read("segmentation.bin"),
        "embedding_path.bin": read("embedding.bin")})
    init_db()
    runtime.reopen_for_tests()
    ray_settings.save({"enabled": True, "dashboard_url": URL, "engines": ["supertonic3", "pyannote"],
                       "num_gpus": float(os.environ.get("VS_RAY_TEST_NUM_GPUS", "0")),
                       "auth_token": os.environ.get("VS_RAY_TEST_TOKEN") or ""})
    try:
        tts = Supertonic3Backend()
        lines = [("M1", "Good morning. Did you see the report I sent yesterday afternoon?"),
                 ("F1", "Yes, I read it last night. The numbers look much better than last quarter."),
                 ("M1", "That is what I thought too. Should we present it to the team on Friday?"),
                 ("F1", "Friday works for me. I will prepare the slides and send you a draft tomorrow.")]
        sr = tts.sample_rate
        parts, truth, t = [], [], 0.0
        for voice, text in lines:
            audio = tts.generate(text, language="en", voice=voice)[0].numpy()
            parts += [audio, np.zeros(int(0.6 * sr), dtype=np.float32)]
            truth.append((t, t + len(audio) / sr, voice))
            t += len(audio) / sr + 0.6
        path = tmp_path / "dialogue.wav"
        sf.write(path, np.concatenate(parts), sr)
        phrases = [{"start": s, "end": e, "text": "x"} for s, e, _ in truth]
        pipe = diarization.RayPyannotePipeline(ray_settings.load(), phrases=phrases)
        started = time.monotonic()
        # A 20 s synthetic dialogue is below pyannote's cluster-size floor
        # (it often collapses to one speaker unprompted; the app's phrase
        # recovery handles that): ask for two, as a user hint would.
        annotation = pipe(str(path), num_speakers=2)
        took = time.monotonic() - started
        labels = annotation.labels()
        print(f"pyannote: {took:.0f}s, speakers {labels}")
        assert len(labels) == 2
        # The phrase embeddings separate the voices: same-voice phrases are
        # closer than cross-voice ones (what the recovery clusters on).
        vecs = [pipe.phrase_embedding(s, e) for s, e, _ in truth]
        unit = [v / np.linalg.norm(v) for v in vecs]
        same = (float(unit[0] @ unit[2]) + float(unit[1] @ unit[3])) / 2
        cross = (float(unit[0] @ unit[1]) + float(unit[2] @ unit[3])) / 2
        print(f"embedding similarity: same voice {same:.2f}, cross voice {cross:.2f}")
        # (synthetic voices vary run to run; printed for the record only)
        # Parity: the cluster's result is the pipeline the app runs locally,
        # same checkpoints, same audio (16 kHz mono) -> the same diarization.
        import torch, yaml
        from pyannote.audio import Pipeline
        from services.asr_backend import WhisperXBackend
        from services.model_manager import _ensure_pyannote_hf_token_compat
        _ensure_pyannote_hf_token_compat()
        WhisperXBackend._allow_vad_pickle_globals()
        config = yaml.safe_load(open(os.path.join(bundle_dir, "config.yaml")))
        config["pipeline"]["params"]["segmentation"] = os.path.join(bundle_dir, "segmentation.bin")
        config["pipeline"]["params"]["embedding"] = os.path.join(bundle_dir, "embedding.bin")
        local_cfg = tmp_path / "pipeline.yaml"
        local_cfg.write_text(yaml.safe_dump(config))
        flac, _ = diarization._flac_16k_mono(str(path))
        import io as _io
        wav16, sr16 = sf.read(_io.BytesIO(flac), dtype="float32", always_2d=True)
        local = Pipeline.from_pretrained(str(local_cfg))(
            {"waveform": torch.from_numpy(wav16.T.copy()), "sample_rate": sr16}, num_speakers=2)
        from pyannote.metrics.diarization import DiarizationErrorRate
        der = DiarizationErrorRate()(local, annotation)
        print(f"DER(cluster vs local) = {der:.3f}")
        assert der < 0.02
        assert all(pipe.phrase_embedding(s, e) is not None for s, e, _ in truth)
    finally:
        ray_settings.save({"enabled": False, "auth_token": ""})
        runtime.shutdown()
        runtime.reopen_for_tests()


@pytest.mark.skipif("omnivoice" not in ENGINES, reason="set VS_RAY_TEST_ENGINES=omnivoice (downloads the OmniVoice checkpoint)")
def test_omnivoice_synthesizes_on_the_cluster(monkeypatch):
    """VoiceStudio's own engine through the routed class (as on MPS)."""
    monkeypatch.setenv("OMNIVOICE_MODEL", "k2-fsa/OmniVoice")
    from core.db import init_db
    from services.ray_jobs import runtime
    from services.ray_jobs import settings as ray_settings
    from services.tts_backend import get_backend_class

    init_db()
    runtime.reopen_for_tests()
    ray_settings.save({"enabled": True, "dashboard_url": URL, "engines": ["omnivoice"],
                       "num_gpus": float(os.environ.get("VS_RAY_TEST_NUM_GPUS", "0")),
                       "auth_token": os.environ.get("VS_RAY_TEST_TOKEN") or ""})
    try:
        cls = get_backend_class("omnivoice")
        assert cls.__name__ == "OmniVoiceMPSSubprocessBackend"
        backend = cls()
        started = time.monotonic()
        backend.ensure_ready()
        install = time.monotonic() - started
        started = time.monotonic()
        audio = backend.generate("Hello from VoiceStudio on the Ray cluster.", language="en")
        took = time.monotonic() - started
        secs = audio.shape[-1] / backend.sample_rate
        print(f"omnivoice: install {install:.0f}s, generate {took:.0f}s, {secs:.2f}s of audio")
        assert 0.5 < secs < 30 and float(audio.abs().max()) > 0.01
    finally:
        ray_settings.save({"enabled": False, "auth_token": ""})
        runtime.shutdown()
        runtime.reopen_for_tests()
