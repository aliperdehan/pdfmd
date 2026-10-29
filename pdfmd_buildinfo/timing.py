"""How long a build took: the clock, the steps, and how a duration is written.

Pure: no pdfmd import. A duration is written by a *style*, one of the names in STYLES or a template:

    auto     0.42 s | 12.4 s | 3:07 | 1:02:03 | 1 d 02:03:04      (the default)
    clock    03:07 | 1:02:03 | 30:00:00                           (always [h:]mm:ss, hours never wrap into days)
    seconds  0.42 s | 12.4 s | 187.0 s                            (seconds only)
    words    12.4 s | 3 min 7 s | 1 h 2 min 3 s | 1 d 2 h 3 min 4 s

A template has tokens in braces: {d} days, {h} {hh} hours, {m} {mm} minutes, {s} {ss} seconds, {s1} {s2} seconds with one
or two decimals, {ms} the three digits of the milliseconds. `{h}:{mm}:{ss}`, `{s} s`, `{m} min {s} s`. A unit that has a larger
unit in the template wraps (minutes at 60 when {h} is there), the largest one counts everything (`{s} s` is 187 s for
3 min 7 s). The time is rounded to the smallest unit the template shows.
"""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from dataclasses import dataclass

STYLES = ("auto", "clock", "seconds", "words")
CLOCK = time.monotonic          # a test replaces it

_TOKEN = re.compile(r"\{([a-z0-9]*)\}")
_UNITS = {"d": 86400000, "h": 3600000, "m": 60000, "s": 1000}


def _split(milliseconds: int) -> tuple[int, int, int, int, int]:
    """(days, hours, minutes, seconds, milliseconds) of a whole number of milliseconds, nothing wrapped away."""
    seconds, millis = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return days, hours, minutes, seconds, millis


def _round_to(milliseconds: float, step: int) -> int:
    """Half up to a multiple of ``step`` milliseconds (Python's round() goes to even)."""
    return int((milliseconds + step / 2) // step) * step


def _auto(seconds: float) -> str:
    if _round_to(seconds * 1000, 10) < 1000:
        return f"{_round_to(seconds * 1000, 10) / 1000:.2f} s"
    if _round_to(seconds * 1000, 100) < 60000:
        return f"{_round_to(seconds * 1000, 100) / 1000:.1f} s"
    total = _round_to(seconds * 1000, 1000) // 1000
    days, hours, minutes, secs, _ = _split(total * 1000)
    if days:
        return f"{days} d {hours:02d}:{minutes:02d}:{secs:02d}"
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _clock(seconds: float) -> str:
    total = _round_to(seconds * 1000, 1000) // 1000
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _seconds(seconds: float) -> str:
    if _round_to(seconds * 1000, 10) < 1000:
        return f"{_round_to(seconds * 1000, 10) / 1000:.2f} s"
    return f"{_round_to(seconds * 1000, 100) / 1000:.1f} s"


def _words(seconds: float) -> str:
    if _round_to(seconds * 1000, 100) < 60000:
        return _seconds(seconds)
    days, hours, minutes, secs, _ = _split(_round_to(seconds * 1000, 1000))
    parts = [(days, "d"), (hours, "h"), (minutes, "min"), (secs, "s")]
    while parts and not parts[0][0]:
        parts.pop(0)
    while parts and not parts[-1][0] and len(parts) > 1:
        parts.pop()
    return " ".join(f"{value} {unit}" for value, unit in parts)


def template_tokens(template: str) -> list[str]:
    return _TOKEN.findall(template)


def check_style(style: str) -> str | None:
    """None when ``style`` is a preset or a usable template, else what is wrong with it."""
    text = style.strip()
    if text in STYLES:
        return None
    tokens = template_tokens(text)
    if not tokens:
        return f"{style!r} is neither one of {', '.join(STYLES)} nor a template with tokens such as {{m}}:{{ss}}"
    known = {"d", "h", "hh", "m", "mm", "s", "ss", "s1", "s2", "ms"}
    unknown = [token for token in tokens if token not in known]
    if unknown:
        return f"unknown token {{{unknown[0]}}} in the time format {style!r} (use {', '.join('{' + t + '}' for t in sorted(known))})"
    return None


def _template(seconds: float, template: str) -> str:
    tokens = set(template_tokens(template))
    if "ms" in tokens:
        step = 1
    elif "s2" in tokens:
        step = 10
    elif "s1" in tokens:
        step = 100
    elif tokens & {"s", "ss"}:
        step = 1000
    elif tokens & {"m", "mm"}:
        step = 60000
    elif tokens & {"h", "hh"}:
        step = 3600000
    else:
        step = 86400000
    remaining = _round_to(seconds * 1000, step)
    shown = {"d": "d" in tokens, "h": bool(tokens & {"h", "hh"}), "m": bool(tokens & {"m", "mm"})}
    days = hours = minutes = 0
    for unit in ("d", "h", "m"):
        if shown[unit]:
            count, remaining = divmod(remaining, _UNITS[unit])
            if unit == "d":
                days = count
            elif unit == "h":
                hours = count
            else:
                minutes = count
    secs, millis = divmod(remaining, 1000)
    values = {"d": f"{days}", "h": f"{hours}", "hh": f"{hours:02d}", "m": f"{minutes}", "mm": f"{minutes:02d}",
              "s": f"{secs}", "ss": f"{secs:02d}", "ms": f"{millis:03d}",
              "s1": f"{secs + millis / 1000:.1f}", "s2": f"{secs + millis / 1000:.2f}"}
    return _TOKEN.sub(lambda found: values[found.group(1)], template)


def format_duration(seconds: float, style: str = "auto") -> str:
    """``seconds`` written by ``style`` (a preset name or a template); an unusable style is read as auto."""
    seconds = max(0.0, float(seconds)) if seconds == seconds else 0.0
    text = (style or "auto").strip()
    if text == "clock":
        return _clock(seconds)
    if text == "seconds":
        return _seconds(seconds)
    if text == "words":
        return _words(seconds)
    if text != "auto" and check_style(text) is None:
        return _template(seconds, text)
    return _auto(seconds)


@dataclass
class Step:
    name: str
    depth: int
    seconds: float


class Timer:
    """The clock of one build: ``elapsed()`` since the start, and the named steps
    that ran, in the order they began, each with its depth (a step inside a step)."""

    def __init__(self, clock=None):
        self._clock = clock
        self.started = self.now()
        self.steps: list[Step] = []
        self._depth = 0

    def now(self) -> float:
        return (self._clock or CLOCK)()

    def elapsed(self) -> float:
        return max(0.0, self.now() - self.started)

    @contextmanager
    def step(self, name: str):
        began, depth = self.now(), self._depth
        entry = Step(name, depth, 0.0)
        self.steps.append(entry)               # in the order they began, so a step stands above the steps inside it
        self._depth += 1
        try:
            yield
        finally:
            self._depth = depth
            entry.seconds = max(0.0, self.now() - began)
