"""A PDF as pictures: one PNG or SVG per page (`pdfmd --to png|svg`, v3.31.21).

PNG is drawn by Ghostscript's `pngalpha` device (a transparent background, the page's crop box as the picture's edge);
SVG by poppler's `pdftocairo`, else MuPDF's `mutool`. Text stays text in the SVG only as far as those tools keep it.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import CropError, ghostscript

DEFAULT_DPI = 300   # pixels per inch of a PNG; `--image-dpi`


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")


def _pages(pdf: Path) -> int:
    from pypdf import PdfReader
    return len(PdfReader(str(pdf)).pages)


def pictures(pdf: Path, target: Path, kind: str, dpi: float = DEFAULT_DPI) -> list[Path]:
    """Draw every page of `pdf` as `kind` ("png" or "svg"). One page is written to `target`; several to `target` with
    `-1`, `-2`... before the suffix. Returns the files written. Raises CropError."""
    if kind not in ("png", "svg"):
        raise CropError(f"cannot draw a PDF as {kind}: png and svg only")
    if dpi <= 0:
        raise CropError("--image-dpi takes a number above 0")
    count = _pages(pdf)
    names = [target] if count == 1 else [target.with_name(f"{target.stem}-{number}{target.suffix}") for number in range(1, count + 1)]
    with tempfile.TemporaryDirectory(prefix="pdfmd-pictures-") as scratch:
        folder = Path(scratch)
        if kind == "png":
            gs = ghostscript()
            if gs is None:
                raise CropError("--to png needs Ghostscript (brew install ghostscript, apt install ghostscript)")
            done = _run([gs, "-q", "-dBATCH", "-dNOPAUSE", "-dUseCropBox", "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4",
                         "-sDEVICE=pngalpha", f"-r{dpi:g}", f"-sOutputFile={folder / 'page-%d.png'}", str(pdf)])
            made = [folder / f"page-{number}.png" for number in range(1, count + 1)]
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
                shutil.move(str(source), str(name))
            except OSError as error:
                raise CropError(f"could not write {name}: {error}") from error
    return names
