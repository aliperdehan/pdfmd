"""`pdfmd -b` / `--batch`: explicit inputs and the Markdown files of folders built separately, sequentially or with `-j`.

Moved out of `pdfmd.py`'s `run_main()` unchanged (v3.32.13). `core` is the `pdfmd` module itself (the file may be running as
`__main__`, so it is passed in, never imported: a second import would be a second copy with its own state). `run` returns
the list of results that `run_main()` prints. Several paths without `-r` also use this pipeline. Input selection happens
before single-file routing, so PDFs are outside the batch reader set."""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from pdfmd_base import core as bound_core
from pdfmd_log import CHATTER, document_chatter, emit, summary, transcript, verbose_output


# D33's preference among sources sharing an output.
SOURCE_LIKENESS = (
    frozenset({".md", ".markdown", ".mdown", ".mkd"}),
    frozenset({".txt", ".rst", ".org", ".adoc", ".asciidoc", ".textile", ".tex", ".latex",
               ".typ", ".typst", ".wiki", ".man"}),
    frozenset({".html", ".htm"}),
    frozenset({".docx", ".doc", ".odt", ".ott", ".rtf", ".epub", ".pptx", ".ppt", ".odp",
               ".xlsx", ".xls", ".ods"}),
)


def input_suffixes(core) -> set[str]:
    """The existing format tables, excluding output-only formats and non-Pandoc readers.

    A folder still discovers only *.md. Explicit files also accept the Markdown spellings and reader aliases used by
    single-file mode. Quarto and the other special single-file routes are deliberately outside this selection.
    """
    formats = (core.FORMAT_EXTENSION.keys()
               - {*core.PICTURE_FORMATS, *core.CALIBRE_ONLY_FORMATS, *core.SOFFICE_ONLY_FORMATS,
                  "ansi", core.ASSEMBLED_FORMAT})
    return ({extension for name, extension in core.FORMAT_EXTENSION.items() if name in formats}
            | {extension for extension, name in core.EXTENSION_FORMAT.items() if name in formats}
            | core.SUFFIX_READERS.keys() | set(core.MARKDOWN_LIKE_SUFFIXES))


def collect_inputs(core, paths: list[Path], recursive: bool = False, include_never: bool = False,
                   deferred_note: list | None = None) -> list[Path]:
    """Expand folders as before; keep explicit Pandoc inputs once, comparing resolved paths."""
    suffixes = input_suffixes(core)
    files, skipped, seen = [], [], set()
    explicit = {path.resolve() for path in paths if path.is_file() and path.suffix.lower() in suffixes}
    for path in paths:
        if not path.exists():
            raise SystemExit(f"{core.display_path(path)}: no such file or directory")
        if path.is_dir():
            candidates = sorted(file.resolve() for file in
                                (path.rglob("*.md") if recursive else path.glob("*.md")) if file.is_file())
            if not candidates:
                skipped.append(path)
            discovered = set(core.skip_never([file for file in candidates if file not in explicit], include_never))
            candidates = [file for file in candidates if file in explicit or file in discovered]
        elif path.is_file() and path.suffix.lower() in suffixes:
            candidates = [path.resolve()]
        else:
            skipped.append(path)
            candidates = []
        for file in candidates:
            if file not in seen:
                files.append(file)
                seen.add(file)
    if deferred_note is not None and files:
        deferred_note.extend(skipped)
    else:
        selection_note(core, paths, files, skipped, [])
    if not files:
        raise SystemExit("No buildable input files remain; name a Pandoc input or a folder containing Markdown files")
    return files


def selection_note(core, paths, files, skipped, outputs, collisions=()):
    if skipped:
        note = "NOTE  skipped non-input paths: " + ", ".join(core.display_path(path) for path in skipped)
        if len(paths) == 2 and any(path.suffix.lower() == ".pdf" and
                                  any(file.parent == path.resolve().parent for file in files) for path in skipped):
            note += "; to name the output, use -o NAME.pdf"
        emit("note", None, note)
    if outputs:
        emit("note", None, "NOTE  skipped built outputs: " + ", ".join(core.display_path(path) for path in outputs))
    for file, chosen in collisions:
        emit("note", None, f"NOTE  skipped (same output as {core.display_path(chosen)}): {core.display_path(file)}")


