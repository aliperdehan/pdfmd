#!/usr/bin/env python3
"""Convert Markdown documents to PDF (or other formats) with Pandoc.

Examples:
    pdfmd report
    pdfmd slides -p
    pdfmd /path/to/report.md -d
    pdfmd Downloads -b -f "DejaVu Serif"
    pdfmd Downloads -b --recursive
    pdfmd book -r -o book.pdf
    pdfmd chapter.md -y metadata.yaml
    pdfmd book -r -y
    pdfmd notes.md -o notes.html
    pdfmd notes.md --to typst -o notes.typ
    pdfmd slides.qmd

Input formats:
    Only .md is ever searched for automatically (bare-name lookup, -b/--batch,
    -r/--report/--book). Any other format Pandoc can read -- .html, .tex,
    .txt, .rst, .docx, etc. -- works too, but only when given as a full
    filename with its real extension, e.g. `pdfmd notes.tex`. Pandoc infers
    the reader from that extension on its own; --from overrides it for the
    rare case Pandoc guesses wrong (no short flag: -f is already --font).
    .qmd (Quarto) is a special case: it's handed off to the `quarto` CLI
    instead of Pandoc, since Pandoc can't execute Quarto's R/Python/Julia
    code chunks and would silently drop figures and computed output.

Output formats:
    Default is PDF. Ask for something else with --to FORMAT (any Pandoc
    writer name: html, latex/tex, typst, plain/txt, docx, ...), or just give
    -o/--out a recognized extension (single-file/report modes only -- batch's
    -o is a directory) -- `-o notes.html` needs no separate --to. An explicit
    --to always wins over the filename. A PDF engine (-e/--engine, or the
    fallback list below) is only relevant, and only required to be installed,
    when the target is actually PDF. A document can request its own default
    engine with a `pdfmd-options: {pdf-engine: lualatex}` (or `engine:`)
    front-matter key -- one engine name/alias, or a family keyword (`tex`,
    `html`, `typst`) to restrict automatic fallback to that paradigm instead
    of one specific engine, e.g. `pdf-engine: tex` for a chemfig-heavy
    document that must never fall back to an HTML engine that can't render
    its LaTeX macros, or `pdf-engine: html` for a plain document that should
    never pay for a slow LaTeX run. The older bare top-level `pdf-engine:`/
    `engine:` spelling (no `pdfmd-options:` nesting) still works unchanged
    for documents already using it, but `pdfmd-options:` is where a new
    document should put this -- Pandoc itself doesn't read `pdf-engine`/
    `engine` at all, unlike e.g. `documentclass:`/`header-includes:`, which
    are real Pandoc keys and stay bare. The document's own front matter is
    checked first; if it sets nothing, each of its linked --metadata-file
    YAML files (auto-discovered or -y) is checked next, in order, for the
    same key -- a shared metadata.yaml can set `pdf-engine: tex` once for
    every document that finds it, and any one document can still override
    it in its own front matter. Consulted only when -e/--engine is absent
    from the command line; report mode reads it from the first file, batch
    mode reads each file's own (and its own metadata). A *bare* `-e` (no
    value) always means the full, unrestricted fallback chain, overriding
    even a family restriction from either source -- the escape hatch when a
    family-restricted document needs output produced at all costs.

    On LaTeX-family engines, a document with no geometry/margin setting at
    all (no -V, no `geometry:`/`margin:` in its own front matter, a linked
    --metadata-file, or a raw ``\\usepackage{geometry}``/``\\geometry{...}``
    call already in its own header-includes or an auto-included preamble)
    automatically gets `geometry:margin=1in` -- LaTeX's article-class
    default margins are much wider than that, and the preamble/header-
    includes check avoids a fatal "Option clash" from loading the geometry
    package twice with different options. Likewise, a document that
    actually has inline code or a fenced code block, but no `monofont:`,
    gets `JetBrains Mono` for it.

    A document with no `mainfont:` and no -f/--font is first tried with
    STIX Two Text (better Unicode/math coverage than LaTeX's own Latin
    Modern for most prose); if that run reports missing glyphs, it's
    silently retried with DejaVu Serif instead, which has near-total
    coverage of the arrows/comparison-operator/Greek symbols that plain
    Unicode notes tend to use in running text. -f/--font, or the
    document's own `mainfont:`, always wins outright over both.

Batch mode (-b) and report/book mode (-r) only look in the given directory
by default; add --recursive to also include subdirectories.

Reader selection for a Markdown source:
    A document with no `---` YAML front matter at all -- ordinary
    GitHub-Flavored Markdown, not written with Pandoc's own stricter rules
    in mind -- is read as `gfm` instead of Pandoc's default `markdown`.
    This matters beyond blank-line tolerance around headings/lists: Pandoc's
    default reader also forces every pipe-table column to an equal width
    fraction, which can bloat a table-heavy document across many extra
    pages; `gfm` sizes columns to their content instead. `+definition_lists`
    is restored automatically when a document uses that syntax (`Term\n:
    definition`), which `gfm` alone can't parse; a document using
    `@citation` syntax instead falls back to the plain `markdown` reader
    entirely, since Pandoc has no way to add citation parsing onto `gfm`.
    A document that already has front matter is assumed to already target
    Pandoc and is left on the default reader -- as is anything given
    explicitly via --from. Report mode decides this once, from the first
    file, same as its documentclass/pdf-engine front matter; batch and
    single-file modes decide it per file.

    A document with no front matter whose very first line is a bare `#
    Title` also gets that heading promoted into real Pandoc title metadata
    (rendered as an actual title page/`<title>`, instead of an extra,
    numbered top-level section), with the rest of its headings shifted up a
    level to match.

Suppressing pdfmd's own defaults, and the `pdfmd-options:` front-matter block:
    --no-auto turns off the reader/title/margin/mainfont/monofont/tablewidth
    defaults documented above, plus pdfmd's own file-discovery (auto-attached
    metadata YAML, LaTeX preambles, Lua filters) -- bare --no-auto disables
    all of it; --no-auto KIND [KIND ...] disables only those. KIND is one of:
    reader, title, margin, mainfont, monofont, font (mainfont+monofont),
    tablewidth, metadata/yaml (the auto-discovered --metadata-file),
    preamble/tex (auto-included preamble.tex etc.), lua (auto-included
    <stem>.lua/nulabreport.lua), files (metadata+preamble+lua). An explicit
    -y/-H/-f/-V/--from still always wins over --no-auto metadata/preamble
    regardless of this flag -- it only stops pdfmd from filling in or
    discovering what's otherwise unset.

    A document can ask for the same thing itself, without the caller having
    to remember a flag, via a `pdfmd-options:` front-matter block -- the
    namespace for settings that are entirely pdfmd's own invention and mean
    nothing to Pandoc itself (unlike e.g. `documentclass:`/`chapter:`/
    `header-includes:`, which are real Pandoc/report-assembly keys and stay
    bare at the top level):

        ---
        pdfmd-options:
          no-auto: [monofont, margin]
          pdf-engine: lualatex
        ---

    Two keys live there today: `no-auto` (same KIND names as --no-auto
    above, plus `true`/`all` for everything or a single bare name --
    additive with a CLI --no-auto, whichever source disables a given kind
    wins for that kind) and `pdf-engine`/`engine` (same values as
    -e/--engine; see frontmatter_engine()'s docstring for why this one in
    particular moved here rather than staying a bare top-level key -- the
    older bare spelling still works for documents already using it). Both
    require PyYAML and a document that already has a `---` block; silently
    ignored (not an error) if PyYAML isn't installed.
"""
# Versioned from here on -- see ~/dev/python-projects/CHANGELOG-pdfmd.md.
# This script began as a one-line `pandoc file.md -o file.pdf` wrapper and
# was revised many times since, across ChatGPT, ChatGPT Codex, Claude Chat,
# Cowork, and Claude Code sessions, with no version marker or changelog kept
# at any point -- there is no reliable "v1.x" history left to backfill,
# only inconsistent backups/pdfmd.py.bak-* snapshots from a handful of
# points in that history. Rather than fabricate a precise-looking but
# unreliable 1.x history from those gaps, versioning restarts at 2.0.0 here
# (2026-09-16, Ali's call) as an honest baseline: this is where real
# changelog tracking begins, not a claim about how many changes preceded it.
PDFMD_VERSION = "2.1.0"
import argparse
from fnmatch import fnmatchcase
import re
import shlex
import subprocess
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from shutil import which
from tempfile import NamedTemporaryFile
from textwrap import dedent
from typing import Iterator

try:
    import yaml
except ImportError:
    yaml = None

PREAMBLE = r"\setcounter{MaxMatrixCols}{20}"
DEFAULT_FONT = "DejaVu Serif"
# Tried first, when neither the document nor -f/--font names a mainfont:
# better Unicode/math coverage and typography than LaTeX's own Latin Modern
# for most prose. DEFAULT_FONT (DejaVu) is the deliberate fallback for
# whatever glyphs it's missing -- see the retry in convert_one(). Pandoc's
# own mainfontfallback mechanism (per-glyph automatic fallback within one
# compile) was tried and rejected here: it silently no-ops under xelatex and
# crashes lualatex outright in this environment, so the existing
# detect-then-retry-with-a-different-mainfont path is what actually works.
PREFERRED_FONT = "STIX Two Text"
DEFAULT_MONOFONT = "JetBrains Mono"
DEFAULT_MARGIN = "1in"
DEFAULT_VARS = []
AUTO_METADATA_DISABLED = object()

# --no-auto KIND values, and its "font" shorthand for both font kinds at
# once. See build_parser()'s --no-auto help text for what each kind does.
NO_AUTO_KINDS = frozenset({
    "reader", "title", "margin", "mainfont", "monofont", "font", "tablewidth",
    "metadata", "yaml", "preamble", "tex", "lua", "files",
})
NO_AUTO_ALIASES = {
    "font": frozenset({"mainfont", "monofont"}),
    "yaml": frozenset({"metadata"}),
    "tex": frozenset({"preamble"}),
    "files": frozenset({"metadata", "preamble", "lua"}),
}


def auto_disabled(no_auto: list[str] | None, kind: str) -> bool:
    """Return whether --no-auto turns off one of pdfmd's own defaults.

    ``no_auto`` is args.no_auto: None (flag absent) never disables anything;
    ``[]`` (bare --no-auto) disables everything; a non-empty list disables
    only the named kinds (expanding the "font" alias to mainfont+monofont).
    """
    if no_auto is None:
        return False
    if not no_auto:
        return True
    return kind in no_auto or any(kind in NO_AUTO_ALIASES.get(item, ()) for item in no_auto)


def merge_no_auto(cli: list[str] | None, doc: list[str] | None) -> list[str] | None:
    """Union a CLI --no-auto with a document's own pdfmd-options.no-auto.

    Additive, never a replacement: a kind named by either source is
    disabled; ``[]`` (bare CLI --no-auto, or ``no-auto: true`` in the
    document) from either side disables everything, regardless of what the
    other side says.
    """
    if cli is None and doc is None:
        return None
    if cli == [] or doc == []:
        return []
    return sorted({*(cli or []), *(doc or [])})


