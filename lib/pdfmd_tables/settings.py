"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_tables.settings`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import functools
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from pdfmd_base import core


# Auto-applied on every LaTeX-family render (see table_width_filter() below).
# Pandoc's LaTeX writer only wraps pipe-table cells when every column has an
# explicit width; a table with none (ColWidth "default" -- what gfm's reader
# always produces, see resolve_from_format()) instead gets plain unwrapped
# `l`/`c`/`r` columns, so a long cell just runs past the page margin instead
# of breaking. This filter leaves any table that already has explicit widths
# alone, and for one that doesn't AND whose content is actually wide enough
# to risk overflowing the page, sizes each column proportionally to its
# longest cell's text length (spreading a spanning cell's length evenly
# across the columns it covers) instead of Pandoc's own default-`markdown`
# behaviour of forcing every column to the same equal fraction regardless of
# content -- see resolve_from_format()'s docstring for why that's also worth
# avoiding. A floor keeps a column with only short labels from collapsing to
# unreadable thinness next to a verbose neighbor.
#
# BUG, found and fixed 2026-09-16 (the author, via a nulabreport/QCA report): this
# used to fire on EVERY table with any default-width column, regardless of
# whether the table's own content came anywhere near overflowing -- a short
# 4-column numeric table ("Sample #" / four-digit masses / a percentage) got
# stretched across the FULL page width for no reason, fighting a downstream
# package Lua filter (nulabreport.lua) that deliberately sizes such a table
# to its natural content width instead. The intent (see the paragraph above,
# unchanged) was always "rescue a table that would otherwise overflow," not
# "give every unwidthed table an opinion" -- this was never meant to fire on
# a table that already fits comfortably. Fixed with a real, if approximate,
# overflow check: estimate the table's total natural width by summing each
# column's longest-cell character count (same measurement already used for
# the proportions below) and comparing against CHAR_BUDGET, a rough
# characters-per-line figure for this project's own default document shape
# (12pt serif body text, ~1in margins on A4/Letter -- see DEFAULT_MARGIN).
# This is deliberately an ESTIMATE, not a real width computation (Pandoc's
# Lua filters run before any font is ever measured, so an exact figure isn't
# available here at all) -- it only needs to be good enough to distinguish
# "a handful of short numeric columns" from "a table with real prose cells,"
# which a raw character count comfortably does. A table with an unusual
# fontsize/geometry front-matter override is not specially accounted for;
# revisit CHAR_BUDGET (or make it geometry-aware) if that turns out to
# matter in practice, rather than assuming this estimate transfers exactly.
TABLE_WIDTH_LUA_FILTER = "table_width"   # pdfmd_lua/table_width.lua


# Auto-applied whenever a document uses a `.csv`-classed fenced Div (see
# contains_csv_table()) -- turns a Div like
#
#     ::: {.csv file="data.csv"}
#     :::
#
# into an actual table, read from that CSV/TSV file, instead of a hand-
# transcribed pipe table -- requested directly (2026-09-19, the author), alongside
# a size cap so an accidentally-huge file doesn't produce a many-page
# table nobody intended: 10 rows and 7 columns by default (`rows`/`cols`
# attributes override either, or set to `all` for no cap), matching the
# request's own suggested numbers. A Div, not raw-text substitution keyed
# on some new sigil character (`\input`-style inclusion was floated for
# the same underlying reason, and rejected for exactly the risk this
# avoids): Pandoc has already correctly told code blocks/spans apart from
# real content by the time a Lua filter's Div() callback ever fires, so
# `::: {.csv ...}` typed inside a fenced code block as a literal example
# is never mistaken for the real thing -- the false-fire risk the author raised
# for a raw-text approach simply can't happen at this level.
#
# Builds the table via pandoc.read() on a hand-assembled GFM pipe-table
# string, rather than constructing pandoc.Table's own AST nodes directly
# -- both produce an equivalent Table block, but this one reuses Pandoc's
# own (already-correct) pipe-table parser instead of this filter needing
# to get every field of TableHead/TableBody/Cell/ColSpec exactly right by
# hand, and it guarantees the result looks EXACTLY like a table pdfmd
# already knows how to handle everywhere else (including
# TABLE_WIDTH_LUA_FILTER re-balancing it afterward, since a pipe-table's
# parsed colspecs are the same "default width" shape a document's own
# hand-written table would produce).
#
# The CSV/TSV line parser handles quoted fields (comma/tab inside a
# quoted cell, and a doubled `""` for a literal quote) but, deliberately,
# not a quoted field containing a literal embedded newline spanning
# multiple physical lines -- a genuine RFC 4180 parser is real added
# complexity for a case simple spreadsheet exports essentially never
# produce, and this filter is explicitly meant to stay simple.
CSV_TABLE_LUA_FILTER = "csv_table"   # pdfmd_lua/csv_table.lua


