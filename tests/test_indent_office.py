"""v3.30.36: the indent div in Word and OpenDocument files (a `pdfmd-indent-<length>` paragraph style per length)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd_office  # noqa: E402
from pdfmd_office import docx_post  # noqa: E402

SOURCE = """---
pdfmd-options:
  office:
    indent: true
---

Before one.

Before two.

::: {indent=false}
Flush *one* with [a link](http://x.org).

Flush two.

- a bullet
:::

::: {indent=2em}
Two em.
:::

After.
"""
SOFFICE = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")


def run(directory: str, *arguments: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": directory}
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], cwd=directory, env=environment,
                          capture_output=True, text=True)


class Styles(unittest.TestCase):
    def test_a_length_in_the_name_is_read_back_in_twips(self):
        self.assertEqual(docx_post.indent_twips("0pt"), 0)
        self.assertEqual(docx_post.indent_twips("2em"), 480)
        self.assertEqual(docx_post.indent_twips("1p5em"), 360)
        self.assertEqual(docx_post.indent_twips("12pt"), 240)
        self.assertIsNone(docx_post.indent_twips("banana"))

    def test_word_styles_get_the_indent_and_others_are_left_alone(self):
        styles = ('<w:styles><w:style w:type="paragraph" w:customStyle="1" w:styleId="pdfmd-indent-0pt"><w:name w:val="pdfmd-indent-0pt"/>'
                  '<w:basedOn w:val="BodyText"/></w:style><w:style w:styleId="BodyText"><w:name w:val="Body Text"/></w:style></w:styles>')
        done, count = docx_post.style_indents(styles)
        self.assertEqual(count, 1)
        self.assertRegex(done, r'pdfmd-indent-0pt".*?<w:ind w:firstLine="0"/>.*?</w:style><w:style w:styleId="BodyText"><w:name w:val="Body Text"/></w:style>')

    def test_an_odt_gets_its_styles_defined_and_a_file_without_them_is_not_touched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.odt"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("content.xml", '<office:text><text:p text:style-name="pdfmd-indent-2em">x</text:p></office:text>')
                archive.writestr("styles.xml", "<office:styles></office:styles>")
            self.assertEqual(pdfmd_office.finish_odt(path), 1)
            styles = zipfile.ZipFile(path).read("styles.xml").decode()
            self.assertIn('style:name="pdfmd-indent-2em"', styles)
            self.assertIn('fo:text-indent="0.3333in"', styles)
            self.assertEqual(pdfmd_office.finish_odt(path), 0)               # already defined
            plain = Path(directory) / "b.odt"
            with zipfile.ZipFile(plain, "w") as archive:
                archive.writestr("content.xml", "<office:text/>")
                archive.writestr("styles.xml", "<office:styles></office:styles>")
            before = plain.read_bytes()
            self.assertEqual(pdfmd_office.finish_odt(plain), 0)
            self.assertEqual(plain.read_bytes(), before)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Built(unittest.TestCase):
    def build(self, target: str) -> tuple[Path, tempfile.TemporaryDirectory]:
        folder = tempfile.TemporaryDirectory()
        (Path(folder.name) / "t.md").write_text(SOURCE, encoding="utf-8")
        done = run(folder.name, "t.md", "--to", target)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("NOTE  indent", done.stdout + done.stderr)
        return Path(folder.name) / f"t.{target}", folder

    def test_docx_paragraphs_in_the_div_have_the_style_and_lists_and_the_rest_keep_theirs(self):
        path, folder = self.build("docx")
        with folder:
            archive = zipfile.ZipFile(path)
            document, styles = archive.read("word/document.xml").decode(), archive.read("word/styles.xml").decode()
            used = [(re.findall(r'pStyle w:val="([^"]+)"', p), "".join(re.findall(r"<w:t[^>]*>([^<]*)", p)))
                    for p in re.findall(r"<w:p>.*?</w:p>", document, re.S)]
            by_text = {text: style for style, text in used}
            self.assertEqual(by_text["Flush two."], ["pdfmd-indent-0pt"])
            self.assertEqual(by_text["Two em."], ["pdfmd-indent-2em"])
            self.assertEqual(by_text["a bullet"], ["Compact"])              # a list item keeps its own style
            self.assertEqual(by_text["After."], ["BodyText"])
            self.assertRegex(styles, r'styleId="pdfmd-indent-0pt".*?<w:ind w:firstLine="0"/>')
            self.assertRegex(styles, r'styleId="pdfmd-indent-2em".*?<w:ind w:firstLine="480"/>')

    def test_odt_defines_the_styles_its_text_names(self):
        path, folder = self.build("odt")
        with folder:
            archive = zipfile.ZipFile(path)
            names = set(re.findall(r'text:style-name="(pdfmd-indent-[^"]+)"', archive.read("content.xml").decode()))
            styles = archive.read("styles.xml").decode()
            self.assertEqual(names, {"pdfmd-indent-0pt", "pdfmd-indent-2em"})
            for name in names:
                self.assertIn(f'style:name="{name}"', styles)

    @unittest.skipUnless(SOFFICE.is_file() or shutil.which("soffice"), "needs LibreOffice")
    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_libreoffice_draws_the_first_line_flush_and_indented(self):
        for target in ("docx", "odt"):
            with self.subTest(target=target):
                path, folder = self.build(target)
                with folder:
                    out = Path(folder.name) / "lo"
                    done = subprocess.run([str(SOFFICE) if SOFFICE.is_file() else "soffice", "--headless", "--convert-to", "pdf",
                                           "--outdir", str(out), str(path)], capture_output=True, text=True,
                                          env={**os.environ, "HOME": folder.name})
                    pdf = out / "t.pdf"
                    self.assertTrue(pdf.is_file(), done.stdout + done.stderr)
                    boxes = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"], capture_output=True, text=True).stdout
                    x = {word: float(re.search(r'<word xMin="([\d.]+)"[^>]*>%s\b' % word, boxes).group(1))
                         for word in ("Flush", "Two", "After")}
                    self.assertAlmostEqual(x["Flush"], 72.0, delta=1)             # the page margin: no indent
                    self.assertAlmostEqual(x["Two"], 96.0, delta=1)               # 2em = 24 pt
                    self.assertGreater(x["After"], 80)                            # the document's own indent is back


if __name__ == "__main__":
    unittest.main()
