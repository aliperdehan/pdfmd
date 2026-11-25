"""Citation sources in priority order, with one explicit winner for every key (D61).

Bibliographies and inline references accumulate; all other metadata keeps its normal precedence. The first source of a key
wins. Pandoc keeps the LAST bibliography entry and always prefers inline references, so relying on its merge would lose the
per-layer ordering. Remove losing entries before passing the accumulated values through the existing metadata append filter.
Original files are never edited. Bibliography syntax (including BibTeX strings and crossrefs) stays in its original format.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from pdfmd_base import core

from pdfmd_base import pandoc_run
from pdfmd_log import emit


def values(value):
    return value if isinstance(value, list) else [] if value is None else [value]


def command_sources(arguments):
    """Pandoc bibliography/metadata spellings; template variables are deliberately excluded."""
    from pdfmd_args import metadata_command_layers

    result = []
    tokens = iter(arguments)
    for token in tokens:
        if token == "--bibliography":
            result.append(next(tokens, ""))
        elif token.startswith("--bibliography="):
            result.append(token.split("=", 1)[1])
        elif token in ("-M", "--metadata") or token.startswith(("-M", "--metadata=")):
            parts = [token, next(tokens, "")] if token in ("-M", "--metadata") else [token]
            for mapping, _ in metadata_command_layers(parts):
                for key in ("bibliography", "bibliography+"):
                    result.extend(values(mapping.get(key)))
    return {"bibliography": result} if result else {}


def layers(sources, metadata_files, arguments):
    """Highest first: CLI, explicit -y, documents, then the existing metadata order, references before files in each layer."""
    explicit = any(token in ("-y", "--metadata-file") or token.startswith(("--metadata-file=", "-y"))
                   for token in sys.argv[1:])
    ordered = core.metadata_files_by_priority(metadata_files)
    named = [path for path in ordered if explicit and path not in core.KIT_METADATA
             and not core.is_folder_metadata(path) and not core.is_global_metadata(path)
             and not core.deferred("pdfmd_metadata", "is_parent_metadata")(path)]
    return [("command line", command_sources(arguments)),
            *((core.display_path(path), core.metadata_file_yaml(path)) for path in named),
            *((core.display_path(path), core.front_matter_dict(core.read_text_best_effort(path))) for path in reversed(sources)),
            *((core.display_path(path), core.metadata_file_yaml(path)) for path in ordered if path not in named)]


def resource_folders(sources, metadata_files):
    """Use the same cwd and resource path as the build, including symlink targets and embedded resources."""
    import os

    directory = sources[0].resolve().parent
    cwd = core.metadata_cwd(metadata_files, directory)
    option = core.resource_path_option(directory, cwd, metadata_files)
    entries = option[1].split(os.pathsep) if option else [str(cwd)]
    return list(dict.fromkeys((cwd if name == "." else Path(name)).resolve() for name in entries))


def locate(name, folders):
    path = Path(str(name)).expanduser()
    return next((folder / path for folder in folders if (folder / path).is_file()), path)


def read_entries(path):
    """(entries as (key, original), render function), or None for an unreadable/unsupported source.
    Case matters for citation identifiers, as it does in Pandoc.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
        suffix = path.suffix.lower()
        if suffix in (".bib", ".bibtex", ".biblatex"):
            items, tail = core.parse_bibliography(text)

            def render(kept):
                return "".join(item["gap"] + (item["text"] if id(item) in kept or not item["key"] else "")
                               for item in items) + tail
            return [(item["key"], item) for item in items if item["key"]], render
        if suffix == ".json":
            data = json.loads(text)
            entries = data.get("items", data) if isinstance(data, dict) else data
        elif suffix in (".yaml", ".yml"):
            data = core.yaml.safe_load(text)
            entries = data.get("references", []) if isinstance(data, dict) else data
        else:
            return None
        if not isinstance(entries, list):
            return None

        def render(kept):
            filtered = [item for item in entries if id(item) in kept or not isinstance(item, dict) or "id" not in item]
            result = {**data, ("items" if suffix == ".json" else "references"): filtered} if isinstance(data, dict) else filtered
            return json.dumps(result, ensure_ascii=False) if suffix == ".json" else core.yaml.safe_dump(result, allow_unicode=True)
        return [(str(item["id"]), item) for item in entries if isinstance(item, dict) and "id" in item], render
    except (OSError, UnicodeError, ValueError, core.yaml.YAMLError):
        return None


