"""Import positions and notes from saved annotations without writing the PDF."""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
import sys

from pdfmd_base import core

from .anchors import geometry, source_files
from .pages import labels, printed_page, reader
from .record import RecordError, canonical, locked, read, validate

MARKUP = frozenset(("Highlight", "Underline", "StrikeOut", "Squiggly"))
AREA = frozenset(("Square", "FreeText"))


@dataclass
class Annotation:
    page: int
    kind: str
    boxes: list
    note: str = ""

    @property
    def position(self):
        return position(self.page, self.boxes)


def position(page, boxes):
    return page, tuple(sorted(tuple(round(value, 1) for value in box) for box in boxes))


def box(x, y):
    points = x + y
    if not all(math.isfinite(value) for value in points):
        return None
    bounds = [round(value, 1) for value in (min(x), min(y), max(x), max(y))]
    return bounds if bounds[0] < bounds[2] and bounds[1] < bounds[3] else None


def quad_boxes(points):
    if not points or len(points) % 8:
        return []
    boxes = [box(points[index:index + 8:2], points[index + 1:index + 8:2])
             for index in range(0, len(points), 8)]
    return boxes if all(boxes) else []


def pdf_annotations(pdf):
    for number, page in enumerate(pdf.pages, 1):
        array = page.get("/Annots")
        if array is None or not isinstance(items := array.get_object(), list):
            continue
        for ref in items:
            try:
                value = ref.get_object()
                subtype = str(value.get("/Subtype", "")).lstrip("/")
                if subtype in MARKUP:
                    points = value["/QuadPoints"] if "/QuadPoints" in value else ()
                    boxes = quad_boxes([float(n) for n in points])
                    kind = "text"
                elif subtype in AREA:
                    x0, y0, x1, y1 = map(float, value["/Rect"])
                    boxes = [box([x0, x1], [y0, y1])]
                    kind = "area"
                else:
                    continue
                contents = value["/Contents"] if "/Contents" in value else None
            except (AttributeError, TypeError, ValueError, KeyError):
                continue
            if boxes and all(boxes):
                yield Annotation(number, kind, boxes, contents if isinstance(contents, str) else "")


def cropped_text(program, file, page, annotation):
    """Crop in Poppler's rotated, top-left media space at the record's 0.1 pt precision."""
    left, bottom, right, top = geometry(page)
    rotation = page.rotation % 360
    text = []
    for x0, y0, x1, y1 in annotation.boxes:
        x0, y0, x1, y1 = max(x0, left), max(y0, bottom), min(x1, right), min(y1, top)
        if x0 >= x1 or y0 >= y1:
            continue
        if rotation == 90:
            x, y, width, height = y0 - bottom, x0 - left, y1 - y0, x1 - x0
        elif rotation == 180:
            x, y, width, height = right - x1, y0 - bottom, x1 - x0, y1 - y0
        elif rotation == 270:
            x, y, width, height = top - y1, right - x1, y1 - y0, x1 - x0
        else:
            x, y, width, height = x0 - left, top - y1, x1 - x0, y1 - y0
        number = str(annotation.page)
        px, py = (str(round(value * 10)) for value in (x, y))
        w, h = (str(max(1, round(value * 10))) for value in (width, height))
        done = subprocess.run([program, "-q", "-enc", "UTF-8", "-nopgbrk", "-f", number, "-l", number,
                               "-r", "720", "-x", px, "-y", py, "-W", w, "-H", h,
                               str(file), "-"], capture_output=True, encoding="utf-8", errors="replace")
        if done.returncode:
            raise RecordError("cannot extract text under the PDF annotation")
        text.extend(done.stdout.split())
    return " ".join(text)


def imported_records(data, path, file, key):
    matching = [item for item in source_files(data) if item.key == key and item.path(path.parent) == file]
    if len(matching) > 1:
        raise RecordError("the PDF has more than one source entry for this key")
    if not matching:
        raise RecordError("register this key and PDF first with pdfmd --excerpts sources add KEY FILE")
    source = matching[0]
    before = file.stat()
    pdf = reader(file)
    try:
        annotations = list(pdf_annotations(pdf))
        if sys.platform == "darwin":
            from .skim import skim_annotations

            annotations.extend(skim_annotations(file, len(pdf.pages)))
    except (core.pypdf.errors.PyPdfError, ValueError, AttributeError, TypeError, KeyError, IndexError):
        raise RecordError("cannot read source PDF annotations") from None
    seen = {position(part["pdf-page"], part["boxes"]) for record in data["excerpts"]
            if record.get("key") == key and record.get("file") == source.supplement
            for part in record.get("parts", ()) if part.get("boxes")}
    additions = []
    for annotation in annotations:
        at = annotation.position
        if at not in seen:
            seen.add(at)
            additions.append(annotation)
    if not additions:
        return []

    program = None
    if any(item.kind == "text" for item in additions):
        program = core.which("pdftotext")
        if not program:
            raise RecordError("importing PDF text highlights needs Poppler pdftotext")

    mapping = source.entry.get("pages")
    page_labels = labels(file) if mapping == "labels" else None
    records = []
    for item in additions:
        printed = page_labels[item.page - 1] if page_labels is not None else printed_page(mapping, item.page)
        part = {"pdf-page": item.page, "boxes": item.boxes}
        if item.kind == "text":
            part["text"] = cropped_text(program, file, pdf.pages[item.page - 1], item)
            part["text-from"] = "pdf"
        record = {"id": data["next-id"] + len(records), "key": key, "page": printed,
                  "kind": item.kind, "parts": [part]}
        if source.supplement is not None:
            record["file"] = source.supplement
        if item.note:
            record["note"] = item.note
        records.append(record)
    after = file.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise RecordError("source PDF changed during import")
    return records


def import_annotations(path, file, key, *, dry_run=False):
    file = Path(file).expanduser().resolve()

    def run(target, write):
        try:
            data = read(target)
        except FileNotFoundError:
            raise RecordError("register this key and PDF first with pdfmd --excerpts sources add KEY FILE") from None
        if data["pdfmd-excerpts"] != 1 and write:
            raise RecordError("newer record version cannot be written")
        records = imported_records(data, target, file, key)
        if write and records:
            data["excerpts"].extend(records)
            data["next-id"] += len(records)
            validate(data)
            core.atomic_write_text(target, canonical(data), newline="\n")
        return records

    if dry_run:
        return run(path, False)
    with locked(path) as target:
        return run(target, True)
