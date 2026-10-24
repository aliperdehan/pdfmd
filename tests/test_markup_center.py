"""v3.29.16: universal markup, the fourth kind: centred text. <center>, <div align="center">, ::: center, \\begin{center}."""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pandoc_support import discard_path  # noqa: E402

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "pdfmd_lua" / "markup.lua"

SOURCE = """\
Before.

<center>

Centred para

</center>

<div align="center">

A div

</div>

::: center
Colon div
:::

\\begin{center}

tex centred

\\end{center}

<div style="text-align: center">

Styled

</div>

After.
"""


def convert(writer: str, enabled: str = "center", text: str = SOURCE) -> tuple[str, str]:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--lua-filter", str(FILTER), "-M", f"pdfmd-markup={enabled}"],
                          input=text, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout, done.stderr


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_latex_gets_one_environment_per_spelling(self):
        out, _ = convert("latex")
        self.assertEqual(out.count("\\begin{center}"), 5)
        self.assertEqual(out.count("\\end{center}"), 5)
        for word in ("Centred para", "A div", "Colon div", "tex centred", "Styled"):
            self.assertIn(word, out)

    def test_typst_gets_an_align_block_per_spelling(self):
        out, _ = convert("typst")
        self.assertEqual(out.count("#align(center)["), 5)
        for word in ("Centred para", "tex centred", "Styled"):
            self.assertIn(word, out)

    def test_html_gets_a_text_align_div_and_loses_no_raw_tex_text(self):
        out, _ = convert("html5")
        self.assertEqual(out.count('<div style="text-align: center">'), 5)
        self.assertIn("<p>tex centred</p>", out)
        self.assertNotIn("<center>", out)

    def test_other_writers_keep_the_text(self):
        out, err = convert("markdown")
        for word in ("Centred para", "A div", "Colon div", "tex centred", "Styled"):
            self.assertIn(word, out)
        self.assertEqual(err, "")

    def test_opendocument_keeps_the_text_and_says_so_once(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "odt", "-o", discard_path(".odt"),
                               "--lua-filter", str(FILTER), "-M", "pdfmd-markup=center"], input=SOURCE, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr.count("centring is not applied to odt"), 1)

    def test_only_when_the_kind_is_on(self):
        out, _ = convert("html5", enabled="toc")
        self.assertNotIn("text-align: center", out.replace('<div style="text-align: center">\n<p>Styled', ""))
        self.assertIn("<center>", out)

    def test_an_unclosed_center_is_left_alone(self):
        out, _ = convert("html5", text="<center>\n\nno end\n")
        self.assertIn("no end", out)


if __name__ == "__main__":
    unittest.main()
