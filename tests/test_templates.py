"""`pdfmd --init`: a new document from a template (v3.26.17)."""

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

import pdfmd_templates  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402


class Package(unittest.TestCase):
    def test_the_built_in_templates_are_described(self):
        names = pdfmd_templates.builtin()
        self.assertEqual(sorted(names), ["article", "book", "notes", "report", "slides"])
        for name, folder in names.items():
            self.assertTrue(pdfmd_templates.describe(folder), name)
            self.assertTrue((folder / "next.txt").is_file(), name)

    def test_placeholders_are_filled_and_others_left_alone(self):
        values = {"name": "n", "title": "T", "author": "A", "date": "D", "year": "Y"}
        self.assertEqual(pdfmd_templates.fill("{{title}} {{ author }} {{unknown}} {{{{name}}}}", values),
                         "T A {{unknown}} {{n}}")

    def test_nothing_that_exists_is_touched(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "x"
            values = {"name": "x", "title": "X", "author": "A", "date": "D", "year": "Y"}
            written = pdfmd_templates.create(pdfmd_templates.builtin()["article"], target, values)
            self.assertEqual(sorted(path.name for path in written), ["refs.bib", "x.md"])
            (target / "x.md").write_text("mine", encoding="utf-8")
            with self.assertRaises(pdfmd_templates.TemplateError) as raised:
                pdfmd_templates.create(pdfmd_templates.builtin()["article"], target, values)
            self.assertIn("x.md", str(raised.exception))
            self.assertEqual((target / "x.md").read_text(encoding="utf-8"), "mine")


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-init-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.config = self.directory / "config"
        self.config.mkdir()

    def run_pdfmd(self, *arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.config), "APPDATA": str(self.config),
                       "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=cwd or self.directory, env=environment)

    def test_the_list(self):
        done = self.run_pdfmd("--init")
        self.assertEqual(done.returncode, 0, done.stderr)
        for name in ("article", "report", "notes", "slides", "book"):
            self.assertRegex(done.stdout, rf"(?m)^  {name}\s+\S")

    def test_a_template_becomes_a_folder_with_the_values_filled_in(self):
        done = self.run_pdfmd("--init", "article", "my-paper", "-V", "author=A. Author", "-V", "title=On Rates")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("CREATED  my-paper", done.stdout)
        self.assertIn("NEXT     cd my-paper && pdfmd my-paper", done.stdout)
        text = (self.directory / "my-paper" / "my-paper.md").read_text(encoding="utf-8")
        self.assertIn('title: "On Rates"', text)
        self.assertIn('author: "A. Author"', text)
        self.assertNotIn("{{", text)
        self.assertTrue((self.directory / "my-paper" / "refs.bib").is_file())
        again = self.run_pdfmd("--init", "article", "my-paper")
        self.assertEqual(again.returncode, 1)
        self.assertIn("already exist", again.stderr)

    def test_the_title_comes_from_the_name_and_the_date_is_today(self):
        self.run_pdfmd("--init", "notes", "thermo_lecture-3")
        text = (self.directory / "thermo_lecture-3" / "thermo_lecture-3.md").read_text(encoding="utf-8")
        self.assertIn('title: "Thermo Lecture 3"', text)
        self.assertRegex(text, r'date: "\d{4}-\d\d-\d\d"')

    def test_into_the_current_folder(self):
        done = self.run_pdfmd("--init", "report", ".")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "data.csv").is_file())
        self.assertEqual(len(list(self.directory.glob("*.md"))), 1)

    def test_unknown_template(self):
        done = self.run_pdfmd("--init", "nonsense")
        self.assertEqual(done.returncode, 1)
        self.assertIn("No template called 'nonsense'", done.stderr)
        self.assertIn("article", done.stderr)

    def test_your_own_templates(self):
        folder = self.config / "pdfmd" / "templates"
        (folder / "lab").mkdir(parents=True)
        (folder / "lab" / "__name__.md").write_text("---\ntitle: {{title}} ({{year}})\n---\n\nLab.\n", encoding="utf-8")
        (folder / "lab" / "description.txt").write_text("my lab sheet\n", encoding="utf-8")
        (folder / "memo.md").write_text("# {{title}}\n\nTo: {{author}}\n", encoding="utf-8")
        listing = self.run_pdfmd("--init").stdout
        self.assertRegex(listing, r"(?m)^  lab\s+my lab sheet  \(yours\)")
        self.assertRegex(listing, r"(?m)^  memo\s+one Markdown file  \(yours\)")
        done = self.run_pdfmd("--init", "lab", "sheet-1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex((self.directory / "sheet-1" / "sheet-1.md").read_text(encoding="utf-8"), r"title: Sheet 1 \(\d{4}\)")
        self.assertFalse((self.directory / "sheet-1" / "description.txt").exists())
        done = self.run_pdfmd("--init", "memo", "note-to-self", "-V", "author=Me")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((self.directory / "note-to-self.md").read_text(encoding="utf-8"), "# Note To Self\n\nTo: Me\n")

    def test_a_template_named_by_path(self):
        source = self.directory / "mine"
        source.mkdir()
        (source / "__name__.md").write_text("# {{name}}\n", encoding="utf-8")
        (source / "extra.csv").write_text("a,b\n", encoding="utf-8")
        done = self.run_pdfmd("--init", str(source), "fresh")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((self.directory / "fresh" / "fresh.md").read_text(encoding="utf-8"), "# fresh\n")
        self.assertTrue((self.directory / "fresh" / "extra.csv").is_file())

    def test_every_template_checks_clean(self):
        for name in pdfmd_templates.builtin():
            with self.subTest(name):
                made = self.run_pdfmd("--init", name, f"t-{name}")
                self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
                checked = self.run_pdfmd(f"t-{name}/t-{name}.md", "--check", "--strict")
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    @needs_pandoc(3, 1, 3)
    def test_every_template_builds(self):
        for name in pdfmd_templates.builtin():
            with self.subTest(name):
                self.run_pdfmd("--init", name, f"b-{name}")
                document = f"b-{name}/b-{name}.md"
                if name == "slides":
                    done = self.run_pdfmd(document, "-p", "--stop-at", "tex")
                    produced = self.directory / f"b-{name}" / f"b-{name}.tex"
                else:
                    done = self.run_pdfmd(document, "-t", "html", "--strict")
                    produced = self.directory / f"b-{name}" / f"b-{name}.html"
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertTrue(produced.is_file(), done.stdout)
        html = (self.directory / "b-report" / "b-report.html").read_text(encoding="utf-8")
        self.assertIn("0.45", html)                                       # the table came from data.csv
        self.assertIn("Knuth", (self.directory / "b-article" / "b-article.html").read_text(encoding="utf-8"))
        book = (self.directory / "b-book" / "b-book.html").read_text(encoding="utf-8")
        self.assertIn("Materials", book)                                  # the chapters were joined


if __name__ == "__main__":
    unittest.main()
