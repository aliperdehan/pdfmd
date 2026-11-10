"""The missing-glyph retry says what it did (v3.32.49)."""

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

LUALATEX_LOG = """[WARNING] Missing character: There is no ≥ (U+2265) in font "name:STIX Two Text:mode=node;script=latn;"!
[WARNING] Missing character: There is no ≥ (U+2265) in font "name:STIX Two Text:mode=node;script=latn;"!
[WARNING] Missing character: There is no ≥ (U+2265) in font "name:STIX Two Text:mode=node;script=latn;"!
[WARNING] Missing character: There is no ∓ (U+2213) in font "name:STIX Two Text:mode=node;script=latn;"!
"""


class Note(unittest.TestCase):
    def test_the_code_points_come_out_of_the_log_once_each_in_order(self):
        self.assertEqual(pdfmd.missing_glyph_codes(LUALATEX_LOG), [0x2213, 0x2265])
        self.assertEqual(pdfmd.missing_glyph_codes("Missing character: There is no ≥ (U+1F600) in font x!\n"), [0x1F600])
        self.assertEqual(pdfmd.missing_glyph_codes("all fine\n"), [])

    def test_characters_no_font_draws_are_left_out(self):
        pdfmd.UNICODE_UNCOVERED.add(0x2213)
        self.addCleanup(pdfmd.UNICODE_UNCOVERED.discard, 0x2213)
        self.assertEqual(pdfmd.missing_glyph_codes(LUALATEX_LOG), [0x2265])

    def test_the_line_names_the_font_the_code_points_and_the_new_font(self):
        line = pdfmd.retry_font_note(Path("d.md"), "STIX Two Text", "DejaVu Serif", [0x2265, 0xB1])
        self.assertTrue(line.startswith("WARN  "), line)
        self.assertIn("STIX Two Text lacks U+2265, U+00B1; rebuilt in DejaVu Serif (set mainfont: to keep your own)", line)

    def test_a_retry_with_no_code_point_to_name_says_so(self):
        line = pdfmd.retry_font_note(Path("d.md"), "STIX Two Text", "DejaVu Serif", [])
        self.assertIn("STIX Two Text lacked glyphs the build did not name", line)
        self.assertIn("rebuilt in DejaVu Serif", line)


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("lualatex") and shutil.which("fc-list")
                     and {"stix two text", "dejavu serif"} <= set(pdfmd.installed_font_families() or ()),
                     "needs Pandoc, LuaLaTeX, STIX Two Text and DejaVu Serif")
class InABuild(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-retry-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, *arguments: str) -> str:
        (self.directory / "d.md").write_text("---\ntitle: T\n---\n\nx \\geq 3 y (text-mode command)\n", encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
        environment.pop("PDFMD_STRICT", None)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-e", "lualatex", *arguments],
                              cwd=self.directory, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout + done.stderr

    def test_the_whole_document_swap_is_announced(self):
        self.assertIn("WARN  d.md: STIX Two Text lacks U+2265; rebuilt in DejaVu Serif (set mainfont: to keep your own)",
                      self.build())

    def test_a_font_of_the_documents_own_is_not_retried_and_says_nothing(self):
        self.assertNotIn("rebuilt in", self.build("-f", "STIX Two Text"))


if __name__ == "__main__":
    unittest.main()
