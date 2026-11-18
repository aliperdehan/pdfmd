"""PDF checks and re-anchoring. Source PDFs are opened read-only."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess
import tempfile
from xml.etree import ElementTree as ET

from pdfmd_base import core
from pdfmd_check.lint import Problem

from .pages import reader
from .record import RecordError, canonical, locked, read, validate


@dataclass(frozen=True)
class SourceFile:
    key: str
    supplement: str | None
    entry: dict
    parts: list

    @property
    def label(self):
        return f"{self.key} ({self.supplement})" if self.supplement else self.key

    def path(self, base):
        hint = self.entry.get("file")
        return (base / Path(hint).expanduser()).resolve() if hint else None


def source_files(data):
    entries = {}
    for key, source in data["sources"].items():
        entries[key, None] = source
        entries.update({(key, name): entry for name, entry in source.get("more", {}).items()})
    anchored = defaultdict(list)
    for record in data["excerpts"]:
        if record["kind"] != "remark":
            anchored[record["key"], record.get("file")].extend(
                (record, index, part) for index, part in enumerate(record.get("parts", []), 1) if "pdf-page" in part)
    return [SourceFile(key, name, entries.get((key, name), {}), anchored.get((key, name), []))
            for key, name in sorted(entries.keys() | {key for key, parts in anchored.items() if parts},
                                    key=lambda key: (key[0], key[1] or ""))]


def geometry(page):
    return tuple(float(value) for value in (page.mediabox.left, page.mediabox.bottom,
                                            page.mediabox.right, page.mediabox.top))


def contains_box(bounds, box):
    left, bottom, right, top = bounds
    x0, y0, x1, y1 = box
    return left <= x0 < x1 <= right and bottom <= y0 < y1 <= top


def pdf_problems(data, path, *, show=None):
    label = (show or core.display_path)(path)
    results, affected = [], set()
    for source in source_files(data):
        file = source.path(path.parent)
        name = "source " + source.label
        if file is None or not file.is_file():
            results.append(Problem(label, 0, "excerpt-source-missing", f"{name}: PDF is missing"))
            continue
        try:
            if source.entry.get("sha256"):
                digest = hashlib.sha256(file.read_bytes()).hexdigest()
                if digest != source.entry["sha256"].casefold():
                    results.append(Problem(label, 0, "excerpt-source-changed",
                                           f"{name}: PDF hash changed; use reanchor"))
                    affected.update(record["id"] for record, _, _ in source.parts)
            if not source.parts:
                continue
            pdf = reader(file)
            bounds = [geometry(page) for page in pdf.pages]
        except Exception:
            results.append(Problem(label, 0, "excerpt-box", f"{name}: cannot read PDF page bounds"))
            affected.update(record["id"] for record, _, _ in source.parts)
            continue
        for record, index, part in source.parts:
            page = part["pdf-page"]
            place = f"excerpt {record['id']}, part {index}"
            if page > len(bounds):
                results.append(Problem(label, 0, "excerpt-box", f"{place}: PDF page {page} is outside {name}"))
                affected.add(record["id"])
            elif any(not contains_box(bounds[page - 1], box) for box in part.get("boxes", [])):
                results.append(Problem(label, 0, "excerpt-box", f"{place}: a box is outside PDF page {page}"))
                affected.add(record["id"])
    return results, affected


def default_box(word, width, height, page):
    """Convert Poppler's rotated top-left coordinates to PDF default user space."""
    left, bottom, right, top = geometry(page)
    w, h = right - left, top - bottom
    rotation = page.rotation % 360

    def point(x, y):
        x, y = x / width, y / height
        if rotation == 90:
            return left + y * w, bottom + x * h
        if rotation == 180:
            return right - x * w, bottom + y * h
        if rotation == 270:
            return right - y * w, top - x * h
        return left + x * w, top - y * h

    x0, y0 = point(float(word.attrib["xMin"]), float(word.attrib["yMin"]))
    x1, y1 = point(float(word.attrib["xMax"]), float(word.attrib["yMax"]))
    return [round(value, 1) for value in (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))]


