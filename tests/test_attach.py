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


class CommentKinds(unittest.TestCase):
    """Comments in a LaTeX preamble, a BibTeX file and a CSL style (v3.22.4)."""

    def test_tex_full_line_comments_go_with_their_line(self):
        text = "% a\n\\usepackage{x}\n% b\n\n% c\n\n\\input{y}\n"
        self.assertEqual(pdfmd.strip_tex_comments(text), "\\usepackage{x}\n\n\\input{y}\n")

    def test_tex_trailing_comment_keeps_a_bare_percent(self):
        # the % swallows the line break: removing it would put a space into the output
        self.assertEqual(pdfmd.strip_tex_comments("\\newcommand{\\a}{%\n  b} % why\n"),
                         "\\newcommand{\\a}{%\n  b} %\n")

    def test_tex_escaped_percent_verb_url_and_verbatim_are_text(self):
        text = ("50\\% of it\n\\verb|a % b| then % c\n\\url{http://x/%20y} % z\n"
                "\\begin{verbatim}\n% keep\n\\end{verbatim}\n% gone\n")
        self.assertEqual(pdfmd.strip_tex_comments(text),
                         "50\\% of it\n\\verb|a % b| then %\n\\url{http://x/%20y} %\n"
                         "\\begin{verbatim}\n% keep\n\\end{verbatim}\n")

    def test_tex_magic_comments_stay(self):
        text = "% !TEX program = lualatex\n% note\nx\n"
        self.assertEqual(pdfmd.strip_tex_comments(text), "% !TEX program = lualatex\nx\n")

    def test_tex_is_idempotent(self):
        once = pdfmd.strip_tex_comments("a % b\n% c\n\\x{%\n}\n")
        self.assertEqual(pdfmd.strip_tex_comments(once), once)

    def test_csl_comments(self):
        self.assertEqual(pdfmd.strip_xml_comments("<a>\n  <!-- x\n y -->\n <b/> <!-- z --></a>"), "<a>\n <b/> </a>")

    BIB = ("% header\n@string{j = \"J. Chem.\"}\n\n% section\n@article{a1,\n  title = {Foo @ bar % not a comment},\n"
           "  journal = j,\n  crossref = {c1},\n}\n@book{c1, title={Whole}}\n@book{dead, title={Dead}}\n"
           "@comment{ignore}\n% tail\n")

    def test_bibliography_keeps_the_cited_entries_and_what_they_cross_reference(self):
        text, kept, total = pdfmd.filter_bibliography(self.BIB, {"a1"}, True)
        self.assertEqual((kept, total), (2, 3))
        self.assertIn("@string{j", text)
        self.assertIn("@book{c1", text)
        self.assertNotIn("dead", text)
        self.assertIn("% not a comment", text)             # inside an entry it is text
        self.assertNotIn("header", text)
        self.assertNotIn("@comment", text)

    def test_bibliography_unpruned_unstripped_is_byte_identical(self):
        self.assertEqual(pdfmd.filter_bibliography(self.BIB, None, False)[0], self.BIB)

    def test_bibliography_can_keep_its_comments_and_still_prune(self):
        text = pdfmd.filter_bibliography(self.BIB, {"a1"}, False)[0]
        self.assertIn("% section", text)
        self.assertNotIn("dead", text)

    def test_cited_keys(self):
        self.assertEqual(pdfmd.used_citation_keys(["see [@Harris2010, p. 5; -@b_2:x], a@b.com, \\parencite[x]{k3,k4}"]),
                         {"harris2010", "b_2:x", "k3", "k4"})
        self.assertIsNone(pdfmd.used_citation_keys(["nocite: '@*'"]))

    def test_policy(self):
        policy = pdfmd.parse_comment_policy
        self.assertEqual(policy(None, True).kinds(), frozenset(pdfmd.COMMENT_KINDS))
        self.assertEqual(policy("tex, bib", True).kinds(), {"preamble", "bibliography"})
        self.assertEqual(policy({"bibliography": False, "markdown": False}, True).kinds(), {"csl", "preamble"})
        self.assertEqual(policy({"preamble": True}, False).kinds(), {"preamble"})
        self.assertEqual(policy(False, True).kinds(), frozenset())


