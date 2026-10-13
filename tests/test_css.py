"""v3.28.41: a style sheet. pdfmd_css reads the parts that mean something to LaTeX, Typst and Word; pdfmd finds `pdfmd.css` and
`NAME.css` beside a document, takes `css:` from the front matter, a metadata file or pdfmd-options, and with `css-scope: all`
turns what it can into Pandoc variables below what the document sets."""

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

import pdfmd_css  # noqa: E402

SHEET = """
/* the page */
@page { size: letter landscape; margin: 2cm 3cm; }
html, body { font-family: "STIX Two Text", Georgia, serif; font-size: 11pt; line-height: 1.3; text-indent: 1.5em; }
a:link { color: #0645AD; }
code, pre { font-family: 'JetBrains Mono', monospace; font-size: 90%; }
h1 { color: red; font-size: 20pt; }
table { border-collapse: collapse; }
@media screen { body { font-size: 18px; line-height: 2; } }
@media print { body { line-height: 1.25; } }
@font-face { font-family: X; src: url(x.woff); }
@import url("other.css");
"""


class Reader(unittest.TestCase):
    def test_the_rules_come_in_order_with_their_media(self):
        rules = pdfmd_css.parse(SHEET)
        self.assertEqual([rule.selector for rule in rules][:3], ["@page", "html, body", "a:link"])
        self.assertEqual([rule.media for rule in rules if rule.selector == "body"], ["screen", "print"])
        self.assertNotIn("@font-face", [rule.selector for rule in rules])

    def test_print_counts_and_screen_and_conditions_do_not(self):                  # (v3.29.8: see test_css_v2 for the rest)
        for media, expected in (("", True), ("print", True), ("all", True), ("print and all", True), ("screen", False),
                                ("(min-width: 600px)", False), ("screen and (min-width: 1px)", False)):
            self.assertEqual(pdfmd_css.applies(media), expected, media)


