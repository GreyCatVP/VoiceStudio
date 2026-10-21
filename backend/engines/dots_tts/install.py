"""Compatibility repairs shared by managed and user-clone installation."""
from pathlib import Path
import re


#: Upstream pins known to be broken, and their replacements. Also applied by
#: the Ray cluster installer (services/ray_jobs/engines.py).
KNOWN_BROKEN_PINS = (
    ("gradio", "6.17.0", "6.17.3"),
    ("transformers", "4.57.0", "4.57.1"),
)
COMPATIBLE_NAME = ".voicestudio-compatible.txt"


def compatible_constraints(source: Path) -> Path:
    """Keep upstream/user constraints intact; replace only known broken pins.

    Keep the generated copy beside the source so relative includes retain their
    meaning. No model data or working environment is removed during a retry.
    """
    text = source.read_text(encoding="utf-8")
    patched = text
    for package, old, new in KNOWN_BROKEN_PINS:
        patched = re.sub(
            rf"(?m)^({package}\s*==\s*){re.escape(old)}(?=\s*(?:#.*)?$)",
            lambda match: match[1] + new,
            patched,
        )
    if patched == text:
        return source
    destination = source.with_name(COMPATIBLE_NAME)
    destination.write_text(patched, encoding="utf-8")
    return destination
