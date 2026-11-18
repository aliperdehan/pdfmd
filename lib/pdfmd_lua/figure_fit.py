"""Select the figure fitter and decode the diagnostics from the typesetting pass."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from pdfmd_base import core
from pdfmd_lua import path


MARKER = re.compile(
    r"(?m)^(?:\[WARNING\] )?(?:Missing character: There is no|warning: unknown font family:) "
    r"pdfmd-fit-([sco])-(\d+)-(\d+)-([0-9a-f]*)[ \t]*\r?$"
)
TYPST_TRACE = re.compile(r"(?m)(warning: unknown font family: pdfmd-fit-[^\r\n]+)\r?\n"
                         r"(?:[ \t]*(?:[┌│]|\d+ [│]).*\r?\n)*")
REPORT_ENV = "PDFMD_FIGURE_REPORT"


def arguments(writer: str, source: Path, metadata: list[Path]) -> list[str]:
    if writer not in (*core.LATEX_ENGINES, "latex", "typst") or writer == "context":
        return []
    script = path("figure_fit")
    if script is None:
        return []
    flag = core.option_flag(core.first_pdfmd_option(source, metadata, "figure-fit"))
    # Tectonic retains TeX's successful-run diagnostics only when asked for engine chatter.
    chatter = ["--pdf-engine-opt=--print"] if writer == "tectonic" else []
    check = ["-M", "pdfmd-figure-check=true"] if os.environ.get(REPORT_ENV) else []
    return [*chatter, *check, "-M", f"pdfmd-figure-fit={'off' if flag is False else 'on'}", "--lua-filter", str(script)]


def without_diagnostics(output: str) -> str:
    return MARKER.sub("", TYPST_TRACE.sub(r"\1\n", output)).strip() if "pdfmd-fit-" in output else output


def diagnostics(output: str, source: Path) -> None:
    figures: dict[tuple[int, str], dict[int, str]] = {}
    for status, number, part, name in MARKER.findall(output):
        figures.setdefault((int(number), status), {})[int(part)] = name
    records = []
    for (number, status), pieces in sorted(figures.items()):
        try:
            name = bytes.fromhex("".join(pieces[key] for key in sorted(pieces))).decode()
        except ValueError:
            continue
        records.append((number, status, name))
    report = os.environ.get(REPORT_ENV)
    if report:
        Path(report).write_text(json.dumps(records), encoding="utf-8")
        return
    messages = {"s": "shrunk to fit the page body", "c": "caption alone is too tall for the page body",
                "o": "image and caption are too tall for the page body"}
    for _, status, name in records:
        print(f"WARN  {core.display_path(source)}: figure {name!r}: {messages[status]}", file=sys.stderr)
