"""The build's view of an excerpt record. No source PDF or private field crosses this boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import sys

from pdfmd_base import core

from .discovery import discover
from .markers import CITATION, canonical, marker, prefix_setting
from .record import RecordError, read

# CSL's English locator labels, including common short forms.
CSL_TERMS = (
    "act", "appendix", "article", "book", "canon", "chapter", "ch.", "column", "col.",
    "elocation", "equation", "eq.", "figure", "fig.", "folio", "fol.", "issue", "no.",
    "line", "l.", "ll.", "note", "opus", "op.", "page", "p.", "pp.", "paragraph", "para.",
    "§", "part", "pt.", "rule", "scene", "section", "sec.", "sub verbo", "s.v.",
    "supplement", "suppl.", "timestamp", "title", "verse", "v.", "vv.",
    "volume", "vol.",
)


def might_cite(text):
    return "@" in text and re.search(r"[:#][0-9]", text) is not None


def warn(message):
    print("WARN  " + message, file=sys.stderr)


def terms(document, metadata):
    value = core.first_pdfmd_option(document, metadata, "excerpt-page-terms")
    page = ["p.", "pp."] if value is None else term_list(value)
    if len(page) != 2:
        raise SystemExit("excerpt-page-terms must give a singular and plural term, such as [p., pp.]")
    other = core.first_pdfmd_option(document, metadata, "pagecite-terms")
    return page, tuple(set(CSL_TERMS).union(page, term_list(other) if other is not None else ()))


def term_list(value):
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return []
    return [item.strip() for item in value]


def enabled(document, metadata, no_auto, named_reader=None):
    _, reader = core.deferred("pdfmd_flavours.markup", "flavour_setting")(document, metadata)
    return (not named_reader and not reader and not core.auto_disabled(no_auto, "excerpts")
            and "excerpts" in core.markup_kinds(document, metadata))


def bibliography_keys(sources, metadata, arguments, no_auto, extra_layers=(), include_candidates=True):
    from pdfmd_bibliography.discovery import candidates
    from pdfmd_bibliography.sources import layers, locate, read_entries, resource_folders, values

    keys, files = set(), set()
    folders = resource_folders(sources, metadata)
    for _, mapping in [*layers(sources, metadata, arguments), *extra_layers]:
        for name in ("references", "references+"):
            keys.update(str(item["id"]) for item in values(mapping.get(name)) if isinstance(item, dict) and "id" in item)
        for name in ("bibliography", "bibliography+"):
            files.update(locate(value, folders) for value in values(mapping.get(name)) if isinstance(value, str))
    if include_candidates and not core.discovery_disabled(no_auto, "bib"):
        files.update(candidates(sources, metadata))
    for path in files:
        parsed = read_entries(path)
        if parsed:
            keys.update(key for key, _ in parsed[0])
    return keys


@dataclass
class Resolution:
    prefix: str
    records: dict | None
    bibliography: set[str]
    page_terms: list[str]
    locator_terms: tuple[str, ...]
    missing: str | None = None
    missing_count: int = 0
    messages: set[str] = field(default_factory=set)
    arguments: tuple[str, ...] = ()
    no_auto: list[str] | None = None

    def message(self, message):
        if message not in self.messages:
            self.messages.add(message)
            warn(message)

    def finish(self):
        if self.missing_count:
            count = self.missing_count
            self.message(f"{count} excerpt marker{'s' if count != 1 else ''} but no excerpts.json (looked in {self.missing})")
            self.missing_count = 0

    def resolve(self, key, *, diagnostics=False, narrative=False):
        """Return the projected record for a marker, or None for an unchanged citation."""
        parsed = marker(key, self.prefix)
        if parsed is None:
            return None
        ident, named = parsed
        record = self.records.get(str(ident)) if self.records is not None else None
        matches = record is not None and (named is None or named == record.get("key"))
        if key in self.bibliography:
            if matches and diagnostics:
                alternatives = [canonical(ident, named, self.prefix)]
                if record.get("key"):
                    alternatives += [canonical(ident, record["key"], self.prefix)]
                alternatives += [canonical(ident, None, self.prefix)]
                suggestion = next((form for form in alternatives if form[1:] not in self.bibliography), alternatives[0])
                source = f" of {named}" if named else ""
                self.message(f"the bibliography has a key '{key}': it is used as a source, "
                             f"not as excerpt {ident}{source} (write {suggestion} for the excerpt)")
            return None
        if self.records is None:
            if diagnostics and self.missing is not None:
                self.missing_count += 1
            return None
        if not matches:
            if diagnostics:
                if record is None:
                    self.message(f"excerpt {ident} is not in excerpts.json")
                else:
                    self.message(f"@{key}: excerpt {ident} belongs to {record.get('key') or 'a remark without a source'}")
            return None
        if diagnostics:
            if record["remark"] and narrative:
                self.message(f"excerpt {ident}: removed a narrative remark marker")
            if not record["remark"] and record["key"] not in self.bibliography:
                self.message(f"excerpt {ident}: its key {record['key']} is not in the bibliography")
        return record

    def key(self, key):
        record = self.resolve(key)
        return (None if record["remark"] else record["key"]) if record is not None else key


def project(data):
    return {str(item["id"]): {"key": item.get("key", ""), "page": item.get("page", ""),
                              "locator": item.get("locator", ""), "remark": item["kind"] == "remark"}
            for item in data["excerpts"]}


def prepare(sources, metadata, arguments=(), no_auto=None, *, diagnostics=False, text=None, named_reader=None,
            data=None, extra_layers=()):
    """Read only when the source or its metadata can use an excerpt."""
    document = sources[0]
    metadata = list(metadata)
    texts = ([text] if text is not None else [core.read_text_best_effort(file) for file in sources])
    texts.extend(core.read_text_best_effort(file) for file in metadata)
    texts.extend(arguments)
    options = core.option_sources(document, metadata)
    if not (any(might_cite(value) for value in texts) or any("excerpt-prefix" in layer for _, layer in options)):
        return None
    try:
        prefix = prefix_setting(document, metadata)
    except RecordError as error:
        raise SystemExit(str(error)) from None
    if not enabled(document, metadata, no_auto, named_reader):
        return None
    try:
        path = discover(document, metadata, diagnostics and core.VERBOSE_OUTPUT)
    except RecordError as error:
        if diagnostics and str(error) != "excerpts are off in this context":
            warn(f"excerpts.json: {error}")
        return None
    # Avoid reading the record or bibliography for ordinary citations.
    if not any(marker(match[1] or match[2], prefix) for value in texts for match in CITATION.finditer(value)):
        return None
    found, missing = None, None
    if data is not None:
        found = project(data)
    else:
        try:
            found = project(read(path))
        except FileNotFoundError:
            missing = core.display_path(path)
        except (OSError, RecordError) as error:
            if diagnostics:
                reason = str(error) if isinstance(error, RecordError) else "cannot read the record file"
                warn("excerpts.json: " + reason)
            return None
    page, locators = terms(document, metadata) if found is not None else ([], ())
    keys = bibliography_keys(sources, metadata, arguments, no_auto, extra_layers)
    return Resolution(prefix, found, keys, page, tuple(sorted(locators)), missing,
                      arguments=tuple(arguments), no_auto=no_auto)


def candidate_keys(sources, metadata, keys, known, no_auto, layers):
    """Resolve the keys before deciding which local bibliography files supply them."""
    state = prepare(sources, metadata, no_auto=no_auto, extra_layers=layers)
    if state is None or state.records is None:
        return keys
    return {resolved for key in keys if (resolved := state.key(key)) is not None} | (keys & known)


def citation_use(sources, metadata, arguments=(), no_auto=None, named_reader=None):
    """None leaves detection to the existing reader. A resolved remark is not a citation."""
    state = prepare(sources, metadata, arguments, no_auto, named_reader=named_reader)
    if state is None or state.records is None:
        return None
    from .markers import citation_mask
    for file in sources:
        text = core.read_text_best_effort(file)
        if core.fullcite_old_spelling(file):
            return True
        if any(state.key(found[1] or found[2]) is not None
               for found in CITATION.finditer(citation_mask(text, file, metadata, include_metadata=True))):
            return True
    return any(state.key(found[1] or found[2]) is not None for file in metadata
               for found in CITATION.finditer(core.read_text_best_effort(file)))


def protect_hyphen_prefix(text, document, metadata, no_auto, named_reader=None):
    """A bare key beginning with a hyphen needs braces to reach Pandoc's Cite AST."""
    if "@-" not in text:
        return text
    state = prepare([document], metadata, no_auto=no_auto, text=text, named_reader=named_reader)
    if not state or state.records is None or not state.prefix.startswith("-"):
        return text
    from .markers import citation_mask

    scanned = citation_mask(text, document, metadata, include_metadata=True)
    offsets = [found.span() for found in CITATION.finditer(scanned)
               if found[2] and found[2].startswith("-") and marker(found[2], state.prefix)
               and marker(found[2], state.prefix)[1] is None]
    for start, end in reversed(offsets):
        text = text[:start + 1] + "{" + text[start + 1:end] + "}" + text[end:]
    return text
