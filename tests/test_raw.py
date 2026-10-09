"""Raw passthrough (`pdfmd-options.raw`, --raw) and PDF images in HTML builds: pdfmd_raw parsing, the Lua filters through
Pandoc, and the real command line."""

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

import pdfmd_raw  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402

PANDOC = shutil.which("pandoc")
TYPST = shutil.which("typst")
POPPLER = shutil.which("pdftocairo")
RAW_LUA = ROOT / "pdfmd_lua" / "raw.lua"
PDF_LUA = ROOT / "pdfmd_lua" / "pdf_images.lua"

DOCUMENT = """\
---
title: Raw
---

Text with <b>bold *md* inside</b> and <i>italic</i>, a line<br>break and \\textbf{tex bold}.

<div class="note">

A paragraph in a div, with **markdown**.

</div>

<table>
<tr><th>A</th><th>B</th></tr>
<tr><td>1</td><td>2</td></tr>
</table>

```{=typst}
#rect(width: 40pt, height: 12pt, fill: red)
```

```{=latex}
\\textit{raw latex block}
```
"""


class Parsing(unittest.TestCase):
    def test_off_by_default_and_for_the_words_that_mean_off(self):
        for value in (None, False, "off", "no", "auto", "", "none"):
            self.assertIsNone(pdfmd_raw.parse(value), value)

    def test_all_lists_everything_for_every_family(self):
        table = pdfmd_raw.parse("all")
        self.assertEqual(sorted(table), ["html", "office", "tex", "typst"])
        self.assertEqual(table["tex"], ["tex", "html", "typst", "office"])
        self.assertEqual(pdfmd_raw.parse(True), table)

    def test_a_list_is_the_same_for_each_family_and_names_have_aliases(self):
        table = pdfmd_raw.parse(["latex", "HTML"])
        self.assertEqual(table["office"], ["tex", "html"])

    def test_a_mapping_per_family_leaves_the_others_to_pandoc_unless_default_is_given(self):
        table = pdfmd_raw.parse({"html": ["tex", "typst"], "docx": "html"})
        self.assertEqual(table, {"html": ["tex", "typst"], "office": ["html"]})
        table = pdfmd_raw.parse({"html": [], "default": ["html"]})
        self.assertEqual(table["html"], [])
        self.assertEqual(table["tex"], ["html"])

    def test_nonsense_is_an_error_with_the_names_in_it(self):
        with self.assertRaises(pdfmd_raw.RawError) as caught:
            pdfmd_raw.parse(["markdownish"])
        self.assertIn("typst", str(caught.exception))
        with self.assertRaises(pdfmd_raw.RawError):
            pdfmd_raw.parse({"printer": ["html"]})

    def test_merge_sets_one_family(self):
        table = pdfmd_raw.merge(None, "latex", ["html"])
        self.assertEqual(table, {"tex": ["html"]})


@needs_pandoc(3, 0)
class Filter(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="pdfmd-raw-"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "doc.md").write_text(DOCUMENT, encoding="utf-8")

    def convert(self, target: str, table: dict, *filters: Path) -> str:
        config = self.folder / "config.yaml"
        import json
        config.write_text(json.dumps({"pdfmd-raw": table, "pdfmd-raw-cache": str(self.folder / "cache")}), encoding="utf-8")
        command = [PANDOC, "doc.md", "-t", target, "--metadata-file", str(config)]
        for item in filters or (RAW_LUA,):
            command += ["--lua-filter", str(item)]
        done = subprocess.run(command, capture_output=True, text=True, cwd=self.folder)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_html_is_read_into_the_targets_own_elements(self):
        for target, expect in (("latex", ("\\textbf{bold \\emph{md} inside}", "\\emph{italic}", "longtable", "\\\\")),
                               ("typst", ("#strong[bold #emph[md] inside]", "#table(")),
                               ("html", ("<strong>tex bold</strong>",))):
            out = self.convert(target, {"tex": ["html", "tex"], "typst": ["html", "tex"], "html": ["html", "tex"],
                                        "office": ["html"]})
            for piece in expect:
                self.assertIn(piece, out, (target, piece))

    def test_a_div_keeps_the_markdown_inside_it(self):
        out = self.convert("html", {"html": ["html"]})
        self.assertIn('<div class="note">', out)
        self.assertIn("<strong>markdown</strong>", out)

    def test_latex_is_read_for_html_and_typst(self):
        out = self.convert("html", {"html": ["tex"]})
        self.assertIn("<strong>tex bold</strong>", out)
        self.assertIn("<em>raw latex block</em>", out)
        self.assertNotIn("<table", out)                  # html is not on this family's list: left out

    def test_a_syntax_not_listed_is_dropped_even_the_familys_own(self):
        out = self.convert("html", {"html": ["tex"]})
        self.assertNotIn("<table", out)                 # (a <div> with Markdown inside is a native Div, not raw)
        self.assertNotIn("<b>", out)
        out = self.convert("latex", {"tex": ["html"]})
        self.assertNotIn("raw latex block", out)
        self.assertIn("longtable", out)

    def test_a_family_that_is_not_mentioned_is_left_to_pandoc(self):
        out = self.convert("latex", {"html": ["html"]})
        self.assertIn("raw latex block", out)             # its own syntax stays
        self.assertNotIn("longtable", out)                # the foreign html is dropped, as always

    @unittest.skipUnless(TYPST, "typst is not installed")
    def test_typst_becomes_a_pdf_picture_in_latex_and_an_svg_in_html(self):
        out = self.convert("latex", {"tex": ["typst"]})
        self.assertRegex(out, r"includegraphics(?:\[[^\]]*\])?\{[^}]+\.pdf\}")
        pictures = list((self.folder / "cache").glob("*.pdf"))
        self.assertEqual(len(pictures), 1)
        self.assertTrue(pictures[0].read_bytes().startswith(b"%PDF"))
        if POPPLER:
            html = self.convert("html", {"html": ["typst"]})
            self.assertRegex(html, r'<img\s+src="[^"]+\.svg"')

    def test_without_the_option_nothing_changes(self):
        done = subprocess.run([PANDOC, "doc.md", "-t", "html", "--lua-filter", str(RAW_LUA)], capture_output=True,
                              text=True, cwd=self.folder)
        plain = subprocess.run([PANDOC, "doc.md", "-t", "html"], capture_output=True, text=True, cwd=self.folder)
        self.assertEqual(done.stdout, plain.stdout)


