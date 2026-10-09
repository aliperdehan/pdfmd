"""Whether a document cites or uses pandoc-crossref is asked of Pandoc's reader, not of a pattern."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["PDFMD_CONFIG"] = ""

import pdfmd  # noqa: E402


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Detection(unittest.TestCase):
    def features(self, text: str) -> tuple[bool, bool]:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.md"
            path.write_text(text, encoding="utf-8")
            return pdfmd.contains_citations(path), pdfmd.contains_crossref(path)

    def test_syntax_written_about_is_not_syntax_used(self):
        self.assertEqual(self.features("Use `@fig:setup` and `[@key]`.\n\n```\n@tbl:x\n```\n\nmail a@b.com, \\@x.\n"),
                         (False, False))

    def test_citations(self):
        self.assertEqual(self.features("As said [@harris2010, p. 3].\n"), (True, False))
        self.assertEqual(self.features("As @harris2010 said, -@other.\n"), (True, False))

    def test_crossref_references_and_labels(self):
        self.assertEqual(self.features("See @fig:setup.\n"), (True, True))
        self.assertEqual(self.features("![cap](a.png){#fig:setup}\n"), (False, True))
        self.assertEqual(self.features("| a |\n|---|\n| b |\n\n: cap {#tbl:t}\n"), (False, True))
        self.assertEqual(self.features("# Method {#sec:method}\n\ntext\n"), (False, True))

    def test_the_result_follows_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.md"
            path.write_text("plain\n", encoding="utf-8")
            self.assertFalse(pdfmd.contains_citations(path))
            path.write_text("now [@cited]\n", encoding="utf-8")
            self.assertTrue(pdfmd.contains_citations(path))

    def test_without_pandoc_the_pattern_is_the_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.md"
            path.write_text("See @fig:setup and [@key].\n", encoding="utf-8")
            old = os.environ["PATH"]
            os.environ["PATH"] = "/nonexistent"
            try:
                pdfmd._MARKDOWN_FEATURES.clear()
                self.assertTrue(pdfmd.contains_citations(path))
                self.assertTrue(pdfmd.contains_crossref(path))
            finally:
                os.environ["PATH"] = old
                pdfmd._MARKDOWN_FEATURES.clear()


if __name__ == "__main__":
    unittest.main()
