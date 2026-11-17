"""Local source identity and matching proposals. No network and no PDF writes."""
from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import os
from pathlib import Path
import re

from .pages import reader, labels
from .record import RecordError, page_map


def identity(path, base, pages=None):
    content = path.read_bytes()
    if not content.startswith(b"%PDF-"):
        raise RecordError("source is not a PDF")
    result = {"file": Path(os.path.relpath(path, base)).as_posix(), "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
    if pages is not None:
        page_map(pages)
        if pages == "labels":
            labels(path)
        result["pages"] = pages
    return result


def states(data, base):
    def state(item):
        if not item.get("file"):
            return "missing"
        path = (base / Path(item["file"]).expanduser()).resolve()
        if not path.is_file():
            return "missing"
        if "sha256" not in item or "size" not in item:
            return "unknown"
        content = path.read_bytes()
        return "ok" if len(content) == item["size"] and hashlib.sha256(content).hexdigest() == item["sha256"] else "changed"
    result = []
    for key, item in sorted(data["sources"].items()):
        result.append({"key": key, **item, "state": state(item)})
        result[-1]["more"] = {name: {**extra, "state": state(extra)} for name, extra in sorted(item.get("more", {}).items())}
    return result


def field(entry, name):
    if "text" not in entry:  # CSL-JSON or YAML
        return str(entry.get(name, entry.get(name.upper(), "")))
    text = entry["text"]
    found = re.search(r"\b" + re.escape(name) + r"\s*=\s*", text, re.I)
    if found is None:
        return ""
    start = found.end()
    if text[start:start + 1] == "{":
        from pdfmd_cite import bib_entry_end
        end = bib_entry_end(text, start)
        return text[start + 1:end - 1] if end else ""
    if text[start:start + 1] == '"':
        found = re.match(r'"((?:\\.|[^"\\])*)"', text[start:])
        return found[1] if found else ""
    return text[start:].split(",", 1)[0].strip()


def normal(text):
    return re.sub(r"[^\w]", "", text.casefold())


def proposed_map(entry, count):
    value = field(entry, "pages") or field(entry, "page")
    found = re.fullmatch(r"\s*([0-9]+)\s*[-–—]+\s*([0-9]+)\s*", value)
    if found:
        start, end = map(int, found.groups())
        length = end - start + 1
        if length > 0 and count in (length, length + 1):
            return [[count - length + 1, str(start)]]
    return None


def match(entries, directory, base):
    """Rank evidence without a hidden similarity threshold. Fuzzy results are proposals only.

    Conflicting candidates and filename likeness require a human choice via sources add;
    --apply uses only a unique match by file, DOI, title or exact filename.
    """
    paths = sorted(path.resolve() for path in directory.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")
    evidence = {}
    for path in paths:
        pdf = reader(path)
        try:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception:
            raise RecordError("cannot read source PDF text") from None
        evidence[path] = (text, len(pdf.pages))
    proposals = []
    for key, (entry, origin) in sorted(entries.items()):
        named = Path(field(entry, "file")).expanduser()
        doi, title = field(entry, "doi"), field(entry, "title")
        ranked = []
        for path, (text, count) in evidence.items():
            reason = ("file" if str(named) != "." and (origin / named).resolve() == path else
                      "doi" if doi and doi.casefold().removeprefix("https://doi.org/") in text.casefold() else
                      "title" if title and normal(title) in normal(text) else
                      "name" if normal(path.stem) == normal(key) else "likeness")
            rank = (5 - ("file", "doi", "title", "name", "likeness").index(reason),
                    SequenceMatcher(None, normal(key), normal(path.stem)).ratio() if reason == "likeness" else 1)
            ranked.append((rank, path, reason, count))
        ranked.sort(key=lambda item: (item[0], str(item[1])), reverse=True)
        if not ranked:
            proposals.append({"key": key, "candidates": [], "apply": False})
            continue
        best = [item for item in ranked if item[0] == ranked[0][0]]
        candidates = []
        for _, path, reason, count in best:
            candidate = {"file": Path(os.path.relpath(path, base)).as_posix(), "reason": reason}
            mapping = proposed_map(entry, count)
            if mapping is not None:
                candidate["pages"] = mapping
            candidates.append(candidate)
        proposals.append({"key": key, "candidates": candidates, "apply": len(best) == 1 and best[0][2] != "likeness"})
    return proposals
