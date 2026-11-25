"""Lay out centred blocks with inkmd's parser, fonts, line wrapper and PDF writer."""

from __future__ import annotations

import unicodedata
from dataclasses import replace


def compile_centred(ink, text, marker, *, page_size, base_dir, orientation="portrait", font_size=None,
                    family="helvetica", autolinks=True, safe=True, html=True, allow_remote_images=False,
                    emoji_fallback="name"):
    # Match inkmd.compile's layout and filtering order. The extra operation
    # is to shift each wrapped line after its actual font widths are known.
    from pdfmd_inkmd.ast import Paragraph, Text
    from pdfmd_inkmd.embedded import (EmbeddedFontRef, document_uses_non_winansi, load_embedded_font,
                                      warn_missing_glyphs)
    from pdfmd_inkmd.render import apply_embedding

    defaults = ink.LayoutConfig()
    layout = replace(defaults, page_size=page_size, orientation=orientation, font_size=font_size or defaults.font_size)
    dimensions = ink.pdf.resolve_page_size(layout.page_size, layout.orientation)
    width, height = (dimension - 2 * layout.margin for dimension in dimensions)
    doc = ink.parse(unicodedata.normalize("NFC", text), autolinks=autolinks, html=html)
    opening, closing = (Text(f"{marker}:start"),), (Text(f"{marker}:end"),)
    depth = 0
    rendered = []
    token = ink.emoji.set_fallback_mode(emoji_fallback)
    try:
        for block in doc.blocks:
            if isinstance(block, Paragraph):
                if block.inlines == opening:
                    depth += 1
                    continue
                if block.inlines == closing:
                    depth -= 1
                    continue
            section = replace(doc, blocks=(block,))
            section = ink.filter_html(section, html=html)
            section = ink.filter_document(section, safe=safe)
            section = ink.resolve_images(section, base_dir=base_dir, allow_remote=allow_remote_images)
            rendered.extend((item, depth > 0) for item in ink.render_document(
                section, family=ink.FAMILIES[family], content_width=width, body_size=layout.font_size,
                line_spacing=layout.line_spacing, usable_height=height))
    finally:
        ink.emoji.reset_fallback_mode(token)

    blocks = [block for block, _ in rendered]
    if document_uses_non_winansi(block.runs for block in blocks):
        loaded = load_embedded_font()
        ref = EmbeddedFontRef(font=loaded[0], font_bytes=loaded[1]) if loaded else None
        missing = []
        blocks = apply_embedding(blocks, ref, missing)
        warn_missing_glyphs(missing)
    output = []
    for block, (_, centred) in zip(blocks, rendered):
        output.extend(centre_block(block, width) if centred else (block,))
    return ink.styled_pdf(output, margin=layout.margin, line_height_ratio=layout.line_spacing, page_dims=dimensions)


def centre_block(block, width):
    from pdfmd_inkmd.layout import run_text_width, wrap_runs

    if block.prepositioned:
        # Tables occupy their own column. Block images have a narrower box.
        shapes = tuple({**shape, "x_offset": (width - shape["width"]) / 2} if shape["kind"] == "image" else shape
                       for shape in block.prepositioned_shapes)
        return [replace(block, prepositioned_shapes=shapes)]
    if not block.runs or block.preserve_lines:
        return [block]
    lines = wrap_runs(block.runs, width - block.body_indent)
    result = []
    for index, line in enumerate(lines):
        markers = block.marker_runs if index == 0 else ()
        left = block.marker_x if markers else block.body_indent
        occupied = block.body_indent - left + sum(run_text_width(run) for run in line)
        shift = max(0, (width - occupied) / 2 - left)
        result.append(replace(block, runs=tuple(line), body_indent=block.body_indent + shift,
                              marker_x=block.marker_x + shift, marker_runs=markers,
                              compact=index > 0 or block.compact, space_above=0 if index else block.space_above,
                              space_below=block.space_below if index + 1 == len(lines) else 0))
    return result or [block]
