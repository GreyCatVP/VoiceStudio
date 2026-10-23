from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "android-play-internal.yml"
GRADLE = ROOT / "mobile" / "android" / "app" / "build.gradle.kts"
MOBILE = ROOT / ".github" / "workflows" / "mobile.yml"


def load(path):
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


def test_workflow_is_manual_main_only_and_read_only():
    workflow = load(WORKFLOW)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["play-internal"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["environment"] == "google-play"
    assert "env" not in job


def test_workflow_uploads_only_a_verified_release_bundle_to_internal():
    steps = load(WORKFLOW)["jobs"]["play-internal"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Verify bundle signature") < names.index("Upload to Play internal testing")
    upload = steps[names.index("Upload to Play internal testing")]
    assert upload["with"]["track"] == "internal"
    assert upload["with"]["packageName"] == "sh.voicestudio.mobile"
    cleanup = steps[-1]
    assert cleanup["name"] == "Remove upload keystore" and cleanup["if"] == "always()"
    build = steps[names.index("Build signed bundle")]
    assert "GITHUB_RUN_ATTEMPT" in build["run"] and ":app:bundleRelease" in build["run"]


def test_gradle_signs_release_only_with_the_upload_key_and_parses_beta_versions():
    source = GRADLE.read_text()
    assert 'Regex("""(\\d+)\\.(\\d+)\\.(\\d+)(?:-beta\\.\\d+)?""")' in source
    assert 'appVersion.split(".")' not in source
    assert "if (uploadKeystore != null)" in source
    assert 'environmentVariable("VOICESTUDIO_ANDROID_VERSION_CODE")' in source


def test_mobile_ci_configures_a_beta_version():
    steps = load(MOBILE)["jobs"]["android"]["steps"]
    step = next(step for step in steps if step.get("name") == "Beta version configures")
    assert "-beta.1" in step["run"] and ":app:printAppVersion" in step["run"]


def test_store_app_id_matches_on_both_platforms_and_the_upload():
    # The shared mobile contract ships both apps under one store identity.
    ios = load(ROOT / "mobile" / "ios" / "VoiceStudio" / "project.yml")
    bundle_id = ios["targets"]["VoiceStudio"]["settings"]["base"]["PRODUCT_BUNDLE_IDENTIFIER"]
    assert bundle_id == "sh.voicestudio.mobile"
    assert f'applicationId = "{bundle_id}"' in GRADLE.read_text()
    steps = load(WORKFLOW)["jobs"]["play-internal"]["steps"]
    upload = next(step for step in steps if step.get("name") == "Upload to Play internal testing")
    assert upload["with"]["packageName"] == bundle_id
