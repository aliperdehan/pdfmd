"""Every command-line flag and every `pdfmd-options` key, and where each one is set (v3.27.0).

Each flag or key is either a `--setup` row (the value here is the row's key) or left out of `--setup` on purpose (the
value is an `Omitted` with its reason). The numbered list shows the left-out ones with `o`, the full-screen one with
`o` too. tests/test_setup.py checks this table against pdfmd's argument parser, its option readers and the registry,
both ways: a new flag or key that is in neither, or a row that names nothing, fails the suite. A new flag or a new
`pdfmd-options` key therefore needs a line here.

Flags are named by their argparse `dest` (`--no-stamp` is `no_stamp`); keys by their dotted path under `pdfmd-options`
(`stamp.mode`). A key whose value is a mapping is listed by its fields; the mapping itself is not a key of its own.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Omitted:
    reason: str      # a key of REASONS
    note: str = ""   # what the reason alone does not say


REASONS = {
    "command": "Commands: they do something once, so there is nothing to make a default of.",
    "run": "About one run: which files, where the result goes, what to print.",
    "document": "About one document or project: its front matter, or its folder's metadata.yaml.",
    "trust": "Trust is given to one file or folder, never to every document at once.",
    "internal": "Written by pdfmd itself into the files it makes, or used between its own parts.",
    "inert": "Accepted for symmetry, but changes nothing.",
}

CMD = Omitted("command")
RUN = Omitted("run")
DOC = Omitted("document")
BUILTIN = Omitted("run", "the built-in renderer's switches, kept for the mdpdf and inkmd commands")
PDF_INFO = Omitted("document", "the document's own title:, subject:, author: and keywords:")
WORD_ONLY = Omitted("document", "a Word/ODT-only override of the metadata rows; per document or house style")

# argparse dest -> the row that sets the same thing for every document, or why there is none
FLAGS: dict[str, str | Omitted] = {
    "help": CMD, "version": CMD, "path": RUN,
    "presentation": Omitted("run", "slides are asked for per run"),
    "slide_level": Omitted("document", "the document's own slide-level:"),
    "newest": RUN, "include_never": RUN, "which": CMD,
    "serve": CMD, "api": CMD,
    "batch": RUN, "report": RUN, "recursive": RUN, "out": RUN,
    "strict": "options.strict", "build_time": "options.build-time", "build_log": "options.build-log", "last_build": CMD, "failed": RUN, "time_format": "options.time-format", "max_asset_mb": "options.max-asset-mb", "max_output_mb": "options.max-output-mb",
    "stop_at": RUN, "assemble_only": RUN, "merge": RUN,
    "embed_metadata": Omitted("document", "per document: pdfmd-options.embed"),
    "no_embed_metadata": RUN,
    "lua_mode": Omitted("document", "per document: pdfmd-options.embed.lua"),
    "strip_comments": "options.strip-comments",
    "strip_comments_in": Omitted("run", "narrows the row \"Drop <!-- comments -->\" to some kinds for one run"),
    "keep_comments_in": Omitted("run", "narrows the row \"Drop <!-- comments -->\" to some kinds for one run"),
    "attach_bibliography": "options.attach-bibliography", "attach_csl": "options.attach-csl", "attach_source": "options.attach-source",
    "keep_source": "options.keep-source", "bundle": "options.bundle", "bundle_packages": "options.bundle-packages",
    "bookmarks": "options.bookmarks", "header": "options.header", "footer": "options.footer",
    "attach_links": "options.attach-links", "paper": "papersize", "paragraph_spacing": "options.paragraph-spacing",
    "css": "options.css", "css_scope": "options.css-scope",
    "family": BUILTIN, "no_autolinks": BUILTIN, "no_html": BUILTIN, "allow_unsafe_urls": BUILTIN,
    "allow_remote_images": BUILTIN, "emoji_fallback": BUILTIN,
    "pdf_title": PDF_INFO, "pdf_subject": PDF_INFO, "pdf_author": PDF_INFO, "pdf_keywords": PDF_INFO,
    "extract": CMD, "restore": CMD, "list_only": CMD,
    "self_contained": "options.html.self-contained",
    "unpack": CMD, "slim": RUN,
    "trust_embedded": Omitted("trust", "the filters embedded in one file, for one run"),
    "trust_lua": Omitted("trust", "a command that trusts one Lua file or folder"),
    "destination_cwd": RUN,
    "font": Omitted("run", "a fallback font for one run; the font rows and `pdfmd --install fonts` cover every document"),
    "engine": "options.pdf-engine", "engine_fallback": "options.engine-fallback", "to": "options.default-output", "from_format": "options.flavour",
    "install": CMD, "kits": "kits", "kit": "options.kit", "kit_stack": "options.kit-stack", "translit": "translit", "fallback": "options.fallback", "missing": "options.missing",
    "check_fonts": CMD, "show_config": CMD, "text_to_markdown": "options.text-to-markdown",
    "setup": CMD, "disabled": Omitted("run", "uses switched-off features for one run"), "init_config": CMD, "uninstall": CMD, "init_reference": CMD, "completion": CMD, "init": CMD,
    "user_path": "user-path", "add_to_path": "user-path", "remove_from_path": "user-path", "show_user_path": "user-path",
    "yes": Omitted("run", "answers the question of --user-path"),
    "check": CMD, "check_source": CMD, "check_ignore": "options.check-ignore", "check_docx": CMD, "edit": CMD,
    "crop": CMD, "crop_pad": Omitted("run", "the room left around the ink of one crop"), "crop_ignore_bottom": Omitted("run", "the strip a crop does not look at, for one crop"), "crop_page": Omitted("run", "which page one crop keeps"),
    "image_dpi": Omitted("run", "the resolution of the pictures of one run"),
    "image_quality": Omitted("run", "the JPEG quality of one run"),
    "page_folder": "options.page-folder",
    "raw": "options.raw", "no_raw": "options.raw",
    "pagebreak": "options.pagebreak", "no_pagebreak": "options.pagebreak",
    "linebreak": "options.linebreak", "no_linebreak": "options.linebreak",
    "markup": "options.markup", "no_markup": "options.markup",
    "show_comments": "options.show-comments",
    "flavour": "options.flavour",
    "unclosed_comment": "options.unclosed-comment",
    "calc": "options.calc.enabled", "calc_digits": "options.calc.digits", "calc_round": "options.calc.round", "calc_subs": "options.calc.subs", "calc_typeset": "options.calc.typeset", "calc_typeset_upright": "options.calc.typeset-upright", "calc_typeset_italic": "options.calc.typeset-italic", "calc_noindent": "options.calc.noindent", "calc_space": "options.calc.space", "calc_align": "options.calc.align", "calc_constants": "options.calc.constants", "calc_export": "options.calc.export",
    "raw_for": Omitted("document", "per output family: pdfmd-options.raw as a mapping"),
    "gfm_scripts": "options.gfm.scripts", "gfm_math": "options.gfm.math", "ascii_missing": "options.ascii.missing",
    "ascii_stdio": Omitted("internal", "pdfmd's own ASCII filter calls it"),
    "init_vscode": CMD, "extract_tables": CMD, "extract_inline_csv": CMD, "expand_tables": CMD,
    "csv": "options.csv.enabled", "csv_rows": "options.csv.rows", "csv_cols": "options.csv.cols", "csv_note": "options.csv.note", "table_keep": "options.table-keep",
    "rewrite": "options.rewrite",
    "view": CMD, "pager": "options.pager", "color": Omitted("run", "auto is right: on for a file and --view, off in a pipe"),
    "width": Omitted("run", "the window's own width; a number only for output that is not read in a window"),
    "table_numbers": RUN, "table_names": RUN, "tables_dir": RUN, "tables_inline": RUN, "dry_run": RUN,
    "line_numbers": "options.line-numbers", "no_code_wrap": "options.code-wrap",
    "apply_defaults": "options.apply-defaults", "hybrid": "options.hybrid",
    "doctor": CMD, "deep": CMD, "check_dependencies": CMD, "doc": CMD, "doc_print": CMD, "doc_path": CMD,
    "jobs": RUN, "variable": RUN, "metadata_file": RUN, "ignore": RUN, "exclude_unnumbered": RUN, "section": RUN,
    "cache": "options.cache.aux", "cache_location": "options.cache.location", "cache_plots": "options.cache.plots",
    "seed_labels": "options.seed-labels", "seed_calc": "options.seed-calc", "clear_cache": CMD, "cache_info": CMD,
    "metadata_precedence": "options.metadata-precedence",
    "preset": "options.preset", "global_metadata": "options.global-metadata", "presets": CMD,
    "editor": "options.editor",
    "split": RUN, "split_depth": RUN, "list_parts": CMD,
    "no_auto": "options.no-auto",
    "verbose": RUN, "no_citeproc": RUN, "full_paths": RUN, "path_style": "options.path-style", "path_up": "options.path-up", "debug": RUN, "open": RUN, "bopen": RUN, "keep_aux": RUN, "watch": RUN,
    "stamp": "options.stamp.enabled", "no_stamp": "options.stamp.enabled", "stamp_mode": "options.stamp.mode",
    "stamp_store": "options.stamp.store",
    "stamp_partial": "options.stamp.partial", "no_stamp_partial": "options.stamp.partial",
    "history_to_file": CMD, "history_to_notes": CMD, "history": CMD, "history_all": CMD, "history_diff": CMD,
    "history_restore": CMD, "no_restored_note": "options.stamp.restored-note",
    "init_backups": CMD, "backup_folder": "options.backup.dir",
    "global_": Omitted("run", "makes --init-backups write the config instead of one document"),
    "merge_history": CMD,
    "stamp_packages": "options.stamp.packages", "stamp_scope": "options.stamp.scope",
    "stamp_output": "options.stamp.include-output", "no_stamp_output": "options.stamp.include-output",
    "stamp_pdf_metadata": "options.stamp.pdf-metadata", "no_stamp_pdf_metadata": "options.stamp.pdf-metadata",
    "backup": "options.backup.enabled", "backup_format": "options.backup.format",
}

# pdfmd-options key (dotted for a mapping's field) -> the row, or why there is none. Old spellings point at the row
# of the current one. A key that takes a value or a mapping (`metadata: x.yaml` / `metadata: {yaml: ...}`) is listed
# both ways.
OPTIONS: dict[str, str | Omitted] = {
    "alias": Omitted("document", "other names one document answers to (pdfmd NAME)"),
    "priority": Omitted("document", "one document's rank when bare pdfmd must choose: a number or a word (draft, final, never)"),
    "ranking.by": "options.ranking.by", "ranking.names": "options.ranking.names",
    "ranking.ladder": Omitted("document", "the order of the classes of priority words: a ranking.yaml or a `ranking:` mapping"),
    "ranking.classes": Omitted("document", "the classes of priority words (fruit: [cherry, banana]): a ranking.yaml or a `ranking:` mapping"),
    "aliases": Omitted("document", "other names one document answers to (pdfmd NAME)"),
    "apply-defaults": "options.apply-defaults",
    "ascii.missing": "options.ascii.missing",
    "attach-bibliography": "options.attach-bibliography", "attach-bib": "options.attach-bibliography",
    "attach-csl": "options.attach-csl",
    "css": "options.css", "css-scope": "options.css-scope",
    "paragraph-spacing": "options.paragraph-spacing",
    "cover": Omitted("document", "per document: a title page, or a picture for the first page / an EPUB's cover"),
    "attach-links": "options.attach-links",
    "attach-source": "options.attach-source", "embed-source": "options.attach-source",
    "backup.enabled": "options.backup.enabled", "backup.dir": "options.backup.dir",
    "backup.format": "options.backup.format", "backup.keep": "options.backup.keep", "backup.pdfs": "options.backup.pdfs",
    "bookmarks": "options.bookmarks",
    "bundle": "options.bundle", "bundle-max-mb": "options.bundle-max-mb", "bundle-packages": "options.bundle-packages",
    "cache.aux": "options.cache.aux", "cache.plots": "options.cache.plots", "cache.location": "options.cache.location",
    "cache.max-mb": "options.cache.max-mb",
    "cache-location": "options.cache.location",
    "check-ignore": "options.check-ignore", "kit": "options.kit", "kit-stack": "options.kit-stack",
    "citation-engine": "options.citation-engine",
    "csl-fallback": "options.csl-fallback",
    "code-wrap": "options.code-wrap", "line-numbers": "options.line-numbers",
    "line-number-step": "options.line-number-step",
    "csv": "options.csv.enabled", "csv.enabled": "options.csv.enabled",
    "csv.rows": "options.csv.rows", "csv.cols": "options.csv.cols", "table-keep": "options.table-keep",
    "table-ascii": "options.table-ascii", "cell-align": "options.cell-align", "table-tag-brackets": "options.table-tag-brackets", "table-align": "options.table-align", "table-valign": "options.table-valign", "md-macro": "options.md-macro", "slide-notes": "options.slide-notes", "linebreak": "options.linebreak", "table-captions": "options.table-captions", "table-caption-label": "options.table-caption-label",
    "table-caption-need-label": "options.table-caption-need-label", "table-caption-colon-words": "options.table-caption-colon-words", "table-caption-words": "options.table-caption-words",
    "pager": "options.pager", "pager_command": "options.pager_command", "pager-command": "options.pager_command",
    "csv.cut": "options.csv.cut", "csv.note": "options.csv.note", "csv.delimiter": "options.csv.delimiter",
    "csv.header": Omitted("document", "the shape of a project's data: per table (header=), or a folder's metadata.yaml"),
    "csv.reader": Omitted("document", "the shape of a project's data: per table (reader=), or a folder's metadata.yaml"),
    "default-output": "options.default-output",
    "embed": Omitted("document", "what one assembled file (--stop-at markdown) carries"),
    "embedded": Omitted("internal", "an assembled file's record of what it carries"),
    "origin": Omitted("internal", "an assembled file's record of where its pieces came from"),
    "applied-lua": Omitted("internal", "an assembled file's record of the filters already run"),
    "engine": "options.pdf-engine", "pdf-engine": "options.pdf-engine", "engine-fallback": "options.engine-fallback",
    "fallback": "options.fallback", "missing": "options.missing",
    "header": "options.header", "footer": "options.footer",
    "smiles.engine": "options.smiles.engine", "smiles.format": "options.smiles.format", "smiles.office-format": "options.smiles.office-format", "smiles.palette": "options.smiles.palette",
    "smiles.cell-width": "options.smiles.cell-width", "smiles.cell-height": "options.smiles.cell-height", "smiles.per-row": "options.smiles.per-row",
    "smiles.bond-length": "options.smiles.bond-length", "smiles.dpi": "options.smiles.dpi",
    "gfm.scripts": "options.gfm.scripts", "gfm.math": "options.gfm.math", "gfm.title": "options.gfm.title",
    "txt.scripts": "options.txt.scripts", "txt.title": "options.txt.title",
    "txt.math": Omitted("inert", "text has no math markup"),
    "html.self-contained": "options.html.self-contained", "html.standalone": "options.html.standalone",
    "html.math": "options.html.math", "html.css": "options.html.css",
    "odt.engine": "options.odt.engine",
    "hybrid": "options.hybrid",
    "keep-source": "options.keep-source",
    "lua-filter": "options.lua-filter",
    "preamble": "options.preamble",
    "yaml": Omitted("document", "the metadata files one document names"),
    "metadata": Omitted("document", "the files one document names, grouped: metadata files, preambles, filters"),
    "metadata.yaml": Omitted("document", "the files one document names, grouped: metadata files, preambles, filters"),
    "metadata.metadata": Omitted("document", "the files one document names, grouped: metadata files, preambles, filters"),
    "metadata.preamble": "options.preamble",
    "metadata.lua-filter": "options.lua-filter",
    "metadata.lua": "options.lua-filter",
    "parts": Omitted("document", "a document in parts (the folder setup will hold it per project)"),
    "max-asset-mb": "options.max-asset-mb", "max-output-mb": "options.max-output-mb", "soffice-timeout": "options.soffice-timeout", "diagram-timeout": "options.diagram-timeout",
    "serve-max-request-mb": "options.serve-max-request-mb",
    "no-auto": "options.no-auto",
    "auto": "options.auto.explicit-only", "auto.explicit-only": "options.auto.explicit-only", "auto.on": "options.auto.on",
    "office.latex": "options.office.latex", "office.labels": "options.office.labels",
    "office.reference-doc": "options.office.reference-doc",
    "office.profile": Omitted("document", "a house style's Word profile, named by the style's own metadata"),
    "office.fonts": WORD_ONLY, "office.style": WORD_ONLY, "office.styles": WORD_ONLY, "office.replace": WORD_ONLY,
    "office.title-page": WORD_ONLY, "office.media": WORD_ONLY, "office.papersize": WORD_ONLY,
    "office.geometry": WORD_ONLY, "office.margin": WORD_ONLY, "office.fontsize": WORD_ONLY,
    "office.mainfont": WORD_ONLY, "office.sansfont": WORD_ONLY, "office.monofont": WORD_ONLY,
    "office.CJKmainfont": WORD_ONLY, "office.linestretch": WORD_ONLY, "office.lang": WORD_ONLY,
    "office.indent": WORD_ONLY,
    "raw": "options.raw",
    "pagebreak": "options.pagebreak", "markup": "options.markup", "show-comments": "options.show-comments", "calc.enabled": "options.calc.enabled", "calc.digits": "options.calc.digits", "calc.round": "options.calc.round", "calc.subs": "options.calc.subs", "calc.typeset": "options.calc.typeset", "calc.typeset-upright": "options.calc.typeset-upright", "calc.typeset-italic": "options.calc.typeset-italic", "calc.noindent": "options.calc.noindent", "calc.space": "options.calc.space", "calc.align": "options.calc.align", "calc.constants": "options.calc.constants", "calc.export": "options.calc.export",
    "calc": "options.calc.enabled",
    "reader": "options.flavour",
    "flavour": "options.flavour", "flavor": "options.flavour",
    "unclosed-comment": "options.unclosed-comment",
    "single-newline": "options.single-newline",
    "embed-px-to-pt": "options.embed-px-to-pt", "embed-fit": "options.embed-fit", "embed-search": "options.embed-search",
    "seed-labels": "options.seed-labels", "seed-calc": "options.seed-calc",
    "metadata-precedence": "options.metadata-precedence",
    "metadata-append": "options.metadata-append",
    "path-style": "options.path-style", "path-up": "options.path-up",
    "found-style": "options.found-style", "ok-delimiter": "options.ok-delimiter",
    "rewrite": "options.rewrite", "rewrite-name": "options.rewrite-name", "rewrite_name": "options.rewrite-name",
    "preset": "options.preset", "global-metadata": "options.global-metadata",
    "editor": "options.editor",
    "stamp.enabled": "options.stamp.enabled", "stamp.mode": "options.stamp.mode", "stamp.store": "options.stamp.store",
    "stamp.partial": "options.stamp.partial", "stamp.restored-note": "options.stamp.restored-note", "stamp.restored_note": "options.stamp.restored-note",
    "stamp.packages": "options.stamp.packages", "stamp.scope": "options.stamp.scope",
    "stamp.include-output": "options.stamp.include-output", "stamp.include_output": "options.stamp.include-output",
    "stamp.pdf-metadata": "options.stamp.pdf-metadata", "stamp.pdf_metadata": "options.stamp.pdf-metadata",
    "strict": "options.strict", "build-time": "options.build-time", "time-format": "options.time-format",
    "page-folder": "options.page-folder",
    "report-build": "options.report-build", "report-titles": "options.report-titles",
    "build-log": "options.build-log", "build-log-keep": "options.build-log-keep", "build-log-max-size": "options.build-log-max-size",
    "strip-comments": "options.strip-comments",
    "column-widths": "options.column-widths", "table-widths": "options.column-widths",
    "column-word-floor": "options.column-word-floor", "table-word-floor": "options.column-word-floor",
    "column-word-floor-limit": "options.column-word-floor-limit",
    "column-outlier": "options.column-outlier", "column-outlier-rows": "options.column-outlier-rows",
    "column-outlier-length": "options.column-outlier-length", "column-count-raw-tex": "options.column-count-raw-tex",
    "text-to-markdown": "options.text-to-markdown",
    "unicode": "options.unicode",
    "tesseract-path": "options.tesseract-path", "soffice-path": "options.soffice-path", "dot-path": "options.dot-path",
    "mmdc-path": "options.mmdc-path", "poppler-path": "options.poppler-path",
    "pandoc-path": "options.pandoc-path", "typst-path": "options.typst-path", "chrome-path": "options.chrome-path",
}


# The feature (pdfmd_help topic) of the rows no flag sets, by key prefix; a row's flags give the rest. A row whose
# features are all switched off (`disabled:`) leaves the setup screen.
ROW_TOPICS = {
    "options.office.": "office", "options.gfm.": "markdown", "options.txt.": "markdown", "options.ascii.": "markdown",
    "options.csv.": "tables", "options.table-keep": "tables", "options.table-caption": "tables", "options.calc.": "markdown", "options.smiles.": "markdown", "options.pager": "view", "options.stamp.": "history", "options.backup.": "history", "options.line-number-step": "code",
    "options.bundle-max-mb": "source", "options.cache.": "cache", "options.unicode": "fonts",
}


def row_topics(flag_topics: dict[str, set[str]], keys) -> dict[str, set[str]]:
    """setting key -> the features it belongs to: the topics of the flags that set it (`flag_topics`: dest -> topics,
    from pdfmd's parser), else ROW_TOPICS."""
    found: dict[str, set[str]] = {}
    for dest, where in FLAGS.items():
        if isinstance(where, str):
            found.setdefault(where, set()).update(flag_topics.get(dest, set()))
    for key in keys:
        if not found.get(key):
            found[key] = {topic for prefix, topic in ROW_TOPICS.items() if key.startswith(prefix)}
    return found


def omitted_lines(flag_names: dict[str, str] | None = None, width: int = 110) -> list[str]:
    """What `--setup` leaves out, by reason, as the screens print it. `flag_names` maps a flag's dest to how it is
    written (`no_stamp` -> `--no-stamp`; pdfmd builds it from its parser)."""
    names = flag_names or {}
    lines: list[str] = []
    for reason, meaning in REASONS.items():
        # (note, flags, keys) in the order they first appear
        groups: dict[str, tuple[list[str], list[str]]] = {}
        for dest, where in FLAGS.items():
            if isinstance(where, Omitted) and where.reason == reason:
                groups.setdefault(where.note, ([], []))[0].append(names.get(dest, "--" + dest.replace("_", "-")))
        for key, where in OPTIONS.items():
            if isinstance(where, Omitted) and where.reason == reason:
                groups.setdefault(where.note, ([], []))[1].append(key)
        if not groups:
            continue
        lines += ["", meaning]
        for note, (flags, keys) in sorted(groups.items(), key=lambda item: item[0] != ""):
            words = [f"{flag}," for flag in flags]
            if keys:
                words += ["pdfmd-options"] + [f"{key}," for key in keys]
            words[-1] = words[-1].rstrip(",") + (":" if note else "")
            words += note.split()
            line = " "
            for word in words:
                if len(line) + len(word) + 1 > width and line.strip():
                    lines.append(line)
                    line = "   "
                line += " " + word
            lines.append(line)
    return lines
