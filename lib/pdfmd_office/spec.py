"""What a document asks of its Word/ODF page and fonts, read from its (merged) metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .fonts import office_font
from .units import PAPER_TWIPS, SIDES, length_to_twips, parse_geometry, parse_paper


@dataclass
class OfficeSpec:
    paper: tuple[int, int] | None = None        # (width, height) twips, portrait
    landscape: bool = False
    margins: dict[str, int] = field(default_factory=dict)
    main: str | None = None
    sans: str | None = None
    mono: str | None = None
    cjk: str | None = None
    size: float | None = None                   # points
    stretch: float | None = None                # line spacing factor
    lang: str | None = None
    indent: bool = False
    house: bool = True                          # pdfmd's own look (black headings, centred title...)
    aliases: dict[str, str] = field(default_factory=dict)   # Pandoc style -> the template's style it should look like
    replace: dict[str, str] = field(default_factory=dict)   # text of the template's headers and footers -> new text
    title_page: bool = False                    # a first page of its own: no header or footer on it
    media: dict[str, bytes] = field(default_factory=dict)   # picture of the template (zip path) -> new bytes
    notes: list[str] = field(default_factory=list)

    def has_page(self) -> bool:
        return bool(self.paper or self.margins or self.landscape)

    def has_text(self) -> bool:
        return any((self.main, self.sans, self.mono, self.cjk, self.size, self.stretch, self.lang, self.indent,
                    self.aliases, self.replace, self.title_page, self.media))

    def page_size(self) -> tuple[int, int]:
        width, height = self.paper or PAPER_TWIPS["letter"]
        return (height, width) if self.landscape else (width, height)

    def empty(self) -> bool:
        return not (self.has_page() or self.has_text())


def _first(meta: dict, *keys):
    for key in keys:
        if meta.get(key) not in (None, "", []):
            return meta[key]
    return None


def _points(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    twips = length_to_twips(value if re.search(r"[a-zA-Z]", str(value)) else f"{value}pt")
    return twips / 20 if twips else None


def spec_from_metadata(meta: dict, office: dict | None = None, font_policy: str = "safe") -> OfficeSpec:
    """`meta` is Pandoc's metadata as the document sees it (front matter, metadata files, -V); `office`
    the `pdfmd-options: {office: {...}}` block, which wins key by key and takes the same names
    (papersize, geometry, margin, fontsize, mainfont, sansfont, monofont, CJKmainfont, linestretch, lang)."""
    merged = dict(meta)
    for key, value in (office or {}).items():
        if key not in ("reference-doc", "fonts", "latex", "style", "profile", "styles", "labels", "replace", "title-page"):
            merged[key.replace("_", "-") if key != "CJKmainfont" else key] = value
    spec = OfficeSpec()
    styles = (office or {}).get("styles")
    if isinstance(styles, dict):
        spec.aliases = {str(target): str(source) for target, source in styles.items() if source}
    spec.title_page = str((office or {}).get("title-page", "")).strip().lower() in ("true", "yes", "on", "1")
    texts = (office or {}).get("replace")
    if isinstance(texts, dict):
        spec.replace = {str(old): str(new) for old, new in texts.items()}
    paper = _first(merged, "papersize", "pagesize")
    classoption = merged.get("classoption")
    options = classoption if isinstance(classoption, list) else ([classoption] if classoption else [])
    size, landscape = parse_paper([paper, *options] if paper else options)
    geometry = parse_geometry(_first(merged, "geometry"))
    margin = merged.get("margin")
    margins = dict(geometry["margins"])
    if margin not in (None, ""):
        from_margin = parse_geometry({"margin": margin} if not isinstance(margin, dict) else margin)["margins"]
        for side, value in from_margin.items():
            margins.setdefault(side, value)
    spec.paper = geometry["paper"] or size
    spec.landscape = bool(landscape or geometry["landscape"])
    spec.margins = {side: margins[side] for side in SIDES if side in margins}
    spec.size = _points(merged.get("fontsize"))
    stretch = merged.get("linestretch")
    try:
        spec.stretch = float(stretch) if stretch not in (None, "") else None
    except (TypeError, ValueError):
        spec.stretch = None
    lang = merged.get("lang")
    spec.lang = str(lang) if isinstance(lang, (str,)) and lang.strip() else None
    spec.indent = str(merged.get("indent", "")).strip().lower() in ("true", "yes", "on", "1")
    for attribute, key, role in (("main", "mainfont", "main"), ("sans", "sansfont", "sans"),
                                 ("mono", "monofont", "mono"), ("cjk", "CJKmainfont", "main")):
        name, note = office_font(merged.get(key) if isinstance(merged.get(key), str) else None, role, font_policy)
        setattr(spec, attribute, name)
        if note:
            spec.notes.append(note)
    return spec
