"""`stamp: {partial: true}` (3.30.23): a build of some parts or sections leaves a "partial" entry in the NAME.hst,
naming the parts it built and those whose text changed since an entry last saw them."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
import pdfmd_history as history  # noqa: E402

PANDOC = shutil.which("pandoc")


class Entries(unittest.TestCase):
    def test_a_partial_entry_round_trips_and_older_readers_keep_it_as_a_comment(self):
        entry = history.Entry("2026-10-25 10:00:00", "partial", "parts 60-d; changed: 60-d; with x",
                              (("parts", "60-d"), ("changed", "60-d"), ("shas", "60-d:abcd1234")))
        line = history.hst.line_of(entry)
        found, other = history.hst.parse(line)
        self.assertEqual(other, [])
        self.assertEqual((found[0].kind, found[0].meta_dict()["shas"]), ("partial", "60-d:abcd1234"))
        self.assertEqual(history.hst.line_of(found[0]), line)

    def test_the_options_key(self):
        self.assertFalse(pdfmd.DEFAULT_STAMP_OPTIONS["partial"])
        self.assertTrue(pdfmd.stamp_fields({"partial": True})["partial"])
        self.assertNotIn("partial", pdfmd.stamp_fields({"mode": "history"}))


class HistoryAlias(unittest.TestCase):
    """`history:` in pdfmd-options is `stamp:` (3.30.24): one setting, two names."""

    def options(self, text):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-alias-"))
        self.addCleanup(shutil.rmtree, directory, True)
        document = directory / "report.md"
        document.write_text(text, encoding="utf-8")
        return pdfmd.frontmatter_stamp(document, [])

    def test_the_same_fields_under_either_name(self):
        stamp = self.options("---\npdfmd-options:\n  stamp: {store: file, partial: true}\n---\n")
        history_ = self.options("---\npdfmd-options:\n  history: {store: file, partial: true}\n---\n")
        self.assertEqual(stamp, history_)
        self.assertEqual((history_["store"], history_["partial"], history_["enabled"]), ("file", True, True))

    def test_a_bare_history_switches_it_on_and_stamp_wins_a_field_both_set(self):
        self.assertTrue(self.options("---\npdfmd-options:\n  history: true\n---\n")["enabled"])
        both = self.options("---\npdfmd-options:\n  stamp: {store: both}\n  history: {store: file, partial: true}\n---\n")
        self.assertEqual((both["store"], both["partial"]), ("both", True))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Builds(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-partial-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "parts").mkdir()
        self.write("parts/10-intro.md", "# Intro\n\nOne.\n")
        self.write("parts/20-calc.md", "# Calc\n\nTwo.\n")
        self.write("parts/30-disc.md", "# Disc\n\nThree.\n")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}

    def write(self, name, text):
        (self.directory / name).write_text(text, encoding="utf-8")

    def build(self, *args, partial=True):
        if partial:
            self.write("report.md", "---\ntitle: R\npdfmd-options:\n  parts: auto\n  stamp: {store: file, mode: history, partial: true}\n---\n")
        else:
            self.write("report.md", "---\ntitle: R\npdfmd-options:\n  parts: auto\n  stamp: {store: file, mode: history}\n---\n")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args, "--to", "latex", "-o", "out.tex"],
                              cwd=self.directory, capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def entries(self):
        found = list(self.directory.rglob("report.hst"))
        return history.hst.read_file(found[0])[0] if found else []

    def test_parts_built_and_changed_are_named_and_a_full_build_is_the_baseline(self):
        self.build("--stamp", "report.md")                                    # a full build: shas of every part
        self.assertEqual([entry.kind for entry in self.entries()], ["compiled"])
        self.assertIn("20-calc:", self.entries()[0].meta_dict()["shas"])
        self.write("parts/20-calc.md", "# Calc\n\nTwo, edited.\n")
        self.build("report@20,30")
        partial = [entry for entry in self.entries() if entry.kind == "partial"]
        self.assertEqual(len(partial), 1)
        meta = partial[0].meta_dict()
        self.assertEqual((meta["parts"], meta["changed"]), ("20-calc,30-disc", "20-calc"))
        self.assertNotIn("new", meta)
        self.assertIn("changed: 20-calc", partial[0].text)
        self.build("report@30")                                               # nothing of it changed since
        newest = next(entry for entry in self.entries() if entry.meta_dict().get("parts") == "30-disc")      # not by position: two builds may share a second
        self.assertNotIn("changed", newest.meta_dict())
        self.assertIn("nothing changed", newest.text)

    def test_a_part_no_entry_has_seen_is_first_seen_not_changed(self):
        self.build("report@20")
        meta = self.entries()[0].meta_dict()
        self.assertEqual((meta["parts"], meta.get("new")), ("20-calc", "20-calc"))
        self.assertNotIn("changed", meta)

    def test_off_by_default_and_no_build_notes_line_either_way(self):
        self.build("report@20", partial=False)
        self.assertEqual(self.entries(), [])
        self.build("report@20")
        self.assertNotIn("BUILD NOTES", (self.directory / "report.md").read_text(encoding="utf-8"))

    def test_the_flags_beat_the_document(self):
        self.build("report@20", "--no-stamp-partial")
        self.assertEqual(self.entries(), [])
        self.build("report@20", "--stamp-partial", partial=False)
        self.assertEqual(len(self.entries()), 1)

    def test_a_section_of_a_plain_document(self):
        shutil.rmtree(self.directory / "parts")
        self.write("report.md", "---\ntitle: R\npdfmd-options:\n  stamp: {store: file, partial: true}\n---\n\n# Alpha\n\nA.\n\n# Beta\n\nB.\n")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report#beta", "--to", "latex", "-o", "out.tex"],
                              cwd=self.directory, capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        entry = self.entries()[0]
        self.assertEqual(entry.kind, "partial")
        self.assertTrue(entry.text.startswith("section "))
        self.assertTrue(entry.meta_dict()["shas"])


if __name__ == "__main__":
    unittest.main()
