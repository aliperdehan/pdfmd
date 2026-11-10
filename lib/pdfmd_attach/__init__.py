"""The source a build carries: what `--attach-source` attaches to a PDF and `--keep-source` puts at the end of a Markdown output
(`attach_source_after_success`, `keep_source_after_success`, `source_attachments`, `attached_source`, `attachment_manifest`), the
files a bundle stores beside it (`bundle_files`, `bundle_reach`, `attached_bundle_mode`, `resolve_bundle_packages`, the images the
text points at: `referenced_images`), the user's own TeX tree a rebuild needs (`tex_tree_dependencies`, `find_in_tex_tree`,
`tex_tree_graphics`, `package_companions`, `attachment_requirements`), the text files kept as blocks of the source
(`inline_candidates`, `inline_blocks`, `drop_blocks`, `csv_block_files`), the bibliography and citation style it takes along
(`resolve_bibliography_pruning`, `resolve_csl_attach`), the folder settings in force (`folder_options_in_force`), and the PDF's
attachments themselves (`write_pdf_attachments`, `read_pdf_attachments`, `add_deflated_attachment`). `held_comments_note` (v3.33.48)
names the kinds of source whose comments were stripped that the attached text holds.

Moved out of `pdfmd.py` unchanged (v3.33.37, SPLIT.md), with the constants only this code reads (`ATTACH_FORMAT_PLAIN`,
`GLOBAL_LAYOUT_PATH`, `RAW_REFERENCE_RES`, `BUNDLE_SKIP_SUFFIXES`, `PATH_TOKEN_RE`, `REFERENCE_EXTENSIONS`, `SCANNED_SUFFIXES`,
`PACKAGE_RE`, `CLASS_RE`, `TEX_INPUT_RE`, `PROVIDES_RE`, `GRAPHIC_SUFFIXES`, `BUNDLE_IMAGE_SUFFIXES`, `TEX_SOURCE_SUFFIXES`,
`TEX_TREE_SCAN_LIMIT`, `GRAPHIC_ARGUMENT_RE`, `MACRO_VALUE_RE`, `FONT_KEYS` and the three `INLINE_*`). `core` is the `pdfmd`
module, bound by `pdfmd.py` when it loads (the first binding wins); the pdfmd names the code uses are read as `core.X` when it
runs: `ACCESSORY_DIRNAME`, `ATTACH_FORMAT`, `ATTACH_MANIFEST`, `ATTACH_SOURCE`, `BIB_ATTACH_CLI`, `BUNDLE_CLI`, `BUNDLE_MAX_MB`,
`BUNDLE_PACKAGES_CLI`, `BUNDLE_SKIP_DIRS`, `CSL_ATTACH_CLI`, `EMBED_BLOCK_RE`, `EMBED_KINDS`, `EmbedRequest`, `GRAPHIC_RE`,
`IMAGE_REF_RE`, `PDFMD_VERSION`, `RESTORED_SUFFIX`, `UNPACKED_SUFFIX`, `active_kits`, `add_calc_constants`,
`assemble_markdown_text`, `atomic_write_bytes`, `atomic_write_pdf`, `comments_note`, `display_path`, `document_preambles`, `drop_calc_export`,
`extra_key`, `first_block_start`, `first_pdfmd_option`, `folder_layer_files`, `folder_options_safe`, `front_matter_dict`,
`frontmatter_no_auto`, `header_includes_text`, `is_crlf_text`, `is_global_metadata`, `kit_carried_files`,
`kit_embedded_preambles`, `make_embed_plan`, `match_images_to_pdf`, `merge_options`, `option_flag`, `option_flag_number`,
`package_places`, `pandoc_version`, `parse_embedded_blocks`, `parts_setting`, `pypdf`, `relative_posix`, `render_embedded_file`,
`requirement_lines`, `resolve_bundle`, `resolve_strip_comments`, `sha256_text`, `strip_location_markers`,
`strip_markdown_comments`, `strip_part_front_matter`, `strip_tex_comments`, `vprint`, `which`, `with_location_markers` and `yaml`.
`BIB_ATTACH_CLI`, `BUNDLE_CLI`, `BUNDLE_PACKAGES_CLI` and `CSL_ATTACH_CLI` stay in `pdfmd.py`, rebound with `global` in `main`;
`pandoc_version` and `which` are patched by tests as `pdfmd.X`. pypdf is `core.pypdf`, a lazy loader there, so it is never
imported at the top here (only the annotations name it); the `from pypdf.generic import ...` line and the imports of
`pdfmd_tables`, `pdfmd_flat.keep` and `pdfmd_flat.asciify` stay inside the functions, as they were. `attach_source_after_success`
was decorated with `pdfmd`'s `@timed`, which is defined far below the place where the package loads: `_timed` is the same
decorator looked up at call time (`core.timed(name)(function)`).
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import io
import json
import logging
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.parse
import warnings
import zlib
from datetime import datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:     # only the annotations name it; the code reads core.pypdf
    import pypdf

core = None


def _timed(name):
    """`core.timed(name)` for a function defined before `core.timed` exists: each call is wrapped when it is made."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            return core.timed(name)(function)(*args, **kwargs)
        return wrapper
    return decorate


def folder_options_in_force(md_path: Path) -> dict:
    """The `options:` of the folder settings (`.pdfmd/config.yaml`) above ``md_path``, nearest layer winning, as one mapping: what an
    attached source takes along so a restored report builds with the same settings. Left out: `kit` and `kit-stack` (what a kit
    wrote is in the source itself), and what a folder cannot set anyway."""
    try:
        layers = core.folder_layer_files(str(md_path.resolve().parent))
    except OSError:
        return {}
    merged: dict = {}
    for path, options in reversed(layers):
        merged = core.merge_options(merged, core.folder_options_safe(path, options))
    return {key: value for key, value in merged.items() if key not in ("kit", "kit-stack")}


INLINE_SUFFIXES = (".tex", ".csv", ".tsv", ".dat", ".txt")
INLINE_LIMIT = 1024 * 1024
INLINE_ORDER = (".tex",)                  # in this order, then the rest by name


def block_places(block: dict) -> list[str]:
    """Every path a `type: file` block stands for: its own and the `also:` ones."""
    return [block["path"] or block["name"], *block.get("also", [])]


