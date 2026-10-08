"""pdfmd --setup: the numbered list, the config it writes, and the full-screen one when prompt_toolkit is there."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
from pdfmd_setup import fancy, registry, settings_for  # noqa: E402

try:
    import yaml
except ImportError:                                         # pragma: no cover
    yaml = None

SETTINGS = settings_for(pdfmd.NO_AUTO_KINDS)


def number(key: str) -> int:
    return [setting.key for setting in SETTINGS if setting.store == "config" or "." not in key].index(key) + 1 \
        if False else [setting.key for setting in SETTINGS].index(key) + 1


@unittest.skipUnless(yaml, "needs PyYAML")
class Plain(unittest.TestCase):
    def run_setup(self, lines: list[str], config: str | None = None, *flags: str):
        directory = tempfile.mkdtemp(prefix="pdfmd-setup-")
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        path = Path(directory) / "config.yaml"
        if config is not None:
            path.write_text(config, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--setup", *flags], input="\n".join(lines) + "\n",
                              capture_output=True, text=True, env={**os.environ, "PDFMD_CONFIG": str(path)})
        return done, path

    def test_a_choice_is_saved_to_the_config_file(self):
        fallback, engine = number("options.fallback"), number("options.pdf-engine")
        done, path = self.run_setup([str(fallback), "2", str(engine), "4", "s"])
        self.assertEqual(done.returncode, 0, done.stderr)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data, {"options": {"fallback": "char", "pdf-engine": "typst"}})
        self.assertIn("Saved", done.stdout)
        if not fancy.available():
            self.assertIn("pdfmd --install tui", done.stdout)       # the nudge to the full-screen one

    def test_on_off_settings_are_booleans_and_a_list_is_toggled(self):
        done, path = self.run_setup([str(number("options.unicode")), "1", str(number("options.no-auto")), "1 3", "s"])
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertIs(data["options"]["unicode"], True)
        self.assertEqual(len(data["options"]["no-auto"]), 2)                   # two kinds toggled on

    def test_zero_restores_the_default_and_empty_sections_go(self):
        done, path = self.run_setup([str(number("options.fallback")), "0", "s"], "options:\n  fallback: box\n")
        self.assertFalse(path.exists())                      # nothing left to keep: the file goes

    def test_quitting_saves_nothing(self):
        done, path = self.run_setup([str(number("options.fallback")), "2", "q", "y"])
        self.assertFalse(path.exists())
        self.assertIn("Nothing saved", done.stdout)

    def test_comments_are_kept_in_a_backup(self):
        done, path = self.run_setup([str(number("options.missing")), "3", "s"], "# my note\noptions:\n  fallback: box\n")
        self.assertTrue(path.with_name("config.yaml.bak").is_file())
        self.assertEqual(yaml.safe_load(path.read_text(encoding="utf-8")), {"options": {"fallback": "box", "missing": "error"}})

    def test_fancy_without_the_package_falls_back_with_a_note(self):
        if fancy.available():
            self.skipTest("prompt_toolkit is installed")
        done, path = self.run_setup(["q"], None, "fancy")
        self.assertIn("pdfmd --install tui", done.stdout)
        self.assertIn("numbered list", done.stdout)

    def test_metadata_settings_go_to_metadata_yaml_beside_the_config(self):
        author, fontsize = number("author"), number("fontsize")
        done, path = self.run_setup([str(author), "Ali P.", str(fontsize), "2", "s"])
        self.assertEqual(done.returncode, 0, done.stderr)
        data = yaml.safe_load(path.with_name("metadata.yaml").read_text(encoding="utf-8"))
        self.assertEqual(data, {"author": "Ali P.", "fontsize": "11pt"})
        self.assertFalse(path.exists())                                  # nothing in config.yaml

    def test_a_number_is_checked(self):
        done, path = self.run_setup([str(number("linestretch")), "wide", str(number("linestretch")), "1.5", "s"])
        self.assertEqual(yaml.safe_load(path.with_name("metadata.yaml").read_text(encoding="utf-8")), {"linestretch": 1.5})

    def test_the_global_metadata_reaches_a_build_below_the_documents_own(self):
        directory = tempfile.mkdtemp(prefix="pdfmd-setup-")
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        folder = Path(directory)
        (folder / "config.yaml").write_text("options: {}\n", encoding="utf-8")
        (folder / "metadata.yaml").write_text("author: Global Author\nlang: de\n", encoding="utf-8")
        (folder / "a.md").write_text("---\ntitle: T\nlang: fr\n---\n\nText.\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "a.md", "-o", "a.html", "--standalone", "--no-stamp",
                               "--no-backup"], cwd=folder, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": str(folder / "config.yaml")})
        self.assertEqual(done.returncode, 0, done.stderr)
        html = (folder / "a.html").read_text(encoding="utf-8")
        self.assertIn("Global Author", html)            # the document names no author: the global one
        self.assertIn('lang="fr"', html)                # its own language wins

    def test_the_config_can_switch_automatic_behaviour_off_for_every_document(self):
        directory = tempfile.mkdtemp(prefix="pdfmd-setup-")
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        path = Path(directory) / "config.yaml"
        path.write_text("options:\n  no-auto: [margin, monofont]\n", encoding="utf-8")
        document = Path(directory) / "d.md"
        document.write_text("Hello.\n", encoding="utf-8")
        old = os.environ.get("PDFMD_CONFIG")
        os.environ["PDFMD_CONFIG"] = str(path)
        pdfmd.load_config.cache_clear()
        try:
            self.assertEqual(pdfmd.effective_no_auto(document, ["title"]), ["margin", "monofont", "title"])
        finally:
            if old is None:
                os.environ.pop("PDFMD_CONFIG", None)
            else:
                os.environ["PDFMD_CONFIG"] = old
            pdfmd.load_config.cache_clear()


@unittest.skipUnless(yaml, "needs PyYAML")
class ConfigLayer(unittest.TestCase):
    """What `pdfmd --setup` writes under `options:` is honoured: below the document, above the built-in default."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="pdfmd-config-")
        self.addCleanup(__import__("shutil").rmtree, self.directory, True)
        self.old = os.environ.get("PDFMD_CONFIG")
        self.addCleanup(self.restore)

    def restore(self):
        if self.old is None:
            os.environ.pop("PDFMD_CONFIG", None)
        else:
            os.environ["PDFMD_CONFIG"] = self.old
        pdfmd.load_config.cache_clear()

    def use(self, text: str) -> Path:
        path = Path(self.directory) / "config.yaml"
        path.write_text(text, encoding="utf-8")
        os.environ["PDFMD_CONFIG"] = str(path)
        pdfmd.load_config.cache_clear()
        document = Path(self.directory) / "d.md"
        document.write_text("Hello.\n", encoding="utf-8")
        return document

    def test_stamp_backup_and_unicode_follow_the_config(self):
        document = self.use("options:\n  stamp: {enabled: true}\n  backup: {enabled: true}\n  unicode: true\n")
        self.assertTrue(pdfmd.resolve_stamp_options(document, [], {})["enabled"])
        self.assertTrue(pdfmd.resolve_backup_options(document, [], None)["enabled"])
        self.assertTrue(pdfmd.unicode_forced(document))

    def test_the_documents_own_setting_wins(self):
        document = self.use("options:\n  stamp: {enabled: true}\n  unicode: true\n")
        document.write_text("---\npdfmd-options:\n  stamp: false\n  unicode: false\n---\n\nHello.\n", encoding="utf-8")
        self.assertFalse(pdfmd.resolve_stamp_options(document, [], {})["enabled"])
        self.assertFalse(pdfmd.unicode_forced(document))

    def test_without_the_config_nothing_is_on(self):
        document = self.use("options: {}\n")
        self.assertFalse(pdfmd.resolve_stamp_options(document, [], {})["enabled"])
        self.assertFalse(pdfmd.resolve_backup_options(document, [], None)["enabled"])
        self.assertFalse(pdfmd.unicode_forced(document))


