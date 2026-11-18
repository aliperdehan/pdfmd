"""Command-only discovery; record paths keep the origin of the naming layer."""
from __future__ import annotations

from pathlib import Path
import sys

from pdfmd_base import core
from .record import RecordError


class FolderDocument(type(Path())):
    """A folder command has no document front matter and creates no dummy file."""
    def read_text(self, *args, **kwargs):
        return ""

    @property
    def parent(self):
        return Path(str(super().parent))


def context(place):
    place = Path(place).expanduser().resolve()
    if not place.exists():
        raise RecordError("--in path does not exist")
    document = place if place.is_file() else FolderDocument(place / "__excerpts__.md")
    folder = document.parent
    found = core.find_metadata(folder, None, document=document, document_stem=document.stem, kits=False)
    metadata = found if isinstance(found, list) else [found] if isinstance(found, Path) else []
    return document, metadata


def discover(document, metadata, verbose=False):
    layers = [(document, core.frontmatter_pdfmd_options(document))]
    layers += [(path, core.metadata_file_yaml(path).get("pdfmd-options", {}))
               for path in core.metadata_files_by_priority(metadata)]
    layers += [(Path(path), options) for path, options in core.folder_layer_files(str(document.parent))]
    layers += [(core.config_path(), core.config_options())]
    for origin, options in layers:
        if not isinstance(options, dict) or "excerpts" not in options:
            continue
        value = options["excerpts"]
        if value is False or isinstance(value, str) and value.strip().casefold() == "off":
            raise RecordError("excerpts are off in this context")
        if not isinstance(value, str) or not value.strip():
            raise RecordError("pdfmd-options.excerpts must be a path or off")
        path = Path(value).expanduser()
        return (origin.parent / path).resolve()

    # Reuse the bounded parent/layer rules, including inherit:false boundaries.
    from pdfmd_metadata import parse_depth
    depth = parse_depth(core.first_pdfmd_option(document, metadata, "metadata-parents"))
    boundary = next((directory for directory, data, _ in core.folder_walk(str(document.parent))
                     if data is not None and str(data.get("inherit", True)).strip().casefold() in ("false", "no", "off", "0")), None)
    directories = [document.parent]
    if boundary != document.parent:
        for distance, parent in enumerate(document.parent.parents, 1):
            if isinstance(depth, int) and depth >= 0 and distance > depth:
                break
            directories.append(parent)
            if parent == boundary:
                break
    # Explicit .pdfmd layers may be further up than visible parent metadata.
    candidates = []
    for directory in directories:
        candidates.extend((directory / "excerpts.json", directory / "metadata" / "excerpts.json"))
        candidates.append(directory / ".pdfmd" / "excerpts.json")
    candidates.extend(Path(path).parent / "excerpts.json" for path, _ in core.folder_layer_files(str(document.parent)))
    found = list(dict.fromkeys(path.resolve() for path in candidates if path.is_file()))
    if verbose:
        for other in found[1:]:
            print(f"excerpts: further file ignored: {core.display_path(other)}", file=sys.stderr)
    return found[0] if found else document.parent / "excerpts.json"


def bibliography(document, metadata):
    """Case-preserving entries for collision checks and source matching, without Pandoc."""
    from pdfmd_bibliography.sources import read_entries, locate, values
    folders = [document.parent, *core.accessory_directories(document.parent, document.stem)]
    result = {}
    layers = [(document, core.front_matter_dict(core.read_text_best_effort(document)))]
    layers += [(path, core.metadata_file_yaml(path)) for path in core.metadata_files_by_priority(metadata)]
    for origin, mapping in layers:
        for entry in values(mapping.get("references")):
            if isinstance(entry, dict) and "id" in entry:
                result.setdefault(str(entry["id"]), (entry, origin.parent))
        for name in values(mapping.get("bibliography")):
            path = locate(name, [origin.parent, *folders])
            parsed = read_entries(path)
            if parsed:
                for key, item in parsed[0]:
                    result.setdefault(key, (item, path.parent))
    # Bibliography discovery also finds local .bib files for fragments with no declaration.
    from pdfmd_bibliography.discovery import candidates
    for path in candidates([document], metadata):
        parsed = read_entries(path)
        if parsed:
            for key, item in parsed[0]:
                result.setdefault(key, (item, path.parent))
    return result


class PrivatePaths:
    """The active record's identity and basename are both private to the project."""
    def __init__(self):
        self.paths = set()
        self.names = {"excerpts.json"}

    def contains(self, path):
        return path.name in self.names or path.resolve() in self.paths


def private_paths(sources, metadata):
    private = PrivatePaths()
    for document in sources:
        try:
            path = discover(document, list(metadata))
        except RecordError:
            continue
        if path.is_file():
            private.paths.add(path.resolve())
            private.names.add(path.name)
    return private
