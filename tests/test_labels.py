"""Cross-references of a part built alone, counted from the sources (v3.26.0): the pdfmd_labels scanner and the TeX it
renders are pure and tested on fixed LaTeX; the end-to-end tests (Pandoc and LuaLaTeX) build a part and compare its
references with the full build's."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402
import pdfmd_labels  # noqa: E402
from pdfmd_labels.scan import Event, scan  # noqa: E402

WRAP = "\\documentclass{article}\n\\newcommand{\\gone}{\\section{in preamble}\\label{gone}}\n\\begin{document}\n%s\n\\end{document}\n"


def kinds(text):
    return [(event.kind, event.arg) for event in scan(WRAP % text).events]


class Scanner(unittest.TestCase):
    def test_numbered_headings_and_labels_in_order(self):
        self.assertEqual(kinds("\\section{A}\\label{sec:a}\n\\subsection{B}\\label{sec:b}"),
                         [("sec", "section"), ("lab", "sec:a"), ("sec", "subsection"), ("lab", "sec:b")])

    def test_a_starred_heading_does_not_step(self):
        self.assertEqual(kinds("\\section*{A}\\label{x}"), [("lab", "x")])

    def test_the_levels_are_reported_for_secnumdepth(self):
        events = scan(WRAP % "\\chapter{A}\\section{B}\\paragraph{C}").events
        self.assertEqual([(event.arg, event.level) for event in events],
                         [("chapter", 0), ("section", 1), ("paragraph", 4)])

    def test_a_caption_steps_the_counter_of_its_float(self):
        text = ("\\begin{figure}\\caption{F}\\label{fig:f}\\end{figure}\n"
                "\\begin{longtable}[]{@{}ll@{}}\\caption{T}\\label{tbl:t}\\tabularnewline\\end{longtable}")
        self.assertEqual(kinds(text), [("step", "figure"), ("lab", "fig:f"), ("step", "table"), ("lab", "tbl:t")])

    def test_a_caption_outside_a_known_float_is_not_counted(self):
        self.assertEqual(kinds("\\begin{mybox}\\caption{F}\\end{mybox}"), [])

    def test_captionof_names_its_counter(self):
        self.assertEqual(kinds("\\captionof{table}{T}\\label{t}"), [("step", "table"), ("lab", "t")])

    def test_equation_and_unstarred_align_rows(self):
        self.assertEqual(kinds("\\begin{equation}\\label{e}a\\end{equation}"), [("step", "equation"), ("lab", "e")])
        self.assertEqual(kinds("\\begin{equation*}a\\end{equation*}"), [("step", "equation")][:0])

    def test_each_align_row_steps_once_unless_switched_off(self):
        text = ("\\begin{align}a &= b \\label{r1}\\\\ c &= d \\nonumber \\\\ e &= f \\label{r3} \\\\\n\\end{align}")
        self.assertEqual(kinds(text), [("step", "equation"), ("lab", "r1"), ("step", "equation"), ("lab", "r3")])

    def test_align_without_labels_counts_its_rows(self):
        self.assertEqual(kinds("\\begin{align}a\\\\b\\\\c\\end{align}"), [("step", "equation")] * 3)

    def test_a_row_break_inside_a_nested_environment_is_not_a_row(self):
        text = "\\begin{align}x = \\begin{cases} 1 \\\\ 2 \\end{cases}\\label{c}\\end{align}"
        self.assertEqual(kinds(text), [("step", "equation"), ("lab", "c")])

    def test_comments_code_and_definitions_are_skipped(self):
        text = ("% \\section{commented}\n50\\% of \\section{kept}\n"
                "\\begin{verbatim}\\section{no}\\label{no}\\end{verbatim}\n"
                "\\newcommand{\\mine}[1]{\\section{#1}\\label{inside}}\n"
                "\\def\\other{\\label{inside2}}\n\\section{after}")
        self.assertEqual(kinds(text), [("sec", "section"), ("sec", "section")])

    def test_the_preamble_is_not_scanned(self):
        self.assertEqual(kinds(""), [])

    def test_appendix_footnotes_and_parts(self):
        self.assertEqual(kinds("\\pdfmdpart{10-a.md}\\appendix\\footnote{x}\\footnotemark"),
                         [("part", "10-a.md"), ("app", ""), ("step", "footnote")])

    def test_counts(self):
        result = scan(WRAP % "\\section{A}\\label{a}\\begin{figure}\\caption{F}\\label{f}\\end{figure}\\pdfmdpart{k}")
        self.assertEqual((result.labels, result.steps, result.parts()), (2, 2, 1))


class Rendering(unittest.TestCase):
    def test_the_seed_runs_the_events_at_the_start_of_the_document(self):
        text = pdfmd_labels.render(scan(WRAP % "\\section{A}\\label{sec:a}\\pdfmdpart{p}"))
        for needle in ("\\pdfmd@ev@sec{section}{1}", "\\pdfmd@ev@lab{sec:a}", "\\pdfmd@ev@part{p}",
                       "\\AtBeginDocument{\\pdfmd@replay{pdfmd@events}}", "\\providecommand\\pdfmd@seed"):
            self.assertIn(needle, text)

    def test_the_replay_defines_only_the_undefined_and_restores_the_counters(self):
        text = pdfmd_labels.REPLAY_DEFS
        self.assertIn("@ifundefined{r@#1}", text)
        self.assertIn("\\cl@@ckpt", text)


class Mode(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.document = self.root / "doc.md"
        self.document.write_text("# A\n", encoding="utf-8")
        patcher = mock.patch.object(pdfmd, "SEED_LABELS_CLI", None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_is_auto(self):
        self.assertEqual(pdfmd.seed_labels_mode(self.document, []), "auto")

    def test_the_front_matter_chooses(self):
        self.document.write_text("---\npdfmd-options:\n  seed-labels: scan\n---\n# A\n", encoding="utf-8")
        self.assertEqual(pdfmd.seed_labels_mode(self.document, []), "scan")

    def test_yaml_off_is_a_boolean_and_means_off(self):
        self.document.write_text("---\npdfmd-options:\n  seed-labels: off\n---\n# A\n", encoding="utf-8")
        self.assertEqual(pdfmd.seed_labels_mode(self.document, []), "off")

    def test_a_wrong_value_names_the_valid_ones(self):
        self.document.write_text("---\npdfmd-options:\n  seed-labels: sometimes\n---\n# A\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            pdfmd.seed_labels_mode(self.document, [])
        self.assertIn("auto, aux, scan, draft, off", str(caught.exception))

    def test_the_command_line_wins(self):
        self.document.write_text("---\npdfmd-options:\n  seed-labels: scan\n---\n# A\n", encoding="utf-8")
        with mock.patch.object(pdfmd, "SEED_LABELS_CLI", "off"):
            self.assertEqual(pdfmd.seed_labels_mode(self.document, []), "off")


class Wanted(unittest.TestCase):
    def ask(self, mode="auto", target="pdf", engines=("lualatex",), partial=True, parts=False, texts=()):
        return pdfmd.label_scan_wanted(mode, target, list(engines), False, Path("doc.md"), partial, parts, list(texts))

    def test_a_part_of_a_split_document_always(self):
        self.assertTrue(self.ask(parts=True))

    def test_a_section_only_when_it_refers_to_something(self):
        self.assertFalse(self.ask(texts=["plain text"]))
        self.assertTrue(self.ask(texts=["see \\ref{sec:x}"]))
        self.assertTrue(self.ask(texts=["see [@fig:a]"]))
        self.assertTrue(self.ask(texts=["see \\cref{x}"]))

    def test_not_for_a_full_build_other_modes_or_engines_without_tex(self):
        self.assertFalse(self.ask(partial=False, parts=True))
        self.assertFalse(self.ask(mode="off", parts=True))
        self.assertFalse(self.ask(mode="aux", parts=True))
        self.assertFalse(self.ask(engines=("weasyprint",), parts=True))
        self.assertFalse(self.ask(target="docx", parts=True))
        self.assertFalse(self.ask(target="latex", parts=True))        # a .tex handed over stays plain


class Wrapping(unittest.TestCase):
    def test_a_part_is_a_fenced_div_marked_yes_or_no(self):
        text = pdfmd.wrap_part("# A\n\ntext\n", True)
        self.assertTrue(text.startswith(':::::::'))
        self.assertIn('pdfmd-keep="yes"', text)
        self.assertIn('pdfmd-keep="no"', pdfmd.wrap_part("x", False))

    def test_runs_mark_only_the_kept_lines(self):
        text = pdfmd.wrap_runs("# A\na\n# B\nb\n# C\nc", [(2, 4)])
        self.assertEqual(text.count("pdfmd-part"), 3)
        order = re.findall(r'pdfmd-keep="(yes|no)"', text)
        self.assertEqual(order, ["no", "yes", "no"])
        kept = text.split('pdfmd-keep="yes"}')[1].split(":::::::")[0]
        self.assertIn("# B", kept)
        self.assertNotIn("# A", kept)
        self.assertNotIn("# C", kept)

    def test_select_wanted_is_for_the_writers_that_are_not_latex(self):
        ask = lambda target, engines=("lualatex",): pdfmd.select_wanted("auto", target, list(engines), False, Path("d.md"))
        self.assertTrue(ask("html"))
        self.assertTrue(ask("docx"))
        self.assertTrue(ask("typst"))
        self.assertTrue(ask("pdf", ("weasyprint",)))
        self.assertFalse(ask("pdf", ("lualatex",)))
        self.assertFalse(ask("pdf", ("inkmd",)))
        self.assertFalse(ask("latex"))
        self.assertFalse(pdfmd.select_wanted("off", "html", [], False, Path("d.md")))
        self.assertFalse(pdfmd.select_wanted("aux", "html", [], False, Path("d.md")))


NEEDS = unittest.skipUnless(shutil.which("pandoc") and shutil.which("lualatex") and shutil.which("pdftotext"),
                            "needs Pandoc, LuaLaTeX and pdftotext")


@NEEDS
class PartsBuild(unittest.TestCase):
    """report#method built alone, with no cache and no earlier full build, shows the full build's numbers."""

    UNDEFINED = re.compile(r"Reference `[^']*' on page \d+ undefined")

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name).resolve()
        cache = self.root / "cache"
        self.environment = {**os.environ, "XDG_CACHE_HOME": str(cache), "LOCALAPPDATA": str(cache)}
        (self.root / "parts").mkdir()
        (self.root / "report.md").write_text("---\ntitle: Demo\nnumbersections: true\npdfmd-options:\n  parts: auto\n---\n",
                                             encoding="utf-8")
        (self.root / "parts" / "10-intro.md").write_text(
            "# Intro {#sec:intro}\n\nSee Section \\ref{sec:method}, Equation \\ref{eq:b}.\n\n"
            "\\begin{equation}\\label{eq:a} a=1 \\end{equation}\n", encoding="utf-8")
        (self.root / "parts" / "20-method.md").write_text(
            "# Method {#sec:method}\n\nBack to Section \\ref{sec:intro}, Equation \\ref{eq:a}, Subsection \\ref{sec:sub} "
            "and Section \\ref{sec:end}.\n\n\\begin{equation}\\label{eq:b} b=2 \\end{equation}\n\n"
            "## Sub {#sec:sub}\n\nText.\n", encoding="utf-8")
        (self.root / "parts" / "30-end.md").write_text("# End {#sec:end}\n\nSee Equation \\ref{eq:b}.\n", encoding="utf-8")

    def build(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments, "-e", "lualatex"],
                              cwd=self.root, env=self.environment, capture_output=True, text=True)

    def text(self, name):
        done = subprocess.run(["pdftotext", "-layout", str(self.root / name), "-"], capture_output=True, text=True)
        return re.sub(r"\s+", " ", done.stdout)

    def test_a_part_alone_prints_the_numbers_of_the_full_build(self):
        self.assertEqual(self.build("report").returncode, 0)
        full = self.text("report.pdf")
        self.assertIn("Back to Section 1, Equation 1, Subsection 2.1 and Section 3", full)
        result = self.build("report#method")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("counted from the sources", result.stdout)
        part = self.text("report.method.pdf")
        self.assertIn("Back to Section 1, Equation 1, Subsection 2.1 and Section 3", part)
        self.assertNotIn("??", part)
        self.assertRegex(part, r"2 Method")                    # its own number continues from the part before it
        self.assertRegex(part, r"\(2\)")                       # and so does the equation

    def test_the_draft_pass_gives_the_exact_numbers(self):
        result = self.build("report#method", "--seed-labels", "draft")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("draft pass", result.stdout)
        part = self.text("report.method.pdf")
        self.assertIn("Back to Section 1, Equation 1, Subsection 2.1 and Section 3", part)
        self.assertNotIn("??", part)

    def test_off_leaves_the_question_marks(self):
        result = self.build("report#method", "--seed-labels", "off")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("??", self.text("report.method.pdf"))
        self.assertNotIn("counted from the sources", result.stdout)

    def test_the_scan_fills_in_what_the_cached_aux_does_not_know(self):
        self.assertEqual(self.build("report", "--cache").returncode, 0)
        (self.root / "parts" / "30-end.md").write_text(
            "# End {#sec:end}\n\nSee Equation \\ref{eq:b}.\n\n# Later {#sec:later}\n\nText.\n", encoding="utf-8")
        (self.root / "parts" / "20-method.md").write_text(
            "# Method {#sec:method}\n\nBack to Section \\ref{sec:later}.\n", encoding="utf-8")
        result = self.build("report#method", "--cache")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("??", self.text("report.method.pdf"))
        self.assertIn("Back to Section 4", self.text("report.method.pdf"))


