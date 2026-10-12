"""What a build tells about its own decisions (v3.28.16): FOUND, DEFAULTS, and the rest on one line each, cut at the
screen's width; --verbose gives every decision with its reason, in the words the manuals quote."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class Lines(unittest.TestCase):
    def test_a_long_line_is_cut_with_a_count(self):
        log = pdfmd.AutoLog()
        parts = [f"file-number-{index}.yaml" for index in range(12)]
        line = log.fit("FOUND", parts)
        self.assertLessEqual(len(line), log.WIDTH)
        self.assertRegex(line, r", \+\d+ more \(--verbose\)$")
        self.assertTrue(line.startswith("FOUND     file-number-0.yaml, "))
        self.assertEqual(log.fit("FOUND", ["a", "b"]), "FOUND     a, b")

    def test_decisions_are_sorted_into_what_was_found_and_what_was_defaulted(self):
        log = pdfmd.AutoLog()
        log.record("MAINFONT", "d.md: no mainfont set; using STIX Two Text", False)
        log.record("PARTS", "d.md: 9 parts joined after it", False)
        log.record("MARGIN", "d.md: no geometry/margin set; using geometry:margin=1in on LaTeX-family targets", False)
        log.record("MONOFONT", "d.md: has code but no monofont set; using JetBrains Mono on LaTeX-family targets", False)
        log.record("LUA", "/x/y/filter.lua", False)
        log.record("STANDALONE", "d.md: needs a complete document", False)
        log.record("MARGIN", "d.md: margin: isn't a Pandoc variable -- using geometry:left=1in", False)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            log.flush()
        self.assertEqual(buffer.getvalue().splitlines(), [
            "FOUND     filter.lua, 9 parts",
            "DEFAULTS  margin 1in, font STIX Two Text, code in JetBrains Mono",
            "AUTO: STANDALONE MARGIN. Use --verbose to see in full"])

    def test_the_same_decision_twice_is_one_item_and_a_batch_does_not_repeat_a_line(self):
        log = pdfmd.AutoLog()
        log.reset(dedupe=True)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            for _ in range(3):
                log.record("MAINFONT", "d.md: no mainfont set; using STIX Two Text", False)
                log.record("MAINFONT", "d.md: no mainfont set; using STIX Two Text", False)
                log.record("STANDALONE", "x", False)
                log.flush()
        self.assertEqual(buffer.getvalue().splitlines(), ["DEFAULTS  font STIX Two Text",
                                                         "AUTO: STANDALONE. Use --verbose to see in full"])

    def test_verbose_prints_each_decision_as_it_happens(self):
        log = pdfmd.AutoLog()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            log.record("MAINFONT", "d.md: no mainfont set; using STIX Two Text", True)
            log.flush()
        self.assertEqual(buffer.getvalue(), "AUTO MAINFONT  d.md: no mainfont set; using STIX Two Text\n")


class Builds(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "home").mkdir()
        (self.root / "home" / "metadata.yaml").write_text("colorlinks: true\ncsl: apa\npapersize: a4\n", encoding="utf-8")
        self.doc = self.root / "doc"
        (self.doc / "metadata").mkdir(parents=True)
        (self.doc / "metadata" / "metadata.yaml").write_text("title: T\n", encoding="utf-8")
        (self.doc / "metadata" / "preamble.tex").write_text("\\usepackage{xcolor}\n", encoding="utf-8")
        (self.doc / "d.md").write_text("---\ntitle: T\n---\n\n# A\n\n```python\nprint(1)\n```\n", encoding="utf-8")

    def run_pdfmd(self, *args: str) -> list[str]:
        env = {**os.environ, "PDFMD_CONFIG": str(self.root / "home" / "config.yaml"), "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.doc, env=env,
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout.splitlines()

    def test_a_default_build_is_three_lines_and_the_ok_line(self):
        lines = self.run_pdfmd("d.md", "--to", "latex")
        self.assertEqual(lines[0], "FOUND     metadata/metadata.yaml, metadata/preamble.tex")
        self.assertTrue(lines[1].startswith("DEFAULTS  global metadata (colorlinks, csl +1), margin 1in"), lines[1])
        self.assertIn("font STIX Two Text", lines[1])
        self.assertIn("code in JetBrains Mono", lines[1])
        self.assertEqual(lines[-1], "OK    d.md")
        self.assertLessEqual(len(lines), 4, lines)
        self.assertTrue(all(len(line) <= 110 for line in lines), lines)
        self.assertFalse(any(line.startswith("AUTO YAML") for line in lines))

    def test_verbose_keeps_the_words_the_manuals_quote(self):
        text = "\n".join(self.run_pdfmd("d.md", "--to", "latex", "--verbose"))
        self.assertIn("AUTO YAML  ", text)
        self.assertIn("AUTO TEX", text)
        self.assertIn("(the global metadata of pdfmd --setup)", text)
        self.assertIn("AUTO MAINFONT  ", text)

    def test_a_batch_prints_one_found_and_one_defaults_line(self):
        for name in ("e.md", "f.md"):
            (self.doc / name).write_text((self.doc / "d.md").read_text(encoding="utf-8"), encoding="utf-8")
        lines = self.run_pdfmd("-b", ".", "--to", "latex")
        self.assertEqual(sum(line.startswith("FOUND") for line in lines), 1, lines)
        self.assertEqual(sum(line.startswith("DEFAULTS") for line in lines), 1, lines)
        self.assertEqual(sum(line.startswith("OK") for line in lines), 3, lines)

    def test_parallel_workers_stay_quiet_and_the_parent_says_what_it_found(self):
        for name in ("e.md", "f.md"):
            (self.doc / name).write_text((self.doc / "d.md").read_text(encoding="utf-8"), encoding="utf-8")
        lines = self.run_pdfmd("-b", ".", "--to", "latex", "-j", "2")
        self.assertEqual(sum(line.startswith("FOUND") for line in lines), 1, lines)
        self.assertEqual(sum(line.startswith("OK") for line in lines), 3, lines)
        self.assertLessEqual(len(lines), 6, lines)


if __name__ == "__main__":
    unittest.main()
