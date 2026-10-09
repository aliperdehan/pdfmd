"""Checking an extraction against Pandoc's own reading: the tables of the new document must be the tables of the old."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .convert import TablesError


def _tables(node, found: list) -> None:
    if isinstance(node, dict):
        if node.get("t") == "Table":
            found.append(node)
        for value in node.values():
            _tables(value, found)
    elif isinstance(node, list):
        for value in node:
            _tables(value, found)


def _normal(table: dict) -> dict:
    attr, caption, colspecs, head, bodies, foot = table["c"]
    widths = [round(spec[1]["c"], 3) if spec[1]["t"] == "ColWidth" else None for spec in colspecs]
    if len(widths) > 1 and len(set(widths)) == 1:
        widths = [None] * len(widths)        # equal shares are what a pipe table's equal dashes give: nobody chose them
    return {"id": attr[0], "classes": attr[1], "caption": caption, "aligns": [spec[0]["t"] for spec in colspecs],
            "widths": widths, "head": head, "bodies": bodies, "foot": foot}


def pandoc_tables(pandoc: str, text: str, directory: Path, *filters: Path, reader: str = "markdown") -> list[dict]:
    """The tables Pandoc reads from `text` (written beside the document, so a relative `file=` is found)."""
    scratch = directory / f".pdfmd-verify-{os.getpid()}.md"
    scratch.write_text(text, encoding="utf-8")
    try:
        command = [pandoc, "-f", reader, "-t", "json"]
        for item in filters:
            command += ["--lua-filter", str(item)]
        done = subprocess.run(command + [scratch.name], capture_output=True, text=True, encoding="utf-8", cwd=directory)
    finally:
        scratch.unlink(missing_ok=True)
    if done.returncode != 0:
        raise TablesError("Pandoc could not read the result: " + done.stderr.strip())
    found: list = []
    _tables(json.loads(done.stdout), found)
    return [_normal(table) for table in found]


def same_tables(pandoc: str, before: str, after: str, directory: Path, csv_filter: Path | None,
                reader: str = "markdown") -> list[str]:
    """What differs between the tables of `before` and of `after` (read with the CSV filter): [] when nothing."""
    old = pandoc_tables(pandoc, before, directory, *([csv_filter] if csv_filter else []), reader=reader)
    new = pandoc_tables(pandoc, after, directory, *([csv_filter] if csv_filter else []), reader=reader)
    if len(old) != len(new):
        return [f"{len(old)} tables before, {len(new)} after"]
    problems = []
    for number, (one, other) in enumerate(zip(old, new), 1):
        for key in one:
            if one[key] != other[key]:
                problems.append(f"table {number}: {key} differs")
    return problems
