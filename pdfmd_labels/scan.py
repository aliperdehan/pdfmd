"""Read the LaTeX Pandoc wrote for a whole document and list, in order, what steps a counter or defines a label.

This is a scanner, not a typesetter: it does not count anything. It only reports the events (a numbered heading, a
caption in a float, a numbered equation row, a label, the start of a part, ``\\appendix``) and leaves the counting
to LaTeX, which replays them (see ``replay.py``), so ``\\counterwithin``, a Roman ``\\thesection``, a package's own
counters and per-chapter resets all come out as in the full build.

What it cannot see: a macro or environment the document defines itself (nulabreport's float wrappers, say), a
``\\label`` that a package writes, ``\\item`` labels. Those labels stay undefined (``??``) as before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LEVELS = {"part": -1, "chapter": 0, "section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4,
          "subparagraph": 5}
FLOATS = {"figure": "figure", "figure*": "figure", "wrapfigure": "figure", "table": "table", "table*": "table",
          "longtable": "table", "longtable*": "table", "sidewaystable": "table", "sidewaysfigure": "figure",
          "subfigure": "subfigure", "subtable": "subtable"}
EQUATION = {"equation", "equation_x"}
ROWS = {"align", "gather", "flalign", "alignat", "eqnarray", "xalignat", "xxalignat"}
SINGLE = {"multline"}
VERBATIM = {"verbatim", "Verbatim", "lstlisting", "minted", "Highlighting", "comment", "filecontents",
            "filecontents*", "BVerbatim", "LVerbatim", "alltt"}
DEFINES_ONE = {"newcommand", "renewcommand", "providecommand", "DeclareRobustCommand", "DeclareMathOperator",
               "newrobustcmd", "renewrobustcmd", "NewDocumentCommand", "RenewDocumentCommand",
               "ProvideDocumentCommand", "DeclareDocumentCommand"}
DEFINES_PLAIN = {"def", "gdef", "edef", "xdef"}
DEFINES_ENV = {"newenvironment", "renewenvironment", "NewDocumentEnvironment"}

TOKEN = re.compile(r"""
    (?P<comment>%[^\n]*)
  | (?P<escaped>\\[\\%{}&_\#$^\s~])
  | \\(?P<name>[A-Za-z@]+)(?P<star>\*?)
""", re.VERBOSE)
GROUP = re.compile(r"\s*\{([^{}]*)\}")


@dataclass(frozen=True)
class Event:
    """kind: sec (arg = counter, level), step (arg = counter), lab (arg = label), part (arg = key), app, fn."""
    kind: str
    arg: str = ""
    level: int = 0


@dataclass
class Scan:
    events: list[Event]
    labels: int          # how many labels the document defines (as the scanner sees them)
    steps: int           # how many counter steps it saw (headings, captions, equations, footnotes)

    def parts(self) -> int:
        return sum(1 for event in self.events if event.kind == "part")


def _group_end(text: str, start: int) -> int:
    """The index just past the brace group that opens at ``text[start]`` ('{'), or ``len(text)`` if it never closes."""
    depth = 0
    index = start
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == "%":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(text)


def _skip_groups(text: str, position: int, groups: int) -> int:
    """Past ``groups`` brace groups after ``position`` (optional [..] arguments in between are skipped too)."""
    index = position
    for _ in range(groups):
        while index < len(text) and (text[index].isspace() or text[index] == "*"):
            index += 1
        while index < len(text) and text[index] == "[":
            close = text.find("]", index)
            index = len(text) if close < 0 else close + 1
            while index < len(text) and text[index].isspace():
                index += 1
        if index < len(text) and text[index] == "{":
            index = _group_end(text, index)
        elif index < len(text) and text[index] == "\\":
            match = re.compile(r"\\[A-Za-z@]+|\\.").match(text, index)
            index = match.end() if match else index + 1
            # a \newcommand\name{body}: the name stood in for the first group
            while index < len(text) and text[index].isspace():
                index += 1
            while index < len(text) and text[index] == "[":
                close = text.find("]", index)
                index = len(text) if close < 0 else close + 1
        else:
            break
    return index


def scan(text: str) -> Scan:
    """The events of a LaTeX document body (what lies between ``\\begin{document}`` and ``\\end{document}``)."""
    start = text.find("\\begin{document}")
    if start >= 0:
        text = text[start + len("\\begin{document}"):]
    end = text.rfind("\\end{document}")
    if end >= 0:
        text = text[:end]
    events: list[Event] = []
    stack: list[str] = []            # open environments, innermost last
    row = {"pending": False, "numbered": True, "from": 0}
    labels = steps = 0

    def step(counter: str) -> None:
        nonlocal steps
        events.append(Event("step", counter))
        steps += 1

    def top_math() -> str | None:
        return stack[-1] if stack and (stack[-1] in ROWS or stack[-1] in EQUATION or stack[-1] in SINGLE) else None

    position = 0
    while True:
        match = TOKEN.search(text, position)
        if match is None:
            break
        position = match.end()
        name = match.group("name")
        if name is None:
            if match.group("escaped") == "\\\\" and top_math() in ROWS:
                # a row break of align & co: the row just ended takes its number (unless it was switched off)
                if row["pending"] and row["numbered"]:
                    step("equation")
                row.update(pending=True, numbered=True)
                row["from"] = position
            continue
        starred = bool(match.group("star"))
        if name in LEVELS:
            if not starred:
                events.append(Event("sec", name, LEVELS[name]))
                steps += 1
        elif name == "caption" or name == "captionof":
            if starred:
                continue
            counter = None
            if name == "captionof":
                group = GROUP.match(text, position)
                if group:
                    counter, position = group.group(1), group.end()
            else:
                for environment in reversed(stack):
                    if environment in FLOATS:
                        counter = FLOATS[environment]
                        break
            if counter:
                step(counter)
        elif name == "label":
            group = GROUP.match(text, position)
            if group:
                position = group.end()
                if top_math() in ROWS and row["pending"] and row["numbered"]:
                    step("equation")
                    row["pending"] = False
                events.append(Event("lab", group.group(1)))
                labels += 1
        elif name == "begin":
            group = GROUP.match(text, position)
            if not group:
                continue
            environment, position = group.group(1), group.end()
            if environment in VERBATIM:
                closing = text.find("\\end{%s}" % environment, position)
                position = len(text) if closing < 0 else closing + len("\\end{%s}" % environment)
                continue
            stack.append(environment)
            if environment in EQUATION or environment in SINGLE:
                step("equation")
            elif environment in ROWS:
                row.update(pending=True, numbered=True)
                row["from"] = position
        elif name == "end":
            group = GROUP.match(text, position)
            if not group:
                continue
            environment, position = group.group(1), group.end()
            if environment in ROWS and stack and stack[-1] == environment:
                if row["pending"] and row["numbered"] and text[row["from"]:match.start()].strip():
                    step("equation")
                row["pending"] = False
            if environment in stack:
                while stack and stack.pop() != environment:
                    pass
        elif name in ("nonumber", "notag", "tag"):
            if top_math() in ROWS:
                row["numbered"] = False
        elif name == "appendix":
            events.append(Event("app"))
        elif name == "pdfmdpart":
            group = GROUP.match(text, position)
            if group:
                position = group.end()
                events.append(Event("part", group.group(1)))
        elif name == "footnote":
            step("footnote")
        elif name in DEFINES_ONE:
            position = _skip_groups(text, position, 2)
        elif name in DEFINES_PLAIN:
            position = _definition_body(text, position)
        elif name in DEFINES_ENV:
            position = _skip_groups(text, position, 3)
    return Scan(events, labels, steps)


def _definition_body(text: str, position: int) -> int:
    """Past the body of ``\\def\\name#1{...}``: the first brace group after the name."""
    brace = text.find("{", position)
    newline = text.find("\n\n", position)
    if brace < 0 or (0 <= newline < brace):
        return position
    return _group_end(text, brace)
