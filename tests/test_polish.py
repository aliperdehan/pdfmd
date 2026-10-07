"""Finishing touches on the built PDF, taken from mdpdf (v3.22.9): bookmarks from headings,
a running header and footer, linked files attached, PDF properties -- and the `mdpdf` command's
own keys. The end-to-end tests build with the built-in renderer (nothing on PATH but Python)."""

from __future__ import annotations

import os
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


class Templates(unittest.TestCase):
    def test_three_fields(self):
        self.assertEqual(pdfmd.parse_hf_template("a,b,c"), ("a", "b", "c"))
        self.assertEqual(pdfmd.parse_hf_template(",,{page}"), ("", "", "{page}"))

    def test_escaped_comma_stays_in_its_field(self):
        self.assertEqual(pdfmd.parse_hf_template(r"Smith\, J.,,{page}"), ("Smith, J.", "", "{page}"))

    def test_wrong_number_of_fields_is_an_error(self):
        for bad in ("a,b", "a,b,c,d", ""):
            with self.assertRaises(ValueError):
                pdfmd.parse_hf_template(bad)

    def test_fields_are_filled_and_unknown_braces_left_alone(self):
        values = {name: name.upper() for name in pdfmd.HF_FIELDS}
        self.assertEqual(pdfmd.fill_hf_field("{page}/{pages} {heading} {x}", values), "PAGE/PAGES HEADING {x}")

    def test_text_helvetica_cannot_draw(self):
        self.assertEqual(pdfmd.hf_text("Ünï"), "Ünï")
        self.assertEqual(pdfmd.hf_text("Привет"), "??????")
        self.assertEqual(pdfmd.hf_text("Žluťoučký"), "Žlutoucký")     # accents it can undo (Ž and ý it can draw)
        self.assertEqual(pdfmd.hf_text("Łódź"), "?ódz")              # a stroke letter it cannot


class Headings(unittest.TestCase):
    def test_atx_setext_and_what_is_skipped(self):
        text = ("---\ntitle: T\n---\n\n# One {#one .unnumbered}\n\n```\n# not a heading\n```\n\n"
                "<!--\n# commented\n-->\n\nTwo *words*\n---\n\n### [Linked](x.md) `code`\n\n- item\n---\n")
        self.assertEqual(pdfmd.markdown_headings([text]),
                         [(1, "One"), (2, "Two words"), (3, "Linked code")])

    def test_several_files_in_order(self):
        self.assertEqual(pdfmd.markdown_headings(["# A\n", "# B\n"]), [(1, "A"), (1, "B")])

    def test_found_on_the_page_that_has_them(self):
        pages = ["intro text", "1 Alpha heading\nbody", "more body", "2.1 Beta  heading"]
        found = pdfmd.locate_headings([(1, "Alpha heading"), (2, "Beta heading")], pages)
        self.assertEqual(found, [(1, 1, "Alpha heading"), (3, 2, "Beta heading")])

    def test_ligatures_and_case_do_not_matter(self):
        self.assertEqual(pdfmd.locate_headings([(1, "Office")], ["x", "OFFICE"]), [(1, 1, "Office")])
        self.assertEqual(pdfmd.locate_headings([(1, "Office")], ["x", "oﬃce"]), [(1, 1, "Office")])

    def test_a_contents_page_does_not_swallow_the_headings(self):
        titles = ["Alpha part", "Beta part", "Gamma part", "Delta part"]
        pages = ["Contents\n" + "\n".join(titles), "Alpha part text", "Beta part text",
                 "Gamma part text", "Delta part text"]
        found = pdfmd.locate_headings([(1, title) for title in titles], pages)
        self.assertEqual([page for page, _, _ in found], [1, 2, 3, 4])

    def test_a_heading_missing_from_the_pdf_is_skipped(self):
        self.assertEqual(pdfmd.locate_headings([(1, "Gone"), (1, "Here")], ["Here it is"]), [(0, 1, "Here")])


