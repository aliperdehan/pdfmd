"""Lossless PDF shrinking (lib/pdfmd_shrink): the providers, what must survive and what must never be touched."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402

import pypdf  # noqa: E402

shrink = pdfmd.load_package("pdfmd_shrink")

XMP = (b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
       b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
       b'xmlns:dc="http://purl.org/dc/elements/1.1/"%s><dc:title>Shrink test</dc:title></rdf:Description></rdf:RDF>'
       b'</x:xmpmeta><?xpacket end="w"?>')
PDFA1 = b' xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" pdfaid:part="1" pdfaid:conformance="B"'


def build_pdf(pages: int = 40, pdfa1: bool = False) -> bytes:
    """What pdfmd's own stamp pass leaves: a PDF 1.3 file with no object streams, an Info dictionary (with a /Trapped name), an
    XMP stream, one text page per page and two attachments."""
    objects: dict[int, bytes] = {}
    first_page = 6
    kids = " ".join(f"{first_page + 2 * number} 0 R" for number in range(pages))
    objects[1] = b"<</Type/Catalog/Pages 2 0 R/Metadata 4 0 R>>"
    objects[2] = f"<</Type/Pages/Kids[{kids}]/Count {pages}>>".encode()
    objects[3] = b"<</Title(Shrink test)/Author(The author)/Trapped/False/PdfmdBuildDate(2026-11-16)>>"
    xmp = XMP % (PDFA1 if pdfa1 else b"")
    objects[4] = b"<</Type/Metadata/Subtype/XML/Length %d>>\nstream\n%s\nendstream" % (len(xmp), xmp)
    objects[5] = b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"
    for number in range(pages):
        text = f"BT /F1 12 Tf 72 720 Td (Page {number + 1} of the shrink test, with some words in it) Tj ET\n" * 20
        stream = text.encode()
        objects[first_page + 2 * number] = (f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents {first_page + 2 * number + 1} 0 R"
                                            "/Resources<</Font<</F1 5 0 R>>>>>>").encode()
        objects[first_page + 2 * number + 1] = b"<</Length %d>>\nstream\n%s\nendstream" % (len(stream), stream)
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n%s\nendobj\n" % (number, objects[number])
    xref = len(out)
    size = max(objects) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for number in range(1, size):
        out += b"%010d 00000 n \n" % offsets[number]
    out += b"trailer\n<</Size %d/Root 1 0 R/Info 3 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    writer = pypdf.PdfWriter(clone_from=io.BytesIO(bytes(out)))
    writer.add_attachment("pdfmd-source.md", b"# source\n" * 50)
    writer.add_attachment("pdfmd-manifest.json", b'{"files": []}')
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def facts(path: Path) -> dict:
    """What a lossless shrink must keep: page count, the text of every page, the Info dictionary, the XMP, the attachments."""
    reader = pypdf.PdfReader(str(path))
    root = reader.trailer["/Root"]
    return {
        "pages": len(reader.pages),
        "text": [page.extract_text() for page in reader.pages],
        "info": {key: str(value) for key, value in (reader.trailer["/Info"].items())},
        "xmp": root["/Metadata"].get_object().get_data(),
        "attachments": {name: list(data) for name, data in reader.attachments.items()},
    }


def installed() -> list[str]:
    return [name for name, _ in shrink.available()]


class Setting(unittest.TestCase):
    def test_modes(self):
        for value, mode in ((True, "true"), (False, "false"), ("true", "true"), ("Fast", "fast"), ("off", "false"), ("yes", "true"),
                            (None, None), ("sometimes", None)):
            self.assertEqual(shrink.parse_mode(value), mode, value)

    def test_the_default_is_on_and_the_command_line_wins(self):
        with tempfile.TemporaryDirectory() as scratch:
            document = Path(scratch) / "d.md"
            document.write_text("---\ntitle: T\n---\n\nText\n", encoding="utf-8")
            with mock.patch.dict(os.environ):
                os.environ.pop("PDFMD_SHRINK", None)
                self.assertEqual(shrink.resolve_mode(document, []), "true")
                document.write_text("---\ntitle: T\npdfmd-options:\n  shrink: fast\n---\n\nText\n", encoding="utf-8")
                self.assertEqual(shrink.resolve_mode(document, []), "fast")
                document.write_text("---\ntitle: T\npdfmd-options:\n  shrink: false\n---\n\nText\n", encoding="utf-8")
                self.assertEqual(shrink.resolve_mode(document, []), "false")
                os.environ["PDFMD_SHRINK"] = "true"
                self.assertEqual(shrink.resolve_mode(document, []), "true")

    def test_the_timeout_is_a_setting(self):
        with tempfile.TemporaryDirectory() as scratch:
            document = Path(scratch) / "d.md"
            document.write_text("---\ntitle: T\n---\n\nText\n", encoding="utf-8")
            self.assertEqual(shrink.timeout_for(document, []), shrink.SHRINK_TIMEOUT)
            document.write_text("---\ntitle: T\npdfmd-options:\n  shrink-timeout: 7\n---\n\nText\n", encoding="utf-8")
            self.assertEqual(shrink.timeout_for(document, []), 7)
            document.write_text("---\ntitle: T\npdfmd-options:\n  shrink-timeout: 0\n---\n\nText\n", encoding="utf-8")
            self.assertIsNone(shrink.timeout_for(document, []))


class Providers(unittest.TestCase):
    """Each installed provider shrinks the file and keeps everything: the same checks, one subtest per provider and mode."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-shrink-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def only(self, provider: str):
        return mock.patch.object(shrink, "available", lambda: [(provider, "test")])

    def test_the_test_pdf_is_what_pdfmd_writes_without_object_streams(self):
        data = build_pdf()
        self.assertNotIn(b"/ObjStm", data)

    def test_every_provider_shrinks_and_keeps_everything(self):
        names = installed()
        if not names:
            self.skipTest("none of qpdf, pikepdf, mutool is installed")
        for provider in names:
            for mode in ("true", "fast"):
                with self.subTest(provider=provider, mode=mode):
                    path = self.directory / f"{provider}-{mode}.pdf"
                    path.write_bytes(build_pdf())
                    before, size = facts(path), path.stat().st_size
                    with self.only(provider):
                        outcome = shrink.shrink_file(path, mode)
                    self.assertEqual(outcome.status, "shrunk", outcome)
                    self.assertEqual((outcome.provider, outcome.before), (provider, size))
                    self.assertLess(path.stat().st_size, size)
                    self.assertEqual(outcome.after, path.stat().st_size)
                    self.assertIn(b"/ObjStm", path.read_bytes())
                    self.assertEqual(facts(path), before)
                    self.assertEqual(facts(path)["attachments"]["pdfmd-source.md"], [b"# source\n" * 50])
                    self.assertEqual([item.name for item in self.directory.iterdir() if item.name.endswith(".part")], [])
        if shutil.which("qpdf") and "qpdf" in names:
            done = subprocess.run(["qpdf", "--check", str(self.directory / "qpdf-true.pdf")], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    @unittest.skipUnless(shutil.which("qpdf"), "needs qpdf")
    def test_two_runs_give_the_same_bytes(self):
        results = []
        for number in range(2):
            path = self.directory / f"{number}.pdf"
            path.write_bytes(build_pdf())
            with self.only("qpdf"):
                shrink.shrink_file(path, "true")
            results.append(path.read_bytes())
        self.assertEqual(results[0], results[1])

    @unittest.skipUnless(shutil.which("qpdf"), "needs qpdf")
    def test_an_old_qpdf_without_recompression_still_makes_object_streams(self):
        seen = []
        real = shrink._run

        def spy(command, timeout):
            seen.append(command)
            return real(command, timeout)

        path = self.directory / "a.pdf"
        path.write_bytes(build_pdf())
        with self.only("qpdf"), mock.patch.object(shrink, "qpdf_options", lambda binary: frozenset({"--object-streams"})), \
                mock.patch.object(shrink, "_run", spy):
            outcome = shrink.shrink_file(path, "true")
        self.assertEqual(outcome.status, "shrunk", outcome)
        command = next(item for item in seen if "--object-streams=generate" in item)
        self.assertEqual([word for word in command if word.startswith("--") and word != "--object-streams=generate"], [])

    def test_pdfa1_gets_no_object_streams(self):
        names = installed()
        if not names:
            self.skipTest("none of qpdf, pikepdf, mutool is installed")
        data = build_pdf(pdfa1=True)
        self.assertTrue(b"pdfaid:part" in data)
        for provider in names:
            with self.subTest(provider=provider):
                path = self.directory / f"{provider}-a1.pdf"
                path.write_bytes(data)
                with self.only(provider):
                    fast = shrink.shrink_file(path, "fast")
                self.assertEqual(fast.status, "skipped", fast)
                self.assertEqual(path.read_bytes(), data)
                with self.only(provider):
                    full = shrink.shrink_file(path, "true")
                self.assertIn(full.status, ("shrunk", "kept"), full)
                self.assertNotIn(b"/ObjStm", path.read_bytes())
                self.assertEqual(facts(path)["pages"], 40)

    def test_pdfa1_is_found_in_pieces_too(self):
        path = self.directory / "a.pdf"
        path.write_bytes(b"x" * (shrink.SCAN_CHUNK - 10) + b'pdfaid:part="1"')
        self.assertTrue(shrink.declares_pdfa1(path))
        path.write_bytes(b"x" * 100 + b"<pdfaid:part>2</pdfaid:part>")
        self.assertFalse(shrink.declares_pdfa1(path))
        path.write_bytes(b"x" * 100 + b"<pdfaid:part>1</pdfaid:part>")
        self.assertTrue(shrink.declares_pdfa1(path))

    def test_what_fails_leaves_the_original_whole(self):
        names = installed()
        if not names:
            self.skipTest("none of qpdf, pikepdf, mutool is installed")
        path = self.directory / "broken.pdf"
        path.write_bytes(b"%PDF-1.4 stand-in, not a document\n")
        for provider in names:
            with self.subTest(provider=provider), self.only(provider):
                outcome = shrink.shrink_file(path, "true")
            self.assertEqual(outcome.status, "failed", outcome)
            self.assertEqual(path.read_bytes(), b"%PDF-1.4 stand-in, not a document\n")
        self.assertEqual(sorted(item.name for item in self.directory.iterdir()), ["broken.pdf"])

    def test_a_result_that_is_not_smaller_is_not_taken(self):
        path = self.directory / "a.pdf"
        data = build_pdf()
        path.write_bytes(data)

        def bigger(source, target, mode, pdfa1, timeout, verbose):
            Path(target).write_bytes(data + b"0" * 1000)
            return "ok", 40, 40, ""

        with mock.patch.object(shrink, "available", lambda: [("qpdf", "x")]), mock.patch.dict(shrink.RUNNERS, {"qpdf": bigger}):
            outcome = shrink.shrink_file(path, "true")
        self.assertEqual(outcome.status, "kept", outcome)
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(sorted(item.name for item in self.directory.iterdir()), ["a.pdf"])

    def test_a_different_page_count_is_not_taken(self):
        path = self.directory / "a.pdf"
        data = build_pdf()
        path.write_bytes(data)

        def lossy(source, target, mode, pdfa1, timeout, verbose):
            Path(target).write_bytes(b"%PDF-1.5 tiny")
            return "ok", 40, 39, ""

        with mock.patch.object(shrink, "available", lambda: [("qpdf", "x")]), mock.patch.dict(shrink.RUNNERS, {"qpdf": lossy}):
            outcome = shrink.shrink_file(path, "true")
        self.assertEqual(outcome.status, "failed", outcome)
        self.assertEqual(path.read_bytes(), data)

    def test_a_tool_that_runs_out_of_time_keeps_the_original(self):
        path = self.directory / "a.pdf"
        data = build_pdf()
        path.write_bytes(data)

        def slow(source, target, mode, pdfa1, timeout, verbose):
            raise subprocess.TimeoutExpired("qpdf", timeout)

        with mock.patch.object(shrink, "available", lambda: [("qpdf", "x")]), mock.patch.dict(shrink.RUNNERS, {"qpdf": slow}):
            outcome = shrink.shrink_file(path, "true", 0.5)
        self.assertEqual((outcome.status, path.read_bytes()), ("failed", data))
        self.assertIn("shrink-timeout", outcome.why)

    def test_no_tool_and_no_pdf(self):
        path = self.directory / "a.pdf"
        path.write_bytes(build_pdf())
        with mock.patch.object(shrink, "available", lambda: []):
            self.assertEqual(shrink.shrink_file(path, "true").status, "none")
        self.assertEqual(shrink.shrink_file(path, "false").status, "off")
        text = self.directory / "a.txt"
        text.write_text("x", encoding="utf-8")
        self.assertEqual(shrink.shrink_output(text, text, [], False).status, "off")
        self.assertEqual(shrink.shrink_output(None, text, [], False).status, "off")

    def test_the_providers_come_in_the_decided_order(self):
        self.assertEqual(shrink.PROVIDERS, ("qpdf", "pikepdf", "mutool"))
        names = installed()
        self.assertEqual(names, [name for name in shrink.PROVIDERS if name in names])


if __name__ == "__main__":
    unittest.main()
