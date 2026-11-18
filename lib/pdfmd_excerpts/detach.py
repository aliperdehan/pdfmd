"""Rewrite excerpt citations in Markdown that leaves the project, and for the native tier."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path
import re

from pdfmd_base import core

from .markers import CITATION, REFERENCE_PREFIXES, citation_mask, marker
from .pagecite import excerpt_repeat
from .pages import roman, roman_number
from .resolution import prepare
from .record import RecordError, read


def citation_name(key):
    return "@" + (key if re.fullmatch(r"[\w](?:[\w:.#$%&+?<>~/-]*\w)?", key) else "{" + key + "}")


def numbered_page(label):
    digits = re.fullmatch(r"(.*?)([0-9]+)", label)
    if digits:
        prefix, number = digits.groups()
        try:
            return ("digits", prefix, len(number) if number.startswith("0") else 0), int(number)
        except ValueError:
            return None
    number = roman_number(label)
    if number is not None:
        return ("roman", label.islower(), 0), number
    return None


def page_list(pages):
    """Coalesce like-numbered pages. Different printed numbering systems have no shared order."""
    intervals, family = [], None
    labels = list(dict.fromkeys(label.strip() for page in pages for label in re.split(r"[,;]", page) if label.strip()))
    if len(labels) < 2:
        return "".join(labels)
    for label in labels:
        span = re.split(r"\s*[-–—]+\s*", label, maxsplit=1)
        first, last = map(numbered_page, span) if len(span) == 2 else (None, None)
        if not first or not last or first[0] != last[0]:
            first = last = numbered_page(label)
        if not first or family is not None and first[0] != family:
            return None
        family = first[0]
        intervals.append(tuple(sorted((first[1], last[1]))))
    joined = []
    for first, last in sorted(intervals):
        if joined and first <= joined[-1][1] + 1:
            joined[-1] = (joined[-1][0], max(last, joined[-1][1]))
        else:
            joined.append((first, last))

    def printed(number):
        system, prefix, width = family
        if system == "digits":
            return prefix + str(number).zfill(width)
        return roman(number).lower() if prefix else roman(number)

    return ", ".join(printed(first) if first == last else f"{printed(first)}--{printed(last)}" for first, last in joined)


def locator(page, whole, suffix, state, *, literal=False):
    typed = suffix.lstrip(", \t\n\u00a0").casefold()
    if re.match(r"[0-9]", typed) or any(typed == term.casefold() or typed.startswith(term.casefold() + " ")
                                        for term in state.locator_terms):
        return suffix
    plural = bool(re.search(r"[,;]|\S\s*[-–—]+\s*\S", page))
    generated = whole
    if not generated and page:
        generated = page if literal else state.page_terms[int(plural)] + " " + page
    if generated:
        return ", " + generated + (", " + suffix.lstrip(", \t\n") if suffix.strip(", \t\n") else "")
    return suffix


@dataclass
class Citation:
    key: str
    prefix: str
    suffix: str
    suppressed: bool
    raw: str
    record: dict | None = None

    @property
    def can_merge(self):
        return (self.record is not None and not self.record["remark"] and not self.record["locator"]
                and not self.prefix.strip() and not self.suffix.strip())

    def rendered(self, state, narrative=False, merged=None):
        if self.record is None:
            return self.raw
        prefix = (self.prefix.rstrip() + " ") if self.prefix.strip() else ""
        name = prefix + ("-" if self.suppressed else "") + citation_name(self.record["key"])
        page = self.record["page"] if merged is None else merged
        suffix = locator(page, self.record["locator"], self.suffix, state)
        return name + (" [" + suffix.lstrip(", \t\n") + "]" if narrative and suffix.strip() else suffix)

    def repeated(self, state, brackets, merged):
        if not self.record or self.record["key"] not in state.bibliography:
            return None
        page = self.record["page"] if merged is None else merged
        words = locator(page, self.record["locator"], self.suffix, state, literal=True).lstrip(", \t\n")
        if not words:
            return None
        prefix = self.prefix.strip()
        opening, closing = brackets
        if opening == "[":
            opening = r"\["
        words = words.replace("--", "–")
        return opening + (prefix + " " if prefix else "") + words + closing


def repeat_edits(scanned, groups, replacements):
    """Track plain Markdown paragraphs conservatively when there is no Pandoc AST."""
    boundaries = [match.start() for match in re.finditer(
        r"(?m)^[ \t]*(?:$|[#>|]|(?:[-+*]|[0-9]+[.)])(?=\s)|\[\^[^\]]+\]:)", scanned)]
    previous, previous_block = None, None
    for start, end, keys, literal in sorted(groups):
        block = bisect_right(boundaries, start)
        if block != previous_block:
            previous = None
        if keys:
            if literal is not None and keys[0] == previous:
                replacements[start, end] = literal
            previous = keys[-1]
        previous_block = block


def brackets(scanned):
    """Find balanced citation brackets and their top-level semicolon separators."""
    stack, found = [], {}
    for match in re.finditer(r"(?<!\\)[\[\];]", scanned):
        at, char = match.start(), match[0]
        if char == "[":
            stack.append((at, []))
        elif char == "]" and stack:
            start, stops = stack.pop()
            if scanned[at + 1:at + 2] not in ("(", ":"):
                found[start] = (at, stops)
        elif char == ";" and stack:
            stack[-1][1].append(at)
    return found


def rewrite(text, document, metadata, state, ids=None, *, diagnostics=False, finish=True, edits=None):
    if state is None:
        return text, 0
    scanned = citation_mask(text, document, metadata, include_metadata=True)
    hits = list(CITATION.finditer(scanned))
    if not hits:
        return text, 0
    starts = [hit.start() for hit in hits]

    def between(first, last):
        return hits[bisect_right(starts, first):bisect_left(starts, last)]

    pairs = brackets(scanned)
    repeat = excerpt_repeat([document], metadata, state.arguments, state.no_auto) if state.records else None
    footnotes = [(start, end) for start, (end, _) in pairs.items() if scanned[start - 1:start] == "^"] if repeat else []
    replacements, groups = {}, []
    count = 0

    def remember(start, end, members, literal=None):
        if not repeat or any(first <= start < last for first, last in footnotes):
            return
        keys = []
        for member in members:
            if member.record and member.record["remark"]:
                continue
            key = member.record["key"] if member.record else member.key
            if not any(key.startswith(prefix + ":") for prefix in REFERENCE_PREFIXES):
                keys.append(key)
        groups.append((start, end, keys, literal))

    def citation(start, end, found, narrative):
        nonlocal count
        key = found[1] or found[2]
        parsed = marker(key, state.prefix)
        record = state.resolve(key, diagnostics=diagnostics, narrative=narrative) if (
            ids is None or parsed and parsed[0] in ids) else None
        count += record is not None
        suppressed = start < found.start() and scanned[found.start() - 1] == "-"
        prefix = text[start:found.start() - suppressed]
        return Citation(key, prefix, text[found.end():end], suppressed, text[start:end], record)

    consumed = set()
    for start, (end, stops) in sorted(pairs.items(), key=lambda item: item[1][0] - item[0]):
        if scanned[start + 1:start + 2] == "^" or scanned[end + 1:end + 2] == "[":
            continue
        # A bracket immediately after a narrative marker is its suffix and is handled with it below.
        previous = bisect_left(starts, start) - 1
        if previous >= 0 and re.fullmatch(r"[ \t\n]+", scanned[hits[previous].end():start]):
            continue
        items = []
        for first, last in zip([start, *stops], [*stops, end]):
            inside = [hit for hit in between(first, last) if hit.start() not in consumed]
            if len(inside) != 1:
                break
            items.append((first + 1, last, inside[0]))
        else:
            members = [citation(first, last, hit, False) for first, last, hit in items]
            consumed.update(hit.start() for _, _, hit in items)
            if not any(member.record for member in members):
                remember(start, end + 1, members)
                continue
            rendered, literal = [], None
            index = 0
            while index < len(members):
                member = members[index]
                index += 1
                if member.record and member.record["remark"]:
                    continue
                following_index = index
                pages = [member.record["page"]] if member.can_merge else []
                while pages and index < len(members):
                    following = members[index]
                    if (not following.can_merge or member.suppressed != following.suppressed
                            or member.record["key"] != following.record["key"]):
                        break
                    pages.append(following.record["page"])
                    index += 1
                merged = page_list(pages) if len(pages) > 1 else None
                if merged is None:
                    index = following_index
                rendered.append(member.rendered(state, merged=merged).strip())
                if repeat and len(rendered) == 1:
                    literal = member.repeated(state, repeat, merged)
            replacements[start, end + 1] = "[" + "; ".join(rendered) + "]" if rendered else ""
            remember(start, end + 1, members, literal if len(rendered) == 1 else None)

    for hit in hits:
        if hit.start() in consumed:
            continue
        start, end = hit.span()
        suppressed = scanned[start - 1:start] == "-"
        start -= suppressed
        following = re.match(r"[ \t\n]*\[", scanned[end:])
        suffix = ""
        if following:
            opening = end + following.end() - 1
            pair = pairs.get(opening)
            if pair and not between(opening, pair[0]):
                suffix = text[opening + 1:pair[0]]
                end = pair[0] + 1
        member = citation(start, hit.end(), hit, not suppressed)
        if member.record:
            member.suffix = suffix
            replacements[start, end] = "" if member.record["remark"] else member.rendered(state, narrative=True)
        literal = member.repeated(state, repeat, None) if repeat and suppressed else None
        remember(start, end, [member], literal)

    if diagnostics and finish:
        state.finish()
    if repeat:
        repeat_edits(scanned, groups, replacements)
    for (start, end), replacement in sorted(replacements.items(), reverse=True):
        if not replacement:
            if text[end:end + 1] in (" ", "\t"):
                end += 1
            elif text[start - 1:start] in (" ", "\t"):
                start -= 1
        if edits is not None:
            edits.append((start, end, len(replacement)))
        text = text[:start] + replacement + text[end:]
    return text, count


def text_for(document, metadata, text, no_auto=None, named_reader=None, *, diagnostics=True):
    state = prepare([document], metadata, no_auto=no_auto, text=text, named_reader=named_reader,
                    diagnostics=diagnostics)
    return rewrite(text, document, metadata, state, diagnostics=diagnostics)[0]


def preview_text(document, metadata, text, no_auto):
    """Detach live CommonMark input and translate its positions back to the draft."""
    state = prepare([document], metadata, no_auto=no_auto, text=text, diagnostics=True)
    edits = []
    rendered, _ = rewrite(text, document, metadata, state, diagnostics=True, edits=edits)
    if not edits:
        return text, None
    old_lines = [0, *(match.end() for match in re.finditer("\n", text))]
    new_lines = [0, *(match.end() for match in re.finditer("\n", rendered))]
    starts, offsets = [], []
    delta = 0
    for start, end, size in reversed(edits):
        starts.append(start + delta)
        delta += size - (end - start)
        offsets.append((start, end, size, delta))

    def point(value):
        line, column = (int(part) for part in value.split(":"))
        if line > len(new_lines):
            return f"{line + len(old_lines) - len(new_lines)}:{column}"
        index = new_lines[line - 1] + column - 1
        edit = bisect_right(starts, index) - 1
        if edit >= 0:
            start, end, size, delta = offsets[edit]
            after = index - starts[edit]
            index = min(start + after, end) if after < size else index - delta
        original = bisect_right(old_lines, index)
        return f"{original}:{index - old_lines[original - 1] + 1}"

    def remap(position):
        start, end = position.split("-")
        return point(start) + "-" + point(end)

    return rendered, remap


def metadata_values(mapping, document, metadata, state):
    """Detach citation-bearing metadata while keeping its file references and options intact."""
    def replace(value):
        if isinstance(value, str):
            return rewrite(value, document, metadata, state)[0]
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        return value

    structural = {"references", "references+", "pdfmd-options", "bibliography", "bibliography+", "csl"}
    return {key: value if key in structural else replace(value) for key, value in mapping.items()}


def files(paths, ids=None, *, selected_path=None, data=None):
    """Detach files atomically, after reading and validating every requested file."""
    from .discovery import context, discover

    changes = []
    for path in dict.fromkeys(Path(name).resolve() for name in paths):
        if path.suffix.lower() not in (".md", ".markdown", ".qmd") or not path.is_file():
            raise RecordError("detach needs an existing Markdown file")
        document, metadata = context(path)
        record = discover(document, metadata)
        if selected_path is not None and selected_path != record:
            raise RecordError("a detach file uses a different excerpt record file")
        if data is None and not record.is_file():
            raise RecordError("excerpts.json was not found for a detach file")
        records = read(record) if data is None else data
        if ids and not ids.issubset({item["id"] for item in records["excerpts"]}):
            raise RecordError("a selected id is not in excerpts.json")
        original = path.read_bytes().decode("utf-8")
        newline = "\r\n" if core.is_crlf_text(original.encode("utf-8")) else "\n"
        text = original.replace("\r\n", "\n")
        state = prepare([document], metadata, no_auto=core.effective_no_auto(document, None),
                        diagnostics=True, text=text, data=records)
        new, count = rewrite(text, document, metadata, state, ids, diagnostics=True)
        if count:
            changes.append((path, new, newline, count))
    for path, new, newline, _ in changes:
        core.atomic_write_text(path, new, newline=newline)
    return [{"file": core.display_path(path), "markers": count} for path, _, _, count in changes]
