#!/usr/bin/env python3
"""Regenerate pdfmd_unicode/_catalog.py, the list of fonts `pdfmd --install fonts` can fetch.

    python3 scripts/gen_font_catalog.py            # rewrite the catalog (needs network and `gh`)
    python3 scripts/gen_font_catalog.py --check    # print what would change, write nothing

Every file in the catalog is pinned: a Noto file by the commit of the repository it is
fetched from and its git blob SHA-1 (what GitHub lists for it), a file out of an archive
(a release zip, a CTAN zip, a PyPI wheel) by the SHA-256 of that archive. pdfmd refuses a
download that does not match, so a moved upstream branch can change nothing silently.
Re-run this to move to newer fonts, read the diff, and bump pdfmd.

All the fonts are under the SIL Open Font License 1.1 except DejaVu (its own free
licence, Bitstream Vera's, plus public-domain additions); the licence of each is
recorded in its catalog entry and written beside the fonts when they are installed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "pdfmd_unicode" / "_catalog.py"
NOTO_REPOSITORY = "notofonts/notofonts.github.io"
CJK_REPOSITORY = "notofonts/noto-cjk"
STYLES = ("Regular", "Bold", "Italic", "BoldItalic")

# key -> (title, scripts, [Noto family folders]); serif where Noto has one
NOTO_SCRIPTS = {
    "noto-serif": ("Noto Serif: Latin, Cyrillic (with Kazakh) and Greek", ("Latn", "Cyrl", "Grek"), ["NotoSerif"]),
    "hebrew": ("Hebrew: Noto Serif Hebrew", ("Hebr",), ["NotoSerifHebrew"]),
    "armenian": ("Armenian: Noto Serif Armenian", ("Armn",), ["NotoSerifArmenian"]),
    "georgian": ("Georgian: Noto Serif Georgian", ("Geor",), ["NotoSerifGeorgian"]),
    "devanagari": ("Devanagari: Noto Serif Devanagari", ("Deva",), ["NotoSerifDevanagari"]),
    "bengali": ("Bengali: Noto Serif Bengali", ("Beng",), ["NotoSerifBengali"]),
    "tamil": ("Tamil: Noto Serif Tamil", ("Taml",), ["NotoSerifTamil"]),
    "telugu": ("Telugu: Noto Serif Telugu", ("Telu",), ["NotoSerifTelugu"]),
    "kannada": ("Kannada: Noto Serif Kannada", ("Knda",), ["NotoSerifKannada"]),
    "malayalam": ("Malayalam: Noto Serif Malayalam", ("Mlym",), ["NotoSerifMalayalam"]),
    "gujarati": ("Gujarati: Noto Serif Gujarati", ("Gujr",), ["NotoSerifGujarati"]),
    "gurmukhi": ("Gurmukhi: Noto Serif Gurmukhi", ("Guru",), ["NotoSerifGurmukhi"]),
    "sinhala": ("Sinhala: Noto Serif Sinhala", ("Sinh",), ["NotoSerifSinhala"]),
    "thai": ("Thai: Noto Serif Thai", ("Thai",), ["NotoSerifThai"]),
    "lao": ("Lao: Noto Serif Lao", ("Laoo",), ["NotoSerifLao"]),
    "khmer": ("Khmer: Noto Serif Khmer", ("Khmr",), ["NotoSerifKhmer"]),
    "myanmar": ("Myanmar: Noto Serif Myanmar", ("Mymr",), ["NotoSerifMyanmar"]),
    "tibetan": ("Tibetan: Noto Serif Tibetan", ("Tibt",), ["NotoSerifTibetan"]),
    "ethiopic": ("Ethiopic: Noto Serif Ethiopic", ("Ethi",), ["NotoSerifEthiopic"]),
    "syriac": ("Syriac: Noto Sans Syriac", ("Syrc",), ["NotoSansSyriac"]),
    "thaana": ("Thaana: Noto Sans Thaana", ("Thaa",), ["NotoSansThaana"]),
    "cherokee": ("Cherokee: Noto Sans Cherokee", ("Cher",), ["NotoSansCherokee"]),
    "nastaliq": ("Urdu Nastaliq: Noto Nastaliq Urdu (chosen for text in `lang: ur`)", ("Arab",), ["NotoNastaliqUrdu"]),
    "oriya": ("Oriya: Noto Sans Oriya", ("Orya",), ["NotoSansOriya"]),
    "mongolian": ("Mongolian: Noto Sans Mongolian", ("Mong",), ["NotoSansMongolian"]),
    "coptic": ("Coptic: Noto Sans Coptic", ("Copt",), ["NotoSansCoptic"]),
    "gothic": ("Gothic: Noto Sans Gothic", ("Goth",), ["NotoSansGothic"]),
    "runic": ("Runic: Noto Sans Runic", ("Runr",), ["NotoSansRunic"]),
    "canadian": ("Canadian Aboriginal syllabics: Noto Sans Canadian Aboriginal", ("Cans",), ["NotoSansCanadianAboriginal"]),
    "tifinagh": ("Tifinagh: Noto Sans Tifinagh", ("Tfng",), ["NotoSansTifinagh"]),
    "nko": ("N'Ko: Noto Sans NKo", ("Nkoo",), ["NotoSansNKo"]),
    "indic-sans": ("Sans-serif faces of the Indic scripts (Devanagari, Bengali, Tamil, Telugu, Kannada, Malayalam, "
                   "Gujarati, Gurmukhi, Sinhala), for documents set in a sans font",
                   ("Deva", "Beng", "Taml", "Telu", "Knda", "Mlym", "Gujr", "Guru", "Sinh"),
                   ["NotoSansDevanagari", "NotoSansBengali", "NotoSansTamil", "NotoSansTelugu", "NotoSansKannada",
                    "NotoSansMalayalam", "NotoSansGujarati", "NotoSansGurmukhi", "NotoSansSinhala"]),
    "symbols": ("Symbols, arrows, dingbats, mathematical alphanumerics (Noto Sans Symbols, Symbols 2, Math)",
                ("Zyyy",), ["NotoSansSymbols", "NotoSansSymbols2", "NotoSansMath"]),
}
NOTO_ARABIC = ["NotoNaskhArabic"]
# key -> (title, scripts, language folder, files)
CJK = {
    "cjk-sc": ("Chinese, simplified: Noto Serif SC", ("Hani",), "SC"),
    "cjk-tc": ("Chinese, traditional: Noto Serif TC", ("Hani",), "TC"),
    "cjk-jp": ("Japanese: Noto Serif JP", ("Hani", "Hira", "Kana"), "JP"),
    "cjk-kr": ("Korean: Noto Serif KR", ("Hani", "Hang"), "KR"),
}


def gh(path: str, *jq: str) -> str:
    return subprocess.run(["gh", "api", path, *(["--jq", jq[0]] if jq else [])], capture_output=True,
                          text=True, check=True).stdout.strip()


def gh_json(path: str):
    return json.loads(gh(path))


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "pdfmd-catalog"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def raw_files(repository: str, commit: str, directory: str, wanted) -> list[dict]:
    """The files of a folder of a repository that ``wanted(name)`` accepts."""
    try:
        listing = gh_json(f"repos/{repository}/contents/{directory}?ref={commit}")
    except subprocess.CalledProcessError:
        return []
    found = []
    for item in listing:
        if item["type"] == "file" and wanted(item["name"]):
            found.append({"url": f"https://raw.githubusercontent.com/{repository}/{commit}/{directory}/{item['name']}",
                          "name": item["name"], "size": item["size"], "git_sha1": item["sha"]})
    return found


def archive_files(url: str, members: dict[str, str]) -> list[dict]:
    """Files out of a zip: ``members`` maps a name pattern's end to the file name it is kept as."""
    data = fetch(url)
    digest = hashlib.sha256(data).hexdigest()
    found = []
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        for info in bundle.infolist():
            for ending, keep in members.items():
                if info.filename.endswith(ending):
                    found.append({"zip": url, "zip_sha256": digest, "member": info.filename,
                                  "name": keep, "size": info.file_size})
    return found


