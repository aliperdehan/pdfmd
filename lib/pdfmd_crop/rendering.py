"""Individual PDF page renderers for the picture and ink measurement chains."""

from __future__ import annotations

import re
from pathlib import Path

from pdfmd_crop import CropError
from pdfmd_crop import tools


def page_args(page: int) -> list[str]:
    return ["-f", str(page), "-l", str(page)]


def gs_page(gs: str, pdf: Path, output: Path, page: int, device: str, *options: str) -> None:
    tools.checked([gs, "-q", "-dBATCH", "-dNOPAUSE", "-dUseCropBox", f"-sDEVICE={device}",
                   f"-dFirstPage={page}", f"-dLastPage={page}", *options, f"-sOutputFile={output}", str(pdf)], output)


def cairo_png(cairo: str, pdf: Path, output: Path, page: int, dpi: float) -> None:
    tools.checked([cairo, "-png", "-transp", "-cropbox", "-singlefile", "-r", f"{dpi:g}",
                   *page_args(page), str(pdf), str(output.with_suffix(""))], output)


def mupdf_png(mupdf: str, pdf: Path, output: Path, page: int, dpi: float) -> None:
    tools.checked([mupdf, "draw", "-q", "-F", "png", "-c", "rgba", "-r", f"{dpi:g}",
                   "-o", str(output), str(pdf), str(page)], output)


def pnm(path: Path, header: bytes) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    found = re.match(header + rb"\s+(\d+)\s+(\d+)\s+255(?:\r\n|\s)", data)
    if not found:
        raise CropError("Poppler did not write an 8-bit PNM image")
    width, height = map(int, found.groups())
    pixels = data[found.end():]
    if len(pixels) != width * height * (3 if header == b"P6" else 1):
        raise CropError("Poppler wrote an incomplete PNM image")
    return width, height, pixels


def paint_behind(page, colour: tuple[int, int, int]) -> None:
    """Place an opaque, crop-box-sized rectangle behind a PDF page."""
    from pypdf import PageObject
    from pypdf.generic import DecodedStreamObject, NameObject

    area = page.cropbox
    width, height = float(area.width), float(area.height)
    background = PageObject.create_blank_page(width=width, height=height)
    background.mediabox = background.cropbox = area
    stream = DecodedStreamObject()
    rgb = " ".join(f"{value / 255:.8f}" for value in colour)
    stream.set_data(f"{rgb} rg {float(area.left):f} {float(area.bottom):f} {width:f} {height:f} re f".encode("ascii"))
    background[NameObject("/Contents")] = stream
    page.merge_page(background, over=False)


def _single_pdf(pdf: Path, page: int, destination: Path, *, black: bool = False) -> tuple[float, float]:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    target = writer.add_page(PdfReader(str(pdf)).pages[page - 1])
    area = target.cropbox
    width, height = float(area.width), float(area.height)
    if black:
        paint_behind(target, (0, 0, 0))
    else:
        target.mediabox = area
    writer.write(str(destination))
    return (height, width) if target.rotation % 180 else (width, height)


def ppm_png(ppm: str, pdf: Path, output: Path, page: int, dpi: float) -> None:
    """Recover alpha from Poppler's renders on white and black mattes."""
    from pdfmd_pdfimages import encode_png

    black = output.with_name("black.pdf")
    _single_pdf(pdf, page, black, black=True)

    def render(source, index, name):
        prefix = output.with_name(name)
        pixels = prefix.with_suffix(".ppm")
        tools.checked([ppm, "-cropbox", "-singlefile", "-r", f"{dpi:g}", *page_args(index),
                       str(source), str(prefix)], pixels)
        return pnm(pixels, b"P6")

    width, height, lighter = render(pdf, page, "white-matte")
    dark_width, dark_height, darker = render(black, 1, "black-matte")
    if (width, height) != (dark_width, dark_height):
        raise CropError("Poppler rendered different sizes on the two mattes")
    pixels = bytearray(width * height * 4)
    for index in range(width * height):
        offset = index * 3
        channels = darker[offset:offset + 3]
        alpha = min(255, 255 - max(lighter[offset + j] - channel for j, channel in enumerate(channels)))
        if alpha:
            pixels[index * 4:index * 4 + 4] = bytes([*(min(255, round(255 * channel / alpha)) for channel in channels), alpha])
    output.write_bytes(encode_png(width, height, 8, 6, pixels))


