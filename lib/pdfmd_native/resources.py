"""Locate complete image destinations for Calibre's scratch Markdown."""

import re

from pdfmd_images.scan import _destination, _image_labels


def _span(text, start, inline):
    if _destination(text, start, inline) is None:
        return None
    while start < len(text) and text[start].isspace():
        start += 1
    angle = text[start] == '<'
    if angle:
        start += 1
    end, depth = start, 0
    while end < len(text):
        char = text[end]
        if char == '\\' and end + 1 < len(text):
            end += 2
            continue
        if angle:
            if char == '>':
                break
        elif char == '(':
            depth += 1
        elif char == ')':
            if not depth:
                break
            depth -= 1
        elif char.isspace():
            break
        end += 1
    return start, end


def image_destinations(text):
    """Return destination spans in visible Markdown and HTML image references."""
    spans = []
    references = set()
    label = lambda value: ' '.join(value.split()).casefold()
    for name, position in _image_labels(text):
        if position < len(text) and text[position] == '(':
            span = _span(text, position + 1, True)
            if span:
                spans.append(span)
        elif position < len(text) and text[position] == '[':
            end = text.find(']', position + 1)
            if end >= 0:
                references.add(label(text[position + 1:end] or name))
        else:
            references.add(label(name))
    for match in re.finditer(r'(?m)^ {0,3}\[([^]\n]+)\]:[ \t]*', text):
        if label(match.group(1)) in references:
            span = _span(text, match.end(), False)
            if span:
                spans.append(span)
    spans.extend(match.span(1) for match in re.finditer(r'''<img\b[^>]*?\bsrc=["']([^"']+)["']''', text, re.IGNORECASE))
    return spans
