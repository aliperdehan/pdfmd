"""Comments stripped from the Markdown that leaves the author's hands, and the
source attached to a PDF (v3.22.0 on): pure functions tested directly, the
rest through the real CLI."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

strip = pdfmd.strip_markdown_comments


class StripComments(unittest.TestCase):
    def test_inline_and_standalone(self):
        text = "A <!-- one --> b.\n\n<!-- alone -->\n\nC.\n"
        self.assertEqual(strip(text), "A b.\n\nC.\n")

    def test_standalone_between_lines_takes_its_line_only(self):
        self.assertEqual(strip("a\n<!-- x -->\nb\n"), "a\nb\n")

    def test_no_doubled_blank_line_is_left(self):
        self.assertEqual(strip("p\n\n<!-- x -->\n\nq\n"), "p\n\nq\n")

    def test_trailing_and_glued(self):
        self.assertEqual(strip("text <!-- t -->\na<!--x-->b\n"), "text\nab\n")

    def test_multiline(self):
        self.assertEqual(strip("a\n\n<!-- one\ntwo\nthree -->\nb\n"), "a\n\nb\n")
        self.assertEqual(strip("lead <!-- one\ntwo --> tail\n"), "lead tail\n")

    def test_code_is_text(self):
        fenced = "```md\n<!-- in a fence -->\n```\n"
        self.assertEqual(strip(fenced), fenced)
        tilde = "~~~\n<!-- x -->\n~~~\n"
        self.assertEqual(strip(tilde), tilde)
        span = "a `<!-- not one -->` b <!-- one -->\n"
        self.assertEqual(strip(span), "a `<!-- not one -->` b\n")
        indented = "para\n\n    <!-- code -->\n\nnext\n"
        self.assertEqual(strip(indented), indented)

    def test_fence_inside_a_comment_does_not_open_one(self):
        self.assertEqual(strip("<!--\n```\n-->\n\n<!-- b -->\ntext\n"), "text\n")

    def test_front_matter_is_untouched(self):
        text = "---\ntitle: X <!-- y -->\n---\n\nBody <!-- z -->\n"
        self.assertEqual(strip(text), "---\ntitle: X <!-- y -->\n---\n\nBody\n")

    def test_pdfmd_markers_and_page_breaks_stay(self):
        text = "a\n\n<!-- pagebreak -->\n\nb\n\n<!-- pdfmd-assembled: true -->\n"
        self.assertEqual(strip(text), text)

    def test_build_notes_block_goes(self):
        text = "Text.\n\n<!--\n======\nBUILD NOTES\n  Compiled 2026 by pdfmd v3.0\n======\n-->\n"
        self.assertEqual(strip(text), "Text.\n\n")

    def test_unterminated_comment_is_kept_as_written(self):
        self.assertEqual(strip("a\n<!-- never closed\nb\n"), "a\n<!-- never closed\nb\n")

    def test_idempotent(self):
        text = "x <!-- a --> y\n\n<!-- b -->\n\n```\n<!-- c -->\n```\n"
        self.assertEqual(strip(strip(text)), strip(text))


class AssembledStrip(unittest.TestCase):
    def run_pdfmd(self, *args: str, cwd: Path) -> str:
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=cwd,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def test_assemble_only_strips_on_request(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "doc.md").write_text(
                "---\ntitle: T\n---\n\nHello <!-- private -->.\n\n```\n<!-- code -->\n```\n",
                encoding="utf-8")
            self.run_pdfmd("doc.md", "--assemble-only", cwd=directory)
            self.assertIn("private", (directory / "doc.assembled.md").read_text(encoding="utf-8"))
            (directory / "doc.assembled.md").unlink()
            self.run_pdfmd("doc.md", "--assemble-only", "--strip-comments", cwd=directory)
            stripped = (directory / "doc.assembled.md").read_text(encoding="utf-8")
            self.assertNotIn("private", stripped)
            self.assertIn("<!-- code -->", stripped)

    def test_option_in_the_document_and_the_command_line_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "doc.md").write_text(
                "---\ntitle: T\npdfmd-options:\n  strip-comments: true\n---\n\nHello <!-- private -->.\n",
                encoding="utf-8")
            self.run_pdfmd("doc.md", "--assemble-only", cwd=directory)
            self.assertNotIn("private", (directory / "doc.assembled.md").read_text(encoding="utf-8"))
            (directory / "doc.assembled.md").unlink()
            self.run_pdfmd("doc.md", "--assemble-only", "--keep-comments", cwd=directory)
            self.assertIn("private", (directory / "doc.assembled.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
