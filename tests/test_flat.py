"""Flat Markdown (`--to gfm`, v3.26.3): the settings, the Lua filter through Pandoc, and the real command line."""

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
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
import pdfmd_flat  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402

PANDOC = shutil.which("pandoc")
FLAT_LUA = ROOT / "pdfmd_lua" / "flat.lua"
WRITER = pdfmd_flat.writer("gfm", "dollars", pdfmd.pandoc_extensions("gfm")) if PANDOC else "gfm-raw_html"


class Settings(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(pdfmd_flat.settings(None), {"scripts": "unicode", "math": "dollars", "title": True})

    def test_the_command_line_wins_over_the_document(self):
        chosen = pdfmd_flat.settings({"scripts": "html", "title": "no"}, scripts="drop")
        self.assertEqual((chosen["scripts"], chosen["title"]), ("drop", False))

    def test_a_wrong_value_names_the_choices(self):
        with self.assertRaisesRegex(pdfmd_flat.FlatError, "unicode, html, drop, ascii"):
            pdfmd_flat.settings({"scripts": "greek"})
        with self.assertRaisesRegex(pdfmd_flat.FlatError, "not a gfm setting"):
            pdfmd_flat.settings({"colour": "red"})

    def test_the_writer(self):
        both = frozenset({"tex_math_dollars", "tex_math_gfm"})
        self.assertEqual(pdfmd_flat.writer("gfm+raw", "dollars", both), "gfm")
        self.assertEqual(pdfmd_flat.writer("gfm", "dollars", both), "gfm-raw_html+tex_math_dollars-tex_math_gfm")
        self.assertEqual(pdfmd_flat.writer("gfm", "fenced", both), "gfm-raw_html")
        self.assertEqual(pdfmd_flat.writer("gfm", "dollars", frozenset()), "gfm-raw_html")     # an older Pandoc

    def test_the_two_targets(self):
        self.assertTrue(pdfmd_flat.is_flat("GFM"))
        self.assertFalse(pdfmd_flat.is_flat("gfm+raw"))
        self.assertTrue(pdfmd_flat.is_family("gfm+raw"))
        self.assertFalse(pdfmd_flat.is_family("html"))


@needs_pandoc(3, 1, 3)
class Filter(unittest.TestCase):
    """flat.lua itself, run by Pandoc on hand-written Markdown (captions as pandoc-crossref would have written them)."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-flat-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def flatten(self, text: str, scripts: str = "unicode", title: bool = True, *extra: str) -> tuple[str, str]:
        source = self.directory / "doc.md"
        source.write_text(text, encoding="utf-8")
        config = self.directory / "flat.yaml"
        config.write_text(f'pdfmd-flat:\n  scripts: {scripts}\n  title: {"true" if title else "false"}\n', encoding="utf-8")
        result = subprocess.run([PANDOC, str(source), "--metadata-file", str(config), "--lua-filter", str(FLAT_LUA),
                                 "-t", WRITER, "--wrap=none", *extra], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout, result.stderr

    def test_unicode_scripts_with_a_fallback(self):
        out, _ = self.flatten("H~2~O, x^2^, Na~2~CO~3~, CO~3~^2-^, Q^q+z^ and e^iπ^.\n")
        self.assertIn("H₂O, x², Na₂CO₃, CO₃²⁻, Q^(q+z)", out)
        self.assertNotIn("<su", out)

    def test_script_modes(self):
        text = "H~2~O and x^2^ and Q^q+z^\n"
        self.assertIn("H<sub>2</sub>O and x<sup>2</sup> and Q<sup>q+z</sup>", self.flatten(text, "html")[0])
        self.assertIn("H2O and x2 and Qq+z", self.flatten(text, "drop")[0])
        self.assertIn("H_2O and x^2 and Q^(q+z)", self.flatten(text, "ascii")[0])

    def test_captions_become_bold_text_above_a_table_and_below_a_figure(self):
        out, _ = self.flatten("| a | b |\n|---|---|\n| 1 | 2 |\n\n: Table 1: Moles {#tbl:m}\n\n"
                              "![Figure 2: A fig](x.png){#fig:a width=50%}\n", title=False)
        self.assertLess(out.index("**Table 1.** Moles"), out.index("| a "))
        self.assertGreater(out.index("**Figure 2.** A fig"), out.index("![Figure 2: A fig](x.png)"))
        self.assertNotIn("{#", out)
        self.assertNotIn("<", out)

    def test_a_caption_without_a_number_is_emphasis(self):
        out, _ = self.flatten("| a |\n|---|\n| 1 |\n\n: Just words\n", title=False)
        self.assertIn("*Just words*", out)

    def test_a_translated_label_is_split_at_its_number(self):
        out, _ = self.flatten("| a |\n|---|\n| 1 |\n\n: Таблица 3: Данные\n", title=False)
        self.assertIn("**Таблица 3.** Данные", out)

    def test_a_table_markdown_cannot_hold_is_html_and_counted(self):
        out, err = self.flatten("+---+-----+\n| a | b   |\n+===+=====+\n| x | - l1 |\n|   | - l2 |\n+---+-----+\n\n: Cap\n",
                                title=False)
        self.assertIn("<table", out)
        self.assertIn("too rich for a Markdown table", err)

    def test_a_simple_table_stays_a_pipe_table(self):
        out, err = self.flatten("| a | b |\n|---|---|\n| 1 | 2 |\n", title=False)
        self.assertIn("| a   | b   |", out)
        self.assertNotIn("too rich", err)

    def test_divisions_spans_and_attributes_are_gone(self):
        out, _ = self.flatten('::: {.note #n}\nA [small]{.smallcaps} and [span]{#s .c} here.\n:::\n\n'
                              '# Head {#h .unnumbered}\n\n``` {.python .numberLines #c}\nprint(1)\n```\n', title=False)
        self.assertNotIn("<", out)
        self.assertNotIn("{", out)
        self.assertIn("A small and span here.", out)
        self.assertIn("``` python", out)

    def test_definition_lists_and_line_blocks(self):
        out, _ = self.flatten("Term\n: The definition\n\n| line one\n| line two\n", title=False)
        self.assertIn("**Term**", out)
        self.assertIn("The definition", out)
        self.assertNotIn(":   ", out)
        self.assertIn("line one\\\nline two", out)

    def test_links_to_vanished_anchors_become_text_and_headings_get_github_slugs(self):
        out, _ = self.flatten("# Alpha {#sec:a}\n\nSee [the start](#sec:a), [gone](#fig:x) and [web](https://example.org/).\n",
                              title=False)
        self.assertIn("[the start](#alpha)", out)
        self.assertIn("See [the start](#alpha), gone and [web](https://example.org/).", out)

    def test_section_numbers_are_written_into_the_headings(self):
        out, _ = self.flatten("# One\n\n## Two\n\n# Three {.unnumbered}\n\n# Four\n", "unicode", False,
                              "--number-sections")
        self.assertIn("# 1 One", out)
        self.assertIn("## 1.1 Two", out)
        self.assertIn("# Three", out)
        self.assertIn("# 2 Four", out)

    def test_the_title_block(self):
        out, _ = self.flatten("---\ntitle: The Title\nauthor: [A One, B Two]\ndate: 2026-10-09\nabstract: Short.\n---\n\nBody.\n")
        self.assertTrue(out.startswith("# The Title\n\n*A One, B Two — 2026-10-09*\n\n**Abstract.** Short.\n\nBody."), out)
        self.assertNotIn("Title", self.flatten("---\ntitle: The Title\n---\n\nBody.\n", title=False)[0])

    def test_raw_pieces_nothing_carried_are_counted_not_silent(self):
        out, err = self.flatten("Text.\n\n```{=openxml}\n<w:p/>\n```\n\nand `\\labsetup`{=latex} then.\n", title=False)
        self.assertNotIn("<w:p/>", out)
        self.assertRegex(err, r"WARN  gfm: 1 raw Word XML piece \(e\.g\. <w:p/>\) has no plain-Markdown form")
        self.assertRegex(err, r"1 raw LaTeX piece \(e\.g\. \\labsetup\)")

    def test_numbered_equation_environments_are_unwrapped(self):
        out, _ = self.flatten("---\ntitle: T\n---\n\n$$\\begin{equation}\n\\label{eq:a}\nx = 1\n\\end{equation}$$\n\n"
                              "$$\\begin{align}\na &= b \\nonumber\\\\\nc &= d\n\\end{align}$$\n", title=False)
        self.assertNotIn("\\label", out)
        self.assertNotIn("\\begin{equation}", out)
        self.assertIn("x = 1", out)
        self.assertIn("\\begin{aligned}", out)
        self.assertNotIn("\\nonumber", out)

    def test_math_stays_math(self):
        out, _ = self.flatten("Inline $a_1^2$ and\n\n$$E = mc^2$$\n", title=False)
        self.assertIn("$a_1^2$", out)
        self.assertIn("E = mc^2", out)


@needs_pandoc(3, 1, 3)
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-flat-cli-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"]}

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=self.env)

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_the_output_sits_beside_the_source_and_never_over_it(self):
        source = self.write("doc.md", "---\ntitle: T\n---\n\nH~2~O and <b>bold</b>.\n")
        result = self.run_pdfmd("doc.md", "--to", "gfm")
        self.assertEqual(result.returncode, 0, result.stderr)
        flat = (self.directory / "doc.gfm.md").read_text(encoding="utf-8")
        self.assertIn("# T", flat)
        self.assertIn("H₂O and **bold**.", flat)
        self.assertIn("title: T", source.read_text(encoding="utf-8"))

    def test_another_markdown_writer_refuses_to_replace_its_source(self):
        source = self.write("doc.md", "# Hi\n\nText.\n")
        result = self.run_pdfmd("doc.md", "--to", "markdown")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is the source itself", result.stdout + result.stderr)
        self.assertEqual(source.read_text(encoding="utf-8"), "# Hi\n\nText.\n")

    def test_the_name_notes_gfm_md_is_flat_markdown_and_notes_md_alone_is_not(self):
        self.write("doc.md", "---\ntitle: T\n---\n\nH~2~O.\n")
        self.assertEqual(self.run_pdfmd("doc.md", "-o", "notes.gfm.md").returncode, 0)
        self.assertIn("H₂O", (self.directory / "notes.gfm.md").read_text(encoding="utf-8"))
        self.assertEqual(self.run_pdfmd("doc.md", "-o", "notes.md").returncode, 0)
        self.assertIn("H~2~O", (self.directory / "notes.md").read_text(encoding="utf-8"))

    def test_gfm_raw_is_pandocs_own_writer(self):
        self.write("doc.md", "---\ntitle: T\n---\n\nH~2~O.\n")
        result = self.run_pdfmd("doc.md", "--to", "gfm+raw", "-o", "own.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("H<sub>2</sub>O", (self.directory / "own.md").read_text(encoding="utf-8"))

    def test_csv_blocks_includes_and_raw_pieces_are_carried_over(self):
        self.write("data.csv", "Name,Mass\nWater,18.02\n")
        self.write("doc.md", '''---
title: T
---

::: {.csv file="data.csv"}
:::

<div class="x">

Raw <b>html</b> and \\textbf{tex}.

</div>
''')
        result = self.run_pdfmd("doc.md", "--to", "gfm")
        self.assertEqual(result.returncode, 0, result.stderr)
        flat = (self.directory / "doc.gfm.md").read_text(encoding="utf-8")
        self.assertIn("| Water | 18.02 |", flat)
        self.assertIn("Raw **html** and **tex**.", flat)
        self.assertNotIn(":::", flat)
        self.assertNotIn("<div", flat)

    def test_images_written_elsewhere_get_a_note(self):
        self.write("doc.md", "---\ntitle: T\n---\n\n![a](fig.png)\n")
        (self.directory / "out").mkdir()
        elsewhere = self.run_pdfmd("doc.md", "--to", "gfm", "-o", "out/doc.md", "--verbose")
        self.assertIn("relative to ITS folder", elsewhere.stdout + elsewhere.stderr)
        beside = self.run_pdfmd("doc.md", "--to", "gfm", "--verbose")
        self.assertNotIn("relative to ITS folder", beside.stdout + beside.stderr)

    def test_scripts_option_and_document_option(self):
        self.write("doc.md", "---\ntitle: T\n---\n\nH~2~O.\n")
        self.assertEqual(self.run_pdfmd("doc.md", "--to", "gfm", "--gfm-scripts", "ascii", "-o", "a.md").returncode, 0)
        self.assertIn("H_2O", (self.directory / "a.md").read_text(encoding="utf-8"))
        self.write("opt.md", "---\ntitle: T\npdfmd-options:\n  gfm:\n    scripts: drop\n---\n\nH~2~O.\n")
        self.assertEqual(self.run_pdfmd("opt.md", "--to", "gfm", "-o", "b.md").returncode, 0)
        self.assertIn("H2O", (self.directory / "b.md").read_text(encoding="utf-8"))
        bad = self.write("bad.md", "---\npdfmd-options:\n  gfm: {scripts: greek}\n---\n\nx\n")
        result = self.run_pdfmd(bad.name, "--to", "gfm", "-o", "c.md")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unicode, html, drop, ascii", result.stdout + result.stderr)

    def test_a_part_keeps_the_numbers_of_the_whole(self):
        self.write("report.md", "---\ntitle: P\npdfmd-options:\n  parts: auto\n---\n")
        self.write("parts/10-one.md", "# One\n\nText.\n")
        self.write("parts/20-two.md", "# Two\n\nText.\n")
        result = self.run_pdfmd("report.md", "--to", "gfm")
        self.assertEqual(result.returncode, 0, result.stderr)
        flat = (self.directory / "report.gfm.md").read_text(encoding="utf-8")
        self.assertLess(flat.index("# One"), flat.index("# Two"))


def _can_draw_latex() -> bool:
    if not (shutil.which("lualatex") and shutil.which("pdftocairo") and shutil.which("kpsewhich")):
        return False
    found = subprocess.run(["kpsewhich", "standalone.cls", "tikz.sty"], capture_output=True, text=True).stdout.split()
    return len(found) == 2


@needs_pandoc(3, 1, 3)
@unittest.skipUnless(_can_draw_latex(), "needs lualatex with standalone and tikz, and poppler's pdftocairo")
class Pictures(unittest.TestCase):
    """Raw LaTeX pictures become SVG files beside the output, drawn with the document's own preamble."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-flat-pic-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        (self.directory / "doc.md").write_text("""---
title: Pics
header-includes: |
  \\usepackage{xcolor}
  \\newcommand{\\mydot}{\\textcolor{red}{$\\bullet$}}
---

Before.

\\begin{tikzpicture}
\\draw (0,0) circle (1cm);
\\node at (0,0) {\\mydot};
\\end{tikzpicture}

then a broken one:

\\begin{tikzpicture}
\\draw \\undefinedmacro;
\\end{tikzpicture}

After.
""", encoding="utf-8")

    def test_a_tikz_picture_becomes_an_svg_and_a_broken_one_is_reported(self):
        env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"]}
        result = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "--to", "gfm"], capture_output=True,
                                text=True, encoding="utf-8", cwd=self.directory, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        flat = (self.directory / "doc.gfm.md").read_text(encoding="utf-8")
        files = sorted(path.name for path in (self.directory / "doc.gfm_files").iterdir())
        self.assertEqual(len(files), 1, files)
        self.assertTrue(files[0].endswith(".svg"))
        self.assertIn(f"![](doc.gfm_files/{files[0]})", flat)
        self.assertIn("then a broken one:", flat)
        self.assertIn("After.", flat)
        self.assertRegex(result.stdout + result.stderr, r"WARN  raw: a LaTeX picture could not be drawn \(! Undefined control sequence")


if __name__ == "__main__":
    unittest.main()
