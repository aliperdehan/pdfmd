"""The full reference in place: `[@key]{.fullcite}`, `[[fullcite:key]]` and `::: fullcite` print the formatted reference of a
source where they stand (pdfmd_lua/fullcite_mark.lua before citeproc, pdfmd_lua/fullcite.lua after it; the package
pdfmd_fullcite decides when they go in). The filters through Pandoc itself, then real builds through pdfmd."""

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

import pdfmd  # noqa: E402

LUA = ROOT / "lib" / "pdfmd_lua"
PANDOC = shutil.which("pandoc")

BIB = """@book{alpha, author={Alpha, Ann}, title={First Book}, year={1984}, publisher={Press}}
@article{beta, author={Beta, Bob}, title={Second Paper}, year={1990}, journal={J. Things}, volume={3}, pages={1--9}}
@book{gamma, author={Gamma, Gus}, title={Third Book}, year={2001}, publisher={Press}}
"""
BODY = """# Intro

Text with [@gamma] cited, and one in a sentence: see [@beta]{.fullcite} done.

# Annotated

[@alpha]{.fullcite}

Note on alpha.

[[fullcite:beta]]

# References

::: {#refs}
:::
"""


class Syntax(unittest.TestCase):
    def test_what_uses_fullcite(self):
        package = pdfmd.load_package("pdfmd_fullcite")
        for text in ("[@a]{.fullcite}", "x [@a; @b]{.fullcite list=keep} y", "::: fullcite\n@a\n:::", ":::: {.fullcite}\n@a\n::::",
                     "[[fullcite:a]]"):
            self.assertTrue(package.SYNTAX_RE.search(text), text)
        for text in ("[@a]", "[x]{.other}", "fullcite", "a ::: fullcitex", "[[Note]]"):
            self.assertFalse(package.SYNTAX_RE.search(text), text)

    def test_the_old_spelling_is_a_citation_to_be(self):
        package = pdfmd.load_package("pdfmd_fullcite")
        self.assertTrue(package.old_spelling_in("a\n\n[[fullcite:key-1]]\n"))
        self.assertFalse(package.old_spelling_in("[[fullcite:]] and [[Note]]"))

    def test_the_command_line_word_is_checked(self):
        package = pdfmd.load_package("pdfmd_fullcite")
        self.assertEqual(package.command_line_value(" ALL "), "all")
        with self.assertRaises(SystemExit):
            package.command_line_value("keep")

    def test_the_markup_kind_is_on_in_the_pdfmd_flavour_and_off_in_a_pandoc_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for flavour, wanted in (("pdfmd", True), ("obsidian", True), ("pandoc", False), ("gfm", False)):
                document = root / f"{flavour}.md"
                document.write_text(f"---\npdfmd-options:\n  flavour: {flavour}\n---\n\n[@a]{{.fullcite}}\n", encoding="utf-8")
                self.assertEqual("fullcite" in pdfmd.markup_kinds(document, []), wanted, flavour)
            document = root / "listed.md"
            document.write_text("---\npdfmd-options:\n  markup: [callouts]\n---\n\n[@a]{.fullcite}\n", encoding="utf-8")
            self.assertEqual(pdfmd.fullcite_pre_args(document, [], []), [])             # a markup list without the word: off

    def test_nothing_is_added_to_a_document_that_does_not_use_it(self):
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "plain.md"
            document.write_text("---\ntitle: T\n---\n\nSee [@a]. Not [x]{.other}.\n", encoding="utf-8")
            self.assertEqual(pdfmd.fullcite_pre_args(document, [], []), [])
            self.assertEqual(pdfmd.fullcite_post_args(document, [], ["--citeproc"], []), [])

    def test_the_filters_go_in_for_a_document_that_uses_it(self):
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "ab.md"
            document.write_text("---\ntitle: T\n---\n\n[@a]{.fullcite}\n", encoding="utf-8")
            pre = pdfmd.fullcite_pre_args(document, [], [])
            self.assertEqual(pre, ["--lua-filter", str(LUA / "fullcite_mark.lua")])
            self.assertEqual(pdfmd.fullcite_pre_args(document, [], ["--biblatex"])[:2], ["-M", "pdfmd-fullcite-engine=biblatex"])
            natbib = pdfmd.fullcite_pre_args(document, [], ["--natbib"])
            self.assertIn("--include-in-header", natbib)                        # \bibentry needs the bibentry package
            self.assertIn("\\usepackage{bibentry}", Path(natbib[natbib.index("--include-in-header") + 1]).read_text(encoding="utf-8"))
            self.assertEqual(pdfmd.fullcite_post_args(document, [], [], []), [])         # no citeproc: nothing to read
            post = pdfmd.fullcite_post_args(document, [], ["--citeproc"], [])
            self.assertIn("pdfmd-fullcite-list=rest", post)
            self.assertEqual(post[-2:], ["--lua-filter", str(LUA / "fullcite.lua")])

    def test_the_list_setting_comes_from_every_layer_and_the_command_line_wins(self):
        package = pdfmd.load_package("pdfmd_fullcite")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            document = root / "d.md"
            document.write_text("---\ntitle: T\n---\n\nx\n", encoding="utf-8")
            metadata = root / "meta.yaml"
            metadata.write_text("pdfmd-options:\n  fullcite-list: none\n", encoding="utf-8")
            old = os.environ.pop(package.ENV, None)
            try:
                self.assertEqual(package.list_mode(document, []), "rest")
                self.assertEqual(package.list_mode(document, [metadata]), "none")
                document.write_text("---\npdfmd-options:\n  fullcite-list: all\n---\n\nx\n", encoding="utf-8")
                self.assertEqual(package.list_mode(document, [metadata]), "all")
                document.write_text("---\npdfmd-options:\n  fullcite-list: some\n---\n\nx\n", encoding="utf-8")
                with self.assertRaises(SystemExit) as caught:
                    package.list_mode(document, [])
                self.assertIn("fullcite-list must be one of rest, all, none", str(caught.exception))
                os.environ[package.ENV] = "rest"
                self.assertEqual(package.list_mode(document, [metadata]), "rest")
            finally:
                os.environ.pop(package.ENV, None)
                if old is not None:
                    os.environ[package.ENV] = old


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filters(unittest.TestCase):
    """The two filters, run by Pandoc on its own (the order of a pdfmd build: mark, citeproc, place)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "refs.bib").write_text(BIB, encoding="utf-8")

    def run_pandoc(self, body: str, to: str = "plain", *meta: str, engine: str = "") -> subprocess.CompletedProcess:
        (self.root / "t.md").write_text("---\nbibliography: refs.bib\n---\n\n" + body, encoding="utf-8")
        command = [PANDOC, "t.md", "-f", "markdown", "-t", to, "--lua-filter", str(LUA / "fullcite_mark.lua")]
        if engine:
            command += ["-M", f"pdfmd-fullcite-engine={engine}", f"--{engine}"]
        else:
            command += ["--citeproc", "-M", "pdfmd-fullcite-doc=t.md", "--lua-filter", str(LUA / "fullcite.lua")]
        for item in meta:
            command += ["-M", item]
        return subprocess.run(command, cwd=self.root, capture_output=True, text=True, encoding="utf-8")

    def out(self, body: str, to: str = "plain", *meta: str) -> str:
        done = self.run_pandoc(body, to, *meta)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_a_span_alone_becomes_the_entry_and_the_list_loses_it(self):
        text = self.out(BODY)
        self.assertIn("Alpha, Ann. 1984. First Book. Press.", text)
        self.assertNotIn("[@alpha]", text)
        self.assertEqual(text.count("First Book"), 1)               # placed once, and gone from the list
        self.assertEqual(text.count("Second Paper"), 2)              # in the sentence, and as the old spelling's entry
        self.assertTrue(text.rstrip().endswith("Third Book. Press."))   # gamma is only cited: the list keeps it
        self.assertIn("References", text)

    def test_a_span_in_a_sentence_becomes_the_text_of_the_entry(self):
        text = " ".join(self.out(BODY).split())
        self.assertIn("see Beta, Bob. 1990. “Second Paper.” J. Things 3: 1–9. done.", text)

    def test_the_old_spelling_and_the_block_form_give_the_same(self):
        text = self.out("::: fullcite\n@alpha\n@gamma\n:::\n\n[[fullcite:beta]]\n")
        for title in ("First Book", "Third Book", "Second Paper"):
            self.assertEqual(text.count(title), 1, title)
        self.assertLess(text.index("First Book"), text.index("Third Book"))
        self.assertLess(text.index("Third Book"), text.index("Second Paper"))

    def test_list_all_keeps_the_whole_list_and_none_removes_it(self):
        body = "Cited [@beta].\n\n[@alpha]{.fullcite}\n\n# References\n\n::: {#refs}\n:::\n"
        everything = self.out(body, "plain", "pdfmd-fullcite-list=all")
        self.assertEqual(everything.count("First Book"), 2)
        self.assertEqual(everything.count("Second Paper"), 1)
        rest = self.out(body, "plain", "pdfmd-fullcite-list=rest")
        self.assertEqual(rest.count("First Book"), 1)
        self.assertIn("References", rest)                          # beta is still there
        self.assertEqual(rest.count("Second Paper"), 1)
        none = self.out(body, "plain", "pdfmd-fullcite-list=none")
        self.assertNotIn("References", none)                       # the list and the heading before it go
        self.assertEqual(none.count("Second Paper"), 0)
        self.assertEqual(none.count("First Book"), 1)

    def test_an_empty_list_takes_the_heading_before_it(self):
        text = self.out("# Entries\n\n[@alpha]{.fullcite}\n\n# References\n\n::: {#refs}\n:::\n")
        self.assertIn("Entries", text)
        self.assertNotIn("References", text)

    def test_one_entry_and_one_block_beat_the_setting(self):
        keep = self.out("[@alpha]{.fullcite list=keep}\n\n# References\n\n::: {#refs}\n:::\n")
        self.assertEqual(keep.count("First Book"), 2)
        block = self.out("::: {.fullcite list=keep}\n@alpha\n:::\n\n# References\n\n::: {#refs}\n:::\n")
        self.assertEqual(block.count("First Book"), 2)
        drop = self.out("Cited [@alpha]{.fullcite list=drop}.\n\n# References\n\n::: {#refs}\n:::\n", "plain", "pdfmd-fullcite-list=all")
        self.assertEqual(drop.count("First Book"), 1)

    def test_an_unknown_key_is_warned_and_the_citation_stays(self):
        done = self.run_pandoc("[@nokey]{.fullcite}\n\n[@alpha]{.fullcite}\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("WARN  t.md: fullcite: no reference for 'nokey'", done.stderr)
        self.assertIn("(nokey?)", done.stdout)
        self.assertIn("First Book", done.stdout)

    def test_each_writer_indents_the_entry_its_own_way(self):
        indent = "pdfmd-fullcite-indent=1.5em"
        body = "[@alpha]{.fullcite}\n"
        self.assertIn("\\hangindent=1.5em\\hangafter=1", self.out(body, "latex", indent))
        self.assertIn("#par(hanging-indent: 1.5em)[", self.out(body, "typst", indent))
        html = self.out(body, "html", indent)
        self.assertIn('style="margin-left: 1.5em; text-indent: -1.5em;"', html)
        self.assertIn('class="csl-entry"', html)
        for writer, marker in (("latex", "\\hangindent"), ("typst", "hanging-indent"), ("html", "text-indent")):
            self.assertNotIn(marker, self.out(body, writer, "pdfmd-fullcite-indent=0"), writer)
            self.assertNotIn(marker, self.out(body, writer), writer)

    def test_biblatex_and_natbib_write_the_citation_package_commands(self):
        text = self.run_pandoc("[@alpha]{.fullcite}\n\n[[fullcite:beta]]\n\n::: fullcite\n@gamma\n:::\n", "latex", engine="biblatex").stdout
        for key in ("alpha", "beta", "gamma"):
            self.assertIn(f"\\fullcite{{{key}}}", text)
        self.run_pandoc("x [@alpha]{.fullcite}\n", "latex", engine="natbib")                # writes t.md for the standalone run
        text = subprocess.run([PANDOC, "t.md", "-f", "markdown", "-t", "latex", "-s", "--natbib", "-M", "pdfmd-fullcite-engine=natbib",
                               "--lua-filter", str(LUA / "fullcite_mark.lua")], cwd=self.root, capture_output=True, text=True,
                              encoding="utf-8").stdout
        self.assertIn("\\bibentry{alpha}", text)
        self.assertIn("\\nobibliography{refs}", text)             # its package comes from pdfmd's own header file


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Builds(unittest.TestCase):
    """Real builds through pdfmd: the filters are in the command, in the right order, and `--strict` counts the warning."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "refs.bib").write_text(BIB, encoding="utf-8")

    def build(self, body: str, to: str = "html", options: str = "", extra: tuple[str, ...] = ()) -> tuple[subprocess.CompletedProcess, Path]:
        front = f"pdfmd-options: {{{options}}}\n" if options else ""
        (self.root / "d.md").write_text(f"---\ntitle: T\nbibliography: refs.bib\n{front}---\n\n{body}", encoding="utf-8")
        out = self.root / f"out.{to}"
        out.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *extra, "--to", to, "-o", out.name, "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "PDFMD_NO_PROMPT": "1",
                                   "XDG_CACHE_HOME": str(self.root / "cache")}, stdin=subprocess.DEVNULL)
        return done, out

    def text(self, body: str, to: str = "html", options: str = "", extra: tuple[str, ...] = ()) -> str:
        done, out = self.build(body, to, options, extra)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return out.read_text(encoding="utf-8")

    def test_html_and_the_filter_order(self):
        (self.root / "d.md").write_text("---\ntitle: T\nbibliography: refs.bib\n---\n\n[@alpha]{.fullcite}\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "html", "-o", "o.html", "--verbose", "--no-stamp",
                               "--no-backup"], cwd=self.root, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              env={**os.environ, "PDFMD_CONFIG": "", "XDG_CACHE_HOME": str(self.root / "cache"), "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        command = next(line for line in (done.stdout + done.stderr).splitlines() if "fullcite_mark.lua" in line)
        self.assertLess(command.index("fullcite_mark.lua"), command.index("--citeproc"))
        self.assertLess(command.index("--citeproc"), command.index("/fullcite.lua"))
        self.assertIn("First Book", (self.root / "o.html").read_text(encoding="utf-8"))

    def test_html_typst_and_tex_builds(self):
        html = self.text(BODY)
        self.assertIn("Alpha, Ann. 1984.", html)
        self.assertIn("text-indent: -1.5em", html)
        self.assertNotIn("fullcite", html.replace("fullcite-", ""))      # no marker left behind
        typst = self.text(BODY, "typ")
        self.assertIn("#par(hanging-indent: 1.5em)[", typst)
        tex = self.text(BODY, "tex")
        self.assertIn("\\hangindent=1.5em\\hangafter=1", tex)

    def test_the_list_setting_and_the_flag(self):
        body = "[@alpha]{.fullcite}\n\n# References\n\n::: {#refs}\n:::\n"
        self.assertEqual(self.text(body).count("First Book"), 1)
        self.assertEqual(self.text(body, options="fullcite-list: all").count("First Book"), 2)
        self.assertEqual(self.text(body, extra=("--fullcite-list", "all")).count("First Book"), 2)
        self.assertEqual(self.text(body, options="fullcite-list: all", extra=("--fullcite-list", "rest")).count("First Book"), 1)

    def test_strict_counts_the_unknown_key(self):
        done, _ = self.build("[@nokey]{.fullcite}\n", extra=("--strict",))
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("fullcite: no reference for 'nokey'", done.stdout + done.stderr)
        self.assertIn("d.md", [line for line in (done.stdout + done.stderr).splitlines() if "fullcite:" in line][0])

    def test_a_pandoc_flavour_leaves_the_syntax_alone(self):
        text = self.text("[@alpha]{.fullcite}\n\n# References\n\n::: {#refs}\n:::\n", options="flavour: pandoc")
        self.assertEqual(text.count("First Book"), 1)             # the list only: nothing was placed
        self.assertIn('class="fullcite"', text)

    def test_the_old_spelling_alone_needs_no_other_citation(self):
        text = self.text("[[fullcite:alpha]]\n")
        self.assertIn("Alpha, Ann. 1984.", text)

    def test_a_document_without_the_syntax_is_built_as_before(self):
        text = self.text("Cited [@alpha].\n\n# References\n\n::: {#refs}\n:::\n")
        self.assertEqual(text.count("First Book"), 1)
        self.assertNotIn("text-indent", text)


if __name__ == "__main__":
    unittest.main()
