"""What `pdfmd --setup` can change: the settings of the global config file, and how to read and write them.

A setting is one key of the config file (`options.fallback` is `options:` / `fallback:`), with the values it
accepts and a line of help. Unset means "pdfmd's own default": the config file only ever holds what the
user chose, so deleting a line gives the default back.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Setting:
    key: str                          # dotted path into the config mapping
    title: str
    kind: str                         # "choice" | "multi" | "text"
    choices: tuple[tuple[str, str], ...] = ()      # (value, what it means)
    default: str = ""                 # what pdfmd does when the key is not set (a choice value, or "" for none)
    help: str = ""
    section: str = ""
    store: str = "config"             # which file: "config" (config.yaml) or "metadata" (metadata.yaml beside it)
    check: str = ""                   # "number" for a text that must be one, "list" for a comma-separated list,
                                      # "count" for a whole number or `all`
    unset: str = ""                   # what pdfmd does when the key is not set, in words (see UNSET); the screens show it
    scope: str = "any"                # "machine": this computer only, never a folder's setup (see MACHINE)


ON_OFF = (("on", "yes"), ("off", "no"))

# What a build does when a setting is not set: the words the screens print beside "default", for every setting whose
# `default` is not itself one of its choices. Checked by tests/test_setup.py: a setting with neither is a bug.
UNSET = {
    "author": "none", "lang": "none",
    "papersize": "US Letter (A4 in WeasyPrint)", "fontsize": "10 pt LaTeX, 11 pt Typst",
    "geometry": "margin=1in", "mainfont": "STIX Two Text (or a serif with the letters)",
    "monofont": "JetBrains Mono (or Menlo)", "linestretch": "the engine's own",
    "colorlinks": "off", "toc": "off",
    "options.unicode": "off (only for text the font lacks)", "translit": "Cyrillic only",
    "bibliography": "none", "csl": "Pandoc's Chicago author-date", "link-citations": "off",
    "options.attach-bibliography": "only the cited entries",
    "options.pdf-engine": "first installed: lualatex, xelatex, ...",
    "options.html.self-contained": "off", "options.html.math": "MathML",
    "options.line-numbers": "off", "options.line-number-step": "1",
    "options.header": "none", "options.footer": "none", "options.bookmarks": "off", "options.attach-links": "off",
    "options.stamp.enabled": "off", "options.backup.enabled": "off",
    "options.backup.dir": ".backups (or an existing backup/)",
    "options.strip-comments": "off", "options.hybrid": "off",
    "options.raw": "off", "options.pagebreak": "each format keeps only its own spelling", "options.attach-source": "off",
    "options.bundle": "off", "options.bundle-max-mb": "100",
    "options.cache.aux": "off", "options.text-to-markdown": "off",
    "options.no-auto": "nothing switched off",
    "options.reader": "gfm without front matter, markdown with it",
    "options.strict": "off", "options.max-asset-mb": "no limit", "options.max-output-mb": "no limit",
    "options.check-ignore": "none",
    "options.html.standalone": "off (a page fragment)", "options.html.css": "none",
    "options.office.reference-doc": "one beside the document, else Pandoc's",
    "options.keep-source": "off",
    "options.stamp.packages": "none", "options.stamp.include-output": "off", "options.stamp.pdf-metadata": "on",
    "options.backup.format": "compact (report.md.bak.20260924091500)", "options.backup.keep": "all of them",
    "options.bundle-packages": "off", "options.cache.plots": "off",
    "options.csv.rows": "10", "options.csv.cols": "7",
    "disabled": "nothing switched off",
}

# Settings that belong to this computer, not to a folder: a folder's setup (pdfmd --setup DIR) cannot set them.
MACHINE = frozenset({"setup-ui", "translit", "disabled"})

TRANSLIT = (("greek", "Greek"), ("armenian", "Armenian"), ("georgian", "Georgian"), ("hebrew", "Hebrew"),
            ("arabic", "Arabic"), ("hangul", "Korean (needs the translit extra)"), ("kana", "Japanese kana"),
            ("han", "Chinese (needs the translit extra)"), ("other", "any other script"))

AUTO_HELP = {
    "reader": "read Markdown without front matter as GitHub-flavoured", "title": "promote a leading `# Title`",
    "margin": "1-inch margins", "mainfont": "a default main font", "monofont": "a default code font",
    "font": "both font defaults", "tablewidth": "balance wide table columns", "metadata": "metadata.yaml discovery",
    "yaml": "metadata.yaml discovery", "preamble": "preamble.tex discovery", "tex": "preamble.tex discovery",
    "lua": "Lua filter discovery", "files": "metadata, preamble and filter discovery", "standalone": "--standalone",
    "texdirect": "compile .tex directly with LaTeX", "officedirect": "convert office files with LibreOffice",
    "svg": "convert SVG images for LaTeX", "remoteimages": "fetch and keep remote images", "pdfimages": "show PDF images in HTML builds (as SVG)", "texpackages": "load mhchem/siunitx when \\ce or \\SI needs it", "draftpictures": "skip the pictures in the draft pass for part numbers", "remotecsl": "fetch a csl: style named by URL", "typstdirect": "build .typ files with Typst directly", "htmldirect": "build .html files with WeasyPrint or a browser directly",
    "crossref": "pandoc-crossref for @fig: references", "citationengine": "citeproc / biblatex choice",
    "csvtable": "tables from CSV files", "papersize": "fix `pagesize:` to `papersize:`", "parts": "report/book parts",
    "lookup": "find a document by a name that is not exact", "unicode": "fonts for other scripts",
    "officeref": "a reference .docx/.odt found beside the document", "officestyle": "pdfmd's look in Word files",
    "officelatex": "make LaTeX native (or a picture) in Word files", "codewrap": "wrapping and numbering of code lines (LaTeX)", "officeprofile": "a house style's Word profile",
}


# the families of pdfmd.PAGEBREAK_KINDS, in its order
PAGEBREAK_CHOICES = (
    ("comment", "<!-- pagebreak -->, <!-- newpage -->, <!-- pdfmd: pagebreak -->"),
    ("tex", "\\newpage, \\pagebreak, \\clearpage, \\cleardoublepage"),
    ("html", '<div style="page-break-after: always">, <div class="pagebreak">'),
    ("div", "an empty ::: pagebreak"),
    ("typst", "a raw Typst #pagebreak()"),
    ("word", "a raw Word page break"),
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
        choice("colorlinks", "Coloured links", on_off, "", "", "Every document (global metadata)", "metadata"),
        choice("toc", "Table of contents", on_off, "", "", "Every document (global metadata)", "metadata"),
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
        # -- citations
        choice("options.citation-engine", "Citation engine",
               (("citeproc", "Pandoc's citeproc (the default)"), ("natbib", "natbib / BibTeX"),
                ("biblatex", "biblatex / biber")), "citeproc", "", "Citations"),
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
        choice("options.default-output", "Default output format",
               (("pdf", "PDF"), ("docx", "Word"), ("odt", "OpenDocument"), ("html", "HTML"), ("latex", "LaTeX"),
                ("typst", "Typst")), "pdf", "What `pdfmd file.md` writes when no -o or --to is given.", "Output"),
        choice("options.apply-defaults", "Defaults for .typ and .html files", (("true", "apply metadata.yaml's title, author, font, paper, margin"), ("false", "build them as they are")), "false",
               "A .typ or .html file is built by its own engine and gets no defaults. Per run: --apply-defaults.", "Output"),
        # -- HTML
        choice("options.html.self-contained", "HTML as one file", on_off, "", "Everything inlined (--embed-resources).",
               "HTML"),
        choice("options.html.standalone", "HTML as a full page", on_off, "",
               "A whole page with <head> (--standalone), not a fragment to paste into one.", "HTML"),
        text("options.html.css", "Style sheet for HTML", "A .css file; an absolute path, or one read beside each document.",
             "HTML"),
        choice("options.html.math", "Math in HTML",
               (("mathml", "MathML (no network)"), ("mathjax", "MathJax"), ("katex", "KaTeX"), ("webtex", "WebTeX images"),
                ("plain", "plain text")), "", "", "HTML"),
        # -- tables
        text("options.csv.rows", "Rows a .csv table shows", "A whole number, or all. A div's rows= wins. Per run: --csv-rows.",
             "Tables", "config", "count"),
        text("options.csv.cols", "Columns a .csv table shows", "A whole number, or all. A div's cols= wins. Per run: --csv-cols.",
             "Tables", "config", "count"),
        choice("options.csv.cut", "Where a long .csv table is cut",
               (("ends", "keep its first and last rows and columns, \u2026 between them"),
                ("head", "keep the first rows and columns only")), "ends", "A div's cut= wins.", "Tables"),
        choice("options.csv.delimiter", "The delimiter of .csv data",
               (("auto", "guessed from the first lines (a warning when it is not what the file name says)"),
                ("comma", ","), ("semicolon", ";"), ("tab", "tab"), ("pipe", "|")), "auto",
               "A div's delimiter= wins.", "Tables"),
        choice("options.table-widths", "Pipe-table column widths",
               (("auto", "a `---|---` separator means no opinion: widths that give the fewest lines"),
                ("keep", "exactly the widths the separator's dashes say")), "auto",
               "Unequal dashes are always kept; this is about equal ones.", "Tables"),
        # -- code
        choice("options.code-wrap", "Long code lines (LaTeX)", (("true", "wrap at the margin"), ("false", "run on")), "true",
               "Needs fvextra (in every full TeX Live). Per block: {wrap=false}.", "Code"),
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
        # -- PDF extras
        text("options.header", "Page header", "A template: {title}, {page}, {pages}, {date}, {header}.", "PDF finishing"),
        text("options.footer", "Page footer", "The same, e.g. {page} / {pages}.", "PDF finishing"),
        choice("options.bookmarks", "PDF bookmarks from headings", on_off, "", "", "PDF finishing"),
        choice("options.attach-links", "Attach linked files to the PDF", on_off, "", "", "PDF finishing"),
        choice("options.hybrid", "Make the PDF editable in LibreOffice (hybrid PDF)", on_off, "",
               "Attaches an OpenDocument copy as Original.odt; LibreOffice then opens the PDF as that document.", "PDF finishing"),
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
        # -- backups
        choice("options.backup.enabled", "A backup of the source after each build", on_off, "",
               "Into .backups/ beside the document, when it changed. Off unless set.", "Backups"),
        text("options.backup.dir", "Backup folder", "Where the copies go, beside the document (or an absolute path). Without "
             "one: .backups, a hidden folder, or a backup/ folder that is already there.", "Backups"),
        text("options.backup.format", "Backup file names",
             "compact, dashed, stem, suffix, short, or a template with {name} {stem} {ext} and strftime codes.",
             "Backups"),
        text("options.backup.keep", "Backups kept per document", "The newest n; 0 keeps all.", "Backups",
             "config", "number"),
        # -- the source inside the PDF
        choice("options.attach-source", "Attach the source to the PDF", on_off, "",
               "Anyone can read it back from the PDF (pdfmd --restore).", "Source inside the PDF"),
        choice("options.bundle", "Attach the images and files too", (("true", "what the text points at"), ("all", "everything")),
               "", "", "Source inside the PDF"),
        choice("options.bundle-packages", "Attach the LaTeX packages too", on_off, "",
               "The .sty/.cls files the build used that are not in TeX Live.", "Source inside the PDF"),
        text("options.bundle-max-mb", "Size limit of the attached bundle (MB)", "Default 100.", "Source inside the PDF",
             "config", "number"),
        choice("options.strip-comments", "Drop <!-- comments --> from what is assembled or attached", on_off, "", "",
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
        choice("options.cache.location", "Where the cache lives",
               (("global", "~/.cache/pdfmd"), ("document", ".cache/pdfmd beside the document")), "global", "", "Cache"),
        # -- input
        choice("options.text-to-markdown", "Read .txt files as Markdown",
               (("auto", "guess headings, lists, tables; a garbled text gets paragraphs only"),
                ("force", "guess structure even in a garbled text"), ("paragraphs", "paragraphs only, no structure")), "",
               "Off unless set. Needs batchocr 1.2.5 (pdfmd --install batchocr); the words never change.", "Input"),
        text("options.reader", "Markdown reader",
             "A Pandoc reader for every Markdown file: markdown, gfm, commonmark_x, with +/- extensions. Per run: --from.",
             "Input"),
        choice("options.metadata-precedence", "Which metadata file wins a key two of them set",
               (("later", "the later one, as Pandoc takes them"), ("first", "the first one")), "later",
               "pdfmd-options too. A document's own front matter beats both; the global metadata.yaml is below both. "
               "Per run: --metadata-precedence.", "Input"),
        # -- universal markup: what is written in one syntax, carried into every output (off unless set)
        choice("options.raw", "Carry raw HTML, LaTeX and Typst pieces into every output", on_off, "",
               "Raw pieces in another syntax than the output's are converted (HTML and LaTeX read into native elements, "
               "Typst drawn as a vector picture) instead of dropped. Per family: pdfmd-options.raw in a document.",
               "Universal markup"),
        Setting("options.pagebreak", "Page breaks carried into every format", "multi", PAGEBREAK_CHOICES, "",
                "Each spelling of a chosen family becomes the output's own page break. Per run: --pagebreak / "
                "--no-pagebreak.", "Universal markup"),
        # -- checks and limits
        choice("options.strict", "A warning fails the build", on_off, "",
               "The output is kept; the exit status is 1. Per run: --strict / --no-strict.", "Checks and limits"),
        text("options.max-asset-mb", "Warn about an image or data file over (MB)", "Before the build starts.",
             "Checks and limits", "config", "number"),
        text("options.max-output-mb", "Warn about an output over (MB)", "After the build.", "Checks and limits", "config",
             "number"),
        text("options.check-ignore", "Codes `pdfmd --check` leaves out", "Comma-separated, e.g. heading-skip, link-anchor.",
             "Checks and limits", "config", "list"),
        Setting("options.no-auto", "Automatic behaviour to switch off", "multi",
                tuple((kind, AUTO_HELP.get(kind, "")) for kind in sorted(no_auto_kinds)), "",
                "What pdfmd does by itself, off for every document (`--no-auto`).", "Automatic behaviour"),
        Setting("disabled", "Features switched off", "multi", feature_choices(), "",
                "Hidden from --help, completion and this screen, refused on the command line; "
                "`pdfmd --disabled ...` uses one for a run. Also the d key.", "Setup"),
        choice("setup-ui", "This setup screen",
               tuple((value, {"plain": "a numbered list", "fancy": "full screen (pdfmd --install tui)"}[value])
                     for value in setup_ui_choices), "plain", "", "Setup"),
    ]


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
            node = nodes[-1][part] = {}
        nodes.append(node)
    if value is not None:
        nodes[-1][parts[-1]] = value
        return
    nodes[-1].pop(parts[-1], None)
    for depth in range(len(parts) - 1, 0, -1):
        if nodes[depth]:
            break
        nodes[depth - 1].pop(parts[depth - 1], None)


def read(stores: dict, setting: Setting):
    return get(stores.setdefault(setting.store, {}), setting.key)


def write(stores: dict, setting: Setting, value) -> None:
    put(stores.setdefault(setting.store, {}), setting.key, value)


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
