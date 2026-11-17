"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_unicode.document`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pdfmd_base import core

from pdfmd_base import pandoc_run


OWN_SCRIPT_SETUP_RE = re.compile(r"ucharclasses|\\newfontfamily|\\babelfont|xeCJK|luatexja|CJKutf8|\\setCJK"
                                 r"|add_fallback|\\setTransition|\\setmainfontfallback")


OWN_SCRIPT_VARIABLES = ("CJKmainfont", "CJKsansfont", "CJKmonofont", "mainfontfallback")


BIBLIOGRAPHY_TEXT_SUFFIXES = (".bib", ".bibtex", ".json", ".yaml", ".yml", ".ris", ".csl")


def unicode_module():
    """pdfmd_unicode, or None where it is not installed beside this file."""
    try:
        import pdfmd_unicode
    except ImportError:
        return None
    return pdfmd_unicode


def fonts_directory() -> Path:
    """Where pdfmd keeps the fonts `pdfmd --install fonts` fetches."""
    return core.data_root() / "fonts"


def managed_index():
    """Only the fonts in pdfmd's own folder (cheap: no system scan)."""
    if core._MANAGED_INDEX is None:
        module = unicode_module()
        core._MANAGED_INDEX = module.FontIndex(fonts_directory(), use_system=False) if module else False
    return core._MANAGED_INDEX or None


def managed_face(family: str):
    index = managed_index()
    face = index.regular(family) if index is not None else None
    return face if face is not None and face.managed else None


# The math font that goes with a text font (v3.28.24). unicode-math sets formulas in Latin Modern Math (Typst: New
# Computer Modern Math) unless told otherwise, so a document in STIX Two Text had formulas that did not match its body. A
# row is (the text font pdfmd chooses, the math fonts that go with it: the first one installed is used; several spellings
# of one family, as fontconfig and Typst name them).
MATH_COMPANIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("STIX Two Text", ("STIX Two Math",)),
    ("DejaVu Serif", ("DejaVu Math TeX Gyre",)),
    ("Libertinus Serif", ("Libertinus Math",)),
    ("New Computer Modern", ("New Computer Modern Math", "NewComputerModern Math")),
    ("TeX Gyre Termes", ("TeX Gyre Termes Math",)),
    ("TeX Gyre Pagella", ("TeX Gyre Pagella Math",)),
)


_TEMPLATE_VARIABLES: dict[tuple[str, str], bool] = {}


