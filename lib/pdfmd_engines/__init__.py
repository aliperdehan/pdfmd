"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_engines`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import pdfmd_install
import re
import sys
from pathlib import Path

from pdfmd_base import core


# Engines are tried in this order only when the user did not request one.
# An explicit --engine is never overridden.
PDF_ENGINES = (
    "lualatex", "xelatex", "pdflatex", "latexmk", "tectonic", "typst",
    "weasyprint", "wkhtmltopdf", "pagedjs-cli", "prince", "context",
    "groff", "pdfroff", "soffice",
)


ENGINE_ALIASES = {
    "1": "lualatex", "lua": "lualatex",
    "2": "xelatex", "xe": "xelatex",
    "3": "pdflatex", "pdf": "pdflatex",
    "4": "latexmk", "mk": "latexmk",
    "5": "tectonic", "tect": "tectonic",
    "6": "typst",
    "7": "weasyprint", "weasy": "weasyprint",
    "8": "wkhtmltopdf", "wkhtml": "wkhtmltopdf",
    "9": "pagedjs-cli", "pagedjs": "pagedjs-cli",
    "10": "prince",
    "11": "context",
    "12": "groff",
    "13": "pdfroff", "roff": "pdfroff",
    "14": "soffice", "libreoffice": "soffice", "office": "soffice",
    "ebook-convert": "calibre",
    "google-chrome": "chrome", "msedge": "edge", "microsoft-edge": "edge", "brave-browser": "brave",
}


# Engines with no number of their own (-e calibre, pdf-engine: calibre; v3.29.1: the browsers too): last resorts of the
# automatic chain (automatic_engines), not part of the numbered one above, and with no number of their own (the numbers are PDF_ENGINES' order in --check-dependencies).
EXPLICIT_ENGINES = ("calibre",)


# A browser prints a Markdown document too (v3.29.1; `-e edge`, `-e chrome`, `-e chromium`, `-e brave`, or the family word
# `-e browser`): Pandoc writes one self-contained HTML page (MathML, which a browser draws itself) and the browser, headless,
# prints it with the page the document asks for. Only when named, like Calibre; `.html` files already went to a browser
# first when they have scripts or MathML (pdfmd_direct).
BROWSER_ENGINES = ("chrome", "chromium", "edge", "brave")


LATEX_ENGINES = frozenset({"lualatex", "xelatex", "pdflatex", "latexmk", "tectonic", "context"})


PREAMBLE_FILENAMES = ("preamble.tex", "latex-preamble.tex")


# Pandoc *writer* names (as opposed to LATEX_ENGINES' *engine* names --
# "context" unavoidably appears in both, since it is both) that need a real
# LaTeX preamble (\documentclass, font/geometry setup, a project's own
# preamble.tex) to be a complete, independently compilable document rather
# than a bare Pandoc-LaTeX fragment. Drives the --standalone default and the
# preamble/header-includes/font/margin auto-discovery for --to (or an -o
# file with one of FORMAT_EXTENSION's matching extensions) targeting one of
# these, mirroring what happens on the way to a PDF through the same writer.
TEX_STANDALONE_FORMATS = frozenset({"latex", "beamer", "context"})


# Engines that share the same underlying TeX engine, grouped by family. If one
# member of a family fails, the others are very unlikely to succeed on the
# same document (they see the same fonts, the same package errors, the same
# Unicode input) so the fallback loop skips straight to a genuinely different
# backend instead of wasting a retry. xelatex/tectonic share XeTeX;
# lualatex/context (MkIV) share LuaTeX; pdflatex/latexmk share pdfTeX --
# latexmk's own default engine, though a local .latexmkrc can change that.
# Anything not listed here is assumed to be its own independent family.
ENGINE_FAMILY = {
    "pdflatex": "pdftex",
    "latexmk": "pdftex",
    "lualatex": "luatex",
    "context": "luatex",
    "xelatex": "xetex",
    "tectonic": "xetex",
}


