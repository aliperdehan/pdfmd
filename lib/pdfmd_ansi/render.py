"""Pandoc's JSON AST -> text for a terminal (bold, italic, code, box-drawn tables, lists, quotes), as a pure function.

    render(document, width=100, color=True, hyperlinks=False, math=None) -> str

`document` is what `pandoc -t json` writes (or `native.from_markdown` makes without Pandoc). `math(tex, display)` may return
lines of `(text, kind)` pieces (kind "", "i" or "b"); without it a formula is shown as its TeX source. No other module
of pdfmd is imported: `qwen` and a later full-screen reader can use this package alone.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

from . import highlight, mathbox
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


# the box-drawing character at a crossing, by which arms (up, down, left, right) reach it
JOINTS = {(False, False, False, False): " ", (True, False, False, False): "│", (False, True, False, False): "│",
          (True, True, False, False): "│", (False, False, True, False): "─", (False, False, False, True): "─",
          (False, False, True, True): "─", (False, True, False, True): "┌", (False, True, True, False): "┐",
          (True, False, False, True): "└", (True, False, True, False): "┘", (True, True, False, True): "├",
          (True, True, True, False): "┤", (False, True, True, True): "┬", (True, False, True, True): "┴",
          (True, True, True, True): "┼"}


class Cell(NamedTuple):
    """A table cell placed on the grid: its top-left corner, how far it reaches, and what it holds."""
    row: int
    col: int
    rowspan: int
    colspan: int
    align: str
    blocks: list
    header: bool


class Renderer:
    def __init__(self, width: int = 100, color: bool = True, hyperlinks: bool = False,
                 math: Optional[MathFunction] = None, title: bool = True, stacked: bool = True):
        self.width = max(20, width)
        self.color = color
        self.hyperlinks = hyperlinks and color
        self.math = math
        self.title = title
        self.stacked = stacked                # display math on several rows (fractions, roots, limits), when `math` can set the rest
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
                rows = self.stacked_math(content[0]["c"][1], width)
                if rows is not None:
                    return rows
                return centred(wrap(self.inlines(content), width), width)       # a formula on its own is centred
            return wrap(self.inlines(content), width)
        if kind == "Header":
            return wrap(self.inlines(content[2], HEADINGS.get(content[0], ("b", "i"))), width)
        if kind == "CodeBlock":
            return self.code_block(content[1], width, content[0][1])
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

    def code_block(self, text: str, width: int, classes: Sequence[str] = ()) -> List[Line]:
        code = clean(text.expandtabs(4)).rstrip("\n")
        marked = highlight.tokens(highlight.language_of(list(classes)), code) if self.color else None
        if marked is None:                                       # colour off, or a language we do not colour: as it always was
            return [[Run("  " + line, ("code",))] if line else [] for line in code.split("\n")]
        out: List[Line] = []
        for pieces in marked:
            out.append([Run("  ", ("code",)), *[Run(text, (highlight.PALETTE[kind],) if kind else ("code",))
                                                  for text, kind in pieces]] if pieces else [])
        return out

    def stacked_math(self, tex: str, width: int) -> Optional[List[Line]]:
        """A display formula on several rows, centred as one block; None when it has nothing to stack, holds something that
        cannot be (see pdfmd_ansi.mathbox), or is wider than the line -- the linear form is shown then."""
        if not (self.stacked and self.math):
            return None
        rows = mathbox.stacked(tex, self.math)
        if not rows:
            return None
        widest = max(sum(text_width(text) for text, _ in row) for row in rows)
        if widest > width:
            return None
        margin = Run(" " * ((width - widest) // 2))
        return [[margin, *[Run(clean(text), (kind,) if kind else ()) for text, kind in row]] if row else [] for row in rows]

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

    def place(self, rows: list, columns: list, header_rows: int) -> Tuple[List[list], List[Cell]]:
        """The cells on the grid: `cover[row][col]` is the index in `cells` of the cell that fills that square (a cell with a
        rowspan or a colspan fills several), and a square no cell names holds an empty one."""
        count, total = len(columns), len(rows)
        cover: List[list] = [[None] * count for _ in rows]
        cells: List[Cell] = []

        def put(r: int, c: int, rowspan: int, colspan: int, align: str, blocks: list) -> None:
            rowspan = max(1, min(rowspan, total - r))
            colspan = max(1, min(colspan, count - c))
            while colspan > 1 and any(cover[r][c + dc] is not None for dc in range(colspan)):
                colspan -= 1                                   # (a malformed table: a span may not run over another cell)
            while rowspan > 1 and any(cover[r + dr][c + dc] is not None for dr in range(rowspan) for dc in range(colspan)):
                rowspan -= 1
            for dr in range(rowspan):
                for dc in range(colspan):
                    cover[r + dr][c + dc] = len(cells)
            cells.append(Cell(r, c, rowspan, colspan, align, blocks, r < header_rows))

        for r, row in enumerate(rows):
            c = 0
            for _, align, rowspan, colspan, blocks in row[1]:
                while c < count and cover[r][c] is not None:
                    c += 1
                if c >= count:
                    break
                put(r, c, rowspan, colspan, self.cell_align(align, columns[c][0]), blocks)
                c += cells[-1].colspan
            for c in range(count):
                if cover[r][c] is None:
                    put(r, c, 1, 1, "l", [])
        return cover, cells

    @staticmethod
    def words_width(lines: List[Line]) -> int:
        longest = 1
        for line in lines:
            for word in "".join(run.text for run in line).split(" "):
                longest = max(longest, text_width(word))
        return longest

    def column_widths(self, cells: List[Cell], count: int, width: int) -> List[int]:
        """The width of each column's text: its natural width, or less when the table is wider than the line (the longest
        words first kept whole). A cell that spans columns widens the ones it spans when it needs more than they have, and
        counts for nothing else; the borders it leaves out give back three cells each."""
        natural = [1] * count
        floor = [1] * count
        measured = []
        for cell in cells:
            lines = self.blocks(cell.blocks, INF)
            need = max([line_width(line) for line in lines] + [1])
            word = self.words_width(lines)
            measured.append((need, word))
            if cell.colspan == 1:
                natural[cell.col] = max(natural[cell.col], need)
                floor[cell.col] = max(floor[cell.col], word)
        spanning = sorted((index for index, cell in enumerate(cells) if cell.colspan > 1), key=lambda i: cells[i].colspan)
        for index in spanning:
            cell, (need, word) = cells[index], measured[index]
            reach = range(cell.col, cell.col + cell.colspan)
            for sizes, wanted in ((natural, need), (floor, word)):
                missing = wanted - (sum(sizes[c] for c in reach) + 3 * (cell.colspan - 1))
                while missing > 0:
                    sizes[min(reach, key=lambda c: sizes[c])] += 1
                    missing -= 1
        available = width - 3 * count - 1
        widths = list(natural)
        for minimum in (lambda c: min(floor[c], natural[c]), lambda c: min(3, natural[c])):
            while sum(widths) > available:
                shrinkable = [c for c in range(count) if widths[c] > minimum(c)]
                if not shrinkable:
                    break
                widths[max(shrinkable, key=lambda c: widths[c])] -= 1
        return widths

    def table(self, content: list, width: int) -> List[Line]:
        _, caption, columns, head, bodies, foot = content
        head_rows = head[1]
        rows = head_rows + [row for body in bodies for row in body[2] + body[3]] + foot[1]
        count = len(columns)
        if not rows or not count:
            return []
        total = len(rows)
        cover, cells = self.place(rows, columns, len(head_rows))
        widths = self.column_widths(cells, count, width)
        edge = ("dim",)

        def span_width(cell: Cell) -> int:
            return sum(widths[cell.col:cell.col + cell.colspan]) + 3 * (cell.colspan - 1)

        text: List[List[Line]] = []
        for cell in cells:
            lines = self.blocks(cell.blocks, span_width(cell))
            text.append([with_style(line, "b") for line in lines] if cell.header else lines)
        heights = [1] * total
        for index, cell in enumerate(cells):
            if cell.rowspan == 1:
                heights[cell.row] = max(heights[cell.row], len(text[index]))
        for index in sorted((i for i, cell in enumerate(cells) if cell.rowspan > 1), key=lambda i: cells[i].rowspan):
            cell = cells[index]
            room = sum(heights[cell.row:cell.row + cell.rowspan]) + cell.rowspan - 1     # the rules it leaves out are lines too
            if len(text[index]) > room:
                heights[cell.row + cell.rowspan - 1] += len(text[index]) - room

        def line_of(index: int, nth: int) -> Line:
            """The nth line of a cell's block, padded to the width of the columns it spans."""
            cell = cells[index]
            lines = text[index]
            return pad(lines[nth] if nth < len(lines) else [], span_width(cell), cell.align)

        def rule_drawn(boundary: int, c: int) -> bool:
            """Whether a horizontal rule runs over column c between row boundary-1 and row boundary."""
            return boundary in (0, total) or cover[boundary - 1][c] != cover[boundary][c]

        def bar_drawn(r: int, j: int) -> bool:
            """Whether a vertical line stands at column boundary j in row r."""
            return j in (0, count) or cover[r][j - 1] != cover[r][j]

        def junction(boundary: int, j: int) -> str:
            up = boundary > 0 and bar_drawn(boundary - 1, j)
            down = boundary < total and bar_drawn(boundary, j)
            left = j > 0 and rule_drawn(boundary, j - 1)
            right = j < count and rule_drawn(boundary, j)
            return JOINTS[(up, down, left, right)]

        def rule(boundary: int) -> Line:
            line: Line = []
            c = 0
            pieces = ""
            while c < count:
                pieces += junction(boundary, c)
                if rule_drawn(boundary, c):
                    pieces += "─" * (widths[c] + 2)
                    c += 1
                    continue
                cell = cells[cover[boundary][c]]                 # inside a rowspan: the cell goes on, across this line
                line.append(Run(pieces, edge))
                nth = sum(heights[cell.row:boundary]) + (boundary - cell.row) - 1
                line += [Run(" "), *line_of(cover[boundary][c], nth), Run(" ")]
                pieces = ""
                c += cell.colspan
            line.append(Run(pieces + junction(boundary, count), edge))
            return line

        out: List[Line] = []
        if caption[1]:
            out += [with_style(line, "i") for line in self.blocks(caption[1], width)]
        out.append(rule(0))
        for r in range(total):
            if r:
                out.append(rule(r))
            for y in range(heights[r]):
                physical: Line = [Run("│", edge)]
                c = 0
                while c < count:
                    index = cover[r][c]
                    cell = cells[index]
                    nth = sum(heights[cell.row:r]) + (r - cell.row) + y
                    physical += [Run(" "), *line_of(index, nth), Run(" "), Run("│", edge)]
                    c += cell.colspan
                out.append(physical)
        out.append(rule(total))
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
           math: Optional[MathFunction] = None, title: bool = True, stacked: bool = True) -> str:
    """Pandoc's JSON AST as text for a terminal (see the module docstring)."""
    return Renderer(width, color, hyperlinks, math, title, stacked).render(doc)
