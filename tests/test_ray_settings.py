"""Ray execution settings, routes, and the SubprocessBackend Ray branch.

settings_store backed by in-memory dicts (house convention, see
test_asr_openai_compat_877.py); the cluster is faked at the HTTP boundary or
at runtime.run_sync, so nothing here needs a Ray head.
"""
from __future__ import annotations

import asyncio
import base64
import importlib
import json
import os
import sys

import httpx
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")


@pytest.fixture
def ss(monkeypatch):
    from services import settings_store as _ss

    text: dict[str, str] = {}
    secrets: dict[str, str] = {}
    monkeypatch.setattr(_ss, "get_text", lambda k, default=None: text.get(k, default))
    monkeypatch.setattr(_ss, "set_text", lambda k, v: text.__setitem__(k, v))
    monkeypatch.setattr(_ss, "get_secret", lambda n: secrets.get(n))
    monkeypatch.setattr(_ss, "set_secret", lambda n, v: secrets.__setitem__(n, v) if v else secrets.pop(n, None))
    monkeypatch.setattr(_ss, "list_secret_names", lambda: list(secrets))
    monkeypatch.delenv("OMNIVOICE_RAY_DASHBOARD_URL", raising=False)
    monkeypatch.delenv("OMNIVOICE_RAY_AUTH_TOKEN", raising=False)
    _ss._test_text, _ss._test_secrets = text, secrets
    return _ss


@pytest.fixture
def rs(ss):
    return importlib.import_module("services.ray_jobs.settings")


@pytest.fixture
def settings_mod(ss):
    return importlib.import_module("api.routers.settings")


# -- settings service -------------------------------------------------------

def test_ray_is_off_by_default(rs):
    cfg = rs.load()
    assert not cfg.enabled and not cfg.active and cfg.engines == ()
    assert rs.route_for("voxcpm2") is None


def test_save_round_trip_never_exposes_secrets(rs, ss):
    state = rs.save({"enabled": True, "dashboard_url": "https://ray.example.com/", "engines": ["voxcpm2"],
                     "auth_token": "tok-SECRET", "cf_access_client_id": "cid", "cf_access_client_secret": "cf-SECRET",
                     "num_gpus": 0.2, "cache_dir": "/models/vs", "python": "python3"}).public()
    assert state["dashboard_url"] == "https://ray.example.com"
    assert state["has_token"] and state["has_cf_secret"] and state["engines"] == ["voxcpm2"]
    assert state["num_gpus"] == 0.2 and state["cache_dir"] == "/models/vs" and state["python"] == "python3"
    assert "SECRET" not in json.dumps(state)
    assert ss._test_secrets == {"ray_auth_token": "tok-SECRET", "ray_cf_access_client_secret": "cf-SECRET"}
    assert {e["id"] for e in state["available_engines"]} == {
        "supertonic3", "voxcpm2", "moss-tts-nano", "indextts2", "cosyvoice", "confucius4-tts", "moss-tts-v15", "dots-tts",
        "faster-whisper-isolated", "nllb", "demucs", "pyannote", "omnivoice"}
    assert {e["id"]: e["kind"] for e in state["available_engines"]}["faster-whisper-isolated"] == "asr"
    # None leaves a secret alone, '' clears it
    rs.save({"auth_token": None})
    assert rs.load().has_token
    rs.save({"auth_token": ""})
    assert not rs.load().has_token


@pytest.mark.parametrize("url", [
    "http://ray.example.com",           # token would travel in clear text
    "https://user:pw@ray.example.com",  # credentials in the URL
    "https://ray.example.com/api",      # must be the dashboard root
    "https://ray.example.com?x=1",
    "ftp://ray.example.com",
])
def test_unsafe_dashboard_urls_are_refused_and_nothing_is_written(rs, ss, url):
    with pytest.raises(ValueError):
        rs.save({"enabled": True, "dashboard_url": url})
    assert ss._test_text == {}


def test_loopback_dashboard_may_use_http(rs):
    assert rs.save({"dashboard_url": "http://127.0.0.1:8265"}).dashboard_url == "http://127.0.0.1:8265"


@pytest.mark.parametrize("changes", [
    {"engines": ["audiocpp-sortformer"]}, {"engines": ["_echo"]}, {"num_gpus": -1}, {"num_cpus": 1000},
    {"cache_dir": "relative/path"}, {"python": "python; rm -rf /"}, {"auth_token": "bad token"},
])
def test_invalid_fields_are_refused(rs, ss, changes):
    with pytest.raises(ValueError):
        rs.save(changes)
    assert ss._test_text == {} and ss._test_secrets == {}


def test_route_for_requires_enabled_url_and_listed_engine(rs):
    rs.save({"dashboard_url": "https://ray.example.com", "engines": ["voxcpm2"]})
    assert rs.route_for("voxcpm2") is None  # not enabled
    rs.save({"enabled": True})
    assert rs.route_for("voxcpm2") is not None
    assert rs.route_for("supertonic3") is None  # not listed
    assert rs.route_for("audiocpp-sortformer") is None  # a native binary: not on Ray


