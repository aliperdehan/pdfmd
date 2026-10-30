"""v3.28.23: --edit FILE.pdf restores the source a PDF carries, edits it (your own editor: --editor CMD), rebuilds and
puts the new PDF in place of the old one, which goes to .backups/."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

try:
    import pypdf
except ImportError:  # pragma: no cover
    pypdf = None

ENGINE = shutil.which("lualatex") or shutil.which("xelatex") or shutil.which("pdflatex") or shutil.which("typst")


@unittest.skipUnless(pypdf and shutil.which("pandoc") and ENGINE, "needs pypdf, Pandoc and an engine")
class EditPdf(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "report.md").write_text("---\ntitle: R\n---\n\n# Intro\n\nFirst paragraph.\n", encoding="utf-8")
        (self.root / "adds.py").write_text(
            "import sys\nfrom pathlib import Path\nPath(sys.argv[1]).open('a', encoding='utf-8').write('\\nADDED PARAGRAPH here.\\n')\n",
            encoding="utf-8")
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}

    def run_pdfmd(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.root, env=self.env,
                              capture_output=True, text=True, timeout=600)

    def build(self) -> Path:
        done = self.run_pdfmd("report.md", "--attach-source")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return self.root / "report.pdf"

    def text(self, pdf: Path) -> str:
        return " ".join(page.extract_text() or "" for page in pypdf.PdfReader(pdf).pages)

    def test_an_edit_is_rebuilt_in_place_with_the_old_pdf_kept(self):
        pdf = self.build()
        self.assertNotIn("ADDED PARAGRAPH", self.text(pdf))
        before = pdf.read_bytes()
        done = self.run_pdfmd("--edit", "report.pdf", "--editor", f"{sys.executable} {self.root / 'adds.py'}")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("REPLACED  report.pdf", done.stdout)
        self.assertIn("ADDED PARAGRAPH", self.text(pdf))
        attached = pdfmd.read_pdf_attachments(pdf)
        self.assertIn("ADDED PARAGRAPH", attached[pdfmd.ATTACH_SOURCE].decode("utf-8"))          # it carries its source again
        backups = list((self.root / ".backups").glob("report.*.pdf"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        self.assertEqual(list(self.root.glob(".*.edit.tmp")), [])

    def test_what_a_build_writes_beside_the_source_is_not_an_edit(self):
        # backups (a .backups folder) are written into the restored folder by every build: one save, one build
        (self.root / "report.md").write_text(
            "---\ntitle: R\npdfmd-options:\n  backup:\n    enabled: true\n---\n\n# Intro\n\nFirst paragraph.\n", encoding="utf-8")
        (self.root / "stays.py").write_text(      # an editor that edits at once and stays open while the build runs
            "import sys, time\nfrom pathlib import Path\nPath(sys.argv[1]).open('a', encoding='utf-8')"
            ".write('\\nADDED PARAGRAPH here.\\n')\ntime.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 50)\n", encoding="utf-8")
        pdf = self.build()
        done = self.run_pdfmd("--edit", "report.pdf", "--editor", f"{sys.executable} {self.root / 'stays.py'}")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.count("BUILT "), 1, done.stdout)
        self.assertIn("ADDED PARAGRAPH", self.text(pdf))

    def test_no_change_leaves_the_pdf_alone(self):
        pdf = self.build()
        before = pdf.read_bytes()
        done = self.run_pdfmd("--edit", "report.pdf", "--editor", f"{sys.executable} -c pass")      # an editor that changes nothing
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("No change", done.stdout)
        self.assertEqual(pdf.read_bytes(), before)
        self.assertFalse((self.root / ".backups").exists())

    def test_a_report_is_edited_and_rebuilt_as_a_report_not_as_its_first_chapter(self):
        # v3.28.31: the first chunk was built alone, and a one-chapter PDF replaced the whole book
        for name, text in (("one.md", "---\ntitle: Book\n---\n\n# One\n\nFirst chapter text.\n"),
                           ("two.md", "---\nchapter: 2\n---\n\n# Two\n\nSecond chapter text.\n"),
                           ("three.md", "# Three\n\nThird chapter text.\n")):
            (self.root / name).write_text(text, encoding="utf-8")
        (self.root / "last.py").write_text(           # appends to the LAST file it is given
            "import sys\nfrom pathlib import Path\nPath(sys.argv[-1]).open('a', encoding='utf-8').write('\\nADDED PARAGRAPH here.\\n')\n",
            encoding="utf-8")
        done = self.run_pdfmd("-r", "one.md", "two.md", "three.md", "--attach-source", "-o", "book.pdf")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        pdf = self.root / "book.pdf"
        order = [word for word in ("First", "Second", "Third") if word in self.text(pdf)]
        edit = self.run_pdfmd("--edit", "book.pdf", "--editor", f"{sys.executable} {self.root / 'last.py'}")
        self.assertEqual(edit.returncode, 0, edit.stdout + edit.stderr)
        self.assertIn("REPLACED  book.pdf", edit.stdout)
        text = self.text(pdf)
        self.assertEqual([word for word in ("First", "Second", "Third") if word in text], order)
        self.assertEqual(len(order), 3)
        self.assertIn("ADDED PARAGRAPH", text)
        self.assertLess(text.index("Third"), text.index("ADDED PARAGRAPH"))
        manifest = pdfmd.json.loads(pdfmd.read_pdf_attachments(pdf)[pdfmd.ATTACH_MANIFEST].decode("utf-8"))
        self.assertEqual(manifest["mode"], "report")                   # still a report that carries its chapters
        self.assertEqual(len(manifest["chunks"]), 3)

    def test_one_document_is_edited_as_one_file_with_its_data_inside(self):
        # v3.28.40: the source is opened as the single file it is: the CSV a table reads is a block of that file
        (self.root / "t.csv").write_text("name,value\nOLDCELL,1\n", encoding="utf-8")
        (self.root / "metadata.yaml").write_text("author: Someone\n", encoding="utf-8")
        (self.root / "doc.md").write_text(
            "---\ntitle: D\n---\n\n# Data\n\n::: {.csv file=\"t.csv\"}\n:::\n", encoding="utf-8")
        (self.root / "swap.py").write_text(
            "import sys\nfrom pathlib import Path\npath = Path(sys.argv[1])\ntext = path.read_text(encoding='utf-8')\n"
            "Path(sys.argv[1] + '.seen').write_text('\\n'.join(sorted(p.name for p in path.parent.iterdir())))\n"
            "assert 'type: file' in text and 'author: Someone' in text and 'pdfmd-at: index' in text, text[:400]\n"
            "path.write_text(text.replace('OLDCELL', 'NEWCELL'), encoding='utf-8')\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "--attach-source", "--bundle")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        pdf = self.root / "doc.pdf"
        self.assertIn("OLDCELL", self.text(pdf))
        edit = self.run_pdfmd("--edit", "doc.pdf", "--editor", f"{sys.executable} {self.root / 'swap.py'}")
        self.assertEqual(edit.returncode, 0, edit.stdout + edit.stderr)
        self.assertIn("REPLACED  doc.pdf", edit.stdout)
        self.assertIn("NEWCELL", self.text(pdf))
        self.assertNotIn("OLDCELL", self.text(pdf))
        source = pdfmd.read_pdf_attachments(pdf)[pdfmd.ATTACH_SOURCE].decode("utf-8")
        self.assertIn("NEWCELL", source)                                  # it carries the edited data, as text
        self.assertNotIn("OLDCELL", source)
        self.assertIn("pdfmd-at: index", source)

    def test_a_rebuilt_pdf_that_lost_something_is_reported_and_one_without_its_source_is_refused(self):
        manifest = {"extras": [{"path": "a.csv", "inline": True}], "source": pdfmd.ATTACH_SOURCE}
        text = "---\npdfmd-assembled: true\n---\n\n```{=pdfmd}\ntype: bibliography\nname: x.bib\npath: x.bib\n\n@book{a}\n```\n"
        before = {pdfmd.ATTACH_MANIFEST: pdfmd.json.dumps(manifest).encode(), pdfmd.ATTACH_SOURCE: text.encode(),
                  "files/logo.pdf": b"x", "files/__up__/schemes/s.tex": b"y"}
        self.assertEqual(pdfmd.source_carried(before), {"a.csv", "x.bib", "logo.pdf", "../schemes/s.tex"})
        kept = self.root / "kept.pdf"
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=10, height=10)
        for name, data in {**before, "files/logo.pdf": b"x"}.items():
            writer.add_attachment(name, data)
        with kept.open("wb") as handle:
            writer.write(handle)
        lost = pdfmd.source_lost(before, kept)
        self.assertEqual(lost, None)                                      # everything it carried is still there
        less = self.root / "less.pdf"
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=10, height=10)
        for name in (pdfmd.ATTACH_MANIFEST, pdfmd.ATTACH_SOURCE):
            writer.add_attachment(name, before[name])
        with less.open("wb") as handle:
            writer.write(handle)
        self.assertTrue(pdfmd.source_lost(before, less).startswith("lost: "))
        self.assertIn("logo.pdf", pdfmd.source_lost(before, less))
        bare = self.root / "bare.pdf"
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=10, height=10)
        with bare.open("wb") as handle:
            writer.write(handle)
        self.assertIn("does not carry its source", pdfmd.source_lost(before, bare))

    def test_a_pdf_without_a_source_is_refused(self):
        writer = pypdf.PdfWriter()
        writer.add_blank_page(100, 100)
        with (self.root / "plain.pdf").open("wb") as handle:
            writer.write(handle)
        done = self.run_pdfmd("--edit", "plain.pdf", "--editor", "true")
        self.assertEqual(done.returncode, 1)
        self.assertIn("carries no pdfmd source", done.stderr)


if __name__ == "__main__":
    unittest.main()
