"""Typed PDF document information shared by the finishing passes."""

from pdfmd_base import core


def add_metadata(writer, values, *, replace=False):
    """Use pypdf's text conversion for text, preserving PDF name objects as names.

    /Trapped is a name in the PDF format. Passing it through add_metadata (or
    the metadata setter) would turn it into a text string. Other name-valued
    entries are preserved too; a text string beginning with / stays text.
    """
    from pypdf.generic import NameObject

    names = {NameObject(key): value for key, value in values.items() if isinstance(value, NameObject)}
    if replace:
        writer.metadata = None
    writer.add_metadata({key: value for key, value in values.items() if not isinstance(value, NameObject)})
    writer._info.update(names)


def clone_pdf(source):
    """Clone a reader or path without lowering its declared PDF version.

    Older pypdf has no keep_initial_header constructor option. Set the
    header after cloning; tolerate older releases without the property.
    """
    from pathlib import Path

    reader = core.pypdf.PdfReader(source) if isinstance(source, (str, Path)) else source
    writer = core.pypdf.PdfWriter(clone_from=reader)
    header = getattr(reader, 'pdf_header', None)
    if header:
        if hasattr(writer, 'pdf_header'):
            writer.pdf_header = header
        elif hasattr(writer, '_header'):
            writer._header = header.encode() if isinstance(header, str) else header
    return writer
