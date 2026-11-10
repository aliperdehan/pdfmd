"""`backup: {keep: N}` says what `pdfs: N` says (v3.32.43, entry 3do): the newest N, 0 none, a negative number every one, the default every
one; and `backups:` is a second spelling of the `backup:` key."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402


class Keep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.md = self.dir / "report.md"

    def document(self, backup: str, key: str = "backup") -> None:
        self.md.write_text(f"---\ntitle: T\npdfmd-options:\n  {key}: {backup}\n---\n\ntext\n", encoding="utf-8")

    def options(self) -> dict:
        return pdfmd.resolve_backup_options(self.md, [], None)

    def copies(self) -> list[str]:
        folder = self.dir / ".backups"
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []

    def back_up(self, times: int) -> None:
        """`times` edits, each backed up; the source's mtime is moved on so that two copies never share a second."""
        for number in range(times):
            self.md.write_text(self.md.read_text(encoding="utf-8").split("\n\ntext")[0] + f"\n\ntext {number}\n", encoding="utf-8")
            stamp = (datetime(2026, 11, 5, 10, 0, 0) + timedelta(minutes=number)).timestamp()
            os.utime(self.md, (stamp, stamp))
            with contextlib.redirect_stdout(io.StringIO()):
                pdfmd.backup_after_success(self.md, [], None, False)

    def test_the_default_keeps_every_copy(self):
        self.document("true")
        self.assertLess(self.options()["keep"], 0)
        self.back_up(4)
        self.assertEqual(len(self.copies()), 4)

    def test_n_keeps_the_newest_n(self):
        self.document("{enabled: true, keep: 2}")
        self.back_up(4)
        self.assertEqual(len(self.copies()), 2)

    def test_zero_makes_no_copy_and_deletes_none(self):
        self.document("{enabled: true}")
        self.back_up(2)
        self.assertEqual(len(self.copies()), 2)
        self.document("{enabled: true, keep: 0}")
        self.back_up(2)
        self.assertEqual(len(self.copies()), 2, "0 stops the copies; what was kept stays")

    def test_the_words_and_a_negative_number(self):
        for given, want in (("all", -1), ("-5", -5), ("none", 0), ("off", 0), ("0", 0), ("12", 12)):
            self.document("{enabled: true, keep: %s}" % given)
            self.assertEqual(self.options()["keep"], want, given)

    def test_a_wrong_value_is_refused_with_its_name(self):
        self.document("{enabled: true, keep: many}")
        with self.assertRaises(SystemExit) as raised:
            self.options()
        self.assertIn("backup.keep", str(raised.exception))

    def test_an_empty_value_is_no_setting(self):
        for given in ("{enabled: true, keep: }", "{enabled: true, keep: ~}", "{enabled: true, pdfs: ~}"):
            self.document(given)
            options = self.options()
            self.assertEqual((options["keep"], options["pdfs"]), (-1, 0), given)

    def test_backups_is_a_second_spelling_of_backup(self):
        self.document("{keep: 7, pdfs: 3}", key="backups")
        options = self.options()
        self.assertEqual((options["enabled"], options["keep"], options["pdfs"]), (True, 7, 3))
        self.document("true", key="backups")
        self.assertTrue(self.options()["enabled"])

    def test_backup_wins_where_both_are_set(self):
        self.md.write_text("---\ntitle: T\npdfmd-options:\n  backup: {keep: 2}\n  backups: {keep: 9, pdfs: 4}\n---\n\ntext\n", encoding="utf-8")
        options = self.options()
        self.assertEqual((options["keep"], options["pdfs"]), (2, 4), "field by field, `backup` first")


if __name__ == "__main__":
    unittest.main()
