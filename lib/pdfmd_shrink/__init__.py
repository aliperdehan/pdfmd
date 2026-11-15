"""Lossless PDF shrinking: the last step on every finished PDF.

pdfmd's own PDFs carry no object streams (the engines write some, and pdfmd's stamp pass, which rewrites the file with pypdf,
drops them), so a document built by it is a fifth to a tenth larger than it needs to be. This package rewrites the finished
file through a tool that can write them: object streams (PDF 1.5) and, unless asked for `fast`, Flate streams deflated again
at zlib's best level. Nothing in the content changes: no image is resampled or quantised, no font is touched, the pages, the
text, the Info dictionary, the XMP and the attachments stay as they were. Decisions D42 and D51 (the maintainer's notes).

`core` is the `pdfmd` module (see `pdfmd_base`); the package is loaded by the build only when a PDF was written, never at start.

The setting `shrink` (`pdfmd-options`, the config, `--setup`; `--shrink` / `--no-shrink` on the command line, which reaches a
`-b -j` worker as `PDFMD_SHRINK`): `true` (the default: object streams and recompression), `fast` (object streams only) or
`false`. `shrink-timeout` is the seconds one run of the tool may take (0 or a negative number: no limit).

The providers, in order (the first one installed does the work):

1. `qpdf`, the binary on PATH;
2. `pikepdf`, qpdf's Python binding (pip installs it everywhere, Windows and macOS included, where qpdf has no ready binary);
3. `mutool` (MuPDF), when its `clean` has `-Z` (objstms); it has no separate recompression, so `fast` and `true` are the same
   there (`clean -z -Z`).

Not used: pdfcpu (rewrites /CreationDate, /ModDate and /Producer, and refuses pdfmd's own LaTeX output), Ghostscript (it
distils again, which is lossy), cpdf (its licence).

The new file replaces the old one only when the tool succeeded (qpdf's exit 3, "warnings", counts as a failure), the page count
is the same and the file is smaller; then through a temporary file beside it and one rename. Anything else leaves the original
untouched and the build stays what it was: silent unless `--verbose`. A file that declares PDF/A-1 gets no object streams (they
need PDF 1.5; PDF/A-1 is 1.4), only the recompression.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from pdfmd_base import core
from pdfmd_base import atomic_file, timed

ENV = "PDFMD_SHRINK"
MODES = ("true", "fast", "false")
PROVIDERS = ("qpdf", "pikepdf", "mutool")
SHRINK_TIMEOUT = 120.0        # seconds one run of the tool may take when nothing says otherwise: the `shrink-timeout` default
COMPRESSION_LEVEL = 9         # zlib's maximum: a file-format fact, not a knob
PDFA1_RE = re.compile(rb"pdfaid:part(?:\s*=\s*[\"']\s*|\s*>\s*)1(?!\d)")
SCAN_CHUNK = 1 << 20          # the XMP is looked for in pieces of this size (a file may be large); the overlap covers a split match
_SAID: set[str] = set()       # one-time notes of this run


class Outcome(NamedTuple):
    status: str               # "shrunk", "kept" (the tool's file was no better), "failed", "skipped", "none" (no tool), "off"
    provider: str = ""
    before: int = 0
    after: int = 0
    why: str = ""


class _Keep(Exception):
    """The tool's file is not taken: the original stays. ``kind`` is the Outcome status that says why."""

    def __init__(self, kind: str, why: str):
        super().__init__(why)
        self.kind, self.why = kind, why


# -- The setting --------------------------------------------------------------------------------------------------------

