"""Top-level pdfmd options keep each layer's explicit block and Pandoc/Quarto metadata safe."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd


class Options(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-top-options-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                    "XDG_CONFIG_HOME": str(self.root / "config"), "XDG_CACHE_HOME": str(self.root / "cache"),
                    "XDG_DATA_HOME": str(self.root / "data")}

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def options(self, front, name="d.md"):
        return pdfmd.frontmatter_pdfmd_options(self.write(name, "---\n" + front + "---\n\nText.\n"))

    def run_pdfmd(self, *args):
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), *args, "--no-stamp", "--no-backup"],
                              check=False, cwd=self.root, env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout + done.stderr

    def test_known_keys_only_and_an_explicit_block_wins_even_for_false_or_null(self):
        data = self.options("engine: typst\nflavour: pandoc\nmade-up: yes\nrewrite: true\ncache: true\n"
                            "pdfmd-options: {engine: xelatex, rewrite: false, cache: null}\n")
        self.assertEqual(data, {"engine": "xelatex", "flavour": "pandoc", "rewrite": False, "cache": None})

    def test_pandoc_and_citeproc_keys_are_never_options(self):
        data = self.options("toc: true\nlang: en-GB\nfontsize: 12pt\ncss: s.css\nheader: Text\n"
                            "pdf-engine: xelatex\nbibliography: refs.bib\nlink-citations: true\nflavour: pandoc\n")
        self.assertEqual(data, {"flavour": "pandoc"})

    def test_metadata_is_preserved_and_explicit_mapping_replaces_the_same_top_level_key(self):
        path = self.write("metadata.yaml", "flavour: pandoc\ncache: {aux: true, plots: true}\n"
                          "pdfmd-options: {cache: {plots: false}}\n")
        before = path.read_bytes()
        data = pdfmd.metadata_file_yaml(path)
        self.assertEqual(data["flavour"], "pandoc")
        self.assertEqual(data["cache"], {"aux": True, "plots": True})
        self.assertEqual(data["pdfmd-options"], {"flavour": "pandoc", "cache": {"plots": False}})
        self.assertEqual(path.read_bytes(), before)

    def test_explicit_null_engine_does_not_reenter_the_legacy_top_level_fallback(self):
        document = self.write("d.md", "---\nengine: typst\npdfmd-options: {engine: null}\n---\nText.\n")
        metadata = self.write("metadata.yaml", "engine: typst\npdfmd-options: {engine: null}\n")
        with mock.patch.object(pdfmd, "config_options", return_value={}):
            self.assertIsNone(pdfmd.frontmatter_engine(document))
            document.write_text("Text.\n", encoding="utf-8")
            self.assertIsNone(pdfmd.frontmatter_engine(document, [metadata]))

    def test_document_metadata_folder_and_kit_layers_have_the_same_rule(self):
        folder = self.root / "course"
        self.write("course/.pdfmd/metadata.yaml", "flavour: gfm\n")
        document = self.write("course/d.md", "---\nflavour: pandoc\n---\nText.\n")
        metadata = self.write("course/metadata.yaml", "flavour: markdown_strict\n")
        kit = self.write("kits/x/metadata.yaml", "flavour: commonmark\n")
        self.assertEqual(pdfmd.first_pdfmd_option(document, [kit, folder / ".pdfmd/metadata.yaml", metadata], "flavour"), "pandoc")
        document.write_text("Text.\n", encoding="utf-8")
        self.assertEqual(pdfmd.first_pdfmd_option(document, [kit, folder / ".pdfmd/metadata.yaml", metadata], "flavour"), "markdown_strict")
        self.assertEqual(pdfmd.metadata_file_yaml(kit)["pdfmd-options"]["flavour"], "commonmark")
        self.assertEqual(pdfmd.metadata_file_yaml(folder / ".pdfmd/metadata.yaml")["pdfmd-options"]["flavour"], "gfm")

    def test_quarto_keys_and_r_markdown_output_are_protected(self):
        for suffix in ("qmd", "Rmd"):
            with self.subTest(suffix=suffix):
                data = self.options("engine: jupyter\neditor: visual\nformat: html\noutput: html_document\n"
                                    "execute: true\nflavour: pandoc\n", "d." + suffix)
                self.assertNotIn("engine", data)
                self.assertNotIn("editor", data)
                self.assertNotIn("output", data)
                # A non-clashing key can still be read when a reliable Quarto schema was shipped.
                self.assertEqual(data.get("flavour"), "pandoc")

    def test_missing_quarto_schema_disables_all_top_level_options_for_routed_inputs(self):
        from pdfmd_args import options

        with mock.patch.object(options, "key_data", return_value={"template_keys": [], "documented_keys": [], "quarto_keys": None}):
            data = self.options("flavour: pandoc\npdfmd-options: {rewrite: false}\n", "d.qmd")
        self.assertEqual(data, {"rewrite": False})

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_cli_reads_layers_reports_each_key_once_and_keeps_custom_template_metadata(self):
        self.write(".pdfmd/metadata.yaml", "flavour: gfm\n")
        self.write("kits/x/.kit", "kit-format: 1\nname: x\ndefaults: metadata.yaml\n")
        self.write("kits/x/metadata.yaml", "flavour: commonmark\n")
        self.write("metadata.yaml", "flavour: pandoc\n")
        self.write("d.md", "---\nkit: x\n---\n\nHello.\n")
        self.write("template.txt", "$flavour$\n$body$\n")
        log = self.run_pdfmd("d.md", "--to", "plain", "-s", "-o", "out.txt", "--template", "template.txt", "--verbose")
        self.assertTrue((self.root / "out.txt").read_text().startswith("pandoc\n"))
        lines = [line for line in log.splitlines() if line.startswith("OPTIONS") and "top level" in line]
        self.assertEqual(sum("kit:" in line for line in lines), 1, log)
        self.assertTrue(any("flavour: pandoc" in line and "metadata.yaml" in line for line in lines), log)
        self.assertEqual(len(lines), len(set(lines)), log)

    @unittest.skipUnless(shutil.which("pandoc") and shutil.which("typst"), "needs Pandoc and Typst")
    def test_top_level_engine_builds_with_typst(self):
        self.write("d.md", "---\nengine: typst\n---\n\nHello.\n")
        log = self.run_pdfmd("d.md", "-o", "out.pdf", "--verbose", "--no-auto", "font")
        self.assertTrue((self.root / "out.pdf").read_bytes().startswith(b"%PDF-"))
        self.assertIn("typst", log)
        self.assertIn("OPTIONS  engine: typst (top level of ", log)
        self.assertIn("d.md)", log)

    @unittest.skipUnless(shutil.which("pandoc") and shutil.which("xelatex"), "needs Pandoc and XeLaTeX")
    def test_explicit_engine_overrides_the_top_level_engine_in_a_real_build(self):
        self.write("d.md", "---\nengine: typst\npdfmd-options: {engine: xelatex}\n---\n\nHello.\n")
        log = self.run_pdfmd("d.md", "-o", "out.pdf", "--verbose", "--no-auto", "font")
        self.assertTrue((self.root / "out.pdf").read_bytes().startswith(b"%PDF-"))
        self.assertIn("--pdf-engine=xelatex", log)
        self.assertNotIn("OPTIONS  engine: typst", log)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_quarto_cli_handoff_keeps_jupyter_and_editor_metadata(self):
        script = self.write("bin/fake_quarto.py", "import sys\nfrom pathlib import Path\n"
                            "text = Path(sys.argv[2]).read_text(encoding='utf-8')\nassert 'engine: jupyter' in text\n"
                            "assert 'editor: visual' in text\nPath(sys.argv[sys.argv.index('-o')+1]).write_text('Quarto')\n")
        # Windows runs no shebang: the launcher is a command script there (as for a real `quarto.cmd`)
        tool = script.with_name("quarto.cmd" if os.name == "nt" else "quarto")
        tool.write_text(f'@"{sys.executable}" "{script}" %*\n' if os.name == "nt"
                        else f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        tool.chmod(0o755)
        self.env["PATH"] = str(tool.parent) + os.pathsep + self.env.get("PATH", "")
        self.write("d.qmd", "---\nengine: jupyter\neditor: visual\n---\n\nHello.\n")
        log = self.run_pdfmd("d.qmd", "--to", "html", "-o", "out.html", "--verbose")
        self.assertEqual((self.root / "out.html").read_text(), "Quarto")
        self.assertNotIn("OPTIONS  engine:", log)
        self.assertNotIn("OPTIONS  editor:", log)


def same_pandoc_as_the_shipped_data() -> bool:
    """The drift check means something only against the Pandoc the data was made from, with its manual installed: CI's
    other Pandoc versions (3.1.3, latest) have other keys and a different version line, and may have no manual."""
    if not shutil.which("pandoc"):
        return False
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import pandoc_keys
    finally:
        sys.path.pop(0)
    shipped = json.loads((ROOT / "lib/pdfmd_args/pandoc_keys.json").read_text(encoding="utf-8"))["pandoc"]
    line = subprocess.run(["pandoc", "--version"], capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout
    return line.splitlines()[:1] == [shipped] and pandoc_keys.manual_path() is not None


SAME_PANDOC = same_pandoc_as_the_shipped_data()
NOT_THE_SAME = "the shipped key data was made from another Pandoc (or its manual is missing)"


class DerivedKeys(unittest.TestCase):
    @unittest.skipUnless(SAME_PANDOC, NOT_THE_SAME)
    def test_shipped_data_matches_installed_pandoc_and_quarto(self):
        script = ROOT / "scripts/pandoc_keys.py"
        done = subprocess.run([sys.executable, str(script), "--check"], check=False, capture_output=True, text=True,
                              env={**os.environ}, stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_key_data_is_shipped_with_the_wheel(self):
        try:
            import tomllib
        except ImportError:  # Python 3.9 and 3.10
            self.skipTest("needs tomllib (Python 3.11)")

        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn("*.json", config["tool"]["setuptools"]["package-data"]["pdfmd_args"])
        data = json.loads((ROOT / "lib/pdfmd_args/pandoc_keys.json").read_text(encoding="utf-8"))
        self.assertTrue({"toc", "lang", "fontsize"} <= set(data["template_keys"]))
        self.assertIn("link-citations", data["documented_keys"])

    @unittest.skipUnless(SAME_PANDOC, NOT_THE_SAME)
    def test_drift_is_an_error(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-key-drift-") as scratch:
            data = json.loads((ROOT / "lib/pdfmd_args/pandoc_keys.json").read_text(encoding="utf-8"))
            data["template_keys"].remove("toc")
            path = Path(scratch) / "keys.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "scripts/pandoc_keys.py"), "--check", "--output", str(path)],
                                  check=False, capture_output=True, text=True, env={**os.environ}, stdin=subprocess.DEVNULL)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("drifted", done.stderr)


if __name__ == "__main__":
    unittest.main()
