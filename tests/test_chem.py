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
        formulas = []
        for kind, source, _ in json.loads((FIXTURES / "mhchem" / "documents.json").read_text(encoding="utf-8")) + \
                json.loads((FIXTURES / "mhchem" / "upstream.json").read_text(encoding="utf-8")):
            if kind in ("ce", "pu"):
                try:
                    runs, _ = render.convert(source, kind)
                except (render.RenderError, render.MhchemError):
                    continue
                formulas.append((source, render.math_tex(runs)))
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
        self.assertEqual(batch.answer({"items": []}), [])


if __name__ == "__main__":
    unittest.main()
