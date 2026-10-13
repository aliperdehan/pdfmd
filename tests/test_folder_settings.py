"""v3.29.10: folder settings. `.pdfmd/config.yaml` in the document's folder or above: the `options:` of the global config, for what is
under it, nearest first, between the metadata files and the global config; `inherit: false` ends the walk; a folder cannot set what
is the machine's."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")


class Layers(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()
        (self.root / "a" / "b").mkdir(parents=True)
        self.doc = self.root / "a" / "b" / "d.md"
        self.doc.write_text("---\ntitle: T\n---\n\ntext\n", encoding="utf-8")
        pdfmd.folder_layer_files.cache_clear()
        self.addCleanup(pdfmd.folder_layer_files.cache_clear)
        pdfmd.FOLDER_WARNED.clear()
        patch = mock.patch.object(pdfmd, "config_options", lambda: {"fallback": "global", "missing": "global"})
        patch.start()
        self.addCleanup(patch.stop)

    def layer(self, where: str, text: str) -> None:
        target = self.root / where / ".pdfmd"
        target.mkdir(parents=True, exist_ok=True)
        (target / "config.yaml").write_text(text, encoding="utf-8")

    def value(self, key: str):
        return pdfmd.first_pdfmd_option(self.doc, [], key)

    def test_a_folder_layer_sits_between_the_document_and_the_global_config(self):
        self.layer("a", "options:\n  fallback: char\n")
        self.assertEqual(self.value("fallback"), "char")
        self.assertEqual(self.value("missing"), "global")              # not set by the folder: the global config's

    def test_the_nearest_folder_wins(self):
        self.layer("a", "options:\n  fallback: char\n")
        self.layer("a/b", "options:\n  fallback: box\n")
        self.assertEqual(self.value("fallback"), "box")

    def test_the_document_and_its_metadata_win_over_a_folder(self):
        self.layer("a", "options:\n  fallback: char\n")
        self.doc.write_text("---\ntitle: T\npdfmd-options:\n  fallback: word\n---\n\ntext\n", encoding="utf-8")
        self.assertEqual(self.value("fallback"), "word")
        self.doc.write_text("---\ntitle: T\n---\n\ntext\n", encoding="utf-8")
        meta = self.root / "m.yaml"
        meta.write_text("pdfmd-options:\n  fallback: error\n", encoding="utf-8")
        self.assertEqual(pdfmd.first_pdfmd_option(self.doc, [meta], "fallback"), "error")

    def test_inherit_false_stops_the_walk(self):
        self.layer("a", "options:\n  fallback: char\n  missing: box\n")
        self.layer("a/b", "inherit: false\noptions:\n  fallback: box\n")
        self.assertEqual(self.value("fallback"), "box")
        self.assertEqual(self.value("missing"), "global")              # a's layer is not read

    def test_the_machines_settings_are_ignored_with_a_warning(self):
        self.layer("a", "translit: [greek]\nsetup-ui: fancy\noptions:\n  fallback: char\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.value("fallback"), "char")
            self.value("fallback")
        self.assertEqual(err.getvalue().count("for this machine and cannot be set by a folder"), 1)
        self.assertIn("setup-ui, translit are", err.getvalue())

    def test_a_broken_file_is_a_warning_and_nothing(self):
        self.layer("a", "options: [unclosed\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.value("fallback"), "global")
        self.assertIn("cannot be read", err.getvalue())

    def test_a_mapping_without_enabled_stays_off_as_in_the_global_config(self):
        self.layer("a", "options:\n  stamp: {mode: history}\n")
        self.assertFalse(pdfmd.frontmatter_stamp(self.doc, [])["enabled"] if pdfmd.frontmatter_stamp(self.doc, []) else False)

    def test_the_labels(self):
        self.layer("a", "options:\n  fallback: char\n")
        labels = [where for where, _ in pdfmd.option_sources(self.doc, [])]
        self.assertEqual(labels[0], "document")
        self.assertTrue(labels[1].startswith("folder "))
        self.assertEqual(labels[-1], "config")
        self.assertTrue(all(pdfmd.is_setup_layer(item) for item in labels[1:]))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Build(unittest.TestCase):
    def test_a_build_reads_the_folder_and_says_so(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".pdfmd").mkdir()
            (root / ".pdfmd" / "config.yaml").write_text("options:\n  css-scope: all\n", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "d.md").write_text("---\ntitle: T\n---\n\n# H\n\ntext\n", encoding="utf-8")
            (root / "sub" / "pdfmd.css").write_text("body { font-size: 12pt }\n", encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "sub/d.md", "--to", "latex", "-o", "sub/d.tex",
                                   "--no-stamp", "--verbose"], cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("AUTO SETTINGS", done.stdout)
            self.assertIn("fontsize=12pt", done.stdout)                 # css-scope: all came from the folder
            self.assertIn("12pt", (root / "sub" / "d.tex").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
