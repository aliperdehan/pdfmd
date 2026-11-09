"""The text of a build put together, and what `--embed-metadata` folds into it: the assembled text itself
(`assemble_markdown_text`, `write_assembled_markdown`, `mark_assembled`), the bibliography it carries cut down to the entries it
cites (`used_citation_keys`, `filter_bibliography`), the plan and the folding (`EmbedPlan`, `embed_into_text`,
`strip_embedded_option_names`, `literal_block`, and `apply_lua_filters` with `relative_filter_path` and `lua_checks_format`), the
`{=pdfmd}` blocks it holds (`render_embedded_block`, `render_embedded_file`, `parse_embedded_blocks`, `safe_relative_path`), the
trust store of embedded Lua filters (`trust_store_path`, `trusted_hashes`, `remember_trusted`), the bibliography, citation style
and files a build of such a file writes out for itself (`embedded_resources`), and an assembled file unpacked again
(`unpack_assembled`, `slim_assembled`, `split_preamble_parts`).

Moved out of `pdfmd.py` unchanged (v3.33.38, SPLIT.md), with the constants only this code reads (`PARTIAL_KEY`,
`ASSEMBLED_COMMENT`, `BIB_LINK_RE`, `BIB_SUFFIXES`, `PANDOC_CITE_RE`, `LATEX_CITE_RE` and `FILE_ONLY_OPTION_KEYS`) and the comment
on the trust store. `core` is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first binding wins); the pdfmd names the
code uses are read as `core.X` when it runs: `ACCESSORY_DIRNAME`, `ASSEMBLED_COMMENT_RE`, `ASSEMBLED_KEY`, `ASSEMBLED_SUFFIX`,
`BUNDLE_MAX_MB`, `COMMENT_KINDS`, `EMBEDDED_RESOURCE_DIRS`, `EMBED_BLOCK_RE`, `EMBED_KINDS`, `METADATA_APPEND_KEY`,
`PREAMBLE_END_MARK`, `UNPACKED_SUFFIX`, `VERBOSE_OUTPUT`, `_EmbedDumper`, `_RESOURCE_OWNER`, `add_calc_constants`,
`atomic_write_bytes`, `block_relative_path`, `bundle_files`, `cache_root`, `config_root`, `display_path`, `drop_calc_export`,
`first_pdfmd_option`, `header_includes_text`, `is_assembled_text`, `is_crlf_text`, `is_global_metadata`, `merge_metadata_layers`,
`merge_option_dicts`, `metadata_append_keys`, `metadata_file_yaml`, `metadata_files_by_priority`, `metadata_plus_key`,
`migrate_state`, `normalized_source`, `option_flag_number`, `outside_folder`, `pandoc_metadata_order`, `pandoc_user_data_dir`,
`parse_bibliography`, `promote_bare_title`, `relative_posix`, `resolve_from_format`, `sha256_text`, `strip_location_markers`,
`strip_markdown_comments`, `strip_part_front_matter`, `strip_tex_comments`, `strip_xml_comments`, `write_text_lf` and `yaml`.
`VERBOSE_OUTPUT` stays in `pdfmd.py`, rebound with `global` in `main`; `cache_root`, `config_root` and `pandoc_user_data_dir` are
patched by tests as `pdfmd.X`; `bundle_files`, `cache_root` and the three `strip_*_comments` are `pdfmd_attach`'s, `pdfmd_cache`'s
and `pdfmd_comments`'s, read through pdfmd as before, and `yaml` is pdfmd's own optional import. `_RESOURCE_OWNER` (the document
whose build holds the resources, so a nested call for it is a no-op) stays in `pdfmd.py` as state: `embedded_resources` reads and
writes it as `core._RESOURCE_OWNER` where it had `global _RESOURCE_OWNER`. `write_assembled_markdown` was decorated with `pdfmd`'s
`@timed`, which is defined far below the place where the package loads: `_timed` is the same decorator looked up at call time
(`core.timed(name)(function)`). The comment above `EMBED_KINDS` that `embed_into_text`'s docstring points at stays in `pdfmd.py`
with `EMBED_KINDS`.
"""

from __future__ import annotations

import base64
import binascii
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from tempfile import mkdtemp

core = None


