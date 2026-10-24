"""`--to ansi` and `--view` (v3.30.3): the renderer (pdfmd_ansi) on its own, then the whole pipeline."""

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

from pdfmd_ansi import render, strip_ansi, visible_width           # noqa: E402
from pdfmd_ansi.native import from_markdown                       # noqa: E402
from pdfmd_ansi.text import Run, clean, text_width, wrap          # noqa: E402

ESC = "\x1b"
TABLE = ("| Ion | Charge | Note |\n|:----|-------:|:----:|\n| Mg²⁺ | +2 | alkaline earth |\n"
         "| Na⁺ | +1 | alkali metal with a rather long description that must wrap |\n| 日本語 | 0 | wide |\n")


def drawn(markdown: str, width: int = 60, color: bool = False, **options) -> str:
    return render(from_markdown(markdown), width=width, color=color, **options)


class Text(unittest.TestCase):
    def test_widths_count_cells_not_characters(self):
        self.assertEqual(text_width("abc"), 3)
        self.assertEqual(text_width("日本語"), 6)
        self.assertEqual(text_width("é"), 1)                       # a combining accent takes no cell
        self.assertEqual(visible_width(f"{ESC}[1mbold{ESC}[0m"), 4)
        self.assertEqual(strip_ansi(f"{ESC}]8;;http://x{ESC}\\link{ESC}]8;;{ESC}\\"), "link")

    def test_wrapping_keeps_words_and_cuts_a_word_longer_than_a_line(self):
        lines = wrap([Run("aaa bbb ccc ddd")], 7)
        self.assertEqual(["".join(run.text for run in line) for line in lines], ["aaa bbb", "ccc ddd"])
        lines = wrap([Run("x " + "y" * 25)], 10)
        self.assertEqual(["".join(run.text for run in line) for line in lines], ["x", "yyyyyyyyyy", "yyyyyyyyyy", "yyyyy"])      # a long word starts a line of its own
        self.assertTrue(all(sum(text_width(run.text) for run in line) <= 10 for line in lines))

    def test_a_document_cannot_send_escape_codes_to_the_terminal(self):
        self.assertEqual(clean(f"a{ESC}[31mb\x07c‮d"), "a[31mbcd")
        shown = drawn(f"hello {ESC}[2J{ESC}]0;title\x07 `x{ESC}y`\n\n```\n{ESC}[31mred\n```\n", color=True)
        self.assertNotIn(f"{ESC}[2J", shown)
        self.assertNotIn(f"{ESC}]0;", shown)
        self.assertNotIn(f"{ESC}[31m", shown)


