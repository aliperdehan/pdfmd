"""`pdfmd --help` in tiers (v3.25.14).

`pdfmd --help` is one short page: what to type for the usual jobs and the dozen options people reach for. `--help all`
is argparse's complete list; `--help TOPIC` is that list cut to one subject (`pdfmd --help tables`). Every option
belongs to a topic below (a test checks it); one that is left out still shows under "other" and in `--help all`.

Without this package argparse keeps its single long page. Since 3.33.0 that is not a shipped case: pdfmd.py stops at start
when its lib/ folder is missing.
"""

from __future__ import annotations

import argparse
import sys

# topic -> (what it covers, option strings; a short form or any alias of an option names it)
TOPICS: dict[str, tuple[str, tuple[str, ...]]] = {
    "output": ("where the result goes, in what format, with which engine", (
        "-o", "-d", "--rewrite", "--no-rewrite", "-e", "--engine-fallback", "-t", "--from", "--flavour", "--unclosed-comment", "--edit", "--init-vscode", "-f", "--editor", "-y", "--metadata-precedence", "--preset", "--presets", "--kit", "--kit-stack", "--kits", "--global-metadata", "-V", "--css", "--css-scope", "--open", "--bopen", "-w", "--keep-aux", "--self-contained",
        "--no-self-contained", "--paper", "--paragraph-spacing", "--pdf-title", "--pdf-subject", "--pdf-author", "--pdf-keywords",
        "--bookmarks", "--header", "--footer", "--page-numbers", "--no-page-numbers", "--attach-links", "--shrink", "--no-shrink", "--no-citeproc", "--pagecite", "--fullcite-list", "--bibliography-indent", "--bibliography", "--extract", "--text-to-markdown",
        "--stylesheet", "--style", "--css-file", "--format", "--page-size", "--orientation", "--border",
        "--border-top", "--border-left", "--border-bottom", "--border-right", "--as-html",
        "--document-title", "--subject", "--author", "--keywords", "--input", "--workers")),
    "modes": ("several files, one report, slides, a long document in parts", (
        "-p", "--no-presentation", "--slide-level", "-b", "-r", "--recursive", "-j", "-i", "--exclude-unnumbered", "--section",
        "--split", "--split-depth", "--list-parts", "--newest", "--all", "--include-never", "--which")),
    "source": ("a PDF that carries its source, an assembled single file, comments", (
        "--stop-at", "--assemble-only", "--merge", "--embed-metadata", "--no-embed-metadata", "--lua-mode", "--strip-comments",
        "--keep-comments", "--strip-comments-in", "--keep-comments-in", "--attach-bibliography", "--attach-csl", "--attach-source",
        "--no-attach-source", "--no-attach-csl", "--bundle", "--bundle-packages", "--no-bundle", "--restore", "--list", "--unpack",
        "--slim", "--trust-embedded", "--hybrid", "--check-source")),
    "tables": ("CSV, widths and spacing", (
        "--extract-tables", "--extract-inline-csv", "--expand-tables", "--csv", "--no-csv", "--csv-rows", "--csv-cols", "--csv-note", "--table-keep", "--table-numbers", "--table-names",
        "--tables-dir", "--tables-inline", "--table-repair", "--fix-tables", "--dry-run")),
    "history": ("build notes, backups, versions of a document", (
        "--stamp", "--no-stamp", "--stamp-mode", "--stamp-store", "--stamp-packages", "--stamp-scope",
        "--stamp-partial", "--no-stamp-partial", "--stamp-output", "--no-stamp-output", "--stamp-pdf-metadata", "--no-stamp-pdf-metadata", "--backup",
        "--no-backup", "--backup-format", "--history-to-file", "--history-to-notes", "--history", "--history-all",
        "--history-diff", "--history-restore", "--no-restored-note", "--init-backups", "--backup-folder",
        "--global", "--merge-history", "--dry-run")),
    "code": ("code blocks and inline code", ("--line-numbers", "--no-code-wrap")),
    "raw": ("raw HTML, LaTeX, Typst and Word pieces inside Markdown, page breaks", (
        "--raw", "--no-raw", "--raw-for", "--pagebreak", "--no-pagebreak", "--linebreak", "--no-linebreak", "--markup", "--no-markup", "--show-hidden", "--show-comments", "--no-show-comments", "--calc", "--no-calc", "--calc-digits", "--calc-round", "--calc-subs", "--no-calc-subs", "--calc-typeset", "--no-calc-typeset", "--calc-typeset-upright", "--calc-typeset-italic", "--calc-noindent", "--no-calc-noindent", "--calc-space", "--calc-align", "--calc-constants", "--calc-export")),
    "markdown": ("plain Markdown, text and ASCII output (--to gfm, txt, ascii), and Markdown that carries its source", (
        "--gfm-scripts", "--gfm-math", "--ascii-missing", "--keep-source", "--no-keep-source", "--restore", "--list")),
    "view": ("reading a document in the terminal: styled text, tables, math as text (--view, --to ansi)", (
        "--view", "--pager", "--colour", "--width")),
    "fonts": ("scripts, fonts, emoji, transliteration", (
        "--fallback", "--missing", "--check-fonts", "--translit", "--emoji-fallback", "-f")),
    "builtin": ("the built-in renderer used when there is no Pandoc or PDF engine", (
        "--family", "--no-autolinks", "--no-html", "--allow-unsafe-urls", "--allow-remote-images",
        "--emoji-fallback", "--paper")),
    "office": ("Word / OpenDocument output and direct .typ / .html builds", (
        "--check-docx", "--init-reference", "--apply-defaults", "--no-apply-defaults", "--hybrid")),
    "crop": ("cutting and exporting PDF pages. For an existing PDF, use --chatter to set output detail or "
             "--mute crop-empty-page,crop-already-pdf to hide notes about blank pages and PDFs left as they are",
             ("--crop", "--no-crop", "--crop-pad", "--crop-ignore-bottom", "--crop-page", "--image-dpi", "--image-quality",
              "--image-background", "--page-numbers", "--no-page-numbers", "--page-folder", "--no-page-folder")),
    "excerpts": ("local source records, citation resolution and detachment", ("--excerpts",)),
    "serve": ("the local server and JSON API behind the web UI (for the Mac app, a browser, or your own tools)", ("--serve", "--api")),
    "cache": ("faster rebuilds", ("--cache", "--cache-location", "--cache-plots", "--clear-cache", "--cache-info", "--no-cache", "--seed-labels", "--seed-calc")),
    "setup": ("installing, configuring and checking pdfmd itself", (
        "--setup", "--disabled", "--init-config", "--show-config", "--install", "--uninstall", "--completion", "--doctor", "--json",
        "--check-dependencies", "--version", "--trust-lua", "--deep", "--init", "--doc", "--print", "--path",
        "--user-path", "--add-to-path", "--remove-from-path", "--show-user-path", "--yes",
        "--pandoc-path", "--typst-path", "--chrome-path", "--tesseract-path", "--soffice-path", "--dot-path",
        "--mmdc-path", "--poppler-path", "--ghostscript-path", "--mutool-path")),
    "debug": ("seeing what pdfmd decided, and turning decisions off", (
        "-v", "-q", "--no-auto", "--full-paths", "--path-style", "--path-up", "--debug", "--keep-aux", "--strict", "--chatter", "--mute", "--log", "--summary", "--check", "--check-ignore",
        "--max-asset-mb", "--max-output-mb", "--build-time", "--no-build-time", "--time-format", "--build-log", "--last-build", "--failed")),
}