def drop_blocks(text: str, doomed) -> str:
    """``text`` without the `{=pdfmd}` blocks ``doomed(fields)`` says yes to (``fields``: the block's header lines as a
    dict), and the line end and blank line each brought."""
    out, last = [], 0
    for match in core.EMBED_BLOCK_RE.finditer(text):
        head = match.group("body").partition("\n\n")[0]
        fields = {key.strip(): value.strip() for key, _, value in (line.partition(":") for line in head.splitlines())}
        if doomed(fields):
            out.append(text[last:match.start()])
            last = match.end() + (1 if text[match.end():match.end() + 1] == "\n" else 0)
            if text[last:last + 1] == "\n" and (not out[-1] or out[-1].endswith("\n\n")):
                last += 1                                  # the blank line that parted it from the next
    out.append(text[last:])
    return "".join(out)


def drop_duplicate_blocks(text: str) -> str:
    """``text`` with the second block of one kind and name (a style or bibliography embedded again by a build of an edited
    single file) taken out; the first stays."""
    seen: set[tuple[str, str]] = set()

    def again(fields: dict) -> bool:
        if fields.get("type") not in ("bibliography", "csl"):
            return False
        key = (fields["type"], fields.get("path") or fields.get("name", ""))
        if key in seen:
            return True
        seen.add(key)
        return False
    return drop_blocks(text, again)


def inline_candidates(extras: dict[str, bytes]) -> dict[str, bytes]:
    """The stored files that go into the text instead: text files within the document's folder or in a folder above it
    (`../schemes/x.tex`: only `..` first, then names), not too big, readable as UTF-8 with Unix line ends and no ``` in them."""
    found: dict[str, bytes] = {}
    for name, data in extras.items():
        below = name.split("/")
        while below and below[0] == "..":
            below.pop(0)
        if (name.lower().endswith(INLINE_SUFFIXES) and below and ".." not in below and "" not in below
                and len(data) <= INLINE_LIMIT and (b"\r" not in data or core.is_crlf_text(data)) and b"\x00" not in data
                and b"```" not in data):
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if not data or data.endswith(b"\n"):
                found[name] = data
    return found


def inline_blocks(files: dict[str, bytes]) -> str:
    """The `type: file` blocks of ``files``: .tex first, then the others, each group by name; the files with one content
    are one block that lists the other paths as `also:`."""
    by_content: dict[bytes, list[str]] = {}
    for name in sorted(files, key=lambda item: (next((index for index, suffix in enumerate(INLINE_ORDER)
                                                      if item.lower().endswith(suffix)), len(INLINE_ORDER)), item)):
        by_content.setdefault(files[name], []).append(name)
    out = ""
    for data, names in by_content.items():
        block = core.render_embedded_file(PurePosixPath(names[0]).name, names[0], data)
        if len(names) > 1:
            block = block.replace("\nsha256:", "".join(f"\nalso: {item}" for item in names[1:]) + "\nsha256:", 1)
        out += "\n" + block
    return out


ATTACH_FORMAT_PLAIN = 2
# How an attached source's manifest names pdfmd's global metadata file (v3.28.13; marked "global": true)
GLOBAL_LAYOUT_PATH = "../pdfmd/metadata.yaml"
RAW_REFERENCE_RES = (
    re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}"),
    re.compile(r"\\(?:input|include)\{([^}]+)\}"),
    re.compile(r"""\bfile=["']([^"']+)["']"""),
    # data a LaTeX macro reads: pgfplots tables, listings, verbatim files, included PDFs
    re.compile(r"\\addplot\+?(?:\[[^\]]*\])?\s*table\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}"),
    re.compile(r"\\(?:pgfplotstableread|pgfplotstabletypeset|lstinputlisting|verbatiminput|includepdf|csvreader)"
               r"(?:\[[^\]]*\])?\s*\{([^}]+)\}"),
)
BUNDLE_SKIP_SUFFIXES = (".aux", ".log", ".out", ".toc", ".bbl", ".blg", ".fls", ".fdb_latexmk",
                        ".synctex.gz", ".assembled.md")
# Any word that looks like a relative file name and names a file that exists: how data
# reached through a project's own macros (`\\irpanel{ir/plain/x.csv}`) is found.
PATH_TOKEN_RE = re.compile(r"(?<![\w/.\\:-])((?:[\w.-]+/)*[\w.-]+\.[A-Za-z0-9]{1,5})(?![\w/-])")
REFERENCE_EXTENSIONS = ("", ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".tex", ".csv")
# What a stored file is read for in turn (the files it points at): LaTeX, Markdown, data lists.
SCANNED_SUFFIXES = (".tex", ".sty", ".cls", ".def", ".cfg", ".md", ".markdown", ".csv", ".tsv", ".txt", ".dat", ".lua")


def attached_bundle_mode(md_path: Path, metadata_files: list[Path], is_pdf: bool) -> str | None:
    """The bundle a source is attached with. Said (--bundle, --no-bundle, pdfmd-options.bundle): that. Not
    said: "sources" (v3.28.15: a restored report builds again, which needed `bundle: referenced` before and the
    images with it), for a PDF and, since v3.33.64, for a Markdown output (--keep-source) as well, which had none:
    the files the text and its preamble `\\input` come back with it. ``is_pdf`` no longer changes the answer; the
    pictures do differ: a PDF holds them, a Markdown file stores them only with a bundle that takes them (`referenced`,
    `all`)."""
    if core.BUNDLE_CLI is not None or core.first_pdfmd_option(md_path, metadata_files, "bundle") is not None:
        return core.resolve_bundle(md_path, metadata_files)
    return "sources"


def layout_path(base: Path, item: Path) -> str:
    """Where ``item`` (a metadata file, preamble or filter pdfmd found) sits
    relative to the document's folder ``base``. Discovery may hand back the file
    a symlink points to, outside the folder; then the name it has in the folder
    itself (beside the document or in `metadata/`) is the layout."""
    inside = core.relative_posix(base, item)
    if not inside.startswith(".."):
        return inside
    for folder in (base, base / core.ACCESSORY_DIRNAME):
        candidate = folder / item.name
        try:
            if candidate.exists() and candidate.resolve() == item.resolve():
                return core.relative_posix(base, candidate)
        except OSError:
            pass
    return inside


def referenced_images(text: str, base: Path, latex: bool = False) -> list[Path]:
    """Files the text points at as images (local, existing), in order: Markdown
    `![](...)` and `<img>`, and raw LaTeX `\\includegraphics{...}` (in a Markdown file's
    raw blocks, or in ``latex`` text such as a preamble)."""
    found: list[Path] = []
    visible = core.strip_tex_comments(text) if latex else core.strip_markdown_comments(text)
    for match in ([] if latex else core.IMAGE_REF_RE.finditer(visible)):
        target = (match.group(1) or match.group(2) or "").split("#")[0].split("?")[0]
        if not target or "://" in target or target.startswith(("data:", "mailto:")):
            continue
        path = Path(os.path.abspath(base / urllib.parse.unquote(target)))
        if path.is_file() and path not in found:
            found.append(path)
    for match in RAW_REFERENCE_RES[0].finditer(visible):
        target = urllib.parse.unquote(match.group(1).strip())
        if not target or "://" in target or "\\" in target:
            continue
        for extension in ("", ".png", ".jpg", ".jpeg", ".pdf"):
            path = Path(os.path.abspath(base / (target + extension)))
            if path.is_file():
                if path not in found:
                    found.append(path)
                break
    return found


