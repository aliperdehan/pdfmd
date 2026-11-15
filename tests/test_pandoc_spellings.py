"""British aliases of Pandoc's variables, through the checkout launcher."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: F401


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Spellings(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-spellings-")
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

    def build(self, front="", writer="latex", args=()):
        self.write("d.md", "---\ntitle: T\n" + front + "---\n\n[Link](https://example.org).\n")
        out = self.root / "out.txt"
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "d.md", "--to", writer,
                               "-s", "-o", str(out), "--no-stamp", "--no-backup", "--no-auto", "crossref", *args],
                              check=False, cwd=self.root, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return out.read_text(encoding="utf-8"), done.stdout + done.stderr

    def test_front_matter_latex_hypersetup(self):
        text, _ = self.build("colourlinks: true\nlinkcolour: red\nurlcolour: blue\n")
        self.assertIn("colorlinks=true", text)
        self.assertIn("linkcolor={red}", text)
        self.assertIn("urlcolor={blue}", text)

    def test_html_css_light_and_dark_colours(self):
        text, _ = self.build("fontcolour: '#123456'\nbackgroundcolourdark: '#abcdef'\n", "html5")
        self.assertIn("#123456", text)
        self.assertIn("#abcdef", text)

    def test_typst_link_colours(self):
        text, _ = self.build("linkcolour: '123456'\ncitecolour: 'abcdef'\nfilecolour: '654321'\n", "typst")
        for key, colour in (("linkcolor", "123456"), ("citecolor", "abcdef"), ("filecolor", "654321")):
            self.assertIn(key + ": [" + colour + "],", text)

    def test_metadata_file(self):
        self.write("metadata.yaml", "colourlinks: true\nurlcolour: green\n")
        text, _ = self.build()
        self.assertIn("urlcolor={green}", text)

    def test_document_alias_overrides_lower_pandoc_spelling_and_conversely(self):
        self.write("metadata.yaml", "urlcolor: red\n")
        self.assertIn("urlcolor={blue}", self.build("urlcolour: blue\n")[0])
        self.write("metadata.yaml", "urlcolour: red\n")
        self.assertIn("urlcolor={blue}", self.build("urlcolor: blue\n")[0])

    def test_folder_and_global_setup_metadata(self):
        self.write(".pdfmd/metadata.yaml", "urlcolour: green\n")
        self.assertIn("urlcolor={green}", self.build()[0])
        self.write("config/pdfmd/metadata.yaml", "linkcolour: red\n")
        self.assertIn("linkcolor={red}", self.build(args=("--preset", str(self.root / "config/pdfmd/metadata.yaml")))[0])

    def test_kit_metadata(self):
        self.write("kits/colours/.kit", "kit-format: 1\nname: colours\ndefaults: metadata.yaml\n")
        self.write("kits/colours/metadata.yaml", "urlcolour: green\n")
        text, _ = self.build("pdfmd-options: {kit: colours}\n")
        self.assertIn("urlcolor={green}", text)

    def test_cli_token_forms(self):
        for args in (("-V", "urlcolour=red"), ("-Vurlcolour=red",), ("--variable=urlcolour=red",),
                     ("--variable", "urlcolour=red"), ("--var", "urlcolour=red"),
                     ("-M", "urlcolour:red"), ("-Murlcolour=red",),
                     ("--metadata", "urlcolour:red"), ("--metadata=urlcolour=red",)):
            with self.subTest(args=args):
                self.assertIn("urlcolor={red}", self.build(args=args)[0])

    def test_pandoc_spelling_wins_in_one_place_with_one_note(self):
        for front in ("urlcolour: red\nurlcolor: blue\n", "urlcolor: blue\nurlcolour: red\n"):
            text, log = self.build(front)
            self.assertIn("urlcolor={blue}", text)
            notes = [line for line in log.splitlines() if line.startswith("NOTE") and "urlcolour" in line]
            self.assertEqual(len(notes), 1, log)
            self.assertIn("ignored", notes[0])

    def test_cli_pandoc_spelling_wins_in_both_orders(self):
        for flag in ("-V", "-M"):
            for args in ((flag, "urlcolour=red", flag, "urlcolor=blue"),
                         (flag, "urlcolor=blue", flag, "urlcolour=red")):
                with self.subTest(args=args):
                    text, log = self.build(args=args)
                    self.assertIn("urlcolor={blue}", text)
                    self.assertEqual(sum(line.startswith("NOTE") and "urlcolour" in line
                                         for line in log.splitlines()), 1, log)

    def test_non_colour_spellings_and_beamer(self):
        self.assertIn("\\usecolortheme", self.build("colourtheme: dove\n", "beamer")[0])
        self.assertIn("Example Organisation", self.build("organisation: Example Organisation\n", "rst")[0])
        self.assertIn("MIT", self.build("licence: MIT\n", "tei")[0])
        self.assertIn("center: false", self.build("centre: false\n", "revealjs")[0])

    def test_cli_metadata_still_overrides_front_matter_alias(self):
        self.assertIn("urlcolor={green}", self.build("urlcolour: red\n", args=("-M", "urlcolor=green"))[0])

    def test_metadata_file_collision_and_aliases_are_removed_before_user_filters(self):
        self.write("metadata.yaml", "urlcolour: red\nurlcolor: blue\n")
        self.write("inspect.lua", 'function Meta(m)\nassert(m.urlcolour == nil)\n'
                   'assert(pandoc.utils.stringify(m.urlcolor) == "blue")\nend\n')
        text, log = self.build(args=("--lua-filter", str(self.root / "inspect.lua")))
        self.assertIn("urlcolor={blue}", text)
        self.assertEqual(sum(line.startswith("NOTE") and "urlcolour" in line for line in log.splitlines()), 1, log)

    def test_alias_values_and_tokens_after_separator_remain_literal(self):
        from pdfmd_args.metadata import command_aliases

        original = ["-M", "title=urlcolour: red", "-Vlinkcolour=https://example.org/a=b:c", "--", "-Vurlcolour=red"]
        self.assertEqual(command_aliases(original),
                         ["-M", "title=urlcolour: red", "-Vlinkcolor=https://example.org/a=b:c", "--", "-Vurlcolour=red"])


if __name__ == "__main__":
    unittest.main()
