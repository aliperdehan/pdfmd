"""Obsidian callout folds and nonstandard task checkboxes."""

from __future__ import annotations

import re

from .comments import _PROTECTED
from .properties import _CODE_IN_CONTAINER, source_matches


_QUOTE = r"(?:[ \t]*>[ \t]?)*"
_SPACE = r"(?=[ \t\r\n]|$)"
_QUOTE_PREFIX = re.compile("^" + _QUOTE)
_MARKERS = re.compile(
    _PROTECTED + "|" + _CODE_IN_CONTAINER
    + rf"|(?P<fold>^{_QUOTE}[ \t]*>[ \t]*(?P<callout>\[![A-Za-z0-9_-]+\])(?P<state>[-+]){_SPACE})"
    + rf"|(?P<task>^{_QUOTE}[ \t]*[-+*][ \t]+(?P<box>\[(?P<status>[^\x00-\x20\s\[\]\\xX])\]){_SPACE})",
    re.MULTILINE | re.DOTALL,
)


def _opens_quote(text, match):
    start = match.start()
    previous_start = text.rfind("\n", 0, max(0, start - 1)) + 1
    previous = _QUOTE_PREFIX.match(text, previous_start)[0]
    return previous.count(">") < text[start:match.start("callout")].count(">")


def callouts_and_tasks(text, fold=False, *, native=False):
    """Use Pandoc spans to carry the extra syntax, or a plain checkbox for the native tier."""
    pieces = []
    start = 0
    for match in source_matches(text, _MARKERS):
        if match.lastgroup == "fold" and fold and (match.start() == 0 or _opens_quote(text, match)):
            left, end = match.start("callout"), match.end("state")
            style = "open" if match["state"] == "+" else "closed"
            kind = match["callout"][2:-1]
            marker = f'[]{{.pdfmd-callout-{style} type="{kind}"}}'
        elif match.lastgroup == "task":
            left, end = match.span("box")
            status = match["status"]
            marker = f"[ ] {status}" if native else f'[]{{.pdfmd-task status="{ord(status)}"}}'
        else:
            continue
        pieces.extend((text[start:left], marker))
        start = end
    return "".join([*pieces, text[start:]]) if pieces else text
