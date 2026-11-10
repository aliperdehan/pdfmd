"""What an engine's failure does to the rest of the PDF engine chain: `engine-fallback` (v3.33.71).

pdfmd tries the engines of its chain in turn, and before this setting every failure, whatever its cause, went on to the next
one; the degraded file (a Typst PDF after a LaTeX error in the document) replaced the good PDF already there, with exit 0. The
modes (`--engine-fallback MODE`, `pdfmd-options: {engine-fallback: MODE}`, a `--setup` row):

- `on`: any failure tries the next engine, as before.
- `missing`: only an engine that cannot run here (not installed, too old, crashed without a word about the document, a
  broken installation, a folder it may not write) falls through, with a NOTE; an engine that ran and reported an error in the
  document (TeX: a `!` error line, a missing `.sty` or `.cls`; Typst: an `error:` with its place in the source) stops the build.
- `off`: the first engine that fails stops the build.
- `auto` (the default): when the output does not exist yet, `on`. When it does, the engine that made it is looked up (pdfmd's
  own build record of the document, a build that did not fall back; else the PDF's Producer/Creator), the chain starts with
  the first engine of that engine's family, and the build behaves as `missing`. Nothing found: `on`. A pinned engine (`-e`,
  `pdf-engine:`, the config's default) is never reordered; with one, `auto` is `missing` when the output exists.

A failed engine run leaves the output as it was (Pandoc writes the PDF only when the engine succeeded), so a stop keeps the
previous file byte for byte. `core` is the `pdfmd` module, bound when `pdfmd.py` loads; the pdfmd names read here
(`BUILD`, `ENGINE_CLI`, `ENGINE_FALLBACK_CLI`, `ENGINE_FAMILY`, `BROWSER_ENGINES`, `LATEX_ENGINES`, `config_options`,
`display_path`, `first_pdfmd_option`, `frontmatter_engine`, `load_package`, `pypdf`, `report_engine_failure`, `vprint`) are
read as `core.X` when it runs.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

core = None

MODES = ("auto", "on", "missing", "off")
# YAML reads a bare on/off/yes/no as a boolean
MODE_WORDS = {"auto": "auto", "on": "on", "true": "on", "yes": "on", "missing": "missing", "off": "off", "false": "off", "no": "off"}

# Pandoc's exit code when it cannot run the PDF program it was told to use (PandocPDFProgramNotFoundError): a fact of Pandoc's.
PANDOC_PROGRAM_NOT_FOUND = 47
# What a TeX run prints when the installation, not the document, is broken or may not write (log signatures, facts of TeX's;
# the ones pdfmd_tex.TEX_CAUSES knows count too, a missing package aside, which is the document's).
TEX_UNUSABLE = ("I can't find the format file", "Fatal format file error", "I can't write on file", "Not writing to",
                "kpathsea: Running mktexfmt", "not loadable: Bad metric (TFM) file")
# An error as TeX's -file-line-error writes it in its log (`./report.tex:12: Undefined control sequence.`), which pdfmd's direct
# .tex route asks for. TeX can wrap the filename even inside its extension.
TEX_FILE_LINE_ERROR = re.compile(
    r"(?m)^[^\r\n]+\.\n?(?:t\n?e\n?x|s\n?t\n?y|c\n?l\n?s|l\n?t\n?x|d\n?e\n?f|c\n?f\n?g|b\n?b\n?l)[\"\']?\n?:\d+: .*$")
# A Typst diagnostic: `error: ...`, then the place in the source on a line of its own (Typst's own layout)
TYPST_SOURCE_ERROR = re.compile(r"(?m)^error: .*\n(?:.*\n)?\s*┌─ ")
# A PDF's Creator and Producer, as each engine writes them -> the engine (first match wins; facts of the engines). pdfmd adds
# " via pdfmd-cli" to the Creator, which matches none of them.
PRODUCERS = (
    (re.compile(r"^Typst\b", re.M), "typst"),
    (re.compile(r"ConTeXt"), "context"),
    (re.compile(r"LuaTeX|LuaHBTeX"), "lualatex"),
    (re.compile(r"xdvipdfmx|XeTeX"), "xelatex"),
    (re.compile(r"pdfTeX"), "pdflatex"),
    (re.compile(r"WeasyPrint"), "weasyprint"),
    (re.compile(r"Prince\b"), "prince"),
    (re.compile(r"wkhtmltopdf"), "wkhtmltopdf"),
    (re.compile(r"\bEdg/"), "edge"),
    (re.compile(r"Skia/PDF|HeadlessChrome"), "chrome"),
    (re.compile(r"LibreOffice|OpenOffice"), "soffice"),
    (re.compile(r"calibre", re.I), "calibre"),
    (re.compile(r"gropdf|groff"), "groff"),
)
# the closing label a build record keeps on its `result:` row: `(typst)` or `(typst; lualatex, xelatex failed)`
RESULT_LABEL = re.compile(r"\((?P<engine>[A-Za-z0-9_.-]+)(?:; (?P<failed>[^()]*) failed)?\)\s*$")


@dataclass
class Plan:
    """The chain's policy for one build: the mode in force (on, missing, off), the mode as set and where, the output."""
    mode: str
    asked: str
    where: str
    output: Path
    stopped: str = ""          # the closing line's words when the chain stopped


