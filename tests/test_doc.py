"""v3.29.26: `pdfmd --doc`: the documents of this version, offline."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


def run(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": ""}
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], capture_output=True, text=True, encoding="utf-8", env=env)


class Command(unittest.TestCase):
    def test_the_list_names_each_document_with_its_size(self):
        done = run("--doc")
        self.assertEqual(done.returncode, 0, done.stderr)
        for name in ("readme", "recipes", "agents", "changelog"):
            self.assertRegex(done.stdout, rf"(?m)^\s+{name}\s+\d+ KB")
        self.assertIn(pdfmd.PDFMD_VERSION, done.stdout)

    def test_a_document_is_printed_when_the_output_is_not_a_terminal(self):
        done = run("--doc", "agents")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.startswith("# pdfmd for an agent"))
        self.assertEqual(run("--doc", "agents", "--print").stdout, done.stdout)

    def test_the_path_is_the_file(self):
        done = run("--doc", "recipes", "--path")
        self.assertEqual(Path(done.stdout.strip()).name, "recipes.md")
        self.assertTrue(Path(done.stdout.strip()).is_file())

    def test_a_section_by_number_and_by_word(self):
        by_number = run("--doc", "agents", "1").stdout
        self.assertTrue(by_number.startswith("## The ten commands that matter"), by_number[:60])
        self.assertNotIn("## Reading what pdfmd says", by_number)            # it ends at the next heading of its level
        by_word = run("--doc", "agents", "running", "without").stdout
        self.assertTrue(by_word.startswith("## Running without a person"))
        self.assertIn("PDFMD_NO_PROMPT", by_word)

    def test_a_section_that_is_not_there_is_an_error(self):
        done = run("--doc", "agents", "no such part")
        self.assertEqual(done.returncode, 1)
        self.assertIn("no section", done.stderr)

    def test_an_unknown_name_lists_the_known_ones(self):
        done = run("--doc", "manual")
        self.assertEqual(done.returncode, 2)
        self.assertIn("readme, recipes, agents, changelog", done.stderr)

    def test_search_finds_a_heading_path_and_a_line(self):
        done = run("--doc", "search", "doctor", "deep")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout, r"(?m)^agents: .* \(line \d+\): ")
        self.assertEqual(run("--doc", "search", "zzzzqqqq").returncode, 1)

    def test_print_and_path_need_doc(self):
        done = run("--print")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("go with --doc", done.stdout + done.stderr)


class Reading(unittest.TestCase):
    def test_headings_ignore_fenced_code(self):
        text = "# One\n\n```sh\n# a comment, not a heading\n```\n\n## Two\n\n~~~\n## nor this\n~~~\n\n### Three ###\n"
        self.assertEqual([(level, title) for _, level, title in pdfmd.document_headings(text)],
                         [(1, "One"), (2, "Two"), (3, "Three")])

    def test_a_section_runs_to_the_next_heading_of_its_level_or_higher(self):
        text = "# A\n\n## B\nb text\n\n### C\nc text\n\n## D\nd text\n"
        self.assertEqual(pdfmd.document_section(text, "B")[1], "## B\nb text\n\n### C\nc text\n")
        self.assertEqual(pdfmd.document_section(text, "2")[0], "D")
        self.assertIsNone(pdfmd.document_section(text, "9"))


class Contents(unittest.TestCase):
    def test_every_flag_the_agent_guide_names_exists(self):
        guide = (ROOT / "docs" / "agents.md").read_text(encoding="utf-8")
        flags = set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", guide))
        known = set(re.findall(r"(--[a-z][a-z0-9-]*)", run("--help", "all").stdout))
        self.assertTrue(flags)
        self.assertEqual(sorted(flags - known), [])

    def test_every_pdfmd_command_of_the_guide_parses(self):
        guide = (ROOT / "docs" / "agents.md").read_text(encoding="utf-8")
        parser = pdfmd.build_parser()
        for line in guide.splitlines():
            if line.startswith("pdfmd "):
                command = line.split("#")[0].strip()
                import shlex
                words = shlex.split(command)[1:]
                try:
                    parser.parse_known_args(words)
                except SystemExit as error:
                    self.fail(f"{command}: {error}")

    def test_the_documents_of_a_checkout_exist(self):
        for name in pdfmd.DOCUMENTS:
            self.assertIsNotNone(pdfmd.document_file(name), name)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Render(unittest.TestCase):
    def test_a_page_is_made_once_per_version(self):
        with tempfile.TemporaryDirectory() as cache:
            from unittest import mock
            with mock.patch.object(pdfmd, "cache_root", lambda: Path(cache)):
                page = pdfmd.render_document(ROOT / "docs" / "agents.md", "pdfmd: agents")
                self.assertTrue(page and page.is_file())
                text = page.read_text(encoding="utf-8")
                self.assertIn("The ten commands that matter", text)
                before = page.stat().st_mtime_ns
                self.assertEqual(pdfmd.render_document(ROOT / "docs" / "agents.md", "pdfmd: agents"), page)
                self.assertEqual(page.stat().st_mtime_ns, before)


@unittest.skipUnless(shutil.which("pip") or True, "")
class Bundling(unittest.TestCase):
    def test_the_build_copies_the_documents_into_the_package(self):
        try:
            import setuptools
        except ImportError:
            self.skipTest("needs setuptools")
        try:
            version = tuple(int(part) for part in setuptools.__version__.split(".")[:2])
        except ValueError:
            version = (0, 0)
        if version < (77, 0):               # pyproject.toml's `license = "MIT AND Apache-2.0"` (PEP 639) is read by setuptools 77 and later
            self.skipTest(f"the license of pyproject.toml needs setuptools 77 or newer (this is {setuptools.__version__})")
        with tempfile.TemporaryDirectory() as folder:
            done = subprocess.run([sys.executable, "setup.py", "-q", "build_py", "--build-lib", folder], cwd=ROOT,
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            for name in ("README.md", "CHANGELOG.md", "recipes.md", "agents.md"):
                self.assertTrue((Path(folder) / "pdfmd_docs" / name).is_file(), name)
            self.assertEqual((Path(folder) / "pdfmd_docs" / "agents.md").read_text(encoding="utf-8"),
                             (ROOT / "docs" / "agents.md").read_text(encoding="utf-8"))
            self.assertTrue((Path(folder) / "pdfmd_docs" / "__init__.py").is_file())
        # (the git checkout has no copies: they are made by the build)
        self.assertFalse((ROOT / "pdfmd_docs" / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
