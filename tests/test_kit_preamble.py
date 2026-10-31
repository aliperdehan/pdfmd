"""v3.31.32: kits, C3 (entry 3du, point 9): the preamble a kit writes and the four outcomes where the user's own LaTeX says the
same thing. The resolver is pure (pdfmd_kits.preamble); the builds go through pdfmd itself with a fixture kit."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfmd_kits.preamble import PreambleClash, Source, blank_comments, kit_inputs, package_line, resolve  # noqa: E402

PANDOC = shutil.which("pandoc")
LABEL = "lab 2.0 (mode qca)"


def run(texts, explicit=False, options=("qca",), foreign=("orgchem", "genchem"), inputs=("chemicals",)):
    sources = [Source(f"s{n}", text, explicit) for n, text in enumerate(texts)]
    return resolve(LABEL, "labstyle", tuple(options), frozenset(foreign), frozenset(inputs), sources)


class Outcomes(unittest.TestCase):
    def test_1_the_same_line_is_dropped_silently(self):
        for line in ("\\usepackage[qca]{labstyle}", "  \\usepackage [ qca ] {labstyle}  % why", "\\RequirePackage[qca]{labstyle}",
                     "\\usepackage{labstyle}"):
            result = run([f"a\n{line}\nb\n"])
            self.assertEqual(result.options, ("qca",), line)
            self.assertTrue(result.texts[0].startswith("a\n% pdfmd: dropped"), result.texts[0])
            self.assertTrue(result.texts[0].endswith("\nb\n"))
            self.assertEqual([event.id for event in result.events], ["KIT-SAME"])
            self.assertFalse(result.events[0].warn)

    def test_the_same_input_is_dropped_and_another_is_kept(self):
        result = run(["\\input{chemicals}\n\\input{chemicals.tex}\n\\input{mine}\n"])
        self.assertEqual(result.texts[0].splitlines()[2], "\\input{mine}")
        self.assertEqual([event.id for event in result.events], ["KIT-SAME", "KIT-SAME"])
        self.assertEqual(run(["\\input{chemicals}\n"], inputs=()).texts[0], "\\input{chemicals}\n")     # the kit does not write it

    def test_2_extra_options_are_merged_into_the_kits_line(self):
        result = run(["\\usepackage[qca,draft]{labstyle}\n", "\\usepackage[draft,final]{labstyle}\n"])
        self.assertEqual(result.options, ("qca", "draft", "final"))
        self.assertEqual([event.id for event in result.events], ["KIT-MERGE", "KIT-MERGE"])
        self.assertIn("draft merged", result.events[0].message)
        self.assertEqual(run(["\\usepackage[qca,draft]{labstyle}\n\\usepackage[draft]{labstyle}\n"]).options, ("qca", "draft"))
        self.assertEqual(run(["\\usepackage[draft]{labstyle}\n"], options=()).options, ("draft",))      # a mode with no options

    def test_options_may_span_lines(self):
        result = run(["\\usepackage[qca,\n   draft]{labstyle}\nafter\n"])
        self.assertEqual(result.options, ("qca", "draft"))
        self.assertEqual(result.texts[0].splitlines()[-1], "after")

    def test_3_another_modes_option_yields_in_a_found_file_with_a_warning(self):
        result = run(["\\usepackage[orgchem]{labstyle}\nkeep\n"], explicit=False)
        self.assertEqual(result.options, ("qca",))
        self.assertTrue(result.texts[0].startswith("% pdfmd: commented out, it contradicts"))
        self.assertIn("keep", result.texts[0])
        self.assertEqual([(event.id, event.warn) for event in result.events], [("KIT-YIELD", True)])
        self.assertIn("another mode of the kit", result.events[0].message)

    def test_3_another_modes_option_in_an_explicit_source_stops_naming_both_sides(self):
        with self.assertRaises(PreambleClash) as caught:
            run(["\\usepackage[qca,orgchem]{labstyle}\n"], explicit=True)
        message = str(caught.exception)
        for part in ("lab 2.0 (mode qca)", "[qca]", "s0", "[qca,orgchem]", "orgchem belongs to another mode"):
            self.assertIn(part, message)

    def test_4_everything_else_is_left_alone(self):
        text = "\\usepackage{xcolor}\n\\usepackage[a]{other}\n\\labsetup{x=1}\n\\newcommand{\\y}{2}\n% \\usepackage[orgchem]{labstyle}\n"
        result = run([text])
        self.assertEqual((result.texts, result.events), ([text], []))

    def test_a_package_in_a_shape_it_will_not_guess_stops_naming_the_line(self):
        for text in ("\\usepackage{a,labstyle}\n", "\\IfFileExists{labstyle.sty}{\\usepackage[qca]{labstyle}}{}\n",
                     "\\newcommand\\load{\\usepackage[qca]{labstyle}}\n", "x\n\\usepackage[qca]{labstyle,other}\n"):
            with self.assertRaises(PreambleClash, msg=text) as caught:
                run([text], explicit=False)
            self.assertIn("labstyle", str(caught.exception))
        with self.assertRaises(PreambleClash) as caught:
            run(["a\nb\n\\newcommand\\load{\\usepackage[qca]{labstyle}}\n"])
        self.assertIn("line 3", str(caught.exception))

    def test_a_commented_line_is_not_a_line(self):
        text = "% \\usepackage[orgchem]{labstyle}\n%\\newcommand\\l{\\usepackage{a,labstyle}}\n"
        self.assertEqual(run([text], explicit=True).texts, [text])
        self.assertEqual(blank_comments("a % b\nc \\% d"), "a    \nc \\% d")

    def test_a_kit_with_no_package_only_checks_its_inputs(self):
        result = resolve("k", "", (), frozenset(), frozenset({"chemicals"}), [Source("s", "\\usepackage[x]{labstyle}\n\\input{chemicals}\n", True)])
        self.assertEqual(result.texts[0].splitlines()[0], "\\usepackage[x]{labstyle}")
        self.assertTrue(result.texts[0].splitlines()[1].startswith("% pdfmd: dropped"))

    def test_helpers(self):
        self.assertEqual(package_line("p", ("a", "b")), "\\usepackage[a,b]{p}")
        self.assertEqual(package_line("p", ()), "\\usepackage{p}")
        self.assertEqual(kit_inputs(["\\input{chemicals}", "\\input{x.tex} % c", "\\labsetup{}", "  \\input{ y } "]),
                         frozenset({"chemicals", "x", "y"}))


KIT = """\
kit-format: 1
name: lab
version: 2.0
package: labstyle
modes:
  qca: {aliases: [220], options: [qca], latex: ['\\LabScheme{word}']}
  org: {aliases: [211], options: [orgchem]}
