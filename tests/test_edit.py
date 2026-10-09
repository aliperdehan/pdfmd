"""`pdfmd --edit`, the small full-screen editor: driven with scripted keys through prompt_toolkit's pipe input."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd_edit  # noqa: E402

CTRL = {"S": "\x13", "B": "\x02", "X": "\x18", "G": "\x07", "W": "\x17", "K": "\x0b", "U": "\x15", "Z": "\x1a"}


class Helpers(unittest.TestCase):
    def test_find_wraps_and_is_case_blind_unless_the_needle_has_a_capital(self):
        text = "alpha Beta alpha"
        self.assertEqual(pdfmd_edit.find_from(text, "alpha", 1), 11)
        self.assertEqual(pdfmd_edit.find_from(text, "alpha", 12), 0)          # wrapped
        self.assertEqual(pdfmd_edit.find_from(text, "beta", 0), 6)
        self.assertIsNone(pdfmd_edit.find_from(text, "BETA", 0))
        self.assertIsNone(pdfmd_edit.find_from(text, "", 0))

    def test_save_replaces_the_file_whole_and_leaves_no_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "a.md"
            target.write_text("old", encoding="utf-8")
            pdfmd_edit.save_text(target, "new\nline\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "new\nline\n")
            self.assertEqual([item.name for item in Path(folder).iterdir()], ["a.md"])


@unittest.skipUnless(pdfmd_edit.available(), "prompt_toolkit is not installed")
class Editing(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "doc.md"
        self.path.write_text("# T\n\nline two\nline three\n", encoding="utf-8")
        self.built: list[str] = []

    def drive(self, keys: str, build=True) -> int:
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        def make(path: Path):
            self.built.append(path.read_text(encoding="utf-8"))
            return True, "OK    doc.md", path.with_suffix(".pdf")
        with create_pipe_input() as pipe:
            pipe.send_text(keys)
            return pdfmd_edit.run(self.path, build=make if build else None, opener=lambda target: None,
                                  input=pipe, output=DummyOutput())

    def test_go_to_line_type_find_save_and_build(self):
        status = self.drive(CTRL["G"] + "3\r" + "XX" + CTRL["W"] + "three\r" + "!" + CTRL["S"] + CTRL["B"] + CTRL["X"])
        self.assertEqual(status, 0)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "# T\n\nXXline two\nline !three\n")
        self.assertEqual(self.built, ["# T\n\nXXline two\nline !three\n"])

    def test_build_saves_first(self):
        self.drive("abc" + CTRL["B"] + CTRL["X"])
        self.assertTrue(self.path.read_text(encoding="utf-8").startswith("abc# T"))
        self.assertEqual(len(self.built), 1)

    def test_leaving_with_unsaved_changes_asks_once(self):
        self.drive("zzz" + CTRL["X"] + CTRL["X"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "# T\n\nline two\nline three\n")      # not saved

    def test_cut_and_paste_a_line(self):
        self.drive(CTRL["G"] + "3\r" + CTRL["K"] + CTRL["G"] + "1\r" + CTRL["U"] + CTRL["S"] + CTRL["X"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "line two\n# T\n\nline three\n")

    def test_a_new_file_is_made_on_the_first_save(self):
        self.path = Path(self.folder.name) / "new.md"
        self.drive("hello" + CTRL["S"] + CTRL["X"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "hello")


class CommandLine(unittest.TestCase):
    @unittest.skipIf(pdfmd_edit.available(), "prompt_toolkit is installed")
    def test_without_prompt_toolkit_it_says_how_to_get_it(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--edit"], capture_output=True, text=True,
                              env={**os.environ, "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"]})
        self.assertEqual(done.returncode, 1)
        self.assertIn("--install tui", done.stderr)


if __name__ == "__main__":
    unittest.main()