def width_filter_args(width_filter: Path) -> list[str]:
    """``--lua-filter`` for the table-width filter, with the global column settings of the config or `--setup` handed
    to it (`column-widths`, `column-word-floor`, `column-count-raw-tex`, and the numbers `column-outlier`,
    `column-outlier-rows`, `column-outlier-length`, `column-word-floor-limit`); a document's own `pdfmd-options` reaches
    it through the metadata and wins. `table-widths` and `table-word-floor` are the older names, still read."""
    args = ["--lua-filter", str(width_filter)]
    options = core.config_options()
    words = (("column-widths", "table-widths", ("auto", "keep", "force")),
             ("column-word-floor", "table-word-floor", ("on", "off", "true", "false")),
             ("column-count-raw-tex", None, ("on", "off", "true", "false")))
    for key, older, allowed in words:
        value = options.get(key)
        if value is None and older:
            value = options.get(older)
        if isinstance(value, bool):
            value = "on" if value else "off"
        if isinstance(value, str) and value.strip().casefold() in allowed:
            args += ["-M", f"pdfmd-{key}={value.strip().casefold()}"]
    for key in ("column-outlier", "column-outlier-rows", "column-outlier-length", "column-word-floor-limit"):
        number = options.get(key)
        if isinstance(number, str) and number.strip().casefold() in ("off", "false"):
            number = 0
        elif isinstance(number, str) and number.strip().replace(".", "", 1).isdigit():
            number = float(number) if "." in number else int(number)
        if isinstance(number, (int, float)) and not isinstance(number, bool) and number >= 0:
            args += ["-M", f"pdfmd-{key}={number}"]
    return args


@contextmanager
def csv_table_filter() -> Iterator[Path]:
    """pdfmd_lua/csv_table.lua, for --lua-filter."""
    with core.lua_filter_file(CSV_TABLE_LUA_FILTER, "pdfmd-csvtable-") as path:
        yield path


# `::: {.csv ...}`, or the bare `::: csv` for inline data (`file=` and `align=` need the braces; `::: csvfile` and
# `::: csv-x` are other classes)
CSV_DIV_RE = re.compile(r"""\{(?:[^}"\n]|"(?:[^"\\\n]|\\.)*")*\.csv\b|^[ \t]*:{3,}[ \t]*csv[ \t]*$""", re.MULTILINE)


def contains_csv_table(md_path: Path) -> bool:
    """Detect a `.csv`-classed fenced Div (see CSV_TABLE_LUA_FILTER)."""
    text = core.EMBED_BLOCK_RE.sub("", md_path.read_text(encoding="utf-8-sig"))
    return bool(CSV_DIV_RE.search(text))


# The cap of a `.csv` table, for every table of a document (v3.27.2): --csv-rows / --csv-cols (reaching -j workers as
# PDFMD_CSV_ROWS / PDFMD_CSV_COLS, as --strict does), else `pdfmd-options: {csv: {rows, cols, header, reader}}` (the
# document, its metadata files, the config: field by field), else 10 rows x 7 columns, a header row and Pandoc's
# Markdown in the cells. A div's own rows= / cols= / header= / reader= still win for that one table.
CSV_DEFAULTS = {"rows": 10, "cols": 7, "header": True, "reader": "markdown", "delimiter": "auto", "cut": "ends", "note": "short"}


