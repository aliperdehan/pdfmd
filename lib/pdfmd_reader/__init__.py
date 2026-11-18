"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_reader`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

from pdfmd_base import core

from pdfmd_base import pandoc_run


# What a Markdown document really contains, asked of Pandoc's own reader: a `@key` in a code span, an e-mail
# address or an escaped `\\@` is no citation, and the reader is the judge of that, not a pattern (the README of
# pdfmd itself, which writes `@fig:` in backticks, was read as using pandoc-crossref). One parse per file state.
_MARKDOWN_FEATURES: dict[tuple, tuple[bool, bool] | None] = {}


def markdown_features(md_path: Path) -> tuple[bool, bool] | None:
    """(has citations, uses pandoc-crossref) of a Markdown file, from its Pandoc AST; None when Pandoc is not
    there to say (the callers then fall back to a pattern)."""
    try:
        stat = md_path.stat()
        key = (str(md_path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None
    if key in _MARKDOWN_FEATURES:
        return _MARKDOWN_FEATURES[key]
    found = None
    pandoc = core.which("pandoc")
    if pandoc:
        try:
            text = core.EMBED_BLOCK_RE.sub("", core.obsidian_source(md_path.read_text(encoding="utf-8-sig"), md_path, show=False))
            command = [pandoc, "-f", "markdown", "-t", "json"]
            if core.md_macro_in(text):
                # the Markdown inside `\md{...}` is part of the document: a citation there needs --citeproc
                try:
                    import pdfmd_lua
                except ImportError:
                    core.pdfmd_lua_missing()
                    shipped = None
                else:
                    shipped = pdfmd_lua.path("md_macro")
                if shipped is not None:
                    command += ["--lua-filter", str(shipped)]
            done = pandoc_run(command, input=text, capture_output=True,
                                  text=True, encoding="utf-8", timeout=120)
            if done.returncode == 0:
                found = ast_features(json.loads(done.stdout))
        except (OSError, ValueError, subprocess.SubprocessError, UnicodeDecodeError):
            found = None
    _MARKDOWN_FEATURES[key] = found
    return found


CROSSREF_ID_RE = re.compile(r"^(?:" + "|".join(("fig", "eq", "tbl", "sec", "lst")) + r"):[-\w]+")


# before Pandoc 3.8.2 a table caption's `{#tbl:t}` is not the table's identifier, it stays in the caption as words
CROSSREF_TEXT_RE = re.compile(r"^\{#(?:fig|eq|tbl|sec|lst):[-\w]+")


def ast_features(document) -> tuple[bool, bool]:
    """(any citation, any pandoc-crossref label or reference) in a Pandoc JSON document."""
    cited = crossref = False
    stack = [document]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("t") == "Cite":
                cited = True
                content = node.get("c") or [[]]
                for citation in content[0] if content else []:
                    if isinstance(citation, dict) and CROSSREF_ID_RE.match(str(citation.get("citationId", ""))):
                        crossref = True
            if node.get("t") == "Str" and isinstance(node.get("c"), str) and CROSSREF_TEXT_RE.match(node["c"]):
                crossref = True
            stack.extend(node.values())
        elif isinstance(node, list):
            # an Attr is [identifier, [classes], [[key, value]...]]
            if (len(node) == 3 and isinstance(node[0], str) and isinstance(node[1], list)
                    and isinstance(node[2], list) and CROSSREF_ID_RE.match(node[0])):
                crossref = True
            stack.extend(node)
        if cited and crossref:
            break
    return cited, crossref


def contains_citations(md_path: Path) -> bool:
    """Whether the document has Pandoc citations (`[@key]`, `@key`, `-@key`)."""
    if md_path.suffix.lower() not in MARKDOWN_LIKE_SUFFIXES:
        return False
    features = markdown_features(md_path)
    if features is not None and features[0] or core.fullcite_old_spelling(md_path):      # `[[fullcite:key]]` is a citation to be
        return True
    if features is not None:
        return False
    text = core.EMBED_BLOCK_RE.sub("", core.obsidian_source(md_path.read_text(encoding="utf-8-sig"), md_path, show=False))
    return bool(re.search(r"(?<![\w@])(?:-?@[-\w:.]+)", text))


CROSSREF_LABEL_KINDS = ("fig", "eq", "tbl", "sec", "lst")


CROSSREF_RE = re.compile(
    r"\{[^}\n]*#(?:" + "|".join(CROSSREF_LABEL_KINDS) + r"):[-\w]+[^}\n]*\}"
    r"|@(?:" + "|".join(CROSSREF_LABEL_KINDS) + r"):[-\w]+"
)


def contains_crossref(md_path: Path) -> bool:
    """Detect pandoc-crossref's own attribute/reference syntax.

    Two shapes: a numbered-element attribute definition (``{#fig:setup}``
    on an image/table/heading -- crossref auto-numbers and prefixes the
    caption even if nothing ever references it back elsewhere) and a
    reference to one (``@fig:...``/``@eq:...``/``@tbl:...``/``@sec:...``/
    ``@lst:...``). Deliberately distinct from contains_citations()'s much
    broader ``@key`` match, which already matches ``@fig:setup`` too (a
    colon is a valid citation-key character) -- that overlap is exactly
    the bug this exists to fix: a crossref-only document was already
    getting `--citeproc` added (harmlessly finding no bibliography entry
    named "fig:setup"), but nothing ever added `--filter pandoc-crossref`,
    so the reference/numbering itself never actually resolved.
    """
    if md_path.suffix.lower() not in MARKDOWN_LIKE_SUFFIXES:
        return False
    features = markdown_features(md_path)
    if features is not None:
        return features[1]
    text = core.EMBED_BLOCK_RE.sub("", md_path.read_text(encoding="utf-8-sig"))
    return bool(CROSSREF_RE.search(text))


@lru_cache(maxsize=None)
def crossref_built_for(executable: str) -> tuple[int, ...] | None:
    """The Pandoc version a pandoc-crossref was built with (from its --version), or None when it does not say."""
    try:
        done = subprocess.run([executable, "--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    found = re.search(r"built with Pandoc v(\d+(?:\.\d+)+)", done.stdout + done.stderr)
    return tuple(int(part) for part in found.group(1).split(".")) if found else None


def crossref_filter_args(sources: Path | list[Path], pandoc_options: list[str],
                         no_auto: list[str] | None, label: str) -> list[str]:
    """``--filter pandoc-crossref``, added before --citeproc, when needed.

    Ordering matters: pandoc-crossref resolves/numbers `@fig:`/`@eq:`/
    `@tbl:`/`@sec:`/`@lst:` references and rewrites the AST accordingly
    BEFORE citeproc ever runs, so citeproc only ever sees genuine
    bibliography citations left over -- the same reasoning the existing
    "Lua filters go last" comment already documents for the table-width
    filter needing citations resolved first, just the opposite ordering
    constraint (crossref before citeproc, not after). Silently a no-op
    when --no-auto crossref disables it, the filter is already given
    explicitly, or no source actually uses crossref syntax; a document
    that DOES use it but has no pandoc-crossref binary gets one clear
    WARN instead of silently shipping unresolved `@fig:...`/`{#fig:...}`
    text into the rendered output.
    """
    if core.auto_disabled(no_auto, "crossref") or "pandoc-crossref" in pandoc_options:
        return []
    files = sources if isinstance(sources, list) else [sources]
    if not any(contains_crossref(file) for file in files):
        return []
    if core.which("pandoc-crossref") is None:
        print(f"WARN  {label}: uses pandoc-crossref syntax (@fig:/@eq:/@tbl:/@sec:/@lst: or a "
              "{#fig:...}-style attribute) but pandoc-crossref isn't installed; the reference/"
              "numbering will not resolve. Install it (e.g. `brew install pandoc-crossref`), "
              "or rewrite without crossref syntax to silence this.", file=sys.stderr)
        return []
    executable = core.which("pandoc-crossref")
    built, running = crossref_built_for(executable), core.pandoc_version()
    if built and running != (0,) and built[:2] != running[:2]:
        # pandoc-crossref "is not supported" through another Pandoc: it runs, and leaves ?? where the numbers go
        print(f"WARN  {label}: uses pandoc-crossref syntax, but the installed pandoc-crossref was built for Pandoc "
              f"{'.'.join(map(str, built))} and this is Pandoc {'.'.join(map(str, running))}; it would put ?? "
              "where the numbers go, so it was not run. Install the pandoc-crossref release made for this Pandoc "
              "(github.com/lierdakil/pandoc-crossref/releases), or a Pandoc to match.", file=sys.stderr)
        return []
    return ["--filter", "pandoc-crossref"]


PERCENT_TITLE_BLOCK_RE = re.compile(r"^%(?:[ \t]|$)")


def has_percent_title_block(text: str) -> bool:
    """Detect Pandoc's legacy ``% title`` / ``% author`` / ``% date`` block.

    Only the ``pandoc_title_block`` extension -- enabled by Pandoc's default
    ``markdown`` reader, but not by ``gfm`` -- parses this. A document
    written this way needs the same treatment as one with ``---`` YAML front
    matter: resolve_from_format() must not downgrade it to ``gfm`` (which
    would leave the ``%`` lines as literal text instead of parsing them into
    title/author/date metadata), and promote_bare_title() must not mistake
    its leading ``%`` line for a bare ATX heading to promote.
    """
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    return bool(PERCENT_TITLE_BLOCK_RE.match(first_line))


# The readers Pandoc would not pick (or would pick wrongly) from the file's extension alone.
SUFFIX_READERS = {".typ": "typst", ".typst": "typst"}


PANDOC_KNOWN_SUFFIXES = frozenset({".typ"})


# What pdfmd reads as Markdown: the helpers that look for Markdown syntax (citations, a bare `# Title`) run on these only
MARKDOWN_LIKE_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd", ".txt", "")


def resolve_from_format(md_path: Path, cli_from: str | None,
                        metadata_files: list[Path] = ()) -> tuple[str | None, str | None]:

    """Pick the Pandoc reader for one Markdown source.

    An explicit --from always wins (returned as-is, with no message). A
    document that already has ``---`` YAML front matter, or a leading
    ``%``-line title block (``% title`` / ``% author`` / ``% date``), is
    assumed to already be written for Pandoc's own default ``markdown``
    reader and is left alone (returns ``None``, meaning "don't pass -f, let
    Pandoc use its default") -- gfm has no ``pandoc_title_block`` extension,
    so switching a ``%``-block document to gfm would leave those lines as
    literal text instead of parsing them into title/author/date metadata.
    So is one with a linked --metadata-file (explicit or
    auto-discovered) attached: a document (or a folder of them) set up with
    its own metadata.yaml is assumed to already be Pandoc-aware, and gfm's
    reader has no ``citations`` extension to fall back to the way the plain
    ``markdown`` reader does below -- see promote_bare_title() for the more
    concrete failure this also heads off (a bare ``# Title`` silently
    overriding the linked file's own ``title:``, since Pandoc gives a
    document's own metadata priority over ``--metadata-file``).

    A document with NO front matter and no linked metadata file -- the
    fingerprint of ordinary GitHub-Flavored Markdown nobody wrote with
    Pandoc's own stricter rules in mind -- is instead read as ``gfm``. This
    matters for more than blank lines before headings/lists/blockquotes
    (Pandoc's default reader requires one, GFM doesn't): Pandoc's default
    ``markdown`` also bundles ``simple_tables``/``multiline_tables``/
    ``grid_tables`` alongside ``pipe_tables``, and that combination makes it
    force EVERY pipe-table column to an equal width fraction (e.g. exactly
    1/3 each for a 3-column table) instead of sizing columns to their actual
    content -- turning a short "Type" column and a long "Notes" column into
    the same width and wrapping the long one over many lines. ``gfm`` only
    enables ``pipe_tables``, so it never does this. On a table-heavy
    document this alone can be the difference between a compact table and
    one that balloons across several pages.

    Two Pandoc-only extensions get restored on top of ``gfm`` when the
    document actually needs them, since GFM's own reader supports neither:
    ``+definition_lists`` (``Term\\n: definition``) can simply be added back
    onto ``gfm``. ``citations`` (``@key``) cannot be -- Pandoc rejects
    ``gfm+citations`` outright -- so a document using citation syntax falls
    all the way back to the plain ``markdown`` reader instead, trading away
    the table/blank-line fixes to keep citeproc resolving its citations.

    None of this heuristic applies to a file that isn't actually Markdown
    in the first place: it looks only at front-matter/title-block/
    metadata-file presence, never at the file's own extension, so a real
    ``.tex``/``.html``/``.rst``/etc. file with no YAML front matter of its
    own used to be silently misread as ``gfm`` too, whenever it reached
    Pandoc at all -- rare in practice since PDF output normally goes
    through the direct-.tex-compile path instead now (see v3.1.0), but
    still live for `--to` a non-PDF format or `--no-auto texdirect`.
    Found during that same v3.1.0 round's own edge-case testing; fixed
    here rather than left for later since it is a pre-existing,
    independent bug, not something v3.1.0 introduced. Guarding on suffix
    up front (below) makes this a no-op for anything but a real
    ``.md``/``.markdown`` source, matching what Pandoc's own extension-
    based reader inference would have picked anyway.
    """
    if cli_from:
        return cli_from, None
    suffix = md_path.suffix.lower()
    if suffix in SUFFIX_READERS:
        # said outright: an extension Pandoc does not know is read as Markdown, and an old Pandoc that has no
        # reader for the format then fails by name instead of printing the source as text
        reader = SUFFIX_READERS[suffix]
        return reader, (None if suffix in PANDOC_KNOWN_SUFFIXES
                        else f"{md_path}: Pandoc does not know the {suffix} extension; reading as {reader}")
    if suffix not in (".md", ".markdown"):
        return None, None
    reader, note = flavour_reader(md_path, metadata_files)
    if core.FLAVOUR_PRESETS and core.single_newline_mode(md_path, metadata_files) == "hard" and "hard_line_breaks" not in (reader or ""):
        reader = f"{reader or 'markdown'}+hard_line_breaks"          # a single newline is a line break (v3.32.27)
    return reader, note


def flavour_reader(md_path: Path, metadata_files: list[Path] = ()) -> tuple[str | None, str | None]:
    """The reader a Markdown file's flavour gives (resolve_from_format adds the single newline): (reader or None for Pandoc's own, note)."""
    name, spec = core.flavour_setting(md_path, metadata_files)
    if spec:
        return spec, None                 # `pdfmd-options: {flavour: gfm+smart}` (or `reader:`; document, metadata file, config): --from, per document
    preset = core.FLAVOUR_PRESETS.get(name)
    if preset is not None and preset.reader != "auto":
        return (None if preset.reader == "default" else preset.reader), None      # `flavour: pandoc|gfm|commonmark`: that reader, as it is
    reader, note = pdfmd_reader(md_path, metadata_files)
    if preset is None:
        return reader, note
    if reader is None:                                   # Pandoc's Markdown, with what the flavour adds to it (v3.32.23)
        return ("markdown" + preset.markdown_plus if preset.markdown_plus else None), note
    return (reader + "".join(f"+{extension}" for extension in preset.gfm_plus.split("+") if extension and extension not in reader)
            if reader.startswith("gfm") else reader), note


def pdfmd_reader(md_path: Path, metadata_files: list[Path] = ()) -> tuple[str | None, str | None]:
    """pdfmd's own pick of reader for a Markdown file, from what the file says and uses (resolve_from_format has the reasons): gfm with
    the extensions it needs, or None for Pandoc's own Markdown."""
    text = core.obsidian_source(md_path.read_text(encoding="utf-8-sig"), md_path, metadata_files, show=False)   # hidden text decides nothing
    if core.has_yaml_frontmatter(text) or has_percent_title_block(text):
        return None, None
    if core.EMBED_BLOCK_RE.search(text) and core.is_assembled_text(text):
        # Embedded `{=pdfmd}` blocks need Pandoc's own markdown: gfm would
        # print them as code blocks.
        return None, None
    # The global metadata (`pdfmd --setup`, and its presets) is the machine's, not the document's: it says nothing about
    # which dialect this file was written in, and on a machine that has one it made every file read as Pandoc's Markdown
    # (v3.32.4). What it sets still applies: Pandoc reads a metadata file with its own Markdown, whatever the reader.
    linked_files = [metadata_file for metadata_file in metadata_files if not core.is_global_metadata(metadata_file)]
    if linked_files:
        names = ", ".join(metadata_file.name for metadata_file in linked_files)
        return None, (f"{md_path}: no YAML front matter, but {names} is linked; "
                      "keeping the default markdown reader instead of gfm")
    if contains_citations(md_path) or ("@-" in text and core.deferred(
            "pdfmd_excerpts.resolution", "protect_hyphen_prefix")(
                text, md_path, metadata_files, core.effective_no_auto(md_path, core.NO_AUTO_CLI)) != text):
        return None, (f"{md_path}: no YAML front matter, but it uses @citation syntax "
                      "gfm can't parse; keeping the default markdown reader")
    if core.ORG_CAPTION_RE.search(text) and core.table_ascii_mode(md_path, list(metadata_files)) == "repair":
        return None, (f"{md_path}: no YAML front matter, but it has Org `#+CAPTION:` lines, which become table captions "
                      "that only Pandoc's markdown reader reads; keeping the default markdown reader instead of gfm")
    if core.md_macro_in(text) and core.md_macro_on(md_path, list(metadata_files)):
        return None, (f"{md_path}: no YAML front matter, but it has `\\md{{...}}` (Markdown inside raw LaTeX), which only Pandoc's "
                      "markdown reader keeps as raw LaTeX for pdfmd to read; keeping the default markdown reader instead of gfm")
    needs = reader_needs(text)
    pandoc_only = [name for name, extension in needs if extension is None]
    if pandoc_only:
        return None, (f"{md_path}: no YAML front matter, but it uses {', '.join(pandoc_only)}, which gfm cannot read; "
                      "keeping the default markdown reader")
    names = [name for name, _ in needs]
    extensions = [extension for _, extension in needs]
    if core.contains_csv_table(md_path):
        # A `.csv` div is Pandoc's fenced_divs syntax (`::: {.csv ...} :::`),
        # which -- unlike Pandoc's own default `markdown` reader, where it's
        # on by default -- gfm doesn't enable at all, so without this a
        # front-matter-less document's `.csv` div is read as literal text
        # instead of a real Div (caught directly: a first real test of this
        # feature rendered the div's own source text verbatim in the PDF,
        # smart-quoted, instead of a table at all).
        names.append("a .csv table")
        extensions.append("fenced_divs")
    reader = "gfm" + "".join(f"+{extension}" for extension in dict.fromkeys(
        part for extension in extensions for part in extension.split("+")))
    return reader, f"{md_path}: no YAML front matter; reading as {reader}" + (f" (it uses {', '.join(names)})" if names else "")


# What a Markdown file with no front matter may use that gfm does not read, and what each needs (v3.32.5; before, a NOTE said
# gfm left it as text). The third column is an extension Pandoc accepts on gfm (added to the reader), or None when only Pandoc's
# own Markdown reader reads it (the reader is then switched). The last column is the text the pattern looks at: "prose" is the
# document without fenced code, inline code, math and HTML comments (an example in a code block is not syntax the document
# uses), "fences" keeps inline code, "text" is the whole file (the line that opens a fence carries its attributes).
READER_NEEDS = (
    ("subscripts (H~2~O)", re.compile(r"(?<![~\\])~(?!~)[^\s~]+~(?!~)"), "subscript", "prose"),
    ("superscripts (x^2^)", re.compile(r"(?<![\^\\])\^[^\s^\[]+\^"), "superscript", "prose"),
    ("{#id .class} attributes", re.compile(r"(?m)^#{1,6} .*\{[#.][^}]*\}[ \t]*$|\]\{[#.][^}]*\}|!\[[^\]]*\]\([^)]*\)\{[^}]*\}"),
     "attributes+bracketed_spans", "prose"),
    ("attributes on inline code", re.compile(r"`[^`\n]+`\{[#.][^}\n]*\}"), "attributes", "fences"),
    ("fenced code attributes ({.class key=value})", re.compile(r"(?m)^[ \t]*(?:`{3,}|~{3,})[ \t]*\{"), "attributes", "text"),
    ("raw attributes (`x`{=html})", re.compile(r"`[^`\n]+`\{=[A-Za-z]+\}"), "raw_attribute", "fences"),
    ("fenced divs (:::)", re.compile(r"(?m)^:{3,}[ \t]*\{?[.\w#]"), "fenced_divs", "prose"),
    ("definition lists", re.compile(r"(?m)^:[ \t]"), "definition_lists", "prose"),
    ("inline footnotes (^[...])", re.compile(r"\^\["), None, "prose"),
    ("raw LaTeX (\\begin{...}, \\newcommand{...}, \\ce{...})", re.compile(r"\\[A-Za-z]+\*?(?:\[[^\]\n]*\])?\{"), None, "prose"),
    ("grid tables", re.compile(r"(?m)^\+[-=:]+(?:\+[-=:]+)*\+[ \t]*$"), None, "prose"),
    ("simple tables", re.compile(r"(?m)^ {0,3}(?:-{2,}[ \t]+)+-{2,}[ \t]*$"), None, "prose"),
    ("example lists ((@))", re.compile(r"(?m)^ {0,3}\(@[\w-]*\)[ \t]"), None, "prose"),
)


LIST_MARKER_RE = re.compile(r"(?m)^ {0,3}\(?([A-Za-z]|[ivxIVX]{1,4})[.)][ \t]+\S")


ROMAN_NUMERALS = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x")


def has_fancy_list(prose: str) -> bool:
    """Two list items in a row that are lettered or numbered in Roman (``a.`` ``b.``, ``(i)`` ``(ii)``, ``A)`` ``B)``): Pandoc's
    ``fancy_lists``. One such line alone ("I. Introduction") is text, as it is in GFM."""
    markers = [(prose.count("\n", 0, match.start()), match.group(1)) for match in LIST_MARKER_RE.finditer(prose)]
    for (line, first), (next_line, second) in zip(markers, markers[1:]):
        if next_line - line > 8 or first.isupper() != second.isupper():
            continue
        low_first, low_second = first.lower(), second.lower()
        if len(low_first) == len(low_second) == 1 and ord(low_second) == ord(low_first) + 1:
            return True
        if low_first in ROMAN_NUMERALS and low_second in ROMAN_NUMERALS \
                and ROMAN_NUMERALS.index(low_second) == ROMAN_NUMERALS.index(low_first) + 1:
            return True
    return False


def reader_texts(text: str) -> dict[str, str]:
    """The three views of a document the detectors of READER_NEEDS look at."""
    without_fences = re.sub(r"(?ms)^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", "", text)
    prose = re.sub(r"`[^`\n]*`", "", without_fences)
    prose = re.sub(r"(?s)<!--.*?-->", "", prose)
    prose = re.sub(r"(?s)\$\$.*?\$\$", "", prose)
    prose = re.sub(r"(?<![\\$])\$(?!\s)[^$\n]*?(?<!\s)\$(?!\d)", "", prose)
    return {"text": text, "fences": without_fences, "prose": prose}


def reader_needs(text: str) -> list[tuple[str, str | None]]:
    """(what the document uses, the gfm extension it needs or None for Pandoc's own reader) for each syntax found."""
    views = reader_texts(text)
    found = [(name, extension) for name, pattern, extension, view in READER_NEEDS if pattern.search(views[view])]
    if has_fancy_list(views["prose"]):
        found.append(("lettered or Roman-numeral lists", "fancy_lists"))
    return found


ATX_H1_RE = re.compile(r"^#[ \t]+(?P<title>.+?)[ \t]*#*[ \t]*$")


def promote_bare_title(text: str, has_external_metadata: bool = False) -> tuple[str, bool]:
    """Promote a document's leading bare ``# Title`` into real Pandoc title
    metadata, and report whether the rest of its headings need shifting up
    a level to match.

    Only fires when the document has no YAML front matter at all (an
    existing ``title:`` is left alone), has no linked --metadata-file
    either, and its very first non-blank line is a single ATX H1 -- exactly
    what a GFM document whose editor rendered ``# Title`` as a page heading
    looks like, as opposed to one already written with Pandoc's own
    ``%``/YAML title-block conventions in mind. The metadata-file check
    matters because Pandoc gives a document's own metadata priority over
    ``--metadata-file``: promoting a bare heading here would silently
    override a ``title:`` the linked file already set, for a document that
    likely only omitted its own front matter because the linked file
    already supplies it.

    Once promoted, the heading becomes the document's actual title (e.g.
    LaTeX's ``\\maketitle``, or an HTML ``<title>``) instead of an extra,
    numbered top-level section -- so the caller must also pass
    ``--shift-heading-level-by=-1`` for the rest of the document's
    ``##``/``###`` sections to land at the levels they were written for.
    """
    if core.has_yaml_frontmatter(text) or has_external_metadata or has_percent_title_block(text):
        return text, False
    lines = text.splitlines(keepends=True)
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return text, False
    match = ATX_H1_RE.match(lines[index].rstrip("\r\n"))
    if not match:
        return text, False
    title = match.group("title").strip()
    if not title:
        return text, False
    newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
    remainder_start = index + 1
    while remainder_start < len(lines) and not lines[remainder_start].strip():
        remainder_start += 1
    remainder = "".join(lines[remainder_start:])
    escaped_title = title.replace("'", "''")
    front_matter = f"---{newline}title: '{escaped_title}'{newline}---{newline}{newline}"
    return front_matter + remainder, True


@contextmanager
def prepared_title_source(md_path: Path, metadata_files: list[Path] = (),
                          disabled: bool = False,
                          override: tuple[str, bool] | None = None) -> Iterator[tuple[Path, bool]]:
    """Yield a temporary copy of ``md_path`` with promote_bare_title() applied,
    and whether that happened (the caller needs to know to also shift
    heading levels). Yields ``md_path`` itself, unchanged, when nothing to
    promote was found, or when ``disabled`` (--no-auto title/bare) skips it.

    ``override`` is (text, shifted) of a document already cut down to some of
    its sections (SectionPlan, which promoted the title itself): that text is
    what the temporary copy holds, whatever the file says. Everything else
    pdfmd reads about the document (front matter, preamble, citations) still
    comes from the whole file, so a section is built with the document's own
    settings.
    """
    if override is not None:
        text, shifted = override
        if md_path.suffix.lower() in MARKDOWN_LIKE_SUFFIXES:
            text = core.obsidian_source(text, md_path, metadata_files)
            text = core.repair_ascii_text(text, core.table_ascii_mode(md_path, list(metadata_files)), core.display_path(md_path))
            text = core.cell_tags_text(text, md_path, metadata_files, core.display_path(md_path))
        with NamedTemporaryFile("w", encoding="utf-8", suffix=md_path.suffix,
                                prefix=f".{md_path.stem}.pdfmd-section-", dir=md_path.parent,
                                delete=False) as temporary:
            temporary.write(text)
            temporary_path = Path(temporary.name)
        try:
            yield temporary_path, shifted
        finally:
            temporary_path.unlink(missing_ok=True)
        return
    if md_path.suffix.lower() not in MARKDOWN_LIKE_SUFFIXES:
        yield md_path, False
        return
    original = md_path.read_text(encoding="utf-8-sig")
    text = core.obsidian_source(original, md_path, metadata_files)      # an Obsidian note's %%comments%% go first: a hidden heading is no title
    corrected, shifted = text, False
    if not disabled:
        corrected, shifted = promote_bare_title(text, has_external_metadata=bool(metadata_files))
    repaired = core.repair_ascii_text(corrected, core.table_ascii_mode(md_path, list(metadata_files)), core.display_path(md_path))
    repaired = core.cell_tags_text(repaired, md_path, metadata_files, core.display_path(md_path))
    chapter = (core.REPORT_BUILD.get("chapters") or {}).get(md_path)
    if chapter is not None:
        # a report's first file: its title leaves the front matter and becomes a chapter heading (pdfmd_report.titles)
        import pdfmd_report.titles as report_titles
        repaired = report_titles.apply(core, repaired, chapter)
    if not shifted and repaired == original:
        yield md_path, False
        return
    with NamedTemporaryFile("w", encoding="utf-8", suffix=md_path.suffix,
                            prefix=f".{md_path.stem}.pdfmd-title-", dir=md_path.parent,
                            delete=False) as temporary:
        temporary.write(repaired)
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path, shifted
    finally:
        temporary_path.unlink(missing_ok=True)
