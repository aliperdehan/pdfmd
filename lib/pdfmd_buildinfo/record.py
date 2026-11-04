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
from pathlib import Path

NAME = re.compile(r"^(\d{8}-\d{6})(?:-(\d+))?-(ok|failed)\.log$")


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
    while (folder / name).exists():
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
    path = folder / file_name(when, ok, folder)
    temporary = folder / (path.name + ".tmp")
    temporary.write_text(scrub_home(clip(text, limit), home), encoding="utf-8", errors="replace")
    os.replace(temporary, path)
    prune(folder, keep)
    return path
