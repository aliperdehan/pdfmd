"""Crop the PDF from a normal build, with the same crop as the standalone command."""

from __future__ import annotations

import math
import shutil
import sys
from collections.abc import Sequence
from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfmd_base import core
from pdfmd_crop import DEFAULT_PAD, CropError, crop_pdf


CROP_OPTIONS_REQUIRED = "--crop-pad, --crop-ignore-bottom and --crop-page go with --crop or pdfmd-options.crop"


@contextmanager
def prepare(document: Path, output: Path, metadata: list[Path], target: str, verbose: bool, *,
            variables: Sequence[str] = (), report: bool = False):
    """Yield the crop to run after the engine succeeds. Restore the previous PDF if cropping fails."""
    enabled, pad, bottom, page = core.POLISH_CLI.get("crop", (None, None, None, None))
    if enabled is None and target == "pdf":
        enabled = core.option_flag(core.first_pdfmd_option(document, metadata, "crop"))
    if not enabled:
        if any(value is not None for value in (pad, bottom, page)):
            raise SystemExit(CROP_OPTIONS_REQUIRED)
        yield None
        return
    if target != "pdf":
        raise SystemExit(f"Cropping requires a PDF build, but the build writes {target}")
    pad = DEFAULT_PAD if pad is None else pad
    bottom = 0.0 if bottom is None else bottom
    if any(not math.isfinite(value) or value < 0 for value in (pad, bottom)):
        raise SystemExit("--crop-pad and --crop-ignore-bottom take a finite number of points of 0 or more")
    if page is not None and page < 1:
        raise SystemExit("--crop-page counts pages from 1")

    from pdfmd_build import page_numbers
    saved = TemporaryDirectory(prefix=".pdfmd-uncropped-", dir=output.parent) if output.is_file() else nullcontext()
    with saved as folder, page_numbers.cropped(document, variables, report=report):
        previous = None
        if folder is not None:
            previous = Path(folder) / output.name
            shutil.copy2(output, previous)

        def finish() -> str:
            try:
                cropped = crop_pdf(output, output, pad=pad, ignore_bottom=bottom, page=page)
            except (CropError, OSError) as error:
                if previous is None:
                    output.unlink(missing_ok=True)
                else:
                    previous.replace(output)
                return str(error)
            empty = [str(number) for number, box in enumerate(cropped.boxes, page or 1) if box is None]
            if empty:
                print(f"NOTE  nothing is drawn on page {', '.join(empty)}: left as it is", file=sys.stderr)
            core.vprint(verbose, f"CROP  {core.display_path(output)}: cut to the ink")
            return ""

        yield finish
