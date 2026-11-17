"""One SVG-to-PDF/PNG converter chain for images and diagrams."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .cache import write_cached

CONVERTERS = ("rsvg-convert", "inkscape", "cairosvg", "svglib", "soffice", "typst", "resvg")
HINTS = ("brew install librsvg  |  apt install librsvg2-bin  |  pip install cairosvg  |  Inkscape or LibreOffice  |  pdfmd --install typst  |  pdfmd --install diagram:resvg")


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
        if name in ("rsvg-convert", "inkscape", "typst", "resvg") and which(name):
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
                soffice: Callable[[], str | None] = lambda: None, run=None, *,
                format: str = "pdf", dpi: float = 192, fonts: Path | None = None) -> tuple[Path | None, str]:
    """(the PDF/PNG in `cache`, "") or (None, why not). A conversion made before is reused. `run(command)` starts the LibreOffice
    command (pdfmd's, which applies the `soffice-timeout` limit); without it the command runs for at most 120 s."""
    target = cache / cache_name(svg)
    if format == "png":
        target = target.with_name(target.stem + f"-{dpi:g}.png")
    if target.is_file() and target.stat().st_size > 0:
        return target, ""
    fallback = target.with_name(target.stem + f"-{dpi:g}.png") if format == "pdf" else target
    if fallback.is_file() and fallback.stat().st_size > 0:
        return fallback, ""
    converters = available_converters(which, soffice)
    if not converters:
        return None, "no SVG converter found (" + HINTS + ")"
    cache.mkdir(parents=True, exist_ok=True)
    reasons = []
    for name in converters:
        scratch = Path(tempfile.mkdtemp(prefix="pdfmd-svg-"))
        try:
            suffix = "png" if name == "resvg" else format
            produced = scratch / ("out." + suffix)
            ok, reason = _run(name, svg, produced, scratch, which, soffice, run, dpi=dpi, fonts=fonts)
            if ok and produced.is_file() and produced.stat().st_size > 0:
                destination = target if suffix == format else target.with_name(target.stem + f"-{dpi:g}.png")
                write_cached(destination, produced.read_bytes())
                return destination, ""
            reasons.append(f"{name}: {reason}")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    return None, "; ".join(reasons)


def _run(name: str, svg: Path, produced: Path, scratch: Path, which, soffice, run=None, *, dpi=192, fonts=None, timeout=120) -> tuple[bool, str]:
    try:
        format = produced.suffix[1:]
        root = scratch.resolve()
        if name == "typst":
            try:
                root = Path(os.path.commonpath([svg.resolve().parent, scratch.resolve()]))
            except ValueError:  # Windows input and temporary folder on different drives
                copied = scratch / "in.svg"
                copied.write_bytes(svg.read_bytes())
                svg = copied
            image = "/" + svg.resolve().relative_to(root).as_posix()
            (scratch / "out.typ").write_text(typst_document(image), encoding="utf-8")
        command = converter_command(name, str(svg.resolve()), str(produced), str(scratch), format, dpi, fonts, which, str(root))
        if command is not None:
            pass
        elif name == "cairosvg":
            import cairosvg
            if format == "pdf":
                cairosvg.svg2pdf(url=str(svg), write_to=str(produced))
            else:
                cairosvg.svg2png(url=str(svg), write_to=str(produced), scale=dpi / 96)
            return True, ""
        elif name == "svglib":
            from reportlab.graphics import renderPDF
            from svglib.svglib import svg2rlg
            drawing = svg2rlg(str(svg))
            if drawing is None:
                return False, "could not read the drawing"
            if format == "pdf":
                renderPDF.drawToFile(drawing, str(produced))
            else:
                from reportlab.graphics import renderPM
                renderPM.drawToFile(drawing, str(produced), fmt="PNG", dpi=dpi)
            return True, ""
        else:                                                     # soffice: Draw sizes the page to the drawing
            profile = scratch / "profile"
            command = [soffice(), "--headless", "--norestore", f"-env:UserInstallation={profile.as_uri()}",
                       "--convert-to", format, "--outdir", str(scratch), str(svg)]
            done = (run(command) if run else
                    subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout))
            made = scratch / f"{svg.stem}.{format}"
            if made.is_file():
                made.replace(produced)
                return True, ""
            return False, (done.stderr.strip() or done.stdout.strip() or "no output made").splitlines()[-1]
        done = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
        return done.returncode == 0, (done.stderr.strip() or done.stdout.strip()).splitlines()[-1:] and \
            (done.stderr.strip() or done.stdout.strip()).splitlines()[-1] or ""
    except Exception as error:  # noqa: BLE001 -- a converter that fails must not stop the next one
        return False, str(error).splitlines()[0] if str(error) else type(error).__name__


def typst_document(image: str) -> str:
    """A vector image's own page, without a paper size or margin."""
    return '#set page(width: auto, height: auto, margin: 0pt)\n#image(' + json.dumps(image, ensure_ascii=False) + ')\n'


def converter_command(name, svg, out, folder, format, dpi, fonts, which, root):
    """One command definition shared by images and diagrams; None uses a Python/LibreOffice adapter."""
    if name == "rsvg-convert":
        return [which(name), *(["-z", f"{dpi / 96:g}"] if format == "png" else []), "-f", format, "-o", out, svg]
    if name == "inkscape":
        return [which(name), svg, "--export-type=" + format,
                *([f"--export-dpi={dpi:g}"] if format == "png" else []), "--export-filename=" + out]
    if name == "typst":
        return [which(name), "compile", "--root", root, *(["--font-path", str(fonts)] if fonts else []),
                *(["--format", "png", "--ppi", f"{dpi:g}"] if format == "png" else []), folder + "/out.typ", out]
    if name == "resvg":
        # --zoom scales pixel dimensions too; SVG's reference pixel is 1/96 inch.
        return [which(name), "--zoom", f"{dpi / 96:g}",
                *(["--font-dirs", str(fonts)] if fonts else []), svg, out]
    return None


def diagram_converters(which, soffice, fonts, dpi=192):
    """Commands with path tokens replaced by diagram.lua for each drawing. The Python adapters import this same module,
    including from a wheel or zipapp, rather than keeping a second chain in Lua."""
    result = {}
    for format in ("pdf", "png"):
        attempts = []
        for name in available_converters(which, soffice):
            suffix = "png" if name == "resvg" else format
            out = "@DIR@/out." + suffix
            command = converter_command(name, "@DIR@/out.svg", out, "@DIR@", suffix, dpi, fonts, which, "@DIR@")
            if command is None:
                code = ("import sys;sys.path.insert(0,sys.argv.pop(1));"
                        "from pdfmd_images.svg import legacy_cli;legacy_cli()")
                command = [sys.executable, "-c", code, str(Path(__file__).resolve().parent.parent), name,
                           "@DIR@/out.svg", out, str(dpi), str(soffice() or "")]
            attempts.append({"name": name, "command": command, "suffix": suffix})
        result[format] = attempts
    return result


def legacy_cli():
    """Python and LibreOffice converters, run under the diagram tool's existing process-tree timeout."""
    name, svg, out, dpi, soffice = sys.argv[1:]
    ok, why = _run(name, Path(svg), Path(out), Path(out).parent, shutil.which, lambda: soffice, dpi=float(dpi), timeout=None)
    if not ok:
        print(why, file=sys.stderr)
        raise SystemExit(1)
