"""Find a named project style in the same locations for every Pandoc writer."""
from __future__ import annotations

import subprocess
from pathlib import Path

from pdfmd_base import core
from .installed_styles import pinned_style
from .pandoc_defaults import custom_template, defaults_value, template_source

WRITER_EXTENSIONS = {
    "html": ("html5", "html"), "html5": ("html5", "html"),
    "epub": ("epub3", "epub"), "epub3": ("epub3", "epub"),
    "docbook": ("docbook4", "docbook"),
    "jats": ("jats_archiving", "jats"),
}
# Pandoc uses reference documents for these binary office formats.
NO_TEMPLATES = frozenset({"ansi", "docx", "json", "native", "odt", "pptx"})


def style_folders(document: Path, accessories: bool):
    root = document.parent
    yield root
    yield root / "templates"
    config = core.config_path()
    if config is not None:
        yield config.parent
        yield config.parent / "templates"
    if accessories:
        yield from core.accessory_directories(root, document.stem)[1:]


def find_style(document: Path, filenames, *, excludes=(), accessories: bool = False,
               template: bool = False) -> Path | None:
    """First matching file, with the names ranked independently in each location."""
    excluded = {document.resolve(), *(path.resolve() for path in excludes)}
    for folder in style_folders(document, accessories):
        for name in filenames:
            candidate = folder / name
            if not candidate.is_file() or (path := candidate.resolve()) in excluded:
                continue
            if template and candidate.stem == document.stem and candidate.parent == document.parent:
                # A previous export can have the same name as a document-specific template.
                from pdfmd_buildinfo.record import matching_outputs

                roots = {core.cache_root() / "builds", document.parent / core.LOCAL_CACHE_DIRNAME / "builds"}
                if matching_outputs([path], roots):
                    continue
            return path
    return None


def local_csl(document: Path, no_auto: list[str] | None) -> Path | None:
    if not core.discovery_disabled(no_auto, "csl"):
        return find_style(document, (f"{document.stem}.csl", "csl.csl"))
    return None


def discovered(kind: str, value: str | Path, verbose: bool) -> None:
    detail = core.display_path(value) if isinstance(value, Path) else value
    core.AUTO_LOG.record(kind, detail, verbose, heading="FOUND", short=detail)


def pdf_writer(engine: str, presentation: bool) -> str:
    if presentation:
        return "beamer"
    if engine in ("typst", "context"):
        return engine
    if engine in core.LATEX_ENGINES:
        return "latex"
    return "html5"


def template_extensions(writer: str) -> tuple[str, ...]:
    writer = writer.split("+", 1)[0].split("-", 1)[0]
    return () if writer in NO_TEMPLATES else WRITER_EXTENSIONS.get(writer, (writer,))


def defaults_csl(document: Path, metadata: list[Path], options) -> str | None:
    if not options:
        return None
    cwd = core.pandoc_working_directory(core.metadata_cwd(metadata, document.parent))
    value = defaults_value("csl", options, cwd)
    if value is None:
        mapping = defaults_value("metadata", options, cwd)
        if isinstance(mapping, dict):
            value = mapping.get("csl")
    return value if isinstance(value, str) and value else None


def template_args(document: Path, metadata_files: list[Path], writer: str, output: Path,
                  options: list[str], cwd: Path, no_auto: list[str] | None, verbose: bool) -> list[str]:
    """Select the template for this attempt and remember the local file for source attachment."""
    core.BUILD.pop("project-template", None)
    extensions = template_extensions(writer)
    if not extensions:
        return []
    options = options[:options.index("--")] if "--" in options else options
    try:
        explicit = custom_template(options, cwd)
    except (OSError, ValueError, subprocess.SubprocessError):
        # Let Pandoc diagnose a defaults file we could not read.
        return []
    if explicit is not None:
        try:
            _, path = template_source(explicit, cwd, options, "." + extensions[0], local_only=True)
        except (OSError, ValueError):
            if path := pinned_style("template", explicit):
                core.BUILD["project-template"] = path
                discovered("TEMPLATE", path, verbose)
                return ["--template", str(path)]
            discovered("TEMPLATE", explicit, verbose)
        else:
            core.BUILD["project-template"] = path
            discovered("TEMPLATE", path, verbose)
        return []
    named = core.first_pdfmd_option(document, metadata_files, "template")
    if named is not None:
        if not isinstance(named, str) or not named.strip():
            raise SystemExit(f"{core.display_path(document)}: pdfmd-options.template must be a template path")
        name = Path(named.strip()).expanduser()
        path = document.parent / name
        if not path.is_file():
            path = pinned_style("template", named.strip())
            if path is None:
                raise SystemExit(f"{core.display_path(document)}: template {named!r} does not exist")
        path = path.resolve()
    elif not core.discovery_disabled(no_auto, "template"):
        names = [f"{stem}.{extension}" for stem in (document.stem, "template") for extension in extensions]
        path = find_style(document, names, excludes=(output,), template=True)
        if path is None:
            return []
    else:
        return []
    core.BUILD["project-template"] = path
    discovered("TEMPLATE", path, verbose)
    return ["--template", str(path)]
