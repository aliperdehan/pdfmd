"""v3.31.4: how long a build took. The formats (pdfmd_buildinfo.timing), the closing line, `build-time` / `time-format`
at every level, the step lines of --verbose, and `took=` in the history file."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
from pdfmd_buildinfo import Timer, check_style, format_duration  # noqa: E402

TIME_ON_THE_LINE = r"(?m)^OK    d\.md > d\.html  in [\d.:]+(?: s)?$"


class Formats(unittest.TestCase):
    def test_auto_by_size(self):
        for seconds, text in [(0, "0.00 s"), (0.004, "0.00 s"), (0.42, "0.42 s"), (12.44, "12.4 s"), (59.94, "59.9 s"),
                              (60, "1:00"), (187, "3:07"), (3723, "1:02:03"), (86399, "23:59:59"),
                              (90061, "1 d 01:01:01"), (108000, "1 d 06:00:00")]:
            self.assertEqual(format_duration(seconds), text, seconds)

    def test_auto_rolls_over_instead_of_printing_sixty(self):
        self.assertEqual(format_duration(0.996), "1.0 s")
        self.assertEqual(format_duration(59.96), "1:00")
        self.assertEqual(format_duration(3599.6), "1:00:00")
        self.assertEqual(format_duration(86399.6), "1 d 00:00:00")

    def test_clock_never_wraps_into_days(self):
        self.assertEqual(format_duration(187, "clock"), "03:07")
        self.assertEqual(format_duration(3723, "clock"), "1:02:03")
        self.assertEqual(format_duration(108000, "clock"), "30:00:00")

    def test_seconds_and_words(self):
        self.assertEqual(format_duration(187, "seconds"), "187.0 s")
        self.assertEqual(format_duration(0.42, "seconds"), "0.42 s")
        self.assertEqual(format_duration(12.4, "words"), "12.4 s")
        self.assertEqual(format_duration(187, "words"), "3 min 7 s")
        self.assertEqual(format_duration(3723, "words"), "1 h 2 min 3 s")
        self.assertEqual(format_duration(108000, "words"), "1 d 6 h")

    def test_a_template_wraps_a_unit_only_below_a_larger_one_of_the_template(self):
        self.assertEqual(format_duration(187, "{s} s"), "187 s")
        self.assertEqual(format_duration(187, "{m} min {s} s"), "3 min 7 s")
        self.assertEqual(format_duration(3723, "{h}:{mm}:{ss}"), "1:02:03")
        self.assertEqual(format_duration(3723, "{m} min"), "62 min")
        self.assertEqual(format_duration(108000, "{h} h"), "30 h")
        self.assertEqual(format_duration(108000, "{d} d {hh} h"), "1 d 06 h")
        self.assertEqual(format_duration(12.345, "{s1} s"), "12.3 s")
        self.assertEqual(format_duration(12.345, "{s2} s"), "12.35 s")
        self.assertEqual(format_duration(12.345, "{s}.{ms}"), "12.345")

    def test_a_template_is_rounded_to_its_smallest_unit(self):
        self.assertEqual(format_duration(59.6, "{s} s"), "60 s")
        self.assertEqual(format_duration(119.5, "{m}:{ss}"), "2:00")

    def test_a_bad_style_is_found_and_read_as_auto(self):
        self.assertIsNone(check_style("auto"))
        self.assertIsNone(check_style("{m}:{ss}"))
        self.assertIn("unknown token {q}", check_style("{q}"))
        self.assertIn("neither", check_style("fast"))
        self.assertEqual(format_duration(187, "{q}"), "3:07")
        self.assertEqual(format_duration(float("nan")), "0.00 s")
        self.assertEqual(format_duration(-5), "0.00 s")


class Steps(unittest.TestCase):
    def test_the_timer_counts_from_its_clock_and_nests_steps(self):
        now = [100.0]
        timer = Timer(clock=lambda: now[0])
        with timer.step("outer"):
            now[0] += 2
            with timer.step("inner"):
                now[0] += 3
            now[0] += 1
        now[0] += 4
        self.assertEqual([(s.name, s.depth, s.seconds) for s in timer.steps], [("outer", 0, 6.0), ("inner", 1, 3.0)])
        self.assertEqual(timer.elapsed(), 10.0)

    def test_a_step_that_raises_is_still_timed(self):
        now = [0.0]
        timer = Timer(clock=lambda: now[0])
        with self.assertRaises(ValueError):
            with timer.step("boom"):
                now[0] += 1.5
                raise ValueError
        self.assertEqual(timer.steps[0].seconds, 1.5)


class OnTheClosingLine(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)

    def build(self, *arguments, front=""):
        (self.path / "d.md").write_text(f"---\ntitle: T\n{front}---\n\nText.\n", encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "html", "--no-stamp", *arguments],
                              capture_output=True, text=True, cwd=self.path)

    def test_on_by_default(self):
        self.assertRegex(self.build().stdout, TIME_ON_THE_LINE)

    def test_off_on_the_command_line_and_in_the_document(self):
        self.assertRegex(self.build("--no-build-time").stdout, r"(?m)^OK    d\.md > d\.html$")
        self.assertRegex(self.build(front="pdfmd-options:\n  build-time: off\n").stdout, r"(?m)^OK    d\.md > d\.html$")

    def test_the_command_line_beats_the_document(self):
        self.assertRegex(self.build("--build-time", front="pdfmd-options:\n  build-time: off\n").stdout, TIME_ON_THE_LINE)

    def test_the_format_from_the_document_and_from_the_command_line(self):
        self.assertRegex(self.build(front="pdfmd-options:\n  time-format: clock\n").stdout, r"(?m)^OK    d\.md > d\.html  in \d\d:\d\d$")
        self.assertRegex(self.build("--time-format", "{s1} sec", front="pdfmd-options:\n  time-format: clock\n").stdout,
                         r"(?m)^OK    d\.md > d\.html  in [\d.]+ sec$")

    def test_a_bad_format_stops_the_command_line_and_warns_for_a_document(self):
        done = self.build("--time-format", "{q}")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("unknown token {q}", done.stderr)
        done = self.build(front="pdfmd-options:\n  time-format: '{q}'\n")
        self.assertEqual(done.returncode, 0)
        self.assertIn("unknown token {q}", done.stderr)
        self.assertRegex(done.stdout, TIME_ON_THE_LINE)

    def test_verbose_lists_the_steps(self):
        out = self.build("--verbose").stdout
        self.assertRegex(out, r"(?m)^TIME  \S*d\.md  [\d.:]+")
        self.assertRegex(out, r"(?m)^TIME    \S.*  [\d.:]+")

    def test_a_failed_build_says_how_long_it_ran(self):
        (self.path / "d.md").write_text("---\ntitle: T\n---\n\nText.\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "html", "--template", "missing.html"],
                              capture_output=True, text=True, cwd=self.path)
        self.assertNotEqual(done.returncode, 0)
        self.assertRegex(done.stdout, r"(?m)^FAIL  d\.md  in [\d.:]+(?: s)?$")

    def test_the_history_entry_carries_the_seconds(self):
        (self.path / "d.md").write_text("---\ntitle: T\n---\n\nText.\n", encoding="utf-8")
        subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--stamp-store", "file", "--stamp"],
                       capture_output=True, text=True, cwd=self.path)
        found = list(self.path.rglob("*.hst"))
        self.assertTrue(found)
        self.assertRegex(found[0].read_text(encoding="utf-8"), r"took=\d+\.\d")


class Records(unittest.TestCase):
    def test_a_result_keeps_its_time_through_a_pickle(self):
        import pickle
        built = pdfmd.Built(("a.md", True, ""), "lualatex")
        built.seconds, built.time_text, built.steps = 3.5, "3.5 s", [("pandoc + lualatex", 0, 3.0)]
        again = pickle.loads(pickle.dumps(built))
        self.assertEqual((again.seconds, again.time_text, again.steps), (3.5, "3.5 s", [("pandoc + lualatex", 0, 3.0)]))
        self.assertEqual(pdfmd.time_label(again), "  in 3.5 s")
        self.assertEqual(pdfmd.time_label(pdfmd.Built(("a.md", True, ""))), "")


if __name__ == "__main__":
    unittest.main()