def frontmatter_pdfmd_options(md_path: Path) -> dict:
    """Parse a document's own ``pdfmd-options:`` front-matter block.

    A real YAML parse (not the regex sniffing the rest of this script uses
    for single scalar keys) because this block can be an arbitrarily
    nested mapping -- ``no-auto: [monofont, margin]`` and
    ``no-auto: true`` both have to parse correctly, not just be detected.
    Returns {} if there's no front matter, no ``pdfmd-options`` key, the
    front matter doesn't parse as YAML, or PyYAML isn't installed --
    document-level pdfmd-options are optional sugar, not a hard dependency
    of the rest of the script.
    """
    if yaml is None:
        return {}
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return {}
    try:
        data = yaml.safe_load(front_matter.group(1))
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    options = data.get("pdfmd-options")
    return options if isinstance(options, dict) else {}


def frontmatter_no_auto(md_path: Path) -> list[str] | None:
    """Read ``pdfmd-options:\n  no-auto: ...`` from a document's own front
    matter, in any of the shapes --no-auto itself accepts: a boolean
    (``true``/``yes``/``on``/``all`` disables everything, ``false`` leaves
    pdfmd's defaults alone), a bare kind name, or a YAML list of kinds.
    """
    value = frontmatter_pdfmd_options(md_path).get("no-auto")
    if value is None:
        return None
    if isinstance(value, bool):
        return [] if value else None
    if isinstance(value, str):
        if value.casefold() in {"true", "yes", "on", "all"}:
            return []
        if value.casefold() in {"false", "no", "off"}:
            return None
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return None


def effective_no_auto(md_path: Path, cli_no_auto: list[str] | None) -> list[str] | None:
    """Merge a CLI --no-auto with md_path's own pdfmd-options.no-auto, and
    validate the result. The one place this logic lives -- both convert_one
    and main()'s pre-discovery gating (metadata/preamble auto-discovery
    happens before convert_one is even called) need the same answer for
    the same file.
    """
    merged = merge_no_auto(cli_no_auto, frontmatter_no_auto(md_path))
    if merged:
        unknown = sorted(set(merged) - NO_AUTO_KINDS)
        if unknown:
            raise SystemExit(f"{md_path}: unknown pdfmd-options.no-auto kind(s): {', '.join(unknown)}. "
                             f"Valid: {', '.join(sorted(NO_AUTO_KINDS))}")
    return merged


# Auto-applied on every LaTeX-family render (see table_width_filter() below).
# Pandoc's LaTeX writer only wraps pipe-table cells when every column has an
# explicit width; a table with none (ColWidth "default" -- what gfm's reader
# always produces, see resolve_from_format()) instead gets plain unwrapped
# `l`/`c`/`r` columns, so a long cell just runs past the page margin instead
# of breaking. This filter leaves any table that already has explicit widths
# alone, and for one that doesn't AND whose content is actually wide enough
# to risk overflowing the page, sizes each column proportionally to its
# longest cell's text length (spreading a spanning cell's length evenly
# across the columns it covers) instead of Pandoc's own default-`markdown`
# behaviour of forcing every column to the same equal fraction regardless of
# content -- see resolve_from_format()'s docstring for why that's also worth
# avoiding. A floor keeps a column with only short labels from collapsing to
# unreadable thinness next to a verbose neighbor.
#
# BUG, found and fixed 2026-09-16 (Ali, via a nulabreport/QCA report): this
# used to fire on EVERY table with any default-width column, regardless of
# whether the table's own content came anywhere near overflowing -- a short
# 4-column numeric table ("Sample #" / four-digit masses / a percentage) got
# stretched across the FULL page width for no reason, fighting a downstream
# package Lua filter (nulabreport.lua) that deliberately sizes such a table
# to its natural content width instead. The intent (see the paragraph above,
# unchanged) was always "rescue a table that would otherwise overflow," not
# "give every unwidthed table an opinion" -- this was never meant to fire on
# a table that already fits comfortably. Fixed with a real, if approximate,
# overflow check: estimate the table's total natural width by summing each
# column's longest-cell character count (same measurement already used for
# the proportions below) and comparing against CHAR_BUDGET, a rough
# characters-per-line figure for this project's own default document shape
# (12pt serif body text, ~1in margins on A4/Letter -- see DEFAULT_MARGIN).
# This is deliberately an ESTIMATE, not a real width computation (Pandoc's
# Lua filters run before any font is ever measured, so an exact figure isn't
# available here at all) -- it only needs to be good enough to distinguish
# "a handful of short numeric columns" from "a table with real prose cells,"
# which a raw character count comfortably does. A table with an unusual
# fontsize/geometry front-matter override is not specially accounted for;
# revisit CHAR_BUDGET (or make it geometry-aware) if that turns out to
# matter in practice, rather than assuming this estimate transfers exactly.
TABLE_WIDTH_LUA_FILTER = r"""
local MIN_FRACTION = 0.08
-- ~95 characters is a commonly-cited rule of thumb for how much 12pt serif
-- text fits on one line within a standard 1in-margin A4/Letter page -- see
-- the long comment above this filter's Python source for what this is and
-- is not measuring, and why an estimate is all that's available here.
local CHAR_BUDGET = 95
-- Rough per-column overhead (rule padding + inter-column gap) so a table
-- with many columns, each individually short, doesn't dodge the budget
-- check on a technicality -- \tabcolsep-scale, not a real measurement.
local PER_COLUMN_OVERHEAD = 3

local function cell_length(cell)
  return #pandoc.utils.stringify(cell.contents)
end

local function scan_row(row, max_len)
  for i, cell in ipairs(row.cells) do
    local span = cell.col_span or 1
    local share = cell_length(cell) / span
    for k = i, math.min(i + span - 1, #max_len) do
      if share > max_len[k] then max_len[k] = share end
    end
  end
end

function Table(tbl)
  local ncols = #tbl.colspecs
  if ncols == 0 then return nil end
  local has_default = false
  for _, spec in ipairs(tbl.colspecs) do
    if spec[2] == nil then has_default = true end
  end
  if not has_default then return nil end

  local max_len = {}
  for i = 1, ncols do max_len[i] = 1 end
  for _, row in ipairs(tbl.head.rows) do scan_row(row, max_len) end
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.head) do scan_row(row, max_len) end
    for _, row in ipairs(body.body) do scan_row(row, max_len) end
  end

  local total = 0
  for i = 1, ncols do total = total + max_len[i] end
  -- The table's own content already fits a reasonable line width -- leave
  -- it at its natural size (nil widths preserved) rather than opinion-ate
  -- a table nobody asked to have stretched or rebalanced.
  if total + ncols * PER_COLUMN_OVERHEAD <= CHAR_BUDGET then return nil end

  local fractions = {}
  for i = 1, ncols do fractions[i] = max_len[i] / total end
  local sum_clamped = 0
  for i = 1, ncols do
    if fractions[i] < MIN_FRACTION then fractions[i] = MIN_FRACTION end
    sum_clamped = sum_clamped + fractions[i]
  end
  for i = 1, ncols do fractions[i] = fractions[i] / sum_clamped end

  for i, spec in ipairs(tbl.colspecs) do
    tbl.colspecs[i] = {spec[1], fractions[i]}
  end
  return tbl
end
"""

# Engines are tried in this order only when the user did not request one.
# An explicit --engine is never overridden.
PDF_ENGINES = (
    "lualatex", "xelatex", "pdflatex", "latexmk", "tectonic", "typst",
    "weasyprint", "wkhtmltopdf", "pagedjs-cli", "prince", "context",
    "groff", "pdfroff",
)
ENGINE_ALIASES = {
    "1": "lualatex", "lua": "lualatex",
    "2": "xelatex", "xe": "xelatex",
    "3": "pdflatex", "pdf": "pdflatex",
    "4": "latexmk", "mk": "latexmk",
    "5": "tectonic", "tect": "tectonic",
    "6": "typst",
    "7": "weasyprint", "weasy": "weasyprint",
    "8": "wkhtmltopdf", "wkhtml": "wkhtmltopdf",
    "9": "pagedjs-cli", "pagedjs": "pagedjs-cli",
    "10": "prince",
    "11": "context",
    "12": "groff",
    "13": "pdfroff", "roff": "pdfroff",
}
LATEX_ENGINES = frozenset({"lualatex", "xelatex", "pdflatex", "latexmk", "tectonic", "context"})
PREAMBLE_FILENAMES = ("preamble.tex", "latex-preamble.tex")

# Engines that share the same underlying TeX engine, grouped by family. If one
# member of a family fails, the others are very unlikely to succeed on the
# same document (they see the same fonts, the same package errors, the same
# Unicode input) so the fallback loop skips straight to a genuinely different
# backend instead of wasting a retry. xelatex/tectonic share XeTeX;
# lualatex/context (MkIV) share LuaTeX; pdflatex/latexmk share pdfTeX --
# latexmk's own default engine, though a local .latexmkrc can change that.
# Anything not listed here is assumed to be its own independent family.
ENGINE_FAMILY = {
    "pdflatex": "pdftex",
    "latexmk": "pdftex",
    "lualatex": "luatex",
    "context": "luatex",
    "xelatex": "xetex",
    "tectonic": "xetex",
}

# Coarse rendering-paradigm groups -- distinct from ENGINE_FAMILY above, which
# groups by underlying TeX implementation for skip-after-failure purposes
# *within* one paradigm. These scope which engines are even eligible
# candidates in the first place, so e.g. a chemfig/nulabreport document that
# requests the "tex" family never falls back to an HTML engine that cannot
# render its LaTeX macros at all, and a plain document that requests "html"
# never pays for a slow LaTeX run it doesn't need. "tex" is defined as
# exactly the members of LATEX_ENGINES, in PDF_ENGINES order, so the two
# can't drift apart. Selected via -e/--engine or a pdf-engine front-matter
# key, same as a single engine name -- see select_engines().
ENGINE_GROUPS: dict[str, tuple[str, ...]] = {
    "tex": tuple(engine for engine in PDF_ENGINES if engine in LATEX_ENGINES),
    "html": ("weasyprint", "wkhtmltopdf", "pagedjs-cli", "prince"),
    "typst": ("typst",),
}


def installed_engines() -> list[str]:
    """Return PDF engines that are currently executable, in fallback order."""
    return [engine for engine in PDF_ENGINES if which(engine)]


