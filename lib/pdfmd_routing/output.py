"""Resolve the protected final destination before a conversion route writes it."""

from __future__ import annotations

from pathlib import Path

core = None


def planned(source: Path, directory: Path | None, target: str) -> Path:
    """The ordinary destination before rewrite protection."""
    extension = core.output_extension_for(target, source)
    return directory / (source.stem + extension) if directory else source.with_suffix(extension)


def protected(source: Path, output: Path, target: str, metadata) -> Path:
    files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
    if target == core.ASSEMBLED_FORMAT or core.rewrite_wanted(source, files):
        return output
    return core.numbered_output(output, core.rewrite_template(source, files))


def job_target(final: Path | None, source: Path, goal: str) -> Path:
    extension = "." + goal
    if final is None:
        return source.with_suffix(extension)
    if final.is_dir():
        return final / (source.stem + extension)
    return final if final.suffix else final.with_suffix(extension)


def single(source: Path, output: Path, job: dict | None, target: str, metadata_for) -> Path:
    metadata = [] if source.suffix.lower() == ".qmd" else metadata_for(source)
    if job is not None:
        final = job_target(job["final"], source, job["goal"])
        job["final"] = protected(source, final, job["goal"], metadata)
        return output  # the intermediate is private to this build
    return protected(source, output, target, metadata)