def prepare_inputs(core, args) -> None:
    """Select batch mode before routing, preserving the existing single-document refusals downstream."""
    args.batch = True
    if args.report:
        raise SystemExit("Choose either --batch or --report/--book, not both")
    if args.out and not args.out.is_dir() and (args.out.suffix or args.out.is_file() or str(args.out) == "-"):
        raise SystemExit("-o/--out in batch mode takes an output directory, not a filename")
    args.batch_original_paths = args.path or [Path.cwd()]
    args.batch_skipped = []
    args.path = collect_inputs(core, args.batch_original_paths, args.recursive, args.include_never, args.batch_skipped)


def prepare_epubs(core, args, files: list[Path], output: Path | None) -> dict[Path, Path | None]:
    """Use the single-file EPUB reader before helpers inspect text; retain each original output folder."""
    from copy import copy
    destinations = {}
    for file in files:
        destination = output
        if file.suffix.lower() == ".epub":
            document = copy(args)
            # Only the reading stage: its suggested PDF name is unused, and media stay with the scratch Markdown.
            document.path, document.batch, document.out, document.to = [file], False, None, "pdf"
            from pdfmd_engines.tools import tool_paths
            with tool_paths(directory=file.parent):
                core.route_ebook_input(document)
            destination = output or file.parent
            file = document.path[0]
        destinations[file] = destination
    return destinations


def convert_logged(log_path, positional, options):
    with transcript.scope(log_path), summary.scope() as tally:
        built = bound_core.convert_one(*positional, **options)
    built.log_path = log_path
    built.diagnostic_counts = tally.counts
    return built


