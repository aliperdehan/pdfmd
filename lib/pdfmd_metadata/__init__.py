"""Metadata discovery, layering, appending, presets and calc-filter arguments.

Visible parent metadata provides bounded discovery and ordering between local and .pdfmd layers.

The depth is decided before discovery, from the document and the layers already known. A parent cannot extend its own
search. Scaffold callers already pass the scaffold as the document, so its folder is the depth's origin.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pdfmd_base import core
from decimal import Decimal
import hashlib
import os
import re


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


def _resolved(path) -> Path:
    try:
        return Path(path).resolve()
    except OSError:
        return Path(path)


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
    seen = {_resolved(path) for path in local}     # a local metadata/ linked to a parent's (`metadata -> ../metadata`) is one layer
    if boundary != start:
        for distance, ancestor in enumerate(start.parents, start=1):
            if isinstance(depth, int) and depth >= 0 and distance > depth:
                break
            folder = ancestor / core.ACCESSORY_DIRNAME
            if folder.is_dir():
                selected = core.find_local_metadata(folder, None, report, document_class, document_stem, search_dirs=[folder])
                for path in selected if isinstance(selected, list) else [selected] if selected is not None else []:
                    if _resolved(path) not in seen:
                        seen.add(_resolved(path))
                        parents.append(ParentMetadata(path))
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


AUTO_METADATA_DISABLED = object()


METADATA_APPEND_KEY = "metadata-append"


METADATA_APPEND_BLOCKED = ("header-includes", "pdfmd-options")          # lifted into header files by pdfmd itself


def metadata_plus_key(key) -> bool:
    return isinstance(key, str) and len(key) > 1 and key.endswith("+")


def metadata_append_keys(md_path: Path | None, metadata_files: list[Path]) -> set[str]:
    """The keys whose document value appends (`pdfmd-options.metadata-append`: a name or a list of names); empty: replace."""
    value = core.first_pdfmd_option(md_path, list(metadata_files), METADATA_APPEND_KEY) if md_path is not None else None
    if value is None or value is False:
        return set()
    where = core.display_path(md_path)
    if not isinstance(value, (str, list, tuple)):
        raise SystemExit(f"{where}: pdfmd-options.{METADATA_APPEND_KEY} must be a key name or a list of them, not {value!r}")
    keys = {part.strip() for item in ([value] if isinstance(value, str) else value) for part in str(item).split(",") if part.strip()}
    for key in sorted(keys & set(METADATA_APPEND_BLOCKED)):
        raise SystemExit(f"{where}: pdfmd-options.{METADATA_APPEND_KEY} cannot name `{key}` (pdfmd lifts it into header files itself)")
    return keys


def metadata_joined(key: str, below, value, where: str) -> list:
    """What ``key`` holds after ``value`` is appended to ``below``: a list (a single value counts as a one-item list)."""
    for part in (below, value):
        if isinstance(part, dict):
            raise SystemExit(f"{where}: `{key}` holds a mapping, which cannot be appended to (only a value or a list can)")
    return [*([] if below is None else below if isinstance(below, list) else [below]),
            *([] if value is None else value if isinstance(value, list) else [value])]


def merge_metadata_layers(layers: list[tuple[dict, bool]], append_keys: set[str], where: str) -> dict:
    """The final value of every key an append touched, from ``layers`` (lowest first; the flag says the layer is the document's).
    In one layer `key:` is taken first and `key+:` appended after it. {} when nothing appends."""
    held: dict = {}
    touched: list[str] = []
    for mapping, is_document in layers:
        for key, value in mapping.items():
            if metadata_plus_key(key):
                continue
            if is_document and key in append_keys and key in held:
                held[key] = metadata_joined(key, held[key], value, where)
                touched.append(key)
            else:
                held[key] = value
        for key, value in mapping.items():
            if not metadata_plus_key(key):
                continue
            base = key[:-1]
            if base in METADATA_APPEND_BLOCKED:
                raise SystemExit(f"{where}: `{key}` is not supported (pdfmd lifts `{base}` into header files itself)")
            held[base] = metadata_joined(base, held.get(base), value, where)
            touched.append(base)
    return {key: held[key] for key in dict.fromkeys(touched)}


def metadata_layers(sources: list[Path], metadata_files: list[Path]) -> list[tuple[dict, bool]]:
    """The metadata a build reads, as layers, lowest first (see the comment above): the files in the order Pandoc gets them, then
    the front matter of each source."""
    layers: list[tuple[dict, bool]] = []
    for path in pandoc_metadata_order(list(metadata_files)):
        data = core.metadata_file_yaml(path)
        data.pop("pdfmd-options", None)
        layers.append((data, False))
    for source in sources:
        layers.append((core.front_matter_dict(core.read_text_best_effort(source)), True))
    return layers


def metadata_append_args(sources: Path | list[Path], metadata_files: list[Path], pandoc_options=(), no_auto=None) -> list[str]:
    """The metadata file with the finished values and ``--lua-filter metadata_append.lua``, only when some key appends; [] otherwise
    (every other build is untouched). Goes before every other filter."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or core.yaml is None:
        return []
    append = metadata_append_keys(files[0], metadata_files)
    layers = metadata_layers(files, metadata_files)
    merged = core.load_package("pdfmd_args").merged_cli_metadata(core, layers, append, core.display_path(files[0]), pandoc_options)
    merged.update(core.deferred("pdfmd_bibliography.sources", "merge_sources")(files, metadata_files, pandoc_options, no_auto))
    if not merged:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("metadata_append")
    if shipped is None:
        return []
    text = core.yaml.safe_dump({"pdfmd-merged": merged}, allow_unicode=True, sort_keys=False, width=1_000_000)
    target = core.cache_root() / "metadata" / f"{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.yaml"
    try:
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--metadata-file", str(target), "--lua-filter", str(shipped)]


def calc_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter calc.lua`` when a source has a `{=}` span or a `::: calc` div and `calc` is not off."""
    files = sources if isinstance(sources, list) else [sources]
    if not any(core.CALC_SPAN_RE.search(core.EMBED_BLOCK_RE.sub("", core.read_text_best_effort(file))) for file in files):
        return []
    if core.calc_is_off(files[0], metadata_files):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("calc")
    if shipped is None:
        return []
    arguments = ["-M", "pdfmd-calc-round=" + core.calc_round_mode(files[0], metadata_files)]
    digits = core.calc_digits_mode(files[0], metadata_files)
    if digits:
        arguments += ["-M", "pdfmd-calc-digits=" + digits]
    if core.calc_subs_on(files[0], metadata_files):
        arguments += ["-M", "pdfmd-calc-subs=true"]
    typeset = core.calc_typeset_mode(files[0], metadata_files)
    if typeset != "off":
        arguments += ["-M", "pdfmd-calc-typeset=" + typeset]
        for style, pieces in core.calc_typeset_styles(files[0], metadata_files).items():
            if pieces:
                arguments += ["-M", f"pdfmd-calc-typeset-{style}=" + ",".join(pieces)]
    noindent = core.calc_noindent_mode(files[0], metadata_files)
    if noindent != "off":
        arguments += ["-M", "pdfmd-calc-noindent=" + ("true" if noindent == "all" else noindent)]
    space = core.calc_space(files[0], metadata_files)
    if space:
        arguments += ["-M", "pdfmd-calc-space=" + space]
    if core.calc_align(files[0], metadata_files) == "center":
        arguments += ["-M", "pdfmd-calc-align=center"]
    constants = core.calc_constants_file(files[0], metadata_files)
    if constants is not None:
        arguments += ["-M", "pdfmd-calc-constants=" + "\n".join(core.calc_constants_statements(constants))]
    if core.CALC_SEED is not None and not core.BUILD.get("scanning"):
        arguments += ["-M", "pdfmd-calc-seed=" + str(core.CALC_SEED)]
    if core.CALC_BELOW is not None and not core.BUILD.get("scanning"):
        arguments += ["-M", "pdfmd-calc-below=" + str(core.CALC_BELOW)]
    if core.CALC_DUMP is not None and not core.BUILD.get("scanning"):
        arguments += ["-V", "pdfmd-calc-dump=" + str(core.CALC_DUMP)]
    return arguments + ["--lua-filter", str(shipped)]


def yaml_order(path: Path, fallback: int = 0) -> tuple[bool, Decimal | int]:
    match = re.search(r"^\s*yamlorder\s*:\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$",
                      path.read_text(encoding="utf-8-sig"), re.IGNORECASE | re.MULTILINE)
    if not match:
        return (False, fallback)
    return (True, Decimal(match.group(1)))


def order_metadata(paths: list[Path]) -> list[Path]:
    """Apply yamlorder where present while preserving explicit order otherwise."""
    if any(yaml_order(path)[0] for path in paths):
        return [path for _, path in sorted(
            enumerate(paths), key=lambda item: (
                yaml_order(item[1], item[0])[1], item[0]))]
    return paths


def resolve_yaml(directory: Path, value: str) -> Path:
    path = Path(value)
    candidates = [path]
    if not path.is_absolute():
        accessory = directory / core.ACCESSORY_DIRNAME
        candidates.append(Path.cwd() / path)
        candidates.append(directory / path)
        candidates.append(accessory / path)
        if not path.suffix:
            candidates.extend((Path.cwd() / path.with_suffix(".yaml"),
                               directory / path.with_suffix(".yaml"),
                               accessory / path.with_suffix(".yaml")))
    for candidate in candidates:
        if candidate.is_file():
            # Absolute: Pandoc runs inside the first metadata file's own
            # folder (pandoc_cwd), where a path relative to ours (`-y
            # cfg/x.yaml`) would no longer lead anywhere.
            return Path(os.path.abspath(candidate))
    raise FileNotFoundError(f"Metadata file not found: {value}")


def global_metadata_file() -> Path | None:
    """`metadata.yaml` beside the config file (`pdfmd --setup` writes it): metadata every document gets, below
    anything its own folder's metadata says. None when absent or the config is switched off."""
    config = core.config_path()
    candidate = None if config is None else config.with_name("metadata.yaml")
    return candidate if candidate is not None and candidate.is_file() else None


PRESET_OFF = ("none", "off", "false", "no")


PRESET_DEFAULT = ("default", "on", "true", "yes")


def presets_dir() -> Path | None:
    config = core.config_path()
    return None if config is None else config.with_name("presets")


def list_presets() -> list[Path]:
    folder = presets_dir()
    return sorted((item for item in folder.glob("*.y*ml") if item.suffix in (".yaml", ".yml")),
                  key=lambda item: item.name.casefold()) if folder is not None and folder.is_dir() else []


def preset_name(path: Path) -> str:
    return "default" if path.parent != presets_dir() else path.stem


def is_global_metadata(path) -> bool:
    """Whether ``path`` is pdfmd's global metadata (`metadata.yaml` beside the config file) or one of its presets."""
    config = core.config_path()
    if config is None or path is None:
        return False
    folder = Path(os.path.abspath(config.parent))
    where = Path(os.path.abspath(path))
    return ((where.parent == folder and where.name == "metadata.yaml")
            or (where.parent == folder / "presets" and where.suffix in (".yaml", ".yml")))


def preset_file(value: str, base: Path | None = None) -> Path | None:
    """The file a preset value names: `default`, a name in presets/ (with or without .yaml), or a path (relative to
    ``base``, the document's folder, else to the working folder). Stops with the names there are for one that is none."""
    name = str(value).strip()
    if name.casefold() in PRESET_DEFAULT:
        return global_metadata_file()
    folder = presets_dir()
    if folder is not None and not re.search(r"[/\\]", name) and not name.startswith("~"):
        for candidate in (name, f"{name}.yaml", f"{name}.yml"):
            if (folder / candidate).is_file():
                return folder / candidate
    else:
        path = Path(name).expanduser()
        for candidate in ([path] if path.is_absolute() else [(base or Path.cwd()) / path, Path.cwd() / path]):
            if candidate.is_file():
                return Path(os.path.abspath(candidate))
    known = ", ".join(preset_name(item) for item in list_presets()) or "none yet"
    raise SystemExit(f"unknown preset {name!r} (the presets/ folder beside the config file has: {known}; "
                     "`none` takes no global metadata; pdfmd --presets lists them)")


def presets_report(path: Path | None = None) -> bool:
    """`--presets [DOCUMENT]`: the global metadata files there are, and which one a build here would use."""
    config = core.config_path()
    if config is None:
        print("The config file is switched off (PDFMD_CONFIG is empty): there is no global metadata.")
        return False
    default = global_metadata_file()
    rows = [("default", default, "metadata.yaml" if default else "metadata.yaml (not there yet: pdfmd --setup writes it)")]
    rows += [(preset_name(item), item, f"presets/{item.name}") for item in list_presets()]
    document = Path(path) if path is not None and Path(path).is_file() else None
    try:
        local = find_local_metadata((document.parent if document else Path.cwd()).resolve(), None,
                                    document_stem=document.stem if document else None)
        local = [] if local is AUTO_METADATA_DISABLED or local is None else (local if isinstance(local, list) else [local])
        used = chosen_global_metadata(document, local)
    except (SystemExit, FileNotFoundError, ValueError) as error:
        print(f"WARN  {error}", file=sys.stderr)
        used = None
    for name, file, where in rows:
        keys = [("options" if key == "pdfmd-options" else key) for key in core.metadata_file_yaml(file)] if file else []
        shown = ", ".join(keys[:6]) + (f" +{len(keys) - 6}" if len(keys) > 6 else "")
        print(f"{'*' if used is not None and file is not None and file == used else ' '} {name:<14} {where}"
              + (f"  ({shown})" if shown else ""))
    print("  (* is the one a build here would use; none marked: no global metadata)" if used is None
          else "  (* is the one a build here would use)")
    return True


def chosen_global_metadata(document: Path | None, local_files: list[Path]) -> Path | None:
    """The global metadata file this document gets: None when it gets none. See the section above for the order."""
    def decide(preset, enabled):
        if enabled is False or (preset is not None and str(preset).strip().casefold() in PRESET_OFF):
            return False
        if preset is not None and str(preset).strip() and str(preset).strip().casefold() not in PRESET_DEFAULT:
            return preset_file(preset, document.parent if document is not None else None)
        return True if (preset is not None or enabled is not None) else None
    chosen = decide(core.PRESET_CLI, core.GLOBAL_METADATA_CLI)
    if chosen is None:
        try:
            if document is not None:
                preset = core.first_pdfmd_option(document, local_files, "preset")
                enabled = core.first_pdfmd_option(document, local_files, "global-metadata")
            else:
                preset, enabled = core.config_options().get("preset"), core.config_options().get("global-metadata")
        except (OSError, UnicodeDecodeError):            # a document that is not there (yet): the config alone decides
            preset, enabled = core.config_options().get("preset"), core.config_options().get("global-metadata")
        if isinstance(enabled, str):
            enabled = False if enabled.strip().casefold() in PRESET_OFF else True if enabled.strip().casefold() in PRESET_DEFAULT else None
        chosen = decide(preset, enabled if isinstance(enabled, bool) else None)
    if chosen is False:
        return None
    return chosen if isinstance(chosen, Path) else global_metadata_file()


METADATA_PRECEDENCES = ("later", "first")


def metadata_precedence() -> str:
    """Which of two metadata files wins a key both set (v3.27.22): `later` (the default, as Pandoc takes them) or
    `first`. From --metadata-precedence, else the config's `options.metadata-precedence` (pdfmd --setup). Not from a
    document or a metadata file: it decides how those are layered."""
    value = core.METADATA_PRECEDENCE_CLI
    if value is None:
        value = core.config_options().get("metadata-precedence")
    if value is None:
        return "later"
    mode = str(value).strip().casefold()
    if mode not in METADATA_PRECEDENCES:
        raise SystemExit(f"unknown metadata-precedence value {value!r}. Valid: {', '.join(METADATA_PRECEDENCES)}")
    return mode


def pandoc_metadata_order(metadata_files: list[Path]) -> list[Path]:
    """The metadata files in the order Pandoc gets them: the global metadata file first. Pandoc prefers a later
    --metadata-file, and the global file is the lowest in priority (v3.27.17; it came last and so beat the
    folder's own metadata.yaml). With `--metadata-precedence first` the others go in reverse, so that the first wins
    in Pandoc too (v3.27.22). The list itself keeps the global file last (Pandoc runs in the folder of its first
    entry); what pdfmd reads out of the files itself follows this order too (metadata_files_by_priority)."""
    KIT_METADATA = core.KIT_METADATA
    extra = next((path for path in metadata_files if is_global_metadata(path)), None)
    supplied = [path for path in metadata_files if path != extra and path in KIT_METADATA]            # a kit's defaults, in its order
    folders = [path for path in metadata_files if path != extra and path not in KIT_METADATA and core.is_folder_metadata(path)]       # nearest first
    parents, local = core.deferred("pdfmd_metadata", "parent_metadata_order")(metadata_files, extra)
    if len(local) > 1 and metadata_precedence() == "first":
        local.reverse()
    return [*([extra] if extra is not None else []), *supplied, *reversed(folders), *parents, *local]


def metadata_files_by_priority(metadata_files) -> list[Path]:
    """The metadata files, the one that wins first, for what pdfmd reads out of them itself (`pdfmd-options`, `margin`,
    the engine): the later file, as Pandoc takes it, then the earlier, the global metadata file (pdfmd --setup) last.
    Until v3.27.22 the first file won for pdfmd's keys while the later won for Pandoc's (a document-named YAML overrode
    metadata.yaml's margins but not its pdfmd-options)."""
    return list(reversed(pandoc_metadata_order(list(metadata_files))))


def find_metadata(directory: Path, requested: list[str] | None, report: bool = False,
                  document_class: str | None = None,
                  document_stem: str | None = None, document: Path | None = None,
                  discover: bool = True, kits: bool = True) -> Path | list[Path] | object | None:
    """Choose metadata files (see find_local_metadata), with the folders' and the global metadata file last when the files were
    found automatically (not named with -y). The global one is the lowest in priority: pandoc_metadata_order gives it to Pandoc
    first. ``discover=False`` (explicit-only) looks for no file beside the document but keeps the folders' and the global ones.
    The defaults of the kits chosen for the document (``kits``; entry 3du) come between the global file and the folders'."""
    found = find_local_metadata(directory, requested, report, document_class, document_stem) if discover else None
    extra, folders = None, []
    if requested is None and found is not AUTO_METADATA_DISABLED:
        extra = chosen_global_metadata(document, [found] if isinstance(found, Path) else list(found or []))
        folders = core.folder_metadata_files(str(directory.resolve()))          # the folders' own, between the files and the global
        found = core.deferred("pdfmd_metadata", "with_metadata_parents")(found, directory, document, report, document_class, document_stem, discover, folders, extra)
    supplied: list[Path] = []
    if kits and document is not None and found is not AUTO_METADATA_DISABLED:
        here = [*(found if isinstance(found, list) else [found] if found is not None else []), *folders,
                *([extra] if extra is not None else [])]
        supplied = core.kit_metadata_files(core.active_kits(document, here))
    if (extra is None and not folders and not supplied) or found is AUTO_METADATA_DISABLED:
        return found
    listed = [*(found if isinstance(found, list) else [found] if found is not None else []), *folders, *supplied,
              *([extra] if extra is not None else [])]
    return listed[0] if len(listed) == 1 else listed


def find_local_metadata(directory: Path, requested: list[str] | None, report: bool = False,
                        document_class: str | None = None,
                        document_stem: str | None = None, search_dirs: list[Path] | None = None) -> Path | list[Path] | object | None:
    """Choose metadata files, supporting explicit stacks and automatic discovery."""
    if requested == []:
        return AUTO_METADATA_DISABLED
    if search_dirs is None and requested is None and document_stem:
        unpacked = directory / f"{document_stem}{core.UNPACKED_SUFFIX}"
        unpacked_yaml = (sorted([*unpacked.glob("*.yaml"), *unpacked.glob("*.yml")],
                                key=lambda item: core.natural_key(item.name)) if unpacked.is_dir() else [])
        if unpacked_yaml:
            # The folder --unpack made for this document holds ITS metadata,
            # in the order it was merged in: nothing else is guessed at.
            return order_metadata(unpacked_yaml)
    search_dirs = core.accessory_directories(directory, document_stem) if search_dirs is None else search_dirs
    if requested is not None:
        if requested == ["all"]:
            candidates = [item for folder in search_dirs
                          for item in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml"))
                          if item.name.lower() != "defaults.yaml" and not core.is_package_helper_yaml(item)
                          and core.yaml_autoinclude(item)]
            return order_metadata(candidates)
        return order_metadata([resolve_yaml(directory, value) for value in requested])
    candidates = [item for folder in search_dirs
                  for item in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml"))
                  if item.name.lower() != "defaults.yaml" and not core.is_package_helper_yaml(item)
                          and core.yaml_autoinclude(item)]
    metadata = next((item for item in candidates if item.name.lower() == "metadata.yaml"), None)
    document_metadata = ([item for item in candidates
                          if document_stem and item.stem.casefold() == document_stem.casefold()]
                         if document_stem else [])
    if document_metadata:
        # metadata.yaml is the shared base; document-named YAML overrides it.
        selected = ([metadata] if metadata and metadata not in document_metadata else []) + document_metadata
        return order_metadata(selected)
    if report:
        preferred = next((item for item in candidates if item.name.lower() == "report.yaml"), None)
        preferred = preferred or next((item for item in candidates if item.name.lower() == "book.yaml"), None)
        if preferred:
            return order_metadata(([metadata] if metadata else []) + [preferred])
    if metadata:
        return metadata
    if document_class:
        matching = [item for item in candidates if item.stem.casefold() == document_class.casefold()]
        if len(matching) == 1:
            return matching[0]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(item.name for item in candidates)
        raise ValueError(f"Multiple YAML files found in {directory}: {names}; use -y FILE or bare -y")
    return None


def chapter_value(md_path: Path):
    """Read the scalar chapter value from a Markdown YAML header."""
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    match = re.search(r"^chapter\s*:\s*(.*?)\s*$", front_matter.group(1), re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip("'\"")
    return None if value.casefold() in {"", "null", "none", "exclude", "excluded"} else value


def has_chapter_field(md_path: Path) -> bool:
    return bool(re.search(r"^chapter\s*:", md_path.read_text(encoding="utf-8-sig"), re.MULTILINE))


def excluded_by_cli(md_path: Path, exclusions: list[str]) -> bool:
    candidates = {md_path.name.casefold(), md_path.stem.casefold(), str(md_path).casefold()}
    for exclusion in exclusions:
        value = Path(exclusion)
        names = {value.name.casefold(), value.stem.casefold(), str(value).casefold()}
        if candidates & names:
            return True
    return False


def report_sources(paths: list[Path], exclusions: list[str], exclude_unnumbered: bool = False,
                   recursive: bool = False, include_never: bool = False) -> tuple[list[Path], list[Path]]:
    # .resolve() for the same reason as find_markdown(): a relative directory
    # plus a file in a subdirectory would otherwise make Pandoc's cwd and its
    # source-file arguments both relative, and doubling up into a bad path.
    files = []
    for path in paths:
        if path.is_dir():
            files.extend(core.skip_never([file.resolve() for file in
                                     (path.rglob("*.md") if recursive else path.glob("*.md"))], include_never))
        elif path.is_file() and path.suffix.lower() == ".md":
            files.append(path.resolve())
    all_files = sorted(set(files))
    excluded = [file for file in all_files if chapter_value(file) is None and has_chapter_field(file)]
    excluded += [file for file in all_files if excluded_by_cli(file, exclusions) and file not in excluded]
    if exclude_unnumbered:
        excluded += [file for file in all_files
                     if file not in excluded and not has_chapter_field(file)]
    included = [file for file in all_files if file not in excluded]
    return sorted(included, key=core.chapter_order), excluded
