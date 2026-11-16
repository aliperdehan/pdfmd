"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_config.auto`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import sys
from pathlib import Path

from pdfmd_base import core


# Auto-discovered yaml/tex/lua files may live directly beside the document
# (the original convention) or inside this subdirectory instead, so a
# report's own top-level folder can hold just its .md source and rendered
# output -- everything else (metadata.yaml, a shared .bib/.csl a metadata.yaml
# points at, preamble.tex, lua filters, and anything a preamble's own raw
# LaTeX \input pulls in relative to pandoc's cwd -- see resource_path_option's
# docstring) can sit out of sight together. See accessory_directories().
ACCESSORY_DIRNAME = "metadata"


# `NAME.unpacked/`, the folder --unpack writes beside NAME.md: an accessory
# folder for that one document, searched like `metadata/` is (see
# accessory_directories). Every .lua in it applies -- the folder is made by
# pdfmd for this document alone, unlike a shared folder where only fixed
# names are trusted (find_lua_filters).
UNPACKED_SUFFIX = ".unpacked"


# --no-auto KIND values, and its "font" shorthand for both font kinds at
# once. See build_parser()'s --no-auto help text for what each kind does.
NO_AUTO_KINDS = frozenset({
    "reader", "title", "margin", "mainfont", "monofont", "font", "tablewidth",
    "metadata", "yaml", "preamble", "tex", "lua", "files", "standalone",
    "texdirect", "officedirect", "crossref", "citationengine", "csvtable",
    "papersize", "parts", "lookup", "unicode", "officeref", "officestyle", "officelatex", "officeprofile",
    "codewrap", "typstdirect", "htmldirect", "svg", "remoteimages", "pdfimages", "diagrams", "texpackages",
    "smiles", "draftpictures", "remotecsl", "mathfont", "css", "mathjax", "kit", "kpsewhich",
    "priority", "bib",
})


NO_AUTO_ALIASES = {
    "font": frozenset({"mainfont", "monofont", "mathfont"}),
    "yaml": frozenset({"metadata"}),
    "tex": frozenset({"preamble"}),
    "files": frozenset({"metadata", "preamble", "lua"}),
}


def auto_disabled(no_auto: list[str] | None, kind: str) -> bool:
    """Return whether --no-auto turns off one of pdfmd's own defaults.

    ``no_auto`` is args.no_auto: None (flag absent) never disables anything;
    ``[]`` (bare --no-auto) disables everything; a non-empty list disables
    only the named kinds (expanding the "font" alias to mainfont+monofont).
    """
    if no_auto is None:
        return False
    if not no_auto:
        return True
    return kind in no_auto or any(kind in NO_AUTO_ALIASES.get(item, ()) for item in no_auto)


def accessory_directories(directory: Path, stem: str | None = None) -> list[Path]:
    """Return `directory`, plus its ACCESSORY_DIRNAME subdirectory if present,
    plus (given the document's ``stem``) the ``STEM.unpacked`` folder
    --unpack writes (see unpacked_directory()).

    Every filename-based auto-discovery (metadata YAML, preambles, Lua
    filters) searches both: a document's own directory (files placed
    directly beside it, the original convention) and, when it exists, a
    metadata/ subfolder holding the same kind of files, so a report's own
    top-level folder can hold nothing but its .md source and rendered
    output. Checked fresh on every call rather than cached -- cheap, and a
    directory created between calls (unlikely, but free to support this way)
    is picked up.
    """
    accessory = directory / ACCESSORY_DIRNAME
    found = [directory, accessory] if accessory.is_dir() else [directory]
    if stem:
        unpacked = directory / f"{stem}{UNPACKED_SUFFIX}"
        if unpacked.is_dir():
            found.append(unpacked)
    return found


EXPLICIT_PREFIX = "explicit:"


EXPLICIT_KINDS = frozenset({"lua", "preamble", "tex", "metadata", "yaml", "files", "bib"})


