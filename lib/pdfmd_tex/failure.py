"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_tex.failure`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pdfmd_base import core


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


LATEX_CONTEXT_RE = re.compile(r"(?m)^l\.(\d+) (.+)$")


def source_line_for(text: str, context: str) -> int | None:
    """The line of ``text`` (a Markdown source) that ``context`` (the words LaTeX printed up to its error) came from.
    The generated LaTeX is wrapped and escaped differently, so the match is on the words with whitespace collapsed,
    first the whole context, then its last 30 characters, then the last command in it."""
    collapsed: list[str] = []
    starts: list[tuple[int, int]] = []
    size = 0
    for number, line in enumerate(text.splitlines(), 1):
        piece = re.sub(r"\s+", " ", line.strip())
        if piece:
            starts.append((size, number))
            collapsed.append(piece)
            size += len(piece) + 1
    haystack = " ".join(collapsed)
    context = re.sub(r"\s+", " ", context.strip())
    command = re.search(r"(\\[A-Za-z@]+)\s*$", context)
    for needle in (context, context[-30:], command.group(1) if command else ""):
        if len(needle) < 4:
            continue
        found = haystack.find(needle)
        if found >= 0:
            return [number for start, number in starts if start <= found][-1]
    return None


def latex_error_location(label: str, stderr: str) -> str | None:
    """`near line 9 of doc.md: Second has \\badmacro` for a LaTeX error whose context is in the Markdown ``label``
    names (Pandoc prints `l.67 Second has \\badmacro`, a line of the LaTeX it wrote, which nobody sees)."""
    path = Path(label)
    found = LATEX_CONTEXT_RE.search(stderr or "")
    if not found or path.suffix.lower() not in (".md", ".markdown") or not path.is_file():
        return None
    try:
        number = source_line_for(path.read_text(encoding="utf-8-sig"), found.group(2))
    except (OSError, UnicodeDecodeError):
        return None
    if number is None:
        return None
    return f"near line {number} of {core.display_path(path)}: {found.group(2).strip()[:100]}"


def report_engine_failure(label: str, engine: str, result: subprocess.CompletedProcess,
                          remaining: list[str], debug: bool, stopped: str | None = None) -> None:
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
        print(f"WARN  {label}: {engine} failed{hint}; {stopped}", file=sys.stderr)
        where = latex_error_location(label, result.stderr)
        if where and (label, where) not in SHOWN_LOCATIONS:
            SHOWN_LOCATIONS.add((label, where))
            print(f"      {where}", file=sys.stderr)
    elif remaining:
        print(f"WARN  {label}: {engine} failed{hint}; trying {remaining[0]}...", file=sys.stderr)
        where = latex_error_location(label, result.stderr)
        if where and (label, where) not in SHOWN_LOCATIONS:       # the next LaTeX engine fails in the same place: once
            SHOWN_LOCATIONS.add((label, where))
            print(f"      {where}", file=sys.stderr)
    else:
        print(f"WARN  {label}: {engine} failed{hint}; no more engines to try. "
              f"Rerun with --engine {engine} --verbose (or --debug) for the full log.",
              file=sys.stderr)
        where = latex_error_location(label, result.stderr)
        if where and (label, where) not in SHOWN_LOCATIONS:
            SHOWN_LOCATIONS.add((label, where))
            print(f"      {where}", file=sys.stderr)
    known = core.tex_failure_cause(result.stderr)
    if known is None and engine == "lualatex" and "Fatal error occurred" in result.stderr:
        known = probe_tex_cause(engine)                                  # the cause is in the console, not in Pandoc's text
    if known and (label, known[0]) not in SHOWN_LOCATIONS:             # once per document, not once per engine
        SHOWN_LOCATIONS.add((label, known[0]))
        print(f"      cause: {known[0]}; {known[1]}", file=sys.stderr)
    if debug and result.stderr.strip():
        print(f"----- {label}: {engine} stderr (--debug) -----", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        print("-" * 40, file=sys.stderr)


def tex_argument(path) -> str:
    """A path as it goes on a TeX engine's command line. The engine reads that line as TeX, where `~` is an active
    character: on Windows, a temporary folder under its short name (`C:\\Users\\RUNNER~1\\AppData\\Local\\Temp`, what
    the CI runner and any long user name give) made MiKTeX's LuaLaTeX look for no file at all (`texput.log`). The long
    name has no `~`; elsewhere the path is unchanged."""
    return str(Path(path).resolve()) if os.name == "nt" else str(path)
