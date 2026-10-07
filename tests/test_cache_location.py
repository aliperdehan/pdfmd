"""Where the cache lives (global or beside the document) and finding it again after a move."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402


class CacheCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name).resolve()
        self._saved = {key: os.environ.get(key) for key in ("XDG_CACHE_HOME", "PDFMD_CONFIG")}
        os.environ["XDG_CACHE_HOME"] = str(self.root / "cache")
        pdfmd.CACHE_LOCATION_CLI = None
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        pdfmd.CACHE_LOCATION_CLI = None
        pdfmd.load_config.cache_clear()

    def document(self, folder: str, text: str = "# Report\n\ntext\n", front: str = "") -> Path:
        path = self.root / folder / "report.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((f"---\n{front}---\n" if front else "") + text, encoding="utf-8")
        return path


class Location(CacheCase):
    def test_global_is_the_default(self):
        doc = self.document("a")
        self.assertEqual(pdfmd.cache_location(doc, []), "global")
        self.assertEqual(pdfmd.document_cache_root(doc, []), pdfmd.cache_root())

    def test_the_document_the_config_and_the_command_line_can_choose_beside_the_document(self):
        doc = self.document("a", front="pdfmd-options:\n  cache: {aux: true, location: document}\n")
        self.assertEqual(pdfmd.cache_location(doc, []), "document")
        self.assertEqual(pdfmd.document_cache_root(doc, []), self.root / "a" / ".cache" / "pdfmd")
        plain = self.document("b")
        config = self.root / "config.yaml"
        config.write_text("options:\n  cache: {location: local}\n", encoding="utf-8")
        os.environ["PDFMD_CONFIG"] = str(config)
        pdfmd.load_config.cache_clear()
        self.assertEqual(pdfmd.cache_location(plain, []), "document")          # `local` is an alias
        own = self.document("c", front="pdfmd-options:\n  cache-location: global\n")
        self.assertEqual(pdfmd.cache_location(own, []), "global")               # the document beats the config
        pdfmd.CACHE_LOCATION_CLI = "global"
        self.assertEqual(pdfmd.cache_location(plain, []), "global")             # the command line beats both

    def test_a_bad_location_is_an_error(self):
        doc = self.document("a", front="pdfmd-options:\n  cache: {location: moon}\n")
        with self.assertRaises(SystemExit):
            pdfmd.cache_location(doc, [])

    def test_the_local_folder_is_marked_as_a_cache_and_ignored_by_git(self):
        doc = self.document("a")
        local = self.root / "a" / ".cache" / "pdfmd"
        pdfmd.prepare_cache_root(local)
        self.assertTrue((local / "CACHEDIR.TAG").read_text(encoding="utf-8").startswith("Signature: 8a477f59"))
        self.assertEqual((self.root / "a" / ".cache" / ".gitignore").read_text(encoding="utf-8"), "*\n")
        self.assertEqual(pdfmd.cache_directory(doc, local), local / "report")
        self.assertNotEqual(pdfmd.cache_directory(doc), local / "report")


class Moving(CacheCase):
    def build(self, doc: Path) -> Path:
        folder = pdfmd.cache_directory(doc)
        folder.mkdir(parents=True, exist_ok=True)
        pdfmd.write_cache_manifest(folder, doc)
        (folder / "report.aux").write_text("aux of " + str(doc), encoding="utf-8")
        return folder

    def test_a_moved_document_finds_its_cache_by_content(self):
        doc = self.document("downloads/lab")
        old = self.build(doc)
        new_dir = self.root / "onedrive" / "lab"
        new_dir.parent.mkdir(parents=True)
        shutil.move(str(doc.parent), str(new_dir))
        moved = new_dir / "report.md"
        notes = []
        target = pdfmd.cache_directory(moved, note=lambda *a: notes.append(a))
        self.assertTrue((target / "report.aux").is_file())
        self.assertFalse(old.exists())
        self.assertNotEqual(target, old)
        self.assertEqual(json.loads((target / pdfmd.CACHE_MANIFEST).read_text(encoding="utf-8"))["path"], str(moved))
        self.assertTrue(notes and notes[0][0] == "CACHE")

    def test_an_edit_before_the_move_is_found_by_the_folder_name(self):
        doc = self.document("downloads/lab")
        self.build(doc)
        doc.write_text("# Report\n\nedited\n", encoding="utf-8")
        new_dir = self.root / "onedrive" / "lab"
        new_dir.parent.mkdir(parents=True)
        shutil.move(str(doc.parent), str(new_dir))
        self.assertTrue((pdfmd.cache_directory(new_dir / "report.md") / "report.aux").is_file())

    def test_a_copy_does_not_take_the_originals_cache(self):
        doc = self.document("downloads/lab")
        old = self.build(doc)
        copy = self.root / "onedrive" / "lab"
        shutil.copytree(doc.parent, copy)
        target = pdfmd.cache_directory(copy / "report.md")
        self.assertFalse(target.exists())
        self.assertTrue(old.exists())

    def test_two_candidates_by_name_are_not_guessed_between(self):
        first = self.document("one/lab")
        second = self.document("two/lab", text="# Another\n")
        self.build(first)
        self.build(second)
        for original in (first, second):
            original.write_text(original.read_text(encoding="utf-8") + "edit\n", encoding="utf-8")
        new_dir = self.root / "moved" / "lab"
        new_dir.parent.mkdir(parents=True)
        shutil.copytree(first.parent, new_dir)
        shutil.rmtree(first.parent)
        shutil.rmtree(second.parent)
        self.assertFalse(pdfmd.cache_directory(new_dir / "report.md").exists())

    def test_plot_entries_follow_a_moved_report(self):
        old_root = self.root / "downloads" / "lab"
        old_root.mkdir(parents=True)
        data = old_root / "data.csv"
        data.write_text("1,2\n", encoding="utf-8")
        plots = self.root / "cache" / "plots-abc"
        plots.mkdir(parents=True)
        (plots / "k1.deps").write_text(json.dumps({str(data): pdfmd.sha1_file(data), "__roots__": [str(old_root)]}),
                                      encoding="utf-8")
        for suffix in (".pdf", ".dim"):
            (plots / f"k1{suffix}").write_text("x", encoding="utf-8")
        new_root = self.root / "onedrive" / "lab"
        new_root.parent.mkdir(parents=True)
        shutil.move(str(old_root), str(new_root))
        self.assertEqual(pdfmd.validate_plot_entries(plots, False, [new_root]), 0)
        self.assertTrue((plots / "k1.pdf").exists())
        self.assertEqual(json.loads((plots / "k1.deps").read_text(encoding="utf-8"))["__roots__"], [str(new_root)])
        (new_root / "data.csv").write_text("changed\n", encoding="utf-8")        # a real change still drops it
        self.assertEqual(pdfmd.validate_plot_entries(plots, False, [new_root]), 1)
        self.assertFalse((plots / "k1.pdf").exists())


if __name__ == "__main__":
    unittest.main()
