"""Which Pandoc the tests run against, and the decorators that skip a test for a Pandoc too old to have its feature.

The oldest Pandoc pdfmd is tested with is 3.1.3 (what the claude.ai sandbox has); PANDOC_FEATURES in pdfmd.py lists what
older versions do without.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import tempfile
import unittest


def _version() -> tuple[int, ...]:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        return (0,)
    try:
        first = subprocess.run([pandoc, "--version"], capture_output=True, text=True).stdout.splitlines()[0]
        return tuple(int(part) for part in re.search(r"(\d+(?:\.\d+)+)", first).group(1).split("."))
    except (OSError, IndexError, AttributeError, ValueError):
        return (0,)


PANDOC_VERSION = _version()


def tex_tree_env(tree) -> dict:
    """The variables that make kpsewhich (TeX Live and MiKTeX) look in a TeX tree of the test's own: TEXMFHOME, and TEXINPUTS with the
    platform's separator (a `:` would cut a Windows drive letter in two; a trailing separator keeps the default search path)."""
    return {"TEXMFHOME": str(tree), "TEXINPUTS": f"{tree}//{os.pathsep}"}


def discard_path(suffix: str) -> str:
    """A file for a Pandoc output a test does not read. The null device will not do: Pandoc's binary writers (odt, docx) cannot open
    `NUL` on Windows ("NUL: withBinaryFile: does not exist")."""
    directory = tempfile.mkdtemp(prefix="pdfmd-discard-")
    atexit.register(shutil.rmtree, directory, True)
    return os.path.join(directory, "out" + suffix)


def _crossref_usable() -> bool:
    """pandoc-crossref is installed and built for this Pandoc: pdfmd runs it only then (crossref_filter_args)."""
    crossref = shutil.which("pandoc-crossref")
    if not crossref or PANDOC_VERSION == (0,):
        return False
    try:
        done = subprocess.run([crossref, "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    found = re.search(r"built with Pandoc v(\d+(?:\.\d+)+)", done.stdout + done.stderr)
    return not found or tuple(int(part) for part in found.group(1).split("."))[:2] == PANDOC_VERSION[:2]


CROSSREF_USABLE = _crossref_usable()


def needs_pandoc(*version: int, why: str = ""):
    """Skip the test unless Pandoc is at least `version`."""
    wanted = ".".join(map(str, version))
    return unittest.skipIf(PANDOC_VERSION < tuple(version), f"needs Pandoc {wanted}" + (f" ({why})" if why else ""))


def needs_crossref(test):
    """Skip the test unless pdfmd would run pandoc-crossref (installed, and built for this Pandoc)."""
    return unittest.skipUnless(CROSSREF_USABLE, "needs a pandoc-crossref built for this Pandoc")(test)
