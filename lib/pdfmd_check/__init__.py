"""`pdfmd --check`: a linter for Markdown documents (v3.26.15).

Reads the text of a document (or a scaffold and its parts, as one document) and reports what would go wrong or print
wrongly in the build, without building anything: an image or a `file=` that is not there, a link or `#anchor` that points
nowhere, a duplicate `{#id}`, a `@fig:x` or `\\ref{x}` nothing defines, a citation the bibliography does not hold,
a footnote without its definition, a heading level that jumps, a code fence or `<!--` that is never closed, front
matter that does not parse. `lint.py` is plain text analysis (no Pandoc, no LaTeX, no pdfmd import); the
caller supplies what needs pdfmd's own discovery (the bibliography's keys).
"""

from __future__ import annotations

from .lint import CODES, Bibliography, Problem, Source, lint, parse_ignore

__all__ = ["CODES", "Bibliography", "Problem", "Source", "lint", "parse_ignore"]
