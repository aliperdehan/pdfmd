"""v3.28.37: pdfmd names no LaTeX package. What a package brings -- its Lua filter, its Word profile, the front-matter keys
it fills, what a draft pass need not draw -- is found by reading the packages a document loads (its preamble files and
its `header-includes:`, the metadata's too) and their `<package>-pdfmd.yaml` beside the style file."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@unittest.skipUnless(shutil.which("kpsewhich"), "a package is found by kpsewhich")
class Helper(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / "doc"
        tree = Path(self.folder.name) / "texmf" / "tex" / "latex" / "thing"
        patcher = mock.patch.dict(os.environ, {"TEXMFHOME": str(Path(self.folder.name) / "texmf")})
        patcher.start()
        self.addCleanup(patcher.stop)
        pdfmd.kpsewhich_locate.cache_clear() if hasattr(pdfmd.kpsewhich_locate, "cache_clear") else None
        write(tree / "thing.sty", "\\ProvidesPackage{thing}\n")
        write(tree / "thing-pdfmd.yaml",
              "latex-keys:\n  performed: ThingPerformed\nlua:\n  - extra.lua\n"
              "draft-skip:\n  commands: [circuit, bad name]\n  spans: {startdraw: stopdraw}\n")
        write(self.root / "thing.lua", "return {}\n")
        write(self.root / "extra.lua", "return {}\n")
        write(self.root / "thing-office.lua", "return {}\n")
        write(self.root / "other.lua", "return {}\n")
        self.md = write(self.root / "doc.md", "---\ntitle: T\nperformed: 2026-01-02\n---\nBody\n")

    def test_a_package_loaded_by_the_preamble_brings_its_lua_by_convention_and_by_its_helper(self):
        pre = write(self.root / "preamble.tex", "\\usepackage{thing}\n")
        names = pdfmd.package_lua_names(self.md, [pre])
        self.assertEqual(names[0], "thing.lua")
        self.assertIn("extra.lua", names)

    def test_a_package_loaded_in_a_metadata_header_includes_counts_as_loaded(self):
        # the first scan read preamble files only: a pre-lab loads its package from `header-includes`
        meta = write(self.root / "meta.yaml", "header-includes:\n  - \\usepackage{thing}\n")
        self.assertIn("thing.lua", pdfmd.package_lua_names(self.md, [meta]))
        self.assertEqual([package for _, package, _ in pdfmd.office_packages(self.md, [meta], None)], ["thing"])

    def test_a_filter_of_the_loaded_package_is_applied_and_an_unrelated_one_is_not(self):
        meta = write(self.root / "meta.yaml", "header-includes:\n  - \\usepackage{thing}\n")
        found = {path.name for path in pdfmd.find_lua_filters(self.md, [meta])}
        self.assertEqual(found, {"thing.lua", "extra.lua"})
        self.assertNotIn("other.lua", found)

    def test_a_package_that_is_not_loaded_brings_nothing(self):
        self.assertEqual(pdfmd.package_lua_names(self.md, []), [])
        self.assertEqual(pdfmd.find_lua_filters(self.md, []), [])

    def test_the_title_page_keys_are_the_packages_own(self):
        meta = write(self.root / "meta.yaml", "header-includes:\n  - \\usepackage{thing}\n")
        self.assertEqual(pdfmd.package_latex_keys(self.md, [meta]), {"performed": "ThingPerformed"})
        self.assertEqual(pdfmd.package_latex_keys(self.md, []), {})
        self.assertIn("\\renewcommand{\\ThingPerformed}{2026-01-02}", pdfmd.document_latex_definitions(self.md, [meta]))

    def test_the_draft_pass_skips_the_defaults_and_what_the_package_adds(self):
        meta = write(self.root / "meta.yaml", "header-includes:\n  - \\usepackage{thing}\n")
        commands, spans = pdfmd.package_draft_skips(self.md, [meta])
        self.assertEqual(commands, [*pdfmd.DRAFT_SKIP_COMMANDS, "circuit"])        # a name with a space is refused
        self.assertEqual(spans, {**pdfmd.DRAFT_SKIP_SPANS, "startdraw": "stopdraw"})
        text = pdfmd.draft_skip_text(commands, spans)
        self.assertIn("\\@ifundefined{circuit}{}{\\let\\circuit\\pdfmd@chemfig}", text)
        self.assertIn("\\long\\def\\pdfmd@span@startdraw#1\\stopdraw{}", text)
        self.assertIn("\\@ifundefined{chemfig}{}{\\let\\chemfig\\pdfmd@chemfig}", text)
        self.assertNotIn("@@", text)

    def test_nothing_in_pdfmd_names_the_first_package(self):
        source = (ROOT / "pdfmd.py").read_text(encoding="utf-8")
        for word in ("DOCUMENT_LATEX_KEYS", '"nulabreport.lua"', '"nulabreport-office.lua"', "LEGACY_CACHE_NAMES"):
            self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
