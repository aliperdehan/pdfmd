"""``![[image.png|300]]``: Obsidian's way to show a picture, read as pdfmd's own image embed (v3.32.25).

A wikilink names a file, not a path: ``![[Pasted image 20260101.png]]`` is the picture of that name wherever it lies in the vault.
``|300`` sizes it to 300 pixels wide, ``|300x200`` to a width and a height; any other text after a ``|`` is the alt text (pdfmd
shows it as the caption of a picture alone in its paragraph).

``embed_images`` turns each one into ``![alt](path){width=...pt}``, which every Pandoc reader pdfmd uses takes. It does no file
lookup itself: the caller gives ``find``, a function from the name to a path (or None). Fenced code, inline code, math, the front
matter and HTML comments are not looked into. A name that is no picture (a note, a PDF) is left as it is: that is a later step.
"""

from __future__ import annotations

import re
from typing import Callable, NamedTuple
from urllib.parse import quote

from .comments import _PROTECTED

# The picture formats a writer can place: a file-format fact, not a threshold.
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".avif", ".tif", ".tiff")

_EMBED = r"(?P<embed>!\[\[(?P<name>[^\[\]|#\n]+?)(?:#[^\[\]|\n]*)?(?:\|(?P<options>[^\[\]\n]*))?\]\])"
_SCAN = re.compile(_PROTECTED + "|" + _EMBED, re.DOTALL | re.MULTILINE)
_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:x\s*(\d+(?:\.\d+)?))?\s*$")


class Embeds(NamedTuple):
    text: str                       # the note, each picture embed written as a Markdown image
    count: int                      # how many were turned into images
    missing: list[tuple[int, str]]  # (line, name) of each picture `find` did not find


def _number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def embed_images(text: str, find: Callable[[str], str | None], px_to_pt: float = 0.75, fit: str = "text-width") -> Embeds:
    """``text`` with each ``![[picture|size]]`` written as ``![alt](path){width=Npt}``; ``find(name)`` gives the path to write (it
    is percent-encoded here) or None, which leaves a visible ``[missing image: name]`` and is reported. ``px_to_pt`` converts the
    pixels of ``|300``; with ``fit`` = ``text-width`` the image carries ``data-pdfmd-fit`` so the LaTeX build keeps it within the
    text width (a picture without a size is fitted by Pandoc already)."""
    missing: list[tuple[int, str]] = []
    count = 0

    def replace(match: re.Match) -> str:
        nonlocal count
        if match.lastgroup != "embed":
            return match.group(0)
        name = match.group("name").strip()
        if not name.lower().endswith(IMAGE_SUFFIXES):
            return match.group(0)
        options = (match.group("options") or "").split("|")
        size = _SIZE.match(options[-1]) if options and options[-1].strip() else None
        alt = "|".join(options[:-1] if size else options).strip()
        path = find(name)
        if path is None:
            missing.append((text.count("\n", 0, match.start()) + 1, name))
            return f"**[missing image: {name}]**"
        count += 1
        attributes = []
        if size:
            attributes.append(f"width={_number(float(size.group(1)) * px_to_pt)}pt")
            if size.group(2):
                attributes.append(f"height={_number(float(size.group(2)) * px_to_pt)}pt")
            if fit == "text-width":
                attributes.append('data-pdfmd-fit="text-width"')
        alt = alt.replace("[", "\\[").replace("]", "\\]")
        return f"![{alt}]({quote(path, safe='/:._-~')})" + ("{" + " ".join(attributes) + "}" if attributes else "")

    return Embeds(_SCAN.sub(replace, text), count, missing)
