"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_assemble.embed`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import re
import shutil
import sys
from collections import namedtuple
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from tempfile import mkdtemp
from typing import Iterator

try:
    from pdfmd_yaml_support import yaml
except ImportError:
    yaml = None

from pdfmd_base import core


def strip_embedded_preamble(text: str) -> str:
    """``text`` without the LaTeX preamble an assembled file embeds at the
    head of its `header-includes` (everything up to PREAMBLE_END_MARK): for a
    target that is not LaTeX-family, where Pandoc would put it in the output
    as text (an HTML <head>). The document's own header-includes stay."""
    front = re.match(r"^(---[ \t]*\n)(.*?)(\n(?:---|\.\.\.)[ \t]*(?:\n|$))", text, re.DOTALL)
    if not front or PREAMBLE_END_MARK not in front.group(2):
        return text
    block = re.search(r"(?m)^header-includes: \|\n((?:  .*\n|[ \t]*\n)*)", front.group(2) + "\n")
    if not block:
        return text
    lines = block.group(1).split("\n")
    mark = f"  {PREAMBLE_END_MARK}"
    if mark not in lines:
        return text
    rest = "\n".join(lines[lines.index(mark) + 1:]).strip("\n")
    replacement = f"header-includes: |\n{rest}\n" if rest.strip() else ""
    yaml_text = front.group(2) + "\n"
    yaml_text = yaml_text[:block.start()] + replacement + yaml_text[block.end():]
    return front.group(1) + yaml_text.rstrip("\n") + front.group(3) + text[front.end():]


# A top-level front-matter key (an HTML comment where there is no front matter
# to put it in) written into every assembled file. A file that carries it is
# already the finished text of a build: parts mode never treats
# it as a scaffold (it would join the parts a second time), and batch/report
# assembly skips it instead of assembling an assembly.
ASSEMBLED_KEY = "pdfmd-assembled"


ASSEMBLED_KEY_RE = re.compile(r"^pdfmd-assembled:[ \t]*(?:true|yes|on)[ \t]*$", re.IGNORECASE | re.MULTILINE)


# `<!-- pdfmd-assembled: true; no-auto: lua,preamble -->`: the comment form of
# the marker can carry the no-auto kinds that the front-matter form keeps in
# `pdfmd-options` (see embed_into_text).
ASSEMBLED_COMMENT_RE = re.compile(
    r"^<!-- pdfmd-assembled: true(?:; no-auto: (?P<kinds>[a-z:,]+))? -->[ \t]*$", re.MULTILINE)


