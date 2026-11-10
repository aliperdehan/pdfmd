"""pdfmd's cache by part (v3.33.74): `pdfmd --cache-info` (the size of each part, and what is stale), `pdfmd --clear-cache
WHAT` (builds, documents, stale or all) and the `--doctor` NOTE when the cache is larger than `cache.max-mb`.

The parts are read from what is in `cache_root()`, not from a list:
- `builds/`: the build records (pdfmd_buildinfo), one folder a document, `<stem>-<sha1 of its path, 8>`; each record's
  header names the document (`document:  /abs/path.md`), and the newest record's is the one read;
- `<sha1 of the path, 10>-<stem>/`: a document's own cache (`cache_directory`), which records its document in
  `.pdfmd-source.json` (`path`, written by `write_cache_manifest`);
- every other folder (tex/, office/, raw/, images/, ...) is shared by all documents and listed by its name, and the loose
  files (CACHEDIR.TAG, kits.json, ...) together.
Stale: a document cache or a build-record folder whose recorded document no longer exists. One that records none (an old
folder, a record cut short) is not called stale: it is counted as "unrecorded".

Removal never follows a symbolic link: a link is removed as a link, `shutil.rmtree` does not descend into one, and a path
is removed only when the folder it sits in is the cache folder (or the document's own `.cache/pdfmd` that `all` and a
bare `--clear-cache` clear, as before) or below it. `core` is the `pdfmd` module, bound when this module is first loaded
(pdfmd.py's `deferred` stand-ins).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

core = None

CLEAR_WORDS = ("builds", "documents", "stale", "all")
BUILDS = "builds"
DOCUMENT_FOLDER = re.compile(r"^[0-9a-f]{10}-.")            # cache_directory's `<sha1[:10]>-<stem>`
RECORD_DOCUMENT = re.compile(r"^document:\s+(.+?)\s*$", re.M)
RECORD_NAME = re.compile(r"^\d{8}-\d{6}(?:-\d+)?-(?:ok|failed)\.log$")    # pdfmd_buildinfo.record.NAME
CACHE_MAX_MB = 1000         # `cache.max-mb` when it is not set: the doctor's NOTE above 1 GB (documented in --setup)


def size_text(size: int) -> str:
    """A size people read: B, KB, MB or GB (powers of 1000, as `--doctor`'s cache line)."""
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if size >= scale:
            return f"{size / scale:.1f} {unit}"
    return f"{size} B"


def shown(path: Path) -> str:
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home):] if text == home or text.startswith(home + os.sep) else text


def tree_size(path: Path) -> int:
    """The bytes under `path`, symbolic links counted as links and never followed."""
    try:
        info = os.lstat(path)
    except OSError:
        return 0
    if not stat.S_ISDIR(info.st_mode):
        return info.st_size
    total = 0
    for folder, folders, files in os.walk(path, followlinks=False):
        for name in files + [name for name in folders if os.path.islink(os.path.join(folder, name))]:
            try:
                total += os.lstat(os.path.join(folder, name)).st_size
            except OSError:
                pass
    return total


def document_of_cache(folder: Path) -> Path | None:
    """The document a per-document cache recorded (.pdfmd-source.json), None when it recorded none."""
    try:
        recorded = json.loads((folder / core.CACHE_MANIFEST).read_text(encoding="utf-8")).get("path")
    except (OSError, ValueError, AttributeError):
        return None
    return Path(recorded) if isinstance(recorded, str) and recorded else None


def document_of_records(folder: Path) -> Path | None:
    """The document the newest build record of a `builds/` folder names in its header, None when none does."""
    try:
        records = sorted((path for path in folder.iterdir() if RECORD_NAME.match(path.name) and path.is_file()), reverse=True)
    except OSError:
        return None
    for record in records:
        try:
            with record.open(encoding="utf-8", errors="replace") as handle:
                head = handle.read(4096)
        except OSError:
            continue
        found = RECORD_DOCUMENT.search(head)
        if found:
            return Path(found.group(1))
    return None


