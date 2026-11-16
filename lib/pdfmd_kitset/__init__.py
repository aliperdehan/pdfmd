"""Which kits a build uses and what they add. Kit-code imports run only when needed.

Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_kitset`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

from pdfmd_base import core


KPSEWHICH_FOLDERS: dict[tuple, Path | None] = {}   # (package, the variables that steer TeX's search) -> its folder


def installed_package_folder(package: str) -> Path | None:
    """The folder of the installed `<package>.sty` that kpsewhich finds (through a symlink to its real folder), or None;
    one kpsewhich call per package and search path. Asked from an empty folder: from the document's own, TeX would answer
    with the lone copy this is looked up for."""
    key = (package, *(os.environ.get(name) for name in ("TEXINPUTS", "TEXMFHOME", "TEXMFLOCAL", "TEXMF")))
    if key not in KPSEWHICH_FOLDERS:
        with tempfile.TemporaryDirectory(prefix="pdfmd-kpse-") as empty:
            located = core.kpsewhich_locate([package + ".sty"], empty).get(package + ".sty")
        KPSEWHICH_FOLDERS[key] = located.resolve().parent if located else None
    return KPSEWHICH_FOLDERS[key]


KIT_CACHE_FILE = "kits.json"


def configured_kits() -> list[tuple[Path, dict]]:
    """(folder, {mode: [aliases]}) of each `kits:` entry of the config; a relative path is read from the config's folder."""
    raw = core.load_config().get("kits")
    if raw is None:
        return []
    config = core.config_path()
    found: list[tuple[Path, dict]] = []
    for entry in (raw if isinstance(raw, list) else [raw]):
        aliases: dict = {}
        if isinstance(entry, dict):
            aliases = entry.get("aliases") or {}
            entry = entry.get("path")
            if not isinstance(aliases, dict):
                print(f"WARN  config {config}: `aliases:` of a kits: entry must be a mapping of mode -> names; ignored",
                      file=sys.stderr)
                aliases = {}
        if not isinstance(entry, str) or not entry.strip():
            print(f"WARN  config {config}: an entry of `kits:` is a path (or a mapping with `path:`); skipped", file=sys.stderr)
            continue
        path = Path(os.path.expandvars(entry)).expanduser()
        if not path.is_absolute() and config is not None:
            path = config.parent / path
        found.append((path, aliases))
    return found


def kit_locations(base: Path | None = None, no_auto: list[str] | None = None, project: bool = True) -> list:
    """The folders a kit is searched in (pdfmd_kits.Location), in order."""
    from pdfmd_kits import Location
    base = (base or Path.cwd()).resolve()
    searching = not core.auto_disabled(no_auto, "kit")
    places = []
    if searching and project:
        places += [Location("a kits/ folder above the document", folder / "kits")
                   for folder in (base, *base.parents) if (folder / "kits").is_dir()]
    places += [Location("kits: in the config", path, aliases) for path, aliases in configured_kits() if path.is_dir()]
    config = core.config_path()
    if searching and config is not None and (config.parent / "kits").is_dir():
        places.append(Location("the kits/ folder beside the config file", config.parent / "kits"))
    return places


def kit_path_like(text: str) -> bool:
    """A kit reference that is a path, not a name: it has a separator or starts with `~` or `.`."""
    return "/" in text or "\\" in text or text.startswith(("~", "."))


