"""Writing a spec into an OpenDocument (`.odt`/`.ott`) reference document: the same job as docx.py,
done on `styles.xml` (page layout, default style, headings, code) as text edits."""

from __future__ import annotations

import io
import re
import zipfile

from pathlib import Path

from .spec import OfficeSpec
from .units import length_to_twips


def _attr(tag: str, name: str, value: str | None) -> str:
    """`tag` (an element's opening text) with attribute `name` set (or removed when value is None)."""
    pattern = re.compile(rf'\s+{re.escape(name)}="[^"]*"')
    tag = pattern.sub("", tag)
    if value is None:
        return tag
    end = tag.rfind("/>") if tag.rstrip().endswith("/>") else tag.rfind(">")
    return f'{tag[:end].rstrip()} {name}="{value}"{tag[end:]}'


def _inch(twips: int) -> str:
    return f"{twips / 1440:.4f}in"


def _style_span(styles: str, name: str) -> tuple[int, int] | None:
    match = re.search(rf'<style:style\b[^>]*\bstyle:name="{re.escape(name)}"[^>]*>.*?</style:style>', styles, re.S)
    return (match.start(), match.end()) if match else None


def _set_in(block: str, element: str, attrs: dict[str, str | None], parent_end: str = "</style:style>") -> str:
    """Set attributes on the (first) `<style:{element} .../>` of a style block, creating it when absent."""
    match = re.search(rf"<style:{element}\b[^>]*?(/>|>)", block)
    if match:
        opening = match.group(0)
        for key, value in attrs.items():
            opening = _attr(opening, key, value)
        return block[:match.start()] + opening + block[match.end():]
    created = f"<style:{element}" + "".join(f' {key}="{value}"' for key, value in attrs.items() if value is not None) + "/>"
    index = block.rfind(parent_end)
    return block[:index] + created + block[index:]


def _edit_style(styles: str, name: str, element: str, attrs: dict[str, str | None]) -> str:
    span = _style_span(styles, name)
    if span is None:
        return styles
    block = _set_in(styles[span[0]:span[1]], element, attrs)
    return styles[:span[0]] + block + styles[span[1]:]


def _font_face(styles: str, name: str) -> str:
    if re.search(rf'<style:font-face\b[^>]*style:name="{re.escape(name)}"', styles):
        return styles
    face = f'<style:font-face style:name="{name}" svg:font-family="\'{name}\'"/>'
    return styles.replace("</office:font-face-decls>", face + "</office:font-face-decls>", 1)


def _text_font(name: str) -> dict[str, str]:
    return {"style:font-name": name, "fo:font-family": f"&apos;{name}&apos;"}


PAGEBREAK_STYLE = ('<style:style style:name="Pagebreak" style:family="paragraph" style:parent-style-name="Standard">'
                   '<style:paragraph-properties fo:break-before="page"/></style:style>')


def with_pagebreak_style(styles: str) -> str:
    """`styles` with the `Pagebreak` paragraph style pdfmd_lua/pagebreak.lua writes page breaks in (v3.27.13), unless
    the reference already has one."""
    if _style_span(styles, "Pagebreak") is not None or "</office:styles>" not in styles:
        return styles
    return styles.replace("</office:styles>", PAGEBREAK_STYLE + "</office:styles>", 1)