CSV_ENV = {"rows": "PDFMD_CSV_ROWS", "cols": "PDFMD_CSV_COLS"}


# The note under a table that was cut (v3.30.22): `short` states the fact only ("showing the first 7 and the last 3 of 11 rows", only
# for what was cut), `full` adds the advice that used to stand in every PDF, `off` leaves it out (the `...` row still marks the cut).
# The advice is in the WARN on stderr, once per table, whatever the note says. --csv-note (PDFMD_CSV_NOTE for -j workers), else
# `pdfmd-options: {csv: {note: off}}`, else short; a div's own note= wins for that table.
CSV_NOTES = ("short", "off", "full")


CSV_NOTE_ENV = "PDFMD_CSV_NOTE"


def csv_note_mode(value) -> str | None:
    """A note mode from a command line, an option or a div attribute: short, off or full (YAML reads a bare `off` as False and
    `on` as True, so those count too); None when it is none of them."""
    if value is True:
        return "short"
    if value is False:
        return "off"
    text = str(value).strip().casefold()
    text = {"on": "short", "true": "short", "false": "off", "no": "off", "yes": "short", "none": "off"}.get(text, text)
    return text if text in CSV_NOTES else None


def csv_count(value) -> int | str | None:
    """A rows/cols cap: a positive whole number or "all"; None when it is neither."""
    text = str(value).strip().casefold()
    if text == "all":
        return "all"
    return int(text) if text.isdigit() and int(text) > 0 else None


# `csv: off` switches the `.csv` div off for a document, the way `calc: off` does the calculator: the Lua filter is not
# added and the div stays as written (a plain div with its text), with no WARN. `pdfmd-options: {csv: off}` is the short form of
# `{csv: {enabled: false}}`, and a mapping (`csv: {rows: 30}`) leaves the tables on. --csv / --no-csv for a run (reaching -j
# workers as PDFMD_CSV); the command line wins over the options.
CSV_ENABLED_ENV = "PDFMD_CSV"


def csv_enabled_option(md_path: Path | None, metadata_files: list[Path] = ()):
    """`pdfmd-options.csv.enabled`; `csv: off` alone means `enabled: off`. None when nothing says."""
    value = core.first_pdfmd_option(md_path, list(metadata_files), "csv") if md_path is not None else None
    if isinstance(value, dict):
        return value.get("enabled")
    return value


def csv_is_off(md_path: Path | None, metadata_files: list[Path] = ()) -> bool:
    value = os.environ.get(CSV_ENABLED_ENV)
    if value is None:
        value = csv_enabled_option(md_path, metadata_files)
    if value is None:
        return False
    flag = core.option_flag(value)
    if flag is None:
        where = core.display_path(md_path) if md_path is not None else "csv"
        raise SystemExit(f"{where}: pdfmd-options.csv.enabled must be true or false, not {value!r}")
    return not flag


# `tablekeep` for a Lua filter (v3.30.2): nulabreport.lua keeps a Markdown table of up to that many body rows on one page.
# --table-keep N (reaching -j workers as PDFMD_TABLE_KEEP), else `pdfmd-options: {table-keep: N}` (the document, its
# metadata files, the config: first one wins), else nothing, and the metadata's own `tablekeep:` or the filter's default
# stands. N reaches Pandoc as -M, which wins over a metadata file; 0 means "let every table break".
TABLE_KEEP_ENV = "PDFMD_TABLE_KEEP"


def table_keep_count(value) -> int | None:
    """A table-keep row count: a whole number, 0 included; None when it is not one."""
    text = str(value).strip()
    return int(text) if text.isdigit() else None


