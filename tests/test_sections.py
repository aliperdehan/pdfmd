"""`pdfmd doc#section`: one section of an ordinary document, or a heading
inside a part in parts mode (v3.21.1).

The scanner and the resolver are pure and tested directly; the end-to-end
tests run the real CLI to LaTeX and check what the section tests exist for: the
section's LaTeX is, block for block, the same LaTeX the full document has.
"""

from __future__ import annotations

import contextlib
import io
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

import pdfmd  # noqa: E402

DOCUMENT = """\
---
title: Glucose in our body
---

Lead paragraph.

# Introduction

Intro text.

# Only a Part {#sec:only}

Text with $$E = mc^2$$ {#eq:emc}

## Only Subsection

Subsection text.

### Deep Level

Deep text.

Setext Heading
--------------

Setext body.

# Next Part

Next text.
"""


def headings_of(text: str):
    return pdfmd.scan_headings(text.split("\n"))


class ScanHeadings(unittest.TestCase):
    def test_atx_levels_ids_and_closing_hashes(self):
        found = headings_of("# One {#a .b}\n\n## Two ##\n\n###### Six\n")
        self.assertEqual([(h.level, h.text, h.ids) for h in found],
                         [(1, "One", ("a",)), (2, "Two", ()), (6, "Six", ())])

    def test_setext_headings_are_headings(self):
        found = headings_of("Title\n=====\n\ntext\n\nSub\n---\n\nmore\n")
        self.assertEqual([(h.level, h.text) for h in found], [(1, "Title"), (2, "Sub")])

    def test_what_looks_like_a_heading_but_is_not(self):
        text = ("para line one\npara line two\n---\n\n"          # a paragraph, then a rule
                "| a | b |\n|---|---|\n| 1 | 2 |\n\n"             # a table
                "```\n# comment in code\n```\n\n"
                "<!--\n# commented out\n-->\n\n"
                "    # indented code\n\n"
                "- item\n---\n\n"
                "#nospace\n")
        self.assertEqual(headings_of(text), [])

    def test_a_section_runs_to_the_next_heading_of_its_level_or_higher(self):
        found = headings_of("# A\n\n## B\n\n### C\n\n## D\n\n# E\n")
        self.assertEqual([(h.text, h.end) for h in found], [("A", 8), ("B", 6), ("C", 6), ("D", 8), ("E", 10)])

    def test_links_and_spans_in_a_heading_are_reduced_to_their_text(self):
        self.assertEqual(headings_of("# See [the docs](http://x.y) and [this]{.c}\n")[0].text,
                         "See the docs and this")


class FindHeading(unittest.TestCase):
    def setUp(self):
        self.headings = headings_of(DOCUMENT.split("---\n", 2)[2])
        pdfmd._LOOKUP_ANNOUNCED.clear()
        self.addCleanup(setattr, pdfmd, "FUZZY_LOOKUP", pdfmd.FUZZY_LOOKUP)
        pdfmd.FUZZY_LOOKUP = True
        self._silence = contextlib.redirect_stderr(io.StringIO())
        self._silence.__enter__()
        self.addCleanup(self._silence.__exit__, None, None, None)

    def find(self, request):
        return pdfmd.find_heading(self.headings, request).text

    def test_by_text_however_it_is_spelt(self):
        for request in ("Only a Part", "onlyapart", "ONLY_A_PART", "only-a-part"):
            self.assertEqual(self.find(request), "Only a Part")

    def test_by_explicit_id(self):
        self.assertEqual(self.find("sec:only"), "Only a Part")

    def test_by_the_start_of_the_text(self):
        self.assertEqual(self.find("introd"), "Introduction")

    def test_a_level_marker_restricts_the_level(self):
        self.assertEqual(self.find("##onlysub"), "Only Subsection")
        self.assertEqual(self.find("###deep"), "Deep Level")
        self.assertEqual(self.find("##setext"), "Setext Heading")
        with self.assertRaises(SystemExit):
            self.find("#deep")

    def test_a_path_goes_one_level_down_at_a_time(self):
        self.assertEqual(self.find("onlyapart/deep"), "Deep Level")
        self.assertEqual(self.find("onlyapart/onlysubsection/deep"), "Deep Level")
        with self.assertRaises(SystemExit):
            self.find("introduction/deep")

    def test_two_headings_that_fit_equally_are_an_error_that_says_how_to_fix_it(self):
        with self.assertRaisesRegex(SystemExit, r"only.*Only a Part.*Only Subsection.*parent/name"):
            self.find("only")

    def test_an_unknown_name_lists_the_headings(self):
        with self.assertRaisesRegex(SystemExit, "matches no heading. Headings: # Introduction"):
            self.find("zzzz")

    def test_with_lookup_off_only_the_name_itself_counts(self):
        pdfmd.FUZZY_LOOKUP = False
        self.assertEqual(self.find("only_a_part"), "Only a Part")
        with self.assertRaises(SystemExit):
            self.find("introd")

    def test_nested_choices_collapse_to_the_outer_one(self):
        outer = pdfmd.outermost_headings([self.headings[3], self.headings[1], self.headings[2]])
        self.assertEqual([h.text for h in outer], ["Only a Part"])


