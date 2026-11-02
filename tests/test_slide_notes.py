"""`slide-notes` (v3.32.2): the `::: notes` blocks of a Beamer deck are dropped from the PDF unless `pdfmd-options` asks for
them (`show`: a notes page after each slide, `only`: the notes pages alone). The deck's own `classoption` must survive."""

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
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

DECK = """---
title: Deck
classoption:
  - aspectratio=169
{options}---

# One

Visible ALPHA

::: notes
SPEAKERNOTE_ONE
:::

# Two

Visible BETA

::: notes
SPEAKERNOTE_TWO
:::
"""


class Mode(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-notes-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def mode(self, options: str) -> str:
        document = self.directory / "d.md"
        document.write_text(DECK.format(options=options), encoding="utf-8")
        return pdfmd.slide_notes_mode(document, [])

    def test_off_unless_asked(self):
        self.assertEqual(self.mode(""), "off")
        self.assertEqual(self.mode("pdfmd-options:\n  slide-notes: off\n"), "off")
        self.assertEqual(self.mode("pdfmd-options:\n  slide-notes: false\n"), "off")

    def test_show_and_only(self):
        self.assertEqual(self.mode("pdfmd-options:\n  slide-notes: show\n"), "show")
        self.assertEqual(self.mode("pdfmd-options:\n  slide-notes: Only\n"), "only")
        self.assertEqual(self.mode("pdfmd-options:\n  slide-notes: true\n"), "show")

    def test_a_bad_word_stops_the_build_and_names_the_choices(self):
        with self.assertRaises(SystemExit) as raised:
            self.mode("pdfmd-options:\n  slide-notes: sideways\n")
        self.assertIn("off, show, only", str(raised.exception))

    def test_a_header_only_for_a_deck(self):
        document = self.directory / "d.md"
        document.write_text(DECK.format(options="pdfmd-options:\n  slide-notes: only\n"), encoding="utf-8")
        self.assertEqual(pdfmd.slide_notes_args(document, [], beamer=False), [])
        arguments = pdfmd.slide_notes_args(document, [], beamer=True)
        self.assertEqual(arguments[0], "--include-in-header")
        self.assertIn("\\setbeameroption{show only notes}", Path(arguments[1]).read_text(encoding="utf-8"))
        document.write_text(DECK.format(options=""), encoding="utf-8")
        self.assertEqual(pdfmd.slide_notes_args(document, [], beamer=True), [])


def has(program: str) -> bool:
    return shutil.which(program) is not None


@unittest.skipUnless(has("pandoc"), "needs pandoc")
class Source(unittest.TestCase):
    """The header reaches the .tex of a deck (`--stop-at tex`, no LaTeX needed), from the front matter or a metadata file, and the
    deck's own classoption and header-includes stay."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-notes-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def tex(self, text: str, *extra: str) -> str:
        (self.directory / "deck.md").write_text(text, encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"], "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "deck.md", "-p", "--stop-at", "tex", *extra],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.directory, env=environment)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.directory / "deck.tex").read_text(encoding="utf-8")

    def test_the_header_is_in_the_tex_and_the_decks_own_settings_stay(self):
        text = DECK.format(options="header-includes:\n  - '\\newcommand{\\mymark}{MYMARKOK}'\npdfmd-options:\n  slide-notes: show\n")
        tex = self.tex(text)
        self.assertIn("\\setbeameroption{show notes}", tex)
        self.assertIn("aspectratio=169", tex)
        self.assertIn("MYMARKOK", tex)                              # --include-in-header did not replace header-includes

    def test_off_leaves_the_tex_alone(self):
        self.assertNotIn("setbeameroption", self.tex(DECK.format(options="")))

    def test_the_setting_may_come_from_a_metadata_file(self):
        (self.directory / "notes.yaml").write_text("pdfmd-options:\n  slide-notes: only\n", encoding="utf-8")
        self.assertIn("\\setbeameroption{show only notes}", self.tex(DECK.format(options=""), "-y", "notes.yaml"))


@unittest.skipUnless(has("pandoc") and has("lualatex") and has("pdfinfo") and has("pdftotext"),
                     "needs pandoc, lualatex and poppler to build and read a deck")
class Deck(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-notes-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, options: str) -> tuple[int, str, str]:
        (self.directory / "deck.md").write_text(DECK.format(options=options), encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"], "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "deck.md", "-p", "-e", "lualatex"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory, env=environment)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        pdf = self.directory / "deck.pdf"
        info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
        pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
        size = re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info)
        text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, encoding="utf-8").stdout
        return pages, f"{float(size.group(1)):.0f}x{float(size.group(2)):.0f}", text

    def test_notes_are_dropped_by_default(self):
        pages, size, text = self.build("")
        self.assertEqual(pages, 3)
        self.assertNotIn("SPEAKERNOTE", text)
        self.assertEqual(size, "454x255")                          # aspectratio=169

    def test_show_adds_a_notes_page_after_each_slide_and_keeps_the_aspect_ratio(self):
        pages, size, text = self.build("pdfmd-options:\n  slide-notes: show\n")
        self.assertEqual(pages, 5)
        self.assertIn("SPEAKERNOTE_ONE", text)
        self.assertIn("SPEAKERNOTE_TWO", text)
        self.assertEqual(size, "454x255")

    def test_only_gives_the_notes_pages_alone(self):
        pages, size, text = self.build("pdfmd-options:\n  slide-notes: only\n")
        self.assertEqual(pages, 2)
        self.assertIn("SPEAKERNOTE_ONE", text)
        self.assertEqual(size, "454x255")


if __name__ == "__main__":
    unittest.main()
