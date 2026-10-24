"""Parts that are symlinks (v3.30.5): a file or a folder linked into `parts/` is built as a part, and `report@name` says
what `report#name` does (an interactive bash takes a `#` for a comment)."""

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

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")


@unittest.skipUnless(PANDOC and hasattr(os, "symlink"), "needs Pandoc and symlinks")
class Symlinks(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pdfmd-symlink-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        outside = self.root / "outside"
        (outside / "folder").mkdir(parents=True)
        (outside / "b.md").write_text("Linked file part.\n", encoding="utf-8")
        (outside / "folder" / "c.md").write_text("Linked folder part.\n", encoding="utf-8")
        self.project = self.root / "project"
        (self.project / "parts").mkdir(parents=True)
        (self.project / "report.md").write_text("---\ntitle: T\npdfmd-options:\n  parts: auto\n---\n", encoding="utf-8")
        (self.project / "parts" / "10-a.md").write_text("# One\n\nReal part.\n", encoding="utf-8")
        try:
            (self.project / "parts" / "20-b.md").symlink_to(outside / "b.md")
            (self.project / "parts" / "30-folder").symlink_to(outside / "folder", target_is_directory=True)
        except OSError:
            self.skipTest("symlinks are not allowed here")

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments, "--to", "latex", "--no-backup"],
                              cwd=self.project, capture_output=True, text=True, encoding="utf-8")

    def test_collected_parts_stay_under_the_parts_folder(self):
        found = pdfmd.collect_parts((self.project / "parts").resolve())
        self.assertEqual([path.name for path in found], ["10-a.md", "20-b.md", "c.md"])
        for path in found:
            self.assertTrue(path.is_relative_to((self.project / "parts").resolve()), path)

    def test_a_linked_file_and_a_linked_folder_are_built(self):
        done = self.run_pdfmd("report.md", "-o", "out.tex")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (self.project / "out.tex").read_text(encoding="utf-8")
        self.assertLess(text.index("Real part."), text.index("Linked file part."))
        self.assertLess(text.index("Linked file part."), text.index("Linked folder part."))

    def test_a_linked_part_can_be_asked_for_by_name(self):
        done = self.run_pdfmd("report@b", "-o", "b.tex")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = (self.project / "b.tex").read_text(encoding="utf-8")
        self.assertIn("Linked file part.", text)
        self.assertNotIn("Real part.", text)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class AtSign(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pdfmd-at-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "parts").mkdir()
        (self.root / "report.md").write_text("---\ntitle: T\npdfmd-options:\n  parts: auto\n---\n", encoding="utf-8")
        (self.root / "parts" / "10-intro.md").write_text("# Intro\n\nIntro text.\n", encoding="utf-8")
        (self.root / "parts" / "20-methods.md").write_text("# Methods\n\nMethods text.\n\n## Sampling\n\nSampling text.\n", encoding="utf-8")
        (self.root / "doc.md").write_text("# Alpha\n\nAlpha text.\n\n## Beta\n\nBeta text.\n\n# Gamma\n\nGamma text.\n", encoding="utf-8")

    def tex(self, *arguments: str, out: str = "o.tex") -> str:
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments, "--to", "latex", "--no-backup", "-o", out],
                              cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.root / out).read_text(encoding="utf-8")

    def test_at_is_hash(self):
        for spelling in ("report#methods", "report@methods", "parts/20-methods.md"):
            with self.subTest(spelling=spelling):
                text = self.tex(spelling)
                self.assertIn("Methods text.", text)
                self.assertNotIn("Intro text.", text)

    def test_a_section_of_an_ordinary_document_is_the_same_with_either_sign(self):
        for hash_spelling, at_spelling, wanted, unwanted in (("doc#gamma", "doc@gamma", "Gamma text.", "Beta text."),
                                                             ("doc##beta", "doc@@beta", "Beta text.", "Gamma text."),
                                                             ("doc##beta", "doc#@beta", "Beta text.", "Gamma text."),
                                                             ("doc#beta+gamma", "doc@beta+gamma", "Gamma text.", "No such text.")):
            with self.subTest(at=at_spelling):
                with_hash = self.tex(hash_spelling, out="hash.tex")
                with_at = self.tex(at_spelling, out="at.tex")
                self.assertEqual(with_at, with_hash)
                self.assertIn(wanted, with_at)
                self.assertNotIn(unwanted, with_at)

    def test_no_document_named_means_the_folders_only_markdown_file(self):
        (self.root / "report.md").unlink()
        (self.root / "parts").rename(self.root / "elsewhere")
        (self.root / "doc.md").rename(self.root / "only.md")
        self.assertIn("Beta text.", self.tex("@@beta"))

    def test_a_real_path_with_an_at_sign_wins(self):
        (self.root / "notes@2x.md").write_text("Real file with an @ in its name.\n", encoding="utf-8")
        self.assertIn("Real file with an @", self.tex("notes@2x.md"))


if __name__ == "__main__":
    unittest.main()
