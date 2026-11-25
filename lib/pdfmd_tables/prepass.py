"""Read and normalise Markdown pipe separators before they reach a reader."""

from __future__ import annotations

import re

from .scan import CSV_OPEN_RE, DIV_CLOSE_RE, GRID_EDGE_RE, PIPE_SEPARATOR_RE, split_row


DASHES = str.maketrans({"–": "--", "—": "---", "−": "-", "‒": "-", "‐": "-", "‑": "-", "=": "-", "+": "|"})
COLON_SPACE = re.compile(r":[ \t]+(?=-)|(?<=-)[ \t]+(?=:)")
SUSPECT = re.compile(r"(?m)^[ \t|+:=–—−‒‐‑-]*[-=–—−‒‐‑][ \t|+:=–—−‒‐‑-]*\r?$")
LITERAL = re.compile(
    r"(?ms)^ *\$\$.*?(?:\$\$|\Z)|^ *\\\[.*?(?:\\\]|\Z)"
    r"|^ *\\begin\{(?P<env>[\w*]+)\}.*?(?:\\end\{(?P=env)\}|\Z)"
    r"|(?i:^ *<(?P<tag>pre|script|style|textarea|xmp|iframe)\b.*?(?:</(?P=tag)\s*>|\Z))"
)
FRONT = re.compile(r"\A\ufeff?(?:[ \t]*\r?\n)*---[ \t]*\r?\n.*?^(?:---|\.\.\.)[ \t]*\r?$", re.M | re.S)


def visible_lines(text: str) -> list[str]:
    """Keep line indices while blanking the places whose text is literal or hidden."""
    from pdfmd_check.lint import blank_matches, mask_code

    prose = blank_matches(FRONT, text)
    prose, _ = mask_code(prose)
    lines = blank_matches(LITERAL, prose).split("\n")
    csv_fence = 0
    for index, line in enumerate(lines):
        if csv_fence:
            if DIV_CLOSE_RE.fullmatch(line) and len(line.strip()) >= csv_fence:
                csv_fence = 0
            lines[index] = ""
        elif match := CSV_OPEN_RE.fullmatch(line):
            csv_fence = len(match[2])
            lines[index] = ""
    return lines


def pipe_row(line: str) -> bool:
    bare = line.strip()
    return bool(bare and (bare.startswith("|") or (bare.endswith("|") and not bare.endswith(r"\|"))
                          or len(split_row(bare)) > 1))


def normal_separator(line: str) -> str | None:
    """The same separator with conventional dashes, dividers and alignment marks."""
    line = COLON_SPACE.sub(lambda match: match[0].strip(), line.translate(DASHES))
    if "|" in line and PIPE_SEPARATOR_RE.fullmatch(line):
        return line
    return None


def grid_lines(lines: list[str]) -> set[int]:
    """Do not mistake any part of a grid table for a pipe table."""
    found = set()
    for index, line in enumerate(lines):
        if index in found or not GRID_EDGE_RE.fullmatch(line) or (index and pipe_row(lines[index - 1])):
            continue
        end = index + 1
        while end < len(lines) and (pipe_row(lines[end]) or GRID_EDGE_RE.fullmatch(lines[end])):
            end += 1
        found.update(range(index, end))
    return found


def normalise_separators(text: str) -> tuple[str, list[int]]:
    """Return the prepared text and the one-based lines of changed separators."""
    if not SUSPECT.search(text):
        return text, []
    visible = visible_lines(text)
    grids = grid_lines(visible)
    lines = text.split("\n")
    changed = []
    for index in range(1, len(lines)):
        if index in grids or not pipe_row(visible[index - 1]) or normal_separator(visible[index - 1]) is not None:
            continue
        if not visible[index].strip() or not (fixed := normal_separator(lines[index])) or fixed == lines[index]:
            continue
        lines[index] = fixed
        changed.append(index + 1)
    return "\n".join(lines), changed


def table_source(text: str, label: str) -> str:
    fixed, changes = normalise_separators(text)
    for line in changes:
        print(f"WARN  table-separator: {label}, line {line}: normalised the pipe-table separator")
    return fixed
