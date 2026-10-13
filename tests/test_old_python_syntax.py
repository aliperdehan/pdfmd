"""v3.28.32: every file of pdfmd parses on the oldest Python it supports (3.9). A backslash inside an f-string's braces,
nested quotes of the same kind and the like are errors there and fine on 3.12+, where the suite mostly runs: such a line
went unseen for days and broke every Word/ODF build on 3.9-3.11 (pdfmd_office/properties.py, v3.28.5)."""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIPPED = {".git", "__pycache__", "dist", "build"}
CHECK = ("import ast, pathlib, sys\nbad = []\nfor name in sys.argv[1:]:\n"
         "    try:\n        ast.parse(pathlib.Path(name).read_text(encoding='utf-8'), filename=name)\n"
         "    except SyntaxError as error:\n        bad.append(f'{name}:{error.lineno}: {error.msg}')\n"
         "print('\\n'.join(bad))\nsys.exit(1 if bad else 0)\n")


def sources() -> list[str]:
    return sorted(str(path) for path in ROOT.rglob("*.py") if not SKIPPED & set(path.relative_to(ROOT).parts))


def older_pythons() -> list[str]:
    """This interpreter when it is older than 3.12, and the other old ones on PATH (and macOS's own 3.9)."""
    found: list[str] = []
    for name in ("python3.9", "python3.10", "python3.11", "/usr/bin/python3"):
        path = shutil.which(name)
        if path and path not in found:
            found.append(path)
    if sys.version_info < (3, 12) and sys.executable not in found:
        found.append(sys.executable)
    old = []
    for path in found:
        try:
            version = subprocess.run([path, "-c", "import sys; print(sys.version_info[0] * 100 + sys.version_info[1])"],
                                     capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            continue
        if version.isdigit() and int(version) < 312:
            old.append(path)
    return old


class OldPython(unittest.TestCase):
    def test_every_file_parses_on_the_oldest_python_here(self):
        pythons = older_pythons()
        if not pythons:
            self.skipTest("no Python older than 3.12 on this machine (CI's matrix runs it on 3.9)")
        files = sources()
        self.assertGreater(len(files), 50)
        for python in pythons:
            with self.subTest(python):
                done = subprocess.run([python, "-c", CHECK, *files], capture_output=True, text=True, timeout=300)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_the_check_itself_finds_a_backslash_in_an_f_string_on_3_9(self):
        if sys.version_info >= (3, 12):
            self.skipTest("3.12+ accepts it")
        with self.assertRaises(SyntaxError):
            ast.parse("x = f'{y[\"a\\\\\"]}'")


if __name__ == "__main__":
    unittest.main()
