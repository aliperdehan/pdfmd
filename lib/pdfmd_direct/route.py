"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_direct.route`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported.

The routes that build a document without Pandoc's discovery: the choice of a direct route for a `.typ` or `.html` input
(`direct_route`, which `run_main` asks for every single file, with `DIRECT_SUFFIXES` and `DIRECT_READERS`), the build itself
(`convert_direct`, `_convert_direct`, and `direct_defaults` for `--apply-defaults`), which hands the work to the package's
`typst` and `html` modules, and a `.qmd` handed whole to the Quarto CLI (`convert_qmd`). lib/pdfmd_run reads the three
public ones as `core.X` (the names table)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from pdfmd_base import core
from pdfmd_log import emit


DIRECT_SUFFIXES = {".typ": "typst", ".typst": "typst", ".html": "html", ".htm": "html", ".xhtml": "html"}


DIRECT_READERS = {"typst": ("typst",), "html": ("html", "html5")}


def direct_route(path: Path, target_format: str, from_format: str | None, no_auto: list[str] | None,
                 engine_request: str | None, announce: bool = True) -> str | None:
    """`typst` or `html` when this input is finished enough to go straight to its engine (a `.typ` to Typst, an
    `.html` to WeasyPrint or a browser), else None: the Pandoc route, which is also what is left when the tool for
    the direct one is not installed. `--no-auto typstdirect|htmldirect`, an explicit `--from`, a target other than
    PDF, or an `-e` naming an engine of another kind all keep the Pandoc route."""
    kind = DIRECT_SUFFIXES.get(path.suffix.lower())
    if kind is None or target_format != "pdf" or core.auto_disabled(no_auto, kind + "direct"):
        return None
    if from_format is not None and from_format.casefold().split("+")[0] not in DIRECT_READERS[kind]:
        return None
    try:
        import pdfmd_direct as direct
    except ImportError:
        return None
    if kind == "typst":
        if not direct.typst_accepts_request(engine_request):
            return None
        if not core.engine_executable("typst"):
            if announce:
                emit("warning", None, f"WARN  {core.display_path(path)}: Typst is not installed, so this goes through Pandoc's Typst "
                      "reader, which loses what Pandoc's model cannot hold (`pdfmd --install typst`)", file=sys.stderr)
            return None
        return kind
    if not direct.html_accepts_request(engine_request):
        return None
    text = core.read_text_best_effort(path)
    if not direct.html_attempts(text, engine_request, core.which, core.resolve_soffice):
        if announce:
            emit("warning", None, f"WARN  {core.display_path(path)}: no HTML engine or browser found for a direct build "
                  "(WeasyPrint, Chrome, Edge...); going through Pandoc", file=sys.stderr)
        return None
    return kind


def direct_defaults(source: Path, metadata_request: list[str] | None) -> dict:
    """The settings `--apply-defaults` gives a direct document: those of the metadata files found for it."""
    import pdfmd_direct.defaults as defaults
    found = core.find_metadata(source.parent.resolve(), metadata_request, document_stem=source.stem, document=source)
    files = [] if found is core.AUTO_METADATA_DISABLED or found is None else (found if isinstance(found, list) else [found])
    return defaults.collect([core.metadata_file_yaml(item) for item in files])


