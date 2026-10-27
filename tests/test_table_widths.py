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


def pandoc_version() -> tuple:
    out = subprocess.run(["pandoc", "--version"], capture_output=True, text=True).stdout.split()[1]
    return tuple(int(part) for part in out.split(".")[:3])


# a chosen table (1 : 12 : 6 dashes) whose first column is a few characters wide but holds "Immediate"
NARROW = (f"| Type | What it is | Example |\n|-|------------|------|\n"
          f"| Immediate | {LONG} | tablets, patches |\n| Targeted | short | carriers |\n")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Modes(unittest.TestCase):
    """v3.31.0: `table-word-floor` and the `force` mode of `table-widths`, global, per document and per table."""

    def test_a_chosen_column_too_narrow_for_its_longest_word_is_widened_to_it(self):
        [cols] = widths(NARROW)
        self.assertAlmostEqual(sum(cols), 1.0, places=6)
        self.assertGreaterEqual(cols[0] * (95 - 3 * 3), 9 - 1e-6)       # "Immediate" fits whole
        self.assertGreater(cols[1], cols[2])                           # the others keep their order

    def test_a_chosen_table_that_already_fits_is_left_exactly_as_written(self):
        [cols] = widths(f"| A | B |\n|----------|-----------|\n| {LONG} | ok |\n")
        self.assertAlmostEqual(cols[0], 10 / 21, places=9)
        self.assertAlmostEqual(cols[1], 11 / 21, places=9)

    def test_the_floor_can_be_switched_off_everywhere(self):
        for extra in (["-M", "pdfmd-table-word-floor=off"],):
            [cols] = widths(NARROW, *extra)
            self.assertAlmostEqual(cols[0], 1 / 19, places=6)
        [cols] = widths("---\npdfmd-options:\n  table-word-floor: off\n---\n\n" + NARROW)
        self.assertAlmostEqual(cols[0], 1 / 19, places=6)

    def test_the_document_wins_over_the_global_setting(self):
        [cols] = widths("---\npdfmd-options:\n  table-word-floor: on\n---\n\n" + NARROW, "-M", "pdfmd-table-word-floor=off")
        self.assertGreater(cols[0], 1 / 19)

    def test_keep_means_exactly_as_written_without_the_floor(self):
        [cols] = widths(NARROW, "-M", "pdfmd-table-widths=keep")
        self.assertAlmostEqual(cols[0], 1 / 19, places=6)

    def test_force_ignores_unequal_dashes(self):
        text = f"| A | B |\n|--|-----------|\n| {LONG} | ok |\n"
        [cols] = widths(text, "-M", "pdfmd-table-widths=force")
        self.assertGreater(cols[0], 0.6)                               # the dashes said 2 : 11
        [cols] = widths("---\npdfmd-options:\n  table-widths: force\n---\n\n" + text)
        self.assertGreater(cols[0], 0.6)

    @unittest.skipUnless(pandoc_version() >= (3, 8, 2), "caption attributes need Pandoc 3.8.2")
    def test_one_table_can_say_so_after_its_caption(self):
        [cols] = widths(NARROW + "\n: Caption {word-floor=off}\n")
        self.assertAlmostEqual(cols[0], 1 / 19, places=6)
        text = f"| A | B |\n|--|-----------|\n| {LONG} | ok |\n\n: Caption {{widths=force}}\n"
        [cols] = widths(text)
        self.assertGreater(cols[0], 0.6)
        [cols] = widths(text.replace("force", "keep"), "-M", "pdfmd-table-widths=force")
        self.assertAlmostEqual(cols[0], 2 / 13, places=6)


class Config(unittest.TestCase):
    def test_the_global_settings_reach_the_filter(self):
        import pdfmd
        from unittest import mock
        with mock.patch.object(pdfmd, "config_options", lambda *a: {"table-widths": "Force", "table-word-floor": False}):
            args = pdfmd.width_filter_args(Path("f.lua"))
        self.assertEqual(args[2:], ["-M", "pdfmd-table-widths=force", "-M", "pdfmd-table-word-floor=off"])
        with mock.patch.object(pdfmd, "config_options", lambda *a: {"table-widths": "sideways"}):
            self.assertEqual(len(pdfmd.width_filter_args(Path("f.lua"))), 2)


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
        self.assertIn('pdfmd_lua = ["*.lua", "*.tex", "*.cjs"]', pyproject)     # *.cjs: katex.cjs (v3.28.11)
        self.assertTrue((pdfmd_lua.FILTERS / "katex.cjs").is_file())

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
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
