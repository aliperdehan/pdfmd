"""Select the figure fitter and decode the diagnostics from the typesetting pass."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pdfmd_base import core
from pdfmd_lua import path


MARKER = re.compile(
    r"(?m)^(?:\[WARNING\] )?(?:Missing character: There is no|warning: unknown font family:) "
    r"pdfmd-fit-([sc])-(\d+)-(\d+)-([0-9a-f]*)[ \t]*\r?$"
)
TYPST_TRACE = re.compile(r"(?m)(warning: unknown font family: pdfmd-fit-[^\r\n]+)\r?\n"
                         r"(?:[ \t]+[┌│].*\r?\n)*")


def arguments(writer: str, source: Path, metadata: list[Path]) -> list[str]:
    if writer not in (*core.LATEX_ENGINES, "latex", "typst") or writer == "context":
        return []
    script = path("figure_fit")
    if script is None:
        return []
    flag = core.option_flag(core.first_pdfmd_option(source, metadata, "figure-fit"))
    # Tectonic retains TeX's successful-run diagnostics only when asked for engine chatter.
    chatter = ["--pdf-engine-opt=--print"] if writer == "tectonic" else []
    return [*chatter, "-M", f"pdfmd-figure-fit={'off' if flag is False else 'on'}", "--lua-filter", str(script)]


def without_diagnostics(output: str) -> str:
    return MARKER.sub("", TYPST_TRACE.sub(r"\1\n", output)) if "pdfmd-fit-" in output else output


def diagnostics(output: str, source: Path) -> None:
    figures: dict[tuple[int, str], dict[int, str]] = {}
    for status, number, part, name in MARKER.findall(output):
        figures.setdefault((int(number), status), {})[int(part)] = name
    for (_, status), pieces in sorted(figures.items()):
        try:
            name = bytes.fromhex("".join(pieces[key] for key in sorted(pieces))).decode()
        except ValueError:
            continue
        message = ("shrunk to fit the page body" if status == "s" else
                   "caption alone is too tall for the page body")
        print(f"WARN  {core.display_path(source)}: figure {name!r}: {message}", file=sys.stderr)
