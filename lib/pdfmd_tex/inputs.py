"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_tex.inputs`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import hashlib
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory, mkdtemp
from textwrap import dedent
from typing import Iterator

from pdfmd_base import core
from pdfmd_reader.controls import repair_controls


# Folders holding files an assembled document embeds (its bibliography and CSL
# blocks, extracted for the length of one build) or that --unpack wrote for it:
# searched after everything else, so they only decide a lookup that would
# otherwise fail. Set by embedded_resources(); read by resource_path_option()
# (Pandoc's citeproc) and tex_search_env() (BibTeX/Biber, via BIBINPUTS).
EMBEDDED_RESOURCE_DIRS: list[Path] = []


def resource_path_option(document_directory: Path, pandoc_cwd: Path,
                         metadata_files: list[Path] | None = None) -> list[str]:
    """--resource-path to keep image/include lookups anchored to the
    document's own directory even when pandoc_cwd points elsewhere.

    pandoc_cwd (see convert_one and main()'s report-mode branch) normally
    equals document_directory, but is set to the first discovered metadata
    file's own directory instead -- an ACCESSORY_DIRNAME subfolder (see
    accessory_directories()), or an explicit -y from a shared directory --
    so that a preamble's raw LaTeX \\input (e.g. a shared chemicals.tex) and
    a metadata.yaml's own relative bibliography:/csl: keys resolve against
    THAT directory. Without this, a document's own relative image paths
    would silently resolve against the same directory instead of the
    document's, the moment metadata moves out of the document's own folder.
    A no-op whenever the two already coincide -- every pipeline that doesn't
    use a metadata/ subfolder or an out-of-tree -y keeps its exact previous
    command line.

    A metadata file that is a SYMLINK also adds its target's real directory,
    at the end of the list (v3.11.0). Pandoc resolves `bibliography:` through
    --resource-path, so one shared metadata file symlinked into many folders
    can say `bibliography: refs.bib` for the refs.bib beside its real copy,
    instead of hard-coding an absolute path. Appended last, so it only
    decides a lookup that would otherwise fail: anything that resolves
    today still resolves to the same file.
    """
    extra: list[Path] = []
    for metadata in metadata_files or []:
        real_directory = metadata.resolve().parent
        if real_directory != metadata.parent.resolve() and real_directory not in extra:
            extra.append(real_directory)
    for metadata in metadata_files or []:                      # a kit's own folder (its csl and bibliography are found by name),
        folder = core.KIT_METADATA.get(metadata)                    # a folder layer's and the global metadata's: they do not move the cwd
        if folder is None and (core.is_folder_metadata(metadata) or core.is_global_metadata(metadata) or core.deferred("pdfmd_metadata", "is_parent_metadata")(metadata)):
            folder = metadata.parent
        if folder is not None and folder not in extra and folder != pandoc_cwd:
            extra.append(folder)
    extra += [directory for directory in EMBEDDED_RESOURCE_DIRS if directory not in extra]
    if document_directory == pandoc_cwd and not extra:
        return []
    entries = ([str(document_directory)] if document_directory != pandoc_cwd else []) + ["."]
    return ["--resource-path", os.pathsep.join(entries + [str(d) for d in extra])]


def kit_search_folders(document: Path | None) -> list[str]:
    """The TeX search path entries of the kits chosen for ``document``: each kit's folder and its package's folder
    and, `//` recursive, the folders its `carry:` names (a logo found by its bare name). The kit's whole folder is not searched
    recursively: it may hold a repository's worth of data. They come after the default path, so an installed copy is the same file
    or stays where it was."""
    if document is None or core.yaml is None:
        return []
    found: list[str] = []
    for item in core.active_kits(document, None, None):
        found.append(str(item.kit.folder))
        found.append(str(item.package_folder))
        found += [f"{item.kit.folder / entry.rstrip('/')}//" for entry in item.kit.carry
                  if (item.kit.folder / entry.rstrip("/")).is_dir()]
    return list(dict.fromkeys(found))


TECTONIC_SEARCH_ENV = "PDFMD_TECTONIC_SEARCH"        # tex_search_env -> run_tex_engine: the folders below, joined with os.pathsep


def tectonic_search_folders(document: Path | None) -> list[str]:
    """The folders of the chosen kits as Tectonic wants them. Tectonic reads no TEXINPUTS: a file is found in its own bundle unless
    `-Z search-path=DIR` names the folder, and that option takes one folder, not a tree. Without it the class a kit ships is never
    loaded: Tectonic builds, and says nothing, with the copy in its bundle. So the kit's folder and every folder under the entries
    that kit_search_folders gives as a tree (`carry:`, the `//` ones) are listed one by one; a hidden folder is left out."""
    folders: list[str] = []
    for entry in kit_search_folders(document):
        tree = entry.endswith("//")
        top = Path(entry[:-2] if tree else entry)
        folders.append(str(top))
        if tree:
            folders += [str(path) for path in sorted(top.rglob("*"))
                        if path.is_dir() and not any(part.startswith(".") for part in path.relative_to(top).parts)]
    return list(dict.fromkeys(folders))


