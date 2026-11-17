"""An optional GHC heap cap applies to Pandoc builds and their helper invocations."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402


class Values(unittest.TestCase):
    def test_size_validation(self):
        from pdfmd_engines.memory import normalise
        for value, expected in ((None, None), ("", None), ("2g", "2g"), (" 512M ", "512m"), ("1k", "1k")):
            self.assertEqual(normalise(value), expected)
        for value in (True, False, 0, "0m", "-2g", "2", "2gb", "1.5g", "2g -RTS", "many"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "size"):
                normalise(value)

    def test_commands_helpers_errors_and_scope(self):
        from pdfmd_engines import memory
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "a.md"
            source.write_text("---\npdfmd-options: {pandoc-memory: 512m}\n---\nText.\n", encoding="utf-8")
            result = subprocess.CompletedProcess([], 1, "", "pandoc: heap overflow")
            with mock.patch.object(memory.subprocess, "run", return_value=result) as run:
                with memory.scope():
                    memory.set_limit(source, [])
                    done = memory.run(["pandoc.exe", "--version"], capture_output=True)
                    self.assertEqual(run.call_args.args[0], ["pandoc.exe", "--version", "+RTS", "-M512m", "-RTS"])
                    self.assertIn("pdfmd-options.pandoc-memory", done.stderr)
                    memory.run(["typst", "--version"])
                    self.assertEqual(run.call_args.args[0], ["typst", "--version"])
                with mock.patch.object(pdfmd, "config_options", return_value={}):
                    memory.run(["pandoc", "--version"])
                    self.assertEqual(run.call_args.args[0], ["pandoc", "--version"])


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Builds(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-memory-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)

    def build(self, value, *args):
        path = self.root / "doc.md"
        path.write_text("---\npdfmd-options: {pandoc-memory: " + value + "}\n---\n\n" + "Body. " * 10000, encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), str(path), "-t", "html", "-s",
                               "--verbose", "--no-stamp", "--no-backup", *args], cwd=self.root,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"},
                              capture_output=True, text=True, encoding="utf-8")

    def test_cap_off_valid_and_invalid(self):
        off = self.build("null")
        self.assertEqual(off.returncode, 0, off.stdout + off.stderr)
        self.assertNotIn("-M512m", off.stdout + off.stderr)
        done = self.build("512m")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("+RTS -M512m -RTS", done.stdout + done.stderr)
        bad = self.build("banana")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("pdfmd-options.pandoc-memory", bad.stdout + bad.stderr)
        self.assertIn("size", bad.stdout + bad.stderr)

    def test_heap_overflow_names_the_setting(self):
        done = self.build("1m")
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("heap", (done.stdout + done.stderr).lower())
        self.assertIn("pdfmd-options.pandoc-memory", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
