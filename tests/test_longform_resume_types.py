"""The Stories/Audiobook recovery card filters jobs by the backend's resumable
job types; a drifted name ("longform" vs "story") silently hid the card."""
import re
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def test_recovery_card_filters_on_the_backend_job_types():
    from services.longform_resume import RESUMABLE_TYPES

    page = (ROOT / "electron/src/renderer/src/features/longform/longform-page.tsx").read_text(encoding="utf-8")
    match = re.search(r"job\.type === \(mode === 'stories' \? '(\w+)' : '(\w+)'\)", page)
    assert match, "recovery filter not found"
    assert set(match.groups()) == set(RESUMABLE_TYPES)