def parse_mode(value) -> str | None:
    """`true`, `fast` or `false` from a setting's value (a YAML boolean included); None when it says none of them."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().casefold()
    if text == "fast":
        return "fast"
    flag = core.option_flag(text)
    return None if flag is None else ("true" if flag else "false")


def _setting(md_path: Path, metadata_files: list[Path], key: str):
    if md_path.suffix.lower() in (".md", ".markdown"):
        return core.first_pdfmd_option(md_path, metadata_files, key)
    return core.config_options(md_path).get(key)


def resolve_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """The command line (`--shrink`, `--no-shrink`: `PDFMD_SHRINK`), else the document's `pdfmd-options.shrink`, its metadata
    files', the folder and global config's, else `true`."""
    chosen = parse_mode(os.environ.get(ENV))
    if chosen:
        return chosen
    value = _setting(md_path, metadata_files, "shrink")
    chosen = parse_mode(value)
    if chosen is None:
        if value is not None and "mode" not in _SAID:
            _SAID.add("mode")
            print(f"NOTE  shrink: `{value}` is not true, fast or false; using true", file=sys.stderr)
        return "true"
    return chosen


def timeout_for(md_path: Path, metadata_files: list[Path]) -> float | None:
    """Seconds one run of the tool may take (`shrink-timeout`); None for no limit (0 or a negative number)."""
    number = core.option_flag_number(_setting(md_path, metadata_files, "shrink-timeout"))
    seconds = SHRINK_TIMEOUT if number is None else number
    return seconds if seconds > 0 else None


# -- What is installed --------------------------------------------------------------------------------------------------

def _run(command: list[str], timeout: float | None) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                          timeout=timeout)


@functools.lru_cache(maxsize=None)
def qpdf_options(binary: str) -> frozenset[str]:
    """The long options of this qpdf (an old one has no `--recompress-flate`)."""
    for argument in ("--help=all", "--help"):
        try:
            done = _run([binary, argument], 30)
        except (OSError, subprocess.SubprocessError):
            continue
        found = frozenset(re.findall(r"--[a-z][a-z0-9-]+", done.stdout + done.stderr))
        if done.returncode == 0 and "--object-streams" in found:
            return found
    return frozenset()


@functools.lru_cache(maxsize=None)
def mutool_has_objstms(binary: str) -> bool:
    """Whether this MuPDF's `mutool clean` writes object streams (`-Z`, MuPDF 1.2x)."""
    try:
        done = _run([binary, "clean"], 30)
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(re.search(r"^\s*-Z\b", done.stdout + done.stderr, re.M))


def available() -> list[tuple[str, str]]:
    """(provider, where) for each installed one, in the order they are tried."""
    found: list[tuple[str, str]] = []
    binary = core.which("qpdf")
    if binary and qpdf_options(binary):
        found.append(("qpdf", binary))
    try:
        if importlib.util.find_spec("pikepdf") is not None:
            found.append(("pikepdf", "Python module"))
    except (ImportError, ValueError):
        pass
    binary = core.which("mutool")
    if binary and mutool_has_objstms(binary):
        found.append(("mutool", binary))
    return found


def install_hint() -> str:
    first = {"darwin": "brew install qpdf", "win32": "scoop install qpdf"}.get(sys.platform, "apt install qpdf")
    return f"{first}, or pip install pikepdf"


def check_rows() -> list[str]:
    """The `--check-dependencies` rows: which provider shrinks the PDFs."""
    found = available()
    rows = [f"OK    {name}  ({where})" + ("  <- shrinks the PDFs" if number == 0 else "")
            for number, (name, where) in enumerate(found)]
    if not found:
        rows.append(f"MISS  qpdf, pikepdf, mutool (optional: smaller PDFs, lossless; {install_hint()})")
    return rows


def budget_hint(md_path: Path, metadata_files: list[Path]) -> str:
    """What the size-budget WARN adds when shrinking is on and no tool is there to do it."""
    if resolve_mode(md_path, metadata_files) == "false" or available():
        return ""
    return f"; a lossless shrink needs one of qpdf, pikepdf or mutool ({install_hint()})"


# -- One file -----------------------------------------------------------------------------------------------------------

def declares_pdfa1(path: Path) -> bool:
    """Whether the file's XMP says it is PDF/A-1 (which allows PDF 1.4 only: no object streams)."""
    carry = b""
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(SCAN_CHUNK)
                if not chunk:
                    return False
                if PDFA1_RE.search(carry + chunk):
                    return True
                carry = chunk[-64:]
    except OSError:
        return False


