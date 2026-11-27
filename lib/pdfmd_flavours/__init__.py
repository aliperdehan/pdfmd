"""Flavour presets (pdfmd 3.32.22, entry 3ee/3eo/3ex).

A flavour is a name for a set of reading choices. ``PRESETS`` holds the defaults. ``pdfmd_flavours.markup`` looks up a
document's flavour here and applies any individual ``flavour-overrides``.

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
``numbered_references``  recognise trailing numbered source lists with matching citation markers.
``embeds``    Obsidian's ``![[picture.png|300]]`` is read as an image embed (found by name, sized in px).
``wikilinks`` Obsidian's ``[[Note|alias]]`` is written as the text it shows.
``newline``   what a single newline inside a paragraph does: ``hard`` (a line break, as Obsidian shows it unless its "Strict line
              breaks" is on) or ``soft`` (a space, as CommonMark, GFM files and Pandoc read it). Obsidian inside a vault says
              which in its own ``.obsidian/app.json`` (``strictLineBreaks``), which wins over this column.
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
    newline: str = "soft"
    numbered_references: bool = False


OWN_SYNTAX = "callouts toc centre highlight underline spans keep landscape appendix fullcite pagecite excerpts"      # `space` stays off: a lone <br> is often just a blank line

PRESETS: dict[str, Preset] = {
    "pandoc": Preset("default", False, "keep"),
    "gfm": Preset("gfm", False, "keep"),
    "commonmark": Preset("commonmark", False, "keep"),
    "pdfmd": Preset("auto", True, "keep", "+smart+implicit_figures", "+autolink_bare_uris+emoji", OWN_SYNTAX, "all", True, True, "soft", numbered_references=True),
    "obsidian": Preset("auto", True, "hide", "+smart+implicit_figures", "+autolink_bare_uris+emoji", OWN_SYNTAX, "all", True, True, "hard", numbered_references=True),
}
WORDS = ("auto", *PRESETS)

__all__ = ["PRESETS", "WORDS", "Preset"]
