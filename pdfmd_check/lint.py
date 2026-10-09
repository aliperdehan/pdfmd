"""The checks of `pdfmd --check` (see the package docstring)."""

from __future__ import annotations

import bisect
import difflib
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:                                # pragma: no cover -- PyYAML is optional
    yaml = None

# code -> (severity, what it means). The README table is this one.
CODES: dict[str, tuple[str, str]] = {
    "front-matter": ("error", "the YAML front matter does not parse, or is opened and never closed"),
    "front-matter-duplicate": ("warning", "a front-matter key is set twice (the last one wins)"),
    "fence-open": ("error", "a code fence is never closed, so the rest of the document is code"),
    "comment-open": ("error", "an HTML comment is never closed, so the rest of the document is hidden"),
    "div-open": ("warning", "a fenced div (:::) is never closed"),
    "div-stray": ("warning", "a closing ::: with no div open"),
    "math-open": ("warning", "an odd number of $$ (a display formula is never closed)"),
    "image-missing": ("error", "an image file is not there"),
    "file-missing": ("error", "a file= of a csv div is not there"),
    "link-missing": ("warning", "a link to a local file that is not there"),
    "anchor-missing": ("warning", "a link to a #heading or {#id} that does not exist"),
    "id-duplicate": ("error", "the same {#id} is used twice"),
    "crossref-missing": ("error", "a @fig:x, @tbl:x, @eq:x, @sec:x or @lst:x with no {#fig:x} to point at"),
    "ref-missing": ("warning", "a \\ref{x} with no \\label{x} or {#x} in the document"),
    "cite-missing": ("error", "a @key the bibliography does not hold"),
    "cite-no-bibliography": ("warning", "citations in a document that names no bibliography"),
    "bibliography-missing": ("error", "a bibliography file that is not there"),
    "footnote-missing": ("warning", "a [^note] with no [^note]: definition"),
    "footnote-unused": ("warning", "a [^note]: definition nothing refers to"),
    "heading-jump": ("warning", "a heading level that skips one (# then ###)"),
    "heading-space": ("warning", "#Heading without a space after the # (it is a paragraph)"),
    "heading-empty": ("warning", "a heading with no text"),
    "asset-large": ("warning", "an image or file bigger than the size budget"),
}


@dataclass(frozen=True)
class Problem:
    file: str
    line: int                                       # 1-based; 0 = the file as a whole
    code: str
    message: str

    @property
    def severity(self) -> str:
        return CODES[self.code][0]


@dataclass
class Source:
    label: str                                      # how messages name it
    path: Path | None                               # where relative paths start (its folder); None = the current one
    text: str


@dataclass
class Bibliography:
    declared: bool = False                          # a bibliography:, references: or csl-json source is set
    keys: frozenset = frozenset()                   # lower-cased
    complete: bool = True                           # False when a file could not be read: then no key is reported missing


# --- Reading the text ------------------------------------------------------------------------------------------

FRONT_RE = re.compile(r"\A\ufeff?---[ \t]*\n(?P<yaml>.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", re.DOTALL)
FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
INLINE_TOKEN_RE = re.compile(r"<!--|(`+)")
DISPLAY_MATH_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
INLINE_MATH_RE = re.compile(r"(?<![\\$\w])\$(?![\s$])(?:[^$\n\\]|\\.)+?(?<![\s\\])\$(?!\d)")
LINK_TARGET_RE = re.compile(r"(?<=\])\([^)\n]*\)")
URL_RE = re.compile(r"https?://[^\s<>)\]]+|<[^>\s]+@[^>\s]+>|<[A-Za-z/!][^>\n]*>")
DEFINITION_LINE_RE = re.compile(r"(?m)^ {0,3}\[[^\]^][^\]]*\]:.*$")

ATTRIBUTES_RE = re.compile(
    r"\{((?:\s*(?:#[^\s{}]+|\.[^\s{}]+|[\w:-]+=(?:\"[^\"]*\"|'[^']*'|[^\s{}]+)))+)\s*\}")
IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)|<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"']",
    re.IGNORECASE)
LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
GRAPHICS_RE = re.compile(r"\\includegraphics\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
CSV_FILE_RE = re.compile(r"\{[^{}\n]*\.csv\b[^{}\n]*\}")
FILE_ATTRIBUTE_RE = re.compile(r"""\bfile\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s{}]+))""")
HTML_TAG_RE = re.compile(r"<[A-Za-z][^>]*>")
HTML_ID_RE = re.compile(r"""\b(?:id|name)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
LATEX_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
LATEX_REF_RE = re.compile(r"\\(?:eq|auto|c|C|page|name|v|)ref\*?\{([^}]+)\}")
CROSSREF_KINDS = ("fig", "eq", "tbl", "sec", "lst")
CROSSREF_RE = re.compile(r"(?<![\w@\\])@((?:" + "|".join(CROSSREF_KINDS) + r"):[-\w]+(?:[.:][-\w]+)*)")
CITE_RE = re.compile(r"(?<![\w@\\])@(?:\{([^}]+)\}|([A-Za-z0-9_](?:[\w:.#$%&+?<>~/-]*[\w])?))")
LATEX_CITE_RE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\]){0,2}\{([^}]*)\}")
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
FOOTNOTE_DEF_RE = re.compile(r"(?m)^ {0,3}\[\^([^\]\s]+)\]:")
ATX_RE = re.compile(r" {0,3}(#{1,6})[ \t]+(.*?)[ \t]*$")
ATX_EMPTY_RE = re.compile(r" {0,3}#{1,6}[ \t]*$")
ATX_NO_SPACE_RE = re.compile(r" {0,3}#{1,6}[A-Za-z]")
SETEXT_RE = re.compile(r" {0,3}(=+|-+)[ \t]*$")
DIV_OPEN_RE = re.compile(r"^ {0,3}(:{3,})[ \t]*\S")
DIV_CLOSE_RE = re.compile(r"^ {0,3}(:{3,})[ \t]*$")
DIRECTIVE_RE = re.compile(r"<!--\s*pdfmd-check:\s*ignore(?:[ \t]+([\w, -]+?))?\s*-->")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
IMAGE_EXTENSIONS = ("", ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".eps", ".gif", ".webp")


def parse_ignore(value) -> frozenset:
    """The codes of a `--check-ignore` / `pdfmd-options.check-ignore` value (a list or a comma-separated string);
    ValueError names one that is not a check."""
    if value is None or value is False:
        return frozenset()
    items = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    codes = frozenset(piece.strip().casefold() for item in items for piece in str(item).split(",") if piece.strip())
    unknown = sorted(code for code in codes if code not in CODES)
    if unknown:
        raise ValueError(f"unknown check(s): {', '.join(unknown)}; the checks are {', '.join(CODES)}")
    return codes


def blank(text: str) -> str:
    """The same text with every character but the newlines turned into a space (offsets and lines stay)."""
    return re.sub(r"[^\n]", " ", text)


def blank_matches(pattern: re.Pattern, text: str) -> str:
    return pattern.sub(lambda found: blank(found.group(0)), text)


def mask_inline(text: str, in_comment: bool) -> tuple[str, bool, int | None]:
    """``text`` (a paragraph, newlines kept) with inline code and HTML comments blanked; whether a comment is open at
    its end and the offset where one opened last."""
    pieces: list[str] = []
    position = 0
    opened: int | None = None
    while position < len(text):
        if in_comment:
            end = text.find("-->", position)
            stop = len(text) if end < 0 else end + 3
            pieces.append(blank(text[position:stop]))
            position, in_comment = stop, end < 0
            continue
        found = INLINE_TOKEN_RE.search(text, position)
        if found is None:
            break
        if found.group(1) is None:                                       # <!--
            pieces.append(text[position:found.start()])
            position, in_comment, opened = found.start(), True, found.start()
            continue
        closing = re.compile("(?<!`)" + "`" * len(found.group(1)) + "(?!`)").search(text, found.end())
        if closing is None:
            pieces.append(text[position:found.end()])
            position = found.end()
            continue
        pieces.append(text[position:found.start()] + blank(text[found.start():closing.end()]))
        position = closing.end()
    pieces.append(text[position:])
    return "".join(pieces), in_comment, opened


def mask_code(body: str) -> tuple[str, list[tuple[int, str]]]:
    """``body`` with its fenced code, inline code (across a line break too) and comments blanked, and the
    (line, code) of what is never closed."""
    lines = body.split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    fence: tuple[str, int, int] | None = None
    in_comment, comment_line = False, 0
    first_of_paragraph = 1

    def flush() -> None:
        nonlocal in_comment, comment_line
        if not paragraph:
            return
        masked, in_comment, opened = mask_inline("\n".join(paragraph), in_comment)
        if opened is not None:
            comment_line = first_of_paragraph + "\n".join(paragraph)[:opened].count("\n")
        out.extend(masked.split("\n"))
        paragraph.clear()

    for number, line in enumerate(lines, 1):
        if fence is not None:
            closing = FENCE_RE.match(line)
            if closing and closing.group(2)[0] == fence[0] and len(closing.group(2)) >= fence[1] \
                    and not closing.group(3).strip():
                fence = None
            out.append(blank(line))
            continue
        opening = None if in_comment else FENCE_RE.match(line)
        if opening and not (opening.group(2)[0] == "`" and "`" in opening.group(3)):
            flush()
            fence = (opening.group(2)[0], len(opening.group(2)), number)
            out.append(blank(line))
            continue
        if not line.strip() and not in_comment:
            flush()
            out.append(line)
            first_of_paragraph = number + 1
            continue
        if not paragraph:
            first_of_paragraph = number
        paragraph.append(line)
    flush()
    open_things = []
    if fence is not None:
        open_things.append((fence[2], "fence-open"))
    if in_comment:
        open_things.append((comment_line, "comment-open"))
    return "\n".join(out), open_things


def plain_heading(text: str) -> str:
    """A heading's text without its markup (what Pandoc and GitHub make an identifier from)."""
    text = re.sub(r"\s+\{[^{}]*\}\s*$", "", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\{[^}]*\}", r"\1", text)
    text = re.sub(r"\^\[[^\]]*\]", "", text)
    text = re.sub(r"\\(.)", r"\1", text)
    text = text.replace("*", "").replace("`", "")
    return re.sub(r"(?<!\w)_|_(?!\w)", "", text).strip()


def heading_identifiers(text: str) -> set[str]:
    """The ids a heading gets by itself: Pandoc's rule (uncollapsed and collapsed dashes) and GitHub's."""
    plain = plain_heading(text)
    found = set()
    pandoc = "".join(char for char in plain if char.isalnum() or char in "_-. " or char.isspace()).lower()
    pandoc = re.sub(r"\s", "-", pandoc.strip())
    letter = re.search(r"[^\W\d_]", pandoc)
    pandoc = pandoc[letter.start():] if letter else ""
    found.update({pandoc or "section", re.sub(r"-+", "-", pandoc) or "section"})
    github = "".join(char for char in plain.lower() if char.isalnum() or char in "_- ")
    found.add(re.sub(r"\s", "-", github.strip()))
    return found


def locate(name: str, folders: list[Path], extensions: tuple[str, ...] = ("",)) -> bool:
    path = Path(name)
    places = [path] if path.is_absolute() else [folder / path for folder in folders]
    return any(Path(str(place) + extension).exists() for place in places for extension in extensions)


def local_target(target: str) -> str | None:
    """The path part of a link or image target when it names a local file, else None (a URL, an anchor, a template)."""
    target = target.strip()
    if not target or target.startswith(("#", "//", "{{", "$", "<")) or SCHEME_RE.match(target) \
            or "(" in target or "\\" in target:
        return None
    target = urllib.parse.unquote(target.split("#")[0].split("?")[0])
    return target or None


# --- The analysis of one source ----------------------------------------------------------------------------------

class Analysis:
    def __init__(self, source: Source):
        self.source = source
        text = source.text
        self.starts = [0] + [found.end() for found in re.finditer("\n", text)]
        front = FRONT_RE.match(text)
        self.front_end = front.end() if front else 0
        self.front_yaml = front.group("yaml") if front else ""
        self.front_start_line = 2
        body_first_line = text.count("\n", 0, self.front_end) + 1
        masked_body, self.open_things = mask_code(text[self.front_end:])
        self.open_things = [(line + body_first_line - 1, code) for line, code in self.open_things]
        self.masked = blank(text[:self.front_end]) + masked_body        # code and comments gone
        self.plain = blank_matches(INLINE_MATH_RE, blank_matches(DISPLAY_MATH_RE, self.masked))   # math gone too
        cited = blank_matches(URL_RE, blank_matches(LINK_TARGET_RE, self.plain))
        self.cited = blank_matches(DEFINITION_LINE_RE, cited)
        self.ignored = self.directives(text)

    def line(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)

    def directives(self, text: str) -> dict[int, frozenset | None]:
        """line -> the codes a `<!-- pdfmd-check: ignore CODE -->` on that line or the one above turns off (None = all)."""
        ignored: dict[int, frozenset | None] = {}
        for found in DIRECTIVE_RE.finditer(text):
            line = self.line(found.start())
            codes = frozenset(item.strip().casefold() for item in re.split(r"[,\s]+", found.group(1) or "") if item.strip())
            for target in (line, line + 1):
                previous = ignored.get(target, frozenset())
                ignored[target] = None if (not codes or previous is None) else previous | codes
        return ignored


@dataclass
class Findings:
    problems: list[Problem] = field(default_factory=list)

    def add(self, analysis: Analysis, line: int, code: str, message: str) -> None:
        silenced = analysis.ignored.get(line, frozenset())
        if silenced is None or code in silenced:
            return
        self.problems.append(Problem(analysis.source.label, line, code, message))


def suggestion(word: str, known) -> str:
    close = difflib.get_close_matches(word, sorted(known), n=1, cutoff=0.75)
    return f" (did you mean {close[0]}?)" if close else ""


def lint(sources: list[Source], bibliography: Bibliography | None = None, ignore: frozenset = frozenset(),
         folders: list[Path] | None = None) -> list[Problem]:
    """The problems of ``sources`` taken as one document (a scaffold and its parts, or a single file), in order.
    ``folders`` are searched for files after the source's own folder."""
    analyses = [Analysis(source) for source in sources]
    findings = Findings()
    for analysis in analyses:
        front_matter(analysis, findings)
        for line, code in analysis.open_things:
            findings.add(analysis, line, code, {
                "fence-open": "this code fence is never closed (the rest of the document is code)",
                "comment-open": "this <!-- is never closed (the rest of the document is hidden)"}[code])
    ids = document_ids(analyses, findings)
    headings(analyses, findings, ids)
    for analysis in analyses:
        places = [analysis.source.path] if analysis.source.path else [Path.cwd()]
        places += list(folders or [])
        images_and_files(analysis, findings, places)
        links(analysis, findings, places, ids)
        structure(analysis, findings)
    cross_references(analyses, findings, ids)
    footnotes(analyses, findings)
    citations(analyses, findings, bibliography)
    problems = [problem for problem in findings.problems if problem.code not in ignore]
    order = {analysis.source.label: number for number, analysis in enumerate(analyses)}
    return sorted(problems, key=lambda item: (order.get(item.file, 0), item.line))


# --- The checks --------------------------------------------------------------------------------------------------

def front_matter(analysis: Analysis, findings: Findings) -> None:
    text = analysis.source.text
    if not analysis.front_end:
        first = text.lstrip("\ufeff").split("\n", 2)
        if first[0].strip() == "---" and len(first) > 1 and re.match(r"[\w-]+\s*:", first[1]):
            findings.add(analysis, 1, "front-matter", "the front matter opened here is never closed (--- or ...)")
        return
    if yaml is not None:
        try:
            yaml.safe_load(analysis.front_yaml)
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            reason = (getattr(error, "problem", None) or str(error)).split("\n")[0]
            findings.add(analysis, (mark.line if mark else 0) + analysis.front_start_line, "front-matter",
                         f"YAML does not parse: {reason}")
    seen: dict[str, int] = {}
    for offset, line in enumerate(analysis.front_yaml.split("\n")):
        key = re.match(r"([A-Za-z_][\w-]*)\s*:", line)
        if key:
            if key.group(1) in seen:
                findings.add(analysis, offset + analysis.front_start_line, "front-matter-duplicate",
                             f"'{key.group(1)}' is set twice in the front matter (line {seen[key.group(1)]}); "
                             "the last one wins")
            seen.setdefault(key.group(1), offset + analysis.front_start_line)


def document_ids(analyses: list[Analysis], findings: Findings) -> set[str]:
    """Every id the document defines (explicit {#id}, HTML id=, \\label, and the ones headings get by themselves);
    a {#id} used twice is reported."""
    known: set[str] = set()
    first_seen: dict[str, tuple[str, int]] = {}
    for analysis in analyses:
        for found in ATTRIBUTES_RE.finditer(analysis.masked):
            for identifier in re.findall(r"(?:^|\s)#([^\s{}]+)", found.group(1)):
                if identifier.isdigit():                                 # `{#1}` in a macro definition
                    continue
                line = analysis.line(found.start())
                known.add(identifier)
                if identifier in first_seen:
                    where = first_seen[identifier]
                    place = f"line {where[1]}" if where[0] == analysis.source.label else f"{where[0]} line {where[1]}"
                    findings.add(analysis, line, "id-duplicate", f"{{#{identifier}}} is already used ({place})")
                else:
                    first_seen[identifier] = (analysis.source.label, line)
        for tag in HTML_TAG_RE.finditer(analysis.masked):
            known.update(HTML_ID_RE.findall(tag.group(0)))
        known.update(label.strip() for label in LATEX_LABEL_RE.findall(analysis.masked))
    return known


def headings(analyses: list[Analysis], findings: Findings, ids: set[str]) -> None:
    """Heading levels in document order (a jump), empty headings, `#Heading`, and the ids headings get."""
    previous = 0
    counts: dict[str, int] = {}
    for analysis in analyses:
        lines = analysis.masked.split("\n")
        for index, line in enumerate(lines):
            number = index + 1
            level, text = 0, ""
            atx = ATX_RE.match(line)
            if atx:
                level, text = len(atx.group(1)), re.sub(r"[ \t]+#+$", "", atx.group(2))
            elif ATX_EMPTY_RE.match(line):
                findings.add(analysis, number, "heading-empty", "a heading with no text")
                continue
            elif ATX_NO_SPACE_RE.match(line) and (index == 0 or not lines[index - 1].strip()):
                findings.add(analysis, number, "heading-space",
                             "no space after the # (Pandoc reads this line as a paragraph, not a heading)")
                continue
            elif (line.strip() and index + 1 < len(lines) and (index == 0 or not lines[index - 1].strip())
                  and SETEXT_RE.match(lines[index + 1]) and not SETEXT_RE.match(line)
                  and not line.startswith(("    ", "\t", ">", "- ", "* ", "+ ", "|", ":"))):
                level, text = (1 if lines[index + 1].lstrip().startswith("=") else 2), line.strip()
            if not level:
                continue
            if previous and level > previous + 1:
                findings.add(analysis, number, "heading-jump",
                             f"heading level {previous} is followed by level {level} (level {previous + 1} is skipped)")
            previous = level
            for identifier in heading_identifiers(text):
                count = counts.get(identifier, 0)
                counts[identifier] = count + 1
                ids.add(identifier if count == 0 else f"{identifier}-{count}")


def images_and_files(analysis: Analysis, findings: Findings, folders: list[Path]) -> None:
    text = analysis.plain
    for found in IMAGE_RE.finditer(text):
        target = local_target(found.group(1) or found.group(2) or "")
        if target and not locate(target, folders, IMAGE_EXTENSIONS):
            findings.add(analysis, analysis.line(found.start()), "image-missing", f"image not found: {target}")
    for found in GRAPHICS_RE.finditer(analysis.masked):
        target = local_target(found.group(1).strip())
        if target and not locate(target, folders, IMAGE_EXTENSIONS):
            findings.add(analysis, analysis.line(found.start()), "image-missing", f"image not found: {target}")
    for found in CSV_FILE_RE.finditer(analysis.masked):
        attribute = FILE_ATTRIBUTE_RE.search(found.group(0))
        name = next((item for item in attribute.groups() if item), "") if attribute else ""
        target = local_target(name)
        if target and not locate(target, folders):
            findings.add(analysis, analysis.line(found.start()), "file-missing", f"data file not found: {target}")


def links(analysis: Analysis, findings: Findings, folders: list[Path], ids: set[str]) -> None:
    for found in LINK_RE.finditer(analysis.plain):
        if found.group(1).startswith("!"):                               # an image inside a link: the image check's
            continue
        raw = found.group(2).strip()
        line = analysis.line(found.start())
        if raw.startswith("#"):
            anchor = urllib.parse.unquote(raw[1:])
            if anchor and anchor not in ids:
                findings.add(analysis, line, "anchor-missing",
                             f"no heading or {{#id}} named '{anchor}'{suggestion(anchor, ids)}")
            continue
        target = local_target(raw)
        if target and not locate(target, folders):
            findings.add(analysis, line, "link-missing", f"link target not found: {target}")


def structure(analysis: Analysis, findings: Findings) -> None:
    stack: list[int] = []
    for number, line in enumerate(analysis.plain.split("\n"), 1):
        closing = DIV_CLOSE_RE.match(line)
        if closing:
            if stack:
                stack.pop()
            else:
                findings.add(analysis, number, "div-stray", "a closing ::: but no div is open")
        elif DIV_OPEN_RE.match(line):
            stack.append(number)
    for number in stack:
        findings.add(analysis, number, "div-open", "this fenced div is never closed")
    count = len(re.findall(r"\$\$", analysis.masked))
    if count % 2:
        last = [found.start() for found in re.finditer(r"\$\$", analysis.masked)][-1]
        findings.add(analysis, analysis.line(last), "math-open", "an odd number of $$ in this file; one is never closed")


def cross_references(analyses: list[Analysis], findings: Findings, ids: set[str]) -> None:
    for analysis in analyses:
        reported: set[str] = set()
        for found in CROSSREF_RE.finditer(analysis.cited):
            label = found.group(1)
            if label not in ids and label not in reported:
                reported.add(label)
                findings.add(analysis, analysis.line(found.start()), "crossref-missing",
                             f"@{label} has no {{#{label}}} to point at{suggestion(label, ids)}")
        for found in LATEX_REF_RE.finditer(analysis.masked):
            for label in (item.strip() for item in found.group(1).split(",")):
                if label and label not in ids and label not in reported:
                    reported.add(label)
                    findings.add(analysis, analysis.line(found.start()), "ref-missing",
                                 f"\\ref{{{label}}} has no \\label{{{label}}} or {{#{label}}} in this document"
                                 f"{suggestion(label, ids)}")


def footnotes(analyses: list[Analysis], findings: Findings) -> None:
    defined = {label for analysis in analyses for label in FOOTNOTE_DEF_RE.findall(analysis.plain)}
    used: set[str] = set()
    for analysis in analyses:
        for found in FOOTNOTE_REF_RE.finditer(analysis.plain):
            used.add(found.group(1))
            if found.group(1) not in defined:
                findings.add(analysis, analysis.line(found.start()), "footnote-missing",
                             f"[^{found.group(1)}] has no [^{found.group(1)}]: definition")
    for analysis in analyses:
        for found in FOOTNOTE_DEF_RE.finditer(analysis.plain):
            if found.group(1) not in used:
                findings.add(analysis, analysis.line(found.start()), "footnote-unused",
                             f"[^{found.group(1)}]: is never referenced")


def citations(analyses: list[Analysis], findings: Findings, bibliography: Bibliography | None) -> None:
    if bibliography is None:
        return
    uses: dict[str, list[tuple[Analysis, int]]] = {}
    for analysis in analyses:
        for found in CITE_RE.finditer(analysis.cited):
            key = (found.group(1) or found.group(2)).strip()
            if key.split(":")[0] in CROSSREF_KINDS and ":" in key or key.startswith("*"):
                continue                                                  # a cross-reference, or `@*`
            uses.setdefault(key, []).append((analysis, analysis.line(found.start())))
        if bibliography.declared:
            for found in LATEX_CITE_RE.finditer(analysis.masked):
                for key in (item.strip() for item in found.group(1).split(",")):
                    if key and key != "*":
                        uses.setdefault(key, []).append((analysis, analysis.line(found.start())))
    if not uses:
        return
    if not bibliography.declared:
        analysis, line = next(iter(uses.values()))[0]
        names = ", ".join(f"@{key}" for key in list(uses)[:4]) + (", ..." if len(uses) > 4 else "")
        findings.add(analysis, line, "cite-no-bibliography",
                     f"{len(uses)} citation(s) ({names}) but no bibliography: or references: is set")
        return
    if not bibliography.complete:
        return
    for key, places in uses.items():
        if key.casefold() in bibliography.keys:
            continue
        analysis, line = places[0]
        more = f" ({len(places)} uses)" if len(places) > 1 else ""
        findings.add(analysis, line, "cite-missing",
                     f"@{key} is not in the bibliography{more}{suggestion(key.casefold(), bibliography.keys)}")
