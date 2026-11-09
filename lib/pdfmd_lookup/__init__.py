"""Finding a document by its name: the Latin and Cyrillic spellings of a name, a wildcard, the comparison keys (`lookup_key`), the tiers
that rank a name against file names, titles and aliases (`rank_lookup`, `LookupAmbiguous` when two fit equally well), what a
document can be found by (`lookup_fields`), and the document's own `priority:` with what decides whether bare `pdfmd` chooses by it
(`document_priority`, `priority_enabled`, `source_markdown`).

Moved out of `pdfmd.py` unchanged (v3.33.20, SPLIT.md), with `LOOKUP_MIN_PREFIX`, `LOOKUP_HEAD_BYTES`, `GENERATED_MARKDOWN_ENDINGS`, and
`LOOKUP_TIERS` and `LOOKUP_FIELD_WORDS` (which `rank_lookup` takes as the defaults of its parameters, so they have to exist when the
module is imported; `pdfmd.py` re-exports them). `core` is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first binding
wins); the pdfmd names the code uses (`CYRILLIC_LOOSE`, `CYRILLIC_STRICT`, `LATIN_EXTRA`, `NO_AUTO_CLI`, `TRANSLIT_CYRILLIC`,
`TRANSLIT_PACKS`, `auto_disabled`, `config_options`, `display_path`, `folder_auto_safe`, `folder_layers`, `is_assembled_document`,
`resolve_auto`, `unicode_module` and `yaml`, pdfmd's own optional import) are read as `core.X` when it runs, so the state that
`set_translit` and `main` rebind (`TRANSLIT_*`, `NO_AUTO_CLI`) is always the current one. `CYRILLIC_LOOSE` stays in `pdfmd.py`: it is built from
`CYRILLIC_STRICT` when that file is loaded. `core.config_options` is patched by tests as `pdfmd.config_options`.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path

core = None


def latin_candidates(value: str) -> list[str]:
    """Return common Cyrillic spellings for a Latin name."""
    value = value.lower()
    replacements = (
        ("shch", "щ"), ("sch", "щ"), ("yo", "ё"), ("zh", "ж"),
        ("kh", "х"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
        ("yu", "ю"), ("ya", "я"), ("ai", "ай"), ("oi", "ой"), ("oy", "ой"),
    )
    variants = [value]
    for latin, cyrillic in replacements:
        variants = [item.replace(latin, cyrillic) for item in variants]
    letter_map = str.maketrans({
        "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф",
        "g": "г", "h": "х", "i": "и", "j": "й", "k": "к", "l": "л",
        "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
        "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс",
        "y": "ы", "z": "з",
    })
    variants += [item.translate(letter_map) for item in variants]
    variants.append(value.translate(letter_map))
    variants.append(value.replace("ai", "ай").translate(letter_map))
    variants.append(value.replace("ai", "аи").translate(letter_map))
    return list(dict.fromkeys(variants))


def cyrillic_candidates(value: str) -> list[str]:
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "shch", "ы": "y", "э": "e", "ю": "yu",
        "я": "ya",
    }
    return ["".join(table.get(letter, letter) for letter in value.lower())]


def strip_lookup_suffix(name: str) -> str:
    """Drop a trailing .md/.markdown/.pdf from a bare-name lookup, and nothing
    else. Path.stem would also eat a dot that is part of the name itself, so
    'prelab5.5' silently resolved to prelab5.md instead of prelab5.5.md."""
    path = Path(name)
    return path.stem if path.suffix.lower() in {".md", ".markdown", ".pdf"} else name


def find_wildcard_markdown(value: Path) -> Path | None:
    """Resolve one case-insensitive wildcard pattern to a Markdown file."""
    pattern = value.name
    if not any(character in pattern for character in "*?["):
        return None
    directory = value.parent if str(value.parent) not in {"", "."} else Path.cwd()
    if not directory.is_dir():
        return None

    # Without an extension, match the Markdown stem, so '*scrutiny' naturally
    # finds 'CAS001-CAS002-CAS003_cassirer_scrutiny.md'.
    match_name = bool(Path(pattern).suffix)
    normalized_pattern = pattern.casefold()
    matches = [file for file in directory.glob("*.md")
               if fnmatchcase((file.name if match_name else file.stem).casefold(), normalized_pattern)]
    if not matches:
        raise FileNotFoundError(f"No Markdown file matches wildcard pattern '{value}'")
    if len(matches) > 1:
        names = ", ".join(file.name for file in sorted(matches))
        raise FileNotFoundError(f"Wildcard pattern '{value}' matches multiple Markdown files: {names}")
    return matches[0]


LOOKUP_MIN_PREFIX = 3      # a shorter start is too likely to be an accident
LOOKUP_HEAD_BYTES = 65536


@lru_cache(maxsize=None)
def lookup_key(text: str, loose: bool = False, y: str = "i", w: str = "v") -> str:
    """The comparison key of a name, title or heading (see the block comment
    above). A loose key then merges what people swap when typing a name in the
    other script or on a keyboard without the letter: sh/sch/shch/ş/ш/щ = s,
    zh/ž/ж = z, ch/ç/ч = k, kh/х = h, c/q/k/қ = k, j/y = i (nothing before a
    vowel: ю = yu = u), w/v = v, x = ks, and a doubled letter is one. ``y``/``w`` choose what a Latin y or w stands
    for: у is written y in some Kazakh Latin spellings and w in others, so a
    query tries both (lookup_query_keys) where a stored name has no choice."""
    text = unicodedata.normalize("NFKC", text).casefold()
    if core.TRANSLIT_PACKS:
        text = core.unicode_module().translit.romanize(text, core.TRANSLIT_PACKS).casefold()
    table = (core.CYRILLIC_LOOSE if loose else core.CYRILLIC_STRICT) if core.TRANSLIT_CYRILLIC else {}
    text = "".join(table.get(letter, core.LATIN_EXTRA.get(letter, letter)) for letter in text)
    letters = "".join(letter for letter in unicodedata.normalize("NFKD", text) if letter.isalnum())
    if not loose:
        return letters
    for digraph, merged in (("shch", "s"), ("sch", "s"), ("sh", "s"), ("zh", "z"), ("ch", "k"), ("kh", "h"),
                            ("ph", "f")):
        letters = letters.replace(digraph, merged)
    letters = re.sub(r"[yj](?=[aeiou])", "", letters)   # ю/я/ё/є: yu, ya, yo, ye ~ u, a, o, e
    letters = letters.translate(str.maketrans({"c": "k", "q": "k", "j": "i", "x": "ks", "y": y, "w": w}))
    return re.sub(r"(.)\1+", r"\1", letters)


def lookup_query_keys(query: str) -> tuple[str, set[str]]:
    """(strict key, every loose key) of what the user typed."""
    loose = {lookup_key(query, True, y, w) for y in ("i", "u") for w in ("v", "u")}
    return lookup_key(query), loose


class LookupAmbiguous(FileNotFoundError):
    """A name that fits several documents equally well. A FileNotFoundError so
    every caller that already handles a missing document handles this; callers
    that would swallow it as "no document" catch this one first."""


# (strength, fields compared, how) in order of preference: the first tier with
# a hit decides, two hits in it are an error. A file name or an alias is
# preferred to a title at every step, and exact to a start to a word. The same
# tiers rank headings (an explicit {#id} counts as an alias, the heading text as
# the name), so `doc#onlyapart` and `pdfmd onlyapart` agree about spelling.
LOOKUP_TIERS = (
    ("strict", ("alias",), "exact"),
    ("strict", ("stem",), "exact"),
    ("strict", ("title",), "exact"),
    ("loose", ("alias",), "exact"),
    ("loose", ("stem",), "exact"),
    ("loose", ("title",), "exact"),
    ("strict", ("alias", "stem"), "start"),
    ("strict", ("title",), "start"),
    ("loose", ("alias", "stem"), "start"),
    ("loose", ("title",), "start"),
    ("strict", ("alias", "stem", "title"), "word"),
    ("loose", ("alias", "stem", "title"), "word"),
)
LOOKUP_FIELD_WORDS = {"alias": "alias", "stem": "file name", "title": "title"}


def lookup_field_matches(strength: str, how: str, queries: tuple[str, set[str]], text: str) -> bool:
    loose = strength == "loose"
    wanted = queries[1] if loose else {queries[0]}
    if how == "exact":
        return lookup_key(text, loose) in wanted
    wanted = {key for key in wanted if len(key) >= LOOKUP_MIN_PREFIX}
    if not wanted:
        return False
    if how == "start":
        return lookup_key(text, loose).startswith(tuple(wanted))
    words = re.split(r"[\W_]+", text)
    return any(lookup_key(" ".join(words[index:]), loose).startswith(tuple(wanted))
               for index in range(1, len(words)))


def rank_lookup(query: str, entries: list[tuple], describe=None, words: dict = LOOKUP_FIELD_WORDS,
                tiers: tuple = LOOKUP_TIERS):
    """Choose among ``entries`` -- (key, [(field, text)]) with field one of
    alias/stem/title -- by LOOKUP_TIERS. Returns (key, tier, field, text), or
    None; raises LookupAmbiguous when the best tier holds several entries.
    ``describe`` names an entry's key in that error (default: a file path)."""
    describe = describe or core.display_path
    queries = lookup_query_keys(query)
    if not queries[0]:
        return None
    for tier in tiers:
        strength, fields, how = tier
        hits: dict = {}
        for key, texts in entries:
            for field, text in texts:
                if field in fields and key not in hits and lookup_field_matches(strength, how, queries, text):
                    hits[key] = (field, text)
        if len(hits) == 1:
            key, (field, text) = next(iter(hits.items()))
            return key, tier, field, text
        if hits:
            names = ", ".join(f"{describe(key)} ({words[field]} '{text}')"
                              for key, (field, text) in sorted(hits.items()))
            raise LookupAmbiguous(f"'{query}' fits several equally well: {names}. "
                                  "Name one of them more exactly.")
    return None


