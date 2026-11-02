"""Text tables that Pandoc does not read as the table they are, repaired into pipe tables (3.31.47-48, entry 3el).

Four spellings, one result (a pipe table, with equal columns that pdfmd's own width filter balances):

* ASCII tables with no inner ``+`` (what chat models write for "a plain-text table"; 3.31.47)::

      +---------------------------------------------+
      | Model Name        | Origin                  |
      +---------------------------------------------+
      | Replacement Model | Africa;                 |
      |                   | ~200-100 ka             |
      +---------------------------------------------+

  Every border is one rule without a ``+`` at the column boundaries, the header has no ``+===+`` line under it, and the
  ``|`` bars drift by a character. The lazy forms work too (3.31.48): a border as short as ``+-+``, rows without outer
  bars (``1 | 2``), middle borders left out. Pandoc reads all of them as a one-column table.
* Box-drawing tables (``┌─┬─┐ │ ├─┼─┤ └─┴─┘``, double, rounded and heavy lines): what a terminal, Rich, pandas or tabulate prints.
* psql output: a header ``a | b``, a rule ``---+---``, rows, an optional ``(2 rows)``.
* MySQL console output: a real grid table (inner ``+``) with no header rule and three rules only. Pandoc reads its body
  lines as ONE row. (A body line with an empty first cell is a wrapped line of a real grid table: then nothing is touched.)

The repair is position-independent, because bars cannot be trusted to line up: a row is split on its bars. The lines
between two borders are one row (the lines of a wrapped cell are joined with a space); when the body has no border between
its lines, a line whose first cell is empty continues the row above and any other line starts a row. The first row is the
header (every row above a header rule, ``+===+`` or a ``═``/``━`` rule, when there is one). A valid grid table is never touched
(except the MySQL shape above). The caller decides what to do with the result: write a temporary copy, or only count.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# a border: one rule, no inner `+` (a real grid table has one at every column boundary); `=` marks the header rule
BORDER = re.compile(r"^ {0,3}\+([-=]+)\+[ \t]*$")
GRID_RULE = re.compile(r"^ {0,3}\+[-=]+(?:\+[-=]+)+\+[ \t]*$")           # a real grid rule (inner `+`): MySQL's shape only
GRID_ROW = re.compile(r"^ {0,3}\|")
PSQL_RULE = re.compile(r"^ {0,3}-+(?:\+-+)+[ \t]*$")
PSQL_FOOTER = re.compile(r"^\(\d+ rows?\)[ \t]*$")
BAR = re.compile(r"(?<!\\)\|")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
COMMENT_OPEN = "<!--"
COMMENT_CLOSE = "-->"
BOX_VERTICAL = "│┃║"
BOX_OTHER_VERTICAL = "╎╏┆┇┊┋"
BOX_HORIZONTAL = "─━═┄┅┈┉╌╍"
BOX_HEAVY = "═━"
LOOKS_LIKE_ONE = re.compile(r"^ {0,3}(?:\+[-=]|[─-╿]|-+\+)", re.MULTILINE)

KINDS = {
    "ascii": "an ASCII table without a `+` at its column boundaries",
    "box": "a box-drawing table",
    "psql": "a psql table",
    "mysql": "a console table whose body Pandoc reads as one row",
}


@dataclass
class Repair:
    """One table that was (or, in `note` mode, would be) rewritten."""
    line: int                 # 1-based line of its first line in the source
    columns: int
    rows: int                 # body rows
    problems: list[str]       # what had to be fitted (a row with another number of cells), for the warning
    kind: str = "ascii"       # a key of KINDS

    @property
    def what(self) -> str:
        return KINDS.get(self.kind, KINDS["ascii"])


Item = tuple[str, object]       # ("rule", heavy: bool) or ("row", cells: list[str])


def split_cells(line: str) -> list[str]:
    """The cells of one ``| a | b |`` (or ``a | b``) line: outer bars dropped, an escaped bar kept, every cell stripped."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in BAR.split(body)]


def psql_cells(line: str) -> list[str]:
    """The cells of a psql line, which has no outer bars: a last cell that is empty is a bar and then nothing."""
    return [cell.strip() for cell in BAR.split(line.strip())]


def split_box_cells(line: str) -> list[str]:
    """The cells of one box-drawing row: split on the vertical lines; a plain `|` inside a cell is escaped."""
    body = line.strip()
    parts = re.split("[" + BOX_VERTICAL + "]", body)
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [BAR.sub("\\|", part.strip()) for part in parts]


