"""Recognise a terminal numbered source list before Pandoc reads Markdown (D112)."""

from __future__ import annotations

import base64
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from pdfmd_base import core

KEY = "numbered-references"
CHECK = "numbered-references-off"
NUMBER = r"[1-9][0-9]*"
LABEL = rf"{NUMBER}(?:[ \t]*,[ \t]*{NUMBER})*|{NUMBER}[ \t]*-[ \t]*{NUMBER}"
LINKED = rf"\[\[(?P<link_number>{NUMBER})\]\]\((?P<link_url>https?://(?:[^()\s<>]|\([^()\s<>]*\))+)\)"
MARKER = re.compile(rf"(?<![!\[\\])(?:{LINKED}|\[(?P<label>{LABEL})\](?![\](:{{]|\[(?![0-9])))", re.I)
ROW = re.compile(
    rf"^ {{0,3}}(?:(?P<ordered>{NUMBER})[.)][ \t]+|"
    rf"(?:[-+*][ \t]+)?\[(?P<bracket>{NUMBER})\](?::[ \t]*|[ \t]+))(?P<entry>\S.*?)[ \t]*$"
)
ROW_PREFIX = re.compile(r"^ {0,3}(?:[0-9]+[.)][ \t]+|(?:[-+*][ \t]+)?\[[0-9]+\](?=[: \t]))")
URL = re.compile(r"https?://[^\s<>\"']+", re.I)
NUMERIC_LINK_LABEL = re.compile(r"(?<!\\)(?:\[(?![0-9]+\])[^\[\]\n]+\]\[([0-9]+)\]|\[([0-9]+)\]\[\])")
HTML_TAG = re.compile(r"</?[A-Za-z][^<>\n]*>")
QUOTED_FENCE = re.compile(
    r"(?ms)^(?:[ \t]*>[ \t]?)+[ \t]*(?P<quote_mark>`{3,}|~{3,})[^\n]*\n"
    r".*?(?:^(?:[ \t]*>[ \t]?)+[ \t]*(?P=quote_mark)[`~]*[ \t]*$|^(?![ \t]*>)|\Z)"
)
RAW_TEX = re.compile(r"\\[a-zA-Z]+(?:\[[^\[\]\n]*\])?(?:\{[^{}]*\})+")
BARE_URL = re.compile(r"(?<![<(\w])https?://[^\s<>\"']+", re.I)

# Citeproc's citation-number is reassigned after sorting. A citation-label retains the actual
# label (including gaps), and a padded sort key orders it numerically on both supported Pandocs.
STYLE = """<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info>
    <title>pdfmd numbered references</title>
    <id>urn:pdfmd:numbered-references</id>
    <updated>2026-11-19T00:00:00+00:00</updated>
  </info>
  <citation><layout delimiter=", "><text variable="citation-label" prefix="[" suffix="]"/></layout></citation>
  <bibliography>
    <sort><key variable="call-number"/></sort>
    <layout><text variable="citation-label" prefix="[" suffix="] "/><text variable="title"/></layout>
  </bibliography>
</style>
"""


@dataclass(frozen=True)
class Entry:
    number: str
    written: str
    url: str
    key: str


def url_end(token: str, *, bare=False) -> str:
    url = token.rstrip(".,;:!?") if bare else token
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1]
    return url


def entry_for(match: re.Match) -> Entry | None:
    text = match["entry"]
    found = URL.search(text)
    if not found:
        return None
    # Markdown link destinations and an entire bare URL keep their final punctuation.
    embedded = bool(found.start() and text[found.start() - 1] in "(<")
    url = url_end(found[0], bare=bool(found.start()) and not embedded)
    try:
        domain = urlsplit(url).hostname
    except ValueError:
        return None
    if not domain:
        return None
    number = match["ordered"] or match["bracket"]
    domain = re.sub(r"[^a-z0-9]+", "-", domain).strip("-")
    return Entry(number, text, url, f"{domain or 'web'}-{number}")


def prose(text: str, source: Path, metadata) -> str:
    from pdfmd_check.lint import blank_matches
    from pdfmd_excerpts.markers import citation_mask

    scanned = citation_mask(text, source, metadata, prose=True)
    return blank_matches(RAW_TEX, blank_matches(HTML_TAG, blank_matches(QUOTED_FENCE, scanned)))


def tail(text: str, scanned: str) -> tuple[int, list[Entry], bool]:
    """Return the start and entries of the terminal block, and whether its rows are all sources."""
    offset = len(text.rstrip())
    entries = []
    complete = True
    while offset:
        start = text.rfind("\n", 0, offset) + 1
        line = text[start:offset]
        prefix = ROW_PREFIX.match(line)
        if prefix is None or not scanned[start:start + prefix.end()].strip():
            break
        match = ROW.fullmatch(line)
        entry = entry_for(match) if match else None
        if entry:
            entries.append(entry)
        elif entries and match and match["bracket"] and ":" not in prefix[0]:
            break                          # a paragraph starting with a bare [n]
        else:
            complete = False
        offset = start
        while offset and text[offset - 1].isspace():
            offset -= 1
    return offset, list(reversed(entries)), complete


