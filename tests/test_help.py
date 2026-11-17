"""`pdfmd --help` in tiers: a short page, one page per topic, and the complete list."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
import pdfmd_help  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], capture_output=True, text=True,
                          env={**os.environ, "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"], "APPDATA": os.environ["XDG_CONFIG_HOME"]})


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
            if action.help == argparse.SUPPRESS:
                continue                       # internal: the ASCII filter's helper
            for option in action.option_strings:
                self.assertIn(option, everything, option)
        tables = run("--help", "tables").stdout
        self.assertIn("--extract-tables", tables)
        self.assertNotIn("--stamp-mode", tables)
        self.assertLess(len(tables.splitlines()), 80)

    def test_pandoc_memory_key_has_a_help_topic(self):
        for topic in ("output", "all"):
            self.assertIn("pdfmd-options.pandoc-memory", run("--help", topic).stdout)

    def test_document_indent_key_has_a_help_topic(self):
        for topic in ("output", "all"):
            self.assertIn("pdfmd-options.indent", run("--help", topic).stdout)

    def test_csl_line_spacing_is_in_output_help(self):
        self.assertIn("CSL line-spacing", run("--help", "output").stdout)

    def test_tables_help_explains_column_estimate(self):
        text = run("--help", "tables").stdout
        self.assertIn("column-estimate", text)
        self.assertIn("Typst", text)
        self.assertIn("measured/cached", text)
        self.assertIn("measure", text)
        self.assertIn("count (default)", " ".join(text.split()))

    def test_every_topic_prints(self):
        for topic in [*pdfmd_help.TOPICS, "other"]:
            done = run("--help", topic)
            self.assertEqual(done.returncode, 0, topic)
            self.assertIn(topic, done.stdout)

    def test_setup_help_explains_the_install_catalogue_and_diagram_group(self):
        text = run("--help", "setup").stdout
        self.assertIn("diagram:all", text)
        self.assertIn("source, target and removal", " ".join(text.split()))

    def test_an_unknown_topic_is_an_error_that_lists_them(self):
        done = run("--help", "nonsense")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("tables", done.stderr)


if __name__ == "__main__":
    unittest.main()