def test_env_pins_url_and_token(rs, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_RAY_DASHBOARD_URL", "https://pinned.example.com")
    monkeypatch.setenv("OMNIVOICE_RAY_AUTH_TOKEN", "envtok")
    cfg = rs.load()
    assert cfg.dashboard_url == "https://pinned.example.com" and cfg.has_token
    assert set(cfg.env_pinned) == {"dashboard_url", "token"}
    assert rs.auth().headers()["Authorization"] == "Bearer envtok"


# -- routes -----------------------------------------------------------------

def test_routes_get_and_put(settings_mod):
    body = settings_mod._RaySettingsBody(enabled=True, dashboard_url="https://ray.example.com",
                                         engines=["supertonic3"], auth_token="t0k")
    state = settings_mod.set_ray_settings(body)
    assert state["enabled"] and state["has_token"] and "t0k" not in json.dumps(state)
    assert settings_mod.get_ray_settings()["engines"] == ["supertonic3"]


def test_put_rejects_bad_input_with_400(settings_mod):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as info:
        settings_mod.set_ray_settings(settings_mod._RaySettingsBody(dashboard_url="http://ray.example.com"))
    assert info.value.status_code == 400


class _FakeCluster:
    def __init__(self, auth_mode="token"):
        self.auth_mode = auth_mode
        self.stopped = []

    def handler(self, request):
        path = request.url.path
        if path == "/api/version":
            return httpx.Response(200, json={"ray_version": "2.59.0"})
        if path == "/api/authentication_mode":
            return httpx.Response(200, json={"authentication_mode": self.auth_mode})
        if path == "/api/v0/cluster_metadata":
            return httpx.Response(200, json={"data": {"pythonVersion": "3.12.13"}})
        if path == "/api/cluster_status":
            return httpx.Response(200, json={"data": {"clusterStatus": "1 node, 0.0/1.0 GPU"}})
        if path == "/api/jobs/" and request.method == "GET":
            return httpx.Response(200, json=[
                {"submission_id": "vs-voxcpm2-1", "status": "RUNNING", "metadata": {"app": "voicestudio", "engine": "voxcpm2", "op": "synthesize"}, "start_time": 2},
                {"submission_id": "other-1", "status": "RUNNING", "metadata": {}, "start_time": 3},
            ])
        if path.endswith("/stop"):
            self.stopped.append(path.split("/")[3])
            return httpx.Response(200, json={"stopped": True})
        if path.startswith("/api/jobs/"):
            sid = path.split("/")[3]
            return httpx.Response(200, json={"status": "RUNNING", "metadata": {"app": "voicestudio" if sid.startswith("vs-") else "x"}})
        return httpx.Response(404)


@pytest.fixture
def fake_cluster(monkeypatch, rs):
    from services.ray_jobs import client as client_mod, diagnostics

    cluster = _FakeCluster()
    real = client_mod.RayJobsClient

    def factory(base_url, auth=client_mod.RayAuth(), **kw):
        kw["transport"] = httpx.MockTransport(cluster.handler)
        return real(base_url, auth, **kw)

    monkeypatch.setattr(diagnostics, "RayJobsClient", factory)
    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com"})
    return cluster


def test_connection_test_flags_a_cluster_without_authentication(settings_mod, fake_cluster, monkeypatch):
    from services.ray_jobs import diagnostics

    fake_cluster.auth_mode = "disabled"
    monkeypatch.setattr(diagnostics, "test_connection", _no_probe(diagnostics.test_connection))
    out = asyncio.run(settings_mod.test_ray_connection())
    assert out["ok"] and out["ray_version"] == "2.59.0" and out["cluster_python"] == "3.12.13"
    assert "cluster_auth_disabled" in out["warnings"]


def _no_probe(fn):
    async def wrapped(cfg, auth, **kw):
        return await fn(cfg, auth, run_probe=False)
    return wrapped


def test_connection_test_reports_not_configured(settings_mod, rs):
    out = asyncio.run(settings_mod.test_ray_connection())
    assert out == {"ok": False, "kind": "not_configured", "message": "Set the Ray dashboard URL first."}


def test_jobs_list_only_shows_voicestudio_jobs(settings_mod, fake_cluster):
    out = asyncio.run(settings_mod.list_ray_jobs())
    assert [j["submission_id"] for j in out["jobs"]] == ["vs-voxcpm2-1"]


def test_stop_refuses_foreign_or_malformed_job_ids(settings_mod, fake_cluster):
    assert asyncio.run(settings_mod.stop_ray_job("other-1"))["kind"] == "invalid"
    assert asyncio.run(settings_mod.stop_ray_job("../../api/jobs"))["kind"] == "invalid"
    assert asyncio.run(settings_mod.stop_ray_job("vs-voxcpm2-1"))["stopped"] is True
    assert fake_cluster.stopped == ["vs-voxcpm2-1"]


def test_jobs_route_requires_the_admin_credential_even_for_get(settings_mod):
    # It spends the stored cluster credentials; require_admin_action also
    # carries the cross-site GET rejection.
    from api.dependencies import require_admin_action

    route = next(r for r in settings_mod.router.routes if r.path == "/api/settings/ray/jobs")
    assert any(d.call is require_admin_action for d in route.dependant.dependencies)


# -- SubprocessBackend Ray branch --------------------------------------------

def _audio_reply(samples, sample_rate):
    pcm = np.asarray(samples, dtype="<f4").tobytes()
    return {"op": "audio", "audio_pcm_b64": base64.b64encode(pcm).decode(), "audio_format": "f32le",
            "sample_rate": sample_rate}


@pytest.fixture
def ray_backend(rs, monkeypatch):
    from services import subprocess_backend as sb
    from services.ray_jobs import runtime
    from services.ray_jobs.executor import RayJobResult

    class Fake(sb.SubprocessBackend):
        id = "voxcpm2"
        supports_float_transport = True
        sample_rate = 48000
        supported_languages = ["multi"]

        @classmethod
        def is_available(cls):
            return True, "ready"

        @classmethod
        def venv_python(cls):
            raise AssertionError("must not spawn a local sidecar")

        @classmethod
        def sidecar_script(cls):
            raise AssertionError("must not spawn a local sidecar")

    calls = []
    reply = {"value": _audio_reply([0.5, -0.5], 48000)}

    def fake_run_sync(cfg, task, *, timeout, idle_timeout=None, on_event=None, cancelled=None):
        calls.append({"task": task, "timeout": timeout, "idle": idle_timeout})
        if on_event:
            on_event({"stage": "installing"})
        if isinstance(reply["value"], Exception):
            raise reply["value"]
        return RayJobResult("vs-voxcpm2-x", reply["value"], [], 0.1)

    monkeypatch.setattr(runtime, "run_sync", fake_run_sync)
    monkeypatch.setattr(runtime, "executor_for", lambda cfg: object())
    monkeypatch.setattr(sb, "_RAY_INSTALLED", set())
    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["voxcpm2"], "num_gpus": 0.15})
    backend = Fake()
    monkeypatch.setattr(backend, "_check_language", lambda lang: None)
    return backend, calls, reply


