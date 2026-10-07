"""Which script a character belongs to, and which fonts are tried for it."""

from __future__ import annotations

import bisect
import unicodedata

from ._scripts import CODES, RANGES

_STARTS = [first for first, _last, _code in RANGES]
COMMON = ("Zyyy", "Zinh")


def script_of(code_point: int) -> str:
    """ISO 15924 code of the script ``code_point`` is written in ("Zzzz" if unassigned)."""
    position = bisect.bisect_right(_STARTS, code_point) - 1
    if position >= 0:
        first, last, code = RANGES[position]
        if first <= code_point <= last:
            return CODES[code]
    return "Zzzz"


SCRIPT_NAMES = {
    "Arab": "Arabic", "Armn": "Armenian", "Beng": "Bengali", "Cyrl": "Cyrillic", "Deva": "Devanagari",
    "Ethi": "Ethiopic", "Geor": "Georgian", "Grek": "Greek", "Gujr": "Gujarati", "Guru": "Gurmukhi",
    "Hang": "Hangul", "Hani": "Han", "Hebr": "Hebrew", "Hira": "Hiragana", "Kana": "Katakana",
    "Khmr": "Khmer", "Knda": "Kannada", "Laoo": "Lao", "Latn": "Latin", "Mlym": "Malayalam",
    "Mong": "Mongolian", "Mymr": "Myanmar", "Orya": "Oriya", "Sinh": "Sinhala", "Syrc": "Syriac",
    "Taml": "Tamil", "Telu": "Telugu", "Thaa": "Thaana", "Thai": "Thai", "Tibt": "Tibetan",
    "Zyyy": "symbols and punctuation", "Zinh": "combining marks", "Cher": "Cherokee", "Copt": "Coptic",
    "Goth": "Gothic", "Runr": "Runic", "Ogam": "Ogham", "Brai": "Braille", "Cans": "Canadian Syllabics",
    "Tfng": "Tifinagh", "Nkoo": "N'Ko", "Bopo": "Bopomofo", "Yiii": "Yi",
}
RTL_SCRIPTS = frozenset({"Arab", "Hebr", "Syrc", "Thaa", "Nkoo", "Adlm", "Rohg", "Mand", "Samr", "Mend"})
# fontspec's own names for the scripts it knows (it errors on a name it does not).
FONTSPEC_SCRIPTS = {
    "Arab": "Arabic", "Armn": "Armenian", "Beng": "Bengali", "Bopo": "Bopomofo", "Cyrl": "Cyrillic",
    "Deva": "Devanagari", "Ethi": "Ethiopic", "Geor": "Georgian", "Grek": "Greek", "Gujr": "Gujarati",
    "Guru": "Gurmukhi", "Hang": "Hangul", "Hani": "CJK", "Hira": "CJK", "Kana": "CJK", "Hebr": "Hebrew",
    "Khmr": "Khmer", "Knda": "Kannada", "Laoo": "Lao", "Latn": "Latin", "Mlym": "Malayalam",
    "Mong": "Mongolian", "Mymr": "Myanmar", "Orya": "Oriya", "Sinh": "Sinhala", "Syrc": "Syriac",
    "Taml": "Tamil", "Telu": "Telugu", "Thaa": "Thaana", "Thai": "Thai", "Tibt": "Tibetan",
}

# -- the fonts tried for a character, best first ----------------------------------
# Families are looked up by name among the installed fonts (and pdfmd's own folder);
# the first that has the glyph wins. Serif or neutral faces first: they sit best in
# running text. The last two lines of every list are the same broad fallbacks.
BROAD = ("DejaVu Serif", "DejaVu Sans", "Noto Serif", "Noto Sans", "Arial Unicode MS", "Apple Symbols",
         "Segoe UI Symbol", "Symbola", "Unifont")
SYMBOLS = ("STIX Two Math", "STIX Two Text", "Noto Sans Symbols 2", "Noto Sans Symbols", "Noto Sans Math",
           "Apple Symbols", "Segoe UI Symbol", "DejaVu Sans", "DejaVu Serif")
