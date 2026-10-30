"""Where a test points pdfmd's cache folder. pdfmd keeps its cache in XDG_CACHE_HOME, and on Windows in %LOCALAPPDATA%: a test that
sets only the first writes into the real cache there."""

from __future__ import annotations

from pathlib import Path


def cache_env(folder: str | Path) -> dict[str, str]:
    """The environment variables that name the cache folder on every system, both set to ``folder``."""
    return {"XDG_CACHE_HOME": str(folder), "LOCALAPPDATA": str(folder)}
