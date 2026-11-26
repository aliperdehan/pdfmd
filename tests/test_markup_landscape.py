"""v3.29.19: universal markup, the seventh kind: blocks on landscape pages."""

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

from pandoc_support import ODF, office_markup  # noqa: E402

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "lib" / "pdfmd_lua" / "markup.lua"

SOURCE = """\
Before.

::: landscape
A wide table here
:::

<div style="page: landscape">

Styled

</div>

\\begin{landscape}

tex land

\\end{landscape}

After.
"""


def convert(writer: str, enabled: str = "landscape", *extra: str) -> tuple[str, str]:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--lua-filter", str(FILTER), "-M", f"pdfmd-markup={enabled}", *extra],
                          input=SOURCE, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout, done.stderr


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_latex_gets_the_environment(self):
        out, _ = convert("latex")
        self.assertEqual(out.count("\\begin{landscape}"), 3)
        self.assertEqual(out.count("\\end{landscape}"), 3)

    def test_typst_gets_flipped_pages(self):
        out, _ = convert("typst")
        self.assertEqual(out.count("#page(flipped: true)["), 3)
        self.assertIn("tex land", out)

    def test_html_gets_a_named_page_and_the_rest_a_name_too(self):
        out, _ = convert("html5", "landscape", "-s", "--metadata", "title=T")
        self.assertEqual(out.count('<div class="pdfmd-landscape">'), 3)
        self.assertEqual(out.count("@page landscape { size: landscape; }"), 1)
        self.assertIn("body { page: pdfmd-normal; }", out)                       # WeasyPrint returns to portrait only by a name
        self.assertIn("<p>tex land</p>", out)

    def test_an_engine_without_named_pages_keeps_the_text_and_says_so(self):
        out, err = convert("html5", "landscape", "-M", "pdfmd-no-named-pages=1")
        self.assertNotIn("pdfmd-landscape", out)
        self.assertIn("A wide table here", out)
        self.assertEqual(err.count("landscape pages are not made in this PDF engine"), 1)

    def test_opendocument_uses_landscape_until_the_next_portrait_content(self):
        source = SOURCE.replace("A wide table here", "| a | b |\n|---|---|\n| 1 | 2 |")
        source += "\n::: landscape\n- One item\n- Another item\n:::\n"
        with tempfile.TemporaryDirectory() as folder:
            document, styles = office_markup(folder, source, "odt", "--paper", "a4", "--markup", "landscape")
            disabled, _ = office_markup(folder, source, "odt", "--paper", "a4", "--no-markup")

        def attribute(element, prefix, name):
            return element.get(f"{{{ODF[prefix]}}}{name}")

        master_pages = styles.findall(".//style:master-page", ODF)
        self.assertEqual(len(master_pages), 2)
        layout_names = [attribute(master, "style", "page-layout-name") for master in master_pages]
        original, turned = [styles.find(f".//style:page-layout[@style:name='{name}']/style:page-layout-properties", ODF)
                            for name in layout_names]
        self.assertEqual(attribute(turned, "style", "print-orientation"), "landscape")
        self.assertEqual(attribute(original, "fo", "page-width"), attribute(turned, "fo", "page-height"))
        self.assertEqual(attribute(original, "fo", "page-height"), attribute(turned, "fo", "page-width"))
        self.assertEqual(attribute(original, "fo", "margin-left"), attribute(turned, "fo", "margin-left"))
        master_names = [attribute(master, "style", "name") for master in master_pages]
        page_styles = {attribute(style, "style", "name"): attribute(style, "style", "master-page-name")
                       for style in document.findall(".//style:style", ODF)
                       if attribute(style, "style", "master-page-name")}
        transitions = [(index, page_styles[name]) for index, element in
                       enumerate(document.find(".//office:text", ODF).iter())
                       if (name := attribute(element, "text", "style-name") or attribute(element, "table", "style-name"))
                       in page_styles]
        self.assertEqual([page for _, page in transitions], [master_names[1], master_names[0], master_names[1]])
        table = document.find(".//table:table", ODF)
        table_style = attribute(table, "table", "style-name")
        self.assertEqual(page_styles[table_style], master_names[1])
        properties = document.find(f".//style:style[@style:name='{table_style}']/style:table-properties", ODF)
        self.assertEqual(attribute(properties, "fo", "break-before"), "page")
        self.assertEqual(disabled.findall(".//style:style[@style:master-page-name]", ODF), [])

    def test_opendocument_can_begin_on_a_landscape_page(self):
        source = "::: landscape\nFirst paragraph.\n:::\n\nBack to the original layout.\n"
        with tempfile.TemporaryDirectory() as folder:
            document, _ = office_markup(folder, source, "odt", "--markup", "landscape")
        paragraphs = document.findall(".//office:text/text:p", ODF)
        self.assertEqual(["".join(para.itertext()) for para in paragraphs], ["First paragraph.", "Back to the original layout."])
        for index, para in enumerate(paragraphs):
            name = para.get(f"{{{ODF['text']}}}style-name")
            style = document.find(f".//style:style[@style:name='{name}'][@style:master-page-name]", ODF)
            self.assertIsNotNone(style)
            properties = style.find("style:paragraph-properties", ODF)
            if index:
                self.assertEqual(properties.get(f"{{{ODF['fo']}}}break-before"), "page")
            else:
                self.assertTrue(properties is None or f"{{{ODF['fo']}}}break-before" not in properties.attrib)

    def test_only_when_the_kind_is_on(self):
        out, _ = convert("html5", "toc")
        self.assertIn('<div class="landscape">', out)


@unittest.skipUnless(PANDOC and shutil.which("weasyprint") and shutil.which("pdfinfo"), "needs Pandoc, WeasyPrint and pdfinfo")
class Build(unittest.TestCase):
    def test_a_weasyprint_pdf_has_a_landscape_page_between_portrait_ones(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "d.md").write_text("---\ntitle: T\npdfmd-options:\n  markup: [landscape]\n---\n\nPortrait.\n\n::: landscape\nWide\n:::\n\nPortrait again.\n",
                                       encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-e", "weasyprint", "-o", "d.pdf", "--no-stamp"],
                                  cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            info = subprocess.run(["pdfinfo", "-f", "1", "-l", "5", str(root / "d.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            sizes = [line.split("size:")[1].split("pts")[0].split("x") for line in info.splitlines() if "size:" in line and "Page" in line]
            shapes = ["landscape" if float(width) > float(height) else "portrait" for width, height in sizes]
            self.assertEqual(shapes, ["portrait", "landscape", "portrait"])


if __name__ == "__main__":
    unittest.main()
