"""Source preparation for Markdown pipe tables."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
PROSE = "A cell with enough ordinary words to make Pandoc use the width of each separator cell."
SPELLINGS = (
    ("|–––|———|", "|------|---------|"),
    ("|−‒‐‑|------|", "|----|------|"),
    ("|====|======|", "|----|------|"),
    ("|---+-----|", "|---|-----|"),
    ("+:--+--:+", "|:--|--:|"),
    ("---+-----", "---|-----"),
    ("|: - :|---|", "|:-:|---|"),
)


class Source(unittest.TestCase):
    def test_rewrites_only_the_separator_and_reports_its_line(self):
        sys.path.insert(0, str(ROOT / "lib"))
        self.addCleanup(sys.path.pop, 0)
        from pdfmd_tables.prepass import normalise_separators

        for spelling, canonical in SPELLINGS:
            text = f"# Title\r\n\r\n| A | B |\r\n{spelling}\r\n| 1 | 2 |\r\n"
            with self.subTest(spelling=spelling):
                fixed, lines = normalise_separators(text)
                self.assertEqual(fixed, text.replace(spelling, canonical))
                self.assertEqual(lines, [4])

    def test_skips_grid_tables_and_literal_blocks(self):
        sys.path.insert(0, str(ROOT / "lib"))
        self.addCleanup(sys.path.pop, 0)
        from pdfmd_tables.prepass import normalise_separators

        table = "| A | B |\n|---+---|\n| 1 | 2 |\n"
        examples = (
            f"---\nraw: |\n{table}---\n", f"```{{=html}}\n{table}```\n",
            f"~~~\n{table}~~~\n", f"<!--\n{table}-->\n", f"<pre>\n{table}</pre>\n",
            f"$$\n{table}$$\n", f"\\[\n{table}\\]\n", f"::: {{.csv}}\n{table}:::\n",
            f"+-----+-----+\n{table}+-----+-----+\n", "\n".join("    " + row for row in table.splitlines()),
        )
        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(normalise_separators(text), (text, []))


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Writers(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def build(self, text, reader, writer, *extra):
        source, output = self.root / "doc.md", self.root / f"out.{writer}"
        source.write_text(text, encoding="utf-8")
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--from", reader,
                                 "--to", writer, "-o", str(output), "--no-stamp", *extra, str(source)],
                                cwd=self.root, env={**os.environ, "PDFMD_CONFIG": ""},
                                capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(source.read_text(encoding="utf-8"), text)
        return result, output.read_text(encoding="utf-8")

    def proportions(self, output, writer):
        if writer == "latex":
            tables = re.findall(r"\\begin\{longtable\}.*?\\end\{longtable\}", output, re.S)
            return [re.findall(r"\\real\{([0-9.]+)\}", table) for table in tables]
        tables = re.findall(r"<table\b.*?</table>", output, re.S)
        return [re.findall(r'<col style="width: ([0-9.]+)%"', table) for table in tables]

    def test_spellings_have_the_proportions_of_the_canonical_separator(self):
        def document(separators):
            return "\n".join(f"| A | B |\n{line}\n| {PROSE} | {PROSE} |\n" for line in separators)

        spellings, canonical = zip(*SPELLINGS)
        for reader in ("gfm", "markdown"):
            for writer in ("latex", "html"):
                with self.subTest(reader=reader, writer=writer):
                    result, output = self.build(document(spellings), reader, writer)
                    _, expected = self.build(document(canonical), reader, writer)
                    for index in range(len(spellings)):
                        self.assertIn(f"line {2 + 4 * index}:", result.stdout + result.stderr)
                    widths = self.proportions(output, writer)
                    self.assertEqual(len(widths), len(spellings))
                    self.assertEqual(widths, self.proportions(expected, writer))

    def test_alignment_colons_do_not_change_chosen_widths_unless_counted(self):
        body = (f"| A | B |\n|:---:|---|\n| {PROSE} | {PROSE} |\n\n"
                f"| A | B |\n|:----:|------|\n| {PROSE} | {PROSE} |\n")
        for writer in ("latex", "html"):
            for mode, shares in (("ignore", [(50, 50), (40, 60)]), ("count", [(62, 37), (50, 50)])):
                with self.subTest(writer=writer, mode=mode):
                    options = f"column-widths: keep, table-colons: {mode}" if mode == "count" else "column-widths: keep"
                    _, output = self.build(f"---\npdfmd-options: {{{options}}}\n---\n\n{body}", "markdown", writer)
                    widths = self.proportions(output, writer)
                    if writer == "latex":
                        expected = [["0.5000", "0.5000"], ["0.4000", "0.6000"]] if mode == "ignore" else [
                            ["0.6250", "0.3750"], ["0.5000", "0.5000"]]
                    else:
                        expected = [[str(value) for value in columns] for columns in shares]
                    self.assertEqual(widths, expected)

    def test_caption_overrides_table_colons(self):
        first = f"| A | B |\n|:---:|---|\n| {PROSE} | {PROSE} |\n"
        second = first + "\n: Caption {table-colons=count}\n"
        _, output = self.build(first + "\n" + second, "markdown", "html")
        self.assertEqual(self.proportions(output, "html"), [["50", "50"], ["62", "37"]])
