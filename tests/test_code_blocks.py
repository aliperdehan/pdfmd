"""Code blocks in LaTeX builds (pdfmd_lua/code.lua): long lines wrap, lines can be numbered."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILTER = ROOT / "pdfmd_lua" / "code.lua"
LONG = "word " * 40


def latex(markdown: str, *extra: str, header: bool = True) -> str:
    """The LaTeX Pandoc writes with the filter and (as pdfmd passes them) the wrapping header and its flag."""
    given = ["-H", str(ROOT / "pdfmd_lua" / "code_wrap.tex"), "-M", "pdfmd-code-header=1"] if header else []
    done = subprocess.run(["pandoc", "-f", "markdown", "-s", "-t", "latex", "--lua-filter", str(FILTER), *given, *extra],
                          input=markdown, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Filter(unittest.TestCase):
    def test_the_header_is_guarded_for_a_tex_without_fvextra(self):
        header = (ROOT / "pdfmd_lua" / "code_wrap.tex").read_text(encoding="utf-8")
        self.assertIn("\\IfFileExists{fvextra.sty}", header)
        self.assertIn("breaklines", header)

    def test_without_the_header_flag_no_block_becomes_a_verbatim(self):
        out = latex("```\nplain\n```\n", header=False)
        self.assertIn("\\begin{verbatim}", out)
        self.assertNotIn("Verbatim}", out)

    def test_a_block_without_a_language_becomes_a_wrapping_verbatim(self):
        out = latex("```\nplain\n```\n")
        self.assertIn("\\begin{Verbatim}\nplain\n\\end{Verbatim}", out)
        self.assertNotIn("\\begin{verbatim}", out)

    def test_numbering_is_off_unless_asked_and_per_block_attributes_work(self):
        self.assertNotIn("numbers=left", latex("```python\nx\n```\n"))
        out = latex('``` {.python .numberLines startFrom="10"}\nx\n```\n')
        self.assertIn("numbers=left", out)
        self.assertIn("firstnumber=10", out)
        out = latex("```python\nx\n```\n\n``` {.python .noNumberLines}\ny\n```\n", "-M", "pdfmd-line-numbers=true")
        self.assertEqual(out.count("numbers=left"), 1)
        out = latex("```\nplain\n```\n", "-M", "pdfmd-line-numbers=true")
        self.assertIn("\\begin{Verbatim}[numbers=left]", out)

    def test_step_and_separation_are_set_for_one_block_or_all(self):
        out = latex("``` {.python .numberLines step=5 numbersep=9pt}\nx\n```\n")
        self.assertIn("\\begingroup\\fvset{stepnumber=5,numbersep=9pt}", out)
        self.assertIn("\\endgroup", out)
        out = latex("```python\nx\n```\n", "-M", "pdfmd-line-numbers=true", "-M", "pdfmd-line-number-step=4")
        self.assertIn("stepnumber=4", out)

    def test_wrapping_can_be_switched_off_for_one_block(self):
        out = latex("``` {.python wrap=false}\nx\n```\n")
        self.assertIn("\\fvset{breaklines=false}", out)

    def test_options_in_the_front_matter_are_read(self):
        out = latex("---\npdfmd-options:\n  line-numbers: true\n---\n\n```python\nx\n```\n")
        self.assertIn("numbers=left", out)


class Arguments(unittest.TestCase):
    """What pdfmd hands Pandoc (code_filter_args)."""

    def args(self, text, no_auto=None, **cli):
        sys.path.insert(0, str(ROOT))
        import pdfmd
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-code-args-"))
        self.addCleanup(shutil.rmtree, directory, True)
        source = directory / "d.md"
        source.write_text(text, encoding="utf-8")
        pdfmd.CODE_CLI.clear()
        pdfmd.CODE_CLI.update(cli)
        self.addCleanup(pdfmd.CODE_CLI.clear)
        return pdfmd.code_filter_args(no_auto, [source])

    def test_a_document_with_code_gets_the_filter_and_the_header(self):
        args = self.args("```python\nx\n```\n")
        self.assertIn("code.lua", " ".join(args))
        self.assertIn("code_wrap.tex", " ".join(args))
        self.assertIn("pdfmd-code-header=1", args)

    def test_indented_code_counts_too_and_no_code_means_nothing(self):
        self.assertTrue(self.args("Text\n\n    indented code\n"))
        self.assertEqual(self.args("Just text.\n"), [])

    def test_switches(self):
        self.assertEqual(self.args("```\nx\n```\n", ["codewrap"]), [])
        args = self.args("```\nx\n```\n", **{"code-wrap": False})
        self.assertNotIn("--include-in-header", args)
        self.assertIn("pdfmd-code-wrap=false", args)
        args = self.args("```\nx\n```\n", **{"line-numbers": True, "line-number-step": 5})
        self.assertIn("pdfmd-line-numbers=true", args)
        self.assertIn("pdfmd-line-number-step=5", args)
        args = self.args("---\npdfmd-options:\n  code-wrap: false\n---\n\n```\nx\n```\n")
        self.assertNotIn("--include-in-header", args)


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("lualatex") and shutil.which("pdftotext"),
                     "needs Pandoc, LuaLaTeX and pdftotext")
class Built(unittest.TestCase):
    def build(self, *args: str) -> str:
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-code-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "c.md").write_text(
            f"---\ntitle: T\n---\n\nAn ordinary paragraph with some Han text 漢字 so that pdfmd adds its own header file.\n\n```bash\n{LONG}\n```\n\n```\n{LONG}\n```\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "c.md", "-e", "lualatex", "--no-stamp",
                               "--no-backup", *args], cwd=directory, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(directory / "xdg")})
        self.assertEqual(done.returncode, 0, done.stderr)
        return subprocess.run(["pdftotext", "-bbox", str(directory / "c.pdf"), "-"], capture_output=True,
                              text=True).stdout

    @staticmethod
    def rightmost(boxes: str) -> tuple[float, float]:
        page = float(re.search(r'<page width="([\d.]+)"', boxes).group(1))
        return max(float(value) for value in re.findall(r'xMax="([\d.]+)"', boxes)), page

    def test_long_code_lines_stay_inside_the_margin_unless_told_not_to(self):
        edge, page = self.rightmost(self.build())
        self.assertLess(edge, page - 60)                       # one inch margins
        edge, page = self.rightmost(self.build("--no-code-wrap"))
        self.assertGreater(edge, page - 60)


if __name__ == "__main__":
    unittest.main()
