"""The hanging indent of a bibliography: one setting for every writer (`bibliography-indent`).

`pdfmd-options: {bibliography-indent: 0.5in}` (the document, its metadata files, the folder layers, the global setup), or
`--bibliography-indent LENGTH` for a run (Pandoc's `--bibliography` is a registered pass-through, so it is never read as this
flag shortened; DECISION 82): how far the lines of an entry after its first are set in, in the combined reference
list and in the entries `fullcite` places in the text, so the two match. A length (pt, mm, cm, in, em), `0` for none, or
`auto` / not set: Pandoc's own, 1.5em, which writers other than Typst already apply to the list as they do today (LaTeX 1.5em,
HTML 2em from its style sheet, Word 0.5in) and Typst, whose writer ignores the style's `hanging-indent`, now gets (1.5em).
Only a style that asks for a hanging indent has one (citeproc's `hanging-indent` class on the list); a numbered style has none.

`pdfmd_lua/bibliography_indent.lua` does the list after `--citeproc`, per writer: `\\cslhangindent` for LaTeX, `#set par(hanging-indent:)`
around the list for Typst, a style on each entry for HTML, and a paragraph style `pdfmd-hang-<length>` for Word and OpenDocument
(`pdfmd_office` writes its indent afterwards). The indent filter goes in only when the setting is set, or for Typst (the default).
A separate post-citeproc filter applies opt-in bibliography line spacing locally. The entries of
`fullcite` take the same value (`pdfmd_fullcite`).

`core` is the `pdfmd` module (`from pdfmd_base import core`); the names used (`first_pdfmd_option`, `display_path`) are read as
`core.X` when the code runs.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal
from math import isfinite
from pathlib import Path

from pdfmd_base import core
from pdfmd_log import emit

ENV = "PDFMD_BIBLIOGRAPHY_INDENT"         # --bibliography-indent, set by main(), so -j workers read it too
KEY = "bibliography-indent"
DEFAULT = "1.5em"                         # Pandoc's own (\cslhangindent); the author decided it (entry D53)
ACCEPTED = "a length such as 0.5in or 1.5em (pt, mm, cm, in, em), 0 for none, or auto"
LENGTH_RE = re.compile(r"(?:\d+(?:\.\d+)?|\.\d+)(?:pt|mm|cm|in|em)")
ZERO_RE = re.compile(r"(?:0+(?:\.0*)?|\.0+)(?:pt|mm|cm|in|em)?")
SPACING_KEY = "bibliography-line-spacing"


def normalise(value) -> str | None:
    """The length as every writer takes it, `0pt` for none, or None for auto (and not set). Raises ValueError for anything else."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(value)
    text = str(value).strip().lower().replace(" ", "")
    if text in ("", "auto"):
        return None
    if ZERO_RE.fullmatch(text):
        return "0pt"
    if LENGTH_RE.fullmatch(text):
        return text
    raise ValueError(value)


def command_line_value(value: str) -> str:
    """--bibliography-indent as main() hands it to the builds (`auto` for auto); a bad value stops the run."""
    try:
        return normalise(value) or "auto"
    except ValueError:
        raise SystemExit(f"--bibliography-indent must be {ACCEPTED}, not {value!r}") from None


def bibliography_indent_command_line(value: str) -> None:
    """Pass a validated command-line value to this run and its batch workers."""
    os.environ[ENV] = command_line_value(value)


def setting(md_path: Path, metadata_files: list[Path]) -> str | None:
    """The indent asked for (`0pt` for none), None for auto: --bibliography-indent, else `pdfmd-options.bibliography-indent`."""
    value = os.environ.get(ENV)
    if value is not None:
        return command_line_value(value) if value != "auto" else None
    value = core.first_pdfmd_option(md_path, metadata_files, KEY)
    try:
        return normalise(value)
    except ValueError:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.{KEY} must be {ACCEPTED}, not {value!r}") from None


