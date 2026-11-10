"""A kit's `markup-off:` (v3.33.68): kinds of pdfmd's universal markup that a kit takes out of the list, for the documents built
with it (`markup-off: [landscape]`, where a house style's own LaTeX does that job). The words are read by `kitfile` as written
and checked here against pdfmd's kinds (`MARKUP_KINDS`), with a WARN naming the kit file for a word that is not one.

The kit's switch is a layer like its `no-auto:`: weaker than the command line (`--markup`, `--no-markup`), the document's
front matter, its own metadata files and the folders' files, which set `markup:` themselves and are then used as they are;
stronger than the config file, a preset, the global metadata, the kit's own metadata files and the flavour's default list,
from which the kit's words are taken out.

`core` is the `pdfmd` module, bound by `pdfmd.py` when the module is first loaded (a stand-in there loads it on the first
call); the pdfmd names it reads (`KIT_METADATA`, `MARKUP_KINDS`, `VERBOSE_OUTPUT`, `active_kits`, `folder_layers`,
`frontmatter_pdfmd_options`, `is_global_metadata`, `metadata_file_yaml`, `metadata_files_by_priority`) are read as `core.X`.
"""

from __future__ import annotations

import sys
from pathlib import Path

core = None

_TOLD: set[tuple[str, str]] = set()          # (what, where) already said: the list is worked out more than once a build


def _say_once(what: str, where: str, line: str, stream=None) -> None:
    if (what, where) not in _TOLD:
        _TOLD.add((what, where))
        print(line, file=stream or sys.stdout)


def markup_set_above_kit(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether the `markup` value in force comes from a place stronger than a kit: the document's front matter, one of its own
    metadata files (not a kit's, not the global metadata or a preset), a folder's files. The places are read in the order
    first_pdfmd_option reads them, so the answer is about the value that is used."""
    if "markup" in core.frontmatter_pdfmd_options(md_path):
        return True
    for path in core.metadata_files_by_priority(metadata_files):
        options = core.metadata_file_yaml(path).get("pdfmd-options")
        if isinstance(options, dict) and "markup" in options:
            return not (path in core.KIT_METADATA or core.is_global_metadata(path))
    return any(isinstance(options, dict) and "markup" in options for _, options in core.folder_layers(md_path))


def kit_markup_off(md_path: Path, metadata_files: list[Path], kinds: list[str]) -> list[str]:
    """``kinds`` without the words of the chosen kits' `markup-off:`, unless a place above the kit set `markup` itself."""
    words: list[str] = []
    for item in core.active_kits(md_path, metadata_files, None):
        for word in item.kit.markup_off:
            if word in core.MARKUP_KINDS:
                if word not in words:
                    words.append(word)
            else:
                _say_once(word, str(item.kit.path), f"WARN  {item.kit.path}: `markup-off: {word}` is not a kind of universal markup "
                          f"({', '.join(core.MARKUP_KINDS)}); ignored", sys.stderr)
    off = [kind for kind in kinds if kind in words]
    if not off or markup_set_above_kit(md_path, metadata_files):
        return kinds
    if core.VERBOSE_OUTPUT:
        _say_once("verbose", str(md_path), f"AUTO KIT  switches off markup {', '.join(off)} (markup-off in the kit)")
    return [kind for kind in kinds if kind not in words]
