"""Obsidian's own Markdown syntax, read before Pandoc sees the note (entry 3ee of the maintainer's notes).

Each module is pure: it takes the text of a note and returns the text Pandoc should read, importing nothing from pdfmd.
pdfmd.py decides whether the note is Obsidian's (a `.obsidian/` folder above it, or `flavour: obsidian`) and calls them.
"""

from .comments import Comments, hide_comments

__all__ = ["Comments", "hide_comments"]
