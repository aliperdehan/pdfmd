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

# never read or write the real user's config and state while testing
import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

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


ELEMENTS = """\
---
title: Elements
---

Lead text before everything.

![A lead figure](x.png){#fig:lead}

# Results

Some text with a span [important]{#span:imp} inside.

$$ E = mc^2 $$ {#eq:energy}

| a | b |
|---|---|
| 1 | 2 |

: Measured values {#tbl:values}

Table: Caption above {#tbl:above}

| c | d |
|---|---|
| 3 | 4 |

::: {#note1 .callout}
Callout text.

![Inside the callout](y.png){#fig:inside}
:::

```{#lst:code .python}
# not a heading

print("hi")
```

## Details {#sec:details}

Detail text.

# Next

End.
"""


class SplitAtHeadings(unittest.TestCase):
    """--split cuts where sections are cut: ATX and setext headings alike."""

    def test_setext_headings_start_a_part(self):
        body = "lead\n\nTitle One\n=========\n\ntext\n\nSub\n---\n\nmore\n\n# ATX\n\nlast\n"
        self.assertEqual([part[0] for part in pdfmd.split_top_level_sections(body, 1)],
                         ["lead", "Title One", "# ATX"])
        self.assertEqual([part[0] for part in pdfmd.split_top_level_sections(body, 2)], ["lead", "Sub"])

    def test_what_is_not_a_heading_is_not_cut_at(self):
        body = "# A\n\n```\n# code\n```\n\n<!--\n# hidden\n-->\n\npara\nend\n---\n\n| a |\n|---|\n"
        self.assertEqual(len(pdfmd.split_top_level_sections(body, 1)), 2)   # the lead, and one part

    def test_a_document_without_headings_is_one_piece(self):
        self.assertEqual(pdfmd.split_top_level_sections("just text", 1), [["just text"]])

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_the_cli_splits_a_mixed_document_and_the_parts_read_back_identically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "book.md").write_text(
                "---\ntitle: Mixed\n---\n\nLead.\n\nIntroduction\n============\n\nIntro.\n\n"
                "Background\n----------\n\nBack.\n\n# Methods\n\nM.\n\nResults {#sec:res}\n=======\n\nR.\n",
                encoding="utf-8")
            for depth, expected in (("1", ["10-introduction.md", "20-methods.md", "30-results.md"]),
                                    ("2", ["00-introduction.md", "10-background.md", "20-methods.md", "30-results.md"])):
                result = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "book", "--split", f"out{depth}",
                                         "--split-depth", depth], cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("identical document", result.stdout)
                self.assertEqual(sorted(path.name for path in (root / f"out{depth}").rglob("*.md")
                                        if path.name != "book.md"), expected)


