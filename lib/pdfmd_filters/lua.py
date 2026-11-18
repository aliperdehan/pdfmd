"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_filters.lua`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import hashlib
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

from pdfmd_base import core


def package_lua_names(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None = None) -> list[str]:
    """The Lua filters a document's LaTeX packages bring: `<package>.lua` for each local package its preamble loads, and what
    the package's `<package>-pdfmd.yaml` lists under `lua:` (v3.28.37; before, one package's name was written in pdfmd)."""
    names: list[str] = []
    for folder, package, _ in core.office_packages(md_path, metadata_files, None):
        listed = [f"{package}.lua"]
        helper = core.package_helper(folder, package, no_auto, md_path)
        extra = helper[0].get("lua") if helper else None
        listed += [str(item) for item in ([extra] if isinstance(extra, str) else extra if isinstance(extra, list) else [])]
        names += [name for name in listed if name not in names and "/" not in name and "\\" not in name]
    return names


def find_lua_filters(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None = None) -> list[Path]:
    """Find Pandoc Lua filters that belong to a document, without guessing.

    Only these names are auto-applied: a filter matching the document's own stem
    (report.md -> report.lua) and the Lua filters of the LaTeX packages it loads
    (package_lua_names: `<package>.lua`), beside the document or its metadata. Anything
    else has to be passed explicitly, so an unrelated .lua file sitting in a folder can
    never silently change a render.
    """
    directories: list[Path] = core.accessory_directories(md_path.parent, md_path.stem)
    directories += [metadata.parent for metadata in metadata_files]
    wanted = (f"{md_path.stem}.lua", *package_lua_names(md_path, metadata_files, no_auto))
    found: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        for name in wanted:
            candidate = (directory / name).resolve()
            if candidate.is_file() and candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
    for item in core.active_kits(md_path, metadata_files, None):         # the Lua filters a chosen kit names
        for candidate in (path.resolve() for path in item.kit.lua):
            if candidate.is_file() and candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
    unpacked = md_path.parent / f"{md_path.stem}{core.UNPACKED_SUFFIX}"
    if unpacked.is_dir():
        for candidate in sorted(unpacked.glob("*.lua"), key=lambda item: core.natural_key(item.name)):
            if candidate.resolve() not in seen:
                seen.add(candidate.resolve())
                found.append(candidate.resolve())
    return found


# A Lua filter can run any command, and pdfmd runs `<name>.lua` and a loaded package's `<package>.lua` beside a document (and the files
# a document names in `pdfmd-options.lua-filter`) without being asked. So the first build with a filter pdfmd has not run
# before prints a NOTE, and so does the first build after the file changed (path and SHA-256 are kept in
# ~/.config/pdfmd/known-lua.txt); the filter still runs, so a filter you edit every day never gets in the way, and
# there is never a prompt (CI, `-j`, `-w` and the Python API have no one to ask). `pdfmd --trust-lua FOLDER` marks a
# folder you work in: nothing in it is noted again. Only `--strict` skips a new or edited filter outside such a folder
# (with a WARN). This does not protect the FIRST run of a folder you have just downloaded: read its .lua first.
def lua_known_path() -> Path:
    return core.config_root() / "known-lua.txt"


def lua_folders_path() -> Path:
    return core.config_root() / "trusted-lua-folders.txt"


def lua_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def known_lua() -> dict[str, str]:
    """{resolved path: SHA-256 it last ran with}; a later line for a path replaces an earlier one."""
    known: dict[str, str] = {}
    try:
        for line in lua_known_path().read_text(encoding="utf-8").splitlines():
            digest, _, name = line.strip().partition(" ")
            if digest and name:
                known[name] = digest
    except OSError:
        pass
    return known


def remember_lua(entries: list[tuple[str, str]]) -> None:
    if not entries:
        return
    try:
        lua_known_path().parent.mkdir(parents=True, exist_ok=True)
        with lua_known_path().open("a", encoding="utf-8") as handle:
            for digest, name in entries:
                handle.write(f"{digest} {name}\n")
    except OSError:
        pass


