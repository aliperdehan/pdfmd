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

    def test_no_change_leaves_the_pdf_alone(self):
        pdf = self.build()
        before = pdf.read_bytes()
        done = self.run_pdfmd("--edit", "report.pdf", "--editor", "true")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("No change", done.stdout)
        self.assertEqual(pdf.read_bytes(), before)
        self.assertFalse((self.root / ".backups").exists())

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
