"""pdfmd --text-to-markdown: a .txt file read as Markdown through batchocr (1.2.5 or newer)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = Path.home() / "dev" / "py" / "batchocr" / "batchocr.py"
COMMAND = os.environ.get("PDFMD_BATCHOCR") or (f"{sys.executable} {CHECKOUT}" if CHECKOUT.is_file() else "")
TEXT = ("MY NOTES\n\n1. Intro\n\nSome text here that goes on for a while and then stops, wrapped by hand at about\n"
        "seventy characters so that the paragraph needs joining by the converter.\n\n- one\n- two\n")


@unittest.skipUnless(COMMAND, "needs batchocr 1.2.5 (set PDFMD_BATCHOCR)")
class TextInput(unittest.TestCase):
    def run_pdfmd(self, folder: Path, *arguments: str):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "n.txt", *arguments, "--no-stamp", "--no-backup"],
                              cwd=folder, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_BATCHOCR": COMMAND, "PDFMD_CONFIG": ""})

    def folder(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-text-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "n.txt").write_text(TEXT, encoding="utf-8")
        return directory

    def test_off_unless_asked(self):
        folder = self.folder()
        done = self.run_pdfmd(folder, "-o", "n.html")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((folder / "n.md").exists())

    def test_with_o_md_it_is_the_conversion_alone(self):
        folder = self.folder()
        done = self.run_pdfmd(folder, "--text-to-markdown", "-o", "out.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        text = (folder / "out.md").read_text(encoding="utf-8")
        self.assertIn("# MY NOTES", text)
        self.assertIn("- one", text)
        self.assertFalse((folder / "n.pdf").exists())

    def test_otherwise_the_markdown_is_kept_beside_and_built_and_never_overwritten(self):
        folder = self.folder()
        done = self.run_pdfmd(folder, "--text-to-markdown", "-o", "n.html")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((folder / "n.md").is_file())
        self.assertIn("<h1", (folder / "n.html").read_text(encoding="utf-8"))
        again = self.run_pdfmd(folder, "--text-to-markdown", "-o", "n.html")
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("exists already", again.stderr)

    def test_the_config_can_turn_it_on(self):
        folder = self.folder()
        (folder / "config.yaml").write_text("options:\n  text-to-markdown: paragraphs\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "n.txt", "-o", "out.md", "--no-stamp"], cwd=folder,
                              capture_output=True, text=True,
                              env={**os.environ, "PDFMD_BATCHOCR": COMMAND, "PDFMD_CONFIG": str(folder / "config.yaml")})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("# MY NOTES", (folder / "out.md").read_text(encoding="utf-8"))   # paragraphs only


if __name__ == "__main__":
    unittest.main()
