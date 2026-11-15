"""The shared `core` of the pdfmd_* packages (phase 2 of the split, SPLIT.md; plan decision D2).

A package reads pdfmd's own helpers, settings and state as `core.X` when its code runs, never by importing pdfmd: run as a
script, pdfmd.py is `__main__`, and a second import would be a second copy with its own state. `core` is one object for
every package (`from pdfmd_base import core`): pdfmd.py binds it to itself when it loads, before it imports any other
package, and every read, write and deletion of an attribute of `core` goes to that module, so `mock.patch.object(pdfmd, ...)`
reaches every package. The first binding wins: a second copy of pdfmd.py in one process (a test loads one) never re-points
it. A package imported on its own (a `-j` worker unpickling a function by its module, one package importing another, a
test) therefore has its `core` whenever pdfmd is loaded; until 3.33.188 each package had a `core = None` of its own, set only
when pdfmd.py imported it.

`names_into()` (3.33.189) gives pdfmd.py its `names("pdfmd_x.role", "a b c")`, the lines of its names table: each name is
served as `pdfmd.a` from that module, loaded on the first read (pdfmd.py's module `__getattr__`).

Since 3.33.209 (phase 2, move 1) it also holds the helpers that pdfmd.py and most packages use; pdfmd.py imports them by
name when it loads, the one package it binds with a plain import: writing a file whole (`atomic_file`, `atomic_write_text`,
`atomic_write_bytes`, `atomic_write_pdf`, `write_text_lf`), `read_text_best_effort`, `read_text_or_none`, `sha256_text`,
`sha1_file`, `natural_key`, `split_command`, `own_python_folder` (pdfmd.py calls it before it imports anything optional),
and the dictionary `BUILD` (`pdfmd.BUILD` is this one object) with what records into it while a build runs: the decorators
`timed` and `noted`, `record_note` and `vprint`. None of them reads `core`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Iterator
from pathlib import Path
from contextlib import contextmanager
import functools
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys

_bound = None                                   # the pdfmd module, once pdfmd.py has bound it


def bind(module) -> None:
    """Make `core` stand for ``module`` (pdfmd.py passes itself); the first binding wins."""
    global _bound
    if _bound is None:
        _bound = module


def bound():
    """The module `core` stands for, or None while nothing has bound it."""
    return _bound


def names_into(table: dict[str, str]) -> Callable[[str, str], None]:
    """`names(module, listed)` for the names table ``table`` (pdfmd.py's `DEFERRED_NAMES`: name -> module): each name in
    ``listed``, separated by spaces or line breaks, is served from ``module`` (`pdfmd_x`, or `pdfmd_x.role` for one module
    of it). The table is handed in, not reached through `bound()`: a second copy of pdfmd.py fills its own. A word that is
    not a name, or a name the table already serves from another module, is a ValueError, raised when pdfmd.py loads."""
    def names(module: str, listed: str) -> None:
        words = listed.split()
        for name in words:
            if not name.isidentifier():
                raise ValueError(f"names({module!r}, ...): {name!r} is not a name")
            if table.get(name, module) != module:
                raise ValueError(f"names({module!r}, ...): {name} is already served from {table[name]}")
        table.update(dict.fromkeys(words, module))
    return names


def _unbound(name: str) -> AttributeError:
    return AttributeError(f"core.{name}: pdfmd_base.core is not bound yet (pdfmd.py binds it when it loads)")


class _Core:
    """pdfmd as the packages see it: every attribute is the bound module's. It holds no state of its own (no slots), so
    `core.__dict__` is the module's too, and `mock.patch.object(core, ...)` saves and restores what the module had."""

    __slots__ = ()

    def __getattr__(self, name: str):
        if _bound is None:
            raise _unbound(name)
        return getattr(_bound, name)

    def __setattr__(self, name: str, value) -> None:
        if _bound is None:
            raise _unbound(name)
        setattr(_bound, name, value)

    def __delattr__(self, name: str) -> None:
        if _bound is None:
            raise _unbound(name)
        delattr(_bound, name)

    def __dir__(self):
        return dir(_bound) if _bound is not None else []

    def __repr__(self) -> str:
        return f"<pdfmd core: {_bound!r}>"


core = _Core()


def write_text_lf(path: Path, text: str) -> None:
    """``path.write_text(text, encoding="utf-8", newline="\\n")``, which Python 3.9 lacks the `newline` of; all or nothing
    (atomic_write_text)."""
    atomic_write_text(path, text, newline="\n")


# -- Writing a file in place: through a temporary file in the same folder and os.replace() -------------------------
# A file pdfmd rewrites (the document's BUILD NOTES, the config, the metadata, a restored source, a PDF it finishes) is written
# whole to `.NAME.<pid>.<random>.part` beside it and then renamed over it: a crash, a full disk or ^C half-way leaves the old
# file as it was (and the temporary file is removed). A symlink is written through, as write_text() does (the link stays); the
# mode of the file it replaces is kept; text is written as write_text() would (newline=None: the platform's, "\n" for
# write_text_lf). Not used for scratch files in a temporary folder, nor for a cache that is only ever replaced whole.
@contextmanager
def atomic_file(path: Path) -> Iterator[Path]:
    """The path of a temporary file beside ``path`` to write into; on leaving the block it is renamed over ``path``, or removed
    when the block raised (``path`` is then untouched)."""
    path = Path(path)
    target = Path(os.path.realpath(path)) if path.is_symlink() else path
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{os.urandom(4).hex()}.part")
    try:
        yield temporary
        try:
            shutil.copymode(target, temporary)
        except OSError:
            pass                                          # a new file: the umask's mode, as the open() gave it
        os.replace(temporary, target)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8", newline: str | None = None) -> None:
    """``Path.write_text(text, encoding=...)`` (``newline`` as open() takes it), all or nothing."""
    with atomic_file(path) as temporary:
        with open(temporary, "x", encoding=encoding, newline=newline) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """``Path.write_bytes(data)``, all or nothing."""
    with atomic_file(path) as temporary:
        with open(temporary, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())


def atomic_write_pdf(writer, path: Path) -> None:
    """A pypdf writer's document over ``path``, all or nothing."""
    with atomic_file(path) as temporary:
        with open(temporary, "xb") as handle:
            writer.write(handle)
            handle.flush()
            os.fsync(handle.fileno())


def own_python_folder() -> Path:
    """Where `pdfmd --install` puts Python packages when the Python it runs from is managed by the system (PEP 668:
    Homebrew, Debian), one folder per Python version, beside pdfmd's other tools (data_root())."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "pdfmd" / "python" / f"{sys.version_info[0]}.{sys.version_info[1]}"


def read_text_best_effort(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def split_command(text: str) -> list[str]:
    """A command line typed by a person (`$PAGER`, `--editor`) as words. POSIX rules eat the backslashes of a Windows path
    (`C:\\Tools\\less.exe` -> `C:Toolsless.exe`), so on Windows the backslashes stay and only the quotes around a word go."""
    if os.name != "nt":
        return shlex.split(text)
    return [word[1:-1] if len(word) > 1 and word[0] == word[-1] and word[0] in "\"'" else word
            for word in shlex.split(text, posix=False)]


def timed(name):
    """Decorator: the call is a step of the build's timer. ``name`` is the step's name, or a function of (args, kwargs) that
    gives it, or None for a call that does no work of its own (it is then not a step)."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            timer = BUILD.get("timer")
            step = name(args, kwargs) if callable(name) and timer is not None else name
            if timer is None or step is None:
                return function(*args, **kwargs)
            with timer.step(step):
                return function(*args, **kwargs)
        return wrapper
    return decorate


def record_note(text: str) -> None:
    """Add lines to the record of the build that is running (nothing when there is none)."""
    lines = BUILD.get("record")
    if lines is not None and text:
        lines.extend(text.rstrip("\n").split("\n"))


def vprint(shown: bool, *args, **kwargs) -> None:
    """print() for a line that only --verbose shows: on the console when ``shown``, and always in the record of the build
    (the first step of `emit`: the sites that print under --verbose go through here, the chatter ladder turns it into
    emit(level, id, text))."""
    if shown:
        print(*args, **kwargs)
    else:
        record_note(str(kwargs.get("sep", " ")).join(str(item) for item in args))


def noted(label, engine: bool = False):
    """Decorator: what a subprocess answered (exit code, stderr, stdout) goes into the record of the build; with
    ``engine``, the label also joins the engines the build tried."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            result = function(*args, **kwargs)
            if isinstance(result, subprocess.CompletedProcess):
                name = label(args, kwargs) if callable(label) else label
                if engine and name not in BUILD["tried"]:
                    BUILD["tried"].append(name)
                record_note(f"----- {name}: exit {result.returncode} -----")
                for stream, text in (("stderr", result.stderr), ("stdout", result.stdout)):
                    if isinstance(text, str) and text.strip():
                        record_note(f"[{stream}]\n{text.strip()}")
            return result
        return wrapper
    return decorate


def natural_key(name: str) -> list:
    """Sort key where digit runs compare as numbers (2-x < 10-y)."""
    return [int(piece) if index % 2 else piece.casefold()
            for index, piece in enumerate(re.split(r"(\d+)", name))]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


BUILD: dict = {"engine": None, "failed": [], "output": None, "sources": [], "partial": None, "root": None, "timer": None, "record": None, "tried": [], "chain": None, "repaired": []}     # what built the file convert_one is working on


def read_text_or_none(path: Path | None) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path else None
    except OSError:
        return None


def sha1_file(path: Path) -> str | None:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return None