class Blocks(unittest.TestCase):
    def test_inline_styles_become_escape_codes_and_nothing_with_color_off(self):
        source = "**bold** *italic* `code` ~~gone~~ [site](https://example.org/a)\n"
        plain = drawn(source)
        self.assertNotIn(ESC, plain)
        self.assertEqual(plain.strip(), "bold italic code gone site (https://example.org/a)")
        styled = drawn(source, color=True)
        for code in ("1m", "3m", "9m"):
            self.assertIn(f"{ESC}[{code}", styled)
        self.assertEqual(strip_ansi(styled), plain)

    def test_a_link_is_an_osc8_hyperlink_when_the_terminal_draws_them(self):
        linked = drawn("[site](https://example.org/a)\n", color=True, hyperlinks=True)
        self.assertIn(f"{ESC}]8;;https://example.org/a{ESC}\\", linked)
        self.assertNotIn("(https://example.org/a)", strip_ansi(linked))

    def test_a_table_is_a_grid_whose_lines_all_have_the_same_width_and_fit(self):
        for width in (80, 44, 30):
            lines = drawn(TABLE, width=width).splitlines()
            self.assertEqual({visible_width(line) for line in lines}, {visible_width(lines[0])}, width)
            self.assertLessEqual(visible_width(lines[0]), width)
            self.assertTrue(lines[0].startswith("┌") and lines[-1].startswith("└"))
            self.assertEqual(sum(line.startswith("├") for line in lines), 3)             # a rule between all rows
        text = drawn(TABLE, width=80)
        self.assertIn("│ Mg²⁺   │", text)
        self.assertIn("│ 日本語 │", text)
        self.assertRegex(text, r"│ +\+2 │")                                              # right-aligned column

    def test_the_header_row_is_bold_and_a_wide_table_wraps_its_cells(self):
        styled = drawn(TABLE, width=40, color=True)
        self.assertIn(f"{ESC}[1mIon", styled)
        body = strip_ansi(styled)
        self.assertIn("must wrap", body.replace("│", " ") + " ".join(body.split()))
        self.assertGreater(len(body.splitlines()), 9)

    def test_lists_quotes_code_headings_and_rules(self):
        text = drawn("# Title\n\n> quoted\n\n- one\n- two\n  - nested\n\n3. three\n4. four\n\n```\ncode here\n```\n\n---\n")
        self.assertIn("Title", text)
        self.assertIn("• one", text)
        self.assertIn("  ◦ nested", text)
        self.assertIn("3. three", text)
        self.assertIn("│ quoted", text)
        self.assertIn("  code here", text)
        self.assertIn("─" * 20, text)

    def test_math_goes_through_the_callback_else_stays_as_tex(self):
        self.assertIn("x^2", drawn("a $x^2$ b\n"))
        shown = drawn("a $x^2$ b\n", math=lambda tex, display: [[("x", "i"), ("²", "")]])
        self.assertIn("x²", shown)
        styled = drawn("a $x^2$ b\n", color=True, math=lambda tex, display: [[("x", "i"), ("²", "")]])
        self.assertIn(f"{ESC}[3mx", styled)

    def test_a_formula_on_its_own_line_is_centred(self):
        line = [line for line in drawn("$$y$$\n", width=40, math=lambda tex, display: [[("y", "")]]).splitlines() if line][0]
        self.assertEqual(len(line) - len(line.lstrip()), 19)

    def test_a_title_block_comes_from_the_front_matter(self):
        text = drawn("---\ntitle: Report\n---\n\nBody\n")
        self.assertTrue(text.startswith("Report\n\nBody"), text)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Pipeline(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-ansi-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "a.md").write_text("---\ntitle: A *test*\n---\n\n# Heading\n\nSome **bold** and $\\Delta G = -RT\\ln K$ "
                                             "and Mg^2+^.\n\n" + TABLE, encoding="utf-8")
        (self.directory / "b.md").write_text("Second file.\n", encoding="utf-8")

    def run_pdfmd(self, *args: str, stdin: str | None = None, env: dict | None = None, path: str | None = None):
        environment = {key: value for key, value in os.environ.items() if key not in ("NO_COLOR", "PAGER", "PDFMD_PAGER")}
        environment.update({"PDFMD_CONFIG": "", **(env or {})})
        if path is not None:
            environment["PATH"] = path
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.directory, input=stdin,
                              capture_output=True, text=True, env=environment)

    def test_to_ansi_writes_a_file_with_styling_and_math_as_text(self):
        done = self.run_pdfmd("a.md", "--to", "ansi", "--width", "70", "--no-stamp", "--no-backup")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (self.directory / "a.ansi").read_text(encoding="utf-8")
        self.assertIn(f"{ESC}[1m", text)
        plain = strip_ansi(text)
        self.assertIn("Heading", plain)                              # a heading stays a heading: the title is not promoted
        self.assertIn("ΔG = − RT ln K", plain)
        self.assertIn("Mg²⁺", plain)
        self.assertIn("┌", plain)
        self.assertLessEqual(max(visible_width(line) for line in text.splitlines()), 70)

    def test_an_ansi_extension_selects_the_format(self):
        done = self.run_pdfmd("a.md", "-o", "x.ansi", "--no-stamp", "--no-backup", "--color", "never")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn(ESC, (self.directory / "x.ansi").read_text(encoding="utf-8"))

    def test_view_prints_styled_text_even_into_a_pipe_and_keeps_the_notes_off_stdout(self):
        done = self.run_pdfmd("--view", "a.md", "--width", "70")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"{ESC}[1m", done.stdout)
        self.assertIn("┌", done.stdout)
        self.assertNotIn("OK ", done.stdout)
        self.assertNotIn("DEFAULTS", done.stdout + done.stderr)
        self.assertEqual(sorted(path.name for path in self.directory.iterdir()), ["a.md", "b.md"])     # nothing left behind

    def test_no_color_and_color_never_strip_the_codes_and_color_always_restores_them(self):
        self.assertNotIn(ESC, self.run_pdfmd("--view", "a.md", env={"NO_COLOR": "1"}).stdout)
        self.assertNotIn(ESC, self.run_pdfmd("--view", "a.md", "--color", "never").stdout)
        self.assertIn(ESC, self.run_pdfmd("--view", "a.md", "--color", "always", env={"NO_COLOR": "1"}).stdout)

    def test_dash_o_dash_is_stdout_and_plain_in_a_pipe_unless_asked(self):
        done = self.run_pdfmd("a.md", "--to", "ansi", "-o", "-")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn(ESC, done.stdout)
        self.assertIn("┌", done.stdout)
        self.assertIn(ESC, self.run_pdfmd("a.md", "--to", "ansi", "-o", "-", "--color", "always").stdout)
        self.assertEqual(sorted(path.name for path in self.directory.iterdir()), ["a.md", "b.md"])
        done = self.run_pdfmd("a.md", "--to", "txt", "-o", "-")                       # any text format
        self.assertIn("Heading", done.stdout)
        self.assertNotIn(ESC, done.stdout)

    def test_several_files_are_one_stream_with_a_rule_naming_each(self):
        done = self.run_pdfmd("--view", "a.md", "b.md", "--color", "never")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout, r"── a\.md ─+\n")
        self.assertRegex(done.stdout, r"── b\.md ─+\n")
        self.assertLess(done.stdout.index("a.md"), done.stdout.index("b.md"))
        self.assertNotIn("── ", self.run_pdfmd("--view", "b.md", "--color", "never").stdout)      # one file: no rule

    def test_a_pipe_and_a_dash_are_read_as_markdown(self):
        for arguments in (("--view",), ("--view", "-")):
            done = self.run_pdfmd(*arguments, "--color", "never", stdin="# Hi\n\n| a | b |\n|---|---|\n| 1 | **2** |\n")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("│ 1 │ 2 │", done.stdout)
        self.assertEqual(sorted(path.name for path in self.directory.glob(".*") if path.is_file()), [])

    def test_view_with_another_format_or_a_file_output_is_refused_or_saves(self):
        done = self.run_pdfmd("--view", "a.md", "--to", "docx")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--to ansi", done.stdout + done.stderr)
        done = self.run_pdfmd("--view", "a.md", "-o", "saved.ansi", "--no-stamp", "--no-backup")     # -o replaces the viewing
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.count("┌"), 0)
        self.assertTrue((self.directory / "saved.ansi").is_file())

    def test_the_pager_is_used_on_a_terminal_only_and_no_pager_prints_everything(self):
        done = self.run_pdfmd("--view", "a.md", "--no-pager", "--color", "never", env={"PDFMD_PAGER": "false"})
        self.assertIn("Heading", done.stdout)

    def test_without_pandoc_the_built_in_parser_draws_it(self):
        done = self.run_pdfmd("--view", "a.md", "--color", "never", "--width", "60", path=str(self.directory / "nobin"))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("┌", done.stdout)
        self.assertIn("Mg²⁺", done.stdout)
        self.assertIn("built-in parser", done.stderr)


