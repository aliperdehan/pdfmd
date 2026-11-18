"""The full reference in place (`fullcite`): the formatted reference of a source, printed where the author asks for it.

    [@trinkaus1984]{.fullcite}      a span around a real citation: the entry, as a block when it is alone in its paragraph,
                                    as text inside a sentence
    [[fullcite:trinkaus1984]]       the older spelling, alone in its paragraph, in every flavour
    ::: fullcite                    one entry for each `@key` line
    @trinkaus1984
    :::

Two Lua filters do it, because citeproc runs between them: `pdfmd_lua/fullcite_mark.lua` (before citeproc) turns each spelling
into the span and records its keys, `pdfmd_lua/fullcite.lua` (after citeproc, before the document's own filters) takes the entries
from citeproc's list. Under `--biblatex` / `--natbib` there is no citeproc, and the first one alone writes `\\fullcite{KEY}` /
`\\bibentry{KEY}`. Both go in only for a document that uses a spelling and has the `fullcite` kind of universal markup (on in the
pdfmd and obsidian flavours, off in a named Pandoc reader; `pdfmd-options: {markup: ...}` and `--markup` choose).

Settings: `pdfmd-options.fullcite-list` (`rest`, the default: what was placed leaves the combined list; `all`: the list stays whole;
`none`: no combined list), from the document, its metadata files, the folder layers and the global setup (`first_pdfmd_option`
reads them in that order), and `--fullcite-list V` for a run (below them all, so the command line wins). One entry or one block
beats the setting: `[@key]{.fullcite list=keep}` / `list=drop`, `::: {.fullcite list=keep}`.

`core` is the `pdfmd` module (`from pdfmd_base import core`); the pdfmd names the code uses (`first_pdfmd_option`, `markup_kinds`,
`read_text_best_effort`, `display_path`, `EMBED_BLOCK_RE`, `CITEPROC_DISABLED`) are read as `core.X` when it runs.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pdfmd_base import core
import pdfmd_bibliography as bibliography

ENV = "PDFMD_FULLCITE_LIST"                  # --fullcite-list, set by main(), so -j workers read it too
KEY = "fullcite-list"
MODES = ("rest", "all", "none")
KIND = "fullcite"                            # the word in `markup:`

# a span with the class, a div with it, the old spelling
SYNTAX_RE = re.compile(r"\{[^}\n]*\.fullcite\b|^[ \t]*:{3,}[ \t]*fullcite\b|\[\[fullcite:", re.MULTILINE)
OLD_SPELLING_RE = re.compile(r"\[\[fullcite:[^\[\]|\n]+\]\]")


def old_spelling_in(text: str) -> bool:
    """Whether `text` has `[[fullcite:KEY]]` (it has no citation for the reader to see, so `contains_citations` asks)."""
    return "[[fullcite:" in text and bool(OLD_SPELLING_RE.search(text))


def fullcite_old_spelling(md_path: Path, metadata_files=()) -> bool:
    """Whether the file has `[[fullcite:KEY]]` and the document may use it (the `fullcite` markup kind is on for its flavour)."""
    try:
        text = core.read_text_best_effort(md_path)
    except OSError:
        return False
    if "[[fullcite:" not in text:
        return False
    from pdfmd_flavours.markup import comment_source
    text = comment_source(text, md_path, metadata_files, show=False)
    return old_spelling_in(core.EMBED_BLOCK_RE.sub("", text)) and KIND in core.markup_kinds(md_path, list(metadata_files))


def command_line_value(value: str) -> str:
    """--fullcite-list as main() hands it to the builds; a word that is none of MODES stops the run."""
    word = str(value).strip().casefold()
    if word not in MODES:
        raise SystemExit(f"--fullcite-list must be one of {', '.join(MODES)}, not {value!r}")
    return word


def fullcite_command_line(value: str) -> None:
    """Pass a validated command-line value to this run and its batch workers."""
    os.environ[ENV] = command_line_value(value)


def list_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """The `fullcite-list` of this build: --fullcite-list, else `pdfmd-options.fullcite-list` (the document, its metadata files, the
    folder layers, the global setup), else `rest`."""
    value = os.environ.get(ENV)
    if value is not None:
        return command_line_value(value)
    value = core.first_pdfmd_option(md_path, metadata_files, KEY)
    if value is None:
        return "rest"
    word = str(value).strip().casefold()
    if word not in MODES:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.{KEY} must be one of {', '.join(MODES)}, not {value!r}")
    return word


def wanted(sources: Path | list[Path], metadata_files: list[Path]) -> bool:
    """Whether the document uses a spelling of fullcite and the `fullcite` kind of markup is on for it."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or files[0].suffix.lower() not in (".md", ".markdown"):
        return False
    if KIND not in core.markup_kinds(files[0], metadata_files):
        return False
    return any(SYNTAX_RE.search(core.EMBED_BLOCK_RE.sub("", core.read_text_best_effort(file))) for file in files if file.is_file())


def lua(name: str) -> Path | None:
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return None
    return pdfmd_lua.path(name)


def engine_of(pandoc_options: list[str], engine: str | None = None) -> str | None:
    """`biblatex` or `natbib` when Pandoc is to write the citations for BibTeX/Biber, else None (citeproc)."""
    if engine in ("biblatex", "natbib"):
        return engine
    for word in ("biblatex", "natbib"):
        if f"--{word}" in pandoc_options:
            return word
    return None


NATBIB_HEADER = "% pdfmd: \\bibentry (fullcite with citation-engine: natbib) needs its package, after natbib\n\\usepackage{bibentry}\n"


def natbib_header(engine: str) -> list[str]:
    """`--include-in-header` of a file that loads the `bibentry` package, for natbib (nothing for biblatex, whose `\\fullcite` is its own)."""
    if engine != "natbib":
        return []
    path = core.cache_root() / "tex" / "fullcite-bibentry.tex"
    try:
        if not path.is_file() or path.read_text(encoding="utf-8") != NATBIB_HEADER:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(NATBIB_HEADER, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(path)]


def fullcite_pre_args(sources: Path | list[Path], metadata_files: list[Path], pandoc_options: list[str],
             engine: str | None = None) -> list[str]:
    """The filter that runs before `--citeproc` (see the top), or [] when the document does not use fullcite."""
    files = sources if isinstance(sources, list) else [sources]
    if not wanted(files, metadata_files):
        return []
    used = engine_of(pandoc_options, engine)
    if used is None and core.CITEPROC_DISABLED:
        return []
    shipped = lua("fullcite_mark")
    if shipped is None:
        return []
    return (["-M", f"pdfmd-fullcite-engine={used}", *natbib_header(used)] if used else []) + ["--lua-filter", str(shipped)]


def fullcite_post_args(sources: Path | list[Path], metadata_files: list[Path], cmd: list[str], pandoc_options: list[str]) -> list[str]:
    """The filter that runs after `--citeproc`, with the settings it reads, or [] (no fullcite in the document, or no citeproc)."""
    files = sources if isinstance(sources, list) else [sources]
    if "--citeproc" not in cmd and "--citeproc" not in pandoc_options:
        return []
    if not wanted(files, metadata_files):
        return []
    shipped = lua("fullcite")
    if shipped is None:
        return []
    return ["-M", f"pdfmd-fullcite-list={list_mode(files[0], metadata_files)}",
            "-M", f"pdfmd-fullcite-indent={bibliography.setting(files[0], metadata_files) or bibliography.DEFAULT}",
            "-M", f"pdfmd-fullcite-doc={core.display_path(files[0])}",
            "--lua-filter", str(shipped)]