def find_kit(reference: str, base: Path | None = None, no_auto: list[str] | None = None, named_only: bool = False):
    """pdfmd_kits.Found for a kit named by ``reference`` (a name, or a path to its folder or `.kit` file); raises
    pdfmd_kits.KitError when there is none, naming where it looked and the nearest names."""
    from pdfmd_kits import Found, KitError, find, list_kits
    from pdfmd_kits.discovery import kit_files
    base = (base or Path.cwd()).resolve()
    reference = str(reference).strip()
    if named_only and kit_path_like(reference):
        raise KitError(f"`{reference}` is a path, and a folder's `kit:` names a kit (a folder's options cannot name code); "
                       "register the kit under `kits:` of the config file, or select it by path in the document")
    if kit_path_like(reference):
        path = Path(os.path.expandvars(reference)).expanduser()
        path = Path(os.path.normpath(path if path.is_absolute() else base / path))
        files = [path] if path.is_file() else kit_files(path) if path.is_dir() else []
        if len(files) != 1:
            raise KitError(f"no kit at {core.display_path(path)}: a kit is a folder with a `.kit` file in it"
                           + (f" (it holds {len(files)})" if len(files) > 1 else ""))
        found = Found(files[0], "a path")
    else:
        searching = not core.auto_disabled(no_auto, "kit")
        lookup = core.installed_package_folder if searching and not core.auto_disabled(no_auto, "kpsewhich") else None
        locations = kit_locations(base, no_auto, project=not named_only)
        found = find(reference, locations, lookup, kit_cache() if lookup else None)
        if found is None:
            from difflib import get_close_matches
            from pdfmd_kits import normalise
            from pdfmd_kits.discovery import _declared_name
            known = {normalise(_declared_name(item.path) or item.path.parent.name): _declared_name(item.path) or item.path.parent.name
                     for item in list_kits(locations)}
            near = [known[key] for key in get_close_matches(normalise(reference), list(known), n=3, cutoff=0.6)]
            looked = [location.source for location in locations] + (["the TeX tree (kpsewhich)"] if lookup else [])
            raise KitError(f"no kit called `{reference}` (looked in: {', '.join(looked) or 'nowhere: --no-auto kit'})"
                           + (f"; did you mean {', '.join(near)}?" if near else "")
                           + "; a kit is a folder with a `.kit` file: name its folder in `kits:` of the config, or give its path")
    if core.VERBOSE_OUTPUT:
        print(f"AUTO KIT  {reference}: {core.display_path(found.path)} ({found.source}{', cached' if found.cached else ''})")
    return found


def kit_cache():
    from pdfmd_kits import Cache
    return Cache(core.cache_root() / KIT_CACHE_FILE)


KIT_METADATA: dict[Path, Path] = {}             # a metadata file a kit supplies -> that kit's folder


ACTIVE_KITS: dict[tuple, list] = {}             # the kits of one document in one run (the choice does not change mid-build)


class ActiveKit:
    """A kit chosen for a document: the loaded kit, its mode (or None), where it was found, and the selection behind it."""

    def __init__(self, kit, mode, found, selection):
        self.kit, self.mode, self.found, self.selection = kit, mode, found, selection

    def describe(self) -> str:
        return (f"{self.kit.name} {self.kit.version}".rstrip() + (f" mode {self.mode.name}" if self.mode else "")
                + f" (chosen in the {self.selection.layer or 'command line'})")


def set_kit_cli(values, stack_value) -> None:
    """--kit (repeatable; bare = no kit) and --kit-stack, read once at the start of a run."""
    core.KIT_CLI, core.KIT_STACK_CLI = None, None
    ACTIVE_KITS.clear()
    if values is None and stack_value is None:
        return                                                  # no kit asked for: the kit code is not even imported
    from pdfmd_kits import selection
    if values is not None:
        core.KIT_CLI = []
        for value in values:
            try:
                core.KIT_CLI += selection.parse(value, "command line") if value else [selection.OFF]
            except selection.SelectionError as error:
                raise SystemExit(f"--kit {value}: {error}")
    if stack_value is not None:
        try:
            selection.parse_stack_setting(stack_value)
        except selection.SelectionError as error:
            raise SystemExit(f"--kit-stack: {error}")
        core.KIT_STACK_CLI = stack_value


