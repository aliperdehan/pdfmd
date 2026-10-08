"""Writing a spec (page, fonts, size, language, pdfmd's house look) into a `.docx` reference document.

Pandoc builds a Word file from a *reference document*: its styles, page setup, headers and footers
are copied, only the content is replaced. So the settings are written into a copy of the reference
(the user's own, or Pandoc's default) before Pandoc runs. The XML is edited as text, never parsed
and re-serialised: a template made by Word declares namespaces (`mc:Ignorable="w14 w15"`) that a
round trip through an XML library would drop, and Word then refuses the file.
"""

from __future__ import annotations

import io
import re
import subprocess
import zipfile

from .spec import OfficeSpec

W = "w"
# Child order Word expects inside <w:rPr> and <w:pPr> and <w:sectPr> (ECMA-376); an element out of place
# can make Word report the file as damaged.
RPR_ORDER = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline", "shadow",
             "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
             "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs",
             "em", "lang", "eastAsianLayout", "specVanish", "oMath"]
PPR_ORDER = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
             "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
             "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid",
             "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
             "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange"]
SECT_ORDER = ["headerReference", "footerReference", "footnotePr", "endnotePr", "type", "pgSz", "pgMar", "paperSrc",
              "pgBorders", "lnNumType", "pgNumType", "cols", "formProt", "vAlign", "noEndnote", "titlePg",
              "textDirection", "bidi", "rtlGutter", "docGrid", "printerSettings", "sectPrChange"]

_CHILD = re.compile(r"<w:(\w+)\b(?:[^>]*?/>|[^>]*>.*?</w:\1>)", re.S)


def default_reference(kind: str = "docx") -> bytes:
    """Pandoc's own reference document (needs the `pandoc` on PATH)."""
    done = subprocess.run(["pandoc", "--print-default-data-file", f"reference.{kind}"], capture_output=True)
    if done.returncode != 0 or not done.stdout:
        raise OSError(done.stderr.decode("utf-8", "replace").strip() or "pandoc has no default reference document")
    return done.stdout


def _children(inner: str) -> list[tuple[str, str]]:
    return [(match.group(1), match.group(0)) for match in _CHILD.finditer(inner)]


def _set(inner: str, order: list[str], tag: str, element: str | None) -> str:
    """`inner` (the content of an rPr/pPr/sectPr) with `tag` replaced by `element` (or removed), in schema order."""
    children = [(name, xml) for name, xml in _children(inner) if name != tag]
    if element is not None:
        rank = order.index(tag) if tag in order else len(order)
        position = len(children)
        for index, (name, _) in enumerate(children):
            if (order.index(name) if name in order else len(order)) > rank:
                position = index
                break
        children.insert(position, (tag, element))
    return "".join(xml for _, xml in children)


def _block(xml: str, container: str, create_at: str | None = None) -> tuple[int, int, str] | None:
    match = re.search(rf"<w:{container}\b[^>]*?(?:/>|>(.*?)</w:{container}>)", xml, re.S)
    if not match:
        return None
    return match.start(), match.end(), match.group(1) or ""


def _edit(xml: str, container: str, order: list[str], tag: str, element: str | None,
          insert_before: str = "") -> str:
    """Set a child of the first `container` in `xml` (an rPr, a pPr ...), creating the container when
    missing: before `insert_before` (a closing tag such as `</w:style>`) at its end."""
    found = _block(xml, container)
    if found:
        start, end, inner = found
        opening = re.match(rf"<w:{container}\b[^>]*>", xml[start:end])
        head = opening.group(0) if opening and not opening.group(0).endswith("/>") else f"<w:{container}>"
        return xml[:start] + f"{head}{_set(inner, order, tag, element)}</w:{container}>" + xml[end:]
    if element is None:
        return xml
    index = xml.rfind(insert_before) if insert_before else len(xml)
    if container == "pPr":
        for later in ("<w:rPr", "<w:tblPr", "<w:trPr", "<w:tcPr"):
            position = xml.find(later)
            if position != -1:
                index = min(index, position)
    return xml[:index] + f"<w:{container}>{element}</w:{container}>" + xml[index:]


def _style(styles: str, style_id: str) -> tuple[int, int] | None:
    match = re.search(rf'<w:style\b[^>]*\bw:styleId="{re.escape(style_id)}"[^>]*>.*?</w:style>', styles, re.S)
    return (match.start(), match.end()) if match else None


