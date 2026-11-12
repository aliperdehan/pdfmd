"""Parts and sections of a document: the folder of parts a report or a split document is made of (`collect_parts`, `chapter_order`,
`select_parts`, `plan_scaffold`, `scaffold_inputs`, `split_into_parts`) and the headings, labelled blocks and list items a build can be
cut down to (`scan_headings`, `scan_items`, `find_heading`, `plan_sections`, `select_parts_and_sections`).

Moved out of `pdfmd.py` unchanged (v3.33.30, SPLIT.md), with `Heading`, `ScaffoldPlan`, `SectionPlan` and the constants only they read
(`ATTRIBUTE_ID_RE`, `ATX_HEADING_RE`, `HEADING_ATTRIBUTES_RE`, `HEADING_FIELD_WORDS`, `PARTS_SKIP_DIRS`, `PART_FENCE`,
`SETEXT_UNDERLINE_RE`, `TABLE_LINE_RE`). `core` is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first binding wins); the
pdfmd names the code uses (`CYRILLIC_STRICT`, `DIV_FENCE_RE`, `FUZZY_LOOKUP`, `LATIN_EXTRA`, `LEADING_FRONT_MATTER_RE`,
`PARTS_DIR_ALIASES`, `PART_CUTS`, `REPORT_BUILD`, `announce_lookup`, `auto_disabled`, `chapter_value`, `display_path`,
`effective_no_auto`, `fence_after`, `natural_key`, `parts_setting`, `promote_bare_title`, `scaffold_metadata_files` and
`strip_part_front_matter`) are read as `core.X` when it runs. `FUZZY_LOOKUP` is rebound with `global`, so it stays in `pdfmd.py`.
`DIV_FENCE_RE` is bound twice there with different patterns; the code reads the one in force at run time (the later binding).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import namedtuple
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from pdfmd_lookup import LOOKUP_TIERS, LookupAmbiguous, rank_lookup

from pdfmd_base import core


HEADING_FIELD_WORDS = {"alias": "{#id}", "stem": "heading text"}


def chapter_order(md_path: Path):
    """Sort chapters by explicit front-matter precedence.

    The order is: always-first, first, numeric values, letter-prefixed values,
    unnumbered files, last, always-last. Numeric values may be negative or
    decimal; letter-prefixed values sort by their letter prefix and number.
    """
    value = core.chapter_value(md_path)
    name = md_path.name.casefold()
    if value is None:
        return (4, "", Decimal(0), Decimal(0), name)
    normalized = value.casefold()
    if normalized == "always-first":
        return (0, "", Decimal(0), Decimal(0), name)
    if normalized == "first":
        return (1, "", Decimal(0), Decimal(0), name)
    if normalized == "last":
        return (5, "", Decimal(0), Decimal(0), name)
    if normalized == "always-last":
        return (6, "", Decimal(0), Decimal(0), name)
    relative = re.fullmatch(r"(before|after)\s+(-?(?:\d+(?:\.\d*)?|\.\d+))", normalized)
    if relative:
        offset = Decimal(0) if relative.group(1) == "before" else Decimal(2)
        return (2, "", Decimal(relative.group(2)), offset, name)
    try:
        return (2, "", Decimal(value), Decimal(1), name)
    except InvalidOperation:
        lettered = re.fullmatch(r"([a-z]+)\s*(-?(?:\d+(?:\.\d*)?|\.\d+))", normalized)
        if lettered:
            return (3, lettered.group(1), Decimal(lettered.group(2)), Decimal(1), name)
        return (3, normalized, Decimal(0), Decimal(1), name)


PARTS_SKIP_DIRS = frozenset({"backup", "backups"})


def parts_directory(scaffold: Path, setting: str) -> Path | None:
    if setting == "auto":
        for name in core.PARTS_DIR_ALIASES:
            if (scaffold.parent / name).is_dir():
                return (scaffold.parent / name).resolve()
        return None
    directory = scaffold.parent / setting
    if not directory.is_dir():
        raise SystemExit(f"{core.display_path(scaffold)}: pdfmd-options.parts names '{setting}', "
                         f"but {core.display_path(directory)} is not a folder")
    return directory.resolve()


def collect_parts(directory: Path) -> list[Path]:
    """Every part under ``directory`` in document order. Subfolders are
    walked (a folder is a part made of several files); names starting with
    ``.`` or ``_`` are skipped, so ``_scratch.md`` is a place to park notes
    and pdfmd's own hidden temp files never count; so are backup folders.
    """
    found: list[Path] = []
    for entry in sorted(directory.iterdir(), key=lambda item: core.natural_key(item.name)):
        if entry.name.startswith((".", "_")):
            continue
        if entry.is_dir():
            if entry.name.casefold() not in PARTS_SKIP_DIRS:
                found.extend(collect_parts(entry))
        elif entry.suffix.lower() == ".md":
            found.append(Path(os.path.abspath(entry)))       # not resolve(): a symlinked file or folder stays under the parts folder
    return found


def part_slug(component: str) -> str:
    """'10-introduction' -> 'introduction' (a leading number and separator
    are ordering, not naming)."""
    return re.sub(r"^\d+[-_. ]*", "", component) or component


def part_keys(relative: Path) -> tuple[set[str], set[str]]:
    """(exact keys, slug keys) a --section request may use for this part:
    the file, each folder above it, with or without the numeric prefix, and
    a top-level component's bare number.
    """
    components = list(relative.parts)
    components[-1] = Path(components[-1]).stem
    exact: set[str] = set()
    slugs: set[str] = set()
    for depth in range(len(components)):
        chain = components[:depth + 1]
        exact.add("/".join(chain).casefold())
        exact.add(chain[-1].casefold())
        slug_chain = [part_slug(item) for item in chain]
        slugs.add("/".join(slug_chain).casefold())
        slugs.add(slug_chain[-1].casefold())
        number = re.match(r"\d+", chain[-1])
        if number and depth == 0:
            exact.update({number.group(0), number.group(0).lstrip("0") or "0"})
    return exact, slugs


# A heading of a Markdown body (scan_headings): `line` is 0-based and of its text,
# `end` the line its section ends before.
Heading = namedtuple("Heading", "line level text ids end")   # line: 0-based, of the heading's text


class NoPartMatches(SystemExit):
    """A --section name that is no part's name (it may still be a heading inside one)."""


