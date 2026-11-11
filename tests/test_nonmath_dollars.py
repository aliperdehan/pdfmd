"""A `$...$` that is not math because the closing `$` is followed by a digit (v3.32.48)."""

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

FRONT = "---\ntitle: T\n---\n\n"
BODY = (
    "a $\\geq$3 batches\n\n"                       # 5 (with the front matter)
    "b $\\geq 3$ batches\n\n"                      # real math
    "c within $\\pm$10 mV\n\n"                     # 9
    "d costs $5 and $10, or $5/$10; `$\\geq$3`; \\$\\geq\\$3; $x$ is fine\n\n"      # prices, code, escaped dollars
    "| col |\n|-----|\n| $\\geq$3 batches |\n\n"   # 15, a table cell
    "```\n$\\geq$3 in code\n```\n"
)


@needs_pandoc(3, 1, 3)
class FindingThem(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-nonmath-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def document(self, text: str, name: str = "d.md") -> Path:
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_pandocs_markdown_reader(self):
        path = self.document(FRONT + BODY)
        found = pdfmd.nonmath_dollars(path, None)
        self.assertEqual([(line, written) for line, written, _ in found],
                         [(5, "$\\geq$3"), (9, "$\\pm$10"), (15, "$\\geq$3")])
        self.assertEqual(found[0][2], "$\\geq 3$")
        self.assertEqual(found[1][2], "$\\pm 10$")

    def test_the_gfm_reader_keeps_the_whole_thing_as_one_word(self):
        """Where it does: the gfm reader of an older Pandoc (3.1.3) has no digit rule and reads `$\\geq$3` as math, so there is nothing
        to say there, although the escaped copy in the document (`\\$\\geq\\$3`) is the same text in what the reader gives."""
        import subprocess
        read = subprocess.run(["pandoc", "-f", "gfm+smart", "-t", "native"], input="a $\\geq$3 b\n", capture_output=True, text=True,
                              encoding="utf-8", check=True).stdout
        path = self.document(BODY)
        self.assertEqual([line for line, _, _ in pdfmd.nonmath_dollars(path, "gfm+smart")], [] if "Math" in read else [1, 5, 11])

    def test_an_escaped_copy_is_not_taken_for_the_unescaped_one(self):
        """The reader gives `\\$\\geq\\$3` as the text `$\\geq$3`. With no failed span beside it in what the reader gave, the unescaped
        copy was read as math (no Pandoc needed: the reader's answer is given)."""
        import json
        from unittest import mock
        path = self.document("a $\\geq$3 b\n\nwritten \\$\\geq\\$3 here\n")

        def answer(*inlines):
            done = mock.Mock(returncode=0)
            done.stdout = json.dumps({"pandoc-api-version": [1, 23], "meta": {}, "blocks": [{"t": "Para", "c": list(inlines)}]})
            return done
        text, math = {"t": "Str", "c": "$\\geq$3"}, {"t": "Math", "c": [{"t": "InlineMath"}, "\\geq"]}
        with mock.patch.object(pdfmd, "which", return_value="pandoc"), mock.patch.object(pdfmd.subprocess, "run") as run:
            run.return_value = answer(math, {"t": "Str", "c": "3"}, {"t": "Space"}, text)        # the unescaped one is math
            self.assertEqual(pdfmd.nonmath_dollars(path, "gfm"), [])
            pdfmd._NONMATH_DOLLARS.clear()
            run.return_value = answer(text, {"t": "Space"}, text)                                # both are text
            self.assertEqual([line for line, _, _ in pdfmd.nonmath_dollars(path, "gfm")], [1])

    def test_a_reader_without_dollar_math_has_nothing_to_say(self):
        path = self.document(FRONT + BODY)
        self.assertEqual(pdfmd.nonmath_dollars(path, "commonmark"), [])
        self.assertEqual(pdfmd.nonmath_dollars(path, "markdown-tex_math_dollars"), [])

    def test_a_soft_break_inside_the_span_still_gets_its_line(self):
        path = self.document(FRONT + "Some words $\\alpha\n+\\beta$2 end\n")
        self.assertEqual([line for line, _, _ in pdfmd.nonmath_dollars(path, None)], [5])

    def test_no_candidate_no_pandoc_pass(self):
        from unittest import mock
        for text in ("Plain text, $x^2$ and $5 and $10 and `$\\geq$3`.\n", "A $\\geq 3$ b.\n"):
            path = self.document(FRONT + text)
            with mock.patch.object(pdfmd.subprocess, "run", side_effect=AssertionError("Pandoc was asked")):
                self.assertEqual(pdfmd.nonmath_dollars(path, None), [])
        path = self.document(FRONT + "a $\\geq$3 b\n")                  # a candidate: Pandoc is asked, and agrees
        self.assertEqual([line for line, _, _ in pdfmd.nonmath_dollars(path, None)], [5])

    def test_prices_alone_say_nothing(self):
        path = self.document(FRONT + "It costs $5 and $10, or $5-$10, or C$3 and US$4.\n")
        self.assertEqual(pdfmd.nonmath_dollars(path, None), [])


@needs_pandoc(3, 1, 3)
class InABuild(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-nonmath-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        (self.directory / "d.md").write_text(FRONT + BODY, encoding="utf-8")

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"], "PDFMD_NO_PROMPT": "1"}
        environment.pop("PDFMD_STRICT", None)
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=environment)

    def test_the_build_warns_with_file_and_line_and_strict_fails_it(self):
        done = self.run_pdfmd("d.md", "-t", "html")
        output = done.stdout + done.stderr
        self.assertEqual(done.returncode, 0, output)
        self.assertIn("WARN  d.md:5: `$\\geq$3` is not math (Pandoc needs the closing $ not followed by a digit); "
                      "write $\\geq 3$", output)
        self.assertIn("d.md:9:", output)
        self.assertIn("d.md:15:", output)
        self.assertNotIn("d.md:7:", output)
        strict = self.run_pdfmd("d.md", "-t", "html", "--strict")
        self.assertEqual(strict.returncode, 1)
        self.assertTrue((self.directory / "d.html").is_file())            # the output is kept


if __name__ == "__main__":
    unittest.main()
