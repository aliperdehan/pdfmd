"""A Mermaid diagram on Windows, where `mmdc` is a command script (`mmdc.cmd`, as `npm install -g` writes it): the Lua filter
starts it through the command interpreter, since a program started by its bare name has to be an .exe."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from pandoc_support import needs_pandoc  # noqa: E402

# arguments of the call: -i in.mmd -o out.svg ...; the stand-in writes a picture to the fourth (they arrive in quotes: %~4)
SHIM = ('@echo off\r\necho ran>> "%STUB_LOG%"\r\n'
        'echo ^<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"^>^</svg^>> "%~4"\r\n')


@unittest.skipUnless(sys.platform == "win32" and shutil.which("pandoc"), "needs Windows, where a tool can be a .cmd, and Pandoc")
class MermaidShim(unittest.TestCase):
    def test_a_command_script_draws_the_diagram(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "stubs").mkdir()
            (folder / "stubs" / "mmdc.cmd").write_bytes(SHIM.encode("ascii"))
            (folder / "doc.md").write_text("# D\n\n```mermaid\ngraph LR; A --> B\n```\n", encoding="utf-8")
            path = os.pathsep.join([str(folder / "stubs"), os.path.dirname(shutil.which("pandoc")),
                                    os.path.dirname(sys.executable), os.environ.get("SystemRoot", r"C:\Windows") + r"\System32"])
            environment = {**os.environ, "PATH": path, "STUB_LOG": str(folder / "ran.log"), "PDFMD_CONFIG": "",
                           "PDFMD_NO_PROMPT": "1", "XDG_CACHE_HOME": str(folder / "cache"), "LOCALAPPDATA": str(folder / "cache"),
                           "XDG_CONFIG_HOME": str(folder / "config"), "APPDATA": str(folder / "config")}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-t", "html", "-o", "doc.html"],
                                  capture_output=True, text=True, encoding="utf-8", cwd=folder, env=environment)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("data:image/svg+xml;base64,", (folder / "doc.html").read_text(encoding="utf-8"))
            self.assertNotIn("WARN", done.stdout + done.stderr)
            self.assertIn("ran", (folder / "ran.log").read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()