def tex_search_env(document_directory: Path, pandoc_cwd: Path, document: Path | None = None) -> dict[str, str] | None:
    """TEXINPUTS for the pdf-engine subprocess, so a raw LaTeX command with a
    relative path still resolves against the document's own directory even
    when pandoc_cwd points elsewhere (see resource_path_option's docstring
    for why pandoc_cwd can differ from document_directory at all).

    --resource-path (resource_path_option, above) only helps PANDOC'S OWN
    image resolution -- a real Image AST node from Markdown ``![]()``
    syntax. Per pandoc's own manual, it "only has an effect when pandoc
    itself needs to find an image... It will not cause image paths to be
    rewritten in other cases (e.g., when pandoc is generating LaTeX)." Raw
    LaTeX passed through untouched -- a bare ``\\includegraphics{...}``, or
    any package macro that reads a data file by relative path (e.g.
    nulabreport's ``\\irspectrum``/``\\irspectrumcompare``, which hand a
    relative CSV path to pgfplots' own table-reading machinery) -- is
    resolved entirely by the TeX engine's own kpathsea search relative to
    ITS working directory (pandoc_cwd), not document_directory. Found via a
    real report (LR4-5): a metadata/ subfolder pulled pandoc_cwd away from
    the document's own directory and broke BOTH kinds of reference the same
    way -- \\includegraphics (TLC contour figures) and pgfplots table reads
    (IR spectra CSVs). A report-local \\graphicspath fixed the first alone;
    TEXINPUTS is the one mechanism kpathsea honors for every one of these at
    once, so it belongs here rather than in a per-project preamble.

    Returns None (meaning: leave the subprocess's environment untouched --
    exactly today's behavior) when document_directory == pandoc_cwd, the
    common case with no metadata/ subfolder or out-of-tree -y in play,
    where nothing is broken and nothing needs fixing.
    """
    kit_dirs = kit_search_folders(document)
    if document_directory == pandoc_cwd and not EMBEDDED_RESOURCE_DIRS and not kit_dirs:
        return None
    env = os.environ.copy()
    if document_directory != pandoc_cwd:
        env["TEXINPUTS"] = f"{document_directory}{os.pathsep}{env.get('TEXINPUTS', '')}"
    if EMBEDDED_RESOURCE_DIRS:
        # (a trailing separator keeps the default search path after these)
        env["BIBINPUTS"] = (os.pathsep.join(str(item) for item in EMBEDDED_RESOURCE_DIRS)
                            + os.pathsep + env.get("BIBINPUTS", ""))
        env["TEXINPUTS"] = (((env.get("TEXINPUTS") or ".").rstrip(os.pathsep)) + os.pathsep
                            + os.pathsep.join(str(item) for item in EMBEDDED_RESOURCE_DIRS) + os.pathsep)
    if kit_dirs:                                              # a kit works from its folder, with no install into the TeX tree
        for name in ("TEXINPUTS", "BIBINPUTS"):
            env[name] = (((env.get(name) or ".").rstrip(os.pathsep)) + os.pathsep + os.pathsep.join(kit_dirs) + os.pathsep)
        env[TECTONIC_SEARCH_ENV] = os.pathsep.join(tectonic_search_folders(document))
    return env


def frontmatter_pdfmd_options(md_path: Path) -> dict:
    """Parse a document's own ``pdfmd-options:`` front-matter block.

    A real YAML parse (not the regex sniffing the rest of this script uses
    for single scalar keys) because this block can be an arbitrarily
    nested mapping -- ``no-auto: [monofont, margin]`` and
    ``no-auto: true`` both have to parse correctly, not just be detected.
    Returns {} if there's no front matter, no ``pdfmd-options`` key, the
    front matter doesn't parse as YAML, or YAML support is unavailable --
    document-level pdfmd-options are optional sugar, not a hard dependency
    of the rest of the script. Also {} for a binary office document
    (OFFICE_INPUT_EXTENSIONS) without even trying to read it as text --
    caught via a real crash (UnicodeDecodeError) the first time an actual
    .docx/.pptx was fed through pdfmd for this round's own office-direct
    feature: effective_no_auto()/resolve_engines() call this
    unconditionally for every input, .tex and now office documents
    included, on the way to either one's own direct (non-Pandoc) branch.
    """
    if core.yaml is None or md_path.suffix.lower() in core.OFFICE_INPUT_EXTENSIONS:
        return {}
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return {}
    try:
        data = core.yaml.safe_load(front_matter.group(1))
    except core.yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return core.load_package("pdfmd_args.options").from_mapping(data, md_path)


