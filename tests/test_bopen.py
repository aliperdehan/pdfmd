"""v3.28.20: --bopen SPEC opens the chosen files of a batch when it is done (fN, lN, flN, eN, sN, all; any N)."""

from __future__ import annotations

import os
import stat
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class Spec(unittest.TestCase):
    def test_the_selectors(self):
        pick = pdfmd.bopen_indices
        self.assertEqual(pick("f2", 10), [0, 1])
        self.assertEqual(pick("l3", 10), [7, 8, 9])
        self.assertEqual(pick("fl10", 20), [0, 1, 2, 3, 4, 15, 16, 17, 18, 19])
        self.assertEqual(pick("fl15", 30), list(range(8)) + list(range(23, 30)))           # 8 first, 7 last
        self.assertEqual(pick("e3", 10), [2, 5, 8])
        self.assertEqual(pick("s3", 10), [0, 3, 6, 9])                                      # Python's [::3]: first, then every 3rd
        self.assertEqual(pick("s1", 3), [0, 1, 2])
        self.assertEqual(pick("s1000", 10), [0])
        self.assertEqual(pick("S2,e5", 10), [0, 2, 4, 6, 8, 9])
        self.assertEqual(pick("e1", 3), [0, 1, 2])
        self.assertEqual(pick("e1000", 10), [])
        self.assertEqual(pick("all", 3), [0, 1, 2])
        self.assertEqual(pick("f2,l1", 5), [0, 1, 4])
        self.assertEqual(pick("f2, e2", 5), [0, 1, 3])                                      # a union, each file once
        self.assertEqual(pick("F2", 5), [0, 1])
        self.assertEqual(pick("fl 10", 20), pick("fl10", 20))
        self.assertEqual(pick("f99", 3), [0, 1, 2])                                          # more than there are
        self.assertEqual(pick("fl4", 2), [0, 1])
        self.assertEqual(pick("l5", 0), [])

    def test_a_bad_spec_stops_with_the_grammar(self):
        for bad in ("", "x", "f", "f0", "fl", "e0", "s0", "2f", "f2;;x"):
            with self.subTest(bad), self.assertRaises(SystemExit) as caught:
                pdfmd.bopen_indices(bad, 5)
            self.assertIn("fN", str(caught.exception))


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc (the CI native job has none)")
@unittest.skipIf(sys.platform == "win32", "uses a fake opener on PATH")
class Batch(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "opened.log"
        for name in ("open", "xdg-open"):
            script = self.bin / name
            script.write_text(f'#!/bin/sh\necho "$1" >> "{self.log}"\n', encoding="utf-8")
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        for number in range(1, 7):
            (self.docs / f"d{number}.md").write_text(f"# D{number}\n\nText.\n", encoding="utf-8")

    def run_pdfmd(self, *args: str, jobs: str = "1") -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "PDFMD_CONFIG": "",
               "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args, "--to", "html", "-j", jobs], cwd=self.docs,
                              env=env, capture_output=True, text=True, timeout=300)

    def opened(self) -> list[str]:
        return [Path(line).name for line in self.log.read_text(encoding="utf-8").split()] if self.log.exists() else []

    def test_the_chosen_files_open_in_listing_order(self):
        done = self.run_pdfmd("-b", ".", "--bopen", "f2,l1", jobs="2")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.opened(), ["d1.html", "d2.html", "d6.html"])
        self.assertIn("OPENED  3 of 6 (f2,l1)", done.stdout)

    def test_every_nth_and_no_spec_means_all(self):
        self.run_pdfmd("-b", ".", "--bopen", "e3")
        self.assertEqual(self.opened(), ["d3.html", "d6.html"])
        self.log.unlink()
        self.run_pdfmd("-b", ".", "--bopen")
        self.assertEqual(len(self.opened()), 6)

    def test_open_alone_is_still_ignored_in_a_batch_and_says_where_to_look(self):
        done = self.run_pdfmd("-b", ".", "--open")
        self.assertEqual(self.opened(), [])
        self.assertIn("--bopen", done.stderr)

    def test_a_bad_spec_stops_before_building(self):
        done = self.run_pdfmd("-b", ".", "--bopen", "q9")
        self.assertNotEqual(done.returncode, 0)
        self.assertFalse((self.docs / "d1.html").exists())

    def test_a_folder_after_a_bare_bopen_is_the_folder(self):
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "PDFMD_CONFIG": "",
               "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--bopen", "docs", "-b", "--to", "html"],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(len(self.opened()), 6)


if __name__ == "__main__":
    unittest.main()
