"""v3.32.8: a kit's own `no-auto:` (entry 3et UPDATE 2). The key is read and checked by pdfmd_kits.kitfile; the builds go through
pdfmd itself with a fixture kit, so what is tested is what the author gets: no automatic margin for a document that uses the kit,
the document able to turn it back on, a kind a kit cannot name warned about, and a kit without the key unchanged."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfmd_kits import load_kit  # noqa: E402
from pdfmd_kits.kitfile import KIT_NO_AUTO_KINDS  # noqa: E402

PANDOC = shutil.which("pandoc")
KIT = "kit-format: 1\nname: page\ndefaults: metadata.yaml\n"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Reading(unittest.TestCase):
    def load(self, extra: str):
        with tempfile.TemporaryDirectory() as folder:
            write(Path(folder) / "metadata.yaml", "lang: en\n")
            return load_kit(write(Path(folder) / ".kit", KIT + extra))

    def test_a_word_or_a_list_of_kinds(self):
        self.assertEqual(self.load("no-auto: margin\n").no_auto, ("margin",))
        self.assertEqual(self.load("no-auto: [margin, font, margin]\n").no_auto, ("margin", "font"))
        self.assertEqual(self.load("").no_auto, ())
        self.assertEqual(self.load("no-auto: false\n").no_auto, ())

    def test_no_warning_for_the_key_and_the_kinds_it_may_name(self):
        kit = self.load(f"no-auto: [{', '.join(KIT_NO_AUTO_KINDS)}]\n")
        self.assertEqual(kit.no_auto, KIT_NO_AUTO_KINDS)
        self.assertEqual(kit.warnings, ())

    def test_a_kind_a_kit_cannot_switch_off_is_warned_about_and_ignored(self):
        kit = self.load("no-auto: [margin, metadata, lua]\n")
        self.assertEqual(kit.no_auto, ("margin",))
        self.assertEqual(len(kit.warnings), 2)
        self.assertIn("`no-auto: metadata`", kit.warnings[0])
        self.assertIn("margin, mainfont", kit.warnings[0])

    def test_everything_is_not_a_choice(self):
        for value in ("true", "all", "yes"):
            kit = self.load(f"no-auto: {value}\n")
            self.assertEqual(kit.no_auto, (), value)
            self.assertIn("names the kinds", kit.warnings[0])


@unittest.skipUnless(PANDOC, "Pandoc is needed")
class Builds(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.kits = self.root / "course" / "kits"
        self.config = write(self.root / "cfg" / "config.yaml", f"kits: [{self.kits}]\n")
        self.folder = self.root / "course" / "LR1"

    def kit(self, name: str, extra: str = "") -> None:
        folder = self.kits / name
        write(folder / ".kit", f"kit-format: 1\nname: {name}\ndefaults: metadata.yaml\n{extra}")
        write(folder / "metadata.yaml", "lang: en\n")

    def build(self, options: str = "", *args):
        write(self.folder / "report.md", f"---\ntitle: T\n{options}\n---\nText.\n")
        environment = {**os.environ, "PDFMD_CONFIG": str(self.config), "XDG_CACHE_HOME": str(self.root / "cache"),
                       "PDFMD_NO_PROMPT": "1", "PDFMD_BUILD_LOG": "off"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "report.md", "--to", "latex", "-o", "out.tex", "--no-backup",
                               "--no-stamp", "--verbose", *args], capture_output=True, text=True, cwd=self.folder, env=environment)
        out = self.folder / "out.tex"
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        return done, out.read_text(encoding="utf-8")

    def test_a_kit_without_the_key_gets_pdfmds_margin(self):
        self.kit("plain")
        done, tex = self.build("pdfmd-options: {kit: plain}")
        self.assertIn("geometry", tex)
        self.assertNotIn("switches off", done.stdout)

    def test_a_kit_with_no_auto_margin_gets_none(self):
        self.kit("page", "no-auto: [margin]\n")
        done, tex = self.build("pdfmd-options: {kit: page}")
        self.assertNotIn("geometry", tex)
        self.assertIn("switches off margin", done.stdout)
        self.assertNotIn("MARGIN", done.stdout)

    def test_the_documents_own_geometry_is_still_used(self):
        self.kit("page", "no-auto: margin\n")
        _, tex = self.build("pdfmd-options: {kit: page}\ngeometry: top=2cm")
        self.assertIn("top=2cm", tex)

    def test_the_document_can_turn_the_default_back_on(self):
        self.kit("page", "no-auto: [margin]\n")
        _, tex = self.build("pdfmd-options: {kit: page, auto: {margin: on}}")
        self.assertIn("geometry", tex)

    def test_the_command_line_kit_works_the_same(self):
        self.kit("page", "no-auto: [margin]\n")
        _, tex = self.build("", "--kit", "page")
        self.assertNotIn("geometry", tex)

    def test_only_the_kit_that_has_the_key_counts_in_a_stack(self):
        self.kit("page", "no-auto: [margin]\n")
        self.kit("plain")
        _, tex = self.build("pdfmd-options: {kit: [plain, page]}")
        self.assertNotIn("geometry", tex)
        _, tex = self.build("pdfmd-options: {kit: [page, none, plain]}")
        self.assertIn("geometry", tex)

    def test_a_kind_it_cannot_name_warns_once_and_changes_nothing(self):
        self.kit("odd", "no-auto: [metadata]\n")
        done, tex = self.build("pdfmd-options: {kit: odd}")
        self.assertEqual(done.stderr.count("is not something a kit can switch off"), 1, done.stderr)
        self.assertIn("geometry", tex)

    def test_a_report_builds_the_same_way(self):
        self.kit("page", "no-auto: [margin]\n")
        write(self.folder / "a.md", "---\ntitle: A\npdfmd-options: {kit: page}\n---\nOne.\n")
        write(self.folder / "b.md", "Two.\n")
        environment = {**os.environ, "PDFMD_CONFIG": str(self.config), "XDG_CACHE_HOME": str(self.root / "cache"),
                       "PDFMD_NO_PROMPT": "1", "PDFMD_BUILD_LOG": "off"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "-r", "--to", "latex", "-o", "out.tex", "--no-backup",
                               "--no-stamp"], capture_output=True, text=True, cwd=self.folder, env=environment)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        tex = (self.folder / "out.tex").read_text(encoding="utf-8")
        self.assertNotIn("geometry", tex)


if __name__ == "__main__":
    unittest.main()
