"""Typhoon Whisper Turbo: catalogue/selection, one-time CTranslate2 conversion,
15 s batched decoding, and whole Thai words from faster-whisper's pieces."""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = "typhoon-ai/typhoon-whisper-turbo"


# ── catalogue, selection, licence ────────────────────────────────────────────

def test_catalogue_lists_it_as_a_thai_only_faster_whisper_model():
    from api.routers.setup.models import KNOWN_MODELS

    row = next(m for m in KNOWN_MODELS if m["repo_id"] == REPO)
    assert row["role"] == "ASR" and row["languages"] == ["th"]
    # whisperx loads its own faster-whisper and does not convert.
    assert row["engines"] == ["faster-whisper", "faster-whisper-isolated"]
    assert "Thai only" in row["label"] and not row.get("curated_on")


def test_settings_may_select_it_for_faster_whisper_only():
    from services.asr_backend import faster_whisper_selectable

    assert faster_whisper_selectable(REPO)
    assert faster_whisper_selectable("Systran/faster-whisper-small")
    assert not faster_whisper_selectable("openai/whisper-large-v3")


def test_conversion_pin_is_the_licence_registry_runtime_revision():
    from core.whisper_ct2 import CONVERTED_MODELS
    from services.hf_revisions import revision_for

    assert CONVERTED_MODELS[REPO]["revision"] == revision_for(REPO)


def test_licence_record_states_the_opentyphoon_terms():
    registry = json.loads((ROOT / "backend/config/model_licenses.json").read_text(encoding="utf-8"))
    row = next(r for r in registry["models"] if r["id"] == REPO)
    # MIT card licence plus the bespoke OpenTyphoon terms ("other"): use needs acceptance.
    assert row["license"] == "mit; other" and row["commercial_use"] is False and row["review_status"] == "unreviewed"
    assert "https://opentyphoon.ai/tac" in row["notes"]
    assert row["engines"] == ["faster-whisper", "faster-whisper-isolated"]


def test_ray_engine_ships_the_helpers_and_installs_their_packages():
    from services.ray_jobs.engines import RAY_ENGINES

    engine = RAY_ENGINES["faster-whisper-isolated"]
    assert {"core/whisper_ct2.py", "core/thai_words.py"} <= {arc for arc, _ in engine.extra_files}
    pins = engine.recipe["install_args"]
    assert "ctranslate2==4.4.0" in pins  # the converter is the engine's own CTranslate2
    assert any(p.startswith("transformers==") for p in pins) and any(p.startswith("pythainlp==") for p in pins)
    assert "TransformersConverter" in engine.recipe["probe_code"]


# ── conversion ───────────────────────────────────────────────────────────────

def _fake_convert(calls, fail=False):
    def convert(source, out):
        calls.append((source, out))
        if fail:
            raise RuntimeError("converter crashed")
        Path(out).mkdir(parents=True)
        (Path(out) / "model.bin").write_bytes(b"ct2")
        (Path(out) / "config.json").write_text("{}")
    return convert


def test_conversion_is_keyed_on_the_revision_and_happens_once(tmp_path):
    from core import whisper_ct2

    downloads, converts, beats = [], [], []

    def download(repo, rev):
        downloads.append((repo, rev))
        return str(tmp_path / "snapshot")

    out = whisper_ct2.ensure_converted(REPO, cache=tmp_path, download=download,
                                       convert=_fake_convert(converts), progress=beats.append)
    rev = whisper_ct2.CONVERTED_MODELS[REPO]["revision"]
    assert out == str(tmp_path / "models--typhoon-ai--typhoon-whisper-turbo" / "voicestudio-ct2" / f"{rev}-float16")
    assert downloads == [(REPO, rev)] and converts[0][0] == str(tmp_path / "snapshot")
    assert converts[0][1] != out  # converted into a temp dir, then renamed
    assert beats  # the sidecar can heartbeat through the silence deadline
    again = whisper_ct2.ensure_converted(REPO, cache=tmp_path, download=download, convert=_fake_convert(converts))
    assert again == out and len(converts) == 1
    assert [p.name for p in Path(out).parent.iterdir()] == [Path(out).name]  # no temp dirs left


def test_a_failed_conversion_leaves_nothing_where_the_engine_looks(tmp_path):
    from core import whisper_ct2

    with pytest.raises(RuntimeError, match="converter crashed"):
        whisper_ct2.ensure_converted(REPO, cache=tmp_path, download=lambda r, v: "src",
                                     convert=_fake_convert([], fail=True))
    parent = tmp_path / "models--typhoon-ai--typhoon-whisper-turbo" / "voicestudio-ct2"
    assert list(parent.iterdir()) == []


