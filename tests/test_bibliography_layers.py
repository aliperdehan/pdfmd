"""Bibliography sources accumulate in the existing metadata layer order (D61)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.doc = self.root / "course" / "report"
        self.doc.mkdir(parents=True)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1", "PDFMD_BUILD_LOG": "off",
                    "XDG_CONFIG_HOME": str(self.root / "config"), "XDG_CACHE_HOME": str(self.root / "cache"), "LOCALAPPDATA": str(self.root / "cache"),
                    "XDG_DATA_HOME": str(self.root / "data")}

    def write(self, name, text):
        path = self.doc / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def bib(self, name, key, title):
        return self.write(name, f"@book{{{key}, title={{{title}}}, author={{Example, A.}}, year={{2020}}}}\n")

    def run_pdfmd(self, *args, target="html"):
        return subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "d.md", "--to", target,
                               "-o", "out." + target, "--no-stamp", "--no-backup", *args], cwd=self.doc,
                              env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def output(self, done, target="html"):
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.doc / ("out." + target)).read_text(encoding="utf-8")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Layers(Tree):
    def test_sources_from_every_layer_and_plus_keys_add(self):
        layers = [("../.pdfmd/metadata.yaml", "folder"), ("../metadata/metadata.yaml", "parent"),
                  ("metadata/metadata.yaml", "accessory"), ("d.yaml", "local")]
        for name, key in layers:
            self.bib(key + ".bib", key, key.title() + " Book")
            self.write(name, f"bibliography: {self.doc / (key + '.bib')}\n")
        self.bib("front.bib", "front", "Front Book")
        self.bib("plus.bib", "plus", "Plus Book")
        self.write("d.md", "---\nbibliography: front.bib\nbibliography+: plus.bib\n---\n"
                   "[@folder; @parent; @accessory; @local; @front; @plus]\n")
        text = self.output(self.run_pdfmd())
        for key in ("folder", "parent", "accessory", "local", "front", "plus"):
            self.assertIn(key.title() + " Book", text)

    def test_each_clashing_key_warns_once_names_both_files_and_strict_counts_it(self):
        self.bib("low.bib", "same", "Lower Book")
        self.bib("high.bib", "same", "Higher Book")
        self.write("metadata.yaml", "bibliography: low.bib\n")
        self.write("d.md", "---\nbibliography: high.bib\n---\n[@same]\n")
        done = self.run_pdfmd()
        text = self.output(done)
        self.assertIn("Higher Book", text)
        self.assertNotIn("Lower Book", text)
        warnings = [line for line in (done.stdout + done.stderr).splitlines() if line.startswith("WARN") and "same" in line]
        self.assertEqual(len(warnings), 1, done.stdout + done.stderr)
        self.assertIn("high.bib", warnings[0])
        self.assertIn("low.bib", warnings[0])
        strict = self.run_pdfmd("--strict")
        self.assertNotEqual(strict.returncode, 0)
        self.assertIn("strict", (strict.stdout + strict.stderr).lower())

    def test_inline_precedence_is_per_layer_not_all_references_over_all_files(self):
        self.bib("front.bib", "same", "Document File")
        self.write("metadata.yaml", "references: [{id: same, type: book, title: Lower Inline}]\n")
        self.write("d.md", "---\nbibliography: front.bib\n---\n[@same]\n")
        text = self.output(self.run_pdfmd())
        self.assertIn("Document File", text)
        self.assertNotIn("Lower Inline", text)
        self.write("d.md", "---\nbibliography: front.bib\nreferences: [{id: same, type: book, title: Document Inline}]\n---\n[@same]\n")
        text = self.output(self.run_pdfmd())
        self.assertIn("Document Inline", text)
        self.assertNotIn("Document File", text)

    def test_cli_bibliographies_and_metadata_forms_are_highest_and_additive(self):
        self.bib("front.bib", "same", "Document File")
        self.bib("cli.bib", "same", "Command File")
        self.bib("other.bib", "other", "Other Command")
        self.write("d.md", "---\nbibliography: front.bib\nreferences: [{id: same, type: book, title: Document Inline}]\n---\n[@same; @other]\n")
        for args in [("--bibliography", "cli.bib"), ("--bibliography=cli.bib",),
                     ("-M", "bibliography=cli.bib"), ("-Mbibliography:cli.bib",),
                     ("--metadata=bibliography=cli.bib",)]:
            with self.subTest(args=args):
                text = self.output(self.run_pdfmd(*args, "--bibliography", "other.bib"))
                self.assertIn("Command File", text)
                self.assertIn("Other Command", text)
                self.assertNotIn("Document Inline", text)

    def test_explicit_metadata_is_above_document_but_variables_are_not_sources(self):
        self.write("named.yaml", "references: [{id: same, type: book, title: Explicit Inline}]\n")
        self.write("d.md", "---\nreferences: [{id: same, type: book, title: Document Inline}]\n---\n[@same]\n")
        done = self.run_pdfmd("-y", "named.yaml", "-V", "references=Template Only")
        text = self.output(done)
        self.assertIn("Explicit Inline", text)
        self.assertNotIn("Document Inline", text)
        self.assertNotIn("Template Only", text)

    def test_json_yaml_and_bibtex_clashes_preserve_unique_entries(self):
        self.write("refs.json", json.dumps([{"id": "same", "type": "book", "title": "JSON Winner"},
                                           {"id": "json", "type": "book", "title": "JSON Unique"}]))
        self.write("refs.yaml", "references: [{id: same, type: book, title: YAML Loser}, {id: yaml, type: book, title: YAML Unique}]\n")
        self.bib("refs.bib", "same", "Bib Loser")
        self.write("d.md", "---\nbibliography: [refs.bib, refs.yaml, refs.json]\n---\n[@same; @json; @yaml]\n")
        done = self.run_pdfmd()
        text = self.output(done)
        for title in ("JSON Winner", "JSON Unique", "YAML Unique"):
            self.assertIn(title, text)
        for title in ("YAML Loser", "Bib Loser"):
            self.assertNotIn(title, text)
        warnings = [line for line in (done.stdout + done.stderr).splitlines() if line.startswith("WARN") and "same" in line]
        self.assertEqual(len(warnings), 1)
        for name in ("refs.json", "refs.yaml", "refs.bib"):
            self.assertIn(name, warnings[0])

    def test_natbib_and_biblatex_receive_all_files_and_inline_references(self):
        cache = self.root / "cache_with_underscores"
        self.env.update(XDG_CACHE_HOME=str(cache), LOCALAPPDATA=str(cache))
        self.bib("low.bib", "low", "Low Book")
        self.bib("high.bib", "high", "High Book")
        self.write("metadata.yaml", "bibliography: low.bib\n")
        self.write("d.md", "---\nbibliography: high.bib\nreferences: [{id: inline, type: book, title: Inline Book}]\n---\n[@low; @high; @inline]\n")
        for mode in ("natbib", "biblatex"):
            with self.subTest(mode=mode):
                tex = self.output(self.run_pdfmd("--" + mode, target="tex"), "tex")
                self.assertIn("low.bib" if mode == "biblatex" else "low", tex)
                self.assertIn("high.bib" if mode == "biblatex" else "high", tex)
                self.assertIn("inline", tex)
                # The generated bib resource, not merely a citation command, must hold the inline entry.
                resources = list(cache.rglob("*.bib"))
                self.assertTrue(any("Inline {Book}" in p.read_text(encoding="utf-8") for p in resources))
                for resource in resources:
                    self.assertIn(resource.resolve().as_posix(), tex)     # paths reach BibTeX/Biber literally, including `_`

    def test_a_file_beside_the_document_keeps_its_name_in_the_native_writers(self):
        """Pandoc 3.1.3 writes the bibliography command with every `_` of a long absolute path escaped (Pandoc issue 7414), which broke
        natbib in a temporary folder whose name has one; the name as written is what 3.33.231 and earlier gave it."""
        self.bib("low.bib", "low", "Low Book")
        self.write("d.md", "---\nbibliography: low.bib\n---\n[@low]\n")
        for mode, command in (("natbib", r"\bibliography{"), ("biblatex", r"\addbibresource{")):
            with self.subTest(mode=mode):
                tex = self.output(self.run_pdfmd("--" + mode, target="tex"), "tex")
                self.assertIn(command + "low.bib}", tex)
                self.assertNotIn(str(self.root), tex)

    def test_repeated_file_is_not_a_clash(self):
        self.bib("refs.bib", "same", "Single Book")
        self.write("metadata.yaml", "bibliography: refs.bib\n")
        self.write("d.md", "---\nbibliography: refs.bib\n---\n[@same]\n")
        done = self.run_pdfmd()
        self.assertIn("Single Book", self.output(done))
        self.assertNotIn("WARN", done.stderr)

    def test_every_key_warns_even_when_entries_are_identical(self):
        text = "@book{one, title={Identical}}\n@book{two, title={Identical}}\n"
        self.write("one.bib", text)
        self.write("two.bib", text)
        self.write("d.md", "---\nbibliography: [one.bib, two.bib]\n---\n[@one; @two]\n")
        done = self.run_pdfmd()
        self.output(done)
        warnings = [line for line in done.stderr.splitlines() if line.startswith("WARN")]
        self.assertEqual(len(warnings), 2, done.stderr)
        for key in ("one", "two"):
            self.assertTrue(any(f"key {key}:" in line and "one.bib" in line and "two.bib" in line for line in warnings))

    def test_same_named_files_use_existing_resource_lookup_and_symlink_target(self):
        self.bib("metadata/refs.bib", "accessory", "Accessory Book")
        self.write("metadata/metadata.yaml", "bibliography: refs.bib\n")
        self.write("d.md", "---\ntitle: T\n---\n[@accessory]\n")
        self.assertIn("Accessory Book", self.output(self.run_pdfmd()))
        # A symlinked metadata file's real directory is already on the resource path.
        (self.doc / "metadata/metadata.yaml").unlink()
        self.bib("../shared/other.bib", "shared", "Shared Book")
        real = self.write("../shared/shared.yaml", "bibliography: other.bib\n")
        (self.doc / "metadata/metadata.yaml").symlink_to(real)
        self.write("d.md", "[@shared]\n")
        self.assertIn("Shared Book", self.output(self.run_pdfmd()))

    def pdf_build(self, method):
        if not all(shutil.which(tool) for tool in ("pdflatex", "pdftotext", *({"natbib": ["bibtex"], "biblatex": ["biber"]}.get(method, [])))):
            self.skipTest("needs TeX, its bibliography tool and pdftotext")
        self.bib("low.bib", "same", "Losing Book")
        with (self.doc / "low.bib").open("a", encoding="utf-8") as handle:
            handle.write("@book{low, title={Lower Unique}, author={Example, A.}, year={2020}}\n")
        self.bib("high.bib", "same", "Winning Book")
        self.write("metadata.yaml", "bibliography: low.bib\n")
        self.write("d.md", "---\nbibliography: high.bib\nreferences: [{id: inline, type: book, title: Inline Book}]\n"
                   f"pdfmd-options: {{citation-engine: {method}}}\n---\n[@same; @low; @inline]\n")
        done = self.run_pdfmd("-e", "pdflatex", "--no-cache", "--engine-fallback", "missing", target="pdf")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = subprocess.run(["pdftotext", str(self.doc / "out.pdf"), "-"],
                              capture_output=True, text=True, check=True).stdout
        for title in ("Winning Book", "Lower Unique", "Inline Book"):
            self.assertIn(title, text)
        self.assertNotIn("Losing Book", text)

    def test_citeproc_pdf(self):
        self.pdf_build("citeproc")

    def test_natbib_pdf(self):
        self.pdf_build("natbib")

    def test_biblatex_pdf(self):
        self.pdf_build("biblatex")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Literal(Tree):
    """The metadata file pdfmd hands Pandoc is Markdown: a path must come out of it exactly as it went in."""

    PATHS = (r"C:\Users\runneradmin\AppData\Local\Temp\tmp22wg_n_7.bib", "C:/Users/RUNNER~1/Temp/tmp_a_b/refs.bib",
             "/tmp/my refs/a_b_c.bib", "/tmp/x*y*/it's [1] <a>.bib", "../a...b/c--d.bib")

    def through_pandoc(self, names, reader="markdown"):
        sys.path.insert(0, str(ROOT / "lib"))
        try:
            from pdfmd_bibliography.sources import literal
        finally:
            sys.path.pop(0)
        merged = self.root / "merged.yaml"          # JSON is YAML, and CI has no PyYAML (pdfmd writes it with its own copy)
        merged.write_text(json.dumps({"bibliography": [literal(name) for name in names]}), encoding="utf-8")
        template = self.root / "t.txt"
        template.write_text("$for(bibliography)$$bibliography$\n$endfor$", encoding="utf-8")
        done = subprocess.run(["pandoc", "-f", reader, "-t", "plain", "--metadata-file", str(merged),
                               "--template", str(template)], input="x", capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.splitlines()

    def test_a_path_with_backslashes_or_markdown_marks_reaches_pandoc_intact(self):
        for reader in ("markdown", "gfm", "commonmark_x"):
            with self.subTest(reader=reader):
                self.assertEqual(self.through_pandoc(self.PATHS, reader), list(self.PATHS))

    def test_plain_commonmark_reads_the_folders_and_drive_too(self):
        """Pandoc's plain `commonmark` reader keeps `\\/` and `\\:` as written, so they are not escaped (it also keeps `\\'`
        and `\\~`, which Pandoc's Markdown needs: a path with those is the one case it reads wrong)."""
        paths = [path for path in self.PATHS if "'" not in path and "~" not in path]
        self.assertEqual(self.through_pandoc(paths, "commonmark"), paths)

    def test_the_escape_is_only_backslashes_before_punctuation(self):
        sys.path.insert(0, str(ROOT / "lib"))
        try:
            from pdfmd_bibliography.sources import literal
        finally:
            sys.path.pop(0)
        self.assertEqual(literal(r"C:\a_b.bib"), r"C:\\a\_b\.bib")
        self.assertEqual(literal("/x/y:z"), "/x/y:z")
        self.assertEqual(literal("plain name 7"), "plain name 7")


class Native(Tree):
    def test_native_tier_still_says_citations_are_left_as_written(self):
        self.write("metadata.yaml", "references: [{id: low, type: book, title: Lower}]\n")
        self.write("d.md", "---\nreferences: [{id: high, type: book, title: Higher}]\n---\n[@low; @high]\n")
        done = self.run_pdfmd("-e", "inkmd", target="pdf")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("citation(s) left as written", done.stdout + done.stderr)


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("typst"), "needs Pandoc and Typst")
class NativePaths(Tree):
    def prepare(self, parent=False, clash=False):
        self.bib("metadata/references.bib", "local", "Local Book")
        style = subprocess.run(["pandoc", "--print-default-data-file", "default.csl"],
                               env=self.env, capture_output=True, text=True, check=True).stdout
        self.write("metadata/apa6.csl", style)
        self.write("metadata/metadata.yaml", "bibliography: references.bib\ncsl: apa6.csl\n"
                   "pdfmd-options: {engine: typst}\n")
        front, citations = "", "@local"
        if parent:
            self.bib("../metadata/parent.bib", "parent", "Parent Book")
            self.write("../metadata/metadata.yaml", "bibliography: parent.bib\n")
            citations += "; @parent"
        if clash:
            with (self.doc / "metadata/references.bib").open("a", encoding="utf-8") as handle:
                handle.write("@book{same, title={Losing Book}, author={Example, A.}, year={2020}}\n")
            self.bib("SR/high.bib", "same", "Winning Book")
            front = "bibliography: high.bib\n"
            citations += "; @same"
        self.write("SR/x.md", "---\ntitle: T\npdfmd-options: {metadata-parents: 2}\n" + front + "---\n\n[" + citations + "]\n")

    def build(self, *flags, source="SR/x.md", output="out.pdf"):
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), source, "-o", output,
                               "--no-stamp", "--no-backup", "--engine-fallback", "missing", "--no-cache", *flags],
                              cwd=self.doc, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def pdf_text(self, output="out.pdf"):
        import pypdf
        return "\n".join(page.extract_text() for page in pypdf.PdfReader(self.doc / output).pages)

    def test_typst_uncited_native_bibliography_has_no_heading_or_block(self):
        self.prepare(parent=True)
        metadata = self.doc / "metadata/metadata.yaml"
        metadata.write_text(metadata.read_text() + "reference-section-title: References\n")
        for front in ("", "bibliography: null\n"):
            with self.subTest(front=front):
                self.write("SR/x.md", "---\ntitle: T\n" + front + "---\n\n"
                           "Uncited prose, `[@local]`, <reader@example.org>.\n\n```text\n[@parent]\n```\n")
                self.build("--no-citeproc")
                text = self.pdf_text()
                for absent in ("Bibliography", "References", "Local Book", "Parent Book"):
                    self.assertNotIn(absent, text)
                self.build("--no-citeproc", "--to", "typst", "--standalone", output="out.typ")
                self.assertNotIn("#bibliography(", (self.doc / "out.typ").read_text())

    def test_typst_cited_native_bibliography_keeps_the_released_title(self):
        self.prepare()
        metadata = self.doc / "metadata/metadata.yaml"
        metadata.write_text(metadata.read_text() + "reference-section-title: References\n")
        self.build("--no-citeproc")
        text = self.pdf_text()
        self.assertIn("Bibliography", text)  # v3.33.191: Typst's automatic title, not citeproc's title metadata.
        self.assertNotIn("References", text)
        self.assertIn("Local Book", text)
        self.build()  # Citeproc still owns its list and honours reference-section-title.
        text = self.pdf_text()
        self.assertIn("References", text)
        self.assertNotIn("Bibliography", text)
        self.assertIn("Local Book", text)

    def test_typst_native_bibliography_uses_citations_after_document_filters(self):
        self.prepare()
        filter_path = self.write("citations.lua", "")
        for body, cited in (("Plain prose.", False), ("A footnote.[^1]\n\n[^1]: [@local]", True)):
            with self.subTest(cited=cited):
                filter_path.write_text("function Pandoc(doc) doc.blocks = pandoc.read("
                                       + json.dumps(body) + ', "markdown").blocks; return doc end\n')
                self.build("--no-citeproc", "--lua-filter", str(filter_path))
                text = self.pdf_text()
                self.assertEqual("Bibliography" in text, cited)
                self.assertEqual("Local Book" in text, cited)

    def test_typst_native_raw_citations_keep_the_bibliography(self):
        self.prepare()
        for body in ('`@local`{=typst}', '```{=typst}\n#cite(label("local"))\n```'):
            with self.subTest(body=body):
                self.write("SR/x.md", "---\ntitle: T\n---\n\n" + body + "\n")
                self.build("--no-citeproc")
                text = self.pdf_text()
                self.assertIn("Bibliography", text)
                self.assertIn("Local Book", text)

    def test_typst_native_bibliography_keeps_explicit_uncited_requests(self):
        self.prepare()
        for extra in ("nocite: '@local'", "nocite: '@*'", "full-bibliography: true"):
            with self.subTest(extra=extra):
                self.write("SR/x.md", "---\ntitle: T\n" + extra + "\n---\n\nPlain prose.\n")
                self.build("--no-citeproc", "--to", "typst", "--standalone", output="out.typ")
                self.assertIn("#bibliography(", (self.doc / "out.typ").read_text())

    def test_typst_without_citeproc_resolves_metadata_and_parent_bibliographies(self):
        for parent in (False, True):
            with self.subTest(parent=parent):
                self.prepare(parent=parent)
                self.build("--no-citeproc")
                text = self.pdf_text()
                self.assertIn("Local Book", text)
                if parent:
                    self.assertIn("Parent Book", text)

    def test_typst_without_citeproc_reads_cached_winners_and_keeps_layers(self):
        self.prepare(parent=True, clash=True)
        self.build("--no-citeproc")
        text = self.pdf_text()
        for title in ("Local Book", "Parent Book", "Winning Book"):
            self.assertIn(title, text)
        self.assertNotIn("Losing Book", text)

    def test_typst_citeproc_still_resolves_metadata_and_parent_layers(self):
        self.prepare(parent=True, clash=True)
        self.build()
        text = self.pdf_text()
        for title in ("Local Book", "Parent Book", "Winning Book"):
            self.assertIn(title, text)
        self.assertNotIn("Losing Book", text)

    def test_typst_export_has_literal_names_and_compiles_with_its_root(self):
        self.prepare(parent=True, clash=True)
        self.build("--no-citeproc", "--to", "typst", "--standalone", "-V", "mainfont=Libertinus Serif", output="out.typ")
        typ = (self.doc / "out.typ").read_text(encoding="utf-8")
        self.assertNotIn(r"\_", next(line for line in typ.splitlines() if line.startswith("#bibliography(")))
        done = subprocess.run(["typst", "compile", "--root=/", "out.typ", "export.pdf"], cwd=self.doc,
                              env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Parent Book", self.pdf_text("export.pdf"))

    def test_direct_typst_with_a_local_bibliography_still_builds(self):
        self.prepare()
        self.write("metadata/direct.typ", 'Cite @local.\n#bibliography("references.bib")\n')
        done = self.build("--verbose", source="metadata/direct.typ")
        self.assertIn("TYPSTDIRECT", done.stdout + done.stderr)
        self.assertIn("Local Book", self.pdf_text())

    def test_latex_native_bibliography_tools_read_metadata_and_parent_layers(self):
        for mode, tool in (("natbib", "bibtex"), ("biblatex", "biber")):
            with self.subTest(mode=mode):
                if not shutil.which("pdflatex") or not shutil.which(tool):
                    self.skipTest("needs pdfLaTeX and " + tool)
                self.prepare(parent=True, clash=True)
                source = self.doc / "SR/x.md"
                source.write_text(source.read_text().replace("metadata-parents: 2", "metadata-parents: 2, citation-engine: " + mode))
                self.build("-e", "pdflatex", "--" + mode)
                text = self.pdf_text()
                for title in ("Local Book", "Parent Book", "Winning Book"):
                    self.assertIn(title, text)
                self.assertNotIn("Losing Book", text)


    def test_typst_native_resource_names_keep_spaces_quotes_and_unicode(self):
        self.prepare()
        metadata = self.doc / "metadata/metadata.yaml"
        text = metadata.read_text()
        for old, new in (("references.bib", 'refs_é "quoted".bib'), ("apa6.csl", 'style_é "quoted".csl')):
            (metadata.parent / old).rename(metadata.parent / new)
            text = text.replace(old, "'" + new + "'")
        metadata.write_text(text)
        self.build("--no-citeproc")
        self.assertIn("Local Book", self.pdf_text())

    def test_typst_csl_front_matter_and_cli_precedence(self):
        self.prepare()
        metadata = self.doc / "metadata/metadata.yaml"
        metadata.write_text(metadata.read_text().replace("apa6.csl", "missing.csl"))
        source = self.doc / "SR/x.md"
        source.write_text(source.read_text().replace("title: T", "title: T\ncsl: apa6.csl"))
        self.build("--no-citeproc")
        self.assertIn("Local Book", self.pdf_text())
        source.write_text(source.read_text().replace("csl: apa6.csl", "csl: missing.csl"))
        for flags in (("--csl", "metadata/apa6.csl"), ("-M", "csl=" + str(self.doc / "metadata/apa6.csl"))):
            with self.subTest(flags=flags):
                self.build("--no-citeproc", *flags)
                self.assertIn("Local Book", self.pdf_text())

    def test_typst_native_citation_forms_compile(self):
        self.prepare()
        source = self.doc / "SR/x.md"
        source.write_text(source.read_text().replace("[@local]", "Author @local; [see @local, p. 2]; [-@local]."))
        self.build("--no-citeproc")
        self.assertIn("Local Book", self.pdf_text())
        self.assertIn("Author", self.pdf_text())

    def test_typst_root_defaults_and_explicit_root(self):
        import pdfmd
        command = ["pandoc", "--pdf-engine=typst"]
        self.assertIn("--pdf-engine-opt=--root=/", pdfmd.typst_filter_args("typst", command))
        for flags in (["--pdf-engine-opt=--root=/chosen"], ["--pdf-engine-opt", "--root=/chosen"]):
            with self.subTest(flags=flags):
                self.assertNotIn("--pdf-engine-opt=--root=/", pdfmd.typst_filter_args("typst", command + flags))
        self.assertNotIn("--pdf-engine-opt=--root=/", pdfmd.typst_filter_args("typst", ["pandoc", "-t", "typst"]))