class MdpdfKeys(unittest.TestCase):
    def translate(self, *arguments):
        return pdfmd.mdpdf_translate(list(arguments))

    def test_every_key_maps_and_the_defaults_of_mdpdf_are_on(self):
        self.assertEqual(
            self.translate("-o", "out.pdf", "-h", "{page},,", "--footer", ",,{date}", "-t", "T", "-s", "S",
                           "-a", "A", "-k", "K,L", "-p", "A4", "doc.md"),
            ["--bookmarks", "--attach-links", "--out", "out.pdf", "--header", "{page},,", "--footer",
             ",,{date}", "--pdf-title", "T", "--pdf-subject", "S", "--pdf-author", "A", "--pdf-keywords",
             "K,L", "--paper", "a4", "doc.md"])

    def test_attached_and_equals_forms(self):
        self.assertEqual(self.translate("-oout.pdf", "--title=My doc", "--paper=Letter")[2:],
                         ["--out", "out.pdf", "--pdf-title", "My doc", "--paper", "letter"])

    def test_other_options_pass_through_in_place(self):
        self.assertEqual(self.translate("-e", "lualatex", "-v", "doc.md")[2:], ["-e", "lualatex", "-v", "doc.md"])

    def test_wildcards_are_expanded_and_several_inputs_make_one_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "a.md").write_text("# A\n", encoding="utf-8")
            (Path(folder) / "b.md").write_text("# B\n", encoding="utf-8")
            result = self.translate(str(Path(folder) / "*.md"))
        self.assertEqual(result[2:4], [str(Path(folder) / "a.md"), str(Path(folder) / "b.md")])
        self.assertIn("--report", result)

    def test_one_input_is_not_a_report(self):
        self.assertNotIn("--report", self.translate("doc.md"))

    def test_the_entry_point_exists(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('mdpdf = "pdfmd:mdpdf_main"', text)


class InkmdKeys(unittest.TestCase):
    def test_keys_are_renamed_in_place_and_the_engine_is_added(self):
        self.assertEqual(pdfmd.inkmd_translate(["doc.md", "-o", "x.pdf", "--page-size", "A4", "--family", "times"]),
                         ["-e", "inkmd", "doc.md", "--out", "x.pdf", "--paper", "a4", "--family", "times"])
        self.assertEqual(pdfmd.inkmd_translate(["--output=x.pdf", "--no-html"]),
                         ["-e", "inkmd", "--out", "x.pdf", "--no-html"])

    def test_a_named_engine_is_kept(self):
        for engine in (["-e", "lualatex"], ["--engine", "typst"], ["-elualatex"], ["--engine=typst"]):
            self.assertEqual(pdfmd.inkmd_translate([*engine, "doc.md"])[:len(engine)], engine)
            self.assertNotIn("inkmd", pdfmd.inkmd_translate([*engine, "doc.md"])[:2])

    def test_the_entry_point_exists(self):
        self.assertIn('inkmd = "pdfmd:inkmd_main"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def run_inkmd(self, folder, *arguments, stdin=None):
        empty = Path(folder) / "empty-bin"
        empty.mkdir(exist_ok=True)
        code = ("import sys; sys.path.insert(0, %r); import pdfmd; sys.argv[0] = 'inkmd'; pdfmd.inkmd_main()"
                % str(ROOT))
        return subprocess.run([sys.executable, "-c", code, *arguments], cwd=folder, input=stdin,
                              env={**os.environ, "PATH": str(empty), "PDFMD_NO_PROMPT": "1"}, capture_output=True)

    @unittest.skipIf(pypdf is None, "pypdf not installed")
    def test_standard_input_to_standard_output(self):
        with tempfile.TemporaryDirectory() as folder:
            done = self.run_inkmd(folder, "--page-size", "letter", stdin=b"# Hi\n\nText.\n")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(done.stdout.startswith(b"%PDF-"))
            (Path(folder) / "piped.pdf").write_bytes(done.stdout)
            reader = pypdf.PdfReader(Path(folder) / "piped.pdf")
            self.assertEqual(round(float(reader.pages[0].mediabox.width)), 612)
            self.assertEqual([path.name for path in Path(folder).iterdir() if path.name.startswith(".inkmd")], [])

    @unittest.skipIf(pypdf is None, "pypdf not installed")
    def test_a_file_with_output_not_a_terminal_goes_to_standard_output_and_o_writes_a_file(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "doc.md").write_text("# Doc\n\nText.\n", encoding="utf-8")
            piped = self.run_inkmd(folder, "doc.md")
            self.assertTrue(piped.stdout.startswith(b"%PDF-"), piped.stderr)
            self.assertFalse((Path(folder) / "doc.pdf").exists())
            self.assertEqual((Path(folder) / "doc.md").read_text(encoding="utf-8"), "# Doc\n\nText.\n")
            filed = self.run_inkmd(folder, "doc.md", "-o", "made.pdf", "--family", "times")
            self.assertEqual(filed.returncode, 0, filed.stderr)
            self.assertTrue((Path(folder) / "made.pdf").read_bytes().startswith(b"%PDF-"))

    def test_a_failed_build_fails_the_command_and_prints_no_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            done = self.run_inkmd(folder, "missing.md")
            self.assertNotEqual(done.returncode, 0)
            self.assertEqual(done.stdout, b"")


@unittest.skipIf(pypdf is None, "pypdf not installed")
class FinishedPdf(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)
        filler = "\n\n".join(f"Filler paragraph {number} " + "word " * 80 for number in range(12))
        (self.root / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (self.root / "doc.md").write_text(
            f"---\ntitle: Demo\n---\n\n# Alpha\n\n{filler}\n\nSee [the data](data.csv) and [web](https://example.com).\n\n"
            "## Sub one\n\nMore.\n\n# Beta\n\nSecond.\n\n<!-- pagebreak -->\n\n# Gamma\n\nEnd.\n", encoding="utf-8")

    def run_pdfmd(self, *arguments):
        empty = self.root / "empty-bin"
        empty.mkdir(exist_ok=True)
        environment = {**os.environ, "PATH": str(empty), "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], cwd=self.root,
                              env=environment, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return pypdf.PdfReader(self.root / "doc.pdf"), done

    @staticmethod
    def titles(reader):
        return [item.title if not isinstance(item, list) else [sub.title for sub in item]
                for item in reader.outline]

    def test_nothing_changes_unless_asked(self):
        reader, done = self.run_pdfmd("doc.md", "-e", "inkmd")
        self.assertEqual(reader.outline, [])
        self.assertEqual(list(reader.attachments), [])
        self.assertNotIn("PDF   ", done.stdout)

    def test_bookmarks_follow_the_headings(self):
        reader, _ = self.run_pdfmd("doc.md", "-e", "inkmd", "--bookmarks")
        self.assertEqual(self.titles(reader), ["Alpha", ["Sub one"], "Beta", "Gamma"])
        pages = [reader.get_destination_page_number(item) for item in reader.outline if not isinstance(item, list)]
        self.assertEqual(pages, sorted(pages))
        self.assertGreater(pages[-1], pages[0])

    def test_header_and_footer_on_every_page(self):
        reader, _ = self.run_pdfmd("doc.md", "-e", "inkmd", "--header", "{title},,{date}",
                                   "--footer", "Page {page} of {pages},{header},")
        count = len(reader.pages)
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            self.assertIn("Demo", text)
            self.assertIn(f"Page {number} of {count}", text)

    def test_linked_file_is_attached_and_marked(self):
        reader, _ = self.run_pdfmd("doc.md", "-e", "inkmd", "--attach-links")
        self.assertEqual(reader.attachments["linked/data.csv"], [b"a,b\n1,2\n"])
        kinds = [annotation.get_object()["/Subtype"] for page in reader.pages for annotation in page.get("/Annots", [])]
        self.assertIn("/FileAttachment", kinds)
        self.assertIn("/Link", kinds)                       # the web link is still a link

    def test_properties_and_paper(self):
        reader, _ = self.run_pdfmd("doc.md", "-e", "inkmd", "--pdf-author", "A. Writer", "--pdf-subject", "S",
                                   "--pdf-keywords", "k1, k2", "--paper", "letter")
        self.assertEqual(reader.metadata["/Author"], "A. Writer")
        self.assertEqual(reader.metadata["/Subject"], "S")
        self.assertEqual(reader.metadata["/Keywords"], "k1, k2")
        self.assertEqual(reader.metadata["/Title"], "Demo")      # the document's own is kept
        self.assertEqual(round(float(reader.pages[0].mediabox.width)), 612)

    def test_all_together_with_the_source_attached(self):
        reader, _ = self.run_pdfmd("doc.md", "-e", "inkmd", "--bookmarks", "--attach-links", "--attach-source",
                                   "--pdf-author", "A")
        self.assertEqual({"linked/data.csv", "pdfmd-manifest.json", "pdfmd-source.md"}, set(reader.attachments))
        self.assertEqual(len(self.titles(reader)), 4)
        self.assertEqual(reader.metadata["/Author"], "A")

    def test_bad_template_is_reported_and_the_pdf_is_still_built(self):
        empty = self.root / "empty-bin"
        empty.mkdir()
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "inkmd", "--header", "a,b"],
                              cwd=self.root, env={**os.environ, "PATH": str(empty), "PDFMD_NO_PROMPT": "1"},
                              capture_output=True, text=True)
        self.assertIn("needs three comma-separated fields", done.stderr)
        self.assertTrue((self.root / "doc.pdf").is_file())

    def test_the_mdpdf_command_line(self):
        empty = self.root / "empty-bin"
        empty.mkdir()
        done = subprocess.run(
            [sys.executable, "-c", "import sys; sys.path.insert(0, %r); import pdfmd; sys.argv[0] = 'mdpdf'; pdfmd.mdpdf_main()"
             % str(ROOT), "-o", "made.pdf", "-f", ",,{page}", "-a", "N. Lorrain", "-p", "A4", "-e", "inkmd", "doc.md"],
            cwd=self.root, env={**os.environ, "PATH": str(empty), "PDFMD_NO_PROMPT": "1"},
            capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        reader = pypdf.PdfReader(self.root / "made.pdf")
        self.assertEqual(reader.metadata["/Author"], "N. Lorrain")
        self.assertIn("linked/data.csv", reader.attachments)
        self.assertEqual(len(self.titles(reader)), 4)
        self.assertIn("1", reader.pages[0].extract_text().splitlines()[-1])


@unittest.skipIf(pypdf is None, "pypdf not installed")
class AttachingKeepsTheDocument(unittest.TestCase):
    def test_properties_bookmarks_and_earlier_files_survive_an_attach(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "x.pdf"
            writer = pypdf.PdfWriter()
            writer.add_blank_page(width=200, height=200)
            writer.add_outline_item("Top", 0)
            writer.add_metadata({"/Title": "Kept"})
            writer.add_attachment("first.txt", b"one")
            with path.open("wb") as handle:
                writer.write(handle)
            pdfmd.write_pdf_attachments(path, {"second.txt": b"two"})
            reader = pypdf.PdfReader(path)
            self.assertEqual(reader.metadata["/Title"], "Kept")
            self.assertEqual([item.title for item in reader.outline], ["Top"])
            self.assertEqual(set(reader.attachments), {"first.txt", "second.txt"})


if __name__ == "__main__":
    unittest.main()