# Table captions typed by hand (v3.31.46, entry 3dy): `**Table 1: Results**` next to a table becomes the table's caption.
# pdfmd-options: table-captions: note (the default: nothing changes, one NOTE says how many lines would have been captions),
# on, off; table-caption-label: strip (default) | keep; table-caption-words: extra label words (the dictionary of
# pdfmd_tables/captions.py follows `lang:`); table-caption-need-label: on (default) | off (any bold line is a caption);
# table-caption-colon-words: a number, 0 (default) off: a gfm `: Results` of at most
# that many words is a caption too.
TABLE_CAPTION_MODES = ("note", "on", "off")


TABLE_CAPTION_LABELS = ("strip", "keep")


TABLE_CAPTION_NEED = ("on", "off")


def table_caption_settings(md_path: Path, metadata_files: list[Path]) -> dict:
    """The table-caption options as they stand (documented above), checked: a word that is not one of the choices stops the build."""
    def switch(value, name, choices, default):
        if value is None:
            return default
        word = {True: "on", False: "off"}.get(value, str(value).strip().casefold())
        if word not in choices:
            raise SystemExit(f"pdfmd-options {name}: {value!r} is not one of {', '.join(choices)}")
        return word
    mode = switch(core.first_pdfmd_option(md_path, metadata_files, "table-captions"), "table-captions", TABLE_CAPTION_MODES, "note")
    label = switch(core.first_pdfmd_option(md_path, metadata_files, "table-caption-label"), "table-caption-label", TABLE_CAPTION_LABELS, "strip")
    need = switch(core.first_pdfmd_option(md_path, metadata_files, "table-caption-need-label"), "table-caption-need-label", TABLE_CAPTION_NEED, "on")
    colon = core.first_pdfmd_option(md_path, metadata_files, "table-caption-colon-words")
    try:
        colon_words = 0 if colon in (None, False) else int(colon)
    except (TypeError, ValueError):
        colon_words = -1
    if colon_words < 0:
        raise SystemExit(f"pdfmd-options table-caption-colon-words: {colon!r} must be a whole number of words (0 is off)")
    extra = core.first_pdfmd_option(md_path, metadata_files, "table-caption-words")
    extra = [part for part in re.split(r"[,;]", extra)] if isinstance(extra, str) else list(extra or [])
    return {"mode": mode, "label": label, "need": need, "colon": colon_words, "extra": [str(word) for word in extra]}


def table_caption_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter table_caption.lua`` with its settings (`-M pdfmd-table-captions=...`), for a document that has a line
    which could be a caption; nothing for `off`, and nothing for a document without such a line (the filter would only look)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []
    settings = table_caption_settings(files[0], metadata_files)
    if settings["mode"] == "off":
        return []
    try:
        from pdfmd_tables.captions import label_words
    except ImportError:
        return []
    words = label_words(core.document_font_setting("lang", files, metadata_files, []), settings["extra"])
    start = r"^[ \t]*\*\*[ \t]*(?:" + "|".join(re.escape(word) for word in words) + ")"
    if settings["need"] == "off":
        start = r"^[ \t]*\*\*\S"
    if settings["colon"] > 0:
        start = "(?:" + start + r")|(?:^: \S)"
    pattern = re.compile(start, re.MULTILINE | re.IGNORECASE)
    if not any(pattern.search(core.EMBED_BLOCK_RE.sub("", core.read_text_best_effort(file))) for file in files):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("table_caption")
    if shipped is None:
        return []
    return ["-M", "pdfmd-table-captions=" + settings["mode"], "-M", "pdfmd-table-caption-label=" + settings["label"],
            "-M", "pdfmd-table-caption-need-label=" + settings["need"],
            "-M", f"pdfmd-table-caption-colon-words={settings['colon']}", "-M", "pdfmd-table-caption-words=" + ",".join(words),
            "--lua-filter", str(shipped)]


# Cell tags of pipe tables: one cell's alignment (v3.31.52, entry 3el) and merged cells (v3.32.31, entry 3fa). A cell may carry a tag
# (`<c>`, `&mc&`, `&<<&`, `<merge-up, top>`, a bare `<<` or `^^`) anywhere in it; lib/pdfmd_tables/celltags.py (a pre-pass on a temporary
# copy) reads every spelling and writes one canonical raw tag, and pdfmd_lua/cellalign.lua makes the spans and the alignment from it (the
# filter goes in after the table-width filter). pdfmd-options: cell-align: on (the default) | off, which switches every cell tag off;
# table-tag-brackets: which spellings are read (a list of angle, amp, brace, guillemet; default angle, amp).
CELL_TAG_KINDS = ("angle", "amp", "brace", "guillemet")