def select_engines(requested: str | None, presentation: bool, label: str = "--engine") -> list[str]:
    """Select installed engines in fallback order, or explain what is missing.

    ``requested`` may be a single engine name/alias (as before), or one of
    ENGINE_GROUPS's family keywords ("tex", "html", "typst"), which restricts
    automatic fallback to that family's installed members in PDF_ENGINES
    order, instead of picking one specific engine or falling back through
    every installed engine regardless of paradigm.

    ``label`` only shapes the incompatibility/not-installed messages below
    (the single-engine not-found error is already source-agnostic) -- it
    lets a front-matter-sourced request name itself instead of claiming to
    be a CLI flag it never was.
    """
    if requested:
        group = ENGINE_GROUPS.get(requested.casefold())
        if group is not None:
            family = requested.casefold()
            installed_in_group = [engine for engine in group if which(engine)]
            if not installed_in_group:
                raise SystemExit(
                    f"{label} restricted to the '{family}' engine family, but none of "
                    + ", ".join(group) + " is installed. Install one, or pass a bare "
                    "-e for the full, unrestricted fallback chain."
                )
            if presentation:
                candidates = [engine for engine in installed_in_group if engine in LATEX_ENGINES]
                if not candidates:
                    raise SystemExit(
                        f"{label} restricted to the '{family}' engine family, which cannot "
                        "render Beamer slides (-p/--presentation): Pandoc's Beamer writer "
                        "requires a LaTeX/ConTeXt engine, one of "
                        + ", ".join(sorted(LATEX_ENGINES))
                    )
                return candidates
            return installed_in_group

        requested = ENGINE_ALIASES.get(requested.casefold(), requested)
        if presentation and requested not in LATEX_ENGINES:
            raise SystemExit(
                f"{label} requested {requested}, which cannot render Beamer slides "
                "(-p/--presentation): Pandoc's Beamer writer requires a LaTeX/ConTeXt "
                "engine, one of " + ", ".join(sorted(LATEX_ENGINES))
            )
        if which(requested):
            return [requested]
        raise SystemExit(
            f"Requested PDF engine '{requested}' was not found on PATH. "
            "Install it or choose one listed by --check-dependencies."
        )

    candidates = installed_engines()
    if presentation:
        # Pandoc's Beamer writer requires a TeX-family engine.
        candidates = [engine for engine in candidates if engine in LATEX_ENGINES]
    if candidates:
        return candidates

    kind = "a LaTeX/ConTeXt engine for Beamer" if presentation else "a PDF engine"
    raise SystemExit(
        f"No supported {kind} was found. Install Pandoc and one of: "
        + ", ".join(PDF_ENGINES)
        + ". Run --check-dependencies for a status report."
    )


def resolve_engines(md_path: Path, cli_engine: str | None, engines: list[str],
                    presentation: bool, target_format: str,
                    metadata_files: list[Path] = ()) -> list[str]:
    """Fall back to a document's own pdf-engine/engine setting, or its
    linked metadata file's.

    Only consulted when -e/--engine was not given AT ALL on the CLI
    (cli_engine is None). A *bare* -e (cli_engine == "", from nargs="?" with
    const="") is itself an explicit request for the full, unrestricted
    fallback chain -- checked with ``is not None`` rather than truthiness so
    it is never confused with "flag absent," and it overrides a front-matter
    engine/family restriction the same way a specific -e value already does
    (both go through the top-level ``engines`` this function is handed,
    already computed by select_engines(args.engine, ...) in main()). Also
    skipped whenever the target isn't PDF (no engine is involved).

    ``metadata_files`` (a document's already-resolved --metadata-file list,
    from find_metadata -- empty unless the caller already has it) lets
    frontmatter_engine fall through to a course-wide default there when the
    document's own front matter sets none; see its docstring.
    """
    if cli_engine is not None or target_format != "pdf":
        return engines
    requested = frontmatter_engine(md_path, metadata_files)
    if not requested:
        return engines
    resolved = select_engines(requested, presentation,
                              label=f"pdf-engine setting for {md_path.name}")
    print(f"AUTO ENGINE  {md_path}: " + " -> ".join(resolved))
    return resolved


def dependency_report() -> bool:
    """Print executable availability and return whether conversion can run."""
    pandoc = which("pandoc")
    print(f"{'OK  ' if pandoc else 'MISS'}  pandoc" + (f"  ({pandoc})" if pandoc else ""))
    for number, engine in enumerate(PDF_ENGINES, start=1):
        path = which(engine)
        print(f"{'OK  ' if path else 'MISS'}  {number}. {engine}" + (f"  ({path})" if path else ""))
    quarto = which("quarto")
    print(f"{'OK  ' if quarto else 'MISS'}  quarto (only needed for .qmd files)"
         + (f"  ({quarto})" if quarto else ""))
    return bool(pandoc and installed_engines())


def has_header_include_option(options: list[str]) -> bool:
    """Return whether the caller already explicitly supplied Pandoc's -H option."""
    return any(option in {"-H", "--include-in-header"}
               or option.startswith("--include-in-header=")
               for option in options)


def has_shift_heading_option(options: list[str]) -> bool:
    """Return whether the caller already explicitly supplied --shift-heading-level-by."""
    return any(option == "--shift-heading-level-by"
               or option.startswith("--shift-heading-level-by=")
               for option in options)


def is_latex_preamble(path: Path) -> bool:
    """Accept preamble snippets, but reject complete documents and TikZ images."""
    text = path.read_text(encoding="utf-8-sig")
    forbidden = r"\\(?:documentclass|begin\s*\{document\}|end\s*\{document\}|begin\s*\{tikzpicture\})"
    return not bool(re.search(forbidden, text, re.IGNORECASE))


def preamble_candidates(directory: Path, document_stem: str) -> list[Path]:
    """Return intentionally named generic and document-specific preambles."""
    stem = document_stem.casefold()
    candidates: list[Path] = []
    for path in directory.glob("*.tex"):
        name = path.name.casefold()
        if name in PREAMBLE_FILENAMES:
            candidates.append(path)
            continue
        if (name == f"{stem}.tex" or name in {f"{stem}_preamble.tex", f"{stem}-preamble.tex"}
                or re.fullmatch(r"(?:latex-)?preamble-[^.]+\.tex", name)):
            candidates.append(path)
    # Generic files load first; document-specific settings then override them.
    def priority(path: Path) -> tuple[int, str]:
        name = path.name.casefold()
        if name == "preamble.tex":
            return (0, name)
        if name == "latex-preamble.tex":
            return (1, name)
        if name.startswith("preamble-") or name.startswith("latex-preamble-"):
            return (2, name)
        return (3, name)
    return sorted(candidates, key=priority)


def find_preambles(directory: Path, document_stem: str, options: list[str]) -> list[Path]:
    """Find safe, intentionally named LaTeX preambles beside a document."""
    if has_header_include_option(options):
        return []
    return [path.resolve() for path in preamble_candidates(directory, document_stem)
            if is_latex_preamble(path)]


def announce_preambles(preambles: list[Path]) -> None:
    for preamble in preambles:
        print(f"AUTO TEX   {preamble}")
    if len(preambles) > 1:
        print("WARN  Multiple preambles discovered; later files may override earlier definitions.",
              file=sys.stderr)


def wrap_latex_header_includes(text: str) -> str:
    """Protect literal YAML header-includes from Pandoc's Markdown parsing.

    A YAML literal block such as ``header-includes: |`` is parsed as Markdown.
    Therefore a LaTeX comment starting with ``%`` can be escaped to ``\\%``.
    Making the scalar a raw LaTeX fenced block preserves preamble commands.
    """
    front_matter = re.match(r"^(---\s*\n)(.*?)(\n(?:---|\.\.\.)\s*(?:\n|$))", text, re.DOTALL)
    if not front_matter:
        return text

    header = front_matter.group(2)
    lines = header.splitlines(keepends=True)
    rewritten: list[str] = []
    index = 0
    changed = False
    while index < len(lines):
        match = re.match(r"^(?P<indent>\s*)header-includes\s*:\s*\|[+-]?\s*(?:#.*)?(?:\r?\n)?$", lines[index])
        if not match:
            rewritten.append(lines[index])
            index += 1
            continue

        base_indent = len(match.group("indent"))
        block_start = index + 1
        index = block_start
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip(" \t")) <= base_indent:
                break
            index += 1
        block = "".join(lines[block_start:index])
        content = dedent(block)
        if re.search(r"(?m)^\s*```\{=latex\}\s*$", content):
            rewritten.extend(lines[block_start - 1:index])
            continue

        newline = "\r\n" if "\r\n" in block else "\n"
        child_indent = match.group("indent") + "  "
        wrapped = f"```{{=latex}}{newline}{content.rstrip()}{newline}```{newline}"
        indented = "".join(child_indent + line if line.strip() else line
                           for line in wrapped.splitlines(keepends=True))
        rewritten.append(lines[block_start - 1])
        rewritten.append(indented)
        changed = True

    if not changed:
        return text
    return front_matter.group(1) + "".join(rewritten) + front_matter.group(3) + text[front_matter.end():]


@contextmanager
def prepared_latex_inputs(paths: list[Path], latex_engine: bool) -> Iterator[list[Path]]:
    """Yield temporary, corrected inputs for LaTeX-family renders when needed."""
    temporary_paths: list[Path] = []
    prepared: list[Path] = []
    try:
        for path in paths:
            text = path.read_text(encoding="utf-8-sig")
            corrected = wrap_latex_header_includes(text) if latex_engine else text
            if corrected == text:
                prepared.append(path)
                continue
            with NamedTemporaryFile("w", encoding="utf-8", suffix=path.suffix,
                                    prefix=f".{path.stem}.pdfmd-", dir=path.parent,
                                    delete=False) as temporary:
                temporary.write(corrected)
                temporary_path = Path(temporary.name)
            temporary_paths.append(temporary_path)
            prepared.append(temporary_path)
        yield prepared
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)


def document_header_includes(text: str) -> str | None:
    """Return the LaTeX in a document's own ``header-includes:`` block.

    Pandoc feeds ``--include-in-header`` files into the very same
    ``header-includes`` template variable, and a variable set on the command
    line beats one set in metadata. So the moment a preamble is auto-included
    beside a document, a ``header-includes`` block in that document's own front
    matter is silently discarded. Extracting it here lets the caller re-append
    it as a second ``--include-in-header``, after the preambles, which is where
    a per-document override belongs.
    """
    front_matter = re.match(r"^(---\s*\n)(.*?)(\n(?:---|\.\.\.)\s*(?:\n|$))", text, re.DOTALL)
    if not front_matter:
        return None

    lines = front_matter.group(2).splitlines(keepends=True)
    index = 0
    while index < len(lines):
        match = re.match(r"^(?P<indent>\s*)header-includes\s*:\s*\|[+-]?\s*(?:#.*)?(?:\r?\n)?$", lines[index])
        if not match:
            index += 1
            continue
        base_indent = len(match.group("indent"))
        start = index + 1
        index = start
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip(" \t")) <= base_indent:
                break
            index += 1
        block = dedent("".join(lines[start:index])).strip()
        return block or None
    return None


