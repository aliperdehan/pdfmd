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

    def test_scoop_gets_a_url_with_a_hash_or_it_refuses_the_manifest(self):
        self.assertRegex(self.manifest["url"], r"^https://files\.pythonhosted\.org/.*pdfmd_cli-[\d.]+-py3-none-any\.whl$")
        self.assertRegex(self.manifest["hash"], r"^[0-9a-f]{64}$")
        self.assertIn(self.manifest["version"], self.manifest["url"])

    def test_the_version_the_wheel_and_its_hash_change_and_the_file_keeps_its_form(self):
        after = bump.rewrite(self.text, "9.9.9", "https://files.pythonhosted.org/x/pdfmd_cli-9.9.9-py3-none-any.whl", "ab" * 32)
        changed = json.loads(after)
        self.assertEqual((changed["version"], changed["hash"]), ("9.9.9", "ab" * 32))
        self.assertTrue(changed["url"].endswith("pdfmd_cli-9.9.9-py3-none-any.whl"))
        moving = ("version", "url", "hash")
        self.assertEqual({k: v for k, v in changed.items() if k not in moving}, {k: v for k, v in self.manifest.items() if k not in moving})
        self.assertEqual(list(changed), list(self.manifest))                                   # the keys keep their order
        again = bump.rewrite(self.text, self.manifest["version"], self.manifest["url"], self.manifest["hash"])
        self.assertEqual(again, self.text)                                                     # the file is what the script writes

    def test_the_wheel_is_picked_out_of_pypis_answer(self):
        data = {"urls": [{"packagetype": "sdist", "url": "s"}, {"packagetype": "bdist_wheel", "url": "w"}]}
        self.assertEqual(bump.wheel_of(data)["url"], "w")
        with self.assertRaises(SystemExit):
            bump.wheel_of({"urls": [{"packagetype": "sdist"}]})


if __name__ == "__main__":
    unittest.main()
