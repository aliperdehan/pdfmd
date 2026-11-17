"""Opt-in page markers: resolve settings and read CSL; Pandoc owns the citations.

P1a only. No excerpt records, source PDFs or project-specific text are read here.
The shared document filter list puts pagecite before crossref and citeproc.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from pdfmd_base import core

ENV = "PDFMD_PAGECITE"
MODES = ("off", "auto", "style", "page", "drop", "bare", "full")
# An internal reader token, restored by the filter before any writer sees it.
ESCAPED_OPEN = "\ue000pdfmd-pagecite-open\ue001"


def mode_value(value) -> str:
    if value is False:
        return "off"
    word = str(value).strip().casefold()
    if word not in MODES:
        raise SystemExit(f"pagecite must be one of {', '.join(MODES)}, not {value!r}")
    return {"bare": "page", "full": "style"}.get(word, word)


def command_line(value: str) -> None:
    os.environ[ENV] = mode_value(value)


def settings(document: Path, metadata: list[Path]) -> tuple[str, list[str]]:
    value = os.environ.get(ENV)
    if value is None:
        value = core.first_pdfmd_option(document, metadata, "pagecite")
    mode = "off" if value is None else mode_value(value)
    terms = core.first_pdfmd_option(document, metadata, "pagecite-terms")
    if terms is None:
        terms = ["p.", "pp."]
    elif isinstance(terms, str):
        terms = [term.strip() for term in terms.split(",") if term.strip()]
    if not isinstance(terms, list) or not all(isinstance(term, str) and term.strip() for term in terms):
        raise SystemExit("pagecite-terms must be a list of non-empty terms, such as [p., pp., S.]")
    return mode, [term.strip() for term in terms]


def enabled(document: Path, metadata: list[Path], no_auto=None) -> bool:
    return (not core.auto_disabled(no_auto, "pagecite") and "pagecite" in core.markup_kinds(document, metadata)
            and settings(document, metadata)[0] != "off")


def marker_pattern(terms: list[str]) -> re.Pattern:
    return re.compile(r"\[(?:" + "|".join(re.escape(term) for term in terms) + r")\s*([^]]*)\]", re.I)


def has_markers(text: str, terms: list[str]) -> bool:
    return any(re.search(r"[0-9]|\b[ivxlcdm]+\b", match[1], re.I) for match in marker_pattern(terms).finditer(text))


def protect_escapes(text: str, document: Path, metadata: list[Path]) -> str:
    """Preserve escaped open brackets, which Pandoc otherwise makes indistinguishable from markers.

    Only Pandoc input copies call this. Code, front matter, math and comments use the existing Markdown scanner;
    raw blocks and indented code are restored verbatim too, by the filter. Native and exported source stay untouched.
    """
    if "\\[" not in text or not enabled(document, metadata, core.effective_no_auto(document, core.NO_AUTO_CLI)):
        return text
    from pdfmd_obsidian.comments import _PROTECTED
    scan = re.compile(_PROTECTED + r"|(?P<texmath>\\\[.*?\\\]|\\\(.*?\\\))" + r"|(?P<open>(?<!\\)(?:\\\\)*\\\[)", re.S | re.M)
    terms = settings(document, metadata)[1]
    pattern = marker_pattern(terms)

    def protect(match: re.Match) -> str:
        if match.lastgroup == "open":
            candidate = pattern.match(text, match.end() - 1)
            if candidate and has_markers(candidate[0], terms):
                return match[0][:-2] + ESCAPED_OPEN
        return match[0]

    return scan.sub(protect, text)


def csl_choice(sources: list[Path], metadata: list[Path], options: list[str]) -> str | None:
    value = core.document_csl(sources, metadata)
    for index, word in enumerate(options):
        following = options[index + 1] if index + 1 < len(options) else ""
        if word == "--csl":
            value = following
        elif word.startswith("--csl="):
            value = word.split("=", 1)[1]
        else:
            item = following if word in ("-M", "--metadata") else word[2:] if word.startswith("-M") else (
                word.split("=", 1)[1] if word.startswith("--metadata=") else "")
            if item.startswith(("csl=", "csl:")):
                value = item[4:]
    return value


def style_settings(mode: str, sources: list[Path], metadata: list[Path], options: list[str]) -> tuple[str, str, str, bool]:
    """(mode, opening, closing, dropped-for-no-locator). Follow citation macros, not unused bibliography macros."""
    from xml.etree import ElementTree as ET

    native = any(word in options for word in ("--natbib", "--biblatex"))
    if mode == "auto" and native:
        return "style", "(", ")", False
    value = csl_choice(sources, metadata, options)
    if not value:
        return ("page" if mode == "auto" else mode), "(", ")", False
    # These are the same local search folders passed to Pandoc. An unreadable style falls back to a real citation.
    cwd = core.pandoc_working_directory(core.metadata_cwd(metadata, sources[0].parent))
    folders = [sources[0].parent, cwd]
    resources = core.resource_path_option(sources[0].parent, cwd, metadata)
    if resources:
        folders += [Path(item) if item != "." else cwd for item in resources[1].split(os.pathsep)]
    for index, word in enumerate(options):
        resource = options[index + 1] if word == "--resource-path" and index + 1 < len(options) else (
            word.split("=", 1)[1] if word.startswith("--resource-path=") else None)
        if resource is not None:
            folders = [cwd / item for item in resource.split(os.pathsep)]
    data_dir = core.pandoc_user_data_dir()
    for index, word in enumerate(options):
        if word == "--data-dir" and index + 1 < len(options):
            data_dir = cwd / options[index + 1]
        elif word.startswith("--data-dir="):
            data_dir = cwd / word.split("=", 1)[1]
    if data_dir is not None:
        folders += [data_dir / "csl", data_dir]
    try:
        path = next((folder / value for folder in folders if (folder / value).is_file()), None)
        if path is None:
            raise OSError(value)
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError, ValueError):
        return ("style" if mode == "auto" else mode), "(", ")", False
    ns = {"c": "http://purl.org/net/xbiblio/csl"}
    citation = root.find("c:citation", ns)
    layout = citation.find("c:layout", ns) if citation is not None else None
    opening = layout.get("prefix", "(") if layout is not None else "("
    closing = layout.get("suffix", ")") if layout is not None else ")"
    if mode != "auto":
        return mode, opening, closing, False
    if citation is None:
        return "style", opening, closing, False
    category = root.find("c:info/c:category[@citation-format]", ns)
    kind = category.get("citation-format") if category is not None else None
    if kind in ("author-date", "author"):
        return "page", opening, closing, False
    if kind not in ("numeric", "label"):
        return "style", opening, closing, False
    macros = {macro.get("name"): macro for macro in root.findall("c:macro", ns)}

    def uses_locator(element, seen: set[str]) -> bool:
        if element is None:
            return False
        for node in element.iter():
            if node.tag.rsplit("}", 1)[-1] in ("text", "number", "label") and "locator" in node.get("variable", "").split():
                return True
            name = node.get("macro")
            if name in macros and name not in seen and uses_locator(macros[name], seen | {name}):
                return True
        return False

    locator = uses_locator(citation, set())
    return ("style" if locator else "drop"), opening, closing, not locator


def filter_args(sources: Path | list[Path], metadata: list[Path], options: list[str], no_auto=None) -> list[str]:
    files = sources if isinstance(sources, list) else [sources]
    if not files or not enabled(files[0], metadata, no_auto):
        return []
    mode, terms = settings(files[0], metadata)
    texts = [core.read_text_best_effort(file) for file in files]
    if not any(has_markers(text, terms) or ESCAPED_OPEN in text for text in texts):
        return []
    import pdfmd_lua
    shipped = pdfmd_lua.path("pagecite")
    if shipped is None:
        core.pdfmd_lua_missing()
        return []
    mode, opening, closing, dropped = style_settings(mode, files, metadata, options)
    if dropped:
        print("NOTE  pagecite: citation style never prints a locator; dropping page markers", file=sys.stderr)
    # JSON metadata keeps literal punctuation and non-ASCII terms without Markdown smartening.
    config = {"pdfmd-pagecite": {"mode": mode, "opening": opening, "closing": closing, "terms": terms,
                                 "escaped": ESCAPED_OPEN}}
    import hashlib
    payload = json.dumps(config, ensure_ascii=False)
    path = core.cache_root() / "pagecite" / (hashlib.sha256(payload.encode()).hexdigest() + ".json")
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        core.atomic_write_text(path, payload)
    # --metadata-file strings are parsed as Markdown; the Lua side reads JSON directly instead.
    return ["-M", f"pdfmd-pagecite-config={path.as_posix()}", "--lua-filter", str(shipped)]


def native_note(document: Path, metadata: list[Path], text: str) -> None:
    if not enabled(document, metadata, core.effective_no_auto(document, core.NO_AUTO_CLI)):
        return
    from pdfmd_check.lint import mask_code
    from pdfmd_obsidian.comments import _PROTECTED
    text = mask_code(core.split_front_matter(text)[1])[0]
    text = re.sub(_PROTECTED, lambda match: " " * len(match[0]), text, flags=re.S | re.M)
    # Blank link labels (including nested brackets) and escaped brackets before looking for markers.
    chars, stack, position = list(text), [], 0
    while position < len(text):
        char = text[position]
        if char == "\\":
            if position + 1 < len(text):
                chars[position + 1] = " "
            position += 2
            continue
        if char == "[":
            stack.append(position)
        elif char == "]" and stack:
            start = stack.pop()
            if text[position + 1:position + 2] in ("(", "["):
                chars[start:position + 1] = " " * (position + 1 - start)
        position += 1
    text = "".join(chars)
    if has_markers(text, settings(document, metadata)[1]):
        print("NOTE  pagecite: native tier leaves page markers unchanged", file=sys.stderr)
