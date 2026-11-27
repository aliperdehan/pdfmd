"""Package finished PDF pages as pictures in Word and OpenDocument files."""

from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfmd_base import atomic_file

from .docx_post import REL_TYPE, SVG_EXTENSION
from .fragments import convert_pages

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006"
_A = "http://schemas.openxmlformats.org/drawingml/2006"
_ODT = "application/vnd.oasis.opendocument.text"
_XML = '<?xml version="1.0" encoding="UTF-8"?>'


def _relationships(relationships: list[tuple[str, str, str]]) -> str:
    elements = "".join(f'<Relationship Id="{key}" Type="{kind}" Target="{target}"/>'
                       for key, kind, target in relationships)
    return f'{_XML}<Relationships xmlns="{_PKG}/relationships">{elements}</Relationships>'


def _section(width: int, height: int) -> str:
    orientation = ' w:orient="landscape"' if width > height else ""
    return (f'<w:sectPr><w:pgSz w:w="{width}" w:h="{height}"{orientation}/>'
            '<w:pgMar w:top="0" w:right="0" w:bottom="0" w:left="0" w:header="0" w:footer="0" w:gutter="0"/>'
            '</w:sectPr>')


def _anchor(index: int, width: int, height: int, extension: str) -> str:
    # DrawingML uses EMU; a Word page specifies its size in whole twips.
    extent = f'cx="{width * 635}" cy="{height * 635}"'
    return (
        '<w:r><w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="0"'
        ' behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
        '<wp:simplePos x="0" y="0"/>'
        '<wp:positionH relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionH>'
        '<wp:positionV relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionV>'
        f'<wp:extent {extent}/><wp:wrapNone/><wp:docPr id="{index}" name="Page {index}"/>'
        f'<a:graphic><a:graphicData uri="{_A}/picture"><pic:pic>'
        f'<pic:nvPicPr><pic:cNvPr id="{index}" name="Page {index}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="png{index}">{extension}</a:blip>'
        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext {extent}/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:anchor></w:drawing></w:r>'
    )


def _word(archive: zipfile.ZipFile, pages: list[dict]) -> None:
    content_types = (
        f'{_XML}<Types xmlns="{_PKG}/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="png" ContentType="image/png"/><Default Extension="svg" ContentType="image/svg+xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    archive.writestr("[Content_Types].xml", content_types)
    archive.writestr("_rels/.rels", _relationships([("rId1", _R + "/officeDocument", "word/document.xml")]))
    relationships, body = [], []
    for index, page in enumerate(pages, 1):
        # A positive dimension needs at least one twip in this file format.
        width, height = (max(1, round(page[key] * 20)) for key in ("width", "height"))
        section = _section(width, height)
        fallback = f"media/page-{index}.png"
        archive.write(page["png"], "word/" + fallback)
        relationships.append((f"png{index}", REL_TYPE, fallback))
        extension = ""
        if Path(page["svg"]).is_file():
            vector = f"media/page-{index}.svg"
            archive.write(page["svg"], "word/" + vector)
            relationships.append((f"svg{index}", REL_TYPE, vector))
            extension = SVG_EXTENSION % f"svg{index}"
        # The paragraph is an anchor carrier. An exact one-twip line keeps
        # it inside even a page whose Word size rounds down to one twip.
        properties = '<w:spacing w:before="0" w:after="0" w:line="1" w:lineRule="exact"/>'
        if index < len(pages):
            properties += section
        body.append(f'<w:p><w:pPr>{properties}</w:pPr>{_anchor(index, width, height, extension)}</w:p>')
    body.append(section)
    archive.writestr("word/document.xml",
                     f'{_XML}<w:document xmlns:w="{_W}" xmlns:r="{_R}" xmlns:a="{_A}/main"'
                     f' xmlns:wp="{_A}/wordprocessingDrawing" xmlns:pic="{_A}/picture"><w:body>'
                     + "".join(body) + '</w:body></w:document>')
    archive.writestr("word/_rels/document.xml.rels", _relationships(relationships))


_ODF_NAMESPACES = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
    'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" office:version="1.2"'
)
_ODF_MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"


