"""SVG images converted for LaTeX (PDF, or PNG as a fallback) and Word (PNG), using the same chain as diagrams.
pdfmd converts each SVG a document refers to once and keeps the result by the file's content.
pdfmd.py works without this package: SVG then goes to Pandoc as before."""

from __future__ import annotations

from .remote import fetch as fetch_remote
from .scan import ImageReference, find_references
from .svg import CONVERTERS, available_converters, convert_svg, install_hint

__all__ = ["fetch_remote", "ImageReference", "find_references", "CONVERTERS", "available_converters", "convert_svg", "install_hint"]
