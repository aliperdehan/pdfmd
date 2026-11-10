"""The Homebrew formula in this repository and the script that points it at a release (scripts/bump_formula.py)."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bump_formula", ROOT / "scripts" / "bump_formula.py")
bump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump)

URL = "https://files.pythonhosted.org/packages/aa/bb/cc/pdfmd_cli-9.9.9.tar.gz"
SUM = "f" * 64


class Formula(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "Formula" / "pdfmd.rb").read_text(encoding="utf-8")

    def test_only_the_top_level_url_and_checksum_change(self):
        after = bump.rewrite(self.text, URL, SUM)
        self.assertIn(f'  url "{URL}"', after)
        self.assertIn(f'  sha256 "{SUM}"', after)
        changed = [line for line, old in zip(after.splitlines(), self.text.splitlines()) if line != old]
        self.assertEqual(len(changed), 2)
        # the resources are pinned: the pyyaml and pypdf lines (four-space indent) stay as they were
        self.assertEqual(re.findall(r'(?m)^    (?:url|sha256) ".*"$', after), re.findall(r'(?m)^    (?:url|sha256) ".*"$', self.text))

    def test_a_formula_without_the_lines_is_refused(self):
        with self.assertRaises(SystemExit):
            bump.rewrite("class Pdfmd < Formula\nend\n", URL, SUM)

    def test_the_source_distribution_is_taken_from_the_release_files(self):
        data = {"urls": [{"packagetype": "bdist_wheel", "url": "w"}, {"packagetype": "sdist", "url": "s"}]}
        self.assertEqual(bump.sdist_of(data)["url"], "s")
        with self.assertRaises(SystemExit):
            bump.sdist_of({"urls": [{"packagetype": "bdist_wheel"}]})

    def test_the_formula_names_the_package_pdfmd_installs_and_is_valid_ruby(self):
        self.assertIn("pdfmd_cli-", self.text)
        self.assertIn('depends_on "pandoc"', self.text)
        ruby = shutil.which("ruby")
        if ruby is None:
            self.skipTest("no ruby")
        done = subprocess.run([ruby, "-c", str(ROOT / "Formula" / "pdfmd.rb")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_release_workflow_has_the_homebrew_job_after_the_upload(self):
        workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        job = workflow[workflow.index("\n  homebrew:"):]
        self.assertIn("needs: [version, publish]", job)
        self.assertIn("environment: homebrew", job)
        self.assertIn("scripts/bump_formula.py", job)
        self.assertIn("brew audit --strict", job)


if __name__ == "__main__":
    unittest.main()
