"""Draw PDF pages as picture files or a multipage TIFF or PostScript file."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import CropError, ghostscript, rendering, tools

KINDS = ("png", "jpg", "tiff", "eps", "ps", "svg")
ONE_FILE = ("tiff", "ps")   # formats that hold all the pages in one file
DEFAULT_DPI = 300   # pixels per inch of a PNG or JPEG; `--image-dpi`
DEFAULT_QUALITY = 90   # JPEG quality, 1-100; `--image-quality`


def _pages(pdf: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise CropError("Picture exports need pypdf (pip install pypdf)") from error
    try:
        count = len(PdfReader(str(pdf)).pages)
    except Exception as error:  # pypdf raises several errors for unreadable PDFs
        raise CropError(f"{pdf.name} is not a readable PDF ({error})") from error
    if not count:
        raise CropError(f"{pdf.name} has no pages")
    return count


def pictures(pdf: Path, target: Path, kind: str, dpi: float = DEFAULT_DPI, quality: int = DEFAULT_QUALITY,
             folder: bool = True) -> list[Path]:
    """Draw every page of `pdf` as `kind` ("png", "jpg" or "svg"). One page is written to `target`; several go into a folder
    named like `target` without its suffix, as `001.png`, `002.png`... (zero-padded so they sort); with `folder` off
    they are written beside it as `NAME-001.png`... Returns the files written. Raises CropError."""
    if kind not in KINDS:
        raise CropError(f"cannot draw a PDF as {kind}: {', '.join(KINDS)} only")
    if dpi <= 0:
        raise CropError("--image-dpi takes a number above 0")
    if not 1 <= quality <= 100:
        raise CropError("--image-quality takes a number from 1 to 100")
    count = _pages(pdf)
    width = max(3, len(str(count)))
    folder_of_pages = target.with_suffix("")
    if count == 1 or kind in ONE_FILE:
        names = [target]
    elif folder:
        names = [folder_of_pages / f"{number:0{width}d}{target.suffix}" for number in range(1, count + 1)]
    else:
        names = [target.with_name(f"{target.stem}-{number:0{width}d}{target.suffix}") for number in range(1, count + 1)]
    with tempfile.TemporaryDirectory(prefix="pdfmd-pictures-") as scratch:
        work = Path(scratch)
        if kind in ("tiff", "eps", "ps"):
            gs = ghostscript()
            if gs is None:
                raise CropError(f"--to {kind} needs Ghostscript (brew install ghostscript, apt install ghostscript)")
            device = {"tiff": ["-sDEVICE=tiff24nc", "-sCompression=lzw", f"-r{dpi:g}"], "eps": ["-sDEVICE=eps2write"],
                      "ps": ["-sDEVICE=ps2write"]}[kind]
            pattern = "pages." + kind if kind in ONE_FILE else "page-%d." + kind
            done = tools.run([gs, "-q", "-dBATCH", "-dNOPAUSE", "-dUseCropBox", *device, f"-sOutputFile={work / pattern}", str(pdf)])
            made = [work / pattern] if kind in ONE_FILE else [work / f"page-{number}.{kind}" for number in range(1, count + 1)]
            if done.returncode != 0 or not all(path.is_file() for path in made):
                detail = (done.stderr.strip().splitlines() or ["no picture was made"])[-1]
                raise CropError(f"could not draw {pdf.name} as {kind}: {detail}")
        else:
            gs = ghostscript()
            made = [work / f"page-{number}.{kind}" for number in range(1, count + 1)]
            for number, path in enumerate(made, 1):
                if kind == "png":
                    rendering.png(pdf, path, number, dpi, gs)
                elif kind == "svg":
                    rendering.svg(pdf, path, number, gs)
                else:
                    if gs is None:
                        raise CropError("--to jpg needs Ghostscript (brew install ghostscript, apt install ghostscript)")
                    rendering.gs_page(gs, pdf, path, number, "jpeg", f"-dJPEGQ={quality}",
                                      "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4", f"-r{dpi:g}")
        for source, name in zip(made, names):
            try:
                name.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(name))
            except OSError as error:
                raise CropError(f"could not write {name}: {error}") from error
    return names
