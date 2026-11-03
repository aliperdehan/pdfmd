"""Obsidian's own syntax (entry 3ee): the flavour of a file, and the `%%comments%%` Obsidian hides (v3.32.20)."""

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
from pandoc_support import needs_pandoc  # noqa: E402
from pdfmd_obsidian import hide_comments  # noqa: E402


class HideComments(unittest.TestCase):
    def hidden(self, text):
        return hide_comments(text).text

    def shown(self, text):
        return hide_comments(text, show=True).text

    def test_an_inline_comment_goes_and_the_text_around_it_stays(self):
        self.assertEqual(self.hidden("a %%hid%% b\n"), "a  b\n")
        self.assertEqual(self.shown("a %%hid%% b\n"), "a <!-- hid --> b\n")

    def test_a_comment_at_the_end_of_a_line_leaves_no_trailing_spaces(self):
        self.assertEqual(self.hidden("text %%note%%\nnext\n"), "text\nnext\n")

    def test_a_comment_on_lines_of_its_own_takes_the_lines_with_it(self):
        text = "para\n\n%%\nmany\n\nlines\n%%\n\nafter\n"
        self.assertEqual(self.hidden(text), "para\n\n\nafter\n")
        self.assertEqual(self.shown(text), "para\n\n<!-- many\n\nlines -->\n\nafter\n")

    def test_a_comment_that_opens_a_line_and_has_text_after_it_does_not_swallow_the_text(self):
        self.assertEqual(self.hidden("%%a%% text\n"), " text\n")
        shown = self.shown("%%a%% text\n")
        self.assertTrue(shown.startswith("<span></span><!-- a -->"), shown)
        self.assertTrue(shown.endswith(" text\n"), shown)

    def test_an_inline_comment_with_a_blank_line_is_moved_to_a_block_of_its_own_when_shown(self):
        self.assertEqual(self.hidden("a %%x\n\ny%% b\n"), "a  b\n")
        self.assertEqual(self.shown("a %%x\n\ny%% b\n"), "a\n\n<!-- x\n\ny -->\n\nb\n")

    def test_the_end_of_an_html_comment_in_the_body_is_defused(self):
        self.assertEqual(self.shown("x %%a --> b%% y\n"), "x <!-- a -- > b --> y\n")
        self.assertEqual(self.shown("%%>x%%\n"), "<!-- >x -->\n")

    def test_code_math_front_matter_and_html_comments_are_not_looked_into(self):
        text = ("---\ntitle: a %% b\n---\n\n`%% x %%` and\n\n```\n%% y %%\n```\n\n~~~\n%% z\n~~~\n\n$a %% b$ and $$ c %% d $$\n\n"
                "<!-- %% in html %% -->\n")
        self.assertEqual(self.hidden(text), text)
        unclosed_fence = "```\n%% never closed\n"
        self.assertEqual(self.hidden(unclosed_fence), unclosed_fence)

    def test_a_percent_pair_with_no_mate_stays_and_its_line_is_reported(self):
        result = hide_comments("one\n%% oops\ntwo\n")
        self.assertEqual(result.text, "one\n%% oops\ntwo\n")
        self.assertEqual((result.count, result.unclosed), (0, [2]))
        self.assertEqual(hide_comments("a %%b%% c %%d\n").unclosed, [1])

    def test_nothing_to_do_without_a_percent_pair(self):
        self.assertEqual(hide_comments("50% and 100%\n").text, "50% and 100%\n")


