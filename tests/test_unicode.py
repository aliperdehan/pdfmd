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

# never read or write the real user's config and state while testing
import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

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

    def test_urdu_is_set_in_nastaliq_and_other_arabic_script_text_in_naskh(self):
        from pdfmd_unicode.scripts import chain_for

        self.assertEqual(chain_for(0x627, "Arab", "sc", "ur")[0], "Noto Nastaliq Urdu")
        self.assertEqual(chain_for(0x627, "Arab", "sc", "ur-PK")[0], "Noto Nastaliq Urdu")
        self.assertEqual(chain_for(0x627, "Arab", "sc", "ar")[0], "Amiri")
        self.assertEqual(chain_for(0x627, "Arab", "sc", None)[0], "Amiri")

    def test_han_language(self):
        self.assertEqual(pu.han_language("命運", None), "sc")
        self.assertEqual(pu.han_language("命運", "zh-TW"), "tc")
        self.assertEqual(pu.han_language("命運", "ja"), "ja")
        self.assertEqual(pu.han_language("運命の", None), "ja")  # kana in the text
        self.assertEqual(pu.han_language("운명 命", "kk"), "ko")  # hangul in the text

    def test_the_generated_table_is_well_formed(self):
        # (scripts/gen_unicode_scripts.py --check compares it with fontTools' copy of the data, whose
        # Unicode version differs between releases, so that is a development-time check, not a test)
        from pdfmd_unicode import _scripts

        last = -1
        for first, end, code in _scripts.RANGES:
            self.assertTrue(last < first <= end <= 0x10FFFF)
            self.assertTrue(0 <= code < len(_scripts.CODES))
            last = end


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

    def test_the_regular_face_stands_for_a_family(self):
        make_font(self.root / "a-medium.ttf", "Family", [(0x41, 0x5A)], style="Medium")
        make_font(self.root / "b-regular.ttf", "Family", [(0x41, 0x5A)], style="Regular")
        make_font(self.root / "c-bold.ttf", "Family", [(0x41, 0x5A)], style="Bold")
        index = pu.FontIndex(self.root, use_system=False)
        self.assertEqual(index.regular("Family").style, "Regular")
        self.assertEqual(index.regular("family").path.endswith("b-regular.ttf"), True)
        self.assertEqual(set(index.styles(index.regular("Family"))), {"bold"})
        self.assertIsNone(index.regular("No Such Family"))

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
        for target, expected in (("typst", '#text(font: ("Amiri",))[القدر]'),
                                 ("html", "font-family: &#39;Amiri&#39;")):
            other = subprocess.run(["pandoc", "-f", "markdown", "-t", target, "--lua-filter", str(filter_file)],
                                   input="القدر\n", capture_output=True, text=True, encoding="utf-8")
            self.assertIn(expected, other.stdout, target)
        docx = subprocess.run(["pandoc", "-f", "markdown", "-t", "plain", "--lua-filter", str(filter_file)],
                              input="القدر\n", capture_output=True, text=True, encoding="utf-8")
        self.assertNotIn("Amiri", docx.stdout)  # formats with their own font fallback are left alone


