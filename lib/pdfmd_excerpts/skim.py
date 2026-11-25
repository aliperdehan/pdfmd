"""Read Skim's archived notes and its macOS plain-text fallback."""
from __future__ import annotations

import bz2
import plistlib
import re
import subprocess
import sys
from xml.parsers.expat import ExpatError

from .import_pdf import Annotation, AREA, MARKUP, box, quad_boxes
from pdfmd_log import emit

STEM = "net_sourceforge_skim-app"
# Foundation serialises NSRect and NSPoint as strings of decimal coordinates.
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
# Skim exports one "* TYPE, page N" heading per note, with a blank line before its text.
TEXT_HEADING = re.compile(r"^(\* [^,\n]+, page [0-9]+)[ \t]*(?:\n\n|\n|\Z)", re.M)
READ_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, RecursionError, EOFError, ExpatError)


def get_attribute(file, name):
    done = subprocess.run(["/usr/bin/xattr", "-px", name, str(file)], capture_output=True)
    return bytes.fromhex(done.stdout.decode("ascii")) if done.returncode == 0 else None


def unpack(file, data, suffix, *, plain_text=False):
    def decode(data):
        if data.startswith(b"BZh"):
            data = bz2.decompress(data)
        try:
            return plistlib.loads(data)
        except plistlib.InvalidFileException:
            if not plain_text:
                raise
            return data.decode("utf-8-sig")

    notes = decode(data)
    if isinstance(notes, dict) and notes.get(STEM + "_has_wrapper"):
        stem = notes[STEM + "_unique_key"]
        count = notes[STEM + "_number_of_fragments"]
        if not isinstance(stem, str) or not stem.startswith(STEM + "_") or type(count) is not int or count < 1:
            raise ValueError("invalid Skim fragments")
        pieces = []
        for number in range(count):
            part = get_attribute(file, f"{stem}-{number}{suffix}")
            if part is None:
                raise ValueError("missing Skim fragment")
            pieces.append(part)
        notes = decode(b"".join(pieces))
    return notes


def archive_items(archive):
    """Decode Foundation collections as data. The class names never instantiate objects."""
    if isinstance(archive, list):
        return archive
    if not isinstance(archive, dict) or archive.get("$archiver") != "NSKeyedArchiver":
        raise ValueError("invalid Skim archive")
    objects = archive["$objects"]

    def decode(ref):
        if not isinstance(ref, plistlib.UID):
            return ref
        if ref.data == 0:
            return None
        value = objects[ref.data]
        if not isinstance(value, dict):
            return value
        if "NS.keys" in value:
            return {decode(key): decode(item) for key, item in zip(value["NS.keys"], value["NS.objects"])}
        if "NS.objects" in value:
            return [decode(item) for item in value["NS.objects"]]
        return decode(value.get("NS.string"))

    result = decode(archive["$top"]["root"])
    if not isinstance(result, list):
        raise ValueError("invalid Skim note list")
    return result


def coordinates(value):
    return [float(number) for number in NUMBER.findall(value)] if isinstance(value, str) else []


def note_annotation(fields, page_count):
    if not isinstance(fields, dict):
        return None
    number, subtype = fields.get("pageIndex"), fields.get("type")
    bounds = coordinates(fields.get("bounds"))
    if (type(number) is not int or not 0 <= number < page_count or len(bounds) != 4
            or not isinstance(subtype, str) or subtype not in (MARKUP | AREA)):
        return None
    x, y, width, height = bounds
    if subtype in AREA:
        boxes, kind = [box([x, x + width], [y, y + height])], "area"
    else:
        values = fields.get("quadrilateralPoints")
        pairs = [coordinates(point) for point in values] if isinstance(values, list) else []
        if any(len(pair) != 2 for pair in pairs):
            return None
        boxes, kind = quad_boxes([coord for dx, dy in pairs for coord in (x + dx, y + dy)]), "text"
    note = fields.get("contents")
    if boxes and all(boxes):
        return Annotation(number + 1, kind, boxes, note if isinstance(note, str) else "")
    return None


def skim_annotations(file, page_count):
    unreadable = False
    for suffix in ("#S", ""):
        try:
            data = get_attribute(file, STEM + "_notes" + suffix)
            if data is not None:
                items = archive_items(unpack(file, data, suffix))
                annotations = [item for fields in items if (item := note_annotation(fields, page_count)) is not None]
                return annotations, []
        except READ_ERRORS:
            unreadable = True
    if unreadable:
        emit("warning", None, "WARN  excerpts: cannot read the Skim notes archive", file=sys.stderr)
    for suffix in ("#S", ""):
        try:
            data = get_attribute(file, STEM + "_text_notes" + suffix)
            if data is not None:
                text = unpack(file, data, suffix, plain_text=True)
                if isinstance(text, str):
                    chunks = TEXT_HEADING.split(text.replace("\r\n", "\n"))
                    # Skim appends a space and blank line after each non-empty note.
                    notes = [{"heading": heading, "text": content.rstrip("\n").removesuffix(" "),
                              "status": "not imported: no position"}
                             for heading, content in zip(chunks[1::2], chunks[2::2])]
                    if notes:
                        return [], notes
        except READ_ERRORS:
            continue
    return [], []
