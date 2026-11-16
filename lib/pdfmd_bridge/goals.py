"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_bridge.goals`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import atexit
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp

from pdfmd_base import core


OFFICE_INPUT_EXTENSIONS = frozenset({
    ".docx", ".doc", ".odt", ".ott", ".rtf",
    ".pptx", ".ppt", ".odp",
    ".xlsx", ".xls", ".ods",
})


# "calibre" as a PDF engine (`-e calibre`, `pdf-engine: calibre`; never part of the automatic chain): Pandoc
# writes ONE standalone HTML file (MathML, pictures inlined) and Calibre's ebook-convert prints it. Not an EPUB:
# Pandoc splits an EPUB at every top-level heading (--split-level takes 1 to 6, no "never") and Calibre starts
# each of those files on a new page. Calibre draws MathML with its own MathJax. Its defaults suit e-books and
# are turned off for a document: font sizes rescaled to its output profile (text came out about twice the
# document's fontsize; without one, 15pt), 5pt of its own inside the page margins, a page break before every
# h1/h2 and before "Chapter"/"Section" headings, and PDF bookmarks made from the document's links; the
# bookmarks are its headings instead (the title left out).
CALIBRE_OPTIONS = ("--disable-font-rescaling", "--pdf-default-font-size", "16",   # 12pt, a browser's (WeasyPrint's)
                   "--margin-left", "0", "--margin-right", "0", "--margin-top", "0", "--margin-bottom", "0",
                   "--max-levels", "0", "--page-breaks-before", "/",
                   "--chapter", "/", "--chapter-mark", "none", "--max-toc-links", "0",
                   "--level1-toc", "//h:h1[not(contains(concat(' ', normalize-space(@class), ' '), ' title '))]",
                   "--level2-toc", "//h:h2", "--level3-toc", "//h:h3", "--pdf-page-numbers")


# Pandoc's HTML page is for a screen: a 36em column with 50px of padding (on paper the margins are the page's) and
# near-black text on an off-white page, which Calibre prints as a grey tint (it does not apply `@media print`)
CALIBRE_CSS = ("html { color-scheme: light; color: black; background-color: white; }\n"
               "body { max-width: none; margin: 0; padding: 0; background-color: transparent; }\n")


# Calibre as a WRITER (v3.29.0). `pdfmd book.md -o book.azw3` (or `--to azw3`) makes the ebook Calibre makes from the
# document: Pandoc writes an EPUB 3 into a scratch folder (chapters, contents, metadata, the math as MathML), and
# ebook-convert turns that into the target. Twelve targets only Calibre writes; five more (epub, docx, rtf, txt, fb2) Pandoc
# writes itself, so they go through Calibre only when `-e calibre` is on the command line (a `pdf-engine: calibre` is a PDF
# setting). Every one was round-tripped through ebook-convert 9.14 to text (heading, words, list and table survive). Before
# v3.29.0 `-o book.azw3` wrote a PDF under that name. One document at a time: not `-b`, not `-r`.
CALIBRE_SHARED_FORMATS = ("epub", "docx", "rtf", "txt", "fb2")


CALIBRE_TARGET_ALIASES = {"plain": "txt", "epub2": "epub", "epub3": "epub"}


# What becomes of the math (v3.29.1). The EPUB Pandoc writes has MathML, which a Kindle or a Kobo does not draw and a
# MOBI, a Palm or an RTF file has no place for: a target with pictures gets each formula drawn by LaTeX as a picture (the
# route of a Word file, `latex: images`), the plain-text ones the formulas as text with a WARN; epub and htmlz keep MathML.
CALIBRE_MATH_PICTURES = ("azw3", "mobi", "kepub", "lit", "lrf", "docx")


CALIBRE_MATH_TEXT = ("pdb", "rb", "snb", "tcr", "pmlz", "txtz", "rtf", "txt", "fb2")