class Registry(unittest.TestCase):
    def test_put_and_get_nest_and_prune(self):
        config: dict = {}
        registry.put(config, "options.office.latex", "off")
        registry.put(config, "options.cache.aux", True)
        self.assertEqual(registry.get(config, "options.office.latex"), "off")
        registry.put(config, "options.office.latex", None)
        self.assertEqual(config, {"options": {"cache": {"aux": True}}})
        registry.put(config, "options.cache.aux", None)
        self.assertEqual(config, {})

    def test_every_setting_has_a_key_a_kind_and_choices(self):
        for setting in SETTINGS:
            self.assertIn(setting.kind, ("choice", "multi", "text"))
            self.assertIn(setting.store, ("config", "metadata"))
            self.assertEqual(bool(setting.choices), setting.kind != "text", setting.key)


@unittest.skipUnless(fancy.available() and yaml, "needs prompt_toolkit")
class Fancy(unittest.TestCase):
    def drive(self, keys: str, stores: dict, ask=None):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        with create_pipe_input() as pipe:
            pipe.send_text(keys)
            return fancy.run(stores, SETTINGS, "config.yaml", input=pipe, output=DummyOutput(), ask=ask)

    def test_space_cycles_a_choice_and_s_saves(self):
        stores: dict = {}
        down = "j" * [s.key for s in SETTINGS].index("options.fallback")
        self.assertTrue(self.drive(down + " s", stores))          # unset -> first choice
        self.assertEqual(stores["config"], {"options": {"fallback": "word"}})

    def test_a_text_setting_is_asked_for_and_stored_in_its_file(self):
        stores: dict = {}
        self.assertTrue(self.drive("\rs", stores, ask=lambda setting, now: "Ali P."))   # the first row is the author
        self.assertEqual(stores["metadata"], {"author": "Ali P."})

    def test_q_quits_without_saving(self):
        stores: dict = {}
        self.assertFalse(self.drive("q", stores))
        self.assertEqual(stores.get("config", {}), {})


if __name__ == "__main__":
    unittest.main()
