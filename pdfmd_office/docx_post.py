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
