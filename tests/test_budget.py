"""Size budgets: --max-asset-mb and --max-output-mb (v3.26.18)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402


class Resolution(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-budget-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        for variable in ("PDFMD_MAX_ASSET_MB", "PDFMD_MAX_OUTPUT_MB"):
            os.environ.pop(variable, None)
            self.addCleanup(os.environ.pop, variable, None)

    def test_no_budget_by_default_then_the_document_then_the_command_line(self):
        document = self.directory / "d.md"
        document.write_text("---\ntitle: T\n---\n\nText\n", encoding="utf-8")
        self.assertEqual(pdfmd.resolve_budget(document, []), (None, None))
        document.write_text("---\ntitle: T\npdfmd-options:\n  max-asset-mb: 5\n  max-output-mb: 0.5\n---\n\nText\n", encoding="utf-8")
        self.assertEqual(pdfmd.resolve_budget(document, []), (5.0, 0.5))
        os.environ["PDFMD_MAX_ASSET_MB"] = "2"
        self.assertEqual(pdfmd.resolve_budget(document, []), (2.0, 0.5))
        os.environ["PDFMD_MAX_ASSET_MB"] = "0"                           # 0 on the command line: off, whatever the document says
        self.assertEqual(pdfmd.resolve_budget(document, []), (None, 0.5))


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-budget-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        (self.directory / "big.png").write_bytes(b"\x89PNG\r\n\x1a\n" + os.urandom(3 * 1024 * 1024))
        (self.directory / "small.png").write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f8ffff3f0005fe02fe"
            "a735810000000049454e44ae426082"))

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"], "PDFMD_NO_PROMPT": "1"}
        for variable in ("PDFMD_STRICT", "PDFMD_MAX_ASSET_MB", "PDFMD_MAX_OUTPUT_MB"):
            environment.pop(variable, None)
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=environment)

    def write(self, name: str, text: str) -> None:
        (self.directory / name).write_text(text, encoding="utf-8")

    def test_check_reports_the_image_only_when_a_budget_is_set(self):
        self.write("a.md", "---\ntitle: T\n---\n\n![big](big.png) ![small](small.png)\n")
        self.assertIn("no problems", self.run_pdfmd("a.md", "--check").stdout)
        done = self.run_pdfmd("a.md", "--check", "--max-asset-mb", "1")
        self.assertIn("a.md:5: warning: big.png is 3.0 MB, over the 1.0 MB budget  [asset-large]", done.stdout)
        self.assertNotIn("small.png", done.stdout)
        self.assertEqual(self.run_pdfmd("a.md", "--check", "--max-asset-mb", "1", "--strict").returncode, 1)

    @needs_pandoc(3, 1, 3)
    def test_the_build_names_the_image_before_it_starts(self):
        self.write("a.md", "---\ntitle: T\n---\n\n![big](big.png)\n")
        plain = self.run_pdfmd("a.md", "-t", "html")
        self.assertNotIn("budget", plain.stdout + plain.stderr)
        done = self.run_pdfmd("a.md", "-t", "html", "--max-asset-mb", "1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("big.png is 3.0 MB, over the 1 MB asset budget", done.stdout + done.stderr)
        strict = self.run_pdfmd("a.md", "-t", "html", "--max-asset-mb", "1", "--strict")
        self.assertEqual(strict.returncode, 1)
        self.assertTrue((self.directory / "a.html").is_file())              # the output is kept

    @needs_pandoc(3, 1, 3)
    def test_the_document_sets_the_budget_and_zero_turns_it_off(self):
        self.write("a.md", "---\ntitle: T\npdfmd-options:\n  max-asset-mb: 1\n---\n\n![big](big.png)\n")
        first = self.run_pdfmd("a.md", "-t", "html")
        self.assertIn("asset budget", first.stdout + first.stderr)
        off = self.run_pdfmd("a.md", "-t", "html", "--max-asset-mb", "0")
        self.assertNotIn("asset budget", off.stdout + off.stderr)

    @needs_pandoc(3, 1, 3)
    def test_the_output_budget_names_the_largest_images(self):
        self.write("a.md", "---\ntitle: T\n---\n\n![big](big.png)\n")
        small = self.run_pdfmd("a.md", "-t", "html", "--max-output-mb", "1")
        self.assertNotIn("output budget", small.stdout + small.stderr)         # the HTML only points at the image
        done = self.run_pdfmd("a.md", "-t", "html", "--self-contained", "--max-output-mb", "1")
        self.assertRegex(done.stdout + done.stderr,
                         r"a\.html is \d+\.\d MB, over the 1 MB output budget.*largest images: big\.png 3\.0 MB")

    @needs_pandoc(3, 1, 3)
    def test_a_batch_with_workers_gets_the_budget(self):
        folder = self.directory / "batch"
        folder.mkdir()
        shutil.copy(self.directory / "big.png", folder / "big.png")
        (folder / "one.md").write_text("---\ntitle: One\n---\n\n![big](big.png)\n", encoding="utf-8")
        (folder / "two.md").write_text("---\ntitle: Two\n---\n\nNo images.\n", encoding="utf-8")
        done = self.run_pdfmd("batch", "-b", "-j", "2", "-t", "html", "--max-asset-mb", "1", "--strict")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^FAIL  batch[\\/]one\.md")
        self.assertRegex(done.stdout, r"(?m)^OK    batch[\\/]two\.md")


if __name__ == "__main__":
    unittest.main()
