"""Finding tables in Markdown text, and the `.csv` blocks that stand for them.

Lines are scanned outside the front matter, fenced code, HTML comments and indented code. A table is a span of lines
(`start`, `end`, the end excluded) of one of the four kinds Pandoc reads: pipe, simple, multiline and grid. Pipe
tables are read here, cell by cell, so that the author's own text is what comes out; the other three are handed to
Pandoc (see convert.py), which is also what says whether a table can be written as CSV at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
PIPE_RE = re.compile(r"(?<!\\)\|")
PIPE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
GRID_EDGE_RE = re.compile(r"^ {0,3}\+(?:[-=:]+\+)+\s*$")
COLUMN_DASHES_RE = re.compile(r"^\s*-+(?:\s+-+)+\s*$")
FULL_DASHES_RE = re.compile(r"^\s*-{3,}\s*$")
CAPTION_START_RE = re.compile(r"^(?:Table)?:[ \t]+(.*)$")
CAPTION_ATTRIBUTES_RE = re.compile(r"\s*\{([^{}]*)\}\s*$")
ATTRIBUTE_TEXT = r'(?:[^}"\n]|"(?:[^"\\\n]|\\.)*")*'            # inside {...}: a quoted value may hold braces
CSV_OPEN_RE = re.compile(r"^(\s*)(:{3,})\s*\{(" + ATTRIBUTE_TEXT + r"\.csv\b" + ATTRIBUTE_TEXT + r")\}\s*$")
DIV_CLOSE_RE = re.compile(r"^\s*:{3,}\s*$")
ATTRIBUTE_RE = re.compile(r"""([\w:.-]+)=(?:"((?:[^"\\]|\\.)*)"|'([^']*)'|([^\s"']+))""")
PANDOC_COLUMNS = 72                       # Pandoc's default line width: longer pipe-table lines make it use the dashes


@dataclass
class FoundTable:
    start: int                            # first line of the table
    end: int                              # line after its last line
    kind: str                             # pipe | simple | multiline | grid
    lines: list[str]
    caption: str | None = None            # the caption as written, trailing `{#tbl:id}` included
    span: tuple[int, int] = (0, 0)        # the lines to replace: the table and the caption paragraph with it
    header: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    aligns: list[str] = field(default_factory=list)        # left | center | right | default, one per column
    widths: list[float] | None = None                       # relative, only when the document chose them
    problem: str = ""                                       # why it cannot become CSV ("" when it can)

    @property
    def identifier(self) -> str:
        return caption_parts(self.caption)[1] if self.caption else ""


@dataclass
class CsvBlock:
    start: int
    end: int                              # line after the closing :::
    attributes: dict[str, str]
    identifier: str
    classes: list[str]
    data: str | None                      # the data written inside the block (None: it names a file)
    indent: str = ""


def caption_parts(caption: str | None) -> tuple[str, str, str]:
    """(text, identifier, the attribute text) of a caption: `Masses {#tbl:m .wide}` -> ("Masses", "tbl:m", ".wide")."""
    if not caption:
        return "", "", ""
    match = CAPTION_ATTRIBUTES_RE.search(caption)
    if not match:
        return caption.strip(), "", ""
    inner = match.group(1)
    found = re.search(r"(?:^|\s)#([^\s{}]+)", inner)
    return caption[:match.start()].strip(), found.group(1) if found else "", inner.strip()


def parse_attributes(text: str) -> tuple[str, list[str], dict[str, str]]:
    """The inside of `{#id .class key="value"}` as (identifier, classes, pairs)."""
    identifier, classes = "", []
    found = re.search(r"(?:^|\s)#([^\s=]+)", text)
    if found:
        identifier = found.group(1)
    classes = re.findall(r"(?:^|\s)\.([\w-]+)", ATTRIBUTE_RE.sub("", text))
    pairs = {}
    for match in ATTRIBUTE_RE.finditer(text):
        value = match.group(2) if match.group(2) is not None else match.group(3) if match.group(3) is not None \
            else match.group(4)
        pairs[match.group(1)] = re.sub(r"\\(.)", r"\1", value) if match.group(2) is not None else value
    return identifier, classes, pairs


