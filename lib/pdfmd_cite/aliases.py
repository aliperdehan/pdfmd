"""Resolve citation aliases in the Pandoc document just before citeproc."""

import sys

from pdfmd_base import core
from pdfmd_log import emit

KEY = "citation-aliases"


def valid_mapping(value) -> bool:
    return isinstance(value, dict) and all(
        isinstance(item, str) and item and not any(char.isspace() for char in item)
        for pair in value.items() for item in pair
    )


def apply(command, document, metadata_files):
    options = command[:command.index("--")] if "--" in command else command
    position = next((index for index, arg in enumerate(options) if arg in ("--citeproc", "-C")), None)
    if position is None:
        return
    aliases = core.first_pdfmd_option(document, metadata_files, KEY)
    if aliases is None:
        return
    if not valid_mapping(aliases):
        emit("warning", None, f"WARN  {core.display_path(document)}: {KEY} expects a mapping of citation keys; ignoring it", file=sys.stderr)
        return
    if not aliases:
        return
    try:
        from pdfmd_lua import path
    except ImportError:
        core.pdfmd_lua_missing()
        return
    filter_path = path("citation_aliases")
    if filter_path is None:
        core.pdfmd_lua_missing("citation_aliases")
        return
    # Keep Pandoc's Markdown metadata reader from interpreting punctuation in a key.
    encoded = ",".join(f"{key.encode('utf-8').hex()}:{target.encode('utf-8').hex()}" for key, target in sorted(aliases.items()))
    command[position:position] = ["--metadata", "pdfmd-citation-aliases=" + encoded, "--lua-filter", str(filter_path)]


def show_warnings(result):
    """Surface alias diagnostics even when Pandoc succeeded and its stderr is hidden."""
    prefix = b"WARN  citation-aliases: " if isinstance(result.stderr, bytes) else "WARN  citation-aliases: "
    rest = []
    for line in result.stderr.splitlines(keepends=True):
        if line.startswith(prefix):
            text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
            emit("warning", None, text.rstrip(), file=sys.stderr)
        else:
            rest.append(line)
    result.stderr = prefix[:0].join(rest)