def convert_direct(kind: str, source: Path, output: Path, engine_request: str | None,
                   verbose: bool, debug: bool, apply_defaults: bool = False,
                   metadata_request: list[str] | None = None) -> tuple[Path, bool, str]:
    """Build a `.typ` or `.html` file with its own engine; none of Pandoc's discovery (metadata, preambles, filters,
    fonts, margins, the stamp) applies, since none of it goes through Pandoc."""
    import pdfmd_direct as direct
    import pdfmd_direct.defaults as defaults
    given = direct_defaults(source, metadata_request) if apply_defaults else {}
    text = core.read_text_best_effort(source)
    prelude = defaults.typst_prelude(given, text) if kind == "typst" and given else ""
    changed = defaults.apply_to_html(given, text) if kind == "html" and given else text
    copy: Path | None = None
    if (prelude or changed != text) and given:
        # beside the original, so what it refers to by a relative path is found; removed afterwards
        copy = source.with_name(f".{source.stem}.pdfmd-defaults{source.suffix}")
        copy.write_text(prelude + text if kind == "typst" else changed, encoding="utf-8")
        emit("verbose", "APPLYDEFAULTS", f"AUTO APPLYDEFAULTS  {core.display_path(source)}: " + ", ".join(sorted(given)), shown=verbose)
    try:
        return _convert_direct(kind, source, copy or source, output, engine_request, verbose, debug, direct,
                               prelude.count("\n"), text)
    finally:
        if copy is not None:
            copy.unlink(missing_ok=True)


def _convert_direct(kind: str, source: Path, built: Path, output: Path, engine_request: str | None,
                    verbose: bool, debug: bool, direct, offset: int, text: str) -> tuple[Path, bool, str]:
    if kind == "typst":
        fonts = core.fonts_directory() if core.managed_index() is not None and core.managed_index().faces else None
        ok, reason = direct.compile_typst(core.engine_executable("typst"), built, output,
                                          str(fonts) if fonts else None, lambda command, cwd: core.log_cmd(command, cwd, verbose))
        if built != source:             # the message names the copy and counts the added lines: say it as the file is
            reason = re.sub(re.escape(built.name) + r":(\d+)", lambda found: f"{source.name}:{max(1, int(found.group(1)) - offset)}", reason)
            reason = reason.replace(built.name, source.name)
            reason = re.sub(r"(?m)^(\s*)(\d+)( │)", lambda found: f"{found.group(1)}{max(1, int(found.group(2)) - offset)}{found.group(3)}", reason)
        if ok:
            core.record_engine("typst")
        if ok:
            emit("verbose", "TYPSTDIRECT", f"AUTO TYPSTDIRECT  {core.display_path(source)}: compiled with Typst directly (no Pandoc)", shown=verbose)
        else:
            emit("warning", None, f"WARN  {core.display_path(source)}: typst failed", file=sys.stderr)
        return source, ok, reason
    order = direct.html_attempts(text, engine_request, core.which, core.resolve_soffice)
    browser = any(name in dict(order) for name in direct.BROWSER_NAMES)
    advice = (" (a browser would: -e chrome, edge or chromium)" if browser
              else "; no browser was found (Chrome, Chromium, Edge, Brave)")
    if order and order[0][0] == "weasyprint" and direct.has_scripts(text):
        emit("warning", None, f"WARN  {core.display_path(source)}: the page has scripts and WeasyPrint does not run them, so what they draw "
              "is missing" + advice, file=sys.stderr)
    if order and order[0][0] == "weasyprint" and direct.has_mathml(text):
        emit("warning", None, f"WARN  {core.display_path(source)}: the page has MathML and WeasyPrint does not draw it, so its formulas "
              "print as flat text" + advice, file=sys.stderr)

    def failed(name: str, reason: str, remaining: list[str]) -> None:
        fake = subprocess.CompletedProcess(args=[name], returncode=1, stdout="", stderr=reason)
        core.report_engine_failure(core.display_path(source), name, fake, remaining, debug)

    ok, reason, used = direct.render_html(built, output, order, soffice_convert=lambda src, out: core.run_soffice_convert(src, out, verbose),
                                          on_failure=failed, log=lambda command, cwd: core.log_cmd(command, cwd, verbose))
    if ok and used:
        core.record_engine(str(used))
    if ok:
        emit("verbose", "HTMLDIRECT", f"AUTO HTMLDIRECT  {core.display_path(source)}: {used} (no Pandoc)", shown=verbose)
    return source, ok, reason


