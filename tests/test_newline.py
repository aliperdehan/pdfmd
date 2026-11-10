"""A single newline inside a paragraph (entry 3ee, v3.32.27): a line break in the obsidian flavour (as the vault's own
`strictLineBreaks` says), a space in the others, `single-newline` overriding both."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402
from pdfmd_flavours import PRESETS  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-newline-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        pdfmd._VAULT_ROOTS.clear()
        pdfmd._FLAVOUR_TOLD.clear()
        (self.directory / "vault" / ".obsidian").mkdir(parents=True)
        (self.directory / "plain").mkdir()

    def app(self, text):
        (self.directory / "vault" / ".obsidian" / "app.json").write_text(text, encoding="utf-8")

    def note(self, place, options="", name="n.md"):
        front = f"---\npdfmd-options:\n{options}---\n" if options else ""
        path = self.directory / place / name
        path.write_text(front + "a\nb\n", encoding="utf-8")
        return path


class Mode(Base):
    def test_the_presets_say_obsidian_breaks_and_the_rest_do_not(self):
        self.assertEqual({name: row.newline for name, row in PRESETS.items()},
                         {"pandoc": "soft", "gfm": "soft", "commonmark": "soft", "pdfmd": "soft", "obsidian": "hard"})

    def test_in_a_vault_the_flavours_default_and_the_vaults_own_setting_decide(self):
        note = self.note("vault")
        self.assertEqual(pdfmd.single_newline_mode(note), "hard")                # no app.json: Obsidian's default
        self.app("{}")
        self.assertEqual(pdfmd.single_newline_mode(note), "hard")
        self.app('{"strictLineBreaks": true}')
        self.assertEqual(pdfmd.single_newline_mode(note), "soft")
        self.app('{"strictLineBreaks": false}')
        self.assertEqual(pdfmd.single_newline_mode(note), "hard")
        self.app('{"strictLineBreaks": "yes"')                                   # broken JSON: the default, no crash
        self.assertEqual(pdfmd.single_newline_mode(note), "hard")

    def test_outside_a_vault_it_is_a_space_unless_the_flavour_or_the_setting_says_otherwise(self):
        self.assertEqual(pdfmd.single_newline_mode(self.note("plain")), "soft")
        self.assertEqual(pdfmd.single_newline_mode(self.note("plain", "  flavour: obsidian\n", "o.md")), "hard")
        self.assertEqual(pdfmd.single_newline_mode(self.note("plain", "  single-newline: Hard\n", "h.md")), "hard")

    def test_the_setting_wins_over_the_vault(self):
        self.app('{"strictLineBreaks": true}')
        self.assertEqual(pdfmd.single_newline_mode(self.note("vault", "  single-newline: hard\n")), "hard")
        self.app('{"strictLineBreaks": false}')
        self.assertEqual(pdfmd.single_newline_mode(self.note("vault", "  single-newline: soft\n", "s.md")), "soft")

    def test_the_vaults_setting_belongs_to_the_obsidian_flavour_only(self):
        self.app('{"strictLineBreaks": false}')
        self.assertEqual(pdfmd.single_newline_mode(self.note("vault", "  flavour: pdfmd\n")), "soft")
        self.assertEqual(pdfmd.single_newline_mode(self.note("vault", "  flavour: gfm\n", "g.md")), "soft")

    def test_a_word_that_is_none_is_told_once_and_the_default_is_used(self):
        note = self.note("plain", "  single-newline: maybe\n")
        self.assertEqual(pdfmd.single_newline_mode(note), "soft")


class Reader(Base):
    def test_the_reader_gets_the_extension_whatever_the_reader_is(self):
        read = lambda path, given=None: pdfmd.resolve_from_format(path, given, [])[0]
        self.assertEqual(read(self.note("plain")), "gfm+smart+implicit_figures")
        self.assertEqual(read(self.note("vault")), "gfm+smart+implicit_figures+hard_line_breaks")
        self.assertEqual(read(self.note("plain", "  single-newline: hard\n", "h.md")),
                         "markdown+autolink_bare_uris+emoji+hard_line_breaks")        # front matter: Pandoc's Markdown
        self.assertEqual(read(self.note("plain", "  flavour: pandoc\n  single-newline: hard\n", "p.md")), "markdown+hard_line_breaks")
        self.assertEqual(read(self.note("plain", "  flavour: gfm+smart\n  single-newline: hard\n", "s.md")), "gfm+smart+hard_line_breaks")

    def test_from_on_the_command_line_wins(self):
        self.assertEqual(pdfmd.resolve_from_format(self.note("vault"), "gfm", [])[0], "gfm")


@needs_pandoc(3, 1, 3)
class Build(Base):
    def build(self, place, target="html", text=None, *arguments):
        path = self.directory / place / "n.md"
        if text is not None:
            path.write_text(text, encoding="utf-8")
        env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.directory / "config"), "APPDATA": str(self.directory / "config")}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "n.md", "-t", target, "--no-stamp", *arguments],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.directory / place, env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.directory / place / f"n.{ {'latex': 'tex', 'typst': 'typ'}.get(target, target) }").read_text(encoding="utf-8")

    SOURCE = ("# T\n\nline one\nline two\n\n> [!note] Title\n> body one\n> body two\n\n- item a\n  wraps here\n\n"
              "Math $a\n+b$ and\n\n```\ncode\nlines\n```\n")

    def test_a_vault_note_breaks_every_line_and_a_callout_keeps_its_title(self):
        html = self.build("vault", "html", self.SOURCE)
        self.assertIn("line one<br />\nline two", html)
        self.assertIn("body one<br />\nbody two", html)
        self.assertIn("item a<br />\nwraps here", html)
        self.assertIn('<div class="callout-title">\n<p><strong>Title</strong></p>', html)
        self.assertIn("code\nlines", html)                                        # code is not touched
        self.assertNotIn("code<br", html)

    def test_the_vault_can_ask_for_strict_line_breaks_and_a_document_can_ask_again(self):
        self.app('{"strictLineBreaks": true}')
        self.assertIn("line one line two", self.build("vault", "html", self.SOURCE))
        text = "---\npdfmd-options:\n  single-newline: hard\n---\n" + self.SOURCE
        self.assertIn("line one<br />\nline two", self.build("vault", "html", text))

    def test_outside_a_vault_a_newline_is_a_space_and_every_writer_takes_the_break(self):
        self.assertIn("line one line two", self.build("plain", "html", self.SOURCE))
        text = "---\npdfmd-options:\n  single-newline: hard\n---\nline one\nline two\n"
        self.assertIn("line one\\\\\nline two", self.build("plain", "latex", text))
        self.assertIn("line one \\ line two", self.build("plain", "typst", text))


if __name__ == "__main__":
    unittest.main()
