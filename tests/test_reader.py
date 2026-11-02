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


class ReaderNeeds(unittest.TestCase):
    """What a file with no front matter uses that gfm does not read (v3.32.5): an extension gfm takes, or Pandoc's own reader."""

    def needs(self, text):
        return dict(pdfmd.reader_needs(text))

    def test_what_gfm_takes_as_an_extension(self):
        found = self.needs("# T\n\nH~2~O, x^2^.\n\n## S {#sec}\n\nTerm\n: definition\n\n::: note\nText\n:::\n")
        self.assertEqual(found, {"subscripts (H~2~O)": "subscript", "superscripts (x^2^)": "superscript",
                                 "{#id .class} attributes": "attributes+bracketed_spans", "fenced divs (:::)": "fenced_divs",
                                 "definition lists": "definition_lists"})

    def test_what_only_pandocs_own_reader_reads(self):
        for text, name in (("A note^[inline].\n", "inline footnotes (^[...])"),
                           ("\\begin{equation} a \\end{equation}\n", "raw LaTeX (\\begin{...}, \\newcommand{...}, \\ce{...})"),
                           ("Text \\textbf{bold} and \\ref{x}\n", "raw LaTeX (\\begin{...}, \\newcommand{...}, \\ce{...})"),
                           ("+---+---+\n| a | b |\n+===+===+\n", "grid tables"),
                           ("  A    B\n ---- ----\n  1    2\n", "simple tables"),
                           ("(@) First\n(@) Second\n", "example lists ((@))")):
            with self.subTest(text=text):
                self.assertIsNone(self.needs(text).get(name, "missing"), text)

    def test_code_math_and_comments_are_not_syntax_the_document_uses(self):
        text = ("# T\n\n~~struck~~ and `H~2~O` and `\\begin{a}` and a | table |\n\n```\nx^2^ \\begin{a} ^[n]\n```\n\n"
                "Math $\\frac{a}{b}$ and $$\\ce{H2O}$$ and a price of $5 or $10.\n\n<!-- \\newcommand{x}{y} H~2~O -->\n")
        self.assertEqual(pdfmd.reader_needs(text), [])

    def test_a_fence_that_opens_with_attributes_is_looked_at(self):
        self.assertEqual(self.needs("```{.smiles caption=\"x\"}\nCCO\n```\n"),
                         {"fenced code attributes ({.class key=value})": "attributes"})

    def test_lettered_lists_need_two_items_in_a_row(self):
        self.assertEqual(self.needs("a. one\nb. two\n"), {"lettered or Roman-numeral lists": "fancy_lists"})
        self.assertEqual(self.needs("(i) one\n(ii) two\n"), {"lettered or Roman-numeral lists": "fancy_lists"})
        self.assertEqual(self.needs("I. Introduction\n\nSome text.\n"), {})
        self.assertEqual(self.needs("A. one\n\nlater text\n\nc. unrelated\n"), {})


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

    def test_what_gfm_can_take_is_added_to_it_and_nothing_is_said_but_in_verbose(self):
        self.write("a.md", "# Water\n\nH~2~O\n")
        self.write("b.md", "# Plain\n\nNothing special.\n")
        done = self.run_pdfmd("a.md", "-t", "html")
        self.assertNotIn("NOTE", done.stdout)
        self.assertIn("<sub>2</sub>", (self.directory / "a.html").read_text(encoding="utf-8"))
        said = self.run_pdfmd("a.md", "-t", "html", "-v").stdout
        self.assertIn("reading as gfm+subscript (it uses subscripts (H~2~O))", said)
        self.assertIn("reading as gfm\n", self.run_pdfmd("b.md", "-t", "html", "-v").stdout)

    def test_what_gfm_cannot_read_switches_the_reader(self):
        self.write("a.md", "# Note\n\nText with a note^[the inline note].\n")
        said = self.run_pdfmd("a.md", "-t", "html", "-v").stdout
        self.assertIn("it uses inline footnotes (^[...]), which gfm cannot read; keeping the default markdown reader", said)
        self.assertIn("the inline note", (self.directory / "a.html").read_text(encoding="utf-8"))
        self.assertIn("footnote", (self.directory / "a.html").read_text(encoding="utf-8"))
        self.write("b.md", "# Raw\n\n\\textbf{bold} here and ```` ``` ```` no.\n")
        self.assertIn("raw LaTeX", self.run_pdfmd("b.md", "-t", "html", "-v").stdout)

    def test_the_same_syntax_in_a_code_block_changes_nothing(self):
        self.write("a.md", "# Example\n\n```\nH~2~O ^[note] \\begin{x}\n```\n")
        said = self.run_pdfmd("a.md", "-t", "html", "-v").stdout
        self.assertIn("reading as gfm\n", said)

    def test_the_reader_option_picks_the_dialect_for_one_document_or_a_folder(self):
        self.write("a.md", "---\ntitle: T\npdfmd-options:\n  reader: gfm\n---\n\nH~2~O\n")
        self.assertEqual(self.run_pdfmd("a.md", "-t", "html").returncode, 0)
        self.assertNotIn("<sub>", (self.directory / "a.html").read_text(encoding="utf-8"))
        self.write("b.md", "# Water\n\nH~2~O\n")
        self.write("metadata.yaml", "pdfmd-options:\n  reader: markdown\n")
        said = self.run_pdfmd("b.md", "-t", "html")
        self.assertNotIn("read as gfm", said.stdout)
        self.assertIn("<sub>", (self.directory / "b.html").read_text(encoding="utf-8"))


