"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_output`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

from pdfmd_base import core


PICTURE_ONLY = ("png", "jpg", "tiff", "eps", "ps", "svg")   # the targets only this command writes


PICTURE_FORMATS = ("pdf", *PICTURE_ONLY)


ASSEMBLED_FORMAT = "assembled"


ASSEMBLED_SUFFIX = ".assembled.md"


# Conventional file extension for a Pandoc writer/target format, used to name
# an output file when the caller didn't give one an explicit suffix. Formats
# missing here fall back to ".<format>" -- a reasonable guess, since Pandoc's
# own format names are usually also their file extension.
FORMAT_EXTENSION = {
    "pdf": ".pdf", "png": ".png", "svg": ".svg", "jpg": ".jpg", "tiff": ".tiff", "eps": ".eps", "ps": ".ps",
    "html": ".html", "html4": ".html", "html5": ".html", "chunkedhtml": ".html",
    "latex": ".tex", "beamer": ".tex", "context": ".tex",
    "typst": ".typ",
    "plain": ".txt", "txt": ".txt", "ansi": ".ansi",
    "markdown": ".md", "gfm": ".md", "gfm+raw": ".md", "commonmark": ".md", "commonmark_x": ".md",
    "docx": ".docx", "odt": ".odt", "pptx": ".pptx",
    "epub": ".epub", "epub2": ".epub", "epub3": ".epub",
    "rst": ".rst", "org": ".org", "rtf": ".rtf",
    "docbook": ".xml", "docbook4": ".xml", "docbook5": ".xml",
    "json": ".json", "man": ".man", "ipynb": ".ipynb",
    "asciidoc": ".adoc", "asciidoctor": ".adoc",
    "textile": ".textile", "mediawiki": ".wiki", "opml": ".opml",
    # Not a Pandoc writer: pdfmd's own "stop after assembling" stage (--stop-at
    # markdown / --assemble-only). See write_assembled_markdown().
    ASSEMBLED_FORMAT: ASSEMBLED_SUFFIX,
}


# The reverse mapping, used to recognize that an explicit -o/--out filename
# (single-file and report/book modes only -- batch mode's -o is a directory)
# already states the target format on its own, e.g. "-o notes.html" needs no
# separate --to. Batch mode has no per-file filename to read, so it only
# responds to an explicit --to. Deliberately only the unambiguous, commonly
# typed extensions -- anything else should be requested with --to instead.
# the targets only Calibre writes (v3.29.0; see calibre_goal): `-o book.azw3` names one
CALIBRE_ONLY_FORMATS = ("azw3", "mobi", "kepub", "lit", "lrf", "pdb", "rb", "snb", "tcr", "pmlz", "htmlz", "txtz")


EXTENSION_FORMAT = {
    ".html": "html", ".htm": "html",
    ".tex": "latex",
    ".typ": "typst",
    ".txt": "txt", ".ansi": "ansi",
    ".md": "markdown", ".markdown": "markdown",
    ".docx": "docx", ".odt": "odt", ".pptx": "pptx",
    ".epub": "epub", ".rst": "rst", ".org": "org", ".rtf": "rtf", ".adoc": "asciidoc",
    ".json": "json", ".pdf": "pdf", ".png": "png", ".svg": "svg", ".jpg": "jpg", ".jpeg": "jpg", ".tif": "tiff", ".tiff": "tiff", ".eps": "eps", ".ps": "ps",
    **{"." + name: name for name in CALIBRE_ONLY_FORMATS},
    ".doc": "doc",                                                    # LibreOffice writes it (v3.29.1; see soffice_goal)
}


# Two-part endings that name a target the plain suffix would not: `-o notes.gfm.md` is `--to gfm` (the name
# `output_extension_for` gives a flat Markdown made from a .md file), where `-o notes.md` alone is Pandoc's Markdown.
COMPOUND_EXTENSION_FORMAT = {".gfm.md": "gfm"}


def format_from_output(path: Path | None) -> str | None:
    """Recognize a target format from an explicit output filename's suffix. An `.ascii` before the ending
    (`notes.ascii.txt`, `notes.ascii.gfm.md`, `notes.ascii.rst`) asks for that format with no byte above 127: `ascii`
    for text, else `ascii:FORMAT`."""
    if path is None or not path.suffix:
        return None
    name = path.name.lower()
    parts = name.split(".")
    for index in range(1, len(parts) - 1):
        if parts[index] == "ascii":
            base = format_from_output(Path("x." + ".".join(parts[index + 1:])))
            if base is None or base == "ascii" or base.startswith("ascii:"):
                return None
            return "ascii" if base == "txt" else f"ascii:{base}"
    for ending in sorted(COMPOUND_EXTENSION_FORMAT, key=len, reverse=True):
        if name.endswith(ending) and len(name) > len(ending):
            return COMPOUND_EXTENSION_FORMAT[ending]
    return EXTENSION_FORMAT.get(path.suffix.lower())


