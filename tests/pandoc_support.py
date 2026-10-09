"""Which Pandoc the tests run against, and the decorators that skip a test for a Pandoc too old to have its feature.

The oldest Pandoc pdfmd is tested with is 3.1.3 (what the claude.ai sandbox has); PANDOC_FEATURES in pdfmd.py lists what
older versions do without.
"""

from __future__ import annotations

import re
import shutil
import subprocess
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


def needs_pandoc(*version: int, why: str = ""):
    """Skip the test unless Pandoc is at least `version`."""
    wanted = ".".join(map(str, version))
    return unittest.skipIf(PANDOC_VERSION < tuple(version), f"needs Pandoc {wanted}" + (f" ({why})" if why else ""))
