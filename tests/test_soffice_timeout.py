"""`soffice-timeout`: a LibreOffice run that takes too long is stopped with its children and fails with the setting named; 0 turns
LibreOffice off, a negative number removes the limit; a document's `pdfmd-options` can name its own."""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


def stand_in(folder: Path, body: str) -> list[str]:
    """A command that behaves like soffice: the running Python on a script (one command on every system)."""
    script = folder / "fake_soffice.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(script)]


class Limit(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, pdfmd, "SOFFICE_TIMEOUT_NOW", None)

    def test_the_value_as_seconds(self):
        self.assertEqual(pdfmd.soffice_timeout_from(None), pdfmd.SOFFICE_TIMEOUT)
        self.assertEqual(pdfmd.soffice_timeout_from("words"), pdfmd.SOFFICE_TIMEOUT)
        self.assertEqual(pdfmd.soffice_timeout_from("45"), 45)
        self.assertEqual(pdfmd.soffice_timeout_from(0), 0)
        self.assertLess(pdfmd.soffice_timeout_from(-1), 0)
        self.assertEqual(pdfmd.SOFFICE_TIMEOUT, 300)

    def test_a_run_over_the_limit_is_stopped_with_its_child(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            command = stand_in(folder, """
                import subprocess, sys, time
                child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
                open(sys.argv[1], "w").write(str(child.pid))
                time.sleep(60)
            """) + [str(folder / "child.pid")]
            pdfmd.SOFFICE_TIMEOUT_NOW = 2
            started = time.monotonic()
            done = pdfmd.run_soffice(command)
            self.assertLess(time.monotonic() - started, 30)
            self.assertEqual(done.returncode, 124)
            self.assertIn("soffice-timeout", done.stderr)
            self.assertIn("2 s", done.stderr)
            if os.name != "nt":
                pid = int((folder / "child.pid").read_text())
                time.sleep(0.5)
                with self.assertRaises(OSError):                    # the child died with its parent
                    os.kill(pid, 0)

    def test_a_run_inside_the_limit_gives_its_output(self):
        with tempfile.TemporaryDirectory() as folder:
            command = stand_in(Path(folder), "import sys\nprint('out')\nprint('err', file=sys.stderr)\nsys.exit(3)\n")
            pdfmd.SOFFICE_TIMEOUT_NOW = 30
            done = pdfmd.run_soffice(command)
            self.assertEqual((done.returncode, done.stdout.strip(), done.stderr.strip()), (3, "out", "err"))

    def test_a_negative_number_is_no_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            command = stand_in(Path(folder), "import time\ntime.sleep(2)\nprint('late')\n")
            pdfmd.SOFFICE_TIMEOUT_NOW = -1
            done = pdfmd.run_soffice(command)
            self.assertEqual((done.returncode, done.stdout.strip()), (0, "late"))

    def test_zero_runs_nothing_and_counts_as_not_installed(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "ran"
            command = stand_in(Path(folder), f"open({str(marker)!r}, 'w').write('x')\n")
            pdfmd.SOFFICE_TIMEOUT_NOW = 0
            done = pdfmd.run_soffice(command)
            self.assertEqual(done.returncode, 1)
            self.assertIn("soffice-timeout", done.stderr)
            self.assertFalse(marker.exists())
            self.assertIsNone(pdfmd.resolve_soffice())

    def test_the_conversion_fails_with_the_setting_named_and_the_batch_goes_on(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            document = folder / "a.docx"
            document.write_bytes(b"x")
            script = folder / "slow.py"
            script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
            launcher = folder / ("soffice.cmd" if os.name == "nt" else "soffice")
            launcher.write_text(f'@"{sys.executable}" "{script}"\n' if os.name == "nt"
                                else f'#!/bin/sh\nexec "{sys.executable}" "{script}"\n', encoding="utf-8")
            launcher.chmod(0o755)
            pdfmd.SOFFICE_TIMEOUT_NOW = 1
            with mock.patch.object(pdfmd, "resolve_soffice", lambda: str(launcher)):
                ok, reason = pdfmd.run_soffice_convert(document, folder / "a.pdf", False)
            self.assertFalse(ok)
            self.assertIn("soffice-timeout", reason)

    def test_a_document_names_its_own_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "d.md"
            document.write_text("---\npdfmd-options:\n  soffice-timeout: 7\n---\n\nText.\n", encoding="utf-8")
            pdfmd.set_soffice_limit(document, [])
            self.assertEqual(pdfmd.soffice_limit(), 7)
            other = Path(folder) / "e.md"
            other.write_text("Text.\n", encoding="utf-8")
            with mock.patch.object(pdfmd, "config_options", lambda *a, **k: {"soffice-timeout": 11}):
                pdfmd.set_soffice_limit(other, [])
            self.assertEqual(pdfmd.soffice_limit(), 11)


if __name__ == "__main__":
    unittest.main()
