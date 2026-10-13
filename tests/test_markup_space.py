"""v3.29.25: universal markup, the ninth kind: vertical space on a line of its own."""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
import zipfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "pdfmd_lua" / "markup.lua"

SOURCE = """\
Before.

\\vspace{1cm}

Mid.

\\bigskip

<br><br>

```{=typst}
#v(2cm)
```

A line with a <br> in it stays.

After.
"""


def convert(writer: str, enabled: str = "space") -> str:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--lua-filter", str(FILTER), "-M", f"pdfmd-markup={enabled}"],
                          input=SOURCE, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_latex_gets_a_vspace_for_each(self):
        out = convert("latex")
        for length in ("1cm", "12pt", "2em", "2cm"):
            self.assertIn(f"\\vspace{{{length}}}", out)
        self.assertNotIn("\\bigskip", out)

    def test_typst_gets_v(self):
        out = convert("typst")
        for length in ("1cm", "12pt", "2em", "2cm"):
            self.assertIn(f"#v({length})", out)

    def test_html_gets_an_empty_div_of_that_height(self):
        out = convert("html5")
        for length in ("1cm", "12pt", "2em", "2cm"):
            self.assertIn(f'<div style="height: {length}">', out)
        self.assertIn("A line with a <br /> in it stays.", out.replace("<br>", "<br />"))

    def test_word_gets_empty_paragraphs(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "o.docx"
            subprocess.run([PANDOC, "-f", "markdown", "-o", str(target), "--lua-filter", str(FILTER), "-M", "pdfmd-markup=space"],
                           input=SOURCE, capture_output=True, text=True, check=True)
            with zipfile.ZipFile(target) as archive:
                body = archive.read("word/document.xml").decode("utf-8")
            self.assertGreaterEqual(body.count("<w:p>"), 8)                      # the text and the lines that stand for the space

    def test_the_markdown_family_keeps_what_was_written(self):
        out = convert("markdown")
        self.assertIn("\\vspace{1cm}", out)
        self.assertIn("\\bigskip", out)

    def test_only_when_the_kind_is_on(self):
        out = convert("latex", enabled="toc")
        self.assertIn("\\bigskip", out)
        self.assertNotIn("\\vspace{12pt}", out)


if __name__ == "__main__":
    unittest.main()
