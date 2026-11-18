"""Control characters in the text passed to Pandoc (3es, D85)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401
from pandoc_support import needs_pandoc  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from pdfmd_reader.controls import repair_controls  # noqa: E402


class ControlRange(unittest.TestCase):
    def test_c0_except_tab_and_line_endings(self):
        source = "".join(chr(point) for point in range(32)) + " café"
        self.assertEqual(repair_controls(source), "\t\n\n\n\r café")


@needs_pandoc(3, 1, 3)
class SourceControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pdfmd-controls-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, content):
        document = self.root / name
        document.parent.mkdir(parents=True, exist_ok=True)
        document.write_bytes(content.encode("utf-8"))
        return document

    def build(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *args,
                               "--no-stamp", "--no-backup", "--build-log", "off"],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.root,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": ""})

    def controls_warning(self, result):
        lines = [line for line in result.stderr.splitlines()
                 if line.startswith("WARN ") and "source control characters" in line]
        self.assertEqual(len(lines), 1, result.stdout + result.stderr)
        return lines[0]

    def test_repairs_once_with_original_line_numbers_and_strict_fails(self):
        original = ("---\r\npdfmd-options: {flavour: obsidian}\r\n---\r\n\r\n"
                    "Left\x00\x07right\vNext\fThird\x1b[38:2:80:60:40m colour\x1b[0m.\r\n"
                    "Line\x1f two.\r\n\r\n```\r\n\tKeep the tab.\r\n```\r\n")
        source = self.write("note.md", original)
        done = self.build("note.md", "-o", "note.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        warning = self.controls_warning(done)
        for detail in ("note.md", "line 5", "removed U+0000", "U+0007", "U+001B", "ANSI",
                       "replaced U+000B", "U+000C", "line 6", "removed U+001F"):
            self.assertIn(detail, warning)
        html = (self.root / "note.html").read_text(encoding="utf-8")
        self.assertRegex(html, r"Leftright<br\s*/?>\s*Next<br\s*/?>\s*Third colour\.")
        self.assertNotIn("[38:2:", html)
        self.assertNotIn("[0m", html)
        self.assertIn("Keep the tab.", html)
        strict = self.build("note.md", "-o", "strict.html", "--strict")
        self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)
        self.controls_warning(strict)
        self.assertTrue((self.root / "strict.html").is_file())
        self.assertEqual(source.read_bytes(), original.encode("utf-8"))

    def test_chapters_and_parts_repair_their_own_source_lines(self):
        chapter = "---\ntitle: Chapter\nchapter: 2\n---\n\nRed\x1b[31m green\x1b[0m.\n"
        for route in ("route", "patch", "parts"):
            with self.subTest(route=route):
                options = "parts: auto" if route == "parts" else f"report-build: {route}"
                self.write("first.md", f"---\ntitle: First\nchapter: 1\npdfmd-options: {{{options}}}\n---\n\nLead.\n")
                name = "parts/10-chapter.md" if route == "parts" else "second.md"
                source = self.write(name, chapter)
                args = ("first.md",) if route == "parts" else ("-r", "first.md", name)
                done = self.build(*args, "-o", "out.html")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                warning = self.controls_warning(done)
                self.assertIn(source.name, warning)
                self.assertIn("line 6", warning)
                self.assertIn("Red green.", (self.root / "out.html").read_text(encoding="utf-8"))
                self.assertEqual(source.read_bytes(), chapter.encode("utf-8"))

    def test_section_uses_repaired_heading_and_original_diagnostic_line(self):
        self.write("note.md", "---\ntitle: Sections\n---\n\n# Kee\x00p\n\nVisible.\n\n# Later\n")
        done = self.build("note#keep", "-o", "cut.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("line 5: removed U+0000", self.controls_warning(done))
        self.assertIn("Visible.", (self.root / "cut.html").read_text(encoding="utf-8"))

    def test_text_readers_besides_markdown_are_repaired(self):
        self.write("note.html", "<p>A\x1b[31m red\x1b[0m line.</p>\n")
        done = self.build("note.html", "-o", "out.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("line 1", self.controls_warning(done))
        self.assertIn("A red line.", (self.root / "out.html").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("lualatex"), "needs LuaLaTeX")
    def test_the_first_pdf_engine_succeeds(self):
        self.write("note.md", "---\ntitle: Controls\n---\n\nText with an invalid byte\x06 here.\n")
        done = self.build("note.md", "-o", "note.pdf", "--engine", "lualatex", "--engine-fallback", "off")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("removed U+0006", self.controls_warning(done))
        self.assertIn("(lualatex)", done.stdout)
        self.assertTrue((self.root / "note.pdf").read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
