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
from env_support import hidden_tools  # noqa: E402


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
            self.assertIn(severity, ("error", "warning", "note"), code)
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


class CalcNames(unittest.TestCase):
    """What the calculator's filter reports about names (pdfmd_lua/calc.lua in check mode) is put on the lines that hold them."""

    REPORT = Source("report.md", None, "---\ntitle: R\n---\n\nIntro `V = 2 + 2`{=} and `W = V * y`{=} and `V = 5`{=}.\n")
    PART_A = Source("parts/10-a.md", None, "# A\n\n::: calc\nRun 1: A = V * zz = {ans:2dp} mL.\n\nV = 7 = {ans}\n:::\n")
    PART_B = Source("parts/60-b.md", None, "# B\n\n```{=calc}\nq = 3\n```\n\n```python\nW = V * y\n```\n\nSo `a + b = {ans}`{=} and `V = 5`{=}.\n")

    def found(self, sources, uses, definitions, ignore=frozenset()):
        return [(problem.file, problem.line, problem.severity, problem.code)
                for problem in lint(sources, calc=(uses, definitions), ignore=ignore)]

    def test_a_use_of_an_undefined_name_is_on_its_line_in_its_part(self):
        uses = [("y", "W = V * y"), ("zz", "Run 1: A = V * zz = {ans:2dp}"), ("a", "a + b = {ans}"), ("b", "a + b = {ans}")]
        problems = [problem for problem in lint([self.REPORT, self.PART_A, self.PART_B], calc=(uses, []))]
        self.assertEqual([(problem.file, problem.line, problem.code) for problem in problems],
                         [("report.md", 5, "calc-undefined"), ("parts/10-a.md", 4, "calc-undefined"),
                          ("parts/60-b.md", 11, "calc-undefined"), ("parts/60-b.md", 11, "calc-undefined")])     # (not the line in the python fence)
        self.assertIn("'y' is not defined for the calculator; give it a value with `y = 2 + 2`{=} somewhere (used in `W = V * y`)",
                      problems[0].message)
        self.assertEqual({problem.severity for problem in problems}, {"error"})
        self.assertTrue(problems[2].message.startswith("'a' ") and problems[3].message.startswith("'b' "))   # one statement, two names

    def test_the_same_text_in_two_places_is_two_places(self):
        source = Source("r.md", None, "`x * 2`{=}\n\ntext\n\n`x * 2`{=}\n")
        found = self.found([source], [("x", "x * 2"), ("x", "x * 2")], [])
        self.assertEqual([line for _, line, _, _ in found], [1, 5])

    def test_a_name_defined_several_times_is_a_note_that_says_where_and_which_one_a_use_sees(self):
        definitions = [("V", "V = 2 + 2", "document"), ("V", "V = 5", "document"), ("V", "V = 7 = {ans}", "document"),
                       ("V", "V = 5", "document")]
        [problem] = lint([self.REPORT, self.PART_A, self.PART_B], calc=([], definitions))
        self.assertEqual((problem.file, problem.line, problem.severity, problem.code), ("report.md", 5, "note", "calc-redefined"))
        self.assertEqual(problem.message, "V is defined 4 times (report.md: line 5 (x2); parts/10-a.md: line 6; parts/60-b.md: line 11); "
                                          "a use below them sees the last one (parts/60-b.md: line 11)")

    def test_constants_count_and_a_name_only_there_is_not_reported(self):
        [problem] = lint([self.REPORT], calc=([], [("V", "V = 1", "constants"), ("V", "V = 2 + 2", "document")]))
        self.assertIn("V is defined 2 times (the constants file; report.md: line 5)", problem.message)
        self.assertEqual(lint([self.REPORT], calc=([], [("V", "V = 1", "constants"), ("V", "V = 2", "constants")])), [])

    def test_the_ignore_codes_and_the_directive_work_for_them_too(self):
        uses = [("y", "W = V * y")]
        self.assertEqual(self.found([self.REPORT], uses, [], frozenset({"calc-undefined"})), [])
        silenced = Source("r.md", None, "<!-- pdfmd-check: ignore calc-undefined -->\n`W = V * y`{=}\n")
        self.assertEqual(self.found([silenced], uses, []), [])
        self.assertEqual(len(self.found([Source("r.md", None, "`W = V * y`{=}\n")], uses, [])), 1)

    def test_a_place_that_cannot_be_found_is_still_reported(self):
        [problem] = lint([self.REPORT], calc=([("q", "nowhere to be seen")], []))
        self.assertEqual((problem.file, problem.line, problem.code), ("report.md", 0, "calc-undefined"))


