"""v3.29.1: an ebook as input. An EPUB goes straight to Pandoc; a MOBI, AZW3, KEPUB ... is turned into an EPUB by Calibre's
ebook-convert first. The Markdown made in a scratch folder is built as any file is, and shown as the book."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")

STUB = """#!{python}
import json, shutil, sys
with open({log!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
shutil.copyfile({epub!r}, sys.argv[2])
"""


class Alias(unittest.TestCase):
    def test_the_scratch_markdown_is_shown_as_the_book(self):
        scratch = Path(tempfile.mkdtemp(prefix="pdfmd-alias-"))
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        markdown = scratch / "book.md"
        markdown.write_text("x\n", encoding="utf-8")
        book = Path("somewhere") / "book.mobi"
        with unittest.mock.patch.dict(pdfmd.DISPLAY_ALIAS, {markdown.resolve(): book}):
            self.assertIn("book.mobi", pdfmd.display_path(markdown))
        self.assertNotIn("book.mobi", pdfmd.display_path(markdown))

    def test_the_extensions(self):
        for suffix in (".epub", ".mobi", ".azw3", ".kepub", ".lit"):
            self.assertIn(suffix, pdfmd.EBOOK_INPUT_EXTENSIONS)
        self.assertNotIn(".md", pdfmd.EBOOK_INPUT_EXTENSIONS)
        self.assertNotIn(".pdf", pdfmd.EBOOK_INPUT_EXTENSIONS)


@unittest.skipUnless(PANDOC and sys.platform != "win32", "needs Pandoc and a POSIX shell for the stand-in ebook-convert")
class Build(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-ebook-input-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        source = self.directory / "src.md"
        source.write_text("---\ntitle: Tiny Book\nauthor: A. Writer\n---\n\n# Chapter One\n\nA sentence with *emphasis* in it.\n\n"
                          "- first\n- second\n", encoding="utf-8")
        subprocess.run([PANDOC, str(source), "-o", str(self.directory / "book.epub")], check=True, capture_output=True)
        self.log = self.directory / "calls.log"
        folder = self.directory / "bin"
        folder.mkdir()
        self.stub = folder / "ebook-convert"
        self.stub.write_text(STUB.format(python=sys.executable, log=str(self.log), epub=str(self.directory / "book.epub")),
                             encoding="utf-8")
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)
        (self.directory / "book.mobi").write_bytes(b"BOOKMOBI not really")

    def run_pdfmd(self, *args: str, calibre: bool = True) -> subprocess.CompletedProcess:
        env = {**os.environ, "PDFMD_NO_PROMPT": "1", "PDFMD_CALIBRE": str(self.stub) if calibre else ""}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args, "--no-stamp"], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=env)

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def test_an_epub_goes_straight_to_pandoc_without_calibre(self):
        done = self.run_pdfmd("book.epub", "-o", "out.md", calibre=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("BOOK      book.epub read as Markdown", done.stdout)
        self.assertIn("OK    book.epub > out.md", done.stdout)
        text = (self.directory / "out.md").read_text(encoding="utf-8")
        self.assertIn("Chapter One", text)
        self.assertIn("emphasis", text)
        self.assertIn("second", text)
        self.assertEqual(self.calls(), [])

    def test_a_mobi_goes_through_ebook_convert_to_an_epub(self):
        done = self.run_pdfmd("book.mobi", "-o", "out.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("OK    book.mobi > out.md", done.stdout)
        self.assertNotIn("pdfmd-ebook", done.stdout)                               # no scratch path in the closing line
        self.assertIn("Chapter One", (self.directory / "out.md").read_text(encoding="utf-8"))
        (call,) = self.calls()
        self.assertTrue(call[0].endswith("book.mobi"), call)
        self.assertTrue(call[1].endswith(".epub"), call)
        self.assertIn("--no-default-epub-cover", call)

    def test_the_output_is_named_after_the_book_beside_it(self):
        done = self.run_pdfmd("book.epub", "--to", "docx", calibre=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "book.docx").is_file())
        self.assertIn("OK    book.epub > book.docx", done.stdout)

    def test_a_book_in_a_folder_keeps_its_name_in_the_line(self):
        (self.directory / "shelf").mkdir()
        shutil.move(str(self.directory / "book.epub"), str(self.directory / "shelf" / "novel.epub"))
        done = self.run_pdfmd("shelf/novel.epub", "--to", "docx", calibre=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "shelf" / "novel.docx").is_file())
        self.assertIn("novel.epub", done.stdout)

    def test_without_calibre_a_mobi_says_how_to_get_it(self):
        done = self.run_pdfmd("book.mobi", "-o", "out.md", calibre=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("ebook-convert", done.stdout + done.stderr)
        self.assertIn("Install Calibre", done.stdout + done.stderr)
        self.assertFalse((self.directory / "out.md").exists())

    def test_an_ebook_is_built_alone(self):
        (self.directory / "other.md").write_text("Hello\n", encoding="utf-8")
        done = self.run_pdfmd("book.epub", "other.md", calibre=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("one at a time", done.stdout + done.stderr)

    def test_a_missing_book_is_named(self):
        done = self.run_pdfmd("gone.epub", calibre=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("gone.epub: no such file", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
