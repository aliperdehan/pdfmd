"""Word/OpenDocument output: page setup and fonts written into the reference document, and the
reference document found beside the source. The slow checks need Pandoc (and LibreOffice for the
one that renders); they skip without."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402
from pdfmd_office import (OfficeSpec, docx, length_to_twips, office_font, parse_geometry, parse_paper,  # noqa: E402
                          patch_reference, spec_from_metadata)

PANDOC = shutil.which("pandoc")
SOFFICE = shutil.which("soffice") or ("/Applications/LibreOffice.app/Contents/MacOS/soffice"
                                      if Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").exists() else None)


class Units(unittest.TestCase):
    def test_lengths(self):
        self.assertEqual(length_to_twips("1in"), 1440)
        self.assertEqual(length_to_twips("2.54cm"), 1440)
        self.assertEqual(length_to_twips("72pt"), 1440)
        self.assertEqual(length_to_twips("25.4mm"), 1440)
        self.assertEqual(length_to_twips(1), 1440)
        self.assertIsNone(length_to_twips("wide"))
        self.assertIsNone(length_to_twips(True))

    def test_paper(self):
        self.assertEqual(parse_paper("A4"), ((11906, 16838), False))
        self.assertEqual(parse_paper("a4paper"), ((11906, 16838), False))
        self.assertEqual(parse_paper(["letterpaper", "landscape"]), ((12240, 15840), True))
        self.assertEqual(parse_paper("us-legal")[0], (12240, 20160))
        self.assertEqual(parse_paper("nonsense"), (None, False))

    def test_geometry_spellings(self):
        sides = lambda value: parse_geometry(value)["margins"]
        self.assertEqual(sides("margin=1in"), {"top": 1440, "bottom": 1440, "left": 1440, "right": 1440})
        self.assertEqual(sides(["top=1in", "bottom=1.17in", "left=2cm", "right=2cm"])["bottom"], 1685)
        self.assertEqual(sides("left=3cm,right=1cm")["left"], 1701)
        self.assertEqual(sides({"left": "3cm"}), {"left": 1701})
        self.assertEqual(sides("hmargin=1in,vmargin=2in"), {"left": 1440, "right": 1440, "top": 2880, "bottom": 2880})
        self.assertEqual(sides("margin=1in,top=2in")["top"], 2880)
        got = parse_geometry("a5paper,landscape,margin=1cm")
        self.assertEqual((got["paper"], got["landscape"]), ((8391, 11906), True))
        self.assertEqual(parse_geometry("paperwidth=6in,paperheight=9in")["paper"], (8640, 12960))
        self.assertEqual(sides("includehead,showframe"), {})

    def test_fonts_are_mapped_to_ones_word_has(self):
        self.assertEqual(office_font("STIX Two Text")[0], "Times New Roman")
        self.assertEqual(office_font("JetBrains Mono")[0], "Consolas")
        self.assertEqual(office_font("STIX Two Text", policy="exact"), ("STIX Two Text", None))
        self.assertEqual(office_font("Arial"), ("Arial", None))
        name, note = office_font("Zapfino")
        self.assertEqual(name, "Zapfino")
        self.assertIn("substitute", note)

    def test_spec_reads_pandoc_metadata(self):
        spec = spec_from_metadata({"papersize": "a4", "geometry": ["top=1in", "left=2cm"], "fontsize": "11pt",
                                   "mainfont": "STIX Two Text", "lang": "en-GB", "indent": True, "linestretch": 1.15,
                                   "classoption": ["landscape"]})
        self.assertEqual(spec.paper, (11906, 16838))
        self.assertTrue(spec.landscape)
        self.assertEqual((spec.size, spec.main, spec.lang, spec.indent, spec.stretch), (11.0, "Times New Roman", "en-GB", True, 1.15))
        self.assertEqual(spec.page_size(), (16838, 11906))
        self.assertEqual(spec_from_metadata({"margin": "2cm"}).margins["top"], 1134)
        self.assertEqual(spec_from_metadata({"pagesize": "a5"}).paper, (8391, 11906))
        self.assertTrue(spec_from_metadata({}).empty())
        # the office: block wins key by key
        self.assertEqual(spec_from_metadata({"papersize": "a4"}, {"papersize": "letter"}).paper, (12240, 15840))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Patching(unittest.TestCase):
    def parts(self, data: bytes) -> dict[str, str]:
        archive = zipfile.ZipFile(io.BytesIO(data))
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".xml")}

    def test_docx_parts_stay_well_formed_and_carry_the_settings(self):
        spec = spec_from_metadata({"papersize": "a4", "geometry": "margin=2cm", "mainfont": "STIX Two Text",
                                   "monofont": "JetBrains Mono", "fontsize": "10pt", "lang": "en-GB",
                                   "indent": True, "linestretch": 1.5})
        data = patch_reference("docx", docx.default_reference(), spec, True)
        parts = self.parts(data)
        for name, text in parts.items():
            ElementTree.fromstring(text)            # raises if broken
        self.assertIn('<w:pgSz w:w="11906" w:h="16838"/>', parts["word/document.xml"])
        self.assertIn('w:top="1134"', parts["word/document.xml"])
        styles = parts["word/styles.xml"]
        self.assertIn('w:ascii="Times New Roman"', styles)
        self.assertNotIn("asciiTheme", re.search(r'w:styleId="Heading1".*?</w:style>', styles, re.S).group(0))
        self.assertIn('<w:sz w:val="20"/>', re.search(r"<w:docDefaults>.*?</w:docDefaults>", styles, re.S).group(0))
        self.assertIn('w:val="en-GB"', styles)
        self.assertIn('w:line="360"', styles)
        self.assertIn('w:ascii="Consolas"', re.search(r'w:styleId="VerbatimChar".*?</w:style>', styles, re.S).group(0))
        self.assertIn("w:firstLine=\"360\"", styles)

    def test_headings_follow_the_size_and_children_stay_in_schema_order(self):
        data = patch_reference("docx", docx.default_reference(), spec_from_metadata({"fontsize": "10pt"}), True)
        styles = self.parts(data)["word/styles.xml"]
        heading = re.search(r'w:styleId="Heading1".*?</w:style>', styles, re.S).group(0)
        self.assertIn('<w:sz w:val="24"/>', heading)                      # 10 pt x 1.2
        rpr = re.search(r"<w:rPr>(.*?)</w:rPr>", heading, re.S).group(1)
        tags = re.findall(r"<w:(\w+)", rpr)
        self.assertEqual(tags, sorted(tags, key=docx.RPR_ORDER.index))

    def test_a_templates_namespaces_survive(self):
        # Word's own files declare mc:Ignorable prefixes; text editing leaves them alone
        reference = docx.default_reference()
        archive = zipfile.ZipFile(io.BytesIO(reference))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as target:
            for item in archive.infolist():
                content = archive.read(item.filename)
                if item.filename == "word/document.xml":
                    content = content.replace(b"<w:document ", b'<w:document xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" ', 1)
                target.writestr(item, content)
        patched = patch_reference("docx", out.getvalue(), spec_from_metadata({"papersize": "a4"}), False)
        self.assertIn('mc:Ignorable="w14"', self.parts(patched)["word/document.xml"])

    def test_a_dotx_becomes_a_document(self):
        reference = docx.default_reference()
        archive = zipfile.ZipFile(io.BytesIO(reference))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as target:
            for item in archive.infolist():
                content = archive.read(item.filename)
                if item.filename == "[Content_Types].xml":
                    content = content.replace(b"document.main+xml", b"template.main+xml")
                target.writestr(item, content)
        patched = self.parts(patch_reference("docx", out.getvalue(), OfficeSpec(), False))
        self.assertIn("document.main+xml", patched["[Content_Types].xml"])

    def test_media_are_replaced_and_figure_paragraphs_are_centred_and_unindented(self):
        reference = docx.default_reference()
        picture = zipfile.ZipFile(io.BytesIO(reference)).namelist()
        spec = spec_from_metadata({})
        spec.media = {"word/theme/theme1.xml": b"<replaced/>"}
        out = patch_reference("docx", reference, spec, False)
        self.assertEqual(zipfile.ZipFile(io.BytesIO(out)).read("word/theme/theme1.xml"), b"<replaced/>")
        styles = self.parts(out)["word/styles.xml"]
        figure = re.search(r'w:styleId="CaptionedFigure".*?</w:style>', styles, re.S).group(0)
        self.assertIn('w:firstLine="0"', figure)
        self.assertIn('w:val="center"', figure)
        self.assertIn("PdfmdCentered", styles)
        self.assertTrue(picture)

    def test_odt_page_and_fonts(self):
        data = subprocess.run(["pandoc", "--print-default-data-file", "reference.odt"], capture_output=True).stdout
        spec = spec_from_metadata({"papersize": "a4", "geometry": "margin=2cm", "mainfont": "Arial", "fontsize": "14pt",
                                   "monofont": "Courier New"})
        styles = self.parts(patch_reference("odt", data, spec, True))["styles.xml"]
        ElementTree.fromstring(styles)
        self.assertIn('fo:page-width="8.2681in"', styles)
        self.assertIn('fo:margin-left="0.7875in"', styles)
        self.assertIn('fo:font-size="14pt"', re.search(r'<style:default-style style:family="paragraph">.*?</style:default-style>', styles, re.S).group(0))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Discovery(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        (self.root / "doc.md").write_text("---\ntitle: T\npapersize: a4\n---\n\nText.\n", encoding="utf-8")
        self.reference = docx.default_reference()

    def build(self, *arguments, name="doc.md", cwd=None):
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.root / "cfg")}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, *arguments], cwd=cwd or self.root,
                              env=environment, capture_output=True, text=True)

    def page(self, path: Path) -> str:
        document = zipfile.ZipFile(path).read("word/document.xml").decode()
        return re.search(r"<w:pgSz[^>]*/>", document).group(0)

    def test_metadata_sets_the_page_without_a_reference_document(self):
        self.assertEqual(self.build("-o", "doc.docx").returncode, 0)
        self.assertIn('w:w="11906"', self.page(self.root / "doc.docx"))

    def test_a_reference_document_beside_the_source_wins_over_the_metadata(self):
        (self.root / "reference.docx").write_bytes(patch_reference("docx", self.reference, spec_from_metadata({"papersize": "legal"}), False))
        result = self.build("-o", "doc.docx", "-v")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('w:h="20160"', self.page(self.root / "doc.docx"))     # the template's legal, not the metadata's a4
        self.assertIn("reference.docx", result.stdout)

    def test_the_office_block_changes_a_template_key_by_key(self):
        (self.root / "reference.docx").write_bytes(patch_reference("docx", self.reference, spec_from_metadata({"papersize": "legal"}), False))
        (self.root / "doc.md").write_text("---\ntitle: T\npdfmd-options:\n  office: {papersize: a5}\n---\n\nText.\n", encoding="utf-8")
        self.assertEqual(self.build("-o", "doc.docx").returncode, 0)
        self.assertIn('w:w="8391"', self.page(self.root / "doc.docx"))

    def test_a_document_named_reference_does_not_use_its_own_output(self):
        (self.root / "reference.md").write_text("---\ntitle: T\n---\n\nText.\n", encoding="utf-8")
        self.assertEqual(self.build("-o", "reference.docx", name="reference.md").returncode, 0)
        self.assertEqual(self.build("-o", "reference.docx", name="reference.md").returncode, 0)   # again: its own output is no template

    def test_name_reference_and_metadata_folder_and_dotx(self):
        folder = self.root / "metadata"
        folder.mkdir()
        (folder / "doc-reference.dotx").write_bytes(patch_reference("docx", self.reference, spec_from_metadata({"papersize": "a3"}), False))
        self.assertEqual(self.build("-o", "doc.docx").returncode, 0)
        self.assertIn('w:w="16838"', self.page(self.root / "doc.docx"))

    def test_no_auto_switches_discovery_and_style_off(self):
        (self.root / "reference.docx").write_bytes(patch_reference("docx", self.reference, spec_from_metadata({"papersize": "legal"}), False))
        self.assertEqual(self.build("-o", "doc.docx", "--no-auto", "officeref").returncode, 0)
        self.assertIn('w:w="11906"', self.page(self.root / "doc.docx"))
        self.assertEqual(self.build("-o", "plain.docx", "--no-auto", "officeref", "officestyle").returncode, 0)
        self.assertNotIn("pgSz", zipfile.ZipFile(self.root / "plain.docx").read("word/document.xml").decode())

    def test_a_pandoc_reference_doc_option_is_left_alone(self):
        (self.root / "mine.docx").write_bytes(patch_reference("docx", self.reference, spec_from_metadata({"papersize": "a3"}), False))
        self.assertEqual(self.build("-o", "doc.docx", "--reference-doc", "mine.docx").returncode, 0)
        self.assertIn('w:w="16838"', self.page(self.root / "doc.docx"))

    def test_other_targets_are_untouched(self):
        self.assertEqual(self.build("-o", "doc.html").returncode, 0)
        self.assertEqual(self.build("-o", "doc.odt").returncode, 0)
        self.assertIn(b"8.2681in", zipfile.ZipFile(self.root / "doc.odt").read("styles.xml"))

    def test_init_reference_writes_and_never_overwrites(self):
        self.assertEqual(self.build("--init-reference", name="--version").returncode, 0) if False else None
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--init-reference"], cwd=self.root,
                              capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": ""})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.root / "reference.docx").is_file())
        marker = (self.root / "reference.docx").read_bytes()
        again = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--init-reference"], cwd=self.root,
                               capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": ""})
        self.assertIn("left alone", again.stdout)
        self.assertEqual((self.root / "reference.docx").read_bytes(), marker)

    def test_report_mode_and_batch_mode_get_it_too(self):
        (self.root / "book").mkdir()
        (self.root / "book" / "a.md").write_text("# A\n\nText.\n", encoding="utf-8")
        (self.root / "book" / "b.md").write_text("# B\n\nText.\n", encoding="utf-8")
        (self.root / "book" / "metadata.yaml").write_text("papersize: a4\n", encoding="utf-8")
        done = self.build("book", "-r", "-o", "book.docx")
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertIn('w:w="11906"', self.page(self.root / "book.docx"))
        done = self.build("-b", "--to", "docx", "-o", "out", name="book")
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertIn('w:w="11906"', self.page(self.root / "out" / "a.docx"))


@unittest.skipUnless(PANDOC and SOFFICE and shutil.which("pdfinfo"), "needs Pandoc, LibreOffice and pdfinfo")
class Rendered(unittest.TestCase):
    """LibreOffice stands in for Word: the page it prints is the page the file asked for."""

    def test_pages_come_out_the_size_asked_for(self):
        cases = {"a4": (595.3, 841.9), "letter": (612, 792), "legal": (612, 1008), "a5": (419.5, 595.3)}
        with tempfile.TemporaryDirectory() as directory:
            for name, (width, height) in cases.items():
                folder = Path(directory) / name
                folder.mkdir()
                (folder / "doc.md").write_text(f"---\ntitle: T\npapersize: {name}\n---\n\nText.\n", encoding="utf-8")
                subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-o", "doc.docx"], cwd=folder,
                               capture_output=True, env={**os.environ, "PDFMD_CONFIG": ""})
                subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", str(folder), str(folder / "doc.docx")],
                               capture_output=True)
                info = subprocess.run(["pdfinfo", str(folder / "doc.pdf")], capture_output=True, text=True).stdout
                found = re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info)
                self.assertAlmostEqual(float(found.group(1)), width, delta=1.5, msg=name)
                self.assertAlmostEqual(float(found.group(2)), height, delta=1.5, msg=name)


if __name__ == "__main__":
    unittest.main()


STYLES = ('<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
          '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
          '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
          '<w:pPr><w:keepNext/><w:spacing w:before="480"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="48"/></w:rPr></w:style>'
          '<w:style w:type="paragraph" w:customStyle="1" w:styleId="LRH1"><w:name w:val="LR H1"/><w:basedOn w:val="Heading1"/>'
          '<w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="both"/></w:pPr><w:rPr><w:sz w:val="24"/></w:rPr></w:style>'
          '<w:style w:type="paragraph" w:customStyle="1" w:styleId="LRNormal"><w:name w:val="LR Normal"/><w:basedOn w:val="Normal"/>'
          '<w:pPr><w:ind w:firstLine="720"/></w:pPr></w:style>'
          '</w:styles>')


class StyleAliases(unittest.TestCase):
    def test_a_source_based_on_its_target_adds_to_it(self):
        out = docx.alias_styles(STYLES, {"Heading1": "LRH1"})
        block = re.search(r'w:styleId="Heading1".*?</w:style>', out, re.S).group(0)
        self.assertIn('<w:keepNext/>', block)                    # kept
        self.assertIn('w:before="0" w:after="0"', block)         # the source's spacing
        self.assertIn('<w:sz w:val="24"/>', block)
        self.assertIn("<w:b/>", block)                           # the target's own bold stays
        self.assertIn('<w:outlineLvl w:val="0"/>', block)        # still a level-1 heading
        self.assertNotIn('basedOn w:val="Heading1"', block)      # no loop onto itself

    def test_any_other_source_replaces_the_look_and_a_missing_style_is_made(self):
        out = docx.alias_styles(STYLES, {"BodyText": "LRNormal", "Compact": "Normal"})
        body = re.search(r'w:styleId="BodyText".*?</w:style>', out, re.S).group(0)
        self.assertIn('<w:name w:val="Body Text"/>', body)
        self.assertIn('w:firstLine="720"', body)
        self.assertIn('w:styleId="Compact"', out)
        ElementTree.fromstring(out)

    def test_title_page_and_replace_reach_the_package(self):
        spec = spec_from_metadata({}, {"title-page": True, "replace": {"KICKER": "Course & Report"}})
        self.assertTrue(spec.title_page)
        document = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                    '<w:sectPr><w:headerReference w:type="default" r:id="x"/><w:pgSz w:w="1" w:h="2"/></w:sectPr></w:body></w:document>')
        patched = docx.patch_document(document, spec)
        self.assertLess(patched.index("pgSz"), patched.index("titlePg"))


@unittest.skipUnless(PANDOC and shutil.which("kpsewhich"), "needs Pandoc and kpsewhich")
class PackageDefaults(unittest.TestCase):
    def test_a_package_ships_its_word_support_beside_its_sty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "tex" / "mypkg"
            (package / "office").mkdir(parents=True)
            (package / "mypkg.sty").write_text("\\ProvidesPackage{mypkg}\n", encoding="utf-8")
            reference = zipfile.ZipFile(io.BytesIO(docx.default_reference()))
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w") as target:
                for item in reference.infolist():
                    content = reference.read(item.filename)
                    if item.filename == "word/styles.xml":
                        content = content.replace(b"</w:styles>", b'<w:style w:type="paragraph" w:customStyle="1" w:styleId="MyH">'
                                                  b'<w:name w:val="My H"/><w:basedOn w:val="Normal"/><w:rPr><w:color w:val="FF0000"/>'
                                                  b'</w:rPr></w:style></w:styles>')
                    target.writestr(item, content)
            (package / "office" / "mypkg-reference.docx").write_bytes(out.getvalue())
            (package / "office" / "mypkg-office.yaml").write_text(
                "styles: {Heading1: MyH}\nby-option:\n  fancy: {title-page: true}\n", encoding="utf-8")
            work = root / "doc"
            work.mkdir()
            (work / "preamble.tex").write_text("\\usepackage[fancy]{mypkg}\n", encoding="utf-8")
            (work / "d.md").write_text("---\ntitle: T\n---\n\n# Head\n\nText.\n", encoding="utf-8")
            environment = {**os.environ, "PDFMD_CONFIG": "", "TEXINPUTS": f"{root / 'tex'}//:"}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-o", "d.docx", "-v"], cwd=work,
                                  capture_output=True, text=True, env=environment)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("shipped with the mypkg package", done.stdout)
            archive = zipfile.ZipFile(work / "d.docx")
            styles = archive.read("word/styles.xml").decode()
            heading = re.search(r'w:styleId="Heading1".*?</w:style>', styles, re.S).group(0)
            self.assertIn('w:val="FF0000"', heading)                       # Heading 1 looks like the package's MyH
            self.assertRegex(archive.read("word/document.xml").decode(), r"<w:titlePg\s*/>")   # by-option: fancy
