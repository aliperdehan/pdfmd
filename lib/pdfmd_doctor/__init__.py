"""`pdfmd --doctor` and the shell completions: the page on everything pdfmd uses (`doctor_report`: tools, fonts, PDF reading, config, cache,
what to run to fix what is missing; `deep_checks` for `--doctor --deep`, `foreign_commands`, `folder_size`), the notes it adds to a tool
(`tool_note`, `user_path_hint`, `pandoc_limits`) and the command line as data for the completion scripts (`completion_options`,
`completion_script`).

Moved out of `pdfmd.py` unchanged (v3.33.31, SPLIT.md), with `DEEP_SAMPLE` and `PANDOC_FEATURES`. `core` is the `pdfmd` module, bound by `pdfmd.py`
when it loads (the first binding wins); the pdfmd names the code uses are read as `core.X` when it runs, including the state that `main`
rebinds (`TEX_FOUND_AT`, `TRANSLIT_PACKS`: they stay in `pdfmd.py`) and the functions that tests patch as `pdfmd.X` (`cache_root`, `data_root`,
`engine_executable`, `katex_runtime`, `mathjax_fonts`, `mathjax_runtime`, `pandoc_version`, `resolve_calibre`, `resolve_soffice`,
`system_font_missing`, `which`); `find_batchocr` too, pdfmd_routing's, which this module imported directly until v3.33.49.
`core.__file__` is `pdfmd.py` itself (`--doctor` prints where pdfmd is and `--doctor --deep` runs it on a sample). Nothing heavy is imported at the top: `importlib.metadata`, `platform`, `pdfmd_direct`, `pdfmd_images`, `pdfmd_unicode`,
`pdfmd_setup` and `pdfmd_inkmd` stay inside the functions, as they were, so none of them loads at start.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pdfmd_base import core
from pdfmd_log import emit


def tool_note(name: str) -> str:
    """What ``--doctor`` adds to a tool that is not found on PATH: where it was found, or the setting that names it."""
    if name not in core.FOUND_TOOLS:
        return ""
    from pdfmd_engines.tools import tool_setting
    if source := tool_setting(name):
        return f"set by {source}"
    file, how = core.TOOLS_FOUND.get(name) or core.locate_tool(name)
    if how == "key":
        return f"set by options.{core.FOUND_TOOLS[name][0]}"
    if how == "probe":
        return f"found at {Path(file).parent}, not on PATH (pdfmd uses it anyway)"
    return ""


def user_path_hint() -> str:
    """The closing line of ``--doctor`` on Windows when a tool pdfmd found is not on the user PATH; "" otherwise."""
    if sys.platform != "win32" or not core.tool_folders_off_path():
        return ""
    try:
        from pdfmd_setup import userpath
        registry = userpath.Registry()
        change = userpath.plan_add(registry.read(), registry.machine(), core.tool_folders_off_path())
    except (ImportError, OSError):
        return ""
    if not change.add:
        return ""
    return (f"NOTE  {len(change.add)} tool folder{'' if len(change.add) == 1 else 's'} found off PATH: `pdfmd --user-path add` puts "
            f"{'it' if len(change.add) == 1 else 'them'} on your user PATH (it asks first; `pdfmd --user-path remove` takes them off)")


PANDOC_FEATURES = (
    ((3, 4), "Word files: the borderless style of numbered equations (the equation and its number sit in a plain table)"),
    ((3, 8, 2), "a table caption's {#id} read as the table's identifier: --extract-tables leaves a table whose caption "
                "has one, and a table's own {widths=... word-floor=...} reaches the width filter"),
)


def pandoc_limits(version: tuple[int, ...]) -> list[str]:
    """What the given Pandoc version does without, from PANDOC_FEATURES."""
    return [text for needed, text in PANDOC_FEATURES if version < needed]


def folder_size(folder: Path) -> int:
    total = 0
    try:
        for path in folder.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


DEEP_SAMPLE = """---
title: pdfmd smoke test
---

# Heading

Text with math $x^2 + \\alpha$, an accent (café), `code`, ~~struck out~~, and a table:

