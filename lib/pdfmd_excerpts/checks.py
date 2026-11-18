"""Check excerpt marker locations and prose without invoking Pandoc or quoting private fields."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
import re
import unicodedata

from pdfmd_base import core
from pdfmd_check.lint import Analysis, Findings, Problem, Source

from .detach import brackets, page_list
from .discovery import discover
from .markers import CITATION, citation_mask, marker, prefix_setting, project_documents
from .record import RecordError, read
from .resolution import bibliography_keys, enabled, might_cite, terms


QUOTE_MIN = 3
OVERLAP_MIN = 6
WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
QUOTE = re.compile(r'(?<!\\)"([^"\n]+(?:\n[^"\n]+)*)"|“([^”]+)”')
QUOTE_EDITS = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…|\[[^\]]*\]")
DASHES = "‐‑‒–—―−"
PUNCTUATION = str.maketrans({**dict.fromkeys(DASHES, "-"), "‘": "'", "’": "'", "“": '"', "”": '"'})
PAGE = r"(?:[^\W\d_]*[0-9]+|[ivxlcdm]+)\b"
PAGE_RANGE = PAGE + r"(?:\s*[-" + DASHES + r"]+\s*" + PAGE + r")?"
TYPED_PAGES = re.compile(PAGE_RANGE + r"(?:\s*[,;]\s*" + PAGE_RANGE + r")*", re.I)
BLOCK_BREAK = re.compile(r"(?m)^[ \t]*(?:$|[#>|]|(?:[-+*]|[0-9]+[.)])(?=\s)|\[\^[^\]]+\]:)")


class ExcerptFindings(Findings):
    def __init__(self):
        super().__init__()
        self.affected = set()

    def add(self, analysis, line, code, message, *, severity=None, subjects=()):
        before = len(self.problems)
        super().add(analysis, line, code, message, severity=severity)
        if len(self.problems) > before and self.problems[-1].severity != "note":
            self.affected.update(subjects)


def threshold(document, metadata, name, default, minimum):
    value = core.first_pdfmd_option(document, metadata, name)
    if value is None:
        return default
    if not re.fullmatch(r"[0-9]+", str(value).strip()) or int(value) < minimum:
        raise RecordError(f"{name} must be a whole number of at least {minimum}")
    return int(value)


def normalised(text):
    text = unicodedata.normalize("NFKC", text).casefold().translate(PUNCTUATION)
    text = re.sub(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=\w)", "", text)
    text = re.sub(r"-+", "-", text)
    return "".join(text.replace("\u00ad", "").split())


def quote_chunks(text):
    # Insertions are removed. Ellipses, including bracketed ones, allow a gap.
    edited = QUOTE_EDITS.sub(lambda hit: "\0" if hit[0].strip("[] \t\n") in ("...", "…") else "", text)
    return [part for bit in edited.split("\0") if (part := normalised(bit))]


def contains_chunks(text, chunks):
    offset = 0
    for chunk in chunks:
        start = text.find(chunk, offset)
        if start < 0:
            return False
        offset = start + len(chunk)
    return bool(chunks)


def typed_locator(suffix, locators):
    suffix = suffix.replace("\u00a0", " ").lstrip(", \t\n")
    lower = suffix.casefold()
    for term in sorted(locators, key=len, reverse=True):
        if lower == term.casefold() or lower.startswith(term.casefold() + " "):
            return suffix, suffix[len(term):].strip()
    if re.match(r"[0-9]", suffix):
        return suffix, suffix
    return None


def locator_differs(record, suffix, locators):
    typed = typed_locator(suffix, locators)
    if typed is None:
        return False
    whole, rest = typed
    if record.get("locator"):
        return normalised(whole.split(",", 1)[0]) != normalised(record["locator"])
    got = TYPED_PAGES.match(rest)
    if record.get("page") is not None and got is not None:
        page = record["page"]
        return normalised(page_list([got[0]]) or got[0]) != normalised(page_list([page]) or page)
    return bool(record.get("page") or whole)


def citation_spans(scanned):
    """Yield the citation hit, whole cluster offsets, suffix and narrative mode."""
    hits = list(CITATION.finditer(scanned))
    starts = [hit.start() for hit in hits]
    pairs = brackets(scanned)
    groups = {}
    for opening, (closing, separators) in sorted(pairs.items(), key=lambda item: item[1][0] - item[0]):
        if scanned[opening - 1:opening] == "^" or scanned[opening + 1:opening + 2] == "^":
            continue
        previous = bisect_left(starts, opening) - 1
        if previous >= 0 and re.fullmatch(r"[ \t\n]+", scanned[hits[previous].end():opening]):
            continue
        pieces = []
        for start, end in zip([opening, *separators], [*separators, closing]):
            candidates = hits[bisect_right(starts, start):bisect_left(starts, end)]
            if len(candidates) != 1:
                break
            pieces.append((candidates[0], end))
        else:
            for hit, end in pieces:
                groups.setdefault(hit.start(), (opening, closing + 1, scanned[hit.end():end], False))
    for hit in hits:
        group = groups.get(hit.start())
        if group is None:
            start, end = hit.span()
            suppressed = scanned[start - 1:start] == "-"
            following = re.match(r"[ \t\n]*\[", scanned[end:])
            suffix = ""
            if following:
                opening = end + following.end() - 1
                pair = pairs.get(opening)
                if pair and bisect_right(starts, opening) == bisect_left(starts, pair[0]):
                    suffix, end = scanned[opening + 1:pair[0]], pair[0] + 1
            group = start - suppressed, end, suffix, not suppressed
        yield hit, *group


def longest_overlap(text, source, minimum):
    words = list(WORD.finditer(text))
    longest = minimum - 1
    offset = 0
    for first, word in enumerate(words):
        for last in range(first + longest, len(words)):
            if normalised(text[word.start():words[last].end()]) not in source:
                break
            longest = last - first + 1
            offset = word.start()
    return (longest, offset) if longest >= minimum else (0, 0)


def prose_checks(scanned, starts, blocks, by_key, quote_min, overlap_min, analysis, findings):
    for block, uses in blocks.items():
        first, last = starts[block - 1:block + 1]
        cited = {record["id"]: record for _, _, _, record in uses if record and record["kind"] != "remark"}
        if not cited:
            continue
        passage = lambda record: normalised(" ".join(part.get("text", "") for part in record.get("parts", [])))
        excerpts = {ident: passage(record) for ident, record in cited.items()}
        alternate = {item["id"]: passage(item) for _, _, key, _ in uses for item in by_key.get(key, [])
                     if item["id"] not in cited}
        body = list(scanned[first:last])
        for start, end, _, _ in uses:
            body[start - first:min(end, last) - first] = " " * (min(end, last) - start)
        body = "".join(body)
        quotes = list(QUOTE.finditer(body))
        for hit in quotes:
            words = hit[1] or hit[2]
            if len(WORD.findall(QUOTE_EDITS.sub(" ", words))) < quote_min:
                continue
            chunks = quote_chunks(words)
            if any(contains_chunks(text, chunks) for text in excerpts.values()):
                continue
            line = analysis.line(first + hit.start())
            other = next((ident for ident, text in sorted(alternate.items()) if contains_chunks(text, chunks)), None)
            if other is not None:
                findings.add(analysis, line, "excerpt-quote", f"quotation matches uncited excerpt {other}", severity="note")
            else:
                ocr = any(part.get("text-from") == "ocr" for record in cited.values() for part in record.get("parts", []))
                findings.add(analysis, line, "excerpt-quote", "quotation is absent from the cited excerpts",
                             severity="note" if ocr else None, subjects=cited)
        if overlap_min:
            bounds = [0, *(offset for hit in quotes for offset in hit.span()), len(body)]
            segments = list(zip(bounds[::2], bounds[1::2]))
            for ident, passage_text in excerpts.items():
                matches = ((count, start + offset) for start, end in segments
                           for count, offset in [longest_overlap(body[start:end], passage_text, overlap_min)])
                count, at = max(matches, key=lambda match: match[0], default=(0, 0))
                if count:
                    findings.add(analysis, analysis.line(first + at), "excerpt-overlap",
                                 f"{count} words as in excerpt {ident}, without quotation marks", subjects=(ident,))


def marker_checks(path, source, document, metadata, prefix, keys, data, *, metadata_only=False):
    analysis = Analysis(source)
    scanned = citation_mask(source.text, path, metadata, include_metadata=True, metadata_only=metadata_only)
    findings = ExcerptFindings()
    used = set()
    by_id = {record["id"]: record for record in data["excerpts"]}
    by_key = defaultdict(list)
    for record in by_id.values():
        if record.get("key"):
            by_key[record["key"]].append(record)
    blocks = defaultdict(list)
    starts = sorted(set([analysis.front_end, len(scanned), *(match.start() for match in BLOCK_BREAK.finditer(scanned)
                                                             if match.start() >= analysis.front_end)]))
    _, locators = terms(document, metadata)
    for hit, start, end, suffix, narrative in citation_spans(scanned):
        key, record = hit[1] or hit[2], None
        parsed = marker(key, prefix)
        if parsed and key not in keys:
            ident, named = parsed
            record = by_id.get(ident)
            line = analysis.line(hit.start())
            if record is None:
                findings.add(analysis, line, "excerpt-unknown", f"excerpt {ident} is not in excerpts.json")
                continue
            if named is not None and record.get("key") != named:
                owner = record.get("key") or "a remark without a source"
                findings.add(analysis, line, "excerpt-key-mismatch", f"excerpt {ident} belongs to {owner}", subjects=(ident,))
                continue
            used.add(ident)
            if record["kind"] == "remark":
                if narrative:
                    findings.add(analysis, line, "excerpt-remark-narrative", f"excerpt {ident} is a narrative remark marker",
                                 subjects=(ident,))
            else:
                key = record["key"]
                if key not in keys:
                    findings.add(analysis, line, "excerpt-bib", f"excerpt {ident}: @{key} is not in the bibliography",
                                 subjects=(ident,))
                if locator_differs(record, suffix, locators):
                    findings.add(analysis, line, "excerpt-locator-differs", f"typed locator differs from excerpt {ident}",
                                 subjects=(ident,))
        if not metadata_only and start >= analysis.front_end:
            blocks[bisect_right(starts, start)].append((start, end, key, record))
    if blocks and used:
        quote_min = threshold(document, metadata, "excerpt-quote-min-words", QUOTE_MIN, 1)
        overlap_min = threshold(document, metadata, "excerpt-overlap-words", OVERLAP_MIN, 0)
        prose_checks(scanned, starts, blocks, by_key, quote_min, overlap_min, analysis, findings)
    return findings.problems, used, findings.affected


def lint_excerpts(files, document, metadata, arguments, no_auto, named_reader):
    """Give --check its own diagnostics and suppress duplicate generic citation diagnostics."""
    if not files or not enabled(document, metadata, no_auto, named_reader):
        return [], None
    sources = [(path, source, False) for path, source in files] + metadata_sources(metadata)
    sources = [item for item in sources if might_cite(item[1].text)]
    if not sources:
        return [], None
    prefix = prefix_setting(document, metadata)
    keys = bibliography_keys([path for path, _ in files], metadata, arguments, no_auto)
    active = lambda key: key not in keys and marker(key, prefix) is not None
    if not any(active(hit[1] or hit[2]) for path, source, is_metadata in sources for hit in
               CITATION.finditer(citation_mask(source.text, path, metadata, include_metadata=True, metadata_only=is_metadata))):
        return [], None
    skip = lambda key: None if active(key) else key
    try:
        path = discover(document, metadata)
        data = read(path)
    except RecordError as error:
        if str(error) == "excerpts are off in this context":
            return [], None
        return [file_problem(document, str(error))], skip
    except OSError:
        return [file_problem(document, "cannot read the record file")], skip
    problems = []
    for path, source, is_metadata in sources:
        problems.extend(marker_checks(path, source, document, metadata, prefix, keys, data, metadata_only=is_metadata)[0])
    return problems, skip


def metadata_sources(metadata, show=None):
    show = show or core.display_path
    return [(path, Source(show(path), path.parent, core.read_text_best_effort(path)), True) for path in metadata]


def file_problem(path, message):
    return Problem(core.display_path(path), 0, "excerpt-file", "excerpts.json: " + message)


def project_checks(place, path, data, *, guard=None, show=None):
    from .anchors import pdf_problems

    show = show or core.display_path
    problems, affected = pdf_problems(data, path, show=show)
    used = set()
    for document, metadata in project_documents(place, path, guard=guard):
        no_auto = core.effective_no_auto(document, None)
        if not enabled(document, metadata, no_auto):
            continue
        own = Source(show(document), document.parent, document.read_text(encoding="utf-8-sig"))
        sources = [item for item in [(document, own, False), *metadata_sources(metadata, show)] if might_cite(item[1].text)]
        if not sources:
            continue
        keys = bibliography_keys([document], metadata, (), no_auto, guard=guard)
        prefix = prefix_setting(document, metadata)
        for item, source, is_metadata in sources:
            found, ids, subject = marker_checks(item, source, document, metadata, prefix, keys, data, metadata_only=is_metadata)
            problems.extend(found)
            used.update(ids)
            affected.update(subject)
    for record in data["excerpts"]:
        if record["id"] not in used:
            problems.append(Problem(show(path), 0, "excerpt-unused", f"excerpt {record['id']} is unused"))
    return list(dict.fromkeys(problems)), used, affected
