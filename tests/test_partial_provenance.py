"""A partial parts build (`report#introduction`) is not the report: no BUILD NOTES stamp in the source, but its PDF still says what made it
(Creator, PdfmdVersions, PdfmdBuildDate, and PdfmdPartial naming the parts)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

try:
    import pypdf
except ImportError:                                           # pragma: no cover
    pypdf = None

PANDOC = shutil.which("pandoc")
ENGINES = [name for name in ("lualatex", "xelatex", "pdflatex") if shutil.which(name)]


class Pieces(unittest.TestCase):
    def test_the_parts_a_partial_build_holds_come_from_its_output_name(self):
        self.assertEqual(pdfmd.partial_parts_label(Path("report.md"), Path("report.introduction+procedure.pdf")), "introduction+procedure")
        self.assertEqual(pdfmd.partial_parts_label(Path("report.md"), Path("other.pdf")), "other")
        self.assertEqual(pdfmd.partial_parts_label(Path("report.md"), Path("report.pdf")), "report")



@unittest.skipUnless(PANDOC and ENGINES and pypdf is not None, "needs Pandoc, a LaTeX engine and pypdf")
class Builds(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-partial-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "parts").mkdir()
        self.scaffold = self.directory / "report.md"
        self.scaffold.write_text("---\ntitle: Report\nauthor: A\npdfmd-options:\n  parts: auto\n  stamp: true\n---\n", encoding="utf-8")
        for name in ("10-introduction", "20-procedure", "30-results"):
            (self.directory / "parts" / f"{name}.md").write_text(f"# {name[3:]}\n\nText of {name}.\n", encoding="utf-8")

    def run_pdfmd(self, *args: str, config: str = ""):
        environment = {**os.environ, "PDFMD_CONFIG": config, "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args, "-e", ENGINES[0], "--no-cache"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8", env=environment)

    def info(self, name: str) -> dict:
        return {key: str(value) for key, value in (pypdf.PdfReader(self.directory / name).metadata or {}).items()}

    def test_a_partial_pdf_says_what_made_it_and_the_source_is_left_alone(self):
        before = self.scaffold.read_bytes(), (self.directory / "parts" / "10-introduction.md").read_bytes()
        done = self.run_pdfmd("report#introduction+procedure")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        info = self.info("report.introduction+procedure.pdf")
        self.assertTrue(info["/Creator"].endswith("via pdfmd-cli"), info)
        self.assertIn("pdfmd v", info["/PdfmdVersions"])
        self.assertRegex(info["/PdfmdBuildDate"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
        self.assertEqual(info["/PdfmdPartial"], "introduction+procedure")
        self.assertEqual((self.scaffold.read_bytes(), (self.directory / "parts" / "10-introduction.md").read_bytes()), before)
        self.assertNotIn("BUILD NOTES", self.scaffold.read_text(encoding="utf-8"))

    def test_the_whole_report_has_the_same_properties_without_partial_and_is_stamped(self):
        done = self.run_pdfmd("report.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        info = self.info("report.pdf")
        self.assertTrue(info["/Creator"].endswith("via pdfmd-cli"), info)
        self.assertIn("/PdfmdVersions", info)
        self.assertNotIn("/PdfmdPartial", info)
        self.assertIn("BUILD NOTES", self.scaffold.read_text(encoding="utf-8"))          # (the stamp of a whole build is as before)

    def test_a_word_file_of_a_partial_build_builds_and_leaves_the_source_alone(self):
        before = self.scaffold.read_bytes()
        done = self.run_pdfmd("report#introduction", "--to", "docx")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "report.introduction.docx").is_file())
        self.assertEqual(self.scaffold.read_bytes(), before)



@unittest.skipUnless(pypdf, "needs pypdf")
class OutlineSurvives(unittest.TestCase):
    def test_bookmarks_calibre_writes_are_kept(self):
        """Calibre 9.16 types every bookmark `/Type /Outlines` (a bookmark is not an outline); pypdf's append() dropped the
        whole outline then, and the stamp of the finished PDF went through append()"""
        from pypdf.generic import NameObject
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "calibre.pdf"
            writer = pypdf.PdfWriter()
            writer.add_blank_page(200, 200)
            writer.add_outline_item("Introduction", 0).get_object()[NameObject("/Type")] = NameObject("/Outlines")
            writer.write(path)
            self.assertEqual([entry.title for entry in pypdf.PdfReader(str(path)).outline], ["Introduction"])
            pdfmd.stamp_pdf_metadata_posthoc(path, {**pdfmd.DEFAULT_STAMP_OPTIONS, "pdf_metadata": True}, [], False)
            reader = pypdf.PdfReader(str(path))
            self.assertIn("PdfmdVersions", str(reader.metadata))
            self.assertEqual([entry.title for entry in reader.outline], ["Introduction"])


if __name__ == "__main__":
    unittest.main()
