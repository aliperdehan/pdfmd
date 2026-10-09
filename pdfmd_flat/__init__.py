"""Flat Markdown: `--to gfm` (v3.26.3).

`--to gfm` writes plain GitHub-flavoured Markdown that any viewer reads as it is. pdfmd runs everything it runs for
any other target (includes, parts, `.csv` tables, pandoc-crossref, citeproc, the raw pieces, the document's filters),
then `pdfmd_lua/flat.lua` takes out what Pandoc's gfm writer would leave as HTML or as noise (see the filter's own
header). `--to gfm+raw` is Pandoc's own gfm writer, with its HTML, unchanged.

This module holds the settings (`pdfmd-options: {gfm: {scripts: unicode, math: dollars, title: true}}`, `--gfm-scripts`,
`--gfm-math`) and the writer's name; the transformation itself lives in the Lua filter.
"""

from __future__ import annotations

FLAT = "gfm"
PANDOC_GFM = "gfm+raw"          # the target that is Pandoc's own gfm writer
SCRIPT_MODES = ("unicode", "html", "drop", "ascii")
MATH_MODES = ("dollars", "fenced")
DEFAULTS = {"scripts": "unicode", "math": "dollars", "title": True}


class FlatError(ValueError):
    pass


def is_flat(target: str | None) -> bool:
    return (target or "").casefold() == FLAT


def is_family(target: str | None) -> bool:
    """Both spellings: the flat writer and Pandoc's own."""
    return (target or "").casefold() in (FLAT, PANDOC_GFM)


def truthy(value) -> bool:
    return value is True or str(value).strip().casefold() in {"true", "yes", "on", "1"}


def settings(option, scripts: str | None = None, math: str | None = None, title: bool | None = None) -> dict:
    """The settings of a build: the command line over the document's `gfm` option over the defaults."""
    chosen = dict(DEFAULTS)
    if isinstance(option, dict):
        for key, value in option.items():
            name = str(key).strip().casefold()
            if name not in DEFAULTS:
                raise FlatError(f"{key!r} is not a gfm setting (scripts, math, title)")
            chosen[name] = truthy(value) if name == "title" else str(value).strip().casefold()
    elif option is not None:
        raise FlatError("pdfmd-options.gfm must be a mapping (scripts, math, title)")
    if scripts is not None:
        chosen["scripts"] = scripts.strip().casefold()
    if math is not None:
        chosen["math"] = math.strip().casefold()
    if title is not None:
        chosen["title"] = title
    if chosen["scripts"] not in SCRIPT_MODES:
        raise FlatError(f"gfm scripts {chosen['scripts']!r}: choose one of {', '.join(SCRIPT_MODES)}")
    if chosen["math"] not in MATH_MODES:
        raise FlatError(f"gfm math {chosen['math']!r}: choose one of {', '.join(MATH_MODES)}")
    return chosen


def writer(target: str, math: str, extensions: frozenset[str]) -> str:
    """The Pandoc writer string: `gfm+raw` is plain `gfm`; the flat writer is `gfm` without raw HTML, with `$..$` math
    (as GitHub, VS Code and Obsidian read it) when this Pandoc has the extensions for it."""
    if target.casefold() == PANDOC_GFM:
        return "gfm"
    name = "gfm-raw_html"
    if math == "dollars" and {"tex_math_dollars", "tex_math_gfm"} <= extensions:
        name += "+tex_math_dollars-tex_math_gfm"
    return name