# Coarse rendering-paradigm groups -- distinct from ENGINE_FAMILY above, which
# groups by underlying TeX implementation for skip-after-failure purposes
# *within* one paradigm. These scope which engines are even eligible
# candidates in the first place, so e.g. a chemfig/nulabreport document that
# requests the "tex" family never falls back to an HTML engine that cannot
# render its LaTeX macros at all, and a plain document that requests "html"
# never pays for a slow LaTeX run it doesn't need. "tex" is defined as
# exactly the members of LATEX_ENGINES, in PDF_ENGINES order, so the two
# can't drift apart. Selected via -e/--engine or a pdf-engine front-matter
# key, same as a single engine name -- see select_engines().
ENGINE_GROUPS: dict[str, tuple[str, ...]] = {
    "tex": tuple(engine for engine in PDF_ENGINES if engine in LATEX_ENGINES),
    "html": ("weasyprint", "wkhtmltopdf", "pagedjs-cli", "prince"),
    "typst": ("typst",),
    "office": ("soffice",),
    "browser": BROWSER_ENGINES,
}


def installed_engines() -> list[str]:
    """Return PDF engines that are currently executable, in fallback order."""
    return [engine for engine in PDF_ENGINES if core.engine_executable(engine)]


def automatic_engines() -> list[str]:
    """The chain of a build that names no engine (v3.29.1): the installed numbered engines in their order, and where those
    all failed or are missing, the browsers (headless Chrome, Chromium, Edge, Brave) and Calibre, ahead of LibreOffice, whose
    page is the least like the document's. They are last resorts: LaTeX, Typst and WeasyPrint still go first. `-e pandoc`
    is every engine Pandoc drives and never these (a list of your own names them)."""
    engines = core.installed_engines()
    extras = [engine for engine in (*BROWSER_ENGINES, "calibre") if core.engine_executable(engine)]
    if "soffice" in engines:
        position = engines.index("soffice")
        return [*engines[:position], *extras, *engines[position:]]
    return [*engines, *extras]


