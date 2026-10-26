"""Finishing a `.docx` Pandoc wrote: what the Lua filter marked in an image's title.

A fragment's image arrives as a 300 dpi PNG with `title="pdfmd:svg=FILE;dp=DEPTH"`. Here the SVG is
added beside it (Word 2016+ draws the vector, older readers and LibreOffice the PNG), an inline picture
is lowered by its depth so it sits on the baseline, one wider than the text is scaled to fit, and the
marker is removed.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .docx import _edit_style
from .units import length_to_twips

REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
SVG_EXTENSION = ('<a:extLst><a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">'
                 '<asvg:svgBlip xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main" r:embed="%s"/>'
                 '</a:ext></a:extLst>')
RUN = re.compile(r"<w:r>(?:(?!</w:r>).)*?pdfmd:svg=[^\"]*\"(?:(?!</w:r>).)*?</w:r>", re.S)


def text_width_emu(document: str) -> int | None:
    sections = re.findall(r"<w:sectPr\b.*?</w:sectPr>", document, re.S)
    if not sections:
        return None
    size = re.search(r'<w:pgSz[^>]*w:w="(\d+)"', sections[-1])
    margin = re.search(r'<w:pgMar[^>]*w:right="(\d+)"[^>]*w:left="(\d+)"|<w:pgMar[^>]*w:left="(\d+)"[^>]*w:right="(\d+)"',
                       sections[-1])
    if not size or not margin:
        return None
    left_right = [int(value) for value in margin.groups() if value]
    return (int(size.group(1)) - sum(left_right)) * 635


PDFMD_TABLE_STYLES = ("PdfmdGrid", "PdfmdBooktabs")
TABLE = re.compile(r"<w:tbl>.*?</w:tbl>", re.S)
TABLE_PROPERTIES = re.compile(r"<w:tblPr>(.*?)</w:tblPr>", re.S)


def centre_table(match: re.Match) -> str:
    """One `<w:tbl>`: pdfmd's own table styles say `jc center`, but LibreOffice ignores a table style's
    alignment, so a table narrower than the text sat at the left margin there. The alignment is written
    into the table itself (a table that already says where it sits, or uses another style, is left alone)."""
    table = match.group(0)
    found = TABLE_PROPERTIES.search(table)
    if found is None or "<w:jc " in found.group(1) or not any(
            f'w:val="{name}"' in found.group(1) for name in PDFMD_TABLE_STYLES):
        return table
    inner = found.group(1)
    width = re.search(r"<w:tblW\b[^>]*/>", inner)
    anchor = width or re.search(r"<w:tblStyle\b[^>]*/>", inner)
    if anchor is None:
        return table
    inner = inner[:anchor.end()] + '<w:jc w:val="center"/>' + inner[anchor.end():]
    return table[:found.start(1)] + inner + table[found.end(1):]


def centre_tables(path: Path) -> int:
    """Write the centring into every table of pdfmd's own styles (see centre_table); returns how many changed."""
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
        infos = {item.filename: item for item in archive.infolist()}
    document = entries["word/document.xml"].decode("utf-8")
    changed = 0

    def count(match: re.Match) -> str:
        nonlocal changed
        result = centre_table(match)
        changed += result != match.group(0)
        return result

    document = TABLE.sub(count, document)
    if not changed:
        return 0
    entries["word/document.xml"] = document.encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(infos[name] if name in infos else name, data)
    temporary.replace(path)
    return changed


