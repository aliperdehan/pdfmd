"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_build`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported.

The build of one document: `convert_one` (every single-file build, `-b` and its `-j` workers, a parts build, `-r`'s files;
the engine that built it and --strict, with `finish_build`, and the document's `soffice-timeout`, `set_soffice_limit`),
`_convert_one_recorded` (a partial build's label scan and calculator names, the --backup snapshot), `_convert_one` (the
embedded bibliography files findable, the ODT route), `_convert_one_core` (discovery, the Pandoc command, the engine chain,
`make_embed_plan` for --embed-metadata, `run_engine_command`, which lib/pdfmd_report calls too) and `convert_via_cache` (the
cache route: Pandoc writes the .tex, pdfmd compiles it), with the build's defaults (`PREFERRED_FONT`,
`DEFAULT_MONOFONT`, `DEFAULT_VARS`) and `WEASYPRINT_CSS_NOISE`. What a build leaves for the command line to report (the
`LAST_*` label counts) and the calculator's seed files (`CALC_SEED`, `CALC_BELOW`, `CALC_DUMP`) stay pdfmd's state, written
as `core.X = ...`, and so does `SOFFICE_TIMEOUT_NOW`; `DEFAULT_MARGIN` stays in pdfmd.py for now (SPLIT.md, moves 5 and 6).
`@timed` and `@noted` come from pdfmd_base, which is loaded already. The quoted annotations name pdfmd.py's `Built`,
`EmbedRequest` and `LabelScan` and pdfmd_assemble's `EmbedPlan` as text: nothing evaluates them."""

from __future__ import annotations

import contextlib
import inspect
import os
import pdfmd_cache
import pdfmd_install
import pdfmd_native
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp, NamedTemporaryFile

from pdfmd_base import core
from pdfmd_base import noted, timed

from pdfmd_base import pandoc_run
from pdfmd_log import emit
from pdfmd_cite.aliases import apply as apply_citation_aliases
from pdfmd_engines.memory import scoped

from . import page_numbers




# Tried first, when neither the document nor -f/--font names a mainfont:
# better Unicode/math coverage and typography than LaTeX's own Latin Modern
# for most prose. DEFAULT_FONT (DejaVu) is the deliberate fallback for
# whatever glyphs it's missing -- see the retry in convert_one(). Pandoc's
# own mainfontfallback mechanism (per-glyph automatic fallback within one
# compile) was tried and rejected here: it silently no-ops under xelatex and
# crashes lualatex outright in this environment, so the existing
# detect-then-retry-with-a-different-mainfont path is what actually works.
PREFERRED_FONT = "STIX Two Text"


DEFAULT_MONOFONT = "JetBrains Mono"


DEFAULT_VARS = []


# WeasyPrint's CSS parser names each property and media query it ignores. Pandoc's page style and KaTeX's stylesheet
# are written for browsers, so a good build printed a screenful of them (v3.28.11); --verbose still shows them.
WEASYPRINT_CSS_NOISE = re.compile(r"(?m)^WARNING: (?:Ignored `[^`\n]*` at \d+:\d+, (?:unknown property|invalid value)\."
                                  r"|Expected a media type, got .*|Invalid media type .* rule was ignored at \d+:\d+\.)"
                                  r"[ \t]*(?:\n|$)")


@timed(lambda args, kwargs: "pandoc + " + str(kwargs["engine"] if "engine" in kwargs else args[1]))
@noted(lambda args, kwargs: str(kwargs["engine"] if "engine" in kwargs else args[1]), engine=True)
def run_engine_command(cmd: list[str], engine: str, output: Path, run_pandoc, page_options,
                       verbose: bool, *, numbered: bool = True) -> subprocess.CompletedProcess:
    """Run one engine's Pandoc command: `run_pandoc(command, target)` as it is, or for "calibre" into an HTML
    page that ebook-convert then prints (`page_options()` gives its paper, margins and language). Pandoc's own
    warnings are kept in the result; WeasyPrint's about the CSS it ignores only with --verbose."""
    environment = (core.load_package("pdfmd_tex.repair").engine_environment(engine) if engine in core.LATEX_ENGINES
                   else contextlib.nullcontext())                  # TeX self-repair (v3.33.219)
    with environment, core.calibre_html_command(cmd, engine) as (command, html):
        result = run_pandoc(command, html or output)
        if result.returncode != 0 and engine == "lualatex":                    # a corrupt font database: once more, with a fresh cache
            repair = core.load_package("pdfmd_tex.repair")

            def again():
                with repair.engine_environment(engine):
                    return run_pandoc(command, html or output)
            result = repair.retry_lualatex(engine, (result.stderr or "") + "\n" + (result.stdout or ""), again) or result
        if engine == "weasyprint" and result.returncode == 0 and not verbose and result.stderr:
            result = subprocess.CompletedProcess(result.args, 0, result.stdout,
                                                 WEASYPRINT_CSS_NOISE.sub("", result.stderr))
        if html is None or result.returncode != 0:
            return result
        printed = (core.run_browser_print(html, output, engine, page_options(), verbose) if engine in core.BROWSER_ENGINES
                   else core.run_calibre(html, output, page_options(), verbose, numbered=numbered))
        return subprocess.CompletedProcess(printed.args, printed.returncode, result.stdout,
                                           (result.stderr or "") + printed.stderr)


def _convert_one(md_path: Path, *args, **kwargs):
    """_convert_one_core, with the document's embedded bibliography files
    (and its NAME.unpacked/ folder) findable for the whole build -- the cache
    route's compile step included, which runs after the Markdown-to-.tex pass."""
    with core.embedded_resources(md_path):
        if kwargs.get("target_format") == "odt":
            return core.deferred("pdfmd_bridge.odt", "convert")(core._convert_one_core, md_path, *args, **kwargs)
        return core._convert_one_core(md_path, *args, **kwargs)


