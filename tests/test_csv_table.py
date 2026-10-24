"""`::: {.csv file=...}` blocks: Pandoc Markdown cells, captions after the block or inside it."""

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


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class InlineData(CsvTables):
    """Data written inside the div (no file=), delimiters, alignment and widths."""

    def cells(self, out: str) -> list[str]:
        import re
        return re.findall(r'Plain \[ Str "([^"]*)"', out)

    def test_data_in_a_code_block_inside_the_div_is_verbatim(self):
        out = self.native('::: {.csv}\n```\nname,note\n"a, b",*not emphasis*\nx,"say ""hi"""\n```\n:::\n')
        self.assertIn('Str "a,"', out)                          # the quoted comma stayed inside the cell
        self.assertIn("hi", out)
        self.assertNotIn("CodeBlock", out)

    def test_data_typed_straight_into_the_div_works_too(self):
        out = self.native('::: {.csv}\nname,qty\nwater,3\nacid,4\n:::\n')
        self.assertIn('Str "water"', out)
        self.assertIn('Str "acid"', out)

    def test_a_quoted_field_may_hold_a_line_break(self):
        out = self.native('::: {.csv}\n```\nk,v\n"one\ntwo",3\n```\n:::\n')
        self.assertIn('Str "one"', out)
        self.assertIn('Str "two"', out)

    def test_the_delimiter_is_guessed_named_or_given(self):
        for body, attribute in (("a;b\n1;2\n", ""), ("a\tb\n1\t2\n", ""), ("a|b\n1|2\n", ""),
                                ("a;b\n1;2\n", " delimiter=semicolon"), ("a b\n1 2\n", " delimiter=space")):
            out = self.native('::: {.csv%s}\n```\n%s```\n:::\n' % (attribute, body))
            self.assertTrue(out.startswith("[ Table"), body)
            self.assertIn('Str "b"', out, body)
            self.assertNotIn('Str "a;b"', out, body)

    def test_alignment_comes_from_align_or_from_a_separator_row(self):
        out = self.native('::: {.csv align="lcr"}\n```\nA,B,C\n1,2,3\n```\n:::\n')
        self.assertIn("AlignLeft , ColWidthDefault", out)
        self.assertIn("AlignCenter , ColWidthDefault", out)
        self.assertIn("AlignRight , ColWidthDefault", out)
        out = self.native('::: {.csv}\n```\nA,B,C\n:--,:-:,--:\n1,2,3\n```\n:::\n')
        self.assertIn("AlignRight , ColWidthDefault", out)
        self.assertNotIn(':--', out)                            # the separator row is not a data row
        out = self.native('::: {.csv align="rrr"}\n```\nA,B,C\n:--,:-:,--:\n1,2,3\n```\n:::\n')
        self.assertEqual(out.count("AlignRight , ColWidthDefault"), 3)                     # align= wins over the row

    def test_a_dashes_only_row_can_be_data(self):
        out = self.native('::: {.csv separator=none}\n```\nA,B\n---,---\n1,2\n```\n:::\n')
        self.assertEqual(out.count('Str "\\8212"'), 2)          # Markdown's `---` in a cell is an em dash
        out = self.native('::: {.csv header="false"}\n```\n---,---\n1,2\n```\n:::\n')
        self.assertEqual(out.count('Str "\\8212"'), 2)

    def test_widths_are_relative_and_kept_even_when_equal(self):
        out = self.native('::: {.csv widths="1,3"}\n```\nA,B\n1,2\n```\n:::\n')
        self.assertIn("ColWidth 0.25", out)
        self.assertIn("ColWidth 0.75", out)
        out = self.native('::: {.csv}\n```\nA,B\n--,------\n1,2\n```\n:::\n')
        self.assertIn("ColWidth 0.25", out)
        self.assertIn("ColWidth 0.75", out)

    def test_data_in_the_div_and_file_together_use_the_file(self):
        out = self.native('::: {.csv file="d.csv"}\n```\nx,y\n9,9\n```\n:::\n')
        self.assertIn('Str "water"', out)
        self.assertNotIn('Str "9"', out)


