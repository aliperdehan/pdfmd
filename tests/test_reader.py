"""The reader pdfmd picks for a Markdown file: the `reader:` option and the notice when gfm would print Pandoc syntax (v3.26.13)."""

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


class ReaderNeeds(unittest.TestCase):
    """What a file with no front matter uses that gfm does not read (v3.32.5): an extension gfm takes, or Pandoc's own reader."""

    def needs(self, text):
        return dict(pdfmd.reader_needs(text))

    def test_what_gfm_takes_as_an_extension(self):
        found = self.needs("# T\n\nH~2~O, x^2^.\n\n## S {#sec}\n\nTerm\n: definition\n\n::: note\nText\n:::\n")
        self.assertEqual(found, {"subscripts (H~2~O)": "subscript", "superscripts (x^2^)": "superscript",
                                 "{#id .class} attributes": "attributes+bracketed_spans", "fenced divs (:::)": "fenced_divs",
                                 "definition lists": "definition_lists"})

    def test_what_only_pandocs_own_reader_reads(self):
        for text, name in (("A note^[inline].\n", "inline footnotes (^[...])"),
                           ("\\begin{equation} a \\end{equation}\n", "raw LaTeX (\\begin{...}, \\newcommand{...}, \\ce{...})"),
                           ("Text \\textbf{bold} and \\ref{x}\n", "raw LaTeX (\\begin{...}, \\newcommand{...}, \\ce{...})"),
                           ("+---+---+\n| a | b |\n+===+===+\n", "grid tables"),
                           ("  A    B\n ---- ----\n  1    2\n", "simple tables"),
                           ("(@) First\n(@) Second\n", "example lists ((@))")):
            with self.subTest(text=text):
                self.assertIsNone(self.needs(text).get(name, "missing"), text)

    def test_code_math_and_comments_are_not_syntax_the_document_uses(self):
        text = ("# T\n\n~~struck~~ and `H~2~O` and `\\begin{a}` and a | table |\n\n```\nx^2^ \\begin{a} ^[n]\n```\n\n"
                "Math $\\frac{a}{b}$ and $$\\ce{H2O}$$ and a price of $5 or $10.\n\n<!-- \\newcommand{x}{y} H~2~O -->\n")
        self.assertEqual(pdfmd.reader_needs(text), [])

    def test_a_fence_that_opens_with_attributes_is_looked_at(self):
        self.assertEqual(self.needs("```{.smiles caption=\"x\"}\nCCO\n```\n"),
                         {"fenced code attributes ({.class key=value})": "attributes"})

    def test_lettered_lists_need_two_items_in_a_row(self):
        self.assertEqual(self.needs("a. one\nb. two\n"), {"lettered or Roman-numeral lists": "fancy_lists"})
        self.assertEqual(self.needs("(i) one\n(ii) two\n"), {"lettered or Roman-numeral lists": "fancy_lists"})
        self.assertEqual(self.needs("I. Introduction\n\nSome text.\n"), {})
        self.assertEqual(self.needs("A. one\n\nlater text\n\nc. unrelated\n"), {})


