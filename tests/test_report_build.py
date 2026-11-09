"""v3.32.18 (entry 3ek): a report (`-r`) is built by the build of one document (`report-build: route`, the default), and the
titles of its files are chapter headings (`report-titles`). Real builds through pdfmd; the finished LaTeX is read back."""

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

import pdfmd  # noqa: E402
from pdfmd_report import route, titles  # noqa: E402

ONE = "---\ntitle: Alpha\nsubtitle: first one\nauthor: Ann\nchapter: 1\n---\n\nIntro.\n\n# Alpha heading\n\ntext\n"
TWO = ("---\ntitle: Beta\nauthor: Bob\nchapter: 2\nkeywords: [x]\n---\n\nSetext two\n----------\n\n```\n# not a heading\n```\n\n"
       "# Beta heading\n\nmore\n")


class Pieces(unittest.TestCase):
    def test_headings_go_down_one_level_and_code_is_left_alone(self):
        body = "# One\n\nSetext\n======\n\nTwo\n---\n\n```\n# code\n```\n\n###### Six\n"
        self.assertEqual(titles.shift_headings(pdfmd, body),
                         "## One\n\n## Setext\n\n### Two\n\n```\n# code\n```\n\n###### Six\n")

    def test_keys_are_cut_and_written_without_touching_the_others(self):
        head = "---\ntitle: A\n  continued\nsubtitle: S\nauthor: X\nlist:\n- a\n---\n"
        self.assertEqual(titles.drop_keys(head, ("title", "subtitle")), "---\nauthor: X\nlist:\n- a\n---\n")
        self.assertIn('title: "He said \\"hi\\""', titles.put_keys("---\nauthor: X\n---\n", {"title": 'He said "hi"'}))

    def test_an_empty_front_matter_is_not_left_behind(self):
        chapter = titles.Chapter(drop=("title",), heading="# T", title="T")
        self.assertEqual(titles.apply(pdfmd, "---\ntitle: T\n---\n\nBody\n", chapter), "# T\n\nBody\n")

    def test_a_title_the_file_repeats_is_not_printed_twice(self):
        chapter = titles.Chapter(drop=("title",), heading="# T", title="T", shift=True)
        self.assertEqual(titles.apply(pdfmd, "\n# T\n\ntext\n\n# Other\n", chapter), "# T\n\ntext\n\n## Other\n")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Builds(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")}

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def report(self, *args: str, first: str = ONE, second: str = TWO, options: str = ""):
        if options:
            first = first.replace("title: Alpha\n", f"title: Alpha\npdfmd-options: {{{options}}}\n")
        self.write("a.md", first)
        self.write("b.md", second)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "-r", ".", "--no-stamp", "--no-backup", "--no-auto", "crossref",
                               "--to", "tex", *args], cwd=self.root, capture_output=True, text=True, env=self.env)
        book = self.root / "book.tex"
        return done, (book.read_text(encoding="utf-8") if book.is_file() else "")

    def test_two_titles_become_two_chapters_and_the_files_headings_go_down(self):
        done, tex = self.report()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(tex, r"\\chapter\{Alpha\}")
        self.assertRegex(tex, r"\\chapter\{Beta\}")
        self.assertRegex(tex, r"\\section\{Alpha heading\}")
        self.assertRegex(tex, r"\\section\{Beta heading\}")
        self.assertRegex(tex, r"\\subsection\{Setext two\}")             # a level-2 setext heading, one down
        self.assertIn("# not a heading", tex)
        self.assertNotIn("\\title{", tex)
        self.assertLess(tex.index("\\chapter{Alpha}"), tex.index("\\chapter{Beta}"))
        self.assertIn("NOTE  report-titles: 2 files have a title", done.stdout)
        self.assertIn("the document class is report", done.stdout)

    def test_a_class_with_chapters_is_kept_and_one_without_is_said(self):
        for klass, expected in (("book", r"\\chapter\{Beta\}"), ("article", r"\\section\{Beta\}")):
            done, tex = self.report(first=ONE.replace("title: Alpha\n", f"title: Alpha\ndocumentclass: {klass}\n"))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertRegex(tex, expected, klass)
            self.assertNotIn("the document class is report", done.stdout, klass)
        self.assertIn("has no chapters", done.stdout)
        self.assertNotRegex(tex, r"\\chapter\{")

    def test_a_report_is_chapters_even_with_one_or_no_title(self):
        done, tex = self.report(second=TWO.replace("title: Beta\n", ""))
        self.assertRegex(tex, r"\\chapter\{Alpha heading\}")
        self.assertRegex(tex, r"\\chapter\{Beta heading\}")
        self.assertIn("the document class is report", done.stdout)

    def test_a_subtitle_and_a_different_author_are_a_line_under_the_heading(self):
        _, tex = self.report()
        self.assertRegex(tex, r"(?s)\\chapter\{Alpha\}.*?\\emph\{first one\}")
        self.assertRegex(tex, r"(?s)\\chapter\{Beta\}.*?\\emph\{Bob\}")
        self.assertNotRegex(tex, r"\\emph\{Ann\}")                       # the first file's author is the book's

    def test_one_title_is_the_books_as_before(self):
        done, tex = self.report(second=TWO.replace("title: Beta\n", ""))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("\\title{Alpha", tex)
        self.assertRegex(tex, r"\\chapter\{Alpha heading\}")
        self.assertNotIn("report-titles", done.stdout)

    def test_first_and_last_keep_one_title_as_the_books(self):
        for policy, title in (("first", "Alpha"), ("last", "Beta")):
            done, tex = self.report(options=f"report-titles: {policy}")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertRegex(tex, r"\\title\{%s" % title, policy)
            self.assertRegex(tex, r"\\chapter\{Alpha heading\}", policy)             # no heading was moved
            self.assertNotRegex(tex, r"\\chapter\{(Alpha|Beta)\}", policy)

    def test_the_patch_build_makes_the_same_chapters(self):
        done, tex = self.report(options="report-build: patch")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(tex, r"\\chapter\{Beta\}")
        self.assertRegex(tex, r"\\section\{Beta heading\}")
        self.assertNotIn("\\title{", tex)

    def test_a_later_files_front_matter_that_the_report_does_not_use_is_said(self):
        done, _ = self.report()
        self.assertIn("front matter of later files that a report build does not use", done.stdout)
        self.assertIn("keywords", done.stdout)

    def test_a_bad_setting_is_said(self):
        done, _ = self.report(options="report-build: sideways")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("report-build", done.stderr)
        done, _ = self.report(options="report-titles: sideways")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("report-titles", done.stderr)

    def test_the_default_is_route(self):
        self.write("x.md", "---\ntitle: X\n---\n\ntext\n")
        self.assertEqual(route.resolve_build(pdfmd, self.root / "x.md", []), "route")
        self.assertEqual(titles.resolve_policy(pdfmd, self.root / "x.md", []), "chapters")


