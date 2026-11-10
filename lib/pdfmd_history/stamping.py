"""History-stamp edits, preserving the text around pdfmd's own line."""

from __future__ import annotations

import re

core = None


def demote(body: str, current, indent: str, new_line: str) -> str:
    """Keep the live stamp first and move its predecessor into the owned history list."""
    prefix = body[:current.start()]
    leading = re.match(r"(?:[ \t]*\n)*", prefix).group()
    suffix = body[current.end():]
    if suffix.startswith("\n"):
        suffix = suffix[1:]  # the old stamp's line terminator
    notes = prefix[len(leading):] + suffix
    bullet = f"{indent}  - {current.group(0)[len(indent):]}\n"
    history = core.history_heading_pattern(indent).search(notes)
    if history:
        notes = notes[:history.end()] + bullet + notes[history.end():]
    else:
        separator = "" if not notes or notes.endswith("\n") else "\n"
        notes += separator + f"{indent}Compile History:\n{bullet}"
    return f"{leading}{indent}{new_line}\n{notes}"
