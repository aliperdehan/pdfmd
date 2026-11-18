"""Remove page-number fields while preserving the rest of the office document."""

import re
import zipfile
from pathlib import Path
from xml.dom import Node, minidom

from pdfmd_base import atomic_file


WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ODT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


def page_field(instruction: str) -> bool:
    words = instruction.split()
    return bool(words and words[0].upper() == "PAGE")


def word_fields(document):
    for field in document.getElementsByTagNameNS(WORD, "fldSimple"):
        if page_field(field.getAttributeNS(WORD, "instr")):
            yield field
    # Word can split the instruction and the cached value across several runs.
    stack = []
    for run in document.getElementsByTagNameNS(WORD, "r"):
        for node in run.childNodes:
            if node.nodeType != Node.ELEMENT_NODE or (node.namespaceURI == WORD and node.localName == "rPr"):
                continue
            kind = node.localName if node.namespaceURI == WORD else ""
            boundary = node.getAttributeNS(WORD, "fldCharType") if kind == "fldChar" else ""
            if boundary == "begin":
                stack.append(([], []))
            for _, nodes in stack:
                nodes.append(node)
            if stack and kind == "instrText":
                stack[-1][0].extend(child.data for child in node.childNodes if child.nodeType == Node.TEXT_NODE)
            if stack and boundary == "end":
                instruction, nodes = stack.pop()
                if page_field("".join(instruction)):
                    yield from nodes


def remove(path: Path) -> None:
    """Patch Word and OpenDocument fields, with an atomic replacement of the zip."""
    word = path.suffix.lower() == ".docx"
    changes = {}
    with zipfile.ZipFile(path) as source:
        for name in source.namelist():
            if word:
                if not re.fullmatch(r"word/(?:document|header[^/]*|footer[^/]*)\.xml", name):
                    continue
            elif name not in ("styles.xml", "content.xml"):
                continue
            document = minidom.parseString(source.read(name))
            fields = list(word_fields(document) if word else document.getElementsByTagNameNS(ODT, "page-number"))
            for field in fields:
                if field.parentNode is not None:
                    field.parentNode.removeChild(field)
            if fields:
                changes[name] = document.toxml(encoding="utf-8")
        if not changes:
            return
        with atomic_file(path) as temporary:
            with zipfile.ZipFile(temporary, "w") as target:
                for info in source.infolist():
                    target.writestr(info, changes[info.filename] if info.filename in changes else source.read(info))
            source.close()  # Windows cannot replace an open archive.
