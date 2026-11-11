"""Batch cache switches override document settings in sequential and worker builds."""
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


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("pdflatex"), "needs Pandoc and pdfLaTeX")
class BatchCache(unittest.TestCase):
    def test_both_switches_override_the_document_with_one_or_two_workers(self):
        for jobs in (1, 2):
            for enabled in (False, True):
                with self.subTest(jobs=jobs, enabled=enabled), tempfile.TemporaryDirectory() as scratch:
                    folder = Path(scratch)
                    for name in ("a", "b"):
                        (folder / f"{name}.md").write_text(
                            f"---\npdfmd-options:\n  cache: {str(not enabled).lower()}\n---\n\nHello.\n",
                            encoding="utf-8")
                    env = {**os.environ, "XDG_CONFIG_HOME": str(folder / "config"),
                           "XDG_CACHE_HOME": str(folder / "cache"), "XDG_DATA_HOME": str(folder / "data"),
                           "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
                    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "-b", ".",
                                           "-j", str(jobs), "-e", "pdflatex", "--engine-fallback", "missing",
                                           "--cache" if enabled else "--no-cache", "--cache-location", "document",
                                           "--no-stamp", "--no-backup"], cwd=folder, env=env,
                                          stdin=subprocess.DEVNULL, capture_output=True, text=True)
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(len(list(folder.glob("*.pdf"))), 2)
                    manifests = list((folder / ".cache" / "pdfmd").rglob(".pdfmd-source.json"))
                    self.assertEqual(len(manifests), 2 if enabled else 0, done.stdout + done.stderr)