def select_engines(requested: str | None, presentation: bool, label: str = "--engine") -> list[str]:
    """Select installed engines in fallback order, or explain what is missing.

    ``requested`` may be a single engine name/alias (as before), or one of
    ENGINE_GROUPS's family keywords ("tex", "html", "typst"), which restricts
    automatic fallback to that family's installed members in PDF_ENGINES
    order, instead of picking one specific engine or falling back through
    every installed engine regardless of paradigm.

    ``label`` only shapes the incompatibility/not-installed messages below
    (the single-engine not-found error is already source-agnostic) -- it
    lets a front-matter-sourced request name itself instead of claiming to
    be a CLI flag it never was.
    """
    if requested and "," in requested:
        return engine_chain(requested, presentation, label)
    if requested and not re.search(r"[\\/]", requested) and requested.casefold().endswith(".exe"):
        requested = requested[:-4]          # `-e lualatex.exe`: the name Windows shows for the engine
    if requested and requested.casefold() == "pandoc":
        candidates = core.installed_engines() if core.which("pandoc") else []
        if presentation:
            candidates = [engine for engine in candidates if engine in LATEX_ENGINES]
        if not candidates:
            raise SystemExit(f"{label} named pandoc (every engine Pandoc drives), but none is installed. "
                             "Run --check-dependencies for a status report.")
        return candidates
    if requested:
        native = core.native_request(requested, presentation, label)
        if native is not None:
            return native
        if not core.which("pandoc"):
            raise SystemExit(core.PANDOC_MISSING)
        group = ENGINE_GROUPS.get(requested.casefold())
        if group is not None:
            family = requested.casefold()
            installed_in_group = [engine for engine in group if core.engine_executable(engine)]
            too_old = pdfmd_install.typst_too_old() if "typst" in installed_in_group else None
            if too_old:                                # too old counts as missing (v3.33.62)
                installed_in_group.remove("typst")
                if not installed_in_group:
                    raise SystemExit(too_old)
            if not installed_in_group:
                raise SystemExit(
                    f"{label} restricted to the '{family}' engine family, but none of "
                    + ", ".join(group) + " is installed on PATH. Install one, or pass a bare "
                    "-e for the full, unrestricted fallback chain."
                )
            if presentation:
                candidates = [engine for engine in installed_in_group if engine in LATEX_ENGINES]
                if not candidates:
                    raise SystemExit(
                        f"{label} restricted to the '{family}' engine family, which cannot "
                        "render Beamer slides (-p/--presentation): Pandoc's Beamer writer "
                        "requires a LaTeX/ConTeXt engine, one of "
                        + ", ".join(sorted(LATEX_ENGINES))
                    )
                return candidates
            return installed_in_group

        requested = ENGINE_ALIASES.get(requested.casefold(), requested)
        if presentation and requested not in LATEX_ENGINES:
            raise SystemExit(
                f"{label} requested {requested}, which cannot render Beamer slides "
                "(-p/--presentation): Pandoc's Beamer writer requires a LaTeX/ConTeXt "
                "engine, one of " + ", ".join(sorted(LATEX_ENGINES))
            )
        if core.engine_executable(requested):
            if requested == "typst" and pdfmd_install.typst_too_old():
                raise SystemExit(pdfmd_install.typst_too_old())
            return [requested]
        if requested == "calibre":
            raise SystemExit(f"{label} requested Calibre, but its ebook-convert was not found (on PATH, in "
                             "calibre.app or in Calibre2 under Program Files). Install Calibre: `pdfmd --install calibre`, "
                             "`brew install --cask calibre`, `winget install calibre.calibre`, your package manager, or "
                             "calibre-ebook.com.")
        raise SystemExit(
            f"Requested PDF engine '{requested}' was not found on PATH. "
            "Install it or choose one listed by --check-dependencies."
        )

    candidates = automatic_engines() if core.which("pandoc") else []
    if presentation:
        # Pandoc's Beamer writer requires a TeX-family engine.
        candidates = [engine for engine in candidates if engine in LATEX_ENGINES]
    if candidates:
        return candidates
    if not presentation and core.available_native_engines():
        # No Pandoc route at all: the native tier (see the section below
        # dependency_report). Never reached while any Pandoc engine exists.
        return core.available_native_engines()

    kind = "a LaTeX/ConTeXt engine for Beamer" if presentation else "a PDF engine"
    raise SystemExit(
        f"No supported {kind} was found. Install Pandoc and one of: "
        + ", ".join(PDF_ENGINES)
        + ". Run --check-dependencies for a status report."
    )


def engine_chain(requested: str, presentation: bool, label: str) -> list[str]:
    """``-e typst,calibre,lualatex`` (v3.28.42): the engines to try, in the order written. A word is an engine, an alias,
    a family (tex, html, typst: its installed members in their usual order) or `pandoc` (every engine Pandoc drives).
    Named means named: nothing outside the list is tried. A word whose engine is not installed is passed over with a
    note when another one of the list is; the build stops only when none is."""
    chain: list[str] = []
    missing: list[str] = []
    for word in (item.strip() for item in requested.split(",")):
        if not word:
            continue
        try:
            found = select_engines(word, presentation, label)
        except SystemExit as error:
            missing.append(f"{word}: {str(error).splitlines()[0]}")
            continue
        chain += [engine for engine in found if engine not in chain]
    if not chain:
        raise SystemExit(f"{label} names {requested}, and none of it can run:\n  " + "\n  ".join(missing))
    for line in missing:
        print(f"NOTE  {label}: {line}; the next in the list is tried", file=sys.stderr)
    return chain


