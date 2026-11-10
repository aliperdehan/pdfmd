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
        self.assertNotIn("[true]", typst)                               # (an author's name is `[...]` in Typst)
        self.assertIn("name: [Bob Baker]", typst)
        self.assertIn('<meta name="author" content="Bob Baker" />', html)
        html = self.convert("author:\n  - affiliation: NU\n  - Bob Baker\n", "html5")    # (a mapping's name: not read there either)
        self.assertNotIn(">true<", html)
        self.assertIn('<p class="author">Bob Baker</p>', html)
        alone = self.convert("author:\n  affiliation: NU\n", "latex")
        self.assertIn("\\author{}", alone)                              # none left: as with no author at all
        self.assertNotIn("[true]", self.convert("author:\n  - affiliation: NU\n  - email: e@x\n", "typst"))

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


class Prince(unittest.TestCase):
    """v3.33.66: Prince takes the first `<meta name="author">` of the page alone: a PDF of two authors named one."""

    def options(self, front: str) -> list[str]:
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "doc.md"
            document.write_text(f"---\ntitle: T\n{front}---\n\nx\n", encoding="utf-8")
            return pdfmd.prince_author_options(document, [], [])

    def test_two_names_or_more_are_given_joined_as_weasyprint_joins_them(self):
        self.assertEqual(self.options(STRINGS), ["--pdf-engine-opt=--pdf-author=Alice Able, Bob Baker"])
        self.assertEqual(self.options(MAPS), ["--pdf-engine-opt=--pdf-author=Alice Able, Bob Baker"])
        self.assertEqual(self.options(MIXED), ["--pdf-engine-opt=--pdf-author=Alice Able, Bob Baker"])
        self.assertEqual(self.options(UNICODE), ["--pdf-engine-opt=--pdf-author=Ərlan Şükürov, 李雷, Zoë Ångström"])

    def test_one_name_its_own_author_meta_and_latex_are_left_to_the_page(self):
        for front in ("author: Bob\n", "author:\n  name: Bob\n", NAMELESS, STRINGS + "author-meta: Mine\n",
                      "author:\n  - Jane \\emph{x} Doe\n  - Bob\n", ""):
            with self.subTest(front):
                self.assertEqual(self.options(front), [])

    @unittest.skipUnless(PANDOC and shutil.which("prince"), "needs Pandoc and Prince")
    def test_through_pdfmd_the_pdf_names_both(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "doc.md").write_text(f"---\ntitle: T\n{MIXED}---\n\nWords.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "prince", "--no-stamp"],
                                  cwd=root, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                  env={**os.environ, "PDFMD_NO_PROMPT": "1"})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            try:
                import pypdf
            except ImportError:
                self.skipTest("needs pypdf")
            self.assertEqual(pypdf.PdfReader(str(root / "doc.pdf")).metadata.get("/Author"), "Alice Able, Bob Baker")



def pdfmd_run(root: Path, *args: str, config: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args, "--no-stamp", "--no-backup"], cwd=root, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL,
                          env={**os.environ, "PDFMD_CONFIG": config, **cache_env(root / "cache"),
                               "XDG_CONFIG_HOME": str(root / "config"), "APPDATA": str(root / "config"), "PDFMD_NO_PROMPT": "1"})