# Front-matter keys that are not pandoc variables but that a LaTeX preamble may
# want. Each becomes \\renewcommand{\\<macro>}{<value>}, appended after the
# preambles so the preamble can supply a default with \\newcommand.
DOCUMENT_LATEX_KEYS = {
    "experiment": "LabExperiment",
    "group": "LabGroup",
    # title-page fields (nulabreport's `titlepage` layout); all optional
    "course": "LabCourse",
    "section": "LabSection",
    "instructor": "LabInstructor",
    "performed": "LabPerformed",
    "unknown": "LabUnknown",
    "unknowns": "LabUnknown",  # same macro; either spelling works, whichever
                                # reads right for a singular or plural value
}


def document_latex_definitions(md_path: Path) -> str:
    """Return \\renewcommand lines for the front-matter keys listed above."""
    lines = []
    for key, macro in DOCUMENT_LATEX_KEYS.items():
        value = frontmatter_value(md_path, key)
        if value:
            lines.append(f"\\renewcommand{{\\{macro}}}{{{value}}}")
    return "\n".join(lines)


@contextmanager
def document_header_file(md_path: Path, active: bool) -> Iterator[Path | None]:
    """Yield a temporary .tex holding the document's own preamble additions."""
    if not active:
        yield None
        return
    try:
        parts = [document_latex_definitions(md_path)]
        parts.append(document_header_includes(md_path.read_text(encoding="utf-8-sig")) or "")
    except OSError:
        parts = []
    block = "\n".join(part for part in parts if part)
    if not block:
        yield None
        return
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".tex",
                            prefix=f".{md_path.stem}.pdfmd-header-", dir=md_path.parent,
                            delete=False) as temporary:
        temporary.write(block + "\n")
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)



def find_lua_filters(md_path: Path, metadata_files: list[Path]) -> list[Path]:
    """Find Pandoc Lua filters that belong to a document, without guessing.

    Only two names are auto-applied: a filter matching the document's own stem
    (report.md -> report.lua) and "nulabreport.lua" beside the document or its
    metadata. Anything else has to be passed explicitly, so an unrelated .lua
    file sitting in a folder can never silently change a render.
    """
    directories: list[Path] = [md_path.parent]
    directories += [metadata.parent for metadata in metadata_files]
    wanted = (f"{md_path.stem}.lua", "nulabreport.lua")
    found: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        for name in wanted:
            candidate = (directory / name).resolve()
            if candidate.is_file() and candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
    return found


@contextmanager
def table_width_filter() -> Iterator[Path]:
    """Materialize TABLE_WIDTH_LUA_FILTER to a temp file for --lua-filter.

    Content is fixed (not document-specific), so this is just a plain
    temp file in the system tempdir rather than beside the document --
    unlike prepared_latex_inputs()'s temp files, nothing needs it to sit
    next to the source for relative paths to resolve.
    """
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".lua",
                            prefix="pdfmd-tablewidth-", delete=False) as temporary:
        temporary.write(TABLE_WIDTH_LUA_FILTER)
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


