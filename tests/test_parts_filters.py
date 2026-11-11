"""Parts syntax is detected across all inputs while the scaffold supplies settings."""
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
class PartsFilters(unittest.TestCase):
    def test_parts_receive_caption_and_linebreak_filters_with_scaffold_settings(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as scratch:
                folder = Path(scratch)
                (folder / "parts").mkdir()
                (folder / "report.md").write_text(
                    "---\ntitle: Report\npdfmd-options:\n  parts: auto\n"
                    f"  table-captions: {'on' if enabled else 'off'}\n"
                    f"  linebreak: {'true' if enabled else 'false'}\n---\n\nLead.\n", encoding="utf-8")
                (folder / "parts" / "10-results.md").write_text(
                    "# Results\n\n**Table 1: Measurements**\n\n"
                    "| a | b |\n|---|---|\n| one<br>two | value |\n", encoding="utf-8")
                env = {**os.environ, "XDG_CONFIG_HOME": str(folder / "config"),
                       "XDG_CACHE_HOME": str(folder / "cache"), "XDG_DATA_HOME": str(folder / "data"),
                       "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "report.md",
                                       "--to", "latex", "-o", "out.tex", "--no-stamp", "--no-backup",
                                       "--no-auto", "crossref", "--verbose"], cwd=folder, env=env,
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                tex = (folder / "out.tex").read_text(encoding="utf-8")
                for rendered, command in ((r"\caption{Measurements}", "table_caption.lua"),
                                           (r"\strut one}\hbox{\strut two}", "linebreak.lua")):
                    with self.subTest(filter=command):
                        if enabled:
                            self.assertIn(rendered, tex)
                            self.assertIn(command, done.stderr)
                        else:
                            self.assertNotIn(rendered, tex)
                            self.assertNotIn(command, done.stderr)
