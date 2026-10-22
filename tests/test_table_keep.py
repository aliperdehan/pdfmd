"""`--table-keep` / `pdfmd-options.table-keep`: the `tablekeep` metadata a Lua filter reads, and what wins."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class TableKeep(unittest.TestCase):
    def command(self, front: str, *flags: str) -> subprocess.CompletedProcess:
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-keep-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "d.md").write_text(f"---\ntitle: T\n{front}---\n\n| a |\n|---|\n| 1 |\n", encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "native", "-o", "out.native",
                               "--no-stamp", "--no-backup", "--no-auto", "crossref", "--verbose", *flags],
                              cwd=directory, capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": ""})

    def test_nothing_is_passed_unless_asked_for(self):
        done = self.command("")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("tablekeep", done.stdout + done.stderr)

    def test_the_option_and_the_flag_reach_pandoc_and_the_flag_wins(self):
        done = self.command("pdfmd-options:\n  table-keep: 3\n")
        self.assertIn("tablekeep=3", done.stdout + done.stderr)
        done = self.command("pdfmd-options:\n  table-keep: 3\n", "--table-keep", "0")
        self.assertIn("tablekeep=0", done.stdout + done.stderr)
        self.assertNotIn("tablekeep=3", done.stdout + done.stderr)

    def test_a_bad_value_stops_the_run(self):
        done = self.command("pdfmd-options:\n  table-keep: many\n")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("table-keep must be a whole number", done.stdout + done.stderr)
        done = self.command("", "--table-keep", "x")
        self.assertNotEqual(done.returncode, 0)


if __name__ == "__main__":
    unittest.main()