def _convert_one_core(md_path: Path, out_dir: Path | None, presentation: bool, font: str,
                engines: list[str], variables: list[str], slide_level: int | None,
                pandoc_options: list[str],
                metadata_file: Path | list[Path] | None = None,
                output_file: Path | None = None,
                preamble_files: list[Path] | None = None,
                target_format: str = "pdf",
                from_format: str | None = None,
                no_auto: list[str] | None = None,
                verbose: bool = False,
                debug: bool = False,
                stamp_overrides: dict | None = None,
                keep_aux: bool = False,
                extra_inputs: list[Path] | None = None,
                partial: bool = False,
                cache_cli: bool | None = None,
                skip_stamp: bool = False,
                full_scaffold: Path | None = None,
                parts_root: Path | None = None,
                part_markers: bool = False,
                embed: "EmbedRequest | None" = None,  # noqa: F821 -- quoted, never evaluated: pdfmd.py's EmbedRequest
                trust_embedded: bool = False,
                self_contained: bool | None = None,
                source_override: tuple[str, bool] | None = None,
                label_scan: "LabelScan | None" = None,  # noqa: F821 -- quoted, never evaluated: pdfmd.py's LabelScan
                selection: "set[Path] | bool | None" = None,
                link_output: Path | None = None) -> tuple[Path, bool, str]:
    # selection: the inputs are ALL the parts (a set: those to keep) or the whole document (True), each wrapped in a part
    # div, and select.lua drops the rest after pandoc-crossref has numbered everything (see wrap_part).
    # label_scan: the headers that replay the whole document's labels (see build_label_scan).
    # source_override: (text, shifted) of the document cut down to some of its
    # sections -- see SectionPlan. Always a partial build.
    # self_contained: --self-contained/--no-self-contained (None = the document's).
    # embed: the EmbedRequest of --embed-metadata, for the assembled stage.
    # trust_embedded: --trust-embedded (see embedded_lua_filters).
    # cache_cli: --cache/--no-cache. skip_stamp: the cache route's .tex stage,
    # whose stamp is written once, after the PDF exists. full_scaffold: the
    # scaffold a partial build's labels may be seeded from (see below).
    # extra_inputs: parts-mode parts, joined to md_path (the scaffold) in one
    # Pandoc run -- see plan_scaffold(). partial: only some of them, so this
    # isn't the report itself and writes no BUILD NOTES stamp.
    stamp_overrides = stamp_overrides or {}
    parts_inputs = list(extra_inputs or [])
    if partial:      # for the history (stamp_build): which parts this build is made of, or the text of the sections
        chosen = ([item for item in parts_inputs if item in selection]
                  if isinstance(selection, (set, frozenset)) and parts_inputs else parts_inputs)
        core.BUILD["partial"] = {"parts": [Path(item) for item in chosen], "root": parts_root,
                            "cut": source_override[0] if source_override is not None else None}
    measurement_state = {}
    tex_path_warnings: set = set()
    noted: set[tuple[str, str]] = set()

    def note(kind: str, detail: str) -> None:
        if (kind, detail) in noted:          # the same decision, made again for the next engine
            return
        noted.add((kind, detail))
        core.AUTO_LOG.record(kind, detail, verbose)

    # the style sheets of the document (v3.28.41): linked for an HTML-family build, read for settings with css-scope: all
    css_meta = [metadata_file] if isinstance(metadata_file, Path) else list(metadata_file or [])
    for layer_path, _ in core.folder_layer_files(str(md_path.resolve().parent)):        # the folder settings in force (v3.29.10)
        core.AUTO_LOG.record_file("SETTINGS", Path(layer_path), verbose)
    html_family = (target_format in core.HTML_TARGETS or target_format.startswith("epub")
                   or (target_format == "pdf" and any(item in core.ENGINE_GROUPS["html"] or item == "calibre" or item in core.BROWSER_ENGINES for item in engines)))
    css_options, css_variables = core.css_additions(md_path, css_meta, variables, no_auto, html_family, note)
    if css_options or css_variables:
        pandoc_options = [*pandoc_options, *css_options]
        variables = [*variables, *css_variables]

    def flush_summary() -> None:
        core.tablewidth_note(md_path, note)
        if not verbose:
            core.AUTO_LOG.flush()

    from pdfmd_filters.lua import figure_fit_module
    figure_fit = figure_fit_module()
    metadata_files = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
    cli_no_auto = no_auto
    no_auto = core.effective_no_auto(md_path, no_auto)
    kit_kinds = core.kit_no_auto_kinds(md_path, metadata_files, no_auto)
    if kit_kinds:
        no_auto = core.effective_no_auto(md_path, cli_no_auto, kit_kinds)
    output_extension = core.output_extension_for(target_format, md_path)
    output = output_file or (
        (out_dir / f"{md_path.stem}{output_extension}") if out_dir else md_path.with_suffix(output_extension)
    )
    core.BUILD["output"], core.BUILD["sources"] = output, [md_path, *parts_inputs]
    if parts_inputs:
        core.BUILD["root"] = parts_root
    if md_path.suffix.lower() in core.MARKDOWN_LIKE_SUFFIXES:
        core.check_asset_budget(core.BUILD["sources"], md_path, metadata_files)
        core.check_nonmath_dollars(core.BUILD["sources"], from_format, metadata_files, core.auto_disabled(no_auto, "reader"))
    for source_file in (md_path, *parts_inputs):
        try:
            clash = output.exists() and source_file.exists() and output.samefile(source_file)
        except OSError:
            clash = False
        if clash:
            raise SystemExit(f"{core.display_path(output)} is the source itself; the {target_format} output would replace it. "
                             "Give another name with -o, or another folder.")
    output.parent.mkdir(parents=True, exist_ok=True)

    if source_override is not None and target_format == core.ASSEMBLED_FORMAT:
        raise SystemExit(f"{md_path}: --stop-at markdown writes the whole document; it cannot be "
                         "combined with name#section")
    if target_format == core.ASSEMBLED_FORMAT:
        # --stop-at markdown: write the text Pandoc would have been given and
        # stop. Before every other branch -- no engine, reader, filter, font
        # or stamp decision below applies to it.
        if parts_inputs:
            note("PARTS", f"{md_path}: {len(parts_inputs)} part{'s' if len(parts_inputs) != 1 else ''} "
                          f"joined after it" + (" (partial build)" if partial else ""))
        plan = make_embed_plan(md_path, metadata_files, preamble_files, no_auto, embed)
        ok, reason = core.write_assembled_markdown([md_path, *parts_inputs], output, bool(parts_inputs), plan, partial,
                                              core.resolve_strip_comments(md_path, metadata_files), metadata_files, no_auto, from_format)
        flush_summary()
        return md_path, ok, reason

    if (target_format == "pdf" and engines and md_path.suffix.lower() not in core.OFFICE_INPUT_EXTENSIONS
            and not all(core.is_native_engine(engine) for engine in engines)):
        engines = core.chain_plan_build(md_path, metadata_files, engines, output, verbose)     # engine-fallback (v3.33.71)
    native_engines = [engine for engine in engines if core.is_native_engine(engine)]
    if target_format == "pdf" and native_engines:
        # The native tier (see the section after dependency_report()): no
        # Pandoc, no engine, none of the discovery below applies to it.
        native_source, temporaries = md_path, []
        if parts_inputs or source_override is not None:
            # The renderers read one Markdown file: the parts are joined after the document and a section is
            # the document cut down to it, the same text Pandoc would be given (see assemble_markdown_text)
            first = md_path
            if source_override is not None:
                with NamedTemporaryFile("w", encoding="utf-8", suffix=md_path.suffix, prefix=f".{md_path.stem}.pdfmd-section-",
                                        dir=md_path.parent, delete=False) as handle:
                    handle.write(source_override[0])
                first = Path(handle.name)
                temporaries.append(first)
            with core.scaffold_inputs([first, *parts_inputs], bool(parts_inputs),
                                      metadata_files=metadata_files, pandoc_source=False) as scaffold_files, \
                    NamedTemporaryFile("w", encoding="utf-8", suffix=md_path.suffix, prefix=f".{md_path.stem}.pdfmd-native-",
                                       dir=md_path.parent, delete=False) as handle:
                handle.write(core.assemble_markdown_text(scaffold_files, False, None, partial, False))
            native_source = Path(handle.name)
            temporaries.append(native_source)
            if parts_inputs:
                note("PARTS", f"{md_path}: {len(parts_inputs)} part{'s' if len(parts_inputs) != 1 else ''} "
                              f"joined after it" + (" (partial build)" if partial else ""))
        try:
            ok, reason = core.convert_native(native_source, output, native_engines, metadata_files, from_format, verbose, debug)
        finally:
            for temporary in temporaries:
                temporary.unlink(missing_ok=True)
        if ok:
            core.stamp_build(partial, skip_stamp, md_path, metadata_files, preamble_files or [],
                                 stamp_overrides, output, verbose)
        flush_summary()
        return md_path, ok, reason[-3000:]

    if (target_format == "pdf" and md_path.suffix.lower() == ".tex"
            and (from_format is None or from_format.casefold() in ("latex", "tex"))
            and not core.auto_disabled(no_auto, "texdirect")):
        # Compile standalone TeX directly, and use the project preamble for a fragment.
        # --no-auto texdirect or an explicit non-LaTeX reader goes through Pandoc.
        from pdfmd_tex.inputs import compile_tex_source
        ok, reason, handled_fragment = compile_tex_source(md_path, output, engines, keep_aux, verbose, debug,
                                                         list(preamble_files or []), metadata_files, pandoc_options)
        if ok or handled_fragment or not core.which("pandoc") or core.chain_stopped():
            flush_summary()
            return md_path, ok, reason[-3000:]
        # No LaTeX engine got it through (or none is installed): Pandoc can still read the file and any engine can
        # draw what it reads -- less faithful than the source, so said out loud, and the LaTeX message stays above.
        emit("warning", None, f"WARN  {core.display_path(md_path)}: direct compilation failed ({reason.strip().splitlines()[-1][:160] if reason.strip() else 'no reason given'}); "
              "trying it through Pandoc, which rewrites the LaTeX and may change its look", file=sys.stderr)

    if md_path.suffix.lower() in core.OFFICE_INPUT_EXTENSIONS:
        # A .docx/.pptx/.xlsx/.odt/etc. source converts straight to PDF
        # via headless soffice -- no Pandoc involved (see the module-level
        # comment above convert_office_direct). Unlike the .tex branch
        # above, there is no working "opt back into Pandoc" route here:
        # every Pandoc-mediated helper below this point (has_mainfont,
        # contains_citations, find_lua_filters, promote_bare_title, ...)
        # unconditionally reads md_path as text, which crashes outright on
        # a binary office document even for .docx/.odt (the two formats
        # Pandoc's reader actually supports) -- caught directly, as a real
        # traceback, testing --no-auto officedirect against a real .docx.
        # Properly supporting that route would mean auditing/guarding
        # every one of those helpers for binary input, out of scope for
        # this phase (and arguably not worth it: direct soffice conversion
        # already preserves the original document's own formatting better
        # than Pandoc's docx/odt reader would). So a non-PDF --to, an
        # explicit --from, or --no-auto officedirect on an office document
        # is a clear error instead of a route that would only crash a few
        # calls later.
        if target_format != "pdf" or from_format is not None or core.auto_disabled(no_auto, "officedirect"):
            raise SystemExit(
                f"{md_path}: only direct PDF conversion (via soffice) is supported for an "
                f"office document in this version -- a non-PDF --to, --no-auto officedirect, "
                f"and --from all have no working Pandoc-mediated route for {md_path.suffix} "
                "input (see CHANGELOG-pdfmd.md's known-limitation note)."
            )
        ok, reason = core.convert_office_direct(md_path, output, verbose, debug)
        if ok:
            core.record_engine("soffice")
        flush_summary()
        return md_path, ok, reason[-3000:]

    if target_format == "ansi" and not core.which("pandoc") and not parts_inputs:
        ok, reason = core.ansi_without_pandoc(md_path, output, metadata_files)        # the built-in parser stands in (v3.30.3)
        flush_summary()
        return md_path, ok, reason[-3000:]
    if not core.which("pandoc"):
        raise SystemExit(core.PANDOC_MISSING)
    core.warn_old_pandoc()

    effective_from, reader_reason = (
        (from_format, None) if core.auto_disabled(no_auto, "reader")
        else core.resolve_from_format(md_path, from_format, metadata_files)
    )
    core.load_package("pdfmd_history.record").set_reader(md_path, effective_from, from_format,
                                                        metadata_files, no_auto, reader_reason)
    if reader_reason:
        note("READER", reader_reason)
    lua_filters = [] if core.discovery_disabled(no_auto, "lua") else core.find_lua_filters(md_path, metadata_files, no_auto)
    if not core.auto_disabled(no_auto, "lua"):
        for extra_filter in core.frontmatter_extra_lua_filters(md_path, metadata_files):
            if extra_filter not in lua_filters:
                lua_filters.append(extra_filter)
    lua_filters = core.check_lua_filters(md_path, lua_filters, core.resolve_strict(md_path, metadata_files))
    for lua_filter in lua_filters:
        note("LUA", str(lua_filter))
    from pdfmd_filters.lua import pre_citeproc_args
    before_citeproc = pre_citeproc_args(md_path, metadata_files, no_auto)

    # Resolved once, up front, since PDF metadata (unlike the .md BUILD
    # NOTES stamp, written after a successful compile) has to already be
    # baked into the LaTeX source before pandoc/the engine even runs.
    # stamp_after_success() resolves its own copy after the fact -- cheap
    # to redo, and keeps that already-tested path untouched.
    pdf_meta_options = core.resolve_stamp_options(md_path, metadata_files, stamp_overrides)
    pdf_meta_snippet_text = (
        core.pdf_metadata_snippet(pdf_meta_options, core.gather_stamp_texts(md_path, preamble_files or []), verbose)
        if pdf_meta_options["pdf_metadata"] and core.stamp_scope_matches(pdf_meta_options, None) else None
    )

    # -- the cache route (see CACHE_DEFAULTS): Markdown -> .tex by the very
    # same code that serves `--to latex`, then pdfmd's own engine runner in
    # a persistent per-document folder. Also taken, regardless of the cache
    # setting, by a parts-mode build that asks for natbib/biblatex: the
    # Pandoc-run bibliography path cannot take several input files, and the
    # runner already knows how to drive bibtex/biber.
    if target_format == "pdf" and not presentation and md_path.suffix.lower() == ".md":
        cache = core.cache_settings(md_path, metadata_files, cache_cli)
        native_bibliography = (not core.auto_disabled(no_auto, "citationengine")
                               and core.frontmatter_citation_engine(md_path, metadata_files) in ("natbib", "biblatex"))
        tex_engines = [engine for engine in engines if engine in core.LATEX_ENGINES and engine not in ("context", "latexmk", "tectonic")]
        if (cache["aux"] or cache["plots"] or (parts_inputs and native_bibliography)) and tex_engines:
            # cli_no_auto, not the merged no_auto: the Markdown-to-.tex pass inside
            # re-reads the document's own `pdfmd-options.no-auto` itself, and an
            # assembled file lists `lua` there, which would hide its embedded
            # filters from that pass (they are not subject to it: see
            # embedded_lua_filters).
            return convert_via_cache(md_path, out_dir, font, tex_engines, variables, slide_level,
                                     pandoc_options, metadata_file, output, preamble_files, from_format,
                                     cli_no_auto, verbose, debug, stamp_overrides, keep_aux, parts_inputs,
                                     partial, bool(cache["aux"]), full_scaffold, parts_root, note,
                                     flush_summary, plots=bool(cache["plots"]),
                                     trust_embedded=trust_embedded, source_override=source_override,
                                     label_scan=label_scan, skip_stamp=skip_stamp)
    if label_scan is not None:
        # the ordinary route: the replay goes in with the other LaTeX headers (the engine loop passes them to the LaTeX engines only)
        preamble_files = [*(preamble_files or []), *label_scan.headers]
        part_markers = part_markers or bool(parts_inputs and label_scan.markers)

    ascii_on = core.ASCII_CLI["on"] and target_format in core.ASCII_FORMATS     # --to ascii: no character above 127
    flat_markdown = target_format == "gfm"             # flat Markdown: pictures beside the output, relative links, one line a paragraph
    flat_target = flat_markdown or target_format == "txt"        # and flat text, which shares the pipeline (not those extras)
    flat = core.flat_settings(md_path, metadata_files, target_format) if flat_target else None
    from pdfmd_cite import numbered
    from pdfmd_filters import document_filter_scope
    from pdfmd_obsidian.links import linked_inputs
    from pdfmd_tables.prepass import table_colons, table_repair, table_source

    references = numbered.prepare([md_path, *parts_inputs], metadata_files, pandoc_options, from_format)
    numbered_citations = references is not None and not references.separate
    numbered_source = numbered_citations and target_format == "markdown"
    if numbered_citations:
        effective_from = numbered.reader_for(effective_from)
    transform_part = core.ascii_table_transform(md_path, metadata_files, parts_inputs, from_format)
    colons = table_colons(md_path, metadata_files) if parts_inputs else "ignore"
    repair = table_repair(md_path, metadata_files) if parts_inputs else "pandoc"
    with contextlib.ExitStack() as reference_files, document_filter_scope(), core.prepared_title_source(md_path, metadata_files, disabled=core.auto_disabled(no_auto, "title") or flat_target or target_format == "ansi",
                               override=source_override, reader=effective_from, keep_wikilinks=True,
                               transform=references.rewrite if references else None) \
            as (title_source, title_shifted), \
            core.embedded_lua_filters(md_path, not core.auto_disabled(cli_no_auto, "lua"), trust_embedded) \
            as embedded_filters, \
            core.table_width_filter() as width_filter, \
            core.csv_table_filter() as csv_filter, \
            core.scaffold_inputs([md_path, *parts_inputs], bool(parts_inputs),
                            {part: core.part_key(part, parts_root) for part in parts_inputs}
                            if part_markers and parts_root else None,
                            selection if isinstance(selection, (set, frozenset)) else None,
                            numbered.part_transform(references, transform_part),
                            metadata_files=metadata_files,
                            prepare_part=lambda text, part: table_source(text, core.display_path(part), colons=colons,
                                                                         reader=effective_from, repair=repair)) as scaffold_files, \
            linked_inputs([title_source, *scaffold_files[1:]], [md_path, *parts_inputs], effective_from, metadata_files,
                          "pdf" if link_output else target_format, link_output or output,
                          not core.auto_disabled(no_auto, "title")) as (linked, effective_from):
        from pdfmd_filters.properties import arguments as properties_arguments

        title_source, *part_files = linked
        properties_args = properties_arguments(md_path, metadata_files, no_auto)
        reference_args = references.metadata_args(reference_files, include_uncited=not partial) if references else []
        lua_filters = [*lua_filters, *embedded_filters]
        all_inputs = [md_path, *parts_inputs] if parts_inputs else None
        any_citations = core.deferred("pdfmd_excerpts.resolution", "citation_use")(
            all_inputs or [md_path], metadata_files, pandoc_options, no_auto, from_format)
        if any_citations is None:
            any_citations = any(core.contains_citations(item, metadata_files) for item in [md_path, *parts_inputs])
        any_citations = any_citations or bool(before_citeproc) or numbered_citations
        any_code_spans = any(core.has_code_spans(item.read_text(encoding="utf-8-sig"))
                             for item in [md_path, *parts_inputs])
        if parts_inputs:
            shown = len(selection) if isinstance(selection, (set, frozenset)) else len(parts_inputs)
            unit = "more file" if core.REPORT_BUILD.get("files") else "part"
            note("PARTS", f"{md_path}: {shown} {unit}{'s' if shown != 1 else ''} "
                          f"joined after it" + (" (partial build; numbered with the whole document)"
                                                if isinstance(selection, (set, frozenset)) else
                                                " (partial build)" if partial else ""))
            if (target_format == "pdf"
                    and core.frontmatter_citation_engine(md_path, metadata_files) in ("natbib", "biblatex")
                    and not core.auto_disabled(no_auto, "citationengine")):
                # Reached only if the cache route above declined (no usable
                # LaTeX engine in the chain): the Pandoc-run bibliography path
                # takes one input file.
                raise SystemExit(f"{md_path}: natbib/biblatex with parts needs a LaTeX engine "
                                 "(lualatex/xelatex/pdflatex); use citeproc otherwise")
        if title_shifted:
            note("TITLE", f"{md_path}: promoted leading '# ' heading to Pandoc title metadata")
        shift_heading = title_shifted and not core.has_shift_heading_option(pandoc_options)

        if target_format != "pdf":
            # No PDF engine here -- but a TEX_STANDALONE_FORMATS writer
            # (latex/beamer/context) is asked for specifically to hand the
            # caller a document THEY compile themselves, so unlike every
            # other non-PDF target it gets the same preamble/font/margin/
            # header-includes treatment as the PDF-via-LaTeX-engine path
            # below -- just without ever running an engine, so there is no
            # missing-glyph retry: a mainfontfallback is set up front
            # instead, since there is no compile output here to inspect for
            # a retry to react to.
            is_tex_target = target_format in core.TEX_STANDALONE_FORMATS
            document_font = core.has_mainfont(md_path, variables, metadata_files)
            mainfont_auto = not core.auto_disabled(no_auto, "mainfont")
            tablewidth_auto = not core.auto_disabled(no_auto, "tablewidth")
            standalone_auto = (not core.auto_disabled(no_auto, "standalone")
                               and not core.has_standalone_option(pandoc_options))
            citation_engine = (None if core.auto_disabled(no_auto, "citationengine")
                               else core.frontmatter_citation_engine(md_path, metadata_files))
            if citation_engine is not None and citation_engine not in core.CITATION_ENGINES:
                raise SystemExit(f"{md_path}: unknown pdfmd-options.citation-engine value "
                                 f"{citation_engine!r}. Valid: {', '.join(sorted(core.CITATION_ENGINES))}")
            geometry_needed = (is_tex_target and target_format != "beamer"
                              and not core.auto_disabled(no_auto, "margin")
                              and not core.has_geometry(md_path, variables, metadata_files, preamble_files or []))
            monofont_needed = (not core.auto_disabled(no_auto, "monofont")
                              and any_code_spans
                              and not core.has_monofont(md_path, variables, metadata_files))
            if geometry_needed:
                note("MARGIN", f"{md_path}: no geometry/margin set; "
                              f"using geometry:margin={core.DEFAULT_MARGIN} on LaTeX-family targets")
            margin_options = (None if core.auto_disabled(no_auto, "margin")
                              else core.frontmatter_margin_geometry_options(md_path, variables, metadata_files))
            if is_tex_target and margin_options:
                note("MARGIN", f"{md_path}: margin: isn't a Pandoc variable LaTeX-family targets "
                              f"read (geometry: is) -- using geometry:{','.join(margin_options)}")
            if is_tex_target and monofont_needed:
                note("MONOFONT", f"{md_path}: has code but no monofont set; "
                                f"using {core.default_monofont()} on LaTeX-family targets")
            pagesize_typo = (None if core.auto_disabled(no_auto, "papersize")
                             else core.pagesize_typo_value(md_path, variables))
            if is_tex_target and pagesize_typo:
                note("PAPERSIZE", f"{md_path}: pagesize: {pagesize_typo!r} is not a Pandoc variable "
                                  f"(papersize: is) -- using papersize={pagesize_typo} on LaTeX-family "
                                  "targets. Set papersize: yourself, or --no-auto papersize, to silence "
                                  "this and keep the Letter default")
            variables, pagesize_typo = core.paper_variables(md_path, metadata_files, variables, pagesize_typo,
                                                      core.paper_kind("tex" if target_format in ("latex", "beamer") else target_format, no_auto))
            tex_first_font = (None if not is_tex_target else
                              core.mainfont_choice([md_path, *parts_inputs], metadata_files, variables, font,
                                              document_font, mainfont_auto, no_auto, note))
            with core.prepared_latex_inputs([title_source, *core.pandoc_metadata_order(metadata_files)], is_tex_target,
                                       typst_engine=(target_format == "typst"),
                                       drop_embedded_preamble=not is_tex_target, named_reader=from_format,
                                       effective_reader=effective_from) as prepared, \
                    core.document_header_file(md_path, (bool(preamble_files) or core.has_embedded_preamble(md_path) or bool(pdf_meta_snippet_text))
                                         and is_tex_target, metadata_files, no_auto) as header_file, \
                    core.pdf_metadata_header_file(pdf_meta_snippet_text if is_tex_target else None) as pdf_meta_file, \
                    (core.script_fallback([md_path, *parts_inputs], metadata_files, variables, preamble_files or [],
                                     tex_first_font, None, no_auto, note)
                     if target_format in ("latex", "beamer") else contextlib.nullcontext((None, None))) \
                    as (fonts_header, fonts_filter), \
                    core.office_reference(md_path, metadata_files, variables, target_format, output, pandoc_options,
                                     no_auto, note) as office_arguments:
                source, *prepared_metadata = prepared
                writer = core.flat_writer(target_format, flat) if target_format in ("gfm", "gfm+raw", "txt") else target_format
                ansi_scratch = tempfile.TemporaryDirectory(prefix="pdfmd-ansi-") if target_format == "ansi" else None
                ansi_json = Path(ansi_scratch.name) / "document.json" if ansi_scratch is not None else None
                if ansi_json is not None:
                    writer = "json"                              # pdfmd_ansi draws Pandoc's AST (v3.30.3)
                if numbered_citations:
                    writer = numbered.writer_for(writer)
                cmd = ["pandoc", str(source), *map(str, part_files), "-o", str(ansi_json or output), "-t", writer]
                if numbered_source and not core.has_standalone_option(pandoc_options):
                    cmd.append("--standalone")
                if flat_markdown and not any(option.startswith("--wrap") for option in pandoc_options):
                    cmd.append("--wrap=none")      # a paragraph is one line: a viewer wraps it, a diff shows what changed
                if (flat_markdown and output.parent.resolve() != md_path.parent.resolve()
                        and any(core.RELATIVE_IMAGE_RE.search(core.read_text_best_effort(item)) for item in [md_path, *parts_inputs])):
                    note("FLAT", f"{md_path}: the images keep the paths the document wrote, relative to ITS folder; the "
                                 f"output is in {core.display_path(output.parent)}, so those links point from there "
                                 "(put the output beside the images, or copy them)")
                if is_tex_target and standalone_auto:
                    note("STANDALONE", f"{md_path}: --to {target_format} needs a complete, "
                                       "independently compilable document; adding --standalone")
                    cmd.append("--standalone")
                if effective_from:
                    cmd += ["-f", effective_from]
                for metadata in prepared_metadata:
                    cmd += ["--metadata-file", str(metadata)]
                cmd += reference_args
                if partial:
                    cmd += core.PARTIAL_METADATA
                cmd += core.table_keep_metadata(md_path, metadata_files)
                pandoc_cwd = core.pandoc_working_directory(core.metadata_cwd(metadata_files, md_path.parent))
                cmd += core.resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
                if is_tex_target:
                    # Only the PDF path's FIRST attempt (PREFERRED_FONT, or an
                    # explicit font/document mainfont) is reproduced here --
                    # its missing-glyph retry needs an actual compile to
                    # detect against, which nothing here performs. No
                    # mainfontfallback either: see PREFERRED_FONT's own
                    # comment above -- Pandoc's mainfontfallback mechanism is
                    # already known to crash lualatex outright in this
                    # environment, which is exactly why the PDF path uses a
                    # detect-then-retry-with-a-different-mainfont approach
                    # instead of that Pandoc mechanism. If the emitted
                    # mainfont turns out to have missing glyphs when this
                    # .tex is compiled by hand, override it with -f/--font
                    # (or edit \\setmainfont directly) the way the PDF path's
                    # retry would have.
                    first_font = tex_first_font
                    if first_font:
                        cmd += core.font_args("mainfont", first_font)
                        cmd += core.mathfont_args(first_font, md_path, metadata_files, variables, font or None, no_auto, None, note)
                    else:
                        cmd += core.document_font_args([md_path, *parts_inputs], metadata_files, variables)
                    if geometry_needed:
                        cmd += ["-V", f"geometry:margin={core.DEFAULT_MARGIN}"]
                    elif margin_options:
                        for margin_option in margin_options:
                            cmd += ["-V", f"geometry:{margin_option}"]
                    if monofont_needed:
                        cmd += core.font_args("monofont", core.default_monofont())
                    if pagesize_typo:
                        cmd += ["-V", f"papersize={pagesize_typo}"]
                for variable in variables:
                    cmd += ["-V", variable]
                if target_format == "typst" and not core.auto_disabled(no_auto, "papersize"):
                    typst_size = core.typst_papersize_translation(
                        pagesize_typo or next((v.split("=", 1)[1] for v in variables
                                               if v.startswith("papersize=")), None)
                        or core.frontmatter_papersize_value(md_path))
                    if typst_size:
                        note("PAPERSIZE", f"{md_path}: translating papersize for --to typst "
                                          f"-> {typst_size} (typst doesn't accept Pandoc's own "
                                          "LaTeX-shaped paper names)")
                        cmd += ["-V", f"papersize={typst_size}"]
                if shift_heading:
                    cmd += ["--shift-heading-level-by=-1"]
                if preamble_files and is_tex_target:
                    for preamble_file in preamble_files:
                        cmd += ["--include-in-header", str(preamble_file)]
                if pdf_meta_file is not None:
                    cmd += ["--include-in-header", str(pdf_meta_file)]
                if fonts_header is not None:
                    cmd += ["--include-in-header", str(fonts_header)]
                # Last, so a document's own header-includes can override
                # anything the shared preamble/pdf-meta files above defined
                # (Pandoc would otherwise drop it entirely; see
                # document_header_file). Added whenever header_file exists,
                # not only when preamble_files is non-empty -- see
                # document_header_includes()'s own docstring.
                if header_file is not None:
                    cmd += ["--include-in-header", str(header_file)]
                cmd += core.document_filter_args(all_inputs or md_path, md_path, metadata_files, no_auto, csv_filter, pandoc_options,
                                            flat_pictures=output.parent / f"{output.stem}_files" if flat_markdown else None,
                                            preamble=list(preamble_files or []) if flat_markdown else None,
                                            flat_text=target_format == "txt",
                                            citation_engine=citation_engine if is_tex_target else None,
                                            named_reader=from_format)
                cmd += before_citeproc + core.select_filter_args(selection)
                if any_citations and not numbered_source and "--citeproc" not in pandoc_options and not core.CITEPROC_DISABLED:
                    if (is_tex_target and citation_engine in ("natbib", "biblatex")
                            and "--natbib" not in pandoc_options and "--biblatex" not in pandoc_options):
                        # No compile-and-rerun concern here the way the PDF path's
                        # convert_via_native_bibliography() has -- this branch never
                        # runs an engine at all, it just hands the caller a .tex to
                        # compile (and resolve its own bibliography in) themselves.
                        cmd.append(f"--{citation_engine}")
                    else:
                        cmd.append("--citeproc")
                cmd += core.csl_args(
                    [md_path], metadata_files, pandoc_options, no_auto, citeproc="--citeproc" in cmd or "--citeproc" in pandoc_options)
                cmd += core.fullcite_post_args(all_inputs or md_path, metadata_files, cmd, pandoc_options)   # after citeproc
                cmd += core.bibliography_indent_args(all_inputs or md_path, metadata_files, cmd, pandoc_options, target_format)
                # pandoc_options after the citation-engine flag above: a
                # caller-supplied --lua-filter/--filter needs resolved
                # citations already in the AST (same invariant as the
                # auto-discovered lua_filters below).
                if target_format in core.HTML_TARGETS:
                    cmd += core.html_pandoc_args(md_path, metadata_files, pandoc_options, self_contained, note)
                cmd += office_arguments
                cmd += pandoc_options
                apply_citation_aliases(cmd, md_path, metadata_files)
                cmd += core.bibliography_spacing_args(md_path, metadata_files, cmd)
                if is_tex_target:
                    cmd += core.tex_package_args([md_path, *parts_inputs], no_auto, note)
                    cmd += core.paragraph_spacing_latex_args([md_path, *parts_inputs], metadata_files)
                    cmd += core.css_heading_args([md_path, *parts_inputs], css_meta, variables, no_auto, note)
                    cmd += core.cover_header_args([md_path, *parts_inputs], css_meta)
                    cmd += core.markup_header_args([md_path, *parts_inputs], css_meta, cmd)
                    cmd += core.slide_notes_args([md_path, *parts_inputs], metadata_files, target_format == "beamer")
                if fonts_filter is not None:
                    cmd += ["--lua-filter", str(fonts_filter)]  # before table-width: it renders cells to LaTeX
                if is_tex_target and tablewidth_auto:
                    cmd += core.width_filter_args(width_filter, command=cmd, cwd=pandoc_cwd)
                cmd += core.cellalign_args([md_path, *parts_inputs], metadata_files)
                if target_format in core.OFFICE_REFERENCE_EXTENSIONS:
                    cmd += core.image_filter_args(no_auto, [md_path, *parts_inputs], metadata_files, format="png")
                if is_tex_target:
                    cmd += core.tblr_header_args([md_path, *parts_inputs], metadata_files)
                    cmd += core.code_filter_args(no_auto, [md_path, *parts_inputs], metadata_files) + core.image_filter_args(no_auto, [md_path, *parts_inputs], metadata_files)
                    cmd += page_numbers.arguments(target_format, md_path, metadata_files)
                    core.hoist_code_header(cmd)
                    core.keep_header_includes(cmd, [md_path], metadata_files, pandoc_options, header_file)
                for lua_filter in lua_filters:
                    cmd += ["--lua-filter", str(lua_filter)]
                cmd += office_arguments.filter_arguments
                cmd += core.chem_filter_args(list(all_inputs or [md_path]), metadata_files,
                                        list(preamble_files or ([] if core.discovery_disabled(no_auto, "preamble")
                                                                else core.find_preambles(md_path.parent, md_path.stem, []))),
                                        target_format, bool(office_arguments.filter_arguments), no_auto)
                cmd += core.deferred("pdfmd_filters.hidden", "finish_args")()
                cmd += core.paragraph_spacing_typst_args(md_path, metadata_files, target_format)
                if target_format == "typst":
                    cmd += page_numbers.arguments(target_format, md_path, metadata_files)
                cmd += core.typst_filter_args(target_format, cmd, pandoc_cwd, document=md_path,
                                               metadata_files=metadata_files, no_auto=no_auto)
                cmd += figure_fit.arguments(target_format, md_path, metadata_files)
                cmd += properties_args
                if target_format == "epub" and core.EBOOK_MATH.get("mode") == "text":
                    cmd += core.ebook_filter_args()                          # a Calibre ebook with no math: after \ce is converted
                if flat_target:
                    cmd += core.flat_filter_args(flat, target_format)       # last: it sees what every other filter made
                if is_tex_target:
                    cmd += core.deferred("pdfmd_bibliography", "native_path_args")(cmd)
                ascii_scratch = tempfile.TemporaryDirectory(prefix="pdfmd-ascii-") if ascii_on else None
                try:
                    ascii_missing_mode = core.ascii_missing(md_path, metadata_files) if ascii_on else None
                    if ascii_scratch is not None:
                        cmd += core.ascii_filter_args(Path(ascii_scratch.name), ascii_missing_mode,
                                                 smart=target_format in ("markdown", "commonmark_x", "txt", "plain"))     # after those
                    from pdfmd_tables.measure import prepare
                    cmd = prepare(cmd, target_format, [md_path, *parts_inputs], metadata_files, pandoc_cwd,
                                  verbose, enabled=tablewidth_auto, export=True, state=measurement_state)
                    if office_arguments.filter_arguments:
                        result = core.run_office_pandoc(cmd, output, office_arguments, pandoc_cwd, verbose, debug)
                    else:
                        cmd = core.headers_as_metadata(cmd)
                        core.log_cmd(cmd, pandoc_cwd, verbose)
                        result = pandoc_run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=pandoc_cwd,
                                                env=core.tex_search_env(md_path.parent, pandoc_cwd, md_path) if flat_markdown else None)
                    ascii_problem = (core.ascii_finish(output, Path(ascii_scratch.name), ascii_missing_mode, md_path)
                                     if ascii_scratch is not None and result.returncode == 0 else None)
                    if ansi_json is not None and result.returncode == 0:
                        ascii_problem = core.ansi_finish(ansi_json, output, md_path, verbose)
                finally:
                    if ascii_scratch is not None:
                        ascii_scratch.cleanup()
                    if ansi_scratch is not None:
                        ansi_scratch.cleanup()
                core.office_finish(office_arguments, md_path, verbose)
            if result.returncode == 0 and not ascii_problem:
                core.stamp_build(partial, skip_stamp, md_path, metadata_files, preamble_files or [], stamp_overrides, output, verbose)
            flush_summary()
            return md_path, result.returncode == 0 and not ascii_problem, ascii_problem or result.stderr[-3000:]

        document_font = core.has_mainfont(md_path, variables, metadata_files)
        explicit_font = document_font or bool(font)
        mainfont_auto = not core.auto_disabled(no_auto, "mainfont")
        tablewidth_auto = not core.auto_disabled(no_auto, "tablewidth")
        geometry_needed = (not presentation and not core.auto_disabled(no_auto, "margin")
                          and not core.has_geometry(md_path, variables, metadata_files, preamble_files or []))
        if geometry_needed:
            note("MARGIN", f"{md_path}: no geometry/margin set; "
                          f"using geometry:margin={core.DEFAULT_MARGIN} on LaTeX-family engines")
        margin_options = (None if core.auto_disabled(no_auto, "margin")
                         else core.frontmatter_margin_geometry_options(md_path, variables, metadata_files))
        if margin_options:
            note("MARGIN", f"{md_path}: margin: isn't a Pandoc variable LaTeX-family engines "
                          f"read (geometry: is) -- using geometry:{','.join(margin_options)}")
        monofont_needed = (not core.auto_disabled(no_auto, "monofont")
                          and any_code_spans
                          and not core.has_monofont(md_path, variables, metadata_files))
        if monofont_needed:
            note("MONOFONT", f"{md_path}: has code but no monofont set; "
                            f"using {core.default_monofont()} on LaTeX-family engines")
        pagesize_typo = (None if core.auto_disabled(no_auto, "papersize")
                         else core.pagesize_typo_value(md_path, variables))
        if pagesize_typo:
            note("PAPERSIZE", f"{md_path}: pagesize: {pagesize_typo!r} is not a Pandoc variable "
                              f"(papersize: is) -- using papersize={pagesize_typo} on LaTeX-family "
                              "engines. Set papersize: yourself, or --no-auto papersize, to silence "
                              "this and keep the Letter default")

        citation_engine = (None if core.auto_disabled(no_auto, "citationengine")
                           else core.frontmatter_citation_engine(md_path, metadata_files))
        if citation_engine is not None and citation_engine not in core.CITATION_ENGINES:
            raise SystemExit(f"{md_path}: unknown pdfmd-options.citation-engine value "
                             f"{citation_engine!r}. Valid: {', '.join(sorted(core.CITATION_ENGINES))}")
        if citation_engine in ("natbib", "biblatex") and any_citations:
            if not any(engine in core.LATEX_ENGINES for engine in engines):
                emit("warning", None, f"WARN  {md_path}: pdfmd-options.citation-engine: {citation_engine} needs a "
                      "LaTeX-family engine, but none is available in this fallback chain; "
                      "using --citeproc instead.", file=sys.stderr)
            else:
                ok, reason = core.convert_via_native_bibliography(
                    md_path, output, effective_from, metadata_files, variables, pandoc_options,
                    lua_filters, preamble_files or [], title_source, pdf_meta_snippet_text,
                    citation_engine, presentation, slide_level, shift_heading, font, document_font,
                    mainfont_auto, geometry_needed, monofont_needed, tablewidth_auto, width_filter,
                    csv_filter, no_auto, engines, keep_aux, verbose, debug, named_reader=from_format,
                    before_citeproc=before_citeproc)
                # Pre-existing gap, closed here rather than left (2026-09-21):
                # this branch never called stamp_after_success at all, so a
                # citation-engine: natbib/biblatex document got neither the
                # .md BUILD NOTES stamp nor a PDF-metadata one -- every other
                # success path in this function does call it.
                if ok:
                    core.stamp_build(partial, skip_stamp, md_path, metadata_files, preamble_files or [],
                                        stamp_overrides, output, verbose)
                flush_summary()
                return md_path, ok, reason[-3000:]

        result = None
        failed_families: set[str] = set()
        failed_engines: list[str] = []
        for engine_index, engine in enumerate(engines):
            family = core.ENGINE_FAMILY.get(engine, engine)
            if family in failed_families:
                print(f"SKIP  {md_path}: {engine} shares the {family} engine with an earlier "
                      f"failure; skipping", file=sys.stderr)
                continue
            if engine == "typst" and pdfmd_install.typst_too_old():         # an automatic chain gets here (v3.33.62)
                print(f"SKIP  {md_path}: {pdfmd_install.typst_too_old()}", file=sys.stderr)
                continue
            if engine == "soffice":
                # Not a real Pandoc --pdf-engine -- see convert_via_soffice_bridge's
                # own docstring for why this is special-cased here instead.
                ok, reason = core.convert_via_soffice_bridge(md_path, output, effective_from, metadata_files,
                                                        variables, pandoc_options, lua_filters, csv_filter,
                                                        no_auto, verbose,
                                                        labels="auto" if engines == ["soffice"] else "off",
                                                        title_source=title_source, part_files=part_files,
                                                        partial=partial, selection=selection, named_reader=from_format,
                                                        before_citeproc=before_citeproc, reference_args=reference_args)
                result = subprocess.CompletedProcess(args=["soffice"], returncode=0 if ok else 1,
                                                     stdout="", stderr="" if ok else reason)
                if ok:
                    emit("verbose", "SOFFICE", f"AUTO SOFFICE  {md_path}: rendered via Pandoc -> .docx -> soffice "
                          "(last-resort fallback)", shown=verbose)
                    core.record_engine(engine, failed_engines)
                    break
                failed_families.add(family)
                failed_engines.append(engine)
                remaining = [e for e in engines[engine_index + 1:] if core.ENGINE_FAMILY.get(e, e) not in failed_families
                             and not (e == "typst" and pdfmd_install.typst_too_old())]
                core.report_engine_failure(str(md_path), engine, result, remaining, debug)
                continue
            with core.prepared_latex_inputs([title_source, *core.pandoc_metadata_order(metadata_files)], engine in core.LATEX_ENGINES,
                                       typst_engine=(engine == "typst"), named_reader=from_format,
                                       effective_reader=effective_from) as prepared, \
                    core.document_header_file(md_path, (bool(preamble_files) or core.has_embedded_preamble(md_path) or bool(pdf_meta_snippet_text))
                                         and engine in core.LATEX_ENGINES, metadata_files, no_auto) as header_file, \
                    core.pdf_metadata_header_file(pdf_meta_snippet_text if engine in core.LATEX_ENGINES else None) as pdf_meta_file:
                source, *prepared_metadata = prepared

                def run(selected_font: str | None, fallback: bool = False, plain: bool = False):
                    with core.script_fallback([md_path, *parts_inputs], metadata_files, variables, preamble_files or [],
                                         selected_font, engine,
                                         no_auto if not plain or no_auto == [] else [*(no_auto or []), "unicode"],
                                         note) as (fonts_header, fonts_filter), \
                            core.managed_fonts_css(engine) as fonts_css:
                        return run_command(selected_font, fallback, fonts_header or fonts_css, fonts_filter)

                def run_command(selected_font: str | None, fallback: bool, fonts_header, fonts_filter):
                    cmd = ["pandoc", str(source), *map(str, part_files), "-o", str(output), "--pdf-engine=" + engine]
                    if engine == "typst" and core.managed_index() is not None and core.managed_index().faces:
                        cmd.append(f"--pdf-engine-opt=--font-path={core.fonts_directory()}")
                    if engine == "tectonic":                      # it reads no TEXINPUTS: the kits' folders by its own option
                        cmd += [f"--pdf-engine-opt=-Zsearch-path={folder}" for folder in core.tectonic_search_folders(md_path)]
                    if engine == "prince":                        # it names only the page's first author (v3.33.66)
                        cmd += core.prince_author_options(md_path, metadata_files, variables)
                    if effective_from:
                        cmd += ["-f", effective_from]
                    for metadata in prepared_metadata:
                        cmd += ["--metadata-file", str(metadata)]
                    cmd += reference_args
                    if partial:
                        cmd += core.PARTIAL_METADATA
                    cmd += core.table_keep_metadata(md_path, metadata_files)
                    pandoc_cwd = core.pandoc_working_directory(core.metadata_cwd(metadata_files, md_path.parent))
                    cmd += core.resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
                    if presentation:
                        cmd += ["-t", "beamer"]
                        if slide_level is not None:
                            cmd += ["--slide-level=" + str(slide_level)]
                    if engine == "typst" and core.UNICODE_CODE_FONTS and not any(
                            variable.startswith("codefont=") for variable in variables):
                        for family in core.UNICODE_CODE_FONTS:
                            cmd += ["-V", f"codefont={family}"]
                    if selected_font:
                        cmd += core.font_args("mainfont", selected_font, engine in core.LATEX_ENGINES)
                        cmd += core.mathfont_args(selected_font, md_path, metadata_files, variables, font or None, no_auto,
                                             engine, note)
                    elif engine in core.LATEX_ENGINES:
                        cmd += core.document_font_args([md_path, *parts_inputs], metadata_files, variables)
                    if fallback and not any(variable.startswith("mainfontfallback=") for variable in variables):
                        cmd += ["-V", f"mainfontfallback={core.fallback_font()}"]
                    if geometry_needed and engine in core.LATEX_ENGINES:
                        cmd += ["-V", f"geometry:margin={core.DEFAULT_MARGIN}"]
                    elif margin_options and engine in core.LATEX_ENGINES:
                        for margin_option in margin_options:
                            cmd += ["-V", f"geometry:{margin_option}"]
                    if monofont_needed and engine in core.LATEX_ENGINES:
                        cmd += core.font_args("monofont", core.default_monofont())
                    page_variables, page_typo = core.paper_variables(md_path, metadata_files, variables, pagesize_typo,
                                                                core.paper_kind(engine, no_auto))
                    if page_typo and engine in core.LATEX_ENGINES:
                        cmd += ["-V", f"papersize={page_typo}"]
                    for variable in page_variables:
                        cmd += ["-V", variable]
                    if engine == "typst" and not core.auto_disabled(no_auto, "papersize"):
                        typst_size = core.typst_papersize_translation(
                            page_typo or next((v.split("=", 1)[1] for v in page_variables
                                               if v.startswith("papersize=")), None)
                            or core.frontmatter_papersize_value(md_path))
                        if typst_size:
                            note("PAPERSIZE", f"{md_path}: translating papersize for the typst "
                                              f"engine -> {typst_size} (typst doesn't accept "
                                              "Pandoc's own LaTeX-shaped paper names)")
                            cmd += ["-V", f"papersize={typst_size}"]
                    if shift_heading:
                        cmd += ["--shift-heading-level-by=-1"]
                    if preamble_files and engine in core.LATEX_ENGINES:
                        for preamble_file in preamble_files:
                            cmd += ["--include-in-header", str(preamble_file)]
                    if pdf_meta_file is not None:
                        cmd += ["--include-in-header", str(pdf_meta_file)]
                    if fonts_header is not None:
                        cmd += ["--include-in-header", str(fonts_header)]
                    # Last, so a document's own header-includes can override
                    # anything the shared preamble/pdf-meta files above
                    # defined (Pandoc would otherwise drop it entirely; see
                    # document_header_file). Added whenever header_file
                    # exists, not only when preamble_files is non-empty --
                    # see document_header_includes()'s own docstring.
                    if header_file is not None:
                        cmd += ["--include-in-header", str(header_file)]
                    cmd += core.document_filter_args(all_inputs or md_path, md_path, metadata_files, no_auto, csv_filter, pandoc_options,
                                                     named_reader=from_format)
                    cmd += before_citeproc + core.select_filter_args(selection)
                    # A CSL selected for Typst needs Pandoc's style resolver even without citations:
                    # otherwise its template gives Typst a bare filename outside Typst's search path.
                    if (any_citations or (engine == "typst" and core.document_csl([md_path], metadata_files))) \
                            and "--citeproc" not in pandoc_options and not core.CITEPROC_DISABLED:
                        cmd.append("--citeproc")
                    cmd += core.csl_args(
                        [md_path], metadata_files, pandoc_options, no_auto, citeproc="--citeproc" in cmd or "--citeproc" in pandoc_options)
                    cmd += core.fullcite_post_args(all_inputs or md_path, metadata_files, cmd, pandoc_options)   # after citeproc
                    cmd += core.bibliography_indent_args(all_inputs or md_path, metadata_files, cmd, pandoc_options, engine)
                    # pandoc_options after --citeproc, same reason as below: a
                    # caller-supplied --lua-filter/--filter needs resolved
                    # citations already in the AST. (This used to sit before
                    # the --citeproc append above, which silently broke any
                    # citeproc-dependent filter passed via extra CLI args --
                    # e.g. `--lua-filter=some.lua` landed ahead of --citeproc
                    # on the actual pandoc command line. Confirmed via
                    # --verbose CMD output before this fix.)
                    cmd += pandoc_options
                    apply_citation_aliases(cmd, md_path, metadata_files)
                    cmd += core.bibliography_spacing_args(md_path, metadata_files, cmd)
                    if engine in core.LATEX_ENGINES:
                        cmd += core.tex_package_args([md_path, *parts_inputs], no_auto, note)
                        cmd += core.paragraph_spacing_latex_args([md_path, *parts_inputs], metadata_files)
                        cmd += core.css_heading_args([md_path, *parts_inputs], css_meta, variables, no_auto, note)
                        cmd += core.cover_header_args([md_path, *parts_inputs], css_meta)
                        cmd += core.markup_header_args([md_path, *parts_inputs], css_meta, cmd)
                        cmd += core.slide_notes_args([md_path, *parts_inputs], metadata_files, bool(presentation))
                    # Lua filters go last: pandoc applies --citeproc and filters in
                    # command-line order, and a filter that renders cell contents to
                    # LaTeX needs the citations already resolved. csv-table has to
                    # come before table-width so a CSV-generated table gets the same
                    # width-balancing pass a hand-written one would.
                    if fonts_filter is not None:
                        cmd += ["--lua-filter", str(fonts_filter)]  # before table-width: it renders cells to LaTeX
                    if tablewidth_auto and engine in core.LATEX_ENGINES:
                        cmd += core.width_filter_args(width_filter, command=cmd, cwd=pandoc_cwd)
                    if tablewidth_auto and engine == "typst":
                        from pdfmd_tables.measure import requested
                        if requested([md_path, *parts_inputs], metadata_files):
                            cmd += core.width_filter_args(width_filter, command=cmd, cwd=pandoc_cwd)
                    cmd += core.cellalign_args([md_path, *parts_inputs], metadata_files)
                    if engine in core.LATEX_ENGINES:
                        cmd += core.tblr_header_args([md_path, *parts_inputs], metadata_files)
                        cmd += core.code_filter_args(no_auto, [md_path, *parts_inputs], metadata_files) + core.image_filter_args(no_auto, [md_path, *parts_inputs], metadata_files)
                        cmd += page_numbers.arguments(engine, md_path, metadata_files)
                        core.hoist_code_header(cmd)
                        core.keep_header_includes(cmd, [md_path], metadata_files, pandoc_options, header_file)
                    for lua_filter in lua_filters:
                        cmd += ["--lua-filter", str(lua_filter)]
                    # last of all, after the LaTeX filter below too: a reference it makes to a figure Typst has no
                    # label for is a link Typst would stop on; WeasyPrint's math is typeset once its \ce is converted
                    cmd += core.paragraph_spacing_typst_args(md_path, metadata_files, engine)
                    last_filters = core.deferred("pdfmd_filters.hidden", "finish_args")()
                    if engine == "typst":
                        cmd += page_numbers.arguments(engine, md_path, metadata_files)
                    last_filters += core.typst_filter_args(engine, cmd, pandoc_cwd, document=md_path,
                                                          metadata_files=metadata_files, no_auto=no_auto) + core.weasyprint_math_args(
                        engine, pandoc_options,
                        selected_font or core.document_font_setting("mainfont", [md_path, *parts_inputs], metadata_files, variables),
                        no_auto)
                    last_filters += figure_fit.arguments("beamer" if presentation else engine, md_path, metadata_files)
                    last_filters += properties_args
                    def measure_command(command):
                        from pdfmd_tables.measure import prepare
                        return prepare(command, engine, [md_path, *parts_inputs], metadata_files, pandoc_cwd,
                                       verbose, enabled=tablewidth_auto, state=measurement_state)

                    page_options = lambda: (core.browser_page_css(md_path, metadata_files, variables) if engine in core.BROWSER_ENGINES
                                            else core.calibre_page_options(md_path, metadata_files, variables))
                    if engine == "calibre" or engine in core.BROWSER_ENGINES or (engine in ("typst", "weasyprint") and core.office_fallback_wanted(
                            md_path, metadata_files, failed_families, "typst" if engine == "typst" else "html",
                            [md_path, *parts_inputs])):
                        # LaTeX failed, or the document has LaTeX this writer would drop (Calibre always, like
                        # LibreOffice): it becomes native or a picture instead of nothing. References take LaTeX's
                        # numbers as in a Word file (`office: {labels}`), unless LaTeX is what failed.
                        with core.office_reference(md_path, metadata_files, variables, "typst" if engine == "typst" else "html",
                                              output, pandoc_options, no_auto, note,
                                              labels="off" if core.latex_failed(failed_families) else None,
                                              force_filter=True) as office_arguments:
                            if office_arguments.filter_arguments:
                                cmd += office_arguments.filter_arguments + last_filters
                                answer = run_engine_command(
                                    cmd, engine, output,
                                    lambda command, target: core.run_office_pandoc(command, target, office_arguments,
                                                                              pandoc_cwd, verbose, prepare_command=measure_command),
                                    page_options, verbose, numbered=page_numbers.enabled(md_path, metadata_files))
                                core.office_finish(office_arguments, md_path, verbose)
                                return answer
                    cmd += last_filters

                    def run_pandoc(command: list[str], target: Path):
                        command = measure_command(command)
                        from pdfmd_tex.references import pandoc_sources

                        sources = (pandoc_sources(command, md_path.parent, pandoc_cwd, tex_path_warnings)
                                   if engine in core.LATEX_ENGINES else contextlib.nullcontext(command))
                        with sources as prepared_command:
                            prepared_command = core.headers_as_metadata(prepared_command)
                            core.log_cmd(prepared_command, pandoc_cwd, verbose)
                            return pandoc_run(prepared_command, capture_output=True, encoding="utf-8", errors="replace",
                                              cwd=pandoc_cwd, env=core.tex_search_env(md_path.parent, pandoc_cwd, md_path))
                    return run_engine_command(cmd, engine, output, run_pandoc, page_options, verbose,
                                              numbered=page_numbers.enabled(md_path, metadata_files))

                first_font = core.mainfont_choice([md_path, *parts_inputs], metadata_files, variables, font,
                                             document_font, mainfont_auto, no_auto, note)
                # fallback=False, not fallback=document_font: Pandoc's own
                # mainfontfallback mechanism is the one PREFERRED_FONT's
                # comment (and the is_tex_target path's own comment above)
                # already document as crashing lualatex outright in this
                # environment -- that's exactly why a document with its own
                # mainfont gets no swap-retry (nothing to safely swap to)
                # AND, as of 2026-09-20, no auto mainfontfallback either. A
                # document that wants one can still set mainfontfallback:
                # itself in its own front matter (or a linked metadata file)
                # -- that routes through Pandoc's normal metadata merge, not
                # this -V injection, so it never hits the crash. Confirmed
                # directly: a document with mainfont: set of its own crashed
                # lualatex on this line's old `fallback=document_font` even
                # though nothing was actually missing a glyph yet.
                result = run(first_font, fallback=False)
                if result.returncode != 0 and "pdfmdf" in result.stdout + result.stderr:
                    # a font pdfmd picked for another script would not load: build without them
                    emit("warning", None, f"WARN  {md_path}: the fonts pdfmd chose for other scripts failed under {engine}; "
                          "building without them (--verbose shows which)", file=sys.stderr)
                    result = run(first_font, fallback=False, plain=True)
                combined_output = figure_fit.without_diagnostics(result.stdout + "\n" + result.stderr)
                if (mainfont_auto and not explicit_font and result.returncode == 0
                        and core.missing_glyph_warning(combined_output)):
                    retry_font = font or core.fallback_font()
                    emit("warning", None, core.retry_font_note(md_path, first_font or PREFERRED_FONT, retry_font,
                                          core.missing_glyph_codes(combined_output)), file=sys.stderr)
                    result = run(retry_font)
            if result.returncode == 0:
                figure_fit.diagnostics(result.stdout + "\n" + result.stderr, md_path)
                result.stderr = figure_fit.without_diagnostics(result.stderr)
                core.record_engine(engine, failed_engines)
                break
            failed_families.add(family)
            failed_engines.append(engine)
            if core.pandoc_refused_command(result):      # an option Pandoc does not take: every engine would fail on it (v3.33.44)
                break
            remaining = [e for e in engines[engine_index + 1:] if core.ENGINE_FAMILY.get(e, e) not in failed_families
                         and not (e == "typst" and pdfmd_install.typst_too_old())]
            if core.chain_engine_failed(str(md_path), engine, result, remaining, debug):     # engine-fallback stops here
                break
        if result is None:
            # Every engine was skipped: each shares an engine with one that failed already.
            return md_path, False, ("no PDF engine could build this. Install a LaTeX or Typst engine "
                                    "(pdfmd --install typst) or use --to html")
        if result.returncode == 0:
            core.stamp_build(partial, skip_stamp, md_path, metadata_files, preamble_files or [], stamp_overrides, output, verbose)
        flush_summary()
        return md_path, result.returncode == 0, result.stderr[-3000:]


