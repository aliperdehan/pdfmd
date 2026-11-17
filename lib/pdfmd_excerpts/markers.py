"""Read-only citation locations. The marker grammar lives here (D81 / Q74).

P1c will supply resolution and detach. No build imports this scanner in P1b.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from pdfmd_base import core

# Change the separators/prefix here if a future decision supersedes D81.
SHORT = re.compile(r"x[:#]([0-9]+)\Z")
LONG = re.compile(r"(.+)#([0-9]+)\Z")
REFERENCE_PREFIXES = ("fig", "tbl", "eq", "sec", "lst")


def marker(key):
    if ":" in key and key.split(":", 1)[0] in REFERENCE_PREFIXES:
        return None
    short = SHORT.fullmatch(key)
    if short:
        return int(short[1]), None
    long = LONG.fullmatch(key)
    return (int(long[2]), long[1]) if long else None


def locations(place, record_path, bibliography):
    from pdfmd_check.lint import Analysis, Source, CITE_RE, blank_matches, blank
    place = Path(place)
    root = place if place.is_dir() else place.parent
    project = record_path.parent.parent if record_path.parent.name in ("metadata", ".pdfmd") else record_path.parent
    if project == root or project in root.parents:
        root = project
    documents = sorted(root.rglob("*"))
    result = []
    collisions = set()
    for path in documents:
        if (path.suffix.lower() not in (".md", ".markdown", ".qmd") or not path.is_file()
                or any(part.startswith(".") for part in path.relative_to(root).parts)):
            continue
        # A nearer/explicit different record file makes this a different id namespace.
        from .discovery import context, discover
        document, metadata = context(path)
        try:
            if discover(document, metadata).resolve() != record_path.resolve():
                continue
        except ValueError:
            continue
        text = path.read_text(encoding="utf-8")
        analysis = Analysis(Source(path.name, path, text))
        # Raw HTML bodies and TeX math are text, as are Pandoc raw blocks (masked as fences).
        scanned = analysis.cited
        for raw in re.finditer(r"(?s)<(pre|script|style)\b[^>]*>.*?</\1>", text):
            scanned = scanned[:raw.start()] + blank(scanned[raw.start():raw.end()]) + scanned[raw.end():]
        scanned = blank_matches(re.compile(r"(?s)\\\[.*?\\\]|\\\(.*?\\\)"), scanned)
        scanned = blank_matches(re.compile(r"(?s)\\begin\{([^}]+)\}.*?\\end\{\1\}"), scanned)
        if "%%" in text:
            preset = core.FLAVOUR_PRESETS.get(core.flavour_of(document, metadata))
            if preset and preset.comments:
                from pdfmd_obsidian.comments import _pairs
                for start, end, closed in _pairs(text, core.unclosed_comment_mode(document, metadata))[0]:
                    stop = end + 2 if closed else end
                    scanned = scanned[:start] + blank(scanned[start:stop]) + scanned[stop:]
        from .discovery import bibliography as document_bibliography
        real_keys = {**bibliography, **document_bibliography(document, metadata)}
        for found in CITE_RE.finditer(scanned):
            key = found[1] or found[2]
            parsed = marker(key)
            if parsed is not None and key in real_keys and key not in collisions:
                collisions.add(key)
                print(f"WARN  the bibliography has a key '{key}': it is used as a source, not as excerpt {parsed[0]}", file=sys.stderr)
            elif parsed is not None and key not in real_keys:
                ident, named = parsed
                result.append({"id": ident, "key": named, "file": core.display_path(path), "line": analysis.line(found.start())})
    return result
