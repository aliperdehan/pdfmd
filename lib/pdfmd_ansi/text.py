"""Display widths, styled runs and word wrapping for the terminal renderer.

A line is a list of `Run`s (text + a tuple of style tokens). Widths are counted in terminal cells (a wide character is
two, a combining mark none), never in characters, and escape codes are only added at the very end (`emit`), so the
wrapping and the table grid never have to look past them.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import List, NamedTuple, Optional, Tuple

INF = 10 ** 6                                   # "no wrapping": the natural width of a piece of text


class Run(NamedTuple):
    text: str
    style: Tuple[str, ...] = ()


Line = List[Run]

SGR = {"b": "1", "i": "3", "u": "4", "s": "9", "dim": "2", "code": "38;5;173", "link": "38;5;75;4"}
BIDI = dict.fromkeys(list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)))


def clean(text: str) -> str:
    """Text from a document made safe for a terminal: no control character (an ESC would start a sequence), no bidi override."""
    if text.isprintable():
        return text
    return "".join(char for char in text.translate(BIDI) if char in "\n\t" or unicodedata.category(char) != "Cc")


@lru_cache(maxsize=8192)
def char_width(char: str) -> int:
    code = ord(char)
    if code < 0x300:
        return 0 if code < 0x20 or 0x7F <= code < 0xA0 else 1
    if unicodedata.combining(char) or unicodedata.category(char) in ("Mn", "Me", "Cf") or code == 0xFE0F:
        return 0
    if unicodedata.east_asian_width(char) in ("W", "F") or 0x1F300 <= code <= 0x1FAFF:
        return 2
    return 1


def text_width(text: str) -> int:
    return sum(char_width(char) for char in text)


def line_width(line: Line) -> int:
    return sum(text_width(run.text) for run in line)


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m|\x1b\]8;;[^\x1b]*\x1b\\")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def visible_width(text: str) -> int:
    """The width of a string that may carry escape codes."""
    return text_width(strip_ansi(text))


def with_style(line: Line, *tokens: str) -> Line:
    return [Run(run.text, tuple(dict.fromkeys((*run.style, *tokens)))) for run in line]


def pad(line: Line, width: int, align: str = "l") -> Line:
    """The line padded with spaces to `width` cells ('l' left, 'r' right, 'c' centred)."""
    gap = max(0, width - line_width(line))
    if not gap:
        return line
    if align == "r":
        return [Run(" " * gap), *line]
    if align == "c":
        return [Run(" " * (gap // 2)), *line, Run(" " * (gap - gap // 2))]
    return [*line, Run(" " * gap)]


# --- wrapping -----------------------------------------------------------------------------------------------------

SPLIT_RE = re.compile(r"( +|\n)")


def _items(runs: List[Run]) -> list:
    items: list = []
    word: List[Run] = []
    for run in runs:
        for part in SPLIT_RE.split(run.text):
            if not part:
                continue
            if part == "\n" or part[0] == " ":
                if word:
                    items.append(("w", word))
                    word = []
                items.append(("n", None) if part == "\n" else ("s", Run(part, run.style)))
            else:
                word.append(Run(part, run.style))
    if word:
        items.append(("w", word))
    return items


def _chunks(word: List[Run], width: int, first: int) -> List[List[Run]]:
    """A word longer than a line, cut by display width: the first piece holds `first` cells, the others `width`."""
    pieces: List[List[Run]] = [[]]
    room = max(1, first)
    for run in word:
        buffer = ""
        for char in run.text:
            size = char_width(char)
            if size > room and (pieces[-1] or buffer):
                if buffer:
                    pieces[-1].append(Run(buffer, run.style))
                    buffer = ""
                pieces.append([])
                room = width
            buffer += char
            room -= size
        if buffer:
            pieces[-1].append(Run(buffer, run.style))
    return pieces


def wrap(runs: List[Run], width: Optional[int]) -> List[Line]:
    """Greedy word wrap of styled runs into lines of at most `width` cells; "\\n" in a run is a hard break."""
    width = INF if width is None else max(1, width)
    lines: List[Line] = []
    current: Line = []
    used = 0
    space: Optional[Run] = None
    for kind, value in _items(runs):
        if kind == "n":
            lines.append(current)
            current, used, space = [], 0, None
        elif kind == "s":
            space = value if current else None
        else:
            size = sum(text_width(run.text) for run in value)
            gap = text_width(space.text) if space else 0
            if current and used + gap + size > width:
                lines.append(current)
                current, used, space, gap = [], 0, None, 0
            if size > width:
                pieces = _chunks(value, width, width - used - gap if current else width)
                if current and space:
                    current.append(space)
                current.extend(pieces[0])
                for piece in pieces[1:]:
                    lines.append(current)
                    current = list(piece)
                used = line_width(current)
                space = None
                continue
            if current and space:
                current.append(space)
                used += gap
            current.extend(value)
            used += size
            space = None
    lines.append(current)
    return lines


# --- output -------------------------------------------------------------------------------------------------------

def _merge(line: Line) -> Line:
    merged: Line = []
    for run in line:
        if not run.text:
            continue
        if merged and merged[-1].style == run.style:
            merged[-1] = Run(merged[-1].text + run.text, run.style)
        else:
            merged.append(run)
    return merged


def emit(line: Line, color: bool = True, hyperlinks: bool = False) -> str:
    """One line as a string. Every styled run is opened and closed on its own (`ESC[0m`), so nothing leaks to the next."""
    pieces: List[str] = []
    for run in _merge(line):
        if not color or not run.style:
            pieces.append(run.text)
            continue
        codes = [SGR[token] if token in SGR else token[3:] for token in run.style
                 if token in SGR or token.startswith("fg:")]
        urls = [token[2:] for token in run.style if token.startswith("a:")]
        opening = f"\x1b[{';'.join(codes)}m" if codes else ""
        closing = "\x1b[0m" if codes else ""
        if urls and hyperlinks:
            opening = f"\x1b]8;;{urls[0]}\x1b\\" + opening
            closing += "\x1b]8;;\x1b\\"
        pieces.append(f"{opening}{run.text}{closing}")
    return "".join(pieces)
