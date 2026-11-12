"""Where a file given to pdfmd goes when it is not a Markdown document: a PDF is read into Markdown by batchocr (`route_pdf_input`,
`pdf_read_target`, `find_batchocr`, `batchocr_spec`, `batchocr_missing_message`, `install_ocr_tools`, and `tessdata_environment` for
Tesseract's languages), an ebook is turned into Markdown through Calibre and Pandoc (`route_ebook_input`), and a text file is read as
Markdown (`route_text_input`, `text_to_markdown_mode`).

Moved out of `pdfmd.py` unchanged (v3.33.25, SPLIT.md), with `BATCHOCR_REPOSITORY`, `BATCHOCR_TAG`, `BATCHOCR_TEXT_MIN`,
`EBOOK_INPUT_EXTENSIONS` and `PDF_READ_FORMATS`. `core` is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first binding
wins); the pdfmd names the code uses (`ATTACH_MANIFEST`, `BATCHOCR_MIN`, `DISPLAY_ALIAS`, `EXTENSION_FORMAT`, `FORMAT_EXTENSION`,
`OCR_PACKAGE_MANAGERS`, `PANDOC_MISSING`, `PDF_TO_STDOUT_CLI`, `batchocr_version`, `config_options`, `log_cmd`, `ocr_install_command`,
`open_file`, `pypdf` (pdfmd's own lazy import), `read_pdf_attachments`, `resolve_calibre`, `restore_from_pdf`, `run_calibre_convert`,
`split_command`, `system_package_manager`, `tessdata_directory`, `tesseract_install_hint`, `unicode_module` and `which`) are read as
`core.X` when it runs. `PDF_TO_STDOUT_CLI` is rebound by `main`, so it stays in `pdfmd.py`; `core.config_options`,
`core.resolve_calibre`, `core.run_calibre_convert`, `core.system_package_manager` and `core.which` are patched by tests as `pdfmd.X`.
"""

from __future__ import annotations

import atexit
import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import mkdtemp

from pdfmd_base import core


def quarto_input(args) -> bool:
    """Select the dedicated Quarto route before enforcing standalone Pandoc dependencies."""
    paths = args.path or []
    return not args.batch and not args.report and len(paths) == 1 and paths[0].suffix.lower() == ".qmd"


def tessdata_environment(extra: list[str]) -> dict[str, str] | None:
    """The environment for batchocr: TESSDATA_PREFIX at pdfmd's own language folder when the user has
    not set one and the folder has every language `--lang` asks for (English when it does not)."""
    if os.environ.get("TESSDATA_PREFIX") or core.unicode_module() is None:
        return None
    from pdfmd_unicode import tessdata
    wanted = "eng"
    for index, item in enumerate(extra):
        if item in ("--lang", "-l") and index + 1 < len(extra):
            wanted = extra[index + 1]
        elif item.startswith("--lang="):
            wanted = item.partition("=")[2]
    if tessdata.covers(core.tessdata_directory(), [code for code in re.split(r"[+,]", wanted) if code]):
        return {**os.environ, "TESSDATA_PREFIX": str(core.tessdata_directory())}
    return None


BATCHOCR_REPOSITORY = "https://github.com/aliperdehan/batchocr.git"
BATCHOCR_TAG = "v1.2.4"


BATCHOCR_TEXT_MIN = (1, 2, 5)      # reads a .txt file as Markdown (--text-to-markdown)
PDF_READ_FORMATS = {"md": "md", "markdown": "md", "gfm": "md", "commonmark": "md", "commonmark_x": "md",
                    "txt": "txt", "text": "txt", "plain": "txt"}


def batchocr_spec() -> str:
    return os.environ.get("PDFMD_BATCHOCR_SPEC") or f"batchocr[md] @ git+{BATCHOCR_REPOSITORY}@{BATCHOCR_TAG}"


def find_batchocr() -> list[str] | None:
    """The command that runs batchocr: $PDFMD_BATCHOCR (a command line, for a checkout or
    an alias that is not on PATH), `batchocr` on PATH, or the module in this Python."""
    override = os.environ.get("PDFMD_BATCHOCR")
    if override:
        return core.split_command(override)
    found = core.which("batchocr")
    if found:
        return [found]
    try:
        if importlib.util.find_spec("batchocr") is not None:
            return [sys.executable, "-m", "batchocr"]
    except (ImportError, ValueError):
        pass
    return None


