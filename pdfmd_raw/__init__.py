"""`pdfmd-options: {raw: ...}` and `--raw`: which non-Markdown syntaxes take part in a build (v3.25.17).

Markdown can carry raw HTML, raw LaTeX, raw Typst and raw Word/OpenDocument XML. Pandoc keeps the ones written in the
format it is writing and drops the rest. This turns the choice into a table, per output family:

    pdfmd-options:
      raw:
        tex:    [tex, html, typst]     # LaTeX builds (PDF through lualatex, xelatex, ...)
        typst:  [typst, html, tex]     # Typst builds
        html:   [html, tex, typst]     # HTML, EPUB, PDF through weasyprint and the other HTML engines
        office: [office, html]         # Word and OpenDocument (and PDF through soffice)
        md:     [html, tex, typst]     # flat Markdown (--to gfm); it takes every syntax unless this says otherwise

A family takes the syntaxes it lists: its own stay as they are, the others are carried over by pdfmd_lua/raw.lua (HTML and
LaTeX read by Pandoc into the target's own elements, Typst drawn as a vector picture); a syntax left out is dropped,
the family's own included. `raw: all` lists everything for every family; `raw: [html]` the same list for each; a family
that is not mentioned is left to Pandoc (its own syntax kept, the rest dropped), as without the option.
"""

from __future__ import annotations

FAMILIES = ("tex", "typst", "html", "office", "md")
SYNTAXES = ("tex", "html", "typst", "office")
FAMILY_ALIASES = {"latex": "tex", "pdf-tex": "tex", "web": "html", "epub": "html", "word": "office", "docx": "office",
                  "odt": "office", "opendocument": "office", "markdown": "md", "gfm": "md", "flat": "md",
                  "commonmark": "md"}
SYNTAX_ALIASES = {"latex": "tex", "word": "office", "docx": "office", "odt": "office", "openxml": "office",
                  "opendocument": "office", "xml": "office"}
ON = {"all", "on", "yes", "true", "everything"}
OFF = {"", "off", "no", "false", "none", "auto"}


class RawError(ValueError):
    pass


def syntaxes(value) -> list[str]:
    """A list (or a comma/space separated string) of syntaxes, in canonical names; `all` is all of them."""
    if value is True:
        return list(SYNTAXES)
    if value in (None, False):
        return []
    items = value if isinstance(value, (list, tuple)) else str(value).replace(",", " ").split()
    out: list[str] = []
    for item in items:
        name = str(item).strip().casefold()
        if name in ON:
            return list(SYNTAXES)
        if name in OFF:
            continue
        name = SYNTAX_ALIASES.get(name, name)
        if name not in SYNTAXES:
            raise RawError(f"{item!r} is not a raw syntax (tex, html, typst, office)")
        if name not in out:
            out.append(name)
    return out


def parse(value) -> dict[str, list[str]] | None:
    """The table {family: [syntaxes]} an option value asks for, or None when it asks for nothing."""
    if value is None or value is False:
        return None
    if isinstance(value, str) and value.strip().casefold() in OFF:
        return None
    if isinstance(value, dict):
        table: dict[str, list[str]] = {}
        default = None
        for key, listing in value.items():
            name = str(key).strip().casefold()
            if name in ("default", "others", "rest"):
                default = syntaxes(listing)
                continue
            family = FAMILY_ALIASES.get(name, name)
            if family not in FAMILIES:
                raise RawError(f"{key!r} is not an output family (tex, typst, html, office, md)")
            table[family] = syntaxes(listing)
        if default is not None:
            for family in FAMILIES:
                table.setdefault(family, default)
        return table or None
    every = syntaxes(value)
    return {family: list(every) for family in FAMILIES}


def merge(table: dict[str, list[str]] | None, family: str, listing: list[str]) -> dict[str, list[str]]:
    """`table` with `family` set to `listing` (a new table: the start of one when there is none)."""
    out = dict(table or {})
    out[FAMILY_ALIASES.get(family.strip().casefold(), family.strip().casefold())] = listing
    for name in out:
        if name not in FAMILIES:
            raise RawError(f"{name!r} is not an output family (tex, typst, html, office, md)")
    return out
