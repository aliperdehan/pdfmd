"""v3.31.37: kits, the spike of entry 3du (point 12): a chosen kit works from its own folder. The folder (and the folders `carry:`
names, `//` recursive) go on TEXINPUTS and BIBINPUTS of the engine's environment, so the kit's package needs no install into the TeX
tree. The real compile is in tests/test_kit_preamble.py (its package exists nowhere but in the kit's folder)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Search(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.kit = self.root / "kits" / "lab"
        write(self.kit / ".kit", "kit-format: 1\nname: lab\npackage: labstyle\ncarry: [labstyle.sty, assets/, nothing/]\n")
        write(self.kit / "labstyle.sty", "\\ProvidesPackage{labstyle}\n")
        (self.kit / "assets").mkdir()
        config = write(self.root / "cfg.yaml", f"kits: [{self.root / 'kits'}]\n")
        saved = {key: os.environ.get(key) for key in ("PDFMD_CONFIG", "XDG_CACHE_HOME", "TEXINPUTS", "BIBINPUTS")}
        os.environ.update({"PDFMD_CONFIG": str(config), "XDG_CACHE_HOME": str(self.root / "cache")})
        os.environ.pop("TEXINPUTS", None)
        os.environ.pop("BIBINPUTS", None)
        self.addCleanup(lambda: [os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
                                 for key, value in saved.items()])
        pdfmd.load_config.cache_clear()
        pdfmd.ACTIVE_KITS.clear()
        pdfmd.set_kit_cli(None, None)
        self.addCleanup(pdfmd.load_config.cache_clear)
        self.folder = self.root / "LR1"

    def document(self, options: str) -> Path:
        md = write(self.folder / "report.md", f"---\ntitle: T\n{options}\n---\nText.\n")
        pdfmd.ACTIVE_KITS.clear()
        return md

    def test_the_kits_folder_and_its_carried_folders_are_on_the_path(self):
        md = self.document("pdfmd-options: {kit: lab}")
        env = pdfmd.tex_search_env(md.parent, md.parent, md)
        for name in ("TEXINPUTS", "BIBINPUTS"):
            parts = env[name].split(os.pathsep)
            self.assertEqual(parts[0], ".", name)
            self.assertIn(str(self.kit), parts)
            self.assertIn(f"{self.kit / 'assets'}//", parts)
            self.assertNotIn(f"{self.kit}//", parts)                  # the whole folder is not walked
            self.assertFalse(any("nothing" in part for part in parts))  # a carried name that is no folder is not a path
            self.assertEqual(parts[-1], "")                           # the default search path follows

    def test_no_kit_no_environment(self):
        md = self.document("")
        self.assertIsNone(pdfmd.tex_search_env(md.parent, md.parent, md))
        self.assertEqual(pdfmd.kit_search_folders(md), [])
        self.assertEqual(pdfmd.kit_search_folders(None), [])

    def test_an_existing_path_is_kept_in_front(self):
        os.environ["TEXINPUTS"] = "/elsewhere"
        md = self.document("pdfmd-options: {kit: lab}")
        parts = pdfmd.tex_search_env(md.parent, md.parent, md)["TEXINPUTS"].split(os.pathsep)
        self.assertEqual(parts[0], "/elsewhere")
        self.assertIn(str(self.kit), parts)


if __name__ == "__main__":
    unittest.main()