class NoHeadingMatches(SystemExit):
    """A --section name that is no heading's name."""


def select_parts(parts: list[Path], directory: Path, requests: list[str]) -> list[Path]:
    """The parts matching any request, in document order. A request matches
    a file name, its name without the numeric prefix, a folder (all parts
    inside), or a top-level number; failing an exact match, a unique prefix
    of a name. Unknown or ambiguous requests are an error that lists the
    choices -- a typo must never silently build the wrong section. Top-level
    files with the same name apart from their numbers (`05-introduction`,
    `10-introduction`) are one section in two files: the name builds both.
    """
    keyed = {part: part_keys(part.relative_to(directory)) for part in parts}
    chosen: set[Path] = set()
    for request in requests:
        wanted = request.strip().casefold().removesuffix(".md")
        if not wanted:
            continue
        hits = [part for part, (exact, slugs) in keyed.items() if wanted in exact or wanted in slugs]
        # `45-60`: every top-level part numbered from 45 to 60 (a name that is literally `45-60` wins above).
        span = re.fullmatch(r"(\d+)-(\d+)", wanted)
        if not hits and span:
            low, high = sorted((int(span.group(1)), int(span.group(2))))
            hits = [part for part in parts
                    if (lead := re.match(r"\d+", part.relative_to(directory).parts[0]))
                    and low <= int(lead.group(0)) <= high]
        if not hits:
            hits = [part for part, (_, slugs) in keyed.items()
                    if any(slug.startswith(wanted) for slug in slugs)]
        # One name must not quietly mean two unrelated sections (`yield` in
        # both Calculations and Discussion): join them yourself with a+b, or
        # spell the folder out (`discussion/yield`).
        groups = {part.relative_to(directory).parts[0] for part in hits}
        # ...but `05-introduction.md` and `10-introduction.md` are the same section split in two files: top-level files that
        # differ only in their numbers are all built (3.31.45). `intro` also takes `introduction` and `introspection`: error.
        same_name = (len(groups) > 1 and not span and all(len(part.relative_to(directory).parts) == 1 for part in hits)
                     and len({part_slug(part.stem).casefold() for part in hits}) == 1)
        if len(groups) > 1 and not span and not same_name:
            raise SystemExit(f"--section '{request}' is ambiguous: it matches parts in "
                             + ", ".join(sorted(groups))
                             + ". Name the folder too (e.g. 'folder/name'), or join with +")
        if not hits:
            tops = dict.fromkeys(part.relative_to(directory).parts[0] for part in parts)
            available = ", ".join(
                f"{part_slug(Path(top).stem)} ({(re.match(r'[0-9]+', top) or [''])[0] or '-'})"
                for top in tops)
            raise NoPartMatches(f"--section '{request}' matches no part. Available: {available}")
        chosen.update(hits)
    return [part for part in parts if part in chosen]


def select_parts_and_sections(parts: list[Path], directory: Path,
                              requests: list[str]) -> tuple[list[Path], dict[Path, list[Heading]]]:
    """select_parts, and then a heading inside a part for every name that is no
    part's: `report#sampling` builds the Sampling section of whichever part has
    it. A name starting with `#` (`report##sampling`) means a heading from the
    start, never a part. Returns the parts to build, in order, and for those
    that only a section of is wanted, the sections (lines of the part's text
    without its front matter). Naming a part whole beats naming a section."""
    chosen: set[Path] = set()
    heading_requests: list[tuple[str, NoPartMatches | None]] = []
    for request in requests:
        if request.strip().startswith("#"):
            heading_requests.append((request, None))
            continue
        try:
            chosen.update(select_parts(parts, directory, [request]))
        except NoPartMatches as error:
            heading_requests.append((request, error))
    cuts: dict[Path, list[Heading]] = {}
    if heading_requests:
        headings: list[Heading] = []
        spans: list[tuple[int, Path, int]] = []      # (offset, part, lines): where each part sits in `headings`' numbering
        offset = 0
        for part in parts:
            lines = core.strip_part_front_matter(part.read_text(encoding="utf-8-sig")).split("\n")
            headings += [heading._replace(line=heading.line + offset, end=heading.end + offset)
                         for heading in scan_items(lines)]
            spans.append((offset, part, len(lines)))
            offset += len(lines) + 1

        def home(heading: Heading) -> tuple[int, Path]:
            return next((start, part) for start, part, count in reversed(spans) if heading.line >= start)

        def describe(heading: Heading) -> str:
            start, part = home(heading)
            return (f"{part.relative_to(directory)}, "
                    + describe_heading(heading._replace(line=heading.line - start)))

        for request, part_error in heading_requests:
            try:
                heading = find_heading(headings, request, describe)
            except NoHeadingMatches as error:
                raise SystemExit(f"{part_error}\n(and no heading named like that: {error})"
                                 if part_error else str(error))
            start, part = home(heading)
            cuts.setdefault(part, []).append(heading._replace(line=heading.line - start, end=heading.end - start))
        cuts = {part: outermost_headings(found) for part, found in cuts.items() if part not in chosen}
    chosen.update(cuts)
    return [part for part in parts if part in chosen], cuts


