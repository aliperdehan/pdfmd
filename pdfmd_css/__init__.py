"""CSS for the writers that do not read it (v3.28.41): a small reader of a style sheet, and the part of it that means
something to LaTeX, Typst, Word and the rest, as the Pandoc variables those take.

`translate(text)` returns what a style sheet asks of the page and the body (the paper, its margins, the body's font, size and
line spacing, the paragraph indent, the colour of links, the font of code) as Pandoc variables, and names the properties it
did not use. It is a v1 on purpose: a CSS cascade has no counterpart in LaTeX, so only the rules that say it plainly
(`@page`, `html`/`body`/`:root`, `a`, `code`/`pre`) count, the last one wins. A media query is read as a browser prints it
(v3.29.8): `print` and `all` apply, `screen` does not, a comma is "or", `only` and `not` count, `(orientation: ...)` is read
against the sheet's own `@page` size, any other condition (a width, a resolution, a colour scheme) is not for the page and is
named. Headings (`h1`-`h6`: colour, size, family, weight, style) are kept for LaTeX, which uses them only when the document does
not format its headings itself; table and everything else are named as not used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PAPER_NAMES = {"a3": "a3", "a4": "a4", "a5": "a5", "a6": "a6", "b4": "b4", "b5": "b5", "letter": "letter", "legal": "legal",
               "ledger": "ledger", "tabloid": "tabloid"}
GENERIC_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-serif", "ui-sans-serif",
                    "ui-monospace", "inherit", "initial", "unset", "emoji", "math", "fangsong"}
LENGTH_RE = re.compile(r"^(-?\d*\.?\d+)(cm|mm|in|pt|px|pc|em|rem|%)?$")
BODY_SELECTORS = {"html", "body", ":root", "html, body", "body, html"}
HEADING_RE = re.compile(r"h([1-6])")
HEADING_PROPERTIES = ("color", "font-size", "font-family", "font-weight", "font-style")
LINK_SELECTORS = {"a", "a:link", "a:visited", "a:any-link", "a:hover"}
CODE_SELECTORS = {"code", "pre", "pre code", "tt", "kbd", "samp", "code, pre", "pre, code"}


@dataclass
class Rule:
    media: str
    selector: str
    declarations: dict[str, str]


@dataclass
class Translation:
    variables: list[str] = field(default_factory=list)       # "key=value", in the form -V takes
    used: list[tuple[str, list[str]]] = field(default_factory=list)   # ("body font-size 11pt", ["fontsize=11pt"])
    ignored: list[str] = field(default_factory=list)         # "h1 color", "table border-collapse"
    headings: dict[int, dict[str, str]] = field(default_factory=dict)    # 1..6 -> {"color": "#036", "font-size": "1.6em", ...}


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def parse(text: str, media: str = "") -> list[Rule]:
    """The rules of a style sheet, in order, with the media query each sits in. At-rules other than @media and @page are
    skipped, with what they hold."""
    text = strip_comments(text)
    rules: list[Rule] = []
    position = 0
    while position < len(text):
        brace = text.find("{", position)
        semicolon = text.find(";", position)
        if brace < 0:
            break
        if 0 <= semicolon < brace:                                  # @import ...; @charset ...;
            position = semicolon + 1
            continue
        prelude = text[position:brace].strip()
        depth, end = 1, brace + 1
        while end < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[end], 0)
            end += 1
        body = text[brace + 1:end - 1]
        position = end
        if prelude.startswith("@media"):
            inner = prelude[len("@media"):].strip()
            rules += parse(body, f"{media} and {inner}" if media else inner)
        elif prelude.startswith("@page"):
            rules.append(Rule(media, "@page", declarations(body)))
        elif prelude.startswith("@"):                                # @font-face, @supports, @keyframes ...
            continue
        else:
            rules.append(Rule(media, re.sub(r"\s+", " ", prelude), declarations(body)))
    return rules


def declarations(block: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for item in block.split(";"):
        name, separator, value = item.partition(":")
        if separator and name.strip():
            found[name.strip().lower()] = re.sub(r"\s*!important\s*$", "", value.strip(), flags=re.IGNORECASE)
    return found


def applies(media: str, landscape: bool = False, unknown: list[str] | None = None) -> bool:
    """Whether a rule in this media query is for the page. `print` and `all` are; `screen` and the other media types are
    not; a comma is "or"; `only X` is X, `not X` is its opposite; `(orientation: landscape|portrait)` is read against the
    sheet's own @page size; a feature of the screen or of a size (`(min-width: 600px)`) is not for the page, and is added to
    `unknown` when that list is given."""
    if not media.strip():
        return True

    def one(query: str) -> bool:
        words = query.strip().lower()
        negate = False
        if words.startswith("not "):
            negate, words = True, words[4:]
        elif words.startswith("only "):
            words = words[5:]
        result = True
        for part in (item.strip() for item in re.split(r"\s+and\s+", words)):
            if part in ("print", "all", "(color)", "(monochrome)"):
                continue
            found = re.fullmatch(r"\(\s*orientation\s*:\s*(landscape|portrait)\s*\)", part)
            if found:
                result = result and ((found.group(1) == "landscape") == landscape)
                continue
            if not part.startswith("(") and part in ("screen", "speech", "tty", "tv", "projection", "handheld", "braille", "embossed"):
                result = False
                continue
            if unknown is not None and part.startswith("("):
                unknown.append(part)
            result = False
        return result != negate if negate else result

    return any(one(query) for query in media.split(","))


def length_points(value: str) -> float | None:
    found = LENGTH_RE.match(value.strip().lower())
    if not found:
        return None
    number, unit = float(found.group(1)), found.group(2) or ""
    factor = {"pt": 1.0, "px": 0.75, "pc": 12.0, "in": 72.0, "cm": 72.0 / 2.54, "mm": 72.0 / 25.4}.get(unit)
    return number * factor if factor is not None else None


def tidy_length(value: str) -> str | None:
    """A CSS length LaTeX's geometry and Typst both read (cm, mm, in, pt), a px as pt, else None."""
    found = LENGTH_RE.match(value.strip().lower())
    if not found:
        return None
    number, unit = found.group(1), found.group(2) or ""
    if unit in ("cm", "mm", "in", "pt"):
        return f"{number}{unit}"
    if unit == "px":
        return f"{round(float(number) * 0.75, 2):g}pt"
    return "0pt" if float(number) == 0 else None


