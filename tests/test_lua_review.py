"""Lua review regressions exercised through the isolated checkout launcher."""

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


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class LuaReview(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="pdfmd-lua-review-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                    "XDG_CONFIG_HOME": str(self.root / "config"), "XDG_CACHE_HOME": str(self.root / "cache"),
                    "XDG_DATA_HOME": str(self.root / "data"), "APPDATA": str(self.root / "config"),
                    "LOCALAPPDATA": str(self.root / "cache")}

    def build(self, source, to, *extra, request="d.md"):
        (self.root / "d.md").write_text(source, encoding="utf-8")
        output = self.root / ("out." + {"latex": "tex", "typst": "typ"}.get(to, to))
        output.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), request,
                               "--to", to, "-o", str(output), "--no-stamp", "--no-backup", *extra],
                              cwd=self.root, env=self.env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=180)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return output.read_text(encoding="utf-8")

    def test_calc_signed_remainder(self):
        source = "Remainders: `7 % -3`{=}, `7 % +3`{=}, `-7 % -3`{=}, `7 % -(1+2)`{=}.\n"
        for to in ("latex", "typst", "html"):
            with self.subTest(to=to):
                text = self.build(source, to)
                self.assertIn("Remainders: -2, 1, -1, -2.", text)

    def test_calc_away_preserves_rounded_values(self):
        source = ("---\npdfmd-options: {calc: {round: away}}\n---\n\n"
                  "Stable: `round(10000000000000) - 10000000000000`{=}, "
                  "`round(-10000000000000) + 10000000000000`{=}, "
                  "`round(1.2345678901234, 13) - 1.2345678901234`{=}, "
                  "`round(4503599627370496) - 4503599627370496`{=}.\n\n"
                  "Ties: `round(2.675, 2)`{=}, `round(-1.005, 2)`{=}.\n\n"
                  "Below: `round(1.0049999999999, 2)`{=}.\n")
        for to in ("latex", "typst", "html"):
            with self.subTest(to=to):
                text = self.build(source, to)
                self.assertIn("Stable: 0, 0, 0, 0.", text)
                self.assertIn("Ties: 2.68, -1.01.", text)
                self.assertIn("Below: 1.", text)

    def test_flat_partial_preserves_section_numbers(self):
        parts = self.root / "parts"
        parts.mkdir()
        (parts / "10-first.md").write_text("# First\n\nDiscarded.\n", encoding="utf-8")
        (parts / "20-second.md").write_text("# Second\n\n## Child\n\nKept.\n", encoding="utf-8")
        source = "---\npdfmd-options: {parts: auto}\n---\n"
        for to in ("gfm", "txt", "latex", "typst", "html"):
            with self.subTest(to=to):
                text = self.build(source, to, "--number-sections", request="d@20")
                self.assertIn("Second", text)
                self.assertIn("Child", text)
                self.assertNotIn("Discarded.", text)
                if to in ("gfm", "txt"):
                    self.assertIn("2 Second", text)
                    self.assertIn("2.1 Child", text)

    def test_horizontal_table_default_keeps_untagged_contents(self):
        source = ("---\npdfmd-options: {table-align: centre}\n---\n\n"
                  "| Name | Qty |\n|---|---|\n| apples | 3 |\n| total | 12 |\n")
        for to in ("latex", "typst", "html"):
            with self.subTest(to=to):
                text = self.build(source, to)
                self.assertIn("apples", text)
                self.assertIn("total", text)
                if to == "latex":
                    self.assertIn(r"\multicolumn{1}{c}{apples}", text)
                    self.assertIn(r"\multicolumn{1}{c}{total}", text)
                elif to == "html":
                    self.assertIn('<td style="text-align: center;">apples</td>', text)
