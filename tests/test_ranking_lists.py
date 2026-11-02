"""v3.32.11: `priority: never` leaves the folder lists of `-b`, `-r` and the viewer; `--all` brings it back; `--newest` builds the
newest file of the folder (entry 3eu). The runs go through pdfmd itself (`--stop-at markdown`, which needs no Pandoc or engine)."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PDFMD = ROOT / "pdfmd.py"

import pdfmd  # noqa: E402


class Lists(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.dir = Path(self._folder.name).resolve()
        self.clock = 1_700_000_000
        pdfmd.folder_walk.cache_clear()

    def doc(self, name: str, priority=None, folder: Path | None = None) -> Path:
        path = (folder or self.dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        front = "" if priority is None else f"---\npriority: {priority}\n---\n"
        path.write_text(front + f"# {name}\n", encoding="utf-8")
        self.clock += 100
        os.utime(path, (self.clock, self.clock))
        return path

    def run_pdfmd(self, *args, stop=True):
        env = {**os.environ, "NO_COLOR": "1", "PDFMD_CONFIG": ""}
        return subprocess.run([sys.executable, str(PDFMD), *args, *(["--stop-at", "markdown"] if stop else [])], cwd=self.dir, env=env,
                              capture_output=True, text=True)

    def built(self):
        return sorted(path.name for path in self.dir.glob("*.assembled.md"))

    def setup_three(self):
        self.doc("a.md")
        self.doc("hidden.md", "never")
        self.doc("c.md", "draft")

    # -- the folder lists --------------------------------------------------------------------------------------------

    def test_batch_leaves_out_never_and_says_so(self):
        self.setup_three()
        done = self.run_pdfmd("-b", ".")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.built(), ["a.assembled.md", "c.assembled.md"])                     # draft is still built
        self.assertIn("NOTE  left out (priority: never): hidden.md", done.stdout)

    def test_all_brings_never_back(self):
        self.setup_three()
        done = self.run_pdfmd("-b", ".", "--all")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.built(), ["a.assembled.md", "c.assembled.md", "hidden.assembled.md"])
        self.assertNotIn("left out", done.stdout)
        done = self.run_pdfmd("-b", ".", "--include-never")
        self.assertNotIn("left out", done.stdout)

    def test_no_auto_priority_switches_the_whole_thing_off(self):
        self.setup_three()
        self.run_pdfmd("-b", ".", "--no-auto", "priority")
        self.assertEqual(len(self.built()), 3)

    def test_a_report_leaves_out_never_but_keeps_a_file_named_on_the_command_line(self):
        self.setup_three()
        done = self.run_pdfmd("-r", ".", "-o", "all.assembled.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        text = (self.dir / "all.assembled.md").read_text(encoding="utf-8")
        self.assertIn("# a.md", text)
        self.assertNotIn("# hidden.md", text)
        done = self.run_pdfmd("-r", "a.md", "hidden.md", "-o", "named.assembled.md")
        self.assertIn("# hidden.md", (self.dir / "named.assembled.md").read_text(encoding="utf-8"))

    def test_the_viewer_lists_without_never(self):
        self.setup_three()

        class Args:
            path = [self.dir]
            recursive = False
            include_never = False

        with contextlib.redirect_stdout(io.StringIO()) as printed:
            found = pdfmd.view_sources(Args, self.dir, [])
        self.assertEqual(sorted(path.name for path in found), ["a.md", "c.md"])
        self.assertIn("left out (priority: never)", printed.getvalue())
        Args.include_never = True
        self.assertEqual(len(pdfmd.view_sources(Args, self.dir, [])), 3)

    def test_a_class_of_your_own_with_exclude_hides_documents_too(self):
        self.doc("a.md")
        self.doc("b.md", "hidden")
        folder = self.dir / ".pdfmd"
        folder.mkdir()
        (folder / "ranking.yaml").write_text("classes:\n  secret: {words: [hidden], exclude: true}\n", encoding="utf-8")
        done = self.run_pdfmd("-b", ".")
        self.assertEqual(self.built(), ["a.assembled.md"])
        self.assertIn("b.md", done.stdout)

    # -- bare pdfmd -----------------------------------------------------------------------------------------------

    def test_newest_builds_the_newest_whatever_the_priorities_say(self):
        self.doc("a.md", "final")
        self.doc("b.md")
        done = self.run_pdfmd("--newest")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.built(), ["b.assembled.md"])
        self.assertEqual(done.stderr, "")                          # asked for: no warning about a tie
        self.assertIn("a.md [older]", done.stdout)

    def test_newest_keeps_never_out_and_all_lets_it_in(self):
        self.doc("a.md")
        self.doc("b.md", "never")
        self.run_pdfmd("--newest")
        self.assertEqual(self.built(), ["a.assembled.md"])
        for path in self.dir.glob("*.assembled.md"):
            path.unlink()
        self.run_pdfmd("--newest", "--all")
        self.assertEqual(self.built(), ["b.assembled.md"])

    def test_all_ranks_a_never_document_as_if_it_had_no_priority(self):
        self.doc("a.md", 1)
        self.doc("b.md", "never")
        self.run_pdfmd()
        self.assertEqual(self.built(), ["a.assembled.md"])
        for path in self.dir.glob("*.assembled.md"):
            path.unlink()
        self.run_pdfmd("--all")
        self.assertEqual(self.built(), ["a.assembled.md"])              # 1 beats nothing-at-all
        for path in self.dir.glob("*.assembled.md"):
            path.unlink()
        self.doc("a.md", "draft")
        self.run_pdfmd("--all")
        self.assertEqual(self.built(), ["b.assembled.md"])              # a is a draft; b counts as normal

    def test_newest_with_a_name_says_it_does_nothing(self):
        self.doc("a.md")
        done = self.run_pdfmd("a", "--newest")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("--newest picks among", done.stderr)

    def test_newest_is_honoured_even_when_priority_is_switched_off(self):
        self.doc("a.md")
        self.doc("b.md")
        done = self.run_pdfmd("--no-auto", "priority", "--newest")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.built(), ["b.assembled.md"])


if __name__ == "__main__":
    unittest.main()
