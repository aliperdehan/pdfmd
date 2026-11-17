"""The opt-in engine pass for column widths; ordinary count builds never enter it.

Pandoc still runs with the build's inputs, metadata, headers and filters. Only its writer/output and the
table-width filter role change. The resulting source, the executable and its options key a cache of engine measurements.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pdfmd_base import core

LATEX = ("pdflatex", "xelatex", "lualatex", "tectonic")


def requested(sources: list[Path], metadata: list[Path]) -> bool:
    """Cheap gate: no extra Pandoc invocation for the default mode, including a document-level count override."""
    value = core.first_pdfmd_option(sources[0], metadata, "column-estimate")
    if value is not None and str(value).strip().casefold() not in ("count", "measure"):
        raise SystemExit(f"pdfmd-options column-estimate: {value!r} is not one of count, measure")
    if str(value).strip().casefold() == "measure":
        return True
    pattern = re.compile(r'\bcolumn-estimate\s*=\s*["\']?\s*measure\b', re.IGNORECASE)
    return any(pattern.search(core.read_text_best_effort(source)) for source in sources)


def dump_command(command: list[str], output: Path, filter_path: Path, writer: str = "latex") -> list[str]:
    """Keep the build's arguments, except the writer, output and engine; the width filter dumps in its original place."""
    result = []
    i = 0
    pairs = ("-o", "--output", "-t", "--to", "--write", "--pdf-engine", "--pdf-engine-opt")
    while i < len(command):
        item = command[i]
        if item in pairs:
            i += 2
            continue
        if item.startswith(tuple(key + "=" for key in pairs if key.startswith("--"))):
            i += 1
            continue
        result.append(item)
        i += 1
    if str(filter_path) not in result and "--lua-filter=" + str(filter_path) not in result:
        result += ["--lua-filter", str(filter_path)]
    return [*result, "-t", writer, "-s", "-o", str(output), "-M", "pdfmd-measure-role=dump"]


def engine_options(command: list[str]) -> list[str]:
    result = []
    for index, item in enumerate(command):
        if item == "--pdf-engine-opt" and index + 1 < len(command):
            result.append(command[index + 1])
        elif item.startswith("--pdf-engine-opt="):
            result.append(item.split("=", 1)[1])
    return result


def parse_latex(text: str) -> dict:
    """TeX's write stream uses decimal points, independent of the document's language."""
    tables = {}
    for line in text.splitlines():
        fields = line.split()
        if fields and fields[0] == "T" and len(fields) == 4:
            _, table, line_width, sep = fields
            tables[table] = {"line": float(line_width), "sep": float(sep), "cells": []}
            continue
        if len(fields) != 5:
            raise ValueError("invalid measurement record")
        kind, table, row, col, value = fields
        width = float(value)
        if not math.isfinite(width) or width < 0:
            raise ValueError("invalid measured width")
        if kind in ("C", "W"):
            cells = tables[table]["cells"]
            r, c = int(row), int(col)
            if r < 1 or c < 1:
                raise ValueError("invalid measured cell position")
            while len(cells) < r:
                cells.append([])
            while len(cells[r - 1]) < c:
                cells[r - 1].append({"width": 0, "word": 0})
            key = "width" if kind == "C" else "word"
            cells[r - 1][c - 1][key] = max(cells[r - 1][c - 1][key], width)
        else:
            raise ValueError("unknown measurement record")
    data = {"tables": tables}
    validate(data)
    return data


def parse_typst(text: str) -> dict:
    """The labelled metadata produced by Typst's contextual measure calls, in typographic points."""
    tables = {}
    for record in json.loads(text):
        table = str(record["table"])
        if record["kind"] == "T":
            tables[table] = {key: record[key] for key in ("line", "sep", "inset", "gutter")}
            tables[table]["cells"] = []
        else:
            cells = tables[table]["cells"]
            r, c = record["row"], record["col"]
            if not isinstance(r, int) or not isinstance(c, int) or r < 1 or c < 1:
                raise ValueError("invalid measured cell position")
            while len(cells) < r:
                cells.append([])
            while len(cells[r - 1]) < c:
                cells[r - 1].append({"width": 0, "word": 0})
            key = {"C": "width", "W": "word"}[record["kind"]]
            width = record["width"]
            if not math.isfinite(width) or width < 0:
                raise ValueError("invalid measured cell width")
            cells[r - 1][c - 1][key] = max(cells[r - 1][c - 1][key], width)
    data = {"tables": tables}
    validate(data)
    return data


def validate(data: dict) -> None:
    if not data["tables"]:
        raise ValueError("no table measurements")
    for table in data["tables"].values():
        if not math.isfinite(table["line"]) or table["line"] <= 0 or not math.isfinite(table["sep"]) or table["sep"] < 0:
            raise ValueError("invalid measured line width")
        if not table["cells"] or any(not row for row in table["cells"]):
            raise ValueError("missing measured cells")
        for key in ("inset", "gutter"):
            if key in table and not math.isfinite(table[key]):
                raise ValueError("invalid measured column separation")
        if table["line"] <= table["sep"] * max(map(len, table["cells"])):
            raise ValueError("column separation leaves no text width")
        for row in table["cells"]:
            for cell in row:
                if any(not math.isfinite(cell[key]) or cell[key] < 0 for key in ("width", "word")):
                    raise ValueError("invalid measured cell width")


def run(command: list[str], cwd: Path, env: dict, verbose: bool) -> subprocess.CompletedProcess:
    core.log_cmd(command, cwd, verbose)
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


