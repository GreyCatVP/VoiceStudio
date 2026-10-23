"""OpenBao (KV v2) as an opt-in HF token source: precedence, failure kinds,
write-only secrets, address validation, and no traffic while it is off."""
import sys
from types import SimpleNamespace

import httpx
import pytest

HF_FROM_BAO = "hf_baobaobao0000000000000000000000000000XYZ"
APP_TOKEN = "hf_appapp00000000000000000000000000000000abc"
ENV_TOKEN = "hf_envenv00000000000000000000000000000000def"
BAO_TOKEN = "s.synthetic-openbao-access-token"


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    from huggingface_hub import constants
    monkeypatch.setattr(constants, "HF_TOKEN_PATH", str(tmp_path / "hf-token"))
    monkeypatch.setattr(constants, "HF_STORED_TOKENS_PATH", str(tmp_path / "stored_tokens"))
    monkeypatch.setenv("OMNIVOICE_DATA_DIR", str(tmp_path))
    for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "OMNIVOICE_OPENBAO_ADDR", "OMNIVOICE_OPENBAO_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    for mod in list(sys.modules):
        if mod.split(".")[0] in ("core", "services", "api"):
            del sys.modules[mod]
    from core import db
    db.init_db()
    from services import openbao, token_resolver
    token_resolver.invalidate_cache()
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub.HfApi, "whoami",
                        lambda self, token=None, **kw: {"name": {HF_FROM_BAO: "bao", APP_TOKEN: "app",
                                                                 ENV_TOKEN: "env"}[token]})
    return openbao, token_resolver


def _server(monkeypatch, openbao, handler):
    """Route openbao's httpx.Client through a MockTransport; returns the request log."""
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    fake = SimpleNamespace(**vars(httpx))
    fake.Client = lambda **kw: httpx.Client(**{**kw, "transport": httpx.MockTransport(wrapped)})
    monkeypatch.setattr(openbao, "httpx", fake)
    return seen


def _kv(request):
    if request.url.path == "/v1/auth/token/lookup-self":
        return httpx.Response(200, json={"data": {"ttl": 3600, "renewable": True}})
    assert request.url.path == "/v1/secret/data/voicestudio/hf", request.url
    assert request.headers["X-Vault-Token"] == BAO_TOKEN
    return httpx.Response(200, json={"data": {"data": {"token": HF_FROM_BAO}, "metadata": {}}})


def _enable(openbao, **extra):
    openbao.save({"enabled": True, "path": "voicestudio/hf", "token": BAO_TOKEN, **extra})


def test_openbao_wins_over_app_and_env_and_is_not_persisted(fresh, monkeypatch, tmp_path):
    openbao, tr = fresh
    from services import settings_store
    settings_store.set_hf_token(APP_TOKEN)
    monkeypatch.setenv("HF_TOKEN", ENV_TOKEN)
    seen = _server(monkeypatch, openbao, _kv)
    _enable(openbao)
    result = tr.resolve()
    assert (result.source, result.token) == ("openbao", HF_FROM_BAO)
    assert settings_store.get_hf_token() == APP_TOKEN  # never copied into the store
    assert not (tmp_path / "hf-token").exists()
    tr.resolve()
    assert len(seen) == 1, "five-minute in-memory cache"
    tr.invalidate_cache()
    tr.resolve()
    assert len(seen) == 2


def test_precedence_without_openbao_is_unchanged(fresh, monkeypatch):
    openbao, tr = fresh
    seen = _server(monkeypatch, openbao, lambda r: pytest.fail("OpenBao contacted while off"))
    openbao.save({"path": "voicestudio/hf", "token": BAO_TOKEN})  # configured but not on
    monkeypatch.setenv("HF_TOKEN", ENV_TOKEN)
    assert tr.resolve().source == "env"
    from services import settings_store
    settings_store.set_hf_token(APP_TOKEN)
    tr.invalidate_cache()
    assert tr.resolve().source == "app"
    assert [row.source for row in tr.state()["sources"]] == ["app", "env", "hf-cli"]
    assert seen == []


