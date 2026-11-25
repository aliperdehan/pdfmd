"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_stamp`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

from pdfmd_base import core
from pdfmd_base import timed
from pdfmd_log import emit


STAMP_MODES = frozenset({"replace", "history"})


STAMP_SCOPES = frozenset({"always", "report", "standalone"})


STAMP_STORES = frozenset({"notes", "file", "both"})


DEFAULT_STAMP_OPTIONS = {
    "enabled": False,
    "mode": "replace",
    # Where a compile is written: the document's BUILD NOTES block (notes, the default), a NAME.hst file beside the
    # backups that leaves the document alone (file), or both.
    "store": "notes",
    # `pdfmd --history-restore` leaves a "Restored ..." entry in the history; false for a document that must not.
    "restored_note": True,
    # A build of some parts or sections only (`pdfmd @60`) is not the report, so it writes no BUILD NOTES line; with this on
    # it leaves a "partial" entry in the NAME.hst (store: file or both) naming the parts it built and those that changed.
    "partial": False,
    "packages": [],
    "scope": "always",
    "include_output": False,
    # On by default, unlike 'enabled' -- embedding two custom, invisible PDF
    # Info-dictionary keys (see pdf_metadata_snippet) has no visible effect
    # on the rendered page or a normal "Document Properties" panel, and
    # never overwrites a document's real metadata, so there's little to
    # protect a caller from the way 'enabled' (which edits the visible .md
    # source) protects them by staying off until asked. Independent of
    # 'enabled': PDF metadata still needs a LaTeX-family engine and a scope
    # match (see stamp_scope_matches), but happens on every such compile
    # unless --no-stamp-pdf-metadata/pdf_metadata:false turns it off, with
    # or without --stamp/enabled ever being turned on for the .md stamp.
    "pdf_metadata": True,
}


def stamp_fields(value, implied_on: bool = True) -> dict:
    """The fields a pdfmd-options.stamp value sets (no defaults filled in).

    Accepts the same range of shapes --no-auto's own settings do: a bare
    bool (on/off, everything else default), a single package name or list
    of names (shorthand for enabling stamping with just those packages), or
    a full dict of {enabled, mode, packages, scope, include_output,
    pdf_metadata}. A dict with no explicit ``enabled`` key is treated as on
    -- bothering to
    configure packages/mode/scope implies wanting it active; write
    ``enabled: false`` explicitly to keep a shared default off until a
    document (or --stamp on the command line) turns it on. Not in the config
    file (``implied_on`` False, v3.27.1): there `pdfmd --setup` writes each
    detail as its own row, and only the "enabled" row switches stamping on.
    """
    options: dict = {}
    if isinstance(value, bool):
        options["enabled"] = value
    elif isinstance(value, str):
        options["enabled"] = True
        options["packages"] = [value]
    elif isinstance(value, list):
        options["enabled"] = True
        options["packages"] = [str(item) for item in value]
    elif isinstance(value, dict):
        if "enabled" in value or implied_on:
            options["enabled"] = bool(value.get("enabled", True))
        if "mode" in value:
            options["mode"] = str(value["mode"])
        if "store" in value:
            options["store"] = str(value["store"])
        restored_note = value.get("restored_note", value.get("restored-note"))
        if restored_note is not None:
            options["restored_note"] = bool(restored_note)
        if value.get("partial") is not None:
            options["partial"] = bool(value["partial"])
        if "packages" in value:
            packages = value["packages"]
            options["packages"] = ([str(item) for item in packages] if isinstance(packages, list)
                                   else [str(packages)])
        if "scope" in value:
            options["scope"] = str(value["scope"])
        include_output = value.get("include_output", value.get("include-output"))
        if include_output is not None:
            options["include_output"] = bool(include_output)
        pdf_metadata = value.get("pdf_metadata", value.get("pdf-metadata"))
        if pdf_metadata is not None:
            options["pdf_metadata"] = bool(pdf_metadata)
    return options