class Setup(unittest.TestCase):
    def test_the_flags_are_in_the_help_the_setup_and_the_packages(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--help", "view"], capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": ""})
        for flag in ("--view", "--pager", "--color", "--width"):
            self.assertIn(flag, done.stdout)



# --- spanning cells, coloured code, stacked math, a pager command setting ------------------------------------------

from pdfmd_ansi import highlight, mathbox               # noqa: E402


def inlines(text: str) -> list:
    out = []
    for number, word in enumerate(text.split(" ")):
        if number:
            out.append({"t": "Space"})
        out.append({"t": "Str", "c": word})
    return out


def cell(text: str, rowspan: int = 1, colspan: int = 1, align: str = "AlignDefault") -> list:
    return [["", [], []], {"t": align}, rowspan, colspan, [{"t": "Plain", "c": inlines(text)}] if text else []]


def row(*cells) -> list:
    return [["", [], []], list(cells)]


def table_document(columns: int, head: list, body: list, caption: list | None = None) -> dict:
    table = {"t": "Table", "c": [["", [], []], [None, caption or []], [[{"t": "AlignDefault"}, {"t": "ColWidthDefault"}]] * columns,
                                 [["", [], []], head], [[["", [], []], 0, [], body]], [["", [], []], []]]}
    return {"pandoc-api-version": [1, 23], "meta": {}, "blocks": [table]}