COMMON = {
    "-o": "output file (a folder with -b), the extension picks the format",
    "-t": "output format: docx, odt, html, typst, epub, latex ...",
    "-e": "PDF engine, or a family: tex, html, typst, office",
    "-d": "save the PDF in the current folder, not beside the source",
    "-y": "metadata YAML file(s); a bare -y turns discovery off",
    "-b": "every Markdown file in the folder, one result each",
    "-r": "all of them joined into one document",
    "-p": "Beamer slides",
    "--section": "build only these sections of a document in parts",
    "-w": "rebuild whenever the source changes",
    "--open": "open the result when it is done",
    "-v": "show every automatic decision and the commands run",
}

SHORT = """\
pdfmd: Markdown (and other Pandoc-readable files) to PDF, Word or HTML. It finds the metadata, preamble, filters,
fonts and an engine that works by itself.

  pdfmd                    build the Markdown file in this folder (when there is only one)
  pdfmd report             report.md -> report.pdf (the .md is optional; the name may be approximate)
  pdfmd report -t docx     another format: docx, odt, html, typst, epub ... (or -o report.docx)
  pdfmd -b                 every Markdown file in the folder, one PDF each
  pdfmd -r                 all of them joined into one PDF
  pdfmd report#results     just one section of a long document (report@results where # is a comment)
  pdfmd -w report          rebuild whenever something changes
  pdfmd --view report      read it in the terminal: styled, tables drawn, paged (also: cat x.md | pdfmd --view)
  pdfmd --restore a.pdf    write back attached source (may normalise front matter)

{options}

More:
  pdfmd --help TOPIC       the options of one subject:  {topics}
  pdfmd --help all         every option, the complete list
  pdfmd --doctor           what is installed and what is missing        pdfmd --setup   change the defaults
  README / CHANGELOG: https://github.com/aliperdehan/pdfmd
"""