def convert_qmd(source: Path, output: Path, target_format: str,
                variables: list[str], pandoc_options: list[str], verbose: bool = False) -> tuple[Path, bool, str]:
    """Render a Quarto document (.qmd) via the Quarto CLI, not Pandoc directly.

    Pandoc has no idea what a .qmd file is -- it silently falls back to
    treating it as plain Markdown, so executable code chunks (R/Python/Julia,
    run through knitr or Jupyter) never get executed: figures don't render
    and the chunk syntax leaks into the output as literal text. Quarto's own
    CLI is what actually knows how to run those chunks, so .qmd is handed off
    to it entirely; none of Pandoc's metadata-file/preamble/Lua-filter
    machinery in this script applies here -- Quarto has its own, separate
    project and metadata system.

    NOTE: this path could not be exercised where this script was written (no
    Quarto install available there) -- it follows Quarto's documented CLI,
    but please flag anything that doesn't match your installed version.
    """
    quarto = core.which("quarto")
    if not quarto:
        return source, False, (
            "Quarto was not found on PATH. Install it from https://quarto.org to render "
            ".qmd files -- Pandoc alone cannot execute their R/Python/Julia code chunks, "
            "which is why a plain Pandoc conversion silently drops figures and computed output."
        )
    if variables or pandoc_options:
        emit("warning", None, f"WARN  {source}: -V and passthrough Pandoc options don't apply to Quarto "
              "rendering and were ignored; use Quarto's own -P/-M flags instead", file=sys.stderr)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Quarto's own -o has historically wanted a bare filename in the source's
    # directory, so render there and move the result to the real destination
    # afterward (covers -o/--out pointing elsewhere, or --destination-cwd).
    cmd = [quarto, "render", source.name, "--to", target_format, "-o", output.name]
    # Quarto forwards these Pandoc arguments after its execution/content filters.
    cmd += core.deferred("pdfmd_filters.hidden", "mark_args")(source, [])
    cmd += core.calc_filter_args(source, [])
    cmd += core.deferred("pdfmd_filters.hidden", "finish_args")()
    from pdfmd_buildinfo.build import record_tex, record_tex_log, tex_log_state
    log = source.with_suffix(".log")
    previous = tex_log_state(log) if core.BUILD["record"] is not None and target_format in ("pdf", "beamer") else None
    core.log_cmd(cmd, source.parent, verbose)
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=source.parent)
    if core.BUILD["record"] is not None and target_format in ("pdf", "beamer"):
        record_tex_log(log, previous)
        record_tex(result.stdout + "\n" + result.stderr)
    rendered = source.parent / output.name
    if result.returncode == 0 and rendered.exists() and rendered.resolve() != output.resolve():
        rendered.replace(output)
    if result.returncode == 0:
        core.record_engine("quarto")
    return source, result.returncode == 0, (result.stdout + result.stderr)[-3000:]


def build_standalone(kind, source, output, metadata_files, target_format, args, variables, pandoc_options, *, export=None):
    """Build directly, with the same record and timing as the Pandoc route."""
    from pdfmd_buildinfo.build import build_record
    from pdfmd_crop.build import finish_direct

    def build(destination):
        if kind == "quarto":
            return core.convert_qmd(source, destination, target_format, variables, pandoc_options, args.verbose)
        settings = core.config_options().get("apply-defaults", False) if args.apply_defaults is None else args.apply_defaults
        return core.convert_direct(kind, source, destination, args.engine, args.verbose, args.debug,
                                   apply_defaults=settings not in (False, "false", "False", 0, ""),
                                   metadata_request=args.metadata_file)

    core.BUILD.update(engine=None, failed=[], tried=[], chain=None, repaired=[], output=None)
    core.begin_timer()
    with build_record(source, metadata_files) as recorder:
        with core.warning_capture() as seen:
            result = finish_direct(source, output, metadata_files, target_format, args.verbose, export, build)
        built = core.finish_build(result, seen, source, [])
        if built[1]:
            core.backup_after_success(source, [], args.backup, args.verbose, args.backup_format)
        if recorder:
            built.record_path = recorder.finish(built)
        return built