| a | b |
|---|---|
| 1 | 2 |
"""


def deep_checks(engines: list[str], timeout: int = 180) -> list[tuple[str, bool, str]]:
    """--doctor --deep: build a small page with each engine by running pdfmd itself (the way a user would), in a
    scratch folder. [(engine, built, seconds or the reason it failed)]; an engine that hangs is stopped."""
    from pdfmd_engines.tools import pinned_flags
    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="pdfmd-deep-") as scratch:
        folder = Path(scratch)
        (folder / "sample.md").write_text(DEEP_SAMPLE, encoding="utf-8")
        environment = {**os.environ, "PDFMD_NO_PROMPT": "1"}
        environment.pop("PDFMD_STRICT", None)
        for entry in engines:
            engine, _, ebook = entry.partition(":")            # "calibre:azw3" builds that ebook (v3.29.5), not a PDF
            output = folder / f"{engine}.{ebook or 'pdf'}"
            started = time.monotonic()
            try:
                done = subprocess.run([sys.executable, str(Path(core.__file__).resolve()), "sample.md", "-e", engine,
                                       "-o", output.name, "--no-backup", "--no-stamp", *pinned_flags()],
                                      capture_output=True, encoding="utf-8", errors="replace", cwd=folder, env=environment, timeout=timeout)
            except subprocess.TimeoutExpired:
                results.append((entry, False, f"no answer after {timeout} s"))
                continue
            seconds = time.monotonic() - started
            if done.returncode == 0 and output.is_file() and (
                    output.stat().st_size > 0 if ebook else output.read_bytes().startswith(b"%PDF")):
                results.append((entry, True, f"{seconds:.1f} s"))
                continue
            text = done.stdout + done.stderr
            found = re.search(r"failed \((.*?)\); (?:no more engines|trying|engine-fallback)", text)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            why = found.group(1) if found else (lines[-1][:160] if lines else "no output")
            cause = re.search(r"(?m)^\s+cause: (.+)$", text)                       # the TeX cause line (v3.30.35), when there is one
            results.append((entry, False, f"{why}; {cause.group(1)}" if cause else why))
    return results


def foreign_commands() -> list[tuple[str, str]]:
    """The commands this install provides (``pdfmd``, ``mdpdf``, ``md2pdf``, ``inkmd`` ...) whose name another program answers on the
    PATH: (name, path). Several tools share those names and the one installed last owns each. Empty when pdfmd is not installed as
    a package (a checkout, a lone pdfmd.py) or when every name is its own."""
    import importlib.metadata  # here, not at the top: only this needs it (start-up time, v3.32.55)
    try:
        dist = importlib.metadata.distribution("pdfmd-cli")
    except importlib.metadata.PackageNotFoundError:
        return []
    names = {entry.name for entry in dist.entry_points if entry.group == "console_scripts"}
    ours: dict[str, set[Path]] = {}
    for file in dist.files or []:
        if file.stem in names and file.parent.name in ("bin", "Scripts"):
            try:
                ours.setdefault(file.stem, set()).add(Path(dist.locate_file(file)).resolve())
            except OSError:
                continue
    found: list[tuple[str, str]] = []
    for name in sorted(names):
        path = core.which(name)
        if path and ours.get(name) and Path(path).resolve() not in ours[name]:
            found.append((name, path))
    return found


def doctor_report(deep: bool = False, *, as_json: bool = False) -> bool:
    """`--doctor`: one page on everything pdfmd uses (tools, fonts, PDF reading, config, cache) and
    what to run to fix what is missing. True unless no PDF can be made at all. ``deep`` also builds a small
    page with each engine, to find the one that is installed but cannot make a PDF."""
    import platform
    problems: list[tuple[str, str]] = []

    checks = []

    def say(*args) -> None:
        if not as_json:
            print(*args)

    def line(check_id: str, ok: bool | None, text: str, fix: str | None = None, why: str | None = None,
             *, required: bool = False) -> None:
        if as_json:
            status = "info" if ok is None else "ok" if ok else "fail" if required else "warn"
            checks.append({"id": check_id, "status": status, "message": text})
        else:
            emit("result", None, f"{'OK  ' if ok else 'MISS' if ok is False else 'NOTE'}  {text}")
        if ok is False and fix:
            problems.append((why or text, fix))

    say(f"pdfmd {core.PDFMD_VERSION} -- Python {platform.python_version()}, {platform.system()} {platform.machine()}")
    say(f"  {Path(core.__file__).resolve()}")
    say("\nMarkdown to PDF:")
    pandoc = core.which("pandoc")
    version = ".".join(map(str, core.pandoc_version())) if pandoc else ""
    line("pandoc", bool(pandoc), "pandoc" + (f" {version}  ({pandoc})" if pandoc else "")
         + (f"  -- {tool_note('pandoc')}" if pandoc and tool_note("pandoc") else ""),
         "pdfmd --install pandoc", "Pandoc (without it only the plain built-in renderer runs)")
    if pandoc and core.pandoc_version() < core.PANDOC_MIN:
        line("pandoc-version", False, f"pandoc {version} is older than {'.'.join(map(str, core.PANDOC_MIN))}, the oldest pdfmd is tested with",
             "pdfmd --install pandoc", "a newer Pandoc (this one may work, but is not tested)")
    if pandoc:
        for index, limit in enumerate(pandoc_limits(core.pandoc_version())):
            line(f"pandoc-limit:{index}", None, f"with Pandoc {version}, not available: {limit}")
    engines = core.installed_engines()
    if core.TEX_FOUND_AT is not None:
        line("tex-location", None, f"TeX found at {core.TEX_FOUND_AT}, which is not on PATH; pdfmd uses it for its own runs "
                   "(add the folder to PATH to use it elsewhere, or set PDFMD_TEX_BIN for another place)")
    line("pdf-engines", bool(engines), "PDF engines: " + (", ".join(engines) if engines else "none"),
         "pdfmd --install typst", "a PDF engine (Typst is the quickest)")
    if engines:
        say(f"      used first: {engines[0]}" + ("" if any(e in core.LATEX_ENGINES for e in engines)
                                               else "  (no TeX: LaTeX packages and some math will not work)"))
        last = [engine for engine in core.automatic_engines() if engine in (*core.BROWSER_ENGINES, "calibre")]
        if last:
            say(f"      last resorts, after those: {', '.join(last)}")
    if not deep:
        say("NOTE  Run pdfmd --doctor --deep to test-compile a page with each engine.")
    if not pandoc or not engines:
        native = core.available_native_engines()
        line("native-renderer", bool(native), "built-in renderer: " + (", ".join(native) if native else "none"), required=True)
    for name in ("typst", "chrome"):
        if tool_note(name):
            where = core.locate_tool(name)[0] or core.TOOLS_FOUND.get(name, (None, ""))[0]
            line(f"tool-location:{name}", None, f"{name}: {where}  -- {tool_note(name)}")
    quarto = core.which("quarto")
    line("quarto", None, "quarto: " + (quarto or "not installed (only .qmd files need it)"))
    soffice = core.resolve_soffice()
    line("soffice", None, "LibreOffice: " + (soffice or ("turned off by `soffice-timeout: 0`" if core.soffice_limit() == 0
                                              else "not installed (only Office files need it)"))
         + (f"  -- {tool_note('soffice')}" if soffice and tool_note("soffice") else ""))
    calibre = core.resolve_calibre()
    line("calibre", None, "Calibre: " + (calibre or "not installed (only -e calibre and the ebook formats azw3, mobi ... need it; `pdfmd --install calibre`)"))
    if core.which("weasyprint"):
        jax, runtime = core.mathjax_runtime(), core.katex_runtime()
        if jax and runtime:
            said = (f"typeset by MathJax {jax[1].name} (fonts {', '.join(core.mathjax_fonts(jax[1]))}), KaTeX {runtime[1].name} "
                    f"for what MathJax cannot read (node {jax[0]})")
        elif jax:
            said = (f"typeset by MathJax {jax[1].name} (fonts {', '.join(core.mathjax_fonts(jax[1]))}; node {jax[0]}), "
                    "a formula it cannot read is printed as text")
        elif runtime:
            said = (f"typeset by KaTeX {runtime[1].name} (node {runtime[0]}); MathJax typesets more of it "
                    "(pdfmd --install math:mathjax)")
        else:
            said = "printed as text, no MathJax or KaTeX"
        line("weasyprint-math", bool(jax or runtime), "math in WeasyPrint's PDFs: " + said,
             "pdfmd --install math:mathjax" if not jax else "pdfmd --install math:katex",
             "MathJax, for math in WeasyPrint's PDFs (WeasyPrint itself prints it as text)" if not jax
             else "KaTeX, behind MathJax, for what it cannot read")
    try:
        import pdfmd_direct as direct
        browsers = [name for name in direct.BROWSER_NAMES if direct.find_browser(name, core.which)]
        line("direct-routes", None, "HTML files go straight to: " + (", ".join(["weasyprint" if core.which("weasyprint") else "", *browsers])
                                                     .strip(", ") or "no engine (pip install weasyprint)")
                   + "; .typ files to: " + ("typst" if core.engine_executable("typst") else "no Typst (pdfmd --install typst)"))
    except ImportError:
        pass
    try:
        import pdfmd_images
        converters = pdfmd_images.available_converters(core.which, core.resolve_soffice)
        line("svg-chain", None, "SVG converter chain: " + " -> ".join(pdfmd_images.CONVERTERS))
        line("svg-converters", None, "SVG images and diagrams to PDF/PNG: " + (", ".join(converters) if converters else
             "nothing installed (" + pdfmd_images.install_hint() + ")"))
    except ImportError:
        pass
    from pdfmd_crop import tools as crop_tools
    line("pdf-ink-chain", None, "PDF ink measurement: " + " -> ".join(crop_tools.INK_CHAIN))
    line("pdf-png-chain", None, "PDF to PNG: " + " -> ".join(crop_tools.PNG_CHAIN))
    line("pdf-svg-chain", None, "PDF to SVG: " + " -> ".join(crop_tools.SVG_CHAIN))
    for name, path, source in crop_tools.reports():
        found = path or source
        line(f"pdf-finishing:{name}", None, f"PDF finishing {name}: {found or 'not found'}"
             + (f"  -- {tool_note(name)}" if path and tool_note(name) else ""))
    drawn_by = [f"{name} ({tool}{', ' + tool_note(tool) if tool_note(tool) else ''})" for tool, name, _ in core.DIAGRAM_TOOLS if core.which(tool)]
    line("diagrams", None, "diagrams written as code (```dot, ```d2, ```mermaid) are drawn with: "
         + (", ".join(drawn_by) if drawn_by else "nothing installed ("
            + "; ".join(f"{name}: {hint.split('  |')[0]}" for _, name, hint in core.DIAGRAM_TOOLS) + ")"))
    has_rdkit = importlib.util.find_spec("rdkit") is not None
    line("rdkit", None, "chemical structures (```smiles blocks) are drawn with: "
         + ("RDKit" if has_rdkit else "nothing installed (pip install rdkit)"))
    from pdfmd_yaml_support import description
    line("yaml", core.yaml is not None, "YAML: " + description(core.yaml), "pip install --force-reinstall pdfmd-cli",
         "YAML support (installation is incomplete)")
    found = importlib.util.find_spec("pypdf") is not None
    line("pypdf", found, "python package pypdf", "pip install pypdf", "the Python package pypdf (PDF stamping is skipped without it)")

    say("\nFonts and scripts:")
    module = core.unicode_module()
    if module is None:
        line("unicode", False, "pdfmd_unicode package", "pip install --force-reinstall pdfmd-cli", "the pdfmd_unicode package")
    else:
        for role, family in (("main", core.PREFERRED_FONT), ("mono", core.DEFAULT_MONOFONT)):
            fix = "pdfmd --install fonts:core"
            line(f"font:{role}", not core.font_missing(family), f"{family}" + ("" if not core.font_missing(family) else "  (a stand-in is used)"),
                 fix, f"the default font {family}")
        from pdfmd_unicode import install as font_installer
        installed = font_installer.installed(core.fonts_directory())
        line("managed-fonts", None, f"fonts installed by pdfmd: {', '.join(sorted(installed)) if installed else 'none'}"
                   f"  ({core.fonts_directory()})")
        try:
            index = module.FontIndex(core.fonts_directory())
            emoji = core.managed_face("Noto Color Emoji") or index.regular("Noto Color Emoji") or index.regular("Apple Color Emoji")
        except Exception:  # noqa: BLE001 -- a broken font folder must not stop the report
            emoji = None
        line("emoji-font", bool(emoji), "colour emoji font" + (f": {emoji.family}" if emoji else ""),
             "pdfmd --install emoji", "a colour emoji font (emoji are labels or boxes without one)")
        cjk = [family for family in ("Songti SC", "PingFang SC", "Noto Serif CJK SC", "Source Han Serif SC",
                                     "SimSun", "Microsoft YaHei", "WenQuanYi Zen Hei") if not core.system_font_missing(family)]
        line("cjk-font", bool(cjk) or "cjk-sc" in installed, "Chinese/Japanese/Korean font" + (f": {cjk[0]}" if cjk else ""),
             "pdfmd --install fonts:cjk-sc  (cjk-jp, cjk-kr...)", "a CJK font (only needed for documents in those scripts)")
        packs = sorted(core.TRANSLIT_PACKS)
        rest = [pack for pack in module.translit.PACKS if pack not in core.TRANSLIT_PACKS]
        ready = sorted(pack for pack in rest if module.translit.available(pack))
        if ready and len(ready) == len(rest):
            hint = f"  (ready, off until you turn them on: --translit all; {', '.join(ready)})"
        elif ready:
            hint = f"  (--translit list; ready, off until turned on: {', '.join(ready)}; pdfmd --install translit for the rest)"
        else:
            hint = "  (--translit list; pdfmd --install translit for Chinese and the rest)"
        line("translit", None, "name lookup in other scripts: Cyrillic" + (", " + ", ".join(packs) if packs else "") + hint)

    say("\nReading PDFs (PDF to Markdown):")
    reader = core.find_batchocr()
    reader_version = core.batchocr_version(reader) if reader else None
    line("batchocr", bool(reader_version and reader_version >= core.BATCHOCR_MIN),
         "batchocr" + (f" {'.'.join(map(str, reader_version))}" if reader_version else ""),
         "pdfmd --install batchocr", "batchocr (reading PDFs)")
    for tool, programs in (("tesseract", ("tesseract",)), ("poppler", ("pdftotext", "pdftoppm"))):
        found = [program for program in programs if core.which(program)]
        line(tool, len(found) == len(programs), f"{tool}: " + (", ".join(found) or "not found")
             + (f"  ({core.which(found[0])})" if found else "")
             + (f"  -- {tool_note(tool)}" if found and tool_note(tool) else ""),
             core.tesseract_install_hint(), f"{tool} (scanned PDFs)")
    if module is not None:
        from pdfmd_unicode import tessdata
        own = tessdata.installed(core.tessdata_directory())
        line("ocr-languages", None, f"OCR languages from pdfmd: {', '.join(own) if own else 'none'}  (pdfmd --install ocr:rus)")

    say("\nSmaller PDFs (lossless; --shrink):")
    shrinkers = core.load_package("pdfmd_shrink").available()
    if shrinkers:
        for number, (name, where) in enumerate(shrinkers):
            line(f"shrinker:{name}", True, f"{name}  ({where})" + ("  -- shrinks every PDF" if number == 0 else "  -- takes over when the one above is gone"))
    else:
        line("shrinker", None, f"no PDF shrinker (optional: PDFs stay about a tenth larger)  ({core.load_package('pdfmd_shrink').install_hint()})")

    foreign = foreign_commands()
    if foreign:
        say("\nCommand names:")
        for name, path in foreign:
            line(f"command-conflict:{name}", None, f"`{name}` on the PATH is another program's, not pdfmd's: {core.display_path(Path(path))}  "
                       f"(the last install owns a name; `pdfmd-cli` is always pdfmd's; to take `{name}` back: "
                       "pip install --force-reinstall --no-deps pdfmd-cli)")

    if deep:
        say("\nSmoke test (a small page with maths, code and a table, built with each engine):")
        candidates = [*engines, *(core.available_native_engines() if not (pandoc and engines) else [])]
        if pandoc:           # the last resorts (v3.29.5): each browser and Calibre print the page, and Calibre writes an ebook
            candidates += [engine for engine in core.automatic_engines() if engine in (*core.BROWSER_ENGINES, "calibre")]
            if core.resolve_calibre():
                candidates.append("calibre:azw3")
        if not candidates:
            line("smoke-test", False, "nothing to try: no engine is installed", "pdfmd --install typst", "a PDF engine", required=True)
        for name, built, detail in deep_checks(candidates):
            engine_name, _, ebook = name.partition(":")
            what = f"an {ebook.upper()} ebook" if ebook else "a PDF"
            line(f"smoke-test:{name}", built, f"{name}: " + (f"built {what} in {detail}" if built else f"could not build it ({detail})"),
                 f"pdfmd --setup, or rerun with: pdfmd sample.md -e {engine_name}{' -o sample.' + ebook if ebook else ''} --debug",
                 f"{engine_name} is installed but cannot build a page", required=True)

    say("\nSettings and cache:")
    from pdfmd_config import global_config_layers

    for layer, path, _ in global_config_layers():
        if layer == "per-install":
            line("per-install-config", None, f"per-install config file: {path}")
    config = core.config_path()
    line("user-config", None, "config file: " + ("switched off by PDFMD_CONFIG" if config is None else
                                  f"{config} ({'present' if config.is_file() else 'none; pdfmd --init-config writes one'})"))
    setup = core.setup_module()
    screens = "numbered list" + (", full screen too" if setup is not None and setup.fancy.available()
                                 else " (full screen: pdfmd --install tui)")
    line("setup", None, f"pdfmd --setup: {screens}")
    cache = core.cache_root()
    size = folder_size(cache) if cache.is_dir() else 0
    line("cache", None, f"cache: {cache} ({f'{size / 1e6:.1f} MB' if size else 'empty'}; pdfmd --cache-info, pdfmd --clear-cache)")
    over = core.cache_size_note(size)                  # v3.33.74: larger than cache.max-mb
    if over:
        line("cache-size", None, over)
    line("data", None, f"installed tools and fonts: {core.data_root()}")

    say()
    if problems:
        say(f"{len(set(fix for _, fix in problems))} thing(s) to fix:")
        merged: dict[str, list[str]] = {}
        for what, fix in problems:
            merged.setdefault(fix, []).append(what)
        for number, (fix, what) in enumerate(merged.items(), start=1):
            say(f"  {number}. {' and '.join(what)}\n       {fix}")
    else:
        say("Everything pdfmd uses is in place.")
    hint = user_path_hint()
    if hint:
        say(hint)
    if as_json:
        import json
        from .tools import tool_reports

        print(json.dumps({"format": "pdfmd-doctor", "version": 1, "pdfmd": core.PDFMD_VERSION, "checks": checks,
                          "tools": tool_reports(pandoc, version, quarto, soffice, calibre, reader, reader_version, shrinkers)}))
    return bool(pandoc and engines) or bool(core.available_native_engines())


def completion_options() -> list[dict]:
    """The command line as data for the completion scripts: flags, help, whether a value follows,
    and the values it can take (argparse choices; the kinds and names of --install/--uninstall)."""
    options = []
    parser, _ = core.command_line_parser([])          # a switched-off feature is not offered
    for action in parser._actions:
        flags = [flag for flag in action.option_strings if flag not in ("-h", "--help")]
        if not flags or action.help == argparse.SUPPRESS:
            continue
        takes_value = action.nargs != 0
        values = [str(choice) for choice in action.choices] if action.choices else []
        if action.dest == "install":
            values = list(core.INSTALL_KINDS)
            module = core.unicode_module()
            if module is not None:
                from pdfmd_unicode import install as font_installer, tessdata
                values += [f"fonts:{key}" for key in sorted(font_installer.PACKAGES)]
                values += [f"ocr:{code}" for code in sorted(tessdata.LANGUAGES)]
        elif action.dest == "uninstall":
            values = ["fonts:", "ocr:"]
        help_text = " ".join((action.help or "").split())
        short = re.split(r"(?<=\.)\s", help_text, maxsplit=1)[0].rstrip(".")
        if len(short) > 90:
            short = short[:88].rsplit(" ", 1)[0].rstrip(",;:( ") + " ..."
        label = (action.metavar if isinstance(action.metavar, str) else action.dest).upper()
        files = bool(re.search(r"FILE|PATH|DIR|OUT|TEMPLATE|BIBLIOGRAPHY|FILTER", label)) and not values
        options.append({"flags": flags, "value": takes_value, "values": values, "files": files, "help": short})
    return options


def completion_script(shell: str) -> str:
    """A completion script for bash, zsh or fish, generated from the parser so it cannot go stale."""
    options = completion_options()
    names = "pdfmd pdfmd-cli"
    if shell == "bash":
        every = " ".join(flag for option in options for flag in option["flags"])
        cases = []
        for option in options:
            if option["values"]:
                # `:` is a word break in bash, so fonts:NAME is offered after its prefix is typed
                shown = " ".join(value for value in option["values"] if ":" not in value) or " ".join(option["values"])
                cases.append(f'        {"|".join(option["flags"])}) COMPREPLY=($(compgen -W "{shown}" -- "$cur")); return ;;')
            elif option["value"]:
                reply = 'COMPREPLY=($(compgen -f -- "$cur"))' if option["files"] else "COMPREPLY=()"
                cases.append(f'        {"|".join(option["flags"])}) {reply}; return ;;')
        return ("# bash completion for pdfmd. Generated by `pdfmd --completion bash`.\n"
                "# Install: pdfmd --completion bash > ~/.local/share/bash-completion/completions/pdfmd\n"
                "_pdfmd() {\n    local cur prev\n    cur=${COMP_WORDS[COMP_CWORD]}\n    prev=${COMP_WORDS[COMP_CWORD-1]}\n"
                '    case "$prev" in\n' + "\n".join(cases) + "\n    esac\n"
                '    if [[ "$cur" == -* ]]; then\n'
                f'        COMPREPLY=($(compgen -W "{every}" -- "$cur"))\n'
                "    else\n        COMPREPLY=($(compgen -f -- \"$cur\"))\n    fi\n}\n"
                f"complete -o filenames -F _pdfmd {names}\n")
    if shell == "zsh":
        lines = ["#compdef " + names, "# zsh completion for pdfmd. Generated by `pdfmd --completion zsh`.",
                 "# Install: pdfmd --completion zsh > ~/.zfunc/_pdfmd   (with ~/.zfunc in $fpath, then compinit)",
                 "_arguments -s \\"]
        for option in options:
            description = option["help"].replace("'", "'\\''").replace("[", "(").replace("]", ")").replace(":", " -")
            action = ""
            if option["value"]:
                plain = [value for value in option["values"] if ":" not in value]
                action = (":value:(" + " ".join(plain) + ")" if plain
                          else ":value:_files" if option["files"] and not option["values"] else ":value: ")
            group = option["flags"]
            if len(group) > 1:
                excl = "(" + " ".join(group) + ")"
                for flag in group:
                    lines.append(f"  '{excl}{flag}[{description}]{action}' \\")
            else:
                lines.append(f"  '{group[0]}[{description}]{action}' \\")
        lines.append("  '*:file:_files'")
        return "\n".join(lines) + "\n"
    if shell == "fish":
        lines = ["# fish completion for pdfmd. Generated by `pdfmd --completion fish`.",
                 "# Install: pdfmd --completion fish > ~/.config/fish/completions/pdfmd.fish"]
        for command in names.split():
            for option in options:
                parts = [f"complete -c {command}"]
                for flag in option["flags"]:
                    parts.append(f"-l {flag[2:]}" if flag.startswith("--") else f"-s {flag[1:]}")
                if option["value"]:
                    parts.append("-r")
                    if option["values"]:
                        parts.append("-f -a '" + " ".join(option["values"]) + "'")
                parts.append("-d '" + option["help"].replace("'", "\\'") + "'")
                lines.append(" ".join(parts))
        return "\n".join(lines) + "\n"
    raise ValueError(shell)
