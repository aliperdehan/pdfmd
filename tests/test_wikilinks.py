"""`[[Note|alias]]` written as the text Obsidian shows (entry 3ee, v3.32.26), and `<u>` underlined in every writer."""

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
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from pandoc_support import needs_pandoc  # noqa: E402
from pdfmd_obsidian import wikilinks_as_text  # noqa: E402


class Transform(unittest.TestCase):
    def text(self, source):
        return wikilinks_as_text(source).text

    def test_the_name_the_alias_and_the_heading_as_obsidian_shows_them(self):
        self.assertEqual(self.text("a [[Some note]] b"), "a Some note b")
        self.assertEqual(self.text("a [[Some note|an alias]] b"), "a an alias b")
        self.assertEqual(self.text("a [[Some note#Heading]] b"), "a Some note > Heading b")
        self.assertEqual(self.text("a [[#Heading]] b"), "a Heading b")
        self.assertEqual(self.text("a [[folder/Note#H|shown]] b"), "a shown b")
        self.assertEqual(wikilinks_as_text("[[a]] [[b]]").count, 2)

    def test_a_pipe_escaped_for_a_table_is_still_the_bar(self):
        self.assertEqual(self.text("| [[Note\\|alias]] |"), "| alias |")

    def test_a_colon_in_the_target_keeps_the_marker_but_aliases_and_anchors_allow_it(self):
        for marker in ("[[fullcite:key]]", "[[fullcite:key|shown]]", "[[name:key#Heading]]", "[[name:key^block]]"):
            with self.subTest(marker=marker):
                self.assertEqual(self.text(marker), marker)
        self.assertEqual(self.text("[[Note|Time: 10]]"), "Time: 10")
        self.assertEqual(self.text("[[Note#Time: 10]]"), "Note > Time: 10")
        self.assertEqual(self.text("[[Note^block:one|shown]]"), "shown")

    def test_markdown_in_a_name_is_kept_as_text(self):
        self.assertEqual(self.text("[[a_b*c]]"), "a\\_b\\*c")

    def test_what_is_not_a_wikilink_is_left_alone(self):
        for kept in ("[[_TOC_]]", "[[1]](http://example.org)", "![[picture.png]]", "![[note]]", "[[ ]]", "[[a]][b]",
                     "`[[code]]`", "$[[x]]$", "<!-- [[c]] -->", "```\n[[fenced]]\n```", "---\nt: '[[front]]'\n---\n"):
            with self.subTest(kept=kept):
                self.assertEqual(self.text(kept), kept)


