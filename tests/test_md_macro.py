"""v3.32.0: Markdown inside raw LaTeX, `\\md{...}` and `\\begin{md}` (entry 3dc, pdfmd_lua/md_macro.lua); real builds through pdfmd."""

from __future__ import annotations

import os
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

import pdfmd  # noqa: E402

BIB = "@book{smith2020, author={Smith, John}, title={A Book}, year={2020}, publisher={P}}\n"


class Detect(unittest.TestCase):
    def test_a_macro_outside_code_is_found(self):
        for text in ("a \\md{x}", "\\textbf{\\md {x}}", "\\begin{md}\nx\n\\end{md}"):
            self.assertTrue(pdfmd.md_macro_in(text), text)

    def test_code_other_commands_and_own_definitions_are_not(self):
        for text in ("`\\md{x}`", "```\n\\md{x}\n```", "\\mdseries{x}", "\\mathbf{x}", "nothing",
                     "\\newcommand{\\md}[1]{#1} \\md{x}", "\\def\\md#1{#1} \\md{x}", "\\newenvironment{md}{}{}\n\\begin{md}\\end{md}"):
            self.assertFalse(pdfmd.md_macro_in(text), text)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Build(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "refs.bib").write_text(BIB, encoding="utf-8")

    def build(self, body: str, to: str = "tex", options: str = "", front: bool = True, extra: tuple[str, ...] = ()):
        head = f"pdfmd-options: {{{options}}}\n" if options else ""
        text = f"---\ntitle: T\n{head}---\n\n{body}" if front else body
        (self.root / "d.md").write_text(text, encoding="utf-8")
        out = self.root / f"out.{to}"
        out.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *extra, "--to", to, "-o", out.name, "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        return done, (out.read_text(encoding="utf-8") if out.exists() else "")

    def test_inline_inside_another_raw_command(self):
        done, tex = self.build("A \\textbf{\\md{**b** and $x^2$ and 50\\% \\{a\\}}} end.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("\\textbf{\\textbf{b} and \\(x^2\\) and 50\\% \\{a\\}}", tex)
        self.assertNotIn("\\md", tex)

    def test_places_a_user_would_write_it(self):
        body = ("# Head \\md{with *em*}\n\n\\md{Alone *on* a line.}\n\n- item \\md{in *list*}\n\n| a | b |\n|---|---|\n| \\md{*cell*} | x |\n")
        done, tex = self.build(body)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(tex, r"Head with\s+\\emph\{em\}")           # Pandoc before 3.1.7 wraps the line inside \texorpdfstring
        for expected in ("Alone \\emph{on} a line.", "item in \\emph{list}", "\\emph{cell} & x"):
            self.assertIn(expected, tex)
        self.assertNotIn("\\md", tex)

    def test_inside_a_raw_block_for_latex_and_dropped_scaffold_for_html(self):
        body = "\\begin{tabular}{ll}\na & \\md{*it* b} \\\\\n\\end{tabular}\n"
        done, tex = self.build(body)
        self.assertIn("\\begin{tabular}{ll}\na & \\emph{it} b \\\\\n\\end{tabular}", tex)
        done, html = self.build(body, "html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("tabular", html)
        self.assertNotIn("\\md", html)

    def test_environment_gives_real_blocks_for_every_writer(self):
        body = "\\begin{md}\nText with *em*.\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\\end{md}\n"
        for to, marks in (("tex", ("\\emph{em}", "\\begin{itemize}", "longtable")), ("html", ("<em>em</em>", "<li>one</li>", "<td>1</td>")),
                          ("typ", ("#emph[em]", "table(")), ("md", ("*em*", "one"))):
            done, text = self.build(body, to)
            self.assertEqual(done.returncode, 0, to + done.stdout + done.stderr)
            for mark in marks:
                self.assertIn(mark, text, to)
            self.assertNotIn("begin{md}", text, to)

    def test_environment_inside_a_raw_environment(self):
        done, tex = self.build("\\begin{center}\n\\begin{md}\nInside *center*.\n\\end{md}\n\\end{center}\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(tex, r"\\begin\{center\}\s+Inside \\emph\{center\}\.\s+\\end\{center\}")

    def test_citation_inside_the_macro_is_resolved_and_listed(self):
        body = "A \\textbf{\\md{cited [@smith2020]}} and\n\n\\begin{tabular}{l}\n\\md{again [@smith2020]} \\\\\n\\end{tabular}\n\n# References\n"
        done, tex = self.build(body, "html", extra=("--bibliography", "refs.bib"))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Smith", tex)
        self.assertIn('id="ref-smith2020"', tex)
        self.assertNotIn("[@smith2020]", tex)

    def test_a_file_without_front_matter_gets_the_markdown_reader(self):
        done, tex = self.build("Plain \\textbf{\\md{*em* $x^2$}} text.\n", front=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("\\textbf{\\emph{em} \\(x^2\\)}", tex)

    def test_off_leaves_the_macro_for_latex(self):
        done, tex = self.build("A \\textbf{\\md{*em*}} b.\n", options="md-macro: off")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("\\md{*em*}", tex)

    def test_a_bad_word_stops_the_build(self):
        done, _ = self.build("\\md{x}\n", options="md-macro: maybe")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("md-macro", done.stdout + done.stderr)

    def test_a_document_that_defines_md_itself_keeps_it(self):
        done, tex = self.build("\\newcommand{\\md}[1]{[#1]}\n\nA \\md{*em*} b.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("A [*em*] b.", tex)                   # Pandoc applies the document's own macro; pdfmd stays out of it
        self.assertNotIn("\\emph{em}", tex)
        self.assertIn("defined by the document itself", done.stdout + done.stderr)

    def test_unbalanced_brace_is_kept_with_a_warning(self):
        done, tex = self.build("A \\md{open {brace} b.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("md\\{open", tex)
        self.assertIn("braces do not balance", done.stdout + done.stderr)

    def test_a_command_that_only_starts_with_md_is_not_touched(self):
        done, tex = self.build("A {\\mdseries bold} b.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("\\mdseries", tex)


if __name__ == "__main__":
    unittest.main()
