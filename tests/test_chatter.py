"""The console level can change what a build says while keeping its status."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
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
