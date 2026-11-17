"""Code blocks and inline code in LaTeX builds (pdfmd_lua/code.lua): long lines wrap, lines can be numbered."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
FILTER = ROOT / "lib" / "pdfmd_lua" / "code.lua"
LONG = "word " * 40


def latex(markdown: str, *extra: str, header: bool = True) -> str:
    """The LaTeX Pandoc writes with the filter and (as pdfmd passes them) the wrapping header and its flag."""
    given = ["-H", str(ROOT / "lib" / "pdfmd_lua" / "code_wrap.tex"), "-M", "pdfmd-code-header=1"] if header else []
    done = subprocess.run(["pandoc", "-f", "markdown", "-s", "-t", "latex", "--lua-filter", str(FILTER), *given, *extra],
                          input=markdown, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Filter(unittest.TestCase):
    def test_the_header_is_guarded_for_a_tex_without_fvextra(self):
        header = (ROOT / "lib" / "pdfmd_lua" / "code_wrap.tex").read_text(encoding="utf-8")
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

    def test_what_is_not_code(self):
        # v3.27.21: thirteen of sixteen real documents that got the code header had no code block at all
        sys.path.insert(0, str(ROOT))
        import pdfmd
        not_code = [
            "---\nreferences:\n  - id: a\n    type: article-journal\n---\n\nText.\n",       # the front matter's YAML
            "```{=latex}\n\\begin{tikzpicture}\\end{tikzpicture}\n```\n",                  # raw blocks, their fences
            "~~~ {=html}\n<b>x</b>\n~~~\n\nText.\n",
            "- item\n\n    more of the item\n",                                             # a list goes on
            "1. one\n    - nested\n",
            "Use ```x``` inline.\n```y``` too.\n",
        ]
        for text in not_code:
            self.assertFalse(pdfmd.has_code_block(text), text)
        code = [
            "```\nplain\n```\n", "```r\nx <- 1\n```\n", "``` {.python}\nx\n```\n", "~~~~\nx\n~~~~\n",
            "```{=latex}\n\\x\n```\n\nThen\n\n```python\ny\n```\n",                          # after a raw block
            "- item\n\n    ```python\n    x\n    ```\n",                                     # fenced in a list item
            "Text\n\n    indented code\n",
        ]
        for text in code:
            self.assertTrue(pdfmd.has_code_block(text), text)
        self.assertEqual(self.args("---\nreferences:\n  - id: a\n    type: book\n---\n\n```{=latex}\n\\x\n```\n"), [])

    def test_inline_only_code_gets_the_filter_without_loading_fvextra(self):
        args = self.args("Use `a/b` here.\n")
        self.assertIn("code.lua", " ".join(args))
        self.assertNotIn("code_wrap.tex", " ".join(args))

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
                              env={**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(directory / "xdg"), "APPDATA": str(directory / "xdg")})
        self.assertEqual(done.returncode, 0, done.stderr)
        return subprocess.run(["pdftotext", "-bbox", str(directory / "c.pdf"), "-"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace").stdout

    @staticmethod
    def rightmost(boxes: str) -> tuple[float, float]:
        page = float(re.search(r'<page width="([\d.]+)"', boxes).group(1))
        return max(float(value) for value in re.findall(r'xMax="([\d.]+)"', boxes)), page

    def test_long_code_lines_stay_inside_the_margin_unless_told_not_to(self):
        edge, page = self.rightmost(self.build())
        self.assertLess(edge, page - 60)                       # one inch margins
        edge, page = self.rightmost(self.build("--no-code-wrap"))
        self.assertGreater(edge, page - 60)


# A class or package that replaces \\[ itself, as nulabreport does after copying it at \\begin{document}: fvextra's lineno
# had rewritten \\[ to open a linenomath environment, and the copy then broke ("\\begin{linenomath} ended by \\end{equation*}").
OVERRIDING_PREAMBLE = r"""\usepackage{amsmath}
\makeatletter
\AtBeginDocument{%
  \NewCommandCopy\Lab@lbrack\[%
  \NewCommandCopy\Lab@rbrack\]%
  \DeclareRobustCommand\[{\Lab@display}}
\def\Lab@display#1\]{\Lab@lbrack #1\Lab@rbrack}
\makeatother
"""


class WithAClassThatOverridesDisplayMath(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_code_wrapping_does_not_break_a_documents_own_display_math(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-code-math-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "preamble.tex").write_text(OVERRIDING_PREAMBLE, encoding="utf-8")
        (directory / "m.md").write_text(
            f"---\ntitle: T\n---\n\n```\n{LONG}\n```\n\n$$ n = \\frac{{m}}{{M}} $$\n\n$$ x = 1 $$\n\n"
            "\\begin{equation}\ny = 2\n\\end{equation}\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "m.md", "-e", "lualatex", "--no-stamp", "--no-backup"],
                              cwd=directory, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(directory / "xdg"), "APPDATA": str(directory / "xdg")})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("failed", done.stderr)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class InlineCode(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="pdfmd-inline-code-")
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)

    def convert(self, text, *extra, writer="latex"):
        (self.directory / "d.md").write_text(text, encoding="utf-8")
        output = self.directory / ("out." + {"latex": "tex", "html": "html", "typst": "typ", "docx": "docx"}[writer])
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "d.md", "--to", writer, "-o", str(output),
                               "--no-stamp", "--no-backup", *extra], cwd=self.directory, capture_output=True, text=True,
                              encoding="utf-8", env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return output

    def test_inline_only_documents_get_emergency_breaks_after_every_separator(self):
        separators = (("/", "/"), (".", "."), ("_", r"\_"), ("-", "-"), ("\\", r"\textbackslash{}"),
                                   (":", ":"), ("=", "="), ("&", r"\&"), ("?", "?"), ("#", r"\#"))
        source = " and ".join(f"`a{separator}b`" for separator, _ in separators) + "\n"
        out = self.convert(source).read_text(encoding="utf-8")
        for separator, escaped in separators:
            with self.subTest(separator=separator):
                self.assertIn(r"\texttt{a" + escaped + r"}\penalty9999{}\texttt{b}", out)

    def test_all_document_switches_remove_inline_breaks(self):
        for front, args in (("", ("--no-code-wrap",)), ("", ("--no-auto", "codewrap")),
                            ("---\npdfmd-options: {code-wrap: false}\n---\n\n", ())):
            with self.subTest(front=front, args=args):
                out = self.convert(front + "Use `a/b` here.\n", *args).read_text(encoding="utf-8")
                self.assertNotIn(r"\penalty9999", out)
                self.assertIn(r"\texttt{a/b}", out)

    def test_other_writers_and_raw_latex_are_unchanged(self):
        for writer in ("html", "typst", "docx"):
            with self.subTest(writer=writer):
                output = self.convert("Use `a/b` here.\n", writer=writer)
                if writer == "docx":
                    import zipfile
                    with zipfile.ZipFile(output) as archive:
                        text = archive.read("word/document.xml").decode("utf-8")
                else:
                    text = output.read_text(encoding="utf-8")
                self.assertIn("a/b", text)
                self.assertNotIn("penalty9999", text)
        out = self.convert(r"Use `\texttt{a/b}`{=latex} here." + "\n").read_text(encoding="utf-8")
        self.assertIn(r"\texttt{a/b}", out)
        self.assertNotIn(r"\penalty9999", out)

    def test_nested_code_escaping_and_attributes_still_use_pandocs_writer(self):
        out = self.convert("# `head/path`\n\n- Use `a/b $x % {c} ~ ^ |` here.\n\n"
                           "A note[^n].\n\n[^n]: Use `a/b`{#example .python} there.\n").read_text(encoding="utf-8")
        self.assertGreaterEqual(out.count(r"\penalty9999"), 2)
        self.assertIn(r"\texttt{head/path}", out)
        self.assertIn(r"\$x", out)
        self.assertIn(r"\%", out)
        self.assertIn(r"\{c\}", out)
        self.assertIn(r"\NormalTok", out)                 # highlighted inline code still gets its macros

    def test_headings_keep_unsplit_code_for_pdf_bookmarks(self):
        out = self.convert("## The `config.yaml` file\n\nUse `body/path` here.\n").read_text(encoding="utf-8")
        self.assertIn(r"The \texttt{config.yaml} file", " ".join(out.split()))
        self.assertEqual(out.count(r"\penalty9999"), 1)

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftotext"), "needs pdfLaTeX and pdftotext")
    def test_pdf_outline_keeps_the_original_heading_text(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("needs pypdf")
        source = "## The `config.yaml` file\n\nUse `body/path` here.\n"
        self.pdf_text_and_log(source, "--no-code-wrap")
        before = [entry.title for entry in PdfReader(self.directory / "out.pdf").outline]
        self.pdf_text_and_log(source)
        after = [entry.title for entry in PdfReader(self.directory / "out.pdf").outline]
        self.assertEqual(before, ["The config.yaml file"])
        self.assertEqual(after, before)

    def pdf_text_and_log(self, text, *extra):
        tex = self.convert(text, *extra)
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(tex), "-e", "pdflatex",
                               "--engine-fallback", "off", "--keep-aux", "--no-stamp", "--no-backup"],
                              cwd=self.directory, capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        log = tex.with_suffix(".log").read_text(encoding="utf-8", errors="replace")
        done = subprocess.run(["pdftotext", "-layout", str(tex.with_suffix(".pdf")), "-"], capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout, log

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftotext"), "needs pdfLaTeX and pdftotext")
    def test_long_inline_path_wraps_without_a_hyphen_and_the_switch_restores_overflow(self):
        path = "/".join(["directory"] * 8) + "/file_name.txt"
        source = f"A long path: `{path}` finishes here.\n"
        text, log = self.pdf_text_and_log(source)
        self.assertNotIn(r"Overfull \hbox", log)
        self.assertIn(path, b"".join(text.split()).decode("utf-8"))
        _, log = self.pdf_text_and_log(source, "--no-code-wrap")
        self.assertIn(r"Overfull \hbox", log)

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftotext"), "needs pdfLaTeX and pdftotext")
    def test_code_that_fits_keeps_the_exact_pdf_text_layout(self):
        source = ("A paragraph with `short/file_name.txt` in the middle of ordinary prose, and with enough words to fill "
                  "several lines. Another `a/b.c_d-e\\f:g=h&i?j#k` fragment fits too, as does `a--b`. " * 3 + "\n")
        before, _ = self.pdf_text_and_log(source, "--no-code-wrap")
        after, log = self.pdf_text_and_log(source)
        self.assertNotIn(r"Overfull \hbox", log)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
