"""Comments cut out of the sources that leave the author's hands: `<!-- -->` in the Markdown (v3.22.0), `%` in a LaTeX
preamble, `<!-- -->` in a CSL style, and which kinds of source lose them (v3.22.4).

Moved out of `pdfmd.py` unchanged (v3.33.0, SPLIT.md). `core` is the `pdfmd` module, bound by `pdfmd.py` when it loads
(the first binding wins); the code reads `core.FENCE_RE`, `core.COMMENT_KINDS` and `core.option_flag` when it runs."""

from __future__ import annotations

import re

from pdfmd_base import core


# -- Stripping HTML comments (v3.22.0) -----------------------------------------
# `pdfmd-options.strip-comments` / --strip-comments: drop every `<!-- -->` from
# the Markdown that leaves the author's hands (the assembled file, and the source
# attached to a PDF, see ATTACH in pdfmd.py), where notes to oneself -- reviewer
# remarks, drafts, the BUILD NOTES block -- should not travel. Context-aware: a
# comment inside a fenced or indented code block or an inline code span is text,
# not a comment; YAML front matter is left alone; a few comments carry meaning
# for pdfmd itself and stay (KEEP_COMMENT_RE). A comment alone on its line takes
# the line with it, and a blank line left doubled by that goes too, so the text
# does not look gapped; one inside a sentence takes one of the spaces around it.
KEEP_COMMENT_RE = re.compile(r"\s*(?:pdfmd\b|page-?break\b|new-?page\b)", re.IGNORECASE)
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])[ \t]")


def scan_comment_line(line: str, carried: str = "") -> tuple[str, bool, str | None]:
    """One prose line with its single-line comments removed: (text, whether one
    was removed, the raw start of a comment that does not close on this line).
    ``carried`` is text already kept before ``line`` (not scanned again)."""
    kept = [carried]
    position = 0
    removed = False
    while position < len(line):
        if line[position] == "`":
            run = re.match(r"`+", line[position:]).group(0)
            close = line.find(run, position + len(run))
            while close != -1 and line[close + len(run):close + len(run) + 1] == "`":
                close = line.find(run, close + 1)       # a longer run does not close a span
            end = position + len(run) if close == -1 else close + len(run)
            kept.append(line[position:end])
            position = end
        elif line.startswith("<!--", position):
            end = line.find("-->", position + 4)
            if end == -1:
                return "".join(kept), removed, line[position:]
            if KEEP_COMMENT_RE.match(line[position + 4:end]):
                kept.append(line[position:end + 3])
                position = end + 3
                continue
            removed = True
            position = end + 3
            before = "".join(kept)
            if not before or before.endswith((" ", "\t")):
                while position < len(line) and line[position] in " \t":
                    position += 1                        # one space, not two, where it was
                if before and line[position:position + 1] in (".", ",", ";", ":", "!", "?", ")", "]"):
                    kept[:] = [before.rstrip(" \t")]      # `word <!-- c -->.` is `word.`
        else:
            kept.append(line[position])
            position += 1
    return "".join(kept), removed, None