class ScaffoldPlan:
    """What a parts-mode build consists of."""

    def __init__(self, scaffold: Path, directory: Path, parts: list[Path],
                 selected: list[Path] | None, metadata_files: list[Path],
                 cuts: dict[Path, list[Heading]] | None = None):
        self.scaffold = scaffold
        self.directory = directory
        self.parts = parts
        self.selected = selected          # None = the full report
        self.metadata_files = metadata_files
        self.cuts = cuts or {}            # selected parts built only in these sections (see PART_CUTS)

    @property
    def files(self) -> list[Path]:
        return [self.scaffold, *(self.parts if self.selected is None else self.selected)]

    @property
    def output_stem(self) -> str:
        if self.selected is None:
            return self.scaffold.stem
        # A whole top-level folder is named by the folder, not its files.
        labels: list[str] = []
        for part in self.selected:
            if part in self.cuts:
                for heading in self.cuts[part]:
                    label = item_label(heading)
                    if label not in labels:
                        labels.append(label)
                continue
            top = part.relative_to(self.directory).parts[0]
            siblings = [other for other in self.parts
                        if other.relative_to(self.directory).parts[0] == top]
            whole = len(siblings) > 1 and all(other in self.selected for other in siblings)
            label = part_slug(Path(top).stem if whole or len(part.relative_to(self.directory).parts) == 1
                              else part.with_suffix("").name)
            if label not in labels:
                labels.append(label)
        return f"{self.scaffold.stem}.{'+'.join(labels)}"


def warn_shared_parts_folder(scaffold: Path, directory: Path, setting: str) -> None:
    """With `parts: auto`, EVERY Markdown file beside a parts/ folder counts as
    its scaffold. That is right for the usual folder (one report.md), and
    surprising when a notes.md or draft sits there too: say so once, rather
    than silently building the same parts into both.
    """
    if setting != "auto":
        return
    others = []
    for item in sorted(scaffold.parent.glob("*.md")):
        if item == scaffold or item.name.startswith("."):
            continue
        probed = _probe_scaffold(item, directory, None)
        if probed is not None and probed[1] == "auto":
            others.append(item.name)
    if others:
        print(f"WARN  {core.display_path(scaffold)}: {core.display_path(directory)} also sits beside "
              f"{', '.join(others)}, which `parts: auto` builds from it too; put "
              "`pdfmd-options: {parts: false}` in the files that are not the report",
              file=sys.stderr)


def _probe_scaffold(
    candidate: Path, ancestor: Path, requested: list[str] | None,
) -> tuple[list[Path], str, Path, list[Path]] | None:
    """An upward candidate is speculative: keep its diagnostics only if it belongs to this build.

    Validate YAML here because the ordinary settings readers deliberately ignore malformed YAML.
    Catch SystemExit as well as ordinary probe errors, but leave interrupts and actual section selection alone.
    """
    output, errors = StringIO(), StringIO()
    try:
        with redirect_stdout(output), redirect_stderr(errors):
            text = candidate.read_text(encoding="utf-8-sig")
            front = core.LEADING_FRONT_MATTER_RE.match(text)
            if front and core.yaml is not None:
                core.yaml.safe_load(front.group("yaml"))
            if requested is None:
                requested = core.option_names(core.frontmatter_pdfmd_options(candidate), "yaml") or None
            found = core.find_metadata(candidate.parent.resolve(), requested,
                                       document_stem=candidate.stem, document=candidate)
            metadata = ([] if found is None or found is core.AUTO_METADATA_DISABLED
                        else found if isinstance(found, list) else [found])
            for path in metadata:
                text = path.read_text(encoding="utf-8-sig")
                front = core.LEADING_FRONT_MATTER_RE.match(text)
                if core.yaml is not None:
                    core.yaml.safe_load(front.group("yaml") if front else text)
            setting = core.parts_setting(candidate, metadata)
            if not setting:
                return None
            directory = parts_directory(candidate, setting)
            if directory is None:
                raise ValueError("no parts folder found")
            if directory != ancestor.resolve():
                return None
            parts = collect_parts(directory)
    except (Exception, SystemExit) as error:
        if core.VERBOSE_OUTPUT:
            reason = " ".join(str(error).split()) or type(error).__name__
            print(f"NOTE  skipped scaffold candidate {core.display_path(candidate)}: {reason}")
        return None
    print(output.getvalue(), end="")
    print(errors.getvalue(), end="", file=sys.stderr)
    return metadata, setting, directory, parts


