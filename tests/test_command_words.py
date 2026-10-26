"""`split_command`: a pager or editor typed by a person, as words. POSIX rules would eat the backslashes of a Windows path."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class SplitCommand(unittest.TestCase):
    def test_posix_rules_off_windows(self):
        with mock.patch.object(pdfmd.os, "name", "posix"):
            self.assertEqual(pdfmd.split_command("less -FRX"), ["less", "-FRX"])
            self.assertEqual(pdfmd.split_command("'my pager' --opt"), ["my pager", "--opt"])

    def test_windows_keeps_the_backslashes_and_drops_the_quotes(self):
        with mock.patch.object(pdfmd.os, "name", "nt"):
            self.assertEqual(pdfmd.split_command(r"C:\Tools\less.exe -FRX"), [r"C:\Tools\less.exe", "-FRX"])
            self.assertEqual(pdfmd.split_command(r'"C:\Program Files\Editor\ed.exe" --wait'), [r"C:\Program Files\Editor\ed.exe", "--wait"])
            self.assertEqual(pdfmd.split_command("code --wait"), ["code", "--wait"])

    def test_the_pager_and_the_editor_use_it(self):
        with mock.patch.object(pdfmd.os, "name", "nt"), mock.patch.dict(pdfmd.os.environ, {"PDFMD_PAGER": r"C:\Tools\less.exe -R"}):
            self.assertEqual(pdfmd.pager_command(), [r"C:\Tools\less.exe", "-R"])


if __name__ == "__main__":
    unittest.main()
