"""v3.33.68: a kit's own `markup-off:`. The key is read by pdfmd_kits.kitfile and checked by pdfmd_kits.markup; the builds go through
pdfmd itself with a fixture kit, so what is tested is what the author gets: the kinds taken out of the list for a document that
uses the kit, a `markup:` of the document, a folder, the command line kept as it is, the config's taken out of, a word that is not
a kind warned about once, naming the kit file, and `--kits NAME` showing the key."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from pdfmd_kits import load_kit  # noqa: E402

PANDOC = shutil.which("pandoc")
KIT = "kit-format: 1\nname: house\ndefaults: metadata.yaml\n"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Reading(unittest.TestCase):
    def load(self, extra: str):
        with tempfile.TemporaryDirectory() as folder:
            write(Path(folder) / "metadata.yaml", "lang: en\n")
            return load_kit(write(Path(folder) / ".kit", KIT + extra))

    def test_a_word_a_list_or_a_string_with_commas(self):
        self.assertEqual(self.load("markup-off: landscape\n").markup_off, ("landscape",))
        self.assertEqual(self.load("markup-off: [Landscape, toc, landscape]\n").markup_off, ("landscape", "toc"))
        self.assertEqual(self.load("markup-off: 'landscape, toc'\n").markup_off, ("landscape", "toc"))
        self.assertEqual(self.load("").markup_off, ())
        self.assertEqual(self.load("markup-off: false\n").markup_off, ())

    def test_the_key_is_known(self):
        self.assertEqual(self.load("markup-off: [landscape]\n").warnings, ())


@unittest.skipUnless(PANDOC, "Pandoc is needed")
class Builds(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.kits = self.root / "course" / "kits"
        self.config = write(self.root / "cfg" / "config.yaml", f"kits: [{self.kits}]\n")
        self.folder = self.root / "course" / "LR1"
        self.folder.mkdir(parents=True)

    def kit(self, extra: str = "", metadata: str = "lang: en\n") -> None:
        write(self.kits / "house" / ".kit", KIT + extra)
        write(self.kits / "house" / "metadata.yaml", metadata)

    def run_pdfmd(self, *args) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PDFMD_CONFIG": str(self.config), "XDG_CACHE_HOME": str(self.root / "cache"),
                       "PDFMD_NO_PROMPT": "1", "PDFMD_BUILD_LOG": "off"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], capture_output=True, text=True, cwd=self.folder,
                              env=environment, stdin=subprocess.DEVNULL)

    def kinds(self, options: str = "", *args) -> tuple[list[str], subprocess.CompletedProcess]:
        """The kinds of markup the build gives markup.lua (none when it gives no list)."""
        write(self.folder / "report.md", f"---\ntitle: T\n{options}\n---\nText.\n")
        done = self.run_pdfmd("report.md", "--to", "latex", "-o", "out.tex", "--no-backup", "--no-stamp", "--verbose", *args)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        found = re.search(r"pdfmd-markup=([a-z,]+)", done.stdout + done.stderr)
        return (found.group(1).split(",") if found else []), done

    def test_the_kits_words_are_taken_out(self):
        self.kit("markup-off: [landscape]\n")
        kinds, done = self.kinds("pdfmd-options: {kit: house}")
        self.assertNotIn("landscape", kinds)
        self.assertIn("callouts", kinds)
        self.assertIn("switches off markup landscape", done.stdout + done.stderr)
        tex = (self.folder / "out.tex").read_text(encoding="utf-8")
        self.assertNotIn("pdflscape", tex)

    def test_a_kit_without_the_key_changes_nothing(self):
        self.kit()
        kinds, _ = self.kinds("pdfmd-options: {kit: house}")
        self.assertIn("landscape", kinds)

    def test_the_command_line_kit_works_the_same(self):
        self.kit("markup-off: landscape\n")
        kinds, _ = self.kinds("", "--kit", "house")
        self.assertNotIn("landscape", kinds)

    def test_the_documents_own_markup_wins(self):
        self.kit("markup-off: [landscape]\n")
        kinds, _ = self.kinds("pdfmd-options: {kit: house, markup: [landscape, toc]}")
        self.assertEqual(kinds, ["toc", "landscape"])

    def test_a_folders_markup_wins(self):
        self.kit("markup-off: [landscape]\n")
        write(self.folder / ".pdfmd" / "config.yaml", "options:\n  markup: [landscape]\n")
        kinds, _ = self.kinds("pdfmd-options: {kit: house}")
        self.assertEqual(kinds, ["landscape"])

    def test_the_command_line_wins(self):
        self.kit("markup-off: [landscape]\n")
        kinds, _ = self.kinds("pdfmd-options: {kit: house}", "--markup", "landscape")
        self.assertEqual(kinds, ["landscape"])
        kinds, _ = self.kinds("pdfmd-options: {kit: house}", "--no-markup")
        self.assertEqual(kinds, [])

    def test_the_configs_and_the_kits_own_markup_lose(self):
        self.kit("markup-off: [landscape]\n")
        write(self.config, f"kits: [{self.kits}]\noptions:\n  markup: [landscape, toc]\n")
        kinds, _ = self.kinds("pdfmd-options: {kit: house}")
        self.assertEqual(kinds, ["toc"])
        self.kit("markup-off: [landscape]\n", "pdfmd-options:\n  markup: [center, landscape]\n")
        kinds, _ = self.kinds("pdfmd-options: {kit: house}")
        self.assertEqual(kinds, ["center"])

    def test_a_word_that_is_not_a_kind_warns_once_naming_the_kit(self):
        self.kit("markup-off: [landscape, comments]\n")
        kinds, done = self.kinds("pdfmd-options: {kit: house}")
        self.assertNotIn("landscape", kinds)
        self.assertEqual(done.stderr.count("`markup-off: comments` is not a kind of universal markup"), 1, done.stderr)
        self.assertIn(".kit", done.stderr.split("`markup-off: comments`")[0].splitlines()[-1])

    def test_kits_name_shows_the_key(self):
        self.kit("markup-off: [landscape, toc]\n")
        done = self.run_pdfmd("--kits", "house")
        self.assertIn("markup-off landscape, toc", done.stdout)


if __name__ == "__main__":
    unittest.main()
