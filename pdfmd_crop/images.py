"""A PDF as pictures: one PNG, JPEG or SVG per page (`pdfmd --to png|jpg|svg`, v3.31.21).

PNG is drawn by Ghostscript's `pngalpha` device (a transparent background, the page's crop box as the picture's edge),
JPEG by its `jpeg` device (white: a JPEG has no transparency); SVG by poppler's `pdftocairo`, else MuPDF's `mutool`. Text stays text in the SVG only as far as those tools keep it.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import CropError, ghostscript

DEFAULT_DPI = 300   # pixels per inch of a PNG or JPEG; `--image-dpi`
DEFAULT_QUALITY = 90   # JPEG quality, 1-100; `--image-quality`


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")


def _pages(pdf: Path) -> int:
    from pypdf import PdfReader
    return len(PdfReader(str(pdf)).pages)


def pictures(pdf: Path, target: Path, kind: str, dpi: float = DEFAULT_DPI, quality: int = DEFAULT_QUALITY) -> list[Path]:
    """Draw every page of `pdf` as `kind` ("png", "jpg" or "svg"). One page is written to `target`; several go into a folder
    named like `target` without its suffix, as `001.png`, `002.png`... (zero-padded so they sort). Returns the files
    written. Raises CropError."""
    if kind not in ("png", "jpg", "svg"):
        raise CropError(f"cannot draw a PDF as {kind}: png, jpg and svg only")
    if dpi <= 0:
        raise CropError("--image-dpi takes a number above 0")
    if not 1 <= quality <= 100:
        raise CropError("--image-quality takes a number from 1 to 100")
    count = _pages(pdf)
    width = max(3, len(str(count)))
    folder_of_pages = target.with_suffix("")
    names = [target] if count == 1 else [folder_of_pages / f"{number:0{width}d}{target.suffix}" for number in range(1, count + 1)]
    with tempfile.TemporaryDirectory(prefix="pdfmd-pictures-") as scratch:
        folder = Path(scratch)
        if kind in ("png", "jpg"):
            gs = ghostscript()
            if gs is None:
                raise CropError(f"--to {kind} needs Ghostscript (brew install ghostscript, apt install ghostscript)")
            device = ["-sDEVICE=pngalpha"] if kind == "png" else ["-sDEVICE=jpeg", f"-dJPEGQ={quality}"]
            done = _run([gs, "-q", "-dBATCH", "-dNOPAUSE", "-dUseCropBox", "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4",
                         *device, f"-r{dpi:g}", f"-sOutputFile={folder / ('page-%d.' + kind)}", str(pdf)])
            made = [folder / f"page-{number}.{kind}" for number in range(1, count + 1)]
        else:
            cairo, mupdf = shutil.which("pdftocairo"), shutil.which("mutool")
            if cairo is None and mupdf is None:
                raise CropError("--to svg needs poppler's pdftocairo or MuPDF's mutool (brew install poppler, or mupdf-tools)")
            made = []
            done = subprocess.CompletedProcess([], 0, "", "")
            for number in range(1, count + 1):
                one = folder / f"page-{number}.svg"
                if cairo is not None:
                    done = _run([cairo, "-svg", "-f", str(number), "-l", str(number), str(pdf), str(one)])
                else:
                    done = _run([mupdf, "convert", "-o", str(one), str(pdf), str(number)])
                if done.returncode != 0:
                    break
                made.append(one)
        if done.returncode != 0 or not all(path.is_file() for path in made):
            detail = (done.stderr.strip().splitlines() or ["no picture was made"])[-1]
            raise CropError(f"could not draw {pdf.name} as {kind}: {detail}")
        for source, name in zip(made, names):
            try:
                name.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(name))
            except OSError as error:
                raise CropError(f"could not write {name}: {error}") from error
    return names
