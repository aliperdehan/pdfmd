"""Discover the tools used to measure and export PDF pages."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from pdfmd_base import bound
from pdfmd_base import core

INK_CHAIN = ("Ghostscript bbox", "mutool bbox", "pdftoppm / pdftocairo / mutool raster scan")
PNG_CHAIN = ("Ghostscript", "pdftocairo", "mutool", "pdftoppm", "sips (macOS)", "pypdfium2 + Pillow")
SVG_CHAIN = ("pdftocairo", "mutool", "Ghostscript svgwrite (when available)")


def find(name: str) -> str | None:
    if name == "sips" and sys.platform != "darwin":
        return None
    if bound() is None:
        candidates = ("gs", "gswin64c", "gswin32c") if name == "ghostscript" else (name,)
        return next((path for program in candidates if (path := shutil.which(program))), None)
    if name in ("ghostscript", "mutool"):
        return core.locate_tool(name)[0]
    if name in ("pdftocairo", "pdftoppm"):
        from pdfmd_engines.tools import pinned_program, tool_program

        if found := pinned_program(name):
            return found
        poppler = core.TOOLS_FOUND.get("poppler")
        if poppler and (found := tool_program(Path(poppler[0]).parent, name)):
            return str(found)
    return core.which(name)


def optional(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def reports():
    for name in ("ghostscript", "mutool", "pdftocairo", "pdftoppm", "sips"):
        yield name, find(name), None
    yield "ImageMagick", find("magick"), None
    for name, module in (("pypdfium2", "pypdfium2"), ("Pillow", "PIL")):
        yield name, None, "Python module" if optional(module) else None


def run(command: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
    except OSError as error:
        return subprocess.CompletedProcess(command, 1, "", str(error))


def checked(command, output: Path) -> None:
    from pdfmd_crop import CropError

    # All attempts share this scratch destination. A failed producer may
    # have left a partial file even if the next producer writes nothing.
    output.unlink(missing_ok=True)
    done = run(command)
    if done.returncode or not output.is_file() or not output.stat().st_size:
        raise CropError((done.stderr.strip().splitlines() or ["no picture was made"])[-1])
