"""The tables' commands and settings: the cap and cell reader of a `.csv` table (`csv_defaults`, with `CSV_CUTS`), the `.csv` filter's
arguments (`csv_table_filter_args`, `spreadsheet_args`), the table-keep row count Pandoc gets (`table_keep_metadata`), and
`--extract-tables` / `--expand-tables` (`tables_command`).

Moved out of `pdfmd.py` unchanged (v3.33.24, SPLIT.md), with `CSV_CUTS`. `core` is the `pdfmd` module, bound when the module is first
loaded (a stand-in in `pdfmd.py` loads it on the first call; the first binding wins); the pdfmd names the code uses
(`AUTO_METADATA_DISABLED`, `CSV_DEFAULTS`, `CSV_DELIMITER_NAMES`, `CSV_DELIMITER_WORDS`, `CSV_ENV`, `CSV_NOTE_ENV`, `TABLE_KEEP_ENV`,
`atomic_write_text`, `auto_disabled`, `backup_before_edit`, `cache_root`, `contains_csv_table`, `csv_count`, `csv_is_off`,
`csv_note_mode`, `display_path`, `find_markdown`, `find_metadata`, `first_pdfmd_option`, `option_flag`, `pandoc_version`,
`plan_scaffold`, `read_text_best_effort`, `resolve_from_format`, `resolve_soffice`, `run_soffice`, `table_keep_count` and `which`) are
read as `core.X` when it runs. `core.cache_root`, `core.pandoc_version`, `core.resolve_soffice` and `core.which` are patched by tests
as `pdfmd.X`. `csv_defaults`, `csv_table_filter_args` and `table_keep_metadata` are called from functions that stay in `pdfmd.py`
through the stand-ins there.
"""

from __future__ import annotations

import contextlib
import difflib
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

core = None


CSV_CUTS = ("ends", "head")


def csv_defaults(md_path: Path | None, metadata_files: list[Path] = ()) -> dict:
    """The cap, the header rule and the cell reader of every `.csv` div of ``md_path`` (see CSV_DEFAULTS)."""
    chosen = dict(core.CSV_DEFAULTS)
    option = core.first_pdfmd_option(md_path, list(metadata_files), "csv") if md_path is not None else None
    where = core.display_path(md_path) if md_path is not None else "csv"
    if option is not None and not isinstance(option, dict):
        if core.option_flag(option) is None:
            raise SystemExit(f"{where}: pdfmd-options.csv must be a mapping (rows, cols, header, reader) or on/off, not {option!r}")
        option = {"enabled": option}                   # `csv: off`: no caps to read (csv_is_off acts on it)
    option = option or {}
    for key in ("rows", "cols"):
        value = os.environ.get(core.CSV_ENV[key])
        if value is None and option.get(key) is not None:
            value = option[key]
            if core.csv_count(value) is None:
                raise SystemExit(f"{where}: pdfmd-options.csv.{key} must be a whole number or all, not {value!r}")
        if value is not None and core.csv_count(value) is not None:
            chosen[key] = core.csv_count(value)
    if option.get("header") is not None:
        flag = core.option_flag(option["header"])
        if flag is None:
            raise SystemExit(f"{where}: pdfmd-options.csv.header must be true or false, not {option['header']!r}")
        chosen["header"] = flag
    if option.get("reader"):
        chosen["reader"] = str(option["reader"]).strip()
    if option.get("delimiter"):
        text = str(option["delimiter"]).strip()
        if text.casefold() != "auto" and text.casefold() not in core.CSV_DELIMITER_NAMES and len(text) != 1:
            raise SystemExit(f"{where}: pdfmd-options.csv.delimiter must be auto, a name "
                             f"({', '.join(core.CSV_DELIMITER_NAMES)}) or one character, not {text!r}")
        chosen["delimiter"] = text.casefold() if len(text) > 1 else text
    if option.get("cut"):
        cut = str(option["cut"]).strip().casefold()
        if cut not in CSV_CUTS:
            raise SystemExit(f"{where}: pdfmd-options.csv.cut must be ends or head, not {option['cut']!r}")
        chosen["cut"] = cut
    note = os.environ.get(core.CSV_NOTE_ENV)
    if note is None and option.get("note") is not None:
        note = option["note"]
        if core.csv_note_mode(note) is None:
            raise SystemExit(f"{where}: pdfmd-options.csv.note must be short, off or full, not {note!r}")
    if note is not None and core.csv_note_mode(note) is not None:
        chosen["note"] = core.csv_note_mode(note)
    return chosen


