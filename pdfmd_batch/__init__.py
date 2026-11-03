"""`pdfmd -b` / `--batch`: every Markdown file of a folder built on its own, one after the other or in worker processes (`-j`).

Moved out of `pdfmd.py`'s `run_main()` unchanged (v3.32.13). `core` is the `pdfmd` module itself (the file may be running as
`__main__`, so it is passed in, never imported: a second import would be a second copy with its own state). `run` returns
the list of results that `run_main()` prints."""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


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
    restore_worker_state, skip_never, worker_state = core.restore_worker_state, core.skip_never, core.worker_state

    if len(paths) != 1 or not paths[0].is_dir():
        raise SystemExit("Batch mode requires one directory path")
    # .resolve() for the same reason as find_markdown(): a relative batch
    # directory plus a file in a subdirectory would otherwise make Pandoc's
    # cwd and its source-file argument both relative, and doubling up.
    files = skip_never(sorted(
        file.resolve() for file in
        (paths[0].rglob("*.md") if args.recursive else paths[0].glob("*.md"))
    ), args.include_never)
    if target_format == ASSEMBLED_FORMAT:
        # Not an assembly of an assembly: a file written by an earlier run
        # (NAME.assembled.md) would otherwise come out as NAME.assembled.assembled.md.
        files = [file for file in files if not is_assembled_document(file)]
    output = Path.cwd() if args.destination_cwd else (args.out.resolve() if args.out else None)
    if output:
        output.mkdir(parents=True, exist_ok=True)
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
        return convert_one(file, output, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, preamble_files=preamble_for(file), target_format=file_target(file), from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format, embed=embed_request, trust_embedded=args.trust_embedded, self_contained=args.self_contained)
    results = []
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs, initializer=restore_worker_state,
                                 initargs=(worker_state(),)) as executor:
            futures = []
            for file in files:
                need_engines(file_target(file))
                metadata, file_engines = file_metadata_and_engines(file)
                file_preambles = preamble_for(file)
                if not args.verbose:
                    AUTO_LOG.flush()           # what the parent found for this file, before its worker's output
                futures.append(executor.submit(convert_one, file, output, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, None, file_preambles, file_target(file), args.from_format, args.no_auto, args.verbose, args.debug, stamp_overrides, args.keep_aux, args.backup, args.backup_format, embed=embed_request, trust_embedded=args.trust_embedded, self_contained=args.self_contained))
            results = [future.result() for future in as_completed(futures)]
            results.sort(key=lambda result: result[0].name.casefold())
    else:
        results = [work(file) for file in files]
    return results
