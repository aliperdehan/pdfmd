"""Finding fonts and reading what they cover, without any dependency.

A font's file is read just far enough to learn its family name and the code
points of its `cmap` (TrueType/OpenType and collections); the installed fonts
come from fontconfig (`fc-list`) when it is there and from a scan of the usual
font folders when it is not, plus a folder of pdfmd's own (`pdfmd --install
fonts`). Nothing here imports pdfmd.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")
REGULAR_STYLES = ("regular", "roman", "book", "normal", "text", "medium")
UNSUPPORTED_FORMATS = ("type 1", "pcf", "bdf", "bitmap", "cff bitmap")


@dataclass(frozen=True)
class Face:
    family: str
    style: str
    path: str
    index: int = 0
    aliases: tuple[str, ...] = ()
    managed: bool = False  # lives in pdfmd's own font folder, so fontspec needs its path

    def names(self) -> tuple[str, ...]:
        return (self.family, *self.aliases)


# -- reading an sfnt file -------------------------------------------------------

def _directory(handle, base: int) -> dict[bytes, tuple[int, int]]:
    handle.seek(base)
    head = handle.read(12)
    if len(head) < 12:
        raise ValueError("short font header")
    count = struct.unpack(">H", head[4:6])[0]
    table = handle.read(16 * count)
    tables: dict[bytes, tuple[int, int]] = {}
    for number in range(count):
        tag, _checksum, offset, length = struct.unpack(">4sIII", table[number * 16:number * 16 + 16])
        tables[tag] = (offset, length)
    return tables


def _offsets(handle) -> list[int]:
    handle.seek(0)
    magic = handle.read(4)
    if magic == b"ttcf":
        _version, count = struct.unpack(">II", handle.read(8))
        return list(struct.unpack(f">{count}I", handle.read(4 * count)))
    if magic in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"):
        return [0]
    raise ValueError("not an sfnt font")


def _names(handle, tables) -> tuple[str, str]:
    if b"name" not in tables:
        return "", ""
    offset, length = tables[b"name"]
    handle.seek(offset)
    data = handle.read(length)
    _format, count, strings = struct.unpack(">HHH", data[:6])
    best: dict[int, tuple[int, str]] = {}
    for number in range(count):
        platform, _encoding, language, name_id, size, start = struct.unpack(
            ">6H", data[6 + 12 * number:18 + 12 * number])
        if name_id not in (1, 2, 16, 17):
            continue
        raw = data[strings + start:strings + start + size]
        if platform in (0, 3):
            text, rank = raw.decode("utf-16-be", "replace"), (0 if language == 0x409 else 1)
        elif platform == 1:
            text, rank = raw.decode("mac_roman", "replace"), (0 if language == 0 else 2)
        else:
            continue
        if name_id not in best or rank < best[name_id][0]:
            best[name_id] = (rank, text)
    family = (best.get(16) or best.get(1) or (0, ""))[1]
    style = (best.get(17) or best.get(2) or (0, ""))[1]
    return family, style


def _cmap(handle, tables) -> frozenset[int]:
    if b"cmap" not in tables:
        return frozenset()
    offset, length = tables[b"cmap"]
    handle.seek(offset)
    data = handle.read(length)
    _version, count = struct.unpack(">HH", data[:4])
    covered: set[int] = set()
    seen: set[int] = set()
    for number in range(count):
        platform, encoding, start = struct.unpack(">HHI", data[4 + 8 * number:12 + 8 * number])
        if platform not in (0, 3) or (platform == 3 and encoding not in (1, 10)) or start in seen:
            continue
        seen.add(start)
        form = struct.unpack(">H", data[start:start + 2])[0]
        if form == 12:
            groups = struct.unpack(">I", data[start + 12:start + 16])[0]
            for group in range(groups):
                first, last, _glyph = struct.unpack(">III", data[start + 16 + 12 * group:start + 28 + 12 * group])
                covered.update(range(first, last + 1))
        elif form == 4:
            segments = struct.unpack(">H", data[start + 6:start + 8])[0] // 2
            ends = start + 14
            starts = ends + 2 * segments + 2
            deltas = starts + 2 * segments
            ranges = deltas + 2 * segments
            for segment in range(segments):
                end = struct.unpack(">H", data[ends + 2 * segment:ends + 2 * segment + 2])[0]
                first = struct.unpack(">H", data[starts + 2 * segment:starts + 2 * segment + 2])[0]
                delta = struct.unpack(">h", data[deltas + 2 * segment:deltas + 2 * segment + 2])[0]
                shift = struct.unpack(">H", data[ranges + 2 * segment:ranges + 2 * segment + 2])[0]
                if first == 0xFFFF:
                    continue
                if shift == 0:
                    covered.update(code for code in range(first, end + 1) if (code + delta) & 0xFFFF)
                    continue
                for code in range(first, end + 1):
                    position = ranges + 2 * segment + shift + 2 * (code - first)
                    if position + 2 <= len(data) and struct.unpack(">H", data[position:position + 2])[0]:
                        covered.add(code)
    return frozenset(covered)


_COVERAGE: dict[tuple[str, int], frozenset[int]] = {}


def coverage(path: str, index: int = 0) -> frozenset[int]:
    """The code points a font file's `cmap` maps to a glyph (empty if unreadable)."""
    key = (path, index & 0xFFFF)
    if key not in _COVERAGE:
        try:
            with open(path, "rb") as handle:
                offsets = _offsets(handle)
                base = offsets[min(index & 0xFFFF, len(offsets) - 1)]
                _COVERAGE[key] = _cmap(handle, _directory(handle, base))
        except (OSError, ValueError, struct.error):
            _COVERAGE[key] = frozenset()
    return _COVERAGE[key]