def grid(document: dict, width: int = 60) -> str:
    return render(document, width=width, color=False)


class SpanningCells(unittest.TestCase):
    """A cell with a colspan or a rowspan is drawn across the merged columns and rows: its text wraps to the merged width, the
    borders inside it are left out, and every crossing is the box character its neighbours ask for."""

    def test_a_header_over_two_columns(self):
        document = table_document(3, [row(cell("Group", colspan=2), cell("Other"))],
                                  [row(cell("a"), cell("b"), cell("c")), row(cell("d"), cell("e"), cell("f"))])
        self.assertEqual(grid(document), "\n".join([
            "┌───────┬───────┐",
            "│ Group │ Other │",
            "├───┬───┼───────┤",
            "│ a │ b │ c     │",
            "├───┼───┼───────┤",
            "│ d │ e │ f     │",
            "└───┴───┴───────┘", ""]))

    def test_a_cell_two_rows_tall(self):
        document = table_document(3, [row(cell("A"), cell("B"), cell("C"))],
                                  [row(cell("tall cell", rowspan=2), cell("b1"), cell("c1")), row(cell("b2"), cell("c2"))])
        self.assertEqual(grid(document), "\n".join([
            "┌───────────┬────┬────┐",
            "│ A         │ B  │ C  │",
            "├───────────┼────┼────┤",
            "│ tall cell │ b1 │ c1 │",
            "│           ├────┼────┤",
            "│           │ b2 │ c2 │",
            "└───────────┴────┴────┘", ""]))

    def test_both_at_once(self):
        document = table_document(
            4, [row(cell("Group", colspan=2), cell("X", rowspan=2), cell("Y")), row(cell("a"), cell("b"), cell("y"))],
            [row(cell("big block", rowspan=2, colspan=2), cell("p"), cell("q")), row(cell("r"), cell("s"))])
        self.assertEqual(grid(document), "\n".join([
            "┌───────────┬───┬───┐",
            "│ Group     │ X │ Y │",
            "├─────┬─────┤   ├───┤",
            "│ a   │ b   │   │ y │",
            "├─────┴─────┼───┼───┤",
            "│ big block │ p │ q │",
            "│           ├───┼───┤",
            "│           │ r │ s │",
            "└───────────┴───┴───┘", ""]))

    def test_the_text_of_a_merged_cell_wraps_to_the_merged_width(self):
        document = table_document(3, [row(cell("A long spanning heading that wraps around two columns", colspan=2), cell("Z"))],
                                  [row(cell("a"), cell("b"), cell("c"))])
        lines = grid(document, width=40).splitlines()
        self.assertEqual(lines[1:3], ["│ A long spanning heading that     │ Z │", "│ wraps around two columns         │   │"])
        self.assertEqual({visible_width(line) for line in lines}, {visible_width(lines[0])})
        self.assertLessEqual(visible_width(lines[0]), 40)

    def test_a_tall_cell_with_more_text_than_its_rows_makes_the_last_row_taller(self):
        document = table_document(2, [row(cell("H"), cell("I"))],
                                  [row(cell("one two three four five six", rowspan=2), cell("x")), row(cell("y"))])
        lines = grid(document, width=24).splitlines()
        self.assertEqual({visible_width(line) for line in lines}, {visible_width(lines[0])})
        text = " ".join(line.replace("│", " ").replace("├", " ").replace("┼", " ").replace("┤", " ") for line in lines)
        for word in "one two three four five six".split():
            self.assertIn(word, text)

    def test_the_header_row_stays_bold_across_a_span(self):
        document = table_document(2, [row(cell("Wide", colspan=2))], [row(cell("a"), cell("b"))])
        styled = render(document, width=40, color=True)
        self.assertIn(f"{ESC}[1mWide", styled)

    def test_a_table_without_spans_is_drawn_as_before(self):
        document = table_document(2, [row(cell("H1"), cell("H2"))], [row(cell("x"), cell("y"))])
        self.assertEqual(grid(document), "┌────┬────┐\n│ H1 │ H2 │\n├────┼────┤\n│ x  │ y  │\n└────┴────┘\n")

    def test_a_row_with_too_few_cells_is_padded_and_a_span_past_the_edge_is_cut(self):
        document = table_document(3, [row(cell("A"), cell("B"), cell("C"))], [row(cell("only")), row(cell("wide", colspan=9))])
        lines = grid(document).splitlines()
        self.assertEqual({visible_width(line) for line in lines}, {visible_width(lines[0])})
        self.assertEqual(sum(line.startswith("├") for line in lines), 2)