def markers(text: str, scanned: str):
    """Yield whole numeric markers with offsets, keeping ordinary Markdown links and images."""
    from pdfmd_check.lint import LINK_TARGET_RE, blank_matches

    scanned = blank_matches(URL, blank_matches(LINK_TARGET_RE, scanned))
    end_of_run = -1
    for match in MARKER.finditer(text):
        if scanned[match.start()] != "[":
            continue
        if match.start() != end_of_run and match.start() and text[match.start() - 1] == "]":
            continue                     # the reference label in [text][1], rather than a numeric run
        end_of_run = match.end()
        label = match["label"] or match["link_number"]
        yield match, re.findall(NUMBER, label), "-" in label


def citation_numbers(labels: list[str], is_range: bool, entries: dict[str, Entry]) -> list[str]:
    if not all(label in entries for label in labels):
        return []
    if not is_range:
        return labels
    try:
        first, last = map(int, labels)
    except ValueError:
        return []
    if first > last or last - first >= len(entries):
        return []
    numbers = [str(number) for number in range(first, last + 1)]
    return numbers if all(number in entries for number in numbers) else []


def link_bare_url(text: str) -> str:
    # An explicit autolink works in YAML Markdown even without autolink_bare_uris.
    def link(match):
        url = url_end(match[0], bare=match[0] != text)
        return f"<{url}>" + match[0][len(url):]

    from pdfmd_check.lint import LINK_TARGET_RE, blank_matches, mask_inline

    scanned = blank_matches(LINK_TARGET_RE, mask_inline(text, False)[0])
    return BARE_URL.sub(lambda match: link(match) if scanned[match.start()] != " " else match[0], text)


@dataclass
class Plan:
    metadata: list[Path]
    tail_source: Path
    entries: dict[str, Entry]
    custom_csl: bool

    def rewrite(self, text: str, source: Path, *, native: bool = False) -> str:
        scanned = prose(text, source, self.metadata)
        if source == self.tail_source:
            stop, found, _ = tail(text, scanned)
            if found and {entry.number: entry for entry in found} == self.entries:
                if native:
                    rows = [f"[{entry.number}] {link_bare_url(entry.written)}" for entry in self.entries.values()]
                    text = text[:stop].rstrip() + "\n\n" + "\n\n".join(rows) + "\n"
                else:
                    # Parts/section selection uses the original line numbers.
                    text = text[:stop] + re.sub(r"[^\n]", "", text[stop:])
                scanned = scanned[:stop]
        limit = len(scanned)
        pieces = []
        end = 0
        run = []
        for match, labels, is_range in markers(text[:limit], scanned):
            numbers = citation_numbers(labels, is_range, self.entries)
            if not numbers:
                continue
            if match.start() != end or not run:
                pieces.append(text[end:match.start()])
                run = []
                pieces.append(run)
            run.extend(numbers)
            end = match.end()
        pieces.append(text[end:])

        def render(piece):
            if isinstance(piece, str):
                return piece
            if native:
                return ", ".join(f"[{number}]" for number in piece)
            return "[" + "; ".join("@" + self.entries[number].key for number in piece) + "]"

        return "".join(map(render, pieces))

    def data(self, include_uncited):
        width = max(map(len, self.entries))
        data = {"references": [
            {"id": entry.key, "type": "webpage", "citation-label": entry.number,
             "call-number": "n" + entry.number.zfill(width), "title": link_bare_url(entry.written), "URL": entry.url}
            for entry in self.entries.values()
        ]}
        # Full builds print every written row. In a selected section or part,
        # citeproc keeps the bibliography limited to the sources it cites.
        if include_uncited:
            data["nocite"] = "[" + "; ".join("@" + entry.key for entry in self.entries.values()) + "]"
        if not self.custom_csl:
            data["csl"] = "data:application/xml;base64," + base64.b64encode(STYLE.encode("utf-8")).decode("ascii")
            data["link-bibliography"] = False
        return data

    def metadata_args(self, scope, *, include_uncited=True) -> list[str]:
        scratch = scope.enter_context(TemporaryDirectory(prefix="pdfmd-numbered-references-"))
        target = Path(scratch) / "numbered.yaml"
        target.write_text(core.yaml.safe_dump(self.data(include_uncited), sort_keys=False, allow_unicode=True, width=1000000),
                          encoding="utf-8")
        return ["--metadata-file", str(target)]