def check(result: subprocess.CompletedProcess, stage: str) -> None:
    if result.returncode:
        # Keep a useful cause without dumping a full TeX log on an otherwise successful build. TeX writes its "!" error
        # to standard output, while MiKTeX puts notices such as "So far, no MiKTeX administrator has checked for
        # updates" on standard error: look at both for the error first.
        lines = [line for text in (result.stdout or "", result.stderr or "") for line in text.strip().splitlines()]
        last = (result.stderr or result.stdout or "").strip().splitlines() or ["no diagnostic"]
        cause = next((line for line in lines if line.startswith("!")), None)
        cause = cause or next((line for line in lines if line.startswith("error:")), last[-1])
        raise ValueError(f"{stage}: {cause}")


def prepare(command: list[str], engine: str, sources: list[Path], metadata: list[Path], cwd: Path,
            verbose: bool = False, *, enabled: bool = True, export: bool = False, state: dict | None = None) -> list[str]:
    """Return the final Pandoc command with a measurement file, or unchanged after one cause-naming fallback."""
    state = state if state is not None else {}
    if state.get("failed") or not enabled or not requested(sources, metadata):
        return command
    if export or engine not in (*LATEX, "typst"):
        if not state.get("noted"):
            print(f"NOTE  column-estimate: measure is unavailable for {engine}{' exports' if export else ''}; using count", file=sys.stderr)
            state["noted"] = True
        return command
    try:
        import pdfmd_lua
        filter_path = pdfmd_lua.path("table_width")
        if filter_path is None:
            raise ValueError("table-width filter is unavailable")
        executable = core.which(engine)
        if not executable:
            raise ValueError(f"{engine} is unavailable")
        options = engine_options(command)
        if engine == "tectonic":
            # Unlike the other TeX engines, Tectonic does not read TEXINPUTS and searches beside its source.
            folders = [cwd, *(source.parent for source in sources), *core.tectonic_search_folders(sources[0])]
            options += ["-Zsearch-path=" + str(folder) for folder in dict.fromkeys(folders)]
        env = core.tex_search_env(sources[0].parent, cwd, sources[0])
        with tempfile.TemporaryDirectory(prefix="pdfmd-column-measure-") as folder:
            scratch = Path(folder)
            writer = "typst" if engine == "typst" else "latex"
            source = scratch / ("measure.typ" if engine == "typst" else "measure.tex")
            assets = core.cache_root() / "column-measure" / "assets"
            assets.mkdir(parents=True, exist_ok=True)
            dump = core.headers_as_metadata(dump_command(command, source, filter_path, writer))
            dump += ["-M", "pdfmd-measure-assets=" + str(assets)]
            check(run(dump, cwd, env, verbose), "measurement Pandoc")
            text = source.read_text(encoding="utf-8")
            if ("<pdfmd-measure>" if engine == "typst" else "\\pdfmdmeasure{") not in text:
                return command                      # there were no tables requesting measurement
            identity = str(Path(executable).resolve()) + str(Path(executable).stat().st_mtime_ns)
            digest = hashlib.sha256((text + identity + repr(options)).encode("utf-8")).hexdigest()
            cache = core.cache_root() / "column-measure" / (digest + ".json")
            data = None
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                validate(data)
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                data = None
            cached = data is not None
            if data is None:
                if engine == "typst":
                    root = [] if any(item == "--root" or item.startswith("--root=") for item in options) else ["--root", str(Path.cwd().anchor)]
                    compile_command = [executable, "query", *options, *root, str(source), "<pdfmd-measure>", "--field", "value"]
                elif engine == "tectonic":
                    compile_command = [executable, *options, "--outfmt=xdv", "--keep-logs", "--keep-intermediates", "--outdir", str(scratch), str(source)]
                else:
                    # By a relative name in the scratch folder, as Pandoc runs its engine: a path on the command line is
                    # read by TeX, where `~` (Windows' short folder names, C:\Users\RUNNER~1\...) is an active character.
                    # The document's own folders stay reachable through TEXINPUTS (a trailing separator keeps the rest).
                    compile_command = [executable, *options, "-interaction=nonstopmode", "-halt-on-error", source.name]
                    tex_env = dict(env if env is not None else os.environ)
                    folders = dict.fromkeys([str(cwd), *(str(item.parent) for item in sources)])
                    tex_env["TEXINPUTS"] = os.pathsep.join(folders) + os.pathsep + tex_env.get("TEXINPUTS", "")
                if engine in ("typst", "tectonic"):
                    result = run(compile_command, cwd, env, verbose)
                else:
                    result = run(compile_command, scratch, tex_env, verbose)
                check(result, f"measurement {engine}")
                data = (parse_typst(result.stdout) if engine == "typst" else
                        parse_latex((scratch / "measure.pdfmdwidths").read_text(encoding="utf-8")))
                cache.parent.mkdir(parents=True, exist_ok=True)
                # A failed/parallel write can never leave a partial cache entry.
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache.parent, delete=False) as handle:
                    temporary = Path(handle.name)
                    json.dump(data, handle)
                try:
                    os.replace(temporary, cache)
                finally:
                    temporary.unlink(missing_ok=True)
            core.vprint(verbose, f"MEASURE  {engine}: {'cached' if cached else 'measured'} widths for "
                        f"{len(data['tables'])} table(s)", file=sys.stderr)
            for number, table in data["tables"].items():
                core.vprint(verbose, f"      table {number}: line {table['line']:.2f} pt, "
                            f"padding/gaps {table['sep']:.2f} pt per column", file=sys.stderr)
            return [*command, "-M", "pdfmd-column-measurements=" + str(cache)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        state["failed"] = True
        print(f"WARN  column-estimate: measurement failed ({exc}); using count", file=sys.stderr)
        return command