# Topics the config can switch off as a whole (v3.27.8, `disabled:` in config.yaml, `pdfmd --setup` and `d`): their
# options are hidden from --help, completion and the setup screen, and refused on the command line unless --disabled
# is given. An option that also belongs to a topic still on stays. These three stay on: without them pdfmd cannot build
# anything, or be set up again.
CORE = ("output", "setup", "debug")
DISABLEABLE = tuple(topic for topic in TOPICS if topic not in CORE)


def topics_of(action: argparse.Action) -> set[str]:
    return {topic for topic, (_, names) in TOPICS.items() if any(name in names for name in action.option_strings)}


def hide(parser: argparse.ArgumentParser, disabled) -> list[argparse.Action]:
    """Hide the options of switched-off topics from `parser`'s help (they still parse); returns their actions."""
    off = {topic for topic in disabled or () if topic in DISABLEABLE}
    parser.pdfmd_disabled = off
    hidden = []
    for action in _option_actions(parser):
        topics = topics_of(action)
        if topics and topics <= off:
            action.help = argparse.SUPPRESS
            hidden.append(action)
    return hidden


def _option_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [action for action in parser._actions if action.option_strings]


def _named(action: argparse.Action, names: tuple[str, ...]) -> bool:
    return any(option in names for option in action.option_strings)


def uncovered(parser: argparse.ArgumentParser) -> list[str]:
    """The options that belong to no topic (a test keeps this empty)."""
    every = {name for _, names in TOPICS.values() for name in names}
    return [action.option_strings[-1] for action in _option_actions(parser)
            if not _named(action, tuple(every)) and "-h" not in action.option_strings
            and action.help != argparse.SUPPRESS]          # an internal option (--ascii-stdio) has no page


FIGURE_FIT_HELP = ("pdfmd-options.figure-fit: on (default) or off. LaTeX and Typst fit images and their captions "
                   "to the page body. A figure image can override it with fit=on or fit=off. "
                   "Typst still warns about figures that are too tall when fitting is off.\n")

PROPERTIES_HELP = ("pdfmd-options.properties: show: false (default), true (ordinary non-empty keys), all, "
                   "or a list of keys. hide removes keys, labels renames them, place is top (default) or end, "
                   "and style is table (default), list or inline. Slides use properties only when the document "
                   "sets properties in its own front matter. Also in --setup.\n")

PRE_CITEPROC_HELP = ("pdfmd-options.lua-filter-before-citeproc: named Lua filters run before citation processing. "
                    "Use a path or list, or append with lua-filter-before-citeproc+. Default: none.\n")


CITATION_ALIASES_HELP = ("pdfmd-options.citation-aliases: map short keys to bibliography keys before citeproc, e.g. "
                         "{short: existing-key}. Real keys win. Missing targets warn. Default: none.\n")

NUMBERED_REFERENCES_HELP = ("pdfmd-options.numbered-references: trailing numbered source lists become Pandoc citations "
                            "when every marker matches. On by default in pdfmd and obsidian, off in pandoc, gfm and "
                            "commonmark. Set on or off to override the flavour. "
                            "With a citeproc bibliography, web sources keep their own list and numbers. "
                            "--check reports numbered-references-off for a matching document with conversion off. "
                            "--to md writes the converted citations and references. Also in --setup.\n")


def _check_codes() -> str:
    from pdfmd_check import CODES

    return "\n--check codes\n" + "".join(f"  {code} ({severity}): {description}\n"
                                         for code, (severity, description) in CODES.items())


def _full(parser: argparse.ArgumentParser) -> str:
    return parser.format_help() + ("\npdfmd-options.pandoc-memory: heap size (512m, 2g); unset = off.\n"
                                 "pdfmd-options.indent (or indent:): false/unset = writer default; true = the writer's standard indent; lengths: 0.5in, 3em, 1cm.\n"
                                 + FIGURE_FIT_HELP + PRE_CITEPROC_HELP + CITATION_ALIASES_HELP + NUMBERED_REFERENCES_HELP + PROPERTIES_HELP
                                 + _check_codes())


