"""The LaTeX packages a document's commands need (v3.27.16, auto kind `texpackages`): `\\ce` without mhchem and `\\SI`
without siunitx used to stop every LaTeX engine."""

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

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

CHEMISTRY = "---\ntitle: C\n---\n\nWater is $\\ce{H2O}$, at $\\SI{25}{\\celsius}$.\n"


def has_latex_package(name: str) -> bool:
    if not (shutil.which("lualatex") and shutil.which("kpsewhich") and shutil.which("pdftotext")):
        return False
    found = subprocess.run(["kpsewhich", f"{name}.sty"], capture_output=True, text=True)
    return found.returncode == 0 and bool(found.stdout.strip())


class Arguments(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-texpackages-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def source(self, text: str) -> Path:
        path = self.directory / "doc.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_nothing_without_the_commands(self):
        self.assertEqual(pdfmd.tex_package_args(self.source("Plain $x^2$.\n"), None, [], []), [])

    def test_a_filter_when_there_is_no_header_file_and_a_header_file_when_there_is(self):
        source = self.source(CHEMISTRY)
        quiet = pdfmd.tex_package_args(source, None, ["pandoc", "doc.md"], [])
        self.assertEqual(quiet[0], "-M")
        self.assertTrue(quiet[-1].endswith("header.lua"))
        header = Path(quiet[1].partition("=")[2]).read_text(encoding="utf-8")
        self.assertIn("\\@ifpackageloaded{mhchem}{}{\\ifdefined\\ce\\else\\IfFileExists{mhchem.sty}", header)
        self.assertIn("\\usepackage{siunitx}", header)
        loud = pdfmd.tex_package_args(source, None, ["pandoc", "--include-in-header", "x.tex"], [])
        self.assertEqual(loud[0], "--include-in-header")
        self.assertEqual(pdfmd.tex_package_args(source, None, ["pandoc"], ["-H", "mine.tex"])[0], "--include-in-header")

    def test_no_auto(self):
        self.assertEqual(pdfmd.tex_package_args(self.source(CHEMISTRY), ["texpackages"], [], []), [])


@unittest.skipUnless(shutil.which("pandoc") and has_latex_package("mhchem") and has_latex_package("siunitx"),
                     "needs Pandoc, lualatex with mhchem and siunitx, and pdftotext")
class Building(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-texpackages-build-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, text: str, *arguments: str, files: dict | None = None) -> tuple[subprocess.CompletedProcess, str]:
        (self.directory / "doc.md").write_text(text, encoding="utf-8")
        for name, content in (files or {}).items():
            (self.directory / name).write_text(content, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "lualatex", *arguments],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})
        text_out = ""
        if (self.directory / "doc.pdf").is_file():
            text_out = subprocess.run(["pdftotext", str(self.directory / "doc.pdf"), "-"], capture_output=True,
                                      text=True).stdout
        return done, text_out

    def test_chemistry_and_units_build_without_a_preamble(self):
        done, text = self.build(CHEMISTRY)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("H2 O", text)
        self.assertIn("25", text)

    def test_a_metadata_files_own_load_wins_and_stays(self):
        # the metadata file loads mhchem with its own options and defines a macro: both must survive
        meta = "header-includes:\n  - \\usepackage[version=3]{mhchem}\n  - \\newcommand{\\housemark}{HOUSE-MARK}\n"
        done, text = self.build(CHEMISTRY + "\nSigned \\housemark.\n", "-y", "meta.yaml", files={"meta.yaml": meta})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("HOUSE-MARK", text)

    def test_a_preamble_that_loads_it_already(self):
        done, _ = self.build(CHEMISTRY, files={"preamble.tex": "\\usepackage[version=3]{mhchem}\n"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_command_of_the_documents_own(self):
        text = "---\ntitle: C\nheader-includes:\n  - \\newcommand{\\ce}[1]{OWN-#1}\n---\n\nWater is \\ce{H2O}.\n"
        done, out = self.build(text)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("OWN-H2O", out)


if __name__ == "__main__":
    unittest.main()
