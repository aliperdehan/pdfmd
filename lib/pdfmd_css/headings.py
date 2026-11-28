"""CSS heading properties shared by the Word and Typst writers."""

from __future__ import annotations

import math
import re

from . import first_family, length_points, translate
from .latex import CSS_COLOURS, css_scope, css_sources


def stylesheet_headings(document, metadata_files, no_auto, pandoc_options=()):
    if css_scope(document, metadata_files) != "all":
        return {}
    sheets = dict.fromkeys(path for group in css_sources(document, metadata_files, no_auto, pandoc_options) for path in group)
    return translate("\n".join(path.read_text(encoding="utf-8", errors="replace") for path in sheets)).headings


def heading_values(rule: dict[str, str], base: float) -> dict:
    values = {}
    colour = rule.get("color", "").lower()
    if re.fullmatch(r"#[0-9a-f]{3}", colour):
        values["colour"] = "".join(digit * 2 for digit in colour[1:]).upper()
    elif re.fullmatch(r"#[0-9a-f]{6}", colour):
        values["colour"] = colour[1:].upper()
    elif colour in CSS_COLOURS:
        values["colour"] = CSS_COLOURS[colour]
    size = rule.get("font-size", "").lower()
    points = length_points(size)
    relative = re.fullmatch(r"(\d*\.?\d+)(em|rem|%)", size)
    if relative:
        points = float(relative[1]) * base / (100 if relative[2] == "%" else 1)
    if points is not None and math.isfinite(points) and points > 0:
        values["size"] = points
    family = first_family(rule.get("font-family", ""))
    if family and family.isprintable():
        values["font"] = family
    weight = rule.get("font-weight", "").lower()
    if weight in ("bold", "bolder", "normal", "lighter") or weight.isascii() and weight.isdigit():
        values["bold"] = weight in ("bold", "bolder") or (weight.isascii() and weight.isdigit() and float(weight) >= 600)
    style = rule.get("font-style", "").lower()
    if style in ("normal", "italic", "oblique"):
        values["italic"] = style != "normal"
    return values
