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
    ("x + 1", "'x' is not a number"), ("3 +", "ends too soon"), ("(1 + 2", "expected ')'"), ("1 2", "unexpected"), ("|1 - 2", "expected '|'"), ("2 $ 3", "is not arithmetic"),
    ("asin(2)", "not defined there"), ("asind(2)", "not defined there"), ("sqrt(-1)", "not defined there"), ("ln(0)", "not defined there"), ("acosh(0.5)", "not defined there"),
    ("(-8)^(1/3)", "not a number"), ("10^400", "infinite"), ("sin(1, 2)", "takes 1 argument"), ("min()", "needs a number"),
    ("round(2.5, 1.5)", "whole number"), ("factorial(2.5)", "whole number"), ("factorial(171)", "whole number"), ("cot(0)", "not defined"),
)


class Detection(unittest.TestCase):
    def test_what_adds_the_filter(self):
        for text in ("so `1/2`{=} is half", "`1/2`{=}.", "``1/2``{=}", "a `2+2`{=}, b"):
            with self.subTest(text=text):
                self.assertTrue(pdfmd.CALC_SPAN_RE.search(text))

    def test_what_does_not(self):
        for text in ("`1/2` is half", "`1/2`{.calc}", "{=} alone", "`{r} 1+1`"):
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
        away = "---\npdfmd-options:\n  calc-round: away\n---\n\n"
        self.assertIn("Half: 3, sum: 3.", self.html(away))
        self.assertIn("Half: 2, sum: 3.", self.html(away, "--calc-round", "even"))
        self.assertIn("Half: 3, sum: 3.", self.html("", "--calc-round", "away"))
        self.assertIn("Half: 3, sum: 3.", self.html("", env={"PDFMD_CALC_ROUND": "away"}))

    def test_a_wrong_calc_round_is_refused(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--calc-round", "up", "doc.md"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("even", done.stderr)
        (self.directory / "bad.md").write_text("---\npdfmd-options:\n  calc-round: up\n---\n\n`1+1`{=}\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "bad.md", "--to", "html", "--no-backup"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("calc-round must be even or away", done.stdout + done.stderr)


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

    def test_a_span_in_a_part_reaches_the_build(self):
        (self.directory / "report.md").write_text("---\npdfmd-options:\n  parts: auto\n---\n", encoding="utf-8")
        (self.directory / "parts").mkdir()
        (self.directory / "parts" / "10-text.md").write_text("Total: `40 + 2`{=} units.\n", encoding="utf-8")
        done = self.build("report.md", "-e", "lualatex")
        self.assertTrue((self.directory / "report.pdf").exists(), done.stdout + done.stderr)
        self.assertIn("Total: 42 units.", words(self.directory / "report.pdf"))


if __name__ == "__main__":
    unittest.main()
