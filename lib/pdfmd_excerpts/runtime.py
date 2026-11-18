"""Prepare the per-invocation Lua filter data, outside Pandoc's metadata."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from pdfmd_base import core

from .resolution import prepare


def filter_args(sources, metadata, options, no_auto, named_reader, temporary):
    state = prepare(sources, metadata, options, no_auto, diagnostics=True, named_reader=named_reader)
    if state is None:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return []
    source = pdfmd_lua.path("excerpts")
    if source is None:
        core.pdfmd_lua_missing("excerpts")
        return []
    path = Path(temporary()) / source.name
    shutil.copyfile(source, path)
    config = {"prefix": state.prefix, "records": state.records if state.records is not None else False,
              "bibliography": dict.fromkeys(state.bibliography, True), "page_terms": state.page_terms,
              "locator_terms": state.locator_terms, "missing": state.missing}
    path.with_suffix(".lua.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return ["--lua-filter", str(path)]