def frontmatter_stamp(md_path: Path, metadata_files: list[Path] = ()) -> dict | None:
    """Cascade a document's own pdfmd-options.stamp, then each linked
    metadata file's (the later first) -- same precedence as frontmatter_engine
    (see its docstring): a shared metadata.yaml can turn stamping on for
    every report that finds it, and any one document can still override it
    with its own pdfmd-options.stamp. Returns None (not
    DEFAULT_STAMP_OPTIONS) when nothing sets it at all, so
    resolve_stamp_options can tell "nowhere set" apart from "set to off".
    """
    # v3.27.1: field by field, the first place to set a field winning (a document's `stamp: true` keeps a shared
    # metadata.yaml's `store: file`); it used to be the whole value of the first place.
    merged: dict = {}
    found = False
    for where, options in core.option_sources(md_path, metadata_files):
        for name in ("stamp", "history"):       # `history` is the same setting under the name people look for (3.30.24)
            if name in options:
                found = True
                for key, value in stamp_fields(options[name], implied_on=not core.is_setup_layer(where)).items():
                    merged.setdefault(key, value)
    return {**DEFAULT_STAMP_OPTIONS, **merged} if found else None


def resolve_stamp_options(md_path: Path, metadata_files: list[Path], cli_overrides: dict) -> dict:
    """Effective --stamp settings: document/metadata front matter first (see
    frontmatter_stamp), then CLI flags win field-by-field on top of that --
    same "explicit CLI always wins" convention as -e/--engine and -y. Raises
    SystemExit for an unrecognized mode/scope, matching
    effective_no_auto's unknown-KIND check.
    """
    options = frontmatter_stamp(md_path, metadata_files) or dict(DEFAULT_STAMP_OPTIONS)
    options.update(cli_overrides)
    if options["mode"] not in STAMP_MODES:
        raise SystemExit(f"{md_path}: unknown --stamp mode '{options['mode']}'. "
                         f"Valid: {', '.join(sorted(STAMP_MODES))}")
    if options["store"] not in STAMP_STORES:
        raise SystemExit(f"{md_path}: unknown --stamp-store '{options['store']}'. "
                         f"Valid: {', '.join(sorted(STAMP_STORES))}")
    if options["scope"] not in STAMP_SCOPES:
        raise SystemExit(f"{md_path}: unknown --stamp scope '{options['scope']}'. "
                         f"Valid: {', '.join(sorted(STAMP_SCOPES))}")
    return options


def package_version(name: str) -> str | None:
    """Locate name.sty via kpsewhich and pull the version out of its own
    \\ProvidesPackage{name}[...] line -- the convention this project's own
    packages (nulabreport.sty included) already follow: a date followed by
    free text that itself starts with a bare vX.Y.Z. Returns None silently
    (a --stamp package is best-effort, never a hard requirement) if
    kpsewhich isn't installed, the package isn't found, or its
    ProvidesPackage line has no bare v-prefixed token to extract.
    """
    kpsewhich = core.which("kpsewhich")
    if not kpsewhich:
        return None
    result = core.run_probe([kpsewhich, f"{name}.sty"])
    if result is None:
        return None
    sty_path = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if result.returncode != 0 or not sty_path:
        return None
    try:
        text = Path(sty_path).read_text(encoding="utf-8-sig")
    except OSError:
        return None
    provides = re.search(rf"\\ProvidesPackage\{{{re.escape(name)}\}}\[([^\]]*)\]", text)
    if not provides:
        return None
    version = re.search(r"\bv\d+(?:\.\d+)*[a-zA-Z]*\b", provides.group(1))
    return version.group(0) if version else None


def package_is_used(name: str, texts: list[str]) -> bool:
    """Return whether \\usepackage/\\RequirePackage{...name...} appears in
    any of the given raw LaTeX texts (a document's preambles and its own
    header-includes) -- so a --stamp-packages entry the document doesn't
    actually load is silently left out of the stamp line, rather than
    reporting a version for a package that played no part in this compile.
    """
    pattern = re.compile(rf"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{{[^}}]*\b{re.escape(name)}\b[^}}]*\}}")
    return any(pattern.search(text) for text in texts)


def stamp_summary(options: dict, texts: list[str], verbose: bool) -> str:
    """Build the 'nulabreport v1.14.7, pdfmd v2.4.0' portion of a stamp
    line: one 'name vVERSION' per options['packages'] entry that's both
    actually loaded (package_is_used) and has a detectable version
    (package_version), in the order given, followed by pdfmd's own version.
    """
    parts = []
    for name in options["packages"]:
        if not package_is_used(name, texts):
            continue
        version = package_version(name)
        if version:
            parts.append(f"{name} {version}")
        else:
            emit("warning", None, f"WARN  --stamp: {name} is loaded but its version could not be "
                   "determined (kpsewhich missing, package not installed, or no "
                   "\\ProvidesPackage line)", file=sys.stderr, shown=verbose)
    parts.append(f"pdfmd v{core.PDFMD_VERSION}")
    return ", ".join(parts)