def kit_layer_selections(md_path: Path, metadata_files: list[Path]) -> dict[str, list]:
    """The `kit:` choices of each layer, parsed: {layer: [Selection]} (see pdfmd_kits.selection.LAYERS)."""
    layers: dict[str, list] = {name: [] for name in ("global", "preset", "folder", "document")}

    def add(layer: str, options, where: str) -> None:
        if isinstance(options, dict) and "kit" in options:
            from pdfmd_kits import selection
            try:
                layers[layer] += selection.parse(options["kit"], layer)
            except selection.SelectionError as error:
                raise SystemExit(f"{where}: kit: {error}")

    add("global", core.config_options(), "the config file")
    others = [path for path in metadata_files if path not in KIT_METADATA and not core.is_folder_metadata(path)]
    for path in others:
        if core.is_global_metadata(path):
            add("preset", core.metadata_file_yaml(path).get("pdfmd-options"), str(path))
    for directory, data, metadata in reversed(core.folder_walk(str(md_path.resolve().parent))):
        if data is not None:
            add("folder", data.get("options"), str(directory / "config.yaml"))
        if metadata is not None:
            add("folder", core.metadata_file_yaml(metadata).get("pdfmd-options"), str(metadata))
    for path in core.pandoc_metadata_order(others):
        if not core.is_global_metadata(path):
            add("document", core.metadata_file_yaml(path).get("pdfmd-options"), str(path))
    add("document", core.frontmatter_pdfmd_options(md_path), str(md_path))
    return layers


def active_kits(md_path: Path | None, metadata_files: list[Path] | None = None, no_auto: list[str] | None = None) -> list:
    """The kits chosen for this document (ActiveKit, in stack order); [] when nothing selects one. Search is not selection:
    a document that merely loads a kit's package gets none. Costs nothing for a document no layer gives a `kit:`."""
    if md_path is None or core.yaml is None:
        return []
    # of --no-auto only the searching of kits matters here (find_kit): a kit's own `no-auto:` changes the list a build uses
    # afterwards, and must not make the same choice be made, and warned about, twice
    key = (str(md_path.resolve()), (core.auto_disabled(no_auto, "kit"), core.auto_disabled(no_auto, "kpsewhich")),
           len(core.KIT_CLI) if core.KIT_CLI is not None else -1)
    if key in ACTIVE_KITS:
        return ACTIVE_KITS[key]
    ACTIVE_KITS[key] = []
    try:
        return _active_kits(md_path, metadata_files, no_auto, key)
    except BaseException:
        ACTIVE_KITS.pop(key, None)
        raise


def _active_kits(md_path: Path, metadata_files: list[Path] | None, no_auto: list[str] | None, key: tuple) -> list:
    if metadata_files is None:
        try:
            found = core.find_metadata(md_path.parent, None, document_stem=md_path.stem, document=md_path, kits=False)
        except (OSError, ValueError, SystemExit):
            found = None
        metadata_files = [] if found is None or found is core.AUTO_METADATA_DISABLED else (found if isinstance(found, list) else [found])
    layers = kit_layer_selections(md_path, list(metadata_files))
    if not any(layers.values()) and core.KIT_CLI is None:
        return ACTIVE_KITS[key]
    from pdfmd_kits import KitError, load_kit, resolve_mode, selection
    try:
        setting = selection.parse_stack_setting(
            core.KIT_STACK_CLI if core.KIT_STACK_CLI is not None else core.first_pdfmd_option(
                md_path, [path for path in metadata_files if path not in KIT_METADATA], "kit-stack"))
    except selection.SelectionError as error:
        raise SystemExit(str(error))
    resolved = []
    for choice in selection.combine(layers, core.KIT_CLI, setting):
        try:
            found = find_kit(choice.ref, md_path.parent, no_auto, named_only=choice.layer == "folder")
            kit = load_kit(found.path, found.aliases)
            mode = resolve_mode(kit, choice.mode)
        except KitError as error:
            raise SystemExit(f"{md_path.name}: kit `{choice.ref}` (chosen in the {choice.layer}): {error}")
        for warning in kit.warnings:
            print(f"WARN  {warning}", file=sys.stderr)
        resolved.append(ActiveKit(kit, mode, found, choice))
        if core.VERBOSE_OUTPUT and choice.layer == "command line":        # a KIT line with its file and how to read about it (v3.33.72)
            line = selection.command_line_line(resolved[-1].describe(), kit.name, core.display_path(kit.path))
            if line:
                print(line)
        elif core.VERBOSE_OUTPUT:
            print(f"AUTO KIT  {resolved[-1].describe()}")
    ACTIVE_KITS[key] = resolved
    return resolved