def test_generate_runs_on_ray_with_reference_audio_shipped(ray_backend, tmp_path):
    backend, calls, _ = ray_backend
    ref = tmp_path / "ref.WAV"
    ref.write_bytes(b"RIFF-bytes")
    audio = backend.generate("hello", ref_audio=str(ref), language="en", seed=7)
    assert audio.shape == (1, 2) and abs(float(audio[0, 0]) - 0.5) < 1e-6
    task = calls[0]["task"]
    assert task.op == "synthesize" and task.engine == "voxcpm2" and task.num_gpus == 0.15
    assert task.inputs == {"ref_audio.wav": b"RIFF-bytes"}
    assert task.params == {"text": "hello", "language": "en", "seed": 7, "audio_format": "f32le"}
    assert task.install and "torch==2.11.0+cu128" in task.install["cuda_args"]
    # silence deadline like the local sidecar, under a cap that always allows
    # for an install (venvs are per node)
    assert calls[0]["idle"] == backend._effective_recv_timeout_s("hello")
    assert calls[0]["timeout"] >= 3600 + calls[0]["idle"]


def test_install_job_requests_the_same_gpu_share_as_synthesis(ray_backend):
    backend, calls, reply = ray_backend
    reply["value"] = {"op": "installed"}
    backend.ensure_ready()
    task = calls[0]["task"]
    assert task.op == "install" and task.num_gpus == 0.15 and calls[0]["idle"] == 600
    backend.ensure_ready()  # memoised for this process
    assert len(calls) == 1


def test_health_check_probes_the_cluster_not_a_local_sidecar(ray_backend, monkeypatch):
    from services.ray_jobs import runtime

    backend, _, _ = ray_backend
    monkeypatch.setattr(runtime, "check_cluster", lambda cfg: (True, "Runs on the Ray cluster (Ray 2.59.0)"))
    assert backend.health_check() == (True, "Runs on the Ray cluster (Ray 2.59.0)")


def test_generate_resamples_when_the_engine_reports_another_rate(ray_backend):
    backend, _, reply = ray_backend
    reply["value"] = _audio_reply([0.0] * 24000, 24000)
    assert backend.generate("x").shape[-1] == 48000


def test_job_failures_surface_like_sidecar_errors(ray_backend):
    from services.ray_jobs.executor import RayJobFailed

    backend, _, reply = ray_backend
    reply["value"] = RayJobFailed("CUDA out of memory", submission_id="s", status="FAILED", stage="engine")
    with pytest.raises(RuntimeError, match=r"voxcpm2 sidecar engine error: CUDA out of memory"):
        backend.generate("x")


def test_engines_not_routed_stay_local(ray_backend, rs):
    from services import subprocess_backend as sb

    rs.save({"engines": ["supertonic3"]})
    assert not sb.ray_routed("voxcpm2")
    backend, calls, _ = ray_backend
    with pytest.raises(AssertionError, match="must not spawn"):
        backend.generate("x")  # local path tried to spawn
    assert calls == []


def test_ray_routed_engines_count_as_available_without_a_local_install(rs, monkeypatch):
    from engines import voxcpm2_subprocess

    monkeypatch.setattr(voxcpm2_subprocess, "own_venv_python", lambda: None)
    ok, _ = voxcpm2_subprocess.VoxCPM2SubprocessBackend.is_available()
    assert not ok
    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["voxcpm2"]})
    ok, _ = voxcpm2_subprocess.VoxCPM2SubprocessBackend.is_available()
    assert ok
    from services import tts_backend

    resolved = tts_backend._effective_backend_class("voxcpm2", object)
    assert resolved is voxcpm2_subprocess.VoxCPM2SubprocessBackend


# -- Ray lane: waiting on the cluster must not occupy a local GPU-pool worker --

def test_executor_for_backend_picks_the_lane_only_for_routed_sidecar_instances(ray_backend, rs):
    from services import model_manager as mm

    backend, _, _ = ray_backend
    assert mm.executor_for_backend(backend) is mm.get_ray_lane()
    assert mm.executor_for_engine_id("voxcpm2") is mm.get_ray_lane()

    class InProcess:  # same id, not a sidecar: stays on the GPU pool
        id = "voxcpm2"

    assert mm.executor_for_backend(InProcess()) is None
    rs.save({"enabled": False})
    assert mm.executor_for_backend(backend) is None
    assert mm.executor_for_engine_id("voxcpm2") is None


def test_ray_generate_runs_on_the_lane_without_touching_the_gpu_pool(ray_backend, monkeypatch):
    from services import model_manager as mm

    backend, calls, _ = ray_backend
    monkeypatch.setattr(mm, "_get_gpu_pool", lambda: (_ for _ in ()).throw(AssertionError("GPU pool used")))
    heartbeats = []
    monkeypatch.setattr(mm, "report_model_load_activity", lambda: heartbeats.append(__import__("threading").current_thread().name))

    async def go():
        return await mm.run_on_gpu_pool_guarded(lambda: backend.generate("hi"), what="TTS generate",
                                                timeout=30, executor=mm.get_ray_lane())

    audio = asyncio.run(go())
    assert audio.shape == (1, 2) and calls
    # the install heartbeat from the fake job was credited on the lane thread
    assert heartbeats and heartbeats[0].startswith("ray-lane")


def test_lane_timeouts_explain_the_cluster_not_local_vram(monkeypatch):
    import threading as _t
    from services import model_manager as mm

    release = _t.Event()

    async def go():
        return await mm.run_on_gpu_pool_guarded(lambda: release.wait(5), what="TTS generate",
                                                timeout=0.2, executor=mm.get_ray_lane())

    monkeypatch.setattr(mm, "MODEL_LOAD_EXTRA_TIMEOUT_S", 0.1, raising=False)
    monkeypatch.setattr(mm, "PROGRESS_EXTENSION_BUDGETS", 0, raising=False)
    with pytest.raises(TimeoutError, match="Ray cluster"):
        asyncio.run(go())
    release.set()


# -- batching: one job (one model load) for many utterances -------------------

def _batch_reply(n, sr=48000):
    pcm = base64.b64encode(np.full(4, 0.25, dtype="<i2").tobytes()).decode()
    return {"op": "batch", "results": [{"op": "audio", "audio_pcm_b64": pcm, "sample_rate": sr}] * n}


def test_generate_batch_sends_one_job_with_deduped_inputs_and_per_item_seeds(ray_backend, tmp_path):
    backend, calls, reply = ray_backend
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF-same")
    reply["value"] = _batch_reply(3)
    out = backend.generate_batch(["a", "b", "c"], ref_audio=str(ref), language="en", seed=[1, None, 3])
    assert len(out) == 3 and all(t.shape == (1, 4) for t in out)
    (call,) = calls
    task = call["task"]
    assert task.op == "batch" and task.params["call"] == "synthesize"
    assert list(task.inputs) == ["ref_audio__0.wav"]  # one copy for three items
    items = task.params["items"]
    assert [i["text"] for i in items] == ["a", "b", "c"]
    assert all(i["ref_audio"] == "@ref_audio__0" for i in items)
    assert items[0]["seed"] == 1 and "seed" not in items[1] and items[2]["seed"] == 3
    assert "audio_format" not in items[0]  # s16 for batches: half the bytes


