"""Opt-in detection of GFM blocks in front-matter documents, and Hugo TOML metadata."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pdfmd_base import core
from pdfmd_obsidian.comments import _PROTECTED, _pairs
from pdfmd_tables.scan import _pipe_end


_TOML = re.compile(r"\A\+\+\+[ \t]*\n(?P<body>.*?)^\+\+\+[ \t]*(?:\n|$)", re.MULTILINE | re.DOTALL)
_ASSIGNMENT = re.compile(r"""(?m)^\s*(?:[\w.-]+|"[^"\n]+"|'[^'\n]+')\s*=\s*\S""")
_YAML_END = re.compile(r"(?m)^(?:---|\.\.\.)[ \t]*(?:\n|$)")
_BLOCK = re.compile(r"^ {0,3}(?:#{1,6}(?:[ \t]|$)|>|(?:[-+*]|[0-9]{1,9}[.)])[ \t]+\S)")
_PROSE = re.compile(_PROTECTED, re.MULTILINE | re.DOTALL)
EXTENSIONS = "+lists_without_preceding_blankline-blank_before_header-blank_before_blockquote"


def deep(path: Path, metadata_files) -> bool:
    return str(core.first_pdfmd_option(path, metadata_files, "dialect-detect")).strip().casefold() == "deep"


def toml_front_matter(text: str):
    """Return the fenced block and its metadata, or None for ordinary Markdown."""
    if not text.startswith("+++"):
        return None
    block = _TOML.match(text)
    if not block or not _ASSIGNMENT.search(block["body"]):
        return None
    try:
        import tomllib
    except ImportError:           # Python 3.9 and 3.10
        return block, None
    try:
        return block, tomllib.loads(block["body"])
    except tomllib.TOMLDecodeError:
        return None


def _gfm_body(text: str, path: Path, metadata_files):
    """Return the numbered GFM block starts and the starts that need a blank line."""
    def spaces(value):
        return re.sub(r"[^\n]", " ", value)

    visible = _PROSE.sub(lambda match: spaces(match[0]) if match.lastgroup != "code" else spaces(match[0]).replace(" ", "x", 1), text)
    if "%%" in visible:
        preset = core.FLAVOUR_PRESETS.get(core.flavour_of(path, metadata_files))
        if preset and preset.comments:
            pairs, _ = _pairs(visible, core.unclosed_comment_mode(path, metadata_files))
            for opening, closing, closed in reversed(pairs):
                end = closing + 2 if closed else closing
                visible = visible[:opening] + spaces(visible[opening:end]) + visible[end:]
    lines = visible.split("\n")
    hits, tables = [], []
    after_table = 0
    for index in range(1, len(lines)):
        line, previous = lines[index], lines[index - 1]
        if index < after_table or not line.strip() or not previous.strip():
            continue
        if _BLOCK.match(line):
            if not _BLOCK.match(previous):
                hits.append(index)
        elif not line.startswith(("    ", "\t")):
            end = _pipe_end(lines, index)
            if end:
                hits.append(index)
                tables.append(index)
                after_table = end
    return hits, tables


def _body_start(text: str, toml) -> int:
    if toml:
        return toml[0].end()
    if core.has_yaml_frontmatter(text):
        delimiters = _YAML_END.finditer(text)
        next(delimiters, None)
        closing = next(delimiters, None)
        if closing:
            return closing.end()
    return 0


def reader(text: str, path: Path, metadata_files, toml) -> tuple[str | None, str]:
    start = _body_start(text, toml)
    if not deep(path, metadata_files):
        return None, f"{path}: YAML front matter; using Pandoc's Markdown (dialect-detect: deep checks the body)"
    hits, _ = _gfm_body(text[start:], path, metadata_files)
    if hits:
        offset = text.count("\n", 0, start) + 1
        lines = ", ".join(str(index + offset) for index in hits)
        return "markdown" + EXTENSIONS, f"{path}: GFM-style blocks after front matter at lines {lines}; using relaxed Markdown"
    return None, f"{path}: front matter; using Pandoc's Markdown"


def prepare(text: str, path: Path, metadata_files, relax: bool = False) -> str:
    """Prepare the copy Pandoc reads. Tables still require a blank line with the relaxed reader."""
    toml = toml_front_matter(text)
    if toml is None and not relax:
        return text
    start = _body_start(text, toml)
    front, body = text[:start], text[start:]
    if toml:
        if not deep(path, metadata_files):
            print(f"WARN  {core.display_path(path)}: TOML front matter is read as text; set dialect-detect: deep to use it",
                  file=sys.stderr)
            return text
        metadata = toml[1]
        if metadata is None:
            print(f"NOTE  {core.display_path(path)}: TOML front matter needs Python 3.11; the block was dropped",
                  file=sys.stderr)
            front = ""
        else:
            front = "---\n" + core.yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + "---\n\n"
    if relax and deep(path, metadata_files):
        lines = body.split("\n")
        _, tables = _gfm_body(body, path, metadata_files)
        for index in reversed(tables):
            lines.insert(index, "")
        body = "\n".join(lines)
    return front + body
