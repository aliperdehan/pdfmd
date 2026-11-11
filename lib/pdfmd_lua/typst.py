"""Typst spacing defaults, before a custom template's rules and inside Pandoc's default conf.

The Lua filter computes lengths from resolved metadata and variables. Template copies live in the
cache; custom templates' partials are copied with distinct names so relative lookups keep their base.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

core = None


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
        done = subprocess.run(["pandoc", *data_args,
                               "--print-default-data-file", kind + "/" + item.as_posix()],
                              capture_output=True, text=True, cwd=directory)
        if done.returncode == 0:
            return done.stdout, directory / item
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


def template_args(writer: str, command: list[str], directory: Path | None = None) -> list[str]:
    """A cached template whose default rules yield separately to every custom setting."""
    if writer != "typst" or not command:
        return []
    directory = directory or Path.cwd()
    try:
        custom = custom_template(command, directory)
        pdf = any(word.lower().endswith(".pdf") for word in option_values(command, "--output", "-o"))
        if not pdf and custom is None and not any(word in ("-s", "--standalone") for word in command):
            return []
        folder = core.cache_root() / "typst"
        folder.mkdir(parents=True, exist_ok=True)
        if custom is not None:
            template, origin = template_source(custom, directory, command)
            template = copy_partials(template, origin, command, folder, frozenset({origin}))
        else:
            template = subprocess.run(["pandoc", "-D", "typst"], capture_output=True, text=True, check=True).stdout
            if "$template.typst()$" in template:
                partial = subprocess.run(["pandoc", "--print-default-data-file", "templates/template.typst"],
                                         capture_output=True, text=True, check=True).stdout
                template = template.replace("$template.typst()$", partial)
            original = "leading: linestretch * 0.65em"
            if original not in template:
                return []
            template = template.replace(original, "leading: $pdfmd-typst-leading$, spacing: $pdfmd-typst-spacing$")
        template = ('#set text(top-edge: $pdfmd-typst-top-edge$, bottom-edge: "baseline")\n'
                    '#set par(leading: $pdfmd-typst-leading$, spacing: $pdfmd-typst-spacing$)\n' + template)
        target = folder / (hashlib.sha256(template.encode()).hexdigest() + ".typ")
        if not target.is_file():
            target.write_text(template, encoding="utf-8")
        marker = "pdfmd-typst-template-rules" if custom is not None else "pdfmd-typst-template-default"
        return ["--template", str(target), "-M", marker + "=true"]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
