"""v3.29.9: `pdfmd-options: cover`. A title page of its own, or a picture for the first page / an EPUB's cover."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082")


class Args(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def doc(self, options: str, front: str = "") -> Path:
        path = self.root / "d.md"
        path.write_text(f"---\ntitle: T\n{front}pdfmd-options:\n  {options}\n---\n\ntext\n", encoding="utf-8")
        return path

    def test_off_by_default_and_when_false(self):
        self.assertEqual(pdfmd.cover_filter_args(self.doc("css-scope: html"), []), [])
        for value in ("false", "no", "off"):
            self.assertEqual(pdfmd.cover_filter_args(self.doc(f"cover: {value}"), []), [], value)

    def test_true_is_the_title_page(self):
        args = pdfmd.cover_filter_args(self.doc("cover: true"), [])
        self.assertIn("pdfmd-cover=title", args)
        self.assertIn("pdfmd-cover-latex=1", args)
        self.assertTrue(args[-1].endswith("cover.lua"))

    def test_a_class_without_titlepage_is_left_alone(self):
        args = pdfmd.cover_filter_args(self.doc("cover: true", "documentclass: myclass\n"), [])
        self.assertIn("pdfmd-cover-latex=0", args)

    def test_a_picture_is_resolved_beside_the_document(self):
        (self.root / "c.png").write_bytes(PNG)
        args = pdfmd.cover_filter_args(self.doc("cover: c.png"), [])
        self.assertIn("pdfmd-cover=image", args)
        self.assertIn(f"pdfmd-cover-image={(self.root / 'c.png').resolve()}", args)

    def test_a_missing_picture_is_a_warning_and_nothing(self):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(pdfmd.cover_filter_args(self.doc("cover: gone.png"), []), [])
        self.assertIn("cover: gone.png was not found", err.getvalue())


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Build(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "c.png").write_bytes(PNG)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}

    def run_pdfmd(self, options: str, *args: str) -> subprocess.CompletedProcess:
        (self.root / "d.md").write_text(f"---\ntitle: The Title\nauthor: A. Writer\npdfmd-options:\n  {options}\n---\n\n# One\n\nText.\n",
                                        encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--no-stamp", *args], cwd=self.root, env=self.env,
                              capture_output=True, text=True, timeout=300)

    def test_latex_gets_titlepage(self):
        done = self.run_pdfmd("cover: true", "--to", "latex", "-o", "d.tex")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex((self.root / "d.tex").read_text(encoding="utf-8"), r"\\documentclass\[[^\]]*titlepage")

    def test_html_gets_a_page_break_after_the_title_block(self):
        done = self.run_pdfmd("cover: true", "--to", "html", "-s", "-o", "d.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("#title-block-header { break-after: page", (self.root / "d.html").read_text(encoding="utf-8"))

    def test_a_picture_comes_before_the_title_in_latex_and_html(self):
        done = self.run_pdfmd("cover: c.png", "--to", "latex", "-o", "d.tex")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (self.root / "d.tex").read_text(encoding="utf-8")
        self.assertIn("\\AtBeginDocument{\\thispagestyle{empty}", text)
        self.assertLess(text.index("\\AtBeginDocument{\\thispagestyle"), text.index("\\maketitle"))
        done = self.run_pdfmd("cover: c.png", "--to", "html", "-s", "-o", "d.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        page = (self.root / "d.html").read_text(encoding="utf-8")
        self.assertIn('id="pdfmd-cover"', page)
        self.assertLess(page.index('id="pdfmd-cover"'), page.index("title-block-header\">"))

    def test_a_picture_is_the_cover_of_an_epub(self):
        done = self.run_pdfmd("cover: c.png", "-o", "d.epub")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with zipfile.ZipFile(self.root / "d.epub") as archive:
            self.assertIn("EPUB/text/cover.xhtml", archive.namelist())

    def test_a_writer_without_it_says_so_once(self):
        done = self.run_pdfmd("cover: true", "-o", "d.docx")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((done.stdout + done.stderr).count("cover: is not applied to docx"), 1)


if __name__ == "__main__":
    unittest.main()
