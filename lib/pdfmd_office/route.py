"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_office.route`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from pdfmd_base import core
from pdfmd_log import emit


OFFICE_REFERENCE_EXTENSIONS = {"docx": ("docx", "dotx"), "odt": ("odt", "ott"), "pptx": ("pptx", "potx")}


OFFICE_OPTION_KEYS = ("reference-doc", "fonts", "latex", "style", "styles", "labels", "profile", "replace", "title-page", "media", "papersize", "geometry", "margin",
                      "fontsize", "mainfont", "sansfont", "monofont", "CJKmainfont", "linestretch", "lang", "indent")


def office_module():
    try:
        import pdfmd_office
    except ImportError:
        return None
    return pdfmd_office


def effective_metadata(md_path: Path, metadata_files: list[Path], variables: list[str]) -> dict:
    """The metadata Pandoc sees for a document, as plain data: -V variables over the document's front
    matter over its metadata files (the later file wins, as in Pandoc, in pandoc_metadata_order)."""
    merged: dict = {}
    for path in core.pandoc_metadata_order(metadata_files):
        merged.update(core.metadata_file_yaml(path))
    if md_path.suffix.lower() in (".md", ".markdown", ".txt", ""):
        try:
            front = core.front_matter_dict(md_path.read_text(encoding="utf-8-sig"))
            if "pagesize" in front and "papersize" not in front:
                front = {**front, "papersize": front["pagesize"]}         # the typo pdfmd reads as papersize (pagesize_typo_value)
            merged.update(front)
        except (OSError, UnicodeDecodeError):
            pass
    from_variables: dict = {}
    for variable in variables:
        match = re.match(r"^([^:=]+)[:=](.*)$", variable)
        key, value = (match.group(1), match.group(2)) if match else (variable, "true")
        from_variables.setdefault(key, []).append(value)
    for key, values in from_variables.items():
        if key == "papersize" and len(values) == 1 and core.paper_words(values[0])[1] and not core.paper_words(values[0])[0]:
            before = core.scalar_text(merged.get("papersize"))              # `--paper landscape`: the size stays what it was
            merged[key] = f"{before},{values[0]}" if before else values[0]
            continue
        merged[key] = values[0] if len(values) == 1 and key != "geometry" else values
    return merged


