"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_filters`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from pdfmd_base import core


CODE_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(?![`~])[ \t]*(.*)$")          # indented too: in a list item


INDENTED_CODE_RE = re.compile(r"^(?: {4}|\t)\S")


LIST_CONTEXT_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)]|#\.|[A-Za-z][.)])\s|^(?: {2,}|\t)")


def has_code_block(text: str) -> bool:
    """Whether Pandoc would see a code block in ``text``: a fenced block that is not a raw ``{=latex}`` one, or an
    indented one after a blank line that does not go on with a list item. The front matter is not looked at: its
    indented YAML (a `references:` list) is not code (v3.27.21; it gave five proposals with no code the code header)."""
    _, body = core.split_front_matter(text)
    fence = None                                     # the fence of the raw block we are in
    blank, context = True, ""                        # whether the last line was blank; the last line that was not
    for line in body.splitlines():
        if fence:
            if re.match(r"^[ \t]*%s{%d,}[ \t]*$" % (re.escape(fence[0]), len(fence)), line):
                fence = None
            continue
        match = CODE_FENCE_RE.match(line)
        if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):     # ```x``` is inline code
            if not match.group(2).strip().startswith("{="):
                return True
            fence = match.group(1)
            continue
        if INDENTED_CODE_RE.match(line) and blank and not LIST_CONTEXT_RE.match(context):
            return True
        blank = not line.strip()
        if not blank:
            context = line
    return False


def code_filter_args(no_auto: list[str] | None, sources: list[Path], metadata_files=()) -> list[str]:
    """What a LaTeX build needs for code blocks (pdfmd_lua/code.lua; wrapping and optional line numbers): the filter
    and, when the document has code and wrapping is not off, the header that loads fvextra. The settings of the
    command line and the global config reach the filter as metadata; a document's own `pdfmd-options` through the
    document. Nothing for `--no-auto codewrap`, a document without code, or a lone pdfmd.py."""
    if core.auto_disabled(no_auto, "codewrap"):
        return []
    try:
        import pdfmd_lua
        shipped, header = pdfmd_lua.path("code"), pdfmd_lua.FILTERS / "code_wrap.tex"
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    if shipped is None or not any(has_code_block(core.read_text_best_effort(source)) for source in sources):
        return []
    settings = {}
    for key in ("code-wrap", "line-numbers", "line-number-step"):
        for where in (core.CODE_CLI, *(options for _, options in core.option_sources(sources[0], metadata_files))):
            if where.get(key) is not None:
                settings[key] = where[key]
                break
    args = ["--lua-filter", str(shipped)]
    for key, value in settings.items():
        args += ["-M", f"pdfmd-{key}={str(value).lower() if isinstance(value, bool) else value}"]
    if str(settings.get("code-wrap", True)).lower() != "false" and header.is_file():
        args += ["--include-in-header", str(header), "-M", "pdfmd-code-header=1"]
    return args


def image_dpi_for(source: Path, metadata_files=(), default=192):
    """Reuse image-dpi for embedded raster SVGs (legacy diagrams: 192; exported pages: 300)."""
    value = core.IMAGE_DPI_CLI
    if value is None:
        value = (core.first_pdfmd_option(source, metadata_files, "image-dpi") if source.suffix.lower() in (".md", ".markdown")
                 else core.config_options().get("image-dpi"))
    if value is None:
        return default
    try:
        dpi = float(value)
        if 0 < dpi < float("inf"):
            return dpi
    except (TypeError, ValueError):
        pass
    print(f"WARN  image-dpi must be a number above 0; using {default}", file=sys.stderr)
    return default


SVG_WARNED: set[str] = set()


def image_filter_args(no_auto: list[str] | None, sources: list[Path], metadata_files=(), *, format="pdf") -> list[str]:
    """What a LaTeX/Word build needs for SVG images (pdfmd_images; pdfmd_lua/images.lua): each SVG the
    documents name is converted once to a PDF (kept by content in the cache) and the filter puts the PDF where the
    document wrote the SVG, in a raw `\\includegraphics{a.svg}` or `\\includesvg{a}` and in a Markdown image when Pandoc
    has no rsvg-convert to do it itself. Word requests PNG; resvg returns PNG for either target.
    A raw `\\includegraphics` also gets graphicx, which Pandoc only loads for a
    Markdown image. Nothing for `--no-auto svg`, a document without such images, or a lone pdfmd.py."""
    if core.auto_disabled(no_auto, "svg"):
        return []
    try:
        import pdfmd_images
        import pdfmd_lua
        shipped, graphicx = pdfmd_lua.path("images"), pdfmd_lua.FILTERS / "graphicx.tex"
    except ImportError:
        return []
    if shipped is None:
        return []
    pandoc_converts = bool(core.which("rsvg-convert"))
    fetch_remote = not core.auto_disabled(no_auto, "remoteimages")
    offline = False
    mapping: dict[str, str] = {}
    raw_graphics = False

    def convert(file: Path, source: Path, written: str) -> str | None:
        pdf, why = pdfmd_images.convert_svg(file, core.cache_root() / "images", core.which, core.resolve_soffice, core.run_soffice,
                                          format=format, dpi=image_dpi_for(source, metadata_files), fonts=core.fonts_directory())
        if pdf is None and str(file) not in SVG_WARNED:
            SVG_WARNED.add(str(file))
            reason = "LaTeX cannot read it" if format == "pdf" else "could not be converted to PNG"
            print(f"WARN  {core.display_path(source)}: {written} is an SVG and {reason}; {why}", file=sys.stderr)
        return str(pdf) if pdf is not None else None

    for source in sources:
        for reference in pdfmd_images.find_references(core.read_text_best_effort(source)):
            if format == "png" and reference.kind != "markdown":
                continue
            raw_graphics = raw_graphics or reference.kind != "markdown"
            if reference.path in mapping:
                continue
            if reference.remote:
                if not (fetch_remote and reference.kind == "markdown" and reference.path.lower().startswith(("http://", "https://"))) \
                        or offline:
                    continue
                local, why, down = pdfmd_images.fetch_remote(reference.path, core.cache_root() / "images" / "remote")
                if local is None:
                    if down:
                        offline = True
                        print(f"WARN  {core.display_path(source)}: no network, so remote images ({reference.path} and the "
                              "others) cannot be fetched; Pandoc will leave their descriptions instead", file=sys.stderr)
                    elif reference.path not in SVG_WARNED:
                        SVG_WARNED.add(reference.path)
                        print(f"WARN  {core.display_path(source)}: {reference.path} could not be fetched ({why})", file=sys.stderr)
                    continue
                if local.suffix == ".svg":
                    converted = convert(local, source, reference.path)
                    if converted:
                        mapping[reference.path] = converted
                else:
                    mapping[reference.path] = str(local)
                continue
            if not reference.is_svg or (reference.kind == "markdown" and pandoc_converts):
                continue
            written = reference.path if reference.path.lower().endswith(".svg") else reference.path + ".svg"
            file = source.parent / urllib.parse.unquote(written)
            if not file.is_file():
                continue
            converted = convert(file, source, reference.path)
            if converted:
                mapping[reference.path] = converted
    args: list[str] = []
    if mapping:
        mapping = {name: Path(path).as_posix() for name, path in mapping.items()}      # LaTeX reads a backslash as a command
        digest = hashlib.sha1(json.dumps(mapping, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        map_file = core.cache_root() / "images" / "maps" / f"{digest}.yaml"
        if not map_file.is_file():
            map_file.parent.mkdir(parents=True, exist_ok=True)
            map_file.write_text("pdfmd-image-map: " + json.dumps(mapping, ensure_ascii=False) + "\n", encoding="utf-8")
        args += ["--lua-filter", str(shipped), "--metadata-file", str(map_file)]
    if raw_graphics and graphicx.is_file():
        args += ["--include-in-header", str(graphicx)]
    return args


PDF_IMAGE_RE = re.compile(r"""!\[[^\]]*\]\([^)\s]*\.pdf(?:[?#][^)\s]*)?(?:\s+(?:"[^"]*"|'[^']*'))?\)|<img\b[^>]*\bsrc\s*=\s*["'][^"']*\.pdf[?#"']""",
                          re.IGNORECASE)


def resolve_raw(md_path: Path, metadata_files: list[Path], flat: bool = False) -> dict[str, list[str]] | None:
    """The raw-syntax table of this build (see pdfmd_raw), or None: `--no-raw`, else the command line, else the
    document's `pdfmd-options.raw`. A flat Markdown build (`--to gfm`) takes every syntax unless `raw: {md: ...}` says
    otherwise: the pieces are carried over, since the output has no HTML or LaTeX of its own to keep them in."""
    if core.RAW_CLI["off"]:
        return None
    try:
        import pdfmd_raw
        table = pdfmd_raw.parse(True if core.RAW_CLI["all"] else core.first_pdfmd_option(md_path, metadata_files, "raw"))
        for spec in core.RAW_CLI["for"]:
            family, _, listing = spec.partition("=")
            table = pdfmd_raw.merge(table, family, pdfmd_raw.syntaxes(listing))
        if flat:
            table = {**(table or {})}
            table.setdefault("md", list(pdfmd_raw.SYNTAXES))
    except ImportError:
        return None
    except ValueError as error:
        print(f"WARN  raw: {error}; the raw option was ignored", file=sys.stderr)
        return None
    return table


# Page breaks carried into every format (v3.27.15, off unless asked; 3.27.13 had it on): the spelling families
# pdfmd_lua/pagebreak.lua makes every output's own. `pdfmd-options.pagebreak` (document, metadata files, config:
# true / all, false, or a list of families), `--pagebreak [KIND ...]` (bare: all) and `--no-pagebreak` for a run.
PAGEBREAK_KINDS = ("comment", "tex", "html", "div", "typst", "word")


def pagebreak_value(value) -> list[str]:
    """The families a `pagebreak` value names, in PAGEBREAK_KINDS order: true or `all` every one, false none, a list
    (or a comma-separated string) those."""
    if value is None or value is False:
        return []
    if value is True:
        return list(PAGEBREAK_KINDS)
    items = value if isinstance(value, list) else str(value).replace(",", " ").split()
    words = [str(item).strip().casefold() for item in items if str(item).strip()]
    if any(word in ("all", "true", "yes", "on") for word in words):
        return list(PAGEBREAK_KINDS)
    unknown = [word for word in words if word not in PAGEBREAK_KINDS and word not in ("false", "no", "off", "none")]
    if unknown:
        print(f"WARN  pagebreak: {', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not a page-break family "
              f"({', '.join(PAGEBREAK_KINDS)}, or all)", file=sys.stderr)
    return [kind for kind in PAGEBREAK_KINDS if kind in words]


def pagebreak_kinds(md_path: Path, metadata_files: list[Path]) -> list[str]:
    """The page-break families this build carries into every format: the command line's, else pdfmd-options'."""
    if core.PAGEBREAK_CLI["off"]:
        return []
    if core.PAGEBREAK_CLI["kinds"] is not None:
        return pagebreak_value(core.PAGEBREAK_CLI["kinds"] or True)
    value = core.first_pdfmd_option(md_path, metadata_files, "pagebreak")
    return pagebreak_value(core.flavour_default(md_path, metadata_files, "pagebreak") if value is None else value)


# Speaker notes in a Beamer deck (v3.32.2): `::: notes` blocks are dropped from the PDF unless Beamer is asked to show them.
# `pdfmd-options: {slide-notes: off | show | only}`: `show` puts each slide's notes on a page after it, `only` makes the PDF
# the notes pages alone. It is a header, not `-V classoption=notes=...`: that variable replaces the deck's own `classoption`
# (an `aspectratio=169` was lost, measured on 3.32.0).
SLIDE_NOTES_HEADERS = {"show": "\\setbeameroption{show notes}\n", "only": "\\setbeameroption{show only notes}\n"}


def slide_notes_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """The `slide-notes` option as off, show or only (a bad word stops the build, like `md-macro`)."""
    value = core.first_pdfmd_option(md_path, metadata_files, "slide-notes")
    if value is None or value is False:
        return "off"
    word = str(value).strip().casefold()
    if word in ("", "off", "no", "false", "0", "none"):
        return "off"
    if word in ("show", "only"):
        return word
    if value is True or word in ("on", "yes", "true", "1"):
        return "show"
    raise SystemExit(f"pdfmd-options slide-notes: {value!r} is not one of off, show, only")


def slide_notes_args(sources: Path | list[Path], metadata_files: list[Path], beamer: bool) -> list[str]:
    """`--include-in-header` that makes a Beamer deck show its speaker notes (`slide-notes`), or []: other builds ignore the setting."""
    files = sources if isinstance(sources, list) else [sources]
    if not beamer or not files:
        return []
    mode = slide_notes_mode(files[0], metadata_files)
    if mode == "off":
        return []
    text = "% pdfmd: speaker notes in the deck (pdfmd-options slide-notes)\n" + SLIDE_NOTES_HEADERS[mode]
    header = core.cache_root() / "tex" / f"slide-notes-{mode}.tex"
    try:
        if not header.is_file() or header.read_text(encoding="utf-8") != text:
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(header)]


def cover_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """`pdfmd-options: {cover: true | PICTURE}` (v3.29.9) as pdfmd_lua/cover.lua and its metadata, or []: `true` is the title
    block on a page of its own, a picture (relative to the document) is the first page, or the cover of an EPUB."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []
    value = core.first_pdfmd_option(files[0], metadata_files, "cover")
    if value is None or value is False or str(value).strip().casefold() in ("", "false", "no", "off", "0", "none"):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("cover")
    if shipped is None:
        return []
    args = ["--lua-filter", str(shipped)]
    if value is True or str(value).strip().casefold() in ("true", "yes", "on", "1", "title"):
        metadata = core.effective_metadata(files[0], metadata_files, [])
        klass = str(metadata.get("documentclass") or "article").strip()
        args = ["-M", "pdfmd-cover=title", "-M", "pdfmd-cover-latex=" + ("1" if klass in ("article", "report", "book", "scrartcl", "scrreprt", "scrbook") else "0"), *args]
        return args
    picture = (files[0].parent / str(value).strip()).resolve()
    if not picture.is_file():
        print(f"WARN  {core.display_path(files[0])}: cover: {value} was not found beside the document; no cover is made", file=sys.stderr)
        return []
    return ["-M", "pdfmd-cover=image", "-M", f"pdfmd-cover-image={picture}", *args]


def cover_header_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """`--include-in-header` for a LaTeX build's picture cover (`cover: picture.png`): the picture on the first page, before
    \\maketitle. A header file of pdfmd's own, last, like the packages: a filter's `header-includes` would be dropped by
    every other one of pdfmd's (the code header, the packages, a house preamble), which only a document's own survive."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []
    value = core.first_pdfmd_option(files[0], metadata_files, "cover")
    if value is None or value is True or str(value).strip().casefold() in (
            "", "false", "no", "off", "0", "none", "true", "yes", "on", "1", "title"):
        return []
    picture = (files[0].parent / str(value).strip()).resolve()
    if not picture.is_file():
        return []                      # cover_filter_args says so
    path_text = picture.as_posix()
    text = ("% pdfmd: the cover picture (pdfmd-options: cover)\n\\usepackage{graphicx}\n\\AtBeginDocument{\\thispagestyle{empty}"
            "\\noindent\\includegraphics[width=\\linewidth,height=\\textheight,keepaspectratio]{" + path_text + "}\\clearpage}\n")
    header = core.cache_root() / "tex" / f"packages-cover-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not header.is_file():
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(header)]


def pagebreak_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter pagebreak.lua`` with the families it takes part in (`-M pdfmd-pagebreak=comment,tex`), when any:
    each such spelling of a page break becomes the target format's own. Before raw.lua, which would otherwise draw or
    drop a raw TeX `\\newpage`."""
    files = sources if isinstance(sources, list) else [sources]
    kinds = pagebreak_kinds(files[0], metadata_files) if files else []
    if not kinds:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("pagebreak")
    return ["-M", "pdfmd-pagebreak=" + ",".join(kinds), "--lua-filter", str(shipped)] if shipped is not None else []


# One line break for every writer (v3.31.49, entry 3el; the idea of pagebreak.lua): each writer takes its own spelling of a line
# break and drops the others ("one<br>two" printed "onetwo" in LaTeX), and a table cell cannot hold a `\\par`.
# pdfmd_lua/linebreak.lua reads the spellings of a family and gives the target its own (one already in its language stays as
# written). Families: html (`<br>`, `<br/>`, `<br />`), tex (a raw `\newline`, `\linebreak`), typst (`#linebreak()`), word (a raw
# break run), context (`\crlf`). Like pagebreak, with a different default: `pdfmd-options.linebreak` (document, metadata files,
# config) is `auto` when not set (every family, inside table cells only), `true` / `all` (every family, everywhere), a list of
# families (those, everywhere) or `false`; `--linebreak [KIND ...]` (bare: all) and `--no-linebreak` for a run.
LINEBREAK_KINDS = ("html", "tex", "typst", "word", "context")


LINEBREAK_RE = re.compile(r"<br\s*/?>|\\(?:newline|linebreak|crlf)|#linebreak\(\)|<w:br\s*/>", re.IGNORECASE)


def linebreak_value(value) -> tuple[str, list[str]]:
    """What a `linebreak` value asks for, as (where, families): where is `cells` or `all`, families in LINEBREAK_KINDS order.
    Not set or `auto`: every family in table cells; true or `all`: every family everywhere; false: none; a list (or a
    comma-separated string): those families, everywhere."""
    if value is None:
        return "cells", list(LINEBREAK_KINDS)
    if value is False:
        return "cells", []
    if value is True:
        return "all", list(LINEBREAK_KINDS)
    items = value if isinstance(value, list) else str(value).replace(",", " ").split()
    words = [str(item).strip().casefold() for item in items if str(item).strip()]
    if not words or words == ["auto"]:
        return "cells", list(LINEBREAK_KINDS)
    if any(word in ("all", "true", "yes", "on") for word in words):
        return "all", list(LINEBREAK_KINDS)
    unknown = [word for word in words if word not in LINEBREAK_KINDS and word not in ("auto", "false", "no", "off", "none")]
    if unknown:
        print(f"WARN  linebreak: {', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not a line-break family "
              f"({', '.join(LINEBREAK_KINDS)}, all, or auto)", file=sys.stderr)
    return "all", [kind for kind in LINEBREAK_KINDS if kind in words]


def linebreak_settings(md_path: Path, metadata_files: list[Path]) -> tuple[str, list[str]]:
    """(where, families) for this build: the command line's, else pdfmd-options' (see linebreak_value)."""
    if core.LINEBREAK_CLI["off"]:
        return "cells", []
    if core.LINEBREAK_CLI["kinds"] is not None:
        return linebreak_value(core.LINEBREAK_CLI["kinds"] or True)
    return linebreak_value(core.first_pdfmd_option(md_path, metadata_files, "linebreak"))


def linebreak_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter linebreak.lua`` (`-M pdfmd-linebreak=html,tex`, `-M pdfmd-linebreak-where=cells|all`) for a document that
    has a line-break spelling in it; nothing when no family takes part, and nothing for a document without a spelling (the
    filter would only look)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []
    where, kinds = linebreak_settings(files[0], metadata_files)
    if not kinds or not any(LINEBREAK_RE.search(core.EMBED_BLOCK_RE.sub("", core.read_text_best_effort(file))) for file in files):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("linebreak")
    return (["-M", "pdfmd-linebreak=" + ",".join(kinds), "-M", "pdfmd-linebreak-where=" + where, "--lua-filter", str(shipped)]
            if shipped is not None else [])


# Markdown inside raw LaTeX (v3.32.0, entry 3dc): `\md{...}` and `\begin{md}...\end{md}`. pdfmd_lua/md_macro.lua reads the argument as
# Markdown, so citations, cross-references and math stay in the one document; the filter goes in before every other one (before
# pandoc-crossref and --citeproc). pdfmd-options: md-macro: on (the default) | off. Only for a document that has a macro, and not
# one that defines `\md` itself.
MD_MACRO_RE = re.compile(r"\\md(?![A-Za-z])[ \t]*\{|\\begin\{md\}")


MD_MACRO_OWN_RE = re.compile(
    r"\\(?:re|provide)?newcommand\*?[ \t]*\{?[ \t]*\\md(?![A-Za-z])|\\(?:def|let|gdef|edef)[ \t]*\\md(?![A-Za-z])"
    r"|\\Declare(?:Robust)?Command\*?[ \t]*\{?[ \t]*\\md(?![A-Za-z])|\\(?:re)?newenvironment\*?[ \t]*\{md\}")


MD_MACRO_CODE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$|`[^`\n]*`", re.MULTILINE | re.DOTALL)


def md_macro_in(text: str) -> bool:
    """Whether the text uses `\\md{...}` or `\\begin{md}` outside code, and does not define `\\md` itself."""
    bare = MD_MACRO_CODE_RE.sub("", text)
    return bool(MD_MACRO_RE.search(bare)) and not MD_MACRO_OWN_RE.search(bare)


def md_macro_on(md_path: Path, metadata_files: list[Path]) -> bool:
    """The `md-macro` option: on unless the document, a metadata file or the config says off (anything else stops the build)."""
    value = core.first_pdfmd_option(md_path, metadata_files, "md-macro")
    if value is None:
        return True
    word = {True: "on", False: "off"}.get(value, str(value).strip().casefold())
    if word not in ("on", "off"):
        raise SystemExit(f"pdfmd-options md-macro: {value!r} is not one of on, off")
    return word == "on"


def md_macro_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter md_macro.lua`` for a document with an `\\md{...}` or `\\begin{md}`, unless `md-macro` is off or the document
    defines `\\md` itself (then its own definition stands)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or not md_macro_on(files[0], metadata_files):
        return []
    if not any(MD_MACRO_RE.search(MD_MACRO_CODE_RE.sub("", core.read_text_best_effort(file))) for file in files):
        return []
    if not any(md_macro_in(core.read_text_best_effort(file)) for file in files):
        print(f"NOTE  {files[0]}: \\md is defined by the document itself, so pdfmd does not read Markdown inside it "
              "(`md-macro: off` silences this)", file=sys.stderr)
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("md_macro")
    return ["--lua-filter", str(shipped)] if shipped is not None else []


# A fenced div that sets the paragraph indent for its stretch of text (v3.30.0): `::: {indent=false}`, `{indent=2em}`,
# `::: noindent`, `::: {.noindent}`, `::: indent`, and the class-word spellings of a value, `::: indent=3in`, `::: .indent=3in`,
# `::: indent-3in`, `::: {.indent-3in}`, `::: {.indent=3in}`. pdfmd_lua/indent.lua does it for the target format and puts the
# document's own indent back at the closing `:::`; the filter goes in only for a document that has such a div. The expression
# also lets a near miss through (`.indent3in`, `.noindent=2em`) so that the filter can say it is none of them; a class that only
# starts with the word (`.indented`, `.indentation`) does not.
_INDENT_WORD = r"(?:no)?indent(?:\b|(?=\d)|(?=(?:rem|em|ex|pt|cm|mm|in|bp|pc|px)\b))"


INDENT_DIV_RE = re.compile(r"""^[ \t]*:{3,}[ \t]*(?:\{(?:[^}"\n]|"(?:[^"\\\n]|\\.)*")*(?:\.""" + _INDENT_WORD + r"""|\bindent[ \t]*=)"""
                           r"""|\.?""" + _INDENT_WORD + r"""[^\s{}]*[ \t]*$)""", re.MULTILINE)


def contains_indent_div(md_path: Path) -> bool:
    text = core.EMBED_BLOCK_RE.sub("", core.read_text_best_effort(md_path))
    return bool(INDENT_DIV_RE.search(text))


def calc_div_wants_indent_filter(files: list[Path], metadata_files: list[Path]) -> bool:
    if not files or not any(core.CALC_DIV_RE.search(core.EMBED_BLOCK_RE.sub("", core.read_text_best_effort(file))) for file in files):
        return False
    return not core.calc_is_off(files[0], metadata_files) and core.calc_noindent_mode(files[0], metadata_files) != "off"


def indent_filter_args(sources: Path | list[Path], metadata_files: list[Path] = ()) -> list[str]:
    """``--lua-filter indent.lua`` when a source has an `indent=` / `.noindent` div (see INDENT_DIV_RE), or a `::: calc` div
    while calc gives its divs no indent (the default; calc.lua sets `indent=false` on them, this filter acts on it)."""
    files = sources if isinstance(sources, list) else [sources]
    if not any(contains_indent_div(file) for file in files) and not calc_div_wants_indent_filter(files, metadata_files):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("indent")
    return ["--lua-filter", str(shipped)] if shipped is not None else []


def title_filter_args(sources: Path | list[Path], metadata_files: list[Path], pandoc_options: list[str] | None = None,
                      no_auto: list[str] | None = None) -> list[str]:
    """``--lua-filter title_meta.lua`` when the title or the authors have LaTeX in them (v3.28.6): Pandoc's own
    `title-meta`, the PDF's Title, leaves raw LaTeX out ("Reduction of -Cinnamaldehyde" for `\\emph{trans}`); and when an
    author is a mapping (`mapped_author`, v3.33.56), which Pandoc's `author-meta`, the PDF's Author, leaves out. Before the
    document's own filters, so that one which takes the title out and keeps `title-meta` finds it set. With
    `-M pdfmd-author-names=true` when the filter may also write such an author's name in its place in LaTeX's and HTML's
    title block (author_names_in_place, v3.33.69)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []

    def text(value) -> str:
        if isinstance(value, dict):
            return " ".join(text(item) for item in value.values())
        if isinstance(value, list):
            return " ".join(text(item) for item in value)
        return "" if value is None else str(value)

    metadata = core.effective_metadata(files[0], metadata_files, [])
    if not any("\\" in text(metadata.get(key)) for key in ("title", "author")) and not core.mapped_author(metadata.get("author")):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("title_meta")
    if shipped is None:
        return []
    in_place = core.author_names_in_place(files[0], metadata_files, metadata.get("author"), pandoc_options, no_auto)
    return [*(["-M", "pdfmd-author-names=true"] if in_place else []), "--lua-filter", str(shipped)]


def raw_filter_args(sources: Path | list[Path], no_auto: list[str] | None, metadata_files: list[Path],
                    flat_pictures: Path | None = None, preamble: list[Path] | None = None,
                    flat_text: bool = False) -> list[str]:
    """The filters of pdfmd_lua for non-Markdown pieces: raw.lua when `raw` asks for it (any writer), pdf_images.lua
    when a document names a PDF image (it acts for HTML writers only: a browser cannot show a PDF). Both read the
    picture cache folder and the table from one metadata file written here."""
    try:
        import pdfmd_lua
        raw_filter, pdf_filter = pdfmd_lua.path("raw"), pdfmd_lua.path("pdf_images")
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    files = sources if isinstance(sources, list) else [sources]
    table = (resolve_raw(files[0], metadata_files, flat=flat_pictures is not None or flat_text)
             if raw_filter is not None and files else None)
    pdf_images = (pdf_filter is not None and not core.auto_disabled(no_auto, "pdfimages")
                  and any(PDF_IMAGE_RE.search(core.read_text_best_effort(file)) for file in files))
    diagram_filter = pdfmd_lua.path("diagram")
    diagrams = (diagram_filter is not None and not core.auto_disabled(no_auto, "diagrams")
                and any(DIAGRAM_BLOCK_RE.search(core.read_text_best_effort(file)) for file in files))
    smiles_filter = pdfmd_lua.path("smiles")
    smiles = (smiles_filter is not None and not core.auto_disabled(no_auto, "smiles")
              and any(SMILES_BLOCK_RE.search(core.read_text_best_effort(file)) for file in files))
    if table is None and not pdf_images and not diagrams and not smiles:
        return []
    folder = core.cache_root() / "raw"
    # Pandoc reads a string in a metadata file as Markdown, where a backslash escapes: a Windows path keeps forward slashes
    config: dict = {"pdfmd-raw-cache": (folder / "pictures").as_posix()}
    if flat_pictures is not None:       # flat Markdown: the pictures it needs sit beside the output, linked by a relative path
        config = {"pdfmd-raw-cache": flat_pictures.as_posix(), "pdfmd-raw-rel": flat_pictures.name,
                  "pdfmd-raw-work": (folder / "pictures").as_posix()}       # the SVGs go beside the output, the drawn PDFs stay in the cache
    if preamble:            # a LaTeX picture is drawn with the document's own preamble
        config["pdfmd-raw-preamble"] = [Path(item).as_posix() for item in preamble]
    if table is not None:
        config["pdfmd-raw"] = table
    if diagrams:
        import pdfmd_images
        from pdfmd_images.svg import diagram_converters, typst_document
        dpi = image_dpi_for(files[0], metadata_files)
        plan = {"converters": diagram_converters(core.which, core.resolve_soffice, core.fonts_directory(), dpi),
                "typst": typst_document("out.svg"), "dpi": dpi}
        payload = json.dumps(plan, ensure_ascii=False)
        plan_file = folder / "maps" / ("svg-" + hashlib.sha256(payload.encode()).hexdigest()[:20] + ".json")
        if not plan_file.is_file():
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_file.write_text(payload, encoding="utf-8")
        config["pdfmd-svg-plan"] = plan_file.as_posix()
        config["pdfmd-diagram-tools"] = [tool for tool in [*(item[0] for item in DIAGRAM_TOOLS), *pdfmd_images.available_converters(core.which, core.resolve_soffice)]
                                          if tool in pdfmd_images.CONVERTERS or core.which(tool)]
        seconds = diagram_timeout_for(files[0], metadata_files)
        if seconds == 0:
            config["pdfmd-diagram-off"] = True
        elif seconds > 0:       # a negative number: no limit, so no runner either
            runner = Path(pdfmd_lua.FILTERS) / "limited_run.py"
            if sys.executable and runner.is_file():
                config["pdfmd-diagram-timeout"] = seconds
                config["pdfmd-diagram-python"] = Path(sys.executable).as_posix()
                config["pdfmd-diagram-runner"] = runner.as_posix()
            else:       # a copy of pdfmd without its runner, or a Python that cannot say where it is: the tools run as before
                print("NOTE  diagram-timeout is not applied: pdfmd_lua/limited_run.py or the Python interpreter was not found",
                      file=sys.stderr)
    if smiles:
        config.update(smiles_config(files[0], metadata_files))
    digest = hashlib.sha1(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    map_file = folder / "maps" / f"{digest}.yaml"
    if not map_file.is_file():
        map_file.parent.mkdir(parents=True, exist_ok=True)
        map_file.write_text(json.dumps(config, ensure_ascii=False) + "\n", encoding="utf-8")
    args = ["--metadata-file", str(map_file)]
    if table is not None:
        args += ["--lua-filter", str(raw_filter)]
    if pdf_images:
        args += ["--lua-filter", str(pdf_filter)]
    if diagrams:
        args += ["--lua-filter", str(diagram_filter)]
    if smiles:
        args += ["--lua-filter", str(smiles_filter)]
    return args


def document_filter_args(inputs: Path | list[Path], md_path: Path | list[Path], metadata_files: list[Path], no_auto: list[str] | None,
                         csv_filter: Path, pandoc_options: list[str], crossref_sources: Path | list[Path] | None = None,
                         flat_pictures: Path | None = None, preamble: list[Path] | None = None, flat_text: bool = False,
                         cellalign_early: bool = False, label: str | None = None) -> list[str]:
    """The filters pdfmd puts on what a document SAYS (its own syntax: the metadata that appends, `\\md{}`, calc, the CSV tables, page
    breaks, indent, callouts and the other markup, table captions, line breaks, the title, the cover, raw pieces and diagrams, the
    cross-references), in the order they run. Every build writes this one list, whatever the writer is, and so does the live view of
    `--serve` (entry 3do): a syntax added here shows in both, and the live view needs no list of its own.

    `inputs` are the files whose text is searched for the syntax (the document, or all the files of a joined build), `md_path` the
    document itself (a report's files, for report mode); `cellalign_early` puts the cell filter here (the office route), where the
    others put it after the writer's own. `label` names the document in a message (report mode: `REPORT`); `md_path` by default."""
    args = core.metadata_append_args(inputs, metadata_files, pandoc_options, no_auto)
    args += md_macro_args(inputs, metadata_files)
    args += core.deferred("pdfmd_filters.hidden", "mark_args")(inputs, metadata_files)
    args += core.calc_filter_args(inputs, metadata_files)
    args += core.csv_table_filter_args(inputs, no_auto, csv_filter, metadata_files)
    args += pagebreak_filter_args(md_path, metadata_files)
    args += indent_filter_args(inputs, metadata_files)
    args += core.markup_filter_args(md_path, metadata_files)
    args += core.table_caption_args(inputs, metadata_files)
    args += linebreak_args(inputs, metadata_files)
    if cellalign_early:
        args += core.cellalign_args(md_path, metadata_files)
    args += title_filter_args(md_path, metadata_files, pandoc_options, no_auto)
    args += cover_filter_args(md_path, metadata_files)
    args += raw_filter_args(inputs, no_auto, metadata_files, flat_pictures=flat_pictures, preamble=preamble, flat_text=flat_text)
    args += core.crossref_filter_args(crossref_sources or inputs, pandoc_options, no_auto, label or str(md_path))
    return args + core.fullcite_pre_args(inputs, metadata_files, pandoc_options)


# A structure written as text (pdfmd_lua/smiles.lua finds it, pdfmd_smiles draws it): ```smiles, ```{.smiles caption="..."}, ::: smiles
SMILES_BLOCK_RE = re.compile(r"(?mi)^[ \t]*(?:`{3,}|~{3,}|:{3,})[ \t]*\{?[ \t]*\.?smiles\b")


def smiles_config(md_path: Path, metadata_files: list[Path]) -> dict:
    """The metadata smiles.lua reads: the resolved `pdfmd-options.smiles` (document, metadata files, config; the first place to set
    a field wins), the interpreter that has RDKit (pdfmd's own) and the folder of the drawing step."""
    try:
        import pdfmd_smiles
    except ImportError:
        return {}
    try:
        settings = pdfmd_smiles.resolve(core.cascaded_option(md_path, metadata_files, "smiles"))
    except pdfmd_smiles.SmilesError as error:
        raise SystemExit(f"{core.display_path(md_path)}: {error}")
    return {"pdfmd-smiles": {key: str(value) for key, value in settings.items()},
            "pdfmd-smiles-python": Path(sys.executable).as_posix(),
            "pdfmd-smiles-dir": Path(pdfmd_smiles.__file__).resolve().parent.as_posix()}


# A fenced block written in a diagram language (pdfmd_lua/diagram.lua draws it): ```mermaid, ```{.d2 caption="..."}, ```dot
DIAGRAM_BLOCK_RE = re.compile(r"(?mi)^[ \t]*(?:`{3,}|~{3,})[ \t]*\{?[ \t]*\.?(?:mermaid|d2|dot|graphviz)\b")


DIAGRAM_TIMEOUT = 120.0         # seconds one diagram tool run may take when nothing says otherwise: the `diagram-timeout` setting's default


def diagram_timeout_from(value) -> float:
    """The `diagram-timeout` setting as seconds: 0 = no diagram is drawn, a negative number = no limit, not set or not a
    number = DIAGRAM_TIMEOUT."""
    number = core.option_flag_number(value)
    return DIAGRAM_TIMEOUT if number is None else number


def diagram_timeout_for(md_path: Path, metadata_files: list[Path]) -> float:
    """The `diagram-timeout` of the document about to be built: its `pdfmd-options`, its metadata files', the config's."""
    value = (core.first_pdfmd_option(md_path, metadata_files, "diagram-timeout") if md_path.suffix.lower() in (".md", ".markdown")
             else core.config_options().get("diagram-timeout"))
    return diagram_timeout_from(value)


DIAGRAM_TOOLS = (("dot", "Graphviz", "brew install graphviz  |  apt install graphviz  |  pdfmd --install diagram:dot"),
                 ("d2", "D2", "brew install d2  |  pdfmd --install diagram:d2  |  https://d2lang.com/tour/install"),
                 ("mmdc", "Mermaid", "npm install -g @mermaid-js/mermaid-cli"))


RELATIVE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((?!https?:|data:|/|<)[^)\s]+\)")