def patch_styles(styles: str, spec: OfficeSpec, house: bool) -> str:
    styles = with_pagebreak_style(styles)
    if spec.has_page():
        width, height = spec.page_size()
        match = re.search(r"<style:page-layout-properties\b[^>]*>", styles)
        if match:
            tag = match.group(0)
            old = {side: re.search(rf'fo:margin-{side}="([\d.]+)in"', tag) for side in ("top", "bottom", "left", "right")}
            tag = _attr(tag, "fo:page-width", _inch(width))
            tag = _attr(tag, "fo:page-height", _inch(height))
            tag = _attr(tag, "style:print-orientation", "landscape" if spec.landscape else "portrait")
            for side in ("top", "bottom", "left", "right"):
                twips = spec.margins.get(side)
                if twips is not None:
                    tag = _attr(tag, f"fo:margin-{side}", _inch(twips))
                elif old[side] is None:
                    tag = _attr(tag, f"fo:margin-{side}", "1in")
            styles = styles[:match.start()] + tag + styles[match.end():]
    base = spec.size or 12.0
    default = re.search(r'<style:default-style style:family="paragraph">.*?</style:default-style>', styles, re.S)
    if default:
        block = default.group(0)
        attrs: dict[str, str | None] = {}
        if spec.main:
            styles = _font_face(styles, spec.main)
            attrs.update(_text_font(spec.main))
            attrs["style:font-name-asian"] = spec.cjk or spec.main
            if spec.cjk:
                styles = _font_face(styles, spec.cjk)
        if spec.size:
            attrs.update({"fo:font-size": f"{spec.size:g}pt", "style:font-size-asian": f"{spec.size:g}pt",
                          "style:font-size-complex": f"{spec.size:g}pt"})
        if spec.lang:
            language, _, country = spec.lang.replace("_", "-").partition("-")
            attrs["fo:language"] = language
            attrs["fo:country"] = country.upper() if country else None
        if attrs:
            block = _set_in(block, "text-properties", attrs, "</style:default-style>")
        if spec.stretch:
            block = _set_in(block, "paragraph-properties", {"fo:line-height": f"{round(spec.stretch * 100)}%"},
                            "</style:default-style>")
        styles = styles.replace(default.group(0), block, 1)
        if spec.main or spec.size:
            styles = _font_face(styles, spec.main) if spec.main else styles
    if spec.mono:
        styles = _font_face(styles, spec.mono)
        for name in ("Source_20_Text", "Preformatted_20_Text"):
            styles = _edit_style(styles, name, "text-properties", {**_text_font(spec.mono),
                                                                     "style:font-name-asian": spec.mono,
                                                                     "style:font-name-complex": spec.mono})
    heading_font = spec.sans or spec.main
    if heading_font:
        styles = _font_face(styles, heading_font)
        for name in ("Heading", "Title", "Subtitle"):
            styles = _edit_style(styles, name, "text-properties", {**_text_font(heading_font),
                                                                    "style:font-name-asian": heading_font})
    if spec.indent:
        styles = _edit_style(styles, "Text_20_body", "paragraph-properties",
                             {"fo:margin-top": "0in", "fo:margin-bottom": "0in", "fo:text-indent": "0.25in"})
        styles = _edit_style(styles, "First_20_paragraph", "paragraph-properties", {"fo:text-indent": "0in"})
    if house:
        size = f"{base:g}pt"
        styles = _edit_style(styles, "Heading", "text-properties",
                             {"fo:font-size": size, "style:font-size-asian": size, "style:font-size-complex": size})
        for name, percent in (("Heading_20_1", 120), ("Heading_20_2", 100), ("Heading_20_3", 100)):
            styles = _edit_style(styles, name, "text-properties",
                                 {"fo:font-size": f"{percent}%", "style:font-size-asian": f"{percent}%",
                                  "style:font-size-complex": f"{percent}%"})
        title = f"{base * 1.44:.1f}pt"
        styles = _edit_style(styles, "Title", "text-properties",
                             {"fo:font-size": title, "fo:font-weight": "normal", "style:font-size-asian": title,
                              "style:font-weight-asian": "normal", "style:font-size-complex": title,
                              "style:font-weight-complex": "normal"})
    return styles


def patch_odt(data: bytes, spec: OfficeSpec, house: bool = True) -> bytes:
    """A copy of the `.odt`/`.ott` bytes with the spec written into its styles (a template's mimetype is
    turned into a document's)."""
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "styles.xml":
                content = patch_styles(content.decode("utf-8"), spec, house).encode("utf-8")
            elif item.filename in ("mimetype", "META-INF/manifest.xml"):
                content = content.replace(b"opendocument.text-template", b"opendocument.text")
            if item.filename == "mimetype":
                target.writestr(item, content, compress_type=zipfile.ZIP_STORED)
            else:
                target.writestr(item, content)
    return out.getvalue()


INDENT_USED = re.compile(r'text:style-name="pdfmd-indent-([0-9p]+[a-z]+)"')


def finish_indents(path: Path) -> int:
    """Define the `pdfmd-indent-<length>` paragraph styles pdfmd_lua/indent.lua put on a stretch of text (Pandoc only names
    them in an `.odt`), based on Text body, with the first-line indent the name says; returns how many were added. A file
    with none of them is not touched. An em is 12 pt here, as in a Word file."""
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
        infos = {item.filename: item for item in archive.infolist()}
    content = entries.get("content.xml", b"").decode("utf-8")
    styles = entries.get("styles.xml", b"").decode("utf-8")
    added = 0
    for token in dict.fromkeys(INDENT_USED.findall(content)):
        name = f"pdfmd-indent-{token}"
        found = re.fullmatch(r"(\d+(?:p\d+)?)([a-z]+)", token)
        twips = length_to_twips(found.group(1).replace("p", ".") + found.group(2)) if found else None
        if twips is None or "</office:styles>" not in styles or _style_span(styles, name) is not None:
            continue
        style = (f'<style:style style:name="{name}" style:family="paragraph" style:parent-style-name="Text_20_body">'
                 f'<style:paragraph-properties fo:text-indent="{_inch(twips)}"/></style:style>')
        styles = styles.replace("</office:styles>", style + "</office:styles>", 1)
        added += 1
    if not added:
        return 0
    entries["styles.xml"] = styles.encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(infos[name] if name in infos else name, data)
    temporary.replace(path)
    return added