CJK = {
    "sc": ("Noto Serif CJK SC", "Noto Serif SC", "Source Han Serif SC", "Songti SC", "STSong", "SimSun",
           "Noto Sans CJK SC", "Noto Sans SC", "PingFang SC", "Heiti SC", "Hiragino Sans GB", "Microsoft YaHei"),
    "tc": ("Noto Serif CJK TC", "Noto Serif TC", "Source Han Serif TC", "Songti TC", "PMingLiU", "MingLiU",
           "Noto Sans CJK TC", "Noto Sans TC", "PingFang TC", "Heiti TC", "Microsoft JhengHei"),
    "ja": ("Noto Serif CJK JP", "Noto Serif JP", "Source Han Serif JP", "Hiragino Mincho ProN", "Yu Mincho",
           "MS Mincho", "Noto Sans CJK JP", "Noto Sans JP", "Hiragino Sans", "Hiragino Kaku Gothic ProN",
           "Yu Gothic", "Meiryo"),
    "ko": ("Noto Serif CJK KR", "Noto Serif KR", "Source Han Serif KR", "AppleMyungjo", "Batang",
           "Noto Sans CJK KR", "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic"),
}
CHAINS = {
    "Latn": ("STIX Two Text", "Gentium Plus", "Charis SIL", "Doulos SIL", "Noto Serif", "DejaVu Serif",
             "Times New Roman"),
    "Cyrl": ("STIX Two Text", "PT Serif", "Noto Serif", "DejaVu Serif", "Times New Roman"),
    "Grek": ("STIX Two Text", "Gentium Plus", "GFS Didot", "Noto Serif", "DejaVu Serif", "Palatino",
             "Times New Roman"),
    "Arab": ("Amiri", "Noto Naskh Arabic", "Noto Sans Arabic", "Scheherazade New", "Geeza Pro",
             "Al Nile", "Arial", "Times New Roman"),
    "Hebr": ("Noto Serif Hebrew", "Noto Sans Hebrew", "SBL Hebrew", "Ezra SIL", "Arial Hebrew", "Times New Roman"),
    "Armn": ("Noto Serif Armenian", "Noto Sans Armenian", "Mshtakan", "Sylfaen"),
    "Geor": ("Noto Serif Georgian", "Noto Sans Georgian", "Sylfaen", "Helvetica Neue"),
    "Deva": ("Noto Serif Devanagari", "Noto Sans Devanagari", "Kohinoor Devanagari", "Devanagari Sangam MN", "Mangal"),
    "Beng": ("Noto Serif Bengali", "Noto Sans Bengali", "Bangla Sangam MN", "Vrinda"),
    "Taml": ("Noto Serif Tamil", "Noto Sans Tamil", "Tamil Sangam MN", "Latha"),
    "Telu": ("Noto Serif Telugu", "Noto Sans Telugu", "Telugu Sangam MN", "Gautami"),
    "Knda": ("Noto Serif Kannada", "Noto Sans Kannada", "Kannada Sangam MN", "Tunga"),
    "Mlym": ("Noto Serif Malayalam", "Noto Sans Malayalam", "Malayalam Sangam MN", "Kartika"),
    "Gujr": ("Noto Serif Gujarati", "Noto Sans Gujarati", "Gujarati Sangam MN", "Shruti"),
    "Guru": ("Noto Serif Gurmukhi", "Noto Sans Gurmukhi", "Gurmukhi Sangam MN", "Raavi"),
    "Sinh": ("Noto Serif Sinhala", "Noto Sans Sinhala", "Sinhala Sangam MN", "Iskoola Pota"),
    "Thai": ("Noto Serif Thai", "Noto Sans Thai", "Thonburi", "Sathu", "Tahoma"),
    "Laoo": ("Noto Serif Lao", "Noto Sans Lao", "Lao Sangam MN", "DokChampa"),
    "Khmr": ("Noto Serif Khmer", "Noto Sans Khmer", "Khmer Sangam MN", "Khmer UI"),
    "Mymr": ("Noto Serif Myanmar", "Noto Sans Myanmar", "Myanmar Sangam MN", "Myanmar Text"),
    "Tibt": ("Noto Serif Tibetan", "Noto Sans Tibetan", "Kailasa", "Microsoft Himalaya"),
    "Ethi": ("Noto Serif Ethiopic", "Noto Sans Ethiopic", "Kefa", "Nyala"),
    "Syrc": ("Noto Sans Syriac", "Estrangelo Edessa"),
    "Thaa": ("Noto Sans Thaana", "MV Boli"),
    "Mong": ("Noto Sans Mongolian", "Mongolian Baiti"),
    "Cher": ("Noto Sans Cherokee", "Plantagenet Cherokee"),
    "Copt": ("Noto Sans Coptic", "Antinoou", "New Athena Unicode"),
    "Goth": ("Noto Sans Gothic", "Segoe UI Historic"),
    "Runr": ("Noto Sans Runic", "Segoe UI Historic"),
    "Cans": ("Noto Sans Canadian Aboriginal", "Euphemia UCAS", "Gadugi"),
    "Tfng": ("Noto Sans Tifinagh", "Ebrima"),
    "Nkoo": ("Noto Sans NKo", "Ebrima"),
    "Brai": ("Noto Sans Symbols 2", "Apple Braille", "Segoe UI Symbol", "DejaVu Sans"),
    "Zyyy": SYMBOLS,
    "Zinh": ("STIX Two Text", "Noto Serif", "DejaVu Serif", "Noto Sans"),
}
# Common-script characters that belong to a CJK run (ideographic punctuation, full-width forms).
CJK_PUNCTUATION = ((0x2E80, 0x2FDF), (0x3000, 0x303F), (0x31C0, 0x31EF), (0x3200, 0x33FF),
                   (0xFE30, 0xFE4F), (0xFF00, 0xFFEF))


def han_language(text: str, document_language: str | None) -> str:
    """sc/tc/ja/ko: the CJK flavour a Han character is set in. Kana means Japanese,
    Hangul Korean; otherwise the document's own language decides, and Simplified
    Chinese is the default."""
    for character in text:
        script = script_of(ord(character))
        if script in ("Hira", "Kana"):
            return "ja"
        if script == "Hang":
            return "ko"
    lang = (document_language or "").casefold().replace("_", "-")
    if lang.startswith("ja"):
        return "ja"
    if lang.startswith("ko"):
        return "ko"
    if lang.startswith("zh") and any(tag in lang for tag in ("tw", "hk", "mo", "hant")):
        return "tc"
    return "sc"


def chain_for(code_point: int, script: str, cjk: str) -> tuple[str, ...]:
    """The families to try for a character, best first, ending in the broad fallbacks."""
    if script in ("Hani", "Hira", "Kana", "Hang", "Bopo", "Yiii") or (
            script in COMMON and any(low <= code_point <= high for low, high in CJK_PUNCTUATION)):
        order = [cjk] + [flavour for flavour in ("sc", "ja", "tc", "ko") if flavour != cjk]
        specific = tuple(family for flavour in order for family in CJK[flavour])
    else:
        specific = CHAINS.get(script, ())
    return (*specific, *BROAD)


def is_neutral(code_point: int) -> bool:
    """Characters that need no font of their own: spaces, controls, format characters."""
    category = unicodedata.category(chr(code_point))
    return category in ("Zs", "Zl", "Zp", "Cc", "Cf", "Cn", "Co", "Cs") or code_point in (0xFE0E, 0xFE0F)
