"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_attach.options`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pdfmd_base import core


ATTACH_FORMAT = 3


ATTACH_MANIFEST = "pdfmd-manifest.json"


ATTACH_SOURCE = "pdfmd-source.md"

ATTACH_EXCERPTS = "excerpts.json"

ATTACH_KEYS = ("attach-source", "embed-source")


BUNDLE_MAX_MB = 100


EXTRA_PREFIX = "files/"


RESTORED_SUFFIX = ".restored"


BUNDLE_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", "venv", "env"})


IMAGE_REF_RE = re.compile(
    r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)|<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"']",
    re.IGNORECASE)


def resolve_attach(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether the PDF built from ``md_path`` carries its source: the command
    line, else `pdfmd-options.attach-source` (or `embed-source`)."""
    if resolve_bundle(md_path, metadata_files):
        return core.ATTACH_CLI is not False           # a bundle is a source plus files; --no-attach-source still wins
    return private_attach(md_path, metadata_files) or bool(core.option_flag(attach_value(md_path, metadata_files)))


def attach_value(md_path: Path, metadata_files: list[Path]):
    value = core.ATTACH_CLI
    return core.first_pdfmd_option(md_path, metadata_files, *ATTACH_KEYS) if value is None else value


def private_attach(md_path: Path, metadata_files: list[Path]) -> bool:
    return str(attach_value(md_path, metadata_files)).strip().casefold() == "private"


def resolve_bundle(md_path: Path, metadata_files: list[Path]) -> str | None:
    """``None`` (no bundle), "sources" (the files the text reads: LaTeX inputs and data, never images),
    "referenced" (those and the images) or "all" (everything in the document's folder worth keeping):
    the command line, else `pdfmd-options.bundle` (sources / true / all / false)."""
    if core.BUNDLE_CLI is not None:
        return None if core.BUNDLE_CLI == "off" else core.BUNDLE_CLI
    value = core.first_pdfmd_option(md_path, metadata_files, "bundle")
    word = str(value).strip().casefold()
    if word in ("all", "sources", "referenced"):
        return word
    if word == "source":
        return "sources"
    return "referenced" if core.option_flag(value) else None


def extra_key(path: str) -> str:
    """The attachment name of a stored file: `../schemes/x.tex` is `files/__up__/schemes/x.tex` (a viewer that saves an
    attachment by its name must not climb out of its folder)."""
    return EXTRA_PREFIX + "/".join("__up__" if part == ".." else part for part in path.split("/"))


def relative_posix(base: Path, path: Path) -> str:
    # not resolve(): a symlinked metadata file is recorded where it sits, not where it points
    return Path(os.path.relpath(os.path.abspath(path), os.path.abspath(base))).as_posix()


GRAPHIC_RE = re.compile(r"\\includegraphics\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")


def drop_calc_export(md_path: Path, sources: list[Path], metadata_files: list[Path], found: list[Path], outside: list) -> None:
    """The file `calc: {export: FILE}` writes is an output: it does not go with the source (v3.30.22), though its name stands in the
    front matter and the file is there. It stays when it is also read: it is the constants file, or the body of the document
    names it (a `.csv` div reading last time's results)."""
    LEADING_FRONT_MATTER_RE = core.LEADING_FRONT_MATTER_RE
    target = core.calc_export_file(md_path, metadata_files)
    if target is None:
        return
    target = Path(os.path.abspath(target))
    try:
        constants = core.calc_constants_file(md_path, metadata_files)
    except SystemExit:
        constants = None
    if constants is not None and Path(os.path.abspath(constants)) == target:
        return
    for source in sources:
        if target.name in LEADING_FRONT_MATTER_RE.sub("", core.read_text_best_effort(source), count=1):
            return
    found[:] = [item for item in found if Path(os.path.abspath(item)) != target]
    outside[:] = [item for item in outside if Path(os.path.abspath(str(item))) != target]


def add_calc_constants(md_path: Path, metadata_files: list[Path], base: Path, represented: set[Path],
                       found: list[Path], outside: list[str]) -> None:
    """The calculator's constants file (`calc: {constants: FILE}`) goes with the source like the history file (v3.30.12): a name
    in a metadata file is no path the text mentions, so the scan for referenced files would not find it."""
    try:
        constants = core.calc_constants_file(md_path, metadata_files)
    except SystemExit:
        return
    if constants is None:
        return
    constants = Path(os.path.abspath(constants))
    if constants in found or constants in represented:
        return
    (found if constants.is_relative_to(base) else outside).append(constants if constants.is_relative_to(base) else str(constants))


def comments_note(manifest: dict) -> str:
    """'comments stripped (markdown, preamble)' / 'comments kept' from a manifest
    (format 1 once held a plain true/false: all of the Markdown's)."""
    stripped = manifest.get("comments_stripped")
    if isinstance(stripped, list):
        return f"comments stripped from {', '.join(stripped)}" if stripped else "comments kept"
    return "comments stripped" if stripped else "comments kept"


def requirement_lines(manifest: dict) -> list[str]:
    """What a rebuild needs that the PDF does not carry, one line a kind (packages, graphics), then the fonts
    and (--verbose) what made the PDF."""
    needs = manifest.get("requirements") or {}
    lines = []
    missing: dict[str, list[str]] = {}
    for item in needs.get("tex") or []:
        if not item.get("stored"):
            version = f" ({item['version']})" if item.get("version") else ""
            missing.setdefault(item["kind"], []).append(f"{item['name']}{version}")
    for kind, names in missing.items():
        lines.append(f"NEEDS     {kind}{'s' if len(names) != 1 else ''} {', '.join(names)}: from the author's own TeX "
                     "tree, not stored (install it, or build with bundle-packages)")
    for kit in manifest.get("kits") or []:
        lines.append(f"KIT       {kit['name']}" + (f" {kit['version']}" if kit.get("version") else "")
                     + (f" (mode {kit['mode']})" if kit.get("mode") else "")
                     + (f": its {len(kit['carried'])} parts are stored" if kit.get("carried") else "")
                     + "; what it wrote is in the source (`kit: none` says so), so a rebuild needs no kit")
    layers = (manifest.get("layers") or {}).get("options")
    if layers:
        lines.append(f"FOLDER    settings the build used: {', '.join(str(key) for key in layers)}"
                     f"; written to {core.FOLDER_DIR}/config.yaml of the restored folder")
    if needs.get("fonts"):
        lines.append(f"NEEDS     fonts: {', '.join(needs['fonts'])}")
    made = [f"pdfmd {needs['pdfmd']}" if needs.get("pdfmd") else "", f"pandoc {needs['pandoc']}" if needs.get("pandoc") else "",
            needs.get("producer") or "", needs.get("texlive") or "", needs.get("platform") or "",
            needs.get("created") or ""]
    if any(made):
        lines.append(f"MADE WITH {', '.join(item for item in made if item)}")
    return lines


MARKDOWN_TARGETS = frozenset({"gfm", "gfm+raw", "markdown", "commonmark", "commonmark_x", "markdown_strict"})


def resolve_keep_source(md_path: Path, metadata_files: list[Path]) -> str | None:
    """"packed", "readable" or None: the command line, else `pdfmd-options.keep-source`."""
    value = core.KEEP_SOURCE_CLI if core.KEEP_SOURCE_CLI is not None else core.first_pdfmd_option(md_path, metadata_files, "keep-source")
    if value in (None, False) or str(value).strip().casefold() in ("", "false", "no", "off", "0"):
        return None
    name = str(value).strip().casefold()
    if value is True or name in ("true", "yes", "on", "1"):
        return "packed"
    if name not in ("packed", "readable"):
        raise SystemExit(f"keep-source {value!r}: choose packed (the default), readable, or false")
    return name
