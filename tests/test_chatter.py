"""The console level can change what a build says while keeping its status."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Chatter(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        # A metadata.yaml beside the config is global metadata.
        self.config = self.folder / "config" / "config.yaml"
        self.config.parent.mkdir()
        self.settings()
        self.write("a.md")
        metadata = self.folder / "metadata.yaml"
        metadata.write_text("title: Sample\n", encoding="utf-8")

    def settings(self, text=""):
        self.config.write_text(f"options:\n  soffice-timeout: 0\n{text}", encoding="utf-8")

    def write(self, name, options="", body="| A | B |\n|---|---|\n| 1 | 2 | 3 |\n"):
        (self.folder / name).write_text(f"{options}# Sample\n\n{body}", encoding="utf-8")

    def run_pdfmd(self, *args):
        # Strict tests count table warnings independently of the machine's fonts.
        command = [sys.executable, str(ROOT / "scripts" / "pdfmd"), "--rewrite", "--to", "latex",
                   "--no-build-time", "--path-style", "relative", *args, "--no-auto", "font", "unicode"]
        return subprocess.run(
            command,
            cwd=self.folder, env={**os.environ, "PDFMD_CONFIG": str(self.config), "PDFMD_NO_PROMPT": "1"},
            capture_output=True, encoding="utf-8", timeout=90)

    def test_console_levels_and_status(self):
        for level in ("off", "result", "warnings", "normal", "verbose", "debug"):
            with self.subTest(level=level):
                done = self.run_pdfmd("a.md", "--chatter", level)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual("OK    a.md > a.tex" in done.stdout, level != "off")
                self.assertEqual("WARN  table-repair:" in done.stdout, level not in ("off", "result"))
                self.assertEqual("FOUND" in done.stdout, level == "normal")
                self.assertEqual("AUTO YAML" in done.stdout, level in ("verbose", "debug"))
                if level == "off":
                    self.assertEqual(done.stdout, "")
                if level == "result":
                    self.assertEqual(done.stdout, "OK    a.md > a.tex\n")

    def test_off_keeps_strict_failure_on_stderr(self):
        done = self.run_pdfmd("a.md", "--strict", "--chatter=off")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")
        self.assertIn("--strict: the build printed", done.stderr)
        self.assertIn("WARN  table-repair:", done.stderr)

    def test_counted_quiet_levels_and_precedence(self):
        self.settings("  chatter: verbose\n")
        self.write("a.md", "---\npdfmd-options: {chatter: off}\n---\n\n")
        for flags, warning, result in [(("-q",), True, True), (("-qq",), False, True),
                                       (("-q", "-qq"), False, False),
                                       (("--chatter=result", "-q"), False, True)]:
            with self.subTest(flags=flags):
                done = self.run_pdfmd("a.md", *flags)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual("WARN  table-repair:" in done.stdout, warning)
                self.assertEqual("OK    a.md > a.tex" in done.stdout, result)
                self.assertNotIn("FOUND", done.stdout)
                self.assertNotIn("AUTO YAML", done.stdout)

    def test_quiet_usage_errors(self):
        for flag in ("-v", "--verbose", "--debug", "-qqq"):
            with self.subTest(flag=flag):
                done = self.run_pdfmd("a.md", "-q", flag)
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertIn("-q", done.stderr)
                if flag != "-qqq":
                    self.assertIn(flag, done.stderr)
                else:
                    self.assertIn("at most three", done.stderr)

    def test_quiet_workers_and_strict_status(self):
        self.write("b.md")
        done = self.run_pdfmd("-b", "-j", "2", "a.md", "b.md", "-qq")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines(), ["OK    a.md > a.tex", "OK    b.md > b.tex"])
        done = self.run_pdfmd("a.md", "-qqq", "--strict")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")
        self.assertIn("--strict: the build printed", done.stderr)

    def test_metadata_can_set_the_level(self):
        (self.folder / "metadata.yaml").write_text("pdfmd-options: {chatter: result}\n", encoding="utf-8")
        self.settings("  chatter: warnings\n")
        done = self.run_pdfmd("a.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "OK    a.md > a.tex\n")

    def test_log_appends_complete_diagnostics_with_a_quiet_console(self):
        log = self.folder / "build.log"
        previous = "earlier entry\n"
        log.write_text(previous, encoding="utf-8")
        for _ in range(2):
            done = self.run_pdfmd("a.md", "-qqq", "--log", log.name)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(done.stdout, "")
            saved = log.read_text(encoding="utf-8")
            self.assertTrue(saved.startswith(previous))
            added = saved[len(previous):]
            header = added.splitlines()[0]
            self.assertRegex(header, r"^pdfmd \d+\.\d+\.\d+  \S+  a\.md > a\.tex$")
            datetime.fromisoformat(header.split()[2])
            for line in ("WARN  table-repair:", "FOUND     metadata.yaml", "DEFAULTS  margin", "AUTO:",
                         "AUTO YAML", "OK    a.md > a.tex"):
                self.assertIn(line, added)
            previous = saved

    def test_log_records_accepted_and_failed_diagnostics(self):
        self.write("a.md", body="A | B\nC | D\n\n| X | Y |\n|---|---|\n| 1 | 2 | 3 |\n")
        done = self.run_pdfmd("a.md", "-qqq", "--log", "build.log", "--mute=table-mismatch,YAML", "--strict")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        saved = (self.folder / "build.log").read_text(encoding="utf-8")
        self.assertRegex(saved, r"WARN  table-repair:[^\n]+ \(muted\)")
        self.assertIn("AUTO YAML  metadata.yaml (muted)", saved)
        self.assertIn("--strict: the build printed", saved)

    def test_log_requires_an_existing_parent(self):
        target = Path("absent") / "build.log"
        done = self.run_pdfmd("a.md", "--log", str(target), "-qqq")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("ERROR  --log:", done.stderr)
        self.assertIn(str(target), done.stderr)
        self.assertFalse((self.folder / target.parent).exists())
        self.assertFalse((self.folder / "a.tex").exists())

    def test_log_option_precedence_and_relative_paths(self):
        self.settings("  log: settings.log\n")
        folder = self.folder / "sub"
        folder.mkdir()
        self.write("sub/b.md", "---\npdfmd-options: {log: document.log}\n---\n\n")
        for source, flags, expected in [("a.md", (), self.folder / "settings.log"),
                                         ("sub/b.md", ("--log", "cli.log"), self.folder / "cli.log"),
                                         ("sub/b.md", (), folder / "document.log")]:
            with self.subTest(source=source, flags=flags):
                done = self.run_pdfmd(source, *flags)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertTrue(expected.is_file(), expected)
                expected.unlink()
        self.assertFalse((folder / "settings.log").exists())
        self.assertFalse((self.folder / "document.log").exists())

    def test_log_two_workers_share_one_file(self):
        self.write("b.md")
        (self.folder / "skip.xyz").write_text("not an input", encoding="utf-8")
        done = self.run_pdfmd("-b", "-j", "2", "a.md", "b.md", "skip.xyz", "-qqq", "--log", "build.log")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")
        saved = (self.folder / "build.log").read_text(encoding="utf-8")
        self.assertIn("NOTE  skipped non-input paths: skip.xyz", saved)
        for stem in ("a", "b"):
            self.assertRegex(saved, rf"(?m)^pdfmd [^\n]+ {stem}\.md > {stem}\.tex$")
            self.assertRegex(saved, rf"(?m)^WARN  table-repair: {stem}\.md, line 5: Pandoc can cut a row with 3 cells to 2$")
            self.assertEqual(saved.splitlines().count(f"OK    {stem}.md > {stem}.tex"), 1)
        self.assertEqual(sum(line.startswith("pdfmd ") for line in saved.splitlines()), 2)

    def test_log_report_has_one_header_and_the_final_output(self):
        self.write("b.md")
        for route in ("route", "patch"):
            with self.subTest(route=route):
                self.settings(f"  report-build: {route}\n")
                done = self.run_pdfmd("-r", "a.md", "b.md", "-qqq", "--log", route + ".log")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(done.stdout, "")
                saved = (self.folder / (route + ".log")).read_text(encoding="utf-8")
                self.assertRegex(saved, r"^pdfmd [^\n]+ a\.md > book\.tex")
                self.assertIn("OK    REPORT  book.tex", saved)
                self.assertEqual(sum(line.startswith("pdfmd ") for line in saved.splitlines()), 1)

    def test_summary_follows_the_result_and_counts_hidden_warnings(self):
        done = self.run_pdfmd("a.md", "-qq", "--summary")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines(), ["OK    a.md > a.tex", "1 warning"])

    def test_summary_omits_accepted_diagnostics_and_zero_counts(self):
        done = self.run_pdfmd("a.md", "-qq", "--summary", "--strict", "--mute=table-mismatch")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "OK    a.md > a.tex\n")

    def test_summary_counts_warning_and_note_totals_across_a_batch(self):
        self.write("b.md")
        (self.folder / "skip.xyz").write_text("not an input", encoding="utf-8")
        for jobs in ("1", "2"):
            with self.subTest(jobs=jobs):
                done = self.run_pdfmd("-b", "-j", jobs, "a.md", "b.md", "skip.xyz", "-qq", "--summary")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(done.stdout.splitlines(),
                                 ["OK    a.md > a.tex", "OK    b.md > b.tex", "2 warnings, 1 note"])

    def test_summary_preserves_strict_status_and_is_silent_at_off(self):
        done = self.run_pdfmd("a.md", "-qq", "--summary", "--strict")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines()[-1], "1 warning, 1 error")
        done = self.run_pdfmd("a.md", "-qqq", "--summary", "--strict")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")
        self.assertIn("--strict: the build printed", done.stderr)
        self.assertNotIn("1 warning, 1 error", done.stderr)

    def test_summary_settings_use_document_precedence(self):
        self.settings("  summary: true\n")
        self.write("b.md", "---\npdfmd-options: {summary: false}\n---\n\n")
        self.assertEqual(self.run_pdfmd("a.md", "-qq").stdout.splitlines()[-1], "1 warning")
        self.assertEqual(self.run_pdfmd("b.md", "-qq").stdout, "OK    b.md > b.tex\n")
        self.assertEqual(self.run_pdfmd("b.md", "-qq", "--summary").stdout.splitlines()[-1], "1 warning")
        self.settings("  summary: false\n")
        self.write("b.md", "---\npdfmd-options: {summary: true}\n---\n\n")
        done = self.run_pdfmd("-b", "-j", "2", "a.md", "b.md", "-qq")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines()[-1], "2 warnings")

    def test_explicit_metadata_is_resolved_before_reading_its_settings(self):
        (self.folder / "explicit.yaml").write_text(
            "pdfmd-options: {chatter: result, mute: [table-mismatch]}\n", encoding="utf-8")
        done = self.run_pdfmd("a.md", "--strict", "-y", "explicit.yaml")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "OK    a.md > a.tex\n")

    def test_report_result_only_shows_the_report(self):
        self.write("b.md")
        done = self.run_pdfmd("-r", "a.md", "b.md", "--chatter=result")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "OK    REPORT  book.tex\n")

    def test_precedence_and_batch_documents(self):
        self.settings("  chatter: warnings\n")
        self.write("a.md", "---\npdfmd-options: {chatter: off}\n---\n\n")
        self.write("b.md")
        self.assertEqual(self.run_pdfmd("a.md").stdout, "")
        forced = self.run_pdfmd("a.md", "--chatter=result")
        self.assertEqual(forced.stdout, "OK    a.md > a.tex\n")
        for jobs in ("1", "2"):
            with self.subTest(jobs=jobs):
                batch = self.run_pdfmd("-b", "-j", jobs, "a.md", "b.md")
                self.assertEqual(batch.returncode, 0, batch.stdout + batch.stderr)
                self.assertNotIn("a.md", batch.stdout)
                self.assertIn("WARN  table-repair: b.md", batch.stdout)
                self.assertIn("OK    b.md > b.tex", batch.stdout)
                self.assertNotIn("FOUND", batch.stdout)

    def test_muting_a_warning_accepts_it_under_strict(self):
        done = self.run_pdfmd("a.md", "--strict", "--mute", "table-mismatch")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("WARN  table-repair:", done.stdout)
        self.assertIn("OK    a.md > a.tex", done.stdout)

        self.write("a.md", body="A | B\nC | D\n\n| X | Y |\n|---|---|\n| 1 | 2 | 3 |\n")
        done = self.run_pdfmd("a.md", "--strict", "--mute", "table-mismatch")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("WARN  table-unparsed:", done.stdout)
        self.assertNotIn("WARN  table-repair:", done.stdout)
        done = self.run_pdfmd("a.md", "--strict", "--mute", "table-mismatch, table-unparsed")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_muting_an_auto_kind_in_both_displays(self):
        for level in ("normal", "verbose"):
            with self.subTest(level=level):
                done = self.run_pdfmd("a.md", "--chatter", level, "--mute", "yAmL")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertNotIn("FOUND", done.stdout)
                self.assertNotIn("AUTO YAML", done.stdout)
                self.assertIn("WARN  table-repair:", done.stdout)

    def test_muting_from_setup_and_document_in_workers(self):
        self.settings("  mute: [table-mismatch]\n")
        self.write("b.md", "---\npdfmd-options: {mute: []}\n---\n\n")
        done = self.run_pdfmd("-b", "-j", "2", "a.md", "b.md", "--strict")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("OK    a.md > a.tex", done.stdout)
        self.assertNotIn("table-repair: a.md", done.stdout)
        self.assertIn("table-repair: b.md", done.stdout)
        done = self.run_pdfmd("-b", "-j", "2", "a.md", "b.md", "--strict", "--mute=table-mismatch")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_check_accepts_muted_warnings(self):
        self.write("a.md", body="Opening paragraph.\n\n### Jump\n\nAnother paragraph.\n")
        done = self.run_pdfmd("a.md", "--check", "--strict")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("[heading-jump]", done.stdout)
        done = self.run_pdfmd("a.md", "--check", "--strict", "--mute=heading-jump")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("[heading-jump]", done.stdout)


if __name__ == "__main__":
    unittest.main()
