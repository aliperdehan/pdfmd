"""The Scoop manifest in this repository and the script that points it at a release (scripts/bump_scoop.py)."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bump_scoop", ROOT / "scripts" / "bump_scoop.py")
bump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump)


class Manifest(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "bucket" / "pdfmd.json").read_text(encoding="utf-8")
        self.manifest = json.loads(self.text)

    def test_what_scoop_requires_is_there(self):
        for key in ("version", "homepage", "license"):
            self.assertTrue(self.manifest.get(key), key)

    def test_it_needs_python_and_the_two_programs_pdfmd_drives(self):
        self.assertEqual(self.manifest["depends"], ["python", "pandoc", "typst"])

    def test_the_install_script_asks_pip_for_the_manifests_own_version(self):
        script = "\n".join(self.manifest["installer"]["script"])
        self.assertIn("pdfmd-cli==$version", script)
        self.assertTrue(self.manifest["bin"].endswith("pdfmd.exe"))

    def test_only_the_version_changes_and_the_file_keeps_its_form(self):
        after = bump.rewrite(self.text, "9.9.9")
        changed = json.loads(after)
        self.assertEqual(changed["version"], "9.9.9")
        self.assertEqual({k: v for k, v in changed.items() if k != "version"},
                         {k: v for k, v in self.manifest.items() if k != "version"})
        self.assertEqual(bump.rewrite(self.text, self.manifest["version"]), self.text)     # the file is what the script writes


if __name__ == "__main__":
    unittest.main()
