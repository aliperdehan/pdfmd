"""Cell tags of pipe tables: merging cells and aligning one cell (entry 3fa, `[tables]`).

A pipe table cell may carry a *tag* that says how that one cell is drawn:

    | Scores &<<& | &mc& 12 | Total <c> | << |

* horizontal alignment `l` `r` `c`, vertical alignment `t` `m` `b` (a lone `c` is horizontal; with one other letter it
  takes the free axis, `cc` is both: `mc` = `cm` = `cc` = centred both ways),
* merging `<<` `>>` `^^` `vv`: the cell belongs to the neighbour in that direction (the arrow points at the owner of the
  content); a chain is followed, the merged region must be a rectangle.

The tag is found anywhere in the cell, in one of these spellings (the order of the letters and their case do not matter, the
separators are a comma, a space or nothing, and full words are read too: `top middle bottom left right center centre`,
`merge-left merge-right merge-up merge-down`, matched after lowercasing and dropping `-`, `_` and `.`):

* `&...&`: the recommended form, takes anything, arrows included (`&mc&`, `&<<&`, `&^^,t,c&`, `&merge-up,top&`);
* `<...>`: letters and words (`<c>`, `<mc>`, `<merge-up, top>`), never a symbolic arrow; `<br>`, `<tr>` and `<tt>` stay HTML,
  `<b>` and `<center>` are tags only when the cell has no closing `</b>` / `</center>`;
* a bare `<<` `>>` `^^` `vv` that is the whole content of the cell;
* `{...}` and `«...»`, off unless asked for (`brackets`).

`&`, `{}` and `«»` tags must stand apart (start or end of the cell, or whitespace around them). Code spans and math are
skipped, a `\\<` escape is a literal. Pandoc does not read any of this as a table feature, so the pre-pass (a temporary
copy, the file is never changed) resolves the merges and writes ONE canonical raw tag in front of each cell it touches:

    <pc c2 r2 hc vm>      the owner of a merged region (2 columns, 2 rows), centred both ways; each word is optional
    <pc xl> / <pc xu>     a cell the owner covers (the filter drops it); the owner is to its left, or above it

The tag is short on purpose: Pandoc reads a pipe table whose source line is longer than its column limit as a table of
fixed, dash-proportional widths, so a long tag would stretch a small table to the page width.
A line `{...}` right under a table (or under its `Table:` caption) is the table's *attribute line*: sizes and defaults for the whole
table, a column or a row, which the cell tags cannot say (step 3 of entry 3fa):

    {widths="2cm * 30%" col2.align=r,m row3.height=1.5cm valign=middle}

    width / widths   a length (`3cm`, `12mm`, `2in`, `40pt`, `10em`), a percentage of the text width, `*` (a share of what is left)
                     or `auto` (the text's own width); `widths="..."` lists every column, `col2.width=3cm` sets one, `width=80%`
                     alone is the whole table's
    height           the least height of a row (`row3.height=1.5cm`), or of every row (`height=1cm`)
    align            alignment words as in a cell tag (`col2.align=r,m`, `row1.align=c`, `align=c`)
    valign           top, middle or bottom (`valign=m` = `align=m`)

and is written, short, into the first header cell as `<pt c2w=3cm r3ht=1.5cm v=m>` (the carrier is a cell because Pandoc ties a
`Table:` caption to the table it follows, and a block between them would cut the tie). pdfmd_lua/cellalign.lua reads both tags.
Functions are pure: text in, text and notes out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KINDS = ("angle", "amp", "brace", "guillemet")
DEFAULT_KINDS = ("angle", "amp")
TAG = "pc"

_ARROWS = {"<<": "left", ">>": "right", "^^": "up", "vv": "down"}
_STEP = {"left": (0, -1), "right": (0, 1), "up": (-1, 0), "down": (1, 0)}
_WORDS = {
    "left": ("h", "l"), "right": ("h", "r"), "center": ("c", ""), "centre": ("c", ""),
    "top": ("v", "t"), "middle": ("v", "m"), "bottom": ("v", "b"),
    "mergeleft": ("m", "left"), "mergeright": ("m", "right"), "mergeup": ("m", "up"), "mergedown": ("m", "down"),
}
_LETTER = {"l": ("h", "l"), "r": ("h", "r"), "c": ("c", ""), "t": ("v", "t"), "m": ("v", "m"), "b": ("v", "b")}
_CHUNK_ARROWS = re.compile(r"(?:<<|>>|\^\^|vv|[lrctmb])+")
_CHUNK_LETTERS = re.compile(r"[lrctmb]+")
_SPLIT = re.compile(r"[,;\s]+")
_ARROW_ONLY = re.compile(r"\s*(?:(?:<<|>>|\^\^|vv)\s*)+", re.IGNORECASE)
_ARROW_FIND = re.compile(r"<<|>>|\^\^|vv", re.IGNORECASE)
_SEPARATOR_ROW = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)", re.DOTALL)
_MATH = re.compile(r"\$\$.+?\$\$|(?<![\\$])\$(?=[^\s$])(?:[^$\\\n]|\\.)+?(?<=[^\s\\])\$(?![\d$])|\\\(.+?\\\)", re.DOTALL)
_ANGLE = re.compile(r"<([A-Za-z][A-Za-z\-_., ;]*)>")
_HTML_NAMES = {"br", "tr", "tt"}
_PAIRED = {"b": "</b>", "center": "</center>"}
_APART_AFTER = ".,;:)]!?"


@dataclass
class Spec:
    """What the tags of one cell say."""
    merge: list[str] = field(default_factory=list)
    h: str = ""
    v: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.merge or self.h or self.v)


def parse_tokens(content: str, arrows: bool) -> Spec | None:
    """The tokens of a tag's content as a Spec, or None when the content is not made of tokens only (so it is not a tag)."""
    chunks = [chunk for chunk in _SPLIT.split(content.strip()) if chunk]
    if not chunks:
        return None
    spec = Spec()
    centres = 0
    letters: list[tuple[str, str]] = []
    for chunk in chunks:
        low = chunk.casefold()
        word = re.sub(r"[-_.]", "", low)
        if word in _WORDS:
            letters.append(_WORDS[word])
        elif (_CHUNK_ARROWS if arrows else _CHUNK_LETTERS).fullmatch(low):
            for token in re.findall(r"<<|>>|\^\^|vv|[lrctmb]" if arrows else r"[lrctmb]", low):
                letters.append(("m", _ARROWS[token]) if token in _ARROWS else _LETTER[token])
        else:
            return None
    for axis, value in letters:
        if axis == "m":
            if value not in spec.merge:
                spec.merge.append(value)
        elif axis == "c":
            centres += 1
        else:
            current = getattr(spec, axis)
            if current and current != value:
                spec.problems.append(f"two {'horizontal' if axis == 'h' else 'vertical'} alignments in one tag "
                                     f"({current}, {value}); the last one wins")
            setattr(spec, axis, value)
    if centres:
        if centres > 2:
            spec.problems.append("more than two `c` in one tag; read as two")
        if centres >= 2:
            _place(spec, "h", "c")
            _place(spec, "v", "m")
        elif spec.v:
            _place(spec, "h", "c")
        elif spec.h:
            _place(spec, "v", "m")
        else:
            spec.h = "c"
    return spec


