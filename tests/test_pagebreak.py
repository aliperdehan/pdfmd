"""Page breaks in every writer (v3.27.13): pdfmd_lua/pagebreak.lua and the built-in renderer's patterns, against one
list of spellings, and real PDFs and Word files counted."""

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

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
PAGEBREAK_LUA = ROOT / "pdfmd_lua" / "pagebreak.lua"

# (Markdown, a line the built-in renderer also reads): every spelling the filter knows
SPELLINGS = [
    ("<!-- pagebreak -->", True),
    ("<!-- page-break -->", True),
    ("<!-- NewPage -->", True),
    ("<!-- new-page -->", True),
    ("<!-- pdfmd: pagebreak -->", True),
    ("<!-- PDFMD: page-break -->", True),
    ("\\newpage", True),
    ("\\newpage{}", True),
    ("\\pagebreak", True),
    ("\\pagebreak[3]", True),
    ("\\clearpage", True),
    ("\\cleardoublepage", True),
    ('<div style="page-break-after: always"></div>', False),
    ('<div style="break-before: page"></div>', False),
    ('<div class="pagebreak"></div>', False),
    ('<hr class="pagebreak">', False),
    ("::: pagebreak\n:::", False),
    ("::: newpage\n:::", False),
    ("```{=typst}\n#pagebreak()\n```", False),
    ('```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```', False),
]
NOT_BREAKS = ["<!-- pagebreaks are explained below -->", "Write `\\newpage` for one.", "<div class=\"pagebreak\">words</div>"]

# what each writer gets, as a pattern over its output
TARGETS = {
    "latex": r"\\(?:newpage|pagebreak|clearpage|cleardoublepage)",
    "typst": r"#pagebreak\(",
    "html": r"<div style=\"[^\"]*break",
    "docx": None,                               # checked in the document XML
    "gfm": r"<!-- pagebreak -->",
    "plain": "\f",
    "context": r"\\page\b",
}


