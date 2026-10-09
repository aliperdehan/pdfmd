"""`--extract-tables` / `--expand-tables` and the pdfmd_tables package behind them."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
import pdfmd_tables as tables  # noqa: E402

FILTER = ROOT / "pdfmd_lua" / "csv_table.lua"
PANDOC = shutil.which("pandoc")

DOCUMENT = """---
title: Tables
---

Before.

| Key | What it does | Example |
|:---|:---:|---:|
| `table-widths` | Chooses how the columns share the width | `auto` |
| `x` | has a \\| pipe | `keep` |

: Settings and what they do {#tbl:settings}

A simple table:

  Right     Left     Center     Default
-------     ------ ----------   -------
     12     12        12            12
    123     123       123          123

Table: Demonstration of simple table syntax.

+---------------------+-----------------------+
| Fruit               | Price                 |
+=====================+=======================+
| Bananas             | $1.34                 |
+---------------------+-----------------------+
| Oranges             | $2.10                 |
+---------------------+-----------------------+

```
| not | a table |
|-----|---------|
| in  | code    |
```

| a | b |
|---|---|
| 1 | 2 |
"""


class Scan(unittest.TestCase):
    def test_every_kind_is_found_and_code_is_not(self):
        found = tables.find_tables(DOCUMENT)
        self.assertEqual([table.kind for table in found], ["pipe", "simple", "grid", "pipe"])
        self.assertEqual(found[0].caption, "Settings and what they do {#tbl:settings}")
        self.assertEqual(found[0].identifier, "tbl:settings")
        self.assertEqual(found[0].aligns, ["left", "center", "right"])
        self.assertEqual(found[0].rows[1], ["`x`", "has a | pipe", "`keep`"])
        self.assertEqual(found[1].caption, "Demonstration of simple table syntax.")
        self.assertIsNone(found[2].caption)               # the caption after the simple table is not the grid table's
        self.assertIsNone(found[3].caption)

    def test_a_caption_may_come_before_the_table(self):
        [table] = tables.find_tables("Table: Before it\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
        self.assertEqual(table.caption, "Before it")
        self.assertEqual(table.span, (0, 5))

    def test_equal_dashes_say_nothing_and_unequal_long_lines_say_widths(self):
        [short] = tables.find_tables("| a | b |\n|-|-----|\n| 1 | 2 |\n")
        self.assertIsNone(short.widths)                   # Pandoc ignores the dashes while every line is short
        long_cell = "word " * 20
        [long] = tables.find_tables(f"| a | b |\n|--|------|\n| {long_cell} | 2 |\n")
        self.assertAlmostEqual(long.widths[0], 0.25)

    def test_cells_split_outside_code_and_escapes(self):
        from pdfmd_tables.scan import split_row
        self.assertEqual(split_row("| a | `b | c` | d \\| e |"), ["a", "`b | c`", "d \\| e"])
        self.assertEqual(split_row("a | b"), ["a", "b"])

    def test_csv_blocks_are_found_with_quoted_braces_in_their_attributes(self):
        text = '::: {.csv file="t.csv" caption="A {#tbl:a}" align="lr"}\n:::\n\n::: {.csv}\n```\nx,y\n```\n:::\n'
        [one, two] = tables.find_csv_blocks(text)
        self.assertEqual(one.attributes["file"], "t.csv")
        self.assertEqual(one.attributes["caption"], "A {#tbl:a}")
        self.assertIsNone(one.data)
        self.assertEqual(two.data, "x,y")


@unittest.skipUnless(PANDOC, "needs Pandoc")
class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-tables-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def extract(self, text=DOCUMENT, **options):
        result = tables.extract(text, self.directory, pandoc=PANDOC, **options)
        for name, data in result.files.items():
            (self.directory / name).parent.mkdir(parents=True, exist_ok=True)
            (self.directory / name).write_text(data, encoding="utf-8")
        return result

    def test_pandoc_reads_the_same_tables_after_extracting_every_kind(self):
        result = self.extract()
        self.assertEqual(result.changed, 4)
        self.assertEqual(tables.same_tables(PANDOC, DOCUMENT, result.text, self.directory, FILTER), [])
        self.assertIn('{.csv file="tables/settings-and-what-they-do.csv"', result.text)
        self.assertIn('align="lcr"', result.text)
        self.assertIn("table3.csv", result.text)                  # no caption: table<position>
        self.assertIn("| not | a table |", result.text)            # the one inside code stays

    def test_inline_data_round_trips_too(self):
        result = self.extract(inline=True)
        self.assertEqual(result.files, {})
        self.assertIn("```\nKey,What it does,Example\n", result.text)
        self.assertEqual(tables.same_tables(PANDOC, DOCUMENT, result.text, self.directory, FILTER), [])

    def test_expanding_gives_the_tables_back(self):
        result = self.extract()
        back = tables.expand(result.text, self.directory)
        self.assertEqual(back.changed, 4)
        self.assertEqual(len(tables.find_tables(back.text)), 5 - 1)
        again = tables.pandoc_tables(PANDOC, back.text, self.directory)
        before = tables.pandoc_tables(PANDOC, DOCUMENT, self.directory)
        self.assertEqual([t["head"] for t in again], [t["head"] for t in before])
        self.assertEqual([t["bodies"] for t in again], [t["bodies"] for t in before])
        self.assertEqual([t["aligns"] for t in again], [t["aligns"] for t in before])
        self.assertEqual(again[0]["caption"], before[0]["caption"])
        self.assertEqual(again[0]["id"], "tbl:settings")

    def test_a_table_longer_than_the_default_cap_is_not_cut(self):
        rows = "\n".join(f"| {n} | {n * n} |" for n in range(1, 31))
        text = f"| n | square |\n|---|---|\n{rows}\n"
        result = self.extract(text)
        self.assertIn("rows=all", result.text)
        self.assertEqual(tables.same_tables(PANDOC, text, result.text, self.directory, FILTER), [])

    def test_a_data_row_of_dashes_is_marked_as_data(self):
        text = "| a | b |\n|---|---|\n| --- | --- |\n| 1 | 2 |\n"
        result = self.extract(text)
        self.assertIn("separator=none", result.text)
        self.assertEqual(tables.same_tables(PANDOC, text, result.text, self.directory, FILTER), [])

    def test_a_caption_with_quotes_goes_under_the_block(self):
        text = '| a | b |\n|---|---|\n| 1 | 2 |\n\n: Say "hi" {#tbl:q}\n'
        result = self.extract(text)
        self.assertNotIn("caption=", result.text)
        self.assertIn(': Say "hi" {#tbl:q}', result.text)
        self.assertEqual(tables.same_tables(PANDOC, text, result.text, self.directory, FILTER), [])

    def test_a_table_whose_cells_are_blocks_is_left_with_the_reason(self):
        text = ("+------+------------------+\n| a    | b                |\n+======+==================+\n"
                "| 1    | - one            |\n|      | - two            |\n+------+------------------+\n")
        result = tables.extract(text, self.directory, pandoc=PANDOC)
        self.assertEqual(result.changed, 0)
        self.assertEqual(result.text, text)
        self.assertTrue(any(line.startswith("SKIP") for line in result.report))

    def test_names_must_match_the_table_count(self):
        with self.assertRaises(tables.TablesError) as caught:
            tables.extract(DOCUMENT, self.directory, pandoc=PANDOC, names=["a", "b"])
        self.assertIn("2 names given for 4 tables", str(caught.exception))
        result = self.extract(names=["one", "two", "three", "four"])
        self.assertTrue((self.directory / "tables" / "three.csv").is_file())
        self.assertIn('file="tables/one.csv"', result.text)

    def test_an_existing_file_with_other_content_is_not_overwritten(self):
        (self.directory / "tables").mkdir()
        (self.directory / "tables" / "table4.csv").write_text("other\n", encoding="utf-8")
        result = tables.extract(DOCUMENT, self.directory, pandoc=PANDOC)
        self.assertIn("tables/table4-2.csv", result.text)
        with self.assertRaises(tables.TablesError):
            tables.extract(DOCUMENT, self.directory, pandoc=PANDOC, names=["a", "b", "c", "table4"])

    def test_a_given_folder_is_used(self):
        result = self.extract(directory="data/csv")
        self.assertIn('file="data/csv/', result.text)
        self.assertTrue((self.directory / "data" / "csv").is_dir())


class Expand(unittest.TestCase):
    def test_a_csv_block_becomes_a_pipe_table_with_its_caption_and_alignment(self):
        text = ('::: {.csv align="lr" caption="Masses {#tbl:m}" widths="1,3"}\n```\nname,mass\n"a, b",1\n```\n:::\n')
        result = tables.expand(text, Path("."))
        self.assertEqual(result.text, "| name | mass |\n|:--|--------:|\n| a, b | 1 |\n\n: Masses {#tbl:m}\n")      # 1:3, colons counted

    def test_all_rows_are_kept_whatever_the_cap(self):
        data = "n\n" + "\n".join(str(n) for n in range(30)) + "\n"
        result = tables.expand("::: {.csv}\n```\n" + data + "```\n:::\n", Path("."))
        self.assertEqual(result.text.count("\n| "), 30)

    def test_a_missing_file_is_reported_and_left(self):
        text = '::: {.csv file="missing.csv"}\n:::\n'
        result = tables.expand(text, Path(tempfile.gettempdir()))
        self.assertEqual(result.changed, 0)
        self.assertEqual(result.text, text)
        self.assertTrue(result.report[0].startswith("SKIP"))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-tables-cli-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "doc.md").write_text(DOCUMENT, encoding="utf-8")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "PDFMD_CONFIG": ""}

    def run_pdfmd(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.directory,
                              capture_output=True, text=True, env=self.env)

    def test_a_dry_run_writes_nothing(self):
        done = self.run_pdfmd("--extract-tables", "doc.md", "--dry-run")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.directory / "doc.md").read_text(encoding="utf-8"), DOCUMENT)
        self.assertFalse((self.directory / "tables").exists())
        self.assertFalse((self.directory / ".backups").exists())
        self.assertIn("would write tables/table4.csv", done.stdout)

    def test_extract_backs_up_the_old_file_and_expand_undoes_it(self):
        done = self.run_pdfmd("--extract-tables", "doc.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("checked: Pandoc reads the same tables", done.stdout)
        self.assertIn("backups go to .backups/", done.stdout)
        [backup] = list((self.directory / ".backups").iterdir())
        self.assertEqual(backup.read_text(encoding="utf-8"), DOCUMENT)
        self.assertTrue((self.directory / "tables" / "table4.csv").is_file())
        self.assertIn("::: {.csv", (self.directory / "doc.md").read_text(encoding="utf-8"))
        again = self.run_pdfmd("--extract-tables", "doc.md")
        self.assertIn("no tables found", again.stdout)
        self.assertNotIn("backups go to", again.stdout)         # said once
        back = self.run_pdfmd("--expand-tables", "doc.md")
        self.assertEqual(back.returncode, 0, back.stderr)
        self.assertNotIn("::: {.csv", (self.directory / "doc.md").read_text(encoding="utf-8"))
        self.assertEqual(len(list((self.directory / ".backups").iterdir())), 2)

    def test_wrong_name_count_is_an_error_that_changes_nothing(self):
        done = self.run_pdfmd("--extract-tables", "doc.md", "--table-names", "a,b")
        self.assertEqual(done.returncode, 1)
        self.assertIn("2 names given for 4 tables", done.stderr)
        self.assertEqual((self.directory / "doc.md").read_text(encoding="utf-8"), DOCUMENT)

    def test_an_existing_backup_folder_of_the_older_spelling_is_kept_using(self):
        (self.directory / "backup").mkdir()
        self.run_pdfmd("--extract-tables", "doc.md")
        self.assertEqual(len(list((self.directory / "backup").iterdir())), 1)
        self.assertFalse((self.directory / ".backups").exists())


MIXED = """---
title: Mixed
---

# Mixed

::: {.csv delimiter=semicolon caption="Inline one"}
a;b;c
1;2;3
:::

::: {.csv file="old.csv"}
:::

| Name | Qty |
|------|----:|
| Pen  |   3 |

+------+----------+
| H1   | H2       |
+======+==========+
| a    | - item 1 |
|      | - item 2 |
+------+----------+

-------  ------
 1        2
 3        4
-------  ------

| X | Y |
|---|---|
| 1 | 2 |
"""


class MixedDocument(unittest.TestCase):
    """csv blocks and tables side by side; a table that cannot be CSV, or a check that fails."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-tables-mixed-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "doc.md").write_text(MIXED, encoding="utf-8")
        (self.directory / "old.csv").write_text("p,q\n7,8\n", encoding="utf-8")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "PDFMD_CONFIG": ""}

    def run_pdfmd(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.directory,
                              capture_output=True, text=True, env=self.env)

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_extract_leaves_csv_blocks_and_unconvertible_tables_alone(self):
        done = self.run_pdfmd("--extract-tables", "doc.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("SKIP  table 2: its cells hold more than one line", done.stdout)
        self.assertIn("SKIP  table 3: it has no header row", done.stdout)      # the headerless simple table
        after = (self.directory / "doc.md").read_text(encoding="utf-8")
        self.assertIn('::: {.csv delimiter=semicolon caption="Inline one"}', after)
        self.assertIn("a;b;c\n1;2;3", after)                                    # the inline block is untouched
        self.assertIn('::: {.csv file="old.csv"}', after)
        self.assertIn("| a    | - item 1 |", after)                             # the skipped grid table is as it was
        self.assertEqual(after.count("::: {.csv"), 4)
        back = self.run_pdfmd("--expand-tables", "doc.md")
        self.assertEqual(back.returncode, 0, back.stderr)
        self.assertEqual((self.directory / "old.csv").read_text(encoding="utf-8"), "p,q\n7,8\n")

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_a_document_read_as_gfm_has_pipe_tables_only(self):
        gfm = MIXED.replace("---\ntitle: Mixed\n---\n\n", "", 1)          # no front matter: pdfmd reads it as gfm
        (self.directory / "doc.md").write_text(gfm, encoding="utf-8")
        done = self.run_pdfmd("--extract-tables", "doc.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("NOTE  2 grid/simple tables left as they are", done.stdout)
        after = (self.directory / "doc.md").read_text(encoding="utf-8")
        self.assertIn("| a    | - item 1 |", after)
        self.assertIn(" 1        2", after)
        self.assertEqual(after.count("::: {.csv"), 4)                         # 2 existing + the 2 pipe tables

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_a_failed_check_stops_the_document_and_writes_nothing(self):
        from unittest import mock
        with mock.patch.object(tables, "same_tables", return_value=["table 1 differs"]), \
                mock.patch.object(sys, "argv", ["pdfmd", "--extract-tables", str(self.directory / "doc.md")]), \
                mock.patch.dict(os.environ, self.env, clear=True):
            with self.assertRaises(SystemExit) as raised:
                pdfmd.main()
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual((self.directory / "doc.md").read_text(encoding="utf-8"), MIXED)
        self.assertFalse((self.directory / "tables").exists())
        self.assertFalse((self.directory / ".backups").exists())


class BackupDirectory(unittest.TestCase):
    def test_default_legacy_and_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "d.md"
            self.assertEqual(pdfmd.backup_directory(document, {"dir": ""}), Path(directory) / ".backups")
            (Path(directory) / "backups").mkdir()
            self.assertEqual(pdfmd.backup_directory(document, {"dir": ""}), Path(directory) / "backups")
            self.assertEqual(pdfmd.backup_directory(document, {"dir": "old"}), Path(directory) / "old")
            self.assertEqual(pdfmd.backup_directory(document, {"dir": "/abs"}), Path("/abs"))


if __name__ == "__main__":
    unittest.main()
