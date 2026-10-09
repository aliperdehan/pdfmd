"""Discovered Lua filters are noted, not blocked (v3.26.11)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402


class Rules(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-lua-")).resolve()
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        config = self.directory / "config"
        patcher = mock.patch.object(pdfmd, "config_root", lambda: config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.work = self.directory / "work"
        self.work.mkdir()
        self.filter = self.work / "doc.lua"
        self.filter.write_text("return {}\n", encoding="utf-8")
        self.document = self.work / "doc.md"

    def check(self, strict=False):
        out = StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            kept = pdfmd.check_lua_filters(self.document, [self.filter], strict)
        return kept, out.getvalue()

    def test_new_then_quiet_then_edited_then_quiet(self):
        kept, said = self.check()
        self.assertEqual(kept, [self.filter])
        self.assertIn("is new here", said)
        self.assertEqual(self.check(), ([self.filter], ""))
        self.filter.write_text("return {} -- edited\n", encoding="utf-8")
        kept, said = self.check()
        self.assertEqual(kept, [self.filter])
        self.assertIn("has changed since it last ran here", said)
        self.assertEqual(self.check(), ([self.filter], ""))

    def test_strict_skips_a_new_or_edited_filter_but_not_a_known_one(self):
        kept, said = self.check(strict=True)
        self.assertEqual(kept, [])
        self.assertIn("was not run (--strict)", said)
        self.check()                                           # run once: known now
        self.assertEqual(self.check(strict=True), ([self.filter], ""))
        self.filter.write_text("return {} -- edited\n", encoding="utf-8")
        self.assertEqual(self.check(strict=True)[0], [])

    def test_a_trusted_folder_is_never_noted_or_skipped_even_when_edited(self):
        with redirect_stdout(StringIO()):
            self.assertTrue(pdfmd.trust_lua([self.work]))
        self.assertEqual(self.check(strict=True), ([self.filter], ""))
        self.filter.write_text("return {} -- edited a lot\n", encoding="utf-8")
        self.assertEqual(self.check(strict=True), ([self.filter], ""))

    def test_a_trusted_file_is_trusted_as_it_is(self):
        with redirect_stdout(StringIO()):
            pdfmd.trust_lua([self.filter])
        self.assertEqual(self.check(strict=True), ([self.filter], ""))
        self.filter.write_text("return {} -- edited\n", encoding="utf-8")
        self.assertIn("changed", self.check()[1])

    def test_a_path_that_is_not_there_is_reported(self):
        err = StringIO()
        with redirect_stdout(StringIO()), redirect_stderr(err):
            self.assertFalse(pdfmd.trust_lua([self.work / "nope"]))
        self.assertIn("no such file or folder", err.getvalue())


@needs_pandoc(3, 1, 3)
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-lua-cli-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.directory / "config"),
                    "APPDATA": str(self.directory / "config")}
        self.env.pop("PDFMD_STRICT", None)
        (self.directory / "doc.md").write_text("---\ntitle: T\n---\n\nHi\n", encoding="utf-8")
        (self.directory / "doc.lua").write_text("function Para(p) return p end\n", encoding="utf-8")

    def run_pdfmd(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=self.env)

    def test_the_filter_always_runs_and_the_edit_is_noted_once(self):
        # the filter turns every paragraph into a shout, so we see whether it ran
        (self.directory / "doc.lua").write_text("function Para(p) return pandoc.Para{pandoc.Str('RAN')} end\n",
                                                encoding="utf-8")
        first = self.run_pdfmd("doc.md", "-t", "html")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("is new here", first.stdout)
        self.assertIn("RAN", (self.directory / "doc.html").read_text(encoding="utf-8"))
        self.assertNotIn("NOTE  doc.md: the Lua filter", self.run_pdfmd("doc.md", "-t", "html").stdout)
        (self.directory / "doc.lua").write_text("function Para(p) return pandoc.Para{pandoc.Str('RAN2')} end\n",
                                                encoding="utf-8")
        edited = self.run_pdfmd("doc.md", "-t", "html")
        self.assertIn("has changed since it last ran here", edited.stdout)
        self.assertIn("RAN2", (self.directory / "doc.html").read_text(encoding="utf-8"))

    def test_trust_lua_stops_the_notes_and_strict_then_runs_it(self):
        self.assertEqual(self.run_pdfmd("doc.md", "-t", "html", "--strict").returncode, 1)     # new: skipped, WARN
        trusted = self.run_pdfmd("--trust-lua", ".")
        self.assertEqual(trusted.returncode, 0, trusted.stdout + trusted.stderr)
        done = self.run_pdfmd("doc.md", "-t", "html", "--strict")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("Lua filter", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