def _timed(name):
    """`core.timed(name)` for a function defined before `core.timed` exists: each call is wrapped when it is made."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            return core.timed(name)(function)(*args, **kwargs)
        return wrapper
    return decorate


PARTIAL_KEY = "pdfmd-partial"
ASSEMBLED_COMMENT = "<!-- pdfmd-assembled: true -->"


def mark_assembled(text: str, no_auto: list[str] | None = None, partial: bool = False) -> str:
    """Mark ``text`` as assembled: ASSEMBLED_KEY in its front matter if it
    has a block, else an HTML comment at the end. Never a NEW front-matter
    block: that would change how the document reads -- Pandoc's own `% title`
    block stops being one behind it, and a leading `# Title` heading is only
    promoted to the title (promote_bare_title) in a document with no front
    matter at all.
    """
    if re.match(r"^---[ \t]*\n", text):
        # A partial build (`report#methods`) tells Pandoc `-M pdfmd-partial=true`
        # on the command line; the assembled file has to carry it itself.
        marks = f"{core.ASSEMBLED_KEY}: true\n" + (f"{PARTIAL_KEY}: true\n" if partial else "")
        return re.sub(r"^---[ \t]*\n", f"---\n{marks}", text, count=1)
    if partial:
        print(f"WARN  a partial build with no front matter cannot record {PARTIAL_KEY}; a filter "
              "that reads it will not see it when the assembled file is built", file=sys.stderr)
    comment = (ASSEMBLED_COMMENT if not no_auto else
               f"<!-- pdfmd-assembled: true; no-auto: {','.join(no_auto)} -->")
    return text.rstrip("\n") + f"\n\n{comment}\n"


BIB_LINK_RE = re.compile(r"\b(?:crossref|xref|xdata|related)\s*=\s*[{\"]?([^}\",]*(?:,[^}\",]*)*)", re.IGNORECASE)
BIB_SUFFIXES = (".bib", ".bibtex", ".biblatex")
PANDOC_CITE_RE = re.compile(r"(?<![\w@])@(?:\{([^}]+)\}|([A-Za-z0-9_](?:[\w:.#$%&+?<>~/-]*[\w])?))")
LATEX_CITE_RE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\]){0,2}\{([^}]*)\}")


def used_citation_keys(texts: list[str]) -> set[str] | None:
    """The citation keys the texts (the document, its metadata, the preamble) use, lower-cased,
    or None when everything is wanted (`nocite: '@*'`, `\\nocite{*}`)."""
    keys: set[str] = set()
    for text in texts:
        if "@*" in text or re.search(r"\\nocite\{\s*\*\s*\}", text):
            return None
        for match in PANDOC_CITE_RE.finditer(text):
            keys.add((match.group(1) or match.group(2)).strip().lower())
        for match in LATEX_CITE_RE.finditer(text):
            keys.update(item.strip().lower() for item in match.group(1).split(",") if item.strip())
    return keys


def filter_bibliography(text: str, used: set[str] | None, strip_comments: bool) -> tuple[str, int, int]:
    """A BibTeX file reduced to the entries ``used`` names (and what they cross-reference;
    None keeps every entry), without the text between entries if ``strip_comments``.
    Returns (text, entries kept, entries in the file). `@string` and `@preamble` always stay."""
    items, tail = core.parse_bibliography(text)
    entries = [item for item in items if item["key"]]
    keep: set[str] | None = None
    if used is not None:
        by_key: dict[str, list[dict]] = {}
        for item in entries:
            by_key.setdefault(item["key"].lower(), []).append(item)
        keep = set()
        queue = [key for key in used if key in by_key]
        while queue:
            key = queue.pop()
            if key in keep:
                continue
            keep.add(key)
            for item in by_key[key]:
                for match in BIB_LINK_RE.finditer(item["text"]):
                    queue.extend(name.strip().lower() for name in match.group(1).split(",")
                                 if name.strip().lower() in by_key)
    pieces: list[str] = []
    kept = 0
    for item in items:
        if item["key"]:
            if keep is not None and item["key"].lower() not in keep:
                continue
            kept += 1
        elif item["kind"] == "comment" and strip_comments:
            continue
        pieces.append(item["text"] if strip_comments else item["gap"] + item["text"])
    if strip_comments:
        result = "\n\n".join(pieces) + "\n" if pieces else ""
    else:
        result = "".join(pieces) + tail
    return result, kept, len(entries)


def assemble_markdown_text(sources: list[Path], drop_later_front_matter: bool,
                           plan: "EmbedPlan | None" = None, partial: bool = False,
                           strip_comments: "bool | frozenset[str]" = False) -> str:
    """The Markdown Pandoc is given for ``sources``, as ONE text: the first
    file as it is, every later one after it. In parts mode a part's own
    leading front matter is dropped first, exactly as scaffold_inputs() does
    before Pandoc sees it; a report/book chapter keeps its own, since there
    Pandoc reads it too. ``strip_comments`` is True (the Markdown's comments
    go), or the set of comment kinds that do (see COMMENT_KINDS).
    """
    kinds = (frozenset(core.COMMENT_KINDS) if strip_comments is True else
             frozenset() if not strip_comments else frozenset(strip_comments))
    if plan is not None:
        plan.strip_kinds = kinds
        plan.sources = list(sources)
    chunks = []
    for index, source in enumerate(sources):
        text = core.strip_location_markers(source.read_text(encoding="utf-8-sig"))
        if index and drop_later_front_matter:
            text = core.strip_part_front_matter(text)
        if "markdown" in kinds:
            text = core.strip_markdown_comments(text)
        chunks.append(text.rstrip("\n") + "\n")
    joined = "\n".join(chunks)
    if plan is not None:
        return embed_into_text(joined, sources[0], plan, partial)
    return mark_assembled(joined, partial=partial)


@_timed("assemble text")
def write_assembled_markdown(sources: list[Path], output: Path,
                             drop_later_front_matter: bool,
                             plan: "EmbedPlan | None" = None,
                             partial: bool = False,
                             strip_comments: "bool | frozenset[str]" = False) -> tuple[bool, str]:
    """Write the --stop-at markdown stage. Never over one of its own sources:
    `-o report.md` would otherwise replace the very file it was built from.
    """
    resolved = {source.resolve() for source in sources}
    if output.resolve() in resolved:
        return False, (f"{core.display_path(output)} is one of the files being assembled; "
                       f"pick another name (the default is NAME{core.ASSEMBLED_SUFFIX})")
    output.parent.mkdir(parents=True, exist_ok=True)
    if plan is not None:
        plan.output = output
    text = assemble_markdown_text(sources, drop_later_front_matter, plan, partial, strip_comments)
    core.write_text_lf(output, text)
    print(f"ASSEMBLED  {core.display_path(output)}  ({len(sources)} file{'s' if len(sources) != 1 else ''}, "
          f"{len(text.splitlines())} lines)")
    return True, ""


# Not folded from a metadata file into an assembled document's pdfmd-options (--embed-metadata metadata): an assembled
# file already holds its parts and records its own no-auto kinds. A normal build reads `parts` from the document, its
# metadata files and the config (parts_setting), `no-auto` from the command line, the document and the config
# (effective_no_auto).
FILE_ONLY_OPTION_KEYS = frozenset({"no-auto", "parts"})


class EmbedPlan:
    """What --embed-metadata folds into one assembled file."""

    def __init__(self, kinds: frozenset[str], lua_mode: str, metadata_files: list[Path],
                 preamble_files: list[Path], lua_filters: list[Path]):
        self.kinds = kinds
        self.lua_mode = lua_mode
        self.metadata_files = metadata_files
        self.preamble_files = preamble_files
        self.lua_filters = lua_filters
        self.output: Path | None = None
        self.hst_file: Path | None = None                 # the document's NAME.hst, when it has one
        self.sources: list[Path] = []                     # the files assembled (the `files` kind looks for what they point at)
        self.strip_kinds: frozenset[str] = frozenset()    # comment kinds cut from what is embedded
        self.bib_prune = False                            # keep only the bibliography entries the text cites
        self.bib_report: list[str] = []                   # "name (kept of total)" for the summary
        self.csl_left: list[str] = []                     # styles the metadata names that were not embedded (the `csl` kind is off)
        self.kit_none = False                             # a chosen kit's every part is embedded: the source says `kit: none`


def render_embedded_block(kind: str, name: str, source: str, path: str | None = None) -> str:
    """One embedded file as a fenced `{=pdfmd}` block. ``path`` (bibliography
    and CSL files) is the name the document's metadata gives the file, which
    is where it is written back to when the block is extracted."""
    source = core.normalized_source(source)
    longest = max((len(run) for run in re.findall(r"`+", source)), default=0)
    fence = "`" * max(3, longest + 1)
    name = re.sub(r"[\r\n]", " ", name)
    clean_path = re.sub(r"[\r\n]", " ", path) if path else ""
    where = f"path: {clean_path}\n" if path else ""
    return (f"{fence}{{=pdfmd}}\ntype: {kind}\nname: {name}\n{where}sha256: {core.sha256_text(source)}\n\n"
            f"{source.rstrip(chr(10))}\n{fence}\n")


def render_embedded_file(name: str, path: str, data: bytes) -> str:
    """One referenced file as a `type: file` block: text as it is, anything else base64 (76 columns). ``path`` is where
    the document names it, which is where it is written back to."""
    try:
        text = data.decode("utf-8")
        printable = "\x00" not in text and "```" not in text
    except UnicodeDecodeError:
        text, printable = "", False
    name = re.sub(r"[\r\n]", " ", name)
    clean_path = re.sub(r"[\r\n]", " ", path)
    digest = hashlib.sha256(data).hexdigest()
    windows = printable and "\r\n" in text and core.is_crlf_text(data)          # Windows line ends: text, with `eol: crlf`
    if windows:
        text = text.replace("\r\n", "\n")
    if printable and (not text or text.endswith("\n")) and "\r" not in text:
        return (f"```{{=pdfmd}}\ntype: file\nname: {name}\npath: {clean_path}\n{'eol: crlf' + chr(10) if windows else ''}"
                f"sha256: {digest}\n\n{text.rstrip(chr(10))}\n```\n")
    encoded = base64.b64encode(data).decode("ascii")
    wrapped = "\n".join(encoded[index:index + 76] for index in range(0, len(encoded), 76))
    return (f"```{{=pdfmd}}\ntype: file\nname: {name}\npath: {clean_path}\nencoding: base64\nsha256: {digest}\n\n"
            f"{wrapped}\n```\n")


def safe_relative_path(name: str) -> str:
    """A relative path for writing an embedded file back: as the metadata
    names it, unless that is absolute or climbs out (then just the file name)."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return path.name or "file"
    return str(path)