def install_ocr_tools() -> None:
    """After `--install batchocr`: install Tesseract/Poppler through the system's package
    manager if they are missing. Only on an interactive terminal, only after a yes; otherwise the
    command is printed. Languages are named, never installed (they are large and personal)."""
    missing = [tool for tool, programs in (("tesseract", ("tesseract",)), ("poppler", ("pdftotext", "pdftoppm")))
               if not all(core.which(program) for program in programs)]
    if not missing:
        return
    manager = core.system_package_manager()
    if not manager:
        print(f"NOTE  {' and '.join(missing)} not found; scanned pages need them: {core.tesseract_install_hint()}")
        return
    command = core.ocr_install_command(manager, tuple(missing))
    base = core.OCR_PACKAGE_MANAGERS[manager][0]
    if command[-len(base):] == base:  # nothing this manager can install (Poppler under winget)
        print(f"NOTE  {' and '.join(missing)} not found; scanned pages need them: {core.tesseract_install_hint()}")
        return
    print(f"NOTE  {' and '.join(missing)} not found; scanned pages need them (pdfmd does not bundle them).")
    print(f"      {shlex.join(command)}")
    if os.environ.get("PDFMD_NO_PROMPT") or not sys.stdin.isatty() or not sys.stdout.isatty():
        print("      (run it yourself; pdfmd asks only on an interactive terminal)")
        return
    try:
        answer = input("      Run it now? [y/N] ").strip().lower()
    except EOFError:
        return
    if answer in ("y", "yes"):
        try:
            code = subprocess.run(command).returncode
        except OSError as error:
            print(f"Could not run {command[0]} ({error}).", file=sys.stderr)
            return
        print("Installed." if code == 0 else f"{command[0]} exited with status {code}.")
    print(f"      More OCR languages: pdfmd --install ocr:rus,kaz  (or {core.OCR_PACKAGE_MANAGERS[manager][2]})")


def batchocr_missing_message(found: tuple[int, ...] | None = None) -> str:
    what = (f"batchocr {'.'.join(map(str, found))} is too old (pdfmd needs {'.'.join(map(str, core.BATCHOCR_MIN))} or newer)"
            if found else "Reading a PDF needs batchocr, which was not found")
    return (f"{what}.\n  install it:  pdfmd --install batchocr\n"
            f"  or by hand:  pip install \"{batchocr_spec()}\"\n"
            f"  it also uses Tesseract and Poppler for scanned pages: {core.tesseract_install_hint()}\n"
            "  (a checkout that is not on PATH: set PDFMD_BATCHOCR to the command that runs it)")


def pdf_read_target(args) -> tuple[str, Path | None]:
    """The format a PDF input is read as ('md' | 'txt'), and -o, from the extension of -o and --to."""
    out = args.out
    by_out = by_to = None
    for label, value in (("--to", args.to), ("-o", out.suffix.lstrip(".") if out is not None else None)):
        if not value:
            continue
        name = value.lower()
        if name == "pdf":
            raise SystemExit(f"{label}: the input is a PDF and so is the output. A PDF is read as Markdown: "
                             "name the output x.md (or --to md)")
        if name in PDF_READ_FORMATS:
            if label == "--to":
                by_to = PDF_READ_FORMATS[name]
            else:
                by_out = PDF_READ_FORMATS[name]
        elif label == "--to" or "." + name in core.EXTENSION_FORMAT:
            raise SystemExit(f"{label} {value}: pdfmd reads a PDF as Markdown or plain text. For {value}, read it "
                             "first (pdfmd FILE.pdf), then convert the Markdown (pdfmd FILE.md -o ...)")
    if by_out and by_to and by_out != by_to:
        raise SystemExit(f"-o {out.name} says {by_out} but --to says {by_to}; choose one")
    return by_to or by_out or "md", out


EBOOK_INPUT_EXTENSIONS = frozenset({".epub", ".mobi", ".azw", ".azw3", ".azw4", ".kepub", ".lit", ".lrf", ".pdb", ".prc",
                                    ".chm", ".snb", ".tcr", ".rb", ".pmlz", ".htmlz", ".txtz"})


