"""Language codes for container stream tags.

MP4 and Matroska store a stream's language as a three-letter ISO 639-2 code.
FFmpeg's MP4 muxer silently drops anything else, so a dub track tagged ``th``
showed no language at all. Matroska expects the bibliographic (B) form, and
players read the same codes from MP4.
"""
from __future__ import annotations

# ISO 639-1 (plus the legacy and regional tags the dub pickers and Whisper
# emit) -> ISO 639-2/B.
_TO_639_2B = {
    "af": "afr", "am": "amh", "ar": "ara", "as": "asm", "az": "aze", "ba": "bak",
    "be": "bel", "bg": "bul", "bn": "ben", "bo": "tib", "bs": "bos", "ca": "cat",
    "cs": "cze", "cy": "wel", "da": "dan", "de": "ger", "el": "gre", "en": "eng",
    "es": "spa", "et": "est", "eu": "baq", "fa": "per", "fi": "fin", "fo": "fao",
    "fr": "fre", "gd": "gla", "gl": "glg", "gu": "guj", "ha": "hau", "he": "heb",
    "hi": "hin", "hr": "hrv", "ht": "hat", "hu": "hun", "hy": "arm", "id": "ind",
    "is": "ice", "it": "ita", "ja": "jpn", "jv": "jav", "ka": "geo", "kk": "kaz",
    "km": "khm", "kn": "kan", "ko": "kor", "ku": "kur", "ky": "kir", "la": "lat",
    "lb": "ltz", "ln": "lin", "lo": "lao", "lt": "lit", "lv": "lav", "mg": "mlg",
    "mi": "mao", "mk": "mac", "ml": "mal", "mn": "mon", "mr": "mar", "ms": "may",
    "mt": "mlt", "my": "bur", "nb": "nob", "ne": "nep", "nl": "dut", "nn": "nno",
    "no": "nor", "oc": "oci", "pa": "pan", "pl": "pol", "ps": "pus", "pt": "por",
    "ro": "rum", "ru": "rus", "sa": "san", "sd": "snd", "si": "sin", "sk": "slo",
    "sl": "slv", "sm": "smo", "sn": "sna", "so": "som", "sq": "alb", "sr": "srp",
    "su": "sun", "sv": "swe", "sw": "swa", "ta": "tam", "te": "tel", "tg": "tgk",
    "th": "tha", "tk": "tuk", "tl": "tgl", "tr": "tur", "tt": "tat", "uk": "ukr",
    "ur": "urd", "uz": "uzb", "vi": "vie", "xh": "xho", "yi": "yid", "yo": "yor",
    "zh": "chi", "zu": "zul", "br": "bre", "haw": "haw",
    # Legacy 639-1 and three-letter tags without their own 639-2 code.
    "iw": "heb", "in": "ind", "jw": "jav", "cmn": "chi", "yue": "chi", "fil": "fil",
}
# The ISO 639-2 codes whose terminology (T) form differs from the B form.
_T_TO_B = {
    "bod": "tib", "ces": "cze", "cym": "wel", "deu": "ger", "ell": "gre",
    "eus": "baq", "fas": "per", "fra": "fre", "hye": "arm", "isl": "ice",
    "kat": "geo", "mri": "mao", "mkd": "mac", "msa": "may", "mya": "bur",
    "nld": "dut", "ron": "rum", "slk": "slo", "sqi": "alb", "zho": "chi",
}


def iso639_2b(code: object) -> str:
    """Three-letter ISO 639-2/B code for a language tag (``th``, ``zh-CN``,
    ``fra``); ``und`` when the tag is unknown."""
    base = str(code or "").strip().lower().replace("_", "-").split("-")[0]
    if base in _TO_639_2B:
        return _TO_639_2B[base]
    if base in _T_TO_B:
        return _T_TO_B[base]
    if len(base) == 3 and base.isascii() and base.isalpha():
        return base
    return "und"


def audio_stream_tags(index: int, language: object, title: str) -> list[str]:
    """FFmpeg args tagging output audio stream ``index`` with its language and
    name. MP4 shows a track's name from ``handler_name``; Matroska from ``title``."""
    spec = f"-metadata:s:a:{index}"
    return [
        spec, f"language={iso639_2b(language)}",
        spec, f"title={title}",
        spec, f"handler_name={title}",
    ]