EBOOK_MATH: dict = {"mode": None}            # while a Calibre job runs: "images" (see office_reference) or "text" (+ goal, why)


def ebook_filter_args() -> list[str]:
    """`--lua-filter ebook.lua` for the EPUB of a Calibre job (pdfmd_lua/ebook.lua): the pictures' titles that name this
    machine's cache are dropped; in "text" mode each formula becomes text and a WARN says so once."""
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("ebook")
    if shipped is None:
        return []
    args: list[str] = []
    if EBOOK_MATH.get("mode") == "text":
        args += ["-M", f"pdfmd-ebook={EBOOK_MATH.get('goal', 'the ebook')}", "-M", "pdfmd-ebook-math=text"]
        if EBOOK_MATH.get("why"):
            args += ["-M", f"pdfmd-ebook-why={EBOOK_MATH['why']}"]
    return args + ["--lua-filter", str(shipped)]


def math_pictures_possible() -> str | None:
    """None when LaTeX can draw formulas as pictures (a LaTeX engine and Poppler's pdftocairo), else why not."""
    module = core.office_module()
    if module is None:
        return "pdfmd_office is not installed"
    if not module.fragments.tools_available():
        return "drawing them needs pdftocairo (Poppler)"
    if not [engine for engine in core.installed_engines() if engine in ("lualatex", "xelatex", "pdflatex")]:
        return "there is no LaTeX engine (lualatex, xelatex or pdflatex)"
    return None


# LibreOffice as a writer (v3.29.1): `-o letter.doc` (Word 97, which Pandoc does not write) is made from the Word file Pandoc
# writes, by headless LibreOffice; rtf, txt and epub go the same way only with `-e soffice` first on the command line.
# OpenDocument's default Word route is selected per document in pdfmd_bridge/odt.py (DECISION 50).
SOFFICE_ONLY_FORMATS = ("doc",)


SOFFICE_SHARED_FORMATS = ("rtf", "odt", "txt", "epub")


def soffice_asked_first(requested: str | None) -> bool:
    """Whether the command line's `-e` puts LibreOffice first (`-e soffice`, `-e libreoffice`, `-e office,typst`)."""
    first = (requested or "").split(",")[0].strip().casefold()
    return bool(first) and core.ENGINE_ALIASES.get(first, first) == "soffice"


def soffice_goal(requested: str | None, target_format: str) -> str | None:
    """The format LibreOffice is to write for this target (`doc`, `rtf` ...), None when the build is not its. `doc` is always
    its; rtf, odt, txt and epub when `-e` names LibreOffice first; any other target with `-e soffice` is an error that names
    what it writes (PDF is the engine's own business)."""
    name = CALIBRE_TARGET_ALIASES.get(target_format.casefold(), target_format.casefold())
    if name in SOFFICE_ONLY_FORMATS:
        return name
    if target_format == "pdf" or not soffice_asked_first(requested):
        return None
    if name in SOFFICE_SHARED_FORMATS:
        return name
    raise SystemExit(f"-e soffice writes PDF, {', '.join(SOFFICE_SHARED_FORMATS)} and {', '.join(SOFFICE_ONLY_FORMATS)}, "
                     f"not {target_format}")


def calibre_asked_first(requested: str | None) -> bool:
    """Whether the command line's `-e` puts Calibre first (`-e calibre`, `-e ebook-convert,typst`)."""
    first = (requested or "").split(",")[0].strip().casefold()
    return bool(first) and core.ENGINE_ALIASES.get(first, first) == "calibre"