def lookup_fields(path: Path) -> list[tuple[str, str]]:
    """What a document can be found by: its file name, its title (front matter
    `title:`, or a `% title` line) and its aliases (`pdfmd-options: {alias: ...}`,
    one name or a list; a bare top-level `pdfmd-title:` is accepted too)."""
    fields = [("stem", path.stem)]
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
            head = handle.read(LOOKUP_HEAD_BYTES)
    except OSError:
        return fields
    title: object = None
    aliases: list = []
    front = re.match(r"^---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", head, re.DOTALL)
    if front:
        data = None
        if core.yaml is not None:
            try:
                data = core.yaml.safe_load(front.group(1))
            except core.yaml.YAMLError:
                data = None
        if isinstance(data, dict):
            title = data.get("title")
            options = data.get("pdfmd-options")
            options = options if isinstance(options, dict) else {}
            for value in (options.get("alias"), options.get("aliases"), data.get("pdfmd-title")):
                aliases += value if isinstance(value, list) else [value]
        else:
            for key in ("title", "pdfmd-title"):
                found = re.search(rf"^{key}\s*:\s*(.+?)\s*$", front.group(1), re.MULTILINE)
                if found:
                    value = found.group(1).strip("'\"")
                    if key == "title":
                        title = value
                    else:
                        aliases.append(value)
    elif head.startswith("% "):
        title = head.split("\n", 1)[0][2:]
    if isinstance(title, (str, int, float)) and not isinstance(title, bool) and str(title).strip():
        fields.append(("title", str(title).strip()))
    fields += [("alias", str(alias).strip()) for alias in aliases
               if isinstance(alias, (str, int, float)) and not isinstance(alias, bool) and str(alias).strip()]
    return fields


