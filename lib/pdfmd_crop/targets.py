"""The picture command (`pdfmd --crop`, `--to png|jpg|tiff|eps|ps|svg`, `--to png,docx,tex`): the sources, the build of the
intermediate PDF, the crop and the pictures for every target, and the run of one pdfmd per format that is not a picture.

Moved out of `pdfmd.py` unchanged (v3.33.11, SPLIT.md), with `PICTURE_OPTIONS` and `TARGET_ONLY_OPTIONS`. `core` is the `pdfmd`
module, bound when the module is first loaded (the first binding wins); the pdfmd names the code uses (`PICTURE_ONLY` and
`PICTURE_FORMATS`, `config_options`, which tests patch, and the rest) are read as `core.X` when it runs. The two builds that start
pdfmd again name the script by `core.__file__` (`pdfmd.py`), not by this module's own file. `from pdfmd_crop import ...` and
`from pdfmd_crop.images import ...` stay inside the functions, as they were.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pdfmd_base import core

def picture_target(args) -> str | None:
    """`--to`, else the format `-o` names by its suffix: png and svg are the ones that choose the picture command."""
    return args.to or (core.format_from_output(args.out) if args.out else None)


# the options of the command line that `picture_build` must not hand on to the build of the intermediate PDF, and how
# many words each takes (-b and --recursive: the files are built one at a time here)
PICTURE_OPTIONS = {"--crop": 0, "-d": 0, "--crop-pad": 1, "--crop-ignore-bottom": 1, "--crop-page": 1, "--image-dpi": 1,
                   "--image-quality": 1, "--page-folder": 0, "--no-page-folder": 0, "-o": 1, "--out": 1, "--output": 1, "-t": 1, "--to": 1, "-b": 0, "--batch": 0, "--recursive": 0}


def picture_build(args, source: Path, scratch: Path) -> tuple[Path | None, str]:
    """The PDF pdfmd makes of the Markdown `source` (a run of pdfmd itself with every option of this command line but
    the ones in PICTURE_OPTIONS, and without a build stamp, a backup or a renamed older result), in `scratch`, and what
    the build printed on stderr; None for the PDF when the build failed."""
    typed = {str(path) for path in args.path}
    kept, skip = [], 0
    for word in sys.argv[1:]:
        if skip:
            skip -= 1
        elif word.split("=", 1)[0] in PICTURE_OPTIONS:
            skip = 0 if "=" in word else PICTURE_OPTIONS[word]
        elif word in typed or str(Path(word)) in typed:
            continue
        else:
            kept.append(word)
    built = scratch / "built.pdf"
    command = [sys.executable, str(Path(core.__file__).resolve()), *kept, str(source), "--to", "pdf", "-o", str(built),
               "--no-stamp", "--no-backup", "--rewrite"]
    done = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
    return (built if done.returncode == 0 and built.is_file() else None), done.stderr


def picture_sources(args) -> list[Path] | str:
    """What `picture_command` works through: the files named, or with -b the Markdown files of the one folder named
    (the files `-b` builds: `*.md`, in subfolders too with --recursive). A string is the reason there are none."""
    if not args.path:
        return f"--{'crop' if args.crop else 'to ' + (picture_target(args) or 'png')} takes the files to work on: pdfmd --crop formula.pdf"
    if not args.batch:
        return list(args.path)
    if len(args.path) != 1 or not args.path[0].is_dir():
        return "-b takes one folder"
    folder = args.path[0]
    files = sorted(folder.rglob("*.md") if args.recursive else folder.glob("*.md"))
    return files or f"-b: no Markdown files in {core.display_path(folder)}"


def picture_page_folder(args, source: Path) -> bool:
    """Whether the pages of a picture go into a folder: --page-folder / --no-page-folder, else the `page-folder` option of
    the document (front matter), its folder layers and the config, else yes."""
    if args.page_folder is not None:
        return args.page_folder
    value = core.first_pdfmd_option(source, [], "page-folder") if source.suffix.lower() in (".md", ".markdown") else core.config_options().get("page-folder")
    flag = core.option_flag(value)
    return True if flag is None else flag


def picture_targets(args) -> list[str]:
    """The formats asked for: `--to png,pdf` (several), `--to` or the suffix of `-o` (one), else pdf."""
    return list(args.to_many or [picture_target(args) or "pdf"])


def picture_one(args, source: Path, destination_for, pad: float, dpi: float, quality: int) -> tuple[int, list[str], list[str]]:
    """One source through the build, the crop and the pictures, for every target: (exit status, lines for stdout, lines
    for stderr). The PDF is built, and cropped, once."""
    from pdfmd_crop import CropError, crop_pdf
    from pdfmd_crop.images import pictures
    targets = picture_targets(args)
    out_lines: list[str] = []
    err_lines: list[str] = []
    from_pdf = source.suffix.lower() == ".pdf"
    if from_pdf and not source.is_file():
        return 1, [], [f"ERROR  {core.display_path(source)}: no such file"]
    if args.report and not from_pdf:
        markdown = source.resolve()   # a report is a folder (or a scaffold); its result is named after it
    else:
        try:
            markdown = source if from_pdf else core.find_markdown(source)
        except FileNotFoundError as error:
            return 1, [], [str(error)]
    stem = markdown.name if args.report and markdown.is_dir() else markdown.stem
    home = markdown if args.report and markdown.is_dir() else markdown.parent
    with tempfile.TemporaryDirectory(prefix="pdfmd-pictures-") as scratch:
        folder = Path(scratch)
        if from_pdf:
            pdf = markdown
        else:
            pdf, printed = picture_build(args, markdown, folder)
            if printed:
                err_lines += printed.rstrip("\n").split("\n")
            if pdf is None:
                return 1, out_lines, err_lines
        try:
            if args.crop:
                cropped = folder / "cropped.pdf"
                done = crop_pdf(pdf, cropped, pad=pad, ignore_bottom=args.crop_ignore_bottom or 0.0, page=args.crop_page)
                first = 1 if args.crop_page is None else args.crop_page
                empty = [str(number) for number, box in enumerate(done.boxes, first) if box is None]
                if empty:
                    err_lines.append(f"NOTE  nothing is drawn on page {', '.join(empty)}: left as it is")
                pdf = cropped
            written: list[Path] = []
            for target in targets:
                destination = destination_for(stem + ("-crop" if from_pdf and target == "pdf" else "") + "." + target, home)
                if target == "pdf":
                    if from_pdf and not args.crop:
                        err_lines.append(f"NOTE  {core.display_path(source)} is a PDF already: nothing to write for pdf")
                        continue
                    part = destination.with_name(destination.name + ".part")
                    shutil.copyfile(pdf, part)
                    part.replace(destination)
                    written.append(destination)
                else:
                    made = pictures(pdf, destination, target, dpi, quality, picture_page_folder(args, markdown))
                    if len(made) > 1 and target not in ("tiff", "ps"):
                        where = "beside it" if made[0].parent == destination.parent else f"in {core.display_path(made[0].parent)}/"
                        err_lines.append(f"NOTE  {len(made)} pages: one {target} each, {where}")
                    written += made
        except (CropError, OSError) as error:
            return 1, out_lines, err_lines + [f"ERROR  {core.display_path(source)}: {error}"]
    if not written:
        return 1, out_lines, err_lines
    out_lines += [f"OK    {core.display_path(source)} > {core.display_path(path)}" for path in written]
    return 0, out_lines, err_lines


# the options of a picture run that a build of another format must not get (the rest of the command line it does)
TARGET_ONLY_OPTIONS = {"--crop": 0, "--crop-pad": 1, "--crop-ignore-bottom": 1, "--crop-page": 1, "--image-dpi": 1,
                       "--image-quality": 1, "--page-folder": 0, "--no-page-folder": 0, "-t": 1, "--to": 1}


def multi_target_command(args) -> int:
    """`--to png,docx,tex`: one run of pdfmd per format that is not a picture (the same command line with that `--to`),
    and one picture run for the picture formats (see picture_command). A plain `pdf` is a build of its own, with its stamp
    and its backup, unless `--crop` cuts it or a source is a PDF already. `-o` is then a folder."""
    formats = list(args.to_many)
    cropped_pdf = args.crop or any(path.suffix.lower() == ".pdf" for path in args.path)
    pictures = [name for name in formats if name in core.PICTURE_ONLY or (name == "pdf" and cropped_pdf)]
    others = [name for name in formats if name not in pictures]
    if len(formats) > 1 and args.out is not None and args.out.suffix and not args.out.is_dir():
        print(f"{len(formats)} formats: -o names a folder, not a file ({args.out})", file=sys.stderr)
        return 1
    if args.out is not None and len(formats) > 1:
        args.out.mkdir(parents=True, exist_ok=True)
    kept, skip = [], 0
    for word in sys.argv[1:]:
        if skip:
            skip -= 1
        elif word.split("=", 1)[0] in TARGET_ONLY_OPTIONS:
            skip = 0 if "=" in word else TARGET_ONLY_OPTIONS[word]
        else:
            kept.append(word)
    status = 0
    for name in others:
        sys.stdout.flush()
        done = subprocess.run([sys.executable, str(Path(core.__file__).resolve()), *kept, "--to", name])
        status = max(status, done.returncode)
    if pictures:
        args.to_many = pictures
        status = max(status, picture_command(args))
    return status


def picture_command(args) -> int:
    """`pdfmd --crop` and `--to png|jpg|tiff|eps|ps|svg`: a PDF (or the PDF pdfmd builds from a source) cut to its ink with
    --crop, and drawn as pictures when the target is one; `--to png,pdf` writes several. Files named on the command line,
    or with -b the Markdown files of a folder (`-j` at a time); with -r the report of a folder is one result. See pdfmd_crop
    and the changelog."""
    from pdfmd_crop import DEFAULT_PAD
    from pdfmd_crop.images import DEFAULT_DPI, DEFAULT_QUALITY
    targets = picture_targets(args)
    for target in targets:
        if target not in core.PICTURE_FORMATS:
            print(f"--crop cuts a PDF page: it goes with --to pdf, png, jpg, tiff, eps, ps or svg, not {target} "
                  f"(a {target} file has no page box to cut)", file=sys.stderr)
            return 1
    sources = picture_sources(args)
    if isinstance(sources, str):
        print(sources, file=sys.stderr)
        return 1
    out = args.out
    if out is not None and len(targets) == 1:
        named = core.format_from_output(out)
        if named is not None and named != targets[0] and not out.is_dir():
            print(f"-o {out} is a {named} file, but the target is {targets[0]}", file=sys.stderr)
            return 1
    many = len(sources) > 1 or len(targets) > 1
    into_folder = out is not None and (many or out.is_dir() or not out.suffix)
    if out is not None and many and out.suffix and not out.is_dir():
        print(f"{len(sources)} files and {len(targets)} format{'' if len(targets) == 1 else 's'}: -o names a folder, "
              f"not a file ({out})", file=sys.stderr)
        return 1
    if into_folder:
        out.mkdir(parents=True, exist_ok=True)

    def destination_for(name: str, home: Path) -> Path:
        if out is None:
            return (Path.cwd() if args.destination_cwd else home) / name
        return out / name if into_folder else out

    pad = DEFAULT_PAD if args.crop_pad is None else args.crop_pad
    dpi = DEFAULT_DPI if args.image_dpi is None else args.image_dpi
    quality = DEFAULT_QUALITY if args.image_quality is None else args.image_quality
    if args.batch and len(sources) > 1 and max(1, args.jobs) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(pool.map(lambda source: picture_one(args, source, destination_for, pad, dpi, quality), sources))
    else:
        results = [picture_one(args, source, destination_for, pad, dpi, quality) for source in sources]
    status = 0
    for code, out_lines, err_lines in results:
        status = max(status, code)
        for line in out_lines:
            print(line)
        for line in err_lines:
            print(line, file=sys.stderr)
    return status
