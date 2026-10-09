"""Diagrams written as code: ```dot, ```d2, ```mermaid (v3.26.16).

No Graphviz, D2 or Mermaid is needed: the tests put stand-ins for `dot`, `neato`, `d2`, `mmdc` and `rsvg-convert` first on
PATH, each of which writes a tiny valid picture and notes that it ran. What they check is what pdfmd does around the tool:
which format it asks for per output, the cache, the blocks left as code, the warnings.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from pandoc_support import needs_pandoc  # noqa: E402

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20" viewBox="0 0 40 20"><rect width="40" height="20" fill="#ccc"/></svg>'
PNG_BYTES = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f8ffff3f0005fe02fe"
                          "a735810000000049454e44ae426082")
PNG = "".join(f"\\{byte:03o}" for byte in PNG_BYTES)           # as printf writes it: no xxd or other program is needed
PDF = "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" \
      "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 40 20]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"

# Each stand-in writes what the real tool would, in the format it is asked for, and appends its name to ran.log.
PDF_LINE = PDF.replace("\n", "\\n")                              # one line for printf (it turns \n back into a newline)
GRAPHVIZ = """#!/bin/sh
echo "$0 $*" >> "$STUB_LOG"
while read -r _; do :; done
case "$1" in
  -Tsvg) printf '%s' '@SVG@' ;;
  -Tpng) printf '@PNG@' ;;
  -Tpdf) printf '%s' '@PDF@' ;;
  *) exit 1 ;;
esac
"""
FAILING = """#!/bin/sh
echo "$0 $*" >> "$STUB_LOG"
while read -r _; do :; done
echo "Error: syntax error in line 1" >&2
exit 1
"""
D2 = """#!/bin/sh
echo "d2 $*" >> "$STUB_LOG"
for last; do :; done
printf '%s' '@SVG@' > "$last"
"""
MERMAID = """#!/bin/sh
echo "mmdc $*" >> "$STUB_LOG"
while [ $# -gt 0 ]; do
  if [ "$1" = "-o" ]; then out="$2"; fi
  shift
done
case "$out" in
  *.png) printf '@PNG@' > "$out" ;;
  *.svg) printf '%s' '@SVG@' > "$out" ;;
  *.pdf) printf '%s' '@PDF@' > "$out" ;;
esac
"""
RSVG = """#!/bin/sh
echo "rsvg-convert $*" >> "$STUB_LOG"
while [ $# -gt 0 ]; do
  if [ "$1" = "-o" ]; then out="$2"; fi
  shift
done
case "$out" in
  *.png) printf '@PNG@' > "$out" ;;
  *) printf '%s' '@PDF@' > "$out" ;;
esac
"""
GRAPHVIZ, D2, MERMAID, RSVG = (script.replace("@SVG@", SVG).replace("@PNG@", PNG).replace("@PDF@", PDF_LINE)
                               for script in (GRAPHVIZ, D2, MERMAID, RSVG))


# A stand-in whose PDF is a real one (the SVG through rsvg-convert), for a build that LaTeX or Typst really typesets.
REAL_GRAPHVIZ = """#!/bin/sh
echo "$0 $*" >> "$STUB_LOG"
while read -r _; do :; done
case "$1" in
  -Tsvg) printf '%s' '@SVG@' ;;
  -Tpdf) printf '%s' '@SVG@' | rsvg-convert -f pdf ;;
  *) exit 1 ;;
