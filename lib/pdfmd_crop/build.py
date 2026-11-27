"""Crop the PDF from a normal build, with the same crop as the standalone command."""

from __future__ import annotations

import math
import shutil
import sys
from collections.abc import Sequence
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfmd_base import core
from pdfmd_log import emit
from pdfmd_crop import DEFAULT_PAD, CropError, crop_pdf


CROP_OPTIONS_REQUIRED = "--crop-pad, --crop-ignore-bottom and --crop-page go with --crop or pdfmd-options.crop"


def setting(document: Path, metadata: list[Path], key: str, cli=None):
    if cli is not None:
        return cli
    return core.first_pdfmd_option(document, metadata, key)


def number(document, metadata, key, cli, default, minimum, *, integer=False, maximum=None, exclusive=False):
    value = setting(document, metadata, key, cli)
    if value is None:
        return default
    parsed = core.option_flag_number(value)
    if (parsed is None or not math.isfinite(parsed) or parsed < minimum or (exclusive and parsed == minimum)
            or (maximum is not None and parsed > maximum) or (integer and not parsed.is_integer())):
        raise CropError(f"--{key} / pdfmd-options.{key}: expected "
                        + (f"a whole number from {minimum} to {maximum}" if maximum is not None else
                           f"a finite number above {minimum}" if exclusive else
                           f"{'a whole number' if integer else 'a finite number'} of {minimum} or more"))
    return int(parsed) if integer else parsed


def crop_settings(document, metadata, target):
    enabled, pad, bottom, page = core.POLISH_CLI.get("crop", (None, None, None, None))
    if target == "pdf":
        enabled = core.option_flag(setting(document, metadata, "crop", enabled))
    if not enabled:
        if any(value is not None for value in (pad, bottom, page)):
            raise CropError(CROP_OPTIONS_REQUIRED)
        return None
    if target != "pdf":
        raise CropError(f"Cropping requires a PDF build, but the build writes {target}")
    return {
        "pad": number(document, metadata, "crop-pad", pad, DEFAULT_PAD, 0),
        "ignore_bottom": number(document, metadata, "crop-ignore-bottom", bottom, 0.0, 0),
        "page": number(document, metadata, "crop-page", page, None, 1, integer=True),
    }


@dataclass(frozen=True)
class Export:
    """Picture destinations of one normal PDF build."""

    formats: tuple[str, ...]
    keep_pdf: bool

    @property
    def primary(self) -> str:
        return "pdf" if self.keep_pdf else self.formats[0]

    def output(self, stack, destination):
        if self.keep_pdf:
            return destination
        scratch = Path(stack.enter_context(TemporaryDirectory(prefix="pdfmd-pictures-")))
        return scratch / destination.with_suffix(".pdf").name

    def finish(self, pdf, destination, document, metadata):
        """Return the main visible output (a folder for some paged exports)."""
        written = draw_targets(pdf, destination, self.formats, document, metadata,
                               exact=not self.keep_pdf and len(self.formats) == 1)
        if self.keep_pdf:
            return pdf
        return written[0] if len(written) == 1 or written[0].parent == destination.parent else written[0].parent


def build_target(target: str) -> tuple[str, Export | None]:
    formats = tuple(target.split(","))
    pictures = tuple(name for name in formats if name in core.PICTURE_ONLY)
    if pictures:
        return "pdf", Export(pictures, "pdf" in formats)
    return target, None


def draw_targets(pdf, destination, formats, document, metadata, *, exact=False) -> list[Path]:
    from pdfmd_crop.images import DEFAULT_DPI, DEFAULT_QUALITY, pictures
    dpi = number(document, metadata, "image-dpi", core.IMAGE_DPI_CLI, DEFAULT_DPI, 0, exclusive=True)
    quality = number(document, metadata, "image-quality", core.POLISH_CLI.get("image-quality"),
                     DEFAULT_QUALITY, 1, integer=True, maximum=100)
    folder = core.option_flag(setting(document, metadata, "page-folder", core.POLISH_CLI.get("page-folder"))) is not False
    written = []
    for target in formats:
        target_path = destination if exact else destination.with_suffix(core.output_extension_for(target))
        made = pictures(pdf, target_path, target, dpi, quality, folder)
        if len(made) > 1:
            where = "beside it" if made[0].parent == target_path.parent else f"in {core.display_path(made[0].parent)}/"
            emit("note", None, f"NOTE  {len(made)} pages: one {target} each, {where}", file=sys.stderr)
        written.extend(made)
    return written


def finish_direct(document, destination, metadata, target, verbose, export, build):
    with ExitStack() as stack:
        output = export.output(stack, destination) if export else destination
        crop = stack.enter_context(prepare(document, output, metadata, target, verbose))
        result = build(output)
        if result[1]:
            core.BUILD["output"] = output
        if result[1] and crop is not None and (problem := crop()):
            return document, False, problem
        if result[1] and export:
            try:
                core.BUILD["output"] = export.finish(output, destination, document, metadata)
            except (CropError, OSError) as error:
                return document, False, str(error)
        return result


@contextmanager
def prepare(document: Path, output: Path, metadata: list[Path], target: str, verbose: bool, *,
            variables: Sequence[str] = (), report: bool = False):
    """Yield the crop to run after the engine succeeds. Restore the previous PDF if cropping fails."""
    try:
        options = crop_settings(document, metadata, target)
    except CropError as error:
        raise SystemExit(str(error)) from error
    if options is None:
        yield None
        return

    from pdfmd_build import page_numbers
    saved = TemporaryDirectory(prefix=".pdfmd-uncropped-", dir=output.parent) if output.is_file() else nullcontext()
    with saved as folder, page_numbers.cropped(document, variables, report=report):
        previous = None
        if folder is not None:
            previous = Path(folder) / output.name
            shutil.copy2(output, previous)

        def finish() -> str:
            try:
                cropped = crop_pdf(output, output, **options)
            except (CropError, OSError) as error:
                if previous is None:
                    output.unlink(missing_ok=True)
                else:
                    previous.replace(output)
                return str(error)
            empty = [str(number) for number, box in enumerate(cropped.boxes, options["page"] or 1) if box is None]
            if empty:
                emit("note", None, f"NOTE  nothing is drawn on page {', '.join(empty)}: left as it is", file=sys.stderr)
            core.vprint(verbose, f"CROP  {core.display_path(output)}: cut to the ink")
            return ""

        yield finish
