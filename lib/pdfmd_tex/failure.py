"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_tex.failure`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from bisect import bisect_right
from pathlib import Path

from pdfmd_base import core
from pdfmd_log import CHATTER, emit


TEX_PROBE_DOCUMENT = "\\documentclass{article}\\usepackage{fontspec}\\begin{document}x\\end{document}\n"


TEX_PROBES: dict[str, tuple[str, str] | None] = {}


def probe_tex_cause(engine: str, timeout: int = 120) -> tuple[str, str] | None:
    """Pandoc reports a LuaTeX run that cannot start its font loader only as `Fatal error occurred, no output PDF file
    produced`; the cause (an unwritable cache, a corrupt font database) is in the engine's own console. Run a one-line page
    with the same engine, in the same environment, and read that. Asked once per engine in a run; None when it cannot tell."""
    if engine not in TEX_PROBES:
        TEX_PROBES[engine] = None
        executable = core.which(engine) if engine == "lualatex" else None
        if executable:
            with tempfile.TemporaryDirectory(prefix="pdfmd-texprobe-") as scratch:
                folder = Path(scratch)
                (folder / "probe.tex").write_text(TEX_PROBE_DOCUMENT, encoding="utf-8")
                try:
                    done = subprocess.run([executable, "-interaction=nonstopmode", "-halt-on-error", "probe.tex"], cwd=folder,
                                          capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                                          stdin=subprocess.DEVNULL)
                    text = done.stdout + done.stderr
                except (OSError, subprocess.TimeoutExpired):
                    text = ""
                log = folder / "probe.log"
                if log.is_file():
                    text += "\n" + log.read_text(encoding="utf-8", errors="replace")
            TEX_PROBES[engine] = core.tex_failure_cause(text)
    return TEX_PROBES[engine]


SHOWN_LOCATIONS: set[tuple[str, str]] = set()


LATEX_CONTEXT_RE = re.compile(r"(?m)^[ \t]*l\.\d+[ \t]+(.+)$")


def source_words(text: str) -> tuple[str, list[int], list[int]]:
    """Put Markdown on one line and retain each original line's starting offset."""
    collapsed: list[str] = []
    starts: list[int] = []
    lines: list[int] = []
    size = 0
    for number, line in enumerate(text.splitlines(), 1):
        piece = re.sub(r"\s+", " ", line.strip())
        if piece:
            starts.append(size)
            lines.append(number)
            collapsed.append(piece)
            size += len(piece) + 1
    return " ".join(collapsed), starts, lines


def source_position(sources, context: str):
    """Locate the most specific TeX context across the original Markdown inputs."""
    context = re.sub(r"\s+", " ", context.strip())
    command = re.search(r"(\\[A-Za-z@]+)\s*$", context)
    candidates = (context, context[-30:], command.group(1) if command else "")
    indexed = [(path, *source_words(text)) for path, text in sources]
    for needle in dict.fromkeys(candidates):
        if len(needle) < 4:
            continue
        hits = {(path, lines[bisect_right(starts, match.start()) - 1])
                for path, haystack, starts, lines in indexed for match in re.finditer(re.escape(needle), haystack)}
        if hits:
            return hits.pop() if len(hits) == 1 else None
    return None


def source_line_for(text: str, context: str) -> int | None:
    """The original Markdown line corresponding to a unique LaTeX context."""
    found = source_position([(None, text)], context)
    return found[1] if found else None


def latex_error_location(label: str, stderr: str, *, sources=()) -> str | None:
    """Report the source part and line when LaTeX's generated context identifies them."""
    found = LATEX_CONTEXT_RE.search(stderr)
    if not found:
        return None
    originals = []
    for path in dict.fromkeys(sources or (Path(label),)):
        if path.suffix.lower() in core.MARKDOWN_LIKE_SUFFIXES:
            text = core.read_text_best_effort(path)
            if text:
                originals.append((path, text))
    context = found.group(1).strip()
    location = source_position(originals, context)
    if location is None:
        return None
    path, number = location
    return f"near line {number} of {core.display_path(path)}: {context[:100]}"


def report_engine_failure(label: str, engine: str, result: subprocess.CompletedProcess,
                          remaining: list[str], debug: bool, stopped: str | None = None, *, sources=()) -> None:
    """Print why one PDF-engine attempt failed -- always, not just under --verbose.

    Added 2026-09-17 alongside engine_failure_reason() (see its docstring):
    every engine failure now gets at least a one-line reason for free.
    --debug goes further and dumps the engine's full captured stderr right
    here, inline, for when that one-line reason is too compressed to
    actually diagnose from (several stacked LaTeX errors, or a Pandoc-level
    error with no leading '!'/'Error' line at all) -- the previous way to
    see this was rerunning by hand with --engine <name> --verbose, which
    means already suspecting which engine to force before you've seen why
    any of them failed.
    """
    reason = core.engine_failure_reason(result.stderr)
    hint = f" ({reason})" if reason else ""
    if stopped:                     # engine-fallback stops the chain here (lib/pdfmd_chain)
        emit("warning", None, f"WARN  {label}: {engine} failed{hint}; {stopped}", file=sys.stderr)
    elif remaining:
        emit("warning", None, f"WARN  {label}: {engine} failed{hint}; trying {remaining[0]}...", file=sys.stderr)
    else:
        emit("warning", None, f"WARN  {label}: {engine} failed{hint}; no more engines to try. "
              f"Rerun with --engine {engine} --verbose (or --debug) for the full log.",
              file=sys.stderr)
    where = latex_error_location(label, (result.stderr or "") + "\n" + (result.stdout or ""), sources=sources)
    if where and (label, where) not in SHOWN_LOCATIONS:       # the next LaTeX engine can fail in the same place
        SHOWN_LOCATIONS.add((label, where))
        emit("warning", None, f"      {where}", file=sys.stderr)
    known = core.tex_failure_cause(result.stderr)
    if known is None and engine == "lualatex" and "Fatal error occurred" in result.stderr:
        known = probe_tex_cause(engine)                                  # the cause is in the console, not in Pandoc's text
    if known and (label, known[0]) not in SHOWN_LOCATIONS:             # once per document, not once per engine
        SHOWN_LOCATIONS.add((label, known[0]))
        emit("warning", None, f"      cause: {known[0]}; {known[1]}", file=sys.stderr)
    if (debug or CHATTER.get() == "debug") and result.stderr.strip():
        emit("debug", None, f"----- {label}: {engine} stderr (--debug) -----", file=sys.stderr)
        emit("debug", None, result.stderr.strip(), file=sys.stderr)
        emit("debug", None, "-" * 40, file=sys.stderr)


def tex_argument(path) -> str:
    """A path as it goes on a TeX engine's command line. The engine reads that line as TeX, where `~` is an active
    character: on Windows, a temporary folder under its short name (`C:\\Users\\RUNNER~1\\AppData\\Local\\Temp`, what
    the CI runner and any long user name give) made MiKTeX's LuaLaTeX look for no file at all (`texput.log`). The long
    name has no `~`; elsewhere the path is unchanged."""
    return str(Path(path).resolve()) if os.name == "nt" else str(path)
