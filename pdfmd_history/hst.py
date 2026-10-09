"""The `.hst` format.

    # pdfmd history of report.md -- one entry per line, newest first: WHEN | KIND | TEXT [| key=value ...]
    2026-10-09 11:22:01 | compiled | with nulabreport v1.27.7, pdfmd v3.25.7 | sha=3fa91c0d
    2026-10-09 11:15:00 | restored | version 20261009110000 | from=report.md.bak.20261009110000

WHEN is a local time, `YYYY-MM-DD HH:MM:SS`; KIND is `compiled`, `restored` or `note`; TEXT is free (a `|` is written
`\\|`, a line break `\\n`); the optional `key=value` words (no spaces) say more about the entry. Lines starting with `#`
are comments, and a line that is not an entry is kept as a comment of its own, so nothing a person wrote is lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

HST_SUFFIX = ".hst"
KINDS = ("compiled", "restored", "note")
WHEN_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
SPLIT_RE = re.compile(r"(?<!\\)\|")


@dataclass(frozen=True)
class Entry:
    when: str                                   # YYYY-MM-DD HH:MM:SS
    kind: str                                   # compiled | restored | note
    text: str
    meta: tuple[tuple[str, str], ...] = field(default=(), compare=False)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.when, self.kind, self.text)

    def meta_dict(self) -> dict[str, str]:
        return dict(self.meta)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "\\n")


def _unescape(text: str) -> str:
    out, index = [], 0
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            following = text[index + 1]
            out.append({"n": "\n", "|": "|", "\\": "\\"}.get(following, "\\" + following))
            index += 2
        else:
            out.append(character)
            index += 1
    return "".join(out)


def line_of(entry: Entry) -> str:
    parts = [entry.when, entry.kind, _escape(entry.text)]
    if entry.meta:
        parts.append(" ".join(f"{key}={value}" for key, value in entry.meta if value != ""))
    return " | ".join(part for part in parts if part != "" or part is parts[2])


def parse(text: str) -> tuple[list[Entry], list[str]]:
    """(the entries in the order written, the other lines: comments and anything that is not an entry)."""
    entries: list[Entry] = []
    other: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            other.append(raw.rstrip())
            continue
        fields = [part.strip() for part in SPLIT_RE.split(line)]
        if len(fields) >= 3 and WHEN_RE.match(fields[0]) and fields[1] in KINDS:
            meta: list[tuple[str, str]] = []
            for word in (fields[3].split() if len(fields) > 3 else []):
                key, _, value = word.partition("=")
                if key and value:
                    meta.append((key, value))
            entries.append(Entry(fields[0], fields[1], _unescape(fields[2]), tuple(meta)))
        else:
            other.append("# " + line)            # kept, as a comment: never lose what somebody wrote
    return entries, other


def merge(*lists: list[Entry]) -> list[Entry]:
    """The entries of all the lists, once each (same time, kind and text), newest first. Where two copies of an entry
    carry different `key=value` words, the words are joined."""
    seen: dict[tuple[str, str, str], Entry] = {}
    for entries in lists:
        for entry in entries:
            old = seen.get(entry.key)
            if old is None:
                seen[entry.key] = entry
            elif entry.meta:
                joined = dict(old.meta)
                for key, value in entry.meta:
                    joined.setdefault(key, value)
                seen[entry.key] = Entry(old.when, old.kind, old.text, tuple(joined.items()))
    return sorted(seen.values(), key=lambda entry: entry.when, reverse=True)


def render(entries: list[Entry], name: str, other: list[str] = ()) -> str:
    """The file's text: its header, the comments kept from before, and the entries newest first."""
    comments = [line for line in other if not line.startswith("# pdfmd history of")]
    header = f"# pdfmd history of {name} -- one entry per line, newest first: WHEN | KIND | TEXT [| key=value ...]"
    body = [line_of(entry) for entry in merge(entries)]
    return "\n".join([header, *comments, *body]) + "\n"


def read_file(path: Path) -> tuple[list[Entry], list[str]]:
    try:
        return parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        return [], []


def write_file(path: Path, entries: list[Entry], name: str, other: list[str] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_text(render(entries, name, other), encoding="utf-8")
    partial.replace(path)


def add_entry(path: Path, entry: Entry, name: str) -> bool:
    """Put `entry` in the file at `path` (made if need be). False when it was already there."""
    entries, other = read_file(path)
    if any(old.key == entry.key for old in entries):
        return False
    write_file(path, [*entries, entry], name, other)
    return True
