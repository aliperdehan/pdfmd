"""Typst spacing defaults, before a custom template's rules and inside Pandoc's default conf.

The Lua filter computes lengths from resolved metadata and variables. Template copies live in the
cache; custom templates' partials are copied with distinct names so relative lookups keep their base.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from pdfmd_base import core

from pdfmd_base import pandoc_run


_HEADING_WRAP: dict[tuple[int, ...], bool] = {}


def heading_args() -> list[str]:
    """`--wrap=none` for a Pandoc whose Typst writer wraps a long heading over several source lines (3.1.3 does): Typst
    reads the continuation as body text, which then swallows the next paragraph's first line. Asked of the writer once
    per Pandoc version; a writer that keeps its headings on one line (3.13) gets nothing, so its output is unchanged."""
    version = core.pandoc_version()
    if version not in _HEADING_WRAP:
        done = core.run_probe(["pandoc", "-f", "markdown", "-t", "typst"], input="# " + "word " * 30 + "\n")
        lines = done.stdout.splitlines() if done is not None and done.returncode == 0 else []
        _HEADING_WRAP[version] = (len(lines) > 1 and lines[0].startswith("= ") and lines[1].strip() != ""
                                  and not lines[1].startswith("<"))
    return ["--wrap=none"] if _HEADING_WRAP[version] else []


def line_spacing_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """LaTeX's line pitch by default, or Pandoc's unmodified Typst template (DECISION 96)."""
    value = core.first_pdfmd_option(md_path, metadata_files, "typst-line-spacing")
    mode = "latex" if value is None else str(value).strip().casefold()
    if mode not in ("latex", "pandoc"):
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.typst-line-spacing must be latex or pandoc, not {value!r}")
    return mode


def option_values(command: list[str], long: str, short: str = "") -> list[str]:
    """Values of a Pandoc option, including equals and attached short forms."""
    values = []
    for index, word in enumerate(command):
        if word == long or (short and word == short):
            if index + 1 < len(command):
                values.append(command[index + 1])
        elif word.startswith(long + "="):
            values.append(word.partition("=")[2])
        elif short and word.startswith(short) and word != short:
            values.append(word[len(short):])
    return values


def template_source(name: str, directory: Path, command: list[str], suffix: str = ".typst",
                    kind: str = "templates") -> tuple[str, Path]:
    """Read a template/partial using its original base and Pandoc's data-file fallback."""
    names = [Path(name)]
    if not Path(name).suffix:
        names.append(Path(name + suffix))
    data_dirs = [directory / path for path in option_values(command, "--data-dir")]
    if not data_dirs:
        home = Path.home()
        data_dirs = ([Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "pandoc"] if os.name == "nt" else
                     [Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "pandoc", home / ".pandoc"])
    locations = [directory, *(path / kind for path in data_dirs)]
    for location in locations:
        for item in names:
            path = location / item
            if path.is_file():
                return path.read_text(encoding="utf-8"), path.resolve()
    for item in names:
        data_args = [word for path in option_values(command, "--data-dir") for word in ("--data-dir", path)]
        done = pandoc_run(["pandoc", *data_args,
                               "--print-default-data-file", kind + "/" + item.as_posix()],
                              capture_output=True, cwd=directory, timeout=core.PROBE_TIMEOUT)
        if done.returncode == 0:
            return done.stdout.decode("utf-8", errors="replace"), directory / item
    raise FileNotFoundError(name)


def defaults_template(name: str, directory: Path, command: list[str], seen: set[Path]) -> str | None:
    """The template selected by a local defaults file (including its nested defaults)."""
    text, path = template_source(name, directory, command, ".yaml", "defaults")
    path = path.resolve()
    if path in seen:
        return None
    seen.add(path)
    try:
        data = core.yaml.safe_load(text) if core.yaml is not None else {}
    except core.yaml.YAMLError:
        return None
    data = data if isinstance(data, dict) else {}
    chosen = None
    parents = data.get("defaults", [])
    for parent in parents if isinstance(parents, list) else [parents]:
        chosen = defaults_template(str(parent).replace("${.}", str(path.parent)), directory, command, seen) or chosen
    if data.get("template") is not None:
        chosen = str(data["template"]).replace("${.}", str(path.parent))
    return chosen


def custom_template(command: list[str], directory: Path) -> str | None:
    """Command-line template over defaults-file templates, as Pandoc resolves them."""
    explicit = option_values(command, "--template")
    if explicit:
        return explicit[-1]
    chosen = None
    for name in option_values(command, "--defaults", "-d"):
        chosen = defaults_template(name, directory, command, set()) or chosen
    return chosen


def copy_partials(text: str, origin: Path, command: list[str], target: Path, stack: frozenset[Path] = frozenset()) -> str:
    """Keep Pandoc partial calls and their context, changing only their names to cached copies.

    Rewriting calls rather than inlining retains mapped partials and whitespace handling. Only Pandoc
    template tokens are inspected: Typst's own function calls and escaped dollar signs stay literal.
    """
    def token(match):
        if match.group(0) == "$$":
            return "$$"
        content = match.group(1) or match.group(2)

        def partial(call):
            source, path = template_source(call.group(1), origin.parent, command, origin.suffix)
            if path in stack:
                raise ValueError("recursive Typst template partial")
            source = copy_partials(source, path, command, target, stack | {path})
            name = "partial-" + hashlib.sha256((str(path) + source).encode()).hexdigest() + ".typ"
            destination = target / name
            if not destination.is_file():
                destination.write_text(source, encoding="utf-8")
            return name + "()"

        rewritten = re.sub(r"([\w./\\-]+)\(\)", partial, content)
        return "${" + rewritten + "}" if match.group(1) is not None else "$" + rewritten + "$"

    return re.sub(r"\$\$|\$\{([^}]+)\}|\$([^$\n]+)\$", token, text)


