"""Command-line Pandoc paths retain the invocation folder when metadata changes the build's cwd."""

from __future__ import annotations

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
import pdfmd  # noqa: E402,F401
from pandoc_support import needs_pandoc  # noqa: E402
from pdfmd_args.paths import invocation_paths  # noqa: E402


class Tokens(unittest.TestCase):
    def test_urls_stdin_builtins_and_path_executables_keep_their_meaning(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-cli-tokens-") as scratch:
            origin = Path(scratch)
            arguments = ["--csl=https://example.org/style.csl", "--bibliography", "https://example.org/refs.bib",
                         "--include-in-header", "-", "--highlight-style", "pygments", "--template", "named",
                         "--filter", "pandoc-crossref", "--pdf-engine", "typst"]
            self.assertEqual(invocation_paths(arguments, origin), arguments)
            (origin / "f.lua").write_text("", encoding="utf-8")
            (origin / "filter.py").write_text("", encoding="utf-8")
            self.assertEqual(invocation_paths(["--lua-filter", "f.lua", "--filter=./filter.py"], origin),
                             ["--lua-filter", str(origin / "f.lua"), "--filter=" + str(origin / "filter.py")])

    def test_a_local_bare_file_wins_but_an_absent_data_file_name_keeps_pandocs_lookup(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-cli-tokens-") as scratch:
            origin = Path(scratch)
            (origin / "style.csl").write_text("local", encoding="utf-8")
            self.assertEqual(invocation_paths(["--csl", "style.csl", "--reference-doc=named.docx"], origin),
                             ["--csl", str(origin / "style.csl"), "--reference-doc=named.docx"])

    def test_an_input_absent_from_the_start_folder_is_left_for_the_build_folder(self):
        # Before 3.33.217 every CLI path counted from the build's working folder; one not found here keeps that meaning.
        with tempfile.TemporaryDirectory(prefix="pdfmd-cli-tokens-") as scratch:
            origin = Path(scratch)
            arguments = ["--lua-filter", "f.lua", "-Hsub/head.tex", "--filter=./absent.py", "--data-dir", "data",
                         "--epub-embed-font", "fonts/*.ttf", "--resource-path", os.pathsep.join(["", ".", "missing"])]
            self.assertEqual(invocation_paths(arguments, origin), arguments)

    def test_outputs_count_from_the_start_folder_and_found_inputs_and_globs_are_anchored(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-cli-tokens-") as scratch:
            origin = Path(scratch)
            (origin / "fonts").mkdir()
            (origin / "fonts" / "a.ttf").write_text("", encoding="utf-8")
            (origin / "here").mkdir()
            self.assertEqual(
                invocation_paths(["--extract-media", "media", "--log=build.log", "--epub-embed-font", "fonts/*.ttf",
                                  "--resource-path", os.pathsep.join([".", "missing", "here"])], origin),
                ["--extract-media", str(origin / "media"), "--log=" + str(origin / "build.log"),
                 "--epub-embed-font", str(origin / "fonts/*.ttf"),
                 "--resource-path", os.pathsep.join([".", "missing", str(origin / "here")])])

    def test_metadata_variables_and_tokens_after_the_separator_are_literal(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-cli-tokens-") as scratch:
            arguments = ["-M", "--lua-filter=literal", "-V", "--template=literal", "--metadata=csl:relative.csl",
                         "--", "--lua-filter", "literal.lua"]
            self.assertEqual(invocation_paths(arguments, Path(scratch)), arguments)

    @needs_pandoc(3, 1, 3)
    def test_a_builtin_highlight_style_wins_over_a_same_named_local_file(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-cli-tokens-") as scratch:
            origin = Path(scratch)
            (origin / "pygments").write_text("not a style", encoding="utf-8")
            self.assertEqual(invocation_paths(["--highlight-style", "pygments"], origin),
                             ["--highlight-style", "pygments"])


@needs_pandoc(3, 1, 3)
class Builds(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="pdfmd-cli-paths-")
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                    "XDG_CONFIG_HOME": str(self.base / "config"), "XDG_CACHE_HOME": str(self.base / "cache"),
                    "XDG_DATA_HOME": str(self.base / "data"), "APPDATA": str(self.base / "config")}
        self.write("doc/metadata/metadata.yaml", "lang: en\n")
        self.write("doc/c.md", "Hello.\n")
        self.write("doc/f.lua", 'function Str(s) if s.text == "Hello." then return pandoc.Str("Passed.") end end\n')

    def write(self, name, text):
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def build(self, *options, target="html", suffix="html", document="doc/c.md"):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), document, "--to", target,
                               "-o", "out." + suffix, "--no-backup", *options],
                              cwd=self.base, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.base / ("out." + suffix)).read_text(encoding="utf-8")

    def test_cli_lua_filter_uses_the_start_folder_with_discovered_or_explicit_metadata(self):
        for spelling in (("--lua-filter", "doc/f.lua"), ("--lua-filter=doc/f.lua",),
                         ("-L", "doc/f.lua"), ("-Ldoc/f.lua",)):
            for metadata in ((), ("-y", "doc/metadata/metadata.yaml")):
                with self.subTest(spelling=spelling, metadata=metadata):
                    self.assertIn("Passed.", self.build(*spelling, *metadata))

    def test_a_path_relative_to_the_build_folder_still_works_when_absent_from_the_start_folder(self):
        # 3.33.217 first broke these: the build's working folder is the metadata folder, else the document's folder.
        self.write("plain/p.md", "Hello.\n")
        self.write("plain/near.lua", 'function Str(s) if s.text == "Hello." then return pandoc.Str("Plain.") end end\n')
        self.assertIn("Plain.", self.build("--lua-filter", "near.lua", document="plain/p.md"))
        self.write("doc/metadata/near.lua", 'function Str(s) if s.text == "Hello." then '
                   'return pandoc.Str("Metadata folder.") end end\n')
        self.assertIn("Metadata folder.", self.build("--lua-filter", "near.lua"))

    def test_one_cli_filter_name_serves_documents_in_different_folders(self):
        for folder in ("a", "b"):
            self.write(folder + "/x.md", "Hello.\n")
            self.write(folder + "/near.lua", 'function Str(s) if s.text == "Hello." then '
                       'return pandoc.Str("From ' + folder + '.") end end\n')
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "a/x.md", "b/x.md", "--to", "html",
                               "--no-backup", "--lua-filter", "near.lua"], cwd=self.base, env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for folder in ("a", "b"):
            self.assertIn("From " + folder + ".", (self.base / folder / "x.html").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("typst"), "needs Typst")
    def test_the_reported_typst_pdf_build(self):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "doc/c.md", "--engine", "typst",
                               "--lua-filter", "doc/f.lua"], cwd=self.base, env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.base / "doc/c.pdf").is_file())

    def test_resource_path_keeps_each_invocation_relative_directory(self):
        self.write("assets/payload.txt", "Passed.")
        probe = self.write("probe.lua", 'function Pandoc(d) local _, text = pandoc.mediabag.fetch("payload.txt"); '
                           'assert(text == "Passed."); return d end\n')
        for spelling in (("--resource-path", "unused" + os.pathsep + "assets"), ("--resource-path=assets",)):
            with self.subTest(spelling=spelling):
                self.build(*spelling, "--lua-filter", str(probe))

    def test_cli_bibliography_and_csl_are_read_from_the_start_folder(self):
        self.write("doc/c.md", "Cite @k.\n")
        self.write("doc/r.bib", "@book{k, title={Passed}, author={A, B}, year={2000}}\n")
        default = subprocess.run(["pandoc", "--print-default-data-file", "default.csl"], env=self.env,
                                 capture_output=True, text=True, check=True)
        self.write("doc/style.csl", default.stdout)
        for options in (("--bibliography", "doc/r.bib", "--csl", "doc/style.csl"),
                        ("--bibliography=doc/r.bib", "--csl=doc/style.csl")):
            with self.subTest(options=options):
                html = self.build(*options)
                self.assertIn("Passed", html)
                self.assertNotIn("citation-not-found", html)

    def test_include_template_and_defaults_files_have_the_same_path_rule(self):
        self.write("doc/header.html", '<meta name="probe" content="Header">\n')
        self.write("doc/before.html", "Before\n")
        self.write("doc/after.html", "After\n")
        self.write("doc/template.html", "$include-before$ $body$ $include-after$ $header-includes$ $title$\n")
        self.write("doc/defaults.yaml", "metadata:\n  title: Defaults\n")
        html = self.build("-H", "doc/header.html", "-Bdoc/before.html", "--include-after-body=doc/after.html",
                          "--template", "doc/template.html", "--defaults=doc/defaults.yaml")
        for expected in ("Header", "Before", "After", "Defaults"):
            self.assertIn(expected, html)

    def test_a_bare_cli_csl_still_uses_pandocs_user_data_folder(self):
        self.write("doc/c.md", "Cite @k.\n")
        bibliography = self.write("doc/r.bib", "@book{k, title={Passed}, year={2000}}\n")
        default = subprocess.run(["pandoc", "--print-default-data-file", "default.csl"], env=self.env,
                                 capture_output=True, text=True, check=True)
        self.write("pandoc-data/csl/style.csl", default.stdout)
        html = self.build("--bibliography", str(bibliography), "--csl", "style.csl", "--data-dir", "pandoc-data")
        self.assertIn("Passed", html)

    @unittest.skipIf(os.name == "nt", "executable-script shebangs need POSIX")
    def test_external_filter_paths_are_anchored_and_program_names_still_use_path(self):
        script = ('#!/usr/bin/env python3\nimport json, sys\n'
                  'doc = json.load(sys.stdin)\n'
                  'doc["blocks"][0]["c"][0]["c"] = "Passed."\njson.dump(doc, sys.stdout)\n')
        path = self.write("doc/filter.py", script)
        path.chmod(0o755)
        self.assertIn("Passed.", self.build("--filter", "doc/filter.py"))
        named = self.write("bin/probe-filter", script)
        named.chmod(0o755)
        self.env["PATH"] = str(named.parent) + os.pathsep + self.env.get("PATH", "")
        self.assertIn("Passed.", self.build("--filter", "probe-filter"))

    def test_filter_paths_inside_files_keep_their_existing_origins(self):
        self.write("doc/metadata/meta-filter.lua", 'function Str(s) if s.text == "Hello." then '
                   'return pandoc.Str("Metadata.") end end\n')
        self.write("doc/metadata/metadata.yaml", "pdfmd-options:\n  lua-filter: meta-filter.lua\n")
        self.assertIn("Metadata.", self.build())
        self.write("doc/c.md", "---\npdfmd-options:\n  lua-filter: f.lua\n---\n\nHello.\n")
        self.assertIn("Passed.", self.build())


if __name__ == "__main__":
    unittest.main()
