"""Resolve the Beamer setting before choosing a writer or a PDF engine."""

from __future__ import annotations

from pathlib import Path

from pdfmd_base import core


def source(document: Path, metadata, cli: bool | None) -> str | None:
    """The winning request, described for errors, or None when slides are off."""
    if cli is not None:
        return "-p/--presentation" if cli else None
    files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
    for where, options in core.load_package("pdfmd_config").option_sources(document, files):
        if "presentation" not in options:
            continue
        if options["presentation"] is not True:
            return None
        if where == "document":
            where = f"{document.name}'s front matter"
        elif where == "config":
            where = core.display_path(core.config_path())
        return f"presentation: true in {where}"
    return None


def validate(request: str, target: str, stop_at: str | None, *, report: bool = False,
             document: Path | None = None) -> None:
    cli = request == "-p/--presentation"
    if report:
        raise SystemExit(f"{'--presentation' if cli else request} cannot be combined with --report/--book")
    if stop_at == "markdown":
        watch = " or -w/--watch" if cli else ""
        raise SystemExit(f"--stop-at markdown can't be combined with {request}{watch}")
    if target != "pdf" and stop_at != "tex":
        raise SystemExit(f"{request} always produces a PDF (via Beamer); "
                         "it can't be combined with --to/-o for another format")
    if document is not None:
        if document.suffix.lower() == ".qmd":
            raise SystemExit(f"{request} isn't supported for .qmd -- set the "
                             "format in the document's own Quarto front matter instead")
        if document.suffix.lower() in core.OFFICE_INPUT_EXTENSIONS:
            raise SystemExit(f"{request} isn't supported for an office-document input")


def engines(document: Path, metadata_files: list[Path], engine: str | None,
            request: str, target: str, verbose: bool) -> list[str]:
    if target != "pdf":
        return []
    try:
        if not core.which("pandoc"):
            raise SystemExit(core.PANDOC_MISSING)
        defaults = core.select_engines(engine, True)
        return core.resolve_engines(document, engine, defaults, True, target, metadata_files, verbose)
    except SystemExit as error:
        if request == "-p/--presentation":
            raise
        raise SystemExit(f"{request}: {error}") from None