def test_generate_batch_surfaces_a_failed_item_like_a_sidecar_error(ray_backend):
    backend, _, reply = ray_backend
    reply["value"] = {"op": "batch", "results": [_batch_reply(1)["results"][0],
                                                 {"op": "error", "stage": "engine", "message": "boom"}]}
    with pytest.raises(RuntimeError, match="sidecar engine error: boom"):
        backend.generate_batch(["a", "b"])


def test_native_batch_is_only_claimed_when_routed_and_hooks_carry_the_engine_logic(ray_backend, rs):
    from services import subprocess_backend as sb

    backend, _, _ = ray_backend
    assert backend.has_native_batch and backend.native_batch_width_hint == 16

    class OwnGenerate(type(backend)):
        def generate(self, text, **kw):
            return super().generate(text, **kw)

    assert not OwnGenerate().has_native_batch  # arbitration-style engines stay per utterance
    rs.save({"enabled": False})
    assert not backend.has_native_batch and backend.native_batch_width_hint is None


def test_batch_groups_respect_the_result_size_budget(monkeypatch):
    from services import subprocess_backend as sb

    items = [("x" * 800, {})] * 40
    groups = sb._batch_groups(items, 48000)
    assert sum(len(g) for g in groups) == 40
    assert all(len(g) <= sb._RAY_BATCH_MAX_ITEMS for g in groups)
    for g in groups:
        est = sum(max(len(t) / sb._RAY_CHARS_PER_SECOND, 1.0) * 48000 * 2 for t, _ in g)
        assert est <= sb._RAY_BATCH_MAX_BYTES or len(g) == 1


def test_long_text_renders_through_one_generate_batch_call(monkeypatch):
    import torch
    gen = importlib.import_module("api.routers.generation")
    seen = {}

    class Batched:
        sample_rate = 24000
        batches_render_chunks = True
        supports_generation_seed = True
        applies_own_mastering = True

        def generate(self, *a, **k):
            raise AssertionError("per-chunk generate on a batched engine")

        def generate_batch(self, texts, **kw):
            seen["texts"], seen["seed"] = texts, kw.get("seed")
            return [torch.zeros(1, 2400) for _ in texts]

    text = " ".join(["This is a sentence that keeps going for a while."] * 60)
    gen._run_backend_inference(Batched(), text, "en", None, None, None, None, 8, 2.0, 1.0,
                               False, False, 7, effect_preset="raw")
    assert len(seen["texts"]) > 1 and seen["seed"] == [7 + i for i in range(len(seen["texts"]))]


def test_dub_batch_width_follows_the_engine_hint_not_the_local_gpu():
    from services.dub_batching import native_batch_width

    class Hinted:
        native_batch_width_hint = 16

    assert native_batch_width(Hinted()) == 16


def test_audiobook_batches_missing_spans_and_caches_each_one(monkeypatch):
    import torch
    from services import audiobook as ab

    calls, stored = [], []

    def synth(text, voice_id, speed=None):
        raise AssertionError("per-chunk synth on a batched engine")

    def batch(requests):
        calls.append([t for t, _, _ in requests])
        return [torch.ones(1, 100) for _ in requests]

    synth.batch = batch

    class Cache:
        def load(self, span, nonce=None):
            return torch.zeros(1, 50) if span.text == "cached line" else None

        def store(self, span, audio, nonce=None):
            stored.append(span.text)

    spans = [ab.Span(text=t, voice_id=None) for t in ("first line", "cached line", "third line")]
    audio, seconds = ab.synthesize_chapter(spans, synth, 1000, segment_cache=Cache())
    assert calls == [["first line", "third line"]]  # one call, cache hit skipped
    assert stored == ["first line", "third line"]
    assert audio.shape[-1] == 100 + 50 + 100


# -- ASR on Ray (faster-whisper-isolated) ------------------------------------

@pytest.fixture
def ray_asr(rs, monkeypatch, tmp_path):
    from services import subprocess_asr as sa
    from services.ray_jobs import runtime
    from services.ray_jobs.executor import RayJobResult

    calls = []

    def fake_run_sync(cfg, task, *, timeout, idle_timeout=None, on_event=None, cancelled=None):
        calls.append({"task": task, "idle": idle_timeout, "timeout": timeout})
        n = len(task.params["items"])
        seg = {"op": "segments", "result": {"segments": [{"start": 0.0, "end": 1.0, "text": "hello"}], "language": "en"}}
        return RayJobResult("vs-asr", {"op": "batch", "results": [seg] * n}, [], 0.1)

    monkeypatch.setattr(runtime, "run_sync", fake_run_sync)
    monkeypatch.setattr(sa, "_RAY_WARM", set())
    monkeypatch.setattr(sa.IsolatedFasterWhisperBackend, "_ray_env", lambda self: {"ASR_MODEL_FW": "Systran/faster-whisper-tiny"})
    # Warm-up has its own tests; elsewhere count only the real jobs.
    real_warm = sa.SubprocessASRBackend._ray_warm_up
    monkeypatch.setattr(sa.SubprocessASRBackend, "_ray_warm_up", lambda self, cfg: None)
    monkeypatch.setattr(sa, "_real_warm_up_for_tests", real_warm, raising=False)
    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["faster-whisper-isolated"]})
    clips = []
    for i in range(3):
        p = tmp_path / f"c{i}.wav"
        p.write_bytes(b"RIFF" + bytes([i]) * 100)
        clips.append(str(p))
    return sa.IsolatedFasterWhisperBackend(), calls, clips