def plan_scaffold(source: Path, sections: list[str], cli_no_auto: list[str] | None,
                  requested_metadata: list[str] | None) -> ScaffoldPlan | None:
    """Decide whether ``source`` is a scaffold, or a part of one, and what to
    build; None means an ordinary document. ``source`` may be the scaffold
    itself, or any file inside its parts folder -- found by walking up to a
    folder whose scaffold names this one, so a part builds with the same
    metadata, paths and bibliography as the full report. A part given by path
    is built alone even if parts-mode skips it (an ``_underscore`` draft).
    """
    if source.suffix.lower() != ".md" or core.auto_disabled(core.effective_no_auto(source, cli_no_auto), "parts"):
        return None
    mfiles = core.scaffold_metadata_files(source, requested_metadata)
    setting = core.parts_setting(source, mfiles)
    directory = parts_directory(source, setting) if setting else None
    if directory is not None:
        parts = collect_parts(directory)
        if not parts:
            raise SystemExit(f"{core.display_path(directory)} has no Markdown parts")
        selected, cuts = select_parts_and_sections(parts, directory, sections) if sections else (None, {})
        warn_shared_parts_folder(source, directory, setting)
        return ScaffoldPlan(source, directory, parts, selected, mfiles, cuts)
    for ancestor in list(source.parents)[:4]:
        root = ancestor.parent
        if root == ancestor:
            break
        for candidate in sorted(root.glob("*.md")):
            probed = _probe_scaffold(candidate, ancestor, requested_metadata)
            if probed is not None:
                candidate_meta, candidate_setting, candidate_dir, parts = probed
                warn_shared_parts_folder(candidate, candidate_dir, candidate_setting)
                more, cuts = select_parts_and_sections(parts, candidate_dir, sections) if sections else ([], {})
                chosen = {source, *more}
                selected = sorted(chosen, key=lambda part: parts.index(part) if part in parts else len(parts))
                return ScaffoldPlan(candidate, candidate_dir, parts, selected, candidate_meta,
                                    {part: found for part, found in cuts.items() if part != source})
    return None


PART_FENCE = ":::::::"


def wrap_part(text: str, keep: bool) -> str:
    """``text`` as a fenced div that pdfmd_lua/select.lua keeps or drops once pandoc-crossref has numbered the whole."""
    return '%s {.pdfmd-part pdfmd-keep="%s"}\n\n%s\n\n%s\n' % (PART_FENCE, "yes" if keep else "no",
                                                                text.strip("\n"), PART_FENCE)


def wrap_runs(text: str, kept: list[tuple[int, int]]) -> str:
    """``text`` as consecutive part divs: the lines inside the (start, end) ranges ``kept`` marked yes, the rest no."""
    lines = text.split("\n")
    flags = [False] * len(lines)
    for start, end in kept:
        for index in range(start, min(end, len(lines))):
            flags[index] = True
    pieces, begin = [], 0
    for index in range(1, len(lines) + 1):
        if index == len(lines) or flags[index] != flags[begin]:
            chunk = "\n".join(lines[begin:index])
            if chunk.strip():
                pieces.append(wrap_part(chunk, flags[begin]))
            begin = index
    return "\n".join(pieces)


@contextmanager
def scaffold_inputs(files: list[Path], active: bool,
                    markers: dict[Path, str] | None = None,
                    select: "set[Path] | None" = None,
                    transform: "Callable[[str, Path], str] | None" = None) -> Iterator[list[Path]]:
    """Yield the files to hand Pandoc: the scaffold as is, each part with its
    front matter removed (a hidden temp copy beside it, deleted afterwards;
    a part with nothing to remove is passed through untouched). ``markers``
    maps a part to its key: that part then starts with a raw
    ``\\pdfmdpart{key}`` line (see PARTS_MARKER_DEFS), which records LaTeX's
    counters at that point in the .aux.
    """
    if not active:
        yield list(files)
        return
    temporary: list[Path] = []
    prepared = [files[0]]
    chapters = core.REPORT_BUILD.get("chapters") or {}
    try:
        for part in files[1:]:
            text = part.read_text(encoding="utf-8-sig")
            cleaned = core.strip_part_front_matter(text)
            if transform is not None:
                cleaned = transform(cleaned, part)     # a rewrite of the part's text (ASCII tables), before it is cut or wrapped
            if part in chapters:
                import pdfmd_report.titles as report_titles
                cleaned = report_titles.apply(core, cleaned, chapters[part])
            if select is not None:
                # every part goes in, wrapped; select.lua drops the ones (or the sections) not asked for
                if part in select and part in core.PART_CUTS:
                    cleaned = wrap_runs(cleaned, [(heading.line, heading.end) for heading in core.PART_CUTS[part]])
                else:
                    cleaned = wrap_part(cleaned, part in select)
            elif part in core.PART_CUTS:
                # Only some sections of this part (a `#name` that is no part's
                # name): no counter marker -- it would restore the counters of
                # the part's start, not of the section's.
                lines = cleaned.split("\n")
                cleaned = "\n\n".join("\n".join(lines[heading.line:heading.end]).rstrip("\n")
                                       for heading in core.PART_CUTS[part]) + "\n"
            elif markers and part in markers:
                cleaned = "```{=latex}\n\\pdfmdpart{%s}\n```\n\n%s" % (markers[part], cleaned)
            if cleaned == text:
                prepared.append(part)
                continue
            with NamedTemporaryFile("w", encoding="utf-8", suffix=".md",
                                    prefix=f".{part.stem}.pdfmd-part-", dir=part.parent,
                                    delete=False) as handle:
                handle.write(cleaned)
                temporary.append(Path(handle.name))
            prepared.append(temporary[-1])
        yield prepared
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def split_top_level_sections(body: str, level: int = 1) -> list[list[str]]:
    """Cut Markdown at its headings of exactly `level` (1 = `# ` or a line
    underlined with `===`; 2 = `## ` or `---`; see scan_headings, which also
    leaves alone a `#` line inside a fenced code block or an HTML comment).
    Element 0 is whatever comes before the first one (often a comment block);
    each later element starts with a heading's own first line."""
    lines = body.split("\n")
    cuts = [heading.line for heading in scan_headings(lines) if heading.level == level]
    bounds = [0, *cuts, len(lines)]
    return [lines[start:end] for start, end in zip(bounds, bounds[1:])]


