"""The test run's own cache, config and data folders, and the check at the end that pdfmd's real ones were left alone.

pdfmd keeps its build records and caches in XDG_CACHE_HOME (%LOCALAPPDATA% on Windows), its settings in XDG_CONFIG_HOME (%APPDATA%)
and the tools it installs in XDG_DATA_HOME (%LOCALAPPDATA%). A test that runs pdfmd without naming them writes into the machine's
own: runs of a few modules (which do not import test_00_environment) once left about 1,660 build records in a real cache. So every
test module imports this one before anything else (test_isolation checks that it does), whatever runs it: `discover -s tests`,
`discover -s tests -p test_x.py`, `-m unittest tests.test_x` from the root, `-m unittest test_x` from tests/. The first import points
the five variables at one temporary folder for the whole process; the pdfmd processes the tests start inherit them. A test that
needs a folder of its own still names one (cache_support.cache_env, env_support.config_env).

At the end of the process it compares pdfmd's real folders with what they held at the start and, when something appeared or
changed there, names it and ends the process with status 1. A build of a document outside the tests in the meantime (one in
another terminal) changes the cache too: what names such a document (a build record, a document's cache folder) is listed apart
and not counted, and so is what names no document then, as it may be that build's.

The tools pdfmd installs (`pdfmd --install`, in the real data folder) are not seen by the tests: a test that needs one skips.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

MARK = "PDFMD_TESTS_SCRATCH"                  # set by the first import: a second copy of this module, or a test's own child, does nothing
SHOWN = 20                                    # how many of the paths that changed the message lists
REAL: list[Path] = []                         # the real folders this process watches (none in a second copy)


def real_folders() -> list[Path]:
    """pdfmd's cache, config and data folders as the environment the run started with names them."""
    home = Path.home()

    def base(variable: str, default: Path) -> Path:
        value = os.environ.get(variable)
        return Path(value) if value else default

    if sys.platform == "win32":
        return [base("LOCALAPPDATA", home / "AppData" / "Local") / "pdfmd", base("APPDATA", home / "AppData" / "Roaming") / "pdfmd"]
    return [base("XDG_CACHE_HOME", home / ".cache") / "pdfmd", base("XDG_CONFIG_HOME", home / ".config") / "pdfmd",
            base("XDG_DATA_HOME", home / ".local" / "share") / "pdfmd"]


def snapshot(folders: list[Path]) -> dict[str, int]:
    """Each folder and what it holds two levels down, with the times they last changed (a folder's changes when something is
    added to it or removed, so a file made deeper down shows too)."""
    seen: dict[str, int] = {}
    for folder in folders:
        try:
            seen[str(folder)] = folder.stat().st_mtime_ns
        except OSError:
            continue
        for first in _entries(folder):
            seen[str(first)] = _mtime(first)
            if first.is_dir() and not first.is_symlink():
                for second in _entries(first):
                    seen[str(second)] = _mtime(second)
    return seen


def _entries(folder: Path) -> list[Path]:
    try:
        return list(folder.iterdir())
    except OSError:
        return []


def _mtime(path: Path) -> int:
    try:
        return path.lstat().st_mtime_ns
    except OSError:
        return 0


def changes(before: dict[str, int], after: dict[str, int]) -> list[str]:
    """The paths that are new or changed (gone ones are not the tests' doing: pdfmd prunes old records)."""
    return [path for path in sorted(after) if before.get(path) != after[path]]


def owner(path: Path, folders: list[Path]) -> Path | None:
    """The document a changed path in a cache belongs to, when its entry says: a build record's folder (`builds/NAME`, the
    `document:` line of its records) or a document's cache folder (its `.pdfmd-source.json`)."""
    import json
    for folder in folders:
        try:
            parts = path.relative_to(folder).parts
        except ValueError:
            continue
        if not parts:
            return None
        if parts[0] == "builds" and len(parts) >= 2:
            for record in sorted(Path(folder, *parts[:2]).glob("*.log")):
                try:
                    for line in record.read_text(encoding="utf-8", errors="replace").splitlines()[:6]:
                        if line.startswith("document:"):
                            text = line.split(":", 1)[1].strip()
                            return Path.home() / text[2:] if text.startswith("~/") else Path(text)
                except OSError:
                    continue
            return None
        try:
            return Path(json.loads(Path(folder, parts[0], ".pdfmd-source.json").read_text(encoding="utf-8"))["path"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
    return None


def test_owned(document: Path) -> bool:
    """A document in a temporary folder or in this checkout: one a test built."""
    places = {os.path.realpath(tempfile.gettempdir()), os.path.realpath(str(Path(__file__).resolve().parent.parent))}
    if sys.platform != "win32":
        places |= {os.path.realpath("/tmp"), os.path.realpath("/var/folders")}
    real = os.path.realpath(str(document))
    return any(real == place or real.startswith(place.rstrip(os.sep) + os.sep) for place in places)


def verdict(found: list[str], folders: list[Path]) -> tuple[list[str], list[str]]:
    """What counts against the tests, and what a document built elsewhere during the run (the author's own work) explains.
    A path that names no document counts against them, unless such a build happened: then it may be that build's."""
    tests, elsewhere, unknown = [], [], []
    for path in found:
        document = owner(Path(path), folders)
        (unknown if document is None else tests if test_owned(document) else elsewhere).append(path)
    return (tests, elsewhere + unknown) if elsewhere else (tests + unknown, [])


def _check(folders: list[Path], before: dict[str, int], scratch: str) -> None:
    shutil.rmtree(scratch, ignore_errors=True)
    tests, other = verdict(changes(before, snapshot(folders)), folders)
    home = str(Path.home())

    def listed(paths: list[str]) -> str:
        lines = [path.replace(home, "~", 1) for path in paths]
        more = f"\n  ... and {len(lines) - SHOWN} more" if len(lines) > SHOWN else ""
        return "\n  " + "\n  ".join(lines[:SHOWN]) + more

    sys.stdout.flush()
    if other:
        print("\nNOTE  pdfmd's real cache changed during the run by a build of a document outside the tests, not counted:"
              + listed(other), file=sys.stderr)
    if tests:
        print("\nERROR  the test run wrote into pdfmd's real folders, which it must leave alone (tests/isolation_support.py):"
              + listed(tests), file=sys.stderr)
    sys.stderr.flush()
    if tests:
        os._exit(1)


def _isolate() -> None:
    if os.environ.get(MARK) and Path(os.environ[MARK]).is_dir():
        return
    folders = real_folders()
    REAL[:] = folders
    before = snapshot(folders)
    scratch = tempfile.mkdtemp(prefix="pdfmd-tests-home-")
    places = {"XDG_CACHE_HOME": "cache", "XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "data",
              "LOCALAPPDATA": "local", "APPDATA": "roaming"}
    for variable, name in places.items():
        Path(scratch, name).mkdir()
        os.environ[variable] = str(Path(scratch, name))
    os.environ[MARK] = scratch
    if os.environ.get("PDFMD_CONFIG"):                # a config file named by path is a real one
        del os.environ["PDFMD_CONFIG"]
    os.environ.setdefault("PDFMD_BUILD_LOG", "off")   # a record for each of the documents the tests build is no use (the tests of
    #                                                   the record switch it on in their own cache folder)
    atexit.register(_check, folders, before, scratch)


_isolate()
