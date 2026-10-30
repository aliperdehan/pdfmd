"""v3.29.28: universal markup in Word. Centred text, highlighted text and landscape pages are written into the .docx: Pandoc makes a
`custom-style` without any formatting and a raw section break as it was written, and pdfmd_office finishes both."""

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
sys.path.insert(0, str(ROOT / "tests"))
from cache_support import cache_env  # noqa: E402

import pdfmd  # noqa: E402
from pdfmd_office import docx_post  # noqa: E402

PANDOC = shutil.which("pandoc")
SOFFICE = pdfmd.resolve_soffice()

PORTRAIT = '<w:p><w:pPr><w:sectPr w:rsidR="00D0F001" /></w:pPr></w:p>'
LANDSCAPE = '<w:p><w:pPr><w:sectPr w:rsidR="00D0F002" /></w:pPr></w:p>'
FINAL = ('<w:sectPr><w:footerReference w:type="default" r:id="rId9"/><w:pgSz w:w="11906" w:h="16838"/>'
         '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
         '<w:titlePg/></w:sectPr>')


def page(*parts: str) -> str:
    return "<w:document><w:body>" + "".join(parts) + FINAL + "</w:body></w:document>"


def sections(document: str) -> list[str]:
    return re.findall(r"<w:sectPr\b.*?</w:sectPr>", document, re.S)


def landscape_sections(document: str) -> list[bool]:
    result = []
    for text in sections(document):
        size = re.search(r"<w:pgSz\b[^>]*>", text).group(0)
        result.append(int(re.search(r'w:w="(\d+)"', size).group(1)) > int(re.search(r'w:h="(\d+)"', size).group(1)))
    return result


class Sections(unittest.TestCase):
    def test_a_block_in_the_middle_is_a_portrait_break_then_a_landscape_one(self):
        document, changed = docx_post.sections_markup(page("<w:p>a</w:p>", PORTRAIT, "<w:p>b</w:p>", LANDSCAPE, "<w:p>c</w:p>"))
        self.assertTrue(changed)
        self.assertEqual(landscape_sections(document), [False, True, False])
        first, second, last = sections(document)
        for text in (first, second, last):
            self.assertIn('<w:footerReference w:type="default" r:id="rId9"/>', text)       # the document's own footer, in every section
            self.assertIn('w:left="1440"', text)
        self.assertIn("<w:titlePg/>", first)                                                  # the title page stays the first page's
        self.assertNotIn("<w:titlePg/>", last)
        self.assertIn('w:w="16838" w:h="11906" w:orient="landscape"', second)                 # A4 turned, from the document's own size

    def test_a_block_at_the_start_makes_no_empty_page(self):
        document, _ = docx_post.sections_markup(page(PORTRAIT, "<w:p>b</w:p>", LANDSCAPE, "<w:p>c</w:p>"))
        self.assertEqual(landscape_sections(document), [True, False])
        self.assertEqual(document.count("<w:p><w:pPr><w:sectPr"), 1)

    def test_a_block_at_the_end_makes_no_empty_page(self):
        document, _ = docx_post.sections_markup(page("<w:p>a</w:p>", PORTRAIT, "<w:p>b</w:p>", LANDSCAPE))
        self.assertEqual(landscape_sections(document), [False, True])                        # the last section is the landscape one

    def test_a_block_that_is_the_whole_document(self):
        document, _ = docx_post.sections_markup(page(PORTRAIT, "<w:p>b</w:p>", LANDSCAPE))
        self.assertEqual(landscape_sections(document), [True])
        self.assertIn("<w:titlePg/>", document)

    def test_two_blocks_in_a_row_share_one_section(self):
        document, _ = docx_post.sections_markup(page("<w:p>a</w:p>", PORTRAIT, "<w:p>b</w:p>", LANDSCAPE, PORTRAIT, "<w:p>c</w:p>",
                                                     LANDSCAPE, "<w:p>d</w:p>"))
        self.assertEqual(landscape_sections(document), [False, True, False])
        self.assertIn("<w:p>b</w:p><w:p>c</w:p>", document)

    def test_a_document_without_markers_is_not_touched(self):
        text = page("<w:p>a</w:p>")
        self.assertEqual(docx_post.sections_markup(text), (text, 0))

    def test_a_page_without_a_size_gets_letter(self):
        text = page(PORTRAIT, "<w:p>b</w:p>", LANDSCAPE, "<w:p>c</w:p>").replace('<w:pgSz w:w="11906" w:h="16838"/>', "")
        document, _ = docx_post.sections_markup(text)
        self.assertEqual(landscape_sections(document), [True, False])
        self.assertIn('w:w="15840" w:h="12240"', document)


