"""v3.28.24: a document in pdfmd's own main font gets the math font that goes with it (-V mathfont=STIX Two Math),
unless the document, a metadata file or -f names a font, or --no-auto mathfont / font says no."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

INSTALLED = {"stix two math", "dejavu math tex gyre", "newcomputermodern math"}


def missing(family: str) -> bool:
    return family.casefold() not in INSTALLED


class Rule(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.doc = self.root / "d.md"
        self.doc.write_text("---\ntitle: T\n---\n\n$x^2$\n", encoding="utf-8")
        patch = unittest.mock.patch.object(pdfmd, "system_font_missing", missing)
        patch.start()
        self.addCleanup(patch.stop)

    def args(self, font="STIX Two Text", variables=(), cli=None, no_auto=None, engine="lualatex", metadata=()):
        return pdfmd.mathfont_args(font, self.doc, list(metadata), list(variables), cli, no_auto, engine)

    def test_the_companions(self):
        self.assertEqual(self.args(), ["-V", "mathfont=STIX Two Math"])
        self.assertEqual(self.args("DejaVu Serif"), ["-V", "mathfont=DejaVu Math TeX Gyre"])
        self.assertEqual(self.args("New Computer Modern"), ["-V", "mathfont=NewComputerModern Math"])   # as fontconfig names it
        self.assertEqual(self.args("Libertinus Serif"), [])          # its math font is not installed
        self.assertEqual(self.args("Georgia"), [])                   # not in the table
        self.assertEqual(self.args(None), [])

    def test_engines(self):
        for engine in ("lualatex", "xelatex", "tectonic", None):
            self.assertEqual(self.args(engine=engine), ["-V", "mathfont=STIX Two Math"], engine)
        for engine in ("pdflatex", "latexmk", "weasyprint"):
            self.assertEqual(self.args(engine=engine), [], engine)
        with unittest.mock.patch.object(pdfmd, "template_has_variable", return_value=False):
            self.assertEqual(self.args(engine="typst"), [])          # Pandoc 3.1.3's Typst template
        with unittest.mock.patch.object(pdfmd, "template_has_variable", return_value=True):
            self.assertEqual(self.args(engine="typst"), ["-V", "mathfont=STIX Two Math"])

    def test_a_font_the_user_named_is_left_alone(self):
        self.assertEqual(self.args(cli="Georgia"), [])
        self.assertEqual(self.args(variables=["mainfont=Georgia"]), [])
        self.assertEqual(self.args(variables=["mathfont=Cambria Math"]), [])
        self.doc.write_text("---\ntitle: T\nmathfont: Cambria Math\n---\n\n$x$\n", encoding="utf-8")
        self.assertEqual(self.args(), [])
        self.doc.write_text("---\ntitle: T\nmainfont: Georgia\n---\n\n$x$\n", encoding="utf-8")
        self.assertEqual(self.args(), [])
        self.doc.write_text("---\ntitle: T\n---\n\n$x$\n", encoding="utf-8")
        metadata = self.root / "metadata.yaml"
        metadata.write_text("mainfont: Georgia\n", encoding="utf-8")
        self.assertEqual(self.args(metadata=[metadata]), [])

    def test_the_switches(self):
        self.assertEqual(self.args(no_auto=["mathfont"]), [])
        self.assertEqual(self.args(no_auto=["font"]), [])
        self.assertEqual(self.args(no_auto=["margin"]), ["-V", "mathfont=STIX Two Math"])
        self.assertEqual(self.args(no_auto=[]), [])                  # a bare --no-auto switches everything off

    def test_it_is_announced_as_a_default(self):
        log = pdfmd.AutoLog()
        log.record("MATHFONT", "d.md: no mathfont set; using STIX Two Math to go with STIX Two Text", False)
        import io
        from contextlib import redirect_stdout
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            log.flush()
        self.assertEqual(buffer.getvalue().strip(), "DEFAULTS  math in STIX Two Math")


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("fc-list")
                     and "stix two math" in (pdfmd.installed_font_families() or ()), "needs Pandoc and STIX Two Math")
class Output(unittest.TestCase):
    def test_the_latex_file_sets_the_math_font(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "d.md").write_text("---\ntitle: T\n---\n\n$x^2$\n", encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}

            def latex(*args):
                done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "latex", "-o", "o.tex", *args],
                                      cwd=root, env=env, capture_output=True, text=True, timeout=120)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                return (root / "o.tex").read_text(encoding="utf-8")
            self.assertRegex(latex(), r"\\setmathfont[^\n]*\{STIX Two Math\}")
            self.assertNotIn("STIX Two Math", latex("--no-auto", "mathfont"))
            self.assertNotIn("STIX Two Math", latex("-f", "Georgia"))


if __name__ == "__main__":
    unittest.main()