def test_ray_transcribe_ships_the_clip_and_normalises_chunks(ray_asr):
    backend, calls, clips = ray_asr
    out = backend.transcribe(clips[0], word_timestamps=True, language="th")
    assert out["chunks"] == [{"text": "hello", "timestamp": (0.0, 1.0)}]
    task = calls[0]["task"]
    assert task.op == "batch" and task.params["call"] == "transcribe" and task.engine == "faster-whisper-isolated"
    assert task.params["shared"]["word_timestamps"] is True
    assert task.params["shared"]["request_options"]["language"] == "th"
    assert list(task.inputs) == ["audio_path__0.wav"] and task.params["items"] == [{"audio_path": "@audio_path__0"}]
    assert task.env == {"ASR_MODEL_FW": "Systran/faster-whisper-tiny"} and task.num_gpus is not None


def test_ray_transcribe_many_is_one_job(ray_asr):
    backend, calls, clips = ray_asr
    out = backend.transcribe_many(clips, word_timestamps=False)
    assert len(out) == 3 and len(calls) == 1 and len(calls[0]["task"].inputs) == 3


def test_ray_warm_up_runs_once_with_a_long_silence_deadline(ray_asr, monkeypatch):
    from services import subprocess_asr as sa

    monkeypatch.setattr(sa.SubprocessASRBackend, "_ray_warm_up", sa._real_warm_up_for_tests)
    backend, calls, _ = ray_asr
    backend.ensure_loaded()
    backend.ensure_loaded()
    assert len(calls) == 1 and calls[0]["idle"] == sa._RAY_ASR_WARM_IDLE_S


def test_ray_asr_refuses_a_local_model_folder(rs, monkeypatch, tmp_path):
    from services import asr_backend, subprocess_asr as sa

    monkeypatch.setattr(asr_backend, "_offline_asr_repo", lambda bid: str(tmp_path))
    with pytest.raises(RuntimeError, match="Hugging Face model id"):
        sa.IsolatedFasterWhisperBackend()._ray_env()


def test_ray_asr_is_available_and_skips_the_local_model_check(ray_asr):
    from services import asr_backend

    backend, _, _ = ray_asr
    assert type(backend).is_available() == (True, "runs on the Ray cluster")
    assert asr_backend.asr_model_missing_error(backend_id="faster-whisper-isolated", require_installed=True) is None


def test_reference_refine_batches_every_clip_into_one_job(ray_asr):
    from services.speaker_clone import refine_ref_texts

    backend, calls, clips = ray_asr
    clones = {f"s{i}": {"ref_audio": c, "ref_text": "old"} for i, c in enumerate(clips)}
    refine_ref_texts(clones, backend)
    assert len(calls) == 1 and all(e["ref_text"] == "hello" for e in clones.values())


def test_asr_package_ships_the_stdlib_core_modules_it_imports():
    import io as _io
    import zipfile as _zf
    from services.ray_jobs.package import build_package

    _, data, task = build_package({"v": 1, "op": "transcribe", "engine": "faster-whisper-isolated"}, {})
    names = set(_zf.ZipFile(_io.BytesIO(data)).namelist())
    assert {"engines/_asr_sidecar/main.py", "core/__init__.py", "core/execstack.py", "core/cudnn8.py",
            "core/device_caps.py", "core/gpu_inventory.py"} <= names
    assert not any(n.startswith(("services/", "api/")) for n in names)


# -- phase-2 review fixes -------------------------------------------------------

def test_non_per_item_lists_such_as_emo_vector_pass_through_whole():
    from services import subprocess_backend as sb

    emo = [0.1, 0, 0, 0, 0, 0, 0, 0.9]
    kw = {"ref_audio": ["a"] * 9, "emo_vector": emo, "seed": [1] + [None] * 8}
    for i in range(9):
        item = sb._item_kwargs(kw, i, 9)
        assert item["emo_vector"] == emo and item["ref_audio"] == "a"
    assert sb._item_kwargs(kw, 0, 9)["seed"] == 1 and "seed" not in sb._item_kwargs(kw, 1, 9)


def test_batch_sizing_is_conservative_for_cjk_and_slow_speech():
    from services import subprocess_backend as sb

    zh = "这是一个用于测试语音合成的中文句子。" * 17  # ~306 chars, like a real chunk
    assert sb._speech_seconds(zh) > 70
    assert sb._speech_seconds("x" * 100, speed=0.5) == 2 * sb._speech_seconds("x" * 100)
    groups = sb._batch_groups([(zh, {})] * 12, 48000)
    for g in groups:
        assert sum(sb._speech_seconds(t) for t, _ in g) * 48000 * 2 <= sb._RAY_BATCH_MAX_BYTES or len(g) == 1


def test_a_truncated_worker_batch_continues_with_the_remaining_items(ray_backend):
    backend, calls, reply = ray_backend
    one = _batch_reply(1)["results"][0]
    replies = [{"op": "batch", "results": [one, one], "truncated": True}, {"op": "batch", "results": [one]}]
    from services.ray_jobs import runtime
    from services.ray_jobs.executor import RayJobResult

    def run_sync(cfg, task, **kw):
        calls.append({"task": task})
        return RayJobResult("s", replies.pop(0), [], 0.1)

    runtime.run_sync = run_sync
    out = backend.generate_batch(["a", "b", "c"])
    assert len(out) == 3 and [len(c["task"].params["items"]) for c in calls] == [3, 1]


def test_audiobook_batch_renders_a_repeated_line_once(monkeypatch):
    import torch
    from services import audiobook as ab

    renders, stored = [], {}

    def synth(text, voice_id, speed=None):
        return torch.ones(1, 10)

    def batch(requests):
        renders.extend(t for t, _, _ in requests)
        return [torch.ones(1, 10) for _ in requests]

    synth.batch = batch

    class Cache:  # nonce-ignoring, like vary_repeats off
        def load(self, span, nonce=None):
            return stored.get(span.text)

        def store(self, span, audio, nonce=None):
            stored[span.text] = audio

    spans = [ab.Span(text=t, voice_id=None) for t in ("Hello there.", "Something else.", "Hello there.")]
    ab.synthesize_chapter(spans, synth, 1000, segment_cache=Cache())
    assert renders == ["Hello there.", "Something else."]


def test_ray_asr_idle_deadline_scales_with_clip_length(ray_asr, monkeypatch):
    from services import subprocess_asr as sa

    backend, calls, clips = ray_asr
    monkeypatch.setattr(sa, "_clip_seconds", lambda p: 1800.0)
    from services.ray_jobs import settings as _rs
    backend._transcribe_via_ray(_rs.load(), clips[:1], True, {})
    assert calls[-1]["idle"] >= backend.recv_timeout_s + 3 * 1800


