"""Resolve Obsidian notes into ordinary Pandoc links before the writer runs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote

from pdfmd_base import core
from pdfmd_base import pandoc_run
from pdfmd_log import emit
from pdfmd_obsidian.properties import syntax_matches, write_syntax
from pdfmd_obsidian.wikilinks import wikilinks_as_text


_SUFFIXES = (".md", ".markdown")


def _inline_text(nodes):
    words = []
    for node in nodes:
        kind, content = node["t"], node.get("c")
        if kind == "Str":
            words.append(content)
        elif kind in ("Space", "SoftBreak", "LineBreak"):
            words.append(" ")
        elif kind in ("Code", "Math"):
            words.append(content[-1])
        elif kind in ("Link", "Image", "Span", "Quoted"):
            words.append(_inline_text(content[1]))
        elif isinstance(content, list) and all(isinstance(item, dict) for item in content):
            words.append(_inline_text(content))
    return "".join(words)


def _ast_nodes(document):
    if isinstance(document, list):
        for item in document:
            yield from _ast_nodes(item)
    elif isinstance(document, dict):
        yield document
        yield from _ast_nodes(document.get("c"))


def _read_headings(texts, reader):
    """Use the same reader and order as the build, including duplicate and explicit identifiers."""
    pandoc = core.which("pandoc")
    headings = [{} for _ in texts]
    if not pandoc:
        return headings
    marker = "pdfmdwikilinksourcebreak"
    while any(marker in text for text in texts):
        marker += "x"
    marked = []
    for index, text in enumerate(texts):
        marked.append((f"{marker}{index}\n\n" if index else "") + wikilinks_as_text(text).text)
    try:
        result = pandoc_run([pandoc, "-f", reader or "markdown", "-t", "json"],
                            input="\n\n".join(marked), capture_output=True, encoding="utf-8", timeout=120)
        if result.returncode:
            return headings
        blocks = json.loads(result.stdout)["blocks"]
    except (OSError, ValueError, subprocess.SubprocessError):
        return headings
    current = headings[0]
    for node in _ast_nodes(blocks):
        if node["t"] == "Para":
            text = _inline_text(node["c"])
            if text.startswith(marker) and text[len(marker):].isdigit():
                current = headings[int(text[len(marker):])]
        if node["t"] == "Header":
            _, (identifier, _, _), inlines = node["c"]
            if identifier:
                current.setdefault(_inline_text(inlines).casefold(), identifier)
                current.setdefault(identifier.casefold(), identifier)
    return headings


def _block_syntax(texts, matches, headings):
    """Allocate one document-wide anchor per block and retain each note's local names."""
    used = {identifier for names in headings for identifier in names.values()}
    names = []
    converted = []
    for text, local_matches in zip(texts, matches):
        local, offsets = {}, {}
        for match in local_matches:
            if match.lastgroup != "block":
                continue
            name = match.group("identifier")
            identifier = name
            suffix = 1
            while identifier in used:
                identifier = f"{name}-{suffix}"
                suffix += 1
            used.add(identifier)
            local.setdefault(name, identifier)
            offsets[match.start()] = identifier
        names.append(local)
        converted.append(write_syntax(text, local_matches, offsets))
    return converted, names


def _span_reader(reader):
    reader = reader or "markdown"
    base = re.split(r"[+-]", reader, maxsplit=1)[0]
    if base in ("gfm", "commonmark", "commonmark_x"):
        for extension in ("+attributes", "+bracketed_spans"):
            if extension not in reader:
                reader += extension
    return reader