def _edit_style(styles: str, style_id: str, container: str, tag: str, element: str | None) -> str:
    span = _style(styles, style_id)
    if span is None:
        return styles
    block = styles[span[0]:span[1]]
    order = RPR_ORDER if container == "rPr" else PPR_ORDER
    # a paragraph style keeps pPr before rPr; _edit appends a missing container before </w:style>
    block = _edit(block, container, order, tag, element, "</w:style>")
    return styles[:span[0]] + block + styles[span[1]:]


def _fonts_element(main: str, east_asia: str | None = None) -> str:
    east = east_asia or main
    return f'<w:rFonts w:ascii="{main}" w:hAnsi="{main}" w:eastAsia="{east}" w:cs="{main}"/>'


def _sz(points: float) -> tuple[str, str]:
    half = max(1, round(points * 2))
    return f'<w:sz w:val="{half}"/>', f'<w:szCs w:val="{half}"/>'


PANDOC_STYLE_NAMES = {"BodyText": "Body Text", "FirstParagraph": "First Paragraph", "Compact": "Compact",
                      "ImageCaption": "Image Caption", "TableCaption": "Table Caption", "BlockText": "Block Text",
                      "FootnoteText": "Footnote Text", "DefinitionTerm": "Definition Term", "Definition": "Definition",
                      "CaptionedFigure": "Captioned Figure", "Figure": "Figure", "Table": "Table",
                      "VerbatimChar": "Verbatim Char", "SourceCode": "Source Code", "TOCHeading": "TOC Heading",
                      "Heading1": "heading 1", "Heading2": "heading 2", "Heading3": "heading 3",
                      "Heading4": "heading 4", "Heading5": "heading 5", "Heading6": "heading 6"}


def _style_text(styles: str, style_id: str) -> str | None:
    span = _style(styles, style_id)
    return styles[span[0]:span[1]] if span else None


def _inner(block: str, container: str) -> str | None:
    found = _block(block, container)
    return found[2] if found else None


def alias_styles(styles: str, aliases: dict[str, str]) -> str:
    """Make Pandoc's style `target` look like the template's own `source` (`Heading1: LRH1`): a template with
    house styles of its own names (LR H1, LR Normal...) is then used for the Heading 1 and Body Text Pandoc
    writes. A source based on the target only adds its own settings to it; any other source replaces the
    target's paragraph and character settings (and borders, for a table style)."""
    for target, source in aliases.items():
        source_block = _style_text(styles, source)
        if source_block is None or target == source:
            continue
        target_block = _style_text(styles, target)
        if target_block is None:
            # Pandoc's styles a template lacks (Body Text, Image Caption...): made from the source, under the name
            # Pandoc looks them up by
            kind = "table" if 'w:type="table"' in source_block else "character" if 'w:type="character"' in source_block else "paragraph"
            name = PANDOC_STYLE_NAMES.get(target, target)
            parent = re.search(r'<w:basedOn w:val="([^"]+)"', source_block)
            body = re.sub(r'^<w:style\b[^>]*>|</w:style>$', "", source_block)
            body = re.sub(r'<w:(?:name|link|autoRedefine|rsid)\b[^>]*/>', "", body)
            body = re.sub(r'<w:next\b[^>]*/>', "", body)
            created = (f'<w:style w:type="{kind}" w:styleId="{target}"><w:name w:val="{name}"/>'
                       + (f'<w:basedOn w:val="{parent.group(1)}"/>' if parent and not re.search(r"<w:basedOn", body) else "")
                       + body + "</w:style>")
            styles = styles.replace("</w:styles>", created + "</w:styles>")
            continue
        based_on = re.search(r'<w:basedOn w:val="([^"]+)"', source_block)
        merge = bool(based_on and based_on.group(1) == target)
        new = target_block
        for container, order in (("pPr", PPR_ORDER), ("rPr", RPR_ORDER)):
            source_inner = _inner(source_block, container)
            if source_inner is None:
                if not merge:
                    new = _edit(new, container, order, "__none__", None, "</w:style>") if _block(new, container) else new
                continue
            if not merge:
                # start from nothing: the source's own settings are the whole look
                found = _block(new, container)
                if found:
                    new = new[:found[0]] + f"<w:{container}></w:{container}>" + new[found[1]:]
            for tag, element in _children(source_inner):
                if tag in ("outlineLvl", "numPr", "pStyle", "rStyle"):
                    continue
                new = _edit(new, container, order, tag, element, "</w:style>")
        for container in ("tblPr", "tcPr", "trPr"):
            source_inner = _inner(source_block, container)
            if source_inner is not None and container == "tblPr":
                found = _block(new, container)
                if found:
                    new = new[:found[0]] + f"<w:tblPr>{source_inner}</w:tblPr>" + new[found[1]:]
        # keep the target's outline level for headings (the heading structure) but take the source's
        # parent when it is not the target itself
        if based_on and not merge and based_on.group(1) != target:
            new = re.sub(r'<w:basedOn w:val="[^"]+"\s*/>', f'<w:basedOn w:val="{based_on.group(1)}"/>', new, count=1)
        elif not based_on and not merge:
            new = re.sub(r'<w:basedOn w:val="[^"]+"\s*/>', "", new, count=1)     # the source is a root style
        span = _style(styles, target)
        styles = styles[:span[0]] + new + styles[span[1]:]
    return styles