def parse_embedded_blocks(text: str) -> list[dict]:
    blocks = []
    for match in core.EMBED_BLOCK_RE.finditer(text):
        head, separator, rest = match.group("body").partition("\n\n")
        if not separator:
            continue
        fields = {}
        also: list[str] = []
        for line in head.splitlines():
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
            if key.strip() == "also" and value.strip():
                also.append(value.strip())
        source = rest + "\n"
        data = None
        digest = core.sha256_text(source)
        if fields.get("encoding") == "base64":
            try:
                data = base64.b64decode("".join(rest.split()))
                digest = hashlib.sha256(data).hexdigest()
                source = ""
            except (ValueError, binascii.Error):
                data = b""
        elif fields.get("type") == "file":
            data = source.rstrip("\n").encode("utf-8") + (b"\n" if rest.strip() else b"")
            if fields.get("eol") == "crlf":
                data = data.replace(b"\n", b"\r\n")
            digest = hashlib.sha256(data).hexdigest()
        blocks.append({"type": fields.get("type", ""), "name": fields.get("name") or "filter.lua",
                       "path": fields.get("path"), "also": also,
                       "declared": fields.get("sha256"), "source": source, "bytes": data,
                       "sha256": digest})
    return blocks


# What this machine's pdfmd has itself written: the SHA-256 of each embedded
# filter, one per line. A block whose own text hashes to one of these is the
# text pdfmd wrote here (not edited since, not from another machine), so it is
# run; any other embedded filter is code from elsewhere -- a Lua filter can
# run any command -- and is skipped, with a warning, unless --trust-embedded.
def trust_store_path() -> Path:
    path = core.config_root() / "trusted-filters.txt"
    core.migrate_state(core.cache_root() / "embedded-trust.txt", path)  # v3.23.5 and before kept it in the cache
    return path


def trusted_hashes() -> set[str]:
    try:
        return {line.split()[0] for line in
                trust_store_path().read_text(encoding="utf-8").splitlines() if line.strip()}
    except OSError:
        return set()


def remember_trusted(entries: list[tuple[str, str]]) -> None:
    known = trusted_hashes()
    fresh = [(digest, name) for digest, name in entries if digest not in known]
    if not fresh:
        return
    try:
        trust_store_path().parent.mkdir(parents=True, exist_ok=True)
        with trust_store_path().open("a", encoding="utf-8") as handle:
            for digest, name in fresh:
                handle.write(f"{digest} {name}\n")
    except OSError:
        pass


def split_preamble_parts(preamble_text: str, record: list) -> list[tuple[str, str]] | None:
    """Cut the embedded preamble back into the files it was made from, by the
    line counts recorded in `origin.preamble`; None if the text no longer
    matches their hashes (it was edited), so the caller keeps it whole."""
    lines = preamble_text.strip("\n").split("\n")
    pieces = []
    for item in record:
        count = item.get("lines") if isinstance(item, dict) else None
        if not isinstance(count, int) or count > len(lines):
            return None
        part = "\n".join(lines[:count])
        lines = lines[count:]
        if core.sha256_text(part) != item.get("sha256"):
            return None
        pieces.append((str(item.get("name") or "preamble.tex"), part + "\n"))
    return pieces if not any(line.strip() for line in lines) else None


