"""`pdfmd --doctor`: the one-page report, on a machine with everything missing and on this one."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def doctor(path: str, home: str, *extra: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PATH": path, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "",
                   "XDG_CONFIG_HOME": home, "XDG_CACHE_HOME": home, "XDG_DATA_HOME": home,
                   "LOCALAPPDATA": home, "APPDATA": home}
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--doctor", *extra], env=environment,
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

    def test_deep_builds_a_page_with_the_built_in_renderer_when_nothing_else_is_there(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty"
            empty.mkdir()
            result = doctor(str(empty), directory, "--deep")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Smoke test", result.stdout)
            self.assertRegex(result.stdout, r"(?m)^OK    (inkmd|md2pdf): built a PDF in ")

    def test_deep_alone_is_refused(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--deep"], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--deep goes with --doctor", done.stdout + done.stderr)

    def test_deep_says_why_an_engine_failed_and_stops_one_that_hangs(self):
        sys.path.insert(0, str(ROOT))
        import pdfmd
        failing = subprocess.CompletedProcess([], 1, "", "WARN  sample.md: typst failed (error: unknown font); no more engines to try.\n")
        with mock.patch.object(pdfmd.subprocess, "run", return_value=failing):
            self.assertEqual(pdfmd.deep_checks(["typst"]), [("typst", False, "error: unknown font")])
        with mock.patch.object(pdfmd.subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 1)):
            self.assertEqual(pdfmd.deep_checks(["typst"], timeout=1), [("typst", False, "no answer after 1 s")])


if __name__ == "__main__":
    unittest.main()