class PlanSections(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name).resolve()
        self.addCleanup(setattr, pdfmd, "FUZZY_LOOKUP", pdfmd.FUZZY_LOOKUP)
        pdfmd.FUZZY_LOOKUP = True
        pdfmd._LOOKUP_ANNOUNCED.clear()

    def plan(self, text, *requests):
        path = self.root / "doc.md"
        path.write_text(text, encoding="utf-8")
        return pdfmd.plan_sections(path, list(requests), None, None)

    def test_the_cut_is_front_matter_lead_and_the_section(self):
        plan = self.plan(DOCUMENT, "onlyapart")
        self.assertTrue(plan.text.startswith("---\ntitle: Glucose in our body\n---\n"))
        self.assertIn("Lead paragraph.", plan.text)
        self.assertIn("# Only a Part {#sec:only}", plan.text)
        self.assertIn("Deep text.", plan.text)
        self.assertIn("Setext body.", plan.text)
        self.assertNotIn("Intro text.", plan.text)
        self.assertNotIn("Next text.", plan.text)

    def test_several_sections_come_out_in_document_order_each_once(self):
        plan = self.plan(DOCUMENT, "next", "introduction", "onlyapart", "##deep".replace("##", "###"))
        self.assertEqual([h.text for h in plan.selected], ["Introduction", "Only a Part", "Next Part"])
        self.assertEqual(plan.text.count("Deep text."), 1)

    def test_the_output_is_named_after_the_sections(self):
        self.assertEqual(self.plan(DOCUMENT, "onlyapart").output_stem, "doc.only-a-part")
        self.assertEqual(self.plan(DOCUMENT, "next", "intro").output_stem, "doc.introduction+next-part")

    def test_cyrillic_headings_get_a_readable_name(self):
        plan = self.plan("---\ntitle: T\n---\n\n# Введение\n\nтекст\n", "vvedenie")
        self.assertEqual(plan.output_stem, "doc.vvedenie")

    def test_a_leading_bare_title_is_promoted_before_cutting(self):
        plan = self.plan("# My Title\n\nIntro.\n\n## Alpha\n\nA.\n\n## Beta\n\nB.\n", "beta")
        self.assertTrue(plan.shifted)
        self.assertTrue(plan.text.startswith("---\ntitle: 'My Title'\n---"))
        self.assertIn("## Beta", plan.text)
        self.assertNotIn("## Alpha", plan.text)

    def test_a_bare_title_is_not_a_section_and_the_error_says_so(self):
        with self.assertRaisesRegex(SystemExit, "became the document's title"):
            self.plan("# Only Heading\n\ntext\n", "only")

    def test_a_document_with_no_headings_is_an_error(self):
        with self.assertRaisesRegex(SystemExit, "no headings"):
            self.plan("just text\n", "anything")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class EndToEnd(unittest.TestCase):
    """The CLI, to LaTeX: every block of a section is in the full build."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name).resolve()

    def pdfmd(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args, "--to", "latex"],
                              cwd=self.root, capture_output=True, text=True)

    @staticmethod
    def blocks(path: Path, after: str) -> list[str]:
        text = path.read_text(encoding="utf-8").split("\\begin{document}", 1)[1].rsplit("\\end{document}", 1)[0]
        return re.split(r"\n\n(?=\\)", text.split(after, 1)[1].strip())

    def assert_blocks_of_full_build(self, section_file: str, full_file: str, after: str):
        full = (self.root / full_file).read_text(encoding="utf-8")
        for block in self.blocks(self.root / section_file, after):
            self.assertIn(block, full)

    def test_a_section_of_an_ordinary_document(self):
        (self.root / "doc.md").write_text(DOCUMENT, encoding="utf-8")
        self.assertEqual(self.pdfmd("doc", "-o", "full.tex").returncode, 0)
        for request, expected in (("doc#onlyapart", ["Only a Part", "Only Subsection", "Deep Level", "Setext Heading"]),
                                  ("doc###deep", ["Deep Level"]), ("doc#setext", ["Setext Heading"]),
                                  ("doc#sec:only", ["Only a Part", "Only Subsection", "Deep Level", "Setext Heading"]),
                                  ("doc#onlyapart/deep", ["Deep Level"]), ("doc#next+intro", ["Introduction", "Next Part"])):
            with self.subTest(request=request):
                result = self.pdfmd(request, "-o", "part.tex")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                names = re.findall(r"section\{([^}]*)\}", (self.root / "part.tex").read_text(encoding="utf-8"))
                self.assertEqual(names, expected)
                self.assert_blocks_of_full_build("part.tex", "full.tex", "Lead paragraph.")

    def test_the_default_output_name_never_replaces_the_document_build(self):
        (self.root / "doc.md").write_text(DOCUMENT, encoding="utf-8")
        self.assertEqual(self.pdfmd("doc#onlyapart").returncode, 0)
        self.assertTrue((self.root / "doc.only-a-part.tex").exists())
        self.assertFalse((self.root / "doc.tex").exists())

    def test_no_document_name_means_the_only_one_here(self):
        (self.root / "doc.md").write_text(DOCUMENT, encoding="utf-8")
        result = self.pdfmd("#introduction", "-o", "part.tex")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AUTO MD", result.stdout)

    def test_list_parts_lists_headings_and_ids(self):
        (self.root / "doc.md").write_text(DOCUMENT, encoding="utf-8")
        result = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc", "--list-parts"],
                                cwd=self.root, capture_output=True, text=True)
        self.assertIn("# Only a Part  {#sec:only}", result.stdout)
        self.assertIn("## Setext Heading", result.stdout)

    def test_an_unknown_section_fails_and_builds_nothing(self):
        (self.root / "doc.md").write_text(DOCUMENT, encoding="utf-8")
        result = self.pdfmd("doc#nonesuch", "-o", "part.tex")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("matches no heading", result.stdout + result.stderr)
        self.assertFalse((self.root / "part.tex").exists())

    def test_parts_mode_falls_back_to_a_heading_inside_a_part(self):
        parts = self.root / "parts"
        parts.mkdir()
        (self.root / "report.md").write_text("---\ntitle: Report\npdfmd-options:\n  parts: auto\n---\n\nLead.\n",
                                             encoding="utf-8")
        (parts / "10-introduction.md").write_text("# Introduction\n\nIntro.\n", encoding="utf-8")
        (parts / "20-methods.md").write_text(
            "# Methods\n\nM.\n\n## Sampling {#sec:sampling}\n\nS.\n\n## Analysis\n\nA.\n", encoding="utf-8")
        (parts / "30-discussion.md").write_text("# Discussion\n\nD.\n\n## Yield\n\nY.\n", encoding="utf-8")
        self.assertEqual(self.pdfmd("report", "-o", "full.tex").returncode, 0)
        for request, expected in (("report#methods", ["Methods", "Sampling", "Analysis"]),   # a part, as before
                                  ("report#sampling", ["Sampling"]), ("report##analysis", ["Analysis"]),
                                  ("report#sec:sampling+yield", ["Sampling", "Yield"]),
                                  ("report#methods/sampling", ["Sampling"])):
            with self.subTest(request=request):
                result = self.pdfmd(request, "-o", "part.tex")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                names = re.findall(r"section\{([^}]*)\}", (self.root / "part.tex").read_text(encoding="utf-8"))
                self.assertEqual(names, expected)
                self.assert_blocks_of_full_build("part.tex", "full.tex", "Lead.")
        result = self.pdfmd("report#nonesuch", "-o", "x.tex")
        self.assertIn("matches no part", result.stdout + result.stderr)
        self.assertIn("no heading named like that", result.stdout + result.stderr)
        result = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report", "--list-parts"],
                                cwd=self.root, capture_output=True, text=True)
        self.assertIn("## Sampling  {#sec:sampling}", result.stdout)


if __name__ == "__main__":
    unittest.main()
