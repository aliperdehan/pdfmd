"""v3.28.22: --check-source says which PDFs carry their source, from the attachment list alone."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

try:
    import pypdf
except ImportError:  # pragma: no cover
    pypdf = None


def blank(path: Path, attachments: dict[str, bytes] | None = None) -> None:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(200, 200)
    with path.open("wb") as handle:
        writer.write(handle)
    if attachments:
        pdfmd.write_pdf_attachments(path, attachments)


def with_source(path: Path, text: str, name: str = "doc.md", sha: str | None = None) -> None:
    manifest = {"format": 1, "pdfmd": "3.28.22", "name": name, "source": pdfmd.ATTACH_SOURCE,
                "sha256": sha or pdfmd.sha256_text(text)}
    blank(path, {pdfmd.ATTACH_MANIFEST: json.dumps(manifest).encode(), pdfmd.ATTACH_SOURCE: text.encode()})


@unittest.skipUnless(pypdf, "needs pypdf")
class Audit(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def run_pdfmd(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.root, env=env,
                              capture_output=True, text=True, timeout=120)

    def test_a_folder_lists_each_pdf_and_exits_1_when_one_has_no_source(self):
        with_source(self.root / "a.pdf", "# A\n\nText\n", "a.md")
        blank(self.root / "b.pdf")
        (self.root / "b.md").write_text("# B\n", encoding="utf-8")
        blank(self.root / "c.pdf")
        done = self.run_pdfmd("--check-source")
        lines = done.stdout.splitlines()
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertRegex(lines[0], r"^SOURCE\s+a\.pdf  a\.md, 3 lines, pdfmd 3\.28\.22$")
        self.assertRegex(lines[1], r"^NONE\s+b\.pdf  b\.md is beside it: pdfmd b\.md --attach-source$")
        self.assertRegex(lines[2], r"^NONE\s+c\.pdf  no c\.md beside it$")
        self.assertEqual(lines[3], "CHECK     3 PDFs: 1 with the source, 2 without")

    def test_all_carrying_exits_0_and_the_alias_and_a_file_argument_work(self):
        with_source(self.root / "a.pdf", "# A\n", "a.md")
        done = self.run_pdfmd("a.pdf", "--sources")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("CHECK     1 PDF: 1 with the source", done.stdout)

    def test_an_edited_attachment_and_a_newer_markdown_are_said(self):
        with_source(self.root / "a.pdf", "# A\n", "a.md", sha="0" * 64)
        (self.root / "a.md").write_text("# A edited\n", encoding="utf-8")
        later = time.time() + 60
        os.utime(self.root / "a.md", (later, later))
        out = self.run_pdfmd("--check-source").stdout
        self.assertIn("the attached text was edited after the build", out)
        self.assertIn("a.md beside it is newer", out)

    def test_an_unreadable_pdf_and_an_empty_folder(self):
        (self.root / "bad.pdf").write_bytes(b"not a pdf")
        self.assertIn("ERROR", self.run_pdfmd("--check-source").stdout)
        (self.root / "bad.pdf").unlink()
        done = self.run_pdfmd("--check-source")
        self.assertEqual(done.returncode, 0)
        self.assertIn("No PDF here.", done.stdout)

    def test_recursive_goes_below(self):
        (self.root / "sub").mkdir()
        with_source(self.root / "sub" / "a.pdf", "# A\n", "a.md")
        self.assertIn("No PDF here.", self.run_pdfmd("--check-source").stdout)
        self.assertIn("a.pdf", self.run_pdfmd("--check-source", "--recursive").stdout)


if __name__ == "__main__":
    unittest.main()
