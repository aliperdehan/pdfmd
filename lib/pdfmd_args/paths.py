"""Keep CLI Pandoc paths based at the invocation folder, before a build changes its working directory.

Only CLI tokens come here. Names read from metadata, front matter or defaults files retain their own rules.
Pandoc also accepts data-file names and built-in style names: a bare name absent here keeps that lookup.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pdfmd_base import core


FILES = frozenset({
    "--bibliography", "--csl", "--citation-abbreviations", "--include-in-header", "--include-before-body",
    "--include-after-body", "--template", "--defaults", "--reference-doc", "--abbreviations", "--syntax-definition",
    "--highlight-style", "--syntax-highlighting", "--epub-cover-image", "--epub-metadata", "--epub-embed-font",
})
PATHS = frozenset({"--lua-filter", "--data-dir", "--extract-media", "--log"})
PROGRAMS = frozenset({"--filter", "--pdf-engine"})
SHORT = {"-L": "--lua-filter", "-F": "--filter", "-H": "--include-in-header", "-B": "--include-before-body",
         "-A": "--include-after-body"}


def invocation_paths(arguments: list[str], origin: Path) -> list[str]:
    """Absolutise path options, retaining URLs, standard input and Pandoc's named lookups."""
    styles = None

    def path(value: str, option: str) -> str:
        nonlocal styles
        if not value or value == "-":
            return value
        if Path(value).is_absolute() or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
            return value
        expanded = Path(value).expanduser()
        if expanded.is_absolute():
            return str(expanded)
        explicit = bool(os.path.dirname(value)) or any(char in value for char in "*?[")
        if option in PROGRAMS and not explicit:
            return value                         # executable names are found on PATH
        if option in FILES and not explicit and not (origin / expanded).is_file():
            return value                         # built-in style or a Pandoc user-data file
        if option in ("--highlight-style", "--syntax-highlighting") and not explicit:
            # Pandoc gives built-in names precedence over a same-named local file.
            if styles is None:
                found = core.run_probe(["pandoc", "--list-highlight-styles"])
                styles = set(found.stdout.split() if found else ()) | {"idiomatic", "none"}
            if value in styles:
                return value
        return str(origin / expanded)

    def value(text: str, option: str) -> str:
        if option == "--resource-path":
            return os.pathsep.join(path(part or ".", option) for part in text.split(os.pathsep))
        return path(text, option)

    result = []
    tokens = iter(arguments)
    for token in tokens:
        if token == "--":
            result.extend([token, *tokens])
            break
        option, equals, attached = token.partition("=")
        option = SHORT.get(option, option)
        if option in FILES | PATHS | PROGRAMS | {"--resource-path"}:
            if equals:
                result.append(token.partition("=")[0] + "=" + value(attached, option))
            else:
                result.append(token)
                following = next(tokens, None)
                if following is not None:
                    result.append(value(following, option))
        elif token[:2] in SHORT and len(token) > 2:
            result.append(token[:2] + value(token[2:], SHORT[token[:2]]))
        else:
            result.append(token)
            if token in ("-M", "--metadata", "-V", "--variable"):
                following = next(tokens, None)
                if following is not None:
                    result.append(following)
    return result