def test_ray_asr_warm_up_follows_the_selected_model(ray_asr, monkeypatch):
    from services import subprocess_asr as sa

    monkeypatch.setattr(sa.SubprocessASRBackend, "_ray_warm_up", sa._real_warm_up_for_tests)
    backend, calls, _ = ray_asr
    backend.ensure_loaded()
    monkeypatch.setattr(sa.IsolatedFasterWhisperBackend, "_ray_env", lambda self: {"ASR_MODEL_FW": "Systran/faster-whisper-large-v3"})
    backend.ensure_loaded()
    assert len(calls) == 2  # a new model warms up again


def test_long_files_are_split_into_pieces_and_merged_on_the_timeline(ray_asr, tmp_path, monkeypatch):
    import soundfile as sf
    from services import subprocess_asr as sa

    backend, _, _ = ray_asr
    monkeypatch.setattr(sa, "_RAY_ASR_PIECE_S", 1.0)
    path = tmp_path / "long.wav"
    sf.write(path, np.zeros(16000 * 3, dtype="float32"), 16000)
    out = backend.transcribe(str(path))
    starts = [s["start"] for s in out["segments"]]
    assert starts == [0.0, 1.0, 2.0] and [c["timestamp"][0] for c in out["chunks"]] == starts


def test_refine_keeps_the_original_text_only_for_the_clip_that_failed(ray_asr, monkeypatch):
    from services.speaker_clone import refine_ref_texts

    backend, _, clips = ray_asr
    monkeypatch.setattr(type(backend), "transcribe_many",
                        lambda self, paths, **kw: [RuntimeError("bad clip"), {"chunks": [{"text": "new"}]}, {"chunks": [{"text": "new"}]}])
    clones = {f"s{i}": {"ref_audio": c, "ref_text": "old"} for i, c in enumerate(clips)}
    refine_ref_texts(clones, backend)
    assert [e["ref_text"] for e in clones.values()] == ["old", "new", "new"]


def test_asr_dispatch_uses_the_lane_and_a_cluster_budget_when_routed(ray_asr, monkeypatch):
    from services import asr_backend, model_manager

    monkeypatch.setattr(asr_backend, "active_backend_id", lambda: "faster-whisper-isolated")
    d = asr_backend.ray_asr_dispatch("pool", 300)
    assert d["executor"] is model_manager.get_ray_lane() and d["timeout"] >= asr_backend.RAY_ASR_TIMEOUT_S
    monkeypatch.setattr(asr_backend, "active_backend_id", lambda: "whisperx")
    assert asr_backend.ray_asr_dispatch("pool", 300) == {"executor": "pool", "timeout": 300}


# -- phase 3: NLLB, Demucs, pyannote, OmniVoice, local alignment ---------------

def test_phase3_engines_are_registered_with_locked_recipes():
    from services.ray_jobs.engines import RAY_ENGINES, install_recipe

    kinds = {e: RAY_ENGINES[e].kind for e in ("nllb", "demucs", "pyannote", "omnivoice")}
    assert kinds == {"nllb": "translation", "demucs": "separation", "pyannote": "diarization", "omnivoice": "tts"}
    for engine in kinds:
        recipe = install_recipe(engine)
        assert "torch==2.8.0+cu128" in recipe["cuda_args"] and "torch==2.8.0+cpu" in recipe["cpu_args"]
    assert "torchaudio==2.8.0+cu128" in install_recipe("pyannote")["cuda_args"]


def test_omnivoice_package_ships_its_inference_modules_only():
    import io as _io
    import zipfile as _zf
    from services.ray_jobs.package import build_package

    _, data, _ = build_package({"v": 1, "op": "synthesize", "engine": "omnivoice"}, {})
    names = set(_zf.ZipFile(_io.BytesIO(data)).namelist())
    assert {"engines/omnivoice_ray/main.py", "omnivoice/models/omnivoice.py", "omnivoice/utils/audio.py"} <= names
    assert not any(n.startswith(("omnivoice/training", "omnivoice/eval", "services/")) for n in names)


def test_extra_files_cannot_escape_their_base():
    from services.ray_jobs.package import _extra_source

    with pytest.raises(ValueError):
        _extra_source("../omnivoice/../../etc/passwd")
    with pytest.raises(ValueError):
        _extra_source("../../etc/passwd")


def _seg(i, text):
    from types import SimpleNamespace
    return SimpleNamespace(id=i, text=text, target_lang=None)


def test_nllb_on_ray_keeps_order_blanks_and_per_row_errors(rs, monkeypatch):
    from api.routers import dub_translate
    from services.ray_jobs import jobs
    from services.ray_jobs.executor import RayJobResult

    sent = {}

    def fake_run(engine_id, cfg, task, **kw):
        sent["task"] = task
        return RayJobResult("s", {"op": "translated", "groups": [
            {"tgt": "tha_Thai", "texts": ["สวัสดี", "x"], "errors": [None, "too long"]},
            {"tgt": "fra_Latn", "texts": ["Bonjour"], "errors": [None]}]}, [], 0.1)

    monkeypatch.setattr(jobs, "run_engine_job", fake_run)
    rows = [(0, _seg(0, "Hello"), "tha_Thai"), (1, _seg(1, " "), "tha_Thai"),
            (2, _seg(2, "Long"), "tha_Thai"), (3, _seg(3, "Hi"), "fra_Latn")]
    out = dub_translate._translate_nllb_on_ray(rs.load(), rows, "eng_Latn", {"num_beams": 5})
    assert [r["id"] for r in out] == [0, 1, 2, 3]
    assert out[0] == {"id": 0, "text": "สวัสดี"} and out[1] == {"id": 1, "text": " "}
    assert out[2] == {"id": 2, "text": "Long", "error": "too long"} and out[3]["text"] == "Bonjour"
    params = sent["task"].params
    assert params["src"] == "eng_Latn" and params["decode_options"] == {"num_beams": 5}
    assert [g["tgt"] for g in params["groups"]] == ["tha_Thai", "fra_Latn"]


