"""A finished Word, OpenDocument or PowerPoint file's properties (v3.28.5).

Pandoc writes every metadata key it does not know into a `.docx` or `.pptx` (`docProps/custom.xml`) or an `.odt`
(`meta.xml`) as a custom property. pdfmd hands its filters their settings as metadata (`pdfmd-office-path`,
`pdfmd-raw-cache`, ...): folders and temporary files of the machine that built the file, the user's name in them, for
anyone who opens its properties. Those are taken out here, `pdfmd-options` with them (settings for pdfmd, not
properties of the document). Pandoc also writes a picture's source into its description in Word and PowerPoint: for
a picture pdfmd drew, a file in its cache (`~/.cache/pdfmd/office/...png`, the home folder spelled out); a description
that names a file in one of `folders` keeps the file's name alone. And when a house style drew its own cover and took
the title and authors out of the metadata (the LaTeX filter reports what they were), an empty Title and Author are
filled in.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

OWN_CUSTOM = re.compile(r'<property\b[^>]*\bname="pdfmd-[^"]*"[^>]*?(?:/>|>.*?</property>)', re.S)
OWN_ODF = re.compile(r'\s*<meta:user-defined\b[^>]*\bmeta:name="pdfmd-[^"]*"[^>]*?(?:/>|>.*?</meta:user-defined>)', re.S)


def fill(xml: str, tag: str, value: str) -> str:
    """`xml` with an empty `<tag>` given `value`; one with text of its own, or none at all, is left as it is."""
    empty = re.compile(rf"<{re.escape(tag)}(\s[^>]*)?(?:/>|>\s*</{re.escape(tag)}>)")
    return empty.sub(lambda found: f"<{tag}{found.group(1) or ''}>{escape(value)}</{tag}>", xml, count=1)


def finish_properties(path: Path, title: str | None = None, authors: list[str] | None = None,
                      folders: list[str] | tuple[str, ...] = ()) -> bool:
    """Take pdfmd's own settings out of `path`'s custom properties, a picture's folder (one of `folders`) out of its
    description, and fill an empty title and author (several authors as Word writes them, `A; B`); returns whether
    the file changed."""
    kind = path.suffix.lower()
    if kind not in (".docx", ".pptx", ".odt"):
        return False
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
        infos = {item.filename: item for item in archive.infolist()}
    creator = "; ".join(name for name in authors or [] if name)
    changed: dict[str, str] = {}

    def edit(name: str, change) -> None:
        if name in entries:
            text = entries[name].decode("utf-8")
            result = change(text)
            if result != text:
                changed[name] = result

    def custom(text: str) -> str:
        text = OWN_CUSTOM.sub("", text)
        numbers = iter(range(2, 1 << 20))         # the properties left are numbered from 2 again, as Word does
        return re.sub(r'\bpid="\d+"', lambda _: f'pid="{next(numbers)}"', text)

    def core(text: str) -> str:
        text = fill(text, "dc:title", title) if title else text
        return fill(text, "dc:creator", creator) if creator else text

    def odf(text: str) -> str:
        text = OWN_ODF.sub("", text)
        text = fill(text, "dc:title", title) if title else text
        if creator:
            text = fill(fill(text, "meta:initial-creator", creator), "dc:creator", creator)
        return text

    prefixes = sorted({escape(folder.rstrip("/\\")) for folder in folders if folder}, key=len, reverse=True)

    def pictures(text: str) -> str:
        def name_only(found: re.Match) -> str:
            value = found.group(2)
            if not any(value.startswith(prefix + separator) for prefix in prefixes for separator in "/\\"):
                return found.group(0)
            return f'{found.group(1)}="{re.split(r"[/\\]", value)[-1]}"'
        return re.sub(r'\b(descr|title)="([^"]*)"', name_only, text)

    if kind == ".odt":
        edit("meta.xml", odf)
    else:
        edit("docProps/custom.xml", custom)
        edit("docProps/core.xml", core)
        if prefixes:
            part = re.compile(r"(word|ppt/slides|ppt/notesSlides)/[^/]+\.xml$")
            for name in list(entries):
                if part.match(name):
                    edit(name, pictures)
    if not changed:
        return False
    for name, text in changed.items():
        entries[name] = text.encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(infos[name] if name in infos else name, data)    # an ODF file's `mimetype` stays first, stored
    temporary.replace(path)
    return True
