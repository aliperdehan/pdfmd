"""Citation locations, the marker grammar and protected Markdown spans."""
from __future__ import annotations

import re
from pathlib import Path

from pdfmd_base import core
from .record import RecordError

MARKER = re.compile(r"(.+)[:#]([0-9]+)\Z")
CITATION = re.compile(r"(?<![\w@\\])@(?:\{([^}\n]+)\}|([-\w](?:[\w:.#$%&+?<>~/-]*\w)?))")
REFERENCE_PREFIXES = ("fig", "tbl", "eq", "sec", "lst")
NON_CITATION_METADATA = frozenset({"references", "references+", "pdfmd-options", "bibliography", "bibliography+", "csl"})


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


def citation_mask(text, document, metadata, include_metadata=False, *, metadata_only=False, prose=False):
    """Blank protected text without changing offsets or line numbers."""
    from pdfmd_check.lint import Analysis, Source, blank_matches, blank, mask_code
    analysis = Analysis(Source(document.name, document, text))
    scanned = analysis.plain if prose else analysis.cited
    front_end = len(text) if metadata_only else analysis.front_end if include_metadata else 0
    if front_end:
        front = text[:front_end]
        # Indented YAML block scalars are content, so mask just their inline code and comments.
        front = mask_code(re.sub(r"(?m)^[ \t]+", lambda match: "!" * len(match[0]), front))[0]
        if metadata_only and core.yaml is not None:
            try:
                node = core.yaml.compose(text)
            except core.yaml.YAMLError:
                node = None
            if isinstance(node, core.yaml.MappingNode):
                for key, value in node.value:
                    if isinstance(key, core.yaml.ScalarNode) and key.value in NON_CITATION_METADATA:
                        start, end = key.start_mark.index, value.end_mark.index
                        if start < end:  # a YAML alias can point back to an earlier key
                            front = front[:start] + blank(front[start:end]) + front[end:]
        scanned = front + scanned[front_end:]
    for raw in re.finditer(r"(?is)<(pre|script|style|code)\b[^>]*>.*?</\1>", text):
        scanned = scanned[:raw.start()] + blank(scanned[raw.start():raw.end()]) + scanned[raw.end():]
    scanned = blank_matches(re.compile(r"(?s)\\\[.*?\\\]|\\\(.*?\\\)"), scanned)
    scanned = blank_matches(re.compile(r"(?s)\\begin\{([^}]+)\}.*?\\end\{\1\}"), scanned)
    if "%%" in text:
        preset = core.effective_preset(document, metadata)
        if preset and preset.comments:
            from pdfmd_obsidian.comments import _pairs
            for start, end, closed in _pairs(text, core.unclosed_comment_mode(document, metadata))[0]:
                stop = end + 2 if closed else end
                scanned = scanned[:start] + blank(scanned[start:stop]) + scanned[stop:]
    return scanned


def project_root(place, record_path):
    place = Path(place).expanduser().resolve()
    root = place if place.is_dir() else place.parent
    project = record_path.parent.parent if record_path.parent.name in ("metadata", ".pdfmd") else record_path.parent
    return project if project == root or project in root.parents else root


def project_contexts(place, record_path, *, guard=None):
    from .discovery import context, discover

    root = project_root(place, record_path)
    for path in sorted(root.rglob("*")):
        if (path.suffix.lower() not in (".md", ".markdown", ".qmd") or not path.is_file()
                or any(part.startswith(".") for part in path.relative_to(root).parts)):
            continue
        # A nearer/explicit different record file makes this a different id namespace.
        document, metadata = context(path, guard=guard)
        try:
            namespace = discover(document, metadata).resolve()
        except ValueError:
            namespace = None
        yield document, metadata, namespace


def project_documents(place, record_path, *, guard=None):
    namespace = record_path.resolve()
    return ((document, metadata) for document, metadata, found in project_contexts(place, record_path, guard=guard)
            if found == namespace)


def locations(place, record_path, bibliography, data=None, *, guard=None, show=None):
    from .resolution import Resolution, project
    show = show or core.display_path
    records = project(data) if data is not None else None
    warnings = set()
    result = []
    for document, metadata in project_documents(place, record_path, guard=guard):
        prefix = prefix_setting(document, metadata)
        text = document.read_text(encoding="utf-8")
        scanned = citation_mask(text, document, metadata, include_metadata=True)
        from .discovery import bibliography as document_bibliography
        real_keys = {**bibliography, **document_bibliography(document, metadata, guard=guard)}
        state = Resolution(prefix, records, set(real_keys), [], (), messages=warnings)
        for found in CITATION.finditer(scanned):
            key = found[1] or found[2]
            parsed = marker(key, prefix)
            if key in real_keys:
                state.resolve(key, diagnostics=True)
            elif parsed is not None and (records is None or state.resolve(key) is not None):
                ident, named = parsed
                result.append({"id": ident, "key": named, "file": show(document),
                               "line": text.count("\n", 0, found.start()) + 1, "marker": canonical(ident, named, prefix)})
    return result
