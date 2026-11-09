"""scripts/pdfmd: the checkout's pdfmd.py imported (bytecode cached) rather than run as a script (entry 3fi)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "scripts" / "pdfmd"
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


def launch(*arguments: str, cwd: Path, launcher: Path = LAUNCHER) -> subprocess.CompletedProcess:
    environment = dict(os.environ, PDFMD_CONFIG="", PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(launcher), *arguments], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", env=environment, timeout=300)


class Launcher(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="pdfmd-launcher-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_it_is_the_checkouts_pdfmd(self):
        done = launch("--version", cwd=self.folder)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), f"pdfmd {pdfmd.PDFMD_VERSION}")

    def test_a_module_in_the_documents_folder_is_not_imported(self):
        # what `python3 -m pdfmd` would do: the current folder first on the import path
        (self.folder / "json.py").write_text("raise SystemExit('the folder was on the import path')\n", encoding="utf-8")
        done = launch("--version", cwd=self.folder)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_a_symlink_to_it_finds_the_checkout(self):
        if os.name == "nt":
            self.skipTest("symlinks need a privilege on Windows")
        link = self.folder / "bin" / "pdfmd"
        link.parent.mkdir()
        link.symlink_to(LAUNCHER)
        done = launch("--version", cwd=self.folder, launcher=link)
        self.assertEqual(done.stdout.strip(), f"pdfmd {pdfmd.PDFMD_VERSION}", done.stderr)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_batch_workers_do_not_start_pdfmd_again(self):
        # -j starts processes that run the launcher again as __mp_main__; without its __main__ guard each would run pdfmd
        for name in ("a", "b"):
            (self.folder / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
        done = launch("-b", ".", "-j", "2", "--to", "html", "--no-backup", "--no-stamp", cwd=self.folder)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.folder / "a.html").is_file() and (self.folder / "b.html").is_file(), done.stdout + done.stderr)
        self.assertNotIn("usage:", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
