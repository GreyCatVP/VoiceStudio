"""Modal provider: the real driver against a local stand-in for the Modal SDK
(tests/fake_modal), so package -> sandbox -> worker -> result frames run end
to end without an account."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

from services.ray_jobs import RayJobFailed, RayTask
from services.ray_jobs import modal_executor as me

FAKE_SDK = Path(__file__).parent / "fake_modal"


@pytest.fixture
def fake_modal(tmp_path, monkeypatch):
    log = tmp_path / "modal.jsonl"
    monkeypatch.setattr(me, "_driver_command", lambda: [sys.executable, str(me.DRIVER)])
    monkeypatch.setattr(me, "_driver_env", lambda token_id, token_secret: {
        "PATH": "/usr/bin:/bin", "PYTHONPATH": str(FAKE_SDK), "FAKE_MODAL_ROOT": str(tmp_path / "sandbox"),
        "FAKE_MODAL_LOG": str(log), "MODAL_TOKEN_ID": token_id, "MODAL_TOKEN_SECRET": token_secret,
    })

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    return calls


def _executor(token="ak-good", gpu="L4"):
    return me.ModalExecutor(token_id=token, token_secret="as-secret", gpu=gpu)


def test_modal_runs_the_worker_in_a_sandbox_and_returns_its_result(fake_modal):
    events = []
    task = RayTask(op="synthesize", engine="_echo", params={"text": "hello", "sample_rate": 16000}, num_cpus=2.0)
    result = asyncio.run(_executor().run(task, timeout=120, on_progress=events.append))
    assert result.result["op"] == "audio" and result.result["n_samples"] == 16000
    assert [e["stage"] for e in events] == ["start", "engine_start", "engine_ready", "engine_done"]
    calls = fake_modal()
    create = next(c for c in calls if c["event"] == "create")
    # A CPU engine gets no GPU; the cache volume is mounted; the sandbox ends with the run.
    assert create["gpu"] is None and create["cpu"] == 2.0 and create["volumes"] == ["/vs-cache"]
    assert create["tags"]["engine"] == "_echo" and create["timeout"] >= 120
    run = next(c for c in calls if c["event"] == "exec")
    assert "VS_RAY_CACHE" in run["env"] and "VS_RAY_DEADLINE" in run["env"]
    assert not any("TOKEN" in key for key in run["env"])  # credentials stay with the driver
    assert calls[-1]["event"] == "terminate"


def test_modal_requests_the_configured_gpu_for_gpu_engines(fake_modal):
    task = RayTask(op="probe", num_gpus=1.0)
    asyncio.run(_executor(gpu="H100").run(task, timeout=120))
    assert next(c for c in fake_modal() if c["event"] == "create")["gpu"] == "H100"


def test_modal_engine_errors_fail_the_run_with_the_worker_message(fake_modal):
    task = RayTask(op="nope", engine="_echo")
    with pytest.raises(RayJobFailed, match="unknown op"):
        asyncio.run(_executor().run(task, timeout=120))
    assert fake_modal()[-1]["event"] == "terminate"


def test_modal_bad_credentials_are_an_auth_error(fake_modal):
    with pytest.raises(RayJobFailed) as info:
        asyncio.run(_executor(token="ak-bad").probe())
    assert info.value.status == "AUTH"


def test_modal_probe_checks_app_and_volume(fake_modal):
    out = asyncio.run(_executor().probe())
    assert out["ok"] is True
    assert {c["event"] for c in fake_modal()} == {"app", "volume"}


def test_modal_cancel_terminates_the_sandbox(fake_modal):
    task = RayTask(op="_hold", engine="_echo", params={"seconds": 60}, test_mode=True)

    async def scenario():
        run = asyncio.ensure_future(_executor().run(task, timeout=120))
        for _ in range(200):  # until the worker is holding
            await asyncio.sleep(0.1)
            if any(c["event"] == "exec" for c in fake_modal()):
                break
        await asyncio.sleep(1.0)
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run

    asyncio.run(asyncio.wait_for(scenario(), 60))
    events = [c["event"] for c in fake_modal()]
    assert events[-1] == "terminate" and events.count("exec") == 1  # no cache sync after a cancel


def test_modal_idle_timeout_ends_a_silent_run(fake_modal):
    task = RayTask(op="_hold", engine="_echo", params={"seconds": 60}, test_mode=True)
    with pytest.raises(TimeoutError, match="no progress"):
        asyncio.run(asyncio.wait_for(_executor().run(task, timeout=120, idle_timeout=3), 60))
    assert fake_modal()[-1]["event"] == "terminate"


def test_modal_settings_validate_and_route(tmp_path, monkeypatch):
    from services.ray_jobs import settings as rs

    store, secrets = {}, {}
    from services import settings_store
    monkeypatch.setattr(settings_store, "get_text", lambda k: store.get(k))
    monkeypatch.setattr(settings_store, "set_text", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(settings_store, "list_secret_names", lambda: [k for k, v in secrets.items() if v])
    monkeypatch.setattr(settings_store, "get_secret", lambda k: secrets.get(k) or None)
    monkeypatch.setattr(settings_store, "set_secret", lambda k, v: secrets.__setitem__(k, v))
    for env in (rs.ENV_URL, rs.ENV_TOKEN, rs.ENV_MODAL_ID, rs.ENV_MODAL_SECRET):
        monkeypatch.delenv(env, raising=False)

    cfg = rs.save({"enabled": True, "provider": "modal", "engines": ["voxcpm2"]})
    assert not cfg.active  # no token yet
    with pytest.raises(ValueError, match="Modal token"):
        rs.save({"modal_token_id": "ak bad"})
    with pytest.raises(ValueError, match="GPU type"):
        rs.save({"modal_gpu": "GTX-1080"})
    cfg = rs.save({"modal_token_id": "ak-1", "modal_token_secret": "as-2", "modal_gpu": "H100"})
    assert cfg.active and cfg.provider == "modal" and cfg.modal_gpu == "H100"
    assert cfg.target == "modal:voicestudio/voicestudio-cache"
    assert rs.route_for("voxcpm2") == cfg and rs.route_for("supertonic3") is None
    public = cfg.public()
    assert public["has_modal_token"] and "H100" in public["modal_gpus"]
    assert "ak-1" not in json.dumps(public) and "as-2" not in json.dumps(public)
    assert rs.modal_credentials() == ("ak-1", "as-2")
    cfg = rs.save({"modal_gpu": ""})  # GPU engines on CPU
    assert cfg.modal_gpu == ""


def test_gpu_request_follows_the_provider():
    from services.ray_jobs.settings import RaySettings

    assert RaySettings(num_gpus=0.25).gpu_request(True) == 0.25
    assert RaySettings(num_gpus=0.0).gpu_request(True) is None  # Ray share 0 = CPU
    # Modal ignores the Ray share: one GPU of the chosen type, or none for "CPU only".
    assert RaySettings(provider="modal", num_gpus=0.0, modal_gpu="L4").gpu_request(True) == 1.0
    assert RaySettings(provider="modal", modal_gpu="").gpu_request(True) is None
    assert RaySettings(provider="modal").gpu_request(False) is None
