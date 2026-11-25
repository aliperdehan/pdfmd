"""Version 1 records: validation, canonical JSON and serialised atomic updates.

Only the commands use this module in P1b; builds do not discover or open records.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import sys

from pdfmd_base import core
from pdfmd_log import emit

TOP = ("pdfmd-excerpts", "next-id", "sources", "excerpts")
SOURCE = ("file", "sha256", "size", "pages", "more")
RECORD = ("id", "key", "page", "locator", "kind", "label", "file", "quoting", "parts", "note", "created")
PART = ("pdf-page", "boxes", "text", "text-from")


class RecordError(ValueError):
    """A safe diagnostic: never interpolate the file's passages or notes."""


class RecordMissing(RecordError):
    """A named record or source does not exist."""


class RecordConflict(RecordError):
    """The requested change conflicts with existing project data."""


def check_source_paths(data, base, guard):
    for source in data["sources"].values():
        for entry in (source, *source.get("more", {}).values()):
            if entry.get("file"):
                guard(base / Path(entry["file"]).expanduser())


def positive(value):
    return type(value) is int and value > 0


def page_map(value):
    if value == "labels":
        return
    if not isinstance(value, list):
        raise RecordError("pages must be anchors or labels")
    previous = 0
    for anchor in value:
        if (not isinstance(anchor, list) or len(anchor) != 2 or not positive(anchor[0])
                or anchor[0] <= previous or not isinstance(anchor[1], str) or not anchor[1]):
            raise RecordError("page anchors must be ordered [positive PDF page, printed page] pairs")
        previous = anchor[0]


def validate(data, *, allow_duplicate_ids=False):
    if not isinstance(data, dict) or not positive(data.get("pdfmd-excerpts")):
        raise RecordError("missing or invalid pdfmd-excerpts version")
    if not positive(data.get("next-id")):
        raise RecordError("missing or invalid next-id")
    if not isinstance(data.get("sources"), dict) or not isinstance(data.get("excerpts"), list):
        raise RecordError("sources must be an object and excerpts an array")

    def source(item, supplement=False):
        if not isinstance(item, dict):
            raise RecordError("a source must be an object")
        for key in ("file", "sha256"):
            if key in item and not isinstance(item[key], str):
                raise RecordError(f"source {key} must be text")
        if "sha256" in item:
            import re
            if not re.fullmatch(r"[0-9a-fA-F]{64}", item["sha256"]):
                raise RecordError("source sha256 must have 64 hexadecimal digits")
        if "size" in item and (type(item["size"]) is not int or item["size"] < 0):
            raise RecordError("source size must be a non-negative integer")
        if "pages" in item:
            page_map(item["pages"])
        if "more" in item:
            if supplement or not isinstance(item["more"], dict):
                raise RecordError("source more must be a mapping of supplements")
            for extra in item["more"].values():
                source(extra, True)

    for item in data["sources"].values():
        source(item)
    seen = set()
    for record in data["excerpts"]:
        if not isinstance(record, dict) or not positive(record.get("id")):
            raise RecordError("excerpt id must be a positive integer")
        ident = record["id"]
        if ident in seen and not allow_duplicate_ids:
            raise RecordError(f"duplicate excerpt id {ident}")
        seen.add(ident)
        if ident >= data["next-id"]:
            raise RecordError("next-id must be above every excerpt id")
        if record.get("kind") not in ("text", "area", "remark"):
            raise RecordError(f"excerpt {ident}: invalid kind")
        if record["kind"] != "remark" and (not isinstance(record.get("key"), str) or not record["key"]):
            raise RecordError(f"excerpt {ident}: missing key")
        for key in ("key", "page", "locator", "label", "file", "quoting", "note", "created"):
            if key in record and not isinstance(record[key], str):
                raise RecordError(f"excerpt {ident}: {key} must be text")
        if record["kind"] != "remark" and "page" not in record:
            raise RecordError(f"excerpt {ident}: missing page (use an empty string for no locator)")
        parts = record.get("parts", [] if record["kind"] == "remark" else None)
        if not isinstance(parts, list):
            raise RecordError(f"excerpt {ident}: parts must be an array")
        for part in parts:
            if not isinstance(part, dict):
                raise RecordError(f"excerpt {ident}: a part must be an object")
            if "pdf-page" in part and not positive(part["pdf-page"]):
                raise RecordError(f"excerpt {ident}: pdf-page must be positive")
            if "text" in part and not isinstance(part["text"], str):
                raise RecordError(f"excerpt {ident}: part text must be text")
            if "text-from" in part and part["text-from"] not in ("pdf", "ocr", "typed"):
                raise RecordError(f"excerpt {ident}: invalid text-from")
            boxes = part.get("boxes", [])
            if not isinstance(boxes, list) or boxes and "pdf-page" not in part:
                raise RecordError(f"excerpt {ident}: boxes need a pdf-page")
            for box in boxes:
                if (not isinstance(box, list) or len(box) != 4
                        or not all(type(n) in (int, float) and math.isfinite(n) for n in box)
                        or round(box[0], 1) >= round(box[2], 1) or round(box[1], 1) >= round(box[3], 1)):
                    raise RecordError(f"excerpt {ident}: invalid box")
    return data


