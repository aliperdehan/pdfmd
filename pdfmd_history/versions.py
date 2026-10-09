"""A document's versions -- backups, git commits, compiles -- as one list, and the words people use for one of them."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class Version:
    when: float                                  # seconds since the epoch
    kind: str                                    # backup | git | compile | restore | note
    ref: str                                     # what `--history-diff REF` takes: a timestamp id, or a commit hash
    label: str                                   # the file name of a backup, the commit's subject
    summary: str = ""                            # what was compiled / who committed
    path: Path | None = None                     # a backup's file
    commit: str = ""                             # a commit's full hash
    document: Path | None = None                 # which file of a document in parts it belongs to
    lines: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def when_text(self) -> str:
        return datetime.fromtimestamp(self.when).strftime("%Y-%m-%d %H:%M")


def timestamp_id(name: str) -> str:
    """The digits that identify a backup in its file name: 20261009112201 (the 14 of a date and time)."""
    full = re.search(r"(?<!\d)(\d{8})-?(\d{6})(?!\d)", name)
    return (full.group(1) + full.group(2)) if full else name


def sort_newest_first(versions: list[Version]) -> list[Version]:
    return sorted(versions, key=lambda version: (version.when, version.kind != "git"), reverse=True)


def table(versions: list[Version], show_document: bool = False, width: int = 110) -> str:
    """The numbered list a person reads."""
    rows = []
    for number, version in enumerate(versions, 1):
        what = {"backup": "backup", "git": "git", "compile": "compiled", "restore": "restored",
                "note": "note"}[version.kind]
        name = version.label if version.kind != "git" else f"{version.ref[:7]}  {version.label}"
        extra = f"  {version.summary}" if version.summary else ""
        if show_document and version.document is not None:
            name = f"{version.document.name}: {name}"
        line = f"{number:>3}  {version.when_text}  {what:<8} {name}{extra}"
        rows.append(line if len(line) <= width else line[:width - 1] + "…")
    return "\n".join(rows)


class Ambiguous(Exception):
    pass


def resolve(reference: str, versions: list[Version], differs=lambda version: True) -> Version | None:
    """The version `reference` names: its number in the list, `latest` (the newest that can be restored) or `previous`
    (the newest of those that `differs` from the file as it is: the one worth going back to), a backup's timestamp (any
    prefix of it), its file name, or a commit hash (4 digits or more). None when nothing matches; Ambiguous when
    several do."""
    word = reference.strip()
    restorable = [version for version in versions if version.kind in ("backup", "git")]
    if word.casefold() in ("latest", "previous", "last"):
        if word.casefold() == "latest":
            return restorable[0] if restorable else None
        return next((version for version in restorable if differs(version)), None)
    if re.fullmatch(r"\d{1,4}", word) and 1 <= int(word) <= len(versions):
        return versions[int(word) - 1]
    found = [version for version in restorable if version.path is not None and word == version.path.name]
    if not found:
        digits = re.sub(r"[-_: ]", "", word)
        found = [version for version in restorable if version.kind == "backup" and len(digits) >= 6 and digits.isdigit()
                 and timestamp_id(version.label).startswith(digits)]
    if not found and re.fullmatch(r"[0-9a-fA-F]{4,40}", word):
        found = [version for version in restorable if version.kind == "git" and version.commit.startswith(word.lower())]
    if len(found) > 1:
        raise Ambiguous(", ".join(version.label for version in found[:6]))
    return found[0] if found else None


def unified(current: str, other: str, other_label: str, current_label: str = "current", color: bool = False) -> str:
    lines = list(difflib.unified_diff(current.splitlines(), other.splitlines(), current_label, other_label,
                                      lineterm="", n=2))
    if not color:
        return "\n".join(lines)
    painted = []
    for line in lines:
        if line.startswith("+") and not line.startswith("+++"):
            painted.append(f"\x1b[32m{line}\x1b[0m")
        elif line.startswith("-") and not line.startswith("---"):
            painted.append(f"\x1b[31m{line}\x1b[0m")
        elif line.startswith("@@"):
            painted.append(f"\x1b[36m{line}\x1b[0m")
        else:
            painted.append(line)
    return "\n".join(painted)
