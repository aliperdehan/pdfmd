"""v3.31.47: an ASCII table with no `+` at its column boundaries (what chat models write for "a plain-text table")
is read as a pipe table (entry 3el). The pure function first, then real builds to LaTeX through pdfmd."""

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

from pdfmd_tables.ascii import repair_ascii_tables  # noqa: E402

RULE = "+" + "-" * 40 + "+"
SLOPPY = f"""{RULE}
| Model Name         | Origin            |
{RULE}
| Replacement Model  | Africa;           |
| (Out of Africa II) | ~200-100 ka       |
{RULE}
| Hybridization      | Africa; |
| (Brauer)           | ~100-40 ka       |
{RULE}
"""


class Repair(unittest.TestCase):
    def test_the_header_is_the_first_row_and_wrapped_cell_lines_are_joined(self):
        text, repairs = repair_ascii_tables(SLOPPY)
        self.assertEqual(text.splitlines(), [
            "| Model Name | Origin |", "| --- | --- |",
            "| Replacement Model (Out of Africa II) | Africa; ~200-100 ka |",
            "| Hybridization (Brauer) | Africa; ~100-40 ka |"])
        self.assertEqual((repairs[0].line, repairs[0].columns, repairs[0].rows, repairs[0].problems), (1, 2, 2, []))

    def test_the_bars_need_not_line_up(self):
        drifting = f"{RULE}\n| a|b |\n{RULE}\n|   1 |2|\n{RULE}\n"
        self.assertEqual(repair_ascii_tables(drifting)[0].splitlines(), ["| a | b |", "| --- | --- |", "| 1 | 2 |"])

    def test_a_header_rule_makes_every_row_above_it_the_header(self):
        text = f"{RULE}\n| a | b |\n| c | d |\n+{'=' * 40}+\n| 1 | 2 |\n{RULE}\n"
        self.assertEqual(repair_ascii_tables(text)[0].splitlines(), ["| a c | b d |", "| --- | --- |", "| 1 | 2 |"])

    def test_a_row_with_another_number_of_cells_is_fitted_to_the_header_and_reported(self):
        text = f"{RULE}\n| a | b | c |\n{RULE}\n| 1 | 2 |\n{RULE}\n| 1 | 2 | 3 | 4 |\n{RULE}\n"
        fixed, repairs = repair_ascii_tables(text)
        self.assertEqual(fixed.splitlines(), ["| a | b | c |", "| --- | --- | --- |", "| 1 | 2 |  |", "| 1 | 2 | 3 |"])
        self.assertEqual(len(repairs[0].problems), 2)
        self.assertIn("padded", repairs[0].problems[0])
        self.assertIn("cut", repairs[0].problems[1])

    def test_an_escaped_bar_stays_in_its_cell(self):
        text = f"{RULE}\n| a | b |\n{RULE}\n| x \\| y | z |\n{RULE}\n"
        self.assertEqual(repair_ascii_tables(text)[0].splitlines()[-1], "| x \\| y | z |")

    def test_text_around_the_table_is_kept_and_a_blank_line_is_put_between(self):
        text, _ = repair_ascii_tables(f"before\n{SLOPPY}after\n")
        lines = text.splitlines()
        self.assertEqual(lines[0:2], ["before", ""])
        self.assertEqual(lines[-2:], ["", "after"])

    def test_two_tables_in_one_document(self):
        text, repairs = repair_ascii_tables(f"{SLOPPY}\nmiddle\n\n{SLOPPY}")
        self.assertEqual([repair.line for repair in repairs], [1, 13])
        self.assertIn("middle", text)

    def test_a_crlf_file_keeps_its_line_ends(self):
        text, repairs = repair_ascii_tables(SLOPPY.replace("\n", "\r\n"))
        self.assertTrue(repairs)
        self.assertNotIn("\r\r", text)
        self.assertTrue(all(line.endswith("\r") for line in text.split("\n")[:-1]))

    def test_nothing_is_touched_that_is_not_such_a_table(self):
        real = "+---+---+\n| a | b |\n+===+===+\n| 1 | 2 |\n+---+---+\n"            # a Pandoc grid table: an inner +
        one_column = f"{RULE}\n| just one cell |\n{RULE}\n| and another |\n{RULE}\n"   # a grid table of one column
        for text in (real, one_column, "+---+\n", "no table here\n", f"{RULE}\n| a | b |\n"):
            self.assertEqual(repair_ascii_tables(text), (text, []), text)

    def test_nothing_is_touched_in_code_comments_or_front_matter(self):
        fenced = f"```\n{SLOPPY}```\n"
        tilde = f"~~~text\n{SLOPPY}~~~\n"
        indented = "".join("    " + line + "\n" for line in SLOPPY.splitlines())
        comment = f"<!--\n{SLOPPY}-->\n"
        front = f"---\nnote: |\n{SLOPPY}---\n\nbody\n"
        for text in (fenced, tilde, indented, comment, front):
            self.assertEqual(repair_ascii_tables(text), (text, []), text)

    def test_a_table_after_a_closed_fence_is_repaired(self):
        text, repairs = repair_ascii_tables(f"```\ncode\n```\n\n{SLOPPY}")
        self.assertEqual(len(repairs), 1)
        self.assertTrue(text.startswith("```\ncode\n```\n\n| Model Name"))


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Build(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def build(self, name: str = "d.md", options: str = "", body: str | None = None, extra: list[str] = ()):
        if body is not None:
            front = f"pdfmd-options: {{{options}}}\n" if options else ""
            (self.root / name).write_text(f"---\ntitle: T\n{front}---\n\n{body}", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, *extra, "--to", "tex", "-o", "out.tex", "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        out = self.root / "out.tex"
        return done, (out.read_text(encoding="utf-8") if out.exists() else "")

    def columns(self, tex: str) -> list[str]:
        found = re.search(r"\\begin\{longtable\}\[\]\{@\{\}(.*?)@\{\}\}", tex, re.DOTALL)
        return re.findall(r"[lrc]|p\{", found.group(1)) if found else []

    def test_the_default_repairs_it_and_says_so(self):
        done, tex = self.build(body=SLOPPY)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("WARN  table-ascii: d.md, line 5", done.stdout)
        self.assertEqual(len(self.columns(tex)), 2)
        self.assertIn("Replacement Model (Out of Africa II)", " ".join(tex.split()))
        self.assertNotIn("| Model Name", tex)
        self.assertIn("+----", (self.root / "d.md").read_text(encoding="utf-8"), "the file is never touched")

    def test_note_leaves_it_and_off_is_silent(self):
        done, tex = self.build(options="table-ascii: note", body=SLOPPY)
        self.assertIn("NOTE  table-ascii: d.md, line 6", done.stdout)
        self.assertEqual(len(self.columns(tex)), 1)
        done, tex = self.build(options="table-ascii: off", body=SLOPPY)
        self.assertNotIn("table-ascii", done.stdout)
        self.assertEqual(len(self.columns(tex)), 1)

    def test_a_word_that_is_not_a_choice_stops_the_build(self):
        done, _ = self.build(options="table-ascii: maybe", body=SLOPPY)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("table-ascii", done.stderr + done.stdout)

    def test_a_real_grid_table_is_left_alone_and_silent(self):
        done, tex = self.build(body="+------+------+\n| a    | b    |\n+======+======+\n| 1    | 2    |\n+------+------+\n")
        self.assertNotIn("table-ascii", done.stdout)
        self.assertEqual(len(self.columns(tex)), 2)

    def test_the_parts_of_a_document_are_repaired_too(self):
        (self.root / "parts").mkdir()
        (self.root / "parts" / "10-a.md").write_text(f"## A\n\n{SLOPPY}", encoding="utf-8")
        done, tex = self.build(options="parts: auto", body="Intro.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("WARN  table-ascii: ", done.stdout)
        self.assertIn("10-a.md", done.stdout)
        self.assertEqual(len(self.columns(tex)), 2, tex[-1500:])


if __name__ == "__main__":
    unittest.main()