def build_stamp_line(options: dict, texts: list[str], output: Path,
                     report_output: Path | None = None, verbose: bool = False) -> str:
    """Compose one stamp line: 'Compiled [as part of `X`/to `X`] with
    PACKAGES, pdfmd vVERSION -- TIMESTAMP'. report_output (this document
    compiled as one chapter of a report/book) always names the shared
    output, since "as part of" is meaningless without it; options
    ['include_output'] opts into naming it for an otherwise plain
    single-file/batch compile too.
    """
    summary = core.stamp_summary(options, texts, verbose)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if report_output is not None:
        return f"Compiled as part of `{report_output.name}` with {summary} -- {timestamp}"
    if options["include_output"]:
        return f"Compiled to `{output.name}` with {summary} -- {timestamp}"
    if output.suffix and output.suffix.lower() not in (".pdf", ".tex"):
        # a build to another format says so: "Compiled to docx with ..."
        return f"Compiled to {output.suffix.lower().lstrip('.')} with {summary} -- {timestamp}"
    return f"Compiled with {summary} -- {timestamp}"


BUILD_NOTES_RE = re.compile(
    r"<!--[ \t]*=+[ \t]*\n"
    r"(?P<indent>[ \t]*)BUILD NOTES[ \t]*\n"
    r"(?P<body>.*?)"
    r"(?P=indent)=+[ \t]*-->",
    re.DOTALL,
)


def stamp_line_pattern(indent: str) -> re.Pattern:
    return re.compile(rf"^{re.escape(indent)}Compiled\b.*?\bpdfmd\s+v[0-9][^\r\n]*$", re.MULTILINE)


def history_heading_pattern(indent: str) -> re.Pattern:
    return re.compile(rf"^{re.escape(indent)}Compile History:[ \t]*\n", re.MULTILINE)


IGNORE_MARK_RE = re.compile(r"(?mi)^[ \t]*pdfmd:[ \t]*(?:ignore|skip|hands[ -]off)[ \t]*$")


def is_pdfmd_notes(body: str, indent: str) -> bool:
    """A BUILD NOTES block pdfmd has written into: it holds its stamp line or its "Compile History:" list."""
    return bool(stamp_line_pattern(indent).search(body) or history_heading_pattern(indent).search(body))


def build_notes_blocks(text: str) -> list[re.Match]:
    """Every BUILD NOTES comment of the document (not the text of an embedded file)."""
    return list(BUILD_NOTES_RE.finditer(core.mask_embedded_blocks(text)))


def pdfmd_build_notes(text: str) -> re.Match | None:
    """The BUILD NOTES block pdfmd writes into, or None when it has to make one. A document may carry several (the
    author's, an AI agent's, a section's own): pdfmd uses the one it has written into before; failing that, the
    only one there is (the convention it automates, kept by hand in real reports); failing that -- several, none
    pdfmd's -- none, so that it starts its own and leaves the others as they are. A block with a line
    `pdfmd: ignore` in it is never touched."""
    blocks = [match for match in build_notes_blocks(text) if not IGNORE_MARK_RE.search(match.group("body"))]
    for match in blocks:
        if is_pdfmd_notes(match.group("body"), match.group("indent")):
            return match
    every = build_notes_blocks(text)
    return blocks[0] if len(every) == 1 and blocks else None