class CodeColours(unittest.TestCase):
    def test_each_language_has_keywords_strings_comments_and_numbers(self):
        samples = {
            "python": ('def f(x):\n    return "a" + str(3.5)  # note\n', {"def": "kw", '"a"': "str", "3.5": "num", "# note": "com"}),
            "bash": ('if [ -n "$X" ]; then echo 5 # hi\nfi\n', {"if": "kw", '"$X"': "str", "5": "num", "# hi": "com"}),
            "json": ('{"a": [1, 2.5, true, null]}\n', {'"a"': "str", "2.5": "num", "true": "kw", "null": "kw"}),
            "yaml": ('name: "x" # c\ncount: 3\nok: true\n', {"name": "kw", '"x"': "str", "# c": "com", "3": "num", "true": "kw"}),
            "c": ('#include <stdio.h>\nint main(void) { /* c */ return 0x1F; } // end\n',
                  {"#include": "kw", "int": "kw", "/* c */": "com", "0x1F": "num", "// end": "com"}),
            "cpp": ('auto x = std::string("s"); // c\nconst int n = 7;\n', {"auto": "kw", '"s"': "str", "// c": "com", "7": "num"}),
            "java": ('public class A { String s = "t"; /* c */ int n = 1; }\n', {"public": "kw", '"t"': "str", "/* c */": "com", "1": "num"}),
            "javascript": ('const t = `a ${b}`; // c\nlet n = 10;\n', {"const": "kw", "`a ${b}`": "str", "// c": "com", "10": "num"}),
            "rust": ("fn f<'a>(x: &'a str) -> char { 'c' } // c\nlet n = 2;\n", {"fn": "kw", "'c'": "str", "// c": "com", "2": "num"}),
            "go": ('package main\nvar s = `raw\nline` // c\nfunc main() { x := 4 }\n',
                   {"package": "kw", "`raw": "str", "line`": "str", "// c": "com", "4": "num", "func": "kw"}),
        }
        for language, (code, expected) in samples.items():
            with self.subTest(language=language):
                found = {text: kind for line in highlight.tokens(language, code) for text, kind in line if kind}
                for text, kind in expected.items():
                    self.assertEqual(found.get(text), kind, f"{text!r} in {found}")

    def test_what_is_not_a_string_comment_or_keyword_stays_plain(self):
        found = {text: kind for line in highlight.tokens("python", 'x = "# not a comment"  # but this is\nlambda_ = 1\nprint("if")\n')
                 for text, kind in line if kind}
        self.assertEqual(found['"# not a comment"'], "str")
        self.assertEqual(found["# but this is"], "com")
        self.assertNotIn("lambda_", found)
        self.assertNotIn("print", found)
        self.assertNotIn("if", found)                                        # (it is inside a string)
        self.assertEqual("".join(text for line in highlight.tokens("go", "a := 1\n\nb := 2\n") for text, _ in line), "a := 1b := 2")

    def test_a_triple_quoted_string_and_a_block_comment_run_over_lines(self):
        lines = highlight.tokens("python", 'x = """a\nb"""\ny = 1\n')
        self.assertEqual([kind for text, kind in lines[0] if kind], ["str"])
        self.assertEqual(lines[1], [('b"""', "str")])
        self.assertEqual(lines[2][-1], ("1", "num"))
        lines = highlight.tokens("c", "/* a\n b */ int x;\n")
        self.assertEqual([lines[0][0], lines[1][0]], [("/* a", "com"), (" b */", "com")])

    def test_an_unknown_language_is_not_coloured(self):
        self.assertIsNone(highlight.tokens("brainfuck", "+++"))
        self.assertIsNone(highlight.tokens(None, "x = 1"))
        self.assertIsNone(highlight.language_of(["sourceCode"]))
        self.assertEqual(highlight.language_of(["sourceCode", "Python"]), "python")
        self.assertEqual(highlight.language_of(["{.js}"]), "js")

    def test_a_fenced_block_with_a_language_gets_colour_codes_and_none_without_colour(self):
        source = '```python\ndef f(x):\n    return "a" + 3.5  # note\n```\n'
        coloured = drawn(source, color=True)
        for palette in ("38;5;176", "38;5;108", "38;5;244", "38;5;74"):
            self.assertIn(f"{ESC}[{palette}m", coloured)
        plain = drawn(source, color=False)
        self.assertNotIn(ESC, plain)
        self.assertEqual(strip_ansi(coloured), plain)                           # the same text, only the codes differ
        self.assertIn('  def f(x):\n      return "a" + 3.5  # note', plain)

    def test_a_block_without_a_language_or_with_an_unknown_one_is_as_it_was(self):
        for fence in ("```", "```brainfuck", "```text"):
            with self.subTest(fence=fence):
                coloured = drawn(f"{fence}\nx = 1  # no\n```\n", color=True)
                self.assertEqual(coloured, f"{ESC}[38;5;173m  x = 1  # no{ESC}[0m\n")

    def test_the_text_of_the_code_cannot_send_escape_codes(self):
        shown = drawn(f'```python\nx = "{ESC}[2J" # {ESC}]0;t\x07\n```\n', color=True)
        self.assertNotIn(f"{ESC}[2J", shown)
        self.assertNotIn(f"{ESC}]0;", shown)