def split_row(line: str) -> list[str]:
    """The cells of a pipe-table row: split at the pipes that are neither escaped nor inside a code span."""
    text = line.strip()
    cells: list[str] = []
    current: list[str] = []
    in_code = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            current.append(text[i:i + 2])
            i += 2
            continue
        if char == "`":
            run = len(text[i:]) - len(text[i:].lstrip("`"))
            if in_code == 0:
                in_code = run
            elif in_code == run:
                in_code = 0
            current.append("`" * run)
            i += run
            continue
        if char == "|" and not in_code:
            cells.append("".join(current))
            current = []
        else:
            current.append(char)
        i += 1
    cells.append("".join(current))
    if text.startswith("|"):
        cells = cells[1:]
    if text.endswith("|") and not text.endswith("\\|") and cells:
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


def unescape_cell(cell: str) -> str:
    return cell.replace("\\|", "|")


def separator_alignments(line: str) -> list[str]:
    out = []
    for cell in split_row(line):
        left, right = cell.startswith(":"), cell.endswith(":")
        out.append("center" if left and right else "left" if left else "right" if right else "default")
    return out


def separator_widths(line: str, lines: list[str]) -> list[float] | None:
    """The relative widths a pipe table's dashes ask for. Pandoc uses them only when some line is longer than its
    line width; otherwise the table has no widths of its own, and the dashes say nothing."""
    if not any(len(item.rstrip()) > PANDOC_COLUMNS for item in lines):
        return None
    counts = [len(cell) for cell in split_row(line)]
    if not counts or len(set(counts)) == 1:
        return None
    total = sum(counts)
    return [count / total for count in counts]


def content_lines(lines: list[str]):
    """Yield (index, line) for the lines that can start or hold a table: not front matter, fenced or indented
    code, nor HTML comments."""
    fence = None
    comment = False
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                start = index + 1
                break
    for index in range(start, len(lines)):
        line = lines[index]
        if comment:
            comment = "-->" not in line
            continue
        match = FENCE_RE.match(line)
        if fence:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= fence[1] and not match.group(2).strip():
                fence = None
            continue
        if match:
            fence = (match.group(1)[0], len(match.group(1)))
            continue
        if "<!--" in line and "-->" not in line.split("<!--", 1)[1]:
            comment = True
            continue
        yield index, line


def _caption(lines: list[str], start: int, end: int, floor: int = 0) -> tuple[str | None, tuple[int, int]]:
    """The caption of the table on lines [start, end): the paragraph after it (after one blank line), else the one
    before it, as `: text` or `Table: text`. And the span to replace."""
    count = len(lines)
    after = end + 1 if end < count and not lines[end].strip() else end
    if after > end and after < count:
        match = CAPTION_START_RE.match(lines[after])
        if match:
            last = after
            parts = [match.group(1).strip()]
            while last + 1 < count and lines[last + 1].strip():
                last += 1
                parts.append(lines[last].strip())
            return " ".join(parts), (start, last + 1)
    if start >= 2 and not lines[start - 1].strip() and lines[start - 2].strip():
        first = start - 2
        while first - 1 >= floor and lines[first - 1].strip():
            first -= 1
        match = CAPTION_START_RE.match(lines[first]) if first >= floor else None
        if match:
            parts = [match.group(1).strip()] + [item.strip() for item in lines[first + 1:start - 1]]
            return " ".join(parts), (first, end)
    return None, (start, end)


def _pipe_end(lines: list[str], index: int) -> int | None:
    if index + 1 >= len(lines):
        return None
    header, separator = lines[index], lines[index + 1]
    if not (PIPE_RE.search(header) and PIPE_RE.search(separator) and PIPE_SEPARATOR_RE.match(separator)):
        return None
    if len(split_row(header)) != len(split_row(separator)):
        return None
    end = index + 2
    while end < len(lines) and lines[end].strip() and PIPE_RE.search(lines[end]):
        end += 1
    return end


