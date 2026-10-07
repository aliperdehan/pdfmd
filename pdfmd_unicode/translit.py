"""Romanization packs: how names in other scripts are spelt in Latin letters for lookup.

pdfmd finds a document by a name typed in Latin letters (`glyukoza` finds "Глюкоза.md") by
comparing keys: both sides are reduced to plain letters, and a name in a script pdfmd can
romanize is spelt in Latin first. Cyrillic is built into pdfmd.py itself and always on; the packs
here are the others, off unless asked for (`--translit greek,hangul`, or PDFMD_TRANSLIT), one
per script so nobody pays for tables they will not use:

    greek armenian georgian hebrew arabic hangul kana    own tables, no dependency
    han                                                  pinyin without tones: the optional
                                                         `pypinyin` (MIT), else `anyascii` (ISC)
    other                                                every other script, through `anyascii`
                                                         (ISC; Eranti Eero's table of ASCII
                                                         transliterations) when it is installed

The romanizations are for *finding* a name, not for printing it: plain letters, no tones or
accents, vowels left out where the script leaves them out (Hebrew, Arabic). Typing the usual
spelling usually matches; where it cannot (homophones: 命運 and 銘運 are both "mingyun"), pdfmd
lists the candidates and does not guess.
"""

from __future__ import annotations

import importlib.util
import re
import unicodedata

from .scripts import script_of

GREEK = {
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "e", "θ": "th", "ι": "i", "κ": "k",
    "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t",
    "υ": "y", "φ": "ph", "χ": "ch", "ψ": "ps", "ω": "o", "ϊ": "i", "ϋ": "y", "ϐ": "b", "ϑ": "th",
    "ϕ": "ph", "ϖ": "p", "ϰ": "k", "ϱ": "r", "ϲ": "s", "ϳ": "j", "ϝ": "w", "ϟ": "q", "ϡ": "s",
}
ARMENIAN = {
    "ա": "a", "բ": "b", "գ": "g", "դ": "d", "ե": "e", "զ": "z", "է": "e", "ը": "y", "թ": "t", "ժ": "zh",
    "ի": "i", "լ": "l", "խ": "kh", "ծ": "ts", "կ": "k", "հ": "h", "ձ": "dz", "ղ": "gh", "ճ": "ch",
    "մ": "m", "յ": "y", "ն": "n", "շ": "sh", "ո": "o", "չ": "ch", "պ": "p", "ջ": "j", "ռ": "r",
    "ս": "s", "վ": "v", "տ": "t", "ր": "r", "ց": "ts", "ւ": "v", "փ": "p", "ք": "k", "օ": "o",
    "ֆ": "f", "և": "ev",
}
GEORGIAN = {
    "ა": "a", "ბ": "b", "გ": "g", "დ": "d", "ე": "e", "ვ": "v", "ზ": "z", "თ": "t", "ი": "i", "კ": "k",
    "ლ": "l", "მ": "m", "ნ": "n", "ო": "o", "პ": "p", "ჟ": "zh", "რ": "r", "ს": "s", "ტ": "t", "უ": "u",
    "ფ": "p", "ქ": "k", "ღ": "gh", "ყ": "q", "შ": "sh", "ჩ": "ch", "ც": "ts", "ძ": "dz", "წ": "ts",
    "ჭ": "ch", "ხ": "kh", "ჯ": "j", "ჰ": "h",
}
# Consonant skeletons: the vowels these scripts leave out are left out here too.
HEBREW = {
    "א": "", "ב": "b", "ג": "g", "ד": "d", "ה": "h", "ו": "v", "ז": "z", "ח": "kh", "ט": "t", "י": "y",
    "כ": "k", "ך": "k", "ל": "l", "מ": "m", "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "", "פ": "p",
    "ף": "p", "צ": "ts", "ץ": "ts", "ק": "q", "ר": "r", "ש": "sh", "ת": "t",
}
ARABIC = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ء": "", "ؤ": "", "ئ": "", "ب": "b", "ت": "t", "ث": "th",
    "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "", "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l",
    "م": "m", "ن": "n", "ه": "h", "ة": "h", "و": "w", "ي": "y", "ى": "a", "ـ": "",
    # Persian and Urdu
    "پ": "p", "چ": "ch", "ژ": "zh", "گ": "g", "ک": "k", "ی": "y", "ٹ": "t", "ڈ": "d", "ڑ": "r",
    "ں": "n", "ے": "y", "ہ": "h", "ھ": "h", "ۂ": "h", "ۃ": "h",
}
HIRAGANA = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o", "か": "ka", "き": "ki", "く": "ku", "け": "ke",
    "こ": "ko", "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so", "た": "ta", "ち": "chi",
    "つ": "tsu", "て": "te", "と": "to", "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho", "ま": "ma", "み": "mi", "む": "mu",
    "め": "me", "も": "mo", "や": "ya", "ゆ": "yu", "よ": "yo", "ら": "ra", "り": "ri", "る": "ru",
    "れ": "re", "ろ": "ro", "わ": "wa", "ゐ": "i", "ゑ": "e", "を": "o", "ん": "n", "が": "ga", "ぎ": "gi",
    "ぐ": "gu", "げ": "ge", "ご": "go", "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do", "ば": "ba", "び": "bi", "ぶ": "bu",
    "べ": "be", "ぼ": "bo", "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po", "ゔ": "vu",
}
SMALL_KANA = {"ゃ": "ya", "ゅ": "yu", "ょ": "yo"}
SMALL_VOWELS = {"ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o"}
KANA_SOKUON = "っ"
KANA_LONG = "ー"

