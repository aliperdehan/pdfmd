"""LaTeX made native for Word output: the Lua filter (pdfmd_office/office.lua) and the label reader."""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pandoc_support import needs_crossref, needs_pandoc  # noqa: E402
from pdfmd_office import caption_separator, cref_names, parse_aux  # noqa: E402

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "pdfmd_office" / "office.lua"
# a 1x1 PNG
TINY_PNG = (b"\x89PNG\r\n\x1a\n" + b"".join(struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data)) for kind, data in
            ((b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)), (b"IDAT", zlib.compress(b"\x00\xff\x00\x00")),
             (b"IEND", b""))))

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
        # the interpreter is the one running the tests, as pdfmd passes it (`python3` is not a command everywhere, Windows)
        script = ("FORMAT = 'docx'\nPDFMD_OFFICE_EXPORT = {}\ndofile('" + FILTER.as_posix() + "')\nlocal E = PDFMD_OFFICE_EXPORT\n"
                  "E.chem.python = '" + Path(sys.executable).as_posix() + "'\n" + code)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "t.lua"
            path.write_text(script, encoding="utf-8")
            done = subprocess.run(["pandoc", "lua", str(path)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def ce(self, source: str) -> str:
        return self.lua(f"print(tostring(E.math_translate([[\\ce{{{source}}}]])))")

    def test_mhchem(self):
        # v3.28.9: pdfmd_chem (mhchem's own parser, ported) writes them; the filter's Lua translator read a bond at the
        # end as a charge and set every symbol in \\text
        self.assertEqual(self.ce("H2O"), r"{\mathrm{H}_{2}\mathrm{O}}")
        self.assertEqual(self.ce("Ag+(aq) + Cl-(aq) -> AgCl(s)"),
                         r"{\mathrm{Ag}^{+}(\mathrm{aq})+\mathrm{Cl}^{-}(\mathrm{aq})\longrightarrow\mathrm{AgCl}(\mathrm{s})}")
        self.assertEqual(self.ce("SO4^2-"), r"{\mathrm{SO}_{4}^{2-}}")
        self.assertEqual(self.ce("2AgCl(s)"), r"{2\,\mathrm{AgCl}(\mathrm{s})}")
        self.assertEqual(self.ce("R2CH-O-Cl"), r"{\mathrm{R}_{2}\mathrm{CH}-\mathrm{O}-\mathrm{Cl}}")
        self.assertEqual(self.ce("Q+X-"), r"{\mathrm{Q}^{+}\mathrm{X}^{-}}")
        self.assertEqual(self.ce("CuSO4.5H2O"), r"{\mathrm{CuSO}_{4}\cdot 5\,\mathrm{H}_{2}\mathrm{O}}")
        self.assertEqual(self.ce("C=O"), r"{\mathrm{C}=\mathrm{O}}")
        self.assertEqual(self.ce("HC#CH"), r"{\mathrm{HC}\equiv \mathrm{CH}}")
        self.assertEqual(self.ce("-COO-"), r"{-\mathrm{COO}-}")                         # bonds, not a charge
        self.assertEqual(self.ce("R-CHO + \\chemfig{A-B}"), "nil")                     # LaTeX draws it

    def test_mhchem_in_text(self):
        native = self.lua("print(pandoc.write(pandoc.Pandoc({pandoc.Plain(E.text_command([[\\ce{SO4^2-}]]))}), 'native'))")
        self.assertEqual(" ".join(native.split()), '[ Plain [ Str "SO" , Subscript [ Str "4" ] , Superscript [ Str "2\\8722" ] ] ]')

    def test_siunitx_in_math(self):
        self.assertEqual(self.lua(r"print(E.math_translate([[M = 35.453\,\si{\gram\per\mole}]]))"),
                         r"M = 35.453\,{\mathrm{g}\,\mathrm{mol}^{-1}}")
        self.assertEqual(self.lua(r"print(E.math_translate([[\SI{5}{\milli\liter}]]))"), r"{5\,\mathrm{mL}}")
        self.assertEqual(self.lua(r"print(E.math_translate([[\qty{25}{\mL}]]))"), r"{25\,\mathrm{mL}}")   # an abbreviation
        self.assertEqual(self.lua(r"print(E.math_translate([[\si{\unknownunit}]]))"), "nil")

    def filtered(self, text: str, *arguments: str) -> tuple[str, dict, str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "d.md").write_text(text, encoding="utf-8")
            done = subprocess.run(["pandoc", "d.md", "--lua-filter", str(FILTER), "-M", "pdfmd-office-latex=auto",
                                   "-M", f"pdfmd-office-python={Path(sys.executable).as_posix()}",
                                   "-M", f"pdfmd-office-report={root / 'report.json'}", *arguments], cwd=root,
                                  capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(done.returncode, 0, done.stderr)
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        return done.stdout, report, done.stderr

    def test_one_call_of_the_converter_for_a_document(self):
        text = ("\\ce{H2O} and \\ce{SO4^2-}, \\qty{25}{\\mL}, $\\ce{CO2}$ and $c = \\SI{0.1}{\\molar}$.\n\n"
                "\\begin{equation}\\ce{A + B -> C}\\end{equation}\n")
        native, report, _ = self.filtered(text, "-t", "native")
        self.assertEqual(report["chem_calls"], 1)
        self.assertIn('Subscript [ Str "2" ]', native)
        self.assertIn("\\\\mathrm{CO}_{2}", native)

    def test_an_arrow_with_words_is_text_where_math_is_plain(self):
        text = "Heat: \\ce{A ->[\\Delta] B}.\n"
        import pdfmd                              # the option for each Pandoc: --math-method= from 3.2 or so
        page, _, _ = self.filtered(text, "-t", "html5", *pdfmd.html_math_args("plain"))
        self.assertIn("A \u27f6 (\u0394) B", page)
        page, _, _ = self.filtered(text, "-t", "html5", *pdfmd.html_math_args("mathml"))
        self.assertIn("<math", page)

    def test_without_python_latex_draws_them(self):
        _, report, stderr = self.filtered("\\ce{H2O} and \\qty{5}{\\mL}\n", "-t", "native",
                                          "-M", "pdfmd-office-python=/nonexistent/python3")
        self.assertEqual(stderr.count("could not run"), 1)                  # one WARN, and the build goes on
        self.assertEqual([item["tex"] for item in report["left_over"]], ["\\ce{H2O}"])  # Pandoc's reader knows \\qty

    def test_a_degree_sign_without_a_base_is_text_not_an_empty_box(self):
        self.assertEqual(self.lua(r"print(E.fix_empty_scripts([[105\,^\circ\text{C}]]))"), r"105\,\text{°}\text{C}")
        self.assertEqual(self.lua(r"print(E.fix_empty_scripts([[x^\circ]]))"), r"x^\circ")

    def test_a_signed_number_is_text_not_an_equation(self):
        self.assertEqual(self.lua(r"print(E.plain_number([[-4]]))"), "\u2212" + "4")
        self.assertEqual(self.lua(r"print(E.plain_number([[\sim 825]]))"), "~ 825")
        self.assertEqual(self.lua(r"print(E.plain_number([[>500]]))"), ">500")
        self.assertEqual(self.lua(r"print(E.plain_number([[x]]))"), "nil")
        self.assertEqual(self.lua(r"print(E.plain_number([[10^{-3}]]))"), "nil")
        self.assertEqual(self.lua(r"print(E.plain_number([[\alpha 5]]))"), "nil")

    def test_a_script_with_no_base_is_a_real_script_not_an_empty_box(self):
        self.assertEqual(self.lua(r"print(E.script_only([[_2]]).t)"), "Subscript")
        self.assertEqual(self.lua(r"print(E.script_only([[^{3+}]]).t)"), "Superscript")
        self.assertEqual(self.lua(r"print(E.script_only([[x_1]]))"), "nil")
        self.assertEqual(self.lua(r"print(E.script_only([[_{\alpha}]]))"), "nil")

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
        done = subprocess.run(["pandoc", str(source), "-o", str(self.root / "d.docx"), "--lua-filter", str(FILTER),
                               "-M", f"pdfmd-office-python={Path(sys.executable).as_posix()}", *extra],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.root)
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

    @needs_pandoc(3, 4, why="Word tables take a style from 3.4; the equation table is plain before")
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

    @needs_pandoc(3, 4, why="Word tables take a style from 3.4; the equation table is plain before")
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

    TABLES = "| a |\n|---|\n| 1 |\n\n: {numbered} {{#tbl:t}}\n\n| b |\n|---|\n| 2 |\n\n: Second\n"

    @needs_pandoc(3, 8, 2, why="a table caption's {#tbl:t} is the table's label from 3.8.2")
    def test_a_caption_pandoc_crossref_numbered_is_not_numbered_again(self):
        # it read "Table 1: Table 1: Labelled" in every Word file, LibreOffice and Calibre PDF (v3.28.1)
        text = re.sub(r"<[^>]+>", "", self.document_xml(self.TABLES.format(numbered="Table 1: Labelled")))
        self.assertIn("Table 1: Labelled", text)
        self.assertNotIn("Table 1. Table", text)
        self.assertIn("Table 2. Second", text)                     # counted all the same
        text = re.sub(r"<[^>]+>", "", self.document_xml(self.TABLES.format(numbered="Tab. 1: Labelled"),
                                                        "-M", "tableTitle=Tab."))
        self.assertNotIn("Table 1. Tab.", text)

    def test_the_label_on_a_div_around_the_table_as_crossref_puts_it_before_pandoc_3_8_2(self):
        # pandoc-crossref 0.3.16 with Pandoc 3.1.3: Div {#tbl:t} [Table "" "Table 1: Labelled"] (v3.28.3)
        wrapped = "::: {{#tbl:t}}\n| a |\n|---|\n| 1 |\n\n: {numbered}\n:::\n\n| b |\n|---|\n| 2 |\n\n: Second\n"
        text = re.sub(r"<[^>]+>", "", self.document_xml(wrapped.format(numbered="Table 1: Labelled")))
        self.assertIn("Table 1: Labelled", text)                     # crossref's own words have a plain space
        self.assertNotIn("Table 1. Table", text)                 # the filter's number has a no-break space
        self.assertIn("Table 2. Second", text)
        text = re.sub(r"<[^>]+>", "", self.document_xml(wrapped.format(numbered="Labelled")))
        self.assertIn("Table 1. Labelled", text)                # a div's label alone numbers nothing away

    def test_a_crossref_label_without_crossref_is_still_numbered(self):
        text = re.sub(r"<[^>]+>", "", self.document_xml(self.TABLES.format(numbered="Labelled")))
        self.assertIn("Table 1. Labelled", text)

    @needs_crossref
    def test_with_pandoc_crossref_itself(self):
        source = self.root / "d.md"
        source.write_text(self.TABLES.format(numbered="Labelled"), encoding="utf-8")
        done = subprocess.run(["pandoc", str(source), "-o", str(self.root / "d.docx"), "--filter", "pandoc-crossref",
                               "--lua-filter", str(FILTER)], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stderr)
        text = re.sub(r"<[^>]+>", "", zipfile.ZipFile(self.root / "d.docx").read("word/document.xml").decode("utf-8"))
        self.assertIn("Table 1: Labelled", text)
        self.assertNotIn("Table 1. Table", text)


def unreached(path: Path) -> list[str]:
    """The internal links of a .docx or .odt with no bookmark of their name."""
    archive = zipfile.ZipFile(path)
    if path.suffix == ".docx":
        xml = archive.read("word/document.xml").decode("utf-8")
        links = set(re.findall(r'<w:hyperlink [^>]*w:anchor="([^"]*)"', xml))
        marks = set(re.findall(r'<w:bookmarkStart [^>]*w:name="([^"]*)"', xml))
    else:
        xml = archive.read("content.xml").decode("utf-8")
        links = {link[1:] for link in re.findall(r'<text:a [^>]*xlink:href="(#[^"]*)"', xml)}
        marks = set(re.findall(r'<text:bookmark(?:-start)? text:name="([^"]*)"', xml))
    return sorted(links - marks)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Anchors(unittest.TestCase):
    """v3.28.4: a reference to what LaTeX labelled leads somewhere in Word, OpenDocument, HTML and Typst."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)

    def convert(self, markdown: str, output: str, *before: str) -> subprocess.CompletedProcess:
        """`before` goes ahead of the filter, as pdfmd puts --citeproc."""
        (self.root / "d.md").write_text(markdown, encoding="utf-8")
        target = ["-o", output] if "." in output else ["-t", output]
        done = subprocess.run(["pandoc", "d.md", *target, *before, "--lua-filter", str(FILTER),
                               "-M", f"pdfmd-office-python={Path(sys.executable).as_posix()}"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def test_a_label_in_a_caption(self):
        # LR4-5: `: caption \`\label{tbl:rf}\`{=latex}`, the label was dropped and \cref{tbl:rf} led nowhere
        text = "See [the table](#tbl:rf).\n\n| a |\n|---|\n| 1 |\n\n: Caption `\\label{tbl:rf}`{=latex}\n"
        for output in ("d.docx", "d.odt"):
            self.convert(text, output)
            self.assertEqual(unreached(self.root / output), [], output)
        caption = re.sub(r"<[^>]+>", "", zipfile.ZipFile(self.root / "d.docx").read("word/document.xml").decode())
        self.assertIn("Table\u00a01. Caption", caption)

    def test_every_label_of_an_equation(self):
        text = ("See [one](#eq:a) and [two](#eq:b).\n\n```{=latex}\n\\begin{align}\na &= b \\label{eq:a}\\\\\n"
                "c &= d \\label{eq:b}\n\\end{align}\n```\n")
        for output in ("d.docx", "d.odt"):           # OpenDocument kept no Div's identifier: the first was lost too
            self.convert(text, output)
            self.assertEqual(unreached(self.root / output), [], output)
        page = self.convert(text, "html5").stdout
        self.assertEqual((page.count('id="eq:a"'), page.count('id="eq:b"')), (1, 1))

    def test_opendocument_reaches_a_table_a_figure_a_div_and_a_citation(self):
        (self.root / "r.bib").write_text("@book{k, title={A Book}, author={Doe, Jane}, year={2020}}\n", encoding="utf-8")
        (self.root / "a.png").write_bytes(TINY_PNG)
        text = ("---\nbibliography: r.bib\nlink-citations: true\n---\n\n"
                "See [the div](#dv), [the figure](#fig:p), [the table](#tbl:t) and @k.\n\n::: {#dv}\nIn a div.\n:::\n\n"
                "![Picture](a.png){#fig:p}\n\n```{=latex}\n\\begin{table}\n\\caption{Stock.\\label{tbl:t}}\n"
                "\\begin{tabular}{l}\nx\\\\\n\\end{tabular}\n\\end{table}\n```\n")
        self.convert(text, "d.odt", "--citeproc")
        self.assertEqual(unreached(self.root / "d.odt"), [])

    def test_no_label_twice_in_html_or_typst(self):
        # Pandoc's LaTeX reader puts a figure's label on the figure and on an empty span in its caption: Typst stopped
        # on it ("label occurs multiple times", typst.lua kept the first) and HTML had the id twice
        (self.root / "a.png").write_bytes(TINY_PNG)
        text = ("See [it](#fig:tlc).\n\n```{=latex}\n\\begin{figure}\n\\centering\n\\includegraphics{a.png}\n"
                "\\caption{Plates.\\label{fig:tlc}}\n\\end{figure}\n```\n\nAgain `\\label{fig:tlc}`{=latex}.\n")
        self.assertEqual(self.convert(text, "html5").stdout.count('id="fig:tlc"'), 1)
        self.assertEqual(self.convert(text, "typst").stdout.count("<fig:tlc>"), 2)      # the label and the link
        self.convert(text, "d.docx")
        self.assertEqual(unreached(self.root / "d.docx"), [])

    def test_a_picture_sized_by_its_height_with_an_older_pandoc(self):
        # Pandoc 3.1.3 has no pandoc.image: "attempt to index a nil value (field 'image')" stopped the build
        (self.root / "a.png").write_bytes(TINY_PNG)
        text = "```{=latex}\n\\begin{figure}\n\\includegraphics[height=2cm]{a.png}\n\\caption{A dot.}\n\\end{figure}\n```\n"
        self.convert(text, "d.docx")
        self.assertIn("<pic:pic", zipfile.ZipFile(self.root / "d.docx").read("word/document.xml").decode())


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


    def test_a_profile_reads_files_of_the_documents_folders_and_builds_a_native_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            (root / "lib" / "data.tex").write_text("Water, 18.02 \\allowbreak 18\n", encoding="utf-8")
            (root / "office.lua").write_text(
                'return {commands = {records = function(args, raw, h)\n'
                '  local text = h.read_file("data")\n'
                '  local cell = pandoc.Cell({pandoc.Para(h.inlines(text) or {})})\n'
                '  local t = pandoc.Table(pandoc.Caption({pandoc.Plain(h.inlines("A caption") or {})}), {{pandoc.AlignLeft, 1}},\n'
                '    pandoc.TableHead({}), {pandoc.TableBody({pandoc.Row({cell})})}, pandoc.TableFoot({}))\n'
                '  return {h.number_caption(t, "table") or t}\nend}}\n', encoding="utf-8")
            (root / "d.md").write_text("---\ntitle: T\n---\n\n```{=latex}\n\\setcounter{table}{4}\\records{x}%\n{ignored}\n```\n",
                                       encoding="utf-8")
            done = subprocess.run(["pandoc", "d.md", "-o", "d.docx", "--lua-filter", str(FILTER), "-M",
                                   f"pdfmd-office-profile={root / 'office.lua'}", "-M", f"pdfmd-office-path={root / 'lib'}",
                                   "-M", "pdfmd-office-latex=auto"], cwd=root, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            xml = zipfile.ZipFile(root / "d.docx").read("word/document.xml").decode()
            self.assertIn("<w:tbl>", xml)
            text = re.sub(r"<[^>]+>", "", xml)
            self.assertIn("Water, 18.02 18", text)          # \allowbreak is no picture and no text
            self.assertIn("Table\u00a05. A caption", text)       # \setcounter{table}{4} before it, a % at the line end joined


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

    def test_a_drawn_block_keeps_its_labels(self):
        # v3.28.4: LR4-5's \irspectrumpage and sidefigure were drawn whole and \cref{fig:...} led nowhere
        root, done = self.build({"preamble.tex": "\\usepackage{tikz}\n\\newenvironment{sidebox}{}{}\n"},
                                "See [one](#fig:side) and [two](#fig:other).\n\n\\begin{sidebox}\n"
                                "\\begin{tikzpicture}\\draw (0,0) circle (1cm);\\end{tikzpicture}\n"
                                "\\label{fig:side}\\label{fig:other}\n\\end{sidebox}\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(unreached(root / "d.docx"), [])


@unittest.skipUnless(PANDOC, "needs Pandoc")
class DisplayBlocks(unittest.TestCase):
    def test_a_bracket_display_is_converted_like_any_math_and_math_the_reader_made_is_translated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "d.md").write_text("```{=latex}\n\\par\\nointerlineskip\n\\[\\ce{H2O} = \\SI{5}{\\milli\\liter}\\]\n\\par\\nointerlineskip\n```\n",
                                       encoding="utf-8")
            done = subprocess.run(["pandoc", "d.md", "-o", "d.docx", "--lua-filter", str(FILTER),
                                   "-M", f"pdfmd-office-python={Path(sys.executable).as_posix()}"], cwd=root,
                                  capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("Could not convert", done.stderr)
            xml = zipfile.ZipFile(root / "d.docx").read("word/document.xml").decode()
            self.assertIn("<m:oMathPara>", xml)
            self.assertNotIn("\\ce", xml)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class CheckDocx(unittest.TestCase):
    def test_it_names_what_would_be_a_picture_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "preamble.tex").write_text("\\usepackage{tikz}\n", encoding="utf-8")
            (root / "d.md").write_text("---\ntitle: T\n---\n\nWater \\ce{H2O} and $x^2$.\n\n"
                                       "\\begin{tikzpicture}\\draw (0,0) circle (1cm);\\end{tikzpicture}\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--check-docx"], cwd=root,
                                  capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": "",
                                                                       "XDG_CACHE_HOME": str(root / "cache")})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("pictures drawn by LaTeX: 1", done.stdout)
            self.assertIn("tikzpicture", done.stdout)
            self.assertRegex(done.stdout, r"native and editable: \d+ formula\(s\), [1-9]")
            self.assertEqual(sorted(path.name for path in root.iterdir() if path.is_file()), ["d.md", "preamble.tex"])

    def test_the_preamble_in_the_front_matter_is_not_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "d.md").write_text("---\ntitle: T\nheader-includes: |\n  \\usepackage{tikz}\n  \\usepackage{siunitx}\n---\n\n"
                                       "\\begin{tikzpicture}\\draw (0,0) circle (1cm);\\end{tikzpicture}\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--check-docx"], cwd=root,
                                  capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": "",
                                                                       "XDG_CACHE_HOME": str(root / "cache")})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("pictures drawn by LaTeX: 1", done.stdout)
            self.assertNotIn("usepackage", done.stdout + done.stderr)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class SeveralEquations(unittest.TestCase):
    def test_a_raw_block_of_equations_is_one_equation_each(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "d.md").write_text("---\ntitle: T\n---\n\n```{=latex}\n\\begin{equation}\\label{eq:a}\n  a = b\n\\end{equation}\n\n"
                                       "\\begin{equation}\\label{eq:b}\n  s = \\sqrt{\\frac{x}{n-1}}\n\\end{equation}\n```\n",
                                       encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "docx"], cwd=root,
                                  capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": "",
                                                                       "XDG_CACHE_HOME": str(root / "cache")})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertNotIn("eqno", done.stdout + done.stderr)
            xml = zipfile.ZipFile(root / "d.docx").read("word/document.xml").decode()
            self.assertEqual(xml.count("<m:oMath>"), 2)


@unittest.skipUnless(PANDOC and shutil.which("lualatex"), "needs Pandoc and LuaLaTeX")
class PartsReferences(unittest.TestCase):
    def test_a_reference_in_a_part_to_an_equation_in_another_has_its_number(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "parts").mkdir()
            (root / "report.md").write_text("---\ntitle: T\npdfmd-options:\n  parts: auto\n---\n\nLead.\n", encoding="utf-8")
            (root / "parts" / "10-theory.md").write_text("# Theory\n\n```{=latex}\n\\begin{equation}\\label{eq:a}\n  a = b\n"
                                                          "\\end{equation}\n```\n", encoding="utf-8")
            (root / "parts" / "20-results.md").write_text("# Results\n\nBy \\ref{eq:a} it follows.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report.md", "--to", "docx"], cwd=root,
                                  capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": "",
                                                                       "XDG_CACHE_HOME": str(root / "cache")})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            xml = zipfile.ZipFile(root / "report.docx").read("word/document.xml").decode()
            self.assertNotIn("??", xml)
            self.assertIn('>1</w:t></w:r></w:hyperlink>', xml)


@unittest.skipUnless(PANDOC and shutil.which("pdftocairo") and (shutil.which("lualatex") or shutil.which("xelatex")),
                     "needs Pandoc, a LaTeX engine and pdftocairo")
class PicturesMode(unittest.TestCase):
    def build(self, option: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "preamble.tex").write_text("\\usepackage{mhchem}\n", encoding="utf-8")
            (root / "d.md").write_text(f"---\ntitle: T\npdfmd-options:\n  office:\n    latex: {option}\n---\n\n"
                                       "Water \\ce{H2O} and $E = mc^2 + \\frac{a}{b}$.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "docx"], cwd=root,
                                  capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": "",
                                                                       "XDG_CACHE_HOME": str(root / "cache")})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            with zipfile.ZipFile(root / "d.docx") as archive:
                return archive.read("word/document.xml").decode() + " ".join(archive.namelist())

    def test_images_draws_what_auto_makes_native(self):
        auto, images = self.build("auto"), self.build("images")
        self.assertIn("<m:oMath>", auto)
        self.assertNotIn("media/", auto)
        self.assertNotIn("<m:oMath>", images)
        self.assertIn("media/", images)


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
        text = subprocess.run(["pdftotext", str(root / "d.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
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
        info = subprocess.run(["pdfinfo", str(root / "d.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertIn("A4", info)
        self.assertTrue(list((root / "cache").rglob("*.svg")))

    @unittest.skipUnless(TYPST, "needs Typst")
    def test_a_named_typst_draws_the_latex_without_being_asked(self):
        # v3.28.2: `-e typst` printed "Water ." and left the tikzpicture out, without a word
        root = self.folder()
        done = self.run_pdfmd(root, "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stderr)
        text = subprocess.run(["pdftotext", str(root / "d.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertIn("H2O", text.replace("\n", ""))
        self.assertTrue(list((root / "cache").rglob("*.svg")))
        said_no = self.folder("pdfmd-options:\n  raw: {typst: [typst]}\n")    # the document says Typst takes no LaTeX
        self.assertEqual(self.run_pdfmd(said_no, "-e", "typst").returncode, 0)
        self.assertFalse(list((said_no / "cache").rglob("*.svg")))

    @unittest.skipUnless(TYPST, "needs Typst")
    def test_typst_after_latex_failed_gets_the_filter(self):
        # the failed engines are recorded by TeX family (luatex, xetex, pdftex), which the check did not know: the
        # 3.24.x fallback never ran
        root = self.folder()
        source = root / "d.md"
        source.write_text(source.read_text(encoding="utf-8").replace("After.", "After. \\undefinedcommandxyz"),
                          encoding="utf-8")
        done = self.run_pdfmd(root, "-e", "")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("(typst;", done.stdout)
        text = subprocess.run(["pdftotext", str(root / "d.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertIn("H2O", text.replace("\n", ""))


class DroppedLatex(unittest.TestCase):
    """Which documents a Typst or HTML writer would lose LaTeX from (pdfmd.latex_dropped, v3.28.2)."""

    def dropped(self, text: str) -> bool:
        import pdfmd
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d.md"
            path.write_text(text, encoding="utf-8")
            return pdfmd.latex_dropped([path])

    def test_what_counts(self):
        self.assertTrue(self.dropped("Water \\ce{H2O}.\n"))
        self.assertTrue(self.dropped("Gas $\\ce{CO2}$ and $5\\,\\si{mL}$.\n"))
        self.assertTrue(self.dropped("```{=latex}\n\\vspace{1cm}\n```\n"))
        self.assertTrue(self.dropped("\\begin{tikzpicture}\\draw (0,0) circle (1);\\end{tikzpicture}\n"))

    def test_what_does_not(self):
        self.assertFalse(self.dropped("Plain text, $\\alpha + \\beta = \\gamma$ and $$\\int_0^1 x\\,dx$$.\n"))
        self.assertFalse(self.dropped("---\nheader-includes: |\n  \\usepackage{mhchem}\n---\n\nText.\n"))
        self.assertFalse(self.dropped("Use `\\newline` or\n\n```tex\n\\section{x}\n```\n"))

    def test_the_raw_option_decides_first_and_a_failed_latex_counts(self):
        import pdfmd
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d.md"
            path.write_text("---\npdfmd-options:\n  raw: {typst: [typst]}\n---\n\nWater \\ce{H2O}.\n", encoding="utf-8")
            self.assertFalse(pdfmd.office_fallback_wanted(path, [], set(), "typst", [path]))
            self.assertTrue(pdfmd.office_fallback_wanted(path, [], set(), "html", [path]))     # html not mentioned
            self.assertTrue(pdfmd.office_fallback_wanted(path, [], {"luatex"}, "typst", [path]))
        self.assertTrue(pdfmd.latex_failed({"xetex"}))
        self.assertFalse(pdfmd.latex_failed({"typst", "weasyprint"}))


# a house style's cover, as nulabreport draws it: the title and authors taken out of the metadata (v3.28.5)
COVER_PROFILE = ('return {pandoc = function(doc)\n'
                 '  doc.meta.title = nil; doc.meta.author = nil\n'
                 '  doc.blocks:insert(1, pandoc.Para({pandoc.Str("COVER")}))\n'
                 '  return doc\nend}\n')
# a straight quote and a backslash (in code: Pandoc's smart quotes would curl them) for the Typst string's escapes
COVERED = ("---\ntitle: 'Reduction of \\emph{trans}-Cinnamaldehyde, `\"a\\b\"`'\n"
           'author: ["A. One", "B. Two"]\n---\n\nBody with \\textbf{bold}.\n')
COVERED_TITLE = 'Reduction of trans-Cinnamaldehyde, "a\\b"'


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Properties(unittest.TestCase):
    """The title and authors a house style's cover took out stay in the file's properties, and pdfmd's own settings
    (folders of the machine that built it) are not among them (v3.28.5)."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root / "office.lua").write_text(COVER_PROFILE, encoding="utf-8")
        (self.root / "d.md").write_text(COVERED, encoding="utf-8")

    def tearDown(self):
        self.folder.cleanup()

    def pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], cwd=self.root,
                              capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "XDG_CACHE_HOME": str(self.root / "cache"),
                                   "XDG_CONFIG_HOME": str(self.root / "config"), "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def filtered(self, writer: str, *arguments: str) -> str:
        done = subprocess.run(["pandoc", "d.md", "-t", writer, "-s", "--lua-filter", str(FILTER), "-M",
                               f"pdfmd-office-profile={self.root / 'office.lua'}", "-M", "pdfmd-office-latex=auto",
                               *arguments], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def assert_private(self, path: Path):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                text = archive.read(name).decode("utf-8", "replace")
                self.assertNotIn("pdfmd-office", text, name)
                self.assertNotIn("pdfmd-raw", text, name)
                self.assertNotIn(str(self.root.resolve()), text, name)
                self.assertNotIn(tempfile.gettempdir(), text, name)

    def test_word_and_opendocument(self):
        self.pdfmd("d.md", "-o", "d.docx")
        with zipfile.ZipFile(self.root / "d.docx") as archive:
            core = archive.read("docProps/core.xml").decode()
            self.assertIn("COVER", archive.read("word/document.xml").decode())
        self.assertIn(f"<dc:title>{COVERED_TITLE}</dc:title>", core)
        self.assertIn("<dc:creator>A. One; B. Two</dc:creator>", core)
        self.assert_private(self.root / "d.docx")
        # title_meta.lua's title-meta repeats the Title: not a custom property of its own (v3.28.6)
        self.assertNotIn("title-meta", zipfile.ZipFile(self.root / "d.docx").read("docProps/custom.xml").decode())
        self.pdfmd("d.md", "-o", "d.odt")
        meta = zipfile.ZipFile(self.root / "d.odt").read("meta.xml").decode()
        self.assertIn(f"<dc:title>{COVERED_TITLE}</dc:title>", meta)
        self.assertIn("<meta:initial-creator>A. One; B. Two</meta:initial-creator>", meta)
        self.assert_private(self.root / "d.odt")
        self.assertEqual(zipfile.ZipFile(self.root / "d.odt").infolist()[0].filename, "mimetype")

    def test_html_and_typst(self):
        page = self.filtered("html5")
        self.assertIn(f"<title>{COVERED_TITLE.replace(chr(34), '&quot;')}</title>", page)
        self.assertIn('<meta name="author" content="A. One" />', page)
        self.assertIn('<meta name="author" content="B. Two" />', page)
        wanted = '#set document(title: "Reduction of trans-Cinnamaldehyde, \\"a\\\\b\\"", author: ("A. One", "B. Two",))'
        self.assertIn(wanted, self.filtered("typst", "-M", "pdfmd-office-typst-document=true"))
        self.assertNotIn("#set document(", self.filtered("typst"))          # pdfmd did not say the Typst takes it
        # in columns Pandoc 3.1.3's template puts the body in a container, where Typst refuses a document set rule
        self.assertNotIn("#set document(", self.filtered("typst", "-M", "pdfmd-office-typst-document=true",
                                                         "-V", "columns=2"))
        # a long title on one line, as Pandoc writes its own (WeasyPrint kept the line breaks in the PDF's Title)
        (self.root / "d.md").write_text(COVERED.replace(
            "title: '", "title: '" + " ".join(["Long"] * 30) + " "), encoding="utf-8")
        self.assertRegex(self.filtered("html5"), r"<title>(Long ){30}Reduction[^\n]*</title>")

    def test_a_document_that_keeps_its_title_is_left_alone(self):
        (self.root / "office.lua").write_text("return {}\n", encoding="utf-8")
        self.assertNotIn("#set document(", self.filtered("typst", "-M", "pdfmd-office-typst-document=true"))
        self.assertEqual(self.filtered("html5").count("<title>"), 1)

    def test_a_partial_builds_title_meta(self):
        # nulabreport.lua leaves only `title-meta` when it builds one part
        (self.root / "office.lua").write_text("return {}\n", encoding="utf-8")
        (self.root / "d.md").write_text("---\ntitle-meta: Part of a report\n---\n\nBody.\n", encoding="utf-8")
        self.assertIn("<title>Part of a report</title>", self.filtered("html5"))

    def test_none_of_pdfmds_settings_in_a_file_without_the_latex_filter(self):
        # the diagram filter's cache folder was a custom property of a Word or PowerPoint file, the filter on or off
        (self.root / "office.lua").unlink()
        (self.root / "d.md").write_text("---\ntitle: T\nkeep: this\npdfmd-options:\n  office: {latex: off}\n---\n\n"
                                        "```mermaid\ngraph TD; A-->B\n```\n", encoding="utf-8")
        for name in ("d.docx", "d.pptx"):
            self.pdfmd("d.md", "-o", name, "--no-cache")
            custom = zipfile.ZipFile(self.root / name).read("docProps/custom.xml").decode()
            self.assertNotIn("pdfmd-", custom)
            self.assertIn('pid="2" name="keep"', custom)          # the document's own key stays, numbered from 2
            self.assert_private(self.root / name)

    def test_finish_properties_fills_only_what_is_empty(self):
        from pdfmd_office import finish_properties
        (self.root / "e.md").write_text("---\ntitle: Own\npdfmd-x: /somewhere\n---\n\nBody.\n", encoding="utf-8")
        subprocess.run(["pandoc", "e.md", "-o", "e.docx"], cwd=self.root, check=True)
        self.assertTrue(finish_properties(self.root / "e.docx", "Other", ["Someone"]))
        with zipfile.ZipFile(self.root / "e.docx") as archive:
            core = archive.read("docProps/core.xml").decode()
            self.assertNotIn("pdfmd-x", archive.read("docProps/custom.xml").decode())
        self.assertIn("<dc:title>Own</dc:title>", core)
        self.assertIn("<dc:creator>Someone</dc:creator>", core)
        self.assertFalse(finish_properties(self.root / "e.docx", "Other", ["Someone"]))     # nothing left to do

    def test_a_pictures_folder_is_not_in_its_description(self):
        # Pandoc writes a picture's source into a Word picture's description: for a picture the LaTeX filter drew, a
        # file in pdfmd's cache, the home folder spelled out
        from pdfmd_office import finish_properties
        (self.root / "cache").mkdir()
        (self.root / "cache" / "drawn.png").write_bytes(TINY_PNG)
        (self.root / "e.md").write_text(f"![A dot]({(self.root / 'cache' / 'drawn.png').as_posix()})\n", encoding="utf-8")
        subprocess.run(["pandoc", "e.md", "-o", "e.docx"], cwd=self.root, check=True)
        before = zipfile.ZipFile(self.root / "e.docx").read("word/document.xml").decode()
        self.assertIn((self.root / "cache").as_posix(), before)
        self.assertTrue(finish_properties(self.root / "e.docx", folders=[str(self.root / "cache")]))
        after = zipfile.ZipFile(self.root / "e.docx").read("word/document.xml").decode()
        self.assertNotIn((self.root / "cache").as_posix(), after)
        self.assertIn('descr="drawn.png"', after)
        self.assertIn("A dot", after)                       # the description a reader sees stays

    def test_a_latex_pdfs_title_keeps_its_latex(self):
        # v3.28.6: Pandoc's title-meta (hyperref's pdftitle) left raw LaTeX out: "Reduction of -Cinnamaldehyde, ..."
        (self.root / "office.lua").unlink()
        done = self.pdfmd("d.md", "--to", "latex", "-o", "d.tex", "-v")
        self.assertIn("pdftitle={Reduction of trans-Cinnamaldehyde,", (self.root / "d.tex").read_text(encoding="utf-8"))
        self.assertIn("pdfauthor={A. One; B. Two}", (self.root / "d.tex").read_text(encoding="utf-8"))
        self.assertIn("title_meta.lua", done.stdout + done.stderr)
        # a filter of the document's own that takes the title out and keeps title-meta, as nulabreport's does for a
        # part built alone, finds it set already
        (self.root / "d.lua").write_text(
            "function Meta(m)\n  if not m['title-meta'] then m['title-meta'] = pandoc.MetaString("
            "pandoc.utils.stringify(m.title)) end\n  m.title = nil\n  return m\nend\n", encoding="utf-8")
        self.pdfmd("d.md", "--to", "latex", "-o", "d.tex")
        self.assertIn("pdftitle={Reduction of trans-Cinnamaldehyde,", (self.root / "d.tex").read_text(encoding="utf-8"))
        # a title without LaTeX: Pandoc's own, no filter
        (self.root / "d.lua").unlink()
        (self.root / "d.md").write_text("---\ntitle: Plain\n---\n\nBody.\n", encoding="utf-8")
        done = self.pdfmd("d.md", "--to", "latex", "-o", "d.tex", "-v")
        self.assertNotIn("title_meta.lua", done.stdout + done.stderr)
        self.assertIn("pdftitle={Plain}", (self.root / "d.tex").read_text(encoding="utf-8"))

    def test_a_calibre_pdf(self):
        try:
            import pypdf
        except ImportError:
            self.skipTest("needs pypdf")
        if not shutil.which("ebook-convert"):
            self.skipTest("needs Calibre")
        self.pdfmd("d.md", "-e", "calibre", "-o", "d.pdf")
        info = pypdf.PdfReader(str(self.root / "d.pdf")).metadata
        self.assertEqual(info.get("/Title"), COVERED_TITLE)        # was "d", by "Unknown"
        self.assertIn("A. One", info.get("/Author", ""))
