"""v3.29.30: the automatic kinds are three-state: on, off, explicit-only. The layers (the command line, the document, the folders,
the config) each say what they say and the first one that names a kind decides it; the old spellings (`--no-auto`, `no-auto:`) mean what
they always did."""

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
from pdfmd_setup import registry  # noqa: E402

try:
    import yaml
except ImportError:                                         # pragma: no cover
    yaml = None

PANDOC = shutil.which("pandoc")
PREAMBLE = "\\usepackage{xcolor}\n"
FILTER = 'function Para(p) return p end\n'


class Tree(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="pdfmd-auto-states-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()
        (self.root / "a").mkdir()
        self.doc = self.root / "a" / "d.md"
        self.write_doc("")
        self.config = self.root / "config.yaml"
        pdfmd.folder_walk.cache_clear()
        self.addCleanup(pdfmd.folder_walk.cache_clear)
        patch = mock.patch.dict(os.environ, {"PDFMD_CONFIG": str(self.config)})
        patch.start()
        self.addCleanup(patch.stop)
        pdfmd.load_config.cache_clear()
        self.addCleanup(pdfmd.load_config.cache_clear)

    def write_doc(self, options: str) -> None:
        front = f"---\ntitle: T\n{options}---\n\n" if options else "---\ntitle: T\n---\n\n"
        self.doc.write_text(front + "text\n", encoding="utf-8")

    def set_config(self, text: str) -> None:
        self.config.write_text(text, encoding="utf-8")
        pdfmd.load_config.cache_clear()

    def layer(self, text: str, where: str = "a") -> None:
        target = self.root / where / ".pdfmd"
        target.mkdir(parents=True, exist_ok=True)
        (target / "config.yaml").write_text(text, encoding="utf-8")
        pdfmd.folder_walk.cache_clear()

    def off(self, cli=None):
        return pdfmd.effective_no_auto(self.doc, cli)


@unittest.skipUnless(yaml, "needs PyYAML")
class Layers(Tree):
    def test_the_old_spellings_mean_what_they_did(self):
        self.assertIsNone(self.off())
        self.assertEqual(self.off([]), [])                                           # bare --no-auto: everything
        self.assertEqual(self.off(["title"]), ["title"])
        self.set_config("options:\n  no-auto: [margin, monofont]\n")
        self.assertEqual(self.off(["title"]), ["margin", "monofont", "title"])      # added up, as before
        self.write_doc("pdfmd-options:\n  no-auto: true\n")
        self.assertEqual(self.off(), [])
        self.write_doc("pdfmd-options:\n  no-auto: font\n")
        found = self.off()
        self.assertTrue(pdfmd.auto_disabled(found, "mainfont") and pdfmd.auto_disabled(found, "monofont"), found)
        self.assertFalse(pdfmd.auto_disabled(found, "title"))

    def test_a_nearer_layer_can_switch_back_on(self):
        self.set_config("options:\n  no-auto: [lua, margin]\n")
        self.assertEqual(self.off(), ["lua", "margin"])
        self.layer("options:\n  auto: {margin: on}\n")                                 # a folder: for what finds no code
        self.assertEqual(self.off(), ["lua"])
        self.write_doc("pdfmd-options:\n  auto: {lua: on}\n")                           # the document: for anything
        self.assertIsNone(self.off())
        self.write_doc("pdfmd-options:\n  auto: {margin: off}\n")                       # the document is nearer than the folder
        self.assertEqual(self.off(), ["lua", "margin"])

    def test_a_folder_cannot_switch_back_on_what_finds_code(self):
        self.set_config("options:\n  no-auto: [lua, preamble]\n")
        for entry in ("lua: on", "preamble: on", "files: on", "tex: on", "lua: true"):
            pdfmd.FOLDER_WARNED.clear()
            self.layer("options:\n  auto: {%s}\n" % entry)
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                found = self.off()
            self.assertEqual(found, ["lua", "preamble"], entry)
            self.assertIn("cannot be set by a folder", errors.getvalue(), entry)

    def test_a_folder_can_only_tighten_what_finds_code(self):
        self.layer("options:\n  auto: {lua: explicit-only, margin: off}\n")
        self.assertEqual(self.off(), ["margin", "explicit:lua"])
        self.set_config("options:\n  no-auto: [lua]\n")                                  # off in the config: explicit-only would loosen it
        self.assertEqual(self.off(), ["lua", "margin"])
        self.set_config("options:\n  auto: {lua: explicit-only}\n")
        self.layer("options:\n  auto: {lua: off}\n")                                    # explicit-only in the config: off tightens it
        self.assertEqual(self.off(), ["lua"])
        self.write_doc("pdfmd-options:\n  auto: {lua: explicit-only}\n")                # the document's own word is the user's
        self.assertEqual(self.off(), ["explicit:lua"])

    def test_the_nearest_folder_decides(self):
        (self.root / "a" / "b").mkdir()
        self.doc = self.root / "a" / "b" / "d.md"
        self.write_doc("")
        self.set_config("options:\n  no-auto: [margin]\n")
        self.layer("options:\n  auto: {margin: off, title: off}\n", "a")
        self.layer("options:\n  auto: {margin: on}\n", "a/b")
        self.assertEqual(self.off(), ["title"])

    def test_among_folders_what_finds_code_takes_the_strictest(self):
        (self.root / "a" / "b").mkdir()
        self.doc = self.root / "a" / "b" / "d.md"
        self.write_doc("")
        self.layer("options:\n  auto: {lua: off}\n", "a")
        self.layer("options:\n  auto: {lua: explicit-only}\n", "a/b")                 # a nearer folder cannot loosen a farther one
        self.assertEqual(self.off(), ["lua"])
        self.layer("options:\n  auto: {lua: explicit-only}\n", "a")
        self.layer("options:\n  auto: {lua: off}\n", "a/b")
        self.assertEqual(self.off(), ["lua"])

    def test_everything_off_in_a_layer_decides_what_a_nearer_one_left_alone(self):
        self.set_config("options:\n  no-auto: true\n")
        self.write_doc("pdfmd-options:\n  auto: {margin: on}\n")
        found = self.off()
        self.assertNotIn("margin", found)
        self.assertIn("lua", found)
        self.assertEqual(sorted(set(found) | {"margin"}), sorted(pdfmd.NO_AUTO_KINDS))

    def test_the_command_line_only_switches_off_and_is_the_strongest(self):
        self.write_doc("pdfmd-options:\n  auto: {lua: on, margin: on}\n")
        self.assertEqual(self.off([]), [])
        self.assertEqual(self.off(["lua"]), ["lua"])

    def test_an_auto_entry_beats_a_no_auto_entry_of_the_same_layer(self):
        self.write_doc("pdfmd-options:\n  no-auto: [lua, margin]\n  auto: {lua: explicit-only}\n")
        self.assertEqual(self.off(), ["margin", "explicit:lua"])

    def test_explicit_only_is_for_the_kinds_that_have_a_file_to_name(self):
        for kind in ("lua", "preamble", "metadata", "files", "yaml", "tex"):
            self.write_doc(f"pdfmd-options:\n  auto: {{{kind}: explicit-only}}\n")
            self.assertTrue(any(item.startswith("explicit:") for item in self.off()), kind)
        self.write_doc("pdfmd-options:\n  auto: {margin: explicit-only}\n")
        with self.assertRaises(SystemExit) as caught:
            self.off()
        self.assertIn("no file a document could name", str(caught.exception))

    def test_mistakes_are_named(self):
        for options, words in (("auto: {nothing: on}\n", "unknown pdfmd-options.auto kind nothing"),
                               ("auto: {lua: maybe}\n", "on, explicit-only or off"),
                               ("auto: lua\n", "must be a mapping"),
                               ("no-auto: [nothing]\n", "unknown pdfmd-options.no-auto kind")):
            self.write_doc("pdfmd-options:\n  " + options.replace("\n", "\n  ").rstrip(" "))
            with self.assertRaises(SystemExit) as caught:
                self.off()
            self.assertIn(words, str(caught.exception), options)

    def test_a_kind_off_in_a_metadata_file_is_still_not_read(self):
        (self.root / "a" / "metadata.yaml").write_text("pdfmd-options:\n  no-auto: [lua]\n", encoding="utf-8")
        self.assertIsNone(self.off())

    def test_the_assembled_marker_carries_the_explicit_kinds(self):
        match = pdfmd.ASSEMBLED_COMMENT_RE.search("<!-- pdfmd-assembled: true; no-auto: margin,explicit:lua -->")
        self.assertEqual(match.group("kinds").split(","), ["margin", "explicit:lua"])


@unittest.skipUnless(yaml, "needs PyYAML")
class Discovery(Tree):
    def setUp(self):
        super().setUp()
        (self.root / "a" / "preamble.tex").write_text(PREAMBLE, encoding="utf-8")
        (self.root / "a" / "named.tex").write_text("\\usepackage{xcolor}\n", encoding="utf-8")

    def preambles(self, *extra):
        return sorted(item.name for item in pdfmd.document_preambles(self.doc, [], self.off(*extra)))

    def test_a_preamble_is_found_unless_off_or_explicit_only(self):
        self.assertEqual(self.preambles(), ["preamble.tex"])
        self.assertEqual(self.preambles(["preamble"]), [])
        self.write_doc("pdfmd-options:\n  auto: {preamble: explicit-only}\n")
        self.assertEqual(self.preambles(), [])

    def test_what_the_document_names_is_kept_by_explicit_only_and_not_by_off(self):
        named = "pdfmd-options:\n  preamble: named.tex\n"
        self.write_doc(named)
        self.assertEqual(self.preambles(), ["named.tex", "preamble.tex"])
        self.write_doc(named + "  auto: {preamble: explicit-only}\n")
        self.assertEqual(self.preambles(), ["named.tex"])
        self.write_doc(named + "  auto: {preamble: off}\n")
        self.assertEqual(self.preambles(), [])

    def test_the_alias_files_covers_the_three(self):
        self.write_doc("pdfmd-options:\n  auto: {files: explicit-only}\n")
        found = self.off()
        for kind in ("lua", "preamble", "metadata"):
            self.assertTrue(pdfmd.discovery_disabled(found, kind), kind)
            self.assertFalse(pdfmd.auto_disabled(found, kind), kind)
        self.assertFalse(pdfmd.discovery_disabled(found, "margin"))


@unittest.skipUnless(yaml and PANDOC, "needs PyYAML and Pandoc")
class Builds(Tree):
    def run_pdfmd(self, *args: str) -> str:
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), str(self.doc), "-o", str(self.root / "o.html"), "--verbose", *args],
                              capture_output=True, text=True, cwd=self.root,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout + done.stderr

    def test_a_lua_filter_beside_the_document(self):
        (self.root / "a" / "d.lua").write_text(FILTER, encoding="utf-8")
        self.assertIn("d.lua", self.run_pdfmd())
        self.write_doc("pdfmd-options:\n  auto: {lua: explicit-only}\n")
        self.assertNotIn("d.lua", self.run_pdfmd())
        self.write_doc("pdfmd-options:\n  auto: {lua: explicit-only}\n  lua-filter: d.lua\n")
        self.assertIn("d.lua", self.run_pdfmd())
        self.write_doc("pdfmd-options:\n  auto: {lua: off}\n  lua-filter: d.lua\n")
        self.assertNotIn("d.lua", self.run_pdfmd())

    def test_a_metadata_file_beside_the_document(self):
        (self.root / "a" / "metadata.yaml").write_text("author: Beside\n", encoding="utf-8")
        (self.root / "a" / "extra.yaml").write_text("lang: en\n", encoding="utf-8")
        self.assertIn("metadata.yaml", self.run_pdfmd())
        self.write_doc("pdfmd-options:\n  auto: {metadata: explicit-only}\n")
        self.assertNotIn("metadata.yaml", self.run_pdfmd())
        self.write_doc("pdfmd-options:\n  auto: {metadata: explicit-only}\n  yaml: extra.yaml\n")
        shown = self.run_pdfmd()
        self.assertIn("extra.yaml", shown)
        self.assertNotIn("metadata.yaml", shown)

    def test_explicit_only_metadata_keeps_the_users_own_defaults(self):
        (self.config.parent / "metadata.yaml").write_text("author: The Global Author\n", encoding="utf-8")
        (self.root / "a" / "metadata.yaml").write_text("lang: en\n", encoding="utf-8")
        self.layer("options: {}\n")
        (self.root / "a" / ".pdfmd" / "metadata.yaml").write_text("papersize: a4\n", encoding="utf-8")
        pdfmd.folder_walk.cache_clear()
        shown = self.run_pdfmd()
        self.assertIn("a/metadata.yaml".replace("/", os.sep), shown)
        self.write_doc("pdfmd-options:\n  auto: {metadata: explicit-only}\n")
        shown = self.run_pdfmd()
        self.assertNotIn(os.path.join("a", "metadata.yaml"), shown.replace(os.path.join(".pdfmd", "metadata.yaml"), ""))
        self.assertIn(os.path.join("a", ".pdfmd", "metadata.yaml"), shown)                  # the folder's own stays
        self.assertIn(str(self.config.parent / "metadata.yaml").replace(str(Path.home()), "~"), shown.replace(str(Path.home()), "~"))   # so does the global one
        self.write_doc("pdfmd-options:\n  auto: {metadata: off}\n")                          # off is what it was: none at all
        shown = self.run_pdfmd()
        self.assertNotIn("metadata.yaml", shown)

    def test_a_folder_cannot_switch_a_filter_back_on_but_the_document_can(self):
        (self.root / "a" / "d.lua").write_text(FILTER, encoding="utf-8")
        self.set_config("options:\n  no-auto: [lua]\n")
        self.assertNotIn("d.lua", self.run_pdfmd())
        self.layer("options:\n  auto: {lua: on}\n")
        self.assertNotIn("d.lua", self.run_pdfmd())
        self.write_doc("pdfmd-options:\n  auto: {lua: on}\n")
        self.assertIn("d.lua", self.run_pdfmd())


