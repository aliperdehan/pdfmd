"""The space between paragraphs (v3.33.58): `pdfmd-options: {paragraph-spacing: 6pt}` and `--paragraph-spacing`, for LaTeX
(`\\setlength{\\parskip}`) and Typst (typst.lua's `#set par(spacing: ...)`; its rules are tested in test_engine_filters)."""

from __future__ import annotations

import os
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
from cache_support import cache_env  # noqa: E402

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
import pdfmd_paragraph  # noqa: E402

PANDOC = shutil.which("pandoc")


class Values(unittest.TestCase):
    def test_what_is_taken(self):
        normalise = pdfmd_paragraph.normalise
        for value, expected in (("6pt", "6pt"), ("1em", "1em"), ("2.5mm", "2.5mm"), (".5cm", ".5cm"), ("1in", "1in"),
                                (" 6 PT ", "6pt"), (0, "0pt"), ("0", "0pt"), (0.0, "0pt"), ("0em", "0pt"),
                                ("auto", None), ("", None), (None, None)):
            self.assertEqual(normalise(value), expected, value)
        for value in ("6", 6, "-3pt", "6px", "1ex", "10%", True, False, "big", "6pt 2pt"):
            with self.assertRaises(ValueError, msg=value):
                normalise(value)

    def test_a_bad_value_names_the_setting_and_the_form(self):
        with self.assertRaises(SystemExit) as caught:
            pdfmd_paragraph.command_line_value("6px")
        self.assertIn("--paragraph-spacing must be a length such as 6pt or 1em (pt, mm, cm, in, em), 0, or auto",
                      str(caught.exception))
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "doc.md"
            document.write_text("---\npdfmd-options:\n  paragraph-spacing: 6\n---\n\nx\n", encoding="utf-8")
            with mock.patch.dict(os.environ), self.assertRaises(SystemExit) as caught:
                os.environ.pop(pdfmd_paragraph.ENV, None)
                pdfmd_paragraph.paragraph_spacing(document, [])
        self.assertIn("pdfmd-options.paragraph-spacing must be a length", str(caught.exception))


class Arguments(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-parskip-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(pdfmd_paragraph.ENV, None)
        cache = mock.patch.object(pdfmd, "cache_root", return_value=self.directory / "cache")
        cache.start()
        self.addCleanup(cache.stop)

    def document(self, front: str) -> Path:
        path = self.directory / "doc.md"
        path.write_text(f"---\ntitle: T\n{front}---\n\nx\n", encoding="utf-8")
        return path

    def test_latex_gets_a_header_file_only_when_set(self):
        self.assertEqual(pdfmd.paragraph_spacing_latex_args(self.document(""), []), [])
        self.assertEqual(pdfmd.paragraph_spacing_latex_args(self.document("pdfmd-options:\n  paragraph-spacing: auto\n"), []), [])
        args = pdfmd.paragraph_spacing_latex_args([self.document("pdfmd-options:\n  paragraph-spacing: 0\n")], [])
        self.assertEqual(args[0], "--include-in-header")
        self.assertIn("\\setlength{\\parskip}{0pt}\n", Path(args[1]).read_text(encoding="utf-8"))

    def test_the_command_line_wins_and_auto_undoes_the_document(self):
        document = self.document("pdfmd-options:\n  paragraph-spacing: 1em\n")
        os.environ[pdfmd_paragraph.ENV] = "6pt"
        self.assertEqual(pdfmd_paragraph.paragraph_spacing(document, []), "6pt")
        os.environ[pdfmd_paragraph.ENV] = "auto"
        self.assertIsNone(pdfmd_paragraph.paragraph_spacing(document, []))
        self.assertEqual(pdfmd.paragraph_spacing_latex_args(document, []), [])

    def test_typst_gets_the_value_and_an_old_typst_is_told(self):
        typst_args = pdfmd.paragraph_spacing_typst_args
        with mock.patch.object(pdfmd, "typst_version", return_value=(0, 15, 1)):
            self.assertEqual(typst_args(self.document(""), [], "typst"), [])
            self.assertEqual(typst_args(self.document("indent: true\n"), [], "typst"), [])
            spaced = self.document("pdfmd-options:\n  paragraph-spacing: 6pt\n")
            self.assertEqual(typst_args(spaced, [], "typst"), ["-M", "pdfmd-paragraph-spacing=6pt"])
            self.assertEqual(typst_args(spaced, [], "lualatex"), [])
        with mock.patch.object(pdfmd, "typst_version", return_value=(0, 11, 1)):
            self.assertEqual(typst_args(self.document("indent: true\n"), [], "typst"), ["-M", "pdfmd-typst-block-spacing=true"])
            self.assertEqual(typst_args(self.document(""), [], "typst"), [])
        with mock.patch.object(pdfmd, "typst_version", return_value=(0,)):          # none found: a current one
            self.assertEqual(typst_args(self.document("indent: true\n"), [], "typst"), [])


@unittest.skipUnless(PANDOC, "needs Pandoc")
class ThroughPdfmd(unittest.TestCase):
    def run_pdfmd(self, root: Path, *args: str) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PDFMD_CONFIG": "", **cache_env(root / "cache"), "XDG_CONFIG_HOME": str(root / "config"),
                       "APPDATA": str(root / "config"), "PDFMD_NO_PROMPT": "1"}
        environment.pop(pdfmd_paragraph.ENV, None)
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=root, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env=environment)

    def test_latex_and_typst_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "doc.md").write_text("---\ntitle: T\npdfmd-options:\n  paragraph-spacing: 6pt\n---\n\nOne.\n\nTwo.\n",
                                         encoding="utf-8")
            done = self.run_pdfmd(root, "doc.md", "-t", "latex", "-s", "-o", "doc.tex")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            tex = (root / "doc.tex").read_text(encoding="utf-8")
            self.assertIn("\\setlength{\\parskip}{6pt}", tex)
            self.assertLess(tex.index("\\usepackage{parskip}"), tex.index("\\setlength{\\parskip}{6pt}"))    # after the template's
            done = self.run_pdfmd(root, "doc.md", "-t", "typst", "-s", "-o", "doc.typ", "--paragraph-spacing", "1em")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("#set par(spacing: 0.65em + 1em)", (root / "doc.typ").read_text(encoding="utf-8"))
            done = self.run_pdfmd(root, "doc.md", "-t", "latex", "-s", "-o", "doc.tex", "--paragraph-spacing", "6px")
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("--paragraph-spacing must be", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