def family(engine: str) -> str:
    """The engine's family for mirroring: the TeX engine (pdfmd's ENGINE_FAMILY), the browsers as one, groff's two routes."""
    if engine in core.BROWSER_ENGINES:
        return "browser"
    if engine in ("groff", "pdfroff"):
        return "groff"
    return core.ENGINE_FAMILY.get(engine, engine)


def mode_word(value) -> str | None:
    if isinstance(value, bool):
        return "on" if value else "off"
    return MODE_WORDS.get(str(value).strip().casefold()) if value is not None else None


def resolve_mode(md_path: Path, metadata_files: list[Path]) -> tuple[str, str]:
    """(mode, where it was set): --engine-fallback, else `pdfmd-options.engine-fallback` (the document, its metadata files, the
    config), else auto. A word that is no mode is one WARN, and auto."""
    if core.ENGINE_FALLBACK_CLI:
        return core.ENGINE_FALLBACK_CLI, "--engine-fallback"
    try:
        if md_path.suffix.lower() in (".md", ".markdown"):
            value = core.first_pdfmd_option(md_path, metadata_files, "engine-fallback")
        else:
            value = core.config_options().get("engine-fallback")
    except Exception:          # noqa: BLE001 -- a document that cannot be read fails elsewhere, with its own message
        value = None
    if value is None:
        return "auto", "default"
    word = mode_word(value)
    if word is None:
        print(f"WARN  {core.display_path(md_path)}: pdfmd-options.engine-fallback {value!r} is not one of "
              f"{', '.join(MODES)}; using auto", file=sys.stderr)
        return "auto", "default"
    return word, "pdfmd-options"


