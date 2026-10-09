"""`pdfmd --help` in tiers (v3.25.14).

`pdfmd --help` is one short page: what to type for the usual jobs and the dozen options people reach for. `--help all`
is argparse's complete list; `--help TOPIC` is that list cut to one subject (`pdfmd --help tables`). Every option
belongs to a topic below (a test checks it); one that is left out still shows under "other" and in `--help all`.

pdfmd.py works without this package (a lone copy of the script): it then keeps argparse's single long page.
"""

from __future__ import annotations

import argparse
import sys

# topic -> (what it covers, option strings; a short form or any alias of an option names it)
TOPICS: dict[str, tuple[str, tuple[str, ...]]] = {
    "output": ("where the result goes, in what format, with which engine", (
        "-o", "-d", "-e", "-t", "--from", "--edit", "--init-vscode", "-f", "-y", "-V", "--open", "-w", "--keep-aux", "--self-contained",
        "--no-self-contained", "--paper", "--pdf-title", "--pdf-subject", "--pdf-author", "--pdf-keywords",
        "--bookmarks", "--header", "--footer", "--attach-links", "--no-citeproc", "--extract", "--text-to-markdown")),
    "modes": ("several files, one report, slides, a long document in parts", (
        "-p", "--slide-level", "-b", "-r", "--recursive", "-j", "-i", "--exclude-unnumbered", "--section",
        "--split", "--split-depth", "--list-parts")),
    "source": ("a PDF that carries its source, an assembled single file, comments", (
        "--stop-at", "--assemble-only", "--embed-metadata", "--no-embed-metadata", "--lua-mode", "--strip-comments",
        "--keep-comments", "--strip-comments-in", "--keep-comments-in", "--attach-bibliography", "--attach-source",
        "--no-attach-source", "--bundle", "--bundle-packages", "--no-bundle", "--restore", "--list", "--unpack",
        "--slim", "--trust-embedded", "--hybrid")),
    "tables": ("tables as CSV files, and back", (
        "--extract-tables", "--extract-inline-csv", "--expand-tables", "--table-numbers", "--table-names",
        "--tables-dir", "--tables-inline", "--dry-run")),
    "history": ("build notes, backups, versions of a document", (
        "--stamp", "--no-stamp", "--stamp-mode", "--stamp-store", "--stamp-packages", "--stamp-scope",
        "--stamp-output", "--no-stamp-output", "--stamp-pdf-metadata", "--no-stamp-pdf-metadata", "--backup",
        "--no-backup", "--backup-format", "--history-to-file", "--history-to-notes", "--history", "--history-all",
        "--history-diff", "--history-restore", "--no-restored-note", "--init-backups", "--backup-folder",
        "--global", "--merge-history", "--dry-run")),
    "code": ("code blocks", ("--line-numbers", "--no-code-wrap")),
    "raw": ("raw HTML, LaTeX, Typst and Word pieces inside Markdown", ("--raw", "--no-raw", "--raw-for")),
    "markdown": ("plain Markdown output (--to gfm), and Markdown that carries its source", (
        "--gfm-scripts", "--gfm-math")),
    "fonts": ("scripts, fonts, emoji, transliteration", (
        "--fallback", "--missing", "--check-fonts", "--translit", "--emoji-fallback", "-f")),
    "builtin": ("the built-in renderer used when there is no Pandoc or PDF engine", (
        "--family", "--no-autolinks", "--no-html", "--allow-unsafe-urls", "--allow-remote-images",
        "--emoji-fallback", "--paper")),
    "office": ("Word / OpenDocument output and direct .typ / .html builds", (
        "--check-docx", "--init-reference", "--apply-defaults", "--no-apply-defaults", "--hybrid")),
    "cache": ("faster rebuilds", ("--cache", "--cache-location", "--cache-plots", "--clear-cache", "--no-cache", "--seed-labels")),
    "setup": ("installing, configuring and checking pdfmd itself", (
        "--setup", "--init-config", "--show-config", "--install", "--uninstall", "--completion", "--doctor",
        "--check-dependencies", "--version")),
    "debug": ("seeing what pdfmd decided, and turning decisions off", (
        "-v", "--no-auto", "--full-paths", "--debug", "--keep-aux")),
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
  pdfmd report#results     just one section of a long document
  pdfmd -w report          rebuild whenever something changes
  pdfmd --restore a.pdf    write back the source a PDF carries (it needs --attach-source when built)

{options}

More:
  pdfmd --help TOPIC       the options of one subject:  {topics}
  pdfmd --help all         every option, the complete list
  pdfmd --doctor           what is installed and what is missing        pdfmd --setup   change the defaults
  README / CHANGELOG: https://github.com/aliperdehan/pdfmd
"""


def _option_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [action for action in parser._actions if action.option_strings]


def _named(action: argparse.Action, names: tuple[str, ...]) -> bool:
    return any(option in names for option in action.option_strings)


def uncovered(parser: argparse.ArgumentParser) -> list[str]:
    """The options that belong to no topic (a test keeps this empty)."""
    every = {name for _, names in TOPICS.values() for name in names}
    return [action.option_strings[-1] for action in _option_actions(parser)
            if not _named(action, tuple(every)) and "-h" not in action.option_strings]


def _full(parser: argparse.ArgumentParser) -> str:
    return parser.format_help()


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
    try:
        return parser.format_help()
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
    return SHORT.format(options=options, topics=", ".join(TOPICS))


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
        else:
            text = _topic(parser, values)
        _write(text)
        parser.exit()
