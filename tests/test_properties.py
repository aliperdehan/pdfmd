"""Visible front-matter properties through the checkout's Pandoc build routes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
PANDOC = shutil.which("pandoc")
LATEX = next((engine for engine in ("pdflatex", "xelatex", "lualatex") if shutil.which(engine)), None)

FRONT = """title: Test title
stage: Review
tags: [sample, '#trial']
signed: TRUE
released: 2026-11-25
counts: [one, two]
sample: {batch: Q9}
empty: ""
cssclasses: example-css
lang: en
"""


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Properties(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.config = self.root / "user.yaml"
        self.config.write_text("options: {soffice-timeout: 0}\n", encoding="utf-8")
        self.source = self.root / "source.md"
        self.env = {**os.environ, "PDFMD_CONFIG": str(self.config), "PDFMD_NO_PROMPT": "1"}

    def document(self, options: str = "{show: true}", front: str = FRONT):
        self.source.write_text(f"---\n{front}pdfmd-options: {{properties: {options}}}\n---\n\nBody marker.\n",
                               encoding="utf-8")

    def build(self, writer: str, *args, suffix: str | None = None) -> Path:
        target = self.root / f"out.{suffix or writer}"
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(self.source),
                               "--to", writer, "-o", str(target), *args],
                              cwd=self.root, env=self.env, capture_output=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(target.is_file(), done.stdout + done.stderr)
        return target

    def test_html_has_a_two_column_table_after_the_title(self):
        self.document()
        output = self.build("html", "--standalone").read_text(encoding="utf-8")
        self.assertLess(output.index("Test title</h1>"), output.index('class="pdfmd-properties"'))
        block = output.split('class="pdfmd-properties"', 1)[1].split("</div>", 1)[0]
        for content in ("<table", "stage", "Review", "#sample", "#trial", "TRUE", "2026-11-25", "one, two", "sample.batch", "Q9"):
            self.assertIn(content, block)
        for hidden in ("empty", "cssclasses", "pdfmd-options", "Test title", "<td>lang</td>"):
            self.assertNotIn(hidden, block)
        self.assertLess(output.index('class="pdfmd-properties"'), output.index("Body marker."))

    def test_explicit_key_order_labels_hide_inline_and_end(self):
        self.document("{show: [tags, stage, signed, released, sample.batch], hide: [signed], "
                      "labels: {stage: Phase}, style: inline, place: end}")
        output = self.build("html").read_text(encoding="utf-8")
        self.assertLess(output.index("Body marker."), output.index('class="pdfmd-properties"'))
        self.assertIn("#sample #trial · Phase Review · 2026-11-25 · sample.batch Q9", output)
        self.assertNotIn("TRUE", output)

    def test_show_all_includes_hidden_and_empty_keys_and_list_style(self):
        self.document("{show: all, style: list}")
        output = self.build("html").read_text(encoding="utf-8")
        block = output.split('class="pdfmd-properties"', 1)[1].split("</div>", 1)[0]
        for content in ("<ul>", "title", "Test title", "lang", "cssclasses", "pdfmd-options.properties.show", "empty"):
            self.assertIn(content, block)

    def test_no_front_matter_or_show_off_gives_no_block(self):
        self.config.write_text("options: {soffice-timeout: 0, properties: {show: true}}\n", encoding="utf-8")
        self.source.write_text("Body marker.\n", encoding="utf-8")
        self.assertNotIn('class="pdfmd-properties"', self.build("html").read_text(encoding="utf-8"))
        self.document("{show: false}")
        self.assertNotIn('class="pdfmd-properties"', self.build("html").read_text(encoding="utf-8"))

    def test_kit_keys_are_hidden_and_folder_settings_are_inherited(self):
        kit = self.root / "kit"
        kit.mkdir()
        (kit / ".kit").write_text("kit-format: 1\nname: sample\nlatex-keys: {stage: Phase}\n", encoding="utf-8")
        folder = self.root / ".pdfmd"
        folder.mkdir()
        (folder / "config.yaml").write_text("options: {properties: {show: true}}\n", encoding="utf-8")
        self.source.write_text(f"---\n{FRONT}---\n\nBody marker.\n", encoding="utf-8")
        output = self.build("html", "--kit", str(kit)).read_text(encoding="utf-8")
        self.assertIn('class="pdfmd-properties"', output)
        self.assertNotIn("Review", output)

    def test_latex_and_typst_have_writer_hooks_and_gfm_has_content(self):
        self.document()
        for writer, suffix, token in (
            ("latex", "tex", r"\begin{pdfmdproperties}"),
            ("typst", "typ", "#pdfmd-properties["),
            ("gfm", "md", "Review"),
        ):
            with self.subTest(writer=writer):
                value = self.build(writer, suffix=suffix).read_text(encoding="utf-8")
                self.assertIn(token, value)
                self.assertLess(value.index("Review"), value.index("Body marker."))

    def test_typst_template_can_redefine_the_properties_function(self):
        self.document()
        template = self.root / "style.typst"
        template.write_text("$for(header-includes)$\n$header-includes$\n$endfor$\n"
                            "#let pdfmd-properties(body) = [Styled #body]\n$body$\n", encoding="utf-8")
        output = self.build("typst", "--standalone", "--template", str(template), suffix="typ").read_text(encoding="utf-8")
        self.assertLess(output.index("#let pdfmd-properties(body) = body"), output.index("[Styled #body]"))
        self.assertLess(output.index("[Styled #body]"), output.index("#pdfmd-properties["))

    @unittest.skipUnless(shutil.which("typst") and shutil.which("pdftotext"), "needs Typst and pdftotext")
    def test_typst_pdf_shows_the_properties(self):
        self.document()
        pdf = self.build("pdf", "--engine", "typst", "--no-stamp", "--engine-fallback", "off")
        extracted = subprocess.run(["pdftotext", str(pdf), "-"], check=True, capture_output=True, encoding="utf-8").stdout
        self.assertLess(extracted.index("Review"), extracted.index("Body marker."))

    def test_docx_applies_the_properties_style(self):
        self.document()
        with zipfile.ZipFile(self.build("docx")) as docx:
            document = docx.read("word/document.xml").decode("utf-8")
            styles = docx.read("word/styles.xml").decode("utf-8")
        self.assertIn('w:val="Properties"', styles)
        self.assertIn('w:pStyle w:val="Properties"', document)
        self.assertIn("Review", document)

    @unittest.skipUnless(LATEX and shutil.which("pdftotext"), "needs LaTeX and pdftotext")
    def test_latex_pdf_shows_the_properties(self):
        self.document()
        pdf = self.build("pdf", "--engine", LATEX, "--no-stamp", "--engine-fallback", "off")
        extracted = subprocess.run(["pdftotext", str(pdf), "-"], check=True, capture_output=True, encoding="utf-8").stdout
        self.assertLess(extracted.index("Test title"), extracted.index("Review"))
        self.assertLess(extracted.index("Review"), extracted.index("Body marker."))

    def test_slides_require_properties_in_the_document(self):
        folder = self.root / ".pdfmd"
        folder.mkdir()
        (folder / "config.yaml").write_text("options: {properties: {show: true}}\n", encoding="utf-8")
        self.config.write_text("options: {soffice-timeout: 0, properties: {show: true, style: inline}}\n", encoding="utf-8")
        for writer, suffix in (("beamer", "tex"), ("revealjs", "html"), ("pptx", "pptx")):
            with self.subTest(writer=writer):
                for own in (False, True):
                    if own:
                        self.document("{show: true, style: inline}", front="stage: Review\n")
                    else:
                        self.source.write_text("---\nstage: Review\n---\n\n# A slide\n\nBody marker.\n", encoding="utf-8")
                    path = self.build(writer, "--no-self-contained", suffix=suffix)
                    if writer == "pptx":
                        with zipfile.ZipFile(path) as pptx:
                            body = "".join(pptx.read(name).decode("utf-8") for name in pptx.namelist()
                                           if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
                    else:
                        body = path.read_text(encoding="utf-8")
                    self.assertEqual("Review" in body, own, writer)
