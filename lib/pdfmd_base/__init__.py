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
"""

from __future__ import annotations

from collections.abc import Callable

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
