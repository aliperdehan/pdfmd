"""The bare `::: csv` div and `csv: off`: the spellings the detection and the native tier know, the filter that is
(not) added, and a real Pandoc run through the whole pipeline."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
DATA = "name,qty\nwater,3\nacid,4\n"
BARE = f"::: csv\n{DATA}:::\n"
BRACED = f"::: {{.csv}}\n{DATA}:::\n"


class Detection(unittest.TestCase):
    def test_the_bare_div_is_detected_like_the_braced_one(self):
        for text in ("::: csv", "  ::: csv  ", "::::: csv", "::: {.csv}", '::: {.csv file="a.csv"}', "::: {#t .csv rows=3}"):
            with self.subTest(text=text):
                self.assertTrue(pdfmd.CSV_DIV_RE.search(text))

    def test_other_classes_are_not(self):
        for text in ("::: csvfile", "::: csv-x", "::: csvs", "::: .csv", "csv", "a ::: csv", "::: {.csvx}", "`::: csv` is the div",
                     "::: calc"):
            with self.subTest(text=text):
                self.assertFalse(pdfmd.CSV_DIV_RE.search(text))

    def test_the_native_tier_reads_the_bare_div_and_only_it(self):
        self.assertTrue(pdfmd.CSV_DIV_LINE_RE.match("::: csv"))
        self.assertTrue(pdfmd.CSV_DIV_LINE_RE.match("::: {.csv}"))
        self.assertIsNone(pdfmd.CSV_DIV_LINE_RE.match("::: csvfile"))
        self.assertIsNone(pdfmd.CSV_DIV_LINE_RE.match("::: csv-x"))
        self.assertIsNone(pdfmd.CSV_DIV_LINE_RE.match("::: csv {.x}"))


class NativeTier(unittest.TestCase):
    """The built-in renderer (no Pandoc) reads the div itself."""

    def normalise(self, text: str, **keywords):
        source, counts = pdfmd.normalise_gfm(text, "inkmd", **keywords)
        return source.text, counts

    def test_a_bare_div_becomes_a_table_like_the_braced_one(self):
        bare, counts = self.normalise(BARE)
        braced, _ = self.normalise(BRACED)
        self.assertEqual(bare, braced)
        self.assertIn("| name", bare)
        self.assertEqual(counts.get("csv"), 1)

    def test_other_class_words_are_not_tables(self):
        for word in ("csvfile", "csv-x"):
            with self.subTest(word=word):
                text, counts = self.normalise(f"::: {word}\n{DATA}:::\n")
                self.assertNotIn("| name", text)
                self.assertIn("water,3", text)
                self.assertNotIn("csv", counts)

    def test_csv_off_leaves_the_data_as_written(self):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "d.md"
            document.write_text("---\ntitle: T\npdfmd-options:\n  csv: off\n---\n\n" + BRACED, encoding="utf-8")
            text, counts = self.normalise(document.read_text(encoding="utf-8"), source_path=document)
            self.assertNotIn("| name", text)
            self.assertIn("water,3", text)
            self.assertNotIn("csv", counts)
            document.write_text("---\ntitle: T\npdfmd-options:\n  csv: {rows: 30}\n---\n\n" + BRACED, encoding="utf-8")
            text, counts = self.normalise(document.read_text(encoding="utf-8"), source_path=document)
            self.assertIn("| name", text)                                  # a mapping leaves the tables on


class Switch(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-csv-switch-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def document(self, options: str = "", body: str = BRACED) -> Path:
        path = self.directory / "d.md"
        path.write_text(f"---\ntitle: T\n{options}---\n\n{body}", encoding="utf-8")
        return path

    def option(self, text: str) -> str:
        return f"pdfmd-options:\n  {text}\n"

    def test_the_setting_in_every_spelling(self):
        for text, off in (("csv: off", True), ("csv: false", True), ("csv: {enabled: false}", True), ("csv: {enabled: off}", True),
                          ("csv: on", False), ("csv: true", False), ("csv: {enabled: true}", False), ("csv: {rows: 30}", False),
                          ("csv: {rows: 30, enabled: no}", True), ("calc: off", False)):
            with self.subTest(text=text):
                self.assertEqual(pdfmd.csv_is_off(self.document(self.option(text)), []), off)
        self.assertFalse(pdfmd.csv_is_off(self.document(), []))

    def test_a_bad_value_is_refused_by_name(self):
        with self.assertRaises(SystemExit) as caught:
            pdfmd.csv_is_off(self.document(self.option("csv: {enabled: banana}")), [])
        self.assertIn("pdfmd-options.csv.enabled must be true or false", str(caught.exception))

    def test_the_environment_wins_over_the_document(self):
        document = self.document(self.option("csv: off"))
        for value, off in (("on", False), ("off", True)):
            with self.subTest(value=value):
                os.environ[pdfmd.CSV_ENABLED_ENV] = value
                self.addCleanup(os.environ.pop, pdfmd.CSV_ENABLED_ENV, None)
                self.assertEqual(pdfmd.csv_is_off(document, []), off)
        os.environ.pop(pdfmd.CSV_ENABLED_ENV, None)

    def test_the_filter_is_not_added_when_it_is_off(self):
        for options, added in ((self.option("csv: off"), False), (self.option("csv: {rows: 30}"), True), ("", True)):
            with self.subTest(options=options):
                document = self.document(options)
                arguments = pdfmd.csv_table_filter_args(document, None, Path("csv_table.lua"), [])
                self.assertEqual(bool(arguments), added)
        self.assertEqual(pdfmd.csv_table_filter_args(self.document("", BARE), None, Path("csv_table.lua"), [])[:1], ["--lua-filter"])

    def test_the_caps_are_still_read_from_a_mapping_and_not_from_off(self):
        self.assertEqual(pdfmd.csv_defaults(self.document(self.option("csv: {rows: 30}")), [])["rows"], 30)
        self.assertEqual(pdfmd.csv_defaults(self.document(self.option("csv: off")), []), pdfmd.CSV_DEFAULTS)
        with self.assertRaises(SystemExit) as caught:
            pdfmd.csv_defaults(self.document(self.option("csv: banana")), [])
        self.assertIn("must be a mapping", str(caught.exception))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class RealRuns(unittest.TestCase):
    """pdfmd itself (the Pandoc command it builds), `--to native`: a Table, or the Div as it was written."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-csv-real-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def build(self, options: str, body: str, *flags: str, environment: dict | None = None):
        (self.directory / "d.md").write_text(f"---\ntitle: T\n{options}---\n\n{body}", encoding="utf-8")
        env = {**os.environ, "PDFMD_CONFIG": ""}
        env.pop(pdfmd.CSV_ENABLED_ENV, None)
        env.update(environment or {})
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "native", "-o", "out.native", "--no-stamp",
                               "--no-backup", "--no-auto", "crossref", *flags], cwd=self.directory, capture_output=True,
                              text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return (self.directory / "out.native").read_text(encoding="utf-8"), done.stdout + done.stderr

    def assert_table(self, native: str):
        self.assertIn("TableBody", native)
        self.assertIn('Str "water"', native)
        self.assertNotIn("Div", native)

    def assert_plain_div(self, native: str, said: str):
        self.assertNotIn("TableBody", native)
        self.assertIn('"csv"', native)                                      # the Div with its class
        self.assertIn("water,3", native.replace('Str "water,3"', "water,3"))
        self.assertNotIn("WARN", said)

    def test_a_bare_div_builds_the_same_table_as_the_braced_one(self):
        bare, _ = self.build("", BARE)
        braced, _ = self.build("", BRACED)
        self.assert_table(bare)
        self.assertEqual(bare, braced)

    def test_the_other_class_words_stay_divs(self):
        for word in ("csvfile", "csv-x"):
            with self.subTest(word=word):
                native, said = self.build("", f"::: {word}\n{DATA}:::\n")
                self.assertNotIn("TableBody", native)
                self.assertIn(f'"{word}"', native)

    def test_csv_off_leaves_a_plain_div_with_its_text(self):
        for options in (self.option_text("csv: off"), self.option_text("csv: {enabled: false}")):
            with self.subTest(options=options):
                for body in (BRACED, BARE):
                    native, said = self.build(options, body)
                    self.assert_plain_div(native, said)

    def option_text(self, text: str) -> str:
        return f"pdfmd-options:\n  {text}\n"

    def test_a_mapping_without_enabled_keeps_the_tables_and_its_caps(self):
        many = "n,v\n" + "".join(f"{n},{n}\n" for n in range(1, 40))
        native, said = self.build(self.option_text("csv: {rows: all}"), f"::: csv\n{many}:::\n")
        self.assertIn("TableBody", native)
        self.assertEqual(len(re.findall(r"\bRow\b", native)), 40)             # the header and 39 rows: `rows: all` was read
        self.assertNotIn("kept", said)

    def test_the_flags_and_the_environment(self):
        native, said = self.build("", BRACED, "--no-csv")
        self.assert_plain_div(native, said)
        native, _ = self.build(self.option_text("csv: off"), BRACED, "--csv")
        self.assert_table(native)                                           # the command line wins
        native, said = self.build("", BRACED, environment={pdfmd.CSV_ENABLED_ENV: "off"})
        self.assert_plain_div(native, said)                                 # what a -j worker sees

    def test_a_missing_file_does_not_warn_when_csv_is_off(self):
        native, said = self.build(self.option_text("csv: off"), '::: {.csv file="missing.csv"}\n:::\n')
        self.assertNotIn("WARN", said)
        self.assertNotIn("TableBody", native)


if __name__ == "__main__":
    unittest.main()