class LabelledElements(unittest.TestCase):
    def setUp(self):
        self.lines = ELEMENTS.split("---\n", 2)[2].split("\n")
        self.items = {item.ids[0]: item for item in pdfmd.scan_items(self.lines) if item.level == 0}

    def text(self, identifier):
        item = self.items[identifier]
        return "\n".join(self.lines[item.line:item.end]).rstrip("\n")

    def test_every_kind_is_found_with_its_kind(self):
        self.assertEqual({identifier: item.text for identifier, item in self.items.items()},
                         {"fig:lead": "figure", "span:imp": "paragraph", "eq:energy": "equation",
                          "tbl:values": "table", "tbl:above": "table", "note1": "div",
                          "fig:inside": "figure", "lst:code": "code block"})

    def test_a_table_is_its_caption_and_the_table_whichever_side_the_caption_is(self):
        self.assertTrue(self.text("tbl:values").startswith("| a | b |"))
        self.assertTrue(self.text("tbl:values").endswith("{#tbl:values}"))
        self.assertTrue(self.text("tbl:above").startswith("Table: Caption above"))
        self.assertTrue(self.text("tbl:above").endswith("| 3 | 4 |"))

    def test_a_div_runs_to_its_closing_fence_and_a_code_block_to_its_own(self):
        self.assertTrue(self.text("note1").endswith(":::"))
        self.assertIn("Inside the callout", self.text("note1"))
        self.assertIn('print("hi")', self.text("lst:code"))     # a blank line inside it does not end it

    def test_a_heading_with_an_id_is_a_heading_not_an_element(self):
        self.assertNotIn("sec:details", self.items)

    def test_an_element_right_under_a_heading_does_not_swallow_it(self):
        # No blank line between the heading and the figure: the figure's paragraph
        # must start below the heading, and the heading's section must stay whole.
        lines = ("# Setup {#sec:setup}\nText.\n![First](a.png){#fig:a}\n\n"
                 "# Results {#sec:results}\n![Second](b.png){#fig:b}\n\n## Details {#sec:details}\n\nMore.\n\n# End\n").split("\n")
        items = pdfmd.scan_items(lines)
        figure = next(item for item in items if item.ids == ("fig:b",))
        self.assertEqual((figure.line, figure.text), (5, "figure"))
        with contextlib.redirect_stderr(io.StringIO()):
            results = pdfmd.find_heading(items, "sec:results")
            self.assertEqual((results.text, results.end), ("Results", 11))
            self.assertEqual(pdfmd.find_heading(items, "details").text, "Details")
            self.assertEqual(pdfmd.find_heading(items, "fig:b").text, "figure")

    def test_two_items_that_begin_on_one_line_stay_two_items(self):
        # A table that holds an id of its own and its caption's id begin on the same line.
        lines = "| a [x]{#span:x} | b |\n|---|---|\n| 1 | 2 |\n\n: Caption {#tbl:t}\n".split("\n")
        items = [item for item in pdfmd.scan_items(lines) if item.level == 0]
        self.assertEqual(sorted(identifier for item in items for identifier in item.ids), ["span:x", "tbl:t"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pdfmd.find_heading(items, "span:x").ids, ("span:x",))
            self.assertEqual(pdfmd.find_heading(items, "tbl:t").ids, ("tbl:t",))

    def test_a_hash_line_in_code_is_not_a_heading(self):
        self.assertEqual([h.text for h in pdfmd.scan_headings(self.lines)], ["Results", "Details", "Next"])

    def test_elements_are_named_by_id_and_by_a_word_of_it(self):
        pdfmd._LOOKUP_ANNOUNCED.clear()
        items = pdfmd.scan_items(self.lines)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pdfmd.find_heading(items, "fig:inside").ids, ("fig:inside",))
            self.assertEqual(pdfmd.find_heading(items, "inside").ids, ("fig:inside",))
            self.assertEqual(pdfmd.find_heading(items, "results/eq:energy").ids, ("eq:energy",))
            with self.assertRaises(SystemExit):
                pdfmd.find_heading(items, "##eq:energy")   # an element has no heading level

    def test_a_lone_element_comes_without_the_lead_but_a_section_with_it(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "doc.md"
            source.write_text(ELEMENTS, encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                lone = pdfmd.plan_sections(source, ["fig:inside"], None, None)
                section = pdfmd.plan_sections(source, ["details"], None, None)
                inside_lead = pdfmd.plan_sections(source, ["fig:lead", "details"], None, None)
        self.assertNotIn("Lead text", lone.text)
        self.assertEqual(lone.output_stem, "doc.fig-inside")
        self.assertIn("Lead text", section.text)
        self.assertEqual(inside_lead.text.count("A lead figure"), 1)   # in the lead already


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

    def test_labelled_elements_build_and_match_the_full_document(self):
        (self.root / "doc.md").write_text(ELEMENTS, encoding="utf-8")
        (self.root / "x.png").write_bytes(b"")
        (self.root / "y.png").write_bytes(b"")
        self.assertEqual(self.pdfmd("doc", "-o", "full.tex").returncode, 0)
        full = (self.root / "full.tex").read_text(encoding="utf-8")
        for request, needle in (("doc#fig:inside", "Inside the callout"), ("doc#eq:energy", "mc^2"),
                                ("doc#tbl:values", "Measured values"), ("doc#tbl:above", "Caption above"),
                                ("doc#note1", "Callout text."), ("doc#lst:code", "print"),
                                ("doc#results/fig:inside", "Inside the callout")):
            with self.subTest(request=request):
                result = self.pdfmd(request, "-o", "part.tex")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                part = (self.root / "part.tex").read_text(encoding="utf-8")
                body = part.split("\\maketitle", 1)[1].rsplit("\\end{document}", 1)[0].strip()
                self.assertIn(needle, body)
                self.assertNotIn("Lead text", body)
                for block in re.split(r"\n\n(?=\\)", body):
                    self.assertIn(block, full)

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


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("lualatex"), "needs Pandoc and LuaLaTeX")
class SectionLabelSeeding(unittest.TestCase):
    """With the cache on, a section of an ordinary document takes the labels it
    does not define itself from the last full build (v3.21.5)."""

    DOCUMENT = ("---\ntitle: Seeding\nnumbersections: true\n---\n\n"
                "# Setup {#sec:setup}\n\nSee Section \\ref{sec:results} and \\ref{sec:details}.\n\n"
                "# Results {#sec:results}\n\nBack to Section \\ref{sec:setup}. Own label: \\ref{sec:results}.\n\n"
                "## Details {#sec:details}\n\nDetails refer to \\ref{sec:setup}.\n\n# End\n\nBye.\n")
    UNDEFINED = re.compile(r"Reference `[^']*' on page \d+ undefined")

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name).resolve()
        self.cache = self.root / "cache"
        self.environment = {**os.environ, "XDG_CACHE_HOME": str(self.cache), "LOCALAPPDATA": str(self.cache)}
        (self.root / "doc.md").write_text(self.DOCUMENT, encoding="utf-8")

    def build(self, request):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), request, "-e", "lualatex", "--cache"],
                              cwd=self.root, env=self.environment, capture_output=True, text=True)

    def log(self, stem):
        old = {key: os.environ.get(key) for key in ("XDG_CACHE_HOME", "LOCALAPPDATA")}
        os.environ.update(XDG_CACHE_HOME=str(self.cache), LOCALAPPDATA=str(self.cache))
        try:
            folder = pdfmd.cache_directory(self.root / "doc.md")
        finally:
            for key, value in old.items():
                os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
        return (folder / f"{stem}.log").read_text(encoding="utf-8", errors="replace")

    def test_references_to_other_sections_resolve_after_a_full_build(self):
        self.assertEqual(self.build("doc").returncode, 0)
        for request, stem in (("doc#results", "doc.results"), ("doc#sec:details", "doc.details")):
            with self.subTest(request=request):
                result = self.build(request)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIsNone(self.UNDEFINED.search(self.log(stem)))
                self.assertIn("come from the last full build", result.stdout)

    def test_without_a_full_build_they_still_print_as_question_marks(self):
        result = self.build("doc#results")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNotNone(self.UNDEFINED.search(self.log("doc.results")))
        self.assertIn("a full build", result.stdout)
        self.assertNotIn("come from the last full build", result.stdout)

    def test_a_sections_own_labels_stay_its_own(self):
        self.build("doc")
        self.build("doc#results")
        aux = (self.cache / "pdfmd").rglob("doc.results.aux")
        text = next(aux).read_text(encoding="utf-8")
        self.assertIn("\\newlabel{sec:results}{{1}", text)     # numbered from its own start, as documented


if __name__ == "__main__":
    unittest.main()
