"""v3.31.49: one line break for every writer (entry 3el). `<br>` and the other spellings of a line break become the
target's own (pdfmd_lua/linebreak.lua); real builds through pdfmd."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

TABLE = "| a | b |\n|---|---|\n| one<br>two<br/>three<BR />four | x\\newline y |\n"


class Detect(unittest.TestCase):
    def test_the_filter_is_wanted_only_for_a_spelling_of_a_break(self):
        for text in ("a<br>b", "a<BR />b", "a\\newline b", "x\\linebreak[2]y", "#linebreak()", "<w:r><w:br/></w:r>", "\\crlf"):
            self.assertTrue(pdfmd.LINEBREAK_RE.search(text), text)
        for text in ("a line", "<b>bold</b>", "a\\nb", "<break>"):
            self.assertFalse(pdfmd.LINEBREAK_RE.search(text), text)

    def test_what_a_value_asks_for(self):
        every = list(pdfmd.LINEBREAK_KINDS)
        self.assertEqual(pdfmd.linebreak_value(None), ("cells", every))
        self.assertEqual(pdfmd.linebreak_value("auto"), ("cells", every))
        self.assertEqual(pdfmd.linebreak_value(True), ("all", every))
        self.assertEqual(pdfmd.linebreak_value("all"), ("all", every))
        self.assertEqual(pdfmd.linebreak_value(False), ("cells", []))
        self.assertEqual(pdfmd.linebreak_value(["typst", "html"]), ("all", ["html", "typst"]))
        self.assertEqual(pdfmd.linebreak_value("tex, word"), ("all", ["tex", "word"]))
        self.assertEqual(pdfmd.linebreak_value("off"), ("all", []))


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Build(unittest.TestCase):
    ALL = "linebreak: true"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def build(self, body: str, to: str = "tex", options: str = "", extra: tuple[str, ...] = ()) -> tuple[subprocess.CompletedProcess, Path]:
        front = f"pdfmd-options: {{{options}}}\n" if options else ""
        (self.root / "d.md").write_text(f"---\ntitle: T\n{front}---\n\n{body}", encoding="utf-8")
        out = self.root / f"out.{to}"
        out.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *extra, "--to", to, "-o", out.name, "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        return done, out

    def text(self, body: str, to: str = "tex", options: str = "", extra: tuple[str, ...] = ()) -> str:
        done, out = self.build(body, to, options, extra)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return " ".join(out.read_text(encoding="utf-8").split())

    def test_the_default_breaks_the_lines_of_a_table_cell_and_leaves_the_text_alone(self):
        tex = self.text(TABLE + "\nText<br>outside.\n")
        self.assertNotIn("onetwo", tex)
        self.assertIn("\\strut one}\\hbox{\\strut two}", tex)
        self.assertIn("Textoutside.", tex)

    def test_true_breaks_the_text_too(self):
        tex = self.text(TABLE + "\nText<br>outside.\n", options=self.ALL)
        self.assertIn("\\strut two}", tex)
        self.assertIn("Text\\\\ outside.", tex)

    def test_a_spelling_in_the_targets_own_language_stays_as_written(self):
        tex = self.text("a\\newline b, c<br>d\n", options=self.ALL)
        self.assertIn("a\\newline b, c\\\\ d", tex)
        html = self.text("a\\newline b, c<br>d\n", "html", self.ALL)
        self.assertIn("a<br /> b, c<br>d", html)

    def test_typst_and_word_get_their_own(self):
        self.assertIn("a \\ b, c \\ d", self.text("a\\newline b, c<br>d\n", "typ", self.ALL))
        done, out = self.build("a\\newline b, c<br>d\n", "docx", self.ALL)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(len(re.findall(r"<w:br\s*/>", archive.read("word/document.xml").decode("utf-8"))), 2)

    def test_the_families_are_chosen(self):
        body = "a\\newline b, c<br>d\n"
        tex = self.text(body, "typ", "linebreak: [tex]")
        self.assertIn("a \\ b", tex)
        self.assertNotIn("c \\ d", tex)                  # html is not a family that takes part: the <br> is dropped as before
        self.assertIn("cd", tex)

    def test_off_and_the_command_line(self):
        body = TABLE + "\nText<br>outside.\n"
        self.assertIn("onetwothreefour", self.text(body, options="linebreak: false"))
        self.assertIn("onetwothreefour", self.text(body, extra=("--no-linebreak",)))
        self.assertIn("Text\\\\ outside.", self.text(body, extra=("--linebreak",)))
        only_tex = self.text(body, extra=("--linebreak", "tex"))
        self.assertIn("onetwothreefour", only_tex)

    def test_a_word_that_is_not_a_family_is_said_and_ignored(self):
        done, _ = self.build("a<br>b\n", options="linebreak: [blah]")
        self.assertIn("not a line-break family", done.stdout + done.stderr)

    def test_the_markdown_writers_keep_what_was_written_unless_raw_html_is_off(self):
        self.assertIn("<br>", self.text("a<br>b\n", "markdown", self.ALL))        # kept (as a raw span)
        flat = self.text("a<br>b\n", "gfm", self.ALL)       # pdfmd's flat Markdown has no raw HTML: a hard break, not a dropped tag
        self.assertNotIn("<br>", flat)
        self.assertIn("a\\ b", flat)

    def test_a_paragraph_of_nothing_but_a_break_is_left_alone(self):
        tex = self.text("before\n\n<br>\n\nafter\n", options=self.ALL)
        self.assertNotIn("\\\\", tex.split("\\begin{document}")[-1].replace("\\maketitle", ""))

    def test_a_break_at_the_end_of_a_cell_leaves_no_empty_line(self):
        tex = self.text("| a | b |\n|---|---|\n| text<br> | <br>more |\n")
        self.assertNotIn("\\strut}", tex)
        self.assertNotIn("\\newline \\\\", tex)


if __name__ == "__main__":
    unittest.main()
