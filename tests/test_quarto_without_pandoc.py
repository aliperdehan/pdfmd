"""Quarto HTML dispatch does not depend on a standalone Pandoc executable."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401
from env_support import hidden_tools  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipIf(os.name == "nt", "the stand-in uses a POSIX launcher")
class QuartoWithoutPandoc(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.folder = Path(self.scratch.name)
        self.bin = self.folder / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, **hidden_tools(self.bin), "PATH": str(self.bin),
                    "XDG_CONFIG_HOME": str(self.folder / "config"), "XDG_CACHE_HOME": str(self.folder / "cache"),
                    "XDG_DATA_HOME": str(self.folder / "data"), "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
        self.env["LOCALAPPDATA"] = self.env["XDG_CACHE_HOME"]
        (self.folder / "analysis.qmd").write_text("---\ntitle: Analysis\n---\n\nHello.\n", encoding="utf-8")

    def run_pdfmd(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *arguments, "--no-stamp", "--no-backup"],
                              cwd=self.folder, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def test_explicit_and_implied_html_render_with_quarto_alone(self):
        tool = self.bin / "quarto"
        tool.write_text(f"#!{sys.executable}\n" +
                        "import sys\nfrom pathlib import Path\n"
                        "assert sys.argv[1:3] == ['render', 'analysis.qmd']\n"
                        "assert sys.argv[sys.argv.index('--to')+1] == 'html'\n"
                        "Path(sys.argv[sys.argv.index('-o')+1]).write_text('<p>Quarto result</p>')\n", encoding="utf-8")
        tool.chmod(0o755)
        for arguments in (("--to", "html", "-o", "explicit.html"), ("-o", "implied.html")):
            with self.subTest(arguments=arguments):
                done = self.run_pdfmd("analysis.qmd", *arguments)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual((self.folder / arguments[-1]).read_text(), "<p>Quarto result</p>")
                self.assertIn("quarto", done.stdout)

    def test_hidden_content_filters_reach_quartos_pandoc(self):
        tool = self.bin / "quarto"
        tool.write_text(f"#!{sys.executable}\n" +
                        "import sys\nfrom pathlib import Path\n"
                        "filters = [sys.argv[i+1] for i, word in enumerate(sys.argv) if word == '--lua-filter']\n"
                        "assert Path(filters[0]).name == 'hidden_mark.lua'\n"
                        "assert Path(filters[-1]).name == 'hidden.lua'\n"
                        "Path(sys.argv[sys.argv.index('-o')+1]).write_text('<p>Visible</p>')\n", encoding="utf-8")
        tool.chmod(0o755)
        done = self.run_pdfmd("analysis.qmd", "--to", "html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_missing_quarto_names_quarto(self):
        done = self.run_pdfmd("analysis.qmd", "--to", "html")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Quarto was not found", done.stdout + done.stderr)
        self.assertNotIn("Pandoc was not found", done.stdout + done.stderr)

    def test_non_quarto_html_still_requires_pandoc(self):
        (self.folder / "document.md").write_text("Hello.\n", encoding="utf-8")
        done = self.run_pdfmd("document.md", "--to", "html")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Pandoc was not found", done.stdout + done.stderr)

    def test_pdf_records_the_actual_tex_banner_and_a_retained_log(self):
        tool = self.bin / "quarto"
        tool.write_text(f"#!{sys.executable}\n" +
                        "import sys\nfrom pathlib import Path\n"
                        "if '--version' in sys.argv:\n    print('1.0')\n    sys.exit(0)\n"
                        "print('  This is pdfTeX, Version 1 (TeX Live 2026)')\n"
                        "Path('analysis.log').write_text('Package: sample 2026/01/01 v1.2 Sample\\n')\n"
                        "Path('analysis.pdf').write_bytes(b'%PDF-sample')\n", encoding="utf-8")
        tool.chmod(0o755)
        done = self.run_pdfmd("analysis.qmd", "--build-log", "on")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        record, = (self.folder / "cache" / "pdfmd" / "builds").rglob("*.log")
        text = record.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^CMD  .*\bquarto['\"]? render")
        self.assertIn("TeX Live year: 2026", text)
        self.assertIn("LaTeX package: sample 2026/01/01 v1.2", text)