class Flavour(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-flavour-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        pdfmd._VAULT_ROOTS.clear()
        pdfmd._FLAVOUR_TOLD.clear()
        self.addCleanup(pdfmd.FLAVOUR_CLI.update, {"name": None})
        (self.directory / "vault" / ".obsidian").mkdir(parents=True)
        (self.directory / "vault" / "deep" / "er").mkdir(parents=True)
        (self.directory / "plain").mkdir()

    def note(self, folder, text="Text\n"):
        path = self.directory / folder / "n.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_auto_is_obsidian_inside_a_vault_at_any_depth_and_pdfmd_outside(self):
        self.assertEqual(pdfmd.flavour_of(self.note("vault")), "obsidian")
        self.assertEqual(pdfmd.flavour_of(self.note("vault/deep/er")), "obsidian")
        self.assertEqual(pdfmd.flavour_of(self.note("plain")), "pdfmd")
        self.assertEqual(pdfmd.vault_root(self.note("vault/deep")), (self.directory / "vault").resolve())

    def test_the_setting_in_the_front_matter_in_either_spelling_beats_the_folder(self):
        for key in ("flavour", "flavor"):
            with self.subTest(key=key):
                inside = self.note("vault", f"---\npdfmd-options:\n  {key}: pandoc\n---\n\nText\n")
                self.assertEqual(pdfmd.flavour_of(inside), "pandoc")
                outside = self.note("plain", f"---\npdfmd-options:\n  {key}: Obsidian\n---\n\nText\n")
                self.assertEqual(pdfmd.flavour_of(outside), "obsidian")

    def test_the_command_line_beats_the_document(self):
        outside = self.note("plain", "---\npdfmd-options:\n  flavour: pandoc\n---\n\nText\n")
        pdfmd.FLAVOUR_CLI["name"] = "obsidian"
        self.assertEqual(pdfmd.flavour_of(outside), "obsidian")

    def test_an_unknown_word_is_told_once_and_taken_as_auto(self):
        path = self.note("vault", "---\npdfmd-options:\n  flavour: marp\n---\n\nText\n")
        import contextlib
        import io
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            self.assertEqual(pdfmd.flavour_of(path), "obsidian")
            self.assertEqual(pdfmd.flavour_of(path), "obsidian")
        self.assertEqual(said.getvalue().count("flavour: marp is not a flavour pdfmd knows"), 1)


@needs_pandoc(3, 1, 3)
class CommandLine(unittest.TestCase):
    NOTE = ("# Note\n\nStart %%an inline comment with @key and \\ref{x}%% and the end.\n\n%%\nA block comment\n\n# Not a heading\n%%\n\n"
            "Text after. `%% code %%` stays.\n\nLast %%trailing%%\n")

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-obsidian-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        (self.directory / "vault" / ".obsidian").mkdir(parents=True)
        (self.directory / "plain").mkdir()
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.directory / "config"),
                    "APPDATA": str(self.directory / "config")}

    def build(self, folder, text, *arguments):
        (self.directory / folder / "n.md").write_text(text, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "n.md", "-t", "html", *arguments], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory / folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.directory / folder / "n.html").read_text(encoding="utf-8"), done.stdout + done.stderr

    def test_in_a_vault_the_comments_are_hidden_and_what_is_in_them_decides_nothing(self):
        html, said = self.build("vault", self.NOTE, "-v")
        for gone in ("inline comment", "A block comment", "Not a heading", "trailing"):
            self.assertNotIn(gone, html)
        self.assertIn("Start", html)
        self.assertIn("and the end.", html)
        self.assertIn("%% code %%", html)
        self.assertIn("reading as gfm\n", said)            # the hidden \ref{x} and @key did not move the reader

    def test_show_comments_draws_them(self):
        html, _ = self.build("vault", self.NOTE, "--show-comments")
        self.assertIn("an inline comment with @key", html)
        self.assertIn("A block comment", html)
        self.assertNotIn("<h1 id=\"not-a-heading\"", html)

    def test_outside_a_vault_the_percent_signs_are_text(self):
        html, _ = self.build("plain", "# N\n\nA %%kept%% B\n")
        self.assertIn("%%kept%%", html)

    def test_the_flavour_turns_it_on_outside_a_vault_and_off_inside_one(self):
        html, _ = self.build("plain", "# N\n\nA %%gone%% B\n", "--flavour", "obsidian")
        self.assertNotIn("gone", html)
        html, _ = self.build("plain", "---\npdfmd-options:\n  flavor: obsidian\n---\n\nA %%gone%% B\n")
        self.assertNotIn("gone", html)
        html, _ = self.build("vault", "# N\n\nA %%kept%% B\n", "--flavor", "pandoc")
        self.assertIn("%%kept%%", html)
        html, _ = self.build("plain", "# N\n\nA %%gone%% B\n", "--flavour", "Obsidian")      # the word's case does not matter
        self.assertNotIn("gone", html)

    def test_a_note_with_properties_is_cleaned_too(self):
        html, _ = self.build("vault", "---\ntags: [a]\n---\n\nOne %%hidden%% two\n")
        self.assertNotIn("hidden", html)
        self.assertIn("One", html)

    def test_a_percent_pair_with_no_mate_is_a_warning_and_stays(self):
        html, said = self.build("vault", "# N\n\nOne\n\n%% oops\nrest\n")
        self.assertIn("a `%%` with no closing `%%`", said)
        self.assertIn("%% oops", html)

    def test_other_writers_agree(self):
        (self.directory / "vault" / "n.md").write_text("# N\n\nA %%gone%% B\n", encoding="utf-8")
        for target, suffix in (("latex", "tex"), ("typst", "typ")):
            with self.subTest(target=target):
                subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "n.md", "-t", target, "-o", f"n.{suffix}"],
                               capture_output=True, text=True, cwd=self.directory / "vault", env=self.env, check=True)
                self.assertNotIn("gone", (self.directory / "vault" / f"n.{suffix}").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
