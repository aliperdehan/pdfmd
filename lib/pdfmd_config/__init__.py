"""Global and folder configuration helpers; automatic discovery lives in pdfmd_config.auto."""

from __future__ import annotations
from pathlib import Path
from functools import lru_cache
import os
import re
import sys
from pdfmd_base import core
from pdfmd_base import spelling


def frontmatter_no_auto(md_path: Path) -> list[str] | None:
    """Read ``pdfmd-options:\n  no-auto: ...`` from a document's own front
    matter, in any of the shapes --no-auto itself accepts: a boolean
    (``true``/``yes``/``on``/``all`` disables everything, ``false`` leaves
    pdfmd's defaults alone), a bare kind name, or a YAML list of kinds.
    """
    value = core.frontmatter_pdfmd_options(md_path).get("no-auto")
    if value is None:
        # An assembled file with no front matter keeps its kinds in the
        # comment form of its marker (see ASSEMBLED_COMMENT_RE).
        if md_path.suffix.lower() in (".md", ".markdown"):
            try:
                ASSEMBLED_COMMENT_RE = core.ASSEMBLED_COMMENT_RE
                found = ASSEMBLED_COMMENT_RE.search(
                    core.mask_embedded_blocks(md_path.read_text(encoding="utf-8-sig")))
            except (OSError, UnicodeDecodeError):
                found = None
            if found and found.group("kinds"):
                return found.group("kinds").split(",")
        return None
    return no_auto_from_value(value)


def no_auto_from_value(value) -> list[str] | None:
    """A `no-auto` setting in any of its shapes (document, config file): True/"all" -> [] (everything off),
    a kind name, or a list of kinds; None when nothing is switched off."""
    if isinstance(value, bool):
        return [] if value else None
    if isinstance(value, str):
        if value.casefold() in {"true", "yes", "on", "all"}:
            return []
        if value.casefold() in {"false", "no", "off"}:
            return None
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return None


def has_embedded_preamble(md_path: Path) -> bool:
    """Whether an assembled file carries its preamble inside `header-includes`
    (--embed-metadata preamble). The front-matter macros a package expects
    (package_latex_keys) are only emitted when a preamble exists, and one
    embedded there counts as one."""
    kinds = core.frontmatter_pdfmd_options(md_path).get("embedded")
    return isinstance(kinds, list) and "preamble" in kinds


def scalar_text(value) -> str:
    """A front-matter value as one line of plain text ('' when absent)."""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return " ".join(str(value).split())


