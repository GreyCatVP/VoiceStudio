"""POST /v1/speak and GET /v1/voices — the simple saved-voice API for local scripts.

Contract pinned here:

* /v1/speak takes only text + a saved voice (id or name) and fills the rest:
  the voice's own language and seed, 32 quality steps, the voice's reference;
* an explicit language / seed from the caller wins;
* an unknown voice is a 404 ``voice_not_found`` (never an engine preset, unlike
  /v1/audio/speech), and a voice without a language asks for one (400);
* /v1/voices lists saved voices with the category read from the name, and
  filters by category (case-insensitive) and language.
"""
from __future__ import annotations

import importlib
import os
import uuid

import pytest
import torch
from fastapi.testclient import TestClient

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")


def _tts_mod():
    return importlib.import_module("services.tts_backend")


@pytest.fixture()
def engine(monkeypatch):
    class _Engine(_tts_mod().TTSBackend):
        id = "speak-api-engine"
        display_name = "Speak API engine (test)"
        gpu_compat = ("cpu",)
        calls: list = []

        @property
        def sample_rate(self) -> int:
            return 24000

        @property
        def supported_languages(self) -> list[str]:
            return ["multi"]

        @classmethod
        def is_available(cls):
            return True, "ready"

        def generate(self, text, **kw):
            type(self).calls.append({"text": text, **kw})
            return torch.zeros(1, 2400)

    _Engine.calls = []
    inst = _Engine()
    tts = _tts_mod()
    monkeypatch.setitem(tts._REGISTRY, _Engine.id, _Engine)
    monkeypatch.setattr(tts, "get_active_tts_backend", lambda: inst)
    monkeypatch.setattr(tts, "get_engine_instance_for", lambda _id: inst)
    from services import engine_routing

    async def _profile(*_a, **_k):
        return {"routing_status": "native", "routing_reason": ""}

    monkeypatch.setattr(engine_routing, "runtime_compute_profile_async", _profile)
    return _Engine


@pytest.fixture()
def client():
    from main import app

    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture()
def profiles():
    from core.db import db_conn, init_db

    init_db()
    stem = f"spk-{uuid.uuid4().hex[:8]}"
    created: list[str] = []

    def add(name: str, *, language: str = "Hindi", seed: int | None = 11, personality: str = "") -> str:
        pid = str(uuid.uuid4())
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO voice_profiles (id, name, kind, created_at, ref_text, ref_audio_path, "
                "language, seed, personality) VALUES (?, ?, 'clone', ?, ?, ?, ?, ?, ?)",
                (pid, name, float(len(created)), "संदर्भ", f"{pid}.wav", language, seed, personality),
            )
        created.append(pid)
        return pid

    add.stem = stem  # type: ignore[attr-defined]
    yield add
    with db_conn() as conn:
        for pid in created:
            conn.execute("DELETE FROM voice_profiles WHERE id=?", (pid,))


def _speak(client, **body):
    body.setdefault("model", "tts-1")
    body.setdefault("humanize", False)
    return client.post("/v1/speak", json=body)


def test_speak_fills_language_seed_and_quality_from_the_voice(client, engine, profiles):
    name = f"HI · Family · Maa {profiles.stem}"
    pid = profiles(name, language="Hindi", seed=23)
    res = _speak(client, text="नमस्ते", voice=name.lower())
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("audio/wav")
    kw = engine.calls[-1]
    assert kw["language"] == "hi"
    assert kw["seed"] == 23
    assert kw["num_step"] == 32
    assert kw["ref_audio"].endswith(f"{pid}.wav")
    assert kw["ref_text"] == "संदर्भ"


def test_caller_language_and_seed_win(client, engine, profiles):
    pid = profiles(f"Mixed {profiles.stem}", language="Hindi", seed=23)
    res = _speak(client, text="Hello", voice=pid, language="en", seed=5, num_step=16)
    assert res.status_code == 200, res.text
    kw = engine.calls[-1]
    assert (kw["language"], kw["seed"], kw["num_step"]) == ("en", 5, 16)


def test_humanize_default_is_on(client, engine, profiles):
    pid = profiles(f"Human {profiles.stem}")
    res = client.post("/v1/speak", json={"model": "tts-1", "text": "नमस्ते", "voice": pid})
    assert res.status_code == 200, res.text


def test_unknown_voice_is_404_not_an_engine_preset(client, engine, profiles):
    res = _speak(client, text="Hi", voice=f"nobody {profiles.stem}")
    assert res.status_code == 404, res.text
    assert res.json()["error"]["code"] == "voice_not_found"
    assert engine.calls == []


def test_voice_without_language_asks_for_one(client, engine, profiles):
    pid = profiles(f"Auto {profiles.stem}", language="Auto")
    res = _speak(client, text="Hi", voice=pid)
    assert res.status_code == 400, res.text
    assert res.json()["error"]["code"] == "language_required"
    assert _speak(client, text="Hi", voice=pid, language="en").status_code == 200


def test_voices_lists_categories_and_filters(client, profiles):
    a = profiles(f"HI · Funny{profiles.stem} · Chacha", personality="funny uncle")
    profiles(f"HI · Love{profiles.stem} · Romantic", language="Hindi")
    c = profiles(f"EN · Funny{profiles.stem} · Joker", language="English")
    funny = f"funny{profiles.stem}"
    res = client.get("/v1/voices", params={"category": funny.upper()})
    assert res.status_code == 200, res.text
    body = res.json()
    assert {v["id"] for v in body["voices"]} == {a, c}
    assert body["categories"] == [f"Funny{profiles.stem}"]
    entry = next(v for v in body["voices"] if v["id"] == a)
    assert entry["language"] == "hi" and entry["description"] == "funny uncle"
    only_en = client.get("/v1/voices", params={"category": funny, "language": "en"}).json()
    assert [v["id"] for v in only_en["voices"]] == [c]


def test_remote_callers_need_the_api_key(monkeypatch, engine, profiles):
    """Same gate as /v1/audio/speech: loopback is open, another device needs the key."""
    from main import app
    from services.admin_sessions import admin_session_store

    admin_session_store.clear()
    monkeypatch.setenv("OMNIVOICE_API_KEY", "s3cret-key")
    pid = profiles(f"Remote {profiles.stem}")
    remote = TestClient(app, base_url="http://gpu.example.com", client=("10.0.0.5", 1))
    body = {"model": "tts-1", "text": "नमस्ते", "voice": pid, "humanize": False}
    assert remote.get("/v1/voices").status_code == 401
    assert remote.post("/v1/speak", json=body).status_code == 401
    assert engine.calls == []
    key = {"Authorization": "Bearer s3cret-key"}
    assert remote.get("/v1/voices", headers=key).status_code == 200
    assert remote.post("/v1/speak", json=body, headers=key).status_code == 200


@pytest.mark.parametrize(
    ("name", "category"),
    [("HI · Family · Didi", "Family"), ("AutoStory · Narrator", "AutoStory"), ("Plain", None), ("A·B", None)],
)
def test_voice_category_rule(name, category):
    from api.routers.openai_compat import voice_category

    assert voice_category(name) == category