def run(core, *,
        args, embed_request, embeds_preamble, engines,
        metadata_for, pandoc_options, paths, plan_bridge,
        stamp_overrides, stop_at, target_explicit, target_format, variables, cli_export=None) -> list:
    from functools import cache

    from pdfmd_buildinfo import record
    from pdfmd_crop.build import CROPPED_OFFICE, build_target, crop_requested, pdf_formats
    from pdfmd_crop.targets import build_batch_writers
    from pdfmd_engines.tools import tool_paths
    from pdfmd_routing import output as routing
    from pdfmd_run import presentation as slides

    # the helpers of pdfmd.py this function calls, bound here so the body reads as it did in run_main()
    ASSEMBLED_FORMAT, AUTO_LOG = core.ASSEMBLED_FORMAT, core.AUTO_LOG
    TEX_STANDALONE_FORMATS, announce_preambles = core.TEX_STANDALONE_FORMATS, core.announce_preambles
    default_output_format = core.default_output_format
    document_preambles, effective_no_auto = core.document_preambles, core.effective_no_auto
    is_assembled_document, resolve_engines = core.is_assembled_document, core.resolve_engines
    restore_worker_state, worker_state = core.restore_worker_state, core.worker_state

    # prepare_inputs has already expanded folders and selected supported reader formats.
    folders = {Path.cwd(), *(file.parent for file in paths),
               *(path.resolve() for path in args.batch_original_paths if path.is_dir())}
    roots = {core.cache_root() / "builds", *(folder / core.LOCAL_CACHE_DIRNAME / "builds" for folder in folders)}
    owned = record.matching_outputs(paths, roots)
    outputs = [file for file in paths if file in owned]
    files = [file for file in paths if file not in owned]
    if not files:
        selection_note(core, args.batch_original_paths, files, args.batch_skipped, outputs)
        raise SystemExit("No buildable input files remain; the selected files are built outputs")
    output = Path.cwd() if args.destination_cwd else (args.out.resolve() if args.out else None)
    if target_format == ASSEMBLED_FORMAT:
        # Not an assembly of an assembly: a file written by an earlier run
        # (NAME.assembled.md) would otherwise come out as NAME.assembled.assembled.md.
        files = [file for file in files if not is_assembled_document(file)]
        if not files:
            selection_note(core, args.batch_original_paths, files, args.batch_skipped, outputs)
            raise SystemExit("No buildable input files remain; the selected files are already assembled")
    jobs = max(1, args.jobs)
    @cache
    def file_presentation(file):
        if args.presentation is not None:
            return slides.source(file, None, args.presentation)
        # EPUB is unpacked to Markdown before reading its options.
        if file.suffix.lower() == ".epub":
            return None
        return slides.source(file, metadata_for(file, announce=False), None)

    @cache
    def file_formats(file):
        """This file's target: the command line's, else its own default-output."""
        if file_presentation(file) and stop_at == "tex":
            return "beamer"
        if file_presentation(file) or target_explicit or file.suffix.lower() not in (".md", ".markdown"):
            return ",".join(args.to_many) if args.to_many else cli_export.primary if cli_export else target_format
        found = metadata_for(file, announce=False)
        chosen = default_output_format(file, found if isinstance(found, list) else ([found] if found else []))
        return chosen or target_format

    @cache
    def file_cropped(file):
        if not set(file_formats(file).split(",")) & set(CROPPED_OFFICE):
            return False
        metadata = metadata_for(file, announce=False)
        return crop_requested(file, metadata if isinstance(metadata, list) else [metadata] if metadata else [])

    @cache
    def file_plan(file):
        return build_target(file_formats(file), cropped=file_cropped(file))

    def file_target(file):
        return file_plan(file)[0]

    def file_output(file):
        target, export = file_plan(file)
        return export.primary if export else target.split(",")[0]

    def separate_writers(file):
        formats = file_formats(file).split(",")
        return formats if len(formats) > 1 and any(name not in pdf_formats(file_cropped(file)) for name in formats) else None

    def writer_outputs(file, directory, source=None):
        formats = separate_writers(file) or ()
        supported = pdf_formats(file_cropped(file))
        pdf_writers = sum(name in supported for name in formats)
        return {name: routing.planned(source or file, directory, name)
                for name in formats if name not in supported or pdf_writers == 1}

    def identity(path):
        try:
            info = path.stat()
        except OSError:
            return None
        return record.file_identity(info) if info.st_ino else None

    def original(file):
        return core.DISPLAY_ALIAS.get(file, file)

    def preference(file):
        file = original(file)
        rank = next((i for i, suffixes in enumerate(SOURCE_LIKENESS) if file.suffix.lower() in suffixes),
                    len(SOURCE_LIKENESS))
        return rank, file.name, str(file)

    def shared_destinations(plans):
        claimed = {}
        pairs = []
        for file in sorted(plans, key=preference):
            paths = [output_file.resolve() for output_file in plans[file]]
            keys = [identity(path) or path for path in paths]
            if chosen := next((claimed[key] for key in keys if key in claimed), None):
                pairs.append((file, chosen))
            else:
                claimed.update(dict.fromkeys(keys, file))
        return pairs

    sources = set(files)
    source_ids = {key for file in files if (key := identity(file)) is not None}
    collisions = []
    epubs = {file for file in files if file.suffix.lower() == ".epub"}
    if epubs and target_explicit:
        # With a fixed target we can skip a losing EPUB before unpacking its Markdown.
        plans = {}
        for file in files:
            source = file.with_suffix(".md") if file in epubs else file
            plans[file] = (routing.planned(source, output, file_output(file)),
                           *writer_outputs(file, output, source).values())
        collisions = shared_destinations(plans)
        excluded = {file for file, _ in collisions}
        files = [file for file in files if file not in excluded]
    destinations = prepare_epubs(core, args, files, output)
    planned_outputs = {file: routing.planned(file, directory, file_output(file)) for file, directory in destinations.items()}
    separate_outputs = {file: writer_outputs(file, directory) for file, directory in destinations.items()}
    plans = {file: (path, *separate_outputs[file].values()) for file, path in planned_outputs.items()}
    for file, chosen in shared_destinations(plans):
        collisions.append((original(file), original(chosen)))
        del planned_outputs[file]
    files = list(planned_outputs)
    selection_note(core, args.batch_original_paths, [original(file) for file in files], args.batch_skipped, outputs, collisions)
    if output:
        output.mkdir(parents=True, exist_ok=True)
    reserved = {path.resolve() for file in files for path in plans[file]}
    for file in files:
        if request := file_presentation(file):
            slides.validate(request, file_target(file), stop_at, document=file)
    plan_bridge(target_format)

    def preamble_for(file, metadata):
        if file.suffix.lower() in core.OFFICE_INPUT_EXTENSIONS:
            return []
        if not (file_target(file) in {"pdf", *TEX_STANDALONE_FORMATS} or embeds_preamble(file)):
            return []
        preambles = document_preambles(file, pandoc_options, effective_no_auto(file, args.no_auto),
                                       metadata if isinstance(metadata, list) else ([metadata] if metadata else []))
        announce_preambles(preambles)
        return preambles
    if args.open and args.bopen is None:
        emit("warning", None, "WARN  --open is ignored in batch mode (-b); it would open every converted file "
              "(--bopen SPEC opens the ones you say)", file=sys.stderr)
    def file_build(file):
        request = file_presentation(file)
        target = file_target(file)
        if target not in ("pdf", "ansi") and not core.which("pandoc"):
            raise SystemExit(core.PANDOC_MISSING)
        candidates = core.select_engines(args.engine, False) if target == "pdf" and not request else engines
        if file.suffix.lower() in core.OFFICE_INPUT_EXTENSIONS:
            return False, None, candidates
        metadata = metadata_for(file)
        metadata_files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
        file_engines = (slides.engines(file, metadata_files, args.engine, request, target, args.verbose)
                        if request else resolve_engines(file, args.engine, candidates, False, target, metadata_files, verbose_output(args.verbose)))
        return bool(request), metadata, file_engines
    run_log = transcript.CURRENT.get()
    initial_logs = set()

    def protect_output(file, planned, target, metadata, export=None):
        destination = planned.resolve()
        destination_id = identity(destination)
        source_clash = destination != file and (destination in sources or
            (destination_id in source_ids and destination_id != identity(file)))
        if export is None or export.keep_pdf or source_clash:
            planned = routing.protected(file, planned, target, metadata, reserved=reserved, source_clash=source_clash)
        reserved.add(planned.resolve())
        return planned

    def work(file, executor=None):
        with transcript.scope(pending=True) as log:
            given = metadata_for(file, announce=False) if file.suffix.lower() not in core.OFFICE_INPUT_EXTENSIONS else None
            metadata_files = given if isinstance(given, list) else [given] if given else []
            summary.select(args.summary, file, metadata_files, batch=True)
            with document_chatter(file, metadata_files), tool_paths(file, metadata_files):
                target, export = file_plan(file)
                if formats := separate_writers(file):
                    # The writer subprocesses each open the transcript for their actual output.
                    chatter = CHATTER.get()
                    cropped = file_cropped(file)
                    overrides = {}
                    for name, planned in separate_outputs[file].items():
                        writer_target, writer_export = build_target(name, cropped=cropped)
                        destination = protect_output(file, planned, writer_target, metadata_files, writer_export)
                        if destination != planned:
                            overrides[name] = destination
                    if executor is not None:
                        AUTO_LOG.flush(shown=not verbose_output(args.verbose))
                        return executor.submit(build_batch_writers, args, file, formats, cropped, sys.argv[1:],
                                               chatter=chatter, output_overrides=overrides)
                    return build_batch_writers(args, file, formats, cropped, chatter=chatter, output_overrides=overrides)
                log_path = transcript.destination(args.log, file, metadata_files)
                output_file = protect_output(file, planned_outputs[file], target, metadata_files, export)
                if log_path is not None:
                    if run_log is not None and log_path not in initial_logs:
                        log.pending[:0] = run_log.pending or []
                        initial_logs.add(log_path)
                log.start(log_path, file, output_file)
                presentation, metadata, file_engines = file_build(file)
                preambles = preamble_for(file, metadata)
                verbose = verbose_output(args.verbose)
                positional = (file, destinations[file], presentation, args.font, file_engines, variables,
                              args.slide_level, pandoc_options, metadata)
                options = dict(output_file=output_file, output_resolved=True,
                               preamble_files=preambles, target_format=target, from_format=args.from_format,
                               no_auto=args.no_auto, verbose=verbose, debug=args.debug, stamp_overrides=stamp_overrides,
                               keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format,
                               embed=embed_request, trust_embedded=args.trust_embedded,
                               self_contained=args.self_contained, cache_cli=args.cache, export=export)
                if executor is not None:
                    AUTO_LOG.flush(shown=not verbose)    # what the parent found, before its worker's output
                    return executor.submit(convert_logged, log_path, positional, options)
                built = core.convert_one(*positional, **options)
                built.log_path = log_path
                return built
    results = []
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs, initializer=restore_worker_state,
                                 initargs=({**worker_state(), "DISPLAY_ALIAS": core.DISPLAY_ALIAS},)) as executor:
            futures = [work(file, executor) for file in files]
            results = [future.result() for future in as_completed(futures)]
            results.sort(key=lambda result: result[0].name.casefold())
    else:
        results = [work(file) for file in files]
    return results