def is_box_rule(line: str) -> bool:
    text = line.strip()
    return (bool(text) and not line.startswith("    ") and not line.startswith("\t")
            and all("─" <= char <= "╿" and char not in BOX_VERTICAL + BOX_OTHER_VERTICAL for char in text)
            and any(char in BOX_HORIZONTAL for char in text))


def is_box_row(line: str) -> bool:
    text = line.strip()
    return bool(text) and not line.startswith("    ") and not line.startswith("\t") and text[0] in BOX_VERTICAL


def split_rows(lines: list[list[str]]) -> list[list[list[str]]]:
    """Lines with no border between them as rows: a line whose first cell is empty continues the row above."""
    rows: list[list[list[str]]] = []
    for cells in lines:
        if rows and not cells[0]:
            rows[-1].append(cells)
        else:
            rows.append([cells])
    return rows


def assemble(items: list[Item], first_line: int, kind: str) -> tuple[list[str], Repair] | None:
    """The pipe-table lines for the items of one table (rules and rows, the first and the last a rule), or None."""
    groups: list[list[list[str]]] = [[]]      # each group = the lines between two rules, each line = its cells
    header_end: int | None = None             # the index of the last group of the header, when a header rule says so
    for position, (what, value) in enumerate(items):
        if what == "rule":
            inner = 0 < position < len(items) - 1
            if inner and value and header_end is None and groups[-1]:
                header_end = len(groups) - 1
            if groups[-1]:
                groups.append([])
            continue
        groups[-1].append(value)              # type: ignore[arg-type]
    if not groups[-1]:
        groups.pop()
    if not groups or not any(len(cells) >= 2 for group in groups for cells in group):
        return None
    if header_end is not None:
        head, body = [line for group in groups[:header_end + 1] for line in group], groups[header_end + 1:]
        if len(body) == 1:
            body = [group for group in split_rows(body[0])]
    elif len(groups) == 1:
        split = split_rows(groups[0])
        head, body = split[0], split[1:]
    else:
        head, body = groups[0], groups[1:]
        if len(body) == 1:
            body = split_rows(body[0])
    width = max(len(cells) for cells in head)

    def merge(group: list[list[str]]) -> list[str]:
        cells = ["" for _ in range(width)]
        for line_cells in group:
            for index in range(min(width, len(line_cells))):
                if line_cells[index]:
                    cells[index] = (cells[index] + " " + line_cells[index]).strip()
        return cells

    problems: list[str] = []
    rows = [merge(head)]
    for number, group in enumerate(body, 1):
        widest = max(len(cells) for cells in group)
        if widest != width:
            problems.append(f"row {number} has {widest} cell{'s' if widest != 1 else ''}, the header {width}"
                            + (" (cut)" if widest > width else " (padded)"))
        rows.append(merge(group))
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join("---" for _ in range(width)) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return lines, Repair(first_line, width, len(rows) - 1, problems, kind)


def one_row_each(rows: list[list[str]]) -> list[Item]:
    """Items for lines that are one row each (psql, MySQL): a rule between every two, so none is taken for a wrapped cell."""
    items: list[Item] = [("rule", False)]
    for cells in rows:
        items += [("row", cells), ("rule", False)]
    return items


def mysql_rows(items: list[Item]) -> list[list[str]] | None:
    """The rows of a console table shaped rule, one header line, rule, two or more lines, rule; else None."""
    kinds = [what for what, _ in items]
    if kinds.count("rule") != 3 or kinds[0] != "rule" or kinds[-1] != "rule" or kinds[2] != "rule":
        return None
    if kinds[1] != "row" or any(value for what, value in items if what == "rule") or len(items) < 6:
        return None
    rows = [value for what, value in items if what == "row"]
    if any(not cells[0] for cells in rows[1:]):        # an empty first cell: the wrapped line of a real grid table's row
        return None
    return rows                                         # type: ignore[return-value]


