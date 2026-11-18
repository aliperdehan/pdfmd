"""Measure figures with the normal PDF build, and locate its findings in the source."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pdfmd_base import core
from pdfmd_check.lint import Analysis, Findings, Problem, Source
from pdfmd_filters.lua import figure_fit_module

REPORT_ENV = figure_fit_module().REPORT_ENV


CODE = "figure-too-tall"
IMAGE_CAPTION = re.compile(r"!\[([^\]]+)\]\s*(?=[(\[])")
FIGURE_ID = re.compile(r"\{[^{}\n]*?#([^\s{}]+)")
FIGURE_SYNTAX = re.compile(r"!\[|(?mi:^[ \t]*(?:`{3,}|~{3,}|:{3,})[^\n]*(?:caption\s*=|#fig[:-]))")
OUTCOME = {
    "s": "build shrinks it to fit the page body",
    "o": "build lets it run past the page body (figure fit is off)",
    "c": "build keeps its original size because the caption alone is too tall",
}


def name_key(name: str) -> str:
    """Compare visible caption words, allowing Markdown punctuation and smart typography."""
    return "".join(char for char in name.casefold() if char.isalnum())


def locate(analyses: list[Analysis], records: list, main: Path) -> list[Problem]:
    ids: dict[str, list[tuple[Analysis, int]]] = {}
    captions: list[tuple[str, Analysis, int]] = []
    for analysis in analyses:
        for match in FIGURE_ID.finditer(analysis.masked):
            spot = analysis.line(match.start())
            ids.setdefault(match[1], []).append((analysis, spot))
        for match in IMAGE_CAPTION.finditer(analysis.masked):
            caption = analysis.source.text[match.start(1):match.end(1)]
            captions.append((name_key(caption), analysis, analysis.line(match.start())))

    findings = Findings()
    for number, outcome, name in records:
        message = f"figure {name!r}: {OUTCOME[outcome]}"
        locations = ids.get(name, [])
        if not locations:
            prefix = name_key(name)
            if prefix:
                locations = [(analysis, line) for key, analysis, line in captions if key.startswith(prefix)]
                # Repeated captions ordinarily follow the writer's figure order.
                if len(locations) > 1 and number <= len(captions):
                    key, analysis, line = captions[number - 1]
                    if key.startswith(prefix):
                        locations = [(analysis, line)]
        if len(locations) == 1:
            analysis, line = locations[0]
            findings.add(analysis, line, CODE, message)
        else:
            findings.problems.append(Problem(core.display_path(main), 0, CODE, message))
    return findings.problems


def options(args, engines: list[str], pandoc_options: list[str]) -> list[str]:
    """Forward the options that select the document's renderer, source and styles."""
    result = ["--to=pdf", "--engine=" + ",".join(engines), "--no-cache", "--no-shrink",
              "--cache-location=global", "--build-log=off"]
    for flag in ("paper", "font", "from_format", "preset", "metadata_precedence", "engine_fallback",
                 "flavour", "css_scope"):
        value = getattr(args, flag)
        if value:
            option = "from" if flag == "from_format" else flag.replace("_", "-")
            result.append(f"--{option}={value}")
    for flag in ("global_metadata", "strict"):
        value = getattr(args, flag)
        if value is not None:
            result.append(("--" if value else "--no-") + flag.replace("_", "-"))
    for flag, values in (("-V", args.variable), ("--css", args.css)):
        for value in values:
            result += [flag, value]
    if args.trust_embedded:
        result.append("--trust-embedded")
    if args.metadata_file == []:
        result.append("-y")
    if args.no_auto is not None:
        result += ["--no-auto", *args.no_auto]
    return [*result, *pandoc_options]


def figure_problems(sources: list[Source], document: Path, metadata: list[Path], args,
                    pandoc_options: list[str]) -> list[Problem]:
    analyses = [Analysis(source) for source in sources]
    if args.presentation or not any(FIGURE_SYNTAX.search(analysis.masked) for analysis in analyses):
        return []
    if not core.which("pandoc"):
        print("NOTE  --check: figure heights are not checked without Pandoc", file=sys.stderr)
        return []
    try:
        engines = core.resolve_engines(document, args.engine, core.select_engines(args.engine, False),
                                       False, "pdf", metadata)
    except SystemExit:
        engines = []
    supported = (core.LATEX_ENGINES - {"context"}) | {"typst"}
    if not engines or engines[0] not in supported:
        print("NOTE  --check: figure heights require a LaTeX or Typst build", file=sys.stderr)
        return []
    engines = [engine for engine in engines if engine in supported]
    with tempfile.TemporaryDirectory(prefix="pdfmd-figure-check-") as scratch:
        folder = Path(scratch)
        report = folder / "figures.json"
        env = {**os.environ, REPORT_ENV: str(report), "PDFMD_NO_PROMPT": "1",
               "XDG_CACHE_HOME": str(folder), "LOCALAPPDATA": str(folder)}
        command = core._api_command(document.resolve(), "pdf", folder / "check.pdf",
                                    options(args, engines, pandoc_options), args.metadata_file,
                                    None, False, False)
        try:
            subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, env=env)
            records = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("NOTE  --check: figure heights could not be measured in a temporary build", file=sys.stderr)
            return []
    return locate(analyses, records, document)