def hoist_code_header(cmd: list[str]) -> None:
    """Put the code-wrapping header (code_wrap.tex) before every other --include-in-header of ``cmd``. fvextra loads lineno,
    which patches the display-math environments; a class or package that patches them too (nulabreport's preamble) must
    come after it to patch on top, not before it to be patched over (\\begin{linenomath} ended by \\end{equation*})."""
    positions = [index for index, item in enumerate(cmd[:-1]) if item == "--include-in-header"]
    mine = [index for index in positions if cmd[index + 1].endswith("code_wrap.tex")]
    if not mine or mine[0] == positions[0]:
        return
    pair = cmd[mine[0]:mine[0] + 2]
    del cmd[mine[0]:mine[0] + 2]
    cmd[positions[0]:positions[0]] = pair


def header_includes_latex(value) -> str | None:
    """A `header-includes:` value as the LaTeX it holds: list items one per line, through raw_latex_only."""
    items = value if isinstance(value, list) else [value]
    lines = [raw_latex_only(str(item)).strip() for item in items if item is not None]
    return "\n".join(line for line in lines if line).strip() or None


def pandoc_header_includes(sources: list[Path], metadata_files: list[Path]) -> tuple[str, str] | None:
    """The `header-includes` Pandoc keeps when the command line has no --include-in-header, as (LaTeX, where):
    "document" for the last source that has its own (they beat every metadata file), else "metadata" for the last
    metadata file in Pandoc's order that has them (checked on Pandoc 3.12 and 3.1.3). None when nothing has any."""
    for source in reversed(sources):
        text = document_header_includes(core.read_text_best_effort(Path(source)))
        if text:
            return text, "document"
    for path in reversed(core.pandoc_metadata_order(metadata_files)):
        data = core.metadata_file_yaml(path) or core.front_matter_dict(core.read_text_best_effort(path))
        if "header-includes" in data:
            text = header_includes_latex(data["header-includes"])
            return (text, "metadata") if text else None
    return None


def keep_header_includes(cmd: list[str], sources: list[Path], metadata_files: list[Path], pandoc_options: list[str],
                         header_file: Path | None = None) -> None:
    """The finished command's header files: a chosen kit's preamble goes in first (it is a header file, so the document's own
    `header-includes` need giving back too), then `_keep_header_includes`, then what the kit and the user's own LaTeX say
    twice is settled (kit_header_resolve)."""
    document = sources[0] if sources else None
    inserted = core.kit_header_insert(cmd, document, metadata_files)
    _keep_header_includes(cmd, sources, metadata_files, pandoc_options, header_file)
    if inserted:
        core.kit_header_resolve(cmd, document, metadata_files, pandoc_options)


def _keep_header_includes(cmd: list[str], sources: list[Path], metadata_files: list[Path], pandoc_options: list[str],
                          header_file: Path | None = None) -> None:
    """Give back the `header-includes` pdfmd's own --include-in-header files took away (v3.27.18). Pandoc puts those
    files and `header-includes:` in one template variable and the command line wins, so the code-wrapping header of a
    document with code, graphicx for a raw \\includegraphics, the fonts header, a preamble.tex or the packages header
    each dropped the document's own `header-includes` or, without them, a metadata file's (a house package loaded
    there: nulabreport's prelab-metadata.yaml). Run last, on the finished command: when pdfmd added a header file and
    the caller none, what Pandoc would have kept goes back in, as a header file of its own. A metadata file's go where
    a shared preamble goes, before the other headers (after code_wrap.tex, which must come first); the document's own
    last but for the packages header, which must see them (document_header_file has them already when it is there).
    An --include-in-header or an `-M header-includes` of the caller's own replaces them, as in Pandoc."""
    positions = [index for index, item in enumerate(cmd[:-1]) if item == "--include-in-header"]
    if not positions or has_header_include_option(pandoc_options) \
            or any("header-includes" in option for option in pandoc_options):
        return
    kept = pandoc_header_includes(sources, metadata_files)
    if kept is None or (kept[1] == "document" and header_file is not None):
        return
    text, where = kept
    path = core.cache_root() / "tex" / f"header-includes-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"% pdfmd: the {where} header-includes the header files below would drop\n{text}\n",
                            encoding="utf-8")
    except OSError:
        return
    packages = core.cache_root() / "tex"
    if where == "metadata":
        at = next((index for index in positions if not cmd[index + 1].endswith("code_wrap.tex")
                   and not Path(cmd[index + 1]).name.startswith(core.KIT_HEADER_PREFIX)), len(cmd))
    else:
        at = next((index for index in positions if Path(cmd[index + 1]).parent == packages
                   and Path(cmd[index + 1]).name.startswith("packages-")), len(cmd))
    cmd[at:at] = ["--include-in-header", str(path)]


