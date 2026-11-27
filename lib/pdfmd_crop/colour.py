"""Picture backgrounds and WebP encoding."""

from __future__ import annotations

import re
from pathlib import Path

from pdfmd_crop import CropError
from pdfmd_crop import tools

# The basic HTML colour names remain available with the optional libraries
# absent. Pillow, when present, also resolves other named CSS colours.
_BASIC = {
    "aqua": "00ffff", "black": "000000", "blue": "0000ff", "fuchsia": "ff00ff",
    "gray": "808080", "grey": "808080", "green": "008000", "lime": "00ff00",
    "maroon": "800000", "navy": "000080", "olive": "808000", "orange": "ffa500",
    "purple": "800080", "red": "ff0000", "silver": "c0c0c0", "teal": "008080",
    "white": "ffffff", "yellow": "ffff00",
}
_HEX = re.compile(r"#[0-9a-f]{3}(?:[0-9a-f]{3})?")


def colour_for(value) -> tuple[int, int, int] | None:
    if value is None:
        return None
    colour = str(value).strip().casefold()
    if colour == "transparent":
        return None
    if colour in _BASIC or _HEX.fullmatch(colour):
        raw = _BASIC.get(colour, colour[1:])
        if len(raw) == 3:
            raw = "".join(item * 2 for item in raw)
        return tuple(bytes.fromhex(raw))
    if tools.optional("PIL"):
        try:
            from PIL import ImageColor
            rgb = ImageColor.getrgb(colour)
            if len(rgb) == 3:
                return rgb
        except (ImportError, ValueError):
            pass
    raise CropError(f"--image-background / pdfmd-options.image-background: {value!r} must be an opaque colour or 'transparent'")


def matte(pdf: Path, target: Path, colour: tuple[int, int, int]) -> None:
    """Paint a background in PDF coordinates before rasterising or exporting SVG."""
    from pypdf import PdfReader, PdfWriter
    from pdfmd_crop.rendering import paint_behind

    writer = PdfWriter()
    for page in PdfReader(str(pdf)).pages:
        paint_behind(writer.add_page(page), colour)
    writer.write(str(target))


def webp(png: Path, output: Path, quality: int) -> None:
    failures = []
    if tools.optional("PIL"):
        try:
            from PIL import Image
            with Image.open(png) as image:
                image.save(output, format="WEBP", quality=quality)
            return
        except (ImportError, KeyError, OSError, ValueError) as error:
            failures.append(f"Pillow: {error}")
    if magick := tools.find("magick"):
        try:
            tools.checked([magick, str(png), "-quality", str(quality), str(output)], output)
            return
        except CropError as error:
            failures.append(f"ImageMagick: {error}")
    raise CropError("WebP export needs Pillow or ImageMagick with WebP support"
                    + (" (" + "; ".join(failures) + ")" if failures else ""))