@needs_pandoc(3, 0)
@unittest.skipUnless(TYPST and POPPLER, "typst and pdftocairo are needed to make and convert a PDF figure")
class PdfImages(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="pdfmd-pdfimg-"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        subprocess.run([TYPST, "compile", "-", str(self.folder / "fig.pdf")], input="#rect(width: 60pt, height: 20pt, fill: blue)",
                       text=True, check=True, capture_output=True)
        (self.folder / "d.md").write_text('---\ntitle: T\n---\n\n![the figure](fig.pdf)\n\nRaw: <img src="fig.pdf" width="80">\n',
                                          encoding="utf-8")
        import json
        (self.folder / "cfg.yaml").write_text(json.dumps({"pdfmd-raw-cache": str(self.folder / "cache")}), encoding="utf-8")

    def html(self, *filters):
        command = [PANDOC, "d.md", "-t", "html", "--metadata-file", "cfg.yaml"]
        for item in filters:
            command += ["--lua-filter", str(item)]
        return subprocess.run(command, capture_output=True, text=True, cwd=self.folder).stdout

    def test_a_pdf_image_becomes_an_svg_in_markdown_and_in_raw_html(self):
        out = self.html(PDF_LUA)
        self.assertNotIn("fig.pdf", out)
        self.assertEqual(out.count(".svg"), 2)
        self.assertEqual(len(list((self.folder / "cache").glob("*.svg"))), 1)       # one picture, kept by its content

    def test_other_writers_are_left_alone(self):
        done = subprocess.run([PANDOC, "d.md", "-t", "latex", "--metadata-file", "cfg.yaml", "--lua-filter", str(PDF_LUA)],
                              capture_output=True, text=True, cwd=self.folder)
        self.assertIn("fig.pdf", done.stdout)

    def test_through_pdfmd_and_switched_off_by_no_auto(self):
        env = {**os.environ, "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"], "XDG_CACHE_HOME": str(self.folder / "xdg")}
        run = lambda *extra: subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-t", "html", "--self-contained",
                                             *extra], capture_output=True, text=True, cwd=self.folder, env=env)
        self.assertEqual(run("-o", "on.html").returncode, 0)
        self.assertEqual((self.folder / "on.html").read_text(encoding="utf-8").count("data:image/svg+xml"), 2)
        self.assertEqual(run("-o", "off.html", "--no-auto", "pdfimages").returncode, 0)
        self.assertEqual((self.folder / "off.html").read_text(encoding="utf-8").count("data:image/svg+xml"), 0)


@needs_pandoc(3, 0)
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="pdfmd-rawcli-"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.env = {**os.environ, "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"], "XDG_CACHE_HOME": str(self.folder / "xdg")}
        (self.folder / "raw.md").write_text(DOCUMENT, encoding="utf-8")

    def build(self, *extra) -> str:
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "raw.md", "-o", "out.typ", *extra],
                              capture_output=True, text=True, cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.folder / "out.typ").read_text(encoding="utf-8")

    def test_the_flag_the_option_and_the_per_family_flag(self):
        self.assertNotIn("#strong[bold", self.build())                              # off: html is dropped for Typst
        self.assertIn("#strong[bold #emph[md] inside]", self.build("--raw"))
        self.assertIn("#strong[bold", self.build("--raw-for", "typst=html"))
        self.assertNotIn("#strong[bold", self.build("--raw", "--no-raw"))
        front = DOCUMENT.replace("title: Raw", "title: Raw\npdfmd-options:\n  raw:\n    typst: [html]")
        (self.folder / "raw.md").write_text(front, encoding="utf-8")
        self.assertIn("#strong[bold", self.build())

    def test_latex_for_html_goes_through_the_route_that_draws_what_it_can(self):
        # raw: html takes tex -> pdfmd turns on the LaTeX route (pdfmd_office), so \ce is chemistry, not a stripped macro
        front = ("---\ntitle: T\npdfmd-options:\n  raw:\n    html: [html, tex]\n---\n\n"
                 "Water is \\ce{H2O} and <b>bold</b>.\n")
        (self.folder / "chem.md").write_text(front, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "chem.md", "-o", "chem.html"], capture_output=True,
                              text=True, cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        html = (self.folder / "chem.html").read_text(encoding="utf-8")
        self.assertIn("H<sub>2</sub>O", html)
        self.assertIn("<b>bold</b>", html)               # its own syntax stays as written

    def test_a_bad_value_is_a_warning_not_a_failure(self):
        front = DOCUMENT.replace("title: Raw", "title: Raw\npdfmd-options:\n  raw: [nonsense]")
        (self.folder / "raw.md").write_text(front, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "raw.md", "-o", "out.typ"], capture_output=True,
                              text=True, cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0)
        self.assertIn("not a raw syntax", done.stderr)


if __name__ == "__main__":
    unittest.main()
