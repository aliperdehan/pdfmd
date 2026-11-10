"""pdfmd's cache folders: the user's cache (`cache_root`), the folder a document's cache goes in, `global` or beside the document
(`cache_location`, `document_cache_root`, from `--cache-location` or `pdfmd-options: {cache: {location: ...}}`), one folder per
document (`cache_directory`), found again when the document was moved (`adopt_moved_cache`, by `source_fingerprint`), and the
temporary folders a run uses in place of one that cannot be written (`folder_is_writable`, `temporary_place`, `TEMPORARY_PLACES`).

Moved out of `pdfmd.py` unchanged (v3.33.33, SPLIT.md), with `CACHE_LOCATION_NAMES` and `TEMPORARY_PLACES`. `core` is the `pdfmd`
module, bound by `pdfmd.py` when it loads (the first binding wins); the pdfmd names the code uses (`CACHE_LOCATIONS`,
`CACHE_LOCATION_CLI`, `CACHE_MANIFEST`, `LOCAL_CACHE_DIRNAME`, `config_options`, `frontmatter_pdfmd_options`, `metadata_file_yaml`,
`metadata_files_by_priority` and `write_cache_manifest`) are read as `core.X` when it runs, so `CACHE_LOCATION_CLI`, which `main`
rebinds, is always the current one. `cache_root` is patched by tests as `pdfmd.cache_root`, so `document_cache_root` and
`cache_directory` call it as `core.cache_root()`; `core.config_options` is patched by tests as well.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp

core = None


def cache_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "pdfmd"


TEMPORARY_PLACES: dict[str, Path] = {}


def folder_is_writable(path: Path) -> bool:
    """Whether a file can be created in ``path`` -- or, when it is not there yet, in the nearest folder above it that is."""
    folder = Path(path)
    try:
        while not folder.exists():
            if folder.parent == folder:
                return False
            folder = folder.parent
        return folder.is_dir() and os.access(folder, os.W_OK | os.X_OK)
    except OSError:
        return False


def temporary_place(kind: str) -> Path:
    """A folder for ``kind`` of this run only, made once and removed when the run ends."""
    if kind not in TEMPORARY_PLACES:
        folder = Path(mkdtemp(prefix=f"pdfmd-{kind}-"))
        TEMPORARY_PLACES[kind] = folder
        atexit.register(shutil.rmtree, folder, True)
    return TEMPORARY_PLACES[kind]


CACHE_LOCATION_NAMES = {"root": "global", "user": "global", "home": "global", "central": "global",
                        "local": "document", "folder": "document", "here": "document", "doc": "document",
                        "self-contained": "document"}


def location_setting(md_path: Path, metadata_files: list[Path]) -> tuple[object, str] | None:
    """The cache location asked for and the setting that asks (`--cache-location`, `pdfmd-options.cache.location` or
    `pdfmd-options.cache-location`): the command line, else the document, its metadata files and the config file, the
    first that says. None when none does."""
    if core.CACHE_LOCATION_CLI is not None:
        return core.CACHE_LOCATION_CLI, "--cache-location"
    sources = [core.frontmatter_pdfmd_options(md_path)]
    for metadata_file in core.metadata_files_by_priority(metadata_files):
        found = core.metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append(found if isinstance(found, dict) else {})
    sources.append(core.config_options(md_path))
    for options in sources:
        nested = options.get("cache")
        value = nested.get("location") if isinstance(nested, dict) else None
        if value:                                       # an empty one gives way to `cache-location:`, as before
            return value, "pdfmd-options.cache.location"
        if options.get("cache-location") is not None:
            return options["cache-location"], "pdfmd-options.cache-location"
    return None


def location_word(value) -> str:
    text = str(value).strip().casefold()
    return CACHE_LOCATION_NAMES.get(text, text)


def cache_location(md_path: Path, metadata_files: list[Path]) -> str:
    """Where this document's cache lives: `global` (cache_root(): ~/.cache/pdfmd) or `document` (a
    `.cache/pdfmd` folder beside it, so the folder carries its cache wherever it is moved). The command
    line, else `pdfmd-options: {cache: {location: ...}}` (or `cache-location:`) of the document, its
    metadata files and the config file, else global."""
    found = location_setting(md_path, metadata_files)
    if found is None:
        return "global"
    value = found[0]
    text = location_word(value)
    if text not in core.CACHE_LOCATIONS:
        raise SystemExit(f"{md_path}: cache location {value!r} is not one of {', '.join(core.CACHE_LOCATIONS)}")
    return text


def check_location(md_path: Path, metadata_files: list[Path], cli: bool | None) -> None:
    """An unknown cache location (`location: moon`) stops a build when the cache is used (cache_location, v3.23.12); with
    the cache off nothing reads it, and it passed in silence. Now a WARN, once a build (convert_one calls this), naming the
    setting, the value and the words it takes (v3.33.61)."""
    if md_path.suffix.lower() not in (".md", ".markdown"):
        return
    try:
        found = location_setting(md_path, metadata_files)
    except OSError:
        return
    if found is None or location_word(found[0]) in core.CACHE_LOCATIONS:
        return
    settings = core.cache_settings(md_path, metadata_files, cli)
    if any(settings.values()):
        return                                                  # used: cache_location stops the build there
    print(f"WARN  {md_path}: {found[1]} {found[0]!r} is not one of {', '.join(core.CACHE_LOCATIONS)}; "
          "the cache is off, so nothing uses it", file=sys.stderr)


def document_cache_root(md_path: Path, metadata_files: list[Path]) -> Path:
    """The folder this document's cache entries go in (made, with its CACHEDIR.TAG, when first used)."""
    if cache_location(md_path, metadata_files) == "global":
        return core.cache_root()
    return md_path.resolve().parent / core.LOCAL_CACHE_DIRNAME