@unittest.skipIf(pypdf is None, "pypdf not installed")
class AttachedKinds(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)
        (self.root / "refs.bib").write_text(
            "% notes\n@article{used1, title={One}}\n@article{dead1, title={Two}}\n", encoding="utf-8")
        (self.root / "preamble.tex").write_text("% style\n\\usepackage{x} % why\n", encoding="utf-8")
        self.document = self.root / "r.md"

    def attach(self, front: str, **flags) -> dict:
        self.document.write_text(f"---\ntitle: T\nbibliography: refs.bib\n{front}---\n\nSee [@used1]. <!-- n -->\n",
                                 encoding="utf-8")
        pdf = blank_pdf(self.root / "r.pdf")
        saved = {name: getattr(pdfmd, name) for name in flags}
        try:
            for name, value in flags.items():
                setattr(pdfmd, name, value)
            with contextlib.redirect_stdout(io.StringIO()):
                pdfmd.attach_source_after_success(self.document, pdf, [], [], [self.root / "preamble.tex"], None, False)
        finally:
            for name, value in saved.items():
                setattr(pdfmd, name, value)
        return {name: b"".join(items) if len(items) > 1 else items[0]
                for name, items in pypdf.PdfReader(pdf).attachments.items()}

    def test_default_prunes_the_bibliography_and_strips_every_kind(self):
        attached = self.attach("")
        source = attached["pdfmd-source.md"].decode()
        self.assertIn("used1", source)
        self.assertNotIn("dead1", source)
        self.assertNotIn("notes", source)
        self.assertNotIn("why", source)
        self.assertNotIn("<!-- n -->", source)
        manifest = json.loads(attached["pdfmd-manifest.json"])
        self.assertEqual(manifest["bibliography"], ["refs.bib: 1 of 2 entries"])
        self.assertIn("preamble", manifest["comments_stripped"])

    def test_the_whole_bibliography_and_chosen_comments_on_request(self):
        attached = self.attach("pdfmd-options:\n  attach-bibliography: all\n  strip-comments:\n"
                               "    bibliography: false\n    markdown: false\n")
        source = attached["pdfmd-source.md"].decode()
        self.assertIn("dead1", source)
        self.assertIn("% notes", source)
        self.assertIn("<!-- n -->", source)
        self.assertNotIn("why", source)                    # the preamble still loses its comments

    def test_command_line_kinds(self):
        attached = self.attach("", KEEP_KINDS_CLI=frozenset({"preamble"}), BIB_ATTACH_CLI="all")
        source = attached["pdfmd-source.md"].decode()
        self.assertIn("why", source)
        self.assertIn("dead1", source)

    def test_attachments_are_deflated(self):
        (self.root / "big.bib").write_text("@article{used1, title={%s}}\n" % ("word " * 4000), encoding="utf-8")
        self.document.write_text("---\nbibliography: big.bib\n---\n\n[@used1]\n", encoding="utf-8")
        pdf = blank_pdf(self.root / "r.pdf")
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.attach_source_after_success(self.document, pdf, [], [], [], None, False)
        self.assertLess(pdf.stat().st_size, 8000)
        attached = pypdf.PdfReader(pdf).attachments
        self.assertGreater(len(attached["pdfmd-source.md"][0]), 20000)