class FrontMatterCheck(unittest.TestCase):
    """`has_yaml_frontmatter` says what Pandoc's own Markdown reader says (v3.32.4). The table was measured with Pandoc 3.13
    (`pandoc -f markdown -t json`): a block opens with `---` and a non-blank line, closes with `---` or `...`."""

    def test_what_pandoc_reads_as_a_metadata_block(self):
        for text in ("---\ntitle: T\n---\n\nBody\n",
                     "---\ntitle: T\n...\n\nBody\n",
                     "---\n---\n\nBody\n",                                  # an empty block still is one (the documented escape hatch)
                     "---\n...\n\nBody\n",
                     "---\r\ntitle: T\r\n---\r\n\r\nBody\r\n",
                     "---  \ntitle: T\n---\n\nBody\n",
                     "﻿---\ntitle: T\n---\n\nBody\n",
                     "\n---\ntitle: T\n---\n\nBody\n",                      # Pandoc allows blank lines before the block
                     "---\ntitle: T\n\nauthor: A\n---\n\nBody\n"):
            with self.subTest(text=text):
                self.assertTrue(pdfmd.has_yaml_frontmatter(text))

    def test_what_pandoc_reads_as_a_horizontal_rule(self):
        for text in ("---\n\nBody\n",
                     "---\n\nBody\n\n---\n\nMore\n",                        # a second rule does not close a block the first never opened
                     "---\nBody text\n\nmore\n",                            # no closing line
                     "---\ntitle: T\n\nBody\n",
                     "---\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
                     "----\ntitle: T\n---\n",                               # four dashes are a rule
                     "Text first\n\n---\ntitle: T\n---\n",
                     ""):
            with self.subTest(text=text):
                self.assertFalse(pdfmd.has_yaml_frontmatter(text))


@needs_pandoc(3, 1, 3)
class GlobalMetadataAndTheReader(unittest.TestCase):
    """The global metadata (`pdfmd --setup`) is the machine's, not the document's: it no longer makes pdfmd keep Pandoc's reader
    for a file with no front matter (v3.32.4), and everything it sets still applies."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-reader-global-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.config = self.directory / "config" / "config.yaml"             # the global metadata is `metadata.yaml` beside it
        self.config.parent.mkdir()
        self.env = {**os.environ, "PDFMD_CONFIG": str(self.config), "XDG_CONFIG_HOME": str(self.directory / "xdg"),
                    "APPDATA": str(self.directory / "xdg")}

    def global_metadata(self, text):
        (self.config.parent / "metadata.yaml").write_text(text, encoding="utf-8")

    def write(self, name, text):
        (self.directory / name).write_text(text, encoding="utf-8")

    def run_pdfmd(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=self.env)

    def tex(self, name="a.md"):
        done = self.run_pdfmd(name, "-v", "--stop-at", "tex")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.directory / name).with_suffix(".tex").read_text(encoding="utf-8"), done.stdout

    def test_a_file_without_front_matter_is_read_as_gfm_with_global_metadata_in_place(self):
        self.global_metadata("title: Global title\n")
        self.write("a.md", "Plain text.\n\nH~2~O\n")
        tex, said = self.tex()
        self.assertIn("no YAML front matter; reading as gfm", said)
        self.assertIn("reading as gfm+subscript", said)
        self.assertIn("H\\textsubscript{2}O", tex)                               # gfm with the subscript extension
        self.assertIn("\\title{Global title}", tex)                              # ...and the global metadata still applies

    def test_what_the_global_metadata_holds_still_applies_under_gfm(self):
        self.global_metadata("title: Global title\nheader-includes:\n  - |\n    \\newcommand{\\fromglobal}{x}\nabstract: Water is H~2~O.\n")
        self.write("a.md", "Plain text.\n")
        tex, said = self.tex()
        self.assertNotIn("keeping the default markdown reader", said)
        self.assertIn("\\newcommand{\\fromglobal}{x}", tex)                      # raw LaTeX in a metadata string
        self.assertIn("H\\textsubscript{2}O", tex)                               # Markdown in a metadata string

    def test_the_global_reader_option_still_wins(self):
        self.global_metadata("pdfmd-options:\n  reader: markdown\n")
        self.write("a.md", "Plain text.\n\nH~2~O\n")
        tex, said = self.tex()
        self.assertNotIn("read as gfm", said)
        self.assertIn("H\\textsubscript{2}O", tex)

    def test_a_metadata_file_beside_the_document_still_means_pandoc_markdown(self):
        self.global_metadata("title: Global title\n")
        self.write("metadata.yaml", "author: Someone\n")
        self.write("a.md", "Plain text.\n\nH~2~O\n")
        tex, said = self.tex()
        self.assertIn("metadata.yaml is linked; keeping the default markdown reader", said)
        self.assertIn("H\\textsubscript{2}O", tex)

    def test_a_leading_rule_is_not_front_matter(self):
        self.write("a.md", "---\n\nPlain text.\n\nH~2~O\n")
        tex, said = self.tex()
        self.assertIn("no YAML front matter; reading as gfm", said)

    def test_a_bare_title_is_still_left_alone_next_to_global_metadata(self):
        """pinned, not changed: promote_bare_title() treats the global metadata as external, as before."""
        self.global_metadata("title: Global title\n")
        self.write("a.md", "# Water\n\nText\n")
        tex, _ = self.tex()
        self.assertIn("\\title{Global title}", tex)
        self.assertIn("\\section{Water}", tex)                                   # the heading was not promoted to the title


if __name__ == "__main__":
    unittest.main()
