"""One process for a whole document: the LaTeX filter sends every \\ce, \\pu and siunitx command it meets in one JSON
request on stdin and reads the answers on stdout (`python3 pdfmd_chem`, see __main__.py).

Request: {"preamble": "<the document's LaTeX preamble, header-includes too>", "items": [{"text": "\\\\ce{H2O}"}, {"math": "x = \\\\SI{5}{\\\\mL}"}]}.
An item "text" is one command written in running text; the answer is {"runs": [[text, place], ...], "math": "<TeX>",
"needs_math": bool}, place "" | "sup" | "sub", and "needs_math" when only an equation shows it as LaTeX does (an
arrow with words over it). An item "math" is the TeX of a formula; the answer is {"math": "<TeX>"} with each command
in it replaced. An item that cannot be converted is {"error": "<why>"}: the filter leaves it to LaTeX.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from pdfmd_mhchem import MhchemError

from . import render, siunitx

CHEMISTRY = ("ce", "cee", "cf", "pu")
COMMAND = re.compile(r"\\(" + "|".join(CHEMISTRY + tuple(siunitx.COMMANDS)) + r")(?![A-Za-z])")


def _span(tex: str, start: int, name: str) -> int:
    """where the command that starts at `start` ends: its optional argument and its brace groups"""
    position = start + 1 + len(name)
    _, position = siunitx._optional(tex, position)
    count = 1 if name in CHEMISTRY else siunitx.COMMANDS[name]
    for _ in range(count):
        group, after = siunitx._group(tex, position)
        if group is None:
            raise siunitx.SiunitxError(f"\\{name} without its argument")
        position = after
    return position


def one(command: str, settings: siunitx.Settings) -> tuple[list, str, bool]:
    """(text runs, math TeX, needs_math) for one command"""
    found = COMMAND.match(command.strip())
    if not found:
        raise siunitx.SiunitxError(f"not a command this module converts: {command[:40]!r}")
    name = found.group(1)
    if name in CHEMISTRY:
        inner, after = siunitx._group(command.strip(), found.end())
        if inner is None:
            raise siunitx.SiunitxError(f"\\{name} without its argument")
        if command.strip()[after:].strip():
            raise siunitx.SiunitxError(f"text after \\{name}{{...}}")
        runs, needs_math = render.convert(inner, "pu" if name == "pu" else "ce")
        return render.text_runs(runs), render.math_tex(runs), needs_math
    runs = siunitx.convert(command, settings)
    return siunitx.runs_text(runs), siunitx.runs_tex(runs), False


def in_math(tex: str, settings: siunitx.Settings) -> str:
    """the formula with each command converted; a reaction scheme (chemfig's \\schemestart, \\chemfig) is left whole:
    only LaTeX draws it, and its arguments are LaTeX's"""
    if render.DRAWN.search(tex):
        raise render.RenderError("a structure LaTeX draws (chemfig)")
    out, position = [], 0
    for found in COMMAND.finditer(tex):
        if found.start() < position:
            continue
        end = _span(tex, found.start(), found.group(1))
        _, math, _ = one(tex[found.start():end], settings)
        out.append(tex[position:found.start()] + "{" + math + "}")
        position = end
    out.append(tex[position:])
    return "".join(out)


ERRORS = (MhchemError, render.RenderError, siunitx.SiunitxError, RecursionError)
USEPACKAGE = re.compile(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")


def own_packages(preamble: str) -> str:
    """the text of the packages the preamble loads that are the user's own (a house style in texmf-home or beside the
    document), not TeX Live's: their \\sisetup and \\DeclareSIUnit apply as in LaTeX. One kpsewhich for them all, the
    preamble's own \\usepackage only (one level), and nothing without kpsewhich."""
    names = []
    for found in USEPACKAGE.finditer(re.sub(r"(?<!\\)%.*", "", preamble)):
        names += [name.strip() + ".sty" for name in found.group(1).split(",") if name.strip()]
    names = [name for name in dict.fromkeys(names) if re.fullmatch(r"[\w.-]+", name)]
    if not names:
        return ""
    try:
        done = subprocess.run(["kpsewhich", "-var-value", "TEXMFDIST", *names], capture_output=True, text=True,
                              timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    if not lines:
        return ""
    dist, paths = Path(lines[0]).resolve(), lines[1:]
    texts = []
    for path in paths:
        resolved = Path(path).resolve()
        if dist in resolved.parents:
            continue
        try:
            texts.append(resolved.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(texts)


def answer(request: dict) -> list:
    preamble = request.get("preamble") or ""
    settings = siunitx.settings_from_preamble(own_packages(preamble) + "\n" + preamble)
    answers = []
    for item in request.get("items") or []:
        try:
            if "math" in item:
                answers.append({"math": in_math(item["math"], settings)})
            else:
                runs, math, needs_math = one(item["text"], settings)
                answers.append({"runs": [list(run) for run in runs], "math": math, "needs_math": needs_math})
        except ERRORS as error:
            answers.append({"error": str(error)[:200]})
    return answers


def main() -> int:
    request = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    sys.stdout.buffer.write(json.dumps(answer(request), ensure_ascii=False).encode("utf-8"))
    return 0
