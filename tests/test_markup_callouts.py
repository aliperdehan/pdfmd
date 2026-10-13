"""v3.29.13: universal markup, the first kind. Callouts (GitHub's and Obsidian's `> [!NOTE]`, a fenced div, Quarto's
`::: callout-tip`) become the writer's own box. Off unless asked."""

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

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "pdfmd_lua" / "markup.lua"

SOURCE = """\
# H

> [!NOTE]
> Useful **info**.

> [!warning] A Title
> Careful.
> second line

> [!tip]-
> folded

> [!bug]
> maps to caution

::: {.caution title="Custom"}
A div caution.
:::

::: callout-important
## Quarto title
body
:::

::: note
A div note.
:::

> an ordinary quote

> text first [!NOTE] is not a marker
"""


def convert(text: str, writer: str, *extra: str) -> str:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--lua-filter", str(FILTER), *extra], input=text,
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_html_gets_a_div_per_callout_and_its_style_once(self):
        out = convert(SOURCE, "html5", "-s", "--metadata", "title=T")
        for kind in ("note", "warning", "tip", "caution", "important"):
            self.assertIn(f'class="callout callout-{kind}"', out)
        self.assertEqual(out.count("class=\"callout callout-note\""), 2)       # [!NOTE] and ::: note
        self.assertIn('class="callout callout-caution"', out)
        self.assertEqual(out.count(".callout-title {"), 1)                       # the style, once
        self.assertIn("<strong>A Title</strong>", out)
        self.assertIn("<strong>Custom</strong>", out)                            # title="" of the div
        self.assertIn("<strong>Quarto title</strong>", out)                      # the first heading of a Quarto callout
        self.assertIn("text first [!NOTE] is not a marker", out)                 # the marker has to start the quote
        self.assertIn("<blockquote>", out)                                       # the ordinary quote stays

    def test_the_title_is_the_rest_of_the_first_line_and_the_body_the_rest(self):
        out = convert("> [!warning] A Title\n> Careful.\n> second line\n", "html5")
        self.assertIn("<strong>A Title</strong>", out)
        self.assertIn("<p>Careful. second line</p>", out)

    def test_a_marker_alone_gets_the_default_title_and_a_fold_marker_goes(self):
        out = convert("> [!tip]-\n> folded\n", "html5")
        self.assertIn("<strong>Tip</strong>", out)
        self.assertNotIn("-</", out)

    def test_obsidian_names_map_to_the_five(self):
        out = convert("> [!bug]\n> x\n\n> [!question]\n> y\n\n> [!todo]\n> z\n", "html5")
        self.assertIn("callout-caution", out)
        self.assertIn("callout-important", out)
        self.assertIn("callout-note", out)

    def test_an_unknown_name_is_a_note_titled_with_it(self):
        out = convert("> [!custom]\n> x\n", "html5")
        self.assertIn("callout-note", out)
        self.assertIn("<strong>custom</strong>", out)

    def test_latex_gets_the_environment_with_the_kinds_colour(self):
        out = convert(SOURCE, "latex")
        self.assertIn("\\begin{pdfmdcallout}{pdfmd-note}", out)
        self.assertIn("\\begin{pdfmdcallout}{pdfmd-caution}", out)
        self.assertEqual(out.count("\\begin{pdfmdcallout}"), out.count("\\end{pdfmdcallout}"))
        self.assertIn("\\textbf{A Title}", out)

    def test_typst_gets_a_tinted_block(self):
        out = convert(SOURCE, "typst")
        self.assertIn('#block(width: 100%, inset: 8pt, radius: 2pt, fill: rgb("#0969DA").lighten(92%)', out)
        self.assertIn("#strong[Quarto title]", out)

    def test_other_writers_get_a_quote_with_a_bold_title(self):
        out = convert("> [!NOTE]\n> Useful.\n", "markdown")
        self.assertIn("> **Note**", out)
        self.assertIn("> Useful.", out)

    def test_the_kinds_asked_for_decide(self):
        out = convert("> [!NOTE]\n> x\n", "html5", "-M", "pdfmd-markup=toc")
        self.assertNotIn("callout", out)
        self.assertIn("[!NOTE]", out)


