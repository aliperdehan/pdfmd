"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_install.manage`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import sys
from pathlib import Path

from pdfmd_base import core


def translit_report() -> bool:
    """`--translit list`: the packs, which are on, which could work."""
    module = core.unicode_module()
    print("Romanization packs (names in other scripts, found by typing them in Latin letters):")
    print("  cyrillic   always on: Russian, Ukrainian, Belarusian, Kazakh (built in)")
    if module is None:
        print("  the other packs are part of the pdfmd_unicode package, which is not installed here")
        return False
    for pack in module.translit.PACKS:
        state = ("on" if pack in core.TRANSLIT_PACKS else "ready" if module.translit.available(pack)
                 else "needs " + module.translit.needs(pack))
        scripts = ", ".join(sorted(module.SCRIPT_NAMES.get(code, code)
                                   for code in module.translit.PACK_SCRIPTS.get(pack, ()))) or "all the rest"
        print(f"  {pack:<10} {state:<44} {scripts}")
    print("Turn them on with --translit greek,hangul (or all), or PDFMD_TRANSLIT=greek,hangul.")
    return True


def kits_install_directory() -> Path | None:
    """The folder pdfmd installs kits into: `kits/` beside the config file, which kit discovery reads already."""
    config = core.config_path()
    return None if config is None else config.parent / "kits"


def uninstall_kit(name: str) -> bool:
    """`pdfmd --uninstall kit:NAME`: remove a kit that `--install kit` put in the kits folder (never one placed there by hand)."""
    from pdfmd_kits import install as kit_installer
    target = core.kits_install_directory()
    if target is None:
        print("ERROR  PDFMD_CONFIG switches off the user config: there is no config folder", file=sys.stderr)
        return False
    try:
        folder = kit_installer.uninstall(name, target)
    except kit_installer.InstallError as error:
        print(f"ERROR  {error}", file=sys.stderr)
        return False
    print(f"REMOVED  {core.display_path(folder)}")
    return True


def uninstall_fonts(names: str) -> bool:
    module = core.unicode_module()
    if module is None:
        return False
    from pdfmd_unicode import install as installer
    try:
        keys = installer.resolve(names.split(",")) if names.strip() else []
    except installer.UnknownPackage as error:
        print(f"No font package or group called {error.args[0]!r}.", file=sys.stderr)
        return False
    if not keys:
        print("Name what to remove: pdfmd --uninstall fonts:arabic,cjk-sc", file=sys.stderr)
        return False
    installer.uninstall(keys, core.fonts_directory())
    reset_font_caches()
    return True


def tessdata_directory() -> Path:
    """Where pdfmd keeps the Tesseract language files `pdfmd --install ocr:LANG` fetches."""
    return core.data_root() / "tessdata"


def install_ocr_languages(names: str, remove: bool = False) -> bool:
    """`pdfmd --install ocr[:LANG,...]` / `--uninstall ocr:LANG`: list the languages, or fetch them
    (pdfmd_unicode/tessdata.py)."""
    if core.unicode_module() is None:
        print("The OCR language installer is part of the pdfmd_unicode package, which is not installed "
              "beside this file (pip install pdfmd-cli).", file=sys.stderr)
        return False
    from pdfmd_unicode import tessdata
    if not names.strip():
        if remove:
            print("Name what to remove: pdfmd --uninstall ocr:rus,kaz", file=sys.stderr)
            return False
        print(tessdata.table(tessdata_directory()))
        return True
    try:
        codes = tessdata.resolve(names.split(","))
    except tessdata.UnknownLanguage as error:
        print(f"No Tesseract language called {error.args[0]!r}. `pdfmd --install ocr` lists them.", file=sys.stderr)
        return False
    if remove:
        tessdata.uninstall(codes, tessdata_directory())
        return True
    failed = tessdata.install(codes, tessdata_directory())
    done = [code for code in codes if code not in failed]
    if done:
        print(f"Installed {', '.join(done)} in {tessdata_directory()}; `pdfmd scan.pdf --lang {'+'.join(done)}` "
              "uses them (remove with `pdfmd --uninstall ocr:LANG`).")
    return not failed


def reset_font_caches() -> None:
    core._FONT_INDEX = core._MANAGED_INDEX = None
    # the cached functions are in pdfmd_unicode.fonts_choice (v3.33.34), whose stand-ins here have no cache_clear;
    # before that module is loaded nothing is cached
    fonts = sys.modules.get("pdfmd_unicode.fonts_choice")
    for name in ("font_missing", "system_font_missing", "default_monofont", "fallback_font", "preferred_font"):
        clear = getattr(getattr(fonts, name, None), "cache_clear", None)
        if clear:
            clear()


def setup_module():
    try:
        import pdfmd_setup
    except ImportError:
        return None
    return pdfmd_setup
