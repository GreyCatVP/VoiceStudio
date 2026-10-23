"""Exported audio tracks carry a language and name players can read (MP4/MKV)."""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core.iso639 import audio_stream_tags, iso639_2b

ROOT = Path(__file__).resolve().parents[1]


def test_two_letter_and_regional_codes_become_iso639_2b():
    assert iso639_2b("th") == "tha"
    assert iso639_2b("en") == "eng"
    assert iso639_2b("ja") == "jpn"
    assert iso639_2b("zh-CN") == "chi"
    assert iso639_2b("fr") == "fre"
    assert iso639_2b("fra") == "fre"
    assert iso639_2b("tha") == "tha"
    assert iso639_2b("und") == "und"
    assert iso639_2b("") == "und"
    assert iso639_2b("not a code") == "und"


def test_every_dub_language_has_a_three_letter_code():
    src = (ROOT / "backend/api/routers/dub_translate.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    flores = next(
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "FLORES_CODES" for t in node.targets)
    )
    for key in ast.literal_eval(flores):
        code = iso639_2b(key)
        assert code != "und" and len(code) == 3, (key, code)


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
@pytest.mark.parametrize("ext", ["mp4", "mkv"])
def test_ffprobe_reads_language_and_title_from_the_export(tmp_path, ext):
    out = tmp_path / f"dub.{ext}"
    cmd = [
        "ffmpeg", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=32x32:d=0.3",
        "-f", "lavfi", "-i", "sine=d=0.3",
        "-f", "lavfi", "-i", "sine=f=600:d=0.3",
        "-map", "0:v", "-map", "1:a", "-map", "2:a",
        "-c:v", "libx264", "-c:a", "aac",
        *audio_stream_tags(0, "und", "Original"),
        *audio_stream_tags(1, "th", "Thai"),
        "-y", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream_tags", "-of", "json", str(out)],
        check=True, capture_output=True, text=True,
    )
    tags = [
        {k.lower(): v for k, v in s.get("tags", {}).items()}
        for s in json.loads(probe.stdout)["streams"]
    ]
    assert tags[1]["language"] == "tha"
    name = "handler_name" if ext == "mp4" else "title"
    assert tags[0][name] == "Original"
    assert tags[1][name] == "Thai"


def test_stream_metadata_is_only_written_through_the_tag_helper():
    """A raw ``-metadata:s:...`` arg skips the ISO 639-2 conversion."""
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "backend").rglob("*.py")
        if "tests" not in path.parts
        and path.name != "iso639.py"
        and "-metadata:s" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []
