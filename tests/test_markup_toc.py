"""v3.29.14: universal markup, the third kind: a table of contents where [TOC], [[_TOC_]], <!-- toc --> or a raw \\tableofcontents stands."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "pdfmd_lua" / "markup.lua"

SOURCE = "# One\n\ntext\n\n## Sub *emph*\n\ntext\n\n#### Too deep\n\n# Two\n\n"


def convert(marker: str, writer: str, enabled: str = "toc") -> str:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--lua-filter", str(FILTER), "-M", f"pdfmd-markup={enabled}"],
                          input=marker + "\n\n" + SOURCE, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    MARKERS = ("[TOC]", "[toc]", "[[_TOC_]]", "[[TOC]]", "<!-- toc -->", "<!--TOC-->", "\\tableofcontents")

    def test_every_spelling_makes_the_same_list_in_html(self):
        for marker in self.MARKERS:
            out = convert(marker, "html5")
            self.assertIn("<strong>Contents</strong>", out, marker)
            self.assertIn('<li><a href="#one">One</a>', out, marker)
            self.assertIn('<a href="#sub-emph">Sub <em>emph</em></a>', out, marker)
            self.assertNotIn("too-deep", out.split("<h1")[0], marker)               # deeper than level 3 is left out
            self.assertNotIn("[TOC]", out)

    def test_the_list_is_nested_by_level(self):
        out = convert("[TOC]", "markdown")
        self.assertRegex(out, r"-\s+\[One\]\(#one\)\n\s+-\s+\[Sub \*emph\*\]\(#sub-emph\)\n-\s+\[Two\]\(#two\)")   # (3.1 pads the bullets)

    def test_latex_keeps_its_own_command_once(self):
        for marker in ("[TOC]", "<!-- toc -->", "\\tableofcontents"):
            self.assertEqual(convert(marker, "latex").count("\\tableofcontents"), 1, marker)

    def test_typst_gets_an_outline(self):
        self.assertIn("#outline()", convert("[TOC]", "typst"))

    def test_word_gets_a_toc_field(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "o.docx"
            subprocess.run([PANDOC, "-f", "markdown", "-o", str(out), "--lua-filter", str(FILTER), "-M", "pdfmd-markup=toc"],
                           input="[TOC]\n\n" + SOURCE, capture_output=True, text=True, check=True)
            with zipfile.ZipFile(out) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn('TOC \\o "1-3" \\h \\z \\u', xml)

    def test_it_is_only_when_the_kind_is_on(self):
        out = convert("[TOC]", "html5", enabled="callouts")
        self.assertIn("[TOC]", out)
        self.assertNotIn("Contents", out)

    def test_a_marker_inside_a_sentence_is_text(self):
        out = convert("Put [TOC] here.", "html5")
        self.assertIn("Put [TOC] here.", out)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Build(unittest.TestCase):
    def build(self, *args: str) -> subprocess.CompletedProcess:
        root = Path(self._tmp.name)
        (root / "d.md").write_text("---\ntitle: T\npdfmd-options:\n  markup: toc\n---\n\n[TOC]\n\n" + SOURCE, encoding="utf-8")
        env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--no-stamp", *args], cwd=root, env=env,
                              capture_output=True, text=True, timeout=300)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    @unittest.skipUnless(shutil.which("lualatex") or shutil.which("xelatex") or shutil.which("pdflatex"), "needs a LaTeX engine")
    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_a_latex_pdf_has_its_contents_filled_in_one_build(self):
        engine = next(name for name in ("lualatex", "xelatex", "pdflatex") if shutil.which(name))
        for extra in ((), ("--no-cache",)):
            done = self.build("-e", engine, "-o", "d.pdf", *extra)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            text = subprocess.run(["pdftotext", str(Path(self._tmp.name) / "d.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            self.assertIn("Contents", text)
            self.assertRegex(text, r"Sub emph \. \. \.")                              # a leader and a page number: it is filled

    def test_the_markup_is_off_without_the_option(self):
        root = Path(self._tmp.name)
        (root / "d.md").write_text("---\ntitle: T\n---\n\n[TOC]\n\n" + SOURCE, encoding="utf-8")
        env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "html", "-s", "-o", "d.html", "--no-stamp"],
                              cwd=root, env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("[TOC]", (root / "d.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
