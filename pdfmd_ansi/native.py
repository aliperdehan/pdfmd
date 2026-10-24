"""The fallback when there is no Pandoc: Markdown -> the built-in parser (pdfmd_inkmd) -> a Pandoc-shaped JSON AST.

The renderer only knows Pandoc's JSON, so this module translates the other parser's tree into it. Less is understood than
with Pandoc (no citations, filters, footnotes, definition lists or metadata files) but a plain report reads the same.
"""

from __future__ import annotations

import re
from typing import List

MATH_RE = re.compile(r"\$\$(.+?)\$\$|(?<![\\$])\$(?=\S)([^$\n]*?\S)\$(?![\d$])", re.S)
FRONT_RE = re.compile(r"\A---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.S)


def _tag(kind: str, content=None) -> dict:
    return {"t": kind} if content is None else {"t": kind, "c": content}


def _text(content: str) -> List[dict]:
    """Text with `$..$` / `$$..$$` cut out as math, and a newline kept as a soft break."""
    out: List[dict] = []

    def plain(piece: str) -> None:
        for index, part in enumerate(piece.split("\n")):
            if index:
                out.append(_tag("SoftBreak"))
            if part:
                out.append(_tag("Str", part))

    position = 0
    for found in MATH_RE.finditer(content):
        plain(content[position:found.start()])
        display = found.group(1) is not None
        out.append(_tag("Math", [_tag("DisplayMath" if display else "InlineMath"), (found.group(1) or found.group(2)).strip()]))
        position = found.end()
    plain(content[position:])
    return out


def _inlines(items) -> List[dict]:
    out: List[dict] = []
    for item in items:
        name = type(item).__name__
        if name == "Text":
            out += _text(item.content)
        elif name in ("Strong", "Emphasis", "Strikethrough", "Underline", "Subscript", "Superscript"):
            kind = {"Strong": "Strong", "Emphasis": "Emph", "Strikethrough": "Strikeout"}.get(name, name)
            out.append(_tag(kind, _inlines(item.inlines)))
        elif name in ("Mark", "Kbd"):
            out += _inlines(item.inlines)
        elif name == "Code":
            out.append(_tag("Code", [["", [], []], item.content]))
        elif name == "Link":
            out.append(_tag("Link", [["", [], []], _inlines(item.inlines), [item.url, item.title]]))
        elif name == "AutoLink":
            out.append(_tag("Link", [["", [], []], [_tag("Str", item.text or item.url)], [item.url, ""]]))
        elif name == "Image":
            out.append(_tag("Image", [["", [], []], _inlines(item.inlines), [item.url, item.title]]))
        elif name == "HardBreak":
            out.append(_tag("LineBreak"))
        elif name == "HtmlInline" and re.fullmatch(r"<br\s*/?>", item.raw.strip()):
            out.append(_tag("LineBreak"))
    return out


def _align(value) -> dict:
    return _tag({"left": "AlignLeft", "right": "AlignRight", "center": "AlignCenter"}.get(value or "", "AlignDefault"))


def _row(cells, alignments) -> list:
    return [["", [], []], [[["", [], []], _align(alignments[index] if index < len(alignments) else None), 1, 1,
                            [_tag("Plain", _inlines(cell.inlines))]] for index, cell in enumerate(cells)]]


def _blocks(items) -> List[dict]:
    out: List[dict] = []
    for item in items:
        name = type(item).__name__
        if name == "Paragraph":
            out.append(_tag("Para", _inlines(item.inlines)))
        elif name == "Heading":
            out.append(_tag("Header", [item.level, ["", [], []], _inlines(item.inlines)]))
        elif name == "CodeBlock":
            info = (item.info or "").split()
            out.append(_tag("CodeBlock", [["", info[:1], []], item.content]))
        elif name == "BlockQuote":
            out.append(_tag("BlockQuote", _blocks(item.blocks)))
        elif name == "ThematicBreak":
            out.append(_tag("HorizontalRule"))
        elif name == "List":
            entries = []
            for entry in item.items:
                blocks = _blocks(entry.blocks)
                if item.tight:
                    blocks = [_tag("Plain", block["c"]) if block["t"] == "Para" else block for block in blocks]
                if entry.task is not None:
                    box = _tag("Str", "☒ " if entry.task else "☐ ")
                    if blocks and blocks[0]["t"] in ("Para", "Plain"):
                        blocks[0] = _tag(blocks[0]["t"], [box, *blocks[0]["c"]])
                    else:
                        blocks.insert(0, _tag("Plain", [box]))
                entries.append(blocks)
            if item.ordered:
                out.append(_tag("OrderedList", [[item.start, _tag("Decimal"), _tag("Period")], entries]))
            else:
                out.append(_tag("BulletList", entries))
        elif name == "Table":
            columns = [[_align(item.alignments[index] if index < len(item.alignments) else None), _tag("ColWidthDefault")]
                       for index in range(len(item.headers))]
            body = [["", [], []], 0, [], [_row(row, item.alignments) for row in item.rows]]
            out.append(_tag("Table", [["", [], []], [None, []], columns,
                                      [["", [], []], [_row(item.headers, item.alignments)]], [body], [["", [], []], []]]))
    return out


def from_markdown(text: str) -> dict:
    """A Pandoc-shaped JSON AST of Markdown text, made without Pandoc."""
    from pdfmd_inkmd.parser import parse

    meta: dict = {}
    front = FRONT_RE.match(text)
    if front:
        text = text[front.end():]
        found = re.search(r"^title:\s*(.+?)\s*$", front.group(1), re.M)
        if found:
            meta["title"] = _tag("MetaString", found.group(1).strip("\"'"))
    return {"pandoc-api-version": [1, 23], "meta": meta, "blocks": _blocks(parse(text).blocks)}