def resolve_engines(md_path: Path, cli_engine: str | None, engines: list[str],
                    presentation: bool, target_format: str,
                    metadata_files: list[Path] = (), verbose: bool = False) -> list[str]:
    """Fall back to a document's own pdf-engine/engine setting, or its
    linked metadata file's.

    Only consulted when -e/--engine was not given AT ALL on the CLI
    (cli_engine is None). A *bare* -e (cli_engine == "", from nargs="?" with
    const="") is itself an explicit request for the full, unrestricted
    fallback chain -- checked with ``is not None`` rather than truthiness so
    it is never confused with "flag absent," and it overrides a front-matter
    engine/family restriction the same way a specific -e value already does
    (both go through the top-level ``engines`` this function is handed,
    already computed by select_engines(args.engine, ...) in main()). Also
    skipped whenever the target isn't PDF (no engine is involved).

    ``metadata_files`` (a document's already-resolved --metadata-file list,
    from find_metadata -- empty unless the caller already has it) lets
    frontmatter_engine fall through to a course-wide default there when the
    document's own front matter sets none; see its docstring.

    The resolved chain is only ever printed under ``--verbose`` -- same
    convention as every other "AUTO ..." discovery note (see convert_one's
    own note()/flush_summary()) -- as a plain ``ENGINE`` line, not
    ``AUTO ENGINE``: this one restriction can come from either the document
    or its metadata file, so "AUTO" would misattribute a document-level
    setting as auto-discovered when it's an explicit request.
    """
    if cli_engine is not None or target_format != "pdf":
        return engines
    requested = frontmatter_engine(md_path, metadata_files)
    if not requested:
        return engines
    resolved = select_engines(requested, presentation,
                              label=f"pdf-engine setting for {md_path.name}")
    core.vprint(verbose, f"ENGINE  {md_path}: " + " -> ".join(resolved))
    return resolved


def dependency_report() -> bool:
    """Print executable availability and return whether conversion can run."""
    pandoc = core.which("pandoc")
    print(f"{'OK  ' if pandoc else 'MISS'}  pandoc" + (f"  ({pandoc})" if pandoc else ""))
    for number, engine in enumerate(PDF_ENGINES, start=1):
        path = core.engine_executable(engine)
        print(f"{'OK  ' if path else 'MISS'}  {number}. {engine}" + (f"  ({path})" if path else ""))
    for engine in EXPLICIT_ENGINES:
        path = core.engine_executable(engine)
        print(f"{'OK  ' if path else 'MISS'}  {engine} (only when named: -e {engine})" + (f"  ({path})" if path else ""))
    quarto = core.which("quarto")
    print(f"{'OK  ' if quarto else 'MISS'}  quarto (only needed for .qmd files)"
         + (f"  ({quarto})" if quarto else ""))
    if core.which("weasyprint"):
        jax = core.mathjax_runtime()
        print(f"{'OK  ' if jax else 'MISS'}  MathJax (math in WeasyPrint's PDFs"
              + (f": {jax[1].name}, fonts {', '.join(core.mathjax_fonts(jax[1]))}, node {jax[0]})" if jax
                 else "; pdfmd --install math:mathjax)"))
        runtime = core.katex_runtime()
        print(f"{'OK  ' if runtime else 'MISS'}  KaTeX (math in WeasyPrint's PDFs"
              + (f": {runtime[1].name}, node {runtime[0]})" if runtime else "; pdfmd --install math:katex)"))
    print("Native renderers (no Pandoc needed; plainer output, Markdown only):")
    print(f"{'OK  ' if core.inkmd_vendored() else 'MISS'}  inkmd  (built in; no math, footnotes become endnotes)")
    if sys.version_info < (3, 11):
        print("MISS  md2pdf  (needs Python 3.11 or newer)")
    else:
        print(f"{'OK  ' if core.md2pdf_available() else 'MISS'}  md2pdf  (footnotes, bookmarks, math"
              + ("" if core.md2pdf_available() else "; pdfmd --install math") + ")")
    print(f"{'OK  ' if core.matplotlib_available() else 'MISS'}  matplotlib  (offline math in md2pdf"
          + ("" if core.matplotlib_available() else "; pdfmd --install math") + ")")
    font = core.inkmd_emoji_font()
    print(f"{'OK  ' if font else 'MISS'}  colour emoji font for inkmd"
          + (f"  ({font})" if font else "  (pdfmd --install emoji)"))
    print("Smaller PDFs (lossless, the first one installed shrinks every PDF; see --shrink):")
    for row in core.load_package("pdfmd_shrink").check_rows():
        print(row)
    print("Reading PDFs (PDF to Markdown, through batchocr):")
    BATCHOCR_MIN = core.BATCHOCR_MIN
    reader = core.find_batchocr()
    reader_version = core.batchocr_version(reader) if reader else None
    print(f"{'OK  ' if reader_version and reader_version >= BATCHOCR_MIN else 'MISS'}  batchocr"
          + (f"  ({'.'.join(map(str, reader_version))})" if reader_version else "  (pdfmd --install batchocr)"))
    for tool in ("tesseract", "pdftotext", "pdftoppm"):
        path = core.which(tool)
        print(f"{'OK  ' if path else 'MISS'}  {tool}" + (f"  ({path})" if path else f"  ({core.tesseract_install_hint()})"))
    pandoc_route = bool(pandoc and core.installed_engines())
    managed = core.managed_tool_directories()
    if managed:
        print("Installed by pdfmd (used when nothing else is on PATH): "
              + ", ".join(str(folder) for folder in managed))
    if pandoc_route:
        print("Mode: Pandoc and PDF engines (the native renderers are used only on request: -e inkmd / -e md2pdf).")
    elif core.available_native_engines():
        why = "Pandoc is installed but no PDF engine is" if pandoc else "no Pandoc"
        print(f"Mode: native only -- {why}; plain Markdown-to-PDF still works. "
              f"For the full pipeline install Pandoc and Typst: {core.pandoc_install_hint()}")
    return pandoc_route or bool(core.available_native_engines())


