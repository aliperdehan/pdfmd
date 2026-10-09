"""Documents that are already finished: a `.typ` file goes to Typst and an `.html` file to an HTML engine or a
browser, with no Pandoc between them (Pandoc would read them into its own model and write them out again, losing the
page size, the styles and the scripts on the way). pdfmd.py works without this package: the files then go through
Pandoc as before."""

from __future__ import annotations

from . import defaults
from .html import (BROWSER_NAMES, HTML_ENGINES, accepts_request as html_accepts_request, find_browser, has_scripts,
                   render_html, attempts as html_attempts)
from .typst import compile_typst, accepts_request as typst_accepts_request

__all__ = ["defaults", "BROWSER_NAMES", "HTML_ENGINES", "html_accepts_request", "find_browser", "has_scripts", "render_html",
           "html_attempts", "compile_typst", "typst_accepts_request"]
