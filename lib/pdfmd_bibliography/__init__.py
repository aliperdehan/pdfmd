"""The hanging indent of a bibliography: one setting for every writer (`bibliography-indent`).

`pdfmd-options: {bibliography-indent: 0.5in}` (the document, its metadata files, the folder layers, the global setup; there is no
command-line flag, a name starting `--bibliography` would be read as Pandoc's own `--bibliography`): how far the lines of an entry after its first are set in, in the combined reference
list and in the entries `fullcite` places in the text, so the two match. A length (pt, mm, cm, in, em), `0` for none, or
`auto` / not set: Pandoc's own, 1.5em, which writers other than Typst already apply to the list as they do today (LaTeX 1.5em,
HTML 2em from its style sheet, Word 0.5in) and Typst, whose writer ignores the style's `hanging-indent`, now gets (1.5em).
Only a style that asks for a hanging indent has one (citeproc's `hanging-indent` class on the list); a numbered style has none.

`pdfmd_lua/bibliography_indent.lua` does the list after `--citeproc`, per writer: `\\cslhangindent` for LaTeX, `#set par(hanging-indent:)`
around the list for Typst, a style on each entry for HTML, and a paragraph style `pdfmd-hang-<length>` for Word and OpenDocument
(`pdfmd_office` writes its indent afterwards). It goes in only when the setting is set, or for Typst (the default). The entries of
`fullcite` take the same value (`pdfmd_fullcite`).

`core` is the `pdfmd` module (`from pdfmd_base import core`); the names used (`first_pdfmd_option`, `display_path`) are read as
`core.X` when the code runs.
"""

from __future__ import annotations

import re
from pathlib import Path

from pdfmd_base import core

KEY = "bibliography-indent"
DEFAULT = "1.5em"                         # Pandoc's own (\cslhangindent); the author decided it (entry D53)
ACCEPTED = "a length such as 0.5in or 1.5em (pt, mm, cm, in, em), 0 for none, or auto"
LENGTH_RE = re.compile(r"(?:\d+(?:\.\d+)?|\.\d+)(?:pt|mm|cm|in|em)")
ZERO_RE = re.compile(r"(?:0+(?:\.0*)?|\.0+)(?:pt|mm|cm|in|em)?")


def normalise(value) -> str | None:
    """The length as every writer takes it, `0pt` for none, or None for auto (and not set). Raises ValueError for anything else."""
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


def setting(md_path: Path, metadata_files: list[Path]) -> str | None:
    """The indent asked for (`0pt` for none), None for auto: `pdfmd-options.bibliography-indent`."""
    value = core.first_pdfmd_option(md_path, metadata_files, KEY)
    try:
        return normalise(value)
    except ValueError:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.{KEY} must be {ACCEPTED}, not {value!r}") from None


def bibliography_indent_args(sources: Path | list[Path], metadata_files: list[Path], cmd: list[str], pandoc_options: list[str],
                             writer: str) -> list[str]:
    """The filter for the combined list, after `--citeproc`: with the value when one is set, and for Typst (`writer`, Pandoc's
    name or the engine's) with the default when not; [] without citeproc, and for any other writer when nothing is set."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or ("--citeproc" not in cmd and "--citeproc" not in pandoc_options):
        return []
    value = setting(files[0], metadata_files)
    if value is None and writer not in ("typst", "typ"):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("bibliography_indent")
    if shipped is None:
        return []
    return ["-M", f"pdfmd-bibliography-indent={value}" if value else f"pdfmd-bibliography-indent-default={DEFAULT}",
            "--lua-filter", str(shipped)]
