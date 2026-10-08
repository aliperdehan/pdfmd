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