def trusted_lua_folders() -> list[Path]:
    try:
        return [Path(line.strip()) for line in lua_folders_path().read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")]
    except OSError:
        return []


def check_lua_filters(md_path: Path, filters: list[Path], strict: bool) -> list[Path]:
    """The filters that run: all of them, with a NOTE for each one new here or edited since it last ran; with
    ``strict`` a new or edited one outside a trusted folder is skipped, with a WARN."""
    if not filters:
        return filters
    known, folders = known_lua(), trusted_lua_folders()
    keep: list[Path] = []
    fresh: list[tuple[str, str]] = []
    for path in filters:
        key = str(path.resolve())
        digest = lua_digest(path)
        if digest is None or known.get(key) == digest or any(path.resolve().is_relative_to(folder) for folder in folders):
            keep.append(path)
            continue
        what = "is new here" if key not in known else "has changed since it last ran here"
        advice = ("A Lua filter can run any command: read it, or mark a folder you work in with "
                  "`pdfmd --trust-lua FOLDER` to stop this note")
        if strict:
            print(f"WARN  {core.display_path(md_path)}: the Lua filter {path.name} {what} and was not run (--strict). {advice}",
                  file=sys.stderr)
            continue
        print(f"NOTE  {core.display_path(md_path)}: the Lua filter {path.name} {what}; it runs. {advice}")
        keep.append(path)
        fresh.append((digest, key))
    remember_lua(fresh)
    return keep


def trust_lua(paths: list[Path]) -> bool:
    """--trust-lua PATH...: a folder is trusted for good, a file as it is now. True when every path was found."""
    complete = True
    for path in paths:
        path = path.expanduser().resolve()
        if path.is_dir():
            if path not in trusted_lua_folders():
                lua_folders_path().parent.mkdir(parents=True, exist_ok=True)
                with lua_folders_path().open("a", encoding="utf-8") as handle:
                    handle.write(f"{path}\n")
            print(f"OK    Lua filters under {core.display_path(path)} run without a note")
        elif path.is_file() and lua_digest(path):
            remember_lua([(lua_digest(path), str(path))])
            print(f"OK    {core.display_path(path)} is trusted as it is now (an edit is noted again; trust its folder to stop that)")
        else:
            print(f"FAIL  {core.display_path(path)}: no such file or folder", file=sys.stderr)
            complete = False
    return complete


PDFMD_LUA_WARNED: set[str] = set()


def pdfmd_lua_missing(name: str = "") -> None:
    """One WARN per run: pdfmd's own Lua filters (the package pdfmd_lua, or one file of it) are not there, so what they do is
    skipped. A lone copy of pdfmd.py has no pdfmd_lua; so does a checkout with the folder deleted."""
    key = name or "package"
    if key in PDFMD_LUA_WARNED:
        return
    PDFMD_LUA_WARNED.add(key)
    what = (f"pdfmd_lua/{name}.lua is missing from the pdfmd_lua package" if name
            else "the pdfmd_lua package is not installed beside pdfmd.py")
    print(f"WARN  lua: {what}, so pdfmd's own Lua filters do nothing in this run (tables sized by content, CSV tables, "
          "calculations, indents, page breaks, markup ...). Install pdfmd-cli (`pipx install pdfmd-cli`) or keep the pdfmd_* "
          "folders of the repository beside pdfmd.py", file=sys.stderr)


class _NoFigureFit:
    """Figure fit (v3.34.4) when pdfmd_lua is missing: no filter for Pandoc (one WARN, as for every other own filter), so
    no engine diagnostics to read and the engine's output stays as it is."""
    REPORT_ENV = "PDFMD_FIGURE_REPORT"

    @staticmethod
    def arguments(writer: str, source: Path, metadata: list[Path]) -> list[str]:
        core.pdfmd_lua_missing()
        return []

    @staticmethod
    def diagnostics(output: str, source: Path) -> None:
        return None

    @staticmethod
    def without_diagnostics(output: str) -> str:
        return output


def figure_fit_module():
    """pdfmd_lua.figure_fit, or a stand-in that does nothing when the package is not there (pdfmd.py
    with its lib/ folder but no lib/pdfmd_lua: a deleted folder, or a repackaging that dropped it)."""
    try:
        from pdfmd_lua import figure_fit
    except ImportError:
        return _NoFigureFit
    return figure_fit


@contextmanager
def lua_filter_file(name: str, prefix: str) -> Iterator[Path]:
    """The path of pdfmd's own Lua filter `name` (pdfmd_lua/NAME.lua) for --lua-filter.

    Without the pdfmd_lua package (a lone copy of this script), or without that file, a filter that does nothing is
    written to a temporary file instead, so the callers need no special case -- and one WARN per run says that the filters
    are missing (pdfmd_lua_missing).
    """
    shipped = None
    try:
        import pdfmd_lua
        shipped = pdfmd_lua.path(name)
    except ImportError:
        pdfmd_lua_missing()
    else:
        if shipped is None:
            pdfmd_lua_missing(name)
    if shipped is not None:
        yield shipped
        return
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".lua", prefix=prefix, delete=False) as temporary:
        temporary.write("return {}\n")
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)