def finish_build(result, seen: list[str], md_path: Path, metadata_files: list[Path]) -> "Built":  # noqa: F821 -- quoted, never evaluated: pdfmd.py's Built
    """Attach the engine that built the file and apply --strict: a build that printed a warning (or about which Pandoc
    warned) fails, its output kept."""
    # a repair is a warning too (lib/pdfmd_tex/repair.py); the run's TeX cache counts only for a build that TeX made
    run_wide = core.BUILD["repaired_run"] if core.BUILD["engine"] in core.LATEX_ENGINES else []
    problems = [*seen, *run_wide, *core.BUILD["repaired"]]
    if result[1] and len(result) > 2 and isinstance(result[2], str):
        known = {line.strip() for line in problems}
        problems += [line for line in re.findall(r"(?m)^(?:\[WARNING\]|WARN\b).*$", result[2]) if line.strip() not in known]
    if result[1] and problems and core.resolve_strict(md_path, metadata_files):
        result = (result[0], False, core.strict_message(problems))
    built = core.Built(result, core.BUILD["engine"], core.BUILD["failed"], core.BUILD["output"])
    built.stopped = core.chain_stopped()
    return core.attach_time(built, md_path, metadata_files)


def set_soffice_limit(md_path: Path, metadata_files: list[Path]) -> None:
    """The `soffice-timeout` of the document about to be built: its `pdfmd-options`, its metadata files', the config's."""
    value = (core.first_pdfmd_option(md_path, metadata_files, "soffice-timeout") if md_path.suffix.lower() in (".md", ".markdown")
             else core.config_options().get("soffice-timeout"))
    core.SOFFICE_TIMEOUT_NOW = core.soffice_timeout_from(value)


