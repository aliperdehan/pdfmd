"""v3.30.37: `--no-rewrite` writes `report (1).pdf` when `report.pdf` is already there."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent


def run(directory: str, *arguments: str, text: str | None = None) -> subprocess.CompletedProcess:
    empty = Path(directory) / "empty-bin"
    empty.mkdir(exist_ok=True)
    environment = {**os.environ, "PATH": str(empty), "PDFMD_CALIBRE": "", "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "",
                   "XDG_CONFIG_HOME": directory, "APPDATA": directory}           # nothing but Python: the built-in renderer builds the PDF
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


@unittest.skipIf(os.name == "nt", "executable stand-ins use shebangs")
class OtherRoutes(unittest.TestCase):
    def test_all_routes_protect_the_final_output_once(self):
        for route in ("azw3", "mobi", "typst", "html", "quarto"):
            with self.subTest(route=route), tempfile.TemporaryDirectory(prefix="pdfmd-rewrite-") as directory:
                if route == "html" and not shutil.which("pandoc"):
                    self.skipTest("needs Pandoc")
                folder = Path(directory)
                binary = folder / "bin"
                binary.mkdir()
                program = ("#!" + sys.executable + "\nimport sys\nfrom pathlib import Path\n"
                           "args = sys.argv[1:]\n"
                           "if '--version' in args: print('tool 1.0'); sys.exit()\n"
                           "name = Path(sys.argv[0]).name\n"
                           "target = args[2] if name == 'typst' else args[args.index('-o')+1] if name == 'quarto' else args[-1] if name == 'wkhtmltopdf' else args[1]\n"
                           "Path(target).write_bytes(b'%PDF-new output')\n")
                for name in ("typst", "ebook-convert", "wkhtmltopdf", "quarto"):
                    path = binary / name
                    path.write_text(program, encoding="utf-8")
                    path.chmod(0o755)
                suffix = {"typst": "typ", "html": "html", "quarto": "qmd"}.get(route, "md")
                source = folder / ("doc." + suffix)
                source.write_text("# Hello\n", encoding="utf-8")
                ext = route if route in ("azw3", "mobi") else "pdf"
                target = folder / ("out." + ext)
                target.write_bytes(b"original")
                (folder / ("out (1)." + ext)).write_bytes(b"first copy")
                env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ.get("PATH", ""),
                           PDFMD_CONFIG="", PDFMD_NO_PROMPT="1", PDFMD_CALIBRE=str(binary / "ebook-convert"))
                for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
                    env[key] = str(folder / key)
                if route in ("azw3", "mobi") and not shutil.which("pandoc"):
                    continue
                flags = ["-e", "wkhtmltopdf"] if route == "html" else []
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(source), "-o", str(target),
                                       "--no-rewrite", "--no-backup", *flags],
                                      cwd=folder, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(target.read_bytes(), b"original")
                self.assertEqual((folder / ("out (1)." + ext)).read_bytes(), b"first copy")
                self.assertTrue((folder / ("out (2)." + ext)).is_file())


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class ClassMetadata(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-output-metadata-")
        self.addCleanup(scratch.cleanup)
        self.folder = Path(scratch.name)
        (self.folder / "article.yaml").write_text("title: Article settings\n")
        (self.folder / "book.yaml").write_text("title: Book settings\n")
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                    **{"XDG_" + key + "_HOME": str(self.folder / key.lower())
                       for key in ("CONFIG", "CACHE", "DATA")}}

    def build(self, front):
        (self.folder / "paper.md").write_text("---\n" + front + "---\n\nBody.\n")
        return subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "paper.md", "--to", "latex",
                               "--no-stamp", "--no-backup", "--no-auto", "font"], cwd=self.folder,
                              env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def test_single_resolves_class_before_discovering_metadata(self):
        for key in ("documentclass", "class"):
            with self.subTest(key=key):
                done = self.build(key + ": article\n")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                text = (self.folder / "paper.tex").read_text()
                self.assertIn("Article settings", text)
                self.assertNotIn("Book settings", text)

    def test_ambiguous_metadata_keeps_the_existing_error_handling(self):
        done = self.build("title: Ambiguous\n")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Multiple YAML files", done.stderr)
        self.assertIn("use -y FILE or bare -y", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_binary_office_input_still_skips_the_frontmatter_class_read(self):
        source = self.folder / "input.docx"
        made = subprocess.run([shutil.which("pandoc"), "-f", "markdown", "-o", str(source)],
                              input="Office body.\n", cwd=self.folder, env=self.env, capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), str(source), "--to", "gfm",
                               "-y", "article.yaml", "--no-stamp", "--no-backup"], cwd=self.folder,
                              env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("only direct PDF conversion", done.stderr)
        self.assertNotIn("Traceback", done.stderr)


if __name__ == "__main__":
    unittest.main()
