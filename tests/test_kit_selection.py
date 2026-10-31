"""v3.31.31: kits, C2 (entry 3du): choosing kits. The grammar of a `kit:` value, the layers that stack, `--kit` and the
`kit-stack` setting, and what a chosen kit brings to a build (its defaults, its mode's text, its Lua filter, its folder on the
resource path). Every kit is a fixture; the real nulabreport is never read."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pdfmd_kits import selection  # noqa: E402
from pdfmd_kits.selection import OFF, Selection, SelectionError, combine, parse, parse_stack_setting, stack  # noqa: E402

PANDOC = shutil.which("pandoc")


def refs(selections):
    return [(item.ref, item.mode) for item in selections]


class Grammar(unittest.TestCase):
    def test_every_spelling_of_one_choice(self):
        for text in ("nulabreport:qca", "nulabreport[qca]", "[qca]nulabreport", " nulabreport : qca "):
            self.assertEqual(refs(parse(text)), [("nulabreport", "qca")], text)
        for value in ({"nulabreport": "qca"}, {"nulabreport": {"mode": "qca"}}, ["nulabreport:qca"], [{"nulabreport": "qca"}]):
            self.assertEqual(refs(parse(value)), [("nulabreport", "qca")], value)

    def test_the_spellings_as_yaml_reads_them(self):
        for text in ("kit: nulabreport:qca", "kit: nulabreport[qca]", 'kit: "[qca]nulabreport"', "kit: {nulabreport: qca}",
                     "kit:\n  nulabreport: qca", "kit:\n  - nulabreport:qca", "kit:\n  nulabreport:\n    mode: qca"):
            self.assertEqual(refs(parse(yaml.safe_load(text)["kit"])), [("nulabreport", "qca")], text)

    def test_a_number_is_a_mode_or_a_name(self):
        self.assertEqual(refs(parse({"nulabreport": 220})), [("nulabreport", "220")])
        self.assertEqual(refs(parse("nulabreport:220")), [("nulabreport", "220")])

    def test_no_mode_and_extra_settings(self):
        self.assertEqual(refs(parse("nulabreport")), [("nulabreport", None)])
        self.assertEqual(refs(parse({"nulabreport": None})), [("nulabreport", None)])
        item = parse({"x": {"mode": "m", "colour": "red"}})[0]
        self.assertEqual((item.mode, item.options), ("m", {"colour": "red"}))

    def test_a_list_keeps_its_order(self):
        self.assertEqual(refs(parse(["b", {"a": "m"}, "c:n"])), [("b", None), ("a", "m"), ("c", "n")])

    def test_a_value_with_a_separator_or_a_leading_tilde_or_dot_is_a_path(self):
        for path in ("~/kits/x", "./x", "../x", "/opt/x", "C:\\kits\\x", "kits/x", ".hidden"):
            self.assertEqual(refs(parse(path)), [(path, None)], path)
        self.assertEqual(refs(parse({"~/kits/x": "qca"})), [("~/kits/x", "qca")])

    def test_the_off_words_and_yaml_booleans(self):
        for value in ("none", "off", "NO", "False", False, ["off"]):
            self.assertEqual(parse(value), [OFF], value)
        for text in ("kit: no", "kit: off", "kit: false", "kit: none"):
            self.assertEqual(parse(yaml.safe_load(text)["kit"]), [OFF], text)
        self.assertEqual(parse(None), [])

    def test_a_value_that_cannot_be_read_says_why(self):
        for bad in ("", "[qca]", "nulabreport[", "nulabreport:", ":qca", True, {"": "x"}, {"x": ["a"]}, {"x": True}):
            with self.assertRaises(SelectionError, msg=repr(bad)):
                parse(bad)

    def test_the_layer_is_recorded(self):
        self.assertEqual([item.layer for item in parse(["a", "b"], "folder")], ["folder", "folder"])


class Stacking(unittest.TestCase):
    def test_a_higher_layer_replaces_what_it_names_and_keeps_the_rest(self):
        low = parse({"nulabreport": {"mode": "orgchem", "colour": "red"}}, "global")
        high = parse({"nulabreport": "qca"}, "document")
        result = stack([low, high])
        self.assertEqual((refs(result), result[0].options, result[0].layer), ([("nulabreport", "qca")], {"colour": "red"}, "document"))
        again = stack([low, parse("nulabreport", "document")])
        self.assertEqual(refs(again), [("nulabreport", "orgchem")])             # no mode named above: the one below stays

    def test_the_same_kit_is_matched_by_its_normalised_name(self):
        self.assertEqual(refs(stack([parse("nulabreport:a"), parse("Nu-Lab-Report:b")])), [("Nu-Lab-Report", "b")])

    def test_different_kits_stack_in_order(self):
        self.assertEqual(refs(stack([parse("a"), parse(["b", "c"]), parse("d")])), [("a", None), ("b", None), ("c", None), ("d", None)])

    def test_none_drops_what_is_below_and_what_is_above_it_stays(self):
        self.assertEqual(refs(stack([parse("a"), parse(["b", "none", "c"])])), [("c", None)])
        self.assertEqual(stack([parse("a"), parse("none")]), [])

    def test_a_path_is_its_own_kit(self):
        self.assertEqual(len(stack([parse("~/k/x"), parse("x")])), 2)


class Combining(unittest.TestCase):
    def layers(self):
        return {"global": parse("a:g", "global"), "preset": parse("p", "preset"), "folder": parse("f:1", "folder"),
                "document": parse({"a": "doc"}, "document")}

    def test_the_layers_alone(self):
        self.assertEqual(refs(combine(self.layers(), None)), [("a", "doc"), ("p", None), ("f", "1")])

    def test_kit_replaces_every_layer_by_default(self):
        self.assertEqual(refs(combine(self.layers(), parse("z:9"))), [("z", "9")])

    def test_repeated_kit_stacks_in_order(self):
        self.assertEqual(refs(combine(self.layers(), parse("y") + parse("z"))), [("y", None), ("z", None)])

    def test_bare_kit_and_none_mean_no_kit_whatever_kit_stack_says(self):
        for setting in ("off", "all", frozenset({"document"})):
            self.assertEqual(combine(self.layers(), [OFF], setting), [])
            self.assertEqual(combine(self.layers(), [], setting), [])

    def test_stack_all_keeps_every_layer_and_the_same_kit_changes_only_what_it_names(self):
        self.assertEqual(refs(combine(self.layers(), parse("a:run"), "all")), [("a", "run"), ("p", None), ("f", "1")])

    def test_stack_some_layers_drops_the_rest(self):
        self.assertEqual(refs(combine(self.layers(), parse("z"), frozenset({"folder", "document"}))),
                         [("f", "1"), ("a", "doc"), ("z", None)])
        self.assertEqual(refs(combine(self.layers(), parse("z"), frozenset({"global"}))), [("a", "g"), ("z", None)])

    def test_none_among_the_command_line_entries_drops_the_stack_below_it(self):
        self.assertEqual(refs(combine(self.layers(), parse(["none", "z"]), "all")), [("z", None)])

    def test_the_setting_is_read_from_its_spellings(self):
        self.assertEqual(parse_stack_setting(None), "off")
        self.assertEqual(parse_stack_setting("off"), "off")
        self.assertEqual(parse_stack_setting(False), "off")
        self.assertEqual(parse_stack_setting("all"), "all")
        self.assertEqual(parse_stack_setting(True), "all")
        self.assertEqual(parse_stack_setting("folder,document"), frozenset({"folder", "document"}))
        self.assertEqual(parse_stack_setting(["Global", "preset"]), frozenset({"global", "preset"}))
        with self.assertRaises(SelectionError):
            parse_stack_setting("folders")


KIT = """\
kit-format: 1
name: lab
version: 2.0
package: labstyle
modes:
  qca: {aliases: [220], options: [qca], metadata: {course: "CHEM 220L"}}
  org: {aliases: [211], defaults: org.yaml}
