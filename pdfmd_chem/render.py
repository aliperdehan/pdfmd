"""mhchem's \\ce and \\pu as runs: what pdfmd_mhchem parses (mhchem's own parse, not its TeX, which is full of
phantoms Word and Pandoc's math converter do not take) written as text with sub- and superscripts, and as plain math
TeX. A mass or atomic number before a symbol (¹⁴N) is written in Unicode super- and subscript digits: in Word and
LibreOffice a script with no base is an empty box.

A run is (text, place), place "", "sup", "sub", "word" (prose), "op" (an operator between spaces), "var" (a variable
mhchem sets in italic, `$x$`) or "tex" (TeX only an equation can show: the formula needs math); an arrow is
(symbol, "arrow", above, below) with runs above and below it. `needs_math` says text cannot show it as LaTeX does (an
arrow with words over it): the caller sets that one as an equation.
"""

from __future__ import annotations

import re

from pdfmd_mhchem import MhchemError, parse

from .siunitx import THIN, _merge, _tex_text


class RenderError(Exception):
    """mhchem's result has something this module cannot write (a colour, an \\underbrace, a TeX command it does not
    know): the caller leaves the formula to LaTeX."""


GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "omicron": "ο", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "ϕ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
SYMBOLS = {"circ": "°", "degree": "°", "infty": "∞", "pm": "±", "mp": "∓", "times": "×", "cdot": "·", "bullet": "•",
           "ldots": "…", "dots": "…", "prime": "′", "approx": "≈", "sim": "∼", "leq": "≤", "geq": "≥", "le": "≤",
           "ge": "≥", "rightarrow": "→", "leftarrow": "←", "hbar": "ℏ", "%": "%", "&": "&", "_": "_", "{": "{",
           "}": "}", "ominus": "⊖", "oplus": "⊕", "mathrm": "", "text": "", "textrm": "", "mbox": "", "ce": ""}
