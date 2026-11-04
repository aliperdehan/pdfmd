"""What a report does with the `title:` of its files (v3.32.14, entry 3ek).

Pandoc reads the files of a report as one document and merges their front matter, and the LATER file's title, subtitle and
author replace the earlier ones: the title of a report of ten chapters was the last chapter's. `pdfmd-options: report-titles`
says what pdfmd does instead:

* `chapters` (the default; only with two or more files that have a `title:`): each title becomes a level-1 heading (a `\\chapter`: see `chapter_arguments`), its
  subtitle and (when it differs from the book's) its author and date a line under it, and that file's own headings go one
  level down. The first file's title and subtitle leave its front matter, so the book's title page is whatever the
  metadata files and the first file's other keys make of it (none, without a title).
* `first`: the first file's title is the book's; the later titles are dropped.
* `last`: the last title is the book's (Pandoc's own merge, said out loud); no chapter headings.

The work is done on the Markdown text of each file (hidden copies handed to Pandoc: the sources are never written), so it
is the same for every reader and writer. `core` is the `pdfmd` module (see `pdfmd_report.run`)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile

POLICIES = ("chapters", "first", "last")
DEFAULT_POLICY = "chapters"
# front matter keys of a later file that the report uses itself; any other key it sets is the first file's to set
OWN_KEYS = frozenset({"title", "subtitle", "author", "date", "chapter", "pdfmd-options", "order", "priority"})


@dataclass
class Chapter:
    """What is done to one file's text before Pandoc reads it."""
    drop: tuple[str, ...] = ()                         # front matter keys cut out
    put: dict[str, str] = field(default_factory=dict)  # front matter keys written (`last`: the final title)
    heading: str = ""                                  # Markdown put before the text
    title: str = ""                                    # the file's title (the heading's text)
    shift: bool = False                                # the file's own headings go one level down


def resolve_policy(core, first: Path, metadata_files: list[Path]) -> str:
    """`pdfmd-options: report-titles`, else `chapters`."""
    value = core.first_pdfmd_option(first, metadata_files, "report-titles")
    if value is None or value == "":
        return DEFAULT_POLICY
    word = str(value).strip().lower()
    if word not in POLICIES:
        raise SystemExit(f"pdfmd-options: report-titles: {value!r} is not one of {', '.join(POLICIES)}")
    return word


def flatten(value) -> str:
    """A front matter value as one line of text (a list of names is joined with commas)."""
    if value is None or value is False:
        return ""
    if isinstance(value, dict):
        value = value.get("name") or value.get("text") or ""
    if isinstance(value, (list, tuple)):
        return ", ".join(part for part in (flatten(item) for item in value) if part)
    return " ".join(str(value).split())


def own_front_matter(core, path: Path) -> dict:
    return core.front_matter_dict(path.read_text(encoding="utf-8-sig"))


def book_value(core, key: str, files: list[Path], metadata_files: list[Path]) -> str:
    """The author or date of the book: the first file's, else the first metadata file that sets one."""
    found = flatten(own_front_matter(core, files[0]).get(key))
    if found:
        return found
    for path in metadata_files:
        if path.suffix.lower() in (".yaml", ".yml", ".json"):
            loaded = core.front_matter_dict("---\n" + path.read_text(encoding="utf-8-sig") + "\n---\n")
            found = flatten(loaded.get(key))
            if found:
                return found
    return ""


def plan(core, files: list[Path], metadata_files: list[Path], policy: str) -> tuple[dict[Path, Chapter], list[str]]:
    """({file: what is done to it}, notes). Nothing is done (an empty dict) unless two files have a title."""
    fronts = {path: own_front_matter(core, path) for path in files}
    titled = [path for path in files if flatten(fronts[path].get("title"))]
    notes: list[str] = []
    chapters: dict[Path, Chapter] = {}
    if len(titled) < 2:
        return chapters, notes
    if policy == "first":
        for path in titled[1:]:
            chapters[path] = Chapter(drop=("title", "subtitle"))
        notes.append(f"report-titles: first: the title of {core.display_path(titled[0])} is the book's; "
                     f"{len(titled) - 1} later title{'s are' if len(titled) > 2 else ' is'} dropped")
    elif policy == "last":
        final = titled[-1]
        put = {"title": flatten(fronts[final].get("title"))}
        if flatten(fronts[final].get("subtitle")):
            put["subtitle"] = flatten(fronts[final].get("subtitle"))
        chapters[files[0]] = Chapter(drop=("title", "subtitle"), put=put)
        for path in titled:
            if path != files[0]:
                chapters[path] = Chapter(drop=("title", "subtitle"))
        notes.append(f"report-titles: last: the title of {core.display_path(final)} is the book's")
    else:
        book_author = book_value(core, "author", files, metadata_files)
        book_date = book_value(core, "date", files, metadata_files)
        for path in titled:
            front = fronts[path]
            title = flatten(front.get("title"))
            lines = [f"# {title}"]
            subtitle = flatten(front.get("subtitle"))
            byline = []
            if path != files[0]:
                for key, book in (("author", book_author), ("date", book_date)):
                    value = flatten(front.get(key))
                    if value and value != book:
                        byline.append(value)
            for line in (subtitle, ", ".join(byline)):
                if line:
                    lines += ["", f"*{line}*"]
            chapters[path] = Chapter(drop=("title", "subtitle"), heading="\n".join(lines), title=title, shift=True)
        notes.append(f"report-titles: {len(titled)} files have a title: each becomes a chapter heading and its own headings "
                     "go one level down (report-titles: first or last keeps one title as the book's)")
    if policy != "last":
        ignored = []
        for path in files[1:]:
            extra = sorted(key for key in fronts[path] if key not in OWN_KEYS and not str(key).startswith("pdfmd"))
            if extra:
                ignored.append(f"{core.display_path(path)} ({', '.join(map(str, extra))})")
        if ignored:
            notes.append("front matter of later files that a report build does not use (the first file sets the book's): "
                         + "; ".join(ignored[:4]) + (f"; +{len(ignored) - 4} more" if len(ignored) > 4 else ""))
    return chapters, notes