def test_another_revision_or_a_half_copy_is_converted_again(tmp_path):
    from core import whisper_ct2

    rev = whisper_ct2.CONVERTED_MODELS[REPO]["revision"]
    final = whisper_ct2.converted_dir(REPO, rev, tmp_path)
    final.mkdir(parents=True)
    (final / "model.bin").write_bytes(b"old")  # no completion marker: an interrupted copy
    calls = []
    whisper_ct2.ensure_converted(REPO, cache=tmp_path, download=lambda r, v: "src", convert=_fake_convert(calls))
    assert len(calls) == 1 and whisper_ct2.is_converted(final, REPO, rev)
    assert not whisper_ct2.is_converted(final, REPO, "0" * 40)


def test_a_concurrent_job_that_finished_first_wins(tmp_path):
    from core import whisper_ct2

    rev = whisper_ct2.CONVERTED_MODELS[REPO]["revision"]
    final = whisper_ct2.converted_dir(REPO, rev, tmp_path)

    def convert(source, out):
        _fake_convert([])(source, out)
        _fake_convert([])(source, str(final))  # the other job renames in first
        (final / ".voicestudio-ct2-complete").write_text(f"{REPO}\n{rev}\n")

    assert whisper_ct2.ensure_converted(REPO, cache=tmp_path, download=lambda r, v: "src", convert=convert) == str(final)
    assert [p.name for p in final.parent.iterdir()] == [final.name]


def test_ordinary_models_are_not_converted():
    from core import whisper_ct2

    assert whisper_ct2.model_settings("Systran/faster-whisper-large-v3") is None
    with pytest.raises(ValueError):
        whisper_ct2.ensure_converted("Systran/faster-whisper-large-v3")


# ── decoding ─────────────────────────────────────────────────────────────────

class _Model:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        return iter(()), types.SimpleNamespace(language="th")


def test_typhoon_decodes_batched_in_15_second_windows(monkeypatch):
    from core import whisper_ct2

    seen = {}

    class Batched:
        def __init__(self, model):
            seen["model"] = model

        def transcribe(self, audio, **kw):
            seen.update(kw)
            return iter(()), None

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(BatchedInferencePipeline=Batched))
    model = _Model()
    whisper_ct2.transcribe(model, "a.wav", REPO, word_timestamps=True, beam_size=5, language="th")
    assert seen["model"] is model and seen["chunk_length"] == 15 and seen["batch_size"] == 8
    assert seen["word_timestamps"] is True and seen["beam_size"] == 5 and seen["language"] == "th"
    assert model.calls == []


def test_other_models_keep_the_plain_30_second_decode():
    from core import whisper_ct2

    model = _Model()
    whisper_ct2.transcribe(model, "a.wav", "Systran/faster-whisper-large-v3", word_timestamps=True)
    assert model.calls == [{"word_timestamps": True}]


# ── Thai words ───────────────────────────────────────────────────────────────

def _w(word, start, end, p=0.9):
    return {"word": word, "start": start, "end": end, "probability": p}


# Real faster-whisper pieces for "ของการเมือง มันมี" (H200 run, Typhoon).
PIECES = [_w("ข", 0.0, 0.14), _w("อง", 0.14, 0.2), _w("ก", 0.2, 0.44, 0.5), _w("าร", 0.44, 0.54),
          _w("เม", 0.54, 0.82), _w("ื", 0.82, 0.86), _w("อง", 0.86, 0.96), _w(" ม", 1.14, 1.58),
          _w("ั", 1.58, 1.62), _w("น", 1.62, 1.62), _w("ม", 1.62, 1.78), _w("ี", 1.78, 1.78)]


def _split(text):  # newmm's answer for the text above, without needing pythainlp
    assert text == "ของการเมือง มันมี"
    return ["ของ", "การเมือง", " ", "มัน", "มี"]


def test_pieces_become_whole_words_with_their_span_and_lowest_probability():
    from core.thai_words import merge_thai_words

    assert merge_thai_words(PIECES, _split) == [
        {"word": "ของ", "start": 0.0, "end": 0.2, "probability": 0.9},
        {"word": "การเมือง", "start": 0.2, "end": 0.96, "probability": 0.5},
        {"word": " มัน", "start": 1.14, "end": 1.62, "probability": 0.9},
        {"word": "มี", "start": 1.62, "end": 1.78, "probability": 0.9},
    ]


def test_a_piece_shared_by_two_words_keeps_times_monotonic():
    from core.thai_words import merge_thai_words

    pieces = [_w("อ", 0.0, 0.2), _w("ันน", 0.2, 0.4), _w("ี้", 0.4, 0.5)]
    words = merge_thai_words(pieces, lambda text: ["อัน", "นี้"])
    assert [w["word"] for w in words] == ["อัน", "นี้"]
    assert words[0]["end"] <= words[1]["start"] <= words[1]["end"]


