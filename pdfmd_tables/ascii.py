"""ASCII "grid" tables that are not Pandoc grid tables, repaired into pipe tables (3.31.47, entry 3el).

Chat models (NotebookLM, among others) write a table like this when asked for plain text::

    +---------------------------------------------+
    | Model Name        | Origin                  |
    +---------------------------------------------+
    | Replacement Model | Africa;                 |
    |                   | ~200-100 ka             |
    +---------------------------------------------+

Every border is one rule without a ``+`` at the column boundaries, the header has no ``+===+`` line under it, and the
``|`` bars drift by a character here and there. Pandoc reads that as a one-column table with no header, a ``|`` in every
cell. A valid grid table (``+---+---+``) is a different thing and is never touched.

The repair is position-independent, because the bars cannot be trusted to line up: a row is split on ``|``, the lines
between two borders are one row (the lines of a wrapped cell are joined with a space), the first row is the header (or
every row above a ``+===+`` line). The result is a pipe table. Nothing is read from the file but its text, and the
caller decides what to do with it (write a temporary copy, or only count the tables).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# a border: one rule, no inner `+` (a real grid table has one at every column boundary); `=` marks the header rule
BORDER = re.compile(r"^ {0,3}\+([-=]{3,})\+[ \t]*$")
ROW = re.compile(r"^ {0,3}\|")
BAR = re.compile(r"(?<!\\)\|")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
COMMENT_OPEN = "<!--"
COMMENT_CLOSE = "-->"


@dataclass
class Repair:
    """One table that was (or, in `note` mode, would be) rewritten."""
    line: int                 # 1-based line of the first border in the source
    columns: int
    rows: int                 # body rows
    problems: list[str]       # what had to be fitted (a row with another number of cells), for the warning


def split_cells(line: str) -> list[str]:
    """The cells of one ``| a | b |`` line: outer bars dropped, an escaped bar kept, every cell stripped."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in BAR.split(body)]


def build_table(block: list[str], first_line: int) -> tuple[list[str], Repair] | None:
    """The pipe-table lines for one block of border and row lines, or None when it is no such table."""
    groups: list[list[list[str]]] = [[]]      # each group = the lines of one row, each line = its cells
    header_rule: int | None = None            # the group index a `+===+` line closes
    borders = 0
    for line in block:
        match = BORDER.match(line)
        if match:
            borders += 1
            if "=" in match.group(1) and header_rule is None:
                header_rule = len(groups) - 1 if groups[-1] else len(groups) - 2
            if groups[-1]:
                groups.append([])
            continue
        groups[-1].append(split_cells(line))
    if not groups[-1]:
        groups.pop()
    # a block must look like a table: a closing border, and one line that really has two cells or more
    if borders < 2 or not groups or not any(len(cells) >= 2 for group in groups for cells in group):
        return None
    if header_rule is not None and header_rule >= 0:
        head_groups, body_groups = groups[:header_rule + 1], groups[header_rule + 1:]
    else:
        head_groups, body_groups = groups[:1], groups[1:]

    def merge(group: list[list[str]], width: int) -> list[str]:
        cells = ["" for _ in range(width)]
        for line_cells in group:
            for index in range(min(width, len(line_cells))):
                if line_cells[index]:
                    cells[index] = (cells[index] + " " + line_cells[index]).strip()
        return cells

    head_lines = [cells for group in head_groups for cells in group]
    width = max(len(cells) for cells in head_lines)
    problems: list[str] = []
    rows = [merge([cells for group in head_groups for cells in group], width)]
    for number, group in enumerate(body_groups, 1):
        widest = max(len(cells) for cells in group)
        if widest != width:
            problems.append(f"row {number} has {widest} cell{'s' if widest != 1 else ''}, the header {width}"
                            + (" (cut)" if widest > width else " (padded)"))
        rows.append(merge(group, width))

    def pipe(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    lines = [pipe(rows[0]), "| " + " | ".join("---" for _ in range(width)) + " |"]
    lines += [pipe(row) for row in rows[1:]]
    return lines, Repair(first_line, width, len(rows) - 1, problems)


def repair_ascii_tables(text: str) -> tuple[str, list[Repair]]:
    """``text`` with every ASCII table of the kind in the module docstring turned into a pipe table, and one Repair
    for each. Not inside code (fenced or indented), HTML comments, YAML front matter or raw blocks."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    if not any(BORDER.match(line.rstrip("\r")) for line in lines):
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
        previous_blank = not out or not out[-1].strip()
        indented_code = bare.startswith("    ") or bare.startswith("\t")
        if BORDER.match(bare) and not indented_code:
            end = index
            while end < len(lines):
                candidate = lines[end].rstrip("\r")
                if BORDER.match(candidate) or ROW.match(candidate):
                    end += 1
                else:
                    break
            built = build_table([item.rstrip("\r") for item in lines[index:end]], index + 1)
            if built is not None:
                table, repair = built
                if not previous_blank:
                    out.append("")
                out.extend(table)
                if end < len(lines) and lines[end].strip():
                    out.append("")
                repairs.append(repair)
                index = end
                continue
        out.append(line)
        index += 1
    if not repairs:
        return text, []
    return newline.join(out), repairs