class Emoji(unittest.TestCase):
    def test_emoji_are_not_script_fallback_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_font(root / "main.ttf", "Main Test", [(0x20, 0x7E)] + [(0x2764, 0x2764)])
            index = pu.FontIndex(root, use_system=False)
            plan = pu.plan_text("rocket \U0001F680 flag \U0001F1F0\U0001F1FF heart \u2764\uFE0F", "Main Test", index)
            self.assertIn(0x1F680, plan.emoji)
            self.assertIn(0x1F1F0, plan.emoji)
            self.assertNotIn(0x2764, plan.emoji)  # the main font has it
            self.assertEqual(plan.uncovered, {})
            self.assertFalse(plan)

    def test_text_symbols_without_a_variation_selector_are_not_emoji(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_font(root / "main.ttf", "Main Test", [(0x20, 0x7E)])
            plan = pu.plan_text("a \u2764 b \u2764\uFE0F c", "Main Test", pu.FontIndex(root, use_system=False))
            self.assertIn(0x2764, plan.emoji)  # one of them asked for the picture


class Installer(unittest.TestCase):
    def setUp(self):
        from pdfmd_unicode import install

        self.install = install
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.blob = b"font bytes"
        self.archive = self._zip({"pkg/ttf/Alpha-Regular.ttf": b"zip font bytes"})
        import hashlib

        sha1 = hashlib.sha1(b"blob %d\0" % len(self.blob) + self.blob).hexdigest()
        self.packages = {
            "alpha": {"title": "Alpha", "scripts": ("Latn",), "license": "OFL-1.1", "homepage": "https://x", "size": 10,
                      "files": ({"url": "https://example.invalid/A.ttf", "name": "A.ttf", "size": 10, "git_sha1": sha1},)},
            "beta": {"title": "Beta", "scripts": ("Arab",), "license": "OFL-1.1", "homepage": "https://x", "size": 14,
                     "files": ({"zip": "https://example.invalid/b.zip", "zip_sha256": hashlib.sha256(self.archive).hexdigest(),
                                "member": "pkg/ttf/Alpha-Regular.ttf", "name": "B.ttf", "size": 14},)},
        }
        self._real = install.PACKAGES
        install.PACKAGES = self.packages
        self.addCleanup(lambda: setattr(install, "PACKAGES", self._real))
        self.served = {"https://example.invalid/A.ttf": self.blob, "https://example.invalid/b.zip": self.archive}

    @staticmethod
    def _zip(members: dict) -> bytes:
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            for name, data in members.items():
                bundle.writestr(name, data)
        return buffer.getvalue()

    def opener(self, request, timeout=None):
        import io

        return io.BytesIO(self.served[request.full_url])

    def test_names_groups_and_aliases(self):
        self.assertEqual(self._real is not None and self.install.resolve(["alpha", "alpha"]), ["alpha"])
        with self.assertRaises(self.install.UnknownPackage):
            self.install.resolve(["nonsense"])

    def test_install_checks_pins_and_lists_the_result(self):
        failed = self.install.install(["alpha", "beta"], self.root, log=lambda line: None, opener=self.opener)
        self.assertEqual(failed, [])
        self.assertEqual((self.root / "alpha" / "A.ttf").read_bytes(), self.blob)
        self.assertEqual((self.root / "beta" / "B.ttf").read_bytes(), b"zip font bytes")
        self.assertIn("Licence: OFL-1.1", (self.root / "alpha" / "LICENSE-pdfmd.txt").read_text(encoding="utf-8"))
        self.assertEqual(sorted(self.install.installed(self.root)), ["alpha", "beta"])
        self.install.uninstall(["alpha"], self.root, log=lambda line: None)
        self.assertEqual(sorted(self.install.installed(self.root)), ["beta"])
        self.assertFalse((self.root / "alpha").exists())

    def test_a_download_that_does_not_match_its_pin_is_refused(self):
        self.served["https://example.invalid/A.ttf"] = b"tampered"
        messages: list[str] = []
        failed = self.install.install(["alpha"], self.root, log=messages.append, opener=self.opener)
        self.assertEqual(failed, ["alpha"])
        self.assertFalse((self.root / "alpha").exists())
        self.assertFalse((self.root / ".alpha.part").exists())
        self.assertTrue(any("mismatch" in message for message in messages))

    def test_hints_name_the_package_that_has_the_script(self):
        real = self.install.PACKAGES
        self.install.PACKAGES = self._real
        try:
            self.assertEqual(self.install.packages_for([ord("ا")]), ["arabic"])
            self.assertEqual(self.install.packages_for([ord("命")]), ["cjk-sc"])
            self.assertEqual(self.install.packages_for([ord("命")], "ja"), ["cjk-jp"])
            self.assertEqual(self.install.packages_for([0x1F680]), ["emoji"])
        finally:
            self.install.PACKAGES = real

    def test_groups_cover_the_catalog_without_overlap(self):
        groups = self.install.GROUPS
        self.assertTrue(groups["cjk-sans"])
        every = set(self._real)
        self.assertEqual(set(groups["all"]), every)
        parts = [set(groups[name]) for name in ("core", "scripts", "cjk", "cjk-sans")]
        self.assertFalse(set.intersection(parts[0], parts[1], parts[2], parts[3]))
        self.assertEqual(set.union(*parts) | {"emoji", "dejavu"}, every)

    def test_the_real_catalog_is_well_formed(self):
        for key, package in self._real.items():
            self.assertTrue(package["files"], key)
            for item in package["files"]:
                self.assertTrue(("url" in item and "git_sha1" in item) or ("zip" in item and "zip_sha256" in item), key)
                self.assertTrue(item["url" if "url" in item else "zip"].startswith("https://"), key)


class ManagedFonts(unittest.TestCase):
    def setUp(self):
        import os

        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self._previous = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self._directory.name
        self._windows = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._directory.name   # where Windows keeps pdfmd's data folder
        pdfmd.reset_font_caches()
        self.addCleanup(self._restore)
        folder = Path(self._directory.name) / "pdfmd" / "fonts" / "pack"
        folder.mkdir(parents=True)
        make_font(folder / "Only-Regular.ttf", "Only In Pdfmd", [(0x20, 0x7E)])
        make_font(folder / "Only-Bold.ttf", "Only In Pdfmd", [(0x20, 0x7E)], style="Bold")

    def _restore(self):
        import os

        if self._previous is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self._previous
        if self._windows is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._windows
        pdfmd.reset_font_caches()

    def test_a_font_only_in_pdfmds_folder_is_named_by_file_for_latex(self):
        args = pdfmd.font_args("mainfont", "Only In Pdfmd")
        self.assertIn("mainfont=Only-Regular.ttf", args)
        self.assertTrue(any(arg.startswith("mainfontoptions=Path={") for arg in args))
        self.assertIn("mainfontoptions=BoldFont={Only-Bold.ttf}", args)
        self.assertFalse(pdfmd.font_missing("Only In Pdfmd"))

    def test_other_engines_and_installed_fonts_are_named_plainly(self):
        self.assertEqual(pdfmd.font_args("mainfont", "Only In Pdfmd", latex=False), ["-V", "mainfont=Only In Pdfmd"])
        self.assertEqual(pdfmd.font_args("mainfont", "No Such Font Anywhere"), ["-V", "mainfont=No Such Font Anywhere"])

    def test_a_font_the_document_names_is_found_by_file_too(self):
        doc = Path(self._directory.name) / "doc.md"
        doc.write_text("---\nmainfont: Only In Pdfmd\nmonofont: Menlo\n---\ntext\n", encoding="utf-8")
        args = pdfmd.document_font_args([doc], [], [])
        self.assertIn("mainfont=Only-Regular.ttf", args)
        self.assertFalse(any(arg.startswith("monofont") for arg in args))  # not a managed font: left to the document
        self.assertEqual(pdfmd.document_font_args([doc], [], ["mainfontoptions=Scale=0.9"]), [])  # its own options win

    def test_the_fonts_folder_is_given_to_typst_and_listed_for_weasyprint(self):
        with pdfmd.managed_fonts_css("weasyprint") as header:
            self.assertIn('font-family: "Only In Pdfmd"', header.read_text(encoding="utf-8"))
            self.assertIn("font-weight: bold", header.read_text(encoding="utf-8"))
        with pdfmd.managed_fonts_css("lualatex") as header:
            self.assertIsNone(header)

    def test_a_missing_glyph_warning_about_unavoidable_characters_is_no_reason_to_retry(self):
        line = "[WARNING] Missing character: There is no X (U+1F680) (U+1F680) in font Y"
        try:
            pdfmd.UNICODE_UNCOVERED.clear()
            self.assertTrue(pdfmd.missing_glyph_warning(line))
            pdfmd.UNICODE_UNCOVERED.add(0x1F680)
            self.assertFalse(pdfmd.missing_glyph_warning(line))
            self.assertTrue(pdfmd.missing_glyph_warning(line + "\nMissing character: There is no (U+0627) in font Y"))
        finally:
            pdfmd.UNICODE_UNCOVERED.clear()


def make_color_font(path: Path, pictures: dict[int, bytes]) -> Path:
    """A CBDT font with a rocket (glyph 1), a man (2), ZWJ (3), a laptop (4) and a ligature
    man+ZWJ+laptop (5); ``pictures`` maps a glyph to its PNG bytes."""
    cmap_groups = [(0x1F680, 1), (0x1F468, 2), (0x200D, 3), (0x1F4BB, 4)]
    groups = b"".join(struct.pack(">III", cp, cp, glyph) for cp, glyph in sorted(cmap_groups))
    format12 = struct.pack(">HHIII", 12, 0, 16 + len(groups), 0, len(cmap_groups)) + groups
    cmap = struct.pack(">HH", 0, 1) + struct.pack(">HHI", 3, 10, 12) + format12
    coverage = struct.pack(">HHH", 1, 1, 2)
    ligature = struct.pack(">HHHH", 5, 3, 3, 4)
    ligature_set = struct.pack(">HH", 1, 4) + ligature
    # a LigatureSubst: format, offset to the coverage (right after this 8-byte header), set count,
    # the offset of the one ligature set (after the coverage), then both
    subtable = struct.pack(">HHHH", 1, 8, 1, 8 + len(coverage)) + coverage + ligature_set
    lookup = struct.pack(">HHHH", 4, 0, 1, 8) + subtable
    lookup_list = struct.pack(">HH", 1, 4) + lookup
    gsub = struct.pack(">IHHH", 0x00010000, 10, 10, 10) + lookup_list  # the lookup list starts at byte 10
    sbits, offsets, position = b"", [], 0
    for glyph in range(1, 6):
        offsets.append(position)
        if glyph in pictures:
            data = struct.pack(">BBbbB", 1, 1, 0, 0, 1) + struct.pack(">I", len(pictures[glyph])) + pictures[glyph]
            sbits += data
            position += len(data)
    offsets.append(position)
    index_table = struct.pack(">HHI", 1, 17, 4) + b"".join(struct.pack(">I", offset) for offset in offsets)
    array = struct.pack(">HHI", 1, 5, 8)
    size = struct.pack(">IIII", 8 + 48, len(array) + len(index_table), 1, 0) + b"\0" * 24 + struct.pack(">HHBBBB", 1, 5, 109, 109, 32, 1)
    cblc = struct.pack(">II", 0x00030000, 1) + size + array + index_table
    cbdt = struct.pack(">HH", 3, 0) + sbits
    name = struct.pack(">HHH", 0, 0, 6)
    tables = {b"cmap": cmap, b"GSUB": gsub, b"CBLC": cblc, b"CBDT": cbdt, b"name": name}
    header = struct.pack(">4sHHHH", b"\x00\x01\x00\x00", len(tables), 0, 0, 0)
    start, blob = 12 + 16 * len(tables), b""
    for tag, table in sorted(tables.items()):
        header += struct.pack(">4sIII", tag, 0, start + len(blob), len(table))
        blob += table + b"\x00" * (-len(table) % 4)
    path.write_bytes(header + blob)
    return path


class ColourEmoji(unittest.TestCase):
    ROCKET = b"\x89PNG\r\n\x1a\nrocket"
    MAN_AT_COMPUTER = b"\x89PNG\r\n\x1a\ntechnologist"

    def setUp(self):
        from pdfmd_unicode import colorfont

        self.colorfont = colorfont
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.font = make_color_font(self.root / "emoji.ttf", {1: self.ROCKET, 5: self.MAN_AT_COMPUTER})

    def test_sequences_in_text(self):
        found = self.colorfont.emoji_sequences("a \U0001F680 b \U0001F468\u200D\U0001F4BB c \U0001F1F0\U0001F1FF 1\uFE0F\u20E3 \u2764\uFE0F \u2764")
        self.assertEqual(set(found), {"\U0001F680", "\U0001F468\u200D\U0001F4BB", "\U0001F1F0\U0001F1FF",
                                      "1\uFE0F\u20E3", "\u2764\uFE0F"})  # a bare heart is text
        self.assertEqual(self.colorfont.sequence_name("\U0001F468\u200D\U0001F4BB"), "1f468-200d-1f4bb")
        self.assertEqual(self.colorfont.sequence_name("\u2764\uFE0F"), "2764")

    def test_pictures_are_read_from_the_font(self):
        font = self.colorfont.ColorFont(str(self.font))
        self.assertEqual(font.png("\U0001F680"), self.ROCKET)
        self.assertEqual(font.png("\U0001F468\u200D\U0001F4BB"), self.MAN_AT_COMPUTER)  # through the ligature
        self.assertIsNone(font.png("\U0001F4BB"))  # a glyph with no picture
        self.assertIsNone(font.png("\U0001F525"))  # a character the font does not have

    def test_pictures_are_written_for_what_the_main_font_lacks(self):
        text = "x \U0001F680 y \U0001F468\u200D\U0001F4BB"
        wanted = {0x1F680, 0x1F468, 0x1F4BB}
        pictures = self.colorfont.write_pictures(text, wanted, str(self.font), self.root / "out")
        self.assertEqual(set(pictures), {"\U0001F680", "\U0001F468\u200D\U0001F4BB"})
        self.assertEqual(Path(pictures["\U0001F680"]).read_bytes(), self.ROCKET)
        self.assertEqual(self.colorfont.write_pictures(text, set(), str(self.font), self.root / "none"), {})
        self.assertEqual(self.colorfont.write_pictures(text, wanted, str(self.root / "missing.ttf"), self.root / "x"), {})

    def test_the_filter_replaces_a_sequence_with_its_picture(self):
        if not shutil.which("pandoc"):
            self.skipTest("Pandoc not installed")
        make_font(self.root / "main.ttf", "Main Test", [(0x20, 0x7E)])
        index = pu.FontIndex(self.root, use_system=False)
        text = "go \U0001F680 and \U0001F468\u200D\U0001F4BB now"
        plan = pu.plan_text(text, "Main Test", index)
        plan.pictures = self.colorfont.write_pictures(text, plan.emoji, str(self.font), self.root / "out")
        self.assertTrue(plan)
        self.assertIn("\\pdfmdemoji", plan.latex_header())
        filter_file = self.root / "f.lua"
        filter_file.write_text(plan.lua_filter(), encoding="utf-8")
        result = subprocess.run(["pandoc", "-f", "markdown", "-t", "latex", "--lua-filter", str(filter_file)],
                                input=text + "\n", capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.stdout.count("\\pdfmdemoji{"), 2, result.stdout + result.stderr)
        self.assertIn("1f468-200d-1f4bb.png", result.stdout)
        self.assertNotIn("\U0001F680", result.stdout)


class FallbackModes(unittest.TestCase):
    """`fallback: char | word | document | off | box | error` and `missing: warn | box | error`."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        make_font(self.root / "main.ttf", "Main Test", [(0x20, 0x7E), (0x410, 0x44F)])
        make_font(self.root / "noto.ttf", "Noto Serif", [(0x20, 0x7E), (0x400, 0x4FF)])
        self.index = pu.FontIndex(self.root, use_system=False)
        self.text = "plain \u049b\u0430\u0437\u0430\u049b end \u547d"      # a Kazakh word with one letter Main lacks

    def convert(self, plan, target="latex"):
        if not shutil.which("pandoc"):
            self.skipTest("Pandoc not installed")
        filter_file = self.root / "f.lua"
        filter_file.write_text(plan.lua_filter(), encoding="utf-8")
        return subprocess.run(["pandoc", "-f", "markdown", "-t", target, "--lua-filter", str(filter_file)],
                              input=self.text + "\n", capture_output=True, text=True, encoding="utf-8").stdout

    def test_char_sets_only_the_missing_letter(self):
        plan = pu.plan_text(self.text, "Main Test", self.index)
        out = self.convert(plan)
        self.assertIn("\\pdfmdrun{A}{\u049b}\u0430\u0437\u0430\\pdfmdrun{A}{\u049b}", out)

    def test_word_sets_the_whole_word_in_one_font(self):
        plan = pu.plan_text(self.text, "Main Test", self.index, words=True)
        self.assertEqual(plan.words, True)
        out = self.convert(plan)
        self.assertIn("\\pdfmdrun{A}{\u049b\u0430\u0437\u0430\u049b}", out)
        self.assertIn("plain", out)
        self.assertNotIn("\\pdfmdrun{A}{plain", out)  # words with nothing missing stay in the main font

    def test_document_picks_the_font_that_draws_most(self):
        self.assertEqual(pu.choose_document_font(self.text, "Main Test", self.index), "Noto Serif")
        self.assertEqual(pu.choose_document_font("plain text", "Main Test", self.index), "Main Test")

    def test_without_fonts_everything_missing_is_uncovered(self):
        plan = pu.plan_text(self.text, "Main Test", self.index, fonts=False)
        self.assertEqual(set(plan.uncovered), {0x49B, 0x547D})
        self.assertFalse(plan)
        plan.boxes = set(plan.uncovered)
        self.assertTrue(plan)
        self.assertIn("\\pdfmdbox", self.convert(plan))
        self.assertIn("background:#000", self.convert(plan, "html"))
        self.assertIn("fill: black", self.convert(plan, "typst"))
        self.assertIn("\\pdfmdbox", plan.latex_header())

    def test_settings_come_from_the_command_line_then_the_document_then_the_config(self):
        import os

        saved = {key: os.environ.get(key) for key in ("PDFMD_CONFIG",)}
        config = self.root / "config.yaml"
        config.write_text("options:\n  fallback: word\n  missing: box\n", encoding="utf-8")
        os.environ["PDFMD_CONFIG"] = str(config)
        pdfmd.load_config.cache_clear()
        try:
            plain = self.root / "plain.md"
            plain.write_text("text\n", encoding="utf-8")
            own = self.root / "own.md"
            own.write_text("---\npdfmd-options:\n  fallback: off\n---\ntext\n", encoding="utf-8")
            boxed = self.root / "boxed.md"
            boxed.write_text("---\npdfmd-options:\n  fallback: box\n---\ntext\n", encoding="utf-8")
            self.assertEqual(pdfmd.fallback_settings(plain, []), ("word", "box"))     # the config's
            self.assertEqual(pdfmd.fallback_settings(own, []), ("off", "box"))        # YAML `off` is false, still off
            self.assertEqual(pdfmd.fallback_settings(boxed, []), ("box", "box"))
            pdfmd.FALLBACK_CLI, pdfmd.MISSING_CLI = "error", None
            self.assertEqual(pdfmd.fallback_settings(plain, []), ("error", "error"))   # the command line wins
            pdfmd.FALLBACK_CLI = "sideways"
            with self.assertRaises(SystemExit):
                pdfmd.fallback_settings(plain, [])
        finally:
            pdfmd.FALLBACK_CLI = pdfmd.MISSING_CLI = None
            if saved["PDFMD_CONFIG"] is None:
                os.environ.pop("PDFMD_CONFIG", None)
            else:
                os.environ["PDFMD_CONFIG"] = saved["PDFMD_CONFIG"]
            pdfmd.load_config.cache_clear()

    def test_word_is_the_default_and_false_is_off(self):
        plain = self.root / "plain.md"
        plain.write_text("text\n", encoding="utf-8")
        self.assertEqual(pdfmd.fallback_settings(plain, []), ("word", "warn"))
        for written, expected in (("false", "off"), ("no", "off"), ("off", "off"), ("none", "off"),
                                  ("true", "word"), ("on", "word"), ("char", "char")):
            doc = self.root / f"{written}.md"
            doc.write_text(f"---\npdfmd-options:\n  fallback: {written}\n---\ntext\n", encoding="utf-8")
            self.assertEqual(pdfmd.fallback_settings(doc, [])[0], expected, written)

    def test_pdfmds_own_default_font_is_replaced_for_the_documents_script_with_a_note(self):
        make_font(self.root / "weak.ttf", "STIX Two Text", [(0x20, 0x7E), (0x410, 0x44F)])
        make_font(self.root / "noto2.ttf", "Noto Serif", [(0x20, 0x7E), (0x400, 0x4FF)])
        index = pu.FontIndex(self.root, use_system=False)
        doc = self.root / "kk.md"
        doc.write_text("\u049b\u0430\u0437\u0430\u049b \u0442\u0456\u043b\u0456 " * 30 + "\n", encoding="utf-8")
        notes: list[tuple] = []
        saved = pdfmd._FONT_INDEX, pdfmd.preferred_font
        pdfmd._FONT_INDEX, pdfmd.preferred_font = index, (lambda: "STIX Two Text")
        try:
            chosen = pdfmd.mainfont_choice([doc], [], [], None, False, True, None, lambda *a: notes.append(a))
            self.assertEqual(chosen, "Noto Serif")
            self.assertEqual(notes[0][0], "MAINFONT")
            self.assertIn("instead of STIX Two Text", notes[0][1])
            # a font the user names is never replaced (but for fallback: document), nor with the fallback off
            self.assertEqual(pdfmd.mainfont_choice([doc], [], [], "STIX Two Text", False, True, None), "STIX Two Text")
            pdfmd.FALLBACK_CLI = "off"
            self.assertEqual(pdfmd.mainfont_choice([doc], [], [], None, False, True, None), "STIX Two Text")
        finally:
            pdfmd._FONT_INDEX, pdfmd.preferred_font = saved
            pdfmd.FALLBACK_CLI = None

    def test_the_main_font_is_not_changed_for_a_few_characters(self):
        doc = self.root / "d.md"
        doc.write_text("---\nmainfont: Main Test\n---\n" + self.text + "\n", encoding="utf-8")
        pdfmd.FALLBACK_CLI = None
        # the document's own font is left to the document (None): the fallback handles the rest
        self.assertIsNone(pdfmd.mainfont_choice([doc], [], [], None, True, True, None))
        self.assertEqual(pdfmd.mainfont_choice([doc], [], [], "Cli Font", True, True, None), "Cli Font")


class CodeFallback(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        make_font(self.root / "main.ttf", "Main Test", [(0x20, 0x7E), (0x2190, 0x21FF)])
        make_font(self.root / "mono.ttf", "Mono Test", [(0x20, 0x7E)])
        make_font(self.root / "dejavu.ttf", "DejaVu Sans", [(0x20, 0x7E), (0x2190, 0x21FF)])
        make_font(self.root / "amiri.ttf", "Amiri", [(0x600, 0x6FF)])
        self.index = pu.FontIndex(self.root, use_system=False)

    def plan(self, code_text):
        plan = pu.plan_text("body \u2192 text", "Main Test", self.index)   # the main font draws the arrow
        code = pu.plan_text(code_text, "Mono Test", self.index)           # the monofont does not
        plan.add_code(code)
        return plan

    def convert(self, plan, markdown):
        if not shutil.which("pandoc"):
            self.skipTest("Pandoc not installed")
        filter_file = self.root / "f.lua"
        filter_file.write_text(plan.lua_filter(), encoding="utf-8")
        return subprocess.run(["pandoc", "-f", "markdown", "-t", "latex", "--lua-filter", str(filter_file)],
                              input=markdown, capture_output=True, text=True, encoding="utf-8").stdout

    def test_code_has_its_own_missing_characters(self):
        plan = self.plan("a \u2192 b")
        self.assertEqual(plan.describe(), [])            # the body needs nothing
        self.assertIn("\\usepackage{fancyvrb}", plan.latex_header())
        out = self.convert(plan, "see `a \u2192 b` and \u2192 here\n")
        self.assertIn("\\pdfmdrun{A}{\u2192}", out)
        self.assertEqual(out.count("pdfmdrun"), 1)         # the arrow in the text is the main font's

    def test_code_blocks_become_verbatim_with_the_fallback_inside(self):
        plan = self.plan("x \u2192 {y} \\ z")
        out = self.convert(plan, "```\nx \u2192 {y} \\ z\nplain\n```\n\n```\nnothing special\n```\n")
        self.assertIn("\\begin{Verbatim}[commandchars=\\\\\\{\\}]", out)
        self.assertIn("x \\pdfmdrun{A}{\u2192} \\{y\\} \\textbackslash{} z\nplain", out)
        self.assertEqual(out.count("Verbatim}[") , 1)       # the block without trouble stays a normal one
        self.assertIn("nothing special", out)

    def test_right_to_left_code_gets_its_direction(self):
        plan = self.plan("a \u0627\u0644")
        self.assertIn("\\pdfmdrunrtl{", self.convert(plan, "`a \u0627\u0644`\n"))

    def test_boxes_in_code(self):
        plan = pu.plan_text("body", "Main Test", self.index)
        plan.code_boxes = {0x2192}
        self.assertTrue(plan)
        self.assertIn("\\pdfmdbox", self.convert(plan, "`a \u2192 b`\n"))


class CheckFonts(unittest.TestCase):
    def test_the_report_names_fonts_and_what_is_missing(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_font(root / "main.ttf", "Main Test", [(0x20, 0x7E)])
            make_font(root / "amiri.ttf", "Amiri", [(0x600, 0x6FF)])
            doc = root / "d.md"
            doc.write_text("---\nmainfont: Main Test\n---\nhello \u0627\u0644 and \u547d\n", encoding="utf-8")
            pdfmd._FONT_INDEX = pu.FontIndex(root, use_system=False)
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    ok = pdfmd.check_fonts(doc, None, [])
            finally:
                pdfmd._FONT_INDEX = None
                pdfmd.reset_font_caches()
        text = out.getvalue()
        self.assertFalse(ok)                                   # the Han character has no font
        self.assertIn("main font: Main Test", text)
        self.assertIn("Arabic takes Amiri", text)
        self.assertIn("U+547D", text)
        self.assertIn("pdfmd --install fonts:cjk-sc", text)


class CodeEmoji(unittest.TestCase):
    def test_emoji_in_code_become_pictures_and_plain_code_is_left_alone(self):
        if not shutil.which("pandoc"):
            self.skipTest("Pandoc not installed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_font(root / "main.ttf", "Main Test", [(0x20, 0x7E)])
            make_font(root / "mono.ttf", "Mono Test", [(0x20, 0x7E)])
            font = make_color_font(root / "emoji.ttf", {1: b"\x89PNG\r\n\x1a\nrocket"})
            index = pu.FontIndex(root, use_system=False)
            code_text = "go \U0001F680 now"
            plan = pu.plan_text("body", "Main Test", index)
            code = pu.plan_text(code_text, "Mono Test", index)
            self.assertIn(0x1F680, code.emoji)
            plan.add_code(code)
            plan.pictures = __import__("pdfmd_unicode.colorfont", fromlist=["x"]).write_pictures(code_text, code.emoji, str(font), root / "pics")
            filter_file = root / "f.lua"
            filter_file.write_text(plan.lua_filter(), encoding="utf-8")

            def convert(markdown):
                return subprocess.run(["pandoc", "-f", "markdown", "-t", "latex", "--lua-filter", str(filter_file)],
                                      input=markdown, capture_output=True, text=True, encoding="utf-8").stdout

            self.assertIn("fancyvrb", plan.latex_header())
            self.assertIn("\\pdfmdemojin{0}", convert("`go \U0001F680 now`\n"))
            block = convert("```\ngo \U0001F680 now\n```\n")
            self.assertIn("\\pdfmdemojin{0}", block)
            self.assertIn("Verbatim", block)
            plain = convert("```\n1 + 1\n```\n")             # a digit starts a keycap sequence, but is not one
            self.assertNotIn("Verbatim}[", plain)
            self.assertNotIn("pdfmdemoji", plain)


class CodeFontsForOtherEngines(unittest.TestCase):
    """Typst takes a `codefont` list, WeasyPrint a CSS font-family for code."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        make_font(self.root / "main.ttf", "Main Test", [(0x20, 0x7E)])
        make_font(self.root / "mono.ttf", "DejaVu Sans Mono", [(0x20, 0x7E)])
        make_font(self.root / "songti.ttf", "Songti SC", [(0x4E00, 0x9FFF)])
        make_font(self.root / "menlo.ttf", "Menlo", [(0x20, 0x7E)])
        self.doc = self.root / "d.md"
        self.doc.write_text("hello\n\n```\nx = '\u547d'\n```\n", encoding="utf-8")
        pdfmd._FONT_INDEX = pu.FontIndex(self.root, use_system=False)
        self.addCleanup(self._reset)

    def _reset(self):
        pdfmd._FONT_INDEX = None
        pdfmd.UNICODE_CODE_FONTS.clear()
        pdfmd.reset_font_caches()

    def run_fallback(self, engine):
        notes = []
        with pdfmd.script_fallback([self.doc], [], [], [], "Main Test", engine, None, lambda *a: notes.append(a)) as made:
            return made, list(pdfmd.UNICODE_CODE_FONTS)

    def test_typst_gets_a_codefont_list(self):
        (header, filter_file), fonts = self.run_fallback("typst")
        self.assertEqual(fonts, ["DejaVu Sans Mono", "Songti SC"])

    def test_weasyprint_gets_a_css_rule(self):
        _, fonts = self.run_fallback("weasyprint")
        self.assertEqual(fonts, ["Menlo", "Songti SC"])
        pdfmd.UNICODE_CODE_FONTS[:] = fonts
        with pdfmd.managed_fonts_css("weasyprint") as header:
            text = header.read_text(encoding="utf-8")
        self.assertIn('font-family: "Menlo", "Songti SC", monospace', text)

    def test_latex_keeps_its_own_way(self):
        (header, filter_file), fonts = self.run_fallback("lualatex")
        self.assertEqual(fonts, [])


class FallbackErrors(unittest.TestCase):
    def test_missing_error_stops_the_build_naming_the_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_font(root / "main.ttf", "Main Test", [(0x20, 0x7E)])
            doc = root / "d.md"
            doc.write_text("---\npdfmd-options:\n  fallback: error\n---\nhello \u547d\n", encoding="utf-8")
            real = pdfmd.font_index
            pdfmd._FONT_INDEX = pu.FontIndex(root, use_system=False)
            try:
                with self.assertRaises(SystemExit) as caught:
                    with pdfmd.script_fallback([doc], [], [], [], "Main Test", "lualatex", None, lambda *a: None):
                        pass
                self.assertIn("U+547D", str(caught.exception))
            finally:
                pdfmd._FONT_INDEX = None
                pdfmd.reset_font_caches()


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
