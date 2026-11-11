"""The Obsidian vault side of reading a note: the vault's root and its `app.json` settings, the single-newline mode, and the
picture embeds (`![[name.png|300]]`: their settings, the search for the file, the Markdown image they become, the Lua filter).

Moved out of `pdfmd.py` unchanged (v3.33.12, SPLIT.md), with `EMBED_FIT_WORDS`, `EMBED_SEARCH_WORDS`, `NEWLINE_WORDS`,
`_EMBED_INDEX`, `_EMBED_SKIP_FOLDERS` and `_VAULT_ROOTS`; the two caches are this module's own dicts, which nothing rebinds
(the tests empty them with `pdfmd._VAULT_ROOTS.clear()`, which `pdfmd.py` hands on through `DEFERRED_NAMES`). `core` is the `pdfmd`
module, bound when the module is first loaded (the first binding wins); the pdfmd names the code uses (`FLAVOUR_PRESETS`,
`_FLAVOUR_TOLD`, `display_path`, `first_pdfmd_option`, `flavour_of`) are read as `core.X` when it runs. `pdfmd_obsidian.embeds`
and `pdfmd_lua` are imported inside the functions, as they were.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

core = None

_VAULT_ROOTS: dict[Path, Path | None] = {}
NEWLINE_WORDS = ("hard", "soft")


def vault_app_setting(md_path: Path, key: str):
    """The value of ``key`` in the vault's ``.obsidian/app.json`` (None outside a vault, or when the file or the key is missing:
    an untouched vault writes only what its user changed)."""
    vault = vault_root(md_path)
    if vault is None:
        return None
    try:
        return json.loads((vault / ".obsidian" / "app.json").read_text(encoding="utf-8")).get(key)
    except (OSError, ValueError, AttributeError):
        return None


def single_newline_mode(md_path: Path, metadata_files=()) -> str:
    """What a single newline inside a paragraph does (v3.32.27): `hard` (a line break) or `soft` (a space). `pdfmd-options.single-newline`,
    else, in the obsidian flavour inside a vault, the vault's own `strictLineBreaks` (true: soft; false: hard; absent: the
    flavour's), else the flavour's column (`hard` for obsidian, `soft` for the rest). Another word is told once."""
    preset = core.FLAVOUR_PRESETS.get(core.flavour_of(md_path, metadata_files))
    default = preset.newline if preset else "soft"
    value = core.first_pdfmd_option(md_path, list(metadata_files), "single-newline")
    if value is None:
        strict = vault_app_setting(md_path, "strictLineBreaks") if core.flavour_of(md_path, metadata_files) == "obsidian" else None
        return default if not isinstance(strict, bool) else ("soft" if strict else "hard")
    name = str(value).strip().casefold()
    if name in NEWLINE_WORDS:
        return name
    if f"newline:{name}" not in core._FLAVOUR_TOLD:
        core._FLAVOUR_TOLD.add(f"newline:{name}")
        print(f"NOTE  single-newline: {name} is not one of {', '.join(NEWLINE_WORDS)}; using {default}", file=sys.stderr)
    return default


def vault_root(path: Path) -> Path | None:
    """The folder that holds `.obsidian/`: the one of ``path`` or the nearest above it (None outside a vault). Remembered per folder."""
    try:
        folder = path.resolve().parent
    except OSError:
        return None
    walked: list[Path] = []
    found: Path | None = None
    for candidate in (folder, *folder.parents):
        if candidate in _VAULT_ROOTS:
            found = _VAULT_ROOTS[candidate]
            break
        walked.append(candidate)
        if (candidate / ".obsidian").is_dir():
            found = candidate
            break
    for candidate in walked:
        _VAULT_ROOTS[candidate] = found
    return found


# Picture embeds, `![[name.png|300]]` (v3.32.25, entry 3ee): Obsidian's way to show a picture by its name, read as pdfmd's own image
# embed in the obsidian and pdfmd flavours. pdfmd-options: embed-px-to-pt (points to a pixel of `|300`, default 0.75: 1 CSS px),
# embed-fit (text-width, the default: a sized picture stays within the text width in a LaTeX build; none), embed-search (where a
# name is looked for besides the path as written: vault, the default; folder; none).
EMBED_FIT_WORDS = ("text-width", "none")
EMBED_SEARCH_WORDS = ("vault", "folder", "none")
_EMBED_INDEX: dict[Path, dict[str, list[Path]]] = {}
_EMBED_SKIP_FOLDERS = frozenset({".git", ".obsidian", ".trash", "node_modules", "__pycache__", ".venv", "venv"})


def embed_settings(md_path: Path, metadata_files=()) -> dict:
    """The embed options as they stand: {"px_to_pt": float, "fit": word, "search": word}. A bad value is told once and the default used."""
    def pick(name, words, default):
        value = core.first_pdfmd_option(md_path, list(metadata_files), name)
        word = default if value is None else str(value).strip().casefold()
        if word in words:
            return word
        if f"{name}:{word}" not in core._FLAVOUR_TOLD:
            core._FLAVOUR_TOLD.add(f"{name}:{word}")
            print(f"NOTE  {name}: {word} is not one of {', '.join(words)}; using {default}", file=sys.stderr)
        return default
    ratio = core.first_pdfmd_option(md_path, list(metadata_files), "embed-px-to-pt")
    try:
        px_to_pt = 0.75 if ratio is None else float(ratio)
        if px_to_pt <= 0:
            raise ValueError
    except (TypeError, ValueError):
        if f"ratio:{ratio}" not in core._FLAVOUR_TOLD:
            core._FLAVOUR_TOLD.add(f"ratio:{ratio}")
            print(f"NOTE  embed-px-to-pt: {ratio!r} is not a positive number; using 0.75", file=sys.stderr)
        px_to_pt = 0.75
    return {"px_to_pt": px_to_pt, "fit": pick("embed-fit", EMBED_FIT_WORDS, "text-width"),
            "search": pick("embed-search", EMBED_SEARCH_WORDS, "vault")}


def _embed_folder_index(root: Path) -> dict[str, list[Path]]:
    """Every picture below ``root`` by file name (lower case), hidden and tool folders left out; remembered per folder."""
    if root not in _EMBED_INDEX:
        from pdfmd_obsidian.embeds import IMAGE_SUFFIXES
        index: dict[str, list[Path]] = {}
        for folder, subfolders, files in os.walk(root):
            subfolders[:] = [name for name in sorted(subfolders) if not name.startswith(".") and name not in _EMBED_SKIP_FOLDERS]
            for name in sorted(files):
                if name.lower().endswith(IMAGE_SUFFIXES):
                    index.setdefault(name.lower(), []).append(Path(folder) / name)
        _EMBED_INDEX[root] = index
    return _EMBED_INDEX[root]


def find_embedded_image(name: str, md_path: Path, search: str = "vault") -> Path | None:
    """The file a picture name stands for: the path as written (beside the document, or from the vault's top), the vault's attachment
    folder (`attachmentFolderPath` of .obsidian/app.json), then by name anywhere below the vault (outside one: below the document's
    folder); the one nearest the document when several have that name, told once. ``search`` = folder keeps to the document's folder,
    none to the path as written."""
    here = md_path.resolve().parent
    vault = vault_root(md_path) if search == "vault" else None
    for base in (here, vault):
        if base is not None and (base / name).is_file():
            return base / name
    if vault is not None:
        attachments = vault_app_setting(md_path, "attachmentFolderPath") or ""
        if isinstance(attachments, str) and attachments.strip() not in ("", "/"):
            folder = here / attachments if attachments.startswith("./") else vault / attachments.strip("/")
            if (folder / name).is_file():
                return folder / name
    if search == "none":
        return None
    candidates = _embed_folder_index(vault or here).get(Path(name).name.lower(), [])
    wanted = Path(name).as_posix().lower()
    candidates = [path for path in candidates if path.as_posix().lower().endswith(wanted)]
    if not candidates:
        return None

    def distance(path: Path) -> tuple[int, str]:
        shared = os.path.commonpath([str(here), str(path.parent)])
        return len(here.relative_to(shared).parts) + len(path.parent.relative_to(shared).parts), str(path)
    candidates.sort(key=distance)
    if len(candidates) > 1 and f"embed:{md_path}:{name}" not in core._FLAVOUR_TOLD:
        core._FLAVOUR_TOLD.add(f"embed:{md_path}:{name}")
        print(f"NOTE  {core.display_path(md_path)}: {len(candidates)} pictures are named {name}; using {core.display_path(candidates[0])}",
              file=sys.stderr)
    return candidates[0]


def embed_source(text: str, md_path: Path, metadata_files=()) -> str:
    """``text`` with each `![[picture|300]]` written as a Markdown image whose path is relative to the document (absolute when it lies
    on another drive), sized in points; a picture that is not found stays a visible `[missing image: name]` and is told once."""
    try:
        from pdfmd_obsidian.embeds import embed_images
    except ImportError:
        return text
    settings = embed_settings(md_path, metadata_files)
    here = md_path.resolve().parent

    def find(name: str) -> str | None:
        found = find_embedded_image(name, md_path, settings["search"])
        if found is None:
            return None
        try:
            return Path(os.path.relpath(found, here)).as_posix()
        except ValueError:                        # another drive (Windows)
            return found.as_posix()
    result = embed_images(text, find, settings["px_to_pt"], settings["fit"])
    for _, name in result.missing:
        told = f"missing:{md_path}:{name}"
        if told not in core._FLAVOUR_TOLD:
            core._FLAVOUR_TOLD.add(told)
            print(f"WARN  {core.display_path(md_path)}: ![[{name}]]: no picture of that name was found "
                  f"(embed-search: {settings['search']}); it is left as [missing image: {name}]", file=sys.stderr)
    return result.text


def embed_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter embed_fit.lua`` when the document has picture embeds in a flavour that reads them and `embed-fit` is
    `text-width`: it keeps a sized picture within the text width in a LaTeX build (the filter acts on `data-pdfmd-fit` images only)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or files[0].suffix.lower() not in (".md", ".markdown"):
        return []
    preset = core.FLAVOUR_PRESETS.get(core.flavour_of(files[0], metadata_files))
    if preset is None or not preset.embeds:
        return []
    try:
        if "![[" not in files[0].read_text(encoding="utf-8-sig") or embed_settings(files[0], metadata_files)["fit"] != "text-width":
            return []
        import pdfmd_lua
    except (OSError, ImportError):
        return []
    shipped = pdfmd_lua.path("embed_fit")
    return ["--lua-filter", str(shipped)] if shipped is not None else []


def figure_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter figures.lua`` for a Markdown document with a picture in it, in a flavour that reads its gfm files with
    `implicit_figures` (pdfmd, obsidian). An older Pandoc (3.1.3) takes the extension's name on the gfm reader and makes no figure;
    the filter makes it, only when the reader of the run was asked for figures, and changes nothing where the reader made them (it
    is told by what the reader left, not by a version number)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or files[0].suffix.lower() not in (".md", ".markdown"):
        return []
    preset = core.FLAVOUR_PRESETS.get(core.flavour_of(files[0], metadata_files))
    if preset is None or "implicit_figures" not in preset.gfm_plus:
        return []
    try:
        if "![" not in files[0].read_text(encoding="utf-8-sig"):
            return []
        import pdfmd_lua
    except (OSError, ImportError):
        return []
    shipped = pdfmd_lua.path("figures")
    return ["--lua-filter", str(shipped)] if shipped is not None else []