def unpack_assembled(path: Path, out_dir: Path | None, slim: bool = False) -> int:
    """--unpack: write what an assembled file embeds back out as files, and
    check each embedded filter's hash. Never overwrites. With ``slim`` it
    then rewrites the file itself without what was unpacked -- the original
    layout, a lean document plus its ``NAME.unpacked/`` folder, which pdfmd
    discovers again (see accessory_directories). Returns the exit status: 1
    if a filter does not match its recorded hash (edited since pdfmd wrote
    it) or nothing could be unpacked."""
    text = path.read_text(encoding="utf-8-sig")
    if not core.is_assembled_text(text):
        raise SystemExit(f"{core.display_path(path)} is not an assembled file (no {core.ASSEMBLED_KEY} marker)")
    default_target = path.with_name(f"{path.stem}{core.UNPACKED_SUFFIX}")
    target = out_dir or default_target
    files: dict[str, str | bytes] = {}
    notes: list[str] = []
    mismatch = False
    known = trusted_hashes()
    taken: set[str] = set()

    def unique(name: str) -> str:
        candidate, number = name, 1
        while candidate in taken:
            number += 1
            original = PurePosixPath(name)
            candidate = str(original.with_name(f"{original.stem}-{number}{original.suffix}"))
        taken.add(candidate)
        return candidate

    all_blocks = parse_embedded_blocks(text)
    blocks = [block for block in all_blocks if block["type"] == "lua-filter"]
    data_blocks = [block for block in all_blocks if block["type"] in ("bibliography", "csl")]
    history_blocks = [block for block in all_blocks if block["type"] == "hst"]
    file_blocks = [block for block in all_blocks if block["type"] == "file"]
    for block in file_blocks:
        if block["declared"] == block["sha256"]:
            state = "hash matches what was written"
        else:
            mismatch = True
            state = "HASH MISMATCH: edited since it was written" if block["declared"] else "no hash recorded"
        for place in [block["path"] or block["name"], *block.get("also", [])]:
            name = unique(core.block_relative_path(place))
            files[name] = block["bytes"] if block.get("bytes") is not None else block["source"]
            notes.append(f"FILE      {name}  ({state})")
    for block in history_blocks:
        name = unique(Path(block["name"]).name or f"{path.stem}.hst")
        files[name] = block["source"]
        if block["declared"] == block["sha256"]:
            state = "hash matches what was written"
        else:
            mismatch = True
            state = "HASH MISMATCH: edited since it was written" if block["declared"] else "no hash recorded"
        notes.append(f"HISTORY   {name}  ({state})")
    for block in data_blocks:
        name = unique(safe_relative_path(block["path"] or block["name"]))
        files[name] = block["source"]
        if block["declared"] == block["sha256"]:
            state = "hash matches what was written"
        else:
            mismatch = True
            state = "HASH MISMATCH: edited since it was written" if block["declared"] else "no hash recorded"
        label = "CSL" if block["type"] == "csl" else "BIBLIO"
        notes.append(f"{label:<10}{name}  ({state})")
    for block in blocks:
        name = unique(Path(block["name"]).name or "filter.lua")
        files[name] = block["source"]
        if block["declared"] == block["sha256"]:
            state = "hash matches what was written"
        else:
            mismatch = True
            state = ("HASH MISMATCH: edited since it was written" if block["declared"]
                     else "no hash recorded")
        trust = ("known to this machine's pdfmd" if block["sha256"] in known
                 else "NOT known to this machine's pdfmd (needs --trust-embedded to run)")
        notes.append(f"LUA       {name}  ({state}; {trust})")
    front = re.match(r"^---[ \t]*\n(?P<yaml>.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    data: dict | None = None
    options: dict = {}
    embedded: list = []
    origin = None
    global_keys: list | None = None
    kept_header = ""
    preamble_unpacked = metadata_unpacked = False
    if front and core.yaml is not None:
        try:
            loaded = core.yaml.safe_load(front.group("yaml"))
        except core.yaml.YAMLError:
            loaded = None
        if isinstance(loaded, dict):
            data = loaded
    if data is not None:
        data.pop(core.ASSEMBLED_KEY, None)
        header = core.header_includes_text(data.get("header-includes"))
        raw_options = data.get("pdfmd-options")
        options = raw_options if isinstance(raw_options, dict) else {}
        embedded = options.get("embedded") or []
        origin = options.get("origin") if isinstance(options.get("origin"), dict) else None
        preamble_text, marker, own_header = header.partition(core.PREAMBLE_END_MARK)
        kept_header = own_header.strip("\n") if marker else header
        if marker and preamble_text.strip():
            pieces = split_preamble_parts(preamble_text, (origin or {}).get("preamble") or [])
            if pieces is None:
                pieces = [("preamble.tex", preamble_text.strip("\n") + "\n")]
                detail = "kept whole: no usable record of the files it was made from"
            else:
                detail = "the part of header-includes before the preamble marker"
            for name, part in pieces:
                files[unique(name)] = part
                notes.append(f"PREAMBLE  {name}  ({detail})")
            preamble_unpacked = True
        if "metadata" in embedded:
            if origin and isinstance(origin.get("files"), dict) and origin["files"]:
                # pdfmd's global metadata (pdfmd --setup) is the building machine's: a build of the
                # unpacked document gets this machine's own, as every document does (v3.28.13)
                labels = [label for label in origin["files"] if label != origin.get("global")]
                if origin.get("global") in origin["files"]:
                    global_keys = origin["files"][origin["global"]]
                    notes.append(f"GLOBAL    {', '.join(global_keys) or 'nothing'}: from pdfmd's global metadata "
                                 "(pdfmd --setup), not written out; a build uses this machine's own")
                for index, label in enumerate(labels, 1):
                    piece: dict = {}
                    sub_options: dict = {}
                    for key in origin["files"][label]:
                        if key.startswith("pdfmd-options."):
                            sub = key.split(".", 1)[1]
                            if sub in options:
                                sub_options[sub] = options[sub]
                        elif key == "header-includes":
                            if kept_header:
                                piece[key] = kept_header
                        elif key in data:
                            piece[key] = data[key]
                    if sub_options:
                        piece["pdfmd-options"] = sub_options
                    name = unique(f"{index:02d}-{label}" if len(labels) > 1 else label)
                    files[name] = core.yaml.dump(piece, Dumper=core._EmbedDumper, sort_keys=False,
                                            allow_unicode=True, default_flow_style=False, width=10**6)
                    notes.append(f"METADATA  {name}  (the keys that came from {label})")
            else:
                rest = {key: value for key, value in data.items()
                        if key not in ("header-includes", "pdfmd-options", PARTIAL_KEY)}
                files[unique("metadata.yaml")] = core.yaml.dump(
                    rest, Dumper=core._EmbedDumper, sort_keys=False, allow_unicode=True,
                    default_flow_style=False, width=10**6)
                notes.append("METADATA  metadata.yaml  (the merged front matter: this file records no "
                             "origin of its keys, so it can't be told from the document's own)")
            metadata_unpacked = bool(origin and origin.get("files"))
    if not files and not global_keys:
        print(f"NOTHING   {core.display_path(path)} embeds nothing to unpack")
        return 1
    def same_on_disk(name: str) -> bool:
        try:
            if isinstance(files[name], bytes):
                return (target / name).read_bytes() == files[name]
            return (target / name).read_text(encoding="utf-8") == files[name]
        except (OSError, UnicodeDecodeError):
            return False

    # A file that is already there with exactly this content is not in the way
    # (so `--unpack` followed by `--unpack --slim` works); a different one is.
    clashes = [name for name in files if (target / name).exists() and not same_on_disk(name)]
    if clashes:
        raise SystemExit(f"{core.display_path(target)} already holds {', '.join(clashes)}, different from "
                         "what the file embeds; nothing was written (remove them, or give another -o folder)")
    if files:
        target.mkdir(parents=True, exist_ok=True)
    fresh = [name for name in files if not (target / name).exists()]
    for name in fresh:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        if isinstance(files[name], bytes):
            core.atomic_write_bytes(target / name, files[name])
        else:
            core.write_text_lf((target / name), files[name])
    # Each file on its own line with --verbose; otherwise counted by kind, and only what needs a look
    # (an edited file, a filter this machine does not know, the global metadata) in full (v3.28.15)
    kinds: dict[str, int] = {}
    for note in notes:
        label = note.split()[0]
        urgent = label == "GLOBAL" or "MISMATCH" in note or "no hash" in note or "NOT known" in note
        if core.VERBOSE_OUTPUT or urgent:
            print(note)
        if label != "GLOBAL":
            word = {"BIBLIO": "bibliography", "CSL": "csl"}.get(label, label.lower())
            kinds[word] = kinds.get(word, 0) + 1
    kept = len(files) - len(fresh)
    if files:
        print(f"UNPACKED  {len(fresh)} file{'s' if len(fresh) != 1 else ''} into {core.display_path(target)}"
              + (f" ({kept} already there, identical)" if kept else "")
              + (f"  ({', '.join(f'{word} {count}' for word, count in kinds.items())})"
                 if kinds and not core.VERBOSE_OUTPUT else ""))
    if slim:
        if files and target.resolve() != default_target.resolve():
            print(f"WARN  --slim: pdfmd finds {default_target.name}/ beside the document by itself; "
                  f"{core.display_path(target)} it will not, unless you move it there", file=sys.stderr)
        slim_assembled(path, text, front, data, options, kept_header, blocks,
                       preamble_unpacked, metadata_unpacked, origin, bool(data_blocks), bool(history_blocks),
                       bool(file_blocks))
    return 1 if mismatch else 0


def slim_assembled(path: Path, text: str, front, data: dict | None, options: dict, kept_header: str,
                   blocks: list, preamble_unpacked: bool, metadata_unpacked: bool, origin,
                   bibliography_unpacked: bool = False, history_unpacked: bool = False,
                   files_unpacked: bool = False) -> None:
    """Rewrite ``path`` without what --unpack just wrote out (the embedded
    filter blocks, the preamble in header-includes, the keys that came from
    metadata files -- the last only where the file records their origin).
    What is left is the document's own: with its `NAME.unpacked/` folder, the
    original layout."""
    body = text[front.end():] if front else text
    body = core.EMBED_BLOCK_RE.sub("", body).rstrip("\n") + "\n"
    removed = []
    if data is None:
        # No front matter: only the comment-form marker carries the kinds.
        body = core.ASSEMBLED_COMMENT_RE.sub(ASSEMBLED_COMMENT, body)
        core.write_text_lf(path, body)
        print(f"SLIMMED   {core.display_path(path)}  (embedded files removed)")
        return
    data = dict(data)
    options = dict(options)
    if metadata_unpacked and origin:
        for keys in origin["files"].values():
            for key in keys:
                if key.startswith("pdfmd-options."):
                    options.pop(key.split(".", 1)[1], None)
                else:
                    data.pop(key, None)
        removed.append("metadata")
    if preamble_unpacked:
        removed.append("preamble")
    # What stays in header-includes: the document's own part (all of it when
    # no preamble was embedded), unless a metadata file owned the key.
    if metadata_unpacked and origin and "header-includes" in sum(origin["files"].values(), []):
        kept_header = ""
    if blocks:
        removed.append("lua")
    if bibliography_unpacked:
        removed.append("bibliography")
    if history_unpacked:
        removed.append("hst")
    if files_unpacked:
        removed.append("files")
    gone = [kind for kind in removed if kind in (options.get("embedded") or [])]
    if isinstance(options.get("no-auto"), list):
        options["no-auto"] = [kind for kind in options["no-auto"] if kind not in gone]
        if not options["no-auto"]:
            del options["no-auto"]
    if "embedded" in options:
        options["embedded"] = [kind for kind in options["embedded"] if kind not in gone]
        if not options["embedded"]:
            del options["embedded"]
    if metadata_unpacked:
        options.pop("origin", None)
    elif isinstance(options.get("origin"), dict):
        options["origin"].pop("preamble", None)
        if not options["origin"].get("files") and not options["origin"].get("document"):
            del options["origin"]
    data.pop("pdfmd-options", None)
    out = {core.ASSEMBLED_KEY: True, **{k: v for k, v in data.items() if k != "header-includes"}}
    if options:
        out["pdfmd-options"] = options
    dumped = core.yaml.dump(out, Dumper=core._EmbedDumper, sort_keys=False, allow_unicode=True,
                       default_flow_style=False, width=10**6)
    head = "---\n" + dumped + (literal_block("header-includes", kept_header) if kept_header else "") + "---\n\n"
    core.write_text_lf(path, head + body.lstrip("\n"))
    print(f"SLIMMED   {core.display_path(path)}  (removed: {', '.join(removed) or 'nothing'})")


@contextmanager
def embedded_resources(md_path: Path) -> Iterator[None]:
    """For the length of a build of ``md_path``: write the document's embedded
    bibliography/CSL blocks into a temporary folder at the path its metadata
    names them by, and register that folder (and the document's
    ``NAME.unpacked/``, if there is one) in EMBEDDED_RESOURCE_DIRS. A nested
    call for the same document (the cache route re-enters the converter) is a
    no-op. These are data, not code, so -- unlike filters -- no trust is asked."""
    if core._RESOURCE_OWNER == md_path or md_path.suffix.lower() not in (".md", ".markdown"):
        yield
        return
    folder: Path | None = None
    added: list[Path] = []
    try:
        blocks = [block for block in parse_embedded_blocks(md_path.read_text(encoding="utf-8-sig"))
                  if block["type"] in ("bibliography", "csl", "file")]
    except (OSError, UnicodeDecodeError):
        blocks = []
    if blocks:
        folder = Path(mkdtemp(prefix="pdfmd-resources-"))
        away: list[str] = []
        for block in blocks:
            for name in [block["path"] or block["name"], *block.get("also", [])]:
                if block["type"] == "file" and core.outside_folder(name):
                    # a file of a folder above the document's: a TeX search does not look there (`../x` is read from the
                    # working folder alone), so it is used where it sits, never written into somebody's folder
                    if not (md_path.parent / name).is_file():
                        away.append(name)
                    continue
                target = folder / safe_relative_path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if block.get("bytes") is not None:
                    core.atomic_write_bytes(target, block["bytes"])
                else:
                    core.write_text_lf(target, block["source"])
        if away:
            print(f"NOTE  {', '.join(away[:3])}{' and %d more' % (len(away) - 3) if len(away) > 3 else ''} "
                  f"{'is' if len(away) == 1 else 'are'} held by the source but not where the document reads "
                  f"{'it' if len(away) == 1 else 'them'}: `pdfmd --restore` (or --edit) puts the folders back", file=sys.stderr)
        added.append(folder)
    unpacked = md_path.parent / f"{md_path.stem}{core.UNPACKED_SUFFIX}"
    if unpacked.is_dir():
        added.append(unpacked.resolve())
    if not added:
        yield
        return
    core._RESOURCE_OWNER = md_path
    core.EMBEDDED_RESOURCE_DIRS.extend(added)
    try:
        yield
    finally:
        for item in added:
            if item in core.EMBEDDED_RESOURCE_DIRS:
                core.EMBEDDED_RESOURCE_DIRS.remove(item)
        core._RESOURCE_OWNER = None
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)


