"""The hybrid PDF (--hybrid) and the `files` embed kind (--embed-metadata files)."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

try:
    import pypdf
except ImportError:  # pragma: no cover
    pypdf = None

PANDOC = shutil.which("pandoc")
SOFFICE = pdfmd.resolve_soffice()
LATEX = shutil.which("lualatex") or shutil.which("xelatex") or shutil.which("pdflatex")


def png(width: int = 40, height: int = 20) -> bytes:
    raw = b"".join(b"\x00" + bytes([200, 50, 50]) * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def blank_pdf(path: Path) -> None:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(200, 200)
    with path.open("wb") as handle:
        writer.write(handle)


class Env(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-embedding-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "APPDATA": str(self.directory / "xdg"), "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}

    def run_pdfmd(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=cwd or self.directory,
                              capture_output=True, text=True, env=self.env)


@unittest.skipUnless(pypdf, "needs pypdf")
class HybridStructure(Env):
    def test_the_attachment_is_what_libreoffice_writes(self):
        pdf = self.directory / "a.pdf"
        blank_pdf(pdf)
        self.assertTrue(pdfmd.attach_hybrid(pdf, b"PK-fake-odt", "odt"))
        reader = pypdf.PdfReader(pdf)
        self.assertEqual(list(reader.attachments), ["Original.odt"])
        [entry] = reader.trailer["/Root"]["/Names"]["/EmbeddedFiles"]["/Names"][1::2]
        filespec = entry.get_object()
        self.assertEqual(str(filespec["/Desc"]), "Embedded original document of this PDF file")
        self.assertEqual(str(filespec["/UF"]), "Original.odt")
        stream = filespec["/EF"]["/F"].get_object()
        self.assertEqual(str(stream["/Subtype"]), "/application/vnd.oasis.opendocument.text")
        self.assertEqual(reader.attachments["Original.odt"][0], b"PK-fake-odt")

    def test_a_pdf_that_has_one_is_left_alone_and_other_attachments_are_kept(self):
        pdf = self.directory / "a.pdf"
        blank_pdf(pdf)
        pdfmd.write_pdf_attachments(pdf, {"pdfmd-source.md": b"text"})
        self.assertTrue(pdfmd.attach_hybrid(pdf, b"one", "odt"))
        self.assertFalse(pdfmd.attach_hybrid(pdf, b"two", "odt"))
        attachments = pypdf.PdfReader(pdf).attachments
        self.assertEqual(sorted(attachments), ["Original.odt", "pdfmd-source.md"])
        self.assertEqual(attachments["Original.odt"][0], b"one")

    def test_restore_gives_back_the_odf_file_of_a_pdf_that_has_no_pdfmd_source(self):
        pdf = self.directory / "report.pdf"
        blank_pdf(pdf)
        pdfmd.attach_hybrid(pdf, b"PK-fake", "odt")
        done = self.run_pdfmd("--restore", "report.pdf")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((self.directory / "report.restored" / "report.odt").read_bytes(), b"PK-fake")
        again = self.run_pdfmd("--restore", "report.pdf")
        self.assertNotEqual(again.returncode, 0)                          # it never overwrites


@unittest.skipUnless(pypdf and SOFFICE and PANDOC and LATEX, "needs pypdf, LibreOffice, Pandoc and a LaTeX engine")
@unittest.skipIf(os.environ.get("CODEX_SANDBOX"), "LibreOffice crashes under the Codex sandbox")
class HybridEndToEnd(Env):
    def test_a_markdown_pdf_opens_in_libreoffice_as_its_editable_document(self):
        (self.directory / "a.md").write_text("---\ntitle: Hybrid Doc\n---\n\nHello **world** from the source.\n", encoding="utf-8")
        done = self.run_pdfmd("a.md", "--hybrid")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("HYBRID", done.stdout)
        self.assertEqual(list(pypdf.PdfReader(self.directory / "a.pdf").attachments), ["Original.odt"])
        scratch = self.directory / "lo"
        subprocess.run([SOFFICE, "--headless", "--norestore", f"-env:UserInstallation={(scratch / 'profile').as_uri()}",
                        "--convert-to", "txt:Text", "--outdir", str(scratch), str(self.directory / "a.pdf")],
                       capture_output=True, text=True)
        self.assertIn("Hello world from the source.", (scratch / "a.txt").read_text(encoding="utf-8-sig"))

    def test_a_docx_goes_through_libreoffice_and_carries_its_odt(self):
        (self.directory / "b.md").write_text("---\ntitle: T\n---\n\nSome words here.\n", encoding="utf-8")
        subprocess.run([PANDOC, "b.md", "-o", "b.docx"], cwd=self.directory, check=True)
        done = self.run_pdfmd("b.docx", "--hybrid")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(list(pypdf.PdfReader(self.directory / "b.pdf").attachments), ["Original.odt"])

    def test_without_the_flag_nothing_is_attached(self):
        (self.directory / "c.md").write_text("---\ntitle: T\n---\n\nWords.\n", encoding="utf-8")
        self.assertEqual(self.run_pdfmd("c.md").returncode, 0)
        self.assertEqual(list(pypdf.PdfReader(self.directory / "c.pdf").attachments), [])

    def test_the_document_can_ask_for_it(self):
        (self.directory / "d.md").write_text("---\ntitle: T\npdfmd-options:\n  hybrid: true\n---\n\nWords.\n", encoding="utf-8")
        self.assertEqual(self.run_pdfmd("d.md").returncode, 0)
        self.assertEqual(list(pypdf.PdfReader(self.directory / "d.pdf").attachments), ["Original.odt"])
        self.assertEqual(self.run_pdfmd("d.md", "--no-hybrid", "-o", "e.pdf").returncode, 0)
        self.assertEqual(list(pypdf.PdfReader(self.directory / "e.pdf").attachments), [])


class FileBlocks(unittest.TestCase):
    def test_text_and_binary_files_round_trip_through_a_block(self):
        text = "name,qty\nPen,3\n"
        binary = png()
        for data in (text.encode(), binary, b"", "no final newline".encode()):
            block = pdfmd.render_embedded_file("x.dat", "dir/x.dat", data)
            [parsed] = pdfmd.parse_embedded_blocks(block)
            self.assertEqual(parsed["bytes"], data, block[:80])
            self.assertEqual(parsed["declared"], parsed["sha256"])
            self.assertEqual(parsed["path"], "dir/x.dat")
        self.assertNotIn("base64", pdfmd.render_embedded_file("t.csv", "t.csv", text.encode()))
        self.assertIn("encoding: base64", pdfmd.render_embedded_file("p.png", "p.png", binary))

    def test_an_edited_file_no_longer_matches_its_hash(self):
        block = pdfmd.render_embedded_file("t.csv", "t.csv", b"a,b\n1,2\n").replace("1,2", "1,3")
        [parsed] = pdfmd.parse_embedded_blocks(block)
        self.assertNotEqual(parsed["declared"], parsed["sha256"])

    def test_all_means_every_kind_and_true_means_the_default_ones(self):
        self.assertIn("files", pdfmd.parse_embed_option("all")[0])
        self.assertNotIn("files", pdfmd.parse_embed_option(True)[0])
        self.assertIn("hst", pdfmd.parse_embed_option(True)[0])
        self.assertIn("files", pdfmd.parse_embed_option({"files": True})[0])
        self.assertIn("files", pdfmd.parse_embed_option(["files", "metadata"])[0])

    def test_file_payload_round_trips_exact_bytes(self):
        for data in (b"x\n\n", b"\n", b" \t\n", b"x\r\n\r\n", b"\r\n", b"", b"x\n", b"x\r\n",
                     b"no newline", b"x\r\ny\n", b"x\x00y", b"\xff"):
            with self.subTest(data=data):
                block = pdfmd.render_embedded_file("data.txt", "data.txt", data)
                parsed = pdfmd.parse_embedded_blocks(block)[0]
                self.assertEqual(parsed["bytes"], data)
                self.assertEqual(parsed["declared"], parsed["sha256"])
                if data in (b"x\n", b"x\r\n", b""):
                    self.assertNotIn("encoding: base64", block)


REFERENCES = ("@book{knuth,\n  author = {Donald E. Knuth},\n  title = {The TeXbook},\n  publisher = {Addison-Wesley},\n"
              "  year = {1984}\n}\n\n@book{lamport,\n  author = {Leslie Lamport},\n  title = {LaTeX},\n"
              "  publisher = {Addison-Wesley},\n  year = {1994}\n}\n\n@article{other,\n  author = {A. Nother},\n"
              "  title = {Unused},\n  journal = {J},\n  year = {2000}\n}\n")


@unittest.skipUnless(PANDOC, "needs Pandoc")
class AssembledBibliography(Env):
    """v3.33.57: --assemble-only (and --merge) embedded the whole bibliography, where --keep-source and --attach-source keep
    only the entries the text cites; now under the same setting (--attach-bibliography, pdfmd-options.attach-bibliography)."""

    def setUp(self):
        super().setUp()
        (self.directory / "refs.bib").write_text(REFERENCES, encoding="utf-8")
        self.document = self.directory / "doc.md"
        self.document.write_text("---\ntitle: Cites\nbibliography: refs.bib\n---\n\nAs shown by @knuth, it is hard.\n",
                                 encoding="utf-8")

    def entries(self, *args: str) -> list[str]:
        done = self.run_pdfmd("doc.md", *args, "-o", "out.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (self.directory / "out.md").read_text(encoding="utf-8")
        return [line.split("{")[1].rstrip(",") for line in text.splitlines() if line.startswith("@")]

    def test_only_the_cited_entries(self):
        self.assertEqual(self.entries("--merge"), ["knuth"])
        self.assertEqual(self.entries("--assemble-only", "--embed-metadata", "bibliography"), ["knuth"])
        self.assertEqual(self.entries("--merge", "--attach-bibliography", "all"), ["knuth", "lamport", "other"])
        self.assertEqual((self.directory / "refs.bib").read_text(encoding="utf-8"), REFERENCES)      # the author's own file
        self.document.write_text(self.document.read_text(encoding="utf-8").replace(
            "bibliography: refs.bib\n", "bibliography: refs.bib\npdfmd-options:\n  attach-bibliography: all\n"),
            encoding="utf-8")
        self.assertEqual(self.entries("--merge"), ["knuth", "lamport", "other"])

    def test_the_assembled_file_builds_alone_with_its_citation(self):
        self.entries("--merge")
        away = self.directory / "away"
        away.mkdir()
        shutil.move(str(self.directory / "out.md"), str(away / "out.md"))
        done = self.run_pdfmd("out.md", "--to", "html", "-o", "out.html", cwd=away)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        page = (away / "out.html").read_text(encoding="utf-8")
        self.assertIn("Knuth", page)
        self.assertIn("1984", page)
        self.assertNotIn("Lamport", page)


class FilesEndToEnd(Env):
    def make_source(self):
        source = self.directory / "src"
        (source / "tables").mkdir(parents=True)
        (source / "img").mkdir()
        (source / "tables" / "stock.csv").write_text("name,qty\nPen,3\nInk,12\n", encoding="utf-8")
        (source / "img" / "red.png").write_bytes(png())
        (source / "img" / "raw.png").write_bytes(png(60, 30))
        (source / "doc.md").write_text(
            "---\ntitle: Embedded\n---\n\n::: {.csv file=\"tables/stock.csv\" caption=\"Stock\"}\n:::\n\n"
            "![red](img/red.png){width=2cm}\n\nRaw LaTeX: \\includegraphics[width=2cm]{img/raw.png}\n", encoding="utf-8")
        return source

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_assemble_and_unpack_keep_trailing_bytes(self):
        payloads = [b"x\n\n", b"\n", b" \t\n", b"x\r\n\r\n", b"\r\n", b"x\r\n", b"x\n"]
        source = self.directory / "source"
        source.mkdir()
        for index, data in enumerate(payloads):
            (source / f"file{index}.tex").write_bytes(data)
        (source / "doc.md").write_text("# Test\n\n```{=latex}\n" + "".join(
            f"\\input{{file{index}.tex}}\n" for index in range(len(payloads))) + "```\n", encoding="utf-8")
        env = dict(self.env)
        for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
            env[key] = str(self.directory / key)
        def run(*args):
            return subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *args], cwd=source,
                                  env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        done = run("doc.md", "--assemble-only", "--embed-metadata", "files", "-o", "all.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        restored = self.directory / "restored"
        done = run("all.md", "--unpack", "-o", str(restored))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for index, data in enumerate(payloads):
            self.assertEqual((restored / f"file{index}.tex").read_bytes(), data)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_files_are_not_embedded_unless_asked_and_are_with_files_or_all(self):
        source = self.make_source()
        self.assertEqual(self.run_pdfmd("doc.md", "--assemble-only", "--embed-metadata", "-o", "plain.md", cwd=source).returncode, 0)
        self.assertNotIn("type: file", (source / "plain.md").read_text(encoding="utf-8"))
        done = self.run_pdfmd("doc.md", "--assemble-only", "--embed-metadata", "files", "-o", "one.md", cwd=source)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (source / "one.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("type: file"), 3)
        for name in ("img/red.png", "img/raw.png", "tables/stock.csv"):
            self.assertIn(name, done.stdout)
        every = self.run_pdfmd("doc.md", "--assemble-only", "--embed-metadata", "all", "-o", "every.md", cwd=source)
        self.assertEqual((source / "every.md").read_text(encoding="utf-8").count("type: file"), 3, every.stdout)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_merge_is_assemble_only_with_everything_embedded(self):
        source = self.make_source()
        merged = self.run_pdfmd("doc.md", "--merge", cwd=source)
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        every = self.run_pdfmd("doc.md", "--assemble-only", "--embed-metadata", "all", "-o", "every.md", cwd=source)
        self.assertEqual(every.returncode, 0, every.stdout + every.stderr)
        text = (source / "doc.assembled.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("type: file"), 3)
        self.assertEqual(text, (source / "every.md").read_text(encoding="utf-8"))
        refused = self.run_pdfmd("doc.md", "--merge", "--no-embed-metadata", cwd=source)
        self.assertNotEqual(refused.returncode, 0)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_unpack_gives_back_the_same_bytes_and_slim_leaves_a_clean_document(self):
        source = self.make_source()
        self.run_pdfmd("doc.md", "--assemble-only", "--embed-metadata", "files", "-o", "one.md", cwd=source)
        done = self.run_pdfmd("--unpack", "one.md", "--slim", cwd=source)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for name in ("img/red.png", "img/raw.png", "tables/stock.csv"):
            self.assertEqual((source / "one.unpacked" / name).read_bytes(), (source / name).read_bytes(), name)
        self.assertNotIn("{=pdfmd}", (source / "one.md").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_a_bibliography_embedded_as_one_is_not_a_file_too(self):
        source = self.make_source()
        (source / "refs.bib").write_text("@article{smith2020,\n  author = {Smith, John},\n  title = {A paper},\n"
                                         "  journal = {J},\n  year = {2020}\n}\n", encoding="utf-8")
        doc = source / "doc.md"
        doc.write_text(doc.read_text(encoding="utf-8").replace("title: Embedded\n", "title: Embedded\nbibliography: refs.bib\n")
                       + "\nAs shown [@smith2020].\n", encoding="utf-8")
        every = self.run_pdfmd("doc.md", "--assemble-only", "--embed-metadata", "all", "-o", "every.md", cwd=source)
        self.assertEqual(every.returncode, 0, every.stdout + every.stderr)
        text = (source / "every.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("type: file"), 3, every.stdout)
        self.assertEqual(text.count("type: bibliography"), 1, every.stdout)
        named = next(line for line in every.stdout.splitlines() if line.startswith("EMBEDDED"))
        self.assertNotIn("refs.bib", next(part for part in named.split("; ") if "files " in part))   # not named among the files
        done = self.run_pdfmd("--unpack", "every.md", cwd=source)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((source / "every.unpacked" / "refs.bib").is_file())
        self.assertFalse((source / "every.unpacked" / "refs-2.bib").exists())
        files = self.run_pdfmd("doc.md", "--assemble-only", "--embed-metadata", "files", "-o", "files.md", cwd=source)
        self.assertEqual((source / "files.md").read_text(encoding="utf-8").count("type: file"), 4, files.stdout)

    @unittest.skipUnless(PANDOC and LATEX and shutil.which("pdfimages"), "needs Pandoc, a LaTeX engine and pdfimages")
    def test_the_single_file_builds_alone_with_its_table_and_both_images(self):
        source = self.make_source()
        self.run_pdfmd("doc.md", "--assemble-only", "--embed-metadata", "files", "-o", "one.md", cwd=source)
        alone = self.directory / "alone"
        alone.mkdir()
        shutil.copy(source / "one.md", alone / "one.md")
        done = self.run_pdfmd("one.md", "-e", Path(LATEX).stem, cwd=alone)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        listing = subprocess.run(["pdfimages", "-list", str(alone / "one.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertEqual(len([line for line in listing.splitlines()[2:] if line.strip()]), 2)       # a Markdown and a raw image
        text = subprocess.run(["pdftotext", str(alone / "one.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertIn("Stock", text)
        self.assertIn("Ink", text)


class UnpackPaths(Env):
    """Origin names and every final destination are untrusted, including preamble pieces."""

    def document(self, name: str, preamble: bool = False) -> Path:
        options = {"embedded": ["metadata"], "origin": {"files": {name: ["title"]}}}
        data = {"pdfmd-assembled": True, "title": "T", "pdfmd-options": options}
        if preamble:
            part = "% a preamble"
            options["origin"] = {"preamble": [{"name": name, "lines": 1, "sha256": pdfmd.sha256_text(part)}]}
            data["header-includes"] = part + "\n" + pdfmd.PREAMBLE_END_MARK
        path = self.directory / "doc.md"
        path.write_text("---\n" + pdfmd.yaml.safe_dump(data) + "---\n\nText.\n\n"
                        + pdfmd.render_embedded_file("valid.txt", "valid.txt", b"valid\n"), encoding="utf-8")
        return path

    def test_metadata_origins_are_refused_before_any_file_is_written(self):
        target = self.directory / "out"
        for name in ("../escape.yaml", "../new/escape.yaml", r"..\escape.yaml",
                     (self.directory / "absolute.yaml").as_posix()):
            with self.subTest(name=name):
                document = self.document(name)
                with self.assertRaises(SystemExit) as caught:
                    pdfmd.unpack_assembled(document, target, slim=True)
                self.assertIn(repr(name), str(caught.exception))
                self.assertIn("nothing was written", str(caught.exception))
                self.assertFalse(target.exists())
                self.assertTrue(pdfmd.is_assembled_text(document.read_text()))
                self.assertFalse((self.directory / "escape.yaml").exists())
                self.assertFalse((self.directory / "absolute.yaml").exists())

    def test_preamble_origins_are_refused_before_any_file_is_written(self):
        target = self.directory / "out"
        document = self.document("../escape.tex", preamble=True)
        with self.assertRaisesRegex(SystemExit, "escape.tex"):
            pdfmd.unpack_assembled(document, target)
        self.assertFalse(target.exists())
        self.assertFalse((self.directory / "escape.tex").exists())

    def test_unpack_refuses_a_symlink_escape_without_reading_or_writing_there(self):
        outside = self.directory / "outside"
        outside.mkdir()
        target = self.directory / "out"
        target.mkdir()
        (target / "sub").symlink_to(outside, target_is_directory=True)
        document = self.document("sub/escape.yaml")
        with self.assertRaisesRegex(SystemExit, "sub/escape.yaml"):
            pdfmd.unpack_assembled(document, target)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((target / "valid.txt").exists())

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_cli_unpack_refuses_metadata_and_preamble_origins(self):
        target = self.directory / "out"
        env = {**self.env, **{key: str(self.directory / key) for key in
                              ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")}}
        for preamble, name in ((False, "../escape.yaml"), (True, "../escape.tex")):
            with self.subTest(preamble=preamble):
                document = self.document(name, preamble=preamble)
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--unpack", str(document),
                                       "-o", str(target)], cwd=self.directory, env=env, stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True)
                self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn(name, done.stdout + done.stderr)
                self.assertIn("nothing was written", done.stdout + done.stderr)
                self.assertNotIn("Traceback", done.stdout + done.stderr)
                self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
