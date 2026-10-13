"""v3.28.17: raw blocks and spans are not code (no code-font default for a document that only has `{=latex}`), and a
`csl: apa` finds `apa.csl` (no `not embedded` warning for a style nothing cites with)."""

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

import pdfmd  # noqa: E402

CASES = [
    ("a raw LaTeX block", "a\n\n```{=latex}\n\\x\n```\n", False),
    ("an embedded pdfmd block", "a\n\n```{=pdfmd}\nparts: x\n```\n", False),
    ("a raw HTML block in tildes", "~~~{=html}\n<b>\n~~~\n", False),
    ("a raw Typst block", "```{=typst}\n#x\n```\n", False),
    ("an inline raw span", "a `\\x`{=latex} b", False),
    ("two inline raw spans", "`a`{=latex} and `b`{=html}", False),
    ("a fence with the class pdfmd (no =) is code", "```{pdfmd}\nx\n```\n", True),
    ("inline code", "a `x` b", True),
    ("a fenced block", "```python\nx\n```\n", True),
    ("raw block, then inline code", "```{=latex}\n\\x\n```\n\nuse `y`", True),
    ("a raw block never closed", "```{=latex}\n\\x\n", True),
    ("a raw block in five backticks holding shorter fences", "`````{=latex}\n````something ```really``` odd````\n```\n`````\n", False),
    ("a raw block in four backticks holding a three-backtick line", "````{=html}\n```\n<b>\n```\n````\n", False),
    ("a raw block closed by a longer fence", "```{=latex}\n\\x\n`````\n", False),
    ("an inline raw span in two backticks holding one", "`` `some inline command` ``{=typst} text", False),
    ("an inline raw span in three backticks", "``` a`b ```{=latex}", False),
    ("code after a raw block in five backticks", "`````{=latex}\n\\x\n`````\n\n```\ncode\n```\n", True),
]


class Detection(unittest.TestCase):
    def test_what_is_code(self):
        for name, text, expected in CASES:
            with self.subTest(name):
                self.assertEqual(pdfmd.has_code_spans(text), expected)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc (the CI native job has none)")
class Builds(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="pdfmd-rawcode-"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def run_pdfmd(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.folder, env=env,
                              capture_output=True, text=True, timeout=300)

    def test_only_raw_blocks_gets_no_code_font(self):
        (self.folder / "d.md").write_text("---\ntitle: T\n---\n\n```{=latex}\n\\relax\n```\n\nText.\n", encoding="utf-8")
        done = self.run_pdfmd("d.md", "--to", "latex", "--verbose")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("AUTO MONOFONT", done.stdout)
        (self.folder / "e.md").write_text("---\ntitle: T\n---\n\nUse `code` here.\n", encoding="utf-8")
        done = self.run_pdfmd("e.md", "--to", "latex", "--verbose")
        self.assertIn("AUTO MONOFONT", done.stdout)

    def assemble(self, name: str) -> subprocess.CompletedProcess:
        return self.run_pdfmd(name, "--assemble-only", "--embed-metadata", "all", "-o", "out.md")

    def test_a_style_named_without_its_suffix_is_found(self):
        (self.folder / "apa.csl").write_text('<style xmlns="http://purl.org/net/xbiblio/csl"><info/></style>\n',
                                             encoding="utf-8")
        (self.folder / "d.md").write_text("---\ntitle: T\ncsl: apa\nbibliography: refs.bib\n---\n\nSee @k.\n",
                                          encoding="utf-8")
        (self.folder / "refs.bib").write_text("@book{k, title={T}, author={A, B}, year={2000}}\n", encoding="utf-8")
        done = self.assemble("d.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("not embedded: apa", done.stderr)
        self.assertIn("apa.csl", (self.folder / "out.md").read_text(encoding="utf-8"))

    def test_a_missing_style_warns_only_when_the_document_cites(self):
        (self.folder / "d.md").write_text("---\ntitle: T\ncsl: nowhere\n---\n\nNo citations.\n", encoding="utf-8")
        done = self.assemble("d.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("not embedded", done.stderr)
        (self.folder / "c.md").write_text("---\ntitle: T\ncsl: nowhere\nbibliography: refs.bib\n---\n\nSee @k.\n",
                                          encoding="utf-8")
        (self.folder / "refs.bib").write_text("@book{k, title={T}, author={A, B}, year={2000}}\n", encoding="utf-8")
        done = self.assemble("c.md")
        self.assertIn("not embedded: nowhere", done.stderr)


if __name__ == "__main__":
    unittest.main()
