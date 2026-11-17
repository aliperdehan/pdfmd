"""Opt-in column measurements use the build's writer, engine and page setup."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402

TEXT = """---
pdfmd-options:
  column-estimate: measure
  stamp: off
---

| A | B |
|---|---|
| iiiiiiiiii iiiiiiiiii iiiiiiiiii | WWWWWWWWWW WWWWWWWWWW WWWWWWWWWW |
| `\\rule{20pt}{1pt}`{=latex} | fixed width |
"""


class Settings(unittest.TestCase):
    def test_config_reaches_filter(self):
        with mock.patch.object(pdfmd, "config_options", return_value={"column-estimate": " Measure "}):
            self.assertIn("pdfmd-column-estimate=measure", pdfmd.width_filter_args(Path("f.lua")))


class Fallbacks(unittest.TestCase):
    def test_count_and_disabled_measure_do_no_extra_work(self):
        from pdfmd_tables.measure import prepare
        with mock.patch.object(pdfmd, "first_pdfmd_option", return_value="count"), mock.patch(
                "pdfmd_tables.measure.run") as run:
            with tempfile.TemporaryDirectory(prefix="pdfmd-count-gate-") as folder:
                source = Path(folder) / "plain.md"
                source.write_text("plain text", encoding="utf-8")
                self.assertEqual(prepare(["pandoc"], "xelatex", [source], [], ROOT), ["pandoc"])
            self.assertEqual(run.call_count, 0)
        with mock.patch("pdfmd_tables.measure.requested") as gate:
            prepare(["pandoc"], "xelatex", [Path(__file__)], [], ROOT, enabled=False)
            gate.assert_not_called()

    def test_exports_and_other_writers_note_once_without_an_engine(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from pdfmd_tables.measure import prepare
        for engine, export in (("latex", True), ("typst", True), ("docx", True), ("odt", True),
                               ("html", True), ("epub", True), ("weasyprint", False)):
            with self.subTest(engine=engine), mock.patch("pdfmd_tables.measure.requested", return_value=True), mock.patch(
                    "pdfmd_tables.measure.run") as run, redirect_stderr(StringIO()) as out:
                self.assertEqual(prepare(["pandoc"], engine, [Path(__file__)], [], ROOT, export=export), ["pandoc"])
                self.assertEqual(out.getvalue().count("NOTE  column-estimate"), 1)
                self.assertIn("using count", out.getvalue())
                run.assert_not_called()

    def test_failed_measurement_keeps_the_build_command_and_names_cause(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from pdfmd_tables.measure import prepare
        with mock.patch("pdfmd_tables.measure.requested", return_value=True), mock.patch.object(
                pdfmd, "which", return_value=sys.executable), mock.patch("pdfmd_tables.measure.run", return_value=
                subprocess.CompletedProcess([], 1, "", "error: bad measurement")), redirect_stderr(StringIO()) as out:
            state = {}
            for _ in range(2):
                self.assertEqual(prepare(["pandoc"], "xelatex", [Path(__file__)], [], ROOT, state=state), ["pandoc"])
        self.assertEqual(out.getvalue().count("WARN  column-estimate"), 1)
        self.assertIn("bad measurement", out.getvalue())

    def test_dump_preserves_filter_order_and_engine_options_are_separate(self):
        from pdfmd_tables.measure import dump_command, engine_options
        width = Path("width.lua")
        command = ["pandoc", "input.md", "--lua-filter", str(width), "--lua-filter", "after.lua",
                   "--pdf-engine=xelatex", "--pdf-engine-opt=-shell-escape", "-o", "old.pdf"]
        dumped = dump_command(command, Path("measure.tex"), width)
        self.assertLess(dumped.index(str(width)), dumped.index("after.lua"))
        self.assertNotIn("old.pdf", dumped)
        self.assertNotIn("--pdf-engine=xelatex", dumped)
        self.assertEqual(engine_options(command), ["-shell-escape"])

    def test_parse_records_and_reject_invalid_dimensions(self):
        from pdfmd_tables.measure import parse_latex
        data = parse_latex("T 1 400.0 12.0\nC 1 1 1 50.5\nW 1 1 1 10.0\nW 1 1 1 20.5\n")
        self.assertEqual(data["tables"]["1"]["cells"], [[{"width": 50.5, "word": 20.5}]])
        for value in ("nan", "-1", "0"):
            with self.assertRaises(ValueError):
                parse_latex(f"T 1 {value} 12\n")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class MeasuredAlgorithm(unittest.TestCase):
    def apply(self, text, table, *args):
        from tests.test_table_widths import widths
        with tempfile.TemporaryDirectory(prefix="pdfmd-measured-algorithm-") as folder:
            path = Path(folder) / "widths.json"
            path.write_text(json.dumps({"tables": {"1": table}}), encoding="utf-8")
            return widths(text, "-M", "pdfmd-column-estimate=measure", "-M",
                          "pdfmd-column-measurements=" + str(path), *args)[0]

    def test_points_drive_allocation_and_count_override_stays_natural(self):
        text = "| A | B |\n|---|---|\n| iii iii iii | WWW WWW WWW |\n"
        data = {"line": 100, "sep": 10, "cells": [[{"width": 5, "word": 5}]*2,
                [{"width": 50, "word": 10}, {"width": 150, "word": 30}]]}
        measured = self.apply(text, data)
        self.assertGreater(measured[1], measured[0])
        self.assertAlmostEqual(sum(measured), 1)
        self.assertEqual(self.apply("---\npdfmd-options: {column-estimate: count}\n---\n" + text, data), [None, None])

    def test_word_floor_cap_uses_measured_points_per_character(self):
        # Equal counted lengths, but 4 points/character in the first column. Limit 4 means a 16-point floor.
        text = "| aa | bb |\n|-|---------|\n| aaaaaaaa | bbbbbbbb |\n"
        data = {"line": 120, "sep": 10, "cells": [[{"width": 8, "word": 8}, {"width": 4, "word": 4}],
                [{"width": 32, "word": 32}, {"width": 16, "word": 16}]]}
        result = self.apply(text, data, "--columns=10", "-M", "pdfmd-column-word-floor-limit=4")
        self.assertAlmostEqual(result[0], 0.16)

    def test_outlier_minimum_stays_in_characters(self):
        from tests.test_table_widths import SITES
        data = {"line": 100, "sep": 2, "cells": [[{"width": a, "word": 3}, {"width": b, "word": 3},
                {"width": c, "word": 3}] for a, b, c in [(10,10,10),(14,20,34),(3,15,20),(3,12,0),(14,66,20),(14,10,0)]]}
        # Scaling the measured dimensions changes no character-based eligibility.
        base = self.apply(SITES, data)
        off = self.apply(SITES, data, "-M", "pdfmd-column-outlier-length=80")
        self.assertGreater(off[1], base[1])


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("xelatex"), "needs Pandoc and XeLaTeX")
class Latex(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pdfmd-measure-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def build(self, text=TEXT, *args):
        source = self.folder / "d.md"
        source.write_text(text, encoding="utf-8")
        target = self.folder / "out.pdf"
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(source),
                               "-e", "xelatex", "-o", str(target), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                                   "XDG_CACHE_HOME": str(self.folder / "cache")})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done, target.read_bytes()

    def test_printed_widths_and_linewidth_are_cached(self):
        done, measured = self.build()
        records = list((self.folder / "cache").rglob("column-measure/*.json"))
        self.assertEqual(len(records), 1, done.stderr)
        data = json.loads(records[0].read_text(encoding="utf-8"))
        table = data["tables"]["1"]
        self.assertGreater(table["line"], 200)
        self.assertGreater(table["sep"], 0)
        left, right = table["cells"][1]
        self.assertGreater(right["width"], left["width"] * 2)
        self.assertGreater(right["word"], left["word"] * 2)
        self.assertAlmostEqual(table["cells"][2][0]["width"], 20, places=3)
        stamp = records[0].stat().st_mtime_ns
        self.build()
        self.assertEqual(records[0].stat().st_mtime_ns, stamp)
        _, counted = self.build(TEXT.replace("measure", "count"))
        self.assertNotEqual(measured, counted)


if __name__ == "__main__":
    unittest.main()
