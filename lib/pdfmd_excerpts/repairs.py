"""Repair excerpt identities and their project markers under the record lock."""
from __future__ import annotations

from collections import defaultdict

from pdfmd_base import core

from .discovery import bibliography
from .markers import CITATION, canonical as marker_text, citation_mask, marker, prefix_setting, project_contexts, project_root
from .record import RecordError, canonical, locked, read, validate


def marker_edits(place, path, replacement):
    contexts = list(project_contexts(place, path))
    root = project_root(place, path)
    owners = defaultdict(set)
    for _, metadata, record in contexts:
        for file in metadata:
            owners[file.resolve()].add(record)
    changes = {}
    for document, metadata, record in contexts:
        if record != path:
            continue
        keys = bibliography(document, metadata)
        prefix = prefix_setting(document, metadata)
        for file, is_metadata in [(document, False), *((file.resolve(), True) for file in metadata)]:
            edit = edit_source(file, document, metadata, keys, prefix, replacement, is_metadata)
            if edit[-1] and (not file.is_relative_to(root) or is_metadata and owners[file] != {path}):
                raise RecordError(f"{core.display_path(file)}: cannot repair markers in outside or shared metadata")
            if file in changes and changes[file] != edit:
                raise RecordError(f"{core.display_path(file)}: excerpt markers have different meanings across documents")
            changes[file] = edit
    return [edit for edit in changes.values() if edit[-1]]


def edit_source(file, document, metadata, keys, prefix, replacement, is_metadata):
    original = file.read_bytes()
    text = original.decode("utf-8")
    scanned = citation_mask(text, document, metadata, include_metadata=True, metadata_only=is_metadata)
    edits = []
    for hit in CITATION.finditer(scanned):
        key = hit[1] or hit[2]
        parsed = marker(key, prefix)
        if parsed is None or key in keys:
            continue
        line = text.count("\n", 0, hit.start()) + 1
        where = f"{core.display_path(file)}:{line}"
        target = replacement(*parsed, where)
        if target is None:
            continue
        ident, named = target
        new = marker_text(ident, named, prefix)
        if marker(new[1:], prefix) != target or new[1:] in keys:
            raise RecordError(f"{where}: the rewritten excerpt marker would clash")
        if CITATION.fullmatch(new) is None:
            new = "@{" + new[1:] + "}"
        edits.append((hit.start(), hit.end(), new))
    for start, end, new in reversed(edits):
        text = text[:start] + new + text[end:]
    return file, original, text.encode("utf-8"), len(edits)


def write_repair(target, data, edits):
    validate(data)
    payload = canonical(data).encode("utf-8")
    for path, original, _, _ in edits:
        if path.read_bytes() != original:
            raise RecordError(f"{core.display_path(path)} changed during the excerpt repair")
    done = []
    try:
        for path, original, edited, _ in edits:
            core.atomic_write_bytes(path, edited)
            done.append((path, original))
        core.atomic_write_bytes(target, payload)
    except (OSError, KeyboardInterrupt):
        for path, original in reversed(done):
            core.atomic_write_bytes(path, original)
        raise
    return [{"file": core.display_path(path), "markers": count} for path, _, _, count in edits]


def rekey(place, path, old, new):
    if old == new or not new:
        raise RecordError("rekey needs a different, non-empty destination key")
    with locked(path) as target:
        data = read(target)
        if data["pdfmd-excerpts"] != 1:
            raise RecordError("newer record version cannot be written")
        records = [record for record in data["excerpts"] if record["kind"] != "remark"]
        if new in data["sources"] or any(record["key"] == new for record in records):
            raise RecordError(f"destination source {new} already has excerpt records or a file")
        owned = [record for record in records if record["key"] == old]
        if not owned and old not in data["sources"]:
            raise RecordError(f"no source named {old}")
        ids = {record["id"] for record in owned}
        edits = marker_edits(place, target, lambda ident, key, _: (ident, new) if ident in ids and key == old else None)
        if old in data["sources"]:
            data["sources"][new] = data["sources"].pop(old)
        for record in owned:
            record["key"] = new
        files = write_repair(target, data, edits)
    return {"old": old, "new": new, "records": len(owned), "files": files}


def renumber(place, path):
    with locked(path) as target:
        data = read(target, allow_duplicate_ids=True)
        if data["pdfmd-excerpts"] != 1:
            raise RecordError("newer record version cannot be written")
        groups = defaultdict(list)
        for record in data["excerpts"]:
            groups[record["id"]].append(record)
        duplicates = {ident: records for ident, records in groups.items() if len(records) > 1}
        if not duplicates:
            return {"renumbered": [], "files": []}
        numbers = defaultdict(list)
        assigned = []
        for ident, records in sorted(duplicates.items()):
            for record in records:
                key = None if record["kind"] == "remark" else record["key"]
                new = data["next-id"]
                data["next-id"] += 1
                record["id"] = new
                numbers[ident, key].append(new)
                assigned.append({"old": ident, "new": new, "key": key})

        def replacement(ident, key, where):
            if ident not in duplicates:
                return None
            choices = numbers.get((ident, key), []) if key is not None else []
            if len(choices) != 1:
                raise RecordError(f"{where}: excerpt {ident} is ambiguous; identify the record before renumbering")
            return choices[0], key

        edits = marker_edits(place, target, replacement)
        files = write_repair(target, data, edits)
    return {"renumbered": assigned, "files": files}
