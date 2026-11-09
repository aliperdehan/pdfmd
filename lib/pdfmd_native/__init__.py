"""The native tier: Markdown to PDF with no Pandoc, through Calibre's Markdown reader (`render_calibre_markdown`,
`calibre_page_options_for`) or the built-in renderers inkmd and md2pdf (`render_native`, `load_inkmd`, `set_pdf_info`,
`captured_logs`, `report_messages`), and `convert_native`, which runs it all. Before a renderer sees it, the text is normalised
(`normalise_gfm`, `NativeSource`, `title_block`, `ignored_front_matter_keys`, `strip_html_comments`, `protect_dollars`,
`convert_math_items`, `escape_markup`, `author_names`); math is set as text without a typesetter (`MathText`, `chunks_markup`,
`chunks_width`, `centred_math`, `inline_math`, `stacked_math`, `mathtext_form`); a `.csv` div becomes a pipe table
(`csv_div_table`, `csv_guess_delimiter`, `csv_extension_delimiter`, `csv_keep`, `csv_alignments`, `csv_separator_alignments`,
`csv_cut_advice`). Also the page (`native_page`, `native_paper`, `native_landscape`, `native_paper_note`, `native_font_size`),
the order of the renderers (`native_order`), and what the tier could not honour (`native_note`, `native_lose`,
`describe_native_changes`).

Moved out of `pdfmd.py` unchanged (v3.33.39, SPLIT.md), with the constants only this code reads (`NATIVE_SOURCE_SUFFIXES`,
`NATIVE_READERS`, `NATIVE_META_KEYS`, the patterns from `HEADING_ATTR_RE` to `PAPER_SIZES`, the tables of the math converter from
`MATH_GREEK` to `MARKDOWN_ESCAPE_RE` but `MATH_LINE_BREAK`, `NO_BREAK_SPACE`, `MATHTEXT_REWRITES`, `CSV_DIV_LINE_RE`,
`DIV_CLOSE_RE`, `DIV_ATTRIBUTE_RE`, `CSV_ALIGNMENTS`, `CSV_SEPARATOR_CELL_RE`, `CALIBRE_MARKDOWN_EXTENSIONS`, and
`NATIVE_PAPER_NOTED`, the papers already noted) and the comments that are theirs alone: the one on math without a typesetter
(which `MathText` points at) and those on `NATIVE_META_KEYS` and `MATHTEXT_REWRITES`. In `MathText.command`, the local `core` (the
radicand of `\\sqrt` as it prints) is `under_root`, as the name `core` is this module's link to pdfmd. `core` is the `pdfmd`
module, bound by `pdfmd.py` when it loads (the first binding wins); the pdfmd names the code uses are read as `core.X` when it
runs: `CALIBRE_CSS`, `CALIBRE_OPTIONS`, `CSV_DEFAULTS`, `CSV_DELIMITER_NAMES`, `CSV_DELIMITER_WORDS`, `CSV_DIV_RE`, `Chunk`,
`DEFAULT_MARGIN`, `DIV_FENCE_RE`, `FENCE_RE`, `INKMD_CLI`, `MATH_LINE_BREAK`, `NATIVE_LOST`, `NATIVE_PAPER_POINTS`, `PAPER_CLI`,
`PAPER_NAME_ALIASES`, `atomic_write_bytes`, `atomic_write_pdf`, `csv_defaults`, `csv_is_off`, `csv_note_mode`, `display_path`,
`inkmd_emoji_font`, `log_cmd`, `math_lines`, `matplotlib_available`, `metadata_file_yaml`, `obsidian_source`, `office_module`,
`pandoc_metadata_order`, `pypdf`, `record_engine`, `resolve_calibre`, `scalar_text`, `split_front_matter`, `vprint` and `yaml`.
`NATIVE_LOST` (what the tier left out, which `pdfmd.py` reads after the build) stays there as state: `native_lose` adds to
`core.NATIVE_LOST`. `PAPER_CLI` stays, rebound with `global` in `main`; `matplotlib_available` and `resolve_calibre` are patched
by tests as `pdfmd.X`; `math_lines`, with `Chunk` and `MATH_LINE_BREAK`, stays because `lib/pdfmd_ansi` reads it; `csv_defaults`
is `pdfmd_tables`'s, read through pdfmd as before; `pypdf` is pdfmd's lazy loader and `yaml` its own optional import. The vendored
inkmd (`pdfmd_inkmd`), md2pdf, matplotlib's `mathtext` and `traceback` are imported inside the functions that use them, as before,
so loading this package loads none of them.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp

core = None


def csv_cut_advice(rows_cut: bool, cols_cut: bool) -> str:
    """How to see more of a table that was cut, for the dimensions that were."""
    parts = []
    if rows_cut:
        parts.append("rows=all or rows=N on the .csv div shows more rows, --csv-rows for every table")
    if cols_cut:
        parts.append("cols=all or cols=N on the .csv div shows more columns, --csv-cols for every table")
    return "; ".join(parts)


NATIVE_SOURCE_SUFFIXES = frozenset({".md", ".markdown", ".mdown", ".mkd"})
NATIVE_READERS = frozenset({"markdown", "md", "gfm", "commonmark", "commonmark_x", "markdown_strict"})


# Front-matter keys the native renderers act on; every other key is reported.
NATIVE_META_KEYS = frozenset({"title", "subtitle", "author", "date", "subject", "keywords",
                              "papersize", "fontsize"})


def native_note(engine: str, message: str, source: Path | None = None) -> None:
    where = f"{core.display_path(source)}: " if source is not None else ""
    line = f"WARN  native ({engine}): {where}{message}"
    if NATIVE_NOTED is not None:
        if line in NATIVE_NOTED:
            return
        NATIVE_NOTED.add(line)
    print(line, file=sys.stderr)


# The notes printed so far while convert_native prepares the text once per renderer (v3.33.46): a `.csv` table cut short is
# said once, not once per renderer in the list. None outside that loop.
NATIVE_NOTED: set[str] | None = None


def native_lose(kind: str, count: int = 1) -> None:
    core.NATIVE_LOST[kind] = core.NATIVE_LOST.get(kind, 0) + count


HEADING_ATTR_RE = re.compile(r"^(#{1,6}\s+.*?)\s*\{(?:[#.][^{}\n]*|[A-Za-z][\w-]*=[^{}\n]*)\}\s*$")
IMAGE_ATTR_RE = re.compile(r"(!\[[^\]\n]*\]\([^)\n]*\))\{[^{}\n]*\}")
PAGE_BREAK_RE = re.compile(r"^\s*\\(?:newpage|pagebreak|clearpage|cleardoublepage)(?:\[\d\])?(?:\{\})?\s*$")
TEX_BEGIN_RE = re.compile(r"^\s*\\begin\{([A-Za-z]+\*?)\}")
TEX_COMMAND_LINE_RE = re.compile(r"^\s*\\[A-Za-z]+\*?(?:\[[^\]\n]*\])*(?:\{[^{}\n]*\})*\s*$")
TEX_MATH_ENVIRONMENTS = frozenset({"equation", "equation*", "align", "align*", "gather", "gather*",
                                   "multline", "multline*", "eqnarray", "eqnarray*", "displaymath"})
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+\1")
CITATION_RE = re.compile(r"\[-?@[^\]\n]+\]")
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?=\S)[^$\n]+?(?<=\S)\$(?!\d)")
INLINE_MATH_CAPTURE_RE = re.compile(r"(?<![\\$])\$(?=\S)([^$\n]+?)(?<=\S)\$(?!\d)")
DISPLAY_IN_TEXT_RE = re.compile(r"\$\$(.+?)\$\$")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
PAGE_BREAK_COMMENT_RE = re.compile(r"^\s*<!--\s*(?:pdfmd\s*:\s*)?(?:page-?break|new-?page)\s*-->\s*$", re.IGNORECASE)
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:\s?(.*)$")
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F1E6-\U0001F1FF]")
PAGE_BREAK_MARKUP = {"inkmd": '<div style="page-break-after: always"></div>', "md2pdf": "\\pagebreak"}
PAPER_SIZES = {"a3", "a4", "a5", "letter", "legal", "tabloid"}


# -- math without a typesetter -------------------------------------------------
#
# inkmd cannot typeset math, and md2pdf can only when matplotlib is installed
# (or the network is reachable, for Kroki) and only for what matplotlib's
# mathtext understands. Rather than print `$$...$$` as source, the native tier
# sets such formulas as text: Greek letters and operators as Unicode, x^2 and
# x_i as <sup>/<sub>, variables in italics, \frac{a}{b} as a/b, and display
# math ($$...$$, \begin{aligned}...) as its own centred line(s) -- centred by
# padding with no-break spaces, since neither renderer aligns text blocks.
# It is a readable approximation, not typesetting: `pdfmd --install math` gives
# real formulas.
MATH_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "varpi": "ϖ", "rho": "ρ",
    "varrho": "ϱ", "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ",
    "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ",
    "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
MATH_SYMBOLS = {
    "int": "∫", "iint": "∬", "iiint": "∭", "oint": "∮", "sum": "∑", "prod": "∏", "coprod": "∐",
    "infty": "∞", "partial": "∂", "nabla": "∇", "pm": "±", "mp": "∓", "times": "×", "div": "÷",
    "cdot": "·", "cdots": "⋯", "ldots": "…", "dots": "…", "vdots": "⋮", "ddots": "⋱",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠", "approx": "≈",
    "sim": "∼", "simeq": "≃", "equiv": "≡", "propto": "∝", "cong": "≅", "ll": "≪", "gg": "≫",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "gets": "←", "leftrightarrow": "↔",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔", "implies": "⇒", "iff": "⇔",
    "mapsto": "↦", "uparrow": "↑", "downarrow": "↓", "in": "∈", "notin": "∉", "ni": "∋",
    "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇", "cup": "∪", "cap": "∩",
    "setminus": "∖", "emptyset": "∅", "varnothing": "∅", "forall": "∀", "exists": "∃",
    "neg": "¬", "lnot": "¬", "land": "∧", "wedge": "∧", "lor": "∨", "vee": "∨", "oplus": "⊕",
    "otimes": "⊗", "angle": "∠", "circ": "∘", "bullet": "•", "star": "⋆", "ast": "∗",
    "hbar": "ħ", "ell": "ℓ", "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ", "prime": "′", "dagger": "†",
    "perp": "⊥", "parallel": "∥", "mid": "|", "therefore": "∴", "because": "∵", "degree": "°",
    "langle": "⟨", "rangle": "⟩", "lceil": "⌈", "rceil": "⌉", "lfloor": "⌊", "rfloor": "⌋",
    "lbrace": "{", "rbrace": "}", "vert": "|", "Vert": "‖", "lvert": "|", "rvert": "|",
    "lVert": "‖", "rVert": "‖", "colon": ":", "triangle": "△", "square": "□", "checkmark": "✓",
}
MATH_RELATIONS = frozenset("=<>≤≥≠≈∼≃≡∝≅≪≫→←↔⇒⇐⇔↦∈∉∋⊂⊆⊃⊇⊥∥∴∵")
MATH_BINARY = frozenset("±∓×÷·∪∩∖∧∨⊕⊗∘⋆∗")
MATH_FUNCTIONS = frozenset({
    "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "sinh", "cosh",
    "tanh", "coth", "log", "ln", "lg", "exp", "lim", "limsup", "liminf", "max", "min", "sup",
    "inf", "det", "dim", "ker", "gcd", "arg", "deg", "Pr", "mod", "hom", "tr", "rank",
})
MATH_ACCENTS = {"hat": "\u0302", "widehat": "\u0302", "bar": "\u0304", "overline": "\u0304",
                "vec": "\u20d7", "dot": "\u0307", "ddot": "\u0308", "tilde": "\u0303",
                "widetilde": "\u0303", "check": "\u030c", "acute": "\u0301", "grave": "\u0300"}
MATH_BLACKBOARD = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "ℙ", "H": "ℍ"}
MATH_DROP = frozenset({"left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr",
                       "biggl", "biggr", "displaystyle", "textstyle", "scriptstyle",
                       "scriptscriptstyle", "limits", "nolimits", "nonumber", "notag", "mathstrut",
                       "strut", "protect", "relax"})
MATH_DROP_ARGUMENT = frozenset({"tag", "label", "phantom", "hphantom", "vphantom", "hspace", "vspace",
                                "ref", "eqref"})
MATH_TEXT_COMMANDS = frozenset({"text", "textrm", "textit", "mathrm", "mathit", "mbox", "operatorname",
                                "textnormal", "textsf", "mathsf", "texttt", "mathtt"})
MATH_BOLD_COMMANDS = frozenset({"mathbf", "boldsymbol", "bm", "textbf", "pmb"})
MATH_MATRICES = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "Bmatrix": ("{", "}"),
                 "vmatrix": ("|", "|"), "Vmatrix": ("‖", "‖"), "matrix": ("", ""),
                 "smallmatrix": ("", ""), "array": ("", "")}
MATH_ESCAPES = {"{": "{", "}": "}", "%": "%", "$": "$", "&": "&", "#": "#", "_": "_", "|": "‖",
                " ": " ", ",": " ", ";": " ", ":": " ", "!": "", ">": " ", "\\": "\x00"}


SUPERSCRIPTS = {**dict(zip("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")), "\u2212": "⁻", "′": "′",
                "∞": "\u221e", **dict(zip("abcdefghjklmoprstuvwxyz", "ᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻ"))}
SUBSCRIPTS = {**dict(zip("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")), "\u2212": "₋",
              **dict(zip("aehijklmnoprstuvx", "ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"))}
MARKDOWN_ESCAPE_RE = re.compile(r"([\\`*_\[\]#|~])")


def escape_markup(text: str) -> str:
    """Make literal text safe inside Markdown plus inline HTML."""
    return MARKDOWN_ESCAPE_RE.sub(r"\\\1", text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class MathText:
    """LaTeX math -> readable inline text (see the comment above)."""

    def __init__(self, source: str, html: bool = True):
        self.s = source.strip()
        self.i = 0
        self.bold = False
        self.html = html  # <sup>/<sub> tags (inkmd); else Unicode super/subscripts (md2pdf)
        self.environments: list[str] = []

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def skip_space(self) -> None:
        while self.peek() in (" ", "\t", "\n", "\r") and self.peek():
            self.i += 1

    def raw_group(self) -> str:
        """The text of a {...} group (nesting respected), cursor after it."""
        self.skip_space()
        if self.peek() != "{":
            char = self.peek()
            self.i += 1 if char else 0
            return char
        depth, start = 0, self.i + 1
        while self.i < len(self.s):
            if self.s[self.i] == "\\":
                self.i += 2
                continue
            if self.s[self.i] == "{":
                depth += 1
            elif self.s[self.i] == "}":
                depth -= 1
                if depth == 0:
                    self.i += 1
                    return self.s[start:self.i - 1]
            self.i += 1
        return self.s[start:]

    def argument(self) -> list[core.Chunk]:
        self.skip_space()
        char = self.peek()
        if char == "{":
            inner = MathText(self.raw_group())
            inner.bold, inner.environments = self.bold, self.environments
            return inner.sequence()
        if char == "\\":
            self.i += 1
            return self.command()
        if char:
            self.i += 1
            return self.atom(char)
        return []

    def atom(self, char: str) -> list[core.Chunk]:
        if char.isalpha():
            return self.letters(char)
        return [(escape_markup(char), char, 1.0)]

    def letters(self, first: str) -> list[core.Chunk]:
        run = first
        while self.peek().isascii() and self.peek().isalpha():
            run += self.peek()
            self.i += 1
        if not run.isascii():
            return [(run, run, 1.0)]
        return [(run, run, 1.0)] if self.bold else [(f"*{run}*", run, 1.0)]

    def scaled(self, chunks: list[core.Chunk], factor: float) -> list[core.Chunk]:
        """A sub/superscript's chunks: smaller, and with no spaces around operators."""
        result = []
        for markup, plain, scale in chunks:
            if len(plain) >= 3 and plain.startswith(" ") and plain.endswith(" ") and markup.startswith(" "):
                markup, plain = markup.strip(), plain.strip()
            result.append((markup, plain, scale * factor))
        return result

    def script(self, kind: str, argument: list[core.Chunk]) -> core.Chunk:
        """A super/subscript as Unicode where every character has one, else ^(...) / _(...)."""
        plain = "".join(piece for _, piece, _ in argument).replace(" ", "")
        table = SUPERSCRIPTS if kind == "^" else SUBSCRIPTS
        if plain and all(char in table for char in plain):
            mapped = "".join(table[char] for char in plain)
            return (mapped, mapped, 0.7)
        text = f"{kind}({plain})"
        return (escape_markup(text), text, 1.0)

    def operator(self, out: list[core.Chunk], symbol: str, spaced: bool = True) -> None:
        last = next((piece[-1] for _, piece, _ in reversed(out) if piece.strip()), "")
        unary = not last or last in "([{,;:±∓+−×·/" or last in MATH_RELATIONS
        if not spaced or (unary and symbol in "+−±∓"):
            out.append(("\\+" if symbol == "+" else escape_markup(symbol), symbol, 1.0))
        else:
            out.append((f" {escape_markup(symbol)} ", f" {symbol} ", 1.0))

    def sequence(self) -> list[core.Chunk]:
        out: list[core.Chunk] = []
        while self.i < len(self.s):
            char = self.s[self.i]
            if char in " \t\n\r{}":
                self.i += 1
                continue
            self.i += 1
            if char == "\\":
                out.extend(self.command(out))
            elif char in "^_":
                argument = self.argument()
                if self.html:
                    tag = "sup" if char == "^" else "sub"
                    out.append((f"<{tag}>", "", 1.0))
                    out.extend(self.scaled(argument, 0.7))
                    out.append((f"</{tag}>", "", 1.0))
                else:
                    out.append(self.script(char, argument))
            elif char == "&":
                matrix = self.environments and self.environments[-1] in MATH_MATRICES
                out.append((", ", ", ", 1.0) if matrix else (" ", " ", 1.0))
            elif char == "'":
                out.append(("′", "′", 1.0))
            elif char in "=<>":
                self.operator(out, char)
            elif char == "+":
                self.operator(out, "+")
            elif char == "-":
                self.operator(out, "\u2212")
            elif char.isdigit():
                run = char
                while self.peek().isdigit() or (self.peek() == "." and self.s[self.i + 1:self.i + 2].isdigit()):
                    run += self.peek()
                    self.i += 1
                out.append((run, run, 1.0))
            elif char.isalpha():
                out.extend(self.letters(char))
            elif char == ",":
                out.append((", ", ", ", 1.0))
            else:
                out.append((escape_markup(char), char, 1.0))
        return out

    def command(self, out: list[core.Chunk] | None = None) -> list[core.Chunk]:
        """The chunks for the control sequence whose backslash was just consumed."""
        out = out if out is not None else []
        char = self.peek()
        if not char:
            return []
        if not char.isalpha():
            self.i += 1
            if char == "\\":
                if self.environments and self.environments[-1] in MATH_MATRICES:
                    return [("; ", "; ", 1.0)]
                return [(core.MATH_LINE_BREAK, core.MATH_LINE_BREAK, 1.0)]
            text = MATH_ESCAPES.get(char, char)
            return [(escape_markup(text), text, 1.0)] if text else []
        start = self.i
        while self.peek().isalpha():
            self.i += 1
        name = self.s[start:self.i]
        if name in MATH_GREEK or name in MATH_SYMBOLS:
            symbol = MATH_GREEK.get(name) or MATH_SYMBOLS[name]
            if symbol in MATH_RELATIONS:
                result: list[core.Chunk] = []
                self.operator(result, symbol)
                return result
            if symbol in MATH_BINARY:
                result = []
                self.operator(result, symbol)
                return result
            return [(escape_markup(symbol), symbol, 1.0)]
        if name in MATH_FUNCTIONS:
            following = self.s[self.i:].lstrip()[:1]
            tail = "" if following in ("", "(", "^", "_", "[", "|") else " "
            return [(name + tail, name + tail, 1.0)]
        if name in MATH_DROP:
            if name in ("left", "right") and self.peek() == ".":
                self.i += 1
            return []
        if name in MATH_DROP_ARGUMENT:
            self.raw_group()
            return []
        if name in ("frac", "dfrac", "tfrac", "cfrac", "binom"):
            numerator, denominator = self.argument(), self.argument()
            return self.fraction(numerator, denominator, name == "binom")
        if name == "sqrt":
            self.skip_space()
            degree: list[core.Chunk] = []
            if self.peek() == "[":
                end = self.s.find("]", self.i)
                degree = MathText(self.s[self.i + 1:end if end >= 0 else len(self.s)]).sequence()
                self.i = end + 1 if end >= 0 else len(self.s)
            radicand = self.argument()
            plain = "".join(piece for _, piece, _ in radicand)
            under_root = radicand if (len(plain) <= 2 and plain.isalnum()) else (
                [("(", "(", 1.0)] + radicand + [(")", ")", 1.0)])
            prefix = ([("<sup>", "", 1.0)] + self.scaled(degree, 0.7) + [("</sup>", "", 1.0)]) if degree else []
            return prefix + [("√", "√", 1.0)] + under_root
        if name in MATH_TEXT_COMMANDS:
            text = self.raw_group()
            return [(escape_markup(text), text, 1.0)]
        if name in MATH_BOLD_COMMANDS:
            previous, self.bold = self.bold, True
            inner = self.argument()
            self.bold = previous
            markup = "".join(piece for piece, _, _ in inner)
            plain = "".join(piece for _, piece, _ in inner)
            return [(f"**{markup}**", plain, 1.0)] if markup.strip() else []
        if name == "mathbb":
            text = self.raw_group().strip()
            mapped = "".join(MATH_BLACKBOARD.get(letter, letter) for letter in text)
            return [(escape_markup(mapped), mapped, 1.0)]
        if name in MATH_ACCENTS:
            inner = self.argument()
            plain = "".join(piece for _, piece, _ in inner)
            if len(plain) == 1 and plain.isalpha():
                mark = MATH_ACCENTS[name]
                return [(f"*{plain}{mark}*" if not self.bold else plain + mark, plain + mark, 1.0)]
            return inner
        if name == "begin":
            environment = self.raw_group().strip()
            self.environments.append(environment)
            opening = MATH_MATRICES.get(environment, ("", ""))[0]
            if environment == "cases":
                opening = "{"
            if environment == "array":
                self.skip_space()
                if self.peek() == "{":
                    self.raw_group()
            return [(escape_markup(opening), opening, 1.0)] if opening else []
        if name == "end":
            environment = self.raw_group().strip()
            if self.environments:
                self.environments.pop()
            closing = MATH_MATRICES.get(environment, ("", ""))[1]
            return [(escape_markup(closing), closing, 1.0)] if closing else []
        if name in ("quad", "qquad", "enspace", "thinspace", "medspace", "thickspace"):
            spaces = "    " if name == "qquad" else "  " if name == "quad" else " "
            return [(spaces, spaces, 1.0)]
        # Anything else: keep its name, so nothing silently vanishes.
        self.skip_space()
        if self.peek() == "{":
            return self.argument()
        return [(escape_markup(name), name, 1.0)]

    def fraction(self, numerator: list[core.Chunk], denominator: list[core.Chunk], binomial: bool) -> list[core.Chunk]:
        def simple(chunks: list[core.Chunk]) -> bool:
            plain = "".join(piece for _, piece, _ in chunks).strip()
            return len(plain) <= 3 and bool(plain) and not any(c in plain for c in " +−=<>")

        if binomial:
            return [("(", "(", 1.0), *numerator, (" ", " ", 1.0), *denominator, (")", ")", 1.0)]
        def wrapped(chunks: list[core.Chunk]) -> list[core.Chunk]:
            return chunks if simple(chunks) else [("(", "(", 1.0), *chunks, (")", ")", 1.0)]

        return [*wrapped(numerator), ("/", "/", 1.0), *wrapped(denominator)]


