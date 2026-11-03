"""``%%comments%%``: text Obsidian's reading view hides (v3.32.20).

A comment opens at one ``%%`` and closes at the next, on the same line or many lines later. Fenced code, inline code, math,
front matter and HTML comments are not looked into (a ``%%`` there is the text it looks like). A ``%%`` with no closing mate
stays as it is, and its line is reported.

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


class Comments(NamedTuple):
    text: str                       # the note, comments hidden or turned into HTML comments
    count: int                      # how many comments were found
    unclosed: list[int]             # the lines (from 1) of a `%%` with no closing `%%`


def _pairs(text: str) -> tuple[list[tuple[int, int]], list[int]]:
    """The (opening, closing) positions of each comment, and the lines of a `%%` left without a mate."""
    marks = [match.start() for match in _SCAN.finditer(text) if match.lastgroup == "percent"]
    pairs = [(marks[index], marks[index + 1]) for index in range(0, len(marks) - 1, 2)]
    unclosed = [text.count("\n", 0, marks[-1]) + 1] if len(marks) % 2 else []
    return pairs, unclosed


def _shown(body: str) -> str:
    """The body as the inside of an HTML comment: a `-->` in it would end the comment early, and a `>` first would make
    `<!-->` an empty comment."""
    return "<!-- " + body.replace("-->", "-- >").strip() + " -->"


def hide_comments(text: str, show: bool = False) -> Comments:
    """``text`` with its ``%%comments%%`` hidden, or (``show``) kept as HTML comments."""
    if "%%" not in text:
        return Comments(text, 0, [])
    pairs, unclosed = _pairs(text)
    pieces: list[str] = []
    cursor = 0
    for opening, closing in pairs:
        end = closing + 2
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
    return Comments("".join(pieces), len(pairs), unclosed)
