"""v3.29.18: universal markup, the sixth kind: blocks kept together on one page."""

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

::: keep
A kept para

Second
:::

::: nobreak
Nobreak
:::

<div style="break-inside: avoid">

Styled keep

</div>

\\begin{samepage}

tex keep

\\end{samepage}
"""


def convert(writer: str, enabled: str = "keep") -> tuple[str, str]:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--lua-filter", str(FILTER), "-M", f"pdfmd-markup={enabled}"],
                          input=SOURCE, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout, done.stderr


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_latex_gets_samepage(self):
        out, _ = convert("latex")
        self.assertEqual(out.count("\\begin{samepage}"), 4)
        self.assertEqual(out.count("\\end{samepage}"), 4)
        for word in ("A kept para", "Nobreak", "Styled keep", "tex keep"):
            self.assertIn(word, out)

    def test_typst_gets_an_unbreakable_block(self):
        out, _ = convert("typst")
        self.assertEqual(out.count("#block(breakable: false)["), 4)
        self.assertIn("tex keep", out)

    def test_html_gets_a_break_inside_div(self):
        out, _ = convert("html5")
        self.assertEqual(out.count('<div style="break-inside: avoid">'), 4)
        self.assertIn("<p>tex keep</p>", out)

    def test_word_keeps_the_text_and_says_so_once(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "docx", "-o", discard_path(".docx"),
                               "--lua-filter", str(FILTER), "-M", "pdfmd-markup=keep"], input=SOURCE, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr.count("keeping blocks together is not applied to docx"), 1)

    def test_only_when_the_kind_is_on(self):
        out, _ = convert("html5", enabled="toc")
        self.assertIn('<div class="keep">', out)


if __name__ == "__main__":
    unittest.main()