CELL_TAG_DEFAULT_KINDS = ("angle", "amp")


def cell_align_on(md_path: Path, metadata_files: list[Path]) -> bool:
    """The `cell-align` option: on unless the document, a metadata file or the config says off (anything else stops the build)."""
    value = core.first_pdfmd_option(md_path, metadata_files, "cell-align")
    if value is None:
        return True
    word = {True: "on", False: "off"}.get(value, str(value).strip().casefold())
    if word not in ("on", "off"):
        raise SystemExit(f"pdfmd-options cell-align: {value!r} is not one of on, off")
    return word == "on"


def cell_tag_kinds(md_path: Path, metadata_files: list[Path]) -> tuple[str, ...]:
    """The `table-tag-brackets` option: the spellings of a cell tag that are read (a list, or words split by commas or spaces)."""
    value = core.first_pdfmd_option(md_path, metadata_files, "table-tag-brackets")
    if value is None:
        return CELL_TAG_DEFAULT_KINDS
    words = [str(item) for item in value] if isinstance(value, list) else re.split(r"[,\s]+", str(value))
    kinds = tuple(dict.fromkeys(word.strip().casefold() for word in words if word.strip()))
    for kind in kinds:
        if kind not in CELL_TAG_KINDS:
            raise SystemExit(f"pdfmd-options table-tag-brackets: {kind!r} is not one of {', '.join(CELL_TAG_KINDS)}")
    return kinds


CELL_ALIGN_WORDS = {"l": "l", "left": "l", "r": "r", "right": "r", "c": "c", "center": "c", "centre": "c"}


CELL_VALIGN_WORDS = {"t": "t", "top": "t", "m": "m", "middle": "m", "b": "b", "bottom": "b"}


def table_defaults(md_path: Path, metadata_files: list[Path]) -> dict[str, str]:
    """The `table-align` (left, right, centre) and `table-valign` (top, middle, bottom) options: the alignment every cell has when
    nothing more specific says (its tag, row, column or the table's own `{align=}`); {} for neither. A word that is not one of them
    stops the build. Either one set makes every table of the document go through cellalign.lua (a vertical one through tabularray)."""
    found: dict[str, str] = {}
    for option, words, key in (("table-align", CELL_ALIGN_WORDS, "h"), ("table-valign", CELL_VALIGN_WORDS, "v")):
        value = core.first_pdfmd_option(md_path, metadata_files, option)
        if value in (None, "", False):
            continue
        word = str(value).strip().casefold()
        if word not in words:
            raise SystemExit(f"pdfmd-options {option}: {value!r} is not one of {', '.join(sorted(set(words)))}")
        found[key] = words[word]
    return found


def cell_tags_text(text: str, md_path: Path, metadata_files: list[Path], label: str) -> str:
    """``text`` with the cell tags of its pipe tables written as canonical tags (a WARN for each thing that could not be done)."""
    if "|" not in text or not cell_align_on(md_path, list(metadata_files)):
        return text
    try:
        from pdfmd_tables.celltags import normalise
    except ImportError:
        return text
    result = normalise(text, cell_tag_kinds(md_path, list(metadata_files)))
    for note in result.notes:
        print(f"WARN  cell-tags: {label}, line {note.line}: {note.message}")
    return result.text


