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
                resources = list((self.root / "cache").rglob("*.bib"))
                self.assertTrue(any("Inline {Book}" in p.read_text(encoding="utf-8") for p in resources))

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