def route_ebook_input(args) -> None:
    """When the one input is an ebook, make its Markdown in a scratch folder and point the run at it (`args.path`), with the
    output named after the book (`args.out`) unless -o gave one. Nothing when the inputs are not ebooks."""
    paths = list(args.path or [])
    books = [path for path in paths if path.suffix.lower() in EBOOK_INPUT_EXTENSIONS]
    if not books:
        return
    if len(books) != len(paths) or len(books) > 1 or args.batch or args.report:
        raise SystemExit("an ebook is built one at a time, by name: pdfmd book.mobi [-o book.pdf] (not with other files, -b or -r)")
    named = books[0]
    if not named.is_file():
        raise SystemExit(f"{named}: no such file")
    book = named.resolve()
    if not core.which("pandoc"):
        raise SystemExit(core.PANDOC_MISSING)
    scratch = Path(mkdtemp(prefix="pdfmd-ebook-"))
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    epub = book
    if book.suffix.lower() != ".epub":
        if core.resolve_calibre() is None:
            raise SystemExit(f"{book.name} is read through Calibre's ebook-convert, which was not found (on PATH, in calibre.app "
                             "or in Calibre2 under Program Files). Install Calibre: `pdfmd --install calibre`, `brew install --cask calibre`, "
                             "`winget install calibre.calibre`, your package manager, or calibre-ebook.com.")
        epub = scratch / "book.epub"
        # no cover page of Calibre's own making (an SVG title page and a picture the book never had) in the text
        done = core.run_calibre_convert(book, epub, args.verbose, ["--no-default-epub-cover", "--no-svg-cover"])
        if done.returncode != 0:
            raise SystemExit(f"{book.name}: {done.stderr}")
    markdown = scratch / (book.stem + ".md")
    command = ["pandoc", str(epub), "-s", "-t", "markdown", "--wrap=none", "--extract-media=media", "-o", str(markdown)]
    try:
        import pdfmd_lua
        if (pdfmd_lua.FILTERS / "ebook_input.lua").is_file():
            command += ["--lua-filter", str(pdfmd_lua.FILTERS / "ebook_input.lua")]       # Calibre's anchors and classes go
    except ImportError:
        pass
    core.log_cmd(command, scratch, args.verbose)
    made = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", cwd=scratch)
    if made.returncode != 0 or not markdown.is_file():
        raise SystemExit(f"{book.name}: Pandoc could not read it ({(made.stderr.strip().splitlines() or ['no output'])[-1]})")
    print(f"BOOK      {book.name} read as Markdown ({markdown.stat().st_size // 1024 or 1} KB"
          + (", with its pictures" if (scratch / "media").is_dir() else "") + ")")
    if args.out is None:
        target = (args.to.casefold() if args.to else "pdf")
        args.out = named.with_suffix(core.FORMAT_EXTENSION.get(target, f".{target}"))
    core.DISPLAY_ALIAS[markdown] = core.DISPLAY_ALIAS[markdown.resolve()] = named
    if args.out.suffix.lower() in (".md", ".markdown") and (scratch / "media").is_dir():
        # the Markdown is kept, so its pictures are too: media/ beside it (never over a file that is there)
        for picture in sorted((scratch / "media").rglob("*")):
            if picture.is_file():
                target = args.out.parent / "media" / picture.relative_to(scratch / "media")
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(picture, target)
    args.path = [markdown]