class StackedMath(unittest.TestCase):
    @staticmethod
    def linear(tex: str, display: bool):
        shown = tex.replace("\\alpha", "α").replace("\\pm", "±").replace("\\to", "→").replace("\\infty", "∞")
        shown = shown.replace("{", "").replace("}", "")
        return [[(shown, "")]]

    def rows(self, tex: str):
        found = mathbox.stacked(tex, self.linear)
        return None if found is None else ["".join(text for text, _ in row) for row in found]

    def test_a_fraction_has_a_bar_as_wide_as_the_wider_part_and_a_cell_on_each_side(self):
        self.assertEqual(self.rows(r"\frac{a+b}{c}"), [" a+b", "─────", "  c"])
        self.assertEqual(self.rows(r"\frac{x}{yy}"), [" x", "────", " yy"])
        self.assertEqual(self.rows(r"\frac12"), [" 1", "───", " 2"])

    def test_a_fraction_among_text_is_joined_on_its_bar(self):
        self.assertEqual(self.rows(r"E = \frac{1}{2} m v^2"), ["     1", "E = ─── m v^2", "     2"])

    def test_a_square_root_has_an_overbar_and_an_index_goes_in_front(self):
        self.assertEqual(self.rows(r"\sqrt{x+1}"), [" ▁▁▁▁", "√ x+1"])
        self.assertEqual(self.rows(r"\sqrt[3]{x}"), ["  ▁▁", "³√ x"])

    def test_sums_and_integrals_have_their_limits_above_and_below(self):
        self.assertEqual(self.rows(r"\sum_{i=1}^{n} x_i"), [" n", " ∑ x_i", "i=1"])
        self.assertEqual(self.rows(r"\int_0^\infty f"), ["∞", "∫ f", "0"])
        self.assertEqual(self.rows(r"\prod_{k=1} x"), [" ∏ x", "k=1"])
        self.assertEqual(self.rows(r"\lim_{x \to 0} y"), [" lim y", "x → 0"])

    def test_boxes_nest(self):
        self.assertEqual(self.rows(r"\frac{\sqrt{a}}{\frac{b}{c}}"), ["  ▁▁", " √ a", "─────", "  b", " ───", "  c"])

    def test_what_cannot_be_stacked_is_left_to_the_linear_form(self):
        for tex in (r"x^2 + y^2", r"\begin{aligned} \frac{a}{b} \end{aligned}", r"\frac{a}{b}^2", r"\sqrt{x}_i", r"\frac{a}{b",
                    r"\frac{a}{b} \\ c", r"\sum x_i", r"\frac{a}{b} & c"):
            with self.subTest(tex=tex):
                self.assertIsNone(self.rows(tex))

    def test_a_piece_the_linear_converter_cannot_read_gives_up_the_whole_formula(self):
        self.assertIsNone(mathbox.stacked(r"\frac{a}{b}", lambda tex, display: None))
        self.assertIsNone(mathbox.stacked(r"\frac{a}{b} + c", lambda tex, display: [[("a", "")], [("b", "")]]))

    def test_the_renderer_stacks_a_display_formula_on_its_own_and_centres_it_as_one_block(self):
        shown = drawn("$$\\frac{a+b}{c}$$\n", width=21, math=self.linear)
        self.assertEqual(shown.splitlines(), ["         a+b", "        ─────", "          c"])
        widths = {len(line) - len(line.lstrip()) for line in shown.splitlines() if line.strip().startswith("a")}
        self.assertEqual(len(widths), 1)

    def test_inline_math_and_a_formula_inside_a_sentence_stay_linear(self):
        for source in ("so $\\frac{a}{b}$ here\n", "so $$\\frac{a}{b}$$ here\n"):
            shown = drawn(source, math=self.linear)
            self.assertEqual(shown.strip(), "so \\fracab here")          # what the linear converter made of it, on one line
            self.assertNotIn("─", shown)

    def test_a_formula_wider_than_the_line_is_linear(self):
        shown = drawn("$$\\frac{" + "a" * 30 + "}{b}$$\n", width=20, math=self.linear)
        self.assertNotIn("─", shown)

    def test_without_a_math_callback_or_with_stacking_off_nothing_is_stacked(self):
        self.assertNotIn("─", drawn("$$\\frac{a}{b}$$\n"))
        self.assertNotIn("─", drawn("$$\\frac{a}{b}$$\n", math=self.linear, stacked=False))

    def test_variables_keep_their_italics_in_a_stacked_formula(self):
        shown = drawn("$$\\frac{a}{b}$$\n", color=True, math=lambda tex, display: [[(tex.replace("{", "").replace("}", ""), "i")]])
        self.assertIn(f"{ESC}[3ma", shown)