def repair_ascii_tables(text: str) -> tuple[str, list[Repair]]:
    """``text`` with every table of the kinds in the module docstring turned into a pipe table, and one Repair for
    each. Not inside code (fenced or indented), HTML comments, YAML front matter or raw blocks."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    if not LOOKS_LIKE_ONE.search(text):
        return text, []
    out: list[str] = []
    repairs: list[Repair] = []
    index = 0
    fence: str | None = None
    in_comment = False
    # front matter: a `---` on the first line up to the next `---` / `...`
    if lines and lines[0].rstrip("\r") == "---":
        for closing in range(1, len(lines)):
            if lines[closing].rstrip("\r") in ("---", "..."):
                out.extend(lines[:closing + 1])
                index = closing + 1
                break

    def put(table: list[str], repair: Repair, end: int) -> int:
        if out and out[-1].strip():
            out.append("")
        out.extend(table)
        if end < len(lines) and lines[end].strip():
            out.append("")
        repairs.append(repair)
        return end

    while index < len(lines):
        line = lines[index]
        bare = line.rstrip("\r")
        if fence is not None:
            if bare.strip().startswith(fence[0] * len(fence)) and not bare.strip().strip(fence[0]):
                fence = None
            out.append(line)
            index += 1
            continue
        if in_comment:
            if COMMENT_CLOSE in bare:
                in_comment = False
            out.append(line)
            index += 1
            continue
        opening = FENCE.match(bare)
        if opening:
            fence = opening.group(1)
            out.append(line)
            index += 1
            continue
        if COMMENT_OPEN in bare and COMMENT_CLOSE not in bare.split(COMMENT_OPEN, 1)[1]:
            in_comment = True
            out.append(line)
            index += 1
            continue
        indented_code = bare.startswith("    ") or bare.startswith("\t")
        built = None
        end = index
        if indented_code:
            pass
        elif BORDER.match(bare):                                       # ASCII, the lazy forms included
            end = index
            while end < len(lines) and (BORDER.match(lines[end].rstrip("\r")) or BAR.search(lines[end])):
                end += 1
            while end > index and not BORDER.match(lines[end - 1].rstrip("\r")):     # it must close with a border
                end -= 1
            items: list[Item] = []
            for item in lines[index:end]:
                item = item.rstrip("\r")
                found = BORDER.match(item)
                items.append(("rule", "=" in found.group(1)) if found else ("row", split_cells(item)))
            built = assemble(items, index + 1, "ascii") if end - index >= 3 else None
        elif GRID_RULE.match(bare):                                    # MySQL's console table
            end = index
            while end < len(lines) and (GRID_RULE.match(lines[end].rstrip("\r")) or GRID_ROW.match(lines[end])):
                end += 1
            while end > index and not GRID_RULE.match(lines[end - 1].rstrip("\r")):
                end -= 1
            items = []
            for item in lines[index:end]:
                item = item.rstrip("\r")
                items.append(("rule", "=" in item) if GRID_RULE.match(item) else ("row", split_cells(item)))
            rows = mysql_rows(items)
            built = assemble(one_row_each(rows), index + 1, "mysql") if rows else None
            if built is None:                       # a real grid table: all of it stays, not to be started again at its second rule
                skip = max(end, index + 1)
                out.extend(lines[index:skip])
                index = skip
                continue
        elif is_box_rule(bare) or is_box_row(bare):                    # box-drawing
            end = index
            while end < len(lines) and (is_box_rule(lines[end].rstrip("\r")) or is_box_row(lines[end].rstrip("\r"))):
                end += 1
            items = []
            for item in lines[index:end]:
                item = item.rstrip("\r")
                items.append(("rule", any(char in BOX_HEAVY for char in item)) if is_box_rule(item)
                             else ("row", split_box_cells(item)))
            built = (assemble(items, index + 1, "box")
                     if items and items[0][0] == "rule" and items[-1][0] == "rule" else None)
        elif PSQL_RULE.match(bare) and out and out[-1].strip() and not out[-1].lstrip().startswith("|"):
            plus = bare.count("+")
            if len(BAR.findall(out[-1])) == plus:
                end = index + 1
                body: list[list[str]] = []
                while end < len(lines) and lines[end].strip() and len(BAR.findall(lines[end])) == plus:
                    body.append(psql_cells(lines[end]))
                    end += 1
                if body:
                    built = assemble(one_row_each([psql_cells(out[-1]), *body]), index, "psql")
                    if built is not None:
                        if end < len(lines) and PSQL_FOOTER.match(lines[end].strip()):
                            end += 1                                   # `(2 rows)` goes with the table
                        out.pop()                                      # the header line, now part of the table
        if built is not None:
            table, repair = built
            index = put(table, repair, end)
            continue
        out.append(line)
        index += 1
    if not repairs:
        return text, []
    return newline.join(out), repairs
