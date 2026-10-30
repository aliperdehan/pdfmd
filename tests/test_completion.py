"""`pdfmd --completion SHELL`: scripts generated from the command line itself."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class CompletionTests(unittest.TestCase):
    def test_every_shell_knows_the_flags_and_their_values(self):
        for shell in ("bash", "zsh", "fish"):
            script = pdfmd.completion_script(shell)
            for flag in ("doctor", "stop-at", "install", "completion", "check-fonts"):
                self.assertIn(flag, script, f"{shell}: {flag}")
        self.assertIn("markdown tex pdf", pdfmd.completion_script("bash"))
        self.assertIn("ocr:rus", pdfmd.completion_script("fish"))
        self.assertIn("fonts:arabic", pdfmd.completion_script("fish"))

    def test_the_scripts_parse_in_their_shells(self):
        for shell in ("bash", "zsh"):
            program = shutil.which(shell)
            if not program:
                continue
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"c.{shell}"
                path.write_bytes(pdfmd.completion_script(shell).encode("utf-8"))      # write_text would turn each newline into CRLF on Windows
                # by name, from its folder: a Windows path with backslashes means nothing to a POSIX shell (Git Bash)
                done = subprocess.run([program, "-n", path.name], capture_output=True, text=True, encoding="utf-8", cwd=directory)
                self.assertEqual(done.returncode, 0, f"{shell}: {done.stderr}")

    def test_the_command_prints_it(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--completion", "zsh"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.startswith("#compdef pdfmd"))

    def test_the_command_prints_it_with_unix_line_ends(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--completion", "bash"], capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn(b"\r", done.stdout)                  # CRLF in a shell script breaks it in Git Bash and WSL


if __name__ == "__main__":
    unittest.main()