def calibre_goal(requested: str | None, target_format: str) -> str | None:
    """The format Calibre is to write for this target (`azw3`, `docx` ...), None when the build is not Calibre's. A target
    only Calibre writes is always its; one Pandoc writes too is Calibre's when `-e` names Calibre first; any other target
    with `-e calibre` is an error that names what Calibre writes."""
    name = CALIBRE_TARGET_ALIASES.get(target_format.casefold(), target_format.casefold())
    if name in core.CALIBRE_ONLY_FORMATS:
        return name
    if target_format == "pdf" or not calibre_asked_first(requested):
        return None
    if name in CALIBRE_SHARED_FORMATS:
        return name
    raise SystemExit(f"-e calibre writes PDF, {', '.join(CALIBRE_SHARED_FORMATS)} and {', '.join(core.CALIBRE_ONLY_FORMATS)}, "
                     f"not {target_format}")


def start_calibre_job(args, goal: str, target_format: str, pandoc_options: list[str] | None = None) -> dict:
    """What a Calibre target needs before the build: the checks, a scratch folder, and `args` pointed at the EPUB 3 that
    Pandoc writes there (the build then runs as for any EPUB). Returns the job for finish_calibre_job."""
    if args.batch or args.report or args.presentation:
        raise SystemExit(f"{goal} is made through Calibre one document at a time: not with "
                         f"{'-b' if args.batch else '-r' if args.report else '-p'} (yet)")
    if core.resolve_calibre() is None:
        raise SystemExit(f"{target_format} is written by Calibre's ebook-convert, which was not found (on PATH, in calibre.app "
                         "or in Calibre2 under Program Files). Install Calibre: `pdfmd --install calibre`, `brew install --cask calibre`, "
                         "`winget install calibre.calibre`, your package manager, or calibre-ebook.com.")
    if goal in CALIBRE_SHARED_FORMATS and goal != "epub":
        print(f"NOTE  -e calibre: {goal} is made by Calibre from an EPUB; without -e calibre Pandoc writes it from the "
              "document itself, with more of its own features (styles, tables, footnotes)", file=sys.stderr)
    scratch = Path(mkdtemp(prefix="pdfmd-calibre-target-"))
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    EBOOK_MATH.clear()
    EBOOK_MATH["mode"] = None
    if not any(item.startswith(core.HTML_MATH_OPTIONS) for item in pandoc_options or []):       # a math option of yours is kept
        why = core.math_pictures_possible() or "" if goal in CALIBRE_MATH_PICTURES else ""
        if goal in CALIBRE_MATH_PICTURES and not why:
            EBOOK_MATH["mode"] = "images"
        elif goal in CALIBRE_MATH_TEXT or why:
            EBOOK_MATH.update({"mode": "text", "goal": goal, "why": why})
        elif pandoc_options is not None:
            pandoc_options += core.html_math_args("mathml")       # kept as MathML (Pandoc 3.1 writes an EPUB's math as plain text)
    job = {"tool": "calibre", "goal": goal, "final": args.out, "scratch": scratch, "open": args.open}
    args.to, args.out, args.engine, args.open = "epub", scratch / "document.epub", None, False
    return job


def finish_convert_job(job: dict, results: list, verbose: bool) -> list:
    """The file: the converter (Calibre's ebook-convert of the EPUB, or LibreOffice of the Word file) run on what the build
    wrote, into the file asked for (named after the document beside it when `-o` gave none; a folder given gets that
    name in it). The result list for the closing line."""
    Built = core.Built
    source, ok, error = results[0]
    if not ok:
        return results
    final = core.load_package("pdfmd_routing.output").job_target(job["final"], Path(source), job["goal"])
    tool = job.get("tool", "calibre")
    if tool == "soffice":
        worked, why = core.run_soffice_convert(job["scratch"] / job["intermediate"], final, verbose, job["goal"])
        if not worked:
            return [Built((source, False, f"soffice failed: {why}"), "soffice")]
    else:
        done = core.run_calibre_convert(job["scratch"] / "document.epub", final, verbose)
        if done.returncode != 0:
            return [Built((source, False, done.stderr), "calibre")]
    if job["open"]:
        core.open_file(final)
    return [Built((source, True, error), tool, output=final)]          # what Pandoc and its filters said stays
