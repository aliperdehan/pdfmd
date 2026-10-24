"""The inline calculator (v3.30.4): `2026 - 2006`{=} becomes 20 through pdfmd_lua/calc.lua's own parser; the detection that
adds the filter, the `calc: off` switch, and a real PDF built through the whole pipeline (a part included)."""

from __future__ import annotations

import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
CALC_LUA = ROOT / "pdfmd_lua" / "calc.lua"

# expression -> the text it becomes (R's print: 7 significant digits, 20 and not 20.0)
VALUES = (
    ("2026 - 2006", "20"), ("2 * 20 / 10", "4"), ("0.1 + 0.2", "0.3"), ("1/3", "0.3333333"), ("-2^2", "-4"), ("2^3^2", "512"),
    ("2^-1", "0.5"), ("(1 + 2) * 3", "9"), ("--3", "3"), ("6.022e23 * 2", "1.2044e+24"), ("1e-3", "0.001"), (".5 + .5", "1"),
    ("7 % 3", "1"), ("-7 % 3", "2"), ("-7 %% 3", "2"), ("7 %/% 2", "3"), ("7 // 2", "3"), ("-7 // 2", "-4"), ("2 ** 10", "1024"),
    ("10^15", "1e+15"), ("999999999999999", "999999999999999"), ("3 * 1000000000000000000", "3e+18"),
    ("0.5 / 4 * 100%", "12.5"), ("sqrt(0.13%^2 + 2.48%^2)", "2.483405"), ("(230.7 - 243.05) / 243.05 * 100 %", "-5.081259"), ("7 %(2+1)", "1"),
    ("|3 - 5| / 2", "1"), ("|0.019593 - 0.020204| / 0.000346", "1.765896"), ("|1 - 3| - |2 - 5|", "-1"), ("2 \u00d7 3 \u2212 1", "5"),
    ("6 \u00f7 4", "1.5"), ("2 \u00b7 3", "6"),
    ("sin(pi)", "0"), ("cos(pi/2)", "0"), ("sin(pi/6)", "0.5"), ("sin(30*deg)", "0.5"), ("sind(30)", "0.5"), ("cosd(60)", "0.5"),
    ("tand(45)", "1"), ("tan(pi/4)", "1"), ("cot(pi/4)", "1"), ("sec(0)", "1"), ("csc(pi/2)", "1"),
    ("asin(1)", "1.570796"), ("acos(0)", "1.570796"), ("atan(1) * 4", "3.141593"), ("atan(1, 1)", "0.7853982"), ("atan(-1, -1)", "-2.356194"),
    ("asind(0.5)", "30"), ("acosd(0.5)", "60"), ("atand(1)", "45"), ("atand(1, -1)", "135"), ("asin(0.5) / deg", "30"),
    ("acot(1)", "0.7853982"), ("sinh(0)", "0"), ("cosh(0)", "1"), ("tanh(1)", "0.7615942"), ("asinh(0)", "0"), ("acosh(1)", "0"), ("atanh(0)", "0"),
    ("exp(1)", "2.718282"), ("ln(exp(2))", "2"), ("log(100, 10)", "2"), ("log(8, 2)", "3"), ("log10(1000)", "3"), ("log2(8)", "3"),
    ("sqrt(2)", "1.414214"), ("cbrt(27)", "3"), ("cbrt(-8)", "-2"), ("abs(-3.5)", "3.5"), ("sign(-9)", "-1"), ("hypot(3, 4)", "5"),
    ("floor(-2.5)", "-3"), ("ceil(2.1)", "3"), ("trunc(-2.7)", "-2"), ("round(2.5)", "2"), ("round(3.5)", "4"), ("round(-2.5)", "-2"), ("round(-0.4)", "0"), ("round(2.675, 2)", "2.67"),
    ("round(0.125, 2)", "0.12"), ("round(0.15, 1)", "0.1"), ("round(2.6)", "3"),
    ("round(1234.5678, 1)", "1234.6"), ("min(4, 2, 8)", "2"), ("max(4, 2, 8)", "8"), ("factorial(10)", "3628800"), ("0 * -1", "0"),
)

FAILS = (
    ("1/0", "division by zero"), ("5 // 0", "division by zero"), ("5 % 0", "division by zero"), ("foo(2)", "'foo' is not a function"),
    ("x + 1", "'x' is not defined"), ("3 +", "ends too soon"), ("(1 + 2", "expected ')'"), ("1 2", "unexpected"), ("|1 - 2", "expected '|'"), ("2 $ 3", "is not arithmetic"),
    ("asin(2)", "not defined there"), ("asind(2)", "not defined there"), ("sqrt(-1)", "not defined there"), ("ln(0)", "not defined there"), ("acosh(0.5)", "not defined there"),
    ("(-8)^(1/3)", "not a number"), ("10^400", "infinite"), ("sin(1, 2)", "takes 1 argument"), ("min()", "needs a number"),
    ("round(2.5, 1.5)", "whole number"), ("factorial(2.5)", "whole number"), ("factorial(171)", "whole number"), ("cot(0)", "not defined"),
)