def chunks_markup(chunks: list[core.Chunk]) -> str:
    """The chunks as one string; a zero-width space keeps `*a*` and `**b**` from fusing."""
    pieces: list[str] = []
    for markup, _, _ in chunks:
        if pieces and pieces[-1].endswith("*") and markup.startswith("*"):
            pieces.append("\u200b")
        pieces.append(markup)
    return re.sub(r" {2,}", " ", "".join(pieces)).strip()


def chunks_width(chunks: list[core.Chunk], size: float) -> float:
    """Approximate printed width in points: Helvetica metrics where the character
    exists there, 0.62 em otherwise (Greek, operators)."""
    try:
        from pdfmd_inkmd.fonts import text_width
    except ImportError:  # pragma: no cover -- the vendored copy is missing
        text_width = None
    total = 0.0
    for _, plain, scale in chunks:
        for char in plain:
            try:
                char.encode("cp1252")
                width = text_width(char, "Helvetica", size) if text_width else 0.5 * size
            except UnicodeEncodeError:
                width = 0.62 * size
            total += width * scale
    return total


NO_BREAK_SPACE = "\u00a0"


def centred_math(expression: str, page: str, size: float, margin: float = 72.0, landscape: bool = False) -> str:
    """A display formula as Markdown for one centred block (one or more lines)."""
    width = core.NATIVE_PAPER_POINTS.get(page, core.NATIVE_PAPER_POINTS["a4"])[1 if landscape else 0]
    available = width - 2 * margin
    rows = []
    for chunks in core.math_lines(expression):
        padding = max(0.0, (available - chunks_width(chunks, size)) / 2)
        count = int(padding / (0.278 * size))
        # inkmd collapses a run of whitespace, no-break spaces included, to one
        # space and trims it at the start of a paragraph; zero-width spaces
        # (which it does not treat as whitespace) in between keep every one.
        rows.append("\u200b" + (NO_BREAK_SPACE + "\u200b") * count + chunks_markup(chunks))
    return "\\\n".join(rows)