def pick_variant(pick: dict, chosen: list[str], md_path: Path, no_auto: list[str] | None) -> dict | None:
    """The variant of a package's `pick:` block that the document selects, as a mapping to merge into its
    office options. `pick: {default: black, default-by-option: {genchem: word}, from-preamble: REGEX, variants:
    {word: {...}, black: {...}}}`: the name starts as the default (of the last package option that has
    one), and the last match of the regex in the preamble (or the document's header-includes) takes over, the
    first capture group that matched being the name; a package whose own macros pick its colour scheme says
    where to read it, and the Word file follows."""
    name = pick.get("default")
    by_option = pick.get("default-by-option")
    if isinstance(by_option, dict):
        for option in chosen:
            if option in by_option:
                name = by_option[option]
    pattern = pick.get("from-preamble")
    if isinstance(pattern, str):
        texts = []
        for item in (core.find_preambles(md_path.parent, md_path.stem, []) if not core.discovery_disabled(no_auto, "preamble") else []):
            try:
                texts.append(item.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        try:
            texts.append(core.document_header_includes(md_path.read_text(encoding="utf-8-sig")) or "")
        except (OSError, UnicodeDecodeError):
            pass
        try:
            for match in re.finditer(pattern, "\n".join(texts)):
                found = next((group for group in match.groups() if group), None)
                if found:
                    name = found
        except re.error:
            pass
    variants = pick.get("variants")
    if isinstance(variants, dict) and isinstance(variants.get(name), dict):
        return variants[name]
    return None


def office_options(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None = None) -> dict:
    """`pdfmd-options: {office: ...}` as the document, its metadata files and the config file give it, over the
    defaults of a package that ships them (`<name>-office.yaml`, or the `office:` of `<name>-pdfmd.yaml`); the
    document wins key by key."""
    value = core.first_pdfmd_option(md_path, metadata_files, "office", with_config=False)
    options = dict(value) if isinstance(value, dict) else {}
    for folder, package, chosen in reversed(core.office_packages(md_path, metadata_files, no_auto)):
        for data, candidate in core.office_defaults_sources(folder, package, no_auto):
            # `by-option:` holds what an option of \usepackage[...] adds (orgchem: footer wording...)
            variants = data.pop("by-option", None)
            if isinstance(variants, dict):
                for option in chosen:
                    extra = variants.get(option)
                    if isinstance(extra, dict):
                        for extra_key, extra_value in extra.items():
                            data[extra_key] = ({**data.get(extra_key, {}), **extra_value}
                                               if isinstance(extra_value, dict) and isinstance(data.get(extra_key), dict)
                                               else extra_value)
            pick = data.pop("pick", None)
            if isinstance(pick, dict):
                extra = pick_variant(pick, chosen, md_path, no_auto)
                for extra_key, extra_value in (extra or {}).items():
                    data[extra_key] = ({**data.get(extra_key, {}), **extra_value}
                                       if isinstance(extra_value, dict) and isinstance(data.get(extra_key), dict)
                                       else extra_value)
            options = {**data, **options}
            # a package's relative reference-doc / profile paths are relative to its folder
            for key in ("reference-doc", "profile"):
                if isinstance(data.get(key), str) and key not in (value or {}):
                    options[key] = str((candidate.parent / data[key]).resolve())
            if isinstance(options.get("media"), dict) and "media" not in (value or {}):
                options["media"] = {name: str((candidate.parent / file).resolve())
                                    for name, file in options["media"].items()}
    # the config file (pdfmd --setup) is below a house style's own defaults (v3.27.9): a global reference-doc must not
    # replace the department template nulabreport ships; the document and its metadata files are above both
    configured = core.config_options(md_path).get("office")
    if isinstance(configured, dict):
        options = {**configured, **options}
    return options


OFFICE_LABEL_COMMANDS = re.compile(r"\\(?:ref|cref|Cref|eqref|autoref|pageref|labelcref|label)\s*\{"
                                   r"|\\begin\{(?:equation|align|gather|multline|eqnarray|reaction|figure|table)")


def office_pdfmd_command(md_path: Path, metadata_files: list[Path], variables: list[str],
                         no_auto: list[str] | None, *options: str) -> list[str]:
    """This pdfmd run again, as a subprocess, for the same document with other options (a PDF build for its
    labels, a `--to latex` run for its preamble)."""
    # --no-stamp/--no-backup: only the build the user asked for writes a note into the source and a snapshot
    command = [sys.executable, str(Path(core.__file__).resolve()), str(md_path), *options, "--no-stamp", "--no-backup", "--rewrite",
               "--no-auto", *(no_auto or ["officeref"])]
    for variable in variables:
        command += ["-V", variable]
    if metadata_files:
        command += ["-y", *map(str, metadata_files)]
    return command


def office_label_data(md_path: Path, metadata_files: list[Path], variables: list[str],
                      no_auto: list[str] | None, note, scratch: Path, mode: str) -> Path | None:
    """The numbers LaTeX gave this document's labels (an .aux from a real PDF build, reused while it is
    newer than the sources), with the caption separator and reference names its preamble sets, written
    as JSON for the Lua filter. None when the document has nothing to refer to or the build fails."""
    module = office_module()
    if module is None or md_path.suffix.lower() not in (".md", ".markdown", ".txt", ""):
        return None
    try:
        text = md_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    # a split document refers to its labels from its parts: they are read, and watched for changes, with it
    parts: list[Path] = []
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            plan = core.plan_scaffold(md_path, [], no_auto, None)
        parts = [part for part in plan.parts if part != md_path] if plan is not None else []
        for part in parts:
            text += "\n" + part.read_text(encoding="utf-8-sig")
    except (SystemExit, OSError, UnicodeDecodeError):
        parts = []
    preambles = core.find_preambles(md_path.parent, md_path.stem, []) if not core.discovery_disabled(no_auto, "preamble") else []
    texts = []
    for item in preambles:
        try:
            texts.append(item.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    names = [package.strip() for name in dict.fromkeys(re.findall(r"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{([^}]+)\}",
                                                                 "\n".join(texts))) for package in name.split(",")]
    for path in core.kpsewhich_locate([package + ".sty" for package in names if package]).values():
        if "texmf-dist" not in str(path) and "/texlive/" not in str(path):
            try:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    data = {"captionsep": module.caption_separator(texts),
            "crefcap": bool(re.search(r"cleveref[^\n]*|\\usepackage\[[^\]]*\]\{cleveref\}", "\n".join(texts)) and
                            re.search(r"\[[^\]]*capitali[sz]e[^\]]*\]\{cleveref\}", "\n".join(texts)) is not None),
            "crefnames": {key: list(value) for key, value in module.cref_names(texts).items()}, "labels": {}}
    wanted = OFFICE_LABEL_COMMANDS.search(text) is not None and mode != "off"
    if wanted:
        base = core.cache_directory(md_path, core.document_cache_root(md_path, metadata_files))
        aux = base / f"{core.safe_stem(md_path.stem)}.aux"
        sources = [md_path, *parts, *metadata_files, *preambles]
        newest = max((item.stat().st_mtime for item in sources if item.is_file()), default=0)
        if not (aux.is_file() and aux.stat().st_mtime >= newest):
            core.load_package("pdfmd_office.build").build_reference_numbers(
                md_path, metadata_files, variables, no_auto, note, scratch)
        if aux.is_file():
            data["labels"] = module.parse_aux(aux.read_text(encoding="utf-8", errors="replace"))
            (scratch / "labels.aux").write_text(
                module.labels_only(aux.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    path = scratch / "labels.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@contextmanager
def office_reference(md_path: Path, metadata_files: list[Path], variables: list[str], target: str, output: Path,
                     pandoc_options: list[str], no_auto: list[str] | None, note,
                     labels: str | None = None, force_filter: bool = False) -> Iterator[list[str]]:
    """Pandoc arguments for a docx/odt/pptx build: `--reference-doc FILE` (the user's own reference
    document, or Pandoc's default, with the document's page setup, fonts and pdfmd's look written in)
    and, with `office: {latex: auto}`, the filter that makes LaTeX native (OfficeArguments)."""
    with tempfile.TemporaryDirectory(prefix="pdfmd-office-filter-") as scratch, \
            office_reference_document(md_path, metadata_files, variables, target, output, pandoc_options,
                                      no_auto, note) as reference_arguments:
        arguments = core.OfficeArguments(reference_arguments)
        arguments.scratch = Path(scratch)
        arguments.context = {"md_path": md_path, "metadata_files": metadata_files, "variables": variables,
                             "no_auto": no_auto, "target": target, "note": note, "output": output}
        module = office_module()
        options = office_options(md_path, metadata_files, no_auto)
        latex = str(options.get("latex", "auto" if target in ("docx", "odt") else "")).casefold()
        ebook = target == "epub" and core.EBOOK_MATH.get("mode") == "images"      # v3.29.1: an ebook's math drawn as pictures
        if ebook:
            latex, labels = "images", "off"
        if not latex and target in ("typst", "html") and raw_takes(md_path, metadata_files, target, "tex"):
            latex = "auto"                  # the raw option has this output take LaTeX: the route that draws what it can
        # Word and ODF always; Typst and HTML files only when the document asks (`office: {latex: auto}`); a Typst,
        # WeasyPrint or Calibre PDF when office_fallback_wanted says so (force_filter)
        wanted = target in ("docx", "odt") or force_filter or latex in ("auto", "images")
        if (module is not None and (target in ("docx", "odt", "typst", "html") or ebook) and wanted
                and latex not in ("off", "false", "no")
                and not core.auto_disabled(no_auto, "officelatex")):
            arguments.report = Path(scratch) / "report.json"
            labels = office_label_data(md_path, metadata_files, variables, no_auto, note, Path(scratch),
                                       labels or str(options.get("labels", "auto")).casefold())
            profile = None if core.auto_disabled(no_auto, "officeprofile") else core.find_office_profile(
                md_path, metadata_files, options, core.office_package_folders(md_path, metadata_files, no_auto))
            if profile is not None:
                note("OFFICE", f"{md_path}: profile {core.display_path(profile)}")
            arguments.filter_arguments = ["-M", f"pdfmd-office-latex={'images' if latex == 'images' else 'auto'}",
                                          "-M", f"pdfmd-office-report={arguments.report}"]
            if target == "typst":
                # a title a house style's cover took out goes back into the PDF's properties by a `set document` in
                # the body; engine selection already requires Typst 0.12 or newer
                arguments.filter_arguments += ["-M", "pdfmd-office-typst-document=true"]
            if labels is not None:
                arguments.filter_arguments += ["-M", f"pdfmd-office-labels={labels}"]
            # where a file the document pulls in (\input, a package's chemicals.tex) may be: its own folder, the
            # metadata and preamble folders, as the PDF build finds them
            places = [md_path.parent, *core.accessory_directories(md_path.parent, md_path.stem),
                      *(item.parent for item in metadata_files),
                      *(item.parent for item in (core.find_preambles(md_path.parent, md_path.stem, [])
                                                  if not core.discovery_disabled(no_auto, "preamble") else []))]
            arguments.filter_arguments += ["-M", "pdfmd-office-path=" + os.pathsep.join(
                dict.fromkeys(str(Path(item).resolve()) for item in places))]
            if profile is not None:
                arguments.filter_arguments += ["-M", f"pdfmd-office-profile={profile}"]
            # the document's preamble: a profile reads its options, the converter of \ce and siunitx its \sisetup
            # and the house packages it loads (v3.28.9: before, it was passed only with a profile)
            parts = []
            for item in (core.find_preambles(md_path.parent, md_path.stem, [])
                         if not core.discovery_disabled(no_auto, "preamble") else []):
                try:
                    parts.append(item.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
            if parts:
                preamble_copy = Path(scratch) / "preamble.txt"
                preamble_copy.write_text("\n".join(parts), encoding="utf-8")
                arguments.filter_arguments += ["-M", f"pdfmd-office-preamble={preamble_copy}"]
            # pdfmd_chem runs in this Python (the one with pdfmd's packages), not whatever python3 is first on PATH
            arguments.filter_arguments += ["-M", f"pdfmd-office-python={sys.executable}"]
            # its answers, kept between the two runs of the filter (the collect run's for the render run)
            arguments.filter_arguments += ["-M", f"pdfmd-office-chem-cache={Path(scratch) / 'chem.json'}"]
            # last: other filters (a house style's own) have shaped the document by then
            arguments.filter_arguments += ["--lua-filter", str(Path(module.__file__).parent / "office.lua")]
            if ebook:
                arguments.filter_arguments += core.ebook_filter_args()
        yield arguments


@contextmanager
def office_reference_document(md_path: Path, metadata_files: list[Path], variables: list[str], target: str,
                              output: Path, pandoc_options: list[str], no_auto: list[str] | None,
                              note) -> Iterator[list[str]]:
    if (target not in OFFICE_REFERENCE_EXTENSIONS
            or any(item == "--reference-doc" or item.startswith("--reference-doc=") for item in pandoc_options)):
        yield []
        return
    module = office_module()
    options = office_options(md_path, metadata_files, no_auto)
    found = (None, "") if core.auto_disabled(no_auto, "officeref") else core.find_reference_doc(
        md_path, metadata_files, target, output, options, core.office_package_folders(md_path, metadata_files, no_auto))
    reference, origin = found
    if module is None or target == "pptx":
        yield ["--reference-doc", str(reference)] if reference else []
        if reference:
            note("OFFICE", f"{md_path}: reference document {origin}")
        return
    styled = not core.auto_disabled(no_auto, "officestyle") and str(options.get("style", "")).casefold() != "none"
    policy = "exact" if str(options.get("fonts", "")).casefold() == "exact" else "safe"
    explicit = {key: value for key, value in options.items() if key in OFFICE_OPTION_KEYS}
    document_indent = core.first_pdfmd_option(md_path, metadata_files, "indent")
    if document_indent is not None:
        explicit.setdefault("indent", document_indent)
    if reference is not None:
        # a template decides its own page and fonts; only what `office:` names changes it
        spec = module.spec_from_metadata({}, explicit, policy)
        house = False
    elif styled:
        spec = module.spec_from_metadata(effective_metadata(md_path, metadata_files, variables), explicit, policy)
        house = str(options.get("style", "house")).casefold() != "plain"
        if target == "docx":
            from pdfmd_css.headings import stylesheet_headings
            spec.css_headings = stylesheet_headings(md_path, metadata_files, no_auto, pandoc_options)
    else:
        yield []
        return
    if reference is None and house:
        # pdfmd's PDF defaults are STIX Two Text and JetBrains Mono: what Word has closest to them
        spec.main = spec.main or "Times New Roman"
        spec.mono = spec.mono or "Consolas"
    if reference is not None and spec.empty() and target != "docx":
        note("OFFICE", f"{md_path}: reference document {origin}")
        yield ["--reference-doc", str(reference)]
        return
    media = options.get("media")
    if isinstance(media, dict):
        for zip_path, file in media.items():
            try:
                spec.media[str(zip_path)] = Path(str(file)).read_bytes()
            except OSError as error:
                emit("warning", None, f"WARN  {md_path}: office.media {file}: {error}", file=sys.stderr)
    try:
        base = reference.read_bytes() if reference else module.default_reference(target)
        data = module.patch_reference(target, base, spec, house)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        emit("warning", None, f"WARN  {md_path}: could not prepare the {target} reference document ({error}); "
              "Pandoc's default is used", file=sys.stderr)
        yield []
        return
    for text in spec.notes:
        note("OFFICE", f"{md_path}: font {text}")
    shown = []
    if spec.paper or spec.landscape:
        width, height = spec.page_size()
        shown.append(f"page {width / 1440:.2f} x {height / 1440:.2f} in")
    if spec.margins:
        shown.append("margins " + "/".join(f"{spec.margins.get(side, 0) / 1440:.2f}" for side in
                                           ("top", "right", "bottom", "left")) + " in")
    if spec.main or spec.size:
        shown.append(", ".join(filter(None, [spec.main, f"{spec.size:g} pt" if spec.size else None])))
    note("OFFICE", f"{md_path}: {target} " + ("from " + origin + "; " if reference else "from Pandoc's default; ")
         + ("; ".join(shown) if shown else "pdfmd's styles"))
    with tempfile.TemporaryDirectory(prefix="pdfmd-office-") as folder:
        path = Path(folder) / f"reference.{target}"
        path.write_bytes(data)
        yield ["--reference-doc", str(path)]


def raw_takes(md_path: Path, metadata_files: list[Path], family: str, syntax: str) -> bool:
    """Whether the `raw` option has output family `family` take the raw `syntax` (see pdfmd_raw)."""
    table = core.resolve_raw(md_path, metadata_files)
    return bool(table and syntax in table.get(family, []))


# LaTeX a Typst or HTML writer drops: a raw ```{=latex} block, a command in the text (Pandoc reads `\ce{H2O}` as raw
# LaTeX), and chemistry or units in math (texmath knows no \ce or \SI: Pandoc prints the TeX). Front matter and code
# are not looked at.
RAW_TEX_FENCE_RE = re.compile(r"(?m)^[ \t]*(?:`{3,}|~{3,})[ \t]*\{=(?:latex|tex)\}")


TEXT_COMMAND_RE = re.compile(r"\\[A-Za-z@]+")


MATH_SPAN_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.DOTALL)


# mhchem's and siunitx's commands pdfmd_chem converts (v3.28.10: one list; pdfmd_lua/chem_client.lua's NAMES and
# pdfmd_chem/batch.py's are the same, tests/test_chem.py)
CHEM_COMMANDS = ("ce", "cee", "cf", "pu", "num", "numlist", "numrange", "numproduct", "si", "unit", "SI", "qty",
                 "SIlist", "qtylist", "SIrange", "qtyrange", "ang")


MATH_ONLY_LATEX_RE = re.compile(r"\\(?:" + "|".join(CHEM_COMMANDS) + r")(?![A-Za-z])")


def latex_failed(failed_families: set) -> bool:
    """Whether a LaTeX engine failed earlier in this chain. The loop records an engine by its TeX family (luatex, xetex,
    pdftex: ENGINE_FAMILY); the check looked for engine names, so it never held and a Typst or WeasyPrint run after
    LaTeX failed did not get the LaTeX filter (v3.24.x to v3.28.1)."""
    latex_families = {core.ENGINE_FAMILY.get(engine, engine) for engine in core.LATEX_ENGINES}
    return any(name in latex_families or name in core.LATEX_ENGINES for name in failed_families)


def latex_dropped(paths: list[Path]) -> bool:
    """Whether the documents say something in LaTeX that a Typst or HTML writer would drop (see TEXT_COMMAND_RE)."""
    for path in paths:
        _, body = core.split_front_matter(core.read_text_best_effort(path))
        if RAW_TEX_FENCE_RE.search(body):
            return True
        body = core.strip_code_text(body)
        if any(MATH_ONLY_LATEX_RE.search(math) for math in MATH_SPAN_RE.findall(body)):
            return True
        if TEXT_COMMAND_RE.search(MATH_SPAN_RE.sub("", body)):
            return True
    return False


def office_fallback_wanted(md_path: Path, metadata_files: list[Path], failed_families: set,
                           family: str = "", sources: list[Path] | tuple = ()) -> bool:
    """Whether a Typst/WeasyPrint run should go through the LaTeX filter: a LaTeX engine has failed already, or the
    document says `office: {latex: auto}` for it, or its `raw` option has this family (`typst`, `html`) take LaTeX.
    With no `raw` setting for the family, whenever the document (`sources`, its parts too) has LaTeX the writer would
    drop (v3.28.2: a named `-e typst` or `-e weasyprint` printed "Water is and" for "Water is \\ce{H2O} and", and
    left out every tikzpicture, without a word)."""
    if latex_failed(failed_families):
        return True
    if str(office_options(md_path, metadata_files).get("latex", "")).casefold() in ("auto", "images"):
        return True
    if not family:
        return False
    table = core.resolve_raw(md_path, metadata_files)
    if table and family in table:
        return "tex" in table[family]
    return latex_dropped(list(sources) or [md_path])