HEADER_FILTER_OPTIONS = ("--lua-filter", "--filter", "-L", "--citeproc", "-C")      # where the first filter runs


def build_is_latex(cmd: list[str]) -> bool:
    """Whether the Pandoc command writes LaTeX: a LaTeX PDF engine (ConTeXt has its own template), or `-t latex` / `beamer`."""
    for index, item in enumerate(cmd):
        if item.startswith("--pdf-engine="):
            return item.split("=", 1)[1] in core.LATEX_ENGINES - {"context"}
        target = (cmd[index + 1] if item in ("-t", "--to", "-w", "--write") and index + 1 < len(cmd)
                  else item.split("=", 1)[1] if item.startswith(("--to=", "--write=")) else None)
        if target is not None:
            return target.split("+", 1)[0].split("-", 1)[0] in ("latex", "beamer")
    return False


def pandoc_filter_paths(cmd: list[str]) -> list[str]:
    """The files of the Lua and JSON filters of a Pandoc command, in order."""
    found = []
    for index, item in enumerate(cmd):
        if item in ("--lua-filter", "--filter", "-L") and index + 1 < len(cmd):
            found.append(cmd[index + 1])
        elif item.startswith(("--lua-filter=", "--filter=")):
            found.append(item.split("=", 1)[1])
    return found


def headers_as_metadata(cmd: list[str]) -> list[str]:
    """``cmd`` with its --include-in-header files given to Pandoc as `header-includes` instead (v3.32.30), or ``cmd`` itself.
    Pandoc puts the files and `header-includes` in one template variable and the files win, so a LaTeX build with any
    header file of pdfmd's lost what a Lua filter had put into `header-includes`: a kit's front-matter commands
    (apa7's \\authorsnames made \\maketitle stop in a partial build, which passes the labels of the whole document as
    header files; the same would have happened to a document with code). Only for a LaTeX build that has a filter of
    somebody else's (a kit's, the document's own): header_snap.lua records `header-includes` before the filters,
    header_merge.lua, last, makes it the files (-M pdfmd-header-file-N=PATH, in order) plus whatever the filters added."""
    positions = core.header_argument_positions(cmd)
    if not positions or not build_is_latex(cmd):
        return cmd
    try:
        import pdfmd_lua
        snap, merge = pdfmd_lua.path("header_snap"), pdfmd_lua.path("header_merge")
    except ImportError:
        return cmd
    if snap is None or merge is None:
        return cmd
    own = pdfmd_lua.FILTERS.resolve()
    foreign = any(Path(name).resolve().parent != own for name in pandoc_filter_paths(cmd))
    if not foreign:
        return cmd
    files: list[str] = []
    drop: set[int] = set()
    for index, equals in positions:
        files.append(cmd[index].split("=", 1)[1] if equals else cmd[index])
        drop.update({index} if equals else {index - 1, index})
    rest = [item for index, item in enumerate(cmd) if index not in drop]
    first = next((index for index, item in enumerate(rest)
                  if item in HEADER_FILTER_OPTIONS or item.startswith(("--lua-filter=", "--filter="))), len(rest))
    result = [*rest[:first], "--lua-filter", str(snap), *rest[first:]]
    for number, name in enumerate(files, 1):
        result += ["-M", f"pdfmd-header-file-{number}={name}"]
    return [*result, "--lua-filter", str(merge)]


# LaTeX packages a document's own commands need (v3.27.16, auto kind `texpackages`): `\ce{H2O}` without mhchem, or
# `\SI{3}{\metre}` without siunitx, stopped every LaTeX engine ("Undefined control sequence"). When a source uses one,
# the preamble gets a guarded load, last: nothing when the package is loaded already (nulabreport's own options win, no
# option clash), when the command is defined some other way, or when the package is not installed (the old error).
TEX_PACKAGE_USES = (
    ("mhchem", "[version=4]", "ce", re.compile(r"\\(?:ce|cee|cf)\s*\{")),
    ("siunitx", "", "SI", re.compile(r"\\(?:SI|si|num|qty|unit|ang|SIrange|numrange|qtyrange)\s*\{")),
)