def update_build_notes(text: str, new_line: str, mode: str) -> tuple[str, str | None]:
    """Insert/replace pdfmd's own stamp line inside a document's BUILD NOTES
    comment, wherever that comment sits in the file (found by BUILD_NOTES_RE
    -- not assumed to be the file's last line: a report chapter's own
    comment can end up anywhere once concatenated with others for a book
    build, and even a lone document's notes might not literally be last).
    Everything else inside the comment -- hand-written notes before or
    after the line pdfmd owns -- is left untouched byte-for-byte. Creates a
    fresh comment at the true end of the file if none is found there yet.
    Returns (updated_text, warning) -- warning is a one-line string to
    surface to the caller (never raised/logged here) or None.

    "replace" mode overwrites the current stamp line (the one right under
    "BUILD NOTES") in place; if there is none yet, one is inserted there.
    It never touches a "Compile History:" trailer even if one already
    exists from an earlier history-mode run -- that history is simply
    frozen, not extended, while stamping runs in replace mode, which is
    worth a warning back to the caller since it's easy to not notice.

    "history" mode keeps exactly one live stamp line at the top (right
    under "BUILD NOTES", so the most recent compile is always the first
    thing read) and demotes whatever was previously there into a
    "Compile History:" list of "  - " bullets at the END of the comment,
    just before its closing "===...-->" -- newest-demoted-first, so the
    whole comment reads newest-to-oldest top to bottom. The heading is
    created there the first time a demotion has nowhere to go.
    """
    match = pdfmd_build_notes(text)
    if not match:
        indent = "     "
        block = f"<!-- {'=' * 60}\n{indent}BUILD NOTES\n\n{indent}{new_line}\n{indent}{'=' * 60} -->\n"
        embedded = core.EMBED_BLOCK_RE.search(text)
        if embedded:
            # Embedded filters stay the last thing in the file.
            return (text[:embedded.start()].rstrip("\n") + "\n\n" + block + "\n"
                    + text[embedded.start():]), None
        return text.rstrip("\n") + "\n\n" + block, None

    indent = match.group("indent")
    body = match.group("body")
    stamp_re = stamp_line_pattern(indent)
    current = stamp_re.search(body)
    warning = None

    if mode == "replace":
        history_match = history_heading_pattern(indent).search(body)
        if history_match:
            bullet_count = len(re.findall(rf"^{re.escape(indent)}  - Compiled\b", body, re.MULTILINE))
            warning = (f"--stamp: 'Compile History' already holds {bullet_count} "
                      "entr" + ("y" if bullet_count == 1 else "ies") + " but --stamp-mode is "
                      "'replace' this run -- history stays frozen (not extended) while in "
                      "replace mode; switch back to --stamp-mode history to keep recording it")
        if current:
            new_body = body[:current.start()] + f"{indent}{new_line}" + body[current.end():]
        else:
            new_body = f"{indent}\n{indent}{new_line}\n\n{body}"
        return text[:match.start("body")] + new_body + text[match.end("body"):], warning

    # history mode
    if not current:
        new_body = f"{indent}\n{indent}{new_line}\n\n{body}"
        return text[:match.start("body")] + new_body + text[match.end("body"):], None

    new_body = core.load_package("pdfmd_history.stamping").demote(body, current, indent, new_line)
    return text[:match.start("body")] + new_body + text[match.end("body"):], None


def apply_stamp(md_path: Path, new_line: str, mode: str, verbose: bool) -> None:
    text = md_path.read_text(encoding="utf-8-sig")
    updated, warning = update_build_notes(text, new_line, mode)
    core.atomic_write_text(md_path, updated)
    if warning:
        emit("warning", None, f"WARN  {md_path}: {warning}", file=sys.stderr)
    emit("verbose", "STAMP", f"AUTO STAMP  {md_path}: {new_line}", shown=verbose)


def partial_names(info: dict, md_path: Path, output: Path) -> list[tuple[str, str]]:
    """(name, digest) of what a partial build is made of: each part (its path under the parts folder, no `.md`), or the one
    cut of a plain document, named by what the output's name adds to the document's (`report.only-a-part.pdf`)."""
    names = core.part_digests(info["parts"], info["root"])
    if info["cut"] is not None:
        stem = output.stem
        label = stem[len(md_path.stem) + 1:] if stem.startswith(md_path.stem + ".") else stem
        names.append((re.sub(r"\s+", "_", label), core.sha256_text(core.normalized_source(info["cut"]))[:8]))
    return names


