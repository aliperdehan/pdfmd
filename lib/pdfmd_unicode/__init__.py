"""Script-aware font fallback for pdfmd: what the main font cannot draw, and who can.

fonts.py    reading fonts (family names, covered code points) and finding installed ones
scripts.py  which script a character is in, and the fonts tried for each script
plan.py     the plan for one document: a LaTeX preamble and a Pandoc Lua filter
translit.py romanization packs for finding names in other scripts
document.py document font settings, indices, math companions, fallback modes and missing-glyph diagnostics
fonts_choice.py  how pdfmd chooses its fonts: missing fonts and their stand-ins, --check-fonts, the per-script fallback of a build

Independent of pdfmd.py (which imports it lazily), except fonts_choice.py and document.py: moved out of pdfmd.py, they read pdfmd as
their `core` and are not imported here.
"""

from . import translit
from .fonts import Face, FontIndex, coverage
from .plan import Plan, choose_document_font, choose_main_font, plan_text
from .scripts import SCRIPT_NAMES, han_language, script_of

__all__ = ["translit", "Face", "FontIndex", "Plan", "SCRIPT_NAMES", "choose_document_font", "choose_main_font", "coverage", "han_language", "plan_text", "script_of"]
