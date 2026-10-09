"""`--to ascii`: Unicode text as plain ASCII (v3.26.8).

A document built for ASCII ends as a file with no byte above 127: for a terminal, an old mail gateway, a legacy system.
`Asciifier.text()` maps one string. It is meant for printing, not for finding a name (that is `pdfmd_unicode.translit`,
which this module borrows for the scripts it knows), so it keeps case, writes the usual ASCII spelling of punctuation
and symbols, and never loses a character silently.

The order of preference, per character:

1. the tables here: spaces and invisible characters, quotes, dashes, `...`, arrows, `<=`, `+/-`, `deg`, Greek letters by
   name (`Delta`; `mu` in front of a letter is the micro prefix, `um`), Cyrillic, the Latin letters Unicode cannot take
   apart (`ss`, `ae`, `o`, `l`), and sub/superscripts as `_2`, `^2`, `^(2-)`;
2. the character without its accents or compatibility form (`é` -> `e`, `ﬁ` -> `fi`, `Ⅳ` -> `IV`);
3. the romanization packs of `pdfmd_unicode.translit` (Hebrew, Arabic, Armenian, Georgian, Korean, Japanese kana; Chinese
   and the rest when `pypinyin` or `anyascii` is installed: `pdfmd --install translit`);
4. what is left has no ASCII form: `?` (the default), `\\uXXXX` (`escape`), nothing (`drop`) or a refusal (`fail`),
   and the characters are counted so the build can say so.

`serve()` is the filter's way in: pdfmd_lua/ascii.lua sends every piece of text of a document in one go and gets them
back mapped, so the Markdown or plain writer escapes what the ASCII spelling needs (`-` at a line's start, `*`, `>`).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter

MISSING_MODES = ("question", "escape", "drop", "fail")
SEPARATOR = "\x00"

# -- the tables -------------------------------------------------------------------------------------------------------
SPACES = {c: " " for c in "\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"}
INVISIBLE = {c: "" for c in "\u00ad\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\ufeff\u202a\u202b\u202c\u202d\u202e"}
QUOTES = {"‘": "'", "’": "'", "‚": ",", "‛": "'", "′": "'", "‵": "'", "ʼ": "'",
          "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "‶": '"',
          "«": "<<", "»": ">>", "‹": "<", "›": ">", "「": '"', "」": '"'}
DASHES = {"‐": "-", "‑": "-", "‒": "-", "–": "-", "−": "-", "⁃": "-", "﹣": "-",
          "－": "-", "—": "--", "―": "--", "⸺": "---", "⸻": "---"}
SYMBOLS = {
    "…": "...", "‥": "..", "·": ".", "•": "*", "‣": ">", "●": "*", "○": "o",
    "▪": "*", "■": "#", "∙": "*", "⋅": "*", "‧": ".", "․": ".",
    "×": "x", "÷": "/", "±": "+/-", "∓": "-/+", "≠": "!=", "≈": "~=", "≅": "~=",
    "≃": "~=", "∼": "~", "≤": "<=", "≥": ">=", "≪": "<<", "≫": ">>", "∞": "inf",
    "√": "sqrt", "∑": "sum", "∏": "prod", "∫": "int", "∂": "d", "∇": "nabla",
    "∆": "Delta", "∈": "in", "∉": "not in", "⊂": "subset of", "∪": "union", "∩": "intersection",
    "→": "->", "←": "<-", "↔": "<->", "⇒": "=>", "⇐": "<=", "⇔": "<=>", "⇌": "<=>",
    "⇄": "<=>", "↑": "^", "↓": "v", "⟶": "-->", "⟵": "<--", "⟷": "<-->", "↦": "|->",
    "∴": "therefore", "∵": "because", "∀": "for all", "∃": "there exists", "¬": "not",
    "∧": "and", "∨": "or", "≡": "==", "∝": "~", "∘": "o",
    "°": "deg", "℃": "degC", "℉": "degF", "‰": " per mille", "‱": " per ten thousand",
    "©": "(c)", "®": "(R)", "™": "(TM)", "§": "Sec.", "¶": "Para.", "†": "+", "‡": "++",
    "€": "EUR", "£": "GBP", "¥": "JPY", "¢": "c", "₹": "INR", "₽": "RUB", "₸": "KZT",
    "¿": "?", "¡": "!", "⁄": "/", "µ": "u", "Å": "A", "Ω": "Ohm", "¼": "1/4",
    "½": "1/2", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8", "✓": "v", "✔": "v",
    "✗": "x", "✘": "x", "★": "*", "☆": "*", "•": "*", "␣": "_", "↵": "<-'",
}
LATIN = {"ß": "ss", "ẞ": "SS", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o",
         "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "þ": "th", "Þ": "Th",
         "ð": "d", "Ð": "D", "ı": "i", "ĸ": "k", "ŋ": "ng", "Ŋ": "Ng", "ſ": "s",
         "ħ": "h", "Ħ": "H", "ŧ": "t", "Ŧ": "T", "ĳ": "ij", "Ĳ": "IJ"}

GREEK_LOWER = {"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta", "η": "eta",
               "θ": "theta", "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "ο": "omicron",
               "π": "pi", "ρ": "rho", "σ": "sigma", "ς": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi", "χ": "chi",
               "ψ": "psi", "ω": "omega", "ϵ": "epsilon", "ϑ": "theta", "ϕ": "phi", "ϱ": "rho", "ϖ": "pi", "ϰ": "kappa"}
GREEK = {**GREEK_LOWER, **{letter.upper(): name.capitalize() for letter, name in GREEK_LOWER.items() if letter != "ς"}}
GREEK_RUN = re.compile("[Ͱ-Ͽἀ-῿]+")

# Russian, Ukrainian, Belarusian and Kazakh Cyrillic (the letters of pdfmd's own lookup keys), with case kept.
CYRILLIC_LOWER = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "є": "ye", "і": "i", "ї": "yi", "ґ": "g", "ў": "u", "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u",
    "ү": "u", "һ": "h",
}
CYRILLIC = {**CYRILLIC_LOWER, **{letter.upper(): latin.capitalize() for letter, latin in CYRILLIC_LOWER.items()}}

SUBSCRIPT = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
             "₊": "+", "₋": "-", "₌": "=", "₍": "(", "₎": ")", "ₐ": "a", "ₑ": "e", "ₕ": "h", "ᵢ": "i", "ⱼ": "j",
             "ₖ": "k", "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₒ": "o", "ₚ": "p", "ᵣ": "r", "ₛ": "s", "ₜ": "t", "ᵤ": "u",
             "ᵥ": "v", "ₓ": "x"}
SUPERSCRIPT = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
               "⁺": "+", "⁻": "-", "⁼": "=", "⁽": "(", "⁾": ")", "ⁿ": "n", "ⁱ": "i", "ᵃ": "a", "ᵇ": "b", "ᶜ": "c",
               "ᵈ": "d", "ᵉ": "e", "ᶠ": "f", "ᵍ": "g", "ʰ": "h", "ʲ": "j", "ᵏ": "k", "ˡ": "l", "ᵐ": "m", "ᵒ": "o",
               "ᵖ": "p", "ʳ": "r", "ˢ": "s", "ᵗ": "t", "ᵘ": "u", "ᵛ": "v", "ʷ": "w", "ˣ": "x", "ʸ": "y", "ᶻ": "z",
               "ᴬ": "A", "ᴮ": "B", "ᴰ": "D", "ᴱ": "E", "ᴳ": "G", "ᴴ": "H", "ᴵ": "I", "ᴶ": "J", "ᴷ": "K", "ᴸ": "L",
               "ᴹ": "M", "ᴺ": "N", "ᴼ": "O", "ᴾ": "P", "ᴿ": "R", "ᵀ": "T", "ᵁ": "U", "ⱽ": "V", "ᵂ": "W"}

# TeX math: the same letters and symbols as macros (a Greek letter in a formula is \\alpha, not "alpha")
TEX_GREEK = {"α": "\\alpha", "β": "\\beta", "γ": "\\gamma", "δ": "\\delta", "ε": "\\varepsilon", "ϵ": "\\epsilon",
             "ζ": "\\zeta", "η": "\\eta", "θ": "\\theta", "ϑ": "\\vartheta", "ι": "\\iota", "κ": "\\kappa",
             "λ": "\\lambda", "μ": "\\mu", "ν": "\\nu", "ξ": "\\xi", "π": "\\pi", "ϖ": "\\varpi", "ρ": "\\rho",
             "ϱ": "\\varrho", "σ": "\\sigma", "ς": "\\varsigma", "τ": "\\tau", "υ": "\\upsilon", "φ": "\\varphi",
             "ϕ": "\\phi", "χ": "\\chi", "ψ": "\\psi", "ω": "\\omega", "Γ": "\\Gamma", "Δ": "\\Delta",
             "Θ": "\\Theta", "Λ": "\\Lambda", "Ξ": "\\Xi", "Π": "\\Pi", "Σ": "\\Sigma", "Υ": "\\Upsilon",
             "Φ": "\\Phi", "Ψ": "\\Psi", "Ω": "\\Omega", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H",
             "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X", "ο": "o"}
TEX_SYMBOLS = {"≤": "\\leq", "≥": "\\geq", "≠": "\\neq", "≈": "\\approx", "±": "\\pm", "∓": "\\mp",
               "×": "\\times", "÷": "\\div", "·": "\\cdot", "⋅": "\\cdot", "→": "\\to", "←": "\\leftarrow",
               "↔": "\\leftrightarrow", "⇒": "\\Rightarrow", "⇔": "\\Leftrightarrow", "⇌": "\\rightleftharpoons",
               "∞": "\\infty", "∂": "\\partial", "∇": "\\nabla", "∑": "\\sum", "∏": "\\prod", "∫": "\\int",
               "√": "\\surd", "∈": "\\in", "∉": "\\notin", "⊂": "\\subset", "∪": "\\cup", "∩": "\\cap",
               "°": "^\\circ", "∝": "\\propto", "∀": "\\forall", "∃": "\\exists", "…": "\\ldots", "ℏ": "\\hbar",
               "ℓ": "\\ell", "µ": "\\mu", "∼": "\\sim", "≡": "\\equiv", "∠": "\\angle", "⊥": "\\perp",
               "∥": "\\parallel", "−": "-", "–": "-", "′": "'", "″": "''"}
TEX = {**TEX_GREEK, **TEX_SYMBOLS}
SMART = frozenset("‘’“”–—…")      # a Markdown writer with `smart` writes these as ASCII itself; escaping would be noise

PLAIN = {**SPACES, **INVISIBLE, **QUOTES, **DASHES, **SYMBOLS, **LATIN, **CYRILLIC}
NON_ASCII = re.compile("[^\x00-\x7f]+")


def _anyascii():
    try:
        from anyascii import anyascii
    except ImportError:
        return None
    return anyascii


def _translit():
    try:
        from pdfmd_unicode import translit
    except ImportError:
        return None
    return translit


def strip_accents(character: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", character) if not unicodedata.combining(c))


def _escape(character: str) -> str:
    code = ord(character)
    return f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}"


def _run(text: str, marker: str) -> str:
    return marker + text if len(text) == 1 else f"{marker}({text})"


class Asciifier:
    """Maps strings to ASCII; `lost` counts the characters that have no ASCII form (and were written per `missing`)."""

    def __init__(self, missing: str = "question"):
        if missing not in MISSING_MODES:
            raise ValueError(f"ascii missing {missing!r}: choose one of {', '.join(MISSING_MODES)}")
        self.missing = missing
        self.lost: Counter[str] = Counter()
        translit = _translit()
        self.translit = translit
        self.packs = frozenset(pack for pack in (translit.PACKS if translit else ()) if translit.available(pack)
                               and pack != "greek")      # Greek has names here, and a spelling for whole words below
        self.anyascii = _anyascii()

    # -- one character
    def _plain(self, character: str) -> str | None:
        if character in PLAIN:
            return PLAIN[character]
        decomposed = "".join(c for c in unicodedata.normalize("NFKD", character) if not unicodedata.combining(c))
        if decomposed and decomposed.isascii():
            return decomposed
        return None

    def _lost(self, character: str) -> str:
        self.lost[character] += 1
        return {"question": "?", "escape": _escape(character), "drop": "", "fail": "?"}[self.missing]

    # -- a run of non-ASCII characters (`following`: the ASCII character after it, if any)
    def convert(self, run: str, following: str = "") -> str:
        out: list[str] = []
        pending: list[str] = []          # characters no table maps: romanized together, so Korean and kana keep their context

        def flush() -> None:
            if not pending:
                return
            text = "".join(pending)
            pending.clear()
            spelt = self.translit.romanize(text, self.packs) if self.translit and self.packs else text
            if spelt.isascii():
                out.append(spelt)
                return
            for character in spelt:
                if character.isascii():
                    out.append(character)
                    continue
                known = self.anyascii(character) if self.anyascii else ""
                out.append(known if known and known.isascii() else self._lost(character))

        index = 0
        while index < len(run):
            character = run[index]
            if character in SUBSCRIPT or character in SUPERSCRIPT:
                flush()
                table, marker = (SUBSCRIPT, "_") if character in SUBSCRIPT else (SUPERSCRIPT, "^")
                end = index
                while end < len(run) and run[end] in table:
                    end += 1
                out.append(_run("".join(table[c] for c in run[index:end]), marker))
                index = end
                continue
            if GREEK_RUN.fullmatch(character):
                flush()
                end = GREEK_RUN.match(run, index).end()
                word = run[index:end]
                if len(word) >= 3 and self.translit:           # a Greek word, not a symbol: spelt, not named letter by letter
                    spelt = self.translit.romanize(word, frozenset({"greek"}))
                    out.append(spelt.capitalize() if word[0].isupper() else spelt)
                else:
                    micro = (word[-1] == "μ" and end == len(run) and following.isalpha() and following.isascii())
                    names = [GREEK.get(strip_accents(c)) or self._lost(c) for c in word]
                    if micro:
                        names[-1] = "u"
                    out.append("".join(names))
                index = end
                continue
            mapped = self._plain(character)
            if mapped is None:
                pending.append(character)
            else:
                flush()
                out.append(mapped)
            index += 1
        flush()
        return "".join(out)

    def text(self, text: str, keep: frozenset[str] = frozenset()) -> str:
        """`text` in ASCII; the characters of `keep` are left as they are."""
        if text.isascii():
            return text
        out: list[str] = []
        position = 0
        for match in NON_ASCII.finditer(text):
            out.append(text[position:match.start()])
            run, following = match.group(), text[match.end():match.end() + 1]
            if keep and any(character in keep for character in run):
                pieces = re.split("([" + re.escape("".join(keep)) + "])", run)
                out.extend(piece if piece in keep else self.convert(piece, following if index == len(pieces) - 1 else "")
                           for index, piece in enumerate(pieces) if piece)
            else:
                out.append(self.convert(run, following))
            position = match.end()
        out.append(text[position:])
        return "".join(out)

    def math(self, text: str) -> str:
        """TeX `text` in ASCII: Greek letters and symbols as macros (`\\alpha`, `\\geq`), the rest as in `text`."""
        if text.isascii():
            return text
        out: list[str] = []
        rest: list[str] = []
        for index, character in enumerate(text):
            if character.isascii():
                if rest:
                    out.append(self.text("".join(rest)))
                    rest = []
                out.append(character)
            elif character in TEX:
                if rest:
                    out.append(self.text("".join(rest)))
                    rest = []
                macro = TEX[character]
                following = text[index + 1:index + 2]
                out.append(macro + " " if macro.startswith("\\") and following.isalpha() and following.isascii() else macro)
            else:
                rest.append(character)
        if rest:
            out.append(self.text("".join(rest)))
        return "".join(out)

    def report(self) -> dict:
        return {"lost": dict(self.lost)}


def describe(lost: dict[str, int], limit: int = 5) -> str:
    """`日 U+65E5 (x3), 😀 U+1F600` for a warning."""
    parts = []
    for character, count in sorted(lost.items(), key=lambda item: (-item[1], item[0]))[:limit]:
        parts.append(f"{character} U+{ord(character):04X}" + (f" (x{count})" if count > 1 else ""))
    more = len(lost) - limit
    return ", ".join(parts) + (f" and {more} more" if more > 0 else "")


def merge(*reports: dict[str, int]) -> dict[str, int]:
    total: Counter[str] = Counter()
    for report in reports:
        total.update(report)
    return dict(total)


def serve(missing: str, report_path: str, smart: str = "all") -> int:
    """Standard input: pieces of text separated by NUL (a piece that starts with SOH is TeX math); standard output: the
    same pieces in ASCII. `smart` = "keep" leaves the quotes, dashes and ellipsis for the writer's own smart typography.
    The characters that have no form are written, counted, to `report_path`."""
    asciifier = Asciifier(missing)
    keep = SMART if smart == "keep" else frozenset()
    data = sys.stdin.buffer.read().decode("utf-8", errors="replace")

    def one(piece: str) -> str:
        if piece.startswith("\x01"):
            return asciifier.math(piece[1:])
        return asciifier.text(piece, keep)

    sys.stdout.buffer.write(SEPARATOR.join(one(piece) for piece in data.split(SEPARATOR)).encode("utf-8" if keep else "ascii"))
    sys.stdout.buffer.flush()
    try:
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(asciifier.report(), handle, ensure_ascii=True)
    except OSError:
        pass
    return 0
