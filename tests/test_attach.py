"""Comments stripped from the Markdown that leaves the author's hands, and the
source attached to a PDF (v3.22.0 on): pure functions tested directly, the
rest through the real CLI."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import pypdf
except ImportError:                                  # pragma: no cover
    pypdf = None

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

    def test_punctuation_closes_up(self):
        self.assertEqual(strip("Hello <!-- c -->. Bye <!-- d -->, ok (<!-- e -->)\n"), "Hello. Bye, ok ()\n")

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


def blank_pdf(path: Path) -> Path:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


@unittest.skipIf(pypdf is None, "pypdf not installed")
class AttachAndRestore(unittest.TestCase):
    """attach_source_after_success + restore_from_pdf on a blank PDF (no engine
    needed: the attachment step only looks at the finished PDF)."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)

    def attach(self, document: Path, parts=(), metadata=(), preamble=()):
        pdf = blank_pdf(document.with_suffix(".pdf"))
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.attach_source_after_success(document, pdf, list(parts), list(metadata), list(preamble),
                                              None, False)
        return pdf

    def restore(self, pdf: Path, name="out") -> Path:
        target = self.root / name
        with contextlib.redirect_stdout(io.StringIO()):
            status = pdfmd.restore_from_pdf(pdf, target)
        self.assertEqual(status, 0)
        return target

    def test_single_file_round_trip_with_metadata_and_preamble(self):
        (self.root / "metadata").mkdir()
        (self.root / "metadata" / "metadata.yaml").write_text("author: A. Author\n", encoding="utf-8")
        (self.root / "metadata" / "preamble.tex").write_text("\\usepackage{xcolor}\n", encoding="utf-8")
        document = self.root / "report.md"
        document.write_text("---\ntitle: T\n---\n\nHello <!-- private -->.\n\n## Two\n\nBody.\n",
                            encoding="utf-8")
        pdf = self.attach(document, metadata=[self.root / "metadata" / "metadata.yaml"],
                          preamble=[self.root / "metadata" / "preamble.tex"])
        out = self.restore(pdf)
        restored = (out / "report.md").read_text(encoding="utf-8")
        self.assertNotIn("private", restored)
        self.assertNotIn("pdfmd-assembled", restored)
        self.assertNotIn("embedded", restored)
        self.assertIn("Hello.", restored)
        self.assertEqual((out / "metadata" / "metadata.yaml").read_text(encoding="utf-8"), "author: A. Author\n")
        self.assertEqual((out / "metadata" / "preamble.tex").read_text(encoding="utf-8").strip(),
                         "\\usepackage{xcolor}")

    def test_comments_kept_when_the_document_says_so(self):
        document = self.root / "keep.md"
        document.write_text("---\ntitle: T\npdfmd-options:\n  strip-comments: false\n---\n\nA <!-- note -->.\n",
                            encoding="utf-8")
        out = self.restore(self.attach(document))
        self.assertIn("<!-- note -->", (out / "keep.md").read_text(encoding="utf-8"))

    def test_parts_come_back_with_their_boundaries_and_front_matter(self):
        (self.root / "parts").mkdir()
        scaffold = self.root / "report.md"
        scaffold.write_text("---\ntitle: T\npdfmd-options:\n  parts: auto\n---\n", encoding="utf-8")
        first = self.root / "parts" / "10-a.md"
        first.write_text("---\nchapter: 1\n---\n\n# A\n\nOne <!-- x --> two.\n\nThree.\n", encoding="utf-8")
        second = self.root / "parts" / "20-b.md"
        second.write_text("# B\n\nOnly body.\n", encoding="utf-8")
        out = self.restore(self.attach(scaffold, parts=[first, second]))
        self.assertEqual((out / "parts" / "20-b.md").read_text(encoding="utf-8"), "# B\n\nOnly body.\n")
        self.assertEqual((out / "parts" / "10-a.md").read_text(encoding="utf-8"),
                         "---\nchapter: 1\n---\n\n# A\n\nOne two.\n\nThree.\n")
        self.assertIn("parts: auto", (out / "report.md").read_text(encoding="utf-8"))

    def test_images_are_recorded_not_stored(self):
        (self.root / "images").mkdir()
        (self.root / "images" / "f.png").write_bytes(b"\x89PNG fake")
        document = self.root / "d.md"
        document.write_text("![fig](images/f.png)\n", encoding="utf-8")
        pdf = self.attach(document)
        manifest = json.loads(pdfmd.read_pdf_attachments(pdf)[pdfmd.ATTACH_MANIFEST])
        self.assertEqual([image["path"] for image in manifest["images"]], ["images/f.png"])
        self.assertEqual(set(pdfmd.read_pdf_attachments(pdf)), {pdfmd.ATTACH_MANIFEST, pdfmd.ATTACH_SOURCE})

    def bundle(self, document: Path, mode: str, **kwargs) -> Path:
        previous = pdfmd.BUNDLE_CLI
        pdfmd.BUNDLE_CLI = mode
        try:
            return self.attach(document, **kwargs)
        finally:
            pdfmd.BUNDLE_CLI = previous

    def test_bundle_stores_what_the_text_points_at_and_restore_puts_it_back(self):
        for name, content in (("images/f.png", b"\x89PNG fake"), ("data/t.csv", b"a,b\n1,2\n"),
                              ("ir/x.csv", b"x\n"), ("unrelated.bin", b"nope")):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(content)
        document = self.root / "d.md"
        document.write_text(
            "---\ntitle: T\n---\n\n![fig](images/f.png)\n\n::: {.csv file=\"data/t.csv\"}\n:::\n\n"
            "\\irpanel{ir/x.csv}\n\nA missing one: nothing/there.csv, a URL https://x.org/a.png\n"
            "<!-- ir/unrelated.bin is only in a comment: unrelated.bin -->\n", encoding="utf-8")
        pdf = self.bundle(document, "referenced")
        attachments = pdfmd.read_pdf_attachments(pdf)
        self.assertEqual(sorted(name for name in attachments if name.startswith(pdfmd.EXTRA_PREFIX)),
                         ["files/data/t.csv", "files/images/f.png", "files/ir/x.csv"])
        out = self.restore(pdf)
        self.assertEqual((out / "images" / "f.png").read_bytes(), b"\x89PNG fake")
        self.assertEqual((out / "data" / "t.csv").read_bytes(), b"a,b\n1,2\n")
        self.assertFalse((out / "unrelated.bin").exists())
        self.assertTrue((out / "d.md").exists())

    def test_bundle_all_takes_the_folder_but_not_output_or_housekeeping(self):
        for name in ("notes/a.txt", "photos/p.jpg", ".hidden/x", ".backups/old.md", "build.aux", "d.pdf.bak"):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(b"x")
        (self.root / "notes" / "n.md").write_text("Note <!-- private -->.\n", encoding="utf-8")
        document = self.root / "d.md"
        document.write_text("Text.\n", encoding="utf-8")
        pdf = self.bundle(document, "all")
        stored = sorted(name[len(pdfmd.EXTRA_PREFIX):] for name in pdfmd.read_pdf_attachments(pdf)
                        if name.startswith(pdfmd.EXTRA_PREFIX))
        self.assertEqual(stored, ["d.pdf.bak", "notes/a.txt", "notes/n.md", "photos/p.jpg"])
        out = self.restore(pdf)
        self.assertEqual((out / "notes" / "n.md").read_text(encoding="utf-8"), "Note.\n")   # stripped like the source

    def test_bundle_off_and_the_size_limit(self):
        (self.root / "f.png").write_bytes(b"x" * 2048)
        document = self.root / "d.md"
        document.write_text("![f](f.png)\n", encoding="utf-8")
        self.assertNotIn("files/f.png", pdfmd.read_pdf_attachments(self.bundle(document, "off")))
        document.write_text("---\npdfmd-options:\n  bundle: true\n  bundle-max-mb: 0.001\n---\n\n![f](f.png)\n",
                            encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()) as warned:
            pdf = self.attach(document)
        self.assertIn("over the", warned.getvalue())
        self.assertNotIn("files/f.png", pdfmd.read_pdf_attachments(pdf))

    def test_an_edited_extra_is_reported(self):
        (self.root / "f.png").write_bytes(b"original")
        document = self.root / "d.md"
        document.write_text("![f](f.png)\n", encoding="utf-8")
        pdf = self.bundle(document, "referenced")
        attachments = pdfmd.read_pdf_attachments(pdf)
        attachments["files/f.png"] = b"edited"
        tampered = blank_pdf(self.root / "t.pdf")
        pdfmd.write_pdf_attachments(tampered, attachments)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            status = pdfmd.restore_from_pdf(tampered, self.root / "t-out")
        self.assertEqual(status, 1)

    def test_never_overwrites(self):
        document = self.root / "d.md"
        document.write_text("Text.\n", encoding="utf-8")
        pdf = self.attach(document)
        out = self.restore(pdf)
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
            pdfmd.restore_from_pdf(pdf, out)
        self.assertIn("nothing was written", str(caught.exception))

    def test_a_pdf_without_a_source_says_so(self):
        pdf = blank_pdf(self.root / "plain.pdf")
        with self.assertRaises(SystemExit) as caught:
            pdfmd.restore_from_pdf(pdf, self.root / "x")
        self.assertIn("carries no pdfmd source", str(caught.exception))

    def test_edited_source_is_reported(self):
        document = self.root / "d.md"
        document.write_text("Text.\n", encoding="utf-8")
        pdf = self.attach(document)
        attachments = pdfmd.read_pdf_attachments(pdf)
        tampered = blank_pdf(self.root / "t.pdf")
        pdfmd.write_pdf_attachments(tampered, {
            pdfmd.ATTACH_MANIFEST: attachments[pdfmd.ATTACH_MANIFEST],
            pdfmd.ATTACH_SOURCE: attachments[pdfmd.ATTACH_SOURCE] + b"\nextra\n"})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            status = pdfmd.restore_from_pdf(tampered, self.root / "t-out")
        self.assertEqual(status, 1)

    def test_paths_leaving_the_folder_are_never_written(self):
        self.assertIsNone(pdfmd.restore_target_name("../evil.md"))
        self.assertIsNone(pdfmd.restore_target_name("/abs/evil.md"))
        self.assertIsNone(pdfmd.restore_target_name("a/../../evil.md"))
        self.assertIsNone(pdfmd.restore_target_name("C:/evil.md"))
        self.assertEqual(str(pdfmd.restore_target_name("metadata/a.yaml")), "metadata/a.yaml")
        document = self.root / "d.md"
        document.write_text("Text.\n", encoding="utf-8")
        pdf = self.attach(document)
        attachments = pdfmd.read_pdf_attachments(pdf)
        manifest = json.loads(attachments[pdfmd.ATTACH_MANIFEST])
        manifest["name"] = "../../escape.md"
        hostile = blank_pdf(self.root / "hostile.pdf")
        pdfmd.write_pdf_attachments(hostile, {
            pdfmd.ATTACH_MANIFEST: json.dumps(manifest).encode(),
            pdfmd.ATTACH_SOURCE: attachments[pdfmd.ATTACH_SOURCE]})
        out = self.root / "h-out"
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.restore_from_pdf(hostile, out)
        self.assertFalse((self.root.parent / "escape.md").exists())
        self.assertTrue((out / "document.md").exists())

    def test_cli_restore_list_and_flag(self):
        document = self.root / "d.md"
        document.write_text("Text <!-- n -->.\n", encoding="utf-8")
        pdf = self.attach(document)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--restore", str(pdf), "--list"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("SOURCE    d.md", done.stdout)
        self.assertFalse((self.root / "d.restored").exists())
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--restore", str(pdf)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.root / "d.restored" / "d.md").read_text(encoding="utf-8"), "Text.\n")


if __name__ == "__main__":
    unittest.main()
