"""Lua filters pdfmd applies to Pandoc builds, kept as real `.lua` files (the filter's name is the file's stem).

`path(name)` is where a filter lives; Pandoc reads it from there. pdfmd.py works without this package (a lone
copy of the script): the filters are then simply not applied.
"""

from __future__ import annotations

from pathlib import Path

FILTERS = Path(__file__).resolve().parent


def path(name: str) -> Path | None:
    """The file of filter `name` (`table_width`), or None when it is not there."""
    candidate = FILTERS / f"{name}.lua"
    return candidate if candidate.is_file() else None