# What pdfmd itself writes beside a source when it stops at Markdown or writes flat Markdown: `report.assembled.md`
# (--stop-at markdown), `report.gfm.md` (--to gfm), `report.ascii.md`, `report.ascii.gfm.md`. They are named like documents
# but are the output of one, so bare pdfmd never chooses among them (the newest of a folder would be the last build's output).
GENERATED_MARKDOWN_ENDINGS = (".ascii.gfm", ".assembled", ".gfm", ".ascii")


def priority_enabled(folder: Path) -> bool:
    """Whether bare pdfmd in ``folder`` chooses by priority: `priority` is not switched off by `--no-auto` or by the folder's
    layers (`.pdfmd/config.yaml`, `.pdfmd/metadata.yaml`, the config file): `options: {no-auto: [priority]}`, `auto: {priority: off}`.
    A document's own front matter has no say: no document is chosen yet."""
    # the layers of effective_no_auto(), for no document: the command line, an empty document, the folders, the config
    stand_in = folder / ".pdfmd-folder.md"
    above = [(where, core.folder_auto_safe(options, where)) for where, options in core.folder_layers(stand_in)]
    layers: list[tuple[object, dict]] = [(stand_in, {"no-auto": core.NO_AUTO_CLI or True} if core.NO_AUTO_CLI is not None else {}), (stand_in, {}),
                                         *above, ("config", core.config_options())]
    return not core.auto_disabled(core.resolve_auto(layers, len(above)), "priority")


def source_markdown(files: list[Path]) -> list[Path]:
    """``files`` without what pdfmd wrote itself (GENERATED_MARKDOWN_ENDINGS beside their source, any assembled file, any
    hidden file such as the temporary `.name.pdfmd-*.md`). All of them are kept if that leaves none."""
    names = {file.name.casefold() for file in files}
    kept = []
    for file in files:
        if file.name.startswith("."):
            continue
        lowered = file.stem.casefold()
        if any(lowered.endswith(ending) and len(lowered) > len(ending) and lowered[:-len(ending)] + ".md" in names
               for ending in GENERATED_MARKDOWN_ENDINGS):
            continue
        if core.is_assembled_document(file):
            continue
        kept.append(file)
    return kept or files


def document_priority(path: Path):
    """(value, where) of the priority a document's front matter sets: `pdfmd-options: {priority: ...}` or a root `priority:`
    (the first wins, with a WARN when they differ); (MISSING, "") when it sets none. Only the head of the file is read."""
    from pdfmd_ranking import MISSING
    if core.yaml is None:
        return MISSING, ""
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
            head = handle.read(LOOKUP_HEAD_BYTES)
    except OSError:
        return MISSING, ""
    front = re.match(r"^---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", head, re.DOTALL)
    if not front:
        return MISSING, ""
    try:
        data = core.yaml.safe_load(front.group(1))
    except core.yaml.YAMLError:
        return MISSING, ""
    if not isinstance(data, dict):
        return MISSING, ""
    options = data.get("pdfmd-options")
    options = options if isinstance(options, dict) else {}
    if "priority" in options:
        if "priority" in data and str(data["priority"]) != str(options["priority"]):
            print(f"WARN  {core.display_path(path)}: priority is set twice ({data['priority']!r} and pdfmd-options "
                  f"{options['priority']!r}); using the one in pdfmd-options", file=sys.stderr)
        return options["priority"], "pdfmd-options priority"
    if "priority" in data:
        return data["priority"], "priority"
    return MISSING, ""
