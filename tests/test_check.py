"""`pdfmd --check`: the Markdown linter (v3.26.15)."""

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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd_check  # noqa: E402
from pdfmd_check import Bibliography, Source, lint  # noqa: E402
from pdfmd_check.lint import heading_identifiers  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402


def codes(text: str, bibliography=None, folder: Path | None = None, **extra) -> list[str]:
    return [problem.code for problem in lint([Source("doc.md", folder, text)], bibliography, **extra)]


class Reading(unittest.TestCase):
    def test_a_clean_document_has_no_problems(self):
        text = "---\ntitle: T\n---\n\n# One {#one}\n\nText [link](#one) and [site](https://x.org/@user).\n\n## Two\n\nMore.\n"
        self.assertEqual(codes(text), [])

    def test_code_comments_and_math_are_not_read(self):
        text = ("# A\n\n```python\n@decorator\n![x](nope.png) [l](#zzz)\n```\n\n`![x](nope.png)` and `@cite`\n\n"
                "<!-- ![x](nope.png) @gone -->\n\n$a[b](c) @d$ and $$x_{[1]}(y) @e$$\n\n"
                "Mail me@x.org, \\@ifnextchar, https://m.example/@someone and <https://m.example/@other>.\n"
                "\\newcommand{\\a}[1]{\\b{#1}}\n")
        self.assertEqual(codes(text, Bibliography(True, frozenset(), True)), [])

    def test_inline_code_across_a_line_break(self):
        self.assertEqual(codes("# A\n\nThe `$for(a)$$a.b$\nand `$x` text, $$ is fine\n"), ["math-open"])
        self.assertEqual(codes("# A\n\nWrap `code $$\nacross` lines.\n"), [])

    def test_things_never_closed(self):
        self.assertEqual(codes("# A\n\n```\nopen\n"), ["fence-open"])
        self.assertEqual(codes("# A\n\ntext <!-- never\n\nmore\n"), ["comment-open"])
        self.assertEqual(codes("# A\n\n::: note\ntext\n"), ["div-open"])
        self.assertEqual(codes("# A\n\ntext\n:::\n"), ["div-stray"])
        self.assertEqual(codes("# A\n\n::: {.a}\n::: {.b}\nx\n:::\n:::\n"), [])

    def test_front_matter(self):
        self.assertEqual(codes("---\ntitle: [unclosed\n---\n\n# A\n"), ["front-matter"])
        self.assertEqual(codes("---\ntitle: T\nauthor: X\n\n# A\n"), ["front-matter"])
        self.assertEqual(codes("---\ntitle: T\ntitle: U\n---\n\n# A\n"), ["front-matter-duplicate"])
        self.assertEqual(codes("---\n\n# A\n\ntext\n"), [])                 # a rule, not metadata
        problem = lint([Source("d.md", None, "---\ntitle: T\nbad: [x\n---\n\n# A\n")])[0]
        self.assertEqual((problem.line, problem.severity), (3, "error"))

    def test_headings(self):
        self.assertEqual(codes("# A\n\n### C\n"), ["heading-jump"])
        self.assertEqual(codes("## A\n\n### B\n\n# C\n\n## D\n"), [])
        self.assertEqual(codes("# A\n\n#B\n"), ["heading-space"])
        self.assertEqual(codes("# A\n\n##\n"), ["heading-empty"])
        self.assertEqual(codes("A\n=\n\nB\n-\n\n#### D\n"), ["heading-jump"])         # setext headings count

    def test_ids_and_anchors(self):
        text = "# Intro {#a}\n\n## Intro\n\n## Intro\n\n[x](#a) [y](#intro) [z](#intro-1) [w](#intro-2) [v](#missing)\n"
        found = lint([Source("d.md", None, text)])
        self.assertEqual([problem.code for problem in found], ["anchor-missing"])
        self.assertIn("missing", found[0].message)
        self.assertEqual(codes("# A {#x}\n\n## B {#x .c}\n"), ["id-duplicate"])
        self.assertEqual(codes("# A\n\n`{#x}` and {#1} and \\textbf{#1}.\n\n{#1}\n"), [])
        self.assertEqual(codes("# The $\\alpha$ decay\n\n[x](#the-alpha-decay)\n"), [])         # math is part of the id

    def test_crossref_and_latex_refs(self):
        text = "# A\n\n![cap](a.png){#fig:one}\n\nSee @fig:one, @fig:two and \\ref{eq:e}.\n\n\\begin{equation}\\label{eq:e}\\end{equation}\n"
        found = lint([Source("d.md", None, text)])
        self.assertEqual([problem.code for problem in found if problem.code != "image-missing"], ["crossref-missing"])
        self.assertEqual(codes("# A\n\n\\ref{nowhere}\n"), ["ref-missing"])
        self.assertEqual(codes("# A {#sec:a}\n\n@sec:a\n"), [])

    def test_footnotes(self):
        self.assertEqual(codes("# A\n\nx[^1] y[^2]\n\n[^1]: one\n[^3]: three\n"), ["footnote-missing", "footnote-unused"])
        self.assertEqual(codes("# A\n\nx[^n] and ^[inline note].\n\n[^n]: text with @k\n", Bibliography(True, frozenset({"k"}))), [])

    def test_citations(self):
        bibliography = Bibliography(True, frozenset({"smith2020", "lee"}), True)
        found = lint([Source("d.md", None, "# A\n\n[@smith2020; @gone] and @gone again, [@Lee], \\cite{lee,zed}.\n")], bibliography)
        self.assertEqual([problem.code for problem in found], ["cite-missing", "cite-missing"])
        self.assertIn("2 uses", found[0].message)
        self.assertEqual(codes("# A\n\n[@x]\n", Bibliography(False)), ["cite-no-bibliography"])
        self.assertEqual(codes("# A\n\n[@x]\n", Bibliography(True, frozenset(), complete=False)), [])    # a kind of file not read
        self.assertEqual(codes("# A\n\n[@x]\n", None), [])
        self.assertEqual(codes("# A\n\n---\nnocite: |\n  @*\n---\n", Bibliography(True, frozenset(), True)), [])

    def test_files_that_must_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "a.png").write_bytes(b"x")
            (base / "plots").mkdir()
            (base / "plots" / "b.pdf").write_bytes(b"x")
            (base / "d.csv").write_text("a,b\n1,2\n")
            text = ("# A\n\n![ok](a.png) ![ok2](plots/b) ![no](c.png) ![web](https://x.org/y.png) ![d](data:image/png;base64,xx)\n"
                    "![sp](a%20b.png)\n\n\\includegraphics[width=2cm]{plots/b} \\includegraphics{zz}\n\n"
                    '[ok](d.csv) [no](nothing.pdf) [mail](mailto:a@b.c) [dir](plots)\n\n::: {.csv file="d.csv"}\n:::\n\n'
                    '::: {.csv file="gone.csv"}\n:::\n')
            found = lint([Source("d.md", base, text)])
            self.assertEqual(sorted(problem.code for problem in found),
                             ["file-missing", "image-missing", "image-missing", "image-missing", "link-missing"])

    def test_ignore(self):
        text = "# A\n\n### C\n"
        self.assertEqual(codes(text, ignore=frozenset({"heading-jump"})), [])
        self.assertEqual(codes("# A\n\n<!-- pdfmd-check: ignore heading-jump -->\n### C\n"), [])
        self.assertEqual(codes("# A\n\n![x](gone.png) <!-- pdfmd-check: ignore -->\n"), [])
        self.assertEqual(codes("# A\n\n<!-- pdfmd-check: ignore heading-jump -->\n![x](gone.png)\n"), ["image-missing"])
        self.assertEqual(pdfmd_check.parse_ignore(["heading-jump,div-open", "math-open"]),
                         frozenset({"heading-jump", "div-open", "math-open"}))
        with self.assertRaises(ValueError):
            pdfmd_check.parse_ignore("nope")

    def test_a_scaffold_and_its_parts_are_one_document(self):
        sources = [Source("book.md", None, "---\ntitle: B\n---\n\nSee [m](#methods) and @fig:p and [^n].\n"),
                   Source("parts/1.md", None, "# Methods\n\n![p](x.png){#fig:p}\n\n[^n]: note\n")]
        self.assertEqual([problem.code for problem in lint(sources) if problem.code != "image-missing"], [])
        sources[1].text = sources[1].text.replace("{#fig:p}", "")
        self.assertEqual([(problem.file, problem.code) for problem in lint(sources)],
                         [("book.md", "crossref-missing"), ("parts/1.md", "image-missing")])

    def test_every_code_has_a_severity_and_text(self):
        for code, (severity, text) in pdfmd_check.CODES.items():
            self.assertIn(severity, ("error", "warning"), code)
            self.assertTrue(text, code)

    @needs_pandoc(3, 1, 3)
    def test_heading_ids_are_the_ones_pandoc_makes(self):
        headings = ["Results & Discussion", "A - B", "2. Methods", "Café au lait", "snake_case_name", "Dry  run",
                    "What's new?", "The `code` and *emphasis*", "x.y.z version", "Über uns", "100% sure"]
        text = "\n\n".join(f"## {heading}" for heading in headings) + "\n"
        done = subprocess.run(["pandoc", "-f", "markdown", "-t", "html"], input=text, capture_output=True, text=True,
                              encoding="utf-8")
        made = re.findall(r'<h2 id="([^"]*)"', done.stdout)
        self.assertEqual(len(made), len(headings))
        for heading, identifier in zip(headings, made):
            self.assertIn(identifier, heading_identifiers(heading), heading)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-check-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"],
                       "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=environment)

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_report_and_exit_code(self):
        self.write("doc.md", "---\ntitle: T\n---\n\n# A\n\n![x](gone.png)\n\n### C\n")
        done = self.run_pdfmd("doc.md", "--check")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("doc.md:7: error: image not found: gone.png  [image-missing]", done.stdout)
        self.assertIn("doc.md:9: warning: heading level 1 is followed by level 3", done.stdout)
        self.assertIn("CHECK  doc.md: 1 error(s), 1 warning(s)", done.stdout)
        self.assertFalse((self.directory / "doc.pdf").exists())                       # nothing is built

    def test_clean_and_warnings_only(self):
        self.write("doc.md", "# A\n\n### C\n")
        done = self.run_pdfmd("doc", "--check")
        self.assertEqual(done.returncode, 0)
        self.assertIn("CHECK  doc.md: 1 warning(s)", done.stdout)
        self.assertEqual(self.run_pdfmd("doc", "--check", "--strict").returncode, 1)       # --strict: a warning fails
        self.assertEqual(self.run_pdfmd("doc", "--check", "--check-ignore", "heading-jump").returncode, 0)
        clean = self.run_pdfmd("doc", "--check", "--check-ignore", "heading-jump")
        self.assertIn("no problems", clean.stdout)

    def test_ignore_in_the_document_and_unknown_codes(self):
        self.write("doc.md", "---\ntitle: T\npdfmd-options:\n  check-ignore: [heading-jump]\n---\n\n# A\n\n### C\n")
        self.assertIn("no problems", self.run_pdfmd("doc.md", "--check").stdout)
        bad = self.run_pdfmd("doc.md", "--check", "--check-ignore", "nonsense")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("unknown check(s): nonsense", bad.stderr)
        self.assertEqual(self.run_pdfmd("doc.md", "--check-ignore", "heading-jump").returncode, 1)     # needs --check

    def test_bibliography_from_front_matter_and_metadata_file(self):
        self.write("refs.bib", "@article{smith2020,\n  title={T}}\n@book{lee1999, title={U}}\n")
        self.write("doc.md", "---\ntitle: T\nbibliography: refs.bib\n---\n\n# A\n\n[@smith2020; @lee1999; @gone]\n")
        done = self.run_pdfmd("doc.md", "--check")
        self.assertIn("doc.md:8: error: @gone is not in the bibliography", done.stdout)
        self.assertNotIn("smith2020", done.stdout)
        self.write("meta.yaml", "bibliography: refs.bib\n")
        self.write("other.md", "---\ntitle: T\n---\n\n# A\n\n[@smith2020; @gone2]\n")
        done = self.run_pdfmd("other.md", "--check", "-y", "meta.yaml")
        self.assertIn("@gone2 is not in the bibliography", done.stdout)
        self.write("json.md", "---\ntitle: T\nbibliography: c.json\n---\n\n# A\n\n[@a1; @b2]\n")
        self.write("c.json", '[{"id": "a1", "title": "x"}]')
        self.assertIn("@b2 is not in", self.run_pdfmd("json.md", "--check").stdout)
        self.write("inline.md", "---\ntitle: T\nreferences:\n- id: k1\n  title: x\n---\n\n# A\n\n[@k1; @k2]\n")
        self.assertIn("@k2 is not in", self.run_pdfmd("inline.md", "--check").stdout)

    def test_missing_bibliography_file_and_unknown_kinds(self):
        self.write("doc.md", "---\ntitle: T\nbibliography: nothere.bib\n---\n\n# A\n\n[@a]\n")
        done = self.run_pdfmd("doc.md", "--check")
        self.assertIn("doc.md:3: error: bibliography file not found: nothere.bib  [bibliography-missing]", done.stdout)
        self.assertNotIn("cite-missing", done.stdout)
        self.write("ris.md", "---\ntitle: T\nbibliography: refs.ris\n---\n\n# A\n\n[@a]\n")
        self.write("refs.ris", "TY  - JOUR\n")
        self.assertIn("no problems", self.run_pdfmd("ris.md", "--check").stdout)

    def test_a_scaffold_is_checked_with_its_parts(self):
        self.write("book.md", "---\ntitle: B\npdfmd-options:\n  parts: true\n---\n\nSee [m](#methods).\n")
        self.write("parts/10-intro.md", "# Intro\n\n![x](gone.png)\n")
        self.write("parts/20-methods.md", "# Methods\n\nText.\n")
        done = self.run_pdfmd("book.md", "--check")
        self.assertIn("CHECK  book.md and 2 part(s): 1 error(s)", done.stdout)
        self.assertRegex(done.stdout, r"parts[\\/]10-intro\.md:3: error: image not found: gone\.png")
        self.assertNotIn("anchor-missing", done.stdout)                                  # #methods is in another part

    def test_not_markdown_and_not_found(self):
        self.write("a.tex", "x")
        done = self.run_pdfmd("a.tex", "--check")
        self.assertEqual(done.returncode, 1)
        self.assertIn("reads Markdown", done.stderr)
        self.assertEqual(self.run_pdfmd("nothing", "--check").returncode, 1)

    def test_several_files(self):
        self.write("a.md", "# A\n")
        self.write("b.md", "# B\n\n![x](no.png)\n")
        done = self.run_pdfmd("a.md", "b.md", "--check")
        self.assertEqual(done.returncode, 1)
        self.assertIn("CHECK  a.md: no problems", done.stdout)
        self.assertIn("CHECK  b.md: 1 error(s)", done.stdout)


if __name__ == "__main__":
    unittest.main()
