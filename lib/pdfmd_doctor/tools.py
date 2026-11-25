"""Tool paths and provenance for the machine-readable doctor report."""

from __future__ import annotations

import os
from pathlib import Path

from pdfmd_base import core
from pdfmd_engines.tools import bundled_pandoc_directory, tools_directory


def source_for(name: str, path: str) -> str:
    tool = Path(path)
    recorded = core.TOOLS_FOUND.get(name)
    key = core.FOUND_TOOLS.get(name, (None,))[0]
    if recorded and tool.resolve() == Path(recorded[0]).resolve():
        if recorded[1] == "key":
            return f"options.{key}"
        return "installation"
    if name in core.FOUND_TOOLS:
        found, how = core.locate_tool(name)
        if found and how == "key" and tool.resolve() == Path(found).resolve():
            return f"options.{key}"
    if name == "calibre" and os.environ.get("PDFMD_CALIBRE"):
        return "PDFMD_CALIBRE"
    if name in core.BROWSER_ENGINES and os.environ.get("PDFMD_BROWSER") == path:
        return "PDFMD_BROWSER"
    if tool.parent == tools_directory() or core.data_root() in tool.parents:
        return "managed"
    if name == "pandoc" and tool.parent == bundled_pandoc_directory():
        return "bundled"
    if core.TEX_FOUND_AT and tool.parent == core.TEX_FOUND_AT:
        chosen = os.environ.get("PDFMD_TEX_BIN", "").strip()
        return "PDFMD_TEX_BIN" if chosen and tool.parent.resolve() == Path(chosen).expanduser().resolve() else "installation"
    if str(tool.parent) in os.environ.get("PATH", "").split(os.pathsep):
        return "PATH"
    return "installation"


def tool_reports(pandoc, version, quarto, soffice, calibre, reader, reader_version, shrinkers):
    from pdfmd_images import CONVERTERS

    tools = {}

    def add(name, path, version=None, source=None):
        tools[name] = {"name": name, "found": bool(path or source), "path": path, "version": version,
                       "source": source or (source_for(name, path) if path else None)}

    add("pandoc", pandoc, version or None)
    add("quarto", quarto)
    add("soffice", soffice)
    add("calibre", calibre)
    for name in (*core.PDF_ENGINES, *core.BROWSER_ENGINES):
        if name not in tools:
            add(name, core.engine_executable(name))
    for name in dict.fromkeys(("tesseract", "pdftotext", "pdftoppm", *(item[0] for item in core.DIAGRAM_TOOLS), *CONVERTERS)):
        if name not in tools:
            add(name, core.which(name))
    if reader:
        source = ("PDFMD_BATCHOCR" if os.environ.get("PDFMD_BATCHOCR") else
                  "Python module" if not isinstance(reader, str) and reader[1:2] == ["-m"] else None)
        add("batchocr", reader if isinstance(reader, str) else reader[0],
            ".".join(map(str, reader_version)) if reader_version else None, source)
    else:
        add("batchocr", None)
    for name, where in shrinkers:
        add(name, None if where == "Python module" else where, source="Python module" if where == "Python module" else None)
    return list(tools.values())