@scoped
def convert_one(md_path: Path, *args, **kwargs) -> "Built":  # noqa: F821 -- quoted, never evaluated: pdfmd.py's Built
    """_convert_one_recorded, with the engine that built the file and --strict (see the section above)."""
    core.BUILD["engine"], core.BUILD["failed"], core.BUILD["output"], core.BUILD["sources"], core.BUILD["partial"], core.BUILD["root"] = None, [], None, [], None, None
    core.BUILD.pop("bibliography-discovery", None)
    core.BUILD.pop("bibliography-warnings", None)
    history_record = core.load_package("pdfmd_history.record")
    history_record.begin_history()
    core.begin_timer()
    core.BUILD["tried"], core.BUILD["chain"], core.BUILD["repaired"] = [], None, []
    bound = inspect.signature(_convert_one_recorded).bind(md_path, *args, **kwargs).arguments
    given = bound.get("metadata_file")
    metadata_files = given if isinstance(given, list) else ([given] if given else [])
    core.deferred("pdfmd_engines.memory", "set_limit")(md_path, metadata_files)
    set_soffice_limit(md_path, metadata_files)
    recorder = core.load_package("pdfmd_buildinfo.build").BuildRecorder.start(md_path, metadata_files)
    try:
        with core.warning_capture() as seen:
            pdfmd_cache.check_location(md_path, metadata_files,
                                       False if bound.get("target_format") in core.HTML_TARGETS else bound.get("cache_cli"))
            pdfmd_native.warn_nameless_authors(md_path, metadata_files)
            result = _convert_one_recorded(md_path, *args, **kwargs)
            if result[1]:
                core.load_package("pdfmd_shrink").shrink_output(core.BUILD["output"], md_path, metadata_files, bool(bound.get("verbose")))
                core.check_output_budget(core.BUILD["output"], core.BUILD["sources"] or [md_path], md_path, metadata_files)
                history_record.reader_warnings()
        built = finish_build(result, seen, md_path, metadata_files)
        history_record.finish_history(built[1])
    except BaseException as error:
        history_record.finish_history(False)
        where = recorder.finish(None, core.failure_text(error)) if recorder else None
        if where:
            print(f"      full record: {core.under_home(where)}", file=sys.stderr)
        raise
    if recorder:
        built.record_path = recorder.finish(built)
    return built


