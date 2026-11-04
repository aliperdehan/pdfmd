"""Priority of documents: which of several Markdown files bare `pdfmd` builds (entry 3eu of the maintainer's notes).

`rules` holds the words, the classes and the ladder (a `priority:` value or a file-name suffix becomes a `Rank` on it);
`choose` takes the documents of a folder and picks one. Both are pure: they import nothing from pdfmd. pdfmd.py reads the
`priority` values, the settings and the modification times, and prints what `choose` returns.
"""

from .choose import MISSING, Candidate, Choice, choose, explain
from .rules import DEFAULT_RANKING, NameParts, Rank, Ranking, RankingError, Value, compare, name_key, tokenize

__all__ = ["Candidate", "Choice", "DEFAULT_RANKING", "MISSING", "NameParts", "Rank", "Ranking", "RankingError", "Value",
           "choose", "compare", "explain", "name_key", "tokenize"]