def latin_candidates(value: str) -> list[str]:
    """Return common Cyrillic spellings for a Latin name."""
    value = value.lower()
    replacements = (
        ("shch", "щ"), ("sch", "щ"), ("yo", "ё"), ("zh", "ж"),
        ("kh", "х"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
        ("yu", "ю"), ("ya", "я"), ("ai", "ай"), ("oi", "oй"), ("oy", "ой"),
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


def name_candidates(value: str) -> list[str]:
    value = Path(value).stem
    candidates = [value]
    if re.search("[А-Яа-яЁё]", value):
        candidates += cyrillic_candidates(value)
    else:
        candidates += latin_candidates(value)
    candidates = list(dict.fromkeys(candidates))
    return candidates + [f"Пробный {item}" for item in candidates]


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


def find_markdown(value: Path, recursive: bool = False) -> Path:
    # Always resolved to an absolute path: a relative path with a subdirectory
    # component (e.g. "sub/nested.md") would otherwise make Pandoc's cwd (set
    # to md_path.parent, so relative includes/images in the document resolve
    # correctly) and its source-file argument both relative to the ORIGINAL
    # cwd, which -- once the subprocess actually changes into that directory
    # -- silently doubles up into a nonexistent path (e.g. "sub/sub/nested.md").
    if value.exists() and value.is_file():
        return value.resolve()
    wildcard_match = find_wildcard_markdown(value)
    if wildcard_match:
        return wildcard_match.resolve()
    directory = value if value.is_dir() else Path.cwd()
    requested = value.name if value.suffix != ".pdf" else value.stem
    requested = Path(requested).stem
    search_dirs = [directory]
    if recursive:
        search_dirs = [directory] + [item for item in directory.rglob("*") if item.is_dir()]
    files = {
        unicodedata.normalize("NFC", file.stem).casefold(): file
        for folder in search_dirs for file in folder.glob("*.md")
    }
    for candidate in name_candidates(requested):
        normalized = unicodedata.normalize("NFC", candidate).casefold()
        if normalized in files:
            return files[normalized].resolve()
    available = ", ".join(sorted(files))
    raise FileNotFoundError(f"Could not find Markdown file for '{value}'. Available: {available or 'none'}")


def has_mainfont(md_path: Path, variables: list[str]) -> bool:
    if any(variable.startswith("mainfont=") for variable in variables):
        return True
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    return bool(front_matter and re.search(r"^mainfont\s*:", front_matter.group(1), re.MULTILINE))


LATEX_GEOMETRY_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\bgeometry\b[^}]*\}|\\geometry\s*\{")


def has_latex_geometry(text: str) -> bool:
    """Detect a raw ``\\usepackage{geometry}``/``\\geometry{...}`` call.

    This is a plain text search across the whole document, not just an
    extracted header-includes block -- a bare word "geometry" in prose can
    never accidentally match either LaTeX-command pattern, so scanning the
    raw file is safe and doesn't need to isolate the YAML value first.
    """
    return bool(LATEX_GEOMETRY_RE.search(text))


def has_geometry(md_path: Path, variables: list[str], metadata_files: list[Path] = (),
                 preamble_files: list[Path] = ()) -> bool:
    """Return whether a page-margin setting already exists somewhere Pandoc
    would see it: a -V variable (``geometry=...``, the nested
    ``geometry:...`` form, or a bare ``margin=...``), the document's own
    front matter (``geometry:``/``margin:``, scalar or a YAML block list
    like a ``top:``/``bottom:``/``left:``/``right:`` breakdown -- either
    form starts with a ``geometry:`` line, which is all the check looks
    for), a linked --metadata-file that sets either, or a raw LaTeX
    ``\\usepackage{geometry}``/``\\geometry{...}`` call already present in
    the document's own header-includes or an auto-included preamble.

    That last check matters because DEFAULT_MARGIN is injected as a Pandoc
    ``-V geometry:...`` variable, which becomes another
    ``\\usepackage[...]{geometry}`` call in the rendered LaTeX (Pandoc's own
    default template). Loading the same package twice with two different,
    non-empty option lists is a fatal "Option clash" error in LaTeX, so a
    preamble or header-includes that already loads ``geometry`` itself has
    to suppress our own injection rather than error out at compile time.
    Only LaTeX-family engines use the ``geometry`` package this backs; see
    DEFAULT_MARGIN.
    """
    if any(variable.startswith(("geometry=", "geometry:", "margin="))
           for variable in variables):
        return True
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if front_matter and re.search(r"^(?:geometry|margin)\s*:", front_matter.group(1), re.MULTILINE):
        return True
    if any(re.search(r"(?m)^(?:geometry|margin)\s*:", metadata_file.read_text(encoding="utf-8-sig"))
           for metadata_file in metadata_files):
        return True
    if has_latex_geometry(text):
        return True
    return any(has_latex_geometry(preamble.read_text(encoding="utf-8-sig"))
               for preamble in preamble_files)


def has_monofont(md_path: Path, variables: list[str]) -> bool:
    if any(variable.startswith("monofont=") for variable in variables):
        return True
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    return bool(front_matter and re.search(r"^monofont\s*:", front_matter.group(1), re.MULTILINE))


def has_code_spans(text: str) -> bool:
    """Detect inline code or fenced code blocks -- the only things Pandoc's
    LaTeX writer actually sets in the monofont. A bare backtick covers both
    (a fence is just 3+ backticks), plus the rarer ``~~~`` fence style.
    """
    return "`" in text or bool(re.search(r"(?m)^\s{0,3}~~~", text))


def missing_glyph_warning(output: str) -> bool:
    return bool(re.search(
        r"missing character|Missing character|Unicode character .* not set|font .* not found",
        output,
    ))


def contains_citations(md_path: Path) -> bool:
    """Detect bracketed, bare, and suppress-citation Pandoc syntax."""
    text = md_path.read_text(encoding="utf-8-sig")
    return bool(re.search(r"(?<![\w@])(?:-?@[-\w:.]+)", text))


def has_yaml_frontmatter(text: str) -> bool:
    return bool(re.match(r"^---\s*\n", text))


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


def has_definition_list(text: str) -> bool:
    """Detect Pandoc's ``Term\\n: definition`` syntax.

    GFM's reader can't parse this at all -- it has to be added back on top
    as ``+definition_lists`` (Pandoc accepts that combination even though it
    rejects e.g. ``gfm+citations``; see resolve_from_format()).
    """
    return bool(re.search(r"(?m)^:[ \t]", text))


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
    """
    if cli_from:
        return cli_from, None
    text = md_path.read_text(encoding="utf-8-sig")
    if has_yaml_frontmatter(text) or has_percent_title_block(text):
        return None, None
    if metadata_files:
        names = ", ".join(metadata_file.name for metadata_file in metadata_files)
        return None, (f"{md_path}: no YAML front matter, but {names} is linked; "
                      "keeping the default markdown reader instead of gfm")
    if contains_citations(md_path):
        return None, (f"{md_path}: no YAML front matter, but it uses @citation syntax "
                      "gfm can't parse; keeping the default markdown reader")
    reader = "gfm+definition_lists" if has_definition_list(text) else "gfm"
    return reader, f"{md_path}: no YAML front matter; reading as {reader}"


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
    if has_yaml_frontmatter(text) or has_external_metadata or has_percent_title_block(text):
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
                          disabled: bool = False) -> Iterator[tuple[Path, bool]]:
    """Yield a temporary copy of ``md_path`` with promote_bare_title() applied,
    and whether that happened (the caller needs to know to also shift
    heading levels). Yields ``md_path`` itself, unchanged, when nothing to
    promote was found, or when ``disabled`` (--no-auto title/bare) skips it.
    """
    if disabled:
        yield md_path, False
        return
    text = md_path.read_text(encoding="utf-8-sig")
    corrected, shifted = promote_bare_title(text, has_external_metadata=bool(metadata_files))
    if not shifted:
        yield md_path, False
        return
    with NamedTemporaryFile("w", encoding="utf-8", suffix=md_path.suffix,
                            prefix=f".{md_path.stem}.pdfmd-title-", dir=md_path.parent,
                            delete=False) as temporary:
        temporary.write(corrected)
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path, True
    finally:
        temporary_path.unlink(missing_ok=True)


def frontmatter_value(md_path: Path, key: str) -> str | None:
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    match = re.search(rf"^{re.escape(key)}\s*:\s*(.*?)\s*$", front_matter.group(1), re.MULTILINE)
    return match.group(1).strip().strip("'\"") if match else None


def metadata_file_yaml(path: Path) -> dict:
    """Parse a --metadata-file's own YAML content as a plain dict.

    Unlike a document's front matter, a --metadata-file has no ``---``/
    ``...`` fence to find first -- the whole file already IS the YAML
    mapping Pandoc's own ``--metadata-file`` reads. Returns {} on a parse
    error, a non-mapping top level, or no PyYAML -- same permissiveness as
    frontmatter_pdfmd_options, since a metadata file's pdfmd-only settings
    are optional sugar, never a hard dependency.
    """
    if yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def frontmatter_engine(md_path: Path, metadata_files: list[Path] = ()) -> str | None:
    """Read the effective default PDF engine: the document's own front
    matter first, then (in order) each linked --metadata-file's own
    ``pdf-engine``/``pdfmd-options`` as a course-wide default the document
    can still override. This is what lets nulabreport's shared
    metadata.yaml -- symlinked into every course folder -- set
    ``pdfmd-options: {pdf-engine: tex}`` once for every report that finds
    it, instead of repeating the block in each report's own front matter.

    ``pdf-engine`` mirrors Pandoc's own ``--pdf-engine`` flag name; ``engine``
    is accepted as a shorter alias. A single engine name/alias/numeric
    shortcut, or an ENGINE_GROUPS family keyword ("tex", "html", "typst") to
    restrict fallback to that paradigm -- same values -e/--engine accepts.

    Unlike documentclass/class or header-includes, ``pdf-engine``/``engine``
    mean nothing to Pandoc itself -- they're entirely pdfmd's own invention
    -- so this checks the nested ``pdfmd-options:`` spelling first (where a
    new document should put pdfmd-only settings) and falls back to the
    older bare top-level key for documents already written with that
    spelling, which keeps working unchanged. A metadata file gets the same
    nested-then-bare check, in the order metadata_files is given (find_metadata's
    own order); this deliberately does NOT extend to `no-auto` -- no-auto
    decides whether metadata auto-discovery runs at all, so it cannot also
    depend on the metadata file that discovery itself would find.
    """
    options = frontmatter_pdfmd_options(md_path)
    value = options.get("pdf-engine") or options.get("engine")
    if value is not None:
        return str(value)
    own = frontmatter_value(md_path, "pdf-engine") or frontmatter_value(md_path, "engine")
    if own is not None:
        return own
    for metadata_file in metadata_files:
        data = metadata_file_yaml(metadata_file)
        options = data.get("pdfmd-options")
        value = (options.get("pdf-engine") or options.get("engine")) if isinstance(options, dict) else None
        if value is None:
            top = data.get("pdf-engine") or data.get("engine")
            value = str(top) if top is not None else None
        if value is not None:
            return str(value)
    return None


def yaml_autoinclude(path: Path) -> bool:
    """Return whether automatic discovery may select this YAML file."""
    text = path.read_text(encoding="utf-8-sig")
    return not bool(re.search(r"^\s*autoinclude\s*:\s*(?:false|no|0)\s*$", text, re.IGNORECASE | re.MULTILINE))


def yaml_order(path: Path, fallback: int = 0) -> tuple[bool, Decimal | int]:
    match = re.search(r"^\s*yamlorder\s*:\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$",
                      path.read_text(encoding="utf-8-sig"), re.IGNORECASE | re.MULTILINE)
    if not match:
        return (False, fallback)
    return (True, Decimal(match.group(1)))


def order_metadata(paths: list[Path]) -> list[Path]:
    """Apply yamlorder where present while preserving explicit order otherwise."""
    if any(yaml_order(path)[0] for path in paths):
        return [path for _, path in sorted(
            enumerate(paths), key=lambda item: (
                yaml_order(item[1], item[0])[1], item[0]))]
    return paths


def resolve_yaml(directory: Path, value: str) -> Path:
    path = Path(value)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(Path.cwd() / path)
        candidates.append(directory / path)
        if not path.suffix:
            candidates.extend((Path.cwd() / path.with_suffix(".yaml"),
                               directory / path.with_suffix(".yaml")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Metadata file not found: {value}")


def find_metadata(directory: Path, requested: list[str] | None, report: bool = False,
                  document_class: str | None = None,
                  document_stem: str | None = None) -> Path | list[Path] | object | None:
    """Choose metadata files, supporting explicit stacks and automatic discovery."""
    if requested == []:
        return AUTO_METADATA_DISABLED
    if requested is not None:
        if requested == ["all"]:
            candidates = [item for item in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
                          if item.name.lower() != "defaults.yaml" and yaml_autoinclude(item)]
            return order_metadata(candidates)
        return order_metadata([resolve_yaml(directory, value) for value in requested])
    candidates = [item for item in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
                  if item.name.lower() != "defaults.yaml" and yaml_autoinclude(item)]
    metadata = next((item for item in candidates if item.name.lower() == "metadata.yaml"), None)
    document_metadata = ([item for item in candidates
                          if document_stem and item.stem.casefold() == document_stem.casefold()]
                         if document_stem else [])
    if document_metadata:
        # metadata.yaml is the shared base; document-named YAML overrides it.
        selected = ([metadata] if metadata and metadata not in document_metadata else []) + document_metadata
        return order_metadata(selected)
    if report:
        preferred = next((item for item in candidates if item.name.lower() == "report.yaml"), None)
        preferred = preferred or next((item for item in candidates if item.name.lower() == "book.yaml"), None)
        if preferred:
            return order_metadata(([metadata] if metadata else []) + [preferred])
    if metadata:
        return metadata
    if document_class:
        matching = [item for item in candidates if item.stem.casefold() == document_class.casefold()]
        if len(matching) == 1:
            return matching[0]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(item.name for item in candidates)
        raise ValueError(f"Multiple YAML files found in {directory}: {names}; use -y FILE or bare -y")
    return None


def chapter_value(md_path: Path):
    """Read the scalar chapter value from a Markdown YAML header."""
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    match = re.search(r"^chapter\s*:\s*(.*?)\s*$", front_matter.group(1), re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip("'\"")
    return None if value.casefold() in {"", "null", "none", "exclude", "excluded"} else value


def has_chapter_field(md_path: Path) -> bool:
    return bool(re.search(r"^chapter\s*:", md_path.read_text(encoding="utf-8-sig"), re.MULTILINE))


def chapter_order(md_path: Path):
    """Sort chapters by explicit front-matter precedence.

    The order is: always-first, first, numeric values, letter-prefixed values,
    unnumbered files, last, always-last. Numeric values may be negative or
    decimal; letter-prefixed values sort by their letter prefix and number.
    """
    value = chapter_value(md_path)
    name = md_path.name.casefold()
    if value is None:
        return (4, "", Decimal(0), Decimal(0), name)
    normalized = value.casefold()
    if normalized == "always-first":
        return (0, "", Decimal(0), Decimal(0), name)
    if normalized == "first":
        return (1, "", Decimal(0), Decimal(0), name)
    if normalized == "last":
        return (5, "", Decimal(0), Decimal(0), name)
    if normalized == "always-last":
        return (6, "", Decimal(0), Decimal(0), name)
    relative = re.fullmatch(r"(before|after)\s+(-?(?:\d+(?:\.\d*)?|\.\d+))", normalized)
    if relative:
        offset = Decimal(0) if relative.group(1) == "before" else Decimal(2)
        return (2, "", Decimal(relative.group(2)), offset, name)
    try:
        return (2, "", Decimal(value), Decimal(1), name)
    except InvalidOperation:
        lettered = re.fullmatch(r"([a-z]+)\s*(-?(?:\d+(?:\.\d*)?|\.\d+))", normalized)
        if lettered:
            return (3, lettered.group(1), Decimal(lettered.group(2)), Decimal(1), name)
        return (3, normalized, Decimal(0), Decimal(1), name)


def excluded_by_cli(md_path: Path, exclusions: list[str]) -> bool:
    candidates = {md_path.name.casefold(), md_path.stem.casefold(), str(md_path).casefold()}
    for exclusion in exclusions:
        value = Path(exclusion)
        names = {value.name.casefold(), value.stem.casefold(), str(value).casefold()}
        if candidates & names:
            return True
    return False


def report_sources(paths: list[Path], exclusions: list[str], exclude_unnumbered: bool = False,
                   recursive: bool = False) -> tuple[list[Path], list[Path]]:
    # .resolve() for the same reason as find_markdown(): a relative directory
    # plus a file in a subdirectory would otherwise make Pandoc's cwd and its
    # source-file arguments both relative, and doubling up into a bad path.
    files = []
    for path in paths:
        if path.is_dir():
            files.extend((file.resolve() for file in
                         (path.rglob("*.md") if recursive else path.glob("*.md"))))
        elif path.is_file() and path.suffix.lower() == ".md":
            files.append(path.resolve())
    all_files = sorted(set(files))
    excluded = [file for file in all_files if chapter_value(file) is None and has_chapter_field(file)]
    excluded += [file for file in all_files if excluded_by_cli(file, exclusions) and file not in excluded]
    if exclude_unnumbered:
        excluded += [file for file in all_files
                     if file not in excluded and not has_chapter_field(file)]
    included = [file for file in all_files if file not in excluded]
    return sorted(included, key=chapter_order), excluded


# Conventional file extension for a Pandoc writer/target format, used to name
# an output file when the caller didn't give one an explicit suffix. Formats
# missing here fall back to ".<format>" -- a reasonable guess, since Pandoc's
# own format names are usually also their file extension.
FORMAT_EXTENSION = {
    "pdf": ".pdf",
    "html": ".html", "html4": ".html", "html5": ".html", "chunkedhtml": ".html",
    "latex": ".tex", "beamer": ".tex", "context": ".tex",
    "typst": ".typ",
    "plain": ".txt",
    "markdown": ".md", "gfm": ".md", "commonmark": ".md", "commonmark_x": ".md",
    "docx": ".docx", "odt": ".odt", "pptx": ".pptx",
    "epub": ".epub", "epub2": ".epub", "epub3": ".epub",
    "rst": ".rst", "org": ".org", "rtf": ".rtf",
    "docbook": ".xml", "docbook4": ".xml", "docbook5": ".xml",
    "json": ".json", "man": ".man", "ipynb": ".ipynb",
    "asciidoc": ".adoc", "asciidoctor": ".adoc",
    "textile": ".textile", "mediawiki": ".wiki", "opml": ".opml",
}

# The reverse mapping, used to recognize that an explicit -o/--out filename
# (single-file and report/book modes only -- batch mode's -o is a directory)
# already states the target format on its own, e.g. "-o notes.html" needs no
# separate --to. Batch mode has no per-file filename to read, so it only
# responds to an explicit --to. Deliberately only the unambiguous, commonly
# typed extensions -- anything else should be requested with --to instead.
EXTENSION_FORMAT = {
    ".html": "html", ".htm": "html",
    ".tex": "latex",
    ".typ": "typst",
    ".txt": "plain",
    ".md": "markdown", ".markdown": "markdown",
    ".docx": "docx", ".odt": "odt", ".pptx": "pptx",
    ".epub": "epub", ".rst": "rst", ".org": "org", ".rtf": "rtf",
    ".json": "json", ".pdf": "pdf",
}


def format_from_output(path: Path | None) -> str | None:
    """Recognize a target format from an explicit output filename's suffix."""
    if path is None or not path.suffix:
        return None
    return EXTENSION_FORMAT.get(path.suffix.lower())


def default_output_path(path: Path, target_format: str) -> Path:
    """Add the extension implied by target_format when the caller omitted one."""
    if path.suffix:
        return path
    return path.with_suffix(FORMAT_EXTENSION.get(target_format, f".{target_format}"))


def open_file(path: Path) -> None:
    """Open a finished file with the platform's default viewer, for --open."""
    opener = "open" if sys.platform == "darwin" else "xdg-open" if sys.platform.startswith("linux") else None
    if opener is None or not which(opener):
        print(f"WARN  --open: no '{opener or 'file opener'}' found for this platform; "
              f"open {path} yourself", file=sys.stderr)
        return
    try:
        subprocess.run([opener, str(path)])
    except OSError as error:
        print(f"WARN  --open: could not open {path}: {error}", file=sys.stderr)


def log_cmd(cmd: list, cwd: Path, verbose: bool) -> None:
    """Print the exact subprocess command about to run, under --verbose.

    Added 2026-09-16 after a real debugging session (the pdfmd.py table-
    width/nulabreport.lua interaction, see TABLE_WIDTH_LUA_FILTER's own
    comment) that would have taken a fraction of the time if --verbose had
    shown this from the start -- it previously only ever printed pdfmd's
    OWN "AUTO ..." decisions (which metadata/preamble/font it picked), never
    the actual command line those decisions built, so which lua-filters
    were passed and in what order was invisible without editing this file
    to find out by hand. shlex.quote so a copy-pasted line is directly
    re-runnable even when an argument has spaces (a metadata file path
    under a directory with one, for instance).
    """
    if not verbose:
        return
    print("CMD  " + " ".join(shlex.quote(str(part)) for part in cmd) + f"  (cwd={cwd})",
          file=sys.stderr)


def convert_one(md_path: Path, out_dir: Path | None, presentation: bool, font: str,
                engines: list[str], variables: list[str], slide_level: int | None,
                pandoc_options: list[str],
                metadata_file: Path | list[Path] | None = None,
                output_file: Path | None = None,
                preamble_files: list[Path] | None = None,
                target_format: str = "pdf",
                from_format: str | None = None,
                no_auto: list[str] | None = None,
                verbose: bool = False) -> tuple[Path, bool, str]:
    auto_summary: list[str] = []

    def note(kind: str, detail: str) -> None:
        if verbose:
            print(f"AUTO {kind}  {detail}")
        else:
            auto_summary.append(kind)

    def flush_summary() -> None:
        if not verbose and auto_summary:
            kinds = " ".join(dict.fromkeys(auto_summary))
            print(f"AUTO: {kinds}. Use --verbose to see in full")

    metadata_files = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
    no_auto = effective_no_auto(md_path, no_auto)
    effective_from, reader_reason = (
        (from_format, None) if auto_disabled(no_auto, "reader")
        else resolve_from_format(md_path, from_format, metadata_files)
    )
    if reader_reason:
        note("READER", reader_reason)
    output_extension = FORMAT_EXTENSION.get(target_format, f".{target_format}")
    output = output_file or (
        (out_dir / f"{md_path.stem}{output_extension}") if out_dir else md_path.with_suffix(output_extension)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    lua_filters = [] if auto_disabled(no_auto, "lua") else find_lua_filters(md_path, metadata_files)
    for lua_filter in lua_filters:
        note("LUA", str(lua_filter))

    with prepared_title_source(md_path, metadata_files, disabled=auto_disabled(no_auto, "title")) \
            as (title_source, title_shifted), \
            table_width_filter() as width_filter:
        if title_shifted:
            note("TITLE", f"{md_path}: promoted leading '# ' heading to Pandoc title metadata")
        shift_heading = title_shifted and not has_shift_heading_option(pandoc_options)

        if target_format != "pdf":
            # No PDF engine and no font-fallback machinery here: those are
            # LaTeX/PDF-only concerns. This is a single, direct Pandoc conversion.
            with prepared_latex_inputs([title_source, *metadata_files], False) as prepared:
                source, *prepared_metadata = prepared
                cmd = ["pandoc", str(source), "-o", str(output), "-t", target_format]
                if effective_from:
                    cmd += ["-f", effective_from]
                for metadata in prepared_metadata:
                    cmd += ["--metadata-file", str(metadata)]
                pandoc_cwd = metadata_files[0].parent if metadata_files else md_path.parent
                for variable in variables:
                    cmd += ["-V", variable]
                if shift_heading:
                    cmd += ["--shift-heading-level-by=-1"]
                cmd += pandoc_options
                if contains_citations(md_path) and "--citeproc" not in pandoc_options and "--no-citeproc" not in pandoc_options:
                    cmd.append("--citeproc")
                if target_format == "latex" and not auto_disabled(no_auto, "tablewidth"):
                    cmd += ["--lua-filter", str(width_filter)]
                for lua_filter in lua_filters:
                    cmd += ["--lua-filter", str(lua_filter)]
                log_cmd(cmd, pandoc_cwd, verbose)
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)
            flush_summary()
            return md_path, result.returncode == 0, result.stderr[-3000:]

        document_font = has_mainfont(md_path, variables)
        explicit_font = document_font or bool(font)
        mainfont_auto = not auto_disabled(no_auto, "mainfont")
        tablewidth_auto = not auto_disabled(no_auto, "tablewidth")
        geometry_needed = (not auto_disabled(no_auto, "margin")
                          and not has_geometry(md_path, variables, metadata_files, preamble_files or []))
        if geometry_needed:
            note("MARGIN", f"{md_path}: no geometry/margin set; "
                          f"using geometry:margin={DEFAULT_MARGIN} on LaTeX-family engines")
        monofont_needed = (not auto_disabled(no_auto, "monofont")
                          and has_code_spans(md_path.read_text(encoding="utf-8-sig"))
                          and not has_monofont(md_path, variables))
        if monofont_needed:
            note("MONOFONT", f"{md_path}: has code but no monofont set; "
                            f"using {DEFAULT_MONOFONT} on LaTeX-family engines")
        result = None
        failed_families: set[str] = set()
        for engine_index, engine in enumerate(engines):
            family = ENGINE_FAMILY.get(engine, engine)
            if family in failed_families:
                print(f"SKIP  {md_path}: {engine} shares the {family} engine with an earlier "
                      f"failure; skipping", file=sys.stderr)
                continue
            with prepared_latex_inputs([title_source, *metadata_files], engine in LATEX_ENGINES) as prepared, \
                    document_header_file(md_path, bool(preamble_files) and engine in LATEX_ENGINES) as header_file:
                source, *prepared_metadata = prepared

                def run(selected_font: str | None, fallback: bool = False):
                    cmd = ["pandoc", str(source), "-o", str(output), "--pdf-engine=" + engine]
                    if effective_from:
                        cmd += ["-f", effective_from]
                    for metadata in prepared_metadata:
                        cmd += ["--metadata-file", str(metadata)]
                    pandoc_cwd = metadata_files[0].parent if metadata_files else md_path.parent
                    if presentation:
                        cmd += ["-t", "beamer"]
                        if slide_level is not None:
                            cmd += ["--slide-level=" + str(slide_level)]
                    if selected_font:
                        cmd += ["-V", f"mainfont={selected_font}"]
                    if fallback and not any(variable.startswith("mainfontfallback=") for variable in variables):
                        cmd += ["-V", f"mainfontfallback={DEFAULT_FONT}"]
                    if geometry_needed and engine in LATEX_ENGINES:
                        cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                    if monofont_needed and engine in LATEX_ENGINES:
                        cmd += ["-V", f"monofont={DEFAULT_MONOFONT}"]
                    for variable in variables:
                        cmd += ["-V", variable]
                    if shift_heading:
                        cmd += ["--shift-heading-level-by=-1"]
                    cmd += pandoc_options
                    if preamble_files and engine in LATEX_ENGINES:
                        for preamble_file in preamble_files:
                            cmd += ["--include-in-header", str(preamble_file)]
                        # Last, so a document's own header-includes can override
                        # anything the shared preamble defined (pandoc would
                        # otherwise drop it entirely; see document_header_file).
                        if header_file is not None:
                            cmd += ["--include-in-header", str(header_file)]
                    if contains_citations(md_path) and "--citeproc" not in pandoc_options and "--no-citeproc" not in pandoc_options:
                        cmd.append("--citeproc")
                    # Lua filters go last: pandoc applies --citeproc and filters in
                    # command-line order, and a filter that renders cell contents to
                    # LaTeX needs the citations already resolved.
                    if tablewidth_auto and engine in LATEX_ENGINES:
                        cmd += ["--lua-filter", str(width_filter)]
                    for lua_filter in lua_filters:
                        cmd += ["--lua-filter", str(lua_filter)]
                    log_cmd(cmd, pandoc_cwd, verbose)
                    return subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)

                first_font = None if document_font else (font or (PREFERRED_FONT if mainfont_auto else None))
                result = run(first_font, fallback=document_font)
                combined_output = result.stdout + result.stderr
                if (mainfont_auto and not explicit_font and result.returncode == 0
                        and missing_glyph_warning(combined_output)):
                    result = run(font or DEFAULT_FONT)
            if result.returncode == 0:
                break
            failed_families.add(family)
            remaining = [e for e in engines[engine_index + 1:] if ENGINE_FAMILY.get(e, e) not in failed_families]
            if remaining:
                print(f"WARN  {md_path}: {engine} failed; trying {remaining[0]}...", file=sys.stderr)
        assert result is not None
        flush_summary()
        return md_path, result.returncode == 0, result.stderr[-3000:]