def tex_package_args(sources: Path | list[Path], no_auto: list[str] | None, note=None) -> list[str]:
    """The arguments that give a LaTeX build the packages its commands need (TEX_PACKAGE_USES), or []: a header file,
    last (keep_header_includes puts back the header-includes it would drop, before it; v3.27.16 appended it to them
    with a filter instead, which a later header file of pdfmd's own undid)."""
    if core.auto_disabled(no_auto, "texpackages"):
        return []
    texts = []
    for file in sources if isinstance(sources, list) else [sources]:
        try:
            texts.append(Path(file).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError):
            continue
    wanted = [(name, options, macro) for name, options, macro, pattern in TEX_PACKAGE_USES
              if any(pattern.search(text) for text in texts)]
    if not wanted:
        return []
    lines = ["% pdfmd: packages the document's commands need, unless already there (--no-auto texpackages)",
             "\\makeatletter"]
    for name, options, macro in wanted:
        lines.append(f"\\@ifpackageloaded{{{name}}}{{}}{{\\ifdefined\\{macro}\\else"
                     f"\\IfFileExists{{{name}.sty}}{{\\usepackage{options}{{{name}}}}}{{}}\\fi}}")
    lines.append("\\makeatother")
    text = "\n".join(lines) + "\n"
    path = core.cache_root() / "tex" / f"packages-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    except OSError:
        return []
    if note is not None:
        note("TEXPACKAGES", "loads " + ", ".join(name for name, _, _ in wanted) + " unless the preamble does "
             "(the document uses " + ", ".join(f"\\{macro}" for _, _, macro in wanted) + ")")
    return ["--include-in-header", str(path)]


def has_header_include_option(options: list[str]) -> bool:
    """Return whether the caller already explicitly supplied Pandoc's -H option (also attached: -Hmine.tex)."""
    return any(option in {"-H", "--include-in-header"}
               or option.startswith(("--include-in-header=", "-H"))
               for option in options)


def has_shift_heading_option(options: list[str]) -> bool:
    """Return whether the caller already explicitly supplied --shift-heading-level-by."""
    return any(option == "--shift-heading-level-by"
               or option.startswith("--shift-heading-level-by=")
               for option in options)


def has_standalone_option(options: list[str]) -> bool:
    """Return whether the caller already explicitly supplied -s/--standalone.

    Also true for ``--template``, since Pandoc treats an explicit template
    as already asking for a standalone document (and passing both is
    harmless but redundant) -- so a caller who wants their own template
    driving a TEX_STANDALONE_FORMATS render isn't fighting pdfmd's own
    ``--standalone`` default.
    """
    return any(option in {"-s", "--standalone"}
               or option == "--template" or option.startswith("--template=")
               for option in options)


def preamble_candidates(directory: Path, document_stem: str) -> list[Path]:
    """Return intentionally named generic and document-specific preambles."""
    stem = document_stem.casefold()
    candidates: list[Path] = []
    for folder in core.accessory_directories(directory, document_stem):
        for path in folder.glob("*.tex"):
            name = path.name.casefold()
            if folder.name.endswith(core.UNPACKED_SUFFIX):
                candidates.append(path)  # a folder --unpack made: every preamble in it is this document's
                continue
            if name in core.PREAMBLE_FILENAMES:
                candidates.append(path)
                continue
            if (name == f"{stem}.tex" or name in {f"{stem}_preamble.tex", f"{stem}-preamble.tex"}
                    or re.fullmatch(r"(?:latex-)?preamble-[^.]+\.tex", name)):
                candidates.append(path)
    # Generic files load first; document-specific settings then override them.
    def priority(path: Path) -> tuple[int, str]:
        name = path.name.casefold()
        if name == "preamble.tex":
            return (0, name)
        if name == "latex-preamble.tex":
            return (1, name)
        if name.startswith("preamble-") or name.startswith("latex-preamble-"):
            return (2, name)
        return (3, name)
    return sorted(candidates, key=priority)


def find_preambles(directory: Path, document_stem: str, options: list[str]) -> list[Path]:
    """Find safe, intentionally named LaTeX preambles beside a document."""
    if has_header_include_option(options):
        return []
    return [path.resolve() for path in preamble_candidates(directory, document_stem)
            if core.is_latex_preamble(path)]


def document_preambles(md_path: Path, pandoc_options: list[str], no_auto: list[str] | None,
                       metadata_files: list[Path] = ()) -> list[Path]:
    """The preambles of a document: the ones found beside it (not for off or explicit-only) and the ones it names (not for off)."""
    found = [] if core.discovery_disabled(no_auto, "preamble") else find_preambles(md_path.parent, md_path.stem, pandoc_options)
    named = [] if core.auto_disabled(no_auto, "preamble") else core.frontmatter_extra_preambles(md_path, metadata_files)
    chosen = core.deferred("pdfmd_metadata", "with_parent_preambles")(found, md_path, pandoc_options, no_auto, metadata_files) + named
    return [path for path in chosen if path != md_path.resolve()] if md_path.suffix.casefold() == ".tex" else chosen


