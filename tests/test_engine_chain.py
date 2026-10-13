"""v3.28.42: `-e typst,calibre,lualatex` is an ordered list of what to try; `pandoc` is every engine Pandoc drives; a front
matter or config `pdf-engine:` takes the same list (a comma string or a YAML list)."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class Chain(unittest.TestCase):
    def select(self, requested, installed=("pandoc", "lualatex", "xelatex", "typst", "weasyprint"), calibre="/opt/bin/ebook-convert",
               presentation=False):
        with mock.patch.object(pdfmd, "which", lambda name: f"/opt/bin/{name}" if name in installed else None), \
                mock.patch.object(pdfmd, "resolve_calibre", lambda: calibre), \
                mock.patch.object(pdfmd, "resolve_soffice", lambda: None):
            return pdfmd.select_engines(requested, presentation)

    def test_the_order_written_is_the_order_tried(self):
        self.assertEqual(self.select("typst,calibre,lualatex"), ["typst", "calibre", "lualatex"])
        self.assertEqual(self.select("lualatex, typst"), ["lualatex", "typst"])

    def test_a_family_and_the_word_pandoc_expand_in_place_and_nothing_is_tried_twice(self):
        self.assertEqual(self.select("typst,tex,lualatex"), ["typst", "lualatex", "xelatex"])
        self.assertEqual(self.select("calibre,pandoc"), ["calibre", "lualatex", "xelatex", "typst", "weasyprint"])
        self.assertEqual(self.select("pandoc"), ["lualatex", "xelatex", "typst", "weasyprint"])         # never Calibre

    def test_named_means_named(self):
        # an engine that is installed but not in the list is not tried
        chain = self.select("typst,lualatex")
        self.assertNotIn("weasyprint", chain)
        self.assertNotIn("xelatex", chain)

    def test_a_word_that_cannot_run_is_passed_over_with_a_note_unless_nothing_can(self):
        shown = io.StringIO()
        with contextlib.redirect_stderr(shown):
            self.assertEqual(self.select("calibre,lualatex", calibre=None), ["lualatex"])
        self.assertIn("calibre", shown.getvalue())
        self.assertIn("the next in the list is tried", shown.getvalue())
        with self.assertRaises(SystemExit) as raised:
            self.select("calibre,prince", calibre=None)
        self.assertIn("none of it can run", str(raised.exception))

    def test_slides_keep_only_the_engines_beamer_can_use(self):
        self.assertEqual(self.select("typst,lualatex", presentation=True), ["lualatex"])

    def test_one_engine_and_no_request_are_what_they_were(self):
        self.assertEqual(self.select("typst"), ["typst"])
        self.assertEqual(self.select(None), ["lualatex", "xelatex", "typst", "weasyprint"])
        self.assertEqual(self.select("html"), ["weasyprint"])


class Settings(unittest.TestCase):
    def engine(self, front: str, config: dict | None = None) -> str | None:
        with tempfile.TemporaryDirectory() as folder:
            md = Path(folder) / "d.md"
            md.write_text(f"---\n{front}---\n\nText.\n", encoding="utf-8")
            with mock.patch.object(pdfmd, "config_options", lambda: config or {}):
                return pdfmd.frontmatter_engine(md)

    def test_a_list_or_a_comma_string_in_pdfmd_options(self):
        self.assertEqual(self.engine("pdfmd-options:\n  pdf-engine: [typst, lualatex]\n"), "typst,lualatex")
        self.assertEqual(self.engine("pdfmd-options:\n  engine: typst, lualatex\n"), "typst, lualatex")
        self.assertEqual(self.engine("pdfmd-options:\n  pdf-engine: lualatex\n"), "lualatex")

    def test_the_older_top_level_key_and_the_config_take_a_list_too(self):
        self.assertEqual(self.engine("pdf-engine: [typst, lualatex]\n"), "typst, lualatex")
        self.assertEqual(self.engine("title: T\n", {"pdf-engine": ["typst", "lualatex"]}), "typst,lualatex")


if __name__ == "__main__":
    unittest.main()