def inline_math(expression: str, html: bool = True) -> str:
    return "; ".join(chunks_markup(chunks) for chunks in core.math_lines(expression, html))


def stacked_math(expression: str, html: bool = True) -> str:
    """A display formula's lines, one under another (hard line breaks), uncentred."""
    return "\\\n".join(chunks_markup(chunks) for chunks in core.math_lines(expression, html))


# What matplotlib's mathtext (md2pdf's offline math) cannot read, and what to
# write instead.
MATHTEXT_REWRITES = (
    (re.compile(r"\\[td]frac(?![A-Za-z])"), r"\\frac"),
    (re.compile(r"\\frac\s*([0-9A-Za-z])\s*([0-9A-Za-z])(?![0-9A-Za-z{])"), r"\\frac{\1}{\2}"),
    (re.compile(r"\\(?:displaystyle|textstyle|scriptstyle|nonumber|notag|limits|nolimits)(?![A-Za-z])\s*"), ""),
    (re.compile(r"\\(?:tag|label)\*?\{[^{}]*\}"), ""),
    (re.compile(r"\\le(?![A-Za-z])"), r"\\leq"),
    (re.compile(r"\\ge(?![A-Za-z])"), r"\\geq"),
    (re.compile(r"\\[lr]Vert(?![A-Za-z])"), r"\\|"),
)


