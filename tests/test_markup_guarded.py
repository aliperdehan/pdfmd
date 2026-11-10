"""v3.33.67: the markup header keeps what LaTeX before it defined. pdfmd's `landscape` markup loaded pdflscape after a kit's
package, and lscape's `\\def` replaced the kit's own `landscape` environment (a wider sheet) by a turned portrait page; its
`highlight` markup loaded lua-ul with `[soul]` after a preamble's soul or bare lua-ul, which stopped LuaLaTeX. After a kit, a
header file of the user's, an own template or a non-standard class the header is the guarded one (pdfmd_tex.markup); a document
with nothing before it gets the header as before, byte for byte. The builds go through pdfmd itself with a fixture kit whose
package defines `landscape`."""

from __future__ import annotations

import os
import re
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
sys.path.insert(0, str(ROOT / "lib"))

import pdfmd  # noqa: E402

markup = pdfmd.load_package("pdfmd_tex.markup")      # bound to pdfmd as its `core`, as the stand-in does

PANDOC = shutil.which("pandoc")
LUALATEX = shutil.which("lualatex")

# a package that defines `landscape` itself, as a house style may: a wider sheet, never a turned one
OWN_LANDSCAPE = r"""\ProvidesPackage{ownland}[2026/11/10 v1.0.0 test]
\newenvironment{landscape}{\clearpage\pagewidth=297mm \pageheight=210mm}{\clearpage\pagewidth=210mm \pageheight=297mm}
"""
DOCUMENT = "---\ntitle: T\npapersize: a4\n{options}\n---\n\nPortrait.\n\n::: landscape\nWide.\n:::\n\nBack.\n"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def page_two(pdf: Path) -> tuple[float, float, int]:
    """The width, height and /Rotate of the PDF's second page."""
    from pypdf import PdfReader
    page = PdfReader(str(pdf)).pages[1]
    box = page.mediabox
    return float(box.width), float(box.height), int(page.get("/Rotate", 0) or 0)


class Pieces(unittest.TestCase):
    def test_nothing_before_gives_the_old_header(self):
        with tempfile.TemporaryDirectory() as folder:
            document = write(Path(folder) / "a.md", "Text.\n")
            pieces = markup.markup_header_pieces(document, [], ["highlight", "landscape"], ["pandoc", str(document), "-s"])
        self.assertEqual(pieces, [pdfmd.MARKUP_HIGHLIGHT_HEADER, pdfmd.MARKUP_LANDSCAPE_HEADER])

    def test_a_header_file_of_the_users_a_template_or_a_class_gives_the_guarded_one(self):
        with tempfile.TemporaryDirectory() as folder:
            document = write(Path(folder) / "a.md", "Text.\n")
            preamble = write(Path(folder) / "preamble.tex", "\\usepackage{soul}\n")
            for before in (["--include-in-header", str(preamble)], [f"--include-in-header={preamble}"], ["-H", str(preamble)],
                           ["--template", "mine.latex"], ["-V", "documentclass=apa7"], ["-M", "documentclass=revtex4-2"]):
                pieces = markup.markup_header_pieces(document, [], ["landscape"], ["pandoc", *before])
                self.assertEqual(pieces, [markup.LANDSCAPE_GUARDED], before)
            for before in (["-V", "documentclass=report"], ["-V", "geometry:margin=1in"]):
                self.assertEqual(markup.markup_header_pieces(document, [], ["landscape"], before), [pdfmd.MARKUP_LANDSCAPE_HEADER])
            classed = write(Path(folder) / "b.md", "---\ndocumentclass: elsarticle\n---\nText.\n")
            self.assertEqual(markup.markup_header_pieces(classed, [], ["landscape"], []), [markup.LANDSCAPE_GUARDED])

    def test_a_header_of_pdfmds_own_is_not_somebody_elses(self):
        with tempfile.TemporaryDirectory() as folder:
            document = write(Path(folder) / "a.md", "Text.\n")
            own = pdfmd.cache_root() / "tex" / "packages-x.tex"
            self.assertEqual(markup.markup_header_pieces(document, [], ["landscape"], ["--include-in-header", str(own)]),
                             [pdfmd.MARKUP_LANDSCAPE_HEADER])

    def test_the_guard_keeps_an_environment_with_its_end(self):
        self.assertIn(r"\ifdefined\landscape\ifdefined\endlandscape", markup.LANDSCAPE_GUARDED)
        self.assertIn(r"\@ifpackageloaded{lua-ul}{}", markup.HIGHLIGHT_GUARDED)


