"""The preamble a kit writes, and what happens where the user's own LaTeX says the same thing (entry 3du, point 9).

The kit's lines come FIRST (`\\usepackage[<mode options>]{package}`, then its `\\input`s and other lines), the user's text
after, so a house package is loaded before the settings that use it. The user's text is scanned, in the BUILD COPY only (a
user's file is never edited), for lines the kit already writes:

1. the same line (the package with options the kit already gives, or the same `\\input{...}`): dropped, silently;
2. extra options (`[qca]` against `[qca,draft]`): merged into the kit's one line, the later line dropped;
3. a CONTRADICTION (an option that belongs to another mode of the same kit): a preamble found in the folder yields to the kit
   with a WARN, its line commented out; an explicit source (`header-includes:`, `--include-in-header`, a named preamble)
   stops the build naming both sides;
4. anything else (fonts, `\\labsetup`, macros of one's own) is left where it is, after the kit's lines.

Only a whole line `\\usepackage[...]{name}` (options may span lines; `\\RequirePackage` too) and a whole line `\\input{...}`
are rewritten. The kit's package behind a macro or inside a list (`\\usepackage{a,nulabreport}`) is never guessed at: the
build stops and names the line. Every outcome has an id, for the day messages have levels: KIT-SAME, KIT-MERGE, KIT-YIELD.

Pure: no pdfmd import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PACKAGE_LINE = re.compile(r"^[ \t]*\\(?:usepackage|RequirePackage)\s*(?:\[([^\]]*)\])?\s*\{([^{}]*)\}[ \t]*(?:%[^\n]*)?$", re.MULTILINE)
PACKAGE_LOOSE = re.compile(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
INPUT_LINE = re.compile(r"^[ \t]*\\input\s*\{([^{}]*)\}[ \t]*(?:%[^\n]*)?$", re.MULTILINE)
INPUT_OF_KIT = re.compile(r"^\s*\\input\s*\{([^{}]*)\}\s*(?:%.*)?$")


class PreambleClash(Exception):
    """The kit and an explicit source of LaTeX contradict each other, or a line cannot be read safely; the build stops."""


@dataclass
class Source:
    name: str                 # said in messages: a path, "header-includes of the document" ...
    text: str
    explicit: bool            # False: found in the folder (yields to the kit); True: asked for (stops the build)


@dataclass
class Event:
    id: str                   # KIT-SAME | KIT-MERGE | KIT-YIELD
    source: str
    line: str
    message: str
    warn: bool = False


@dataclass
class Resolution:
    options: tuple[str, ...]
    texts: list[str]
    events: list[Event] = field(default_factory=list)


def options_of(text: str | None) -> list[str]:
    return [part.strip() for part in re.split(r"[,\n]", text or "") if part.strip() and not part.strip().startswith("%")]


def blank_comments(text: str) -> str:
    """``text`` with every `%` comment replaced by spaces, so that positions stay the same."""
    out = []
    for line in text.split("\n"):
        cut = next((i for i, ch in enumerate(line) if ch == "%" and (i == 0 or line[i - 1] != "\\")), None)
        out.append(line if cut is None else line[:cut] + " " * (len(line) - cut))
    return "\n".join(out)


def input_name(text: str) -> str:
    name = text.strip()
    return name[:-4] if name.endswith(".tex") else name


def kit_inputs(lines: list[str]) -> frozenset[str]:
    return frozenset(input_name(match.group(1)) for line in lines if (match := INPUT_OF_KIT.match(line)))


def package_line(package: str, options: tuple[str, ...]) -> str:
    return f"\\usepackage[{','.join(options)}]{{{package}}}" if options else f"\\usepackage{{{package}}}"


def resolve(label: str, package: str, options: tuple[str, ...], foreign: frozenset[str], inputs: frozenset[str],
            sources: list[Source]) -> Resolution:
    """Scan ``sources`` for what the kit ``label`` already writes (see the module's docstring). ``package`` may be empty (a kit
    that writes no package line); ``foreign`` are options of other modes of the kit; ``inputs`` are the names the kit
    `\\input`s. Raises PreambleClash for a contradiction in an explicit source or a package line of a shape it will not guess."""
    final = list(options)
    events: list[Event] = []
    texts: list[str] = []
    for source in sources:
        text = source.text
        if package:
            bare = blank_comments(text)
            whole = [match.span() for match in PACKAGE_LINE.finditer(bare)]
            for loose in PACKAGE_LOOSE.finditer(bare):
                names = [name.strip() for name in loose.group(1).split(",")]
                if package in names and not any(start <= loose.start() and loose.end() <= end for start, end in whole):
                    line = text[:loose.start()].count("\n") + 1
                    raise PreambleClash(f"{source.name}, line {line}: `{text[loose.start():loose.end()]}` loads the package of kit "
                                        f"{label} in a shape pdfmd will not guess at; write it as its own line, "
                                        f"`\\usepackage[options]{{{package}}}`, or leave it to the kit")

            def package_replacement(match: re.Match) -> str:
                names = [name.strip() for name in match.group(2).split(",")]
                if names != [package]:
                    if package in names:
                        raise PreambleClash(f"{source.name}: `{match.group(0).strip()}` loads the package of kit {label} together "
                                            f"with others; give it its own `\\usepackage` line, or leave it to the kit")
                    return match.group(0)
                given = options_of(match.group(1))
                shown = " ".join(match.group(0).split())
                extra = [item for item in given if item not in final]
                if not extra:
                    events.append(Event("KIT-SAME", source.name, shown, f"{shown}: the kit {label} writes it already; dropped"))
                    return f"% pdfmd: dropped, kit {label} writes {package_line(package, tuple(final))}"
                clash = [item for item in extra if item in foreign]
                if clash:
                    both = (f"kit {label} loads {package} with [{','.join(options)}]; {source.name} loads it with "
                            f"[{','.join(given)}], and {', '.join(clash)} belong{'s' if len(clash) == 1 else ''} to another mode of the kit")
                    if source.explicit:
                        raise PreambleClash(both + ". Keep one: remove that line, or choose the other mode (`--kit NAME:MODE`)")
                    events.append(Event("KIT-YIELD", source.name, shown, both + f"; the kit wins and `{shown}` is commented out in the build copy", True))
                    return f"% pdfmd: commented out, it contradicts kit {label}: {shown}"
                final.extend(extra)
                events.append(Event("KIT-MERGE", source.name, shown,
                                    f"{shown}: {', '.join(extra)} merged into the kit's line, {package_line(package, tuple(final))}"))
                return f"% pdfmd: merged into the kit's line: {shown}"

            text = PACKAGE_LINE.sub(package_replacement, text)

        def input_replacement(match: re.Match) -> str:
            if input_name(match.group(1)) not in inputs:
                return match.group(0)
            shown = " ".join(match.group(0).split())
            events.append(Event("KIT-SAME", source.name, shown, f"{shown}: the kit {label} writes it already; dropped"))
            return f"% pdfmd: dropped, kit {label} writes \\input{{{match.group(1).strip()}}}"

        if inputs:
            text = INPUT_LINE.sub(input_replacement, text)
        texts.append(text)
    return Resolution(tuple(final), texts, events)