@needs_pandoc(3, 1, 3)
class CalcCheck(unittest.TestCase):
    """`pdfmd FILE --check` on a document with a calculator: Pandoc runs the filter once, only when a calculator is there."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calc-check-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "parts").mkdir()
        (self.directory / "report.md").write_text(
            "---\ntitle: R\npdfmd-options:\n  parts: auto\n---\n\nIntro `V = 2 + 2`{=} and `W = V * y`{=}.\n", encoding="utf-8")
        (self.directory / "parts" / "10-a.md").write_text(
            "# A\n\n::: calc\nRun 1: A = V * zz = {ans:2dp} mL.\n\nV = 7 = {ans}\n:::\n", encoding="utf-8")
        (self.directory / "parts" / "60-b.md").write_text("# B\n\nSo `a + b = {ans}`{=} and `V = 5`{=}.\n", encoding="utf-8")

    def check(self, *arguments, folder=None):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], cwd=folder or self.directory,
                              capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PDFMD_CONFIG": ""})

    def test_undefined_names_and_a_name_defined_often_are_reported_in_document_order(self):
        done = self.check("report.md", "--check")
        lines = done.stdout.replace("\\", "/").splitlines()       # (Windows prints parts\10-a.md)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual([line.split(": ")[0] for line in lines[:-1]],
                         ["report.md:7", "report.md:7", "parts/10-a.md:4", "parts/60-b.md:3", "parts/60-b.md:3"])
        self.assertIn("report.md:7: error: 'y' is not defined for the calculator", lines[0])
        self.assertIn("report.md:7: note: V is defined 3 times (report.md: line 7; parts/10-a.md: line 6; parts/60-b.md: line 3); "
                      "a use below them sees the last one (parts/60-b.md: line 3)  [calc-redefined]", lines[1])
        self.assertIn("parts/10-a.md:4: error: 'zz' is not defined", lines[2])
        self.assertIn("'a' is not defined", lines[3])
        self.assertIn("'b' is not defined", lines[4])
        self.assertEqual(lines[-1], "CHECK  report.md and 2 part(s): 4 error(s), 1 note(s)")

    def test_a_normal_build_says_nothing_about_a_name_that_is_defined_often(self):
        (self.directory / "parts" / "10-a.md").write_text("# A\n\nRun `V = 7`{=}.\n", encoding="utf-8")
        built = self.check("report.md", "--to", "latex", "-o", "out.tex", "--no-backup", "--no-stamp")
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        said = built.stdout + built.stderr
        self.assertNotIn("times", said)                                   # (the WARNs about y, a and b are the build's own, as before)
        self.assertNotIn("redefined", said)
        self.assertNotIn("V is defined", said)

    def test_a_note_alone_does_not_fail_even_with_strict(self):
        (self.directory / "report.md").write_text(
            "---\ntitle: R\npdfmd-options:\n  parts: auto\n---\n\n`V = 2`{=}\n", encoding="utf-8")
        (self.directory / "parts" / "10-a.md").write_text("# A\n\n`V = 3`{=}\n", encoding="utf-8")
        (self.directory / "parts" / "60-b.md").write_text("# B\n\nOK\n", encoding="utf-8")
        done = self.check("report.md", "--check", "--strict")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("1 note(s)", done.stdout)
        self.assertNotIn("error", done.stdout.split("CHECK")[-1])
        ignored = self.check("report.md", "--check", "--check-ignore", "calc-redefined")
        self.assertIn("no problems", ignored.stdout)

    def test_a_document_without_a_calculator_never_starts_pandoc(self):
        (self.directory / "plain.md").write_text("---\ntitle: P\n---\n\nA `code` span and {braces}.\n", encoding="utf-8")
        bin_dir = self.directory / "bin"
        bin_dir.mkdir()
        marker = self.directory / "pandoc-ran"
        wrapper = bin_dir / "pandoc"
        wrapper.write_text(f"#!/bin/sh\ntouch '{marker}'\nexec '{shutil.which('pandoc')}' \"$@\"\n", encoding="utf-8")
        wrapper.chmod(0o755)
        if os.name == "nt":
            self.skipTest("a shell wrapper stands in for Pandoc")
        env = {**os.environ, "PDFMD_CONFIG": "", "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "plain.md", "--check"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertIn("no problems", done.stdout)
        self.assertFalse(marker.exists(), "Pandoc was started for a document with no calculator")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report.md", "--check"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertTrue(marker.exists())                                      # with one it is started once for the whole document
        self.assertEqual(wrapper.read_text().count("touch"), 1)

    def test_calc_off_and_a_missing_pandoc_leave_names_alone(self):
        off = self.check("report.md", "--check", "--no-calc")
        self.assertIn("no problems", off.stdout, off.stdout + off.stderr)
        empty = self.directory / "empty"
        empty.mkdir()
        environment = {**os.environ, "PDFMD_CONFIG": "", "PATH": str(empty), **hidden_tools(empty)}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report.md", "--check"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8", env=environment)
        self.assertIn("NOTE  --check: the names of the calculator are not checked without Pandoc", done.stderr)
        self.assertIn("no problems", done.stdout)



if __name__ == "__main__":
    unittest.main()
