"""v3.32.12: `pdfmd --which [NAME ...]` says what a bare `pdfmd` would build and why, or which file a name finds, and builds nothing
(entry 3eu)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
PDFMD = ROOT / "pdfmd.py"


class Which(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.dir = Path(self._folder.name).resolve()
        self.clock = 1_700_000_000

    def doc(self, name: str, priority=None) -> Path:
        path = self.dir / name
        path.write_text(("" if priority is None else f"---\npriority: {priority}\n---\n") + f"# {name}\n", encoding="utf-8")
        self.clock += 100
        os.utime(path, (self.clock, self.clock))
        return path

    def which(self, *args):
        env = {**os.environ, "NO_COLOR": "1", "PDFMD_CONFIG": ""}
        return subprocess.run([sys.executable, str(PDFMD), "--which", *args], cwd=self.dir, env=env, capture_output=True, text=True)

    def test_every_document_gets_a_row_and_nothing_is_built(self):
        for name in ("report.md", "report.final.md", "report_draft.md"):
            self.doc(name)
        self.doc("notes.md", "never")
        done = self.which()
        self.assertEqual(done.returncode, 0, done.stderr)
        out = done.stdout
        self.assertIn("builds report.final.md", out)
        for text in ("report.final.md  BUILT", "left: name: bare name", "left: name: draft", "left: priority: never", "priority: never"):
            self.assertIn(text, out)
        self.assertEqual(list(self.dir.glob("*.pdf")) + list(self.dir.glob("*.assembled.md")), [])

    def test_the_rules_and_where_they_came_from_are_shown(self):
        self.doc("a.md")
        self.doc("b.md")
        folder = self.dir / ".pdfmd"
        folder.mkdir()
        (folder / "ranking.yaml").write_text("classes:\n  fruit: {words: [cherry, banana], above: numbers}\n", encoding="utf-8")
        out = self.which().stdout
        self.assertIn(f"RULES  from {Path('.pdfmd') / 'ranking.yaml'}, the built-in default", out)
        self.assertIn("names: family   by: priority, newest", out)
        self.assertIn("fruit    cherry < banana", out)
        self.assertLess(out.index("numbers "), out.index("fruit "))
        self.assertLess(out.index("fruit "), out.index("final "))

    def test_a_tie_is_shown_with_the_warning(self):
        self.doc("a.md", 2)
        self.doc("b.md", 2)
        done = self.which()
        self.assertIn("WARN  2 Markdown files tie (priority: 2)", done.stderr)
        self.assertIn("b.md  BUILT", done.stdout)
        self.assertIn("a.md  left: tie, not the newest", done.stdout)

    def test_no_priority_on_either_says_so_and_that_the_newest_wins(self):
        """v3.33.50: a folder of documents with nothing set was called a tie."""
        self.doc("a.md")
        self.doc("b.md")
        done = self.which()
        self.assertIn("WARN  2 Markdown files have no priority set: a.md, b.md; using b.md, the newest", done.stderr)
        for old in ("files tie", "[tie", "left: tie"):
            self.assertNotIn(old, done.stderr + done.stdout)
        self.assertIn("b.md  BUILT", done.stdout)
        self.assertIn("a.md  left: no priority set, older", done.stdout)

    def test_a_tie_that_cannot_be_settled_says_it_would_stop(self):
        paths = [self.doc(name, 2) for name in ("a.md", "b.md")]
        for path in paths:
            os.utime(path, (self.clock, self.clock))                     # the same moment
        done = self.which()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("would stop", done.stdout)
        self.assertIn("tied", done.stdout)

    def test_newest_and_all_act_as_they_would_for_a_build(self):
        self.doc("a.md", "final")
        self.doc("b.md")
        self.assertIn("builds a.md", self.which().stdout)
        self.assertIn("--newest in . builds b.md", self.which("--newest").stdout)
        self.doc("c.md", "never")
        self.assertIn("left: priority: never", self.which().stdout)
        self.assertIn("--newest in . builds c.md", self.which("--newest", "--all").stdout)

    def test_a_single_file_and_no_file_and_no_auto(self):
        self.assertNotEqual(self.which().returncode, 0)
        self.doc("only.md")
        self.assertIn("builds only.md, the only Markdown file", self.which().stdout)
        self.doc("two.md")
        self.assertIn("stops with the list", subprocess.run(
            [sys.executable, str(PDFMD), "--which", "--no-auto", "priority"], cwd=self.dir,
            env={**os.environ, "PDFMD_CONFIG": ""}, capture_output=True, text=True).stdout)

    def test_names_say_which_file_they_find(self):
        self.doc("report.md")
        self.doc("other.md")
        done = self.which("report", "other")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("report  ->  report.md", done.stdout)
        self.assertIn("other  ->  other.md", done.stdout)
        missing = self.which("nosuchdocument")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("Could not find", missing.stderr)

    def test_a_mistake_in_the_ranking_is_reported(self):
        self.doc("a.md")
        self.doc("b.md")
        folder = self.dir / ".pdfmd"
        folder.mkdir()
        (folder / "ranking.yaml").write_text("by: [luck]\n", encoding="utf-8")
        done = self.which()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("luck", done.stderr)


if __name__ == "__main__":
    unittest.main()