def patch_styles(styles: str, spec: OfficeSpec, house: bool) -> str:
    """Fonts, size, language, line spacing and (with `house`) pdfmd's look, written into styles.xml."""
    if spec.aliases:
        styles = alias_styles(styles, spec.aliases)
    base = spec.size
    if base is None:
        found = re.search(r"<w:docDefaults>.*?<w:sz w:val=\"(\d+)\"", styles, re.S)
        base = int(found.group(1)) / 2 if found else 12.0
    scale = (spec.size / _doc_default_size(styles)) if spec.size else 1.0

    # document defaults: fonts (theme attributes would override names, so they are replaced), size, language
    defaults = re.search(r"<w:docDefaults>.*?</w:docDefaults>", styles, re.S)
    if defaults:
        block = defaults.group(0)
        if spec.main:
            block = _edit(block, "rPr", RPR_ORDER, "rFonts", _fonts_element(spec.main, spec.cjk), "</w:rPrDefault>")
        if spec.size:
            sz, szcs = _sz(spec.size)
            block = _edit(block, "rPr", RPR_ORDER, "sz", sz)
            block = _edit(block, "rPr", RPR_ORDER, "szCs", szcs)
        if spec.lang:
            tag = spec.lang.replace("_", "-")
            old = re.search(r"<w:lang\b[^>]*/>", block)
            east = re.search(r'w:eastAsia="([^"]+)"', old.group(0)).group(1) if old and "eastAsia" in old.group(0) else None
            bidi = re.search(r'w:bidi="([^"]+)"', old.group(0)).group(1) if old and "bidi" in old.group(0) else None
            element = f'<w:lang w:val="{tag}"' + (f' w:eastAsia="{east}"' if east else "") + (f' w:bidi="{bidi}"' if bidi else "") + "/>"
            block = _edit(block, "rPr", RPR_ORDER, "lang", element)
        if spec.stretch:
            line = round(240 * spec.stretch)
            spacing = re.search(r"<w:spacing\b[^>]*/>", block)
            attrs = re.sub(r'\s*w:line(Rule)?="[^"]*"', "", spacing.group(0)[len("<w:spacing"):-2]) if spacing else ""
            block = _edit(block, "pPr", PPR_ORDER, "spacing", f'<w:spacing{attrs} w:line="{line}" w:lineRule="auto"/>', "</w:pPrDefault>")
        styles = styles[:defaults.start()] + block + styles[defaults.end():]

    if scale != 1.0:
        # every other absolute size follows (headings, captions, footnotes, code)
        def rescale(match: re.Match) -> str:
            return f'{match.group(1)}{max(1, round(int(match.group(2)) * scale))}"'
        head, marker, tail = styles.partition("</w:docDefaults>")
        styles = head + marker + re.sub(r'(<w:sz(?:Cs)? w:val=")(\d+)"', rescale, tail)

    if spec.mono:
        for style_id in ("VerbatimChar", "SourceCode"):
            styles = _edit_style(styles, style_id, "rPr", "rFonts",
                                 f'<w:rFonts w:ascii="{spec.mono}" w:hAnsi="{spec.mono}" w:cs="{spec.mono}"/>')
    if spec.sans:
        for style_id in ("Title", "Subtitle", *(f"Heading{n}" for n in range(1, 10))):
            styles = _edit_style(styles, style_id, "rPr", "rFonts", _fonts_element(spec.sans))
    elif spec.main:
        # headings and titles use theme fonts in Pandoc's reference: follow the body font instead
        for style_id in ("Title", "Subtitle", "Author", "Date", "Abstract", *(f"Heading{n}" for n in range(1, 10))):
            span = _style(styles, style_id)
            if span and "Theme=" in styles[span[0]:span[1]]:
                styles = _edit_style(styles, style_id, "rPr", "rFonts", _fonts_element(spec.main, spec.cjk))
    if spec.indent:
        for style_id, indent in (("BodyText", 360), ("FirstParagraph", 0)):
            styles = _edit_style(styles, style_id, "pPr", "spacing", '<w:spacing w:before="0" w:after="0"/>')
            styles = _edit_style(styles, style_id, "pPr", "ind", f'<w:ind w:firstLine="{indent}"/>')
    if house:
        styles = _house(styles, base)
    return styles


