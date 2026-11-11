"""Where a Markdown document refers to image files: `![alt](path)`, raw LaTeX `\\includegraphics{path}` and
`\\includesvg{path}`. Code, comments and the front matter are not looked at."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

IMAGE_RE = re.compile(r"!\[")
DEFINITION_RE = re.compile(r"^ {0,3}\[((?:[^\]\\]|\\.)+)\]:\s*")
GRAPHICS_RE = re.compile(r"""\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}""")
SVG_RE = re.compile(r"""\\includesvg\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}""")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")


@dataclass(frozen=True)
class ImageReference:
    kind: str                # markdown | graphics | includesvg
    path: str                # Pandoc destination (raw LaTeX paths as written)
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


def _label(text: str) -> str:
    return " ".join(text.split()).casefold()


def _destination(text: str, start: int, inline: bool) -> tuple[str, int] | None:
    """Read an angle-delimited or balanced Markdown destination."""
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return None
    if text[start] == "<":
        end = start + 1
        while end < len(text) and text[end] != ">":
            end += 2 if text[end] == "\\" and end + 1 < len(text) else 1
        if end >= len(text):
            return None
        path, end = text[start + 1:end], end + 1
    else:
        end, depth = start, 0
        while end < len(text):
            character = text[end]
            if character == "\\" and end + 1 < len(text):
                end += 2
                continue
            if character == "(":
                depth += 1
            elif character == ")":
                if depth == 0:
                    break
                depth -= 1
            elif character.isspace():
                break
            end += 1
        if depth or end == start:
            return None
        path = text[start:end]
    if inline:
        tail = text[end:]
        close = re.match(r"\s*(?:(?:\"[^\"]*\"|'[^']*'|\([^)]*\))\s*)?\)", tail)
        if close is None:
            return None
        end += close.end()
    path = re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])", r"\1", path)
    return html.unescape(path).replace(" ", "%20"), end


def _image_labels(line: str):
    """Read image labels with balanced, escapable brackets."""
    for match in IMAGE_RE.finditer(line):
        start, position, depth = match.end(), match.end(), 1
        while position < len(line):
            character = line[position]
            if character == "\\" and position + 1 < len(line):
                position += 2
                continue
            if character == "[":
                depth += 1
            elif character == "]":
                depth -= 1
                if not depth:
                    yield line[start:position], position + 1
                    break
            position += 1


def find_references(text: str) -> list[ImageReference]:
    """Every image the text refers to, in order."""
    found: list[ImageReference] = []
    lines = list(_content_lines(text.split("\n")))
    definitions = {}
    for offset, (index, line) in enumerate(lines):
        match = DEFINITION_RE.match(line)
        if match:
            destination = _destination(line, match.end(), False)
            if destination is None and not line[match.end():].strip() and offset + 1 < len(lines):
                next_index, next_line = lines[offset + 1]
                if next_index == index + 1:
                    destination = _destination(next_line, 0, False)
            if destination:
                definitions.setdefault(_label(match.group(1)), destination[0])
    for index, line in lines:
        for label, position in _image_labels(line):
            path = None
            if position < len(line) and line[position] == "(":
                destination = _destination(line, position + 1, True)
                if destination:
                    path = destination[0]
            else:
                if position < len(line) and line[position] == "[":
                    end = line.find("]", position + 1)
                    if end < 0:
                        continue
                    label = line[position + 1:end] or label
                path = definitions.get(_label(label))
            if path:
                found.append(ImageReference("markdown", path, index + 1))
        for kind, pattern in (("graphics", GRAPHICS_RE), ("includesvg", SVG_RE)):
            for match in pattern.finditer(line):
                found.append(ImageReference(kind, match.group(1).strip(), index + 1))
    return found
