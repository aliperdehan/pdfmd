"""Resolve office template text against the metadata of the document Pandoc actually built."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

TOKEN = re.compile(r"\$\$|\$([A-Za-z0-9_.-]+)\$")
CUSTOM = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
META = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
DC = "http://purl.org/dc/elements/1.1/"


def replacement_text(value: str, metadata: dict, xml: bool = False) -> str:
    """Expand names once (metadata can itself contain dollars); literal values retain their spacing."""
    if "$" not in value:
        return value

    def token(found: re.Match) -> str:
        if found.group(0) == "$$":
            return "$"
        item = metadata.get(found.group(1))
        text = "" if item is None else str(item)
        return escape(text) if xml else text

    return re.sub(r"[ \t\r\n]+", " ", TOKEN.sub(token, value)).strip()


def built_metadata(entries: dict[str, bytes], fallback: dict) -> dict:
    """Pandoc 3.1.3 and later store extra fields in custom properties, including fields set by filters.
    Standard document properties supply the reserved names; effective metadata supplies other writer variables.
    Read XML with a parser to decode entities before inserting text into another part.
    """
    metadata = dict(fallback)
    for name in ("docProps/custom.xml", "docProps/core.xml", "meta.xml"):
        if name not in entries:
            continue
        root = ElementTree.fromstring(entries[name])
        for node in root.iter():
            key = None
            if node.tag == f"{{{CUSTOM}}}property":
                key = node.get("name")
            elif node.tag == f"{{{META}}}user-defined":
                key = node.get(f"{{{META}}}name")
            elif node.tag.startswith("{" + DC + "}"):
                key = node.tag.split("}", 1)[1]
                key = "author" if key == "creator" else key
            if key:
                metadata[key] = "".join(node.itertext())
    return metadata


def finish_replacements(path: Path, replacements: dict, fallback: dict) -> bool:
    """Fill dollar-valued replacements in a finished Word/ODF file, including headers and footers.
    Literal Word replacements were already applied to its reference document and are left alone here.
    """
    with zipfile.ZipFile(path) as source:
        infos = source.infolist()
        entries = {item.filename: source.read(item.filename) for item in infos}
    metadata = built_metadata(entries, fallback)
    changed = False
    for name, content in entries.items():
        if not ((path.suffix.lower() == ".docx" and name.startswith("word/") and name.endswith(".xml"))
                or (path.suffix.lower() == ".odt" and name in ("content.xml", "styles.xml"))):
            continue
        text = content.decode("utf-8")
        for old, value in replacements.items():
            value = str(value)
            if "$" not in value:
                continue
            # Existing markup keys replace XML with XML; only interpolated metadata is escaped in that case.
            xml = "<" in str(old)
            value = replacement_text(value, metadata, xml=xml)
            text = text.replace(str(old), value if xml else escape(value))
        result = text.encode("utf-8")
        if result != content:
            entries[name] = result
            changed = True
    if changed:
        temporary = path.with_suffix(path.suffix + ".part")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
            for item in infos:
                target.writestr(item, entries[item.filename])
        temporary.replace(path)
    return changed