def slug_of(heading_line: str) -> str:
    title = re.sub(r"\{#[^}]*\}", "", heading_line.lstrip("# "))
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")
    if len(slug) > 30:   # cut at a word boundary, not mid-word
        slug = slug[:30].rsplit("-", 1)[0] if "-" in slug[:30] else slug[:30]
    return slug or "part"



# --- Rendering one section of an ordinary document: `pdfmd doc#methods` -------
#
# A document that is not in parts mode has no parts to name, so a section is cut
# out of the text: a heading, and everything up to the next heading of the same
# or a higher level (its subsections included). The cut document is the
# document's own front matter, the text before its first heading, and the
# chosen sections, built as a partial build (see ScaffoldPlan): title page and
# settings kept, written as `doc.NAME.pdf`, no BUILD NOTES stamp,
# `pdfmd-partial: true`. A section is named the way a file is (lookup_key and
# LOOKUP_TIERS: `onlyapart`, `only_a_part` and `Only a Part` are one name), by
# its `{#id}` too, one level down with `/` (`results/yield`), and a leading run
# of `#` restricts it to that heading level (`doc##yield`).

ATX_HEADING_RE = re.compile(r" {0,3}(#{1,6})[ \t]+(.*?)[ \t]*$")
SETEXT_UNDERLINE_RE = re.compile(r" {0,3}(=+|-+)[ \t]*$")
HEADING_ATTRIBUTES_RE = re.compile(
    r"^(?:\s*(?:#[^\s{}]+|\.[^\s{}]+|[\w:-]+=(?:\"[^\"]*\"|'[^']*'|[^\s{}]+)|-))+\s*$")


def heading_parts(raw: str) -> tuple[str, list[str]]:
    """(plain text, explicit ids) of a heading's text as written: the closing
    ``#``s and a trailing ``{#id .class}`` block removed, links and spans
    reduced to their text."""
    text = re.sub(r"[ \t]+#+$", "", raw.strip())
    ids: list[str] = []
    match = re.search(r"\s+\{([^{}]*)\}\s*$", text)     # `[span]{.c}` is not the heading's own
    if match and HEADING_ATTRIBUTES_RE.match(match.group(1)):
        ids = re.findall(r"(?:^|\s)#([^\s{}]+)", match.group(1))
        text = re.sub(r"[ \t]+#+$", "", text[:match.start()].strip())
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\{[^}]*\}", r"\1", text)
    return text.strip(), ids


def scan_headings(lines: list[str]) -> list[Heading]:
    """Every heading of a Markdown body, ATX (``## Title``) and setext (a line
    underlined with ``===`` or ``---``) alike, in order, each with the line it
    ends before: the next heading of the same or a higher level, or the end.
    A ``#`` line inside a fenced code block or an HTML comment is not one, and
    a setext heading needs a blank line (or the start) before its text, so a
    paragraph's last line, a table rule and a ``---`` rule are left alone."""
    found: list[tuple[int, int, str]] = []
    fence = ""
    comment = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        was_comment = comment
        if not comment:
            fence = core.fence_after(fence, stripped)
        if not fence and not was_comment:
            atx = ATX_HEADING_RE.match(line)
            if atx:
                found.append((index, len(atx.group(1)), atx.group(2)))
            elif (stripped and index + 1 < len(lines) and (index == 0 or not lines[index - 1].strip())
                  and SETEXT_UNDERLINE_RE.match(lines[index + 1])
                  and not SETEXT_UNDERLINE_RE.match(line) and "<!--" not in line
                  and not line.startswith(("    ", "\t", ">", "- ", "* ", "+ ", "|"))):
                found.append((index, 1 if lines[index + 1].lstrip().startswith("=") else 2, line))
        if not fence:
            position = 0
            while True:
                if not comment:
                    at = line.find("<!--", position)
                    if at < 0:
                        break
                    comment, position = True, at + 4
                else:
                    at = line.find("-->", position)
                    if at < 0:
                        break
                    comment, position = False, at + 3
    headings = []
    for number, (index, level, raw) in enumerate(found):
        text, ids = heading_parts(raw)
        end = next((later for later, later_level, _ in found[number + 1:] if later_level <= level), len(lines))
        headings.append(Heading(index, level, text, tuple(ids), end))
    return headings