def literal(name):
    """A file name as Pandoc must read it from a metadata file.

    Pandoc parses every YAML string as Markdown, so a Windows path loses its folders (`\\Users` and `\\Temp` are read as raw
    TeX commands, which gave `C:22wg_n_7.bib`) and smart punctuation rewrites dots and quotes. A backslash before an ASCII
    punctuation mark is that mark, literally, in Pandoc's Markdown, so every one of them gets one, except `/` and `:`: they
    mean nothing inside a path, and Pandoc's plain `commonmark` reader keeps `\\/` and `\\:` as written (a CommonMark document
    would then name a file that does not exist).
    """
    return re.sub(r"([!-.;-@\[-`{-~])", r"\\\1", str(name))


def written_name(name, path, folders):
    """What the build hands Pandoc for a bibliography file nothing rewrote.

    The name as the author wrote it when it is the file the start folder holds (as before 3.33.232: natbib and biblatex copy
    the name into `\\bibliography{}`, and Pandoc 3.1.3 escapes every `_` of a long absolute path there); otherwise the file's
    absolute path, with forward slashes, which Pandoc, BibTeX and Biber read on every system.
    """
    start = Path(str(name)).expanduser()
    if not start.is_absolute() and (folders[0] / start).is_file() and (folders[0] / start).resolve() == path.resolve():
        return str(name)
    return path.resolve().as_posix()


def cached(text, suffix):
    target = core.cache_root() / "bibliography" / (hashlib.sha256(text.encode("utf-8")).hexdigest() + suffix)
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        core.atomic_write_text(target, text)
    return target


def native_references(references):
    """BibTeX/Biber read files, not Pandoc's inline reference metadata. Let Pandoc translate CSL fields losslessly."""

    done = pandoc_run([core.which("pandoc"), "-f", "csljson", "-t", "biblatex"],
                          input=json.dumps(references, ensure_ascii=False), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.returncode:
        raise SystemExit("Cannot prepare inline bibliography references: " + done.stderr)
    return cached(done.stdout, ".bib")


def merge_sources(sources, metadata_files, arguments, no_auto=None):
    """Accumulated citation metadata, with at most one warning per clashing key per build."""
    folders = resource_folders(sources, metadata_files)
    winners, clashes, references, bibliographies, files = {}, {}, [], [], set()
    declared = False
    parsed_files = {}

    def read(path):
        path = path.resolve()
        if path not in parsed_files:
            parsed_files[path] = read_entries(path)
        return parsed_files[path]

    ordered = layers(sources, metadata_files, arguments)
    from .discovery import discover
    if no_auto is None:
        no_auto = core.effective_no_auto(sources[0], None)
    automatic = discover(sources, metadata_files, ordered, read, no_auto)
    if automatic:
        ordered.append(("automatic bibliography", {"bibliography": automatic}))

    def accept(key, label):
        if key not in winners:
            winners[key] = label
            return True
        clashes.setdefault(key, [winners[key]]).append(label)
        return False

    for label, mapping in ordered:
        declared |= any(key in mapping for key in ("bibliography", "bibliography+", "references", "references+"))
        # Inside a layer keep Pandoc's existing last-entry-wins rule, including key+ after the plain key.
        for key in ("references+", "references"):
            for item in reversed(values(mapping.get(key))):
                if isinstance(item, dict) and "id" in item and accept(str(item["id"]), label + " references"):
                    references.append(item)
        for key in ("bibliography+", "bibliography"):
            for name in reversed(values(mapping.get(key))):
                if not name or isinstance(name, (dict, bool)):
                    continue
                path = locate(name, folders)
                identity = path.resolve()
                if identity in files:
                    continue
                files.add(identity)
                parsed = read(path)
                rewritten = False
                if parsed is not None:
                    entries, render = parsed
                    kept = {id(item) for citation, item in reversed(entries) if accept(citation, core.display_path(path))}
                    if len(kept) != len(entries):
                        path, rewritten = cached(render(kept), path.suffix), True
                if not path.is_file():
                    bibliographies.append(literal(name))
                else:
                    bibliographies.append(literal(path.resolve().as_posix() if rewritten else written_name(name, path, folders)))
    seen = core.BUILD.setdefault("bibliography-warnings", set())
    for key, origins in clashes.items():
        message = f"WARN  bibliography key {key}: {origins[0]} wins; ignored in {', '.join(origins[1:])}"
        if message not in seen:
            seen.add(message)
            emit("warning", None, message, file=sys.stderr)
    if not declared:
        return {}
    method = core.first_pdfmd_option(sources[0], metadata_files, "citation-engine")
    if references and ("--biblatex" in arguments or "--natbib" in arguments or method in ("biblatex", "natbib")):
        bibliographies.append(literal(native_references(references).resolve().as_posix()))
        references = []
    return {"bibliography": bibliographies, "references": references}
