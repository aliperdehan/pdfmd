"""pdfmd_mhchem: the Python port of mhchemParser 4.2.1 gives the TeX the JavaScript original gives.

The fixtures hold the original's own answers: its test suite (upstream.json), the \\ce of real lab reports
(documents.json) and generated inputs, mhchem's errors included (odd.json). With `PDFMD_MHCHEM_NODE` set to a
`node_modules` folder that has `mhchemparser` (`npm install mhchemparser@4.2.1`), fresh random inputs are compared
with the original itself; without it that test is skipped (pdfmd's users never need node).
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfmd_mhchem import MhchemError, parse, to_tex  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "mhchem"


def answer(kind: str, given: str) -> str | None:
    try:
        return to_tex(given, kind)
    except MhchemError:
        return None


class Fixtures(unittest.TestCase):
    def check(self, name: str):
        cases = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        self.assertTrue(cases)
        for kind, given, expected in cases:
            with self.subTest(kind=kind, given=given):
                self.assertEqual(answer(kind, given), expected)

    def test_mhchems_own_tests(self):
        self.check("upstream.json")

    def test_the_formulas_of_real_lab_reports(self):
        self.check("documents.json")

    def test_odd_inputs_and_errors(self):
        self.check("odd.json")


class Examples(unittest.TestCase):
    def test_what_the_lua_translator_got_wrong(self):
        # the old office.lua translator read a bond at the end as a charge and left an arrow's label as text
        self.assertEqual(to_tex("-COO-"), "{{-}\\mathrm{COO}{-}}")
        self.assertIn("\\mathrm{NaBH}{\\vphantom{A}}_{\\smash[t]{4}}", to_tex("->[NaBH4]"))
        self.assertEqual(to_tex("^15N"), "{{\\vphantom{A}}^{\\hphantom{15}}_{\\hphantom{}}\\mkern-1.5mu{\\vphantom{A}}"
                                          "^{\\smash[t]{\\vphantom{2}}\\llap{15}}_{\\vphantom{2}\\llap{\\smash[t]{}}}"
                                          "\\mathrm{N}}")

    def test_units_and_tex(self):
        self.assertEqual(to_tex("123 kJ/mol", "pu"), "{123~\\mathrm{kJ}/\\mathrm{mol}}")
        self.assertEqual(to_tex("m_{\\ce{H2O}} = \\pu{1.2kg}", "tex"),
                         "m_{{\\mathrm{H}{\\vphantom{A}}_{\\smash[t]{2}}\\mathrm{O}}} = {1.2~\\mathrm{kg}}")

    def test_the_parsed_form(self):
        parsed = parse("H2O")
        self.assertEqual([item["type_"] for item in parsed], ["chemfive", "chemfive"])
        self.assertEqual(parsed[0]["o"], [{"type_": "rm", "p1": "H"}])
        self.assertEqual(parsed[0]["q"], ["2"])

    def test_an_error_is_mhchems_own(self):
        with self.assertRaises(MhchemError):
            to_tex("->[\\bond{=}}Ag")             # a brace closed that was never opened
        self.assertEqual(to_tex("A}"), "{\\mathrm{A}}}")
        self.assertEqual(to_tex(""), "")


class Licence(unittest.TestCase):
    def test_the_port_keeps_its_licence(self):
        self.assertIn("Apache License", (ROOT / "pdfmd_mhchem" / "LICENSE").read_text(encoding="utf-8"))
        header = (ROOT / "pdfmd_mhchem" / "parser.py").read_text(encoding="utf-8")[:1500]
        self.assertIn("Copyright (c) 2015-2023 Martin Hensel", header)
        self.assertIn("Changes (pdfmd", header)


NODE_MODULES = os.environ.get("PDFMD_MHCHEM_NODE")


@unittest.skipUnless(NODE_MODULES and shutil.which("node")
                     and (Path(NODE_MODULES or ".") / "mhchemparser").is_dir(),
                     "a development check: set PDFMD_MHCHEM_NODE to a node_modules folder with mhchemparser")
class AgainstTheOriginal(unittest.TestCase):
    TOKENS = ["H", "C", "O", "N", "Na", "Cl", "Fe", "Cu", "x", "n", "i", "R", "2", "3", "12", "0.5", "1/2", "+", "-",
              "^", "_", "{", "}", "(", ")", "[", "]", "=", "#", "~", ".", "*", "...", " ", "->", "<=>", "<->", "<=>>",
              "$", "$x$", "\\alpha", "\\Delta", "\\bond{~}", "(aq)", "(s)", " v", " ^", ",", "'", "\\,", "^2+", "_{n}",
              "pH", "sp", "\\ce{H2O}", "\\pu{1 kg}", "&", "/", "IV", "+II", "->[", "][", "T[", "\\frac{1}{2}", "e", "10^3"]

    def test_random_inputs(self):
        generator = random.Random()
        inputs = sorted({"".join(generator.choice(self.TOKENS) for _ in range(generator.randint(1, 9)))
                         for _ in range(3000)})
        script = ("const { mhchemParser } = require('mhchemparser');\n"
                  "const inputs = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                  "const out = inputs.map(s => { try { return mhchemParser.toTex(s, 'ce'); } catch (e) { return null; } });\n"
                  "process.stdout.write(JSON.stringify(out));\n")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reference.cjs"
            path.write_text(script, encoding="utf-8")
            done = subprocess.run(["node", str(path)], input=json.dumps(inputs), capture_output=True, text=True,
                                  env={**os.environ, "NODE_PATH": str(NODE_MODULES)}, check=True)
        for given, expected in zip(inputs, json.loads(done.stdout)):
            with self.subTest(given=given):
                self.assertEqual(answer("ce", given), expected)


if __name__ == "__main__":
    unittest.main()
