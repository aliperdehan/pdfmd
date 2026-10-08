"""`pdfmd --doctor`: the one-page report, on a machine with everything missing and on this one."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def doctor(path: str, home: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PATH": path, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "",
                   "XDG_CONFIG_HOME": home, "XDG_CACHE_HOME": home, "XDG_DATA_HOME": home,
                   "LOCALAPPDATA": home, "APPDATA": home}
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--doctor"], env=environment,
                          capture_output=True, text=True)


class DoctorTests(unittest.TestCase):
    def test_with_nothing_on_path_it_names_what_to_install(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty"
            empty.mkdir()
            result = doctor(str(empty), directory)
            text = result.stdout
            self.assertIn("MISS  pandoc", text)
            self.assertIn("pdfmd --install pandoc", text)
            self.assertIn("MISS  tesseract", text)
            self.assertIn("thing(s) to fix", text)
            self.assertEqual(result.returncode, 0, result.stderr)   # a PDF can still be made

    def test_the_sections_are_there(self):
        with tempfile.TemporaryDirectory() as directory:
            text = doctor(os.environ.get("PATH", ""), directory).stdout
            for heading in ("Markdown to PDF:", "Fonts and scripts:", "Reading PDFs (PDF to Markdown):",
                            "Settings and cache:"):
                self.assertIn(heading, text)


if __name__ == "__main__":
    unittest.main()