def finish_docx(path: Path) -> int:
    """Patch the file in place; returns the number of pictures finished."""
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
        infos = {item.filename: item for item in archive.infolist()}
    document = entries["word/document.xml"].decode("utf-8")
    relationships = entries["word/_rels/document.xml.rels"].decode("utf-8")
    types = entries["[Content_Types].xml"].decode("utf-8")
    limit = text_width_emu(document)
    added: dict[str, tuple[str, bytes]] = {}
    count = 0

    def fix(match: re.Match) -> str:
        nonlocal relationships, count
        run = match.group(0)
        marker = re.search(r'title="pdfmd:svg=([^;"]*);dp=([\d.]+)"', run)
        if not marker:
            return run
        svg_path, depth = Path(marker.group(1).replace("&amp;", "&")), float(marker.group(2))
        run = run.replace(marker.group(0), "").replace("  ", " ")
        blip = re.search(r'<a:blip r:embed="(rId\d+)"\s*/>', run)
        if blip and svg_path.is_file():
            if str(svg_path) not in added:
                number = len(added) + 1
                rid = f"rIdPdfmd{number}"
                added[str(svg_path)] = (rid, svg_path.read_bytes())
                relationships = relationships.replace(
                    "</Relationships>", f'<Relationship Id="{rid}" Type="{REL_TYPE}" Target="media/pdfmd-{number}.svg"/></Relationships>')
            rid = added[str(svg_path)][0]
            run = run.replace(blip.group(0), f'<a:blip r:embed="{blip.group(1)}">' + SVG_EXTENSION % rid + "</a:blip>")
        extent = re.search(r'<wp:extent cx="(\d+)" cy="(\d+)"', run)
        if extent and limit and int(extent.group(1)) > limit:
            factor = limit / int(extent.group(1))
            cx, cy = limit, round(int(extent.group(2)) * factor)
            run = re.sub(r'(<wp:extent cx=")\d+(" cy=")\d+', rf"\g<1>{cx}\g<2>{cy}", run)
            run = re.sub(r'(<a:ext cx=")\d+(" cy=")\d+', rf"\g<1>{cx}\g<2>{cy}", run)
            depth *= factor
        if depth > 0.05 and "<w:rPr>" not in run:
            run = run.replace("<w:drawing>", f'<w:rPr><w:position w:val="{-round(depth * 2)}"/></w:rPr><w:drawing>', 1)
        count += 1
        return run

    document = RUN.sub(fix, document)
    if count == 0:
        return 0
    if 'Extension="svg"' not in types:
        types = types.replace("<Default ", '<Default Extension="svg" ContentType="image/svg+xml"/><Default ', 1)
    entries["word/document.xml"] = document.encode("utf-8")
    entries["word/_rels/document.xml.rels"] = relationships.encode("utf-8")
    entries["[Content_Types].xml"] = types.encode("utf-8")
    for number, (_, data) in enumerate(added.values(), start=1):
        entries[f"word/media/pdfmd-{number}.svg"] = data
    temporary = path.with_suffix(path.suffix + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(infos[name] if name in infos else name, data)
    temporary.replace(path)
    return count


# ---- universal markup (v3.29.28): what pdfmd_lua/markup.lua marks in a Word file ----------------------------------------
# Pandoc makes a style it does not find in the reference document (a Div or Span with `custom-style`) without any formatting
# and an openxml section break as it was written. Both are finished here, for the reference document of the user's too. The highlight
# is a character shading, not `w:highlight`: Word takes both in a style, LibreOffice only the shading.
MARKUP_STYLES = {"PdfmdCenter": ("pPr", "jc", '<w:jc w:val="center"/>'),
                 "PdfmdHighlight": ("rPr", "shd", '<w:shd w:val="clear" w:color="auto" w:fill="FFFF00"/>')}
PORTRAIT_MARK, LANDSCAPE_MARK = "00D0F001", "00D0F002"
BREAK = r'<w:p><w:pPr><w:sectPr w:rsidR="%s"\s*(?:/>|></w:sectPr>)</w:pPr></w:p>'
SECTION = re.compile(r"<w:sectPr\b[^>]*?(?:/>|>(.*?)</w:sectPr>)", re.S)
LETTER = (12240, 15840)


def style_markup(styles: str) -> tuple[str, int]:
    """The formatting of the markup styles, written into the ones that have none (a style the user's reference document
    defines with its own centring or highlight is left as it is)."""
    changed = 0
    for style_id, (container, tag, element) in MARKUP_STYLES.items():
        found = re.search(r'<w:style\b[^>]*w:styleId="%s"[^>]*>.*?</w:style>' % style_id, styles, re.S)
        if found is None or f"<w:{tag}" in found.group(0):
            continue
        block = found.group(0)
        have = re.search(rf"<w:{container}>(.*?)</w:{container}>", block, re.S)
        if have:
            block = block[:have.start(1)] + element + have.group(1) + block[have.end(1):]
        else:
            block = block[:-len("</w:style>")] + f"<w:{container}>{element}</w:{container}></w:style>"
        styles = styles[:found.start()] + block + styles[found.end():]
        changed += 1
    return styles, changed


INDENT_STYLE = re.compile(r'w:styleId="pdfmd-indent-([0-9p]+[a-z]+)"')


def indent_twips(token: str) -> int | None:
    """`pdfmd-indent-1p5em` -> 360 twips (an em is 12 pt here; the filter writes a "." as "p")."""
    found = re.fullmatch(r"(\d+(?:p\d+)?)([a-z]+)", token)
    return length_to_twips(found.group(1).replace("p", ".") + found.group(2)) if found else None


def style_indents(styles: str) -> tuple[str, int]:
    """The first-line indent of the `pdfmd-indent-<length>` paragraph styles pdfmd_lua/indent.lua puts on a stretch of
    text (Pandoc makes the styles empty, based on Body Text, which brings the document's own indent)."""
    changed = 0
    for token in dict.fromkeys(INDENT_STYLE.findall(styles)):
        twips = indent_twips(token)
        if twips is None:
            continue
        styles = _edit_style(styles, f"pdfmd-indent-{token}", "pPr", "ind", f'<w:ind w:firstLine="{twips}"/>')
        changed += 1
    return styles, changed


def final_section(document: str) -> re.Match | None:
    """The `<w:sectPr>` of the whole body: the last one, after every paragraph."""
    found = None
    for found in SECTION.finditer(document):
        pass
    if found is None or "</w:p>" in document[found.end():]:
        return None
    return found


def landscape_of(inner: str) -> str:
    size = re.search(r"<w:pgSz\b[^>]*/>", inner)
    if size is None:
        return inner + '<w:pgSz w:w="%d" w:h="%d" w:orient="landscape"/>' % (LETTER[1], LETTER[0])
    width, height = (re.search(rf'w:{name}="(\d+)"', size.group(0)) for name in ("w", "h"))
    if not width or not height:
        return inner
    wide, high = max(int(width.group(1)), int(height.group(1))), min(int(width.group(1)), int(height.group(1)))
    return inner[:size.start()] + f'<w:pgSz w:w="{wide}" w:h="{high}" w:orient="landscape"/>' + inner[size.end():]


def portrait_of(inner: str) -> str:
    size = re.search(r"<w:pgSz\b[^>]*/>", inner)
    if size is None:
        return inner + '<w:pgSz w:w="%d" w:h="%d"/>' % LETTER
    return inner


def sections_markup(document: str) -> tuple[str, int]:
    """Each landscape block of the filter is two marker paragraphs; they become section breaks that carry the document's own
    page setup (size, margins, headers and footers of its last section), the block's turned. A block at the very start or end
    makes no empty page: the first or the last section takes the setting itself."""
    portrait_break, landscape_break = BREAK % PORTRAIT_MARK, BREAK % LANDSCAPE_MARK
    if PORTRAIT_MARK not in document and LANDSCAPE_MARK not in document:
        return document, 0
    document = re.sub(landscape_break + r"\s*" + portrait_break, "", document)         # two blocks in a row: one section
    final = final_section(document)
    inner = (final.group(1) or "") if final else ""
    first_page = "<w:titlePg/>" in inner
    inner = inner.replace("<w:titlePg/>", "")
    inner = re.sub(r"<w:type\b[^>]*/>", "", inner)
    portrait_inner, landscape_inner = portrait_of(inner), landscape_of(portrait_of(inner))
    count = 0
    ends_landscape = False
    start = re.search(r"<w:body>\s*(" + portrait_break + ")", document)
    if start:
        document = document[:start.start(1)] + document[start.end(1):]
    end = re.search("(" + landscape_break + r")\s*<w:sectPr\b", document)
    if end and final is not None:
        document = document[:end.start(1)] + document[end.end(1):]
        ends_landscape = True
    first = True

    def section(kind_inner: str, mark: str) -> str:
        nonlocal first
        body = kind_inner + ("<w:titlePg/>" if first and first_page else "")
        first = False
        return f'<w:p><w:pPr><w:sectPr w:rsidR="{mark}">{body}</w:sectPr></w:pPr></w:p>'

    def replace(match: re.Match) -> str:
        nonlocal count
        count += 1
        return section(portrait_inner if PORTRAIT_MARK in match.group(0) else landscape_inner,
                       PORTRAIT_MARK if PORTRAIT_MARK in match.group(0) else LANDSCAPE_MARK)

    document = re.sub(r'<w:p><w:pPr><w:sectPr w:rsidR="(?:%s|%s)"\s*(?:/>|></w:sectPr>)</w:pPr></w:p>' % (PORTRAIT_MARK, LANDSCAPE_MARK),
                      replace, document)
    final = final_section(document)
    if final is not None:
        body = landscape_inner if ends_landscape else portrait_inner
        if first_page and first:                       # no break kept: this is the first section
            body += "<w:titlePg/>"
        attrs = re.match(r"<w:sectPr\b[^>]*?(?=/?>)", final.group(0)).group(0)
        document = document[:final.start()] + attrs + ">" + body + "</w:sectPr>" + document[final.end():]
    return document, count + int(ends_landscape) + (1 if start else 0)


def finish_markup(path: Path) -> int:
    """Write the formatting of pdfmd's markup (centred text, highlighted text, landscape pages) into a Word file Pandoc made;
    returns how many things changed. A file with none of it is not touched."""
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
        infos = {item.filename: item for item in archive.infolist()}
    document = entries["word/document.xml"].decode("utf-8")
    styles = entries["word/styles.xml"].decode("utf-8") if "word/styles.xml" in entries else ""
    used = any(f'w:val="{name}"' in document for name in MARKUP_STYLES)
    styles, styled = style_markup(styles) if used else (styles, 0)
    styles, indented = style_indents(styles) if "pdfmd-indent-" in styles else (styles, 0)
    styled += indented
    document, sections = sections_markup(document)
    if not styled and not sections:
        return 0
    entries["word/document.xml"] = document.encode("utf-8")
    if styled:
        entries["word/styles.xml"] = styles.encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(infos[name] if name in infos else name, data)
    temporary.replace(path)
    return styled + sections
