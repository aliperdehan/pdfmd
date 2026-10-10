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
from pdfmd_setup import fancy, inventory, registry, settings_for  # noqa: E402

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

    def test_o_lists_what_is_not_settable_and_why(self):
        done, path = self.run_setup(["o", "q"])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Not settable here, on purpose", done.stdout)
        self.assertIn("--history-restore", done.stdout)                       # a command, written as people type it
        self.assertIn("--no-embed-metadata", done.stdout)                     # a dest spelled from the parser
        self.assertIn("office.title-page", done.stdout)                       # a pdfmd-options key
        self.assertIn(inventory.REASONS["trust"], done.stdout)

    def test_a_list_setting_is_stored_as_a_list(self):
        done, path = self.run_setup([str(number("options.check-ignore")), "heading-skip, link-anchor", "s"])
        self.assertEqual(yaml.safe_load(path.read_text(encoding="utf-8")),
                         {"options": {"check-ignore": ["heading-skip", "link-anchor"]}})

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

    @unittest.skipUnless(__import__("shutil").which("pandoc"), "needs Pandoc")
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


@unittest.skipUnless(yaml, "needs PyYAML")
class NewRows(unittest.TestCase):
    """The rows added in 3.27.0 reach a build: each value as `--setup` stores it, read by the function pdfmd uses."""

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

    def use(self, values: dict) -> Path:
        config: dict = {}
        by_key = {setting.key: setting for setting in SETTINGS}
        for key, value in values.items():
            registry.write({"config": config}, by_key[key], value)
        path = Path(self.directory) / "config.yaml"
        path.write_text(yaml.safe_dump(config), encoding="utf-8")
        os.environ["PDFMD_CONFIG"] = str(path)
        pdfmd.load_config.cache_clear()
        document = Path(self.directory) / "d.md"
        document.write_text("Hello.\n", encoding="utf-8")
        return document

    def test_checks_and_limits(self):
        document = self.use({"options.strict": True, "options.max-asset-mb": 5, "options.max-output-mb": 20,
                             "options.check-ignore": ["heading-skip"]})
        self.assertIs(pdfmd.first_pdfmd_option(document, [], "strict"), True)
        self.assertEqual(pdfmd.resolve_budget(document, []), (5, 20))
        self.assertEqual(pdfmd.first_pdfmd_option(document, [], "check-ignore"), ["heading-skip"])

    def test_the_reader(self):
        document = self.use({"options.reader": "commonmark_x"})
        self.assertEqual(pdfmd.resolve_from_format(document, None, [])[0], "commonmark_x")

    def test_stamp_and_backup_details(self):
        document = self.use({"options.stamp.mode": "history", "options.stamp.scope": "report",
                             "options.stamp.packages": ["nulabreport"], "options.stamp.include-output": True,
                             "options.stamp.pdf-metadata": False, "options.backup.format": "dashed",
                             "options.backup.keep": 3})
        stamp = pdfmd.resolve_stamp_options(document, [], {})
        self.assertEqual((stamp["mode"], stamp["scope"], stamp["packages"], stamp["include_output"], stamp["pdf_metadata"]),
                         ("history", "report", ["nulabreport"], True, False))
        backup = pdfmd.resolve_backup_options(document, [], None)
        self.assertEqual((backup["format"], backup["keep"]), ("dashed", 3))

    def test_plain_markdown_and_text(self):
        import pdfmd_flat
        document = self.use({"options.gfm.scripts": "ascii", "options.gfm.math": "fenced", "options.gfm.title": False,
                             "options.txt.scripts": "drop", "options.txt.title": False, "options.ascii.missing": "escape",
                             "options.keep-source": "readable"})
        gfm = pdfmd_flat.settings(pdfmd.cascaded_option(document, [], "gfm"))
        self.assertEqual(gfm, {"scripts": "ascii", "math": "fenced", "title": False})
        txt = pdfmd_flat.settings(pdfmd.cascaded_option(document, [], "txt"), target="txt")
        self.assertEqual((txt["scripts"], txt["title"]), ("drop", False))
        self.assertEqual(pdfmd.cascaded_option(document, [], "ascii"), {"missing": "escape"})
        self.assertEqual(pdfmd.resolve_keep_source(document, []), "readable")

    def test_html_word_cache_and_bundle(self):
        document = self.use({"options.html.standalone": True, "options.html.css": "/styles/a.css",
                             "options.office.reference-doc": "/templates/house.dotx", "options.cache.plots": True,
                             "options.seed-labels": "scan", "options.bundle-packages": True})
        html = pdfmd.html_settings(document, [])
        self.assertEqual((html["standalone"], html["css"]), (True, "/styles/a.css"))
        self.assertEqual(pdfmd.office_options(document, [])["reference-doc"], "/templates/house.dotx")
        self.assertTrue(pdfmd.cache_settings(document, [], None)["plots"])
        self.assertEqual(pdfmd.seed_labels_mode(document, []), "scan")
        self.assertIs(pdfmd.first_pdfmd_option(document, [], "bundle-packages"), True)