@NEEDS
class SectionBuild(unittest.TestCase):
    def test_a_section_of_an_ordinary_document_resolves_its_references_without_a_full_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "doc.md").write_text(
                "---\ntitle: S\nnumbersections: true\n---\n\n# Setup {#sec:setup}\n\nText.\n\n"
                "# Results {#sec:results}\n\nBack to Section \\ref{sec:setup}.\n\n# End\n\nBye.\n", encoding="utf-8")
            cache = root / "cache"
            environment = {**os.environ, "XDG_CACHE_HOME": str(cache), "LOCALAPPDATA": str(cache)}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc#results", "-e", "lualatex"],
                                  cwd=root, env=environment, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            text = subprocess.run(["pdftotext", str(root / "doc.results.pdf"), "-"], capture_output=True, text=True).stdout
            self.assertIn("Back to Section 1", text)
            self.assertNotIn("??", text)


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("pandoc-crossref"), "needs Pandoc and pandoc-crossref")
class WholeNumbering(unittest.TestCase):
    """HTML, Word, Typst: the whole document is numbered by pandoc-crossref and the part kept (select.lua)."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name).resolve()
        (self.root / "parts").mkdir()
        (self.root / "report.md").write_text("---\ntitle: Demo\npdfmd-options:\n  parts: auto\n---\n", encoding="utf-8")
        (self.root / "parts" / "10-intro.md").write_text("# Intro {#sec:intro}\n\nSee [@sec:method].\n", encoding="utf-8")
        (self.root / "parts" / "20-method.md").write_text(
            "# Method {#sec:method}\n\nBack to [@sec:intro] and [@sec:end].\n\n## Sub {#sec:sub}\n\nText.\n",
            encoding="utf-8")
        (self.root / "parts" / "30-end.md").write_text("# End {#sec:end}\n\nLast [@sec:method].\n", encoding="utf-8")

    def build(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments, "--number-sections"],
                              cwd=self.root, capture_output=True, text=True)

    def test_a_part_keeps_the_numbers_and_references_of_the_whole_document(self):
        result = self.build("report#method", "-t", "html", "-o", "m.html")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        html = (self.root / "m.html").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'data-number="([^"]*)" id="([^"]*)"', html),
                         [("2", "sec:method"), ("2.1", "sec:sub")])
        text = re.sub(r"<[^>]*>", "", html).replace("\xa0", " ")
        self.assertIn("Back to sec. 1 and sec. 3.", text)
        self.assertNotIn("Intro", text)
        self.assertNotIn("pdfmd-part", html)

    def test_several_parts_in_the_documents_order(self):
        result = self.build("report#end+method", "-t", "html", "-o", "m.html")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        html = (self.root / "m.html").read_text(encoding="utf-8")
        self.assertEqual([number for number, _ in re.findall(r'data-number="([^"]*)" id="([^"]*)"', html)],
                         ["2", "2.1", "3"])

    def test_typst_gets_a_heading_counter_before_a_kept_heading(self):
        result = self.build("report#end", "-t", "typst", "-o", "e.typ")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("#counter(heading).update((2,))", (self.root / "e.typ").read_text(encoding="utf-8"))

    def test_a_full_build_is_untouched(self):
        result = self.build("report", "-t", "html", "-o", "f.html")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("pdfmd-part", (self.root / "f.html").read_text(encoding="utf-8"))

    def test_a_section_of_an_ordinary_document(self):
        (self.root / "doc.md").write_text(
            "---\ntitle: D\n---\n\n# One {#sec:one}\n\nText.\n\n# Two {#sec:two}\n\nBack to [@sec:one].\n\n# Three\n\nBye.\n", encoding="utf-8")
        result = self.build("doc#two", "-t", "html", "-o", "d.html")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        html = (self.root / "d.html").read_text(encoding="utf-8")
        self.assertIn('data-number="2"', html)
        self.assertIn("sec. 1", re.sub(r"<[^>]*>", "", html).replace("\xa0", " "))


if __name__ == "__main__":
    unittest.main()
