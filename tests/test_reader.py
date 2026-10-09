"""The reader pdfmd picks for a Markdown file: the `reader:` option and the notice when gfm would print Pandoc syntax (v3.26.13)."""

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

import pdfmd  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402


class BlindSpots(unittest.TestCase):
    def test_what_gfm_would_print(self):
        found = pdfmd.gfm_blind_spots("# T\n\nH~2~O, x^2^ and a note^[inline].\n\n## S {#sec}\n\n\\begin{equation} a \\end{equation}\n")
        self.assertEqual(found, ["subscripts (H~2~O)", "superscripts (x^2^)", "inline footnotes (^[...])",
                                 "{#id .class} attributes", "raw LaTeX (\\begin{...}, \\newcommand, \\ce{...})"])

    def test_code_and_plain_markdown_are_left_alone(self):
        self.assertEqual(pdfmd.gfm_blind_spots("# T\n\n~~struck~~ and `H~2~O` and a | table |\n\n```\nx^2^ \\begin{a}\n```\n"), [])


@needs_pandoc(3, 1, 3)
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-reader-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.directory / "config"),
                    "APPDATA": str(self.directory / "config")}

    def run_pdfmd(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=self.env)

    def write(self, name, text):
        (self.directory / name).write_text(text, encoding="utf-8")

    def test_the_notice_is_said_once_and_only_when_it_matters(self):
        self.write("a.md", "# Water\n\nH~2~O\n")
        self.write("b.md", "# Plain\n\nNothing special.\n")
        said = self.run_pdfmd("a.md", "-t", "html")
        self.assertIn("NOTE  a.md: no YAML front matter, so it is read as gfm, which leaves subscripts (H~2~O)", said.stdout)
        self.assertNotIn("<sub>", (self.directory / "a.html").read_text(encoding="utf-8"))
        self.assertNotIn("read as gfm", self.run_pdfmd("b.md", "-t", "html").stdout)
        again = self.run_pdfmd("a.md", "-t", "html", "--from", "markdown")        # asked for: no notice
        self.assertNotIn("read as gfm", again.stdout)
        self.assertIn("<sub>", (self.directory / "a.html").read_text(encoding="utf-8"))

    def test_the_reader_option_picks_the_dialect_for_one_document_or_a_folder(self):
        self.write("a.md", "---\ntitle: T\npdfmd-options:\n  reader: gfm\n---\n\nH~2~O\n")
        self.assertEqual(self.run_pdfmd("a.md", "-t", "html").returncode, 0)
        self.assertNotIn("<sub>", (self.directory / "a.html").read_text(encoding="utf-8"))
        self.write("b.md", "# Water\n\nH~2~O\n")
        self.write("metadata.yaml", "pdfmd-options:\n  reader: markdown\n")
        said = self.run_pdfmd("b.md", "-t", "html")
        self.assertNotIn("read as gfm", said.stdout)
        self.assertIn("<sub>", (self.directory / "b.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
