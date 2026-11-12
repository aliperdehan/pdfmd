"""The command-line side of `--serve` and `--api`: the project's main document and the files pdfmd discovers beside it, the live
view's filters, the JSON core built for a folder, and the two commands.

Moved out of `pdfmd.py` unchanged (v3.33.7, SPLIT.md). `core` is the `pdfmd` module (unrelated to this package's own `core.py`),
bound when the module is first loaded (the first binding wins); the pdfmd names the code uses are read as `core.X` when it runs.
The package's own parts (`Core`, `run`), `pdfmd_web`, `pdfmd_lua` and the ranking classes are imported inside the functions, as
they were, so this module stays light.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from pdfmd_base import core

def serve_main_document(folder: Path) -> tuple[Path | None, str]:
    """The document a bare `pdfmd` builds in ``folder`` and why, for the web UI's project view (the data of `which_command`, not its text)."""
    files = sorted(folder.glob("*.md"), key=lambda path: path.name.casefold())
    if not files:
        return None, "there is no Markdown file in the folder"
    if len(files) == 1:
        return files[0], "the only Markdown file in the folder"
    from pdfmd_ranking import Ranking, RankingError, choose
    try:
        layers, own = core.ranking_layers(files)
        ranking = Ranking.from_layers(layers)
    except RankingError as error:
        return None, f"ranking: {error}"
    ranking.warnings += core.ranking_clashes(layers, own)
    if not core.priority_enabled(folder):
        return None, "bare pdfmd stops with the list of Markdown files here (--no-auto priority)"
    sources = core.source_markdown(files)
    choice = choose(core.priority_candidates(sources or files), ranking, show=core.display_path)
    if choice.winner is None:
        return None, choice.error or "no document is ranked first"
    return choice.winner, "ranked first by pdfmd's rules" + (f" ({choice.settled_by} settled a tie)" if choice.settled_by else "")


def serve_discovered(folder: Path, main: Path | None) -> list[dict]:
    """The files pdfmd would pick up beside ``main`` (metadata, bibliographies, styles), as `[{role, file}]`; a file outside the folder
    (the global metadata) carries `outside` and is written with `~`."""
    found: list[dict] = []
    try:
        metadata = core.find_metadata(folder, None, document=main, document_stem=main.stem if main else None)
    except Exception:
        metadata = None
    for path in ([] if metadata is None or metadata is core.AUTO_METADATA_DISABLED
                 else [metadata] if isinstance(metadata, Path) else list(metadata)):
        try:
            found.append({"role": "metadata", "file": Path(path).resolve().relative_to(folder).as_posix()})
        except ValueError:
            found.append({"role": "metadata", "file": str(path).replace(str(Path.home()), "~", 1), "outside": True})
    for pattern, role in (("*.bib", "bibliography"), ("*.csl", "csl")):
        found += [{"role": role, "file": path.name} for path in sorted(folder.glob(pattern), key=lambda item: item.name.casefold())]
    return found


@contextmanager
def serve_live_filters(source: Path, metadata_files: list[Path]) -> Iterator[list]:
    """The Pandoc arguments the live view of ``source`` gets: core.document_filter_args(), the list every build writes, so the document's own
    syntax (CSV tables, calc, callouts, page breaks, ...) is what it is in a build and a new one needs nothing here. Only one filter is
    the live view's own, and it runs first: pdfmd_lua/sourcepos.lua puts back what the position-marking reader changed in the document."""
    import pdfmd_lua
    first = pdfmd_lua.path("sourcepos")
    with core.csv_table_filter() as csv_filter:
        yield (["--lua-filter", str(first)] if first is not None else []) + core.document_filter_args(
            source, source, metadata_files, core.effective_no_auto(source, None), csv_filter, [])


def serve_core(folder: Path):
    """The JSON core of `--serve` and `--api` for the project folder ``folder`` (which becomes the working folder: pdfmd's
    discovery reads it)."""
    from pdfmd_serve import Core
    folder = folder.expanduser().resolve()
    os.chdir(folder)

    def pick(root: Path):
        main, why = serve_main_document(root)
        return main, why
    return Core(folder, pick_main=pick, discover=serve_discovered, write_bytes=core.atomic_write_bytes,
                display=lambda path: str(path).replace(str(Path.home()), "~", 1), filters=serve_live_filters,
                places=lambda: [core.cache_root()])


def serve_command(args) -> int:
    """`pdfmd --serve [FOLDER]`: the local server of the web UI. One JSON line on stdout says where it is."""
    folder = Path(args.serve or ".").expanduser()
    if not folder.is_dir():
        print(f"--serve takes a folder (the project): {folder} is not one", file=sys.stderr)
        return 2
    try:
        import pdfmd_web
        from pdfmd_serve import run
        from pdfmd_serve.shell import MAX_REQUEST_MB
    except ImportError as error:
        print(f"--serve needs pdfmd's pdfmd_serve and pdfmd_web packages: {error}", file=sys.stderr)
        return 2
    # the largest request body (`serve-max-request-mb` in the config's options: MB, 0 or less = no limit), read before serve_core
    # makes the folder the working one
    megabytes = core.option_flag_number(core.config_options().get("serve-max-request-mb"))
    megabytes = MAX_REQUEST_MB if megabytes is None else megabytes
    return run(serve_core(folder), Path(pdfmd_web.__file__).resolve().parent,
               max_body=int(megabytes * 1024 * 1024) if 0 < megabytes < float("inf") else None)


def api_command(words: list[str]) -> int:
    """`pdfmd --api METHOD PATH [JSON]`: one request of the web UI's API, answered on stdout (the project is the working folder).
    JSON may be `-` for standard input. Exit 1 when the answer is an error."""
    if len(words) not in (2, 3) or words[0].upper() not in ("GET", "POST", "PUT", "DELETE"):
        print("--api takes METHOD PATH [JSON]: pdfmd --api GET /api/project", file=sys.stderr)
        return 2
    try:
        body = (sys.stdin.read() if words[2] == "-" else words[2]).encode("utf-8") if len(words) == 3 else None
    except OSError as error:
        print(f"--api: {error}", file=sys.stderr)
        return 2
    status, answer = serve_core(Path.cwd()).handle(words[0], words[1], body)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    print(json.dumps(answer, ensure_ascii=False, indent=2))
    return 0 if status < 400 else 1