def words_by_page(file, pdf, program):
    with tempfile.TemporaryDirectory(prefix="pdfmd-excerpt-anchors-") as scratch:
        destination = Path(scratch) / "boxes.html"
        done = subprocess.run([program, "-bbox-layout", str(file), str(destination)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if done.returncode or not destination.is_file():
            raise RecordError("cannot extract source PDF text and boxes")
        try:
            tree = ET.parse(destination)
        except ET.ParseError:
            raise RecordError("cannot read extracted source PDF boxes") from None
    results = []
    for node, page in zip(tree.findall(".//{*}page"), pdf.pages):
        width, height = float(node.attrib["width"]), float(node.attrib["height"])
        lines = []
        for line in node.findall(".//{*}line"):
            lines.append([(word.text or "", default_box(word, width, height, page))
                          for word in line.findall("{*}word")])
        results.append(PageWords(lines))
    if len(results) != len(pdf.pages):
        raise RecordError("PDF page count differs from the extracted text")
    return results


class PageWords:
    def __init__(self, lines):
        text = []
        self.words = []
        offset = 0
        for index, line in enumerate(lines):
            for word, box in line:
                piece = "".join(word.split())
                if piece:
                    self.words.append((offset, offset + len(piece), index, box))
                    text.append(piece)
                    offset += len(piece)
        self.text = "".join(text)

    def find(self, wanted):
        first = self.text.find(wanted)
        if first < 0:
            return []
        if self.text.find(wanted, first + 1) >= 0:
            return None
        last = first + len(wanted)
        lines = {}
        for start, end, index, box in self.words:
            if start < last and end > first:
                current = lines.get(index)
                lines[index] = ([min(current[0], box[0]), min(current[1], box[1]),
                                 max(current[2], box[2]), max(current[3], box[3])] if current is not None else box)
        return list(lines.values())


def locate(pages, wanted, old):
    if not wanted:
        return None
    if old <= len(pages):
        same = pages[old - 1].find(wanted)
        if same:
            return old, same
        if same is None:
            return None
    found = []
    for page, text in enumerate(pages, 1):
        if page == old:
            continue
        boxes = text.find(wanted)
        if boxes is None:
            return None
        if boxes:
            found.append((page, boxes))
    return found[0] if len(found) == 1 else None


def plan(source, file, pdf, program):
    pages = words_by_page(file, pdf, program) if any(record["kind"] == "text" for record, _, _ in source.parts) else []
    changes, manual, shifts, areas = [], [], [], []
    for record, index, part in source.parts:
        if record["kind"] == "area":
            areas.append((record, index, part))
            continue
        old = part["pdf-page"]
        found = locate(pages, "".join(part.get("text", "").split()), old)
        if found is None or not all(contains_box(geometry(pdf.pages[found[0] - 1]), box) for box in found[1]):
            manual.append({"id": record["id"], "part": index, "reason": "text did not locate one valid position"})
        else:
            number, boxes = found
            changes.append((record["id"], index, part, number, boxes))
            shifts.append(number - old)
    uniform = len(set(shifts)) == 1 and not manual
    for record, index, part in areas:
        number = part["pdf-page"] + shifts[0] if uniform else 0
        boxes = part.get("boxes", [])
        if 1 <= number <= len(pdf.pages) and all(contains_box(geometry(pdf.pages[number - 1]), box) for box in boxes):
            changes.append((record["id"], index, part, number, boxes))
        else:
            manual.append({"id": record["id"], "part": index, "reason": "no uniform valid page move for this area"})
    return changes, manual


def reanchor(path, key):
    with locked(path) as target:
        data = read(target)
        if data["pdfmd-excerpts"] != 1:
            raise RecordError("newer record version cannot be written")
        sources = [source for source in source_files(data) if source.key == key]
        if not sources:
            raise RecordError(f"no source named {key}")
        answer, wrote = [], False
        for source in sources:
            file = source.path(path.parent)
            if file is None or not file.is_file():
                answer.append({"source": source.label, "state": "missing"})
                continue
            content = file.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest == source.entry.get("sha256", "").casefold():
                answer.append({"source": source.label, "state": "unchanged"})
                continue
            program = core.which("pdftotext")
            if not program and any(record["kind"] == "text" for record, _, _ in source.parts):
                raise RecordError("reanchor needs Poppler pdftotext to locate text and boxes")
            try:
                pdf = reader(file)
                changes, manual = plan(source, file, pdf, program)
            except (ValueError, OSError, KeyError, ZeroDivisionError) as error:
                if isinstance(error, RecordError):
                    raise
                raise RecordError("cannot locate text and boxes in the source PDF") from None
            locations = [{"id": ident, "part": index, "from": part["pdf-page"], "to": number}
                         for ident, index, part, number, _ in changes]
            if manual:
                answer.append({"source": source.label, "state": "review", "located": locations, "unresolved": manual})
                continue
            if file.read_bytes() != content:
                raise RecordError("source PDF changed during reanchor")
            for _, _, part, number, boxes in changes:
                part["pdf-page"] = number
                if "boxes" in part or boxes:
                    part["boxes"] = boxes
            source.entry.update(sha256=digest, size=len(content))
            answer.append({"source": source.label, "state": "updated", "located": locations})
            wrote = True
        if wrote:
            validate(data)
            core.atomic_write_text(target, canonical(data), newline="\n")
    return answer
