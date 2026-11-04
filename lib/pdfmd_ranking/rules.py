"""The rules of priority: words, classes and the ladder (entry 3eu of the maintainer's notes).

A *class* is a named group of words (`final: [final, last, max]`, `fruit: [cherry, banana]`); the *ladder* puts the classes
in order, low to high, with two reserved members: `unset` (no priority was written) and `numbers` (ranked by their
value). A document's `priority:` value, and a suffix word in its file name (`report.final.md`), both turn into a `Rank` on
that one ladder, so the same classes serve both. The built-in behaviour is the default setting (`DEFAULT_RANKING`), written
the way a user would write it.

Pure: nothing here imports pdfmd. `Ranking.from_layers()` takes the mappings the caller found (nearest first); the caller
knows where they live.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

NAMES_MODES = ("family", "folder", "off")
BY_CRITERIA = ("priority", "newest", "oldest", "name")
RESERVED = ("unset", "numbers")
KNOWN_KEYS = ("ladder", "classes", "names", "by", "inherit")
CLASS_KEYS = ("words", "ordered", "degrees", "exclude", "names", "above", "below")

# What ships. `ordered: false` = every word of the class on one level; a plain list is ordered low -> high, and a nested list is
# one level (`[apple, [banana, cherry]]`). `{n}` in a word stands for a number (`v2`, `rev3`, `version 4`): the higher wins.
DEFAULT_RANKING: dict[str, Any] = {
    "ladder": ["never", "draft", "unset", "revised", "numbers", "final"],
    "classes": {
        "never": {"words": ["never", "ignore", "skip", "exclude"], "ordered": False, "exclude": True},
        "draft": {"words": ["draft", "wip", "old", "backup", "copy", "tmp", "test", "0"], "ordered": False},
        "unset": {"words": ["none", "null", "nil", "nill", "~"], "ordered": False},
        "revised": {"words": ["new", "updated", "rewrite", "rewritten", "revised", "v{n}", "rev{n}", "version {n}"],
                    "ordered": False},
        "final": {"words": ["final", "last", "max"], "ordered": False, "degrees": True},
    },
    "names": "family",
    "by": ["priority", "newest"],
}

_SEPARATORS = re.compile(r"[\s._\-]+")
_MARKS = re.compile(r"[!?'\"“”‘’]+")


class RankingError(ValueError):
    """A ranking setting that cannot be used; the message names the layer it came from."""


def tokenize(text: Any) -> list[str]:
    """The words of a value or a file-name suffix: case folded, `!`, `?` and quotes dropped, split at spaces, `.`, `_`, `-`."""
    text = unicodedata.normalize("NFC", str(text)).casefold()
    return [part for part in _SEPARATORS.split(_MARKS.sub(" ", text)) if part]


def name_key(text: str) -> str:
    """A file-name base reduced to letters and digits (case, separators and accents gone), what two names are compared by."""
    decomposed = unicodedata.normalize("NFKD", str(text)).casefold()
    return "".join(character for character in decomposed if character.isalnum())


@dataclass(frozen=True)
class WordClass:
    name: str
    levels: tuple[tuple[str, ...], ...]       # the words, low -> high; the words of one level are equal
    degrees: bool = False                     # repeated words and a glued number raise the rank (final, FINAL FINAL, final67)
    exclude: bool = False                     # the class of `never`: out of the autodiscovery list
    names: bool = True                        # whether its words count in file names
    above: str | None = None
    below: str | None = None
    where: str = field(default="", compare=False)       # the layer that defined it, for the messages


@dataclass(frozen=True)
class Rank:
    """A place on the ladder. `level` is the ladder level, `cls` the class (or "numbers"/"unset"), `inner` the place inside it."""
    level: int
    cls: str
    inner: tuple = ()
    label: str = ""


def compare(first: Rank, second: Rank) -> int:
    """1 when `first` is higher, -1 when lower, 0 when equal or not comparable (two classes sharing a ladder level)."""
    if first.level != second.level:
        return 1 if first.level > second.level else -1
    if first.cls != second.cls:
        return 0
    return (first.inner > second.inner) - (first.inner < second.inner)


@dataclass(frozen=True)
class Value:
    """What a `priority:` value means: a rank, `excluded` (never), or `invalid` (why)."""
    kind: str
    rank: Rank | None = None
    why: str = ""

    @property
    def label(self) -> str:
        return self.rank.label if self.rank else ""


@dataclass(frozen=True)
class NameParts:
    """A file stem split into the part that names the document (`base`) and the trailing words that name a version."""
    key: str
    base: str
    suffix: str | None = None
    value: Value | None = None


@dataclass
class _Word:
    cls: str
    class_level: int
    text: str
    parts: list                        # per token: a str, or a compiled pattern (a number inside)
    degrees: bool

    def match(self, tokens: Sequence[str], index: int):
        """(tokens used, number or None, count) when the word stands at `index`, else None."""
        if index + len(self.parts) > len(tokens):
            return None
        number = None
        count = 1
        for offset, part in enumerate(self.parts):
            token = tokens[index + offset]
            last = offset == len(self.parts) - 1
            if isinstance(part, str):
                if self.degrees and last:
                    found = re.fullmatch(r"((?:%s)+)(\d*)" % re.escape(part), token)
                    if not found:
                        return None
                    if len(self.parts) == 1:
                        count = len(found.group(1)) // len(part)
                    if found.group(2):
                        number = int(found.group(2))
                elif token != part:
                    return None
            else:
                found = part.fullmatch(token)
                if not found:
                    return None
                number = max(number or 0, int(found.group(1)))
        return len(self.parts), number, count


@dataclass
class _Hit:
    word: _Word
    number: int | None
    count: int
    text: str


def _compile_part(part: str):
    if "{n}" in part:
        return re.compile(re.escape(part).replace(r"\{n\}", r"(\d+)"))
    return part


def _text(value: Any, where: str, what: str) -> str:
    """A word or a name from YAML: text, with the values YAML turns into something else put back (`null` -> "null")."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        raise RankingError(f"{where}: {what} {value!r} was read as a YAML boolean; put it in quotes")
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise RankingError(f"{where}: {what} must be text, not {value!r}")


