"""A Typst source is read as Typst: by its `.typ` or `.typst` name, and without the Markdown-only helpers."""

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

import pdfmd  # noqa: E402


def pandoc_reads_typst() -> bool:
    if not shutil.which("pandoc"):
        return False
    done = subprocess.run(["pandoc", "--list-input-formats"], capture_output=True, text=True)
    return "typst" in done.stdout.split()


SOURCE = "= Heading One\n\nSome *strong* text.\n\nSee @h1 and email a@b.com.\n"


class Readers(unittest.TestCase):
    def test_a_typst_name_picks_the_typst_reader(self):
        self.assertEqual(pdfmd.resolve_from_format(Path("a.typ"), None), ("typst", None))
        reader, reason = pdfmd.resolve_from_format(Path("a.typst"), None)
        self.assertEqual(reader, "typst")
        self.assertIn("does not know the .typst extension", reason)
        self.assertEqual(pdfmd.resolve_from_format(Path("a.typ"), "rst"), ("rst", None))

    def test_the_markdown_only_helpers_leave_it_alone(self):
        with tempfile.TemporaryDirectory() as folder:
            typst, markdown = Path(folder) / "a.typ", Path(folder) / "a.md"
            typst.write_text(SOURCE, encoding="utf-8")
            markdown.write_text(SOURCE, encoding="utf-8")
            self.assertFalse(pdfmd.contains_citations(typst))
            self.assertTrue(pdfmd.contains_citations(markdown))
            typst.write_text("= T {#fig:x}\n@fig:x\n", encoding="utf-8")
            self.assertFalse(pdfmd.contains_crossref(typst))
            typst.write_text("# Looks like a Markdown title\n\ntext\n", encoding="utf-8")
            with pdfmd.prepared_title_source(typst) as (source, shifted):
                self.assertEqual((source, shifted), (typst, False))


@unittest.skipUnless(pandoc_reads_typst(), "needs a Pandoc with the Typst reader")
class Builds(unittest.TestCase):
    def build(self, name, *arguments):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / name).write_text(SOURCE, encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, "-v", *arguments], cwd=folder,
                                  capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": ""})
            outputs = {item.name: item.read_text(encoding="utf-8", errors="replace")
                       for item in Path(folder).iterdir() if item.suffix in (".tex", ".md", ".html")}
            return done, outputs

    def test_both_extensions_build_as_typst_without_citeproc(self):
        for name in ("a.typ", "a.typst"):
            with self.subTest(name=name):
                done, outputs = self.build(name, "--to", "latex")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn("-f typst", done.stdout + done.stderr)
                self.assertNotIn("--citeproc", done.stdout + done.stderr)
                self.assertIn("Heading One", outputs["a.tex"])
                self.assertNotIn("= Heading One", outputs["a.tex"])

    def test_to_md_is_markdown(self):
        done, outputs = self.build("a.typ", "--to", "md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Heading One", outputs["a.md"])


if __name__ == "__main__":
    unittest.main()