_VARIABLE: dict[str, bool] = {}


def is_variable(path: str) -> bool:
    """Whether a font file is a variable font (it has an `fvar` table). TeX engines load such
    a font at its default weight, which for many families is the thinnest one."""
    if path not in _VARIABLE:
        try:
            with open(path, "rb") as handle:
                offsets = _offsets(handle)
                _VARIABLE[path] = b"fvar" in _directory(handle, offsets[0])
        except (OSError, ValueError, struct.error):
            _VARIABLE[path] = False
    return _VARIABLE[path]


def file_faces(path: Path, managed: bool = False) -> list[Face]:
    """Every face in one font file, named from its own `name` table."""
    faces: list[Face] = []
    try:
        with path.open("rb") as handle:
            for number, base in enumerate(_offsets(handle)):
                family, style = _names(handle, _directory(handle, base))
                if family:
                    faces.append(Face(family, style or "Regular", str(path), number, (), managed))
    except (OSError, ValueError, struct.error):
        pass
    return faces


# -- where fonts are -----------------------------------------------------------------

def system_font_directories() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        folders = [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library/Fonts"]
    elif sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        folders = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts", local / "Microsoft" / "Windows" / "Fonts"]
    else:
        folders = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".fonts",
                   Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "fonts"]
    return [folder for folder in folders if folder.is_dir()]


def _fontconfig_faces() -> list[Face] | None:
    exe = shutil.which("fc-list")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--format", "%{family}\t%{style}\t%{file}\t%{index}\t%{fontformat}\n"],
                             capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    faces = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 5 or parts[4].casefold() in UNSUPPORTED_FORMATS:
            continue
        names = [name.strip() for name in parts[0].replace("\\,", "\0").split(",")]
        names = [name.replace("\0", ",") for name in names if name]
        styles = [style.strip() for style in parts[1].split(",") if style.strip()]
        if not names or not parts[2].lower().endswith(FONT_SUFFIXES):
            continue
        try:
            index = int(parts[3])
        except ValueError:
            index = 0
        faces.append(Face(names[0], styles[0] if styles else "Regular", parts[2], index, tuple(names[1:])))
    return faces


def _scanned_faces(folders: list[Path], managed: bool = False) -> list[Face]:
    faces: list[Face] = []
    for folder in folders:
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() in FONT_SUFFIXES and path.is_file():
                faces.extend(file_faces(path, managed))
    return faces


class FontIndex:
    """The installed faces, found once, looked up by family name."""

    def __init__(self, managed_directory: Path | None = None, use_system: bool = True):
        faces: list[Face] = []
        if use_system:
            found = _fontconfig_faces()
            faces = found if found is not None else _scanned_faces(system_font_directories())
        self.managed_directory = managed_directory
        if managed_directory is not None and managed_directory.is_dir():
            known = {(face.path, face.index) for face in faces}
            faces += [face for face in _scanned_faces([managed_directory], True)
                      if (face.path, face.index) not in known]
        self.faces = faces
        self._by_name: dict[str, list[Face]] = {}
        for face in faces:
            for name in face.names():
                self._by_name.setdefault(name.casefold(), []).append(face)

    def has(self, family: str) -> bool:
        return family.casefold() in self._by_name

    def regular(self, family: str) -> Face | None:
        """The face of ``family`` that stands for it: its regular style."""
        candidates = self._by_name.get(family.casefold())
        if not candidates:
            return None
        # A managed copy wins over a system one of the same name: it is the one pdfmd chose. Then the
        # plainest style ("Regular" before "Medium"), then a static font before a variable one.
        rank = {name: number for number, name in enumerate(REGULAR_STYLES)}
        return min(candidates, key=lambda face: (not face.managed, rank.get(face.style.casefold(), 50),
                                                 is_variable(face.path), len(face.style), face.index))

    def styles(self, face: Face) -> dict[str, Face]:
        """The bold/italic/bold-italic faces beside ``face`` (same family, same folder)."""
        found: dict[str, Face] = {}
        for other in self._by_name.get(face.family.casefold(), []):
            if os.path.dirname(other.path) != os.path.dirname(face.path):
                continue
            style = other.style.casefold()
            bold, italic = "bold" in style and "semi" not in style and "extra" not in style, \
                "italic" in style or "oblique" in style
            kind = "bolditalic" if bold and italic else "bold" if bold else "italic" if italic else None
            if kind and style.replace(" ", "") in (kind, "bold", "italic", "oblique", "bolditalic", "boldoblique"):
                found.setdefault(kind, other)
        return found

    def covers(self, family: str, code_point: int) -> bool:
        face = self.regular(family)
        return face is not None and code_point in coverage(face.path, face.index)

    def static(self, family: str) -> bool:
        """True for a family that is not (only) a variable font."""
        face = self.regular(family)
        return face is not None and not is_variable(face.path)