def parse_class(name: str, spec: Any, where: str) -> WordClass:
    """One class from its YAML: a list of words, or a mapping with `words:` and options."""
    if name in RESERVED and name != "unset":
        raise RankingError(f"{where}: `{name}` is a reserved name of the ladder, not a class of words")
    options: dict = {}
    if isinstance(spec, Mapping):
        unknown = sorted(str(key) for key in spec if key not in CLASS_KEYS)
        if unknown:
            raise RankingError(f"{where}: class {name}: unknown key(s) {', '.join(unknown)}. Valid: {', '.join(CLASS_KEYS)}")
        options = dict(spec)
        words = options.get("words")
    else:
        words = spec
    if not isinstance(words, list) or not words:
        raise RankingError(f"{where}: class {name}: `words` must be a list of words")
    ordered = options.get("ordered", True)
    if ordered is False:
        levels = (tuple(_text(word, where, f"a word of {name}") for word in words if not isinstance(word, list)),)
        if any(isinstance(word, list) for word in words):
            raise RankingError(f"{where}: class {name}: `ordered: false` already puts every word on one level")
    else:
        levels = tuple(
            tuple(_text(inner, where, f"a word of {name}") for inner in word) if isinstance(word, list)
            else (_text(word, where, f"a word of {name}"),)
            for word in words)

    def flag(key: str, default: bool) -> bool:
        value = options.get(key, default)
        if not isinstance(value, bool):
            raise RankingError(f"{where}: class {name}: `{key}` must be true or false")
        return value

    above, below = options.get("above"), options.get("below")
    if above is not None and below is not None:
        raise RankingError(f"{where}: class {name}: give `above` or `below`, not both")
    return WordClass(name, levels, flag("degrees", False), flag("exclude", False), flag("names", True),
                     _text(above, where, "`above`").casefold() if above is not None else None,
                     _text(below, where, "`below`").casefold() if below is not None else None, where)