def _qpdf_pages(binary: str, path: Path, timeout: float | None) -> int | None:
    done = _run([binary, "--show-npages", str(path)], timeout)
    return int(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip().isdigit() else None


def _with_qpdf(source: Path, target: Path, mode: str, pdfa1: bool, timeout: float | None, verbose: bool):
    binary = core.which("qpdf")
    options = qpdf_options(binary)
    if pdfa1 and (mode == "fast" or "--recompress-flate" not in options):
        return "skipped", None, None, "PDF/A-1 takes no object streams"
    command = [binary, "--object-streams=" + ("disable" if pdfa1 else "generate")]
    if mode == "true" and "--recompress-flate" in options:
        command.append("--recompress-flate")
        if "--compression-level" in options:
            command.append(f"--compression-level={COMPRESSION_LEVEL}")
    if "--deterministic-id" in options:
        command.append("--deterministic-id")
    command += [str(source), str(target)]
    core.log_cmd(command, source.parent, verbose)
    done = _run(command, timeout)
    if done.returncode != 0:                                  # 2 = error, 3 = warnings: either way the original stays
        return "failed", None, None, f"qpdf exit {done.returncode}"
    return "ok", _qpdf_pages(binary, source, timeout), _qpdf_pages(binary, target, timeout), ""


def _with_mutool(source: Path, target: Path, mode: str, pdfa1: bool, timeout: float | None, verbose: bool):
    binary = core.which("mutool")
    if pdfa1 and mode == "fast":
        return "skipped", None, None, "PDF/A-1 takes no object streams"
    flags = ["-z"] if pdfa1 else ["-z", "-Z"]            # -z deflates what is stored raw; no -f/-i, no -g: nothing else changes
    command = [binary, "clean", *flags, str(source), str(target)]
    core.log_cmd(command, source.parent, verbose)
    done = _run(command, timeout)
    if done.returncode != 0:
        return "failed", None, None, f"mutool exit {done.returncode}"
    counts = []
    for path in (source, target):
        shown = _run([binary, "show", str(path), "trailer/Root/Pages/Count"], timeout)
        text = shown.stdout.strip()
        counts.append(int(text) if shown.returncode == 0 and text.isdigit() else None)
    return "ok", counts[0], counts[1], ""


def _with_pikepdf(source: Path, target: Path, mode: str, pdfa1: bool, timeout: float | None, verbose: bool):
    import pikepdf
    if pdfa1 and mode == "fast":
        return "skipped", None, None, "PDF/A-1 takes no object streams"
    core.vprint(verbose, f"  pikepdf {pikepdf.__version__}: save {core.display_path(source)} with object streams"
                         f"{'' if pdfa1 else ' (not for PDF/A-1)'}")
    settings = getattr(pikepdf, "settings", None)
    if mode == "true" and settings is not None and hasattr(settings, "set_flate_compression_level"):
        settings.set_flate_compression_level(COMPRESSION_LEVEL)
    modes = pikepdf.ObjectStreamMode
    with pikepdf.open(source) as pdf:
        pages = len(pdf.pages)
        pdf.save(target, object_stream_mode=modes.disable if pdfa1 else modes.generate,
                 recompress_flate=(mode == "true"), deterministic_id=True,
                 fix_metadata_version=False, preserve_pdfa=False)      # both would re-serialise the XMP: not lossless
    with pikepdf.open(target) as made:
        return "ok", pages, len(made.pages), ""


RUNNERS = {"qpdf": _with_qpdf, "pikepdf": _with_pikepdf, "mutool": _with_mutool}


def shrink_file(path: Path, mode: str = "true", timeout: float | None = SHRINK_TIMEOUT, verbose: bool = False) -> Outcome:
    """Rewrite the PDF at ``path`` losslessly and smaller, or leave it as it is; never raises."""
    if mode not in ("true", "fast"):
        return Outcome("off")
    found = available()
    if not found:
        return Outcome("none")
    provider = found[0][0]
    try:
        before = path.stat().st_size
        pdfa1 = declares_pdfa1(path)
        with atomic_file(path) as target:
            status, pages_before, pages_after, why = RUNNERS[provider](path, target, mode, pdfa1, timeout, verbose)
            if status != "ok":
                raise _Keep(status, why or "the tool failed")
            if pages_before is None or pages_before != pages_after:
                raise _Keep("failed", f"the page count could not be confirmed ({pages_before} -> {pages_after})")
            after = target.stat().st_size
            if after >= before:
                raise _Keep("kept", f"not smaller ({after} bytes against {before})")
    except _Keep as reason:
        return Outcome(reason.kind, provider, 0, 0, reason.why)
    except subprocess.TimeoutExpired:
        return Outcome("failed", provider, 0, 0, "the tool ran out of time (shrink-timeout)")
    except Exception as error:                                # a shrink must never fail a build: the original is whole
        return Outcome("failed", provider, 0, 0, f"{type(error).__name__}: {error}")
    return Outcome("shrunk", provider, before, after)


def size_text(size: int) -> str:
    return f"{size / 1024:.0f} KB" if size < 1048576 else f"{size / 1048576:.1f} MB"


@timed("shrink PDF")
def shrink_output(output: Path | None, md_path: Path, metadata_files: list[Path], verbose: bool) -> Outcome:
    """The build's last step on its PDF (see the module's note). Silent unless ``verbose``."""
    if output is None or output.suffix.lower() != ".pdf" or not output.is_file():
        return Outcome("off")
    mode = resolve_mode(md_path, metadata_files)
    if mode == "false":
        return Outcome("off")
    outcome = shrink_file(output, mode, timeout_for(md_path, metadata_files), verbose)
    name = core.display_path(output)
    if outcome.status == "shrunk":
        core.vprint(verbose, f"SHRINK  {name}: {size_text(outcome.before)} -> {size_text(outcome.after)} ({outcome.provider})")
    elif outcome.status == "none":
        if "none" not in _SAID:
            _SAID.add("none")
            core.vprint(verbose, f"SHRINK  none of qpdf, pikepdf or mutool is installed; the PDF is left as built ({install_hint()})")
    elif outcome.status != "off":
        core.vprint(verbose, f"SHRINK  {name}: left as built ({outcome.provider}: {outcome.why})")
    return outcome
