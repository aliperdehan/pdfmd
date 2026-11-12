"""Which Markdown file bare `pdfmd` builds, and `pdfmd --which`: the layers of `ranking` settings in force for a folder's documents
(their own front matter and metadata files, `.pdfmd/ranking.yaml`, folder settings, the global `ranking.yaml` and the config), the
clashes between documents, the candidates `pdfmd_ranking.choose` takes, and the command that explains the choice.

Moved out of `pdfmd.py` unchanged (v3.33.19, SPLIT.md), with `RANKING_FILE`, `RANKING_DOCUMENT_KEYS` and `FOLDER_SETTINGS`. `core` is the
`pdfmd` module, bound when the module is first loaded (a stand-in in `pdfmd.py` loads it on the first call; the first binding wins);
the pdfmd names the code uses (`FOLDER_DIR`, `LookupAmbiguous`, `config_options`, `config_path`, `display_path`, `document_priority`,
`find_local_metadata`, `find_markdown`, `folder_file_data`, `folder_walk`, `frontmatter_pdfmd_options`, `metadata_file_yaml`,
`priority_enabled` and `source_markdown`) are read as `core.X` when it runs; `core.config_options` is patched by tests as
`pdfmd.config_options`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pdfmd_base import core


FOLDER_SETTINGS = ".pdfmd/config.yaml"
RANKING_FILE = "ranking.yaml"
RANKING_DOCUMENT_KEYS = ("classes", "ladder")        # what a document may say about the rules; `by`, `names`, `inherit` are the folder's


def ranking_inherit_off(mapping) -> bool:
    return isinstance(mapping, dict) and str(mapping.get("inherit", True)).strip().casefold() in ("false", "no", "off", "0")


def read_ranking_file(path: Path) -> dict | None:
    """The `ranking.yaml` at ``path`` as the ranking mapping (a `ranking:` wrapped around it is accepted), None when there is none
    or it cannot be used (folder_file_data says why, once)."""
    data = core.folder_file_data(path)
    if data is not None and set(data) == {"ranking"} and isinstance(data["ranking"], dict):
        return data["ranking"]
    return data


def ranking_of_options(options) -> dict | None:
    value = options.get("ranking") if isinstance(options, dict) else None
    return value if isinstance(value, dict) else None


def ranking_for_document(mapping: dict, where: str) -> dict:
    """What a document's own `ranking` may say: its classes and ladder. The rest is the folder's to set (a WARN)."""
    ignored = sorted(str(key) for key in mapping if key not in RANKING_DOCUMENT_KEYS)
    if ignored:
        print(f"WARN  ranking: {where}: {', '.join(ignored)} can be set by a folder or the config, not by a document; ignored",
              file=sys.stderr)
    return {key: value for key, value in mapping.items() if key in RANKING_DOCUMENT_KEYS}


def ranking_layers(files: list[Path]) -> tuple[list[tuple[str, dict]], set[str]]:
    """The `ranking` mappings in force for these documents, NEAREST FIRST (the order Ranking.from_layers takes): the documents' own
    (front matter, then a metadata file named after the document; the newest document first), then, folder by folder from theirs
    upward, `.pdfmd/ranking.yaml`, the folder's `metadata.yaml`, the folder settings' `options.ranking`; then the global
    `ranking.yaml` and the config's `options.ranking`. A `ranking.yaml` or folder settings with `inherit: false` end the climb.
    Also the names of the layers that are the documents' own (ranking_clashes). Nothing here is read until bare `pdfmd` has several
    documents to choose from."""
    directory = files[0].parent.resolve()
    own: set[str] = set()
    stems = {file.stem.casefold() for file in files}
    layers: list[tuple[str, dict]] = []
    seen: set[Path] = set()
    shared: list[tuple[str, dict]] = []
    newest_first = sorted(files, key=lambda file: (-file.stat().st_mtime_ns if file.exists() else 0, file.name.casefold()))
    for file in newest_first:
        mapping = ranking_of_options(core.frontmatter_pdfmd_options(file))
        if mapping is not None:
            where = f"{core.display_path(file)} pdfmd-options"
            layers.append((where, ranking_for_document(mapping, where)))
            own.add(where)
        try:
            found = core.find_local_metadata(directory, None, False, None, file.stem)
        except (OSError, ValueError):
            found = None
        for path in (found if isinstance(found, list) else [found] if isinstance(found, Path) else []):
            if path.resolve() in seen:
                continue
            seen.add(path.resolve())
            mapping = ranking_of_options(core.metadata_file_yaml(path).get("pdfmd-options"))
            if mapping is None:
                continue
            if path.stem.casefold() in stems:                       # named after one document: its own, like its front matter
                layers.append((core.display_path(path), ranking_for_document(mapping, core.display_path(path))))
                own.add(core.display_path(path))
            else:
                shared.append((core.display_path(path), mapping))
    walk = {entry[0].parent: entry for entry in core.folder_walk(str(directory))}
    stopped = False
    for level in (directory, *directory.parents):
        file_mapping = read_ranking_file(level / core.FOLDER_DIR / RANKING_FILE)
        if file_mapping is not None:
            layers.append((core.display_path(level / core.FOLDER_DIR / RANKING_FILE), file_mapping))
        if level == directory:
            layers += shared
        entry = walk.get(level)
        if entry is not None:
            _, settings, metadata = entry
            mapping = ranking_of_options(core.metadata_file_yaml(metadata).get("pdfmd-options")) if metadata is not None else None
            if mapping is not None:
                layers.append((core.display_path(metadata), mapping))
            mapping = ranking_of_options(settings.get("options")) if settings is not None else None
            if mapping is not None:
                layers.append((core.display_path(level / FOLDER_SETTINGS), mapping))
        if ranking_inherit_off(file_mapping) or (entry is not None and ranking_inherit_off(entry[1])):
            stopped = True
            break
    path = core.config_path()
    if not stopped and path is not None:
        file_mapping = read_ranking_file(path.parent / RANKING_FILE)
        if file_mapping is not None:
            layers.append((core.display_path(path.parent / RANKING_FILE), file_mapping))
        mapping = ranking_of_options(core.config_options())
        if mapping is not None:
            layers.append((f"config {core.display_path(path)}", mapping))
    return layers, own


def ranking_clashes(layers: list[tuple[str, dict]], own: set[str]) -> list[str]:
    """Warnings for two documents that define the same class, or the ladder, differently (the newer document's wins, as it comes
    first in the layers)."""
    documents = [(where, mapping) for where, mapping in layers if where in own]
    warnings, classes, ladder = [], {}, None
    for where, mapping in documents:
        for name, spec in (mapping.get("classes") or {}).items() if isinstance(mapping.get("classes"), dict) else []:
            if name in classes and classes[name][1] != spec:
                warnings.append(f"class {name} is defined differently in {classes[name][0]} and {where}; using the first")
            classes.setdefault(name, (where, spec))
        if "ladder" in mapping:
            if ladder is not None and ladder[1] != mapping["ladder"]:
                warnings.append(f"the ladder is defined differently in {ladder[0]} and {where}; using the first")
            ladder = ladder or (where, mapping["ladder"])
    return warnings


def bare_ranking(files: list[Path]):
    """The rules for choosing among ``files``: the built-in ranking under the layers ranking_layers() finds."""
    from pdfmd_ranking import Ranking
    layers, own = ranking_layers(files)
    ranking = Ranking.from_layers(layers)
    ranking.warnings += ranking_clashes(layers, own)
    return ranking


def priority_candidates(files: list[Path]):
    """pdfmd_ranking.Candidate for each file: its priority value and where it was written, and its modification time."""
    from pdfmd_ranking import Candidate
    candidates = []
    for file in files:
        value, where = core.document_priority(file)
        try:
            modified = file.stat().st_mtime_ns
        except OSError:
            modified = 0
        candidates.append(Candidate(file, value, where or "priority", modified))
    return candidates


def which_command(names: list[str], args) -> bool:
    """`pdfmd --which [NAME ...]`: say what a bare `pdfmd` would build and why, or which file each NAME finds, and build nothing.
    Every Markdown file of the folder gets a row (built, left out and why, tied), then the rules in force and where they came from."""
    from pdfmd_ranking import RankingError, choose, explain
    ok = True
    if names:
        for name in names:
            try:
                print(f"{name}  ->  {core.display_path(core.find_markdown(Path(name)))}")
            except (FileNotFoundError, core.LookupAmbiguous) as error:
                print(f"{name}: {error}", file=sys.stderr)
                ok = False
        return ok
    folder = Path.cwd()
    files = sorted(folder.glob("*.md"), key=lambda path: path.name.casefold())
    if not files:
        print(f"WHICH  no Markdown files in {core.display_path(folder)}")
        return False
    if len(files) == 1:
        print(f"WHICH  bare pdfmd builds {core.display_path(files[0])}, the only Markdown file in this folder")
        return True
    try:
        layers, own = ranking_layers(files)
        from pdfmd_ranking import Ranking
        ranking = Ranking.from_layers(layers)
    except RankingError as error:
        print(f"ranking: {error}", file=sys.stderr)
        return False
    ranking.warnings += ranking_clashes(layers, own)
    newest, include_never = args.newest, args.include_never
    if core.priority_enabled(folder) or newest:
        sources = core.source_markdown(files)
        if len(sources) != len(files):
            print(f"NOTE  not candidates (pdfmd's own output): {', '.join(core.display_path(file) for file in files if file not in sources)}")
            files = sources
    candidates = priority_candidates(files)
    if not core.priority_enabled(folder) and not newest:
        print("WHICH  --no-auto priority: bare pdfmd stops with the list of Markdown files and builds none of them")
        return True
    choice = choose(candidates, ranking, by=["newest"] if newest else None, show=core.display_path, include_excluded=include_never)
    for line in [f"WARN  ranking: {text}" for text in ranking.warnings] + choice.warnings:
        print(line, file=sys.stderr)
    if choice.winner is not None:
        print(f"WHICH  bare pdfmd{' --newest' if newest else ''} in {core.display_path(folder)} builds {core.display_path(choice.winner)}")
    else:
        print(f"WHICH  bare pdfmd in {core.display_path(folder)} would stop: {choice.error}")
    rows = explain(candidates, ranking, choice, core.display_path)
    width = [max(len(row[column]) for row in rows) for column in range(3)]
    for document, verdict, says, stamp in rows:
        print(f"       {document:<{width[0]}}  {verdict:<{width[1]}}  {says:<{width[2]}}  {stamp}")
    print(f"RULES  from {', '.join([where for where, _ in layers] + ['the built-in default'])}")
    print(f"       names: {ranking.names}   by: {', '.join(ranking.by) or 'nothing'}")
    for line in ranking.describe():
        print(f"       {line}")
    return choice.winner is not None
