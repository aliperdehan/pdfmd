"""The space between paragraphs (v3.33.58): `pdfmd-options: {paragraph-spacing: 6pt}`, or `--paragraph-spacing 6pt` for a
run. The value is the room a paragraph break adds to the line spacing: a length LaTeX and Typst both read (pt, mm, cm, in, em),
`0` for none (the next paragraph one line below, as a book sets it with `indent: true`), or `auto`, the default: each engine's
own spacing, as before.

- LaTeX and Beamer (`latex_args`): `\\setlength{\\parskip}{X}` in a header file of its own, after the template's paragraph
  set-up (the parskip package without `indent`, the class's 0pt with it).
- Typst (`typst_args`): the value reaches `pdfmd_lua/typst.lua` as `pdfmd-paragraph-spacing`, which writes `#set
  par(spacing: <leading> + X)`. Typst measures a paragraph's spacing as it measures its leading, edge to edge, where LaTeX adds
  `\\parskip` to the line pitch: the line's leading is added so the same value gives the same gap. `par.spacing` is Typst 0.12's,
  the oldest pdfmd builds with (v3.33.62: an older one is refused as an engine, `pdfmd_install.typst_too_old`).
- The HTML writers (WeasyPrint, Calibre, the browser, `--to html`) are not given it: pdfmd adds no style sheet of its own in
  one place there; a style sheet's `p { margin: ... }` does it.

`core` is the `pdfmd` module, bound by `pdfmd.py` on first use (the first binding wins); the pdfmd names the code uses
(`cache_root`, `display_path` and `first_pdfmd_option`) are read as `core.X` when it runs.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

core = None

ENV = "PDFMD_PARAGRAPH_SPACING"            # --paragraph-spacing, set by main(), so -j workers read it too
KEY = "paragraph-spacing"
ACCEPTED = "a length such as 6pt or 1em (pt, mm, cm, in, em), 0, or auto"
LENGTH_RE = re.compile(r"(?:\d+(?:\.\d+)?|\.\d+)(?:pt|mm|cm|in|em)")
ZERO_RE = re.compile(r"(?:0+(?:\.0*)?|\.0+)(?:pt|mm|cm|in|em)?")


def normalise(value) -> str | None:
    """The length as both engines take it, or None for auto (and unset). `0` (any zero) is `0pt`: LaTeX needs a unit.
    Raises ValueError for anything else: a bare number, a negative length, another unit, true/false."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(value)
    text = str(value).strip().lower().replace(" ", "")
    if text in ("", "auto"):
        return None
    if ZERO_RE.fullmatch(text):
        return "0pt"
    if LENGTH_RE.fullmatch(text):
        return text
    raise ValueError(value)


def command_line_value(value: str) -> str:
    """--paragraph-spacing as main() hands it to the builds (`auto` for auto); a bad value stops the run."""
    try:
        return normalise(value) or "auto"
    except ValueError:
        raise SystemExit(f"--paragraph-spacing must be {ACCEPTED}, not {value!r}") from None


def apply_cli(value: str) -> None:
    """Pass a validated command-line value to this run and its batch workers."""
    os.environ[ENV] = command_line_value(value)


def paragraph_spacing(md_path: Path, metadata_files: list[Path]) -> str | None:
    """The space between paragraphs this build asks for (normalise), None for each engine's own: --paragraph-spacing, else
    `pdfmd-options.paragraph-spacing` (the document, its metadata files, the config)."""
    value = os.environ.get(ENV)
    if value is not None:
        return command_line_value(value) if value != "auto" else None
    value = core.first_pdfmd_option(md_path, metadata_files, KEY)
    try:
        return normalise(value)
    except ValueError:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.{KEY} must be {ACCEPTED}, not {value!r}") from None


def latex_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """`--include-in-header` of a file that sets `\\parskip`, or [] when the spacing is the engine's own."""
    files = sources if isinstance(sources, list) else [sources]
    value = paragraph_spacing(files[0], metadata_files) if files else None
    if value is None:
        return []
    text = (f"% pdfmd: the space between paragraphs (paragraph-spacing: {value}), after the template's own\n"
            f"\\setlength{{\\parskip}}{{{value}}}\n")
    path = core.cache_root() / "tex" / f"parskip-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(path)]


def typst_args(md_path: Path, metadata_files: list[Path], writer: str) -> list[str]:
    """What typst.lua needs to set the space between paragraphs: the value."""
    if writer != "typst":
        return []
    value = paragraph_spacing(md_path, metadata_files)
    return ["-M", f"pdfmd-paragraph-spacing={value}"] if value is not None else []
