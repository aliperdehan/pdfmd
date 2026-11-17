"""Only audited default templates warn when their title block loses the byline."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: F401,E402

ROOT = Path(__file__).resolve().parent.parent
NOTE = "author/date not printed: no title (add `title:`)"


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class TitleNote(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-title-note-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)

    def build(self, writer, title=False, extra=(), byline="author: BylineMarker\ndate: DateMarker\n"):
        source = self.root / "doc.md"
        source.write_text("---\n" + ("title: TitleMarker\n" if title else "") + byline + "---\n\nBody.\n", encoding="utf-8")
        output = self.root / ("doc." + writer)
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), str(source), "-t", writer, "-s",
                               "-o", str(output), "--no-stamp", "--no-backup", *extra], cwd=self.root,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"},
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout + done.stderr, output

    def test_checked_templates_that_drop_the_byline(self):
        for writer in ("latex", "typst", "html"):
            for byline in ("author: BylineMarker\n", "date: DateMarker\n", "author: BylineMarker\ndate: DateMarker\n"):
                with self.subTest(writer=writer, byline=byline):
                    log, _ = self.build(writer, byline=byline)
                    self.assertEqual(log.count(NOTE), 1, log)
                    self.assertNotIn(NOTE, self.build(writer, title=True, byline=byline)[0])

    def test_writers_that_print_the_byline(self):
        for writer, member in (("docx", "word/document.xml"), ("odt", "content.xml"), ("epub", None)):
            with self.subTest(writer=writer):
                log, output = self.build(writer)
                self.assertNotIn(NOTE, log)
                with zipfile.ZipFile(output) as archive:
                    text = archive.read(member).decode("utf-8") if member else "\n".join(
                        archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".xhtml"))
                self.assertIn("BylineMarker", text)
                self.assertIn("DateMarker", text)

    def test_custom_template_and_cli_title(self):
        template = self.root / "custom.html"
        template.write_text("$author$ $date$ $body$", encoding="utf-8")
        self.assertNotIn(NOTE, self.build("html", extra=("--template", str(template)))[0])
        self.assertNotIn(NOTE, self.build("html", extra=("-M", "title=CLI"))[0])
        self.assertNotIn(NOTE, self.build("html", extra=("-V", "title=CLI"))[0])
        self.assertIn(NOTE, self.build("html", extra=("-V", "title="))[0])
        defaults = self.root / "defaults.yaml"
        defaults.write_text("template: custom.html\n", encoding="utf-8")
        self.assertNotIn(NOTE, self.build("html", extra=("--defaults", str(defaults)))[0])


if __name__ == "__main__":
    unittest.main()
