"""Tesseract language files, fetched into pdfmd's own folder (`pdfmd --install ocr:LANG`).

The `tessdata_fast` models of the tesseract-ocr project (Apache-2.0), each checked against the git
blob SHA-1 pinned in `_tessdata_catalog.py`. Nothing system-wide is touched: the files live in one
folder, which `pdfmd` hands to Tesseract (through TESSDATA_PREFIX) only for a PDF whose requested
languages it has all of. English and the orientation model are always added, so the folder can stand
on its own.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable

from ._tessdata_catalog import COMMIT, LANGUAGES, REPOSITORY

ALWAYS = ("eng", "osd")
MANIFEST = "manifest.json"
NAMES = {
    "afr": "Afrikaans", "amh": "Amharic", "ara": "Arabic", "aze": "Azerbaijani", "bel": "Belarusian",
    "ben": "Bengali", "bul": "Bulgarian", "cat": "Catalan", "ces": "Czech", "chi_sim": "Chinese, simplified",
    "chi_sim_vert": "Chinese, simplified, vertical", "chi_tra": "Chinese, traditional",
    "chi_tra_vert": "Chinese, traditional, vertical", "dan": "Danish", "deu": "German", "ell": "Greek",
    "eng": "English", "est": "Estonian", "fas": "Persian", "fin": "Finnish", "fra": "French", "heb": "Hebrew",
    "hin": "Hindi", "hrv": "Croatian", "hun": "Hungarian", "hye": "Armenian", "ind": "Indonesian",
    "isl": "Icelandic", "ita": "Italian", "jpn": "Japanese", "jpn_vert": "Japanese, vertical",
    "kat": "Georgian", "kaz": "Kazakh", "khm": "Khmer", "kor": "Korean", "lao": "Lao", "lat": "Latin",
    "lav": "Latvian", "lit": "Lithuanian", "mkd": "Macedonian", "mon": "Mongolian", "msa": "Malay",
    "nld": "Dutch", "nor": "Norwegian", "osd": "orientation and script detection", "pol": "Polish",
    "por": "Portuguese", "ron": "Romanian", "rus": "Russian", "slk": "Slovak", "slv": "Slovenian",
    "spa": "Spanish", "srp": "Serbian", "srp_latn": "Serbian, Latin", "swe": "Swedish", "tam": "Tamil",
    "tha": "Thai", "tur": "Turkish", "ukr": "Ukrainian", "urd": "Urdu", "uzb": "Uzbek", "vie": "Vietnamese",
}
ALIASES = {
    "ar": "ara", "arabic": "ara", "be": "bel", "belarusian": "bel", "bg": "bul", "cs": "ces", "czech": "ces",
    "da": "dan", "de": "deu", "german": "deu", "el": "ell", "greek": "ell", "en": "eng", "english": "eng",
    "es": "spa", "spanish": "spa", "fa": "fas", "persian": "fas", "fi": "fin", "fr": "fra", "french": "fra",
    "he": "heb", "hebrew": "heb", "hi": "hin", "hindi": "hin", "hu": "hun", "hy": "hye", "armenian": "hye",
    "it": "ita", "italian": "ita", "ja": "jpn", "japanese": "jpn", "ka": "kat", "georgian": "kat",
    "kazakh": "kaz", "kk": "kaz", "ko": "kor", "korean": "kor", "nl": "nld", "dutch": "nld", "pl": "pol",
    "polish": "pol", "pt": "por", "portuguese": "por", "ro": "ron", "ru": "rus", "russian": "rus",
    "sv": "swe", "swedish": "swe", "th": "tha", "thai": "tha", "tr": "tur", "turkish": "tur", "uk": "ukr",
    "ukrainian": "ukr", "ur": "urd", "urdu": "urd", "vi": "vie", "vietnamese": "vie",
    "zh": "chi_sim", "zh-cn": "chi_sim", "zh-hans": "chi_sim", "chinese": "chi_sim",
    "zh-tw": "chi_tra", "zh-hant": "chi_tra",
}


class UnknownLanguage(KeyError):
    pass


def resolve(words: list[str]) -> list[str]:
    """Tesseract codes for codes, ISO 639-1 codes and names (`ru`, `kazakh`, `chi_sim`)."""
    codes: list[str] = []
    for word in words:
        name = word.strip().casefold()
        if not name:
            continue
        code = name if name in LANGUAGES else ALIASES.get(name)
        if code is None or code not in LANGUAGES:
            raise UnknownLanguage(name)
        if code not in codes:
            codes.append(code)
    return codes


def read_manifest(directory: Path) -> dict:
    try:
        data = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def installed(directory: Path) -> list[str]:
    """The languages in the folder whose files are there (and as large as pinned)."""
    return sorted(code for code in (read_manifest(directory).get("languages") or {})
                  if code in LANGUAGES and (directory / f"{code}.traineddata").is_file()
                  and (directory / f"{code}.traineddata").stat().st_size == LANGUAGES[code][1])


def covers(directory: Path, wanted: list[str]) -> bool:
    """True when the folder has every one of `wanted` (Tesseract's `eng+rus` spelling already split)."""
    have = set(installed(directory))
    return bool(wanted) and all(code in have for code in wanted)


def megabytes(size: int) -> str:
    return f"{size / 1e6:.1f} MB" if size >= 1e5 else f"{max(size // 1000, 1)} kB"


def table(directory: Path) -> str:
    have = set(installed(directory))
    lines = [f"Tesseract languages pdfmd can install (into {directory}; no admin rights; the fast models, "
             "Apache-2.0):", "", f"  {'CODE':13} {'SIZE':>8}  {'STATE':9} LANGUAGE"]
    for code in sorted(LANGUAGES):
        lines.append(f"  {code:13} {megabytes(LANGUAGES[code][1]):>8}  {'installed' if code in have else '-':9} "
                     f"{NAMES.get(code, '')}")
    lines += ["", "Install: pdfmd --install ocr:rus,kaz  (also ru, kk, russian, kazakh, zh, ja...; English and "
                  "the orientation model come along)",
              "Remove: pdfmd --uninstall ocr:rus",
              "Used for `pdfmd scan.pdf --lang rus` when this folder has every language asked for; "
              "otherwise Tesseract's own languages are used (set TESSDATA_PREFIX yourself to override)."]
    return "\n".join(lines)


def _download(url: str, opener: Callable) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "pdfmd-tessdata"})
    with opener(request, timeout=600) as response:
        return response.read()