def announce_preambles(preambles: list[Path]) -> None:
    for preamble in preambles:
        core.AUTO_LOG.record_file("TEX", preamble, core.VERBOSE_OUTPUT)
    if len(preambles) > 1:
        print("WARN  Multiple preambles discovered; later files may override earlier definitions.",
              file=sys.stderr)


TEX_COMMAND_START = re.compile(r"^(?:[ \t]*\n)* {0,3}\\[A-Za-z@]+\*?")
TEX_ARGUMENT_TOKENS = re.compile(r"\\[^\n]|%[^\n]*|[{}\]]")


def multiline_tex_command(body: str) -> bool:
    """A whole Markdown body consisting of one command whose arguments Pandoc could split."""
    start = TEX_COMMAND_START.match(body)
    if start is None:
        return False
    arguments = body[start.end():].rstrip()
    if not arguments or "\n" not in arguments or re.search(r"\n[ \t]*\n", arguments):
        return False
    position = 0
    split = False
    braced = False
    while position < len(arguments):
        unspaced = arguments[position:].lstrip()
        opening = unspaced[0]
        if opening not in "{[":
            return False
        begin = len(arguments) - len(unspaced)
        depth = int(opening == "{")
        braced |= opening == "{"
        for token in TEX_ARGUMENT_TOKENS.finditer(arguments, begin + 1):
            value = token.group()
            depth += (value == "{") - (value == "}")
            if depth < 0:
                return False
            if depth == 0 and value == ("}" if opening == "{" else "]"):
                split |= "\n" in arguments[position:begin] or (opening == "[" and "\n" in arguments[begin:token.end()])
                position = token.end()
                break
        else:
            return False
    return split and braced


def fence_multiline_tex(text: str) -> str:
    front = core.LEADING_FRONT_MATTER_RE.match(text)
    offset = front.end() if front else 0
    body = text[offset:]
    if not multiline_tex_command(body):
        return text
    fence = "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", body)), default=0))
    return f"{text[:offset]}{fence}{{=latex}}\n{body.strip()}\n{fence}\n"


TEX_DOCUMENT_RE = re.compile(r"\\(?:document(?:class|style)\b|begin\s*\{document\})")


def compile_tex_source(source: Path, output: Path, engines: list[str], keep_aux: bool, verbose: bool,
                       debug: bool, preambles: list[Path], metadata_files: list[Path], pandoc_options: list[str]
                       ) -> tuple[bool, str, bool]:
    """Compile .tex directly, including a discovered preamble around a fragment."""
    text = core.read_text_best_effort(source)
    fragment = not TEX_DOCUMENT_RE.search(re.sub(r"(?<!\\)%[^\n]*", "", text))
    if fragment:
        explicit = []
        for index, arg in enumerate(pandoc_options):
            if arg in ("-H", "--include-in-header") and index + 1 < len(pandoc_options):
                explicit.append(pandoc_options[index + 1])
            elif arg.startswith("--include-in-header="):
                explicit.append(arg.split("=", 1)[1])
            elif arg.startswith("-H") and len(arg) > 2:
                explicit.append(arg[2:])
        cwd = core.metadata_cwd(metadata_files, source.parent)
        headers = [path.read_text(encoding="utf-8-sig") for path in preambles]
        headers += [(cwd / name).read_text(encoding="utf-8-sig") for name in explicit]
        if headers:
            def compile_wrapped(folder: Path) -> tuple[bool, str, bool]:
                wrapper = folder / source.name
                wrapper.write_text("\n".join([r"\documentclass{article}", *headers, r"\begin{document}", text,
                                             r"\end{document}", ""]), encoding="utf-8")
                core.vprint(verbose, f"AUTO TEXFRAGMENT  {core.display_path(source)}: compiling with its project preamble")
                env = tex_search_env(cwd, source.parent, source)
                ok, reason = core.compile_tex_direct(wrapper, output, engines, keep_aux, verbose, debug,
                                                     cwd=source.parent, env=env, document_directory=source.parent)
                return ok, reason, True

            if keep_aux:
                folder = Path(mkdtemp(prefix="pdfmd-tex-fragment-"))
                print(f"NOTE  LaTeX fragment and auxiliary files kept in {core.display_path(folder)}")
                return compile_wrapped(folder)
            with TemporaryDirectory(prefix="pdfmd-tex-fragment-") as folder:
                return compile_wrapped(Path(folder))
    ok, reason = core.compile_tex_direct(source, output, engines, keep_aux, verbose, debug)
    if fragment and not ok and "undefined control sequence" in reason.casefold():
        return False, ("This LaTeX fragment needs its project preamble. Put the macro definitions in a discovered "
                       "preamble.tex or supply them with --include-in-header FILE."), True
    return ok, reason, False