def mathtext_form(expression: str) -> str | None:
    """The expression rewritten for matplotlib's mathtext if it can read it, else None."""
    for pattern, replacement in MATHTEXT_REWRITES:
        expression = pattern.sub(replacement, expression)
    try:
        from matplotlib import mathtext
        mathtext.MathTextParser("path").parse(f"${expression.strip()}$")
    except Exception:  # noqa: BLE001 -- any parse failure means "set it as text"
        return None
    return expression.strip()


class NativeSource:
    """A document, normalised for a native renderer."""

    def __init__(self, text: str, metadata: dict, has_footnotes: bool, math: int, emoji: bool):
        self.text = text
        self.metadata = metadata
        self.has_footnotes = has_footnotes
        self.math = math
        self.emoji = emoji


def author_names(value) -> list[str]:
    if isinstance(value, dict):
        value = value.get("name")
    if isinstance(value, list):
        return [name for item in value for name in author_names(item)]
    text = core.scalar_text(value)
    return [text] if text else []


CSV_DIV_LINE_RE = re.compile(r"""^\s*:{3,}\s*(?:\{((?:[^}"]|"(?:[^"\\]|\\.)*")*\.csv\b(?:[^}"]|"(?:[^"\\]|\\.)*")*)\}|csv)\s*$""")
DIV_CLOSE_RE = re.compile(r"^\s*:{3,}\s*$")
DIV_ATTRIBUTE_RE = re.compile(r"""([\w-]+)=(?:"((?:[^"\\]|\\.)*)"|'([^']*)'|(\S+))""")


CSV_ALIGNMENTS = {"l": "left", "left": "left", "c": "center", "center": "center", "centre": "center",
                  "r": "right", "right": "right", "d": "default", "default": "default"}
CSV_SEPARATOR_CELL_RE = re.compile(r"^\s*:?-+:?\s*$")


def csv_extension_delimiter(name: str | None) -> str:
    """The delimiter a file's name promises: tab for .tsv/.tab, else a comma."""
    return "\t" if name and name.lower().endswith((".tsv", ".tab")) else ","


def csv_guess_delimiter(text: str, name: str | None) -> str:
    """The delimiter of a CSV nobody named (v3.27.5, as pdfmd_lua/csv_table.lua guesses it): the one of , ; tab | that
    gives the first 20 records, parsed as CSV (quoted delimiters and line breaks count as they should), the same number
    of fields, more than one; the most fields win, the name's own delimiter (csv_extension_delimiter) wins a tie.
    Failing that, the one the first line holds most of, else the name's own."""
    expected = csv_extension_delimiter(name)
    sample, cut = (text[:65536], True) if len(text) > 65536 else (text, False)
    candidates = [expected] + [item for item in (",", ";", "\t", "|") if item != expected]
    best, best_fields = None, 1
    for candidate in candidates:
        try:
            records = [row for row in csv.reader(io.StringIO(sample, newline=""), delimiter=candidate) if row]
        except csv.Error:
            continue
        count = min(len(records), 20)
        if cut and count == len(records) and count > 1:
            count -= 1                                  # the sample's last record may be cut short
        if count >= 1:
            fields = len(records[0])
            if fields > best_fields and all(len(record) == fields for record in records[1:count]):
                best, best_fields = candidate, fields
    if best is not None:
        return best
    first = text.splitlines()[0] if text.strip() else ""
    best, best_count = expected, 0
    for candidate in candidates:
        count, quoted = 0, False
        for char in first:
            if char == '"':
                quoted = not quoted
            elif char == candidate and not quoted:
                count += 1
        if count > best_count:
            best, best_count = candidate, count
    return best


def csv_keep(total: int, cap: float, cut: str) -> tuple[list[int], int | None, int]:
    """Which of `total` rows or columns stay under `cap` (as the Lua filter's keep_indices): all, the first `cap`
    (cut "head"), or the first ones and the last floor(sqrt(cap)) (cut "ends", the default: 7 + 3 of 10, 5 + 2 of 7,
    16 + 4 of 20; a cap under 3 keeps the head).
    Returns the kept indices, how many come from the head (None when nothing was cut) and from the tail."""
    if total <= cap:
        return list(range(total)), None, 0
    cap = int(cap)
    tail = math.isqrt(cap) if cut == "ends" and cap >= 3 else 0
    head = cap - tail
    return list(range(head)) + list(range(total - tail, total)), head, tail


def csv_alignments(value: str | None) -> list[str] | None:
    """`align="lcr"` / `align="left,center,right"` as a list of left/center/right/default (None when not given)."""
    if not value:
        return None
    if re.fullmatch(r"[lcrdLCRD]+", value):
        return [CSV_ALIGNMENTS[letter] for letter in value.lower()]
    return [CSV_ALIGNMENTS.get(word, "default") for word in re.split(r"[,\s]+", value.lower()) if word]


def csv_separator_alignments(row: list[str]) -> list[str]:
    """What a `---`, `:--`, `--:`, `:-:` row says about each column."""
    out = []
    for cell in row:
        cell = cell.strip()
        left, right = cell.startswith(":"), cell.endswith(":")
        out.append("center" if left and right else "left" if left else "right" if right else "default")
    return out


