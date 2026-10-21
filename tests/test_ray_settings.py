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
    assert {e["id"] for e in state["available_engines"]} == {"supertonic3", "voxcpm2"}
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
    {"engines": ["indextts2"]}, {"engines": ["_echo"]}, {"num_gpus": 0}, {"num_cpus": 1000},
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
    assert rs.route_for("indextts2") is None  # not portable


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
