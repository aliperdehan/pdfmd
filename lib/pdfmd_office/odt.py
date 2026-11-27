"""Writing a spec into an OpenDocument (`.odt`/`.ott`) reference document: the same job as docx.py,
done on `styles.xml` (page layout, default style, headings, code) as text edits."""

from __future__ import annotations

import io
import re
import zipfile

from pathlib import Path
from xml.dom import Node, minidom

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
            if spec.paper or spec.landscape:
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


INDENT_USED = re.compile(r'text:style-name="pdfmd-(indent|hang)-([0-9p]+[a-z]+)"')


def with_paragraph_and_text_styles(content: str, styles: str) -> str:
    """Supply the styles Pandoc names for pdfmd's custom-styled paragraphs and spans."""
    for name, family, properties, parent in (
        ("PdfmdCenter", "paragraph", '<style:paragraph-properties fo:text-align="center"/>', "Text_20_body"),
        ("PdfmdHighlight", "text", '<style:text-properties fo:background-color="#ffff00"/>', ""),
        ("PdfmdWavy", "text", '<style:text-properties style:text-underline-style="wave" style:text-underline-type="single"/>', ""),
        ("PdfmdDotted", "text", '<style:text-properties style:text-underline-style="dotted" style:text-underline-type="single"/>', ""),
    ):
        if (f'text:style-name="{name}"' in content
                and not re.search(rf'<style:style\b[^>]*\bstyle:name="{name}"', styles)):
            base = f' style:parent-style-name="{parent}"' if parent else ""
            style = f'<style:style style:name="{name}" style:family="{family}"{base}>{properties}</style:style>'
            styles = styles.replace("</office:styles>", style + "</office:styles>", 1)
    for kind, token in dict.fromkeys(INDENT_USED.findall(content)):
        name = f"pdfmd-{kind}-{token}"
        found = re.fullmatch(r"(\d+(?:p\d+)?)([a-z]+)", token)
        twips = length_to_twips(found.group(1).replace("p", ".") + found.group(2)) if found else None
        if twips is None or "</office:styles>" not in styles or _style_span(styles, name) is not None:
            continue
        # `hang` is a whole hanging indent (the entries of a reference list), `indent` a first-line indent
        properties = (f'fo:margin-left="{_inch(twips)}" fo:text-indent="-{_inch(twips)}"' if kind == "hang"
                      else f'fo:text-indent="{_inch(twips)}"')
        style = (f'<style:style style:name="{name}" style:family="paragraph" style:parent-style-name="Text_20_body">'
                 f'<style:paragraph-properties {properties}/></style:style>')
        styles = styles.replace("</office:styles>", style + "</office:styles>", 1)

    return styles


def named_elements(node, tag: str) -> dict:
    return {element.getAttribute("style:name"): element for element in node.getElementsByTagName(tag)}


def unused_name(base: str, names: dict) -> str:
    name = base
    while name in names:
        name += "_"
    return name


def landscape_master(styles):
    """Copy the document's first master page and layout, preserving its margins, headers and footers."""
    masters = named_elements(styles, "style:master-page")
    portrait = next(iter(masters.values()), None)
    if portrait is None:
        return "", ""
    normal = portrait.getAttribute("style:name")
    layouts = named_elements(styles, "style:page-layout")
    layout = layouts.get(portrait.getAttribute("style:page-layout-name"))
    if layout is None:
        return normal, normal
    wide_layout = layout.cloneNode(True)
    properties = next(iter(wide_layout.getElementsByTagName("style:page-layout-properties")), None)
    if properties is None:
        return normal, normal
    width = properties.getAttribute("fo:page-width") or "8.5in"
    height = properties.getAttribute("fo:page-height") or "11in"
    if properties.getAttribute("style:print-orientation") == "landscape":
        return normal, normal
    if (length_to_twips(width) or 0) < (length_to_twips(height) or 0):
        width, height = height, width
    properties.setAttribute("fo:page-width", width)
    properties.setAttribute("fo:page-height", height)
    properties.setAttribute("style:print-orientation", "landscape")
    layout_name = unused_name("PdfmdLandscapeLayout", layouts)
    wide_layout.setAttribute("style:name", layout_name)
    layout.parentNode.appendChild(wide_layout)
    landscape = unused_name("PdfmdLandscape", masters)
    master = portrait.cloneNode(True)
    master.setAttribute("style:name", landscape)
    master.setAttribute("style:page-layout-name", layout_name)
    if master.hasAttribute("style:next-style-name"):
        master.removeAttribute("style:next-style-name")
    portrait.parentNode.appendChild(master)
    return normal, landscape


