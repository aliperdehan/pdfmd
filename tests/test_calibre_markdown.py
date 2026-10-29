"""v3.29.1: with no Pandoc and Calibre installed, Calibre's own Markdown reader prints the document, ahead of the rough
built-in renderers (which stay its fallback); with Pandoc, `-e calibre` is still the HTML route."""

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


class Selection(unittest.TestCase):
    def test_calibre_is_a_native_engine_only_without_pandoc(self):
        with mock.patch.object(pdfmd, "which", lambda name: None), mock.patch.object(pdfmd, "resolve_calibre", lambda: "/c"):
            self.assertTrue(pdfmd.native_available("calibre"))
            self.assertTrue(pdfmd.is_native_engine("calibre"))
            self.assertEqual(pdfmd.available_native_engines()[0], "calibre")         # before the rough ones
        with mock.patch.object(pdfmd, "which", lambda name: "/p" if name == "pandoc" else None), \
                mock.patch.object(pdfmd, "resolve_calibre", lambda: "/c"):
            self.assertFalse(pdfmd.native_available("calibre"))
            self.assertFalse(pdfmd.is_native_engine("calibre"))
            self.assertNotIn("calibre", pdfmd.available_native_engines())
            self.assertIsNone(pdfmd.native_request("calibre", False, "--engine"))      # the HTML route's name

    def test_without_pandoc_both_the_automatic_chain_and_e_calibre_pick_it(self):
        with mock.patch.object(pdfmd, "which", lambda name: None), mock.patch.object(pdfmd, "resolve_calibre", lambda: "/c"), \
                mock.patch.object(pdfmd, "md2pdf_available", lambda: False), mock.patch.object(pdfmd, "inkmd_vendored", lambda: True):
            self.assertEqual(pdfmd.select_engines(None, False), ["calibre", "inkmd"])
            self.assertEqual(pdfmd.select_engines("calibre", False), ["calibre"])
            self.assertEqual(pdfmd.select_engines("ebook-convert", False), ["calibre"])
            self.assertEqual(pdfmd.select_engines("native", False), ["calibre", "inkmd"])

    def test_without_calibre_nothing_changes(self):
        with mock.patch.object(pdfmd, "which", lambda name: None), mock.patch.object(pdfmd, "resolve_calibre", lambda: None), \
                mock.patch.object(pdfmd, "md2pdf_available", lambda: False), mock.patch.object(pdfmd, "inkmd_vendored", lambda: True):
            self.assertEqual(pdfmd.select_engines(None, False), ["inkmd"])

    def test_calibre_goes_first_in_the_native_order(self):
        source = mock.Mock(has_footnotes=True, math=[], metadata={})
        self.assertEqual(pdfmd.native_order(["calibre", "md2pdf", "inkmd"], source), ["calibre", "md2pdf", "inkmd"])
        self.assertEqual(pdfmd.native_order(["md2pdf", "inkmd"], source)[0], "md2pdf")

    def test_the_override_names_the_file_or_none(self):
        with mock.patch.dict(os.environ, {"PDFMD_CALIBRE": ""}):
            self.assertIsNone(pdfmd.resolve_calibre())
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / "ebook-convert"
            binary.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PDFMD_CALIBRE": str(binary)}):
                self.assertEqual(pdfmd.resolve_calibre(), str(binary))
            with mock.patch.dict(os.environ, {"PDFMD_CALIBRE": str(binary) + "x"}):
                self.assertIsNone(pdfmd.resolve_calibre())


STUB = """#!{python}
import json, shutil, sys
from pathlib import Path
args = sys.argv[1:]
Path({log!r}).write_text(json.dumps({{"args": args, "text": Path(args[0]).read_text(encoding="utf-8")}}), encoding="utf-8")
if {fail!r}:
    sys.stderr.write("stub: refused")
    sys.exit(1)
Path(args[1]).write_bytes(b"%PDF-1.4 stand-in\\n")
"""


@unittest.skipIf(sys.platform == "win32", "needs a POSIX shell for the stand-in ebook-convert")
class Build(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calibre-md-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.log = self.directory / "call.json"
        (self.directory / "empty").mkdir()
        (self.directory / "d.md").write_text("---\ntitle: My Title\nauthor: [A. Writer, B. Other]\npapersize: a5\n---\n\n"
                                             "# Head\n\nText with $x^2$ and a note[^1].\n\n[^1]: The note.\n", encoding="utf-8")

    def run_pdfmd(self, *args: str, fail: bool = False, pandoc: bool = False) -> subprocess.CompletedProcess:
        script = self.directory / "ebook-convert"
        script.write_text(STUB.format(python=sys.executable, log=str(self.log), fail=fail), encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        path = os.environ["PATH"] if pandoc else str(self.directory / "empty")
        environment = {**os.environ, "PATH": path, "PDFMD_CALIBRE": str(script), "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *args, "--no-stamp"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory, env=environment)

    def test_without_pandoc_calibre_reads_the_markdown(self):
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("NATIVE  d.md via calibre", done.stdout)
        self.assertRegex(done.stdout, r"OK    d\.md > d\.pdf(?:  in [\d.:]+(?: s)?)?  \(calibre\)")
        self.assertIn("Calibre's Markdown reader", done.stdout)
        call = json.loads(self.log.read_text(encoding="utf-8"))
        args = call["args"]
        self.assertTrue(args[0].endswith("document.md"))
        self.assertNotIn("--max-levels", args)                                         # an option of the HTML reader
        self.assertEqual(args[args.index("--markdown-extensions") + 1], pdfmd.CALIBRE_MARKDOWN_EXTENSIONS)
        self.assertEqual(args[args.index("--title") + 1], "My Title")
        self.assertEqual(args[args.index("--authors") + 1], "A. Writer & B. Other")
        self.assertIn("--custom-size", args)                                            # A5 from papersize
        self.assertTrue(args[args.index("--custom-size") + 1].startswith("419.5"))
        self.assertIn("# My Title", call["text"])                                       # the title block, as Markdown
        self.assertNotIn("papersize", call["text"])                                     # the front matter is gone
        self.assertTrue((self.directory / "d.pdf").read_bytes().startswith(b"%PDF"))

    def test_the_formulas_are_text_and_it_says_so(self):
        done = self.run_pdfmd()
        self.assertIn("math expression(s) set as plain text", done.stdout + done.stderr)
        call = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertNotIn("$x^2$", call["text"])

    def test_a_calibre_that_fails_leaves_the_rough_renderer(self):
        done = self.run_pdfmd(fail=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("calibre failed", done.stdout)
        self.assertTrue((self.directory / "d.pdf").is_file())

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_with_pandoc_calibre_is_the_html_route_not_this(self):
        done = self.run_pdfmd("-e", "calibre", pandoc=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("NATIVE", done.stdout)
        call = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertTrue(call["args"][0].endswith("document.html"), call["args"][0])


if __name__ == "__main__":
    unittest.main()
