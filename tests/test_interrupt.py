"""Ctrl-C ends the command with one line and status 130, not a traceback (v3.30.14)."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402


class Interrupt(unittest.TestCase):
    def test_a_keyboard_interrupt_is_one_line_and_status_130(self):
        error = io.StringIO()
        with mock.patch.object(pdfmd, "run_main", side_effect=KeyboardInterrupt), redirect_stderr(error):
            with self.assertRaises(SystemExit) as caught:
                pdfmd.main()
        self.assertEqual(caught.exception.code, 130)
        self.assertEqual(error.getvalue().strip(), "Interrupted (Ctrl-C).")


if __name__ == "__main__":
    unittest.main()