GRID = """+---------+---------+
| Group             |
+=========+=========+
| a       | b       |
+---------+---------+
| tall    | x       |
|         +---------+
|         | y       |
+---------+---------+
"""


class PagerCommand(unittest.TestCase):
    """`pager_command` beside the on/off `pager`: the environment wins, then the setting, then `less -FRX`."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-pager-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        saved = {key: os.environ.pop(key, None) for key in ("PDFMD_PAGER", "PAGER", "PDFMD_CONFIG")}
        os.environ["PDFMD_CONFIG"] = ""
        self.addCleanup(lambda: [os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
                                 for key, value in saved.items()])

    def document(self, front: str) -> Path:
        path = self.directory / "d.md"
        path.write_text(f"---\ntitle: T\n{front}---\n\nText\n", encoding="utf-8")
        return path

    def test_the_order(self):
        import pdfmd
        self.assertEqual(pdfmd.pager_command(), ["less", "-FRX"])
        self.assertEqual(pdfmd.pager_command("bat --paging=always"), ["bat", "--paging=always"])
        os.environ["PAGER"] = "more"
        self.assertEqual(pdfmd.pager_command("bat"), ["more"])                      # $PAGER wins over the setting
        os.environ["PDFMD_PAGER"] = "most -s"
        self.assertEqual(pdfmd.pager_command("bat"), ["most", "-s"])                # $PDFMD_PAGER over both

    def test_the_setting_is_read_from_the_document_in_either_spelling_and_as_a_list(self):
        import pdfmd
        for front, expected in (("pdfmd-options:\n  pager_command: bat --paging=always\n", "bat --paging=always"),
                                ("pdfmd-options:\n  pager-command: less -R\n", "less -R"),
                                ("pdfmd-options:\n  pager_command: [bat, --style, plain file]\n", "bat --style 'plain file'"),
                                ("pdfmd-options:\n  pager: false\n", ""), ("", "")):
            with self.subTest(front=front):
                self.assertEqual(pdfmd.view_pager_setting(self.document(front)), expected)

    def test_the_text_goes_through_the_setting_and_the_environment_overrides_it(self):
        import pdfmd
        if sys.platform == "win32":
            self.skipTest("needs sh")
        one, two = self.directory / "one.txt", self.directory / "two.txt"
        pdfmd.run_pager("hello\n", f"sh -c 'cat > {one}'")
        self.assertEqual(one.read_text(encoding="utf-8"), "hello\n")
        os.environ["PDFMD_PAGER"] = f"sh -c 'cat > {two}'"
        pdfmd.run_pager("again\n", f"sh -c 'cat > {one}'")
        self.assertEqual(two.read_text(encoding="utf-8"), "again\n")
        self.assertEqual(one.read_text(encoding="utf-8"), "hello\n")                 # the setting was not used
        os.environ["PDFMD_PAGER"] = "pdfmd-no-such-pager"
        with mock.patch.object(sys.stdout, "write") as written:
            pdfmd.run_pager("plain\n")                                              # no such program: printed directly
        written.assert_called_with("plain\n")

    def test_the_setting_has_a_row_in_the_setup_and_a_name_in_the_options(self):
        from pdfmd_setup import inventory, registry
        rows = {setting.key: setting for setting in registry.settings_for(("lua",))}
        self.assertIn("options.pager_command", rows)
        self.assertIn("less -FRX", rows["options.pager_command"].unset)
        self.assertEqual(inventory.OPTIONS["pager_command"], "options.pager_command")
        self.assertEqual(inventory.OPTIONS["pager-command"], "options.pager_command")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class PipelineBlocks(unittest.TestCase):
    """Spanning cells, coloured code and stacked math through the whole of pdfmd (Pandoc's AST, ansi_math)."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-ansi-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "m.md").write_text(
            "---\ntitle: M\n---\n\n$$\\frac{a+b}{c}$$\n\nInline $\\frac{a}{b}$ stays.\n\n```python\nx = 1  # note\n```\n\n" + GRID,
            encoding="utf-8")

    def view(self, *args: str):
        environment = {key: value for key, value in os.environ.items() if key not in ("NO_COLOR", "PAGER", "PDFMD_PAGER")}
        environment["PDFMD_CONFIG"] = ""
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--view", "m.md", "--width", "50", *args], cwd=self.directory,
                              capture_output=True, text=True, env=environment)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_a_fraction_is_stacked_and_the_inline_one_is_not(self):
        shown = self.view("--color", "never").splitlines()
        bar = next(index for index, line in enumerate(shown) if "─────" in line and "a" not in line and "┬" not in line)
        self.assertEqual((shown[bar - 1].strip(), shown[bar + 1].strip()), ("a + b", "c"))
        self.assertTrue(any("Inline" in line and "a/b" in line for line in shown), shown)

    def test_code_is_coloured_with_colour_and_plain_without(self):
        coloured = self.view("--color", "always")
        self.assertIn(f"{ESC}[38;5;244m# note", coloured)
        self.assertIn(f"{ESC}[38;5;74m1", coloured)
        plain = self.view("--color", "never")
        self.assertNotIn(ESC, plain)
        self.assertIn("  x = 1  # note", plain)

    def test_a_grid_table_with_spans_is_drawn_with_the_spans(self):
        shown = self.view("--color", "never").splitlines()
        top = next(index for index, line in enumerate(shown) if line.startswith("┌"))
        self.assertNotIn("┬", shown[top])                                           # the header cell spans both columns
        self.assertIn("Group", shown[top + 1])
        self.assertEqual(shown[top + 1].count("│"), 2)
        joined = "\n".join(shown)
        self.assertRegex(joined, r"│ tall +│ x +│\n│ +├─+┤\n│ +│ y +│")             # the tall cell's right neighbours are two rows


if __name__ == "__main__":
    unittest.main()
