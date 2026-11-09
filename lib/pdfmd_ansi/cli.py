"""The terminal reader's command-line side (`--to ansi`, `--view`): the width argument, the width and colour choices, the
math-as-text bridge and the three entry points that turn Pandoc's JSON AST (or, with no Pandoc, the built-in parser's tree)
into styled text.

Moved out of `pdfmd.py` unchanged (v3.33.6, SPLIT.md). `core` is the `pdfmd` module, bound when the module is first loaded (the
first binding wins); the pdfmd names the code uses, `ANSI_*_ENV`, `ANSI_FALLBACK_WIDTH` and `inkmd_vendored` (patched by tests)
among them, are read as `core.X` when it runs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

core = None

def ansi_width_argument(value: str) -> int:
    if not value.isdigit() or int(value) < 20:
        raise argparse.ArgumentTypeError(f"{value!r}: a width in columns, 20 or more")
    return int(value)


def ansi_columns() -> int:
    """The width to draw for: --width, else the terminal's, else 120."""
    value = os.environ.get(core.ANSI_WIDTH_ENV, "")
    if value.isdigit() and int(value) >= 20:
        return int(value)
    return max(20, shutil.get_terminal_size((core.ANSI_FALLBACK_WIDTH, 24)).columns)


def ansi_colour_on() -> bool:
    """--color always|never decides; `auto` (and a build into a file) is on unless NO_COLOR is set."""
    mode = os.environ.get(core.ANSI_COLOR_ENV, "auto")
    if mode in ("always", "never"):
        return mode == "always"
    return not os.environ.get("NO_COLOR")


def ansi_math(tex: str, display: bool) -> "list[list[tuple[str, str]]] | None":
    """A formula for pdfmd_ansi.render: lines of (text, kind) pieces from the math-as-text converter (MathText), kind ""
    (upright), "i" (a variable) or "b" (bold): Unicode Greek, operators, sub- and superscripts, `(a+b)/(c+d)`; None when the
    converter cannot read it, and the TeX is shown as it was written. This is the linear form; for `$$..$$` on its own the renderer
    stacks fractions, roots and sums on several rows (pdfmd_ansi/mathbox.py) and sets every other piece of the formula with this."""
    from pdfmd_ansi.render import script
    try:
        lines = core.math_lines(tex, False)
    except Exception:                                   # a formula the converter chokes on is the TeX, not a crash
        return None
    shown: list[list[tuple[str, str]]] = []
    for line in lines:
        pieces: list[tuple[str, str]] = []
        raised: bool | None = None
        held = ""
        for markup, text, _ in line:
            if markup in ("<sup>", "<sub>"):                # a script the converter left as a tag (nested in a root, say)
                raised, held = markup == "<sup>", ""
            elif markup in ("</sup>", "</sub>"):
                if raised is not None and held:
                    pieces.append((script(held, raised), ""))
                raised = None
            elif raised is not None:
                held += text
            elif text:
                kind = "b" if markup.startswith("**") else "i" if markup.startswith("*") else ""
                if not kind and text[0].isascii() and text[0].isalpha() and pieces and pieces[-1][0][-1:].isalnum():
                    text = " " + text                   # a function name after a variable: RT ln K, not RTln K
                pieces.append((text, kind))
        if pieces:
            shown.append(pieces)
    return shown or None


def ansi_document_text(document: dict) -> "tuple[str, int]":
    """Pandoc's JSON AST as styled text, and how many raw pieces (LaTeX, Word XML) no terminal could show."""
    from pdfmd_ansi.render import Renderer
    renderer = Renderer(ansi_columns(), ansi_colour_on(), os.environ.get(core.ANSI_LINKS_ENV) == "1", ansi_math)
    return renderer.render(document), renderer.skipped


def ansi_finish(json_file: Path, output: Path, md_path: Path, verbose: bool = False) -> str | None:
    """After Pandoc wrote its JSON AST: the styled text into `output`. A reason when it cannot (the build failed)."""
    try:
        text, skipped = ansi_document_text(json.loads(json_file.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        return f"{core.display_path(md_path)}: --to ansi could not draw what Pandoc made ({type(error).__name__}: {error})"
    core.write_text_lf(output, text)
    if skipped:
        core.vprint(verbose, f"NOTE  ansi: {core.display_path(md_path)}: {skipped} raw piece{'s' if skipped != 1 else ''} (LaTeX, Word XML) "
              "no terminal can show left out", file=sys.stderr)
    return None


def ansi_without_pandoc(md_path: Path, output: Path) -> "tuple[bool, str]":
    """`--to ansi` with no Pandoc: the built-in parser reads the Markdown (no filters, citations or footnotes)."""
    if md_path.suffix.lower() not in (".md", ".markdown", ".txt") or not core.inkmd_vendored():
        return False, core.PANDOC_MISSING
    try:
        from pdfmd_ansi.native import from_markdown
        text, _ = ansi_document_text(from_markdown(core.read_text_best_effort(md_path)))
    except (OSError, ImportError, ValueError) as error:
        return False, f"{core.display_path(md_path)}: --to ansi could not read it without Pandoc ({type(error).__name__}: {error})"
    print(f"NOTE  ansi: no Pandoc: {core.display_path(md_path)} was read by the built-in parser (no filters, citations "
          "or footnotes)", file=sys.stderr)
    core.write_text_lf(output, text)
    return True, ""