def make_embed_plan(md_path: Path, metadata_files: list[Path], preamble_files: list[Path] | None,
                    no_auto: list[str] | None, request: "EmbedRequest | None") -> "EmbedPlan | None":  # noqa: F821 -- quoted, never evaluated: pdfmd.py's EmbedRequest, pdfmd_assemble's EmbedPlan
    """What --embed-metadata folds into ``md_path``'s assembled text, or None."""
    resolved = core.resolve_embed(md_path, metadata_files, request)
    if resolved is None:
        return None
    kinds, lua_mode = resolved
    discovered_lua = ([] if (core.discovery_disabled(no_auto, "lua") or "lua" not in kinds)
                      else core.find_lua_filters(md_path, metadata_files, no_auto))
    if not core.auto_disabled(no_auto, "lua") and "lua" in kinds:
        for extra_filter in core.frontmatter_extra_lua_filters(md_path, metadata_files):
            if extra_filter not in discovered_lua:
                discovered_lua.append(extra_filter)
    plan = core.EmbedPlan(kinds, lua_mode, list(metadata_files), core.kit_embedded_preambles(md_path, metadata_files, preamble_files), discovered_lua)
    kits_here = core.active_kits(md_path, metadata_files, no_auto)
    # What a kit brought (defaults, preamble, Lua filter) is now in the source: a rebuild must not choose the kit again, where it
    # would be found twice over (the stored copies and the kit's), or not found at all. `kit: none` in the source's own
    # pdfmd-options replaces every `kit:` below it; only a part left out of the embedding keeps the kit chosen.
    plan.kit_none = bool(kits_here) and {"metadata", "preamble"} <= kinds and (
        not any(item.kit.lua for item in kits_here) or ("lua" in kinds and lua_mode in ("embed", "apply")))
    if "hst" in kinds:
        found = core.history_file(md_path, metadata_files, existing=True)
        plan.hst_file = found if found.is_file() else None
    return plan


