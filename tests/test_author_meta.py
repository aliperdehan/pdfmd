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

    def test_nameless_authors(self):
        self.assertEqual(pdfmd.pdfmd_native.nameless_authors([{"affiliation": "NU"}, "Bob", {"name": "A"}, {"email": "e"}]), [1, 4])
        self.assertEqual(pdfmd.pdfmd_native.nameless_authors({"affiliation": "NU"}), [1])
        for value in (["A", {"name": "B"}], "A", None, [], {"name": "A"}):
            self.assertEqual(pdfmd.pdfmd_native.nameless_authors(value), [])

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

    def test_an_author_without_a_name_is_left_out_not_printed_as_true(self):
        """v3.33.63: Pandoc printed a mapping without `name` as `true` in LaTeX's \\author, Typst's title block and Author, and
        HTML's title block."""
        latex, typst, html = (self.convert(NAMELESS, writer) for writer in ("latex", "typst", "html5"))
        self.assertIn("\\author{true}", latex)                     # Bob Baker's own mapping: LaTeX's template reads no `name`
        self.assertIn("\\author{Bob Baker}", self.convert("author:\n  - affiliation: NU\n  - Bob Baker\n", "latex"))
        self.assertNotIn("true", typst.split("#show: doc => conf(")[1])
        self.assertIn("name: [Bob Baker]", typst)
        self.assertIn('<meta name="author" content="Bob Baker" />', html)
        html = self.convert("author:\n  - affiliation: NU\n  - Bob Baker\n", "html5")    # (a mapping's name: not read there either)
        self.assertNotIn(">true<", html)
        self.assertIn('<p class="author">Bob Baker</p>', html)
        alone = self.convert("author:\n  affiliation: NU\n", "latex")
        self.assertIn("\\author{}", alone)                              # none left: as with no author at all
        self.assertNotIn("true", self.convert("author:\n  - affiliation: NU\n  - email: e@x\n", "typst").split("#show: doc => conf(")[1])

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


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Nameless(unittest.TestCase):
    def test_one_warning_an_entry_once_a_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "doc.md").write_text("---\ntitle: T\nauthor:\n  - affiliation: NU\n  - Bob\n  - email: e@x\n---\n\nWords.\n",
                                         encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", "html", "--no-stamp"],
                                  cwd=root, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                  env={**os.environ, "PDFMD_CONFIG": "", **cache_env(root / "cache"),
                                       "XDG_CONFIG_HOME": str(root / "config"), "APPDATA": str(root / "config"),
                                       "PDFMD_NO_PROMPT": "1"})
            self.assertEqual(done.returncode, 0, done.stderr)
            warned = [line for line in done.stderr.splitlines() if line.startswith("WARN")]
            self.assertEqual([line.split("doc.md: ", 1)[1] for line in warned],
                             ["author entry 1 has no name: left out", "author entry 3 has no name: left out"], done.stderr)


TYPST_LUA = ROOT / "lib" / "pdfmd_lua" / "typst.lua"
WRAPPED = ('author:\n  - "`#text(font: (\\"X Serif\\",), lang: \\"zh\\")[`{=typst}李雷`]`{=typst}"\n  - Alice Able\n'
           '  - name: "`#text(font: (\\"X Serif\\",), lang: \\"zh\\")[`{=typst}山田 太郎`]`{=typst}"\n'
           '  - "Kim `#text(font: (\\"Y Gothic\\",), lang: \\"ko\\")[`{=typst}김민준`]`{=typst}"\n')


@unittest.skipUnless(PANDOC, "needs Pandoc")
class TypstAuthorFonts(unittest.TestCase):
    """v3.33.65: a name pdfmd's font filter set in another script's font (`#text(font: ...)[...]`) was dropped from a Typst
    PDF's Author (Pandoc's template reads no styled content), and one alone stopped the build."""

    def convert(self, front: str) -> str:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "doc.md"
            source.write_text(f"---\ntitle: T\n{front}---\n\nx\n", encoding="utf-8")
            done = subprocess.run([PANDOC, str(source), "-s", "-t", "typst", "--lua-filter", str(TYPST_LUA)],
                                  capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(done.returncode, 0, done.stderr)
            return done.stdout

    def test_each_run_is_a_labelled_box_with_one_rule_a_font(self):
        out = self.convert(WRAPPED)
        self.assertIn('#show <pdfmd-author-font-1>: set text(font: ("X Serif",), lang: "zh")', out)
        self.assertIn('#show <pdfmd-author-font-2>: set text(font: ("Y Gothic",), lang: "ko")', out)
        self.assertEqual(out.count("#show <pdfmd-author-font-"), 2)                     # one rule for each font setting
        self.assertIn("#box[李雷]<pdfmd-author-font-1>", out)
        self.assertIn("#box[山田 太郎]<pdfmd-author-font-1>", out)
        self.assertIn("Kim #box[김민준]<pdfmd-author-font-2>", out)
        self.assertNotIn("#text(font:", out)
        self.assertLess(out.index("#show <pdfmd-author-font-1>"), out.index("#show: doc => conf("))

    def test_names_without_a_font_run_are_as_before(self):
        for front in (STRINGS, MAPS, UNICODE):
            with self.subTest(front):
                with tempfile.TemporaryDirectory() as folder:
                    source = Path(folder) / "doc.md"
                    source.write_text(f"---\ntitle: T\n{front}---\n\nx\n", encoding="utf-8")
                    plain = subprocess.run([PANDOC, str(source), "-s", "-t", "typst"], capture_output=True, text=True,
                                           encoding="utf-8").stdout
                self.assertEqual(self.convert(front), plain)

    @unittest.skipUnless(shutil.which("typst"), "needs Typst")
    def test_the_pdfs_author_holds_the_names(self):
        try:
            import pypdf
        except ImportError:
            self.skipTest("needs pypdf")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, front, expected in (("many", "author:\n  - 李雷\n  - Alice Able\n  - name: 山田太郎\n  - 김민준\n",
                                           "李雷, Alice Able, 山田太郎 & 김민준"),
                                          ("one", "author: 山田太郎\n", "山田太郎")):           # one alone stopped the build
                with self.subTest(name):
                    (root / f"{name}.md").write_text(f"---\ntitle: T\n{front}---\n\nWords.\n", encoding="utf-8")
                    done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), f"{name}.md", "-e", "typst", "--no-stamp"],
                                          cwd=root, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                          env={**os.environ, "PDFMD_NO_PROMPT": "1"})
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(pypdf.PdfReader(str(root / f"{name}.pdf")).metadata.get("/Author"), expected)


if __name__ == "__main__":
    unittest.main()
