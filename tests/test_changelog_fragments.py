"""Changelog fragments (`changelog.d/`): lint every fragment and prove assembly."""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import changelog_fragments as cf  # noqa: E402
from test_changelog_style import (  # noqa: E402
    _CREDIT, _MAX_ENTRY_CHARS, _REF_AT_END, lint_changelog,
)

SAMPLE = """# Changelog

## [Unreleased]

**Highlights**

- One highlight

### Changed

- Existing change (#1)

### Fixed

- Existing fix (#2)

## [0.5.7] — 2026-10-01

### Fixed

- Old (#3)
"""

EMPTY_UNRELEASED = """# Changelog

## [Unreleased]

## [0.5.7] — 2026-10-26

**Highlights**

- First released highlight
- Second released highlight
- Third released highlight

### Fixed

- Old fix (#3)
"""


def _write(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")


def test_every_repo_fragment_is_one_valid_line():
    problems = []
    for path in cf.fragment_files():
        entry = cf.entry_of(path)
        kind = cf.NAME.match(path.name).group("type")
        ident = re.match(r"\d*", cf.NAME.match(path.name).group("id")).group()
        if len(entry) > _MAX_ENTRY_CHARS:
            problems.append(f"{path.name}: longer than {_MAX_ENTRY_CHARS} characters")
        if kind in ("added", "fixed") and not (_REF_AT_END.search(entry) or _CREDIT.search(entry)):
            problems.append(f"{path.name}: needs a (#N) reference or a thanks credit")
        if ident and not re.search(rf"#{ident}\b", entry):
            problems.append(f"{path.name}: should reference its own PR (#{ident})")
    assert not problems, "\n".join(problems)


def test_stray_files_in_the_fragment_directory_are_named_correctly():
    allowed = {"README.md"}
    bad = [
        p.name for p in (cf.FRAGMENT_DIR).iterdir()
        if p.is_file() and p.name not in allowed and not cf.NAME.match(p.name)
    ]
    assert not bad, f"not <id>.<type>.md: {bad}"


def test_repo_fragments_fold_into_a_changelog_that_passes_the_style_lint():
    """Keep repository fragments compatible with the changelog style gate."""
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
        folded = cf.apply_fragments(fh.read(), cf.read_fragments())
    assert not lint_changelog(folded)


def test_entries_land_under_their_heading_newest_first(tmp_path):
    _write(tmp_path, "10.fixed.md", "- Older fix (#10)\n")
    _write(tmp_path, "11.fixed.md", "Newer fix (#11)\n")
    out = cf.apply_fragments(SAMPLE, cf.read_fragments(tmp_path))
    fixed = out.split("### Fixed\n\n", 1)[1]
    assert fixed.startswith("- Newer fix (#11)\n- Older fix (#10)\n- Existing fix (#2)\n")


def test_missing_sections_are_created_in_canonical_order(tmp_path):
    _write(tmp_path, "20.added.md", "New thing (#20)\n")
    _write(tmp_path, "21.ci.md", "Faster runs (#21)\n")
    out = cf.apply_fragments(SAMPLE, cf.read_fragments(tmp_path))
    unreleased = out.split("## [0.5.7]")[0]
    order = re.findall(r"^### (\w+)", unreleased, re.M)
    assert order == ["Changed", "Added", "Fixed", "CI"]
    assert "## [0.5.7] — 2026-10-01\n\n### Fixed\n\n- Old (#3)" in out


def test_assembly_is_idempotent_and_leaves_released_sections_alone(tmp_path):
    _write(tmp_path, "30.changed.md", "Tweaked (#30)\n")
    frags = cf.read_fragments(tmp_path)
    once = cf.apply_fragments(SAMPLE, frags)
    assert cf.apply_fragments(once, frags) == once
    assert once.endswith("- Old (#3)\n")


def test_multi_line_fragment_is_rejected(tmp_path):
    _write(tmp_path, "40.fixed.md", "One (#40)\nTwo\n")
    with pytest.raises(ValueError, match="exactly one line"):
        cf.read_fragments(tmp_path)


def test_removal_keeps_the_readme(tmp_path):
    _write(tmp_path, "README.md", "doc")
    _write(tmp_path, "50.docs.md", "Doc (#50)\n")
    assert cf.remove_fragments(tmp_path) == ["50.docs.md"]
    assert (tmp_path / "README.md").exists()


def test_a_bullet_elsewhere_does_not_hide_a_fragment(tmp_path):
    text = SAMPLE.replace("- One highlight", "- Same words (#9)")
    _write(tmp_path, "9.fixed.md", "Same words (#9)\n")
    out = cf.apply_fragments(text, cf.read_fragments(tmp_path))
    assert out.count("Same words (#9)") == 2


def test_suffixed_fragment_names_keep_their_pr_number():
    """Preserve the numeric PR reference in suffixed fragment filenames."""
    assert re.match(r"\d*", cf.NAME.match("3263-b.docs.md").group("id")).group() == "3263"


@pytest.mark.parametrize("count", [1, 2, 3, 5])
def test_empty_unreleased_seeds_up_to_three_newest_fragment_highlights(tmp_path, count):
    """Seed newest Highlights while preserving releases and fold idempotency."""
    entries = [f"Fix number {number} (#{number})" for number in range(1, count + 1)]
    for number, entry in enumerate(entries, start=1):
        _write(tmp_path, f"{number}.fixed.md", entry + "\n")
    fragments = cf.read_fragments(tmp_path)

    folded = cf.apply_fragments(EMPTY_UNRELEASED, fragments)

    preamble = folded.split("### Fixed", 1)[0]
    expected = "**Highlights**\n\n" + "".join(f"- {entry}\n" for entry in reversed(entries[-3:]))
    assert expected in preamble
    assert not lint_changelog(folded)
    assert cf.apply_fragments(folded, fragments) == folded
    assert folded.split("## [0.5.7]", 1)[1] == EMPTY_UNRELEASED.split("## [0.5.7]", 1)[1]
    assert folded.split("### Fixed\n\n", 1)[1].startswith(
        "".join(f"- {entry}\n" for entry in reversed(entries))
    )


def test_generated_highlights_deduplicate_entries_across_sections():
    """List an incoming entry once in Highlights even when sections repeat it."""
    fragments = [
        ("Docs", "Same entry (#10)"),
        ("Fixed", "Same entry (#10)"),
        ("Added", "Newest entry (#11)"),
    ]
    folded = cf.apply_fragments(EMPTY_UNRELEASED, fragments)
    preamble = folded.split("### ", 1)[0]
    assert "**Highlights**\n\n- Newest entry (#11)\n- Same entry (#10)\n\n" in preamble
    assert preamble.count("Same entry (#10)") == 1


@pytest.mark.parametrize("marker", ["**Highlights**", "  **Highlights**  "])
def test_existing_owner_highlights_are_preserved_verbatim(marker):
    """Preserve owner-written Highlights and their surrounding preamble verbatim."""
    text = SAMPLE.replace("**Highlights**", marker, 1)
    before = text.split("## [Unreleased]\n", 1)[1].split("### Changed", 1)[0]

    folded = cf.apply_fragments(text, [("Fixed", "New fix (#42)")])

    after = folded.split("## [Unreleased]\n", 1)[1].split("### Changed", 1)[0]
    assert after == before
    assert folded.count(marker) == 1


@pytest.mark.parametrize("text", [EMPTY_UNRELEASED, SAMPLE, SAMPLE.replace("**Highlights**", "")])
def test_no_fragments_leave_the_entire_changelog_unchanged(text):
    """Leave the complete changelog untouched when no fragments are supplied."""
    assert cf.apply_fragments(text, []) == text


def test_missing_highlights_follow_existing_preamble_before_subsections():
    """Place generated Highlights after the owner preamble and before entry sections."""
    text = EMPTY_UNRELEASED.replace(
        "## [Unreleased]\n\n", "## [Unreleased]\n\nOwner preamble stays as written.\n\n",
    )
    folded = cf.apply_fragments(text, [("Fixed", "New fix (#42)")])
    assert folded.index("Owner preamble stays as written.") < folded.index("**Highlights**")
    assert folded.index("**Highlights**") < folded.index("### Fixed")


def test_existing_folded_entry_can_seed_missing_highlights_without_duplication():
    """Reuse an existing entry as a highlight without duplicating its section bullet."""
    text = EMPTY_UNRELEASED.replace(
        "## [Unreleased]\n\n", "## [Unreleased]\n\n### Fixed\n\n- Existing fix (#7)\n\n",
    )
    folded = cf.apply_fragments(text, [("Fixed", "Existing fix (#7)")])
    assert folded.split("### Fixed", 1)[0].count("Existing fix (#7)") == 1
    assert folded.count("Existing fix (#7)") == 2
    assert not lint_changelog(folded)


def test_generated_highlights_preserve_literal_fragment_text():
    """Copy fragment text literally, including Windows path backslashes."""
    entry = r"Keep C:\models\1 intact (#42)"
    folded = cf.apply_fragments(EMPTY_UNRELEASED, [("Fixed", entry)])
    assert f"**Highlights**\n\n- {entry}\n\n" in folded.split("### Fixed", 1)[0]


def test_generated_highlights_use_only_incoming_fragment_entries():
    """Choose Highlights from incoming fragments rather than older folded entries."""
    text = EMPTY_UNRELEASED.replace(
        "## [Unreleased]\n\n", "## [Unreleased]\n\n### Fixed\n\n- Earlier entry (#1)\n\n",
    )
    folded = cf.apply_fragments(text, [("Fixed", "Current fragment (#2)")])
    preamble = folded.split("### Fixed", 1)[0]
    assert "- Current fragment (#2)" in preamble
    assert "Earlier entry (#1)" not in preamble