ATTRIBUTE_ID_RE = re.compile(r"\{[^{}]*?#([^\s{}]+)[^{}]*\}")
TABLE_LINE_RE = re.compile(r"\s*(?:[|+].*|[-=+| :]{3,})$")


def block_ids(text: str) -> list[str]:
    return ATTRIBUTE_ID_RE.findall(text)


def scan_labelled_blocks(lines: list[str], headings: list[Heading]) -> list[Heading]:
    """The elements of a Markdown body that carry a ``{#id}`` and are not
    headings, as Heading(level=0): a fenced div (``::: {#id}``, to its closing
    fence), a fenced code block (``{#lst:x}`` on the fence), a table (the
    ``: caption {#tbl:x}`` line and the table it belongs to), and any other
    paragraph with an id in it -- a figure ``![..](..){#fig:x}``, an equation
    ``$$..$$ {#eq:x}``, a ``[span]{#id}``. A paragraph is a run of lines up to
    a blank one, so a labelled list item is its whole list. ``text`` names the
    kind; ``end`` is exclusive."""
    taken = {heading.line for heading in headings}
    taken |= {heading.line + 1 for heading in headings
              if heading.line + 1 < len(lines) and SETEXT_UNDERLINE_RE.match(lines[heading.line + 1])
              and not ATX_HEADING_RE.match(lines[heading.line])}
    found: list[Heading] = []
    chunks: list[list] = []                      # [start, end, ids] of text runs
    divs: list[tuple[int, int, list[str]]] = []  # open fenced divs
    run_start: int | None = None
    index = 0

    def close_run(end: int) -> None:
        nonlocal run_start
        if run_start is not None:
            ids = [identifier for line_no in range(run_start, end) if line_no not in taken
                   for identifier in block_ids(lines[line_no])]
            chunks.append([run_start, end, ids])
            run_start = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if index in taken:
            # A heading line (and a setext underline): it ends the paragraph before it and
            # never starts one, even with no blank line between it and the text below.
            close_run(index)
            index += 1
            continue
        fence = core.fence_after("", stripped)
        if fence:
            close_run(index)
            end = next((later + 1 for later in range(index + 1, len(lines))
                        if not core.fence_after(fence, lines[later].strip())), len(lines))
            ids = block_ids(line)
            if ids:
                found.append(Heading(index, 0, "code block", tuple(ids), end))
            index = end
            continue
        if stripped.startswith("<!--") and "-->" not in stripped:
            close_run(index)
            index = next((later + 1 for later in range(index + 1, len(lines)) if "-->" in lines[later]), len(lines))
            continue
        div = core.DIV_FENCE_RE.match(line)
        if div:
            close_run(index)
            if div.group(2).strip():
                divs.append((index, len(div.group(1)), block_ids(div.group(2))))
            elif divs:
                start, _, ids = divs.pop()
                if ids:
                    found.append(Heading(start, 0, "div", tuple(ids), index + 1))
            index += 1
            continue
        if not stripped:
            close_run(index)
        elif run_start is None:
            run_start = index
        index += 1
    close_run(len(lines))
    for position, (start, end, ids) in enumerate(chunks):
        if not ids:
            continue
        kind = "equation" if "$$" in "".join(lines[start:end]) else (
            "figure" if lines[start].lstrip().startswith("![") else "paragraph")
        first = lines[start].lstrip()
        if first.startswith((": ", "Table:")):
            # A table caption: the table is the run before it, or, for a caption written
            # above the table, the run after it.
            before = chunks[position - 1] if position else None
            after = chunks[position + 1] if position + 1 < len(chunks) else None
            if before and TABLE_LINE_RE.match(lines[before[0]]):
                start, kind = before[0], "table"
            elif after and TABLE_LINE_RE.match(lines[after[0]]):
                end, kind = after[1], "table"
        found.append(Heading(start, 0, kind, tuple(ids), end))
    return sorted(found, key=lambda item: (item.line, item.end))


def scan_items(lines: list[str]) -> list[Heading]:
    """Everything `#name` can name in a body: its headings (level 1-6) and its
    labelled elements (level 0), in order."""
    headings = scan_headings(lines)
    return sorted(headings + scan_labelled_blocks(lines, headings), key=lambda item: (item.line, item.level == 0))


def parse_section_request(request: str) -> tuple[int | None, list[str]]:
    """``##yield`` -> (2, ["yield"]); ``results/yield`` -> (None, ["results", "yield"])."""
    match = re.match(r"\s*(#*)(.*)$", request)
    return (len(match.group(1)) or None), [name.strip() for name in match.group(2).split("/") if name.strip()]


