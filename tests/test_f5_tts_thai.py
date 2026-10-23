"""F5-TTS-THAI: remote-only engine registration, reference preparation, and
the Ray sidecar's protocol pieces (no model, no cluster)."""
from __future__ import annotations

import base64
import importlib
import importlib.util
import io
import json
import os
import struct
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

SIDECAR = ROOT / "backend" / "engines" / "f5_tts_thai" / "main.py"
SR = 16000


@pytest.fixture
def rs(monkeypatch):
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
    return importlib.import_module("services.ray_jobs.settings")


@pytest.fixture
def routed(rs):
    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["f5-tts-thai"]})
    return rs


def _wav(path: Path, seconds: float) -> str:
    import soundfile as sf

    t = np.arange(int(seconds * SR)) / SR
    sf.write(path, (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), SR)
    return str(path)


# -- recipe and registry ----------------------------------------------------

def test_engine_is_a_gpu_tts_ray_engine_with_a_fully_pinned_recipe():
    from services.ray_jobs.engines import RAY_ENGINES, install_recipe

    engine = RAY_ENGINES["f5-tts-thai"]
    assert (engine.kind, engine.gpu, engine.directory, engine.entry) == ("tts", True, "f5_tts_thai", "main.py")
    recipe = install_recipe("f5-tts-thai")
    assert "torch==2.8.0+cu128" in recipe["cuda_args"] and "torchaudio==2.8.0+cpu" in recipe["cpu_args"]
    pins = dict(arg.split("==") for arg in recipe["install_args"])  # every argument is pinned
    assert pins["f5-tts-th"] == "1.0.9" and pins["numpy"] == "1.26.4"  # f5-tts-th caps numpy
    assert "f5_tts_th.utils_infer" in recipe["probe_code"] and recipe["key"]


def test_package_ships_the_sidecar():
    import zipfile
    from services.ray_jobs.package import build_package

    _, data, _ = build_package({"v": 1, "op": "synthesize", "engine": "f5-tts-thai"}, {})
    assert "engines/f5_tts_thai/main.py" in set(zipfile.ZipFile(io.BytesIO(data)).namelist())


def test_listed_as_a_cloning_tts_engine_for_thai_and_english():
    from services import tts_backend as tb

    cls = tb.get_backend_class("f5-tts-thai")
    assert cls.__name__ == "F5TTSThaiBackend"
    assert cls.supports_cloning and not cls.supports_voice_design
    assert (cls.max_ref_seconds, cls.ref_strategy) == (8.0, "best_window")
    assert cls().supported_languages == ["th", "en"]
    assert "f5-tts-thai" in tb._ENGINE_DOCS and (ROOT / tb._ENGINE_DOCS["f5-tts-thai"]).is_file()


def test_available_only_when_routed_to_the_remote_gpu(rs):
    from engines.f5_tts_thai import F5TTSThaiBackend

    ok, why = F5TTSThaiBackend.is_available()
    assert not ok and "Remote GPU" in why
    with pytest.raises(RuntimeError, match="remote GPU"):
        F5TTSThaiBackend.venv_python()  # never a local sidecar
    rs.save({"enabled": True, "dashboard_url": "https://ray.example.com", "engines": ["f5-tts-thai"]})
    assert F5TTSThaiBackend.is_available() == (True, "ready")


def test_licence_gate_names_the_fine_tune_and_the_vocoder():
    from services.model_acceptance import repos_for_engine, status

    assert set(repos_for_engine("f5-tts-thai")) == {"VIZINTZOR/F5-TTS-THAI", "charactr/vocos-mel-24khz"}
    assert status("VIZINTZOR/F5-TTS-THAI")["category"] == "noncommercial"  # base SWivid/F5-TTS terms
    src = SIDECAR.read_text(encoding="utf-8")
    rows = json.loads((ROOT / "backend/config/model_licenses.json").read_text(encoding="utf-8"))["models"]
    for row in rows:
        if "f5-tts-thai" in (row.get("engines") or []):
            assert f'"{row["runtime_revision"]}"' in src  # the record pins what the sidecar loads


# -- reference preparation --------------------------------------------------

@pytest.fixture
def backend(monkeypatch, routed):
    from engines.f5_tts_thai import F5TTSThaiBackend

    return F5TTSThaiBackend()


