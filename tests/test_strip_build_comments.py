"""The build's own HTML comments obey strip-comments, after preserving pdfmd markers."""
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
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class BuildComments(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-build-comments-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)

    def build(self, text, writer="html", *flags):
        source = self.root / "doc.md"
        source.write_text(text, encoding="utf-8")
        output = self.root / ("doc." + writer)
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), str(source), "-t", writer,
                               "-s", "-o", str(output), "--no-stamp", "--no-backup", *flags], cwd=self.root,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"},
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        if writer == "epub":
            with zipfile.ZipFile(output) as archive:
                result = "\n".join(archive.read(n).decode("utf-8") for n in archive.namelist() if n.endswith(".xhtml"))
        else:
            result = output.read_text(encoding="utf-8")
        return result, done.stdout + done.stderr

    def test_own_comments_default_on_off_and_code(self):
        text = "---\ntitle: Comments\n---\n\nBefore.\n\n<!-- SecretMarker -->\n\nAfter.\n\n`<!-- CodeMarker -->`\n"
        for writer in ("html", "epub"):
            with self.subTest(writer=writer):
                self.assertIn("SecretMarker", self.build(text, writer)[0])
                stripped = self.build(text, writer, "--strip-comments")[0]
                self.assertNotIn("SecretMarker", stripped)
                self.assertIn("CodeMarker", stripped)
                self.assertIn("SecretMarker", self.build(text, writer, "--keep-comments")[0])
        enabled = text.replace("title: Comments", "title: Comments\npdfmd-options: {strip-comments: true}")
        self.assertNotIn("SecretMarker", self.build(enabled)[0])
        self.assertIn("SecretMarker", self.build(enabled, "html", "--keep-comments")[0])
        self.assertNotIn("SecretMarker", self.build(text, "html", "--strip-comments-in", "markdown")[0])
        self.assertIn("SecretMarker", self.build(text, "html", "--strip-comments-in", "csl")[0])

    def test_markers_and_parts_keep_working(self):
        (self.root / "parts").mkdir()
        (self.root / "parts" / "10-body.md").write_text("# Part heading\n\nPartMarker.\n\n<!-- PartSecret -->\n", encoding="utf-8")
        text = "---\ntitle: Markers\npdfmd-options: {parts: auto, strip-comments: true}\n---\n\n<!-- pdfmd: parts -->\n\n<!-- ToC -->\n\n# Main heading\n\n<!-- PAGE-BREAK -->\n\nAfterBreak.\n\n<!-- appendix -->\n\n# Appendix\n"
        output, _ = self.build(text)
        self.assertIn("PartMarker", output)
        self.assertNotIn("PartSecret", output)
        self.assertIn('<strong>Contents</strong>', output)
        self.assertIn('href="#main-heading"', output)
        self.assertIn("break-after", output)
        latex, _ = self.build(text, "latex")
        self.assertIn("\\appendix", latex)
        self.assertIn("\\tableofcontents", latex)

    def test_show_comments_strips_before_drawing_and_all_writers(self):
        text = "---\ntitle: Comments\n---\n\nBody.\n\n<!-- SecretMarker -->\n\nAfter.\n"
        for writer in ("html", "epub", "latex", "typst"):
            with self.subTest(writer=writer):
                self.assertIn("SecretMarker", self.build(text, writer, "--show-comments")[0])
                self.assertNotIn("SecretMarker", self.build(text, writer, "--show-comments", "--strip-comments")[0])

    def test_percent_comments_are_private_with_gfm_and_unclosed_is_kept(self):
        text = "---\ntitle: Comments\n---\n\nVisible %% SecretMarker %% text.\n\nUnclosed %% remains.\n"
        output, log = self.build(text, "html", "--from", "gfm")
        self.assertNotIn("SecretMarker", output)
        self.assertIn("Unclosed %% remains.", output)
        self.assertIn("with no closing `%%`", log)
        self.assertIn("SecretMarker", self.build(text, "html", "--from", "gfm", "--show-comments")[0])


if __name__ == "__main__":
    unittest.main()
