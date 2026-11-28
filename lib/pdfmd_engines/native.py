"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_engines.native`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

from pdfmd_base import core
from pdfmd_log import emit


NATIVE_ENGINES = ("calibre", "md2pdf", "inkmd")


NATIVE_ALIASES = {"ink": "inkmd", "reportlab": "md2pdf", "pymd2pdf": "md2pdf", "ebook-convert": "calibre"}


# Kinds that are not pip packages (see install_typst), and the one that is both.
INSTALL_KINDS = ("pandoc", "typst", "full", "core", "cortex", "math", "diagram", "calibre", "emoji", "batchocr", "fonts", "translit", "ocr", "tui", "kit", "template", "csl")


CORE_TYPST_SIZE = "Pandoc 35 MB, Typst 15 MB and fonts 8 MB (about 58 MB download)"
CORE_TEX_SIZE = "Pandoc 35 MB, Tectonic 10 to 22 MB and fonts 8 MB (about 53 to 65 MB download)"


INSTALL_SIZES = {"template": "one asset", "csl": "one style", "kit": "the repository you name", "tui": "about 1 MB", "translit": "about 3 MB", "ocr": "see `pdfmd --install ocr`", "fonts": "see `pdfmd --install fonts`", "emoji": "about 11 MB", "math": "about 150 MB", "pandoc": "about 35 MB download",
                 "typst": "about 15 MB download", "full": CORE_TYPST_SIZE,
                 "diagram": "about 22 MB: D2 17 MB, Graphviz 2 MB, resvg about 3 MB",
                 "diagram:resvg": "about 3 MB download",
                 "diagram:d2": "about 17 MB download", "diagram:dot": "about 2 MB, plus node if needed",
                 "diagram:all": "about 22 MB, plus node if needed",
                 "math:katex": "about 1.5 MB, plus node if needed", "math:mathjax": "about 12 MB, plus node if needed",
                 "calibre": "190 to 360 MB download", "core": CORE_TYPST_SIZE,
                 "core:typst": CORE_TYPST_SIZE,
                 "core:tex": CORE_TEX_SIZE,
                 "cortex": CORE_TEX_SIZE,
                 "batchocr": "about 40 MB with PyMuPDF"}


# The oldest Pandoc pdfmd is tested with: 3.1.3, which is what the claude.ai sandbox has (the suite runs against it). An
# older one may still work; the first compile with it says so once. What an older-than-latest one does without:
PANDOC_MIN = (3, 1, 3)


def warn_old_pandoc() -> None:
    """The first compile with a Pandoc older than PANDOC_MIN says so, once for that version on this machine."""
    version = core.pandoc_version()
    if version == (0,) or version >= PANDOC_MIN:
        return
    shown = ".".join(map(str, version))
    path = core.config_root() / f"notice-pandoc-{shown}"
    if os.environ.get("PDFMD_NO_PROMPT") or path.exists():
        return
    emit("warning", None, f"WARN  Pandoc {shown} is older than {'.'.join(map(str, PANDOC_MIN))}, the oldest pdfmd is tested with; "
          "it may work, and a newer one (`pdfmd --install pandoc`) is the first thing to try if something looks wrong. "
          "This is said once.", file=sys.stderr)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("shown\n", encoding="utf-8")
    except OSError:
        pass


PANDOC_MISSING = ("Pandoc was not found on PATH. Install it with `pdfmd --install pandoc` (no admin rights; "
                  "`pdfmd --install full` adds Typst for PDF output), or -- macOS: `brew install pandoc`; "
                  "Debian/Ubuntu: `sudo apt install pandoc`; others: https://pandoc.org/installing.html "
                  "-- then run `pdfmd --check-dependencies`.")


def inkmd_vendored() -> bool:
    """Whether the vendored inkmd (pdfmd_inkmd/) ships next to this file."""
    return importlib.util.find_spec("pdfmd_inkmd") is not None


def md2pdf_available() -> bool:
    """pymd2pdf (not the unrelated WeasyPrint-based `md2pdf`) is installed."""
    import importlib.metadata  # here, not at the top: only this needs it (start-up time, v3.32.55)
    if sys.version_info < (3, 11):
        return False
    try:
        importlib.metadata.version("pymd2pdf")
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def matplotlib_available() -> bool:
    return importlib.util.find_spec("matplotlib") is not None


def inkmd_emoji_font() -> Path | None:
    """The colour-emoji font: pdfmd's own (`pdfmd --install emoji`), else that of a
    separately installed `inkmd` (the [emoji] extra)."""
    own = core.fonts_directory() / "emoji" / "NotoColorEmoji.ttf"
    if own.is_file():
        return own
    try:
        spec = importlib.util.find_spec("inkmd")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    font = Path(spec.origin).parent / "assets" / "emoji" / "NotoColorEmoji.ttf"
    return font if font.is_file() else None


def is_native_engine(engine: str) -> bool:
    """Whether ``engine`` is one of the Pandoc-less renderers in this run: Calibre's own name is one only with no Pandoc (with
    Pandoc, `-e calibre` is the HTML route)."""
    return engine in NATIVE_ENGINES and (engine != "calibre" or not core.which("pandoc"))


def native_available(engine: str) -> bool:
    if engine == "calibre":
        return not core.which("pandoc") and core.resolve_calibre() is not None      # with Pandoc, -e calibre is the HTML route
    return core.inkmd_vendored() if engine == "inkmd" else core.md2pdf_available()


def available_native_engines() -> list[str]:
    return [engine for engine in NATIVE_ENGINES if native_available(engine)]