@unittest.skipUnless(PANDOC, "Pandoc is needed")
class Builds(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.kits = self.root / "course" / "kits"
        self.config = write(self.root / "cfg" / "config.yaml", f"kits: [{self.kits}]\n")
        self.folder = self.root / "course" / "LR1"
        write(self.kits / "ownland" / ".kit", "kit-format: 1\nname: ownland\npackage: ownland\n")
        write(self.kits / "ownland" / "ownland.sty", OWN_LANDSCAPE)

    def build(self, options: str, output: str, *args) -> tuple[subprocess.CompletedProcess, Path]:
        write(self.folder / "report.md", DOCUMENT.format(options=options))
        environment = {**os.environ, "PDFMD_CONFIG": str(self.config), "XDG_CACHE_HOME": str(self.root / "cache"),
                       "PDFMD_NO_PROMPT": "1", "PDFMD_BUILD_LOG": "off"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report.md", "-o", output, "--no-backup", "--no-stamp",
                               *args], capture_output=True, text=True, cwd=self.folder, env=environment,
                              stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        return done, self.folder / output

    def test_a_kit_gets_the_guarded_header_and_a_plain_document_the_old_one(self):
        _, out = self.build("pdfmd-options: {kit: ownland}", "out.tex", "--to", "latex")
        tex = out.read_text(encoding="utf-8")
        self.assertLess(tex.index(r"\usepackage{ownland}"), tex.index(markup.LANDSCAPE_GUARDED))
        _, out = self.build("", "out.tex", "--to", "latex")
        tex = out.read_text(encoding="utf-8")
        self.assertIn(pdfmd.MARKUP_LANDSCAPE_HEADER, tex)
        self.assertNotIn("pdfmdownlandscape", tex)

    def test_a_preamble_gets_the_guarded_header(self):
        write(self.folder / "preamble.tex", "\\usepackage{soul}\n")
        _, out = self.build("", "out.tex", "--to", "latex")
        tex = out.read_text(encoding="utf-8")
        self.assertIn(markup.HIGHLIGHT_GUARDED, tex)
        self.assertIn(markup.LANDSCAPE_GUARDED, tex)

    @unittest.skipUnless(LUALATEX, "LuaLaTeX is needed")
    def test_the_kits_landscape_page_is_kept(self):
        _, pdf = self.build("pdfmd-options: {kit: ownland}", "out.pdf", "-e", "lualatex")
        width, height, rotate = page_two(pdf)
        self.assertGreater(width, height)            # the kit's wider sheet (pdflscape's: a portrait page turned by /Rotate 90)
        self.assertEqual(rotate, 0)
        _, pdf = self.build("", "plain.pdf", "-e", "lualatex")
        width, height, rotate = page_two(pdf)
        self.assertLess(width, height)               # a plain document: pdflscape's page, as before
        self.assertEqual(rotate, 90)

    @unittest.skipUnless(LUALATEX, "LuaLaTeX is needed")
    def test_lualatex_builds_after_a_preambles_soul(self):
        write(self.folder / "preamble.tex", "\\usepackage{soul}\n")
        done, _ = self.build("", "soul.pdf", "-e", "lualatex")
        self.assertTrue(re.search(r"\(lualatex\)", done.stdout + done.stderr), done.stdout + done.stderr)
        self.assertNotIn("lualatex failed", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