def _grid_end(lines: list[str], index: int) -> int | None:
    if not GRID_EDGE_RE.match(lines[index]):
        return None
    end = index
    while end < len(lines) and lines[end].strip() and lines[end].lstrip()[:1] in ("+", "|"):
        end += 1
    if end - index < 3 or not GRID_EDGE_RE.match(lines[end - 1]):
        return None
    return end


def _multiline_end(lines: list[str], index: int) -> int | None:
    if not FULL_DASHES_RE.match(lines[index]):
        return None
    probe = index + 1
    while probe < len(lines) and probe - index <= 6 and lines[probe].strip() and not COLUMN_DASHES_RE.match(lines[probe]):
        probe += 1
    if probe >= len(lines) or not COLUMN_DASHES_RE.match(lines[probe]):
        return None
    for end in range(probe + 1, len(lines)):
        if FULL_DASHES_RE.match(lines[end]):
            return end + 1
    return None


def _simple_end(lines: list[str], index: int) -> int | None:
    if index + 1 >= len(lines):
        return None
    if lines[index].strip() and not COLUMN_DASHES_RE.match(lines[index]) and not FULL_DASHES_RE.match(lines[index]) \
            and COLUMN_DASHES_RE.match(lines[index + 1]) and not PIPE_RE.search(lines[index]):
        end = index + 2
        while end < len(lines) and lines[end].strip():
            end += 1
        if end - index >= 3:
            return end
        return None
    return None


def find_tables(text: str) -> list[FoundTable]:
    """Every table of `text`, in order, with its caption. Pipe tables are read; the others carry only their lines."""
    lines = text.split("\n")
    found: list[FoundTable] = []
    skip_until = -1
    for index, line in content_lines(lines):
        if index < skip_until:
            continue
        if line.startswith(("    ", "\t")) and (index == 0 or not lines[index - 1].strip() or index - 1 < skip_until):
            continue
        for kind, ender in (("pipe", _pipe_end), ("grid", _grid_end), ("multiline", _multiline_end),
                            ("simple", _simple_end)):
            end = ender(lines, index)
            if end is None:
                continue
            table = FoundTable(index, end, kind, lines[index:end])
            table.caption, table.span = _caption(lines, index, end, max(skip_until, 0))
            if kind == "pipe":
                table.aligns = separator_alignments(lines[index + 1])
                table.widths = separator_widths(lines[index + 1], lines[index:end])
                table.header = [unescape_cell(cell) for cell in split_row(lines[index])]
                width = len(table.aligns)
                for row in lines[index + 2:end]:
                    cells = [unescape_cell(cell) for cell in split_row(row)]
                    table.rows.append((cells + [""] * width)[:width])
            found.append(table)
            skip_until = max(end, table.span[1])
            break
    return found


def find_csv_blocks(text: str) -> list[CsvBlock]:
    """The `::: {.csv ...}` divs of `text`, with their data when it is written inside."""
    lines = text.split("\n")
    blocks: list[CsvBlock] = []
    skip_until = -1
    for index, line in content_lines(lines):
        if index < skip_until:
            continue
        match = CSV_OPEN_RE.match(line)
        if not match:
            continue
        end = None
        fence = None
        for probe in range(index + 1, len(lines)):
            fence_match = FENCE_RE.match(lines[probe])
            if fence:
                if fence_match and fence_match.group(1)[0] == fence[0] and len(fence_match.group(1)) >= fence[1] \
                        and not fence_match.group(2).strip():
                    fence = None
                continue
            if fence_match:
                fence = (fence_match.group(1)[0], len(fence_match.group(1)))
                continue
            if DIV_CLOSE_RE.match(lines[probe]):
                end = probe
                break
        if end is None:
            continue
        identifier, classes, pairs = parse_attributes(match.group(3))
        body = lines[index + 1:end]
        data = None
        if "file" not in pairs and any(item.strip() for item in body):
            if body and FENCE_RE.match(body[0].strip()):
                body = body[1:-1] if len(body) > 1 and FENCE_RE.match(body[-1].strip()) else body[1:]
            data = "\n".join(body)
        blocks.append(CsvBlock(index, end + 1, pairs, identifier, classes, data, match.group(1)))
        skip_until = end + 1
    return blocks
