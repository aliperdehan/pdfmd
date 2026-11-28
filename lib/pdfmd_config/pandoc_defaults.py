"""Resolve Pandoc options and defaults without depending on the optional Lua package."""
from __future__ import annotations

import os
from pathlib import Path

from pdfmd_base import core
from pdfmd_base import pandoc_run


def option_values(command: list[str], long: str, short: str = "") -> list[str]:
    """Values of a Pandoc option, including equals and attached short forms."""
    values = []
    for index, word in enumerate(command):
        if word == "--":
            break
        if word == long or (short and word == short):
            if index + 1 < len(command):
                values.append(command[index + 1])
        elif word.startswith(long + "="):
            values.append(word.partition("=")[2])
        elif short and word.startswith(short) and word != short:
            values.append(word[len(short):])
    return values


def template_source(name: str, directory: Path, command: list[str], suffix: str = ".typst",
                    kind: str = "templates", *, local_only: bool = False) -> tuple[str, Path]:
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
    if local_only:
        raise FileNotFoundError(name)
    for item in names:
        data_args = [word for path in option_values(command, "--data-dir") for word in ("--data-dir", path)]
        done = pandoc_run(["pandoc", *data_args,
                               "--print-default-data-file", kind + "/" + item.as_posix()],
                              capture_output=True, cwd=directory, timeout=core.PROBE_TIMEOUT)
        if done.returncode == 0:
            return done.stdout.decode("utf-8", errors="replace"), directory / item
    raise FileNotFoundError(name)


def defaults_option(name: str, directory: Path, command: list[str], seen: set[Path], key: str):
    """An option selected by a local defaults file (including its nested defaults)."""
    text, path = template_source(name, directory, command, ".yaml", "defaults")
    path = path.resolve()
    if path in seen:
        return None
    seen.add(path)
    try:
        data = core.yaml.safe_load(text) if core.yaml is not None else {}
    except core.yaml.YAMLError as error:
        raise ValueError(f"invalid Pandoc defaults: {path}") from error
    data = data if isinstance(data, dict) else {}
    chosen = None
    parents = data.get("defaults", [])
    for parent in parents if isinstance(parents, list) else [parents]:
        value = defaults_option(str(parent).replace("${.}", str(path.parent)), directory, command, seen, key)
        if value is not None:
            chosen = value
    if key in data:
        chosen = data[key]
        if isinstance(chosen, str):
            chosen = chosen.replace("${.}", str(path.parent))
    return chosen


def defaults_value(key: str, options: list[str], cwd: Path):
    chosen = None
    for default in option_values(options, "--defaults", "-d"):
        value = defaults_option(default, cwd, options, set(), key)
        if value is not None:
            chosen = value
    return chosen


def custom_template(command: list[str], directory: Path) -> str | None:
    """Command-line template over defaults-file templates, as Pandoc resolves them."""
    explicit = option_values(command, "--template")
    if explicit:
        return explicit[-1]
    chosen = defaults_value("template", command, directory)
    return str(chosen) if chosen is not None else None