def _place(spec: Spec, axis: str, value: str) -> None:
    current = getattr(spec, axis)
    if current and current != value:
        spec.problems.append(f"`c` and {current} are both a {'horizontal' if axis == 'h' else 'vertical'} alignment; "
                             f"the last one wins")
    setattr(spec, axis, value)


def _masked(text: str) -> list[tuple[int, int]]:
    return [match.span() for pattern in (_CODE, _MATH) for match in pattern.finditer(text)]


def _inside(masks: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(a < end and start < b for a, b in masks)


def _apart(text: str, start: int, end: int) -> bool:
    before = start == 0 or text[start - 1].isspace()
    after = end >= len(text) or text[end].isspace() or text[end] in _APART_AFTER
    return before and after


def find_tags(cell: str, kinds: tuple[str, ...] = DEFAULT_KINDS) -> tuple[list[tuple[int, int, Spec]], bool]:
    """The tags of one cell as (start, end, Spec), and whether the cell is a bare arrow cell (then the one tag spans it)."""
    if _ARROW_ONLY.fullmatch(cell):
        spec = Spec(merge=[])
        for token in _ARROW_FIND.findall(cell):
            direction = _ARROWS[token.casefold()]
            if direction not in spec.merge:
                spec.merge.append(direction)
        return [(0, len(cell), spec)], True
    masks = _masked(cell)
    found: list[tuple[int, int, Spec]] = []

    def take(start: int, end: int, content: str, arrows: bool) -> bool:
        if _inside(masks, start, end) or (start and cell[start - 1] == "\\"):
            return False
        spec = parse_tokens(content, arrows)
        if spec is None:
            return False
        found.append((start, end, spec))
        return True

    if "angle" in kinds:
        for match in _ANGLE.finditer(cell):
            low = match.group(1).strip().casefold()
            if low in _HTML_NAMES:
                continue
            if low in _PAIRED and _PAIRED[low] in cell.casefold():
                continue
            take(match.start(), match.end(), match.group(1), False)
    if "amp" in kinds:
        spots = [index for index, char in enumerate(cell) if char == "&" and not _inside(masks, index, index + 1)
                 and (index == 0 or cell[index - 1] != "\\")]
        at = 0
        while at + 1 < len(spots):
            start, end = spots[at], spots[at + 1]
            if _apart(cell, start, end + 1) and end > start + 1 and take(start, end + 1, cell[start + 1:end], True):
                at += 2
            else:
                at += 1
    for kind, opener, closer in (("brace", "{", "}"), ("guillemet", "«", "»")):
        if kind not in kinds:
            continue
        for match in re.finditer(re.escape(opener) + r"([^" + re.escape(opener + closer) + r"\n]+)" + re.escape(closer), cell):
            if _apart(cell, match.start(), match.end()):
                take(match.start(), match.end(), match.group(1), True)
    found.sort(key=lambda item: item[0])
    clean: list[tuple[int, int, Spec]] = []
    for item in found:
        if clean and item[0] < clean[-1][1]:
            continue
        clean.append(item)
    return clean, False


def _combine(specs: list[Spec]) -> Spec:
    total = Spec()
    for spec in specs:
        for direction in spec.merge:
            if direction not in total.merge:
                total.merge.append(direction)
        for axis in ("h", "v"):
            value = getattr(spec, axis)
            if value:
                if getattr(total, axis) and getattr(total, axis) != value:
                    total.problems.append(f"two tags set the {'horizontal' if axis == 'h' else 'vertical'} alignment "
                                          f"({getattr(total, axis)}, {value}); the last one wins")
                setattr(total, axis, value)
        total.problems.extend(spec.problems)
    return total


def strip_tags(cell: str, tags: list[tuple[int, int, Spec]]) -> str:
    """``cell`` without its tags (and one space next to each), trimmed."""
    pieces: list[str] = []
    position = 0
    for start, end, _ in tags:
        pieces.append(cell[position:start])
        pieces.append("\0")
        position = end
    pieces.append(cell[position:])
    text = "".join(pieces)
    text = re.sub(r"([ \t]?)\0([ \t]?)", lambda m: " " if m.group(1) or m.group(2) else "", text)
    return text.strip()


@dataclass
class Note:
    line: int
    message: str


@dataclass
class Result:
    text: str
    notes: list[Note] = field(default_factory=list)
    tables: int = 0                  # tables with at least one tag
    cells: int = 0                   # cells with a tag
    tblr: int = 0                    # cells and tables LaTeX can only draw with tabularray: a vertical alignment, a width, a height


def _split_row(line: str) -> tuple[str, list[str], str]:
    body = line.rstrip("\r")
    start = len(body) - len(body.lstrip())
    lead = body[:start]
    rest = body[start:]
    opening = "|" if rest.startswith("|") else ""
    if opening:
        rest = rest[1:]
    closing = ""
    if rest.rstrip().endswith("|") and not rest.rstrip().endswith("\\|"):
        stripped = rest.rstrip()
        trailing = rest[len(stripped):]
        rest = stripped[:-1]
        closing = "|" + trailing
    return lead + opening, re.split(r"(?<!\\)\|", rest), closing


def _canon(spec: Spec | None, colspan: int = 1, rowspan: int = 1, covered: str = "") -> str:
    if covered:
        return f"<{TAG} x{covered}>"
    words = []
    if colspan > 1:
        words.append(f"c{colspan}")
    if rowspan > 1:
        words.append(f"r{rowspan}")
    if spec is not None and spec.h:
        words.append(f"h{spec.h}")
    if spec is not None and spec.v:
        words.append(f"v{spec.v}")
    return f"<{TAG}{' ' if words else ''}{' '.join(words)}>"


_LENGTH = re.compile(r"\d+(?:\.\d+)?(?:cm|mm|in|pt|em|ex)")
_PERCENT = re.compile(r"\d+(?:\.\d+)?%")
_ATTR_ITEM = re.compile(r"""([A-Za-z][A-Za-z0-9.\-_]*)\s*=\s*("[^"]*"|'[^']*'|[^\s"']+)""")
_ATTR_LINE = re.compile(r"^\s{0,3}\{(.*)\}\s*$")
_ATTR_NAMES = {"width": "w", "widths": "ws", "height": "ht", "align": "h", "valign": "v"}
_ATTR_CARRIER = "pt"
# Pandoc reads a pipe table whose longest source line is over its column limit (`--columns`, 72 unless told otherwise) as a table of fixed
# widths from the dashes of the separator row. The tags make lines longer, so a table that was under the limit must not cross it
# because of them: the padding of rewritten rows is cut, and if that is not enough the carrier says `nw` (natural widths) and the
# filters give the table back the widths it would have had. A Pandoc fact, not a setting.
PANDOC_COLUMNS = 72


def _word(value: str, kind: str, notes: list[str]) -> str | None:
    """One width, height or alignment value as the carrier's short word, or None (with a note)."""
    low = value.strip().casefold()
    if kind == "w":
        if low in ("*", "auto") or _LENGTH.fullmatch(low) or _PERCENT.fullmatch(low):
            return low
        notes.append(f"`{value}` is not a width (3cm, 12mm, 2in, 40pt, 10em, 30%, * or auto)")
    elif kind == "ht":
        if _LENGTH.fullmatch(low):
            return low
        notes.append(f"`{value}` is not a height (3cm, 12mm, 2in, 40pt or 10em)")
    return None


def parse_attribute_line(content: str, columns: int) -> tuple[list[str], list[str]]:
    """The words of a table's attribute line (`<pt ...>` carrier words like `c2w=3cm`) and the problems found."""
    words: list[str] = []
    notes: list[str] = []
    rest = _ATTR_ITEM.sub(" ", content)
    if rest.strip(" ,;"):
        notes.append(f"`{rest.strip()}` in the attribute line is not understood and was left out")
    for match in _ATTR_ITEM.finditer(content):
        key, value = match.group(1).casefold(), match.group(2).strip("\"'")
        scope = ""
        scoped = re.fullmatch(r"(?:col|column|c)(\d+)\.(\w+)|(?:row|r)(\d+)\.(\w+)", key)
        if scoped:
            scope, key = (f"c{scoped.group(1)}", scoped.group(2)) if scoped.group(1) else (f"r{scoped.group(3)}", scoped.group(4))
            if scope[0] == "c" and not 1 <= int(scope[1:]) <= columns:
                notes.append(f"`{match.group(1)}`: the table has {columns} columns")
                continue
        if key not in _ATTR_NAMES:
            notes.append(f"`{match.group(1)}` is not a table setting (width, widths, height, align, valign)")
            continue
        name = _ATTR_NAMES[key]
        if name == "ws":
            parts = [part for part in re.split(r"[\s,]+", value) if part]
            for index, part in enumerate(parts[:columns], 1):
                word = _word(part, "w", notes)
                if word:
                    words.append(f"c{index}w={word}")
            if len(parts) > columns:
                notes.append(f"`widths` lists {len(parts)} widths for {columns} columns; the extra were left out")
        elif name in ("w", "ht"):
            word = _word(value, name, notes)
            if word and name == "ht" and scope.startswith("c"):
                notes.append("a height belongs to a row (`row3.height=1cm`) or to the table, not to a column")
            elif word:
                words.append(f"{scope}{name}={word}")
        elif name in ("h", "v"):
            spec = parse_tokens(value, False)
            if spec is None or spec.merge:
                vertical = {"top": "t", "middle": "m", "bottom": "b"}.get(value.casefold())
                if key == "valign" and vertical:
                    words.append(f"{scope}v={vertical}")
                else:
                    notes.append(f"`{value}` is not an alignment (l, r, c, t, m, b, or words like top, centre)")
                continue
            notes.extend(spec.problems)
            if key == "valign":
                if spec.h:
                    notes.append("`valign` takes top, middle or bottom")
                spec.h, spec.v = "", spec.v or ("m" if spec.h == "c" else "")
            if spec.h:
                words.append(f"{scope}h={spec.h}")
            if spec.v:
                words.append(f"{scope}v={spec.v}")
    return words, notes


@dataclass
class _Cell:
    raw: str
    text: str
    spec: Spec | None = None
    new: str | None = None
    virtual: bool = False


def _process_table(rows: list[tuple[int, str]], kinds: tuple[str, ...], notes: list[Note],
                   attributes: list[str] | None = None) -> dict[int, str]:
    """The rewritten lines of one table (line number -> new text), ``rows`` being its header and body lines. ``attributes`` are the
    words of its attribute line, which go in front of the first header cell."""
    parsed = []
    for number, line in rows:
        lead, cells, closing = _split_row(line)
        parsed.append((number, lead, closing, cells))
    columns = len(parsed[0][3])
    grid: list[list[_Cell]] = []
    any_tag = False
    for number, lead, closing, cells in parsed:
        row: list[_Cell] = []
        for raw in cells:
            tags, bare = find_tags(raw.strip(), kinds)
            if tags:
                any_tag = True
                spec = _combine([tag[2] for tag in tags])
                for problem in spec.problems:
                    notes.append(Note(number, problem))
                text = "" if bare else strip_tags(raw.strip(), tags)
                row.append(_Cell(raw, text, spec))
            else:
                row.append(_Cell(raw, raw.strip()))
        grid.append(row)
    if not any_tag and not attributes:
        return {}
    width = max(columns, *(len(row) for row in grid))
    for row in grid:
        while len(row) < width:
            row.append(_Cell("", "", None, None, True))      # a cell Pandoc pads; written out only if something covers it
    # union of the cells an arrow joins
    parent = {(r, c): (r, c) for r in range(len(grid)) for c in range(width)}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell.spec is None:
                continue
            for direction in cell.spec.merge:
                dr, dc = _STEP[direction]
                if not (0 <= r + dr < len(grid) and 0 <= c + dc < width):
                    notes.append(Note(rows[r][0], f"column {c + 1}: `{direction}` points outside the table; ignored"))
                    continue
                parent[find((r, c))] = find((r + dr, c + dc))
    groups: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for item in parent:
        groups.setdefault(find(item), []).append(item)
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort()
        rs, cs = [m[0] for m in members], [m[1] for m in members]
        top, left, bottom, right = min(rs), min(cs), max(rs), max(cs)
        area = (bottom - top + 1) * (right - left + 1)
        if area != len(members):
            notes.append(Note(rows[top][0], f"cells merged by arrows do not form a rectangle (rows {rows_label(rows, top, bottom)}, "
                                            f"columns {left + 1}-{right + 1}); not merged"))
            continue
        texts = [grid[r][c].text for r, c in members if grid[r][c].text]
        owner = grid[top][left]
        merged = texts[0] if texts else ""
        if len(texts) > 1:
            merged = "<br>".join(texts)
            notes.append(Note(rows[top][0], f"column {left + 1}: {len(texts) - 1} merged cell(s) held text; it was added to "
                                            "the merged cell on a new line, nothing is dropped"))
        h = next((grid[r][c].spec.h for r, c in members if grid[r][c].spec and grid[r][c].spec.h), "")
        v = next((grid[r][c].spec.v for r, c in members if grid[r][c].spec and grid[r][c].spec.v), "")
        spec = Spec(h=h, v=v)
        owner.new = _canon(spec, right - left + 1, bottom - top + 1) + (" " + merged if merged else "")
        owner.spec = None
        for r, c in members:
            if (r, c) != (top, left):
                grid[r][c].new = _canon(None, covered="l" if c > left else "u")
                grid[r][c].spec = None
    # cells with an alignment tag only, and merge arrows that were dropped (their text stays)
    for row in grid:
        for cell in row:
            if cell.new is None and cell.spec is not None:
                cell.new = (_canon(cell.spec) + (" " + cell.text if cell.text else "")) if (cell.spec.h or cell.spec.v) \
                    else cell.text
    if attributes:
        first = grid[0][0]
        carrier = f"<{_ATTR_CARRIER} {' '.join(attributes)}>"
        first.new = carrier + (" " + (first.new if first.new is not None else first.text) if (first.new or first.text) else "")
    changed: dict[int, str] = {}
    for r, (number, lead, closing, cells) in enumerate(parsed):
        row = grid[r]
        if all(cell.new is None for cell in row):
            continue
        used = max([len(cells)] + [c + 1 for c, cell in enumerate(row) if cell.new is not None])
        pieces = [f" {row[c].new} " if row[c].new is not None else (cells[c] if c < len(cells) else " ") for c in range(used)]
        if not closing:
            closing = "|"
        if not lead.strip():
            lead = lead + "|"
        changed[number] = lead + "|".join(pieces) + closing
    return changed


def _compact(line: str) -> str:
    """A table row with one space on each side of every cell (the padding of a rewritten row is what makes it long)."""
    lead, cells, closing = _split_row(line)
    return lead.rstrip() + "|".join(f" {cell.strip()} " for cell in cells) + "|" + ("\r" if line.endswith("\r") else "")


def _longest(lines: list[str], numbers: range, changes: dict[int, str]) -> int:
    return max(len(changes.get(number, lines[number]).rstrip("\r")) for number in numbers)


def _find_attribute_line(lines: list[str], end: int) -> int | None:
    """The index of the attribute line of the table that ends before line ``end``: the first line after it (one blank line allowed)
    or after its `Table:` caption, if it is `{...}` with at least one `key=value`; else None."""
    index = end
    if index < len(lines) and not lines[index].strip():
        index += 1
    if index < len(lines) and re.match(r"^\s{0,3}(?:Table)?:\s", lines[index]):
        while index < len(lines) and lines[index].strip():
            index += 1
        if index < len(lines):
            index += 1
    if index < len(lines):
        match = _ATTR_LINE.match(lines[index].rstrip("\r"))
        if match and _ATTR_ITEM.search(match.group(1)):
            return index
    return None


def rows_label(rows: list[tuple[int, str]], top: int, bottom: int) -> str:
    return f"{top + 1}-{bottom + 1}" if top != bottom else str(top + 1)


def normalise(text: str, kinds: tuple[str, ...] = DEFAULT_KINDS) -> Result:
    """``text`` with every cell tag of its pipe tables rewritten to the canonical tag; notes for what could not be done."""
    if "\n" not in text and "|" not in text:
        return Result(text)
    lines = text.split("\n")
    result = Result(text)
    index = 0
    fence = ""
    if lines and lines[0].strip() == "---":
        for end in range(1, len(lines)):
            if lines[end].strip() in ("---", "..."):
                index = end + 1
                break
    changed: dict[int, str] = {}
    removals: list[int] = []
    while index < len(lines):
        line = lines[index].rstrip("\r")
        match = _FENCE.match(line)
        if fence:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) and not line.strip(match.group(1)[0]).strip():
                fence = ""
            index += 1
            continue
        if match:
            fence = match.group(1)
            index += 1
            continue
        if "|" in line and not line.startswith("    ") and index + 1 < len(lines) and "|" in lines[index + 1] \
                and _SEPARATOR_ROW.match(lines[index + 1].rstrip("\r")):
            rows = [(index, lines[index])]
            end = index + 2
            while end < len(lines) and lines[end].strip() and "|" in lines[end] and not _FENCE.match(lines[end]):
                rows.append((end, lines[end]))
                end += 1
            notes: list[Note] = []
            attributes: list[str] = []
            drop = _find_attribute_line(lines, end)
            if drop is not None:
                attributes, problems = parse_attribute_line(_ATTR_LINE.match(lines[drop].rstrip("\r")).group(1),
                                                            len(_split_row(rows[0][1])[1]))
                notes.extend(Note(drop, problem) for problem in problems)
                removals.append(drop)
            table_changes = _process_table(rows, kinds, notes, attributes)
            numbers = range(index, end)
            if table_changes and _longest(lines, numbers, {}) <= PANDOC_COLUMNS < _longest(lines, numbers, table_changes):
                table_changes = {number: _compact(text) if number in table_changes else text for number, text in table_changes.items()}
                if _longest(lines, numbers, table_changes) > PANDOC_COLUMNS:
                    table_changes = {number: _compact(text) for number, text in
                                     _process_table(rows, kinds, [], [*attributes, "nw"]).items()}
            for note in notes:
                result.notes.append(Note(note.line + 1, note.message))
            if table_changes:
                result.tables += 1
                result.cells += sum(piece.count(f"<{TAG}") + piece.count(f"<{_ATTR_CARRIER} ") for piece in table_changes.values())
                result.tblr += sum(len(re.findall(rf"<{TAG} [^>]*\bv[tmb]\b", piece)) + len(re.findall(r"<pt [^>]*>", piece))
                                   for piece in table_changes.values())
                changed.update(table_changes)
            index = end
            continue
        index += 1
    if not changed and not result.notes and not removals:
        return result
    for number, new in changed.items():
        lines[number] = new + ("\r" if lines[number].endswith("\r") else "")
    for number in sorted(removals, reverse=True):
        # the attribute line goes, and the blank line before it when a blank line follows it (two blank lines in a row are one)
        del lines[number]
        if number < len(lines) and not lines[number].strip() and number > 0 and not lines[number - 1].strip():
            del lines[number]
    result.text = "\n".join(lines)
    return result