def _doc_default_size(styles: str) -> float:
    found = re.search(r"<w:docDefaults>.*?<w:sz w:val=\"(\d+)\"", styles, re.S)
    return int(found.group(1)) / 2 if found else 12.0


def _house(styles: str, base: float) -> str:
    """pdfmd's Word look: black bold headings sized like a LaTeX article, a centred title block."""
    for style_id, factor, italic in (("Heading1", 1.2, False), ("Heading2", 1.0, False), ("Heading3", 1.0, False),
                                     ("Heading4", 1.0, True), ("Heading5", 1.0, True), ("Heading6", 1.0, True)):
        sz, szcs = _sz(base * factor)
        styles = _edit_style(styles, style_id, "rPr", "color", '<w:color w:val="000000"/>')
        styles = _edit_style(styles, style_id, "rPr", "b", "<w:b/>")
        styles = _edit_style(styles, style_id, "rPr", "bCs", "<w:bCs/>")
        styles = _edit_style(styles, style_id, "rPr", "i", "<w:i/>" if italic else None)
        styles = _edit_style(styles, style_id, "rPr", "sz", sz)
        styles = _edit_style(styles, style_id, "rPr", "szCs", szcs)
        styles = _edit_style(styles, style_id, "pPr", "spacing",
                             '<w:spacing w:before="240" w:after="120"/>' if factor > 1 else '<w:spacing w:before="200" w:after="80"/>')
    for style_id, factor, bold in (("Title", 1.44, False), ("Subtitle", 1.2, False), ("Author", 1.0, False),
                                   ("Date", 1.0, False)):
        sz, szcs = _sz(base * factor)
        styles = _edit_style(styles, style_id, "pPr", "jc", '<w:jc w:val="center"/>')
        styles = _edit_style(styles, style_id, "rPr", "color", '<w:color w:val="000000"/>')
        styles = _edit_style(styles, style_id, "rPr", "b", "<w:b/>" if bold else None)
        styles = _edit_style(styles, style_id, "rPr", "sz", sz)
        styles = _edit_style(styles, style_id, "rPr", "szCs", szcs)
    for style_id in ("CaptionedFigure", "Figure"):
        styles = _edit_style(styles, style_id, "pPr", "jc", '<w:jc w:val="center"/>')
    for style_id in ("ImageCaption", "TableCaption", "Caption"):
        sz, szcs = _sz(base * 0.9)
        styles = _edit_style(styles, style_id, "pPr", "jc", '<w:jc w:val="center"/>')
        styles = _edit_style(styles, style_id, "rPr", "i", "<w:i/>")
        styles = _edit_style(styles, style_id, "rPr", "sz", sz)
        styles = _edit_style(styles, style_id, "rPr", "szCs", szcs)
    span = _style(styles, "Table")
    if span and "<w:tblBorders" not in styles[span[0]:span[1]]:
        # booktabs: a rule above and below the table, one under the header row
        block = styles[span[0]:span[1]]
        rules = ('<w:tblBorders><w:top w:val="single" w:sz="8" w:space="0" w:color="auto"/>'
                 '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="auto"/></w:tblBorders>')
        block = re.sub(r"(<w:tblInd\b[^>]*/>)", lambda m: m.group(1) + rules, block, count=1)
        block = block.replace('<w:bottom w:val="single"/>', '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>', 1)
        styles = styles[:span[0]] + block + styles[span[1]:]
    return styles


