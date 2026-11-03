"""Flavour presets (pdfmd 3.32.22, entry 3ee/3eo/3ex).

A flavour is a name for a set of reading choices. One table, ``PRESETS``, holds them; ``pdfmd.py`` looks a document's flavour
up here and does what the row says, so a new flavour (or, later, a user's own) is a new row, not new code.

The columns of a row:

``reader``    the Pandoc reader. ``"auto"`` is pdfmd's own pick (gfm for a file with no front matter, Pandoc's Markdown for one
              that has some, and so on); ``"default"`` is Pandoc's own default for the file (no ``-f``); anything else is a
              reader spec, handed to Pandoc as it stands (``gfm``, ``commonmark``).
``comments``  Obsidian's ``%%comments%%`` are hidden.
``unclosed``  what a ``%%`` with no closing ``%%`` does: ``hide`` (the rest of the note, as Obsidian does) or ``keep`` (it
              stays text, with a warning). Outside a vault a stray ``%%`` is as likely TeX or plain text as a forgotten close, so
              ``pdfmd`` keeps it.

``auto`` is not a row: it is ``obsidian`` inside a vault and ``pdfmd`` elsewhere (``pdfmd.flavour_of``).
"""
from typing import NamedTuple


class Preset(NamedTuple):
    reader: str
    comments: bool
    unclosed: str


PRESETS: dict[str, Preset] = {
    "pandoc": Preset("default", False, "keep"),
    "gfm": Preset("gfm", False, "keep"),
    "commonmark": Preset("commonmark", False, "keep"),
    "pdfmd": Preset("auto", True, "keep"),
    "obsidian": Preset("auto", True, "hide"),
}
WORDS = ("auto", *PRESETS)

__all__ = ["PRESETS", "WORDS", "Preset"]
