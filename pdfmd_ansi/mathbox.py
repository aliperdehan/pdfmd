"""Stacked display math for the terminal renderer (level (b)): `$$..$$` drawn on several rows instead of one line of Unicode.

    \\frac{a+b}{c}            a fraction on three rows, the bar as wide as the wider part (and a cell on each side)
    \\sqrt{x+1}, \\sqrt[3]{x}   an overbar above the radicand, the radical sign on its baseline
    \\sum_{i=1}^{n}, \\int_a^b, \\prod, \\lim_{x \\to 0}   the limits above and below the operator

Everything else in the formula is set by `linear`, the one-line converter the renderer already has (Greek letters, operators,
sub- and superscripts as Unicode): a piece of the formula that is neither of the above is drawn as `linear` draws it. Anything
this module cannot place (an environment, a row break, a script on a fraction, an unbalanced brace, a piece `linear` cannot
read) makes `stacked` return None, and the caller keeps the linear form of the whole formula: never half of it stacked and half of
it wrong.

A box is a block of rows with a baseline; boxes are joined along their baselines. Pieces are (text, kind) like the linear form's.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple

from .text import text_width

Piece = Tuple[str, str]
Row = List[Piece]
Linear = Callable[[str, bool], Optional[List[List[Piece]]]]

TRIGGER = re.compile(r"\\(?:[dt]?frac|sqrt|sum|prod|coprod|int|iint|iiint|oint|lim|limsup|liminf|max|min|sup|inf)(?![A-Za-z])")
BIG_OPERATORS = {"sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬", "iiint": "∭", "oint": "∮"}
LIMIT_WORDS = {"lim": "lim", "limsup": "lim sup", "liminf": "lim inf", "max": "max", "min": "min", "sup": "sup", "inf": "inf"}
BAR = "─"
OVERBAR = "▁"                                   # the lower eighth block sits at the foot of its cell: above the radicand it joins the radical's top
RADICAL = "√"
OPENERS = "([{⟨|‖⌈⌊"
CLOSERS = ")]},.;:!?⟩|‖⌉⌋'’"


class Unsupported(Exception):
    """The formula has a shape this module does not draw."""


class Box:
    """Rows of pieces, the index of the row the text line runs on, and the cell width."""

    def __init__(self, rows: List[Row], baseline: int) -> None:
        self.rows = rows
        self.baseline = baseline
        self.width = max([sum(text_width(text) for text, _ in row) for row in rows] + [0])

    def row_width(self, row: Row) -> int:
        return sum(text_width(text) for text, _ in row)

    @property
    def above(self) -> int:
        return self.baseline

    @property
    def below(self) -> int:
        return len(self.rows) - self.baseline - 1

    def edge(self, last: bool) -> str:
        """The first or last visible character of the baseline row ('' if it has none)."""
        text = "".join(piece for piece, _ in self.rows[self.baseline])
        return (text[-1:] if last else text[:1]) if text else ""


def blank(width: int) -> Row:
    return [(" " * width, "")] if width else []


def centred(row: Row, width: int, own: int) -> Row:
    left = (width - own) // 2
    return [*blank(left), *row, *blank(width - own - left)]


# --- the TeX ------------------------------------------------------------------------------------------------------------

def group(source: str, start: int) -> Tuple[str, int]:
    """The argument at `start`: a {group} (its inside), or one token; and where it ends."""
    n = len(source)
    while start < n and source[start] in " \t\n":
        start += 1
    if start >= n:
        raise Unsupported("missing argument")
    if source[start] == "{":
        depth, i = 0, start
        while i < n:
            char = source[i]
            if char == "\\":
                i += 2
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return source[start + 1:i], i + 1
            i += 1
        raise Unsupported("unbalanced brace")
    if source[start] == "\\":
        match = re.compile(r"\\(?:[A-Za-z]+|.)").match(source, start)
        return match.group(0), match.end()
    return source[start], start + 1


def split(source: str) -> list:
    """The formula as text pieces and structures: ("text", tex), ("frac", num, den), ("sqrt", index, radicand),
    ("big", name, lower, upper). The arguments are TeX again, drawn by the same function."""
    if re.search(r"\\begin\b|\\end\b|\\\\|&", source):
        raise Unsupported("an environment or a row break")
    items: list = []
    text = ""
    i, n = 0, len(source)

    def flush() -> None:
        nonlocal text
        if text.strip():
            items.append(("text", text))
        text = ""

    while i < n:
        char = source[i]
        if char == "{":                                   # a plain group stays inside its text piece, braces and all
            inner, end = group(source, i)
            text += source[i:end]
            i = end
            continue
        if char != "\\":
            text += char
            i += 1
            continue
        found = re.compile(r"\\([A-Za-z]+)").match(source, i)
        if not found:
            text += source[i:i + 2]
            i += 2
            continue
        name = found.group(1)
        after = found.end()
        if name in ("frac", "dfrac", "tfrac"):
            flush()
            numerator, after = group(source, after)
            denominator, after = group(source, after)
            items.append(("frac", numerator, denominator))
            after = no_script(source, after)
        elif name == "sqrt":
            flush()
            index = None
            probe = after
            while probe < n and source[probe] in " \t":
                probe += 1
            if probe < n and source[probe] == "[":
                close = source.find("]", probe)
                if close < 0:
                    raise Unsupported("unbalanced bracket")
                index, after = source[probe + 1:close], close + 1
            radicand, after = group(source, after)
            items.append(("sqrt", index, radicand))
            after = no_script(source, after)
        elif name in BIG_OPERATORS or name in LIMIT_WORDS:
            lower = upper = None
            probe = after
            for _ in range(2):
                while probe < n and source[probe] in " \t\n":
                    probe += 1
                if probe < n and source[probe] in "_^":
                    which = source[probe]
                    argument, probe = group(source, probe + 1)
                    if which == "_" and lower is None:
                        lower = argument
                    elif which == "^" and upper is None:
                        upper = argument
                    else:
                        raise Unsupported("a limit given twice")
            if lower is None and upper is None:
                text += found.group(0)
                i = after
                continue
            if name in LIMIT_WORDS and upper is not None:
                raise Unsupported("a word operator with an upper limit")
            flush()
            items.append(("big", name, lower, upper))
            after = probe
        else:
            text += found.group(0)
        i = after
    flush()
    return items


def no_script(source: str, position: int) -> int:
    """A script on a fraction or a root is not drawn: the formula stays linear."""
    probe = position
    while probe < len(source) and source[probe] in " \t":
        probe += 1
    if probe < len(source) and source[probe] in "_^":
        raise Unsupported("a script on a fraction or a root")
    return position


# --- boxes --------------------------------------------------------------------------------------------------------------

def one_line(tex: str, linear: Linear) -> Box:
    shown = linear(tex.strip(), False) if tex.strip() else [[]]
    if shown is None or len(shown) != 1:
        raise Unsupported("the linear form is not one line")
    return Box([shown[0]], 0)


def build(source: str, linear: Linear) -> Box:
    """The TeX as one box."""
    boxes: List[Box] = []
    for item in split(source):
        kind = item[0]
        if kind == "text":
            boxes.append(one_line(item[1], linear))
        elif kind == "frac":
            boxes.append(fraction(build(item[1], linear), build(item[2], linear)))
        elif kind == "sqrt":
            boxes.append(root(build(item[2], linear), one_line(item[1], linear) if item[1] else None))
        else:
            boxes.append(operator(item[1], build(item[2], linear) if item[2] is not None else None,
                                  build(item[3], linear) if item[3] is not None else None))
    if not boxes:
        raise Unsupported("nothing to draw")
    return join(boxes)


def fraction(top: Box, bottom: Box) -> Box:
    width = max(top.width, bottom.width) + 2
    rows = [centred(row, width, top.row_width(row)) for row in top.rows]
    rows.append([(BAR * width, "")])
    rows += [centred(row, width, bottom.row_width(row)) for row in bottom.rows]
    return Box(rows, len(top.rows))


def root(inner: Box, index: Optional[Box]) -> Box:
    from .render import script
    mark = ""
    if index is not None:
        shown = "".join(text for text, _ in index.rows[0]).strip()
        mark = script(shown, True)
    lead = text_width(mark) + text_width(RADICAL)
    rows: List[Row] = [[*blank(lead), (OVERBAR * (inner.width + 1), "")]]
    for number, row in enumerate(inner.rows):
        if number == inner.baseline:
            rows.append([*([(mark, "")] if mark else []), (RADICAL, ""), (" ", ""), *row])
        else:
            rows.append([*blank(lead + 1), *row])
    return Box(rows, inner.baseline + 1)


def operator(name: str, lower: Optional[Box], upper: Optional[Box]) -> Box:
    symbol = BIG_OPERATORS.get(name) or LIMIT_WORDS[name]
    width = max(text_width(symbol), lower.width if lower else 0, upper.width if upper else 0)
    rows: List[Row] = []
    if upper:
        rows += [centred(row, width, upper.row_width(row)) for row in upper.rows]
    baseline = len(rows)
    rows.append(centred([(symbol, "")], width, text_width(symbol)))
    if lower:
        rows += [centred(row, width, lower.row_width(row)) for row in lower.rows]
    return Box(rows, baseline)


def join(boxes: List[Box]) -> Box:
    """The boxes side by side along their baselines, a space between a drawn structure and its neighbours."""
    if len(boxes) == 1:
        return boxes[0]
    above = max(box.above for box in boxes)
    below = max(box.below for box in boxes)
    rows: List[Row] = [[] for _ in range(above + 1 + below)]
    previous: Optional[Box] = None
    for box in boxes:
        if previous is not None and gap_between(previous, box):
            for row in rows:
                row.append((" ", ""))
        for number in range(len(rows)):
            inner = number - (above - box.baseline)
            if 0 <= inner < len(box.rows):
                row = box.rows[inner]
                rows[number] += row + blank(box.width - box.row_width(row))
            else:
                rows[number] += blank(box.width)
        previous = box
    return Box(rows, above)


def gap_between(left: Box, right: Box) -> bool:
    """A space between two boxes when one of them is more than one row (a fraction, a root, an operator with limits)."""
    if len(left.rows) == 1 and len(right.rows) == 1:
        return False
    last, first = left.edge(True), right.edge(False)
    if last == " " or first == " ":
        return False
    if len(left.rows) == 1 and (last in OPENERS or last == ""):
        return False
    if len(right.rows) == 1 and first and first in CLOSERS:
        return False
    return True


def stacked(tex: str, linear: Linear) -> Optional[List[Row]]:
    """`tex` (a display formula) as rows of (text, kind) pieces, fractions, roots and operators with limits drawn on several rows;
    None when there is nothing to stack or the formula holds anything this module does not draw."""
    if not TRIGGER.search(tex):
        return None
    try:
        box = build(tex, linear)
    except (Unsupported, IndexError, ValueError):
        return None
    if len(box.rows) < 2:
        return None
    rows = []
    for row in box.rows:
        merged: Row = []
        for text, kind in row:
            if merged and merged[-1][1] == kind:
                merged[-1] = (merged[-1][0] + text, kind)
            elif text:
                merged.append((text, kind))
        while merged and not merged[-1][0].strip():
            merged.pop()
        if merged:
            merged[-1] = (merged[-1][0].rstrip(), merged[-1][1])
        rows.append(merged)
    return rows