def literal_block(key: str, text: str) -> str:
    """``key: |`` and the text indented under it, written by hand: PyYAML will
    not emit a literal block for text with trailing spaces, and pdfmd's
    header-includes readers want exactly this shape."""
    lines = text.replace("\r\n", "\n").strip("\n").split("\n")
    return f"{key}: |\n" + "".join(f"  {line}\n" if line.strip() else "\n" for line in lines)


def strip_embedded_option_names(options: dict, kinds: frozenset[str], lua_mode: str) -> None:
    """Drop from ``options`` the file names (see option_names) of the kinds
    now embedded: they point into the original folder, and the content is
    in the file. Also `embed`, the instruction that asked for this."""
    options.pop("embed", None)
    grouped = options.get("metadata")
    if "metadata" in kinds:
        options.pop("yaml", None)
        if isinstance(grouped, dict):
            grouped.pop("yaml", None)
            grouped.pop("metadata", None)
        else:
            options.pop("metadata", None)
    if "preamble" in kinds:
        options.pop("preamble", None)
        if isinstance(grouped, dict):
            grouped.pop("preamble", None)
    if "lua" in kinds and lua_mode != "off":
        options.pop("lua-filter", None)
        if isinstance(grouped, dict):
            grouped.pop("lua-filter", None)
            grouped.pop("lua", None)
    if isinstance(grouped, dict) and not grouped:
        del options["metadata"]