def record_partial_history(md_path: Path, metadata_files: list[Path], preamble_files: list[Path],
                           cli_overrides: dict, output: Path, verbose: bool) -> None:
    """The "partial" entry of a build of some parts or sections (`stamp: {partial: true}`, the history in a NAME.hst)."""
    options = resolve_stamp_options(md_path, metadata_files, cli_overrides)
    if not (options["enabled"] and options["partial"] and options["store"] in ("file", "both")
            and core.stamp_scope_matches(options, None)):
        return
    history = core.history_module()
    info = core.BUILD.get("partial")
    if history is None or info is None:
        return
    names = partial_names(info, md_path, output)
    if not names:
        return
    path = core.history_file(md_path, metadata_files)
    earlier, _ = history.read_file(path)
    known: dict[str, str] = {}          # the digest each part had the last time an entry saw it
    for entry in sorted(earlier, key=lambda item: item.when):
        for word in entry.meta_dict().get("shas", "").split(","):
            name, _, digest = word.rpartition(":")
            if name and digest:
                known[name] = digest
    changed = [name for name, digest in names if name in known and known[name] != digest]
    new = [name for name, _ in names if name not in known]      # no entry has seen it yet: there is nothing to compare with
    texts = core.gather_stamp_texts(md_path, preamble_files)
    tail = core.compile_entry(build_stamp_line(options, texts, output, None, verbose))
    if tail is None:
        return
    shown = ", ".join(name for name, _ in names)
    what = "parts" if len(names) != 1 or info["cut"] is None else "section"
    news = f"; first seen: {', '.join(new)}" if new else ""
    text = (f"{what} {shown}; " + (f"changed: {', '.join(changed)}" if changed else "nothing changed") + news
            + f"; {tail.text}")
    where = history.git.state(md_path)
    meta = (("parts", ",".join(name for name, _ in names)), ("changed", ",".join(changed)), ("new", ",".join(new)),
            ("shas", ",".join(f"{name}:{digest}" for name, digest in names if digest)), ("out", output.name),
            ("git", (where[0] + ("+" if where[1] else "")) if where else ""))
    entry = history.Entry(tail.when, "partial", text, tuple(item for item in meta if item[1]))
    try:
        history.add_entry(path, entry, md_path.name)
    except OSError as error:
        emit("warning", None, f"WARN  {core.display_path(md_path)}: cannot write {core.display_path(path)} ({error.strerror or error})", file=sys.stderr)
        return
    emit("verbose", "HISTORY", f"AUTO HISTORY  {core.display_path(path)}: {entry.when} partial ({shown})", shown=verbose)


@timed(lambda args, kwargs: None if args[1] else "stamp and history")    # `skip`: the cache route's .tex, no step
def stamp_build(partial: bool, skip: bool, md_path: Path, *args, **kwargs) -> None:
    """stamp_after_success for a finished build. A partial parts-mode build isn't the report, so it writes no BUILD NOTES
    stamp into the source (it would claim the report was built) -- but its PDF still says what made it (Creator,
    PdfmdVersions, PdfmdBuildDate, and PdfmdPartial naming the parts). `skip`: an intermediate stage (the cache route's
    .tex), which the final stage stamps."""
    REPORT_BUILD = core.REPORT_BUILD
    if skip:
        return
    if REPORT_BUILD.get("files"):
        # a report built through convert_one(): every chapter is stamped as a chapter of the report, as the report's own loop did
        for chapter in REPORT_BUILD["files"]:
            stamp_after_success(chapter, *args, **kwargs, pdf_only=partial, report_output=args[3])
        return
    stamp_after_success(md_path, *args, **kwargs, pdf_only=partial)
    if partial and core.BUILD.get("partial") is not None and len(args) >= 5:
        # `stamp: {partial: true}`: a "partial" entry in the NAME.hst (the source is not stamped, the history says what was built)
        record_partial_history(md_path, *args[:5])


def stamp_after_success(md_path: Path, metadata_files: list[Path], preamble_files: list[Path],
                        cli_overrides: dict, output: Path, verbose: bool,
                        report_output: Path | None = None, pdf_only: bool = False) -> None:
    """Write/update md_path's BUILD NOTES stamp after a successful compile,
    if --stamp/pdfmd-options.stamp says to for this context.

    report_output being given means md_path is one chapter of a report/book
    compile (main()'s -r/--report path) rather than a standalone/batch
    compile (convert_one) -- options['scope'] decides which context(s)
    actually write a stamp (see DEFAULT_STAMP_OPTIONS/resolve_stamp_options):
    "always" (default), "report"-only, or "standalone"-only.

    pdf_only (a partial build): the PDF's own provenance is written, the source's BUILD NOTES are not.
    """
    options = resolve_stamp_options(md_path, metadata_files, cli_overrides)
    if not core.stamp_scope_matches(options, report_output):
        return
    texts = core.gather_stamp_texts(md_path, preamble_files)
    # Independent of options["enabled"] below on purpose -- pdf_metadata is
    # its own always-on-by-default switch (DEFAULT_STAMP_OPTIONS), separate
    # from the .md-source BUILD NOTES stamp that "enabled" actually gates.
    stamp_pdf_metadata_posthoc(output, options, texts, verbose, partial_parts=partial_parts_label(md_path, output) if pdf_only else "")
    if pdf_only or not options["enabled"]:
        return
    line = build_stamp_line(options, texts, output, report_output, verbose)
    store = options["store"]
    if store in ("file", "both") and not core.record_history(md_path, metadata_files, line, output, verbose):
        store = "notes"                                   # no pdfmd_history here: the document keeps it, as before
    if store in ("notes", "both"):
        apply_stamp(md_path, line, options["mode"], verbose)


