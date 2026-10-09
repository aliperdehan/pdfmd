"""Cross-references for a part built on its own (v3.26.0).

A part of a split document, or one section of an ordinary document, is typeset without the rest, so a reference to
a section, figure or equation outside it used to print ``??``. Three sources can fill those in, tried in this order
(``pdfmd-options: {seed-labels: ...}`` / ``--seed-labels`` picks which):

    aux    the ``.aux`` of the last full build, kept by the cache (exact, free; needs ``cache: {aux: true}``)
    scan   the LaTeX Pandoc writes for the WHOLE document is read for what steps a counter or defines a label, and
           LaTeX replays that at the start of the part (instant, a second Pandoc run; exact for the headings,
           floats, equations and labels Pandoc writes, blind to a macro the document defines itself)
    draft  a LaTeX pass over the whole document without output (exact, but most of a full compile)

``auto`` (the default) is aux, then scan for what the aux does not know. ``off`` leaves every reference to ``??``.
``scan.py`` reads, ``replay.py`` is the TeX that replays; neither needs Pandoc or LaTeX to be imported.
"""

from __future__ import annotations

from .replay import REPLAY_DEFS, render
from .scan import Event, Scan, scan

MODES = ("auto", "aux", "scan", "draft", "off")

__all__ = ["MODES", "REPLAY_DEFS", "Event", "Scan", "render", "scan"]