def describe_heading(heading: Heading) -> str:
    if not heading.level:
        return f"line {heading.line + 1}: {heading.text} {{#{heading.ids[0]}}}"
    return f"line {heading.line + 1}: {'#' * heading.level} {heading.text}"


def item_label(item: Heading) -> str:
    """The file-name label of a section or element."""
    return section_label(item.text if item.level else item.ids[0])


def find_heading(headings: list[Heading], request: str, describe=None) -> Heading:
    """The one heading ``request`` names. Unknown or ambiguous names are an
    error that lists the choices: a typo must never silently build the wrong
    section."""
    describe = describe or describe_heading
    level, names = parse_section_request(request)
    if not names:
        raise SystemExit(f"--section '{request}' names no heading")
    tiers = LOOKUP_TIERS if core.FUZZY_LOOKUP else LOOKUP_TIERS[:3]
    pool = list(headings)
    pool_owner = None                                      # the heading the pool is inside, from the second name on
    for position, name in enumerate(names):
        last = position == len(names) - 1
        candidates = [heading for heading in pool if not last or level is None or heading.level == level]
        # Keyed by position: two items may begin on one line, and a line number would merge them.
        entries = [(number, [("alias", identifier) for identifier in heading.ids]
                    + ([("stem", heading.text)] if heading.level else []))
                   for number, heading in enumerate(candidates)]
        try:
            found = rank_lookup(name, entries, lambda number: describe(candidates[number]),
                                HEADING_FIELD_WORDS, tiers)
        except LookupAmbiguous as error:
            raise SystemExit(f"--section '{request}': {error} Add `#`s for its level, or `parent/name`.")
        if not found:
            choices = "; ".join((f"{'#' * heading.level} {heading.text}" if heading.level else f"{{#{heading.ids[0]}}}")
                                for heading in candidates[:12])
            raise NoHeadingMatches(f"--section '{request}' matches no heading"
                             + (f" at level {level}" if last and level else "")
                             + (f" under '{pool_owner.text}'" if pool_owner else "")
                             + f". Headings: {choices or 'none'}" + (" ..." if len(candidates) > 12 else ""))
        heading = candidates[found[0]]
        core.announce_lookup(name, describe(heading), *found[1:], words=HEADING_FIELD_WORDS, subject="heading or element")
        pool_owner = heading
        pool = [other for other in headings if heading.line < other.line < heading.end]
    return heading


def outermost_headings(chosen: list[Heading]) -> list[Heading]:
    """In document order, without any heading already inside another one chosen."""
    ordered = sorted(set(chosen), key=lambda heading: heading.line)
    kept: list[Heading] = []
    for heading in ordered:
        if not kept or heading.line >= kept[-1].end:
            kept.append(heading)
    return kept


def section_label(text: str) -> str:
    """A file-name label for a heading, Cyrillic and Turkish letters written in Latin."""
    return slug_of("".join(core.CYRILLIC_STRICT.get(letter, core.LATIN_EXTRA.get(letter, letter))
                           for letter in text.casefold()))



class SectionPlan:
    """A plain document cut down to some of its sections (see above)."""

    def __init__(self, source: Path, text: str, shifted: bool, selected: list[Heading]):
        self.source = source
        self.text = text            # the document pdfmd hands Pandoc instead of the file
        self.shifted = shifted      # the document's leading `# Title` became its title
        self.selected = selected
        self.full_text = text       # the whole document, the selection in part divs (set by plan_sections)
        self.calc_text = ""         # the whole document with a mark around each section chosen, "" when nothing else holds text (for the calculator)

    @property
    def output_stem(self) -> str:
        labels = list(dict.fromkeys(item_label(item) for item in self.selected))
        return f"{self.source.stem}.{'+'.join(labels)}"


def section_source(source: Path, cli_no_auto: list[str] | None,
                   requested_metadata: list[str] | None) -> tuple[str, list[str], bool]:
    """(front matter, body lines, shifted) of ``source`` as pdfmd would give it
    to Pandoc: the same bare-`# Title` promotion first, so headings are cut
    from the text that is actually built."""
    raw = source.read_text(encoding="utf-8-sig")
    if core.auto_disabled(core.effective_no_auto(source, cli_no_auto), "title"):
        promoted, shifted = raw, False
    else:
        promoted, shifted = core.promote_bare_title(
            raw, has_external_metadata=bool(core.scaffold_metadata_files(source, requested_metadata)))
    front = core.LEADING_FRONT_MATTER_RE.match(promoted)
    end = front.end() if front else 0
    return promoted[:end], promoted[end:].split("\n"), shifted


