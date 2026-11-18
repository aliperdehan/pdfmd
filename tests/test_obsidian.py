"""Obsidian's own syntax (entry 3ee): the flavour of a file, and the `%%comments%%` Obsidian hides (v3.32.20)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
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

    def test_indented_code_keeps_percent_delimiters(self):
        text = ("# Heading\n    %% code after heading %%\n\n"
                "Paragraph\n    continuation %%prose%%\n\n"
                "    %% literal %%\n\n\t%% also literal\n\nEnd %%hidden%%\n")
        text += "\n- Item\n\n    Text %%list prose%%\n\n      %% list code %%\n"
        expected = text.replace(" %%prose%%", "").replace(" %%hidden%%", "").replace(" %%list prose%%", "")
        self.assertEqual(self.hidden(text), expected)
        self.assertEqual(self.shown(text).count("<!--"), 3)

    def test_a_percent_pair_with_no_mate_hides_the_rest_as_obsidian_does(self):
        # checked in Obsidian's reading view: the rest of the note is the comment, and a later `%%` closes an earlier one
        result = hide_comments("one\n%% oops\ntwo\nthree\n")
        self.assertEqual(result.text, "one\n")
        self.assertEqual((result.count, result.unclosed), (1, [2]))
        self.assertEqual(hide_comments("a %%b%% c %%d\n").text, "a  c")
        self.assertEqual(hide_comments("a %%b").text, "a")
        self.assertEqual(hide_comments("a %%b\nlast\n", show=True).text, "a <!-- b\nlast -->")
        closed = hide_comments("fd\n\n%%x\ny\n%%\nfdgf\n%% whatever\n\n#\n%%\nfd\n")
        self.assertEqual((closed.text, closed.unclosed), ("fd\n\nfdgf\nfd\n", []))

    def test_unclosed_keep_leaves_it_as_text_and_still_reports_the_line(self):
        result = hide_comments("one\n%% oops\ntwo\n", unclosed="keep")
        self.assertEqual(result.text, "one\n%% oops\ntwo\n")
        self.assertEqual((result.count, result.unclosed), (0, [2]))

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

    def test_another_word_is_a_pandoc_reader_and_the_flavour_stays_auto(self):
        for key in ("flavour", "flavor", "reader"):
            with self.subTest(key=key):
                path = self.note("vault", f"---\npdfmd-options:\n  {key}: gfm+smart\n---\n\nText\n")
                self.assertEqual(pdfmd.flavour_setting(path), ("obsidian", "gfm+smart"))
                self.assertEqual(pdfmd.resolve_from_format(path, None, [])[0], "gfm+smart+hard_line_breaks")      # a vault: Obsidian's newlines
        outside = self.note("plain", "---\npdfmd-options:\n  reader: markdown\n---\n\nText\n")
        self.assertEqual(pdfmd.flavour_setting(outside), ("pdfmd", "markdown"))
        self.assertEqual(pdfmd.resolve_from_format(outside, "commonmark", [])[0], "commonmark")      # --from still wins

    def test_the_presets_say_what_reader_they_read_with(self):
        for word, reader in (("pandoc", None), ("gfm", "gfm"), ("commonmark", "commonmark")):
            with self.subTest(word=word):
                path = self.note("plain", f"---\npdfmd-options:\n  flavour: {word.upper()}\n---\n\nText\n")
                self.assertEqual(pdfmd.flavour_of(path), word)
                self.assertEqual(pdfmd.resolve_from_format(path, None, [])[0], reader)
        path = self.note("plain", "Text\n")           # no front matter: pdfmd's own pick, gfm, with what the flavour adds
        self.assertEqual(pdfmd.resolve_from_format(path, None, [])[0], "gfm+smart+implicit_figures")
        path = self.note("plain", "---\ntitle: T\n---\n\nText\n")      # front matter: Pandoc's Markdown, with what the flavour adds
        self.assertEqual(pdfmd.resolve_from_format(path, None, [])[0], "markdown+autolink_bare_uris+emoji")
        path = self.note("plain", "---\ntitle: T\npdfmd-options:\n  flavour: pandoc\n---\n\nText\n")
        self.assertIsNone(pdfmd.resolve_from_format(path, None, [])[0])        # strict Pandoc adds nothing

    def test_an_unclosed_percent_pair_is_hidden_in_a_vault_and_kept_outside_it(self):
        self.assertEqual(pdfmd.unclosed_comment_mode(self.note("vault")), "hide")
        self.assertEqual(pdfmd.unclosed_comment_mode(self.note("plain")), "keep")
        pdfmd.UNCLOSED_CLI["mode"] = "hide"
        self.addCleanup(pdfmd.UNCLOSED_CLI.update, {"mode": None})
        self.assertEqual(pdfmd.unclosed_comment_mode(self.note("plain")), "hide")


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

    def run_pdfmd(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *arguments],
                              capture_output=True, text=True, encoding="utf-8",
                              cwd=self.directory / "vault", env=self.env)

    def write_note(self, name, text):
        path = self.directory / "vault" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_report_chapters_follow_the_comment_policy(self):
        first = "---\ntitle: First\nchapter: 1\n{}---\n\nVisible first.\n"
        self.write_note("second.md", "---\ntitle: Second\nchapter: 2\n---\n\n"
                        "%%\n\n# Private chapter heading\n\n%%\n\nVisible second.\n")
        for route in ("route", "patch"):
            self.write_note("first.md", first.format(f"pdfmd-options: {{report-build: {route}}}\n"))
            for flag in ((), ("--show-comments",), ("--flavour", "pandoc")):
                with self.subTest(route=route, flag=flag):
                    done = self.run_pdfmd("-r", "first.md", "second.md", "-o", "book.html", *flag)
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    html = (self.directory / "vault" / "book.html").read_text(encoding="utf-8")
                    self.assertIn("Visible second.", html)
                    self.assertEqual("Private chapter heading" in html, bool(flag))
                    self.assertEqual('id="private-chapter-heading"' in html, flag == ("--flavour", "pandoc"))

    def test_split_document_parts_follow_their_flavour(self):
        self.write_note("doc.md", "---\ntitle: Parts\npdfmd-options: {parts: auto}\n---\n")
        self.write_note("parts/10-first.md", "Start %%private text%% end.\n")
        self.write_note("parts/20-second.md", "---\npdfmd-options: {flavour: pandoc}\n---\n\n"
                        "Start %%literal text%% end.\n")
        done = self.run_pdfmd("doc.md", "-o", "doc.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        html = (self.directory / "vault" / "doc.html").read_text(encoding="utf-8")
        self.assertNotIn("private text", html)
        self.assertIn("%%literal text%%", html)

    def test_section_and_heading_scanners_skip_private_headings(self):
        body = "# Visible\n\nBefore.\n\n%%\n# Secret\n\n[hidden]{#private}\n%%\n\nAfter.\n\n# Last\n\nEnd.\n"
        for parts in (False, True):
            with self.subTest(parts=parts):
                options = "pdfmd-options: {parts: auto}\n" if parts else ""
                first = f"---\ntitle: Sections\n{options}---\n\n"
                self.write_note("doc.md", first if parts else first + body)
                if parts:
                    self.write_note("parts/10-first.md", body)
                listed = self.run_pdfmd("doc.md", "--list-parts")
                self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
                self.assertIn("# Visible", listed.stdout)
                self.assertNotIn("Secret", listed.stdout)
                self.assertNotIn("private", listed.stdout)
                for flag in ((), ("--show-comments",)):
                    done = self.run_pdfmd("doc#visible", "-o", "doc.html", *flag)
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    html = (self.directory / "vault" / "doc.html").read_text(encoding="utf-8")
                    self.assertIn("After.", html)
                    self.assertEqual("Secret" in html, bool(flag))
                    self.assertNotIn('id="secret"', html)

    def test_metadata_only_flavour_reaches_citation_detection(self):
        self.write_note("n.md", "Visible.\n\n%% [@missing]\n")
        self.write_note("meta.yaml", "pdfmd-options: {flavour: pandoc}\n")
        done = self.run_pdfmd("n.md", "--metadata-file", "meta.yaml", "-o", "n.html", "--verbose")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Citeproc: citation missing not found", done.stdout + done.stderr)
        self.write_note("meta.yaml", "pdfmd-options: {flavour: obsidian}\n")
        hidden = self.run_pdfmd("n.md", "--metadata-file", "meta.yaml", "-o", "n.html")
        self.assertEqual(hidden.returncode, 0, hidden.stdout + hidden.stderr)
        self.assertNotIn("Citeproc: citation missing not found", hidden.stdout + hidden.stderr)

    def test_split_does_not_create_a_part_from_a_commented_out_heading(self):
        self.write_note("doc.md", "---\ntitle: Sections\n---\n\n# One\n\n"
                        "%%\n\n# Private\n\n%%\n\n# Two\n\nEnd.\n")
        done = self.run_pdfmd("doc.md", "--split", "split")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        parts = self.directory / "vault" / "split" / "parts"
        self.assertEqual(sorted(item.name for item in parts.iterdir()), ["10-one.md", "20-two.md"])
        self.assertIn("# Private", (parts / "10-one.md").read_text(encoding="utf-8"))

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

    def test_outside_a_vault_the_pdfmd_flavour_hides_them_too(self):
        html, _ = self.build("plain", "# N\n\nA %%gone%% B\n")
        self.assertNotIn("gone", html)

    def test_an_unclosed_percent_pair_outside_a_vault_stays_text_and_says_so(self):
        html, said = self.build("plain", "# N\n\nA %% b\n\nThe end.\n")
        self.assertIn("The end.", html)
        self.assertIn("with no closing", said)

    def test_the_flavour_turns_it_on_outside_a_vault_and_off_inside_one(self):
        html, _ = self.build("plain", "# N\n\nA %%gone%% B\n", "--flavour", "obsidian")
        self.assertNotIn("gone", html)
        html, _ = self.build("plain", "---\npdfmd-options:\n  flavor: obsidian\n---\n\nA %%gone%% B\n")
        self.assertNotIn("gone", html)
        for word in ("pandoc", "gfm", "commonmark"):
            with self.subTest(word=word):
                html, _ = self.build("vault", "# N\n\nA %%kept%% B\n", "--flavor", word)
                self.assertIn("%%kept%%", html)
                html, _ = self.build("plain", f"---\npdfmd-options:\n  flavour: {word}\n---\n\nA %%kept%% B\n")
                self.assertIn("%%kept%%", html)
        html, _ = self.build("plain", "# N\n\nA %%gone%% B\n", "--flavour", "Obsidian")      # the word's case does not matter
        self.assertNotIn("gone", html)

    def test_the_pdfmd_flavour_reads_typography_figures_bare_links_and_emoji_on_both_readers(self):
        body = '"Quoted" -- and ---\n\n![The caption](pic.png)\n\nSee https://example.org/a now :smile:\n'
        for front, label in (("", "gfm"), ("---\ntitle: T\n---\n\n", "markdown")):
            with self.subTest(reader=label):
                html, _ = self.build("plain", front + body)
                self.assertIn("\u201cQuoted\u201d \u2013 and \u2014", html)
                self.assertIn("<figcaption", html)
                self.assertIn('<a href="https://example.org/a"', html)
                self.assertIn("\U0001f604", html)
        html, _ = self.build("plain", body, "--flavour", "gfm")
        self.assertIn("-- and ---", html)               # strict gfm: no smart typography, no figures
        self.assertNotIn("<figcaption", html)

    def test_a_figure_is_made_where_the_gfm_reader_does_not_make_it(self):
        """Pandoc 3.1.3's gfm reader takes `+implicit_figures` and makes no figure: lib/pdfmd_lua/figures.lua makes it, in the shape a
        newer reader gives (where the reader made it, the filter finds nothing to do), and only when the reader was asked for figures."""
        source = self.directory / "plain" / "f.md"
        source.write_text("![The *cap*](pic.png)\n\nBeside ![inline](pic.png) text.\n\n![](pic.png)\n", encoding="utf-8")
        import pdfmd_lua

        def run(reader):
            done = subprocess.run(["pandoc", "-f", reader, "-t", "html", "--lua-filter", str(pdfmd_lua.path("figures")), str(source)],
                                  capture_output=True, text=True, encoding="utf-8", env=self.env)
            self.assertEqual(done.returncode, 0, done.stderr)
            return done.stdout
        asked = run("gfm+implicit_figures")
        self.assertEqual(asked.count("<figure"), 1, asked)
        self.assertIn("<figcaption", asked)
        self.assertIn("The <em>cap</em></figcaption>", asked)
        self.assertIn('<p>Beside <img src="pic.png" alt="inline" /> text.</p>', asked)
        self.assertIn('<p><img src="pic.png" /></p>', asked)                     # no caption: no figure
        self.assertNotIn("<figure", run("gfm"))                                  # figures not asked for: none made

    def test_a_note_with_properties_is_cleaned_too(self):
        source = ("---\ntitle: Sample note\ntags: [one, two]\naliases: [Other name]\n"
                  "cssclasses: [sample]\npdfmd-options: {single-newline: soft}\n---\n\n"
                  "One %%hidden%% two\nthree\n")
        html, _ = self.build("vault", source, "--standalone")
        self.assertNotIn("hidden", html)
        self.assertIn("<title>Sample note</title>", html)
        self.assertIn("One", html)
        self.assertNotIn("<br />", html)
        result = self.run_pdfmd("n.md", "-t", "markdown", "--standalone", "-o", "properties.markdown")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        markdown = (self.directory / "vault" / "properties.markdown").read_text(encoding="utf-8")
        for key in ("tags:", "aliases:", "cssclasses:"):
            self.assertIn(key, markdown)

    def test_block_ids_and_tags_in_the_writers(self):
        self.write_note("other.md", "Target text. ^external\n")
        self.write_note("n.md", "Start #Alpha/one and #café. ^sample\n\n"
                        "[[#^sample|Local]] and [[other#^external|Remote]].\n\n"
                        "## Heading #unchanged\n\n"
                        "`#code ^code` and [link](https://example.org/#fragment).\n\n"
                        "    #indented ^indented\n\n"
                        "- Nested #tag ^nested\n\n[[#^nested|Nested link]].\n")
        for target, suffix, expected in (
            ("html", "html", ('id="sample"', 'href="#sample"', 'class="tag">#Alpha/one',
                              'class="tag">#café', 'href="other.html#external"', 'href="#nested"')),
            ("latex", "tex", (r"\label{sample}", r"\hyperref[sample]", r"\#Alpha/one")),
            ("typst", "typ", ("<sample>", "#link(<sample>)", "Alpha/one")),
            ("markdown", "markdown", ("{#sample}", "](#sample)", "{.tag}")),
            ("docx", "docx", ("sample", "Alpha/one")),
            ("odt", "odt", ('xlink:href="#sample"', "Alpha/one")),
            ("plain", "txt", ("#Alpha/one", "#café", "Nested link")),
        ):
            with self.subTest(target=target):
                name = f"out.{suffix}"
                done = self.run_pdfmd("n.md", "-t", target, "-o", name)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                path = self.directory / "vault" / name
                if target in ("docx", "odt"):
                    with zipfile.ZipFile(path) as archive:
                        output = archive.read("word/document.xml" if target == "docx" else "content.xml").decode("utf-8")
                else:
                    output = path.read_text(encoding="utf-8")
                for token in expected:
                    self.assertIn(token, output)
                self.assertNotIn("^sample", output)
                self.assertNotIn("^nested", output)
                if target == "html":
                    self.assertIn("Heading #unchanged", output)
                    self.assertIn("#code ^code", output)
                    self.assertIn("#indented ^indented", output)
                    self.assertIn('https://example.org/#fragment', output)
                    self.assertNotIn('class="tag">#fragment', output)

    def test_duplicate_block_ids_in_parts_resolve_in_their_own_notes(self):
        self.write_note("doc.md", "---\ntitle: Parts\npdfmd-options: {parts: auto}\n---\n\n"
                        "[[second#^point|From scaffold]].\n")
        self.write_note("parts/first.md", "First. ^point\n\n[[#^point|First link]].\n")
        self.write_note("parts/second.md", "Second. ^point\n\n[[#^point|Second link]].\n")
        done = self.run_pdfmd("doc.md", "-o", "doc.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        html = (self.directory / "vault" / "doc.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'First\.\s*<span id="point"')
        self.assertRegex(html, r'Second\.\s*<span id="point-1"')
        self.assertIn('href="#point">First link', html)
        self.assertIn('href="#point-1">Second link', html)
        self.assertIn('href="#point-1">From scaffold', html)

    def test_block_ids_and_tags_stay_literal_with_the_flavour_off(self):
        html, _ = self.build("vault", "Start #tag. ^sample\n\n[[#^sample|Local]].\n", "--flavour", "pandoc")
        self.assertIn("Start #tag. ^sample", html)
        self.assertNotIn('id="sample"', html)
        self.assertNotIn('class="tag"', html)

    def test_a_percent_pair_with_no_mate_hides_the_rest_and_says_so_unless_told_to_keep_it(self):
        note = "# N\n\nOne\n\n%% oops\nrest\n"
        html, said = self.build("vault", note)
        self.assertIn("a `%%` with no closing `%%`: the rest of the note (2 lines) is hidden", said)
        self.assertIn("One", html)
        self.assertNotIn("rest", html)
        html, said = self.build("vault", note, "--unclosed-comment", "keep")
        self.assertIn("it is kept as text", said)
        self.assertIn("%% oops", html)
        html, _ = self.build("vault", "---\npdfmd-options:\n  unclosed-comment: keep\n---\n\nOne\n\n%% oops\nrest\n")
        self.assertIn("rest", html)

    def test_other_writers_agree(self):
        (self.directory / "vault" / "n.md").write_text("# N\n\nA %%gone%% B\n", encoding="utf-8")
        for target, suffix in (("latex", "tex"), ("typst", "typ")):
            with self.subTest(target=target):
                subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "n.md", "-t", target, "-o", f"n.{suffix}"],
                               capture_output=True, text=True, cwd=self.directory / "vault", env=self.env, check=True)
                self.assertNotIn("gone", (self.directory / "vault" / f"n.{suffix}").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