def split_front_matter(text: str) -> tuple[dict, str]:
    """(front-matter mapping, body). {} when there is none or it will not parse."""
    match = re.match(r"^---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if not match:
        return {}, text
    body = text[match.end():]
    if core.yaml is None:
        return {}, body
    try:
        data = core.yaml.safe_load(match.group(1))
    except core.yaml.YAMLError:
        return {}, body
    return (data if isinstance(data, dict) else {}), body


def data_root() -> Path:
    """Where pdfmd keeps tools it installs itself (a sibling of cache_root())."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "pdfmd"


CONFIG_FILENAME = "config.yaml"


CONFIG_KEYS = ("translit", "options", "setup-ui", "disabled", "kits")


CONFIG_TEMPLATE = """# pdfmd's global config. Everything is optional; delete a line to get the built-in default back.
# Precedence: command line > document > metadata files > folder settings > per-install config > user config.

# Romanization packs for finding a document by a name typed in Latin letters
# (greek armenian georgian hebrew arabic hangul kana han other; Cyrillic is always on).
# translit: [greek, hangul]

# Defaults for the `pdfmd-options:` of every document.
options:
  # What to do about characters the main font cannot draw:
  #   char      set just those characters in another installed font
  #   word      set the whole word in another font, so no word mixes fonts (default); it sees literal
  #             characters only: a missing glyph that comes from a TeX command (`\\geq` in text mode) still
  #             rebuilds the whole document in DejaVu Serif, with a WARN naming the font and the code points
  #   document  use the one installed font that draws most of the document as the main font
  #   off       nothing: what Pandoc and TeX do without pdfmd (missing glyphs vanish or print boxes)
  #   box       no fallback; each missing character is drawn as a black box
  #   error     no fallback; the build fails, listing the missing characters
  # fallback: word
  # What to do about characters no installed font draws (after the fallback): warn, box or error.
  # missing: warn
  # pdf-engine: lualatex
  # cache: {aux: true, location: global}   # location: global (~/.cache/pdfmd) or document (.cache/pdfmd beside it)
"""


def config_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "pdfmd"


def config_path() -> Path | None:
    override = os.environ.get("PDFMD_CONFIG")
    if override:
        return Path(override).expanduser() if override.strip() else None
    return core.config_root() / CONFIG_FILENAME


def install_config_path() -> Path:
    return Path(sys.prefix) / "etc" / "pdfmd" / CONFIG_FILENAME


def read_config(path: Path | None) -> dict:
    """Read one config file, warning when it cannot be read."""
    if path is None or core.yaml is None or not path.is_file():
        return {}
    try:
        data = core.yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, core.yaml.YAMLError) as error:
        print(f"WARN  config {path}: cannot be read ({error}); ignoring it", file=sys.stderr)
        return {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        print(f"WARN  config {path}: expected a mapping of settings; ignoring it", file=sys.stderr)
        return {}
    unknown = sorted(str(key) for key in set(data) - set(CONFIG_KEYS))
    if unknown:
        print(f"WARN  config {path}: unknown setting{'s' if len(unknown) > 1 else ''} "
              f"{', '.join(unknown)} (known: {', '.join(CONFIG_KEYS)}); `options:` holds pdfmd-options",
              file=sys.stderr)
    return data


@lru_cache(maxsize=None)
def _global_config() -> tuple[list[tuple[str, Path, dict]], dict]:
    layers = []
    install = install_config_path()
    user = core.config_path()
    if install.is_file():
        layers.append(("per-install", install, read_config(install)))
    if user is not None and not (layers and install == user):
        layers.append(("user", user, read_config(user)))
    merged = {}
    for _, _, data in reversed(layers):
        merged = merge_options(merged, data)
    return layers, merged


def global_config_layers() -> list[tuple[str, Path, dict]]:
    """The global configuration files, strongest first, with their unmixed settings."""
    return _global_config()[0]


def load_config() -> dict:
    """The effective global config, with per-install settings winning over the user file."""
    return _global_config()[1]


load_config.cache_clear = _global_config.cache_clear


def global_option_layers() -> list[tuple[str, Path, dict]]:
    return [(layer, path, data["options"]) for layer, path, data in global_config_layers()
            if isinstance(data.get("options"), dict)]


def merge_options(base: dict, layer: dict) -> dict:
    """``layer`` over ``base``: a mapping on both sides is merged field by field, anything else is the layer's."""
    merged = dict(base)
    for key, value in layer.items():
        merged[key] = merge_options(merged[key], value) if isinstance(value, dict) and isinstance(merged.get(key), dict) else value
    return merged


FOLDER_CODE_KEYS = (("office", "profile"),)         # a Lua file that runs in the Word route: a folder cannot name one


def folder_options_safe(path: str, options: dict) -> dict:
    """A folder layer's options without what names code (FOLDER_CODE_KEYS), said once."""
    for outer, inner in FOLDER_CODE_KEYS:
        if isinstance(options.get(outer), dict) and inner in options[outer]:
            if f"{path}:{outer}.{inner}" not in FOLDER_WARNED:
                FOLDER_WARNED.add(f"{path}:{outer}.{inner}")
                print(f"WARN  {path}: {outer}.{inner} names code and cannot be set by a folder; ignored", file=sys.stderr)
            options = {**options, outer: {key: value for key, value in options[outer].items() if key != inner}}
    return options


def config_options(md_path: Path | None = None) -> dict:
    """`options:` of the config file: defaults for every document's ``pdfmd-options``. With a document, the `options:` of the
    folder settings above it lie over them (v3.29.29; the nearest folder wins)."""
    options = core.load_config().get("options")
    options = options if isinstance(options, dict) else {}
    if md_path is None:
        return options
    try:
        layers = folder_layer_files(str(Path(md_path).resolve().parent))
    except OSError:
        return options
    for path, folder_options in reversed(layers):
        options = merge_options(options, folder_options_safe(path, folder_options))
    return options


def config_report(init: bool = False, document: Path | None = None, no_auto=None, metadata_request=None) -> bool:
    """--show-config / --init-config."""
    path = core.config_path()
    if path is None and init:
        print("The config file is switched off (PDFMD_CONFIG contains only whitespace).")
        return True
    if init:
        if path.exists():
            print(f"{path} exists already; left alone.")
        else:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                core.atomic_write_text(path, CONFIG_TEMPLATE)
            except OSError as error:
                print(f"Could not write {path}: {error}", file=sys.stderr)
                return False
            print(f"Wrote {path} (every setting is commented out; edit it).")
        return True
    if path is None:
        print("The user config file is switched off (PDFMD_CONFIG contains only whitespace).")
    for layer, file, data in global_config_layers():
        state = 'present' if file.is_file() else 'not there: pdfmd --init-config writes one'
        print(f"{layer} config file: {file} ({state})")
        for key in CONFIG_KEYS:
            if key in data:
                print(f"  {key}: {data[key]}")
    if core.config_root().is_dir():
        print(f"state kept beside it: {core.config_root()}")
    return core.deferred("pdfmd_metadata", "metadata_sources")(document, no_auto, metadata_request)


def migrate_state(old: Path, new: Path) -> None:
    """Move a file pdfmd used to keep in the cache folder (where cleaning it loses it) to ``new``."""
    try:
        if not new.exists() and old.is_file():
            new.parent.mkdir(parents=True, exist_ok=True)
            new.write_bytes(old.read_bytes())
            old.unlink()
    except OSError:
        pass


SETUP_HEADER = ("# pdfmd's global config, written by `pdfmd --setup` (edit it by hand, or run that again).\n"
                "# Precedence: command line > document > metadata files > folder settings > per-install config > user config.\n")


def has_yaml_frontmatter(text: str) -> bool:
    """Whether Pandoc's Markdown reader finds a YAML metadata block at the top of ``text`` (v3.32.4: it used to be only
    "the first line is ``---``", so a file that opens with a thematic break counted).

    Pandoc's rule, measured with 3.13: blank lines may come first; then a line of three dashes (trailing spaces allowed)
    followed by a NON-BLANK line, and a later line of ``---`` or ``...`` that closes it. ``---`` straight after ``---``
    is an empty block, which counts (the documented way to ask for Pandoc's reader). ``---`` then a blank line is a
    horizontal rule, and so is an opening line that nothing closes."""
    lines = text.lstrip("﻿").splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start + 1 >= len(lines) or lines[start].rstrip() != "---" or not lines[start + 1].strip():
        return False
    return any(line.rstrip() in ("---", "...") for line in lines[start + 1:])


def frontmatter_value(md_path: Path, key: str) -> str | None:
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    match = re.search(rf"^{re.escape(key)}\s*:\s*(.*?)\s*$", front_matter.group(1), re.MULTILINE)
    return match.group(1).strip().strip("'\"") if match else None


def metadata_file_yaml(path: Path) -> dict:
    """Parse a --metadata-file's own YAML content as a plain dict.

    A --metadata-file accepts bare YAML or a front-matter fence ending
    in ``---`` or ``...``, as Pandoc does. Returns {} on a parse
    error, a non-mapping top level, or no PyYAML -- same permissiveness as
    frontmatter_pdfmd_options, since a metadata file's pdfmd-only settings
    are optional sugar, never a hard dependency.
    """
    LEADING_FRONT_MATTER_RE = core.LEADING_FRONT_MATTER_RE
    if core.yaml is None:
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig")
        data = front_matter_dict(text) if LEADING_FRONT_MATTER_RE.match(text) else core.yaml.safe_load(text)
    except (core.yaml.YAMLError, OSError):
        return {}
    return core.load_package("pdfmd_args.options").metadata_mapping(data, path)


def option_names(options: dict, kind: str) -> list[str]:
    """File names a ``pdfmd-options`` block gives for ``kind`` -- ``yaml``
    (metadata files), ``preamble`` or ``lua-filter`` -- written flat or
    grouped under ``metadata:``::

        pdfmd-options:
          yaml: [a.yaml]          # also `metadata: a.yaml` (a name or a list)
          preamble: p.tex
          lua-filter: f.lua
          metadata:               # the same, grouped
            yaml: [a.yaml]
            preamble: p.tex
            lua-filter: f.lua     # (`lua:` is accepted too)

    Both spellings add up; a name given twice counts once."""
    names: list[str] = []

    def add(value) -> None:
        for item in ([value] if isinstance(value, str) else value if isinstance(value, list) else []):
            if str(item) not in names:
                names.append(str(item))

    add(options.get(kind))
    grouped = options.get("metadata")
    if isinstance(grouped, dict):
        keys = {"yaml": ("yaml", "metadata"), "preamble": ("preamble",),
                "lua-filter": ("lua-filter", "lua")}[kind]
        for key in keys:
            add(grouped.get(key))
    elif kind == "yaml":
        add(grouped)
    return names


def frontmatter_extra_preambles(md_path: Path, metadata_files: list[Path] = ()) -> list[Path]:
    """Named preambles through every option layer, relative to the file naming each one.
    Added after discovery; --no-auto preamble suppresses them, unlike CLI -H.
    """
    return core.deferred("pdfmd_assemble.named", "files")(md_path, metadata_files, "preamble")


def frontmatter_extra_lua_filters(md_path: Path, metadata_files: list[Path] = ()) -> list[Path]:
    """Named Lua filters through every option layer; --no-auto lua suppresses them.
    The build applies check_lua_filters to these together with discovered filters.
    """
    return core.deferred("pdfmd_assemble.named", "files")(md_path, metadata_files, "lua-filter")


def option_flag(value) -> bool | None:
    """A pdfmd-options value read as on/off; None when it says neither."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"true", "yes", "on"}:
        return True
    if text in {"false", "no", "off"}:
        return False
    return None


FOLDER_WARNED: set[str] = set()


FOLDER_DIR = ".pdfmd"




MACHINE_KEYS = ("translit", "setup-ui", "disabled")


def folder_file_data(path: Path):
    """The mapping a folder's settings file holds ({} when it is empty), None when there is no such file, or it cannot be
    used: belongs to another user, cannot be read, is not a mapping (each said once, with a WARN)."""
    try:
        if not path.is_file():
            return None
        if hasattr(os, "getuid") and path.stat().st_uid not in (os.getuid(), 0):
            if str(path) not in FOLDER_WARNED:
                FOLDER_WARNED.add(str(path))
                print(f"WARN  {path}: belongs to another user; not read", file=sys.stderr)
            return None
        data = core.yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, core.yaml.YAMLError) as error:
        print(f"WARN  {path}: cannot be read ({error}); ignoring it", file=sys.stderr)
        return None
    if data is None:
        return {}
    if not isinstance(data, dict):
        print(f"WARN  {path}: expected a mapping of settings; ignoring it", file=sys.stderr)
        return None
    return data


@lru_cache(maxsize=None)
def folder_walk(folder: str) -> tuple[tuple[Path, dict | None, Path | None], ...]:
    """((the .pdfmd folder, the mapping of its config.yaml or None, its metadata.yaml or None) ...) from `folder` up, nearest
    first, for each folder that has one of the two files; a config that says `inherit: false` ends the walk (v3.29.29: the
    metadata.yaml of a folder is a layer too)."""
    if core.yaml is None:
        return ()
    found: list[tuple[Path, dict | None, Path | None]] = []
    here = Path(folder)
    for candidate in (here, *here.parents):
        directory = candidate / FOLDER_DIR
        data = folder_file_data(directory / "config.yaml")
        metadata = directory / "metadata.yaml"
        if folder_file_data(metadata) is None:
            metadata = None
        if data is None and metadata is None:
            continue
        if data is not None:
            machine = sorted(str(key) for key in data if key in MACHINE_KEYS)
            if machine and str(directory / "config.yaml") not in FOLDER_WARNED:
                FOLDER_WARNED.add(str(directory / "config.yaml"))
                print(f"WARN  {directory / 'config.yaml'}: {', '.join(machine)} {'is' if len(machine) == 1 else 'are'} for this "
                      "machine and cannot be set by a folder; ignored", file=sys.stderr)
        found.append((directory, data, metadata))
        if data is not None and str(data.get("inherit", True)).strip().casefold() in ("false", "no", "off", "0"):
            break
    return tuple(found)


def folder_layer_files(folder: str) -> tuple[tuple[str, dict], ...]:
    """((path, options) ...) of the folder layers from `folder` up, nearest first (see FOLDER_SETTINGS)."""
    result = []
    for directory, data, _ in core.folder_walk(folder):
        if data is not None:
            options = data.get("options")
            result.append((str(directory / "config.yaml"), options if isinstance(options, dict) else {}))
    return tuple(result)


def folder_metadata_files(folder: str) -> list[Path]:
    """The `.pdfmd/metadata.yaml` files of the folder layers from `folder` up, nearest first."""
    return [metadata for _, _, metadata in core.folder_walk(folder) if metadata is not None]


def is_folder_metadata(path) -> bool:
    return Path(path).name == "metadata.yaml" and Path(path).parent.name == FOLDER_DIR


def is_setup_layer(where: str) -> bool:
    """Whether an option source is a setup (the global config or a folder's) and not a document or its metadata: a mapping
    there without `enabled` stays off."""
    return where in ("config", "per-install") or where.startswith("folder ")


def folder_layers(md_path: Path) -> list[tuple[str, dict]]:
    """The folder layers of a document as (where, options) for option_sources, nearest first."""
    try:
        start = str(md_path.resolve().parent)
    except OSError:
        return []
    return [(f"folder {core.display_path(Path(path))}", options) for path, options in folder_layer_files(start)]


def option_sources(md_path: Path, metadata_files: list[Path], with_config: bool = True) -> list[tuple[str, dict]]:
    """Where a pdfmd-options key is read, the first one winning: the document's own front matter, its metadata files
    (in Pandoc priority order), folder settings, then per-install and user config. Each as (where, mapping)."""
    sources = [("document", core.frontmatter_pdfmd_options(md_path))]
    for metadata_file in core.metadata_files_by_priority(metadata_files):
        found = metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append((metadata_file.name, found if isinstance(found, dict) else {}))
    if with_config:
        sources.extend(folder_layers(md_path))
        global_options = global_option_layers()
        if global_options and global_options[0][0] == "per-install":
            sources.extend(("per-install" if layer == "per-install" else "config", options)
                           for layer, _, options in global_options)
        else:
            sources.append(("config", core.config_options()))
    return sources


def first_pdfmd_option(md_path: Path, metadata_files: list[Path], *names: str, with_config: bool = True):
    """The value of the first of ``names`` that the document's own pdfmd-options, then its metadata files' (the later
    first, metadata_files_by_priority), then the config file's set; None if none does. A mapping is merged field by field with the mappings set below it
    (the first place to set a field wins, v3.27.1), down to a place that sets the key to something else."""
    names = tuple(alias for name in names for alias in spelling.spellings(name))
    found: list[dict] = []
    for _, options in option_sources(md_path, metadata_files, with_config):
        for name in names:
            if name in options:
                value = options[name]
                if not isinstance(value, dict):
                    return merge_option_dicts(found) if found else value
                found.append(value)
                break
    return merge_option_dicts(found) if found else None


def resolve_strip_comments(md_path: Path, metadata_files: list[Path], default: bool = False,
                           *, default_keep: frozenset[str] = frozenset()) -> frozenset[str]:
    """The kinds of source whose comments are stripped (see COMMENT_KINDS): the command
    line (--strip-comments / --keep-comments, then --strip-comments-in / --keep-comments-in),
    else `pdfmd-options.strip-comments`, else ``default`` except for kinds in ``default_keep``."""
    if core.STRIP_COMMENTS_CLI is not None:
        policy = core.CommentPolicy(core.STRIP_COMMENTS_CLI)
    else:
        policy = core.parse_comment_policy(first_pdfmd_option(md_path, metadata_files, "strip-comments"), default,
                                           default_keep=default_keep)
    return policy.adjusted(core.STRIP_KINDS_CLI, core.KEEP_KINDS_CLI).kinds()


def merge_option_dicts(sources: list[dict]) -> dict:
    """Merge ``pdfmd-options`` mappings; an earlier one wins, mappings are
    merged field by field (the cascade pdfmd's own readers apply)."""
    merged: dict = {}
    for source in sources:
        for key, value in source.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = merge_option_dicts([merged[key], value])
    return merged


def option_flag_number(value) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def front_matter_dict(text: str) -> dict:
    LEADING_FRONT_MATTER_RE = core.LEADING_FRONT_MATTER_RE
    front = LEADING_FRONT_MATTER_RE.match(text)
    if not front or core.yaml is None:
        return {}
    try:
        loaded = core.yaml.safe_load(front.group("yaml"))
    except core.yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}