SUPERSCRIPT = dict(zip("0123456789+-−=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿⁱ"))
SUBSCRIPT = dict(zip("0123456789+-−=()aeoxhklmnpst", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ"))
ARROWS = {"->": ("⟶", "\\longrightarrow"), "\u2192": ("⟶", "\\longrightarrow"), "\u27f6": ("⟶", "\\longrightarrow"),
          "<-": ("⟵", "\\longleftarrow"), "<->": ("⟷", "\\longleftrightarrow"), "<-->": ("⇄", "\\rightleftarrows"),
          "<=>": ("⇌", "\\rightleftharpoons"), "\u21cc": ("⇌", "\\rightleftharpoons"),
          "<=>>": ("⇌", "\\rightleftharpoons"), "<<=>": ("⇌", "\\rightleftharpoons")}
BONDS = {"-": "−", "1": "−", "=": "=", "2": "=", "#": "≡", "3": "≡", "...": "⋯", "....": "⋯", "->": "→",
         "<-": "←", "<": "<", ">": ">", "~": "∼"}
OPERATORS = {"+": "+", "-": "−", "=": "=", "<": "<", ">": ">", "<<": "≪", ">>": "≫", "\\pm": "±", "\\approx": "≈",
             "$\\approx$": "≈"}
UP_DOWN = {"v": "↓", "(v)": "↓", "^": "↑", "(^)": "↑"}
SIMPLE = {"space": (" ", ""), "tinySkip": ("", ""), "entitySkip": (" ", ""), "pu-space-1": ("\u00a0", ""),
          "pu-space-2": (THIN, ""), "1000 separator": (THIN, ""), "commaDecimal": (",", ""), "hyphen": ("-", ""),
          "addition compound": ("·", "op"), "electron dot": ("•", ""), "KV x": ("×", ""), "prime": ("′", ""),
          "cdot": ("·", "op"), "tight cdot": ("·", ""), "times": ("×", "op"), "circa": ("∼", ""),
          "ellipsis": ("…", ""), "/": ("/", ""), " / ": ("/", "op")}


def tex_text(tex: str) -> str:
    """a small piece of TeX (a Greek letter, `x`, `\\Delta`, `2n-1`) as text; RenderError for anything bigger"""
    def command(found):
        name = found.group(1)
        if name in GREEK:
            return GREEK[name]
        if name in SYMBOLS:
            return SYMBOLS[name].replace("{", "\x01").replace("}", "\x02")
        raise RenderError(f"\\{name}")
    text = re.sub(r"\\([A-Za-z]+|.)\s*", command, tex)
    if re.search(r"[\^_\\]", text):
        raise RenderError(tex)
    text = text.replace("{", "").replace("}", "").replace("~", "\u00a0").replace("$", "")
    return text.replace("\x01", "{").replace("\x02", "}").strip()


# chemfig's and chemmacros' drawing commands: no equation shows them, LaTeX draws the formula
DRAWN = re.compile(r"\\(?:chemfig|chemname|chemmove|schemestart|schemestop|arrow|lewis|Lewis|chemabove|chembelow|"
                   r"setchemfig|definesubmol|redox|OX|ox)(?![A-Za-z])")
SCRIPT = re.compile(r"([\^_])(\{((?:[^{}]|\{[^{}]*\})*)\}|[^{\\])")
NESTED = re.compile(r"\\(ce|pu)\s*\{")


def nested(tex: str) -> str:
    """TeX with every \\ce{...} and \\pu{...} in it as math TeX (mhchem leaves one inside $...$ to TeX)"""
    out, position = [], 0
    for found in NESTED.finditer(tex):
        if found.start() < position:
            continue
        depth, end = 0, None
        for index in range(found.end() - 1, len(tex)):
            if tex[index] == "{" and tex[index - 1] != "\\":
                depth += 1
            elif tex[index] == "}" and tex[index - 1] != "\\":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        if end is None:
            raise RenderError(tex)
        runs, _ = convert(tex[found.end():end], found.group(1))
        out.append(tex[position:found.start()] + "{" + math_tex(runs) + "}")
        position = end + 1
    out.append(tex[position:])
    return "".join(out)


def _flat(runs: list) -> str:
    """runs that sit inside a script, or an amount: one string. A state written as a subscript inside a subscript
    (CO3^2-_{(aq)}) is part of it; anything else that cannot be one line of text raises RenderError."""
    out = ""
    for run in runs:
        if run[1] in ("arrow", "tex", "sup"):
            raise RenderError("a script inside a script")
        out += run[0]
    return out


def _scripted(text: str, table: dict) -> str:
    if not all(c in table for c in text):
        raise RenderError(f"no Unicode script for {text!r}")
    return "".join(table[c] for c in text)


class Writer:
    def __init__(self):
        self.needs_math = False

    def items(self, parsed) -> list:
        runs: list = []
        for item in parsed or []:
            if isinstance(item, str):
                if item in ("{", "}"):
                    continue                    # mhchem's own grouping braces
                runs += self.scripted(item)
            else:
                runs += self.item(item)
        return runs

    def item(self, buf: dict) -> list:
        kind = buf["type_"]
        if kind == "chemfive":
            return self.chemfive(buf)
        if kind in ("rm", "roman numeral"):
            return self.scripted(buf["p1"])
        if kind == "text":
            return [(tex_text(buf["p1"]) if "\\" in buf["p1"] else buf["p1"], "word")]
        if kind in ("state of aggregation", "state of aggregation subscript"):
            inner = _flat(self.items(buf["p1"]))
            return [(inner, "sub" if kind.endswith("subscript") else "")]
        if kind == "bond":
            if buf["kind_"] not in BONDS:
                raise RenderError(f"bond {buf['kind_']}")
            return [(BONDS[buf["kind_"]], "")]
        if kind == "frac":
            return [(tex_text(buf["p1"]) + "/" + tex_text(buf["p2"]), "")]
        if kind in ("frac-ce", "pu-frac"):
            self.needs_math = True              # a fraction: only an equation shows it
            top, bottom = math_tex(self.items(buf["p1"])), math_tex(self.items(buf["p2"]))
            return [("\\frac{" + top + "}{" + bottom + "}", "tex")]
        if kind == "tex-math":
            run = self.tex(buf["p1"])
            return [(run[0], "var") if run[1] == "" else run]       # mhchem sets $x$ as math: italic
        if kind == "arrow":
            symbol, _ = ARROWS[buf["r"]]
            above, below = self.items(buf["rd"]), self.items(buf["rq"])
            if above or below:
                self.needs_math = True
            return [(symbol, "arrow", above, below)]
        if kind == "operator":
            name = buf["kind_"]
            if name in UP_DOWN:
                return [(" " + UP_DOWN[name], "")]
            if name not in OPERATORS:
                raise RenderError(f"operator {name}")
            return [(OPERATORS[name], "op")]
        if kind in ("comma enumeration L", "comma enumeration M", "comma enumeration S"):
            return [(buf["p1"] + " ", "")]
        if kind in SIMPLE:
            text, place = SIMPLE[kind]
            return [(text, place)] if text else []
        raise RenderError(kind)

    def tex(self, tex: str) -> tuple:
        """TeX as text when it is that simple; else as TeX for an equation (place "tex", a \\ce or \\pu in it
        converted too), and the formula needs math"""
        try:
            return (tex_text(tex), "")
        except RenderError:
            if DRAWN.search(tex):
                raise RenderError("a structure LaTeX draws (chemfig)") from None
            self.needs_math = True
            return (nested(tex), "tex")

    def scripted(self, tex: str) -> list:
        """a string mhchem wrote, `10^{3}` or `kg^{-1}` among them: text with its scripts as runs"""
        if not re.search(r"[\^_\\$]", tex):
            return [(tex.replace("{", "").replace("}", ""), "")]
        runs, position = [], 0
        try:
            for found in SCRIPT.finditer(tex):
                if found.start() > position:
                    runs.append((tex_text(tex[position:found.start()]), ""))
                inner = found.group(3) if found.group(3) is not None else found.group(2)
                runs.append((tex_text(inner), "sup" if found.group(1) == "^" else "sub"))
                position = found.end()
            if position < len(tex):
                runs.append((tex_text(tex[position:]), ""))
        except RenderError:
            return [self.tex(tex)]
        return runs

    def chemfive(self, buf: dict) -> list:
        runs: list = []
        amount = _flat(self.items(buf["a"]))
        if amount:
            runs.append((amount + THIN, ""))
        mass, number = _flat(self.items(buf["b"])), _flat(self.items(buf["p"]))
        if mass or number:
            runs.append((_scripted(mass, SUPERSCRIPT) + _scripted(number, SUBSCRIPT), ""))
        runs += self.items(buf["o"])
        sub, sup = _flat(self.items(buf["q"])), _flat(self.items(buf["d"]))
        if buf.get("dType") in ("kv", "oxidation"):
            pairs = ((sup, "sup"), (sub, "sub"))
        else:
            pairs = ((sub, "sub"), (sup, "sup"))
        for text, place in pairs:
            if text:
                runs.append((text.replace("-", "−"), place))
        return runs


def convert(source: str, kind: str = "ce") -> tuple[list, bool]:
    """(runs, needs_math) for the text of a \\ce (kind "ce") or a \\pu (kind "pu"); MhchemError when mhchem itself
    cannot read it, RenderError when the result has what this module cannot write"""
    writer = Writer()
    runs = writer.items(parse(source, kind))
    return _merge_runs(runs), writer.needs_math


def _merge_runs(runs: list) -> list:
    out: list = []
    for run in runs:
        if run[1] == "arrow":
            out.append(run)
        elif out and out[-1][1] != "arrow":
            out = out[:-1] + _merge([out[-1], run])
        else:
            out += _merge([run])
    return out


def text_runs(runs: list) -> list[tuple[str, str]]:
    """runs for text: an arrow as its symbol between spaces (its words, if any, after it in brackets), an operator
    between spaces; places "", "sup", "sub" only"""
    out: list[tuple[str, str]] = []
    for run in runs:
        if run[1] == "arrow":
            words = " / ".join("".join(piece[0] for piece in part if piece[1] != "arrow") for part in run[2:] if part)
            out.append((" " + run[0] + (f" ({words})" if words else "") + " ", ""))
        elif run[1] == "op":
            out.append((" " + run[0] + " ", ""))
        elif run[1] in ("word", "tex", "var"):
            out.append((run[0], ""))
        else:
            out.append((run[0], run[1]))
    text = _merge(out)
    return [(re.sub(r" {2,}", " ", t).strip() if i in (0, len(text) - 1) and False else re.sub(r" {2,}", " ", t), p)
            for i, (t, p) in enumerate(text)]


def math_tex(runs: list) -> str:
    """runs as math TeX texmath reads: symbols upright, arrows as stretchy arrows with their words over and under. The
    scripts after one base are one subscript and one superscript (CO3^2-_{(aq)} has two subscripts in a row, which
    TeX refuses): a second one joins the first after a thin space."""
    out = []
    scripts = {"sub": [], "sup": []}

    def flush():
        if scripts["sub"]:
            out.append("_{" + "\\,".join(scripts["sub"]) + "}")
        if scripts["sup"]:
            out.append("^{" + "\\,".join(scripts["sup"]) + "}")
        scripts["sub"], scripts["sup"] = [], []

    for run in runs:
        text, place = run[0], run[1]
        if place in ("sup", "sub"):
            scripts[place].append(_tex_text(text.replace("−", "-"), True))
            continue
        flush()
        if place == "arrow":
            above, below = math_tex(run[2]) if run[2] else "", math_tex(run[3]) if run[3] else ""
            tex = next(t for s, t in ARROWS.values() if s == text)
            if above or below:
                # \\overset and \\underset: Pandoc's converter (texmath) has no \\xrightarrow, the arrow stays as long
                # as \\longrightarrow
                core = tex
                if below:
                    core = "\\underset{" + below + "}{" + core + "}"
                if above:
                    core = "\\overset{" + above + "}{" + core + "}"
                out.append(core)
            else:
                out.append(tex)
        elif place == "tex":
            out.append(text)
        elif place == "var":
            out.append(_tex_text(text.replace("−", "-"), False))
        elif place == "word":
            out.append("\\text{" + text.replace("{", "\\{").replace("}", "\\}") + "}")
        elif place == "op":
            out.append({"·": "\\cdot ", "×": "\\times ", "/": "/", "±": "\\pm ", "≈": "\\approx ", "−": "-",
                        "≪": "\\ll ", "≫": "\\gg "}.get(text, text))
        else:
            out.append(_tex_text(text.replace("−", "-"), True))
    flush()
    return re.sub(r"(?:\\ |\s)+$", "", "".join(out))


__all__ = ["MhchemError", "RenderError", "convert", "math_tex", "tex_text", "text_runs"]