def kit_overlay(kit, label: str, mapping: dict) -> Path | None:
    """The kit's inline default metadata as a metadata file in the cache folder (named by its content, written once)."""
    if not mapping or core.yaml is None:
        return None
    text = core.yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False)
    from pdfmd_kits import normalise
    path = core.cache_root() / "kit-metadata" / f"{normalise(kit.name)}-{label}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}.yaml"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, path)
    except OSError as error:
        print(f"WARN  kit {kit.name}: cannot write its default metadata to {path} ({error.strerror or error}); left out", file=sys.stderr)
        return None
    return path


def kit_metadata_files(kits: list) -> list[Path]:
    """The metadata files the kits supply, lowest first: for each kit its defaults, its inline metadata, its mode's defaults, its
    mode's metadata. Each is remembered in KIT_METADATA with the kit's folder."""
    files: list[Path] = []
    for item in kits:
        kit, mode = item.kit, item.mode
        parts = [*kit.defaults, kit_overlay(kit, "kit", kit.metadata),
                 *(mode.defaults if mode else ()), kit_overlay(kit, "mode", mode.metadata if mode else {})]
        for path in parts:
            if path is not None and path not in files:
                KIT_METADATA[path] = kit.folder
                files.append(path)
    return files


KIT_HEADER_PREFIX = "pdfmd-kit-"


def kit_preamble_kits(document: Path | None, metadata_files: list[Path] | None) -> list:
    return [item for item in active_kits(document, metadata_files, None)
            if item.kit.package or item.kit.latex or (item.mode is not None and item.mode.latex)]


def kit_writes_preamble(document: Path | None, metadata_files: list[Path] | None) -> bool:
    return bool(document is not None and kit_preamble_kits(document, metadata_files))


def header_argument_positions(cmd: list[str]) -> list[tuple[int, bool]]:
    """(index of the file, whether it is the `--include-in-header=FILE` form) of each header file of ``cmd``."""
    found = []
    for index, item in enumerate(cmd):
        if item in ("-H", "--include-in-header") and index + 1 < len(cmd):
            found.append((index + 1, False))
        elif item.startswith("--include-in-header="):
            found.append((index, True))
    return found


def kit_explicit_sources(document: Path, paths: list[Path], pandoc_options: list[str],
                         metadata_files: list[Path] = ()) -> list[bool]:
    """For each of ``paths`` (header files of a build): whether it was asked for (`-H`, a named `preamble:`), not found by
    discovery. A found one yields to the kit where they contradict; an explicit one stops the build."""
    auto = {path.resolve() for path in ([] if core.has_header_include_option(pandoc_options) else
                                        core.find_preambles(document.parent, document.stem, []))}
    named = {path.resolve() for path in core.frontmatter_extra_preambles(document, metadata_files)}
    flags = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        flags.append(resolved not in auto or resolved in named)
    return flags


def kit_embedded_preambles(document: Path, metadata_files: list[Path], preamble_files: list[Path] | None) -> list[Path]:
    """The preamble files an assembled or attached source embeds: when a kit writes part of the preamble, the kit's header file
    first and then the found preambles as the build read them (what the kit writes twice settled in them), so a rebuild that
    has no kit gets the same LaTeX in the same order. ``preamble_files`` unchanged when no kit writes a preamble."""
    files = list(preamble_files or [])
    if any(path.name.startswith(KIT_HEADER_PREFIX) for path in files):
        return files
    kits = kit_preamble_kits(document, metadata_files)
    if not kits:
        return files
    explicit = kit_explicit_sources(document, files, [], metadata_files)
    body, texts, _ = core.kit_header_settle(document, kits, [(path, core.display_path(path), flag) for path, flag in zip(files, explicit)])
    settled = [core.kit_cache_tex(f"kit-{path.stem}-", text, 12) if text != core.read_text_best_effort(path) else path
               for path, text in zip(files, texts)]
    return [core.kit_cache_tex(KIT_HEADER_PREFIX, body, 16), *settled]


