"""Citation locations, the marker grammar and protected Markdown spans."""
from __future__ import annotations

import re
from pathlib import Path

from pdfmd_base import core
from .record import RecordError

MARKER = re.compile(r"(.+)[:#]([0-9]+)\Z")
CITATION = re.compile(r"(?<![\w@\\])@(?:\{([^}\n]+)\}|([-\w](?:[\w:.#$%&+?<>~/-]*\w)?))")
REFERENCE_PREFIXES = ("fig", "tbl", "eq", "sec", "lst")


def prefix_setting(document, metadata):
    for _, options in core.option_sources(document, metadata):
        if "excerpt-prefix" in options:
            value = options["excerpt-prefix"]
            break
    else:
        return "x"
    if type(value) is int:
        value = str(value)
    if (not isinstance(value, str) or not value or value in REFERENCE_PREFIXES
            or not all(char.isalpha() or char.isdecimal() or char in "-_" for char in value)):
        raise RecordError("excerpt-prefix must be one word of letters, digits, - or _, without a cross-reference prefix")
    return value


def marker(key, prefix="x"):
    if ":" in key and key.split(":", 1)[0] in REFERENCE_PREFIXES:
        return None
    found = MARKER.fullmatch(key)
    if found:
        head, ident = found.groups()
        try:
            return int(ident), None if head == prefix else head
        except ValueError:
            return None
    return None


def canonical(ident, key, prefix):
    return f"@{key}#{ident}" if key is not None else f"@{prefix}:{ident}"


def citation_mask(text, document, metadata, include_metadata=False):
    """Blank protected text without changing offsets or line numbers."""
    from pdfmd_check.lint import Analysis, Source, blank_matches, blank, mask_code
    analysis = Analysis(Source(document.name, document, text))
    scanned = analysis.cited
    if include_metadata and analysis.front_end:
        front = text[:analysis.front_end]
        # Indented YAML block scalars are content, so mask just their inline code and comments.
        scanned = mask_code(re.sub(r"(?m)^[ \t]+", lambda match: "!" * len(match[0]), front))[0] + scanned[analysis.front_end:]
    for raw in re.finditer(r"(?is)<(pre|script|style|code)\b[^>]*>.*?</\1>", text):
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
    return scanned


def locations(place, record_path, bibliography, data=None):
    from .resolution import Resolution, project
    records = project(data) if data is not None else None
    warnings = set()
    place = Path(place)
    root = place if place.is_dir() else place.parent
    project = record_path.parent.parent if record_path.parent.name in ("metadata", ".pdfmd") else record_path.parent
    if project == root or project in root.parents:
        root = project
    documents = sorted(root.rglob("*"))
    result = []
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
        prefix = prefix_setting(document, metadata)
        text = path.read_text(encoding="utf-8")
        scanned = citation_mask(text, document, metadata, include_metadata=True)
        from .discovery import bibliography as document_bibliography
        real_keys = {**bibliography, **document_bibliography(document, metadata)}
        state = Resolution(prefix, records, set(real_keys), [], (), messages=warnings)
        for found in CITATION.finditer(scanned):
            key = found[1] or found[2]
            parsed = marker(key, prefix)
            if key in real_keys:
                state.resolve(key, diagnostics=True)
            elif parsed is not None and (records is None or state.resolve(key) is not None):
                ident, named = parsed
                result.append({"id": ident, "key": named, "file": core.display_path(path),
                               "line": text.count("\n", 0, found.start()) + 1, "marker": canonical(ident, named, prefix)})
    return result
