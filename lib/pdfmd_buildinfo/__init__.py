"""What a build leaves behind about itself: how long it took (`timing`) and the record it is kept in (`record`).
Pure: no pdfmd import."""

from . import record
from .timing import STYLES, Step, Timer, check_style, format_duration

__all__ = ["STYLES", "Step", "Timer", "check_style", "format_duration", "record"]
