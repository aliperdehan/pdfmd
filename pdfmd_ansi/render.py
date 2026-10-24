"""Pandoc's JSON AST -> text for a terminal (bold, italic, code, box-drawn tables, lists, quotes), as a pure function.

    render(document, width=100, color=True, hyperlinks=False, math=None) -> str

`document` is what `pandoc -t json` writes (or `native.from_markdown` makes without Pandoc). `math(tex, display)` may return
lines of `(text, kind)` pieces (kind "", "i" or "b"); without it a formula is shown as its TeX source. No other module
of pdfmd is imported: `qwen` and a later full-screen reader can use this package alone.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .text import INF, Line, Run, clean, emit, line_width, pad, text_width, with_style, wrap

MathFunction = Callable[[str, bool], Optional[List[List[Tuple[str, str]]]]]

SUPERSCRIPTS = {**dict(zip("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")), "−": "⁻",
                **dict(zip("abcdefghjklmoprstuvwxyz", "ᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻ"))}
SUBSCRIPTS = {**dict(zip("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")), "−": "₋",
              **dict(zip("aehijklmnoprstuvx", "ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"))}
BULLETS = ("•", "◦", "▪")
HEADINGS = {1: ("b", "u"), 2: ("b",), 3: ("b", "i")}
ROMAN = (("m", 1000), ("cm", 900), ("d", 500), ("cd", 400), ("c", 100), ("xc", 90), ("l", 50), ("xl", 40),
         ("x", 10), ("ix", 9), ("v", 5), ("iv", 4), ("i", 1))


def script(text: str, up: bool) -> str:
    """Super- or subscript as Unicode when every character has one, else `^x` / `_(xy)`."""
    table = SUPERSCRIPTS if up else SUBSCRIPTS
    if text and all(char in table for char in text):
        return "".join(table[char] for char in text)
    return ("^" if up else "_") + (text if len(text) == 1 else f"({text})")


def number_name(value: int, style: str) -> str:
    if style in ("LowerAlpha", "UpperAlpha"):
        name = ""
        number = value
        while number > 0:
            number, rest = divmod(number - 1, 26)
            name = chr(97 + rest) + name
        return name.upper() if style == "UpperAlpha" else name
    if style in ("LowerRoman", "UpperRoman"):
        name, number = "", value
        for symbol, size in ROMAN:
            while number >= size:
                name += symbol
                number -= size
        return name.upper() if style == "UpperRoman" else name
    return str(value)


def plain(inlines: Sequence[dict]) -> str:
    """The text of inline elements, with no style."""
    out: List[str] = []
    for item in inlines:
        kind, content = item["t"], item.get("c")
        if kind == "Str":
            out.append(content)
        elif kind in ("Space", "SoftBreak"):
            out.append(" ")
        elif kind == "LineBreak":
            out.append("\n")
        elif kind in ("Code",):
            out.append(content[1])
        elif kind == "Math":
            out.append(content[1])
        elif kind in ("Emph", "Strong", "Strikeout", "Superscript", "Subscript", "SmallCaps", "Underline"):
            out.append(plain(content))
        elif kind in ("Span",):
            out.append(plain(content[1]))
        elif kind in ("Link", "Image"):
            out.append(plain(content[1]))
        elif kind == "Quoted":
            quote = "“”" if content[0]["t"] == "DoubleQuote" else "‘’"
            out.append(quote[0] + plain(content[1]) + quote[1])
        elif kind == "Cite":
            out.append(plain(content[1]))
    return "".join(out)


def meta_inlines(value: Optional[dict]) -> List[dict]:
    """A metadata value as inline elements."""
    if not value:
        return []
    kind, content = value["t"], value.get("c")
    if kind == "MetaInlines":
        return content
    if kind == "MetaString":
        return [{"t": "Str", "c": content}]
    if kind == "MetaBool":
        return [{"t": "Str", "c": "true" if content else "false"}]
    if kind == "MetaBlocks":
        parts: List[dict] = []
        for block in content:
            if block["t"] in ("Para", "Plain"):
                parts += ([{"t": "Space"}] if parts else []) + block["c"]
        return parts
    if kind == "MetaMap":
        for key in ("name", "family", "text"):
            if key in content:
                return meta_inlines(content[key])
    return []


class Renderer:
    def __init__(self, width: int = 100, color: bool = True, hyperlinks: bool = False,
                 math: Optional[MathFunction] = None, title: bool = True):
        self.width = max(20, width)
        self.color = color
        self.hyperlinks = hyperlinks and color
        self.math = math
        self.title = title
        self.notes: List[List[dict]] = []
        self.depth = 0
        self.skipped = 0                      # raw pieces no terminal can show (LaTeX, Word XML), counted, not hidden

    # --- inline elements --------------------------------------------------------------------------------------------

    def inlines(self, items: Sequence[dict], style: Tuple[str, ...] = ()) -> List[Run]:
        runs: List[Run] = []
        for item in items:
            runs += self.inline(item, style)
        return runs

    def inline(self, item: dict, style: Tuple[str, ...]) -> List[Run]:
        kind, content = item["t"], item.get("c")
        if kind == "Str":
            return [Run(clean(content), style)]
        if kind in ("Space", "SoftBreak"):
            return [Run(" ", style)]
        if kind == "LineBreak":
            return [Run("\n", style)]
        if kind == "Emph":
            return self.inlines(content, (*style, "i"))
        if kind == "Strong":
            return self.inlines(content, (*style, "b"))
        if kind == "Strikeout":
            return self.inlines(content, (*style, "s"))
        if kind == "Underline":
            return self.inlines(content, (*style, "u"))
        if kind in ("SmallCaps", "Span"):
            return self.inlines(content if kind == "SmallCaps" else content[1], style)
        if kind in ("Superscript", "Subscript"):
            return [Run(script(clean(plain(content)), kind == "Superscript"), style)]
        if kind == "Quoted":
            quote = "“”" if content[0]["t"] == "DoubleQuote" else "‘’"
            return [Run(quote[0], style), *self.inlines(content[1], style), Run(quote[1], style)]
        if kind == "Cite":
            return self.inlines(content[1], style)
        if kind == "Code":
            return [Run(clean(content[1]).replace("\n", " "), (*style, "code"))]
        if kind == "Math":
            return self.inline_math(content[1], content[0]["t"] == "DisplayMath", style)
        if kind == "RawInline":
            if content[0] in ("html", "html5") and re.fullmatch(r"<br\s*/?>", content[1].strip()):
                return [Run("\n", style)]
            self.skipped += 1
            return []
        if kind == "Link":
            return self.link(content, style)
        if kind == "Image":
            alt = clean(plain(content[1])).strip()
            label = f"[image: {alt}]" if alt else "[image]"
            return [Run(label, (*style, "i")), Run(f" ({clean(content[2][0])})", (*style, "dim"))]
        if kind == "Note":
            self.notes.append(content)
            return [Run(script(str(len(self.notes)), True), (*style, "dim"))]
        return []

    def link(self, content: list, style: Tuple[str, ...]) -> List[Run]:
        url = clean(content[2][0])
        body = self.inlines(content[1], (*style, "link", *(["a:" + url] if url else [])))
        shown = plain(content[1]).strip()
        if not url or url.startswith("#") or self.hyperlinks or shown in (url, url.replace("mailto:", "")):
            return body
        return [*body, Run(f" ({url})", (*style, "dim"))]

    def inline_math(self, tex: str, display: bool, style: Tuple[str, ...]) -> List[Run]:
        pieces = self.math(tex, display) if self.math else None
        if not pieces:
            return [Run(clean(tex), (*style, "code"))]
        runs: List[Run] = []
        for index, line in enumerate(pieces):
            if index:
                runs.append(Run("\n", style))
            runs += [Run(clean(text), (*style, *( (kind,) if kind else ()))) for text, kind in line]
        return runs

    # --- blocks -----------------------------------------------------------------------------------------------------

    def blocks(self, items: Sequence[dict], width: int) -> List[Line]:
        out: List[Line] = []
        previous = ""
        for item in items:
            lines = self.block(item, width)
            if not lines:
                continue
            if out and previous != "Plain":
                out.append([])
            out += lines
            previous = item["t"]
        return out

    def block(self, item: dict, width: int) -> List[Line]:
        kind, content = item["t"], item.get("c")
        if kind in ("Para", "Plain"):
            if len(content) == 1 and content[0]["t"] == "Math" and content[0]["c"][0]["t"] == "DisplayMath":
                return centred(wrap(self.inlines(content), width), width)       # a formula on its own is centred
            return wrap(self.inlines(content), width)
        if kind == "Header":
            return wrap(self.inlines(content[2], HEADINGS.get(content[0], ("b", "i"))), width)
        if kind == "CodeBlock":
            return self.code_block(content[1], width)
        if kind == "BlockQuote":
            inner = self.blocks(content, width - 2)
            return [[Run("│ ", ("dim",)), *line] if line else [Run("│", ("dim",))] for line in inner]
        if kind == "BulletList":
            return self.bullets(content, width)
        if kind == "OrderedList":
            return self.ordered(content, width)
        if kind == "DefinitionList":
            return self.definitions(content, width)
        if kind == "HorizontalRule":
            return [[Run("─" * min(width, 100), ("dim",))]]
        if kind == "Table":
            return self.table(content, width)
        if kind == "Div":
            return self.blocks(content[1], width)
        if kind == "Figure":
            return self.figure(content, width)
        if kind == "LineBlock":
            out: List[Line] = []
            for line in content:
                out += wrap(self.inlines(line), width)
            return out
        if kind == "RawBlock":
            if content[0] in ("html", "html5") and re.match(r"\s*<hr\b", content[1]):
                return [[Run("─" * min(width, 100), ("dim",))]]
            self.skipped += 1
        return []

    def code_block(self, text: str, width: int) -> List[Line]:
        lines = clean(text.expandtabs(4)).rstrip("\n").split("\n")
        return [[Run("  " + line, ("code",))] if line else [] for line in lines]

    def item(self, blocks: Sequence[dict], width: int, marker: str, size: int) -> List[Line]:
        self.depth += 1
        inner = self.blocks(blocks, max(10, width - size))
        self.depth -= 1
        if not inner:
            return [[Run(marker)]]
        return [[Run(marker if index == 0 else " " * size), *line] if line else [] for index, line in enumerate(inner)]

    @staticmethod
    def loose(items: Sequence[Sequence[dict]]) -> bool:
        return any(block["t"] == "Para" for entry in items for block in entry)

    def bullets(self, items: Sequence[Sequence[dict]], width: int) -> List[Line]:
        marker = BULLETS[self.depth % len(BULLETS)] + " "
        out: List[Line] = []
        for entry in items:
            if out and self.loose(items):
                out.append([])
            out += self.item(entry, width, marker, 2)
        return out

    def ordered(self, content: list, width: int) -> List[Line]:
        (start, style, delimiter), items = content
        style, delimiter = style["t"], delimiter["t"]
        names = [number_name(start + index, style) for index in range(len(items))]
        markers = [f"({name})" if delimiter == "TwoParens" else f"{name}{')' if delimiter == 'OneParen' else '.'}"
                   for name in names]
        size = max(text_width(marker) for marker in markers) + 1
        out: List[Line] = []
        for entry, marker in zip(items, markers):
            if out and self.loose(items):
                out.append([])
            out += self.item(entry, width, marker.rjust(size - 1) + " ", size)
        return out

    def definitions(self, items: list, width: int) -> List[Line]:
        out: List[Line] = []
        for term, definitions in items:
            if out:
                out.append([])
            out += wrap(self.inlines(term, ("b",)), width)
            for definition in definitions:
                out += [[Run("  "), *line] if line else [] for line in self.blocks(definition, width - 2)]
        return out

    def figure(self, content: list, width: int) -> List[Line]:
        caption = content[1][1]
        body = content[2]
        text = self.blocks(caption, width) if caption else []
        images = [part for block in body if block["t"] in ("Plain", "Para") for part in block["c"] if part["t"] == "Image"]
        if len(images) == 1 and len(body) == 1 and len(body[0]["c"]) == 1:
            url = clean(images[0]["c"][2][0])
            label = [Run("[figure] ", ("dim",)), *self.inlines(
                caption[0]["c"] if caption and caption[0]["t"] in ("Plain", "Para") else images[0]["c"][1], ("i",)),
                Run(f" ({url})", ("dim",))]
            return wrap(label, width)
        return [*self.blocks(body, width), *([[]] if text else []), *[with_style(line, "i") for line in text]]

    # --- tables -----------------------------------------------------------------------------------------------------

    @staticmethod
    def cell_align(cell_align: dict, column_align: dict) -> str:
        name = cell_align["t"] if cell_align["t"] != "AlignDefault" else column_align["t"]
        return {"AlignRight": "r", "AlignCenter": "c"}.get(name, "l")

    def grid(self, rows: list, columns: list) -> List[list]:
        """The rows as lists of ncols entries `(align, blocks)` or None (covered by a span): spans are placed, not merged."""
        occupied = set()
        grid = []
        for r, row in enumerate(rows):
            cells: list = [None] * len(columns)
            c = 0
            for cell in row[1]:
                while c < len(columns) and (r, c) in occupied:
                    c += 1
                if c >= len(columns):
                    break
                _, align, rowspan, colspan, blocks = cell
                cells[c] = (self.cell_align(align, columns[c][0]), blocks)
                for dr in range(rowspan):
                    for dc in range(colspan):
                        occupied.add((r + dr, c + dc))
                c += colspan
            grid.append(cells)
        return grid

    @staticmethod
    def words_width(lines: List[Line]) -> int:
        longest = 1
        for line in lines:
            for word in "".join(run.text for run in line).split(" "):
                longest = max(longest, text_width(word))
        return longest

    def table(self, content: list, width: int) -> List[Line]:
        _, caption, columns, head, bodies, foot = content
        head_rows = head[1]
        rows = head_rows + [row for body in bodies for row in body[2] + body[3]] + foot[1]
        count = len(columns)
        if not rows or not count:
            return []
        grid = self.grid(rows, columns)
        header_rows = len(head_rows)
        natural = [1] * count
        floor = [1] * count
        for cells in grid:
            for c, cell in enumerate(cells):
                if cell:
                    lines = self.blocks(cell[1], INF)
                    natural[c] = max(natural[c], *(line_width(line) for line in lines), 1)
                    floor[c] = max(floor[c], self.words_width(lines))
        available = width - 3 * count - 1
        widths = list(natural)
        for minimum in (lambda c: min(floor[c], natural[c]), lambda c: min(3, natural[c])):
            while sum(widths) > available:
                shrinkable = [c for c in range(count) if widths[c] > minimum(c)]
                if not shrinkable:
                    break
                widths[max(shrinkable, key=lambda c: widths[c])] -= 1
        edge = ("dim",)

        def rule(left: str, middle: str, right: str) -> Line:
            return [Run(left + middle.join("─" * (w + 2) for w in widths) + right, edge)]

        out: List[Line] = []
        if caption[1]:
            out += [with_style(line, "i") for line in self.blocks(caption[1], width)]
        out.append(rule("┌", "┬", "┐"))
        for r, cells in enumerate(grid):
            if r:
                out.append(rule("├", "┼", "┤"))
            rendered = []
            for c, cell in enumerate(cells):
                lines = self.blocks(cell[1], widths[c]) if cell else []
                if r < header_rows:
                    lines = [with_style(line, "b") for line in lines]
                rendered.append((cell[0] if cell else "l", lines))
            for y in range(max([len(lines) for _, lines in rendered] + [1])):
                physical: Line = [Run("│", edge)]
                for c, (align, lines) in enumerate(rendered):
                    physical += [Run(" "), *pad(lines[y] if y < len(lines) else [], widths[c], align), Run(" "), Run("│", edge)]
                out.append(physical)
        out.append(rule("└", "┴", "┘"))
        return out

    # --- the document -----------------------------------------------------------------------------------------------

    def title_block(self, meta: Dict[str, dict], width: int) -> List[Line]:
        title = meta_inlines(meta.get("title"))
        if not title:
            return []
        out = wrap(self.inlines(title, ("b", "u")), width)
        authors = meta.get("author")
        names = [plain(meta_inlines(entry)) for entry in (authors["c"] if authors and authors["t"] == "MetaList" else
                                                          [authors] if authors else [])]
        line = [*names, plain(meta_inlines(meta.get("date")))]
        text = " · ".join(clean(part) for part in line if part)
        if text:
            out += wrap([Run(text, ("dim",))], width)
        abstract = meta.get("abstract")
        if abstract:
            body = (abstract["c"] if abstract["t"] == "MetaBlocks" else
                    [{"t": "Para", "c": meta_inlines(abstract)}])
            out += [[], *[with_style(piece, "i") for piece in self.blocks(body, width)]]
        return out

    def document(self, doc: dict) -> List[Line]:
        lines: List[Line] = []
        if self.title:
            lines = self.title_block(doc.get("meta", {}), self.width)
        body = self.blocks(doc.get("blocks", []), self.width)
        if lines and body:
            lines.append([])
        lines += body
        if self.notes:
            lines += [[], [Run("─" * min(self.width, 20), ("dim",))]]
            index = 0
            while index < len(self.notes):             # a note may hold a note
                text = self.blocks(self.notes[index], self.width - 4)
                marker = f"{index + 1}. "
                lines += [[Run(marker.rjust(4) if i == 0 else "    ", ("dim",)), *line] if line else []
                          for i, line in enumerate(text)] or [[Run(marker.rjust(4), ("dim",))]]
                index += 1
        return lines

    def render(self, doc: dict) -> str:
        lines = self.document(doc)
        while lines and not lines[-1]:
            lines.pop()
        return "".join(emit(line, self.color, self.hyperlinks).rstrip(" ") + "\n" if line else "\n" for line in lines)


def centred(lines: List[Line], width: int) -> List[Line]:
    return [[Run(" " * max(0, (width - line_width(line)) // 2)), *line] for line in lines]


def render(doc: dict, width: int = 100, color: bool = True, hyperlinks: bool = False,
           math: Optional[MathFunction] = None, title: bool = True) -> str:
    """Pandoc's JSON AST as text for a terminal (see the module docstring)."""
    return Renderer(width, color, hyperlinks, math, title).render(doc)
