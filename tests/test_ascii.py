"""`--to ascii` (v3.26.8): the transliterator (pure Python) and the command line."""

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
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
from pdfmd_flat import asciify, keep  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402

from pdfmd_unicode import translit  # noqa: E402

HAS_HAN = translit.available("han")          # pypinyin or anyascii is installed: Chinese has a spelling


class Transliteration(unittest.TestCase):
    def setUp(self):
        self.ascii = asciify.Asciifier()

    def check(self, text: str, expected: str):
        got = self.ascii.text(text)
        self.assertEqual(got, expected)
        self.assertTrue(got.isascii())

    def test_ascii_is_left_alone(self):
        self.assertEqual(self.ascii.text("plain ~ text\n"), "plain ~ text\n")

    def test_punctuation_spaces_and_invisible_characters(self):
        self.check("“quoted” ‘single’ it’s", "\"quoted\" 'single' it's")
        self.check("1–5 — a … b", "1-5 -- a ... b")
        self.check("a\u00a0b\u2009c\u200bd\u00ade", "a b cde")
        self.check("5 ≤ x ≥ 2 ≠ 3 ± 1 × 2 → 3 ⇌ 4", "5 <= x >= 2 != 3 +/- 1 x 2 -> 3 <=> 4")
        self.check("5 °C and 90°", "5 degC and 90deg")
        self.check("© ® ™ ½", "(c) (R) (TM) 1/2")
        self.check("−5", "-5")

    def test_scripts_are_marked(self):
        self.check("H₂O x² CO₃²⁻ x₁₂ 10⁻³", "H_2O x^2 CO_3^(2-) x_(12) 10^(-3)")

    def test_latin_letters(self):
        self.check("Café Müller Łódź Straße Æsir œuvre ﬁ", "Cafe Muller Lodz Strasse AEsir oeuvre fi")

    def test_greek_by_name_the_micro_prefix_and_words(self):
        self.check("α-helix ΔT Ω", "alpha-helix DeltaT Omega")
        self.check("5 μm, 3 µL, μ = 2", "5 um, 3 uL, mu = 2")
        self.check("Σοφία", "Sophia")

    def test_cyrillic_keeps_its_case(self):
        self.check("Привет Мир Щука", "Privet Mir Shchuka")
        self.check("Қазақстан", "Qazaqstan")

    def test_scripts_with_a_pack(self):
        self.check("שלום", "shlvm")
        self.check("안녕", "annyeong")
        self.check("こんにちは", "konnichiha")

    def test_what_has_no_form_is_counted_and_written_by_the_mode(self):
        if HAS_HAN:
            self.skipTest("a library here spells Chinese")
        self.assertEqual(self.ascii.text("a日b"), "a?b")
        self.assertEqual(dict(self.ascii.lost), {"日": 1})
        self.assertEqual(asciify.Asciifier("escape").text("a日b😀"), "a\\u65e5b\\U0001f600")
        self.assertEqual(asciify.Asciifier("drop").text("a日b"), "ab")
        with self.assertRaises(ValueError):
            asciify.Asciifier("shout")

    @unittest.skipUnless(HAS_HAN, "needs pypinyin or anyascii (pdfmd --install translit)")
    def test_chinese_with_a_library(self):
        self.assertEqual(self.ascii.text("日本語").replace(" ", "").lower(), "ribenyu")
        self.assertEqual(dict(self.ascii.lost), {})

    def test_math_uses_macros(self):
        self.assertEqual(self.ascii.math("α + β ≥ 2x² · ΔG°"), "\\alpha + \\beta \\geq 2x^2 \\cdot \\Delta G^\\circ")
        self.assertEqual(self.ascii.math("\\alpha"), "\\alpha")
        self.assertEqual(self.ascii.math("αx"), "\\alpha x")

    def test_smart_punctuation_can_be_kept_for_the_writer(self):
        self.assertEqual(self.ascii.text("“a” — é…", keep=asciify.SMART), "“a” — e…")

    def test_describe_and_merge(self):
        merged = asciify.merge({"日": 2}, {"日": 1, "本": 1})
        self.assertEqual(merged, {"日": 3, "本": 1})
        self.assertEqual(asciify.describe(merged), "日 U+65E5 (x3), 本 U+672C")

    def test_the_helper_process_answers_in_ascii(self):
        report = Path(tempfile.mkdtemp(prefix="pdfmd-ascii-report-")) / "r.json"
        self.addCleanup(shutil.rmtree, report.parent, ignore_errors=True)
        data = "Привет\x00\x01α ≥ 1\x00plain\x00a日".encode("utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--ascii-stdio", "question", str(report)],
                              input=data, capture_output=True, cwd=report.parent)
        self.assertEqual(done.returncode, 0, done.stderr)
        pieces = done.stdout.decode("ascii").split("\x00")
        self.assertEqual(pieces[:3], ["Privet", "\\alpha \\geq 1", "plain"])
        self.assertEqual(len(pieces), 4)


HOSTILE = """---
title: Hostile “title”
---

− 5 is minus five.

≥ 5 is at least five.

• bullet-like

—

* real list ≥ item

Link [écran](https://example.org/é "Titre é") and `code é` and
$α + β ≥ 2$ with “quotes” and ‘single’.

| Größe | Wert |
|-------|------|
| α     | 1–2  |

```
é in code
```

H~2~O — x² ≠ y³, Привет.
"""


