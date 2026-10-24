"""The documents say what the program does: the version they name is PDFMD_VERSION, a count in a heading is the count of what is
under it, and the default the agent guide states is the default the code has."""

from __future__ import annotations

import os
import re
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
import pdfmd_docs  # noqa: E402

VERSION_RE = re.compile(r"(?<![\w.])v?(\d+\.\d+\.\d+)(?![\w.])")
NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15}


class Version(unittest.TestCase):
    def test_the_docs_package_derives_its_version(self):
        self.assertEqual(pdfmd_docs.version(), pdfmd.PDFMD_VERSION)

    def test_a_version_the_docs_name_as_their_own_is_the_current_one(self):
        # these files state no number of their own; if one is added, it is this version or the test says so
        for path in (ROOT / "pdfmd_docs" / "__init__.py", ROOT / "docs" / "agents.md"):
            for found in VERSION_RE.findall(path.read_text(encoding="utf-8")):
                with self.subTest(path=path.name, found=found):
                    self.assertEqual(found, pdfmd.PDFMD_VERSION)

    def test_the_changelog_names_the_current_version_first_and_gives_its_location(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"(?m)^## v(\d+\.\d+\.\d+)\b", text)[0], pdfmd.PDFMD_VERSION)
        header = text.split("\n---\n", 1)[0]
        self.assertIn("PDFMD_VERSION", header)
        source = (ROOT / "pdfmd.py").read_text(encoding="utf-8")
        self.assertRegex(source, r'(?m)^PDFMD_VERSION = "\d+\.\d+\.\d+"$')            # the line the header points at

    def test_the_changelog_header_says_what_the_numbering_rule_says(self):
        header = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("\n---\n", 1)[0]
        self.assertNotIn("fixes a bug without changing what any flag does", header)    # CLAUDE.md: a patch may add anything
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("every commit after it in that line", claude)
        self.assertIn("(`3.N.x`)", header)


class AgentGuide(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "docs" / "agents.md").read_text(encoding="utf-8")

    def test_a_number_in_a_heading_is_the_count_of_the_commands_under_it(self):
        heading = re.search(r"(?m)^## The (\w+ )?commands that matter\s*$", self.text)
        self.assertIsNotNone(heading, "the section on the commands that matter")
        block = re.search(r"```sh\n(.*?)```", self.text[heading.end():], re.S).group(1)
        commands = [line for line in block.splitlines() if line.startswith("pdfmd ")]
        self.assertGreater(len(commands), 5)
        word = (heading.group(1) or "").strip().lower()
        if word:
            self.assertEqual(NUMBER_WORDS.get(word, int(word) if word.isdigit() else None), len(commands))

    def test_attaching_the_source_is_off_unless_asked_and_the_guide_says_so(self):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "d.md"
            document.write_text("---\ntitle: T\n---\n\nText\n", encoding="utf-8")
            self.assertFalse(pdfmd.resolve_attach(document, []))
        row = next(line for line in self.text.splitlines() if "restorable PDF" in line)
        self.assertIn("--attach-source", row)
        self.assertNotRegex(row, r"the default")
        self.assertIn("off unless asked", row)


if __name__ == "__main__":
    unittest.main()
