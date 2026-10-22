"""Typhoon Translate Ray sidecar: prompt, output cleaning, batching (fake model)."""
from __future__ import annotations

import importlib.util
import io
import json
import struct
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

PATH = Path(__file__).resolve().parents[1] / "backend" / "engines" / "typhoon_translate" / "main.py"


@pytest.fixture
def sidecar():
    spec = importlib.util.spec_from_file_location("typhoon_translate_sidecar", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prompt_without_rules_is_the_model_card_prompt(sidecar):
    assert sidecar.build_prompt("Hello", "English", "Thai") == (
        "Translate the following English text into Thai and return only the translated text.\n"
        "Source Text:\nHello")


def test_prompt_numbers_the_rules(sidecar):
    prompt = sidecar.build_prompt("สวัสดี", "Thai", "English", ['Translate "a" as "b".', " ", 'Translate "c" as "d".'])
    assert prompt == (
        "Translate the following Thai text into English, strictly following the rules below and return only "
        "the translated text.\nRules:\n1. Translate \"a\" as \"b\".\n2. Translate \"c\" as \"d\".\n"
        "Source Text:\nสวัสดี")


def test_prompt_refuses_other_pairs(sidecar):
    with pytest.raises(ValueError):
        sidecar.build_prompt("Hi", "English", "French")


def test_glossary_rules_apply_only_to_rows_with_their_term(sidecar):
    rules = ['Translate "campaign" as "แคมเปญ".', 'Translate "Q3 report" as "รายงานไตรมาส 3".', "Use a formal tone."]
    assert sidecar.rules_for("Our new Campaigns start Monday.", rules) == [rules[0], rules[2]]
    assert sidecar.rules_for("Break a leg tonight!", rules) == [rules[2]]


@pytest.mark.parametrize("raw, source, expected", [
    ("สวัสดี", "Hello", "สวัสดี"),
    ("  \"สวัสดี\"  ", "Hello", "สวัสดี"),
    ("“สวัสดี”", "Hello", "สวัสดี"),
    ("\"Hi\"", "\"สวัสดี\"", "\"Hi\""),  # the source was quoted: keep the quotes
    ("Source Text:\nHello\nสวัสดี", "Hello", "สวัสดี"),
    ("Source Text: สวัสดี", "Hello", "สวัสดี"),
    ("สวัสดี\nSource Text:\nHello", "Hello", "สวัสดี"),
    ("<think>\n</think>\n\nสวัสดี", "Hello", "สวัสดี"),
    ("Translated text: สวัสดี", "Hello", "สวัสดี"),
])
def test_clean_output_strips_echoes_and_quotes(sidecar, raw, source, expected):
    assert sidecar.clean_output(raw, source) == expected


class _Enc(dict):
    def to(self, device):
        return self


class FakeTokenizer:
    pad_token_id = 0

    def __init__(self, replies):
        self.replies = replies  # source text -> raw model output
        self.batches = []

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, enable_thinking):
        assert not tokenize and add_generation_prompt and enable_thinking is False
        return "<user>" + messages[0]["content"] + "<assistant>"

    def __call__(self, text, **kw):
        if isinstance(text, str):  # length of one source text
            return {"input_ids": text.split()}
        assert kw["padding"] is True and kw["add_special_tokens"] is False
        self.batches.append([p.split("Source Text:\n", 1)[1][:-len("<assistant>")] for p in text])
        return _Enc(input_ids=torch.zeros((len(text), 3), dtype=torch.long))

    def batch_decode(self, tokens, skip_special_tokens):
        sources = self.batches[-1]
        return [self.replies[sources[int(row[0])]] for row in tokens]


class FakeModel:
    """Fails a batch holding "BOOM" with other rows, and any batch holding "FAIL"."""

    def __init__(self, tokenizer):
        self.tokenizer, self.calls = tokenizer, []

    def generate(self, input_ids, max_new_tokens, do_sample, pad_token_id):
        sources = self.tokenizer.batches[-1]
        self.calls.append((list(sources), max_new_tokens, do_sample))
        if "FAIL" in sources or ("BOOM" in sources and len(sources) > 1):
            raise RuntimeError("bad row" if "FAIL" in sources else "batch failed")
        return torch.cat([input_ids, torch.arange(len(sources))[:, None]], dim=1)


