"""`pdfmd --watch`: recompile a document whenever it or its accessory files change.

`watch_signature`, `pinned_watch_argv` and `run_watch` moved out of `pdfmd.py` in v3.33.3 (SPLIT.md). `core`
is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first binding wins); the package reads `core.WATCH_INTERVAL`,
`core.PARTS_DIR_ALIASES` and `core.accessory_directories` when it runs. `run_watch` re-runs the script `core.__file__`
(`pdfmd.py`), not this package's `__file__`.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from pdfmd_base import core


def watch_signature(source: Path, outputs: set[Path] | None = None) -> tuple:
    """Snapshot the files in discovery directories and conventional parts folders."""
    excluded = {path.resolve() for path in (outputs or set())} - {source.resolve()}
    entries = {}

    def record(path: Path) -> None:
        try:
            if path.resolve() in excluded or not path.is_file():
                return
            stat = path.stat()
            entries[str(path)] = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            pass

    for directory in core.accessory_directories(source.parent, source.stem):
        for path in directory.glob("*"):
            record(path)
    for name in core.PARTS_DIR_ALIASES:
        directory = source.parent / name
        if directory.is_dir():
            for path in directory.rglob("*.md"):
                record(path)
    return tuple(sorted(entries.items()))


def watch_output(source, args, default_target, scaffold_plan, section_plan) -> Path:
    """The same output path that single-file dispatch chooses for this build."""
    stem = scaffold_plan.output_stem if scaffold_plan is not None else (
        section_plan.output_stem if section_plan is not None else source.stem)
    target = default_target(source, core.scaffold_metadata_files(source, args.metadata_file))
    extension = core.output_extension_for(target, source)
    if args.out and not args.destination_cwd and args.out.is_dir():
        return args.out.resolve() / f"{stem}{extension}"
    if args.out:
        requested = Path.cwd() / args.out.name if args.destination_cwd else args.out.resolve()
        return core.default_output_path(requested, target)
    if args.destination_cwd:
        return Path.cwd() / f"{stem}{extension}"
    return source.with_name(f"{stem}{extension}")


def pinned_watch_argv(argv: list[str], given: list | None, chosen: Path) -> list[str]:
    """The command line a watch re-runs, with the document it chose pinned (v3.32.13): `pdfmd -w` in a folder of several
    Markdown files chose one by priority or age, and a later run must not choose again (the choice would move to whichever file
    was saved last). ``given`` is the paths the command line named: none, or only a `#section`/`@section` request, which the
    chosen document is put in front of. `--newest` is dropped, since the pinned path names the file."""
    argv = [arg for arg in argv if arg != "--newest"]
    if not given:
        return [*argv, "--", str(chosen)]
    token = str(given[0])
    if len(given) == 1 and token[:1] in ("#", "@") and token in argv:
        argv[argv.index(token)] = f"{chosen}{token}"
    return argv


def run_watch(source: Path, argv: list[str], args, default_target, scaffold_plan, section_plan) -> None:
    """Recompile ``source`` immediately, then again on each later change.

    Deliberately a thin wrapper that re-execs the whole, already-tested
    CLI as a fresh subprocess (the original argv, minus -w/--watch) on
    every recompile, rather than threading a rebuild loop through main()'s
    own batch/report/single-file branching -- disproportionate
    engineering for a feature expected to see light use (a convenience
    feature the author expects to use rarely). Polling a directory's own file mtimes (watch_signature(), not a
    filesystem-events library like watchdog) keeps this dependency-free,
    matching every other part of pdfmd. The signature is re-snapshotted
    AFTER each recompile, so a --stamp write back into the source itself
    never falsely re-triggers another immediate recompile. The output file
    is excluded from the snapshot.
    """
    rerun_argv = [arg for arg in argv if arg not in ("-w", "--watch")]
    script = str(Path(core.__file__).resolve())
    print(f"WATCH  {source}: watching {source.parent} for changes (Ctrl+C to stop)")
    try:
        while True:
            subprocess.run([sys.executable, script, *rerun_argv])
            outputs = {watch_output(source, args, default_target, scaffold_plan, section_plan)}
            signature = watch_signature(source, outputs)
            while watch_signature(source, outputs) == signature:
                time.sleep(core.WATCH_INTERVAL)
            print(f"WATCH  change detected, recompiling {source}...")
    except KeyboardInterrupt:
        print("\nWATCH  stopped")