@contextmanager
def prepared_latex_inputs(paths: list[Path], latex_engine: bool,
                          typst_engine: bool = False, doc_count: int = 1,
                          drop_embedded_preamble: bool = False,
                          named_reader: str | None = None, effective_reader: str | None = None) -> Iterator[list[Path]]:
    """Yield temporary, corrected inputs for LaTeX-family renders when
    needed -- or, with `typst_engine` instead, to make a margin setting
    written for the OTHER engine family reach Typst's own template (see
    fix_typst_margin()). The two are mutually exclusive; at most one
    corrector ever applies to a given render, same as `latex_engine` alone
    before this.

    `paths[:doc_count]` are the main document(s) being rendered -- a
    single `title_source` everywhere except report/book mode, where every
    chapter file counts (``doc_count=len(files)``, passed explicitly by
    those two call sites; every other call site keeps the default of 1).
    Every path after that is a linked --metadata-file, which Pandoc
    accepts EITHER fenced (``---``/``...``-delimited, same as a
    document's own front matter) OR completely bare (no delimiters at
    all -- see the Pandoc manual's own "metadata file" section).
    fix_typst_margin() is told which is which (`is_metadata`) so it can
    safely treat a bare metadata file as pure YAML, while a bare MAIN
    DOCUMENT (no delimiters at all) is definitely markdown body text,
    never YAML, and is always left alone regardless.
    """
    reader = effective_reader or named_reader or "markdown"
    latex_fences = (re.split(r"[+-]", reader, maxsplit=1)[0] == "markdown"
                    and "-raw_attribute" not in reader and "-raw_tex" not in reader)
    temporary_paths: list[Path] = []
    prepared: list[Path] = []
    try:
        for index, path in enumerate(paths):
            original = path.read_text(encoding="utf-8-sig")
            text = repair_controls(original, path) if index < doc_count else original
            if drop_embedded_preamble and index < doc_count:
                # A target that is not LaTeX-family gets no embedded LaTeX preamble.
                text = core.strip_embedded_preamble(text)
            if index < doc_count and "\\[" in text:
                text = core.deferred("pdfmd_excerpts.pagecite", "protect_escapes")(text, paths[0], paths[doc_count:])
            if "@-" in text:
                text = core.deferred("pdfmd_excerpts.resolution", "protect_hyphen_prefix")(
                    text, paths[0], paths[doc_count:], core.effective_no_auto(paths[0], core.NO_AUTO_CLI), named_reader)
            if latex_engine:
                corrected = core.wrap_latex_header_includes(text)
                if latex_fences and index < doc_count and path.suffix.lower() in (".md", ".markdown"):
                    corrected = fence_multiline_tex(corrected)
            elif typst_engine:
                corrected = core.fix_typst_margin(text, is_metadata=(index >= doc_count))
            else:
                corrected = text
            if corrected == original:
                prepared.append(path)
                continue
            with NamedTemporaryFile("w", encoding="utf-8", suffix=path.suffix,
                                    prefix=f".{path.stem}.pdfmd-", dir=path.parent,
                                    delete=False) as temporary:
                temporary.write(corrected)
                temporary_path = Path(temporary.name)
            temporary_paths.append(temporary_path)
            prepared.append(temporary_path)
        yield prepared
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)


RAW_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*\{=([\w+-]+)\}[ \t]*\n(.*?)\n[ \t]*\1[ \t]*$",
                          re.DOTALL | re.MULTILINE)


RAW_INLINE_RE = re.compile(r"`([^`\n]+)`\{=([\w+-]+)\}")


def raw_latex_only(text: str) -> str:
    """What LaTeX gets of a `header-includes:` item written with Pandoc's raw attribute (v3.27.19): a ```{=latex} block
    or `...`{=latex} span without its fence, a block or span for another format (html, typst ...) dropped, as Pandoc's
    LaTeX writer does. A header file pdfmd builds from the item would otherwise hand LaTeX the backticks."""
    def keep(match: re.Match, body: int, form: int) -> str:
        return match.group(body) if match.group(form).lower() in ("latex", "tex") else ""
    text = RAW_FENCE_RE.sub(lambda match: keep(match, 3, 2), text)
    return RAW_INLINE_RE.sub(lambda match: keep(match, 1, 2), text)


