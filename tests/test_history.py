"""The .hst history file (pdfmd_history), BUILD NOTES blocks that belong to pdfmd or to somebody else, and the
commands that move a document's history between the two."""

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

LINE = "     "
RULE = "=" * 60
OWN = (f"<!-- {RULE}\n{LINE}BUILD NOTES\n\n{LINE}Compiled with nulabreport v1.27.7, pdfmd v3.25.6 -- 2026-10-09 10:00:00\n\n"
       f"{LINE}My own remark: figure 2 needs a re-run of the fit.\n\n{LINE}Compile History:\n"
       f"{LINE}  - Compiled with pdfmd v3.25.5 -- 2026-10-08 09:00:00\n"
       f"{LINE}  - Compiled with pdfmd v3.25.4 -- 2026-10-07 08:30:00\n{LINE}{RULE} -->\n")
AGENT = f"<!-- {RULE}\n{LINE}BUILD NOTES\n{LINE}(an agent wrote this) Checked the numbers.\n{LINE}{RULE} -->\n"
DOCUMENT = f"---\ntitle: H\n---\n\n# H\n\nText.\n\n{OWN}\n{AGENT}"


class Format(unittest.TestCase):
    def test_an_entry_survives_a_pipe_a_line_break_and_extra_words(self):
        entry = history.Entry("2026-10-09 11:22:01", "compiled", "with a | pipe, a \\ backslash\nand a second line",
                              (("sha", "ab12"), ("out", "r.pdf")))
        text = history.render([entry], "r.md")
        [again], other = history.parse(text)
        self.assertEqual(again.text, entry.text)
        self.assertEqual(again.meta_dict(), {"sha": "ab12", "out": "r.pdf"})
        self.assertEqual(len(text.splitlines()), 2)                       # a header and ONE line

    def test_merging_keeps_each_entry_once_newest_first_and_joins_the_extra_words(self):
        one = history.Entry("2026-10-09 11:00:00", "compiled", "a", (("sha", "1"),))
        two = history.Entry("2026-10-09 12:00:00", "note", "b")
        again = history.Entry("2026-10-09 11:00:00", "compiled", "a", (("git", "g"),))
        merged = history.merge([one], [two, again])
        self.assertEqual([entry.when for entry in merged], ["2026-10-09 12:00:00", "2026-10-09 11:00:00"])
        self.assertEqual(merged[1].meta_dict(), {"sha": "1", "git": "g"})

    def test_what_is_not_an_entry_is_kept_as_a_comment(self):
        entries, other = history.parse("# mine\nsome stray words\n2026-10-09 11:00:00 | compiled | x\n")
        self.assertEqual(len(entries), 1)
        self.assertEqual(other, ["# mine", "# some stray words"])
        self.assertIn("# some stray words", history.render(entries, "r.md", other))

    def test_two_files_joined_with_cat_merge_cleanly(self):
        a = history.render([history.Entry("2026-10-09 10:00:00", "compiled", "one")], "r.md")
        b = history.render([history.Entry("2026-10-09 11:00:00", "compiled", "two")], "r.md")
        entries, _ = history.parse(a + b)
        self.assertEqual([entry.text for entry in history.merge(entries)], ["two", "one"])

    def test_adding_the_same_entry_twice_writes_it_once(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-hst-"))
        self.addCleanup(shutil.rmtree, directory, True)
        path = directory / "x.hst"
        entry = history.Entry("2026-10-09 10:00:00", "compiled", "one")
        self.assertTrue(history.add_entry(path, entry, "x.md"))
        self.assertFalse(history.add_entry(path, entry, "x.md"))
        self.assertEqual(len(history.read_file(path)[0]), 1)


class Blocks(unittest.TestCase):
    def chosen(self, text):
        match = pdfmd.pdfmd_build_notes(text)
        return None if match is None else match.group("body")

    def test_the_block_pdfmd_wrote_into_is_the_one_it_uses(self):
        self.assertIn("Compiled with nulabreport", self.chosen(AGENT + "\n" + OWN))
        self.assertIn("Compiled with nulabreport", self.chosen(OWN + "\n" + AGENT))

    def test_a_lone_hand_kept_block_is_used_as_the_convention_always_was(self):
        self.assertIn("agent wrote", self.chosen("Text\n\n" + AGENT))

    def test_several_blocks_none_pdfmds_means_a_block_of_its_own(self):
        self.assertIsNone(self.chosen(AGENT + "\n" + AGENT.replace("agent", "person")))
        updated, _ = pdfmd.update_build_notes(AGENT + "\n" + AGENT.replace("agent", "person"),
                                              "Compiled with pdfmd v9 -- 2026-10-09 10:00:00", "replace")
        self.assertEqual(updated.count("BUILD NOTES"), 3)
        self.assertIn("(an agent wrote this)", updated)
        self.assertIn("(an person wrote this)", updated)

    def test_a_block_marked_ignore_is_never_written_into(self):
        marked = AGENT.replace(f"{LINE}{RULE} -->", f"{LINE}pdfmd: ignore\n{LINE}{RULE} -->")
        updated, _ = pdfmd.update_build_notes("Text\n\n" + marked, "Compiled with pdfmd v9 -- 2026-10-09 10:00:00", "replace")
        self.assertEqual(updated.count("BUILD NOTES"), 2)
        self.assertIn(marked, updated)


class Moving(unittest.TestCase):
    def test_pdfmds_lines_become_entries_and_everybody_elses_stay(self):
        stripped, entries = pdfmd.notes_to_entries(DOCUMENT)
        self.assertEqual([(entry.when, entry.text) for entry in pdfmd.history_module().merge(entries)][::-1], [
            ("2026-10-07 08:30:00", "with pdfmd v3.25.4"), ("2026-10-08 09:00:00", "with pdfmd v3.25.5"),
            ("2026-10-09 10:00:00", "with nulabreport v1.27.7, pdfmd v3.25.6")])
        self.assertIn("My own remark", stripped)
        self.assertIn("(an agent wrote this)", stripped)
        self.assertNotIn("Compiled", stripped)
        self.assertNotIn("Compile History", stripped)
        self.assertEqual(stripped.count("BUILD NOTES"), 2)

    def test_a_block_with_nothing_else_in_it_goes_when_its_lines_do(self):
        text = f"Text\n\n<!-- {RULE}\n{LINE}BUILD NOTES\n\n{LINE}Compiled with pdfmd v1 -- 2026-10-09 10:00:00\n{LINE}{RULE} -->\n"
        stripped, entries = pdfmd.notes_to_entries(text)
        self.assertEqual(len(entries), 1)
        self.assertNotIn("BUILD NOTES", stripped)
        self.assertEqual(stripped.strip(), "Text")

    def test_putting_them_back_gives_the_same_lines_newest_on_top(self):
        stripped, entries = pdfmd.notes_to_entries("Text\n\n" + OWN.replace("My own remark", "Mine"))
        again = pdfmd.entries_to_notes(stripped, entries)
        self.assertLess(again.index("2026-10-09 10:00:00"), again.index("2026-10-08 09:00:00"))
        self.assertLess(again.index("2026-10-08 09:00:00"), again.index("2026-10-07 08:30:00"))
        self.assertIn("Mine", again)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-hst-cli-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.document = self.directory / "doc.md"
        self.document.write_text(DOCUMENT, encoding="utf-8")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}

    def run_pdfmd(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.directory,
                              capture_output=True, text=True, env=self.env)

    def test_to_file_and_back(self):
        done = self.run_pdfmd("doc.md", "--history-to-file", "--dry-run")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.document.read_text(encoding="utf-8"), DOCUMENT)
        self.assertFalse((self.directory / ".backups").exists())
        done = self.run_pdfmd("doc.md", "--history-to-file")
        self.assertEqual(done.returncode, 0, done.stderr)
        file = self.directory / ".backups" / "doc.hst"
        entries, _ = history.read_file(file)
        self.assertEqual(len(entries), 4)                                  # three compiles and the block's own text
        [block] = [entry for entry in entries if entry.meta_dict().get("block")]
        self.assertIn("My own remark: figure 2 needs a re-run of the fit.", block.text)
        after = self.document.read_text(encoding="utf-8")
        self.assertNotIn("Compiled", after)
        self.assertNotIn("My own remark", after)                           # the whole block went, its text too
        self.assertIn("(an agent wrote this)", after)                      # another author's block did not
        self.assertEqual(len([p for p in (self.directory / ".backups").iterdir() if p.name.startswith("doc.md.bak")]), 1)
        again = self.run_pdfmd("doc.md", "--history-to-file")
        self.assertIn("no pdfmd BUILD NOTES block", again.stdout)
        back = self.run_pdfmd("doc.md", "--history-to-notes")
        self.assertEqual(back.returncode, 0, back.stderr)
        text = self.document.read_text(encoding="utf-8")
        self.assertIn("Compiled with nulabreport v1.27.7, pdfmd v3.25.6 -- 2026-10-09 10:00:00", text)
        self.assertIn("  - Compiled with pdfmd v3.25.5 -- 2026-10-08 09:00:00", text)
        self.assertIn("(an agent wrote this)", text)
        self.assertIn("My own remark: figure 2 needs a re-run of the fit.", text)     # the block is whole again
        self.assertEqual(text.count("My own remark"), 1)
        self.assertFalse(file.exists())                                  # nothing left in it
        again = self.run_pdfmd("doc.md", "--history-to-file")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.run_pdfmd("doc.md", "--history-to-notes")
        self.run_pdfmd("doc.md", "--history-to-file")
        self.assertEqual(len([e for e in history.read_file(file)[0] if e.meta_dict().get("block")]), 1)   # no copy of the text added

    def test_a_note_in_the_file_stays_when_the_compiles_go_back(self):
        self.run_pdfmd("doc.md", "--history-to-file")
        file = self.directory / ".backups" / "doc.hst"
        entries, other = history.read_file(file)
        history.write_file(file, [*entries, history.Entry("2026-10-09 13:00:00", "note", "sent to the supervisor")], "doc.md", other)
        self.run_pdfmd("doc.md", "--history-to-notes")
        left, _ = history.read_file(file)
        self.assertEqual([entry.kind for entry in left], ["note"])

    def test_stamp_store_file_leaves_the_document_alone(self):
        output = self.directory / "doc.pdf"
        output.write_bytes(b"%PDF-1.4\n")
        stamp = {"enabled": True, "store": "file", "pdf_metadata": False}
        from unittest import mock
        patcher = mock.patch.dict(os.environ, self.env)       # the notice about the hidden folder must not touch the real config
        patcher.start()
        self.addCleanup(patcher.stop)
        pdfmd.stamp_after_success(self.document, [], [], stamp, output, False)
        self.assertEqual(self.document.read_text(encoding="utf-8"), DOCUMENT)
        [entry] = history.read_file(self.directory / ".backups" / "doc.hst")[0]
        self.assertEqual(entry.kind, "compiled")
        self.assertEqual(entry.meta_dict()["out"], "doc.pdf")
        self.assertEqual(len(entry.meta_dict()["sha"]), 12)
        pdfmd.stamp_after_success(self.document, [], [], {**stamp, "store": "both"}, output, False)
        self.assertGreater(self.document.read_text(encoding="utf-8").count("Compiled"), DOCUMENT.count("Compiled") - 1)

    def test_merge_history_joins_files_once_each(self):
        a, b = self.directory / "a.hst", self.directory / "b.hst"
        history.write_file(a, [history.Entry("2026-10-09 10:00:00", "compiled", "one")], "r.md")
        history.write_file(b, [history.Entry("2026-10-09 10:00:00", "compiled", "one"),
                               history.Entry("2026-10-09 11:00:00", "compiled", "two")], "r.md")
        done = self.run_pdfmd("--merge-history", "a.hst", "b.hst", "-o", "all.hst")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([entry.text for entry in history.read_file(self.directory / "all.hst")[0]], ["two", "one"])
        printed = self.run_pdfmd("--merge-history", "a.hst", "b.hst")
        self.assertIn("| two", printed.stdout)

    def test_the_history_travels_in_an_assembled_file_and_comes_out_of_it(self):
        self.run_pdfmd("doc.md", "--history-to-file")
        done = self.run_pdfmd("doc.md", "--assemble-only", "--embed-metadata", "-o", "one.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("type: hst", (self.directory / "one.md").read_text(encoding="utf-8"))
        self.assertIn("history doc.hst", done.stdout)
        done = self.run_pdfmd("--unpack", "one.md", "--slim")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("{=pdfmd}", (self.directory / "one.md").read_text(encoding="utf-8"))
        self.assertEqual(len(history.read_file(self.directory / "one.unpacked" / "doc.hst")[0]), 4)
        document = self.directory / "one.md"
        found = pdfmd.history_file(document, existing=True)
        self.assertEqual(found, self.directory / "one.unpacked" / "doc.hst")


if __name__ == "__main__":
    unittest.main()
