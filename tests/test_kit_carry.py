"""v3.31.35: kits, C4 (entry 3du, points 11 and 17): an attached source holds what the kit wrote and the kit's parts, so a restored
report rebuilds with no kit on the machine. A fixture kit; the PDF is a blank page, the source is read back."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

try:
    import pypdf
except ImportError:                                      # pragma: no cover
    pypdf = None

KIT = """\
kit-format: 1
name: lab
package: labstyle
modes:
  qca: {aliases: [220], options: [qca], latex: ['\\LabScheme{word}']}
  org: {options: [orgchem]}
latex: ['\\input{chemicals}']
carry: [labstyle.sty, chemicals.tex, assets/, missing.tex]
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@unittest.skipIf(pypdf is None, "needs pypdf")
class Carry(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        kit = self.root / "kits" / "lab"
        write(kit / ".kit", KIT)
        write(kit / "labstyle.sty", "\\ProvidesPackage{labstyle}[2026/10/31 v2.5.1 test]\n")
        write(kit / "chemicals.tex", "\\newcommand{\\chem}{1}\n")
        write(kit / "assets" / "logo.pdf", "pdf")
        write(kit / "assets" / "deep" / "badge.png", "png")
        write(kit / "assets" / ".hidden", "no")
        write(kit / "notes.txt", "not carried")
        config = write(self.root / "cfg.yaml", f"kits: [{self.root / 'kits'}]\n")
        self.environment = {"PDFMD_CONFIG": str(config), "XDG_CACHE_HOME": str(self.root / "cache")}
        saved = {key: os.environ.get(key) for key in self.environment}
        os.environ.update(self.environment)
        self.addCleanup(lambda: [os.environ.pop(key) if value is None else os.environ.__setitem__(key, value)
                                 for key, value in saved.items()])
        self.reset()
        self.addCleanup(self.reset)
        self.folder = self.root / "LR1"
        self.pdf = self.root / "LR1.pdf"
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with self.pdf.open("wb") as handle:
            writer.write(handle)

    def reset(self):
        pdfmd.load_config.cache_clear()
        pdfmd.ACTIVE_KITS.clear()
        pdfmd.set_kit_cli(None, None)

    def report(self, options="pdfmd-options: {kit: lab:qca}", preamble=None, files=()) -> Path:
        for name, text in files:
            write(self.folder / name, text)
        md = write(self.folder / "report.md", f"---\ntitle: T\n{options}\n---\nText.\n")
        return md

    def attach(self, md: Path, preamble=None):
        found = [write(md.parent / "preamble.tex", preamble)] if preamble is not None else []
        self.reset()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            attachments, merged, manifest = pdfmd.source_attachments(md, self.pdf, [], [], found, None)
        self.notes = err.getvalue()
        return attachments, merged, manifest

    def test_the_kits_parts_are_stored_and_the_kit_is_recorded(self):
        _, _, manifest = self.attach(self.report())
        stored = {item["path"]: item for item in manifest["extras"]}
        self.assertEqual(sorted(stored), ["badge.png", "chemicals.tex", "labstyle.sty", "logo.pdf"])     # a folder lands flat
        self.assertTrue(all(item["from"] == "kit" for item in stored.values()))
        self.assertEqual(manifest["kits"], [{"name": "lab", "version": "2.5.1", "mode": "qca", "package": "labstyle",
                                             "carried": ["badge.png", "chemicals.tex", "labstyle.sty", "logo.pdf"]}])
        self.assertIn("`carry: missing.tex` names nothing", self.notes)
        self.assertEqual(manifest["format"], pdfmd.ATTACH_FORMAT_PLAIN)

    def test_a_name_the_documents_folder_holds_is_left_to_the_folder(self):
        _, _, manifest = self.attach(self.report(files=[("chemicals.tex", "\\newcommand{\\chem}{mine}\n")]))
        self.assertNotIn("chemicals.tex", [item["path"] for item in manifest.get("extras", []) if item.get("from") == "kit"])
        self.assertNotIn("chemicals.tex", manifest["kits"][0]["carried"])

    def test_the_source_holds_the_kits_preamble_first_and_the_users_settled_in_it(self):
        _, merged, _ = self.attach(self.report(), "\\usepackage[qca,draft]{labstyle}\n\\input{chemicals}\n\\labsetup{mine=1}\n")
        self.assertIn("\\usepackage[qca,draft]{labstyle}", merged)           # the kit's line, with the user's extra option merged in
        self.assertEqual([line for line in merged.splitlines() if line.strip() == "\\usepackage[qca,draft]{labstyle}"].__len__(), 1)
        self.assertEqual([line for line in merged.splitlines() if line.strip() == "\\input{chemicals}"].__len__(), 1)
        order = [merged.index(text) for text in ("\\usepackage[qca,draft]{labstyle}", "\\LabScheme{word}", "\\labsetup{mine=1}")]
        self.assertEqual(order, sorted(order))

    def test_the_source_says_kit_none_so_a_rebuild_does_not_choose_the_kit_again(self):
        _, merged, _ = self.attach(self.report())
        self.assertEqual(pdfmd.front_matter_dict(merged)["pdfmd-options"]["kit"], "none")
        _, merged, _ = self.attach(self.report(options="pdfmd-options: {kit: lab:qca, bundle-max-mb: 20}"))
        self.assertEqual(pdfmd.front_matter_dict(merged)["pdfmd-options"]["bundle-max-mb"], 20)         # the rest stays
        _, merged, _ = self.attach(self.report(options=""))
        self.assertNotIn("kit", (pdfmd.front_matter_dict(merged).get("pdfmd-options") or {}))

    def test_nothing_changes_without_a_kit(self):
        _, merged, manifest = self.attach(self.report(options=""), "\\usepackage{xcolor}\n")
        self.assertNotIn("kits", manifest)
        self.assertNotIn("labstyle", merged)
        self.assertIn("\\usepackage{xcolor}", merged)
        self.assertEqual([item for item in manifest.get("extras", []) if item.get("from") == "kit"], [])

    def test_a_restore_writes_the_parts_back_and_the_report_says_which_kit(self):
        attachments, _, manifest = self.attach(self.report())
        out = self.root / "back"
        with contextlib.redirect_stdout(io.StringIO()):
            status = pdfmd.restore_attachments_in_place(self.pdf, attachments, out, False)
        self.assertEqual(status, 0)
        for name in ("labstyle.sty", "chemicals.tex", "logo.pdf", "badge.png"):
            self.assertTrue((out / name).is_file(), name)
        self.assertFalse((out / "notes.txt").exists())
        lines = pdfmd.requirement_lines(json.loads(attachments[pdfmd.ATTACH_MANIFEST]))
        self.assertTrue(any(line.startswith("KIT       lab 2.5.1 (mode qca): its 4 parts are stored") for line in lines), lines)

    def test_a_kit_with_too_much_to_carry_is_left_out_with_a_warning(self):
        write(self.root / "kits" / "lab" / "assets" / "big.bin", "x" * 3 * 1024 * 1024)
        write(self.folder / "report.md", "---\ntitle: T\npdfmd-options: {kit: lab:qca, bundle-max-mb: 1}\n---\nText.\n")
        _, _, manifest = self.attach(self.folder / "report.md")
        self.assertEqual(manifest["kits"][0]["carried"], [])
        self.assertIn("over the 1 MB limit", self.notes)


if __name__ == "__main__":
    unittest.main()
