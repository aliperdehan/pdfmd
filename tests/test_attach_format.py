"""v3.28.45: the manifest of an attached source is format 2; a pdfmd that reads up to 1 refuses it, this one reads 1 and 2."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

try:
    import pypdf
except ImportError:                                      # pragma: no cover
    pypdf = None


@unittest.skipIf(pypdf is None, "needs pypdf")
class Format(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.md = self.root / "doc.md"
        self.md.write_text("---\ntitle: T\n---\n\nText.\n", encoding="utf-8")
        self.pdf = self.root / "doc.pdf"
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with self.pdf.open("wb") as handle:
            writer.write(handle)
        with contextlib.redirect_stdout(io.StringIO()):
            self.attachments, _, self.manifest = pdfmd.source_attachments(self.md, self.pdf, [], [], [], None)

    def restore(self, manifest: dict, out: str) -> int:
        attachments = dict(self.attachments)
        attachments[pdfmd.ATTACH_MANIFEST] = json.dumps(manifest).encode("utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            return pdfmd.restore_attachments_in_place(self.pdf, attachments, self.root / out, False)

    def test_a_new_manifest_is_format_2(self):
        self.assertEqual(pdfmd.ATTACH_FORMAT, 2)
        self.assertEqual(self.manifest["format"], 2)

    def test_format_1_and_2_both_restore(self):
        for number in (1, 2):
            status = self.restore({**self.manifest, "format": number}, f"out{number}")
            self.assertEqual(status, 0)
            self.assertIn("Text.", (self.root / f"out{number}" / "doc.md").read_text(encoding="utf-8"))

    def test_a_newer_format_is_refused_with_the_versions(self):
        with self.assertRaises(SystemExit) as raised:
            self.restore({**self.manifest, "format": 3, "pdfmd": "9.9.9"}, "out3")
        text = str(raised.exception)
        for word in ("newer pdfmd", "pdfmd 9.9.9", "format 3", f"reads up to {pdfmd.ATTACH_FORMAT}", "upgrade pdfmd"):
            self.assertIn(word, text)
        self.assertFalse((self.root / "out3").exists())


if __name__ == "__main__":
    unittest.main()