esac
""".replace("@SVG@", SVG)


def has(program: str) -> bool:
    return shutil.which(program) is not None


@unittest.skipUnless(has("pandoc") and sys.platform != "win32", "needs pandoc, and shell scripts as stand-ins for the tools")
class Diagrams(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-diagram-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.stubs = self.directory / "stubs"
        self.stubs.mkdir()
        self.log = self.directory / "ran.log"
        self.log.write_text("")
        self.cache = self.directory / "cache"
        # a PATH with Pandoc and the stand-ins only: no real dot, d2 or mmdc can answer
        self.bare = self.directory / "bare"
        self.bare.mkdir()
        (self.bare / "pandoc").symlink_to(shutil.which("pandoc"))

    def install(self, **tools: str) -> None:
        for name, script in tools.items():
            path = self.stubs / name
            path.write_text(script)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def provide(self, *programs: str) -> None:
        """Let the build see these real programs (the bare PATH has Pandoc only)."""
        for program in programs:
            link = self.bare / program
            if not link.exists():
                link.symlink_to(shutil.which(program))

    def run_pdfmd(self, *arguments: str, stubs: bool = True) -> subprocess.CompletedProcess:
        path = os.pathsep.join([str(self.stubs)] * stubs + [str(self.bare), os.path.dirname(sys.executable)])
        environment = {**os.environ, "PATH": path, "STUB_LOG": str(self.log),
                       "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"], "XDG_CACHE_HOME": str(self.cache),
                       "PDFMD_NO_PROMPT": "1"}
        environment.pop("PDFMD_STRICT", None)
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=environment)

    def write(self, text: str, name: str = "doc.md") -> Path:
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def ran(self) -> list[str]:
        calls = []
        for line in self.log.read_text().splitlines():
            program, _, rest = line.partition(" ")
            calls.append((Path(program).name + " " + rest).strip())
        return calls

    def test_html_carries_the_picture_inside_the_file(self):
        self.install(dot=GRAPHVIZ)
        self.write("# D\n\n```dot\ndigraph { a -> b }\n```\n\nAfter.\n")
        done = self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        html = (self.directory / "doc.html").read_text(encoding="utf-8")
        self.assertIn("data:image/svg+xml;base64,", html)
        self.assertNotIn("<pre", html)
        self.assertEqual(self.ran(), ["dot -Tsvg"])
        self.assertNotIn("WARN", done.stdout + done.stderr)

    def test_a_drawing_is_kept_by_its_content(self):
        self.install(dot=GRAPHVIZ)
        self.write("---\ntitle: T\n---\n\n```dot\ndigraph { a -> b }\n```\n\n```{.dot}\ndigraph { a -> b }\n```\n")
        self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html")
        self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html")
        self.assertEqual(self.ran(), ["dot -Tsvg"])                              # twice in one file, twice in two builds
        self.write("```dot\ndigraph { b -> c }\n```\n")
        self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html")
        self.assertEqual(self.ran(), ["dot -Tsvg", "dot -Tsvg"])

    def test_each_output_asks_for_its_own_format(self):
        self.install(dot=GRAPHVIZ, mmdc=MERMAID, d2=D2, **{"rsvg-convert": RSVG})
        self.write("```dot\ndigraph { a -> b }\n```\n\n```mermaid\ngraph LR; A --> B\n```\n\n```d2\nx -> y\n```\n")
        latex = self.run_pdfmd("doc.md", "-t", "latex", "-o", "doc.tex")
        self.assertEqual(latex.returncode, 0, latex.stdout + latex.stderr)
        tex = (self.directory / "doc.tex").read_text(encoding="utf-8")
        self.assertEqual(tex.count(".pdf}"), 3)                                  # PDF pictures for LaTeX
        calls = " ".join(self.ran())
        self.assertIn("dot -Tpdf", calls)
        self.assertIn("-o out.pdf", calls)
        self.assertIn("rsvg-convert -f pdf", calls)                              # D2 draws SVG; the PDF is converted from it
        self.log.write_text("")
        typst = self.run_pdfmd("doc.md", "-t", "typst", "-o", "doc.typ")
        self.assertEqual(typst.returncode, 0, typst.stdout + typst.stderr)
        calls = " ".join(self.ran())
        self.assertIn("dot -Tsvg", calls)
        self.assertIn("-o out.png", calls)                                       # Mermaid's SVG is not drawn by Typst
        self.assertRegex((self.directory / "doc.typ").read_text(encoding="utf-8"), r"image\(\"[^\"]+\.svg\"")

    @unittest.skipUnless(has("rsvg-convert") and (has("lualatex") or has("typst")), "needs rsvg-convert and lualatex or typst")
    def test_a_pdf_that_is_really_typeset_carries_the_drawing(self):
        self.install(dot=REAL_GRAPHVIZ)
        self.provide("rsvg-convert", "lualatex", "typst", "kpsewhich")
        self.write('---\ntitle: T\n---\n\n# D\n\n```{.dot caption="A to B"}\ndigraph { a -> b }\n```\n')
        for engine in [name for name in ("lualatex", "typst") if has(name)]:
            done = self.run_pdfmd("doc.md", "-e", engine, "-o", f"{engine}.pdf")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertRegex(done.stdout, rf"OK    doc\.md  \({engine}\)")
            data = (self.directory / f"{engine}.pdf").read_bytes()
            self.assertTrue(data.startswith(b"%PDF-"))
            try:
                import pypdf
            except ImportError:
                continue
            text = pypdf.PdfReader(str(self.directory / f"{engine}.pdf")).pages[0].extract_text()
            self.assertIn("A to B", text)                                              # the figure and its caption are on the page

    def test_word_gets_png_pictures(self):
        self.install(dot=GRAPHVIZ)
        self.write("# D\n\n```dot\ndigraph { a -> b }\n```\n")
        done = self.run_pdfmd("doc.md", "-t", "docx", "-o", "doc.docx")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with zipfile.ZipFile(self.directory / "doc.docx") as archive:
            self.assertTrue([name for name in archive.namelist() if name.startswith("word/media/")])
        self.assertEqual(self.ran(), ["dot -Tpng -Gdpi=192"])

    def test_flat_markdown_links_svg_and_leaves_mermaid_to_github(self):
        self.install(dot=GRAPHVIZ, mmdc=MERMAID)
        self.write("# D\n\n```dot\ndigraph { a -> b }\n```\n\n```mermaid\ngraph LR; A --> B\n```\n")
        done = self.run_pdfmd("doc.md", "--to", "gfm")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (self.directory / "doc.gfm.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"!\[\]\(doc\.gfm_files/[0-9a-f]{40}\.svg\)")
        self.assertRegex(text, r"(?m)^```\s*mermaid$")
        self.assertEqual(self.ran(), ["dot -Tsvg"])                              # mmdc never ran
        plain = self.run_pdfmd("doc.md", "--to", "txt")
        self.assertEqual(plain.returncode, 0, plain.stdout + plain.stderr)
        self.assertIn("digraph", (self.directory / "doc.txt").read_text(encoding="utf-8"))   # a text file keeps the source

    def test_a_missing_tool_leaves_the_block_with_one_warning(self):
        self.write("# D\n\n```dot\ndigraph { a -> b }\n```\n\n```dot\ndigraph { c -> d }\n```\n")
        done = self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html", stubs=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((done.stdout + done.stderr).count("`dot` is not installed"), 1)
        self.assertIn("brew install graphviz", done.stdout + done.stderr)
        self.assertIn("digraph", (self.directory / "doc.html").read_text(encoding="utf-8"))
        strict = self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html", "--strict", stubs=False)
        self.assertEqual(strict.returncode, 1)

    def test_a_diagram_that_does_not_parse_stays_code(self):
        self.install(dot=FAILING)
        self.write("```dot\ndigraph {\n```\n")
        done = self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html")
        self.assertEqual(done.returncode, 0)
        self.assertIn("a dot diagram could not be drawn", done.stdout + done.stderr)
        self.assertIn("<pre", (self.directory / "doc.html").read_text(encoding="utf-8"))

    def test_no_auto_diagrams(self):
        self.install(dot=GRAPHVIZ)
        self.write("```dot\ndigraph { a -> b }\n```\n")
        done = self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html", "--no-auto", "diagrams")
        self.assertEqual(self.ran(), [])
        self.assertIn("<pre", (self.directory / "doc.html").read_text(encoding="utf-8"))
        self.assertNotIn("WARN", done.stdout + done.stderr)

    def test_a_caption_and_an_id_make_a_figure(self):
        self.install(dot=GRAPHVIZ)
        self.write('---\ntitle: T\n---\n\n```{.dot #fig:flow caption="The *flow* of it" width=50%}\ndigraph { a -> b }\n```\n')
        done = self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        html = (self.directory / "doc.html").read_text(encoding="utf-8")
        self.assertIn('<figure id="fig:flow"', html)
        self.assertIn("The <em>flow</em> of it</figcaption>", html)
        self.assertIn('width:50', html)

    def test_the_graphviz_engine_is_one_of_the_known_ones(self):
        self.install(dot=GRAPHVIZ, neato=GRAPHVIZ)
        self.write('---\ntitle: T\n---\n\n```{.dot engine=neato}\ngraph { a -- b }\n```\n\n```{.dot engine="rm -rf"}\ngraph { c -- d }\n```\n')
        self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html")
        self.assertEqual(sorted(self.ran()), ["dot -Tsvg", "neato -Tsvg"])

    def test_the_doctor_names_the_tools(self):
        self.install(dot=GRAPHVIZ)
        found = self.run_pdfmd("--doctor")
        self.assertIn("diagrams written as code", found.stdout)
        self.assertIn("Graphviz (dot)", found.stdout)
        none = self.run_pdfmd("--doctor", stubs=False)
        self.assertIn("nothing installed", none.stdout)

    def test_a_document_without_diagrams_is_untouched(self):
        self.install(dot=GRAPHVIZ)
        self.write("# D\n\n```python\nprint('dot')\n```\n\nA dot here.\n")
        self.run_pdfmd("doc.md", "-t", "html", "-o", "doc.html")
        self.assertEqual(self.ran(), [])

    @needs_pandoc(3, 1, 3)
    def test_a_real_graphviz_draws_when_there_is_one(self):
        dot = next((path for path in os.environ.get("PATH", "").split(os.pathsep)
                    if (Path(path) / "dot").is_file()), None)
        if dot is None or not has("dot"):
            self.skipTest("Graphviz is not installed")
        self.write("```dot\ndigraph { a -> b }\n```\n")
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CACHE_HOME": str(self.cache), "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-t", "html", "-o", "doc.html"],
                              capture_output=True, text=True, cwd=self.directory, env=environment)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("data:image/svg+xml;base64,", (self.directory / "doc.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