AUTO_STATES = {"on": "on", "true": "on", "yes": "on", "off": "off", "false": "off", "no": "off",
               "explicit-only": "explicit", "explicit": "explicit", "named": "explicit"}


def auto_expand(kind: str) -> set[str]:
    return set(NO_AUTO_ALIASES.get(kind, {kind}))


def discovery_disabled(no_auto: list[str] | None, kind: str) -> bool:
    """Whether pdfmd may not LOOK for files of this kind: off (auto_disabled), or explicit-only. What the document names is
    asked of auto_disabled alone."""
    if auto_disabled(no_auto, kind):
        return True
    for item in no_auto or ():
        if item.startswith(EXPLICIT_PREFIX) and kind in auto_expand(item[len(EXPLICIT_PREFIX):]):
            return True
    return False


CODE_KINDS = frozenset({"lua", "preamble"})


def folder_auto_safe(options: dict, where: str) -> dict:
    """A folder's `auto:` without the `on` of a kind that finds code (lua, preamble, and the aliases files and tex that cover them):
    a folder you did not write must not run what you switched off in your config or your document. Off and explicit-only,
    which only tighten, stay."""
    mapping = options.get("auto")
    if not isinstance(mapping, dict):
        return options
    kept = {}
    for kind, value in mapping.items():
        if (AUTO_STATES.get(str(value).strip().casefold()) == "on" and str(kind) in NO_AUTO_KINDS
                and auto_expand(str(kind)) & CODE_KINDS):
            if f"{where}:{kind}" not in core.FOLDER_WARNED:
                core.FOLDER_WARNED.add(f"{where}:{kind}")
                print(f"WARN  {where}: auto: {kind}: on cannot be set by a folder (it finds code); ignored", file=sys.stderr)
            continue
        kept[kind] = value
    return {**options, "auto": kept}


def auto_layer(options: dict, where) -> tuple[bool, dict[str, str]]:
    """(whether the layer switches everything off, {kind: "on" | "off" | "explicit"}) as one layer of options says it."""
    everything, states = False, {}
    listed = core.no_auto_from_value(options.get("no-auto"))
    if listed == []:
        everything = True
    for item in listed or ():
        if item.startswith(EXPLICIT_PREFIX):
            name, state = item[len(EXPLICIT_PREFIX):], "explicit"
        else:
            name, state = item, "off"
        if name not in NO_AUTO_KINDS:
            raise SystemExit(f"{where}: unknown pdfmd-options.no-auto kind(s): {name}. Valid: {', '.join(sorted(NO_AUTO_KINDS))}")
        if state == "explicit" and name not in EXPLICIT_KINDS:
            raise SystemExit(f"{where}: {item}: explicit-only is for {', '.join(sorted(EXPLICIT_KINDS))}")
        for member in auto_expand(name):
            states[member] = state
    mapping = options.get("auto")
    if mapping is not None:
        if not isinstance(mapping, dict):
            raise SystemExit(f"{where}: pdfmd-options.auto must be a mapping of kinds to on, explicit-only or off, not {mapping!r}")
        for kind, value in mapping.items():
            name, state = str(kind), AUTO_STATES.get(str(value).strip().casefold())
            if name not in NO_AUTO_KINDS:
                raise SystemExit(f"{where}: unknown pdfmd-options.auto kind {name}. Valid: {', '.join(sorted(NO_AUTO_KINDS))}")
            if state is None:
                raise SystemExit(f"{where}: pdfmd-options.auto.{name} is {value!r}: on, explicit-only or off")
            if state == "explicit" and name not in EXPLICIT_KINDS:
                raise SystemExit(f"{where}: pdfmd-options.auto.{name}: explicit-only is for {', '.join(sorted(EXPLICIT_KINDS))}: "
                                 f"{name} has no file a document could name")
            for member in auto_expand(name):
                states[member] = state
    return everything, states


AUTO_STRICTNESS = {"on": 0, "explicit": 1, "off": 2}


