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
    kind: str                         # "choice" | "multi"
    choices: tuple[tuple[str, str], ...] = ()      # (value, what it means)
    default: str = ""                 # what pdfmd does when the key is not set (a choice value, or "" for none)
    help: str = ""
    section: str = ""


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
    "crossref": "pandoc-crossref for @fig: references", "citationengine": "citeproc / biblatex choice",
    "csvtable": "tables from CSV files", "papersize": "fix `pagesize:` to `papersize:`", "parts": "report/book parts",
    "lookup": "find a document by a name that is not exact", "unicode": "fonts for other scripts",
    "officeref": "a reference .docx/.odt found beside the document", "officestyle": "pdfmd's look in Word files",
    "officelatex": "make LaTeX native (or a picture) in Word files", "officeprofile": "a house style's Word profile",
}


def settings_for(no_auto_kinds, setup_ui_choices=("plain", "fancy")) -> list[Setting]:
    """The settings, grouped by `section`. `no_auto_kinds` are the names `--no-auto` accepts."""
    return [
        Setting("options.fallback", "Characters the font lacks", "choice",
                (("word", "set the whole word in another font"), ("char", "set just those characters in another font"),
                 ("document", "the one font that draws most of the document becomes the main font"),
                 ("off", "nothing: what Pandoc and TeX do without pdfmd"), ("box", "no fallback; boxes"),
                 ("error", "the build fails, listing the characters")), "word",
                "What to do about characters the main font cannot draw.", "Fonts and characters"),
        Setting("options.missing", "Characters no font draws", "choice",
                (("warn", "warn and go on"), ("box", "draw a box"), ("error", "fail the build")), "warn",
                "What to do about characters no installed font draws, after the fallback.", "Fonts and characters"),
        Setting("options.unicode", "Fonts for other scripts", "choice", ON_OFF, "",
                "Set Arabic, Han, Greek... runs in an installed font for their script even when the main font has them.",
                "Fonts and characters"),
        Setting("translit", "Finding a document by a Latin spelling", "multi", TRANSLIT, "",
                "Romanization packs for finding 命運.md when told `mingyun` (Cyrillic is always on).",
                "Fonts and characters"),
        Setting("options.pdf-engine", "PDF engine", "choice",
                (("lualatex", "LuaLaTeX"), ("xelatex", "XeLaTeX"), ("pdflatex", "pdfLaTeX"), ("typst", "Typst (only Typst, no fallback to others)"),
                 ("weasyprint", "WeasyPrint (HTML)"), ("tex", "only TeX engines"),
                 ("html", "only HTML engines"), ("office", "only the LibreOffice route")), "",
                "The engine to try first (a family limits the fallback chain). `-e` on the command line wins.",
                "Output"),
        Setting("options.default-output", "Default output format", "choice",
                (("pdf", "PDF"), ("docx", "Word"), ("odt", "OpenDocument"), ("html", "HTML"), ("latex", "LaTeX"),
                 ("typst", "Typst")), "pdf", "What `pdfmd file.md` writes when no -o or --to is given.", "Output"),
        Setting("options.office.latex", "LaTeX in Word and ODT files", "choice",
                (("auto", "native where possible, pictures for the rest"), ("images", "pictures"),
                 ("off", "Pandoc's own behaviour")), "auto",
                "How `\\ce`, `\\si`, tikz and house macros reach a .docx/.odt.", "Output"),
        Setting("options.office.labels", "Reference numbers in Word files", "choice",
                (("auto", "build the PDF once and read LaTeX's numbers"), ("off", "count them instead")), "auto",
                "Where \"Figure 3\" and \"Equation 2\" come from.", "Output"),
        Setting("options.cache.aux", "Remember reference numbers between builds", "choice", ON_OFF, "",
                "Carries figure/table numbers over to a partial build of a long document.", "Cache"),
        Setting("options.cache.location", "Where the cache lives", "choice",
                (("global", "~/.cache/pdfmd"), ("document", ".cache/pdfmd beside the document")), "global",
                "", "Cache"),
        Setting("options.no-auto", "Automatic behaviour to switch off", "multi",
                tuple((kind, AUTO_HELP.get(kind, "")) for kind in sorted(no_auto_kinds)), "",
                "What pdfmd does by itself, off for every document (`--no-auto`).", "Automatic behaviour"),
        Setting("setup-ui", "This setup screen", "choice",
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
    return text


def from_stored(setting: Setting, value) -> str | None:
    """A stored value as the text of a choice (None when it is not one of them)."""
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value) if value is not None else None
