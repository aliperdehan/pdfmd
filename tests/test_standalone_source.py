"""v3.28.38: a PDF that carries its source carries what a rebuild needs of the machine that made it: the local package
(its style file, its pdfmd helper, the graphics it draws), files in sibling folders (`../schemes/x.tex`), and they come back
under the same layout; a source restored with its package keeps it when it is attached again."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
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
os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402

STY = """\\ProvidesPackage{keypkg}[2026/01/01 v1.0 a package]
\\newcommand{\\KeyLogoFile}{key-logo}
\\DeclareOption{titlepage}{}
\\newcommand{\\KeyLogo}{\\includegraphics{\\KeyLogoFile}}
\\input{keydata}
"""


class GraphicNames(unittest.TestCase):
    def test_a_name_that_reaches_includegraphics_counts_and_an_option_or_a_title_does_not(self):
        names = pdfmd.graphic_names_in(STY + "\\newcommand{\\Other}{titlepage}\n\\DeclareOption{equation}{}\n")
        self.assertEqual(names, ["key-logo"])

    def test_a_dotted_value_is_not_a_name(self):
        text = "\\renewcommand{\\KeyLogoFile}{logo.png}\n\\includegraphics{\\KeyLogoFile}\n"
        self.assertEqual(pdfmd.graphic_names_in(text), [])

    def test_the_helper_yaml_is_not_a_metadata_file(self):
        for name, expected in (("keypkg-pdfmd.yaml", True), ("keypkg-office.yaml", True), ("metadata.yaml", False),
                               ("report.yaml", False)):
            self.assertEqual(pdfmd.is_package_helper_yaml(Path(name)), expected, name)


@unittest.skipIf(pypdf is None, "needs pypdf")
class Pictures(unittest.TestCase):
    def test_a_one_bit_png_a_tex_engine_included_comes_back_pixel_for_pixel(self):
        # LuaTeX copies a PNG's IDAT data into the PDF with a PNG predictor; decoding it with pypdf lost 1-bit pictures
        try:
            from PIL import Image, ImageChops
        except ImportError:
            self.skipTest("needs Pillow")
        import struct
        import zlib
        from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, StreamObject
        picture = Image.new("1", (37, 21), 1)
        for x in range(37):
            for y in range(21):
                picture.putpixel((x, y), (x * 3 + y * 5) % 7 < 3)
        buffer = io.BytesIO()
        picture.save(buffer, "PNG")
        data, position, idat = buffer.getvalue(), 8, b""
        while position < len(data):
            size, = struct.unpack(">I", data[position:position + 4])
            if data[position + 4:position + 8] == b"IDAT":
                idat += data[position + 8:position + 8 + size]
            position += 12 + size
        stream = StreamObject()
        stream._data = idat
        stream.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
                       NameObject("/Width"): NumberObject(37), NameObject("/Height"): NumberObject(21),
                       NameObject("/BitsPerComponent"): NumberObject(1), NameObject("/ColorSpace"): NameObject("/DeviceGray"),
                       NameObject("/Filter"): NameObject("/FlateDecode"),
                       NameObject("/DecodeParms"): DictionaryObject({
                           NameObject("/Predictor"): NumberObject(10), NameObject("/Colors"): NumberObject(1),
                           NameObject("/Columns"): NumberObject(37), NameObject("/BitsPerComponent"): NumberObject(1)})})
        restored = Image.open(io.BytesIO(pdfmd.samples_to_png(stream)))
        self.assertEqual(restored.size, (37, 21))
        self.assertIsNone(ImageChops.difference(picture.convert("L"), restored.convert("L")).getbbox())


@unittest.skipIf(pypdf is None, "needs pypdf")
class Sources(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve() / "work"
        self.doc = self.root / "sub"
        self.write(self.doc / "keypkg.sty", STY)
        self.write(self.doc / "keypkg-pdfmd.yaml", "latex-keys:\n  experiment: KeyExperiment\n")
        self.write(self.doc / "key-logo.pdf", "%PDF-1.4 logo\n")
        self.write(self.doc / "key-other.pdf", "%PDF-1.4 unused\n")
        self.write(self.doc / "keydata.tex", "\\newcommand{\\KeyData}{1}\n")
        self.write(self.doc / "preamble.tex", "\\usepackage{keypkg}\n")
        self.write(self.root / "schemes" / "fig.tex", "\\fbox{scheme}\n")
        self.md = self.write(self.doc / "doc.md", "---\ntitle: T\nbundle-packages: true\n---\n\n"
                             "```{=latex}\n\\input{../schemes/fig.tex}\n```\n\nText.\n")

    def write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def attach(self, md: Path, *, packages: bool = True) -> tuple[dict, dict]:
        pdfmd.BUNDLE_PACKAGES_CLI = packages
        self.addCleanup(setattr, pdfmd, "BUNDLE_PACKAGES_CLI", None)
        out = md.with_suffix(".pdf")
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with out.open("wb") as handle:
            writer.write(handle)
        with contextlib.redirect_stdout(io.StringIO()):
            attachments, _, manifest = pdfmd.source_attachments(
                md, out, [], [], [md.parent / "preamble.tex"], None)
        return attachments, manifest

    def test_the_package_its_helper_its_logo_and_the_sibling_file_are_stored(self):
        attachments, manifest = self.attach(self.md)
        names = {name for name in attachments if name.startswith("files/")}
        self.assertIn("files/keypkg.sty", names)
        self.assertNotIn("files/keydata.tex", names)                         # a text file: in the source's own text now
        self.assertIn("keydata.tex", {item["path"] for item in manifest["extras"] if item.get("inline")})
        self.assertIn("files/keypkg-pdfmd.yaml", names)
        self.assertIn("files/key-logo.pdf", names)
        self.assertNotIn("files/key-other.pdf", names)                       # a graphic the package does not draw
        self.assertNotIn("files/__up__/schemes/fig.tex", names)              # a sibling folder's text file: in the text too (v3.28.44)
        self.assertEqual(manifest["chain"], ["sub"])
        self.assertIn("../schemes/fig.tex", {item["path"] for item in manifest["extras"] if item.get("inline")})
        needs = {item["name"]: item["stored"] for item in manifest["requirements"]["tex"]}
        self.assertTrue(needs and all(needs.values()), needs)               # what is stored is not reported as missing

    def test_without_the_package_flag_only_the_data_is_stored(self):
        attachments, _ = self.attach(self.md, packages=False)
        names = {name for name in attachments if name.startswith("files/")}
        self.assertNotIn("files/keypkg.sty", names)
        self.assertNotIn("files/keypkg-pdfmd.yaml", names)

    def test_restore_puts_the_sibling_folder_back_beside_the_documents(self):
        attachments, manifest = self.attach(self.md)
        out = self.root.parent / "restored"
        with contextlib.redirect_stdout(io.StringIO()):
            status = pdfmd.restore_attachments(self.md.with_suffix(".pdf"), attachments, out, False)
        self.assertEqual(status, 0)
        self.assertTrue((out / "sub" / "doc.md").is_file())
        self.assertEqual((out / "schemes" / "fig.tex").read_text(), "\\fbox{scheme}\n")
        self.assertTrue((out / "sub" / "keypkg.sty").is_file())
        self.assertTrue((out / "sub" / "keypkg-pdfmd.yaml").is_file())
        self.assertEqual(pdfmd.RESTORE_CHAIN, [])                            # the chain is only for the restore

    def test_a_restored_source_attached_again_loses_nothing(self):
        attachments, _ = self.attach(self.md)
        out = self.root.parent / "restored"
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.restore_attachments(self.md.with_suffix(".pdf"), attachments, out, False)
        again, manifest = self.attach(out / "sub" / "doc.md")
        first = {name for name in attachments if name.startswith("files/")}
        second = {name for name in again if name.startswith("files/")}
        self.assertEqual(first, second)
        self.assertEqual(manifest["chain"], ["sub"])

    def test_a_path_that_climbs_out_of_the_restored_folder_is_refused(self):
        with pdfmd.restore_chain({"chain": ["sub"]}):
            self.assertEqual(str(pdfmd.restore_target_name("x.tex")), "sub/x.tex")
            self.assertEqual(str(pdfmd.restore_target_name("../schemes/x.tex")), "schemes/x.tex")
            self.assertIsNone(pdfmd.restore_target_name("../../x.tex"))
        self.assertIsNone(pdfmd.restore_target_name("../x.tex"))


class Outside(unittest.TestCase):
    """v3.28.44: the text files of folders above the document's are blocks of the text too, and editable there."""

    def test_a_file_above_the_folder_is_a_candidate_and_a_climb_in_the_middle_is_not(self):
        data = b"a\n"
        found = pdfmd.inline_candidates({"../schemes/x.tex": data, "../../y.csv": data, "a/../b.tex": data,
                                         "../": data, "../x.pdf": data, "ok.tex": data})
        self.assertEqual(sorted(found), ["../../y.csv", "../schemes/x.tex", "ok.tex"])

    def test_a_file_with_windows_line_ends_is_text_with_eol_and_comes_back_byte_for_byte(self):
        data = b"a,b\r\n1,2\r\n"
        self.assertIn("../ir/a.csv", pdfmd.inline_candidates({"../ir/a.csv": data}))
        self.assertNotIn("m.csv", pdfmd.inline_candidates({"m.csv": b"a\r\nb\n"}))      # mixed line ends: an attachment
        self.assertNotIn("m.csv", pdfmd.inline_candidates({"m.csv": b"a\rb\n"}))
        block = pdfmd.inline_blocks({"../ir/a.csv": data})
        self.assertIn("eol: crlf", block)
        self.assertNotIn("\r", block)
        parsed = pdfmd.parse_embedded_blocks(block)[0]
        self.assertEqual(parsed["bytes"], data)
        self.assertEqual(parsed["declared"], parsed["sha256"])
        edited = block.replace("1,2\n", "1,2\n3,4\n")
        self.assertEqual(pdfmd.parse_embedded_blocks(edited)[0]["bytes"], b"a,b\r\n1,2\r\n3,4\r\n")

    def test_unpack_keeps_a_sibling_and_a_local_file_of_one_name_apart_and_stays_in_its_folder(self):
        text = ("---\ntitle: T\npdfmd-assembled: true\n---\n\nText.\n\n"
                + pdfmd.inline_blocks({"../schemes/x.tex": b"up\n", "x.tex": b"here\n", "../../z.csv": b"z\n"}))
        with tempfile.TemporaryDirectory() as folder:
            md = Path(folder) / "d.md"
            md.write_text(text, encoding="utf-8")
            out = Path(folder) / "u"
            with contextlib.redirect_stdout(io.StringIO()):
                pdfmd.unpack_assembled(md, out)
            self.assertEqual((out / "__up__" / "schemes" / "x.tex").read_text(), "up\n")
            self.assertEqual((out / "x.tex").read_text(), "here\n")
            self.assertEqual((out / "__up__" / "__up__" / "z.csv").read_text(), "z\n")
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ["d.md", "u"])

    def test_the_edit_folder_gets_the_sibling_files_from_the_text_as_it_is_now(self):
        text = "---\ntitle: T\n---\n\nText.\n\n" + pdfmd.inline_blocks({"../schemes/x.tex": b"one\n", "own.tex": b"o\n"})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            document = root / "sub" / "doc.md"
            document.parent.mkdir()
            document.write_text(text, encoding="utf-8")
            manifest = {"chain": ["sub"]}
            self.assertEqual(pdfmd.put_outside_blocks(document, root, manifest), ["../schemes/x.tex"])
            self.assertEqual((root / "schemes" / "x.tex").read_text(), "one\n")
            self.assertFalse((root / "sub" / "own.tex").exists())            # a file of the folder itself is the build's own business
            self.assertEqual(pdfmd.put_outside_blocks(document, root, manifest), [])
            document.write_text(text.replace("one\n", "two\n"), encoding="utf-8")
            self.assertEqual(pdfmd.put_outside_blocks(document, root, manifest), ["../schemes/x.tex"])
            self.assertEqual((root / "schemes" / "x.tex").read_text(), "two\n")

    def test_a_build_beside_no_such_folder_says_where_the_file_is_and_writes_nothing_outside(self):
        text = "---\ntitle: T\n---\n\nText.\n\n" + pdfmd.inline_blocks({"../schemes/x.tex": b"one\n"})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            document = root / "sub" / "doc.md"
            document.parent.mkdir()
            document.write_text(text, encoding="utf-8")
            shown = io.StringIO()
            with contextlib.redirect_stderr(shown), pdfmd.embedded_resources(document):
                pass
            self.assertIn("../schemes/x.tex is held by the source", shown.getvalue())
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["sub"])
            (root / "schemes").mkdir()
            (root / "schemes" / "x.tex").write_text("real\n")
            shown = io.StringIO()
            with contextlib.redirect_stderr(shown), pdfmd.embedded_resources(document):
                pass
            self.assertEqual(shown.getvalue(), "")
            self.assertEqual((root / "schemes" / "x.tex").read_text(), "real\n")      # never overwritten