CHAPTER_CLASSES = frozenset({"report", "book", "memoir", "scrreprt", "scrbook", "extreport", "extbook", "amsbook"})
CHAPTER_CLASS = "report"                               # the class a report gets when nothing names one


def chapter_arguments(core, files: list[Path], metadata_files: list[Path], variables: list[str]) -> tuple[list[str], list[str], str]:
    """(variables, Pandoc options, note) for a LaTeX or PDF report: a report is chapters, so the `report` class (a new page and a
    large title for each chapter) when no document class is named anywhere, and `--top-level-division=chapter`, which makes a
    level-1 heading a `\\chapter`. A class the author named is kept; one without `\\chapter` (`article`) is said."""
    named = str(core.effective_metadata(files[0], metadata_files, list(variables)).get("documentclass") or "").strip()
    if not named:
        return [f"documentclass={CHAPTER_CLASS}"], ["--top-level-division=chapter"], \
            f"report: the document class is {CHAPTER_CLASS}, each level-1 heading a chapter (documentclass: book or article sets another)"
    if named in CHAPTER_CLASSES:
        return [], ["--top-level-division=chapter"], ""
    return [], [], f"report: the document class {named} has no chapters, so a level-1 heading is a section (documentclass: report or book makes it a chapter)"


def drop_keys(head: str, keys: tuple[str, ...]) -> str:
    """The YAML block `head` (fences included) without the top-level entries named `keys`."""
    out, skipping = [], False
    for line in head.split("\n"):
        entry = re.match(r"([A-Za-z_][\w-]*)\s*:", line)
        if entry:
            skipping = entry.group(1) in keys
        elif line.startswith(("---", "...")):
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out)


def put_keys(head: str, put: dict[str, str]) -> str:
    """`head` with `key: "value"` lines added before its closing fence."""
    if not put:
        return head
    lines = head.rstrip("\n").split("\n")
    closing = len(lines) - 1
    added = ['%s: "%s"' % (key, value.replace("\\", "\\\\").replace('"', '\\"')) for key, value in put.items()]
    return "\n".join(lines[:closing] + added + lines[closing:]) + ("\n" if head.endswith("\n") else "")


def shift_headings(core, body: str) -> str:
    """`body` with every heading one level down (six stays six); a setext heading becomes an ATX one."""
    lines = body.split("\n")
    for heading in sorted(core.scan_headings(lines), key=lambda found: -found.line):
        atx = core.ATX_HEADING_RE.match(lines[heading.line])
        if atx:
            lines[heading.line] = (lines[heading.line][:atx.start(1)] + "#" * min(heading.level + 1, 6)
                                   + lines[heading.line][atx.end(1):])
        else:
            lines[heading.line] = "#" * min(heading.level + 1, 6) + " " + lines[heading.line].strip()
            del lines[heading.line + 1]
    return "\n".join(lines)


def drop_repeated_heading(core, body: str, title: str) -> str:
    """The body without its first line when that is `# Title` again (the file said its title twice)."""
    lines = body.split("\n")
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        atx = core.ATX_HEADING_RE.match(line)
        if atx and len(atx.group(1)) == 1 and core.heading_parts(atx.group(2))[0].casefold() == title.casefold():
            return "\n".join(lines[:index] + lines[index + 1:]).lstrip("\n")
        break
    return body


def apply(core, text: str, chapter: Chapter) -> str:
    """`text` of a file (its front matter included or already cut off) as Pandoc is to read it."""
    head, body = "", text
    found = core.LEADING_FRONT_MATTER_RE.match(text)
    if found:
        head, body = text[:found.end()], text[found.end():]
        head = put_keys(drop_keys(head, chapter.drop), chapter.put)
        if not [line for line in head.rstrip("\n").split("\n")[1:-1] if line.strip()]:
            head = ""                                       # nothing is left of the front matter: no empty block
    if chapter.heading:
        body = drop_repeated_heading(core, body, chapter.title)
        if chapter.shift:
            body = shift_headings(core, body)
        body = chapter.heading + "\n\n" + body.lstrip("\n")
    return head + body


class Hidden:
    """`with Hidden() as hidden:` - copies of the inputs Pandoc is given, retitled where the plan says so (`report-build:
    patch`; `route` does the same inside `scaffold_inputs`); they are deleted on leaving."""

    def __enter__(self):
        self.paths: list[Path] = []
        return self

    def __exit__(self, *error):
        for path in self.paths:
            path.unlink(missing_ok=True)

    def copies(self, core, inputs: list[Path], files: list[Path], chapters: dict[Path, Chapter]) -> list[Path]:
        out = []
        for path, original in zip(inputs, files):
            if original not in chapters:
                out.append(path)
                continue
            text = apply(core, Path(path).read_text(encoding="utf-8-sig"), chapters[original])
            with NamedTemporaryFile("w", encoding="utf-8", suffix=".md", prefix=f".{original.stem}.pdfmd-title-",
                                    dir=Path(path).parent, delete=False) as handle:
                handle.write(text)
            self.paths.append(Path(handle.name))
            out.append(self.paths[-1])
        return out