def _ladder_levels(value: Any, where: str) -> list[list[str]]:
    if not isinstance(value, list) or not value:
        raise RankingError(f"{where}: `ladder` must be a list of class names, low to high")
    levels = []
    for item in value:
        members = item if isinstance(item, list) else [item]
        if not members:
            raise RankingError(f"{where}: `ladder` has an empty level")
        levels.append([_text(member, where, "a class name").casefold() for member in members])
    return levels


def parse_by(value: Any, where: str) -> tuple[str, ...]:
    """The criteria that settle a tie, from a list or from words separated by commas (`priority, newest`)."""
    items = value if isinstance(value, list) else str(value).split(",") if isinstance(value, str) else [value]
    chain = []
    for item in items:
        word = _text(item, where, "a `by` criterion").casefold()
        if word not in BY_CRITERIA:
            raise RankingError(f"{where}: unknown `by` criterion {word!r}. Valid: {', '.join(BY_CRITERIA)}")
        if word not in chain:
            chain.append(word)
    return tuple(chain)


class Ranking:
    """The rules in force: the classes, the ladder, `names` (family, folder, off) and `by` (what settles a tie)."""

    def __init__(self, classes: Mapping[str, WordClass], ladder: list[list[str]], names: str, by: tuple[str, ...],
                 warnings: Sequence[str] = ()):
        self.names = names
        self.by = by
        self.warnings: list[str] = list(warnings)
        self.classes = dict(classes)
        self.ladder = self._place(ladder)
        self.level: dict[str, int] = {member: index for index, members in enumerate(self.ladder) for member in members}
        for reserved in RESERVED:
            if reserved not in self.level:
                raise RankingError(f"the ladder must list `{reserved}` (it is where {'a missing priority' if reserved == 'unset' else 'a number'} stands)")
        self._words = self._compile()
        self.unset = Rank(self.level["unset"], "unset", (), "unset")

    # -- building -------------------------------------------------------------------------------------------------

    @classmethod
    def from_layers(cls, layers: Sequence[tuple[str, Mapping]] = ()) -> "Ranking":
        """The rules from the mappings found, NEAREST FIRST as (where, mapping), over the built-in default. A nearer layer's
        `ladder`, `names` and `by` replace the farther one's; `classes` merge by class name, a class replacing the farther
        class of the same name."""
        warnings: list[str] = []
        classes: dict[str, WordClass] = {}
        ladder: Any = None
        names, by = DEFAULT_RANKING["names"], tuple(DEFAULT_RANKING["by"])
        order = [("built-in", DEFAULT_RANKING), *reversed(list(layers))]
        for where, mapping in order:
            if not isinstance(mapping, Mapping):
                raise RankingError(f"{where}: `ranking` must be a mapping")
            for key in mapping:
                if key not in KNOWN_KEYS:
                    warnings.append(f"{where}: unknown ranking key {key!r} ignored. Valid: {', '.join(KNOWN_KEYS)}")
            if "classes" in mapping:
                if not isinstance(mapping["classes"], Mapping):
                    raise RankingError(f"{where}: `classes` must be a mapping of class name to words")
                for raw_name, spec in mapping["classes"].items():
                    name = _text(raw_name, where, "a class name").casefold()
                    classes[name] = parse_class(name, spec, where)
            if "ladder" in mapping:
                ladder = _ladder_levels(mapping["ladder"], where)
            if "names" in mapping:
                raw = mapping["names"]
                names = ("off" if raw is False else "family" if raw is True      # YAML reads `off` as false
                         else _text(raw, where, "`names`").casefold())
                if names not in NAMES_MODES:
                    raise RankingError(f"{where}: `names` must be one of {', '.join(NAMES_MODES)}, not {names!r}")
            if "by" in mapping:
                by = parse_by(mapping["by"], where)
        return cls(classes, ladder, names, by, warnings)

    def _place(self, ladder: list[list[str]]) -> list[list[str]]:
        """The ladder with the classes that say `above:`/`below:` put where they ask (a class listed on the ladder as well is
        moved); a class that is nowhere is dropped, with a warning. A class with an unknown target is an error."""
        levels = [list(members) for members in ladder]
        for members in levels:
            for member in members:
                if member not in self.classes and member not in RESERVED:
                    raise RankingError(f"the ladder names {member!r}, which is not a class (and not unset or numbers)")
        if len({member for members in levels for member in members}) != sum(len(members) for members in levels):
            raise RankingError("a class appears twice on the ladder")
        movers = [wc for wc in self.classes.values() if wc.above or wc.below]
        for wc in movers:
            for members in levels:
                if wc.name in members:
                    members.remove(wc.name)
            levels = [members for members in levels if members]
        pending = list(movers)
        while pending:
            progress = False
            groups: dict[tuple[str, str], list[WordClass]] = {}
            for wc in pending:
                direction, target = ("above", wc.above) if wc.above else ("below", wc.below)
                if target not in self.classes and target not in RESERVED:
                    raise RankingError(f"{wc.where}: class {wc.name}: `{direction}: {target}` names no class")
                if any(target in members for members in levels):
                    groups.setdefault((direction, target), []).append(wc)
            for (direction, target), members in groups.items():
                index = next(i for i, level in enumerate(levels) if target in level)
                levels.insert(index + 1 if direction == "above" else index, [wc.name for wc in members])
                pending = [wc for wc in pending if wc not in members]
                progress = True
            if not progress:
                break
        for wc in pending:
            self.warnings.append(f"class {wc.name} cannot be placed ({'above' if wc.above else 'below'} "
                                 f"{wc.above or wc.below} is not on the ladder); its words are ignored")
        self.classes = {name: wc for name, wc in self.classes.items() if wc not in pending}
        placed = {member for members in levels for member in members}
        for wc in list(self.classes.values()):
            if wc.name not in placed and not wc.exclude:
                self.warnings.append(f"class {wc.name} is not on the ladder and has no `above:`/`below:`; its words are ignored")
                del self.classes[wc.name]
        return levels

    def _compile(self) -> list[_Word]:
        words: list[_Word] = []
        seen: dict[str, str] = {}
        for wc in self.classes.values():
            for class_level, level in enumerate(wc.levels):
                for text in level:
                    parts = tokenize(text.replace("{n}", "①"))
                    parts = [part.replace("①", "{n}") for part in parts]
                    if not parts:
                        raise RankingError(f"class {wc.name}: the word {text!r} has no letters or digits")
                    key = " ".join(parts)
                    if key in seen and seen[key][0] != wc.name:
                        raise RankingError(f"the word {text!r} is in two classes: {seen[key][0]} ({seen[key][1]}) and "
                                           f"{wc.name} ({wc.where})")
                    seen[key] = (wc.name, wc.where)
                    words.append(_Word(wc.name, class_level, text.casefold(), [_compile_part(part) for part in parts], wc.degrees))
        words.sort(key=lambda word: -len(word.parts))
        return words

    def describe(self) -> list[str]:
        """The rules as lines, low to high (`pdfmd --which`): one per class or reserved member, words low < high, equal ones joined by =."""
        lines = []
        for members in self.ladder:
            for member in members:
                if member == "numbers":
                    lines.append("numbers  0, 1, 2 ... by value; a negative number is the same as never")
                elif member == "unset":
                    words = " = ".join(word for level in self.classes["unset"].levels for word in level) if "unset" in self.classes else ""
                    lines.append(f"unset    no priority written ({words})")
                else:
                    wc = self.classes[member]
                    words = " < ".join(" = ".join(level) for level in wc.levels)
                    flags = [text for flag, text in ((wc.exclude, "leaves the list"), (wc.degrees, "degrees: repeats and a glued number count"),
                                                    (not wc.names, "not read in file names")) if flag]
                    lines.append(f"{member:<8} {words}" + (f"  ({'; '.join(flags)})" if flags else ""))
            if len(members) > 1:
                lines.append(f"         (the {len(members)} classes above share one level)")
        return lines

    # -- reading --------------------------------------------------------------------------------------------------

    def _segment(self, tokens: Sequence[str], words: Sequence[_Word]) -> list[_Hit] | None:
        """The tokens read completely as words of the classes, or None."""
        cache: dict[int, Any] = {}

        def go(index: int):
            if index == len(tokens):
                return []
            if index in cache:
                return cache[index]
            found = None
            for word in words:
                matched = word.match(tokens, index)
                if matched:
                    used, number, count = matched
                    rest = go(index + used)
                    if rest is not None:
                        found = [_Hit(word, number, count, " ".join(tokens[index:index + used]))] + rest
                        break
            cache[index] = found
            return found

        return go(0)

    def _from_hits(self, hits: list[_Hit]) -> Value:
        if any(self.classes[hit.word.cls].exclude for hit in hits):
            first = next(hit for hit in hits if self.classes[hit.word.cls].exclude)
            return Value("excluded", Rank(-1, first.word.cls, (), first.text))
        top = max(hits, key=lambda hit: self.level.get(hit.word.cls, -1))
        same = [hit for hit in hits if hit.word.cls == top.word.cls]
        wc = self.classes[top.word.cls]
        numbers = [hit.number for hit in same if hit.number is not None]
        sub = max([sum(hit.count for hit in same) if wc.degrees else 0, *numbers])
        label = top.word.text + (f" x{sub}" if sub > 1 else "") if wc.degrees else top.text
        return Value("rank", Rank(self.level[wc.name], wc.name, (max(hit.word.class_level for hit in same), sub), label))

    def read(self, raw: Any) -> Value:
        """What a `priority:` value written in a document means."""
        if raw is None:
            return Value("rank", self.unset)
        if isinstance(raw, bool):
            return Value("invalid", why="a yes/no is not a priority; use a number or a word")
        number = None
        if isinstance(raw, (int, float)):
            number = float(raw)
            if not math.isfinite(number):
                return Value("invalid", why="not a finite number")
            text = str(int(number)) if number == int(number) else repr(raw)
        else:
            text = str(raw).strip()
            if not text:
                return Value("rank", self.unset)
            try:
                number = float(text)
            except ValueError:
                number = None
            if number is not None and not math.isfinite(number):
                return Value("invalid", why="not a finite number")
        tokens = tokenize(text)
        hits = self._segment(tokens, self._words) if tokens else None
        if hits:
            value = self._from_hits(hits)
            if value.rank is not None and value.rank.cls == "unset":
                return Value("rank", self.unset)
            return value
        if number is not None:
            if number < 0:
                return Value("excluded", Rank(-1, "never", (), text))
            return Value("rank", Rank(self.level["numbers"], "numbers", (number,), text))
        return Value("invalid", why="neither a number nor a word of any class")

    def name_parts(self, stem: str) -> NameParts:
        """Split a file stem into its base and a trailing version suffix (`report.final` -> report + final)."""
        tokens = [part for part in _SEPARATORS.split(unicodedata.normalize("NFC", stem).casefold()) if part]
        usable = [word for word in self._words if self.classes[word.cls].names and word.cls != "unset"]
        for start in range(1, len(tokens)):
            hits = self._segment(tokens[start:], usable)
            if hits:
                base = tokens[:start]
                return NameParts(name_key("".join(base)), " ".join(base), " ".join(tokens[start:]), self._from_hits(hits))
        return NameParts(name_key("".join(tokens)), " ".join(tokens))