def page_transitions(body):
    """Yield page switches on the first paragraph, heading or table of a new range."""
    depth, wide, started = 0, False, False

    def walk(parent, can_break=True):
        nonlocal depth, wide, started
        for node in list(parent.childNodes):
            if node.nodeType == Node.COMMENT_NODE and node.data in ("pdfmd-landscape", "/pdfmd-landscape"):
                if can_break:
                    depth += 1 if node.data == "pdfmd-landscape" else -1
                parent.removeChild(node)
            elif node.nodeType == Node.ELEMENT_NODE:
                block = node.tagName in ("text:p", "text:h", "table:table")
                if block and can_break:
                    if (depth > 0) != wide:
                        wide = depth > 0
                        yield node, wide, started
                    started = True
                yield from walk(node, can_break and not block)

    yield from walk(body)


def landscape_styles(content: str, styles: str) -> tuple[str, str]:
    """Set the new master page directly on existing content, without inserting blank paragraphs."""
    document = minidom.parseString(content)
    body = document.getElementsByTagName("office:text")[0]
    transitions = list(page_transitions(body))
    if not transitions:
        return document.toxml(), styles
    references = minidom.parseString(styles)
    normal, landscape = landscape_master(references)
    if normal == landscape:
        return document.toxml(), styles
    automatic = document.getElementsByTagName("office:automatic-styles")[0]
    existing = named_elements(automatic, "style:style")
    occupied = {**named_elements(references, "style:style"), **existing}
    added = {}
    for block, wide, started in transitions:
        family = "table" if block.tagName == "table:table" else "paragraph"
        attr = "table:style-name" if family == "table" else "text:style-name"
        original = block.getAttribute(attr)
        master = landscape if wide else normal
        key = (family, original, master, started)
        if key not in added:
            # Automatic styles cannot be inherited by name. Clone those and inherit the named styles.
            if original in existing:
                style = existing[original].cloneNode(True)
            else:
                style = document.createElement("style:style")
                style.setAttribute("style:family", family)
                if original:
                    style.setAttribute("style:parent-style-name", original)
            name = unused_name(f"PdfmdPage{len(added) + 1}", occupied)
            style.setAttribute("style:name", name)
            style.setAttribute("style:master-page-name", master)
            if started:
                tag = f"style:{family}-properties"
                properties = next(iter(style.getElementsByTagName(tag)), None)
                if properties is None:
                    properties = style.insertBefore(document.createElement(tag), style.firstChild)
                properties.setAttribute("fo:break-before", "page")
            automatic.appendChild(style)
            occupied[name] = style
            added[key] = name
        block.setAttribute(attr, added[key])
    return document.toxml(), references.toxml()


def finish_odt(path: Path) -> int:
    """Supply the named styles and finish the landscape ranges of a Pandoc OpenDocument file."""
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
        infos = {item.filename: item for item in archive.infolist()}
    original_content = entries.get("content.xml", b"").decode("utf-8")
    original_styles = entries.get("styles.xml", b"").decode("utf-8")
    content = original_content
    styles = with_paragraph_and_text_styles(content, original_styles)
    if "<!--pdfmd-landscape-->" in content:
        content, styles = landscape_styles(content, styles)
    if content == original_content and styles == original_styles:
        return 0
    entries["content.xml"] = content.encode("utf-8")
    entries["styles.xml"] = styles.encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(infos[name] if name in infos else name, data)
    temporary.replace(path)
    return 1