def test_nllb_job_failure_marks_every_row_like_a_load_error(rs, monkeypatch):
    from api.routers import dub_translate
    from services.ray_jobs import jobs

    monkeypatch.setattr(jobs, "run_engine_job", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cluster down")))
    out = dub_translate._translate_nllb_on_ray(rs.load(), [(0, _seg(0, "Hello"), "tha_Thai")], "eng_Latn", {})
    assert out[0]["text"] == "Hello" and out[0]["error"].startswith("Model load error")


def test_nllb_readiness_does_not_need_local_weights_when_routed(rs):
    from services import translation_engines

    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["nllb"]})
    assert translation_engines._nllb_weights_probe() == (True, None)


def test_separation_windows_cover_the_track_with_context_pads():
    from services.ray_jobs import separation as sep

    sr = 1000
    windows = sep._windows(int(300.5 * sr), sr)
    assert windows[0][0] == 0 and windows[0][2] == 0  # no left pad at the start
    cores = sum(b - a - pl - pr for a, b, pl, pr in windows)
    assert cores == int(300.5 * sr)
    assert all(pl <= sep.PAD_S * sr and pr <= sep.PAD_S * sr for _, _, pl, pr in windows)


def test_separation_reassembles_windows_and_continues_after_truncation(rs, monkeypatch, tmp_path):
    import base64 as _b64
    import io as _io
    import soundfile as sf
    from services.ray_jobs import jobs, separation as sep
    from services.ray_jobs.executor import RayJobResult

    monkeypatch.setattr(sep, "WINDOW_S", 1.0)
    monkeypatch.setattr(sep, "PAD_S", 0.25)
    src = tmp_path / "in.wav"
    sf.write(src, np.zeros((int(3.5 * 44100), 2), dtype="float32"), 44100)
    calls = []

    def fake_run(engine_id, cfg, task, **kw):
        items = task.params["items"]
        calls.append(len(items))
        out = []
        for item in items[:2]:  # the worker stops after two windows
            frames = int(1.0 * 44100)
            v, b = _io.BytesIO(), _io.BytesIO()
            sf.write(v, np.full((frames, 2), 0.1, dtype="float32"), 44100, format="FLAC")
            sf.write(b, np.full((frames, 2), 0.2, dtype="float32"), 44100, format="FLAC")
            out.append({"op": "separated", "vocals_b64": _b64.b64encode(v.getvalue()).decode(),
                        "bed_b64": _b64.b64encode(b.getvalue()).decode()})
        return RayJobResult("s", {"op": "batch", "results": out, "truncated": len(items) > 2}, [], 0.1)

    monkeypatch.setattr(jobs, "run_engine_job", fake_run)
    progress = []
    sep.separate_on_ray(rs.load(), str(src), str(tmp_path / "v.wav"), str(tmp_path / "b.wav"), on_progress=progress.append)
    assert calls == [4, 2]
    v, _ = sf.read(tmp_path / "v.wav", always_2d=True)
    b, _ = sf.read(tmp_path / "b.wav", always_2d=True)
    # Stereo stems, like the local CLI's.
    assert v.shape == (4 * 44100, 2) and b.shape == (4 * 44100, 2) and progress[-1] == 1.0


def test_ray_pyannote_pipeline_rebuilds_an_annotation_and_serves_phrase_embeddings(rs, monkeypatch, tmp_path):
    import soundfile as sf
    from services.ray_jobs import diarization, jobs
    from services.ray_jobs.executor import RayJobResult

    monkeypatch.setattr(diarization, "_local_bundle", lambda: {"config_path.yaml": b"c", "segmentation_path.bin": b"s",
                                                               "embedding_path.bin": b"e"})
    sent = {}

    def fake_run(engine_id, cfg, task, **kw):
        sent["task"] = task
        return RayJobResult("s", {"op": "diarization", "turns": [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}, {"start": 1.2, "end": 2.0, "speaker": "SPEAKER_01"}],
            "phrase_embeddings": [[1.0, 0.0], [0.0, 1.0]]}, [], 0.1)

    monkeypatch.setattr(jobs, "run_engine_job", fake_run)
    path = tmp_path / "a.wav"
    sf.write(path, np.zeros(44100 * 2, dtype="float32"), 44100)
    phrases = [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 1.2, "end": 2.0, "text": "b"},
               {"start": 2.0, "end": 2.3, "text": "short"}]
    pipe = diarization.RayPyannotePipeline(rs.load(), phrases=phrases)
    ann = pipe(str(path), num_speakers=2)
    assert sorted(ann.labels()) == ["SPEAKER_00", "SPEAKER_01"]
    task = sent["task"]
    assert set(task.inputs) == {"config_path.yaml", "segmentation_path.bin", "embedding_path.bin", "audio_path.ogg"}
    assert task.params == {"num_speakers": 2, "phrases": [(0.0, 1.0), (1.2, 2.0)]}  # short phrase not embedded
    assert list(pipe.phrase_embedding(1.2, 2.0)) == [0.0, 1.0] and pipe.phrase_embedding(2.0, 2.3) is None
    assert not any("TOKEN" in k for k in task.env)


def test_speaker_recovery_uses_precomputed_phrase_embeddings(monkeypatch):
    dub_core = importlib.import_module("api.routers.dub_core")

    class Pipe:
        def phrase_embedding(self, start, end):
            # two clearly separated voices, alternating
            return np.array([1.0, 0.05] if int(start) % 2 == 0 else [0.05, 1.0])

    phrases = [{"start": float(i), "end": float(i) + 0.9, "text": f"p{i}"} for i in range(6)]
    segments = [{"start": float(i), "end": float(i) + 0.9, "text": f"p{i}", "speaker_id": "Speaker 1"} for i in range(6)]
    out = dub_core._recover_from_phrase_embeddings(Pipe(), segments, phrases=phrases, requested_speakers=None,
                                                   audio_target="unused.wav", segments=segments, words=[])
    assert out is not None
    recovered, separation = out
    assert len({s["speaker_id"] for s in recovered}) == 2 and separation > 0.12


def test_ray_asr_results_get_local_forced_alignment(monkeypatch, tmp_path):
    from services import asr_backend, subprocess_asr as sa

    monkeypatch.setattr(asr_backend, "_decode_audio_16k_mono", lambda p: "AUDIO")
    seen = {}

    def fake_align(segments, audio, lang):
        seen["args"] = (audio, lang)
        return [{**s, "start": s["start"] + 0.01} for s in segments]

    monkeypatch.setattr(asr_backend, "forced_align", fake_align)
    result = {"segments": [{"start": 1.0, "end": 2.0, "text": "hi"}], "language": "th", "chunks": []}
    out = sa._align_locally(result, tmp_path / "x.wav")
    assert seen["args"] == ("AUDIO", "th") and out["segments"][0]["start"] == 1.01
    assert out["chunks"] == [{"text": "hi", "timestamp": (1.01, 2.0)}]
    monkeypatch.setenv("OMNIVOICE_RAY_ASR_ALIGN", "0")
    assert sa._align_locally(result, tmp_path / "x.wav") is result