@needs_pandoc(3, 1, 3)
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-ascii-cli-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"]}

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=self.env)

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def read(self, name: str) -> str:
        data = (self.directory / name).read_bytes()
        self.assertTrue(data.isascii(), f"{name} is not ASCII")
        return data.decode("ascii")

    def test_text_beside_the_source_under_its_own_name(self):
        self.write("doc.md", HOSTILE)
        result = self.run_pdfmd("doc.md", "--to", "ascii")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = self.read("doc.ascii.txt")
        self.assertIn("Hostile \"title\"\n===============\n", text)
        self.assertIn("ecran <https://example.org/%C3%A9>", text)
        self.assertIn("\"quotes\" and 'single'", text)
        self.assertIn("H_2O -- x^2 != y^3, Privet.", text)
        self.assertFalse((self.directory / "doc.txt").exists())

    def test_flat_markdown_does_not_turn_symbols_into_syntax(self):
        self.write("doc.md", HOSTILE)
        self.assertEqual(self.run_pdfmd("doc.md", "--to", "ascii:gfm").returncode, 0)
        text = self.read("doc.ascii.gfm.md")
        for line in ("\\- 5 is minus five.", "\\>= 5 is at least five.", "\\* bullet-like", "\n--\n"):
            self.assertIn(line, text)
        self.assertIn("[ecran](https://example.org/%C3%A9 \"Titre e\")", text)
        self.assertIn("$\\alpha + \\beta \\geq 2$", text)
        self.assertIn("| alpha  | 1-2  |", text)             # the columns were measured on the ASCII text
        self.assertIn("    e in code", text)
        self.assertIn("`code e`", text)
        self.assertIn("\"quotes\" and 'single'", text)
        self.assertNotIn("\\\"", text)

    def test_other_text_formats_are_ascii_too(self):
        self.write("doc.md", HOSTILE)
        for target in ("markdown", "commonmark", "rst", "org", "asciidoc", "plain"):
            with self.subTest(target=target):
                self.assertEqual(self.run_pdfmd("doc.md", "--to", f"ascii:{target}", "-o", f"{target}.out").returncode, 0)
                self.read(f"{target}.out")
        smart = self.read("markdown.out")
        self.assertIn("\"quotes\" and 'single'", smart)          # Pandoc's own smart typography, no backslashes

    def test_the_name_asks_for_it_and_a_binary_format_is_refused(self):
        self.write("doc.md", "---\ntitle: T\n---\n\nCafé.\n")
        self.assertEqual(self.run_pdfmd("doc.md", "-o", "x.ascii.txt").returncode, 0)
        self.assertIn("Cafe.", self.read("x.ascii.txt"))
        self.assertEqual(self.run_pdfmd("doc.md", "-o", "y.ascii.gfm.md").returncode, 0)
        self.assertIn("# T", self.read("y.ascii.gfm.md"))
        bad = self.run_pdfmd("doc.md", "--to", "ascii:docx")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("text formats", bad.stdout + bad.stderr)

    def test_missing_characters(self):
        if HAS_HAN:
            self.skipTest("a library here spells Chinese")
        self.write("doc.md", "---\ntitle: T\n---\n\nA 日本 b.\n")
        warned = self.run_pdfmd("doc.md", "--to", "ascii")
        self.assertEqual(warned.returncode, 0)
        self.assertIn("2 characters with no ASCII form (日 U+65E5, 本 U+672C)", warned.stdout + warned.stderr)
        self.assertIn("A ?? b.", self.read("doc.ascii.txt"))
        self.assertEqual(self.run_pdfmd("doc.md", "--to", "ascii", "--ascii-missing", "escape", "-o", "e.txt").returncode, 0)
        self.assertIn("A \\u65e5\\u672c b.", self.read("e.txt"))
        refused = self.run_pdfmd("doc.md", "--to", "ascii", "--ascii-missing", "fail", "-o", "f.txt")
        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse((self.directory / "f.txt").exists())

    def test_fail_fails_one_file_and_a_batch_goes_on(self):
        if HAS_HAN:
            self.skipTest("a library here spells Chinese")
        (self.directory / "d").mkdir()
        (self.directory / "out").mkdir()
        (self.directory / "d" / "a.md").write_text("# A\n\n日本\n", encoding="utf-8")
        (self.directory / "d" / "b.md").write_text("# B\n\nCafé\n", encoding="utf-8")
        result = self.run_pdfmd("-b", "d", "-o", "out", "--to", "ascii", "--ascii-missing", "fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL  d/a.md", result.stdout + result.stderr)
        self.assertFalse((self.directory / "out" / "a.ascii.txt").exists())
        self.assertIn("Cafe", self.read("out/b.ascii.txt"))

    def test_default_output_cannot_be_ascii(self):
        self.write("doc.md", "---\ntitle: T\npdfmd-options:\n  default-output: ascii\n---\n\nText.\n")
        result = self.run_pdfmd("doc.md")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command line", result.stdout + result.stderr)

    def test_the_document_option(self):
        if HAS_HAN:
            self.skipTest("a library here spells Chinese")
        self.write("doc.md", "---\ntitle: T\npdfmd-options:\n  ascii: {missing: drop}\n---\n\nA 日 b.\n")
        self.assertEqual(self.run_pdfmd("doc.md", "--to", "ascii").returncode, 0)
        self.assertIn("A b.", self.read("doc.ascii.txt"))

    def test_kept_source_stays_ascii(self):
        self.write("doc.md", "---\ntitle: Étude\n---\n\nCafé α.\n")
        result = self.run_pdfmd("doc.md", "--to", "ascii:gfm", "--keep-source", "readable")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("keeps its source packed", result.stdout + result.stderr)
        text = self.read("doc.ascii.gfm.md")
        body, trailer = keep.split(text)
        self.assertEqual(trailer.mode, "packed")
        restored = self.run_pdfmd("--restore", "doc.ascii.gfm.md")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertIn("Café α.", (self.directory / "doc.ascii.gfm.restored" / "doc.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