def _odt(archive: zipfile.ZipFile, pages: list[dict]) -> None:
    archive.writestr("mimetype", _ODT, compress_type=zipfile.ZIP_STORED)
    entries = [("/", _ODT), ("content.xml", "text/xml"), ("styles.xml", "text/xml")]
    layouts, masters, paragraphs, body = [], [], [], []
    for index, page in enumerate(pages, 1):
        width, height = page["width"], page["height"]
        dimensions = f'fo:page-width="{width:.5f}pt" fo:page-height="{height:.5f}pt"'
        orientation = "landscape" if width > height else "portrait"
        layouts.append(f'<style:page-layout style:name="Layout{index}"><style:page-layout-properties {dimensions}'
                       f' style:print-orientation="{orientation}" fo:margin="0pt"/></style:page-layout>')
        masters.append(f'<style:master-page style:name="Master{index}" style:page-layout-name="Layout{index}"/>')
        page_break = ' fo:break-before="page"' if index > 1 else ""
        paragraphs.append(f'<style:style style:name="Page{index}" style:family="paragraph" style:master-page-name="Master{index}">'
                          f'<style:paragraph-properties fo:margin="0pt"{page_break}/></style:style>')
        images = []
        for extension, mime in (("svg", "image/svg+xml"), ("png", "image/png")):
            if Path(page[extension]).is_file():
                name = f"Pictures/page-{index}.{extension}"
                archive.write(page[extension], name)
                entries.append((name, mime))
                images.append(f'<draw:image xlink:href="{name}" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/>')
        body.append(f'<text:p text:style-name="Page{index}"><draw:frame draw:style-name="Picture" draw:name="Page {index}"'
                    f' text:anchor-type="paragraph" svg:x="0pt" svg:y="0pt" svg:width="{width:.5f}pt" svg:height="{height:.5f}pt">'
                    + "".join(images) + '</draw:frame></text:p>')
    frame = ('<style:style style:name="Picture" style:family="graphic">'
             '<style:graphic-properties style:wrap="run-through" style:horizontal-pos="from-left"'
             ' style:horizontal-rel="page" style:vertical-pos="from-top" style:vertical-rel="page"/></style:style>')
    archive.writestr("styles.xml", f'{_XML}<office:document-styles {_ODF_NAMESPACES}><office:automatic-styles>'
                     + "".join(layouts) + '</office:automatic-styles><office:master-styles>'
                     + "".join(masters) + '</office:master-styles></office:document-styles>')
    archive.writestr("content.xml", f'{_XML}<office:document-content {_ODF_NAMESPACES}><office:automatic-styles>'
                     + frame + "".join(paragraphs) + '</office:automatic-styles><office:body><office:text>'
                     + "".join(body) + '</office:text></office:body></office:document-content>')
    manifest = "".join(f'<manifest:file-entry manifest:full-path="{name}" manifest:media-type="{mime}"'
                       + (' manifest:version="1.2"/>' if name == "/" else '/>') for name, mime in entries)
    archive.writestr("META-INF/manifest.xml",
                     f'{_XML}<manifest:manifest xmlns:manifest="{_ODF_MANIFEST}" manifest:version="1.2">'
                     + manifest + '</manifest:manifest>')


def write(pdf: Path, destinations: dict[str, Path], dpi: float, background) -> list[Path]:
    """Write one full-page picture per crop and add each reader's vector fallback."""
    from pdfmd_crop.images import _pages

    with TemporaryDirectory(prefix="pdfmd-cropped-office-") as scratch:
        folder = Path(scratch)
        if background is not None:
            from pdfmd_crop.colour import colour_for, matte

            if colour := colour_for(background):
                painted = folder / "background.pdf"
                matte(pdf, painted, colour)
                pdf = painted
        pages = convert_pages(pdf, _pages(pdf), folder, jobs=1, export_dpi=dpi)
        for kind, destination in destinations.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            with atomic_file(destination) as temporary, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                (_word if kind == "docx" else _odt)(archive, pages)
    return list(destinations.values())
