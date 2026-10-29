"""v3.29.1: a browser prints a Markdown document (`-e edge`, `-e chrome`, `-e chromium`, `-e brave`, `-e browser`): Pandoc writes a
self-contained HTML page and the browser, headless, prints it with the page the document asks for."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")


class Selection(unittest.TestCase):
    def test_the_browsers_are_engines_only_when_named_and_have_aliases_and_a_family_word(self):
        self.assertEqual(pdfmd.BROWSER_ENGINES, ("chrome", "chromium", "edge", "brave"))
        self.assertEqual(pdfmd.ENGINE_GROUPS["browser"], pdfmd.BROWSER_ENGINES)
        for name in pdfmd.BROWSER_ENGINES:
            self.assertNotIn(name, pdfmd.PDF_ENGINES)                                # never in the automatic chain
        self.assertEqual(pdfmd.ENGINE_ALIASES["msedge"], "edge")
        self.assertEqual(pdfmd.ENGINE_ALIASES["google-chrome"], "chrome")

    def test_a_browser_is_found_by_pdfmd_direct(self):
        with mock.patch("pdfmd_direct.find_browser", lambda name, which=None: f"/apps/{name}" if name == "edge" else None):
            self.assertEqual(pdfmd.engine_executable("edge"), "/apps/edge")
            self.assertIsNone(pdfmd.engine_executable("brave"))

    def test_e_edge_and_the_family_word_select_what_is_installed(self):
        installed = {"edge": "/apps/edge", "brave": "/apps/brave"}
        with mock.patch.object(pdfmd, "engine_executable", lambda engine: installed.get(engine) or (
                "/usr/bin/pandoc" if engine == "pandoc" else None)), \
                mock.patch.object(pdfmd, "which", lambda name: "/usr/bin/pandoc" if name == "pandoc" else None), \
                mock.patch.object(pdfmd, "native_request", lambda *a, **k: None):
            self.assertEqual(pdfmd.select_engines("edge", False), ["edge"])
            self.assertEqual(pdfmd.select_engines("browser", False), ["edge", "brave"])
            self.assertEqual(pdfmd.select_engines("edge,brave", False), ["edge", "brave"])

    def test_the_page_is_the_documents_as_css(self):
        with tempfile.TemporaryDirectory() as folder:
            md = Path(folder) / "d.md"
            md.write_text("---\ntitle: T\npapersize: a5\ngeometry: margin=2cm\n---\n\nText.\n", encoding="utf-8")
            css = pdfmd.browser_page_css(md, [], [])
            self.assertIn("@page { size: 419.5", css)                                  # A5 in points
            self.assertIn("margin: 56.7pt 56.7pt 56.7pt 56.7pt", css)


STUB = """#!{python}
import json, sys
from pathlib import Path
args = sys.argv[1:]
produced = next(item.split("=", 1)[1] for item in args if item.startswith("--print-to-pdf="))
page = Path(args[-1].replace("file://", ""))
Path({log!r}).write_text(json.dumps({{"args": args, "html": page.read_text(encoding="utf-8")}}), encoding="utf-8")
Path(produced).write_bytes(b"%PDF-1.4 stand-in\\n")
"""


@unittest.skipUnless(PANDOC and sys.platform != "win32", "needs Pandoc and a POSIX shell for the stand-in browser")
class Build(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-browser-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.log = self.directory / "browser.json"
        (self.directory / "d.md").write_text("---\ntitle: T\npapersize: a5\n---\n\n# H\n\nMath $x^2$ and a table\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
                                             encoding="utf-8")
        script = self.directory / "chrome"
        script.write_text(STUB.format(python=sys.executable, log=str(self.log)), encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

    def run_pdfmd(self, *args: str) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PDFMD_NO_PROMPT": "1", "PDFMD_BROWSER": str(self.directory / "chrome")}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *args, "--no-stamp"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory, env=environment)

    def test_the_page_pandoc_writes_is_printed_with_the_documents_paper_and_the_print_style(self):
        done = self.run_pdfmd("-e", "chrome")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"OK    d\.md > d\.pdf(?:  in [\d.:]+(?: s)?)?  \(chrome\)")
        self.assertTrue((self.directory / "d.pdf").read_bytes().startswith(b"%PDF"))
        call = json.loads(self.log.read_text(encoding="utf-8"))
        html = call["html"]
        self.assertIn("<math", html)                                                 # MathML: a browser draws it itself
        self.assertIn("@page { size: 419.5", html)                                   # A5
        self.assertIn("max-width: none", html)                                       # Pandoc's screen column, undone
        self.assertIn("table { display: table;", html)
        self.assertIn("--headless=new", call["args"])
        self.assertIn("--no-pdf-header-footer", call["args"])

    def test_a_browser_that_writes_nothing_is_an_engine_that_failed(self):
        script = self.directory / "chrome"
        script.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
        done = self.run_pdfmd("-e", "chrome")
        self.assertNotEqual(done.returncode, 0)
        self.assertFalse((self.directory / "d.pdf").exists())

    def test_without_e_a_browser_is_never_used(self):
        done = self.run_pdfmd("--to", "html", "-o", "d.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