@needs_pandoc(3, 1, 3)
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-reader-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.directory / "config"),
                    "APPDATA": str(self.directory / "config")}

    def run_pdfmd(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=self.env)

    def write(self, name, text):
        (self.directory / name).write_text(text, encoding="utf-8")

    def test_what_gfm_can_take_is_added_to_it_and_nothing_is_said_but_in_verbose(self):
        self.write("a.md", "# Water\n\nH~2~O\n")
        self.write("b.md", "# Plain\n\nNothing special.\n")
        done = self.run_pdfmd("a.md", "-t", "html")
        self.assertNotIn("NOTE", done.stdout)
        self.assertIn("<sub>2</sub>", (self.directory / "a.html").read_text(encoding="utf-8"))
        said = self.run_pdfmd("a.md", "-t", "html", "-v").stdout
        self.assertIn("reading as gfm+subscript (it uses subscripts (H~2~O))", said)
        self.assertIn("reading as gfm\n", self.run_pdfmd("b.md", "-t", "html", "-v").stdout)

    def test_what_gfm_cannot_read_switches_the_reader(self):
        self.write("a.md", "# Note\n\nText with a note^[the inline note].\n")
        said = self.run_pdfmd("a.md", "-t", "html", "-v").stdout
        self.assertIn("it uses inline footnotes (^[...]), which gfm cannot read; keeping the default markdown reader", said)
        self.assertIn("the inline note", (self.directory / "a.html").read_text(encoding="utf-8"))
        self.assertIn("footnote", (self.directory / "a.html").read_text(encoding="utf-8"))
        self.write("b.md", "# Raw\n\n\\textbf{bold} here and ```` ``` ```` no.\n")
        self.assertIn("raw LaTeX", self.run_pdfmd("b.md", "-t", "html", "-v").stdout)

    def test_the_same_syntax_in_a_code_block_changes_nothing(self):
        self.write("a.md", "# Example\n\n```\nH~2~O ^[note] \\begin{x}\n```\n")
        said = self.run_pdfmd("a.md", "-t", "html", "-v").stdout
        self.assertIn("reading as gfm\n", said)

    def test_the_reader_option_picks_the_dialect_for_one_document_or_a_folder(self):
        self.write("a.md", "---\ntitle: T\npdfmd-options:\n  reader: gfm\n---\n\nH~2~O\n")
        self.assertEqual(self.run_pdfmd("a.md", "-t", "html").returncode, 0)
        self.assertNotIn("<sub>", (self.directory / "a.html").read_text(encoding="utf-8"))
        self.write("b.md", "# Water\n\nH~2~O\n")
        self.write("metadata.yaml", "pdfmd-options:\n  reader: markdown\n")
        said = self.run_pdfmd("b.md", "-t", "html")
        self.assertNotIn("read as gfm", said.stdout)
        self.assertIn("<sub>", (self.directory / "b.html").read_text(encoding="utf-8"))


    def test_deep_reads_adjacent_blocks_after_front_matter(self):
        body = ("Intro followed by a list.\n- entry\n\n"
                "Intro followed by a heading.\n## Section\n\n"
                "Intro followed by a quote.\n> quoted\n\n"
                "Intro followed by a table.\nName | Value\n--- | ---\nA | B\n")
        self.write("a.md", "---\ntitle: Sample\npdfmd-options: {dialect-detect: deep}\n---\n\n" + body)
        done = self.run_pdfmd("a.md", "-t", "html", "-v")
        self.assertEqual(done.returncode, 0, done.stderr)
        html = (self.directory / "a.html").read_text(encoding="utf-8")
        for tag in ("<ul>", "<h2", "<blockquote>", "<table>"):
            self.assertIn(tag, html)
        self.assertIn("lines 7, 10, 13, 16", done.stdout)

    def test_basic_keeps_its_body_and_hints_at_deep(self):
        self.write("a.md", "---\ntitle: Sample\n---\n\nProse.\n- entry\n")
        done = self.run_pdfmd("a.md", "-t", "html", "-v")
        self.assertEqual(done.returncode, 0, done.stderr)
        html = (self.directory / "a.html").read_text(encoding="utf-8")
        self.assertNotIn("<ul>", html)
        self.assertIn("dialect-detect: deep", done.stdout)
        self.write("a.md", "---\ntitle: Sample\npdfmd-options: {dialect-detect: basic}\n---\n\nProse.\n- entry\n")
        done = self.run_pdfmd("a.md", "-t", "html")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.directory / "a.html").read_text(encoding="utf-8"), html)

    def test_toml_front_matter_has_a_default_warning_and_deep_reads_it(self):
        source = '+++\ntitle = "Synthetic note"\n+++\n\nProse.\n- entry\n'
        self.write("a.md", source)
        done = self.run_pdfmd("a.md", "-t", "html")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr.count("TOML front matter"), 1)
        self.assertIn("dialect-detect: deep", done.stderr)
        self.assertIn("+++", (self.directory / "a.html").read_text(encoding="utf-8"))
        self.write("dialect.yaml", "pdfmd-options: {dialect-detect: deep}\n")
        done = self.run_pdfmd("a.md", "-t", "html", "-y", "dialect.yaml", "--standalone")
        self.assertEqual(done.returncode, 0, done.stderr)
        html = (self.directory / "a.html").read_text(encoding="utf-8")
        self.assertNotIn("+++", html)
        self.assertIn("<ul>", html)
        if sys.version_info >= (3, 11):
            self.assertIn("<title>Synthetic note</title>", html)
        else:
            self.assertIn("NOTE", done.stderr)
        self.assertEqual((self.directory / "a.md").read_text(encoding="utf-8"), source)


    def test_deep_probe_corpus(self):
        self.write("dialect.yaml", "pdfmd-options: {dialect-detect: DeEp}\n")
        probes = {
            "gfm": ("- plain list\n", "<ul>"),
            "pandoc": ("% Synthetic title\n\nA note^[footnote].\n", "footnote"),
            "commonmark": ("---\ntitle: Synthetic\n---\n\nParagraph.\n\n> quote\n", "<blockquote>"),
            "obsidian": ("---\ntitle: Synthetic\n---\n\nTry this.\n%%\n# Hidden\n%%\n\n==marked==\n", "marked"),
            "r-markdown": ("```{r}\nx <- 2\n```\n", "x &lt;- 2"),
            "multimarkdown": ("Title: Synthetic\nAuthor: Example\n\nBody.\n", "Author: Example"),
            "jekyll": ("---\nlayout: post\n---\n\nText.\n## Heading\n", "<h2"),
            "mixed": ("---\ntitle: Synthetic\n---\n\n<!-- Prose\n# Example\n-->\n\n"
                      "```\nExample\n- Item\n```\n\n$$\ntext\n- x\n$$\n", "<pre>"),
            "not-toml": ("+++\nOrdinary fenced-looking prose.\n+++\n", "+++"),
        }
        for name, (source, expected) in probes.items():
            with self.subTest(name=name):
                self.write("a.md", source)
                done = self.run_pdfmd("a.md", "-t", "html", "-y", "dialect.yaml", "-v")
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertNotIn("TOML front matter", done.stderr)
                self.assertIn(expected, (self.directory / "a.html").read_text(encoding="utf-8"))
                self.assertEqual("GFM-style blocks after front matter" in done.stdout, name == "jekyll")