def relative_filter_path(target: Path, output: Path | None) -> str:
    if output is None:
        return str(target)
    try:
        return Path(os.path.relpath(target, output.resolve().parent)).as_posix()
    except ValueError:
        return target.as_posix()


def lua_checks_format(path: Path) -> bool:
    """Whether a Lua filter looks at Pandoc's FORMAT. In the Markdown-to-
    Markdown pass --lua-mode apply runs, FORMAT is `markdown`, not what the
    real build's would be (latex, ...), so such a filter would behave
    differently there; it is embedded instead and runs in the real build."""
    try:
        return bool(re.search(r"\bFORMAT\b", path.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeDecodeError):
        return True


def apply_lua_filters(front_text: str, body: str, filters: list[Path], first: Path,
                      metadata_files: list[Path]) -> str | None:
    """Run ``filters`` over the document, Markdown in and Markdown out, and
    return the new body; None if Pandoc fails (the caller then embeds them
    instead). Only the body comes back: Pandoc's Markdown writer without
    --standalone drops the metadata, which the caller writes itself -- so a
    filter's change to the metadata, and a citation it needs resolved first
    (no --citeproc here), are not reproduced. Pandoc re-writes the text
    (tables, footnotes and line breaks may come out formatted differently).
    """
    folder = Path(mkdtemp(prefix="pdfmd-apply-"))
    try:
        source = folder / "input.md"
        core.write_text_lf(source, front_text + body)
        reader = core.resolve_from_format(source, None, metadata_files)[0] or "markdown"
        cmd = ["pandoc", str(source), "-f", reader, "-t", reader, "--wrap=preserve"]
        for metadata_file in core.pandoc_metadata_order(metadata_files):
            cmd += ["--metadata-file", str(metadata_file)]
        for lua_filter in filters:
            cmd += ["--lua-filter", str(lua_filter)]
        result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=first.parent)
        if result.returncode != 0:
            print(f"WARN  --lua-mode apply: Pandoc failed ({result.stderr.strip().splitlines()[-1:] or ['?']}); "
                  "the filters are embedded instead", file=sys.stderr)
            return None
        return result.stdout
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def embed_into_text(text: str, first: Path, plan: EmbedPlan, partial: bool = False) -> str:
    """Fold what ``plan`` names into the joined assembled ``text`` (see the
    comment above EMBED_KINDS); ``first`` is the document whose own front
    matter is merged (the scaffold, or a report's first chapter)."""
    if core.yaml is None:
        raise SystemExit("--embed-metadata needs PyYAML (pip install pyyaml)")
    kinds = plan.kinds
    front = re.match(r"^---[ \t]*\n(?P<yaml>.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    body = text[front.end():] if front else text
    document: dict = {}
    if front:
        try:
            loaded = core.yaml.safe_load(front.group("yaml"))
        except core.yaml.YAMLError as error:
            raise SystemExit(f"{core.display_path(first)}: its front matter does not parse as YAML "
                             f"({str(error).splitlines()[0]}); --embed-metadata cannot merge into it")
        document = loaded if isinstance(loaded, dict) else {}
    to_embed: list[Path] = list(plan.lua_filters) if plan.lua_mode == "embed" else []
    applied: list[Path] = []
    gated: list[Path] = []
    if "lua" in kinds and plan.lua_filters and plan.lua_mode == "apply":
        runnable = [item for item in plan.lua_filters if not lua_checks_format(item)]
        gated = [item for item in plan.lua_filters if item not in runnable]
        to_embed = list(gated)
        if runnable:
            new_body = apply_lua_filters(text[:front.end()] if front else "", body, runnable, first,
                                         plan.metadata_files if "metadata" in kinds else [])
            if new_body is None:
                to_embed = list(plan.lua_filters)
                gated = []
            else:
                applied = runnable
                body = new_body
                text = (text[:front.end()] if front else "") + body
    left_out = []
    if ("preamble" in kinds and plan.preamble_files and not front and not plan.metadata_files
            and core.promote_bare_title(text, False)[1]):
        # A new front-matter block would stop the leading `# Title` being
        # promoted to the document's title (see promote_bare_title).
        print(f"WARN  {core.display_path(first)}: has no front matter and starts with a bare '# Title'; "
              "embedding a preamble would change how that reads, so it was left out. Give the "
              "document front matter (a `title:`) to embed it", file=sys.stderr)
        kinds = kinds - {"preamble"}
        left_out.append("preamble " + ", ".join(item.name for item in plan.preamble_files) + " (left out)")
    no_auto = [kind for kind in core.EMBED_KINDS
               if kind in kinds and kind not in ("bibliography", "hst", "files")  # nothing discovers a bibliography: it is named
               and not (kind == "lua" and plan.lua_mode in ("ref", "off"))]
    if plan.lua_mode == "off":
        no_auto = [kind for kind in no_auto if kind != "lua"]
    blocks = ""
    lua_refs: list[str] = []
    entries: list[tuple[str, str]] = []
    if "lua" in kinds and plan.lua_filters:
        for lua_filter in to_embed:
            source = lua_filter.read_text(encoding="utf-8-sig")
            blocks += "\n" + render_embedded_block("lua-filter", lua_filter.name, source)
            entries.append((core.sha256_text(core.normalized_source(source)), lua_filter.name))
        if plan.lua_mode == "ref":
            lua_refs = [relative_filter_path(item, plan.output) for item in plan.lua_filters]
    file_names: list[str] = []
    if "files" in kinds and plan.sources:
        base = Path(os.path.abspath(first.parent))
        represented = {Path(os.path.abspath(item)) for item in [*plan.sources, *plan.metadata_files,
                                                                   *plan.preamble_files, *plan.lua_filters]}
        found, outside_files = core.bundle_files(first, plan.sources[1:], plan.preamble_files, "referenced", represented,
                                            plan.output or (base / "_assembled.md"), [], base)
        core.add_calc_constants(first, plan.metadata_files, base, represented, found, outside_files)
        core.drop_calc_export(first, list(plan.sources), plan.metadata_files, found, outside_files)
        limit = float(core.option_flag_number(core.first_pdfmd_option(first, plan.metadata_files, "bundle-max-mb"))
                      or core.BUNDLE_MAX_MB) * 1024 * 1024
        if sum(item.stat().st_size for item in found) > limit:
            print(f"WARN  embed files: {len(found)} files, {sum(item.stat().st_size for item in found) / 1048576:.0f} MB, is "
                  f"over the {limit / 1048576:.0f} MB limit (pdfmd-options.bundle-max-mb); none was embedded", file=sys.stderr)
            found = []
        for item in found:
            blocks_text = render_embedded_file(item.name, core.relative_posix(base, item), item.read_bytes())
            blocks += "\n" + blocks_text
            file_names.append(core.relative_posix(base, item))
        for name in outside_files:
            print(f"WARN  embed files: {name} is outside the document's folder; not embedded", file=sys.stderr)
    history_text = None
    if "hst" in kinds and plan.hst_file is not None:
        try:
            history_text = plan.hst_file.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            history_text = None
        if history_text and history_text.strip():
            blocks += "\n" + render_embedded_block("hst", plan.hst_file.name, history_text)
        else:
            history_text = None
    # ---- metadata: files lowest, the document over them
    merged: dict = {}
    file_layers: list[tuple[dict, bool]] = []
    file_options: list[dict] = []
    # Which source each key finally came from ("document", or a metadata
    # file's name): written to `pdfmd-options.origin`, so --unpack can split
    # the merged front matter back into the files it was made from.
    owner: dict[str, str] = {}
    labels: list[str] = []
    option_labels: list[str] = []
    label_of: dict[Path, str] = {}
    global_label = None
    if "metadata" in kinds:
        for metadata_file in plan.metadata_files:
            label = metadata_file.name
            while label in labels:
                label = f"{metadata_file.parent.name}-{label}"
            labels.append(label)
            label_of[metadata_file] = label
        global_label = next((label for item, label in label_of.items() if core.is_global_metadata(item)), None)
        # The files in the order a build layers them (v3.28.13): the global metadata file (pdfmd --setup) lowest,
        # as Pandoc gets it. In list order it came last, so its keys beat the folder's own metadata.yaml here.
        for metadata_file in core.pandoc_metadata_order(list(plan.metadata_files)):
            data = core.metadata_file_yaml(metadata_file)
            data.pop("pdfmd-options", None)
            file_layers.append((dict(data), False))
            for key in data:
                owner[key] = label_of[metadata_file]
            merged.update(data)
        # the keys in the order they are written in the files, as listed (only which value wins changed)
        written = [key for metadata_file in plan.metadata_files for key in core.metadata_file_yaml(metadata_file)
                   if key != "pdfmd-options"]
        merged = {key: merged[key] for key in dict.fromkeys(written)}
        for metadata_file in core.metadata_files_by_priority(plan.metadata_files):
            options = core.metadata_file_yaml(metadata_file).get("pdfmd-options")
            if isinstance(options, dict):
                file_options.append({key: value for key, value in options.items()
                                     if key not in FILE_ONLY_OPTION_KEYS})
                option_labels.append(label_of[metadata_file])
    document = dict(document)
    document_options = document.pop("pdfmd-options", None)
    for key in document:
        owner[key] = "document"
    merged.update(document)
    # `key+:` and `metadata-append` (v3.31.40): the source holds the finished values and no `key+`, so a rebuild, which has only
    # this layer, neither loses what a metadata file held nor appends twice
    append_names = core.metadata_append_keys(first, plan.metadata_files) if "metadata" in kinds else set()
    for key in [key for key in merged if core.metadata_plus_key(key)]:
        del merged[key]
        owner.pop(key, None)
    for key, value in core.merge_metadata_layers([*file_layers, (document, True)], append_names, core.display_path(first)).items():
        merged[key] = value
        owner[key] = "document"
    option_owner: dict[str, str] = {}
    for label, source in [("document", document_options if isinstance(document_options, dict) else {}),
                          *zip(option_labels, file_options)]:
        for key in source:
            option_owner.setdefault(key, label)
    options = core.merge_option_dicts([document_options if isinstance(document_options, dict) else {},
                                  *file_options])
    if append_names:
        options[core.METADATA_APPEND_KEY] = []                 # resolved above: the rebuild must not append the document's own value again
        option_owner[core.METADATA_APPEND_KEY] = "document"
    # ---- bibliography and CSL files the metadata names: data, embedded as blocks
    references: list[tuple[str, str]] = []
    for key in ("bibliography", "csl"):
        value = merged.get(key)
        for name in ([value] if isinstance(value, str) else
                     [str(item) for item in value] if isinstance(value, list) else []):
            if "://" not in name and (key, name) not in references:
                references.append((key, name))
    bib_embedded: list[str] = []
    bib_problems: list[str] = []
    renamed: dict[str, str] = {}
    if references and ("bibliography" in kinds or "csl" in kinds):
        cited: set[str] | None = None
        if plan.bib_prune:
            cited = used_citation_keys([body, json.dumps(merged, default=str, ensure_ascii=False),
                                        *(item.read_text(encoding="utf-8-sig", errors="replace")
                                          for item in plan.preamble_files)])
        search: list[Path] = []
        for directory in ([plan.metadata_files[0].parent] if plan.metadata_files else []) + [
                first.parent, *(item.parent for item in plan.metadata_files),
                first.parent / core.ACCESSORY_DIRNAME, first.parent / f"{first.stem}{core.UNPACKED_SUFFIX}", Path.cwd(),
                *(item.resolve().parent for item in plan.metadata_files)]:     # a symlinked metadata file: its real folder, as the build's --resource-path
            if directory not in search:
                search.append(directory)
        data_dir = core.pandoc_user_data_dir()

        def cites_anything() -> bool:
            if merged.get("bibliography") or merged.get("references"):
                return True
            keys = used_citation_keys([body, json.dumps(merged, default=str, ensure_ascii=False)])
            return keys is None or bool(keys)
        for key, name in references:
            if key not in kinds:
                if key == "csl":
                    plan.csl_left.append(name)            # the manifest says so, and --restore tells what the build needs
                continue
            reference = Path(name)
            # A CSL style is also looked up in Pandoc's own user data folder (csl/).
            where = search + ([data_dir / "csl", data_dir] if key == "csl" and data_dir else [])
            # `csl: apa` is `apa.csl` (Pandoc adds the suffix too): the name as written first, then with .csl
            names = [reference] + ([Path(name + ".csl")] if key == "csl" and not name.lower().endswith(".csl") else [])
            found = next((candidate for candidate in names if candidate.is_absolute() and candidate.is_file()), None)
            if found is None and not reference.is_absolute():
                found = next(((directory / candidate) for candidate in names for directory in where
                              if (directory / candidate).is_file()), None)
            if key == "csl" and not cites_anything():
                continue            # a style nothing cites with is not worth a warning, nor 2000 lines of the source (the
                                    # global metadata sets one for every document)
            if found is None:
                bib_problems.append(f"{name} (not found in the document's folders"
                                    + (" or Pandoc's csl/ folder" if key == "csl" else "") + ")")
                continue
            try:
                source = found.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                bib_problems.append(f"{name} (not UTF-8 text)")
                continue
            if key == "csl":
                if "csl" in plan.strip_kinds:
                    source = core.strip_xml_comments(source)
            elif found.suffix.lower() in BIB_SUFFIXES and (cited is not None or "bibliography" in plan.strip_kinds):
                source, kept, total = filter_bibliography(source, cited, "bibliography" in plan.strip_kinds)
                if cited is not None:
                    plan.bib_report.append(f"{found.name}: {kept} of {total} entries")
            safe = safe_relative_path(name)
            blocks += "\n" + render_embedded_block("csl" if key == "csl" else "bibliography",
                                                   found.name, source, path=safe)
            bib_embedded.append(name)
            if safe != name:
                # An absolute or `../` name cannot be written back as it is: the
                # metadata then names the embedded file by its safe path.
                renamed[name] = safe
    for key in ("bibliography", "csl"):
        value = merged.get(key)
        if renamed and isinstance(value, str):
            merged[key] = renamed.get(value, value)
        elif renamed and isinstance(value, list):
            merged[key] = [renamed.get(str(item), item) for item in value]
    strip_embedded_option_names(options, kinds, plan.lua_mode)
    if lua_refs:
        options["lua-filter"] = lua_refs
    if labels and "metadata" in kinds:
        origin: dict = {"document": [], "files": {label: [] for label in labels}}
        for key, label in owner.items():
            (origin["document"] if label == "document" else origin["files"][label]).append(key)
        for key, label in option_owner.items():
            # Bookkeeping keys, and the ones this file replaces with its own
            # embedded copy, are not part of any source.
            if (key in ("embedded", "origin", "applied-lua", "embed")
                    or (key in ("yaml", "metadata") and "metadata" in kinds)
                    or (key == "preamble" and "preamble" in kinds)
                    or (key == "lua-filter" and "lua" in kinds)):
                continue
            (origin["document"] if label == "document" else origin["files"][label]).append(f"pdfmd-options.{key}")
        if global_label is not None:
            # --unpack and --restore leave this one out: it is the building machine's, not the document's
            origin["global"] = global_label
        options["origin"] = origin
    embedded_now = [kind for kind in core.EMBED_KINDS if kind in kinds and not (
        (kind == "lua" and plan.lua_mode in ("ref", "off")) or (kind == "preamble" and not plan.preamble_files)
        or (kind == "bibliography" and not bib_embedded) or (kind == "hst" and history_text is None))]
    if file_names:
        embedded_now.append("files")
    if embedded_now:
        options["embedded"] = embedded_now
    if applied:
        options["applied-lua"] = [item.name for item in applied]
    if plan.kit_none:
        options["kit"] = "none"
    if no_auto:
        existing = options.get("no-auto")
        if existing is True or (isinstance(existing, str) and existing.casefold() in {"true", "yes", "on", "all"}):
            pass  # everything is already off
        else:
            current = ([] if existing is None or existing is False else
                       [existing] if isinstance(existing, str) else [str(item) for item in existing])
            options["no-auto"] = [*current, *(kind for kind in no_auto if kind not in current)]
    # ---- preamble: raw LaTeX at the head of header-includes
    header_parts = []
    if "preamble" in kinds:
        header_parts += [core.strip_tex_comments(text) if "preamble" in plan.strip_kinds else text
                         for text in (item.read_text(encoding="utf-8-sig") for item in plan.preamble_files)]
        if plan.preamble_files:
            preamble_record = [{"name": item.name, "lines": len(part.strip("\n").split("\n")),
                                "sha256": core.sha256_text(part.strip("\n"))}
                               for item, part in zip(plan.preamble_files, header_parts)
                               if part.strip()]
            options.setdefault("origin", {})["preamble"] = preamble_record
    own_header = core.header_includes_text(merged.pop("header-includes", None))
    if own_header:
        header_parts.append(own_header)
    if "preamble" in kinds and plan.preamble_files:
        header_parts.insert(len(plan.preamble_files), core.PREAMBLE_END_MARK)
    header_text = "\n".join(part.strip("\n") for part in header_parts if part.strip())
    # Nothing but the two bookkeeping keys to say, and no front matter to put
    # them in: the comment form of the marker carries it instead, so the
    # document does not gain a front-matter block (see mark_assembled).
    if front or merged or header_text or (set(options) - {"embedded", "no-auto", "applied-lua"}):
        out: dict = {core.ASSEMBLED_KEY: True}
        if partial:
            out[PARTIAL_KEY] = True
        out.update(merged)
        if options:
            out["pdfmd-options"] = options
        dumped = core.yaml.dump(out, Dumper=core._EmbedDumper, sort_keys=False, allow_unicode=True,
                           default_flow_style=False, width=10**6)
        head = "---\n" + dumped + (literal_block("header-includes", header_text) if header_text else "") + "---\n\n"
        result = head + body.lstrip("\n").rstrip("\n") + "\n"
    else:
        result = mark_assembled(text, no_auto, partial)
    if entries:
        remember_trusted(entries)
    if blocks:
        result = result.rstrip("\n") + "\n" + blocks
    summary = []
    if "metadata" in kinds and plan.metadata_files:
        summary.append("metadata " + ", ".join(item.name for item in plan.metadata_files))
    if "preamble" in kinds and plan.preamble_files:
        summary.append("preamble " + ", ".join(item.name for item in plan.preamble_files))
    if history_text is not None:
        summary.append(f"history {plan.hst_file.name}")
    if file_names:
        summary.append("files " + ", ".join(file_names))
    if "lua" in kinds and plan.lua_filters and plan.lua_mode != "off":
        if plan.lua_mode == "apply":
            if applied:
                summary.append("lua (applied) " + ", ".join(item.name for item in applied))
            if to_embed:
                reason = "checks FORMAT" if gated else "apply failed"
                summary.append(f"lua (embedded instead: {reason}) " + ", ".join(item.name for item in to_embed))
        else:
            summary.append(f"lua ({plan.lua_mode}) " + ", ".join(item.name for item in plan.lua_filters))
    if bib_embedded:
        summary.append("bibliography " + ", ".join(bib_embedded)
                       + (f" ({'; '.join(plan.bib_report)})" if plan.bib_report else ""))
    for problem in bib_problems:
        print(f"WARN  not embedded: {problem}", file=sys.stderr)
    summary += left_out
    print("EMBEDDED  " + ("; ".join(summary) if summary else "nothing was found to embed"))
    # What the text points at is not embedded: say which of it the file still needs.
    outside: list[str] = []
    for key in ("bibliography", "csl"):
        names = [name for kind, name in references if kind == key and name not in bib_embedded]
        if names:
            outside.append(f"{key} {', '.join(names)}")
    if re.search(r"\\(?:input|include|includegraphics)\b", header_text) and not file_names:
        outside.append("files the preamble reads (\\input, \\includegraphics)")
    if re.search(r"!\[[^\]\n]*\]\(", body) and not file_names:
        outside.append("the images in the text")
    if outside:
        print("NOTE  not embedded: " + "; ".join(outside) + " -- keep them where the document "
              "finds them (relative to the assembled file's folder)")
    if summary and not file_names:
        print("NOTE  not embedded, and not detected: data a macro in the text reads (CSV tables "
              "for plots, images in raw LaTeX) -- they stay beside the document; `--embed-metadata files` embeds "
              "what the text and the preamble name")
    return result