def _convert_one_recorded(md_path: Path, out_dir: Path | None, presentation: bool, font: str,
                engines: list[str], variables: list[str], slide_level: int | None,
                pandoc_options: list[str],
                metadata_file: Path | list[Path] | None = None,
                output_file: Path | None = None,
                preamble_files: list[Path] | None = None,
                target_format: str = "pdf",
                from_format: str | None = None,
                no_auto: list[str] | None = None,
                verbose: bool = False,
                debug: bool = False,
                stamp_overrides: dict | None = None,
                keep_aux: bool = False,
                backup: bool | None = None,
                backup_format: str | None = None,
                extra_inputs: list[Path] | None = None,
                partial: bool = False,
                cache_cli: bool | None = None,
                parts_root: Path | None = None,
                embed: "EmbedRequest | None" = None,  # noqa: F821 -- quoted, never evaluated: pdfmd.py's EmbedRequest
                trust_embedded: bool = False,
                self_contained: bool | None = None,
                source_override: tuple[str, bool] | None = None,
                all_parts: list[Path] | None = None,
                full_override: str | None = None,
                calc_text_override: str | None = None, output_resolved: bool = False) -> tuple[Path, bool, str]:
    """_convert_one, plus the --backup snapshot on success -- wrapped here
    rather than threaded into each of _convert_one's own success returns
    (Pandoc, natbib/biblatex, direct .tex, office), so every one of them
    gets it, including any added later.
    """
    core.LAST_SCANNED, core.LAST_EXACT, core.LAST_WHOLE, core.LAST_SKIPPED = 0, False, False, 0
    metadata_list = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
    scratch = None
    label_scan = None
    selection = None
    pandoc_inputs = extra_inputs
    if partial or source_override is not None:
        seed_mode = core.seed_labels_mode(md_path, metadata_list)
        if core.label_scan_wanted(seed_mode, target_format, engines, presentation, md_path, True, parts_root is not None,
                             [source_override[0]] if source_override is not None else []):
            scratch = tempfile.TemporaryDirectory(prefix="pdfmd-labels-")
            label_scan = core.build_label_scan(md_path, Path(scratch.name), font, engines, variables, slide_level,
                                          pandoc_options, metadata_file, preamble_files, from_format, no_auto,
                                          stamp_overrides or {}, trust_embedded, list(all_parts or []), parts_root,
                                          verbose, draft=(seed_mode == "draft"))
            core.LAST_SCANNED = label_scan.labels if label_scan is not None else 0
            core.LAST_EXACT = bool(label_scan is not None and label_scan.exact)
            core.LAST_SKIPPED = label_scan.skipped if label_scan is not None else 0
        elif core.select_wanted(seed_mode, target_format, engines, presentation, md_path):
            # HTML, Word, OpenDocument, Typst: no LaTeX to seed. Number the whole document, then keep the part(s) asked for.
            if parts_root is not None and all_parts and extra_inputs:
                selection = set(extra_inputs)
                pandoc_inputs = list(all_parts)
                core.LAST_WHOLE = True
            elif source_override is not None and full_override is not None:
                selection = True
                source_override = (full_override, source_override[1])
                core.LAST_WHOLE = True
    calc_scratch = None
    calc_names = calc_below_names = 0
    calc_from = calc_below_from = ""
    if (partial or source_override is not None) and selection is None and not presentation:
        # The names the calculator needs from the rest of the document (a `mean_A`{=2dp} of part 60, defined in part 50, or the
        # `y` that part 20 prints, defined in part 30): the nearest definition above, else the first below, as in the full build.
        before = []
        after = []
        if all_parts and extra_inputs:
            built = [all_parts.index(part) for part in extra_inputs if part in all_parts]
            before = [part for part in all_parts[:max(built)] if part not in extra_inputs] if built else []
            after = [part for part in all_parts[max(built) + 1:] if part not in extra_inputs] if built else []
            calc_from = core.parts_range_text(before)
            calc_below_from = core.parts_range_text(after)
        calc_wanted = bool(before) or bool(after) or bool(calc_text_override and calc_text_override.strip())
        if calc_wanted and core.seed_calc_mode(md_path, metadata_list) != "off":
            calc_scratch = tempfile.TemporaryDirectory(prefix="pdfmd-calc-")
            if calc_text_override is None:
                inputs = core.calc_marked_inputs(md_path, all_parts or [], list(extra_inputs or []), Path(calc_scratch.name))
            else:
                text_whole = Path(calc_scratch.name) / "whole.md"
                text_whole.write_text(calc_text_override, encoding="utf-8")
                inputs = [text_whole]
                calc_from, calc_below_from = "the sections above it", "the sections below it"
            seed_file, calc_names, below_file, calc_below_names = core.build_calc_seed(
                md_path, metadata_list, [md_path, *(extra_inputs or [])], inputs, Path(calc_scratch.name), from_format, verbose)
            core.CALC_SEED, core.CALC_BELOW = seed_file, below_file
            if seed_file is not None and seed_file.suffix == ".json":
                calc = core.load_package("pdfmd_calc")
                if calc_text_override is not None and source_override is not None:
                    source_override = (calc.context_sections(calc_text_override), source_override[1])
                elif extra_inputs:
                    pandoc_inputs = calc.context_inputs(list(extra_inputs), Path(calc_scratch.name))
    export_target = core.calc_export_file(md_path, metadata_list) if target_format != core.ASSEMBLED_FORMAT else None
    export_scratch = None
    if export_target is not None:
        if (partial or source_override is not None) and selection is None and core.CALC_SEED is None:
            emit("note", None, f"NOTE  calc: {core.display_path(export_target)} is not written for a part built alone with no names from the parts "
                  "above it (seed-calc is off, or nothing stands above it)", file=sys.stderr)
            export_target = None
        else:
            export_scratch = tempfile.TemporaryDirectory(prefix="pdfmd-calc-export-")
            core.CALC_DUMP = Path(export_scratch.name) / "names.tsv"
    if not output_resolved:
        planned = output_file or core.load_package("pdfmd_routing.output").planned(md_path, out_dir, target_format)
        output_file = core.load_package("pdfmd_routing.output").protected(md_path, planned, target_format, metadata_list)
    from pdfmd_crop.build import prepare as prepare_crop
    try:
        with prepare_crop(md_path, output_file, metadata_list, target_format, verbose,
                          variables=variables, report=bool(core.REPORT_BUILD.get("files"))) as crop:
            result = _convert_one(md_path, out_dir, presentation, font, engines, variables, slide_level,
                                  pandoc_options, metadata_file, output_file, preamble_files,
                                  target_format=target_format, from_format=from_format, no_auto=no_auto,
                                  verbose=verbose, debug=debug, stamp_overrides=stamp_overrides,
                                  keep_aux=keep_aux, extra_inputs=pandoc_inputs, partial=partial,
                                  cache_cli=cache_cli, full_scaffold=(md_path if extra_inputs else None),
                                  parts_root=parts_root, embed=embed, trust_embedded=trust_embedded,
                                  self_contained=self_contained, source_override=source_override,
                                  label_scan=label_scan, selection=selection, skip_stamp=crop is not None)
            if result[1] and crop is not None:
                if source_override is None and not partial:
                    core.polish_pdf(output_file, [md_path, *(extra_inputs or [])], verbose)
                if problem := crop():
                    return md_path, False, problem
                if md_path.suffix.lower() in core.MARKDOWN_LIKE_SUFFIXES:
                    core.stamp_build(partial, False, md_path, metadata_list, preamble_files or [],
                                     stamp_overrides or {}, output_file, verbose)
    finally:
        core.CALC_SEED = core.CALC_BELOW = None
        dump_text = ""
        if core.CALC_DUMP is not None and core.CALC_DUMP.is_file():
            dump_text = core.CALC_DUMP.read_text(encoding="utf-8", errors="replace")
        core.CALC_DUMP = None
        if export_scratch is not None:
            export_scratch.cleanup()
        if scratch is not None:
            scratch.cleanup()
        if calc_scratch is not None:
            calc_scratch.cleanup()
    if result[1] and export_target is not None and dump_text:
        try:
            written = core.write_calc_export(dump_text, export_target)
        except OSError as error:
            emit("warning", None, f"WARN  calc: could not write {core.display_path(export_target)} ({error})", file=sys.stderr)
        else:
            if written:
                print(f"CALC  {written} name{'s' if written != 1 else ''} written to {core.display_path(export_target)}")
    if result[1] and (calc_names or calc_below_names):
        taken = []
        if calc_names:
            taken.append(f"{calc_names} names taken from {calc_from}")
        if calc_below_names:
            taken.append(f"{calc_below_names} " + ("from" if taken else "names taken from") + f" {calc_below_from} (defined below)")
        emit("note", None, f"NOTE  calc: {', '.join(taken)} (evaluated, not typeset)")
    if result[1] and target_format != core.ASSEMBLED_FORMAT:
        metadata_files = (metadata_file if isinstance(metadata_file, list)
                          else ([metadata_file] if metadata_file else []))
        saved: list[Path] = []
        for backed_up in [md_path, *(extra_inputs or [])]:
            core.backup_after_success(backed_up, metadata_files, backup, verbose, backup_format, collect=saved)
        if saved:
            print(core.backup_summary(md_path, saved))
            if len(saved) > 1:
                for target in saved:
                    core.vprint(verbose, f"  BACKUP  {core.display_path(target)}")
        if target_format == "pdf":
            made_pdf = output_file or ((out_dir / f"{md_path.stem}.pdf") if out_dir else md_path.with_suffix(".pdf"))
            core.backup_pdf_after_success(md_path, made_pdf, metadata_files, backup,
                                     verbose, datetime.fromtimestamp(core.backup_sort_key(saved[0])[0]) if saved else None)
        if target_format == "pdf" and crop is None and source_override is None and not partial:
            core.polish_pdf(output_file or ((out_dir / f"{md_path.stem}.pdf") if out_dir else md_path.with_suffix(".pdf")),
                       [md_path, *(extra_inputs or [])], verbose)
        if (target_format == "pdf" and source_override is None and not partial and not presentation
                and core.resolve_hybrid(md_path, metadata_files)):
            core.hybrid_after_success(md_path, output_file or ((out_dir / f"{md_path.stem}.pdf") if out_dir
                                                           else md_path.with_suffix(".pdf")),
                                 metadata_files, variables, core.effective_no_auto(md_path, no_auto), verbose)
        if (target_format == "pdf" and source_override is None and not partial
                and md_path.suffix.lower() in (".md", ".markdown")
                and core.resolve_attach(md_path, metadata_files)):
            produced = output_file or ((out_dir / f"{md_path.stem}.pdf") if out_dir
                                       else md_path.with_suffix(".pdf"))
            core.attach_source_after_success(md_path, produced, list(extra_inputs or []), metadata_files,
                                        preamble_files, core.effective_no_auto(md_path, no_auto), verbose,
                                        report=bool(core.REPORT_BUILD), base=core.REPORT_BUILD.get("base"),
                                        named_reader=from_format, pandoc_options=pandoc_options)
        if (target_format in core.MARKDOWN_TARGETS and source_override is None and not partial
                and md_path.suffix.lower() in (".md", ".markdown")):
            keep_mode = core.resolve_keep_source(md_path, metadata_files)
            if keep_mode:
                suffix = core.output_extension_for(target_format, md_path)
                produced = output_file or ((out_dir / f"{md_path.stem}{suffix}") if out_dir
                                           else md_path.with_suffix(suffix))
                core.keep_source_after_success(md_path, produced, list(extra_inputs or []), metadata_files,
                                          preamble_files, core.effective_no_auto(md_path, no_auto), keep_mode, verbose,
                                          ascii_only=core.ASCII_CLI["on"] and target_format in core.ASCII_FORMATS,
                                          pandoc_options=pandoc_options, named_reader=from_format)
    return result


