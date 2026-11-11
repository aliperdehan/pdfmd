"""Relative Python API outputs stay in the caller's directory when the child runs elsewhere."""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class RelativeApiOutput(unittest.TestCase):
    def test_relative_outputs_are_fresh_and_survive_the_child_working_directory(self):
        for text_api in (False, True):
            for stale in (False, True):
                for child_cwd in (False, True):
                    with self.subTest(text_api=text_api, stale=stale, child_cwd=child_cwd), tempfile.TemporaryDirectory() as scratch:
                        folder = Path(scratch).resolve()
                        caller = folder / "caller"
                        caller.mkdir()
                        child = folder / "child"
                        child.mkdir()
                        source = folder / "source.md"
                        source.write_text("Fresh *content*.\n", encoding="utf-8")
                        if stale:
                            (caller / "out.html").write_text("stale output", encoding="utf-8")
                        env = {**os.environ, "XDG_CONFIG_HOME": str(folder / "config"),
                               "XDG_CACHE_HOME": str(folder / "cache"), "XDG_DATA_HOME": str(folder / "data"),
                               "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
                        # Route the API's child through the checkout launcher, with closed stdin.
                        run = subprocess.run
                        def launch(command, **kwargs):
                            command = [command[0], str(ROOT / "scripts" / "pdfmd"), *command[2:]]
                            return run(command, stdin=subprocess.DEVNULL, **kwargs)
                        with contextlib.chdir(caller), mock.patch.dict(os.environ, env), mock.patch.object(
                                pdfmd.subprocess, "run", side_effect=launch):
                            options = {"cwd": child} if child_cwd else {}
                            if text_api:
                                output = pdfmd.convert_text(source.read_text(encoding="utf-8"), "html", outputfile="out.html", **options)
                            else:
                                output = pdfmd.convert_file(source, "html", outputfile="out.html", **options)
                            self.assertEqual(output.resolve(), caller / "out.html")
                            self.assertIn("Fresh <em>content</em>", output.read_text(encoding="utf-8"))
                        self.assertFalse((child / "out.html").exists())
