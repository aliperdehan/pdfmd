"""Lower universal markup before the native Markdown reader sees it."""

from __future__ import annotations

import re

from pdfmd_base import core


CENTRE_CLASSES = {"centre", "centred", "centring", "center", "centered", "centering"}
DIV_CLASSES = {
    "centre": CENTRE_CLASSES,
    "keep": {"keep", "nobreak", "keep-together"},
    "landscape": {"landscape"},
    "callouts": {"note", "tip", "important", "warning", "caution", "abstract", "summary", "info", "todo",
                 "success", "check", "done", "question", "help", "faq", "attention", "failure", "fail",
                 "missing", "danger", "error", "bug", "example", "quote", "cite"},
    "fullcite": {"fullcite"},
}
DIV_STYLES = {
    "centre": r"text-align\s*:\s*center\b",
    "keep": r"break-inside\s*:\s*avoid\b",
    "landscape": r"page\s*:\s*landscape\b",
}
TEX_WRAPPER = re.compile(r"^ {0,3}\\begin\{(center|samepage|landscape)\}")
TEX_KINDS = {"center": "centre", "samepage": "keep", "landscape": "landscape"}
HTML_WRAPPER = re.compile(r"^ {0,3}<(center|div)\b([^>]*)>\s*$", re.I)
TOC = re.compile(r"^(?:\[toc\]|\[\[_?toc_?\]\]|\[_toc_\]|\{:toc\}|\\tableofcontents)$", re.I)
CALLOUT = re.compile(r"^(\s*(?:>\s*)+)\[![\w-]+\][-+]?(?:[ \t]+|$)")
HIGHLIGHT = re.compile(r"(?<![\w=\\])==(?=[^=\s])((?:[^\n]|\n(?![ \t]*\n))+?)(?<![=\s])==(?!=)")
UNDERLINE = re.compile(r"<(?P<tag>u|ins)\s*>(?P<body>.*?)</(?P=tag)\s*>", re.I | re.S)
MARK_SPAN = re.compile(r"(?<![\\!])\[([^\[\]\n]+)\]\{\.mark\}")
FULLCITE = re.compile(r"(?<!\\)(\[@[^\]\n]+\])\{\.fullcite(?:\s+[^{}\n]*)?\}|\[\[fullcite:([^\]\n]+)\]\]")
SPACE = re.compile(r"(?:\\(?:smallskip|medskip|bigskip|vspace\*?\{[^{}]+\})|(?:<br\s*/?>\s*)+|#v\([^()]+\))$", re.I)


def div_kind(attributes: str) -> str | None:
    classes = set(re.findall(r"(?:^|[\s{.])([\w-]+)(?=\s|\}|$)", attributes.strip()))
    for kind, names in DIV_CLASSES.items():
        if classes & names or (kind == "callouts" and any(name.startswith("callout-") and name[8:] in names for name in classes)):
            return kind
        if kind in DIV_STYLES and re.search(DIV_STYLES[kind], attributes, re.I):
            return kind
    if re.search(r"\balign\s*=\s*[\"']?center\b", attributes, re.I):
        return "centre"
    return None


def lower(body: str, kinds: set[str], engine: str, marker: str, pagecite: bool) -> tuple[str, dict[str, int]]:
    """Keep the prose, translating supported syntax and counting dropped styling."""
    from pdfmd_check.lint import mask_code

    masked, _ = mask_code(body)
    lines = body.split("\n")
    visible = masked.split("\n")
    dropped: dict[str, int] = {}
    wrappers: list[tuple[str, str | None, int, str]] = []

    def lose(kind: str) -> None:
        dropped[kind] = dropped.get(kind, 0) + 1

    def close(kind: str | None, start: int, end: int, inner: str = "") -> None:
        if kind not in kinds:
            return
        if kind == "centre" and engine == "inkmd":
            opening, closing = f"\n{marker}:start\n", f"\n{marker}:end\n"
        elif kind == "centre" and engine == "calibre":
            opening, closing = '\n<div style="text-align: center" markdown="1">\n', "\n</div>\n"
        else:
            opening = closing = ""
            lose(kind)
        lines[start] = opening + inner
        if start == end:
            lines[end] += closing
        else:
            lines[end] = closing

    for index, line in enumerate(visible):
        plain = line.strip()
        if not plain:
            continue
        tex = TEX_WRAPPER.match(line)
        if tex:
            end = r"\end{" + tex[1] + "}"
            if plain.endswith(end):
                close(TEX_KINDS[tex[1]], index, index, lines[index][tex.end():].rstrip()[:-len(end)].strip())
            else:
                wrappers.append((end, TEX_KINDS[tex[1]], index, lines[index][tex.end():].strip()))
            continue
        html = HTML_WRAPPER.match(line)
        if html:
            tag = html[1].lower()
            wrappers.append((f"</{tag}>", "centre" if tag == "center" else div_kind(html[2]), index, ""))
            continue
        div = core.DIV_FENCE_RE.match(line)
        if div and div[2].strip():
            wrappers.append((":::", div_kind(div[2]), index, ""))
            continue
        if wrappers and (plain.casefold() == wrappers[-1][0] or
                         (plain.startswith(":::") and not plain.strip(":") and wrappers[-1][0] == ":::")):
            _, kind, start, inner = wrappers.pop()
            close(kind, start, index, inner)
            continue
        if "callouts" in kinds and (callout := CALLOUT.match(line)):
            lose("callouts")
            lines[index] = line[:callout.end(1)] + lines[index][callout.end():]
        if "toc" in kinds and TOC.fullmatch(plain):
            lose("toc")
            lines[index] = ""
        if "appendix" in kinds:
            if plain == r"\appendix":
                lose("appendix")
                lines[index] = ""
            elif re.match(r"^#{1,6}\s+.+\{[^{}]*\.appendix\b[^{}]*\}$", plain):
                lose("appendix")   # the normaliser removes heading attributes
        if "space" in kinds and SPACE.fullmatch(plain):
            lose("space")
            lines[index] = ""

    # Apply only the delimiters, leaving any Markdown inside the run intact.
    text = "\n".join(lines)
    masked, _ = mask_code(text)
    edits: list[tuple[int, int, str]] = []
    for kind, pattern, tag, inner in (("highlight", HIGHLIGHT, "mark", 1), ("highlight", MARK_SPAN, "mark", 1),
                                      ("underline", UNDERLINE, "u", "body")):
        if kind not in kinds:
            continue
        for found in pattern.finditer(masked):
            left, right = found.span(inner)
            if kind == "underline" and "\n\n" in found[inner]:
                continue
            if engine == "md2pdf":
                lose(kind)
                opening = closing = ""
            else:
                opening, closing = f"<{tag}>", f"</{tag}>"
            edits.extend([(found.start(), left, opening), (right, found.end(), closing)])
    if "fullcite" in kinds:
        for found in FULLCITE.finditer(masked):
            lose("fullcite")
            edits.append((*found.span(), text[slice(*found.span(1))] if found[1] else f"[@{found[2]}]"))
    if pagecite:
        lose("pagecite")
    position = len(text)
    for start, end, replacement in sorted(edits, reverse=True):
        if end <= position:
            text = text[:start] + replacement + text[end:]
            position = start
    return text, dropped