def template_has_variable(writer: str, variable: str) -> bool:
    """Whether Pandoc's default template for ``writer`` reads ``$variable$`` (Pandoc 3.1.3's Typst one has no mathfont)."""
    key = (writer, variable)
    if key not in _TEMPLATE_VARIABLES:
        try:
            done = pandoc_run(["pandoc", "-D", writer], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
            _TEMPLATE_VARIABLES[key] = done.returncode == 0 and f"$if({variable})$" in done.stdout
        except (OSError, subprocess.SubprocessError):
            _TEMPLATE_VARIABLES[key] = False
    return _TEMPLATE_VARIABLES[key]


def math_companion(main_font: str) -> str | None:
    """The installed math font that goes with ``main_font``, None when there is none (or the font is not in the table)."""
    for text_font, candidates in MATH_COMPANIONS:
        if text_font.casefold() == main_font.casefold():
            return next((name for name in candidates if not core.system_font_missing(name)), None)
    return None


def mathfont_args(main_font: str | None, md_path: Path, metadata_files: list[Path], variables: list[str],
                  cli_font: str | None, no_auto: list[str] | None, engine: str | None, note=None) -> list[str]:
    """`-V mathfont=<companion>` when pdfmd chose the main font itself (no -f, no mainfont: or mathfont: in the document or
    its metadata files), the companion math font is installed, and the engine can use it (lualatex, xelatex, tectonic, Typst
    with a Pandoc whose template knows mathfont; not pdfLaTeX; ``engine`` None is a LaTeX file that any engine builds)."""
    if (not main_font or cli_font or core.auto_disabled(no_auto, "mathfont")
            or has_mainfont(md_path, variables, metadata_files) or has_font_setting("mathfont", md_path, variables, metadata_files)):
        return []
    if engine is not None and engine not in ("lualatex", "xelatex", "tectonic", "typst"):
        return []
    companion = math_companion(main_font)
    if companion is None or (engine == "typst" and not core.template_has_variable("typst", "mathfont")):
        return []
    if note:
        note("MATHFONT", f"{md_path}: no mathfont set; using {companion} to go with {main_font}")
    return ["-V", f"mathfont={companion}"]


def document_font_args(md_paths: list[Path], metadata_files: list[Path], variables: list[str]) -> list[str]:
    """`-V` arguments for the fonts a document itself names (mainfont/sansfont/monofont) that
    exist only in pdfmd's own fonts folder, so LaTeX can load them by file."""
    args: list[str] = []
    for kind in ("mainfont", "sansfont", "monofont"):
        if any(variable.startswith(f"{kind}options=") for variable in variables):
            continue
        family = document_font_setting(kind, md_paths, metadata_files, variables)
        if family and core.managed_face(family) is not None and core.system_font_missing(family):
            args += core.font_args(kind, family)
    return args


def font_index():
    """The installed fonts (and pdfmd's own), read once per run."""
    if core._FONT_INDEX is None:
        module = unicode_module()
        core._FONT_INDEX = module.FontIndex(fonts_directory()) if module else False
    return core._FONT_INDEX or None


def strip_code_text(text: str) -> str:
    """Markdown without its fenced and inline code (set in the monofont, not a fallback's)."""
    text = re.sub(r"(?ms)^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", "", text)
    return re.sub(r"`[^`\n]*`", "", text)


def unicode_source_text(md_paths: list[Path], metadata_files: list[Path]) -> str:
    """All the text a document will print: its Markdown, metadata and bibliography files."""
    pieces: list[str] = []
    seen: set[Path] = set()

    def read(path: Path, code: bool = False) -> str:
        try:
            if path.resolve() in seen or not path.is_file():
                return ""
            seen.add(path.resolve())
            data = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return ""
        return data if code else strip_code_text(data)

    for path in [*md_paths, *metadata_files]:
        text = read(path)
        pieces.append(text)
        front = core.front_matter_dict(text) if path.suffix.lower() in (".md", ".markdown", ".txt", "") \
            else core.metadata_file_yaml(path)
        wanted = front.get("bibliography") if isinstance(front, dict) else None
        for name in (wanted if isinstance(wanted, list) else [wanted] if wanted else []):
            candidate = Path(str(name))
            for folder in (path.parent, Path.cwd()):
                found = candidate if candidate.is_absolute() else folder / candidate
                if found.suffix.lower() in BIBLIOGRAPHY_TEXT_SUFFIXES and found.is_file():
                    pieces.append(read(found, code=True))
                    break
    return "\n".join(pieces)


def document_font_setting(key: str, md_paths: list[Path], metadata_files: list[Path],
                          variables: list[str]) -> str | None:
    """A Pandoc variable as the document sets it: -V, then its front matter, then metadata files."""
    for variable in variables:
        if variable.startswith(f"{key}="):
            return variable.split("=", 1)[1] or None
    for path in [*md_paths[:1], *core.metadata_files_by_priority(metadata_files)]:
        try:
            data = (core.front_matter_dict(path.read_text(encoding="utf-8-sig"))
                    if path.suffix.lower() in (".md", ".markdown", ".txt", "") else core.metadata_file_yaml(path))
        except (OSError, UnicodeDecodeError):
            continue
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return None


def own_script_setup(md_paths: list[Path], preamble_files: list[Path], variables: list[str],
                     metadata_files: list[Path]) -> bool:
    """Whether the document already sets up its own fonts per script."""
    if any(variable.split("=", 1)[0] in OWN_SCRIPT_VARIABLES for variable in variables):
        return True
    if any(document_font_setting(key, md_paths, metadata_files, []) for key in OWN_SCRIPT_VARIABLES):
        return True
    texts = [item.read_text(encoding="utf-8-sig", errors="replace") for item in preamble_files if item.is_file()]
    texts += [core.document_header_includes(item.read_text(encoding="utf-8-sig", errors="replace")) or ""
              for item in md_paths if item.suffix.lower() in (".md", ".markdown", ".txt")]
    return any(OWN_SCRIPT_SETUP_RE.search(text) for text in texts)


# What to do about characters the main font cannot draw (`pdfmd-options: {fallback: ..., missing: ...}`,
# --fallback / --missing, the config file's `options:`). See CONFIG_TEMPLATE for the meaning of each.
FALLBACK_MODES = ("char", "word", "document", "off", "box", "error")


MISSING_MODES = ("warn", "box", "error")


FALLBACK_NAMES = {"character": "char", "per-character": "char", "run": "char", "words": "word",
                  "per-word": "word", "whole": "document", "whole-document": "document", "doc": "document",
                  "none": "off", "no": "off", "false": "off", "true": "word", "on": "word", "yes": "word",
                  "black-box": "box", "err": "error", "fail": "error"}


def normalise_mode(value, allowed: tuple[str, ...], aliases: dict[str, str], label: str, source: str) -> str | None:
    if value is None:
        return None
    if value is False:      # YAML reads a bare `off` or `no` as false
        text = "off"
    elif value is True:
        text = "on"
    else:
        text = str(value).strip().casefold()
    text = aliases.get(text, text)
    if text not in allowed:
        raise SystemExit(f"{source}: {label} {value!r} is not one of {', '.join(allowed)}")
    return text


def fallback_settings(md_path: Path, metadata_files: list[Path]) -> tuple[str, str]:
    """(fallback mode, missing mode): the command line, else the document, its metadata files, the
    config file, else word / warn. `box` and `error` as a fallback mode mean no fallback and that
    treatment of every missing character."""
    where = f"{md_path}: pdfmd-options"
    mode = normalise_mode(core.FALLBACK_CLI, FALLBACK_MODES, FALLBACK_NAMES, "--fallback", "pdfmd") or normalise_mode(
        core.first_pdfmd_option(md_path, metadata_files, "fallback"), FALLBACK_MODES, FALLBACK_NAMES,
        "fallback", where) or "word"
    missing = normalise_mode(core.MISSING_CLI, MISSING_MODES, FALLBACK_NAMES, "--missing", "pdfmd") or normalise_mode(
        core.first_pdfmd_option(md_path, metadata_files, "missing"), MISSING_MODES, FALLBACK_NAMES,
        "missing", where) or "warn"
    if mode in ("box", "error"):
        missing = mode
    return mode, missing


def mainfont_choice(md_paths: list[Path], metadata_files: list[Path], variables: list[str],
                    cli_font: str | None, document_font: bool, mainfont_auto: bool,
                    no_auto: list[str] | None, note=None) -> str | None:
    """The main font to pass to Pandoc (None: leave the document's own). A font the document or the
    command line names is never changed for a few missing characters -- that is the fallback's job --
    except in `fallback: document` mode, where the installed font that draws most of the document
    replaces it. pdfmd's own default (no font named) is changed, with an AUTO MAINFONT note, when it
    lacks letters of the script the document is mostly written in (STIX Two Text has no Kazakh
    Cyrillic), so the text is not set half in one font and half in another."""
    explicit = cli_font or (document_font_setting("mainfont", md_paths, metadata_files, variables)
                            if document_font else None)
    if explicit:
        base = explicit
    elif mainfont_auto:
        base = core.preferred_font()
    else:
        return None
    module, index = unicode_module(), font_index()
    if (module is not None and index is not None and not core.auto_disabled(no_auto, "unicode")
            and not own_script_setup(md_paths, [], variables, metadata_files)):
        mode = fallback_settings(md_paths[0], metadata_files)[0]
        text = unicode_source_text(md_paths, metadata_files) if mode in ("document", "char", "word") else ""
        if mode == "document":
            chosen = module.choose_document_font(text, base, index)
            reason = "fallback: document"
        elif mode in ("char", "word") and not explicit:
            chosen = module.choose_main_font(text, base, index)
            reason = "it lacks letters of the document's own script"
        else:
            chosen = base
        if chosen != base:
            if note:
                note("MAINFONT", f"{md_paths[0]}: {chosen} instead of {base} ({reason}; "
                                 f"name a font with mainfont: to keep your own)")
            return chosen
    if cli_font:
        return cli_font
    if not document_font and note:
        # pdfmd's own default, named like every other default it applies (v3.28.14; it was silent)
        note("MAINFONT", f"{md_paths[0]}: no mainfont set; using {base}")
    return None if document_font else base


def name_candidates(value: str) -> list[str]:
    value = core.strip_lookup_suffix(value)
    candidates = [value]
    if not core.TRANSLIT_CYRILLIC:  # --translit none
        return candidates
    if re.search("[А-Яа-яЁё]", value):
        candidates += core.cyrillic_candidates(value)
    else:
        candidates += core.latin_candidates(value)
    candidates = list(dict.fromkeys(candidates))
    return candidates + [f"Пробный {item}" for item in candidates]


def has_mainfont(md_path: Path, variables: list[str], metadata_files=()) -> bool:
    return has_font_setting("mainfont", md_path, variables, metadata_files)


def has_font_setting(key: str, md_path: Path, variables: list[str], metadata_files=()) -> bool:
    """Whether the document names this font itself: with -V, in its front matter, or in a metadata file it gets
    (the folder's metadata.yaml, the global one of pdfmd --setup). Until v3.28.14 only the first two counted, so
    pdfmd's own default (`-V mainfont=STIX Two Text`, `-V monofont=JetBrains Mono`) overrode a metadata file's."""
    if any(variable.startswith(f"{key}=") for variable in variables):
        return True
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = core.LEADING_FRONT_MATTER_RE.match(text)
    if front_matter and re.search(rf"^{key}\s*:", front_matter.group(1), re.MULTILINE):
        return True
    return any(core.metadata_file_yaml(path).get(key) not in (None, "") for path in metadata_files)


# Raw content (v3.28.17): ```{=latex} ... ``` and `x`{=html}, in any format, is not code -- Pandoc hands it to the
# writer as it is, and `{=pdfmd}` blocks are the same shape. A plain ```{pdfmd} fence (no `=`) is ordinary code.
# The fence is any run of three or more backticks (or tildes) -- a longer one lets the block hold shorter ones -- and
# the closing line is a run of at least as many.
CODE_RAW_FENCE_RE = re.compile(r"^[ \t]*(?P<fence>(?P<c>[`~])(?P=c){2,})[ \t]*\{=[^}\n]*\}[ \t]*\n.*?\n[ \t]*(?P=fence)(?P=c)*[ \t]*$",
                          re.MULTILINE | re.DOTALL)


CODE_RAW_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1\{=[^}\s]+\}", re.DOTALL)


