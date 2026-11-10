"""An author written as a mapping (`- name: Jane Doe` with an `affiliation:`) in a PDF's Author (v3.33.56). Pandoc's
`author-meta` (hyperref's pdfauthor, an HTML page's `<meta name="author">`) holds the authors written as text only, so two
mappings gave no author and a string and a mapping only the string. pdfmd_lua/title_meta.lua now sets it from the names,
joined as Pandoc joins authors written as text; a document whose authors are all text is built as before."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from cache_support import cache_env  # noqa: E402

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
TITLE_META = ROOT / "lib" / "pdfmd_lua" / "title_meta.lua"

MAPS = "author:\n  - name: Alice Able\n    affiliation: NU\n  - name: Bob Baker\n"
MIXED = "author:\n  - Alice Able\n  - name: Bob Baker\n    affiliation: NU\n"
PUNCT = "author:\n  - name: \"Doe, Jane\"\n  - name: \"Smith & Wesson; Ltd\"\n  - \"O%Brien\"\n"
NAMELESS = "author:\n  - affiliation: NU\n  - name: Bob Baker\n"
UNICODE = "author:\n  - name: Ərlan Şükürov\n  - name: 李雷\n  - Zoë Ångström\n"
STRINGS = "author:\n  - Alice Able\n  - Bob Baker\n"


class Predicate(unittest.TestCase):
    def test_mapped_author(self):
        self.assertTrue(pdfmd.mapped_author([{"name": "A"}]))
        self.assertTrue(pdfmd.mapped_author(["A", {"name": "B"}]))
        self.assertTrue(pdfmd.mapped_author({"name": "A"}))
        self.assertFalse(pdfmd.mapped_author(["A", "B"]))
        self.assertFalse(pdfmd.mapped_author("A"))
        self.assertFalse(pdfmd.mapped_author(None))

    def test_the_filter_runs_for_a_mapping_and_not_for_text(self):
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "doc.md"
            for front, wanted in ((MAPS, True), (MIXED, True), ("author:\n  name: A\n", True), (STRINGS, False), ("", False)):
                document.write_text(f"---\ntitle: T\n{front}---\n\nx\n", encoding="utf-8")
                self.assertEqual("title_meta.lua" in " ".join(pdfmd.title_filter_args(document, [])), wanted, front)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-author-meta-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def convert(self, front: str, writer: str) -> str:
        source = self.directory / "doc.md"
        source.write_text(f"---\ntitle: T\n{front}---\n\nx\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-s", "-t", writer, "--lua-filter", str(TITLE_META)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_latex_joins_the_names_as_pandoc_joins_text(self):
        cases = {MAPS: "pdfauthor={Alice Able; Bob Baker},", MIXED: "pdfauthor={Alice Able; Bob Baker},",
                 PUNCT: r"pdfauthor={Doe, Jane; Smith \& Wesson; Ltd; O\%Brien},",
                 NAMELESS: "pdfauthor={Bob Baker},", UNICODE: "pdfauthor={Ərlan Şükürov; 李雷; Zoë Ångström},"}
        for front, expected in cases.items():
            self.assertIn(expected, self.convert(front, "latex"), front)
        self.assertIn("pdfauthor={Alice Able; Bob Baker},", self.convert(MAPS, "beamer"))
        self.assertNotIn("NU", self.convert(MAPS, "latex").split("pdfauthor=")[1].split("\n")[0])

    def test_html_writes_one_tag_a_name(self):
        page = self.convert(PUNCT, "html5")
        self.assertIn('<meta name="author" content="Doe, Jane" />\n'
                      '  <meta name="author" content="Smith &amp; Wesson; Ltd" />\n'
                      '  <meta name="author" content="O%Brien" />', page)
        self.assertEqual(self.convert(MIXED, "html5").count('<meta name="author"'), 2)
        self.assertEqual(self.convert(NAMELESS, "html5").count('<meta name="author"'), 1)

    def test_a_documents_own_author_meta_stays(self):
        self.assertIn("pdfauthor={Mine},", self.convert(MAPS + "author-meta: Mine\n", "latex"))

    def test_typst_is_left_to_its_template(self):
        self.assertEqual(self.convert(MAPS, "typst"),
                         subprocess.run([PANDOC, str(self.directory / "doc.md"), "-s", "-t", "typst"], capture_output=True,
                                        text=True, encoding="utf-8").stdout)


@unittest.skipUnless(PANDOC and shutil.which("lualatex"), "needs Pandoc and LuaLaTeX")
class Build(unittest.TestCase):
    def test_a_pdfs_author(self):
        try:
            import pypdf
        except ImportError:
            self.skipTest("needs pypdf")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "doc.md").write_text(f"---\ntitle: T\n{MIXED}---\n\nWords.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-o", "doc.pdf", "--no-stamp"],
                                  cwd=root, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                  env={**os.environ, "PDFMD_CONFIG": "", **cache_env(root / "cache"),
                                       "XDG_CONFIG_HOME": str(root / "config"), "APPDATA": str(root / "config"),
                                       "PDFMD_NO_PROMPT": "1"})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(pypdf.PdfReader(str(root / "doc.pdf")).metadata.get("/Author"), "Alice Able; Bob Baker")


if __name__ == "__main__":
    unittest.main()