def auto_states(layers: list[tuple[object, dict]]) -> tuple[dict[str, str], bool]:
    """({kind: state} the layers decide, strongest first, and whether a layer switched everything off): a kind is decided by the
    first layer that names it, and a layer that switches everything off decides every kind no stronger layer named."""
    decided: dict[str, str] = {}
    blanket = False
    for where, options in layers:
        everything, states = auto_layer(options, where)
        if not blanket:
            for kind, state in states.items():
                decided.setdefault(kind, state)
            blanket = everything
    return decided, blanket


def resolve_auto(layers: list[tuple[object, dict]], folders: int = 0) -> list[str] | None:
    """The kinds that are off (and `explicit:KIND` for the explicit-only ones) after the layers, strongest first. ``folders`` is
    how many of the layers after the first two (command line, document) are folders': for what finds code (CODE_KINDS) a folder
    only ever tightens: the state is the strictest of the layers that are not a folder's and of every folder's, unless the command
    line or the document says it."""
    decided, blanket = auto_states(layers)
    if folders:
        strong, strong_blanket = auto_states(layers[:2])
        without, without_blanket = auto_states([*layers[:2], *layers[2 + folders:]])
        for kind in CODE_KINDS:
            if kind in strong or strong_blanket:
                continue
            states = [without.get(kind, "off" if without_blanket else "on")]
            for layer in layers[2:2 + folders]:
                named, everything = auto_states([layer])
                states.append(named.get(kind, "off" if everything else "on"))
            decided[kind] = max(states, key=AUTO_STRICTNESS.get)
    if blanket:
        for kind in NO_AUTO_KINDS - NO_AUTO_ALIASES.keys():
            decided.setdefault(kind, "off")
        if all(state == "off" for state in decided.values()):
            return []
    off = sorted(kind for kind, state in decided.items() if state == "off")
    explicit = sorted(EXPLICIT_PREFIX + kind for kind, state in decided.items() if state == "explicit")
    return [*off, *explicit] or None


def effective_no_auto(md_path: Path, cli_no_auto: list[str] | None, kit_kinds: list[str] | None = None) -> list[str] | None:
    """What is switched off for a document, from the layers described above. The one place this logic lives -- both
    convert_one and main()'s pre-discovery gating (metadata/preamble auto-discovery happens before convert_one is even
    called) need the same answer for the same file. ``kit_kinds`` (v3.32.8) are what the chosen kits' `no-auto:` switch off: a
    layer under the command line, the document and the folders and above the config, where a kit's own metadata sits. Only
    the callers that know the kit pass it (the kit is chosen from these very layers, so the first answer cannot include it)."""
    own = dict(core.frontmatter_pdfmd_options(md_path))
    if "no-auto" not in own:
        assembled = core.frontmatter_no_auto(md_path)             # an assembled file keeps its kinds in the comment form of its marker
        if assembled is not None:
            own["no-auto"] = assembled or True
    layers: list[tuple[object, dict]] = []
    if cli_no_auto is not None:
        layers.append((md_path, {"no-auto": cli_no_auto or True}))
    layers.append((md_path, own))
    if cli_no_auto is None:
        layers.insert(0, (md_path, {}))                  # the command line's place is always the first
    above = [(folder, folder_auto_safe(options, folder)) for folder, options in core.folder_layers(md_path)]
    layers.extend(above)
    if kit_kinds:
        layers.append(("kit", {"no-auto": list(kit_kinds)}))
    layers.append(("config", core.config_options()))
    return resolve_auto(layers, len(above))


def kit_no_auto_kinds(md_path: Path, metadata_files: list[Path] | None, no_auto: list[str] | None) -> list[str]:
    """The pdfmd defaults the chosen kits switch off with `no-auto:` (v3.32.8), for effective_no_auto's ``kit_kinds``."""
    kinds: list[str] = []
    for item in core.active_kits(md_path, metadata_files, no_auto):
        for kind in item.kit.no_auto:
            if kind not in kinds:
                kinds.append(kind)
    if kinds and core.VERBOSE_OUTPUT:
        print(f"AUTO KIT  switches off {', '.join(kinds)} (no-auto in the kit)")
    return kinds
