"""Finding a kit by name, and remembering where it was.

A *location* is a folder that either is a kit (it holds `.kit`, or `NAME.kit`) or holds kit folders one level down. The
search goes through the locations in the order given: the first location with a match wins. Two different kits that answer
to one name WITHIN one location stop the search (nothing is guessed between them); across locations the order decides, and
the caller can print the winner. A name matches the folder's name, the `NAME.kit` file's name or the `name:` the file
declares, compared with `normalise` (case, `-` `_` `.` and spaces ignored).

After the locations come two steps that cost a process or a file read: a *lookup* (the folder of `NAME.sty` that kpsewhich
finds, handed in by the caller) and the *cache*, which remembers only where a kit was found: name -> the `.kit`'s path, its
size and its modification time. A hit is trusted only while that file still has that size and time; an unreadable or
corrupt cache is a miss; a miss is never written. The cache is read before the lookup and written after it.
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


def _declared_name(path: Path) -> str | None:
    try:
        import yaml
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

    def put(self, wanted: str, path: Path) -> None:
        if self.path is None:
            return
        try:
            seen = path.stat()
            entries = dict(self._load())
            entries[wanted] = {"path": str(path), "size": seen.st_size, "mtime_ns": seen.st_mtime_ns}
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
        path = cache.get(wanted)
        if path is not None:
            return Found(path, "the TeX tree", cached=True)
    if lookup is not None:
        for spelling in dict.fromkeys((name, wanted)):
            folder = lookup(spelling)
            if folder is not None:
                path = next(iter(kit_files(Path(folder))), None)
                if path is not None:
                    if cache is not None:
                        cache.put(wanted, path)
                    return Found(path, "the TeX tree")
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
            path = cache.get(wanted)
            if path is not None:
                add(Found(path, "the TeX tree", cached=True))
    return found
