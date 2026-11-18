"""The filters pdfmd adds for one engine: pdfmd_lua/typst.lua (v3.27.11: links to anchors the document does not have,
pictures with an older Pandoc) and pdfmd_lua/weasyprint.lua (v3.27.12: math WeasyPrint cannot draw; v3.28.11: typeset
by KaTeX when `pdfmd --install math:katex` put it in place)."""

from __future__ import annotations

import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
TYPST = shutil.which("typst")
WEASYPRINT = shutil.which("weasyprint")
TYPST_LUA = ROOT / "lib" / "pdfmd_lua" / "typst.lua"
WEASYPRINT_LUA = ROOT / "lib" / "pdfmd_lua" / "weasyprint.lua"
NODE = shutil.which("node")
# the KaTeX this machine has (`pdfmd --install math:katex`), for the tests that typeset with it
KATEX = pdfmd.katex_runtime()

DOCUMENT = """\
# Head {#h}

Intro.

::: {#d}
A div.
:::

A [span]{#s} here.

``` {#c}
code
```

[to the head](#h) [to the div](#d) [to the span](#s) [to the code](#c) [gone](#nope) [again](#nope)
[web](https://example.org/)
"""


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


class TypstLineSpacing(unittest.TestCase):
    def test_values_are_normalised_and_bad_values_stop(self):
        for value, expected in ((None, []), ("latex", []), (" LATEX ", []),
                                (" PaNdOc ", ["-M", "pdfmd-typst-line-spacing=pandoc"])):
            with self.subTest(value=value), mock.patch.object(pdfmd, "first_pdfmd_option",
                                                                  side_effect=lambda source, metadata, key: value if key == "typst-line-spacing" else None):
                self.assertEqual(pdfmd.paragraph_spacing_typst_args(Path("doc.md"), [], "typst"), expected)
        for value in ("moon", True, ""):
            with self.subTest(value=value), mock.patch.object(pdfmd, "first_pdfmd_option",
                                                                  side_effect=lambda source, metadata, key: value if key == "typst-line-spacing" else None):
                with self.assertRaisesRegex(SystemExit, "typst-line-spacing must be latex or pandoc"):
                    pdfmd.paragraph_spacing_typst_args(Path("doc.md"), [], "typst")
                self.assertEqual(pdfmd.paragraph_spacing_typst_args(Path("doc.md"), [], "latex"), [])

    def test_document_over_metadata_over_config(self):
        with tempfile.TemporaryDirectory() as folder:
            doc, meta = Path(folder) / "doc.md", Path(folder) / "metadata.yaml"
            doc.write_text("Text.\n", encoding="utf-8")
            with mock.patch.object(pdfmd, "config_options", return_value={"typst-line-spacing": "pandoc"}):
                self.assertIn("pdfmd-typst-line-spacing=pandoc", pdfmd.paragraph_spacing_typst_args(doc, [], "typst"))
                meta.write_text("pdfmd-options: {typst-line-spacing: latex}\n", encoding="utf-8")
                self.assertEqual(pdfmd.paragraph_spacing_typst_args(doc, [meta], "typst"), [])
                doc.write_text("---\npdfmd-options: {typst-line-spacing: pandoc}\n---\n\nText.\n", encoding="utf-8")
                self.assertIn("pdfmd-typst-line-spacing=pandoc", pdfmd.paragraph_spacing_typst_args(doc, [meta], "typst"))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class PageNumbers(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-page-numbers-")
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)
        self.source = self.directory / "doc.md"

    def build(self, text, *options, target="pdf"):
        self.source.write_text(text, encoding="utf-8")
        output = self.directory / f"result.{target}"
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), str(self.source),
                               "-o", str(output), "--no-stamp", "--no-backup", "--rewrite", "--no-auto", "crossref", *options],
                              cwd=self.directory, capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return output

    def check_pdf_numbering(self, engine, text):
        try:
            import pypdf
        except ImportError:
            self.skipTest("needs pypdf for PDF text extraction")

        def content(out):
            pages = pypdf.PdfReader(out).pages
            self.assertEqual(len(pages), 1)
            return (pages[0].extract_text() or "").splitlines()

        default = self.build(text, "-e", engine)
        expected = content(default)
        self.assertIn("1", expected)
        off = text.replace("---\n", "---\npdfmd-options: {page-numbers: off}\n", 1)
        hidden = content(self.build(off, "-e", engine))
        self.assertIn("Header kept", " ".join(hidden))
        self.assertEqual(hidden, [line for line in expected if line != "1"])
        self.assertEqual(content(self.build(off, "-e", engine, "--page-numbers")), expected)
        self.assertEqual(content(self.build(text, "-e", engine, "--no-page-numbers")), hidden)

    def test_latex_keeps_header_includes_when_it_adds_an_empty_page_style(self):
        text = ("---\ntitle: Title\nheader-includes: |\n"
                "  ```{=latex}\n  \\newcommand{\\ownheading}{Header kept}\n  ```\n---\n\n"
                "`\\ownheading`{=latex}\n")
        default = self.build(text, "-s", target="tex").read_bytes()
        self.assertEqual(self.build(text, "-s", "--page-numbers", target="tex").read_bytes(), default)
        disabled = self.build(text, "-s", "--no-page-numbers", target="tex").read_text(encoding="utf-8")
        self.assertIn(r"\newcommand{\ownheading}{Header kept}", disabled)
        self.assertIn(r"\pagestyle{empty}", disabled)
        self.assertIn(r"\let\ps@plain\ps@empty", disabled)

    @unittest.skipUnless(TYPST, "needs Typst")
    def test_typst_title_page_and_header_includes(self):
        self.check_pdf_numbering("typst", "---\ntitle: Title\npage-numbering: '1'\nheader-includes: |\n"
                                 "  ```{=typst}\n  #let ownheading = [Header kept]\n  ```\n---\n\n"
                                 "`#ownheading`{=typst}\n")

    def test_word_removes_only_page_number_fields(self):
        text = """```{=openxml}
<w:p>
<w:r><w:t>Footer kept</w:t></w:r>
<w:fldSimple w:instr=" NUMPAGES "><w:r><w:t>Total kept</w:t></w:r></w:fldSimple>
<w:fldSimple w:instr=" PAGE "><w:r><w:t>Simple removed</w:t></w:r></w:fldSimple>
<w:r><w:fldChar w:fldCharType="begin"/><w:instrText> PA</w:instrText></w:r>
<w:r><w:instrText>GE </w:instrText><w:fldChar w:fldCharType="separate"/></w:r>
<w:r><w:t>Complex removed</w:t><w:fldChar w:fldCharType="end"/><w:t>After kept</w:t></w:r>
</w:p>
```
"""
        for flags in ((), ("--no-page-numbers",)):
            output = self.build(text, "--from", "markdown", *flags, target="docx")
            with zipfile.ZipFile(output) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
            for kept in ("Footer kept", "Total kept", "After kept"):
                self.assertIn(kept, document)
            self.assertEqual("Simple removed" in document, not flags)
            self.assertEqual("Complex removed" in document, not flags)

    def test_opendocument_removes_the_page_number_field(self):
        text = ('---\npdfmd-options: {odt: {engine: pandoc}}\n---\n\n'
                '```{=opendocument}\n<text:p>Footer kept '
                '<text:page-number text:select-page="current">Number removed</text:page-number>'
                '</text:p>\n```\n')
        for flags in ((), ("--no-page-numbers",)):
            output = self.build(text, "--from", "markdown", *flags, target="odt")
            with zipfile.ZipFile(output) as archive:
                document = archive.read("content.xml").decode("utf-8")
            self.assertIn("Footer kept", document)
            self.assertEqual("Number removed" in document, not flags)

    def test_typst_spacing_opt_out_works_with_page_numbers_off(self):
        text = "---\npdfmd-options: {typst-line-spacing: pandoc}\npage-numbering: '1'\n---\n\nText."
        output = self.build(text, "-s", "--no-page-numbers", target="typ")
        source = output.read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^ +(?:page)?numbering: none,")
        self.assertNotIn("bottom-edge:", source)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-typst-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def convert(self, writer: str) -> subprocess.CompletedProcess:
        source = self.directory / "doc.md"
        source.write_text(DOCUMENT, encoding="utf-8")
        return subprocess.run([PANDOC, str(source), "-t", writer, "--lua-filter", str(TYPST_LUA)], capture_output=True,
                              text=True, encoding="utf-8")

    def test_links_to_labels_stay_and_the_others_become_text(self):
        done = self.convert("typst")
        self.assertEqual(done.returncode, 0, done.stderr)
        for kept in ("#link(<h>)", "#link(<d>)", "#link(<s>)", '#link("https://example.org/")'):
            self.assertIn(kept, done.stdout)
        self.assertNotIn("<c>)", done.stdout)                      # a code block's id is no Typst label
        self.assertNotIn("<nope>", done.stdout)
        self.assertIn("to the code", done.stdout)
        self.assertIn("gone", done.stdout)
        self.assertEqual(done.stderr.count("WARN"), 1)
        self.assertIn("3 links to anchors that are not in the document (#c, #nope)", done.stderr)

    def standalone_typst(self, front: str, *extra: str) -> str:
        source = self.directory / "indent.md"
        source.write_text(f"---\ntitle: T\n{front}---\n\n# H\n\nOne.\n\nTwo.\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-s", "-t", "typst", *extra, "--lua-filter", str(TYPST_LUA)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_the_documents_indent_reaches_typst(self):
        """v3.33.42: `indent: true` indents in LaTeX; Pandoc's Typst template has no such variable, so typst.lua sets it."""
        rule = "#set par(first-line-indent: 1.5em)"
        self.assertIn(rule, self.standalone_typst("indent: true\n"))
        self.assertIn(rule, self.standalone_typst("indent: \"yes\"\n"))
        self.assertNotIn(rule, self.standalone_typst("indent: false\n"))
        self.assertNotIn(rule, self.standalone_typst(""))

    def test_the_space_between_paragraphs(self):
        """v3.33.58: `indent: true` gives Typst LaTeX's spacing (one line: the leading), and paragraph-spacing
        (`pdfmd-paragraph-spacing`) is added to it; v3.33.73: the leading is LaTeX's line pitch less the line box, and
        without either Typst's own room (1.2em - 0.65em) is added to it."""
        def rules(front: str, *extra: str) -> list[str]:
            # the `#set` rules only: Pandoc 3.1.3 defines an `endnote` with a `#stack(dir: ltr, spacing: 3pt, ...)` in every standalone document
            return [line for line in self.standalone_typst(front, *extra).splitlines() if "spacing" in line and line.startswith("#set ")]

        self.assertEqual(rules(""), ["#set par(leading: 0.5317em, spacing: 0.5317em + 0.55em)"])
        self.assertEqual(rules("indent: false\n"), ["#set par(leading: 0.5317em, spacing: 0.5317em + 0.55em)"])
        self.assertEqual(rules("indent: true\n"), ["#set par(leading: 0.5317em, spacing: 0.5317em)"])
        self.assertEqual(rules("indent: true\nlinestretch: 1.5\n"), ["#set par(leading: 1.1476em, spacing: 1.1476em)"])
        self.assertEqual(rules("indent: true\n", "-V", "linestretch=2"), ["#set par(leading: 1.7635em, spacing: 1.7635em)"])
        self.assertEqual(rules("", "-M", "pdfmd-paragraph-spacing=6pt"),
                         ["#set par(leading: 0.5317em, spacing: 0.5317em + 6pt)"])
        self.assertEqual(rules("indent: true\n", "-M", "pdfmd-paragraph-spacing=1em"),
                         ["#set par(leading: 0.5317em, spacing: 0.5317em + 1em)"])
        self.assertEqual(rules("", "-M", "pdfmd-paragraph-spacing=0pt"), ["#set par(leading: 0.5317em, spacing: 0.5317em)"])

    def test_the_line_spacing_is_latexs(self):
        """v3.33.73: lines linestretch x the class's \\baselineskip apart (10, 11, 12 pt: 12, 13.6, 14.5 TeX points; 1.2 x
        another size), less the line box of 0.7em, in Typst's points; a -V variable over the metadata; at the top of
        the body, after the template's own leading; none in a fragment."""
        def leading(front: str, *extra: str) -> str:
            text = self.standalone_typst(front, *extra)
            found = re.findall(r"#set par\(leading: ([0-9.]+em),", text)
            self.assertEqual(len(found), 1, text)
            self.assertIn('#set text(top-edge: 0.7em, bottom-edge: "baseline")', text)
            self.assertLess(text.index("#show: doc => conf("), text.index("#set par(leading:"))
            self.assertLess(text.index("#set par(leading:"), text.index("One."))
            return found[0]

        self.assertEqual(leading(""), "0.5317em")                         # the template's 11pt
        self.assertEqual(leading("fontsize: 10pt\n"), "0.4955em")
        self.assertEqual(leading("fontsize: 12pt\n"), "0.5038em")
        self.assertEqual(leading("fontsize: 12pt\nlinestretch: 2\n"), "1.7076em")
        self.assertEqual(leading("fontsize: 10pt\nlinestretch: 1.5\n"), "1.0933em")
        self.assertEqual(leading("fontsize: 14pt\n"), "0.4955em")       # no class size: 1.2 x the size
        self.assertEqual(leading("fontsize: 12pt\n", "-V", "fontsize=10pt"), "0.4955em")
        source = self.directory / "fragment.md"
        source.write_text("One.\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-t", "typst", "--lua-filter", str(TYPST_LUA)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("leading", done.stdout)

    def test_reference_entries_are_spaced_in_lines(self):
        """v3.33.59: the `refs` div's CSL entry-spacing N becomes the leading plus N lines; Pandoc's template wrote
        `spacing: Nem`, edge to edge, so 0 printed one entry's first line on the previous one's last."""
        def rules(attributes: str, identifier: str = "refs") -> list[str]:
            source = self.directory / "refs.md"
            source.write_text(f"::: {{#{identifier} .references .csl-bib-body {attributes}}}\nAn entry.\n:::\n",
                              encoding="utf-8")
            done = subprocess.run([PANDOC, str(source), "-t", "typst", "--lua-filter", str(TYPST_LUA)],
                                  capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(done.returncode, 0, done.stderr)
            return [line for line in done.stdout.splitlines() if "spacing" in line]

        self.assertEqual(rules('entry-spacing="0"'), ["#show: body => context { set par(spacing: par.leading); body }"])
        self.assertEqual(rules('entry-spacing="2"'), ["#show: body => context { set par(spacing: par.leading + 2 * "
                                                      "(par.leading + measure[X].height)); body }"])
        for value in ("2.5", "0.5"):
            self.assertEqual(rules(f'entry-spacing="{value}"'),
                             [f"#show: body => context {{ set par(spacing: par.leading + {value} * "
                              "(par.leading + measure[X].height)); body }"])
        self.assertEqual(rules(""), [])
        self.assertEqual(rules('entry-spacing="0"', "other"), [])

    @unittest.skipUnless(TYPST, "needs Typst")
    def test_the_spacing_rule_compiles(self):
        source = self.directory / "spaced.md"
        source.write_text("---\nindent: true\nmainfont: Libertinus Serif\n---\n\nOne.\n\nTwo.\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-o", str(self.directory / "spaced.pdf"), "--pdf-engine=typst",
                               "-M", "pdfmd-paragraph-spacing=6pt", "--lua-filter", str(TYPST_LUA)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_other_writers_are_untouched(self):
        done = self.convert("html")
        self.assertIn('href="#nope"', done.stdout)
        self.assertNotIn("WARN", done.stderr)

    def test_weasyprint_gets_a_table_style_while_pandocs_own_is_in(self):
        # v3.28.3: Pandoc's screen style set a narrow table's caption a syllable a line in WeasyPrint
        source = self.directory / "styled.md"
        source.write_text("---\nheader-includes: |\n  ```{=html}\n  <meta name=\"own\" content=\"kept\">\n  ```\n---\n\n"
                          "| a |\n|---|\n| 1 |\n\n: Caption\n", encoding="utf-8")
        (self.directory / "own.css").write_text("", encoding="utf-8")

        def page(*extra: str) -> str:
            done = subprocess.run([PANDOC, str(source), "-s", "-t", "html5", "--lua-filter", str(WEASYPRINT_LUA), *extra],
                                  capture_output=True, text=True, encoding="utf-8", cwd=self.directory)
            self.assertEqual(done.returncode, 0, done.stderr)
            return done.stdout

        plain = page()
        self.assertIn("min-width: 4in", plain)
        self.assertIn('name="own"', plain)                           # the document's own header-includes stay
        self.assertNotIn("min-width: 4in", page("--css", "own.css"))  # a stylesheet of one's own replaces Pandoc's
        self.assertNotIn("min-width: 4in", page("-t", "typst"))

    def test_a_label_used_twice_is_kept_by_the_first_element(self):
        # v3.28.2: "label <fig:tlc> occurs multiple times" stopped a lab report through the LaTeX filter
        source = self.directory / "twice.md"
        source.write_text("::: {#x}\nFirst.\n:::\n\n# Second {#x}\n\n[link](#x)\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-t", "typst", "--lua-filter", str(TYPST_LUA)], capture_output=True,
                              text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.count("<x>"), 2)                 # the div's label and the link to it
        self.assertIn("1 label on more than one element (x)", done.stderr)


@unittest.skipUnless(PANDOC and TYPST, "needs Pandoc and Typst")
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-typst-cli-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_typst_lists_of_figures_and_tables_with_and_without_contents(self):
        picture = self.directory / "pixel.png"
        picture.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                                         "0000000d49444154789c6360606060000000050001a5f645400000000049454e44ae426082"))
        source = self.directory / "doc.md"
        for lof, lot, toc in ((None, None, None), (False, False, False), (True, True, False), (True, True, True),
                              (True, False, False), (False, True, False)):
            with self.subTest(lof=lof, lot=lot, toc=toc):
                requests = "".join(f"{key}: {str(value).lower()}\n" for key, value in
                                   (("lof", lof), ("lot", lot), ("toc", toc)) if value is not None)
                source.write_text("---\nmainfont: Libertinus Serif\n" + requests + "---\n\n"
                                  "# Bodymarker\n\n![Figuremarker](pixel.png)\n\n"
                                  "| a | b |\n|---|---|\n| 1 | 2 |\n\n: Tablemarker\n", encoding="utf-8")
                done = self.run_pdfmd("doc.md", "-e", "typst", "--no-stamp", "--no-backup")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                text = subprocess.check_output(["pdftotext", str(source.with_suffix(".pdf")), "-"], encoding="utf-8")
                self.assertEqual(text.count("Figuremarker"), 1 + int(bool(lof)), text)
                self.assertEqual(text.count("Tablemarker"), 1 + int(bool(lot)), text)
                self.assertEqual("List of Figures" in text, bool(lof), text)
                self.assertEqual("List of Tables" in text, bool(lot), text)
                if toc:
                    self.assertLess(text.index("Contents"), text.index("List of Figures"))
                if lof and lot:
                    self.assertLess(text.index("List of Figures"), text.index("List of Tables"))

    def test_typst_list_titles_follow_the_document_language(self):
        for lang, figures, tables in (("en", "List of Figures", "List of Tables"),
                                      ("ru-RU", "Список иллюстраций", "Список таблиц"),
                                      ("fr", "Table des figures", "Liste des tableaux")):
            with self.subTest(lang=lang):
                source = self.directory / "doc.md"
                source.write_text(f"---\nlof: true\nlot: true\nlang: {lang}\n---\n\nBody.\n", encoding="utf-8")
                done = self.run_pdfmd("doc.md", "--to", "typst", "--standalone", "--no-stamp", "-o", "doc.typ")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                out = (self.directory / "doc.typ").read_text(encoding="utf-8")
                self.assertIn(figures, out)
                self.assertIn(tables, out)
                self.assertIn("figure.where(kind: image)", out)
                self.assertIn("figure.where(kind: table)", out)

    def test_inline_calls_followed_by_brackets_build_and_modern_output_is_unchanged(self):
        text = ('A *378*(6552), ~~s~~(z), [l](https://example.org)(y), **bold**(b), '
                '[caps]{.smallcaps}(c), [under]{.underline}[d], [span]{.foo}(e), '
                '*nested **bold***[f].\n')
        source = self.directory / "doc.md"
        source.write_text(text, encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-e", "typst", "--no-stamp")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        done = self.run_pdfmd("doc.md", "--to", "typst", "-o", "doc.typ")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        plain = subprocess.run([PANDOC, str(source), "-t", "typst"], capture_output=True,
                               text=True, encoding="utf-8", check=True).stdout
        if r"#emph[378]\(6552)" in plain:
            filtered = subprocess.run([PANDOC, str(source), "-t", "typst", "--lua-filter", str(TYPST_LUA)],
                                      capture_output=True, text=True, encoding="utf-8", check=True).stdout
            self.assertEqual(filtered, plain)

    def test_citeproc_volume_followed_by_issue_builds(self):
        (self.directory / "refs.bib").write_text(
            '@article{k, title={Title}, volume={378}, number={6552}}', encoding="utf-8")
        (self.directory / "style.csl").write_text(
            '<style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" version="1.0">'
            '<info><title>T</title><id>t</id></info><citation><layout><text variable="title"/>'
            '</layout></citation><bibliography><layout><text variable="volume" font-style="italic"/>'
            '<text variable="issue" prefix="(" suffix=")"/></layout></bibliography></style>', encoding="utf-8")
        (self.directory / "doc.md").write_text(
            "---\nbibliography: refs.bib\ncsl: style.csl\n---\n\nCite @k.\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-e", "typst", "--no-stamp")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_default_template_applies_pitch_before_the_title(self):
        (self.directory / "doc.md").write_text(
            "---\nfontsize: 12pt\nlinestretch: 2\ntitle: Titlefirst\n---\n\nBodyfirst.\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "--to", "typst", "--standalone", "-o", "doc.typ")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (self.directory / "doc.typ").read_text(encoding="utf-8")
        self.assertLess(text.index("leading: 1.7076em"), text.index("title: [Titlefirst]"))

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_long_headings_do_not_spill_into_the_following_paragraph(self):
        (self.directory / "doc.md").write_text(
            "---\nfontsize: 12pt\n---\n\n# Headingfirst " + "heading " * 20 +
            "\n\nBodyfirst bodyword.\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-e", "typst", "--no-stamp")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Bodyfirst", [first for _, first in self.line_tops()])

    def test_a_link_to_a_missing_anchor_does_not_stop_the_pdf(self):
        (self.directory / "doc.md").write_text(DOCUMENT, encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "doc.pdf").is_file())
        self.assertIn("links to anchors that are not in the document", done.stdout + done.stderr)

    def test_a_picture_is_found_when_pandoc_runs_in_the_metadata_files_folder(self):
        # pdfmd runs Pandoc in the first metadata file's folder; a Pandoc before 3.2 did not find the picture there
        (self.directory / "pictures").mkdir()
        (self.directory / "pictures" / "dot.png").write_bytes(tiny_png())
        (self.directory / "shared").mkdir()
        (self.directory / "shared" / "meta.yaml").write_text("lang: en\n", encoding="utf-8")
        (self.directory / "doc.md").write_text("# A\n\n![A dot](pictures/dot.png)\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-y", "shared/meta.yaml", "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "doc.pdf").is_file())
        typ = self.run_pdfmd("doc.md", "-y", "shared/meta.yaml", "-t", "typst", "-o", "doc.typ")
        self.assertEqual(typ.returncode, 0, typ.stdout + typ.stderr)
        self.assertIn('image("pictures/dot.png"', (self.directory / "doc.typ").read_text(encoding="utf-8"))

    def test_uncited_csl_in_pandocs_data_directory_builds_like_the_cited_document(self):
        metadata = self.directory / "doc" / "metadata"
        metadata.mkdir(parents=True)
        (metadata / "r.bib").write_text('@book{k, author={A, B}, title={T}, year={2000}, publisher={P}}\n',
                                        encoding="utf-8")
        (metadata / "metadata.yaml").write_text(
            "csl: apa6.csl\nbibliography: r.bib\npdfmd-options:\n  engine: typst\n", encoding="utf-8")
        env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
               "XDG_CONFIG_HOME": str(self.directory / "config"), "XDG_CACHE_HOME": str(self.directory / "cache"),
               "XDG_DATA_HOME": str(self.directory / "data"), "APPDATA": str(self.directory / "config")}
        # Ask Pandoc for its directory under this environment; no access to the real user data folder.
        version = subprocess.run([PANDOC, "--version"], env=env, capture_output=True, text=True, check=True)
        data = Path(next(line.partition(":")[2].strip() for line in version.stdout.splitlines()
                         if line.startswith("User data directory:")))
        style = data / "csl" / "apa6.csl"
        style.parent.mkdir(parents=True)
        default = subprocess.run([PANDOC, "--print-default-data-file", "default.csl"], env=env,
                                 capture_output=True, text=True, check=True)
        style.write_text(default.stdout, encoding="utf-8")
        for cited in (False, True):
            with self.subTest(cited=cited):
                source = self.directory / "doc" / ("cited.md" if cited else "uncited.md")
                source.write_text("Cite @k.\n" if cited else "No citations here.\n", encoding="utf-8")
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(source), "--verbose"],
                                      cwd=self.directory, env=env, stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertTrue(source.with_suffix(".pdf").is_file())
                self.assertIn("--citeproc", done.stdout + done.stderr)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_reference_entries_do_not_overlap(self):
        """v3.33.59: with a CSL's entry-spacing 0 the entries' lines are the document's line spacing apart (each entry's
        first line was printed on the previous entry's last); with 1 one line more, as LaTeX's \\itemsep does."""
        words = " ".join(["word"] * 40)
        (self.directory / "refs.bib").write_text("".join(f"@book{{k{n}, title={{Entry {n} {words}}}, year={{2000}}}}\n"
                                                         for n in range(3)), encoding="utf-8")
        for spacing, apart in (("0", 1), ("1", 2), ("2.5", 3.5), ("0.5", 1.5)):
            with self.subTest(entry_spacing=spacing):
                (self.directory / "style.csl").write_text(
                    '<?xml version="1.0" encoding="utf-8"?>\n<style xmlns="http://purl.org/net/xbiblio/csl" '
                    'class="in-text" version="1.0"><info><title>T</title><id>t</id><updated>2026-01-01T00:00:00+00:00'
                    '</updated></info><citation><layout><text variable="title"/></layout></citation>'
                    f'<bibliography entry-spacing="{spacing}"><sort><key variable="title"/></sort><layout>'
                    '<text variable="title"/></layout></bibliography></style>\n', encoding="utf-8")
                (self.directory / "doc.md").write_text("---\nbibliography: refs.bib\ncsl: style.csl\nlinestretch: 2\n"
                                                       "nocite: '@*'\n---\n", encoding="utf-8")
                done = self.run_pdfmd("doc.md", "-e", "typst")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                layout = subprocess.run(["pdftotext", "-bbox-layout", str(self.directory / "doc.pdf"), "-"],
                                        capture_output=True, text=True, encoding="utf-8").stdout
                lines = [(float(top), first) for top, first in re.findall(
                    r'<line xMin="[^"]+" yMin="([^"]+)".*?<word[^>]*>([^<]*)', layout, re.S) if first != "1"]  # no page number
                tops = [top for top, _ in lines]
                firsts = [index for index, (_, first) in enumerate(lines) if first == "Entry"]
                pitches = [round(after - before, 1) for before, after in zip(tops, tops[1:])]
                self.assertEqual(len(firsts), 3)
                self.assertGreater(len(tops), 6)                                # the entries wrap
                line = min(pitches)
                for index, pitch in enumerate(pitches, 1):
                    self.assertAlmostEqual(pitch, line * (apart if index in firsts else 1), delta=0.2, msg=pitches)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_lines_are_latexs_line_pitch_apart(self):
        """v3.33.73: a Typst PDF's lines are LaTeX's linestretch x \\baselineskip apart (a TeX point is 72/72.27 of
        Typst's), in two fonts; a paragraph break adds paragraph-spacing to it; a raw rule later in the text still wins."""
        words = " ".join(["word"] * 120)
        cases = (("fontsize: 12pt\nlinestretch: 2\n", 2 * 14.5), ("fontsize: 10pt\n", 12.0),
                 ("fontsize: 11pt\nlinestretch: 1.5\nmainfont: Times New Roman\n", 1.5 * 13.6))
        for front, pitch in cases:
            with self.subTest(front=front):
                (self.directory / "doc.md").write_text(f"---\n{front}---\n\nFirst {words}\n\nSecond {words}\n",
                                                       encoding="utf-8")
                done = self.run_pdfmd("doc.md", "-e", "typst", "--paragraph-spacing", "6pt")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                tops = self.line_tops()
                second = [first for _, first in tops].index("Second")
                pitches = [round(after - before, 2) for (before, _), (after, _) in zip(tops, tops[1:])]
                for index, apart in enumerate(pitches[:4] + pitches[second:second + 3]):
                    self.assertAlmostEqual(apart, pitch * 72 / 72.27, delta=0.05, msg=pitches)
                self.assertAlmostEqual(pitches[second - 1], pitch * 72 / 72.27 + 6, delta=0.05, msg=pitches)
        (self.directory / "doc.md").write_text(f"---\nfontsize: 12pt\n---\n\nFirst {words}\n\n```{{=typst}}\n"
                                               f"#set par(leading: 2em)\n```\n\nSecond {words}\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        tops = self.line_tops()
        second = [first for _, first in tops].index("Second")
        self.assertAlmostEqual(tops[second + 1][0] - tops[second][0], 12 * 2.7, delta=0.05)    # 2em + the 0.7em box

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_title_and_abstract_pitch_with_either_abstract_label_layout(self):
        (self.directory / "doc.md").write_text(
            "---\ntitle: Titlefirst " + "title " * 20 +
            "\nfontsize: 12pt\nlinestretch: 2\nabstract: Abstractfirst " + "abstractword " * 30 +
            "\n---\n\nBodyfirst " + "bodyword " * 80 + "\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-e", "typst", "--no-stamp")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        layout = subprocess.check_output(["pdftotext", "-bbox-layout", str(self.directory / "doc.pdf"), "-"],
                                         text=True, encoding="utf-8")
        lines = [(float(top), re.findall(r"<word[^>]*>([^<]*)", content)) for top, content in re.findall(
            r'<line xMin="[^"]+" yMin="([^"]+)"[^>]*>(.*?)</line>', layout, re.S)]
        for word, ratio in (("Titlefirst", 1.5), ("Abstractfirst", 1), ("Bodyfirst", 1)):
            with self.subTest(region=word):
                index = next(i for i, (_, words) in enumerate(lines) if word in words)
                self.assertAlmostEqual((lines[index + 1][0] - lines[index][0]) / ratio,
                                       2 * 14.5 * 72 / 72.27, delta=0.05)

    @unittest.skipUnless(shutil.which("pdftotext") and shutil.which("lualatex"), "needs pdftotext and LuaLaTeX")
    def test_title_abstract_and_toc_use_the_body_pitch(self):
        source = self.directory / "doc.md"
        source.write_text("---\ntitle: Titlefirst " + "title " * 12 +
                          "\nfontsize: 12pt\nlinestretch: 2\nmainfont: STIX Two Text\nabstract: Abstractfirst " +
                          "abstractword " * 20 + "\n---\n\n# Headingfirst " + "heading " * 10 +
                          "\n\nBodyfirst " + "bodyword " * 80 + "\n\n# Headingsecond\n\nLast.\n", encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                       "XDG_CONFIG_HOME": str(self.directory / "config"),
                       "XDG_CACHE_HOME": str(self.directory / "cache"), "XDG_DATA_HOME": str(self.directory / "data")}
        lines = {}
        for engine in ("lualatex", "typst"):
            output = self.directory / (engine + ".pdf")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(source), "-e", engine,
                                   "--toc", "--no-stamp", "--no-backup", "-o", str(output)],
                                  env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            layout = subprocess.check_output(["pdftotext", "-bbox-layout", str(output), "-"], text=True)
            lines[engine] = [(float(top), " ".join(re.findall(r"<word[^>]*>([^<]*)", content)))
                             for top, content in re.findall(
                                 r'<line xMin="[^"]+" yMin="([^"]+)"[^>]*>(.*?)</line>', layout, re.S)]

        def pitch(engine, word):
            found = lines[engine]
            index = next(i for i, (_, text) in enumerate(found) if word in text.split())
            return found[index + 1][0] - found[index][0]

        body = pitch("lualatex", "Bodyfirst")
        self.assertAlmostEqual(pitch("typst", "Bodyfirst"), body, delta=0.05)
        for word, size_ratio in (("Titlefirst", 1.5), ("Abstractfirst", 1), ("Headingfirst", 1)):
            with self.subTest(region=word):
                self.assertAlmostEqual(pitch("typst", word) / size_ratio, body, delta=0.05)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_custom_template_spacing_wins_property_by_property(self):
        (self.directory / "doc.md").write_text(
            "---\nfontsize: 12pt\nlinestretch: 2\n---\n\nFirst  \nline\n\nSecond  \nline\n", encoding="utf-8")
        folder = self.directory / "custom templates"
        folder.mkdir()
        template = folder / "own.typ"
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                       "XDG_CONFIG_HOME": str(self.directory / "config"),
                       "XDG_CACHE_HOME": str(self.directory / "cache"), "XDG_DATA_HOME": str(self.directory / "data")}
        default_leading = (2 * 14.5 * 72 / 72.27) - 0.7 * 12
        cases = (("", default_leading + 8.4, default_leading + 15),
                 ("#set par(leading: 2em)", 32.4, default_leading + 15),
                 ("#set par(leading: 1.3em)", 24, default_leading + 15),
                 ("#set par(spacing: 30pt)", default_leading + 8.4, 38.4),
                 ("#set text(top-edge: 1em)", default_leading + 12, default_leading + 18.6),
                 ("#set text(bottom-edge: -0.2em)", default_leading + 10.8, default_leading + 17.4),
                 ("#show: body => { set par(leading: 2em, spacing: 30pt); body }", 32.4, 38.4))
        for rules, pitch, gap in cases:
            with self.subTest(rules=rules):
                template.write_text('#set text(size: 12pt)\n' + rules + '\n$body$\n', encoding="utf-8")
                self.check_template_pitch(environment, ["--template", str(template)], pitch, gap)
        (folder / "nested").mkdir()
        (folder / "nested" / "piece.typ").write_text('#set par(spacing: 30pt)\n\n', encoding="utf-8")
        template.write_text('#set text(size: 12pt)\n#set par(leading: 2em)\n$nested/piece.typ()$\n$body$\n', encoding="utf-8")
        self.check_template_pitch(environment, ["--template=" + str(template)], 32.4, 38.4)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_defaults_relative_template_and_parent_paths(self):
        version = subprocess.check_output([PANDOC, "--version"], text=True).splitlines()[0]
        (self.directory / "doc.md").write_text(
            "---\nfontsize: 12pt\nlinestretch: 2\n---\n\nFirst  \nline\n\nSecond  \nline\n", encoding="utf-8")
        folder = self.directory / "custom templates"
        folder.mkdir()
        template = folder / "own.typ"
        template.write_text('#set text(size: 12pt)\n#set par(leading: 2em, spacing: 30pt)\n$body$\n', encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                       "XDG_CONFIG_HOME": str(self.directory / "config"),
                       "XDG_CACHE_HOME": str(self.directory / "cache"), "XDG_DATA_HOME": str(self.directory / "data")}
        defaults = folder / "defaults.yaml"
        defaults.write_text('template: "${.}/own.typ"\n', encoding="utf-8")
        self.check_template_pitch(environment, ["--defaults", str(defaults)], 32.4, 38.4)
        if version == "pandoc 3.1.3":
            self.skipTest("Pandoc 3.1.3 does not expand ${.} in parent-default paths; template path checked above")
        defaults_folder = Path(environment["XDG_DATA_HOME"]) / "pandoc" / "defaults"
        defaults_folder.mkdir(parents=True)
        (defaults_folder / "base.yaml").write_text("template: " + str(template) + "\n", encoding="utf-8")
        (defaults_folder / "house.yaml").write_text('defaults: ["${.}/base.yaml"]\n', encoding="utf-8")
        self.check_template_pitch(environment, ["--defaults", "house"], 32.4, 38.4)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_default_template_body_still_resets_header_edges(self):
        (self.directory / "doc.md").write_text(
            '---\nfontsize: 12pt\nlinestretch: 2\nheader-includes: |\n'
            '  ```{=typst}\n  #set text(top-edge: 1em)\n  ```\n---\n\nFirst  \nline\n\nSecond  \nline\n', encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                       "XDG_CONFIG_HOME": str(self.directory / "config"),
                       "XDG_CACHE_HOME": str(self.directory / "cache"), "XDG_DATA_HOME": str(self.directory / "data")}
        pitch = 2 * 14.5 * 72 / 72.27
        self.check_template_pitch(environment, [], pitch, pitch + 0.55 * 12)

    def check_template_pitch(self, environment, options, pitch, gap):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "doc.md", "-e", "typst",
                               "--no-stamp", "--no-backup", *options], cwd=self.directory, env=environment,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        tops = self.line_tops()
        self.assertAlmostEqual(tops[1][0] - tops[0][0], pitch, delta=0.05, msg=tops)
        self.assertAlmostEqual(tops[2][0] - tops[1][0], gap, delta=0.05, msg=tops)

    def line_tops(self) -> list[tuple[float, str]]:
        layout = subprocess.run(["pdftotext", "-bbox-layout", str(self.directory / "doc.pdf"), "-"],
                                capture_output=True, text=True, encoding="utf-8").stdout
        page = layout.split("</page>")[0]
        return [(float(top), first) for top, first in re.findall(
            r'<line xMin="[^"]+" yMin="([^"]+)".*?<word[^>]*>([^<]*)', page, re.S)]

    def test_typst_line_spacing_defaults_are_byte_identical_and_pandoc_opts_out(self):
        source = self.directory / "doc.md"
        front = "fontsize: 12pt\nmainfont: Libertinus Serif\nlinestretch: 2\n"
        source.write_text("---\n" + front + "---\n\nFirst.\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "--to", "typst", "--standalone", "--no-stamp", "-o", "doc.typ")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        default = (self.directory / "doc.typ").read_bytes()
        for mode in ("latex", " LATEX "):
            source.write_text("---\n" + front + 'pdfmd-options: {typst-line-spacing: "' + mode + '"}\n---\n\nFirst.\n', encoding="utf-8")
            done = self.run_pdfmd("doc.md", "--to", "typst", "--standalone", "--no-stamp", "-o", "doc.typ")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual((self.directory / "doc.typ").read_bytes(), default)
        source.write_text("---\n" + front + "pdfmd-options: {typst-line-spacing: pandoc}\n---\n\nFirst.\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "--to", "typst", "--standalone", "--no-stamp", "-o", "doc.typ")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (self.directory / "doc.typ").read_text(encoding="utf-8")
        self.assertNotIn('#set text(top-edge: 0.7em, bottom-edge: "baseline")', text)
        self.assertNotIn("#set par(leading:", text)
        plain = subprocess.run([PANDOC, str(source), "-t", "typst", "--standalone"],
                               cwd=self.directory, env={**os.environ}, capture_output=True, text=True)
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(text, plain.stdout)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_pandoc_line_spacing_matches_pandocs_measured_pdf(self):
        source = self.directory / "doc.md"
        source.write_text("---\nfontsize: 12pt\nmainfont: Libertinus Serif\nlinestretch: 2\n"
                          "pdfmd-options: {typst-line-spacing: pandoc}\n---\n\nFirst  \nline\n\nSecond  \nline\n", encoding="utf-8")
        done = subprocess.run([PANDOC, "doc.md", "--pdf-engine=typst", "--pdf-engine-opt=--root=/", "-o", "doc.pdf"],
                              cwd=self.directory, env={**os.environ}, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        baseline = self.line_tops()
        done = self.run_pdfmd("doc.md", "-e", "typst", "--no-stamp", "--no-backup")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        built = self.line_tops()
        self.assertGreaterEqual(len(baseline), 4, baseline)
        self.assertGreaterEqual(len(built), 4, built)
        for index in range(3):
            expected = baseline[index + 1][0] - baseline[index][0]
            actual = built[index + 1][0] - built[index][0]
            self.assertAlmostEqual(actual, expected, delta=0.05, msg=(baseline, built))
        self.assertGreater(abs((built[1][0] - built[0][0]) - 2 * 14.5 * 72 / 72.27), 1)

    def test_the_filter_is_given_only_to_typst(self):
        self.assertEqual(pdfmd.typst_filter_args("latex"), [])
        self.assertEqual(pdfmd.typst_filter_args("typst")[-1], str(TYPST_LUA))


class WeasyPrintArguments(unittest.TestCase):
    def test_plain_math_and_the_filter_only_for_weasyprint(self):
        self.assertEqual(pdfmd.weasyprint_math_args("typst", []), [])
        arguments = pdfmd.weasyprint_math_args("weasyprint", [])
        self.assertEqual(arguments[-1], str(ROOT / "lib" / "pdfmd_lua" / "weasyprint.lua"))
        if pdfmd.pandoc_has_option("--math-method"):
            self.assertIn("--math-method=plain", arguments)

    def test_the_command_lines_math_wins(self):
        arguments = pdfmd.weasyprint_math_args("weasyprint", ["--mathml"])
        self.assertFalse([item for item in arguments if item.startswith("--math")])
        self.assertIn("--lua-filter", arguments)
        self.assertFalse([item for item in arguments if item.startswith("pdfmd-katex")])

    def test_katex_and_node_are_named_to_the_filter(self):
        folder = Path(tempfile.mkdtemp(prefix="pdfmd-katex-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        with mock.patch.object(pdfmd, "katex_runtime", return_value=("/opt/node/bin/node", folder)):
            arguments = pdfmd.weasyprint_math_args("weasyprint", [])
            chosen = pdfmd.weasyprint_math_args("weasyprint", ["--math-method=mathml"])
        self.assertIn(f"pdfmd-katex={folder}", arguments)
        self.assertIn(f"pdfmd-katex-url={folder.as_uri()}", arguments)
        self.assertIn("pdfmd-katex-node=/opt/node/bin/node", arguments)
        self.assertEqual(arguments[-2:], ["--lua-filter", str(WEASYPRINT_LUA)])
        if pdfmd.pandoc_has_option("--math-method"):
            self.assertIn("--math-method=plain", arguments)         # what KaTeX does not reach stays text
        self.assertFalse([item for item in chosen if item.startswith("pdfmd-katex")])


class KatexInstall(unittest.TestCase):
    """The pieces of `pdfmd --install math:katex` that need no network."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-katex-install-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def package(self, names: list[str]) -> Path:
        archive = self.directory / "katex.tgz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name in names:
                data = name.encode()
                member = tarfile.TarInfo(name)
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
        return archive

    def test_only_the_script_stylesheet_fonts_mhchem_and_licence_are_kept(self):
        archive = self.package(["package/LICENSE", "package/README.md", "package/package.json",
                                "package/dist/katex.min.js", "package/dist/katex.js", "package/dist/katex.min.css",
                                "package/dist/katex.mjs", "package/dist/fonts/KaTeX_Main-Regular.woff2",
                                "package/dist/fonts/KaTeX_Main-Regular.ttf", "package/dist/contrib/mhchem.min.js",
                                "package/dist/contrib/copy-tex.min.js", "package/src/katex.ts", "../escape.js"])
        target = self.directory / "data" / "katex" / "0.18.9"
        target.mkdir(parents=True)
        (target / "old.js").write_text("left from before", encoding="utf-8")
        pdfmd.unpack_katex(archive, target)
        kept = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
        self.assertEqual(kept, ["LICENSE", "contrib/mhchem.min.js", "fonts/KaTeX_Main-Regular.ttf",
                                "fonts/KaTeX_Main-Regular.woff2", "katex.min.css", "katex.min.js"])
        self.assertFalse((self.directory / "escape.js").exists())
        self.assertFalse(target.with_name("0.18.9.part").exists())

    def test_a_package_without_fonts_is_refused(self):
        archive = self.package(["package/dist/katex.min.js", "package/dist/katex.min.css"])
        target = self.directory / "katex" / "0.18.9"
        with self.assertRaises(OSError):
            pdfmd.unpack_katex(archive, target)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name("0.18.9.part").exists())

    def test_the_pinned_release_else_the_newest_installed(self):
        root = self.directory / "pdfmd" / "katex"
        for version in ("0.9.0", "0.16.11", "0.10.2"):
            (root / version).mkdir(parents=True)
            for name in ("katex.min.js", "katex.min.css"):
                (root / version / name).write_text("", encoding="utf-8")
        (root / "1.0.0").mkdir()                                    # incomplete: not a candidate
        with mock.patch.object(pdfmd, "data_root", return_value=self.directory / "pdfmd"):
            self.assertEqual(pdfmd.katex_folder(), root / "0.16.11")
            (root / pdfmd.KATEX_VERSION).mkdir()
            for name in ("katex.min.js", "katex.min.css"):
                (root / pdfmd.KATEX_VERSION / name).write_text("", encoding="utf-8")
            self.assertEqual(pdfmd.katex_folder(), root / pdfmd.KATEX_VERSION)
            with mock.patch.object(pdfmd, "which", return_value=None):
                self.assertIsNone(pdfmd.katex_runtime())             # KaTeX without node: no typesetting
        with mock.patch.object(pdfmd, "data_root", return_value=self.directory / "nothing"):
            self.assertIsNone(pdfmd.katex_folder())

    def test_nodes_release_names(self):
        self.assertEqual(pdfmd.node_asset_name("v24.21.0", "Darwin", "arm64"), "node-v24.21.0-darwin-arm64.tar.xz")
        self.assertEqual(pdfmd.node_asset_name("v24.21.0", "Linux", "x86_64"), "node-v24.21.0-linux-x64.tar.xz")
        self.assertEqual(pdfmd.node_asset_name("v24.21.0", "Windows", "AMD64"), "node-v24.21.0-win-x64.zip")
        self.assertIsNone(pdfmd.node_asset_name("v24.21.0", "FreeBSD", "x86_64"))

    def test_node_is_taken_from_its_bin_folder(self):
        archive = self.directory / "node.tar.xz"
        with tarfile.open(archive, "w:xz") as bundle:
            for name, data in (("node-v1/lib/node_modules/x/node", b"not this"), ("node-v1/bin/node", b"this")):
                member = tarfile.TarInfo(name)
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
        target = pdfmd.extract_executable(archive, "node", self.directory / "bin", inside="bin")
        self.assertEqual(target.read_bytes(), b"this")

    def test_the_kind_is_math_katex(self):
        self.assertEqual(pdfmd.install_kind("math:katex"), "math:katex")
        self.assertEqual(pdfmd.install_kind("math"), "math")
        with self.assertRaises(Exception):
            pdfmd.install_kind("math:mathjaxx")                         # math:mathjax is MathJax (tests/test_mathjax.py)

    def test_weasyprints_css_complaints_are_dropped(self):
        said = ("WARNING: Ignored `text-rendering: optimizeLegibility` at 22:7, unknown property.\n"
                "WARNING: Expected a media type, got '(max-width: 600px)'\n"
                "WARNING: Invalid media type ' (max-width: 600px) ' the whole @media rule was ignored at 25:5.\n"
                "WARNING: Ignored `width:min-content` at 1:5629, invalid value.\n"
                "WARNING: Failed to load image at 'file:///x.png': No such file\n"
                "WARN  weasyprint: KaTeX could not typeset 1 of 2 formulas\n")
        self.assertEqual(pdfmd.WEASYPRINT_CSS_NOISE.sub("", said),
                         "WARNING: Failed to load image at 'file:///x.png': No such file\n"
                         "WARN  weasyprint: KaTeX could not typeset 1 of 2 formulas\n")


@unittest.skipUnless(PANDOC and WEASYPRINT, "needs Pandoc and WeasyPrint")
class WeasyPrintMath(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-weasy-math-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, text: str) -> subprocess.CompletedProcess:
        (self.directory / "doc.md").write_text(text, encoding="utf-8")
        nothing = str(self.directory / "no-data")                   # no KaTeX installed: math as text
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "weasyprint"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1", "XDG_DATA_HOME": nothing, "LOCALAPPDATA": nothing})

    def test_math_is_text_once_and_said_once(self):
        done = self.build("---\ntitle: M\n---\n\nSee $\\alpha_i \\le \\beta$ and $x^2 + \\frac{a}{b}$.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertEqual(said.count("WeasyPrint does not typeset math"), 1)
        self.assertIn("2 formulas are printed as text", said)
        self.assertIn("pdfmd --install math:katex", said)
        self.assertNotIn("WARNING: Ignored", said)                  # WeasyPrint's CSS complaints (v3.28.11)
        if shutil.which("pdftotext"):
            text = subprocess.run(["pdftotext", str(self.directory / "doc.pdf"), "-"], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace").stdout
            self.assertIn("α", text)
            self.assertNotIn("x2+ab", text)                    # MathML's flat text, before the TeX, is gone

    def test_no_math_no_warning(self):
        done = self.build("---\ntitle: M\n---\n\nJust words.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("typeset math", done.stdout + done.stderr)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_a_narrow_tables_caption_breaks_between_words(self):
        # v3.28.3: "Ta / ble / 1: / A / rat / her" at the width of a one-column table
        done = self.build("---\ntitle: M\n---\n\n| a |\n|---|\n| 1 |\n\n: A rather long caption for a narrow table\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = subprocess.run(["pdftotext", str(self.directory / "doc.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertIn("A rather long caption for a narrow table", " ".join(text.split()))



@unittest.skipUnless(PANDOC and WEASYPRINT and KATEX, "needs Pandoc, WeasyPrint, node and `pdfmd --install math:katex`")
class WeasyPrintKatex(unittest.TestCase):
    """v3.28.11: with KaTeX installed, a WeasyPrint PDF's math is typeset in KaTeX's fonts."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-weasy-katex-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, text: str, *extra: str) -> subprocess.CompletedProcess:
        (self.directory / "doc.md").write_text(text, encoding="utf-8")
        # --no-auto mathjax: with MathJax installed too it would typeset first (tests/test_mathjax.py); these are KaTeX's
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "weasyprint", "--no-auto", "mathjax",
                               *extra], capture_output=True, text=True, encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    def fonts(self) -> str:
        return subprocess.run(["pdffonts", str(self.directory / "doc.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

    def text(self) -> str:
        return subprocess.run(["pdftotext", str(self.directory / "doc.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

    @unittest.skipUnless(shutil.which("pdffonts") and shutil.which("pdftotext"), "needs Poppler")
    def test_math_is_typeset_without_a_word_said(self):
        done = self.build("---\ntitle: K\n---\n\nSee $\\frac{a}{b} \\neq \\vec{v}$ and\n\n"
                          "$$\\sum_{n=1}^{\\infty} \\frac{1}{n^2} = \\frac{\\pi^2}{6}$$\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertNotIn("typeset math", said)
        self.assertNotIn("KaTeX could not", said)
        self.assertNotIn("WARNING: Ignored", said)
        self.assertIn("KaTeX_Main", self.fonts())
        self.assertIn("KaTeX_Size", self.fonts())                  # the big sum sign
        self.assertNotIn("\\frac", self.text())

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_a_formula_katex_cannot_read_is_text_and_said_once(self):
        done = self.build("---\ntitle: K\n---\n\nGood $x^2$, bad $\\nosuchmacro{y}$.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertEqual(said.count("KaTeX could not typeset 1 of 2 formulas"), 1, said)
        self.assertIn("\\nosuchmacro", said)
        self.assertIn("\\nosuchmacro{y}", self.text())

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_chemistry_in_math_is_converted_first(self):
        done = self.build("---\ntitle: K\n---\n\nWater $\\ce{2H2 + O2 -> 2H2O}$.\n", "-v")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("\\ce", self.text())
        self.assertNotIn("KaTeX could not", done.stdout + done.stderr)
        # KaTeX's own mhchem would hide the order: the command line shows it, the LaTeX filter first
        command = next(line for line in (done.stdout + done.stderr).splitlines()
                       if line.startswith("CMD") and "weasyprint.lua" in line)
        self.assertLess(command.index("office.lua"), command.index("weasyprint.lua"))

    @unittest.skipUnless(shutil.which("pdfinfo") and shutil.which("pdffonts"), "needs Poppler")
    def test_a_formula_in_the_title_stays_in_the_pdfs_title(self):
        # typeset, it is raw HTML, which the page's <title> (the PDF's Title) leaves out: "Energy  here"
        done = self.build("---\ntitle: Energy $E = mc^2$ here\n---\n\nWords.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        info = subprocess.run(["pdfinfo", str(self.directory / "doc.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertIn("Energy E = mc^2 here", info)
        self.assertIn("KaTeX_Main", self.fonts())                  # on the page, typeset


class TypstHeadingWrap(unittest.TestCase):
    """`--wrap=none` only for a Pandoc whose Typst writer wraps a long heading (3.1.3), asked once per version (v3.33.316)."""

    def answers(self, output: str, version: tuple[int, ...]):
        from pdfmd_lua import typst
        calls = []

        def probe(command, **options):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, output, "")
        return typst, calls, (mock.patch.object(pdfmd, "run_probe", probe),
                              mock.patch.object(pdfmd, "pandoc_version", lambda: version),
                              mock.patch.dict(typst._HEADING_WRAP, clear=True))

    def test_a_wrapping_writer_gets_wrap_none_once(self):
        typst, calls, patches = self.answers("= word word word\nword word\n<word-word>\n", (3, 1, 3))
        with patches[0], patches[1], patches[2]:
            self.assertEqual(typst.heading_args(), ["--wrap=none"])
            self.assertEqual(typst.heading_args(), ["--wrap=none"])
        self.assertEqual(len(calls), 1)

    def test_a_writer_keeping_headings_on_one_line_gets_nothing(self):
        typst, calls, patches = self.answers("= word word word word\n<word-word-word-word>\n", (3, 13))
        with patches[0], patches[1], patches[2]:
            self.assertEqual(typst.heading_args(), [])

    def test_no_answer_gets_nothing(self):
        typst, calls, patches = self.answers("", (0,))
        with patches[0], patches[1], patches[2]:
            self.assertEqual(typst.heading_args(), [])


@unittest.skipUnless(PANDOC, "needs Pandoc")
class FigureFit(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-figure-")
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)
        width, height = 400, 1600

        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress((b"\0" + b"\x88" * width) * height)) + chunk(b"IEND", b"")
        (self.directory / "tall.png").write_bytes(png)

    def build(self, source, *options):
        (self.directory / "doc.md").write_text(source, encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "doc.md", "--no-stamp",
                               "--no-backup", *options], cwd=self.directory, capture_output=True, encoding="utf-8")

    def test_without_pdfmd_lua_figure_fit_does_nothing_and_warns(self):
        # a copy whose lib/ has no pdfmd_lua: the build, the report route, the TeX runs and --check reach figure fit through
        # figure_fit_module(), which must not raise (CI on 3.34.5: every build of such a copy stopped at the import)
        code = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); sys.modules['pdfmd_lua'] = None\n"
                "import pdfmd\n"
                "from pdfmd_filters.lua import figure_fit_module\n"
                "fit = figure_fit_module()\n"
                "print(fit.arguments('latex', Path('d.md'), []), repr(fit.without_diagnostics('x')),"
                " fit.diagnostics('y', Path('d.md')), fit.REPORT_ENV)\n")
        done = subprocess.run([sys.executable, "-c", code, str(ROOT)], cwd=self.directory, capture_output=True,
                              encoding="utf-8", env={**os.environ, "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "[] 'x' None PDFMD_FIGURE_REPORT")
        self.assertEqual(done.stderr.count("WARN  lua:"), 1, done.stderr)
        shipped = (ROOT / "lib" / "pdfmd_lua" / "figure_fit.py").read_text(encoding="utf-8")
        self.assertIn('REPORT_ENV = "PDFMD_FIGURE_REPORT"', shipped)     # the stand-in names the same variable

    def test_fitted_figure_warns_once_and_off_keeps_native_rendering(self):
        engines = [engine for engine in ("typst", "pdflatex") if shutil.which(engine)]
        if not engines:
            self.skipTest("needs Typst or pdfLaTeX")
        caption = "Tall marker. " + "A folded length across the narrow page. " * 15
        for engine in engines:
            with self.subTest(engine=engine):
                source = "Before.\n\n![" + caption + "](tall.png){#fig-tall width=100%}\n\nAfter.\n"
                done = self.build(source, "-e", engine)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(sum("WARN" in line and "fig-tall" in line and "shrunk" in line
                                     for line in (done.stdout + done.stderr).splitlines()), 1, done.stderr)
                done = self.build(source.replace("width=100%", "width=100% fit=off"), "-e", engine)
                self.assertEqual(done.returncode, 0, done.stderr)
                warning = "figure 'fig-tall': image and caption are too tall for the page body"
                self.assertEqual(done.stderr.count(warning), int(engine == "typst"), done.stderr)
                self.assertNotIn("figure 'fig-tall': shrunk", done.stderr)

    @unittest.skipUnless(TYPST, "needs Typst")
    def test_typst_strict_counts_a_figure_with_fitting_switched_off(self):
        caption = "A caption that wraps across the page. " * 65
        source = ("---\npdfmd-options: {figure-fit: off}\n---\n\n"
                  "![Short caption.](tall.png){#fig-short height=10pt}\n\n"
                  f"![{caption}](tall.png){{#fig-tall height=550pt}}\n")
        done = self.build(source, "-e", "typst", "--strict")
        log = done.stdout + done.stderr
        warning = "figure 'fig-tall': image and caption are too tall for the page body"
        self.assertEqual(done.stderr.count(warning), 1, log)
        self.assertNotIn("figure 'fig-short':", log)
        self.assertNotEqual(done.returncode, 0, log)
        self.assertIn("--strict: the build printed", log)

    def test_figure_fit_off_leaves_exports_byte_identical(self):
        for writer, suffix in (("latex", "tex"), ("typst", "typ")):
            with self.subTest(writer=writer):
                source = "Before.\n\n![A short caption.](tall.png){fit=off}\n\nAfter.\n"
                target = self.directory / ("result." + suffix)
                options = ("--standalone", "-t", writer, "-o", str(target))
                done = self.build(source, *options)
                self.assertEqual(done.returncode, 0, done.stderr)
                original = target.read_bytes()
                done = self.build("---\npdfmd-options: {figure-fit: off}\n---\n\n" + source, *options)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(original, target.read_bytes())


if __name__ == "__main__":
    unittest.main()