def csv_div_table(attributes: str, base_dir: Path, source: Path | None, inline: str | None = None,
                  defaults: dict | None = None) -> list[str]:
    """The Markdown pipe table for a `::: {.csv file="data.csv"}` div, the way
    pdfmd_lua/csv_table.lua builds it for Pandoc: the data from `file=` or written inside the div, the delimiter
    from `delimiter=` (a character or its name), the extension or the first line, the first row the header unless
    `header="false"`, a `---`/`:-:`/`--:` second row or `align="lcr"` for the alignments, capped at 10 rows x 7
    columns unless `rows=`/`cols=` (or `all`) say otherwise, or ``defaults`` (csv_defaults) for every table. (Column
    `widths=` need Pandoc.)"""
    defaults = defaults or core.CSV_DEFAULTS
    options = {name: next(value for value in groups if value is not None)
               for name, *groups in ((m.group(1), m.group(2), m.group(3), m.group(4))
                                     for m in DIV_ATTRIBUTE_RE.finditer(attributes))}
    name = options.get("file")
    if name:
        try:
            text = (base_dir / name).read_text(encoding="utf-8-sig")
        except OSError:
            native_note("csv", f"could not open '{name}'; left empty", source)
            return []
    elif inline is not None:
        text = inline
    else:
        native_note("csv", ".csv div has neither file= nor data inside it; left empty", source)
        return []

    def limit(key: str, default: int) -> float:
        value = options.get(key, "")
        if not value:
            return default
        if value.lower() == "all":
            return float("inf")
        return int(value) if value.isdigit() else default

    delimiter = options.get("delimiter") or (defaults["delimiter"] if defaults["delimiter"] != "auto" else None)
    if delimiter and delimiter.lower() != "auto":
        delimiter = core.CSV_DELIMITER_NAMES.get(delimiter.lower(), delimiter[:1])
    else:
        delimiter = csv_guess_delimiter(text, name)
        if delimiter != csv_extension_delimiter(name):
            word = core.CSV_DELIMITER_WORDS.get(delimiter, delimiter)
            native_note("csv", f"{name or 'inline data'}: read with {word}s as the delimiter (its records all have the same "
                               f"number of fields with them); say delimiter=\"{word}\" on the div, or `csv: {{delimiter: {word}}}` in "
                               "pdfmd-options, to make it explicit", source)
    cut = (options.get("cut") or defaults.get("cut") or "ends").lower()
    max_rows, max_columns = (limit(key, float("inf") if defaults[key] == "all" else defaults[key])
                             for key in ("rows", "cols"))
    has_header = options.get("header") != "false" if options.get("header") is not None else defaults["header"]
    rows = [row for row in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter) if row]
    total_columns = max((len(row) for row in rows), default=0)
    header = rows.pop(0) if has_header and rows else [f"Column {n}" for n in range(1, max(total_columns, 1) + 1)]
    alignments = None
    if (has_header and rows and options.get("separator", "auto").lower() not in ("none", "false")
            and all(CSV_SEPARATOR_CELL_RE.match(cell) for cell in rows[0])):
        alignments = csv_separator_alignments(rows.pop(0))
    alignments = csv_alignments(options.get("align")) or alignments or []
    kept_columns, column_head, column_tail = csv_keep(total_columns, max_columns, cut)
    kept_rows, row_head, row_tail = csv_keep(len(rows), max_rows, cut)
    gap = "\u2026"

    def project(values: list, filler):
        out = []
        for position, index in enumerate(kept_columns, start=1):
            out.append(values[index] if index < len(values) else "")
            if column_tail and position == column_head:
                out.append(filler)
        return out

    if column_head is not None:
        header = project(header, gap)
        alignments = project(alignments, "center") if alignments else alignments
    shown = []
    for position, index in enumerate(kept_rows, start=1):
        shown.append(project(rows[index], gap) if column_head is not None else rows[index])
        if row_tail and position == row_head:
            shown.append([gap] * len(header))
    shown_columns = len(kept_columns)

    def cell(value: str | None) -> str:
        return (value or "").replace("\r", "").replace("\n", " ").replace("|", "\\|")

    marks = {"left": " :--- |", "center": " :---: |", "right": " ---: |"}
    lines = ["| " + " | ".join(cell(header[n] if n < len(header) else "") for n in range(len(header))) + " |",
             "|" + "".join(marks.get(alignments[n] if n < len(alignments) else "", " --- |")
                           for n in range(len(header)))]
    for row in shown:
        lines.append("| " + " | ".join(cell(row[n] if n < len(row) else "") for n in range(len(header))) + " |")
    if row_head is not None or column_head is not None:
        def part(head, tail, shown_count, total, noun):
            plural = "" if total == 1 else "s"
            if head is not None and tail:
                return f"the first {head} and the last {tail} of {total} {noun}{plural}"
            return f"{shown_count} of {total} {noun}{plural}"
        facts = ", ".join(piece for piece in (
            part(row_head, row_tail, len(kept_rows), len(rows), "row") if row_head is not None else "",
            part(column_head, column_tail, shown_columns, total_columns, "column") if column_head is not None else "") if piece)
        advice = csv_cut_advice(row_head is not None, column_head is not None)
        mode = core.csv_note_mode(options.get("note")) if options.get("note") is not None else None
        if options.get("note") is not None and mode is None:
            native_note("csv", f"note={options['note']!r} is not short, off or full; short is used", source)
        mode = mode or defaults.get("note") or "short"
        native_note("csv", f"showing {facts} -- {advice}", source)
        if mode == "full":
            lines += ["", f"*(showing {facts} -- use `rows=all`/`cols=all`, or `rows=N`/`cols=N`, on this `.csv` div to include "
                          "more, or `--csv-rows`/`--csv-cols` for every table)*"]
        elif mode == "short":
            lines += ["", f"*(showing {facts})*"]
    return lines


def strip_html_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    """Remove <!-- ... --> from one line (outside code spans); a comment left
    open at the end of the line carries over to the next one."""
    pieces: list[str] = []
    position = 0
    spans = [(match.start(), match.end()) for match in CODE_SPAN_RE.finditer(line)]
    spans.append((len(line), len(line)))
    for start, end in spans:
        segment = line[position:start]
        if in_comment:
            close = segment.find("-->")
            if close < 0:
                segment = ""
            else:
                segment, in_comment = segment[close + 3:], False
        segment = HTML_COMMENT_RE.sub("", segment)
        open_at = segment.find("<!--")
        if open_at >= 0:
            segment, in_comment = segment[:open_at], True
        pieces.append(segment)
        pieces.append(line[start:end])
        position = end
    return "".join(pieces), in_comment


def convert_math_items(items: list[tuple[str, bool]], engine: str, page: str,
                       size: float, landscape: bool = False) -> tuple[list[tuple[str, bool]], int]:
    """Set formulas md2pdf cannot typeset (and, for inkmd, every formula) as text.

    inkmd: every formula becomes text, display math a centred block. md2pdf with
    matplotlib: formulas mathtext can read are kept (rewritten where a known
    LaTeX spelling needs it), the rest become text. md2pdf without matplotlib:
    untouched (it needs the network for them). Returns (items, formulas set as text).
    """
    typeset = engine == "md2pdf"
    if typeset and not core.matplotlib_available():
        return items, 0
    converted = 0
    out: list[tuple[str, bool]] = []

    def inline(expression: str) -> str:
        nonlocal converted
        if typeset:
            form = mathtext_form(expression)
            if form is not None:
                return f"${form}$"
        converted += 1
        return inline_math(expression, html=not typeset)

    index = 0
    while index < len(items):
        line, code = items[index]
        stripped = line.strip()
        display_block = stripped.startswith("$$") and (
            stripped.count("$$") == 1 or (stripped.endswith("$$") and stripped.count("$$") == 2))
        if code or not display_block:
            if not code:
                parts = []
                position = 0
                for span in CODE_SPAN_RE.finditer(line):
                    parts.append(("text", line[position:span.start()]))
                    parts.append(("code", span.group(0)))
                    position = span.end()
                parts.append(("text", line[position:]))
                line = "".join(
                    INLINE_MATH_CAPTURE_RE.sub(lambda m: inline(m.group(1)),
                                               DISPLAY_IN_TEXT_RE.sub(lambda m: inline(m.group(1)), text))
                    if kind == "text" else text for kind, text in parts)
            out.append((line, code))
            index += 1
            continue
        end = index
        expression = None
        if len(stripped) > 4 and stripped.endswith("$$"):
            expression = stripped[2:-2]
        else:
            collected = [stripped[2:]]
            end = index + 1
            while end < len(items) and end - index < 200 and not items[end][1]:
                current = items[end][0].strip()
                if current.endswith("$$"):
                    collected.append(current[:-2])
                    expression = "\n".join(collected)
                    break
                collected.append(current)
                end += 1
        if expression is None or not expression.strip():
            out.append((line, code))
            index += 1
            continue
        form = mathtext_form(expression) if typeset else None
        if form is not None:
            out.extend([("", False), ("$$", False), (form, False), ("$$", False), ("", False)])
        else:
            converted += 1
            block = stacked_math(expression, html=False) if typeset else centred_math(expression, page, size, landscape=landscape)
            out.extend([("", False), (block, False), ("", False)])
        index = end + 1
    return out, converted