class FrontMatterCheck(unittest.TestCase):
    """`has_yaml_frontmatter` says what Pandoc's own Markdown reader says (v3.32.4). The table was measured with Pandoc 3.13
    (`pandoc -f markdown -t json`): a block opens with `---` and a non-blank line, closes with `---` or `...`."""

    def test_what_pandoc_reads_as_a_metadata_block(self):
        for text in ("---\ntitle: T\n---\n\nBody\n",
                     "---\ntitle: T\n...\n\nBody\n",
                     "---\n---\n\nBody\n",                                  # an empty block still is one (the documented escape hatch)
                     "---\n...\n\nBody\n",
                     "---\r\ntitle: T\r\n---\r\n\r\nBody\r\n",
                     "---  \ntitle: T\n---\n\nBody\n",
                     "﻿---\ntitle: T\n---\n\nBody\n",
                     "\n---\ntitle: T\n---\n\nBody\n",                      # Pandoc allows blank lines before the block
                     "---\ntitle: T\n\nauthor: A\n---\n\nBody\n"):
            with self.subTest(text=text):
                self.assertTrue(pdfmd.has_yaml_frontmatter(text))

    def test_what_pandoc_reads_as_a_horizontal_rule(self):
        for text in ("---\n\nBody\n",
                     "---\n\nBody\n\n---\n\nMore\n",                        # a second rule does not close a block the first never opened
                     "---\nBody text\n\nmore\n",                            # no closing line
                     "---\ntitle: T\n\nBody\n",
                     "---\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
                     "----\ntitle: T\n---\n",                               # four dashes are a rule
                     "Text first\n\n---\ntitle: T\n---\n",
                     ""):
            with self.subTest(text=text):
                self.assertFalse(pdfmd.has_yaml_frontmatter(text))


