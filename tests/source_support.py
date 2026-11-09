"""The Python files of pdfmd's own code, for the tests that read the code as text (entry 3fi).

pdfmd.py is being split into packages under lib/; a scan of pdfmd.py alone stops seeing a function the day it moves.
The tests that check the source (probe timeouts, subprocess encodings, the pdfmd-options keys read, words pdfmd must
not contain) take their list of files from here, so a move keeps them checking the same code.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def python_sources(*, vendored: bool = False) -> list[Path]:
    """pdfmd.py first, then every .py file under lib/ in name order. The vendored inkmd (another project's code, a
    generated copy) only when asked."""
    files = [ROOT / "pdfmd.py"]
    for path in sorted((ROOT / "lib").rglob("*.py")):
        if "__pycache__" in path.parts or "node_modules" in path.parts:
            continue
        if not vendored and "pdfmd_inkmd" in path.parts:
            continue
        files.append(path)
    return files


def source_text() -> str:
    """pdfmd.py and lib/ (without the vendored inkmd) as one text, for the scans that look for words or patterns."""
    return "\n".join(path.read_text(encoding="utf-8") for path in python_sources())


def shown(path: Path) -> str:
    """A file's name in a failure message: its path in the repository (two packages may both have an __init__.py)."""
    return path.relative_to(ROOT).as_posix()
