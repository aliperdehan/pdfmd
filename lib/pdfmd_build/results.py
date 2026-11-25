"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_build.results`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from pdfmd_base import core
from pdfmd_base import timed

from pdfmd_base import pandoc_run
from pdfmd_log import WARNING_LINE_RE, emit
from pdfmd_reader.controls import diagnostic_scope, repair_controls


def timing_module():
    """pdfmd_buildinfo.timing, or None in a lone pdfmd.py (no time is shown then)."""
    try:
        from pdfmd_buildinfo import timing
        return timing
    except ImportError:
        return None


def time_label(result) -> str:
    """`  in 3:07` for the closing line; nothing when the time is off."""
    text = getattr(result, "time_text", "")
    return f"  in {text}" if text else ""


def record_engine(engine: str, failed: list[str] | tuple[str, ...] = ()) -> None:
    """Note the engine that succeeded and the engines that were tried and failed before it."""
    core.BUILD["engine"], core.BUILD["failed"] = engine, [name for name in failed if name != engine]


class Built(tuple):
    """convert_one's `(path, ok, message)`, carrying the engine too (a tuple subclass: three-way unpacking and pickling
    through a process pool both keep working)."""

    def __new__(cls, items, engine: str | None = None, failed=(), output=None):
        self = super().__new__(cls, items)
        self.engine, self.failed, self.output = engine, list(failed), output
        self.seconds, self.time_text, self.time_style, self.steps = None, "", "auto", []     # see attach_time
        self.record_path = None                                                       # see BuildRecorder
        self.stopped = ""                                       # engine-fallback stopped the chain (lib/pdfmd_chain)
        return self


def engine_label(result) -> str:
    """`  (lualatex)` or `  (typst; lualatex failed)` for the closing line; nothing when no engine was involved."""
    engine = getattr(result, "engine", None)
    if not result[1] and getattr(result, "stopped", ""):
        return f"  ({result.stopped})"
    if not engine or not result[1]:
        return ""
    failed = getattr(result, "failed", [])
    return f"  ({engine}" + (f"; {', '.join(failed)} failed" if failed else "") + ")"


def ok_delimiter() -> str:
    """What stands between the source and the file in `OK    report.md > report.pdf` (`options.ok-delimiter`)."""
    value = core.config_options().get("ok-delimiter")
    return ">" if value is None or not str(value).strip() else str(value).strip()


def built_name(result) -> str:
    """` > report.pdf` for the closing line: the file a successful build wrote, by its name when it sits beside the
    source, else by its path; nothing when the build wrote no one file."""
    output = getattr(result, "output", None)
    if output is None or not result[1]:
        return ""
    try:
        beside = Path(output).parent.resolve() == Path(result[0]).parent.resolve()
    except OSError:
        beside = False
    return f" {ok_delimiter()} {Path(output).name if beside else core.display_path(Path(output))}"