def table_keep_metadata(md_path: Path | None, metadata_files: list[Path] = ()) -> list[str]:
    """``["-M", "tablekeep=N"]`` when the command line or `pdfmd-options.table-keep` names N, else []."""
    value = os.environ.get(core.TABLE_KEEP_ENV)
    if value is None and md_path is not None:
        value = core.first_pdfmd_option(md_path, list(metadata_files), "table-keep")
    if value is None or str(value).strip() == "":
        return []
    found = core.table_keep_count(value)
    if found is None:
        where = core.display_path(md_path) if md_path is not None else "table-keep"
        raise SystemExit(f"{where}: pdfmd-options.table-keep must be a whole number of rows (0 lets every table break), "
                         f"not {value!r}")
    return ["-M", f"tablekeep={found}"]


def spreadsheet_args(files: list[Path]) -> list[str]:
    """`--metadata-file` with the CSV each spreadsheet a `.csv` block names was turned into (v3.29.23: `::: {.csv file="a.xlsx"
    sheet="Run 2"}`), or []. A sheet that cannot be read is a WARN naming what to install."""
    try:
        from pdfmd_tables import scan, sheets
    except ImportError:
        return []
    mapping: dict[str, str] = {}
    for source in files:
        text = core.read_text_best_effort(Path(source))
        if not any(suffix in text.lower() for suffix in sheets.SUFFIXES):
            continue
        for block in scan.find_csv_blocks(text):
            name = block.attributes.get("file", "")
            if not name or not sheets.is_spreadsheet(name):
                continue
            key = f"{name}|{block.attributes.get('sheet', '')}"
            if key in mapping:
                continue
            path = (Path(source).parent / name).resolve()
            try:
                mapping[key] = sheets.cached_csv(path, block.attributes.get("sheet") or None, core.cache_root() / "sheets",
                                                 core.resolve_soffice(), core.run_soffice).as_posix()      # Pandoc reads metadata as Markdown: a backslash would go
            except (OSError, sheets.SheetError) as error:
                said = "no such file" if isinstance(error, FileNotFoundError) else error
                print(f"WARN  {core.display_path(Path(source))}: {name}: {said}", file=sys.stderr)
    if not mapping:
        return []
    digest = hashlib.sha1(json.dumps(mapping, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    target = core.cache_root() / "sheets" / "maps" / f"{digest}.yaml"
    try:
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("pdfmd-sheet-map: " + json.dumps(mapping, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        return []
    return ["--metadata-file", str(target)]


def csv_table_filter_args(sources: Path | list[Path], no_auto: list[str] | None,
                          csv_filter_path: Path, metadata_files: list[Path] = ()) -> list[str]:
    """``--lua-filter`` for CSV_TABLE_LUA_FILTER, only when actually needed.

    Mirrors crossref_filter_args()'s own shape and reasoning: silently a
    no-op when --no-auto csvtable disables it or no source actually uses
    a `.csv` div. Must run BEFORE the table-width filter (the caller is
    responsible for that ordering) so a CSV-generated table gets the same
    width-balancing pass a hand-written one would.
    """
    if core.auto_disabled(no_auto, "csvtable"):
        return []
    files = sources if isinstance(sources, list) else [sources]
    if not any(core.contains_csv_table(file) for file in files):
        return []
    if core.csv_is_off(files[0], metadata_files):               # `csv: off`: the div stays as written
        return []
    args = ["--lua-filter", str(csv_filter_path)]
    args += spreadsheet_args(files)
    chosen = csv_defaults(files[0], metadata_files)
    for key, value in chosen.items():            # only what differs: the filter's own defaults are the same
        if key == "delimiter":
            value = core.CSV_DELIMITER_WORDS.get(value, value)     # a name survives -M, a tab or a colon would not
        if value != core.CSV_DEFAULTS[key]:
            args += ["-M", f"pdfmd-csv-{key}={str(value).lower() if isinstance(value, bool) else value}"]
    return args


def tables_command(args) -> int:
    """Rewrite documents so their tables are `.csv` blocks (or the other way round). Returns the exit status."""
    try:
        import pdfmd_tables as tables
    except ImportError:
        print("ERROR  --extract-tables needs the pdfmd_tables package (a full install of pdfmd-cli).", file=sys.stderr)
        return 1
    if args.extract_inline_csv and not args.expand_tables:
        args.extract_tables = True
    if args.extract_tables and args.expand_tables:
        print("ERROR  --extract-tables and --expand-tables are opposites; pick one.", file=sys.stderr)
        return 1
    pandoc = core.which("pandoc")
    names = [name for name in re.split(r"[,\s]+", args.table_names or "") if name] or None
    only_tables: set[int] | None = None
    if args.table_numbers:
        only_tables = set()
        for piece in re.split(r"[,\s]+", args.table_numbers.strip()):
            span = re.fullmatch(r"(\d+)(?:-(\d+))?", piece)
            if not span or int(span.group(1)) < 1:
                print(f"ERROR  --table-numbers: {piece!r} is not a table number (1, 3 or 2-4)", file=sys.stderr)
                return 1
            only_tables.update(range(int(span.group(1)), int(span.group(2) or span.group(1)) + 1))
    csv_filter = None
    try:
        import pdfmd_lua
        csv_filter = pdfmd_lua.path("csv_table")
    except ImportError:
        pass
    documents: list[Path] = []
    scaffolds: dict[Path, Path] = {}        # a part -> the report it belongs to: its paths are relative to the report's folder
    for target in (args.path or [Path.cwd()]):
        try:
            document = core.find_markdown(target)
        except FileNotFoundError as error:
            print(f"ERROR  {error}", file=sys.stderr)
            return 1
        with contextlib.redirect_stderr(io.StringIO()):
            plan = core.plan_scaffold(document, [], args.no_auto, args.metadata_file)
        for item in (plan.files if plan else [document]):
            if item not in documents:
                documents.append(item)
            if plan:
                scaffolds[item] = plan.scaffold
    if names and len(documents) > 1:       # a part given by name: the report's own file has no tables to name
        holding = [item for item in documents if tables.find_tables(item.read_text(encoding="utf-8"))]
        if len(holding) != 1:
            print("ERROR  --table-names names the tables of one document; this is a document in parts "
                  f"with tables in {len(holding)} of its files (give the one part: pdfmd parts/NAME.md ...).",
                  file=sys.stderr)
            return 1
        names_for = holding[0]
    else:
        names_for = documents[0] if documents else None
    status = 0
    for document in documents:
        text = document.read_text(encoding="utf-8")
        owner = scaffolds.get(document, document)       # the report a part is built into: its folder and reader
        base = owner.parent
        found = core.find_metadata(base.resolve(), args.metadata_file, document_stem=owner.stem, document=owner)
        linked = [] if found is core.AUTO_METADATA_DISABLED or found is None else (found if isinstance(found, list) else [found])
        reader = (args.from_format or "markdown") if core.auto_disabled(args.no_auto, "reader") \
            else (core.resolve_from_format(owner, args.from_format, linked)[0] or "markdown")
        prefix = re.sub(r"^[\d._ -]+", "", document.stem) + "-" if document != owner else ""
        try:
            if args.extract_tables:
                result = tables.extract(text, base, pandoc=pandoc, names=names if document == names_for else None, directory=args.tables_dir,
                                        inline=args.tables_inline, reader=reader,
                                        pandoc_version=core.pandoc_version() if pandoc else None,
                                        inline_csv=args.extract_inline_csv, prefix=prefix, only=only_tables)
            else:
                result = tables.expand(text, base)
            if result.changed and pandoc and args.extract_tables:
                scratch_files: list[Path] = []
                try:
                    for name, data in result.files.items():     # the new document reads them: put them there for the check
                        target = base / name
                        if not target.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text(data, encoding="utf-8")
                            scratch_files.append(target)
                    problems = tables.same_tables(pandoc, text, result.text, base, csv_filter, reader)
                    if not problems:
                        result.report.append("checked: Pandoc reads the same tables from the new document")
                finally:
                    for target in scratch_files:
                        target.unlink(missing_ok=True)
                        try:
                            target.parent.rmdir()
                        except OSError:
                            pass
                if problems:
                    print(f"ERROR  {core.display_path(document)}: Pandoc would read different tables after the change "
                          f"({'; '.join(problems)}). Nothing was written.", file=sys.stderr)
                    status = 1
                    continue
        except tables.TablesError as error:
            print(f"ERROR  {core.display_path(document)}: {error}", file=sys.stderr)
            status = 1
            continue
        print(f"{core.display_path(document)}:")
        for line in result.report:
            print(f"  {line}")
        if not result.changed:
            continue
        if args.dry_run:
            diff = difflib.unified_diff(text.split("\n"), result.text.split("\n"), "before", "after", lineterm="", n=1)
            print("\n".join(diff))
            for name in result.files:
                print(f"  would write {name}")
            continue
        backup = core.backup_before_edit(document)
        if backup is None:
            status = 1
            print(f"ERROR  {core.display_path(document)}: not changed, since its backup could not be made.", file=sys.stderr)
            continue
        for name, data in result.files.items():
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            core.atomic_write_text(target, data)
        core.atomic_write_text(document, result.text)
        print(f"  BACKUP  {core.display_path(backup)}")
        print(f"  WROTE   {core.display_path(document)}" + (f" and {len(result.files)} CSV file"
              f"{'' if len(result.files) == 1 else 's'}" if result.files else ""))
    return status
