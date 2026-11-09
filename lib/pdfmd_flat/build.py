"""The build side of flat Markdown and ASCII text (`--to gfm`, `--to txt`, `--to ascii`): the settings, the Pandoc writer, the
filter arguments, the target's name and the finishing step that maps what the writer made itself.

Moved out of `pdfmd.py` unchanged (v3.33.8, SPLIT.md), with `_PANDOC_EXTENSIONS`. `core` is the `pdfmd` module, bound when the module
is first loaded (the first binding wins); the pdfmd names the code uses (`GFM_CLI`, `ASCII_CLI`, `ASCII_FORMATS`, `cache_root`
and `run_probe`, which tests patch, and the rest) are read as `core.X` when it runs. `ascii_filter_args` names the script that
the Lua filter's helper process runs by `core.__file__` (`pdfmd.py`), not by this module's own file. The package's own parts
(`pdfmd_flat`, `pdfmd_flat.asciify`) and `pdfmd_lua` are imported inside the functions, as they were.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

core = None

_PANDOC_EXTENSIONS: dict[str, frozenset[str]] = {}


def pandoc_extensions(name: str) -> frozenset[str]:
    """The extensions this Pandoc knows for format `name` (on or off), for building a writer string it will accept."""
    if name not in _PANDOC_EXTENSIONS:
        done = core.run_probe(["pandoc", f"--list-extensions={name}"])
        listing = done.stdout if done else ""
        _PANDOC_EXTENSIONS[name] = frozenset(line.strip().lstrip("+-") for line in listing.splitlines() if line.strip())
    return _PANDOC_EXTENSIONS[name]


def flat_settings(md_path: Path, metadata_files: list[Path], target: str = "gfm") -> dict:
    try:
        import pdfmd_flat
    except ImportError:
        raise SystemExit(f"--to {target} needs the pdfmd_flat package (install pdfmd-cli; a lone copy of pdfmd.py has "
                         f"only Pandoc's own writer: --to {'plain' if target == 'txt' else 'gfm+raw'})")
    try:
        chosen = pdfmd_flat.settings(core.cascaded_option(md_path, metadata_files, target), target=target, **core.GFM_CLI)
    except pdfmd_flat.FlatError as error:
        raise SystemExit(f"{core.display_path(md_path)}: {error}")
    if core.ASCII_CLI["on"] and chosen["scripts"] != "drop":       # --to ascii: H_2O, x^2 (`drop` is a choice of its own)
        chosen["scripts"] = "ascii"
    return chosen


def flat_writer(target_format: str, settings: dict | None) -> str:
    """The Pandoc writer of a target: the flat writer for `gfm`, plain `gfm` for `gfm+raw`, `plain` for `txt`, else the
    target itself."""
    try:
        import pdfmd_flat
    except ImportError:
        return {"gfm+raw": "gfm", "txt": "plain"}.get(target_format, target_format)
    if not pdfmd_flat.is_family(target_format):
        return target_format
    return pdfmd_flat.writer(target_format, (settings or pdfmd_flat.DEFAULTS)["math"], pandoc_extensions("gfm"))


def flat_filter_args(settings: dict, target: str = "gfm") -> list[str]:
    """The arguments that make a build flat: its settings (a metadata file) and pdfmd_lua/flat.lua, which must be last."""
    try:
        import pdfmd_lua
        filter_path = pdfmd_lua.path("flat")
    except ImportError:
        filter_path = None
    if filter_path is None:
        raise SystemExit(f"--to {target} needs pdfmd_lua/flat.lua (install pdfmd-cli; a lone copy of pdfmd.py has only "
                         f"Pandoc's own writer: --to {'plain' if target == 'txt' else 'gfm+raw'})")
    config = {"pdfmd-flat": {"scripts": settings["scripts"], "title": bool(settings["title"]), "target": target}}
    digest = hashlib.sha1(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    map_file = core.cache_root() / "flat" / f"{digest}.yaml"
    if not map_file.is_file():
        map_file.parent.mkdir(parents=True, exist_ok=True)
        map_file.write_text(json.dumps(config) + "\n", encoding="utf-8")
    return ["--metadata-file", str(map_file), "--lua-filter", str(filter_path)]


def split_ascii_target(name: str) -> tuple[str, bool]:
    """(the format, True) for `ascii` and `ascii:FORMAT`; (name, False) for any other target."""
    lowered = name.strip().casefold()
    if lowered != "ascii" and not lowered.startswith("ascii:"):
        return name, False
    base = lowered.partition(":")[2].strip().lstrip(".") or "txt"
    base = core.DEFAULT_OUTPUT_ALIASES.get(base, base)
    if base not in core.ASCII_FORMATS:
        raise SystemExit(f"--to {name}: ASCII applies to text formats ({', '.join(sorted(core.ASCII_FORMATS))}); "
                         f"{base} is not one of them")
    return base, True


def ascii_missing(md_path: Path, metadata_files: list[Path]) -> str:
    """What a character with no ASCII form becomes: --ascii-missing, else `pdfmd-options.ascii.missing`, else `question`."""
    option = core.cascaded_option(md_path, metadata_files, "ascii")
    value = core.ASCII_CLI["missing"] or (option.get("missing") if isinstance(option, dict) else None) or "question"
    value = str(value).strip().casefold()
    if value not in ("question", "escape", "drop", "fail"):
        raise SystemExit(f"{core.display_path(md_path)}: ascii missing {value!r}: choose one of question, escape, drop, fail")
    return value


def ascii_filter_args(scratch: Path, missing: str, smart: bool = False) -> list[str]:
    """The arguments that add pdfmd_lua/ascii.lua, which must run after every other filter."""
    try:
        import pdfmd_lua
        filter_path = pdfmd_lua.path("ascii")
        import pdfmd_flat.asciify  # noqa: F401 -- the helper process needs it; fail here, not in the middle of a build
    except ImportError:
        filter_path = None
    if filter_path is None:
        raise SystemExit("--to ascii needs pdfmd_lua/ascii.lua and pdfmd_flat (install pdfmd-cli; a lone copy of "
                         "pdfmd.py cannot make ASCII text)")
    config = {"pdfmd-ascii": {"command": Path(sys.executable).as_posix(), "script": Path(core.__file__).resolve().as_posix(),
                              "missing": missing, "report": (scratch / "report.json").as_posix(), "smart": "keep" if smart else "all"}}
    map_file = scratch / "ascii.yaml"
    map_file.write_text(json.dumps(config) + "\n", encoding="utf-8")
    return ["--metadata-file", str(map_file), "--lua-filter", str(filter_path)]


def ascii_finish(output: Path, scratch: Path, missing: str, md_path: Path) -> str | None:
    """After the build: map what the writer made itself (math in the plain writer, say), count the characters that
    have no ASCII form, and say so; with `fail` the output is removed and the reason returned (the file failed, and
    a batch goes on with the next)."""
    import pdfmd_flat.asciify as asciify
    lost: dict[str, int] = {}
    try:
        lost = json.loads((scratch / "report.json").read_text(encoding="utf-8")).get("lost", {})
    except (OSError, ValueError):
        pass
    if output.is_file():
        data = output.read_bytes()
        if not data.isascii():
            asciifier = asciify.Asciifier(missing)
            core.atomic_write_bytes(output, asciifier.text(data.decode("utf-8")).encode("ascii"))
            lost = asciify.merge(lost, asciifier.lost)
    if not lost:
        return None
    count = sum(lost.values())
    shown = asciify.describe(lost)
    if missing == "fail":
        output.unlink(missing_ok=True)
        return (f"{core.display_path(md_path)}: {count} character{'s' if count != 1 else ''} with no ASCII form "
                f"({shown}); nothing was written. --ascii-missing question|escape|drop writes the file anyway; "
                "`pdfmd --install translit` adds the scripts it can spell")
    written = {"question": "?", "escape": "a \\u escape", "drop": "nothing"}[missing]
    print(f"WARN  ascii: {core.display_path(md_path)}: {count} character{'s' if count != 1 else ''} with no ASCII form "
          f"({shown}) {'was' if count == 1 else 'were'} written as {written}; `pdfmd --install translit` adds the "
          "scripts it can spell, --ascii-missing escape|drop|fail changes this", file=sys.stderr)
    return None
