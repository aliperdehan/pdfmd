"""Per-invocation warning, note and error totals."""

from __future__ import annotations

import re
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar

from pdfmd_base import core


CURRENT = ContextVar("diagnostic_summary", default=None)
LEVELS = ("warning", "note", "error")
RETURNED = re.compile(r"^\s*(WARN\b|\[WARNING\]|NOTE\b)")


class Summary:
    def __init__(self):
        self.counts = Counter()
        self.requested = False

    def show(self):
        from pdfmd_log import CHATTER, emit

        if self.requested and CHATTER.get() != "off":
            parts = [f"{count} {level}{'s' if count != 1 else ''}"
                     for level in LEVELS if (count := self.counts[level])]
            if parts:
                emit("result", None, ", ".join(parts))


@contextmanager
def scope(*, display=False):
    tally = Summary()
    token = CURRENT.set(tally)
    try:
        yield tally
    except SystemExit as error:
        if isinstance(error.code, str):
            tally.counts["error"] += 1
        raise
    finally:
        try:
            if display:
                tally.show()
        finally:
            CURRENT.reset(token)


def select(cli, document, metadata=(), *, batch=False) -> None:
    from pdfmd_log import output_setting

    tally = CURRENT.get()
    if tally is not None:
        wanted = bool(cli or core.option_flag(output_setting("summary", document, metadata)))
        tally.requested = wanted or (batch and tally.requested)


def count(level: str) -> None:
    tally = CURRENT.get()
    if tally is not None and level in LEVELS:
        tally.counts[level] += 1


def returned_diagnostics(text, previously_seen=()) -> None:
    """Count warnings and notes returned by an engine, including those a strict failure will quote."""
    if CURRENT.get() is None or not isinstance(text, str):
        return
    known = {line.strip() for line in previously_seen}
    for line in text.splitlines():
        match = RETURNED.match(line)
        if match and line.strip() not in known:
            count("note" if match[1] == "NOTE" else "warning")


def collect(result):
    tally = CURRENT.get()
    if tally is not None:
        tally.counts.update(getattr(result, "diagnostic_counts", {}))
