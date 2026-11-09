"""`pdfmd --watch`: recompile a document whenever it or its accessory files change.

`watch_signature`, `pinned_watch_argv` and `run_watch` are moved out of `pdfmd.py` unchanged (v3.33.3, SPLIT.md). `core`
is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first binding wins); the package reads `core.WATCH_INTERVAL`,
`core.PARTS_DIR_ALIASES` and `core.accessory_directories` when it runs. `run_watch` re-runs the script `core.__file__`
(`pdfmd.py`), not this package's `__file__`.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

core = None


def watch_signature(source: Path) -> float:
    """Max mtime across ``source``'s own directory and its ``metadata/``
    subfolder (if present) -- the same two locations pdfmd's own metadata/
    preamble/Lua-filter auto-discovery already searches
    (accessory_directories()), reused as a cheap, dependency-free,
    non-recursive proxy for "has anything --watch should react to
    changed". Non-recursive is deliberate: an unbounded directory tree
    scan polled every WATCH_INTERVAL seconds would be a real cost in a
    large project directory, for no real benefit -- pdfmd's own auto-
    discovery never looks any deeper than these two directories either.
    """
    latest = 0.0
    for directory in core.accessory_directories(source.parent, source.stem):
        for path in directory.glob("*"):
            if path.is_file():
                try:
                    latest = max(latest, path.stat().st_mtime)
                except OSError:
                    continue
    # A parts-mode document's parts live one level down (and deeper): watch
    # those too. Only the conventional folder names -- a custom
    # `parts: <folder>` is not followed, to keep this scan cheap and bounded.
    for name in core.PARTS_DIR_ALIASES:
        directory = source.parent / name
        if directory.is_dir():
            for path in directory.rglob("*.md"):
                try:
                    latest = max(latest, path.stat().st_mtime)
                except OSError:
                    continue
    return latest


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


def run_watch(source: Path, argv: list[str]) -> None:
    """Recompile ``source`` immediately, then again on each later change.

    Deliberately a thin wrapper that re-execs the whole, already-tested
    CLI as a fresh subprocess (the original argv, minus -w/--watch) on
    every recompile, rather than threading a rebuild loop through main()'s
    own batch/report/single-file branching -- disproportionate
    engineering for a feature expected to see light use (a convenience
    feature the author expects to use rarely). Polling a directory's own file mtimes (watch_signature(), not a
    filesystem-events library like watchdog) keeps this dependency-free,
    matching every other part of pdfmd. The signature is re-snapshotted
    AFTER each recompile, not just before, so the compile's own output
    file (and a --stamp write back into the source itself) never falsely
    re-triggers another immediate recompile.
    """
    rerun_argv = [arg for arg in argv if arg not in ("-w", "--watch")]
    script = str(Path(core.__file__).resolve())
    print(f"WATCH  {source}: watching {source.parent} for changes (Ctrl+C to stop)")
    try:
        while True:
            subprocess.run([sys.executable, script, *rerun_argv])
            signature = watch_signature(source)
            while watch_signature(source) == signature:
                time.sleep(core.WATCH_INTERVAL)
            print(f"WATCH  change detected, recompiling {source}...")
    except KeyboardInterrupt:
        print("\nWATCH  stopped")
