"""The record a build leaves behind: one plain-text file per build, kept in a folder per document, so that whoever debugs
a failure reads what happened instead of building again.

Pure: no pdfmd import. The caller composes the text; this module keeps it safe to store and to share (the home folder
written as ``~``, a size cap that keeps the start and the end), names the files, writes them without a half-written file
ever being seen, and prunes: the newest ``keep`` records stay, and the newest failed one stays whatever its age, so a
later successful build never erases the evidence of a failure.

    folder/20261029-140533-ok.log
    folder/20261029-135901-failed.log
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from stat import S_ISREG
from unicodedata import normalize

NAME = re.compile(r"^(\d{8}-\d{6})(?:-(\d+))?-(ok|failed)\.log$")
WRITTEN = re.compile(r"written:   ([0-9a-f]{64}) ([0-9a-f]{64})\n")


def output_key(path: Path) -> str:
    """Find candidate records even under a different spelling on a case-insensitive file system."""
    spelling = normalize("NFC", str(path.resolve()).casefold())
    return sha256(os.fsencode(spelling)).hexdigest()


def file_identity(info: os.stat_result) -> tuple[int, int, int | float | None]:
    birth = getattr(info, "st_birthtime", None)
    if os.name == "nt":
        birth = getattr(info, "st_birthtime_ns", info.st_ctime_ns)
    return info.st_dev, info.st_ino, birth


def output_fingerprint(path: Path) -> str | None:
    """Identify the written file and its contents. A byte-identical replacement is a different file."""
    def state(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    try:
        before = path.stat()
        if not S_ISREG(before.st_mode):
            return None
        with path.open("rb") as handle:
            if state(before) != state(os.fstat(handle.fileno())):
                return None
            digest = sha256(repr(file_identity(before)).encode("ascii"))
            for block in iter(lambda: handle.read(128 * 1024), b""):
                digest.update(block)
            if state(before) == state(path.stat()):
                return digest.hexdigest()
    except OSError:
        pass
    return None


def matching_outputs(paths: list[Path], roots: set[Path]) -> set[Path]:
    """Look at retained build records only. Older records lack a fingerprint and prove no ownership."""
    candidates = {}
    for path in paths:
        candidates.setdefault(output_key(path), set()).add(path)
    fingerprints = {}
    found = set()
    for root in roots:
        try:
            entries = list(root.glob("*/*.log"))
        except OSError:
            continue
        for entry in entries:
            if not NAME.fullmatch(entry.name):
                continue
            try:
                with entry.open(encoding="utf-8", errors="replace") as handle:
                    if handle.readline() != "pdfmd build record\n":
                        continue
                    match = WRITTEN.fullmatch(handle.readline())
            except OSError:
                continue
            if match is None or (key := match[1]) not in candidates:
                continue
            for path in candidates[key] - found:
                if path not in fingerprints:
                    fingerprints[path] = output_fingerprint(path)
                if fingerprints[path] == match[2]:
                    found.add(path)
            if candidates[key] <= found:
                del candidates[key]
            if not candidates:
                return found
    return found


def scrub_home(text: str, home: str) -> str:
    """``home`` (and its forward-slash spelling) written as ``~``, so a record can be pasted into a bug report."""
    if not home or home in ("/", "\\"):
        return text
    for spelling in {home, home.replace("\\", "/")}:
        text = text.replace(spelling, "~")
    return text


def clip(text: str, limit: int) -> str:
    """``text`` cut to about ``limit`` bytes, keeping the start (what was asked) and, more of it, the end (where the error is)."""
    data = text.encode("utf-8", "replace")
    if limit <= 0 or len(data) <= limit:
        return text
    head, tail = limit // 3, limit - limit // 3
    cut = len(data) - head - tail
    return (data[:head].decode("utf-8", "ignore") + f"\n\n[... {cut} bytes cut out of the middle (build-log-max-size) ...]\n\n"
            + data[-tail:].decode("utf-8", "ignore"))


def file_name(when: datetime, ok: bool, folder: Path) -> str:
    base = when.strftime("%Y%m%d-%H%M%S")
    kind = "ok" if ok else "failed"
    name, number = f"{base}-{kind}.log", 1
    while os.path.lexists(folder / name) or os.path.lexists(folder / (name + ".tmp")):
        number += 1
        name = f"{base}-{number}-{kind}.log"
    return name


def records(folder: Path) -> list[Path]:
    """The records of ``folder``, newest first."""
    try:
        found = [path for path in folder.iterdir() if NAME.match(path.name)]
    except OSError:
        return []

    def key(path: Path):
        match = NAME.match(path.name)
        return match.group(1), int(match.group(2) or 1)
    return sorted(found, key=key, reverse=True)


def newest(folder: Path, failed: bool = False) -> Path | None:
    for path in records(folder):
        if not failed or path.name.endswith("-failed.log"):
            return path
    return None


def newest_of(folders: list[Path], failed: bool = False) -> Path | None:
    """The newest record of several folders (the cache of the machine and the one beside the document)."""
    found = [path for path in (newest(folder, failed) for folder in folders) if path is not None]

    def key(path: Path):
        match = NAME.match(path.name)
        return match.group(1), int(match.group(2) or 1)
    return max(found, key=key) if found else None


def prune(folder: Path, keep: int) -> None:
    """Keep the newest ``keep`` records and the newest failed one; delete the rest, by name."""
    everything = records(folder)
    survivors = set(everything[:max(1, keep)])
    latest_failure = next((path for path in everything if path.name.endswith("-failed.log")), None)
    if latest_failure is not None:
        survivors.add(latest_failure)
    for path in everything:
        if path not in survivors:
            try:
                path.unlink()
            except OSError:
                pass


def write(folder: Path, text: str, ok: bool, keep: int, limit: int, when: datetime | None = None,
          home: str | None = None) -> Path:
    """Store ``text`` as the newest record of ``folder`` and prune the older ones; the path. May raise OSError."""
    when = when or datetime.now()
    home = str(Path.home()) if home is None else home
    folder.mkdir(parents=True, exist_ok=True)
    text = scrub_home(clip(text, limit), home)
    while True:
        path = folder / file_name(when, ok, folder)
        temporary = folder / (path.name + ".tmp")
        try:
            handle = temporary.open("x", encoding="utf-8", errors="replace")
        except FileExistsError:
            continue
        try:
            with handle:
                taken = os.path.lexists(path)    # a concurrent writer finished after file_name checked
                if not taken:
                    handle.write(text)
            if taken:
                temporary.unlink()
                continue
            os.replace(temporary, path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        break
    prune(folder, keep)
    return path
