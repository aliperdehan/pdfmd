"""A document's history as a plain-text file (`NAME.hst`), kept beside its backups instead of inside the document.

One entry per line, so two files can be joined with `cat`, diffed, and merged line by line without losing or doubling
anything. pdfmd.py works without this package: the history then stays in the document's BUILD NOTES block."""

from __future__ import annotations

from .hst import Entry, HST_SUFFIX, add_entry, merge, parse, read_file, render, write_file

__all__ = ["Entry", "HST_SUFFIX", "add_entry", "merge", "parse", "read_file", "render", "write_file"]