@needs_pandoc(3, 1, 3)
class GlobalMetadataAndTheReader(unittest.TestCase):
    """The global metadata (`pdfmd --setup`) is the machine's, not the document's: it no longer makes pdfmd keep Pandoc's reader
    for a file with no front matter (v3.32.4), and everything it sets still applies."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-reader-global-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.config = self.directory / "config" / "config.yaml"             # the global metadata is `metadata.yaml` beside it
        self.config.parent.mkdir()
        self.env = {**os.environ, "PDFMD_CONFIG": str(self.config), "XDG_CONFIG_HOME": str(self.directory / "xdg"),
                    "APPDATA": str(self.directory / "xdg")}

    def global_metadata(self, text):
        (self.config.parent / "metadata.yaml").write_text(text, encoding="utf-8")

    def write(self, name, text):
        (self.directory / name).write_text(text, encoding="utf-8")

    def run_pdfmd(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=self.env)

    def tex(self, name="a.md"):
        done = self.run_pdfmd(name, "-v", "--stop-at", "tex")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.directory / name).with_suffix(".tex").read_text(encoding="utf-8"), done.stdout

    def test_a_file_without_front_matter_is_read_as_gfm_with_global_metadata_in_place(self):
        self.global_metadata("title: Global title\n")
        self.write("a.md", "Plain text.\n\nH~2~O\n")
        tex, said = self.tex()
        self.assertIn("no YAML front matter; reading as gfm", said)
        self.assertIn("reading as gfm+subscript", said)
        self.assertIn("H\\textsubscript{2}O", tex)                               # gfm with the subscript extension
        self.assertIn("\\title{Global title}", tex)                              # ...and the global metadata still applies

    def test_what_the_global_metadata_holds_still_applies_under_gfm(self):
        self.global_metadata("title: Global title\nheader-includes:\n  - |\n    \\newcommand{\\fromglobal}{x}\nabstract: Water is H~2~O.\n")
        self.write("a.md", "Plain text.\n")
        tex, said = self.tex()
        self.assertNotIn("keeping the default markdown reader", said)
        self.assertIn("\\newcommand{\\fromglobal}{x}", tex)                      # raw LaTeX in a metadata string
        self.assertIn("H\\textsubscript{2}O", tex)                               # Markdown in a metadata string

    def test_the_global_reader_option_still_wins(self):
        self.global_metadata("pdfmd-options:\n  reader: markdown\n")
        self.write("a.md", "Plain text.\n\nH~2~O\n")
        tex, said = self.tex()
        self.assertNotIn("read as gfm", said)
        self.assertIn("H\\textsubscript{2}O", tex)

    def test_a_metadata_file_beside_the_document_still_means_pandoc_markdown(self):
        self.global_metadata("title: Global title\n")
        self.write("metadata.yaml", "author: Someone\n")
        self.write("a.md", "Plain text.\n\nH~2~O\n")
        tex, said = self.tex()
        self.assertIn("metadata.yaml is linked; keeping the default markdown reader", said)
        self.assertIn("H\\textsubscript{2}O", tex)

    def test_a_leading_rule_is_not_front_matter(self):
        self.write("a.md", "---\n\nPlain text.\n\nH~2~O\n")
        tex, said = self.tex()
        self.assertIn("no YAML front matter; reading as gfm", said)

    def test_a_bare_title_is_still_left_alone_next_to_global_metadata(self):
        """pinned, not changed: promote_bare_title() treats the global metadata as external, as before."""
        self.global_metadata("title: Global title\n")
        self.write("a.md", "# Water\n\nText\n")
        tex, _ = self.tex()
        self.assertIn("\\title{Global title}", tex)
        self.assertIn("\\section{Water}", tex)                                   # the heading was not promoted to the title


@needs_pandoc(3, 1, 3)
class ReaderHistory(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="pdfmd-reader-history-")
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.document = self.directory / "doc.md"
        self.hst = self.directory / ".backups" / "doc.hst"
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}

    def write(self, text):
        self.document.write_text(text, encoding="utf-8")

    def build(self, *extra, source="doc.md", ok=True):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), source, "--to", "html",
                               *([] if "--no-stamp" in extra else ["--stamp"]),
                               "--stamp-store", "file", "--no-backup", *extra],
                              cwd=self.directory, env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode == 0, ok, done.stdout + done.stderr)
        return done.stdout + done.stderr

    def entries(self):
        import pdfmd_history
        return pdfmd_history.read_file(self.hst)[0]

    def test_front_matter_changes_the_reader_once_and_preserves_the_output(self):
        self.write("Ordinary text.\n")
        self.assertNotIn("reader changed from", self.build())
        first = self.entries()[0].meta_dict()["reader"]
        self.assertTrue(first.startswith("gfm"), first)
        self.assertNotIn("reader changed from", self.build())
        self.write("---\ntitle: Title\n---\n\nOrdinary text.\n")
        said = self.build()
        newest = self.entries()[0].meta_dict()["reader"]
        self.assertTrue(newest.startswith("markdown"), newest)
        self.assertEqual(said.count("reader changed from"), 1, said)
        self.assertIn(f"reader changed from {first} to {newest}", said)
        self.assertIn("front matter", said)
        output = (self.directory / "doc.html").read_bytes()
        self.assertNotIn("reader changed from", self.build())
        self.assertEqual((self.directory / "doc.html").read_bytes(), output)

    def test_latest_legacy_entry_without_a_reader_never_warns(self):
        import pdfmd_history
        self.write("---\ntitle: Title\n---\n\nOrdinary text.\n")
        entries = [pdfmd_history.Entry("2000-01-02 00:00:00", "compiled", "legacy"),
                   pdfmd_history.Entry("2000-01-01 00:00:00", "compiled", "older", (("reader", "commonmark_x"),))]
        pdfmd_history.write_file(self.hst, entries, "doc.md")
        self.assertNotIn("reader changed from", self.build())
        self.assertTrue(self.entries()[0].meta_dict()["reader"].startswith("markdown"))

    def test_disabled_history_and_failed_builds_leave_the_baseline_alone(self):
        self.write("Ordinary text.\n")
        self.build()
        before = self.hst.read_bytes()
        self.write("---\ntitle: Title\n---\n\nOrdinary text.\n")
        self.assertNotIn("reader changed from", self.build("--no-stamp"))
        self.assertEqual(self.hst.read_bytes(), before)
        self.build("--from", "not_a_pandoc_reader", ok=False)
        self.assertEqual(self.hst.read_bytes(), before)
        self.assertIn("reader changed from", self.build())

    def test_explicit_readers_are_recorded_without_warning(self):
        self.write("Ordinary text.\n")
        self.build()
        self.assertNotIn("reader changed from", self.build("--from", "commonmark_x"))
        self.assertEqual(self.entries()[0].meta_dict()["reader"], "commonmark_x")
        self.write("---\npdfmd-options: {reader: gfm}\n---\n\nOrdinary text.\n")
        self.assertNotIn("reader changed from", self.build())
        self.assertEqual(self.entries()[0].meta_dict()["reader"], "gfm")
        self.write("---\npdfmd-options: {reader: commonmark_x}\n---\n\nOrdinary text.\n")
        self.assertNotIn("reader changed from", self.build())
        self.assertEqual(self.entries()[0].meta_dict()["reader"], "commonmark_x")

    def test_partial_history_entries_do_not_record_or_compare_a_reader(self):
        self.write("Ordinary text.\n")
        self.build()
        baseline = self.entries()[0]
        self.write("---\ntitle: Title\n---\n\n# One\n\nOne.\n\n# Two\n\nTwo.\n")
        self.assertNotIn("reader changed from", self.build("--stamp-partial", source="doc#one"))
        entries = self.entries()
        partial = [entry for entry in entries if entry.kind == "partial"]
        self.assertEqual(len(partial), 1)
        self.assertNotIn("reader", partial[0].meta_dict())
        compiled = [entry for entry in entries if entry.kind == "compiled"]
        self.assertEqual(compiled[0].meta_dict()["reader"], baseline.meta_dict()["reader"])

    def test_a_strict_failure_does_not_commit_the_new_reader(self):
        self.write("Ordinary text.\n")
        self.build()
        before = self.hst.read_bytes()
        self.write("---\ntitle: Title\n---\n\nOrdinary text.\n")
        self.assertIn("reader changed from", self.build("--strict", ok=False))
        self.assertEqual(self.hst.read_bytes(), before)
        self.assertIn("reader changed from", self.build())

    def test_metadata_reader_and_no_auto_reader_are_explicit_choices(self):
        self.write("Ordinary text.\n")
        self.build()
        metadata = self.directory / "chosen.yaml"
        metadata.write_text("pdfmd-options: {reader: commonmark_x}\n", encoding="utf-8")
        self.assertNotIn("reader changed from", self.build("--metadata-file", str(metadata)))
        self.assertEqual(self.entries()[0].meta_dict()["reader"], "commonmark_x")
        self.assertNotIn("reader changed from", self.build("--no-auto", "reader"))
        self.assertEqual(self.entries()[0].meta_dict()["reader"], "markdown")

    def test_report_readers_are_compared_in_both_routes(self):
        for route in ("route", "patch"):
            with self.subTest(route=route):
                self.write("Ordinary text.\n")
                if self.hst.exists():
                    self.hst.unlink()
                self.build("--report")
                self.write(f"---\ntitle: Title\npdfmd-options: {{report-build: {route}}}\n---\n\nOrdinary text.\n")
                before = self.hst.read_bytes()
                self.assertIn("reader changed from", self.build("--report", "--strict", ok=False))
                self.assertEqual(self.hst.read_bytes(), before)
                self.assertIn("reader changed from", self.build("--report"))
                self.assertNotIn("reader changed from", self.build("--report"))

    def test_config_reader_is_an_explicit_choice(self):
        self.write("Ordinary text.\n")
        self.build()
        config = self.directory / "config.yaml"
        config.write_text("options:\n  reader: commonmark_x\n", encoding="utf-8")
        self.env["PDFMD_CONFIG"] = str(config)
        self.assertNotIn("reader changed from", self.build())
        self.assertEqual(self.entries()[0].meta_dict()["reader"], "commonmark_x")

    def test_an_automatic_flavour_still_warns_and_removing_front_matter_warns(self):
        self.write("Ordinary text.\n")
        self.build("--flavour", "pdfmd")
        self.write("---\ntitle: Title\n---\n\nOrdinary text.\n")
        self.assertIn("reader changed from", self.build("--flavour", "pdfmd"))
        self.write("Ordinary text.\n")
        said = self.build("--flavour", "pdfmd")
        self.assertIn("reader changed from markdown", said)
        self.assertIn("no YAML front matter", said)

    def test_a_batch_keeps_each_files_reader_and_override_separate(self):
        self.write("Ordinary text.\n")
        other = self.directory / "other.md"
        other.write_text("---\npdfmd-options: {reader: commonmark_x}\n---\n\nOther.\n", encoding="utf-8")
        self.build("other.md")
        self.write("---\ntitle: Title\n---\n\nOrdinary text.\n")
        said = self.build("other.md")
        self.assertEqual(said.count("reader changed from"), 1, said)
        self.assertIn("doc.md: reader changed from", said)


if __name__ == "__main__":
    unittest.main()