@unittest.skipIf(pypdf is None, "pypdf not installed")
class BundleReach(unittest.TestCase):
    """What a bundle follows: files named by files it stores, chapters of a report, and the
    user's own TeX tree (v3.22.5)."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)
        self.saved = pdfmd.BUNDLE_CLI
        self.addCleanup(setattr, pdfmd, "BUNDLE_CLI", self.saved)

    def attach(self, document: Path, parts=(), preamble=(), report=False, base=None, **flags) -> dict:
        pdf = blank_pdf(document.with_suffix(".pdf"))
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.attach_source_after_success(document, pdf, list(parts), [], list(preamble), None, False,
                                              report=report, base=base)
        return {name: b"".join(items) if len(items) > 1 else items[0]
                for name, items in pypdf.PdfReader(pdf).attachments.items()}

    def test_a_stored_tex_file_is_read_for_the_files_it_inputs(self):
        (self.root / "tex").mkdir()
        (self.root / "tex" / "fig.tex").write_text("\\input{tex/raw}\n", encoding="utf-8")
        (self.root / "tex" / "raw.tex").write_text("\\addplot table {data/x.csv};\n", encoding="utf-8")
        (self.root / "data").mkdir()
        (self.root / "data" / "x.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        document = self.root / "r.md"
        document.write_text("---\ntitle: T\n---\n\n```{=latex}\n\\input{tex/fig}\n```\n", encoding="utf-8")
        pdfmd.BUNDLE_CLI = "referenced"
        attached = self.attach(document)
        self.assertEqual({name for name in attached if name.startswith("files/")},
                         {"files/tex/fig.tex", "files/tex/raw.tex", "files/data/x.csv"})

    def test_report_chapters_keep_their_front_matter_and_places(self):
        (self.root / "ch").mkdir()
        first, second = self.root / "ch" / "one.md", self.root / "ch" / "two.md"
        first.write_text("---\ntitle: Book\nchapter: 1\n---\n\n# One <!-- n -->\n\nText.\n", encoding="utf-8")
        second.write_text("---\nchapter: 2\n---\n\n# Two\n\nMore.\n", encoding="utf-8")
        attached = self.attach(first, parts=[second], report=True, base=self.root)
        manifest = json.loads(attached["pdfmd-manifest.json"])
        self.assertEqual(manifest["mode"], "report")
        self.assertEqual([chunk["path"] for chunk in manifest["chunks"]], ["ch/one.md", "ch/two.md"])
        out = self.root / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.restore_from_pdf(self.root / "ch" / "one.pdf", out)
        self.assertIn("chapter: 1", (out / "ch" / "one.md").read_text(encoding="utf-8"))
        self.assertNotIn("<!--", (out / "ch" / "one.md").read_text(encoding="utf-8"))
        self.assertEqual((out / "ch" / "two.md").read_text(encoding="utf-8"),
                         "---\nchapter: 2\n---\n\n# Two\n\nMore.\n")

    @unittest.skipIf(not pdfmd.which("kpsewhich"), "kpsewhich not installed")
    def test_the_users_own_tex_tree_is_recorded_and_stored_on_request(self):
        tree = self.root / "texmf"
        (tree / "tex" / "latex" / "mystyle").mkdir(parents=True)
        (tree / "tex" / "latex" / "mystyle" / "mystyle.sty").write_text(
            "\\ProvidesPackage{mystyle}[2026/01/01 v1.2 My style]\n\\input{mylib}\n", encoding="utf-8")
        (tree / "tex" / "latex" / "mystyle" / "mylib.tex").write_text("\\def\\x{1}\n", encoding="utf-8")
        work = self.root / "work"
        work.mkdir()
        (work / "preamble.tex").write_text("\\usepackage{mystyle}\n\\input{mylib}\n", encoding="utf-8")
        document = work / "r.md"
        document.write_text("---\ntitle: T\n---\n\nHi.\n", encoding="utf-8")
        old = pdfmd.os.environ.get("TEXMFHOME")
        pdfmd.os.environ["TEXMFHOME"] = str(tree)
        pdfmd.find_in_tex_tree.cache_clear()
        pdfmd.tex_distribution_roots.cache_clear()
        try:
            pdfmd.BUNDLE_CLI = "referenced"
            plain = self.attach(document, preamble=[work / "preamble.tex"])
            manifest = json.loads(plain["pdfmd-manifest.json"])
            needs = {item["name"]: item for item in manifest["requirements"]["tex"]}
            self.assertEqual(needs["mystyle.sty"]["version"], "2026/01/01 v1.2 My style")
            self.assertFalse(needs["mystyle.sty"]["stored"])
            self.assertTrue(needs["mylib.tex"]["stored"])             # an \input is data: stored with a bundle
            self.assertIn("files/mylib.tex", plain)
            self.assertNotIn("files/mystyle.sty", plain)
            saved = pdfmd.BUNDLE_PACKAGES_CLI
            pdfmd.BUNDLE_PACKAGES_CLI = True
            try:
                full = self.attach(document, preamble=[work / "preamble.tex"])
            finally:
                pdfmd.BUNDLE_PACKAGES_CLI = saved
            self.assertIn("files/mystyle.sty", full)
        finally:
            if old is None:
                pdfmd.os.environ.pop("TEXMFHOME", None)
            else:
                pdfmd.os.environ["TEXMFHOME"] = old
            pdfmd.find_in_tex_tree.cache_clear()
            pdfmd.tex_distribution_roots.cache_clear()


def png_rows(data: bytes) -> tuple[tuple[int, int, int, int], bytes]:
    """(width, height, depth, colour type) and the unfiltered scanlines of a PNG made by encode_png."""
    import struct
    import zlib
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    position, header, idat = 8, None, b""
    while position < len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        body = data[position + 8:position + 8 + length]
        assert zlib.crc32(kind + body) & 0xFFFFFFFF == struct.unpack(">I", data[position + 8 + length:position + 12 + length])[0]
        if kind == b"IHDR":
            header = struct.unpack(">IIBB", body[:10])
        elif kind == b"IDAT":
            idat += body
        position += 12 + length
    raw = zlib.decompress(idat)
    stride = len(raw) // header[1]
    return header, b"".join(raw[line * stride + 1:(line + 1) * stride] for line in range(header[1]))


MINI_JPEG = b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x02\x00\x03\x01\x01\x11\x00\xff\xd9"      # a 3x2 SOF0 header, enough to size


@unittest.skipIf(pypdf is None, "pypdf not installed")
class PicturesFromThePdf(unittest.TestCase):
    """The pictures a plain attach does not store come out of the PDF itself (v3.22.6)."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)

    def pdf_with(self, name: str, pictures: list) -> Path:
        from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject,
                                   NumberObject)
        writer = pypdf.PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        xobjects = DictionaryObject()
        for index, picture in enumerate(pictures):
            stream = DecodedStreamObject()
            stream.set_data(picture["data"])
            stream[NameObject("/Type")] = NameObject("/XObject")
            if picture["kind"] == "form":
                stream[NameObject("/Subtype")] = NameObject("/Form")
                stream[NameObject("/BBox")] = ArrayObject(FloatObject(value) for value in picture["bbox"])
            else:
                stream[NameObject("/Subtype")] = NameObject("/Image")
                stream[NameObject("/Width")] = NumberObject(picture["width"])
                stream[NameObject("/Height")] = NumberObject(picture["height"])
                stream[NameObject("/BitsPerComponent")] = NumberObject(8)
                stream[NameObject("/ColorSpace")] = NameObject(picture.get("space", "/DeviceRGB"))
                if picture.get("filter"):
                    stream[NameObject("/Filter")] = NameObject(picture["filter"])
            xobjects[NameObject(f"/Im{index}")] = writer._add_object(stream)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): xobjects})
        path = self.root / name
        with path.open("wb") as handle:
            writer.write(handle)
        return path

    def test_png_encoder_writes_what_it_was_given(self):
        rows = bytes(range(12))                           # 2x2 RGB
        header, back = png_rows(pdfmd.encode_png(2, 2, 8, 2, rows))
        self.assertEqual(header, (2, 2, 8, 2))
        self.assertEqual(back, rows)

    def test_picture_sizes(self):
        (self.root / "a.png").write_bytes(pdfmd.encode_png(3, 2, 8, 2, bytes(18)))
        (self.root / "b.jpg").write_bytes(MINI_JPEG)
        (self.root / "c.svg").write_text('<svg width="100mm" height="2in" viewBox="0 0 1 1"></svg>', encoding="utf-8")
        (self.root / "d.svg").write_text('<svg viewBox="0 0 40 20"></svg>', encoding="utf-8")
        size = pdfmd.file_picture_size
        self.assertEqual(size(self.root / "a.png"), ("raster", 3, 2))
        self.assertEqual(size(self.root / "b.jpg"), ("raster", 3, 2))
        kind, width, height = size(self.root / "c.svg")
        self.assertEqual(kind, "vector")
        self.assertAlmostEqual(width, 283.46, places=1)
        self.assertAlmostEqual(height, 144.0, places=1)
        self.assertEqual(size(self.root / "d.svg"), ("vector", 30.0, 15.0))
        self.assertIsNone(size(self.root / "missing.png"))

    def test_attach_then_restore_gives_pictures_back_without_a_bundle(self):
        import zlib
        (self.root / "fig").mkdir()
        pixels = bytes((7 * index) % 256 for index in range(4 * 3 * 3))        # 4x3 RGB
        (self.root / "fig" / "p.png").write_bytes(pdfmd.encode_png(4, 3, 8, 2, pixels))
        (self.root / "fig" / "j.jpg").write_bytes(MINI_JPEG)
        (self.root / "fig" / "v.svg").write_text('<svg width="100" height="60"></svg>', encoding="utf-8")
        document = self.root / "r.md"
        document.write_text("---\ntitle: T\n---\n\n![a](fig/p.png) ![b](fig/j.jpg) ![c](fig/v.svg)\n", encoding="utf-8")
        pdf = self.pdf_with("r.pdf", [
            {"kind": "image", "width": 4, "height": 3, "data": zlib.compress(pixels), "filter": "/FlateDecode"},
            {"kind": "image", "width": 3, "height": 2, "data": MINI_JPEG, "filter": "/DCTDecode"},
            {"kind": "form", "bbox": [0, 0, 75, 45], "data": b"0 0 1 rg 0 0 75 45 re f"}])
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.attach_source_after_success(document, pdf, [], [], [], None, False)
        manifest = json.loads(pypdf.PdfReader(pdf).attachments["pdfmd-manifest.json"][0])
        self.assertTrue(all(image.get("pdf") for image in manifest["images"]), manifest["images"])
        out = self.root / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pdfmd.restore_from_pdf(pdf, out), 0)
        self.assertEqual(png_rows((out / "fig" / "p.png").read_bytes()), ((4, 3, 8, 2), pixels))
        self.assertEqual((out / "fig" / "j.jpg").read_bytes(), MINI_JPEG)                  # byte for byte
        figure = pypdf.PdfReader(out / "fig" / "v.pdf")
        self.assertEqual((float(figure.pages[0].mediabox.width), float(figure.pages[0].mediabox.height)), (75.0, 45.0))
        self.assertFalse((out / "fig" / "v.svg").exists())
        self.assertIn("![c](fig/v.pdf)", (out / "r.md").read_text(encoding="utf-8"))      # the Markdown follows

    def test_a_bundle_stores_the_files_and_extracts_nothing(self):
        (self.root / "p.png").write_bytes(pdfmd.encode_png(1, 1, 8, 2, b"\x01\x02\x03"))
        document = self.root / "r.md"
        document.write_text("---\ntitle: T\n---\n\n![a](p.png)\n", encoding="utf-8")
        import zlib
        pdf = self.pdf_with("r.pdf", [{"kind": "image", "width": 1, "height": 1, "data": zlib.compress(b"\x01\x02\x03"),
                                        "filter": "/FlateDecode"}])
        saved = pdfmd.BUNDLE_CLI
        pdfmd.BUNDLE_CLI = "referenced"
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                pdfmd.attach_source_after_success(document, pdf, [], [], [], None, False)
        finally:
            pdfmd.BUNDLE_CLI = saved
        manifest = json.loads(pypdf.PdfReader(pdf).attachments["pdfmd-manifest.json"][0])
        self.assertNotIn("pdf", manifest["images"][0])
        self.assertIn("files/p.png", pypdf.PdfReader(pdf).attachments)

    def test_a_picture_that_is_not_in_the_pdf_is_only_recorded(self):
        (self.root / "gone.png").write_bytes(pdfmd.encode_png(5, 5, 8, 2, bytes(75)))
        document = self.root / "r.md"
        document.write_text("---\ntitle: T\n---\n\n![a](gone.png)\n", encoding="utf-8")
        pdf = blank_pdf(self.root / "r.pdf")
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.attach_source_after_success(document, pdf, [], [], [], None, False)
        out = self.root / "out"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            pdfmd.restore_from_pdf(pdf, out)
        self.assertIn("recorded, not in the PDF", buffer.getvalue())
        self.assertFalse((out / "gone.png").exists())

    def test_rewrite_image_paths(self):
        text = "![a](x/v.svg) ![b](<x/v.svg> \"t\") <img src=\"x/v.svg\"> [link](x/v.svg) ![c](x/other.svg)\n"
        self.assertEqual(pdfmd.rewrite_image_paths(text, {"x/v.svg": "x/v.pdf"}),
                         "![a](x/v.pdf) ![b](<x/v.pdf> \"t\") <img src=\"x/v.pdf\"> [link](x/v.svg) ![c](x/other.svg)\n")
