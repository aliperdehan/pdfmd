"""Pinned copies installed on request, separate from the rolling CSL URL cache."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pdfmd_base import core


def directory(kind: str, source: str) -> Path:
    root = core.cache_root() / "csl" if kind == "csl" else core.config_root() / "templates"
    return root / "installed" / hashlib.sha256(source.encode("utf-8")).hexdigest()


def pinned_style(kind: str, source: str) -> Path | None:
    folder = directory(kind, source)
    try:
        record = json.loads((folder / "asset.json").read_text(encoding="utf-8"))
        filename = record["file"]
        digest = record["sha256"]
        if not isinstance(filename, str) or Path(filename).name != filename or filename in ("", ".", ".."):
            return None
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            return None
        path = folder / digest / filename
        if path.is_file():
            return path
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def save_style(kind: str, source: str, filename: str, upstream: str, revision: str, licence: str, data: bytes) -> Path:
    folder = directory(kind, source)
    digest = hashlib.sha256(data).hexdigest()
    path = folder / digest / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    core.atomic_write_bytes(path, data)
    record = {"file": filename, "source": upstream, "revision": revision, "licence": licence, "sha256": digest}
    core.atomic_write_text(folder / "asset.json", json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return path
