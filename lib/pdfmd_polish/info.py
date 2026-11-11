"""Typed PDF document information shared by the finishing passes."""

core = None


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