def test_short_reference_without_a_transcript_is_transcribed_once_per_render(backend, tmp_path, monkeypatch):
    from services import asr_backend

    calls = []
    monkeypatch.setattr(asr_backend, "transcribe_reference", lambda p: calls.append(p) or " สวัสดีครับ ")
    ref = _wav(tmp_path / "ref.wav", 5)
    with backend._reference_scope():
        kw = backend._prepare_generate_kwargs("x", {"ref_audio": ref})
        backend._prepare_generate_kwargs("y", {"ref_audio": ref})
    assert kw == {"ref_audio": ref, "ref_text": "สวัสดีครับ"} and calls == [ref]


def test_short_reference_keeps_a_typed_transcript(backend, tmp_path, monkeypatch):
    from services import asr_backend

    monkeypatch.setattr(asr_backend, "transcribe_reference", lambda p: pytest.fail("must not transcribe"))
    ref = _wav(tmp_path / "ref.wav", 5)
    assert backend._prepare_generate_kwargs("x", {"ref_audio": ref, "ref_text": "typed"})["ref_text"] == "typed"


def test_short_reference_with_no_transcript_and_no_recognizer_says_what_to_do(backend, tmp_path, monkeypatch):
    from services import asr_backend

    monkeypatch.setattr(asr_backend, "transcribe_reference", lambda p: None)
    with pytest.raises(RuntimeError, match="transcript"):
        with backend._reference_scope():
            backend._prepare_generate_kwargs("x", {"ref_audio": _wav(tmp_path / "ref.wav", 5)})


def test_long_reference_uses_its_best_8s_window_and_deletes_it_after_the_render(backend, tmp_path, monkeypatch):
    from services import tts_backend as tb

    window = tmp_path / "window.wav"
    window.write_bytes(b"x")
    seen = []
    monkeypatch.setattr(tb, "best_reference_window", lambda p, s: seen.append((p, s)) or (str(window), "คำพูด"))
    ref = _wav(tmp_path / "long.wav", 20)
    with backend._reference_scope():
        kw = backend._prepare_generate_kwargs("x", {"ref_audio": ref, "ref_text": "whole clip transcript"})
        assert kw == {"ref_audio": str(window), "ref_text": "คำพูด"} and window.exists()
    assert seen == [(ref, 8.0)] and not window.exists()


def test_long_reference_without_a_recognizer_fails_with_the_limit(backend, tmp_path, monkeypatch):
    from services import tts_backend as tb

    monkeypatch.setattr(tb, "best_reference_window", lambda p, s: None)
    with pytest.raises(RuntimeError, match="at most 8 seconds"):
        with backend._reference_scope():
            backend._prepare_generate_kwargs("x", {"ref_audio": _wav(tmp_path / "long.wav", 20)})


def test_no_reference_is_left_to_the_sidecar_sample_voice(backend):
    assert backend._prepare_generate_kwargs("x", {"language": "th"}) == {"language": "th"}


def test_routed_batch_is_one_job_carrying_each_prepared_reference(backend, tmp_path, monkeypatch):
    from services import asr_backend
    from services import subprocess_backend as sb
    from services.ray_jobs import runtime
    from services.ray_jobs.executor import RayJobResult

    monkeypatch.setattr(asr_backend, "transcribe_reference", lambda p: "ข้อความอ้างอิง")
    monkeypatch.setattr(sb, "_RAY_INSTALLED", set())
    monkeypatch.setattr(runtime, "executor_for", lambda cfg: object())
    pcm = base64.b64encode(np.zeros(240, dtype="<i2").tobytes()).decode()
    tasks = []

    def run_sync(cfg, task, **_kw):
        tasks.append(task)
        items = task.params["items"]
        return RayJobResult("vs-x", {"op": "batch", "results": [
            {"op": "audio", "audio_pcm_b64": pcm, "audio_format": "s16le", "sample_rate": 24000}] * len(items)},
            [], 0.1)

    monkeypatch.setattr(runtime, "run_sync", run_sync)
    monkeypatch.setattr(backend, "_validate_generate_authorization", lambda: None)
    assert backend.has_native_batch
    ref = _wav(tmp_path / "ref.wav", 4)
    out = backend.generate_batch(["สวัสดี", "Hello"], ref_audio=ref, language=["th", "en"])
    assert len(out) == 2 and len(tasks) == 1 and tasks[0].op == "batch" and tasks[0].engine == "f5-tts-thai"
    items = tasks[0].params["items"]
    assert [i["ref_text"] for i in items] == ["ข้อความอ้างอิง"] * 2 and items[0]["ref_audio"].startswith("@")
    assert len(tasks[0].inputs) == 1  # the same clip ships once


