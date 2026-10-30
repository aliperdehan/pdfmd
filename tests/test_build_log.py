"""v3.31.5: the record of a build. The pure part (pdfmd_buildinfo.record: scrubbing, clipping, naming, pruning) and the
build itself (what is written, when, where, and how a failure points at it)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402,F401
from pdfmd_buildinfo import record  # noqa: E402


class Pure(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)

    def test_the_home_folder_becomes_a_tilde(self):
        self.assertEqual(record.scrub_home("CMD pandoc /home/ann/a.md -o /home/ann/a.pdf", "/home/ann"), "CMD pandoc ~/a.md -o ~/a.pdf")
        self.assertEqual(record.scrub_home("C:/Users/ann/a.md", "C:\\Users\\ann"), "~/a.md")
        self.assertEqual(record.scrub_home("nothing", ""), "nothing")

    def test_a_long_record_keeps_its_start_and_more_of_its_end(self):
        text = "START\n" + "middle\n" * 5000 + "THE ERROR\n"
        clipped = record.clip(text, 3000)
        self.assertTrue(clipped.startswith("START"))
        self.assertTrue(clipped.rstrip().endswith("THE ERROR"))
        self.assertIn("bytes cut out of the middle", clipped)
        self.assertLess(len(clipped.encode()), 3300)
        self.assertEqual(record.clip("short", 3000), "short")

    def test_names_sort_by_time_and_never_collide(self):
        when = datetime(2026, 10, 29, 14, 5, 33)
        first = record.write(self.path, "one", True, 9, 10_000, when, "")
        second = record.write(self.path, "two", True, 9, 10_000, when, "")
        self.assertEqual(first.name, "20261029-140533-ok.log")
        self.assertEqual(second.name, "20261029-140533-2-ok.log")
        self.assertEqual(record.records(self.path), [second, first])
        self.assertEqual(sorted(p.name for p in self.path.iterdir()), sorted([first.name, second.name]))      # no .tmp left

    def test_pruning_keeps_the_newest_and_the_newest_failure(self):
        for second, ok in enumerate([False, True, True, True, True, True]):
            record.write(self.path, f"build {second}", ok, 3, 10_000, datetime(2026, 10, 29, 14, 0, second), "")
        names = [p.name for p in record.records(self.path)]
        self.assertEqual(names, ["20261029-140005-ok.log", "20261029-140004-ok.log", "20261029-140003-ok.log",
                                 "20261029-140000-failed.log"])
        self.assertEqual(record.newest(self.path).name, "20261029-140005-ok.log")
        self.assertEqual(record.newest(self.path, failed=True).name, "20261029-140000-failed.log")

    def test_the_newest_of_several_folders(self):
        other = self.path / "other"
        record.write(self.path, "a", True, 5, 1000, datetime(2026, 10, 29, 14, 0, 0), "")
        record.write(other, "b", True, 5, 1000, datetime(2026, 10, 29, 15, 0, 0), "")
        self.assertEqual(record.newest_of([self.path, other]).parent, other)
        self.assertIsNone(record.newest_of([self.path, other], failed=True))
        self.assertIsNone(record.newest_of([self.path / "none"]))


class VerbosePrint(unittest.TestCase):
    def test_shown_goes_to_the_console_and_hidden_to_the_record_only(self):
        import contextlib
        import io
        import pdfmd
        lines: list[str] = []
        saved = pdfmd.BUILD["record"]
        pdfmd.BUILD["record"] = lines
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                pdfmd.vprint(True, "seen", 1)
                pdfmd.vprint(False, "hidden", 2)
                pdfmd.vprint(False, "a", "b", sep="-")
            self.assertEqual(out.getvalue(), "seen 1\n")
            self.assertEqual(lines, ["hidden 2", "a-b"])
        finally:
            pdfmd.BUILD["record"] = saved

    def test_no_record_running_nothing_happens(self):
        import pdfmd
        saved = pdfmd.BUILD["record"]
        pdfmd.BUILD["record"] = None
        try:
            pdfmd.vprint(False, "nowhere")
        finally:
            pdfmd.BUILD["record"] = saved


class Builds(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)
        self.cache = self.path / "cache"
        self.env = {key: value for key, value in os.environ.items() if key != "PDFMD_BUILD_LOG"}
        self.env["XDG_CACHE_HOME"] = self.env["LOCALAPPDATA"] = str(self.cache)        # the cache folder: XDG, on Windows LOCALAPPDATA
        self.env["PDFMD_NO_PROMPT"] = "1"

    def run_pdfmd(self, *arguments, front="", good=True):
        (self.path / "d.md").write_text(f"---\ntitle: T\n{front}---\n\nText.\n", encoding="utf-8")
        extra = [] if good else ["--template", "missing.html"]
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "html", "--no-stamp", *extra, *arguments],
                              capture_output=True, text=True, cwd=self.path, env=self.env)

    def records(self, base=None):
        return sorted((base or self.cache).rglob("*.log"))

    def test_a_good_build_leaves_a_record_with_what_it_ran(self):
        done = self.run_pdfmd()
        found = self.records()
        self.assertEqual(len(found), 1, done.stderr)
        self.assertTrue(found[0].name.endswith("-ok.log"))
        text = found[0].read_text(encoding="utf-8")
        for expected in ("pdfmd build record", "result:    ok", "command:   pdfmd d.md --to html", "CMD  pandoc d.md",
                         "what pdfmd printed, and what it ran", "TIME  d.md"):
            self.assertIn(expected, text)
        self.assertNotIn("full record", done.stdout)               # nothing to point at when the build went well

    def test_the_record_holds_every_line_that_only_verbose_prints(self):
        quiet = self.run_pdfmd()
        self.assertNotIn("AUTO ", quiet.stdout)                       # the console is as it was without -v
        record_text = self.records()[0].read_text(encoding="utf-8")
        loud = self.run_pdfmd("--verbose", "--build-log", "off")
        auto = [line for line in loud.stdout.splitlines() if line.startswith("AUTO ")]
        self.assertTrue(auto)
        for line in auto:
            self.assertIn(line.split("  ")[0] + "  ", record_text, line)

    def test_verbose_names_the_record(self):
        self.assertRegex(self.run_pdfmd("--verbose").stdout, r"(?m)^RECORD  \S+-ok\.log$")

    def test_a_failed_build_points_at_its_record_and_the_record_says_why(self):
        done = self.run_pdfmd(good=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertRegex(done.stdout, r"(?m)^      full record: \S+-failed\.log$")
        failed = [p for p in self.records() if p.name.endswith("-failed.log")]
        self.assertEqual(len(failed), 1)
        text = failed[0].read_text(encoding="utf-8")
        self.assertIn("result:    FAILED", text)
        self.assertIn("Could not find data file", text)

    def test_a_good_build_after_a_failure_does_not_erase_it(self):
        self.run_pdfmd(good=False)
        self.run_pdfmd()
        self.run_pdfmd()
        shown = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--last-build", "--failed", "d.md"],
                               capture_output=True, text=True, cwd=self.path, env=self.env)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("result:    FAILED", shown.stdout)
        latest = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--last-build", "d.md"],
                                capture_output=True, text=True, cwd=self.path, env=self.env)
        self.assertIn("result:    ok", latest.stdout)

    def test_off_and_failed_only(self):
        self.run_pdfmd("--build-log", "off")
        self.run_pdfmd(front="pdfmd-options:\n  build-log: off\n")
        self.assertEqual(self.records(), [])
        self.run_pdfmd("--build-log", "failed")
        self.assertEqual(self.records(), [])
        self.run_pdfmd("--build-log", "failed", good=False)
        self.assertEqual([p.name.endswith("-failed.log") for p in self.records()], [True])

    def test_the_command_line_beats_the_document(self):
        self.run_pdfmd("--build-log", "on", front="pdfmd-options:\n  build-log: off\n")
        self.assertEqual(len(self.records()), 1)

    def test_only_the_newest_records_stay(self):
        for _ in range(4):
            self.run_pdfmd(front="pdfmd-options:\n  build-log-keep: 2\n")
        self.assertEqual(len(self.records()), 2)

    def test_the_record_can_sit_beside_the_document(self):
        self.run_pdfmd(front="pdfmd-options:\n  cache:\n    location: document\n")
        self.assertEqual(self.records(self.cache), [])
        beside = self.records(self.path / ".cache")
        self.assertEqual(len(beside), 1)
        shown = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--last-build", "d.md"],
                               capture_output=True, text=True, cwd=self.path, env=self.env)
        self.assertIn("pdfmd build record", shown.stdout)

    def test_no_record_is_said_and_fails(self):
        (self.path / "d.md").write_text("---\ntitle: T\n---\n\nText.\n", encoding="utf-8")
        shown = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--last-build", "d.md"],
                               capture_output=True, text=True, cwd=self.path, env=self.env)
        self.assertEqual(shown.returncode, 1)
        self.assertIn("no record of a build", shown.stderr)
        again = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--failed", "d.md"],
                               capture_output=True, text=True, cwd=self.path, env=self.env)
        self.assertIn("--failed goes with --last-build", again.stderr)

    def test_a_cache_that_cannot_be_written_does_not_fail_the_build(self):
        (self.path / "blocked").write_text("a file where the cache folder should be", encoding="utf-8")
        self.env["XDG_CACHE_HOME"] = self.env["LOCALAPPDATA"] = str(self.path / "blocked")
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.path / "d.html").is_file())


if __name__ == "__main__":
    unittest.main()
