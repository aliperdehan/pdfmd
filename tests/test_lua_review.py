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