def patch_document(document: str, spec: OfficeSpec) -> str:
    """The page size and margins (and a title page's own first page), written into the last section's `<w:sectPr>`."""
    if spec.title_page:
        sections = list(re.finditer(r"<w:sectPr\b[^>]*?(?:/>|>.*?</w:sectPr>)", document, re.S))
        if sections:
            last = sections[-1]
            text = last.group(0)
            if text.endswith("/>") and "</w:sectPr>" not in text:
                text = text[:-2] + "></w:sectPr>"
            start = re.match(r"<w:sectPr\b[^>]*>", text).group(0)
            inner = _set(text[len(start):-len("</w:sectPr>")], SECT_ORDER, "titlePg", "<w:titlePg/>")
            document = document[:last.start()] + start + inner + "</w:sectPr>" + document[last.end():]
    if not spec.has_page():
        return document
    sections = list(re.finditer(r"<w:sectPr\b[^>]*?(?:/>|>.*?</w:sectPr>)", document, re.S))
    width, height = spec.page_size()
    size = f'<w:pgSz w:w="{width}" w:h="{height}"' + (' w:orient="landscape"' if spec.landscape else "") + "/>"
    old = re.search(r'<w:pgMar\b[^>]*/>', sections[-1].group(0)) if sections else None

    def keep(name: str, default: int) -> int:
        found = re.search(rf'w:{name}="(-?\d+)"', old.group(0)) if old else None
        return int(found.group(1)) if found else default

    margins = {side: spec.margins.get(side, keep(side, 1440)) for side in ("top", "bottom", "left", "right")}
    edge = min(708, margins["top"] // 2, margins["bottom"] // 2)
    margin = (f'<w:pgMar w:top="{margins["top"]}" w:right="{margins["right"]}" w:bottom="{margins["bottom"]}" '
              f'w:left="{margins["left"]}" w:header="{keep("header", edge) if not spec.margins else edge}" '
              f'w:footer="{keep("footer", edge) if not spec.margins else edge}" w:gutter="{keep("gutter", 0)}"/>')
    if not sections:
        return document.replace("</w:body>", f"<w:sectPr>{size}{margin}</w:sectPr></w:body>")
    last = sections[-1]
    text = last.group(0)
    if text.endswith("/>") and "</w:sectPr>" not in text:
        text = text[:-2] + "></w:sectPr>"
    start = re.match(r"<w:sectPr\b[^>]*>", text).group(0)
    inner = text[len(start):-len("</w:sectPr>")]
    inner = _set(inner, SECT_ORDER, "pgSz", size)
    inner = _set(inner, SECT_ORDER, "pgMar", margin)
    return document[:last.start()] + start + inner + "</w:sectPr>" + document[last.end():]


EQUATION_STYLE = (
    '<w:style w:type="table" w:customStyle="1" w:styleId="PdfmdEquation"><w:name w:val="PdfmdEquation"/>'
    '<w:basedOn w:val="TableNormal"/><w:uiPriority w:val="99"/><w:unhideWhenUsed/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/>'
    '<w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="0" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/>'
    '<w:right w:w="0" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tcPr><w:vAlign w:val="center"/></w:tcPr></w:style>')
CENTERED_STYLE = ('<w:style w:type="paragraph" w:customStyle="1" w:styleId="PdfmdCentered"><w:name w:val="PdfmdCentered"/>'
                  '<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="center"/></w:pPr></w:style>')


def ensure_styles(styles: str) -> str:
    """Styles pdfmd's own output refers to, added when the reference document lacks them: the borderless
    table an equation and its number sit in."""
    if 'w:styleId="PdfmdEquation"' not in styles:
        styles = styles.replace("</w:styles>", EQUATION_STYLE + "</w:styles>")
    if 'w:styleId="PdfmdCentered"' not in styles:
        styles = styles.replace("</w:styles>", CENTERED_STYLE + "</w:styles>")
    # a picture's paragraph is centred and never indented like the body text it may inherit from
    for style_id, name in (("Figure", "Figure"), ("CaptionedFigure", "Captioned Figure")):
        if _style(styles, style_id) is None:
            styles = styles.replace("</w:styles>", (
                f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{style_id}"><w:name w:val="{name}"/>'
                '<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="center"/></w:pPr></w:style>'
                "</w:styles>"))
        else:
            styles = _edit_style(styles, style_id, "pPr", "ind", '<w:ind w:left="0" w:firstLine="0"/>')
            styles = _edit_style(styles, style_id, "pPr", "jc", '<w:jc w:val="center"/>')
    return styles


def patch_docx(data: bytes, spec: OfficeSpec, house: bool = True) -> bytes:
    """A copy of the `.docx`/`.dotx` bytes with the spec written into it (a template's content type is
    turned into a document's, so Pandoc and Word read it as an ordinary document)."""
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "word/styles.xml":
                content = ensure_styles(patch_styles(content.decode("utf-8"), spec, house)).encode("utf-8")
            elif item.filename == "word/document.xml":
                content = patch_document(content.decode("utf-8"), spec).encode("utf-8")
            elif spec.replace and re.match(r"word/(header|footer)\d*\.xml$", item.filename):
                text = content.decode("utf-8")
                for old, new in spec.replace.items():
                    text = text.replace(old, new.replace("&", "&amp;").replace("<", "&lt;"))
                content = text.encode("utf-8")
            elif item.filename in spec.media:
                content = spec.media[item.filename]
            elif item.filename == "[Content_Types].xml":
                content = content.replace(b"wordprocessingml.template.main+xml", b"wordprocessingml.document.main+xml")
            target.writestr(item, content)
    return out.getvalue()
