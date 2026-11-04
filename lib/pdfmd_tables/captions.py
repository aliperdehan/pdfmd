"""The words a hand-typed table caption starts with (`**Table 1: ...**`), by language (v3.31.46, entry 3dy).

Data, not code: pdfmd_lua/table_caption.lua gets the list for the document's `lang:` (and English, which a document in any
language may still use) plus the words of the `table-caption-words` setting, so a language this list lacks is one line in a
setting, not a change here."""

from __future__ import annotations

# the primary language subtag -> the words for "Table"
CAPTION_WORDS: dict[str, tuple[str, ...]] = {
    "en": ("Table",), "de": ("Tabelle",), "fr": ("Tableau",), "es": ("Tabla", "Cuadro"), "it": ("Tabella",),
    "pt": ("Tabela", "Quadro"), "nl": ("Tabel",), "pl": ("Tabela",), "cs": ("Tabulka",), "sv": ("Tabell",),
    "da": ("Tabel",), "no": ("Tabell",), "nb": ("Tabell",), "nn": ("Tabell",), "fi": ("Taulukko",), "ro": ("Tabel",),
    "hu": ("Táblázat",), "el": ("Πίνακας",), "bg": ("Таблица",), "ru": ("Таблица",), "uk": ("Таблиця",), "kk": ("Кесте",),
    "tr": ("Tablo",), "ar": ("جدول",), "zh": ("表", "表格"), "ja": ("表",), "ko": ("표",),
}


def label_words(lang: str | None, extra: list[str] | tuple[str, ...] = ()) -> list[str]:
    """The label words for a document in ``lang`` (`ru`, `ru-RU`, `ru_RU`): English, those of the language, then ``extra``;
    each once, in that order."""
    words: list[str] = list(CAPTION_WORDS["en"])
    primary = (lang or "").replace("_", "-").split("-")[0].strip().casefold()
    words += CAPTION_WORDS.get(primary, ())
    words += [str(word).strip() for word in extra if str(word).strip()]
    return list(dict.fromkeys(words))
