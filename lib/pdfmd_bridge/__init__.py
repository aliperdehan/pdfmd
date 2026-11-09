"""The bridges to LibreOffice, Calibre and a browser: a document turned into a PDF (or another format) by a program that is not a
PDF engine of Pandoc's. LibreOffice (`run_soffice_convert`, `convert_office_direct` for an office file, `convert_via_soffice_bridge`
for the "soffice" engine, `start_soffice_job` for an odt, rtf or doc target), Calibre (`calibre_html_command`, `calibre_page_options`
with `calibre_author_options`, `run_calibre` for the "calibre" engine, `run_calibre_convert` for its targets) and a headless browser
(`browser_page_css`, `run_browser_print`).

Moved out of `pdfmd.py` unchanged (v3.33.26, SPLIT.md), with `CALIBRE_TABLE_CSS` and `PANDOC_TABLE_STYLE_RE`. `core` is the `pdfmd`
module, bound by `pdfmd.py` when it loads (the first binding wins); the pdfmd names the code uses (`BROWSER_ENGINES`, `CALIBRE_CSS`,
`CALIBRE_OPTIONS`, `CITEPROC_DISABLED`, `DEFAULT_MARGIN`, `HTML_MATH_OPTIONS`, `PARTIAL_METADATA`, `SOFFICE_SHARED_FORMATS`,
`author_names`, `contains_citations`, `csl_args`, `document_filter_args`, `effective_metadata`, `html_math_args`, `log_cmd`, `metadata_cwd`,
`office_finish`, `office_module`, `office_reference`, `pandoc_metadata_order`, `pandoc_version`, `pandoc_working_directory`,
`prepared_latex_inputs`, `report_engine_failure`, `resolve_calibre`, `resolve_soffice`, `resource_path_option`, `run_office_pandoc`,
`run_soffice`, `select_filter_args`, `table_keep_metadata`, `vprint` and `which`) are read as `core.X` when it runs.
`CITEPROC_DISABLED` is rebound by `main`, so it stays in `pdfmd.py`; `core.html_math_args`, `core.pandoc_version`,
`core.resolve_calibre`, `core.resolve_soffice` and `core.which` are patched by tests as `pdfmd.X`, and `pdfmd.run_calibre_convert`
(re-exported here) is patched too, through `finish_convert_job`, which stays. `pdfmd_direct` is imported inside `run_browser_print`,
so neither it nor `pdfmd_office` loads at start. The three functions that `pdfmd.py` decorated with `@timed` are decorated with
`_timed`, which looks `core.timed` up when the function is called (`timed` is defined far below the place where the package loads).
"""

from __future__ import annotations

import atexit
import functools
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp

core = None


