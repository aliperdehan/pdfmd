"""Fetching the fonts of the catalog into pdfmd's own folder.

Nothing is fetched unless asked for (`pdfmd --install fonts:NAME[,NAME...]`); every file is
checked against the pin the catalog records before it is kept; each package lives in a folder of its
own under the fonts directory (so removing one is deleting a folder), with its licence beside it.
No admin rights, no system font folder touched.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from typing import Callable

from ._catalog import PACKAGES
from .scripts import SCRIPT_NAMES

MANIFEST = "manifest.json"
CORE = ("stix", "jetbrains-mono", "noto-serif", "symbols")
CJK = ("cjk-sc", "cjk-tc", "cjk-jp", "cjk-kr")
GROUPS = {
    "core": CORE,
    "scripts": tuple(key for key in sorted(PACKAGES) if key not in CORE + CJK + ("emoji", "dejavu")),
    "cjk": CJK,
    "all": tuple(sorted(PACKAGES)),
}
ALIASES = {
    "latin": ("noto-serif",), "cyrillic": ("noto-serif",), "greek": ("noto-serif",), "kazakh": ("noto-serif",),
    "russian": ("noto-serif",), "stix-two": ("stix",), "mono": ("jetbrains-mono",), "jetbrains": ("jetbrains-mono",),
    "chinese": ("cjk-sc", "cjk-tc"), "zh": ("cjk-sc",), "zh-cn": ("cjk-sc",), "zh-hans": ("cjk-sc",),
    "zh-tw": ("cjk-tc",), "zh-hant": ("cjk-tc",), "japanese": ("cjk-jp",), "ja": ("cjk-jp",),
    "korean": ("cjk-kr",), "ko": ("cjk-kr",), "persian": ("arabic",), "urdu": ("arabic",),
    "arabic-script": ("arabic",), "devanagari-script": ("devanagari",), "hindi": ("devanagari",),
    "amiri": ("arabic",), "noto": ("noto-serif", "symbols"), "emojis": ("emoji",), "math": ("symbols",),
}
LICENCE_TEXT = {
    "OFL-1.1": "SIL Open Font License, Version 1.1 (https://openfontlicense.org): the fonts may be used, "
               "copied and redistributed freely; they may not be sold on their own.",
    "Bitstream-Vera": "The Bitstream Vera / DejaVu licence (see DejaVu-LICENSE.txt beside the fonts): free to use, "
                      "copy and redistribute; the additions to Vera are public domain.",
}


class UnknownPackage(KeyError):
    pass


def resolve(words: list[str]) -> list[str]:
    """Package keys for names, groups and aliases (``arabic``, ``cjk``, ``ja``, ``all``...)."""
    keys: list[str] = []
    for word in words:
        name = word.strip().casefold()
        if not name:
            continue
        found = GROUPS.get(name) or ALIASES.get(name) or ((name,) if name in PACKAGES else None)
        if not found:
            raise UnknownPackage(name)
        keys += [key for key in found if key not in keys]
    return keys


def read_manifest(directory: Path) -> dict:
    try:
        data = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def installed(directory: Path) -> dict[str, dict]:
    """The packages in the folder: those the manifest lists whose files are all still there."""
    found = {}
    for key, info in (read_manifest(directory).get("packages") or {}).items():
        folder = directory / key
        if key in PACKAGES and all((folder / name).is_file() for name in info.get("files", [])):
            found[key] = info
    return found


def megabytes(size: int) -> str:
    return f"{size / 1e6:.1f} MB" if size >= 1e5 else f"{max(size // 1000, 1)} kB"


def table(directory: Path) -> str:
    have = installed(directory)
    lines = [f"Fonts pdfmd can install (into {directory}; no admin rights, nothing is installed system-wide):", ""]
    lines.append(f"  {'NAME':15} {'SIZE':>8}  {'STATE':9} WHAT")
    for key in sorted(PACKAGES):
        package = PACKAGES[key]
        state = "installed" if key in have else "-"
        lines.append(f"  {key:15} {megabytes(package['size']):>8}  {state:9} {package['title']}")
    lines += ["",
              "Groups: core (" + " ".join(CORE) + "), scripts (every other alphabet, about 10 MB), "
              "cjk (all four, about 34 MB), all.",
              "Install: pdfmd --install fonts:arabic,cjk-sc    Remove: delete the folder, or "
              "pdfmd --uninstall fonts:arabic",
              "Fonts are used automatically: for other scripts in a document (see 'Other scripts'), and "
              "STIX Two Text / JetBrains Mono as pdfmd's defaults."]
    return "\n".join(lines)


def packages_for(code_points, language: str | None = None) -> list[str]:
    """Catalog packages that would draw the given characters (for a hint when none is installed)."""
    from .emoji import is_emoji_code_point
    from .scripts import COMMON, han_language, script_of

    wanted: list[str] = []
    for code_point in code_points:
        script = script_of(code_point)
        cjk_punctuation = script in COMMON and (0x3000 <= code_point <= 0x303F or 0xFF00 <= code_point <= 0xFFEF)
        if is_emoji_code_point(code_point):
            matches = ["emoji"]
        elif script in ("Hani", "Hira", "Kana", "Hang", "Bopo") or cjk_punctuation:
            matches = ["cjk-" + {"sc": "sc", "tc": "tc", "ja": "jp", "ko": "kr"}[han_language(chr(code_point), language)]]
        else:
            matches = [key for key, package in PACKAGES.items()
                       if script in package["scripts"] and not key.startswith("cjk")
                       and key not in ("dejavu", "emoji", "stix", "jetbrains-mono")][:1]
        for key in matches:
            if key not in wanted:
                wanted.append(key)
    return wanted


# -- fetching ----------------------------------------------------------------------

def _download(url: str, opener: Callable = urllib.request.urlopen) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "pdfmd-fonts"})
    with opener(request, timeout=300) as response:
        return response.read()


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _file_bytes(item: dict, archives: dict[str, bytes], opener: Callable) -> bytes:
    """One catalog file's content, checked against its pin."""
    if "zip" in item:
        url = item["zip"]
        if url not in archives:
            archives[url] = _download(url, opener)
            if hashlib.sha256(archives[url]).hexdigest() != item["zip_sha256"]:
                raise OSError(f"SHA-256 mismatch for {url}")
        with zipfile.ZipFile(io.BytesIO(archives[url])) as bundle:
            return bundle.read(item["member"])
    data = _download(item["url"], opener)
    if _git_blob_sha1(data) != item["git_sha1"]:
        raise OSError(f"checksum mismatch for {item['url']}")
    return data


