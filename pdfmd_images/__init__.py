"""Images that a LaTeX engine cannot read as they are. Today that is SVG: LaTeX wants a PDF (or a raster), so pdfmd
converts each SVG a document refers to once, keeps the result by the file's content, and hands the build the PDF.
pdfmd.py works without this package: SVG then goes to Pandoc as before."""

from __future__ import annotations

from .remote import fetch as fetch_remote
from .scan import ImageReference, find_references
from .svg import CONVERTERS, available_converters, convert_svg, install_hint

__all__ = ["fetch_remote", "ImageReference", "find_references", "CONVERTERS", "available_converters", "convert_svg", "install_hint"]
