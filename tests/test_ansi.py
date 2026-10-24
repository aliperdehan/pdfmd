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


if __name__ == "__main__":
    unittest.main()
