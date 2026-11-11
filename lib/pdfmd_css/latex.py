"""The style sheets of a document, as pdfmd finds and applies them: the scope, the sources, the Pandoc options and variables they
add, and the LaTeX headings (`--css`, `css-scope`).

Moved out of `pdfmd.py` unchanged (v3.33.10, SPLIT.md), with `CSS_COLOURS`, `CSS_HEADING_COMMANDS`, `CSS_HEADING_DEFAULTS` and
`CSS_HEADING_OWN_RE`. `core` is the `pdfmd` module, bound when the module is first loaded (the first binding wins); the pdfmd
names the code uses (`CSS_CLI`, `CSS_SCOPES`, `CSS_SCOPE_CLI` (rebound by `main()`), `cache_root`, which tests patch, and the
rest) are read as `core.X` when it runs. The package's own reader (`import pdfmd_css`) is imported inside the functions, as it was.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

core = None

def css_scope(md_path: Path, metadata_files: list[Path]) -> str:
    """``html`` (a style sheet is for the writers that read CSS: the default) or ``all``: the command line, else
    `pdfmd-options.css-scope`."""
    value = core.CSS_SCOPE_CLI if core.CSS_SCOPE_CLI is not None else core.first_pdfmd_option(md_path, metadata_files, "css-scope")
    value = str(value or "html").strip().casefold()
    return value if value in core.CSS_SCOPES else "html"


def css_names(value) -> list[str]:
    return [str(item) for item in ([value] if isinstance(value, str) else value if isinstance(value, list) else [])
            if str(item).strip()]


def css_sources(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None
                ) -> tuple[list[Path], list[Path], list[Path]]:
    """(found beside the document, named by `css:` of the front matter or a metadata file, named by pdfmd-options or the
    command line): each in the order the page reads them, files that exist only (a missing one is a WARN)."""
    def existing(names: list[str], origin: str) -> list[Path]:
        found: list[Path] = []
        for name in names:
            path = (md_path.parent / name).resolve()
            if path.is_file():
                found.append(path)
            else:
                print(f"WARN  {origin}: the style sheet {name} was not found beside {core.display_path(md_path)}", file=sys.stderr)
        return found

    beside: list[Path] = []
    if not core.auto_disabled(no_auto, "css"):
        for folder in core.accessory_directories(md_path.parent, md_path.stem):
            for name in (f"{md_path.stem}.css", "pdfmd.css"):
                if (folder / name).is_file() and (folder / name).resolve() not in beside:
                    beside.append((folder / name).resolve())
    keys: list[str] = []
    for item in metadata_files:
        keys += css_names(core.metadata_file_yaml(item).get("css"))
    try:
        keys += css_names(core.front_matter_dict(md_path.read_text(encoding="utf-8-sig")).get("css"))
    except (OSError, UnicodeDecodeError):                    # not a text file (a .docx is converted too)
        pass
    named = css_names(core.first_pdfmd_option(md_path, metadata_files, "css")) + [str(Path(item)) for item in core.CSS_CLI]
    return beside, existing(keys, "css:"), existing(named, "pdfmd-options.css / --css")


def css_additions(md_path: Path, metadata_files: list[Path], variables: list[str], no_auto: list[str] | None,
                  for_html: bool, note) -> tuple[list[str], list[str]]:
    """(Pandoc options, -V variables) the style sheets of a document add. The options are `--css FILE` for an HTML-family
    build, for the sheets Pandoc would not read itself (not `css:` of the metadata, which its template links). The
    variables are what `css-scope: all` finds in them that nothing of the document sets."""
    beside, keyed, named = css_sources(md_path, metadata_files, no_auto)
    options: list[str] = []
    if for_html:
        for path in dict.fromkeys([*beside, *named]):
            options += ["--css", str(path)]
        if beside or named:
            note("CSS", f"{', '.join(item.name for item in [*beside, *named])}: the HTML writers link it")
    if css_scope(md_path, metadata_files) != "all":
        if beside and not for_html:
            note("CSS", f"{', '.join(item.name for item in beside)}: found; --css-scope all reads it for this writer too")
        return options, []
    sheets = list(dict.fromkeys([*beside, *keyed, *named]))
    if not sheets:
        return options, []
    try:
        import pdfmd_css
    except ImportError:
        return options, []
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in sheets)
    translation = pdfmd_css.translate(text)
    added: list[str] = []
    geometry_set = core.has_geometry(md_path, list(variables), metadata_files)
    for variable in translation.variables:
        key = variable.split("=", 1)[0]
        if key.startswith("geometry"):
            if geometry_set:
                continue
        elif core.document_font_setting(key, [md_path], metadata_files, [*variables, *added]) is not None:
            continue
        added.append(variable)
    for said, taken in translation.used:
        if any(item in added for item in taken):                  # what the document sets is not said to come from the sheet
            note("CSS", f"{', '.join(item.name for item in sheets)}: {said} -> {', '.join(taken)}")
    if translation.ignored:
        note("CSS", "not used: " + ", ".join(translation.ignored[:12]) + (" ..." if len(translation.ignored) > 12 else ""))
    return options, added


# Headings from a style sheet for LaTeX (v3.29.8, `css-scope: all`). `h1`-`h5` (`h6` has no LaTeX counterpart) with a colour, a
# size, a family, a weight or a style become titlesec's \\titleformat*{\\section} ... {\\subparagraph} (the starred form: the numbering and
# the spacing stay the class's) in a header file of their own. They are
# for the plain article class only, and never over a document that formats its headings itself: a titlesec / sectsty /
# KOMA / memoir command or an own \\section in its preamble, header-includes or metadata is reported, and nothing is added.
CSS_HEADING_COMMANDS = {1: "section", 2: "subsection", 3: "subsubsection", 4: "paragraph", 5: "subparagraph"}
CSS_HEADING_OWN_RE = re.compile(
    r"titlesec|sectsty|titletoc|titleps|\\titleformat|\\titlespacing|\\(?:all)?(?:sub)*(?:section|paragraph)font|\\setkomafont|"
    r"\\addtokomafont|\\RedeclareSectionCommand|\\@startsection|\\chapterstyle|\\setsecheadstyle|"
    r"\\(?:re)?newcommand\*?\s*\{?\\(?:sub)*section\b|\\def\\(?:sub)*section\b")
CSS_HEADING_DEFAULTS = {1: "\\Large", 2: "\\large", 3: "\\normalsize", 4: "\\normalsize", 5: "\\normalsize"}    # article's own
CSS_COLOURS = {    # CSS's named colours (not xcolor's: its `green` is #00FF00)
    "black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000", "blue": "0000FF", "yellow": "FFFF00",
    "gray": "808080", "grey": "808080", "silver": "C0C0C0", "maroon": "800000", "purple": "800080", "fuchsia": "FF00FF",
    "magenta": "FF00FF", "lime": "00FF00", "olive": "808000", "navy": "000080", "teal": "008080", "aqua": "00FFFF",
    "cyan": "00FFFF", "orange": "FFA500", "brown": "A52A2A", "pink": "FFC0CB", "gold": "FFD700", "crimson": "DC143C",
    "indigo": "4B0082", "darkgreen": "006400", "darkblue": "00008B", "darkred": "8B0000", "darkgray": "A9A9A9",
    "darkgrey": "A9A9A9", "lightgray": "D3D3D3", "lightgrey": "D3D3D3", "steelblue": "4682B4", "royalblue": "4169E1",
    "firebrick": "B22222", "slategray": "708090", "dimgray": "696969", "tomato": "FF6347", "coral": "FF7F50"}


def css_heading_latex(headings: dict[int, dict[str, str]], base_pt: float, say) -> list[str]:
    """The LaTeX lines (titlesec) for the headings of a style sheet; `say(text)` is told what was left out."""
    import pdfmd_css
    fonts: list[str] = []
    commands: list[str] = []
    for level in sorted(headings):
        if level not in CSS_HEADING_COMMANDS:
            say(f"h{level} (LaTeX has no sixth heading level)")
            continue
        found = headings[level]
        size_part, colour_part, family_part = CSS_HEADING_DEFAULTS[level], "", ""
        weight_part, style_part = "\\bfseries", ""
        changed = False
        size = found.get("font-size", "").strip().lower()
        if size:
            value = pdfmd_css.length_points(size)
            if value is None and re.fullmatch(r"\d*\.?\d+(em|rem|%)", size):
                number = float(re.match(r"[\d.]+", size).group(0))
                value = number / 100 * base_pt if size.endswith("%") else number * base_pt
            if value is not None and 5 <= value <= 60:
                size_part, changed = f"\\fontsize{{{value:g}}}{{{value * 1.2:.1f}}}\\selectfont", True
            else:
                say(f"h{level} font-size {size}")
        colour = found.get("color", "").strip()
        if colour:
            hexed = re.fullmatch(r"#([0-9a-fA-F]{6})", colour) or re.fullmatch(r"#([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])", colour)
            if hexed:
                digits = "".join(hexed.groups()) if len(hexed.groups()) == 1 else "".join(2 * item for item in hexed.groups())
                colour_part, changed = f"\\color[HTML]{{{digits.upper()}}}", True
            elif colour.lower() in CSS_COLOURS:
                colour_part, changed = f"\\color[HTML]{{{CSS_COLOURS[colour.lower()]}}}", True
            else:
                say(f"h{level} color {colour}")
        weight = found.get("font-weight", "").strip().lower()
        if weight:
            if weight in ("bold", "bolder") or (weight.isdigit() and int(weight) >= 600):
                weight_part, changed = "\\bfseries", True
            elif weight in ("normal", "lighter") or (weight.isdigit() and int(weight) < 600):
                weight_part, changed = "\\mdseries", True
            else:
                say(f"h{level} font-weight {weight}")
        style = found.get("font-style", "").strip().lower()
        if style in ("italic", "oblique"):
            style_part, changed = "\\itshape", True
        elif style and style != "normal":
            say(f"h{level} font-style {style}")
        family = pdfmd_css.first_family(found.get("font-family", "")) if found.get("font-family") else None
        if family:
            name = f"\\pdfmdhead{'abcde'[level - 1]}"
            fonts.append(f"\\@ifpackageloaded{{fontspec}}{{\\newfontfamily{name}{{{family}}}}}{{\\let{name}\\relax}}")
            family_part, changed = name, True
        if changed:
            commands.append(f"\\titleformat*{{\\{CSS_HEADING_COMMANDS[level]}}}"
                            f"{{\\normalfont{family_part}{size_part}{weight_part}{style_part}{colour_part}}}")
    if not commands:
        return []
    return ["\\makeatletter", "\\@ifpackageloaded{xcolor}{}{\\usepackage{xcolor}}", *fonts, "\\makeatother",
            "\\IfFileExists{titlesec.sty}{\\usepackage{titlesec}", *commands, "}{\\PackageWarningNoLine{pdfmd}{titlesec.sty is not "
            "installed: the headings of the style sheet are not applied}}"]


def css_heading_args(sources: Path | list[Path], metadata_files: list[Path], variables: list[str], no_auto: list[str] | None,
                     note) -> list[str]:
    """`--include-in-header` for the headings of the style sheets of a LaTeX build (`css-scope: all`), or []."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or css_scope(files[0], metadata_files) != "all":
        return []
    sheets = list(dict.fromkeys(item for group in css_sources(files[0], metadata_files, no_auto) for item in group))
    if not sheets:
        return []
    try:
        import pdfmd_css
    except ImportError:
        return []
    translation = pdfmd_css.translate("\n".join(path.read_text(encoding="utf-8", errors="replace") for path in sheets))
    if not translation.headings:
        return []
    names = ", ".join(sorted(f"h{level}" for level in translation.headings))
    metadata = core.effective_metadata(files[0], metadata_files, list(variables))
    klass = str(metadata.get("documentclass") or "article").strip()
    if klass != "article":
        note("CSS", f"{names} not applied to the headings: the document class is {klass} (they are set for article only)")
        return []
    own: list[tuple[str, str]] = []
    kept = core.pandoc_header_includes(files, metadata_files)
    if kept:
        own.append(("header-includes", kept[0]))
    for path in core.document_preambles(files[0], [], no_auto, metadata_files):
        own.append((path.name, core.read_text_best_effort(path)))
    for where, text in own:
        found = CSS_HEADING_OWN_RE.search(text)
        if found:
            note("CSS", f"{names} not applied to the headings: {where} formats them itself ({found.group(0).strip()})")
            return []
    size = next((item.split("=", 1)[1] for item in variables if item.startswith("fontsize=")),
                str(metadata.get("fontsize") or next((item.split("=", 1)[1] for item in translation.variables
                                                      if item.startswith("fontsize=")), "")))
    found_size = re.match(r"(\d+(?:\.\d+)?)", size)
    base = float(found_size.group(1)) if found_size else 10.0
    left_out: list[str] = []
    lines = css_heading_latex(translation.headings, base, left_out.append)
    if left_out:
        note("CSS", "headings not used: " + ", ".join(left_out))
    if not lines:
        return []
    text = "% pdfmd: the headings of the style sheet (css-scope: all)\n" + "\n".join(lines) + "\n"
    path = core.cache_root() / "tex" / f"packages-css-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    except OSError:
        return []
    note("CSS", f"{names}: the headings take the style sheet's colour, size and font (titlesec)")
    return ["--include-in-header", str(path)]
