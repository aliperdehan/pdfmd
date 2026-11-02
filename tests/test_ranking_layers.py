"""v3.32.10: the `ranking` settings of bare `pdfmd` (entry 3eu): where they are read from (the documents, `.pdfmd/ranking.yaml` of the
folder and of the folders above it, the folders' own files, the global `ranking.yaml` and the config), which one wins (the nearer to the
file) and what they can change. The runs go through pdfmd itself (`--stop-at markdown`)."""

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
FRUIT = "classes:\n  fruit: {words: [cherry, banana], above: numbers}\n"


@unittest.skipUnless(shutil.which("pandoc"), "a build, even one that stops at Markdown, needs Pandoc")
class Layers(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.root = Path(self._folder.name).resolve()
        self.work = self.root / "top" / "work"
        self.work.mkdir(parents=True)
        self.config = self.root / "global" / "config.yaml"
        self.config.parent.mkdir()
        self.clock = 1_700_000_000

    def put(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def doc(self, name: str, priority=None, extra: str = "") -> Path:
        front = "" if priority is None and not extra else f"---\n{'' if priority is None else f'priority: {priority}' + chr(10)}{extra}---\n"
        path = self.put(self.work / name, front + f"# {name}\n")
        self.clock += 100
        os.utime(path, (self.clock, self.clock))
        return path

    def run_pdfmd(self, *args, config: bool = True):
        env = {**os.environ, "NO_COLOR": "1", "PDFMD_CONFIG": str(self.config) if config else ""}
        return subprocess.run([sys.executable, str(PDFMD), *args, "--stop-at", "markdown"], cwd=self.work, env=env,
                              capture_output=True, text=True)

    def built(self) -> list[str]:
        return sorted(path.name for path in self.work.glob("*.assembled.md"))

    def three(self):
        self.doc("a.md", 7)
        self.doc("b.md", "banana")
        self.doc("c.md", "cherry")

    # -- where the words come from -------------------------------------------------------------------------------------

    def test_a_folders_ranking_yaml_defines_the_words(self):
        self.three()
        self.put(self.work / ".pdfmd" / "ranking.yaml", FRUIT)
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.built(), ["b.assembled.md"])                  # banana > cherry > 7
        self.assertEqual(done.stderr, "")

    def test_the_ranking_yaml_of_a_folder_above_reaches_the_documents_below(self):
        self.three()
        self.put(self.root / "top" / ".pdfmd" / "ranking.yaml", FRUIT)
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["b.assembled.md"])

    def test_the_global_ranking_yaml_and_the_config_options(self):
        self.three()
        self.put(self.config, "options: {}\n")
        self.put(self.config.parent / "ranking.yaml", FRUIT)
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["b.assembled.md"])
        for path in self.work.glob("*.assembled.md"):
            path.unlink()
        (self.config.parent / "ranking.yaml").unlink()
        self.put(self.config, "options:\n  ranking:\n    classes:\n      fruit: {words: [cherry, banana], above: numbers}\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["b.assembled.md"])

    def test_the_folder_settings_and_a_metadata_yaml_are_layers_too(self):
        self.three()
        self.put(self.work / ".pdfmd" / "config.yaml", "options:\n  ranking:\n    classes:\n      fruit: {words: [cherry, banana], above: numbers}\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["b.assembled.md"])
        for path in self.work.glob("*.assembled.md"):
            path.unlink()
        (self.work / ".pdfmd" / "config.yaml").unlink()
        self.put(self.work / "metadata.yaml", "pdfmd-options:\n  ranking:\n    classes:\n      fruit: {words: [cherry, banana], above: numbers}\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["b.assembled.md"])

    # -- which one wins -----------------------------------------------------------------------------------------------

    def test_in_one_folder_ranking_yaml_beats_metadata_yaml_beats_the_settings(self):
        self.doc("a.md", "x")
        self.doc("b.md", "y")
        self.put(self.work / ".pdfmd" / "config.yaml", "options:\n  ranking:\n    classes:\n      k: {words: [x, y], above: numbers}\n")
        self.put(self.work / "metadata.yaml", "pdfmd-options:\n  ranking:\n    classes:\n      k: {words: [y, x], above: numbers}\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["a.assembled.md"])                  # metadata.yaml (x above y?) no: [y, x] is low -> high, x wins
        for path in self.work.glob("*.assembled.md"):
            path.unlink()
        self.put(self.work / ".pdfmd" / "ranking.yaml", "classes:\n  k: {words: [x, y], above: numbers}\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["b.assembled.md"])                  # the ranking.yaml says [x, y]: y wins

    def test_a_nearer_folder_beats_a_farther_one_and_the_config(self):
        self.doc("a.md", "x")
        self.doc("b.md", "y")
        self.put(self.config, "options: {}\n")
        self.put(self.config.parent / "ranking.yaml", "classes:\n  k: {words: [x, y], above: numbers}\n")
        self.put(self.root / "top" / ".pdfmd" / "ranking.yaml", "classes:\n  k: {words: [y, x], above: numbers}\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["a.assembled.md"])

    def test_a_document_beats_every_folder_and_may_only_set_classes_and_ladder(self):
        self.put(self.work / ".pdfmd" / "ranking.yaml", "classes:\n  k: {words: [x, y], above: numbers}\nby: [priority]\n")
        self.doc("a.md", "x", "pdfmd-options:\n  ranking:\n    classes:\n      k: {words: [y, x], above: numbers}\n    by: [newest]\n")
        self.doc("b.md", "y")
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.built(), ["a.assembled.md"])
        self.assertIn("by can be set by a folder or the config, not by a document", done.stderr)

    def test_two_documents_that_define_a_class_differently_warn_and_the_newer_wins(self):
        self.doc("old.md", "x", "pdfmd-options:\n  ranking:\n    classes:\n      k: {words: [y, x], above: numbers}\n")
        self.doc("new.md", "y", "pdfmd-options:\n  ranking:\n    classes:\n      k: {words: [x, y], above: numbers}\n")
        done = self.run_pdfmd()
        self.assertIn("class k is defined differently in", done.stderr)
        self.assertEqual(self.built(), ["new.assembled.md"])

    def test_inherit_false_stops_the_climb(self):
        self.three()
        self.put(self.root / "top" / ".pdfmd" / "ranking.yaml", FRUIT)
        self.put(self.work / ".pdfmd" / "ranking.yaml", "inherit: false\n")
        done = self.run_pdfmd()
        self.assertIn("is not a priority", done.stderr)                      # banana is unknown again
        self.assertEqual(self.built(), ["a.assembled.md"])

    # -- what they change -------------------------------------------------------------------------------------------

    def test_by_priority_makes_equal_priority_an_error_that_says_what_raised_each(self):
        self.doc("a.md", 2)
        self.doc("b.md", 2)
        self.put(self.work / ".pdfmd" / "ranking.yaml", "by: [priority]\n")
        done = self.run_pdfmd()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("tie for first place", done.stderr)
        self.assertIn("a.md: priority: 2", done.stderr)
        self.assertEqual(self.built(), [])

    def test_by_oldest_and_the_comma_form_of_the_config_row(self):
        self.doc("a.md")
        self.doc("b.md")
        self.put(self.config, "options:\n  ranking:\n    by: priority, oldest\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["a.assembled.md"])

    def test_names_folder_lets_a_final_name_take_over_and_off_ignores_names(self):
        self.doc("report.md")
        self.doc("report.final.md")
        self.doc("zzz.md")                                  # the newest, unrelated
        self.put(self.work / ".pdfmd" / "ranking.yaml", "names: folder\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["report.final.assembled.md"])
        for path in self.work.glob("*.assembled.md"):
            path.unlink()
        self.put(self.work / ".pdfmd" / "ranking.yaml", "names: off\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["zzz.assembled.md"])                # three equal documents: the newest

    def test_a_custom_ladder_reorders_the_built_in_classes(self):
        self.doc("a.md", "final")
        self.doc("b.md", 5)
        self.put(self.work / ".pdfmd" / "ranking.yaml", "ladder: [never, draft, unset, revised, final, numbers]\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["b.assembled.md"])

    # -- mistakes ------------------------------------------------------------------------------------------------------

    def test_a_mistake_in_a_ranking_stops_the_choice_and_names_the_file(self):
        self.doc("a.md")
        self.doc("b.md")
        self.put(self.work / ".pdfmd" / "ranking.yaml", "classes:\n  fruit: {words: [final], above: numbers}\n")
        done = self.run_pdfmd()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("ranking.yaml", done.stderr)
        self.assertIn("two classes: final (built-in) and fruit (", done.stderr)

    def test_a_class_that_is_nowhere_on_the_ladder_is_a_warning(self):
        self.doc("a.md")
        self.doc("b.md")
        self.put(self.work / ".pdfmd" / "ranking.yaml", "classes:\n  fruit: [cherry]\n")
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("class fruit is not on the ladder", done.stderr)

    def test_nothing_is_read_when_there_is_nothing_to_choose(self):
        self.doc("only.md")
        self.put(self.work / ".pdfmd" / "ranking.yaml", "classes: [this is not valid\n")
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, "")
        self.assertEqual(self.built(), ["only.assembled.md"])

    def test_a_ranking_yaml_wrapped_in_ranking_is_accepted(self):
        self.three()
        self.put(self.work / ".pdfmd" / "ranking.yaml", "ranking:\n  classes:\n    fruit: {words: [cherry, banana], above: numbers}\n")
        self.assertEqual(self.run_pdfmd().returncode, 0)
        self.assertEqual(self.built(), ["b.assembled.md"])


if __name__ == "__main__":
    unittest.main()