def protect_dollars(items: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    """Write the dollar signs that are not math (prices) as &#36;, so md2pdf, which
    reads "$5 and $6" as a formula (and prints a backslash escape as it is), leaves them alone. Math follows Pandoc's rule:
    `$` opens only before a non-space and closes only after one, not before a digit."""
    protected: list[tuple[str, bool]] = []
    for line, code in items:
        if code or line.strip() == "$$" or "$" not in line:
            protected.append((line, code))
            continue
        pieces, position = [], 0
        for span in CODE_SPAN_RE.finditer(line):
            pieces.append((line[position:span.start()], True))
            pieces.append((span.group(0), False))
            position = span.end()
        pieces.append((line[position:], True))
        rebuilt = []
        for text, is_text in pieces:
            if is_text:
                masked: list[str] = []

                def keep(match: re.Match) -> str:
                    masked.append(match.group(0))
                    return f"\x00{len(masked) - 1}\x00"

                text = INLINE_MATH_CAPTURE_RE.sub(keep, DISPLAY_IN_TEXT_RE.sub(keep, text))
                text = re.sub(r"(?<!\\)\$", "&#36;", text)
                text = re.sub(r"\x00(\d+)\x00", lambda match: masked[int(match.group(1))], text)
            rebuilt.append(text)
        protected.append(("".join(rebuilt), code))
    return protected


def normalise_gfm(text: str, engine: str, metadata_files: list[Path] = (), base_dir: Path | None = None,
                  source_path: Path | None = None) -> tuple[NativeSource, dict[str, int]]:
    """Reduce a Pandoc-flavoured Markdown file to what ``engine`` can render.

    Returns the source plus a count of what was dropped or converted, by kind.
    Fenced code is never touched. The kinds: ``attributes``, ``divs``,
    ``latex`` (raw LaTeX removed), ``math`` (formulas found), ``math_text``
    (formulas set as plain text, see convert_math_items), ``citations`` (left
    as written), ``footnotes`` (turned into endnotes). HTML comments are
    dropped silently (a ``<!-- pagebreak -->`` comment becomes a page break).
    """
    front, body = core.split_front_matter(text.lstrip("﻿"))
    metadata: dict = {}
    for path in core.pandoc_metadata_order(list(metadata_files)):
        metadata.update(core.metadata_file_yaml(path))
    metadata.update(front)

    counts: dict[str, int] = {}

    def count(kind: str, amount: int = 1) -> None:
        counts[kind] = counts.get(kind, 0) + amount

    items: list[tuple[str, bool]] = []  # (line, inside fenced code)
    fence: tuple[str, int] | None = None
    raw_block = False
    skip_environment: str | None = None
    math_environment: str | None = None
    in_comment = False
    in_display = False
    skip_csv_div = False
    csv_off = bool(core.CSV_DIV_RE.search(body)) and core.csv_is_off(source_path, list(metadata_files))   # `csv: off`: a plain div, its text
    body_lines = iter(body.splitlines())
    for line in body_lines:
        match = core.FENCE_RE.match(line)
        if fence is not None:
            closes = match and match.group(1)[0] == fence[0] and len(match.group(1)) >= fence[1] \
                and not match.group(2).strip()
            if closes:
                fence = None
                if not raw_block:
                    items.append((line, True))
                raw_block = False
            elif not raw_block:
                items.append((line, True))
            continue
        if match:
            info = match.group(2).strip()
            fence = (match.group(1)[0], len(match.group(1)))
            raw_block = bool(re.match(r"^\{=(?:latex|tex|typst|context)\}$", info))
            if raw_block:
                count("latex")
            else:
                items.append((line, True))
            continue
        if in_display:
            # Inside $$ ... $$: the formula's own \begin{aligned} etc. are not raw LaTeX.
            items.append((line, False))
            in_display = not line.strip().endswith("$$")
            continue
        opener = line.strip()
        if opener.startswith("$$") and opener.count("$$") == 1:
            in_display = True
            items.append((line, False))
            continue
        if not in_comment and PAGE_BREAK_COMMENT_RE.match(line):
            items.append((PAGE_BREAK_MARKUP[engine], False))
            continue
        before_comments = line
        line, in_comment = strip_html_comments(line, in_comment)
        if line != before_comments and not line.strip():
            continue
        if math_environment is not None:
            if re.match(rf"^\s*\\end\{{{re.escape(math_environment)}\}}", line):
                math_environment = None
                items.append(("$$", False))
            else:
                items.append((line, False))
            continue
        if skip_environment is not None:
            if re.match(rf"^\s*\\end\{{{re.escape(skip_environment)}\}}", line):
                skip_environment = None
            continue
        begin = TEX_BEGIN_RE.match(line)
        if begin and begin.group(1) in TEX_MATH_ENVIRONMENTS:
            # \begin{equation}/align/...: a display formula, handled like $$...$$.
            name = re.escape(begin.group(1))
            single = re.match(rf"^\s*\\begin\{{{name}\}}(.*)\\end\{{{name}\}}\s*$", line)
            if single:
                items.append((f"$${single.group(1).strip()}$$", False))
            else:
                math_environment = begin.group(1)
                items.append(("$$", False))
                rest = re.sub(rf"^\s*\\begin\{{{name}\}}", "", line).strip()
                if rest:
                    items.append((rest, False))
            continue
        if begin and begin.group(1) not in TEX_MATH_ENVIRONMENTS:
            skip_environment = begin.group(1)
            count("latex")
            continue
        if PAGE_BREAK_RE.match(line):
            items.append((PAGE_BREAK_MARKUP[engine], False))
            continue
        if TEX_COMMAND_LINE_RE.match(line):
            count("latex")
            continue
        if skip_csv_div:
            skip_csv_div = not DIV_CLOSE_RE.match(line)
            continue
        csv_div = None if csv_off else CSV_DIV_LINE_RE.match(line)
        if csv_div:
            csv_attributes = csv_div.group(1) or ".csv"          # the bare `::: csv` has none
            inline = None
            if not re.search(r"\bfile=", csv_attributes):
                data = []
                for data_line in body_lines:      # the data written inside the div, up to its closing :::
                    if DIV_CLOSE_RE.match(data_line):
                        break
                    data.append(data_line)
                if data and core.FENCE_RE.match(data[0]):
                    data = data[1:-1] if len(data) > 1 and core.FENCE_RE.match(data[-1]) else data[1:]
                inline = "\n".join(data) if any(part.strip() for part in data) else None
            table = csv_div_table(csv_attributes, base_dir or Path.cwd(), source_path, inline,
                                  core.csv_defaults(source_path, metadata_files) if source_path is not None else None)
            items.extend([("", False), *[(row, False) for row in table], ("", False)])
            skip_csv_div = inline is None and bool(re.search(r"\bfile=", csv_attributes))
            count("csv")
            continue
        if core.DIV_FENCE_RE.match(line):
            count("divs")
            continue
        stripped = HEADING_ATTR_RE.sub(r"\1", line)
        stripped = IMAGE_ATTR_RE.sub(r"\1", stripped)
        if stripped != line:
            count("attributes")
        items.append((stripped, False))

    # Footnotes: md2pdf renders them itself; inkmd gets numbered endnotes.
    has_footnotes = any(FOOTNOTE_DEF_RE.match(line) and not code for line, code in items)
    endnotes: list[str] = []
    if has_footnotes and engine == "inkmd":
        definitions: dict[str, str] = {}
        kept: list[tuple[str, bool]] = []
        index = 0
        while index < len(items):
            line, code = items[index]
            definition = None if code else FOOTNOTE_DEF_RE.match(line)
            if definition is None:
                kept.append((line, code))
                index += 1
                continue
            note = [definition.group(2)]
            index += 1
            while index < len(items) and not items[index][1] and (
                    items[index][0].startswith(("    ", "\t"))
                    or (not items[index][0].strip() and index + 1 < len(items)
                        and items[index + 1][0].startswith(("    ", "\t")))):
                note.append(items[index][0].strip())
                index += 1
            definitions[definition.group(1)] = " ".join(part for part in note if part)
        numbers: dict[str, int] = {}

        def reference(match: re.Match) -> str:
            label = match.group(1)
            if label not in definitions:
                return match.group(0)
            if label not in numbers:
                numbers[label] = len(numbers) + 1
                endnotes.append(definitions[label])
            return f"<sup>{numbers[label]}</sup>"

        items = [(line if code else FOOTNOTE_REF_RE.sub(reference, line), code) for line, code in kept]
        count("footnotes", len(endnotes))

    lines = [line for line, _ in items]
    math = display = 0
    citations = 0
    emoji = False
    for line, code in items:
        if code:
            continue
        plain = CODE_SPAN_RE.sub("", line)
        math += len(INLINE_MATH_RE.findall(plain))
        if plain.strip() == "$$":
            display += 1
        else:
            display += 2 * (plain.count("$$") // 2)
        citations += len(CITATION_RE.findall(plain))
        emoji = emoji or bool(EMOJI_RE.search(plain))
    math += display // 2
    if math:
        count("math", math)
    if citations:
        count("citations", citations)

    formulas_as_text = 0
    if math:
        items, formulas_as_text = convert_math_items(items, engine, native_paper(metadata),
                                                     native_font_size(metadata) or 12.0, native_landscape(metadata))
        lines = [line for line, _ in items]
        if formulas_as_text:
            count("math_text", formulas_as_text)
    if engine == "md2pdf":
        items = protect_dollars(items)
        lines = [line for line, _ in items]
    block = title_block(metadata, lines)
    notes_text = ""
    if endnotes:
        notes_text = "\n\n---\n\n**Notes**\n\n" + "\n".join(f"{n}. {note}" for n, note in enumerate(endnotes, 1)) + "\n"
    front_text = ""
    if engine == "md2pdf" and core.yaml is not None:
        wanted = {key: core.scalar_text(metadata.get(key)) for key in ("title", "subject", "keywords", "date")
                  if core.scalar_text(metadata.get(key))}
        names = author_names(metadata.get("author"))
        if names:
            wanted["author"] = ", ".join(names)
        if wanted:
            front_text = "---\n" + core.yaml.safe_dump(wanted, allow_unicode=True, sort_keys=False) + "---\n\n"
    # md2pdf prepends a hidden "<!-- SOURCE_FILE: <path> -->" marker to the text
    # and, when a paragraph follows it directly, prints it (path included) into
    # the PDF; a heading after it is fine. So a document that does not start with
    # a heading gets an empty paragraph first (a comment of our own would print).
    first = next((line.strip() for line in [*block.splitlines(), *lines] if line.strip()), "#")
    guard = "&nbsp;\n\n" if engine == "md2pdf" and not first.startswith("#") else ""
    result = front_text + guard + block + "\n".join(lines).strip("\n") + notes_text
    return NativeSource(result.rstrip("\n") + "\n", metadata, has_footnotes, math, emoji), counts


def title_block(metadata: dict, body_lines: list[str]) -> str:
    """The title/author/date block Pandoc would typeset, as Markdown."""
    title = core.scalar_text(metadata.get("title"))
    if not title:
        return ""
    first = next((line.strip() for line in body_lines if line.strip()), "")
    if first == f"# {title}":
        return ""
    parts = [f"# {title}"]
    subtitle = core.scalar_text(metadata.get("subtitle"))
    if subtitle:
        parts.append(f"*{subtitle}*")
    byline = " — ".join(part for part in (", ".join(author_names(metadata.get("author"))),
                                              core.scalar_text(metadata.get("date"))) if part)
    if byline:
        parts.append(f"*{byline}*")
    return "\n\n".join(parts) + "\n\n"


def ignored_front_matter_keys(metadata: dict) -> list[str]:
    # pdfmd's own marks on a joined or cut document are not the author's keys
    own = {"pdfmd-assembled", "pdfmd-partial"}
    return sorted(str(key) for key in metadata if str(key) not in NATIVE_META_KEYS and str(key) not in own)


def native_page(metadata: dict) -> tuple[str, bool, str]:
    """(the paper, landscape, the name that is no paper we know or "") the built-in renderers set: --paper, else `papersize:` /
    `pagesize:`, as `a4`, `a4paper`, `us-letter`, `a4,landscape`; `landscape` also from `classoption:` and `geometry:` (as for
    LaTeX and Word). A paper we do not know gives A4 and its name, for the caller's NOTE."""
    asked = core.PAPER_CLI or core.scalar_text(metadata.get("papersize")) or core.scalar_text(metadata.get("pagesize"))
    words = [word.casefold() for word in re.split(r"[,\s]+", asked) if word]
    options = metadata.get("classoption")
    extra = [str(item) for item in options] if isinstance(options, list) else ([str(options)] if options else [])
    geometry = metadata.get("geometry")
    extra += [str(item) for item in geometry] if isinstance(geometry, list) else re.split(r"[,\s]+", core.scalar_text(geometry))
    extra = [word.casefold() for word in extra if word]
    landscape = "landscape" in words or "landscape" in extra or any(word == "landscape=true" for word in extra)

    def known(word: str) -> str:
        word = core.PAPER_NAME_ALIASES.get(word, word)
        word = word[:-5] if word.endswith("paper") and word[:-5] in core.NATIVE_PAPER_POINTS else word
        return word if word in core.NATIVE_PAPER_POINTS else ""

    unknown = ""
    for word in words:
        if word == "landscape" or word == "portrait":
            continue
        if known(word):
            return known(word), landscape, ""
        unknown = unknown or word
    for word in extra:                                   # `classoption: a5paper`, `geometry: a5paper`
        if known(word):
            return known(word), landscape, unknown
    return "a4", landscape, unknown


def native_paper(metadata: dict) -> str:
    return native_page(metadata)[0]


def native_landscape(metadata: dict) -> bool:
    return native_page(metadata)[1]


def native_paper_note(metadata: dict, source: Path | None, engine: str) -> None:
    """A NOTE for a `papersize:` the built-in renderers do not have (they set A4), once per file and name."""
    unknown = native_page(metadata)[2]
    if unknown and (str(source), unknown) not in NATIVE_PAPER_NOTED:
        NATIVE_PAPER_NOTED.add((str(source), unknown))
        where = f"{core.display_path(source)}: " if source is not None else ""
        print(f"NOTE  native ({engine}): {where}paper '{unknown}' is not a size the built-in renderers know "
              f"({', '.join(sorted(core.NATIVE_PAPER_POINTS))}); A4 is used", file=sys.stderr)


NATIVE_PAPER_NOTED: set[tuple[str, str]] = set()


def native_font_size(metadata: dict) -> float | None:
    match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:pt)?$", core.scalar_text(metadata.get("fontsize")))
    return float(match.group(1)) if match else None


def native_order(engines: list[str], source: NativeSource) -> list[str]:
    """Which of the available native renderers to try, best first.

    md2pdf when the document has footnotes, math it can typeset, or a
    title/author to record; inkmd otherwise (and as the fallback if the first
    choice fails)."""
    if len(engines) == 1:
        return list(engines)
    if "calibre" in engines:                              # no Pandoc and Calibre: its reader before the rough ones (v3.29.1)
        return ["calibre", *[engine for engine in engines if engine != "calibre"]]
    wants_md2pdf = (source.has_footnotes or bool(source.math) or bool(core.scalar_text(source.metadata.get("title")))
                    or bool(author_names(source.metadata.get("author"))))
    if source.math and not core.matplotlib_available():
        wants_md2pdf = False  # md2pdf would need the network (Kroki) for each formula
    first = "md2pdf" if wants_md2pdf and "md2pdf" in engines else "inkmd"
    return [first, *[engine for engine in engines if engine != first]]


def load_inkmd():
    """The vendored inkmd, pointed at the emoji font of an installed `inkmd` if any."""
    import pdfmd_inkmd
    font = core.inkmd_emoji_font()
    if font is not None and hasattr(pdfmd_inkmd.emoji, "_BUNDLED_FONT"):
        pdfmd_inkmd.emoji._BUNDLED_FONT = str(font)
        cache_clear = getattr(pdfmd_inkmd.emoji._load_font, "cache_clear", None)
        if cache_clear:
            cache_clear()
    return pdfmd_inkmd


def set_pdf_info(pdf_path: Path, metadata: dict, verbose: bool, creator: str = "") -> None:
    """Record title/author/subject/keywords (and the renderer as /Creator) in the
    PDF Info dictionary, best effort. stamp_pdf_metadata_posthoc() then appends
    "via pdfmd-cli" to the creator."""
    info = {"/Creator": creator,
            "/Title": core.scalar_text(metadata.get("title")),
            "/Author": ", ".join(author_names(metadata.get("author"))),
            "/Subject": core.scalar_text(metadata.get("subject")),
            "/Keywords": core.scalar_text(metadata.get("keywords"))}
    info = {key: value for key, value in info.items() if value}
    if not info or core.pypdf is None:
        return
    try:
        reader = core.pypdf.PdfReader(pdf_path)
        writer = core.pypdf.PdfWriter()
        writer.append(reader)
        writer.add_metadata({**(dict(reader.metadata) if reader.metadata else {}), **info})
        core.atomic_write_pdf(writer, pdf_path)
    except Exception as error:  # noqa: BLE001 -- the PDF itself is already fine
        core.vprint(verbose, f"WARN  native: could not write the PDF title/author ({error})", file=sys.stderr)


@contextmanager
def captured_logs(name: str) -> Iterator[list[str]]:
    """Collect a library's WARNING+ log records instead of letting them print."""
    messages: list[str] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger(name)
    handler = Collector(level=logging.WARNING)
    previous = (logger.level, logger.propagate)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        yield messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous[0])
        logger.propagate = previous[1]


