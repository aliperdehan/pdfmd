"""v3.32.9: bare `pdfmd` in a folder of several Markdown files chooses one by priority and by name (entry 3eu). The runs go through
pdfmd itself (`--stop-at markdown`, which needs no Pandoc or PDF engine), so what is tested is what the author sees: the AUTO MD
line, the WARNs, the file that gets built and what an exact name still does."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDFMD = ROOT / "pdfmd.py"


@unittest.skipUnless(shutil.which("pandoc"), "a build, even one that stops at Markdown, needs Pandoc")
class Bare(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.dir = Path(self._folder.name)
        self.clock = 1_700_000_000

    def doc(self, name, text="# T\n\nbody\n"):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        self.clock += 100
        os.utime(path, (self.clock, self.clock))
        return path

    def run_pdfmd(self, *args):
        env = {**os.environ, "NO_COLOR": "1", "PDFMD_CONFIG": ""}
        return subprocess.run([sys.executable, str(PDFMD), *args, "--stop-at", "markdown"], cwd=self.dir, env=env,
                              capture_output=True, text=True)

    def built(self):
        return sorted(path.name for path in self.dir.glob("*.assembled.md"))

    def test_the_final_version_is_built_and_the_line_says_what_it_beat(self):
        for name in ("report.md", "report_draft.md", "report.final.md"):
            self.doc(name)
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.built(), ["report.final.assembled.md"])
        line = next(line for line in done.stdout.splitlines() if line.startswith("AUTO MD"))
        for text in ("report.final.md", "over", "report.md [name: bare name]", "report_draft.md [name: draft]"):
            self.assertIn(text, line)
        self.assertEqual(done.stderr, "")

    def test_an_exact_name_is_still_the_override(self):
        self.doc("report.md")
        self.doc("report.final.md")
        done = self.run_pdfmd("report")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.built(), ["report.assembled.md"])

    def test_a_priority_in_the_front_matter_root_or_in_pdfmd_options(self):
        self.doc("a.md", "---\npriority: 1\n---\n# A\n")
        self.doc("b.md", "---\npdfmd-options:\n  priority: 5\n---\n# B\n")
        self.doc("c.md", "---\npriority: 3\n---\n# C\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["b.assembled.md"])

    def test_a_document_that_is_never_leaves_the_list(self):
        self.doc("a.md", "---\npriority: never\n---\n# A\n")
        self.doc("b.md")
        done = self.run_pdfmd()
        self.assertEqual(self.built(), ["b.assembled.md"])
        self.assertIn("a.md [priority: never]", done.stdout)

    def test_draft_loses_to_any_other_document_and_final_wins(self):
        self.doc("a.md", "---\npriority: draft\n---\n# A\n")
        self.doc("b.md")
        self.doc("c.md", "---\npriority: FINAL FINAL!!!\n---\n# C\n")
        self.run_pdfmd()
        self.assertEqual(self.built(), ["c.assembled.md"])

    def test_equal_priority_builds_the_newest_and_warns(self):
        self.doc("old.md")
        self.doc("new.md")
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.built(), ["new.assembled.md"])
        self.assertIn("WARN  2 Markdown files have no priority set", done.stderr)
        self.assertIn("using new.md", done.stderr)
        self.assertIn("[no priority set, older]", done.stdout)

    def test_the_same_modification_time_cannot_be_settled(self):
        first, second = self.doc("a.md"), self.doc("b.md")
        os.utime(second, (self.clock - 100, self.clock - 100))
        os.utime(first, (self.clock - 100, self.clock - 100))
        done = self.run_pdfmd()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("same moment", done.stderr + done.stdout)

    def test_a_value_that_is_not_a_priority_warns_and_counts_as_unset(self):
        self.doc("a.md", "---\npriority: banana\n---\n# A\n")
        self.doc("b.md", "---\npriority: 1\n---\n# B\n")
        done = self.run_pdfmd()
        self.assertEqual(self.built(), ["b.assembled.md"])
        self.assertIn("'banana' is not a priority", done.stderr)

    def test_two_different_values_in_one_document_warn_and_pdfmd_options_wins(self):
        self.doc("a.md", "---\npriority: 9\npdfmd-options:\n  priority: 1\n---\n# A\n")
        self.doc("b.md", "---\npriority: 5\n---\n# B\n")
        done = self.run_pdfmd()
        self.assertIn("priority is set twice", done.stderr)
        self.assertEqual(self.built(), ["b.assembled.md"])

    def test_no_auto_priority_brings_back_the_list_and_stop(self):
        self.doc("a.md")
        self.doc("b.md", "---\npriority: 3\n---\n# B\n")
        done = self.run_pdfmd("--no-auto", "priority")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Multiple Markdown files found: a.md, b.md", done.stderr)
        self.assertEqual(self.built(), [])

    def test_one_file_is_built_as_before_with_no_ranking_in_the_line(self):
        self.doc("only.md")
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("AUTO MD    only.md\n", done.stdout)
        self.assertNotIn("over", done.stdout)


if __name__ == "__main__":
    unittest.main()
