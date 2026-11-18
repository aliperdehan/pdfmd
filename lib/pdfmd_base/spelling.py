"""British public spellings of pdfmd's own names.

Apply these aliases only where pdfmd reads a name or a choice. Pandoc keys,
writer syntax and free text have their own spelling rules.
"""

ALIASES = {"color": "colour", "center": "centre", "flavor": "flavour", "gray": "grey"}


def british(word: str) -> str:
    return ALIASES.get(word, word)


def spellings(word: str) -> tuple[str, ...]:
    return (word, *(alias for alias, canonical in ALIASES.items() if canonical == word))


def flags(word: str) -> tuple[str, ...]:
    return tuple("--" + spelling for spelling in spellings(word))