@needs_pandoc(3, 1, 3)
class Build(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-wikilinks-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.directory / "config"),
                    "APPDATA": str(self.directory / "config")}

    def build(self, text, target, *arguments):
        (self.directory / "n.md").write_text(text, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "n.md", "-t", target, "--no-stamp", *arguments],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.directory, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        suffix = {"latex": "tex", "typst": "typ", "markdown": "markdown"}.get(target, target)
        if "-o" in arguments:
            return " ".join((self.directory / arguments[arguments.index("-o") + 1]).read_text(encoding="utf-8").split())
        return " ".join((self.directory / f"n.{suffix}").read_text(encoding="utf-8").split())

    def test_wikilinks_are_text_in_the_pdfmd_flavour_and_literal_in_pandoc(self):
        html = self.build("A [[Note|alias]] and [[Other#Part]].\n", "html")
        self.assertIn("A alias and Other &gt; Part.", html)
        html = self.build("---\npdfmd-options:\n  flavour: pandoc\n---\n\nA [[Note|alias]].\n", "html")
        self.assertIn("[[Note|alias]]", html)

    def test_colon_markers_reach_pandoc_and_user_filters_in_every_flavour(self):
        source = "before\n\n[[marker:key]]\n\n[[Note|Time: 10]]\n\n[[Note]]\n\nafter\n"
        note = self.directory / "n.md"
        note.write_text(source, encoding="utf-8")
        probe = self.directory / "probe.lua"
        probe.write_text('function Pandoc(doc)\n'
                         '  assert(pandoc.utils.stringify(doc):find("[[marker:key]]", 1, true))\n'
                         'end\n', encoding="utf-8")
        for flavour in ("pdfmd", "obsidian", "pandoc", "gfm", "commonmark"):
            with self.subTest(flavour=flavour):
                output = self.directory / "out.md"
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(note), "--to", "md",
                                       "--flavour", flavour, "--lua-filter", str(probe), "-o", str(output)],
                                      cwd=self.directory, env={**self.env, "PDFMD_NO_PROMPT": "1"},
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                text = output.read_text(encoding="utf-8").replace("\\[", "[").replace("\\]", "]")
                self.assertIn("[[marker:key]]", text)
                if flavour in ("pdfmd", "obsidian"):
                    self.assertIn("Time: 10", text)
                    self.assertNotIn("[[Note", text)

    def test_obsidian_resolves_local_and_built_note_links(self):
        (self.directory / "Other Note.md").write_text("## Related {#custom}\n\nText.\n", encoding="utf-8")
        source = ("---\ntitle: Index\n---\n\n"
                  "[[#Local heading]] and [[Other Note#Related|read more]] and [[Other Note]].\n\n"
                  "## Local heading {#local}\n\nHere.\n")
        html = self.build(source, "html", "--flavour", "obsidian")
        self.assertIn('<a href="#local">Local heading</a>', html)
        self.assertIn('<a href="Other%20Note.html#custom">read more</a>', html)
        self.assertIn('<a href="Other%20Note.html">Other Note</a>', html)
        for target, expected in (("latex", r"(?:\\hyperref\[local\]|\\hyperlink\{local\})\{Local heading\}"),
                                 ("typst", r"#link\(<local>\)\[Local heading\]"),
                                 ("markdown", r"\[Local heading\]\(#local\)")):
            with self.subTest(target=target):
                self.assertRegex(self.build(source, target, "--flavour", "obsidian", "-o", f"n.{target}"), expected)

    def test_obsidian_reports_one_missing_note_warning_and_strict_fails(self):
        (self.directory / "n.md").write_text("[[Missing|first]] and [[Missing|second]].\n", encoding="utf-8")
        args = [sys.executable, str(ROOT / "scripts" / "pdfmd"), "n.md", "-t", "html", "--flavour", "obsidian"]
        done = subprocess.run(args, cwd=self.directory, env=self.env, capture_output=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr.count("wikilink note not found"), 1, done.stderr)
        self.assertIn("<p>first and second.</p>", (self.directory / "n.html").read_text(encoding="utf-8"))
        strict = subprocess.run([*args, "--strict"], cwd=self.directory, env=self.env, capture_output=True, encoding="utf-8")
        self.assertNotEqual(strict.returncode, 0)
        self.assertIn("wikilink note not found", strict.stderr)

    def test_notes_that_are_parts_become_internal_links(self):
        (self.directory / "Later.md").write_text(
            "---\nchapter: 2\n---\n\n## Repeated\n\n[[#Repeated|self]].\n", encoding="utf-8")
        (self.directory / "n.md").write_text(
            "---\nchapter: 1\n---\n\n[[Later|part]] or [[Later#Repeated|section]].\n\n## Repeated\n",
            encoding="utf-8")
        for route in ("route", "patch"):
            with self.subTest(route=route):
                (self.directory / "metadata.yaml").write_text(
                    f"pdfmd-options: {{report-build: {route}}}\n", encoding="utf-8")
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--report", "--flavour",
                                       "obsidian", "-t", "html", "-o", "book.html"],
                                      cwd=self.directory, env=self.env, capture_output=True, encoding="utf-8")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                html = " ".join((self.directory / "book.html").read_text(encoding="utf-8").split())
                self.assertRegex(html, r'<a href="#pdfmd-wikilink-[^"]+">part</a>')
                self.assertIn('<a href="#repeated-1">section</a>', html)
                self.assertIn('<a href="#repeated-1">self</a>', html)

    def test_scaffold_links_and_office_bookmarks(self):
        parts = self.directory / "parts"
        parts.mkdir()
        (parts / "other.md").write_text("## Café\n\nPart body.\n", encoding="utf-8")
        source = "---\ntitle: Index\npdfmd-options: {parts: auto, flavour: obsidian}\n---\n\n[[other#Café|Read it]].\n"
        (self.directory / "n.md").write_text(source, encoding="utf-8")
        for target, xml, anchor in (("docx", "word/document.xml", 'w:anchor="_?café"'),
                                     ("odt", "content.xml", 'xlink:href="#caf')):
            with self.subTest(target=target):
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "n.md", "-t", target],
                                      cwd=self.directory, env=self.env, capture_output=True, encoding="utf-8")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                with zipfile.ZipFile(self.directory / f"n.{target}") as archive:
                    self.assertRegex(archive.read(xml).decode("utf-8"), anchor)

    def test_underline_is_the_writers_own(self):
        source = "x <u>under</u> and <ins>ins</ins> y\n"
        self.assertIn("<u>under</u>", self.build(source, "html"))
        self.assertIn("\\ul{under}", self.build(source, "latex"))
        self.assertIn("#underline[under]", self.build(source, "typst"))
        html = self.build(source, "html", "--no-markup")
        self.assertIn("<u>under</u>", html)                 # raw HTML is what an HTML build keeps either way
        self.assertIn("under", self.build(source, "latex", "--no-markup"))
        self.assertNotIn("\\ul{", self.build(source, "latex", "--no-markup"))


if __name__ == "__main__":
    unittest.main()
