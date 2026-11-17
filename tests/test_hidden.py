"""Plain hidden content is read by filters, then removed from each output."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402


class Hidden(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pdfmd-hidden-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.source = self.folder / "doc.md"

    def build(self, writer, text, *flags):
        self.source.write_text(text, encoding="utf-8")
        output = self.folder / ("out." + writer)
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), str(self.source),
                               "--to", writer, "--no-backup", "--no-stamp", "-o", str(output), *flags],
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"},
                              capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        if output.read_bytes().startswith(b"%PDF"):
            import pypdf
            text = "\n".join(page.extract_text() for page in pypdf.PdfReader(output).pages)
        elif writer in ("docx", "odt", "epub"):
            with zipfile.ZipFile(output) as archive:
                text = "\n".join(archive.read(name).decode("utf-8", errors="replace") for name in archive.namelist()
                                 if name.endswith((".xml", ".xhtml", ".html")))
        else:
            text = output.read_text(encoding="utf-8")
        return text, done

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_every_writer_drops_blocks_and_spans_after_calc_reads_them(self):
        document = ("---\ntitle: Hidden test\n---\n\nVisible.\n\n::: hide\nSecretblock\n\n"
                    "`x = 40`{=}\n\n::: calc\n`y = 2`{=}\n:::\n\n:::\n\n"
                    "Outside `x+y`{=}. [Secretspan]{.hide}\n\n::: hide\nSecretalias\n:::\n")
        for writer in ("html", "latex", "typst", "docx", "odt", "epub", "gfm", "txt", "ansi"):
            with self.subTest(writer=writer):
                text, done = self.build(writer, document)
                self.assertNotIn("Secret", text)
                self.assertIn("42", text)
                self.assertNotIn("undefined", done.stderr)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_show_hidden_from_flag_and_metadata_keeps_calc_hide_silent(self):
        body = ("::: {.hide}\nAnswerkey\n:::\n\n[Spankey]{.hide}\n\n"
                "::: {.calc .hide}\nx = 42\n:::\n\nValue `x`{=}.\n")
        for front, flags in (("", ("--show-hidden",)), ("pdfmd-options: {show-hidden: true}\n", ())):
            with self.subTest(front=front):
                text, _ = self.build("html", "---\ntitle: T\n" + front + "---\n\n" + body, *flags)
                self.assertIn("Answerkey", text)
                self.assertIn("Spankey", text)
                self.assertIn("42", text)
                self.assertNotIn("x = 42", text)
                self.assertNotIn('class="hide"', text)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_referenced_hidden_labels_warn_once(self):
        text, done = self.build("html", "---\ntitle: T\n---\n\n::: {.hide #answer}\nSecret\n:::\n\n"
                               "[See](#answer) and [again](#answer).\n")
        self.assertNotIn("Secret", text)
        self.assertEqual((done.stdout + done.stderr).count("WARN  hidden:"), 1, done.stdout + done.stderr)
        self.assertIn("answer", done.stdout + done.stderr)
        _, shown = self.build("html", self.source.read_text(), "--show-hidden")
        self.assertNotIn("WARN  hidden:", shown.stdout + shown.stderr)

    def test_native_normalisation_drops_nested_hidden_content_but_keeps_code_examples(self):
        body = ("Visible\n\n::: hide\nSecret\n\n::: note\nNestedsecret\n:::\n:::\n\n"
                "A [Secretspan]{.hide}.\n\n```markdown\n::: hide\nExample\n:::\n```\n")
        self.source.write_text(body)
        source, _ = pdfmd.normalise_gfm(body, "inkmd", source_path=self.source)
        self.assertNotIn("Secret", source.text)
        self.assertNotIn("Nestedsecret", source.text)
        self.assertIn("Example", source.text)
        self.assertIn("Visible", source.text)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_no_front_matter_lists_parts_and_filter_reading(self):
        # The document's own filter sees hidden text; code examples stay literal.
        (self.folder / "doc.lua").write_text(
            'return {{Pandoc = function(doc) local text = pandoc.utils.stringify(doc); '
            'if text:find("Secret", 1, true) then doc.blocks:insert(pandoc.Para({pandoc.Str("Readfirst")})) end; '
            'return doc end}}')
        text, _ = self.build("html", "::: hide\nSecret\n:::\n\n- Item\n\n  ::: hide\n  Secretnested\n  :::\n\n"
                             "```markdown\n::: hide\nExample\n:::\n```\n")
        self.assertNotIn("Secret", text)
        self.assertIn("Readfirst", text)
        self.assertIn("Example", text)

    @unittest.skipUnless(shutil.which("pandoc") and shutil.which("typst"), "needs Pandoc and Typst")
    def test_typst_pdf_and_reference_link(self):
        import pypdf
        self.source.write_text("---\ntitle: T\n---\n\n::: {.hide #answer}\nSecret\n:::\n\n[See](#answer). Visible\n")
        output = self.folder / "out.pdf"
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), str(self.source), "-e", "typst",
                               "--no-backup", "--no-stamp", "-o", str(output)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = "\n".join(page.extract_text() for page in pypdf.PdfReader(output).pages)
        self.assertNotIn("Secret", text)
        self.assertIn("Visible", text)
        self.assertEqual((done.stdout + done.stderr).count("WARN  hidden:"), 1, done.stdout + done.stderr)

    def test_source_ranges_preserve_calc_hide_code_and_other_attributes(self):
        from pdfmd_filters.hidden import strip_hidden
        text = ("::: {.calc .hide}\nx = 2\n:::\n\n::: hide\nAnswer\n:::\n\n"
                "[outer [inner]{.strong} secret]{.hide} [kept]{.strong}\n\n"
                "`[example]{.hide}`\n\n    ::: hide\n    Codeexample\n    :::\n")
        stripped = strip_hidden(text)
        self.assertNotIn("Answer", stripped)
        self.assertNotIn("secret", stripped)
        for kept in ("x = 2", "[kept]{.strong}", "`[example]{.hide}`", "Codeexample"):
            self.assertIn(kept, stripped)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_reference_link_and_latex_reference_forms(self):
        for ref in ("[See][a]\n\n[a]: #answer", r"\ref{answer}", r"\cref{answer}"):
            with self.subTest(ref=ref):
                _, done = self.build("html", "---\ntitle: T\n---\n\n::: {.hide #answer}\nSecret\n:::\n\n" + ref)
                self.assertEqual((done.stdout + done.stderr).count("WARN  hidden:"), 1, done.stdout + done.stderr)

    @unittest.skipUnless(shutil.which("quarto"), "needs Quarto")
    def test_quarto_drops_plain_hidden_content_after_execution(self):
        self.source = self.folder / "analysis.qmd"
        for writer in ("html", "typst"):
            with self.subTest(writer=writer):
                text, _ = self.build(writer, "---\ntitle: T\n---\n\n::: hide\nSecret\n\n`x = 42`{=}\n:::\n\n"
                                     "Visible `x`{=}. [Secretspan]{.hide}\n")
                self.assertNotIn("Secret", text)
                self.assertIn("42", text)
                self.assertIn("Visible", text)

    def test_native_show_hidden_prints_ordinary_span_text(self):
        body = "---\npdfmd-options: {show-hidden: true}\n---\n\n[Answer]{.hide}\n"
        self.source.write_text(body)
        for path in (None, self.source):
            source, _ = pdfmd.normalise_gfm(body, "inkmd", source_path=path)
            self.assertEqual(source.text.strip(), "Answer")


    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_plain_hidden_is_ordinary_in_every_writer_and_calc_alias_stays_silent(self):
        document = ("---\ntitle: T\n---\n\n::: {.hidden #ordinary}\nOrdinaryblock\n:::\n\n"
                    "[Ordinaryspan]{.hidden} [see](#ordinary).\n\n::: hidden\nOrdinaryshort\n:::\n\n"
                    "::: {.calc .hidden}\nx = 42\n:::\n\nValue `x`{=}.\n")
        for writer in ("html", "latex", "typst", "docx", "odt", "epub", "gfm", "txt", "ansi"):
            with self.subTest(writer=writer):
                text, done = self.build(writer, document)
                for kept in ("Ordinaryblock", "Ordinaryspan", "Ordinaryshort", "42"):
                    self.assertIn(kept, text)
                self.assertNotIn("x = 42", text)
                self.assertNotIn("WARN  hidden:", done.stdout + done.stderr)
        for flags in ((), ("--show-hidden",)):
            text, _ = self.build("html", document, *flags)
            self.assertIn('class="hidden"', text)
            self.assertIn('id="ordinary"', text)

    def test_hidden_survives_native_and_source_stripping(self):
        from pdfmd_filters.hidden import strip_hidden, reveal_hidden
        body = "::: {.hidden}\nOrdinaryblock\n:::\n\n[Ordinaryspan]{.hidden}\n"
        self.assertEqual(strip_hidden(body), body)
        self.assertEqual(reveal_hidden(body), body)
        for shown in (False, True):
            self.source.write_text("---\npdfmd-options: {show-hidden: " + str(shown).lower() + "}\n---\n" + body)
            for path in (None, self.source):
                source, _ = pdfmd.normalise_gfm(self.source.read_text(), "inkmd", source_path=path)
                self.assertIn("Ordinaryblock", source.text)
                self.assertIn("Ordinaryspan", source.text)

    @unittest.skipUnless(shutil.which("pandoc") and shutil.which("pdflatex"), "needs Pandoc and pdfLaTeX")
    def test_quarto_math_macro_shape_survives_html_latex_and_pdf(self):
        body = "---\ntitle: T\n---\n\n::: {.hidden}\n$$ \\def\\RR{{\\bf R}} $$\n:::\n\nUse $\\RR$.\n"
        for writer in ("html", "latex"):
            with self.subTest(writer=writer):
                text, _ = self.build(writer, body, "--from", "markdown-latex_macros", "--mathjax")
                self.assertIn(r"\def\RR", text)
                self.assertIn(r"\RR", text)
        # A display scopes TeX's \def locally even before pdfmd 3.33.290. Use its global form for a later formula.
        text, _ = self.build("pdf", body.replace(r"\def", r"\gdef"), "-e", "pdflatex",
                             "--engine-fallback", "missing", "--no-cache")
        self.assertIn("Use", text)
        self.assertIn("R", text)