def document_header_includes(text: str) -> str | None:
    """Return the LaTeX in a document's own ``header-includes:`` block (raw_latex_only of each item).

    Pandoc feeds ``--include-in-header`` files into the very same
    ``header-includes`` template variable, and a variable set on the command
    line beats one set in metadata. So the moment ANY ``--include-in-header``
    reaches the command line -- an auto-included preamble, or pdfmd's own
    PDF-metadata stamp header (on by default; see ``--stamp-pdf-metadata``) --
    a ``header-includes`` block in that document's own front matter is
    silently discarded, even if nothing about preambles is otherwise in play.
    Confirmed directly (2026-09-20, CHEM 341 session): a document with its
    own YAML ``header-includes`` and no preamble.tex/latex-preamble.tex beside
    it still lost that block, because the PDF-metadata stamp header alone was
    enough to trigger it. Extracting it here lets the caller re-append it as a
    trailing ``--include-in-header``, after anything else, which is where a
    per-document override belongs -- so every call site that may add ANY
    other ``--include-in-header`` must pass ``active=True`` here too, not just
    the ones adding a preamble.

    Handles both YAML shapes a ``header-includes:`` value can take: a block
    scalar (``header-includes: |`` ... indented lines), the ORIGINAL and
    only shape this function understood before 2026-09-20, and a sequence
    (``header-includes:\\n  - \\usepackage{mhchem}\\n  - ...``) -- the more
    common form in practice, and the one that silently defeated this whole
    safeguard for any document using it: the block-scalar-only regex below
    simply never matched, so `active` calculations based on this function
    looked right while the document's actual header-includes kept vanishing
    anyway. A real YAML parse (installed PyYAML or the bundled fallback;
    see `frontmatter_pdfmd_options`) handles the
    sequence shape correctly, one raw LaTeX line per list item, joined with
    newlines, matching how Pandoc's own template concatenates such a list.
    Falls back to the original block-scalar-only regex when PyYAML isn't
    available -- worse than a real parse, but not a new limitation; a
    sequence-style document with no PyYAML available is simply back to the
    pre-2026-09-20 (bugged) behavior for this one shape, same as it always
    was.
    """
    if core.yaml is not None:
        loose_front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
        if loose_front_matter:
            try:
                data = core.yaml.safe_load(loose_front_matter.group(1))
            except core.yaml.YAMLError:
                data = None
            if isinstance(data, dict):
                value = data.get("header-includes")
                if isinstance(value, list):
                    lines_out = [raw_latex_only(str(item)).strip() for item in value if item is not None]
                    return "\n".join(line for line in lines_out if line).strip() or None
                if isinstance(value, str):
                    return raw_latex_only(value).strip() or None
                return None

    front_matter = re.match(r"^(---\s*\n)(.*?)(\n(?:---|\.\.\.)\s*(?:\n|$))", text, re.DOTALL)
    if not front_matter:
        return None

    lines = front_matter.group(2).splitlines(keepends=True)
    index = 0
    while index < len(lines):
        match = re.match(r"^(?P<indent>\s*)header-includes\s*:\s*\|[+-]?\s*(?:#.*)?(?:\r?\n)?$", lines[index])
        if not match:
            index += 1
            continue
        base_indent = len(match.group("indent"))
        start = index + 1
        index = start
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip(" \t")) <= base_indent:
                break
            index += 1
        block = raw_latex_only(dedent("".join(lines[start:index]))).strip()
        return block or None
    return None


@contextmanager
def document_header_file(md_path: Path, active: bool, metadata_files: list[Path] | None = None,
                         no_auto: list[str] | None = None) -> Iterator[Path | None]:
    """Yield a temporary .tex holding the document's own preamble additions."""
    if not active and core.kit_writes_preamble(md_path, metadata_files):
        active = True                                    # the kit's header file would drop the document's own header-includes
    if not active:
        yield None
        return
    try:
        definitions = core.document_latex_definitions(md_path, metadata_files, no_auto)
        includes = document_header_includes(md_path.read_text(encoding="utf-8-sig")) or ""
        if core.PREAMBLE_END_MARK in includes:
            # An embedded preamble (see EMBED_KINDS): definitions go after it.
            head, _, tail = includes.partition(core.PREAMBLE_END_MARK)
            parts = [head.rstrip("\n"), definitions, tail.lstrip("\n")]
        else:
            parts = [definitions, includes]
    except OSError:
        parts = []
    block = "\n".join(part for part in parts if part)
    if not block:
        yield None
        return
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".tex",
                            prefix=f".{md_path.stem}.pdfmd-header-", dir=md_path.parent,
                            delete=False) as temporary:
        temporary.write(block + "\n")
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)