def select_filter_args(selection) -> list[str]:
    """``--lua-filter select.lua`` when the inputs are wrapped in part divs (see ``wrap_part``)."""
    if selection is None or selection is False:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("select")
    return ["--lua-filter", str(shipped)] if shipped is not None else []


def chem_filter_args(sources: list[Path], metadata_files: list[Path], preamble_files: list[Path], writer: str,
                     office_filter: bool, no_auto: list[str] | None) -> list[str]:
    """``--lua-filter chem.lua`` (v3.28.10) for an output whose writer drops raw LaTeX and that the LaTeX filter does not
    run for (an HTML, EPUB, Markdown, text or .typ file, a PowerPoint deck), when a source has a \\ce, \\pu or siunitx
    command: they become text with sub- and superscripts, or converted math. Not for LaTeX, nor Word and OpenDocument
    (the LaTeX filter's own), nor with `office: {latex: off}`."""
    if (office_filter or writer in ("latex", "beamer", "context", "docx", "odt", "opendocument", "json", "native")
            or core.auto_disabled(no_auto, "officelatex")
            or str(core.office_options(sources[0], metadata_files, no_auto).get("latex", "")).casefold() in ("off", "false", "no")):
        return []
    if not any(core.MATH_ONLY_LATEX_RE.search(core.strip_code_text(core.split_front_matter(core.read_text_best_effort(source))[1]))
               for source in sources):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("chem")
    if shipped is None:
        return []
    args = ["-M", f"pdfmd-chem-python={sys.executable}"]
    if preamble_files:
        args += ["-M", "pdfmd-chem-preamble=" + os.pathsep.join(str(item) for item in preamble_files)]
    return args + ["--lua-filter", str(shipped)]


def typst_filter_args(writer: str, command: list[str] | None = None, directory: Path | None = None) -> list[str]:
    """``--lua-filter typst.lua`` for Typst (v3.27.11): a link to an anchor the document does not have becomes its
    text with one WARN, where Typst would stop the build; with a Pandoc before 3.2, a picture's relative path is made
    absolute. Last, after citeproc and the document's own filters."""
    if writer != "typst":
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("typst")
    # Pandoc 3.1.3 otherwise writes native #cite calls even after citeproc resolved the text.
    # Explicitly use that text; current Pandoc writes the same output with either extension setting.
    citations = ["-t", "typst-citations"] if "--citeproc" in (command or []) else []
    paths = core.deferred("pdfmd_bibliography", "typst_path_args")(command or [])
    return citations + core.typst_template_args(writer, command or [], directory) + paths + ["--lua-filter", str(shipped)] if shipped is not None else []
