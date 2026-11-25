"""The global config file (~/.config/pdfmd/config.yaml) and the state kept beside it."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402


class ConfigCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self._saved = {key: os.environ.get(key) for key in ("PDFMD_CONFIG", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "APPDATA", "LOCALAPPDATA")}
        os.environ["XDG_CONFIG_HOME"] = str(self.root / "config")
        os.environ["XDG_CACHE_HOME"] = str(self.root / "cache")
        os.environ["APPDATA"] = str(self.root / "config")          # the same places on Windows
        os.environ["LOCALAPPDATA"] = str(self.root / "cache")
        self.config = self.root / "config" / "pdfmd" / "config.yaml"
        os.environ["PDFMD_CONFIG"] = str(self.config)
        pdfmd.load_config.cache_clear()
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        pdfmd.load_config.cache_clear()

    def write_config(self, text: str):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(text, encoding="utf-8")
        pdfmd.load_config.cache_clear()

    def document(self, front: str = "", name: str = "doc.md") -> Path:
        path = self.root / name
        path.write_text(f"---\n{front}---\ntext\n" if front else "text\n", encoding="utf-8")
        return path


class Loading(ConfigCase):
    def test_no_file_means_no_settings(self):
        self.assertEqual(pdfmd.load_config(), {})
        self.assertEqual(pdfmd.config_options(), {})

    def test_options_and_translit_are_read(self):
        self.write_config("translit: [greek]\noptions:\n  parts: auto\n  cache: {aux: true}\n")
        self.assertEqual(pdfmd.load_config()["translit"], ["greek"])
        self.assertEqual(pdfmd.config_options()["parts"], "auto")

    def test_a_broken_or_odd_file_is_reported_and_ignored(self):
        self.write_config("options: [unclosed\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(pdfmd.load_config(), {})
        self.assertIn("cannot be read", err.getvalue())
        self.write_config("just a string\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(pdfmd.load_config(), {})
        self.assertIn("mapping", err.getvalue())

    def test_unknown_settings_are_named(self):
        self.write_config("fallbak: char\noptions: {}\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            pdfmd.load_config()
        self.assertIn("fallbak", err.getvalue())

    def test_an_empty_PDFMD_CONFIG_reads_the_default_user_file(self):
        self.write_config("options: {parts: auto}\n")
        for value in (None, ""):
            with self.subTest(value=value):
                if value is None:
                    os.environ.pop("PDFMD_CONFIG", None)
                else:
                    os.environ["PDFMD_CONFIG"] = value
                pdfmd.load_config.cache_clear()
                self.assertEqual(pdfmd.config_path(), self.config)
                self.assertEqual(pdfmd.config_options(), {"parts": "auto"})

    def test_a_nonempty_whitespace_override_can_still_disable_the_user_file(self):
        self.write_config("options: {parts: auto}\n")
        os.environ["PDFMD_CONFIG"] = " "
        self.assertEqual(pdfmd.config_options(), {})

    def test_config_off_spellings_disable_the_user_file(self):
        self.write_config("options: {parts: auto}\n")
        for value in ("off", "OFF", " none "):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"PDFMD_CONFIG": value}):
                pdfmd.load_config.cache_clear()
                self.assertIsNone(pdfmd.config_path())
                self.assertEqual(pdfmd.config_options(), {})

    def test_reports_explain_why_the_user_config_is_off(self):
        self.write_config("options: {parts: auto}\n")
        for args in (("--show-config",), ("--doctor",), ("--verbose", "--show-config")):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *args],
                                        cwd=self.root, capture_output=True, encoding="utf-8",
                                        env={**os.environ, "PDFMD_CONFIG": " OFF ", "PDFMD_NO_PROMPT": "1"})
                report = result.stderr if "--verbose" in args else result.stdout
                self.assertIn("switched off by PDFMD_CONFIG", report)


class Precedence(ConfigCase):
    def install_config(self, text):
        prefix = self.root / "prefix"
        path = prefix / "etc" / "pdfmd" / "config.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        patch = mock.patch.object(sys, "prefix", str(prefix))
        patch.start()
        self.addCleanup(patch.stop)
        return path

    def test_off_leaves_the_per_install_config_active(self):
        self.write_config("options: {parts: auto}\n")
        self.install_config("options: {default-output: gfm}\n")
        with mock.patch.dict(os.environ, {"PDFMD_CONFIG": "none"}):
            self.assertEqual(pdfmd.config_options(), {"default-output": "gfm"})

    def test_per_install_options_win_over_user_but_yield_to_local_layers(self):
        self.write_config("translit: [greek]\noptions: {default-output: html, cache: {aux: true}}\n")
        self.install_config("translit: [hangul]\noptions: {default-output: gfm, cache: {location: document}}\n")
        self.assertEqual(pdfmd.load_config()["translit"], ["hangul"])
        self.assertEqual(pdfmd.config_options()["cache"], {"aux": True, "location": "document"})
        self.assertEqual(pdfmd.cascaded_option(self.document(), [], "default-output"), "gfm")
        project = self.root / ".pdfmd" / "config.yaml"
        project.parent.mkdir()
        project.write_text("options: {default-output: typst}\n", encoding="utf-8")
        folder = self.root / "child" / ".pdfmd" / "config.yaml"
        folder.parent.mkdir(parents=True)
        doc = self.document(name="child/doc.md")
        self.assertEqual(pdfmd.cascaded_option(doc, [], "default-output"), "typst")
        folder.write_text("options: {default-output: docx}\n", encoding="utf-8")
        pdfmd.folder_walk.cache_clear()
        self.addCleanup(pdfmd.folder_walk.cache_clear)
        self.assertEqual(pdfmd.cascaded_option(doc, [], "default-output"), "docx")
        self.document("pdfmd-options: {default-output: odt}\n", name="child/doc.md")
        self.assertEqual(pdfmd.cascaded_option(doc, [], "default-output"), "odt")

    def test_show_config_and_which_name_the_per_install_file(self):
        self.write_config("options: {parts: auto}\n")
        path = self.install_config("options: {parts: off}\n")
        doc = self.document()
        for command in (lambda: pdfmd.config_report(), lambda: pdfmd.which_command([doc.name], SimpleNamespace())):
            shown = io.StringIO()
            with mock.patch.object(pdfmd, "find_markdown", return_value=doc), contextlib.redirect_stdout(shown):
                self.assertTrue(command())
            self.assertIn("per-install", shown.getvalue())
            self.assertIn(str(path), shown.getvalue())

    def test_relative_preamble_is_read_from_the_config_that_names_it(self):
        self.write_config("options: {preamble: base.tex}\n")
        base = self.config.with_name("base.tex")
        base.touch()
        install = self.install_config("options: {preamble+: override.tex}\n")
        override = install.with_name("override.tex")
        override.touch()
        self.assertEqual(pdfmd.frontmatter_extra_preambles(self.document()), [base.resolve(), override.resolve()])

    def test_the_config_is_the_lowest_source(self):
        self.write_config("options:\n  parts: auto\n  default-output: html\n")
        plain = self.document()
        self.assertEqual(pdfmd.cascaded_option(plain, [], "default-output"), "html")  # the config's
        own = self.document("pdfmd-options:\n  default-output: typ\n", "own.md")
        self.assertEqual(pdfmd.cascaded_option(own, [], "default-output"), "typ")      # the document wins
        metadata = self.root / "metadata.yaml"
        metadata.write_text("pdfmd-options:\n  default-output: docx\n", encoding="utf-8")
        self.assertEqual(pdfmd.cascaded_option(plain, [metadata], "default-output"), "docx")  # then metadata files
        self.assertEqual(pdfmd.parts_setting(plain, []), "auto")

    def test_engine_and_cache_come_from_the_config_too(self):
        self.write_config("options:\n  pdf-engine: xelatex\n  cache: {aux: true}\n")
        plain = self.document()
        self.assertEqual(pdfmd.frontmatter_engine(plain), "xelatex")
        self.assertTrue(pdfmd.cache_settings(plain, [], None)["aux"])
        own = self.document("pdfmd-options:\n  pdf-engine: lualatex\n", "own.md")
        self.assertEqual(pdfmd.frontmatter_engine(own), "lualatex")


class State(ConfigCase):
    def test_the_trust_store_moves_out_of_the_cache(self):
        old = pdfmd.cache_root() / "embedded-trust.txt"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text("abc123 filter.lua\n", encoding="utf-8")
        self.assertEqual(pdfmd.trusted_hashes(), {"abc123"})
        self.assertFalse(old.exists())
        self.assertEqual(pdfmd.trust_store_path(), pdfmd.config_root() / "trusted-filters.txt")
        self.assertTrue(pdfmd.trust_store_path().is_file())
        pdfmd.remember_trusted([("def456", "other.lua")])
        self.assertEqual(pdfmd.trusted_hashes(), {"abc123", "def456"})

    def test_clearing_the_cache_leaves_the_state(self):
        pdfmd.remember_trusted([("abc123", "f.lua")])
        import shutil

        shutil.rmtree(pdfmd.cache_root(), ignore_errors=True)
        self.assertEqual(pdfmd.trusted_hashes(), {"abc123"})

    def test_init_writes_a_commented_template_once(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(pdfmd.config_report(init=True))
        self.assertTrue(self.config.is_file())
        self.assertIn("fallback", self.config.read_text(encoding="utf-8"))
        pdfmd.load_config.cache_clear()
        self.assertEqual(pdfmd.config_options(), {})  # everything in it is commented out
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pdfmd.config_report(init=True)
        self.assertIn("exists already", out.getvalue())


if __name__ == "__main__":
    unittest.main()