def _frames(buffer: io.BytesIO) -> list:
    data, out = buffer.getvalue(), []
    while data:
        (n,) = struct.unpack("!I", data[:4])
        out.append(json.loads(data[4:4 + n]))
        data = data[4 + n:]
    return out


def test_translate_batches_retries_rows_and_reports_progress(sidecar):
    tokenizer = FakeTokenizer({"one": "หนึ่ง", "two two": "\"สอง\"", "BOOM": "บูม", "FAIL": "x",
                               "four": "Source Text:\nfour\nสี่"})
    model = FakeModel(tokenizer)
    sidecar._model, sidecar._tokenizer, sidecar._device, sidecar._loaded_key = model, tokenizer, "cpu", ("m", "r")
    out = io.BytesIO()
    reply = sidecar._translate(out, {"model": "m", "revision": "r", "src": "English", "batch_size": 2,
                                     "rules": ['Translate "x" as "y".'],
                                     "groups": [{"tgt": "Thai", "texts": ["one", "two two", " ", "BOOM", "FAIL", "four"]}]})
    group = reply["groups"][0]
    assert group["texts"] == ["หนึ่ง", "สอง", " ", "บูม", "FAIL", "สี่"]
    assert group["errors"][:4] == [None] * 4 and "bad row" in group["errors"][4] and group["errors"][5] is None
    # Width 2 over the non-blank rows; the failed batch is retried row by row.
    assert [c[0] for c in model.calls] == [["one", "two two"], ["BOOM", "FAIL"], ["BOOM"], ["FAIL"], ["four"]]
    assert model.calls[0][1:] == (64 + 4 * 2, False)  # greedy; budget from the longest input
    progress = [f for f in _frames(out) if f.get("stage") == "translating"]
    assert [f["percent"] for f in progress] == [40.0, 80.0, 100.0]


def test_an_empty_translation_is_a_row_error(sidecar):
    tokenizer = FakeTokenizer({"Hello": "  \"\"  "})
    sidecar._model, sidecar._tokenizer, sidecar._device, sidecar._loaded_key = FakeModel(tokenizer), tokenizer, "cpu", ("m", "")
    reply = sidecar._translate(io.BytesIO(), {"model": "m", "src": "English",
                                              "groups": [{"tgt": "Thai", "texts": ["Hello"]}]})
    assert reply["groups"][0]["texts"] == ["Hello"] and "empty translation" in reply["groups"][0]["errors"][0]


def test_nllb_sidecar_progress_reaches_100_with_blank_rows():
    """Same progress contract in the NLLB sidecar: blank rows are not work."""
    spec = importlib.util.spec_from_file_location("nllb_sidecar", PATH.parents[1] / "nllb" / "main.py")
    nllb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nllb)

    class Tok:
        src_lang = None

        def __call__(self, texts, **kw):
            return _Enc(input_ids=list(texts))

        def convert_tokens_to_ids(self, tgt):
            return tgt

        def batch_decode(self, tokens, skip_special_tokens):
            return [f"t:{t}" for t in tokens]

    class Model:
        def generate(self, input_ids, **kw):
            return input_ids

    nllb._model, nllb._tokenizer, nllb._device, nllb._loaded_key = Model(), Tok(), "cpu", ("m", "")
    out = io.BytesIO()
    reply = nllb._translate(out, {"model": "m", "src": "eng_Latn", "batch_size": 1,
                                  "groups": [{"tgt": "tha_Thai", "texts": ["a", " ", "b"]}]})
    assert reply["groups"][0]["texts"] == ["t:a", " ", "t:b"]
    assert [f["percent"] for f in _frames(out) if f.get("stage") == "translating"] == [50.0, 100.0]
