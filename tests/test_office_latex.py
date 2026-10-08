"""LaTeX made native for Word output: the Lua filter (pdfmd_office/office.lua) and the label reader."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfmd_office import caption_separator, cref_names, parse_aux  # noqa: E402

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "pdfmd_office" / "office.lua"

AUX = r"""
\relax
\newlabel{eq:precip}{{1}{2}{Theory}{equation.1}{}}
\newlabel{eq:precip@cref}{{[equation][1][]1}{[1][2][]2}{}{}{}}
\newlabel{fig:a}{{3}{5}{Results}{figure.3}{}}
\newlabel{fig:a@cref}{{[figure][3][]3}{[1][5][]5}{}{}{}}
\newlabel{sec:intro}{{I}{1}{Intro}{section.1}{}}
\newlabel{sec:intro@cref}{{[section][1][]\Roman {section}}{[1][1][]1}{}{}{}}
"""


class Labels(unittest.TestCase):
    def test_aux_numbers_pages_and_types(self):
        labels = parse_aux(AUX)
        self.assertEqual(labels["eq:precip"], {"num": "1", "page": "2", "title": "Theory", "type": "equation"})
        self.assertEqual(labels["fig:a"]["num"], "3")
        self.assertEqual(labels["fig:a"]["type"], "figure")
        self.assertEqual(labels["sec:intro"]["num"], "I")

    def test_caption_separator_and_names_come_from_the_preamble(self):
        self.assertEqual(caption_separator([r"\captionsetup{labelsep=period}"]), ". ")
        self.assertEqual(caption_separator([r"\captionsetup{labelsep=colon}"]), ": ")
        self.assertEqual(caption_separator(["nothing"]), ": ")
        names = cref_names([r"\crefname{equation}{formula}{formulae}", r"\Crefname{figure}{Fig.}{Figs.}"])
        self.assertEqual(names["equation"], ("Equation", "Equations"))     # `\crefname` alone does not rename a default
        self.assertEqual(names["figure"], ("Fig.", "Figs."))
        self.assertEqual(names["reaction"] if "reaction" in names else ("", ""), ("", ""))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Translators(unittest.TestCase):
    def lua(self, code: str) -> str:
        script = ("FORMAT = 'docx'\nPDFMD_OFFICE_EXPORT = {}\ndofile('" + str(FILTER) + "')\nlocal E = PDFMD_OFFICE_EXPORT\n" + code)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "t.lua"
            path.write_text(script, encoding="utf-8")
            done = subprocess.run(["pandoc", "lua", str(path)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def ce(self, source: str) -> str:
        return self.lua(f"local t = E.ce_parse([[{source}]]); print(t and E.ce_math(t) or 'FAIL')")

    def test_mhchem(self):
        self.assertEqual(self.ce("H2O"), r"\text{H}_{2}\text{O}")
        self.assertEqual(self.ce("Ag+(aq) + Cl-(aq) -> AgCl(s)"),
                         r"\text{Ag}^{+}\text{(aq)}\ +\ \text{Cl}^{-}\text{(aq)}\ \longrightarrow\ \text{AgCl(s)}")
        self.assertEqual(self.ce("SO4^2-"), r"\text{S}\text{O}_{4}^{2-}")
        self.assertEqual(self.ce("2AgCl(s)"), r"2\,\text{AgCl(s)}")
        self.assertEqual(self.ce("R2CH-O-Cl"), r"\text{R}_{2}\text{CH}\text{-}\text{O}\text{-}\text{Cl}")
        self.assertEqual(self.ce("Q+X-"), r"\text{Q}^{+}\text{X}^{-}")
        self.assertEqual(self.ce("CuSO4.5H2O"), r"\text{CuS}\text{O}_{4}\text{·}5\,\text{H}_{2}\text{O}")
        self.assertEqual(self.ce("nonsense $"), "FAIL")

    def test_siunitx_in_math(self):
        self.assertEqual(self.lua(r"print(E.math_translate([[M = 35.453\,\si{\gram\per\mole}]]))"),
                         r"M = 35.453\,\text{g}\,\text{mol}^{-1}")
        self.assertEqual(self.lua(r"print(E.math_translate([[\SI{5}{\milli\liter}]]))"), r"5\,\text{mL}")
        self.assertEqual(self.lua(r"print(E.math_translate([[\si{\unknownunit}]]))"), "nil")

    def test_a_degree_sign_without_a_base_is_text_not_an_empty_box(self):
        self.assertEqual(self.lua(r"print(E.fix_empty_scripts([[105\,^\circ\text{C}]]))"), r"105\,\text{°}\text{C}")
        self.assertEqual(self.lua(r"print(E.fix_empty_scripts([[x^\circ]]))"), r"x^\circ")

    def test_a_long_display_is_cut_at_its_equals_signs(self):
        long = r"a = \frac{1234567890+1234567890}{3} = \frac{1234567890}{3} = 411522630 = 4.1\times 10^{8} = 0.41\times 10^{9}"
        cut = self.lua("print(E.break_display([[" + long + r"]], 40))")
        self.assertTrue(cut.startswith(r"\begin{aligned}"), cut)
        self.assertGreaterEqual(cut.count(r"\\"), 1)
        self.assertEqual(self.lua(r"print(E.break_display([[a = b = c]], 40))"), "a = b = c")      # short: untouched
        self.assertEqual(self.lua("print(E.break_display([[" + long + r" \\ x]], 40))"), long + r" \\ x")  # the author's own breaks

    def test_math_texmath_check(self):
        self.assertEqual(self.lua(r"print(E.math_native([[\frac{a}{b}]], true))"), "true")
        self.assertEqual(self.lua(r"print(E.math_native([[\ce{H2O}]], false))"), "false")


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Documents(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)

    def document_xml(self, markdown: str, *extra: str) -> str:
        source = self.root / "d.md"
        source.write_text(markdown, encoding="utf-8")
        done = subprocess.run(["pandoc", str(source), "-o", str(self.root / "d.docx"), "--lua-filter", str(FILTER), *extra],
                              capture_output=True, text=True, cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stderr)
        return zipfile.ZipFile(self.root / "d.docx").read("word/document.xml").decode("utf-8")

    def labels(self) -> str:
        path = self.root / "labels.json"
        path.write_text(json.dumps({"labels": parse_aux(AUX), "crefnames": {"equation": ["Equation", "Equations"],
                                                                         "figure": ["Figure", "Figures"]},
                                    "captionsep": ". ", "crefcap": True}), encoding="utf-8")
        return f"pdfmd-office-labels={path}"

    TEXT = ("Water \\ce{H2O} and \\SI{5}{\\milli\\liter} and $x_{\\ce{NaCl}}$.\n\n"
            "\\begin{equation}\\label{eq:precip}\n  \\ce{Ag+(aq) -> Ag(s)}\n\\end{equation}\n\n"
            "As \\cref{eq:precip} and \\ref{fig:a} show, \\eqref{eq:precip}.\n")

    def test_chemistry_and_units_become_text_and_equations(self):
        xml = self.document_xml(self.TEXT, "-M", self.labels())
        self.assertNotIn("\\ce", xml)
        self.assertNotIn("\\SI", xml)
        self.assertGreaterEqual(xml.count("<m:oMath"), 2)             # inline formula and the equation
        self.assertIn('w:val="PdfmdEquation"', xml)                   # equation and its number in a table
        self.assertIn(">(1)<", xml)

    def test_references_use_the_numbers_latex_assigned(self):
        xml = self.document_xml(self.TEXT, "-M", self.labels())
        text = re.sub(r"<[^>]+>", "", xml)
        self.assertIn("Equation\u00a0(1)", text)
        self.assertIn("3", text)
        self.assertIn("(1)", text)

    def test_an_unknown_reference_is_marked_not_dropped(self):
        xml = self.document_xml("See \\cref{nowhere}.\n")
        self.assertIn("??", xml)

    def test_a_raw_figure_environment_is_read_and_captioned(self):
        figure = ("\\begin{figure}[H]\n\\centering\n\\includegraphics{x.png}\n"
                  "\\caption{Plates \\emph{one}.\\label{fig:a}}\n\\end{figure}\n")
        (self.root / "x.png").write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"))
        xml = self.document_xml(figure, "-M", self.labels())
        text = re.sub(r"<[^>]+>", "", xml)
        self.assertIn("Figure\u00a03. Plates", text)
        self.assertIn("<pic:pic", xml)

    def test_latex_off_leaves_pandocs_own_behaviour(self):
        xml = self.document_xml("Water \\ce{H2O}.\n", "-M", "pdfmd-office-latex=off")
        self.assertNotIn("subscript", xml)      # Pandoc drops the raw command; no chemistry was made

    def test_a_layout_wrapped_equation_is_still_an_equation(self):
        raw = "```{=latex}\n\\par\\nointerlineskip\n\\begin{equation}\\label{e}\n  a = b\n\\end{equation}\n\\par\\nointerlineskip\n```\n"
        xml = self.document_xml(raw)
        self.assertIn('w:val="PdfmdEquation"', xml)

    def test_the_report_names_what_was_left_out(self):
        report = self.root / "r.json"
        self.document_xml("A \\prelab{1} and\n\n\\begin{tikzpicture}\\draw (0,0)--(1,1);\\end{tikzpicture}\n",
                          "-M", f"pdfmd-office-report={report}")
        data = json.loads(report.read_text(encoding="utf-8"))
        kinds = sorted(item["kind"] for item in data["left_over"])
        self.assertEqual(kinds, ["block", "inline"])


if __name__ == "__main__":
    unittest.main()


LUALATEX = shutil.which("lualatex")
POPPLER = shutil.which("pdftocairo")
MINIMAL_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
               b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 50]/Contents 4 0 R>>endobj\n"
               b"4 0 obj<</Length 33>>stream\n0 0 1 rg 10 10 80 30 re f\nendstream endobj\n"
               b"trailer<</Root 1 0 R/Size 5>>\n%%EOF\n")


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Profile(unittest.TestCase):
    def test_a_profile_says_what_a_house_macro_means(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "office.lua").write_text(
                'return {ignore = {"\\\\Hidden"}, commands = {tag = function(args) '
                'return {pandoc.Strong({pandoc.Str("[tag " .. args[1] .. "]")})} end}}\n', encoding="utf-8")
            (root / "d.md").write_text("---\ntitle: T\npdfmd-options:\n  office: {labels: off}\n---\n\n"
                                       "A \\tag{7} and \\Hidden here.\n\n\\Hidden\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-o", "d.docx", "-v"], cwd=root,
                                  capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": ""})
            self.assertEqual(done.returncode, 0, done.stderr)
            text = re.sub(r"<[^>]+>", "", zipfile.ZipFile(root / "d.docx").read("word/document.xml").decode())
            self.assertIn("[tag 7]", text)
            self.assertNotIn("Hidden", text)
            self.assertIn("profile", done.stdout)


@unittest.skipUnless(PANDOC and LUALATEX and POPPLER and shutil.which("pdfinfo"), "needs Pandoc, LuaLaTeX and Poppler")
class Pictures(unittest.TestCase):
    def build(self, files: dict[str, str | bytes], markdown: str) -> tuple[Path, subprocess.CompletedProcess]:
        directory = tempfile.mkdtemp(prefix="pdfmd-pictures-")
        self.addCleanup(shutil.rmtree, directory, True)
        root = Path(directory)
        for name, content in files.items():
            (root / name).write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        (root / "d.md").write_text("---\ntitle: T\npdfmd-options:\n  office: {labels: off}\n---\n\n" + markdown, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-o", "d.docx"], cwd=root, capture_output=True,
                              text=True, env={**os.environ, "PDFMD_CONFIG": "", "XDG_CACHE_HOME": str(root / "cache")})
        return root, done

    def test_unknown_latex_becomes_a_vector_picture_with_a_png_fallback(self):
        root, done = self.build({"preamble.tex": "\\usepackage{tikz}\n\\newcommand{\\boxtag}[1]{\\textbf{[tag #1]}}\n"},
                                "Before \\boxtag{1} after.\n\n\\begin{tikzpicture}\\draw (0,0) circle (1cm);\\end{tikzpicture}\n\nEnd.\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        archive = zipfile.ZipFile(root / "d.docx")
        names = archive.namelist()
        self.assertEqual(sorted(name for name in names if name.endswith(".svg")), ["word/media/pdfmd-1.svg", "word/media/pdfmd-2.svg"])
        xml = archive.read("word/document.xml").decode()
        self.assertEqual(xml.count("svgBlip"), 2)
        self.assertIn('<w:position w:val="-', xml)           # the inline one sits on the baseline
        self.assertNotIn("pdfmd:svg", xml)
        self.assertIn("image/svg+xml", archive.read("[Content_Types].xml").decode())
        self.assertNotIn("WARN", done.stderr)

    def test_a_picture_is_drawn_once(self):
        files = {"preamble.tex": "\\usepackage{tikz}\n"}
        text = "\\begin{tikzpicture}\\draw (0,0) rectangle (2,1);\\end{tikzpicture}\n"
        root, done = self.build(files, text)
        self.assertEqual(done.returncode, 0, done.stderr)
        again = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-o", "d.docx", "-v"], cwd=root,
                               capture_output=True, text=True,
                               env={**os.environ, "PDFMD_CONFIG": "", "XDG_CACHE_HOME": str(root / "cache")})
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("drawing 1 LaTeX fragment", again.stdout)      # cached

    def test_a_fragment_that_will_not_compile_is_named_and_the_rest_still_builds(self):
        root, done = self.build({}, "Good \\textbf{bold}.\n\n\\begin{nosuchenv}x\\end{nosuchenv}\n\nEnd.\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("could not draw a LaTeX block", done.stderr)
        self.assertIn("End.", re.sub(r"<[^>]+>", "", zipfile.ZipFile(root / "d.docx").read("word/document.xml").decode()))

    def test_a_pdf_picture_is_converted(self):
        root, done = self.build({"plot.pdf": MINIMAL_PDF}, "![A plot](plot.pdf)\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        archive = zipfile.ZipFile(root / "d.docx")
        self.assertTrue(any(name.endswith(".svg") for name in archive.namelist()))
        self.assertIn("<pic:pic", archive.read("word/document.xml").decode())

    def test_a_figure_with_tikz_keeps_its_caption_as_text_and_its_number(self):
        root, done = self.build({"preamble.tex": "\\usepackage{tikz}\n"},
                                "\\begin{figure}[H]\n\\centering\n\\begin{tikzpicture}\\draw (0,0) circle (1cm);\\end{tikzpicture}\n"
                                "\\caption{A circle.\\label{fig:c}}\n\\end{figure}\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        text = re.sub(r"<[^>]+>", "", zipfile.ZipFile(root / "d.docx").read("word/document.xml").decode())
        self.assertIn("Figure\u00a01: A circle.", text)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class DisplayBlocks(unittest.TestCase):
    def test_a_bracket_display_is_converted_like_any_math_and_math_the_reader_made_is_translated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "d.md").write_text("```{=latex}\n\\par\\nointerlineskip\n\\[\\ce{H2O} = \\SI{5}{\\milli\\liter}\\]\n\\par\\nointerlineskip\n```\n",
                                       encoding="utf-8")
            done = subprocess.run(["pandoc", "d.md", "-o", "d.docx", "--lua-filter", str(FILTER)], cwd=root,
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("Could not convert", done.stderr)
            xml = zipfile.ZipFile(root / "d.docx").read("word/document.xml").decode()
            self.assertIn("<m:oMathPara>", xml)
            self.assertNotIn("\\ce", xml)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class TableWidths(unittest.TestCase):
    def grid(self, source: str) -> list[int]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "t.md").write_text(source, encoding="utf-8")
            done = subprocess.run(["pandoc", "t.md", "-o", "t.docx", "--lua-filter", str(FILTER)], cwd=root,
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            xml = zipfile.ZipFile(root / "t.docx").read("word/document.xml").decode()
            return [int(width) for width in re.findall(r'<w:gridCol w:w="(\d+)"', xml)]

    def test_a_table_without_widths_is_sized_to_its_text(self):
        widths = self.grid("| Lane | Sample | Feature |\n|---|---|---|\n| 1 | Paracetamol | faint, no lane or smear |\n")
        self.assertEqual(len(widths), 3)
        self.assertGreater(widths[2], widths[1])
        self.assertGreater(widths[1], widths[0])

    def test_given_widths_are_left_alone(self):
        widths = self.grid("| a | b |\n|---|---|\n| 1 | 2 |\n")
        self.assertEqual(len(set(widths)), 1)   # a pipe table's lines are short: Pandoc gives no widths, we do
        widths = self.grid("| a | b |\n|--|------------------|\n| " + "x" * 30 + " | " + "y" * 90 + " |\n")
        self.assertLess(widths[0], widths[1])


TYPST = shutil.which("typst")
SOFFICE_PATH = shutil.which("soffice") or ("/Applications/LibreOffice.app/Contents/MacOS/soffice"
                                           if Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").exists() else None)
FALLBACK_DOCUMENT = ("---\ntitle: T\npapersize: a4\n{options}---\n\nWater \\ce{{H2O}}.\n\n"
                     "\\begin{{tikzpicture}}\\draw (0,0) circle (1cm);\\end{{tikzpicture}}\n\nAfter.\n")


@unittest.skipUnless(PANDOC and LUALATEX and POPPLER and shutil.which("pdfinfo"), "needs Pandoc, LuaLaTeX and Poppler")
class OtherOutputs(unittest.TestCase):
    def folder(self, options: str = "") -> Path:
        directory = tempfile.mkdtemp(prefix="pdfmd-others-")
        self.addCleanup(shutil.rmtree, directory, True)
        root = Path(directory)
        (root / "preamble.tex").write_text("\\usepackage{tikz}\n", encoding="utf-8")
        (root / "d.md").write_text(FALLBACK_DOCUMENT.format(options=options), encoding="utf-8")
        return root

    def run_pdfmd(self, root: Path, *arguments: str):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *arguments], cwd=root, capture_output=True,
                              text=True, env={**os.environ, "PDFMD_CONFIG": "", "XDG_CACHE_HOME": str(root / "cache")})

    @unittest.skipUnless(TYPST, "needs Typst")
    def test_typst_gets_the_drawing_when_the_document_asks(self):
        root = self.folder("pdfmd-options:\n  office: {latex: auto, labels: off}\n")
        done = self.run_pdfmd(root, "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stderr)
        text = subprocess.run(["pdftotext", str(root / "d.pdf"), "-"], capture_output=True, text=True).stdout
        self.assertIn("After.", text)
        self.assertNotIn("\\ce", text)
        self.assertTrue(list((root / "cache").rglob("*.svg")))        # the picture was drawn

    def test_html_is_untouched_unless_asked(self):
        plain = self.folder()
        self.assertEqual(self.run_pdfmd(plain, "-o", "d.html", "--self-contained").returncode, 0)
        self.assertNotIn("<img", (plain / "d.html").read_text(encoding="utf-8"))
        asked = self.folder("pdfmd-options:\n  office: {latex: auto, labels: off}\n")
        self.assertEqual(self.run_pdfmd(asked, "-o", "d.html", "--self-contained").returncode, 0)
        self.assertIn("<img", (asked / "d.html").read_text(encoding="utf-8"))

    @unittest.skipUnless(SOFFICE_PATH, "needs LibreOffice")
    def test_the_soffice_fallback_keeps_the_page_and_draws_what_it_can(self):
        root = self.folder()
        done = self.run_pdfmd(root, "-e", "soffice")
        self.assertEqual(done.returncode, 0, done.stderr)
        info = subprocess.run(["pdfinfo", str(root / "d.pdf")], capture_output=True, text=True).stdout
        self.assertIn("A4", info)
        self.assertTrue(list((root / "cache").rglob("*.svg")))