def source_fingerprint(source: Path) -> str | None:
    try:
        return hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError:
        return None


def adopt_moved_cache(source: Path, target: Path, root: Path, note=None) -> bool:
    """A document moved to another folder (a lab report from Downloads into OneDrive) has no cache
    under its new path. Find the folder of the same document by what it recorded: a cache whose
    original no longer exists, with the same stem and the same content (SHA-256), or else the same
    stem and the same folder name when only one such cache is left. The folder is renamed to this
    document's, so the cross-reference files carry on. A copy (the original still there) never
    takes the original's cache."""
    import json
    here = str(source.resolve())
    fingerprint = source_fingerprint(source)
    exact, by_name = [], []
    for candidate in root.glob(f"*-{source.stem}"):
        try:
            manifest = json.loads((candidate / core.CACHE_MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (candidate == target or manifest.get("stem") != source.stem or manifest.get("path") == here
                or Path(str(manifest.get("path", ""))).exists()):
            continue
        if fingerprint and manifest.get("sha256") == fingerprint:
            exact.append(candidate)
        elif manifest.get("folder") == source.resolve().parent.name:
            by_name.append(candidate)
    chosen = exact[0] if len(exact) >= 1 else (by_name[0] if len(by_name) == 1 else None)
    if chosen is None:
        return False
    try:
        chosen.rename(target)
    except OSError:
        return False
    core.write_cache_manifest(target, source)
    if note:
        note("CACHE", f"{source}: the cache of the document it was moved from is reused")
    return True


def cache_directory(source: Path, root: Path | None = None, note=None) -> Path:
    """One folder per document. In the global cache it is keyed by the document's absolute path (two
    reports both called report.md must not share an .aux), and a moved document finds its folder again
    by what the folder recorded; in a document's own `.cache/pdfmd` the stem is enough."""
    root = root or core.cache_root()
    if root != core.cache_root():
        return root / source.stem
    digest = hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:10]
    target = root / f"{digest}-{source.stem}"
    if not target.exists() and root.is_dir():
        adopt_moved_cache(source, target, root, note)
    return target