def read(path: Path, create=False, *, allow_duplicate_ids=False):
    if create and not path.exists():
        return {"pdfmd-excerpts": 1, "next-id": 1, "sources": {}, "excerpts": []}
    try:
        def invalid_constant(value):
            raise ValueError("non-finite JSON number")
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)
    except (ValueError, UnicodeError):
        raise RecordError("invalid JSON") from None
    validate(data, allow_duplicate_ids=allow_duplicate_ids)
    if data["pdfmd-excerpts"] > 1:
        emit("warning", None, "WARN  excerpts.json: newer record version; reading only", file=sys.stderr)
    return data


def ordered(item, keys):
    return {key: item[key] for key in (*keys, *sorted(set(item) - set(keys))) if key in item}


def canonical(data):
    """One source and one record per line; future fields survive at every level."""
    def source(item):
        result = ordered(item, SOURCE)
        if "more" in result:
            result["more"] = {key: source(value) for key, value in sorted(result["more"].items())}
        return result

    def record(item):
        result = ordered(item, RECORD)
        if "parts" in result:
            result["parts"] = []
            for part in item["parts"]:
                value = ordered(part, PART)
                if "boxes" in value:
                    value["boxes"] = [[round(n, 1) for n in box] for box in value["boxes"]]
                if "text" in value:
                    value["text"] = value["text"].replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
                result["parts"].append(value)
        return result

    dump = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False)
    sources = ",\n".join("    " + dump(key) + ": " + dump(source(item)) for key, item in sorted(data["sources"].items()))
    records = ",\n".join("    " + dump(record(item)) for item in sorted(data["excerpts"], key=lambda item: item["id"]))
    lines = ['{"pdfmd-excerpts": ' + dump(data["pdfmd-excerpts"]), ' "next-id": ' + dump(data["next-id"]),
             ' "sources": {\n' + sources + '\n }', ' "excerpts": [\n' + records + '\n ]']
    lines.extend(" " + dump(key) + ": " + dump(data[key]) for key in sorted(set(data) - set(TOP)))
    return ",\n".join(lines) + "}\n"


@contextmanager
def locked(path):
    """Lock a stable file of its own, not the JSON inode replaced by atomic_write_text.

    The lock file stays: unlinking it would let a waiting writer lock an old inode. It lives in pdfmd's cache, named by
    the record's path, so the project folder holds excerpts.json alone (a sibling `.lock` was left beside it, v3.34.1).
    OS locks are released on process exit, including an interrupted writer.
    """
    import hashlib
    path = path.resolve()
    folder = core.cache_root() / "excerpts-locks"
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / (hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:24] + ".lock")
    with open(lock, "a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield path
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def update(path, change, *, guard=None):
    with locked(path) as target:
        if guard is not None:
            guard(target)
        data = read(target, create=True)  # Always reread after acquiring the lock.
        if guard is not None:
            check_source_paths(data, target.parent, guard)
        if data["pdfmd-excerpts"] != 1:
            raise RecordError("newer record version cannot be written")
        result = change(data)
        validate(data)
        core.atomic_write_text(target, canonical(data), newline="\n")
        return result