def is_assembled_text(text: str) -> bool:
    front_matter = re.match(r"^---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if front_matter and ASSEMBLED_KEY_RE.search(front_matter.group(1)):
        return True
    return bool(ASSEMBLED_COMMENT_RE.search(mask_embedded_blocks(text)))


def is_assembled_document(path: Path) -> bool:
    """Whether ``path`` is an assembled file written by --stop-at markdown."""
    if path.suffix.lower() not in (".md", ".markdown"):
        return False
    try:
        return is_assembled_text(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        return False


EMBED_KINDS = ("metadata", "preamble", "lua", "bibliography", "hst")


# `csl` (v3.28.36) is not in the default either: a citation style is 10-90 KB (apa.csl is 86 KB, 2000 lines) and the global
# metadata sets one for every document; `--embed-metadata csl`, `--attach-csl` or `pdfmd-options: {embed: {csl: true}}` carry it.
# `files` (v3.25.10) is not in the default: it can be big. `--embed-metadata files` or `all` asks for it: the images, CSV
# data and included files the text and the preamble point at, as `type: file` blocks (text as it is, anything else as base64).
EMBED_OPTIONAL = ("files", "csl")


EMBED_ALL = EMBED_KINDS + EMBED_OPTIONAL


# A LaTeX comment line closing the embedded preamble inside `header-includes`:
# document_header_file puts the front-matter macro definitions there, after
# the preamble that defines them and before the document's own additions,
# the order a normal build gives them.
PREAMBLE_END_MARK = "% pdfmd: end of embedded preamble"


LUA_MODES = ("embed", "ref", "apply", "off")


EMBED_BLOCK_RE = re.compile(
    r"^(?P<fence>`{3,})\{=pdfmd\}[ \t]*\n(?P<body>.*?)\n(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL)


# What the command line asks of --embed-metadata: `kinds` None = not named
# (the document's own `pdfmd-options.embed` decides), `lua_mode` None likewise,
# `off` = --no-embed-metadata.
EmbedRequest = namedtuple("EmbedRequest", "kinds lua_mode off")


def parse_embed_option(value) -> tuple[frozenset[str], str | None] | None:
    """``pdfmd-options.embed``: ``true`` (all four kinds), ``false``, a list
    of kinds, or a mapping -- ``metadata``/``preamble`` as true/false (each on
    unless said otherwise), ``lua`` as a --lua-mode (or true = embed, false =
    off). Returns (kinds, lua mode or None), or None when it asks for nothing."""
    if value is None or value is False:
        return None
    text = str(value).strip().casefold()
    if text == "all":
        return frozenset(EMBED_ALL), None
    if value is True or text in {"true", "yes", "on"}:
        return frozenset(EMBED_KINDS), None
    if text in {"false", "no", "off", "none"}:
        return None
    if isinstance(value, list):
        return frozenset(str(item) for item in value if str(item) in EMBED_ALL), None
    if isinstance(value, dict):
        kinds = {kind for kind in ("metadata", "preamble", "bibliography", "hst")
                 if value.get(kind, True) not in (False, "false", "no", "off")}
        for optional in EMBED_OPTIONAL:
            if value.get(optional) not in (None, False, "false", "no", "off"):
                kinds.add(optional)
        lua = value.get("lua", True)
        mode = None
        if lua is False or str(lua).casefold() in {"false", "no", "off"}:
            mode = "off"
        elif isinstance(lua, str) and lua in LUA_MODES:
            mode = lua
        kinds.add("lua")
        return frozenset(kinds), mode
    return None


def resolve_embed(md_path: Path, metadata_files: list[Path],
                  request: "EmbedRequest | None") -> tuple[frozenset[str], str] | None:
    """What to embed for ``md_path`` (kinds, lua mode), or None: the command
    line first (--embed-metadata KIND.., --lua-mode, --no-embed-metadata),
    else the document's `pdfmd-options.embed` (then its metadata files',
    in order -- the first to name it wins), else the defaults (all four
    kinds, lua embedded) when --embed-metadata was given bare."""
    if request is None or request.off:
        return None
    wanted = None
    option_mode = None
    sources = [core.frontmatter_pdfmd_options(md_path)]
    for metadata_file in core.metadata_files_by_priority(metadata_files):
        found = core.metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append(found if isinstance(found, dict) else {})
    for options in sources:
        if "embed" in options:
            wanted = parse_embed_option(options["embed"])
            if wanted is not None:
                option_mode = wanted[1]
            break
    if request.kinds is not None:
        kinds = request.kinds
    elif wanted is not None:
        kinds = wanted[0]
    else:
        return None
    return kinds, request.lua_mode or option_mode or "embed"


def normalized_source(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n") + "\n"


def mask_embedded_blocks(text: str) -> str:
    """``text`` with every embedded block's characters blanked (newlines and
    length kept, so positions still line up): what the BUILD NOTES and
    marker searches look at, so a Lua filter's own text never matches them.
    """
    return EMBED_BLOCK_RE.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)


def is_crlf_text(data: bytes) -> bool:
    """Whether every line end of ``data`` is CRLF and no other CR is in it: a file a block can hold as text (with
    `eol: crlf`) and give back byte for byte."""
    plain = data.replace(b"\r\n", b"")
    return b"\r" not in plain and b"\n" not in plain and data.count(b"\r\n") > 0


LOCATION_MARK = "pdfmd-at:"


LOCATION_LINE_RE = re.compile(r"^<!-- pdfmd-at: [^\n]*-->[ \t]*\n(?:[ \t]*\n)?", re.MULTILINE)


LOCATION_INDEX_RE = re.compile(r"^<!-- pdfmd-at: index\n.*?\n-->[ \t]*\n(?:[ \t]*\n)?", re.MULTILINE | re.DOTALL)


BLOCK_TYPES = ("file", "lua-filter", "hst", "bibliography", "csl")


def strip_location_markers(text: str) -> str:
    """``text`` without the `<!-- pdfmd-at: ... -->` comments (and the one blank line each brought): the source as it was
    before they were put in. Not inside a fenced block."""
    return LOCATION_LINE_RE.sub("", LOCATION_INDEX_RE.sub("", text))


def first_block_start(text: str) -> int:
    """Where the trailing `{=pdfmd}` blocks (a file, a filter, the history, a bibliography, a style) begin in an assembled
    text: the offset of the first one of those types, len(text) when there is none."""
    for match in EMBED_BLOCK_RE.finditer(text):
        head = match.group("body").partition("\n\n")[0]
        if re.search(r"^type:[ \t]*(?:" + "|".join(BLOCK_TYPES) + r")[ \t]*$", head, re.MULTILINE):
            return match.start()
    return len(text)


def outside_folder(name: str) -> bool:
    """Whether a stored path climbs out of the document's folder (`../schemes/x.tex`)."""
    return name.split("/")[0] == ".."


def block_relative_path(name: str) -> str:
    """A path for writing a `type: file` block under a folder that is not the document's (--unpack, the build's own
    folder): the path as it is, with each `..` as `__up__` (as the attachment names do); an absolute one by its name."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or not path.parts:
        return path.name or "file"
    return "/".join("__up__" if part == ".." else part for part in path.parts)


def embedded_lines(text: str) -> dict[str, int]:
    """{path or name: the line on which its `{=pdfmd}` block opens (1-based)} for the blocks of ``text``, and `front matter`
    and `preamble` for the front matter's own parts."""
    found: dict[str, int] = {}
    front = re.match(r"^---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if front:
        found["front matter"] = 1
        header = re.search(r"^header-includes:", front.group(1), re.MULTILINE)
        if header:
            found["preamble"] = text.count("\n", 0, front.start(1)) + front.group(1).count("\n", 0, header.start()) + 1
    for match in EMBED_BLOCK_RE.finditer(text):
        head = match.group("body").partition("\n\n")[0]
        fields = {key.strip(): value.strip() for key, _, value in (line.partition(":") for line in head.splitlines())}
        if fields.get("type") in BLOCK_TYPES:
            found[fields.get("path") or fields.get("name") or fields["type"]] = text.count("\n", 0, match.start()) + 1
    return found


def reference_names(line: str, names: list[str]) -> list[str]:
    """Which of ``names`` (paths of embedded files) a line of the text points at: `file="x.csv"`, `\\input{x}`."""
    hits: list[str] = []
    for found in re.findall(r"""\bfile\s*=\s*["']([^"']+)["']""", line) + re.findall(
            r"\\(?:input|include|InputIfFileExists)\s*\{([^{}]+)\}", line):
        for name in names:
            if found == name or name in (found + ".tex", found + ".csv") or name.endswith("/" + found):
                if name not in hits:
                    hits.append(name)
    return hits


def with_location_markers(text: str) -> str:
    """``text`` with the `pdfmd-at` comments: an index after the front matter, a line before each block of the text that
    names an embedded file. Their line numbers are those of the text as returned (settled by repeating: the comments
    themselves move what is below them, though never by a different amount)."""
    clean = strip_location_markers(text)
    split = first_block_start(clean)
    body_part, blocks_part = clean[:split], clean[split:]
    front = re.match(r"^---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|$)", body_part, re.DOTALL)
    names = [name for name in embedded_lines(clean) if name not in ("front matter", "preamble")]
    if not names and not (front and "header-includes:" in front.group(0)):
        return clean
    # which block of the body points at which file, and where that block starts (a fence, a div, a paragraph)
    lines = body_part.splitlines(keepends=True)
    starts: dict[int, list[str]] = {}
    fence: tuple[str, int] | None = None
    first = body_part[:front.end()].count("\n") if front else 0
    paragraph = None
    for index in range(first, len(lines)):
        line = lines[index]
        opener = re.match(r"^(`{3,}|~{3,})", line)
        if fence is None and opener:
            fence = (opener.group(1), index)
        elif fence is not None and line.startswith(fence[0]) and line.strip() == fence[0]:
            fence = None
            continue
        if not line.strip():
            paragraph = None
        elif paragraph is None:
            paragraph = index
        if line[:1] in " \t>" or not line.strip():
            continue
        hits = reference_names(line, names)
        if hits:
            start = fence[1] if fence is not None else paragraph if paragraph is not None else index
            for name in hits:
                if name not in starts.setdefault(start, []):
                    starts[start].append(name)
    listing = ["front matter", *(["preamble"] if "preamble" in embedded_lines(clean) else []), *names]
    numbers: dict[str, int] = {}
    result = clean
    for _ in range(4):
        out = []
        for index, line in enumerate(lines):
            for name in starts.get(index, []):
                out.append(f"<!-- {LOCATION_MARK} {name} @ line {numbers.get(name, 0)} -->\n\n")
            out.append(line)
        marked = "".join(out)
        entries = "".join(f"{name:<40} line {numbers.get(name, 0)}\n" for name in listing)
        index_text = f"<!-- {LOCATION_MARK} index\n{entries}-->\n\n"
        cut = front.end() if front else 0          # the markers are all after the front matter: it is still the first characters
        result = marked[:cut] + index_text + marked[cut:] + blocks_part
        found = embedded_lines(result)
        fresh = {name: found[name] for name in listing if name in found}
        if fresh == numbers:
            break
        numbers = fresh
    return result


@contextmanager
def embedded_lua_filters(md_path: Path, allowed: bool, trust_all: bool) -> Iterator[list[Path]]:
    """Yield temp files for the Lua filters embedded in ``md_path`` (see the
    comment above EMBED_KINDS) that may run; the files are removed afterwards.
    ``allowed`` False (a CLI --no-auto lua) yields none.
    """
    if not allowed or md_path.suffix.lower() not in (".md", ".markdown"):
        yield []
        return
    try:
        blocks = [block for block in core.parse_embedded_blocks(md_path.read_text(encoding="utf-8-sig"))
                  if block["type"] == "lua-filter"]
    except (OSError, UnicodeDecodeError):
        blocks = []
    if not blocks:
        yield []
        return
    known = core.trusted_hashes()
    folder = Path(mkdtemp(prefix="pdfmd-embedded-"))
    try:
        paths: list[Path] = []
        for index, block in enumerate(blocks, 1):
            label = Path(block["name"]).name or "filter.lua"
            if not (trust_all or block["sha256"] in known):
                print(f"WARN  {core.display_path(md_path)}: the embedded Lua filter '{label}' was not run: "
                      "it was not written by this pdfmd (or was edited since), and a Lua filter can "
                      "run any command. Read it, then use --trust-embedded to run it", file=sys.stderr)
                continue
            target = folder / f"{index:02d}-{label}"
            core.write_text_lf(target, block["source"])
            paths.append(target)
            print(f"AUTO LUA  {core.display_path(md_path)}: embedded filter {label}")
        yield paths
    finally:
        shutil.rmtree(folder, ignore_errors=True)


class _EmbedDumper(yaml.SafeDumper if yaml is not None else object):
    pass


if yaml is not None:
    _EmbedDumper.add_representer(
        str, lambda dumper, value: dumper.represent_scalar(
            "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None))


def header_includes_text(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item is not None)
    return "" if value is None else str(value)
