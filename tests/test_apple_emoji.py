"""Apple Color Emoji names its glyphs for sequences (`u1F469_u1F52C.3`); pdfmd reads the `post` table."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfmd_unicode import colorfont  # noqa: E402


def post_table(names: list[str]) -> bytes:
    """A format-2 `post` table naming glyph 0 .notdef (standard index 0), then `names` from 258."""
    header = struct.pack(">IIhhIIIII", 0x00020000, 0, 0, 0, 0, 0, 0, 0, 0)
    indexes = struct.pack(f">{len(names) + 1}H", 0, *range(258, 258 + len(names)))
    strings = b"".join(bytes([len(name)]) + name.encode("latin-1") for name in names)
    return header + struct.pack(">H", len(names) + 1) + indexes + strings


class AppleNames(unittest.TestCase):
    def test_post_table_names_map_to_glyph_ids(self):
        names = colorfont.post_names(post_table(["u1F44D.3", "u1F680"]))
        self.assertEqual(names, {"u1F44D.3": 1, "u1F680": 2})
        self.assertEqual(colorfont.post_names(b"\x00\x03\x00\x00" + b"\0" * 40), {})

    def test_sequence_to_glyph_names(self):
        self.assertEqual(colorfont.apple_names("\U0001F44D\U0001F3FD")[0], "u1F44D.3")                 # thumbs up, tone 3
        self.assertEqual(colorfont.apple_names("\U0001F469‍\U0001F52C")[0], "u1F469_u1F52C.0")     # woman scientist
        self.assertEqual(colorfont.apple_names("\U0001F469\U0001F3FD‍\U0001F52C")[0], "u1F469_u1F52C.3")
        self.assertEqual(colorfont.apple_names("\U0001F1F0\U0001F1FF")[0], "u1F1F0_u1F1FF.0")          # flag: .0 tried first, bare name next
        self.assertIn("u1F1F0_u1F1FF", colorfont.apple_names("\U0001F1F0\U0001F1FF"))
        self.assertIn("u1F9CE.0.W", colorfont.apple_names("\U0001F9CE‍♀️"))             # kneeling woman
        self.assertIn("u1F468_u1F91D_u1F468.11", colorfont.apple_names("\U0001F468\U0001F3FB‍\U0001F91D‍\U0001F468\U0001F3FB"))
        self.assertIn("u0031_u20E3", colorfont.apple_names("1️⃣"))

    def test_a_font_with_names_finds_the_toned_glyph(self):
        font = colorfont.ColorFont.__new__(colorfont.ColorFont)
        font._names = {"u1F44D.3": 7}
        font._cmap = {0x1F44D: 5, 0x1F3FD: 6}
        font._ligatures = {}
        font._selector = font._joiner = None
        self.assertEqual(font.glyph_for("\U0001F44D\U0001F3FD"), 7)
        self.assertEqual(font.glyph_for("\U0001F44D"), 5)

    def test_a_joined_emoji_apple_cannot_name_is_undrawn_not_its_first_emoji(self):
        font = colorfont.ColorFont.__new__(colorfont.ColorFont)
        font._names = {"u1F468.0": 3}
        font._cmap = {0x1F468: 3, 0x1F469: 4, 0x200D: 9}
        font._ligatures = {}
        font._selector = font._joiner = None
        self.assertIsNone(font.glyph_for("\U0001F468‍\U0001F469"))


if __name__ == "__main__":
    unittest.main()
