"""`backup: {pdfs: N}` (v3.32.42, entry 3do): the PDF a build made is copied beside the source copies; N is how many are kept (negative: all,
0: none), a milestone name is never counted, and the source copies' own `keep:` does not touch the PDFs."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
ENGINES = [name for name in ("lualatex", "xelatex", "pdflatex") if shutil.which(name)]


class Pdfs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.md = self.dir / "report.md"
        self.pdf = self.dir / "report.pdf"

    def document(self, backup: str) -> None:
        self.md.write_text(f"---\ntitle: T\npdfmd-options:\n  backup: {backup}\n---\n\ntext\n", encoding="utf-8")

    def build(self, content: bytes, when: datetime) -> Path | None:
        self.pdf.write_bytes(content)
        with contextlib.redirect_stdout(io.StringIO()):
            return pdfmd.backup_pdf_after_success(self.md, self.pdf, [], None, False, when)

    def copies(self) -> list[str]:
        folder = self.dir / ".backups"
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []

    def test_backup_alone_keeps_no_pdf(self):
        self.document("true")
        self.assertIsNone(self.build(b"%PDF-1", datetime(2026, 11, 5, 10, 0, 0)))
        self.assertEqual(self.copies(), [])

    def test_without_backup_nothing_is_copied(self):
        self.md.write_text("---\ntitle: T\n---\n\ntext\n", encoding="utf-8")
        self.assertIsNone(self.build(b"%PDF-1", datetime(2026, 11, 5, 10, 0, 0)))
        self.assertEqual(self.copies(), [])

    def test_a_negative_number_keeps_every_pdf_under_the_stamp_of_the_run(self):
        self.document("{enabled: true, pdfs: -1}")
        first = self.build(b"%PDF-1 a", datetime(2026, 11, 5, 10, 0, 0))
        self.build(b"%PDF-1 b", datetime(2026, 11, 5, 10, 5, 0))
        self.assertEqual(first.name, "report_20261105-100000.pdf")
        self.assertEqual(self.copies(), ["report_20261105-100000.pdf", "report_20261105-100500.pdf"])

    def test_n_keeps_the_newest_n(self):
        self.document("{enabled: true, pdfs: 2}")
        for minute in range(4):
            self.build(f"%PDF {minute}".encode(), datetime(2026, 11, 5, 10, minute, 0))
        self.assertEqual(self.copies(), ["report_20261105-100200.pdf", "report_20261105-100300.pdf"])

    def test_zero_and_none_keep_none(self):
        for word in ("0", "none"):
            with self.subTest(word=word):
                self.document("{enabled: true, pdfs: %s}" % word)
                self.assertIsNone(self.build(b"%PDF-1", datetime(2026, 11, 5, 10, 0, 0)))
                self.assertEqual(self.copies(), [])

    def test_the_same_file_is_not_copied_twice_and_a_clash_gets_a_counter(self):
        self.document("{enabled: true, pdfs: -1}")
        self.build(b"%PDF same", datetime(2026, 11, 5, 10, 0, 0))
        self.assertIsNone(self.build(b"%PDF same", datetime(2026, 11, 5, 10, 1, 0)))
        self.build(b"%PDF other", datetime(2026, 11, 5, 10, 0, 0))                 # the stamp of the first, another file
        self.assertEqual(self.copies(), ["report_20261105-100000-2.pdf", "report_20261105-100000.pdf"])

    def test_a_milestone_pdf_is_never_counted_or_pruned_and_the_sources_do_not_see_the_pdfs(self):
        self.document("{enabled: true, pdfs: 1}")
        folder = self.dir / ".backups"
        folder.mkdir()
        (folder / "report_submitted_20261003-000313.pdf").write_bytes(b"%PDF milestone")
        for minute in range(3):
            self.build(f"%PDF {minute}".encode(), datetime(2026, 11, 5, 10, minute, 0))
        self.assertEqual(self.copies(), ["report_20261105-100200.pdf", "report_submitted_20261003-000313.pdf"])
        every, prunable = pdfmd.backup_snapshots(folder, self.md, pdfmd.backup_template("stem"))
        self.assertEqual((every, prunable), ([], []), "a PDF is not a version of the source")

    def test_a_wrong_value_is_refused_with_its_name(self):
        self.document("{enabled: true, pdfs: lots}")
        with self.assertRaises(SystemExit) as raised:
            pdfmd.resolve_backup_options(self.md, [], None)
        self.assertIn("pdfs", str(raised.exception))

    def test_the_default_and_the_words(self):
        self.document("true")
        self.assertEqual(pdfmd.resolve_backup_options(self.md, [], None)["pdfs"], 0)
        for given, want in (("all", -1), ("-3", -3), ("7", 7), ("off", 0)):
            self.document("{enabled: true, pdfs: %s}" % given)
            self.assertEqual(pdfmd.resolve_backup_options(self.md, [], None)["pdfs"], want, given)

    def test_a_missing_pdf_is_no_error(self):
        self.document("true")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(pdfmd.backup_pdf_after_success(self.md, self.dir / "ghost.pdf", [], None, False))


@unittest.skipUnless(PANDOC and ENGINES, "needs Pandoc and a LaTeX engine")
class Builds(unittest.TestCase):
    def test_a_build_keeps_its_pdf_next_to_the_source_copy_and_prunes_to_n(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            report = folder / "report.md"
            report.write_text("---\ntitle: T\npdfmd-options:\n  backup: {enabled: true, pdfs: 1}\n---\n\ntext\n", encoding="utf-8")
            outputs = []
            for number in range(2):
                report.write_text(report.read_text(encoding="utf-8") + f"\nline {number}\n", encoding="utf-8")
                done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report.md", "-e", ENGINES[0], "--no-cache", "--no-stamp"],
                                      cwd=folder, capture_output=True, text=True, encoding="utf-8",
                                      env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                outputs.append(done.stdout)
            names = sorted(path.name for path in (folder / ".backups").iterdir())
            pdfs = [name for name in names if name.endswith(".pdf")]
            self.assertEqual(len(pdfs), 1, names)                                  # pdfs: 1, two builds
            sources = [name for name in names if name.startswith("report.md.bak.")]
            self.assertEqual(len(sources), 2, names)
            self.assertEqual(pdfs[0][len("report_"):-len(".pdf")].replace("-", ""), sources[-1][len("report.md.bak."):], "the stamps pair up")
            self.assertTrue(any(line.startswith("BACKUP  ") and line.endswith(".pdf") for line in outputs[-1].splitlines()), outputs[-1])


if __name__ == "__main__":
    unittest.main()