def bibliography_indent_args(sources: Path | list[Path], metadata_files: list[Path], cmd: list[str], pandoc_options: list[str],
                             writer: str) -> list[str]:
    """The combined list's hanging indent after citeproc, when set or for Typst."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or ("--citeproc" not in cmd and "--citeproc" not in pandoc_options):
        return []
    value = setting(files[0], metadata_files)
    if value is None and writer not in ("typst", "typ"):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("bibliography_indent")
    if shipped is None:
        return []
    return ["-M", f"pdfmd-bibliography-indent={value}" if value else f"pdfmd-bibliography-indent-default={DEFAULT}",
            "--lua-filter", str(shipped)]


def normalise_spacing(value) -> str:
    """A spacing mode or a decimal usable by LaTeX, Typst, CSS and Word."""
    if value is False:  # PyYAML reads an unquoted off as false.
        return "off"
    text = str(value).strip().casefold()
    if text in ("off", "style"):
        return text
    if re.fullmatch(r"\+?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:e[+-]?[0-9]+)?", text):
        number = float(text)
        if isfinite(number) and number > 0:
            decimal = format(Decimal(text), "f")
            return decimal.rstrip("0").rstrip(".") if "." in decimal else decimal
    raise ValueError(value)


def checked_spacing(value, key: str, source: Path) -> str:
    try:
        return normalise_spacing(value)
    except ValueError:
        raise SystemExit(f"{core.display_path(source)}: pdfmd-options.{key} must be off, style, or a positive number, "
                         f"not {value!r}") from None


def csl_option(source: Path, metadata_files: list[Path]) -> tuple[str | None, str | None]:
    """The pdfmd-options alias's file and spacing, each optional in the mapping."""
    value = core.first_pdfmd_option(source, metadata_files, "csl")
    if value is None:
        return None, None
    where = f"{core.display_path(source)}: pdfmd-options.csl"
    if isinstance(value, dict):
        for key in value:
            if key not in ("file", "spacing"):
                raise SystemExit(f"{where}: unknown key {key!r}; allowed keys are file and spacing")
        path = value.get("file")
        if "file" in value and (not isinstance(path, str) or not path.strip()):
            raise SystemExit(f"{where}.file must be a CSL file path, not {path!r}")
        spacing = checked_spacing(value["spacing"], "csl.spacing", source) if "spacing" in value else None
        return path.strip() if path is not None else None, spacing
    if isinstance(value, str) and value.strip():
        return value.strip(), None
    raise SystemExit(f"{where} must be a CSL file path or a mapping with file and spacing, not {value!r}")


def bibliography_spacing_args(source: Path, metadata_files: list[Path], command: list[str]) -> list[str]:
    """Validate the setting and apply it to the combined list after citeproc."""
    import sys

    _, alias = csl_option(source, metadata_files)
    mode = None
    for _, options in core.option_sources(source, metadata_files):
        if SPACING_KEY in options:
            mode = checked_spacing(options[SPACING_KEY], SPACING_KEY, source)
            break
    if mode is not None and alias is not None and mode != alias:
        emit("warning", None, f"WARN  {core.display_path(source)}: pdfmd-options.{SPACING_KEY} ({mode}) overrides csl.spacing ({alias})",
              file=sys.stderr)
    mode = mode or alias
    if mode in (None, "off") or "--citeproc" not in command:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("bibliography_spacing")
    return ["-M", f"pdfmd-bibliography-line-spacing={mode}", "--lua-filter", str(shipped)] if shipped is not None else []


def native_path_args(command: list[str], writer: str | None = None) -> list[str]:
    """Literal resources for BibTeX/Biber and native Typst, after the document's own filters."""
    typst = writer == "typst" and "--citeproc" not in command
    if not typst and not any(option in command for option in ("--natbib", "--biblatex")):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("bibliography_paths")
    return ["--lua-filter", str(shipped)] if shipped is not None else []


def native_csl_args(command: list[str]) -> list[str]:
    """Keep a file's original CSL string before Pandoc smartens quotes in YAML metadata.

    These internal commands start with their input paths, then -o; metadata files are in Pandoc's application order.
    Command-line CSL selections remain Pandoc's; document filters still run after the --csl option is read.
    """
    from pdfmd_args import metadata_keys

    if "csl" in metadata_keys(command) or any(option == "--csl" or option.startswith("--csl=") for option in command):
        return []
    if "-o" not in command:
        return []
    value = None
    tokens = iter(command)
    for token in tokens:
        if token == "--metadata-file":
            path = next(tokens, "")
        elif token.startswith("--metadata-file="):
            path = token.split("=", 1)[1]
        else:
            continue
        if path:
            value = core.metadata_file_yaml(Path(path)).get("csl", value)
    for source in command[1:command.index("-o")]:
        value = core.front_matter_dict(core.read_text_best_effort(Path(source))).get("csl", value)
    return ["--csl", value] if isinstance(value, str) and value.strip() else []


def typst_path_args(command: list[str]) -> list[str]:
    """Native bibliography/style resources may lie outside Pandoc's temporary Typst project."""
    root = []
    if "--pdf-engine=typst" in command and not any("--root" in option for option in command):
        root = ["--pdf-engine-opt=--root=/"]
    style = native_csl_args(command) if "--citeproc" not in command else []
    return root + style + native_path_args(command, "typst")