class _WarningTee:
    """A text stream that passes everything on and remembers the lines that are warnings."""

    def __init__(self, stream, lines: list[str]):
        self._stream, self._lines, self._partial = stream, lines, ""

    def remember_warning(self, text):
        self._partial += text
        *complete, self._partial = self._partial.split("\n")
        self._lines.extend(line.strip() for line in complete if WARNING_LINE_RE.match(line))

    def write(self, text):
        self.remember_warning(text)
        return self._stream.write(text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


@contextmanager
def warning_capture() -> Iterator[list[str]]:
    """Yield the list that fills with each WARN / [WARNING] line printed meanwhile (stdout and stderr)."""
    lines: list[str] = []
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _WarningTee(out, lines), _WarningTee(err, lines)
    try:
        with diagnostic_scope():
            yield lines
    finally:
        sys.stdout, sys.stderr = out, err


def resolve_strict(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether warnings fail ``md_path``'s build: --strict / --no-strict, else `pdfmd-options.strict`."""
    if core.STRICT_CLI is None and os.environ.get("PDFMD_STRICT") in ("0", "1"):
        return os.environ["PDFMD_STRICT"] == "1"       # a -j worker is a fresh process: main hands the flag down
    if core.STRICT_CLI is not None:
        return core.STRICT_CLI
    if md_path.suffix.lower() not in (".md", ".markdown"):
        return False
    return bool(core.option_flag(core.first_pdfmd_option(md_path, metadata_files, "strict")))


def resolve_budget(md_path: Path, metadata_files: list[Path]) -> tuple[float | None, float | None]:
    """(MB for one image or data file, MB for the output), None for no budget; 0 on the command line turns it off."""
    found = []
    for variable, key in (("PDFMD_MAX_ASSET_MB", "max-asset-mb"), ("PDFMD_MAX_OUTPUT_MB", "max-output-mb")):
        value = core.option_flag_number(os.environ.get(variable))
        if value is None and md_path.suffix.lower() in (".md", ".markdown"):
            value = core.option_flag_number(core.first_pdfmd_option(md_path, metadata_files, key))
        found.append(value if value and value > 0 else None)
    return found[0], found[1]


def size_text(size: int) -> str:
    return f"{size / 1048576:.1f} MB"


def check_asset_budget(sources: list[Path], md_path: Path, metadata_files: list[Path]) -> None:
    """WARN for each image the sources point at that is over the asset budget (before the build)."""
    limit, _ = resolve_budget(md_path, metadata_files)
    if limit is None or core.BUILD.get("scanning"):          # the label scan builds the same document again: say it once
        return
    seen: set[Path] = set()
    for source in sources:
        for image in core.referenced_images(core.read_text_best_effort(source), source.parent):
            if image in seen:
                continue
            seen.add(image)
            try:
                size = image.stat().st_size
            except OSError:
                continue
            if size > limit * 1048576:
                emit("warning", None, f"WARN  {core.display_path(md_path)}: {core.display_path(image)} is {size_text(size)}, over the "
                      f"{limit:g} MB asset budget (--max-asset-mb, pdfmd-options.max-asset-mb)", file=sys.stderr)


NONMATH_DOLLAR_RE = re.compile(r"(?<![\\$])\$(?=[^\s$])([^$]*?)(?<=\S)\$(?=\d)(\d+(?:[.,]\d+)?)")


# a text between two dollars that looks like math: a TeX command, a script or brace, or a single letter; "$5/$10" is no math
MATH_LOOKING_RE = re.compile(r"\\[A-Za-z]+|[\^_{}]|^[A-Za-z]$")


NONMATH_DOLLAR_READERS = ("markdown", "gfm", "commonmark_x")


# the source-text scan that decides whether Pandoc is asked at all: any `$` + text + `$` + digit (a span may run over lines; the
# AST has the last word, so this only has to find every candidate, and "costs $5 and $10" is none: a space comes before the 2nd $)
NONMATH_DOLLAR_CANDIDATE_RE = re.compile(r"(?<![\\$])\$(?=[^\s$])([^$]*)(?<=\S)\$\d")


_NONMATH_DOLLARS: dict[tuple, list[tuple[int, str, str]]] = {}


def inline_text_runs(document) -> Iterator[str]:
    """The text of each stretch of plain words and raw TeX in a Pandoc JSON document (math, code and any
    formatting end a stretch): where a `$...$` that Pandoc did not take for math is still to be seen."""
    stack = [document]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
            if not any(isinstance(item, dict) and item.get("t") in ("Str", "RawInline") for item in node):
                continue
            run: list[str] = []
            for item in node:
                kind = item.get("t") if isinstance(item, dict) else None
                content = item.get("c") if isinstance(item, dict) else None
                if kind == "Str" and isinstance(content, str):
                    run.append(content)
                elif kind in ("Space", "SoftBreak"):
                    run.append(" ")
                elif (kind == "RawInline" and isinstance(content, list) and len(content) == 2
                        and content[0] in ("tex", "latex")):
                    run.append(content[1])
                else:
                    if run:
                        yield "".join(run)
                    run = []
            if run:
                yield "".join(run)


def nonmath_dollars(md_path: Path, reader: str | None) -> list[tuple[int, str, str]]:
    """(line, the text as written, the way to write it) for each `$...$` of a Markdown file that Pandoc reads
    as text because the closing `$` is followed by a digit. Empty when Pandoc is not there or the reader has no
    dollar math; a `$` the author escaped, or a price, is not one."""
    base = (reader or "markdown").split("+")[0].split("-")[0]
    if base not in NONMATH_DOLLAR_READERS or "-tex_math_dollars" in (reader or ""):
        return []
    pandoc = core.which("pandoc")
    try:
        stat = md_path.stat()
        key = (str(md_path), stat.st_mtime_ns, stat.st_size, reader)
    except OSError:
        return []
    if key in _NONMATH_DOLLARS:
        return _NONMATH_DOLLARS[key]
    found: list[tuple[int, str, str]] = []
    if pandoc:
        try:
            raw = md_path.read_text(encoding="utf-8-sig")
            if not any(MATH_LOOKING_RE.search(candidate.group(1)) for candidate in NONMATH_DOLLAR_CANDIDATE_RE.finditer(core.strip_code_text(raw))):
                _NONMATH_DOLLARS[key] = found                   # nothing that could be one: no Pandoc pass for it
                return found
            text = core.EMBED_BLOCK_RE.sub("", core.obsidian_source(repair_controls(raw), md_path, show=False))
            done = pandoc_run([pandoc, "-f", reader or "markdown", "-t", "json"], input=text, capture_output=True,
                                  text=True, encoding="utf-8", timeout=120)
            if done.returncode == 0:
                seen: set[str] = set()
                prose = core.strip_code_text(raw)
                runs = list(inline_text_runs(json.loads(done.stdout)))
                for run in runs:
                    for match in NONMATH_DOLLAR_RE.finditer(run):
                        inner = match.group(1)
                        if not MATH_LOOKING_RE.search(inner) or match.group(0) in seen:
                            continue
                        seen.add(match.group(0))
                        # where it stands in the file, as written: a soft break is any white space, and an escaped `$` does not match
                        words = [re.escape(word) for word in match.group(0).split(" ")]
                        written = [position.start() for position in re.finditer(r"(?<!\\)" + r"\s+".join(words), prose)]
                        # the same text with a dollar escaped (`\$\geq\$3`) is the same text to the reader: when those copies account
                        # for every one it gave, the unescaped ones were read as math (Pandoc 3.1.3's gfm reader has no digit rule)
                        any_way = len(re.findall(r"\s+".join(word.replace(r"\$", r"\\?\$") for word in words), prose))
                        if sum(text.count(match.group(0)) for text in runs) <= any_way - len(written):
                            continue
                        for line in sorted({prose.count("\n", 0, start) + 1 for start in written}):
                            found.append((line, match.group(0), f"${inner} {match.group(2)}$"))
        except (OSError, ValueError, subprocess.SubprocessError, UnicodeDecodeError):
            found = []
    found.sort()
    _NONMATH_DOLLARS[key] = found
    return found


def check_nonmath_dollars(sources: list[Path], cli_from: str | None, metadata_files: list[Path], fixed_reader: bool) -> None:
    """WARN `file:line` for each `$...$` the sources write as math that Pandoc reads as text (before the build)."""
    if core.BUILD.get("scanning"):                           # the label scan builds the same document again: say it once
        return
    for source in sources:
        if source.suffix.lower() not in (".md", ".markdown"):
            continue
        reader = cli_from if fixed_reader else core.resolve_from_format(source, cli_from, metadata_files)[0]   # --no-auto reader: no pick of pdfmd's
        for line, written, instead in nonmath_dollars(source, reader):
            emit("warning", None, f"WARN  {core.display_path(source)}:{line}: `{written}` is not math (Pandoc needs the closing $ not "
                  f"followed by a digit); write {instead}", file=sys.stderr)


@timed("size budget")
def check_output_budget(output: Path | None, sources: list[Path], md_path: Path, metadata_files: list[Path]) -> None:
    """WARN when the output is over the output budget, with the largest images behind it."""
    _, limit = resolve_budget(md_path, metadata_files)
    if limit is None or output is None:
        return
    try:
        size = output.stat().st_size
    except OSError:
        return
    if size <= limit * 1048576:
        return
    images = {}
    for source in sources:
        for image in core.referenced_images(core.read_text_best_effort(source), source.parent):
            try:
                images[image] = image.stat().st_size
            except OSError:
                pass
    biggest = sorted(images.items(), key=lambda item: -item[1])[:3]
    behind = ("; the largest images: " + ", ".join(f"{core.display_path(path)} {size_text(value)}" for path, value in biggest)) \
        if biggest and biggest[0][1] > 1048576 else ""
    emit("warning", None, f"WARN  {core.display_path(md_path)}: {core.display_path(output)} is {size_text(size)}, over the {limit:g} MB output budget "
          f"(--max-output-mb, pdfmd-options.max-output-mb){behind}"
          + (core.load_package("pdfmd_shrink").budget_hint(md_path, metadata_files) if output.suffix.lower() == ".pdf" else ""), file=sys.stderr)


def strict_message(lines: list[str]) -> str:
    unique = list(dict.fromkeys(lines))
    shown = "\n".join(f"  {line[:220]}" for line in unique[:5])
    more = f"\n  ... and {len(unique) - 5} more" if len(unique) > 5 else ""
    return (f"--strict: the build printed {len(unique)} warning{'s' if len(unique) != 1 else ''}, so it counts as "
            f"failed (the output was written):\n{shown}{more}")