def _topic(parser: argparse.ArgumentParser, topic: str) -> str:
    """argparse's own help for the options of one topic (the others are hidden for the moment)."""
    summary, names = TOPICS[topic] if topic != "other" else ("options no topic claims", ())
    every = tuple({name for _, listed in TOPICS.values() for name in listed})
    hidden: list[tuple[argparse.Action, object]] = []
    for action in _option_actions(parser):
        keep = _named(action, names) if topic != "other" else not _named(action, every)
        if "-h" in action.option_strings:
            keep = True
        if not keep:
            hidden.append((action, action.help))
            action.help = argparse.SUPPRESS
    previous = parser.description
    parser.description = f"{topic}: {summary}"
    if topic == "tables":
        parser.description += (". column-estimate: count (default) | measure (LaTeX/Typst PDF). "
                               "--verbose reports measured/cached widths. table-chars: 95 (LaTeX fallback). "
                               "table-style: spaced. table-row-spacing: 1.4. "
                               "Equal dashes use default sizing in Typst, HTML, Word and ODT. "
                               "table-colons: ignore | count, column-widths: keep, column-word-ceil: on | off, "
                               "column-ceil-margin: 25% (pdfmd-options or --setup). --check reports table-unparsed.")
    try:
        text = parser.format_help()
        if topic == "output":
            text += ("\npdfmd-options.pandoc-memory: heap size (512m, 2g); unset = off.\n"
                     "pdfmd-options.indent (or indent:): false/unset = writer default; true = the writer's standard indent; lengths: 0.5in, 3em, 1cm.\n"
                     + FIGURE_FIT_HELP + PRE_CITEPROC_HELP + CITATION_ALIASES_HELP + NUMBERED_REFERENCES_HELP + PROPERTIES_HELP)
        if topic == "setup":
            text += ("\nOn macOS, if a downloaded Calibre disk image stays attached, pdfmd prints the manual detach command.\n")
        if topic == "debug":
            text += _check_codes()
        return text
    finally:
        parser.description = previous
        for action, text in hidden:
            action.help = text


def _short(parser: argparse.ArgumentParser) -> str:
    rows = []
    for key, text in COMMON.items():
        action = next((item for item in _option_actions(parser) if key in item.option_strings), None)
        if action is None:
            continue
        longer = next((name for name in action.option_strings if name.startswith("--")), None)
        flags = action.option_strings[0] + (f", {longer}" if longer and longer != action.option_strings[0] else "")
        if action.nargs != 0 and action.metavar:
            flags += f" {action.metavar}"
        rows.append((flags, text))
    width = max(len(flags) for flags, _ in rows) + 2
    options = "Common options:\n" + "\n".join(f"  {flags.ljust(width)}{text}" for flags, text in rows)
    off = getattr(parser, "pdfmd_disabled", set())
    return SHORT.format(options=options, topics=", ".join(topic for topic in TOPICS if topic not in off))


def _write(text: str) -> None:
    """Print `text`; a console that cannot show a character (a cp1252 Windows pipe and the CJK sample in
    `--translit`'s help) gets `?` for it instead of a traceback."""
    text = text if text.endswith("\n") else text + "\n"
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        sys.stdout.write(text.encode(encoding, "replace").decode(encoding))


class TieredHelp(argparse.Action):
    """`-h` / `--help` [TOPIC]: the short page, a topic, or `all`."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, **kwargs):
        super().__init__(option_strings, dest=dest, default=default, nargs="?",
                         choices=["all", "other", *TOPICS], metavar="TOPIC",
                         help="this help; `--help all` lists every option, `--help TOPIC` one subject ("
                              + ", ".join(TOPICS) + ")")

    def __call__(self, parser, namespace, values, option_string=None):
        if values is None:
            text = _short(parser)
        elif values == "all":
            text = _full(parser)
        elif values in getattr(parser, "pdfmd_disabled", set()):
            text = (f"The {values} features are switched off (`pdfmd --setup`, d). `pdfmd --disabled --help {values}` "
                    "shows them; `--disabled` also lets one run use them.")
        else:
            text = _topic(parser, values)
        _write(text)
        parser.exit()