@unittest.skipUnless(yaml, "needs PyYAML")
class Rows(unittest.TestCase):
    def setUp(self):
        self.settings = {setting.key: setting for setting in registry.settings_for(pdfmd.NO_AUTO_KINDS)}

    def test_the_rows_read_and_write_the_auto_mapping(self):
        stores = {"config": {"options": {"auto": {"lua": "explicit-only", "margin": "on", "title": "off"}}}}
        explicit, back = self.settings["options.auto.explicit-only"], self.settings["options.auto.on"]
        self.assertEqual(registry.read(stores, explicit), ["lua"])
        self.assertEqual(registry.read(stores, back), ["margin"])
        registry.write(stores, explicit, ["preamble", "metadata"])
        self.assertEqual(stores["config"]["options"]["auto"], {"margin": "on", "title": "off", "preamble": "explicit-only",
                                                                "metadata": "explicit-only"})
        registry.write(stores, back, None)
        registry.write(stores, explicit, None)
        self.assertEqual(stores["config"]["options"]["auto"], {"title": "off"})

    def test_an_emptied_mapping_leaves_no_trace(self):
        stores = {"config": {}}
        row = self.settings["options.auto.explicit-only"]
        registry.write(stores, row, ["lua"])
        registry.write(stores, row, None)
        self.assertEqual(stores["config"], {})
        self.assertIsNone(registry.read(stores, row))

    def test_switching_back_on_is_a_row_of_a_folder_only(self):
        import pdfmd_setup
        kept, _ = pdfmd_setup.folder_settings(list(self.settings.values()))
        self.assertIn("options.auto.on", [setting.key for setting in kept])
        self.assertIn("options.no-auto", [setting.key for setting in kept])


if __name__ == "__main__":
    unittest.main()
