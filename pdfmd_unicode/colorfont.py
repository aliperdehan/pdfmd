"""Pictures of emoji out of a colour bitmap font (Noto Color Emoji's CBDT/CBLC tables).

LaTeX engines cannot draw colour fonts, but they can include pictures. This reads the PNG of a
glyph straight out of the font file (no dependency), and finds the glyph of an emoji
sequence (a flag, a family, a skin tone, a keycap) through the font's own ligature
substitutions (GSUB, lookup type 4), the way a text shaper would.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .emoji import EMOJI_BLOCKS, DEFAULT_EMOJI, TEXT_DEFAULT_EMOJI, VARIATION_EMOJI, ZERO_WIDTH_JOINER

SKIN_TONES = "\U0001F3FB-\U0001F3FF"


def _class(ranges) -> str:
    return "".join(f"{chr(low)}-{chr(high)}" if low != high else chr(low) for low, high in ranges)


_ALWAYS = _class(EMOJI_BLOCKS) + "".join(chr(code) for code in sorted(DEFAULT_EMOJI))
_WITH_SELECTOR = _class(TEXT_DEFAULT_EMOJI)
_ELEMENT = (rf"(?:[{_ALWAYS}]️?[{SKIN_TONES}]?|[{_WITH_SELECTOR}]️[{SKIN_TONES}]?)")
SEQUENCE_RE = re.compile(
    rf"[\U0001F1E6-\U0001F1FF]{{2}}"                               # a flag
    rf"|[\U0001F3F4][\U000E0020-\U000E007E]+\U000E007F"          # a subdivision flag
    rf"|[0-9#*]️?⃣"                                      # a keycap
    rf"|{_ELEMENT}(?:‍{_ELEMENT})*"                           # one emoji, or several joined
)


def emoji_sequences(text: str) -> list[str]:
    """The distinct emoji sequences in ``text``, longest first."""
    found = {match.group(0) for match in SEQUENCE_RE.finditer(text)}
    return sorted(found, key=lambda sequence: (-len(sequence), sequence))


# -- reading the font --------------------------------------------------------------------

def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _tables(path: str, index: int = 0) -> dict[bytes, bytes]:
    wanted = (b"cmap", b"GSUB", b"CBLC", b"CBDT", b"sbix", b"maxp")
    with open(path, "rb") as handle:
        magic = handle.read(4)
        base = 0
        if magic == b"ttcf":
            handle.seek(12 + 4 * index)
            base = struct.unpack(">I", handle.read(4))[0]
        handle.seek(base + 4)
        count = struct.unpack(">H", handle.read(2))[0]
        handle.seek(base + 12)
        directory = handle.read(16 * count)
        tables = {}
        for number in range(count):
            tag, _checksum, offset, length = struct.unpack(">4sIII", directory[number * 16:number * 16 + 16])
            if tag in wanted:
                handle.seek(offset)
                tables[tag] = handle.read(length)
    return tables


def _coverage(data: bytes, offset: int) -> list[int]:
    form = _u16(data, offset)
    if form == 1:
        count = _u16(data, offset + 2)
        return [_u16(data, offset + 4 + 2 * number) for number in range(count)]
    glyphs: list[int] = []
    for number in range(_u16(data, offset + 2)):
        first, last, _start = struct.unpack_from(">HHH", data, offset + 4 + 6 * number)
        glyphs.extend(range(first, last + 1))
    return glyphs


def _cmap(data: bytes) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for number in range(_u16(data, 2)):
        platform, encoding, start = struct.unpack_from(">HHI", data, 4 + 8 * number)
        if platform not in (0, 3):
            continue
        form = _u16(data, start)
        if form == 12:
            for group in range(_u32(data, start + 12)):
                first, last, glyph = struct.unpack_from(">III", data, start + 16 + 12 * group)
                for code in range(first, last + 1):
                    mapping.setdefault(code, glyph + code - first)
        elif form == 4:
            segments = _u16(data, start + 6) // 2
            ends, starts = start + 14, start + 16 + 2 * segments
            deltas, ranges = starts + 2 * segments, starts + 4 * segments
            for segment in range(segments):
                end = _u16(data, ends + 2 * segment)
                first = _u16(data, starts + 2 * segment)
                delta = struct.unpack_from(">h", data, deltas + 2 * segment)[0]
                shift = _u16(data, ranges + 2 * segment)
                if first == 0xFFFF:
                    continue
                for code in range(first, end + 1):
                    if shift == 0:
                        glyph = (code + delta) & 0xFFFF
                    else:
                        position = ranges + 2 * segment + shift + 2 * (code - first)
                        glyph = _u16(data, position) if position + 2 <= len(data) else 0
                        glyph = (glyph + delta) & 0xFFFF if glyph else 0
                    if glyph:
                        mapping.setdefault(code, glyph)
    return mapping


def _ligatures(data: bytes) -> dict[tuple[int, ...], int]:
    """(glyph, glyph, ...) -> the single glyph the font substitutes for them."""
    ligatures: dict[tuple[int, ...], int] = {}
    lookups = _u16(data, 8)
    count = _u16(data, lookups)
    for number in range(count):
        lookup = lookups + _u16(data, lookups + 2 + 2 * number)
        kind = _u16(data, lookup)
        for sub in range(_u16(data, lookup + 4)):
            table = lookup + _u16(data, lookup + 6 + 2 * sub)
            if kind == 7:
                kind_inner = _u16(data, table + 2)
                if kind_inner != 4:
                    continue
                table += _u32(data, table + 4)
            elif kind != 4:
                continue
            if _u16(data, table) != 1:
                continue
            covered = _coverage(data, table + _u16(data, table + 2))
            for position, first in enumerate(covered):
                ligature_set = table + _u16(data, table + 6 + 2 * position)
                for entry in range(_u16(data, ligature_set)):
                    ligature = ligature_set + _u16(data, ligature_set + 2 + 2 * entry)
                    glyph = _u16(data, ligature)
                    parts = _u16(data, ligature + 2)
                    rest = tuple(_u16(data, ligature + 4 + 2 * part) for part in range(parts - 1))
                    ligatures.setdefault((first, *rest), glyph)
    return ligatures


def _glyph_image(cblc: bytes, cbdt: bytes, glyph: int) -> bytes | None:
    """The PNG of ``glyph`` from the largest bitmap strike that has it."""
    best: tuple[int, bytes] | None = None
    for size in range(_u32(cblc, 4)):
        record = 8 + 48 * size
        array_offset, _tables_size, tables = struct.unpack_from(">III", cblc, record)
        first_glyph, last_glyph = struct.unpack_from(">HH", cblc, record + 40)
        ppem = cblc[record + 44]
        if not first_glyph <= glyph <= last_glyph:
            continue
        for number in range(tables):
            first, last, additional = struct.unpack_from(">HHI", cblc, array_offset + 8 * number)
            if not first <= glyph <= last:
                continue
            table = array_offset + additional
            index_format, image_format, image_offset = struct.unpack_from(">HHI", cblc, table)
            position = glyph - first
            if index_format == 1:
                start, end = struct.unpack_from(">II", cblc, table + 8 + 4 * position)
            elif index_format == 3:
                start, end = struct.unpack_from(">HH", cblc, table + 8 + 2 * position)
            else:
                continue
            if end <= start:
                continue
            at = image_offset + start
            if image_format == 17:
                at += 5
            elif image_format == 18:
                at += 8
            elif image_format != 19:
                continue
            length = _u32(cbdt, at)
            png = cbdt[at + 4:at + 4 + length]
            if png[:4] == b"\x89PNG" and (best is None or ppem > best[0]):
                best = (ppem, png)
    return best[1] if best else None


def _sbix_image(sbix: bytes, glyphs: int, glyph: int, depth: int = 0) -> bytes | None:
    """The PNG of ``glyph`` from the largest sbix strike that has it (Apple Color Emoji)."""
    if not 0 <= glyph < glyphs or depth > 2:
        return None
    best: tuple[int, bytes] | None = None
    for strike in range(_u32(sbix, 4)):
        base = _u32(sbix, 8 + 4 * strike)
        ppem = _u16(sbix, base)
        start, end = struct.unpack_from(">II", sbix, base + 4 + 4 * glyph)
        if end <= start + 8:
            continue
        kind, data = sbix[base + start + 4:base + start + 8], sbix[base + start + 8:base + end]
        if kind == b"dupe" and len(data) >= 2:
            data = _sbix_image(sbix, glyphs, _u16(data, 0), depth + 1)
            kind = b"png "
        if kind == b"png " and data and data[:4] == b"\x89PNG" and (best is None or ppem > best[0]):
            best = (ppem, data)
    return best[1] if best else None


class ColorFont:
    """A bitmap colour font (CBDT as in Noto Color Emoji, or sbix as in Apple Color Emoji): look up
    the picture of an emoji sequence."""

    def __init__(self, path: str, index: int = 0):
        tables = _tables(path, index)
        cbdt = all(tag in tables for tag in (b"CBLC", b"CBDT"))
        if b"cmap" not in tables or not (cbdt or (b"sbix" in tables and b"maxp" in tables)):
            raise ValueError("not a bitmap colour font")
        self.path = path
        self._cblc, self._cbdt = tables.get(b"CBLC"), tables.get(b"CBDT")
        self._sbix = None if cbdt else tables[b"sbix"]
        self._glyphs = _u16(tables[b"maxp"], 4) if b"maxp" in tables else 0
        self._cmap = _cmap(tables[b"cmap"])
        self._ligatures = _ligatures(tables[b"GSUB"]) if b"GSUB" in tables else {}
        self._selector = self._cmap.get(VARIATION_EMOJI)
        self._joiner = self._cmap.get(ZERO_WIDTH_JOINER)

    def glyph_for(self, sequence: str) -> int | None:
        glyphs = [self._cmap.get(ord(character)) for character in sequence]
        if any(glyph is None for glyph in glyphs):
            # a character the font has no glyph for: try without the selector, else give up
            glyphs = [self._cmap.get(ord(character)) for character in sequence if ord(character) != VARIATION_EMOJI]
            if any(glyph is None for glyph in glyphs):
                return None
        variants = [tuple(glyphs), tuple(glyph for glyph in glyphs if glyph != self._selector)]
        for variant in variants:
            if variant in self._ligatures:
                return self._ligatures[variant]
        for variant in variants:
            if len(variant) == 1:
                return variant[0]
        # a sequence the font does not know as a whole: show its first emoji
        return variants[1][0] if variants[1] else None

    def png(self, sequence: str) -> bytes | None:
        glyph = self.glyph_for(sequence)
        if glyph is None:
            return None
        if self._sbix is not None:
            return _sbix_image(self._sbix, self._glyphs, glyph)
        return _glyph_image(self._cblc, self._cbdt, glyph)


def sequence_name(sequence: str) -> str:
    """A file name for an emoji sequence: its code points, e.g. 1f468-200d-1f4bb."""
    return "-".join(f"{ord(character):x}" for character in sequence if ord(character) != VARIATION_EMOJI) or "emoji"


def write_pictures(text: str, wanted: set[int], font_path: str, directory: Path, index: int = 0) -> dict[str, str]:
    """Write a PNG for each emoji sequence of ``text`` that contains a wanted code point (one
    the main font lacks); returns sequence -> file path. Sequences the font cannot draw are left out."""
    try:
        font = ColorFont(font_path, index)
    except (OSError, ValueError, struct.error):
        return {}
    pictures: dict[str, str] = {}
    for sequence in emoji_sequences(text):
        if not any(ord(character) in wanted for character in sequence):
            continue
        target = directory / f"{sequence_name(sequence)}.png"
        if not target.is_file():
            try:
                data = font.png(sequence)
            except (struct.error, IndexError):
                data = None
            if data is None:
                continue
            directory.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".part")
            temporary.write_bytes(data)
            temporary.replace(target)
        pictures[sequence] = str(target)
    return pictures
