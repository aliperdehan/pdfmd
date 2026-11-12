"""v3.32.13: fixes to bare `pdfmd`'s choice (entry 3eu). pdfmd's own Markdown output is never a candidate (the newest file of a folder
would be the last build's output), `-w` keeps the document it chose, and `no-auto: [priority]` works from the folders and the config,
not only from the command line."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
PDFMD = ROOT / "pdfmd.py"

sys.path.insert(0, str(ROOT))
import pdfmd as _first  # noqa: E402,F401  (v3.33.188: binds every package's `core` first, as in a whole run; first binding wins)

spec = importlib.util.spec_from_file_location("pdfmd_under_test", PDFMD)
pdfmd = importlib.util.module_from_spec(spec)
sys.modules["pdfmd_under_test"] = pdfmd
spec.loader.exec_module(pdfmd)


class Folder(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.dir = Path(self._folder.name)
        self.clock = 1_700_000_000
        self.config = ""

    def doc(self, name, text="# T\n\nbody\n"):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.clock += 100
        os.utime(path, (self.clock, self.clock))
        return path

    def run_pdfmd(self, *args):
        env = {**os.environ, "NO_COLOR": "1", "PDFMD_CONFIG": self.config}
        return subprocess.run([sys.executable, str(PDFMD), *args, "--stop-at", "markdown"], cwd=self.dir, env=env,
                              capture_output=True, text=True)

    def names(self):
        return sorted(path.name for path in self.dir.glob("*.md"))


@unittest.skipUnless(shutil.which("pandoc"), "a build, even one that stops at Markdown, needs Pandoc")
class OwnOutput(Folder):
    def test_a_second_bare_run_builds_the_same_source_not_the_first_runs_output(self):
        self.doc("alpha.md")
        self.doc("beta.md", "---\npriority: 2\n---\n# B\n")
        first = self.run_pdfmd()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("AUTO MD    beta.md", first.stdout)
        self.assertIn("beta.assembled.md", self.names())
        second = self.run_pdfmd()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("AUTO MD    beta.md", second.stdout)
        self.assertEqual(second.stderr, "")
        self.assertNotIn("beta.assembled.assembled.md", self.names())

    def test_equal_documents_still_build_the_newest_source_after_a_run(self):
        self.doc("a.md")
        self.doc("b.md")
        self.run_pdfmd()
        done = self.run_pdfmd()
        self.assertIn("using b.md, the newest", done.stderr)
        self.assertEqual(done.stderr.count("WARN"), 1)

    def test_flat_markdown_beside_its_source_is_not_a_candidate(self):
        self.doc("report.md")
        for name in ("report.gfm.md", "report.ascii.md", "report.ascii.gfm.md"):
            self.doc(name)
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("AUTO MD    report.md\n", done.stdout)

    def test_a_dotted_name_without_a_source_is_a_document(self):
        self.doc("notes.gfm.md")
        self.doc("other.md")
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("notes.gfm.md", done.stderr + done.stdout)

    def test_hidden_markdown_files_are_not_candidates(self):
        self.doc("a.md")
        self.doc(".a.pdfmd-tmp.md")
        done = self.run_pdfmd()
        self.assertIn("AUTO MD    a.md\n", done.stdout)

    def test_an_assembled_file_is_not_a_candidate_even_under_another_name(self):
        self.doc("a.md")
        self.doc("zz-build.md", "---\npdfmd-assembled: true\n---\n# Built\n")
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("AUTO MD    a.md\n", done.stdout)

@unittest.skipUnless(shutil.which("pandoc"), "a build, even one that stops at Markdown, needs Pandoc")
class SwitchedOff(Folder):
    def two(self):
        self.doc("a.md")
        self.doc("b.md", "---\npriority: 3\n---\n# B\n")

    def test_no_auto_priority_in_a_folders_options(self):
        self.two()
        self.doc(".pdfmd/config.yaml", "options:\n  no-auto: [priority]\n")
        done = self.run_pdfmd()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Multiple Markdown files found", done.stderr)

    def test_auto_priority_off_in_a_folders_options(self):
        self.two()
        self.doc(".pdfmd/config.yaml", "options:\n  auto: {priority: off}\n")
        done = self.run_pdfmd()
        self.assertIn("Multiple Markdown files found", done.stderr)

    def test_the_same_in_the_config_file(self):
        self.two()
        config = self.dir.parent / (self.dir.name + "-config.yaml")
        config.write_text("options:\n  no-auto: [priority]\n", encoding="utf-8")
        self.addCleanup(config.unlink)
        self.config = str(config)
        done = self.run_pdfmd()
        self.assertIn("Multiple Markdown files found", done.stderr)

    def test_an_unrelated_no_auto_kind_leaves_priority_on(self):
        self.two()
        self.doc(".pdfmd/config.yaml", "options:\n  no-auto: [margin]\n")
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("AUTO MD    b.md", done.stdout)

    def test_newest_still_works_where_priority_is_off(self):
        self.two()
        self.doc(".pdfmd/config.yaml", "options:\n  no-auto: [priority]\n")
        done = self.run_pdfmd("--newest")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_never_stays_in_the_batch_list_where_priority_is_off(self):
        self.doc("a.md")
        self.doc("b.md", "---\npriority: never\n---\n# B\n")
        self.doc(".pdfmd/config.yaml", "options:\n  no-auto: [priority]\n")
        done = self.run_pdfmd("-b", ".")
        self.assertNotIn("left out (priority: never)", done.stdout)

class Which(Folder):
    """--which reads no document through Pandoc, so these run without it."""

    def test_which_names_what_it_left_out(self):
        self.doc("report.md")
        self.doc("report.gfm.md")
        done = self.run_pdfmd("--which")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("not candidates", done.stdout)
        self.assertIn("report.gfm.md", done.stdout)

    def test_which_says_the_list_comes_back_where_priority_is_off(self):
        self.doc("a.md")
        self.doc("b.md", "---\npriority: 3\n---\n# B\n")
        self.doc(".pdfmd/config.yaml", "options:\n  no-auto: [priority]\n")
        done = self.run_pdfmd("--which")
        self.assertIn("stops with the list", done.stdout)


class WatchPin(unittest.TestCase):
    def test_a_bare_watch_gets_the_chosen_document(self):
        self.assertEqual(pdfmd.pinned_watch_argv(["-w"], None, Path("/x/b.md")), ["-w", "--", str(Path("/x/b.md"))])

    def test_newest_is_dropped_since_the_path_names_the_file(self):
        self.assertEqual(pdfmd.pinned_watch_argv(["--newest", "-w", "--no-auto"], [], Path("/x/b.md")),
                         ["-w", "--no-auto", "--", str(Path("/x/b.md"))])

    def test_a_section_request_gets_the_document_in_front(self):
        self.assertEqual(pdfmd.pinned_watch_argv(["#intro", "-w"], [Path("#intro")], Path("/x/b.md")), [str(Path("/x/b.md")) + "#intro", "-w"])

    def test_a_named_document_is_left_alone(self):
        self.assertEqual(pdfmd.pinned_watch_argv(["report", "-w"], ["report"], Path("/x/report.md")), ["report", "-w"])

    def test_the_parser_reads_the_pinned_line_as_that_document(self):
        parser_args = pdfmd.build_parser().parse_args(pdfmd.pinned_watch_argv(["--no-auto", "-w"], None, Path("/x/b.md")))
        self.assertEqual(parser_args.path, [Path("/x/b.md")])


if __name__ == "__main__":
    unittest.main()
