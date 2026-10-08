"""`::: {.csv file=...}` blocks: Pandoc Markdown cells, captions after the block or inside it."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class CsvTables(unittest.TestCase):
    def native(self, markdown: str, data: str = "Name,Formula\nwater,H~2~O\nacid,$x^2$\n") -> str:
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-csv-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "d.csv").write_text(data, encoding="utf-8")
        (directory / "d.md").write_text("---\ntitle: T\n---\n\n" + markdown, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "native", "-o", "out.native",
                               "--no-stamp", "--no-backup", "--no-auto", "crossref"], cwd=directory, capture_output=True,
                              text=True, env={**os.environ, "PDFMD_CONFIG": ""})
        self.assertEqual(done.returncode, 0, done.stderr)
        return (directory / "out.native").read_text(encoding="utf-8")

    def test_cells_are_pandoc_markdown_by_default_and_gfm_on_request(self):
        block = '::: {.csv file="d.csv"%s}\n:::\n'
        default = self.native(block % "")
        self.assertIn("Subscript", default)
        self.assertIn("Math InlineMath", default)
        gfm = self.native(block % ' reader="gfm"')
        self.assertNotIn("Subscript", gfm)

    def test_a_caption_line_after_the_block_becomes_the_tables_caption(self):
        out = self.native('::: {.csv file="d.csv"}\n:::\n\n: Raw data, H~2~O {#tbl:raw}\n\nAfter.\n')
        self.assertNotIn('Str ":"', out)
        self.assertIn('"tbl:raw"', out)
        self.assertIn("Raw", out.split("Caption")[1])
        self.assertNotIn("{#tbl:raw}", out)
        self.assertIn('Str "After."', out)

    def test_table_colon_form_works_too(self):
        out = self.native('::: {.csv file="d.csv"}\n:::\n\nTable: Plain caption\n')
        self.assertNotIn('Str "Table:"', out)
        self.assertIn('Str "Plain"', out)

    def test_the_caption_can_sit_in_the_attributes(self):
        out = self.native('::: {.csv file="d.csv" caption="Inside *the* block" #tbl:in}\n:::\n\n: Not used by the table\n')
        self.assertIn('"tbl:in"', out)
        self.assertIn("Emph", out.split("Caption")[1])
        self.assertIn('Str "Not"', out)           # a later paragraph is left alone when the block carried its own caption

    def test_a_table_without_a_caption_has_none(self):
        out = self.native('::: {.csv file="d.csv"}\n:::\n\nPlain paragraph.\n')
        self.assertIn("(Caption Nothing [])", out)


if __name__ == "__main__":
    unittest.main()