def pinned(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether the chain is pinned: -e with a value (a bare -e asks for the whole chain and overrides the rest), else a
    `pdf-engine:` of the document, its metadata files or the config (as resolve_engines decides)."""
    cli = core.ENGINE_CLI
    if cli is not None:
        return bool(cli)
    try:
        return bool(core.frontmatter_engine(md_path, metadata_files))
    except Exception:          # noqa: BLE001
        return False


def _header_rows(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    break
                name, _, value = line.partition(":")
                if value and name and " " not in name.strip():
                    rows.setdefault(name.strip(), value.strip())
    except OSError:
        pass
    return rows


def _same_file(written: str, output: Path) -> bool:
    if not written:
        return False
    if written == "~" or written.startswith(("~/", "~\\")):        # a record writes the home folder as ~ (scrub_home)
        written = str(Path.home()) + written[1:]
    try:
        return Path(written).resolve() == output.resolve()
    except OSError:
        return False


def from_records(md_path: Path, output: Path) -> tuple[str | None, str]:
    """(engine, how it is known) from the newest good build record of ``md_path`` that wrote ``output`` and did not fall back;
    (None, why) when there is none. When every record of this output fell back, nothing is mirrored (the PDF is a degraded one,
    and mirroring it would lock the degraded engine in)."""
    try:
        from pdfmd_buildinfo import record
        folders = core.load_package("pdfmd_buildinfo.build").build_record_folders(md_path)
    except Exception:          # noqa: BLE001
        return None, ""
    found = []
    for folder in folders:
        for path in record.records(folder):
            match = record.NAME.match(path.name)
            if match and match.group(3) == "ok":
                found.append(((match.group(1), int(match.group(2) or 1)), path))
    degraded = ""
    for _, path in sorted(found, key=lambda item: item[0], reverse=True):
        rows = _header_rows(path)
        if not _same_file(rows.get("output", ""), output):
            continue
        label = RESULT_LABEL.search(rows.get("result", ""))
        if label is None:
            continue
        if label.group("failed"):
            degraded = degraded or f"{label.group('engine')} after {label.group('failed')} failed"
            continue
        when = rows.get("when", "")[:16]
        return label.group("engine"), f"build record {when}".strip()
    if degraded:
        return None, f"its last build fell back ({degraded}), which is not mirrored"
    return None, ""


def from_metadata(output: Path) -> str | None:
    """The engine a PDF's Creator and Producer name (PRODUCERS), else None."""
    try:
        info = core.pypdf.PdfReader(str(output)).metadata or {}
        text = f"{info.get('/Creator') or ''}\n{info.get('/Producer') or ''}"
    except Exception:          # noqa: BLE001 -- no pypdf, a damaged PDF: nothing known
        return None
    for pattern, engine in PRODUCERS:
        if pattern.search(text):
            return engine
    return None


def previous_engine(md_path: Path, output: Path) -> tuple[str | None, str]:
    """(engine, how it is known) that made ``output``: the build record first, else the PDF's metadata."""
    engine, how = from_records(md_path, output)
    if engine or how:
        return engine, how
    engine = from_metadata(output)
    return (engine, "the PDF's Producer/Creator") if engine else (None, "")


def mirrored(engines: list[str], previous: str) -> list[str] | None:
    """The chain started with ``previous``'s engine, or the first one of its family; the others after it in their order."""
    start = previous if previous in engines else next((engine for engine in engines if family(engine) == family(previous)), None)
    if start is None:
        return None
    return [start, *(engine for engine in engines if engine != start)]


def plan_build(md_path: Path, metadata_files: list[Path], engines: list[str], output: Path, verbose: bool) -> list[str]:
    """The chain this build runs (``engines``, perhaps started with the engine that made the output) and its Plan, kept in
    core.BUILD["chain"] for the engine loops."""
    asked, where = resolve_mode(md_path, metadata_files)
    name = output.name
    exists = output.is_file()
    mode, why = asked, {"on": "any failure tries the next engine", "missing": "only an engine that cannot run here falls through",
                        "off": "the first failure stops the build"}.get(asked, "")
    if asked == "auto":
        if not exists:
            mode, why = "on", f"{name} does not exist yet, so the whole chain may be tried"
        elif pinned(md_path, metadata_files):
            mode, why = "missing", f"{name} exists and the engine is pinned; an error in the document keeps it"
        else:
            engine, how = previous_engine(md_path, output)
            if engine is None:
                mode, why = "on", (f"{name} exists, but {how}" if how else
                                   f"{name} exists, but no record or metadata says which engine made it") + "; the whole chain"
            else:
                order = mirrored(engines, engine)
                mode = "missing"
                if order is None:
                    print(f"NOTE  {core.display_path(md_path)}: engine-fallback auto: {name} was made by {engine} ({how}), which "
                          f"cannot run here (not installed); starting with {engines[0] if engines else 'nothing'}",
                          file=sys.stderr)
                    why = f"{name} was made by {engine} ({how}), which is not installed; the usual chain"
                else:
                    engines = order
                    why = f"{name} was made by {engine} ({how}); starting with {order[0]}"
    core.vprint(verbose, f"ENGINE  engine-fallback {asked}{'' if where == 'default' else f' ({where})'}: {why}")
    core.BUILD["chain"] = Plan(mode, asked, where, output)
    return engines


def failure_kind(engine: str, result) -> tuple[str, str]:
    """("document", why) for an engine that ran and reported an error in the document, else ("engine", why): the engine
    cannot run here. Only what is recognised counts as the document's."""
    text = (result.stderr or "") + ("\n" + result.stdout if getattr(result, "stdout", "") else "")
    if result.returncode == PANDOC_PROGRAM_NOT_FOUND:
        return "engine", "Pandoc could not run it"
    if engine in core.LATEX_ENGINES:
        if any(signature in text for signature in TEX_UNUSABLE):
            return "engine", "the TeX installation cannot run it"
        try:
            from pdfmd_tex import TEX_CAUSES
        except ImportError:
            TEX_CAUSES = ()
        for pattern, cause, fix in TEX_CAUSES:
            if fix is not None and re.search(pattern, text):          # fix None: a missing package, the document's
                return "engine", cause
        line = re.search(r"(?m)^! .*$", text) or TEX_FILE_LINE_ERROR.search(text)
        if line:
            return "document", line.group(0).strip()
        return "engine", "it stopped without a LaTeX error"
    if engine == "typst":
        found = TYPST_SOURCE_ERROR.search(text)
        if found:
            return "document", found.group(0).splitlines()[0].strip()
        return "engine", "it stopped without an error in the source"
    return "engine", "it reported no error in the document that pdfmd recognises"


def engine_failed(label: str, engine: str, result, remaining: list[str], debug: bool) -> bool:
    """Report one engine's failure (core.report_engine_failure) and say whether the chain stops here (True) under the build's
    engine-fallback; a fall-through for an engine that cannot run here gets a NOTE in `missing` mode."""
    plan = core.BUILD.get("chain")
    if plan is None or plan.mode == "on":
        core.report_engine_failure(label, engine, result, remaining, debug)
        return False
    kind, why = failure_kind(engine, result)
    if plan.mode == "missing" and kind == "engine":
        core.report_engine_failure(label, engine, result, remaining, debug)
        if remaining:
            print(f"NOTE  {label}: engine-fallback {plan.asked}: {engine} counts as unusable here ({why}), not as an error in "
                  f"the document, so {remaining[0]} is tried", file=sys.stderr)
        return False
    kept = (f"the existing {plan.output.name} is left as it was" if plan.output.is_file() else "nothing is written")
    cause = "an error in the document" if kind == "document" else "no other engine is tried"
    core.report_engine_failure(label, engine, result, [], debug,
                               stopped=f"engine-fallback {plan.asked}: {cause}, so the build stops here and {kept}")
    plan.stopped = (f"{engine} failed; engine-fallback {plan.asked} stopped the build, "
                    + (f"{plan.output.name} kept" if plan.output.is_file() else "nothing written")
                    + "; --engine-fallback on tries the next engine")
    return True


def stopped() -> str:
    """The closing line's words when this build's chain stopped, else ''."""
    plan = core.BUILD.get("chain")
    return plan.stopped if plan is not None else ""
