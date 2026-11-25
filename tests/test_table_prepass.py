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

    def test_check_names_the_reader_problem_and_can_ignore_it(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "doc.md").write_text("| A | B | C |\n|---|---|\n| 1 | 2 | 3 |\n", encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts" / "pdfmd"), "--check", "--from", "gfm", "doc.md"]
            done = subprocess.run(command, cwd=root, capture_output=True, encoding="utf-8")
            self.assertIn("doc.md:2: warning:", done.stdout)
            self.assertIn("header 3 / separator 2", done.stdout)
            self.assertIn("[table-unparsed]", done.stdout)
            ignored = subprocess.run([*command, "--check-ignore", "table-unparsed"], cwd=root,
                                     capture_output=True, encoding="utf-8")
            self.assertEqual(ignored.returncode, 0, ignored.stderr)
            self.assertNotIn("[table-unparsed]", ignored.stdout)


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

    def test_build_warns_about_unparsed_table_shapes(self):
        text = ("a | b\nc | d\n\ncommand | other\n\n| A | B |\n|---+---|\n| x | y |\n\n"
                "+---+---+\n| a | b |\n+===+===+\n| x | y |\n+---+---+\n")
        result, _ = self.build(text, "gfm", "html")
        lines = [line for line in result.stdout.splitlines() if "WARN  table-unparsed" in line]
        self.assertEqual(len(lines), 3, lines)
        self.assertIn("line 1: looks like a table but was not read as one (no separator row)", lines[0])
        self.assertIn("line 7:", lines[1])
        self.assertIn("+ separator", lines[1])
        self.assertIn("line 10:", lines[2])
        self.assertIn("gfm does not read grid tables", lines[2])

    def test_repair_modes_pad_or_cut_as_requested(self):
        sample = "A | B\n|---|---|\n| short |\nwide | body | sentinel\n"
        for reader in ("gfm", "markdown"):
            with self.subTest(reader=reader):
                headline, html = self.build(sample, reader, "html", "--table-repair", "header")
                self.assertIn("padded", headline.stdout)
                self.assertIn("cut", headline.stdout)
                self.assertNotIn("sentinel", html)
                widest, html = self.build(sample, reader, "html", "--table-repair", "widest")
                self.assertIn("padded", widest.stdout)
                self.assertNotIn("cut from", widest.stdout)
                self.assertIn("sentinel", html)
                self.assertEqual(html.count("<th"), 4)  # thead and three cells
                _, original = self.build(sample, reader, "html")
                _, pandoc = self.build(sample, reader, "html", "--table-repair", "pandoc")
                self.assertEqual(original, pandoc)

    def test_repair_synthesises_the_missing_row(self):
        text = "A | B\nx | y\n\n|---|---|\n| c | d |\n"
        result, html = self.build(text, "gfm", "html", "--table-repair", "widest")
        self.assertEqual(html.count("<table>"), 2)
        self.assertIn("inserted a separator", result.stdout)
        self.assertIn("inserted an empty header", result.stdout)

    def test_repair_keeps_proportions_for_all_separator_spellings(self):
        def document(separators, repaired):
            header = "| A | B | |" if repaired else "| A | B |"
            return "\n".join(f"{header}\n{line}\n| {PROSE} | {PROSE} | marker |\n" for line in separators)

        spellings, canonical = zip(*SPELLINGS)
        padded = [line.rstrip("|") + "|---|" for line in canonical]
        for reader in ("gfm", "markdown"):
            for writer in ("latex", "html"):
                with self.subTest(reader=reader, writer=writer):
                    result, output = self.build(document(spellings, False), reader, writer, "--table-repair", "widest")
                    _, expected = self.build(document(padded, True), reader, writer)
                    self.assertEqual(output.count("marker"), len(spellings))
                    self.assertEqual(result.stdout.count("padded the separator"), len(spellings))
                    self.assertEqual(self.proportions(output, writer), self.proportions(expected, writer))