# Revised Romanization of Korean, letter by letter (with the liaison of a final before a vowel).
HANGUL_INITIAL = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
HANGUL_VOWEL = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we",
                "wi", "yu", "eu", "ui", "i"]
HANGUL_FINAL = ["", "k", "kk", "ks", "n", "nj", "nh", "t", "l", "lk", "lm", "lb", "ls", "lt", "lp", "lh", "m", "p",
                "ps", "t", "t", "ng", "t", "t", "k", "t", "p", "h"]
# A single final consonant that moves to the next syllable when that begins with a vowel.
HANGUL_LIAISON = {1: "g", 4: "n", 7: "d", 8: "r", 16: "m", 17: "b", 19: "s", 20: "ss", 22: "j", 23: "ch",
                  24: "k", 25: "t", 26: "p", 27: "h"}

TABLES = {"greek": GREEK, "armenian": ARMENIAN, "georgian": GEORGIAN, "hebrew": HEBREW, "arabic": ARABIC}
# The scripts a pack reads (ISO 15924).
PACK_SCRIPTS = {
    "greek": {"Grek"}, "armenian": {"Armn"}, "georgian": {"Geor"}, "hebrew": {"Hebr"}, "arabic": {"Arab"},
    "hangul": {"Hang"}, "kana": {"Hira", "Kana"}, "han": {"Hani"},
}
PACKS = tuple(PACK_SCRIPTS) + ("other",)
HANDLED = {code for codes in PACK_SCRIPTS.values() for code in codes} | {"Cyrl", "Latn", "Zyyy", "Zinh", "Zzzz"}
SCRIPT_PACK = {code: pack for pack, codes in PACK_SCRIPTS.items() for code in codes}


def _han_library():
    if importlib.util.find_spec("pypinyin") is not None:
        from pypinyin import lazy_pinyin
        return lambda text: " ".join(lazy_pinyin(text))
    if importlib.util.find_spec("anyascii") is not None:
        from anyascii import anyascii
        return anyascii
    return None


def _anyascii():
    if importlib.util.find_spec("anyascii") is not None:
        from anyascii import anyascii
        return anyascii
    return None


def available(pack: str) -> bool:
    """Whether a pack can work here (han and other need a library)."""
    if pack == "han":
        return _han_library() is not None
    if pack == "other":
        return _anyascii() is not None
    return pack in PACK_SCRIPTS


def needs(pack: str) -> str:
    return {"han": "pip install pypinyin (or anyascii)", "other": "pip install anyascii"}.get(pack, "")


