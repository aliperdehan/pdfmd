"""v3.31.46: a hand-typed caption next to a table (`**Table 1: Results**`) becomes the table's caption (entry 3dy).
Real builds to LaTeX through pdfmd; the finished `\\caption{...}` lines are what is read back."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
from pdfmd_tables.captions import label_words  # noqa: E402

TABLE = "| a | b |\n|---|---|\n| 1 | 2 |\n"


class Words(unittest.TestCase):
    def test_english_is_always_there_and_the_language_and_the_setting_add(self):
        self.assertEqual(label_words(None), ["Table"])
        self.assertEqual(label_words("ru-RU"), ["Table", "Таблица"])
        self.assertEqual(label_words("de_DE", ["Tab.", " ", "Table"]), ["Table", "Tabelle", "Tab."])
        self.assertEqual(label_words("xx"), ["Table"])


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Captions(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def build(self, body: str, options: str = "", head: str = "", name: str = "d.md"):
        front = "title: T\n" + head + (f"pdfmd-options: {{{options}}}\n" if options else "")
        (self.root / name).write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, "--to", "tex", "-o", "out.tex", "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        tex = (self.root / "out.tex").read_text(encoding="utf-8") if (self.root / "out.tex").exists() else ""
        return done, tex

    def captions(self, tex: str) -> list[str]:
        return [" ".join(found.split()) for found in re.findall(r"\\caption\{(.*?)\}(?:\\label\{[^}]*\})?\\tabularnewline", tex, re.DOTALL)]

    def test_the_default_changes_nothing_and_says_how_many_lines_would_have_been_captions(self):
        done, tex = self.build(f"**Table 1: Results**\n\n{TABLE}\ntext\n\n{TABLE}\n**Table 2: Below**\n\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.captions(tex), [])
        self.assertIn("\\textbf{Table 1: Results}", tex)
        self.assertRegex(done.stdout + done.stderr, r"NOTE  table-captions: 2 lines")
        self.assertIn("table-captions: on", done.stdout + done.stderr)

    def test_off_is_silent(self):
        done, tex = self.build(f"**Table 1: Results**\n\n{TABLE}", "table-captions: off")
        self.assertNotIn("NOTE  table-captions", done.stdout + done.stderr)
        self.assertEqual(self.captions(tex), [])

    def test_on_makes_the_caption_above_or_below_cuts_the_label_and_keeps_the_markup_and_the_id(self):
        body = (f"**Table 1: Results of $x^2$ at *low* pH** {{#tbl:res}}\n\n{TABLE}\ntext\n\n{TABLE}\n**Table 2. Below**\n\n")
        done, tex = self.build(body, "table-captions: on")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.captions(tex), [r"Results of \(x^2\) at \emph{low} pH", "Below"])
        self.assertIn(r"\label{tbl:res}", tex)
        self.assertNotIn("NOTE  table-captions", done.stdout + done.stderr)

    def test_the_label_can_stay(self):
        _, tex = self.build(f"**Table 1: Results**\n\n{TABLE}", "table-captions: on, table-caption-label: keep")
        self.assertEqual(self.captions(tex), ["Table 1: Results"])

    def test_what_is_not_a_caption_is_left_alone(self):
        body = (f"**Tables are nice** and **more**\n\n{TABLE}\nA paragraph.\n\n**Table 3**\n\nB paragraph.\n\n"
                f"**Table 4: Something between**\n\nA paragraph.\n\n{TABLE}\n**Notes on the above**\n\n")
        done, tex = self.build(body, "table-captions: on")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.captions(tex), [])

    def test_a_table_with_a_caption_keeps_it_and_an_above_line_wins_over_a_below_one(self):
        done, tex = self.build(f"**Table 1: Mine**\n\n{TABLE}\nTable: Theirs\n\n", "table-captions: on")
        self.assertEqual(self.captions(tex), ["Theirs"])
        done, tex = self.build(f"**Table 1: Above**\n\n{TABLE}\n**Table 2: Below**\n\n", "table-captions: on", name="e.md")
        self.assertEqual(self.captions(tex), ["Above"])
        self.assertIn("\\textbf{Table 2: Below}", tex)

    def test_the_number_of_blank_lines_does_not_matter_but_a_table_must_start_its_own_block(self):
        body = f"**Table 1: Three blank lines**\n\n\n\n{TABLE}\n**Table 2: A soft\nbreak inside**\n\n{TABLE}\n**Table 3: Touching**\n{TABLE}"
        done, tex = self.build(body, "table-captions: on")
        self.assertEqual(self.captions(tex), ["Three blank lines", "A soft break inside"])
        self.assertIn("Table 3: Touching", tex)                 # Pandoc read the touching table as text, so there is no table

    def test_the_label_words_follow_the_language_and_the_setting(self):
        done, tex = self.build(f"**Таблица 1: Итоги**\n\n{TABLE}\n**Tbl 2: Extra**\n\n{TABLE}", "table-captions: on, table-caption-words: Tbl",
                               head="lang: ru\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.captions(tex), ["Итоги", "Extra"])
        done, tex = self.build(f"**Таблица 1: Итоги**\n\n{TABLE}", "table-captions: on", name="e.md")          # no lang: not a label
        self.assertEqual(self.captions(tex), [])

    def test_without_a_label_word_needed_any_bold_line_is_a_caption(self):
        body = f"**Results of the run**\n\n{TABLE}\n**Table 2: With label**\n\n{TABLE}\n**Bold** and more\n\n{TABLE}"
        _, tex = self.build(body, "table-captions: on, table-caption-need-label: off")
        self.assertEqual(self.captions(tex), ["Results of the run", "With label"])
        done, tex = self.build(body, "table-captions: on", name="e.md")
        self.assertEqual(self.captions(tex), ["With label"])
        done, _ = self.build(body, "table-captions: note, table-caption-need-label: off", name="f.md")
        self.assertIn("NOTE  table-captions: 2 lines", done.stdout + done.stderr)

    def test_a_short_colon_line_is_a_caption_under_gfm_when_asked(self):
        body = f": Results\n\n{TABLE}\n: Too many words here\n\n{TABLE}"
        _, tex = self.build(body, "table-captions: on, table-caption-colon-words: 2, reader: gfm")
        self.assertEqual(self.captions(tex), ["Results"])
        self.assertIn(": Too many words here", tex)
        _, tex = self.build(body, "table-captions: on, reader: gfm", name="e.md")
        self.assertEqual(self.captions(tex), [])

    def test_the_bold_line_works_the_same_under_gfm_and_pandoc_markdown(self):
        body = f"**Table 1: Results** {{#tbl:res}}\n\n{TABLE}\n**Table 2. Below**\n\n"
        for reader in ("gfm", "markdown"):
            done, tex = self.build(body, f"table-captions: on, reader: {reader}", name=f"{reader}.md")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(self.captions(tex), ["Results"], reader)
            self.assertIn(r"\label{tbl:res}", tex, reader)

    def test_a_bad_setting_is_said(self):
        done, _ = self.build(f"**Table 1: R**\n\n{TABLE}", "table-captions: sometimes")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("table-captions", done.stderr)
        done, _ = self.build(f"**Table 1: R**\n\n{TABLE}", "table-caption-colon-words: many", name="e.md")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("table-caption-colon-words", done.stderr)

    def test_a_document_without_such_a_line_gets_no_filter(self):
        plain = self.root / "plain.md"
        plain.write_text("---\ntitle: T\n---\n\n**Notes**\n\n" + TABLE, encoding="utf-8")
        self.assertEqual(pdfmd.table_caption_args(plain, []), [])
        plain.write_text("---\ntitle: T\n---\n\n**Table 1: R**\n\n" + TABLE, encoding="utf-8")
        self.assertIn("pdfmd-table-captions=note", pdfmd.table_caption_args(plain, []))


if __name__ == "__main__":
    unittest.main()
