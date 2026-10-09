"""Tables to `.csv` blocks (extract) and back (expand)."""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .scan import (FENCE_RE, CsvBlock, FoundTable, caption_parts, find_csv_blocks, find_tables, split_row,
                   unescape_cell)

DEFAULT_ROWS, DEFAULT_COLUMNS = 10, 7                   # the caps a `.csv` block applies unless `rows=`/`cols=` say
SEPARATOR_CELL_RE = re.compile(r"^\s*:?-+:?\s*$")
ALIGN_LETTERS = {"left": "l", "center": "c", "right": "r", "default": "d"}
ALIGN_NAMES = {"l": "left", "left": "left", "c": "center", "center": "center", "centre": "center", "r": "right",
               "right": "right", "d": "default", "default": "default"}
DELIMITER_NAMES = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|", "space": " ", "colon": ":"}
INLINE_FORMS = ("external", "inline")


class TablesError(Exception):
    """A request pdfmd cannot carry out; the message says what to change."""


@dataclass
class Extracted:
    text: str
    files: dict[str, str] = field(default_factory=dict)       # path (as written in file=) -> its CSV
    report: list[str] = field(default_factory=list)
    changed: int = 0


# ---- Pandoc reads the three table kinds that are not pipe tables ------------------------------------------------

def _run(command: list[str], text: str) -> str:
    done = subprocess.run(command, input=text, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise TablesError(done.stderr.strip() or f"{command[0]} failed")
    return done.stdout


def read_with_pandoc(table: FoundTable, pandoc: str) -> None:
    """Fill `table` from Pandoc's own reading: its header, rows, alignments and widths, or say why it cannot be CSV."""
    try:
        document = json.loads(_run([pandoc, "-f", "markdown", "-t", "json"], "\n".join(table.lines) + "\n"))
    except (TablesError, ValueError) as error:
        table.problem = f"Pandoc could not read it ({error})"
        return
    node = next((block for block in document["blocks"] if block["t"] == "Table"), None)
    if node is None:
        table.problem = "Pandoc does not read it as a table"
        return
    _, _, colspecs, head, bodies, _foot = node["c"]
    table.aligns = [spec[0]["t"].replace("Align", "").lower() for spec in colspecs]
    widths = [spec[1]["c"] if spec[1]["t"] == "ColWidth" else None for spec in colspecs]
    table.widths = widths if all(width is not None for width in widths) else None
    if not head[1]:
        table.problem = "it has no header row (a CSV block always has one)"
        return
    node["c"][1] = [None, []]                             # the caption is read separately
    document["blocks"] = [node]
    written = _run([pandoc, "-f", "json", "-t", "markdown+pipe_tables-simple_tables-multiline_tables-grid_tables",
                    "--columns=100000", "--wrap=none"], json.dumps(document))
    found = find_tables(written)
    if len(found) != 1 or found[0].kind != "pipe" or found[0].end - found[0].start < 3 or len(bodies) != 1:
        table.problem = "its cells hold more than one line of text (lists, paragraphs, code) or span rows/columns"
        return
    table.header, table.rows = found[0].header, found[0].rows
    width = len(table.aligns)
    if len(table.header) != width or any(len(row) != width for row in table.rows):
        table.problem = "its rows do not all have the same number of cells"


# ---- extract ---------------------------------------------------------------------------------------------------

def csv_text(header: list[str], rows: list[list[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


def slug(caption: str | None) -> str:
    """A file name from a caption: words only, lower case, at most 40 characters."""
    text = caption_parts(caption)[0]
    text = re.sub(r"[`*_$~^\\\[\]<>]|\{[^}]*\}", " ", text)
    text = unicodedata.normalize("NFKC", text).lower()
    words = re.findall(r"[^\W_]+", text)
    name = "-".join(words)[:40].strip("-")
    return name


def quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _first_row_is_separator(rows: list[list[str]]) -> bool:
    return bool(rows) and all(SEPARATOR_CELL_RE.match(cell) for cell in rows[0])


def _width_text(widths: list[float]) -> str:
    return ",".join(f"{width * 100:.4g}%" for width in widths)


def _attributes(table: FoundTable, file_name: str | None) -> tuple[str, bool]:
    """The `{.csv ...}` attribute text, and whether the caption has to follow the block as a paragraph."""
    parts = [".csv"]
    if file_name:
        parts.append(f"file={quoted(file_name)}")
    caption_below = False
    if table.caption:
        if '"' in table.caption or "\\" in table.caption or "\n" in table.caption:
            caption_below = True
        else:
            parts.append(f"caption={quoted(table.caption)}")
    if any(align != "default" for align in table.aligns):
        parts.append(f"align={quoted(''.join(ALIGN_LETTERS[align] for align in table.aligns))}")
    if table.widths:
        parts.append(f"widths={quoted(_width_text(table.widths))}")
    if len(table.rows) > DEFAULT_ROWS:
        parts.append("rows=all")
    if len(table.header) > DEFAULT_COLUMNS:
        parts.append("cols=all")
    if _first_row_is_separator(table.rows):
        parts.append("separator=none")
    return " ".join(parts), caption_below


def block_lines(table: FoundTable, data: str, file_name: str | None, indent: str = "") -> list[str]:
    attributes, caption_below = _attributes(table, file_name)
    lines = [f"{indent}::: {{{attributes}}}"]
    if not file_name:
        longest = max([len(run) for run in re.findall(r"`+", data)] + [2])
        fence = "`" * (longest + 1)
        lines += [f"{indent}{fence}", *[f"{indent}{row}" for row in data.rstrip("\n").split("\n")], f"{indent}{fence}"]
    lines.append(f"{indent}:::")
    if caption_below and table.caption:
        lines += ["", f"{indent}: {table.caption}"]
    return lines


def choose_names(tables: list[FoundTable], given: list[str] | None) -> list[str]:
    if given is not None:
        if len(given) != len(tables):
            raise TablesError(f"{len(given)} name{'' if len(given) == 1 else 's'} given for {len(tables)} "
                              f"table{'' if len(tables) == 1 else 's'} in the document; give one name per table, "
                              "in the order they appear")
        clean = [re.sub(r"\.csv$", "", name.strip(), flags=re.I) for name in given]
        if any(not name or re.search(r"[\\/]", name) for name in clean):
            raise TablesError("a table name is a file name without a folder: " + ", ".join(given))
        if len(set(clean)) != len(clean):
            raise TablesError("two tables were given the same name")
        return clean
    names: list[str] = []
    for position, table in enumerate(tables, 1):
        name = slug(table.caption) or f"table{position}"
        base, counter = name, 2
        while name in names:
            name, counter = f"{base}-{counter}", counter + 1
        names.append(name)
    return names


def extract(text: str, base_dir: Path, *, pandoc: str | None, names: list[str] | None = None,
            directory: str = "tables", inline: bool = False) -> Extracted:
    """Every table of `text` as a `.csv` block: the data in `directory` beside the document (`file=`), or inside
    the block with `inline`. Tables that cannot be written as CSV are left as they are, with the reason."""
    tables = find_tables(text)
    result = Extracted(text)
    if not tables:
        result.report.append("no tables found")
        return result
    chosen = choose_names(tables, names)
    lines = text.split("\n")
    used: dict[str, str] = {}
    for position in range(len(tables) - 1, -1, -1):
        table, name = tables[position], chosen[position]
        label = f"table {position + 1}" + (f" ({name})" if names or table.caption else "")
        if table.kind != "pipe":
            if pandoc is None:
                table.problem = f"{table.kind} tables need Pandoc to be read"
            else:
                read_with_pandoc(table, pandoc)
        elif not table.header:
            table.problem = "it has no header"
        if table.problem:
            result.report.insert(0, f"SKIP  {label}: {table.problem}")
            continue
        data = csv_text(table.header, table.rows)
        file_name = None
        if not inline:
            file_name = f"{directory.rstrip('/')}/{name}.csv"
            target = base_dir / file_name
            counter = 2
            while (file_name in used and used[file_name] != data) or \
                    (target.exists() and target.read_text(encoding="utf-8") != data):
                if names is not None:
                    raise TablesError(f"{file_name} already exists and holds something else; choose another name")
                file_name = f"{directory.rstrip('/')}/{name}-{counter}.csv"
                target = base_dir / file_name
                counter += 1
            used[file_name] = data
            result.files[file_name] = data
        indent = re.match(r" *", lines[table.start]).group(0) if table.kind == "pipe" else ""
        lines[table.span[0]:table.span[1]] = block_lines(table, data, file_name, indent)
        result.report.insert(0, f"{'EXTRACT' if file_name else 'INLINE '}  {label}: " +
                             (file_name if file_name else f"{len(table.rows)} rows, inside the document"))
        result.changed += 1
    result.text = "\n".join(lines)
    result.files = dict(reversed(list(result.files.items())))     # in the order of the tables
    return result


# ---- expand ----------------------------------------------------------------------------------------------------

def read_csv_data(block: CsvBlock, base_dir: Path) -> tuple[str, str]:
    """(the text, where it came from) of a `.csv` block's data."""
    name = block.attributes.get("file")
    if name:
        try:
            return (base_dir / name).read_text(encoding="utf-8-sig"), name
        except OSError as error:
            raise TablesError(f"cannot read {name}: {error.strerror or error}")
    if block.data is None:
        raise TablesError("a .csv block with neither file= nor data")
    return block.data, "inline data"


def guess_delimiter(text: str, name: str | None) -> str:
    if name and name.lower().endswith(".tsv"):
        return "\t"
    first = text.splitlines()[0] if text.strip() else ""
    best, best_count = ",", 0
    for candidate in (",", ";", "\t", "|"):
        count, in_quotes = 0, False
        for char in first:
            if char == '"':
                in_quotes = not in_quotes
            elif char == candidate and not in_quotes:
                count += 1
        if count > best_count:
            best, best_count = candidate, count
    return best


def block_table(block: CsvBlock, base_dir: Path) -> tuple[list[str], list[list[str]], list[str], list[float] | None]:
    """(header, rows, alignments, widths) of a `.csv` block, as the Lua filter reads them (all rows, no caps)."""
    text, origin = read_csv_data(block, base_dir)
    delimiter = block.attributes.get("delimiter")
    delimiter = DELIMITER_NAMES.get(delimiter.lower(), delimiter[:1]) if delimiter else \
        guess_delimiter(text, block.attributes.get("file"))
    rows = [row for row in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter) if row]
    if not rows:
        raise TablesError(f"{origin} holds no data")
    columns = max(len(row) for row in rows)
    rows = [(row + [""] * columns)[:columns] for row in rows]
    has_header = block.attributes.get("header") != "false"
    header = rows.pop(0) if has_header else [f"Column {n}" for n in range(1, columns + 1)]
    aligns: list[str] | None = None
    widths: list[float] | None = None
    if has_header and rows and block.attributes.get("separator", "auto").lower() not in ("none", "false") \
            and all(SEPARATOR_CELL_RE.match(cell) for cell in rows[0]):
        separator = rows.pop(0)
        aligns = []
        counts = []
        for cell in separator:
            cell = cell.strip()
            left, right = cell.startswith(":"), cell.endswith(":")
            aligns.append("center" if left and right else "left" if left else "right" if right else "default")
            counts.append(len(cell))
        if len(set(counts)) > 1:
            widths = [count / sum(counts) for count in counts]
    given = block.attributes.get("align")
    if given:
        if re.fullmatch(r"[lcrdLCRD]+", given):
            aligns = [ALIGN_NAMES[letter] for letter in given.lower()]
        else:
            aligns = [ALIGN_NAMES.get(word, "default") for word in re.split(r"[,\s]+", given.lower()) if word]
    given = block.attributes.get("widths")
    if given:
        try:
            words = [word for word in re.split(r"[,\s]+", given.strip()) if word]
            numbers = [float(word.rstrip("%")) for word in words]
            if numbers and all(number > 0 for number in numbers):
                percent = all(word.endswith("%") for word in words) and sum(numbers) <= 100.5
                widths = [number / (100 if percent else sum(numbers)) for number in numbers]
        except ValueError:
            pass
    aligns = ((aligns or []) + ["default"] * columns)[:columns]
    if widths and len(widths) != columns:
        widths = None
    return header, rows, aligns, widths


def pipe_table(header: list[str], rows: list[list[str]], aligns: list[str], widths: list[float] | None) -> list[str]:
    def cell(value: str) -> str:
        return value.replace("\r", "").replace("\n", " ").replace("|", "\\|")

    if widths:
        smallest = min(widths)
        counts = [max(3, round(width / smallest * 3)) for width in widths]
    else:
        counts = [3] * len(header)
    marks = []
    for align, count in zip(aligns, counts):
        colons = {"left": 1, "right": 1, "center": 2}.get(align, 0)
        dashes = "-" * max(1, count - colons)
        marks.append({"left": ":" + dashes, "right": dashes + ":", "center": ":" + dashes + ":"}.get(align, dashes))
    lines = ["| " + " | ".join(cell(value) for value in header) + " |", "|" + "|".join(marks) + "|"]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows]
    return lines


def expand(text: str, base_dir: Path) -> Extracted:
    """Every `.csv` block of `text` as a pipe table (all its rows: the block's `rows=`/`cols=` caps are not
    applied), with its `caption=` as the `: caption` line under the table."""
    blocks = find_csv_blocks(text)
    result = Extracted(text)
    if not blocks:
        result.report.append("no .csv blocks found")
        return result
    lines = text.split("\n")
    for position in range(len(blocks) - 1, -1, -1):
        block = blocks[position]
        label = f"block {position + 1}"
        try:
            header, rows, aligns, widths = block_table(block, base_dir)
        except TablesError as error:
            result.report.insert(0, f"SKIP  {label}: {error}")
            continue
        new = [block.indent + line if line else line for line in pipe_table(header, rows, aligns, widths)]
        caption = block.attributes.get("caption")
        if caption:
            new += ["", f"{block.indent}: {caption}"]
        elif block.identifier:
            new += ["", f"{block.indent}: {{#{block.identifier}}}"]
        lines[block.start:block.end] = new
        origin = block.attributes.get("file", "inline data")
        result.report.insert(0, f"EXPAND  {label}: {origin} -> {len(rows)} rows")
        result.changed += 1
    result.text = "\n".join(lines)
    return result