def package_helper(folder: Path, package: str, no_auto: list[str] | None = None, document: Path | None = None) -> tuple[dict, Path] | None:
    """What a package tells pdfmd about itself: `<package>-pdfmd.yaml` beside its `.sty`, else the same file
    (or a plain `pdfmd.yaml`) in a `pdfmd/` folder there; (its mapping, its path) or None. Keys: `latex-keys:`
    (front-matter key -> the macro it fills), `office:` (defaults of a Word/ODT build, as `<package>-office.yaml`), `lua:` (Lua
    filters besides `<package>.lua`), `draft-skip:` (`commands:`, `spans:` a draft pass need not draw) and `picture-cache:`
    (the names the package uses for the picture cache's protocol).

    The `.sty` that wins may be a lone copy beside the document (TeX's own order), which carries no helper file, and its
    `latex-keys:` would be lost without a word (v3.31.29): the same file is then looked for beside the `.sty` of a selected
    kit, then of the installed copy kpsewhich finds; the path returned is the one that gave it. `--no-auto kit` and
    `--no-auto kpsewhich` (bare `--no-auto` too) take those places off."""
    found = core.read_package_helper(folder, package)
    if found or core.yaml is None:
        return found
    others: list[Path] = [] if core.auto_disabled(no_auto, "kit") else core.kit_package_folders(package, document)
    if not core.auto_disabled(no_auto, "kpsewhich"):
        installed = core.installed_package_folder(package)
        if installed:
            others.append(installed)
    for other in others:
        if other != folder.resolve():
            found = core.read_package_helper(other, package)
            if found:
                return found
    return None


def header_includes_texts(md_path: Path, metadata_files: list[Path]) -> list[str]:
    """The LaTeX a document gets from `header-includes:` -- its own front matter's and its metadata files' (a package may
    be loaded there instead of in a preamble file: a pre-lab's metadata does that)."""
    texts: list[str] = []

    def collect(value) -> None:
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    for item in metadata_files:
        collect(core.metadata_file_yaml(item).get("header-includes"))
    try:
        own = core.document_header_includes(md_path.read_text(encoding="utf-8-sig"))
    except OSError:
        own = None
    if own:
        texts.append(own)
    return texts


def office_packages(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None = None
                    ) -> list[tuple[Path, str, list[str]]]:
    """(folder, package name) of each LaTeX package the document's preamble loads that is not part of the TeX
    distribution: a package may ship its Word support beside its .sty (`<name>-office.lua`,
    `<name>-office.yaml`, `<name>-reference.dotx`), found here."""
    chosen = [(item.kit.folder, item.kit.package, list(item.mode.options) if item.mode else [])
              for item in active_kits(md_path, metadata_files, None) if item.kit.package]
    if core.discovery_disabled(no_auto, "preamble"):
        return chosen
    texts = []
    for item in core.find_preambles(md_path.parent, md_path.stem, []):
        try:
            texts.append(item.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    texts += header_includes_texts(md_path, metadata_files)
    loaded: list[tuple[str, list[str]]] = []
    for match in re.finditer(r"\\(?:usepackage|RequirePackage)(?:\[([^\]]*)\])?\{([^}]+)\}", "\n".join(texts)):
        options = [part.strip() for part in (match.group(1) or "").split(",") if part.strip()]
        loaded += [(part.strip(), options) for part in match.group(2).split(",") if part.strip()]
    located = core.kpsewhich_locate(sorted({package + ".sty" for package, _ in loaded}))
    # beside the document first, as TeX itself looks (a restored source carries its package there)
    here = [md_path.parent, *(item.parent for item in metadata_files), md_path.parent / core.ACCESSORY_DIRNAME]
    found: list[tuple[Path, str, list[str]]] = []
    for package, options in loaded:
        path = next((folder / f"{package}.sty" for folder in here if (folder / f"{package}.sty").is_file()),
                    located.get(package + ".sty"))
        if path and "texmf-dist" not in str(path) and "/texlive/" not in str(path):
            folder = path.resolve().parent
            if not any(item[0] == folder and item[1] == package for item in found):
                found.append((folder, package, options))
    for entry in chosen:                                       # a kit loads its package itself; a copy the preamble resolved stands
        if not any(item[1] == entry[1] for item in found):
            found.append(entry)
    return found
