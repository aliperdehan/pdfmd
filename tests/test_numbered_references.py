"""Synthetic builds for trailing numbered references (D112)."""

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

from pandoc_support import needs_pandoc  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = """A later source [10], then [3]. Compare [[3]](https://example.org/three)[4] and [3, 10].
The range [3-4] includes both. Keep `[99]` and $a[99]$.

## Sources

[3]: [A *written* title](https://example.org/three)
4. A label — https://example.net/four
10. https://example.com/ten
"""


@needs_pandoc(3, 1, 3)
class NumberedReferences(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.source = self.folder / "source.md"

    def build(self, target, text=SOURCE, *args):
        self.source.write_text(text, encoding="utf-8")
        suffix = {"markdown": "md", "gfm": "md", "gfm+raw": "md", "plain": "txt", "latex": "tex",
                  "beamer": "tex", "context": "tex", "typst": "typ", "ansi": "txt"}.get(target, target)
        output = self.folder / f"result.{suffix}"
        done = self.run_pdfmd(str(self.source), "--to", target, "-o", str(output), *args)
        return output, done

    def run_pdfmd(self, *args):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *args], cwd=self.folder,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"}, capture_output=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def test_html_keeps_numbers_and_written_entry_links(self):
        output, done = self.build("html")
        text = output.read_text(encoding="utf-8")
        self.assertIn('data-cites="example-com-10">[10]', text)
        self.assertIn('data-cites="example-org-3">[3]', text)
        self.assertIn('data-cites="example-org-3 example-net-4">[3], [4]', text)
        self.assertIn('<code>[99]</code>', text)
        self.assertIn('<a href="https://example.org/three">A <em>written</em> title</a>', text)
        self.assertIn('href="https://example.com/ten"', text)
        self.assertLess(text.index('id="ref-example-org-3"'), text.index('id="ref-example-com-10"'))
        self.assertNotIn("citation not found", done.stderr)

    def test_markdown_is_citable_source(self):
        output, _ = self.build("markdown")
        text = output.read_text(encoding="utf-8")
        self.assertIn("[@example-com-10]", text)
        self.assertIn("references:", text)
        self.assertIn("citation-label:", text)
        rebuilt, _ = self.build("html", text)
        self.assertIn('data-cites="example-com-10">[10]', rebuilt.read_text(encoding="utf-8"))

    def test_numbered_sources_and_citeproc_bibliography_keep_their_own_lists(self):
        bib = self.folder / "sources.bib"
        bib.write_text("@book{book, author={Example, A.}, title={Real Book}, year={2020}}\n", encoding="utf-8")
        style = self.folder / "numeric.csl"
        style.write_text("""<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
<info><title>Numeric test</title><id>urn:numeric</id><updated>2026-11-25T00:00:00+00:00</updated></info>
<citation><layout prefix="[" suffix="]"><text variable="citation-number"/></layout></citation>
<bibliography><layout><text variable="citation-number" suffix=". "/><text variable="title"/></layout></bibliography>
</style>""", encoding="utf-8")
        header = "---\nbibliography: sources.bib\ncsl: numeric.csl\n---\n\n"
        real = "## Bibliography\n\n::: {#refs}\n:::\n"
        ai = "## Sources\n\n[7]: [First web source](https://example.org/one)\n"
        ai += "[12]: [Second web source](https://example.org/two)\n"
        baseline, _ = self.build("html", header + "Real citation [@book].\n\n" + real)
        expected = baseline.read_text(encoding="utf-8").split('<div id="refs"', 1)[1]
        for first in ("real", "numbered"):
            with self.subTest(first=first):
                body = "Real citation [@book]. Numbered sources [7, 12].\n\n"
                output, done = self.build("html", header + body + (real + "\n" + ai if first == "real" else ai + "\n" + real))
                html = output.read_text(encoding="utf-8")
                joined = " ".join(html.split())
                self.assertIn('data-cites="book">[1]', joined)
                self.assertIn(expected, html)
                self.assertIn('Numbered sources [7], [12].', joined)
                self.assertIn('[7] <a href="https://example.org/one">First web source</a>', joined)
                self.assertIn('[12] <a href="https://example.org/two">Second web source</a>', joined)
                self.assertEqual(joined.index('id="ref-book"') < joined.index("First web source"), first == "real")
                self.assertNotIn("numbered references left unchanged", done.stderr)


    def test_pdfmd_and_obsidian_convert_but_other_flavours_leave_source_alone(self):
        base = "Claim [1].\n\n1. https://example.org/\n"
        for flavour in ("pdfmd", "obsidian", "pandoc", "gfm", "commonmark"):
            with self.subTest(flavour=flavour):
                output, _ = self.build("html", base, "--flavour", flavour)
                self.assertEqual('data-cites="example-org-1"' in output.read_text(encoding="utf-8"),
                                 flavour in ("pdfmd", "obsidian"))

    def test_off_in_folder_metadata_or_document_and_check_code(self):
        base = "Claim [1].\n\n1. https://example.org/\n"
        config = self.folder / ".pdfmd" / "config.yaml"
        config.parent.mkdir()
        config.write_text("options:\n  numbered-references: off\n", encoding="utf-8")
        output, done = self.build("html", base)
        original = output.read_bytes()
        self.assertNotIn(b"data-cites", original)
        self.assertNotIn("incomplete numbered references", done.stderr)
        check = self.run_pdfmd(str(self.source), "--check")
        self.assertIn("[numbered-references-off]", check.stdout)
        check = self.run_pdfmd(str(self.source), "--check", "--check-ignore", "numbered-references-off")
        self.assertNotIn("[numbered-references-off]", check.stdout)
        meta = self.folder / "named.yaml"
        meta.write_text("pdfmd-options: {numbered-references: on}\n", encoding="utf-8")
        output, _ = self.build("html", base, "-y", str(meta))
        self.assertIn(b"data-cites", output.read_bytes())
        document = "---\npdfmd-options: {numbered-references: off}\n---\n\n" + base
        output, _ = self.build("html", document, "-y", str(meta))
        self.assertNotIn(b"data-cites", output.read_bytes())

    def test_partial_matches_are_atomic(self):
        base = "One [1], then [1-3].\n\n[1] [First source](https://example.org/one)\n"
        for text in (base, base + "[3]: https://example.org/three\n",
                     base.replace("[1-3]", "[1]") + "1. https://example.net/duplicate\n",
                     base.replace("[1-3]", "[[1]](https://example.net/conflict)")):
            with self.subTest(text=text):
                output, done = self.build("html", text)
                self.assertNotIn(b"data-cites", output.read_bytes())
                self.assertIn("incomplete numbered references", done.stderr)

    def test_protected_numeric_markers_do_not_prevent_conversion(self):
        raw = r"""---
abstract: '[70]'
---

Claim [1], literally \[2], [linked label](https://example.org/#tag[7]) and [topic][ordinary].
Keep [1](https://example.org/its-own-link), ![1](picture.png), `[3]` and $a[4]$.

<!-- [5] -->

> ```text
> [80]
> ```

```{=html}
<span>[6]</span>
```

[ordinary]: https://example.org/topic

1. https://example.org/one
"""
        output, done = self.build("html", raw)
        html = output.read_text(encoding="utf-8")
        self.assertEqual(html.count('data-cites="example-org-1"'), 1)
        self.assertIn("<span>[6]</span>", html)
        self.assertIn("[80]", html)
        self.assertNotIn("incomplete numbered references", done.stderr)

    def test_custom_csl(self):
        style = self.folder / "test.csl"
        style.write_text("""<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
<info><title>Test</title><id>urn:test</id><updated>2026-11-19T00:00:00+00:00</updated></info>
<citation><layout prefix="(" suffix=")"><text value="custom citation"/></layout></citation>
<bibliography><layout><text variable="title"/></layout></bibliography></style>""", encoding="utf-8")
        base = "Claim [2].\n\n2. [Written title](https://example.org/)\n"
        for text, flags in ((base, ("--csl", style.name)), ("---\ncsl: test.csl\n---\n\n" + base, ())):
            with self.subTest(flags=flags):
                output, _ = self.build("html", text, *flags)
                self.assertIn(b"(custom citation)", b" ".join(output.read_bytes().split()))

    def test_split_document_uses_one_terminal_source_list(self):
        part_dir = self.folder / "parts"
        part_dir.mkdir()
        (part_dir / "1.md").write_text("# Part one\n\nClaim [3].\n", encoding="utf-8")
        (part_dir / "2.md").write_text("# Part two\n\n[3]: https://example.org/three\n", encoding="utf-8")
        text = "---\ntitle: Test\npdfmd-options: {parts: auto}\n---\n"
        output, _ = self.build("html", text)
        self.assertIn(b'data-cites="example-org-3"', output.read_bytes())

    def test_both_report_routes_use_the_terminal_list(self):
        chapters = self.folder / "chapters"
        chapters.mkdir()
        first = chapters / "10-start.md"
        (chapters / "20-end.md").write_text("# End\n\n7. https://example.org/\n", encoding="utf-8")
        output = self.folder / "report.html"
        for route in ("route", "patch"):
            with self.subTest(route=route):
                first.write_text(f"---\npdfmd-options: {{report-build: {route}}}\n---\n\n# Start\n\nClaim [7].\n",
                                 encoding="utf-8")
                self.run_pdfmd("-r", str(chapters), "-t", "html", "-o", str(output))
                self.assertIn(b'data-cites="example-org-7"', output.read_bytes())

    def test_a_repaired_source_uses_the_same_labels_and_list_for_detection(self):
        text = "Claim [\x001].\n\n1. https://example.org/o\x00ne\n"
        output, done = self.build("html", text)
        html = output.read_text(encoding="utf-8")
        self.assertIn('data-cites="example-org-1"', html)
        self.assertEqual(html.count('href="https://example.org/one"'), 1)
        self.assertIn("source control characters", done.stderr)

    def test_other_links_using_the_number_keep_their_definition(self):
        text = "Claim [1]. Open [the link][1].\n\n[1]: https://example.org/\n"
        output, done = self.build("html", text)
        self.assertIn(b'href="https://example.org/"', output.read_bytes())
        self.assertNotIn(b"data-cites", output.read_bytes())
        self.assertIn("a Markdown link uses a source number", done.stderr)

    def test_writers_render_the_citations_and_references(self):
        text = "## Claim [7]\n\n7. [WrittenTitle](https://example.org/)\n"
        for target in ("html", "html4", "html5", "latex", "beamer", "context", "typst", "gfm", "gfm+raw",
                       "commonmark", "commonmark_x", "plain", "txt", "ansi", "rst", "org", "rtf", "docbook",
                       "docbook4", "docbook5", "json", "man", "ipynb", "asciidoc", "asciidoctor", "textile", "mediawiki",
                       "opml", "docx", "odt", "pptx", "epub", "epub2", "epub3"):
            with self.subTest(target=target):
                output, _ = self.build(target, text)
                if zipfile.is_zipfile(output):
                    with zipfile.ZipFile(output) as archive:
                        contents = b" ".join(archive.read(name) for name in archive.namelist()
                                             if name.endswith((".xml", ".xhtml", ".html")))
                else:
                    contents = output.read_bytes()
                if target != "opml":  # OPML writes headings only
                    self.assertIn(b"WrittenTitle", contents)
                for marker in (b"{[}7{]}", b"++[++7++]++", rb"\[7\]", rb"\\[7\\]"):
                    contents = contents.replace(marker, b"[7]")
                self.assertIn(b"[7]", contents)

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftotext"), "needs pdfLaTeX and pdftotext")
    def test_hand_written_numbering_looks_the_same_in_pdf(self):
        base = "A claim [1]. Another [2].\n\n[1] First — https://example.org/one\n\n[2] Second — https://example.org/two\n"
        extracted = []
        for flags in ((), ("--flavour", "pandoc")):
            output, _ = self.build("pdf", base, "-e", "pdflatex", *flags)
            result = subprocess.run(["pdftotext", str(output), "-"], check=True, capture_output=True, encoding="utf-8")
            extracted.append(" ".join(result.stdout.split()))
        self.assertEqual(*extracted)
        self.assertIn("[1] First", extracted[0])


    def test_without_bundled_lua(self):
        self.source.write_text("Claim [3].\n\n[3]: https://example.org/three\n", encoding="utf-8")
        output = self.folder / "result.html"
        program = ("import runpy, sys; sys.modules['pdfmd_lua'] = None; sys.argv = sys.argv[1:]; "
                   "runpy.run_path(sys.argv[0], run_name='__main__')")
        done = subprocess.run([sys.executable, "-c", program, str(ROOT / "pdfmd.py"), str(self.source),
                               "-t", "html", "-o", str(output)], cwd=self.folder, capture_output=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(b'data-cites="example-org-3"', output.read_bytes())


class NativeNumberedReferences(unittest.TestCase):
    def test_native_ansi_without_pandoc_keeps_a_visible_source_list(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.md"
            output = Path(directory) / "result.ansi"
            source.write_text("Claim [3].\n\n[3]: https://example.org/three\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(source),
                                   "-t", "ansi", "-o", str(output)], cwd=directory, capture_output=True, encoding="utf-8",
                                  env={**os.environ, "PATH": ""})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("example.org/three", output.read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_native_pdf_without_pandoc_keeps_a_visible_source_list(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.md"
            output = Path(directory) / "result.pdf"
            source.write_text("Claim [3].\n\n[3]: https://example.org/three\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(source),
                                   "-e", "inkmd", "-o", str(output)], cwd=directory, capture_output=True, encoding="utf-8",
                                  env={**os.environ, "PATH": ""})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            result = subprocess.run(["pdftotext", str(output), "-"], check=True, capture_output=True, encoding="utf-8")
            self.assertIn("[3] https://example.org/three", " ".join(result.stdout.split()))
