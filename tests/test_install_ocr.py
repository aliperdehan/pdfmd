"""`pdfmd --install batchocr` and the system programs batchocr needs (Tesseract, Poppler)."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class OcrToolsCase(unittest.TestCase):
    def test_every_manager_names_packages_for_both_tools_or_says_it_cannot(self):
        for manager, (command, packages, languages) in pdfmd.OCR_PACKAGE_MANAGERS.items():
            self.assertEqual(set(packages), {"tesseract", "poppler"}, manager)
            self.assertTrue(packages["tesseract"], manager)
            self.assertTrue(languages, manager)
            built = pdfmd.ocr_install_command(manager)
            self.assertEqual(built[-len(packages["tesseract"]) - len(packages["poppler"]):],
                             packages["tesseract"] + packages["poppler"], manager)

    def test_sudo_only_for_the_linux_managers_and_only_when_not_root(self):
        with mock.patch.object(pdfmd, "which", return_value="/usr/bin/sudo"), \
                mock.patch.object(os, "geteuid", create=True, return_value=1000):
            self.assertEqual(pdfmd.ocr_install_command("apt-get")[0], "sudo")
            self.assertEqual(pdfmd.ocr_install_command("brew")[0], "brew")
        with mock.patch.object(pdfmd, "which", return_value="/usr/bin/sudo"), \
                mock.patch.object(os, "geteuid", create=True, return_value=0):
            self.assertEqual(pdfmd.ocr_install_command("apt-get")[0], "apt-get")

    def test_nothing_is_run_without_a_terminal(self):
        out = io.StringIO()
        with mock.patch.object(pdfmd, "which", side_effect=lambda name: "/bin/brew" if name == "brew" else None), \
                mock.patch.object(pdfmd, "system_package_manager", return_value="brew"), \
                mock.patch.object(pdfmd.subprocess, "run") as run, \
                mock.patch.object(sys.stdin, "isatty", return_value=False), \
                contextlib.redirect_stdout(out):
            pdfmd.install_ocr_tools()
        run.assert_not_called()
        self.assertIn("brew install tesseract poppler", out.getvalue())

    def test_nothing_is_said_when_both_are_there(self):
        out = io.StringIO()
        with mock.patch.object(pdfmd, "which", return_value="/bin/x"), contextlib.redirect_stdout(out):
            pdfmd.install_ocr_tools()
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
