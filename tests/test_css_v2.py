"""v3.29.8: a style sheet, the second round. Media queries are read as a browser prints (comma, only, not, orientation), and
`css-scope: all` turns the headings (h1-h5) into titlesec's starred formats, for the plain article class and never over a
document that formats its headings itself."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
import pdfmd_css  # noqa: E402

PANDOC = shutil.which("pandoc")


class Media(unittest.TestCase):
    def test_queries(self):
        cases = [("print", False, True), ("screen", False, False), ("print, screen", False, True), ("screen, print", False, True),
                 ("only print", False, True), ("only screen", False, False), ("not screen", False, True), ("not print", False, False),
                 ("all and (color)", False, True), ("print and (orientation: landscape)", False, False),
                 ("print and (orientation: landscape)", True, True), ("print and (orientation: portrait)", False, True),
                 ("print and (orientation: portrait)", True, False), ("(min-width: 600px)", False, False),
                 ("print and (prefers-color-scheme: dark)", False, False), ("speech", False, False)]
        for media, landscape, expected in cases:
            self.assertEqual(pdfmd_css.applies(media, landscape), expected, (media, landscape))

    def test_a_condition_of_the_screen_is_named(self):
        said: list[str] = []
        self.assertFalse(pdfmd_css.applies("(min-width: 600px)", False, said))
        self.assertEqual(said, ["(min-width: 600px)"])

    def test_the_sheet_s_own_page_decides_the_orientation(self):
        sheet = "@page { size: A4 landscape } @media print and (orientation: landscape) { body { font-size: 12pt } } " \
                "@media print and (orientation: portrait) { body { font-size: 10pt } }"
        self.assertIn("fontsize=12pt", pdfmd_css.translate(sheet).variables)
        portrait = "@media print and (orientation: portrait) { body { font-size: 10pt } }"
        self.assertIn("fontsize=10pt", pdfmd_css.translate(portrait).variables)

    def test_a_dropped_rule_says_why(self):
        result = pdfmd_css.translate("@media (min-width: 700px) { h4 { color: blue } }")
        self.assertIn("(min-width: 700px) is not for a printed page", " ".join(result.ignored))


class Headings(unittest.TestCase):
    def test_they_are_collected_for_each_level_in_order(self):
        result = pdfmd_css.translate("h1, h2 { color: #036; font-size: 1.6em } h2 { font-style: italic } h3 { margin: 0 } "
                                     "@media screen { h1 { color: red } }")
        self.assertEqual(result.headings[1], {"color": "#036", "font-size": "1.6em"})
        self.assertEqual(result.headings[2], {"color": "#036", "font-size": "1.6em", "font-style": "italic"})
        self.assertIn("h3 margin", result.ignored)

    def test_the_latex(self):
        said: list[str] = []
        lines = pdfmd.css_heading_latex({1: {"color": "darkgreen", "font-size": "2em"}, 2: {"font-weight": "400", "font-family": "Georgia, serif"},
                                         3: {"color": "#abc", "font-style": "italic"}, 6: {"color": "red"}}, 11, said.append)
        text = "\n".join(lines)
        self.assertIn("\\titleformat*{\\section}{\\normalfont\\fontsize{22}{26.4}\\selectfont\\bfseries\\color[HTML]{006400}}", text)
        self.assertIn("\\titleformat*{\\subsection}{\\normalfont\\pdfmdheadb\\large\\mdseries}", text)
        self.assertIn("\\newfontfamily\\pdfmdheadb{Georgia}", text)
        self.assertIn("\\titleformat*{\\subsubsection}{\\normalfont\\normalsize\\bfseries\\itshape\\color[HTML]{AABBCC}}", text)
        self.assertIn("\\usepackage{titlesec}", text)
        self.assertEqual(said, ["h6 (LaTeX has no sixth heading level)"])

    def test_a_property_that_is_not_understood_is_said(self):
        said: list[str] = []
        pdfmd.css_heading_latex({1: {"color": "rebeccapurple", "font-size": "large", "font-weight": "heavy"}}, 10, said.append)
        self.assertEqual(said, ["h1 font-size large", "h1 color rebeccapurple", "h1 font-weight heavy"])


class Args(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "d.md").write_text("---\ntitle: T\n---\n\n# H\n\ntext\n", encoding="utf-8")
        (self.root / "pdfmd.css").write_text("h1 { color: #003366; font-size: 2em }\n", encoding="utf-8")
        self.notes: list[tuple[str, str]] = []
        patch = mock.patch.object(pdfmd, "cache_root", lambda: self.root / "cache")
        patch.start()
        self.addCleanup(patch.stop)

    def args(self, scope: str = "all", variables=None) -> list[str]:
        pdfmd.CSS_SCOPE_CLI = scope
        self.addCleanup(setattr, pdfmd, "CSS_SCOPE_CLI", None)
        return pdfmd.css_heading_args([self.root / "d.md"], [], list(variables or []), None, lambda kind, text: self.notes.append((kind, text)))

    def test_with_css_scope_all_a_header_file_comes_back(self):
        out = self.args()
        self.assertEqual(out[0], "--include-in-header")
        self.assertIn("\\titleformat*{\\section}", Path(out[1]).read_text(encoding="utf-8"))
        self.assertTrue(Path(out[1]).name.startswith("packages-"))
        self.assertTrue(any("titlesec" in text for _, text in self.notes))

    def test_by_default_nothing(self):
        self.assertEqual(self.args("html"), [])

    def test_the_class_has_to_be_article(self):
        (self.root / "d.md").write_text("---\ntitle: T\ndocumentclass: report\n---\n\n# H\n", encoding="utf-8")
        self.assertEqual(self.args(), [])
        self.assertTrue(any("class is report" in text for _, text in self.notes))

    def test_a_preamble_that_formats_headings_is_left_alone(self):
        for text in ("\\usepackage{titlesec}\n", "\\usepackage{sectsty}\n\\sectionfont{\\Huge}\n",
                     "\\titleformat{\\section}{\\Large}{}{}{}\n", "\\addtokomafont{section}{\\color{red}}\n",
                     "\\renewcommand{\\section}{x}\n"):
            self.notes.clear()
            (self.root / "preamble.tex").write_text("\\usepackage{amsmath}\n" + text, encoding="utf-8")
            self.assertEqual(self.args(), [], text)
            self.assertTrue(any("formats them itself" in note for _, note in self.notes), text)

    def test_header_includes_that_format_headings_count_too(self):
        (self.root / "d.md").write_text("---\ntitle: T\nheader-includes: |\n  \\usepackage{titlesec}\n---\n\n# H\n", encoding="utf-8")
        self.assertEqual(self.args(), [])

    def test_document_font_size_overrides_css_body_size_for_headings(self):
        (self.root / "d.md").write_text("---\nfontsize: 12pt\n---\n\n# H\n", encoding="utf-8")
        (self.root / "pdfmd.css").write_text("body { font-size: 11pt } h1 { font-size: 2em }\n", encoding="utf-8")
        out = self.args()
        self.assertIn("\\fontsize{24}{28.8}", Path(out[1]).read_text(encoding="utf-8"))

    def test_the_font_size_is_taken_from_the_document(self):
        (self.root / "d.md").write_text("---\ntitle: T\nfontsize: 12pt\n---\n\n# H\n", encoding="utf-8")
        out = self.args()
        self.assertIn("\\fontsize{24}{28.8}", Path(out[1]).read_text(encoding="utf-8"))


@unittest.skipUnless(PANDOC and (shutil.which("lualatex") or shutil.which("xelatex") or shutil.which("pdflatex")), "needs Pandoc and a LaTeX engine")
class Build(unittest.TestCase):
    def test_a_real_build_gets_the_heading_in_its_colour(self):
        engine = next(name for name in ("lualatex", "xelatex", "pdflatex") if shutil.which(name))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "d.md").write_text("---\ntitle: T\n---\n\n# Heading one\n\nText.\n", encoding="utf-8")
            (root / "pdfmd.css").write_text("h1 { color: #FF0000; font-size: 2em }\n", encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-e", engine, "--css-scope", "all",
                                   "--stop-at", "tex", "--no-stamp"], cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            source = (root / "d.tex").read_text(encoding="utf-8")
            self.assertIn("\\titleformat*{\\section}", source)
            self.assertIn("\\color[HTML]{FF0000}", source)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class HeadingWriters(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "d.md").write_text(
            "---\ntitle: Example\n---\n\n# FirstHeading\n\n## SecondHeading\n\nBody text.\n", encoding="utf-8")
        (self.root / "pdfmd.css").write_text(
            'body { font-size: 11pt }\nh1 {color: #369; font-size: 2em; font-weight: normal; font-style: italic; '
            'font-family: "Example Serif", serif}\nh2 {color: red}', encoding="utf-8")

    def run_pdfmd(self, *args):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "d.md", "--no-stamp", *args],
                              cwd=self.root, capture_output=True, encoding="utf-8", timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_word_headings_follow_css_until_a_reference_document_supplies_them(self):
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        val = f'{{{ns["w"]}}}val'

        def heading(name, level=1):
            with zipfile.ZipFile(self.root / name) as package:
                styles = ElementTree.fromstring(package.read("word/styles.xml"))
            return styles.find(f'w:style[@w:styleId="Heading{level}"]/w:rPr', ns)

        self.run_pdfmd("--to", "docx", "-o", "default.docx")
        self.run_pdfmd("--to", "docx", "-o", "css.docx", "--css-scope", "all")
        styled = heading("css.docx")
        self.assertEqual(styled.find("w:color", ns).get(val), "336699")
        self.assertEqual(styled.find("w:sz", ns).get(val), "44")
        self.assertEqual(styled.find("w:b", ns).get(val), "0")
        self.assertIsNotNone(styled.find("w:i", ns))
        self.assertEqual(styled.find("w:rFonts", ns).get(f'{{{ns["w"]}}}ascii'), "Example Serif")
        self.assertEqual(heading("css.docx", 2).find("w:color", ns).get(val), "FF0000")
        (self.root / "default.docx").rename(self.root / "reference.docx")
        original = heading("reference.docx")
        self.assertNotEqual(original.find("w:color", ns).get(val), "336699")
        self.run_pdfmd("--to", "docx", "-o", "own.docx", "--css-scope", "all")
        self.assertEqual(ElementTree.tostring(heading("own.docx")), ElementTree.tostring(original))

    def test_typst_fragment_headings_respect_the_css_scope(self):
        self.run_pdfmd("--to", "typst", "-o", "css.typ", "--css-scope", "all")
        plain = (self.root / "css.typ").read_text(encoding="utf-8")
        self.assertIn('#show heading.where(level: 1): set text(fill: rgb("#336699"), size: 22pt', plain)
        self.assertIn('#show heading.where(level: 2): set text(fill: rgb("#FF0000"))', plain)
        self.run_pdfmd("--to", "typst", "-o", "off.typ")
        self.assertNotIn("#336699", (self.root / "off.typ").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("typst") and shutil.which("pdftotext"), "needs Typst and pdftotext")
    def test_typst_template_heading_styles_win_in_the_pdf(self):
        # A template that styles headings also styles the CSS-free control.
        template = self.root / "own.typst"
        template.write_text('#show heading: set text(fill: rgb("#12AB34"), size: 29pt, style: "normal", weight: "bold")\n'
                            '#show heading: set text(font: "Libertinus Serif")\n$body$\n', encoding="utf-8")
        settings = ("-e", "typst", "--template", template.name)
        self.run_pdfmd(*settings, "-o", "control.pdf")
        self.run_pdfmd(*settings, "-o", "custom.pdf", "--css-scope", "all")

        def boxes(name):
            result = subprocess.run(["pdftotext", "-bbox", name, "-"], cwd=self.root,
                                    capture_output=True, encoding="utf-8", check=True)
            root = ElementTree.fromstring(result.stdout)
            return [word.attrib for word in root.iter("{http://www.w3.org/1999/xhtml}word")
                    if word.text in ("FirstHeading", "SecondHeading")]

        control = boxes("control.pdf")
        self.assertEqual(len(control), 2)
        self.assertEqual(boxes("custom.pdf"), control)
        self.run_pdfmd("-e", "typst", "-o", "default.pdf", "--css-scope", "all")
        self.assertNotEqual(boxes("default.pdf"), control)
        template.write_text("$body$\n", encoding="utf-8")
        self.run_pdfmd(*settings, "-o", "unstyled.pdf", "--css-scope", "all")
        self.run_pdfmd(*settings, "-o", "unstyled-control.pdf")
        self.assertNotEqual(boxes("unstyled.pdf"), boxes("unstyled-control.pdf"))


if __name__ == "__main__":
    unittest.main()
