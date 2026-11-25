"""`pdfmd --check` as pdfmd runs it: the discovery that `lint.py` does not do (which files make up the document, which metadata files
apply, the keys of the bibliography it names) and the command itself.

Moved out of `pdfmd.py` unchanged (v3.33.17, SPLIT.md). `core` is the `pdfmd` module, bound when the module is first loaded (a
stand-in in `pdfmd.py` loads it on the first call; the first binding wins); the pdfmd names the code uses are read as `core.X`
when it runs, among them `core.yaml` (pdfmd's own optional import, None without PyYAML) and `core.which`, which tests patch as
`pdfmd.which`. The lazy loader `check_module()` is gone: the code imports `pdfmd_check` itself inside the functions.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

from pdfmd_base import core

from pdfmd_base import pandoc_run
from pdfmd_log import emit


# --- pdfmd --check: a linter (v3.26.15) ---------------------------------------------------------------------
#
# pdfmd_check/lint.py does the reading (plain text, no Pandoc); what needs pdfmd's own discovery is here: which
# files make up the document (a scaffold and its parts), which metadata files apply, and the keys of the
# bibliography the document names.


def bibliography_names(value) -> list[str]:
    return [str(item) for item in (value if isinstance(value, list) else [value]) if item and not isinstance(item, (dict, bool))]


def check_bibliography(document: Path, metadata_files: list[Path], variables: list[str], pandoc_options: list[str]):
    """(Declared bibliography and its keys, names of missing bibliography files)."""
    import pdfmd_check as check
    from pdfmd_args import metadata_command_layers
    from pdfmd_bibliography.sources import layers, locate, read_entries, resource_folders, values
    from pdfmd_check.lint import CITE_RE

    metadata = core.effective_metadata(document, metadata_files, variables)
    cli_metadata = metadata_command_layers(pandoc_options)[0][0]
    ordered = [metadata, *(mapping for _, mapping in layers([document], metadata_files, pandoc_options))]
    names = list(dict.fromkeys(name for layer in ordered for key in ("bibliography", "bibliography+")
                               for name in bibliography_names(layer.get(key))))
    references = [item for layer in ordered for key in ("references", "references+")
                  for item in values(layer.get(key))]
    keys = {str(item["id"]) for item in references if isinstance(item, dict) and "id" in item}
    complete = True
    missing: list[str] = []
    folders = [*resource_folders([document], metadata_files), *core.accessory_directories(document.parent, document.stem), Path.cwd()]
    for name in names:
        found = locate(name, folders)
        if not found.is_file():
            missing.append(name)
            continue
        parsed = read_entries(found)
        if parsed is None:
            complete = False                       # a kind of file pdfmd cannot list: report no key as missing
        else:
            keys.update(key for key, _ in parsed[0])
    declared = bool(names or any(isinstance(layer.get(key), list) for layer in ordered for key in ("references", "references+"))
                    or metadata.get("csl-json"))
    if not declared and (not metadata and not metadata_files                      # a fragment: its metadata is elsewhere
                         or core.find_lua_filters(document, metadata_files)           # a filter may do the citing
                         or core.first_pdfmd_option(document, metadata_files, "citation-engine") is not None):
        return None, missing
    nocite = " ".join(str(value) for value in values(cli_metadata.get("nocite", metadata.get("nocite"))))
    exempt = {(found[1] or found[2]).strip().casefold() for found in CITE_RE.finditer(nocite)}
    full = cli_metadata.get("full-bibliography", metadata.get("full-bibliography"))
    if re.search(r"(?<![\w@\\])@\*", nocite) or full is True or full == "true":
        exempt.add("*")
    return check.Bibliography(declared, frozenset(key.casefold() for key in keys), complete and not missing,
                              frozenset(keys), frozenset(exempt)), missing


def calc_check_records(files: list[Path], metadata_files: list[Path]) -> "tuple[list, list] | None":
    """What the calculator's filter finds in ``files`` for `--check` (pdfmd_lua/calc.lua, `-V pdfmd-calc-check=FILE`): ([(name, place)] of the
    uses of a name nothing defines, [(name, place, origin)] of every definition of a name that has several). None when there is
    no calculator in them, `calc` is off, Pandoc is not there or could not read them: the check then says nothing about names
    (a NOTE when Pandoc is the reason). Pandoc is run only for a document with a calculator span or div."""
    if core.calc_is_off(files[0], metadata_files):
        return None
    if not any(core.CALC_SPAN_RE.search(core.EMBED_BLOCK_RE.sub("", core.read_text_best_effort(file))) for file in files):
        return None
    pandoc = core.which("pandoc")
    if not pandoc:
        emit("note", None, "NOTE  --check: the names of the calculator are not checked without Pandoc", file=sys.stderr)
        return None
    arguments = core.calc_filter_args(files, metadata_files)
    if not arguments:
        return None
    with tempfile.TemporaryDirectory(prefix="pdfmd-calc-check-") as scratch:
        report = Path(scratch) / "names.tsv"
        command = [pandoc, *(str(file.resolve()) for file in files), "-t", "native", "-o", str(Path(scratch) / "out.native"),
                   *arguments, "-V", "pdfmd-calc-check=" + str(report)]
        try:
            done = pandoc_run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  cwd=core.pandoc_working_directory(files[0].parent))
        except OSError:
            return None
        if done.returncode != 0 or not report.is_file():
            emit("note", None, "NOTE  --check: the names of the calculator are not checked (Pandoc could not read the document)", file=sys.stderr)
            return None
        unescape = {"t": "\t", "n": "\n", "r": "\r", "\\": "\\"}
        uses, definitions = [], []
        for line in report.read_text(encoding="utf-8").split("\n"):
            fields = [re.sub(r"\\(.)", lambda found: unescape.get(found.group(1), found.group(1)), field) for field in line.split("\t")]
            if fields[0] == "U" and len(fields) == 3:
                uses.append((fields[1], fields[2]))
            elif fields[0] == "D" and len(fields) == 4:
                definitions.append((fields[1], fields[2], fields[3]))
    return (uses, definitions) if uses or definitions else None


def check_documents(target: Path, args) -> tuple[list[Path], Path]:
    """(the files `--check` reads for ``target``, the document's main file): the scaffold and its parts when
    it is one."""
    document = core.find_markdown(target)
    if document.suffix.lower() not in (".md", ".markdown"):
        raise FileNotFoundError(f"--check reads Markdown files; {core.display_path(document)} is not one")
    files = [document]
    metadata_files = core.scaffold_metadata_files(document, args.metadata_file)
    setting = core.parts_setting(document, metadata_files)
    if setting is not None and not core.auto_disabled(core.effective_no_auto(document, args.no_auto), "parts"):
        directory = core.parts_directory(document, setting)
        if directory is not None:
            files += core.collect_parts(directory)
    return files, document


def check_heading_ids(sources, document: Path, metadata_files: list[Path], args) -> list[tuple[int, str]]:
    """Read the ids with the selected Pandoc reader, only when a repeated heading needs them."""
    pandoc = core.which("pandoc")
    if not pandoc:
        return []
    no_auto = core.effective_no_auto(document, args.no_auto)
    reader = args.from_format if core.auto_disabled(no_auto, "reader") else core.resolve_from_format(
        document, args.from_format, metadata_files)[0]
    text = "\n\n".join([sources[0].text, *(core.strip_part_front_matter(source.text) for source in sources[1:])])
    try:
        done = pandoc_run([pandoc, "-f", reader or "markdown", "-t", "json"], input=text, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", cwd=core.pandoc_working_directory(document.parent))
        if done.returncode:
            return []
        blocks = json.loads(done.stdout)["blocks"]
    except (OSError, ValueError, KeyError):
        return []

    def identifiers(value):
        if isinstance(value, list):
            for item in value:
                yield from identifiers(item)
        elif isinstance(value, dict):
            if value.get("t") == "Header":
                level, attributes, _ = value["c"]
                yield level, attributes[0]
            elif "c" in value:
                yield from identifiers(value["c"])

    return list(identifiers(blocks))


def check_command(args, pandoc_options: list[str]) -> int:
    """Read and check the source, then measure figure heights if the document has pictures."""
    import pdfmd_check as check
    status = 0
    for target in (args.path or [Path.cwd()]):
        try:
            files, document = check_documents(target, args)
        except (FileNotFoundError, SystemExit) as error:
            print(str(error), file=sys.stderr)
            status = 1
            continue
        metadata_files = core.scaffold_metadata_files(document, args.metadata_file)
        try:
            ignore = check.parse_ignore(args.check_ignore) | check.parse_ignore(
                core.first_pdfmd_option(document, metadata_files, "check-ignore"))
        except ValueError as error:
            print(f"{core.display_path(document)}: {error}", file=sys.stderr)
            status = 1
            continue
        bibliography, missing = check_bibliography(document, metadata_files, args.variable or [], pandoc_options)
        inputs = []
        for path in files:
            try:
                inputs.append((path, check.Source(core.display_path(path), path.parent, path.read_text(encoding="utf-8-sig"))))
            except (OSError, UnicodeDecodeError) as error:
                print(f"{core.display_path(path)}: cannot read it ({error})", file=sys.stderr)
                status = 1
        folders = core.accessory_directories(document.parent, document.stem)
        limit = core.resolve_budget(document, metadata_files)[0]
        try:
            excerpts, citation_key, excerpt_keys = core.deferred("pdfmd_excerpts.checks", "lint_excerpts")(
                inputs, document, metadata_files, pandoc_options, core.effective_no_auto(document, args.no_auto),
                args.from_format)
        except ValueError as error:
            print(f"{core.display_path(document)}: {error}", file=sys.stderr)
            status = 1
            continue
        from pdfmd_cite import numbered
        from pdfmd_tables.prepass import unparsed_tables

        sources = [source for _, source in inputs]
        if "table-unparsed" not in ignore:
            no_auto = core.effective_no_auto(document, args.no_auto)
            reader = args.from_format
            if not core.auto_disabled(no_auto, "reader"):
                reader = core.resolve_from_format(document, reader, metadata_files)[0]
            excerpts.extend(check.Problem(source.label, line, "table-unparsed", message)
                            for source in sources for line, message in unparsed_tables(source.text, reader))
        _, reference_issue = numbered.inspect([path for path, _ in inputs], [source.text for source in sources],
                                              metadata_files, pandoc_options, args.from_format)
        if reference_issue == numbered.CHECK and numbered.CHECK not in ignore:
            excerpts.append(check.Problem(sources[0].label, 0, numbered.CHECK,
                                          "numbered source list matches but numbered-references is off"))
        problems = check.lint(sources, bibliography, ignore, folders, int(limit * 1048576) if limit else None,
                              citation_key=citation_key, extra_problems=excerpts, excerpt_keys=excerpt_keys,
                              calc=calc_check_records(files, metadata_files),
                              read_heading_ids=lambda: check_heading_ids(sources, document, metadata_files, args))
        if "figure-too-tall" not in ignore:
            from pdfmd_check.figures import figure_problems
            problems.extend(figure_problems(sources, document, metadata_files, args, pandoc_options))
        for name in missing:
            if "bibliography-missing" in ignore:
                continue
            line, label = 0, sources[0].label if sources else core.display_path(document)
            for source in sources:
                spot = next((number for number, text in enumerate(source.text.split("\n"), 1) if name in text), 0)
                if spot:
                    line, label = spot, source.label
                    break
            problems.insert(0, check.Problem(label, line, "bibliography-missing", f"bibliography file not found: {name}"))
        errors = sum(problem.severity == "error" for problem in problems)
        notes = sum(problem.severity == "note" for problem in problems)
        warnings = len(problems) - errors - notes
        for problem in problems:
            place = f"{problem.file}:{problem.line}" if problem.line else problem.file
            emit(problem.severity, problem.code, f"{place}: {problem.severity}: {problem.message}  [{problem.code}]")
        name = core.display_path(document) + (f" and {len(files) - 1} part(s)" if len(files) > 1 else "")
        if not problems:
            print(f"CHECK  {name}: no problems")
        else:
            counts = ", ".join(part for part in (f"{errors} error(s)" if errors else "",
                                                 f"{warnings} warning(s)" if warnings else "",
                                                 f"{notes} note(s)" if notes else "") if part)
            print(f"CHECK  {name}: {counts}")
        strict = core.resolve_strict(document, metadata_files)
        if errors or (warnings and strict):
            status = 1
    return status
