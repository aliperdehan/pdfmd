"""Crop a PDF to what it draws (`pdfmd --crop`, v3.31.20).

Only the page's boxes change; the PDF's contents stay vector. `crop_pdf`
does the whole job and `ink_boxes` measures the displayed page. A blank page
keeps its original boxes.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PAD = 2.0   # points of room around the ink; `--crop-pad`

Box = tuple[float, float, float, float]   # left, bottom, right, top, in points


class CropError(Exception):
    """Why nothing was cropped: the message is for the person at the command line."""


@dataclass
class Cropped:
    """What `crop_pdf` did: the number of pages in the source, and for each kept page its new box (None: nothing was
    drawn on it, so it is as it was)."""
    pages: int
    boxes: list[Box | None]


def ghostscript() -> str | None:
    from pdfmd_crop.tools import find

    return find("ghostscript")


def ink_boxes(pdf: Path, pages: int | None = None, *, page: int | None = None) -> list[Box | None]:
    """Ink boxes relative to the displayed crop box, or None for blank pages."""
    from pdfmd_crop.measure import measure

    return measure(pdf, pages, ghostscript(), page=page)


def _unrotate(box: Box, rotation: int, width: float, height: float) -> Box:
    """A box found on the displayed page, turned back into the page's unrotated coordinates (`width` x `height` is
    the unrotated page)."""
    left, bottom, right, top = box
    if rotation == 90:
        return (width - top, left, width - bottom, right)
    if rotation == 180:
        return (width - right, height - top, width - left, height - bottom)
    if rotation == 270:
        return (bottom, height - right, top, height - left)
    return box


def crop_pdf(source: Path, target: Path, *, pad: float = DEFAULT_PAD, ignore_bottom: float = 0.0,
             page: int | None = None) -> Cropped:
    """Write `source` to `target` with each page cut to its ink plus `pad` points (never beyond the page's own
    box). `ignore_bottom` points at the foot of every page are not looked at (a page number); `page` (counted from 1)
    keeps that page alone. Both the media box and the crop box are set, which is what Word, Keynote and the like read."""
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import RectangleObject
    except ImportError as error:
        raise CropError("--crop needs pypdf (pip install pypdf)") from error
    logger = logging.getLogger("pypdf")
    level = logger.level
    logger.setLevel(logging.CRITICAL)   # a file that is not a PDF is reported once, below, not also as pypdf's own lines
    try:
        reader = PdfReader(str(source))
        count = len(reader.pages)
    except Exception as error:   # pypdf raises its own and builtin errors for a file that is not a PDF
        raise CropError(f"{source.name} is not a readable PDF ({error})") from error
    finally:
        logger.setLevel(level)
    if count == 0:
        raise CropError(f"{source.name} has no pages")
    if page is not None and not 1 <= page <= count:
        raise CropError(f"{source.name} has {count} page{'' if count == 1 else 's'}, not a page {page}")
    if pad < 0 or ignore_bottom < 0:
        raise CropError("--crop-pad and --crop-ignore-bottom take a number of points of 0 or more")

    # the pages as Ghostscript should see them: each one's crop box without the strip at its foot
    probe = PdfWriter()
    for number in range(count):
        original = reader.pages[number]
        area = original.cropbox
        floor = float(area.bottom) + ignore_bottom
        if floor >= float(area.top):
            raise CropError(f"--crop-ignore-bottom {ignore_bottom:g} is the whole of page {number + 1} of {source.name}")
        original.cropbox = RectangleObject([float(area.left), floor, float(area.right), float(area.top)])
        probe.add_page(original)
    with tempfile.TemporaryDirectory(prefix="pdfmd-crop-") as scratch:
        measured = Path(scratch) / "measured.pdf"
        with open(measured, "wb") as handle:
            probe.write(handle)
        seen = ink_boxes(measured, count)

    # a fresh reader: the probe changed the crop boxes of the first one
    reader = PdfReader(str(source))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    result: list[Box | None] = []
    for number in range(count):
        if page is not None and number + 1 != page:
            continue
        target_page = writer.pages[number]
        area = target_page.cropbox
        left0, bottom0 = float(area.left), float(area.bottom)
        right0, top0 = float(area.right), float(area.top)
        ink = seen[number]
        if ink is None:
            result.append(None)
        else:
            rotation = int(getattr(target_page, "rotation", 0) or 0) % 360
            width, height = right0 - left0, top0 - bottom0
            # the probe's crop box began `ignore_bottom` above the page's own, and Ghostscript reports from its corner
            ink = _unrotate(ink, rotation, width, height - ignore_bottom)
            ink = (ink[0] + left0, ink[1] + bottom0 + ignore_bottom, ink[2] + left0, ink[3] + bottom0 + ignore_bottom)
            box = (max(ink[0] - pad, left0), max(ink[1] - pad, bottom0), min(ink[2] + pad, right0), min(ink[3] + pad, top0))
            rectangle = RectangleObject(list(box))
            target_page.mediabox = rectangle
            target_page.cropbox = rectangle
            for name in ("trimbox", "bleedbox", "artbox"):
                if f"/{name[:-3].capitalize()}Box" in target_page:
                    setattr(target_page, name, rectangle)
            result.append(box)
    if page is not None:
        for number in reversed(range(count)):
            if number + 1 != page:
                writer.remove_page(number, clean=True)
    # to a sibling file first, so a crop in place never leaves half a PDF
    partial = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name + ".", suffix=".part", delete=False) as handle:
            partial = Path(handle.name)
            writer.write(handle)
        partial.replace(target)
    except OSError as error:
        raise CropError(f"could not write {target}: {error}") from error
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
    return Cropped(count, result)
