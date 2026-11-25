"""Finding a kit by name, and remembering where it was.

A *location* is a folder that either is a kit (it holds `.kit`, or `NAME.kit`) or holds kit folders one level down. The
search goes through the locations in the order given: the first location with a match wins. Two different kits that answer
to one name WITHIN one location stop the search (nothing is guessed between them); across locations the order decides, and
the caller can print the winner. A name matches the folder's name, the `NAME.kit` file's name or the `name:` the file
declares, compared with `normalise` (case, `-` `_` `.` and spaces ignored).

After the locations come the cache and the TeX lookup (the folder of `NAME.sty` that kpsewhich finds, handed in by the
caller). The cache remembers the kit's path, size, modification time and package folder. A hit rechecks the package's
kit locations while the recorded file has the same size and time. A miss is never written.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .kitfile import FILE, SUFFIX, KitError, normalise

CACHE_FORMAT = 1


@dataclass(frozen=True)
class Location:
    source: str                  # said to the user: "project kits/", "kits: in the config" ...
    folder: Path
    aliases: dict = field(default_factory=dict, hash=False, compare=False)   # {mode: [alias, ...]} a `kits:` entry added


@dataclass(frozen=True)
class Found:
    path: Path                   # the `.kit` file
    source: str
    cached: bool = False
    aliases: dict = field(default_factory=dict, hash=False, compare=False)
    package_folder: Path | None = None
    shadowed: tuple[Path, ...] = ()

    @property
    def folder(self) -> Path:
        return self.path.parent


def kit_files(folder: Path, wanted: str | None = None) -> list[Path]:
    """The kit file(s) of ``folder``: `.kit` if it is there, else the `*.kit` files (those answering to ``wanted`` if given)."""
    try:
        if (folder / FILE).is_file():
            return [folder / FILE]
        named = sorted(item for item in folder.iterdir() if item.suffix == SUFFIX and item.stem and item.is_file())
    except OSError:
        return []
    if wanted is None:
        return named
    return [item for item in named if normalise(item.stem) == wanted]


def package_kit_places(folder: Path) -> tuple[Path, ...]:
    """The kit folders of a LaTeX package, starting at the folder of its style file."""
    return folder, folder / "pdfmd", folder / ".pdfmd"


def package_kit_files(folder: Path) -> list[Path]:
    """The first kit file in each place, in precedence order."""
    return [files[0] for place in package_kit_places(folder) if (files := kit_files(place))]


def _declared_name(path: Path) -> str | None:
    try:
        from pdfmd_yaml_support import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except Exception:       # a kit that cannot be read is reported when it is loaded, not here
        return None
    return str(data["name"]) if isinstance(data, dict) and isinstance(data.get("name"), (str, int, float)) else None


def _answers(path: Path, wanted: str) -> bool:
    """Whether the kit file ``path`` is called ``wanted`` (a normalised name)."""
    if normalise(path.parent.name) == wanted or (path.name != FILE and normalise(path.stem) == wanted):
        return True
    declared = _declared_name(path)
    return declared is not None and normalise(declared) == wanted


def _candidates(folder: Path) -> list[Path]:
    """Every kit file of a location: the folder's own, else those of its sub-folders (one level)."""
    own = kit_files(folder)
    if own:
        return own
    found: list[Path] = []
    try:
        children = sorted(item for item in folder.iterdir() if item.is_dir() and not item.name.startswith("."))
    except OSError:
        return []
    for child in children:
        found += kit_files(child)
    return found


def _in_location(location: Location, wanted: str) -> Path | None:
    matches: dict[Path, Path] = {}
    for path in _candidates(location.folder):
        if _answers(path, wanted):
            try:
                matches.setdefault(path.resolve(), path)
            except OSError:
                matches.setdefault(path, path)
    if len(matches) > 1:
        raise KitError([f"two kits in {location.source} ({location.folder}) answer to `{wanted}`:"
                        + "".join(f"\n  {path}" for path in matches.values())
                        + "\nrename one folder or its `name:`; pdfmd will not choose between them"])
    return next(iter(matches.values()), None)


class Cache:
    """name -> where its `.kit` was found. ``path`` is the JSON file (None: no cache at all)."""

    def __init__(self, path: Path | None):
        self.path = path
        self._entries: dict | None = None

    def _load(self) -> dict:
        if self._entries is None:
            self._entries = {}
            try:
                data = json.loads(self.path.read_text(encoding="utf-8")) if self.path else None
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict) and data.get("format") == CACHE_FORMAT and isinstance(data.get("kits"), dict):
                self._entries = {key: value for key, value in data["kits"].items() if isinstance(value, dict)}
        return self._entries

    def get(self, wanted: str) -> Path | None:
        entry = self._load().get(wanted)
        if not entry:
            return None
        try:
            path = Path(entry["path"])
            seen = path.stat()
            if seen.st_size == entry["size"] and seen.st_mtime_ns == entry["mtime_ns"]:
                return path
        except (OSError, KeyError, TypeError, ValueError):
            pass
        return None

    def found(self, wanted: str) -> Found | None:
        path = self.get(wanted)
        if path is None:
            return None
        # Before packages could put kits in subfolders, the kit's parent was the package folder.
        folder = self._load()[wanted].get("package_folder")
        folder = Path(folder) if isinstance(folder, str) else path.parent
        files = package_kit_files(folder)
        if files:
            return Found(files[0], "the TeX tree", cached=True, package_folder=folder, shadowed=tuple(files[1:]))
        return None

    def put(self, wanted: str, path: Path, package_folder: Path | None = None) -> None:
        if self.path is None:
            return
        try:
            seen = path.stat()
            entries = dict(self._load())
            entries[wanted] = {"path": str(path), "size": seen.st_size, "mtime_ns": seen.st_mtime_ns}
            if package_folder is not None:
                entries[wanted]["package_folder"] = str(package_folder)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    json.dump({"format": CACHE_FORMAT, "kits": entries}, stream, indent=1, sort_keys=True)
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            self._entries = entries
        except OSError:
            pass            # a cache that cannot be written only costs the next search


def find(name: str, locations: list[Location], lookup=None, cache: Cache | None = None) -> Found | None:
    """Where the kit called ``name`` is, or None. ``lookup(name)`` may give the folder of its `.sty` (the TeX tree); it runs
    only when the locations and the cache have nothing."""
    wanted = normalise(name)
    if not wanted:
        return None
    for location in locations:
        path = _in_location(location, wanted)
        if path is not None:
            return Found(path, location.source, aliases=location.aliases)
    if cache is not None:
        found = cache.found(wanted)
        if found is not None:
            return found
    if lookup is not None:
        for spelling in dict.fromkeys((name, wanted)):
            located = lookup(spelling)
            if located is None:
                continue
            folder = Path(located)
            if files := package_kit_files(folder):
                if cache is not None:
                    cache.put(wanted, files[0], folder)
                return Found(files[0], "the TeX tree", package_folder=folder, shadowed=tuple(files[1:]))
    return None


def list_kits(locations: list[Location], cache: Cache | None = None) -> list[Found]:
    """Every kit the locations hold, in order, then the ones the cache remembers that they do not (each once)."""
    found: list[Found] = []
    seen: set[Path] = set()

    def add(item: Found) -> None:
        try:
            key = item.path.resolve()
        except OSError:
            key = item.path
        if key not in seen:
            seen.add(key)
            found.append(item)

    for location in locations:
        for path in _candidates(location.folder):
            add(Found(path, location.source, aliases=location.aliases))
    if cache is not None:
        for wanted in sorted(cache._load()):
            item = cache.found(wanted)
            if item is not None:
                add(item)
    return found