def _hangul(run: str) -> str:
    """Revised Romanization, letter by letter, with the one sound change people always type:
    a lone final consonant before a vowel-initial syllable is said with that syllable."""
    values = [ord(character) - 0xAC00 for character in run]
    out: list[str] = []
    carry = ""
    for position, value in enumerate(values):
        if not 0 <= value < 11172:
            out.append(run[position])
            carry = ""
            continue
        initial, vowel, final = value // 588, value % 588 // 28, value % 28
        first, carry = (carry or HANGUL_INITIAL[initial]), ""
        following = values[position + 1] if position + 1 < len(values) else -1
        if final in HANGUL_LIAISON and 0 <= following < 11172 and following // 588 == 11:
            carry, last = HANGUL_LIAISON[final], ""
        else:
            last = HANGUL_FINAL[final]
        out.append(first + HANGUL_VOWEL[vowel] + last)
    return "".join(out)


def _kana(run: str) -> str:
    """Hepburn: yoon (きゃ = kya), small vowels (ふぁ = fa), doubled consonants (っ), long marks dropped."""
    out: list[str] = []
    double = False
    for character in run:
        code = ord(character)
        if 0x30A1 <= code <= 0x30F6:        # katakana read as the hiragana it matches
            character = chr(code - 0x60)
        if character == KANA_SOKUON:
            double = True
        elif character == KANA_LONG:
            continue
        elif character in SMALL_KANA and out:
            previous = out.pop()
            out.append(previous[:-1] + (SMALL_KANA[character][1:] if previous.endswith(("shi", "chi", "ji"))
                                        else SMALL_KANA[character]))
        elif character in SMALL_VOWELS and out:
            out.append(out.pop()[:-1] + SMALL_VOWELS[character])
        elif character in HIRAGANA:
            syllable = HIRAGANA[character]
            if double and syllable[0] not in "aiueon":
                syllable = ("t" if syllable.startswith("ch") else syllable[0]) + syllable
            double = False
            out.append(syllable)
        else:
            out.append(character)
    return "".join(out)


def romanize(text: str, packs: frozenset[str]) -> str:
    """``text`` with the characters of the enabled packs' scripts spelt in Latin letters."""
    if not packs or text.isascii():
        return text
    out: list[str] = []
    runs: list[tuple[str, str]] = []  # (pack, run) of consecutive characters of one pack
    for character in text:
        pack = SCRIPT_PACK.get(script_of(ord(character))) if not character.isascii() else None
        if pack is None and not character.isascii() and "other" in packs:
            pack = "other" if script_of(ord(character)) not in HANDLED else None
        if pack is not None and (pack in packs or pack == "other") and runs and runs[-1][0] == pack:
            runs[-1] = (pack, runs[-1][1] + character)
        elif pack is not None and (pack in packs or pack == "other"):
            runs.append((pack, character))
        elif runs and runs[-1][0] == "":
            runs[-1] = ("", runs[-1][1] + character)
        else:
            runs.append(("", character))
    han = _han_library() if "han" in packs else None
    anyascii = _anyascii() if "other" in packs else None
    for pack, run in runs:
        if pack == "":
            out.append(run)
        elif pack in TABLES:
            table = TABLES[pack]
            decomposed = unicodedata.normalize("NFD", run.casefold())
            if pack == "greek":   # gamma before a velar is "n" (Ἀνάγκη = ananke); upsilon after a vowel is "u"
                decomposed = re.sub("γ(?=[γκξχ])", "ν", re.sub("(?<=[αεηοω])υ", "\u0001", decomposed))
            out.append("".join("u" if letter == "\u0001" else table.get(letter, "" if unicodedata.combining(letter)
                                                                      else letter) for letter in decomposed))
        elif pack == "hangul":
            out.append(_hangul(unicodedata.normalize("NFC", run)))
        elif pack == "kana":
            out.append(_kana(run))
        elif pack == "han":
            out.append(han(run) if han else run)
        elif pack == "other":
            out.append(anyascii(run) if anyascii else run)
    return "".join(out)
