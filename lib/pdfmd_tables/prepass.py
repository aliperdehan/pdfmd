"""Read and normalise Markdown pipe separators before they reach a reader."""

from __future__ import annotations

import re
from math import gcd

from pdfmd_base import core

from .scan import (CSV_OPEN_RE, DIV_CLOSE_RE, GRID_EDGE_RE, PIPE_SEPARATOR_RE, _caption, _grid_end, caption_parts,
                   parse_attributes, split_row)


DASHES = str.maketrans({"–": "--", "—": "---", "−": "-", "‒": "-", "‐": "-", "‑": "-", "=": "-", "+": "|"})
COLON_SPACE = re.compile(r":[ \t]+(?=-)|(?<=-)[ \t]+(?=:)")
SUSPECT = re.compile(r"(?m)^[ \t|+:=–—−‒‐‑-]*[-=–—−‒‐‑][ \t|+:=–—−‒‐‑-]*\r?$")
LITERAL = re.compile(
    r"(?ms)^ *\$\$.*?(?:\$\$|\Z)|^ *\\\[.*?(?:\\\]|\Z)"
    r"|^ *\\begin\{(?P<env>[\w*]+)\}.*?(?:\\end\{(?P=env)\}|\Z)"
    r"|(?i:^ *<(?P<tag>pre|script|style|textarea|xmp|iframe)\b.*?(?:</(?P=tag)\s*>|\Z))"
)
FRONT = re.compile(r"\A\ufeff?(?:[ \t]*\r?\n)*---[ \t]*\r?\n.*?^(?:---|\.\.\.)[ \t]*\r?$", re.M | re.S)
REPAIR_MODES = ("pandoc", "header", "widest")
MARKDOWN_READERS = frozenset({"markdown", "markdown_strict", "markdown_mmd", "markdown_phpextra", "gfm",
                              "commonmark_x", "commonmark"})


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
    if "|" not in line:
        return False
    bare = line.strip()
    return bool(bare and (bare.startswith("|") or (bare.endswith("|") and not bare.endswith(r"\|"))
                          or len(split_row(bare)) > 1))


def normal_separator(line: str) -> str | None:
    """The same separator with conventional dashes, dividers and alignment marks."""
    if "|" not in line and "+" not in line:
        return None
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


def pipe_blocks(lines: list[str], grids: set[int]):
    """Spans that have a pipe separator or at least two consecutive pipe rows."""
    start = 0
    while start < len(lines):
        if start in grids:
            start += 1
            continue
        if normal_separator(lines[start]) is not None:
            separator = start
        elif pipe_row(lines[start]):
            separator = start + 1 if start + 1 < len(lines) and start + 1 not in grids \
                and normal_separator(lines[start + 1]) is not None else None
        else:
            start += 1
            continue
        end = start + 1 if separator is None else separator + 1
        while end < len(lines) and end not in grids and pipe_row(lines[end]):
            end += 1
        if separator is not None or end > start + 1:
            yield start, end, separator
        start = end


def reader_family(reader: str | None) -> str:
    return re.split(r"[+-]", reader or "markdown", maxsplit=1)[0].casefold()


def unparsed_tables(text: str, reader: str | None) -> list[tuple[int, str]]:
    """Likely pipe or grid tables that the selected reader cannot read as written."""
    family = reader_family(reader)
    if family not in MARKDOWN_READERS:
        return []
    if "|" not in text and "+" not in text:
        return []
    lines = visible_lines(text)
    grids = grid_lines(lines)
    reasons = []
    for start, _, separator in pipe_blocks(lines, grids):
        if separator is None:
            reasons.append((start + 1, "no separator row"))
            continue
        if separator == start:
            reasons.append((start + 1, "no header row"))
            continue
        original = lines[separator]
        fixed = normal_separator(original)
        header_count, separator_count = len(split_row(lines[start])), len(split_row(fixed))
        if header_count != separator_count:
            reason = f"header {header_count} / separator {separator_count}"
        elif "+" in original and (family != "markdown" or original.strip().startswith("+") or ":" in original):
            reason = "+ separator"
        elif original.replace("+", "|") != fixed:
            reason = "non-standard separator spelling"
        elif reader and "-pipe_tables" in reader:
            reason = f"{family} has pipe tables disabled"
        else:
            continue
        reasons.append((separator + 1, reason))
    if family == "gfm":
        for index in sorted(grids):
            if index - 1 not in grids and _grid_end(lines, index) is not None:
                reasons.append((index + 1, "gfm does not read grid tables"))
    return [(line, f"looks like a table but was not read as one ({reason})") for line, reason in sorted(reasons)]


def table_colons(path, metadata_files) -> str:
    value = core.first_pdfmd_option(path, list(metadata_files), "table-colons")
    mode = "ignore" if value is None else str(value).strip().casefold()
    if mode not in ("ignore", "count"):
        raise SystemExit(f"pdfmd-options table-colons: {value!r} is not one of ignore, count")
    return mode