@pytest.mark.parametrize("handler, kind", [
    (lambda r: httpx.Response(503, json={"errors": ["Vault is sealed"]}), "sealed"),
    (lambda r: httpx.Response(403, json={"errors": ["permission denied"]}), "denied"),
    (lambda r: httpx.Response(404, json={"errors": []}), "not_found"),
    (lambda r: httpx.Response(200, json={"data": {"data": {"other": "x"}}}), "not_found"),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")), "unreachable"),
])
def test_failures_fall_through_with_a_clear_kind(fresh, monkeypatch, handler, kind):
    openbao, tr = fresh
    from services import settings_store
    settings_store.set_hf_token(APP_TOKEN)
    _server(monkeypatch, openbao, handler)
    _enable(openbao)
    assert tr.resolve().source == "app"  # never crashes, next source is used
    row = tr.state()["sources"][0]
    assert (row.source, row.set, row.error) == ("openbao", False, kind)
    result = openbao.test_connection()
    assert result["ok"] is False and result["kind"] == kind


def test_test_connection_reports_masked_value_only(fresh, monkeypatch):
    openbao, _ = fresh
    _server(monkeypatch, openbao, _kv)
    _enable(openbao)
    result = openbao.test_connection()
    assert result == {"ok": True, "kind": "ok", "ttl": 3600, "renewable": True, "masked": "hf_…XYZ"}
    assert HF_FROM_BAO not in repr(result) and BAO_TOKEN not in repr(result)


def test_lookup_self_denied_still_reads_the_secret(fresh, monkeypatch):
    openbao, _ = fresh

    def handler(request):
        if request.url.path.endswith("lookup-self"):
            return httpx.Response(403, json={"errors": ["permission denied"]})
        return _kv(request)

    _server(monkeypatch, openbao, handler)
    _enable(openbao)
    assert openbao.test_connection()["ok"] is True


@pytest.mark.parametrize("addr, ok", [
    ("http://127.0.0.1:8200", True),
    ("http://localhost:8200/", True),
    ("https://bao.example.com", True),
    ("http://bao.example.com:8200", False),  # token would travel in clear text
    ("https://user:pw@bao.example.com", False),
    ("https://bao.example.com/v1", False),
    ("file:///etc/passwd", False),
])
def test_address_validation(fresh, addr, ok):
    openbao, _ = fresh
    if ok:
        assert openbao.save({"addr": addr}).addr == addr.rstrip("/")
    else:
        with pytest.raises(ValueError):
            openbao.save({"addr": addr})


@pytest.mark.parametrize("change", [{"path": "../sys/seal"}, {"path": "a/../b"}, {"mount": "a/b"}, {"field": "x y"}])
def test_path_validation(fresh, change):
    openbao, _ = fresh
    with pytest.raises(ValueError):
        openbao.save(change)


def test_env_pins_address_and_token(fresh, monkeypatch):
    openbao, _ = fresh
    monkeypatch.setenv("OMNIVOICE_OPENBAO_ADDR", "https://vault.example.org")
    monkeypatch.setenv("OMNIVOICE_OPENBAO_TOKEN", BAO_TOKEN)
    cfg = openbao.load()
    assert (cfg.addr, cfg.has_token, cfg.env_pinned) == ("https://vault.example.org", True, ("addr", "token"))


def test_api_never_returns_the_secrets(fresh, monkeypatch):
    openbao, _ = fresh
    _server(monkeypatch, openbao, _kv)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers import settings as settings_router
    app = FastAPI()
    app.include_router(settings_router.router)
    c = TestClient(app, client=("127.0.0.1", 12345))
    assert c.get("/api/settings/openbao").json()["enabled"] is False
    r = c.put("/api/settings/openbao", json={"enabled": True, "path": "voicestudio/hf", "token": BAO_TOKEN})
    assert r.status_code == 200 and r.json()["has_token"] is True
    assert c.put("/api/settings/openbao", json={"addr": "http://remote.example:8200"}).status_code == 400
    bodies = [r.text, c.get("/api/settings/openbao").text, c.post("/api/settings/openbao/test").text,
              c.get("/api/settings/hf-token/state").text]
    for body in bodies:
        assert BAO_TOKEN not in body and HF_FROM_BAO not in body
    assert '"masked":"hf_…XYZ"' in bodies[2]
