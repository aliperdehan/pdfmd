"""The append-only diagnostic log requested for a build."""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from pdfmd_base import core


CURRENT = ContextVar("transcript", default=None)


@contextmanager
def append_file(path: Path):
    with path.open("ab", buffering=0) as handle:
        if os.name != "nt":
            yield handle
            return
        # The Windows C runtime seeks to the end for O_APPEND. Lock byte zero
        # across the seek and writes so two workers cannot write at the same offset.
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield handle
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


class Transcript:
    def __init__(self, path: Path | None = None, *, pending=False):
        self.path = path
        self.pending = [] if pending else None

    def add(self, text: str, *, muted=False) -> None:
        lines = [line + (" (muted)" if muted else "") for line in text.splitlines()]
        if self.pending is not None:
            self.pending.extend(lines)
        elif self.path is not None:
            self.append(self.path, lines)

    @staticmethod
    def append(path: Path, lines: list[str]) -> None:
        if not lines:
            return
        try:
            with append_file(path) as handle:
                for line in lines:
                    data = (line + "\n").encode("utf-8", errors="backslashreplace")
                    if handle.write(data) != len(data):
                        raise OSError("short write")
        except OSError as error:
            raise SystemExit(f"ERROR  --log: {path}: {error.strerror or error}") from None

    def start(self, path: Path | None, source: Path, output: Path) -> None:
        if path is not None:
            from datetime import datetime

            # Output routes replace a file at the end of a build. Sharing the
            # destination with the transcript would lose the log or corrupt it.
            if any(path.resolve() == item.resolve() for item in (source, output)):
                raise SystemExit(f"ERROR  --log: {path} is the build input or output")
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            label = f"{core.display_path(source)} > {core.display_path(output)}"
            label = label.replace("\r", r"\r").replace("\n", r"\n")
            self.append(path, [f"pdfmd {core.PDFMD_VERSION}  {stamp}  {label}", *(self.pending or [])])
        self.path = path
        self.pending = None


@contextmanager
def scope(path: Path | None = None, *, pending=False):
    log = Transcript(path, pending=pending)
    token = CURRENT.set(log)
    try:
        yield log
    except SystemExit as error:
        if isinstance(error.code, str) and not error.code.startswith("ERROR  --log:"):
            log.add(f"ERROR  {error.code}")
        raise
    finally:
        CURRENT.reset(token)


def recording() -> bool:
    log = CURRENT.get()
    return log is not None and (log.path is not None or log.pending is not None)


def record(text: str, *, muted=False) -> None:
    log = CURRENT.get()
    if log is not None and (log.path is not None or log.pending is not None):
        log.add(text, muted=muted)


@contextmanager
def result_scope(batch: bool, result):
    if batch:
        with scope(getattr(result, "log_path", None)):
            yield
    else:
        yield


def destination(cli: Path | None, document: Path, metadata=()) -> Path | None:
    from pdfmd_log import output_setting

    if cli is not None:
        return cli.expanduser().absolute()
    value = output_setting("log", document, metadata)
    if value is None or value is False or value == "":
        return None
    if not isinstance(value, str):
        raise SystemExit(f"ERROR  --log: {document}: pdfmd-options.log must be a file path")
    return document.parent / Path(value).expanduser()