def document(spelling: str) -> str:
    return f"---\ntitle: T\n---\n\nBefore.\n\n{spelling}\n\nAfter.\n"


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-pagebreak-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def convert(self, text: str, writer: str, reader: str = "markdown") -> subprocess.CompletedProcess:
        source = self.directory / "doc.md"
        source.write_text(text, encoding="utf-8")
        output = self.directory / f"out.{writer}"
        done = subprocess.run([PANDOC, str(source), "-f", reader, "-t", writer, "-o", str(output), "--lua-filter",
                               str(PAGEBREAK_LUA)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        done.stdout = (output.read_bytes().decode("latin-1") if writer in ("docx", "odt")
                       else output.read_text(encoding="utf-8"))
        return done

    def test_every_spelling_becomes_every_writers_own(self):
        for spelling, _ in SPELLINGS:
            for writer, pattern in TARGETS.items():
                with self.subTest(spelling=spelling, writer=writer):
                    out = self.convert(document(spelling), writer).stdout
                    if writer == "docx":
                        with zipfile.ZipFile(self.directory / "out.docx") as word:
                            xml = word.read("word/document.xml").decode("utf-8")
                        self.assertEqual(xml.count('w:type="page"'), 1)
                        self.assertLess(xml.find("Before"), xml.find('w:type="page"'))
                        self.assertLess(xml.find('w:type="page"'), xml.find("After"))
                    else:
                        self.assertEqual(len(re.findall(pattern, out)), 1, out)
                        self.assertLess(out.find("Before"), out.find("After"))

    def test_a_spelling_in_the_writers_own_language_is_kept_as_written(self):
        self.assertIn("\\pagebreak[3]", self.convert(document("\\pagebreak[3]"), "latex").stdout)
        self.assertIn("\\cleardoublepage", self.convert(document("\\cleardoublepage"), "latex").stdout)
        self.assertIn('to: "odd"', self.convert(document("\\cleardoublepage"), "typst").stdout)
        self.assertIn("#pagebreak()", self.convert(document("```{=typst}\n#pagebreak()\n```"), "typst").stdout)

    def test_odt_gets_a_paragraph_in_the_pagebreak_style(self):
        self.convert(document("<!-- pagebreak -->"), "odt")
        with zipfile.ZipFile(self.directory / "out.odt") as odt:
            self.assertIn('text:style-name="Pagebreak"', odt.read("content.xml").decode("utf-8"))

    def test_github_markdown_reads_a_tex_command_as_words_and_it_still_breaks(self):
        out = self.convert("Before.\n\n\\newpage\n\nAfter.\n", "typst", reader="gfm").stdout
        self.assertIn("#pagebreak(", out)
        self.assertNotIn("newpage", out)

    def test_what_is_not_a_page_break(self):
        for text in NOT_BREAKS:
            with self.subTest(text=text):
                self.assertNotIn("#pagebreak", self.convert(document(text), "typst").stdout)

    def test_slides_drop_it_with_a_note_and_markdown_keeps_it(self):
        done = self.convert(document("<!-- pagebreak -->"), "beamer")
        self.assertNotIn("pagebreak", done.stdout)
        self.assertIn("1 page break left out", done.stderr)
        self.assertIn("\\newpage", self.convert(document("\\newpage"), "beamer").stdout)    # the author's own TeX
        self.assertIn("\\newpage", self.convert(document("\\newpage"), "markdown").stdout)


class NativeTier(unittest.TestCase):
    """The built-in renderer reads the line spellings with its own patterns: the same list."""

    def test_the_line_spellings(self):
        for spelling, line in SPELLINGS:
            matched = bool(pdfmd.PAGE_BREAK_COMMENT_RE.match(spelling) or pdfmd.PAGE_BREAK_RE.match(spelling))
            with self.subTest(spelling=spelling):
                self.assertEqual(matched, line)
        for text in NOT_BREAKS:
            self.assertFalse(pdfmd.PAGE_BREAK_COMMENT_RE.match(text) or pdfmd.PAGE_BREAK_RE.match(text))

    def test_kept_by_the_comment_stripper(self):
        for spelling, _ in SPELLINGS[:6]:
            self.assertIn(spelling, pdfmd.strip_markdown_comments(f"A\n\n{spelling}\n\nB\n"))

    def test_no_auto_leaves_the_filter_out(self):
        self.assertEqual(pdfmd.pagebreak_filter_args(["pagebreak"]), [])
        self.assertEqual(pdfmd.pagebreak_filter_args(None)[-1], str(PAGEBREAK_LUA))


FIVE = "\n\n".join(["One.", "<!-- pagebreak -->", "Two.", "\\newpage", "Three.", '<div class="pagebreak"></div>', "Four.",
                    "::: pagebreak\n:::", "Five.", "<!-- pdfmd: new-page -->", "Six."])


def pages(pdf: Path) -> int | None:
    if not shutil.which("pdfinfo"):
        return None
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    found = re.search(r"Pages:\s+(\d+)", info)
    return int(found.group(1)) if found else None


@unittest.skipUnless(PANDOC, "needs Pandoc")
class RealOutput(unittest.TestCase):
    """Five breaks, six pages, through pdfmd itself."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-pagebreak-real-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        (self.directory / "doc.md").write_text("---\ntitle: T\n---\n\n" + FIVE + "\n", encoding="utf-8")

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", *arguments], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory, env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    def test_six_pages_in_every_pdf_engine(self):
        engines = [engine for engine in ("lualatex", "typst", "weasyprint") if shutil.which(engine)]
        if not engines or not shutil.which("pdfinfo"):
            self.skipTest("needs a PDF engine and pdfinfo")
        for engine in engines:
            with self.subTest(engine=engine):
                done = self.run_pdfmd("-e", engine, "-o", f"{engine}.pdf")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(pages(self.directory / f"{engine}.pdf"), 6)

    def test_five_breaks_in_a_word_file_and_fewer_without_the_filter(self):
        done = self.run_pdfmd("-o", "doc.docx")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with zipfile.ZipFile(self.directory / "doc.docx") as word:
            self.assertEqual(word.read("word/document.xml").decode("utf-8").count('w:type="page"'), 5)
        done = self.run_pdfmd("-o", "old.docx", "--no-auto", "pagebreak")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with zipfile.ZipFile(self.directory / "old.docx") as word:
            self.assertLess(word.read("word/document.xml").decode("utf-8").count('w:type="page"'), 5)   # \newpage only


if __name__ == "__main__":
    unittest.main()