def frontmatter_engine(md_path: Path, metadata_files: list[Path] = ()) -> str | None:
    """Read the effective default PDF engine: the document's own front
    matter first, then each linked --metadata-file's own (the later file first, see
    metadata_files_by_priority)
    ``pdf-engine``/``pdfmd-options`` as a course-wide default the document
    can still override. This is what lets nulabreport's shared
    metadata.yaml -- symlinked into every course folder -- set
    ``pdfmd-options: {pdf-engine: tex}`` once for every report that finds
    it, instead of repeating the block in each report's own front matter.

    ``pdf-engine`` mirrors Pandoc's own ``--pdf-engine`` flag name; ``engine``
    is accepted as a shorter alias. A single engine name/alias/numeric
    shortcut, or an ENGINE_GROUPS family keyword ("tex", "html", "typst") to
    restrict fallback to that paradigm -- same values -e/--engine accepts.

    Unlike documentclass/class or header-includes, ``pdf-engine``/``engine``
    mean nothing to Pandoc itself -- they're entirely pdfmd's own invention
    -- so this checks the nested ``pdfmd-options:`` spelling first (where a
    new document should put pdfmd-only settings) and falls back to the
    older bare top-level key for documents already written with that
    spelling, which keeps working unchanged. A metadata file gets the same
    nested-then-bare check, in metadata_files_by_priority's order (v3.27.22; it
    was find_metadata's own order, so the first file won); this deliberately does NOT extend to `no-auto` -- no-auto
    decides whether metadata auto-discovery runs at all, so it cannot also
    depend on the metadata file that discovery itself would find.
    """
    def words(value) -> str:
        return ",".join(str(item) for item in value) if isinstance(value, (list, tuple)) else str(value)

    options = core.frontmatter_pdfmd_options(md_path)
    value = options.get("pdf-engine") or options.get("engine")
    if value is not None:
        return words(value)
    own = core.load_package("pdfmd_args.options").legacy_engine(md_path, options)
    if own is not None:
        return own.strip("[]")
    for metadata_file in core.metadata_files_by_priority(metadata_files):
        data = core.metadata_file_yaml(metadata_file)
        options = data.get("pdfmd-options")
        value = (options.get("pdf-engine") or options.get("engine")) if isinstance(options, dict) else None
        if value is None:
            top = core.load_package("pdfmd_args.options").legacy_engine(data, options or {})
            value = words(top) if top is not None else None
        if value is not None:
            return words(value)
    configured = core.config_options(md_path)
    value = configured.get("pdf-engine") or configured.get("engine")
    return words(value) if value is not None else None
