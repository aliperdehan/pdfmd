"""`pdfmd --help` in tiers: a short page, one page per topic, and the complete list."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402
import pdfmd_help  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], capture_output=True, text=True,
                          env={**os.environ, "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"]})


class TieredHelp(unittest.TestCase):
    def test_every_option_belongs_to_a_topic(self):
        self.assertEqual(pdfmd_help.uncovered(pdfmd.build_parser()), [])

    def test_the_default_page_is_short_and_names_the_topics(self):
        done = run("--help")
        self.assertEqual(done.returncode, 0)
        self.assertLess(len(done.stdout.splitlines()), 45)
        for topic in pdfmd_help.TOPICS:
            self.assertIn(topic, done.stdout)
        self.assertEqual(run("-h").stdout, done.stdout)

    def test_all_lists_every_option_and_a_topic_only_its_own(self):
        everything = run("--help", "all").stdout
        for action in pdfmd.build_parser()._actions:
            for option in action.option_strings:
                self.assertIn(option, everything, option)
        tables = run("--help", "tables").stdout
        self.assertIn("--extract-tables", tables)
        self.assertNotIn("--stamp-mode", tables)
        self.assertLess(len(tables.splitlines()), 80)

    def test_every_topic_prints(self):
        for topic in [*pdfmd_help.TOPICS, "other"]:
            done = run("--help", topic)
            self.assertEqual(done.returncode, 0, topic)
            self.assertIn(topic, done.stdout)

    def test_an_unknown_topic_is_an_error_that_lists_them(self):
        done = run("--help", "nonsense")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("tables", done.stderr)


if __name__ == "__main__":
    unittest.main()
