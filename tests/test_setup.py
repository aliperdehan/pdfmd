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
    return [setting.key for setting in SETTINGS].index(key) + 1


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
        self.assertEqual(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, {})

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
            self.assertIn(setting.kind, ("choice", "multi"))
            self.assertTrue(setting.choices, setting.key)


@unittest.skipUnless(fancy.available() and yaml, "needs prompt_toolkit")
class Fancy(unittest.TestCase):
    def drive(self, keys: str, config: dict):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        with create_pipe_input() as pipe:
            pipe.send_text(keys)
            return fancy.run(config, SETTINGS, "config.yaml", input=pipe, output=DummyOutput())

    def test_space_cycles_a_choice_and_s_saves(self):
        config: dict = {}
        self.assertTrue(self.drive(" s", config))                 # first setting: unset -> first choice
        self.assertEqual(config, {"options": {"fallback": "word"}})

    def test_q_quits_without_saving(self):
        config: dict = {}
        self.assertFalse(self.drive("q", config))
        self.assertEqual(config, {})


if __name__ == "__main__":
    unittest.main()
