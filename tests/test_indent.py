"""Paragraph indentation for a stretch of text (v3.30.0): the `::: {indent=false}` div, pdfmd_lua/indent.lua per writer,
the detection that adds the filter, and real PDFs measured (the first word's left edge) through the whole pipeline,
parts included."""

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

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
INDENT_LUA = ROOT / "pdfmd_lua" / "indent.lua"

LONG = " words to wrap onto a second line so that the first-line indent is visible in the output of the build."
NESTED = f"""Outer.{LONG}

::: {{indent=false}}
Inside.{LONG}

::: {{#inner indent=3em}}
Nested.{LONG}
:::

Back.{LONG}
:::

After.{LONG}
"""


class Detection(unittest.TestCase):
    def test_the_spellings_that_add_the_filter(self):
        for text in ("::: {indent=false}", "::: noindent", "::: {.noindent}", "::: {#a .indent}", "::::: {indent=2em}",
                     '::: {style="x" indent="1em"}', "::: indent", "  ::: {indent=true}",
                     "::: .indent=3in", "::: indent=3in", "::: indent-3in", "::: {.indent-3in}", "::: {.indent=3in}",
                     "::: .indent", "::: .indent3in", "::: .noindent=2em"):          # the last two: near misses, the filter warns
            with self.subTest(text=text):
                self.assertTrue(pdfmd.INDENT_DIV_RE.search(text))

    def test_what_does_not(self):
        for text in ("::: {.csv}", "::: indented", "indent = false", "indent: true", "`::: noindent` is the div", "::: {.indentation}",
                     "::: .indented", "::: .indentation", "::: indentation-x"):
            with self.subTest(text=text):
                self.assertFalse(pdfmd.INDENT_DIV_RE.search(text))

    def test_the_filter_goes_in_only_for_a_document_with_one(self):
        with tempfile.TemporaryDirectory() as directory:
            plain = Path(directory) / "plain.md"
            plain.write_text("Text.\n", encoding="utf-8")
            marked = Path(directory) / "marked.md"
            marked.write_text("Text.\n\n::: noindent\nx\n:::\n", encoding="utf-8")
            self.assertEqual(pdfmd.indent_filter_args(plain), [])
            self.assertEqual(pdfmd.indent_filter_args([plain, marked])[0], "--lua-filter")      # one of the parts is enough


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def convert(self, text: str, writer: str, reader: str = "markdown") -> subprocess.CompletedProcess:
        return subprocess.run([PANDOC, "-f", reader, "-t", writer, "--lua-filter", str(INDENT_LUA)], input=text,
                              capture_output=True, text=True, encoding="utf-8")

    def test_latex_sets_the_indent_in_a_group_and_the_group_closes_with_the_div(self):
        out = self.convert(NESTED, "latex").stdout
        order = [out.find(word) for word in ("Outer.", "\\begingroup\\setlength{\\parindent}{0pt}", "Inside.",
                                             "\\begingroup\\setlength{\\parindent}{3em}", "Nested.", "Back.", "After.")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn(-1, order)
        self.assertEqual(out.count("\\begingroup"), 2)
        self.assertEqual(out.count("\\endgroup"), 2)
        self.assertLess(out.rfind("\\endgroup"), out.find("After."))
        self.assertLess(out.find("Nested."), out.find("\\endgroup"))
        self.assertLess(out.find("\\endgroup"), out.find("Back."))               # the inner group closes first
        self.assertTrue("\\label{inner}" in out or "\\hypertarget{inner}" in out, out)   # the id stays (Pandoc 3.1 writes a hypertarget)

    def test_the_values(self):
        for value, length in (("false", "0pt"), ("no", "0pt"), ("off", "0pt"), ("0", "0pt"), ("true", "1.5em"),
                              ("yes", "1.5em"), ("2em", "2em"), ("12pt", "12pt"), ("5mm", "5mm"), ("0.2in", "0.2in"),
                              ("2", "2em"), ('"1.25 em"', "1.25em"), ('"2 furlongs"', None)):
            with self.subTest(value=value):
                done = self.convert(f"::: {{indent={value}}}\nx\n:::\n", "latex")
                if length is None:
                    self.assertIn("is not an indent", done.stderr)
                    self.assertNotIn("\\parindent", done.stdout)
                else:
                    self.assertIn("\\setlength{\\parindent}{" + length + "}", done.stdout)

    def test_the_class_spellings(self):
        self.assertIn("{0pt}", self.convert("::: noindent\nx\n:::\n", "latex").stdout)
        self.assertIn("{0pt}", self.convert("::: {.noindent}\nx\n:::\n", "latex").stdout)
        self.assertIn("{1.5em}", self.convert("::: {.indent}\nx\n:::\n", "latex").stdout)
        self.assertIn("{4em}", self.convert("::: {.noindent indent=4em}\nx\n:::\n", "latex").stdout)     # the value wins
        self.assertIn("\\begingroup", self.convert("::: {indent=false}\nx\n:::\n", "beamer").stdout)

    def test_the_value_in_the_class_word(self):
        # Pandoc reads `::: indent=3in` as one class word; only the braced form carries attributes
        for text, length in (("::: .indent=3in", "3in"), ("::: indent=3in", "3in"), ("::: indent-3in", "3in"),
                             ("::: {.indent-3in}", "3in"), ("::: {.indent=3in}", "3in"), ("::: indent=false", "0pt"),
                             ("::: .indent-no", "0pt"), ("::: indent=true", "1.5em"), ("::: indent-2", "2em"),
                             ("::: .indent=1.5em", "1.5em"), ("::: .noindent", "0pt"), ("::: .indent", "1.5em")):
            with self.subTest(text=text):
                done = self.convert(f"{text}\nx\n:::\n", "latex")
                self.assertEqual(done.stdout.count("\\setlength{\\parindent}{" + length + "}"), 1, done.stdout)
                self.assertEqual(done.stderr, "")
                self.assertNotIn("indent=", done.stdout.replace("\\parindent", ""))

    def test_the_value_in_the_class_word_goes_through_the_same_parser_in_every_writer(self):
        self.assertIn('text-indent: 3in', self.convert("::: indent=3in\nx\n:::\n", "html").stdout)
        self.assertIn("first-line-indent: (amount: 3in, all: true)", self.convert("::: .indent=3in\nx\n:::\n", "typst").stdout)
        kept = self.convert("::: indent=3in\nx\n:::\n", "markdown").stdout
        self.assertIn("indent=3in", kept)                                           # the Markdown writer keeps it as written

    def test_a_bad_value_in_the_class_word_warns_like_the_attribute(self):
        done = self.convert("::: indent=banana\nx\n:::\n", "latex")
        self.assertIn("WARN  indent: 'banana' is not an indent", done.stderr)
        self.assertNotIn("parindent", done.stdout)

    def test_the_other_classes_and_the_id_stay(self):
        out = self.convert("::: {#box .indent-3in .shaded}\nx\n:::\n", "html").stdout
        self.assertIn('id="box"', out)
        self.assertIn('class="shaded"', out)
        self.assertIn("text-indent: 3in", out)
        self.assertNotIn("indent-3in", out)

    def test_a_near_miss_warns_once_and_changes_nothing(self):
        for text, shown in ((".indent3in", ".indent3in"), (".noindent=2em", ".noindent=2em"), ("indent3in", "indent3in"),
                            ("{.noindent-2em}", "noindent-2em"), (".indentem", ".indentem"), ("indent=", "indent=")):
            with self.subTest(text=text):
                done = self.convert(f"::: {text}\nx\n:::\n", "latex")
                self.assertEqual(done.stderr.strip(), f"WARN  indent: '{shown}' is not an indent div; write ::: {{indent=3in}} (or ::: noindent)")
                self.assertNotIn("parindent", done.stdout)
                self.assertNotIn("begingroup", done.stdout)
                html = self.convert(f"::: {text}\nx\n:::\n", "html").stdout
                self.assertNotIn("text-indent", html)
                self.assertIn(f'class="{shown}"', html)                              # the div is as it was written

    def test_a_near_miss_beside_a_real_indent_div_does_not_disturb_it(self):
        done = self.convert("::: .indent3in\na\n:::\n\n::: indent=2em\nb\n:::\n", "latex")
        self.assertEqual(done.stdout.count("\\setlength"), 1)
        self.assertIn("{2em}", done.stdout)
        self.assertEqual(done.stderr.count("WARN"), 1)

    def test_classes_a_project_may_own_are_left_alone_without_a_warning(self):
        for text in (".indented", ".indentation", "indent-block", ".indent-block", "{.indentation}", ".noindented", "{.indent-list .x}"):
            with self.subTest(text=text):
                done = self.convert(f"::: {text}\nx\n:::\n", "latex")
                self.assertEqual(done.stderr, "")
                self.assertNotIn("parindent", done.stdout)

    def test_an_invalid_value_warns_and_changes_nothing(self):
        done = self.convert("::: {indent=banana}\nx\n:::\n", "latex")
        self.assertIn("WARN  indent: 'banana'", done.stderr)
        self.assertNotIn("parindent", done.stdout)
        self.assertNotIn("banana", done.stdout)

    def test_typst_sets_the_rule_in_a_content_block(self):
        out = self.convert(NESTED, "typst").stdout
        self.assertIn("#[#set par(first-line-indent: 0pt)", out)
        self.assertIn("#[#set par(first-line-indent: (amount: 3em, all: true))", out)
        self.assertEqual(out.count("\n]"), 2 + 0)
        self.assertIn("] <inner>", out)

    def test_html_gets_a_text_indent_style(self):
        out = self.convert(NESTED, "html").stdout
        self.assertIn('<div style="text-indent: 0pt">', out)
        self.assertIn('<div id="inner" style="text-indent: 3em">', out)
        self.assertNotIn("indent=", out)
        self.assertIn('style="color: red; text-indent: 0pt"', self.convert('::: {style="color: red" indent=false}\nx\n:::\n', "html").stdout)

    def test_markdown_keeps_the_div_as_written(self):
        out = self.convert(NESTED, "markdown").stdout
        self.assertIn('indent="false"', out)
        self.assertIn("indent=\"3em\"", out)

    def test_a_writer_without_a_paragraph_indent_keeps_the_text_and_says_so(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "plain", "--lua-filter", str(INDENT_LUA)], input=NESTED,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertIn("Inside.", done.stdout)
        self.assertIn("NOTE  indent: 2 indent settings left out: plain has no per-block paragraph indent", done.stderr)


NAMES = ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot")


def first_words(pdf: Path) -> dict[str, float]:
    """The left edge of every word that ends in a full stop and starts a line (`Inside.`), from pdftotext -bbox."""
    xml = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"], capture_output=True, text=True).stdout
    edges = {}
    for match in re.finditer(r'<word xMin="([\d.]+)"[^>]*>([A-Z][a-z]+)\.</word>', xml):
        edges[match.group(2)] = float(match.group(1))
    return edges


@unittest.skipUnless(PANDOC and shutil.which("lualatex") and shutil.which("pdftotext"), "needs Pandoc, LuaLaTeX and pdftotext")
class RealOutput(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-indent-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def build(self, name: str, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, "--no-backup", *arguments], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8")

    def check(self, edges):
        self.assertGreater(edges["Outer"], edges["Inside"] + 5)                  # the document's indent, then none
        self.assertAlmostEqual(edges["Back"], edges["Inside"], places=1)
        self.assertGreater(edges["Nested"], edges["Inside"] + 20)                # three ems
        self.assertAlmostEqual(edges["After"], edges["Outer"], places=1)         # the document's own is back

    def test_a_pdf_has_the_text_indented_unindented_and_back(self):
        (self.directory / "doc.md").write_text("---\nindent: true\n---\n\n" + NESTED, encoding="utf-8")
        done = self.build("doc.md", "-e", "lualatex")
        self.assertTrue((self.directory / "doc.pdf").exists(), done.stdout + done.stderr)
        self.check(first_words(self.directory / "doc.pdf"))

    def test_every_spelling_of_the_value_indents_by_that_much(self):
        # three centimetres: the first word of the paragraph sits that far right of the unindented one
        lines = ["---\nlang: en\n---\n", "Plain.%s" % LONG, ""]
        for number, spelling in enumerate(("::: .indent=3cm", "::: indent=3cm", "::: indent-3cm", "::: {.indent-3cm}",
                                           "::: {.indent=3cm}", "::: {indent=3cm}"), start=1):
            lines += [spelling, "%s.%s" % (NAMES[number - 1], LONG), ":::", ""]
        (self.directory / "doc.md").write_text("\n".join(lines), encoding="utf-8")
        done = self.build("doc.md", "-e", "lualatex")
        self.assertTrue((self.directory / "doc.pdf").exists(), done.stdout + done.stderr)
        edges = first_words(self.directory / "doc.pdf")
        for name in NAMES:
            with self.subTest(name=name):
                self.assertAlmostEqual(edges[name] - edges["Plain"], 3 / 2.54 * 72, delta=1.0)

    def test_a_near_miss_warns_through_the_build_and_does_not_indent(self):
        (self.directory / "doc.md").write_text("---\nlang: en\n---\n\nPlain.%s\n\n::: .indent3in\nNear.%s\n:::\n" % (LONG, LONG), encoding="utf-8")
        done = self.build("doc.md", "-e", "lualatex")
        self.assertTrue((self.directory / "doc.pdf").exists(), done.stdout + done.stderr)
        self.assertIn("WARN  indent: '.indent3in' is not an indent div", done.stdout + done.stderr)
        edges = first_words(self.directory / "doc.pdf")
        self.assertAlmostEqual(edges["Near"], edges["Plain"], places=1)

    def test_a_div_in_a_part_reaches_the_build(self):
        (self.directory / "report.md").write_text("---\nindent: true\npdfmd-options:\n  parts: auto\n---\n", encoding="utf-8")
        (self.directory / "parts").mkdir()
        (self.directory / "parts" / "10-text.md").write_text(NESTED, encoding="utf-8")
        done = self.build("report.md", "-e", "lualatex")
        self.assertTrue((self.directory / "report.pdf").exists(), done.stdout + done.stderr)
        self.check(first_words(self.directory / "report.pdf"))


if __name__ == "__main__":
    unittest.main()
