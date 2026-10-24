"""The inline calculator (v3.30.4): `2026 - 2006`{=} becomes 20 through pdfmd_lua/calc.lua's own parser; the detection that
adds the filter, the `calc: off` switch, and a real PDF built through the whole pipeline (a part included)."""

from __future__ import annotations

import os
import shutil
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
            self.assertEqual(pdfmd.calc_filter_args([plain, marked], []), ["-M", "pdfmd-calc-round=even", "--lua-filter", str(CALC_LUA)])

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
