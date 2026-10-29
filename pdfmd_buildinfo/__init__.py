"""What a build leaves behind about itself: how long it took (`timing`). Pure: no pdfmd import."""

from .timing import STYLES, Step, Timer, check_style, format_duration

__all__ = ["STYLES", "Step", "Timer", "check_style", "format_duration"]
