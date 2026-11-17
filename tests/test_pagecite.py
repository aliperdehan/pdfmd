"""Pagecite P1a: synthetic sources, CSL styles and claims, through the checkout."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
BIB = """@book{alpha, author={Alpha, Ada}, title={Invented Glass}, year={2001}}
@book{beta, author={Beta, Ben}, title={Invented Clay}, year={2002}}
"""


def csl(kind, locator=True, macro=False):
    printed = '<text variable="locator" prefix=", p. "/>' if locator else ""
    macros = f'<macro name="pages">{printed}</macro>' if macro else ""
    printed = '<text macro="pages"/>' if macro else printed
    name = '<text variable="citation-number"/>' if kind in ("numeric", "label") else '<names variable="author"><name form="short"/></names>'
    prefix, suffix = ("[", "]") if kind in ("numeric", "label") else ("(", ")")
    return f"""<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="{'note' if kind == 'note' else 'in-text'}">
<info><title>Synthetic {kind}</title><id>https://example.invalid/{kind}</id><category citation-format="{kind}"/></info>
{macros}<citation><layout prefix="{prefix}" suffix="{suffix}" delimiter="; ">{name}{printed}</layout></citation>
<bibliography><layout><text variable="title"/></layout></bibliography></style>"""


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Builds(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pagecite-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "refs.bib").write_text(BIB, encoding="utf-8")
        for kind in ("author-date", "author", "note", "numeric", "label"):
            (self.root / f"{kind}.csl").write_text(csl(kind, macro=True), encoding="utf-8")
        (self.root / "no-pages.csl").write_text(csl("numeric", False), encoding="utf-8")

    def build(self, body="Claim [@alpha, p. 2]. Next [p. 5].", mode="auto", style=None, to="plain", options="", extra=()):
        header = "title: Synthetic trial\nbibliography: refs.bib\n"
        if style:
            header += f"csl: {style}.csl\n"
        if options:
            header += "pdfmd-options:\n" + options + "\n"
        source = "---\n" + header + "---\n\n" + body + "\n"
        (self.root / "d.md").write_text(source, encoding="utf-8")
        output = self.root / ("out." + ("txt" if to == "plain" else to))
        command = [sys.executable, str(ROOT / "scripts" / "pdfmd"), "d.md", "--to", to, "-o", str(output),
                   "--no-backup", "--no-stamp", "--no-auto", "bib", "crossref", "--verbose"]
        if mode is not None:
            command += ["--pagecite", mode]
        command += ["--wrap=none"]
        done = subprocess.run(command + list(extra), cwd=self.root, env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"},
                              capture_output=True, encoding="utf-8", timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((self.root / "d.md").read_text(encoding="utf-8"), source)
        content = output.read_bytes() if to in ("docx", "pdf") else output.read_text(encoding="utf-8")
        if to == "plain":
            content = content.replace("\xa0", " ")  # Pandoc makes a page label’s space non-breaking.
        return content, done.stdout + done.stderr

    def test_auto_default_style_uses_pages(self):
        text, _ = self.build()
        self.assertIn("Next (p. 5).", text)

    def test_modes_against_each_style(self):
        for kind in ("author-date", "author", "note", "numeric", "label", "no-pages"):
            for mode in ("off", "auto", "page", "style", "drop", "bare", "full"):
                with self.subTest(kind=kind, mode=mode):
                    text, log = self.build(style=kind, mode=mode)
                    if mode == "off":
                        self.assertIn("Next [p. 5].", text)
                    elif mode == "drop" or mode == "auto" and kind == "no-pages":
                        self.assertIn("Next.", text)
                        if mode == "auto":
                            self.assertEqual(log.count("pagecite: citation style never prints a locator; dropping page markers"), 1)
                    elif mode in ("page", "bare") or mode == "auto" and kind in ("author-date", "author"):
                        self.assertIn("Next [p. 5]." if kind in ("numeric", "label", "no-pages") else "Next (p. 5).", text)
                    elif kind in ("numeric", "label", "no-pages"):
                        self.assertIn("Next [1]." if kind == "no-pages" else "Next [1, p. 5].", text)
                    else:
                        self.assertIn("Alpha, p. 5", text)

    def test_note_style_can_choose_ibid_with_locator(self):
        style = csl("note").replace(
            '<names variable="author"><name form="short"/></names>',
            '<choose><if position="ibid-with-locator"><text value="Ibid"/></if>'
            '<else><names variable="author"><name form="short"/></names></else></choose>')
        (self.root / "ibid.csl").write_text(style, encoding="utf-8")
        text, _ = self.build(style="ibid")
        self.assertIn("Ibid, p. 5", text)

    def test_scope_sources_comments_crossrefs_and_notes(self):
        body = """No source [p. 1].