class Styles(unittest.TestCase):
    STYLES = ('<w:styles><w:style w:type="paragraph" w:customStyle="1" w:styleId="PdfmdCenter"><w:name w:val="PdfmdCenter" />'
              '<w:basedOn w:val="BodyText" /></w:style><w:style w:type="character" w:customStyle="1" w:styleId="PdfmdHighlight">'
              '<w:name w:val="PdfmdHighlight" /></w:style></w:styles>')

    def test_the_formatting_is_written_into_a_style_that_has_none(self):
        styles, changed = docx_post.style_markup(self.STYLES)
        self.assertEqual(changed, 2)
        self.assertIn('<w:pPr><w:jc w:val="center"/></w:pPr>', styles)
        self.assertIn('w:fill="FFFF00"', styles)

    def test_a_style_the_user_formats_is_left_alone(self):
        own = self.STYLES.replace('<w:basedOn w:val="BodyText" />', '<w:basedOn w:val="BodyText" /><w:pPr><w:jc w:val="right"/></w:pPr>')
        styles, changed = docx_post.style_markup(own)
        self.assertEqual(changed, 1)
        self.assertIn('<w:jc w:val="right"/>', styles)
        self.assertNotIn('<w:jc w:val="center"/>', styles)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Build(unittest.TestCase):
    SOURCE = ("---\ntitle: Word markup\npapersize: a4\n---\n\n# One\n\nPlain text, ==marked words== in it.\n\n::: center\nCentred line.\n:::\n\n"
              "::: landscape\n| a | b |\n|---|---|\n| 1 | 2 |\n:::\n\n# Two\n\nBack in portrait.\n")

    def make(self, folder: str, *extra: str) -> Path:
        root = Path(folder)
        (root / "doc.md").write_text(self.SOURCE, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-o", "doc.docx", "--markup", "center", "highlight",
                               "landscape", *extra], cwd=root, capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                                   **cache_env(root / "cache"), "XDG_CONFIG_HOME": str(root / "config")})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("not applied", done.stdout + done.stderr)
        return root / "doc.docx"

    def test_the_file_carries_the_formatting(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-word-markup-") as folder:
            with zipfile.ZipFile(self.make(folder)) as archive:
                styles = archive.read("word/styles.xml").decode("utf-8")
                document = archive.read("word/document.xml").decode("utf-8")
        self.assertRegex(styles, r'w:styleId="PdfmdCenter".*?<w:jc w:val="center"/>')
        self.assertRegex(styles, r'w:styleId="PdfmdHighlight".*?<w:shd [^>]*w:fill="FFFF00"')
        self.assertEqual(landscape_sections(document), [False, True, False])

    @unittest.skipUnless(SOFFICE, "needs LibreOffice to draw the pages")
    def test_the_pages_are_what_was_asked_when_drawn(self):
        try:
            import pypdf
        except ImportError:
            self.skipTest("needs pypdf")
        with tempfile.TemporaryDirectory(prefix="pdfmd-word-markup-") as folder:
            docx = self.make(folder)
            done = subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", folder, str(docx)],
                                  capture_output=True, text=True, timeout=240)
            pdf = Path(folder) / "doc.pdf"
            self.assertTrue(pdf.is_file(), done.stdout + done.stderr)
            pages = [(float(item.mediabox.width), float(item.mediabox.height)) for item in pypdf.PdfReader(str(pdf)).pages]
        self.assertEqual(len(pages), 3, pages)
        self.assertEqual([width > height for width, height in pages], [False, True, False])
        self.assertAlmostEqual(pages[0][0], 595.3, delta=1)                              # A4, not Letter, in every section


if __name__ == "__main__":
    unittest.main()
