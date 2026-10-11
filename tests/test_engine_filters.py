"""The filters pdfmd adds for one engine: pdfmd_lua/typst.lua (v3.27.11: links to anchors the document does not have,
pictures with an older Pandoc) and pdfmd_lua/weasyprint.lua (v3.27.12: math WeasyPrint cannot draw)."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
TYPST = shutil.which("typst")
WEASYPRINT = shutil.which("weasyprint")
TYPST_LUA = ROOT / "pdfmd_lua" / "typst.lua"

DOCUMENT = """\
# Head {#h}

Intro.

::: {#d}
A div.
:::

A [span]{#s} here.

``` {#c}
code
```

[to the head](#h) [to the div](#d) [to the span](#s) [to the code](#c) [gone](#nope) [again](#nope)
[web](https://example.org/)
"""


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-typst-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def convert(self, writer: str) -> subprocess.CompletedProcess:
        source = self.directory / "doc.md"
        source.write_text(DOCUMENT, encoding="utf-8")
        return subprocess.run([PANDOC, str(source), "-t", writer, "--lua-filter", str(TYPST_LUA)], capture_output=True,
                              text=True, encoding="utf-8")

    def test_links_to_labels_stay_and_the_others_become_text(self):
        done = self.convert("typst")
        self.assertEqual(done.returncode, 0, done.stderr)
        for kept in ("#link(<h>)", "#link(<d>)", "#link(<s>)", '#link("https://example.org/")'):
            self.assertIn(kept, done.stdout)
        self.assertNotIn("<c>)", done.stdout)                      # a code block's id is no Typst label
        self.assertNotIn("<nope>", done.stdout)
        self.assertIn("to the code", done.stdout)
        self.assertIn("gone", done.stdout)
        self.assertEqual(done.stderr.count("WARN"), 1)
        self.assertIn("3 links to anchors that are not in the document (#c, #nope)", done.stderr)

    def test_other_writers_are_untouched(self):
        done = self.convert("html")
        self.assertIn('href="#nope"', done.stdout)
        self.assertNotIn("WARN", done.stderr)

    def test_a_label_used_twice_is_kept_by_the_first_element(self):
        # v3.28.2: "label <fig:tlc> occurs multiple times" stopped a lab report through the LaTeX filter
        source = self.directory / "twice.md"
        source.write_text("::: {#x}\nFirst.\n:::\n\n# Second {#x}\n\n[link](#x)\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-t", "typst", "--lua-filter", str(TYPST_LUA)], capture_output=True,
                              text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.count("<x>"), 2)                 # the div's label and the link to it
        self.assertIn("1 label on more than one element (x)", done.stderr)


@unittest.skipUnless(PANDOC and TYPST, "needs Pandoc and Typst")
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-typst-cli-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    def test_a_link_to_a_missing_anchor_does_not_stop_the_pdf(self):
        (self.directory / "doc.md").write_text(DOCUMENT, encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "doc.pdf").is_file())
        self.assertIn("links to anchors that are not in the document", done.stdout + done.stderr)

    def test_a_picture_is_found_when_pandoc_runs_in_the_metadata_files_folder(self):
        # pdfmd runs Pandoc in the first metadata file's folder; a Pandoc before 3.2 did not find the picture there
        (self.directory / "pictures").mkdir()
        (self.directory / "pictures" / "dot.png").write_bytes(tiny_png())
        (self.directory / "shared").mkdir()
        (self.directory / "shared" / "meta.yaml").write_text("lang: en\n", encoding="utf-8")
        (self.directory / "doc.md").write_text("# A\n\n![A dot](pictures/dot.png)\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-y", "shared/meta.yaml", "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "doc.pdf").is_file())
        typ = self.run_pdfmd("doc.md", "-y", "shared/meta.yaml", "-t", "typst", "-o", "doc.typ")
        self.assertEqual(typ.returncode, 0, typ.stdout + typ.stderr)
        self.assertIn('image("pictures/dot.png"', (self.directory / "doc.typ").read_text(encoding="utf-8"))

    def test_the_filter_is_given_only_to_typst(self):
        self.assertEqual(pdfmd.typst_filter_args("latex"), [])
        self.assertEqual(pdfmd.typst_filter_args("typst")[-1], str(TYPST_LUA))


class WeasyPrintArguments(unittest.TestCase):
    def test_plain_math_and_the_filter_only_for_weasyprint(self):
        self.assertEqual(pdfmd.weasyprint_math_args("typst", []), [])
        arguments = pdfmd.weasyprint_math_args("weasyprint", [])
        self.assertEqual(arguments[-1], str(ROOT / "pdfmd_lua" / "weasyprint.lua"))
        if pdfmd.pandoc_has_option("--math-method"):
            self.assertIn("--math-method=plain", arguments)

    def test_the_command_lines_math_wins(self):
        arguments = pdfmd.weasyprint_math_args("weasyprint", ["--mathml"])
        self.assertFalse([item for item in arguments if item.startswith("--math")])
        self.assertIn("--lua-filter", arguments)


@unittest.skipUnless(PANDOC and WEASYPRINT, "needs Pandoc and WeasyPrint")
class WeasyPrintMath(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-weasy-math-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, text: str) -> subprocess.CompletedProcess:
        (self.directory / "doc.md").write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "weasyprint"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory, env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    def test_math_is_text_once_and_said_once(self):
        done = self.build("---\ntitle: M\n---\n\nSee $\\alpha_i \\le \\beta$ and $x^2 + \\frac{a}{b}$.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertEqual(said.count("WeasyPrint does not typeset math"), 1)
        self.assertIn("2 formulas are printed as text", said)
        if shutil.which("pdftotext"):
            text = subprocess.run(["pdftotext", str(self.directory / "doc.pdf"), "-"], capture_output=True,
                                  text=True).stdout
            self.assertIn("α", text)
            self.assertNotIn("x2+ab", text)                    # MathML's flat text, before the TeX, is gone

    def test_no_math_no_warning(self):
        done = self.build("---\ntitle: M\n---\n\nJust words.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("typeset math", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
