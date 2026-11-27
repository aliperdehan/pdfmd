"""What `pdfmd --setup` can change: the settings of the global config file, and how to read and write them.

A setting is one key of the config file (`options.fallback` is `options:` / `fallback:`), with the values it
accepts and a line of help. Unset means "pdfmd's own default": the config file only ever holds what the
user chose, so deleting a line gives the default back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from pdfmd_base import spelling


@dataclass(frozen=True)
class Setting:
    key: str                          # dotted path into the config mapping
    title: str
    kind: str                         # "choice" | "multi" | "text" | "action" (runs something; stores nothing, shown only where pdfmd_setup.run is given it)
    choices: tuple[tuple[str, str], ...] = ()      # (value, what it means)
    default: str = ""                 # what pdfmd does when the key is not set (a choice value, or "" for none)
    help: str = ""
    section: str = ""
    store: str = "config"             # which file: "config" (config.yaml) or "metadata" (metadata.yaml beside it)
    check: str = ""                   # "number" for a text that must be one, "list" for a comma-separated list,
                                      # "count" for a positive whole number or `all`; "nonnegative" for a whole number including zero
    unset: str = ""                   # what pdfmd does when the key is not set, in words (see UNSET); the screens show it
    scope: str = "any"                # "machine": this computer only, never a folder's setup (see MACHINE)


ON_OFF = (("on", "yes"), ("off", "no"))

# What a build does when a setting is not set: the words the screens print beside "default", for every setting whose
# `default` is not itself one of its choices. Checked by tests/test_setup.py: a setting with neither is a bug.
UNSET = {
    "author": "none", "lang": "none",
    "papersize": "US Letter (A4 in WeasyPrint)", "fontsize": "10 pt LaTeX, 11 pt Typst",
    "geometry": "margin=1in for LaTeX documents, Beamer's own for slides",
    "mainfont": "STIX Two Text (or a serif with the letters)",
    "monofont": "JetBrains Mono (or Menlo)", "linestretch": "the engine's own",
    "options.properties.show": "false: print no properties",
    "options.properties.hide": "no keys hidden after selection",
    "options.properties.labels": "the keys as written",
    "options.pandoc-memory": "off (no heap cap)",
    "options.presentation": "off (ordinary documents)",
    "options.indent": "the writer's own (no first-line indent)",
    "options.paragraph-spacing": "the engine's own (none with indent: true)",
    "options.typst-line-spacing": "latex: LaTeX's line pitch",
    "options.figure-fit": "on: fit images and their captions to one page",
    "options.pagecite-terms": "p., pp.",
    "options.numbered-references": "on when the markers match a trailing source list (pdfmd and obsidian flavours)",
    "options.citation-aliases": "none",
    "options.flavour-overrides": "use the selected flavour's defaults",
    "options.excerpt-prefix": "x",
    "options.excerpt-page-terms": "p., pp.",
    "options.excerpt-quote-min-words": "3 words",
    "options.excerpt-overlap-words": "6 words",
    "options.bibliography-indent": "the writer's own (1.5em in Typst, which had none)",
    "options.bibliography-line-spacing": "off, writer defaults",
    "colorlinks": "off", "toc": "off",
    "options.unicode": "off (only for text the font lacks)", "translit": "Cyrillic only",
    "bibliography": "none", "csl": "Pandoc's Chicago author-date", "link-citations": "off",
    "options.attach-bibliography": "only the cited entries", "options.attach-csl": "off",
    "options.pdf-engine": "first installed: lualatex, xelatex, ...",
    "options.engine-fallback": "auto: the whole chain for a new PDF; for an existing one, its engine first, and an error in the document keeps it",
    "options.tex-repair": "auto: a broken TeX installation is mended for the run, with a NOTE",
    "options.html.self-contained": "off", "options.html.math": "MathML", "options.css-scope": "html", "options.css": "none",
    "options.odt.engine": "auto",
    "options.line-numbers": "off", "options.line-number-step": "1", "options.column-outlier": "2", "options.column-outlier-rows": "4", "options.column-outlier-length": "30", "options.column-word-floor-limit": "16", "options.column-ceil-margin": "25%",
    "options.table-chars": "95 (fallback when the layout cannot be estimated)",
    "options.table-row-spacing": "1.4",
    "options.header": "none", "options.footer": "none", "options.bookmarks": "off", "options.attach-links": "off",
    "options.stamp.enabled": "off", "options.backup.enabled": "off",
    "options.backup.dir": ".backups (or an existing backup/)",
    "options.strip-comments": "off", "options.hybrid": "off",
    "options.shrink": "on: object streams and recompression, when qpdf, pikepdf or mutool is installed", "options.shrink-timeout": "120 seconds",
    "options.smiles.engine": "auto", "options.smiles.format": "auto", "options.smiles.office-format": "png", "options.smiles.palette": "colour", "options.smiles.cell-width": "250", "options.smiles.cell-height": "200", "options.smiles.per-row": "3", "options.smiles.bond-length": "40", "options.smiles.dpi": "300",
    "options.raw": "off", "options.pagebreak": "every family, in the pdfmd and obsidian flavours", "options.markup": "all but space, in the pdfmd and obsidian flavours", "options.show-comments": "off", "options.show-hidden": "off", "options.calc.enabled": "on", "options.calc.digits": "as R prints (up to 7 figures)", "options.calc.round": "even", "options.calc.subs": "off", "options.calc.typeset": "off", "options.calc.typeset-upright": "none", "options.calc.typeset-italic": "none", "options.calc.noindent": "lines", "options.calc.space": "0.75em", "options.calc.align": "left", "options.calc.constants": "none", "options.calc.export": "none", "options.attach-source": "off",
    "options.bundle": "the files the text reads (LaTeX inputs, data), not images", "options.bundle-max-mb": "100",
    "options.cache.aux": "off", "options.text-to-markdown": "off",
    "options.lua-filter": "none", "options.lua-filter-before-citeproc": "none", "options.preamble": "none",
    "options.crop": "off",
    "options.crop-pad": "2 pt", "options.crop-ignore-bottom": "0 pt", "options.crop-page": "all pages",
    "options.image-quality": "90", "options.default-output": "pdf",
    "options.no-auto": "nothing switched off", "options.auto.explicit-only": "none", "options.auto.on": "none",
    "options.dialect-detect": "basic", "options.flavour": "auto: obsidian in a vault, pdfmd elsewhere", "options.embed-px-to-pt": "0.75 (1 CSS pixel)", "options.embed-fit": "text-width", "options.embed-search": "vault", "options.single-newline": "the flavour's: a line break in obsidian (or as the vault says), a space elsewhere", "options.unclosed-comment": "hide in an Obsidian vault (the rest of the note, as Obsidian does), keep elsewhere",
    "options.page-numbers": "keep the writer's page numbering",
    "options.page-folder": "on", "options.report-build": "route", "options.report-titles": "chapters", "options.strict": "off", "options.build-time": "on", "options.time-format": "auto", "options.build-log": "on", "options.build-log-keep": "5", "options.build-log-max-size": "512 KB", "options.max-asset-mb": "no limit", "options.max-output-mb": "no limit", "options.soffice-timeout": "300 seconds", "options.diagram-timeout": "120 seconds", "options.image-dpi": "192 embedded SVG; 300 exported page", "options.serve-max-request-mb": "100 MB", "options.download-retries": "2 extra tries",
    "options.chatter": "normal", "options.mute": "none", "options.log": "none", "options.summary": "off",
    "options.check-ignore": "none",
    "options.html.standalone": "off (a page fragment)", "options.html.css": "none",
    "options.office.reference-doc": "one beside the document, else Pandoc's",
    "options.keep-source": "off",
    "options.stamp.packages": "none", "options.stamp.include-output": "off", "options.stamp.pdf-metadata": "on", "options.stamp.partial": "off (a partial build leaves no entry)",
    "options.backup.format": "compact (report.md.bak.20260924091500)", "options.backup.keep": "all of them", "options.backup.pdfs": "none (only the source is kept)",
    "options.bundle-packages": "off", "options.cache.plots": "off", "options.cache.max-mb": "1000 (1 GB)",
    "options.csv.enabled": "on", "options.csv.rows": "10", "options.csv.cols": "7", "options.table-keep": "the filter's own (10)", "options.table-ascii": "repair", "options.cell-align": "on", "options.table-tag-brackets": "angle, amp", "options.table-align": "the column's own", "options.table-valign": "top (the baseline of the row)", "options.md-macro": "on", "options.linebreak": "every spelling, inside table cells only", "options.table-captions": "note", "options.table-caption-label": "strip", "options.table-caption-need-label": "on", "options.table-caption-colon-words": "0 (off)", "options.table-caption-words": "the document language's word, and Table", "options.pager": "on",
    "options.pager_command": "$PDFMD_PAGER, $PAGER, else less -FRX",
    "options.tesseract-path": "PATH, then the usual install folders", "options.soffice-path": "PATH, then the usual install folders",
    "options.dot-path": "PATH, then the usual install folders", "options.mmdc-path": "PATH, then npm's global folder",
    "options.poppler-path": "PATH, then the usual install folders",
    "options.ghostscript-path": "PATH, then the usual install folders", "options.mutool-path": "PATH, then App Paths on Windows",
    "options.pandoc-path": "PATH, then the usual install folders", "options.typst-path": "PATH, then the usual install folders",
    "options.chrome-path": "PATH, then the usual install folders",
    "user-path": "nothing changed until you choose it", "kits": "kits/ folders above the document, then the TeX tree", "options.kit": "no kit", "options.kit-stack": "off (--kit replaces every kit setting)", "options.metadata-append": "nothing appends (a document value replaces)", "options.path-style": "auto", "options.path-up": "2", "options.metadata-parents": "1 (one parent above the scaffold or document folder)",
    "disabled": "nothing switched off",
    "options.ok-delimiter": ">",
    "options.rewrite": "on (the old file is replaced)", "options.rewrite-name": "{stem} ({n}){ext}",
    "options.editor": "the built-in editor", "options.preset": "metadata.yaml", "options.global-metadata": "on",
}

# Settings that belong to this computer, not to a folder: a folder's setup (pdfmd --setup DIR) cannot set them.
MACHINE = frozenset({"setup-ui", "translit", "disabled", "user-path", "kits", "options.cache.max-mb"})

# What `pdfmd --setup DIR` offers (v3.29.29), by the key of the row: the `options:` a document's build reads through its folder
# layers (first_pdfmd_option / option_sources, or config_options(document)), and the metadata rows below. A row that is not here
# is read from the global config alone (the polish keys at the start of a run, the output formats' own tables, a path relative
# to a place that is not the document's ...): the folder screen leaves it out and says so instead of offering a row that would
# change nothing. tests/test_setup_folder.py walks this list against the folder layers.
FOLDER_OPTIONS = frozenset({
    "options.pandoc-path", "options.typst-path", "options.chrome-path", "options.tesseract-path",
    "options.soffice-path", "options.dot-path", "options.mmdc-path", "options.poppler-path",
    "options.ghostscript-path", "options.mutool-path",
    "options.global-metadata", "options.preset", "options.rewrite", "options.rewrite-name", "options.fallback", "options.missing", "options.citation-engine",
    "options.numbered-references", "options.csl-fallback", "options.fullcite-list", "options.attach-bibliography", "options.pdf-engine", "options.engine-fallback", "options.tex-repair", "options.pandoc-memory", "options.css-scope", "options.indent", "options.paragraph-spacing", "options.bibliography-indent",
    "options.typst-line-spacing", "options.figure-fit", "options.page-numbers",
    "options.bibliography-line-spacing",
    "options.properties.show", "options.properties.hide", "options.properties.labels",
    "options.properties.place", "options.properties.style",
    "options.csv.enabled", "options.csv.rows", "options.csv.cols", "options.csv.cut", "options.csv.note", "options.csv.delimiter", "options.table-keep", "options.table-ascii", "options.cell-align", "options.table-tag-brackets", "options.table-align", "options.table-valign", "options.md-macro", "options.linebreak", "options.table-captions", "options.table-caption-label", "options.table-caption-need-label", "options.table-caption-colon-words", "options.table-caption-words", "options.pager", "options.pager_command",
    "options.code-wrap", "options.line-numbers", "options.line-number-step", "options.office.latex", "options.office.labels",
    "options.keep-source", "options.hybrid", "options.shrink", "options.shrink-timeout", "options.odt.engine",
    "options.stamp.enabled", "options.stamp.store", "options.stamp.mode", "options.stamp.scope", "options.stamp.packages",
    "options.stamp.include-output", "options.stamp.pdf-metadata", "options.stamp.restored-note", "options.stamp.partial",
    "options.backup.enabled", "options.backup.format", "options.backup.keep", "options.backup.pdfs",
    "options.attach-source", "options.attach-csl", "options.bundle", "options.bundle-packages", "options.bundle-max-mb",
    "options.strip-comments", "options.cache.aux", "options.cache.plots", "options.cache.location", "options.seed-labels", "options.seed-calc",
    "options.smiles.engine", "options.smiles.format", "options.smiles.office-format", "options.smiles.palette", "options.smiles.cell-width", "options.smiles.cell-height", "options.smiles.per-row", "options.smiles.bond-length", "options.smiles.dpi",
    "options.flavour", "options.flavour-overrides", "options.dialect-detect", "options.single-newline", "options.unclosed-comment", "options.embed-px-to-pt", "options.embed-fit", "options.embed-search", "options.raw", "options.pagebreak", "options.show-hidden", "options.show-comments", "options.markup", "options.calc.enabled", "options.calc.digits", "options.calc.round", "options.calc.subs", "options.calc.typeset", "options.calc.typeset-upright", "options.calc.typeset-italic", "options.calc.noindent", "options.calc.space", "options.calc.align", "options.calc.constants", "options.calc.export", "options.page-folder", "options.report-build", "options.report-titles", "options.strict",
    "options.chatter", "options.mute", "options.log", "options.summary", "options.max-asset-mb", "options.max-output-mb",
    "options.check-ignore", "options.build-time", "options.time-format",
    "options.image-dpi", "options.build-log", "options.build-log-keep", "options.build-log-max-size", "options.soffice-timeout", "options.diagram-timeout",
    "options.no-auto", "options.auto.explicit-only", "options.auto.on", "options.kit", "options.kit-stack", "options.metadata-append", "options.metadata-parents",
    "options.path-style", "options.path-up", "options.ranking.by", "options.ranking.names",
})
# metadata rows whose value is a path: Pandoc takes it from the metadata file's own folder, which for a folder's setup is
# `.pdfmd`, not the document's (the author has not decided that yet)
FOLDER_PATH_ROWS = frozenset({"bibliography", "csl"})


def folder_split(settings: list["Setting"]) -> tuple[list["Setting"], list["Setting"]]:
    """(the rows a folder's setup offers, the rows it leaves out) of ``settings``."""
    kept = [setting for setting in settings
            if setting.scope != "machine" and (
                setting.key in FOLDER_OPTIONS or (setting.store == "metadata" and setting.key not in FOLDER_PATH_ROWS))]
    return kept, [setting for setting in settings if setting not in kept]

# `auto:` (v3.29.30) says, for a kind, `on`, `off` or `explicit-only`; the two rows above write the last and the first, `no-auto` the list of off
AUTO_EXPLICIT_CHOICES = ("lua", "preamble", "metadata", "bib")
AUTO_ROWS = {"options.auto.explicit-only": "explicit", "options.auto.on": "on"}
AUTO_WORDS = {"on": "on", "true": "on", "yes": "on", "explicit-only": "explicit", "explicit": "explicit", "named": "explicit"}

TRANSLIT = (("greek", "Greek"), ("armenian", "Armenian"), ("georgian", "Georgian"), ("hebrew", "Hebrew"),
            ("arabic", "Arabic"), ("hangul", "Korean (needs the translit extra)"), ("kana", "Japanese kana"),
            ("han", "Chinese (needs the translit extra)"), ("other", "any other script"))

AUTO_HELP = {
    "bib": "find local bibliography files for missing citation keys",
    "reader": "read Markdown without front matter as GitHub-flavoured", "title": "promote a leading `# Title`",
    "margin": "1-inch margins", "mainfont": "a default main font", "monofont": "a default code font", "mathfont": "the math font that goes with the default main font",
    "font": "both font defaults", "tablewidth": "balance wide table columns", "metadata": "metadata.yaml discovery",
    "yaml": "metadata.yaml discovery", "preamble": "preamble.tex discovery", "tex": "preamble.tex discovery",
    "lua": "Lua filter discovery", "files": "metadata, preamble and filter discovery", "standalone": "--standalone",
    "texdirect": "compile .tex directly with LaTeX", "officedirect": "convert office files with LibreOffice",
    "svg": "convert SVG images for LaTeX", "remoteimages": "fetch and keep remote images", "pdfimages": "show PDF images in HTML builds (as SVG)", "texpackages": "load mhchem/siunitx when \\ce or \\SI needs it", "draftpictures": "skip the pictures in the draft pass for part numbers", "remotecsl": "fetch a csl: style named by URL", "mathjax": "MathJax for the math of WeasyPrint PDFs (KaTeX or text instead)", "typstdirect": "build .typ files with Typst directly", "htmldirect": "build .html files with WeasyPrint or a browser directly",
    "pagecite": "bare page markers after citations",
    "excerpts": "local excerpt citation markers",
    "crossref": "pandoc-crossref for @fig: references", "citationengine": "citeproc / biblatex choice",
    "csvtable": "tables from CSV files", "papersize": "fix `pagesize:` to `papersize:`", "parts": "report/book parts",
    "lookup": "find a document by a name that is not exact", "unicode": "fonts for other scripts",
    "officeref": "a reference .docx/.odt found beside the document", "officestyle": "pdfmd's look in Word files",
    "officelatex": "make LaTeX native (or a picture) in Word files", "codewrap": "wrapping inline code and code blocks, numbering block lines (LaTeX)", "officeprofile": "a house style's Word profile",
    "priority": "choose one of several documents by priority and by name (bare pdfmd)",
    "kit": "a package's pdfmd helper file from a kit", "kpsewhich": "a package's pdfmd helper file from the installed copy",
}


# the kinds of pdfmd.MARKUP_KINDS, in its order
MARKUP_CHOICES = (
    ("callouts", "> [!NOTE], > [!warning] Title, ::: note: a box (LaTeX, Typst), a styled div (HTML), a quote (the rest)"),
    ("toc", "[TOC], [[_TOC_]], <!-- toc -->: the table of contents where it stands"),
    ("centre", "<center>, <div align=center>, ::: centre, \\begin{center}: centred text in LaTeX, Typst, HTML, Word and OpenDocument"),
    ("highlight", "==marked text==: highlighted in LaTeX (soul), Typst, HTML, Word and OpenDocument"),
    ("underline", "<u>text</u>, <ins>text</ins>: underlined in LaTeX (soul), Typst, HTML, Word and OpenDocument"),
    ("spans", "[text]{.caps}, [text]{.wavy}, [text]{.dotted}: uppercase text and styled underlines"),
    ("keep", "::: keep, break-inside: avoid, \\begin{samepage}: blocks held on one page in LaTeX, Typst, HTML and Word"),
    ("landscape", "::: landscape, \\begin{landscape}: the blocks on landscape pages in LaTeX, Typst, HTML, Word and OpenDocument"),
    ("appendix", "\\appendix, <!-- appendix -->, {.appendix}: the sections after it lettered A, B (LaTeX, Typst; with --number-sections)"),
    ("fullcite", "[@key]{.fullcite}, [[fullcite:key]], ::: fullcite: the formatted reference of a source where it stands (citeproc)"),
    ("pagecite", "[p. 5] after a citation: that source’s page (off unless pagecite: auto or a mode is set)"),
    ("excerpts", "[@x:1] uses the source and locator from excerpts.json"),
    ("space", "\\vspace{1cm}, \\bigskip, <br><br>, #v(1cm) alone on a line: vertical space in every format"),
)


# the families of pdfmd.PAGEBREAK_KINDS, in its order
PAGEBREAK_CHOICES = (
    ("comment", "<!-- pagebreak -->, <!-- newpage -->, <!-- pdfmd: pagebreak -->"),
    ("tex", "\\newpage, \\pagebreak, \\clearpage, \\cleardoublepage"),
    ("html", '<div style="page-break-after: always">, <div class="pagebreak">'),
    ("div", "an empty ::: pagebreak"),
    ("typst", "a raw Typst #pagebreak()"),
    ("word", "a raw Word page break"),
)


# the families of pdfmd.LINEBREAK_KINDS, in its order
LINEBREAK_CHOICES = (
    ("html", "<br>, <br/>, <br />"),
    ("tex", "a raw \\newline, \\linebreak, \\linebreak[2]"),
    ("typst", "a raw Typst #linebreak()"),
    ("word", "a raw Word line break"),
    ("context", "a raw ConTeXt \\crlf"),
)


def feature_choices() -> tuple[tuple[str, str], ...]:
    """The features (topics of pdfmd_help) the config can switch off, with what each covers."""
    try:
        from pdfmd_help import DISABLEABLE, TOPICS
    except ImportError:
        return ()
    return tuple((topic, TOPICS[topic][0]) for topic in DISABLEABLE)


def settings_for(no_auto_kinds, setup_ui_choices=("plain", "fancy")) -> list[Setting]:
    """The settings, grouped by `section`. `no_auto_kinds` are the names `--no-auto` accepts."""
    def choice(key, title, choices, default="", help="", section="", store="config"):
        return Setting(key, title, "choice", tuple(choices), default, help, section, store)

    def text(key, title, help="", section="", store="config", check=""):
        return Setting(key, title, "text", (), "", help, section, store, check)

    on_off = ON_OFF
    return [replace(setting, unset=UNSET.get(setting.key, ""), scope="machine" if setting.key in MACHINE else "any")
            for setting in _settings(choice, text, no_auto_kinds, setup_ui_choices, on_off)]


def _settings(choice, text, no_auto_kinds, setup_ui_choices, on_off) -> list[Setting]:
    return [
        # -- what every document gets (metadata.yaml beside the config file)
        text("author", "Author", "Put in every document that names none.", "Every document (global metadata)", "metadata"),
        text("lang", "Language", "A BCP 47 tag: en-GB, ru, kk.", "Every document (global metadata)", "metadata"),
        choice("papersize", "Paper size", (("a4", "A4"), ("letter", "US Letter"), ("a5", "A5"), ("legal", "Legal")), "",
               "", "Every document (global metadata)", "metadata"),
        choice("fontsize", "Font size", (("10pt", "10 pt"), ("11pt", "11 pt"), ("12pt", "12 pt")), "", "",
               "Every document (global metadata)", "metadata"),
        text("geometry", "Page geometry", "Pandoc's geometry, e.g. margin=2.5cm (pdfmd's own default is margin=1in).",
             "Every document (global metadata)", "metadata"),
        text("mainfont", "Main font", "A font name; without one pdfmd picks STIX Two Text or a serif that has the letters.",
             "Every document (global metadata)", "metadata"),
        text("monofont", "Code font", "Without one pdfmd picks JetBrains Mono or Menlo.", "Every document (global metadata)",
             "metadata"),
        text("linestretch", "Line spacing", "A factor: 1.15, 1.5.", "Every document (global metadata)", "metadata", "number"),
        choice("options.typst-line-spacing", "Typst line spacing", (("latex", "LaTeX"), ("pandoc", "Pandoc")), "latex",
               "LaTeX's line pitch (the default), or Pandoc's own Typst template spacing without pdfmd's text-edge, leading "
               "or paragraph-spacing rules.", "Every document (global metadata)"),
        choice("options.page-numbers", "Page numbers", on_off, "",
               "Keep the writer's numbering by default. Off suppresses it in LaTeX, Typst, Calibre, Word and OpenDocument. "
               "A Markdown --crop build suppresses it unless you give --page-numbers.", "Every document (global metadata)"),
        choice("options.figure-fit", "Figures that are too tall for the page", (("on", "shrink to fit"), ("off", "keep size")), "on",
               "LaTeX and Typst shrink the images proportionally and keep the full-size caption on the same page. "
               "Typst still warns when fitting is off and a figure is too tall. An image's fit=on or fit=off overrides "
               "the document for its figure.", "Every document (global metadata)"),
        text("options.pandoc-memory", "Pandoc memory cap",
             "Optional heap size, e.g. 512m or 2g (whole k, m or g units). Empty: off. Passed to every Pandoc as "
             "+RTS -M<size> -RTS. A heap overflow names pdfmd-options.pandoc-memory.", "Every document (global metadata)"),
        text("options.indent", "First-line paragraph indent",
             "False or unset keeps the writer's default; true keeps each writer's standard indent (LaTeX the class's, Typst 1.5em, Word 0.25in, HTML none), or a length such as 0.5in, 3em, 1cm. "
             "LaTeX, Typst, Word and HTML. Also indent: in front matter.", "Every document (global metadata)"),
        text("options.paragraph-spacing", "Space between paragraphs",
             "Added to the line spacing at a paragraph break: a length (6pt, 1em, 2mm; units pt, mm, cm, in, em), 0 for none, "
             "or auto. LaTeX and Typst; the HTML engines take it from a style sheet. Empty: each engine's own (none with "
             "indent: true). Per run: --paragraph-spacing.", "Every document (global metadata)"),
        text("options.bibliography-indent", "Hanging indent of references",
             "How far the lines of a reference after its first are set in, in the reference list and in the entries `fullcite` places: "
             "a length (0.5in, 1.5em; units pt, mm, cm, in, em), 0 for none, or auto. Only a style that asks for a hanging indent has "
             "one. Empty: each writer's own (LaTeX 1.5em, HTML 2em, Word 0.5in) and, for Typst, whose writer had none, 1.5em; a "
             "value is applied the same in every writer. Per run: --bibliography-indent.", "Every document (global metadata)"),
        text("options.bibliography-line-spacing", "Line spacing of references",
             "Off leaves the writer's own spacing. Style uses CSL line-spacing. A positive factor such as 1 or 1.5 "
             "sets the spacing in LaTeX, Typst, Word and HTML.", "Every document (global metadata)"),
        choice("colorlinks", "Coloured links", on_off, "", "Metadata accepts colourlinks or Pandoc's colorlinks.", "Every document (global metadata)", "metadata"),
        choice("toc", "Table of contents", on_off, "", "", "Every document (global metadata)", "metadata"),
        choice("options.global-metadata", "Use the global metadata above", on_off, "",
               "Off: no document gets the rows above (nor a preset). Per run: --no-global-metadata / --global-metadata; "
               "per document: pdfmd-options.global-metadata.", "Every document (global metadata)"),
        text("options.preset", "Which set of global metadata",
             "A preset: a file in the presets/ folder beside the config (lab, or lab.yaml), or a path; `none` = no global "
             "metadata. Edit one with `pdfmd --setup --preset lab`. Per run: --preset.",
             "Every document (global metadata)"),
        # -- fonts and characters
        choice("options.fallback", "Characters the font lacks",
               (("word", "set the whole word in another font"), ("char", "set just those characters in another font"),
                ("document", "the one font that draws most of the document becomes the main font"),
                ("off", "nothing: what Pandoc and TeX do without pdfmd"), ("box", "no fallback; boxes"),
                ("error", "the build fails, listing the characters")), "word",
               "What to do about characters the main font cannot draw.", "Fonts and characters"),
        choice("options.missing", "Characters no font draws",
               (("warn", "warn and go on"), ("box", "draw a box"), ("error", "fail the build")), "warn",
               "What to do about characters no installed font draws, after the fallback.", "Fonts and characters"),
        choice("options.unicode", "Fonts for other scripts", on_off, "",
               "Set Arabic, Han, Greek... runs in an installed font for their script even when the main font has them.",
               "Fonts and characters"),
        Setting("translit", "Finding a document by a Latin spelling", "multi", TRANSLIT, "",
                "Romanization packs for finding 命運.md when told `mingyun` (Cyrillic is always on).",
                "Fonts and characters"),
        # -- which document bare pdfmd builds
        choice("options.ranking.by", "Equal priority, when bare pdfmd must choose a document",
               (("priority, newest", "the newest file is built, with a warning"),
                ("priority, oldest", "the oldest file is built, with a warning"),
                ("priority", "an error naming the files")), "priority, newest",
               "Documents rank by their priority: and by their names (report.final over report.md); this settles the rest.",
               "Input"),
        choice("options.ranking.names", "Names that rank versions of a document (report.final, report_draft)",
               (("family", "only among a document's own versions"), ("folder", "against every document of the folder"),
                ("off", "names are not read")), "family", "", "Input"),
        # -- citations
        choice("options.citation-engine", "Citation engine",
               (("citeproc", "Pandoc's citeproc (the default)"), ("natbib", "natbib / BibTeX"),
                ("biblatex", "biblatex / biber")), "citeproc", "", "Citations"),
        text("options.citation-aliases", "Citation key aliases", "A YAML mapping, e.g. {short: existing-key}.",
             "Citations", check="citation-aliases"),
        choice("options.numbered-references", "Convert numbered source lists to citations",
               (("on", "when the markers match a trailing numbered source list"),
                ("off", "leave the Markdown as written")), "",
               "On by default in pdfmd and obsidian, off in pandoc, gfm and commonmark. Set on or off to override.", "Citations"),
        choice("options.pagecite", "Page markers after citations",
               (("off", "leave them as text (the default)"), ("auto", "the CSL style chooses"),
                ("style", "a real citation with its locator"), ("page", "pages in the style’s brackets"),
                ("drop", "remove the marker"), ("bare", "alias for page"), ("full", "alias for style")),
               "off", "A bare [p. 5] refers to the last source in the same paragraph. Per run: --pagecite MODE.", "Citations"),
        text("options.pagecite-terms", "Page marker terms", "A list, e.g. p., pp., S.; replaces the default p., pp.",
             "Citations", check="list"),
        text("options.excerpt-prefix", "Short excerpt marker prefix",
             "One word of letters, digits, - or _. Reserved: fig, tbl, eq, sec, lst.", "Citations"),
        text("options.excerpt-page-terms", "Excerpt page terms",
             "The singular and plural locator terms, e.g. p., pp.", "Citations", check="list"),
        choice("options.excerpt-repeat", "Repeated excerpt citations",
               (("full", "keep the full citation"), ("page", "use the page form when pagecite gives one")),
               "full", "Applies after a citation of the same source in the same paragraph.", "Citations"),
        text("options.excerpt-quote-min-words", "Minimum words in a quotation to check",
             "A positive whole number, default 3.", "Citations", check="positive"),
        text("options.excerpt-overlap-words", "Minimum unquoted words in a row to check",
             "A non-negative whole number, default 6. Enter 0 to switch the check off.", "Citations", check="nonnegative"),
        choice("options.fullcite-list", "The combined reference list when entries were placed with `[@key]{.fullcite}`",
               (("rest", "the placed entries leave it (the list goes when none is left)"), ("all", "it stays whole"),
                ("none", "no combined list")), "rest",
               "`[@key]{.fullcite}`, `[[fullcite:key]]` and `::: fullcite` print the formatted reference where they stand (the markup "
               "kind `fullcite`). One entry or block says otherwise with `list=keep` / `list=drop`. Per run: --fullcite-list.",
               "Citations"),
        text("bibliography", "Bibliography file", "A .bib or .json; every document without its own uses it.", "Citations",
             "metadata"),
        text("csl", "Citation style (CSL)", "A .csl file or its name.", "Citations", "metadata"),
        choice("options.csl-fallback", "When a csl: URL cannot be fetched",
               (("default", "Pandoc's default style, with a warning"), ("error", "stop")), "default",
               "A style named by URL is fetched once and kept; offline, pdfmd takes that copy, else one of the same name "
               "in Pandoc's csl/ folder (with a warning), and only then this.", "Citations"),
        choice("link-citations", "Link citations to the list", on_off, "", "", "Citations", "metadata"),
        choice("options.attach-bibliography", "A bibliography attached to the PDF",
               (("all", "every entry (the file as it is)"),), "", "By default only the entries the text cites travel.",
               "Citations"),
        # -- output
        choice("options.pdf-engine", "PDF engine",
               (("lualatex", "LuaLaTeX"), ("xelatex", "XeLaTeX"), ("pdflatex", "pdfLaTeX"),
                ("typst", "Typst (only Typst, no fallback to others)"), ("weasyprint", "WeasyPrint (HTML)"),
                ("calibre", "Calibre's ebook-convert (only when named, no fallback)"), ("tex", "only TeX engines"), ("html", "only HTML engines"), ("office", "only the LibreOffice route")), "",
               "The engine to try first (a family limits the fallback chain). `-e` on the command line wins.", "Output"),
        choice("options.engine-fallback", "When a PDF engine fails",
               (("auto", "a new PDF: any failure tries the next engine; an existing one: start with the engine that made it, "
                         "as missing"),
                ("on", "any failure tries the next engine"),
                ("missing", "only an engine that cannot run here falls through; an error in the document stops the build and "
                            "keeps the PDF already there"),
                ("off", "the first failure stops the build")), "",
               "A stopped build exits 1 and leaves the existing PDF as it was. A pinned engine (-e, pdf-engine) is never "
               "reordered. Per run: --engine-fallback MODE.", "Output"),
        choice("options.tex-repair", "Mend a broken TeX installation for the run",
               (("auto", "what is broken in the TeX installation (a missing package or font loader, a cache that cannot be "
                         "used, a stale Biber cache) is worked around for this run only, with a NOTE for each"),
                ("off", "nothing is mended: the engine fails as the installation says")), "",
               "The TeX installation and its caches are never changed: the build skips an engine, puts a stand-in file or a "
               "scratch cache folder on its own search path, or runs a tool again. --strict counts a repaired build as a "
               "warning. Per document: `tex-repair` in `pdfmd-options`.", "Output"),
        text("options.editor", "Editor for pdfmd --edit",
             "A command: code --wait, vim, \"nano -l\". Without one --edit uses its built-in editor (pdfmd --install tui). "
             "Per run: --editor.", "Output"),
        text("options.properties.show", "Print front-matter properties",
             "false, true (skip internal, title, layout and empty keys), all, or a list of keys in display order.",
             "Output", check="properties-show"),
        text("options.properties.hide", "Property keys to hide", "A comma-separated list of keys to remove after show.",
             "Output", check="list"),
        text("options.properties.labels", "Property labels", "A YAML mapping, e.g. {stage: Stage of review}.",
             "Output", check="properties-labels"),
        choice("options.properties.place", "Place of property block",
               (("top", "after the title block"), ("end", "at the end")), "top", "", "Output"),
        choice("options.properties.style", "Style of property block",
               (("table", "two columns"), ("list", "a bulleted list"), ("inline", "one line")), "table", "", "Output"),
        text("options.default-output", "Default output formats",
             "A format name or comma-separated list (e.g. pdf, png, html) when the command line names no format.",
             "Output", check="list"),
        choice("options.presentation", "Build Beamer slides", on_off, "",
               "Per document use pdfmd-options.presentation. Per run use -p or --no-presentation.", "Output"),
        choice("options.apply-defaults", "Defaults for .typ and .html files", (("true", "apply metadata.yaml's title, author, font, paper, margin"), ("false", "build them as they are")), "false",
               "A .typ or .html file is built by its own engine and gets no defaults. Per run: --apply-defaults.", "Output"),
        choice("options.odt.engine", "OpenDocument writer",
               (("auto", "LibreOffice from Word; Pandoc if unavailable or an OpenDocument reference is chosen"),
                ("soffice", "LibreOffice from Word (required)"), ("pandoc", "Pandoc's OpenDocument writer")),
               "", "Auto keeps raw Word blocks (a cover or form) and the Word route's extras; a failed conversion falls "
               "back to Pandoc with a warning. An .odt/.ott reference selects Pandoc in auto. Per document: odt.engine; "
               "-e soffice / -e pandoc wins.", "Output"),
        # -- HTML
        choice("options.html.self-contained", "HTML as one file", on_off, "", "Everything inlined (--embed-resources).",
               "HTML"),
        choice("options.html.standalone", "HTML as a full page", on_off, "",
               "A whole page with <head> (--standalone), not a fragment to paste into one.", "HTML"),
        text("options.html.css", "Style sheet for HTML", "A .css file; an absolute path, or one read beside each document.",
             "HTML"),
        text("options.css", "Style sheet for every document",
             "A .css file (an absolute path, or one read beside each document): linked by the HTML writers, and with the "
             "scope below read for the other writers too. A document's own pdfmd.css or NAME.css comes after it.", "HTML"),
        choice("options.css-scope", "What a style sheet is for",
               (("html", "the writers that read CSS"), ("all", "and the paper, margins, body font and size, line spacing, "
                                                     "link colour and code font of LaTeX, Typst and Word")),
               "", "`all` reads @page, body, a and code rules (@media print counts, @media screen does not), below what the "
               "document, its metadata and the command line set. Per run: --css-scope.", "HTML"),
        choice("options.html.math", "Math in HTML",
               (("mathml", "MathML (no network)"), ("mathjax", "MathJax"), ("katex", "KaTeX"), ("webtex", "WebTeX images"),
                ("plain", "plain text")), "", "", "HTML"),
        # -- tables
        choice("options.csv.enabled", "Build a table from a ::: {.csv} div", on_off, "",
               "On unless set to off. Off leaves the div as written, a plain div with its text, and no WARN: for a document that "
               "shows CSV lines as text. Per run: --csv / --no-csv.", "Tables"),
        text("options.csv.rows", "Rows a .csv table shows", "A whole number, or all. A div's rows= wins. Per run: --csv-rows.",
             "Tables", "config", "count"),
        text("options.csv.cols", "Columns a .csv table shows", "A whole number, or all. A div's cols= wins. Per run: --csv-cols.",
             "Tables", "config", "count"),
        text("options.table-keep", "Rows a table keeps on one page",
             "A whole number, 0 to let every table break. For a Lua filter that reads tablekeep (nulabreport.lua). Per run: --table-keep.",
             "Tables", "config", "nonnegative"),
        choice("options.table-ascii", "A text table Pandoc cannot read (ASCII without inner `+`, box-drawing, psql, MySQL, Org-mode), as a pipe table",
               (("repair", "rewrite it as a pipe table (a temporary copy, the file is not touched), with a WARN for each"),
                ("note", "leave it, and say so"), ("off", "leave it, silently")), "repair",
               "What chat models write for a plain-text table (`+-----+` borders, no inner `+`; `+-+` and `1 | 2` rows work too), a "
               "box-drawing table (`┌─┬─┐ │ ├─┼─┤`), psql output (`a | b`, `---+---`), MySQL console output (no header rule), Org-mode tables (`|---+---|`, `<r>` cookies, `#+CAPTION:`) and `|` lines with no separator row. The first "
               "row is the header, wrapped cell lines are joined, bar positions are not trusted. A real grid table (`+---+---+`) is "
               "never touched.", "Tables"),
        choice("options.cell-align", "Cell tags in a pipe table: one cell's alignment, and merged cells",
               (("on", "read the tags: `<c>`, `&mc&`, `&<<&`, a bare `<<` or `^^`"), ("off", "leave the cells as written")), "on",
               "`| <c> total | &r& 12 | << |`: a tag anywhere in a cell sets that cell's alignment, whatever its column's; an arrow "
               "merges the cell with its neighbour. A pipe table's separator row (`:--`, `:-:`, `--:`) sets whole columns. HTML, Typst, "
               "Word and the rest use the cell's own alignment and spans; LaTeX gets `\\multicolumn`, `\\multirow` and raw TeX around "
               "the cell. The Markdown writers write the tags back as `&...&`.", "Tables"),
        choice("options.table-align", "Horizontal alignment of every table cell that has no other",
               (("", "the column's own (its `:--:` in the separator row)"), ("left", "left"), ("centre", "centred"), ("right", "right")), "",
               "The lowest tier, under a cell's tag, its row's and column's `{row2.align=r}` / `{col3.align=c}`, the column's `:--:` and the table's own "
               "`{align=c}`. Per table: the attribute line under it.", "Tables"),
        choice("options.table-valign", "Vertical alignment of every table cell that has no other",
               (("", "the top (the baseline of the row)"), ("top", "the top of the row"), ("middle", "the middle of the row"),
                ("bottom", "the bottom of the row")), "",
               "Setting it draws every table of a LaTeX build as a tabularray `longtblr`; a cell's tag (`&b&`), a row's or column's "
               "`{row2.valign=m}` and the table's own `{valign=m}` win over it. HTML gets `vertical-align`; Typst and Word do not draw it yet.", "Tables"),
        text("options.table-tag-brackets", "Which spellings of a cell tag are read",
             "Words separated by commas: `angle` (`<c>`, `<merge-up, top>`), `amp` (`&mc&`, the form that never clashes), `brace` "
             "(`{mc}`) and `guillemet` (`\u00abmc\u00bb`). The default is `angle, amp`; `brace` is off because `K_{c}` or `\\textbf{b}` can "
             "look like a tag.", "Tables"),
        choice("options.slide-notes", "Speaker notes (`::: notes`) in a Beamer deck",
               (("off", "leave them out of the PDF"), ("show", "a notes page after each slide"),
                ("only", "the notes pages alone, for printing")), "off",
               "A `::: notes` block under a slide is dropped from the PDF unless asked for. It is Beamer's `show notes` / `show only "
               "notes`, added as a header, so the deck's own `classoption` (an `aspectratio=169`) is kept. Only a deck with a "
               "LaTeX engine; any other build ignores it. Per document: `slide-notes` in `pdfmd-options`.", "Output"),
        choice("options.md-macro", "Markdown inside raw LaTeX: \\md{...} and \\begin{md}",
               (("on", "read the argument as Markdown"), ("off", "leave \\md{...} for LaTeX")), "on",
               "`\\textbf{\\md{**bold** and [@smith2020]}}`, `\\begin{md} ... \\end{md}`: the text is read as Markdown, so citations, "
               "cross-references and math belong to the one document. Not for a document that defines `\\md` itself.", "Input"),
        choice("options.table-captions", "A bold line next to a table, `**Table 1: ...**`, as its caption",
               (("note", "leave it, and say once how many lines would have been captions"), ("on", "make it the caption"),
                ("off", "leave it, silently")), "note",
               "The line must be one bold span that starts with a label word (Table, Tabelle, Таблица ... by `lang:`) and stand right above "
               "a table without a caption, or right below one. A trailing {#tbl:id} becomes the table's id. Pipe tables, gfm and Pandoc "
               "Markdown.", "Tables"),
        choice("options.table-caption-label", "The typed label (`Table 1:`) of such a caption",
               (("strip", "cut it off, the engine numbers the table"), ("keep", "keep it (the engine numbers the table as well)")),
               "strip", "Only with table-captions: on.", "Tables"),
        choice("options.table-caption-need-label", "A label word (Table ...) is needed for such a caption",
               (("on", "yes: a bold line without one is left alone"), ("off", "no: any line that is one bold span next to a table")),
               "on", "Off also takes a bold sub-heading above a table, so try it with table-captions: note first.", "Tables"),
        text("options.table-caption-colon-words", "Also a short `: Results` line as a caption (words)",
             "A whole number: a paragraph that starts with `: ` and has at most that many words, next to a table, is its caption "
             "(gfm has no caption syntax; Pandoc Markdown reads it itself). 0 is off; 2 is a good start.", "Tables", "config", "nonnegative"),
        text("options.table-caption-words", "More label words for such captions",
             "Words separated by commas, added to the document language's own word and to Table (the list is in "
             "pdfmd_tables/captions.py).", "Tables"),
        choice("options.csv.cut", "Where a long .csv table is cut",
               (("ends", "keep its first and last rows and columns, \u2026 between them"),
                ("head", "keep the first rows and columns only")), "ends", "A div's cut= wins.", "Tables"),
        choice("options.csv.note", "The note under a .csv table that was cut",
               (("short", "the fact only: showing the first 7 and the last 3 of 11 rows"),
                ("off", "none (the \u2026 row still marks the cut)"),
                ("full", "the fact and how to show more")), "short",
               "A div's note= wins. The advice is in the warning on stderr whatever this says. Per run: --csv-note.", "Tables"),
        choice("options.csv.delimiter", "The delimiter of .csv data",
               (("auto", "guessed from the first lines (a warning when it is not what the file name says)"),
                ("comma", ","), ("semicolon", ";"), ("tab", "tab"), ("pipe", "|")), "auto",
               "A div's delimiter= wins.", "Tables"),
        choice("options.column-estimate", "How table cell widths are estimated",
               (("count", "character counts (fast, the default)"),
                ("measure", "measure with the selected PDF engine; cache unchanged measurements")), "count",
               "LaTeX and Typst PDF builds. Exports and other writers keep count with a NOTE; a failed measurement "
               "keeps count with a WARN. One table: {column-estimate=measure} after its caption.", "Tables"),
        text("options.table-chars", "Fallback characters per line for LaTeX tables",
             "Default 95. A positive whole number used in count mode when paper, margins or font size cannot be estimated. "
             "One table: {table-chars=120} after its caption (Pandoc 3.8.2 or newer) or on a .csv div.",
             "Tables", check="positive"),
        choice("options.table-style", "Extra row spacing for LaTeX tables with wrapping cells",
               (("off", "use the writer's spacing"), ("spaced", "stretch the row strut by table-row-spacing")), "off",
               "One table: {table-style=spaced} after its caption (Pandoc 3.8.2 or newer) or on a .csv div.", "Tables"),
        text("options.table-row-spacing", "Row stretch factor for spaced tables",
             "Default 1.4. Use a decimal of at least 1. One table: {table-row-spacing=1.5} after its caption or on a .csv div.",
             "Tables", check="number"),
        choice("options.column-widths", "Pipe-table column widths",
               (("auto", "LaTeX balances wide tables with equal dashes; Typst, HTML, Word and ODT use default sizing"),
                ("keep", "preserve the widths Pandoc read"),
                ("force", "ignore the dashes when balancing columns")), "auto",
               "Unequal dashes express a width choice under Pandoc's Markdown reader. "
               "One table: {widths=force} after its caption (Pandoc 3.8.2 or newer). Older name: table-widths.", "Tables"),
        choice("options.column-word-floor", "A narrow column keeps its longest word whole",
               (("on", "a chosen column too narrow for its longest word is widened to it"),
                ("off", "allow words to break in a narrow column")), "on",
               "One table: {word-floor=off} after its caption (Pandoc 3.8.2 or newer). Not used under column-widths keep. "
               "Older name: table-word-floor.", "Tables"),
        text("options.column-word-floor-limit", "The longest word the floor protects (characters)",
             "Default 16: a longer word (a URL, a long name) is not worth the room. One table: {column-word-floor-limit=24}.",
             "Tables", "config", "number"),
        choice("options.column-word-ceil", "Narrow airy columns to their longest cell plus a margin",
               (("on", "give up excess space to columns that need it"), ("off", "keep airy columns")), "on",
               "One table: {word-ceil=off} after its caption (Pandoc 3.8.2 or newer). Not used under column-widths keep.",
               "Tables"),
        text("options.column-ceil-margin", "Extra width an airy column can keep as a share of the line",
             "Default 25%. Use a percentage or a fraction from 0 to 1; 0 or off disables the ceiling. "
             "One table: {column-ceil-margin=40%}.", "Tables", "config"),
        choice("options.table-colons", "Count alignment colons towards pipe-table widths",
               (("ignore", "only dashes determine proportions"), ("count", "dashes and colons both count")), "ignore",
               "Alignment is retained in either mode. One table: {table-colons=count} after its caption.", "Tables"),
        choice("options.table-repair", "Fit each pipe-table row to the same number of cells",
               (("pandoc", "let Pandoc read the original row shapes"), ("header", "pad or cut to the header's count"),
                ("widest", "pad to the highest count, keeping every cell")), "pandoc",
               "Header and widest also add a missing separator or header when possible. All modes leave list code fences "
               "and GFM raw HTML div blocks alone. --table-repair overrides this setting.", "Tables"),
        text("options.column-outlier", "A cell this many times longer than the next wraps instead of widening its column",
             "Default 2; 0 switches it off. One table: {column-outlier=3} after its caption (Pandoc 3.8.2 or newer).",
             "Tables", "config", "number"),
        text("options.column-outlier-rows", "Rows a column needs before a cell can be an outlier",
             "Default 4. One table: {column-outlier-rows=6}.", "Tables", "config", "number"),
        text("options.column-outlier-length", "Characters a cell needs before it can be an outlier",
             "Default 30. One table: {column-outlier-length=40}.", "Tables", "config", "number"),
        choice("options.column-count-raw-tex", "Count raw TeX cells (\\SI, \\SIrange, \\num, \\ce) when sizing columns",
               (("on", "KLUDGE until the true width estimator: a guess of the printed width"),
                ("off", "raw TeX counts as nothing, as before 3.31.0")), "on",
               "One table: {count-raw-tex=off} after its caption.", "Tables"),
        # -- code
        choice("options.code-wrap", "Long code blocks and inline code (LaTeX)", (("true", "wrap at the margin"), ("false", "run on")), "true",
               "Blocks need fvextra (in every full TeX Live). Inline code breaks at punctuation only to avoid overflow. "
               "Per block: {wrap=false}.", "Code"),
        choice("options.line-numbers", "Number code lines (LaTeX)", on_off, "",
               "Off unless set. Per block: {.numberLines startFrom=10} or {.noNumberLines}.", "Code"),
        text("options.line-number-step", "Number every n-th code line", "1 is every line.", "Code", "config", "number"),
        # -- Word and OpenDocument
        choice("options.office.latex", "LaTeX in Word and ODT files",
               (("auto", "native where possible, pictures for the rest"), ("images", "pictures, formulas and units too"),
                ("off", "Pandoc's own behaviour")), "auto", "How `\\ce`, `\\si`, tikz and house macros reach a .docx/.odt.",
               "Word and OpenDocument"),
        choice("options.office.labels", "Reference numbers in Word files",
               (("auto", "build the PDF once and read LaTeX's numbers"), ("off", "count them instead")), "auto",
               "Where \"Figure 3\" and \"Equation 2\" come from.", "Word and OpenDocument"),
        text("options.office.reference-doc", "Word/ODT template (reference document)",
             "A .docx/.dotx or .odt/.ott whose styles Word and ODT files take; an absolute path.", "Word and OpenDocument"),
        # -- plain Markdown and text
        choice("options.gfm.scripts", "Sub- and superscripts in plain Markdown",
               (("unicode", "H\u2082O; _(..) and ^(..) where Unicode has none"), ("html", "<sub> and <sup>"),
                ("drop", "plain text"), ("ascii", "_2 and ^(2+)")), "unicode", "--to gfm. Per run: --gfm-scripts.",
               "Plain Markdown and text"),
        choice("options.gfm.math", "Math in plain Markdown",
               (("dollars", "$..$ and $$..$$ (GitHub, VS Code, Obsidian)"), ("fenced", "```math fences")), "dollars",
               "--to gfm. Per run: --gfm-math.", "Plain Markdown and text"),
        choice("options.gfm.title", "A title block in plain Markdown",
               (("true", "# Title and an author/date line"), ("false", "none")), "true", "", "Plain Markdown and text"),
        choice("options.txt.scripts", "Sub- and superscripts in text",
               (("unicode", "H\u2082O; _(..) and ^(..) where Unicode has none"), ("drop", "plain text"),
                ("ascii", "_2 and ^(2+)")), "unicode", "--to txt.", "Plain Markdown and text"),
        choice("options.txt.title", "A title block in text", (("true", "the title, underlined"), ("false", "none")), "true",
               "", "Plain Markdown and text"),
        choice("options.ascii.missing", "Characters with no ASCII form",
               (("question", "?"), ("escape", "\\u65e5"), ("drop", "nothing"), ("fail", "no file is written")),
               "question", "--to ascii. Per run: --ascii-missing.", "Plain Markdown and text"),
        choice("options.keep-source", "Markdown output carries its source",
               (("packed", "compressed, in one comment at the end"), ("readable", "as text, escaped")), "",
               "pdfmd --restore FILE.md writes the folder back. Per run: --keep-source.", "Plain Markdown and text"),
        # -- reading in the terminal
        choice("options.pager", "Page --view output in the terminal", on_off, "",
               "Through $PDFMD_PAGER, $PAGER, the command below or less when stdout is a terminal. Per run: --pager / --no-pager.",
               "Reading in the terminal"),
        text("options.pager_command", "The pager command for --view",
             "A command with its flags, e.g. `bat --paging=always` or `less -R`. $PDFMD_PAGER and $PAGER win over it, so one "
             "shell can override a project's choice. Empty: `less -FRX` (it quits at once when the text fits the screen).",
             "Reading in the terminal"),
        # -- PDF extras
        text("options.header", "Page header", "A template: {title}, {page}, {pages}, {date}, {header}.", "PDF finishing"),
        text("options.footer", "Page footer", "The same, e.g. {page} / {pages}.", "PDF finishing"),
        choice("options.bookmarks", "PDF bookmarks from headings", on_off, "", "", "PDF finishing"),
        choice("options.attach-links", "Attach linked files to the PDF", on_off, "", "", "PDF finishing"),
        choice("options.hybrid", "Make the PDF editable in LibreOffice (hybrid PDF)", on_off, "",
               "Attaches an OpenDocument copy as Original.odt; LibreOffice then opens the PDF as that document.", "PDF finishing"),
        choice("options.shrink", "Shrink the finished PDF, losslessly",
               (("true", "object streams and recompression (the default)"), ("fast", "object streams only"), ("false", "off")), "",
               "The last step on every PDF: it is rewritten by qpdf, pikepdf or mutool (the first one installed) with object "
               "streams (PDF 1.5) and Flate streams deflated again, about a tenth smaller here. Nothing is lost: no image or font "
               "is touched, and the file is replaced only when it is valid, has the same pages and is smaller. Without one of "
               "the tools nothing happens. Per run: --shrink / --no-shrink.", "PDF finishing"),
        text("options.shrink-timeout", "Time limit of one shrink run (seconds)",
             "A run that takes longer is stopped and the PDF stays as it was built. Default 120. 0 or a negative number: no "
             "limit.", "PDF finishing", "config", "number"),
        # -- build history
        choice("options.stamp.enabled", "A \"Compiled with...\" line in the source", on_off, "",
               "Written into the document's BUILD NOTES after each build. Off unless set.", "Build history"),
        choice("options.stamp.store", "Where the compile history goes", (("notes", "the document's BUILD NOTES"),
               ("file", "a NAME.hst file in the backup folder; the document is left alone"), ("both", "both")), "notes",
               "Only matters when the line above is on.", "Build history"),
        choice("options.stamp.mode", "Older \"Compiled with...\" lines",
               (("replace", "the new line replaces the old one"), ("history", "kept below it as a list")), "replace", "",
               "Build history"),
        choice("options.stamp.scope", "When the line is written",
               (("always", "every build"), ("report", "only as part of a -r report"),
                ("standalone", "only when built on its own")), "always", "", "Build history"),
        text("options.stamp.packages", "LaTeX packages whose version the line names",
             "Comma-separated, e.g. nulabreport; left out when the document does not load it.", "Build history",
             "config", "list"),
        choice("options.stamp.include-output", "The line names the output file", on_off, "", "", "Build history"),
        choice("options.stamp.pdf-metadata", "The PDF records the build too", on_off, "",
               "Two invisible fields in the PDF's Info dictionary.", "Build history"),
        choice("options.stamp.restored-note", "A \"Restored ...\" entry when a version is put back", (("true", "yes"), ("false", "no")),
               "true", "pdfmd --history-restore adds it to the history when the document keeps one.", "Build history"),
        choice("options.stamp.partial", "Builds of some parts leave an entry in the history", on_off, "",
               "Needs the history in a NAME.hst file (\"Where the compile history goes\"): a build of parts or sections only "
               "is written there as a \"partial\" entry naming the parts and those that changed. Off unless set.", "Build history"),
        # -- backups
        choice("options.backup.enabled", "A backup of the source after each build", on_off, "",
               "Into .backups/ beside the document, when it changed. Off unless set.", "Backups"),
        text("options.backup.dir", "Backup folder", "Where the copies go, beside the document (or an absolute path). Without "
             "one: .backups, a hidden folder, or a backup/ folder that is already there.", "Backups"),
        text("options.backup.format", "Backup file names",
             "compact, dashed, stem, suffix, short, or a template with {name} {stem} {ext} and strftime codes.",
             "Backups"),
        text("options.backup.keep", "Backups kept per document", "The newest n; 0 keeps none; a negative number keeps every one (the default).", "Backups",
             "config", "number"),
        text("options.backup.pdfs", "Built PDFs kept per document",
             "Copied into the backup folder after each PDF build (a rebuilt source cannot give an old PDF back). The newest n; "
             "0 keeps none (the default); a negative number keeps every one.", "Backups", "config", "number"),
        # -- the source inside the PDF
        choice("options.attach-source", "Attach the source to the PDF",
               (*on_off, ("private", "keep excerpt markers and attach passages and notes")), "",
               "Anyone can read it back from the PDF (pdfmd --restore). An explicit strip setting for excerpts wins.",
               "Source inside the PDF"),
        choice("options.attach-csl", "The citation style attached with the source", on_off, "",
               "Off by default: a style is 10-90 KB (apa.csl is 86 KB) and the global metadata sets one for every document. "
               "Without it a machine that builds the source again needs the style by its name.", "Source inside the PDF"),
        choice("options.bundle", "Files attached with the source",
               (("sources", "the files the text reads, not images"), ("true", "and the images"), ("all", "everything"),
                ("false", "none: the source alone")),
               "", "Default: the files the text reads. An explicit PDF bundle keeps comments and excerpts by default.",
               "Source inside the PDF"),
        choice("options.bundle-packages", "Attach the LaTeX packages too", on_off, "",
               "The .sty/.cls files the build used that are not in TeX Live.", "Source inside the PDF"),
        text("options.bundle-max-mb", "Size limit of the attached bundle (MB)", "Default 100.", "Source inside the PDF",
             "config", "number"),
        choice("options.strip-comments", "Drop comments from build/assembled/attached source (hidden: assembled/attached only)",
               (("true", "strip comment kinds"), ("false", "keep comments"),
                ("hidden", "only plain hide blocks and spans"),
                ("markdown,hidden", "Markdown comments and plain hide content"),
                ("excerpts", "only excerpt records from the PDF source"),
                ("markdown,excerpts", "Markdown comments and excerpt records")), "",
               "On strips comment kinds and excerpt records. Hidden (alias hide) is opt-in. Calc-hide statements stay.",
               "Source inside the PDF"),
        # -- cache
        choice("options.cache.aux", "Remember reference numbers between builds", on_off, "",
               "Carries figure/table numbers over to a partial build of a long document.", "Cache"),
        choice("options.cache.plots", "Keep the plots a build draws", on_off, "",
               "Plots drawn by code in the document are reused while the code is unchanged.", "Cache"),
        choice("options.seed-labels", "Reference numbers in a part built alone",
               (("auto", "the last full build's, else a scan of the whole document"), ("aux", "the last full build's only"),
                ("scan", "a scan of the whole document"), ("draft", "a LaTeX pass over the whole document, without its pictures: exact"),
                ("off", "none: ?? for references outside the part")), "auto", "", "Cache"),
        choice("options.seed-calc", "Calculator names in a part built alone",
               (("auto", "evaluate the whole document (the calculator only, nothing typeset)"),
                ("off", "none: a name defined in a part left out is undefined")), "auto", "", "Cache"),
        choice("options.cache.location", "Where the cache lives",
               (("global", "~/.cache/pdfmd"), ("document", ".cache/pdfmd beside the document")), "global", "", "Cache"),
        text("options.cache.max-mb", "Cache size --doctor notes (MB)",
             "pdfmd --doctor says so (a NOTE) when ~/.cache/pdfmd is larger. Default 1000 (1 GB); 0: never. "
             "pdfmd --cache-info shows the parts, pdfmd --clear-cache WHAT clears one.", "Cache", "config", "number"),
        # -- input
        choice("options.text-to-markdown", "Read .txt files as Markdown",
               (("auto", "guess headings, lists, tables; a garbled text gets paragraphs only"),
                ("force", "guess structure even in a garbled text"), ("paragraphs", "paragraphs only, no structure")), "",
               "Off unless set. Needs batchocr 1.2.5 (pdfmd --install batchocr); the words never change.", "Input"),
        text("options.flavour", "Flavour of Markdown (and its reader)",
             "auto (obsidian inside an Obsidian vault, a folder with .obsidian/ above the document; pdfmd elsewhere), obsidian "
             "(%%comments%% hidden, more of its syntax in each release), pdfmd (%%comments%% hidden), pandoc (strict Pandoc), gfm, "
             "commonmark; or a Pandoc reader with +/- extensions (markdown, gfm+smart, commonmark_x), which is the reader with the "
             "flavour on auto. `reader` is another name for the setting. Per run: --flavour, or --from for a reader.",
             "Input"),
        text("options.flavour-overrides", "Flavour preset overrides",
             "A YAML mapping, e.g. {comments: false, gfm-extensions: [smart]}. Fields: reader, comments, embeds, "
             "wikilinks, gfm-extensions and markdown-extensions. Each extension list replaces the preset list.",
             "Input", check="flavour-overrides"),
        choice("options.dialect-detect", "Markdown dialect detection",
               (("basic", "use the usual reader selection; warn about TOML front matter"),
                ("deep", "look for GFM-style blocks after front matter and read TOML metadata")), "",
               "An explicit reader overrides automatic reader selection. TOML metadata needs Python 3.11 or later.", "Input"),
        choice("options.single-newline", "A single newline inside a paragraph of a Markdown file",
               (("hard", "a line break (Obsidian's way; the default of the obsidian flavour)"),
                ("soft", "a space, as CommonMark, GFM files and Pandoc read it (the default of the other flavours)")), "",
               "In an Obsidian vault the vault's own \"Strict line breaks\" (strictLineBreaks in .obsidian/app.json) decides when this is "
               "unset. A blank line is always a new paragraph; two spaces or a backslash at the end of a line is always a line break.",
               "Input"),
        choice("options.unclosed-comment", "A %% with no closing %% in a Markdown file",
               (("hide", "the rest of the note is the comment, as Obsidian shows it (the default in a vault)"),
                ("keep", "it stays as text (the default outside a vault)")), "",
               "Both warn, naming the line. Per run: --unclosed-comment.", "Input"),
        text("options.embed-px-to-pt", "Points to a pixel in ![[picture|300]]",
             "Obsidian sizes a picture embed in pixels; one pixel is this many points (default 0.75, a CSS pixel). Used by the "
             "obsidian and pdfmd flavours.", "Input"),
        choice("options.embed-fit", "A sized picture embed that is wider than the text",
               (("text-width", "stays within the text width (LaTeX and HTML builds; Word scales to the page itself)"),
                ("none", "keeps the size it was given")), "text-width",
               "A picture with no size is fitted to the text by Pandoc already.", "Input"),
        choice("options.embed-search", "Where a picture embed's name is looked for",
               (("vault", "beside the document, then the vault's attachment folder, then anywhere below the vault (outside a vault: "
                          "anywhere below the document's folder)"),
                ("folder", "beside the document, then anywhere below the document's folder"),
                ("none", "only the path as written")), "vault",
               "The nearest picture wins when several have the name, with a note.", "Input"),
        choice("options.metadata-precedence", "Which metadata file wins a key two of them set",
               (("later", "the later one, as Pandoc takes them"), ("first", "the first one")), "later",
               "pdfmd-options too. A document's own front matter beats both; the global metadata.yaml is below both. "
               "Per run: --metadata-precedence.", "Input"),
        choice("options.path-style", "How a path is written in a message",
               (("auto", "relative to the working folder, then ~/..., then absolute"), ("relative", "relative, never ~"),
                ("home", "~/... under your home folder"), ("full", "always absolute")), "auto",
               "Per run: --path-style (--full-paths is `full`). --verbose gives `full` unless --path-style is given.", "Messages"),
        text("options.path-up", "How many `..` steps above the working folder are still written relative",
             "A whole number (default 2). A folder further up is written ~/... or in full, per the style above. Per run: --path-up.", "Messages"),
        text("options.metadata-parents", "How far above the document to look for metadata/",
             "A whole number (default 1): 0 = off; all or any negative number = up to the .pdfmd inheritance boundary. "
             "Count from the scaffold folder for parts, otherwise the document folder.", "Input", "config", "parents"),
        text("options.metadata-append", "Keys whose document value adds to the layers below",
             "Names of front-matter keys (`author`, or `author, instructor`) whose value in a document is appended to the one the "
             "metadata files hold, instead of replacing it. Any layer can also write `author+: [B]` to append. Off unless set.", "Input"),
        # -- universal markup: what is written in one syntax, carried into every output (off unless set)
        choice("options.raw", "Carry raw HTML, LaTeX and Typst pieces into every output", on_off, "",
               "Raw pieces in another syntax than the output's are converted (HTML and LaTeX read into native elements, "
               "Typst drawn as a vector picture) instead of dropped. Per family: pdfmd-options.raw in a document.",
               "Universal markup"),
        Setting("options.pagebreak", "Page breaks carried into every format", "multi", PAGEBREAK_CHOICES, "",
                "Each spelling of a chosen family becomes the output's own page break. Left unset: every family, in the pdfmd "
                "and obsidian flavours (none with flavour: pandoc, gfm or commonmark). Per run: --pagebreak / --no-pagebreak.", "Universal markup"),
        Setting("options.linebreak", "Line breaks (<br>, \\newline ...) carried into every format, everywhere", "multi", LINEBREAK_CHOICES, "",
                "Each spelling of a chosen family becomes the output's own line break, in text as well as in table cells. Left unset, "
                "every spelling is carried in table cells only (a cell cannot hold a blank line or \\par), and text outside a table "
                "keeps what each format makes of it. Per run: --linebreak / --no-linebreak.", "Universal markup"),
        choice("options.show-hidden", "Print plain hide blocks and spans", on_off, "",
               "Off by default: content is read by filters, then removed. Calc hide stays silent. Per run: --show-hidden.",
               "Universal markup"),
        choice("options.show-comments", "Show the <!-- comments --> of the text in the output", on_off, "",
               "Each comment becomes a box labelled Comment (LaTeX, Typst, HTML), a real Word comment (docx). pdfmd's own "
               "markers stay invisible. Per run: --show-comments / --no-show-comments.", "Universal markup"),
        choice("options.calc.enabled", "Calculate `2 + 2`{=} and the lines of a ::: calc div", on_off, "",
               "Inline code followed by a bare {=} becomes its value; `C = n / V = {ans:4sf}` prints the text with the value in and keeps C. "
               "Pure arithmetic only, nothing is run. On unless set to off. Needs Pandoc. Per run: --calc / --no-calc.", "Calculations"),
        text("options.calc.digits", "Figures a calculated value shows",
             "4sf (four significant figures), 2dp (two decimal places). Empty: as R prints, up to 7 figures. A span's {ans:2dp} wins. "
             "Per run: --calc-digits.", "Calculations"),
        choice("options.calc.round", "How round() in a calculation settles an exact half",
               (("even", "to the even digit: 2.5 is 2, 3.5 is 4 (R, Python)"), ("away", "away from zero: 2.5 is 3")), "even",
               "For `round(2.5)`{=}. Per run: --calc-round.", "Calculations"),
        choice("options.calc.subs", "Show a calculation with its numbers put in", on_off, "",
               "Before the result of `C = n / V = {ans}` print `n / V` with n and V replaced by their values, in the digits each was "
               "defined with (the computation keeps the full values). {subs} forces it on one line, {nosubs} stops it. "
               "Per run: --calc-subs / --no-calc-subs.", "Calculations"),
        choice("options.calc.typeset", "Print a calculation as typeset maths",
               (("inline", "a line of inline maths, the label and the unit stay text"),
                ("display", "a centred display formula per line, the label and the unit inside it (it does not wrap)"),
                ("off", "the plain text it was written in")), "",
               "`m = c_s * V_el = 28.07 * 75 = 2105.25 ng` becomes a formula: c with an s subscript, V with an el subscript, a centred "
               "dot for *, Greek names as letters. inline (`true`) keeps the label and the unit as text in the line and breaks a long "
               "line before an =; display makes each `::: calc` or fenced line one centred formula, the label and unit set as \\text "
               "inside it; a `{=}` span stays inline. Needs a writer with maths (LaTeX, Typst, HTML, Word, OpenDocument); Markdown and "
               "the plain-text writers keep the text. Off unless set. Per run: --calc-typeset [inline|display] / --no-calc-typeset.",
               "Calculations"),
        text("options.calc.typeset-upright", "Name pieces a typeset calculation sets upright",
             "Comma separated pieces: V makes V_el an upright V with an el subscript, e makes c_e an upright e. A piece is the letters "
             "of a name's base or one word after an underscore. The default is one letter italic, a longer piece upright. "
             "Greek names keep their usual style. For one calculation line use {upright: s, V} in its text. "
             "Empty: none. Per run: --calc-typeset-upright.", "Calculations"),
        text("options.calc.typeset-italic", "Name pieces a typeset calculation sets italic",
             "Comma separated pieces: el makes V_el an italic word, DNA makes k_DNA an italic DNA. "
             "For one calculation line use {italic: el, DNA} in its text. Empty: none. "
             "Per run: --calc-typeset-italic.", "Calculations"),
        choice("options.calc.noindent", "Leave the first-line indent off a ::: calc div",
               (("lines", "off the calculation lines; the prose between them keeps the document's (the default)"),
                ("on", "off every paragraph of the div"),
                ("off", "the whole div keeps the document's indent")), "",
               "Calculation lines read better flush left, so in a `::: calc` div the paragraphs that hold one have no first-line "
               "indent even when the document has one, and a paragraph of prose keeps it. An `indent=` on the div wins, and so "
               "does a nested `::: indent` / `::: noindent` div. Empty: lines. "
               "Per run: --calc-noindent [lines|all] / --no-calc-noindent.", "Calculations"),
        text("options.calc.space", "Room above and below a ::: calc div",
             "A length (0.75em, 6pt, 2mm; units pt, mm, cm, in, em) or off. The default 0.75em keeps a block of calculation lines "
             "apart from the paragraphs around it (LaTeX, Typst and HTML). Empty: 0.75em. Per run: --calc-space.", "Calculations"),
        choice("options.calc.align", "Alignment of a ::: calc div",
               (("left", "flush left (the default)"), ("centre", "centred")), "left",
               "Centres the lines of a `::: calc` div. Per run: --calc-align.", "Calculations"),
        text("options.calc.constants", "A file of named values for the calculator",
             "A CSV file, columns name,value[,digits[,note]] (a header row is fine, # lines are skipped), read before the document: "
             "`t18` then works in `t18`{=4sf} and {subs}. Looked for beside the document and its metadata files. Empty: none. "
             "Per run: --calc-constants.", "Calculations"),
        text("options.calc.export", "A file the calculator's names are written to",
             "A CSV, columns name,value,digits: the value of the last definition of each name after a build that evaluated names "
             "(the mirror of the constants file, which can read it back). Beside the document unless the path is absolute. "
             "Empty: none. Per run: --calc-export.", "Calculations"),
        # -- chemical structures (a ```smiles block; every one of these is also an attribute of the block)
        choice("options.smiles.engine", "What draws a ```smiles block",
               (("auto", "the best one there is"), ("rdkit", "RDKit pictures (SVG, PNG, or PDF for LaTeX)")), "auto",
               "A block of structures (SMILES, molfile) is drawn as a picture. Per block: engine=.", "Chemical structures"),
        choice("options.smiles.format", "Picture format of a structure",
               (("auto", "what the output reads best: PDF for LaTeX, SVG for HTML and Typst, PNG for Word"), ("svg", "SVG"),
                ("png", "PNG"), ("pdf", "PDF (needs rsvg-convert)")), "auto", "Per block: format=.", "Chemical structures"),
        choice("options.smiles.office-format", "Picture format of a structure in Word and OpenDocument",
               (("png", "PNG (every Word, Google Docs, Pages)"), ("svg", "SVG (Word 365, LibreOffice)")), "png",
               "Used when the format above is auto. Per block: office-format=.", "Chemical structures"),
        choice("options.smiles.palette", "Atom colours of a structure",
               (("colour", "RDKit's: O red, N blue, S yellow... (the default)"), ("bw", "black and white, like a chemfig drawing")), "colour",
               "Per block: palette=.", "Chemical structures"),
        text("options.smiles.cell-width", "Width of one structure, in pixels",
             "A whole number (default 250); a block of several structures is as many cells wide as it has per row. Per block: cell-width=.",
             "Chemical structures"),
        text("options.smiles.cell-height", "Height of one structure, in pixels",
             "A whole number (default 200). Per block: cell-height=.", "Chemical structures"),
        text("options.smiles.per-row", "Structures in a row",
             "A whole number (default 3): the line-per-structure block is wrapped after this many. Per block: columns=.",
             "Chemical structures"),
        text("options.smiles.bond-length", "Length of a bond, in pixels",
             "A whole number (default 40): every structure has the same bond length, so a small molecule is not drawn large. "
             "A structure that does not fit its cell is scaled down. Per block: bond-length=.", "Chemical structures"),
        text("options.smiles.dpi", "Resolution of a PNG structure",
             "A whole number (default 300). Per block: dpi=.", "Chemical structures"),
        Setting("options.markup", "Spellings of other Markdown dialects carried into every format", "multi", MARKUP_CHOICES, "",
                "Callouts: GitHub's and Obsidian's `> [!NOTE]` and Quarto's `::: callout-tip`; toc: `[TOC]` where the "
                "contents go; centre: `<center>` and `::: centre`; highlight: `==text==`; keep: `::: keep`; landscape: `::: landscape`; appendix: `\\appendix`; space: `\\vspace{1cm}`. Left unset: all but space, in the pdfmd and obsidian "
                "flavours (none with flavour: pandoc, gfm or commonmark). Per run: --markup / --no-markup.", "Universal markup"),
        choice("options.rewrite", "Replace an older output of the same name", on_off, "",
               "Off: a build that finds report.pdf already there writes report (1).pdf and leaves the old one. "
               "Per run: --rewrite / --no-rewrite. A watch (-w) always rewrites.", "Output"),
        text("options.rewrite-name", "The name of the numbered copy",
             "A template with {n} (1, 2, ...), {stem}, {ext} (with its dot) and {date}: `{stem} ({n}){ext}`, `{stem}-{n}{ext}`, "
             "`{stem}_{date}-{n}{ext}`. No folders.", "Output"),
        # -- what a build prints
        choice("options.found-style", "How the FOUND line lists the files it picked up",
               (("group", "files of one folder together: metadata: metadata.yaml + preamble.tex"),
                ("path", "each with its path: metadata/metadata.yaml, metadata/preamble.tex")), "group",
               "Only this setting; a document does not change it.", "Messages"),
        choice("options.build-time", "Say how long a build took", on_off, "",
               "On the closing line: `OK    report.md > report.pdf  in 3:07`; --verbose adds the time of every step. "
               "Per run: --build-time / --no-build-time.", "Messages"),
        text("options.time-format", "How a time is written",
             "auto (0.42 s, 12.4 s, 3:07, 1:02:03, 1 d 02:03:04), clock (03:07), seconds (12.4 s), words (3 min 7 s) or a "
             "template with {d} {h} {hh} {m} {mm} {s} {ss} {s1} {s2} {ms}, e.g. `{h}:{mm}:{ss}`. Per run: --time-format.",
             "Messages"),
        choice("options.build-log", "Keep a record of each build for debugging afterwards",
               (("on", "every build"), ("failed", "only a build that failed"), ("off", "none")), "on",
               "A plain-text file in the cache (where `cache: location` says) with the command line, the commands run, what pdfmd "
               "printed and what the engines said. A failed build prints its path; `pdfmd --last-build FILE [--failed]` shows it. "
               "Per run: --build-log MODE.", "Messages"),
        text("options.build-log-keep", "How many records of a document to keep",
             "The newest ones, and the newest failed one whatever its age. Default 5.", "Messages", "config", "number"),
        text("options.build-log-max-size", "Size cap of one record (KB)",
             "A longer record keeps its start and its end. Default 512.", "Messages", "config", "number"),
        text("options.ok-delimiter", "What stands between the source and the file in the closing line",
             "OK    report.md > report.pdf. Any short text: >, ->, =>.", "Messages"),
        choice("options.report-build", "How a report (-r) is built",
               (("route", "through the build of one document: the files are its first file and its parts"),
                ("patch", "one Pandoc command over the list of files (fonts and titles only; no font retry, no cache route)")),
               "route",
               "route gives a report everything a document gets (fonts, --font, the engine chain, citation-engine, the cache, the style "
               "sheets). Later files' front matter is not merged; the first file's is the book's.", "Output"),
        choice("options.report-titles", "The titles of a report's files",
               (("chapters", "each title becomes a chapter heading (with two or more titled files)"),
                ("first", "the first file's title is the book's, the later ones are dropped"),
                ("last", "the last file's title is the book's (Pandoc's own merge)")),
               "chapters",
               "chapters also puts a subtitle, and an author or date that differs from the book's, in a line under the heading, and moves "
               "the file's own headings one level down.", "Output"),
        choice("options.page-folder", "Several pages of a picture go into a folder", on_off, "",
               "On: NAME/001.png ... ; off: NAME-001.png ... beside the document. Per run: --page-folder / --no-page-folder.",
               "Output"),
        choice("options.crop", "Crop PDF builds to the ink of each page", on_off, "",
               "Off by default. Per run: --crop / --no-crop. Needs pypdf and a PDF measuring tool (see --doctor).", "Output"),
        text("options.crop-pad", "Points of padding around the crop", "Default 2 pt. Per run: --crop-pad.",
             "Output", check="number"),
        text("options.crop-ignore-bottom", "Points at the bottom excluded from the crop", "Default 0 pt. Per run: --crop-ignore-bottom.",
             "Output", check="number"),
        text("options.crop-page", "Crop and keep only this page", "Counts from 1. Leave unset for all pages. Per run: --crop-page.",
             "Output", check="positive"),
        text("options.image-quality", "JPEG export quality", "A whole number from 1 to 100, default 90. Per run: --image-quality.",
             "Output", check="positive"),
        # -- checks and limits
        choice("options.chatter", "How much a build says",
               (("off", "errors on stderr"), ("result", "the final OK line"), ("warnings", "results, warnings and errors"),
                ("normal", "usual build output"), ("verbose", "discovery and commands"), ("debug", "engine diagnostics too")),
               "", "Per run: --chatter LEVEL, or -q (warnings), -qq (result), -qqq (off). "
               "Per document: pdfmd-options.chatter.", "Checks and limits"),
        text("options.mute", "Diagnostic IDs to accept",
             "Comma-separated, e.g. table-mismatch, table-unparsed, YAML. Muted warnings pass --strict. "
             "Per run: --mute ID[,ID]. Per document: pdfmd-options.mute.", "Checks and limits", "config"),
        text("options.log", "Append build diagnostics to a file",
             "The parent folder must exist. A relative path is based at the document. "
             "Per run: --log FILE (relative to the working folder). Per document: pdfmd-options.log.",
             "Checks and limits", "config"),
        choice("options.summary", "Count diagnostics after the last result", on_off, "",
               "One line of unmuted warnings, notes and errors for the whole run, unless chatter is off. "
               "Per run: --summary. Per document: pdfmd-options.summary.", "Checks and limits"),
        choice("options.strict", "A warning fails the build", on_off, "",
               "The output is kept; the exit status is 1. Per run: --strict / --no-strict.", "Checks and limits"),
        text("options.max-asset-mb", "Warn about an image or data file over (MB)", "Before the build starts.",
             "Checks and limits", "config", "number"),
        text("options.max-output-mb", "Warn about an output over (MB)", "After the build.", "Checks and limits", "config",
             "number"),
        text("options.soffice-timeout", "Time limit of one LibreOffice run (seconds)",
             "A run that takes longer is stopped, with the process it started, and its file fails with this setting named; the "
             "other files go on. Default 300. 0: LibreOffice is never run (it counts as not installed). A negative number "
             "(-1): no limit. Per document: `soffice-timeout` in `pdfmd-options`.", "Checks and limits", "config", "number"),
        text("options.image-dpi", "Raster image resolution (pixels per inch)",
             "A number above 0. SVG images and raster diagrams default to 192 (the existing diagram resolution); "
             "exported pages (--to png, jpg, tiff) default to 300. Per run: --image-dpi. "
             "Per document: image-dpi in pdfmd-options. Vector PDFs keep their size.", "Output", "config", "number"),
        text("options.diagram-timeout", "Time limit of one diagram tool run (seconds)",
             "mmdc, dot, d2 and the converters behind them: a run that takes longer is stopped, with the process it started, "
             "and the diagram stays as code with a warning that names this setting; that tool is not tried again in the build. "
             "Default 120. 0: no diagram is drawn (the code stays). A negative number (-1): no limit. Per document: "
             "`diagram-timeout` in `pdfmd-options`.", "Checks and limits", "config", "number"),
        text("options.serve-max-request-mb", "Largest request `pdfmd --serve` takes (MB)",
             "The body of one request to the local server of the web UI (a save sends the whole file): a larger one is refused (413) "
             "before it is read. Default 100. 0: request bodies are switched off, so every save, new file and render is refused "
             "and the studio is read-only (reading still works). A negative number (-1): no limit. Read from this setup only, when the server starts.",
             "Checks and limits", "config", "number"),
        text("options.download-retries", "Extra tries of a font download from mirrors.ctan.org",
             "mirrors.ctan.org sends every request to a different CTAN mirror, and one mirror may fail (an incomplete certificate "
             "chain, a dead connection, a time-out, a file that fails its checksum). pdfmd then asks the redirector again, up to this "
             "many extra times after the first try, and prints one WARN per failed try that names the mirror and the error. Default 2. "
             "0: no retry. A negative number (-1): no limit (it keeps asking until a mirror answers; Ctrl-C stops it). Other hosts "
             "are never retried. Read from this setup only, by `pdfmd --install fonts`.",
             "Checks and limits", "config", "number"),
        text("options.check-ignore", "Codes `pdfmd --check` leaves out", "Comma-separated, e.g. heading-skip, link-anchor.",
             "Checks and limits", "config", "list"),
        text("options.lua-filter", "Named Lua filters",
             "Comma-separated paths, relative to this settings file. Nearest list replaces; lua-filter+: appends. "
             "The ordinary Lua trust check applies.", "Automatic behaviour", "config", "list"),
        text("options.lua-filter-before-citeproc", "Lua filters before citation processing",
             "Comma-separated paths, relative to this settings file. Nearest list replaces; "
             "lua-filter-before-citeproc+: appends. The ordinary Lua trust check applies.",
             "Automatic behaviour", "config", "list"),
        text("options.preamble", "Named LaTeX preambles",
             "Comma-separated paths, relative to this settings file. Nearest list replaces; preamble+: appends. "
             "Added after discovered preambles.", "Automatic behaviour", "config", "list"),
        Setting("options.no-auto", "Automatic behaviour to switch off", "multi",
                tuple((kind, AUTO_HELP.get(kind, "")) for kind in sorted(no_auto_kinds)), "",
                "What pdfmd does by itself, off for every document (`--no-auto`).", "Automatic behaviour"),
        Setting("options.auto.explicit-only", "Look for nothing, use only what the document names", "multi",
                tuple((kind, AUTO_HELP.get(kind, "")) for kind in AUTO_EXPLICIT_CHOICES), "",
                "Not off (a file the document names is still used) but no longer looked for beside it: `auto: {lua: explicit-only}`.",
                "Automatic behaviour"),
        Setting("options.auto.on", "Switch back on", "multi",
                tuple((kind, AUTO_HELP.get(kind, "")) for kind in sorted(no_auto_kinds)), "",
                "For a folder: what the setup above it switched off (the nearest setup that names a kind decides it): `auto: {margin: on}`.",
                "Automatic behaviour"),
        # -- kits (entry 3du): a house style or any whole document pipeline, a folder with a `.kit` file
        text("kits", "Folders of kits", "Comma-separated: a folder that is a kit, or one that holds kits (`pdfmd --kits` lists "
             "them). Names for a kit's modes, added without editing it, go in the file by hand: `- {path: ~/kits/x, aliases: "
             "{mode: [name]}}`.", "Kits", "config", "list"),
        text("options.kit", "Kit for every document", "A kit to use when a document or its folder names none: `nulabreport`, "
             "`nulabreport:qca`, or `none`. Layers stack: the document's own `kit:` is laid over this one.", "Kits"),
        text("options.kit-stack", "What --kit stacks on", "`off` (default: --kit replaces every kit setting), `all`, or the "
             "layers it keeps: global, preset, folder, document (e.g. folder,document).", "Kits"),
        # -- tool locations (Windows installers often leave a tool off PATH)
        text("options.tesseract-path", "Tesseract", "The tesseract program, or the folder that holds it. Without it pdfmd looks on "
             "PATH, then in the usual Windows install folders.", "Tool locations"),
        text("options.soffice-path", "LibreOffice", "The soffice program, or the folder that holds it. Without it pdfmd looks on "
             "PATH, then in the usual Windows install folders.", "Tool locations"),
        text("options.dot-path", "Graphviz", "The dot program, or the folder that holds it. Without it pdfmd looks on PATH, "
             "then in the usual Windows install folders.", "Tool locations"),
        text("options.mmdc-path", "Mermaid", "The mmdc program, or the folder that holds it. Without it pdfmd looks on PATH, "
             "then in npm's global folder.", "Tool locations"),
        text("options.poppler-path", "Poppler", "The folder that holds pdftotext, pdftoppm and pdftocairo. Without it pdfmd looks on PATH, "
             "then in the usual Windows install folders.", "Tool locations"),
        text("options.ghostscript-path", "Ghostscript", "The gs program (gswin64c or gswin32c on Windows), or its folder. "
             "Without it pdfmd looks on PATH, then in the usual Windows install folders.", "Tool locations"),
        text("options.mutool-path", "MuPDF", "The mutool program, or its folder. Without it pdfmd looks on PATH, "
             "then in Windows App Paths.", "Tool locations"),
        text("options.pandoc-path", "Pandoc", "The pandoc program, or the folder that holds it. Without it pdfmd looks on PATH, "
             "then in the usual Windows install folders.", "Tool locations"),
        text("options.typst-path", "Typst", "The typst program, or the folder that holds it. Without it pdfmd looks on PATH, "
             "then in the usual Windows install folders.", "Tool locations"),
        text("options.chrome-path", "Chrome", "The chrome program, or the folder that holds it (the browser that prints HTML "
             "pages). Without it pdfmd looks on PATH, then in the usual Windows install folders.", "Tool locations"),
        Setting("user-path", "Windows user PATH", "action", (), "",
                "Windows only. Put the folders of the tools pdfmd found off PATH, or a folder you name, on your user PATH; "
                "show it; take off what pdfmd added. Asks before it writes (pdfmd --user-path).", "Tool locations"),
        Setting("disabled", "Features switched off", "multi", feature_choices(), "",
                "Hidden from --help, completion and this screen, refused on the command line; "
                "`pdfmd --disabled ...` uses one for a run. Also the d key.", "Setup"),
        choice("setup-ui", "This setup screen",
               tuple((value, {"plain": "a numbered list", "fancy": "full screen (pdfmd --install tui)"}[value])
                     for value in setup_ui_choices), "plain", "", "Setup"),
    ]


def parse_citation_aliases(text: str) -> dict:
    from pdfmd_base import core
    from pdfmd_cite.aliases import valid_mapping

    message = "A YAML mapping of citation keys, e.g. {short: existing-key}, please."
    try:
        aliases = core.yaml.safe_load(text)
    except core.yaml.YAMLError as error:
        raise ValueError(message) from error
    if not valid_mapping(aliases):
        raise ValueError(message)
    return aliases


def parse_flavour_overrides(text: str) -> dict:
    from pdfmd_base import core
    from pdfmd_flavours.markup import preset_overrides

    try:
        value = core.yaml.safe_load(text)
    except core.yaml.YAMLError as error:
        raise ValueError("A YAML mapping such as {comments: false}, please.") from error
    _, invalid = preset_overrides(value)
    if invalid:
        raise ValueError("Flavour overrides: " + ", ".join(invalid))
    return value


def parse_properties_value(kind: str, text: str):
    """Read either of the properties settings with more than one YAML shape."""
    from pdfmd_base import core

    if kind == "properties-show":
        word = text.casefold()
        flag = core.option_flag(word)
        if flag is not None:
            return flag
        if word == "all":
            return word
        if not text.startswith("["):
            return [item.strip() for item in text.split(",") if item.strip()]

    message = ("A YAML list of property keys, e.g. [stage, tags], please." if kind == "properties-show"
               else "A YAML mapping of property keys and labels, e.g. {stage: Phase}, please.")
    try:
        value = core.yaml.safe_load(text)
    except core.yaml.YAMLError as error:
        raise ValueError(message) from error
    if kind == "properties-show" and isinstance(value, list) and all(isinstance(key, str) for key in value):
        return value
    if kind == "properties-labels" and isinstance(value, dict) and all(
            isinstance(key, str) and isinstance(label, str) for key, label in value.items()):
        return value
    raise ValueError(message)


def get(config: dict, key: str):
    node = config
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def put(config: dict, key: str, value) -> None:
    """Set `key` (None removes it, and the empty mappings it leaves behind)."""
    parts = key.split(".")
    nodes = [config]
    for part in parts[:-1]:
        node = nodes[-1].get(part)
        if not isinstance(node, dict):
            if value is None:
                return
            node = nodes[-1][part] = {"enabled": node} if part in ("calc", "csv") and node is not None else {}
        nodes.append(node)
    if value is not None:
        nodes[-1][parts[-1]] = value
        return
    nodes[-1].pop(parts[-1], None)
    for depth in range(len(parts) - 1, 0, -1):
        if nodes[depth]:
            break
        nodes[depth - 1].pop(parts[depth - 1], None)


def auto_kinds(store: dict, state: str) -> list[str]:
    mapping = get(store, "options.auto")
    return [str(kind) for kind, value in mapping.items() if AUTO_WORDS.get(str(value).strip().casefold()) == state] \
        if isinstance(mapping, dict) else []


def read(stores: dict, setting: Setting):
    store = stores.setdefault(setting.store, {})
    if setting.key in AUTO_ROWS:                       # the kinds of `auto:` that are in this state
        return auto_kinds(store, AUTO_ROWS[setting.key]) or None
    value = get(store, setting.key)
    if setting.key == "options.flavour":
        options = store.get("options")
        if isinstance(options, dict):
            return next((options[key] for key in spelling.spellings("flavour") if key in options), None)
    if setting.key in ("options.calc.align", "options.table-align", "options.smiles.palette") and isinstance(value, str):
        return spelling.british(value)
    if setting.key == "options.markup":
        if isinstance(value, list):
            return [spelling.british(item) if isinstance(item, str) else item for item in value]
        if isinstance(value, str):
            return re.sub(r"[\w-]+", lambda match: spelling.british(match[0]), value)
    return value


def write(stores: dict, setting: Setting, value) -> None:
    store = stores.setdefault(setting.store, {})
    if setting.key in AUTO_ROWS:
        state = AUTO_ROWS[setting.key]
        mapping = dict(get(store, "options.auto") or {})
        for kind in auto_kinds(store, state):
            mapping.pop(kind, None)
        for kind in value or []:
            mapping[kind] = "explicit-only" if state == "explicit" else "on"
        put(store, "options.auto", mapping or None)
        return
    if setting.key == "options.flavour":
        for alias in spelling.spellings("flavour")[1:]:
            put(store, f"options.{alias}", None)
    put(store, setting.key, value)


def shown(setting: Setting, value) -> str:
    """The current value as the screens print it."""
    if value is None:
        what = setting.unset or setting.default
        return f"{what} (default)" if what else "none"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "none"
    return str(value)


def to_stored(setting: Setting, text: str):
    """A choice's text as the config stores it (on/off become booleans)."""
    if tuple(value for value, _ in setting.choices) == ("on", "off"):
        return text == "on"
    if text in ("true", "false"):
        return text == "true"
    return text


def from_stored(setting: Setting, value) -> str | None:
    """A stored value as the text of a choice (None when it is not one of them)."""
    if isinstance(value, bool):
        names = ("on", "off") if "on" in [v for v, _ in setting.choices] else ("true", "false")
        return names[0] if value else names[1]
    return str(value) if value is not None else None
