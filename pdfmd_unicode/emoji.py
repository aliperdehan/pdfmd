"""Which characters are emoji (drawn in colour), without a Unicode emoji table.

Approximate by design: the ranges of the emoji blocks, and the older symbols that are emoji too
when a variation selector (U+FE0F) asks for it. A symbol such as the heart U+2764 is text by
default and emoji only with U+FE0F, so a lone one is left to the symbol fonts.
"""

from __future__ import annotations

# Always emoji (pictographs, flags' regional indicators, transport, food, faces, hands...).
EMOJI_BLOCKS = ((0x1F300, 0x1F5FF), (0x1F600, 0x1F64F), (0x1F680, 0x1F6FF), (0x1F900, 0x1F9FF),
                (0x1FA70, 0x1FAFF), (0x1F1E6, 0x1F1FF), (0x1F3FB, 0x1F3FF))
# Emoji in the older blocks: arrows, shapes, Misc Symbols and Dingbats, only a subset is emoji by default.
DEFAULT_EMOJI = frozenset(
    [0x231A, 0x231B, 0x23E9, 0x23EA, 0x23EB, 0x23EC, 0x23F0, 0x23F3, 0x25FD, 0x25FE, 0x2614, 0x2615]
    + list(range(0x2648, 0x2654)) + [0x267F, 0x2693, 0x26A1, 0x26AA, 0x26AB, 0x26BD, 0x26BE, 0x26C4, 0x26C5,
                                     0x26CE, 0x26D4, 0x26EA, 0x26F2, 0x26F3, 0x26F5, 0x26FA, 0x26FD, 0x2705,
                                     0x270A, 0x270B, 0x2728, 0x274C, 0x274E, 0x2753, 0x2754, 0x2755, 0x2757,
                                     0x2795, 0x2796, 0x2797, 0x27B0, 0x27BF, 0x2B1B, 0x2B1C, 0x2B50, 0x2B55])
# Text by default, emoji when followed by U+FE0F.
TEXT_DEFAULT_EMOJI = ((0x203C, 0x203C), (0x2049, 0x2049), (0x2122, 0x2122), (0x2139, 0x2139),
                      (0x2194, 0x21AA), (0x2328, 0x2328), (0x23CF, 0x23CF), (0x23ED, 0x23EF),
                      (0x23F1, 0x23F2), (0x23F8, 0x23FA), (0x24C2, 0x24C2), (0x25AA, 0x25FC),
                      (0x2600, 0x27BF), (0x2934, 0x2935), (0x2B05, 0x2B07), (0x3030, 0x3030),
                      (0x303D, 0x303D), (0x3297, 0x3299), (0xA9, 0xA9), (0xAE, 0xAE))
VARIATION_EMOJI = 0xFE0F
ZERO_WIDTH_JOINER = 0x200D
KEYCAP = 0x20E3


def is_emoji_code_point(code_point: int) -> bool:
    """True for characters that are emoji on their own."""
    return code_point in DEFAULT_EMOJI or any(low <= code_point <= high for low, high in EMOJI_BLOCKS)


def can_be_emoji(code_point: int) -> bool:
    """True for characters that are emoji when followed by U+FE0F."""
    return any(low <= code_point <= high for low, high in TEXT_DEFAULT_EMOJI)
