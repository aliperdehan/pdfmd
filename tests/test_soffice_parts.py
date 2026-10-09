"""Parts mode and `doc#section` build with every engine, the soffice route (Pandoc -> .docx -> LibreOffice) too."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOFFICE = shutil.which("soffice") or ("/Applications/LibreOffice.app/Contents/MacOS/soffice"
                                      if Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").exists() else None)


@unittest.skipUnless(shutil.which("pandoc") and SOFFICE and shutil.which("pdftotext"),
                     "needs Pandoc, LibreOffice and pdftotext")
class SofficeParts(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name).resolve()
        parts = self.root / "parts"
        parts.mkdir()
        (self.root / "report.md").write_text("---\ntitle: Report\npdfmd-options:\n  parts: auto\n---\n\nLead.\n",
                                             encoding="utf-8")
        (parts / "10-introduction.md").write_text("# Introduction\n\nIntro words.\n", encoding="utf-8")
        (parts / "20-methods.md").write_text("# Methods\n\nMethod words.\n\n## Sampling\n\nSampling words.\n",
                                             encoding="utf-8")

    def build(self, request, output):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), request, "-e", "soffice", "-o", output],
                              cwd=self.root, capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": ""})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return subprocess.run(["pdftotext", str(self.root / output), "-"], capture_output=True, text=True).stdout

    def test_the_whole_split_document(self):
        text = self.build("report", "full.pdf")
        for word in ("Intro words.", "Method words.", "Sampling words."):
            self.assertIn(word, text)

    def test_one_part_and_one_heading_inside_a_part(self):
        text = self.build("report#methods", "part.pdf")
        self.assertIn("Method words.", text)
        self.assertNotIn("Intro words.", text)
        text = self.build("report#sampling", "heading.pdf")
        self.assertIn("Sampling words.", text)
        self.assertNotIn("Method words.", text)


@unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
class NativeParts(unittest.TestCase):
    """The built-in renderer (no Pandoc on the PATH) joins the parts and cuts the section itself."""

    def build(self, request, output):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), request, "-o", output],
                              cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PATH": "/nonexistent", "PDFMD_CONFIG": ""})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return subprocess.run(["pdftotext", str(self.root / output), "-"], capture_output=True, text=True).stdout

    setUp = SofficeParts.setUp

    def test_the_whole_split_document_a_part_and_a_heading(self):
        self.addCleanup(self._directory.cleanup)
        text = self.build("report", "full.pdf")
        for word in ("Lead.", "Intro words.", "Method words.", "Sampling words."):
            self.assertIn(word, text)
        text = self.build("report#methods", "part.pdf")
        self.assertIn("Method words.", text)
        self.assertNotIn("Intro words.", text)
        text = self.build("report#sampling", "heading.pdf")
        self.assertIn("Sampling words.", text)
        self.assertNotIn("Method words.", text)
        self.assertEqual([item.name for item in self.root.iterdir() if item.name.startswith(".")], [])


if __name__ == "__main__":
    unittest.main()