class Limits(unittest.TestCase):
    """The cap for every table (v3.27.2): --csv-rows/--csv-cols, `pdfmd-options: {csv: ...}`, the config; a div's own
    rows=/cols= still win."""

    DATA = "a,b,c,d,e,f,g,h,i\n" + "".join(f"{n},2,3,4,5,6,7,8,9\n" for n in range(1, 16))

    def build(self, markdown: str, *flags: str, front: str = "", config: str | None = None, target: str = "native"):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-csv-limits-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "d.csv").write_text(self.DATA, encoding="utf-8")
        (directory / "d.md").write_text(f"---\ntitle: T\n{front}---\n\n" + markdown, encoding="utf-8")
        env = {**os.environ, "PDFMD_CONFIG": ""}
        env.pop("PDFMD_CSV_ROWS", None)
        env.pop("PDFMD_CSV_COLS", None)
        if config is not None:
            (directory / "config.yaml").write_text(config, encoding="utf-8")
            env["PDFMD_CONFIG"] = str(directory / "config.yaml")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", target, "-o", f"out.{target}",
                               "--no-stamp", "--no-backup", "--no-auto", "crossref", *flags], cwd=directory,
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return (directory / f"out.{target}").read_text(encoding="utf-8"), done.stdout + done.stderr

    def rows_and_columns(self, native: str) -> tuple[int, int]:
        import re
        rows = len(re.findall(r"\bRow\b", native.split("TableBody", 1)[1]))
        header = native.split("TableHead", 1)[1].split("TableBody", 1)[0]
        return rows, len(re.findall(r"\bCell\b", header))

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_the_default_cap_and_its_note(self):
        native, stderr = self.build('::: {.csv file="d.csv"}\n:::\n')
        self.assertEqual(self.rows_and_columns(native), (11, 8))           # 7 + a row of … + 3; 5 + … + 2
        self.assertIn("the first 7 and the last 3 of 15 rows", " ".join(re.findall(r'Str "([^"]*)"', native)))
        self.assertTrue('Str "15"' in native, "the last row is missing")
        self.assertIn("--csv-rows", native)                                  # the note under the table says how
        self.assertIn("WARN", stderr)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_the_command_line_the_document_and_the_config(self):
        block = '::: {.csv file="d.csv"}\n:::\n'
        self.assertEqual(self.rows_and_columns(self.build(block, "--csv-rows", "3", "--csv-cols", "all")[0]), (4, 9))   # 2 + … + 1
        front = "pdfmd-options:\n  csv: {rows: all, cols: 4}\n"
        self.assertEqual(self.rows_and_columns(self.build(block, front=front)[0]), (15, 5))      # 3 + … + 1
        config = "options:\n  csv: {rows: 5}\n"
        self.assertEqual(self.rows_and_columns(self.build(block, config=config)[0]), (6, 8))     # 4 + … + 1
        # the document over the config, field by field; the command line over both
        self.assertEqual(self.rows_and_columns(self.build(block, front="pdfmd-options:\n  csv: {cols: 2}\n",
                                                          config=config)[0]), (6, 2))           # under 3: the head
        self.assertEqual(self.rows_and_columns(self.build(block, "--csv-rows", "all", config=config)[0]), (15, 8))
        front = "pdfmd-options:\n  csv: {cut: head}\n"
        self.assertEqual(self.rows_and_columns(self.build(block, front=front)[0]), (10, 7))      # the old cut
        self.assertEqual(self.rows_and_columns(self.build('::: {.csv file="d.csv" cut="head"}\n:::\n')[0]), (10, 7))

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_a_divs_own_attributes_win_and_header_and_reader_apply_to_every_table(self):
        native, _ = self.build('::: {.csv file="d.csv" rows="2"}\n:::\n', "--csv-rows", "all")
        self.assertEqual(self.rows_and_columns(native)[0], 2)
        native, _ = self.build('::: {.csv file="d.csv"}\n:::\n', front="pdfmd-options:\n  csv: {header: false, rows: all}\n")
        self.assertEqual(self.rows_and_columns(native)[0], 16)            # the first line is data now
        self.assertNotIn("pdfmd-csv", native)                              # the settings left no trace in the metadata

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_the_delimiter_is_guessed_with_a_warning_or_named(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-csv-delimiter-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "s.csv").write_text("name;value\nx;1,5\ny;2,25\n", encoding="utf-8")
        (directory / "t.tsv").write_text("a\tb\n1\t2\n", encoding="utf-8")

        def run(markdown, front=""):
            (directory / "d.md").write_text(f"---\ntitle: T\n{front}---\n\n" + markdown, encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "native", "-o", "o.native",
                                   "--no-stamp", "--no-backup", "--no-auto", "crossref"], cwd=directory,
                                  capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": ""})
            self.assertEqual(done.returncode, 0, done.stderr)
            return (directory / "o.native").read_text(encoding="utf-8"), done.stdout + done.stderr

        native, said = run('::: {.csv file="s.csv"}\n:::\n')
        self.assertIn('Str "1,5"', native)                                  # a decimal comma stays in its cell
        self.assertIn("semicolons as the delimiter", said)
        native, said = run('::: {.csv file="s.csv"}\n:::\n', "pdfmd-options:\n  csv: {delimiter: semicolon}\n")
        self.assertIn('Str "1,5"', native)
        self.assertNotIn("as the delimiter", said)                          # named: no warning
        native, said = run('::: {.csv file="t.tsv"}\n:::\n')
        self.assertNotIn("as the delimiter", said)                          # a .tsv is tab-separated as it says
        native, said = run('::: {.csv file="s.csv" delimiter="comma"}\n:::\n')
        self.assertIn('Str "name;value"', native)                          # the div's own word wins

    def test_the_built_in_renderer_guesses_the_same_way(self):
        sys.path.insert(0, str(ROOT))
        import pdfmd
        self.assertEqual(pdfmd.csv_guess_delimiter("name;value\nx;1,5\ny;2,25\n", "s.csv"), ";")
        self.assertEqual(pdfmd.csv_guess_delimiter('"a;b",c\n"1;2",3\n', "q.csv"), ",")     # quoted ; do not count
        self.assertEqual(pdfmd.csv_guess_delimiter("a,b\n1,2\n", "t.tsv"), ",")              # the lines win
        self.assertEqual(pdfmd.csv_guess_delimiter("one\ntwo\n", "t.tsv"), "\t")              # nothing: the name
        quoted = 'name;note\n"x";"a, b\nc, d, e"\n"y";"f"\n'                    # commas and a line break in a field
        self.assertEqual(pdfmd.csv_guess_delimiter(quoted, "q.csv"), ";")
        self.assertEqual(pdfmd.csv_guess_delimiter("a,b,c\n1,2,3\n4,5,6\n" * 3000, "big.csv"), ",")
        self.assertEqual(pdfmd.csv_keep(15, 10, "ends"), (list(range(7)) + [12, 13, 14], 7, 3))
        self.assertEqual(pdfmd.csv_keep(15, 10, "head"), (list(range(10)), 10, 0))
        self.assertEqual([pdfmd.csv_keep(1000, cap, "ends")[1:] for cap in (7, 10, 20, 30, 100)],
                         [(5, 2), (7, 3), (16, 4), (25, 5), (90, 10)])
        self.assertEqual(pdfmd.csv_keep(5, 10, "ends"), (list(range(5)), None, 0))

    def test_a_bad_value_is_an_error(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-csv-limits-"))
        self.addCleanup(shutil.rmtree, directory, True)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "x.md", "--csv-rows", "many"], cwd=directory,
                              capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("whole number", done.stderr)

    def test_the_built_in_renderer_takes_the_same_cap(self):
        sys.path.insert(0, str(ROOT))
        import pdfmd
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-csv-limits-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "d.csv").write_text(self.DATA, encoding="utf-8")
        lines = pdfmd.csv_div_table('.csv file="d.csv"', directory, None, None, {**pdfmd.CSV_DEFAULTS, "rows": 3, "cols": "all"})
        self.assertEqual(len([line for line in lines if line.startswith("| ")]), 6)       # header, ---, 2 + … + 1
        self.assertEqual(lines[0].count("|"), 10)                                          # 9 columns
        lines = pdfmd.csv_div_table('.csv file="d.csv" rows="1"', directory, None, None, {**pdfmd.CSV_DEFAULTS, "rows": 3})
        self.assertEqual(len([line for line in lines if line.startswith("| ")]), 3)


if __name__ == "__main__":
    unittest.main()
