"""``[[Note]]``, ``[[Note|alias]]``, ``[[Note#Heading]]``: Obsidian's links between notes, written as the text they show (v3.32.26).

A printed document has no other notes to open, so a wikilink becomes its display text: the alias after the bar when there is
one, else the note name, with ``#Heading`` shown as ``Note > Heading`` as Obsidian does (``[[#Heading]]``, a link inside the
note, is just ``Heading``). Fenced code, inline code, math, the front matter and HTML comments are not looked into. Left as they
are: ``![[...]]`` (a picture is embeds.py's, a note embed is a later step), ``[[_TOC_]]`` (pdfmd's contents marker) and
``[[1]](url)`` (a link whose text is ``[1]``).
"""

from __future__ import annotations

import re
from typing import NamedTuple

from .comments import _PROTECTED

_LINK = (r"(?P<link>(?<!!)\[\[(?!\s*_TOC_\s*\]\])(?P<target>[^\[\]|#\n\\]*)(?:#(?P<heading>[^\[\]|\n\\]*))?"
         r"(?:\\?\|(?P<alias>[^\[\]\n]*))?\]\](?![(\[]))")
_SCAN = re.compile(_PROTECTED + "|" + _LINK, re.DOTALL | re.MULTILINE)
_SPECIAL = re.compile(r"([\\`*_\[\]<$~])")


class Wikilinks(NamedTuple):
    text: str       # the note with each wikilink written as its display text
    count: int      # how many were written as text


def _plain(text: str) -> str:
    return _SPECIAL.sub(r"\\\1", text)


def wikilinks_as_text(text: str) -> Wikilinks:
    """``text`` with each wikilink replaced by what Obsidian shows for it (see the module's docstring)."""
    count = 0

    def replace(match: re.Match) -> str:
        nonlocal count
        if match.lastgroup != "link":
            return match.group(0)
        target = (match.group("target") or "").strip()
        heading = (match.group("heading") or "").strip()
        alias = (match.group("alias") or "").strip()
        shown = alias or " > ".join(part for part in (target, heading) if part)
        if not shown:
            return match.group(0)
        count += 1
        return _plain(shown)

    return Wikilinks(_SCAN.sub(replace, text), count)