Claim [@alpha; @beta]. <!-- a synthetic comment --> Follow [p. 5]. See @fig:shape; then [p. 6].

New block [p. 7].

Outer [@alpha]. Note[^n] Outer again [p. 8].

[^n]: No source [p. 9]. Then [@beta]. Follow [p. 10].
"""
        text, log = self.build(body, "style", "author-date")
        for page in (1, 7, 9):
            self.assertIn(f"pagecite: no citation before [p. {page}]", log)
        self.assertIn("pagecite: [p. 5] follows several sources, using beta", log)
        self.assertIn("Beta, p. 6", text)
        self.assertIn("Alpha, p. 8", text)
        self.assertIn("Beta, p. 10", text)
        text, log = self.build("[@alpha; @alpha]. Follow [p. 5].", "style", "author-date")
        self.assertIn("Alpha, p. 5", text)
        self.assertNotIn("follows several sources", log)

    def test_escapes_code_links_math_and_multiple_markers(self):
        body = r"""Claim [@alpha]. \[p. 5] `code [p. 6]` [link [p. 7]](https://example.invalid) $[p. 8]$. Then [p. 9], [pp. 10--12].

    code \[p. 13]

```text
code \[p. 14]
```
"""
        text, _ = self.build(body, "page")
        for page in (5, 6, 7):
            self.assertIn(f"[p. {page}]", text)
        self.assertIn("(p. 9), (pp. 10–12).", text)
        self.assertIn(r"code \[p. 13]", text)
        self.assertIn(r"code \[p. 14]", text)
        self.assertNotIn("pdfmd-pagecite", text)

    def test_terms_roman_numbers_lists_cells_and_inline_wrappers(self):
        body = """- *Claim [@alpha]* then [S. iv]. [p. 5].

| A | B |
|---|---|
| [@beta]. Next [S. 7] | [S. 8] |
"""
        text, log = self.build(body, "page", options="  pagecite-terms: [S., p.]")
        self.assertIn("(S. iv)", text)
        self.assertIn("(p. 5)", text)
        self.assertIn("(S. 7)", text)
        self.assertIn("pagecite: no citation before [S. 8]", log)

    def test_cache_paths_keep_markdown_punctuation(self):
        cache = str(self.root / "_trial_~cache~'s")
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache, "LOCALAPPDATA": cache}):
            text, _ = self.build()
            self.assertIn("Next (p. 5).", text)

    def test_default_off_is_byte_identical_to_explicit_off(self):
        a, log = self.build(mode=None, to="html")
        b, _ = self.build(mode="off", to="html")
        self.assertEqual(a, b)
        self.assertNotIn("pagecite.lua", log)

    def test_markup_no_auto_and_layered_settings(self):
        for options, extra in (("  pagecite: auto", ()), ("  pagecite: off", ("--pagecite", "auto"))):
            text, _ = self.build(mode=None, options=options, extra=extra)
            self.assertIn("Next (p. 5).", text)
        for options, extra in (("  markup: [callouts]", ()), ("  flavour: pandoc", ()), ("", ("--no-auto", "pagecite"))):
            text, log = self.build(mode="page", options=options, extra=extra)
            self.assertIn("Next [p. 5].", text)
            self.assertNotIn("pagecite.lua", log)

    def test_every_writer_and_native_bibliography_engines(self):
        for writer in ("latex", "typst", "docx", "html", "gfm"):
            with self.subTest(writer=writer):
                text, log = self.build(mode="style", style="numeric", to=writer)
                if writer == "docx":
                    import io
                    with zipfile.ZipFile(io.BytesIO(text)) as archive:
                        text = archive.read("word/document.xml").decode("utf-8")
                self.assertIn("p. 5", text)
                self.assertNotIn("[p. 5]", text)
                self.assertLess(log.index("pagecite.lua"), log.index("--citeproc"))
        for engine in ("natbib", "biblatex"):
            text, _ = self.build(mode="auto", to="latex", extra=(f"--{engine}",))
            self.assertRegex(text, r"\\(?:auto)?cite\w*\[.*5.*\]\{alpha\}")

    def test_native_bibliography_setting_only_applies_where_enabled(self):
        options = "  citation-engine: biblatex"
        text, _ = self.build(mode="auto", to="latex", options=options)
        self.assertRegex(text, r"\\autocite\[(?:p\.~)?5\]\{alpha\}")
        text, _ = self.build(mode="auto", to="html", options=options)
        self.assertIn("Next (p. 5).", text)
        text, _ = self.build(mode="auto", to="latex", options=options, extra=("--no-auto", "citationengine"))
        self.assertIn("Next (p. 5).", text)

    def test_project_filter_of_the_same_name_runs_after_builtin(self):
        project = self.root / "pagecite.lua"
        project.write_text('return {{Para = function(el) for _, item in ipairs(el.content) do if item.t == "Str" and item.text:find("^%[p%.") then error("marker reached project filter") end end end}}', encoding="utf-8")
        for mode, expected in (("style", "Next [1, p. 5]."), ("page", "Next [p. 5].")):
            text, log = self.build(mode=mode, style="numeric", extra=("--lua-filter", str(project)))
            self.assertIn(expected, text)
            self.assertLess(log.index(str(ROOT / "lib" / "pdfmd_lua" / "pagecite.lua")), log.index(str(project)))

    def test_unrelated_escapes_case_spacing_and_softbreaks(self):
        text, _ = self.build(r"Claim [@alpha]. \[ordinary] then [P.   5], [pp. 6--8].", "page")
        self.assertIn("[ordinary] then (P. 5), (pp. 6–8).", text)
        self.assertNotIn("pdfmd-pagecite", text)
        text, _ = self.build("Claim [@alpha]. [pp.\n9--10].", "page")
        self.assertIn("(pp. 9–10).", text)
        text, log = self.build(r"Claim [@alpha]. \[ordinary].", "page")
        self.assertIn("[ordinary].", text)
        self.assertNotIn("pagecite.lua", log)

    def test_parts_inherit_pagecite_and_escaped_markers_stay_literal(self):
        (self.root / "parts").mkdir()
        (self.root / "parts" / "10-claims.md").write_text(
            r"Part [@alpha]. Next [p. 5]. Literal \[p. 6].", encoding="utf-8")
        text, _ = self.build("Lead.", "page", options="  parts: auto")
        self.assertIn("Next (p. 5). Literal [p. 6].", text)

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftotext"), "needs pdfLaTeX and pdftotext")
    def test_latex_pdf_prints_locator_at_each_numeric_claim(self):
        self.check_pdf("pdflatex")

    @unittest.skipUnless(shutil.which("typst") and shutil.which("pdftotext"), "needs Typst and pdftotext")
    def test_typst_pdf_prints_locator_at_each_numeric_claim(self):
        self.check_pdf("typst")

    def check_pdf(self, engine):
        self.build(mode="auto", style="numeric", to="pdf",
                   extra=("-e", engine, "--engine-fallback", "missing", "--no-cache"))
        done = subprocess.run(["pdftotext", str(self.root / "out.pdf"), "-"],
                              capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        text = " ".join(done.stdout.split())
        self.assertIn("Claim [1, p. 2]. Next [1, p. 5].", text)

    def test_native_keeps_markers_and_notes_once(self):
        _, log = self.build("[@alpha]. Follow [p. 5] and [p. 6].", "auto", to="pdf", extra=("-e", "inkmd"))
        self.assertEqual(log.count("pagecite: native tier leaves page markers unchanged"), 1)


class Settings(unittest.TestCase):
    def test_cli_terms_and_csl_fallbacks(self):
        package = pdfmd.load_package("pdfmd_excerpts.pagecite")
        self.assertEqual(package.mode_value(" FULL "), "style")
        self.assertEqual(package.mode_value(False), "off")
        with self.assertRaises(SystemExit):
            package.mode_value("unknown")
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "d.md"
            document.write_text("---\npdfmd-options:\n  pagecite: auto\n---\n\n[@alpha]. [p. 5]", encoding="utf-8")
            metadata = Path(folder) / "m.yaml"
            metadata.write_text("pdfmd-options:\n  pagecite: drop\n  pagecite-terms: [S.]\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(package.ENV, None)
                self.assertEqual(package.settings(document, [metadata])[0], "auto")
                self.assertEqual(package.settings(document, [metadata])[1], ["S."])
                os.environ[package.ENV] = "page"
                self.assertEqual(package.settings(document, [metadata])[0], "page")
            self.assertEqual(package.style_settings("auto", [document], [], ["--csl", "missing.csl"])[0], "style")
            self.assertEqual(package.style_settings("auto", [document], [], ["--biblatex"])[0], "style")
            document.write_text("Claim.", encoding="utf-8")
            with mock.patch.object(pdfmd, "config_options", return_value={"pagecite": "page"}), \
                    mock.patch.object(pdfmd.load_package("pdfmd_config"), "folder_layers", return_value=[]):
                self.assertEqual(package.settings(document, [])[0], "page")
                with mock.patch.object(pdfmd.load_package("pdfmd_config"), "folder_layers", return_value=[("folder project", {"pagecite": "drop"})]):
                    self.assertEqual(package.settings(document, [])[0], "drop")
                    self.assertEqual(package.settings(document, [metadata])[0], "drop")

    def test_csl_only_considers_macros_reached_from_the_citation(self):
        package = pdfmd.load_package("pdfmd_excerpts.pagecite")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            document = root / "d.md"
            document.write_text("Claim.", encoding="utf-8")
            style = root / "s.csl"
            style.write_text(csl("numeric", False).replace("<citation>", '<macro name="unused"><text variable="locator"/></macro><citation>'), encoding="utf-8")
            self.assertEqual(package.style_settings("auto", [document], [], ["--csl", str(style)])[0], "drop")
            data = root / "data"
            (data / "csl").mkdir(parents=True)
            (data / "csl" / "style.csl").write_text(csl("numeric", False), encoding="utf-8")
            self.assertEqual(package.style_settings("auto", [document], [], ["--data-dir", str(data), "--csl=style.csl"])[0], "drop")
            style.write_text("<not-xml", encoding="utf-8")
            self.assertEqual(package.style_settings("auto", [document], [], ["--csl", str(style)])[0], "style")

    def test_native_does_not_note_escaped_or_protected_markers(self):
        import io
        from contextlib import redirect_stderr
        package = pdfmd.load_package("pdfmd_excerpts.pagecite")
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "d.md"
            document.write_text("---\npdfmd-options:\n  pagecite: auto\n---\n", encoding="utf-8")
            for text in (r"\[p. 5]", "`[p. 5]`", "[a [p. 5]](https://example.invalid)", "    [p. 5]", "<!-- [p. 5] -->"):
                with self.subTest(text=text), redirect_stderr(io.StringIO()) as said:
                    package.native_note(document, [], text)
                    self.assertNotIn("pagecite: native tier", said.getvalue())

