"""Native bibliography PDF builds include definitions for the markup filter's LaTeX."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(all(shutil.which(x) for x in ("pandoc", "pdflatex", "pdftotext")), "needs Pandoc, pdfLaTeX and pdftotext")
class NativeBibliographyMarkup(unittest.TestCase):
    def test_natbib_and_biblatex_define_callouts_and_highlights(self):
        for engine, tool in (("natbib", "bibtex"), ("biblatex", "biber")):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as scratch:
                if not shutil.which(tool):
                    self.skipTest(f"needs {tool}")
                folder = Path(scratch)
                (folder / "references.bib").write_text(
                    "@book{r, author={Example, A.}, title={Example Study}, year={2020}}\n", encoding="utf-8")
                (folder / "paper.md").write_text(
                    "---\nbibliography: references.bib\npdfmd-options:\n"
                    f"  citation-engine: {engine}\n  markup: [callouts, highlight]\n---\n\n"
                    "Citing [@r].\n\n> [!NOTE]\n> Callout content.\n\n==Highlighted words==.\n", encoding="utf-8")
                env = {**os.environ, "XDG_CONFIG_HOME": str(folder / "config"),
                       "XDG_CACHE_HOME": str(folder / "cache"), "XDG_DATA_HOME": str(folder / "data"),
                       "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "paper.md",
                                       "-e", "pdflatex", "--engine-fallback", "missing", "--no-cache", "--keep-aux",
                                       "--no-stamp", "--no-backup"], cwd=folder, env=env,
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                [tex] = folder.glob("paper-pdfmd-nativebib-*.tex")
                source = tex.read_text(encoding="utf-8")
                self.assertIn(r"\newtcolorbox{pdfmdcallout}", source)
                self.assertIn(r"\newcommand{\pdfmdhl}", source)
                text = subprocess.run(["pdftotext", str(folder / "paper.pdf"), "-"],
                                      capture_output=True, text=True, check=True).stdout
                for expected in ("Callout content.", "Highlighted words", "Example Study"):
                    self.assertIn(expected, text)
