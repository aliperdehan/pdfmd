"""v3.30.37: `--no-rewrite` writes `report (1).pdf` when `report.pdf` is already there."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(directory: str, *arguments: str, text: str | None = None) -> subprocess.CompletedProcess:
    empty = Path(directory) / "empty-bin"
    empty.mkdir(exist_ok=True)
    environment = {**os.environ, "PATH": str(empty), "PDFMD_CALIBRE": "", "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "",
                   "XDG_CONFIG_HOME": directory}           # nothing but Python: the built-in renderer builds the PDF
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], cwd=directory, env=environment,
                          input=text, capture_output=True, text=True)


def names(directory: str) -> list[str]:
    return sorted(item.name for item in Path(directory).iterdir() if item.suffix == ".pdf")


class Rewrite(unittest.TestCase):
    def folder(self, front: str = ""):
        directory = tempfile.TemporaryDirectory()
        (Path(directory.name) / "doc.md").write_text(f"{front}# Hi\n\nSome text.\n", encoding="utf-8")
        return directory

    def test_by_default_the_old_file_is_replaced(self):
        with self.folder() as directory:
            for _ in range(2):
                self.assertEqual(run(directory, "doc.md", "-e", "inkmd").returncode, 0)
            self.assertEqual(names(directory), ["doc.pdf"])

    def test_no_rewrite_numbers_the_copy_and_leaves_the_old_file_byte_identical(self):
        with self.folder() as directory:
            self.assertEqual(run(directory, "doc.md", "-e", "inkmd").returncode, 0)
            first = (Path(directory) / "doc.pdf").read_bytes()
            second = run(directory, "doc.md", "-e", "inkmd", "--no-rewrite")
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("doc.md > doc (1).pdf", second.stdout)
            self.assertEqual(run(directory, "doc.md", "-e", "inkmd", "--no-rewrite").returncode, 0)
            self.assertEqual(names(directory), ["doc (1).pdf", "doc (2).pdf", "doc.pdf"])
            self.assertEqual((Path(directory) / "doc.pdf").read_bytes(), first)

    def test_a_first_build_has_no_number(self):
        with self.folder() as directory:
            self.assertEqual(run(directory, "doc.md", "-e", "inkmd", "--no-rewrite").returncode, 0)
            self.assertEqual(names(directory), ["doc.pdf"])

    def test_the_document_can_turn_it_off_and_the_command_line_turns_it_back_on(self):
        with self.folder("---\npdfmd-options:\n  rewrite: false\n---\n\n") as directory:
            run(directory, "doc.md", "-e", "inkmd")
            run(directory, "doc.md", "-e", "inkmd")
            self.assertEqual(names(directory), ["doc (1).pdf", "doc.pdf"])
            run(directory, "doc.md", "-e", "inkmd", "--rewrite")
            self.assertEqual(names(directory), ["doc (1).pdf", "doc.pdf"])

    def test_the_name_comes_from_a_template(self):
        with self.folder("---\npdfmd-options:\n  rewrite: false\n  rewrite-name: \"{stem}-{n}{ext}\"\n---\n\n") as directory:
            run(directory, "doc.md", "-e", "inkmd")
            run(directory, "doc.md", "-e", "inkmd")
            self.assertEqual(names(directory), ["doc-1.pdf", "doc.pdf"])

    def test_a_template_without_a_number_or_with_a_folder_is_refused_for_the_default(self):
        for template in ("copy.pdf", "sub/{n}.pdf"):
            with self.subTest(template=template), self.folder(
                    f"---\npdfmd-options:\n  rewrite: false\n  rewrite-name: \"{template}\"\n---\n\n") as directory:
                run(directory, "doc.md", "-e", "inkmd")
                done = run(directory, "doc.md", "-e", "inkmd")
                self.assertIn("rewrite-name", done.stderr)
                self.assertEqual(names(directory), ["doc (1).pdf", "doc.pdf"])

    def test_an_o_name_that_exists_is_numbered_too(self):
        with self.folder() as directory:
            run(directory, "doc.md", "-e", "inkmd", "-o", "out.pdf")
            run(directory, "doc.md", "-e", "inkmd", "-o", "out.pdf", "--no-rewrite")
            self.assertEqual(names(directory), ["out (1).pdf", "out.pdf"])

    def test_every_file_of_a_batch_is_numbered_on_its_own(self):
        with self.folder() as directory:
            (Path(directory) / "two.md").write_text("# Two\n", encoding="utf-8")
            run(directory, "-b", "-e", "inkmd")
            run(directory, "-b", "-e", "inkmd", "--no-rewrite")
            self.assertEqual(names(directory), ["doc (1).pdf", "doc.pdf", "two (1).pdf", "two.pdf"])

    def test_stdin_builds_are_numbered_too(self):
        with self.folder() as directory:
            run(directory, "-", "-e", "inkmd", text="# One\n")
            run(directory, "-", "-e", "inkmd", "--no-rewrite", text="# Two\n")
            self.assertEqual(names(directory), ["stdin (1).pdf", "stdin.pdf"])


if __name__ == "__main__":
    unittest.main()