def convert_qmd(source: Path, output: Path, target_format: str,
                variables: list[str], pandoc_options: list[str]) -> tuple[Path, bool, str]:
    """Render a Quarto document (.qmd) via the Quarto CLI, not Pandoc directly.

    Pandoc has no idea what a .qmd file is -- it silently falls back to
    treating it as plain Markdown, so executable code chunks (R/Python/Julia,
    run through knitr or Jupyter) never get executed: figures don't render
    and the chunk syntax leaks into the output as literal text. Quarto's own
    CLI is what actually knows how to run those chunks, so .qmd is handed off
    to it entirely; none of Pandoc's metadata-file/preamble/Lua-filter
    machinery in this script applies here -- Quarto has its own, separate
    project and metadata system.

    NOTE: this path could not be exercised where this script was written (no
    Quarto install available there) -- it follows Quarto's documented CLI,
    but please flag anything that doesn't match your installed version.
    """
    quarto = which("quarto")
    if not quarto:
        return source, False, (
            "Quarto was not found on PATH. Install it from https://quarto.org to render "
            ".qmd files -- Pandoc alone cannot execute their R/Python/Julia code chunks, "
            "which is why a plain Pandoc conversion silently drops figures and computed output."
        )
    if variables or pandoc_options:
        print(f"WARN  {source}: -V and passthrough Pandoc options don't apply to Quarto "
              "rendering and were ignored; use Quarto's own -P/-M flags instead", file=sys.stderr)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Quarto's own -o has historically wanted a bare filename in the source's
    # directory, so render there and move the result to the real destination
    # afterward (covers -o/--out pointing elsewhere, or --destination-cwd).
    cmd = [quarto, "render", source.name, "--to", target_format, "-o", output.name]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=source.parent)
    rendered = source.parent / output.name
    if result.returncode == 0 and rendered.exists() and rendered.resolve() != output.resolve():
        rendered.replace(output)
    return source, result.returncode == 0, (result.stdout + result.stderr)[-3000:]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert Markdown (and other Pandoc-readable) files to PDF or another format with Pandoc.")
    parser.add_argument("--version", action="version", version=f"pdfmd {PDFMD_VERSION}")
    parser.add_argument("path", type=Path, nargs="*", help="Markdown name, files, or directory (default: current directory)")
    parser.add_argument("-p", "--presentation", action="store_true", help="create Beamer slides")
    parser.add_argument("--slide-level", type=int, help="Beamer heading level used for slide breaks")
    parser.add_argument("-b", "--batch", action="store_true", help="convert all Markdown files")
    parser.add_argument("-r", "--report", "--book", action="store_true",
                        help="combine all Markdown files in PATH into one PDF")
    parser.add_argument("--recursive", action="store_true",
                        help="include Markdown files in subdirectories (batch and report/book modes; "
                             "off by default, both search the given directory only)")
    parser.add_argument("-o", "--out", type=Path,
                        help="output directory (batch) or filename (single-file/report/book); "
                             "a recognized extension (e.g. .html, .tex, .typ) also selects the "
                             "target format, same as --to")
    parser.add_argument("-d", "-cwd", "--cwd", "--destination-cwd", action="store_true",
                        dest="destination_cwd",
                        help="save PDFs in the current working directory")
    parser.add_argument("-f", "--font", default=None, help="font to use if glyph fallback is needed")
    parser.add_argument("-e", "--engine", nargs="?", const="", default=None,
                        help="PDF engine, family (tex/html/typst), numeric shortcut, or alias; run "
                             "--check-dependencies to see engine choices. Meaningless (and ignored) when "
                             "--to targets a non-PDF format. Always wins over a document's own "
                             "pdf-engine/engine front-matter key (see below). A bare -e (no value) "
                             "explicitly requests the full, unrestricted fallback chain across every "
                             "installed engine, overriding even a family restriction in front matter -- "
                             "use it to force output out of a document that would otherwise refuse to "
                             "leave its family. With neither a value nor front matter, the same full "
                             "fallback chain applies by default")
    parser.add_argument("-t", "--to", dest="to", default=None, metavar="FORMAT",
                        help="Pandoc target format, e.g. html, latex (tex), typst, plain (txt), docx. "
                             "Default is pdf. An -o/--out filename with a recognized extension "
                             "(single-file/report modes only, e.g. -o notes.html) implies this too; "
                             "an explicit --to always wins. No PDF engine is involved, or required "
                             "to be installed, for a non-pdf target -- Pandoc writes that format directly")
    parser.add_argument("--from", dest="from_format", default=None, metavar="FORMAT",
                        help="Pandoc source format override (no short flag: -f is --font). Only needed "
                             "when Pandoc's own extension-based guess is wrong, e.g. a .txt file that "
                             "is actually reStructuredText: --from rst")
    parser.add_argument("--check-dependencies", action="store_true",
                        help="show Pandoc and supported PDF-engine availability, then exit")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="parallel workers in batch mode")
    parser.add_argument("-V", "--var", action="append", default=[], dest="variable", metavar="KEY=VALUE")
    parser.add_argument("-y", "--metadata-file", nargs="*", default=None, metavar="FILE",
                        help="metadata YAML file(s), 'all', or bare -y to disable discovery")
    parser.add_argument("-i", "--ignore", "--exclude", action="append", default=[], metavar="FILE",
                        help="exclude a Markdown file from report/book input (extension optional)")
    parser.add_argument("--exclude-unnumbered", action="store_true",
                        help="exclude Markdown files without a chapter field in report/book mode")
    parser.add_argument("--no-auto", nargs="*", default=None, metavar="KIND",
                        help="disable pdfmd's own automatic per-document behavior. Bare --no-auto "
                             "disables all of it; or name one or more of: reader (the gfm switch "
                             "for front-matter-less documents), title (bare '# Title' promotion), "
                             "margin (geometry:margin=1in), mainfont (the STIX Two Text/DejaVu Serif "
                             "fallback), monofont (JetBrains Mono for code), font (mainfont and "
                             "monofont together), tablewidth (proportional pipe-table column widths), "
                             "metadata/yaml (auto-discovered --metadata-file), preamble/tex "
                             "(auto-included LaTeX preambles), lua (auto-included Lua filters), "
                             "files (metadata+preamble+lua together). An explicit -y/-H/-f/-V/--from "
                             "always wins over --no-auto metadata/preamble regardless of this flag -- "
                             "--no-auto only stops pdfmd from filling in or discovering what's "
                             "otherwise unset. Same KIND names work in a document's own "
                             "pdfmd-options.no-auto front matter (see the module docstring)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show each AUTO decision's full explanation as it happens. Default is "
                             "a single condensed 'AUTO: KIND KIND ...' line per document (naming "
                             "only the reader/title/margin/mainfont/monofont/lua kinds that actually "
                             "fired) so a normal run stays quiet; AUTO YAML/TEX/ENGINE/MD are "
                             "unaffected by this flag and always print in full, since they're rarer "
                             "and already name a specific file/engine rather than a generic default")
    parser.add_argument("--open", action="store_true",
                        help="open the finished file (via macOS 'open'/Linux 'xdg-open') once "
                             "conversion succeeds. Applies to single-file and report/book mode, "
                             "each of which produce exactly one output; ignored in batch mode "
                             "(-b), which would otherwise pop open every file in the directory")
    return parser


