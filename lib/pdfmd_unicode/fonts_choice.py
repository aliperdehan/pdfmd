"""How pdfmd chooses its fonts: the families fontconfig knows (`installed_font_families`), whether a font is missing
(`font_missing`, `system_font_missing`), the stand-ins for a code font and for the missing-glyph retry when the defaults are not
installed (`default_monofont`, `fallback_font`, `preferred_font`), the `-V` arguments that name a font in pdfmd's own folder by file
(`font_args`), WeasyPrint's `@font-face` rules for that folder (`managed_fonts_css`), `--check-fonts` (`check_fonts`) and the
per-script fallback of a build (`script_fallback`, with `unicode_code_text`, `unicode_forced` and `describe_code_points`).

Moved out of `pdfmd.py` unchanged (v3.33.34, SPLIT.md), with `DEFAULT_FONT`, `MONOFONT_STAND_INS`, `SERIF_STAND_INS`,
`CODE_FONTS_TYPST`, `CODE_FONTS_HTML`, `EMOJI_FAMILIES` and `UNICODE_ENGINES`. Unlike the rest of this package, it reads pdfmd: `core`
is the `pdfmd` module, bound when the module is first loaded (a stand-in in `pdfmd.py` loads it on the first call; the first binding
wins), and the pdfmd names the code uses (`DEFAULT_MONOFONT`, `EMBED_BLOCK_RE`, `LATEX_ENGINES`, `PREFERRED_FONT`, `UNICODE_CODE_FONTS`,
`UNICODE_UNCOVERED`, `auto_disabled`, `config_options`, `document_cache_root`, `document_font_setting`, `fallback_settings`,
`find_metadata`, `font_index`, `frontmatter_pdfmd_options`, `has_mainfont`, `mainfont_choice`, `managed_face`, `managed_index`,
`own_script_setup`, `unicode_module` and `unicode_source_text`) are read as `core.X` when it runs. Tests patch `pdfmd.system_font_missing`
and `pdfmd.preferred_font` (and `pdfmd.config_options`), so `font_missing`, `font_args` and `check_fonts` call them as `core.X`.
`pdfmd.installed_font_families` is this module's own function (`DEFERRED_NAMES` in `pdfmd.py`), so a test's `.cache_clear()` reaches
its cache; `reset_font_caches` in `pdfmd.py` clears the other caches here by name.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

core = None


DEFAULT_FONT = "DejaVu Serif"


# Installed-by-default stand-ins, tried in order when one of the three fonts
# above isn't installed (a fresh machine rarely has JetBrains Mono or, on
# macOS, DejaVu Serif). Without this, every LaTeX engine failed with a
# fontspec error and the build silently fell through to typst/HTML engines.
MONOFONT_STAND_INS = ("Menlo", "DejaVu Sans Mono", "Liberation Mono", "Courier New")
# For DEFAULT_FONT's missing-glyph retry: system serifs that, like DejaVu,
# cover the arrows/comparison/Greek that STIX Two Text lacks (it has no ≥).
SERIF_STAND_INS = ("Times New Roman", "Liberation Serif", "Georgia")


@lru_cache(maxsize=None)
def installed_font_families() -> frozenset[str] | None:
    """Lower-cased font family names from fontconfig, or None without fc-list."""
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return None
    try:
        done = subprocess.run([fc_list, ":", "family"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    # decoded here: with text=True a Windows fc-list whose output the console code page cannot decode came back as None
    out = (done.stdout or b"").decode("utf-8", "replace")
    return frozenset(name.strip().casefold() for line in out.splitlines() for name in line.split(","))


def font_missing(family: str) -> bool:
    """True only when a font is known NOT to be installed -- anywhere, pdfmd's own fonts
    folder (`pdfmd --install fonts`) included."""
    return core.system_font_missing(family) and core.managed_face(family) is None


@lru_cache(maxsize=None)
def system_font_missing(family: str) -> bool:
    """True only when a font is known NOT to be installed.

    Asks fontconfig (fc-list) first, then luaotfload-tool (ships with TeX
    Live/MacTeX, so it's there whenever lualatex is). If neither tool is
    available the answer is False -- "assume it's there", exactly the
    behavior before this check existed.
    """
    families = installed_font_families()
    if families is not None:
        return family.casefold() not in families
    tool = shutil.which("luaotfload-tool")
    if not tool:
        # No fontconfig and no TeX: pdfmd's own scan of the system font folders (Windows, mostly)
        index = core.font_index()
        if index is None:
            return False
        return not any(not face.managed for face in index._by_name.get(family.casefold(), []))
    try:
        result = subprocess.run([tool, f"--find={family}"], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return "Cannot find" in (result.stdout or "") + (result.stderr or "")


@lru_cache(maxsize=None)
def default_monofont() -> str:
    """DEFAULT_MONOFONT, or the first installed MONOFONT_STAND_INS entry."""
    for family in (core.DEFAULT_MONOFONT, *MONOFONT_STAND_INS):
        if not font_missing(family):
            if family != core.DEFAULT_MONOFONT:
                print(f"WARN  font: {core.DEFAULT_MONOFONT} is not installed; using {family} for code "
                      "(install it, or set monofont:, to change this)", file=sys.stderr)
            return family
    return core.DEFAULT_MONOFONT


@lru_cache(maxsize=None)
def fallback_font() -> str:
    """DEFAULT_FONT for the missing-glyph retry, else an installed stand-in.

    Retrying with a font that isn't installed turned a render with a few
    missing glyphs into a failed build (every LaTeX engine hits the same
    fontspec error). With no stand-in either, PREFERRED_FONT is returned,
    so the retry repeats the first attempt instead of failing.
    """
    for family in (DEFAULT_FONT, *SERIF_STAND_INS):
        if not font_missing(family):
            if family != DEFAULT_FONT:
                print(f"WARN  font: {DEFAULT_FONT} is not installed; using {family} for "
                      "missing-glyph fallback", file=sys.stderr)
            return family
    return core.PREFERRED_FONT


@lru_cache(maxsize=None)
def preferred_font() -> str:
    """PREFERRED_FONT, or the fallback font when it isn't installed."""
    if font_missing(core.PREFERRED_FONT):
        replacement = fallback_font()
        if replacement != core.PREFERRED_FONT:
            print(f"WARN  font: {core.PREFERRED_FONT} is not installed; using {replacement} instead "
                  "(install it, or set mainfont:/-f, to change this)", file=sys.stderr)
            return replacement
    return core.PREFERRED_FONT


# What Typst and Pandoc's HTML put code in by default (the first of these that is installed).
CODE_FONTS_TYPST = ("DejaVu Sans Mono",)
CODE_FONTS_HTML = ("Menlo", "Monaco", "Consolas", "Lucida Console", "DejaVu Sans Mono")
EMOJI_FAMILIES = ("Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", "Twemoji Mozilla", "Noto Emoji")
UNICODE_ENGINES = ("lualatex", "xelatex", "typst", "weasyprint")


def font_args(kind: str, family: str, latex: bool = True) -> list[str]:
    """`-V` arguments that select ``family`` as mainfont/monofont. One only found in pdfmd's own
    folder (not installed system-wide) is named by file, with the folder as its Path, which
    is how fontspec loads a font it cannot find by name."""
    face = core.managed_face(family) if latex else None
    if face is None or not core.system_font_missing(family):
        return ["-V", f"{kind}={family}"]
    directory = str(Path(face.path).parent).replace("\\", "/") + "/"
    args = ["-V", f"{kind}={Path(face.path).name}", "-V", f"{kind}options=Path={{{directory}}}"]
    for style, option in (("bold", "BoldFont"), ("italic", "ItalicFont"), ("bolditalic", "BoldItalicFont")):
        other = core.managed_index().styles(face).get(style)
        if other is not None:
            args += ["-V", f"{kind}options={option}={{{Path(other.path).name}}}"]
    return args


def unicode_code_text(md_paths: list[Path]) -> str:
    """Collect code from Markdown, including nested and indented blocks."""
    pieces: list[str] = []
    for path in md_paths:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        text = core.EMBED_BLOCK_RE.sub("", text)
        pandoc = shutil.which("pandoc")
        if pandoc:
            reader = core.flavour_reader(path)[0] or "markdown"
            try:
                result = subprocess.run([pandoc, "-f", reader, "-t", "json"], input=text,
                                        capture_output=True, text=True, encoding="utf-8", check=True)
                document = json.loads(result.stdout)
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
            else:
                def collect(node):
                    if isinstance(node, dict):
                        if node.get("t") in ("Code", "CodeBlock"):
                            pieces.append(node["c"][1])
                        else:
                            for value in node.values():
                                collect(value)
                    elif isinstance(node, list):
                        for value in node:
                            collect(value)
                collect(document)
                continue
        pieces += [match.group(2) for match in re.finditer(r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n(.*?)^[ \t]*\1[ \t]*$", text)]
        text = re.sub(r"(?ms)^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", "", text)
        pieces += re.findall(r"`([^`\n]+)`", text)
    return "\n".join(pieces)


def unicode_forced(md_path: Path) -> bool:
    value = core.frontmatter_pdfmd_options(md_path).get("unicode", core.config_options().get("unicode", ""))
    return str(value).casefold() in ("true", "yes", "on", "force")


@contextmanager
def managed_fonts_css(engine: str | None) -> Iterator[Path | None]:
    """For WeasyPrint, which finds fonts through fontconfig: an @font-face rule for every font in
    pdfmd's own folder, so a document can name them like installed ones."""
    index = core.managed_index() if engine == "weasyprint" else None
    rules = []
    if engine == "weasyprint" and core.UNICODE_CODE_FONTS:
        # code: the fonts it already used, then the ones for its other characters, then any monospace
        stack = ", ".join(f'"{family}"' for family in core.UNICODE_CODE_FONTS)
        rules.append(f"code, pre, pre code, code span {{ font-family: {stack}, monospace; }}")
    if not rules and (index is None or not index.faces):
        yield None
        return
    for face in (index.faces if index is not None else []):
        if "emoji" in face.family.casefold():
            continue  # WeasyPrint draws bitmap colour fonts (Noto Color Emoji) badly
        style = face.style.casefold()
        rules.append('@font-face { font-family: "%s"; src: url("%s"); font-weight: %s; font-style: %s; }' % (
            face.family, Path(face.path).as_uri(), "bold" if "bold" in style else "normal",
            "italic" if "italic" in style or "oblique" in style else "normal"))
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".html", prefix="pdfmd-fontface-",
                            delete=False) as temporary:
        temporary.write("<style>\n" + "\n".join(rules) + "\n</style>\n")
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


def check_fonts(md_path: Path, no_auto: list[str] | None, variables: list[str]) -> bool:
    """`--check-fonts`: what the fonts would do for one document, without building it. True when
    every character can be drawn."""
    module, index = core.unicode_module(), core.font_index()
    if module is None or index is None:
        print("The fonts check is part of the pdfmd_unicode package, which is not installed here.")
        return False
    found = core.find_metadata(md_path.parent, None, document_stem=md_path.stem, document=md_path)
    metadata_files = ([found] if isinstance(found, Path) else found if isinstance(found, list) else [])
    paths = [md_path]
    mode, missing_mode = core.fallback_settings(md_path, metadata_files)
    notes: list[tuple] = []
    document_font = core.has_mainfont(md_path, variables, metadata_files)
    main = (core.mainfont_choice(paths, metadata_files, variables, None, document_font,
                            not core.auto_disabled(no_auto, "mainfont"), no_auto, lambda *a: notes.append(a))
            or core.document_font_setting("mainfont", paths, metadata_files, variables)
            or core.preferred_font())
    print(f"{md_path}")
    print(f"  fallback: {mode}   missing: {missing_mode}"
          + ("   (switched off by --no-auto unicode)" if core.auto_disabled(no_auto, "unicode") else ""))
    for _kind, detail in notes:
        print(f"  note: {detail.split(': ', 1)[-1]}")
    face = index.regular(main)
    print(f"  main font: {main}" + ("" if face else "   (not installed: pdfmd cannot tell what it lacks)"))
    if face is None:
        return False
    if core.own_script_setup(paths, [], variables, metadata_files) and not unicode_forced(md_path):
        print("  the document sets up its own fonts for other scripts; pdfmd leaves them to it")
        return True
    text = core.unicode_source_text(paths, metadata_files)
    language = core.document_font_setting("lang", paths, metadata_files, variables)
    plan = module.plan_text(text, main, index, language, fonts=mode in ("char", "word", "document"))
    undrawn = dict(plan.uncovered)
    for line in plan.describe():
        print(f"  {line.replace('->', 'takes')}")
    if not plan.choices and not plan.emoji and not plan.uncovered:
        print(f"  every character of the text is in {main}")
    emoji = set(plan.emoji)
    code_text = unicode_code_text(paths)
    if code_text.strip():
        mono = core.document_font_setting("monofont", paths, metadata_files, variables) or default_monofont()
        code = module.plan_text(code_text, mono, index, language, fonts=mode in ("char", "word", "document"))
        if code is not None:
            for line in code.describe():
                print(f"  code in {mono}: {line.replace('->', 'takes')}")
            undrawn.update(code.uncovered)
            emoji.update(code.emoji)
    if emoji:
        picture = (core.managed_face("Noto Color Emoji") or index.regular("Noto Color Emoji")
                   or index.regular("Apple Color Emoji"))
        print(f"  {len(emoji)} emoji character(s): LaTeX sets them as pictures from "
              + (picture.family if picture else "a colour emoji font (not installed: pdfmd --install emoji)")
              + "; Typst draws them itself")
        if picture is None:
            undrawn.update({code_point: 1 for code_point in emoji})
    if undrawn:
        from pdfmd_unicode import install as installer
        wanted = installer.packages_for(undrawn, language)
        print(f"  no installed font draws: {describe_code_points(undrawn)}")
        print("  install: " + (f"pdfmd --install fonts:{','.join(wanted)}" if wanted else "pdfmd --install fonts")
              + f"   (until then: missing: {missing_mode})")
        return False
    print("  everything can be drawn")
    return True


def describe_code_points(code_points, limit: int = 12) -> str:
    shown = []
    for code_point in sorted(code_points)[:limit]:
        try:
            name = unicodedata.name(chr(code_point))
        except ValueError:
            name = "unnamed"
        shown.append(f"U+{code_point:04X} {chr(code_point)} {name}")
    more = len(code_points) - len(shown)
    return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


@contextmanager
def script_fallback(md_paths: list[Path], metadata_files: list[Path], variables: list[str],
                    preamble_files: list[Path], main_font: str | None, engine: str | None,
                    no_auto: list[str] | None, note) -> Iterator[tuple[Path | None, Path | None]]:
    """(header, filter) temp files that set the text ``main_font`` cannot draw in other fonts,
    or (None, None) when there is nothing to do, or no way to know what is missing."""
    module = core.unicode_module()
    index = core.font_index()
    skip = (module is None or index is None or core.auto_disabled(no_auto, "unicode")
            or (engine is not None and engine not in UNICODE_ENGINES))
    mode, missing_mode = core.fallback_settings(md_paths[0], metadata_files) if not skip else ("char", "warn")
    skip = skip or mode == "off"
    if not skip and not unicode_forced(md_paths[0]) and core.own_script_setup(md_paths, preamble_files, variables,
                                                                       metadata_files):
        note("UNICODE", f"{md_paths[0]}: sets up its own fonts for other scripts; leaving them to it "
                        "(pdfmd-options: {unicode: true} adds pdfmd's)")
        skip = True
    main = main_font or (core.document_font_setting("mainfont", md_paths, metadata_files, variables)
                         if not skip else None)
    if skip or not main:
        yield None, None
        return
    text = core.unicode_source_text(md_paths, metadata_files)
    language = core.document_font_setting("lang", md_paths, metadata_files, variables)
    fonts_on = mode in ("char", "word", "document")
    plan = module.plan_text(text, main, index, language, fonts=fonts_on, words=mode == "word")
    core.UNICODE_UNCOVERED.clear()
    core.UNICODE_CODE_FONTS.clear()
    code_uncovered: set[int] = set()
    code_emoji: set[int] = set()
    code_text = ""
    if plan is not None:
        # Code is set in the monofont, which lacks other characters than the main font does.
        code_text = unicode_code_text(md_paths)
        latex = engine is None or engine in core.LATEX_ENGINES
        mono = (core.document_font_setting("monofont", md_paths, metadata_files, variables)
                or (default_monofont() if latex else next(
                    (family for family in (CODE_FONTS_TYPST if engine == "typst" else CODE_FONTS_HTML)
                     if index.has(family)), "DejaVu Sans Mono")))
        code_plan = module.plan_text(code_text, mono, index, language, fonts=fonts_on) if code_text.strip() else None
        if code_plan is not None:
            code_uncovered = set(code_plan.uncovered)
            if latex:
                code_emoji = set(code_plan.emoji)   # LaTeX sets these as pictures, like those in the text
                plan.add_code(code_plan)
            elif code_plan.choices:
                core.UNICODE_CODE_FONTS.extend(dict.fromkeys(choice.family for choice in code_plan.choices.values()))
                core.UNICODE_CODE_FONTS.insert(0, mono)
            if code_plan.choices:
                for line in code_plan.describe():
                    note("UNICODE", f"{md_paths[0]}: code in {mono} lacks {line}")
    if plan is None:
        note("UNICODE", f"{md_paths[0]}: {main} is not among the installed fonts, so what it lacks "
                        "cannot be told")
        yield None, None
        return
    if plan.emoji or code_emoji:
        # WeasyPrint draws Noto Color Emoji (bitmaps) badly, so it only counts the others for it.
        usable = EMOJI_FAMILIES if engine != "weasyprint" else EMOJI_FAMILIES[1:4]
        emoji_font = next((family for family in usable if index.has(family)), None)
        if engine in ("typst", "weasyprint") and emoji_font is None:
            print(f"WARN  {md_paths[0]}: the document has emoji and no colour emoji font {engine} can use is "
                  "installed (" + ("-e typst, with pdfmd --install emoji" if engine == "weasyprint"
                                   else "pdfmd --install emoji") + ")", file=sys.stderr)
        elif engine in core.LATEX_ENGINES or engine is None:
            # LaTeX cannot draw a colour font: each emoji becomes the picture the font holds for it.
            # Noto's bitmaps first (the managed copy, then a system one), else Apple's.
            face = (core.managed_face("Noto Color Emoji") or index.regular("Noto Color Emoji")
                    or index.regular("Apple Color Emoji"))
            if face is not None:
                from pdfmd_unicode import colorfont
                stat = Path(face.path).stat()
                digest = hashlib.sha1(f"{face.path}{face.index}{stat.st_size}{stat.st_mtime_ns}".encode()
                                      ).hexdigest()[:8]
                plan.pictures = colorfont.write_pictures(
                    text + "\n" + code_text, plan.emoji | code_emoji, face.path,
                    core.document_cache_root(md_paths[0], metadata_files) / "emoji" / digest, face.index)
            drawn = {ord(character) for sequence in plan.pictures for character in sequence}
            left = plan.emoji - drawn
            if plan.pictures:
                note("UNICODE", f"{md_paths[0]}: {len(plan.pictures)} emoji set as pictures from {face.family}")
            code_uncovered |= code_emoji - drawn
            if left:
                plan.uncovered.update({code_point: 1 for code_point in left})
    undrawn = {**plan.uncovered, **{code_point: 1 for code_point in code_uncovered}}
    if undrawn:
        # Nothing installed draws these: warn, draw a black box, or stop, as `missing:` says.
        core.UNICODE_UNCOVERED.update(undrawn)
        if missing_mode == "error":
            raise SystemExit(f"{md_paths[0]}: the fonts do not draw "
                             f"{describe_code_points(undrawn)} (pdfmd-options: {{missing: warn}} "
                             "to build anyway)")
        elif missing_mode == "box":
            plan.boxes = set(plan.uncovered)
            plan.code_boxes = code_uncovered
            note("UNICODE", f"{md_paths[0]}: {len(undrawn)} character(s) no font draws are set as black boxes")
        else:
            from pdfmd_unicode import install as installer
            wanted = installer.packages_for(undrawn, language)
            hint = (f"pdfmd --install fonts:{','.join(wanted)}" if wanted else "pdfmd --install fonts")
            print(f"WARN  {md_paths[0]}: no installed font draws {describe_code_points(undrawn)} "
                  f"({hint}, or name a font that does; pdfmd-options: {{missing: box}} marks them)",
                  file=sys.stderr)
    if not plan:
        yield None, None
        return
    for line in plan.describe():
        note("UNICODE", f"{md_paths[0]}: {main} lacks {line}")
    header = filter_file = None
    try:
        if engine is None or engine in core.LATEX_ENGINES:
            with NamedTemporaryFile("w", encoding="utf-8", suffix=".tex", prefix="pdfmd-fonts-",
                                    delete=False) as temporary:
                temporary.write(plan.latex_header())
                header = Path(temporary.name)
        with NamedTemporaryFile("w", encoding="utf-8", suffix=".lua", prefix="pdfmd-fonts-",
                                delete=False) as temporary:
            temporary.write(plan.lua_filter())
            filter_file = Path(temporary.name)
        yield header, filter_file
    finally:
        for temporary_path in (header, filter_file):
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
