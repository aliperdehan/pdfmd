"""v3.29.29: `pdfmd --setup FOLDER`. A folder's own `.pdfmd/config.yaml` and `.pdfmd/metadata.yaml`, the numbered screen that writes them, and
the places a build reads them: between the document's metadata files and the global setup, the nearest folder first."""

from __future__ import annotations

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
import pdfmd_setup  # noqa: E402
from pdfmd_setup import registry  # noqa: E402

try:
    import yaml
except ImportError:                                         # pragma: no cover
    yaml = None

PANDOC = shutil.which("pandoc")
SCREEN, _ = pdfmd_setup.folder_settings(pdfmd_setup.settings_for(pdfmd.NO_AUTO_KINDS))


def number(key: str) -> int:
    return [setting.key for setting in SCREEN].index(key) + 1


class Tree(unittest.TestCase):
    """a/b/d.md, with a settings folder wherever a test puts one."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="pdfmd-folder-setup-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()
        (self.root / "a" / "b").mkdir(parents=True)
        self.doc = self.root / "a" / "b" / "d.md"
        self.doc.write_text("---\ntitle: T\n---\n\ntext\n", encoding="utf-8")
        pdfmd.folder_walk.cache_clear()
        self.addCleanup(pdfmd.folder_walk.cache_clear)
        pdfmd.FOLDER_WARNED.clear()
        self.config = self.root / "global" / "config.yaml"
        self.config.parent.mkdir()
        patch = mock.patch.dict(os.environ, {"PDFMD_CONFIG": str(self.config)})
        patch.start()
        self.addCleanup(patch.stop)
        pdfmd.load_config.cache_clear()
        self.addCleanup(pdfmd.load_config.cache_clear)

    def put(self, where: str, name: str, text: str) -> Path:
        target = self.root / where / ".pdfmd"
        target.mkdir(parents=True, exist_ok=True)
        (target / name).write_text(text, encoding="utf-8")
        return target / name


@unittest.skipUnless(yaml, "needs PyYAML")
class Reading(Tree):
    def test_the_folders_metadata_sits_between_the_files_and_the_global_one(self):
        self.config.write_text("options: {}\n", encoding="utf-8")
        (self.config.parent / "metadata.yaml").write_text("author: Global\n", encoding="utf-8")
        far = self.put("a", "metadata.yaml", "author: Far\n")
        near = self.put("a/b", "metadata.yaml", "author: Near\n")
        (self.root / "a" / "b" / "metadata.yaml").write_text("title: Local\n", encoding="utf-8")
        found = pdfmd.find_metadata(self.doc.parent, None, document_stem="d", document=self.doc)
        names = [str(item.relative_to(self.root)) if item.is_relative_to(self.root) else "global" for item in found]
        self.assertEqual(names, [os.path.join("a", "b", "metadata.yaml"), os.path.join("a", "b", ".pdfmd", "metadata.yaml"),
                                 os.path.join("a", ".pdfmd", "metadata.yaml"), os.path.join("global", "metadata.yaml")])
        order = pdfmd.pandoc_metadata_order(found)
        self.assertEqual([item.name for item in order], ["metadata.yaml"] * 4)
        self.assertEqual([item.parent.parent.name for item in order[1:3]], ["a", "b"])      # the far one, then the near one
        self.assertEqual(order[3].parent.name, "b")                                            # the local file last: it wins
        self.assertEqual(order[0].parent, self.config.parent)                                  # the global file lowest
        self.assertEqual(pdfmd.metadata_files_by_priority(found)[0], found[0])

    def test_a_folder_alone_is_a_single_file(self):
        only = self.put("a", "metadata.yaml", "author: Only\n")
        found = pdfmd.find_metadata(self.doc.parent, None, document_stem="d", document=self.doc)
        self.assertEqual(found, only)

    def test_named_files_take_no_folder_layers(self):
        self.put("a", "metadata.yaml", "author: Only\n")
        (self.root / "a" / "b" / "mine.yaml").write_text("title: Mine\n", encoding="utf-8")
        found = pdfmd.find_metadata(self.doc.parent, ["mine.yaml"], document_stem="d", document=self.doc)
        self.assertEqual([item.name for item in (found if isinstance(found, list) else [found])], ["mine.yaml"])

    def test_inherit_false_ends_the_walk_for_the_metadata_too(self):
        self.put("a", "metadata.yaml", "author: Far\n")
        self.put("a/b", "config.yaml", "inherit: false\n")
        near = self.put("a/b", "metadata.yaml", "author: Near\n")
        found = pdfmd.find_metadata(self.doc.parent, None, document_stem="d", document=self.doc)
        self.assertEqual(found, near)

    def test_the_options_of_the_folders_lie_over_the_config_for_a_document(self):
        self.config.write_text("options:\n  csv: {rows: 3, cols: 4}\n  fallback: word\n", encoding="utf-8")
        self.put("a", "config.yaml", "options:\n  csv: {rows: 8}\n  fallback: char\n")
        self.put("a/b", "config.yaml", "options:\n  csv: {cols: 9}\n")
        merged = pdfmd.config_options(self.doc)
        self.assertEqual(merged["csv"], {"rows": 8, "cols": 9})                  # field by field, the nearest first
        self.assertEqual(merged["fallback"], "char")
        self.assertEqual(pdfmd.config_options()["csv"], {"rows": 3, "cols": 4})   # without a document: the global config alone

    def test_every_row_a_folder_offers_reaches_a_build(self):
        """Each key of registry.FOLDER_OPTIONS is read for a document from its folder's settings: through first_pdfmd_option (the
        cascade most keys use) or config_options(document)."""
        self.config.write_text("options: {}\n", encoding="utf-8")
        for key in sorted(registry.FOLDER_OPTIONS):
            path = key.split(".")[1:]
            data: dict = {}
            node = data
            for part in path[:-1]:
                node = node.setdefault(part, {})
            node[path[-1]] = "from-folder"
            self.put("a", "config.yaml", yaml.safe_dump({"options": data}))
            pdfmd.folder_walk.cache_clear()
            top = path[0]
            self.assertEqual(pdfmd.config_options(self.doc).get(top), data[top], key)
            self.assertEqual(pdfmd.first_pdfmd_option(self.doc, [], top), data[top], key)

    def test_a_folder_cannot_set_what_is_the_machines(self):
        self.put("a", "config.yaml", "setup-ui: fancy\noptions:\n  fallback: char\n")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), str(self.doc), "-o", str(self.root / "o.md"), "--to", "gfm"],
                              capture_output=True, text=True, env={**os.environ, "PDFMD_NO_PROMPT": "1"})
        self.assertIn("setup-ui is for this machine", done.stderr)


@unittest.skipUnless(yaml, "needs PyYAML")
class Screen(Tree):
    def run_setup(self, lines: list[str], where: Path | str | None = None, *flags: str):
        target = str(self.root / "a" if where is None else where)
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--setup", target, *flags], input="\n".join(lines) + "\n",
                              capture_output=True, text=True, env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    def test_it_writes_the_two_files_of_the_folder(self):
        author, rows, inherit = number("author"), number("options.csv.rows"), number("inherit")
        done = self.run_setup([str(author), "The Author", str(rows), "5", str(inherit), "2", "s"])
        self.assertEqual(done.returncode, 0, done.stderr)
        folder = self.root / "a" / ".pdfmd"
        self.assertEqual(yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8")),
                         {"options": {"csv": {"rows": 5}}, "inherit": False})
        self.assertEqual(yaml.safe_load((folder / "metadata.yaml").read_text(encoding="utf-8")), {"author": "The Author"})
        self.assertFalse((self.config).exists(), "the global config is not touched")
        pdfmd.folder_walk.cache_clear()
        self.assertEqual(pdfmd.config_options(self.doc)["csv"], {"rows": 5})
        self.assertEqual(pdfmd.find_metadata(self.doc.parent, None, document_stem="d", document=self.doc), folder / "metadata.yaml")

    def test_it_offers_no_row_of_the_machine_and_none_a_build_cannot_take_from_a_folder(self):
        done = self.run_setup(["q"])
        for title in ("This setup screen", "Features switched off", "Alphabets"):
            self.assertNotIn(title, done.stdout)
        for setting in SCREEN:
            self.assertIn(setting.title, done.stdout)
        self.assertNotIn("Header", [setting.title for setting in SCREEN])
        shown = self.run_setup(["o", "q"]).stdout
        self.assertIn("Left out of a folder's setup", shown)
        self.assertIn("options.header", shown)
        self.assertIn("bibliography", shown)

    def test_an_emptied_folder_loses_its_files_and_its_folder(self):
        author = number("author")
        self.run_setup([str(author), "X", "s"])
        self.assertTrue((self.root / "a" / ".pdfmd" / "metadata.yaml").is_file())
        done = self.run_setup([str(author), "-", "s"])
        self.assertIn("Removed", done.stdout)
        self.assertFalse((self.root / "a" / ".pdfmd").exists())

    def test_a_second_save_leaves_no_backup_of_its_own_header(self):
        author = number("author")
        self.run_setup([str(author), "X", "s"])
        done = self.run_setup([str(author), "Y", "s"])
        self.assertNotIn("comments are not kept", done.stdout)
        self.assertEqual(sorted(item.name for item in (self.root / "a" / ".pdfmd").iterdir()), ["metadata.yaml"])

    def test_a_name_that_is_no_folder_is_refused(self):
        done = self.run_setup(["q"], self.root / "nothing-here")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("plain, fancy or a folder", done.stderr)

    def test_presets_belong_to_the_global_setup(self):
        done = self.run_setup(["q"], None, "--preset", "lab")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("global setup", done.stderr)


@unittest.skipUnless(yaml and PANDOC, "needs PyYAML and Pandoc")
class Build(Tree):
    def test_a_document_is_built_with_its_folders_settings(self):
        self.put("a", "metadata.yaml", "author: The Folder Author\n")
        self.put("a", "config.yaml", "options:\n  csv: {rows: 4}\n")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), str(self.doc), "-o", str(self.root / "o.html"), "--verbose"],
                              capture_output=True, text=True, env={**os.environ, "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        shown = done.stdout + done.stderr
        self.assertIn("--metadata-file", shown)
        self.assertIn(os.path.join("a", ".pdfmd", "metadata.yaml"), shown)


if __name__ == "__main__":
    unittest.main()
