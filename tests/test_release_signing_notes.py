"""Release notes describe the signing each platform leg measured (v0.5.7-beta.1 follow-up)."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_signing_notes", ROOT / "scripts/release_signing_notes.py")
notes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notes)


def write(tmp_path, platform, arch, status):
    (tmp_path / f"signing-{platform}-{arch}.json").write_text(
        json.dumps({"platform": platform, "arch": arch, "status": status})
    )


def test_table_lists_each_platform_with_its_measured_status(tmp_path):
    write(tmp_path, "linux", "x64", "not-applicable")
    write(tmp_path, "win32", "x64", "unsigned")
    write(tmp_path, "darwin", "arm64", "notarized")
    write(tmp_path, "darwin", "x64", "adhoc")
    text = notes.render(tmp_path)
    rows = [line for line in text.splitlines() if line.startswith("| ") and "Platform" not in line]
    assert [row.split(" | ")[0] for row in rows] == [
        "| macOS (Apple Silicon)", "| macOS (Intel)", "| Windows x64", "| Linux x64",
    ]
    assert "✅ Signed with Developer ID and notarized" in rows[0]
    assert rows[1].count("⚠️") == 1 and "shell installer" in rows[1]
    assert "SmartScreen" in rows[2]
    assert "### Installer signing" in text


@pytest.mark.parametrize("platform,arch,status", [("darwin", "arm64", "signed-ish"), ("plan9", "x64", "signed")])
def test_unknown_reports_fail_instead_of_rendering(tmp_path, platform, arch, status):
    write(tmp_path, platform, arch, status)
    with pytest.raises(ValueError):
        notes.render(tmp_path)


def test_missing_reports_fail(tmp_path):
    with pytest.raises(ValueError):
        notes.render(tmp_path)


def load_workflow():
    return yaml.load((ROOT / ".github/workflows/electron-release.yml").read_text(), Loader=yaml.BaseLoader)


def test_every_package_leg_reports_and_mac_check_ignores_allow_unsigned():
    steps = {step.get("name"): step for step in load_workflow()["jobs"]["package"]["steps"]}
    mac = steps["Report and enforce macOS signing"]
    # Runs on every macOS build, published or not, and allow_unsigned cannot skip it.
    assert mac["if"] == "matrix.platform == 'darwin'"
    assert 'codesign --verify --deep --strict "$APP"' in mac["run"]
    assert mac["env"]["HAS_CREDENTIALS"] == "${{ secrets.ELECTRON_MACOS_CSC_LINK != '' }}"
    windows = steps["Report and enforce Windows signing"]
    assert windows["if"] == "matrix.platform == 'win32'"
    assert windows["env"]["HAS_CREDENTIALS"] == "${{ secrets.ELECTRON_WINDOWS_CSC_LINK != '' }}"
    assert steps["Report Linux signing"]["if"] == "matrix.platform == 'linux'"
    assert steps["Save the signing report"]["with"]["name"] == "electron-signing-${{ matrix.platform }}-${{ matrix.arch }}"


def test_release_notes_are_built_from_the_reports():
    steps = load_workflow()["jobs"]["release"]["steps"]
    describe = next(step for step in steps if step.get("name") == "Describe installer signing per platform")
    assert "if" not in describe
    assert describe["run"] == "python3 scripts/release_signing_notes.py release-signing >> release-assets/RELEASE_NOTES.md"
    assert not any("Electron installer trust" in step.get("run", "") for step in steps)
