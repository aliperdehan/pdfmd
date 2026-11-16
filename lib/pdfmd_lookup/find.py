"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_lookup.find`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

from pdfmd_base import core
from pdfmd_lookup import LOOKUP_FIELD_WORDS


LOOKUP_SCAN_LIMIT = 500    # Markdown files whose front matter is read


# Russian, Ukrainian, Belarusian and Kazakh Cyrillic. Kazakh қ = q, ғ = g,
# ң = n, ә = a, ө = o, ұ and ү = u, һ = h, і = i.
CYRILLIC_STRICT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "є": "ye", "і": "i", "ї": "yi", "ґ": "g", "ў": "u",
    "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h",
}


# The loose key starts from the same transliteration, with ё read as е; the
# Latin letters it produces are then merged (see lookup_key).
CYRILLIC_LOOSE = {**CYRILLIC_STRICT, "ё": "e"}


# Latin letters NFKD cannot take apart, spelt the way the Cyrillic sound is.
LATIN_EXTRA = {"ş": "sh", "š": "sh", "ç": "ch", "č": "ch", "ž": "zh", "ğ": "g", "ı": "i",
               "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "đ": "d", "ł": "l"}


def set_translit(spec: str | None) -> list[str]:
    """Choose the romanization packs from a --translit / PDFMD_TRANSLIT value: names separated by
    commas or spaces, `all`, or `none` (Cyrillic off too). Returns problems to report."""
    problems: list[str] = []
    packs: set[str] = set()
    core.TRANSLIT_CYRILLIC = True
    module = core.unicode_module()
    known = module.translit.PACKS if module else ()
    for word in re.split(r"[,\s]+", (spec or "").strip().casefold()):
        if not word:
            continue
        if word == "none":
            packs.clear()
            core.TRANSLIT_CYRILLIC = False
        elif word == "all":
            packs.update(known)
        elif word == "cyrillic":
            core.TRANSLIT_CYRILLIC = True
        elif word in known:
            packs.add(word)
        else:
            problems.append(f"unknown romanization pack {word!r}; choose from cyrillic (always on), "
                            f"{', '.join(known) or 'none installed'}, all, none")
    for pack in sorted(packs):
        if not module.translit.available(pack):
            problems.append(f"the {pack} pack needs a library: {module.translit.needs(pack)} "
                            "(pdfmd --install translit)")
            packs.discard(pack)
    core.TRANSLIT_PACKS = frozenset(packs)
    core.lookup_key.cache_clear()
    return problems


def lookup_wording(tier: tuple, words: dict) -> str | None:
    """What to say a guessed match matched on; None for an exact one that only
    differs in case, separators and script (strict exact tiers)."""
    strength, fields, how = tier
    if strength == "strict" and how == "exact":
        return None
    names = " or ".join(words[field] for field in fields if field in words)
    phrase = {"exact": f"spelt differently from its {names}", "start": f"the start of its {names}",
              "word": f"the start of a word in its {names}"}[how]
    return phrase + (", spelt differently" if strength == "loose" and how != "exact" else "")


def lookup_entries(directory: Path, recursive: bool) -> list[tuple[Path, list[tuple[str, str]]]]:
    folders = [directory] + ([item for item in directory.rglob("*") if item.is_dir()] if recursive else [])
    files = sorted(file for folder in folders for file in folder.glob("*.md")
                   if not file.name.startswith(".") and file.is_file())
    return [(file, core.lookup_fields(file)) for file in files[:LOOKUP_SCAN_LIMIT]]


_LOOKUP_ANNOUNCED: set[tuple[str, str]] = set()


def skip_never(files: list[Path], include_never: bool = False) -> list[Path]:
    """``files`` without the documents that say `priority: never` (or another word of a class with `exclude`), which are named in
    one NOTE: what `-b`, `-r` and the viewer list from a folder. ``include_never`` (`--all`) keeps them, and so does
    `--no-auto priority`. A document named on the command line is never dropped: the callers pass only what a folder gave them."""
    if include_never:
        return files
    from pdfmd_ranking import MISSING
    by_folder: dict[Path, list[Path]] = {}
    for file in files:
        by_folder.setdefault(file.parent, []).append(file)
    dropped: list[Path] = []
    for folder_files in by_folder.values():
        if not core.priority_enabled(folder_files[0].parent):
            continue
        values = {file: core.document_priority(file) for file in folder_files}
        if all(value is MISSING for value, _ in values.values()):
            continue
        try:
            ranking = core.bare_ranking(folder_files)
        except Exception as error:
            print(f"WARN  ranking: {error}; every document of {core.display_path(folder_files[0].parent)} is kept", file=sys.stderr)
            continue
        for file, (value, _) in values.items():
            if value is not MISSING and ranking.read(value).kind == "excluded":
                dropped.append(file)
    if dropped:
        print(f"NOTE  left out (priority: never): {', '.join(core.display_path(file) for file in dropped)}  (--all builds them too)")
    return [file for file in files if file not in dropped]


def choose_markdown(files: list[Path], newest: bool = False, include_never: bool = False) -> Path:
    """The one of several Markdown files of a folder that bare `pdfmd` builds; says so (an AUTO MD line, WARNs), or stops with
    the reason (SystemExit) when equal documents cannot be told apart. ``newest`` (`--newest`): by modification time alone;
    ``include_never`` (`--all`): the documents that say `never` take part as if they had said nothing."""
    from pdfmd_ranking import RankingError, choose
    candidates = core.priority_candidates(files)
    try:
        ranking = core.bare_ranking(files)
    except RankingError as error:
        raise SystemExit(f"ranking: {error}")
    choice = choose(candidates, ranking, by=["newest"] if newest else None, show=core.display_path, include_excluded=include_never)
    for line in [f"WARN  ranking: {text}" for text in ranking.warnings] + choice.warnings:
        print(line, file=sys.stderr)
    if choice.error or choice.winner is None:
        raise SystemExit(choice.error or "No Markdown file could be chosen.")
    beaten = choice.beaten(core.display_path)
    print(f"AUTO MD    {core.display_path(choice.winner)}" + (f"  (over {beaten})" if beaten else ""))
    return choice.winner


def find_markdown(value: Path, recursive: bool = False) -> Path:
    # Always resolved to an absolute path: a relative path with a subdirectory
    # component (e.g. "sub/nested.md") would otherwise make Pandoc's cwd (set
    # to md_path.parent, so relative includes/images in the document resolve
    # correctly) and its source-file argument both relative to the ORIGINAL
    # cwd, which -- once the subprocess actually changes into that directory
    # -- silently doubles up into a nonexistent path (e.g. "sub/sub/nested.md").
    if value.exists() and value.is_file():
        return value.resolve()
    wildcard_match = core.find_wildcard_markdown(value)
    if wildcard_match:
        return wildcard_match.resolve()
    directory = value if value.is_dir() else Path.cwd()
    requested = core.strip_lookup_suffix(value.name)
    search_dirs = [directory]
    if recursive:
        search_dirs = [directory] + [item for item in directory.rglob("*") if item.is_dir()]
    files = {
        unicodedata.normalize("NFC", file.stem).casefold(): file
        for folder in search_dirs for file in folder.glob("*.md")
    }
    for candidate in core.name_candidates(requested):
        normalized = unicodedata.normalize("NFC", candidate).casefold()
        if normalized in files:
            return files[normalized].resolve()
    if core.FUZZY_LOOKUP and requested and not value.is_dir():
        fuzzy_directory = value.parent if value.parent.is_dir() and str(value.parent) != "." else Path.cwd()
        found = core.rank_lookup(requested, lookup_entries(fuzzy_directory, recursive))
        if found:
            announce_lookup(requested, core.display_path(found[0]), *found[1:])
            return found[0].resolve()
    available = ", ".join(sorted(files))
    raise FileNotFoundError(f"Could not find Markdown file for '{value}'. Available: {available or 'none'}")


def announce_lookup(query: str, shown: str, tier: tuple, field: str, text: str,
                    words: dict = LOOKUP_FIELD_WORDS, subject: str = "file name") -> None:
    """Say, once per run, that something was found by other than its exact
    name: a plain AUTO line when only case, separators and script differ, a
    WARN for anything that guessed (a start, a word, a looser spelling)."""
    if (query, shown) in _LOOKUP_ANNOUNCED:
        return
    _LOOKUP_ANNOUNCED.add((query, shown))
    what = "file name" if field == "stem" and subject == "file name" else f"{words[field]} '{text}'"
    wording = lookup_wording(tier, words)
    if wording is None:
        # Naming a heading without its exact case or spaces is the normal way to
        # ask for one; only a file name found that way is worth a line.
        if subject == "file name":
            print(f"AUTO MD    {shown}  ('{query}' = its {what}, ignoring case, spaces and punctuation)")
        return
    print(f"WARN  '{query}' is not a {subject}; using {shown} ({wording}: {what}). "
          "Name it exactly, or pass --no-auto lookup, to stop pdfmd guessing.", file=sys.stderr)

