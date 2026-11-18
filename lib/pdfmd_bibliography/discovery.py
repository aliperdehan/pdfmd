"""One bounded search per build for missing citation keys (D60).

Only local BibTeX-family files in existing accessory/resource folders are candidates; never walk recursively or use the
network. These conservative candidate rules fill the gap in the supplied proposal. Automatic sources sit below every
explicitly named source. Every file holding a missing key is added, so ambiguity goes through the normal clash warning.
"""
from __future__ import annotations

from pdfmd_base import core


def cited_keys(sources, layers):
    """Reuse --check's code/comment/math/URL masking and citation grammar; preserve case for Pandoc."""
    from pdfmd_check.lint import Analysis, Source, CITE_RE, LATEX_CITE_RE, CROSSREF_KINDS

    keys = set()

    def add(text):
        for found in CITE_RE.finditer(text):
            key = (found.group(1) or found.group(2)).strip()
            if key != "*" and not (":" in key and key.split(":")[0] in CROSSREF_KINDS):
                keys.add(key)

    for path in sources:
        analysis = Analysis(Source(str(path), path, core.read_text_best_effort(path)))
        add(analysis.cited)
        for found in LATEX_CITE_RE.finditer(analysis.masked):
            keys.update(key.strip() for key in found.group(1).split(",") if key.strip() and key.strip() != "*")
    for _, mapping in layers:
        value = mapping.get("nocite")
        if isinstance(value, str):
            add(value)
    return keys


def candidates(sources, metadata_files):
    """A finite, deterministic list: document/accessory folders, then the existing resource folders; no recursive search."""
    from .sources import resource_folders

    folders = [*core.accessory_directories(sources[0].resolve().parent, sources[0].stem),
               *resource_folders(sources, metadata_files)]
    paths = []
    for folder in dict.fromkeys(folders):
        try:
            found = sorted(folder.iterdir(), key=lambda item: core.natural_key(item.name))
        except OSError:
            continue
        for path in found:
            if path.suffix.lower() in (".bib", ".bibtex", ".biblatex") and path.is_file() and path.resolve() not in paths:
                paths.append(path.resolve())
    return paths


def discover(sources, metadata_files, layers, read, no_auto):
    """All candidate files holding at least one initially missing key, cached across engine retries (including no matches)."""
    from .sources import values, locate, resource_folders

    if core.discovery_disabled(no_auto, "bib"):
        return []
    scope = (tuple(sources), tuple(metadata_files), core.BUILD.get("output"))
    held = core.BUILD.get("bibliography-discovery")
    if held is not None and held[0] == scope:
        return held[1]
    wanted = cited_keys(sources, layers)
    known, named = set(), set()
    folders = resource_folders(sources, metadata_files)
    for _, mapping in layers:
        for key in ("references", "references+"):
            known.update(str(item["id"]) for item in values(mapping.get(key)) if isinstance(item, dict) and "id" in item)
        for key in ("bibliography", "bibliography+"):
            for name in values(mapping.get(key)):
                if not name or isinstance(name, (dict, bool)):
                    continue
                path = locate(name, folders).resolve()
                named.add(path)
                parsed = read(path)
                if parsed is not None:
                    known.update(citation for citation, _ in parsed[0])
    wanted = core.deferred("pdfmd_excerpts.resolution", "candidate_keys")(
        sources, metadata_files, wanted, known, no_auto, layers)
    missing = wanted - known
    added = []
    if missing:
        for path in candidates(sources, metadata_files):
            if path in named:
                continue
            parsed = read(path)
            if parsed is not None and any(key in missing for key, _ in parsed[0]):
                added.append(str(path))
                core.AUTO_LOG.record("BIB", core.display_path(path), core.VERBOSE_OUTPUT,
                                     heading="FOUND", short=core.display_path(path))
    core.BUILD["bibliography-discovery"] = (scope, added)
    return added
