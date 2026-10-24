import importlib.util
import plistlib
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ios-testflight.yml"
SPEC = importlib.util.spec_from_file_location("prepare_resources", ROOT / "mobile/ios/scripts/prepare_resources.py")
prepare_resources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_resources)


def load_workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


@pytest.mark.parametrize(("version", "expected"), [("0.5.7", "0.5.7"), ("0.5.8-beta.2", "0.5.8")])
def test_marketing_version_is_app_store_shaped(version, expected):
    assert prepare_resources.marketing_version(version) == expected


@pytest.mark.parametrize("version", ["0.5", "0.5.8-rc.1", "v0.5.8"])
def test_marketing_version_rejects_unsupported_versions(version):
    with pytest.raises(ValueError):
        prepare_resources.marketing_version(version)


def test_build_number_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICESTUDIO_IOS_BUILD_NUMBER", "42.2")
    prepare_resources.prepare(tmp_path / "bundle", tmp_path / "Info.plist")
    info = plistlib.loads((tmp_path / "Info.plist").read_bytes())
    assert info["CFBundleVersion"] == "42.2"
    assert prepare_resources.re.fullmatch(r"\d+\.\d+\.\d+", info["CFBundleShortVersionString"])


@pytest.mark.parametrize("value", ["", "1.2.3.4", "12a"])
def test_build_number_rejects_values_app_store_connect_refuses(value):
    with pytest.raises(ValueError):
        prepare_resources.build_number(value)


def test_workflow_is_manual_main_only_and_read_only():
    workflow = load_workflow()
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["testflight"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["environment"] == "app-store-connect"
    assert "github.run_attempt" in job["env"]["VOICESTUDIO_IOS_BUILD_NUMBER"]


def test_workflow_signs_verifies_and_cleans_up_the_key():
    steps = load_workflow()["jobs"]["testflight"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Verify archive signature and version") < names.index("Upload to TestFlight")
    cleanup = steps[-1]
    assert cleanup["name"] == "Remove API key" and cleanup["if"] == "always()"
    source = WORKFLOW.read_text()
    assert "CODE_SIGNING_ALLOWED=NO" not in source
    assert "testFlightInternalTestingOnly bool true" in source
    # Secrets reach only the steps that need them, never the whole job.
    assert "secrets." not in yaml.dump(load_workflow()["jobs"]["testflight"].get("env", {}))


def test_archive_check_matches_automatic_signing():
    # The archive carries the development identity until export re-signs it, so
    # requiring Apple Distribution here failed every run; check the team instead.
    steps = load_workflow()["jobs"]["testflight"]["steps"]
    verify = next(step for step in steps if step.get("name") == "Verify archive signature and version")
    assert "Authority=Apple Distribution" not in verify["run"]
    assert 'TeamIdentifier=$TEAM_ID' in verify["run"]
    assert verify["env"]["TEAM_ID"] == "${{ secrets.APPLE_TEAM_ID }}"


IOS = ROOT / "mobile" / "ios" / "VoiceStudio"


def test_app_store_validation_requirements():
    # Each check mirrors an App Store Connect upload rejection (run 39956020986).
    assert load_workflow()["jobs"]["testflight"]["runs-on"] == "macos-26"
    info = plistlib.loads((IOS / "Info.plist").read_bytes())
    assert info["CFBundleIconName"] == "AppIcon"
    assert set(info["UISupportedInterfaceOrientations~ipad"]) == {
        "UIInterfaceOrientationPortrait",
        "UIInterfaceOrientationPortraitUpsideDown",
        "UIInterfaceOrientationLandscapeLeft",
        "UIInterfaceOrientationLandscapeRight",
    }
    project = yaml.safe_load((IOS / "project.yml").read_text())
    assert project["targets"]["VoiceStudio"]["settings"]["base"]["ASSETCATALOG_COMPILER_APPICON_NAME"] == "AppIcon"


def test_app_icon_is_an_opaque_1024_png():
    png = (IOS / "Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    assert (width, height) == (1024, 1024)
    assert png[25] == 2, "App Store icons must be RGB without an alpha channel"


def test_mobile_ci_builds_ios_with_the_upload_toolchain():
    mobile = yaml.load((ROOT / ".github/workflows/mobile.yml").read_text(), Loader=yaml.BaseLoader)
    assert mobile["jobs"]["ios"]["runs-on"] == load_workflow()["jobs"]["testflight"]["runs-on"]