@functools.lru_cache(maxsize=1)
def tabularray_available() -> bool:
    """Whether LaTeX has the `tabularray` package, which draws a cell's vertical alignment (found with kpsewhich)."""
    kpsewhich = shutil.which("kpsewhich")
    if not kpsewhich:
        return False
    try:
        found = subprocess.run([kpsewhich, "tabularray.sty"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(found.strip())


def cell_tag_counts(sources: Path | list[Path], metadata_files: list[Path]) -> tuple[int, int]:
    """(cells with a tag or tables with settings, those LaTeX draws only with tabularray: a vertical alignment, a width, a height) in the
    pipe tables of the sources; (0, 0) when `cell-align` is off."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or not cell_align_on(files[0], metadata_files):
        return 0, 0
    try:
        from pdfmd_tables.celltags import normalise
    except ImportError:
        return 0, 0
    kinds = cell_tag_kinds(files[0], metadata_files)
    found = [normalise(core.EMBED_BLOCK_RE.sub("", core.read_text_best_effort(file)), kinds) for file in files]
    return sum(result.cells for result in found), sum(result.tblr for result in found)


TABLAY_NOTED: set[str] = set()


def cellalign_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter cellalign.lua`` for a document with a cell tag in a pipe table, unless `cell-align` is off. Vertical
    alignment is drawn in LaTeX with tabularray; without it the filter is told (`-M pdfmd-tblr=off`) and says so once."""
    files = sources if isinstance(sources, list) else [sources]
    tagged, vertical = cell_tag_counts(files, metadata_files)
    defaults = table_defaults(files[0], metadata_files) if files and cell_align_on(files[0], metadata_files) else {}
    if not tagged and not defaults:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("cellalign")
    if shipped is None:
        return []
    arguments = ["--lua-filter", str(shipped)]
    for key, option in (("h", "pdfmd-table-align"), ("v", "pdfmd-table-valign")):
        if key in defaults:
            arguments = ["-M", f"{option}={defaults[key]}"] + arguments
    if (vertical or "v" in defaults) and not core.tabularray_available():
        arguments = ["-M", "pdfmd-tblr=off"] + arguments
        label = core.display_path(files[0])
        if label not in core.TABLAY_NOTED:
            core.TABLAY_NOTED.add(label)
            print(f"NOTE  cell-tags: {label}: a table has a vertical alignment, a width or a height, which LaTeX draws with its "
                  "`tabularray` package; it was not found (kpsewhich), so LaTeX ignores these except percentage widths. HTML is unaffected.")
    return arguments


def tblr_header_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """`--include-in-header` with tabularray for a LaTeX build of a document with a vertical alignment in a cell, or [] (a filter's
    `header-includes` is dropped by every header file of pdfmd's, so the package goes in a file of its own)."""
    files = sources if isinstance(sources, list) else [sources]
    _, vertical = cell_tag_counts(files, metadata_files)
    if files and cell_align_on(files[0], metadata_files) and "v" in table_defaults(files[0], metadata_files):
        vertical += 1
    if not vertical or not core.tabularray_available():
        return []
    text = ("% pdfmd: vertical alignment of table cells (cell tags, entry 3fa)\n\\usepackage{tabularray}\n\\UseTblrLibrary{booktabs}\n"
            "% a long table repeats its header on every page, as Pandoc's own tables do, without tabularray's continuation texts\n"
            "\\DeclareTblrTemplate{contfoot-text}{pdfmd}{}\n\\SetTblrTemplate{contfoot-text}{pdfmd}\n"
            "\\DeclareTblrTemplate{conthead-text}{pdfmd}{}\n\\SetTblrTemplate{conthead-text}{pdfmd}\n")
    header = core.cache_root() / "tex" / f"packages-tblr-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not header.is_file():
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(header)]


CSV_DELIMITER_NAMES = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|", "space": " ", "colon": ":"}


CSV_DELIMITER_WORDS = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe", " ": "space", ":": "colon"}


@contextmanager
def table_width_filter() -> Iterator[Path]:
    """pdfmd_lua/table_width.lua, for --lua-filter. The filter appends a line to PDFMD_TABLEWIDTH_LOG for every table
    it resizes; tablewidth_note() reads that back (v3.28.18)."""
    log = Path(tempfile.gettempdir()) / f"pdfmd-tablewidth-{os.getpid()}.log"
    log.unlink(missing_ok=True)
    os.environ["PDFMD_TABLEWIDTH_LOG"] = str(log)
    with core.lua_filter_file(TABLE_WIDTH_LUA_FILTER, "pdfmd-tablewidth-") as path:
        yield path


def tablewidth_note(md_path, note) -> None:
    """Say that the table-width filter resized tables in the build just made, once (AUTO TABLEWIDTH), and forget it."""
    name = os.environ.get("PDFMD_TABLEWIDTH_LOG")
    if not name:
        return
    log = Path(name)
    try:
        seen = set(log.read_text(encoding="utf-8").split())
        log.unlink(missing_ok=True)
    except OSError:
        return
    count = sum(1 for mark in seen if not mark.endswith("w"))
    widened = sum(1 for mark in seen if mark.endswith("w"))
    if count:
        note("TABLEWIDTH", f"{md_path}: {count} wide table{'s' if count != 1 else ''} had no column widths (or "
                           "`column-widths: force` is set); pdfmd balanced the columns (--no-auto tablewidth stops it)")
    if widened:
        note("TABLEWIDTH", f"{md_path}: {widened} table{'s' if widened != 1 else ''} had a column too narrow for its "
                           "longest word; pdfmd widened it and took the room from the others (`column-widths: keep` "
                           "leaves the widths as written)")


# Text tables Pandoc does not read as tables (v3.31.47-52, entry 3el): ASCII tables without the inner `+` of a grid table
# (what chat models write for "a plain-text table", lazy forms too), box-drawing tables, psql and MySQL console output,
# Org-mode tables (`|---+---|`) and `|` lines with no separator row.
# pdfmd_tables/ascii.py turns them into pipe tables, in memory (a temporary copy, the file is never touched). pdfmd-options: table-ascii: repair (the default, one WARN per table) | note (leave
# it, say so) | off.
TABLE_ASCII_MODES = ("repair", "note", "off")


ORG_CAPTION_RE = re.compile(r"^ {0,3}#\+CAPTION(?:\[[^\]]*\])?:", re.MULTILINE | re.IGNORECASE)


def table_ascii_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """The `table-ascii` option (documented above), checked: a word that is not one of the choices stops the build."""
    value = core.first_pdfmd_option(md_path, metadata_files, "table-ascii")
    if value is None:
        return "repair"
    word = {True: "repair", False: "off"}.get(value, str(value).strip().casefold())
    if word not in TABLE_ASCII_MODES:
        raise SystemExit(f"pdfmd-options table-ascii: {value!r} is not one of {', '.join(TABLE_ASCII_MODES)}")
    return word


def repair_ascii_text(text: str, mode: str, label: str) -> str:
    """``text`` with its ASCII tables turned into pipe tables (mode `repair`), or unchanged with a NOTE for each (`note`);
    ``label`` names the file in the messages. Nothing to say, and nothing done, when there is no such table."""
    if mode == "off":
        return text
    try:
        from pdfmd_tables.ascii import repair_ascii_tables
    except ImportError:
        return text
    fixed, repairs = repair_ascii_tables(text)
    for repair in repairs:
        if repair.kind == "extras":          # a pipe table that was fine: only the `#+` lines around it were dealt with
            if mode != "note":
                for problem in repair.problems:
                    print(f"WARN  table-ascii: {label}, line {repair.line}: {problem}")
            continue
        shape = f"{repair.columns} columns, {repair.rows} row{'s' if repair.rows != 1 else ''}"
        if mode == "note":
            print(f"NOTE  table-ascii: {label}, line {repair.line}: {repair.what} ({shape}) that Pandoc does not read as a "
                  "table; pdfmd-options: table-ascii: repair rewrites it as a pipe table, off ends this note")
            continue
        print(f"WARN  table-ascii: {label}, line {repair.line}: {repair.what} was read as a pipe table ({shape}); "
              "pdfmd-options: table-ascii: off keeps it as written")
        for problem in repair.problems:
            print(f"WARN  table-ascii: {label}, line {repair.line}: {problem}")
    return text if mode == "note" else fixed