# LaTeX files that live in the user's own TeX tree (texmf-home, texmf-local), not in the
# TeX distribution: what `\input{chemicals}` or `\usepackage{mystyle}` finds anywhere on the
# machine and nowhere else. The distribution's packages need no carrying; these are what a
# rebuild on another machine misses.
PACKAGE_RE = re.compile(r"\\(?:usepackage|RequirePackage(?:WithOptions)?)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
CLASS_RE = re.compile(r"\\(?:documentclass|LoadClass(?:WithOptions)?)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
TEX_INPUT_RE = re.compile(r"\\(?:input|include|InputIfFileExists)\s*\{([^}]+)\}")
PROVIDES_RE = re.compile(r"\\Provides(?:Package|Class|File)\s*\{[^}]*\}\s*\[([^\]]*)\]")
GRAPHIC_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg")
# Files "sources" mode (v3.28.15) never stores: the PDF holds the pictures, and --restore takes them out of it
BUNDLE_IMAGE_SUFFIXES = GRAPHIC_SUFFIXES + (".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".avif")
TEX_SOURCE_SUFFIXES = (".tex", ".sty", ".cls", ".def", ".cfg", ".clo", ".ltx", ".bbx", ".cbx")
TEX_TREE_SCAN_LIMIT = 200


@lru_cache(maxsize=None)
def tex_distribution_roots() -> tuple[Path, ...]:
    kpsewhich = core.which("kpsewhich")
    roots: list[Path] = []
    if kpsewhich:
        for variable in ("TEXMFDIST", "TEXMFMAIN", "TEXMFSYSVAR", "TEXMFSYSCONFIG"):
            try:
                value = subprocess.run([kpsewhich, "-var-value", variable], capture_output=True, encoding="utf-8", errors="replace",
                                       timeout=30).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                continue
            roots.extend(Path(item).resolve() for item in value.split(os.pathsep) if item)
    return tuple(roots)


GRAPHIC_ARGUMENT_RE = re.compile(r"\\(?:includegraphics|includepdf)\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
MACRO_VALUE_RE = re.compile(r"\\(?:(?:re|provide)?newcommand\*?\s*\{\\([A-Za-z@]+)\}|def\\([A-Za-z@]+))\s*(?:\[\d\])?\s*\{([A-Za-z0-9][\w.-]{1,60})\}")


def graphic_names_in(text: str) -> list[str]:
    """The file names a package's text hands to \\includegraphics through a macro: the values the macros that sit in an
    \\includegraphics argument are given by `\\(re)newcommand{\\LogoFile}{nu-logo}` (v3.28.38; before, any braced word of
    the text that was also the name of a graphic on the TeX tree counted: a `titlepage` option was a `titlepage.pdf`)."""
    macros = {name for argument in GRAPHIC_ARGUMENT_RE.findall(text) for name in re.findall(r"\\([A-Za-z@]+)", argument)}
    values: dict[str, None] = {}
    for first, second, value in MACRO_VALUE_RE.findall(text):
        if (first or second) in macros and "." not in value:
            values[value] = None
    return list(values)


def graphics_named_in(text: str, folders: tuple[Path, ...] = ()) -> tuple[Path, ...]:
    """Graphics of the user's own TeX tree that a package's text names without `\\includegraphics`
    next to the name (`\\newcommand{\\LogoFile}{nu-logo}` ... `\\includegraphics{\\LogoFile}`): the names
    graphic_names_in finds, looked up with a graphic's extension, in ``folders`` (where a stored package sits, in a
    restored source) and in one kpsewhich call."""
    words = sorted(graphic_names_in(text))[:3000]
    local = [(folder / (word + suffix)).resolve() for folder in folders for word in words for suffix in GRAPHIC_SUFFIXES
             if (folder / (word + suffix)).is_file()]
    return tuple(dict.fromkeys([*local, *tex_tree_graphics(tuple(words))]))


@lru_cache(maxsize=None)
def tex_tree_graphics(words: tuple[str, ...]) -> tuple[Path, ...]:
    kpsewhich = core.which("kpsewhich")
    if not kpsewhich or not words:
        return ()
    names = [word + suffix for word in words for suffix in GRAPHIC_SUFFIXES]
    try:
        out = subprocess.run([kpsewhich, *names], capture_output=True, encoding="utf-8", errors="replace", timeout=60,
                             cwd=tempfile.gettempdir()).stdout.split("\n")
    except (OSError, subprocess.SubprocessError):
        return ()
    found = []
    for line in out:
        path = Path(line.strip()).resolve() if line.strip() else None
        if path and path.is_file() and not any(path.is_relative_to(root) for root in tex_distribution_roots()):
            found.append(path)
    return tuple(dict.fromkeys(found))


@lru_cache(maxsize=None)
def find_in_tex_tree(name: str) -> Path | None:
    """The file ``name`` as kpsewhich finds it in a TeX tree of the user's own (not the
    distribution's, not the current folder), or None."""
    kpsewhich = core.which("kpsewhich")
    if not kpsewhich:
        return None
    try:
        found = subprocess.run([kpsewhich, name], capture_output=True, encoding="utf-8", errors="replace", timeout=30,
                               cwd=tempfile.gettempdir()).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not found:
        return None
    path = Path(found).resolve()
    if not path.is_file() or any(path.is_relative_to(root) for root in tex_distribution_roots()):
        return None
    return path


def tex_names(text: str) -> list[tuple[str, tuple[str, ...]]]:
    """(kind, kpsewhich candidates) for each package, class and \\input a LaTeX text names."""
    found: list[tuple[str, tuple[str, ...]]] = []
    for regex, kind, suffix in ((PACKAGE_RE, "package", ".sty"), (CLASS_RE, "class", ".cls")):
        for match in regex.finditer(text):
            for name in match.group(1).split(","):
                name = name.strip()
                if name:
                    found.append((kind, (name if name.endswith(suffix) else name + suffix,)))
    for match in TEX_INPUT_RE.finditer(text):
        name = match.group(1).strip()
        if name and "\\" not in name:
            found.append(("input", (name, name + ".tex") if not Path(name).suffix else (name,)))
    for match in core.GRAPHIC_RE.finditer(text):
        name = match.group(1).strip()
        if name and "\\" not in name and "://" not in name:
            found.append(("graphic", (name,) if name.lower().endswith(GRAPHIC_SUFFIXES)
                          else tuple(name + suffix for suffix in GRAPHIC_SUFFIXES)))
    return found


def tex_tree_dependencies(sources: list[Path], extra_texts: list[str], base: Path,
                          include_local: bool = False) -> list[dict]:
    """The files of the user's own TeX tree that the LaTeX ``sources`` (and ``extra_texts``,
    e.g. a front matter header-includes) pull in, and those they pull in, as
    {name, kind, path, version, sha256}: `name` is the file name a rebuild looks for. ``include_local``: a package or class
    that sits in the document's own folder counts too ("local": True, `name` its path from ``base``): a source that was
    restored with its package must keep it when it is attached again (v3.28.38)."""
    deps: list[dict] = []
    seen: set[Path] = set()
    queue: list[tuple[Path | None, str]] = []
    for source in sources:
        try:
            queue.append((source, source.read_text(encoding="utf-8-sig", errors="replace")))
        except OSError:
            continue
    queue.extend((None, text) for text in extra_texts)
    scanned = 0
    while queue and scanned < TEX_TREE_SCAN_LIMIT:
        origin, text = queue.pop(0)
        scanned += 1
        for kind, candidates in tex_names(text):
            local = next(((folder / candidate) for candidate in candidates
                          for folder in ([origin.parent] if origin else []) + [base] if (folder / candidate).is_file()), None)
            if local is not None and not (include_local and kind in ("package", "class", "input")):
                continue                                   # in the document's own folders: the folder's business
            hit = (Path(os.path.abspath(local)) if local is not None else
                   next((found for found in (find_in_tex_tree(candidate) for candidate in candidates) if found), None))
            if hit is None or hit in seen:
                continue
            seen.add(hit)
            try:
                content = hit.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            provides = PROVIDES_RE.search(content[:20000])
            is_local = local is not None
            deps.append({"name": core.relative_posix(base, hit) if is_local else hit.name, "kind": kind, "path": hit,
                         "version": " ".join(provides.group(1).split()) if provides else None,
                         "sha256": hashlib.sha256(hit.read_bytes()).hexdigest(), **({"local": True} if is_local else {})})
            if hit.suffix.lower() in TEX_SOURCE_SUFFIXES:
                queue.append((hit, content))
                if kind in ("package", "class"):
                    for graphic in graphics_named_in(content, (hit.parent,) if is_local else ()):
                        if graphic not in seen:
                            seen.add(graphic)
                            graphic_local = is_local and graphic.is_relative_to(base)
                            deps.append({"name": core.relative_posix(base, graphic) if graphic_local else graphic.name,
                                         "kind": "graphic", "path": graphic, "version": None,
                                         "sha256": hashlib.sha256(graphic.read_bytes()).hexdigest(),
                                         **({"local": True} if graphic_local else {})})
    return deps


def package_companions(deps: list[dict], base: Path) -> list[dict]:
    """The file that belongs beside a stored package and tells pdfmd about it (v3.28.38): `<package>-pdfmd.yaml` (its
    title-page keys, picture-cache names ...), as a dep of kind "companion". Without it a rebuilt source loses what the
    package asks pdfmd for. Its Lua filter is not stored here: one the build applied is embedded in the source already, and
    one it did not apply (a pre-lab does not) must not start to be applied by a rebuild. Its Word profile is for another
    output."""
    found: list[dict] = []
    for dep in deps:
        if dep["kind"] not in ("package", "class"):
            continue
        folder, stem = dep["path"].parent if dep.get("local") else dep["path"].resolve().parent, dep["path"].stem
        for place in core.package_places(folder):
            for name in (f"{stem}-pdfmd.yaml",):
                candidate = place / name
                local = Path(os.path.abspath(candidate)).is_relative_to(Path(os.path.abspath(base)))
                stored = core.relative_posix(base, candidate) if local else name
                if (candidate.is_file() and candidate.stat().st_size <= 2 * 1024 * 1024
                        and not any(item["name"] == stored for item in found)):
                    found.append({"name": stored, "kind": "companion", "path": candidate, "version": None,
                                  "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                                  **({"local": True} if local else {})})
    return found


def bundle_reach(base: Path) -> Path | None:
    """How far above the document's folder a source may keep files (v3.28.38): two folders up at most, never the home folder
    or a folder above it (a pre-lab's `../schemes/x.tex`, `../ir/x.csv` are siblings of its folder; --restore puts the folder
    back under the same sibling layout). None when there is no such folder."""
    home = Path.home().resolve()
    reach = None
    for parent in list(base.parents)[:2]:
        if len(parent.parts) < 3 or parent.resolve() == home or home.is_relative_to(parent.resolve()):
            break
        reach = parent
    return reach


def bundle_files(md_path: Path, parts: list[Path], preamble_files: list[Path] | None, mode: str,
                 represented: set[Path], output: Path, data_names: list[str],
                 base: Path | None = None, pictures: list[Path] | None = None,
                 reach: Path | None = None) -> tuple[list[Path], list[str]]:
    """The files to store beside the source (the source carries the Markdown,
    metadata, preamble, filters, bibliography and CSL itself): the images and data
    the text and the preamble point at, and what the text files among them point at
    in turn ("referenced"), the same without the images ("sources": the PDF holds
    those; the ones inside the folder go to ``pictures``), or every file in the
    document's folder that is not output or housekeeping ("all"). Returns (files
    inside the folder, names of referenced files outside it)."""
    base = Path(os.path.abspath(base or md_path.parent))
    found: list[Path] = []
    outside: list[str] = []

    def add(path: Path) -> bool:
        path = Path(os.path.abspath(path))
        if path in represented or path == Path(os.path.abspath(output)) or path in found:
            return False
        if mode == "sources" and path.suffix.lower() in BUNDLE_IMAGE_SUFFIXES:
            if pictures is not None and path not in pictures and path.is_relative_to(base):
                pictures.append(path)
            return False
        if path.name in data_names and path.suffix.lower() in (".bib", ".csl", ".bibtex"):
            return False                                 # already embedded in the source
        try:
            path.relative_to(base)
        except ValueError:
            if reach is not None and path.is_relative_to(reach):        # a sibling folder (`../schemes/x.tex`): see bundle_reach
                found.append(path)
                return True
            outside.append(str(path))
            return False
        found.append(path)
        return True

    if mode == "all":
        for folder, directories, names in os.walk(base):
            directories[:] = sorted(item for item in directories
                                    if not item.startswith(".") and item not in core.BUNDLE_SKIP_DIRS
                                    and not item.endswith((core.RESTORED_SUFFIX, core.UNPACKED_SUFFIX)))
            for name in sorted(names):
                full = Path(folder) / name
                if (name.startswith(".") or name.lower().endswith(BUNDLE_SKIP_SUFFIXES)
                        or full.is_symlink() and not full.exists()):
                    continue
                add(full)
        return found, outside
    # Each file taken is read in turn for the files it points at: a figure's .tex that
    # \inputs its raw data, a CSV a macro opens (to a depth no document needs).
    queue: list[Path] = [md_path, *parts, *(preamble_files or [])]
    scanned: set[Path] = set()
    while queue and len(scanned) < 400:
        source = queue.pop(0)
        if Path(os.path.abspath(source)) in scanned:
            continue
        scanned.add(Path(os.path.abspath(source)))
        deeper = source not in (md_path, *parts, *(preamble_files or []))
        if deeper and (source.suffix.lower() not in SCANNED_SUFFIXES or source.stat().st_size > 2 * 1024 * 1024):
            continue
        try:
            text = source.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        hits: list[Path] = []
        for image in referenced_images(text, source.parent, source.suffix.lower() in TEX_SOURCE_SUFFIXES):
            hits.append(image)
        visible = core.strip_markdown_comments(text) if source.suffix == ".md" else text
        for token in dict.fromkeys(PATH_TOKEN_RE.findall(visible)):
            for folder in (source.parent, base):
                try:
                    candidate = folder / token
                    if candidate.is_file():
                        hits.append(candidate)
                        break
                except OSError:
                    break
        for pattern in RAW_REFERENCE_RES:
            for match in pattern.finditer(visible):
                target = urllib.parse.unquote(match.group(1).strip())
                if not target or "://" in target:
                    continue
                for folder in (source.parent, base):
                    hit = next((Path(os.path.abspath(folder / (target + extension)))
                                for extension in REFERENCE_EXTENSIONS
                                if (folder / (target + extension)).is_file()), None)
                    if hit is not None:
                        hits.append(hit)
                        break
        for hit in hits:
            if add(hit):
                queue.append(hit)
    return found, outside


def attachment_manifest(md_path: Path, parts: list[Path], plan: "core.EmbedPlan | None",
                        merged: str, stripped: frozenset[str], chunks: list[dict],
                        base: Path | None = None, report: bool = False) -> dict:
    base = base or md_path.parent
    layout: list[dict] = []
    if plan is not None:
        for kind, paths in (("metadata", plan.metadata_files), ("preamble", plan.preamble_files),
                            ("lua", plan.lua_filters)):
            if kind in plan.kinds:
                # global: pdfmd's global metadata (pdfmd --setup), which --restore leaves to the machine (v3.28.13).
                # Its path relative to the document told how deep the folder was, and from outside the home
                # folder it held the user's name: a neutral one now (`..`, so no restore writes it anywhere)
                layout.extend({"kind": kind, "path": GLOBAL_LAYOUT_PATH, "global": True}
                              if kind == "metadata" and core.is_global_metadata(item)
                              else {"kind": kind, "path": layout_path(base, item)}
                              for item in paths)
        if "hst" in plan.kinds and plan.hst_file is not None:
            layout.append({"kind": "hst", "path": core.relative_posix(base, plan.hst_file)})
    images = []
    for source, latex in [(item, False) for item in (md_path, *parts)] + [
            (item, True) for item in (plan.preamble_files if plan else [])]:
        for image in referenced_images(source.read_text(encoding="utf-8-sig"), source.parent if not latex else base,
                                       latex):
            entry = {"path": core.relative_posix(base, image), "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                     "size": image.stat().st_size}
            if entry not in images:
                images.append(entry)
    metadata_texts: dict[str, str] = {}
    if plan is not None and "metadata" in plan.kinds and "metadata" not in stripped:
        for item in plan.metadata_files:
            if core.is_global_metadata(item):
                continue
            try:
                metadata_texts[layout_path(base, item)] = item.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                pass
    front_text = None
    if "metadata" not in stripped:             # the document's own front matter, as written (comments, quoting)
        try:
            found_front = re.match(r"^---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|$)",
                                   md_path.read_text(encoding="utf-8-sig"), re.DOTALL)
            front_text = found_front.group(0) if found_front else None
        except (OSError, UnicodeDecodeError):
            pass
    return {"format": ATTACH_FORMAT_PLAIN, "pdfmd": core.PDFMD_VERSION, "kind": "source",
            "mode": "report" if report else "document",
            "parts": (core.parts_setting(md_path, list(plan.metadata_files) if plan else []) if parts and not report else None),
            "name": core.relative_posix(base, md_path), "source": core.ATTACH_SOURCE, "sha256": core.sha256_text(merged),
            "comments_stripped": sorted(stripped), "no_auto": core.frontmatter_no_auto(md_path), "chunks": chunks,
            "bibliography": list(plan.bib_report) if plan else [],
            **({"csl_left": list(plan.csl_left)} if plan is not None and plan.csl_left else {}),
            "layout": layout, "data_files": [block["path"] or block["name"] for block in core.parse_embedded_blocks(merged)
                                             if block["type"] in ("bibliography", "csl")],
            "images": images, **({"metadata_texts": metadata_texts} if metadata_texts else {}),
            **({"front_matter_text": front_text} if front_text else {})}


def held_comments_note(manifest: dict, merged: str) -> str:
    """`comments_note` for the kinds of source the attached text holds (v3.33.48). The manifest's `comments_stripped` is the
    policy, every kind for --strip-comments; the note names only what is there: the Markdown always, the metadata when there is
    front matter or a metadata file, a preamble file, and the bibliography and CSL the text carries as blocks."""
    stripped = manifest.get("comments_stripped")
    if not isinstance(stripped, list):
        return core.comments_note(manifest)
    layout = {item.get("kind") for item in manifest.get("layout") or []}
    blocks = {block["type"] for block in core.parse_embedded_blocks(merged)}
    held = {"markdown", *(kind for kind in ("bibliography", "csl") if kind in blocks)}
    if "metadata" in layout or any(chunk.get("front_matter") for chunk in manifest.get("chunks") or []):
        held.add("metadata")
    if "preamble" in layout:
        held.add("preamble")
    return core.comments_note({**manifest, "comments_stripped": [kind for kind in stripped if kind in held]})


def attached_source(md_path: Path, parts: list[Path], metadata_files: list[Path],
                    preamble_files: list[Path] | None, no_auto: list[str] | None,
                    strip: frozenset[str], prune_bibliography: bool = True,
                    report: bool = False, base: Path | None = None, with_csl: bool = False) -> tuple[str, dict]:
    """The text to attach (the assembled file with everything embedded) and its manifest.
    ``report``: the files are the chapters of a -r/--report build, each keeping its own front matter."""
    plan = core.make_embed_plan(md_path, metadata_files, preamble_files, no_auto,
                           core.EmbedRequest(frozenset(core.EMBED_KINDS + (("csl",) if with_csl else ())), None, False))
    plan.bib_prune = prune_bibliography
    base = base or md_path.parent
    chunks: list[dict] = []
    for index, source in enumerate([md_path, *parts]):
        raw = core.strip_location_markers(source.read_text(encoding="utf-8-sig"))
        text = core.strip_part_front_matter(raw) if index and not report else raw
        head = raw[:len(raw) - len(text)] if index and raw.endswith(text) else ""
        if "markdown" in strip:
            text = core.strip_markdown_comments(text)
        chunk = text.rstrip("\n") + "\n"
        front = re.match(r"^---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|$)", chunk, re.DOTALL) if not index else None
        body = chunk[front.end():] if front else chunk
        # The assembled text normalises the blank lines at a boundary, so a chunk
        # is found again by its content: how many blank lines led it, then its lines.
        content = body.lstrip("\n")
        chunks.append({"path": core.relative_posix(base, source), "head": head,
                       "lead": len(body) - len(content), "lines": len(content.splitlines()),
                       "sha256": core.sha256_text(content), "front_matter": bool(front)})
    merged = core.assemble_markdown_text([md_path, *parts], bool(parts) and not report, plan, False, strip)
    return merged, attachment_manifest(md_path, parts, plan, merged, strip, chunks, base, report)


def resolve_bibliography_pruning(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether the attached bibliography keeps only the entries the text cites: the command line
    (--attach-bibliography used|all), else `pdfmd-options.attach-bibliography`, else yes."""
    value = core.BIB_ATTACH_CLI or core.first_pdfmd_option(md_path, metadata_files, "attach-bibliography", "attach-bib")
    return str(value).strip().casefold() not in {"all", "false", "no", "off", "whole", "full"}


def resolve_csl_attach(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether the attached source carries the citation style the metadata names: the command line (--attach-csl), else
    `pdfmd-options.attach-csl`, else no (v3.28.36: a style is 10-90 KB, and the global metadata sets one for every document)."""
    if core.CSL_ATTACH_CLI is not None:
        return core.CSL_ATTACH_CLI
    return bool(core.option_flag(core.first_pdfmd_option(md_path, metadata_files, "attach-csl")))


def add_deflated_attachment(writer: "pypdf.PdfWriter", name: str, data: bytes):
    """Embed ``data`` as ``name`` and return its stream; deflated, as any other stream in the PDF."""
    from pypdf.generic import DictionaryObject, NameObject, NumberObject
    embedded = writer.add_attachment(name, data)._embedded_file
    if len(data) > 256:
        embedded.set_data(zlib.compress(data, 9))
        embedded[NameObject("/Filter")] = NameObject("/FlateDecode")
        embedded[NameObject("/Params")] = DictionaryObject({NameObject("/Size"): NumberObject(len(data))})
    return embedded


def write_pdf_attachments(pdf_path: Path, files: dict[str, bytes]) -> None:
    """Add ``files`` to ``pdf_path`` as attachments, in place (written beside it,
    then moved over it, so a failure leaves the PDF as it was)."""
    pypdf_logger = logging.getLogger("pypdf")
    previous_level = pypdf_logger.level
    pypdf_logger.setLevel(logging.ERROR)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            writer = core.pypdf.PdfWriter(clone_from=pdf_path)      # the whole document: properties, bookmarks, files
            for name, data in files.items():
                add_deflated_attachment(writer, name, data)
            core.atomic_write_pdf(writer, pdf_path)
    finally:
        pypdf_logger.setLevel(previous_level)


def read_pdf_attachments(pdf_path: Path) -> dict[str, bytes]:
    pypdf_logger = logging.getLogger("pypdf")
    previous_level = pypdf_logger.level
    pypdf_logger.setLevel(logging.ERROR)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reader = core.pypdf.PdfReader(pdf_path)
            return {name: b"".join(items) if len(items) > 1 else items[0]
                    for name, items in reader.attachments.items() if items}
    finally:
        pypdf_logger.setLevel(previous_level)


FONT_KEYS = ("mainfont", "sansfont", "monofont", "mathfont", "CJKmainfont", "CJKsansfont", "CJKmonofont")


def resolve_bundle_packages(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether the TeX packages and classes of the user's own tree that a preamble loads are
    stored too: --bundle-packages, else `pdfmd-options.bundle-packages`."""
    if core.BUNDLE_PACKAGES_CLI is not None:
        return core.BUNDLE_PACKAGES_CLI
    return bool(core.option_flag(core.first_pdfmd_option(md_path, metadata_files, "bundle-packages")))


def attachment_requirements(merged: str, deps: list[dict], stored: set[str], pdf_path: Path | None) -> dict:
    """What a rebuild needs that the PDF does not carry: the user's own TeX files (name,
    version, whether stored), the fonts the metadata names, the tools that made it."""
    front = core.front_matter_dict(merged)
    producer = None
    try:
        info = core.pypdf.PdfReader(pdf_path).metadata if pdf_path is not None and core.pypdf is not None else None
        producer = str(info.get("/Producer") or info.get("/Creator") or "") or None if info else None
    except Exception:  # noqa: BLE001 -- a hint only
        pass
    fonts = []
    for key in FONT_KEYS:
        value = front.get(key)
        if isinstance(value, str) and value not in fonts:
            fonts.append(value)
    texlive = None
    if core.which("kpsewhich"):
        try:
            texlive = subprocess.run(["kpsewhich", "--version"], capture_output=True, encoding="utf-8", errors="replace",
                                     timeout=30).stdout.splitlines()[0].strip() or None
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    return {"pdfmd": core.PDFMD_VERSION, "pandoc": ".".join(map(str, core.pandoc_version())) or None,
            "producer": producer, "texlive": texlive,
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "platform": f"{platform.system()} {platform.machine()}", "fonts": fonts,
            "tex": [{"name": dep["name"], "kind": dep["kind"], "version": dep["version"],
                     "sha256": dep["sha256"], "stored": dep["name"] in stored} for dep in deps]}


def csv_block_files(merged: str, base: Path) -> dict[str, bytes]:
    """The files the `.csv` blocks of the attached text read (`file="tables/x.csv"`), as {path relative to the
    document's folder: bytes}: the ones that exist inside the folder and are small."""
    try:
        import pdfmd_tables
    except ImportError:
        return {}
    found: dict[str, bytes] = {}
    for block in pdfmd_tables.find_csv_blocks(merged):
        name = block.attributes.get("file")
        if not name or "://" in name or Path(name).is_absolute():
            continue
        path = Path(os.path.abspath(base / name))
        try:
            path.relative_to(Path(os.path.abspath(base)))
        except ValueError:
            continue
        if path.is_file() and path.stat().st_size <= 5 * 1024 * 1024:
            found[core.relative_posix(base, path)] = path.read_bytes()
    return found


def source_attachments(md_path: Path, output: Path, parts: list[Path], metadata_files: list[Path],
                       preamble_files: list[Path] | None, no_auto: list[str] | None,
                       report: bool = False, base: Path | None = None) -> tuple[dict[str, bytes], str, dict]:
    """The files a build's source is kept as -- the assembled Markdown, a manifest of the layout, the data and
    bundled files -- as {name: bytes}, with the merged text and the manifest. They go into a PDF (--attach-source)
    or after a Markdown output (--keep-source); ``output`` is the file they will belong to."""
    base = Path(os.path.abspath(base or md_path.parent))
    is_pdf = output.suffix.lower() == ".pdf"
    with contextlib.redirect_stdout(io.StringIO()):       # the embed notes are for --assemble-only
        merged, manifest = attached_source(md_path, parts, metadata_files, preamble_files, no_auto,
                                           core.resolve_strip_comments(md_path, metadata_files, default=True),
                                           resolve_bibliography_pruning(md_path, metadata_files),
                                           report=report, base=base, with_csl=resolve_csl_attach(md_path, metadata_files))
    extras: dict[str, bytes] = {}
    origins: dict[str, str] = {}
    # A chosen kit's parts (its package, the library it inputs, its logos: the `carry:` list) are stored whether or not the
    # folder is bundled: the source holds the LaTeX the kit wrote, and a rebuild with no kit on the machine needs the files.
    kits_here = core.active_kits(md_path, metadata_files, no_auto)
    kit_record: list[dict] = []
    if kits_here:
        limit_mb = core.option_flag_number(core.first_pdfmd_option(md_path, metadata_files, "bundle-max-mb")) or core.BUNDLE_MAX_MB
        carried, kit_record, kit_notes = core.kit_carried_files(kits_here, base, float(limit_mb) * 1024 * 1024)
        for line in kit_notes:
            print(line, file=sys.stderr)
        for name, path in carried.items():
            if name not in extras:
                extras[name] = path.read_bytes()
                origins[name] = "kit"
    mode = attached_bundle_mode(md_path, metadata_files, is_pdf)
    header_text = core.header_includes_text(core.front_matter_dict(merged).get("header-includes"))
    packages = resolve_bundle_packages(md_path, metadata_files)
    deps = tex_tree_dependencies(core.kit_embedded_preambles(md_path, metadata_files, preamble_files),
                                 [header_text] if header_text else [], base, packages)
    if mode:
        represented = {Path(os.path.abspath(base / item["path"]))
                       for item in [*manifest["chunks"], *manifest["layout"]]}
        pictures: list[Path] = []
        found, outside = bundle_files(md_path, parts, preamble_files, mode, represented, output,
                                      manifest["data_files"], base, pictures, bundle_reach(base))
        core.add_calc_constants(md_path, metadata_files, base, represented, found, outside)
        core.drop_calc_export(md_path, [md_path, *parts], metadata_files, found, outside)
        up = next((count for count in (1, 2) if all(item.is_relative_to(base.parents[count - 1])
                                                    for item in found if not item.is_relative_to(base))), 0) \
            if any(not item.is_relative_to(base) for item in found) else 0
        if up:
            # the folder comes back under the same sibling layout: its path from the folder `up` levels above
            manifest["chain"] = list(base.relative_to(base.parents[up - 1]).parts)
        # A picture only an \input'ed .tex draws is recorded like the text's own, so --restore can take it out of the PDF
        for picture in pictures:
            entry = {"path": core.relative_posix(base, picture), "sha256": hashlib.sha256(picture.read_bytes()).hexdigest(),
                     "size": picture.stat().st_size}
            if entry["path"] not in {image["path"] for image in manifest["images"]}:
                manifest["images"].append(entry)
        from_tree = [dep for dep in deps if (dep["kind"] == "input" or packages)
                     and (dep.get("local") or not (base / dep["name"]).exists())]
        if packages:
            from_tree += [dep for dep in package_companions(from_tree, base)
                          if dep.get("local") or not (base / dep["name"]).exists()]
        limit = float(core.option_flag_number(core.first_pdfmd_option(md_path, metadata_files, "bundle-max-mb"))
                      or core.BUNDLE_MAX_MB) * 1024 * 1024
        total = sum(item.stat().st_size for item in found) + sum(dep["path"].stat().st_size for dep in from_tree)
        if total > limit:
            print(f"WARN  bundle: {len(found) + len(from_tree)} files, {total / 1048576:.0f} MB, is over the "
                  f"{limit / 1048576:.0f} MB limit (pdfmd-options.bundle-max-mb); only the source was attached",
                  file=sys.stderr)
        else:
            stripping = "markdown" in manifest["comments_stripped"]
            for item in found:
                data = item.read_bytes()
                if stripping and item.suffix.lower() in (".md", ".markdown"):
                    try:
                        data = core.strip_markdown_comments(data.decode("utf-8-sig")).encode("utf-8")
                    except UnicodeDecodeError:
                        pass
                extras[core.relative_posix(base, item)] = data
            for dep in from_tree:
                if dep["name"] not in extras:
                    extras[dep["name"]] = dep["path"].read_bytes()
                    if not dep.get("local"):
                        origins[dep["name"]] = "tex-tree"
            manifest["bundle"] = mode
            manifest["outside"] = sorted({Path(name).name for name in outside})
    # The data a `.csv` block names is part of the source (the merged text cannot build without it), and
    # small: it is stored even when the rest of the folder is not bundled.
    for name, data in csv_block_files(merged, base).items():
        if name not in extras:
            extras[name] = data
    # A source that was edited as one file (--edit) already holds its files as blocks, and its embedded data again: a file
    # found now replaces its block, one not found now (no copy beside the document) is carried on as the block it is
    for block in core.parse_embedded_blocks(merged):
        if block["type"] == "file":
            for place in block_places(block):
                if place not in extras and place in inline_candidates({place: block["bytes"]}):
                    extras[place] = block["bytes"]
    inline = inline_candidates(extras)
    merged = drop_blocks(merged, lambda fields: fields.get("type") == "file" and fields.get("path", fields.get("name")) in inline)
    merged = drop_duplicate_blocks(merged)
    if inline:
        cut = core.first_block_start(merged)
        merged = merged[:cut].rstrip("\n") + "\n" + inline_blocks(inline) + ("\n" if cut < len(merged) else "") + merged[cut:]
    merged = core.with_location_markers(merged)
    manifest["sha256"] = core.sha256_text(merged)
    if extras:
        manifest["extras"] = [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                               **({"from": origins[name]} if name in origins else {}),
                               **({"inline": True} if name in inline else {})}
                              for name, data in extras.items()]
    if is_pdf:
        core.match_images_to_pdf(output, [image for image in manifest["images"] if image["path"] not in extras], base)
    manifest["requirements"] = attachment_requirements(merged, deps, set(extras), output if is_pdf else None)
    if kit_record:
        manifest["kits"] = kit_record
    layers = folder_options_in_force(md_path) if core.yaml is not None else {}
    if layers:
        manifest["layers"] = {"options": layers}
        manifest["format"] = core.ATTACH_FORMAT
    attachments = {
        core.ATTACH_SOURCE: merged.encode("utf-8"),
        core.ATTACH_MANIFEST: json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"),
        **{core.extra_key(name): data for name, data in extras.items() if name not in inline}}
    return attachments, merged, manifest


@_timed("attach source")
def attach_source_after_success(md_path: Path, pdf_path: Path, parts: list[Path],
                                metadata_files: list[Path], preamble_files: list[Path] | None,
                                no_auto: list[str] | None, verbose: bool,
                                report: bool = False, base: Path | None = None) -> None:
    """--attach-source: put the document's source into the PDF just built. ``report``: the
    files are the chapters of a -r/--report build; ``base`` the folder their layout is relative to."""
    if pdf_path.suffix.lower() != ".pdf" or not pdf_path.is_file():
        return
    if core.pypdf is None:
        print("WARN  attach-source: pypdf is not installed (pip install pypdf); nothing was attached",
              file=sys.stderr)
        return
    base = Path(os.path.abspath(base or md_path.parent))
    try:
        attachments, merged, manifest = source_attachments(md_path, pdf_path, parts, metadata_files, preamble_files, no_auto,
                                                           report, base)
        write_pdf_attachments(pdf_path, attachments)
    except Exception as error:  # noqa: BLE001 -- the PDF itself is fine; say so and carry on
        print(f"WARN  attach-source: could not attach the source to {core.display_path(pdf_path)} ({error}); "
              "the PDF itself was built", file=sys.stderr)
        return
    note = held_comments_note(manifest, merged)
    kept = manifest.get("extras") or []
    print(f"ATTACHED  {core.display_path(pdf_path)}: source of {core.display_path(md_path)}"
          + (f" and {len(parts)} more" if report and parts else "")
          + f" ({len(merged.splitlines())} lines, {note}"
          + (f", plus {len(kept)} file{'s' if len(kept) != 1 else ''}, "
             f"{sum(item['size'] for item in kept) / 1048576:.1f} MB" if kept else "")
          + "); `pdfmd --restore` writes it back")
    stored = {item["path"] for item in kept}
    unstored = [image["path"] for image in manifest["images"] if image["path"] not in stored]
    if unstored:
        core.vprint(verbose, f"NOTE  images the text points at are recorded, not stored (the PDF holds them; "
              f"`--bundle referenced` stores the files): {', '.join(unstored)}")
    if manifest.get("outside"):
        print(f"NOTE  not stored, outside the document's folder: {', '.join(manifest['outside'])}")
    for line in core.requirement_lines(manifest):
        if line.startswith("NEEDS") and "not stored" in line:
            print("NOTE  " + line[10:])
        else:
            core.vprint(verbose, line)


def keep_source_after_success(md_path: Path, output: Path, parts: list[Path], metadata_files: list[Path],
                              preamble_files: list[Path] | None, no_auto: list[str] | None, mode: str,
                              verbose: bool, ascii_only: bool = False, pandoc_options: list[str] | None = None) -> None:
    """--keep-source: end the Markdown just written with its source. For an ASCII build the trailer is ASCII too: the
    packed form, with the source's name spelt in ASCII (the readable form would carry the Unicode source as it is).

    The preambles are found here when the build had none (v3.33.64): a Markdown build does not look for them (they are
    LaTeX's), so the kept source had no `preamble.tex`, nor the files it `\\input`s, where a PDF's attached one has both.
    Found as a PDF build finds them (`document_preambles`, with the run's Pandoc options: an `--include-in-header` still
    stops the search), for the kept source only: the Markdown written is as before."""
    if not preamble_files:
        preamble_files = core.document_preambles(md_path, list(pandoc_options or []), no_auto)
    try:
        import pdfmd_flat.keep as keep
    except ImportError:
        print("WARN  keep-source: needs the pdfmd_flat package (install pdfmd-cli); the source was not kept",
              file=sys.stderr)
        return
    if not output.is_file():
        return
    try:
        entries, merged, manifest = source_attachments(md_path, output, parts, metadata_files, preamble_files, no_auto)
        written = output.read_bytes().decode("utf-8")
        body, old = keep.split(written)        # a file written by this run never has one; a stale one would be replaced
        label = md_path.name
        if ascii_only:
            if mode == "readable":
                print("NOTE  keep-source: an ASCII file keeps its source packed (the readable form would be Unicode)",
                      file=sys.stderr)
                mode = "packed"
            import pdfmd_flat.asciify as asciify
            label = asciify.Asciifier().text(label)
        trailer = keep.pack(entries, body, mode, label, core.PDFMD_VERSION)
        core.atomic_write_bytes(output, keep.append(body, trailer).encode("utf-8"))
    except Exception as error:  # noqa: BLE001 -- the Markdown itself is fine; say so and carry on
        print(f"WARN  keep-source: could not keep the source in {core.display_path(output)} ({error}); "
              "the Markdown itself was written", file=sys.stderr)
        return
    kept = manifest.get("extras") or []
    print(f"KEPT      {core.display_path(output)}: source of {core.display_path(md_path)}"
          + (f" and {len(parts)} more" if parts else "")
          + f" ({len(merged.splitlines())} lines, {held_comments_note(manifest, merged)}"
          + (f", plus {len(kept)} file{'s' if len(kept) != 1 else ''}" if kept else "")
          + f"; {mode}, {len(trailer) / 1024:.0f} KB); `pdfmd --restore {output.name}` writes it back")
    if len(trailer.encode("utf-8")) > keep.WARN_BYTES:
        print(f"WARN  keep-source: the kept source is {len(trailer) / 1048576:.1f} MB; GitHub and some editors stop "
              "showing a Markdown file this large (--no-keep-source, or --attach-source on a PDF, keeps it out)",
              file=sys.stderr)