def native_request(requested: str, presentation: bool, label: str) -> list[str] | None:
    """The native engine(s) a -e/--engine or `pdf-engine` value names, or None
    if it names something else. Raises if the named renderer is not installed."""
    name = requested.casefold()
    if name == "native":
        engines = available_native_engines()
    else:
        name = NATIVE_ALIASES.get(name, name)
        if name not in NATIVE_ENGINES or (name == "calibre" and core.which("pandoc")):
            return None
        engines = [name] if native_available(name) else []
        if not engines:
            hint = ("needs Python 3.11 or newer" if name == "md2pdf" and sys.version_info < (3, 11)
                    else "Calibre's ebook-convert was not found" if name == "calibre"
                    else 'install it with `pdfmd --install math` (or pip install "pdfmd-cli[math]")')
            raise SystemExit(f"{label} requested {name}, which is not available: {hint}.")
    if presentation:
        raise SystemExit(f"{label} requested a native renderer, which cannot make Beamer slides "
                         "(-p/--presentation): Pandoc's Beamer writer and a LaTeX engine are required.")
    if not engines:
        raise SystemExit(f"{label} requested the native renderers, but none is available.")
    return engines


def native_possible(args: argparse.Namespace) -> bool:
    """Whether this invocation could be served without Pandoc: a plain
    Markdown-to-PDF run, none of the modes that are Pandoc all the way down."""
    if (args.presentation or args.report or args.split or args.clear_cache or args.list_parts
            or args.unpack or args.slim or args.assemble_only or args.stop_at or args.watch
            or args.embed_metadata is not None):
        return False
    chosen = args.to.casefold() if args.to else (
        core.format_from_output(args.out) if args.out and not args.batch else None)
    from pdfmd_crop.build import CROPPED_OFFICE
    return (chosen in (None, "ansi", *core.PICTURE_FORMATS)
            or (chosen in CROPPED_OFFICE and getattr(args, "crop", None) is not False))


def native_run_note(engines: list[str]) -> None:
    """Printed once when the native tier was chosen automatically."""
    reason = "Pandoc was not found" if not core.which("pandoc") else "no PDF engine was found"
    what = ("Calibre's Markdown reader (no math, none of Pandoc's syntax)" if engines and engines[0] == "calibre"
            else "the built-in renderer")
    emit("note", None, f"NOTE  {reason}: building with {what} ({' / '.join(engines)}). "
          "The output is plain -- no LaTeX, preambles, filters or citation processing. "
          "Pandoc plus Typst or TeX gives the full result: `pdfmd --install full`, or "
          "`pdfmd --check-dependencies`.")


def system_install_hint() -> str:
    """How to install Pandoc and Typst with the system's own package manager."""
    if sys.platform == "darwin":
        return "brew install pandoc typst"
    if sys.platform == "win32":
        return "winget install JohnMacFarlane.Pandoc Typst.Typst"
    return ("sudo apt install pandoc (or your package manager), plus Typst from "
            "https://github.com/typst/typst/releases")


def pandoc_install_hint() -> str:
    """How to get Pandoc and Typst: pdfmd's own installer first, then the system way."""
    return f"`pdfmd --install full` (no admin rights needed), or {system_install_hint()}"


def native_prompt_state() -> Path:
    path = core.config_root() / "native-prompt-dismissed"
    core.migrate_state(core.cache_root() / "native-prompt-dismissed", path)
    return path


def report_native_markup(engine: str, source: Path, losses: dict[str, int]) -> None:
    from pdfmd_flavours.markup import MARKUP_KINDS
    from pdfmd_native import native_lose, native_note

    for kind, count in losses.items():
        native_lose(kind, count)
    items = ", ".join(f"{kind} ({losses[kind]})" for kind in (*MARKUP_KINDS, "comments") if kind in losses)
    native_note(engine, "markup dropped: " + items, source)


def offer_native_upgrade() -> None:
    """After an automatic native build that lost something, offer the upgrades.

    Interactive terminals only (never in CI, a pipe, or with PDFMD_NO_PROMPT
    set), and never again once the user has chosen to continue as is.
    """
    if (not core.NATIVE_LOST or os.environ.get("PDFMD_NO_PROMPT") or not sys.stdin.isatty()
            or not sys.stdout.isatty() or native_prompt_state().exists()):
        return
    lost = ", ".join(f"{kind} ({count})" for kind, count in sorted(core.NATIVE_LOST.items()))
    options: list[tuple[str, str]] = []
    if "math" in core.NATIVE_LOST and sys.version_info >= (3, 11) \
            and not (core.md2pdf_available() and core.matplotlib_available()):
        options.append(("math", f"install md2pdf with math now ({INSTALL_SIZES['math']})"))
    if "emoji" in core.NATIVE_LOST and inkmd_emoji_font() is None:
        options.append(("emoji", f"install the colour emoji font ({INSTALL_SIZES['emoji']})"))
    if not (core.which("pandoc") and core.installed_engines()):
        options.append(("full", f"install Pandoc, Typst and the default fonts now ({INSTALL_SIZES['full']}, into pdfmd's own "
                                "folders, no admin rights) for the full-quality route"))
    options.append(("never", "continue as is and don't ask again"))
    print(f"\nThe native renderer could not render: {lost}.")
    for number, (_, label) in enumerate(options, 1):
        print(f"  {number}) {label}")
    try:
        answer = input("Choose [Enter = continue this time]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not answer.isdigit() or not 1 <= int(answer) <= len(options):
        return
    choice = options[int(answer) - 1][0]
    if choice in INSTALL_KINDS:
        if core.install_extra(choice):
            print("Installed. Run pdfmd again to use it.")
    else:
        try:
            native_prompt_state().parent.mkdir(parents=True, exist_ok=True)
            native_prompt_state().write_text("dismissed\n", encoding="utf-8")
        except OSError:
            pass
