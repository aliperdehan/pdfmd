"""Without the pdfmd_lua package (a lone copy of pdfmd.py) the Lua filters of pdfmd do nothing; one WARN per run says so."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
ENGINES = [name for name in ("lualatex", "xelatex", "pdflatex", "tectonic", "typst") if shutil.which(name)]


class InProcess(unittest.TestCase):
    def setUp(self):
        pdfmd.PDFMD_LUA_WARNED.clear()
        self.addCleanup(pdfmd.PDFMD_LUA_WARNED.clear)
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-lua-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def test_a_missing_package_gives_a_no_op_filter_and_one_warn(self):
        with mock.patch.dict(sys.modules, {"pdfmd_lua": None}), contextlib.redirect_stderr(io.StringIO()) as seen:
            for _ in range(3):
                with pdfmd.lua_filter_file("table_width", "pdfmd-x-") as path:
                    self.assertEqual(path.read_text(encoding="utf-8"), "return {}\n")
                with pdfmd.csv_table_filter() as path:
                    self.assertEqual(path.read_text(encoding="utf-8"), "return {}\n")
            self.assertFalse(path.exists())                                    # the temporary filter is removed
        said = seen.getvalue()
        self.assertEqual(said.count("WARN"), 1, said)
        self.assertIn("the pdfmd_lua package is not installed beside pdfmd.py", said)
        self.assertIn("do nothing in this run", said)

    def test_a_missing_file_of_the_package_is_named(self):
        import pdfmd_lua
        with mock.patch.object(pdfmd_lua, "path", lambda name: None), contextlib.redirect_stderr(io.StringIO()) as seen:
            with pdfmd.lua_filter_file("table_width", "pdfmd-x-") as path:
                self.assertEqual(path.read_text(encoding="utf-8"), "return {}\n")
            with pdfmd.lua_filter_file("table_width", "pdfmd-x-"):
                pass
        self.assertEqual(seen.getvalue().count("WARN"), 1)
        self.assertIn("pdfmd_lua/table_width.lua is missing from the pdfmd_lua package", seen.getvalue())

    def test_a_present_package_says_nothing(self):
        with contextlib.redirect_stderr(io.StringIO()) as seen:
            with pdfmd.lua_filter_file("table_width", "pdfmd-x-") as path:
                self.assertTrue(path.name.endswith("table_width.lua"))
        self.assertEqual(seen.getvalue(), "")

    def test_a_feature_that_needs_a_filter_warns_instead_of_silently_doing_nothing(self):
        document = self.directory / "d.md"
        document.write_text("---\ntitle: T\n---\n\n::: noindent\nx\n:::\n", encoding="utf-8")
        with mock.patch.dict(sys.modules, {"pdfmd_lua": None}), contextlib.redirect_stderr(io.StringIO()) as seen:
            self.assertEqual(pdfmd.indent_filter_args(document), [])
            self.assertEqual(pdfmd.calc_filter_args(document, []), [])          # no calculator in it: nothing needed, nothing said
        self.assertEqual(seen.getvalue().count("WARN"), 1, seen.getvalue())
        plain = self.directory / "plain.md"
        plain.write_text("Text.\n", encoding="utf-8")
        pdfmd.PDFMD_LUA_WARNED.clear()
        with mock.patch.dict(sys.modules, {"pdfmd_lua": None}), contextlib.redirect_stderr(io.StringIO()) as seen:
            self.assertEqual(pdfmd.indent_filter_args(plain), [])
        self.assertEqual(seen.getvalue(), "")                                  # a document that needs none is not bothered


@unittest.skipUnless(PANDOC and ENGINES, "needs Pandoc and a PDF engine")
class LoneCopy(unittest.TestCase):
    def test_a_lone_pdfmd_py_builds_and_warns_once(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-lone-"))
        self.addCleanup(shutil.rmtree, directory, True)
        shutil.copy(ROOT / "pdfmd.py", directory / "pdfmd.py")
        (directory / "d.md").write_text("---\ntitle: T\n---\n\nHello.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
        # (an installed pdfmd -- `pip install .` in CI -- has pdfmd_lua on the path too, so it is hidden: None in sys.modules)
        program = ("import runpy, sys; sys.modules['pdfmd_lua'] = None; sys.argv = ['pdfmd.py', 'd.md', '-e', %r, '--no-backup', "
                   "'--no-stamp']; runpy.run_path('pdfmd.py', run_name='__main__')" % ENGINES[0])
        done = subprocess.run([sys.executable, "-c", program], cwd=directory, capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
        self.assertTrue((directory / "d.pdf").is_file(), done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertEqual(said.count("the pdfmd_lua package is not installed"), 1, said)
        self.assertRegex(said, r"WARN  lua: ")


if __name__ == "__main__":
    unittest.main()
