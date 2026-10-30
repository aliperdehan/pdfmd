"""v3.30.34: `pdfmd -` builds the Markdown on standard input like a file (`stdin.pdf`, `stdin.<ext>`, or `-o`)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(directory: str, text: str, *arguments: str, bare: bool = True) -> subprocess.CompletedProcess:
    path = Path(directory) / "empty-bin"
    path.mkdir(exist_ok=True)
    environment = {**os.environ, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": directory, "APPDATA": directory}
    if bare:                                       # nothing but Python: the built-in renderer (no Pandoc, no TeX)
        environment.update(PATH=str(path), PDFMD_CALIBRE="")
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "-", *arguments], cwd=directory, env=environment,
                          input=text, capture_output=True, text=True)


class Stdin(unittest.TestCase):
    def test_a_pipe_builds_stdin_pdf_and_leaves_nothing_behind(self):
        with tempfile.TemporaryDirectory() as directory:
            done = run(directory, "# Hi\n\nSome text.\n", "-e", "inkmd")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("stdin.md > stdin.pdf", done.stdout)
            self.assertTrue((Path(directory) / "stdin.pdf").read_bytes().startswith(b"%PDF-"))
            self.assertEqual(sorted(item.name for item in Path(directory).iterdir() if item.name.startswith(".")), [])

    def test_a_pipe_without_the_dash_is_not_read_and_the_error_names_the_dash(self):
        # decided 2026-10-27: plain `pdfmd` never reads standard input (a script's inherited pipe looks the same)
        with tempfile.TemporaryDirectory() as directory:
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py")], cwd=directory, input="# Hi\n", capture_output=True,
                                  text=True, env={**os.environ, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": directory, "APPDATA": directory})
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("No Markdown files found", done.stderr)
            self.assertIn("`pdfmd -`", done.stderr)
            self.assertEqual(sorted(item.name for item in Path(directory).iterdir()), [])

    def test_o_names_the_result(self):
        with tempfile.TemporaryDirectory() as directory:
            done = run(directory, "# Hi\n", "-e", "inkmd", "-o", "named.pdf")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertTrue((Path(directory) / "named.pdf").is_file())
            self.assertFalse((Path(directory) / "stdin.pdf").exists())

    def test_empty_input_is_refused_with_a_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            done = run(directory, "  \n", "-e", "inkmd")
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("standard input was empty", done.stdout + done.stderr)
            self.assertFalse((Path(directory) / "stdin.pdf").exists())

    def test_a_failed_build_still_removes_the_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            done = run(directory, "# Hi\n", "-e", "no-such-engine")
            self.assertNotEqual(done.returncode, 0)
            self.assertEqual(sorted(item.name for item in Path(directory).iterdir() if item.name.startswith(".pdfmd-stdin")), [])

    def test_the_markdown_of_a_folder_is_not_built_instead(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "other.md").write_text("# Other\n", encoding="utf-8")
            done = run(directory, "# From the pipe\n", "-e", "inkmd")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertTrue((Path(directory) / "stdin.pdf").is_file())
            self.assertFalse((Path(directory) / "other.pdf").exists())

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_to_html_writes_stdin_html_and_a_relative_picture_resolves(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "pic.png").write_bytes(bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6c0c40000000049454e44ae426082"))
            done = run(directory, "# Hi\n\n![p](pic.png)\n", "--to", "html", bare=False)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            html = (Path(directory) / "stdin.html").read_text(encoding="utf-8")
            self.assertIn("pic.png", html)
            self.assertNotIn("Could not fetch", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