@unittest.skipUnless(yaml, "needs PyYAML")
class FieldByField(unittest.TestCase):
    """v3.27.1: a mapping-valued option is merged field by field down document > metadata files > config, and a
    config mapping says only what it says (a detail row does not switch stamping or backups on)."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-layers-"))
        self.addCleanup(__import__("shutil").rmtree, self.directory, True)
        self.old = os.environ.get("PDFMD_CONFIG")
        self.addCleanup(self.restore)

    def restore(self):
        if self.old is None:
            os.environ.pop("PDFMD_CONFIG", None)
        else:
            os.environ["PDFMD_CONFIG"] = self.old
        pdfmd.load_config.cache_clear()

    def layers(self, config: str, document: str = "", metadata: str = ""):
        (self.directory / "config.yaml").write_text(config, encoding="utf-8")
        os.environ["PDFMD_CONFIG"] = str(self.directory / "config.yaml")
        pdfmd.load_config.cache_clear()
        path = self.directory / "d.md"
        path.write_text((f"---\n{document}---\n\n" if document else "") + "Text.\n", encoding="utf-8")
        files = []
        if metadata:
            (self.directory / "metadata.yaml").write_text(metadata, encoding="utf-8")
            files.append(self.directory / "metadata.yaml")
        return path, files

    def test_a_detail_in_the_config_does_not_switch_stamping_or_backups_on(self):
        path, files = self.layers("options:\n  stamp: {store: file, mode: history}\n  backup: {dir: old, keep: 2}\n")
        stamp = pdfmd.resolve_stamp_options(path, files, {})
        backup = pdfmd.resolve_backup_options(path, files, None)
        self.assertFalse(stamp["enabled"])
        self.assertFalse(backup["enabled"])
        self.assertEqual((stamp["store"], stamp["mode"], backup["dir"], backup["keep"]), ("file", "history", "old", 2))

    def test_a_document_switches_it_on_and_keeps_the_details_below(self):
        path, files = self.layers("options:\n  stamp: {store: file}\n  backup: {dir: old}\n",
                                  "pdfmd-options:\n  stamp: true\n  backup: true\n")
        stamp = pdfmd.resolve_stamp_options(path, files, {})
        self.assertEqual((stamp["enabled"], stamp["store"]), (True, "file"))
        backup = pdfmd.resolve_backup_options(path, files, None)
        self.assertEqual((backup["enabled"], backup["dir"]), (True, "old"))

    def test_a_shared_metadata_file_still_switches_on_by_naming_details(self):
        path, files = self.layers("options: {}\n", "pdfmd-options:\n  stamp: {mode: replace}\n",
                                  "pdfmd-options:\n  stamp: {packages: [nulabreport], mode: history, store: file}\n")
        stamp = pdfmd.resolve_stamp_options(path, files, {})
        self.assertEqual((stamp["enabled"], stamp["mode"], stamp["store"], stamp["packages"]),
                         (True, "replace", "file", ["nulabreport"]))

    def test_the_documents_explicit_off_wins(self):
        path, files = self.layers("options: {}\n", "pdfmd-options:\n  stamp: false\n",
                                  "pdfmd-options:\n  stamp: {store: file}\n")
        self.assertFalse(pdfmd.resolve_stamp_options(path, files, {})["enabled"])

    def test_a_list_shorthand_in_the_config_still_means_on(self):
        path, files = self.layers("options:\n  stamp: [nulabreport]\n")
        self.assertTrue(pdfmd.resolve_stamp_options(path, files, {})["enabled"])

    def test_other_mappings_merge_and_a_plain_value_ends_the_merge(self):
        path, files = self.layers("options:\n  html: {css: a.css}\n  cache: {aux: true}\n  raw: {html: [tex]}\n",
                                  "pdfmd-options:\n  html: {math: katex}\n  cache: {plots: true}\n  raw: true\n")
        self.assertEqual(pdfmd.html_settings(path, files), {"math": "katex", "css": "a.css"})
        self.assertEqual(pdfmd.cache_settings(path, files, None), {"aux": True, "plots": True})
        self.assertIs(pdfmd.first_pdfmd_option(path, files, "raw"), True)

    def test_the_first_place_to_set_a_field_wins(self):
        path, files = self.layers("options:\n  html: {math: mathml, css: c.css}\n", "pdfmd-options:\n  html: {math: katex}\n",
                                  "pdfmd-options:\n  html: {math: webtex, css: m.css}\n")
        self.assertEqual(pdfmd.html_settings(path, files), {"math": "katex", "css": "m.css"})


class Completeness(unittest.TestCase):
    """Every flag and every pdfmd-options key is a --setup row or left out on purpose (pdfmd_setup/inventory.py)."""

    @classmethod
    def setUpClass(cls):
        cls.keys = {setting.key for setting in SETTINGS}
        cls.dests = {action.dest for action in pdfmd.build_parser()._actions}

    def test_every_flag_is_accounted_for(self):
        missing = sorted(self.dests - set(inventory.FLAGS))
        self.assertEqual(missing, [], "flags in neither --setup nor pdfmd_setup.inventory.FLAGS (add them there)")
        stale = sorted(set(inventory.FLAGS) - self.dests)
        self.assertEqual(stale, [], "inventory.FLAGS names flags the parser no longer has")

    def test_every_row_named_exists_and_every_reason_is_known(self):
        for table in (inventory.FLAGS, inventory.OPTIONS):
            for name, where in table.items():
                if isinstance(where, inventory.Omitted):
                    self.assertIn(where.reason, inventory.REASONS, name)
                else:
                    self.assertIn(where, self.keys, f"{name} points at {where!r}, which is no --setup row")

    def test_every_options_row_is_a_key_people_can_write(self):
        written = {where for where in inventory.OPTIONS.values() if isinstance(where, str)}
        for key in self.keys:
            if key.startswith("options."):
                self.assertIn(key, written, f"the row {key} has no pdfmd-options key in inventory.OPTIONS")
                self.assertIn(key[len("options."):], inventory.OPTIONS, key)

    def test_the_keys_pdfmd_reads_are_accounted_for(self):
        import re
        source = (ROOT / "pdfmd.py").read_text(encoding="utf-8")
        found: set[str] = set()
        for call in re.findall(r"(?:first_pdfmd_option|cascaded_option)\(([^()]*)\)", source):
            found.update(re.findall(r'"([a-z][a-z0-9-]*)"', call))
        found.update(re.findall(r'config_options\(\)(?:\.get\(|\[)"([a-z][a-z0-9-]*)"', source))
        found.update(re.findall(r'"([a-z][a-z0-9-]*)" in config_options\(\)', source))
        found.update(re.findall(r'frontmatter_pdfmd_options\([^()]*\)\.get\("([a-z][a-z0-9-]*)"', source))
        found.update(re.findall(r'"([a-z][a-z0-9-]*)" in (?:options|own|nested)\b', source))
        found.update(re.findall(r'\b(?:options|own|nested)\["([a-z][a-z0-9-]*)"\]', source))
        found -= {"info"}                              # the PDF Info record pdfmd builds for itself
        self.assertGreater(len(found), 25)             # the scan itself still works
        # a mapping's field read inside its normaliser (`options["mode"]` of stamp) counts as its dotted key
        listed = {part for key in inventory.OPTIONS for part in (key, key.split(".")[0], key.split(".")[-1])}
        self.assertEqual(sorted(found - listed), [], "pdfmd reads pdfmd-options keys inventory.OPTIONS does not list")

    def test_the_fields_of_mappings_are_accounted_for(self):
        import pdfmd_flat
        fields = {f"stamp.{key.replace('_', '-')}" for key in pdfmd.DEFAULT_STAMP_OPTIONS}
        fields |= {f"backup.{key}" for key in pdfmd.DEFAULT_BACKUP_OPTIONS}
        fields |= {f"cache.{key}" for key in pdfmd.CACHE_DEFAULTS} | {"cache.location"}
        fields |= {f"{target}.{key}" for target in pdfmd_flat.TARGETS for key in pdfmd_flat.DEFAULTS}
        fields |= {f"office.{key}" for key in pdfmd.OFFICE_OPTION_KEYS}
        self.assertEqual(sorted(fields - set(inventory.OPTIONS)), [])

    def test_every_setting_has_a_scope(self):
        for setting in SETTINGS:
            self.assertIn(setting.scope, ("any", "machine"), setting.key)
        self.assertEqual({s.key for s in SETTINGS if s.scope == "machine"}, set(registry.MACHINE))

    def test_the_list_of_what_is_left_out_names_every_one(self):
        text = "\n".join(inventory.omitted_lines(pdfmd.flag_names(), width=10000))
        for dest, where in inventory.FLAGS.items():
            if isinstance(where, inventory.Omitted):
                self.assertIn(pdfmd.flag_names()[dest], text, dest)


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

    def test_an_unset_setting_says_what_pdfmd_does_instead(self):
        for setting in SETTINGS:
            self.assertTrue(setting.unset or setting.default, f"{setting.key}: nothing says what the default is")
            self.assertNotIn("not set", registry.shown(setting, None), setting.key)
        for key in registry.UNSET:
            self.assertIn(key, [setting.key for setting in SETTINGS], f"UNSET names {key}, which is no setting")

    def test_the_screen_shows_the_fonts_pdfmd_picks(self):
        by_key = {setting.key: setting for setting in SETTINGS}
        self.assertIn("STIX Two Text", registry.shown(by_key["mainfont"], None))
        self.assertIn("JetBrains Mono", registry.shown(by_key["monofont"], None))
        self.assertEqual(registry.shown(by_key["mainfont"], "Georgia"), "Georgia")


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

    def test_o_shows_what_is_left_out_and_a_key_goes_back(self):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        stores: dict = {}
        with create_pipe_input() as pipe:
            pipe.send_text("oqq")                     # o shows the list, q goes back, q quits
            saved = fancy.run(stores, SETTINGS, "config.yaml", input=pipe, output=DummyOutput(),
                              left_out=inventory.omitted_lines())
        self.assertFalse(saved)


if __name__ == "__main__":
    unittest.main()
