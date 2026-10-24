"""-j N: a document built by a worker process gets the same command-line settings as one built in the main process
(v3.27.3)."""

from __future__ import annotations

import inspect
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class WorkerState(unittest.TestCase):
    def test_every_global_main_sets_reaches_a_worker(self):
        names = set()
        for line in re.findall(r"^\s+global (.+)$", inspect.getsource(pdfmd.run_main), re.MULTILINE):
            names.update(name.strip() for name in line.split(","))
        self.assertTrue(names)
        for name in names:
            self.assertTrue(name.endswith("_CLI") or name in pdfmd.WORKER_GLOBALS,
                            f"main() sets {name}, which -j workers would not get (add it to WORKER_GLOBALS)")

    def test_the_state_round_trips(self):
        old = dict(pdfmd.CODE_CLI)
        self.addCleanup(lambda: (pdfmd.CODE_CLI.clear(), pdfmd.CODE_CLI.update(old)))
        pdfmd.CODE_CLI["line-numbers"] = True
        state = pdfmd.worker_state()
        self.assertIn("CODE_CLI", state)
        self.assertIn("SHOW_FULL_PATHS", state)
        import pickle
        state = pickle.loads(pickle.dumps(state))                 # what a spawned worker receives
        pdfmd.CODE_CLI.clear()
        pdfmd.restore_worker_state(state)
        self.assertEqual(pdfmd.CODE_CLI.get("line-numbers"), True)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Batch(unittest.TestCase):
    def test_a_worker_builds_what_the_main_process_builds(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-jobs-"))
        self.addCleanup(shutil.rmtree, directory, True)
        for name in ("a", "b"):
            (directory / name / "in").mkdir(parents=True)
        code = "---\ntitle: T\n---\n\n```python\nx = 1\ny = 2\n```\n"
        outputs = {}
        for jobs in ("1", "2"):
            for doc in ("one", "two"):
                (directory / jobs / f"{doc}.md").parent.mkdir(parents=True, exist_ok=True)
                (directory / jobs / f"{doc}.md").write_text(code, encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "-b", str(directory / jobs), "-j", jobs,
                                   "--to", "latex", "--line-numbers", "--no-stamp", "--no-backup"],
                                  cwd=directory, capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": ""})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            outputs[jobs] = sorted((path.name, path.read_text(encoding="utf-8"))
                                   for path in (directory / jobs).glob("*.tex"))
        self.assertEqual(len(outputs["2"]), 2)
        self.assertTrue(any("numbers" in text for _, text in outputs["1"]))      # line numbers asked for
        self.assertEqual(outputs["1"], outputs["2"])


if __name__ == "__main__":
    unittest.main()