latex: ['\\input{chemicals}']
latex-keys: {experiment: LabExperiment}
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@unittest.skipUnless(PANDOC, "Pandoc is needed")
class Builds(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        kit = self.root / "course" / "kits" / "lab"
        write(kit / ".kit", KIT)
        write(kit / "chemicals.tex", "\\newcommand{\\chem}{1}\n")
        write(kit / "labstyle.sty", "\\ProvidesPackage{labstyle}\n\\DeclareOption{qca}{}\\DeclareOption{orgchem}{}\\DeclareOption{draft}{}\\ProcessOptions\\relax\n"
                                    "\\newcommand{\\LabScheme}[1]{}\\newcommand{\\LabExperiment}{N/A}\\newcommand{\\labsetup}[1]{}\n")
        self.config = write(self.root / "cfg" / "config.yaml", f"kits: [{self.root / 'course' / 'kits'}]\n")
        self.folder = self.root / "course" / "LR1"
        self.doc("pdfmd-options: {kit: lab:qca}")

    def doc(self, options="", more="") -> Path:
        return write(self.folder / "report.md", f"---\ntitle: T\nexperiment: 6\n{options}\n{more}---\nText.\n")

    def build(self, *args):
        environment = {**os.environ, "PDFMD_CONFIG": str(self.config), "XDG_CACHE_HOME": str(self.root / "cache"),
                       "PDFMD_NO_PROMPT": "1", "PDFMD_BUILD_LOG": "off"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report.md", "--to", "latex", "-o", "out.tex", "--no-backup",
                               "--no-stamp", "--verbose", *args], capture_output=True, text=True, cwd=self.folder, env=environment)
        out = self.folder / "out.tex"
        return done, out.read_text(encoding="utf-8") if done.returncode == 0 and out.is_file() else ""

    def active(self, tex, text):
        """How many uncommented lines of the LaTeX are ``text``."""
        return sum(1 for line in tex.splitlines() if line.strip() == text)

    def test_the_kits_lines_come_first_and_the_users_after(self):
        write(self.folder / "preamble.tex", "\\usepackage{xcolor}\n\\labsetup{x=1}\n")
        done, tex = self.build()
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        order = [tex.index(text) for text in ("\\usepackage[qca]{labstyle}", "\\input{chemicals}", "\\LabScheme{word}", "\\labsetup{x=1}")]
        self.assertEqual(order, sorted(order))
        self.assertIn("\\renewcommand{\\LabExperiment}{6}", tex)                  # the .kit's latex-keys, with no preamble.tex of the user's

    def test_the_documents_header_includes_follow_the_kit(self):
        self.doc("pdfmd-options: {kit: lab:qca}", "header-includes:\n  - '\\labsetup{doc=1}'\n")
        done, tex = self.build()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertLess(tex.index("\\usepackage[qca]{labstyle}"), tex.index("\\labsetup{doc=1}"))

    def test_a_folders_metadata_header_includes_follow_the_kit(self):
        write(self.root / "course" / ".pdfmd" / "metadata.yaml", "header-includes:\n  - '\\labsetup{course=1}'\n")
        done, tex = self.build()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertLess(tex.index("\\usepackage[qca]{labstyle}"), tex.index("\\labsetup{course=1}"))

    def test_outcomes_1_and_2_in_a_found_preamble_leave_the_file_alone(self):
        original = "\\usepackage[qca,draft]{labstyle}\n\\input{chemicals}\n\\usepackage{xcolor}\n"
        path = write(self.folder / "preamble.tex", original)
        done, tex = self.build()
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertEqual(self.active(tex, "\\usepackage[qca,draft]{labstyle}"), 1)         # the kit's, merged
        self.assertEqual(self.active(tex, "\\input{chemicals}"), 1)
        self.assertIn("\\usepackage{xcolor}", tex)
        self.assertIn("AUTO KIT-MERGE", done.stdout)
        self.assertIn("AUTO KIT-SAME", done.stdout)
        self.assertEqual(path.read_text(encoding="utf-8"), original)                # a user's file is never edited

    def test_outcome_3_a_found_preamble_yields_with_a_warning(self):
        write(self.folder / "preamble.tex", "\\usepackage[orgchem]{labstyle}\n\\labsetup{kept=1}\n")
        done, tex = self.build()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("WARN  KIT-YIELD", done.stderr)
        self.assertEqual(self.active(tex, "\\usepackage[orgchem]{labstyle}"), 0)
        self.assertIn("\\labsetup{kept=1}", tex)

    def test_outcome_3_an_explicit_source_stops_the_build(self):
        self.doc("pdfmd-options: {kit: lab:qca}", "header-includes:\n  - '\\usepackage[orgchem]{labstyle}'\n")
        done, _ = self.build()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("belongs to another mode", done.stderr)
        header = write(self.folder / "mine.tex", "\\usepackage[orgchem]{labstyle}\n")
        self.doc("pdfmd-options: {kit: lab:qca}")
        done, _ = self.build("--include-in-header", str(header))
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("mine.tex", done.stderr)
        self.assertEqual(header.read_text(encoding="utf-8"), "\\usepackage[orgchem]{labstyle}\n")

    def test_the_other_mode_is_a_switch_away(self):
        done, tex = self.build("--kit", "lab:211")
        self.assertIn("\\usepackage[orgchem]{labstyle}", tex)
        self.assertNotIn("\\LabScheme{word}", tex)                                  # that line belongs to the qca mode

    def test_an_explicit_include_in_header_follows_the_kit_too(self):
        header = write(self.folder / "mine.tex", "\\labsetup{mine=1}\n")
        done, tex = self.build("--include-in-header", str(header))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertLess(tex.index("\\usepackage[qca]{labstyle}"), tex.index("\\labsetup{mine=1}"))

    @unittest.skipUnless(shutil.which("pdflatex"), "needs pdflatex")
    def test_a_real_compile_survives_the_options_the_user_added(self):
        """The reason for the merge: LaTeX stops with an Option clash when two \\usepackage lines of one package differ."""
        write(self.folder / "preamble.tex", "\\usepackage[qca,draft]{labstyle}\n\\input{chemicals}\n")
        environment = {**os.environ, "PDFMD_CONFIG": str(self.config), "XDG_CACHE_HOME": str(self.root / "cache"),
                       "PDFMD_NO_PROMPT": "1", "PDFMD_BUILD_LOG": "off",
                       "TEXINPUTS": str(self.root / "course" / "kits" / "lab") + "//" + os.pathsep}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report.md", "-e", "pdflatex", "-o", "out.pdf", "--no-backup",
                               "--no-stamp"], capture_output=True, text=True, cwd=self.folder, env=environment)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.folder / "out.pdf").read_bytes().startswith(b"%PDF"))
        # without pdfmd's settling the same two lines are the clash
        clash = self.root / "clash.tex"
        write(clash, "\\documentclass{article}\n\\usepackage[qca]{labstyle}\n\\usepackage[qca,draft]{labstyle}\n\\begin{document}x\\end{document}\n")
        bare = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", clash.name], capture_output=True, text=True,
                              cwd=self.root, env=environment)
        self.assertNotEqual(bare.returncode, 0)
        self.assertIn("Option clash", bare.stdout)

    def test_no_kit_no_change(self):
        self.doc()
        write(self.folder / "preamble.tex", "\\usepackage[qca]{labstyle}\n")
        done, tex = self.build()
        self.assertEqual(self.active(tex, "\\usepackage[qca]{labstyle}"), 1)
        self.assertNotIn("KIT", done.stdout)


if __name__ == "__main__":
    unittest.main()
