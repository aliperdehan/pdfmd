"""Flavour presets (pdfmd 3.32.22, entry 3ee/3eo/3ex).

A flavour is a name for a set of reading choices. One table, ``PRESETS``, holds them; ``pdfmd.py`` looks a document's flavour
up here and does what the row says, so a new flavour (or, later, a user's own) is a new row, not new code.

The columns of a row:

``reader``    the Pandoc reader. ``"auto"`` is pdfmd's own pick (gfm for a file with no front matter, Pandoc's Markdown for one
              that has some, and so on); ``"default"`` is Pandoc's own default for the file (no ``-f``); anything else is a
              reader spec, handed to Pandoc as it stands (``gfm``, ``commonmark``).
``comments``  Obsidian's ``%%comments%%`` are hidden.
``gfm_plus``  extensions added to the gfm reader pdfmd picks (``reader = "auto"`` only), as ``+name`` text.
``markdown_plus``  the same for Pandoc's Markdown reader when pdfmd picks it (a file with front matter, a Pandoc-only syntax...).
``markup``    the kinds of universal markup that are on without a ``markup`` setting (``pdfmd-options.markup``, ``--markup``), as a
              space-separated list; ``pagebreak`` likewise for the page-break families (``all``). Only for a Markdown file; a
              ``markup`` / ``pagebreak`` setting of any kind, ``false`` included, replaces the row's.
``embeds``    Obsidian's ``![[picture.png|300]]`` is read as an image embed (found by name, sized in px).
``wikilinks`` Obsidian's ``[[Note|alias]]`` is written as the text it shows.
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
    gfm_plus: str = ""
    markdown_plus: str = ""
    markup: str = ""
    pagebreak: str = ""
    embeds: bool = False
    wikilinks: bool = False


OWN_SYNTAX = "callouts toc center highlight underline keep landscape appendix"      # `space` stays off: a lone <br> is often just a blank line

PRESETS: dict[str, Preset] = {
    "pandoc": Preset("default", False, "keep"),
    "gfm": Preset("gfm", False, "keep"),
    "commonmark": Preset("commonmark", False, "keep"),
    "pdfmd": Preset("auto", True, "keep", "+smart+implicit_figures", "+autolink_bare_uris+emoji", OWN_SYNTAX, "all", True, True),
    "obsidian": Preset("auto", True, "hide", "+smart+implicit_figures", "+autolink_bare_uris+emoji", OWN_SYNTAX, "all", True, True),
}
WORDS = ("auto", *PRESETS)

__all__ = ["PRESETS", "WORDS", "Preset"]
