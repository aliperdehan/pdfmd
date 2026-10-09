"""--history, --history-diff, --history-restore and --init-backups: a document's versions from backups of every
naming form and folder spelling, git, and its history file."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
import pdfmd_history as history  # noqa: E402

GIT = shutil.which("git")
FRONT = "---\ntitle: R\n---\n\n"


def make(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-versions-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.document = make(self.directory, "report.md", FRONT + "Version five (current).\n")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                    "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@e"}
        patcher = mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_pdfmd(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=cwd or self.directory,
                              capture_output=True, text=True, env=self.env)

    def old_versions(self):
        """Backups in three naming forms and two folder spellings."""
        make(self.directory, "backup/report.md.bak.20261001-090000", FRONT + "Version one.\n")
        make(self.directory, "backup/report_20261002-101500.md", FRONT + "Version two.\n")
        make(self.directory, ".backups/report.md.bak.20261003110005", FRONT + "Version three.\n\n<!-- ====\n"
             "     BUILD NOTES\n\n     Compiled with nulabreport v1.27.7, pdfmd v3.25.5 -- 2026-10-03 11:00:00\n     ==== -->\n")
        make(self.directory, "backups/report.md.20261004-080000.bak", FRONT + "Version four.\n")


class Listing(Base):
    def test_every_folder_spelling_and_every_name_form_is_found_newest_first(self):
        self.old_versions()
        found = pdfmd.document_versions(self.document, [], include_git=False)
        self.assertEqual([version.label for version in found], [
            "report.md.20261004-080000.bak", "report.md.bak.20261003110005", "report_20261002-101500.md",
            "report.md.bak.20261001-090000"])
        self.assertEqual(found[1].summary, "compiled with nulabreport v1.27.7, pdfmd v3.25.5")
        self.assertEqual(found[1].ref, "20261003110005")

    def test_the_command_lists_numbers_truncates_and_shows_all_on_request(self):
        for number in range(1, 21):
            make(self.directory, f".backups/report.md.bak.202610{number:02d}090000", FRONT + f"Version {number}.\n")
        short = self.run_pdfmd("--history", "report.md")
        self.assertEqual(short.returncode, 0, short.stderr)
        self.assertIn("20 versions", short.stdout)
        self.assertIn("  1  ", short.stdout)
        self.assertNotIn(" 16  ", short.stdout)
        self.assertIn("5 older; --history-all lists them", short.stdout)
        every = self.run_pdfmd("--history", "report.md", "--history-all")
        self.assertIn(" 20  ", every.stdout)

    def test_a_document_with_no_versions_says_how_to_start(self):
        done = self.run_pdfmd("--history", "report.md")
        self.assertEqual(done.returncode, 0)
        self.assertIn("no versions found", done.stdout)
        self.assertIn("--init-backups", done.stdout)

    @unittest.skipUnless(GIT, "needs git")
    def test_commits_are_listed_too_even_from_a_repository_above_the_document(self):
        subprocess.run([GIT, "init", "-q", str(self.directory)], check=True, env=self.env)
        sub = self.directory / "sub"
        moved = sub / "report.md"
        sub.mkdir()
        shutil.move(str(self.document), str(moved))
        moved.write_text(FRONT + "Draft one.\n", encoding="utf-8")
        subprocess.run([GIT, "-C", str(self.directory), "add", "-A"], check=True, env=self.env)
        subprocess.run([GIT, "-C", str(self.directory), "commit", "-qm", "first draft"], check=True, env=self.env)
        moved.write_text(FRONT + "Draft two.\n", encoding="utf-8")
        subprocess.run([GIT, "-C", str(self.directory), "commit", "-qam", "second draft"], check=True, env=self.env)
        moved.write_text(FRONT + "Draft three (not committed).\n", encoding="utf-8")
        found = pdfmd.document_versions(moved, [])
        self.assertEqual([version.label for version in found if version.kind == "git"], ["second draft", "first draft"])
        done = self.run_pdfmd("--history", "report.md", cwd=sub)
        self.assertIn("second draft", done.stdout)


class Resolving(Base):
    def test_the_ways_to_name_a_version(self):
        self.old_versions()
        found = pdfmd.document_versions(self.document, [], include_git=False)
        resolve = history.versions.resolve
        self.assertEqual(resolve("2", found).label, "report.md.bak.20261003110005")
        self.assertEqual(resolve("20261002", found).label, "report_20261002-101500.md")
        self.assertEqual(resolve("2026-10-02", found).label, "report_20261002-101500.md")
        self.assertEqual(resolve("report.md.bak.20261001-090000", found).ref, "20261001090000")
        self.assertEqual(resolve("latest", found).label, "report.md.20261004-080000.bak")
        self.assertIsNone(resolve("20271231", found))
        with self.assertRaises(history.versions.Ambiguous):
            resolve("202610", found)

    def test_previous_is_the_newest_that_is_not_the_file_as_it_is(self):
        make(self.directory, ".backups/report.md.bak.20261005090000", FRONT + "Version five (current).\n")   # = the file
        make(self.directory, ".backups/report.md.bak.20261004090000", FRONT + "Version four.\n")
        found = pdfmd.document_versions(self.document, [], include_git=False)
        self.assertEqual(history.versions.resolve("previous", found, pdfmd.version_differs).label,
                         "report.md.bak.20261004090000")


class Acting(Base):
    def test_diff_shows_what_restoring_would_change(self):
        self.old_versions()
        done = self.run_pdfmd("--history-diff", "20261002", "report.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("-Version five (current).", done.stdout)
        self.assertIn("+Version two.", done.stdout)

    def test_an_unknown_version_is_an_error(self):
        self.old_versions()
        done = self.run_pdfmd("--history-restore", "20300101", "report.md")
        self.assertEqual(done.returncode, 1)
        self.assertIn("no version", done.stderr)

    def test_restore_backs_up_the_file_first_and_changes_nothing_on_a_dry_run(self):
        self.old_versions()
        self.run_pdfmd("--history-restore", "20261002", "report.md", "--dry-run")
        self.assertIn("Version five", self.document.read_text(encoding="utf-8"))
        done = self.run_pdfmd("--history-restore", "20261002", "report.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.document.read_text(encoding="utf-8"), FRONT + "Version two.\n")
        copies = [path for path in (self.directory / ".backups").iterdir() if "Version five" in path.read_text(encoding="utf-8")]
        self.assertEqual(len(copies), 1)                                  # the file as it was, kept

    def test_a_tracked_document_keeps_its_current_notes_and_gets_a_restored_entry(self):
        self.old_versions()
        file = self.directory / ".backups" / "report.hst"
        history.write_file(file, [history.Entry("2026-10-08 10:00:00", "compiled", "with pdfmd v3.25.7")], "report.md")
        done = self.run_pdfmd("--history-restore", "20261003", "report.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("Compiled with nulabreport v1.27.7", self.document.read_text(encoding="utf-8"))   # an old day's notes
        entries, _ = history.read_file(file)
        self.assertEqual([entry.kind for entry in entries], ["restored", "compiled"])
        self.assertIn("20261003110005", entries[0].text)
        shown = self.run_pdfmd("--history", "report.md").stdout
        self.assertIn("restored", shown)

    def test_no_restored_note_leaves_the_history_alone(self):
        self.old_versions()
        file = self.directory / ".backups" / "report.hst"
        history.write_file(file, [history.Entry("2026-10-08 10:00:00", "compiled", "with pdfmd v3.25.7")], "report.md")
        self.run_pdfmd("--history-restore", "20261003", "report.md", "--no-restored-note")
        self.assertEqual([entry.kind for entry in history.read_file(file)[0]], ["compiled"])

    def test_a_document_that_keeps_notes_in_itself_gets_the_entry_there(self):
        text = (FRONT + "Now.\n\n<!-- ====\n     BUILD NOTES\n\n     Compiled with pdfmd v3.25.8 -- 2026-10-09 09:00:00\n"
                "     ==== -->\n")
        self.document.write_text(text, encoding="utf-8")
        self.old_versions()
        done = self.run_pdfmd("--history-restore", "20261002", "report.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        result = self.document.read_text(encoding="utf-8")
        self.assertIn("Version two.", result)
        self.assertIn("Compiled with pdfmd v3.25.8 -- 2026-10-09 09:00:00", result)         # the newest file's, carried over
        self.assertRegex(result, r"- Restored version 20261002101500 \(report_20261002-101500\.md\) -- \d{4}-")

    def test_an_untracked_document_is_not_given_notes_it_never_had(self):
        self.old_versions()
        self.run_pdfmd("--history-restore", "20261002", "report.md")
        self.assertNotIn("Restored", self.document.read_text(encoding="utf-8"))
        self.assertFalse((self.directory / ".backups" / "report.hst").exists())

    @unittest.skipUnless(GIT, "needs git")
    def test_a_commit_can_be_restored(self):
        subprocess.run([GIT, "init", "-q", str(self.directory)], check=True, env=self.env)
        self.document.write_text(FRONT + "Draft one.\n", encoding="utf-8")
        subprocess.run([GIT, "-C", str(self.directory), "add", "-A"], check=True, env=self.env)
        subprocess.run([GIT, "-C", str(self.directory), "commit", "-qm", "first draft"], check=True, env=self.env)
        full = subprocess.run([GIT, "-C", str(self.directory), "rev-parse", "HEAD"], capture_output=True, text=True,
                              env=self.env).stdout.strip()
        self.document.write_text(FRONT + "Draft two.\n", encoding="utf-8")
        done = self.run_pdfmd("--history-restore", full[:7], "report.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.document.read_text(encoding="utf-8"), FRONT + "Draft one.\n")

    def test_the_interactive_list_shows_diffs_and_asks_before_restoring(self):
        self.old_versions()
        found = pdfmd.document_versions(self.document, [], include_git=False)
        args = mock.Mock(metadata_file=None, no_restored_note=False, dry_run=False)
        output = io.StringIO()
        with mock.patch("builtins.input", side_effect=["1", "r 2", "n", "x", "q"]), redirect_stdout(output):
            pdfmd.history_interactive([self.document], found, found, args)
        shown = output.getvalue()
        self.assertIn("+Version four.", shown)
        self.assertIn("a number, `d N`", shown)                            # the unknown answer is explained
        self.assertIn("Version five", self.document.read_text(encoding="utf-8"))       # `n` did not restore


class InitBackups(Base):
    def test_front_matter_gets_backup_and_stamp_with_a_note_and_a_first_copy(self):
        done = self.run_pdfmd("--init-backups", "report.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = self.document.read_text(encoding="utf-8")
        self.assertIn("# AUTO GENERATED by pdfmd --init-backups", text)
        self.assertIn("  backup: {enabled: true}", text)
        self.assertIn("  stamp: {enabled: true, store: file}", text)
        self.assertEqual(len(list((self.directory / ".backups").glob("report.md.bak.*"))), 1)
        entries, _ = history.read_file(self.directory / ".backups" / "report.hst")
        self.assertEqual(entries[0].kind, "note")
        again = self.run_pdfmd("--init-backups", "report.md")
        self.assertIn("ALREADY SET", again.stdout)
        self.assertEqual(self.document.read_text(encoding="utf-8"), text)

    def test_existing_pdfmd_options_are_extended_not_replaced(self):
        self.document.write_text("---\ntitle: R\npdfmd-options:\n  backup: {keep: 5}\n  engine: typst\n---\n\nText.\n", encoding="utf-8")
        self.run_pdfmd("--init-backups", "report.md")
        text = self.document.read_text(encoding="utf-8")
        self.assertIn("  backup: {keep: 5}", text)                        # the person's own setting is not touched
        self.assertIn("  stamp: {enabled: true, store: file}", text)
        self.assertNotIn("enabled: true}\n  engine", text.replace("store: file}", ""))

    def test_a_document_with_no_front_matter_is_not_given_one(self):
        self.document.write_text("Just text.\n", encoding="utf-8")
        done = self.run_pdfmd("--init-backups", "report.md")
        self.assertEqual(done.returncode, 1)
        self.assertIn("--global", done.stdout)
        self.assertEqual(self.document.read_text(encoding="utf-8"), "Just text.\n")

    def test_global_sets_the_config(self):
        config = self.directory / "config.yaml"
        env = {**self.env, "PDFMD_CONFIG": str(config)}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--init-backups", "--global"], cwd=self.directory,
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = config.read_text(encoding="utf-8")
        self.assertIn("AUTO GENERATED", text)
        self.assertIn("store: file", text)


if __name__ == "__main__":
    unittest.main()
