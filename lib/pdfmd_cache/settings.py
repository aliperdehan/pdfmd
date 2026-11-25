"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_cache.settings`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pdfmd_base import core
from pdfmd_log import emit


# -- The cache route (pdfmd-options: {cache: {aux: true}}) -------------------
# Normally Pandoc writes a .tex into a throwaway directory, runs the engine
# there two or three times, and deletes everything, so every build starts from
# zero: LaTeX's cross-reference files do not exist yet, the first pass can
# only print ?? and ask for another. With cache.aux the same .tex (the very one
# Pandoc would have made: --to latex, standalone) is written into a per-
# document folder under the user's cache directory and compiled there by
# pdfmd's own engine runner (compile_tex_direct), which reruns only while the
# log asks for it -- latexmk's rule. The folder, and LaTeX's .aux inside it,
# survive between builds, so an unchanged document settles in ONE pass, and a
# part of a split document built alone can read the labels the last full build
# left (seed_labels_file), instead of printing ??. Nothing is trusted: a failed
# build wipes that document's LaTeX files and retries from clean, and the final
# PDF is always the product of a pass whose log asked for no further rerun.
CACHE_DEFAULTS = {"aux": False, "plots": False}


# -- A home that cannot be written (a sandbox, a read-only container) ------------------------------------------------------------
# pdfmd keeps a cache (cache_root()), LuaTeX keeps its font names in the TeX user tree (TEXMFVAR, under the home), Pandoc and the
# tools it starts may write in their working folder. When one of those places cannot be written the build goes on with a
# temporary folder in its place, removed when the run ends, and says so once (a NOTE): the first run in such a place is slower
# (the cache starts empty, LuaTeX indexes the fonts again), nothing else differs.
NOTED_PLACES: set[str] = set()


def note_place_once(key: str, message: str) -> None:
    if key not in NOTED_PLACES:
        NOTED_PLACES.add(key)
        emit("note", None, f"NOTE  {message}", file=sys.stderr)


def tex_user_tree_writable() -> bool:
    """Whether LuaTeX and friends can keep their caches: TEXMFVAR if it is set, else a TeX user tree in the home
    (~/.texlive2023, ~/Library/texlive/2023) that exists and can be written, else the home itself."""
    if os.environ.get("TEXMFVAR"):
        return core.folder_is_writable(Path(os.environ["TEXMFVAR"].split(os.pathsep)[0]))
    try:
        home = Path.home()
    except RuntimeError:
        return False
    for pattern in (".texlive*/texmf-var", "Library/texlive/*/texmf-var"):
        if any(core.folder_is_writable(found) for found in home.glob(pattern)):
            return True
    return core.folder_is_writable(home)


def provide_writable_places() -> None:
    """Redirect what cannot be written to a temporary folder (see above); called once, at the start of main()."""
    cache = core.cache_root()
    redirected: list[str] = core.deferred("pdfmd_tex.repair", "unwritable_cache")() if os.environ.get("TEXMFCACHE") else []    # v3.33.221
    if not core.folder_is_writable(cache):
        folder = core.temporary_place("cache")
        variable = "LOCALAPPDATA" if sys.platform == "win32" else "XDG_CACHE_HOME"
        os.environ[variable] = str(folder)               # cache_root() and the tools pdfmd starts (fontconfig, Typst ...) follow
        redirected.append(f"the cache folder {core.display_path(cache)}")
    if (not tex_user_tree_writable()
            and any(core.which(name) for name in ("lualatex", "xelatex", "pdflatex", "latexmk", "tectonic"))):
        folder = core.temporary_place("texmf")
        for name, variable in (("texmf-var", "TEXMFVAR"), ("texmf-config", "TEXMFCONFIG")):
            (folder / name).mkdir(parents=True, exist_ok=True)         # (an engine that does not make its own cache folder needs it there)
            os.environ[variable] = str(folder / name)
        redirected.append("the TeX user tree (font names, formats)")
    if redirected:
        note_place_once("places", f"{' and '.join(redirected)} cannot be written (a read-only home?): this run uses a temporary "
                                  "folder instead, removed when it ends; the first build is slower and nothing else differs")


