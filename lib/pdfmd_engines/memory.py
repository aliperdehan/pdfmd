"""Pandoc's optional GHC heap cap, scoped to one build and inherited by pdfmd children."""
from __future__ import annotations

import contextlib
import functools
import os
import re
import subprocess
from pathlib import Path

from pdfmd_base import bound
from pdfmd_base import core

ENV = "PDFMD_PANDOC_MEMORY"


def normalise(value) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if not re.fullmatch(r"[1-9][0-9]*[kmg]", text):
        raise ValueError("a positive size such as 512m or 2g (whole k, m or g units)")
    return text


@contextlib.contextmanager
def scope():
    """Restore the enclosing build's cap, also after a failed or nested build."""
    previous = os.environ.get(ENV)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = previous


def scoped(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        with scope():
            return function(*args, **kwargs)
    return wrapped


def set_limit(source: Path, metadata_files: list[Path]) -> None:
    value = core.first_pdfmd_option(source, metadata_files, "pandoc-memory")
    try:
        size = normalise(value)
    except ValueError as error:
        raise SystemExit(f"{core.display_path(source)}: pdfmd-options.pandoc-memory must be {error}, not {value!r}") from None
    # An empty value explicitly switches off an inherited parent build's cap.
    os.environ[ENV] = size or ""


def heap_command(arguments):
    """Append the RTS heap limit to every Pandoc invocation."""
    if not arguments:
        return arguments
    from pdfmd_engines.tools import pinned_program
    program = str(arguments[0])
    if Path(program).name.lower() not in ("pandoc", "pandoc.exe") and program != pinned_program("pandoc"):
        return arguments
    value = os.environ.get(ENV)
    if value is None and bound() is not None:
        value = core.config_options().get("pandoc-memory")
    try:
        size = normalise(value)
    except ValueError as error:
        raise SystemExit(f"pdfmd-options.pandoc-memory must be {error}, not {value!r}") from None
    return [*arguments, "+RTS", "-M" + size, "-RTS"] if size else arguments


def command(arguments):
    """Apply Pandoc's heap limit and exact tool filenames before running or logging."""
    arguments = heap_command(arguments)
    if bound() is None:
        return arguments
    from pdfmd_engines.tools import pinned_command
    return pinned_command(arguments)


def heap_note(error, arguments):
    text = error.decode("utf-8", errors="replace") if isinstance(error, bytes) else error or ""
    capped = "+RTS" in arguments and any(str(word).startswith("-M") for word in arguments[arguments.index("+RTS") + 1:])
    if capped and "heap" in text.lower() and ("overflow" in text.lower() or "exhausted" in text.lower()):
        note = "\nPandoc reached its heap cap; raise or unset pdfmd-options.pandoc-memory.\n"
        return error + (note.encode("utf-8") if isinstance(error, bytes) else note)
    return error


def run(arguments, **kwargs):
    """Run with the cap, keeping the original diagnostic and naming its setting on heap overflow."""
    arguments = command(arguments)
    try:
        done = subprocess.run(arguments, **kwargs)
    except subprocess.CalledProcessError as error:
        error.stderr = heap_note(error.stderr, arguments)
        raise
    if done.returncode:
        done.stderr = heap_note(done.stderr, arguments)
    return done