class Translation(unittest.TestCase):
    def setUp(self):
        self.result = pdfmd_css.translate(SHEET)
        self.variables = self.result.variables

    def test_the_page(self):
        self.assertIn("papersize=letter", self.variables)
        self.assertIn("geometry:landscape", self.variables)
        for side, value in (("top", "2cm"), ("right", "3cm"), ("bottom", "2cm"), ("left", "3cm")):
            self.assertIn(f"geometry:{side}={value}", self.variables)

    def test_the_body_and_the_last_rule_that_applies_wins(self):
        self.assertIn("mainfont=STIX Two Text", self.variables)      # the first family that is not generic
        self.assertIn("fontsize=11pt", self.variables)
        self.assertIn("linestretch=1.25", self.variables)             # @media print after the plain rule; screen ignored
        self.assertIn("indent=true", self.variables)

    def test_links_and_code(self):
        self.assertIn("linkcolor=[HTML]{0645AD}", self.variables)
        self.assertIn("colorlinks=true", self.variables)
        self.assertIn("monofont=JetBrains Mono", self.variables)

    def test_what_it_does_not_use_is_named(self):
        ignored = " ".join(self.result.ignored)
        for word in ("table border-collapse", "(@media screen)"):
            self.assertIn(word, ignored)
        self.assertEqual(self.result.headings, {1: {"color": "red", "font-size": "20pt"}})     # v3.29.8: kept for LaTeX

    def test_a_size_latex_has_no_class_for_is_not_used_and_a_px_body_is_converted_only_when_it_fits(self):
        out = pdfmd_css.translate("body { font-size: 14pt }")
        self.assertEqual(out.variables, [])
        self.assertIn("14pt", " ".join(out.ignored))
        self.assertIn("fontsize=12pt", pdfmd_css.translate("body { font-size: 16px }").variables)    # 16 px = 12 pt
        self.assertEqual(pdfmd_css.translate("body { line-height: 150% }").variables, ["linestretch=1.5"])

    def test_one_margin_for_every_side_is_one_setting(self):
        self.assertEqual(pdfmd_css.translate("@page { margin: 1in }").variables, ["geometry:margin=1in"])
        self.assertIn("geometry:left=1cm", pdfmd_css.translate("@page { margin-left: 1cm }").variables)

    def test_an_empty_or_broken_sheet_is_nothing(self):
        for text in ("", "/* only a comment */", "body { font-size: ; }", "a { color: "):
            self.assertEqual(pdfmd_css.translate(text).variables, [], text)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Build(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "d.md").write_text("---\ntitle: T\n---\n\nSome text and `code`.\n", encoding="utf-8")
        (self.root / "pdfmd.css").write_text(
            "@page { size: letter; margin: 2cm }\nbody { font-size: 11pt; font-family: 'STIX Two Text' }\n", encoding="utf-8")
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}

    def run_pdfmd(self, *args: str) -> str:
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "latex", "-o", "d.tex", "--no-stamp",
                               "--verbose", *args], cwd=self.root, env=self.env, capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout + (self.root / "d.tex").read_text(encoding="utf-8")

    def test_a_sheet_beside_the_document_changes_nothing_for_latex_by_default(self):
        out = self.run_pdfmd()
        self.assertNotIn("papersize=letter", out)
        self.assertNotIn("-> fontsize", out)
        self.assertIn("pdfmd.css: found; --css-scope all reads it", out)   # said, not applied

    def test_with_css_scope_all_it_sets_the_paper_the_size_and_the_font(self):
        out = self.run_pdfmd("--css-scope", "all")
        self.assertIn("papersize=letter", out)
        self.assertIn("fontsize=11pt", out)
        self.assertIn("mainfont=STIX Two Text", out)
        self.assertIn("geometry:margin=2cm", out)
        self.assertIn("letterpaper", out)                                # in the .tex itself
        self.assertIn("11pt", out)

    def test_what_the_document_sets_wins_over_the_sheet(self):
        (self.root / "d.md").write_text("---\ntitle: T\npapersize: a5\nfontsize: 12pt\ngeometry: margin=1in\n---\n\nText.\n",
                                        encoding="utf-8")
        out = self.run_pdfmd("--css-scope", "all")
        self.assertNotIn("papersize=letter", out)
        self.assertNotIn("fontsize=11pt", out)
        self.assertNotIn("geometry:margin=2cm", out)
        self.assertIn("mainfont=STIX Two Text", out)                     # the sheet still fills what nothing else sets
        self.assertNotIn("papersize=letter", out)                        # and is not said to have set what it did not

    def test_the_scope_can_be_a_pdfmd_option_and_the_sheet_can_be_named(self):
        (self.root / "pdfmd.css").unlink()
        (self.root / "my.css").write_text("@page { size: a5 }\n", encoding="utf-8")
        (self.root / "d.md").write_text("---\ntitle: T\npdfmd-options:\n  css: my.css\n  css-scope: all\n---\n\nText.\n",
                                        encoding="utf-8")
        self.assertIn("papersize=a5", self.run_pdfmd())

    def test_css_in_the_front_matter_is_read_like_a_pdfmd_option(self):
        (self.root / "pdfmd.css").unlink()
        (self.root / "my.css").write_text("@page { size: a5 }\n", encoding="utf-8")
        (self.root / "d.md").write_text("---\ntitle: T\ncss: my.css\npdfmd-options:\n  css-scope: all\n---\n\nText.\n",
                                        encoding="utf-8")
        self.assertIn("papersize=a5", self.run_pdfmd())

    def test_no_auto_css_leaves_a_sheet_beside_the_document_alone(self):
        out = self.run_pdfmd("--css-scope", "all", "--no-auto", "css")
        self.assertNotIn("papersize=letter", out)

    def test_the_command_line_sheet_comes_last_and_html_links_what_it_is_given(self):
        (self.root / "late.css").write_text("body { font-size: 12pt }\n", encoding="utf-8")
        out = self.run_pdfmd("--css-scope", "all", "--css", "late.css")
        self.assertIn("fontsize=12pt", out)                              # after pdfmd.css's 11pt
        html = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "html", "-o", "d.html", "--standalone",
                               "--no-stamp", "--css", "late.css"], cwd=self.root, env=self.env, capture_output=True,
                              text=True, timeout=300)
        self.assertEqual(html.returncode, 0, html.stdout + html.stderr)
        page = (self.root / "d.html").read_text(encoding="utf-8")
        self.assertIn('href="', page)
        self.assertIn("late.css", page)
        self.assertIn("pdfmd.css", page)

    def test_a_missing_sheet_is_a_warning_not_a_failure(self):
        (self.root / "d.md").write_text("---\ntitle: T\npdfmd-options:\n  css: nope.css\n---\n\nText.\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "latex", "-o", "d.tex", "--no-stamp"],
                              cwd=self.root, env=self.env, capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("nope.css was not found", done.stderr)


if __name__ == "__main__":
    unittest.main()
