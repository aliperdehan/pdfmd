"""v3.31.52: a table cell that starts with `<l>`, `<c>` or `<r>` keeps that alignment (entry 3el, pdfmd_lua/cellalign.lua);
real builds through pdfmd, to LaTeX, Typst, HTML and Markdown."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pdfmd  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402

TABLE = "| Name | Qty |\n|:-----|----:|\n| apples | 3 |\n| <c> total | <l> 12 |\n| <R> right | <c>mid |\n"
LONG = ("| Name | Note |\n|:--|:--|\n| a | " + "a long sentence that needs wrapping " * 6 + " |\n"
        "| <c> centred | <r> " + "another long sentence that needs wrapping " * 6 + " |\n")


class Detect(unittest.TestCase):
    """The filter is wanted for a document with a cell tag in a pipe table (v3.32.31: anywhere in the cell, not only at its start)."""

    @staticmethod
    def wanted(table: str) -> bool:
        from pdfmd_tables.celltags import normalise
        return bool(normalise(table).cells)

    def test_a_tag_in_a_cell_of_a_pipe_table_is_wanted_and_prose_is_not(self):
        head = "| h | i |\n|---|---|\n"
        for row in ("| a | <c> b |", "<r> x | y", "| <L> | z |", "a | <c>", "| a<c> | b |", "| a | b <c> |"):
            self.assertTrue(self.wanted(head + row + "\n"), row)
        for row in ("| a | <center>b</center> |", "| a | <b>bold</b> |", "| a | b<br>c |", "| a | b |"):
            self.assertFalse(self.wanted(head + row + "\n"), row)
        self.assertFalse(self.wanted("a <c> b\n"))
        self.assertFalse(self.wanted("text <r>\n"))


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Build(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def build(self, body: str, to: str = "tex", options: str = "", extra: tuple[str, ...] = ()) -> tuple[subprocess.CompletedProcess, str]:
        front = f"pdfmd-options: {{{options}}}\n" if options else ""
        (self.root / "d.md").write_text(f"---\ntitle: T\n{front}---\n\n{body}", encoding="utf-8")
        out = self.root / f"out.{to}"
        out.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *extra, "--to", to, "-o", out.name, "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        return done, (out.read_text(encoding="utf-8") if out.exists() else "")

    def test_latex_wraps_a_cell_of_a_natural_width_column_in_a_multicolumn(self):
        done, tex = self.build(TABLE)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("\\multicolumn{1}{c}{total} & \\multicolumn{1}{l}{12}", tex)
        self.assertIn("\\multicolumn{1}{r}{right} & \\multicolumn{1}{c}{mid}", tex)
        self.assertNotIn("<c>", tex)

    def test_latex_aligns_a_cell_of_a_column_with_a_width_inside_a_group(self):
        done, tex = self.build(LONG)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("{\\centering centred\\par}", tex)
        self.assertIn("{\\raggedleft another long", tex)
        self.assertNotIn("<r>", tex)

    @needs_pandoc(3, 1, 13, why="the Typst writer gained cell alignment overrides then")
    def test_typst_uses_the_cells_own_alignment(self):
        done, typst = self.build(TABLE, "typ")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("table.cell(align: center)[total], table.cell(align: left)[12]", typst)

    def test_html_uses_the_cells_own_alignment(self):
        done, html = self.build(TABLE, "html")
        self.assertIn('<td style="text-align: center;">total</td>', html)
        self.assertIn('<td style="text-align: left;">12</td>', html)

    def test_off_leaves_the_tags_alone(self):
        done, tex = self.build(TABLE, options="cell-align: off")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("multicolumn", tex)

    def test_a_word_that_is_not_a_choice_stops_the_build(self):
        done, _ = self.build(TABLE, options="cell-align: maybe")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("cell-align", done.stdout + done.stderr)

    def test_the_markdown_writers_keep_what_was_written(self):
        done, md = self.build(TABLE, "md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("&c& total", md)                # Markdown has no cell alignment: the tag comes back as a `&...&` tag
        self.assertNotIn("<pc", md)
        self.assertNotIn("multicolumn", md)

    def test_a_table_that_needs_no_tags_has_no_filter(self):
        self.assertEqual(pdfmd.cellalign_args(self.write("| a | b |\n|---|---|\n| 1 | 2 |\n"), []), [])
        self.assertEqual(pdfmd.cellalign_args(self.write(TABLE), [])[0], "--lua-filter")

    def write(self, text: str) -> Path:
        path = self.root / "w.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_the_example_of_the_author_works_whole(self):
        done, tex = self.build("#+caption: Demo\n1 | 2 | 3\n:-|:-:|-:\ndefault | default | default\n<c> override | <r> override | <l> override\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("\\caption{Demo}", tex)
        self.assertIn("\\multicolumn{1}{c}{override}", tex)
        self.assertNotIn("#+caption", tex)


if __name__ == "__main__":
    unittest.main()
