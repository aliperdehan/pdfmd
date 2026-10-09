"""What `pdfmd --setup` can change: the settings of the global config file, and how to read and write them.

A setting is one key of the config file (`options.fallback` is `options:` / `fallback:`), with the values it
accepts and a line of help. Unset means "pdfmd's own default": the config file only ever holds what the
user chose, so deleting a line gives the default back.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    check: str = ""                   # "number" for a text that must be one


ON_OFF = (("on", "yes"), ("off", "no"))

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
    "svg": "convert SVG images for LaTeX", "remoteimages": "fetch and keep remote images", "typstdirect": "build .typ files with Typst directly", "htmldirect": "build .html files with WeasyPrint or a browser directly",
    "crossref": "pandoc-crossref for @fig: references", "citationengine": "citeproc / biblatex choice",
    "csvtable": "tables from CSV files", "papersize": "fix `pagesize:` to `papersize:`", "parts": "report/book parts",
    "lookup": "find a document by a name that is not exact", "unicode": "fonts for other scripts",
    "officeref": "a reference .docx/.odt found beside the document", "officestyle": "pdfmd's look in Word files",
    "officelatex": "make LaTeX native (or a picture) in Word files", "codewrap": "wrapping and numbering of code lines (LaTeX)", "officeprofile": "a house style's Word profile",
}


def settings_for(no_auto_kinds, setup_ui_choices=("plain", "fancy")) -> list[Setting]:
    """The settings, grouped by `section`. `no_auto_kinds` are the names `--no-auto` accepts."""
    def choice(key, title, choices, default="", help="", section="", store="config"):
        return Setting(key, title, "choice", tuple(choices), default, help, section, store)

    def text(key, title, help="", section="", store="config", check=""):
        return Setting(key, title, "text", (), "", help, section, store, check)

    on_off = ON_OFF
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
        choice("link-citations", "Link citations to the list", on_off, "", "", "Citations", "metadata"),
        choice("options.attach-bibliography", "A bibliography attached to the PDF",
               (("all", "every entry (the file as it is)"),), "", "By default only the entries the text cites travel.",
               "Citations"),
        # -- output
        choice("options.pdf-engine", "PDF engine",
               (("lualatex", "LuaLaTeX"), ("xelatex", "XeLaTeX"), ("pdflatex", "pdfLaTeX"),
                ("typst", "Typst (only Typst, no fallback to others)"), ("weasyprint", "WeasyPrint (HTML)"),
                ("tex", "only TeX engines"), ("html", "only HTML engines"), ("office", "only the LibreOffice route")), "",
               "The engine to try first (a family limits the fallback chain). `-e` on the command line wins.", "Output"),
        choice("options.default-output", "Default output format",
               (("pdf", "PDF"), ("docx", "Word"), ("odt", "OpenDocument"), ("html", "HTML"), ("latex", "LaTeX"),
                ("typst", "Typst")), "pdf", "What `pdfmd file.md` writes when no -o or --to is given.", "Output"),
        choice("options.html.self-contained", "HTML as one file", on_off, "", "Everything inlined (--embed-resources).",
               "Output"),
        choice("options.html.math", "Math in HTML",
               (("mathml", "MathML (no network)"), ("mathjax", "MathJax"), ("katex", "KaTeX"), ("webtex", "WebTeX images"),
                ("plain", "plain text")), "", "", "Output"),
        choice("options.table-widths", "Pipe-table column widths",
               (("auto", "a `---|---` separator means no opinion: widths that give the fewest lines"),
                ("keep", "exactly the widths the separator's dashes say")), "auto",
               "Unequal dashes are always kept; this is about equal ones.", "Output"),
        choice("options.apply-defaults", "Defaults for .typ and .html files", (("true", "apply metadata.yaml's title, author, font, paper, margin"), ("false", "build them as they are")), "false",
               "A .typ or .html file is built by its own engine and gets no defaults. Per run: --apply-defaults.", "Output"),
        choice("options.code-wrap", "Long code lines (LaTeX)", (("true", "wrap at the margin"), ("false", "run on")), "true",
               "Needs fvextra (in every full TeX Live). Per block: {wrap=false}.", "Output"),
        choice("options.line-numbers", "Number code lines (LaTeX)", on_off, "",
               "Off unless set. Per block: {.numberLines startFrom=10} or {.noNumberLines}.", "Output"),
        text("options.line-number-step", "Number every n-th code line", "1 is every line.", "Output", "config", "number"),
        choice("options.office.latex", "LaTeX in Word and ODT files",
               (("auto", "native where possible, pictures for the rest"), ("images", "pictures, formulas and units too"),
                ("off", "Pandoc's own behaviour")), "auto", "How `\\ce`, `\\si`, tikz and house macros reach a .docx/.odt.",
               "Output"),
        choice("options.office.labels", "Reference numbers in Word files",
               (("auto", "build the PDF once and read LaTeX's numbers"), ("off", "count them instead")), "auto",
               "Where \"Figure 3\" and \"Equation 2\" come from.", "Output"),
        # -- PDF extras
        text("options.header", "Page header", "A template: {title}, {page}, {pages}, {date}, {header}.", "PDF finishing"),
        text("options.footer", "Page footer", "The same, e.g. {page} / {pages}.", "PDF finishing"),
        choice("options.bookmarks", "PDF bookmarks from headings", on_off, "", "", "PDF finishing"),
        choice("options.attach-links", "Attach linked files to the PDF", on_off, "", "", "PDF finishing"),
        # -- source
        choice("options.stamp.enabled", "A \"Compiled with...\" line in the source", on_off, "",
               "Written into the document's BUILD NOTES after each build. Off unless set.", "The source file"),
        choice("options.backup.enabled", "A backup of the source after each build", on_off, "",
               "Into .backups/ beside the document, when it changed. Off unless set.", "The source file"),
        text("options.backup.dir", "Backup folder", "Where the copies go, beside the document (or an absolute path). Without "
             "one: .backups, a hidden folder, or a backup/ folder that is already there.", "The source file"),
        choice("options.strip-comments", "Drop <!-- comments --> from what is assembled or attached", on_off, "", "",
               "The source file"),
        choice("options.attach-source", "Attach the source to the PDF", on_off, "",
               "Anyone can read it back from the PDF (pdfmd --restore).", "The source file"),
        choice("options.bundle", "Attach the images and files too", (("true", "what the text points at"), ("all", "everything")),
               "", "", "The source file"),
        text("options.bundle-max-mb", "Size limit of the attached bundle (MB)", "Default 100.", "The source file",
             "config", "number"),
        # -- cache
        choice("options.cache.aux", "Remember reference numbers between builds", on_off, "",
               "Carries figure/table numbers over to a partial build of a long document.", "Cache"),
        choice("options.cache.location", "Where the cache lives",
               (("global", "~/.cache/pdfmd"), ("document", ".cache/pdfmd beside the document")), "global", "", "Cache"),
        # -- input
        choice("options.text-to-markdown", "Read .txt files as Markdown",
               (("auto", "guess headings, lists, tables; a garbled text gets paragraphs only"),
                ("force", "guess structure even in a garbled text"), ("paragraphs", "paragraphs only, no structure")), "",
               "Off unless set. Needs batchocr 1.2.5 (pdfmd --install batchocr); the words never change.", "Input"),
        Setting("options.no-auto", "Automatic behaviour to switch off", "multi",
                tuple((kind, AUTO_HELP.get(kind, "")) for kind in sorted(no_auto_kinds)), "",
                "What pdfmd does by itself, off for every document (`--no-auto`).", "Automatic behaviour"),
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
        return f"{setting.default or 'not set'} (default)" if setting.default else "not set"
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
