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
                                       "XDG_CONFIG_HOME": str(root / "config"), "PDFMD_NO_PROMPT": "1"})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("(calibre)", done.stdout)
            reader = pypdf.PdfReader(str(root / "doc.pdf"))
            box = reader.pages[0].mediabox
            self.assertAlmostEqual(float(box.width), 595.3, delta=1)        # A4, not Calibre's Letter
            self.assertEqual([item.title for item in reader.outline], ["Introduction", "Second section"])
            text = "".join(page.extract_text() for page in reader.pages)
            self.assertIn("More words.", text)
            self.assertEqual(len(reader.pages), 1)      # no page break before each section, 12pt text

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
                                       "XDG_CONFIG_HOME": str(root / "config"), "PDFMD_NO_PROMPT": "1"})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            text = " ".join("".join(page.extract_text() for page in pypdf.PdfReader(str(root / "doc.pdf")).pages).split())
            self.assertIn("A rather long caption for a narrow table, set whole", text)


if __name__ == "__main__":
    unittest.main()
