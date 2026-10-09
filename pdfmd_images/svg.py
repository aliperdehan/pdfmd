"""SVG to PDF for LaTeX, with whichever converter is installed."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

CONVERTERS = ("rsvg-convert", "inkscape", "cairosvg", "svglib", "soffice")
HINTS = ("brew install librsvg  |  apt install librsvg2-bin  |  pip install cairosvg  |  Inkscape or LibreOffice")


def install_hint() -> str:
    return HINTS


def _python_module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


def available_converters(which: Callable[[str], str | None] = shutil.which,
                         soffice: Callable[[], str | None] = lambda: None) -> list[str]:
    """The converters installed, best first."""
    found = []
    for name in CONVERTERS:
        if name in ("rsvg-convert", "inkscape") and which(name):
            found.append(name)
        elif name == "cairosvg" and _python_module("cairosvg"):
            found.append(name)
        elif name == "svglib" and _python_module("svglib") and _python_module("reportlab"):
            found.append(name)
        elif name == "soffice" and soffice():
            found.append(name)
    return found


def cache_name(svg: Path) -> str:
    """The file name of the PDF for this SVG: by its content, so an edited file converts again and two files with the
    same drawing share one PDF."""
    digest = hashlib.sha256(svg.read_bytes()).hexdigest()[:20]
    return f"{svg.stem[:40]}-{digest}.pdf"


def convert_svg(svg: Path, cache: Path, which: Callable[[str], str | None] = shutil.which,
                soffice: Callable[[], str | None] = lambda: None) -> tuple[Path | None, str]:
    """(the PDF in `cache`, "") or (None, why not). A conversion made before is reused."""
    target = cache / cache_name(svg)
    if target.is_file() and target.stat().st_size > 0:
        return target, ""
    converters = available_converters(which, soffice)
    if not converters:
        return None, "no SVG converter found (" + HINTS + ")"
    cache.mkdir(parents=True, exist_ok=True)
    reasons = []
    for name in converters:
        scratch = Path(tempfile.mkdtemp(prefix="pdfmd-svg-"))
        try:
            produced = scratch / "out.pdf"
            ok, reason = _run(name, svg, produced, scratch, which, soffice)
            if ok and produced.is_file() and produced.stat().st_size > 0:
                partial = target.with_suffix(".part")
                shutil.copyfile(produced, partial)
                partial.replace(target)
                return target, ""
            reasons.append(f"{name}: {reason}")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    return None, "; ".join(reasons)


def _run(name: str, svg: Path, produced: Path, scratch: Path, which, soffice) -> tuple[bool, str]:
    try:
        if name == "rsvg-convert":
            command = [which("rsvg-convert"), "-f", "pdf", "-o", str(produced), str(svg)]
        elif name == "inkscape":
            command = [which("inkscape"), str(svg), "--export-type=pdf", f"--export-filename={produced}"]
        elif name == "cairosvg":
            import cairosvg
            cairosvg.svg2pdf(url=str(svg), write_to=str(produced))
            return True, ""
        elif name == "svglib":
            from reportlab.graphics import renderPDF
            from svglib.svglib import svg2rlg
            drawing = svg2rlg(str(svg))
            if drawing is None:
                return False, "could not read the drawing"
            renderPDF.drawToFile(drawing, str(produced))
            return True, ""
        else:                                                     # soffice: Draw sizes the page to the drawing
            profile = scratch / "profile"
            command = [soffice(), "--headless", "--norestore", f"-env:UserInstallation=file://{profile}",
                       "--convert-to", "pdf", "--outdir", str(scratch), str(svg)]
            done = subprocess.run(command, capture_output=True, text=True, timeout=120)
            made = scratch / f"{svg.stem}.pdf"
            if made.is_file():
                made.replace(produced)
                return True, ""
            return False, (done.stderr.strip() or done.stdout.strip() or "no PDF made").splitlines()[-1]
        done = subprocess.run(command, capture_output=True, text=True, timeout=120)
        return done.returncode == 0, (done.stderr.strip() or done.stdout.strip()).splitlines()[-1:] and \
            (done.stderr.strip() or done.stdout.strip()).splitlines()[-1] or ""
    except Exception as error:  # noqa: BLE001 -- a converter that fails must not stop the next one
        return False, str(error).splitlines()[0] if str(error) else type(error).__name__