def css_heading_rules(document: Path, metadata_files: list[Path], no_auto, command: list[str]) -> str:
    from pdfmd_css.headings import heading_values, stylesheet_headings

    headings = stylesheet_headings(document, metadata_files, no_auto)
    if not headings:
        return ""
    variables = option_values(command, "--variable", "-V")
    size = core.document_font_setting("fontsize", [document], metadata_files, variables)
    points = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*pt\s*", str(size))
    base = float(points[1]) if points else 11.0    # Pandoc's default Typst text size
    lines = []
    for level, rule in headings.items():
        values = heading_values(rule, base)
        options = []
        if "colour" in values:
            options.append(f'fill: rgb("#{values["colour"]}")')
        if "size" in values:
            options.append(f'size: {values["size"]:g}pt')
        if "font" in values:
            options.append("font: " + json.dumps(values["font"], ensure_ascii=False))
        if "bold" in values:
            options.append('weight: "bold"' if values["bold"] else 'weight: "regular"')
        if "italic" in values:
            options.append('style: "italic"' if values["italic"] else 'style: "normal"')
        if options:
            lines.append(f"#show heading.where(level: {level}): set text({', '.join(options)})")
    return "\n".join(lines)


def template_args(writer: str, command: list[str], directory: Path | None = None, heading_rules: str = "") -> list[str]:
    """A cached template whose default rules yield separately to every custom setting."""
    if writer != "typst" or not command:
        return []
    metadata = option_values(command, "--metadata", "-M")
    spacing = "pdfmd-typst-line-spacing=pandoc" not in metadata
    unnumbered = "pdfmd-page-numbers=off" in metadata
    if not (spacing or unnumbered or heading_rules):
        return []
    directory = directory or Path.cwd()
    try:
        custom = custom_template(command, directory)
        pdf = any(word.lower().endswith(".pdf") for word in option_values(command, "--output", "-o"))
        if not pdf and custom is None and not any(word in ("-s", "--standalone") for word in command):
            return ["-V", f"pdfmd-css-headings={heading_rules}"] if heading_rules else []
        folder = core.cache_root() / "typst"
        folder.mkdir(parents=True, exist_ok=True)
        if custom is not None:
            template, origin = template_source(custom, directory, command)
            template = copy_partials(template, origin, command, folder, frozenset({origin}))
        else:
            template = pandoc_run(["pandoc", "-D", "typst"], capture_output=True, check=True,
                                      timeout=core.PROBE_TIMEOUT).stdout.decode("utf-8", errors="replace")
            if "$template.typst()$" in template:
                partial = pandoc_run(["pandoc", "--print-default-data-file", "templates/template.typst"],
                                         capture_output=True, check=True,
                                         timeout=core.PROBE_TIMEOUT).stdout.decode("utf-8", errors="replace")
                template = template.replace("$template.typst()$", partial)
            if spacing:
                original = "leading: linestretch * 0.65em"
                if original in template:
                    template = template.replace(original, "leading: $pdfmd-typst-leading$, spacing: $pdfmd-typst-spacing$")
                elif "set par(justify: true)" in template:
                    # Pandoc 3.1.3's conf has no linestretch parameter or leading rule.
                    template = template.replace("set par(justify: true)",
                                                "set par(justify: true, leading: $pdfmd-typst-leading$, "
                                                "spacing: $pdfmd-typst-spacing$)")
                else:
                    spacing = False
                    if not (unnumbered or heading_rules):
                        return []
        if unnumbered:
            # Newer Pandoc passes this argument to conf; 3.1.3 hard-codes the setting inside conf.
            template = re.sub(r'^([ \t]*)pagenumbering:[^\n]*\$page-numbering\$[^\n]*,$',
                              r'\1pagenumbering: none,', template, flags=re.M)
            if custom is None:
                template = template.replace('numbering: "1",', 'numbering: none,')
            else:
                template = '#set page(numbering: none)\n' + template
        if spacing:
            template = ('#set text(top-edge: $pdfmd-typst-top-edge$, bottom-edge: "baseline")\n'
                        '#set par(leading: $pdfmd-typst-leading$, spacing: $pdfmd-typst-spacing$)\n' + template)
        if heading_rules:
            # Rules in the user's template or its imported conf take precedence.
            template = heading_rules.replace("$", "$$") + "\n" + template
        target = folder / (hashlib.sha256(template.encode()).hexdigest() + ".typ")
        if not target.is_file():
            target.write_text(template, encoding="utf-8")
        if not spacing:
            return ["--template", str(target)]
        marker = "pdfmd-typst-template-rules" if custom is not None else "pdfmd-typst-template-default"
        return ["--template", str(target), "-M", marker + "=true"]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
