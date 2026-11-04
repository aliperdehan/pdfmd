"""Where a Markdown document refers to image files: `![alt](path)`, raw LaTeX `\\includegraphics{path}` and
`\\includesvg{path}`. Code, comments and the front matter are not looked at."""

from __future__ import annotations

import re
from dataclasses import dataclass

MARKDOWN_RE = re.compile(r"""!\[(?:[^\]\\]|\\.)*\]\(\s*(?:<([^>]+)>|([^)\s]+))(?:\s+(?:"[^"]*"|'[^']*'))?\s*\)""")
GRAPHICS_RE = re.compile(r"""\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}""")
SVG_RE = re.compile(r"""\\includesvg\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}""")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")


@dataclass(frozen=True)
class ImageReference:
    kind: str                # markdown | graphics | includesvg
    path: str                # as written
    line: int                # 1-based

    @property
    def is_svg(self) -> bool:
        return self.path.lower().split("?")[0].endswith(".svg") or self.kind == "includesvg"

    @property
    def remote(self) -> bool:
        return bool(re.match(r"^(?:https?|ftp)://", self.path, re.IGNORECASE)) or self.path.startswith("data:")


def _content_lines(lines: list[str]):
    """(index, line) outside the front matter, fenced code and HTML comments."""
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                start = index + 1
                break
    fence = None
    comment = False
    for index in range(start, len(lines)):
        line = lines[index]
        if comment:
            comment = "-->" not in line
            continue
        match = FENCE_RE.match(line)
        if fence:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= fence[1] and not match.group(2).strip():
                fence = None
            continue
        if match:
            fence = (match.group(1)[0], len(match.group(1)))
            continue
        if "<!--" in line and "-->" not in line.split("<!--", 1)[1]:
            comment = True
            continue
        yield index, line


def find_references(text: str) -> list[ImageReference]:
    """Every image the text refers to, in order."""
    found: list[ImageReference] = []
    lines = text.split("\n")
    for index, line in _content_lines(lines):
        if "![" not in line and "\\include" not in line:
            continue
        for kind, pattern in (("markdown", MARKDOWN_RE), ("graphics", GRAPHICS_RE), ("includesvg", SVG_RE)):
            for match in pattern.finditer(line):
                path = next(group for group in match.groups() if group)
                found.append(ImageReference(kind, path.strip(), index + 1))
    return found
