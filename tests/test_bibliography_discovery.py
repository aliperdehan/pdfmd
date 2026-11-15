"""The bib auto kind searches once for cited keys not held by the declared sources (D60)."""
from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pdfmd  # noqa: E402
from tests.test_bibliography_layers import Tree  # noqa: E402


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Discovery(Tree):
    def test_no_declared_source_finds_bib_files_beside_document_and_in_metadata(self):
        self.bib("local.bib", "local", "Local Discovery")
        self.bib("metadata/extra.bib", "extra", "Accessory Discovery")
        self.bib("unrelated.bib", "other", "Unrelated Book")
        self.write("d.md", "[@local; @extra]\n")
        done = self.run_pdfmd("--verbose")
        text = self.output(done)
        for title in ("Local Discovery", "Accessory Discovery"):
            self.assertIn(title, text)
        self.assertNotIn("Unrelated Book", text)
        self.assertIn("AUTO BIB", done.stdout + done.stderr)

    def test_missing_keys_extend_both_named_bibliography_and_inline_references(self):
        self.bib("named.bib", "named", "Named Book")
        self.bib("other.bib", "missing", "Discovered Book")
        self.write("d.md", "---\nbibliography: named.bib\nreferences: [{id: inline, type: book, title: Inline Book}]\n---\n"
                   "[@named; @inline; @missing]\n")
        text = self.output(self.run_pdfmd())
        for title in ("Named Book", "Inline Book", "Discovered Book"):
            self.assertIn(title, text)

    def test_cli_sources_are_also_checked_for_missing_keys(self):
        self.bib("named.bib", "named", "Named Book")
        self.bib("other.bib", "missing", "Discovered Book")
        self.write("d.md", "[@named; @missing]\n")
        text = self.output(self.run_pdfmd("--bibliography", "named.bib"))
        self.assertIn("Named Book", text)
        self.assertIn("Discovered Book", text)

    def test_declared_keys_do_not_trigger_a_search_or_a_new_clash(self):
        self.bib("named.bib", "named", "Named Book")
        self.bib("other.bib", "named", "Unwanted Book")
        self.write("d.md", "---\nbibliography: named.bib\n---\n[@named]\n")
        done = self.run_pdfmd("--verbose")
        self.assertIn("Named Book", self.output(done))
        self.assertNotIn("AUTO BIB", done.stdout + done.stderr)
        self.assertNotIn("bibliography key", done.stderr)

    def test_all_matching_files_add_but_declared_sources_win_clashes(self):
        self.bib("named.bib", "same", "Declared Winner")
        self.write("a.bib", "@book{same,title={Automatic Loser}}\n@book{missing,title={First Match}}\n")
        self.bib("b.bib", "missing", "Last Match")
        self.write("d.md", "---\nbibliography: named.bib\n---\n[@same; @missing]\n")
        done = self.run_pdfmd()
        text = self.output(done)
        self.assertIn("Declared Winner", text)
        self.assertIn("Last Match", text)
        self.assertNotIn("Automatic Loser", text)
        warnings = [line for line in done.stderr.splitlines() if line.startswith("WARN")]
        self.assertEqual(len(warnings), 2, done.stderr)
        self.assertTrue(any("named.bib" in line and "a.bib" in line for line in warnings))
        self.assertTrue(any("b.bib" in line and "a.bib" in line for line in warnings))

    def test_off_and_explicit_only_stop_discovery_but_keep_declared_sources(self):
        self.bib("named.bib", "named", "Named Book")
        self.bib("other.bib", "missing", "Unwanted Book")
        for front, args in [("", ("--no-auto", "bib")), ("pdfmd-options: {no-auto: bib}\n", ()),
                            ("pdfmd-options: {auto: {bib: explicit-only}}\n", ()),
                            ("pdfmd-options: {auto: {bib: off}}\n", ())]:
            with self.subTest(front=front, args=args):
                self.write("d.md", "---\nbibliography: named.bib\n" + front + "---\n[@named; @missing]\n")
                done = self.run_pdfmd(*args)
                text = self.output(done)
                self.assertIn("Named Book", text)
                self.assertNotIn("Unwanted Book", text)
                self.assertIn("missing?", text)

    def test_folder_setting_and_bare_no_auto_disable_discovery(self):
        self.bib("other.bib", "missing", "Unwanted Book")
        self.write(".pdfmd/config.yaml", "options: {auto: {bib: explicit-only}}\n")
        self.write("d.md", "[@missing]\n")
        done = self.run_pdfmd()
        self.assertNotIn("Unwanted Book", self.output(done))
        (self.doc / ".pdfmd/config.yaml").unlink()
        self.assertNotIn("Unwanted Book", self.output(self.run_pdfmd("--no-auto")))

    def test_only_real_citations_count_and_search_is_not_recursive(self):
        self.bib("skip.bib", "skip", "Unwanted Book")
        self.bib("deep/hidden.bib", "hidden", "Hidden Book")
        self.write("d.md", "`@skip`\n\n```text\n@skip\n```\n\n<!-- @skip -->\n\n"
                   "    @skip\n\nname@example.org [link](https://example.org/@skip) $x @skip$\n\n[@hidden]\n")
        done = self.run_pdfmd("--verbose")
        text = self.output(done)
        self.assertNotIn("Unwanted Book", text)
        self.assertNotIn("Hidden Book", text)
        self.assertNotIn("AUTO BIB", done.stdout + done.stderr)
        self.assertIn("hidden?", text)

    def test_parent_metadata_resources_and_unpacked_folder_are_candidates(self):
        self.write("../metadata/metadata.yaml", "title: Parent\n")
        self.bib("../metadata/project.bib", "project", "Project Book")
        self.bib("d.unpacked/local.bib", "local", "Unpacked Book")
        self.write("d.md", "[@project; @local]\n")
        text = self.output(self.run_pdfmd())
        self.assertIn("Project Book", text)
        self.assertIn("Unpacked Book", text)

    def test_unfindable_key_stays_missing_for_pandoc(self):
        self.bib("other.bib", "other", "Unwanted Book")
        self.write("d.md", "[@unknown; @unknown]\n")
        done = self.run_pdfmd("--strict")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual((done.stdout + done.stderr).count("citation unknown not found"), 1)

    def test_discovered_sources_reach_both_native_bibliography_writers(self):
        self.bib("auto.bib", "found", "Found Book")
        self.write("d.md", "[@found]\n")
        for method in ("natbib", "biblatex"):
            with self.subTest(method=method):
                tex = self.output(self.run_pdfmd("--" + method, target="tex"), "tex")
                self.assertIn("auto.bib" if method == "biblatex" else "auto", tex)

    def test_real_pdfs_use_discovered_sources(self):
        if not all(shutil.which(tool) for tool in ("pdflatex", "pdftotext", "bibtex", "biber")):
            self.skipTest("needs TeX, bibliography tools and pdftotext")
        self.bib("auto.bib", "found", "Discovered Book")
        for method in ("citeproc", "natbib", "biblatex"):
            with self.subTest(method=method):
                self.write("d.md", f"---\npdfmd-options: {{citation-engine: {method}}}\n---\n[@found]\n")
                done = self.run_pdfmd("-e", "pdflatex", "--no-cache", "--engine-fallback", "missing", target="pdf")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                import subprocess
                text = subprocess.run(["pdftotext", str(self.doc / "out.pdf"), "-"],
                                      capture_output=True, text=True, check=True).stdout
                self.assertIn("Discovered Book", text)