def install(codes: list[str], directory: Path, log: Callable[[str], None] = print,
            opener: Callable = urllib.request.urlopen) -> list[str]:
    """Fetch languages (plus English and OSD); returns the codes that failed."""
    failed: list[str] = []
    manifest = read_manifest(directory)
    manifest.setdefault("languages", {})
    directory.mkdir(parents=True, exist_ok=True)
    for code in [*codes, *(extra for extra in ALWAYS if extra not in codes)]:
        sha1, size = LANGUAGES[code]
        if code in installed(directory):
            continue
        log(f"INSTALL  {code} ({megabytes(size)}): {NAMES.get(code, code)}")
        url = f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{code}.traineddata"
        try:
            data = _download(url, opener)
            if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() != sha1:
                raise OSError(f"checksum mismatch for {url}")
            part = directory / f".{code}.traineddata.part"
            part.write_bytes(data)
            part.replace(directory / f"{code}.traineddata")
        except OSError as error:
            log(f"Could not install {code}: {error}")
            failed.append(code)
            continue
        manifest["languages"][code] = {"installed": date.today().isoformat()}
    manifest["version"] = 1
    (directory / "LICENSE-pdfmd.txt").write_text(
        "Tesseract language models (tessdata_fast), Apache-2.0, https://github.com/" + REPOSITORY + "\n"
        f"Installed by pdfmd; the files are exactly the upstream ones at commit {COMMIT}\n"
        "(checked against the checksums pinned in pdfmd).\n", encoding="utf-8")
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    return failed


def uninstall(codes: list[str], directory: Path, log: Callable[[str], None] = print) -> None:
    manifest = read_manifest(directory)
    for code in codes:
        (directory / f"{code}.traineddata").unlink(missing_ok=True)
        (manifest.get("languages") or {}).pop(code, None)
        log(f"REMOVED  {code}")
    if directory.is_dir():
        (directory / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
