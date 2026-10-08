"""Numbers and names for references, read from what LaTeX itself wrote.

A Word file has no counters: "Equation 3", "Figure 2", "see Table 1" must be text. LaTeX knows the
numbers; they are in the `.aux` file of a real PDF build (`\\newlabel`, and cleveref's `@cref` twin).
This reads them, plus the caption separator and `\\crefname`s the document's preamble sets.
"""

from __future__ import annotations

import re

# cleveref's names, singular and plural, capitalised (`\\usepackage[capitalize]{cleveref}`)
CREF_NAMES = {
    "equation": ("Equation", "Equations"), "figure": ("Figure", "Figures"), "subfigure": ("Figure", "Figures"),
    "table": ("Table", "Tables"), "subtable": ("Table", "Tables"), "page": ("Page", "Pages"),
    "part": ("Part", "Parts"), "chapter": ("Chapter", "Chapters"), "section": ("Section", "Sections"),
    "subsection": ("Section", "Sections"), "subsubsection": ("Section", "Sections"),
    "paragraph": ("Paragraph", "Paragraphs"), "appendix": ("Appendix", "Appendices"),
    "subappendix": ("Appendix", "Appendices"), "enumi": ("Item", "Items"), "footnote": ("Note", "Notes"),
    "theorem": ("Theorem", "Theorems"), "lemma": ("Lemma", "Lemmas"), "corollary": ("Corollary", "Corollaries"),
    "proposition": ("Proposition", "Propositions"), "definition": ("Definition", "Definitions"),
    "result": ("Result", "Results"), "example": ("Example", "Examples"), "remark": ("Remark", "Remarks"),
    "algorithm": ("Algorithm", "Algorithms"), "listing": ("Listing", "Listings"), "line": ("Line", "Lines"),
}


def _group(text: str, position: int) -> tuple[str, int] | None:
    """The balanced {...} group at or after `position`: (content, position after it)."""
    start = text.find("{", position)
    if start == -1:
        return None
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
        index += 1
    return None


def _plain(text: str) -> str:
    """A label's number as typed text: commands dropped, braces opened."""
    text = re.sub(r"\\(?:relax|nobreakspace|protect|space)\b\s*", " ", text)
    text = re.sub(r"\\[a-zA-Z@]+\*?\s*", "", text)
    return re.sub(r"[{}]", "", text).strip()


def parse_aux(text: str) -> dict[str, dict]:
    """{label: {num, page, title, type}} from the `\\newlabel` lines of an .aux file."""
    labels: dict[str, dict] = {}
    cref: dict[str, tuple[str, str]] = {}
    position = 0
    marker = "\\newlabel"
    while True:
        at = text.find(marker, position)
        if at == -1:
            break
        name = _group(text, at + len(marker))
        if name is None:
            break
        body = _group(text, name[1])
        position = name[1] if body is None else body[1]
        if body is None:
            continue
        label, content = name[0], body[0]
        fields: list[str] = []
        cursor = 0
        while True:
            part = _group(content, cursor)
            if part is None:
                break
            fields.append(part[0])
            cursor = part[1]
        if label.endswith("@cref"):
            found = re.match(r"\[([^\]]*)\]\[[^\]]*\]\[[^\]]*\](.*)", fields[0]) if fields else None
            if found:
                cref[label[:-5]] = (found.group(1), _plain(found.group(2)))
            continue
        if fields:
            labels[label] = {"num": _plain(fields[0]), "page": _plain(fields[1]) if len(fields) > 1 else "",
                             "title": _plain(fields[2]) if len(fields) > 2 else ""}
    for label, (kind, number) in cref.items():
        entry = labels.setdefault(label, {"num": number, "page": "", "title": ""})
        entry["type"] = kind
        if not entry.get("num"):
            entry["num"] = number
    for label, entry in labels.items():
        entry.setdefault("type", _type_from_anchor(label, entry))
    return labels


def _type_from_anchor(label: str, entry: dict) -> str:
    return ""


def caption_separator(texts: list[str]) -> str:
    """'. ' or ': ' ... from `labelsep=` in the preamble (captionsetup), else LaTeX's ': '."""
    for text in texts:
        found = re.search(r"labelsep\s*=\s*(\w+)", text)
        if found:
            return {"period": ". ", "colon": ": ", "space": " ", "quad": "  ", "newline": " ",
                    "endash": " – ", "none": ""}.get(found.group(1), ": ")
    return ": "


def cref_names(texts: list[str]) -> dict[str, tuple[str, str]]:
    """`\\crefname{type}{singular}{plural}` / `\\Crefname` set in the preamble, over the defaults."""
    names = dict(CREF_NAMES)
    for text in texts:
        for command in ("\\crefname", "\\Crefname"):
            position = 0
            while True:
                at = text.find(command + "{", position)
                if at == -1:
                    break
                first = _group(text, at + len(command))
                second = _group(text, first[1]) if first else None
                third = _group(text, second[1]) if second else None
                position = at + len(command) + 1
                if first and second and third:
                    if command == "\\Crefname" or first[0] not in names:
                        names[first[0]] = (second[0], third[0])
    return names
