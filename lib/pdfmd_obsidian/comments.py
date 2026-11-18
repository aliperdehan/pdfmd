"""``%%comments%%``: text Obsidian's reading view hides (v3.32.20).

A comment opens at one ``%%`` and closes at the next, on the same line or many lines later. Fenced and indented code, inline code, math,
front matter and HTML comments are not looked into (a ``%%`` there is the text it looks like). A ``%%`` with no closing mate
hides the rest of the note, as in Obsidian (checked in its reading view, v3.32.21), and its line is reported: it is usually a typo.
``unclosed="keep"`` keeps it as text instead (still reported).

``hide_comments`` returns the note without its comments (what Obsidian shows), or, with ``show``, with each comment turned into
an HTML comment, which pdfmd's ``show-comments`` then draws as a Comment box and every writer otherwise drops.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# What a `%%` is not looked for in, leftmost match first: front matter, fenced code (an unclosed fence runs to the end, as in
# CommonMark), an HTML comment, display math, inline code, inline math.
_PROTECTED = (
    r"(?P<front>\A(?:[ \t]*\r?\n)*---[ \t]*\r?\n(?=[ \t]*\S).*?^(?:---|\.\.\.)[ \t]*\r?$)"
    r"|(?P<fence>^[ \t]{0,3}(?P<mark>`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]{0,3}(?P=mark)[`~]*[ \t]*\r?$|\Z))"
    r"|(?P<html><!--.*?-->)"
    r"|(?P<display>\$\$.*?\$\$)"
    r"|(?P<code>(?<!`)(?P<ticks>`+)(?!`)(?:(?!\n[ \t]*\r?\n).)*?(?<!`)(?P=ticks)(?!`))"
    r"|(?P<math>(?<![\\$])\$(?!\s)[^$\n]*?(?<!\s)\$(?!\d))"
)
_SCAN = re.compile(_PROTECTED + r"|(?P<percent>%%)", re.DOTALL | re.MULTILINE)
_INDENTED = re.compile(r"^(?: {4}| {0,3}\t)", re.MULTILINE)
_LIST = re.compile(r"(?:[-+*]|[0-9]+[.)]) +(?=\S)")
_HEADING = re.compile(r"(?:#{1,6}(?: |$)|(?:=+|-+) *$)")


class Comments(NamedTuple):
    text: str                       # the note, comments hidden or turned into HTML comments
    count: int                      # how many comments were found
    unclosed: list[int]             # the lines (from 1) of a `%%` with no closing `%%` (its comment runs to the end)


def _indented_code(text: str):
    """Offsets of indented code lines, with indentation measured from the enclosing list item."""
    margin = []
    boundary, in_code = True, False
    start = 0
    for line in text.split("\n"):
        end = start + len(line) + 1
        expanded = line.expandtabs(4)
        body = expanded.lstrip(" ")
        if not body.strip():
            boundary = True
        else:
            indent = len(expanded) - len(body)
            while margin and margin[-1] > indent:
                margin.pop()
            base = margin[-1] if margin else 0
            in_code = indent >= base + 4 and (boundary or in_code)
            if in_code:
                yield start, end
            else:
                marker = _LIST.match(body)
                if marker:
                    # Five spaces after a list marker start code after the first space.
                    padding = len(marker[0]) - len(marker[0].rstrip(" "))
                    margin.append(indent + marker.end() - (padding - 1 if padding > 4 else 0))
                boundary = bool(_HEADING.match(body.rstrip("\r")))
        start = end


def _marks(text: str) -> list[int]:
    if not _INDENTED.search(text):
        return [match.start() for match in _SCAN.finditer(text) if match.lastgroup == "percent"]
    spans = iter(_indented_code(text))
    span = next(spans, None)
    marks = []
    cursor = 0
    while match := _SCAN.search(text, cursor):
        while span and span[0] < cursor:
            span = next(spans, None)
        if span and span[0] <= match.start():
            cursor = span[1]
        else:
            if match.lastgroup == "percent":
                marks.append(match.start())
            cursor = match.end()
    return marks


def _pairs(text: str, unclosed: str) -> tuple[list[tuple[int, int, bool]], list[int]]:
    """The (opening, closing, closed) positions of each comment, and the lines of a `%%` left without a mate. With
    ``unclosed="hide"`` that one is a comment too, to the end of the text (closed False, closing = the length of the text)."""
    marks = _marks(text)
    pairs = [(marks[index], marks[index + 1], True) for index in range(0, len(marks) - 1, 2)]
    lines: list[int] = []
    if len(marks) % 2:
        lines = [text.count("\n", 0, marks[-1]) + 1]
        if unclosed != "keep":
            pairs.append((marks[-1], len(text), False))
    return pairs, lines


def _shown(body: str) -> str:
    """The body as the inside of an HTML comment: a `-->` in it would end the comment early, and a `>` first would make
    `<!-->` an empty comment."""
    return "<!-- " + body.replace("-->", "-- >").strip() + " -->"


def mask_comments(text: str, unclosed: str) -> str:
    """Blank percent comments for source scans that must keep the original line numbers."""
    pairs, _ = _pairs(text, unclosed)
    for start, closing, closed in reversed(pairs):
        end = closing + 2 if closed else closing
        text = text[:start] + re.sub(r"[^\r\n]", " ", text[start:end]) + text[end:]
    return text


def hide_comments(text: str, show: bool = False, unclosed: str = "hide") -> Comments:
    """``text`` with its ``%%comments%%`` hidden, or (``show``) kept as HTML comments. A ``%%`` with no closing ``%%`` hides the
    rest of the text (``unclosed="hide"``, Obsidian's way) or is kept as text (``"keep"``); its line is in ``Comments.unclosed``."""
    if "%%" not in text:
        return Comments(text, 0, [])
    pairs, unclosed_lines = _pairs(text, unclosed)
    pieces: list[str] = []
    cursor = 0
    for opening, closing, closed in pairs:
        end = closing + 2 if closed else len(text)
        start_of_line = text.rfind("\n", 0, opening) + 1
        next_newline = text.find("\n", end)
        end_of_line = len(text) if next_newline == -1 else next_newline
        opens_line = not text[start_of_line:opening].strip()
        closes_line = not text[end:end_of_line].strip()
        before = text[cursor:opening]
        if not show:
            if opens_line and closes_line:                      # a comment on lines of its own: the lines go
                pieces.append(text[cursor:start_of_line])
                cursor = min(end_of_line + 1, len(text))
            elif closes_line:                                   # the end of a line: no trailing spaces left (two make a line break)
                pieces.append(before.rstrip(" \t"))
                cursor = end
            else:
                pieces.append(before)
                cursor = end
            continue
        body = text[opening + 2:closing]
        blank = re.search(r"\n[ \t]*\r?\n", body) is not None
        if opens_line and closes_line:
            pieces += [before, _shown(body)]
        elif opens_line:                                        # text follows the comment: an HTML block would swallow it
            pieces += [before, "<span></span>", _shown(body)]
        elif blank:                                             # an inline comment cannot hold a paragraph break
            pieces += [before.rstrip(" \t"), "\n\n", _shown(body), "\n\n"]
            end = end + len(text[end:end_of_line]) - len(text[end:end_of_line].lstrip(" \t"))
        else:
            pieces += [before, _shown(body)]
        cursor = end
    pieces.append(text[cursor:])
    return Comments("".join(pieces), len(pairs), unclosed_lines)