# PDF Info-dictionary key names pdfmd writes when pdf_metadata is on. Two
# separate keys, not one combined "Compiled with ... -- TIMESTAMP" line like
# the .md stamp's: LuaTeX/XeTeX apply their usual typographic ligatures
# (-- becomes an en dash) to hypersetup's pdfinfo strings same as any other
# typeset text, so a literal "--" separator doesn't survive intact -- kept
# out entirely here rather than fought with escaping.
PDF_INFO_VERSIONS_KEY = "PdfmdVersions"


PDF_INFO_BUILD_DATE_KEY = "PdfmdBuildDate"


PDF_INFO_PARTIAL_KEY = "PdfmdPartial"


def partial_parts_label(scaffold: Path, output: Path) -> str:
    """The parts a partial build holds, as the output file names them (`report.introduction+procedure.pdf` ->
    `introduction+procedure`); the output's own stem when it does not start with the scaffold's."""
    prefix = scaffold.stem + "."
    return output.stem[len(prefix):] if output.stem.startswith(prefix) and len(output.stem) > len(prefix) else output.stem


def pdf_metadata_snippet(options: dict, texts: list[str], verbose: bool) -> str | None:
    """SUPERSEDED, v3.7.0 (2026-09-21) -- now always returns None.

    Used to return \\AtBeginDocument{...\\hypersetup{pdfinfo={...}}} LaTeX for
    --include-in-header, baking the PdfmdVersions/PdfmdBuildDate keys into
    the PDF Info dictionary from inside the LaTeX compile itself. Replaced
    by stamp_pdf_metadata_posthoc() below, which does the identical thing
    with pypdf AFTER a successful compile instead: confirmed directly (a
    real nulabreport `prelab` document, `\\usepackage[prelab]{nulabreport}`
    loaded via a --metadata-file's own header-includes rather than a
    preamble.tex) that pandoc's own template gives --include-in-header
    content and a metadata file's header-includes THE SAME template slot,
    and --include-in-header simply WINS -- the metadata file's
    header-includes vanished from the preamble entirely the moment this
    function's old --include-in-header snippet was also present, silently
    undoing an entire package load with no error at that point, surfacing
    only later as "Undefined control sequence" the first time the document
    used one of that package's macros. A post-hoc PDF edit sidesteps the
    whole class of --include-in-header/header-includes interaction (this
    one and any similar one not yet found) and, as a real improvement over
    the LaTeX-side version, now also works on every engine, not only
    LATEX_ENGINES (a non-LaTeX target such as weasyprint/typst previously
    had no equivalent mechanism this reached at all -- see this function's
    pre-v3.7.0 docstring history if needed). Left defined (rather than
    deleted) and still called from every site it always was, all of which
    already treat a None return as "no --include-in-header entry needed" --
    the safest way to retire it without touching pdfmd's own multi-engine
    fallback/native-bibliography/report/batch call sites, several of which
    thread pdf_meta_snippet_text through as a plain parameter.
    """
    return None