def report_messages(engine: str, messages: list[str], source: Path) -> None:
    """Print each distinct renderer warning once, with a repeat count."""
    seen: dict[str, int] = {}
    for message in messages:
        first_line = (message.splitlines() or [""])[0][:300]
        seen[first_line] = seen.get(first_line, 0) + 1
    for message, times in seen.items():
        native_note(engine, message + (f" (x{times})" if times > 1 else ""), source)


def render_native(engine: str, md_path: Path, source: NativeSource, output: Path, verbose: bool) -> list[str]:
    """Render one normalised document with one native engine, or raise.
    Returns the renderer's own warnings, for the caller to report."""
    if engine == "calibre":
        return render_calibre_markdown(md_path, source, output, verbose)
    if engine == "inkmd":
        ink = load_inkmd()
        paper, landscape, _ = native_page(source.metadata)
        native_paper_note(source.metadata, md_path, engine)
        options: dict = {"page_size": paper if paper in PAPER_SIZES else core.NATIVE_PAPER_POINTS[paper],
                         "base_dir": md_path.resolve().parent}
        if landscape:
            options.update(orientation="landscape")          # inkmd's keyword, not a pdfmd-options key
        size = native_font_size(source.metadata)
        if size:
            options["font_size"] = size
        options.update(core.INKMD_CLI)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            data = ink.compile(source.text, **options)
        core.atomic_write_bytes(output, data)
        set_pdf_info(output, source.metadata, verbose, creator="inkmd")
        return [str(item.message) for item in caught]
    import md2pdf
    paper, landscape, _ = native_page(source.metadata)
    native_paper_note(source.metadata, md_path, engine)
    try:
        config = md2pdf.Config(input_file=str(md_path), output_file=str(output), page_size=paper.upper(),
                               orientation="landscape" if landscape else "portrait")
    except Exception:  # a paper ReportLab has no name for (executive, folio): md2pdf's own default
        print(f"NOTE  native (md2pdf): {core.display_path(md_path)}: md2pdf has no paper '{paper}'; its own default is used",
              file=sys.stderr)
        config = md2pdf.Config(input_file=str(md_path), output_file=str(output),
                               orientation="landscape" if landscape else "portrait")
    with captured_logs("md2pdf") as messages:
        md2pdf.Pipeline(config).run(source.text)
    set_pdf_info(output, {}, verbose, creator="md2pdf (ReportLab)")
    return messages