class Bounded(Tree):
    def test_setup_exposes_bib_in_all_existing_auto_rows(self):
        from pdfmd_setup import registry
        rows = {setting.key: setting for setting in registry.settings_for(pdfmd.NO_AUTO_KINDS)}
        for key in ("options.no-auto", "options.auto.explicit-only", "options.auto.on"):
            self.assertIn("bib", dict(rows[key].choices))

    def test_one_finite_scan_for_all_missing_keys_and_engine_retries(self):
        from pdfmd_bibliography import sources
        self.bib("one.bib", "first", "First")
        self.bib("two.bib", "second", "Second")
        document = self.write("d.md", "[@first; @second; @never]\n")
        with patch.dict(pdfmd.BUILD, {"bibliography-discovery": None}), patch.dict("os.environ", self.env):
            with patch("pdfmd_bibliography.discovery.candidates", wraps=__import__(
                    "pdfmd_bibliography.discovery", fromlist=["candidates"]).candidates) as scan:
                first = sources.merge_sources([document], [], [])
                second = sources.merge_sources([document], [], [])
            self.assertEqual(scan.call_count, 1)
            self.assertEqual(first, second)
            self.assertEqual(len(first["bibliography"]), 2)

    def test_no_matches_are_cached_too(self):
        from pdfmd_bibliography import discovery, sources
        document = self.write("d.md", "[@never; @also_missing]\n")
        with patch.dict(pdfmd.BUILD, {"bibliography-discovery": None}), patch.dict("os.environ", self.env):
            with patch.object(discovery, "candidates", wraps=discovery.candidates) as scan:
                self.assertEqual(sources.merge_sources([document], [], []), {})
                self.assertEqual(sources.merge_sources([document], [], []), {})
            self.assertEqual(scan.call_count, 1)
