"""Chemical structures written as text: ```smiles and ::: smiles blocks (v3.31.42, pdfmd_smiles and pdfmd_lua/smiles.lua).

The parsing and the settings need nothing; the drawing needs RDKit (the tests that draw are skipped without it), the builds
need Pandoc too.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd_smiles  # noqa: E402
from pdfmd_smiles import batch  # noqa: E402

try:
    import rdkit  # noqa: F401
    HAS_RDKIT = True
except ImportError:
    HAS_RDKIT = False

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
MOLFILE = """
  RDKit          2D

  2  1  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2990    0.7500    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
M  END
"""


class Settings(unittest.TestCase):
    def test_defaults_are_filled_in(self):
        self.assertEqual(pdfmd_smiles.resolve(None), pdfmd_smiles.DEFAULTS)

    def test_a_field_is_checked_and_an_alias_is_read(self):
        chosen = pdfmd_smiles.resolve({"columns": "2", "office-format": "SVG", "bond_length": 50})
        self.assertEqual((chosen["per-row"], chosen["office-format"], chosen["bond-length"]), (2, "svg", 50))

    def test_what_is_wrong_is_named(self):
        for bad, words in (({"engine": "paint"}, "choose one of"), ({"per-row": "0"}, "at least 1"),
                           ({"dpi": "high"}, "whole number"), ({"colour": "red"}, "unknown setting"), ("engine", "mapping")):
            with self.assertRaises(pdfmd_smiles.SmilesError) as caught:
                pdfmd_smiles.resolve(bad)
            self.assertIn(words, str(caught.exception))


class Reading(unittest.TestCase):
    def test_the_kind_is_read_from_the_text_or_the_extension(self):
        self.assertEqual(pdfmd_smiles.detect_kind(ASPIRIN), "smiles")
        self.assertEqual(pdfmd_smiles.detect_kind(MOLFILE), "mol")
        self.assertEqual(pdfmd_smiles.detect_kind("InChI=1S/CH4/h1H4"), "inchi")
        self.assertEqual(pdfmd_smiles.detect_kind("@<TRIPOS>MOLECULE\nx\n"), "mol2")
        self.assertEqual(pdfmd_smiles.detect_kind("anything", extension=".sdf"), "mol")
        self.assertEqual(pdfmd_smiles.detect_kind(MOLFILE, kind="smiles"), "smiles")        # a kind asked for wins

    def test_a_line_is_a_structure_and_a_word_after_it_its_name(self):
        found = pdfmd_smiles.split_molecules(f"\n{ASPIRIN} aspirin tablet\nCCO\n\n", "smiles")
        self.assertEqual(found, [(ASPIRIN, "aspirin tablet"), ("CCO", "")])

    def test_a_molfile_keeps_its_blank_title_line_and_an_sd_file_is_split(self):
        found = pdfmd_smiles.split_molecules(MOLFILE + "$$$$\n" + MOLFILE + "$$$$\n", "mol")
        self.assertEqual(len(found), 2)
        self.assertTrue(found[0][0].startswith("\n  RDKit"))


@unittest.skipUnless(HAS_RDKIT, "needs RDKit")
class Drawing(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-smiles-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def ask(self, items, target="html", settings=None):
        out = io.StringIO()
        request = {"cache": str(self.directory), "settings": settings or {}, "target": target, "items": items}
        batch.main(io.StringIO(json.dumps(request)), out)
        return json.loads(out.getvalue())

    def test_a_block_is_drawn_once_and_kept(self):
        first = self.ask([{"text": ASPIRIN, "attributes": {}}])[0]
        self.assertEqual((first["format"], first["count"]), ("svg", 1))
        stamp = Path(first["file"]).stat().st_mtime_ns
        again = self.ask([{"text": ASPIRIN, "attributes": {}}])[0]
        self.assertEqual(again["file"], first["file"])
        self.assertEqual(Path(again["file"]).stat().st_mtime_ns, stamp)

    def test_every_setting_that_changes_the_drawing_changes_the_key(self):
        files = {self.ask([{"text": ASPIRIN, "attributes": attributes}])[0]["file"]
                 for attributes in ({}, {"bond-length": "50"}, {"cell-width": "400"}, {"format": "png"}, {"dpi": "150", "format": "png"})}
        self.assertEqual(len(files), 5)

    def test_the_format_follows_the_output(self):
        got = {target: self.ask([{"text": ASPIRIN, "attributes": {}}], target=target)[0]["format"]
               for target in ("html", "typst", "office", "md")}
        self.assertEqual(got, {"html": "svg", "typst": "svg", "office": "png", "md": "svg"})
        self.assertEqual(self.ask([{"text": ASPIRIN, "attributes": {}}], target="office",
                                  settings={"office-format": "svg"})[0]["format"], "svg")
        # LaTeX reads a PDF; without rsvg-convert the way out is a PNG, never a failure
        self.assertIn(self.ask([{"text": ASPIRIN, "attributes": {}}], target="tex")[0]["format"],
                      ("pdf", "png") if shutil.which("rsvg-convert") is None else ("pdf",))

    def test_one_line_one_structure_laid_in_rows(self):
        answer = self.ask([{"text": f"{ASPIRIN}\nCCO\nCCN\nCCC\n", "attributes": {"columns": "2"}}])[0]
        self.assertEqual((answer["count"], answer["width"], answer["height"]), (4, 500, 400))

    def test_a_molfile_and_the_mistakes(self):
        answers = self.ask([{"text": MOLFILE, "extension": ".mol", "attributes": {}},
                            {"text": "not a smiles", "attributes": {}},
                            {"text": ASPIRIN, "attributes": {"engine": "chemfig"}},
                            {"text": "  \n", "attributes": {}},
                            {"text": ASPIRIN, "attributes": {"kind": "pdb"}}])
        self.assertEqual(answers[0]["count"], 1)
        self.assertIn("could not read", answers[1]["error"])
        self.assertIn("choose one of", answers[2]["error"])
        self.assertIn("empty", answers[3]["error"])
        self.assertIn("kind", answers[4]["error"])

    def test_a_wrong_setting_in_the_request_is_an_error_for_every_block(self):
        answers = self.ask([{"text": ASPIRIN, "attributes": {}}] * 2, settings={"dpi": "high"})
        self.assertEqual(len(answers), 2)
        self.assertIn("whole number", answers[0]["error"])


class WithoutRdkit(unittest.TestCase):
    def test_a_block_is_answered_with_how_to_install_it(self):
        saved = {name: sys.modules.get(name) for name in ("rdkit", "rdkit.Chem", "rdkit.Chem.Draw")}
        try:
            for name in saved:
                sys.modules[name] = None                      # an import of these raises ImportError
            out = io.StringIO()
            batch.main(io.StringIO(json.dumps({"cache": tempfile.gettempdir(), "items": [{"text": ASPIRIN, "attributes": {}}]})), out)
        finally:
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
        self.assertIn("pip install rdkit", json.loads(out.getvalue())[0]["error"])


@unittest.skipUnless(HAS_RDKIT and shutil.which("pandoc"), "needs RDKit and Pandoc")
class Build(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-smiles-build-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, text: str, *arguments: str, name: str = "doc.md") -> tuple[str, subprocess.CompletedProcess]:
        source = self.directory / name
        if not text.startswith("---"):
            text = "---\ntitle: t\n---\n\n" + text         # Pandoc's own Markdown: gfm reads neither a div nor code attributes
        source.write_text(text, encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"],
                       "XDG_CACHE_HOME": str(self.directory / "cache"), "PDFMD_NO_PROMPT": "1"}
        environment.pop("PDFMD_STRICT", None)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), str(source), "--to", "html", *arguments],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.directory, env=environment)
        output = source.with_suffix(".html")
        return (output.read_text(encoding="utf-8") if output.is_file() else ""), done

    def test_a_fenced_block_becomes_a_figure_with_its_caption(self):
        html, done = self.build('```{.smiles #fig:asa caption="Aspirin"}\n' + ASPIRIN + '\n```\n')
        self.assertIn("data:image/svg+xml;base64,", html, done.stderr)
        self.assertIn("Aspirin", html)
        self.assertNotIn(ASPIRIN, html)

    def test_a_div_reads_a_nitro_group_that_markdown_takes_for_a_link(self):
        html, done = self.build("::: {.smiles caption=\"Nitromethane\"}\nC[N+](=O)[O-]\n:::\n")
        self.assertIn("data:image/svg+xml;base64,", html, done.stderr)
        self.assertNotIn("WARN  smiles", done.stderr)

    def test_a_file_beside_the_document(self):
        (self.directory / "x.mol").write_text(MOLFILE, encoding="utf-8")
        html, done = self.build('```{.smiles file="x.mol"}\n```\n')
        self.assertIn("data:image/svg+xml;base64,", html, done.stderr)

    def test_a_missing_file_and_a_bad_structure_leave_the_block_as_code_with_a_warning(self):
        html, done = self.build('```{.smiles file="nowhere.mol"}\n```\n\n```smiles\nnot a smiles\n```\n')
        said = done.stdout + done.stderr
        self.assertIn("nowhere.mol", said)
        self.assertIn("could not read", said)
        self.assertIn("not a smiles", html)
        self.assertNotIn("data:image/svg+xml", html)

    def test_no_auto_smiles_leaves_the_blocks_alone(self):
        html, _ = self.build("```smiles\n" + ASPIRIN + "\n```\n", "--no-auto", "smiles")
        self.assertIn(ASPIRIN, html)
        self.assertNotIn("data:image/svg+xml", html)

    def test_the_document_settings_reach_the_drawing(self):
        text = "---\npdfmd-options:\n  smiles: {per-row: 1, cell-width: 123}\n---\n\n```smiles\nCCO\nCCN\n```\n"
        html, done = self.build(text)
        self.assertIn("data:image/svg+xml;base64,", html, done.stderr)
        import base64
        import re
        svg = base64.b64decode(re.search(r"base64,([A-Za-z0-9+/=]+)", html).group(1)).decode()
        self.assertIn("width='123px'", svg)
        self.assertIn("height='400px'", svg)                  # two rows, because per-row is 1

    def test_a_wrong_setting_stops_the_build_and_names_the_key(self):
        _, done = self.build("---\npdfmd-options:\n  smiles: {dpi: high}\n---\n\n```smiles\nCCO\n```\n")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("whole number", done.stderr + done.stdout)


if __name__ == "__main__":
    unittest.main()