def test_best_reference_window_ranks_8s_windows_and_remembers_them_apart_from_15s(tmp_path, monkeypatch):
    import soundfile as sf
    from services import asr_backend
    from services import tts_backend as tb

    monkeypatch.setattr(tb, "_reference_asr_identity", lambda: "fake:asr")
    texts = iter(["one", "the most spoken words here", "two"])
    heard = []

    def transcribe(path):
        heard.append(sf.info(path).duration)
        return next(texts)

    monkeypatch.setattr(asr_backend, "transcribe_reference", transcribe)
    ref = _wav(tmp_path / "long.wav", 20)
    path, text = tb.best_reference_window(ref, 8.0)
    try:
        assert text == "the most spoken words here" and abs(sf.info(path).duration - 8.0) < 0.01
        assert heard[:2] == [8.0, 8.0] and len(heard) == 3
        assert tb._recall_passage(ref, 8.0) == (1, text) and tb._recall_passage(ref) is None
    finally:
        os.remove(path)
    again, again_text = tb.best_reference_window(ref, 8.0)  # recalled, not re-ranked
    os.remove(again)
    assert again_text == text and len(heard) == 3


# -- sidecar ----------------------------------------------------------------

@pytest.fixture
def sidecar():
    spec = importlib.util.spec_from_file_location("f5_tts_thai_sidecar", SIDECAR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frames(raw: bytes) -> list[dict]:
    out, pos = [], 0
    while pos < len(raw):
        (n,) = struct.unpack("!I", raw[pos:pos + 4])
        out.append(json.loads(raw[pos + 4:pos + 4 + n]))
        pos += 4 + n
    return out


def test_sidecar_speaks_the_wire_protocol_without_the_model():
    def frame(obj):
        body = json.dumps(obj).encode()
        return struct.pack("!I", len(body)) + body

    proc = subprocess.run([sys.executable, str(SIDECAR)], capture_output=True, timeout=60,
                          input=frame({"op": "ping"}) + frame({"op": "nope"}) + frame({"op": "shutdown"}))
    frames = _frames(proc.stdout)
    assert proc.returncode == 0
    assert frames[0] == {"op": "ready", "engine": "f5-tts-thai"} and frames[1] == {"op": "pong"}
    assert frames[2]["op"] == "error" and frames[2]["stage"] == "dispatch"


def test_sidecar_refuses_a_reference_without_its_transcript(sidecar):
    with pytest.raises(ValueError, match="ref_text"):
        sidecar._reference({"ref_audio": "/x.wav", "ref_text": "  "})


def test_sidecar_falls_back_to_the_pinned_sample_voice(sidecar, monkeypatch):
    calls = []
    hub = types.SimpleNamespace(hf_hub_download=lambda repo, name, revision: calls.append((repo, name, revision))
                                or f"/cache/{name}")
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    path, text = sidecar._reference({})
    assert path == "/cache/sample/ref_audio.wav" and text == sidecar.SAMPLE_REF_TEXT
    assert calls == [(sidecar.MODEL_REPO, "sample/ref_audio.wav", sidecar.MODEL_REVISION)]


@pytest.mark.parametrize("speed, expected", [(None, 1.0), (0.8, 0.8), (9, 2.0), (0.1, 0.5), ("x", 1.0),
                                             (float("nan"), 1.0)])
def test_sidecar_speed_is_clamped(sidecar, speed, expected):
    assert sidecar._speed({"speed": speed}) == expected


def test_sidecar_synthesize_returns_audio_and_removes_its_reference_copy(sidecar, tmp_path):
    copy = tmp_path / "prepared.wav"
    seen = {}

    def preprocess(ref_audio, ref_text, show_info=None):
        copy.write_bytes(b"x")
        return str(copy), ref_text + ". "

    def infer(ref_audio, ref_text, text, model, vocoder, **kw):
        seen.update(ref_text=ref_text, text=text, speed=kw["speed"], steps=kw["nfe_step"])
        return np.array([0.5, -2.0, 0.0], dtype=np.float32), 24000, None

    sidecar._engine = ("model", "vocoder", infer, preprocess)
    out = io.BytesIO()
    reply = sidecar._synthesize(out, {"text": " สวัสดี ", "ref_audio": "/in.wav", "ref_text": "อ้างอิง",
                                      "speed": 0.8, "seed": -5, "audio_format": "f32le"})
    samples = np.frombuffer(base64.b64decode(reply["audio_pcm_b64"]), dtype="<f4")
    assert reply["op"] == "audio" and reply["sample_rate"] == 24000 and reply["n_samples"] == 3
    assert samples.tolist() == [0.5, -1.0, 0.0]  # clipped
    assert seen == {"ref_text": "อ้างอิง. ", "text": "สวัสดี", "speed": 0.8, "steps": 32}
    assert not copy.exists()
