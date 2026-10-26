"""pdfmd_chem: siunitx's numbers and units and mhchem's formulas as text runs and as math Pandoc converts.

tests/fixtures/chem/siunitx-latex.json holds what siunitx 3.4.14 printed (LuaLaTeX, then pdftotext, spaces left
out) for 269 commands, with siunitx's defaults and with nulabreport's `\\sisetup`; the mhchem formulas are those of
tests/fixtures/mhchem/.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfmd_chem import batch, render, siunitx  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
HOUSE = (r"\sisetup{output-decimal-marker={.}, group-separator={,}} "
         r"\DeclareSIUnit[quantity-product = \,]{\atm}{atm} \DeclareSIUnit[quantity-product = \,]{\torr}{torr} "
         r"\DeclareSIUnit[quantity-product = \,]{\molar}{M}")
UNITS_ONLY = HOUSE.split("} ", 1)[1]


def flat(runs) -> str:
    return re.sub(r"\s+", "", "".join(text for text, _ in runs)).replace("−", "-")


class Siunitx(unittest.TestCase):
    def test_what_latex_prints(self):
        rows = json.loads((FIXTURES / "chem" / "siunitx-latex.json").read_text(encoding="utf-8"))
        settings = {"default": siunitx.settings_from_preamble(UNITS_ONLY), "house": siunitx.settings_from_preamble(HOUSE)}
        for command, default, house in rows:
            for name, expected in (("default", default), ("house", house)):
                with self.subTest(command=command, setup=name):
                    if expected is None:
                        with self.assertRaises(siunitx.SiunitxError):
                            siunitx.convert(command, settings[name])
                    else:
                        self.assertEqual(flat(siunitx.runs_text(siunitx.convert(command, settings[name]))), expected)

    def test_spaces_and_scripts(self):
        house = siunitx.settings_from_preamble(HOUSE)
        self.assertEqual(siunitx.runs_text(siunitx.convert(r"\qty{25}{\mL}")), [("25 mL", "")])
        self.assertEqual(siunitx.runs_text(siunitx.convert(r"\num{1.5e-3}")), [("1.5 × 10", ""), ("−3", "sup")])
        self.assertEqual(siunitx.runs_text(siunitx.convert(r"\si{\gram\per\mole}")), [("g mol", ""), ("−1", "sup")])
        self.assertEqual(siunitx.runs_text(siunitx.convert(r"\num{12345}", house)), [("12,345", "")])
        self.assertEqual(siunitx.runs_text(siunitx.convert(r"\qty{90}{\degree}")), [("90°", "")])

    def test_the_preamble(self):
        settings = siunitx.settings_from_preamble(
            "\\sisetup{per-mode = symbol}\n\\DeclareSIUnit[quantity-product = \\,]{\\molar}{M}\n"
            "\\newcommand{\\gml}{\\gram\\per\\milli\\liter}  % a shortcut\n\\newcommand{\\note}[1]{#1}")
        self.assertEqual(flat(siunitx.convert(r"\qty{1.2}{\gml}", settings)), "1.2g/mL")
        self.assertEqual(flat(siunitx.convert(r"\qty{3}{\milli\molar}", settings)), "3mM")
        self.assertNotIn("note", settings.shortcuts)

    def test_math(self):
        self.assertEqual(siunitx.runs_tex(siunitx.convert(r"\qty{1.5e-3}{\mol\per\litre}")),
                         r"1.5\times 10^{-3}\,\mathrm{mol}\,\mathrm{L}^{-1}")
        self.assertEqual(siunitx.runs_tex(siunitx.convert(r"\qtyrange{1}{5}{\mL}")),
                         r"1\,\mathrm{mL}\text{ to }5\,\mathrm{mL}")

    def test_an_empty_unit_prints_the_number_alone(self):
        # siunitx 2 style, as in study notes: \SI{1.8e-5}{} is \num{1.8e-5} (issue 12)
        number = siunitx.runs_tex(siunitx.convert(r"\num{1.8e-5}"))
        for command in (r"\SI{1.8e-5}{}", r"\qty{1.8e-5}{}", r"\SI{1.8e-5}{ }"):
            with self.subTest(command=command):
                self.assertEqual(siunitx.runs_tex(siunitx.convert(command)), number)
        self.assertEqual(flat(siunitx.convert(r"\SIrange{1}{2}{}")), "1to2")
        self.assertEqual(siunitx.convert(r"\si{}"), [])

    def test_what_it_refuses(self):
        for command in (r"\num{2 x 3}", r"\si{\unknownunit}", r"\qty{5}", r"\num{abc}"):
            with self.subTest(command=command), self.assertRaises(siunitx.SiunitxError):
                siunitx.convert(command)


class Chemistry(unittest.TestCase):
    def convert(self, source, kind="ce"):
        runs, needs_math = render.convert(source, kind)
        return render.text_runs(runs), render.math_tex(runs), needs_math

    def test_formulas(self):
        self.assertEqual(self.convert("H2O"), ([("H", ""), ("2", "sub"), ("O", "")], r"\mathrm{H}_{2}\mathrm{O}", False))
        self.assertEqual(self.convert("SO4^2-")[0], [("SO", ""), ("4", "sub"), ("2−", "sup")])
        self.assertEqual(self.convert("2H2O")[1], r"2\,\mathrm{H}_{2}\mathrm{O}")
        self.assertEqual(self.convert("CuSO4.5H2O")[1], r"\mathrm{CuSO}_{4}\cdot 5\,\mathrm{H}_{2}\mathrm{O}")

    def test_what_the_lua_translator_got_wrong(self):
        self.assertEqual(self.convert("-COO-")[0], [("−COO−", "")])                 # bonds, not a charge
        self.assertEqual(self.convert("^15N")[0], [("¹⁵N", "")])                   # Unicode: no empty base
        self.assertEqual(self.convert("(CH2O)_n")[0], [("(CH", ""), ("2", "sub"), ("O)", ""), ("n", "sub")])
        self.assertIn(r"\mathrm{NaBH}_{4}", self.convert("A ->[NaBH4] B")[1])

    def test_an_arrow_with_words_needs_math(self):
        runs, math, needs_math = self.convert("A ->[\\Delta][-H2O] B")
        self.assertTrue(needs_math)
        self.assertEqual(math, r"\mathrm{A}\overset{\mathrm{Δ}}{\underset{-\mathrm{H}_{2}\mathrm{O}}{\longrightarrow}}"
                               r"\mathrm{B}")

    def test_two_subscripts_in_a_row_are_one(self):
        self.assertEqual(self.convert("CO3^2-_{(aq)}")[1], r"\mathrm{CO}_{3\,(\mathrm{aq})}^{2-}")

    def test_a_ce_inside_math_inside_a_ce(self):
        math = self.convert(r"Hg^2+ ->[I-] $\underset{\mathrm{red}}{\ce{HgI2}}$")[1]
        self.assertIn(r"\underset{\mathrm{red}}{{\mathrm{HgI}_{2}}}", math)

    def test_units(self):
        self.assertEqual(self.convert("123 kJ/mol", "pu")[1], r"123\ \mathrm{kJ}/\mathrm{mol}")
        self.assertEqual(self.convert("1.2e3 kJ", "pu")[1], r"1.2\cdot 10^{3}\ \mathrm{kJ}")

    def test_what_it_leaves_to_latex(self):
        with self.assertRaises(render.RenderError):
            render.convert(r"R-CHO + \chemfig{A-B}")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class PandocReadsTheMath(unittest.TestCase):
    """every formula's math TeX through Pandoc's own converter (texmath): MathML, so Word gets an equation"""

    def test_every_fixture_formula(self):
        formulas, as_text = [], set()           # as_text: formulas text outputs show as text (chem.lua), not as math
        for kind, source, _ in json.loads((FIXTURES / "mhchem" / "documents.json").read_text(encoding="utf-8")) + \
                json.loads((FIXTURES / "mhchem" / "upstream.json").read_text(encoding="utf-8")):
            if kind in ("ce", "pu"):
                try:
                    runs, needs_math = render.convert(source, kind)
                except (render.RenderError, render.MhchemError):
                    continue
                formulas.append((source, render.math_tex(runs)))
                if needs_math:
                    as_text.add(render.math_tex(runs))
        house = siunitx.settings_from_preamble(HOUSE)
        for command, default, _ in json.loads((FIXTURES / "chem" / "siunitx-latex.json").read_text(encoding="utf-8")):
            if default is not None:
                formulas.append((command, siunitx.runs_tex(siunitx.convert(command, house))))
        script = ('local out = {}\nfor line in io.lines(arg[1]) do\n'
                  '  local ok, html = pcall(pandoc.write, pandoc.Pandoc({pandoc.Plain({pandoc.Math("InlineMath", line)})}),'
                  ' "html", pandoc.WriterOptions({html_math_method = "mathml"}))\n'
                  '  out[#out + 1] = (ok and html:find("<math", 1, true)) and "1" or "0"\nend\n'
                  'io.write(table.concat(out))\n')
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "check.lua").write_text(script, encoding="utf-8")
            (Path(folder) / "formulas.txt").write_text("\n".join(tex for _, tex in formulas) + "\n", encoding="utf-8")
            done = subprocess.run(["pandoc", "lua", "check.lua", "formulas.txt"], cwd=folder, capture_output=True,
                                  text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        failed = [source for (source, _), mark in zip(formulas, done.stdout) if mark != "1"]
        self.assertEqual(len(done.stdout), len(formulas))
        self.assertEqual(failed, [])
        # and Typst and plain text (v3.28.10: chem.lua's outputs): no TeX left over
        typst = ('local bad = {}\nfor line in io.lines(arg[1]) do\n'
                 '  for _, writer in ipairs({"typst", "plain"}) do\n'
                 '    local ok, out = pcall(pandoc.write, pandoc.Pandoc({pandoc.Plain({pandoc.Math("InlineMath", line)})}),'
                 ' writer)\n'
                 '    if not ok or out:find("\\\\[A-Za-z]") then bad[#bad + 1] = writer .. ": " .. line end\n'
                 '  end\nend\nio.write(table.concat(bad, "\\n"))\n')
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "check.lua").write_text(typst, encoding="utf-8")
            (Path(folder) / "formulas.txt").write_text("\n".join(tex for _, tex in formulas) + "\n", encoding="utf-8")
            done = subprocess.run(["pandoc", "lua", "check.lua", "formulas.txt"], cwd=folder, capture_output=True,
                                  text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        bad = [line for line in done.stdout.splitlines() if line.split(": ", 1)[1] not in as_text
               or line.startswith("typst")]
        self.assertEqual(bad, [])


class CommandLists(unittest.TestCase):
    def test_one_list_of_commands(self):
        import pdfmd
        lua = (ROOT / "pdfmd_lua" / "chem_client.lua").read_text(encoding="utf-8")
        block = re.search(r"M\.NAMES = \{(.*?)\}", lua, re.S).group(1)
        lua_names = set(re.findall(r"(\w+) = true", block))
        self.assertEqual(lua_names, set(pdfmd.CHEM_COMMANDS))
        self.assertEqual(set(batch.CHEMISTRY) | set(siunitx.COMMANDS), set(pdfmd.CHEM_COMMANDS))


DOCUMENT = ("---\ntitle: Routes\n---\n\nWater \\ce{H2O}, \\qty{25}{\\mL}, $\\ce{CO2}$ and \\ce{A ->[\\Delta] B}.\n\n"
            "\\ce{2H2 + O2 -> 2H2O}\n\nIsotope \\ce{^15N}, $\\num{1.5e-3}$.\n")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Routes(unittest.TestCase):
    """v3.28.10: the outputs the LaTeX filter does not run for (chem.lua)"""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        root = Path(cls.folder.name)
        (root / "d.md").write_text(DOCUMENT, encoding="utf-8")
        cls.out = {}
        for target in ("html", "gfm", "txt", "ascii", "typst", "markdown"):
            extra = ["-s"] if target == "markdown" else []
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", target, "-o", f"d.{target}",
                                   *extra], cwd=root, capture_output=True, text=True,
                                  env={**__import__("os").environ, "PDFMD_CONFIG": "", "XDG_CACHE_HOME": str(root / "c"),
                                       "PDFMD_NO_PROMPT": "1"})
            assert done.returncode == 0, done.stdout + done.stderr
            cls.out[target] = (root / f"d.{target}").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_html(self):
        page = self.out["html"]
        self.assertIn("Water H<sub>2</sub>O, 25\u202fmL", page)
        self.assertIn("2\u202fH<sub>2</sub> + O<sub>2</sub> \u27f6 2\u202fH<sub>2</sub>O", page)   # a paragraph of its own
        self.assertIn("\u00b9\u2075N", page)
        self.assertNotIn("\\ce", page)

    def test_markdown_and_text(self):
        # in Markdown a formula that is one command is text too
        self.assertIn("Water H\u2082O, 25\u202fmL, CO\u2082 and", self.out["gfm"])
        self.assertIn("1.5\u202f\u00d7\u202f10\u207b\u00b3", self.out["gfm"])
        self.assertIn("A \u27f6 (\u0394) B", self.out["gfm"])               # no equation in Markdown: the words follow
        self.assertIn("CO\u2082 and A \u27f6 (\u0394) B", self.out["txt"])
        self.assertIn("H_2O", self.out["ascii"])

    def test_typst(self):
        self.assertIn("H#sub[2]O", self.out["typst"])
        self.assertNotIn("\\ce", self.out["typst"])

    def test_none_of_its_settings_in_the_output(self):
        # a standalone Markdown file writes the metadata: pdfmd-chem-python (the home folder) is taken out first
        self.assertNotIn("pdfmd-chem", self.out["markdown"])


class WhatItCannotConvert(unittest.TestCase):
    """issue 12: an empty unit in a formula took the whole formula down, and the loss was silent"""

    def build(self, text):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "d.md").write_text(text, encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--from", "markdown", "--to", "typst",
                                   "-o", "d.typ"], cwd=root, capture_output=True, text=True,
                                  env={**__import__("os").environ, "PDFMD_CONFIG": "", "XDG_CACHE_HOME": str(root / "c"),
                                       "PDFMD_NO_PROMPT": "1"})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            return (root / "d.typ").read_text(encoding="utf-8"), done.stdout + done.stderr

    def test_an_empty_unit_in_a_formula_and_in_text(self):
        typst, _ = self.build("B: $\\ce{K_a} = \\SI{1.8e-5}{}$\n\nD: \\SI{1.8e-5}{} here\n")
        self.assertNotIn("\\SI", typst)
        self.assertIn("upright(K)", typst)
        self.assertIn("10#super[\u22125] here", typst)

    def test_a_command_it_cannot_convert_is_named_in_a_warn(self):
        typst, report = self.build("F: \\SI{3}{\\bogus} here and $x = \\SI{3}{\\bogus}$\n")
        self.assertEqual(report.count("[pdfmd] WARN \\SI{3}{\\bogus} cannot be converted"), 1)
        self.assertIn("x = \\SI{3}{\\bogus} cannot be converted", report)
        self.assertIn("is not known", report)


class Batch(unittest.TestCase):
    def test_one_call_for_a_document(self):
        request = {"preamble": r"\sisetup{group-separator={,}}",
                   "items": [{"text": r"\ce{H2O}"}, {"math": r"c = \SI{12345}{\mol}, \ce{Cu^2+}"},
                             {"text": r"\num{2 x 3}"}]}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd_chem")], input=json.dumps(request),
                              capture_output=True, text=True, check=True)
        answers = json.loads(done.stdout)
        self.assertEqual(answers[0]["runs"], [["H", ""], ["2", "sub"], ["O", ""]])
        self.assertEqual(answers[1]["math"], r"c = {12{,}345\,\mathrm{mol}}, {\mathrm{Cu}^{2+}}")
        self.assertIn("error", answers[2])
        # a reaction scheme is LaTeX's to draw: its \\ce are left as they are
        scheme = batch.answer({"items": [{"math": r"\schemestart A \arrow{->[\ce{NaBH4}]} B \schemestop"}]})
        self.assertIn("error", scheme[0])
        self.assertEqual(batch.answer({"items": []}), [])


if __name__ == "__main__":
    unittest.main()