def output_extension_for(target_format: str, source: Path | None = None) -> str:
    """The suffix an output gets by default. Flat Markdown (`gfm`, `gfm+raw`) made from a `.md` file is `.gfm.md`: beside
    its source, never over it."""
    if target_format in ("gfm", "gfm+raw") and source is not None and source.suffix.lower() == ".md":
        extension = ".gfm.md"
    else:
        extension = FORMAT_EXTENSION.get(target_format, f".{target_format}")
    if core.ASCII_CLI["on"] and target_format in core.ASCII_FORMATS:       # --to ascii: another name, so the Unicode file stays
        extension = ".ascii" + extension
    return extension


REWRITE_NAME = "{stem} ({n}){ext}"


def rewrite_wanted(md_path: Path, metadata_files: list[Path]) -> bool:
    """--rewrite/--no-rewrite, else `pdfmd-options: {rewrite: ...}` (the document, its folder, the config), else on."""
    if core.REWRITE_CLI is not None:
        return core.REWRITE_CLI
    try:
        value = core.first_pdfmd_option(md_path, metadata_files, "rewrite")
    except Exception:
        return True
    return True if value is None else str(value).strip().casefold() not in ("false", "no", "off", "0")


def rewrite_template(md_path: Path, metadata_files: list[Path]) -> str:
    """`rewrite-name`: the numbered copy's name; it must have {n} and no folder, else the default with a WARN."""
    try:
        value = core.first_pdfmd_option(md_path, metadata_files, "rewrite-name", "rewrite_name")
    except Exception:
        value = None
    if value in (None, ""):
        return REWRITE_NAME
    template = str(value)
    if "{n}" not in template or re.search(r"[\\/]", template):
        print(f"WARN  rewrite-name '{template}' needs {{n}} and no folder; using {REWRITE_NAME}", file=sys.stderr)
        return REWRITE_NAME
    return template


def numbered_output(output: Path, template: str = REWRITE_NAME) -> Path:
    """``output`` when nothing is there, else the first free numbered name (`report (1).pdf`)."""
    if not output.exists():
        return output
    today = datetime.now().strftime("%Y%m%d")
    for number in range(1, 1000):
        name = (template.replace("{stem}", output.stem).replace("{ext}", output.suffix)
                .replace("{date}", today).replace("{n}", str(number)))
        candidate = output.with_name(name)
        if not candidate.exists():
            return candidate
    raise SystemExit(f"{core.display_path(output)} and the 999 numbered copies of it exist; remove some or name the output with -o")


def default_output_path(path: Path, target_format: str) -> Path:
    """Add the extension implied by target_format when the caller omitted one."""
    if path.suffix:
        return path
    return path.with_suffix(FORMAT_EXTENSION.get(target_format, f".{target_format}"))


BOPEN_RE = re.compile(r"^(?:(?P<all>all|a)|(?P<kind>fl|f|l|e|s)(?P<n>[0-9]+))$", re.IGNORECASE)


BOPEN_HELP = "all, fN (first N), lN (last N), flN (first half and last half), eN (the Nth, 2Nth ...), sN (the 1st, then every Nth: 1st, N+1th ...); joined by commas: f2,l3"


def parse_bopen(spec: str) -> list[tuple[str, int]]:
    """The selectors of a --bopen spec as (kind, N); kind is all, f, l, fl, e or s. Stops with the grammar when it is not one."""
    selectors: list[tuple[str, int]] = []
    for word in re.split(r"[,;]", re.sub(r"\s+", "", str(spec))):
        if not word:
            continue
        found = BOPEN_RE.match(word)
        if not found or (found.group("n") is not None and int(found.group("n")) < 1):
            raise SystemExit(f"--bopen {spec!r}: {word!r} is not a selector. A spec is {BOPEN_HELP}")
        selectors.append(("all", 0) if found.group("all") else (found.group("kind").lower(), int(found.group("n"))))
    if not selectors:
        raise SystemExit(f"--bopen {spec!r}: empty. A spec is {BOPEN_HELP}")
    return selectors


def bopen_indices(spec: str, count: int) -> list[int]:
    """The positions (0-based, in order) of ``count`` files that ``spec`` selects."""
    chosen: set[int] = set()
    for kind, number in parse_bopen(spec):
        if kind == "all":
            chosen.update(range(count))
        elif kind == "f":
            chosen.update(range(min(number, count)))
        elif kind == "l":
            chosen.update(range(max(0, count - number), count))
        elif kind == "fl":
            first = (number + 1) // 2
            chosen.update(range(min(first, count)))
            chosen.update(range(max(0, count - (number - first)), count))
        elif kind == "s":
            chosen.update(range(0, count, number))                    # Python's [::N]: the first, then every Nth
        else:
            chosen.update(range(number - 1, count, number))           # e: the Nth, the 2Nth ...
    return sorted(chosen)


def report_common_folder(files: list[Path]) -> Path:
    """The folder a report's chapters are laid out relative to (the first chapter's, when they
    share no folder, as on different Windows drives)."""
    try:
        return Path(os.path.commonpath([str(item.parent.resolve()) for item in files]))
    except ValueError:
        return files[0].parent.resolve()
