"""`pdfmd -b` / `--batch`: explicit inputs and the Markdown files of folders built separately, sequentially or with `-j`.

Moved out of `pdfmd.py`'s `run_main()` unchanged (v3.32.13). `core` is the `pdfmd` module itself (the file may be running as
`__main__`, so it is passed in, never imported: a second import would be a second copy with its own state). `run` returns
the list of results that `run_main()` prints. Several paths without `-r` also use this pipeline. Input selection happens
before single-file routing, so PDFs left by earlier builds are skipped rather than read back through batchocr."""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


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


def collect_inputs(core, paths: list[Path], recursive: bool = False, include_never: bool = False) -> list[Path]:
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
    if skipped:
        note = "NOTE  skipped non-input paths: " + ", ".join(core.display_path(path) for path in skipped)
        if len(paths) == 2 and any(path.suffix.lower() == ".pdf" and
                                  any(file.parent == path.resolve().parent for file in files) for path in skipped):
            note += "; to name the output, use -o NAME.pdf"
        print(note)
    if not files:
        raise SystemExit("No buildable input files remain; name a Pandoc input or a folder containing Markdown files")
    return files


def prepare_inputs(core, args) -> None:
    """Select batch mode before routing, preserving the existing single-document refusals downstream."""
    args.batch = True
    if args.report:
        raise SystemExit("Choose either --batch or --report/--book, not both")
    if args.out and not args.out.is_dir() and (args.out.suffix or args.out.is_file() or str(args.out) == "-"):
        raise SystemExit("-o/--out in batch mode takes an output directory, not a filename")
    args.path = collect_inputs(core, args.path or [Path.cwd()], args.recursive, args.include_never)


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
            core.route_ebook_input(document)
            destination = output or file.parent
            file = document.path[0]
        destinations[file] = destination
    return destinations


def run(core, *,
        args, embed_request, embeds_preamble, engines,
        metadata_for, need_engines, pandoc_options, paths,
        stamp_overrides, target_explicit, target_format, variables) -> list:
    # the helpers of pdfmd.py this function calls, bound here so the body reads as it did in run_main()
    ASSEMBLED_FORMAT, AUTO_LOG = core.ASSEMBLED_FORMAT, core.AUTO_LOG
    TEX_STANDALONE_FORMATS, announce_preambles = core.TEX_STANDALONE_FORMATS, core.announce_preambles
    convert_one, default_output_format = core.convert_one, core.default_output_format
    document_preambles, effective_no_auto = core.document_preambles, core.effective_no_auto
    is_assembled_document, resolve_engines = core.is_assembled_document, core.resolve_engines
    restore_worker_state, worker_state = core.restore_worker_state, core.worker_state

    files = list(paths)       # prepare_inputs has already expanded, filtered and resolved the paths
    output = Path.cwd() if args.destination_cwd else (args.out.resolve() if args.out else None)
    if output:
        output.mkdir(parents=True, exist_ok=True)
    destinations = prepare_epubs(core, args, files, output)
    files = list(destinations)
    if target_format == ASSEMBLED_FORMAT:
        # Not an assembly of an assembly: a file written by an earlier run
        # (NAME.assembled.md) would otherwise come out as NAME.assembled.assembled.md.
        files = [file for file in files if not is_assembled_document(file)]
        if not files:
            raise SystemExit("No buildable input files remain; the selected files are already assembled")
    jobs = max(1, args.jobs)
    batch_target = target_format

    def file_target(file):
        """This file's target: the command line's, else its own default-output."""
        if target_explicit or file.suffix.lower() not in (".md", ".markdown"):
            return batch_target
        found = metadata_for(file)
        chosen = default_output_format(file, found if isinstance(found, list) else ([found] if found else []))
        return chosen or batch_target

    def preamble_for(file):
        if not (file_target(file) in {"pdf", *TEX_STANDALONE_FORMATS} or embeds_preamble(file)):
            return []
        preambles = document_preambles(file, pandoc_options, effective_no_auto(file, args.no_auto))
        announce_preambles(preambles)
        return preambles
    if args.open and args.bopen is None:
        print("WARN  --open is ignored in batch mode (-b); it would open every converted file "
              "(--bopen SPEC opens the ones you say)", file=sys.stderr)
    def file_metadata_and_engines(file):
        # metadata_for(file) is looked up once and reused for both the
        # engine restriction (which may now fall through to this same
        # metadata file's own pdf-engine setting -- see resolve_engines)
        # and the actual conversion, rather than calling it twice.
        metadata = metadata_for(file)
        metadata_files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
        return metadata, resolve_engines(file, args.engine, engines, args.presentation, file_target(file), metadata_files, args.verbose)
    def work(file):
        need_engines(file_target(file))
        metadata, file_engines = file_metadata_and_engines(file)
        return convert_one(file, destinations[file], args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, preamble_files=preamble_for(file), target_format=file_target(file), from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format, embed=embed_request, trust_embedded=args.trust_embedded, self_contained=args.self_contained)
    results = []
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs, initializer=restore_worker_state,
                                 initargs=({**worker_state(), "DISPLAY_ALIAS": core.DISPLAY_ALIAS},)) as executor:
            futures = []
            for file in files:
                need_engines(file_target(file))
                metadata, file_engines = file_metadata_and_engines(file)
                file_preambles = preamble_for(file)
                if not args.verbose:
                    AUTO_LOG.flush()           # what the parent found for this file, before its worker's output
                futures.append(executor.submit(convert_one, file, destinations[file], args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, None, file_preambles, file_target(file), args.from_format, args.no_auto, args.verbose, args.debug, stamp_overrides, args.keep_aux, args.backup, args.backup_format, embed=embed_request, trust_embedded=args.trust_embedded, self_contained=args.self_contained))
            results = [future.result() for future in as_completed(futures)]
            results.sort(key=lambda result: result[0].name.casefold())
    else:
        results = [work(file) for file in files]
    return results