def inspect(sources: list[Path], texts: list[str], metadata, arguments=(), reader=None, *, native=False):
    """Return (plan, diagnostic). A partial or ambiguous match leaves all input alone."""
    if not sources or any(source.suffix.lower() not in core.MARKDOWN_LIKE_SUFFIXES for source in sources):
        return None, None
    document = sources[0]
    flavour, configured_reader = core.flavour_setting(document, metadata)
    named = (reader or configured_reader or "").casefold()
    if not core.FLAVOUR_PRESETS[flavour].numbered_references or (named and not named.startswith(
            ("markdown", "md", "gfm", "commonmark"))):
        return None, None
    if not native:
        from pdfmd_reader.controls import repair_controls

        texts = [repair_controls(text) for text in texts]
    last = next((index for index in reversed(range(len(texts))) if texts[index].strip()), 0)
    if not any("[" in text and MARKER.search(text) for text in texts):
        terminal_line = texts[last].rstrip().rsplit("\n", 1)[-1]
        if not ROW_PREFIX.match(terminal_line) or not URL.search(terminal_line):
            return None, None
    enabled = core.option_flag(core.first_pdfmd_option(document, metadata, KEY)) is not False
    scanned = [prose(text, path, metadata) for text, path in zip(texts[:last + 1], sources)]
    stop, rows, complete = tail(texts[last], scanned[last])
    eligible = texts[:last] + [texts[last][:stop]]
    visible = scanned[:last] + [scanned[last][:stop]]
    matches = [marker for text, mask in zip(eligible, visible) for marker in markers(text, mask)]
    if not matches and not rows:
        return None, None
    entries = {entry.number: entry for entry in rows}
    if enabled and any(tail(text, mask)[1] for text, mask in zip(texts[:last], scanned[:last])):
        return None, "numbered references left unchanged because more than one input has a source list"
    if not matches or not complete or not entries or len(entries) != len(rows):
        return None, "incomplete numbered references: expected markers and a trailing numbered source list" if enabled else None
    for match, labels, is_range in matches:
        actual = citation_numbers(labels, is_range, entries)
        if not actual or (match["link_url"] and match["link_url"] != entries[actual[0]].url):
            return None, "incomplete numbered references: a marker does not match the trailing source list" if enabled else None
    if any((match[1] or match[2]) in entries for body in visible for match in NUMERIC_LINK_LABEL.finditer(body)):
        return None, "numbered references left unchanged because a Markdown link uses a source number" if enabled else None
    if not enabled:
        return None, CHECK
    from pdfmd_args import metadata_command_layers
    from pdfmd_bibliography.sources import command_sources
    from pdfmd_excerpts.markers import CITATION, REFERENCE_PREFIXES

    existing = {"references", "references+", "bibliography", "bibliography+", "nocite"}
    cli, _ = metadata_command_layers(list(arguments))[0]
    layers = [mapping for mapping, _ in core.load_package("pdfmd_metadata").metadata_layers(sources, list(metadata))]
    if (any(existing.intersection(layer) for layer in [cli, *layers]) or command_sources(arguments)
            or any((cite[1] or cite[2]).split(":", 1)[0] not in REFERENCE_PREFIXES
                   for body in visible for cite in CITATION.finditer(body)) or
            core.first_pdfmd_option(document, metadata, "citation-engine") in ("natbib", "biblatex") or
            any(option in ("--natbib", "--biblatex") for option in arguments)):
        return None, "numbered references left unchanged alongside an existing bibliography or citation system"
    if not native and core.CITEPROC_DISABLED:
        return None, "numbered references left unchanged because citation processing is disabled"
    if not native and named and (not named.startswith(("markdown", "md")) or "-citations" in named):
        return None, "numbered references left unchanged because the chosen reader does not parse citations"
    custom = bool(core.document_csl(sources, list(metadata)) or "csl" in cli
                  or any(option == "--csl" or option.startswith("--csl=") for option in arguments))
    return Plan(list(metadata), sources[last], entries, custom), None


def prepare(sources, metadata, arguments=(), reader=None, *, native_text=None):
    if native_text is None:
        texts = [core.read_text_best_effort(path) for path in sources]
    else:
        texts = [native_text]
    plan, issue = inspect(sources, texts, metadata, arguments, reader, native=native_text is not None)
    if issue and issue != CHECK:
        print(f"WARN  {core.display_path(sources[0])}: {issue}", file=sys.stderr)
    return plan


def native_text_for(text, document, metadata, reader=None):
    plan = prepare([document], metadata, reader=reader, native_text=text)
    return plan.rewrite(text, document, native=True) if plan else text


def reader_for(reader):
    if reader is None or reader.startswith("markdown"):
        return reader
    # The CommonMark readers in both Pandocs lack the citations extension.
    from pdfmd_reader.dialect import EXTENSIONS

    return "markdown+autolink_bare_uris+emoji" + EXTENSIONS + ("+hard_line_breaks" if "+hard_line_breaks" in reader else "")


def writer_for(writer: str) -> str:
    # Pandoc 3.1.3's Org writer emits native citation syntax and omits the
    # rendered bibliography unless its citations extension is disabled.
    return "org-citations" if writer == "org" else writer


def part_transform(plan, existing):
    if plan is None:
        return existing

    def transform(text, path):
        text = plan.rewrite(text, path)
        return existing(text, path) if existing else text

    return transform
