"""Local API adapter for the excerpt commands and their source PDFs."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import BinaryIO

from pdfmd_serve.core import ApiError

from .cli import UsageError, add_source, problem_answers, remove_record, save_record
from .discovery import bibliography, context, discover
from .markers import locations, prefix_setting
from .record import (RECORD, RecordConflict, RecordError, RecordMissing, check_source_paths,
                     page_map, positive, read)


@dataclass
class SourcePDF:
    file: BinaryIO
    start: int
    length: int
    size: int
    partial: bool

    @property
    def headers(self):
        headers = {"Accept-Ranges": "bytes"}
        if self.partial:
            headers["Content-Range"] = f"bytes {self.start}-{self.start + self.length - 1}/{self.size}"
        return headers

    def write_to(self, destination):
        self.file.seek(self.start)
        remaining = self.length
        while remaining:
            chunk = self.file.read(min(remaining, 64 * 1024))
            if not chunk:
                break
            destination.write(chunk)
            remaining -= len(chunk)


def open_source(file, range_header):
    if not file.is_file():
        raise RecordMissing("the source PDF does not exist")
    handle = file.open("rb")
    try:
        if handle.read(5) != b"%PDF-":
            raise ApiError(415, "not_pdf", "the named source does not start with %PDF-")
        size = os.fstat(handle.fileno()).st_size
        # The source viewer needs single byte ranges. Ignore unsupported units and multipart ranges.
        range_header = range_header or ""
        if not range_header.lower().startswith("bytes=") or "," in range_header:
            return SourcePDF(handle, 0, size, size, False)
        match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", range_header, re.I)
        if match is not None:
            first, last = match.groups()
            try:
                if first:
                    start, end = int(first), min(int(last), size - 1) if last else size - 1
                else:
                    start, end = max(size - int(last), 0), size - 1
                if start <= end:
                    return SourcePDF(handle, start, end - start + 1, size, True)
            except ValueError:
                pass
        raise ApiError(416, "range", "the requested byte range cannot be served", size=size)
    except BaseException:
        handle.close()
        raise


def excerpt_id(query):
    try:
        ident = int(query.get("id", ""))
    except ValueError:
        ident = None
    if not positive(ident):
        raise ApiError(400, "id", "id must be a positive integer")
    return ident


def dispatch(server, action, query, body, range_header):
    def guard(path):
        return server.resolve(str(path))[0]

    def show(path):
        return server.resolve(str(path))[1]

    try:
        document, metadata = context(server.root, guard=guard)
        path = guard(discover(document, metadata))
        if action in ("create", "edit"):
            if body.keys() - (set(RECORD) - {"id", "created"}):
                raise ApiError(400, "body", "the body must contain editable excerpt fields")
            ident = excerpt_id(query) if action == "edit" else None
            record = save_record(path, body, prefix_setting(document, metadata), ident=ident, guard=guard)
            return (200 if ident is not None else 201), record
        if action == "remove":
            force, detach = body.get("force", False), body.get("detach", False)
            if (body.keys() - {"force", "detach"} or type(force) is not bool or type(detach) is not bool
                    or (force and detach)):
                raise ApiError(400, "body", "use at most one of force or detach")
            ident = excerpt_id(query)
            entries = {} if force else bibliography(document, metadata, guard=guard)
            return 200, remove_record(path, ident, server.root, entries, force=force, detach=detach, guard=guard)
        if action == "add_source":
            key = body.get("key")
            if not isinstance(key, str) or not key or body.keys() - {"key", "file", "pages"}:
                raise ApiError(400, "body", "a source needs a key and file, with optional pages")
            file, _ = server.resolve(body.get("file"))
            if "pages" in body:
                page_map(body["pages"])
            return 201, add_source(path, key, file, body.get("pages"), guard=guard)

        data = read(path)
        if action == "source":
            key = query.get("key")
            if not key:
                raise ApiError(400, "key", "a source key is needed")
            hint = data["sources"].get(key, {}).get("file")
            if not hint:
                raise RecordMissing("the key has no source PDF in excerpts.json")
            pdf = open_source(guard(path.parent / Path(hint).expanduser()), range_header)
            return (206 if pdf.partial else 200), pdf

        from .checks import project_checks

        check_source_paths(data, path.parent, guard)
        problems = problem_answers(project_checks(server.root, path, data, guard=guard, show=show)[0])
        if action == "check":
            return 200, {"problems": problems}
        entries = bibliography(document, metadata, guard=guard)
        places = locations(server.root, path, entries, data, guard=guard, show=show)
        return 200, {"record": data, "locations": places, "problems": problems}
    except RecordMissing as error:
        raise ApiError(404, "excerpt_missing", str(error)) from None
    except RecordConflict as error:
        raise ApiError(409, "excerpt_conflict", str(error)) from None
    except (RecordError, UsageError) as error:
        raise ApiError(422, "excerpt", str(error)) from None
    except (ValueError, RuntimeError, OverflowError):
        raise ApiError(422, "excerpt", "cannot read excerpt settings or paths") from None
