"""Block identifiers and visible inline tags in the Obsidian flavour."""

from __future__ import annotations

import re

from .comments import _PROTECTED, _indented_code


_CODE_IN_CONTAINER = (
    r"(?P<container_fence>^(?:[ \t]*>[ \t]?)+[ \t]*(?P<quote_mark>`{3,}|~{3,})[^\n]*\n"
    r".*?(?:^(?:[ \t]*>[ \t]?)+[ \t]*(?P=quote_mark)[`~]*[ \t]*\r?$|^(?![ \t]*>)|\Z))"
)
_LINK_OR_RAW = (
    r"(?P<literal>!?\[\[[^\n]*?\]\](?:\([^\n]*?\))?|"
    r"!?\[[^\[\]\n]*\](?:\([^\n]*?\)|\[[^\n]*?\]|\{[^\n]*?\})|"
    r"</?[A-Za-z][^<>\n]*>|(?:[A-Za-z][\w+.-]*://|www\.)[^\s<>]+)"
)
_SYNTAX = re.compile(
    _PROTECTED + "|" + _CODE_IN_CONTAINER + "|" + _LINK_OR_RAW
    + r"|(?P<block>[ \t]+\^(?P<identifier>[A-Za-z0-9-]+)[ \t]*(?=\r?$))"
    + r"|(?P<tag>(?<![\w/#\\&])#[\w-]+(?:/[\w-]+)*)", re.MULTILINE | re.DOTALL
)
_QUOTE = re.compile(r"^(?:[ \t]*>[ \t]?)*")
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-+*]|[0-9]+[.)])[ \t]+")
_NON_PARAGRAPH = re.compile(r"^[ \t]*(?:#{1,6}(?:[ \t]|$)|\||`{3,}|~{3,}|\[\^?[^\]]+\]:)")
_NEXT_BLOCK = re.compile(r"^[ \t]*(?:#{1,6}(?:[ \t]|$)|`{3,}|~{3,}|:::+)")
_SETEXT = re.compile(r"^[ \t]*[=-]+[ \t]*$")


def _line_body(line):
    content = _QUOTE.sub("", line, count=1)
    return _LIST_ITEM.sub("", content, count=1)


def _paragraph_end(text, end, prefix):
    if not prefix.strip():
        return False
    newline = text.find("\n", end)
    following = text[newline + 1:].split("\n", 1)[0] if newline != -1 else ""
    body = _QUOTE.sub("", following, count=1).rstrip("\r")
    if _SETEXT.fullmatch(body):
        return False
    return not body.strip() or bool(_NEXT_BLOCK.match(body) or _LIST_ITEM.match(body))


def syntax_matches(text):
    """Find source markers without entering protected Markdown constructs."""
    spans = iter(_indented_code(text))
    span = next(spans, None)
    cursor = 0
    while match := _SYNTAX.search(text, cursor):
        while span and span[1] <= match.start():
            span = next(spans, None)
        if span and span[0] <= match.start() < span[1]:
            cursor = max(match.end(), span[1]) if match.lastgroup in ("front", "fence", "container_fence") else span[1]
            continue
        cursor = match.end()
        if match.lastgroup not in ("block", "tag"):
            continue
        start = text.rfind("\n", 0, match.start()) + 1
        prefix = _line_body(text[start:match.start()])
        stop = text.find("\n", start)
        line = _line_body(text[start:stop if stop != -1 else len(text)])
        if _NON_PARAGRAPH.match(line) and (match.lastgroup == "block" or not line.lstrip().startswith("|")):
            continue
        if match.lastgroup == "block" and not _paragraph_end(text, match.end(), prefix):
            continue
        if match.lastgroup == "tag" and not any(char.isalpha() or char == "_" for char in match[0]):
            continue
        yield match


def write_syntax(text, matches, block_ids):
    """Write standard Pandoc spans so the same source works without bundled Lua."""
    pieces = []
    start = 0
    for match in matches:
        pieces.append(text[start:match.start()])
        if match.lastgroup == "tag":
            pieces.append(f"[{match[0]}]{{.tag}}")
        else:
            identifier = block_ids.get(match.start())
            pieces.append(f" []{{#{identifier}}}" if identifier else match[0])
        start = match.end()
    pieces.append(text[start:])
    return "".join(pieces)


def without_block_ids(text):
    """Keep the native renderer's prose when it cannot place Pandoc anchors."""
    for match in reversed(list(syntax_matches(text))):
        if match.lastgroup == "block":
            text = text[:match.start()] + text[match.end():]
    return text
