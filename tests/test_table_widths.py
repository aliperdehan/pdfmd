"""The table-width filter (pdfmd_lua/table_width.lua): `---|---` means "no opinion", unequal dashes are a choice."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILTER = ROOT / "pdfmd_lua" / "table_width.lua"

LONG = ("Chooses how the columns of a pipe table share the text width when the separator row says nothing at all "
        "about them")


def widths(markdown: str, *extra: str) -> list[list]:
    """The column widths (None = natural) of every table the filter leaves."""
    done = subprocess.run(["pandoc", "-f", "markdown", "-t", "json", "--lua-filter", str(FILTER), *extra],
                          input=markdown, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("t") == "Table":
                found.append([None if spec[1] == {"t": "ColWidthDefault"} else spec[1]["c"]
                              for spec in node["c"][2]])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(done.stdout))
    return found


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Auto(unittest.TestCase):
    def test_equal_dashes_under_long_prose_give_the_prose_the_room(self):
        [(key, what, example)] = widths(
            f"| Key | What it does | Example |\n|---|---|---|\n| `table-widths` | {LONG} | `auto` |\n"
            "| `x` | short | `keep` |\n")
        self.assertAlmostEqual(key + what + example, 1.0, places=6)
        self.assertGreater(what, 0.6)
        self.assertGreater(key, example * 0.9)          # the key column keeps its longest word whole

    def test_a_table_that_fits_goes_back_to_its_natural_width(self):
        [cols] = widths("| a | b |\n|---|---|\n| 1 | 2 |\n")
        self.assertEqual(cols, [None, None])
        [cols] = widths("| a | b |\n|---|---|\n| " + "x" * 40 + " | y |\n")      # long line, short cells
        self.assertEqual(cols, [None, None])

    def test_unequal_dashes_are_the_authors_choice(self):
        [cols] = widths(f"| A | B |\n|--|-----------|\n| {LONG} | ok |\n")
        self.assertAlmostEqual(cols[0], 2 / 13, places=6)
        self.assertAlmostEqual(cols[1], 11 / 13, places=6)

    def test_keep_leaves_even_equal_dashes_alone(self):
        text = f"| A | B |\n|---|---|\n| {LONG} | ok |\n"
        [cols] = widths(text, "-M", "pdfmd-table-widths=keep")
        self.assertEqual(cols, [0.5, 0.5])
        [cols] = widths("---\npdfmd-options:\n  table-widths: keep\n---\n\n" + text)
        self.assertEqual(cols, [0.5, 0.5])
        [cols] = widths(text)
        self.assertGreater(cols[0], 0.7)

    def test_a_wide_table_without_dashes_to_go_by_is_still_rescued(self):
        words = " ".join(["word"] * 30)
        [cols] = widths(f"A | B\n--|--\n{words} | {words}\n\n")
        self.assertIsNotNone(cols[0])

    def test_the_height_is_what_is_minimised(self):
        # one column of long text next to two of medium text: the long one is widest, none is starved
        a, b, c = " ".join(["alpha"] * 12), " ".join(["beta"] * 5), " ".join(["gamma"] * 5)
        [(x, y, z)] = widths(f"| A | B | C |\n|---|---|---|\n| {a} | {b} | {c} |\n| {a} | {b} | {c} |\n")
        self.assertGreater(x, y)
        self.assertGreater(x, z)
        self.assertGreater(min(x, y, z), 0.1)


class Packaging(unittest.TestCase):
    def test_the_filters_ship_as_files_in_a_package(self):
        sys.path.insert(0, str(ROOT))
        try:
            import pdfmd_lua
        finally:
            sys.path.pop(0)
        for name in ("table_width", "csv_table"):
            self.assertTrue(pdfmd_lua.path(name).is_file(), name)
        self.assertIsNone(pdfmd_lua.path("nope"))
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"pdfmd_lua"', pyproject)
        self.assertIn('pdfmd_lua = ["*.lua"]', pyproject)

    def test_a_lone_pdfmd_py_still_builds_without_the_package(self):
        import tempfile
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-lone-"))
        self.addCleanup(shutil.rmtree, directory, True)
        shutil.copy(ROOT / "pdfmd.py", directory / "pdfmd.py")
        (directory / "d.md").write_text("| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(directory / "pdfmd.py"), "d.md", "--to", "latex", "-o", "o.tex"],
                              cwd=directory, capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": ""})
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
