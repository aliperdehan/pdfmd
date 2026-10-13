"""v3.29.21: `show-comments`: the <!-- comments --> of the text shown in the output (off by default; pdfmd's own markers stay invisible)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "pdfmd_lua" / "markup.lua"

SOURCE = """\
Before.

<!-- a block comment
over two lines -->

A paragraph with <!-- inline note --> text.

<!-- pdfmd: parts -->

<!-- pagebreak -->

<!-- toc -->

<!--  -->

Last para.
"""


def convert(writer: str, enabled: str = "comments") -> tuple[str, str]:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--lua-filter", str(FILTER), "-M", f"pdfmd-markup={enabled}"],
                          input=SOURCE, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout, done.stderr


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_html_gets_a_comment_box_and_the_markers_stay(self):
        out, _ = convert("html5")
        self.assertIn('<div class="callout callout-comment">', out)
        self.assertIn("a block comment over two lines", out)
        self.assertIn("<em>[comment: inline note]</em>", out)
        for marker in ("<!-- pdfmd: parts -->", "<!-- pagebreak -->", "<!-- toc -->"):
            self.assertIn(marker, out)                                            # untouched
        self.assertEqual(out.count('callout-comment"'), 1)                       # (the empty comment is nothing)

    def test_latex_and_typst_get_the_box(self):
        out, _ = convert("latex")
        self.assertIn("\\begin{pdfmdcallout}{pdfmd-comment}", out)
        out, _ = convert("typst")
        self.assertIn('rgb("#6E7781")', out)

    def test_word_gets_real_comments_anchored_on_the_next_paragraph(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "o.docx"
            subprocess.run([PANDOC, "-f", "markdown", "-o", str(target), "--lua-filter", str(FILTER), "-M", "pdfmd-markup=comments"],
                           input=SOURCE, capture_output=True, text=True, check=True)
            with zipfile.ZipFile(target) as archive:
                comments = archive.read("word/comments.xml").decode("utf-8")
                body = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("a block comment", comments)
            self.assertIn("inline note", comments)
            self.assertEqual(body.count("commentRangeStart"), 2)

    def test_the_markdown_family_keeps_the_comment_as_it_is(self):
        out, _ = convert("gfm")
        self.assertIn("<!-- a block comment", out)

    def test_open_document_drops_them_with_a_note_once(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "odt", "-o", "/dev/null" if sys.platform != "win32" else "NUL",
                               "--lua-filter", str(FILTER), "-M", "pdfmd-markup=comments"], input=SOURCE, capture_output=True, text=True)
        self.assertEqual(done.stderr.count("comments are not shown in odt"), 1)

    def test_not_unless_asked(self):
        out, _ = convert("html5", enabled="callouts")
        self.assertNotIn("callout-comment", out)
        self.assertIn("a block comment", out)                                      # the raw comment, as Pandoc writes it


class Option(unittest.TestCase):
    def test_off_by_default_and_not_part_of_markup_true(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "d.md"
            doc.write_text("---\ntitle: T\npdfmd-options:\n  markup: true\n---\n\ntext\n", encoding="utf-8")
            self.assertFalse(pdfmd.show_comments_on(doc, []))
            self.assertNotIn("comments", pdfmd.markup_kinds(doc, []))

    def test_the_option_the_flag_and_the_off_switch(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "d.md"
            doc.write_text("---\ntitle: T\npdfmd-options:\n  show-comments: true\n---\n\ntext\n", encoding="utf-8")
            try:
                self.assertEqual(pdfmd.markup_kinds(doc, []), ["comments"])
                pdfmd.SHOW_COMMENTS_CLI["on"] = False
                self.assertEqual(pdfmd.markup_kinds(doc, []), [])
                doc.write_text("---\ntitle: T\n---\n\ntext\n", encoding="utf-8")
                pdfmd.SHOW_COMMENTS_CLI["on"] = True
                self.assertEqual(pdfmd.markup_kinds(doc, []), ["comments"])
            finally:
                pdfmd.SHOW_COMMENTS_CLI["on"] = None

    def test_the_latex_box_is_defined_once_for_both_kinds(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "d.md"
            doc.write_text("---\ntitle: T\npdfmd-options:\n  show-comments: true\n  markup: callouts\n---\n\ntext\n", encoding="utf-8")
            with mock.patch.object(pdfmd, "cache_root", lambda: Path(folder) / "cache"):
                args = pdfmd.markup_header_args(doc, [])
            self.assertEqual(Path(args[1]).read_text(encoding="utf-8").count("\\newtcolorbox{pdfmdcallout}"), 1)
            self.assertIn("pdfmd-comment", Path(args[1]).read_text(encoding="utf-8"))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Build(unittest.TestCase):
    def test_the_flag_shows_a_comment_in_a_latex_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "d.md").write_text("---\ntitle: T\n---\n\nText.\n\n<!-- remember this -->\n\nMore.\n", encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            command = [sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "latex", "-o", "d.tex", "--no-stamp"]
            done = subprocess.run([*command, "--show-comments"], cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("remember this", (root / "d.tex").read_text(encoding="utf-8"))
            done = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertNotIn("remember this", (root / "d.tex").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
