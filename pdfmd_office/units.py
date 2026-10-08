"""Lengths, paper sizes and the LaTeX `geometry` / `papersize` / `margin` spellings, in twips
(1/20 point, Word's unit: 1440 per inch)."""

from __future__ import annotations

import re

TWIPS_PER_INCH = 1440
_UNITS = {"in": 1440.0, "cm": 1440 / 2.54, "mm": 144 / 2.54, "pt": 20.0, "bp": 20.0 * 72.27 / 72, "pc": 240.0,
          "dd": 20.0 * 1238 / 1157, "cc": 240.0 * 1238 / 1157, "sp": 20.0 / 65536, "px": 15.0,
          "em": 240.0, "ex": 120.0}
_LENGTH = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([a-zA-Z]*)\s*$")

# paper name -> (width, height) in twips, portrait
PAPER_TWIPS = {
    "letter": (12240, 15840), "legal": (12240, 20160), "executive": (10440, 15120), "tabloid": (15840, 24480),
    "ledger": (24480, 15840), "a0": (47780, 67559), "a1": (33780, 47780), "a2": (23811, 33780),
    "a3": (16838, 23811), "a4": (11906, 16838), "a5": (8391, 11906), "a6": (5953, 8391),
    "b4": (14173, 20013), "b5": (9979, 14173), "b6": (7087, 9979), "c4": (12983, 18369), "c5": (9185, 12983),
    "folio": (12240, 18720), "quarto": (12240, 15840),
}
PAPER_ALIASES = {"us-letter": "letter", "usletter": "letter", "us-legal": "legal", "uslegal": "legal",
                 "letterpaper": "letter", "legalpaper": "legal", "executivepaper": "executive"}
SIDES = ("top", "bottom", "left", "right")


def length_to_twips(value) -> int | None:
    """'2.54cm', '1in', '12pt', 1.5 (inches, like a bare LaTeX number would not be: taken as points
    only with a unit; a bare number is inches) -> twips; None if it is not a length."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value) * TWIPS_PER_INCH)
    match = _LENGTH.match(str(value).replace("true", ""))
    if not match:
        return None
    unit = match.group(2).lower() or "in"
    if unit not in _UNITS:
        return None
    return round(float(match.group(1)) * _UNITS[unit])


def parse_paper(value) -> tuple[tuple[int, int] | None, bool]:
    """`a4`, `letter`, `a4paper`, `landscape`... or 'a4,landscape' -> ((width, height) | None, landscape)."""
    if isinstance(value, (list, tuple)):
        words = [str(item) for item in value]
    else:
        words = [part for part in re.split(r"[,\s]+", str(value or "")) if part]
    size, landscape = None, False
    for word in words:
        name = word.strip().lower()
        if name == "landscape":
            landscape = True
            continue
        name = PAPER_ALIASES.get(name, name)
        name = name[:-5] if name.endswith("paper") and name[:-5] in PAPER_TWIPS else name
        if name in PAPER_TWIPS:
            size = PAPER_TWIPS[name]
    return size, landscape


def parse_geometry(value) -> dict:
    """Read a `geometry:` value (a string, a comma-joined string, a list of `key=value`, or a mapping)
    or a `margin:` mapping into {'margins': {top,bottom,left,right: twips}, 'paper': (w, h)|None,
    'landscape': bool}. Keys that are not about the page (includehead, showframe...) are ignored."""
    items: list[str] = []
    if isinstance(value, dict):
        items = [f"{key}={item}" for key, item in value.items()]
    elif isinstance(value, (list, tuple)):
        for entry in value:
            items += [f"{key}={item}" for key, item in entry.items()] if isinstance(entry, dict) else str(entry).split(",")
    elif value is not None:
        items = str(value).split(",")
    margins: dict[str, int] = {}
    paper = None
    paper_w = paper_h = None
    landscape = False
    for raw in items:
        raw = raw.strip()
        if not raw:
            continue
        key, sep, rest = raw.partition("=")
        key = key.strip().lower()
        if not sep:
            size, land = parse_paper(key)
            paper = size or paper
            landscape = landscape or land
            continue
        twips = length_to_twips(rest.strip().strip("{}"))
        if key == "margin" and twips is not None:
            for side in SIDES:
                margins[side] = twips
        elif key in ("hmargin", "x") and twips is not None:
            margins["left"] = margins["right"] = twips
        elif key in ("vmargin", "y") and twips is not None:
            margins["top"] = margins["bottom"] = twips
        elif key in ("left", "lmargin", "inner") and twips is not None:
            margins["left"] = twips
        elif key in ("right", "rmargin", "outer") and twips is not None:
            margins["right"] = twips
        elif key in ("top", "tmargin") and twips is not None:
            margins["top"] = twips
        elif key in ("bottom", "bmargin") and twips is not None:
            margins["bottom"] = twips
        elif key == "paperwidth" and twips is not None:
            paper_w = twips
        elif key == "paperheight" and twips is not None:
            paper_h = twips
        elif key in ("paper", "papersize"):
            size, land = parse_paper(rest)
            paper = size or paper
            landscape = landscape or land
        elif key == "landscape":
            landscape = rest.strip().lower() not in ("false", "no", "0")
    if paper_w and paper_h:
        paper = (paper_w, paper_h)
    return {"margins": margins, "paper": paper, "landscape": landscape}
