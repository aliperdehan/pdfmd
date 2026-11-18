"""Repair C0 controls in the text handed to Pandoc (3es, D85)."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from pdfmd_base import core

# Match a complete CSI sequence first, so its parameters never leak into the output.
_CONTROLS = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BREAKS = frozenset(("\v", "\f"))
_REPORTED: ContextVar[set[Path] | None] = ContextVar("source_control_diagnostics", default=None)


@contextmanager
def diagnostic_scope():
    """A build reports each source once, including during engine retries and draft scans."""
    token = _REPORTED.set(set())
    try:
        yield
    finally:
        _REPORTED.reset(token)


def repair_controls(text: str, path: Path | None = None) -> str:
    """Drop controls, preserving tabs and line endings; turn VT and FF into LF.

    A path requests one warning, with line numbers from the original text.
    The reader's other scans use the same repair silently.
    """
    reported = _REPORTED.get()
    if path is None or (reported is not None and path in reported):
        return _CONTROLS.sub(lambda match: "\n" if match[0] in _BREAKS else "", text)

    changes: dict[int, dict[str, dict[str, None]]] = defaultdict(lambda: {"removed": {}, "replaced": {}})
    line, cursor = 1, 0

    def replace(match: re.Match) -> str:
        nonlocal line, cursor
        word = match[0]
        line += text.count("\n", cursor, match.start())
        cursor = match.end()
        code = f"U+{ord(word[0]):04X}" + (" (ANSI escape sequence)" if len(word) > 1 else "")
        replacement = word in _BREAKS
        changes[line]["replaced" if replacement else "removed"][code] = None
        return "\n" if replacement else ""

    repaired = _CONTROLS.sub(replace, text)
    if changes:
        if reported is not None:
            reported.add(path)
        details = []
        for number, actions in changes.items():
            edits = []
            if actions["removed"]:
                edits.append("removed " + ", ".join(actions["removed"]))
            if actions["replaced"]:
                edits.append("replaced " + ", ".join(actions["replaced"]) + " with newlines")
            details.append(f"line {number}: " + ", ".join(edits))
        print(f"WARN  {core.display_path(path)}: source control characters: " + "; ".join(details), file=sys.stderr)
    return repaired
