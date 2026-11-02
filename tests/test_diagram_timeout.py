"""`diagram-timeout` (v3.32.1): a diagram tool that takes too long is stopped with what it started; 0 draws nothing, a negative
number removes the limit; a document's `pdfmd-options` can name its own. The runner (pdfmd_lua/limited_run.py) is tested here on
its own, the filter around it in test_diagrams.py."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

RUNNER = ROOT / "pdfmd_lua" / "limited_run.py"


def run(seconds: float, *program: str, data: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RUNNER), str(seconds), *program], input=data, capture_output=True, timeout=60)


class Setting(unittest.TestCase):
    def test_the_value_as_seconds(self):
        self.assertEqual(pdfmd.DIAGRAM_TIMEOUT, 120)
        self.assertEqual(pdfmd.diagram_timeout_from(None), 120)
        self.assertEqual(pdfmd.diagram_timeout_from("words"), 120)
        self.assertEqual(pdfmd.diagram_timeout_from("45"), 45)
        self.assertEqual(pdfmd.diagram_timeout_from(0), 0)
        self.assertLess(pdfmd.diagram_timeout_from(-1), 0)

    def test_a_document_names_its_own_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "d.md"
            document.write_text("---\npdfmd-options:\n  diagram-timeout: 7\n---\n\nText.\n", encoding="utf-8")
            self.assertEqual(pdfmd.diagram_timeout_for(document, []), 7)
            other = Path(folder) / "e.md"
            other.write_text("Text.\n", encoding="utf-8")
            with mock.patch.object(pdfmd, "config_options", lambda *a, **k: {"diagram-timeout": 11}):
                self.assertEqual(pdfmd.diagram_timeout_for(other, []), 11)
            with mock.patch.object(pdfmd, "config_options", lambda *a, **k: {}):
                self.assertEqual(pdfmd.diagram_timeout_for(other, []), 120)


class Runner(unittest.TestCase):
    def test_the_output_comes_back_byte_for_byte(self):
        payload = bytes(range(256)) + b"\r\n\x00\xff\r\n"
        done = run(30, sys.executable, "-c",
                   "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())", data=payload)
        self.assertEqual((done.returncode, done.stdout), (0, payload))

    def test_the_exit_code_and_the_error_output_pass_through(self):
        done = run(30, sys.executable, "-c", "import sys; print('why', file=sys.stderr); sys.exit(3)")
        self.assertEqual(done.returncode, 3)
        self.assertIn(b"why", done.stderr)

    def test_a_run_over_the_limit_is_stopped_with_its_child(self):
        with tempfile.TemporaryDirectory() as folder:
            pid_file = Path(folder) / "child.pid"
            script = ("import subprocess, sys, time\n"
                      "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                      f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
                      "time.sleep(60)\n")
            started = time.monotonic()
            done = run(2, sys.executable, "-c", script)
            self.assertLess(time.monotonic() - started, 30)
            self.assertEqual(done.returncode, 124)
            self.assertEqual(done.stdout, b"PDFMD-DIAGRAM-TIMEOUT")
            self.assertIn(b"diagram-timeout", done.stderr)
            self.assertIn(b"2 s", done.stderr)
            if os.name != "nt":
                pid = int(pid_file.read_text())
                time.sleep(0.5)
                with self.assertRaises(OSError):                    # the child died with its parent
                    os.kill(pid, 0)

    def test_a_missing_program_is_127(self):
        done = run(5, "no-such-diagram-tool-anywhere")
        self.assertEqual(done.returncode, 127)


if __name__ == "__main__":
    unittest.main()