def convert_via_cache(md_path: Path, out_dir: Path | None, font: str, engines: list[str],
                      variables: list[str], slide_level: int | None, pandoc_options: list[str],
                      metadata_file: Path | list[Path] | None, output: Path,
                      preamble_files: list[Path] | None, from_format: str | None,
                      no_auto: list[str] | None, verbose: bool, debug: bool,
                      stamp_overrides: dict, keep_aux: bool, parts_inputs: list[Path],
                      partial: bool, persistent: bool, full_scaffold: Path | None,
                      parts_root: Path | None, note, flush_summary,
                      plots: bool = False,
                      trust_embedded: bool = False,
                      source_override: tuple[str, bool] | None = None,
                      label_scan: "LabelScan | None" = None, skip_stamp: bool = False) -> tuple[Path, bool, str]:  # noqa: F821 -- quoted, never evaluated: pdfmd.py's LabelScan
    """Build a PDF the cache way: Pandoc writes the .tex, pdfmd compiles it.
    See the comment above CACHE_DEFAULTS. ``persistent`` False (the natbib +
    parts case without the cache switched on) uses a scratch folder instead
    and discards it.
    """
    metadata_files = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
    cache_base = core.document_cache_root(full_scaffold or md_path, metadata_files)
    if persistent:
        core.prepare_cache_root(cache_base)
        base = core.cache_directory(full_scaffold or md_path, cache_base, note)
    else:
        base = Path(mkdtemp(prefix="pdfmd-cache-"))
    base.mkdir(parents=True, exist_ok=True)
    if persistent:
        core.write_cache_manifest(base, full_scaffold or md_path)
    stem = core.safe_stem(output.stem)
    tex_path = base / f"{stem}.tex"
    headers = list(preamble_files or [])
    own_headers: list[str] = []      # what pdfmd adds to this build only: left out of the plots' preamble
    seeded = 0
    core.LAST_SEEDED = 0
    seed_mode = core.seed_labels_mode(md_path, metadata_files)
    if persistent and parts_inputs and parts_root is not None and not (label_scan and label_scan.markers):
        defs = base / f"{stem}.pdfmd-defs.tex"
        defs.write_text(core.PARTS_MARKER_DEFS, encoding="utf-8")
        headers.append(defs)
        own_headers.append(core.PARTS_MARKER_DEFS)
    # A partial build takes its missing labels from the last full build's .aux: the
    # report's, in parts mode, or the document's own for one section or element of an
    # ordinary document (source_override), which has no parts and so no counter markers.
    seed_from = full_scaffold if parts_root is not None else (md_path if source_override is not None else None)
    if (persistent and partial and seed_from is not None and stem != core.safe_stem(seed_from.stem)
            and seed_mode in ("auto", "aux", "draft") and not (label_scan is not None and label_scan.exact)):
        # (Not when the build is named like the full one: it would overwrite the .aux it reads.)
        full_aux = base / f"{core.safe_stem(seed_from.stem)}.aux"
        seed = base / f"{stem}.seed.tex"
        seed.unlink(missing_ok=True)
        seeded = core.seed_labels_file(full_aux, seed)
        if seeded:
            core.LAST_SEEDED = seeded
            hook = base / f"{stem}.seed-hook.tex"
            hook.write_text("\\AtBeginDocument{\\InputIfFileExists{\"%s\"}{}{}}\n" % seed.as_posix(), encoding="utf-8")
            headers.append(hook)
            own_headers.append(hook.read_text(encoding="utf-8"))
            when = datetime.fromtimestamp(full_aux.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            note("CACHE", f"{md_path}: {seeded} labels from the last full build ({when}) fill in "
                          + ("references to the rest of the document" if source_override is not None
                             else "references to parts left out"))
    if label_scan is not None:
        headers.extend(label_scan.headers)          # after the .aux seed: what the last full build knew wins
        own_headers.extend(header.read_text(encoding="utf-8", errors="replace") for header in label_scan.headers)
        if label_scan.exact:
            note("LABELS", f"{md_path}: labels from a draft pass over the whole document (exact), the scan fills in the rest")
        else:
            note("LABELS", f"{md_path}: {label_scan.labels} labels counted from the sources fill in what the "
                           f"{'last full build does not know' if seeded else 'references to parts left out need'} "
                           "(approximate: a macro the document defines itself is not counted)")
    try:
        stage_build = (core.BUILD["output"], list(core.BUILD["sources"]))      # the PDF this build is for (v3.30.1)
        built = _convert_one(md_path, out_dir, False, font, engines, variables, slide_level,
                             pandoc_options, metadata_file, tex_path, headers, target_format="latex",
                             from_format=from_format, no_auto=no_auto, verbose=verbose, debug=debug,
                             stamp_overrides=stamp_overrides, keep_aux=keep_aux,
                             extra_inputs=parts_inputs, partial=partial, cache_cli=False,
                             skip_stamp=True, parts_root=parts_root,
                             part_markers=bool((persistent or (label_scan is not None and label_scan.markers))
                                               and parts_inputs),
                             trust_embedded=trust_embedded, source_override=source_override, link_output=output)
        core.BUILD["output"], core.BUILD["sources"] = stage_build[0], stage_build[1]   # the .tex stage recorded its own file
        if not built[1]:
            return built
        pandoc_cwd = core.pandoc_working_directory(core.metadata_cwd(metadata_files, md_path.parent))
        tex_env = core.tex_search_env(md_path.parent, pandoc_cwd, md_path)
        plot_dir = None
        aliases: dict[str, list[str]] = {}
        preamble_text = ""
        if plots:
            tex_text = tex_path.read_text(encoding="utf-8")
            preamble_text = core.plot_preamble(tex_text.split("\\begin{document}")[0], own_headers)
            styles = core.picture_cache_styles(preamble_text)
            sty_text = "\0".join(f"{name}\0{text}" for name, text, _ in styles)
            aliases = core.cache_aliases(styles)
            # the document's own cache folder: the aux cache's, or the one it would use when it is off
            plot_home = base if persistent else core.cache_directory(full_scaffold or md_path, cache_base, note)
            roots = [Path(os.path.abspath(pandoc_cwd)), Path(os.path.abspath(md_path.parent)), *core.user_tex_trees()]
            if engines[0] != "lualatex":
                note("CACHE", "plots: only LuaLaTeX is supported; plot cache skipped")
            elif not styles:
                note("CACHE", "plots: no package the document loads takes part in the picture cache "
                              "(its style file mentions pdfmdCacheDir); skipped")
            elif " " in str(plot_home):
                note("CACHE", "plots: the cache folder's path has a space; plot cache skipped")
            else:
                if not persistent:
                    core.prepare_cache_root(cache_base)
                    plot_home.mkdir(parents=True, exist_ok=True)
                    core.write_cache_manifest(plot_home, full_scaffold or md_path)
                plot_dir = core.plot_cache_directory(preamble_text, sty_text, "lualatex", plot_home)
                plot_dir.mkdir(parents=True, exist_ok=True)
                os.utime(plot_dir)
                core.prune_plot_directories(plot_dir)
                core.validate_plot_entries(plot_dir, verbose, roots)
                tex_path.write_text("\\def\\pdfmdCacheDir{%s/}\\def\\pdfmdCacheVersion{3}\n" % plot_dir.as_posix()
                                    + "".join("\\def\\%s{%s/}\n" % (name, plot_dir.as_posix())
                                              for name in aliases.get("dir", [])) + tex_text,
                                    encoding="utf-8")
        ok, reason = core.compile_tex_direct(tex_path, output, engines, keep_aux, verbose, debug,
                                        aux_dir=base, cwd=pandoc_cwd, env=tex_env, document_directory=md_path.parent)
        if ok and plot_dir is not None:
            requests = {}
            for suffix in (*aliases.get("requests", []), ".pdfmdreq"):
                requests.update(core.read_plot_requests(base / f"{stem}{suffix}"))
            if requests:
                started = time.time()
                done, failed = core.render_plot_requests(requests, plot_dir, preamble_text, "lualatex",
                                                    pandoc_cwd, tex_env, roots, verbose, aliases)
                if done or failed:
                    print(f"PLOTS  stored {done} plot{'s' if done != 1 else ''} for the next build "
                          f"({time.time() - started:.0f} s)" + (f"; {failed} failed (typeset inline, "
                          "nothing lost)" if failed else ""))
        if ok:
            core.stamp_build(partial, skip_stamp, md_path, metadata_files, preamble_files or [], stamp_overrides,
                                 output, verbose)
        flush_summary()
        return md_path, ok, reason[-3000:]
    finally:
        if not persistent:
            shutil.rmtree(base, ignore_errors=True)