def _timed(name):
    """`core.timed(name)` for a function defined before `core.timed` exists: each call is wrapped when it is made."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            return core.timed(name)(function)(*args, **kwargs)
        return wrapper
    return decorate


@_timed("soffice")
def run_soffice_convert(input_path: Path, output: Path, verbose: bool, target: str = "pdf") -> tuple[bool, str]:
    """Convert one file to PDF (or ``target``: doc, rtf, odt, txt, epub: v3.29.1) via headless LibreOffice, into ``output``.

    Runs entirely in a scratch directory (both the conversion's own
    output and its throwaway --env:UserInstallation profile), deleted
    afterward regardless of outcome -- soffice leaves no equivalent of a
    LaTeX engine's .aux/.log, but the scratch profile itself would
    otherwise accumulate under /tmp across every call.
    """
    binary = core.resolve_soffice()
    if binary is None:
        return False, "soffice/LibreOffice not found (checked PATH, 'libreoffice', and the standard macOS app bundle)"
    scratch = Path(mkdtemp(prefix="pdfmd-soffice-"))
    try:
        profile_dir = scratch / "profile"
        cmd = [binary, "--headless", "--norestore",
              f"-env:UserInstallation={profile_dir.as_uri()}",       # a real file URL: on Windows LibreOffice hangs on file://C:\...
              "--convert-to", "txt:Text" if target == "txt" else target, "--outdir", str(scratch), str(input_path)]
        core.log_cmd(cmd, input_path.parent, verbose)
        result = core.run_soffice(cmd, cwd=input_path.parent)
        produced = scratch / f"{input_path.stem}.{target}"
        if result.returncode != 0 or not produced.exists():
            reason = result.stderr.strip() or result.stdout.strip() or f"soffice failed to produce a {target}"
            return False, reason.splitlines()[-1]
        output.parent.mkdir(parents=True, exist_ok=True)
        if produced.resolve() != output.resolve():
            shutil.copy2(produced, output)
        return True, ""
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def convert_office_direct(input_path: Path, output: Path, verbose: bool, debug: bool) -> tuple[bool, str]:
    """Convert an office document straight to PDF -- no Pandoc involved."""
    ok, reason = run_soffice_convert(input_path, output, verbose)
    if ok:
        core.vprint(verbose, f"AUTO OFFICEDIRECT  {input_path}: converted with soffice directly (no Pandoc)")
    else:
        fake_result = subprocess.CompletedProcess(args=["soffice"], returncode=1, stdout="", stderr=reason)
        core.report_engine_failure(str(input_path), "soffice", fake_result, [], debug)
    return ok, reason


def convert_via_soffice_bridge(md_path: Path, output: Path, effective_from: str | None,
                               metadata_files: list[Path], variables: list[str],
                               pandoc_options: list[str], lua_filters: list[Path],
                               csv_filter: Path, no_auto: list[str] | None,
                               verbose: bool, labels: str = "off", title_source: Path | None = None,
                               part_files: list[Path] | tuple = (), partial: bool = False,
                               selection=None) -> tuple[bool, str]:
    """The "soffice" PDF-engine fallback: Pandoc -> .docx -> headless
    LibreOffice -> PDF (the same Word file `-o x.docx` writes: template, native equations and tables, pictures
    for what LaTeX alone can draw; `labels` says where reference numbers come from, see office_label_data). Deliberately skips every LaTeX-only concern
    convert_one's own per-engine run() closure applies for a real engine
    (geometry/mainfont/monofont/preamble/table-width filter) -- none of
    it means anything for an ODT target. Citeproc and a document's own
    auto-discovered Lua filters still apply, same as every other engine.

    The input is what every other engine gets: `title_source` (the document with its title promoted, or cut
    down to the sections asked for), `part_files` (the parts of a split document, joined after it) and
    `partial` (a build of some parts only), so parts mode and `doc#section` work here as everywhere else.
    """
    scratch = Path(mkdtemp(prefix="pdfmd-soffice-src-"))
    try:
        odt = scratch / f"{md_path.stem}.docx"
        pandoc_cwd = core.pandoc_working_directory(core.metadata_cwd(metadata_files, md_path.parent))

        def note(kind: str, detail: str) -> None:
            core.vprint(verbose, f"AUTO {kind}  {detail}")
        with core.prepared_latex_inputs([title_source or md_path, *core.pandoc_metadata_order(metadata_files)], False, drop_embedded_preamble=True) as prepared:
            source, *prepared_metadata = prepared
            cmd = ["pandoc", str(source), *map(str, part_files), "-o", str(odt), "-t", "docx"]
            if effective_from:
                cmd += ["-f", effective_from]
            for metadata in prepared_metadata:
                cmd += ["--metadata-file", str(metadata)]
            if partial:
                cmd += core.PARTIAL_METADATA
            cmd += core.table_keep_metadata(md_path, metadata_files)
            cmd += core.resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
            for variable in variables:
                cmd += ["-V", variable]
            cmd += core.document_filter_args(md_path, md_path, metadata_files, no_auto, csv_filter, pandoc_options,
                                        crossref_sources=[md_path, *part_files], cellalign_early=True)
            cmd += core.select_filter_args(selection)
            if core.contains_citations(md_path) and "--citeproc" not in pandoc_options and not core.CITEPROC_DISABLED:
                cmd.append("--citeproc")
            if "--citeproc" in cmd or "--citeproc" in pandoc_options:
                cmd += core.csl_args([md_path], metadata_files, pandoc_options, no_auto)
            # pandoc_options after --citeproc: any --lua-filter/--filter a caller
            # passes through needs resolved citations already in the AST, same
            # invariant as the auto-discovered lua_filters below (see run()'s
            # matching comment in convert_one).
            # the LaTeX the document uses is made native or drawn (no PDF build for its numbers here: LaTeX is what failed)
            with core.office_reference(md_path, metadata_files, variables, "docx", odt, pandoc_options, no_auto, note,
                                  labels=labels, force_filter=True) as office_arguments:
                cmd += office_arguments
                cmd += pandoc_options
                for lua_filter in lua_filters:
                    cmd += ["--lua-filter", str(lua_filter)]
                cmd += office_arguments.filter_arguments
                if office_arguments.filter_arguments:
                    result = core.run_office_pandoc(cmd, odt, office_arguments, pandoc_cwd, verbose)
                else:
                    core.log_cmd(cmd, pandoc_cwd, verbose)
                    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=pandoc_cwd)
                core.office_finish(office_arguments, md_path, verbose)
        if result.returncode != 0 or not odt.exists():
            return False, result.stderr.strip() or "pandoc failed to produce an intermediate .docx"
        return run_soffice_convert(odt, output, verbose)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# and its tables are full-width blocks that scroll sideways (`display: block; overflow-x: auto`): on paper a caption was
# cut off at the width of a narrow table ("Table 1: Labe"). While that style is in, a table is a table at its natural
# width, centred, and its caption up to 4in wide, as LaTeX's longtable sets them (v3.28.3). A numbered equation (the
# LaTeX filter's three-cell table) spans the line, its number at the margin, without the rules of a table.
PANDOC_TABLE_STYLE_RE = re.compile(r"\btable\s*\{[^{}]*overflow-x:\s*auto")
CALIBRE_TABLE_CSS = ("table { display: table; width: auto; overflow: visible; margin-left: auto; margin-right: auto; }\n"
                     "table caption { width: max-content; max-width: 4in; margin-left: auto; margin-right: auto; }\n"
                     'table[data-custom-style="PdfmdEquation"] { width: 100%; }\n'
                     'table[data-custom-style="PdfmdEquation"] tbody { border: none; }\n')


@contextmanager
def calibre_html_command(cmd: list[str], engine: str) -> Iterator[tuple[list[str], Path | None]]:
    """The Pandoc command of one engine run, and for "calibre" where it writes instead of the PDF: the same
    command (filters, citations, metadata, fonts) with `--pdf-engine=calibre` turned into a standalone,
    self-contained HTML5 page with MathML, in a scratch folder that is gone afterwards."""
    if engine != "calibre" and engine not in core.BROWSER_ENGINES:
        yield cmd, None
        return
    scratch = Path(mkdtemp(prefix="pdfmd-calibre-"))
    try:
        html = scratch / "document.html"
        command = list(cmd)
        position = command.index(f"--pdf-engine={engine}")
        command[position:position + 1] = ["-t", "html5", "--standalone",
                                          "--embed-resources" if core.pandoc_version() >= (2, 19) else "--self-contained"]
        command[command.index("-o") + 1] = str(html)
        command += ["-M", "pdfmd-no-named-pages=1"]          # Calibre's PDF cannot name page types: markup: landscape says so
        if not any(item.startswith(core.HTML_MATH_OPTIONS) for item in command):
            command += core.html_math_args("mathml")
        yield command, html
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def calibre_author_options(metadata: dict) -> list[str]:
    """`--authors "A & B"` when the page Pandoc writes would not name every author: its `<meta name="author">` tags
    (`author-meta`) hold the authors written as text and drop one written as a mapping (`- name: B`), so Calibre kept only
    the others, or wrote `Unknown`. Authors that are all text are left to Pandoc (it writes their markup as plain text), and a
    document's own `author-meta` is left alone."""
    value = metadata.get("author")
    if "author-meta" in metadata or not any(isinstance(item, dict) for item in (value if isinstance(value, list) else [value])):
        return []
    names = core.author_names(value)
    return ["--authors", " & ".join(names)] if names else []