class Detection(unittest.TestCase):
    def test_what_adds_the_filter(self):
        for text in ("so `1/2`{=} is half", "`1/2`{=}.", "``1/2``{=}", "a `2+2`{=}, b", "`1/3`{=4sf}", "`1/3`{=2dp}", "::: calc", "::: {.calc}",
                     "::::: {#c1 .calc}", "  ::: calc"):
            with self.subTest(text=text):
                self.assertTrue(pdfmd.CALC_SPAN_RE.search(text))

    def test_what_does_not(self):
        for text in ("`1/2` is half", "`1/2`{.calc}", "{=} alone", "`{r} 1+1`", "{ans} in prose", "::: calculation", "::: {.csv}", "`x`{=html}"):
            with self.subTest(text=text):
                self.assertFalse(pdfmd.CALC_SPAN_RE.search(text))

    def test_the_filter_goes_in_for_a_document_with_one_and_a_part_is_enough(self):
        with tempfile.TemporaryDirectory() as directory:
            plain = Path(directory) / "plain.md"
            plain.write_text("`2+2` stays.\n", encoding="utf-8")
            marked = Path(directory) / "marked.md"
            marked.write_text("It is `2+2`{=}.\n", encoding="utf-8")
            self.assertEqual(pdfmd.calc_filter_args(plain, []), [])
            self.assertEqual(pdfmd.calc_filter_args([plain, marked], []), ["-M", "pdfmd-calc-round=even", "-M", "pdfmd-calc-noindent=true",
                                                                                    "-M", "pdfmd-calc-space=0.75em", "--lua-filter", str(CALC_LUA)])

    def test_calc_off_in_the_options_or_a_metadata_file_leaves_the_span_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            for header in ("pdfmd-options:\n  calc: off\n", "pdfmd-options:\n  calc: false\n"):
                with self.subTest(header=header):
                    off = Path(directory) / "off.md"
                    off.write_text(f"---\n{header}---\n\nIt is `2+2`{{=}}.\n", encoding="utf-8")
                    self.assertEqual(pdfmd.calc_filter_args(off, []), [])
            for header in ("pdfmd-options:\n  calc:\n    enabled: false\n", "pdfmd-options:\n  calc:\n    enabled: off\n"):
                with self.subTest(header=header):
                    mapped = Path(directory) / "mapped.md"
                    mapped.write_text(f"---\n{header}---\n\nIt is `2+2`{{=}}.\n", encoding="utf-8")
                    self.assertEqual(pdfmd.calc_filter_args(mapped, []), [])
            digits = Path(directory) / "digits.md"
            digits.write_text("---\npdfmd-options:\n  calc:\n    digits: 4sf\n---\n\nIt is `2+2`{=}.\n", encoding="utf-8")
            self.assertEqual(pdfmd.calc_filter_args(digits, []), ["-M", "pdfmd-calc-round=even", "-M", "pdfmd-calc-digits=4sf",
                                                                   "-M", "pdfmd-calc-noindent=true", "-M", "pdfmd-calc-space=0.75em",
                                                                   "--lua-filter", str(CALC_LUA)])
            on = Path(directory) / "on.md"
            on.write_text("---\npdfmd-options:\n  calc: on\n---\n\nIt is `2+2`{=}.\n", encoding="utf-8")
            self.assertIn("--lua-filter", pdfmd.calc_filter_args(on, []))
            meta = Path(directory) / "metadata.yaml"
            meta.write_text("pdfmd-options:\n  calc: off\n", encoding="utf-8")
            plain = Path(directory) / "plain.md"
            plain.write_text("It is `2+2`{=}.\n", encoding="utf-8")
            self.assertEqual(pdfmd.calc_filter_args(plain, [meta]), [])


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def convert(self, text: str, writer: str = "plain") -> subprocess.CompletedProcess:
        return subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--wrap=none", "--lua-filter", str(CALC_LUA)], input=text,
                              capture_output=True, text=True, encoding="utf-8")

    def test_the_values(self):
        for expression, expected in VALUES:
            with self.subTest(expression=expression):
                done = self.convert(f"It is `{expression}`{{=}}.\n")
                self.assertEqual(done.stdout.strip(), f"It is {expected}.", done.stderr)
                self.assertEqual(done.stderr, "")

    def test_round_away_from_zero_when_asked(self):
        for expression, expected in (("round(2.5)", "3"), ("round(-2.5)", "-3"), ("round(2.675, 2)", "2.68"), ("round(0.125, 2)", "0.13"),
                                     ("round(3.5)", "4"), ("round(2.4)", "2")):
            with self.subTest(expression=expression):
                done = subprocess.run([PANDOC, "-f", "markdown", "-t", "plain", "-M", "pdfmd-calc-round=away", "--lua-filter", str(CALC_LUA)],
                                      input=f"`{expression}`{{=}}\n", capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(done.stdout.strip(), expected, done.stderr)

    def test_what_fails_keeps_the_code_and_warns_once(self):
        for expression, reason in FAILS:
            with self.subTest(expression=expression):
                done = self.convert(f"It is `{expression}`{{=}}.\n")
                self.assertEqual(done.stdout.strip(), f"It is {expression}.")
                self.assertEqual(done.stderr.count("WARN  calc:"), 1, done.stderr)
                self.assertIn(reason, done.stderr)
                self.assertIn(expression, done.stderr)

    def test_the_text_around_the_span_is_kept(self):
        self.assertEqual(self.convert("`1/2`{=}, `1/4`{=}; (`2+2`{=}) and `3+3`{=}s\n").stdout.strip(), "0.5, 0.25; (4) and 6s")
        self.assertEqual(self.convert("**bold `1+1`{=}** and *`2+2`{=}*\n").stdout.strip(), "bold 2 and 4")
        self.assertIn("Heading 2", self.convert("# Heading `1+1`{=}\n").stdout)
        self.assertIn("item 4", self.convert("- item `2*2`{=}\n").stdout)

    def test_code_without_the_marker_and_code_blocks_are_not_touched(self):
        out = self.convert("It is `2+2` and `3+3` {=} here.\n\n```\n`1+1`{=}\n```\n\n    `4+4`{=}\n").stdout
        self.assertIn("2+2", out)
        self.assertIn("3+3", out)
        self.assertIn("`1+1`{=}", out)
        self.assertIn("`4+4`{=}", out)
        self.assertNotIn("WARN", self.convert("`2+2` only\n").stderr)

    def test_a_failed_span_loses_its_marker_and_nothing_else(self):
        out = self.convert("Good `1+1`{=} bad `1/0`{=}, fine `2+2`{=}.\n")
        self.assertEqual(out.stdout.strip(), "Good 2 bad 1/0, fine 4.")

    def test_the_other_writers(self):
        self.assertIn("<p>It is 20.</p>", self.convert("It is `2026 - 2006`{=}.\n", "html").stdout)
        self.assertIn("It is 20.", self.convert("It is `2026 - 2006`{=}.\n", "latex").stdout)
        self.assertIn("It is 20.", self.convert("It is `2026 - 2006`{=}.\n", "typst").stdout)



# (document text, what a plain-text build says, words in the warnings): the {ans} placeholder, stored names, formats
STATEMENTS = (
    ("`2-4`{=}", "-2"),
    ("`2 - 4 = {ans}`{=}", "2 - 4 = -2"),
    ("`2-4={ans}`{=}", "2-4=-2"),
    ("`V = 20.60 - 0.00 = {ans} mL`{=}", "V = 20.60 - 0.00 = 20.6 mL"),
    ("`V = 20.60 - 0.00 = {ans:2dp} mL`{=}", "V = 20.60 - 0.00 = 20.60 mL"),
    ("`A = 4 - 2`{=}Value `A`{=}.", "Value 2."),
    ("`A = 4 - 2 = {ans}`{=}", "A = 4 - 2 = 2"),
    ("`A = B = 4 - 2`{=}`A + B`{=}", "4"),
    ("`RSD = R_C = 3 / 4 * 100% = {ans}%`{=} `R_C`{=}", "RSD = R_C = 3 / 4 * 100% = 75% 75"),
    ("Use `B`{=}. `B = 6 / 4`{=}", "Use 1.5."),                                  # a name may be used before it is given
    ("`A = 1`{=} `A`{=} `A = 2`{=} `A`{=}", "1 2"),                              # the nearest definition above
    ("`A = 1/3 = {ans:4sf}`{=}, `A`{=} and `A + 1`{=}", "A = 1/3 = 0.3333, 0.3333 and 1.333333"),   # a name keeps its format
    ("`A = 1/3`{=3sf}`A`{=} and `1/3`{=2dp}", "0.333 and 0.33"),
    ("`a = 2 + 2 = {ans} and b = 3 + 3 = {ans:2dp}`{=}", "a = 2 + 2 = 4 and b = 3 + 3 = 6.00"),
    ("`Run 1: V = 5 - 1 = {ans:2dp} mL`{=} then `V`{=}", "Run 1: V = 5 - 1 = 4.00 mL then 4.00"),
    ("{ans} stays in `code` and prose", "{ans} stays in code and prose"),
)

FORMATS = (
    ("0.0203862", "4sf", "0.02039"), ("20.6", "4sf", "20.60"), ("0.0000265", "3sf", "0.0000265"), ("1.6e-19", "4sf", "1.600e-19"),
    ("6.022e23", "4sf", "6.022e+23"), ("9.9996", "4sf", "10.00"), ("-0.0004999", "2sf", "-0.00050"), ("0", "3sf", "0.00"),
    ("1049", "3sf", "1049"), ("1049.6", "3sf", "1050"), ("12345.678", "3sf", "12346"), ("2.5", "1sf", "2"), ("3.5", "1sf", "4"),
    ("0.125", "2dp", "0.12"), ("-0.001", "1dp", "0.0"), ("1234.5678", "0dp", "1235"), ("2", "3dp", "2.000"), ("20.6", "2dp", "20.60"),
    ("231.0997", "4sf", "231.1"), ("0.1299657", "2sf", "0.13"),
)

DIV = """\
::: calc
Run 1: V = 20.60 - 0.00 = {ans:2dp} mL.\\
ppm = 0.02039 * 11.66 / 25.00 * 24.305 * 1000 = {ans:4sf} ppm

No placeholder, so V = 3 + 4 stays as it is.

Run 2: V = 41.11 - 20.60 = {ans:2dp} mL, double = V * 2 = {ans:1dp}.
:::

Later: `V`{=} and `ppm`{=}.
"""


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Variables(unittest.TestCase):
    def convert(self, text: str, *meta: str, writer: str = "plain") -> subprocess.CompletedProcess:
        arguments = [PANDOC, "-f", "markdown", "-t", writer, "--wrap=none"]
        for item in meta:
            arguments += ["-M", item]
        return subprocess.run(arguments + ["--lua-filter", str(CALC_LUA)], input=text, capture_output=True, text=True, encoding="utf-8")

    @staticmethod
    def flat(text: str) -> str:
        return " ".join(text.split())

    def test_statements(self):
        for source, expected in STATEMENTS:
            with self.subTest(source=source):
                done = self.convert(source + "\n")
                self.assertEqual(self.flat(done.stdout), expected, done.stderr)
                self.assertEqual(done.stderr, "")

    def test_formats(self):
        for value, fmt, expected in FORMATS:
            with self.subTest(value=value, fmt=fmt):
                done = self.convert(f"`{value}`{{={fmt}}}\n")
                self.assertEqual(self.flat(done.stdout), expected, done.stderr)

    def test_the_default_digits_from_the_option(self):
        self.assertEqual(self.flat(self.convert("`2/3`{=} `1049`{=} `20.6 = {ans}`{=}\n", "pdfmd-calc-digits=4sf").stdout), "0.6667 1049 20.6 = 20.60")
        self.assertEqual(self.flat(self.convert("`2/3`{=} `V = 5 = {ans}`{=}\n", "pdfmd-calc-digits=2dp").stdout), "0.67 V = 5 = 5.00")
        self.assertEqual(self.flat(self.convert("`2/3 = {ans:3sf}`{=}\n", "pdfmd-calc-digits=2dp").stdout), "2/3 = 0.667")      # the span wins

    def test_the_div_calculates_its_lines_without_backticks(self):
        done = self.convert(DIV)
        self.assertEqual(done.stderr, "")
        out = done.stdout
        self.assertIn("Run 1: V = 20.60 - 0.00 = 20.60 mL.", out)
        self.assertIn("ppm = 0.02039 * 11.66 / 25.00 * 24.305 * 1000 = 231.1 ppm", out)
        self.assertIn("No placeholder, so V = 3 + 4 stays as it is.", out)
        self.assertIn("Run 2: V = 41.11 - 20.60 = 20.51 mL, double = V * 2 = 41.0.", out)
        self.assertIn("Later: 20.51 and 231.1.", self.flat(out))                  # V is the nearest definition above, ppm keeps 4sf
        self.assertNotIn(":::", out)

    def test_the_div_spellings(self):
        for fence in ("::: calc", "::: {.calc}", "::::: {.calc}", "::: {#c .calc}"):
            with self.subTest(fence=fence):
                closing = ":::::" if fence.startswith(":::::") else ":::"
                out = self.convert(f"{fence}\nV = 7 - 2 = {{ans}} mL\n{closing}\n", writer="html").stdout
                self.assertIn("V = 7 - 2 = 5 mL", out)
                self.assertIn('id="c"' if "#c" in fence else "<p>", out)
                self.assertNotIn("{ans}", out)
        self.assertIn("{ans}", self.convert("::: note\nV = 7 - 2 = {ans}\n:::\n").stdout)      # only a calc div

    def test_two_placeholders_in_a_line_and_other_blocks_of_the_div(self):
        out = self.convert("::: calc\n- a = 1 + 1 = {ans}, b = a * 3 = {ans}\n\n> c = b / 4 = {ans:2dp}\n:::\n").stdout
        self.assertIn("a = 1 + 1 = 2, b = a * 3 = 6", out)
        self.assertIn("c = b / 4 = 1.50", out)

    def test_what_goes_wrong_is_kept_and_warned_once_each(self):
        for source, kept, reason in (
            ("`x = y + 1 = {ans}`{=}", "x = y + 1 = {ans}", "'y' is not defined"),
            ("`1/0 = {ans}`{=}", "1/0 = {ans}", "division by zero"),
            ("`A = B`{=} `B = A`{=} `A`{=}", "A = B B = A A", "depends on itself"),
            ("`pi = 3`{=}", "pi = 3", "built in"),
            ("`Run 1 = 3`{=}", "Run 1 = 3", "is not a name"),
            ("`2 + 2 = {ans:9xx}`{=}", "2 + 2 = {ans:9xx}", "not a number format"),
            ("`2 + 2 {ans}`{=}", "2 + 2 {ans}", "right after an ="),
            ("`= {ans}`{=}", "= {ans}", "nothing to calculate"),
            ("`2 + 2 = {ans}`{=7zz}", "2 + 2 = {ans}", None),
        ):
            with self.subTest(source=source):
                done = self.convert(source + "\n")
                if reason is None:
                    continue
                self.assertEqual(self.flat(done.stdout), kept, done.stderr)
                self.assertIn("WARN  calc:", done.stderr)
                self.assertIn(reason, done.stderr)

    def test_a_div_line_with_formatting_or_a_bad_expression_is_left_as_written(self):
        out = self.convert("::: calc\nV = **2** + 2 = {ans}\n\nW = 1/0 = {ans}\n:::\n")
        self.assertIn("V = 2 + 2 = {ans}", out.stdout)
        self.assertIn("W = 1/0 = {ans}", out.stdout)
        self.assertIn("holds formatting", out.stderr)
        self.assertIn("division by zero", out.stderr)

    def test_the_other_writers(self):
        html = self.convert("`C = 1/3 = {ans:4sf} M`{=}\n", writer="html").stdout
        self.assertIn("<p>C = 1/3 = 0.3333 M</p>", html)
        latex = self.convert("`C = 1/3 = {ans:4sf} M`{=}\n", writer="latex").stdout
        self.assertIn("C = 1/3 = 0.3333 M", latex)

    # v3.30.8: what real use of a long Calculations section turned up

    def test_a_span_in_a_div_line_sees_the_definition_above_it_not_the_last_one(self):
        source = "::: calc\na = 1 + 1 = {ans:1dp}, so `a * 10`{=0dp}\na = 3 + 3 = {ans:1dp}, so `a * 10`{=0dp}\n:::\n"
        done = self.convert(source)
        self.assertEqual(self.flat(done.stdout), "a = 1 + 1 = 2.0, so 20 a = 3 + 3 = 6.0, so 60", done.stderr)
        self.assertEqual(done.stderr, "")
        paragraphs = self.convert("::: calc\na = 1 + 1 = {ans:1dp}, so `a * 10`{=}\n\na = 3 + 3 = {ans:1dp}, so `a * 10`{=}\n:::\n")
        self.assertEqual(self.flat(paragraphs.stdout), "a = 1 + 1 = 2.0, so 20 a = 3 + 3 = 6.0, so 60")
        defined_only_in_the_div = self.convert("::: calc\nn1 = 2.4 + 0 = {ans:1dp}\nn2 = n1 * 2 = {ans:1dp}, `round(n2)`{=}\n:::\n")
        self.assertEqual(self.flat(defined_only_in_the_div.stdout), "n1 = 2.4 + 0 = 2.4 n2 = n1 * 2 = 4.8, 5")
        self.assertEqual(defined_only_in_the_div.stderr, "")

    def test_what_follows_the_last_ans_of_a_div_line_is_copied_as_it_is(self):
        for tail, latex in (("ppm \\ce{Ca^2+}", "ppm \\ce{Ca^2+}"), ("ppm Ca^2+^", "ppm Ca\\textsuperscript{2+}"),
                            ("ppm **Ca**", "ppm \\textbf{Ca}"), ("ppm $x^2$", "ppm \\(x^2\\)"),
                            ("ppm [link](http://x.y)", "ppm \\href{http://x.y}{link}")):
            with self.subTest(tail=tail):
                done = self.convert(f"::: calc\ny = 2 + 2 = {{ans:1dp}} {tail}\n:::\n", writer="latex")
                self.assertIn("y = 2 + 2 = 4.0 " + latex, done.stdout, done.stderr)
                self.assertEqual(done.stderr, "")
        before = self.convert("::: calc\ny = **2** + 2 = {ans:1dp} ppm\n:::\n")
        self.assertIn("{ans:1dp}", before.stdout)                                   # formatting BEFORE the {ans} is still refused
        self.assertIn("holds formatting", before.stderr)

    def test_several_ans_in_one_text(self):
        for source, expected in (
            ("n = 9.7 * 9.7 / 1.0 = {ans:1dp}, so {ans:0dp}", "n = 9.7 * 9.7 / 1.0 = 94.1, so 94"),
            ("n = 9.7 * 9.7 = {ans:1dp}, so round(n) = {ans:0dp}, so n / 2 = {ans:3dp}", "n = 9.7 * 9.7 = 94.1, so round(n) = 94, so n / 2 = 47.045"),
            ("m = 2.5 * 7 = {ans:2dp}, then m2 = m / 2 = {ans:1dp}", "m = 2.5 * 7 = 17.50, then m2 = m / 2 = 8.8"),
            ("x = 3 * 3 = {ans}; {ans:2dp} {ans:0dp}", "x = 3 * 3 = 9; 9.00 9"),
        ):
            with self.subTest(source=source):
                done = self.convert(f"::: calc\n{source}\n:::\n")
                self.assertEqual(self.flat(done.stdout), expected, done.stderr)
                self.assertEqual(done.stderr, "")
        stored = self.convert("::: calc\nn = 9.7 * 9.7 = {ans:1dp}, so k = round(n) = {ans:0dp}\n\nk2 = k * 2 = {ans}\n:::\n")
        self.assertIn("k2 = k * 2 = 188", stored.stdout)                              # the second expression's name is stored
        self.assertIn("{ans} has to come right after an =", self.convert("`2 + 2 {ans}`{=}\n").stderr)

    def test_the_left_arrow_assigns(self):
        done = self.convert("`t18 <- 2.10092204`{=} `t18`{=4sf} ppm1 and\n\n::: calc\nppm1 <- t18 * 10 = {ans:2dp}\n\nk = ppm1 / 2 = {ans:1dp}\n:::\n")
        self.assertEqual(done.stderr, "")
        self.assertEqual(self.flat(done.stdout), "2.101 ppm1 and ppm1 <- t18 * 10 = 21.01 k = ppm1 / 2 = 10.5")
        self.assertEqual(self.flat(self.convert("`a <- b <- 4`{=} `a + b`{=}\n").stdout), "8")
        self.assertEqual(self.flat(self.convert("`x<-2`{=}`x`{=}\n").stdout), "2")

    def test_subs_puts_the_values_into_the_expression(self):
        source = ("`C_dil <- 0.002039`{=} `V <- 34.41`{=2dp} `neg <- -0.5`{=}\n\n::: calc\n"
                  "ppm1 = C_dil * V / 100.0 * 40.078 * 1000 = {subs} = {ans:2dp} ppm\n\n"
                  "xbar = (ppm1 + V) / 3 = {subs} = {ans:2dp}\n\n"
                  "sq = neg^2 + neg * 2 = {subs} = {ans}\n\n"
                  "f = sqrt(V) + pi - neg = {subs} = {ans:3dp}\n:::\n")
        done = self.convert(source, "pdfmd-calc-digits=4sf")
        self.assertEqual(done.stderr, "")
        out = done.stdout
        self.assertIn("ppm1 = C_dil * V / 100.0 * 40.078 * 1000 = 0.002039 * 34.41 / 100.0 * 40.078 * 1000 = 28.12 ppm", out)
        self.assertIn("xbar = (ppm1 + V) / 3 = (28.12 + 34.41) / 3 = 20.84", out)           # each name in the digits it was defined with
        self.assertIn("sq = neg^2 + neg * 2 = (-0.5000)^2 + (-0.5000) * 2 = -0.7500", out)     # a negative value gets parentheses
        self.assertIn("f = sqrt(V) + pi - neg = sqrt(34.41) + pi - (-0.5000) = 9.508", out)   # functions and constants stay

    def test_subs_computes_with_the_full_value(self):
        done = self.convert("`a <- 1/3`{=3sf}\n\n::: calc\nb = a * 3 = {subs} = {ans:3sf}\n:::\n")
        self.assertIn("b = a * 3 = 0.333 * 3 = 1.00", done.stdout)                           # 0.333 * 3 is 0.999: the result is 1.00

    def test_the_switch_puts_subs_before_every_ans_that_has_names(self):
        source = ("`C <- 0.5`{=} `V <- 20`{=}\n\n::: calc\nx = C * V = {ans}\n\nx2 = 2 * 3 = {ans}\n\ny = C = {ans:3dp}\n\n"
                  "z = C * V = {ans} {nosubs}\n\nw = C * V = {ans:2dp}, so {ans:0dp}\n:::\n\n"
                  "Span: `q = C * V / 4 = {ans:2dp}`{=}.\n")
        off = self.convert(source).stdout
        self.assertIn("x = C * V = 10", off)
        on = self.convert(source, "pdfmd-calc-subs=true")
        self.assertEqual(on.stderr, "")
        self.assertIn("x = C * V = 0.5 * 20 = 10", on.stdout)
        self.assertIn("x2 = 2 * 3 = 6", on.stdout)                                           # nothing to put in: no second copy
        self.assertIn("y = C = 0.500", on.stdout)                                            # a lone name: it would only repeat the value
        self.assertIn("z = C * V = 10", on.stdout)                                           # {nosubs}
        self.assertNotIn("nosubs", on.stdout)
        self.assertIn("w = C * V = 0.5 * 20 = 10.00, so 10", on.stdout)                      # a repeat has no expression of its own
        self.assertIn("Span: q = C * V / 4 = 0.5 * 20 / 4 = 2.50.", on.stdout)
        forced = self.convert("`C <- 0.5`{=}\n\n::: calc\nx = 2 * 3 = {subs} = {ans}\n\ny = C * 2 = {subs} = {ans} {subs:off}\n:::\n")
        self.assertIn("x = 2 * 3 = 2 * 3 = 6", forced.stdout)                                # {subs} forces the copy
        self.assertIn("y = C * 2 = 0.5 * 2 = 1", forced.stdout)

    def test_a_misplaced_subs_is_kept_with_one_warning(self):
        done = self.convert("`x = 2 * 3 = {subs}`{=}\n")
        self.assertIn("{subs} has to stand in front of an {ans}", done.stderr)
        self.assertEqual(self.flat(done.stdout), "x = 2 * 3 = {subs}")

    def test_a_raw_span_of_another_format_is_left_alone(self):
        out = self.convert("`<b>x</b>`{=html} and `\\textbf{y}`{=latex}\n", writer="html").stdout
        self.assertIn("<b>x</b>", out)

@unittest.skipUnless(PANDOC, "needs Pandoc")
class Switches(unittest.TestCase):
    """--calc / --no-calc, --calc-round, the options that say the same, and which wins."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calc-switch-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def html(self, header: str, *arguments: str, env: dict | None = None) -> str:
        (self.directory / "doc.md").write_text(f"{header}Half: `round(5/2)`{{=}}, sum: `1+2`{{=}}.\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", "html", "--no-backup", *arguments],
                              cwd=self.directory, capture_output=True, text=True, encoding="utf-8", env={**os.environ, **(env or {})})
        self.assertTrue((self.directory / "doc.html").exists(), done.stdout + done.stderr)
        return (self.directory / "doc.html").read_text(encoding="utf-8")

    def test_on_by_default_and_the_half_goes_to_even(self):
        self.assertIn("Half: 2, sum: 3.", self.html(""))

    def test_no_calc_leaves_the_span(self):
        out = self.html("", "--no-calc")
        self.assertIn("5/2", out)
        self.assertNotIn("Half: 2", out)

    def test_the_flag_beats_the_document(self):
        off = "---\npdfmd-options:\n  calc: off\n---\n\n"
        self.assertIn("5/2", self.html(off))
        self.assertIn("Half: 2, sum: 3.", self.html(off, "--calc"))
        self.assertIn("5/2", self.html("---\npdfmd-options:\n  calc: on\n---\n\n", "--no-calc"))

    def test_the_variable_reaches_a_worker(self):
        self.assertIn("5/2", self.html("", env={"PDFMD_CALC": "off"}))

    def test_calc_round_in_the_options_the_flag_and_the_variable(self):
        away = "---\npdfmd-options:\n  calc:\n    round: away\n---\n\n"
        self.assertIn("Half: 3, sum: 3.", self.html(away))
        self.assertIn("Half: 2, sum: 3.", self.html(away, "--calc-round", "even"))
        self.assertIn("Half: 3, sum: 3.", self.html("", "--calc-round", "away"))
        self.assertIn("Half: 3, sum: 3.", self.html("", env={"PDFMD_CALC_ROUND": "away"}))

    def test_calc_digits_in_the_options_the_flag_and_the_variable(self):
        def body(header, *arguments, env=None):
            (self.directory / "doc.md").write_text(f"{header}Third: `1/3`{{=}}, volume: `V = 5 - 1 = {{ans}} mL`{{=}}.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", "html", "--no-backup", *arguments],
                                  cwd=self.directory, capture_output=True, text=True, encoding="utf-8", env={**os.environ, **(env or {})})
            self.assertTrue((self.directory / "doc.html").exists(), done.stdout + done.stderr)
            return (self.directory / "doc.html").read_text(encoding="utf-8")
        self.assertIn("Third: 0.3333333, volume: V = 5 - 1 = 4 mL.", body(""))
        four = "---\npdfmd-options:\n  calc:\n    digits: 4sf\n---\n\n"
        self.assertIn("Third: 0.3333, volume: V = 5 - 1 = 4.000 mL.", body(four))
        self.assertIn("Third: 0.33, volume: V = 5 - 1 = 4.00 mL.", body(four, "--calc-digits", "2dp"))
        self.assertIn("Third: 0.3333333, volume: V = 5 - 1 = 4 mL.", body(four, env={"PDFMD_CALC_DIGITS": "none"}))
        self.assertIn("Third: 0.333, volume: V = 5 - 1 = 4.00 mL.", body("", env={"PDFMD_CALC_DIGITS": "3sf"}))

    def test_calc_subs_in_the_options_the_flag_and_the_variable(self):
        def body(header, *arguments, env=None):
            (self.directory / "doc.md").write_text(header + "`C <- 0.5`{=} `V <- 20`{=}\n\n`x = C * V = {ans}`{=}\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", "html", "--no-backup", *arguments],
                                  cwd=self.directory, capture_output=True, text=True, encoding="utf-8", env={**os.environ, **(env or {})})
            self.assertTrue((self.directory / "doc.html").exists(), done.stdout + done.stderr)
            return (self.directory / "doc.html").read_text(encoding="utf-8")
        self.assertIn("x = C * V = 10", body(""))
        on = "---\npdfmd-options:\n  calc:\n    subs: true\n---\n\n"
        self.assertIn("x = C * V = 0.5 * 20 = 10", body(on))
        self.assertIn("x = C * V = 10", body(on, "--no-calc-subs"))
        self.assertIn("x = C * V = 0.5 * 20 = 10", body("", "--calc-subs"))
        self.assertIn("x = C * V = 0.5 * 20 = 10", body("", env={"PDFMD_CALC_SUBS": "true"}))

    def test_a_calc_div_has_no_indent_unless_asked_otherwise(self):
        source = "::: calc\nx = 2 * 3 = {ans}\n:::\n\n::: {.calc indent=2em}\ny = 2 * 4 = {ans}\n:::\n\n::: {.calc .indent}\nz = 2 * 5 = {ans}\n:::\n"

        def latex(*arguments, header="---\nindent: true\n---\n\n", env=None):
            (self.directory / "doc.md").write_text(header + source, encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", "latex", "--no-backup", *arguments],
                                  cwd=self.directory, capture_output=True, text=True, encoding="utf-8", env={**os.environ, **(env or {})})
            self.assertTrue((self.directory / "doc.tex").exists(), done.stdout + done.stderr)
            return (self.directory / "doc.tex").read_text(encoding="utf-8")
        on = latex()
        self.assertIn("\\begingroup\\setlength{\\parindent}{0pt}\n\nx = 2 * 3 = 6", on)       # the default
        self.assertIn("\\setlength{\\parindent}{2em}\n\ny = 2 * 4 = 8", on)                    # an indent= on the div wins
        self.assertIn("\\setlength{\\parindent}{1.5em}\n\nz = 2 * 5 = 10", on)                 # so does .indent
        self.assertEqual(on.count("\\endgroup"), 3)
        off = "---\npdfmd-options:\n  calc:\n    noindent: false\n---\n\n"
        self.assertEqual(latex(header=off).count("\\begingroup"), 2)                                # only the two explicit ones
        self.assertEqual(latex("--no-calc-noindent").count("\\begingroup"), 2)
        self.assertEqual(latex("--calc-noindent", header=off).count("\\begingroup"), 3)
        self.assertEqual(latex(env={"PDFMD_CALC_NOINDENT": "false"}).count("\\begingroup"), 2)
        self.assertEqual(latex("--no-calc").count("\\begingroup"), 2)                                               # no calculator: the explicit divs only

    def test_a_calc_div_has_room_around_it_and_can_be_centred(self):
        source = "---\ntitle: T\n---\n\nBefore.\n\n::: calc\nx = 2 * 3 = {ans}\n:::\n\nAfter.\n"

        def convert(target, *arguments, env=None, header=""):
            (self.directory / "doc.md").write_text(source.replace("---\ntitle: T\n", "---\ntitle: T\n" + header, 1), encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", target, "--no-backup", "-o", "out." + target,
                                   *arguments], cwd=self.directory, capture_output=True, text=True, encoding="utf-8",
                                  env={**os.environ, **(env or {})})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            return (self.directory / ("out." + target)).read_text(encoding="utf-8")
        latex = convert("latex")
        self.assertEqual(latex.count("\\par\\addvspace{0.75em}"), 2)                      # the default: above and below
        self.assertLess(latex.find("Before."), latex.find("\\addvspace"))
        self.assertLess(latex.find("x = 2 * 3 = 6"), latex.rfind("\\addvspace"))
        self.assertLess(latex.rfind("\\addvspace"), latex.find("After."))
        self.assertNotIn("\\centering", latex)                                              # left unless asked
        centred = convert("latex", "--calc-align", "center", "--calc-space", "6pt")
        self.assertEqual(centred.count("\\par\\addvspace{6pt}"), 2)
        self.assertLess(centred.find("\\begingroup\\centering"), centred.find("x = 2 * 3 = 6"))
        self.assertLess(centred.find("x = 2 * 3 = 6"), centred.find("\\par\\endgroup"))
        self.assertNotIn("addvspace", convert("latex", "--calc-space", "off"))
        self.assertNotIn("addvspace", convert("latex", header="pdfmd-options:\n  calc:\n    space: 0\n"))
        self.assertIn("addvspace{2mm}", convert("latex", header="pdfmd-options:\n  calc:\n    space: 2mm\n    align: center\n"))
        self.assertIn("\\centering", convert("latex", env={"PDFMD_CALC_ALIGN": "center"}))
        typst = convert("typst", "--calc-align", "center")
        self.assertEqual(typst.count("#v(0.75em, weak: true)"), 2)
        self.assertLess(typst.find("#align(center)["), typst.find("x = 2"))
        html = convert("html", "--calc-align", "center")
        self.assertIn('style="padding-top: 0.75em; padding-bottom: 0.75em; text-align: center;"', html)
        self.assertNotIn("padding", convert("html", "--calc-space", "off"))

    def test_a_bad_space_or_align_is_an_error_and_the_other_writers_get_nothing(self):
        (self.directory / "doc.md").write_text("---\ntitle: T\n---\n\n::: calc\nx = 2 * 3 = {ans}\n:::\n", encoding="utf-8")
        for arguments in (("--calc-space", "big"), ("--calc-space", "3"), ("--calc-space", "2furlongs")):
            with self.subTest(arguments=arguments):
                done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", "latex", "--no-backup", *arguments],
                                      cwd=self.directory, capture_output=True, text=True, encoding="utf-8")
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("calc.space must be a length", done.stdout + done.stderr)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", "gfm", "--no-backup", "-o", "out.md"],
                              cwd=self.directory, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (self.directory / "out.md").read_text(encoding="utf-8")
        self.assertNotIn("addvspace", text)
        self.assertNotIn("padding", text)

    def test_the_other_writers_get_no_indent_attribute_and_no_note(self):
        (self.directory / "doc.md").write_text("---\ntitle: T\n---\n\n::: calc\nx = 2 * 3 = {ans}\n:::\n", encoding="utf-8")
        for target, suffix in (("gfm", "md"), ("docx", "docx"), ("html", "html")):
            with self.subTest(target=target):
                done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", target, "--no-backup", "-o", f"out.{suffix}"],
                                      cwd=self.directory, capture_output=True, text=True, encoding="utf-8")
                self.assertTrue((self.directory / f"out.{suffix}").exists(), done.stdout + done.stderr)
                self.assertNotIn("indent", done.stdout + done.stderr)
                if suffix == "md":
                    self.assertEqual((self.directory / "out.md").read_text(encoding="utf-8").split("\n\n", 1)[1].strip(), "x = 2 \\* 3 = 6")
                if suffix == "html":
                    self.assertIn("text-indent: 0pt", (self.directory / "out.html").read_text(encoding="utf-8"))

    def test_a_wrong_calc_digits_is_refused(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--calc-digits", "four", "doc.md"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("4sf", done.stderr)
        (self.directory / "bad.md").write_text("---\npdfmd-options:\n  calc:\n    digits: lots\n---\n\n`1+1`{=}\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "bad.md", "--to", "html", "--no-backup"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("calc.digits must be like 4sf", done.stdout + done.stderr)

    def test_a_wrong_calc_round_is_refused(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--calc-round", "up", "doc.md"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("even", done.stderr)
        (self.directory / "bad.md").write_text("---\npdfmd-options:\n  calc:\n    round: up\n---\n\n`1+1`{=}\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "bad.md", "--to", "html", "--no-backup"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("calc.round must be even or away", done.stdout + done.stderr)


def words(pdf: Path) -> str:
    return " ".join(subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout.split())


# Reference values: qt(0.975, df) from R 4.6.1 (the first block, as printed to 12 figures), the rest from SciPy.
R_QT = (("1", "12.7062047362"), ("2", "4.30265272975"), ("3", "3.18244630528"), ("6", "2.44691185114"), ("8", "2.3060041352"),
        ("9", "2.2621571628"), ("10", "2.22813885199"), ("13", "2.16036865646"), ("16", "2.11990529922"),
        ("18", "2.10092204024"), ("93", "1.98580181435"), ("96", "1.98498431152"), ("13.947016149", "2.14555134732"),
        ("Inf", "1.95996398454"))
DISTRIBUTION_ROWS = (
    ("qnorm", "0.001", "-3.09023230617"),
    ("qnorm", "0.025", "-1.95996398454"),
    ("qnorm", "0.05", "-1.64485362695"),
    ("qnorm", "0.3", "-0.524400512708"),
    ("qnorm", "0.5", "0"),
    ("qnorm", "0.9", "1.28155156554"),
    ("qnorm", "0.975", "1.95996398454"),
    ("qnorm", "0.995", "2.57582930355"),
    ("qnorm", "0.999999", "4.75342430882"),
    ("pnorm", "-8", "6.22096057427e-16"),
    ("pnorm", "-3", "0.00134989803163"),
    ("pnorm", "-1.96", "0.0249978951482"),
    ("pnorm", "-0.5", "0.308537538726"),
    ("pnorm", "0", "0.5"),
    ("pnorm", "0.5", "0.691462461274"),
    ("pnorm", "1", "0.841344746069"),
    ("pnorm", "1.96", "0.975002104852"),
    ("pnorm", "3", "0.998650101968"),
    ("pnorm", "6", "0.999999999013"),
    ("qt", "0.025, 0.5", "-164.55767348"),
    ("qt", "0.2, 0.5", "-2.51271795367"),
    ("qt", "0.975, 0.5", "164.55767348"),
    ("qt", "0.025, 1", "-12.7062047362"),
    ("qt", "0.2, 1", "-1.37638192047"),
    ("qt", "0.975, 1", "12.7062047362"),
    ("qt", "0.025, 2", "-4.30265272975"),
    ("qt", "0.2, 2", "-1.06066017178"),
    ("qt", "0.975, 2", "4.30265272975"),
    ("qt", "0.025, 2.5", "-3.574654842"),
    ("qt", "0.2, 2.5", "-1.01016387472"),
    ("qt", "0.975, 2.5", "3.574654842"),
    ("qt", "0.025, 3", "-3.18244630528"),
    ("qt", "0.2, 3", "-0.978472312363"),
    ("qt", "0.975, 3", "3.18244630528"),
    ("qt", "0.025, 4", "-2.7764451052"),
    ("qt", "0.2, 4", "-0.940964577235"),
    ("qt", "0.975, 4", "2.7764451052"),
    ("qt", "0.025, 5", "-2.57058183564"),
    ("qt", "0.2, 5", "-0.919543780241"),
    ("qt", "0.975, 5", "2.57058183564"),
    ("qt", "0.025, 7", "-2.36462425159"),
    ("qt", "0.2, 7", "-0.896029644314"),
    ("qt", "0.975, 7", "2.36462425159"),
    ("qt", "0.025, 13", "-2.16036865646"),
    ("qt", "0.2, 13", "-0.870151533968"),
    ("qt", "0.975, 13", "2.16036865646"),
    ("qt", "0.025, 30", "-2.0422724563"),
    ("qt", "0.2, 30", "-0.853767261471"),
    ("qt", "0.975, 30", "2.0422724563"),
    ("qt", "0.025, 93", "-1.98580181435"),
    ("qt", "0.2, 93", "-0.845503281805"),
    ("qt", "0.975, 93", "1.98580181435"),
    ("qt", "0.025, 500", "-1.96471983747"),
    ("qt", "0.2, 500", "-0.842340706154"),
    ("qt", "0.975, 500", "1.96471983747"),
    ("qt", "0.025, 1000", "-1.96233908083"),
    ("qt", "0.2, 1000", "-0.841980822162"),
    ("qt", "0.975, 1000", "1.96233908083"),
    ("qt", "0.025, 1001", "-1.96233670528"),
    ("qt", "0.2, 1001", "-0.841980462786"),
    ("qt", "0.975, 1001", "1.96233670528"),
    ("qt", "0.025, 5000", "-1.96043855171"),
    ("qt", "0.2, 5000", "-0.841693127664"),
    ("qt", "0.975, 5000", "1.96043855171"),
    ("qt", "0.025, 1e+06", "-1.95996635681"),
    ("qt", "0.2, 1e+06", "-0.841621593014"),
    ("qt", "0.975, 1e+06", "1.95996635681"),
    ("qt", "0.025, 1e+08", "-1.95996400826"),
    ("qt", "0.2, 1e+08", "-0.841621237167"),
    ("qt", "0.975, 1e+08", "1.95996400826"),
    ("pt", "-3, 1", "0.10241638235"),
    ("pt", "-0.5, 1", "0.35241638235"),
    ("pt", "0.7, 1", "0.694400112214"),
    ("pt", "2.101, 1", "0.858595786365"),
    ("pt", "6, 1", "0.947431543289"),
    ("pt", "-3, 2.5", "0.0362880477745"),
    ("pt", "-0.5, 2.5", "0.328848959935"),
    ("pt", "0.7, 2.5", "0.728297528405"),
    ("pt", "2.101, 2.5", "0.927809809471"),
    ("pt", "6, 2.5", "0.992359135057"),
    ("pt", "-3, 8", "0.00853584061689"),
    ("pt", "-0.5, 8", "0.315268037778"),
    ("pt", "0.7, 8", "0.748114473991"),
    ("pt", "2.101, 8", "0.96558481435"),
    ("pt", "6, 8", "0.999838303389"),
    ("pt", "-3, 18", "0.00384270607016"),
    ("pt", "-0.5, 18", "0.311566228648"),
    ("pt", "0.7, 18", "0.753561964569"),
    ("pt", "2.101, 18", "0.975003818561"),
    ("pt", "6, 18", "0.999994365014"),
    ("pt", "-3, 100", "0.00170395767166"),
    ("pt", "-0.5, 100", "0.309086782915"),
    ("pt", "0.7, 100", "0.757223696773"),
    ("pt", "2.101, 100", "0.980922340486"),
    ("pt", "6, 100", "0.999999984138"),
    ("pt", "-3, 1000", "0.00138335452212"),
    ("pt", "-0.5, 1000", "0.308592540417"),
    ("pt", "0.7, 1000", "0.757954943004"),
    ("pt", "2.101, 1000", "0.982054605912"),
    ("pt", "6, 1000", "0.999999998622"),
    ("pt", "-3, 100000", "0.00135023044203"),
    ("pt", "-0.5, 100000", "0.308538088827"),
    ("pt", "0.7, 100000", "0.758035533576"),
    ("pt", "2.101, 100000", "0.982178268681"),
    ("pt", "6, 100000", "0.99999999901"),
)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Distributions(unittest.TestCase):
    """qnorm, pnorm, qt and pt (3.30.10): no library, checked against R and SciPy."""

    def values(self, expressions: list[str]) -> list[float]:
        text = " | ".join(f"`{expression}`{{=12sf}}" for expression in expressions)
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "plain", "--wrap=none", "--lua-filter", str(CALC_LUA)], input=text,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.stderr, "")
        return [float(part) for part in done.stdout.split("|")]

    def test_qt_against_r(self):
        got = self.values([f"qt(0.975, {df})" for df, _ in R_QT])
        for (df, want), value in zip(R_QT, got):
            with self.subTest(df=df):
                self.assertAlmostEqual(value / float(want), 1.0, delta=2e-11)

    def test_the_reference_table(self):
        got = self.values([f"{name}({arguments})" for name, arguments, _ in DISTRIBUTION_ROWS])
        for (name, arguments, want), value in zip(DISTRIBUTION_ROWS, got):
            with self.subTest(call=f"{name}({arguments})"):
                reference = float(want)
                loose = name == "pt" and float(arguments.split(",")[1]) > 1e4
                self.assertLessEqual(abs(value - reference), (2e-9 if loose else 3e-11) * max(abs(reference), 1e-12))

    def test_inf_and_the_symmetry(self):
        a, b, c, d = self.values(["qt(0.975, Inf)", "qnorm(0.975)", "qt(0.025, 18) + qt(0.975, 18)", "pt(0, 5)"])
        self.assertEqual(a, b)
        self.assertLess(abs(c), 1e-12)
        self.assertEqual(d, 0.5)

    def test_a_degree_of_freedom_from_a_name_and_a_table_value(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "plain", "--wrap=none", "--lua-filter", str(CALC_LUA)],
                              input="`df_w = 13.947016149`{=} t = `qt(0.975, df_w) = {ans:4sf}`{=}, `qt(0.975, 18)`{=4sf}\n",
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.stderr, "")
        self.assertIn("t = qt(0.975, df_w) = 2.146, 2.101", done.stdout)

    def test_a_value_outside_the_domain_keeps_the_text_and_warns_once(self):
        for expression, reason in (("qt(1.5, 3)", "probability between 0 and 1"), ("qt(0, 3)", "probability between 0 and 1"),
                                   ("qt(0.9, 0)", "degrees of freedom above 0"), ("qnorm(1)", "probability between 0 and 1"),
                                   ("pt(1, -2)", "degrees of freedom above 0"), ("qt(0.9)", "qt takes 2 arguments")):
            with self.subTest(expression=expression):
                done = subprocess.run([PANDOC, "-f", "markdown", "-t", "plain", "--lua-filter", str(CALC_LUA)],
                                      input=f"`{expression}`{{=}}\n", capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(done.stderr.count("WARN"), 1, done.stderr)
                self.assertIn(reason, done.stderr)
                self.assertIn(expression, done.stdout)

    def test_the_new_names_are_built_in(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "plain", "--lua-filter", str(CALC_LUA)], input="`pt = 3`{=}\n",
                              capture_output=True, text=True, encoding="utf-8")
        self.assertIn("'pt' is built in", done.stderr)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Blocks(unittest.TestCase):
    """Statement blocks (3.30.11): ```{=calc}, ```{=} (read again from the source), `::: {.calc .hide}`, `code`{=calc}, the constants file."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calc-blocks-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def convert(self, text: str, *meta: str, name: str | None = "doc.md") -> subprocess.CompletedProcess:
        arguments = [PANDOC, "-f", "markdown", "-t", "plain", "--wrap=none", "--lua-filter", str(CALC_LUA)]
        for item in meta:
            arguments += ["-M", item]
        if name is None:
            return subprocess.run(arguments, input=text, capture_output=True, text=True, encoding="utf-8")
        (self.directory / name).write_text(text, encoding="utf-8")
        return subprocess.run(arguments + [name], cwd=self.directory, capture_output=True, text=True, encoding="utf-8")

    def test_the_calc_raw_block_stores_silently_and_prints_the_lines_with_an_ans(self):
        done = self.convert("```{=calc}\n# the constants\nt1 = 12.7\n\nt2 <- 4.3\nk = t1 * 2 = {ans:3sf}\n```\n\nSo `t1 + t2`{=}.\n")
        self.assertEqual(done.stderr, "")
        self.assertEqual(done.stdout.split(), "k = t1 * 2 = 25.4 So 17.".split())

    def test_a_fence_with_an_empty_format_is_the_same_block(self):
        done = self.convert("```{=}\nt1 = 12.7\nt2 = 4.3\nk = t1 * 2 = {ans:3sf}\n```\n\nSo `t1 + t2`{=}.\n")
        self.assertEqual(done.stderr, "")
        self.assertEqual(done.stdout.split(), "k = t1 * 2 = 25.4 So 17.".split())

    def test_several_empty_format_fences_and_one_shown_in_a_longer_fence(self):
        text = ("````\n```{=}\nnot = 1\n```\n````\n\n```{=}\na = 2\n```\n\ntext\n\n```{=}\nb = a * 3\n```\n\n`a`{=}, `b`{=}\n")
        done = self.convert(text)
        self.assertEqual(done.stderr, "")
        self.assertIn("2, 6", done.stdout)
        self.assertIn("not = 1", done.stdout)                                    # the documented fence stays as shown

    def test_an_empty_format_fence_from_standard_input_warns_and_stays(self):
        done = self.convert("```{=}\na = 2\n```\n", name=None)
        self.assertIn("write ```{=calc}", done.stderr)
        self.assertIn("a = 2", done.stdout)

    def test_the_inline_raw_spelling(self):
        done = self.convert("`a = 2`{=calc}`a * 3`{=calc} and `a * 4`{=calc}.\n")
        self.assertEqual(done.stderr, "")
        self.assertEqual(done.stdout.strip(), "6 and 8.")

    def test_a_hidden_div_defines_and_prints_nothing(self):
        text = ("Before.\n\n::: {.calc .hide}\nc1 = 10\nc2 <- c1 / 4\n\n# note\nc3 = c2 * 2 = {ans}\n:::\n\n"
                "After: `c1`{=}, `c2`{=}, `c3`{=}.\n")
        done = self.convert(text)
        self.assertEqual(done.stderr, "")
        self.assertEqual(done.stdout.split(), "Before. After: 10, 2.5, 5.".split())
        self.assertEqual(self.convert(text.replace(".calc .hide", ".calc .hidden")).stdout, done.stdout)

    def test_a_failing_line_warns_and_the_rest_goes_on(self):
        done = self.convert("```{=calc}\nbad = 1 / 0\ngood = 2 + 2\n```\n\n`good`{=}\n")
        self.assertEqual(done.stderr.count("WARN"), 1)
        self.assertIn("bad = 1 / 0", done.stdout)
        self.assertIn("4", done.stdout)
        hidden = self.convert("::: {.calc .hide}\nbad = 1 / 0\ngood = 2 + 2\n:::\n\n`good`{=}\n")
        self.assertEqual(hidden.stderr.count("WARN"), 1)
        self.assertEqual(hidden.stdout.strip(), "4")

    def test_fourteen_constants_in_one_block(self):
        lines = "\n".join(f"t{n} = {n}.5" for n in range(1, 15))
        done = self.convert(f"```{{=calc}}\n{lines}\n```\n\n`t14`{{=4sf}} and `t1 + t2`{{=}}\n")
        self.assertEqual(done.stderr, "")
        self.assertEqual(done.stdout.strip(), "14.50 and 4")

    def test_a_hash_starts_a_comment_at_the_end_of_a_line_too(self):
        done = self.convert("```{=calc}\n# a whole line\nM_Mg <- 24.305 # g/mol\nn = 2   #   moles #  more\n   # indented\n```\n\n`M_Mg * n`{=4sf}\n")
        self.assertEqual(done.stderr, "")
        self.assertEqual(done.stdout.strip(), "48.61")

    def test_constants_from_a_metadata_string(self):
        done = self.convert("`t18`{=4sf}, `x = t18 * 2 = {ans:3sf}`{=}\n", "pdfmd-calc-constants=t18 = 2.100922\nunused = 1")
        self.assertEqual(done.stderr, "")
        self.assertEqual(done.stdout.strip(), "2.101, x = t18 * 2 = 4.20")

    def test_detection(self):
        for text in ("```{=calc}\nx = 1\n```", "~~~{=}\nx = 1\n~~~", "  ````{=}\n", "`x = 1`{=calc}", "::: {.calc .hide}\n"):
            with self.subTest(text=text):
                self.assertTrue(pdfmd.CALC_SPAN_RE.search(text))
        for text in ("```{=latex}\nx\n```", "```{.calc}\nx = 1\n```", "```{=html}\n"):
            with self.subTest(text=text):
                self.assertFalse(pdfmd.CALC_SPAN_RE.search(text))

    def build(self, name: str, *arguments: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, "--to", "gfm", "--no-backup", "-o", "out.md", *arguments],
                              cwd=self.directory, capture_output=True, text=True, encoding="utf-8", env={**os.environ, **(env or {})})

    def test_the_constants_file_in_the_options_the_flag_and_the_variable(self):
        (self.directory / "k.csv").write_text("name,value,digits,note\nt18,2.100922,4sf,\"R qt(0.975, 18)\"\n# a comment\nstock,0.1\n",
                                              encoding="utf-8")
        body = "`x = t18 * stock = {ans}`{=}, `t18`{=}, `t18`{=2dp}\n"
        (self.directory / "a.md").write_text("---\npdfmd-options:\n  calc:\n    constants: k.csv\n---\n\n" + body, encoding="utf-8")
        (self.directory / "b.md").write_text("---\ntitle: B\n---\n\n" + body, encoding="utf-8")
        done = self.build("a.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("x = t18 \\* stock = 0.2100922, 2.101, 2.10", (self.directory / "out.md").read_text(encoding="utf-8"))
        for arguments, env in ((("--calc-constants", "k.csv"), None), ((), {"PDFMD_CALC_CONSTANTS": "k.csv"})):
            with self.subTest(arguments=arguments, env=env):
                self.assertEqual(self.build("b.md", *arguments, env=env).returncode, 0)
                self.assertIn("2.101, 2.10", (self.directory / "out.md").read_text(encoding="utf-8"))

    def test_a_semicolon_file_and_the_errors(self):
        (self.directory / "s.csv").write_text("name;value\nk;1,5\n", encoding="utf-8")
        statements = pdfmd.calc_constants_statements(self.directory / "s.csv")
        self.assertEqual(statements, ["k = 1,5"])
        (self.directory / "bad.csv").write_text("name,value,digits\nk,2,lots\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            pdfmd.calc_constants_statements(self.directory / "bad.csv")
        self.assertIn("4sf", str(caught.exception))
        (self.directory / "x.md").write_text("---\ntitle: X\n---\n\n`1+1`{=}\n", encoding="utf-8")
        done = self.build("x.md", "--calc-constants", "missing.csv")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("no file 'missing.csv'", done.stdout + done.stderr)

    def test_the_constants_file_named_in_a_metadata_file_travels_with_the_source(self):
        (self.directory / "tables").mkdir()
        (self.directory / "tables" / "k.csv").write_text("t18,2.100922,4sf\n", encoding="utf-8")
        (self.directory / "metadata.yaml").write_text("pdfmd-options:\n  calc: {constants: tables/k.csv}\n", encoding="utf-8")
        (self.directory / "d.md").write_text("---\ntitle: D\n---\n\n`t18`{=}\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--assemble-only", "--embed-metadata", "files",
                               "--no-backup", "-o", "asm.md"], cwd=self.directory, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("tables/k.csv", (self.directory / "asm.md").read_text(encoding="utf-8"))
        found, outside = [], []
        pdfmd.add_calc_constants(self.directory / "d.md", [self.directory / "metadata.yaml"], Path(os.path.abspath(self.directory)), set(), found, outside)
        self.assertEqual([item.name for item in found], ["k.csv"])
        self.assertEqual(outside, [])


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Statistics(unittest.TestCase):
    """mean, sd, rsd, ci, Grubbs' G (3.30.20) and the `.calc-table` div, which lists names with their values."""

    def convert(self, text: str, *meta: str) -> subprocess.CompletedProcess:
        arguments = [PANDOC, "-f", "markdown", "-t", "plain", "--wrap=none", "--lua-filter", str(CALC_LUA)]
        for item in meta:
            arguments += ["-M", item]
        return subprocess.run(arguments, input=text, capture_output=True, text=True, encoding="utf-8")

    def values(self, expressions: list[str]) -> list[float]:
        done = self.convert(" | ".join(f"`{expression}`{{=12sf}}" for expression in expressions))
        self.assertEqual(done.stderr, "")
        return [float(part) for part in done.stdout.split("|")]

    def test_the_summary_functions_against_python(self):
        data = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        listing = ", ".join(str(x) for x in data)
        got = self.values([f"mean({listing})", f"median({listing})", f"sum({listing})", f"sd({listing})", f"stdev({listing})",
                           f"var({listing})", f"sem({listing})", f"rsd({listing})", "median(5, 1, 3)", "mean(0.5, 0.7)"])
        want = [statistics.mean(data), statistics.median(data), sum(data), statistics.stdev(data), statistics.stdev(data),
                statistics.variance(data), statistics.stdev(data) / len(data) ** 0.5, statistics.stdev(data) / statistics.mean(data) * 100,
                3.0, 0.6]
        for value, expected in zip(got, want):
            self.assertAlmostEqual(value / expected, 1.0, delta=1e-10)

    def test_a_confidence_interval_and_grubbs(self):
        a, b, c, d, e = self.values(["ci(0.95, 10, 12, 11, 13)", "gstat(10.1, 10.2, 10.15, 10.3, 11.5)", "gcrit(3, 0.05)",
                                     "gcrit(10, 0.05)", "gcrit(25, 0.05)"])
        data = [10.1, 10.2, 10.15, 10.3, 11.5]
        self.assertAlmostEqual(a / (3.1824463052837078 * statistics.stdev([10, 12, 11, 13]) / 2), 1.0, delta=1e-10)
        self.assertAlmostEqual(b / (max(abs(x - statistics.mean(data)) for x in data) / statistics.stdev(data)), 1.0, delta=1e-10)
        for value, expected in ((c, 1.1543048513440386), (d, 2.289954084479603), (e, 2.8216812378051954)):   # SciPy
            self.assertAlmostEqual(value / expected, 1.0, delta=1e-9)

    def test_the_sentence_of_a_discussion(self):
        done = self.convert("`R_A = 0.0102`{=} `R_B2 = 0.0117`{=} `R_E4 = 0.3`{=}\n\nThey are ~`R_E4 / mean(R_A, R_B2)`{=0dp} times lower than the "
                            "`R_E4`{=3sf}% of Experiment 4.\n")
        self.assertEqual(done.stderr, "")
        self.assertIn("They are ~27 times lower than the 0.300% of Experiment 4.", done.stdout)

    def test_a_bad_call_keeps_the_code_with_one_warning(self):
        for expression, reason in (("mean()", "mean needs a number"), ("sd(1)", "sd needs at least two numbers"),
                                   ("ci(2, 1, 2)", "ci takes the confidence first"), ("gcrit(2, 0.05)", "3 or more"),
                                   ("gcrit(10, 5)", "between 0 and 1"), ("gstat(1, 1, 1)", "all the numbers are equal"),
                                   ("rsd(1, -1)", "the mean is 0")):
            with self.subTest(expression=expression):
                done = self.convert(f"`{expression}`{{=}}\n")
                self.assertEqual(done.stderr.count("WARN"), 1, done.stderr)
                self.assertIn(reason, done.stderr)
                self.assertIn(expression, done.stdout)

    def test_the_new_function_names_are_still_free_for_a_variable(self):
        done = self.convert("`mean = 5`{=} `sd = 2`{=} so `mean * sd`{=} and `mean(1, 3)`{=} and `sum = mean + sd = {ans}`{=}\n")
        self.assertEqual(done.stderr, "")
        self.assertIn("10 and 2 and sum = mean + sd = 7", done.stdout)

    def test_the_older_functions_stay_reserved(self):
        done = self.convert("`sqrt = 3`{=}\n")
        self.assertIn("'sqrt' is built in", done.stderr)

    TABLE = ("::: {#tbl:t .calc-table names=\"t*, V\" labels=\"t1=$t_{1}$; V=Volume\" head=\"Symbol; Value\" caption=\"Student's *t*\"}\n:::\n\n"
             "::: {.calc .hide}\nt1 = qt(0.975, 1)\nt2 = qt(0.975, 2)\nt10 = qt(0.975, 10)\nt3 = qt(0.975, 3)\nV = 3.47\nV = 11.82\n:::\n")

    def test_a_table_of_the_names_matching_a_pattern(self):
        done = self.convert(self.TABLE, "pdfmd-calc-digits=4sf")
        self.assertEqual(done.stderr, "")
        rows = [line.split() for line in done.stdout.splitlines() if line.strip() and not line.lstrip().startswith(("-", ":"))]
        self.assertEqual(rows[0][:2], ["Symbol", "Value"])
        self.assertEqual([row[0] for row in rows[1:-0 or None]][:5], ["t₁", "t2", "t3", "t10", "Volume"])     # natural order: t3 before t10
        self.assertEqual([row[-1] for row in rows[1:6]], ["12.71", "4.303", "3.182", "2.228", "3.470"])
        self.assertIn("Student", done.stdout)

    def test_the_table_is_a_real_table_with_the_identifier_and_caption(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "native", "--lua-filter", str(CALC_LUA)], input=self.TABLE, capture_output=True,
                              text=True, encoding="utf-8")
        self.assertIn('"tbl:t"', done.stdout)
        self.assertIn("Emph", done.stdout)                                       # the caption is Markdown
        self.assertIn("InlineMath", done.stdout)                                 # and so is a label

    def test_a_name_counts_as_defined_where_the_table_stands(self):
        done = self.convert("::: {.calc-table names=\"V\" head=none}\n:::\n\n`V = 1`{=}\n\n::: {.calc-table names=\"V\" head=none}\n:::\n\n`V = 2`{=}\n\n"
                            "::: {.calc-table names=\"V\" head=none}\n:::\n")
        self.assertEqual(done.stderr, "")
        self.assertEqual([line.split()[-1] for line in done.stdout.splitlines() if line.strip().startswith("V")], ["1", "1", "2"])

    def test_digits_override_and_the_names_digits(self):
        done = self.convert("`a = 2.71828 = {ans:3sf}`{=} `b = 2.71828`{=}\n\n::: {.calc-table names=\"a b\" digits=\"1dp\" head=none}\n:::\n\n"
                            "::: {.calc-table names=\"a b\" head=none}\n:::\n")
        self.assertEqual(done.stderr, "")
        self.assertEqual([line.split()[-1] for line in done.stdout.splitlines() if re.fullmatch(r"[ab]\s+\S+", line.strip())],
                         ["2.7", "2.7", "2.72", "2.71828"])

    def test_what_goes_wrong_is_visible_and_warned_once_each(self):
        done = self.convert("`ok = 1`{=} `bad = 1/0`{=}\n\n::: {.calc-table names=\"zz* ok nothing bad\"}\n:::\n\n::: {.calc-table}\n:::\n\n"
                            "::: {.calc-table names=\"qq*\"}\n:::\n")
        lines = [line for line in done.stderr.splitlines() if line.startswith("WARN  calc-table")]
        self.assertEqual(len(lines), 5, done.stderr)
        for fragment in ("no name matches 'zz*'", "'nothing' is not defined", "division by zero", "has no names", "no name matches 'qq*'"):
            self.assertTrue(any(fragment in line for line in lines), (fragment, lines))
        self.assertIn("calc-table: no names", done.stdout)
        self.assertIn('calc-table names="qq*": no name found', done.stdout)

    def test_the_names_as_the_text_of_the_div_and_the_digit_pattern(self):
        done = self.convert("::: calc-table\nt# tinf\n:::\n\n::: {.calc .hide}\nt1 = 1.5\nt10 = 2.5\nt2 = 3.5\nt = 9\nt_w = 8\ntinf = 1.96\n:::\n\n"
                            "::: calc-table\nt* V\n:::\n", "pdfmd-calc-digits=3sf")
        rows = [line.split() for line in done.stdout.splitlines() if re.match(r"\s*(t\w*|V)\s+[\d.]+$", line)]
        self.assertEqual([row[0] for row in rows], ["t1", "t2", "t10", "tinf", "t", "t1", "t2", "t10", "t_w", "tinf"])
        self.assertEqual(done.stderr.count("WARN  calc-table"), 1)                    # V is not defined
        self.assertIn("'V' is not defined", done.stderr)

    def test_a_silent_span_glued_to_an_ans_line_keeps_the_later_places(self):
        done = self.convert("::: calc\na = 2 + 3 = {ans:2dp}`b = a * 2`{=}\n\nc = b + 1 = {ans:2dp}\n:::\n\nSpan: `b`{=2dp}, `c`{=2dp}.\n")
        self.assertEqual(done.stderr, "")
        self.assertIn("Span: 10.00, 11.00.", done.stdout)
        self.assertIn("c = b + 1 = 11.00", done.stdout)

    def test_many_places_that_fail_end_with_one_summary_line(self):
        done = self.convert("`a1`{=} `a2`{=} `a3`{=}\n")
        self.assertEqual(done.stderr.count("WARN  calc: `"), 3, done.stderr)
        self.assertIn("WARN  calc: 3 places were not evaluated", done.stderr)
        self.assertNotIn("places were not evaluated", self.convert("`a1`{=} `a2`{=}\n").stderr)

    def test_a_caption_written_in_the_div(self):
        for form in ("t# tinf\n\n: Student *t*, 95%", "t# tinf\n\nTable: Student *t*, 95%", "t# tinf\n: Student *t*, 95%"):
            with self.subTest(form=form):
                done = subprocess.run([PANDOC, "-f", "markdown", "-t", "native", "--lua-filter", str(CALC_LUA)],
                                      input=f"`t1 = 12.7`{{=}} `t10 = 2.2`{{=}} `tinf = 1.96`{{=}}\n\n::: {{#tbl:t .calc-table}}\n{form}\n:::\n",
                                      capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(done.stderr, "")
                self.assertIn('"tbl:t"', done.stdout)
                self.assertIn("Emph", done.stdout)
                self.assertIn('Str "95%"', done.stdout)
                self.assertNotIn("Table:", done.stdout)
                self.assertIn('Str "tinf"', done.stdout)

    def test_a_bare_word_in_braces_is_not_a_div_and_says_so(self):
        done = self.convert("::: {.calc-table t*}\n:::\n")
        self.assertEqual(done.stderr.count("WARN  calc-table"), 1, done.stderr)
        self.assertIn('write ::: {.calc-table names="t*"}', done.stderr)
        self.assertIn("{.calc-table t*}", done.stdout)

    def test_the_detection_adds_the_filter_for_a_document_with_only_a_table(self):
        self.assertTrue(pdfmd.CALC_SPAN_RE.search('::: {.calc-table names="t*"}'))
        self.assertTrue(pdfmd.CALC_SPAN_RE.search("::: calc-table"))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class PartBuiltAlone(unittest.TestCase):
    """A part (or a section) built alone knows the names of what stands above it (3.30.19): pandoc evaluates the parts left out
    with the calculator only, calc.lua writes each name's last value, and the build reads it back."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calc-seed-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "report.md").write_text("---\npdfmd-options:\n  parts: auto\n  calc:\n    digits: 4sf\n---\n\nScaffold.\n",
                                                 encoding="utf-8")
        (self.directory / "parts").mkdir()
        self.parts = self.directory / "parts"
        (self.parts / "10-intro.md").write_text("# Intro\n\nNothing computed here.\n", encoding="utf-8")
        (self.parts / "50-calculations.md").write_text(
            "# Calculations\n\n::: calc\nV = 37.58 - 34.11 = {ans:2dp}\nV = 40.00 - 28.18 = {ans:2dp}\nn = V / 4 = {ans}\n:::\n\n"
            "```{=calc}\nt = 2.101\n```\n", encoding="utf-8")
        (self.parts / "60-discussion.md").write_text(
            "# Discussion\n\nThe tap volume was `V`{=} mL, so `n * 2`{=2dp} and `t`{=}; `ghost`{=2dp} is nowhere.\n", encoding="utf-8")

    def build(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments, "--no-backup", "--to", "latex", "-o", "out.tex"],
                              cwd=self.directory, capture_output=True, text=True, encoding="utf-8")

    def tex(self) -> str:
        return (self.directory / "out.tex").read_text(encoding="utf-8")

    def test_the_dump_and_the_seed_round_trip_through_the_filter(self):
        before = self.directory / "before.md"
        before.write_text((self.parts / "50-calculations.md").read_text(encoding="utf-8"), encoding="utf-8")
        dump = self.directory / "names.tsv"
        subprocess.run([PANDOC, str(before), "-t", "native", "-o", os.devnull, "--lua-filter", str(CALC_LUA), "-M", f"pdfmd-calc-dump={dump}"],
                       capture_output=True, text=True, check=True)
        lines = dump.read_text(encoding="utf-8").splitlines()
        self.assertEqual([line.split("\t")[0] for line in lines], ["V", "n", "t"])
        self.assertEqual(lines[0].split("\t")[1], "11.82")          # the LAST definition of V, at full precision
        self.assertEqual(lines[0].split("\t")[2], "2dp")
        self.assertEqual(lines[1].split("\t")[1:], ["2.9550000000000001", ""])
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "plain", "--wrap=none", "--lua-filter", str(CALC_LUA), "-M", f"pdfmd-calc-seed={dump}"],
                              input="`V`{=} and `n * 2`{=2dp} and `t`{=}\n", capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.stderr, "")
        self.assertEqual(done.stdout.strip(), "11.82 and 5.91 and 2.101")

    def test_a_part_alone_prints_the_numbers_of_the_full_build_and_nothing_vanishes(self):
        full = self.build()
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        whole = self.tex()
        alone = self.build("@60")
        self.assertEqual(alone.returncode, 0, alone.stdout + alone.stderr)
        text = self.tex()
        self.assertIn("The tap volume was 11.82 mL, so 5.91 and 2.101;", text)
        self.assertIn("The tap volume was 11.82 mL, so 5.91 and 2.101;", whole)
        self.assertIn("NOTE  calc: 3 names taken from parts 10-50 (evaluated, not typeset)", alone.stdout)

    def test_a_name_that_is_nowhere_prints_as_code_with_one_warning_in_both_builds(self):
        for arguments in ((), ("@60",)):
            with self.subTest(arguments=arguments):
                done = self.build(*arguments)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn("\\texttt{ghost}", self.tex())
                lines = [line for line in (done.stdout + done.stderr).splitlines() if line.startswith("WARN  calc")]
                self.assertEqual(len(lines), 1, lines)
                self.assertIn("`ghost`{=2dp}", lines[0])

    def test_the_filter_alone_keeps_a_formatted_span_it_cannot_evaluate_visible(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "latex", "--lua-filter", str(CALC_LUA)], input="a `nope + 1`{=3sf} b\n",
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.stderr.count("WARN"), 1, done.stderr)
        self.assertIn("\\texttt{nope\\ +\\ 1}", done.stdout)

    def test_the_setting_turns_it_off(self):
        done = self.build("@60", "--seed-calc", "off")
        self.assertNotIn("names taken from", done.stdout)
        self.assertIn("\\texttt{V}", self.tex())
        self.assertGreaterEqual(done.stdout.count("WARN  calc"), 3)
        (self.directory / "report.md").write_text("---\npdfmd-options:\n  parts: auto\n  seed-calc: off\n---\n", encoding="utf-8")
        done = self.build("@60")
        self.assertNotIn("names taken from", done.stdout)
        self.assertEqual(pdfmd.seed_calc_mode(self.directory / "report.md", []), "off")

    def test_a_part_that_defines_its_own_names_is_not_overridden_by_the_parts_above(self):
        (self.parts / "60-discussion.md").write_text("# Discussion\n\n::: calc\nV = 1.5 + 1 = {ans}\n:::\n\nNow `V`{=}.\n", encoding="utf-8")
        done = self.build("@60")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Now 2.500.", self.tex())

    def test_a_part_with_no_calculator_and_a_document_without_one_are_built_as_before(self):
        done = self.build("@10")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("calc", done.stdout)
        (self.directory / "plain.md").write_text("# One\n\ntext\n\n# Two\n\nmore\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "plain#Two", "--no-backup", "--to", "latex", "-o", "plain.tex"],
                              cwd=self.directory, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("names taken from", done.stdout)

    def test_a_section_built_alone_knows_the_names_of_the_sections_above(self):
        (self.directory / "doc.md").write_text("---\ntitle: T\n---\n\n# Calculations\n\n::: calc\nC = 0.01 = {ans}\nV = 25.0 = {ans}\nm = C * V = {ans:3sf}\n:::\n\n"
                                               "# Discussion\n\nHere `m * 2`{=2dp} and `C`{=}.\n\n# Notes\n\nLater `m`{=3sf}.\n",
                                               encoding="utf-8")
        for section, expected in (("Discussion", "Here 0.50 and 0.01."), ("Notes", "Later 0.250.")):
            with self.subTest(section=section):
                done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), f"doc#{section}", "--no-backup", "--to", "latex", "-o", "doc.tex"],
                                      cwd=self.directory, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn(expected, (self.directory / "doc.tex").read_text(encoding="utf-8"))
                self.assertIn("NOTE  calc: 3 names taken from the sections above it", done.stdout)
                self.assertNotIn("WARN  calc", done.stdout + done.stderr)

    def test_the_mode_is_checked(self):
        with self.assertRaises(SystemExit):
            old, pdfmd.SEED_CALC_CLI = pdfmd.SEED_CALC_CLI, "sometimes"
            try:
                pdfmd.seed_calc_mode(self.directory / "report.md", [])
            finally:
                pdfmd.SEED_CALC_CLI = old


@unittest.skipUnless(PANDOC and shutil.which("lualatex") and shutil.which("pdftotext"), "needs Pandoc, LuaLaTeX and pdftotext")
class RealOutput(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calc-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def build(self, name: str, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, "--no-backup", *arguments], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8")

    def test_a_pdf_has_the_values(self):
        (self.directory / "doc.md").write_text("Years: `2026 - 2006`{=}, half: `1/2`{=}, angle: `sind(30)`{=}, "
                                               "inline code: `2+2`, price $`3*4`{=}.\n", encoding="utf-8")
        done = self.build("doc.md", "-e", "lualatex")
        self.assertTrue((self.directory / "doc.pdf").exists(), done.stdout + done.stderr)
        text = words(self.directory / "doc.pdf")
        self.assertIn("Years: 20, half: 0.5, angle: 0.5, inline code: 2+2, price $12.", text)
        self.assertNotIn("{=}", text)

    def test_calc_off_leaves_the_span_as_it_was(self):
        (self.directory / "doc.md").write_text("---\npdfmd-options:\n  calc: off\n---\n\nYears: `2026 - 2006`{=}.\n", encoding="utf-8")
        done = self.build("doc.md", "-e", "lualatex")
        self.assertTrue((self.directory / "doc.pdf").exists(), done.stdout + done.stderr)
        self.assertIn("2026 - 2006", words(self.directory / "doc.pdf"))

    def test_a_name_defined_in_one_part_is_used_in_another_and_the_div_builds(self):
        (self.directory / "report.md").write_text("---\npdfmd-options:\n  parts: auto\n  calc:\n    digits: 4sf\n---\n", encoding="utf-8")
        (self.directory / "parts").mkdir()
        (self.directory / "parts" / "45-results.md").write_text("The standardised molarity is `C_EDTA`{=} M.\n", encoding="utf-8")
        (self.directory / "parts" / "50-calculations.md").write_text(
            "::: calc\nRun 1: V = 20.60 - 0.00 = {ans:2dp} mL.\\\nC_EDTA = 0.4179 * 0.05000 / (100.09 * 0.5000 * V / 1000) = {ans} M\n:::\n",
            encoding="utf-8")
        done = self.build("report.md", "-e", "lualatex")
        self.assertTrue((self.directory / "report.pdf").exists(), done.stdout + done.stderr)
        text = words(self.directory / "report.pdf")
        self.assertIn("The standardised molarity is 0.02027 M.", text)
        self.assertIn("Run 1: V = 20.60 - 0.00 = 20.60 mL.", text)
        self.assertNotIn("{ans", text)

    def test_a_span_in_a_part_reaches_the_build(self):
        (self.directory / "report.md").write_text("---\npdfmd-options:\n  parts: auto\n---\n", encoding="utf-8")
        (self.directory / "parts").mkdir()
        (self.directory / "parts" / "10-text.md").write_text("Total: `40 + 2`{=} units.\n", encoding="utf-8")
        done = self.build("report.md", "-e", "lualatex")
        self.assertTrue((self.directory / "report.pdf").exists(), done.stdout + done.stderr)
        self.assertIn("Total: 42 units.", words(self.directory / "report.pdf"))


if __name__ == "__main__":
    unittest.main()
