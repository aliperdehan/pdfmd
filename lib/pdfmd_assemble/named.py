"""Named preambles and Lua filters, with the file that owns each relative path."""
from pathlib import Path
import sys

from pdfmd_base import core


def sources(document, metadata_files):
    """The ordinary option cascade, retaining file paths instead of display labels."""
    yield document, core.frontmatter_pdfmd_options(document)
    for path in core.metadata_files_by_priority(metadata_files):
        options = core.metadata_file_yaml(path).get('pdfmd-options')
        yield path, options if isinstance(options, dict) else {}
    for path, options in core.folder_layer_files(str(document.resolve().parent)):
        yield Path(path), options
    config = core.config_path()
    if config is not None:
        yield config, core.config_options()


def names(options, kind, suffix=''):
    """Flat and grouped spellings add within one layer; empty values still replace."""
    present, found = False, []
    grouped = options.get('metadata')
    aliases = ('lua-filter', 'lua') if kind == 'lua-filter' else (kind,)
    for mapping, keys in ((options, (kind,)), (grouped, aliases)):
        if not isinstance(mapping, dict):
            continue
        for key in keys:
            key += suffix
            if key not in mapping:
                continue
            present = True
            value = mapping[key]
            found.extend(str(item) for item in ([value] if isinstance(value, str) else value if isinstance(value, list) else []))
    return present, found


def files(document, metadata_files, kind):
    """Nearest lists replace, key+: (or key+=:) appends; resolve only the effective names."""
    held = []
    for owner, options in reversed(list(sources(document, metadata_files))):
        present, values = names(options, kind)
        if present:
            held = [(owner, name) for name in values]
        for suffix in ('+', '+='):
            _, values = names(options, kind, suffix)
            held.extend((owner, name) for name in values)
    resolved = []
    for owner, name in held:
        path = (owner.parent / name).resolve()
        if not path.is_file():
            if kind == 'lua-filter' and owner == document and core.is_assembled_document(document):
                # An assembled --lua-mode ref document retains its existing best-effort behaviour.
                print(f"WARN  {core.display_path(document)}: the Lua filter it names, {name!r}, was not found "
                      f"at {path}; building without it", file=sys.stderr)
                continue
            raise SystemExit(f"{owner}: pdfmd-options.{kind} names {name!r}, which doesn't exist at {path}")
        if path not in resolved:
            resolved.append(path)
    return resolved