def build() -> dict:
    noto = gh(f"repos/{NOTO_REPOSITORY}/commits/main", ".sha")
    cjk = gh(f"repos/{CJK_REPOSITORY}/commits/main", ".sha")
    packages: dict[str, dict] = {}

    def add(key, title, scripts, files, licence="OFL-1.1", homepage=None, note=None):
        if not files:
            print(f"skipped {key}: nothing found", file=sys.stderr)
            return
        packages[key] = {"title": title, "scripts": tuple(scripts), "license": licence,
                         "homepage": homepage or "", "files": files,
                         "size": sum(item["size"] for item in files), **({"note": note} if note else {})}

    for key, (title, scripts, families) in NOTO_SCRIPTS.items():
        files = []
        for family in families:
            files += raw_files(NOTO_REPOSITORY, noto, f"fonts/{family}/hinted/ttf",
                               lambda name, family=family: name in {f"{family}-{style}.ttf" for style in STYLES})
        add(key, title, scripts, files, homepage="https://notofonts.github.io")

    files = raw_files(NOTO_REPOSITORY, noto, "fonts/NotoNaskhArabic/hinted/ttf",
                      lambda name: name in {f"NotoNaskhArabic-{style}.ttf" for style in ("Regular", "Bold")})
    amiri = archive_files("https://github.com/aliftype/amiri/releases/download/1.003/Amiri-1.003.zip",
                          {f"Amiri-{style}.ttf": f"Amiri-{style}.ttf" for style in ("Regular", "Bold", "Italic", "BoldItalic")})
    add("arabic", "Arabic: Amiri, Noto Naskh Arabic", ("Arab",), amiri + files,
        homepage="https://github.com/aliftype/amiri")

    for key, (title, scripts, language) in CJK.items():
        add(key, title, scripts,
            raw_files(CJK_REPOSITORY, cjk, f"Serif/SubsetOTF/{language}",
                      lambda name, language=language: name == f"NotoSerif{language}-Regular.otf"),
            homepage="https://github.com/notofonts/noto-cjk",
            note="a subset of the Noto CJK fonts, one weight; bold is synthesised")

    for key, (title, scripts, language) in CJK.items():
        add(key.replace("cjk-", "cjk-sans-"), title.replace("Serif", "Sans"), scripts,
            raw_files(CJK_REPOSITORY, cjk, f"Sans/SubsetOTF/{language}",
                      lambda name, language=language: name in (f"NotoSans{language}-Regular.otf",
                                                               f"NotoSans{language}-Bold.otf")),
            homepage="https://github.com/notofonts/noto-cjk", note="a subset of the Noto CJK fonts")

    stix = archive_files("https://mirrors.ctan.org/fonts/stix2-otf.zip",
                         {f"STIXTwoText-{style}.otf": f"STIXTwoText-{style}.otf"
                          for style in ("Regular", "Italic", "Bold", "BoldItalic")}
                         | {"STIXTwoMath-Regular.otf": "STIXTwoMath-Regular.otf"})
    add("stix", "STIX Two Text and Math (pdfmd's default main font)", ("Latn", "Grek", "Cyrl", "Zyyy"), stix,
        homepage="https://github.com/stipub/stixfonts")
    jetbrains = archive_files(
        "https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip",
        {f"fonts/ttf/JetBrainsMono-{style}.ttf": f"JetBrainsMono-{style}.ttf" for style in STYLES})
    add("jetbrains-mono", "JetBrains Mono (pdfmd's default font for code)", ("Latn", "Cyrl", "Grek"), jetbrains,
        homepage="https://www.jetbrains.com/lp/mono/")
    dejavu = archive_files(
        "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip",
        {f"ttf/DejaVu{family}{style}.ttf": f"DejaVu{family}{style}.ttf"
         for family in ("Serif", "Sans", "SansMono")
         for style in ("", "-Bold", "-Italic", "-BoldItalic", "-Oblique", "-BoldOblique")
         if not (family == "Serif" and "Oblique" in style) and not (family != "Serif" and style in ("-Italic", "-BoldItalic"))}
        | {"LICENSE": "DejaVu-LICENSE.txt"})
    add("dejavu", "DejaVu Serif, Sans and Sans Mono: broad coverage of Latin, Cyrillic, Greek, Arabic, Hebrew, "
        "Armenian, Georgian and many symbols", ("Latn", "Cyrl", "Grek", "Arab", "Hebr", "Armn", "Geor", "Zyyy"),
        dejavu, licence="Bitstream-Vera", homepage="https://dejavu-fonts.github.io")

    release = json.loads(fetch("https://pypi.org/pypi/inkmd/0.5.0/json"))
    wheel = next(item for item in release["urls"] if item["filename"].endswith(".whl"))
    emoji = archive_files(wheel["url"], {"inkmd/assets/emoji/NotoColorEmoji.ttf": "NotoColorEmoji.ttf",
                                         "inkmd/assets/emoji/OFL.txt": "NotoColorEmoji-OFL.txt"})
    for item in emoji:
        item["zip_sha256"] = wheel["digests"]["sha256"]
    add("emoji", "Noto Color Emoji (colour emoji; the same font `pdfmd --install emoji` gives the built-in renderer)",
        ("Zyyy",), emoji, homepage="https://github.com/googlefonts/noto-emoji")
    return packages


def render(packages: dict) -> str:
    lines = ['"""The fonts `pdfmd --install fonts` can fetch. GENERATED by scripts/gen_font_catalog.py."""', "",
             "PACKAGES = {"]
    for key in sorted(packages):
        package = packages[key]
        lines.append(f"    {key!r}: {{")
        for field in ("title", "scripts", "license", "homepage", "size", "note"):
            if field in package:
                lines.append(f"        {field!r}: {package[field]!r},")
        lines.append("        'files': (")
        for item in package["files"]:
            lines.append(f"            {item!r},")
        lines.append("        ),")
        lines.append("    },")
    lines += ["}", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="write nothing; say whether the catalog would change")
    args = parser.parse_args()
    text = render(build())
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        print("up to date" if current == text else "would change")
        return 0 if current == text else 1
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET} ({len(text) // 1024} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
