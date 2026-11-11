"""`pdfmd -r` / `--report` / `--book`: the files of a folder built into one document (book.pdf, book.docx ...).

Moved out of `pdfmd.py`'s `run_main()` unchanged (v3.32.13); the report is built from this one function. `core` is the
`pdfmd` module itself (the file may be running as `__main__`, so it is passed in, never imported: a second import would be
a second copy with its own state). Every helper is called through the names bound at the top of `run`."""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from pathlib import Path

from pdfmd_report import route, titles


def run(core, *,
        args, default_target, embed_request, engines,
        need_engines, pandoc_options, paths, stamp_overrides,
        target_format, variables) -> None:
    # the helpers of pdfmd.py this function calls, bound here so the body reads as it did in run_main()
    ASSEMBLED_FORMAT, AUTO_LOG = core.ASSEMBLED_FORMAT, core.AUTO_LOG
    AUTO_METADATA_DISABLED, BROWSER_ENGINES, BUILD = core.AUTO_METADATA_DISABLED, core.BROWSER_ENGINES, core.BUILD
    Built, DEFAULT_MARGIN, ENGINE_FAMILY = core.Built, core.DEFAULT_MARGIN, core.ENGINE_FAMILY
    ENGINE_GROUPS, EmbedPlan, HTML_TARGETS = core.ENGINE_GROUPS, core.EmbedPlan, core.HTML_TARGETS
    LATEX_ENGINES, TEX_STANDALONE_FORMATS = core.LATEX_ENGINES, core.TEX_STANDALONE_FORMATS
    announce_preambles, attach_source_after_success = core.announce_preambles, core.attach_source_after_success
    attach_time, auto_disabled, backup_after_success = core.attach_time, core.auto_disabled, core.backup_after_success
    begin_timer, browser_page_css = core.begin_timer, core.browser_page_css
    calibre_page_options, cellalign_args = core.calibre_page_options, core.cellalign_args
    check_asset_budget, check_output_budget = core.check_asset_budget, core.check_output_budget
    chem_filter_args, code_filter_args = core.chem_filter_args, core.code_filter_args
    contains_citations, document_filter_args = core.contains_citations, core.document_filter_args
    cover_header_args = core.cover_header_args
    csl_args, css_additions, css_heading_args = core.csl_args, core.css_additions, core.css_heading_args
    csv_table_filter = core.csv_table_filter
    default_monofont = core.default_monofont
    discovery_disabled, display_path = core.discovery_disabled, core.display_path
    document_font_args, document_font_setting = core.document_font_args, core.document_font_setting
    document_header_file, document_preambles = core.document_header_file, core.document_preambles
    effective_no_auto, engine_label, find_metadata = core.effective_no_auto, core.engine_label, core.find_metadata
    find_preambles, font_args = core.find_preambles, core.font_args
    frontmatter_margin_geometry_options = core.frontmatter_margin_geometry_options
    frontmatter_pdfmd_options, frontmatter_value = core.frontmatter_pdfmd_options, core.frontmatter_value
    gather_stamp_texts, has_chapter_field = core.gather_stamp_texts, core.has_chapter_field
    has_code_spans, has_embedded_preamble = core.has_code_spans, core.has_embedded_preamble
    has_geometry, has_mainfont, has_monofont = core.has_geometry, core.has_mainfont, core.has_monofont
    has_standalone_option, hoist_code_header = core.has_standalone_option, core.hoist_code_header
    html_pandoc_args, image_filter_args = core.html_pandoc_args, core.image_filter_args
    is_assembled_document = core.is_assembled_document
    keep_header_includes, kit_no_auto_kinds = core.keep_header_includes, core.kit_no_auto_kinds
    log_cmd, mainfont_choice = core.log_cmd, core.mainfont_choice
    managed_fonts_css = core.managed_fonts_css
    markup_header_args, mathfont_args = core.markup_header_args, core.mathfont_args
    metadata_cwd = core.metadata_cwd
    office_fallback_wanted, office_finish = core.office_fallback_wanted, core.office_finish
    office_reference, open_file, option_names = core.office_reference, core.open_file, core.option_names
    pandoc_metadata_order, pandoc_working_directory = core.pandoc_metadata_order, core.pandoc_working_directory
    paper_kind, paper_variables = core.paper_kind, core.paper_variables
    pdf_metadata_header_file, pdf_metadata_snippet = core.pdf_metadata_header_file, core.pdf_metadata_snippet
    polish_pdf, prepared_latex_inputs = core.polish_pdf, core.prepared_latex_inputs
    record_engine = core.record_engine
    report_common_folder = core.report_common_folder
    report_sources, resolve_attach, resolve_embed = core.report_sources, core.resolve_attach, core.resolve_embed
    resolve_engines, resolve_from_format = core.resolve_engines, core.resolve_from_format
    resolve_stamp_options, resolve_strict = core.resolve_stamp_options, core.resolve_strict
    resolve_strip_comments, resource_path_option = core.resolve_strip_comments, core.resource_path_option
    run_engine_command, run_office_pandoc = core.run_engine_command, core.run_office_pandoc
    script_fallback, stamp_after_success = core.script_fallback, core.stamp_after_success
    stamp_scope_matches, strict_message = core.stamp_scope_matches, core.strict_message
    table_width_filter = core.table_width_filter
    tex_package_args, tex_search_env, time_breakdown = core.tex_package_args, core.tex_search_env, core.time_breakdown
    time_label, typst_filter_args = core.time_label, core.typst_filter_args
    warning_capture, weasyprint_math_args = core.warning_capture, core.weasyprint_math_args
    width_filter_args, write_assembled_markdown = core.width_filter_args, core.write_assembled_markdown

    files, excluded = report_sources(paths, args.ignore, args.exclude_unnumbered, args.recursive, args.include_never)
    if target_format == ASSEMBLED_FORMAT:
        files = [file for file in files if not is_assembled_document(file)]
    if not files:
        raise SystemExit("No Markdown files found for the report")
    # --no-auto and its pdfmd-options counterpart are decided from
    # files[0] only, same as the reader/documentclass/pdf-engine
    # front matter below -- a report can't mix per-chapter overrides
    # in one Pandoc invocation.
    report_no_auto = effective_no_auto(files[0], args.no_auto)

    def report_note(kind: str, detail: str) -> None:
        AUTO_LOG.record(kind, detail, args.verbose)

    try:
        document_class = (frontmatter_value(files[0], "documentclass")
                          or frontmatter_value(files[0], "class"))
        metadata_directory = paths[0] if len(paths) == 1 and paths[0].is_dir() else files[0].parent
        # An explicit -y/--metadata-file always wins over --no-auto
        # metadata; only auto-discovery (args.metadata_file is None) is
        # what --no-auto metadata/yaml suppresses.
        metadata_request = ([] if args.metadata_file is None and auto_disabled(report_no_auto, "metadata")
                            else args.metadata_file)
        if metadata_request is None:
            metadata_request = option_names(frontmatter_pdfmd_options(files[0]), "yaml") or None
        metadata = find_metadata(metadata_directory.resolve(), metadata_request, report=True,
                                 document_class=document_class, document_stem=files[0].stem, document=files[0],
                                 discover=not (metadata_request is None and discovery_disabled(report_no_auto, "metadata")))
    except (FileNotFoundError, ValueError) as error:
        raise SystemExit(str(error))
    metadata_files = ([] if metadata is AUTO_METADATA_DISABLED else
                      (metadata if isinstance(metadata, list) else ([metadata] if metadata else [])))
    report_kit_kinds = kit_no_auto_kinds(files[0], metadata_files, report_no_auto)
    if report_kit_kinds:
        report_no_auto = effective_no_auto(files[0], args.no_auto, report_kit_kinds)
    target_format = default_target(files[0], metadata_files)
    need_engines(target_format)
    engines = resolve_engines(files[0], args.engine, engines, args.presentation, target_format, metadata_files, args.verbose)
    report_build = route.resolve_build(core, files[0], metadata_files)
    report_chapters, title_notes = titles.plan(core, files, metadata_files, titles.resolve_policy(core, files[0], metadata_files))
    if target_format in {"pdf", *TEX_STANDALONE_FORMATS}:
        class_variables, class_options, class_note = titles.chapter_arguments(core, files, metadata_files, list(variables))
        variables = [*variables, *class_variables]
        pandoc_options = [*pandoc_options, *class_options]
        title_notes = [*title_notes, *([class_note] if class_note else [])]
    for note in (title_notes if report_build == "patch" else []):
        print(f"NOTE  {note}")
    if report_build == "route" and target_format != ASSEMBLED_FORMAT:
        route.build(core, args=args, files=files, excluded=excluded, metadata=metadata, metadata_files=metadata_files,
                    target_format=target_format, engines=engines, variables=variables, pandoc_options=pandoc_options,
                    stamp_overrides=stamp_overrides, embed_request=embed_request, no_auto=report_no_auto,
                    chapters=report_chapters, notes=title_notes)
        return
    BUILD["engine"], BUILD["failed"], BUILD["chain"] = None, [], None
    begin_timer()
    report_capture = warning_capture()
    report_seen = report_capture.__enter__()       # --strict: the warnings of this build (closed before the OK lines)
    report_from, report_reader_reason = (
        (args.from_format, None) if auto_disabled(report_no_auto, "reader")
        else resolve_from_format(files[0], args.from_format, metadata_files)
    )
    if report_reader_reason:
        report_note("READER", report_reader_reason)
    output = route.output_path(core, args, target_format)
    if target_format == ASSEMBLED_FORMAT:
        # --stop-at markdown: the chapters, as one Markdown text, in the
        # order Pandoc would read them. Nothing else of the build runs.
        report_plan = None
        report_embed = resolve_embed(files[0], metadata_files, embed_request)
        if report_embed is not None:
            kinds, lua_mode = report_embed
            report_plan = EmbedPlan(
                kinds, lua_mode, list(metadata_files),
                ([] if "preamble" not in kinds else document_preambles(files[0], pandoc_options, report_no_auto)),
                [])  # a report build applies no discovered Lua filter
            if "lua" in kinds:
                print("NOTE  a report/book build applies no discovered Lua filter, so none is embedded")
        ok, reason = write_assembled_markdown(files, output, False, report_plan,
                                              strip_comments=resolve_strip_comments(files[0], metadata_files))
        if not ok:
            raise SystemExit(reason)
        for file in files:
            if not has_chapter_field(file):
                print(f"[WARNING] unnumbered Markdown included: {display_path(file)}")
            print(f"OK    {display_path(file)}")
        for file in excluded:
            print(f"SKIP  {display_path(file)}")
        print(f"OK    REPORT  {display_path(output)}")
        if args.open:
            open_file(output)
        return
    pandoc_cwd = pandoc_working_directory(metadata_cwd(metadata_files, files[0].parent))
    report_resource_path = resource_path_option(files[0].parent, pandoc_cwd, metadata_files)

    with table_width_filter() as width_filter, csv_table_filter() as csv_filter, titles.Hidden() as hidden:
        if target_format != "pdf":
            # See convert_one's matching comment: a TEX_STANDALONE_FORMATS
            # writer here still gets --standalone plus the same
            # preamble/font/margin/header-includes treatment as the PDF
            # report path below (all decided from files[0] only, same as
            # report_no_auto/report_from/documentclass above), just
            # without an engine ever actually running.
            is_tex_target = target_format in TEX_STANDALONE_FORMATS
            report_preambles = ([] if not is_tex_target else document_preambles(files[0], pandoc_options, report_no_auto))
            if report_preambles:
                announce_preambles(report_preambles)
            stamp_preambles = report_preambles
            report_pdf_meta_options = resolve_stamp_options(files[0], metadata_files, stamp_overrides)
            report_pdf_meta_snippet_text = (
                pdf_metadata_snippet(report_pdf_meta_options,
                                     gather_stamp_texts(files[0], stamp_preambles), args.verbose)
                if (report_pdf_meta_options["pdf_metadata"] and is_tex_target
                    and stamp_scope_matches(report_pdf_meta_options, output)) else None
            )
            # the style sheets of the first file (v3.28.41), as _convert_one_core does for a document
            css_options, css_variables = css_additions(
                files[0], metadata_files, variables, report_no_auto,
                target_format in HTML_TARGETS or target_format.startswith("epub")
                or (target_format == "pdf" and any(item in ENGINE_GROUPS["html"] or item == "calibre" or item in BROWSER_ENGINES for item in engines)),
                report_note)
            if css_options or css_variables:
                pandoc_options = [*pandoc_options, *css_options]
                variables = [*variables, *css_variables]
            report_document_font = is_tex_target and has_mainfont(files[0], variables, metadata_files)
            report_mainfont_auto = is_tex_target and not auto_disabled(report_no_auto, "mainfont")
            report_standalone_auto = (is_tex_target and not auto_disabled(report_no_auto, "standalone")
                                      and not has_standalone_option(pandoc_options))
            report_geometry_needed = (is_tex_target and not auto_disabled(report_no_auto, "margin")
                                      and not has_geometry(files[0], variables, metadata_files, report_preambles))
            if report_geometry_needed:
                report_note("MARGIN", "REPORT: no geometry/margin set; "
                                     f"using geometry:margin={DEFAULT_MARGIN} on LaTeX-family targets")
            report_margin_options = (None if auto_disabled(report_no_auto, "margin")
                                     else frontmatter_margin_geometry_options(files[0], variables,
                                                                              metadata_files))
            if is_tex_target and report_margin_options:
                report_note("MARGIN", "REPORT: margin: isn't a Pandoc variable LaTeX-family "
                                     "targets read (geometry: is) -- using "
                                     f"geometry:{','.join(report_margin_options)}")
            report_monofont_needed = (is_tex_target and not auto_disabled(report_no_auto, "monofont")
                                      and any(has_code_spans(file.read_text(encoding="utf-8-sig")) for file in files)
                                      and not has_monofont(files[0], variables, metadata_files))
            if report_monofont_needed:
                report_note("MONOFONT", "REPORT: has code but no monofont set; "
                                       f"using {default_monofont()} on LaTeX-family targets")
            report_tex_font = (None if not is_tex_target else
                               mainfont_choice(list(files), metadata_files, variables, args.font,
                                               report_document_font, report_mainfont_auto, report_no_auto,
                                               report_note))
            with prepared_latex_inputs([*files, *pandoc_metadata_order(metadata_files)], is_tex_target,
                                       typst_engine=(target_format == "typst"),
                                       doc_count=len(files),
                                       drop_embedded_preamble=not is_tex_target) as prepared, \
                    document_header_file(files[0], (bool(report_preambles) or has_embedded_preamble(files[0]) or bool(report_pdf_meta_snippet_text))
                                         and is_tex_target, metadata_files, report_no_auto) as report_header_file, \
                    pdf_metadata_header_file(report_pdf_meta_snippet_text) as report_pdf_meta_file, \
                    (script_fallback(list(files), metadata_files, variables, report_preambles,
                                     report_tex_font, None, report_no_auto, report_note)
                     if target_format in ("latex", "beamer") else contextlib.nullcontext((None, None))) \
                    as (report_fonts_header, report_fonts_filter), \
                    office_reference(files[0], metadata_files, variables, target_format, output,
                                     pandoc_options, report_no_auto, report_note) as report_office_arguments:
                prepared_files = hidden.copies(core, prepared[:len(files)], files, report_chapters)
                prepared_metadata = prepared[len(files):]
                cmd = ["pandoc", *map(str, prepared_files), "-o", str(output), "-t", target_format]
                if is_tex_target and report_standalone_auto:
                    report_note("STANDALONE", f"REPORT: --to {target_format} needs a complete, "
                                              "independently compilable document; adding --standalone")
                    cmd.append("--standalone")
                if report_from:
                    cmd += ["-f", report_from]
                if metadata is not AUTO_METADATA_DISABLED:
                    for metadata_file in prepared_metadata:
                        cmd += ["--metadata-file", str(metadata_file)]
                cmd += report_resource_path
                if is_tex_target:
                    # See convert_one's matching comment: no
                    # mainfontfallback here -- it's the Pandoc mechanism
                    # PREFERRED_FONT's own comment already documents as
                    # crashing lualatex outright in this environment.
                    report_first_font = report_tex_font
                    if report_first_font:
                        cmd += font_args("mainfont", report_first_font)
                        cmd += mathfont_args(report_first_font, files[0], metadata_files, variables, args.font or None,
                                             report_no_auto, None, report_note)
                    else:
                        cmd += document_font_args(list(files), metadata_files, variables)
                    if report_geometry_needed:
                        cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                    elif report_margin_options:
                        for margin_option in report_margin_options:
                            cmd += ["-V", f"geometry:{margin_option}"]
                    if report_monofont_needed:
                        cmd += font_args("monofont", default_monofont())
                for variable in paper_variables(files[0], metadata_files, variables, None,
                                                paper_kind("tex" if target_format in ("latex", "beamer") else target_format,
                                                           report_no_auto))[0]:
                    cmd += ["-V", variable]
                if report_preambles and is_tex_target:
                    for preamble in report_preambles:
                        cmd += ["--include-in-header", str(preamble)]
                if report_pdf_meta_file is not None:
                    cmd += ["--include-in-header", str(report_pdf_meta_file)]
                if report_fonts_header is not None:
                    cmd += ["--include-in-header", str(report_fonts_header)]
                # Last -- see convert_one's matching comment; report_header_file
                # is added whenever it exists, not only when report_preambles
                # is non-empty (report_pdf_meta_file alone can trigger the drop
                # this guards against).
                if report_header_file is not None:
                    cmd += ["--include-in-header", str(report_header_file)]
                if target_format in HTML_TARGETS:
                    cmd += html_pandoc_args(files[0], metadata_files, pandoc_options,
                                            args.self_contained, report_note)
                cmd += document_filter_args(files, files, metadata_files, report_no_auto, csv_filter, pandoc_options,
                                            label="REPORT")
                if (any(contains_citations(file) for file in files)
                        and "--citeproc" not in pandoc_options
                        and not core.CITEPROC_DISABLED):
                    cmd.append("--citeproc")
                if "--citeproc" in cmd or "--citeproc" in pandoc_options:
                    cmd += csl_args(list(files), metadata_files, pandoc_options, report_no_auto)
                # pandoc_options after --citeproc: see convert_one's
                # matching comment.
                cmd += report_office_arguments
                cmd += pandoc_options
                if report_fonts_filter is not None:
                    cmd += ["--lua-filter", str(report_fonts_filter)]
                if is_tex_target and not auto_disabled(report_no_auto, "tablewidth"):
                    cmd += width_filter_args(width_filter)
                cmd += cellalign_args(files, metadata_files)
                if is_tex_target:
                    cmd += code_filter_args(report_no_auto, list(files)) + image_filter_args(report_no_auto, list(files))
                    hoist_code_header(cmd)
                    keep_header_includes(cmd, list(files), metadata_files, pandoc_options, report_header_file)
                if is_tex_target:
                    cmd += core.paragraph_spacing_latex_args(list(files), metadata_files)
                cmd += core.paragraph_spacing_typst_args(files[0], metadata_files, target_format)
                cmd += typst_filter_args(target_format, cmd, pandoc_cwd)
                cmd += report_office_arguments.filter_arguments
                cmd += chem_filter_args(list(files), metadata_files,
                                        list(report_preambles or ([] if discovery_disabled(report_no_auto, "preamble")
                                                                  else find_preambles(files[0].parent, files[0].stem, []))),
                                        target_format, bool(report_office_arguments.filter_arguments),
                                        report_no_auto)
                if report_office_arguments.filter_arguments:
                    result = run_office_pandoc(cmd, output, report_office_arguments, pandoc_cwd,
                                               args.verbose, args.debug)
                else:
                    log_cmd(cmd, pandoc_cwd, args.verbose)
                    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=pandoc_cwd)
                office_finish(report_office_arguments, files[0], args.verbose)
        else:
            preambles = document_preambles(files[0], pandoc_options, report_no_auto)
            announce_preambles(preambles)
            stamp_preambles = preambles
            report_pdf_meta_options = resolve_stamp_options(files[0], metadata_files, stamp_overrides)
            report_pdf_meta_snippet_text = (
                pdf_metadata_snippet(report_pdf_meta_options,
                                     gather_stamp_texts(files[0], stamp_preambles), args.verbose)
                if (report_pdf_meta_options["pdf_metadata"]
                    and stamp_scope_matches(report_pdf_meta_options, output)) else None
            )
            report_tablewidth_auto = not auto_disabled(report_no_auto, "tablewidth")
            geometry_needed = (not auto_disabled(report_no_auto, "margin")
                              and not has_geometry(files[0], variables, metadata_files, preambles))
            if geometry_needed:
                report_note("MARGIN", "REPORT: no geometry/margin set; "
                                     f"using geometry:margin={DEFAULT_MARGIN} on LaTeX-family engines")
            margin_options = (None if auto_disabled(report_no_auto, "margin")
                             else frontmatter_margin_geometry_options(files[0], variables, metadata_files))
            if margin_options:
                report_note("MARGIN", "REPORT: margin: isn't a Pandoc variable LaTeX-family "
                                     "engines read (geometry: is) -- using "
                                     f"geometry:{','.join(margin_options)}")
            monofont_needed = (not auto_disabled(report_no_auto, "monofont")
                              and any(has_code_spans(file.read_text(encoding="utf-8-sig")) for file in files)
                              and not has_monofont(files[0], variables, metadata_files))
            if monofont_needed:
                report_note("MONOFONT", "REPORT: has code but no monofont set; "
                                       f"using {default_monofont()} on LaTeX-family engines")
            # the document font and the math font, chosen as for one document (v3.32.14; `report-build: route` gets the rest)
            pdf_font = mainfont_choice(list(files), metadata_files, variables, args.font,
                                       has_mainfont(files[0], variables, metadata_files),
                                       not auto_disabled(report_no_auto, "mainfont"), report_no_auto, report_note)
            # Reports need one Pandoc invocation, so retry each usable engine here.
            #
            # Like its is_tex_target sibling above, it adds document_header_file()
            # (v3.27.26): the first chapter's front-matter macro definitions
            # (document_latex_definitions: experiment: -> \LabExperiment) were
            # never made here, so a -r PDF printed N/A for them. The chapters'
            # own header-includes are kept since v3.27.18 (keep_header_includes).
            result = None
            failed_families: set[str] = set()
            failed_engines: list[str] = []
            engines = core.chain_plan_build(files[0], metadata_files, engines, output, args.verbose)   # engine-fallback
            for engine_index, engine in enumerate(engines):
                family = ENGINE_FAMILY.get(engine, engine)
                if family in failed_families:
                    print(f"SKIP  REPORT: {engine} shares the {family} engine with an earlier "
                          f"failure; skipping", file=sys.stderr)
                    continue
                with prepared_latex_inputs([*files, *pandoc_metadata_order(metadata_files)], engine in LATEX_ENGINES,
                                           typst_engine=(engine == "typst"),
                                           doc_count=len(files)) as prepared, \
                        pdf_metadata_header_file(
                            report_pdf_meta_snippet_text if engine in LATEX_ENGINES else None
                        ) as report_pdf_meta_file, \
                        script_fallback(list(files), metadata_files, variables, preambles, pdf_font, engine,
                                        report_no_auto, report_note) as (report_fonts_header,
                                                                         report_fonts_filter), \
                        managed_fonts_css(engine) as report_fonts_css, \
                        document_header_file(files[0], (bool(preambles) or has_embedded_preamble(files[0])
                                                        or bool(report_pdf_meta_snippet_text))
                                             and engine in LATEX_ENGINES, metadata_files, report_no_auto) as report_header_file:
                    prepared_files = hidden.copies(core, prepared[:len(files)], files, report_chapters)
                    prepared_metadata = prepared[len(files):]
                    cmd = ["pandoc", *map(str, prepared_files), "-o", str(output), "--pdf-engine=" + engine]
                    if engine == "prince":                # it names only the page's first author (v3.33.66)
                        cmd += core.prince_author_options(files[0], metadata_files, variables)
                    if report_from:
                        cmd += ["-f", report_from]
                    if metadata is not AUTO_METADATA_DISABLED:
                        for metadata_file in prepared_metadata:
                            cmd += ["--metadata-file", str(metadata_file)]
                    cmd += report_resource_path
                    if geometry_needed and engine in LATEX_ENGINES:
                        cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                    elif margin_options and engine in LATEX_ENGINES:
                        for margin_option in margin_options:
                            cmd += ["-V", f"geometry:{margin_option}"]
                    if monofont_needed and engine in LATEX_ENGINES:
                        cmd += font_args("monofont", default_monofont())
                    if engine in LATEX_ENGINES:
                        if pdf_font:
                            cmd += font_args("mainfont", pdf_font)
                            cmd += mathfont_args(pdf_font, files[0], metadata_files, variables, args.font or None,
                                                 report_no_auto, None, report_note)
                        else:
                            cmd += document_font_args(list(files), metadata_files, variables)
                    for variable in paper_variables(files[0], metadata_files, variables, None,
                                                    paper_kind(engine, report_no_auto))[0]:
                        cmd += ["-V", variable]
                    if preambles and engine in LATEX_ENGINES:
                        for preamble in preambles:
                            cmd += ["--include-in-header", str(preamble)]
                    if report_pdf_meta_file is not None:
                        cmd += ["--include-in-header", str(report_pdf_meta_file)]
                    if report_fonts_header or report_fonts_css:
                        cmd += ["--include-in-header", str(report_fonts_header or report_fonts_css)]
                    if report_header_file is not None:          # last, as in the branch above
                        cmd += ["--include-in-header", str(report_header_file)]
                    cmd += document_filter_args(files, files, metadata_files, report_no_auto, csv_filter, pandoc_options,
                                                label="REPORT")
                    if (any(contains_citations(file) for file in files)
                            and "--citeproc" not in pandoc_options
                            and not core.CITEPROC_DISABLED):
                        cmd.append("--citeproc")
                    if "--citeproc" in cmd or "--citeproc" in pandoc_options:
                        cmd += csl_args(list(files), metadata_files, pandoc_options, report_no_auto)
                    # pandoc_options after --citeproc: see convert_one's
                    # matching comment.
                    cmd += pandoc_options
                    if engine in LATEX_ENGINES:
                        cmd += tex_package_args(files, report_no_auto, report_note)
                        cmd += core.paragraph_spacing_latex_args(list(files), metadata_files)
                        cmd += css_heading_args(list(files), metadata_files, variables, report_no_auto, report_note)
                        cmd += cover_header_args(list(files), metadata_files)
                        cmd += markup_header_args(list(files), metadata_files, cmd)
                    if report_fonts_filter is not None:
                        cmd += ["--lua-filter", str(report_fonts_filter)]
                    if report_tablewidth_auto and engine in LATEX_ENGINES:
                        cmd += width_filter_args(width_filter)
                    cmd += cellalign_args(files, metadata_files)
                    if engine in LATEX_ENGINES:
                        cmd += code_filter_args(report_no_auto, list(files)) + image_filter_args(report_no_auto, list(files))
                        hoist_code_header(cmd)
                        keep_header_includes(cmd, list(files), metadata_files, pandoc_options, report_header_file)
                    # as for one document (v3.28.2): last, after the LaTeX filter (v3.28.11)
                    cmd += core.paragraph_spacing_typst_args(files[0], metadata_files, engine)
                    report_last = typst_filter_args(engine, cmd, pandoc_cwd) + weasyprint_math_args(
                        engine, pandoc_options,
                        args.font or document_font_setting("mainfont", list(files), metadata_files, variables),
                        report_no_auto)

                    def run_report_pandoc(command: list[str], target: Path):
                        log_cmd(command, pandoc_cwd, args.verbose)
                        return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", cwd=pandoc_cwd,
                                              env=tex_search_env(files[0].parent, pandoc_cwd, files[0]))
                    report_page = lambda: (browser_page_css(files[0], metadata_files, variables) if engine in BROWSER_ENGINES
                                         else calibre_page_options(files[0], metadata_files, variables))
                    if engine == "calibre" or engine in BROWSER_ENGINES or (engine in ("typst", "weasyprint") and office_fallback_wanted(
                            files[0], metadata_files, failed_families, "typst" if engine == "typst" else "html",
                            list(files))):
                        # as for one document (LaTeX made native or drawn), without LaTeX's label numbers:
                        # those would be the first chapter's alone
                        with office_reference(files[0], metadata_files, variables,
                                              "typst" if engine == "typst" else "html", output, pandoc_options,
                                              report_no_auto, report_note, labels="off",
                                              force_filter=True) as office_arguments:
                            cmd += office_arguments.filter_arguments + report_last
                            runner = ((lambda command, target: run_office_pandoc(
                                          command, target, office_arguments, pandoc_cwd, args.verbose))
                                      if office_arguments.filter_arguments else run_report_pandoc)
                            result = run_engine_command(cmd, engine, output, runner, report_page, args.verbose)
                            office_finish(office_arguments, files[0], args.verbose)
                    else:
                        cmd += report_last
                        result = run_engine_command(cmd, engine, output, run_report_pandoc, report_page,
                                                    args.verbose)
                if result.returncode == 0:
                    record_engine(engine, failed_engines)
                    break
                failed_families.add(family)
                failed_engines.append(engine)
                remaining = [e for e in engines[engine_index + 1:] if ENGINE_FAMILY.get(e, e) not in failed_families]
                if core.chain_engine_failed("REPORT", engine, result, remaining, args.debug):   # engine-fallback stops here
                    break
    assert result is not None
    if result.returncode == 0:
        check_asset_budget(list(files), files[0], metadata_files)
        check_output_budget(output, list(files), files[0], metadata_files)
    report_capture.__exit__(None, None, None)
    report_problems = list(report_seen)
    if result.returncode == 0:             # what Pandoc and its filters wrote (a filter's WARN lines too), once each
        known = {line.strip() for line in report_problems}
        report_problems += [line for line in re.findall(r"(?m)^(?:\[WARNING\]|WARN\b).*$", result.stderr or "")
                            if line.strip() not in known]
    report_strict_failed = bool(result.returncode == 0 and report_problems and resolve_strict(files[0], metadata_files))
    if result.returncode == 0:
        for file in files:
            stamp_after_success(file, metadata_files, stamp_preambles, stamp_overrides,
                                output, args.verbose, report_output=output)
            backup_after_success(file, metadata_files, args.backup, args.verbose, args.backup_format)
        if target_format == "pdf":
            polish_pdf(output, list(files), args.verbose)
        if target_format == "pdf" and resolve_attach(files[0], metadata_files):
            attach_source_after_success(
                files[0], output, list(files[1:]), metadata_files, list(stamp_preambles), report_no_auto,
                args.verbose, report=True,
                base=report_common_folder(files))
    for file in files:
        if not has_chapter_field(file):
            print(f"[WARNING] unnumbered Markdown included: {display_path(file)}")
        print(f"OK    {display_path(file)}")
    for file in excluded:
        print(f"SKIP  {display_path(file)}")
    if metadata is not AUTO_METADATA_DISABLED:
        for metadata_file in metadata_files:
            if args.metadata_file is None:
                AUTO_LOG.record_file("YAML", metadata_file, args.verbose)
            else:
                print(f"YAML  {display_path(metadata_file)}")
    if not args.verbose:
        AUTO_LOG.flush()
    report_built = attach_time(Built((output, result.returncode == 0), BUILD["engine"], BUILD["failed"]), files[0], metadata_files)
    report_built.stopped = core.chain_stopped()
    print(f"{'OK  ' if result.returncode == 0 and not report_strict_failed else 'FAIL'}  REPORT  {display_path(output)}"
          + time_label(report_built) + engine_label(report_built))
    if args.verbose:
        for line in time_breakdown(report_built):
            print(line)
    if result.stderr:
        print(result.stderr[-3000:])
    if report_strict_failed:
        print(strict_message(report_problems))
    if result.returncode or report_strict_failed:
        raise SystemExit(1)
    if args.open:
        open_file(output)
    return