def entries(folder: Path) -> list[Path]:
    try:
        return sorted(folder.iterdir())
    except OSError:
        return []


def survey(root: Path) -> dict:
    """What the cache holds: {"documents": [(folder, size, document or None)], "builds": [the same for builds/],
    "shared": [(folder, size)], "files": [(file, size)]}."""
    found: dict = {"documents": [], "builds": [], "shared": [], "files": []}
    for path in entries(root):
        size = tree_size(path)
        if path.is_symlink() or not path.is_dir():
            found["files"].append((path, size))
        elif path.name == BUILDS:
            for folder in entries(path):
                if folder.is_dir() and not folder.is_symlink():
                    found["builds"].append((folder, tree_size(folder), document_of_records(folder)))
                else:
                    found["files"].append((folder, tree_size(folder)))
        elif DOCUMENT_FOLDER.match(path.name):
            found["documents"].append((path, size, document_of_cache(path)))
        else:
            found["shared"].append((path, size))
    return found


def stale(items: list) -> list:
    """The folders whose recorded document is gone."""
    return [(folder, size, document) for folder, size, document in items if document is not None and not document.exists()]


def cache_info(cwd: Path | None = None) -> int:
    """`pdfmd --cache-info`: the cache folder, its size, each part's size, and the stale part."""
    root = core.cache_root()
    if not root.is_dir():
        print(f"pdfmd's cache: {shown(root)} does not exist (nothing cached yet)")
        return 0
    found = survey(root)
    total = sum(item[1] for part in found.values() for item in part)
    print(f"pdfmd's cache: {shown(root)}  {size_text(total)}")
    rows = []
    for key, what, unit in (("documents", "documents/", "document caches"),
                            ("builds", "builds/", "documents' build records")):
        items = found[key]
        if not items:
            continue
        gone = stale(items)
        unrecorded = sum(1 for item in items if item[2] is None)
        detail = f"{len(items)} {unit}"
        if gone:
            detail += f", {len(gone)} stale ({size_text(sum(item[1] for item in gone))})"
        if unrecorded:
            detail += f", {unrecorded} unrecorded"
        rows.append((what if key == "builds" else "<hash>-<name>/", sum(item[1] for item in items), detail))
    for folder, size in sorted(found["shared"], key=lambda item: -item[1]):
        rows.append((folder.name + "/", size, "shared by every document"))
    if found["files"]:
        names = ", ".join(path.name for path, _ in found["files"][:4]) + (", ..." if len(found["files"]) > 4 else "")
        rows.append(("files", sum(size for _, size in found["files"]), names))
    width = max(len(name) for name, _, _ in rows) if rows else 0
    for name, size, detail in rows:
        print(f"  {name:<{width}}  {size_text(size):>9}  {detail}")
    local = (cwd or Path.cwd()) / core.LOCAL_CACHE_DIRNAME
    if local.is_dir() and not local.is_symlink():
        print(f"  and beside the documents here: {shown(local)}  {size_text(tree_size(local))}")
    gone = stale(found["documents"]) + stale(found["builds"])
    if gone:
        print(f"Stale: {len(gone)} folder{'' if len(gone) == 1 else 's'} whose document is gone, "
              f"{size_text(sum(item[1] for item in gone))}: pdfmd --clear-cache stale")
    print("Clear a part: pdfmd --clear-cache builds | documents | stale | all")
    return 0


def inside(path: Path, roots: list[Path]) -> bool:
    """Whether `path` is one of `roots` or lies below one, judged by the real folder it sits in (a link in the path above
    it is resolved, the last part is not)."""
    try:
        parent = Path(os.path.realpath(path.parent))
    except OSError:
        return False
    for root in roots:
        real = Path(os.path.realpath(root))
        if path.name == root.name and parent == Path(os.path.realpath(root.parent)):
            return True                             # the root itself
        if parent == real or real in parent.parents:
            return True
    return False