def sips_png(sips: str, pdf: Path, output: Path, page: int, dpi: float) -> None:
    single = output.with_name(f"sips-{page}.pdf")
    width, height = _single_pdf(pdf, page, single)
    tools.checked([sips, "-s", "format", "png", "-s", "dpiWidth", f"{dpi:g}", "-s", "dpiHeight", f"{dpi:g}",
                   "-z", str(max(1, round(height * dpi / 72))), str(max(1, round(width * dpi / 72))),
                   str(single), "--out", str(output)], output)


def pdfium_png(pdf: Path, output: Path, page: int, dpi: float) -> None:
    import pypdfium2

    try:
        with pypdfium2.PdfDocument(str(pdf)) as document:
            source = document[page - 1]
            bitmap = source.render(scale=dpi / 72, fill_color=(0, 0, 0, 0), force_bitmap_format=pypdfium2.raw.FPDFBitmap_BGRA)
            bitmap.to_pil().save(output, dpi=(dpi, dpi))
    except (pypdfium2.PdfiumError, OSError, ValueError) as error:
        raise CropError(str(error)) from error


def png(pdf: Path, output: Path, page: int, dpi: float, gs: str | None) -> None:
    failures = []
    if gs:
        try:
            gs_page(gs, pdf, output, page, "pngalpha", "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4", f"-r{dpi:g}")
            return
        except CropError as error:
            failures.append(f"Ghostscript: {error}")
    for name, render in (("pdftocairo", cairo_png), ("mutool", mupdf_png), ("pdftoppm", ppm_png), ("sips", sips_png)):
        if executable := tools.find(name):
            try:
                render(executable, pdf, output, page, dpi)
                return
            except (CropError, OSError) as error:
                failures.append(f"{name}: {error}")
    if tools.optional("pypdfium2") and tools.optional("PIL"):
        try:
            pdfium_png(pdf, output, page, dpi)
            return
        except (CropError, ImportError) as error:
            failures.append(f"pypdfium2: {error}")
    raise CropError("could not draw PNG with " + " -> ".join(tools.PNG_CHAIN)
                    + (" (" + "; ".join(failures) + ")" if failures else "; install Poppler, Ghostscript or MuPDF"))


def svg(pdf: Path, output: Path, page: int, gs: str | None) -> None:
    commands = []
    if cairo := tools.find("pdftocairo"):
        # SVG already uses the visible page box. Poppler accepts -cropbox
        # only for its raster output options.
        commands.append([cairo, "-svg", *page_args(page), str(pdf), str(output)])
    if mupdf := tools.find("mutool"):
        # The draw command expands %d to the real page number. With no
        # placeholder it may insert a page number into the output name.
        pattern = output.with_name("mupdf-page-%d.svg")
        mupdf_output = output.with_name(f"mupdf-page-{page}.svg")
        commands.append([mupdf, "draw", "-q", "-F", "svg", "-o", str(pattern), str(pdf), str(page)])
    failures = []
    for command in commands:
        produced = mupdf_output if command[1] == "draw" else output
        try:
            tools.checked(command, produced)
            if produced != output:
                produced.replace(output)
            return
        except CropError as error:
            failures.append(str(error))
    if gs:
        try:
            gs_page(gs, pdf, output, page, "svgwrite")
            return
        except CropError as error:
            failures.append(str(error))
    raise CropError("could not draw SVG with " + " -> ".join(tools.SVG_CHAIN)
                    + (" (" + "; ".join(failures) + ")" if failures else "; install Poppler or MuPDF"))
