"""v3.29.18: universal markup, the sixth kind: blocks kept together on one page."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pandoc_support import WORD, office_markup  # noqa: E402

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "lib" / "pdfmd_lua" / "markup.lua"

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

    def test_word_keeps_paragraphs_and_lists_without_joining_the_next_block(self):
        source = SOURCE.replace("Second", "- First item\n- Last item") + "\nAfter.\n"
        with tempfile.TemporaryDirectory() as folder:
            document, _ = office_markup(folder, source, "docx", "--markup", "keep")
            disabled, _ = office_markup(folder, source, "docx", "--no-markup")
        for para in document.findall(".//w:body/w:p", WORD):
            label = "".join(span.text or "" for span in para.findall(".//w:t", WORD))
            with self.subTest(label=label):
                self.assertTrue(label, "keep delimiters must not create empty paragraphs")
                self.assertEqual(para.find("./w:pPr/w:keepLines", WORD) is not None,
                                 label not in ("Before.", "After."))
                self.assertEqual(para.find("./w:pPr/w:keepNext", WORD) is not None,
                                 label in ("A kept para", "First item"))
        self.assertEqual(len(document.findall(".//w:keepLines", WORD)), 6)
        self.assertEqual(disabled.findall(".//w:keepLines", WORD), [])

    def test_only_when_the_kind_is_on(self):
        out, _ = convert("html5", enabled="toc")
        self.assertIn('<div class="keep">', out)


if __name__ == "__main__":
    unittest.main()