def remove(path: Path, roots: list[Path]) -> int | None:
    """Remove `path` (a link as a link) when it is inside `roots`; its size, or None when it was not there or not removed."""
    if not os.path.lexists(path):
        print(f"NOTHING  {shown(path)} does not exist")
        return None
    if not inside(path, roots):
        print(f"SKIPPED  {shown(path)} is outside pdfmd's cache", file=sys.stderr)
        return None
    size = tree_size(path)
    try:
        if path.is_symlink() or not path.is_dir():
            path.unlink()
        else:
            shutil.rmtree(path)
    except OSError as error:
        print(f"WARN  {shown(path)} could not be removed whole: {error}", file=sys.stderr)
        return None
    print(f"CLEARED  {shown(path)}  {size_text(size)}")
    return size


def remove_all(paths: list[Path], roots: list[Path]) -> int:
    """Remove each path, with a total line when there were several. The status: 0, or 1 when one could not be removed."""
    removed, status = [], 0
    for path in paths:
        size = remove(path, roots)
        if size is not None:
            removed.append(size)
        elif os.path.lexists(path):
            status = 1
    if len(removed) > 1:
        print(f"CLEARED  {len(removed)} folders, {size_text(sum(removed))}")
    return status


def clear_cache(word: str, cwd: Path | None = None) -> int:
    """`pdfmd --clear-cache WHAT`: builds, documents, stale or all (the cache folder and ./.cache/pdfmd, as before)."""
    root = core.cache_root()
    local = (cwd or Path.cwd()) / core.LOCAL_CACHE_DIRNAME
    if word == "all":
        if root.is_symlink():
            print(f"SKIPPED  {shown(root)} is a symbolic link: pdfmd does not clear what it points at; "
                  "remove the link, or clear the parts: pdfmd --clear-cache documents", file=sys.stderr)
            remove_all([local], [local])
            return 1
        return remove_all([root, local], [root, local])
    if not root.is_dir():
        print(f"NOTHING  {shown(root)} does not exist")
        return 0
    found = survey(root)
    if word == "builds":
        targets = [root / BUILDS]
    elif word == "documents":
        targets = [folder for folder, _, _ in found["documents"]]
    else:
        targets = [folder for folder, _, _ in stale(found["documents"]) + stale(found["builds"])]
    if not targets:
        print(f"NOTHING  no {'stale folders' if word == 'stale' else 'document caches'} in {shown(root)}")
        return 0
    return remove_all(targets, [root])


def cache_command(args) -> int | None:
    """`--cache-info` and `--clear-cache WHAT`. A `--clear-cache` value that is not one of the words is a document (`pdfmd
    --clear-cache doc.md`): it is put back among the paths and the bare --clear-cache runs as before (None)."""
    value = args.clear_cache
    if isinstance(value, str) and value not in CLEAR_WORDS:
        args.path = [Path(value), *args.path]
        args.clear_cache = True
        value = True
    if args.cache_info and value:
        raise SystemExit("--cache-info only shows the cache; clear it in a run of its own: pdfmd --clear-cache WHAT")
    if args.cache_info:
        if args.path:
            raise SystemExit("--cache-info takes no document: it shows the whole cache")
        return cache_info()
    if isinstance(value, str):
        if args.path:
            raise SystemExit(f"--clear-cache {value} is for the whole cache and takes no document; "
                             "pdfmd --clear-cache DOC clears one document's cache")
        return clear_cache(value)
    return None


def max_megabytes() -> float | None:
    """`cache.max-mb` of the config file (the doctor reads no document): a number of MB, 0 or less for no NOTE."""
    nested = core.config_options().get("cache")
    value = nested.get("max-mb") if isinstance(nested, dict) else None
    number = core.option_flag_number(value)
    if value is None or number is None:
        return float(CACHE_MAX_MB)
    return number if number > 0 else None


def size_note(size: int) -> str | None:
    """The doctor's NOTE when the cache is larger than `cache.max-mb`, else None."""
    limit = max_megabytes()
    if limit is None or size <= limit * 1e6:
        return None
    return (f"the cache is {size_text(size)}, more than cache.max-mb ({limit:g} MB): pdfmd --cache-info shows its parts, "
            "pdfmd --clear-cache stale (or builds, documents, all) clears them")
