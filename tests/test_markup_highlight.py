"""v3.29.17: universal markup, the fifth kind: ==highlighted text==."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pandoc_support import discard_path  # noqa: E402

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
FILTER = ROOT / "lib" / "pdfmd_lua" / "markup.lua"

SOURCE = ("Some ==marked text== here, ==one== and ==with *emph* inside==, ==end==. A lone == sign and a == b == c.\n\n"
          "`==code==` stays. ==multi\nline==\n")


def convert(writer: str, enabled: str = "highlight", text: str = SOURCE, *extra: str) -> tuple[str, str]:
    done = subprocess.run([PANDOC, "-f", "markdown", "-t", writer, "--wrap=none", "--lua-filter", str(FILTER), "-M",
                           f"pdfmd-markup={enabled}", *extra], input=text, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout, done.stderr


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_single_character_does_not_consume_the_next_highlight(self):
        for writer, expected in (("html5", "<mark>x</mark> and <mark>xy</mark>"),
                                 ("latex", "\\pdfmdhl{x} and \\pdfmdhl{xy}"),
                                 ("typst", "#highlight[x] and #highlight[xy]")):
            with self.subTest(writer=writer):
                out, _ = convert(writer, text="==x== and ==xy==\n")
                self.assertIn(expected, out)

    def test_html_gets_mark(self):
        out, _ = convert("html5")
        self.assertIn("<mark>marked text</mark>", out)
        self.assertIn("<mark>one</mark>", out)
        self.assertIn("<mark>with <em>emph</em> inside</mark>", out)
        self.assertIn("<mark>end</mark>.", out)                                   # a punctuation mark after the closer stays outside
        self.assertIn("<mark>multi line</mark>", out)
        self.assertIn("A lone == sign and a == b == c.", out)                     # not a pair around text
        self.assertIn("<code>==code==</code>", out)

    def test_latex_gets_the_macro(self):
        out, _ = convert("latex")
        self.assertIn("\\pdfmdhl{marked text}", out)
        self.assertIn("\\pdfmdhl{with \\emph{emph} inside}", out)
        self.assertNotIn("<mark>", out)

    def test_typst_gets_highlight(self):
        out, _ = convert("typst")
        self.assertIn("#highlight[marked text]", out)

    def test_gfm_gets_mark_and_pandoc_markdown_is_left_alone(self):
        out, _ = convert("gfm")
        self.assertIn("<mark>marked text</mark>", out)
        out, _ = convert("markdown")
        self.assertIn("==marked text==", out)

    def test_opendocument_keeps_the_text_and_says_so_once(self):
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "odt", "-o", discard_path(".odt"),
                               "--lua-filter", str(FILTER), "-M", "pdfmd-markup=highlight"], input=SOURCE, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr.count("highlighting is not applied to odt"), 1)

    def test_only_when_the_kind_is_on(self):
        out, _ = convert("html5", enabled="toc")
        self.assertIn("==marked text==", out)
        self.assertNotIn("<mark>", out)

    def test_pandoc_3_12_marks_keep_working_with_the_extension_on(self):
        done = subprocess.run([PANDOC, "-f", "markdown+mark", "-t", "latex", "--lua-filter", str(FILTER), "-M", "pdfmd-markup=highlight"],
                              input="A ==marked== word.\n", capture_output=True, text=True)
        if done.returncode != 0:
            self.skipTest("this Pandoc has no mark extension")
        self.assertIn("\\pdfmdhl{marked}", done.stdout)


class Header(unittest.TestCase):
    def test_the_latex_definition_is_in_the_one_header_file(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "d.md"
            doc.write_text("---\ntitle: T\npdfmd-options:\n  markup: [highlight, callouts]\n---\n\ntext\n", encoding="utf-8")
            with mock.patch.object(pdfmd, "cache_root", lambda: Path(folder) / "cache"):
                args = pdfmd.markup_header_args(doc, [])
            text = Path(args[1]).read_text(encoding="utf-8")
            self.assertIn("\\newcommand{\\pdfmdhl}[1]{\\hl{#1}}", text)
            self.assertIn("\\newtcolorbox{pdfmdcallout}", text)
            self.assertEqual(args.count("--include-in-header"), 1)
            doc.write_text("---\ntitle: T\npdfmd-options:\n  markup: [toc]\n---\n\ntext\n", encoding="utf-8")
            self.assertEqual(pdfmd.markup_header_args(doc, []), [])               # a kind that needs no LaTeX needs no file


LUALATEX = shutil.which("lualatex")
KPSEWHICH = shutil.which("kpsewhich")


def tex_file(name: str) -> bool:
    return bool(KPSEWHICH) and bool(subprocess.run([KPSEWHICH, name], capture_output=True, text=True).stdout.strip())


class LuaColor(unittest.TestCase):
    """v3.33.70: lua-ul's `\\highLight` colours through luacolor, which Pandoc's template loads only for struck-out text, so
    `==x==` stopped LuaLaTeX ("Color support in lua-ul requires luacolor") and pdfmd fell back to XeLaTeX."""

    def test_both_headers_load_luacolor_before_lua_ul(self):
        markup = pdfmd.load_package("pdfmd_tex.markup")
        for header in (pdfmd.MARKUP_HIGHLIGHT_HEADER, markup.HIGHLIGHT_GUARDED):
            self.assertIn("{luacolor.sty}{\\def\\pdfmdhasluaul{1}}", header)        # lua-ul without luacolor: soul instead
            self.assertLess(header.index("{luacolor}"), header.index("{lua-ul}"))

    @unittest.skipUnless(PANDOC and LUALATEX and tex_file("lua-ul.sty") and tex_file("luacolor.sty"),
                         "needs Pandoc, LuaLaTeX, lua-ul and luacolor")
    def test_a_plain_document_builds_on_lualatex_with_its_highlight(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = Path(folder) / "d.md"
            doc.write_text("Some ==marked words== here.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), str(doc), "--no-backup", "--no-stamp"],
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                  env={**__import__("os").environ, "PDFMD_NO_PROMPT": "1", "PDFMD_BUILD_LOG": "off"})
            output = done.stdout + done.stderr
            self.assertEqual(done.returncode, 0, output)
            self.assertRegex(output, r"OK +\S*d\.md > d\.pdf .*\(lualatex\)")
            self.assertNotIn("failed", output)
            if shutil.which("pdftoppm"):
                from PIL import Image
                subprocess.run(["pdftoppm", "-r", "40", "-f", "1", "-l", "1", "-png", str(Path(folder) / "d.pdf"),
                                str(Path(folder) / "page")], check=True)
                image = Image.open(next(Path(folder).glob("page*.png"))).convert("RGB")
                yellow = [1 for red, green, blue in image.getdata() if red > 230 and green > 225 and blue < 200]
                self.assertGreater(len(yellow), 20)                 # the pale yellow of pdfmd-mark (FFF3A3) is on the page


if __name__ == "__main__":
    unittest.main()