def route_pdf_input(args, extra: list[str]) -> int | None:
    """Handle a run whose inputs are PDFs; None when they are not."""
    paths = list(args.path or [])
    pdfs = [path for path in paths if path.suffix.lower() == ".pdf"]
    if not pdfs:
        return None
    if len(pdfs) != len(paths):
        raise SystemExit("PDF files and Markdown files cannot be given together; run them separately")
    if args.batch or args.report:
        raise SystemExit("-b and -r build PDFs from Markdown; to read PDFs, give them by name: pdfmd a.pdf b.pdf")
    for pdf in pdfs:
        if not pdf.is_file():
            raise SystemExit(f"{pdf}: no such file")
    fmt, out = pdf_read_target(args)
    out_is_file = out is not None and out.suffix.lower() in (".md", ".markdown", ".txt")
    read_pages = bool(args.extract or args.to or out_is_file)
    restorable: list[Path] = []
    for pdf in pdfs:
        if core.pypdf is None:
            break
        try:
            has_source = core.ATTACH_MANIFEST in core.read_pdf_attachments(pdf)
        except Exception:  # noqa: BLE001 -- unreadable here; batchocr will say what is wrong with it
            has_source = False
        if has_source and not read_pages:
            restorable.append(pdf)
        elif has_source:
            print(f"NOTE  {pdf.name} carries its own source; `pdfmd --restore {pdf.name}` writes it back "
                  "(reading its pages, as asked)", file=sys.stderr)
    status = 0
    for pdf in restorable:
        print(f"NOTE  {pdf.name} carries its own source; restoring it (--extract reads the pages instead)",
              file=sys.stderr)
        folder = None if out is None else (out if len(pdfs) == 1 else out / pdf.stem)
        status = max(status, core.restore_from_pdf(pdf, folder.resolve() if folder else None))
    rest = [pdf for pdf in pdfs if pdf not in restorable]
    if not rest:
        return status
    command = find_batchocr()
    if command is None:
        raise SystemExit(batchocr_missing_message())
    version = core.batchocr_version(command)
    if version is not None and version < core.BATCHOCR_MIN:
        raise SystemExit(batchocr_missing_message(version))
    suffix = ".md" if fmt == "md" else ".txt"
    call = [*command, *map(str, rest), "--to", fmt]
    to_stdout = any(item in ("-s", "--stdout") for item in extra) or core.PDF_TO_STDOUT_CLI
    if core.PDF_TO_STDOUT_CLI and not any(item in ("-s", "--stdout") for item in extra):
        extra = [*extra, "--stdout"]
    produced: list[Path] = []
    if out is not None and not to_stdout:
        if len(rest) == 1 and (out_is_file or not out.is_dir() and not out.suffix):
            target = out if out_is_file else out / (rest[0].stem + suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            call += ["-o", str(target)]
            produced = [target]
        else:
            out.mkdir(parents=True, exist_ok=True)
            call += ["-o", str(out)]
            produced = [out / (pdf.stem + suffix) for pdf in rest]
    else:
        produced = [pdf.with_suffix(suffix) for pdf in rest]
    levels = (sum(len(token) - 1 for token in sys.argv[1:] if re.fullmatch(r"-v+", token))
              + sys.argv[1:].count("--verbose"))
    call += ["-v"] * (levels or (1 if args.verbose else 0))     # pdfmd's -v is a switch, batchocr's a counter
    if args.jobs and args.jobs > 1:
        call += ["-j", str(args.jobs)]
    if args.engine and "=" in args.engine:
        call += ["--engine", args.engine]          # batchocr's FORMAT=ENGINE; pdfmd's own --engine is a PDF engine
    call += extra
    print(f"ROUTE  {', '.join(pdf.name for pdf in rest)} -> batchocr"
          + (f" {'.'.join(map(str, version))}" if version else "") + f" ({fmt})", file=sys.stderr)
    code = subprocess.run(call, env=tessdata_environment(extra)).returncode
    if code == 0 and args.open and produced and produced[0].is_file():
        core.open_file(produced[0])
    return max(status, code)


def text_to_markdown_mode(args) -> str | None:
    """How .txt input is to be read as Markdown (batchocr's --txt-structure: `auto`, `force`, or `off` = paragraphs
    only), from --text-to-markdown or the config's `options: {text-to-markdown: ...}`; None (the default) when it
    is not asked for."""
    value = args.text_to_markdown
    if value is None:
        value = core.config_options().get("text-to-markdown")
    if value is None or value is False:
        return None
    if value is True:
        return "auto"
    value = str(value).strip().casefold()
    return {"auto": "auto", "force": "force", "paragraphs": "off"}.get(value)


def route_text_input(args, extra: list[str]) -> int | None:
    """`pdfmd notes.txt --text-to-markdown`: read the .txt file as Markdown through batchocr (headings, lists, tables and
    paragraphs guessed from how it is typed; the words never change). With `-o x.md` that is the whole job (returns its
    status). Otherwise the Markdown is written beside the text as notes.md (never over a file that is there) and
    replaces the .txt in the arguments (returns None), so the usual build goes on from it."""
    mode = text_to_markdown_mode(args)
    paths = list(args.path or [])
    if mode is None or not paths or any(path.suffix.lower() != ".txt" for path in paths):
        return None
    if args.batch or args.report:
        return None
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"{path}: no such file")
    command = find_batchocr()
    if command is None:
        raise SystemExit(batchocr_missing_message())
    version = core.batchocr_version(command)
    if version is not None and version < BATCHOCR_TEXT_MIN:
        raise SystemExit(batchocr_missing_message(version).replace(
            ".".join(map(str, core.BATCHOCR_MIN)), ".".join(map(str, BATCHOCR_TEXT_MIN))))
    out = args.out
    only_markdown = out is not None and out.suffix.lower() in (".md", ".markdown")
    structure = mode
    produced: list[Path] = []
    for path in paths:
        if only_markdown and len(paths) == 1:
            target = out
        else:
            target = path.with_suffix(".md")
            if target.exists():
                raise SystemExit(f"{target} exists already: pdfmd does not write over it. Remove it, or name another "
                                 "file with -o x.md (a Markdown output is the conversion alone)")
        target.parent.mkdir(parents=True, exist_ok=True)
        call = [*command, str(path), "--to", "md", "-o", str(target), "--txt-structure", structure]
        if not args.verbose:
            call.append("-q")
        print(f"ROUTE  {path.name} -> batchocr"
              + (f" {'.'.join(map(str, version))}" if version else "") + f" (txt to Markdown, {structure})", file=sys.stderr)
        code = subprocess.run(call).returncode
        if code != 0 or not target.is_file():
            return code or 1
        produced.append(target)
    if only_markdown:
        return 0
    print("NOTE  the Markdown is kept beside the text file: " + ", ".join(path.name for path in produced), file=sys.stderr)
    args.path = produced
    return None
