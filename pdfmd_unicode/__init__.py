"""Script-aware font fallback for pdfmd: what the main font cannot draw, and who can.

fonts.py    reading fonts (family names, covered code points) and finding installed ones
scripts.py  which script a character is in, and the fonts tried for each script
plan.py     the plan for one document: a LaTeX preamble and a Pandoc Lua filter
translit.py romanization packs for finding names in other scripts

Independent of pdfmd.py (which imports it lazily and does without it).
"""

from . import translit
from .fonts import Face, FontIndex, coverage
from .plan import Plan, choose_main_font, plan_text
from .scripts import SCRIPT_NAMES, han_language, script_of

__all__ = ["translit", "Face", "FontIndex", "Plan", "SCRIPT_NAMES", "choose_main_font", "coverage", "han_language", "plan_text", "script_of"]
