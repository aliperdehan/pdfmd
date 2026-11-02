"""v3.31.30: kits, C1 (entry 3du): the `.kit` format, finding a kit by name, the cached location, `kits:` in the config,
`pdfmd --kits`. Every kit here is a fixture built in a temporary folder; the real nulabreport is never read."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pdfmd  # noqa: E402
from env_support import can_symlink  # noqa: E402
from pdfmd_kits import Cache, KitError, Location, find, list_kits, load_kit, normalise, resolve_mode  # noqa: E402

FULL = """\
kit-format: 1
name: nulabreport
version: 1.30.0
description: House style
package: nulabreport
default-mode: genchem
modes:
  qca: {aliases: [220, "chem 220"], options: [qca], defaults: qca.yaml, metadata: {course: "CHEM 220L"}, latex: ['\\LabScheme{word}']}
  orgchem: {aliases: [211, 212], options: orgchem}
  genchem: {aliases: [101]}
latex: ['\\input{chemicals}']
lua: [nulabreport.lua]
defaults: metadata.yaml
metadata: {lang: en-GB}
latex-keys: {experiment: LabExperiment}
carry: [nulabreport.sty, assets/]
settings: {scheme: word}
requires: {fonts: [STIX Two Text]}
"""


def write(path: Path, text: str = "x\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_kit(folder: Path, text: str = FULL, files=("qca.yaml", "metadata.yaml", "nulabreport.lua")) -> Path:
    for name in files:
        write(folder / name)
    return write(folder / ".kit", text)


class Scratch(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()


class Normalise(unittest.TestCase):
    def test_case_and_separators_do_not_count(self):
        for spelling in ("Nu-Lab-Report", "nulab_report", "nulabreport", "NULAB REPORT", "nu.lab.report"):
            self.assertEqual(normalise(spelling), "nulabreport")
        self.assertEqual(normalise("chem 220"), normalise("Chem-220"))
        self.assertEqual(normalise(220), "220")


class Format(Scratch):
    def test_a_full_kit_is_read(self):
        kit = load_kit(make_kit(self.root / "nulabreport"))
        self.assertEqual((kit.name, kit.version, kit.package, kit.default_mode), ("nulabreport", "1.30.0", "nulabreport", "genchem"))
        self.assertEqual(list(kit.modes), ["qca", "orgchem", "genchem"])
        qca = kit.modes["qca"]
        self.assertEqual((qca.aliases, qca.options, qca.metadata, qca.latex), (("220", "chem 220"), ("qca",), {"course": "CHEM 220L"}, ("\\LabScheme{word}",)))
        self.assertEqual(qca.defaults, (self.root / "nulabreport" / "qca.yaml",))
        self.assertEqual(kit.modes["orgchem"].options, ("orgchem",))               # one word is a list of one
        self.assertEqual(kit.latex, ("\\input{chemicals}",))
        self.assertEqual(kit.lua, (self.root / "nulabreport" / "nulabreport.lua",))
        self.assertEqual(kit.defaults, (self.root / "nulabreport" / "metadata.yaml",))
        self.assertEqual(kit.metadata, {"lang": "en-GB"})
        self.assertEqual(kit.helper, {"latex-keys": {"experiment": "LabExperiment"}})
        self.assertEqual(kit.carry, ("nulabreport.sty", "assets/"))
        self.assertEqual(kit.warnings, ())                                           # settings, requires: reserved, silent

    def test_the_name_defaults_to_the_folder_and_a_number_version_is_text(self):
        kit = load_kit(write(self.root / "thing" / ".kit", "kit-format: 1\nversion: 2\n"))
        self.assertEqual((kit.name, kit.version, kit.modes, kit.package), ("thing", "2", {}, ""))

    def test_a_missing_version_is_the_one_the_package_announces(self):
        folder = self.root / "thing"
        write(folder / "thing.sty", "\\NeedsTeXFormat{LaTeX2e}\n\\ProvidesPackage{thing}[2026/10/31 v1.28.30 A style]\n")
        kit = load_kit(write(folder / ".kit", "kit-format: 1\npackage: thing\n"))
        self.assertEqual(kit.version, "1.28.30")
        self.assertEqual(load_kit(write(folder / ".kit", "kit-format: 1\npackage: thing\nversion: 7\n")).version, "7")   # a written one wins

    def test_no_package_file_or_no_version_in_it_is_no_version(self):
        folder = self.root / "thing"
        self.assertEqual(load_kit(write(folder / ".kit", "kit-format: 1\npackage: thing\n")).version, "")
        write(folder / "thing.sty", "\\ProvidesPackage{thing}[2026/10/31 a style with no number]\n")
        self.assertEqual(load_kit(folder / ".kit").version, "")

    def test_a_missing_or_newer_format_stops(self):
        with self.assertRaises(KitError) as caught:
            load_kit(write(self.root / "a" / ".kit", "name: a\n"))
        self.assertIn("kit-format", str(caught.exception))
        with self.assertRaises(KitError) as caught:
            load_kit(write(self.root / "b" / ".kit", "kit-format: 2\n"))
        self.assertIn("needs a newer pdfmd", str(caught.exception))
        for bad in ("kit-format: one\n", "kit-format: 0\n", "kit-format: true\n"):
            with self.assertRaises(KitError):
                load_kit(write(self.root / "c" / ".kit", bad))

    def test_a_file_that_is_not_a_mapping_or_not_yaml_stops(self):
        with self.assertRaises(KitError):
            load_kit(write(self.root / "a" / ".kit", "- one\n- two\n"))
        with self.assertRaises(KitError) as caught:
            load_kit(write(self.root / "b" / ".kit", "kit-format: 1\nname: [unclosed\n"))
        self.assertIn("not valid YAML", str(caught.exception))

    def test_an_unknown_key_is_a_warning_not_a_stop(self):
        kit = load_kit(write(self.root / "a" / ".kit", "kit-format: 1\nbogus: 1\nmodes:\n  m: {color: red}\n"))
        self.assertEqual(len(kit.warnings), 2)
        self.assertIn("`bogus`", kit.warnings[0])
        self.assertIn("`color` in mode `m`", kit.warnings[1])

    def test_every_fault_is_listed_at_once(self):
        text = ("kit-format: 1\npackage: 'a b'\nlua: [missing.lua]\ndefaults: ../outside.yaml\ncarry: [/etc/passwd]\n"
                "modes:\n  one: {aliases: [x]}\n  two: {aliases: [X]}\ndefault-mode: nine\n")
        with self.assertRaises(KitError) as caught:
            load_kit(write(self.root / "k" / ".kit", text))
        text = str(caught.exception)
        for part in ("`package:`", "missing.lua", "leaves the kit's folder", "not relative", "also a name of mode `one`", "default-mode: nine"):
            self.assertIn(part, text)

    def test_paths_stay_inside_the_folder(self):
        for bad in ("../x.yaml", "/abs/x.yaml", "C:\\x.yaml", "~/x.yaml", "a/../../x.yaml"):
            with self.assertRaises(KitError, msg=bad):
                load_kit(write(self.root / "k" / ".kit", f"kit-format: 1\ndefaults: {json.dumps(bad)}\n"))

    def test_a_mode_with_nothing_in_it_is_fine(self):
        kit = load_kit(write(self.root / "k" / ".kit", "kit-format: 1\nmodes:\n  plain:\n  220: {}\n"))
        self.assertEqual(list(kit.modes), ["plain", "220"])

    def test_the_config_adds_mode_names_without_editing_the_kit(self):
        kit = load_kit(make_kit(self.root / "n"), {"QCA": ["analytical"], "orgchem": "organic"})
        self.assertEqual(resolve_mode(kit, "Analytical").name, "qca")
        self.assertEqual(resolve_mode(kit, "organic").name, "orgchem")
        with self.assertRaises(KitError):
            load_kit(make_kit(self.root / "n2"), {"qca": ["211"]})                    # 211 is orgchem's already


class Modes(Scratch):
    def setUp(self):
        super().setUp()
        self.kit = load_kit(make_kit(self.root / "n"))

    def test_a_mode_is_found_by_name_or_alias_with_the_same_normalising(self):
        for text, name in (("qca", "qca"), ("QCA", "qca"), ("220", "qca"), ("Chem-220", "qca"), (212, "orgchem"), ("101", "genchem")):
            self.assertEqual(resolve_mode(self.kit, text).name, name, text)

    def test_no_mode_asked_gives_the_default_or_none(self):
        self.assertEqual(resolve_mode(self.kit, None).name, "genchem")
        self.assertEqual(resolve_mode(self.kit, "  ").name, "genchem")
        bare = load_kit(write(self.root / "b" / ".kit", "kit-format: 1\nmodes: {a: {}}\n"))
        self.assertIsNone(resolve_mode(bare, None))

    def test_an_unknown_mode_stops_and_lists_the_modes(self):
        with self.assertRaises(KitError) as caught:
            resolve_mode(self.kit, "physics")
        self.assertIn("`physics`", str(caught.exception))
        self.assertIn("qca (220, chem 220)", str(caught.exception))
        none = load_kit(write(self.root / "b" / ".kit", "kit-format: 1\n"))
        with self.assertRaises(KitError) as caught:
            resolve_mode(none, "x")
        self.assertIn("no modes", str(caught.exception))


class Discovery(Scratch):
    def kit(self, where: str, name: str, body: str = "") -> Path:
        return write(self.root / where / ".kit", f"kit-format: 1\nname: {name}\n{body}")

    def test_found_by_the_folder_the_file_name_or_the_declared_name(self):
        self.kit("a/Nu-Lab-Report", "whatever")
        write(self.root / "a" / "named" / "other.kit", "kit-format: 1\nname: zzz\n")
        self.kit("a/folder", "Declared Name")
        place = [Location("here", self.root / "a")]
        self.assertEqual(find("nulabreport", place).path, self.root / "a" / "Nu-Lab-Report" / ".kit")
        self.assertEqual(find("OTHER", place).path, self.root / "a" / "named" / "other.kit")
        self.assertEqual(find("declared_name", place).path, self.root / "a" / "folder" / ".kit")
        self.assertIsNone(find("missing", place))
        self.assertEqual(find("nulabreport", place).source, "here")

    def test_a_location_may_be_the_kit_itself(self):
        self.kit("thing", "thing")
        self.assertEqual(find("thing", [Location("registered", self.root / "thing")]).source, "registered")

    def test_dot_kit_comes_before_a_named_file(self):
        folder = self.root / "a" / "thing"
        self.kit("a/thing", "thing")
        write(folder / "thing.kit", "kit-format: 1\nname: thing\n")
        self.assertEqual(find("thing", [Location("x", self.root / "a")]).path.name, ".kit")

    def test_two_kits_of_one_name_in_one_place_stop_and_name_both(self):
        self.kit("a/one", "same")
        self.kit("a/two", "SAME")
        with self.assertRaises(KitError) as caught:
            find("same", [Location("the project", self.root / "a")])
        self.assertIn("one", str(caught.exception))
        self.assertIn("two", str(caught.exception))
        self.assertIn("will not choose", str(caught.exception))

    def test_across_places_the_order_decides(self):
        self.kit("near/thing", "thing")
        self.kit("far/thing", "thing")
        places = [Location("near", self.root / "near"), Location("far", self.root / "far")]
        self.assertEqual(find("thing", places).source, "near")

    @unittest.skipUnless(can_symlink(), "needs symbolic links")
    def test_one_kit_reached_twice_is_not_a_collision(self):
        self.kit("a/thing", "thing")
        os.symlink(self.root / "a" / "thing", self.root / "a" / "link")
        self.assertEqual(find("thing", [Location("x", self.root / "a")]).source, "x")

    def test_the_lookup_runs_only_after_the_places_and_the_cache_have_nothing(self):
        self.kit("tex/thing", "thing")
        calls = []

        def lookup(name):
            calls.append(name)
            return self.root / "tex" / "thing"
        self.kit("a/thing", "thing")
        self.assertEqual(find("thing", [Location("a", self.root / "a")], lookup).source, "a")
        self.assertEqual(calls, [])
        cache = Cache(self.root / "cache" / "kits.json")
        found = find("thing", [], lookup, cache)
        self.assertEqual((found.source, found.cached, calls), ("the TeX tree", False, ["thing"]))
        again = find("thing", [], lookup, cache)
        self.assertEqual((again.cached, again.path, calls), (True, found.path, ["thing"]))     # no second lookup

    def test_a_lookup_that_finds_a_folder_without_a_kit_is_a_miss_and_nothing_is_cached(self):
        cache = Cache(self.root / "cache" / "kits.json")
        write(self.root / "tex" / "thing" / "thing.sty")
        self.assertIsNone(find("thing", [], lambda name: self.root / "tex" / "thing", cache))
        self.assertIsNone(find("thing", [], lambda name: None, cache))
        self.assertFalse((self.root / "cache").exists())

    def test_the_lookup_is_asked_for_the_name_as_typed_and_normalised(self):
        asked = []
        find("Nu-Lab", [], lambda name: asked.append(name))
        self.assertEqual(asked, ["Nu-Lab", "nulab"])


class CacheFile(Scratch):
    def setUp(self):
        super().setUp()
        self.kit = write(self.root / "k" / ".kit", "kit-format: 1\n")
        self.file = self.root / "cache" / "kits.json"

    def test_a_hit_needs_the_same_size_and_time(self):
        cache = Cache(self.file)
        cache.put("k", self.kit)
        self.assertEqual(Cache(self.file).get("k"), self.kit)
        self.kit.write_text("kit-format: 1\nname: longer now\n", encoding="utf-8")
        self.assertIsNone(Cache(self.file).get("k"))
        self.kit.unlink()
        self.assertIsNone(Cache(self.file).get("k"))

    def test_a_corrupt_or_foreign_cache_is_a_miss_and_is_replaced_by_the_next_write(self):
        for text in ("{not json", "[]", json.dumps({"format": 99, "kits": {}}), json.dumps({"format": 1, "kits": []})):
            write(self.file, text)
            self.assertIsNone(Cache(self.file).get("k"), text)
        write(self.file, "{not json")
        Cache(self.file).put("k", self.kit)
        self.assertEqual(Cache(self.file).get("k"), self.kit)

    def test_entries_accumulate_and_no_file_is_left_half_written(self):
        other = write(self.root / "o" / ".kit", "kit-format: 1\n")
        cache = Cache(self.file)
        cache.put("k", self.kit)
        cache.put("o", other)
        again = Cache(self.file)
        self.assertEqual((again.get("k"), again.get("o")), (self.kit, other))
        self.assertEqual([item.name for item in self.file.parent.iterdir()], ["kits.json"])

    def test_no_path_means_no_cache_and_an_unwritable_one_costs_nothing(self):
        Cache(None).put("k", self.kit)
        self.assertIsNone(Cache(None).get("k"))
        blocked = write(self.root / "blocked")                  # a file where the cache folder should be
        Cache(blocked / "kits.json").put("k", self.kit)


class Listing(Scratch):
    def test_every_kit_of_the_places_then_the_cached_ones_each_once(self):
        write(self.root / "a" / "one" / ".kit", "kit-format: 1\n")
        write(self.root / "a" / "two" / "two.kit", "kit-format: 1\n")
        cached = write(self.root / "tex" / "three" / ".kit", "kit-format: 1\n")
        cache = Cache(self.root / "c.json")
        cache.put("three", cached)
        rows = list_kits([Location("a", self.root / "a"), Location("again", self.root / "a")], cache)
        self.assertEqual([(row.path.parent.name, row.source, row.cached) for row in rows],
                         [("one", "a", False), ("two", "a", False), ("three", "the TeX tree", True)])


class Wiring(Scratch):
    """pdfmd.py: the config's `kits:`, the places, find_kit, `pdfmd --kits`."""

    def setUp(self):
        super().setUp()
        self.config = self.root / "cfg" / "config.yaml"
        patcher = mock.patch.dict(os.environ, {"PDFMD_CONFIG": str(self.config), "XDG_CACHE_HOME": str(self.root / "cache"),
                                                  "LOCALAPPDATA": str(self.root / "cache")})      # Windows keeps the cache there
        patcher.start()
        self.addCleanup(patcher.stop)
        pdfmd.load_config.cache_clear()
        self.addCleanup(pdfmd.load_config.cache_clear)

    def set_config(self, text: str) -> None:
        write(self.config, text)
        pdfmd.load_config.cache_clear()

    def test_kits_in_the_config_are_a_path_or_a_mapping_and_a_relative_one_is_read_from_the_config_folder(self):
        self.set_config("kits:\n  - ~/somewhere\n  - {path: rel/kit, aliases: {qca: [analytical]}}\n  - 5\n")
        with mock.patch("sys.stderr"):
            found = pdfmd.configured_kits()
        self.assertEqual(found, [(Path("~/somewhere").expanduser(), {}), (self.config.parent / "rel" / "kit", {"qca": ["analytical"]})])

    def test_one_string_is_one_entry_and_no_kits_is_none(self):
        place = (self.root / "one" / "place").as_posix()                 # absolute on every system (`/one/place` has no drive on Windows)
        self.set_config(f"kits: {place}\n")
        self.assertEqual(pdfmd.configured_kits(), [(Path(place), {})])
        self.set_config("options: {}\n")
        self.assertEqual(pdfmd.configured_kits(), [])

    def test_the_known_keys_of_the_config_include_kits(self):
        self.set_config("kits: [/x]\n")
        with mock.patch("sys.stderr") as err:
            pdfmd.load_config()
        self.assertFalse(err.write.called)

    def test_the_places_in_order_and_what_no_auto_kit_takes_away(self):
        project = self.root / "p" / "doc"
        project.mkdir(parents=True)
        (self.root / "p" / "kits").mkdir()
        (self.root / "reg").mkdir()
        (self.config.parent / "kits").mkdir(parents=True)
        self.set_config(f"kits: [{self.root / 'reg'}]\n")
        places = pdfmd.kit_locations(project)
        self.assertEqual([place.source for place in places],
                         ["a kits/ folder above the document", "kits: in the config", "the kits/ folder beside the config file"])
        self.assertEqual([place.source for place in pdfmd.kit_locations(project, ["kit"])], ["kits: in the config"])
        self.assertEqual(pdfmd.kit_locations(project, []) , places[1:2])

    def test_find_kit_by_name_by_path_and_the_miss_says_where_it_looked(self):
        make_kit(self.root / "p" / "kits" / "nulabreport")
        project = self.root / "p" / "doc"
        project.mkdir(parents=True)
        with mock.patch.object(pdfmd, "installed_package_folder", return_value=None):
            found = pdfmd.find_kit("Nulab-Report", project)
            self.assertEqual((found.path, found.source), (self.root / "p" / "kits" / "nulabreport" / ".kit", "a kits/ folder above the document"))
            self.assertEqual(pdfmd.find_kit("../kits/nulabreport", project).source, "a path")
            self.assertEqual(pdfmd.find_kit(str(self.root / "p" / "kits" / "nulabreport" / ".kit"), project).source, "a path")
            with self.assertRaises(KitError) as caught:
                pdfmd.find_kit("nulabreprot", project)
            self.assertIn("did you mean nulabreport", str(caught.exception))
            self.assertIn("the TeX tree", str(caught.exception))
            with self.assertRaises(KitError) as caught:
                pdfmd.find_kit("./nothing", project)
            self.assertIn("no kit at", str(caught.exception))

    def test_no_auto_kit_stops_the_search_but_not_a_registered_folder_or_a_path(self):
        make_kit(self.root / "p" / "kits" / "nulabreport")
        make_kit(self.root / "reg" / "other", FULL.replace("name: nulabreport", "name: other"))
        self.set_config(f"kits: [{self.root / 'reg'}]\n")
        project = self.root / "p" / "doc"
        project.mkdir(parents=True)
        asked = []
        with mock.patch.object(pdfmd, "installed_package_folder", side_effect=lambda name: asked.append(name)):
            with self.assertRaises(KitError):
                pdfmd.find_kit("nulabreport", project, ["kit"])
            self.assertEqual(pdfmd.find_kit("other", project, ["kit"]).source, "kits: in the config")
            self.assertEqual(pdfmd.find_kit("p/kits/nulabreport", self.root, ["kit"]).source, "a path")
            self.assertEqual(asked, [])                                              # the TeX tree was never asked
            with self.assertRaises(KitError):
                pdfmd.find_kit("nothing", project, ["kpsewhich"])
            self.assertEqual(asked, [])

    def test_the_tex_tree_answer_is_cached_for_the_next_run(self):
        make_kit(self.root / "tex" / "nulabreport")
        project = self.root / "doc"
        project.mkdir()
        with mock.patch.object(pdfmd, "installed_package_folder", return_value=self.root / "tex" / "nulabreport") as asked:
            first = pdfmd.find_kit("nulabreport", project)
            second = pdfmd.find_kit("nulabreport", project)
        self.assertEqual((first.cached, second.cached, asked.call_count), (False, True, 1))
        self.assertTrue((self.root / "cache" / "pdfmd" / "kits.json").is_file())

    def run_kits(self, *args, cwd=None):
        environment = {**os.environ, "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], capture_output=True, text=True,
                              cwd=cwd or self.root, env=environment)

    def test_kits_lists_and_shows_and_checks(self):
        make_kit(self.root / "kits" / "nulabreport")
        write(self.root / "kits" / "broken" / ".kit", "kit-format: 3\n")
        listing = self.run_kits("--kits", "--no-auto", "kpsewhich")
        self.assertIn("nulabreport 1.30.0", listing.stdout)
        self.assertIn("modes: qca (220, chem 220), orgchem (211, 212), genchem (101)", listing.stdout)
        self.assertIn("needs a newer pdfmd", listing.stderr)
        self.assertEqual(listing.returncode, 1)                                      # a broken kit is an error, the rest is shown
        shown = self.run_kits("--kits", "nulab_report", "--no-auto", "kpsewhich")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("mode      genchem (101)  [default]", shown.stdout)
        self.assertIn("carries   nulabreport.sty, assets/", shown.stdout)
        miss = self.run_kits("--kits", "zzz", "--no-auto", "kpsewhich")
        self.assertEqual(miss.returncode, 1)
        self.assertIn("no kit called `zzz`", miss.stderr)

    def test_no_kit_at_all_says_how_to_make_one_known(self):
        empty = self.run_kits("--kits", "--no-auto", "kpsewhich", cwd=self.root)
        self.assertEqual(empty.returncode, 0)
        self.assertIn("No kit found", empty.stdout)

    def test_a_build_that_selects_no_kit_never_loads_the_kit_code(self):
        probe = ("import sys; sys.path.insert(0, %r); import pdfmd; "
                 "pdfmd.configured_kits; assert 'pdfmd_kits' not in sys.modules; print('clean')" % str(ROOT))
        done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), "clean", done.stderr)


if __name__ == "__main__":
    unittest.main()