@unittest.skipUnless(PANDOC, "needs Pandoc")
class TitleBlock(unittest.TestCase):
    """v3.33.69: an author written as a mapping WITH a `name` was `true` in LaTeX's \\author and HTML's title block (Pandoc's
    templates read no `name`). title_meta.lua writes the name in its place when pdfmd gives it `pdfmd-author-names`: only where
    nothing after pdfmd's filters reads the mapping (no kit, no own template, no Lua filter of the document's own)."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pdfmd-author-title-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def convert(self, front: str, writer: str, flag: bool = True) -> str:
        source = self.root / "doc.md"
        source.write_text(f"---\ntitle: T\n{front}---\n\nx\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-s", "-t", writer, *(["-M", "pdfmd-author-names=true"] if flag else []),
                               "--lua-filter", str(TITLE_META)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_the_filter_writes_the_names_in_latex_beamer_and_html(self):
        self.assertIn(r"\author{Alice Able \and Bob Baker}", self.convert(MAPS, "latex"))
        self.assertIn(r"\author{Alice Able \and Bob Baker}", self.convert(MIXED, "latex"))
        self.assertIn(r"\author{Bob Baker}", self.convert("author:\n  name: Bob Baker\n  affiliation: NU\n", "latex"))
        self.assertIn(r"\texorpdfstring{Alice Able \and Bob Baker}", self.convert(MAPS, "beamer"))
        page = self.convert(MAPS, "html5")
        self.assertIn('<p class="author">Alice Able</p>\n<p class="author">Bob Baker</p>', page)
        self.assertNotIn(">true<", page)
        self.assertIn("pdfauthor={Alice Able; Bob Baker},", self.convert(MAPS, "latex"))          # the PDF's Author as before
        self.assertNotIn("pdfmd-author-names", self.convert(MAPS, "latex"))

    def test_without_the_flag_and_in_typst_nothing_changes(self):
        self.assertIn(r"\author{true \and true}", self.convert(MAPS, "latex", flag=False))
        self.assertEqual(self.convert(MAPS, "typst"), self.convert(MAPS, "typst", flag=False))

    def test_through_pdfmd_where_nothing_else_reads_the_mapping(self):
        (self.root / "doc.md").write_text(f"---\ntitle: T\n{MAPS}---\n\nx\n", encoding="utf-8")
        done = pdfmd_run(self.root, "doc.md", "--to", "latex", "-o", "doc.tex")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(r"\author{Alice Able \and Bob Baker}", (self.root / "doc.tex").read_text(encoding="utf-8"))
        done = pdfmd_run(self.root, "doc.md", "--to", "html", "-s", "-o", "doc.html")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('<p class="author">Alice Able</p>', (self.root / "doc.html").read_text(encoding="utf-8"))

    def test_strings_alone_get_no_flag(self):
        for front in (STRINGS, "author: Bob\n", NAMELESS.replace("  - name: Bob Baker\n", "  - Bob Baker\n"), ""):
            (self.root / "doc.md").write_text(f"---\ntitle: T\n{front}---\n\nx\n", encoding="utf-8")
            self.assertNotIn("pdfmd-author-names=true", pdfmd.title_filter_args(self.root / "doc.md", []), front)

    def test_a_documents_own_filter_a_template_or_a_kit_keeps_the_mapping(self):
        (self.root / "doc.md").write_text(f"---\ntitle: T\n{MAPS}---\n\nx\n", encoding="utf-8")
        self.assertIn("pdfmd-author-names=true", pdfmd.title_filter_args(self.root / "doc.md", [], []))
        self.assertNotIn("pdfmd-author-names=true", pdfmd.title_filter_args(self.root / "doc.md", [], ["--template", "x.latex"]))
        (self.root / "doc.lua").write_text("function Meta(m) io.stderr:write('AFFILIATION ', pandoc.utils.stringify("
                                           "m.author[1].affiliation), '\\n') end\n", encoding="utf-8")
        self.assertNotIn("pdfmd-author-names=true", pdfmd.title_filter_args(self.root / "doc.md", [], []))
        done = pdfmd_run(self.root, "doc.md", "--to", "latex", "-o", "doc.tex")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("AFFILIATION NU", done.stdout + done.stderr)                      # the document's own filter still reads the mapping
        (self.root / "doc.lua").unlink()
        kits = self.root / "kits"
        (kits / "house").mkdir(parents=True)
        (kits / "house" / ".kit").write_text("kit-format: 1\nname: house\n", encoding="utf-8")
        config = self.root / "cfg.yaml"
        config.write_text(f"kits: [{kits}]\n", encoding="utf-8")
        (self.root / "doc.md").write_text(f"---\ntitle: T\n{MAPS}pdfmd-options: {{kit: house}}\n---\n\nx\n", encoding="utf-8")
        done = pdfmd_run(self.root, "doc.md", "--to", "latex", "-o", "doc.tex", "--verbose", config=str(config))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("AUTO KIT", done.stdout + done.stderr)
        self.assertNotIn("pdfmd-author-names", done.stdout + done.stderr)

    @unittest.skipUnless(shutil.which("lualatex") and shutil.which("pdftotext"), "needs LuaLaTeX and pdftotext")
    def test_the_rendered_title_names_them(self):
        (self.root / "doc.md").write_text(f"---\ntitle: T\n{MIXED}---\n\nWords.\n", encoding="utf-8")
        done = pdfmd_run(self.root, "doc.md", "-o", "doc.pdf", "-e", "lualatex")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = subprocess.run(["pdftotext", "-l", "1", str(self.root / "doc.pdf"), "-"], capture_output=True, text=True).stdout
        self.assertIn("Bob Baker", text)
        self.assertNotIn("true", text)


if __name__ == "__main__":
    unittest.main()
