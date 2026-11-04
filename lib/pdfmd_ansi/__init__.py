"""pdfmd's terminal renderer (`--to ansi`, `--view`): Pandoc's JSON AST -> text with ANSI styling, box-drawn tables
and wrapping to the terminal width. Pure: no pdfmd import, so other programs can use it as it is.

    from pdfmd_ansi import render
    sys.stdout.write(render(json.loads(pandoc_json), width=shutil.get_terminal_size().columns))
"""

from .render import render, Renderer, plain
from .text import strip_ansi, visible_width

__all__ = ["render", "Renderer", "plain", "strip_ansi", "visible_width"]
