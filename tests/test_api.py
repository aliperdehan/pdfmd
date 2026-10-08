"""The Python API: pdfmd.convert_file / convert_text."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Api(unittest.TestCase):
    def test_text_to_a_text_format_is_a_string_and_to_a_binary_one_bytes(self):
        html = pdfmd.convert_text("Some *text* here.\n", "html")
        self.assertIsInstance(html, str)
        self.assertIn("<em>text</em>", html)
        docx = pdfmd.convert_text("Some *text* here.\n", "docx")
        self.assertIsInstance(docx, bytes)
        self.assertTrue(docx.startswith(b"PK"))

    def test_another_input_format_is_read_by_its_extension(self):
        html = pdfmd.convert_text("Some *emphasis* here.\n\n* one\n* two\n", "html", format="rst")
        self.assertIn("<em>emphasis</em>", html)
        self.assertIn("<li>", html)

    def test_a_file_is_converted_beside_itself_and_left_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "note.md"
            text = "---\ntitle: T\n---\n\nHello.\n"
            source.write_text(text, encoding="utf-8")
            output = pdfmd.convert_file(source, "docx")
            self.assertEqual(output, source.with_suffix(".docx"))
            self.assertIn("word/document.xml", zipfile.ZipFile(output).namelist())
            self.assertEqual(source.read_text(encoding="utf-8"), text)          # no stamp, no backup
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["note.docx", "note.md"])

    def test_metadata_and_variables_reach_the_build(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "note.md"
            source.write_text("Hello.\n", encoding="utf-8")
            output = pdfmd.convert_file(source, "html", metadata=[], variables={"title": "My Title"},
                                        extra_args=["--standalone"])
            self.assertIn("My Title", output.read_text(encoding="utf-8"))

    def test_a_missing_file_or_a_failed_build_raises(self):
        with self.assertRaises(pdfmd.PdfmdError):
            pdfmd.convert_file("/nonexistent/none.md")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bad.md"
            source.write_text("Hello.\n", encoding="utf-8")
            with self.assertRaises(pdfmd.PdfmdError) as caught:
                pdfmd.convert_file(source, "html", extra_args=["--lua-filter", str(Path(directory) / "missing.lua")])
            self.assertNotEqual(caught.exception.returncode, 0)

    def test_the_version_is_available(self):
        self.assertEqual(pdfmd.pdfmd_version(), pdfmd.PDFMD_VERSION)


if __name__ == "__main__":
    unittest.main()
