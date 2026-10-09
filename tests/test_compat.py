"""What pdfmd says about an old Pandoc, and the single-file build for a machine that cannot pip install."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class Versions(unittest.TestCase):
    def test_what_an_older_pandoc_does_without(self):
        self.assertEqual(pdfmd.pandoc_limits((3, 12)), [])
        self.assertEqual(len(pdfmd.pandoc_limits((3, 1, 3))), 3)
        self.assertEqual(len(pdfmd.pandoc_limits((3, 4))), 1)
        self.assertIn("{#id}", pdfmd.pandoc_limits((3, 4))[0])
        self.assertEqual(pdfmd.PANDOC_MIN, (3, 1, 3))

    def test_the_first_compile_with_an_older_pandoc_says_so_once(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-compat-"))
        self.addCleanup(shutil.rmtree, directory, True)
        environment = {k: v for k, v in os.environ.items() if k != "PDFMD_NO_PROMPT"}
        environment["XDG_CONFIG_HOME"] = str(directory)
        environment["APPDATA"] = str(directory)           # where Windows keeps it
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(pdfmd, "pandoc_version", return_value=(3, 0, 1)):
            first, second = io.StringIO(), io.StringIO()
            with redirect_stderr(first):
                pdfmd.warn_old_pandoc()
            with redirect_stderr(second):
                pdfmd.warn_old_pandoc()
        self.assertIn("Pandoc 3.0.1 is older than 3.1.3", first.getvalue())
        self.assertEqual(second.getvalue(), "")

    def test_nothing_is_said_for_a_tested_pandoc_or_for_none_at_all(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-compat-"))
        self.addCleanup(shutil.rmtree, directory, True)
        for version in ((3, 1, 3), (3, 12), (0,)):
            environment = {k: v for k, v in os.environ.items() if k != "PDFMD_NO_PROMPT"}
            environment["XDG_CONFIG_HOME"] = str(directory)
            environment["APPDATA"] = str(directory)           # where Windows keeps it
            with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(pdfmd, "pandoc_version", return_value=version):
                shown = io.StringIO()
                with redirect_stderr(shown):
                    pdfmd.warn_old_pandoc()
            self.assertEqual(shown.getvalue(), "", version)


class Crossref(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "the stand-in programs are sh scripts")
    def test_a_pandoc_crossref_built_for_another_pandoc_is_not_run(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-crossref-"))
        self.addCleanup(shutil.rmtree, directory, True)
        document = directory / "d.md"
        document.write_text("See @tbl:t.\n\n| a |\n|---|\n| 1 |\n\n: Stock {#tbl:t}\n", encoding="utf-8")
        pdfmd.crossref_built_for.cache_clear()
        fake = directory / "pandoc-crossref"
        fake.write_text("#!/bin/sh\necho 'pandoc-crossref v0.3.25 built with Pandoc v3.12, pandoc-types v1.23.1.2'\n", encoding="utf-8")
        fake.chmod(0o755)
        for running, expected in (((3, 1, 3), []), ((3, 12, 1), ["--filter", "pandoc-crossref"]), ((0,), ["--filter", "pandoc-crossref"])):
            shown = io.StringIO()
            with mock.patch.object(pdfmd, "pandoc_version", return_value=running), \
                    mock.patch.object(pdfmd, "which", side_effect=lambda name: str(fake) if name == "pandoc-crossref" else None), \
                    redirect_stderr(shown):
                args = pdfmd.crossref_filter_args(document, [], None, "d.md")
            self.assertEqual(args, expected, running)
            self.assertEqual("built for Pandoc 3.12 and this is Pandoc 3.1.3" in shown.getvalue(), running == (3, 1, 3))


class Zipapp(unittest.TestCase):
    def test_one_file_that_runs_with_nothing_installed_but_python(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-zipapp-"))
        self.addCleanup(shutil.rmtree, directory, True)
        archive = directory / "pdfmd.pyz"
        built = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_zipapp.py"), "-o", str(archive)],
                               capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        env = {**os.environ, "XDG_CACHE_HOME": str(directory / "cache"), "XDG_CONFIG_HOME": str(directory / "cfg"),
               "PDFMD_NO_PROMPT": "1"}
        # -S: without site-packages, so PyYAML and pypdf can only be the copies inside the file
        done = subprocess.run([sys.executable, "-S", str(archive), "--version"], cwd=directory, capture_output=True,
                              text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), f"pdfmd {pdfmd.PDFMD_VERSION}")
        unpacked = list((directory / "cache" / "pdfmd" / "pyz").iterdir())
        self.assertEqual(len(unpacked), 1)
        for name in ("pdfmd.py", "pdfmd_lua/table_width.lua", "pdfmd_lua/code_wrap.tex", "yaml/__init__.py", "pypdf/__init__.py"):
            self.assertTrue((unpacked[0] / name).is_file(), name)
        again = subprocess.run([sys.executable, "-S", str(archive), "--version"], cwd=directory, capture_output=True,
                               text=True, env=env)
        self.assertEqual(again.stdout, done.stdout)
        self.assertEqual(len(list((directory / "cache" / "pdfmd" / "pyz").iterdir())), 1)       # unpacked once

    @unittest.skipUnless(shutil.which("pandoc") and (shutil.which("lualatex") or shutil.which("xelatex") or shutil.which("pdflatex")),
                         "needs Pandoc and a LaTeX engine")
    def test_it_builds_a_document_with_its_filters(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-zipapp-"))
        self.addCleanup(shutil.rmtree, directory, True)
        archive = directory / "pdfmd.pyz"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_zipapp.py"), "-o", str(archive)], check=True,
                       capture_output=True)
        (directory / "t.md").write_text("---\ntitle: Zipapp\n---\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nprint('hi')\n```\n",
                                        encoding="utf-8")
        env = {**os.environ, "XDG_CACHE_HOME": str(directory / "cache"), "XDG_CONFIG_HOME": str(directory / "cfg"),
               "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, "-S", str(archive), "t.md", "--verbose"], cwd=directory, capture_output=True,
                              text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((directory / "t.pdf").is_file())
        self.assertIn("table_width.lua", done.stdout + done.stderr)      # the filters were found in the unpacked folder


if __name__ == "__main__":
    unittest.main()
