"""Opt-in column measurements use the build's writer, engine and page setup."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
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

INLINE_CODE = """---
pdfmd-options: {column-estimate: measure, stamp: off}
---

| Phrase | Longest segment | Identifier |
|---|---|---|
| **`read configuration twice`** | **`configuration`** | `cached_configuration_revision` |
"""

CODE_LAYOUT = """---
geometry: textwidth=450pt
pdfmd-options: {column-widths: force, column-estimate: measure, stamp: off}
---

| Signal | Inspect | Explanation |
|-------------|----------|---------------------|
| Local and remote catalogues disagree | A copy of the local manifest | Refresh the local catalogue before asking the operator to restore the latest backup. |
| Stale copy | Recorded revision number | Compare the recorded revision with the manifest and repeat the export once they agree. |
| `the current configuration file could not be found` | Settings in the active runner | Read the runner settings and check if the file moved when the workspace was restored. |
| Blank status | Log from the previous attempt | Find the last completed step in the process log and verify its write permission. |
| Timeout | Jobs still active in the queue | Let active jobs finish, then check for a slow step in the queue before retrying. |
| Retry | Most recent complete result | Publish the new report once the last result is complete and the checks have passed. |
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

    def test_typst_failure_warns_once_even_without_a_diagnostic(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from pdfmd_tables.measure import prepare
        with mock.patch("pdfmd_tables.measure.requested", return_value=True), mock.patch.object(
                pdfmd, "which", return_value=sys.executable), mock.patch("pdfmd_tables.measure.run", return_value=
                subprocess.CompletedProcess([], 1, "", "  \n")), redirect_stderr(StringIO()) as out:
            state = {}
            for _ in range(2):
                self.assertEqual(prepare(["pandoc"], "typst", [Path(__file__)], [], ROOT, state=state), ["pandoc"])
        self.assertEqual(out.getvalue().count("WARN  column-estimate"), 1)
        self.assertIn("measurement Pandoc: no diagnostic", out.getvalue())

    def test_typst_query_failure_keeps_count_and_names_the_engine_cause(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from pdfmd_tables.measure import prepare
        with tempfile.TemporaryDirectory(prefix="pdfmd-query-failure-") as folder:
            def run(command, *args):
                if "-o" in command:
                    Path(command[command.index("-o") + 1]).write_text("#metadata(()) <pdfmd-measure>", encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(command, 1, "", "error: font unavailable")
            with mock.patch("pdfmd_tables.measure.requested", return_value=True), mock.patch.object(
                    pdfmd, "which", return_value=sys.executable), mock.patch.object(
                    pdfmd, "cache_root", return_value=Path(folder)), mock.patch(
                    "pdfmd_tables.measure.run", side_effect=run) as invoked, redirect_stderr(StringIO()) as out:
                command = ["pandoc", "--pdf-engine=typst", "--pdf-engine-opt=--font-path=fonts"]
                state = {}
                for _ in range(2):
                    self.assertEqual(prepare(command, "typst", [Path(__file__)], [], ROOT, state=state), command)
            self.assertEqual(invoked.call_count, 2)
            query = invoked.call_args.args[0]
            self.assertIn("query", query)
            self.assertIn("--font-path=fonts", query)
            self.assertEqual(out.getvalue().count("WARN  column-estimate"), 1)
            self.assertIn("measurement typst: error: font unavailable", out.getvalue())

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

    def test_office_collection_does_not_measure_but_final_render_does(self):
        from types import SimpleNamespace
        from pdfmd_office.build import build_office_pandoc
        with tempfile.TemporaryDirectory(prefix="pdfmd-office-measure-") as folder:
            scratch = Path(folder)
            arguments = SimpleNamespace(context={"target": "typst"}, scratch=scratch, filter_arguments=["filter"])
            command = ["pandoc", "d.md", "--pdf-engine=typst", "-o", str(scratch / "out.pdf")]
            def run(cmd, **kwargs):
                if "pdfmd-office-mode=collect" in cmd:
                    (scratch / "wanted.json").write_text("[]", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            prepare = mock.Mock(side_effect=lambda cmd: [*cmd, "-M", "prepared=true"])
            with mock.patch.object(pdfmd, "office_module", return_value=object()), mock.patch(
                    "pdfmd_office.build.subprocess.run", side_effect=run), mock.patch.object(pdfmd, "log_cmd"):
                build_office_pandoc(command, scratch / "out.pdf", arguments, scratch, False, prepare_command=prepare)
            self.assertEqual(prepare.call_count, 1)
            self.assertEqual(prepare.call_args.args[0], command)

    def test_typst_records_reject_invalid_measurements(self):
        from pdfmd_tables.measure import parse_typst
        records = [{"kind": "T", "table": "1", "line": 120, "sep": 12, "inset": 12, "gutter": 0},
                   {"kind": "C", "table": "1", "row": 1, "col": 1, "width": 50},
                   {"kind": "W", "table": "1", "row": 1, "col": 1, "width": 20}]
        self.assertEqual(parse_typst(json.dumps(records))["tables"]["1"]["cells"], [[{"width": 50, "word": 20}]])
        for value in (float("nan"), float("inf"), -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_typst(json.dumps([records[0], {**records[1], "width": value}]))
        for values in ({"line": 0}, {"line": 10}, {"inset": float("inf")}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                parse_typst(json.dumps([{**records[0], **values}, records[1]]))
        with self.assertRaises(ValueError):
            parse_typst(json.dumps([records[0]]))

    def test_parse_records_and_reject_invalid_dimensions(self):
        from pdfmd_tables.measure import parse_latex
        data = parse_latex("T 1 400.0 12.0\nC 1 1 1 50.5\nW 1 1 1 10.0\nW 1 1 1 20.5\n")
        self.assertEqual(data["tables"]["1"]["cells"], [[{"width": 50.5, "word": 20.5}]])
        for value in ("nan", "-1", "0"):
            with self.assertRaises(ValueError):
                parse_latex(f"T 1 {value} 12\n")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class MeasuredAlgorithm(unittest.TestCase):
    @staticmethod
    def apply(text, table, *args):
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

    def test_latex_word_dump_respects_the_writer_syntax(self):
        from tests.test_table_widths import FILTER
        text = "| Plain | Language |\n|---|---|\n| `word  word` | `word word`{.python} |\n"
        command = ["pandoc", "-f", "markdown", "-t", "latex", "--lua-filter", str(FILTER),
                   "-M", "pdfmd-column-estimate=measure", "-M", "pdfmd-measure-role=dump"]
        for options, expected in (([], (2, 1)), (["--listings"], (1, 1)), (["--no-highlight"], (2, 2))):
            with self.subTest(options=options):
                done = subprocess.run([*command, *options], input=text, capture_output=True, encoding="utf-8", check=True)
                actual = tuple(done.stdout.count(rf"\pdfmdword{{1}}{{2}}{{{col}}}{{") for col in (1, 2))
                self.assertEqual(actual, expected)

    def test_word_floor_cap_uses_measured_points_per_character(self):
        # Equal counted lengths, but 4 points/character in the first column. Limit 4 means a 16-point floor.
        text = "| aa | bb |\n|-|---------|\n| aaaaaaaa | bbbbbbbb |\n"
        data = {"line": 120, "sep": 10, "cells": [[{"width": 8, "word": 8}, {"width": 4, "word": 4}],
                [{"width": 32, "word": 32}, {"width": 16, "word": 16}]]}
        result = self.apply(text, data, "--columns=10", "-M", "pdfmd-column-word-floor-limit=4",
                              "-M", "pdfmd-column-ceil-margin=0")  # the floor alone: no ceiling (3.34.56)
        self.assertAlmostEqual(result[0], 0.16)

    def test_typst_count_override_and_failed_measurement_preserve_the_writer(self):
        from tests.test_table_widths import SITES, FILTER
        base = ["pandoc", "-f", "markdown", "-t", "typst"]
        plain = subprocess.run(base, input=SITES, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        for mode in ("count", "measure"):
            filtered = subprocess.run([*base, "--lua-filter", str(FILTER), "-M", "pdfmd-column-estimate=" + mode],
                                      input=SITES, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(filtered.returncode, 0, filtered.stderr)
            self.assertEqual(filtered.stdout, plain.stdout)

    def test_typst_measured_percentages_reserve_inset_and_gutters(self):
        from tests.test_table_widths import FILTER
        table = {"line": 120, "sep": 15.5, "inset": 14, "gutter": 3,
                 "cells": [[{"width": 5, "word": 5}] * 2,
                           [{"width": 90, "word": 12}, {"width": 270, "word": 36}]]}
        text = "| A | B |\n|---|---|\n| iii iii iii | WWW WWW WWW |\n\n: Caption\n"
        with tempfile.TemporaryDirectory(prefix="pdfmd-typst-widths-") as folder:
            path = Path(folder) / "widths.json"
            path.write_text(json.dumps({"tables": {"1": table}}), encoding="utf-8")
            for extra in ([], ["-M", "lot=true"]):
                with self.subTest(extra=extra):
                    done = subprocess.run(["pandoc", "-f", "markdown", "-t", "typst", "--lua-filter", str(FILTER),
                                           "--lua-filter", str(ROOT / "lib" / "pdfmd_lua" / "typst.lua"),
                                           "-M", "pdfmd-column-estimate=measure", "-M",
                                           "pdfmd-column-measurements=" + str(path), *extra],
                                          input=text, capture_output=True, text=True, encoding="utf-8")
                    self.assertEqual(done.returncode, 0, done.stderr)
                    columns = re.search(r"columns: \(([^)]+)\)", done.stdout)
                    self.assertIsNotNone(columns, done.stdout)
                    left, right = [float(value) / 100 for value in re.findall(r"([0-9.]+)%", columns[1])]
                    self.assertGreater(right, left)
                    self.assertAlmostEqual((left + right) * 120 + 3, 120, places=2)
                    self.assertGreater(left * 120, 14)  # each percentage includes that column's inset
                    if extra:
                        self.assertIn("target: figure.where(kind: table)", done.stdout)
                        self.assertIn("caption: [Caption]", done.stdout)

    def test_outlier_minimum_stays_in_characters(self):
        from tests.test_table_widths import SITES
        data = {"line": 100, "sep": 2, "cells": [[{"width": a, "word": 3}, {"width": b, "word": 3},
                {"width": c, "word": 3}] for a, b, c in [(10,10,10),(14,20,34),(3,15,20),(3,12,0),(14,66,20),(14,10,0)]]}
        # Scaling the measured dimensions changes no character-based eligibility.
        base = self.apply(SITES, data)
        off = self.apply(SITES, data, "-M", "pdfmd-column-outlier-length=80")
        self.assertGreater(off[1], base[1])


class Build(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pdfmd-measure-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def build(self, text=TEXT, *args):
        source = self.folder / "d.md"
        source.write_text(text, encoding="utf-8")
        target = self.folder / "out.pdf"
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(source),
                               "-e", getattr(self, "engine", "xelatex"), "-o", str(target), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                                   # pdfmd's cache is under LOCALAPPDATA on Windows, XDG_CACHE_HOME elsewhere
                                   "XDG_CACHE_HOME": str(self.folder / "cache"), "LOCALAPPDATA": str(self.folder / "cache")})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done, target.read_bytes()

    def measurements(self, done):
        records = list((self.folder / "cache").rglob("column-measure/*.json"))
        self.assertEqual(len(records), 1, done.stderr)
        return json.loads(records[0].read_text(encoding="utf-8"))["tables"]["1"]


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("pdflatex"), "needs Pandoc and pdfLaTeX")
class InlineCodeLatex(Build):
    engine = "pdflatex"

    def test_inline_code_measures_the_full_phrase_and_each_word(self):
        done, _ = self.build(INLINE_CODE)
        phrase, longest, identifier = self.measurements(done)["cells"][1]
        self.assertGreater(phrase["width"], 1.5 * longest["width"])
        self.assertAlmostEqual(phrase["word"], longest["width"], places=3)
        self.assertGreater(identifier["word"], longest["width"])
        self.assertAlmostEqual(identifier["word"], identifier["width"], places=3)

    def test_forced_measured_layout_gives_the_explanation_room(self):
        done, _ = self.build(CODE_LAYOUT)
        table = self.measurements(done)
        with self.subTest("balanced widths"):
            fractions = MeasuredAlgorithm.apply(CODE_LAYOUT, table)
            self.assertLess(fractions[0], 0.35, fractions)
            self.assertGreater(fractions[2], 0.43, fractions)
        with self.subTest("author-specified widths"):
            kept = CODE_LAYOUT.replace("column-widths: force", "column-widths: keep")
            self.assertEqual(MeasuredAlgorithm.apply(kept, table), [13 / 44, 10 / 44, 21 / 44])

        def height():
            done = subprocess.run(["pdftotext", "-bbox", str(self.folder / "out.pdf"), "-"],
                                  capture_output=True, encoding="utf-8", check=True)
            pages = ET.fromstring(done.stdout).findall(".//{*}page")
            self.assertEqual(len(pages), 1)
            words = pages[0].findall(".//{*}word")
            top = next(float(word.attrib["yMin"]) for word in words if word.text == "Signal")
            bottom = next(float(word.attrib["yMax"]) for word in words if word.text == "passed.")
            return bottom - top

        with self.subTest("rendered height"):
            if not shutil.which("pdftotext"):
                self.skipTest("needs pdftotext")
            measured = height()
            self.build(CODE_LAYOUT.replace("column-estimate: measure", "column-estimate: count"))
            counted = height()
            self.assertLessEqual(measured, 1.10 * counted, (measured, counted))


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("xelatex"), "needs Pandoc and XeLaTeX")
class Latex(Build):
    def test_a_temporary_folder_with_a_tilde_is_measured(self):
        # Windows' short folder names (C:\\Users\\RUNNER~1\\...) put `~` in the temporary folder. The engine was given the
        # measuring file's absolute path, which TeX reads with `~` active: "I can't find file", and the build fell back
        # to the count (the branch CI's windows-latex job, v3.33.333)
        tilde = self.folder / "a~b"
        tilde.mkdir()
        with mock.patch.dict(os.environ, {"TMPDIR": str(tilde), "TEMP": str(tilde), "TMP": str(tilde)}):
            done, _ = self.build()
        self.assertNotIn("measurement failed", done.stderr)
        self.assertEqual(len(list((self.folder / "cache").rglob("column-measure/*.json"))), 1, done.stderr)

    def test_printed_widths_and_linewidth_are_cached(self):
        done, measured = self.build(TEXT, "--verbose")
        engine = getattr(self, "engine", "xelatex")
        self.assertIn(f"MEASURE  {engine}: measured widths for 1 table(s)", done.stderr)
        self.assertIn("table 1: line", done.stderr)
        records = list((self.folder / "cache").rglob("column-measure/*.json"))
        self.assertEqual(len(records), 1, done.stderr)
        data = json.loads(records[0].read_text(encoding="utf-8"))
        table = data["tables"]["1"]
        self.assertGreater(table["line"], 200)
        self.assertGreater(table["sep"], 0)
        if engine == "typst":
            self.assertAlmostEqual(table["inset"], 12)  # both supported Pandoc writers use a 6pt default
        left, right = table["cells"][1]
        self.assertGreater(right["width"], left["width"] * 2)
        self.assertGreater(right["word"], left["word"] * 2)
        self.assertAlmostEqual(table["cells"][2][0]["width"], 20, places=3)
        stamp = records[0].stat().st_mtime_ns
        reused, _ = self.build(TEXT, "--verbose")
        self.assertIn(f"MEASURE  {engine}: cached widths for 1 table(s)", reused.stderr)
        self.assertEqual(records[0].stat().st_mtime_ns, stamp)
        _, counted = self.build(TEXT.replace("measure", "count"))
        self.assertNotEqual(measured, counted)


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("typst"), "needs Pandoc and Typst")
class Typst(Build):
    engine = "typst"

    def build(self, text=TEXT, *args):
        text = text.replace("`\\rule{20pt}{1pt}`{=latex}", "`#box(width:20pt,height:1pt)`{=typst}")
        return super().build(text, *args)

    test_printed_widths_and_linewidth_are_cached = Latex.test_printed_widths_and_linewidth_are_cached
    test_inline_code_measures_the_full_phrase_and_each_word = (
        InlineCodeLatex.test_inline_code_measures_the_full_phrase_and_each_word)

    def test_relative_image_is_measured_from_its_document_folder(self):
        import struct
        import zlib
        def chunk(kind, data):
            return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data) & 0xffffffff)
        picture = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", 1, 1, 8, 2, 0, 0, 0)) +
                   chunk(b"IDAT", zlib.compress(b"\x00\x20\x80\xc0")) + chunk(b"IEND", b""))
        (self.folder / "tiny.png").write_bytes(picture)
        self.build(TEXT + "| ![tiny](tiny.png){width=10pt} | image |\n")
        record = next((self.folder / "cache").rglob("column-measure/*.json"))
        data = json.loads(record.read_text(encoding="utf-8"))
        self.assertAlmostEqual(data["tables"]["1"]["cells"][-1][0]["width"], 10, places=3)

    def test_count_keep_and_disabled_measure_leave_no_measurements(self):
        for text, args in ((TEXT.replace("measure", "count"), ()),
                           (TEXT.replace("column-estimate: measure", "column-estimate: measure\n  column-widths: keep"), ()),
                           (TEXT, ("--no-auto", "tablewidth"))):
            with self.subTest(args=args, text=text):
                done, _ = self.build(text, *args)
                self.assertEqual(list((self.folder / "cache").rglob("column-measure/*.json")), [])
                self.assertNotIn("WARN  column-estimate", done.stderr)
                self.assertNotIn("MEASURE  typst:", done.stderr)

    def test_latex_cells_are_measured_after_office_conversion(self):
        # A Typst build converts raw LaTeX only when the document asks (or when pdfmd falls back to Typst because no LaTeX
        # engine works, as in a sandbox): ask, so the test does not depend on the machine's engines
        text = (TEXT.replace("  stamp: off\n", "  stamp: off\n  office: {latex: auto}\n")
                + r"| `\textbf{iiiiiiiiii}`{=latex} | `\textbf{WWWWWWWWWW}`{=latex} |" + "\n")
        done, _ = self.build(text)
        records = list((self.folder / "cache").rglob("column-measure/*.json"))
        self.assertEqual(len(records), 1, done.stderr)
        cells = json.loads(records[0].read_text(encoding="utf-8"))["tables"]["1"]["cells"]
        left, right = cells[-1]
        self.assertGreater(left["width"], 0)
        self.assertGreater(right["width"], 2 * left["width"])

    def test_page_and_table_gutter_are_measured(self):
        text = TEXT.replace("pdfmd-options:", "papersize: a5\npdfmd-options:")
        before = self.folder / "before.typ"
        before.write_text("#set table(inset: 7pt, column-gutter: 3pt)", encoding="utf-8")
        self.build(text, "--include-before-body", str(before))
        records = list((self.folder / "cache").rglob("column-measure/*.json"))
        self.assertEqual(len(records), 1)
        data = json.loads(records[0].read_text(encoding="utf-8"))["tables"]["1"]
        self.assertLess(data["line"], 300)
        written = subprocess.run(["pandoc", "-f", "markdown", "-t", "typst"], input="| A | B |\n|---|---|\n| a | b |\n",
                                 capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(written.returncode, 0, written.stderr)
        # Older writers override #set table(inset: 7pt) in every table; measure the inset the writer actually uses.
        explicit = re.search(r"\n[ ]*inset: ([0-9.]+)pt,", written.stdout)
        inset = 2 * float(explicit[1]) if explicit else 14
        self.assertAlmostEqual(data["sep"], inset + 1.5)
        self.assertAlmostEqual(data["inset"], inset)
        self.assertAlmostEqual(data["gutter"], 3)


if __name__ == "__main__":
    unittest.main()
