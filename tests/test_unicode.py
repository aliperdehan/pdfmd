"""Script-aware font fallback (pdfmd_unicode): what the main font lacks, and the LaTeX it becomes.

No real fonts are needed: the tests write tiny sfnt files that carry just a name and a character
table, and name them after the families the registry looks for.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
import pdfmd_unicode as pu  # noqa: E402


def make_font(path: Path, family: str, ranges, style: str = "Regular", wide=()) -> Path:
    """A font file with nothing in it but a name and a `cmap` over the given (first, last) ranges."""
    segments = list(ranges) + [(0xFFFF, 0xFFFF)]
    count = len(segments)
    ends = b"".join(struct.pack(">H", last) for _first, last in segments)
    starts = b"".join(struct.pack(">H", first) for first, _last in segments)
    deltas = b"".join(struct.pack(">H", (1 - first) & 0xFFFF) if first != 0xFFFF else struct.pack(">H", 1)
                      for first, _last in segments)
    offsets = struct.pack(">H", 0) * count
    body = ends + b"\x00\x00" + starts + deltas + offsets
    format4 = struct.pack(">HHHHHHH", 4, 16 + len(body), 0, count * 2, 0, 0, 0) + body
    subtables = [(3, 1, format4)]
    if wide:
        groups = b"".join(struct.pack(">III", first, last, 1) for first, last in wide)
        format12 = struct.pack(">HHIII", 12, 0, 16 + len(groups), 0, len(wide)) + groups
        subtables.append((3, 10, format12))
    head = struct.pack(">HH", 0, len(subtables))
    position = 4 + 8 * len(subtables)
    directory, data = b"", b""
    for platform, encoding, table in subtables:
        directory += struct.pack(">HHI", platform, encoding, position + len(data))
        data += table
    cmap = head + directory + data

    def record(name_id: int, text: str) -> tuple[bytes, bytes]:
        raw = text.encode("utf-16-be")
        return struct.pack(">6H", 3, 1, 0x409, name_id, len(raw), 0), raw

    entries = [record(1, family), record(2, style)]
    strings, offset, rows = b"", 0, b""
    for row, raw in entries:
        rows += row[:10] + struct.pack(">H", offset)
        strings += raw
        offset += len(raw)
    name = struct.pack(">HHH", 0, len(entries), 6 + 12 * len(entries)) + rows + strings
    tables = {b"cmap": cmap, b"name": name}
    header = struct.pack(">4sHHHH", b"\x00\x01\x00\x00", len(tables), 0, 0, 0)
    position = 12 + 16 * len(tables)
    blob = b""
    for tag, table in tables.items():
        header += struct.pack(">4sIII", tag, 0, position + len(blob), len(table))
        blob += table + b"\x00" * (-len(table) % 4)
    path.write_bytes(header + blob)
    return path


class ScriptTable(unittest.TestCase):
    def test_scripts(self):
        self.assertEqual(pu.script_of(ord("a")), "Latn")
        self.assertEqual(pu.script_of(ord("қ")), "Cyrl")
        self.assertEqual(pu.script_of(ord("ا")), "Arab")
        self.assertEqual(pu.script_of(ord("命")), "Hani")
        self.assertEqual(pu.script_of(ord("ῖ")), "Grek")
        self.assertEqual(pu.script_of(ord("։")), "Zyyy" if pu.script_of(ord("։")) == "Zyyy" else "Armn")
        self.assertEqual(pu.script_of(ord("1")), "Zyyy")
        self.assertEqual(pu.script_of(0x378), "Zzzz")  # unassigned

    def test_han_language(self):
        self.assertEqual(pu.han_language("命運", None), "sc")
        self.assertEqual(pu.han_language("命運", "zh-TW"), "tc")
        self.assertEqual(pu.han_language("命運", "ja"), "ja")
        self.assertEqual(pu.han_language("運命の", None), "ja")  # kana in the text
        self.assertEqual(pu.han_language("운명 命", "kk"), "ko")  # hangul in the text

    def test_generated_table_is_current(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_unicode_scripts.py"), "--check"],
                                capture_output=True, text=True)
        if "fontTools is needed" in result.stdout + result.stderr:
            self.skipTest("fontTools not installed")
        self.assertEqual(result.returncode, 0, result.stdout)


class FontFiles(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)

    def test_name_and_coverage_are_read(self):
        path = make_font(self.root / "a.ttf", "Test Serif", [(0x41, 0x5A), (0x600, 0x6FF)], wide=[(0x1F600, 0x1F64F)])
        [face] = pu.fonts.file_faces(path)
        self.assertEqual((face.family, face.style), ("Test Serif", "Regular"))
        covered = pu.coverage(str(path))
        self.assertIn(0x41, covered)
        self.assertIn(0x627, covered)
        self.assertIn(0x1F600, covered)
        self.assertNotIn(0x61, covered)

    def test_unreadable_files_cover_nothing(self):
        junk = self.root / "junk.ttf"
        junk.write_bytes(b"not a font")
        self.assertEqual(pu.fonts.file_faces(junk), [])
        self.assertEqual(pu.coverage(str(junk)), frozenset())
        self.assertEqual(pu.coverage(str(self.root / "missing.ttf")), frozenset())


class Planning(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        latin = [(0x20, 0x7E), (0xA0, 0x24F)]
        make_font(self.root / "main.ttf", "Main Test", latin + [(0x400, 0x4FF)])
        make_font(self.root / "amiri.ttf", "Amiri", [(0x600, 0x6FF), (0x20, 0x7E)])
        make_font(self.root / "dejavu.ttf", "DejaVu Sans", [(0x2000, 0x2BFF), (0x20, 0x4FF)])
        self.index = pu.FontIndex(self.root, use_system=False)

    def plan(self, text, main="Main Test", lang=None):
        return pu.plan_text(text, main, self.index, lang)

    def test_nothing_missing_is_an_empty_plan(self):
        plan = self.plan("plain text and қазақ")
        self.assertFalse(plan)
        self.assertEqual(plan.uncovered, {})

    def test_unknown_main_font_cannot_be_judged(self):
        self.assertIsNone(self.plan("text", main="No Such Font"))

    def test_arabic_gets_its_own_font_and_direction(self):
        plan = self.plan("word القدر word")
        self.assertEqual([choice.family for choice in plan.choices.values()], ["Amiri"])
        self.assertTrue(plan.choices["A"].rtl)
        header = plan.latex_header()
        self.assertIn("pdfmdfA", header)
        self.assertIn("Script=Arabic", header)
        self.assertIn("Path={", header)  # a font from pdfmd's own folder is loaded by file
        self.assertIn("\\pdfmdrunrtl", header)

    def test_symbols_and_arabic_punctuation_follow_their_neighbours(self):
        plan = self.plan("القدر، والقضاء ✶")
        comma = ord("،")
        self.assertIn(comma, plan.common)
        self.assertEqual(plan.candidates[comma][0], plan.candidates[ord("ا")][0])

    def test_uncovered_characters_are_reported_not_dropped(self):
        plan = self.plan("a 命 b")
        self.assertEqual(list(plan.uncovered), [ord("命")])
        self.assertIn("U+547D", plan.describe_uncovered())
        self.assertFalse(plan)

    def test_main_font_follows_the_dominant_script(self):
        make_font(self.root / "weak.ttf", "STIX Two Text", [(0x20, 0x7E), (0x410, 0x44F)])
        make_font(self.root / "noto.ttf", "Noto Serif", [(0x20, 0x7E), (0x400, 0x4FF)])
        index = pu.FontIndex(self.root, use_system=False)
        text = "Қазақ тілі " * 20
        self.assertEqual(pu.choose_main_font(text, "STIX Two Text", index), "Noto Serif")
        self.assertEqual(pu.choose_main_font("plain english text", "STIX Two Text", index), "STIX Two Text")
        self.assertEqual(pu.choose_main_font(text, "Noto Serif", index), "Noto Serif")

    def test_lua_filter_wraps_runs(self):
        if not shutil.which("pandoc"):
            self.skipTest("Pandoc not installed")
        plan = self.plan("word القدر والقضاء word")
        filter_file = self.root / "fonts.lua"
        filter_file.write_text(plan.lua_filter(), encoding="utf-8")
        result = subprocess.run(["pandoc", "-f", "markdown", "-t", "latex", "--lua-filter", str(filter_file)],
                                input="Say *القدر والقضاء* now, (plain) و.\n", capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        # one run across the space, inside the emphasis; the plain parts are untouched
        self.assertIn("\\emph{\\pdfmdrunrtl{A}{القدر والقضاء}}", result.stdout)
        self.assertIn("(plain)", result.stdout)
        self.assertEqual(result.stdout.count("\\pdfmdrunrtl"), 2)
        other = subprocess.run(["pandoc", "-f", "markdown", "-t", "html", "--lua-filter", str(filter_file)],
                               input="القدر\n", capture_output=True, text=True, encoding="utf-8")
        self.assertNotIn("pdfmdrun", other.stdout)  # only LaTeX is rewritten


class Integration(unittest.TestCase):
    def test_a_document_with_its_own_script_setup_is_left_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            md = Path(directory) / "doc.md"
            md.write_text("---\nheader-includes: |\n  \\usepackage{ucharclasses}\n---\nقدر\n", encoding="utf-8")
            plain = Path(directory) / "plain.md"
            plain.write_text("قدر\n", encoding="utf-8")
            self.assertTrue(pdfmd.own_script_setup([md], [], [], []))
            self.assertFalse(pdfmd.own_script_setup([plain], [], [], []))
            self.assertTrue(pdfmd.own_script_setup([plain], [], ["CJKmainfont=Songti SC"], []))

    def test_code_is_not_scanned(self):
        text = pdfmd.strip_code_text("a `命` b\n\n```\n運\n```\n\nend\n")
        self.assertNotIn("命", text)
        self.assertNotIn("運", text)
        self.assertIn("end", text)

    def test_no_auto_unicode_is_a_known_kind(self):
        self.assertIn("unicode", pdfmd.NO_AUTO_KINDS)
        self.assertTrue(pdfmd.auto_disabled(["unicode"], "unicode"))


if __name__ == "__main__":
    unittest.main()