def strip_markdown_comments(text: str) -> str:
    """``text`` without its HTML comments (see the comment above)."""
    out: list[str] = []
    lines = text.splitlines(keepends=True)
    start = 0
    front = re.match(r"^---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if front:
        start = len(front.group(0).splitlines(keepends=True))
        out.extend(lines[:start])
    fence: tuple[str, int] | None = None     # (character, length) of the open code fence
    open_comment: tuple[str, list[str]] | None = None   # (kept prefix, raw lines) of a comment still open
    in_list = indented_code = False
    source_blank = True                      # the previous SOURCE line was blank
    emitted_blank = True                     # the last line written was blank (or none yet)
    skip_blank = False                       # a dropped line left a blank one doubled

    def drop_line() -> None:
        nonlocal skip_blank
        if emitted_blank:
            skip_blank = True

    for line in lines[start:]:
        if open_comment is not None:
            prefix, raw = open_comment
            raw.append(line)
            end = line.find("-->")
            if end == -1:
                continue
            open_comment = None
            whole = "".join(raw)
            tail = line[end + 3:]
            if KEEP_COMMENT_RE.match(whole[4:len(whole) - len(tail) - 3]):
                out.append(prefix + whole)
                emitted_blank = source_blank = False
                continue
            carried = prefix.rstrip(" \t") + (" " if prefix.strip() and tail.strip() else "")
            text_after, _, opened = scan_comment_line(tail.lstrip(" \t") if not carried.strip() else tail.lstrip(" \t"), carried)
            if opened is not None:
                open_comment = (text_after, [opened])
                continue
            ending = "\n" if tail.endswith("\n") else ""
            body = text_after.rstrip("\r\n")
            if body.strip():
                out.append(body.rstrip(" \t") + ending)
                emitted_blank = source_blank = False
            else:
                drop_line()
            continue
        if fence is not None:
            out.append(line)
            match = core.FENCE_RE.match(line.rstrip("\r\n"))
            if (match and match.group("fence")[0] == fence[0] and len(match.group("fence")) >= fence[1]
                    and not match.group("rest").strip()):
                fence = None
            emitted_blank = source_blank = False
            continue
        if not line.strip():
            if skip_blank:
                skip_blank = False
            else:
                out.append(line)
                emitted_blank = True
            source_blank = True
            indented_code = False
            continue
        skip_blank = False
        match = core.FENCE_RE.match(line.rstrip("\r\n"))
        if match and not (match.group("fence")[0] == "`" and "`" in match.group("rest")):
            fence = (match.group("fence")[0], len(match.group("fence")))
            out.append(line)
            emitted_blank = source_blank = False
            continue
        deep = line.startswith(("    ", "\t"))
        if LIST_ITEM_RE.match(line):
            in_list = True
        elif not deep:
            in_list = False
        if deep and not in_list and (source_blank or indented_code):
            indented_code = True
            out.append(line)
            emitted_blank = source_blank = False
            continue
        indented_code = False
        source_blank = False
        text_after, removed, opened = scan_comment_line(line)
        if opened is not None:
            open_comment = (text_after, [opened])
            continue
        if not removed:
            out.append(line)
            emitted_blank = False
            continue
        ending = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
        body = text_after.rstrip("\r\n")
        if body.strip():
            out.append(body.rstrip(" \t") + ending)
            emitted_blank = False
        else:
            drop_line()
    if open_comment is not None:                     # unterminated: not a comment, keep it as written
        prefix, raw = open_comment
        out.append(prefix + "".join(raw))
    return "".join(out)


# -- Comments in the other kinds of source (v3.22.4) ---------------------------
# `strip-comments` names which kinds of source lose their comments, not only the
# Markdown's: `true` (all), `false`, a list (just those), or a mapping with true
# and false per kind (the rest follow the default: all where a PDF is being
# attached, none for --assemble-only). Kinds: markdown (<!-- -->), preamble
# (LaTeX `%`), bibliography (what a .bib holds outside its entries), csl (XML
# comments), metadata (a YAML file's `#` comments, v3.25.13). The YAML metadata is
# merged and written again whenever it is embedded, so the merged text never has
# them; with the metadata kind kept, an attached source also stores each metadata
# file's own text, and --restore writes that back byte for byte (when it still reads
# as the same data). A Lua filter is code and is never touched. A LaTeX comment is cut with care: a `%` after a command that ends a
# line keeps its bare `%` (it swallows the line break, which is meaning), a `%`
# in `\verb`, `\url` or a verbatim environment is text, and `% !TEX` magic
# comments stay.
COMMENT_KIND_NAMES = {
    "markdown": "markdown", "md": "markdown", "text": "markdown", "document": "markdown",
    "preamble": "preamble", "tex": "preamble", "latex": "preamble",
    "bibliography": "bibliography", "bib": "bibliography", "bibtex": "bibliography",
    "references": "bibliography", "csl": "csl", "style": "csl",
    "metadata": "metadata", "yaml": "metadata", "yml": "metadata", "lua": "lua",
}
TEX_VERBATIM_BEGIN_RE = re.compile(r"\\begin\{(verbatim\*?|Verbatim\*?|lstlisting|minted|alltt|filecontents\*?|comment)\}")
TEX_KEEP_COMMENT_RE = re.compile(r"%+[ \t]*(?:!\s*TEX|pdfmd\b)", re.IGNORECASE)


class CommentPolicy:
    """Which kinds of source lose their comments: ``default`` for every kind not
    named, ``strip`` and ``keep`` for the ones that are."""

    def __init__(self, default: bool, strip: frozenset[str] = frozenset(), keep: frozenset[str] = frozenset()):
        self.default = default
        self.strip = frozenset(strip) - frozenset(keep)
        self.keep = frozenset(keep)

    def strips(self, kind: str) -> bool:
        if kind in self.keep:
            return False
        return kind in self.strip or self.default

    def kinds(self) -> frozenset[str]:
        return frozenset(kind for kind in core.COMMENT_KINDS if self.strips(kind))

    def adjusted(self, strip: frozenset[str], keep: frozenset[str]) -> "CommentPolicy":
        return CommentPolicy(self.default, (self.strip | strip) - keep, (self.keep | keep) - strip)


def comment_kind_set(value) -> frozenset[str]:
    names = ([str(item) for item in value] if isinstance(value, (list, tuple, set, frozenset))
             else re.split(r"[\s,]+", str(value or "")))
    return frozenset(COMMENT_KIND_NAMES[name.casefold()] for name in names if name.casefold() in COMMENT_KIND_NAMES)


def parse_comment_policy(value, default: bool) -> CommentPolicy:
    """``pdfmd-options.strip-comments`` as a policy (see the comment above)."""
    if isinstance(value, dict):
        wanted = {comment_kind_set(name): core.option_flag(flag) for name, flag in value.items()}
        return CommentPolicy(default,
                             frozenset().union(*(kinds for kinds, flag in wanted.items() if flag is not False)),
                             frozenset().union(*(kinds for kinds, flag in wanted.items() if flag is False)))
    text = str(value).strip().casefold()
    if value is None:
        return CommentPolicy(default)
    if value is True or text in {"true", "yes", "on", "all"}:
        return CommentPolicy(True)
    if value is False or text in {"false", "no", "off", "none"}:
        return CommentPolicy(False)
    named = comment_kind_set(value)
    return CommentPolicy(False, named) if named else CommentPolicy(default)


def tex_comment_start(line: str) -> int | None:
    """Where the `%` comment on a LaTeX line begins, or None."""
    position = 0
    while position < len(line):
        char = line[position]
        if char == "\\":
            verb = re.match(r"\\verb\*?([^\sA-Za-z*])", line[position:])
            argument = re.match(r"\\(?:url|path|nolinkurl|href)\{", line[position:])
            if verb:
                close = line.find(verb.group(1), position + verb.end())
                position = len(line) if close == -1 else close + 1
            elif argument:
                close = line.find("}", position + argument.end())
                position = len(line) if close == -1 else close + 1
            else:
                position += 2                      # `\%`, `\\`, `\{`: the next character is not special
        elif char == "%":
            return position
        else:
            position += 1
    return None


def strip_tex_comments(text: str) -> str:
    """``text`` (LaTeX) without its `%` comments: see the comment above."""
    out: list[str] = []
    environment: str | None = None
    emitted_blank = True
    skip_blank = False
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if environment is not None:
            out.append(line)
            emitted_blank = False
            if re.search(r"\\end\{%s\}" % re.escape(environment), body):
                environment = None
            continue
        start = tex_comment_start(body)
        begin = TEX_VERBATIM_BEGIN_RE.search(body)
        if begin and (start is None or begin.start() < start):
            if not re.search(r"\\end\{%s\}" % re.escape(begin.group(1)), body[begin.end():]):
                environment = begin.group(1)
            out.append(line)
            emitted_blank = skip_blank = False
            continue
        if start is None or TEX_KEEP_COMMENT_RE.match(body[start:]):
            if body.strip():
                emitted_blank = skip_blank = False
            elif skip_blank:
                skip_blank = False
                continue
            else:
                emitted_blank = True
            out.append(line)
            continue
        code = body[:start]
        if not code.strip():                       # a comment alone on its line takes the line
            if emitted_blank:
                skip_blank = True
            continue
        emitted_blank = skip_blank = False
        # the bare % keeps the line break swallowed; the blanks before it are one space to TeX
        out.append(code.rstrip(" \t") + (" " if code.endswith((" ", "\t")) else "") + "%" + line[len(body):])
    return "".join(out)


def strip_xml_comments(text: str) -> str:
    """``text`` (a CSL style) without its `<!-- -->` comments, the lines holding only one included."""
    text = re.sub(r"^[ \t]*<!--.*?-->[ \t]*\r?\n", "", text, flags=re.DOTALL | re.MULTILINE)
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