class Links:
    def __init__(self, sources, texts, reader, target, output, title_auto):
        self.sources = [path.resolve() for path in sources]
        self.texts = texts
        self.reader = reader
        self.target = target
        self.output = output
        self.title_auto = title_auto
        self.anchors = {}
        self.told = set()
        self.headings = None
        self.blocks = None
        self.external = {}
        self.indexes = {}

    def find(self, path, name):
        note = Path(name)
        if note.is_absolute() or note.drive:
            return None, False
        names = (note,) if note.suffix.casefold() in _SUFFIXES else tuple(note.with_name(note.name + s) for s in _SUFFIXES)
        vault = core.vault_root(path)
        for folder in dict.fromkeys((path.parent, self.sources[0].parent, vault)):
            if folder is None:
                continue
            for candidate in names:
                found = folder / candidate
                if found.is_file():
                    return found.resolve(), False
        if len(note.parts) > 1:
            return None, False
        folder = vault or self.sources[0].parent
        if folder not in self.indexes:
            index = {}
            for root, directories, files in os.walk(folder):
                directories[:] = [directory for directory in directories if not directory.startswith(".")]
                for file in files:
                    if Path(file).suffix.casefold() in _SUFFIXES:
                        index.setdefault(file.casefold(), set()).add((Path(root) / file).resolve())
            self.indexes[folder] = index
        matches = set().union(*(self.indexes[folder].get(candidate.name.casefold(), set()) for candidate in names))
        matches.update(source for source in self.sources if source.name.casefold() in {n.name.casefold() for n in names})
        return (matches.pop(), False) if len(matches) == 1 else (None, bool(matches))

    def identifier(self, note, heading):
        is_block = heading.startswith("^")
        key = heading[1:] if is_block else heading.casefold()
        if note in self.sources:
            index = self.sources.index(note)
            if is_block:
                return self.blocks[index].get(key)
            if self.headings is None:
                self.headings = _read_headings(self.texts, self.reader)
            return self.headings[index].get(key)
        if note not in self.external:
            try:
                raw = note.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                return None
            from pdfmd_reader.controls import repair_controls
            metadata = core.scaffold_metadata_files(note, None)
            text = core.obsidian_source(repair_controls(raw), note, metadata, show=False)
            if self.title_auto:
                text, _ = core.promote_bare_title(text, bool(metadata))
            reader, _ = core.resolve_from_format(note, None, metadata)
            headings = _read_headings([text], reader)
            _, blocks = _block_syntax([text], [list(syntax_matches(text))], headings)
            self.external[note] = headings[0], blocks[0]
        return self.external[note][int(is_block)].get(key)

    def destination(self, path, name, heading):
        if name:
            note, ambiguous = self.find(path, name)
            if not note:
                if not ambiguous and name.casefold() not in self.told:
                    self.told.add(name.casefold())
                    emit("warning", None, f"WARN  {core.display_path(path)}: wikilink note not found: {name}", file=sys.stderr)
                return None
        else:
            note = path
        if heading:
            identifier = self.identifier(note, heading)
            if not identifier:
                return None
            fragment = "#" + identifier
        else:
            fragment = ""
        if note not in self.sources:
            built = note.with_suffix(core.output_extension_for(self.target, note))
            try:
                relative = Path(os.path.relpath(built, self.output.resolve().parent)).as_posix()
            except ValueError:                 # another drive on Windows
                return built.as_uri() + quote(fragment, safe="#")
            return quote(relative) + quote(fragment, safe="#")
        if fragment:
            return fragment
        if note not in self.anchors:
            identifier = f"pdfmd-wikilink-note-{self.sources.index(note) + 1}"
            while any(identifier in text for text in self.texts):
                identifier += "x"
            self.anchors[note] = identifier
        return "#" + self.anchors[note]


@contextmanager
def linked_inputs(inputs, sources, reader, metadata_files, target, output, title_auto=True):
    """Convert only the Obsidian inputs and keep their copies beside their original paths."""
    first_obsidian = core.flavour_of(sources[0], metadata_files) == "obsidian"
    active = [path.suffix.lower() in core.MARKDOWN_LIKE_SUFFIXES
              and (core.flavour_of(path, metadata_files) == "obsidian" or
                   (first_obsidian and core.first_pdfmd_option(path, metadata_files, "flavour", "flavor", "reader") is None))
              for path in sources]
    if not any(active):
        yield inputs, reader
        return
    wikilinks = [enabled and core.effective_preset(path, metadata_files).wikilinks
                 for enabled, path in zip(active, sources)]
    texts = [path.read_text(encoding="utf-8-sig") for path in inputs]
    kinds = core.markup_kinds(sources[0], metadata_files)
    from pdfmd_obsidian.markup import callouts_and_tasks
    try:
        from pdfmd_lua import path as lua_path
    except ImportError:
        lua_path = None
    fold = target in ("html", "html4", "html5") and "callouts" in kinds
    styled = [callouts_and_tasks(text, fold) if enabled else text for enabled, text in zip(active, texts)] \
        if kinds and lua_path and lua_path("markup") else texts
    matches = [list(syntax_matches(text)) if enabled and ("#" in text or "^" in text) else []
               for enabled, text in zip(active, styled)]
    if styled == texts and not any(matches) and not any(enabled and "[[" in text for enabled, text in zip(wikilinks, texts)):
        yield inputs, reader
        return
    links = Links(sources, texts, reader, target, output, title_auto)
    if any(match.lastgroup == "block" for local in matches for match in local):
        links.headings = _read_headings(texts, reader)
    marked, links.blocks = _block_syntax(styled, matches, links.headings or [])
    converted = []
    for enabled, path, text in zip(wikilinks, links.sources, marked):
        def destination(name, heading):
            return links.destination(path, name, heading)

        converted.append(wikilinks_as_text(text, destination).text if enabled else text)
    if links.anchors or any(matches) or styled != texts:
        reader = _span_reader(reader)
    with ExitStack() as stack:
        prepared = []
        for index, (path, original, changed) in enumerate(zip(inputs, texts, converted)):
            if identifier := links.anchors.get(links.sources[index]):
                front = core.LEADING_FRONT_MATTER_RE.match(changed)
                offset = front.end() if front else 0
                changed = changed[:offset] + f"\n\n[]{{#{identifier}}}\n\n" + changed[offset:]
            if changed == original:
                prepared.append(path)
                continue
            copy = NamedTemporaryFile("w", encoding="utf-8", suffix=path.suffix, prefix=".pdfmd-wikilinks-",
                                      dir=path.parent, delete=False)
            prepared.append(Path(copy.name))
            stack.callback(prepared[-1].unlink, missing_ok=True)
            with copy:
                copy.write(changed)
        yield prepared, reader