def stamp_pdf_metadata_posthoc(pdf_path: Path, options: dict, texts: list[str], verbose: bool, partial_parts: str = "") -> None:
    """Write PdfmdVersions/PdfmdBuildDate into pdf_path's own PDF Info
    dictionary after a successful compile -- see pdf_metadata_snippet's
    docstring for why this replaced an in-LaTeX \\hypersetup injection.
    Silently does nothing if options['pdf_metadata'] is off, pdf_path isn't
    a real PDF (e.g. a --to other than pdf), or pypdf isn't installed (a
    soft dependency, same convention as this module's own `yaml` import --
    a WARN either way, since unlike PyYAML's front-matter sugar this is an
    always-on-by-default feature quietly not doing its job). ``partial_parts``: the parts a partial build holds, recorded as
    PdfmdPartial so the PDF says it is not the whole report.
    """
    import logging
    import warnings
    if not options.get("pdf_metadata"):
        return
    if core.pypdf is None:
        emit("warning", None, "WARN  --stamp: pdf_metadata is on but pypdf is not installed "
              "(pip install pypdf) -- skipping the PDF Info-dictionary stamp",
              file=sys.stderr, shown=verbose)
        return
    if pdf_path.suffix.lower() != ".pdf" or not pdf_path.is_file():
        return
    summary = core.stamp_summary(options, texts, verbose)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # pypdf's own "Annotation sizes differ" message fires on essentially
        # every hyperref-linked document (link-annotation bookkeeping quirk
        # of read-then-rewrite) and is not this function's business to
        # surface -- it changes nothing about whether the metadata write
        # below succeeds. pypdf logs this (and similar notices) through the
        # stdlib `logging` module, not `warnings.warn` -- confirmed directly
        # (grepped pypdf's own source) -- so both need silencing.
        pypdf_logger = logging.getLogger("pypdf")
        previous_level = pypdf_logger.level
        pypdf_logger.setLevel(logging.ERROR)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                reader = core.pypdf.PdfReader(pdf_path)
                existing = dict(reader.metadata) if reader.metadata else {}
                # Credit pdfmd in /Creator, appended in pandoc's own
                # "<tool> via <wrapper>" order ("LaTeX via pandoc" -> "LaTeX
                # via pandoc via pdfmd-cli"; "Typst 0.15.1" -> "Typst 0.15.1
                # via pdfmd-cli"). Named by its PyPI distribution name so it
                # is searchable; the version is already in PdfmdVersions.
                # Idempotent (a re-stamp doesn't append twice).
                creator = str(existing.get("/Creator") or "").strip()
                if not creator.endswith("pdfmd-cli"):
                    existing["/Creator"] = f"{creator} via pdfmd-cli" if creator else "pdfmd-cli"
                # clone_from, not append(): append() drops the whole outline of a PDF whose bookmarks are typed
                # `/Type /Outlines` (Calibre 9.16 writes them so), and a Calibre PDF's bookmarks are its headings
                writer = core.deferred("pdfmd_polish.info", "clone_pdf")(reader)
                core.deferred("pdfmd_polish.info", "add_metadata")(writer, {
                    **existing,
                    f"/{PDF_INFO_VERSIONS_KEY}": summary,
                    f"/{PDF_INFO_BUILD_DATE_KEY}": timestamp,
                    **({f"/{PDF_INFO_PARTIAL_KEY}": partial_parts} if partial_parts else {}),
                })
                core.atomic_write_pdf(writer, pdf_path)
        finally:
            pypdf_logger.setLevel(previous_level)
    except Exception as error:  # noqa: BLE001 -- best-effort, like package_version()
        emit("warning", None, f"WARN  --stamp: could not write the PDF Info-dictionary stamp "
              f"into {pdf_path} ({error}) -- the compile itself still succeeded",
              file=sys.stderr)


@contextmanager
def pdf_metadata_header_file(snippet: str | None) -> Iterator[Path | None]:
    """Materialize pdf_metadata_snippet's LaTeX to a temp file for
    --include-in-header -- same pattern as table_width_filter's fixed,
    non-document-specific content, so a plain system-tempdir file is fine.
    """
    if not snippet:
        yield None
        return
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".tex",
                            prefix="pdfmd-pdfmeta-", delete=False) as temporary:
        temporary.write(snippet)
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


def is_package_helper_yaml(path: Path) -> bool:
    """`<package>-pdfmd.yaml` and `<package>-office.yaml`: what a LaTeX package tells pdfmd (package_helper), not metadata.
    A source restored with its package has them beside the document (v3.28.38)."""
    return path.name.lower().endswith(("-pdfmd.yaml", "-pdfmd.yml", "-office.yaml", "-office.yml"))


def yaml_autoinclude(path: Path) -> bool:
    """Return whether automatic discovery may select this YAML file."""
    text = path.read_text(encoding="utf-8-sig")
    return not bool(re.search(r"^\s*autoinclude\s*:\s*(?:false|no|0)\s*$", text, re.IGNORECASE | re.MULTILINE))