def test_unmergeable_input_is_returned_unchanged():
    from core.thai_words import merge_thai_words

    assert merge_thai_words(PIECES, lambda text: ["something", "else"]) is PIECES
    assert merge_thai_words(PIECES, lambda text: 1 / 0) is PIECES
    assert merge_thai_words([], _split) == []


def test_only_thai_segments_are_merged():
    from core.thai_words import merge_segment_words

    english = [{"words": [_w(" hel", 0, 1), _w("lo", 1, 2)]}]
    assert merge_segment_words(english, "en")[0]["words"] == [_w(" hel", 0, 1), _w("lo", 1, 2)]


def test_newmm_merges_real_pieces():
    pytest.importorskip("pythainlp")
    from core.thai_words import merge_segment_words

    segments = merge_segment_words([{"words": [dict(p) for p in PIECES]}], "th")
    assert [w["word"].strip() for w in segments[0]["words"]] == ["ของ", "การเมือง", "มัน", "มี"]


# ── engines ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sidecar(monkeypatch):
    path = ROOT / "backend" / "engines" / "_asr_sidecar" / "main.py"
    spec = importlib.util.spec_from_file_location("asr_sidecar_typhoon", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seg(words):
    return types.SimpleNamespace(start=0.0, end=2.0, text="".join(w["word"] for w in words),
                                 words=[types.SimpleNamespace(**w) for w in words])


def test_sidecar_converts_typhoon_and_returns_thai_words(sidecar, monkeypatch):
    from core import execstack, thai_words, whisper_ct2

    monkeypatch.setenv("ASR_MODEL_FW", REPO)
    monkeypatch.setattr(execstack, "ensure_ctranslate2_loadable", lambda: (True, ""))
    converted, loaded, decoded = [], [], []
    monkeypatch.setattr(whisper_ct2, "ensure_converted",
                        lambda name, progress=None: converted.append(name) or "/cache/ct2")

    class WhisperModel:
        def __init__(self, source, **kw):
            loaded.append(source)

    def transcribe(model, audio, name, **kw):
        decoded.append((name, kw))
        return iter([_seg(PIECES)]), types.SimpleNamespace(language="th")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WhisperModel))
    monkeypatch.setattr(whisper_ct2, "transcribe", transcribe)
    real = thai_words.merge_thai_words
    monkeypatch.setattr(thai_words, "merge_thai_words", lambda words, tokenize=None: real(words, _split))
    result = sidecar._transcribe("a.wav", True, {"beam_size": 5}, {"language": "th"})
    assert converted == [REPO] and loaded == ["/cache/ct2"]
    assert decoded == [(REPO, {"word_timestamps": True, "beam_size": 5, "language": "th"})]
    assert [w["word"] for w in result["segments"][0]["words"]] == ["ของ", "การเมือง", " มัน", "มี"]


def test_in_process_faster_whisper_loads_the_conversion(monkeypatch):
    from core import whisper_ct2
    from services import asr_backend

    loaded = []
    monkeypatch.setattr(asr_backend, "_ctranslate2_execstack_ok", lambda: (True, ""))
    monkeypatch.setattr(asr_backend, "_ctranslate2_cuda_ok", lambda: False)
    monkeypatch.setattr(whisper_ct2, "ensure_converted", lambda name, progress=None: "/cache/ct2")
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(
        WhisperModel=lambda source, **kw: loaded.append(source) or object()))
    asr_backend.FasterWhisperBackend(model_name=REPO)._ensure_model()
    assert loaded == ["/cache/ct2"]


def test_local_isolated_transcribe_waits_through_conversion_heartbeats(monkeypatch):
    from services import subprocess_asr as sa

    backend = sa.IsolatedFasterWhisperBackend()
    replies = iter([{"op": "progress", "stage": "loading", "message": "converting"},
                    {"op": "progress", "stage": "loading", "message": "converting"},
                    {"op": "segments", "result": {"segments": [], "language": "th"}}])
    monkeypatch.setattr(sa, "_ray_route", lambda engine: None)
    monkeypatch.setattr("services.model_manager.running_on_gpu_pool", lambda: True)
    monkeypatch.setattr(backend, "_spawn", lambda: None)
    monkeypatch.setattr(backend, "_send", lambda msg: None)
    monkeypatch.setattr(backend, "_recv_with_timeout", lambda timeout: next(replies), raising=False)
    backend._last_recv_timed_out = False
    assert backend.transcribe("a.wav")["language"] == "th"