CALIBRE_MARKDOWN_EXTENSIONS = "extra, toc, sane_lists"      # Python-Markdown's tables, footnotes, fenced code, attribute lists


def calibre_page_options_for(metadata: dict) -> list[str]:
    """ebook-convert's page from a document's metadata: the paper and margins it asks for (papersize, geometry, margin,
    read as for a Word file), else Letter and DEFAULT_MARGIN; and its language. In points."""
    module = core.office_module()
    if module is None:
        return []
    spec = module.spec_from_metadata(metadata, None, "exact")
    width, height = spec.page_size()
    default = module.length_to_twips(core.DEFAULT_MARGIN) or 1440
    points = lambda twips: f"{twips / 20:g}"
    options = ["--custom-size", f"{points(width)}x{points(height)}", "--unit", "point"]
    for side in ("left", "right", "top", "bottom"):
        options += [f"--pdf-page-margin-{side}", points(spec.margins.get(side, default))]
    if spec.lang:
        options += ["--language", spec.lang]
    return options


def render_calibre_markdown(md_path: Path, source: NativeSource, output: Path, verbose: bool) -> list[str]:
    """Print a normalised Markdown document with Calibre's own Markdown reader (v3.29.1): `ebook-convert` of the text written
    to a scratch folder, with the title and author recorded and the paper of the document. Raises when it fails."""
    binary = core.resolve_calibre()
    if binary is None:
        raise RuntimeError("Calibre's ebook-convert was not found")
    scratch = Path(mkdtemp(prefix="pdfmd-calibre-md-"))
    try:
        page = scratch / "document.md"
        page.write_text(source.text, encoding="utf-8")
        produced = scratch / "document.pdf"
        css = scratch / "pdfmd-calibre.css"
        css.write_text(core.CALIBRE_CSS, encoding="utf-8")
        options = list(core.CALIBRE_OPTIONS)
        del options[options.index("--max-levels"):options.index("--max-levels") + 2]       # an option of the HTML reader only
        cmd = [binary, str(page), str(produced), *options, "--extra-css", str(css),
               "--markdown-extensions", CALIBRE_MARKDOWN_EXTENSIONS, "--input-encoding", "utf-8",
               *calibre_page_options_for(source.metadata)]
        title = core.scalar_text(source.metadata.get("title"))
        authors = author_names(source.metadata.get("author"))
        if title:
            cmd += ["--title", title]
        if authors:
            cmd += ["--authors", " & ".join(authors)]
        environment = dict(os.environ)
        if sys.platform != "win32":
            environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        core.log_cmd(cmd, scratch, verbose)
        done = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=scratch, env=environment)
        if done.returncode != 0 or not produced.is_file():
            said = [line for line in (done.stderr + "\n" + done.stdout).splitlines() if line.strip()]
            raise RuntimeError("ebook-convert failed: " + " | ".join(said[-3:] or ["no PDF written"]))
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, output)
        set_pdf_info(output, source.metadata, verbose, creator="Calibre")
        return []
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def convert_native(md_path: Path, output: Path, engines: list[str], metadata_files: list[Path],
                   from_format: str | None, verbose: bool, debug: bool) -> tuple[bool, str]:
    """Markdown -> PDF with the native renderers; (ok, reason)."""
    if md_path.suffix.lower() not in NATIVE_SOURCE_SUFFIXES or (
            from_format is not None and from_format.casefold().split("+")[0] not in NATIVE_READERS):
        raise SystemExit(f"{md_path}: the native renderers read Markdown only; this input needs Pandoc "
                         "(and a LaTeX/Typst/HTML engine, or soffice) -- see `pdfmd --check-dependencies`.")
    text = core.obsidian_source(md_path.read_text(encoding="utf-8-sig"), md_path, metadata_files)
    attempts: list[str] = []
    prepared: dict[str, tuple[NativeSource, dict[str, int]]] = {}
    global NATIVE_NOTED
    NATIVE_NOTED = set()
    try:
        for engine in engines:
            # Calibre's Markdown reader is told what inkmd is: no math, endnotes, no Pandoc syntax (v3.29.1)
            prepared[engine] = normalise_gfm(text, "inkmd" if engine == "calibre" else engine, metadata_files,
                                             md_path.resolve().parent, md_path)
    finally:
        NATIVE_NOTED = None
    order = native_order(engines, prepared[engines[0]][0])
    for position, engine in enumerate(order):
        source, counts = prepared[engine]
        try:
            messages = render_native(engine, md_path, source, output, verbose)
        except Exception as error:  # noqa: BLE001 -- try the next renderer, report them all
            if debug:
                import traceback
                traceback.print_exc()
            attempts.append(f"{engine}: {error}")
            if position + 1 < len(order):
                native_note(engine, f"failed ({error}); trying {order[position + 1]}", md_path)
            continue
        core.record_engine(engine, [attempt.split(":", 1)[0] for attempt in attempts])
        print(f"NATIVE  {core.display_path(md_path)} via {engine}")
        report_messages(engine, messages, md_path)
        describe_native_changes(engine, md_path, source, counts)
        return True, ""
    return False, "native renderers failed:\n  " + "\n  ".join(attempts)


def describe_native_changes(engine: str, md_path: Path, source: NativeSource, counts: dict[str, int]) -> None:
    """One warning per kind of thing the native renderer could not honour."""
    def say(message: str) -> None:
        native_note(engine, message, md_path)

    if counts.get("latex"):
        say(f"{counts['latex']} raw LaTeX block/line(s) removed")
        native_lose("latex", counts["latex"])
    if counts.get("divs"):
        say(f"{counts['divs']} Pandoc fenced-div marker(s) removed (their content is kept)")
    if counts.get("attributes"):
        say(f"{counts['attributes']} heading/image attribute block(s) removed")
    if counts.get("citations"):
        say(f"{counts['citations']} citation(s) left as written (no citation processing without Pandoc)")
        native_lose("citations", counts["citations"])
    if counts.get("footnotes") and engine in ("inkmd", "calibre"):
        say(f"{counts['footnotes']} footnote(s) turned into numbered notes at the end")
    if counts.get("math_text"):
        if engine == "calibre":
            say(f"{counts['math_text']} math expression(s) set as plain text (Unicode, sub/superscripts, display math "
                "centred); Calibre's Markdown reader cannot typeset math -- Pandoc does (`pdfmd --install pandoc`)")
        elif engine == "inkmd":
            say(f"{counts['math_text']} math expression(s) set as plain text (Unicode, sub/superscripts, "
                "display math centred); inkmd cannot typeset math -- `pdfmd --install math` does")
        else:
            say(f"{counts['math_text']} formula(e) matplotlib cannot read set as plain text")
        native_lose("math", counts["math_text"])
    elif counts.get("math") and engine == "md2pdf" and not core.matplotlib_available():
        say(f"{counts['math']} math expression(s) need matplotlib or network access (Kroki) -- "
            "`pdfmd --install math` installs matplotlib")
        native_lose("math", counts["math"])
    if source.emoji and engine == "inkmd" and core.inkmd_emoji_font() is None:
        say("emoji shown as [name] labels (`pdfmd --install emoji` adds the colour emoji font)")
        native_lose("emoji")
    ignored = ignored_front_matter_keys(source.metadata)
    if ignored:
        shown = ", ".join(ignored[:8]) + (", ..." if len(ignored) > 8 else "")
        say(f"front-matter keys not used: {shown}")
        native_lose("keys", len(ignored))
