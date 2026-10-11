"""One process for a whole document: the LaTeX filter sends every \\ce, \\pu and siunitx command it meets in one JSON
request on stdin and reads the answers on stdout (`python3 pdfmd_chem`, see __main__.py).

Request: {"preamble": "<the document's LaTeX preamble>", "items": [{"text": "\\\\ce{H2O}"}, {"math": "x = \\\\SI{5}{\\\\mL}"}]}.
An item "text" is one command written in running text; the answer is {"runs": [[text, place], ...], "math": "<TeX>",
"needs_math": bool}, place "" | "sup" | "sub", and "needs_math" when only an equation shows it as LaTeX does (an
arrow with words over it). An item "math" is the TeX of a formula; the answer is {"math": "<TeX>"} with each command
in it replaced. An item that cannot be converted is {"error": "<why>"}: the filter leaves it to LaTeX.
"""

from __future__ import annotations

import json
import re
import sys

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
        inner, _ = siunitx._group(command.strip(), found.end())
        if inner is None:
            raise siunitx.SiunitxError(f"\\{name} without its argument")
        runs, needs_math = render.convert(inner, "pu" if name == "pu" else "ce")
        return render.text_runs(runs), render.math_tex(runs), needs_math
    runs = siunitx.convert(command, settings)
    return siunitx.runs_text(runs), siunitx.runs_tex(runs), False


def in_math(tex: str, settings: siunitx.Settings) -> str:
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


def answer(request: dict) -> list:
    settings = siunitx.settings_from_preamble(request.get("preamble") or "")
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
