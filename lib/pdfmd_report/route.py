"""`report-build: route` (the default, v3.32.14, entry 3ek): the report is built by the build of one document.

The files of the folder go to `convert_one()` as the first file and its parts, the way a parts-mode scaffold and its parts do
(`extra_inputs`), so the report gets everything a single document gets: the document font and the math font, `-f/--font`, the
retry with another font when a glyph is missing, the engine chain with the Typst and Calibre routes, `citation-engine`, the
cache route, the style sheets, the table-width note, the budgets and `--strict`. What is the report's own stays here: the
files and their order, the metadata found for the folder, the name `book.EXT`, the chapters' stamps (`REPORT_BUILD`), and the
lines that say which files went in.

`report-build: patch` keeps the report's own Pandoc command over the file list (see `pdfmd_report.run`). `core` is the
`pdfmd` module (see there)."""

from __future__ import annotations

from pathlib import Path

BUILDS = ("route", "patch")
DEFAULT_BUILD = "route"


def resolve_build(core, first: Path, metadata_files: list[Path]) -> str:
    """`pdfmd-options: report-build`, else `route`."""
    value = core.first_pdfmd_option(first, metadata_files, "report-build")
    if value is None or value == "":
        return DEFAULT_BUILD
    word = str(value).strip().lower()
    if word not in BUILDS:
        raise SystemExit(f"pdfmd-options: report-build: {value!r} is not one of {', '.join(BUILDS)}")
    return word


def output_path(core, args, target_format: str) -> Path:
    """Where the report is written: `book.EXT` in the current folder, or in/at what `-o` names."""
    extension = core.output_extension_for(target_format)
    if args.out:
        # Check is-a-directory BEFORE adding a default suffix -- a dot-less directory name (e.g. "out/") would otherwise
        # get ".pdf" appended to the directory's own name instead of being used as a directory.
        output = args.out / f"book{extension}" if args.out.is_dir() else core.default_output_path(args.out, target_format)
    else:
        output = Path.cwd() / f"book{extension}"
    return output.resolve()


def build(core, *, args, files: list[Path], excluded: list[Path], metadata, metadata_files: list[Path], target_format: str,
          engines: list[str], variables: list[str], pandoc_options: list[str], stamp_overrides: dict, embed_request,
          no_auto: list[str] | None, chapters: dict, notes: list[str]) -> None:
    output = output_path(core, args, target_format)
    preambles: list[Path] = []
    if target_format in {"pdf", *core.TEX_STANDALONE_FORMATS}:
        preambles = core.document_preambles(files[0], pandoc_options, no_auto)
        core.announce_preambles(preambles)
    for note in notes:
        print(f"NOTE  {note}")
    given = None if metadata is core.AUTO_METADATA_DISABLED else metadata
    core.REPORT_BUILD.clear()
    core.REPORT_BUILD.update(chapters=chapters, files=list(files), base=core.report_common_folder(files))
    try:
        built = core.convert_one(files[0], None, False, args.font, engines, variables, args.slide_level, pandoc_options,
                                 given, output, preambles, target_format=target_format, from_format=args.from_format,
                                 no_auto=args.no_auto, verbose=args.verbose, debug=args.debug,
                                 stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup,
                                 backup_format=args.backup_format, extra_inputs=list(files[1:]) or None,
                                 cache_cli=args.cache, embed=embed_request, trust_embedded=args.trust_embedded,
                                 self_contained=args.self_contained)
    finally:
        core.REPORT_BUILD.clear()
    ok = bool(built[1])
    for file in files:
        if not core.has_chapter_field(file):
            print(f"[WARNING] unnumbered Markdown included: {core.display_path(file)}")
        print(f"OK    {core.display_path(file)}")
    for file in excluded:
        print(f"SKIP  {core.display_path(file)}")
    if metadata is not core.AUTO_METADATA_DISABLED:
        for metadata_file in metadata_files:
            if args.metadata_file is None:
                core.AUTO_LOG.record_file("YAML", metadata_file, args.verbose)
            else:
                print(f"YAML  {core.display_path(metadata_file)}")
    if not args.verbose:
        core.AUTO_LOG.flush()
    print(f"{'OK  ' if ok else 'FAIL'}  REPORT  {core.display_path(output)}" + core.time_label(built) + core.engine_label(built))
    if args.verbose:
        for line in core.time_breakdown(built):
            print(line)
    if built[2]:
        print(built[2])
    if getattr(built, "record_path", None) and (args.verbose or not ok):
        print(f"{'      full record: ' if not ok else 'RECORD  '}{core.under_home(built.record_path)}")
    if not ok:
        raise SystemExit(1)
    if args.open:
        core.open_file(output)
