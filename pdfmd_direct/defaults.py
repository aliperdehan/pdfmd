"""`--apply-defaults`: the settings pdfmd would give a Markdown document, for a `.typ` or `.html` file that gets none.

Only what means the same in every kind of document is applied: title, author, date, language, main font, font size,
page size and margin, read from the metadata files pdfmd finds (a `metadata.yaml` beside the document, the global
one). They go in FIRST, so anything the document sets itself comes after and wins. No Pandoc is involved.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime

PAPER_TYPST = {"a3": "a3", "a4": "a4", "a5": "a5", "a6": "a6", "letter": "us-letter", "legal": "us-legal",
               "us-letter": "us-letter", "us-legal": "us-legal", "b5": "iso-b5", "executive": "us-executive"}
PAPER_CSS = {"a3": "A3", "a4": "A4", "a5": "A5", "a6": "A6", "letter": "letter", "legal": "legal", "b5": "B5",
             "us-letter": "letter", "us-legal": "legal", "executive": "7.25in 10.5in"}
LENGTH_RE = re.compile(r"^\d+(?:\.\d+)?(?:pt|mm|cm|in|em)$")


def _text(value) -> str | None:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value).strip() or None
    return None


def _length(value, default_unit: str = "pt") -> str | None:
    word = _text(value)
    if word is None:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", word):
        word += default_unit
    return word if LENGTH_RE.match(word) else None


def _margin(data: dict) -> str | None:
    """`margin: 1in`, or the `margin=1in` of a `geometry:` string or list."""
    direct = _length(data.get("margin"))
    if direct:
        return direct
    geometry = data.get("geometry")
    for item in (geometry if isinstance(geometry, list) else [geometry]):
        found = re.search(r"(?:^|[,\s])margin\s*=\s*([\d.]+(?:pt|mm|cm|in))", str(item or ""))
        if found:
            return found.group(1)
    return None


def collect(sources: list[dict]) -> dict:
    """The settings of `sources` (parsed metadata files, the highest priority first) that a direct document can take."""
    found: dict = {}
    for data in sources:
        if not isinstance(data, dict):
            continue
        for key in ("title", "date", "lang", "mainfont"):
            if key not in found and _text(data.get(key)):
                found[key] = _text(data[key])
        if "author" not in found:
            author = data.get("author")
            names = [_text(item) if not isinstance(item, dict) else _text(item.get("name")) for item in
                     (author if isinstance(author, list) else [author])]
            names = [name for name in names if name]
            if names:
                found["author"] = names
        if "fontsize" not in found and _length(data.get("fontsize")):
            found["fontsize"] = _length(data.get("fontsize"))
        if "papersize" not in found and _text(data.get("papersize")) and _text(data.get("papersize")).lower() in PAPER_TYPST:
            found["papersize"] = _text(data.get("papersize")).lower()
        if "margin" not in found and _margin(data):
            found["margin"] = _margin(data)
    return found


def _typst_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _iso_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value[:10]) if re.match(r"^\d{4}-\d{2}-\d{2}", value) else None
    except ValueError:
        return None


def typst_prelude(found: dict, source: str) -> str:
    """Typst `#set` lines for the settings the document does not already make itself (a `#set document(title:`
    of its own would make the same rule twice, and the later one wins anyway, so this only adds what is missing)."""
    lines = []
    document = []
    if found.get("title") and not re.search(r"#set\s+document\([^)]*title", source):
        document.append(f"title: {_typst_string(found['title'])}")
    if found.get("author") and not re.search(r"#set\s+document\([^)]*author", source):
        names = ", ".join(_typst_string(name) for name in found["author"])
        document.append(f"author: ({names},)")
    stamp = _iso_date(found.get("date", ""))
    if stamp and not re.search(r"#set\s+document\([^)]*date", source):
        document.append(f"date: datetime(year: {stamp.year}, month: {stamp.month}, day: {stamp.day})")
    if document:
        lines.append("#set document(" + ", ".join(document) + ")")
    text = []
    if found.get("lang"):
        text.append(f"lang: {_typst_string(found['lang'].split('-')[0].lower())}")
    if found.get("mainfont"):
        text.append(f"font: {_typst_string(found['mainfont'])}")
    if found.get("fontsize"):
        text.append(f"size: {found['fontsize']}")
    if text:
        lines.append("#set text(" + ", ".join(text) + ")")
    page = []
    if found.get("papersize"):
        page.append(f"paper: {_typst_string(PAPER_TYPST[found['papersize']])}")
    if found.get("margin"):
        page.append(f"margin: {found['margin']}")
    if page:
        lines.append("#set page(" + ", ".join(page) + ")")
    return ("\n".join(lines) + "\n") if lines else ""


def html_head(found: dict, source: str) -> tuple[str, dict]:
    """(markup for the start of `<head>`, attributes for `<html>`): a title and author when the page has none, and
    a `<style>` for the font and page, which comes before the page's own styles so those win."""
    parts = []
    if found.get("title") and not re.search(r"<title[\s>]", source, re.IGNORECASE):
        parts.append(f"<title>{html.escape(found['title'])}</title>")
    if found.get("author") and not re.search(r"""<meta[^>]+name\s*=\s*["']?author""", source, re.IGNORECASE):
        parts.append(f'<meta name="author" content="{html.escape("; ".join(found["author"]), quote=True)}">')
    rules = []
    page = []
    if found.get("papersize"):
        page.append(f"size: {PAPER_CSS[found['papersize']]}")
    if found.get("margin"):
        page.append(f"margin: {found['margin']}")
    if page:
        rules.append("@page { " + "; ".join(page) + " }")
    body = []
    if found.get("mainfont"):
        body.append(f'font-family: "{found["mainfont"].replace(chr(34), "")}", serif')
    if found.get("fontsize"):
        body.append(f"font-size: {found['fontsize']}")
    if body:
        rules.append("body { " + "; ".join(body) + " }")
    if rules:
        parts.append("<style>" + " ".join(rules) + "</style>")
    attributes = {}
    if found.get("lang") and not re.search(r"<html[^>]*\blang\s*=", source, re.IGNORECASE):
        attributes["lang"] = found["lang"]
    return "\n".join(parts) + ("\n" if parts else ""), attributes


def apply_to_html(found: dict, source: str) -> str:
    head, attributes = html_head(found, source)
    if not head and not attributes:
        return source
    if attributes:
        extra = "".join(f' {key}="{html.escape(value, quote=True)}"' for key, value in attributes.items())
        if re.search(r"<html\b", source, re.IGNORECASE):
            source = re.sub(r"<html\b", lambda match: match.group(0) + extra, source, count=1, flags=re.IGNORECASE)
    if head:
        opened = re.search(r"<head\b[^>]*>", source, re.IGNORECASE)
        if opened:
            source = source[:opened.end()] + "\n" + head + source[opened.end():]
        else:
            opened = re.search(r"<html\b[^>]*>", source, re.IGNORECASE)
            source = (source[:opened.end()] + "\n<head>\n" + head + "</head>" + source[opened.end():]) if opened \
                else "<head>\n" + head + "</head>\n" + source
    return source
