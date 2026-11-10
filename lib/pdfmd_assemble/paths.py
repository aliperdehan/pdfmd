"""Paths written beneath a build, extraction or unpack folder, on every host OS."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


def relative_parts(name: str) -> tuple[str, ...]:
    """POSIX relative components, refusing Windows roots, drives and separators too."""
    path = PurePosixPath(name)
    windows = PureWindowsPath(name)
    if (not path.parts or path.is_absolute() or windows.drive or windows.root
            or "\\" in name or "\x00" in name or ".." in path.parts
            or any(PureWindowsPath(part).drive for part in path.parts)):
        raise ValueError(f"{name!r} is not a safe relative path")
    return path.parts


def confined_destination(folder: Path, name: str) -> Path:
    """A safe relative destination whose existing links also stay beneath ``folder``."""
    target = folder.joinpath(*relative_parts(name))
    if not target.resolve().is_relative_to(folder.resolve()):
        raise ValueError(f"{name!r} resolves outside its folder")
    return target
