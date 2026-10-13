"""v3.29.20: universal markup, the eighth kind: where the appendix starts."""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "pdfmd_lua" / "markup.lua"


def convert(text: str, writer: str, *extra: str, enabled: str = "appendix") -> tuple[str, str]:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--lua-filter", str(FILTER), "-M", f"pdfmd-markup={enabled}", *extra],
                          input=text, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout, done.stderr


SPELLINGS = ("# One\n\n# Two\n\n\\appendix\n\n# Extra\n", "# One\n\n# Two\n\n<!-- appendix -->\n\n# Extra\n",
             "# One\n\n# Two\n\n# Extra {.appendix}\n")


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_latex_gets_one_appendix_before_the_extra_section(self):
        for text in SPELLINGS:
            out, _ = convert(text, "latex", "--number-sections")
            self.assertEqual(out.count("\\appendix"), 1, text)
            self.assertLess(out.index("\\section{Two}"), out.index("\\appendix"), text)
            self.assertLess(out.index("\\appendix"), out.index("\\section{Extra}"), text)

    def test_typst_gets_letters_and_a_counter_reset(self):
        for text in SPELLINGS:
            out, _ = convert(text, "typst", "--number-sections")
            self.assertEqual(out.count('#set heading(numbering: "A.1")'), 1, text)
            self.assertIn("#counter(heading).update(0)", out)
            self.assertLess(out.index("#set heading"), out.index("= Extra"), text)

    def test_without_numbered_sections_typst_gets_nothing(self):
        out, _ = convert(SPELLINGS[0], "typst")
        self.assertNotIn("#set heading", out)

    def test_other_writers_keep_their_numbering_and_say_so_once_when_numbered(self):
        out, err = convert(SPELLINGS[1], "html5", "--number-sections")
        self.assertNotIn("appendix", out.lower().replace("<!-- appendix -->", ""))
        self.assertEqual(err.count("the appendix is lettered in LaTeX and Typst only"), 1)
        out, err = convert(SPELLINGS[1], "html5")
        self.assertEqual(err, "")

    def test_only_when_the_kind_is_on(self):
        out, _ = convert(SPELLINGS[0], "latex", "--number-sections", enabled="toc")
        self.assertEqual(out.count("\\appendix"), 1)                             # the raw one, as the reader kept it


if __name__ == "__main__":
    unittest.main()
