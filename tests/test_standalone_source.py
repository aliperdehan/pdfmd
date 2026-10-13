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
        self.assertIn("files/keypkg-pdfmd.yaml", names)
        self.assertIn("files/key-logo.pdf", names)
        self.assertNotIn("files/key-other.pdf", names)                       # a graphic the package does not draw
        self.assertIn("files/keydata.tex", names)
        self.assertIn("files/__up__/schemes/fig.tex", names)                 # no `..` in an attachment's name
        self.assertEqual(manifest["chain"], ["sub"])
        self.assertIn("../schemes/fig.tex", {item["path"] for item in manifest["extras"]})

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


if __name__ == "__main__":
    unittest.main()
