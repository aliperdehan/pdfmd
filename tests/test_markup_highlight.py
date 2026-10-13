"""v3.29.17: universal markup, the fifth kind: ==highlighted text==."""

from __future__ import annotations

import shutil
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
FILTER = ROOT / "pdfmd_lua" / "markup.lua"

SOURCE = ("Some ==marked text== here, ==one== and ==with *emph* inside==, ==end==. A lone == sign and a == b == c.\n\n"
          "`==code==` stays. ==multi\nline==\n")


def convert(writer: str, enabled: str = "highlight", text: str = SOURCE, *extra: str) -> tuple[str, str]:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--wrap=none", "--lua-filter", str(FILTER), "-M",
                           f"pdfmd-markup={enabled}", *extra], input=text, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout, done.stderr


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_html_gets_mark(self):
        out, _ = convert("html5")
        self.assertIn("<mark>marked text</mark>", out)
        self.assertIn("<mark>one</mark>", out)
        self.assertIn("<mark>with <em>emph</em> inside</mark>", out)
        self.assertIn("<mark>end</mark>.", out)                                   # a punctuation mark after the closer stays outside
        self.assertIn("<mark>multi line</mark>", out)
        self.assertIn("A lone == sign and a == b == c.", out)                     # not a pair around text
        self.assertIn("<code>==code==</code>", out)

    def test_latex_gets_the_macro(self):
        out, _ = convert("latex")
        self.assertIn("\\pdfmdhl{marked text}", out)
        self.assertIn("\\pdfmdhl{with \\emph{emph} inside}", out)
        self.assertNotIn("<mark>", out)

    def test_typst_gets_highlight(self):
        out, _ = convert("typst")
        self.assertIn("#highlight[marked text]", out)

    def test_gfm_gets_mark_and_pandoc_markdown_is_left_alone(self):
        out, _ = convert("gfm")
        self.assertIn("<mark>marked text</mark>", out)
        out, _ = convert("markdown")
        self.assertIn("==marked text==", out)

    def test_word_keeps_the_text_and_says_so_once(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "docx", "-o", "/dev/null" if sys.platform != "win32" else "NUL",
                               "--lua-filter", str(FILTER), "-M", "pdfmd-markup=highlight"], input=SOURCE, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr.count("highlighting is not applied to docx"), 1)

    def test_only_when_the_kind_is_on(self):
        out, _ = convert("html5", enabled="toc")
        self.assertIn("==marked text==", out)
        self.assertNotIn("<mark>", out)

    def test_pandoc_3_12_marks_keep_working_with_the_extension_on(self):
        done = subprocess.run([PANDOC, "-f", "markdown+mark", "-t", "latex", "--lua-filter", str(FILTER), "-M", "pdfmd-markup=highlight"],
                              input="A ==marked== word.\n", capture_output=True, text=True)
        if done.returncode != 0:
            self.skipTest("this Pandoc has no mark extension")
        self.assertIn("\\pdfmdhl{marked}", done.stdout)


class Header(unittest.TestCase):
    def test_the_latex_definition_is_in_the_one_header_file(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "d.md"
            doc.write_text("---\ntitle: T\npdfmd-options:\n  markup: [highlight, callouts]\n---\n\ntext\n", encoding="utf-8")
            with mock.patch.object(pdfmd, "cache_root", lambda: Path(folder) / "cache"):
                args = pdfmd.markup_header_args(doc, [])
            text = Path(args[1]).read_text(encoding="utf-8")
            self.assertIn("\\newcommand{\\pdfmdhl}[1]{\\hl{#1}}", text)
            self.assertIn("\\newtcolorbox{pdfmdcallout}", text)
            self.assertEqual(args.count("--include-in-header"), 1)
            doc.write_text("---\ntitle: T\npdfmd-options:\n  markup: [toc]\n---\n\ntext\n", encoding="utf-8")
            self.assertEqual(pdfmd.markup_header_args(doc, []), [])               # a kind that needs no LaTeX needs no file


if __name__ == "__main__":
    unittest.main()