def install(keys: list[str], directory: Path, log: Callable[[str], None] = print,
            opener: Callable = urllib.request.urlopen) -> list[str]:
    """Install packages; returns the keys that failed. Re-installing replaces the folder."""
    failed: list[str] = []
    archives: dict[str, bytes] = {}
    manifest = read_manifest(directory)
    manifest.setdefault("packages", {})
    directory.mkdir(parents=True, exist_ok=True)
    for key in keys:
        package = PACKAGES[key]
        log(f"INSTALL  {key} ({megabytes(package['size'])}): {package['title']}")
        staging = directory / f".{key}.part"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        try:
            for item in package["files"]:
                (staging / item["name"]).write_bytes(_file_bytes(item, archives, opener))
            licence = (f"{package['title']}\n\nLicence: {package['license']}\n"
                       f"{LICENCE_TEXT.get(package['license'], '')}\nUpstream: {package['homepage']}\n"
                       f"Installed by pdfmd on {date.today().isoformat()}; the files are exactly the upstream ones "
                       "(checked against the checksums pinned in pdfmd).\n")
            (staging / "LICENSE-pdfmd.txt").write_text(licence, encoding="utf-8")
        except (OSError, zipfile.BadZipFile, KeyError) as error:
            log(f"Could not install {key}: {error}")
            shutil.rmtree(staging, ignore_errors=True)
            failed.append(key)
            continue
        target = directory / key
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
        manifest["packages"][key] = {"files": [item["name"] for item in package["files"]],
                                     "installed": date.today().isoformat(),
                                     "scripts": list(package["scripts"])}
        log(f"  installed in {target}")
    manifest["version"] = 1
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    return failed


def uninstall(keys: list[str], directory: Path, log: Callable[[str], None] = print) -> None:
    manifest = read_manifest(directory)
    for key in keys:
        shutil.rmtree(directory / key, ignore_errors=True)
        (manifest.get("packages") or {}).pop(key, None)
        log(f"REMOVED  {key}")
    if directory.is_dir():
        (directory / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")


def script_label(codes) -> str:
    return ", ".join(SCRIPT_NAMES.get(code, code) for code in codes)