def metadata_cwd(metadata_files: list[Path] | None, default: Path) -> Path:
    """The folder Pandoc (and so the TeX engine) runs in: that of the first metadata file placed FOR the document -- beside it, in
    its `metadata/` folder, or named with -y -- else ``default`` (the document's). A file a kit supplies, a folder's
    `.pdfmd/metadata.yaml` and the global metadata of `pdfmd --setup` belong to no document's folder: a relative path in raw
    LaTeX (a pgfplots table, `../ir/x.csv`) must stay relative to the document (v3.31.33). Their own folders go on the resource
    path instead (resource_path_option), so a `bibliography:` or `csl:` written beside them is still found."""
    for path in metadata_files or []:
        if path not in core.KIT_METADATA and not core.is_folder_metadata(path) and not core.is_global_metadata(path):
            return path.parent
    return default


def pandoc_working_directory(folder: Path) -> Path:
    """The folder Pandoc runs in: ``folder`` (the document's, so its relative paths resolve), or when that cannot be written
    a temporary one with the document's folder on --resource-path and TEXINPUTS (resource_path_option, tex_search_env)."""
    if core.folder_is_writable(folder):
        return folder
    note_place_once(f"cwd:{folder}", f"{core.display_path(folder)} cannot be written: Pandoc runs in a temporary folder, with "
                                     "the document's folder searched for what it names")
    return core.temporary_place("pandoc")


CACHE_LOCATIONS = ("global", "document")


CACHE_MANIFEST = ".pdfmd-source.json"


LOCAL_CACHE_DIRNAME = Path(".cache") / "pdfmd"


def prepare_cache_root(root: Path) -> None:
    """Mark a cache folder as one: CACHEDIR.TAG (backup tools skip it) and, for a `.cache/pdfmd`
    beside a document, a .gitignore so the cache is not committed."""
    try:
        root.mkdir(parents=True, exist_ok=True)
        tag = root / "CACHEDIR.TAG"
        if not tag.exists():
            tag.write_text("Signature: 8a477f597d28d172789f06886806bc55\n"
                           "# This is a cache directory made by pdfmd (safe to delete).\n", encoding="utf-8")
        if root.parent.name == ".cache" and not (root.parent / ".gitignore").exists():
            (root.parent / ".gitignore").write_text("*\n", encoding="utf-8")
    except OSError:
        pass


def write_cache_manifest(folder: Path, source: Path) -> None:
    """Record whose cache a folder is, so a moved document can find it again (see adopt_moved_cache)."""
    import json
    try:
        (folder / CACHE_MANIFEST).write_text(json.dumps({
            "path": str(source.resolve()), "stem": source.stem, "folder": source.resolve().parent.name,
            "sha256": core.source_fingerprint(source)}), encoding="utf-8")
    except OSError:
        pass


def cache_settings(md_path: Path, metadata_files: list[Path], cli: bool | None) -> dict:
    """Effective ``pdfmd-options: {cache: {aux, plots}}``: the document's own
    front matter first, then each linked metadata file, then --cache/--no-cache
    (--cache turns aux on, --no-cache turns everything off)."""
    settings = dict(CACHE_DEFAULTS)
    chosen: set = set()
    sources = [core.frontmatter_pdfmd_options(md_path)]
    for metadata_file in core.metadata_files_by_priority(metadata_files):
        options = core.metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append(options if isinstance(options, dict) else {})
    sources.append(core.config_options(md_path))
    for options in sources:
        if "cache" not in options:
            continue
        value = options["cache"]
        if isinstance(value, bool):
            value = {"aux": value}
        if isinstance(value, dict):
            for key in settings:
                if key in value and key not in chosen:      # the first place to set a field wins (v3.27.1)
                    chosen.add(key)
                    settings[key] = bool(value[key])
    if cli is True:
        settings["aux"] = True
    elif cli is False:
        settings = {key: False for key in settings}
    if core.CACHE_PLOTS_CLI and cli is not False:
        settings["plots"] = True
    return settings
