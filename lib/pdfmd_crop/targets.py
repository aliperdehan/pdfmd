"""Dispatch standalone PDF exports and lists spanning different build writers."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfmd_base import core
from pdfmd_crop import CropError, crop_pdf
from pdfmd_crop.build import crop_settings, draw_targets


def picture_target(args) -> str | None:
    """An explicit target or the format implied by an output file's suffix."""
    return args.to or (core.format_from_output(args.out) if args.out and not args.batch else None)


def picture_command(args) -> int:
    """Export a PDF that already exists, without invoking a document writer."""
    targets = list(args.to_many or [picture_target(args) or "pdf"])
    if any(target not in core.PICTURE_FORMATS for target in targets):
        names = ", ".join(core.PICTURE_FORMATS[:-1]) + " or " + core.PICTURE_FORMATS[-1]
        raise SystemExit(f"--crop cuts a PDF page: it goes with --to {names}")
    if args.batch:
        raise SystemExit("-b takes one folder")
    many = len(args.path) > 1 or len(targets) > 1
    out = output_folder(args.out, many)
    if out is not None and out.suffix and not out.is_dir():
        check_suffix(out, targets[0])
    status = 0
    sources = [source for source in args.path if source.suffix.casefold() == ".pdf"]
    documents = [source for source in args.path if source not in sources]
    if documents:
        options = {"--input": 1}
        kept = kept_arguments(sys.argv[1:], options, set(args.original_source_paths))
        command = [sys.executable, str(Path(core.__file__).resolve()), *kept, "--", *map(str, documents)]
        status = subprocess.run(command).returncode
    for source in sources:
        source = source.resolve()
        if not source.is_file():
            print(f"ERROR  {core.display_path(source)}: no such file", file=sys.stderr)
            status = 1
            continue
        home = Path.cwd() if args.destination_cwd else source.parent
        try:
            metadata = core.find_metadata(source.parent, args.metadata_file, document_stem=source.stem, document=source)
            metadata = metadata if isinstance(metadata, list) else [metadata] if isinstance(metadata, Path) else []
            crop = crop_settings(source, metadata, "pdf")
            from pdfmd_engines.tools import tool_paths

            with tool_paths(source, metadata), TemporaryDirectory(prefix="pdfmd-pictures-") as scratch:
                pdf = source
                if crop is not None:
                    pdf = Path(scratch) / "cropped.pdf"
                    cropped = crop_pdf(source, pdf, **crop)
                    empty = [str(n) for n, box in enumerate(cropped.boxes, crop["page"] or 1) if box is None]
                    if empty:
                        print(f"NOTE  nothing is drawn on page {', '.join(empty)}: left as it is", file=sys.stderr)
                written = []
                if "pdf" in targets:
                    if crop is None:
                        print(f"NOTE  {core.display_path(source)} is a PDF already: nothing to write for pdf", file=sys.stderr)
                    else:
                        destination = picture_destination(out, home, source.stem + "-crop.pdf")
                        part = destination.with_name(destination.name + ".part")
                        shutil.copyfile(pdf, part)
                        part.replace(destination)
                        written.append(destination)
                pictures = tuple(target for target in targets if target != "pdf")
                if pictures:
                    destination = picture_destination(out, home, source.stem + core.output_extension_for(pictures[0]))
                    written += draw_targets(pdf, destination, pictures, source, metadata, exact=len(pictures) == 1)
            for path in written:
                print(f"OK    {core.display_path(source)} > {core.display_path(path)}")
            if not written:
                status = 1
        except (CropError, FileNotFoundError, ValueError, OSError) as error:
            print(f"ERROR  {core.display_path(source)}: {error}", file=sys.stderr)
            status = 1
    return status


def check_suffix(output: Path, target: str) -> None:
    named = core.format_from_output(output)
    if named is not None and named != target and not output.is_dir():
        raise SystemExit(f"-o {output} is a {named} file, but the target is {target}")


def output_folder(output: Path | None, many: bool) -> Path | None:
    if output is not None and (many or not output.suffix):
        if output.suffix and not output.is_dir():
            raise SystemExit(f"Several outputs: -o names a folder, not a file ({output})")
        output.mkdir(parents=True, exist_ok=True)
    return output


def picture_destination(output: Path | None, home: Path, name: str) -> Path:
    if output is None:
        return home / name
    return output / name if output.is_dir() else output


# Other writers get their own invocation, as with explicit --to lists since
# 3.31.28. The PDF and all of its derivatives share one normal PDF invocation.
_TARGET_OPTIONS = {"-t": 1, "--to": 1}
_PICTURE_OPTIONS = {"--crop": 0, "--no-crop": 0, "--crop-pad": 1, "--crop-ignore-bottom": 1, "--crop-page": 1,
                    "--image-quality": 1, "--page-folder": 0, "--no-page-folder": 0}


def kept_arguments(argv, options, paths=()):
    kept, skip = [], 0
    for word in argv:
        key, equals, _ = word.partition("=")
        if skip:
            skip -= 1
        elif key in options:
            skip = 0 if equals else options[key]
        elif not paths or (word != "--" and str(Path(word)) not in paths):
            kept.append(word)
    return kept


def multi_target_command(args, *, formats=None, source=None, batch_file=False, original=None) -> int:
    """Build unrelated writer targets separately. Pin a resolved default to its input."""
    formats = list(formats or args.to_many)
    pdf_targets = [name for name in formats if name in core.PICTURE_FORMATS]
    others = [name for name in formats if name not in core.PICTURE_FORMATS]
    output_folder(args.out, len(formats) > 1)
    argv = [sys.executable, str(Path(core.__file__).resolve())]
    removed = _TARGET_OPTIONS.copy()
    paths = ()
    if source is not None:
        paths = set(args.original_source_paths)
        removed["--input"] = 1
        if batch_file:
            removed.update({"-b": 0, "--batch": 0, "--recursive": 0, "--jobs": 1, "-j": 1})
    status = 0
    for targets in [[name] for name in others] + ([pdf_targets] if pdf_targets else []):
        options = removed if targets == pdf_targets else {**removed, **_PICTURE_OPTIONS}
        command = [*argv, "--to", ",".join(targets),
                   *kept_arguments(sys.argv[1:] if original is None else original, options, paths)]
        if source is not None:
            command.extend(("--", str(source)))
        sys.stdout.flush()
        status = max(status, subprocess.run(command).returncode)
    return status


def build_batch_writers(args, source, formats, original=None, *, chatter=None):
    status = multi_target_command(args, formats=formats, source=source, batch_file=True, original=original)
    built = core.Built((source, status == 0, ""))
    built.chatter = chatter
    return built