def test_omnivoice_routes_to_the_sidecar_class_and_sends_a_hub_checkpoint(rs, monkeypatch, tmp_path):
    from engines.omnivoice_subprocess import OmniVoiceMPSSubprocessBackend
    from services import model_manager, tts_backend

    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["omnivoice"]})
    assert tts_backend._effective_backend_class("omnivoice", object, host_family="cuda") is OmniVoiceMPSSubprocessBackend
    monkeypatch.setattr(model_manager, "resolve_omnivoice_checkpoint", lambda: "k2-fsa/OmniVoice")
    assert OmniVoiceMPSSubprocessBackend()._ray_env() == {"VS_OMNIVOICE_CHECKPOINT": "k2-fsa/OmniVoice"}
    monkeypatch.setattr(model_manager, "resolve_omnivoice_checkpoint", lambda: str(tmp_path))
    with pytest.raises(RuntimeError, match="Hugging Face model id"):
        OmniVoiceMPSSubprocessBackend()._ray_env()
    rs.save({"enabled": False})
    assert tts_backend._effective_backend_class("omnivoice", object, host_family="cuda") is object


def test_omnivoice_on_ray_resolves_the_reference_transcript_locally(rs, monkeypatch, tmp_path):
    from engines.omnivoice_subprocess import OmniVoiceMPSSubprocessBackend
    from services import asr_backend, subprocess_backend as sb, tts_backend

    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["omnivoice"]})
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    monkeypatch.setattr(tts_backend, "reference_duration_s", lambda p: 5.0)
    monkeypatch.setattr(tts_backend, "omnivoice_inline_reference", lambda a, t: (a, t, None))
    calls = []
    # Default release policy: the API process's ASR model may be shared.
    monkeypatch.setattr(asr_backend, "transcribe_reference", lambda p, **kw: calls.append(kw) or "the words")
    sent = {}
    base = next(c for c in OmniVoiceMPSSubprocessBackend.__mro__ if "_generate_raw" in vars(c))
    monkeypatch.setattr(base, "_generate_raw", lambda self, text, kw: sent.update(kw) or __import__("torch").zeros(1, 4))
    OmniVoiceMPSSubprocessBackend().generate("hi", ref_audio=str(ref))
    assert sent["ref_text"] == "the words"
    assert calls == [{}]


def test_omnivoice_on_ray_batches_with_one_transcript_and_drops_passages(rs, monkeypatch, tmp_path):
    from engines.omnivoice_subprocess import OmniVoiceMPSSubprocessBackend
    from services import asr_backend, tts_backend

    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["omnivoice"]})
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    passage = tmp_path / "passage.wav"
    monkeypatch.setattr(tts_backend, "reference_duration_s", lambda p: 5.0)

    def inline(audio, text):
        passage.write_bytes(b"RIFF")
        return str(passage), text + " (passage)", str(passage)

    monkeypatch.setattr(tts_backend, "omnivoice_inline_reference", inline)
    calls = []
    monkeypatch.setattr(asr_backend, "transcribe_reference", lambda p, **kw: calls.append(p) or "the words")
    backend = OmniVoiceMPSSubprocessBackend.__new__(OmniVoiceMPSSubprocessBackend)
    assert backend.has_native_batch
    groups = []

    def fake_batch(self, cfg, group):
        assert passage.exists()  # alive while the job runs
        groups.append(group)
        return [__import__("torch").zeros(1, 4) for _ in group]

    base = next(c for c in OmniVoiceMPSSubprocessBackend.__mro__ if "_generate_batch_via_ray" in vars(c))
    monkeypatch.setattr(base, "_generate_batch_via_ray", fake_batch)
    out = backend.generate_batch(["one", "two"], ref_audio=str(ref))
    assert len(out) == 2 and calls == [str(ref)]
    assert [kw["ref_text"] for group in groups for _text, kw in group] == ["the words (passage)"] * 2
    assert not passage.exists()


def test_ray_jobs_receive_the_callers_cancel_event(rs, monkeypatch, tmp_path):
    import threading

    import soundfile as sf
    from services.ray_jobs import diarization, jobs, separation as sep
    from services.ray_jobs.executor import RayJobResult

    src = tmp_path / "in.wav"
    sf.write(src, np.zeros((44100, 2), dtype="float32"), 44100)
    seen = []

    def fake_run(engine_id, cfg, task, **kw):
        seen.append((engine_id, kw.get("cancelled")))
        raise RuntimeError("stop here")

    monkeypatch.setattr(jobs, "run_engine_job", fake_run)
    monkeypatch.setattr(diarization, "_local_bundle", lambda: {"config_path.yaml": b"c", "segmentation_path.bin": b"s",
                                                               "embedding_path.bin": b"e"})
    cancel = threading.Event()
    with pytest.raises(RuntimeError):
        sep.separate_on_ray(rs.load(), str(src), str(tmp_path / "v.wav"), str(tmp_path / "b.wav"), cancelled=cancel)
    with pytest.raises(RuntimeError):
        diarization.RayPyannotePipeline(rs.load(), cancelled=cancel)(str(src))
    assert seen == [("demucs", cancel), ("pyannote", cancel)]


def test_ray_diarization_without_the_local_bundle_reports_missing(rs, monkeypatch):
    from api.routers import dub_core
    from services.model_manager import DIARIZATION_ERR_MISSING
    from services.ray_jobs import diarization

    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["pyannote"]})
    monkeypatch.setattr(dub_core, "_ensure_diarisation_accepted", lambda: None)
    monkeypatch.setattr(diarization, "bundle_installed", lambda: False)
    assert dub_core._diarization_pipeline_checked() == (None, DIARIZATION_ERR_MISSING)
    monkeypatch.setattr(diarization, "bundle_installed", lambda: True)
    pipe, err = dub_core._diarization_pipeline_checked()
    assert err is None and isinstance(pipe, diarization.RayPyannotePipeline)
