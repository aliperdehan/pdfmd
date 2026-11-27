"""Measure PDF ink in displayed coordinates, relative to the crop box."""

from __future__ import annotations

import re
import struct
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfmd_crop import Box, CropError
from pdfmd_crop import tools

# Sample at eqpop's original measurement scale of four pixels per point.
# Output image-dpi is independent of the resolution used to measure ink.
INK_DPI = 4 * 72

_GS_BOX = re.compile(r"%%HiResBoundingBox:\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)")
_MU_BOX = re.compile(r'<page bbox="([^"]+)" mediabox="([^"]+)"')


def _box(values) -> Box | None:
    left, bottom, right, top = values
    return (left, bottom, right, top) if left < right and bottom < top else None


def gs_boxes(gs, pdf, page):
    selected = [] if page is None else [f"-dFirstPage={page}", f"-dLastPage={page}"]
    done = tools.run([gs, "-q", "-dBATCH", "-dNOPAUSE", "-dUseCropBox", "-sDEVICE=bbox", *selected, str(pdf)])
    if done.returncode:
        raise CropError((done.stderr.strip().splitlines() or ["no bounding boxes"])[-1])
    return [_box(tuple(map(float, match.groups()))) for match in _GS_BOX.finditer(done.stderr)]


def mu_boxes(mupdf, pdf, page):
    selected = [] if page is None else [str(page)]
    done = tools.run([mupdf, "draw", "-q", "-F", "bbox", str(pdf), *selected])
    if done.returncode:
        raise CropError((done.stderr.strip().splitlines() or ["no bounding boxes"])[-1])
    boxes = []
    for match in _MU_BOX.finditer(done.stdout):
        left, top, right, bottom = map(float, match[1].split())
        x0, y0, _, y1 = map(float, match[2].split())
        boxes.append(_box((left - x0, y1 - bottom, right - x0, y1 - top)) if y1 > y0 else None)
    return boxes


def png_alpha(path: Path) -> tuple[int, int, bytes]:
    """Read the 8-bit RGBA PNG that pdftocairo writes with -transp."""
    from pypdf.filters import FlateDecode
    from pypdf.generic import DictionaryObject, NameObject, NumberObject

    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[24:29] != b"\x08\x06\x00\x00\x00":
        raise CropError("pdftocairo did not write an 8-bit RGBA image")
    width, height = struct.unpack_from(">II", raw, 16)
    offset, chunks = 8, []
    while offset + 12 <= len(raw):
        size, kind = struct.unpack_from(">I4s", raw, offset)
        if kind == b"IDAT":
            chunks.append(raw[offset + 8:offset + 8 + size])
        offset += size + 12
    parameters = DictionaryObject({NameObject("/" + name): NumberObject(value) for name, value in
                                   (("Predictor", 15), ("Columns", width), ("Colors", 4), ("BitsPerComponent", 8))})
    pixels = FlateDecode.decode(b"".join(chunks), parameters)
    if len(pixels) != width * height * 4:
        raise CropError("pdftocairo wrote an incomplete RGBA image")
    return width, height, pixels[3::4]


def raster_pixels(name: str, executable: str, pdf: Path, path: Path, page: int) -> tuple[int, int, bytes]:
    from pdfmd_crop.rendering import cairo_png, page_args, pnm

    if name == "pdftoppm":
        pgm = path.with_suffix(".pgm")
        tools.checked([executable, "-gray", "-cropbox", "-singlefile", "-r", str(INK_DPI),
                       *page_args(page), str(pdf), str(path)], pgm)
        width, height, pixels = pnm(pgm, b"P5")
        return width, height, pixels.translate(bytes(reversed(range(256))))
    if name == "pdftocairo":
        png = path.with_suffix(".png")
        cairo_png(executable, pdf, png, page, INK_DPI)
        return png_alpha(png)
    pam = path.with_suffix(".pam")
    tools.checked([executable, "draw", "-q", "-F", "pam", "-c", "rgba", "-r", str(INK_DPI),
                   "-o", str(pam), str(pdf), str(page)], pam)
    header, sep, pixels = pam.read_bytes().partition(b"ENDHDR\n")
    width = re.search(rb"(?m)^WIDTH (\d+)$", header)
    height = re.search(rb"(?m)^HEIGHT (\d+)$", header)
    if not (sep and width and height and b"TUPLTYPE RGB_ALPHA" in header and b"MAXVAL 255" in header):
        raise CropError("MuPDF did not write an 8-bit RGBA image")
    return int(width[1]), int(height[1]), pixels[3::4]


def scan(width: int, height: int, ink: bytes, page_height: float) -> Box | None:
    if len(ink) != width * height:
        raise CropError("renderer wrote incomplete pixels")
    left, right, first, last = width, 0, height, 0
    for row in range(height):
        line = ink[row * width:(row + 1) * width]
        if mark := line.lstrip(b"\x00"):
            left = min(left, width - len(mark))
            right = max(right, len(line.rstrip(b"\x00")))
            first = min(first, row)
            last = row + 1
    scale = 72 / INK_DPI
    return _box((left * scale, page_height - last * scale, right * scale, page_height - first * scale))


def raster_boxes(name, executable, pdf, page):
    from pypdf import PdfReader

    with TemporaryDirectory(prefix="pdfmd-ink-") as scratch:
        path = Path(scratch) / "page"
        boxes = []
        pages = PdfReader(str(pdf)).pages
        for number in range(1, len(pages) + 1) if page is None else (page,):
            width, height, ink = raster_pixels(name, executable, pdf, path, number)
            rendered = pages[number - 1]
            area = rendered.cropbox
            page_height = float(area.width if rendered.rotation % 180 else area.height) * float(rendered.user_unit)
            boxes.append(scan(width, height, ink, page_height))
    return boxes


def measure(pdf: Path, pages: int | None, gs: str | None, *, page: int | None) -> list[Box | None]:
    mupdf = tools.find("mutool")
    failures = []

    def accept(boxes):
        if not boxes or (pages is not None and len(boxes) != pages):
            raise CropError("unexpected number of bounding boxes")
        return boxes

    for executable, run in ((gs, gs_boxes), (mupdf, mu_boxes)):
        if executable:
            try:
                return accept(run(executable, pdf, page))
            except (CropError, ValueError) as error:
                failures.append(str(error))
    for name in ("pdftoppm", "pdftocairo", "mutool"):
        if executable := tools.find(name):
            try:
                return accept(raster_boxes(name, executable, pdf, page))
            except (CropError, OSError, ImportError, ValueError) as error:
                failures.append(f"{name}: {error}")
    hint = "install Ghostscript, MuPDF or Poppler"
    detail = "; ".join(failures)
    raise CropError(f"could not measure {pdf.name} with " + " -> ".join(tools.INK_CHAIN)
                    + (f" ({detail})" if detail else f"; {hint}"))