def main() -> None:
    args, pandoc_options = build_parser().parse_known_args()
    if args.check_dependencies:
        raise SystemExit(0 if dependency_report() else 1)
    if not which("pandoc"):
        raise SystemExit("Pandoc was not found on PATH. Install Pandoc, then run --check-dependencies.")
    paths = args.path or [Path.cwd()]
    variables = DEFAULT_VARS + args.variable
    if args.no_auto:
        unknown = sorted(set(args.no_auto) - NO_AUTO_KINDS)
        if unknown:
            raise SystemExit(f"Unknown --no-auto kind(s): {', '.join(unknown)}. "
                             f"Valid: {', '.join(sorted(NO_AUTO_KINDS))}")
    if args.batch and args.report:
        raise SystemExit("Choose either --batch or --report/--book, not both")
    if args.presentation and args.report:
        raise SystemExit("--presentation cannot be combined with --report/--book")

    # Target format: explicit --to wins; otherwise a recognized -o/--out
    # extension implies it (single-file/report only -- batch's -o is a
    # directory, so it only responds to --to); default is pdf.
    target_format = (
        (args.to.casefold() if args.to else None)
        or (format_from_output(args.out) if args.out and not args.batch else None)
        or "pdf"
    )
    if args.presentation and target_format != "pdf":
        raise SystemExit("-p/--presentation always produces a PDF (via Beamer); "
                         "it can't be combined with --to/-o for another format")
    if args.engine is not None and target_format != "pdf":
        print(f"WARN  --engine is ignored for --to {target_format}: no PDF engine is involved",
              file=sys.stderr)
    engines = select_engines(args.engine, args.presentation) if target_format == "pdf" else []
    if not args.path and not args.batch and not args.report:
        markdown_files = sorted(Path.cwd().glob("*.md"), key=lambda path: path.name.casefold())
        if not markdown_files:
            raise SystemExit("No Markdown files found in the current directory.")
        if len(markdown_files) > 1:
            names = ", ".join(path.name for path in markdown_files)
            raise SystemExit(
                f"Multiple Markdown files found: {names}\n"
                "Specify one file, use -b to convert all separately, or use -r to combine them."
            )
        paths = [markdown_files[0]]
        print(f"AUTO MD    {paths[0]}")
    if args.report:
        files, excluded = report_sources(paths, args.ignore, args.exclude_unnumbered, args.recursive)
        if not files:
            raise SystemExit("No Markdown files found for the report")
        # --no-auto and its pdfmd-options counterpart are decided from
        # files[0] only, same as the reader/documentclass/pdf-engine
        # front matter below -- a report can't mix per-chapter overrides
        # in one Pandoc invocation.
        report_no_auto = effective_no_auto(files[0], args.no_auto)
        report_auto_summary: list[str] = []

        def report_note(kind: str, detail: str) -> None:
            if args.verbose:
                print(f"AUTO {kind}  {detail}")
            else:
                report_auto_summary.append(kind)

        try:
            document_class = (frontmatter_value(files[0], "documentclass")
                              or frontmatter_value(files[0], "class"))
            metadata_directory = paths[0] if len(paths) == 1 and paths[0].is_dir() else files[0].parent
            # An explicit -y/--metadata-file always wins over --no-auto
            # metadata; only auto-discovery (args.metadata_file is None) is
            # what --no-auto metadata/yaml suppresses.
            metadata_request = ([] if args.metadata_file is None and auto_disabled(report_no_auto, "metadata")
                                else args.metadata_file)
            metadata = find_metadata(metadata_directory.resolve(), metadata_request, report=True,
                                     document_class=document_class, document_stem=files[0].stem)
        except (FileNotFoundError, ValueError) as error:
            raise SystemExit(str(error))
        metadata_files = ([] if metadata is AUTO_METADATA_DISABLED else
                          (metadata if isinstance(metadata, list) else ([metadata] if metadata else [])))
        engines = resolve_engines(files[0], args.engine, engines, args.presentation, target_format, metadata_files)
        report_from, report_reader_reason = (
            (args.from_format, None) if auto_disabled(report_no_auto, "reader")
            else resolve_from_format(files[0], args.from_format, metadata_files)
        )
        if report_reader_reason:
            report_note("READER", report_reader_reason)
        output_extension = FORMAT_EXTENSION.get(target_format, f".{target_format}")
        if args.out:
            # Check is-a-directory BEFORE adding a default suffix -- a dot-less
            # directory name (e.g. "out/") would otherwise get ".pdf" appended
            # to the directory's own name instead of being used as a directory.
            output = args.out / f"book{output_extension}" if args.out.is_dir() else default_output_path(args.out, target_format)
        else:
            output = Path.cwd() / f"book{output_extension}"
        output = output.resolve()
        pandoc_cwd = metadata_files[0].parent if metadata_files else files[0].parent

        with table_width_filter() as width_filter:
            if target_format != "pdf":
                with prepared_latex_inputs([*files, *metadata_files], False) as prepared:
                    prepared_files = prepared[:len(files)]
                    prepared_metadata = prepared[len(files):]
                    cmd = ["pandoc", *map(str, prepared_files), "-o", str(output), "-t", target_format]
                    if report_from:
                        cmd += ["-f", report_from]
                    if metadata is not AUTO_METADATA_DISABLED:
                        for metadata_file in prepared_metadata:
                            cmd += ["--metadata-file", str(metadata_file)]
                    for variable in variables:
                        cmd += ["-V", variable]
                    cmd += pandoc_options
                    if (any(contains_citations(file) for file in files)
                            and "--citeproc" not in pandoc_options
                            and "--no-citeproc" not in pandoc_options):
                        cmd.append("--citeproc")
                    if target_format == "latex" and not auto_disabled(report_no_auto, "tablewidth"):
                        cmd += ["--lua-filter", str(width_filter)]
                    log_cmd(cmd, pandoc_cwd, args.verbose)
                    result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)
            else:
                preambles = ([] if auto_disabled(report_no_auto, "preamble")
                            else find_preambles(files[0].parent, files[0].stem, pandoc_options))
                announce_preambles(preambles)
                report_tablewidth_auto = not auto_disabled(report_no_auto, "tablewidth")
                geometry_needed = (not auto_disabled(report_no_auto, "margin")
                                  and not has_geometry(files[0], variables, metadata_files, preambles))
                if geometry_needed:
                    report_note("MARGIN", "REPORT: no geometry/margin set; "
                                         f"using geometry:margin={DEFAULT_MARGIN} on LaTeX-family engines")
                monofont_needed = (not auto_disabled(report_no_auto, "monofont")
                                  and any(has_code_spans(file.read_text(encoding="utf-8-sig")) for file in files)
                                  and not has_monofont(files[0], variables))
                if monofont_needed:
                    report_note("MONOFONT", "REPORT: has code but no monofont set; "
                                           f"using {DEFAULT_MONOFONT} on LaTeX-family engines")
                # Reports need one Pandoc invocation, so retry each usable engine here.
                result = None
                failed_families: set[str] = set()
                for engine_index, engine in enumerate(engines):
                    family = ENGINE_FAMILY.get(engine, engine)
                    if family in failed_families:
                        print(f"SKIP  REPORT: {engine} shares the {family} engine with an earlier "
                              f"failure; skipping", file=sys.stderr)
                        continue
                    with prepared_latex_inputs([*files, *metadata_files], engine in LATEX_ENGINES) as prepared:
                        prepared_files = prepared[:len(files)]
                        prepared_metadata = prepared[len(files):]
                        cmd = ["pandoc", *map(str, prepared_files), "-o", str(output), "--pdf-engine=" + engine]
                        if report_from:
                            cmd += ["-f", report_from]
                        if metadata is not AUTO_METADATA_DISABLED:
                            for metadata_file in prepared_metadata:
                                cmd += ["--metadata-file", str(metadata_file)]
                        if geometry_needed and engine in LATEX_ENGINES:
                            cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                        if monofont_needed and engine in LATEX_ENGINES:
                            cmd += ["-V", f"monofont={DEFAULT_MONOFONT}"]
                        for variable in variables:
                            cmd += ["-V", variable]
                        cmd += pandoc_options
                        if preambles and engine in LATEX_ENGINES:
                            for preamble in preambles:
                                cmd += ["--include-in-header", str(preamble)]
                        if (any(contains_citations(file) for file in files)
                                and "--citeproc" not in pandoc_options
                                and "--no-citeproc" not in pandoc_options):
                            cmd.append("--citeproc")
                        if report_tablewidth_auto and engine in LATEX_ENGINES:
                            cmd += ["--lua-filter", str(width_filter)]
                        log_cmd(cmd, pandoc_cwd, args.verbose)
                        result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)
                    if result.returncode == 0:
                        break
                    failed_families.add(family)
                    remaining = [e for e in engines[engine_index + 1:] if ENGINE_FAMILY.get(e, e) not in failed_families]
                    if remaining:
                        print(f"WARN  REPORT: {engine} failed; trying {remaining[0]}...", file=sys.stderr)
        assert result is not None
        for file in files:
            if not has_chapter_field(file):
                print(f"[WARNING] unnumbered Markdown included: {file}")
            print(f"OK    {file}")
        for file in excluded:
            print(f"SKIP  {file}")
        if metadata is not AUTO_METADATA_DISABLED:
            for metadata_file in metadata_files:
                label = "AUTO YAML" if args.metadata_file is None else "YAML"
                print(f"{label}  {metadata_file}")
        if not args.verbose and report_auto_summary:
            kinds = " ".join(dict.fromkeys(report_auto_summary))
            print(f"AUTO: {kinds}. Use --verbose to see in full")
        print(f"{'OK  ' if result.returncode == 0 else 'FAIL'}  REPORT  {output}")
        if result.stderr:
            print(result.stderr[-3000:])
        if result.returncode:
            raise SystemExit(1)
        if args.open:
            open_file(output)
        return
    metadata_by_dir = {}
    def metadata_for(file, document_class=None):
        directory = file.parent.resolve()
        cache_key = (directory, file.stem.casefold())
        if cache_key not in metadata_by_dir:
            # An explicit -y/--metadata-file always wins over --no-auto
            # metadata; only auto-discovery (args.metadata_file is None) is
            # what --no-auto metadata/yaml suppresses -- per file, since
            # each file's own pdfmd-options can differ even in one batch.
            requested = ([] if args.metadata_file is None
                        and auto_disabled(effective_no_auto(file, args.no_auto), "metadata")
                        else args.metadata_file)
            metadata_by_dir[cache_key] = find_metadata(directory, requested,
                                                        document_class=document_class,
                                                        document_stem=file.stem)
            discovered = metadata_by_dir[cache_key]
            if args.metadata_file is None and discovered is not None and discovered is not AUTO_METADATA_DISABLED:
                paths = discovered if isinstance(discovered, list) else [discovered]
                for path in paths:
                    print(f"AUTO YAML  {path}")
        value = metadata_by_dir[cache_key]
        return None if value is AUTO_METADATA_DISABLED else value
    if args.batch:
        if len(paths) != 1 or not paths[0].is_dir():
            raise SystemExit("Batch mode requires one directory path")
        # .resolve() for the same reason as find_markdown(): a relative batch
        # directory plus a file in a subdirectory would otherwise make Pandoc's
        # cwd and its source-file argument both relative, and doubling up.
        files = sorted(
            file.resolve() for file in
            (paths[0].rglob("*.md") if args.recursive else paths[0].glob("*.md"))
        )
        output = Path.cwd() if args.destination_cwd else (args.out.resolve() if args.out else None)
        if output:
            output.mkdir(parents=True, exist_ok=True)
        jobs = max(1, args.jobs)
        def preamble_for(file):
            if target_format != "pdf" or auto_disabled(effective_no_auto(file, args.no_auto), "preamble"):
                return []
            preambles = find_preambles(file.parent, file.stem, pandoc_options)
            announce_preambles(preambles)
            return preambles
        if args.open:
            print("WARN  --open is ignored in batch mode (-b); it would open every converted file",
                 file=sys.stderr)
        def file_metadata_and_engines(file):
            # metadata_for(file) is looked up once and reused for both the
            # engine restriction (which may now fall through to this same
            # metadata file's own pdf-engine setting -- see resolve_engines)
            # and the actual conversion, rather than calling it twice.
            metadata = metadata_for(file)
            metadata_files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
            return metadata, resolve_engines(file, args.engine, engines, args.presentation, target_format, metadata_files)
        def work(file):
            metadata, file_engines = file_metadata_and_engines(file)
            return convert_one(file, output, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, preamble_files=preamble_for(file), target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose)
        results = []
        if jobs > 1:
            with ProcessPoolExecutor(max_workers=jobs) as executor:
                futures = []
                for file in files:
                    metadata, file_engines = file_metadata_and_engines(file)
                    futures.append(executor.submit(convert_one, file, output, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, None, preamble_for(file), target_format, args.from_format, args.no_auto, args.verbose))
                results = [future.result() for future in as_completed(futures)]
                results.sort(key=lambda result: result[0].name.casefold())
        else:
            results = [work(file) for file in files]
    else:
        try:
            if len(paths) != 1:
                raise FileNotFoundError("Single-file mode accepts one Markdown name or path")
            source = find_markdown(paths[0])
        except FileNotFoundError as error:
            raise SystemExit(str(error))
        output_extension = FORMAT_EXTENSION.get(target_format, f".{target_format}")
        out_dir = None
        output_file = None
        if args.out and not args.destination_cwd and args.out.is_dir():
            # Check is-a-directory BEFORE adding a default suffix -- a dot-less
            # directory name would otherwise get an extension appended to the
            # directory's own name instead of being used as a directory.
            out_dir = args.out.resolve()
        elif args.out:
            requested_output = Path.cwd() / args.out.name if args.destination_cwd else args.out.resolve()
            output_file = default_output_path(requested_output, target_format)
        elif args.destination_cwd:
            output_file = Path.cwd() / f"{source.stem}{output_extension}"
        output = output_file or ((out_dir / f"{source.stem}{output_extension}") if out_dir
                                 else source.with_suffix(output_extension))
        if source.suffix.lower() == ".qmd":
            if args.presentation:
                raise SystemExit("-p/--presentation isn't supported for .qmd -- set the "
                                 "format in the document's own Quarto front matter instead")
            results = [convert_qmd(source, output, target_format, variables, pandoc_options)]
        else:
            document_class = (frontmatter_value(source, "documentclass")
                              or frontmatter_value(source, "class"))
            try:
                metadata = metadata_for(source, document_class=document_class)
            except (FileNotFoundError, ValueError) as error:
                raise SystemExit(str(error))
            preambles = []
            if target_format == "pdf" and not auto_disabled(effective_no_auto(source, args.no_auto), "preamble"):
                preambles = find_preambles(source.parent, source.stem, pandoc_options)
                announce_preambles(preambles)
            engine_metadata_files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
            file_engines = resolve_engines(source, args.engine, engines, args.presentation, target_format, engine_metadata_files)
            results = [convert_one(source, out_dir, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, output_file, preambles, target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose)]
        if args.open and results[0][1]:
            open_file(output)
    failures = [result for result in results if not result[1]]
    for source, ok, error in results:
        print(f"{'OK  ' if ok else 'FAIL'}  {source}")
        if error:
            print(error)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