class Options(unittest.TestCase):
    def test_values(self):
        self.assertEqual(pdfmd.markup_value(None), [])
        self.assertEqual(pdfmd.markup_value(False), [])
        self.assertEqual(pdfmd.markup_value(True), ["callouts"])
        self.assertEqual(pdfmd.markup_value("all"), ["callouts"])
        self.assertEqual(pdfmd.markup_value(["callouts"]), ["callouts"])
        self.assertEqual(pdfmd.markup_value("off"), [])

    def test_a_flag_and_the_document_and_no_markup(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "d.md"
            doc.write_text("---\ntitle: T\npdfmd-options:\n  markup: callouts\n---\n\ntext\n", encoding="utf-8")
            try:
                self.assertEqual(pdfmd.markup_kinds(doc, []), ["callouts"])
                pdfmd.MARKUP_CLI.update({"off": True})
                self.assertEqual(pdfmd.markup_kinds(doc, []), [])
                self.assertEqual(pdfmd.markup_filter_args(doc, []), [])
                pdfmd.MARKUP_CLI.update({"off": False, "kinds": []})
                self.assertEqual(pdfmd.markup_kinds(doc, []), ["callouts"])        # a bare --markup is all of them
            finally:
                pdfmd.MARKUP_CLI.update({"kinds": None, "off": False})
            args = pdfmd.markup_filter_args(doc, [])
            self.assertEqual(args[:2], ["-M", "pdfmd-markup=callouts"])
            self.assertTrue(args[-1].endswith("markup.lua"))

    def test_off_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "d.md"
            doc.write_text("---\ntitle: T\n---\n\n> [!NOTE]\n> x\n", encoding="utf-8")
            self.assertEqual(pdfmd.markup_filter_args(doc, []), [])
            self.assertEqual(pdfmd.markup_header_args(doc, []), [])

    def test_the_latex_header_is_a_file_of_pdfmd_s_own(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "d.md"
            doc.write_text("---\ntitle: T\npdfmd-options:\n  markup: callouts\n---\n\ntext\n", encoding="utf-8")
            from unittest import mock
            with mock.patch.object(pdfmd, "cache_root", lambda: Path(folder) / "cache"):
                args = pdfmd.markup_header_args(doc, [])
            self.assertEqual(args[0], "--include-in-header")
            self.assertTrue(Path(args[1]).name.startswith("packages-"))
            text = Path(args[1]).read_text(encoding="utf-8")
            self.assertIn("\\newtcolorbox{pdfmdcallout}", text)
            self.assertIn("\\newenvironment{pdfmdcallout}", text)                   # the fallback without tcolorbox


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Build(unittest.TestCase):
    def test_a_build_with_code_still_has_the_box_environment(self):
        # pdfmd's own header files (the code header) replace metadata header-includes: the environment is in a header file of its own
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "d.md").write_text("---\ntitle: T\npdfmd-options:\n  markup: callouts\n---\n\n> [!NOTE]\n> Hello.\n\n```python\nprint(1)\n```\n",
                                       encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "latex", "-o", "d.tex", "--no-stamp"],
                                  cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            text = (root / "d.tex").read_text(encoding="utf-8")
            self.assertIn("\\newenvironment{pdfmdcallout}", text)
            self.assertIn("\\begin{pdfmdcallout}{pdfmd-note}", text)
            self.assertIn("fvextra", text)

    def test_the_flag_turns_it_on_and_no_markup_turns_it_off(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "d.md").write_text("---\ntitle: T\n---\n\n> [!NOTE]\n> Hello.\n", encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            command = [sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "latex", "-o", "d.tex", "--no-stamp"]
            done = subprocess.run([*command, "--markup"], cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("\\begin{pdfmdcallout}", (root / "d.tex").read_text(encoding="utf-8"))
            done = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertNotIn("pdfmdcallout", (root / "d.tex").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
