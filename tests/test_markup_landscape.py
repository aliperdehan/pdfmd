"""v3.29.19: universal markup, the seventh kind: blocks on landscape pages."""

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

from pandoc_support import discard_path  # noqa: E402

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "pdfmd_lua" / "markup.lua"

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

    def test_opendocument_keeps_the_text_and_says_so_once(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "odt", "-o", discard_path(".odt"),
                               "--lua-filter", str(FILTER), "-M", "pdfmd-markup=landscape"], input=SOURCE, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr.count("landscape pages are not made in odt"), 1)

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
