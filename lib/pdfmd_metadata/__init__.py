"""Visible parent metadata: bounded discovery and ordering between local and .pdfmd layers.

The depth is decided before discovery, from the document and the layers already known. A parent cannot extend its own
search. Scaffold callers already pass the scaffold as the document, so its folder is the depth's origin.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pdfmd_base import core


class ParentMetadata(type(Path())):
    """A discovered parent file, still a Path everywhere it is consumed.

    The marker belongs to this selection, rather than a global set of filenames: the same file can be local to another
    document in a batch. It survives list copies and pickling into workers. Subclass the platform's concrete Path for
    Python 3.9 as well as newer Python versions.
    """


def is_parent_metadata(path) -> bool:
    return isinstance(path, ParentMetadata)


def parse_depth(value) -> int | str:
    """A whole number, or all; negative numbers mean the same bounded upward walk as all."""
    if value is None:
        return 1
    if isinstance(value, str) and value.strip().casefold() == "all":
        return "all"
    if not isinstance(value, bool) and isinstance(value, (str, int)):
        try:
            return int(value)
        except ValueError:
            pass
    raise SystemExit(f"pdfmd-options: metadata-parents: {value!r}: use a whole number (0 = off), all, or a negative number")


def with_metadata_parents(found, directory, document, report, document_class, document_stem, discover, folders, extra):
    """Add nearest-first parent layers, using precisely the local YAML selection rule in each visible metadata/ folder."""
    if not discover:
        return found
    local = found if isinstance(found, list) else [found] if found is not None else []
    known = [*local, *folders, *([extra] if extra is not None else [])]
    value = (core.first_pdfmd_option(document, known, "metadata-parents") if document is not None
             else core.config_options().get("metadata-parents"))
    depth = parse_depth(value)
    if depth == 0:
        return found
    start = directory.resolve()
    boundary = None
    for folder, data, _ in core.folder_walk(str(start)):
        if data is not None and str(data.get("inherit", True)).strip().casefold() in ("false", "no", "off", "0"):
            boundary = folder.parent
            break
    parents = []
    if boundary != start:
        for distance, ancestor in enumerate(start.parents, start=1):
            if isinstance(depth, int) and depth >= 0 and distance > depth:
                break
            folder = ancestor / core.ACCESSORY_DIRNAME
            if folder.is_dir():
                selected = core.find_local_metadata(folder, None, report, document_class, document_stem, search_dirs=[folder])
                parents.extend(ParentMetadata(path) for path in
                               (selected if isinstance(selected, list) else [selected] if selected is not None else []))
            if ancestor == boundary:
                break
    if not parents:
        return found
    return [*local, *parents]


def parent_metadata_order(metadata_files, extra):
    """(parent layers in Pandoc order, ordinary local files). Precedence only reverses files WITHIN a layer."""
    groups = {}
    local = []
    for path in metadata_files:
        if path == extra or path in core.KIT_METADATA or core.is_folder_metadata(path):
            continue
        if is_parent_metadata(path):
            groups.setdefault(path.parent, []).append(path)
        else:
            local.append(path)
    parents = []
    for folder in sorted(groups, key=lambda folder: len(folder.parts)):
        files = groups[folder]
        parents.extend(reversed(files) if core.metadata_precedence() == "first" else files)
    return parents, local


def metadata_sources(document, no_auto=None, metadata_request=None) -> bool:
    """The metadata sources for --show-config DOCUMENT, strongest file first, without building."""
    if document is None:
        return True
    try:
        document = core.find_markdown(Path(document))
        disabled = core.effective_no_auto(document, no_auto)
        plan = core.plan_scaffold(document, [], disabled, metadata_request)
        if plan is not None:
            document = plan.scaffold
            disabled = core.effective_no_auto(document, no_auto)
        requested = metadata_request
        if requested is None:
            requested = ([] if core.auto_disabled(disabled, "metadata")
                         else core.option_names(core.frontmatter_pdfmd_options(document), "yaml") or None)
        found = core.find_metadata(document.parent, requested, document_stem=document.stem, document=document,
                                   discover=not core.discovery_disabled(disabled, "metadata"))
        files = [] if found is None or found is core.AUTO_METADATA_DISABLED else found if isinstance(found, list) else [found]
        print("metadata sources (strongest first):")
        for file in core.metadata_files_by_priority(files):
            print(f"  {core.display_path(file)}")
    except (FileNotFoundError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return False
    return True


def with_parent_preambles(found, document, pandoc_options, no_auto, metadata_files):
    """Apply the existing preamble filename rule to discovered parent metadata folders, lowest layer first."""
    if core.discovery_disabled(no_auto, "preamble"):
        return found
    parents, _ = parent_metadata_order(metadata_files, None)
    folders = dict.fromkeys(path.parent for path in parents)
    preambles = []
    for folder in folders:
        for path in core.find_preambles(folder, document.stem, pandoc_options):
            if path not in preambles and path not in found:
                preambles.append(path)
    return preambles + found