def calibre_page_options(md_path: Path, metadata_files: list[Path], variables: list[str]) -> list[str]:
    """ebook-convert's options from the document's metadata: the page, i.e. the paper and margins the document asks for
    (papersize, geometry, margin, classoption, read as for a Word file), else Letter and DEFAULT_MARGIN like the LaTeX
    engines, in points; its language; and its authors where Pandoc's page leaves some out (calibre_author_options)."""
    metadata = core.effective_metadata(md_path, metadata_files, variables)
    authors = calibre_author_options(metadata)
    module = core.office_module()
    if module is None:
        return authors
    spec = module.spec_from_metadata(metadata, None, "exact")
    width, height = spec.page_size()
    default = module.length_to_twips(core.DEFAULT_MARGIN) or 1440
    points = lambda twips: f"{twips / 20:g}"
    options = ["--custom-size", f"{points(width)}x{points(height)}", "--unit", "point"]
    for side in ("left", "right", "top", "bottom"):
        options += [f"--pdf-page-margin-{side}", points(spec.margins.get(side, default))]
    if spec.lang:
        options += ["--language", spec.lang]
    return options + authors


@_timed("calibre")
def run_calibre(html: Path, output: Path, page_options: list[str], verbose: bool) -> subprocess.CompletedProcess:
    """`ebook-convert` the HTML page into `output` (written beside the page first, so a failed run leaves no
    half-written PDF). Qt runs offscreen on macOS and Linux: no window, and no display needed on a server."""
    binary = core.resolve_calibre()
    if binary is None:
        return subprocess.CompletedProcess(["ebook-convert"], 1, "", "Calibre's ebook-convert was not found")
    css = html.with_name("pdfmd-calibre.css")
    head = html.read_text(encoding="utf-8", errors="replace").split("</head>", 1)[0]
    css.write_text(core.CALIBRE_CSS + (CALIBRE_TABLE_CSS if PANDOC_TABLE_STYLE_RE.search(head) else ""), encoding="utf-8")
    produced = html.with_name("document.pdf")
    cmd = [binary, str(html), str(produced), *core.CALIBRE_OPTIONS, "--extra-css", str(css), *page_options]
    environment = dict(os.environ)
    if sys.platform != "win32":
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    core.log_cmd(cmd, html.parent, verbose)
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=html.parent, env=environment)
    if result.returncode != 0 or not produced.is_file():
        said = [line for line in (result.stderr + "\n" + result.stdout).splitlines() if line.strip()]
        return subprocess.CompletedProcess(cmd, result.returncode or 1, "",
                                           "ebook-convert failed: " + " | ".join(said[-3:] or ["no PDF written"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(produced, output)
    return subprocess.CompletedProcess(cmd, 0, "", "")


def start_soffice_job(args, goal: str, target_format: str) -> dict:
    """The same for a LibreOffice target (v3.29.1): `args` pointed at the Word file Pandoc writes in a scratch folder."""
    if args.batch or args.report or args.presentation:
        raise SystemExit(f"{goal} is made through LibreOffice one document at a time: not with "
                         f"{'-b' if args.batch else '-r' if args.report else '-p'} (yet)")
    if core.resolve_soffice() is None:
        raise SystemExit(f"{target_format} is written by LibreOffice, which was not found (checked PATH, 'libreoffice' and the "
                         "standard macOS app bundle). Install it: `brew install --cask libreoffice`, "
                         "`winget install TheDocumentFoundation.LibreOffice`, your package manager, or libreoffice.org.")
    if goal in core.SOFFICE_SHARED_FORMATS:
        print(f"NOTE  -e soffice: {goal} is made by LibreOffice from the Word file Pandoc writes; without -e soffice Pandoc "
              "writes it from the document itself", file=sys.stderr)
    scratch = Path(mkdtemp(prefix="pdfmd-soffice-target-"))
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    job = {"tool": "soffice", "goal": goal, "final": args.out, "scratch": scratch, "open": args.open,
           "intermediate": "document.docx"}
    args.to, args.out, args.engine, args.open = "docx", scratch / "document.docx", None, False
    return job


def run_calibre_convert(source: Path, output: Path, verbose: bool, extra: list[str] | None = None) -> subprocess.CompletedProcess:
    """`ebook-convert source output`, written into a scratch folder first (so a failed run leaves nothing half-written, and
    nothing lands beside `source`). Qt runs offscreen as for the PDF route."""
    binary = core.resolve_calibre()
    if binary is None:
        return subprocess.CompletedProcess(["ebook-convert"], 1, "", "Calibre's ebook-convert was not found")
    scratch = Path(mkdtemp(prefix="pdfmd-ebook-convert-"))
    try:
        produced = scratch / ("calibre-output" + output.suffix)
        cmd = [binary, str(source), str(produced), *(extra or [])]
        environment = dict(os.environ)
        if sys.platform != "win32":
            environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        core.log_cmd(cmd, source.parent, verbose)
        result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=scratch, env=environment)
        if result.returncode != 0 or not produced.is_file():
            said = [line for line in (result.stderr + "\n" + result.stdout).splitlines() if line.strip()]
            return subprocess.CompletedProcess(cmd, result.returncode or 1, "",
                                               "ebook-convert failed: " + " | ".join(said[-3:] or ["no file written"]))
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, output)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def browser_page_css(md_path: Path, metadata_files: list[Path], variables: list[str]) -> str:
    """The page a browser prints, as CSS: `@page` with the paper and margins the document asks for (papersize, geometry,
    margin, classoption, read as for a Word file), else Letter and DEFAULT_MARGIN like the LaTeX engines. In points."""
    module = core.office_module()
    if module is None:
        return ""
    spec = module.spec_from_metadata(core.effective_metadata(md_path, metadata_files, variables), None, "exact")
    width, height = spec.page_size()
    default = module.length_to_twips(core.DEFAULT_MARGIN) or 1440
    points = lambda twips: f"{twips / 20:g}pt"
    margins = " ".join(points(spec.margins.get(side, default)) for side in ("top", "right", "bottom", "left"))
    return (f"@page {{ size: {points(width)} {points(height)}; margin: {margins}; }}\n"
            f"@page landscape {{ size: {points(height)} {points(width)} !important; }}\n")        # for markup: landscape, the same paper turned


@_timed("browser print")
def run_browser_print(html: Path, output: Path, engine: str, page_css: str, verbose: bool) -> subprocess.CompletedProcess:
    """Print the page with headless `engine` (chrome, chromium, edge, brave) into `output`: the page gets the paper and
    margins as `@page` and the print style of CALIBRE_CSS (Pandoc's own is for a screen). The browser writes into a scratch
    folder first, so a failed run leaves no half-written PDF."""
    try:
        import pdfmd_direct as direct
    except ImportError:
        return subprocess.CompletedProcess(["browser"], 1, "", "pdfmd_direct, the folder of pdfmd's browser support, is missing")
    executable = direct.find_browser(engine, core.which)
    if executable is None:
        return subprocess.CompletedProcess([engine], 1, "", f"{engine} was not found")
    text = html.read_text(encoding="utf-8", errors="replace")
    head = text.split("</head>", 1)[0]
    style = core.CALIBRE_CSS + (CALIBRE_TABLE_CSS if PANDOC_TABLE_STYLE_RE.search(head) else "") + page_css
    page = html.with_name("document-print.html")
    page.write_text(text.replace("</head>", f"<style>\n{style}</style>\n</head>", 1) if "</head>" in text
                    else f"<style>\n{style}</style>\n{text}", encoding="utf-8")
    ok, reason, _ = direct.render_html(page, output, [(engine, executable)],
                                       log=lambda command, cwd: core.log_cmd(command, cwd, verbose))
    return subprocess.CompletedProcess([engine], 0 if ok else 1, "", "" if ok else f"{engine} failed: {reason}")