def table_repair(path, metadata_files) -> str:
    value = core.TABLE_REPAIR_CLI or core.first_pdfmd_option(path, list(metadata_files), "table-repair")
    mode = "pandoc" if value is None else str(value).strip().casefold()
    if mode not in REPAIR_MODES:
        raise SystemExit(f"pdfmd-options table-repair: {value!r} is not one of {', '.join(REPAIR_MODES)}")
    return mode


def caption_options(lines: list[str], start: int, end: int) -> dict[str, str]:
    caption, _ = _caption(lines, start, end)
    return parse_attributes(caption_parts(caption)[2])[2]


def ignore_colons(separator: str) -> str:
    """Encode the dash-only ratios in the cell lengths Pandoc counts, including colons."""
    cells = list(re.finditer(r":?-+:?", separator))
    dashes = [cell[0].count("-") for cell in cells]
    colons = [cell[0].count(":") for cell in cells]
    if all(mark * dashes[0] == colons[0] * count for count, mark in zip(dashes, colons)):
        return separator
    divisor = gcd(*dashes)
    ratios = [count // divisor for count in dashes]
    scale = max(mark // ratio + 1 for ratio, mark in zip(ratios, colons))
    replacements = []
    for cell, ratio, marks in zip(cells, ratios, colons):
        count = scale * ratio - marks
        replacements.append(re.sub(r"-+", "-" * count, cell[0]))
    encoded = iter(replacements)
    return re.sub(r":?-+:?", lambda _: next(encoded), separator)


def normalise_separators(text: str, *, colons: str | None = None) -> tuple[str, list[int]]:
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
        if not visible[index].strip() or not (fixed := normal_separator(lines[index])):
            continue
        if fixed != lines[index]:
            changed.append(index + 1)
        if colons is not None and ":" in fixed:
            end = index + 1
            while end < len(lines) and pipe_row(visible[end]):
                end += 1
            if caption_options(lines, index - 1, end).get("table-colons", colons).strip().casefold() == "ignore":
                fixed = ignore_colons(fixed)
        lines[index] = fixed
    return "\n".join(lines), changed


def render_row(line: str, cells: list[str], separator: bool) -> str:
    indent = re.match(r"[ \t]*", line)[0]
    ending = "\r" if line.endswith("\r") else ""
    inner = "|".join(cells) if separator else " " + " | ".join(cells) + " "
    return f"{indent}|{inner}|{ending}"


def repair_pipe_tables(text: str, mode: str) -> tuple[str, list[tuple[int, str]]]:
    """Fit pipe rows to the header or widest row. In pandoc mode leave the bytes as received."""
    if "|" not in text:
        return text, []
    visible = visible_lines(text)
    lines = text.split("\n")
    fixed = lines.copy()
    notices = []
    for start, end, separator in pipe_blocks(visible, grid_lines(visible)):
        rows = {index: split_row(lines[index]) for index in range(start, end)}
        if mode == "pandoc":
            if separator == start + 1 and len(rows[start]) == len(rows[separator]):
                count = len(rows[start])
                for index in range(separator + 1, end):
                    found = len(rows[index])
                    if found != count:
                        action = "pad" if found < count else "cut"
                        notices.append((index + 1, f"Pandoc can {action} a row with {found} cells to {count}"))
            continue
        if separator is None and len({len(cells) for cells in rows.values()}) != 1:
            continue
        if separator == start and end == start + 1:
            continue
        count = len(rows[start]) if mode == "header" else max(map(len, rows.values()))
        for index, cells in rows.items():
            is_separator = index == separator
            found = len(cells)
            bare = lines[index].strip()
            if found != count:
                action = "padded" if found < count else "cut"
                notices.append((index + 1, f"{action} the {'separator' if is_separator else 'row'} from {found} cells to {count}"))
            elif not bare.startswith("|") or not bare.endswith("|") or bare.endswith(r"\|"):
                notices.append((index + 1, "normalised the row's outer pipes"))
            else:
                continue
            fill = "---" if is_separator else ""
            fixed[index] = render_row(lines[index], cells[:count] + [fill] * max(0, count - found), is_separator)
        if separator is None:
            fixed[start] += "\n" + render_row(lines[start], ["---"] * count, True)
            notices.append((start + 1, "inserted a separator below the header"))
        elif separator == start:
            fixed[start] = render_row(lines[start], [""] * count, False) + "\n" + fixed[start]
            notices.append((start + 1, "inserted an empty header above the separator"))
    return "\n".join(fixed), sorted(notices, key=lambda notice: notice[0])


def table_source(text: str, label: str, *, colons: str = "ignore", reader: str | None = None,
                 repair: str = "pandoc") -> str:
    if reader_family(reader) not in MARKDOWN_READERS or "|" not in text:
        return text
    for line, reason in unparsed_tables(text, reader):
        print(f"WARN  table-unparsed: {label}, line {line}: {reason}")
    fixed, changes = normalise_separators(text)
    for line in changes:
        print(f"WARN  table-separator: {label}, line {line}: normalised the pipe-table separator")
    fixed, notices = repair_pipe_tables(fixed, repair)
    for line, reason in notices:
        print(f"WARN  table-repair: {label}, line {line}: {reason}")
    if ":" in fixed:
        fixed, _ = normalise_separators(fixed, colons=colons)
    return fixed
