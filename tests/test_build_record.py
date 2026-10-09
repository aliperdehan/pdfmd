"""The engine named on the closing line, and `--strict` (v3.26.10)."""

from __future__ import annotations

import io
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402


class Record(unittest.TestCase):
    def test_label(self):
        built = pdfmd.Built((Path("a.md"), True, ""), "lualatex", [])
        self.assertEqual(pdfmd.engine_label(built), "  (lualatex)")
        built = pdfmd.Built((Path("a.md"), True, ""), "typst", ["lualatex", "xelatex"])
        self.assertEqual(pdfmd.engine_label(built), "  (typst; lualatex, xelatex failed)")
        self.assertEqual(pdfmd.engine_label(pdfmd.Built((Path("a.md"), False, "x"), "typst", [])), "")
        self.assertEqual(pdfmd.engine_label((Path("a.md"), True, "")), "")          # a plain tuple: nothing known

    def test_a_result_still_unpacks_and_crosses_a_process_pool(self):
        built = pdfmd.Built((Path("a.md"), True, "text"), "xelatex", ["lualatex"])
        path, ok, message = built
        self.assertEqual((path, ok, message), (Path("a.md"), True, "text"))
        again = pickle.loads(pickle.dumps(built))
        self.assertEqual((again.engine, again.failed, tuple(again)), ("xelatex", ["lualatex"], tuple(built)))

    def test_warning_lines_are_remembered_and_still_printed(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            with pdfmd.warning_capture() as seen:
                print("WARN  one")
                print("fine")
                print("[WARNING] two", file=sys.stderr)
                sys.stdout.write("WARN  three, written ")
                sys.stdout.write("in pieces\n")
                print("NOTE  not a warning")
        self.assertEqual(seen, ["WARN  one", "[WARNING] two", "WARN  three, written in pieces"])
        self.assertIn("fine", out.getvalue())
        self.assertIn("[WARNING] two", err.getvalue())

    def test_strict_fails_a_build_with_warnings_and_keeps_its_result_otherwise(self):
        pdfmd.STRICT_CLI = True
        self.addCleanup(setattr, pdfmd, "STRICT_CLI", None)
        failed = pdfmd.finish_build((Path("a.md"), True, "[WARNING] Could not fetch resource x.png"), [], Path("a.md"), [])
        self.assertFalse(failed[1])
        self.assertIn("--strict", failed[2])
        self.assertIn("Could not fetch resource", failed[2])
        clean = pdfmd.finish_build((Path("a.md"), True, ""), [], Path("a.md"), [])
        self.assertTrue(clean[1])
        pdfmd.STRICT_CLI = False
        lax = pdfmd.finish_build((Path("a.md"), True, ""), ["WARN  x"], Path("a.md"), [])
        self.assertTrue(lax[1])


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-record-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def run_pdfmd(self, *arguments: str, bare: bool = False) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"],
                       "PDFMD_NO_PROMPT": "1"}
        environment.pop("PDFMD_STRICT", None)
        if bare:                                           # nothing but Python on PATH: the built-in renderer builds
            empty = self.directory / "empty-bin"
            empty.mkdir(exist_ok=True)
            environment["PATH"] = str(empty)
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=environment)

    def write(self, name: str, text: str) -> None:
        (self.directory / name).write_text(text, encoding="utf-8")

    def test_the_built_in_renderer_is_named(self):
        self.write("doc.md", "# Hi\n\nText\n")
        done = self.run_pdfmd("doc.md", bare=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^OK    doc\.md  \((inkmd|md2pdf)\)$")

    def test_strict_applies_to_the_built_in_renderer_too(self):
        self.write("doc.md", "---\ntitle: T\nlang: en\ncustom: 1\n---\n\n# Hi\n\nText\n")
        loose = self.run_pdfmd("doc.md", bare=True)
        self.assertEqual(loose.returncode, 0)
        self.assertIn("WARN", loose.stdout + loose.stderr)
        strict = self.run_pdfmd("doc.md", "--strict", bare=True)
        self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)
        self.assertRegex(strict.stdout, r"(?m)^FAIL  doc\.md")
        self.assertIn("--strict: the build printed", strict.stdout)
        self.assertTrue((self.directory / "doc.pdf").is_file())            # the output is kept
        self.assertEqual(self.run_pdfmd("doc.md", "--strict", "--no-strict", bare=True).returncode, 0)

    @needs_pandoc(3, 1, 3)
    def test_strict_and_pandoc_warnings(self):
        self.write("doc.md", "---\ntitle: T\n---\n\n![x](nope.png)\n")
        self.assertEqual(self.run_pdfmd("doc.md", "-t", "docx").returncode, 0)
        strict = self.run_pdfmd("doc.md", "-t", "docx", "--strict")
        self.assertEqual(strict.returncode, 1)
        self.assertIn("Could not fetch resource", strict.stdout)
        self.write("doc.md", "---\ntitle: T\npdfmd-options:\n  strict: true\n---\n\n![x](nope.png)\n")
        self.assertEqual(self.run_pdfmd("doc.md", "-t", "docx").returncode, 1)         # the document asks for it
        self.assertEqual(self.run_pdfmd("doc.md", "-t", "docx", "--no-strict").returncode, 0)

    @needs_pandoc(3, 1, 3)
    def test_strict_in_a_batch_with_workers_fails_only_the_file(self):
        folder = self.directory / "batch"
        folder.mkdir()
        (folder / "good.md").write_text("---\ntitle: G\n---\n\nFine.\n", encoding="utf-8")
        (folder / "bad.md").write_text("---\ntitle: B\n---\n\n![x](nope.png)\n", encoding="utf-8")
        done = self.run_pdfmd("batch", "-b", "-j", "2", "-t", "docx", "--strict")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^OK    batch[\\/]good\.md")
        self.assertRegex(done.stdout, r"(?m)^FAIL  batch[\\/]bad\.md")


if __name__ == "__main__":
    unittest.main()