defaults: defaults.yaml
lua: [lab.lua]
latex-keys: {experiment: LabExperiment}
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@unittest.skipUnless(PANDOC, "Pandoc is needed")
class Builds(unittest.TestCase):
    """Through pdfmd itself: the Pandoc command and the LaTeX it writes."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        kit = self.root / "course" / "kits" / "lab"
        write(kit / ".kit", KIT)
        write(kit / "defaults.yaml", "fontsize: 12pt\nbibliography: refs.bib\npdfmd-options:\n  parts: auto\n")
        write(kit / "org.yaml", "fontsize: 11pt\n")
        write(kit / "refs.bib", "@book{k, title={T}, author={Someone}, year=2000}\n")
        write(kit / "lab.lua", "function Pandoc(d) return d end\n")
        write(kit / "labstyle.sty", "\\ProvidesPackage{labstyle}\n")
        self.config = write(self.root / "cfg" / "config.yaml", f"kits: [{self.root / 'course' / 'kits'}]\n")
        self.folder = self.root / "course" / "LR1"
        self.write_doc("pdfmd-options: {kit: lab}")

    def write_doc(self, line: str = "", extra: str = "") -> Path:
        return write(self.folder / "report.md", f"---\ntitle: T\n{line}\n{extra}---\nHello [@k].\n")

    def run_pdfmd(self, *args, config=True, verbose=True):
        environment = {**os.environ, "PDFMD_CONFIG": str(self.config) if config else "", "XDG_CACHE_HOME": str(self.root / "cache"),
                       "PDFMD_NO_PROMPT": "1", "PDFMD_BUILD_LOG": "off"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report.md", "--to", "latex", "-o", "out.tex", "--no-backup",
                               "--no-stamp", *(["--verbose"] if verbose else []), *args],
                              capture_output=True, text=True, cwd=self.folder, env=environment)
        out = self.folder / "out.tex"
        return done, out.read_text(encoding="utf-8") if done.returncode == 0 and out.is_file() else ""

    def test_a_kit_brings_its_defaults_its_folder_and_its_lua(self):
        done, tex = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertIn("AUTO KIT  lab 2.0 (chosen in the document)", done.stdout)
        self.assertIn("12pt", tex)                                                         # defaults.yaml
        self.assertIn("(Someone 2000)", tex)                                               # refs.bib found in the kit's folder
        self.assertIn("lab.lua", done.stdout)                                              # the filter is on the command line
        command = done.stdout + done.stderr
        self.assertIn(f"(cwd={self.root / 'course' / 'kits' / 'lab'}", command)            # the first metadata file is the kit's: Pandoc runs there

    def test_no_kit_chosen_changes_nothing(self):
        self.write_doc()
        done, tex = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("AUTO KIT", done.stdout)
        self.assertNotIn("lab.lua", done.stdout)
        self.assertNotIn("12pt", tex)

    def test_the_document_beats_a_folder_and_a_folder_beats_the_kit(self):
        write(self.root / "course" / ".pdfmd" / "metadata.yaml", "fontsize: 11pt\n")
        done, tex = self.run_pdfmd()
        self.assertIn("11pt", tex)
        self.assertNotIn("12pt", tex)
        self.assertIn("(Someone 2000)", tex)                       # Pandoc runs in .pdfmd/ now: the kit's folder is on the resource path
        self.write_doc("pdfmd-options: {kit: lab}", "fontsize: 10pt\n")
        done, tex = self.run_pdfmd()
        self.assertIn("10pt", tex)
        self.assertNotIn("11pt", tex)

    def test_a_modes_text_and_defaults_come_after_the_kits(self):
        done, tex = self.run_pdfmd("--kit", "lab:org")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("11pt", tex)                                                         # org.yaml over defaults.yaml
        done, tex = self.run_pdfmd("--kit", "lab:220")
        self.assertIn("mode qca", done.stdout)                                             # an alias of the mode

    def test_a_folder_chooses_a_kit_by_name_only(self):
        self.write_doc()
        write(self.root / "course" / ".pdfmd" / "config.yaml", "options:\n  kit: lab:220\n")
        done, tex = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertIn("lab 2.0 mode qca (chosen in the folder)", done.stdout)
        write(self.root / "course" / ".pdfmd" / "config.yaml", f"options:\n  kit: {self.root / 'course' / 'kits' / 'lab'}\n")
        done, _ = self.run_pdfmd()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("is a path, and a folder's `kit:` names a kit", done.stderr)

    def test_a_folder_does_not_search_the_projects_kits_folder(self):
        self.write_doc()
        write(self.root / "course" / ".pdfmd" / "config.yaml", "options:\n  kit: lab\n")
        done, _ = self.run_pdfmd(config=False)                                              # kits/ is not registered any more
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("no kit called `lab`", done.stderr)
        self.write_doc("pdfmd-options: {kit: lab}")                                         # the document may: the full search
        done, _ = self.run_pdfmd(config=False)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_layers_stack_and_none_drops_the_ones_below(self):
        write(self.root / "course" / ".pdfmd" / "config.yaml", "options:\n  kit: lab:org\n")
        self.write_doc("pdfmd-options: {kit: lab}")                                         # same kit, no mode named: the folder's stays
        done, tex = self.run_pdfmd()
        self.assertIn("mode org", done.stdout)
        self.write_doc("pdfmd-options: {kit: {lab: qca}}")
        done, _ = self.run_pdfmd()
        self.assertIn("mode qca", done.stdout)
        self.write_doc("pdfmd-options: {kit: none}")
        done, tex = self.run_pdfmd()
        self.assertNotIn("AUTO KIT", done.stdout)
        self.assertNotIn("12pt", tex)

    def test_kit_on_the_command_line_replaces_and_kit_stack_keeps(self):
        self.write_doc("pdfmd-options: {kit: lab:org}")
        done, _ = self.run_pdfmd("--kit", "lab:qca")
        self.assertIn("mode qca (chosen in the command line)", done.stdout)
        done, _ = self.run_pdfmd("--kit", "none")
        self.assertNotIn("AUTO KIT", done.stdout)
        done, _ = self.run_pdfmd("--kit")                                                   # bare, and last
        self.assertNotIn("AUTO KIT", done.stdout)
        done, _ = self.run_pdfmd("--kit-stack", "all", "--kit", "lab")
        self.assertIn("mode org", done.stdout)                                              # the document's mode stays
        done, _ = self.run_pdfmd("--kit-stack", "all", "--kit", "lab:qca")
        self.assertIn("mode qca", done.stdout)
        self.write_doc("pdfmd-options: {kit: lab:org, kit-stack: [global]}")             # the setting from the document
        done, _ = self.run_pdfmd("--kit", "lab:qca")
        self.assertIn("mode qca", done.stdout)

    def test_an_unknown_mode_or_kit_stops_and_says_what_there_is(self):
        self.write_doc("pdfmd-options: {kit: 'lab:physics'}")
        done, _ = self.run_pdfmd()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("has no mode `physics`", done.stderr)
        self.assertIn("qca (220)", done.stderr)
        self.write_doc("pdfmd-options: {kit: nothere}")
        done, _ = self.run_pdfmd()
        self.assertIn("no kit called `nothere`", done.stderr)

    def test_the_global_config_kit_is_the_bottom_layer(self):
        write(self.config, f"kits: [{self.root / 'course' / 'kits'}]\noptions:\n  kit: lab:org\n")
        self.write_doc()
        done, tex = self.run_pdfmd()
        self.assertIn("lab 2.0 mode org (chosen in the global)", done.stdout)
        self.assertIn("11pt", tex)
        self.write_doc("pdfmd-options: {kit: off}")
        done, _ = self.run_pdfmd()
        self.assertNotIn("AUTO KIT", done.stdout)

    def test_the_kits_package_helper_is_read_from_its_kit_file(self):
        import pdfmd
        os.environ["PDFMD_CONFIG"] = str(self.config)
        pdfmd.load_config.cache_clear()
        self.addCleanup(pdfmd.load_config.cache_clear)
        self.addCleanup(os.environ.pop, "PDFMD_CONFIG", None)
        kit_folder = self.root / "course" / "kits" / "lab"
        found = pdfmd.read_package_helper(kit_folder, "labstyle")
        self.assertEqual(found[0]["latex-keys"], {"experiment": "LabExperiment"})
        self.assertEqual(found[1], kit_folder / ".kit")
        self.assertIsNone(pdfmd.read_package_helper(kit_folder, "other"))


if __name__ == "__main__":
    unittest.main()