def first_family(value: str) -> str | None:
    for item in re.split(r",", value):
        name = item.strip().strip("\"'").strip()
        if name and name.lower() not in GENERIC_FAMILIES:
            return name
    return None


def translate(text: str) -> Translation:
    out = Translation()
    chosen: dict[str, tuple[str, str]] = {}            # variable -> (value, what said it): the last rule wins
    margins: dict[str, str] = {}
    landscape = False
    ignored: dict[str, None] = {}

    def choose(key: str, value: str, said: str) -> None:
        chosen[key] = (value, said)

    rules = parse(text)
    sheet_landscape = any(rule.selector == "@page" and "landscape" in rule.declarations.get("size", "").lower().split()
                          and applies(rule.media) for rule in rules)
    headings = out.headings
    for rule in rules:
        conditions: list[str] = []
        if not applies(rule.media, sheet_landscape, conditions):
            ignored[f"{rule.selector} (@media {rule.media})" + (f": {', '.join(conditions)} is not for a printed page"
                                                                if conditions else "")] = None
            continue
        selector, found = rule.selector, rule.declarations
        levels = [HEADING_RE.fullmatch(item.strip()) for item in selector.split(",")]
        if levels and all(levels):
            for level in (int(item.group(1)) for item in levels):
                for name, value in found.items():
                    if name in HEADING_PROPERTIES:
                        headings.setdefault(level, {})[name] = value
                    else:
                        ignored[f"h{level} {name}"] = None
            continue
        if selector == "@page":
            for name, value in found.items():
                if name == "size":
                    words = value.lower().split()
                    paper = next((PAPER_NAMES[word] for word in words if word in PAPER_NAMES), None)
                    if paper:
                        choose("papersize", paper, f"@page size {value}")
                    else:
                        ignored[f"@page size {value}"] = None
                    landscape = "landscape" in words if words else landscape
                elif name == "margin":
                    sides = [tidy_length(item) for item in value.split()]
                    if sides and None not in sides and len(sides) <= 4:
                        top, right, bottom, left = {1: lambda s: (s[0],) * 4, 2: lambda s: (s[0], s[1], s[0], s[1]),
                                                    3: lambda s: (s[0], s[1], s[2], s[1]), 4: lambda s: tuple(s)}[len(sides)](sides)
                        margins.update(top=top, right=right, bottom=bottom, left=left)      # type: ignore[arg-type]
                    else:
                        ignored[f"@page margin {value}"] = None
                elif name in ("margin-top", "margin-right", "margin-bottom", "margin-left"):
                    length = tidy_length(value)
                    if length:
                        margins[name.split("-")[1]] = length
                    else:
                        ignored[f"@page {name} {value}"] = None
                else:
                    ignored[f"@page {name}"] = None
            continue
        if selector in BODY_SELECTORS:
            for name, value in found.items():
                if name == "font-family":
                    family = first_family(value)
                    if family:
                        choose("mainfont", family, f"{selector} font-family {value}")
                elif name == "font-size":
                    points = length_points(value)
                    if points is not None and abs(points * 2 - round(points * 2)) < 0.01 and round(points) in (10, 11, 12):
                        choose("fontsize", f"{round(points)}pt", f"{selector} font-size {value}")
                    else:
                        ignored[f"{selector} font-size {value} (LaTeX's body takes 10, 11 or 12pt)"] = None
                elif name == "line-height":
                    number = value.strip()
                    if re.fullmatch(r"\d*\.?\d+", number):
                        choose("linestretch", number, f"{selector} line-height {value}")
                    elif re.fullmatch(r"\d*\.?\d+%", number):
                        choose("linestretch", f"{float(number[:-1]) / 100:g}", f"{selector} line-height {value}")
                    else:
                        ignored[f"{selector} line-height {value}"] = None
                elif name == "text-indent":
                    if not LENGTH_RE.match(value.strip().lower()):
                        ignored[f"{selector} text-indent {value}"] = None
                    elif float(LENGTH_RE.match(value.strip().lower()).group(1)) != 0:
                        choose("indent", "true", f"{selector} text-indent {value}")
                else:
                    ignored[f"{selector} {name}"] = None
        elif selector in LINK_SELECTORS:
            for name, value in found.items():
                if name == "color" and re.fullmatch(r"#[0-9a-fA-F]{6}|[a-zA-Z]+", value.strip()):
                    colour = value.strip()
                    choose("linkcolor", f"[HTML]{{{colour[1:].upper()}}}" if colour.startswith("#") else colour.lower(),
                           f"{selector} color {value}")
                else:
                    ignored[f"{selector} {name}"] = None
        elif selector in CODE_SELECTORS:
            for name, value in found.items():
                if name == "font-family":
                    family = first_family(value)
                    if family:
                        choose("monofont", family, f"{selector} font-family {value}")
                else:
                    ignored[f"{selector} {name}"] = None
        else:
            for name in found:
                ignored[f"{selector} {name}"] = None
    for key, (value, said) in chosen.items():
        out.variables.append(f"{key}={value}")
        out.used.append((said, [f"{key}={value}"]))
        if key == "linkcolor":
            out.variables.append("colorlinks=true")
    if margins:
        sides = {side: margins[side] for side in ("top", "right", "bottom", "left") if side in margins}
        if len(sides) == 4 and len(set(sides.values())) == 1:
            out.variables.append(f"geometry:margin={sides['top']}")
            out.used.append((f"@page margin {sides['top']}", [f"geometry:margin={sides['top']}"]))
        else:
            for side, value in sides.items():
                out.variables.append(f"geometry:{side}={value}")
            out.used.append(("@page margin", [f"geometry:{side}={value}" for side, value in sides.items()]))
    if landscape:
        out.variables.append("geometry:landscape")
        out.used.append(("@page size landscape", ["geometry:landscape"]))
    out.ignored = list(ignored)
    return out
