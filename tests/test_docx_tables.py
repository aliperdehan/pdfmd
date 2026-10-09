"""A table in pdfmd's own style is centred in the .docx itself (LibreOffice ignores a style's alignment)."""

from __future__ import annotations

import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from pdfmd_office.docx_post import centre_table, centre_tables, TABLE

NARROW = ('<w:tbl><w:tblPr><w:tblStyle w:val="PdfmdGrid" /><w:tblW w:type="pct" w:w="4167" />'
          '<w:tblLayout w:type="fixed" /></w:tblPr><w:tr/></w:tbl>')


def centred(xml: str) -> str:
    return TABLE.sub(centre_table, xml)


class CentreTables(unittest.TestCase):
    def test_a_pdfmd_table_gets_its_own_alignment_after_its_width(self):
        self.assertIn('<w:tblW w:type="pct" w:w="4167" /><w:jc w:val="center"/><w:tblLayout', centred(NARROW))

    def test_a_table_that_says_where_it_sits_is_left_alone(self):
        left = NARROW.replace("<w:tblLayout", '<w:jc w:val="left"/><w:tblLayout')
        self.assertEqual(centred(left), left)

    def test_another_style_and_the_form_table_are_left_alone(self):
        template = NARROW.replace("PdfmdGrid", "TableGrid")
        form = '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblLayout w:type="fixed"/></w:tblPr></w:tbl>'
        self.assertEqual(centred(template), template)
        self.assertEqual(centred(form), form)

    def test_a_file_is_rewritten_in_place(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "t.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", f"<w:document><w:body>{NARROW}</w:body></w:document>")
                archive.writestr("[Content_Types].xml", "<Types/>")
            self.assertEqual(centre_tables(path), 1)
            self.assertEqual(centre_tables(path), 0)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(len(re.findall(r'<w:jc w:val="center"/>', archive.read("word/document.xml").decode())), 1)
                self.assertIn("[Content_Types].xml", archive.namelist())


if __name__ == "__main__":
    unittest.main()