def plan_sections(source: Path, requests: list[str], cli_no_auto: list[str] | None,
                  requested_metadata: list[str] | None) -> SectionPlan:
    head, lines, shifted = section_source(source, cli_no_auto, requested_metadata)
    items = scan_items(lines)
    if not items:
        raise SystemExit(f"{core.display_path(source)} has no headings or {{#labels}} to take a section of"
                         + (" (its first `# Title` became the document's title)" if shifted else ""))
    selected = outermost_headings([find_heading(items, request) for request in requests])
    # The text before the first heading (an abstract, a \tableofcontents) comes
    # with a section, as in parts mode, but not with a lone figure or equation.
    first_heading = next((item.line for item in items if item.level), len(lines))
    with_lead = any(item.level for item in selected)
    lead = "\n".join(lines[:first_heading]).strip("\n") if with_lead else ""
    blocks = ([lead] if lead else []) + ["\n".join(lines[item.line:item.end]).rstrip("\n")
                                         for item in selected if not (lead and item.end <= first_heading)]
    plan = SectionPlan(source, head + "\n\n".join(blocks) + "\n", shifted, selected)
    # the whole document with the selection marked, for the writers that number it whole (see wrap_part)
    kept = [(item.line, item.end) for item in selected] + ([(0, first_heading)] if lead else [])
    plan.full_text = head + wrap_runs("\n".join(lines), kept) + "\n"
    outside = [line for number, line in enumerate(lines) if not any(start <= number < stop for start, stop in kept)]
    if any(line.strip() for line in outside):
        pieces, position = [], 0
        for start, stop in sorted(kept):
            pieces += ["\n".join(lines[position:start]), "pdfmd-calc-mark-in", "\n".join(lines[start:stop]), "pdfmd-calc-mark-out"]
            position = stop
        pieces.append("\n".join(lines[position:]))
        plan.calc_text = head + "\n\n".join(piece for piece in pieces if piece.strip()) + "\n"
    return plan


def split_into_parts(source: Path, destination: Path, depth: int = 1) -> int:
    """Turn a single-file document into a scaffold plus parts in a NEW folder
    (never in place), and link everything else the document refers to, so the
    result builds as it stands. Returns 0 if the Pandoc AST of the parts
    equals the original's, 1 if not (the cut is then wrong; nothing is
    claimed). The source is not modified.
    """
    text = source.read_text(encoding="utf-8-sig")
    front = re.match(r"^---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if not front:
        raise SystemExit(f"{source}: --split needs YAML front matter (it becomes the scaffold)")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"{destination} exists and is not empty; --split writes to a new folder")
    sections = split_top_level_sections(text[front.end():])
    if len(sections) < 2:
        raise SystemExit(f"{source}: no level-1 headings ('# Title', or a line underlined with ===) to split at")
    parts_dir = destination / "parts"
    parts_dir.mkdir(parents=True)
    lead = "\n".join(sections[0]).strip("\n")
    scaffold = destination / f"{source.stem}.md"
    scaffold.write_text(text[:front.end()] + (("\n" + lead + "\n") if lead else ""), encoding="utf-8")
    written: list[Path] = []

    def emit(section: list[str], directory: Path, number: int, level: int) -> None:
        """One file per section; with depth left, a folder whose first file
        holds the heading and the text before its first subheading and whose
        other files are the subsections (selecting the folder selects all)."""
        slug = slug_of(section[0])
        pieces = split_top_level_sections("\n".join(section), level + 1) if level < depth else [section]
        if len(pieces) < 2:
            part = directory / f"{number * 10:02d}-{slug}.md"
            part.write_text("\n".join(section).rstrip("\n") + "\n", encoding="utf-8")
            written.append(part)
            return
        folder = directory / f"{number * 10:02d}-{slug}"
        folder.mkdir()
        lead = folder / f"00-{slug}.md"
        lead.write_text("\n".join(pieces[0]).rstrip("\n") + "\n", encoding="utf-8")
        written.append(lead)
        for index, piece in enumerate(pieces[1:], 1):
            emit(piece, folder, index, level + 1)

    for number, section in enumerate(sections[1:], 1):
        emit(section, parts_dir, number, 1)
    skip = {source.name.casefold()}
    for entry in sorted(source.parent.iterdir()):
        if (entry.name.startswith(".") or entry.name.casefold() in skip or entry.name.casefold() in PARTS_SKIP_DIRS
                or entry.suffix.lower() in {".pdf", ".md"} or (destination / entry.name).exists()
                or entry.resolve() in (destination, *destination.parents)):
            continue
        link = destination / entry.name
        try:
            link.symlink_to(os.path.relpath(entry.absolute(), destination), target_is_directory=entry.is_dir())
        except OSError:
            # Windows without the symlink privilege (no Developer Mode, not elevated) cannot link: copy instead
            if entry.is_dir():
                shutil.copytree(entry, link)
            else:
                shutil.copy2(entry, link)
    original = subprocess.run(["pandoc", str(source), "-t", "native"], capture_output=True, encoding="utf-8", errors="replace")
    split = subprocess.run(["pandoc", str(scaffold), *map(str, written), "-t", "native"],
                           capture_output=True, encoding="utf-8", errors="replace")
    print(f"SPLIT  {core.display_path(source)} -> {core.display_path(scaffold)} + {len(written)} parts in "
          f"{core.display_path(parts_dir)}")
    if original.returncode == 0 and original.stdout == split.stdout:
        print("OK     the parts read back as the identical document (Pandoc AST compared)")
        if not core.parts_setting(scaffold, core.scaffold_metadata_files(scaffold, None)):
            print("NOTE   parts mode is off for this document: add `pdfmd-options: {parts: auto}` "
                  "to its metadata.yaml (or the scaffold's front matter) to build from the parts")
        return 0
    print("FAIL   the parts do NOT read back as the original; do not use this split", file=sys.stderr)
    return 1
