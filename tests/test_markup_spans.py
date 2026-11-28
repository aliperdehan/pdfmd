"""Named universal markup spans through pdfmd's Pandoc writers."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

from pandoc_support import ODF, PANDOC_VERSION, WORD, needs_pandoc, office_markup  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "- [Café *mixed* `case`]{.caps}; [a *wave*]{#sample .wavy}\n- > [a dot]{.dotted}\n"


@needs_pandoc(3, 1, 3)
class NamedSpans(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="pdfmd-spans-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def build(self, suffix, *options, source=SOURCE):
        path = self.root / "note.md"
        path.write_text(source, encoding="utf-8")
        output = self.root / ("output." + suffix)
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(path),
                                 "-o", str(output), "--no-stamp", "--no-backup", *options],
                                cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=60,
                                env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return output

    def test_html_preserves_inline_structure_and_supports_switching_the_spans_off(self):
        html = self.build("html").read_text(encoding="utf-8")
        self.assertIn("CAFÉ <em>MIXED</em> <code>case</code>", html)
        self.assertIn('id="sample"', html)
        self.assertRegex(html, r'text-decoration-style: wavy">a\s+<em>wave</em>')
        self.assertRegex(html, r'text-decoration-style: dotted">a\s+dot')
        for options in (("--no-markup",), ("--markup", "highlight"), ("--flavour", "pandoc")):
            with self.subTest(options=options):
                disabled = self.build("html", *options).read_text(encoding="utf-8")
                self.assertIn("Café <em>mixed</em> <code>case</code>", disabled)
                self.assertNotIn("text-decoration-style:", disabled)
        opted_in = self.build("html", "--flavour", "pandoc", "--markup", "spans").read_text(encoding="utf-8")
        self.assertIn("text-decoration-style: dotted", opted_in)

    def test_latex_and_typst_keep_the_text_and_use_their_underline_commands(self):
        latex = self.build("tex").read_text(encoding="utf-8")
        self.assertIn(r"\pdfmdwavy{a \emph{wave}}", latex)
        self.assertIn(r"\pdfmddotted{a dot}", latex)
        self.assertIn(r"\IfFileExists{ulem.sty}", latex)
        typst = self.build("typ").read_text(encoding="utf-8")
        self.assertIn("#underline[a #emph[wave]]", typst)
        self.assertIn('#underline(stroke: (dash: "dotted"))[a dot]', typst)

    def test_latex_header_accounts_for_a_span_in_a_split_document_part(self):
        parts = self.root / "parts"
        parts.mkdir()
        (parts / "10-first.md").write_text("# Part\n\n[A word]{.caps .dotted}.\n", encoding="utf-8")
        source = "---\ntitle: Example\npdfmd-options: {parts: auto}\n---\n\nBefore the parts.\n"
        latex = self.build("tex", source=source).read_text(encoding="utf-8")
        self.assertIn(r"\pdfmddotted{A WORD}", latex)
        self.assertIn(r"\IfFileExists{ulem.sty}", latex)

    def test_word_and_opendocument_carry_the_underline_styles(self):
        for writer in ("docx", "odt"):
            with self.subTest(writer=writer):
                document, styles = office_markup(str(self.root), SOURCE, writer)
                legacy_odt = writer == "odt" and PANDOC_VERSION < (3, 2)
                if legacy_odt:
                    paragraphs = document.findall(".//office:text//text:p", ODF)
                    self.assertEqual(["".join(para.itertext()) for para in paragraphs], ["CAFÉ MIXED case; a wave", "a dot"])
                    emphasis = document.findall(".//text:span[@text:style-name='Emphasis']", ODF)
                    self.assertEqual(["".join(span.itertext()) for span in emphasis], ["MIXED", "wave"])
                for name, line in (("PdfmdWavy", "wave"), ("PdfmdDotted", "dotted")):
                    if writer == "docx":
                        style = styles.find(f".//w:style[@w:styleId='{name}']/w:rPr/w:u", WORD)
                        self.assertIsNotNone(style)
                        self.assertEqual(style.get(f"{{{WORD['w']}}}val"), line)
                        self.assertIsNotNone(document.find(f".//w:rStyle[@w:val='{name}']", WORD))
                    else:
                        style = styles.find(f".//style:style[@style:name='{name}']", ODF)
                        span = document.find(f".//text:span[@text:style-name='{name}']", ODF)
                        if legacy_odt:
                            self.assertIsNone(style)
                            self.assertIsNone(span)
                        else:
                            self.assertIsNotNone(style)
                            properties = style.find("style:text-properties", ODF)
                            self.assertIsNotNone(properties)
                            self.assertEqual(properties.get(f"{{{ODF['style']}}}text-underline-style"), line)
                            self.assertIsNotNone(span)

    def test_epub_carries_the_style_and_flat_text_keeps_the_words(self):
        with zipfile.ZipFile(self.build("epub")) as epub:
            content = "".join(epub.read(name).decode("utf-8") for name in epub.namelist() if name.endswith(".xhtml"))
        self.assertIn("text-decoration-style: wavy", content)
        self.assertIn("text-decoration-style: dotted", content)
        plain = self.build("txt").read_text(encoding="utf-8")
        for words in ("CAFÉ MIXED case", "a wave", "a dot"):
            self.assertIn(words, plain)
        self.assertNotIn("{.dotted}", plain)

    def test_markdown_keeps_the_named_spans_for_rebuilding(self):
        for writer in ("markdown", "commonmark_x"):
            with self.subTest(writer=writer):
                markdown = self.build("md", "--to", writer).read_text(encoding="utf-8")
                self.assertIn("[a *wave*]{#sample .wavy}", markdown)
                self.assertIn("[a dot]{.dotted}", markdown)

    def test_adaptive_reader_recognises_attribute_spacing_and_class_assignment(self):
        source = '[Two Words]{ .caps } and [a wave]{class="wavy"}.\n'
        html = self.build("html", source=source).read_text(encoding="utf-8")
        self.assertIn("TWO WORDS", html)
        self.assertIn("text-decoration-style: wavy", html)
        tex = self.build("tex", source=source).read_text(encoding="utf-8")
        self.assertIn(r"\pdfmdwavy{a wave}", tex)


if __name__ == "__main__":
    unittest.main()