class Again(unittest.TestCase):
    """v3.28.44: a source edited as one file (--edit) already holds its files as blocks; building it again does not repeat them."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve() / "work"
        self.doc = self.root / "sub"
        self.doc.mkdir(parents=True)
        blocks = pdfmd.inline_blocks({"../schemes/x.tex": b"old\n", "own.tex": b"mine\n", "data.csv": b"a,b\n1,2\n"})
        self.md = self.doc / "doc.md"
        self.text = ("---\ntitle: T\n---\n\n```{=latex}\n\\input{../schemes/x}\n\\input{own}\n```\n\n"
                     "::: {.csv file=\"data.csv\"}\n:::\n\n" + blocks)
        self.md.write_text(self.text, encoding="utf-8")

    def attach(self):
        out = self.md.with_suffix(".pdf")
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with out.open("wb") as handle:
            writer.write(handle)
        pdfmd.BUNDLE_CLI = "referenced"
        self.addCleanup(setattr, pdfmd, "BUNDLE_CLI", None)
        with contextlib.redirect_stdout(io.StringIO()):
            return pdfmd.source_attachments(self.md, out, [], [], [], None)

    def paths(self, merged):
        return [place for block in pdfmd.parse_embedded_blocks(merged) if block["type"] == "file" for place in pdfmd.block_places(block)]

    @unittest.skipIf(pypdf is None, "needs pypdf")
    def test_a_file_the_build_cannot_find_stays_the_block_it_is_and_is_not_repeated(self):
        _, merged, manifest = self.attach()
        self.assertEqual(sorted(self.paths(merged)), ["../schemes/x.tex", "data.csv", "own.tex"])
        self.assertEqual(sorted(item["path"] for item in manifest["extras"] if item.get("inline")),
                         ["../schemes/x.tex", "data.csv", "own.tex"])
        self.assertEqual(pdfmd.strip_location_markers(merged).count("old\n```"), 1)

    @unittest.skipIf(pypdf is None, "needs pypdf")
    def test_a_file_beside_the_document_replaces_its_block(self):
        (self.root / "schemes").mkdir()
        (self.root / "schemes" / "x.tex").write_text("new\n", encoding="utf-8")
        _, merged, _ = self.attach()
        self.assertEqual(sorted(self.paths(merged)), ["../schemes/x.tex", "data.csv", "own.tex"])
        self.assertIn("new\n```", merged)
        self.assertNotIn("old\n```", merged)

    def test_a_style_or_bibliography_embedded_twice_keeps_the_first(self):
        csl = pdfmd.render_embedded_block("csl", "s.csl", "<style/>\n", path="s.csl")
        bib = pdfmd.render_embedded_block("bibliography", "r.bib", "@a{k}\n", path="r.bib")
        text = "Text.\n\n" + csl + "\n" + bib + "\n" + csl
        out = pdfmd.drop_duplicate_blocks(text)
        self.assertEqual(out.count("type: csl"), 1)
        self.assertEqual(out.count("type: bibliography"), 1)
        self.assertEqual(pdfmd.drop_duplicate_blocks(out), out)

    def test_dropping_a_block_leaves_the_rest_as_it_was(self):
        blocks = pdfmd.inline_blocks({"a.tex": b"a\n", "b.tex": b"b\n"})
        text = "Text.\n\n" + blocks + "\nEnd.\n"
        out = pdfmd.drop_blocks(text, lambda fields: fields.get("path") == "a.tex")
        self.assertIn("b\n```", out)
        self.assertNotIn("a.tex", out)
        self.assertEqual(len(pdfmd.parse_embedded_blocks(out)), 1)
        self.assertNotIn("\n\n\n\n", out)
        self.assertTrue(out.endswith("End.\n"))


class Inline(unittest.TestCase):
    """v3.28.39: the text files a source needs are blocks of its own text, after the text, with line markers."""

    FRONT = "---\ntitle: T\nheader-includes: |\n  \\usepackage{x}\n---\n\n"
    BODY = ("Intro.\n\n::: {.csv file=\"tables/a.csv\"}\n:::\n\n```{=latex}\n\\input{tex/fig}\n```\n\nEnd.\n")

    def text(self) -> str:
        files = {"tables/a.csv": b"a,b\n1,2\n", "tex/fig.tex": b"\\fbox{1}\n", "chemicals.tex": b"x\n",
                 "metadata/chemicals.tex": b"x\n"}
        return self.FRONT + self.BODY + pdfmd.inline_blocks(files), files

    def test_the_tex_files_come_first_then_the_data_and_equal_files_are_one_block(self):
        text, _ = self.text()
        order = [(block["path"], block["also"]) for block in pdfmd.parse_embedded_blocks(text)]
        self.assertEqual(order, [("chemicals.tex", ["metadata/chemicals.tex"]), ("tex/fig.tex", []),
                                 ("tables/a.csv", [])])

    def test_the_markers_give_the_lines_where_the_files_are_and_come_out_again(self):
        text, _ = self.text()
        marked = pdfmd.with_location_markers(text)
        lines = marked.splitlines()
        for name, line in pdfmd.embedded_lines(marked).items():
            if name in ("front matter", "preamble"):
                continue
            self.assertIn(f"{name}  ", "\n".join(l for l in lines if l.startswith(name)) + "  ")
            self.assertTrue(lines[line - 1].startswith("```{=pdfmd}"), name)
            self.assertIn(f"line {line}", next(l for l in lines if l.startswith(name + " ")), name)
        self.assertIn("<!-- pdfmd-at: tables/a.csv @ line ", marked)       # before the block that names it
        self.assertIn("<!-- pdfmd-at: tex/fig.tex @ line ", marked)
        self.assertEqual(pdfmd.strip_location_markers(marked), text)
        self.assertEqual(pdfmd.with_location_markers(marked), marked)       # regenerated, not stacked

    def test_an_edit_that_moves_a_line_is_followed_by_the_next_write(self):
        text, _ = self.text()
        marked = pdfmd.with_location_markers(text)
        longer = marked.replace("Intro.\n", "Intro.\n\nOne more paragraph.\n\nAnd another.\n", 1)
        again = pdfmd.with_location_markers(longer)
        lines = again.splitlines()
        for name, line in pdfmd.embedded_lines(again).items():
            if name not in ("front matter", "preamble"):
                self.assertIn(f"line {line}", next(l for l in lines if l.startswith(name + " ")), name)

    def test_a_text_without_embedded_files_is_left_alone(self):
        plain = self.FRONT.replace("header-includes: |\n  \\usepackage{x}\n", "") + "Just text.\n"
        self.assertEqual(pdfmd.with_location_markers(plain), plain)

    @unittest.skipIf(pypdf is None, "needs pypdf")
    def test_restore_gives_the_original_text_without_markers(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name).resolve() / "work" / "doc"
        (root / "tables").mkdir(parents=True)
        (root / "metadata").mkdir()
        (root / "tables" / "a.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (root / "chemicals.tex").write_text("x\n", encoding="utf-8")
        (root / "metadata" / "chemicals.tex").write_text("x\n", encoding="utf-8")
        original = "---\ntitle: T\n---\n\nIntro.\n\n::: {.csv file=\"tables/a.csv\"}\n:::\n\n```{=latex}\n\\input{chemicals}\n```\n"
        md = root / "doc.md"
        md.write_text(original, encoding="utf-8")
        pdfmd.BUNDLE_CLI = "referenced"
        self.addCleanup(setattr, pdfmd, "BUNDLE_CLI", None)
        out = md.with_suffix(".pdf")
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with out.open("wb") as handle:
            writer.write(handle)
        with contextlib.redirect_stdout(io.StringIO()):
            attachments, merged, manifest = pdfmd.source_attachments(md, out, [], [], [], None)
        self.assertIn("<!-- pdfmd-at: index", merged)
        self.assertFalse([name for name in attachments if name.startswith("files/")])      # every file is in the text
        restored = root.parent / "restored"
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.restore_attachments(out, attachments, restored, False)
        self.assertEqual((restored / "doc.md").read_text(encoding="utf-8"), original)
        self.assertEqual((restored / "tables" / "a.csv").read_text(), "a,b\n1,2\n")
        self.assertEqual((restored / "chemicals.tex").read_text(), "x\n")
        self.assertFalse((restored / "doc.unpacked").exists())

    def test_a_block_that_lists_two_paths_comes_back_at_both(self):
        text, files = self.text()
        from pathlib import PurePosixPath
        text = text.replace("title: T\n", "pdfmd-assembled: true\ntitle: T\n", 1)
        placed = pdfmd.layout_from_source(text, {"layout": [], "chunks": [], "sha256": ""}, PurePosixPath("doc.md"))
        for name in files:
            self.assertEqual(placed[name], files[name].decode("utf-8") if isinstance(placed[name], str) else files[name], name)
        self.assertIn("metadata/chemicals.tex", placed)
        self.assertFalse([name for name in placed if ".unpacked" in name])


if __name__ == "__main__":
    unittest.main()
