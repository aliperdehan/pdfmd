"""`[[Note|alias]]` written as the text Obsidian shows (entry 3ee, v3.32.26), and `<u>` underlined in every writer."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from pandoc_support import needs_pandoc  # noqa: E402
from pdfmd_obsidian import wikilinks_as_text  # noqa: E402


class Transform(unittest.TestCase):
    def text(self, source):
        return wikilinks_as_text(source).text

    def test_the_name_the_alias_and_the_heading_as_obsidian_shows_them(self):
        self.assertEqual(self.text("a [[Some note]] b"), "a Some note b")
        self.assertEqual(self.text("a [[Some note|an alias]] b"), "a an alias b")
        self.assertEqual(self.text("a [[Some note#Heading]] b"), "a Some note > Heading b")
        self.assertEqual(self.text("a [[#Heading]] b"), "a Heading b")
        self.assertEqual(self.text("a [[folder/Note#H|shown]] b"), "a shown b")
        self.assertEqual(wikilinks_as_text("[[a]] [[b]]").count, 2)

    def test_a_pipe_escaped_for_a_table_is_still_the_bar(self):
        self.assertEqual(self.text("| [[Note\\|alias]] |"), "| alias |")

    def test_markdown_in_a_name_is_kept_as_text(self):
        self.assertEqual(self.text("[[a_b*c]]"), "a\\_b\\*c")

    def test_what_is_not_a_wikilink_is_left_alone(self):
        for kept in ("[[_TOC_]]", "[[1]](http://example.org)", "![[picture.png]]", "![[note]]", "[[ ]]", "[[a]][b]",
                     "`[[code]]`", "$[[x]]$", "<!-- [[c]] -->", "```\n[[fenced]]\n```", "---\nt: '[[front]]'\n---\n"):
            with self.subTest(kept=kept):
                self.assertEqual(self.text(kept), kept)


@needs_pandoc(3, 1, 3)
class Build(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-wikilinks-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.directory / "config"),
                    "APPDATA": str(self.directory / "config")}

    def build(self, text, target, *arguments):
        (self.directory / "n.md").write_text(text, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "n.md", "-t", target, "--no-stamp", *arguments],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.directory, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        suffix = {"latex": "tex", "typst": "typ"}.get(target, target)
        return " ".join((self.directory / f"n.{suffix}").read_text(encoding="utf-8").split())

    def test_wikilinks_are_text_in_the_pdfmd_flavour_and_literal_in_pandoc(self):
        html = self.build("A [[Note|alias]] and [[Other#Part]].\n", "html")
        self.assertIn("A alias and Other &gt; Part.", html)
        html = self.build("---\npdfmd-options:\n  flavour: pandoc\n---\n\nA [[Note|alias]].\n", "html")
        self.assertIn("[[Note|alias]]", html)

    def test_underline_is_the_writers_own(self):
        source = "x <u>under</u> and <ins>ins</ins> y\n"
        self.assertIn("<u>under</u>", self.build(source, "html"))
        self.assertIn("\\ul{under}", self.build(source, "latex"))
        self.assertIn("#underline[under]", self.build(source, "typst"))
        html = self.build(source, "html", "--no-markup")
        self.assertIn("<u>under</u>", html)                 # raw HTML is what an HTML build keeps either way
        self.assertIn("under", self.build(source, "latex", "--no-markup"))
        self.assertNotIn("\\ul{", self.build(source, "latex", "--no-markup"))


if __name__ == "__main__":
    unittest.main()
