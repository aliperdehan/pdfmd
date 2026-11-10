"""`-e calibre` (v3.28.0): Calibre's ebook-convert as a PDF engine, used only when named. Pandoc writes one HTML page
and ebook-convert prints it with the document's page, the headings as bookmarks."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from cache_support import cache_env  # noqa: E402

import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402


class Finding(unittest.TestCase):
    def test_on_the_path_first(self):
        with mock.patch.object(pdfmd, "which", lambda name: "/opt/bin/ebook-convert" if name == "ebook-convert" else None):
            self.assertEqual(pdfmd.resolve_calibre(), "/opt/bin/ebook-convert")
            self.assertEqual(pdfmd.engine_executable("calibre"), "/opt/bin/ebook-convert")

    def test_where_the_windows_installer_puts_it(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / "Calibre2" / "ebook-convert.exe"
            binary.parent.mkdir()
            binary.write_bytes(b"")
            with mock.patch.object(pdfmd, "which", lambda name: None), mock.patch.object(pdfmd.sys, "platform", "win32"), \
                    mock.patch.dict(os.environ, {"ProgramFiles": folder, "ProgramW6432": "", "ProgramFiles(x86)": "",
                                                 "LOCALAPPDATA": "", "PDFMD_NO_APP_PATHS": "1"}):
                self.assertEqual(pdfmd.resolve_calibre(), str(binary))

    def test_not_installed(self):
        with tempfile.TemporaryDirectory() as data, mock.patch.dict(os.environ, {"XDG_DATA_HOME": data}), \
                mock.patch.object(pdfmd, "which", lambda name: None), mock.patch.object(pdfmd.sys, "platform", "linux"):
            os.environ.pop("PDFMD_CALIBRE", None)
            self.assertIsNone(pdfmd.resolve_calibre())        # (pdfmd's own folder is under XDG_DATA_HOME: a real install must not count)


class Choosing(unittest.TestCase):
    def select(self, requested, calibre="/opt/bin/ebook-convert", presentation=False):
        installed = {"pandoc", "lualatex", "typst"}
        with mock.patch.object(pdfmd, "which", lambda name: f"/opt/bin/{name}" if name in installed else None), \
                mock.patch.object(pdfmd, "resolve_calibre", lambda: calibre), \
                mock.patch.object(pdfmd, "resolve_soffice", lambda: None), \
                mock.patch("pdfmd_direct.find_browser", lambda name, which=None: None):
            return pdfmd.select_engines(requested, presentation)

    def test_named_it_is_the_only_engine_and_unnamed_it_is_a_last_resort(self):
        self.assertEqual(self.select("calibre"), ["calibre"])
        self.assertEqual(self.select("ebook-convert"), ["calibre"])
        self.assertEqual(self.select(None), ["lualatex", "typst", "calibre"])      # v3.29.1: after the numbered engines
        self.assertEqual(self.select(None, calibre=None), ["lualatex", "typst"])
        self.assertNotIn("calibre", pdfmd.PDF_ENGINES)                              # and it has no number

    def test_not_installed_says_how_to_get_it(self):
        with self.assertRaises(SystemExit) as raised:
            self.select("calibre", calibre=None)
        self.assertIn("Install Calibre", str(raised.exception))

    def test_no_slides(self):
        with self.assertRaises(SystemExit) as raised:
            self.select("calibre", presentation=True)
        self.assertIn("Beamer", str(raised.exception))

    def test_dependency_report_names_it(self):
        shown = io.StringIO()
        with mock.patch.object(pdfmd, "resolve_calibre", lambda: "/opt/bin/ebook-convert"), redirect_stdout(shown):
            pdfmd.dependency_report()
        self.assertIn("OK    calibre (only when named: -e calibre)  (/opt/bin/ebook-convert)", shown.getvalue())


class Commands(unittest.TestCase):
    def test_pandoc_writes_one_html_page_instead(self):
        cmd = ["pandoc", "doc.md", "-o", "doc.pdf", "--pdf-engine=calibre", "--citeproc"]
        with mock.patch.object(pdfmd, "html_math_args", lambda method: [f"--math-method={method}"]), \
                mock.patch.object(pdfmd, "pandoc_version", lambda: (3, 12)):
            with pdfmd.calibre_html_command(cmd, "calibre") as (command, html):
                self.assertEqual(command[:3], ["pandoc", "doc.md", "-o"])
                self.assertEqual(command[3], str(html))
                self.assertEqual(command[4:8], ["-t", "html5", "--standalone", "--embed-resources"])
                self.assertIn("--citeproc", command)
                self.assertEqual(command[-1], "--math-method=mathml")
                self.assertNotIn("--pdf-engine=calibre", command)
                self.assertTrue(html.parent.is_dir())
            self.assertFalse(html.parent.exists())
            with pdfmd.calibre_html_command([*cmd, "--mathjax"], "calibre") as (command, _):
                self.assertNotIn("--math-method=mathml", command)          # the command line chose the math
        with pdfmd.calibre_html_command(cmd, "typst") as (command, html):
            self.assertEqual((command, html), (cmd, None))

    def test_the_documents_page(self):
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "doc.md"
            document.write_text("---\npapersize: a5\nclassoption: landscape\ngeometry: margin=1cm\nlang: de-DE\n---\n\nx\n",
                                encoding="utf-8")
            options = pdfmd.calibre_page_options(document, [], [])
            plain = Path(folder) / "plain.md"
            plain.write_text("x\n", encoding="utf-8")
            default = pdfmd.calibre_page_options(plain, [], [])
        self.assertEqual(options[:4], ["--custom-size", "595.3x419.55", "--unit", "point"])
        self.assertEqual(options[4:6], ["--pdf-page-margin-left", "28.35"])
        self.assertEqual(options[-2:], ["--language", "de-DE"])
        self.assertEqual(default, ["--custom-size", "612x792", "--unit", "point", "--pdf-page-margin-left", "72",
                                   "--pdf-page-margin-right", "72", "--pdf-page-margin-top", "72",
                                   "--pdf-page-margin-bottom", "72"])

    def test_every_author_when_one_is_a_mapping(self):
        # v3.33.53: Pandoc's <meta name="author"> drops an author written as `- name: B`, so Calibre kept only the others
        cases = {"author:\n  - name: Alice Able\n  - name: Bob Baker\n": ["--authors", "Alice Able & Bob Baker"],
                 "author:\n  - Alice Able\n  - name: Bob Baker\n    affiliation: X\n": ["--authors", "Alice Able & Bob Baker"],
                 "author:\n  name: Alice Able\n": ["--authors", "Alice Able"],
                 "author:\n  - Alice Able\n  - Bob Baker\n": [],             # Pandoc names them itself
                 "author:\n  - name: Alice Able\nauthor-meta: Mine\n": [],      # the document's own
                 "": []}
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "doc.md"
            for front, expected in cases.items():
                document.write_text(f"---\ntitle: T\n{front}---\n\nx\n", encoding="utf-8")
                options = pdfmd.calibre_page_options(document, [], [])
                self.assertEqual(options[options.index("--authors"):] if "--authors" in options else [], expected, front)
                self.assertEqual(options[:4], ["--custom-size", "612x792", "--unit", "point"], front)

    def test_calibres_unknown_author_is_taken_out(self):
        # v3.33.55: ebook-convert names `Unknown` when it is given no author, in the Info dictionary and the XMP metadata
        try:
            import pypdf
            from pypdf.generic import DecodedStreamObject, NameObject
        except ImportError:
            self.skipTest("needs pypdf")
        xmp = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
               b'<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/" rdf:about="">'
               b'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">T</rdf:li></rdf:Alt></dc:title>\n      '
               b'<dc:creator>\n <rdf:Seq>\n <rdf:li>Unknown</rdf:li>\n </rdf:Seq>\n </dc:creator>'
               b'</rdf:Description></rdf:RDF></x:xmpmeta>')
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / "doc.pdf"
            writer = pypdf.PdfWriter()
            writer.add_blank_page(100, 100)
            writer.add_metadata({"/Title": "T", "/Author": "Unknown"})
            stream = DecodedStreamObject()
            stream.set_data(xmp)
            writer._root_object[NameObject("/Metadata")] = writer._add_object(stream)
            with open(pdf, "wb") as handle:
                writer.write(handle)
            pdfmd.pdfmd_bridge.drop_calibre_author(pdf, False)
            reader = pypdf.PdfReader(str(pdf))
            self.assertEqual(reader.metadata.get("/Title"), "T")
            self.assertNotIn("/Author", reader.metadata)
            data = reader.trailer["/Root"]["/Metadata"].get_object().get_data()
            self.assertNotIn(b"creator", data)
            self.assertIn(b"<dc:title>", data)
            self.assertEqual(reader.xmp_metadata.dc_title, {"x-default": "T"})


NARROW_TABLE = "| a |\n|---|\n| 1 |\n\n: A rather long caption for a narrow table, set whole\n"


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class TableStyle(unittest.TestCase):
    def test_only_while_pandocs_own_style_is_in(self):
        # v3.28.3: Pandoc's `table { display: block; overflow-x: auto }` cut a caption off at a narrow table's width
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "doc.md").write_text(NARROW_TABLE, encoding="utf-8")
            (Path(folder) / "own.css").write_text("", encoding="utf-8")
            for extra, expected in (([], True), (["--css", "own.css"], False)):
                page = subprocess.run(["pandoc", "doc.md", "-s", "-t", "html5", *extra], cwd=folder, capture_output=True,
                                      text=True, encoding="utf-8").stdout
                head = page.split("</head>", 1)[0]
                self.assertEqual(bool(pdfmd.PANDOC_TABLE_STYLE_RE.search(head)), expected, extra)
        self.assertIn('data-custom-style="PdfmdEquation"', pdfmd.CALIBRE_TABLE_CSS)


@unittest.skipUnless(shutil.which("pandoc") and pdfmd.resolve_calibre(), "needs Pandoc and Calibre")
class Builds(unittest.TestCase):
    def test_a_document(self):
        try:
            import pypdf
        except ImportError:
            self.skipTest("needs pypdf")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "doc.md").write_text(
                "---\ntitle: Trial\npapersize: a4\n---\n\n# Introduction\n\nWords and $E = mc^2$.\n\n"
                "| a | b |\n|---|---|\n| 1 | 2 |\n\n# Second section\n\nMore words.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "calibre", "-o", "doc.pdf"],
                                  cwd=root, capture_output=True, text=True,
                                  env={**os.environ, "PDFMD_CONFIG": "", **cache_env(root / "cache"),
                                       "XDG_CONFIG_HOME": str(root / "config"), "APPDATA": str(root / "config"), "PDFMD_NO_PROMPT": "1"})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("(calibre)", done.stdout)
            reader = pypdf.PdfReader(str(root / "doc.pdf"))
            box = reader.pages[0].mediabox
            self.assertAlmostEqual(float(box.width), 595.3, delta=1)        # A4, not Calibre's Letter
            self.assertEqual([item.title for item in reader.outline], ["Introduction", "Second section"])
            text = "".join(page.extract_text() for page in reader.pages)
            self.assertIn("More words.", text)
            self.assertEqual(len(reader.pages), 1)      # no page break before each section, 12pt text

    def test_every_author_reaches_the_pdf(self):
        try:
            import pypdf
        except ImportError:
            self.skipTest("needs pypdf")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "doc.md").write_text("---\ntitle: Trial\nauthor:\n  - Alice Able\n  - name: Bob Baker\n---\n\nWords.\n",
                                         encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "calibre", "-o", "doc.pdf"],
                                  cwd=root, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                  env={**os.environ, "PDFMD_CONFIG": "", **cache_env(root / "cache"),
                                       "XDG_CONFIG_HOME": str(root / "config"), "APPDATA": str(root / "config"), "PDFMD_NO_PROMPT": "1"})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(pypdf.PdfReader(str(root / "doc.pdf")).metadata.get("/Author"), "Alice Able & Bob Baker")

    def test_no_author_is_no_author(self):
        # v3.33.55: Calibre wrote `Unknown` for a document with no author; an author named Unknown is still one
        try:
            import pypdf
        except ImportError:
            self.skipTest("needs pypdf")
        cases = {"title: Trial\n": None, "title: Trial\nauthor:\n  - affiliation: X\n": None,
                 "title: Trial\nauthor: Unknown\n": "Unknown"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for front, expected in cases.items():
                (root / "doc.md").write_text(f"---\n{front}---\n\nWords.\n", encoding="utf-8")
                done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "calibre", "-o", "doc.pdf"],
                                      cwd=root, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                      env={**os.environ, "PDFMD_CONFIG": "", **cache_env(root / "cache"),
                                           "XDG_CONFIG_HOME": str(root / "config"), "APPDATA": str(root / "config"),
                                           "PDFMD_NO_PROMPT": "1"})
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                reader = pypdf.PdfReader(str(root / "doc.pdf"))
                self.assertEqual(reader.metadata.get("/Author"), expected, front)
                self.assertEqual(reader.metadata.get("/Title"), "Trial", front)
                xmp = reader.xmp_metadata
                self.assertEqual(xmp.dc_creator if xmp else [], [expected] if expected else [], front)

    def test_a_caption_is_not_cut_off_at_its_tables_width(self):
        # v3.28.3: it read "Table 1: A rather / long / caption / for a / narrow" and the rest of each line was gone
        try:
            import pypdf
        except ImportError:
            self.skipTest("needs pypdf")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "doc.md").write_text("---\ntitle: Trial\n---\n\n" + NARROW_TABLE, encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "calibre", "-o", "doc.pdf"],
                                  cwd=root, capture_output=True, text=True,
                                  env={**os.environ, "PDFMD_CONFIG": "", **cache_env(root / "cache"),
                                       "XDG_CONFIG_HOME": str(root / "config"), "APPDATA": str(root / "config"), "PDFMD_NO_PROMPT": "1"})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            text = " ".join("".join(page.extract_text() for page in pypdf.PdfReader(str(root / "doc.pdf")).pages).split())
            self.assertIn("A rather long caption for a narrow table, set whole", text)


if __name__ == "__main__":
    unittest.main()