@unittest.skipUnless(shutil.which("pandoc") and (shutil.which("lualatex") or shutil.which("xelatex")), "needs Pandoc and LaTeX")
class Fonts(unittest.TestCase):
    """The bug of entry 3ek: the PDF branch of a report chose no font and ignored -f/--font, so ≥ ′ came out as 'Missing
    character' in Latin Modern. (A font that pdfmd picks itself needs the font installed, so only the flag is tested here.)"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "a.md").write_text("---\ntitle: A\nchapter: 1\n---\n\nx ≥ 2 and y′ ≈ 3.\n", encoding="utf-8")
        (self.root / "b.md").write_text("---\ntitle: B\nchapter: 2\n---\n\nmore text\n", encoding="utf-8")
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")}

    def build(self, *args: str, options: str = ""):
        if options:
            text = (self.root / "a.md").read_text(encoding="utf-8")
            (self.root / "a.md").write_text(text.replace("title: A\n", f"title: A\npdfmd-options: {{{options}}}\n"), encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "-r", ".", "--verbose", "--no-stamp", "--no-backup", *args],
                              cwd=self.root, capture_output=True, text=True, env=self.env)

    def test_the_font_flag_reaches_the_report_in_both_builds(self):
        for options in ("", "report-build: patch"):
            done = self.build("--font", "Latin Modern Roman", options=options)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            command = next(line for line in (done.stdout + done.stderr).splitlines() if line.startswith("CMD"))
            self.assertIn("mainfont=Latin Modern Roman", command, options)


if __name__ == "__main__":
    unittest.main()
