"""A LaTeX error is placed in the Markdown the author wrote (v3.26.14)."""

from __future__ import annotations

import os
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
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402

SOURCE = """---
title: T
---

# One

First paragraph.

The second paragraph runs over
two lines and has \\badmacro here.

## Two

Tail.
"""


class Location(unittest.TestCase):
    def test_the_words_are_found_across_a_rewrapped_line(self):
        self.assertEqual(pdfmd.source_line_for(SOURCE, "First paragraph."), 7)
        self.assertEqual(pdfmd.source_line_for(SOURCE, "two lines and has \\badmacro"), 10)
        self.assertEqual(pdfmd.source_line_for(SOURCE, "over two lines and has \\badmacro"), 9)     # LaTeX joined the lines
        self.assertEqual(pdfmd.source_line_for(SOURCE, "text the source never had \\badmacro"), 10)   # the command alone
        self.assertIsNone(pdfmd.source_line_for(SOURCE, "\\x"))

    def test_the_message_names_the_file_and_the_line(self):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "doc.md"
            document.write_text(SOURCE, encoding="utf-8")
            stderr = "Error producing PDF.\n! Undefined control sequence.\nl.67 two lines and has \\badmacro\n"
            where = pdfmd.latex_error_location(str(document), stderr)
            self.assertIn("near line 10 of", where)
            self.assertTrue(where.endswith("two lines and has \\badmacro"))
            self.assertIsNone(pdfmd.latex_error_location("REPORT", stderr))
            self.assertIsNone(pdfmd.latex_error_location(str(document), "no context here"))

    def test_the_complete_context_wins_over_a_command_shared_by_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = (Path(directory) / name for name in ("01.md", "02.md"))
            first.write_text("First \\badmacro\n", encoding="utf-8")
            second.write_text("Second \\badmacro\n", encoding="utf-8")
            sources = [first, second]
            self.assertIn("02.md: Second", pdfmd.latex_error_location(
                "REPORT", "l.91 Second \\badmacro\n", sources=sources))
            self.assertIsNone(pdfmd.latex_error_location("REPORT", "l.91 \\badmacro\n", sources=sources))


HAS_LATEX = any(shutil.which(name) for name in ("xelatex", "lualatex", "pdflatex"))


@needs_pandoc(3, 1, 3)
@unittest.skipUnless(HAS_LATEX, "needs a LaTeX engine")
class CommandLine(unittest.TestCase):
    def test_a_failing_build_says_where(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "doc.md").write_text(SOURCE, encoding="utf-8")
            engine = next(name for name in ("xelatex", "lualatex", "pdflatex") if shutil.which(name))
            env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": directory, "APPDATA": directory}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", engine], cwd=directory,
                                  capture_output=True, text=True, encoding="utf-8", env=env)
            self.assertEqual(done.returncode, 1)
            self.assertRegex(done.stderr, r"near line (9|10) of doc\.md")      # the paragraph that holds the macro

    def test_scaffold_and_reports_name_the_original_part(self):
        engine = next(name for name in ("pdflatex", "xelatex", "lualatex") if shutil.which(name))
        for route in ("scaffold", "cached scaffold", "report", "patch report"):
            with self.subTest(route=route), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                parts = folder / "parts"
                parts.mkdir()
                options = "parts: auto, stamp: {pdf-metadata: false}"
                if route == "patch report":
                    options += ", report-build: patch"
                (folder / "01-paper.md").write_text(
                    f"---\ntitle: Paper\npdfmd-options: {{{options}}}\n---\n\nIntroduction.\n",
                    encoding="utf-8")
                (parts / "02-section.md").write_text(
                    "---\ntitle: Part\n---\n\n# Findings\n\n```{=latex}\n\\pdfmdUndefinedFixture\n```\n",
                    encoding="utf-8")
                args = ["01-paper.md"] if route.endswith("scaffold") else [
                    "-r", "01-paper.md", str(Path("parts") / "02-section.md")]
                if route == "cached scaffold":
                    args += ["--cache"]
                done = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "pdfmd"), *args, "-e", engine,
                     "--no-auto", "mainfont", "unicode", "texpackages"],
                    cwd=folder, env={**os.environ, "PYTHONUTF8": "1"}, stdin=subprocess.DEVNULL,
                    capture_output=True, encoding="utf-8", timeout=90)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn(f"near line 8 of {Path('parts') / '02-section.md'}", done.stderr)


if __name__ == "__main__":
    unittest.main()
