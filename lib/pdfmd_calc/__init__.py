"""Calculator settings, constants input and exported names.

Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_calc`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pdfmd_base import core


CALC_DIV_RE = re.compile(r"^[ \t]*:{3,}[ \t]*(?:calc\b|\{[^}\n]*\.calc\b)", re.MULTILINE)


CALC_SPAN_RE = re.compile(r"`\{=(?:\d+[a-z]{2}|calc)?\}|^[ \t]*:{3,}[ \t]*(?:calc\b|\{[^}\n]*\.calc\b)"
                         r"|^[ \t]*(?:`{3,}|~{3,})[ \t]*\{=(?:calc)?\}[ \t]*$", re.MULTILINE)


CALC_ENV = "PDFMD_CALC"


CALC_DIGITS_ENV = "PDFMD_CALC_DIGITS"


CALC_ROUND_ENV = "PDFMD_CALC_ROUND"


CALC_SUBS_ENV = "PDFMD_CALC_SUBS"


CALC_TYPESET_ENV = "PDFMD_CALC_TYPESET"


CALC_TYPESET_STYLE_ENVS = {"upright": "PDFMD_CALC_TYPESET_UPRIGHT", "italic": "PDFMD_CALC_TYPESET_ITALIC"}


CALC_TYPESET_PIECE_RE = re.compile(r"^[A-Za-z]+$")


CALC_NOINDENT_ENV = "PDFMD_CALC_NOINDENT"


CALC_SPACE_ENV = "PDFMD_CALC_SPACE"


CALC_ALIGN_ENV = "PDFMD_CALC_ALIGN"


CALC_SPACE_DEFAULT = "0.75em"


CALC_SPACE_RE = re.compile(r"^(?:\d+\.?\d*|\.\d+)(?:pt|mm|cm|in|em)$")


CALC_ALIGNS = ("left", "center")


CALC_TYPESETS = ("off", "inline", "display")


CALC_CONSTANTS_ENV = "PDFMD_CALC_CONSTANTS"


CALC_EXPORT_ENV = "PDFMD_CALC_EXPORT"


CALC_ROUNDS = ("even", "away")


CALC_DIGITS_RE = re.compile(r"(\d+)\s*(sf|dp)", re.IGNORECASE)


def calc_option(md_path: Path, metadata_files: list[Path], field: str):
    """`pdfmd-options.calc.<field>`; `calc: off` alone means `enabled: off`."""
    value = core.first_pdfmd_option(md_path, list(metadata_files), "calc")
    if isinstance(value, dict):
        return value.get(field)
    return value if field == "enabled" else None


def calc_is_off(md_path: Path, metadata_files: list[Path]) -> bool:
    value = os.environ.get(CALC_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "enabled")
    if value is None:
        return False
    flag = core.option_flag(value)
    if flag is None:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.enabled must be true or false, not {value!r}")
    return not flag


def calc_round_mode(md_path: Path, metadata_files: list[Path]) -> str:
    value = os.environ.get(CALC_ROUND_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "round")
    mode = str(value).strip().lower() if value is not None else "even"
    if mode not in CALC_ROUNDS:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.round must be even or away, not {value!r}")
    return mode


def calc_subs_on(md_path: Path, metadata_files: list[Path]) -> bool:
    """`calc: {subs: true}`: every {ans} is preceded by the expression with its names replaced by their values."""
    value = os.environ.get(CALC_SUBS_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "subs")
    if value is None:
        return False
    flag = core.option_flag(value)
    if flag is None:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.subs must be true or false, not {value!r}")
    return flag


def calc_typeset_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """`calc: {typeset: ...}`: "off" (the default; the calculator prints the plain text it was written in), "inline" (true; each
    calculation a line of inline maths, its label and unit text) or "display" (a centred display formula per `::: calc` line,
    the label and the unit inside it as \\text)."""
    value = os.environ.get(CALC_TYPESET_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "typeset")
    if value is None:
        return "off"
    word = str(value).strip().lower()
    if word in CALC_TYPESETS:
        return word
    flag = core.option_flag(value)
    if flag is None:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.typeset must be true, false or display, not {value!r}")
    return "inline" if flag else "off"


def calc_typeset_styles(md_path: Path, metadata_files: list[Path]) -> dict[str, list[str]]:
    """`calc: {typeset-upright: [V, k], typeset-italic: [el, DNA]}`: pieces of a name that a typeset calculation sets upright or italic
    against the default (a one-letter piece italic, a longer one upright). A piece is the letters of a name's base or one word after an
    underscore (`V_el` has V and el); a list or a comma/space separated string. Returns {"upright": [...], "italic": [...]}."""
    found: dict[str, list[str]] = {}
    for style, env in CALC_TYPESET_STYLE_ENVS.items():
        value = os.environ.get(env)
        if value is None:
            value = calc_option(md_path, metadata_files, "typeset-" + style)
        if value is None or value is False:
            found[style] = []
            continue
        words = [str(item) for item in value] if isinstance(value, list) else [value if isinstance(value, str) else str(value)]
        pieces = [piece for word in words for piece in re.split(r"[,\s]+", word.strip()) if piece]
        if [piece.casefold() for piece in pieces] == ["none"] or [piece.casefold() for piece in pieces] == ["off"]:
            pieces = []
        for piece in pieces:
            if not CALC_TYPESET_PIECE_RE.match(piece):
                raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.typeset-{style}: {piece!r} is not a piece of a name. "
                                 f"Give the letters of a base or of one word after an underscore (V, el, DNA), not V_el or A260")
        found[style] = list(dict.fromkeys(pieces))
    both = [piece for piece in found["upright"] if piece in found["italic"]]
    if both:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.typeset-upright and typeset-italic both list {', '.join(both)}")
    return found


def calc_noindent_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """`calc: {noindent: ...}`: "lines" (the default, 3.33.18; a `::: calc` div's calculation lines have no first-line indent, its
    prose keeps the document's), "all" (true, all: no paragraph of the div is indented, 3.30.9) or "off" (false: the document's
    indent everywhere)."""
    value = os.environ.get(CALC_NOINDENT_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "noindent")
    if value is None:
        return "lines"
    word = str(value).strip().lower()
    if word in ("lines", "all"):
        return word
    flag = core.option_flag(value)
    if flag is None:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.noindent must be lines, true (all) or false, not {value!r}")
    return "all" if flag else "off"


def calc_space(md_path: Path, metadata_files: list[Path]) -> str | None:
    """`calc: {space: 0.75em}`: the room above and below a `::: calc` div (pt, mm, cm, in or em), 0.75em unless set; off, false or 0 gives none."""
    value = os.environ.get(CALC_SPACE_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "space")
    if value is None or value is True:
        return CALC_SPACE_DEFAULT
    text = str(value).strip().lower().replace(" ", "")
    if value is False or text in ("", "off", "none", "false", "no", "0", "0.0"):
        return None
    if text in ("on", "true", "yes"):
        return CALC_SPACE_DEFAULT
    if not CALC_SPACE_RE.match(text):
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.space must be a length such as 0.75em or 6pt "
                         f"(pt, mm, cm, in, em), or off, not {value!r}")
    return text


def calc_align(md_path: Path, metadata_files: list[Path]) -> str:
    """`calc: {align: center}` centres the lines of a `::: calc` div; left (the default) leaves them flush left."""
    value = os.environ.get(CALC_ALIGN_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "align")
    text = str(value).strip().lower() if value is not None else "left"
    if text not in CALC_ALIGNS:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.align must be left or center, not {value!r}")
    return text


def calc_constants_file(md_path: Path, metadata_files: list[Path]) -> Path | None:
    """`calc: {constants: FILE}`: the file, looked for beside the document, beside each metadata file, then in the cwd."""
    value = os.environ.get(CALC_CONSTANTS_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "constants")
    if value is None or str(value).strip().casefold() in ("", "none", "off"):
        return None
    name = Path(os.path.expanduser(str(value).strip()))
    candidates = [name] if name.is_absolute() else [md_path.parent / name, *(m.parent / name for m in metadata_files), Path.cwd() / name]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.constants: no file {str(value)!r} (looked beside the document "
                     f"and its metadata files)")


def calc_export_file(md_path: Path, metadata_files: list[Path]) -> Path | None:
    """`calc: {export: FILE}` / --calc-export: the CSV the build writes with the calculator's names (the mirror of
    `constants`), a relative name beside the document. None when nothing asks for one."""
    value = os.environ.get(CALC_EXPORT_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "export")
    if value is None or str(value).strip().casefold() in ("", "none", "off", "false"):
        return None
    name = Path(os.path.expanduser(str(value).strip()))
    return name if name.is_absolute() else md_path.parent / name


def write_calc_export(dump: str, target: Path) -> int:
    """`name,value,digits` from the text of calc.lua's dump (name TAB value TAB digits, value at %.17g), sorted by name, written
    atomically: the format `calc_constants_statements()` reads back, so the file is a constants file as it is. A value that is not a
    finite number has no form a constants file could hold and is left out. The number of names written (0: no file)."""
    rows = []
    for line in dump.splitlines():
        fields = line.split("\t")
        if len(fields) < 2 or not fields[0] or fields[1] in ("nan", "inf", "-inf"):
            continue
        rows.append((fields[0], fields[1], fields[2] if len(fields) > 2 else ""))
    if not rows:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    core.atomic_write_text(target, "name,value,digits\n" + "".join(f"{name},{value},{digits}\n" for name, value, digits in sorted(rows)),
                      newline="\n")
    return len(rows)


def calc_constants_statements(path: Path) -> list[str]:
    """The lines `name = value` (or `name = value = {ans:4sf}` with a digits column) of a constants file: columns
    name,value[,digits[,note]], comma, semicolon or tab separated, an optional header row, # lines and blank lines skipped."""
    import csv
    lines = [line for line in core.read_text_best_effort(path).splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        return []
    head = lines[0]
    delimiter = "\t" if head.count("\t") else ";" if head.count(";") > head.count(",") else ","
    statements = []
    for row in csv.reader(lines, delimiter=delimiter):
        cells = [cell.strip() for cell in row]
        if not cells or not any(cells):
            continue
        if cells[0].casefold() == "name":
            continue
        if len(cells) < 2 or not cells[0] or not cells[1]:
            raise SystemExit(f"{core.display_path(path)}: a constant needs a name and a value (name,value[,digits[,note]]): {','.join(cells)!r}")
        statement = f"{cells[0]} = {cells[1]}"
        if len(cells) > 2 and cells[2]:
            digits = calc_digits_value(cells[2])
            if digits is None:
                raise SystemExit(f"{core.display_path(path)}: the digits of {cells[0]} must be like 4sf or 2dp, not {cells[2]!r}")
            statement += " = {ans:" + digits + "}"
        statements.append(statement)
    return statements


def calc_digits_value(value) -> str | None:
    """``4sf`` / ``2dp`` from what was written (None when it is no format)."""
    found = CALC_DIGITS_RE.fullmatch(str(value).strip())
    if not found:
        return None
    count, kind = int(found.group(1)), found.group(2).lower()
    if (kind == "sf" and not 1 <= count <= 15) or (kind == "dp" and count > 15):
        return None
    return f"{count}{kind}"


def calc_digits_mode(md_path: Path, metadata_files: list[Path]) -> str | None:
    value = os.environ.get(CALC_DIGITS_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "digits")
    if value is None or str(value).strip().casefold() in ("", "none", "auto"):
        return None
    found = calc_digits_value(value)
    if found is None:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.calc.digits must be like 4sf (four significant figures) "
                         f"or 2dp (two decimal places), not {value!r}")
    return found


def context_inputs(parts: list[Path], scratch: Path) -> list[Path]:
    """Hidden calculator slots before each selected part, after the scaffold's own definitions."""
    inputs = []
    for slot, part in enumerate(parts):
        mark = scratch / f"calc-context-{slot}.md"
        mark.write_text(f"pdfmd-calc-context-{slot}\n", encoding="utf-8")
        inputs += [mark, part]
    return inputs


def context_sections(text: str) -> str:
    """Keep selected runs of the marked whole document, with a hidden slot at each boundary."""
    pieces = re.split(r"(?m)^pdfmd-calc-mark-(?:in|out)[ \t]*$", text)
    front = core.LEADING_FRONT_MATTER_RE.match(pieces[0])
    head = front.group(0) if front else ""
    return head + "\n\n".join(f"pdfmd-calc-context-{slot}\n\n{pieces[index]}"
                                 for slot, index in enumerate(range(1, len(pieces), 2))) + "\n"