def has_code_spans(text: str) -> bool:
    """Detect inline code or fenced code blocks -- the only things Pandoc's
    LaTeX writer actually sets in the monofont. A bare backtick covers both
    (a fence is just 3+ backticks), plus the rarer ``~~~`` fence style; raw
    blocks and spans (`{=latex}`, `{=html}`, `{=typst}`, `{=pdfmd}` ...) are not code.
    """
    text = CODE_RAW_SPAN_RE.sub("", CODE_RAW_FENCE_RE.sub("", core.EMBED_BLOCK_RE.sub("", text)))
    return "`" in text or bool(re.search(r"(?m)^\s{0,3}~~~", text))


# Characters no installed font draws (script_fallback has already warned about them): a
# missing-glyph warning that is only about those is not a reason to retry with another font.
UNICODE_UNCOVERED: set[int] = set()


# The families code needs for the characters its monofont lacks, for Typst's `codefont` list and
# WeasyPrint's CSS (script_fallback sets it; LaTeX gets them through its Lua filter instead).
UNICODE_CODE_FONTS: list[str] = []


MISSING_GLYPH_LINE_RE = re.compile(r"missing character|Missing character|Unicode character .* not set|font .* not found")


def missing_glyph_warning(output: str) -> bool:
    for line in output.splitlines():
        if not MISSING_GLYPH_LINE_RE.search(line):
            continue
        codes = {int(code, 16) for code in re.findall(r"U\+([0-9A-Fa-f]{4,6})", line)}
        if not codes or not codes <= UNICODE_UNCOVERED:
            return True
    return False


def missing_glyph_codes(output: str) -> list[int]:
    """The code points a build's missing-glyph lines name (LuaLaTeX and XeLaTeX print `There is no ≥ (U+2265) in font`),
    in order; characters no installed font draws are left out (script_fallback has warned about them). A count of the lines
    is no count of the uses: LuaLaTeX prints each missing character three times."""
    codes: dict[int, None] = {}
    for line in output.splitlines():
        if MISSING_GLYPH_LINE_RE.search(line):
            for code in re.findall(r"U\+([0-9A-Fa-f]{4,6})", line):
                if int(code, 16) not in UNICODE_UNCOVERED:
                    codes[int(code, 16)] = None
    return sorted(codes)


def retry_font_note(md_path: Path, tried: str, instead: str, codes: list[int]) -> str:
    """The WARN line for the missing-glyph retry that rebuilds the whole document in another font."""
    lacks = (f"lacks {', '.join(f'U+{code:04X}' for code in codes)}" if codes
             else "lacked glyphs the build did not name (--verbose shows the log)")
    return (f"WARN  {core.display_path(md_path)}: {tried} {lacks}; rebuilt in {instead} "
            "(set mainfont: to keep your own)")
