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

    A real .tex file targeting PDF is another special case, as of v3.1.0:
    it is already a complete, independently compilable document (its own
    `\\documentclass`...`\\begin{document}`...`\\end{document}`), so instead
    of handing it to Pandoc -- which would read it with Pandoc's own LaTeX
    reader and regenerate it through Pandoc's LaTeX writer before an engine
    ever saw it, a lossy round-trip for hand-written LaTeX macros (chemfig,
    tikz, ...) that don't survive re-serialization -- pdfmd runs a LaTeX
    engine on it directly. The -e/--engine fallback chain (or a document's
    own `pdf-engine:`/`engine:` setting) still applies, restricted to its
    LaTeX-family members (lualatex, xelatex, pdflatex, latexmk, tectonic --
    not context, whose CLI and markup are unrelated to the other five).
    lualatex/xelatex/pdflatex are rerun automatically, up to
    MAX_TEX_DIRECT_PASSES times, whenever the engine's own .log asks for
    another pass (the same "Rerun to get..."/"Label(s) may have changed"
    signal latexmk itself watches for) -- covering both a bibliography
    (`\\bibliography{...}`/`\\addbibresource{...}` triggers a bibtex/biber
    pass between engine runs, chosen automatically) and any other multi-
    pass need, such as a chemfig diagram whose arrow angles depend on a
    label resolved in a previous pass. latexmk and tectonic already manage
    all of this internally and are each given a single wrapped call instead.
    Every engine writes into a scratch directory that is discarded once the
    final PDF is copied out, so -- like tectonic itself -- the source
    directory never ends up holding `.aux`/`.log`/`.out`/etc.; --keep-aux
    turns this off and compiles in place instead, for inspecting a failing
    or suspicious build's own .log by hand. None of pdfmd's own Pandoc-
    side auto-discovery (metadata YAML, preambles, Lua filters, font/
    margin defaults, PDF-metadata/BUILD-NOTES stamping) applies to this
    path, since none of it goes through Pandoc -- a document that actually
    needs pdfmd's own injection applied to raw LaTeX should keep going
    through Pandoc instead, via `--no-auto texdirect` or an explicit
    `--from` other than latex/tex.

    An office document (.docx, .doc, .odt, .ott, .rtf, .pptx, .ppt, .odp,
    .xlsx, .xls, .ods) targeting PDF is a third special case, as of
    v3.2.0: it converts straight to PDF via headless LibreOffice
    (`soffice --convert-to pdf`), no Pandoc involved at all -- a default
    change for .docx/.odt specifically, which Pandoc CAN also read as
    input (lossily -- through the same kind of AST round-trip the .tex
    case above exists to avoid, here losing the original document's own
    layout instead of raw macros); .pptx/.xlsx/.ppt/.xls/etc. have no
    Pandoc reader at all and could never reach a PDF through pdfmd before
    this. Unlike `.tex`, there is no working "opt back into Pandoc" route
    for any of these: --no-auto officedirect, an explicit --from, or a
    non-PDF --to target all raise a clear error instead of the crash they
    used to reach a few calls later, since Pandoc's own docx/odt reader
    is a strictly worse outcome here anyway (loses the original
    formatting soffice preserves) and every Pandoc-side auto-discovery
    helper (front matter, citations, Lua filters, font/margin defaults)
    assumes text input, which a binary office document never is.

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
    `html`, `typst`, `office`) to restrict automatic fallback to that
    paradigm instead of one specific engine, e.g. `pdf-engine: tex` for a chemfig-heavy
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

    Targeting `latex`, `beamer`, or `context` (--to, or an -o/--out file
    ending `.tex`) produces a complete, standalone document -- the same
    `\\documentclass`...`\\begin{document}`...`\\end{document}` a direct PDF
    render goes through, not a bare Pandoc-LaTeX fragment that only compiles
    once pasted into a preamble of its own -- so the same margin/mainfont/
    monofont defaults above apply, and a project's own discovered preamble
    (PREAMBLE_FILENAMES beside the document, e.g. `preamble.tex`) and
    `header-includes`/`pdfmd-options` front matter are included the same way
    they would be for a PDF made through that same writer, via
    `--include-in-header`. `--no-auto standalone` (or `pdfmd-options:
    no-auto: [standalone]`) turns off just the `--standalone` addition, for
    the fragment-only behavior other non-PDF targets still have by default
    -- e.g. a `.tex` meant to be `\\input`/`\\include`d into another
    document, not compiled on its own. One thing this can't reproduce: the
    PDF path's missing-glyph detect-and-retry between `mainfont: STIX Two
    Text` and `mainfont: DejaVu Serif` needs an actual compile to check
    against, which nothing here performs, so the emitted document keeps
    whichever of the two it tried first (PREFERRED_FONT, unless the document
    or -f/--font already names one) -- override it by hand with -f/--font or
    by editing the emitted `\\setmainfont` line if that turns out to be the
    wrong one for a particular document's glyphs.

Batch mode (-b) and report/book mode (-r) only look in the given directory
by default; add --recursive to also include subdirectories.

Auto-discovered metadata YAML, preambles, and Lua filters (see "Suppressing
pdfmd's own defaults" below for what each of these is) are looked for beside
the document itself -- the original convention -- and, if present, inside a
`metadata/` subdirectory beside it as well, so a report's own top-level
folder can hold nothing but its .md source and rendered output while
metadata.yaml, a shared .bib/.csl, preamble.tex, and Lua filters live out of
sight together in `metadata/`. Both locations are always searched; nothing
needs to opt in. Whichever directory a document's --metadata-file (explicit
or auto-discovered) ends up in also becomes the working directory Pandoc
itself runs in, so a preamble's own raw LaTeX `\\input{...}` and a
metadata.yaml's own relative `bibliography:`/`csl:` paths can live in that
same `metadata/` folder and still resolve -- pdfmd adds `--resource-path`
pointing back at the document's own directory in that case, so the
document's own relative image paths keep resolving too.

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

CSV/TSV table inclusion:
    A fenced Div with class `csv` --

        ::: {.csv file="data.csv"}
        :::

    -- is replaced with an actual table read from that file, instead of a
    hand-transcribed pipe table (`contains_csv_table()`,
    CSV_TABLE_LUA_FILTER). Delimiter is auto-detected from the extension
    (`.tsv` -> tab, otherwise comma), or set explicitly with a
    `delimiter="..."` attribute; the first row is treated as a header
    unless `header="false"`. Capped at 10 rows and 7 columns by default --
    `rows`/`cols` attributes override either (a number, or `all` for no
    cap) -- so an accidentally-huge CSV doesn't produce a many-page table
    nobody intended; a truncated table gets both a one-line `WARN` (naming
    how many of how many rows/columns were kept) and a note printed
    directly under the table itself, in the rendered output, not just on
    the compiling terminal. A `.csv` div with no `file=` attribute, or one
    naming a file that can't be opened, gets a `WARN` and is left empty
    rather than failing the whole compile. Works for any output format
    (not LaTeX-specific, unlike the table-width filter above) -- Markdown/
    Pandoc input, single-file/batch/report modes, and the soffice PDF-
    engine fallback all support it; a real .tex or office-document INPUT
    does not (there is no Pandoc AST -- and so no Div -- on either of
    those paths). `--no-auto csvtable` turns it off.

    A fenced Div, not a new raw-text sigil/key scanned over the Markdown
    source before Pandoc ever sees it, deliberately: Pandoc has already
    told code blocks/spans apart from real content by the time a Lua
    filter's own Div() callback fires, so `::: {.csv ...} :::` typed
    inside a fenced code block as a literal example is never mistaken for
    the real thing -- a raw-text approach keyed on some other character
    would not have that guarantee.

Suppressing pdfmd's own defaults, and the `pdfmd-options:` front-matter block:
    --no-auto turns off the reader/title/margin/mainfont/monofont/tablewidth/
    standalone defaults documented above, plus pdfmd's own file-discovery
    (auto-attached metadata YAML, LaTeX preambles, Lua filters) -- bare
    --no-auto disables all of it; --no-auto KIND [KIND ...] disables only
    those. KIND is one of: reader, title, margin, mainfont, monofont, font
    (mainfont+monofont), tablewidth, standalone (the --to latex/beamer/
    context --standalone default), metadata/yaml (the auto-discovered
    --metadata-file), preamble/tex (auto-included preamble.tex etc.), lua
    (auto-included <stem>.lua/nulabreport.lua), files (metadata+preamble+
    lua), texdirect (the v3.1.0 direct-.tex-compile path under "Input
    formats" above -- disabling it routes a .tex input back through Pandoc
    the old way), officedirect (the direct office-document-to-PDF path,
    also under "Input formats" -- disabling it on a .docx/.odt is an
    error in this version, not a route back through Pandoc; see that
    section for why), crossref (the auto-detected `--filter pandoc-
    crossref` for `@fig:`/`@eq:`/`@tbl:`/`@sec:`/`@lst:` syntax or a
    `{#fig:...}`-style attribute -- see crossref_filter_args()),
    citationengine (a document's own `pdfmd-options.citation-engine`
    setting -- see "Output formats" below; disabling this KIND always
    means plain `--citeproc`, regardless of what the document's own front
    matter or metadata file requests), csvtable (the `.csv`-div table
    inclusion under "CSV/TSV table inclusion" above). An explicit
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

    Four keys live there today: `no-auto` (same KIND names as --no-auto
    above, plus `true`/`all` for everything or a single bare name --
    additive with a CLI --no-auto, whichever source disables a given kind
    wins for that kind), `pdf-engine`/`engine` (same values as
    -e/--engine; see frontmatter_engine()'s docstring for why this one in
    particular moved here rather than staying a bare top-level key -- the
    older bare spelling still works for documents already using it),
    `preamble` (a bare string or a YAML list -- one or more LaTeX preamble
    files to `--include-in-header`, resolved relative to the document's own
    directory; merged with, not a replacement for, whatever
    PREAMBLE_FILENAMES auto-discovery already finds beside it, and subject
    to the same `--no-auto preamble` gate -- see
    frontmatter_extra_preambles()'s own docstring for why an explicit `-H`
    on the command line is the escape hatch when a preamble must survive
    even that), and `citation-engine`: `citeproc` (the default -- a document
    only needs this key at all to opt into something else), `natbib`, or
    `biblatex`.
    The last one routes a LaTeX-family PDF target's (or `--to latex`/
    `beamer`/`context`'s) bibliography through Pandoc's own `--natbib`/
    `--biblatex` flags -- native biber/bibtex processing via the engine's
    own tooling, using the document's existing `bibliography:` field --
    instead of `--citeproc` (which renders citations directly into the
    LaTeX Pandoc generates, via a CSL style, without touching biber/bibtex
    at all). For a PDF target specifically, this compiles by generating a
    complete standalone `.tex` via Pandoc first, then handing it to the
    same direct-compile engine+rerun+bibtex/biber loop `.tex` input uses
    above (`compile_tex_direct()`) -- necessary because confirmed
    empirically that Pandoc's own PDF-making pipeline never runs bibtex/
    biber itself when it calls a LaTeX engine directly (only `--pdf-
    engine=latexmk` manages that on its own); this way `natbib`/`biblatex`
    work with any LaTeX-family engine, not just latexmk. Meaningless (and
    silently ignored) for a non-LaTeX target -- HTML, typst, docx, an
    office document, or the soffice PDF-engine fallback -- same as e.g.
    LaTeX-only geometry/monofont defaults already are; a document that
    sets it but ends up on a fallback chain with no LaTeX-family engine
    available at all gets one clear WARN and `--citeproc` instead. All
    three keys require PyYAML and a document that already has a `---`
    block; silently ignored (not an error) if PyYAML isn't installed.

Build-provenance stamping (--stamp):
    Off by default. On a successful compile, appends or updates a
    `<!-- ===... BUILD NOTES ...=== -->` HTML comment near the end of the
    .md source recording what compiled it and when -- invisible in the
    rendered output (every writer pdfmd targets drops a raw HTML comment),
    visible to anyone reading the source later. This automates a convention
    already kept by hand in real reports; anything else already written
    inside that same BUILD NOTES comment (by hand, for unrelated notes) is
    never touched.

    --stamp-mode controls repeats: `replace` (default) overwrites the
    current stamp line in place. `history` keeps exactly one live stamp
    line at the top (right under BUILD NOTES, so the latest compile is
    always the first thing read) and demotes whatever was there before
    into a "Compile History:" list of bullets at the END of the comment,
    just before its closing `===...-->`, newest-demoted-first -- so hand-
    written notes in between never get pushed further down with each
    compile the way a plain top-of-block history would. Switching back to
    `replace` afterward freezes that history list rather than deleting it,
    which prints a WARN so it isn't silently forgotten about.

    --stamp-packages NAME [NAME ...] names LaTeX packages (e.g.
    `nulabreport`) whose version to include, found via `kpsewhich
    NAME.sty` and that file's own `\\ProvidesPackage` line -- a named
    package is silently left off the line if this document doesn't
    actually load it, or its version can't be determined. --stamp-scope
    decides which compiles write a stamp at all: `always` (default),
    `report` (only as part of a -r/--report build, not a standalone/batch
    one), or `standalone` (the opposite). --stamp-output names the
    rendered output file in the stamp line even outside report mode (a
    report/book chapter's stamp always names the shared output, "Compiled
    as part of `book.pdf` with ...", regardless of this flag).

    PDF metadata is a separate concern from all of the above, and ON by
    default (--no-stamp-pdf-metadata turns it off): after every successful
    compile that actually produces a PDF, pdfmd writes the same package/
    pdfmd version info directly into the rendered PDF's own Info dictionary,
    as two custom keys (`PdfmdVersions`, `PdfmdBuildDate`) -- invisible on
    the rendered page and in a normal "Document Properties" panel, but
    readable with `exiftool`/`pdfinfo -meta`, and additive (merged with the
    engine's own existing Info dictionary -- pdftitle/pdfauthor/etc. are
    never overwritten). Unlike `enabled` (which edits the visible .md
    source and stays off until asked), this has no visible effect on
    anything a reader or a "Get Info" panel would normally show, so it
    defaults to on rather than needing --stamp/pdfmd-options.stamp.enabled
    first -- the two are otherwise independent switches: PDF metadata with
    the .md stamp off, the .md stamp with PDF metadata explicitly turned
    off, or both, are all valid combinations.

    As of v3.7.0 (2026-09-21) this is a post-hoc edit of the finished PDF
    (via the optional `pypdf` dependency -- silently skipped with a WARN if
    it isn't installed), not something baked into the LaTeX source before
    the engine runs. Two reasons for the change, not just a refactor:
    it now works on every engine that produces a PDF (weasyprint, typst,
    soffice, ... -- previously silently skipped on anything outside
    LATEX_ENGINES, which had no equivalent injection point this reached at
    all); and the old \\hypersetup-injection approach (a second
    --include-in-header file) could silently discard a *different*
    --include-in-header/header-includes source entirely -- confirmed
    directly: an external --metadata-file's own `header-includes:` (not the
    .md document's own front matter, which pdfmd already protects via
    document_header_file/wrap_latex_header_includes) shares pandoc's single
    `header-includes` template slot with --include-in-header, and
    --include-in-header wins outright, not merges -- so a metadata file's
    entire package load could vanish with no error at that point, surfacing
    later as a confusing "Undefined control sequence" the first time the
    document used one of that package's macros. A post-hoc PDF edit cannot
    collide with a document's preamble at all, closing this whole class of
    bug rather than one instance of it.

    Same settings via a document's own front matter or a --metadata-file's,
    nested under `pdfmd-options: stamp:` -- same precedence as
    `pdf-engine`/`engine` above (document wins over metadata file; either
    lets a shared metadata.yaml turn stamping on for every report that
    finds it). Accepts a bare `true`/`false`, a package name or list of
    names (shorthand for `{packages: [...]}`), or the full form:

        ---
        pdfmd-options:
          stamp:
            packages: [nulabreport]
            mode: history
            scope: report
        ---

    An explicit --stamp/--no-stamp/--stamp-mode/--stamp-packages/
    --stamp-scope/--stamp-output on the command line always wins over
    front matter, field by field.

Automatic source backups (--backup, v3.8.0; formats v3.9.0):
    Off by default. After every successful compile (single-file, batch,
    report/book chapter, .qmd, direct .tex, office), copies the source into
    `backup/` beside it. Runs after the BUILD NOTES stamp, and writes
    nothing when the newest existing snapshot already matches (ignoring the
    stamp's own lines). --no-backup forces it off for one run. Same front-
    matter/metadata-file cascade as `stamp:` above, as a bare `true`/
    `false`, a directory name, or the full form:

        ---
        pdfmd-options:
          backup:
            dir: backup      # relative to the document; default `backup`
            format: dashed   # see below; default `compact`
            keep: 30         # newest N plain snapshots; default 0 = all
        ---

    `format:` (or --backup-format for one run) is a preset or a template:

        compact  report.md.bak.20260924091500      (default)
        dashed   report.md.bak.20260924-091500
        stem     report_20260924-091500.md         (opens in its own app)
        suffix   report.md.20260924-091500.bak
        short    report.md.09-24_09-15-00.bak
        custom   any mix of {name} {stem} {ext} and strftime codes,
                 e.g. "{stem}-v%Y%m%d-%H%M%S{ext}"

    Switching format never orphans older snapshots: every one of those
    shapes (plus pdfmd's own `.bak-YYYYMMDD[letter]` and hand-tagged names
    like `report.md.pre-irstack.20260923-211848.bak`) counts as a snapshot
    of that file for the "unchanged since" check, ordered by the date in
    its name (mtime when there isn't one). `keep:` only prunes plain-
    timestamp snapshots; a tagged name (`.pre-...`, `.before-...`, any
    extra label) is a deliberate milestone and is never deleted. A .qmd
    only reads its own front matter (no metadata.yaml, same as the rest
    of the Quarto path).
"""
# Versioned from here on -- see CHANGELOG.md next to this file.
#
# BEFORE EDITING THIS FILE: read CLAUDE.md next to this file first. In
# short -- make sure everything is committed in git (`git status` clean)
# before changing anything, and
# add a CHANGELOG.md entry (bump PDFMD_VERSION below) IN THE SAME
# EDIT, not after. This is a shared dependency across multiple, unrelated
# Markdown-to-PDF pipelines (nulabreport is one, but not the only one) --
# CLAUDE.md explains why a fix that looks scoped to one project's document
# can still break another, and why a fix should be verified through the
# full `pdfmd` pipeline, not just by compiling the `.tex` it produced.
#
# This script began as a one-line `pandoc file.md -o file.pdf` wrapper and
# was revised many times since, across ChatGPT, ChatGPT Codex, Claude Chat,
# Cowork, and Claude Code sessions, with no version marker or changelog kept
# at any point -- there is no reliable "v1.x" history left to backfill,
# only inconsistent backups/pdfmd.py.bak-* snapshots from a handful of
# points in that history. Rather than fabricate a precise-looking but
# unreliable 1.x history from those gaps, versioning restarts at 2.0.0 here
# (2026-09-16, the author's call) as an honest baseline: this is where real
# changelog tracking begins, not a claim about how many changes preceded it.
PDFMD_VERSION = "3.13.0"
import argparse
import filecmp
from fnmatch import fnmatchcase
from functools import lru_cache
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

if sys.version_info < (3, 10):
    # Checked before any annotation below is evaluated: on 3.9 the first
    # `list[str] | None` would otherwise fail with a cryptic TypeError.
    # macOS's own /usr/bin/python3 is 3.9, so this is a real first-run trap.
    raise SystemExit(f"pdfmd needs Python 3.10 or newer (this is {sys.version.split()[0]}). "
                     "Install it with `pipx install pdfmd-cli`, "
                     "which picks a suitable Python, or run pdfmd.py with a newer python3.")
import unicodedata
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from shutil import which
from tempfile import NamedTemporaryFile, mkdtemp, mkstemp
from textwrap import dedent
from typing import Iterator

try:
    import yaml
except ImportError:
    yaml = None

try:
    import pypdf
except ImportError:
    pypdf = None

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
# Installed-by-default stand-ins, tried in order when one of the three fonts
# above isn't installed (a fresh machine rarely has JetBrains Mono or, on
# macOS, DejaVu Serif). Without this, every LaTeX engine failed with a
# fontspec error and the build silently fell through to typst/HTML engines.
MONOFONT_STAND_INS = ("Menlo", "DejaVu Sans Mono", "Liberation Mono", "Courier New")
# For DEFAULT_FONT's missing-glyph retry: system serifs that, like DejaVu,
# cover the arrows/comparison/Greek that STIX Two Text lacks (it has no ≥).
SERIF_STAND_INS = ("Times New Roman", "Liberation Serif", "Georgia")


@lru_cache(maxsize=None)
def installed_font_families() -> frozenset[str] | None:
    """Lower-cased font family names from fontconfig, or None without fc-list."""
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return None
    try:
        out = subprocess.run([fc_list, ":", "family"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return frozenset(name.strip().casefold() for line in out.splitlines() for name in line.split(","))


@lru_cache(maxsize=None)
def font_missing(family: str) -> bool:
    """True only when a font is known NOT to be installed.

    Asks fontconfig (fc-list) first, then luaotfload-tool (ships with TeX
    Live/MacTeX, so it's there whenever lualatex is). If neither tool is
    available the answer is False -- "assume it's there", exactly the
    behavior before this check existed.
    """
    families = installed_font_families()
    if families is not None:
        return family.casefold() not in families
    tool = shutil.which("luaotfload-tool")
    if not tool:
        return False
    try:
        result = subprocess.run([tool, f"--find={family}"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return "Cannot find" in result.stdout + result.stderr


@lru_cache(maxsize=None)
def default_monofont() -> str:
    """DEFAULT_MONOFONT, or the first installed MONOFONT_STAND_INS entry."""
    for family in (DEFAULT_MONOFONT, *MONOFONT_STAND_INS):
        if not font_missing(family):
            if family != DEFAULT_MONOFONT:
                print(f"WARN  font: {DEFAULT_MONOFONT} is not installed; using {family} for code "
                      "(install it, or set monofont:, to change this)", file=sys.stderr)
            return family
    return DEFAULT_MONOFONT


@lru_cache(maxsize=None)
def fallback_font() -> str:
    """DEFAULT_FONT for the missing-glyph retry, else an installed stand-in.

    Retrying with a font that isn't installed turned a render with a few
    missing glyphs into a failed build (every LaTeX engine hits the same
    fontspec error). With no stand-in either, PREFERRED_FONT is returned,
    so the retry repeats the first attempt instead of failing.
    """
    for family in (DEFAULT_FONT, *SERIF_STAND_INS):
        if not font_missing(family):
            if family != DEFAULT_FONT:
                print(f"WARN  font: {DEFAULT_FONT} is not installed; using {family} for "
                      "missing-glyph fallback", file=sys.stderr)
            return family
    return PREFERRED_FONT


@lru_cache(maxsize=None)
def preferred_font() -> str:
    """PREFERRED_FONT, or the fallback font when it isn't installed."""
    if font_missing(PREFERRED_FONT):
        replacement = fallback_font()
        if replacement != PREFERRED_FONT:
            print(f"WARN  font: {PREFERRED_FONT} is not installed; using {replacement} instead "
                  "(install it, or set mainfont:/-f, to change this)", file=sys.stderr)
            return replacement
    return PREFERRED_FONT
DEFAULT_MARGIN = "1in"
DEFAULT_VARS = []
AUTO_METADATA_DISABLED = object()

# Cosmetic-only (never affects what pdfmd actually does, only how a path is
# PRINTED), so a plain module-level flag rather than threading a parameter
# through every AUTO-announcement/log_cmd call site -- set once from
# args.full_paths at the top of main(), before any conversion work starts.
# Added 2026-09-20 (the author): the default full-absolute-path printing that
# announce_preambles()/log_cmd()/the AUTO YAML and AUTO MD lines used before
# this is fine from a shallow directory (Downloads) but genuinely hard to
# read from a deep one (a real example that prompted this: a path under
# .../Library/CloudStorage/OneDrive-.../Documents/Fall26/CHEM341/guides/M1).
SHOW_FULL_PATHS = False
# Set from --no-citeproc in main(). A real pdfmd flag rather than a string
# looked for in the passthrough Pandoc options: Pandoc itself has no
# --no-citeproc, so leaving it in that list made Pandoc reject the whole
# command (fixed v3.10.0).
CITEPROC_DISABLED = False


def display_path(path: Path) -> str:
    """Format `path` for a user-facing AUTO/CMD message.

    Relative to the current working directory by default (SHOW_FULL_PATHS
    False, the default -- see --full-paths), which is what a caller
    actually invoking pdfmd from a project directory wants to read; falls
    back to the absolute path when `path` isn't under cwd at all (a system
    temp file, e.g.) since a relative path can't reach it, or when
    SHOW_FULL_PATHS is True (--full-paths, for a copy-pasteable absolute
    path -- e.g. to hand to another tool, or when cwd itself is ambiguous
    in a script's own log).
    """
    if SHOW_FULL_PATHS:
        return str(path)
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except (OSError, ValueError):
        return str(path)

# Auto-discovered yaml/tex/lua files may live directly beside the document
# (the original convention) or inside this subdirectory instead, so a
# report's own top-level folder can hold just its .md source and rendered
# output -- everything else (metadata.yaml, a shared .bib/.csl a metadata.yaml
# points at, preamble.tex, lua filters, and anything a preamble's own raw
# LaTeX \input pulls in relative to pandoc's cwd -- see resource_path_option's
# docstring) can sit out of sight together. See accessory_directories().
ACCESSORY_DIRNAME = "metadata"

# --no-auto KIND values, and its "font" shorthand for both font kinds at
# once. See build_parser()'s --no-auto help text for what each kind does.
NO_AUTO_KINDS = frozenset({
    "reader", "title", "margin", "mainfont", "monofont", "font", "tablewidth",
    "metadata", "yaml", "preamble", "tex", "lua", "files", "standalone",
    "texdirect", "officedirect", "crossref", "citationengine", "csvtable",
    "papersize",
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


def accessory_directories(directory: Path) -> list[Path]:
    """Return `directory`, plus its ACCESSORY_DIRNAME subdirectory if present.

    Every filename-based auto-discovery (metadata YAML, preambles, Lua
    filters) searches both: a document's own directory (files placed
    directly beside it, the original convention) and, when it exists, a
    metadata/ subfolder holding the same kind of files, so a report's own
    top-level folder can hold nothing but its .md source and rendered
    output. Checked fresh on every call rather than cached -- cheap, and a
    directory created between calls (unlikely, but free to support this way)
    is picked up.
    """
    accessory = directory / ACCESSORY_DIRNAME
    return [directory, accessory] if accessory.is_dir() else [directory]


def resource_path_option(document_directory: Path, pandoc_cwd: Path,
                         metadata_files: list[Path] | None = None) -> list[str]:
    """--resource-path to keep image/include lookups anchored to the
    document's own directory even when pandoc_cwd points elsewhere.

    pandoc_cwd (see convert_one and main()'s report-mode branch) normally
    equals document_directory, but is set to the first discovered metadata
    file's own directory instead -- an ACCESSORY_DIRNAME subfolder (see
    accessory_directories()), or an explicit -y from a shared directory --
    so that a preamble's raw LaTeX \\input (e.g. a shared chemicals.tex) and
    a metadata.yaml's own relative bibliography:/csl: keys resolve against
    THAT directory. Without this, a document's own relative image paths
    would silently resolve against the same directory instead of the
    document's, the moment metadata moves out of the document's own folder.
    A no-op whenever the two already coincide -- every pipeline that doesn't
    use a metadata/ subfolder or an out-of-tree -y keeps its exact previous
    command line.

    A metadata file that is a SYMLINK also adds its target's real directory,
    at the end of the list (v3.11.0). Pandoc resolves `bibliography:` through
    --resource-path, so one shared metadata file symlinked into many folders
    can say `bibliography: refs.bib` for the refs.bib beside its real copy,
    instead of hard-coding an absolute path. Appended last, so it only
    decides a lookup that would otherwise fail: anything that resolves
    today still resolves to the same file.
    """
    extra: list[Path] = []
    for metadata in metadata_files or []:
        real_directory = metadata.resolve().parent
        if real_directory != metadata.parent.resolve() and real_directory not in extra:
            extra.append(real_directory)
    if document_directory == pandoc_cwd and not extra:
        return []
    entries = ([str(document_directory)] if document_directory != pandoc_cwd else []) + ["."]
    return ["--resource-path", os.pathsep.join(entries + [str(d) for d in extra])]


def tex_search_env(document_directory: Path, pandoc_cwd: Path) -> dict[str, str] | None:
    """TEXINPUTS for the pdf-engine subprocess, so a raw LaTeX command with a
    relative path still resolves against the document's own directory even
    when pandoc_cwd points elsewhere (see resource_path_option's docstring
    for why pandoc_cwd can differ from document_directory at all).

    --resource-path (resource_path_option, above) only helps PANDOC'S OWN
    image resolution -- a real Image AST node from Markdown ``![]()``
    syntax. Per pandoc's own manual, it "only has an effect when pandoc
    itself needs to find an image... It will not cause image paths to be
    rewritten in other cases (e.g., when pandoc is generating LaTeX)." Raw
    LaTeX passed through untouched -- a bare ``\\includegraphics{...}``, or
    any package macro that reads a data file by relative path (e.g.
    nulabreport's ``\\irspectrum``/``\\irspectrumcompare``, which hand a
    relative CSV path to pgfplots' own table-reading machinery) -- is
    resolved entirely by the TeX engine's own kpathsea search relative to
    ITS working directory (pandoc_cwd), not document_directory. Found via a
    real report (LR4-5): a metadata/ subfolder pulled pandoc_cwd away from
    the document's own directory and broke BOTH kinds of reference the same
    way -- \\includegraphics (TLC contour figures) and pgfplots table reads
    (IR spectra CSVs). A report-local \\graphicspath fixed the first alone;
    TEXINPUTS is the one mechanism kpathsea honors for every one of these at
    once, so it belongs here rather than in a per-project preamble.

    Returns None (meaning: leave the subprocess's environment untouched --
    exactly today's behavior) when document_directory == pandoc_cwd, the
    common case with no metadata/ subfolder or out-of-tree -y in play,
    where nothing is broken and nothing needs fixing.
    """
    if document_directory == pandoc_cwd:
        return None
    env = os.environ.copy()
    env["TEXINPUTS"] = f"{document_directory}{os.pathsep}{env.get('TEXINPUTS', '')}"
    return env


def frontmatter_pdfmd_options(md_path: Path) -> dict:
    """Parse a document's own ``pdfmd-options:`` front-matter block.

    A real YAML parse (not the regex sniffing the rest of this script uses
    for single scalar keys) because this block can be an arbitrarily
    nested mapping -- ``no-auto: [monofont, margin]`` and
    ``no-auto: true`` both have to parse correctly, not just be detected.
    Returns {} if there's no front matter, no ``pdfmd-options`` key, the
    front matter doesn't parse as YAML, or PyYAML isn't installed --
    document-level pdfmd-options are optional sugar, not a hard dependency
    of the rest of the script. Also {} for a binary office document
    (OFFICE_INPUT_EXTENSIONS) without even trying to read it as text --
    caught via a real crash (UnicodeDecodeError) the first time an actual
    .docx/.pptx was fed through pdfmd for this round's own office-direct
    feature: effective_no_auto()/resolve_engines() call this
    unconditionally for every input, .tex and now office documents
    included, on the way to either one's own direct (non-Pandoc) branch.
    """
    if yaml is None or md_path.suffix.lower() in OFFICE_INPUT_EXTENSIONS:
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
# BUG, found and fixed 2026-09-16 (the author, via a nulabreport/QCA report): this
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
-- pandoc.utils.stringify() renders a Math inline as its raw LaTeX SOURCE
-- (e.g. "\frac{1.0 \times 10^{-14}}{[OH^-]}", 34 characters), not its
-- typeset width (a fraction that renders at a fraction of that) -- found
-- via a real chemistry-report table (Ksp/uncertainty-propagation cells)
-- getting stretched by cell_length() treating that raw command text as
-- 34 characters of visual width. No exact fix is possible here either
-- (same reasoning as CHAR_BUDGET above -- no font has been measured yet
-- when this filter runs), so this is a flat divisor, not a real LaTeX-
-- width estimator: a short subscript/superscript like "K_{sp}" (6 raw
-- characters, renders about as wide as "Ksp") and a stacked fraction
-- like the one above (34 raw characters, renders roughly as wide as its
-- widest of numerator/denominator, maybe 10-12) both land closer to
-- their real rendered width divided by roughly 3 than left undivided.
local MATH_LENGTH_DIVISOR = 3

local function math_overcount(contents)
  local overcount = 0
  contents:walk({
    Math = function(m)
      local source_len = #m.text
      overcount = overcount + (source_len - math.ceil(source_len / MATH_LENGTH_DIVISOR))
    end
  })
  return overcount
end

local function cell_length(cell)
  local length = #pandoc.utils.stringify(cell.contents) - math_overcount(cell.contents)
  if length < 1 then length = 1 end
  return length
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

# Auto-applied whenever a document uses a `.csv`-classed fenced Div (see
# contains_csv_table()) -- turns a Div like
#
#     ::: {.csv file="data.csv"}
#     :::
#
# into an actual table, read from that CSV/TSV file, instead of a hand-
# transcribed pipe table -- requested directly (2026-09-19, the author), alongside
# a size cap so an accidentally-huge file doesn't produce a many-page
# table nobody intended: 10 rows and 7 columns by default (`rows`/`cols`
# attributes override either, or set to `all` for no cap), matching the
# request's own suggested numbers. A Div, not raw-text substitution keyed
# on some new sigil character (`\input`-style inclusion was floated for
# the same underlying reason, and rejected for exactly the risk this
# avoids): Pandoc has already correctly told code blocks/spans apart from
# real content by the time a Lua filter's Div() callback ever fires, so
# `::: {.csv ...}` typed inside a fenced code block as a literal example
# is never mistaken for the real thing -- the false-fire risk the author raised
# for a raw-text approach simply can't happen at this level.
#
# Builds the table via pandoc.read() on a hand-assembled GFM pipe-table
# string, rather than constructing pandoc.Table's own AST nodes directly
# -- both produce an equivalent Table block, but this one reuses Pandoc's
# own (already-correct) pipe-table parser instead of this filter needing
# to get every field of TableHead/TableBody/Cell/ColSpec exactly right by
# hand, and it guarantees the result looks EXACTLY like a table pdfmd
# already knows how to handle everywhere else (including
# TABLE_WIDTH_LUA_FILTER re-balancing it afterward, since a pipe-table's
# parsed colspecs are the same "default width" shape a document's own
# hand-written table would produce).
#
# The CSV/TSV line parser handles quoted fields (comma/tab inside a
# quoted cell, and a doubled `""` for a literal quote) but, deliberately,
# not a quoted field containing a literal embedded newline spanning
# multiple physical lines -- a genuine RFC 4180 parser is real added
# complexity for a case simple spreadsheet exports essentially never
# produce, and this filter is explicitly meant to stay simple.
CSV_TABLE_LUA_FILTER = r"""
local DEFAULT_MAX_ROWS = 10
local DEFAULT_MAX_COLS = 7

local function parse_csv_line(line, delim)
  local fields = {}
  local field = {}
  local in_quotes = false
  local i = 1
  local n = #line
  while i <= n do
    local c = line:sub(i, i)
    if in_quotes then
      if c == '"' then
        if line:sub(i + 1, i + 1) == '"' then
          table.insert(field, '"')
          i = i + 1
        else
          in_quotes = false
        end
      else
        table.insert(field, c)
      end
    else
      if c == '"' then
        in_quotes = true
      elseif c == delim then
        table.insert(fields, table.concat(field))
        field = {}
      else
        table.insert(field, c)
      end
    end
    i = i + 1
  end
  table.insert(fields, table.concat(field))
  return fields
end

local function limit_or_all(value, default)
  if value == nil or value == "" then return default end
  if value:lower() == "all" then return math.huge end
  return tonumber(value) or default
end

local function escape_cell(text)
  text = (text or ""):gsub("\r", ""):gsub("\n", " ")
  -- A leading/trailing "|" (already escaped) still needs the pipe-table
  -- delimiter itself escaped; a literal backslash is left alone, unlike
  -- a general Markdown escaper, since a CSV cell's own backslashes (a
  -- Windows path, a regex) should render as typed, not be mistaken for
  -- Markdown escape sequences. Wrapped in parens: string.gsub returns
  -- TWO values (the string, and a count of substitutions made), and a
  -- bare `return text:gsub(...)` -- as the LAST argument to a later
  -- table.insert(escaped, escape_cell(...)) call -- leaks that count as
  -- a second, unwanted argument, which table.insert then misreads as
  -- its own `pos` parameter. Caught directly, as a real Lua runtime
  -- error ("bad argument #2 to 'insert' (number expected, got
  -- string)"), the first time this filter ran against an actual CSV.
  return (text:gsub("|", "\\|"))
end

function Div(div)
  if not div.classes:includes("csv") then return nil end
  local path = div.attributes["file"]
  if not path then
    io.stderr:write("WARN  .csv div has no file= attribute; leaving it empty\n")
    return {}
  end
  local file = io.open(path, "r")
  if not file then
    io.stderr:write("WARN  .csv: could not open '" .. path .. "'; leaving it empty\n")
    return {}
  end

  local delim = div.attributes["delimiter"]
  if delim == nil or delim == "" then
    delim = path:match("%.tsv$") and "\t" or ","
  end
  local max_rows = limit_or_all(div.attributes["rows"], DEFAULT_MAX_ROWS)
  local max_cols = limit_or_all(div.attributes["cols"], DEFAULT_MAX_COLS)
  local has_header = div.attributes["header"] ~= "false"

  local header_fields = nil
  local data_rows = {}
  local total_data_rows = 0
  local total_cols = 0
  local rows_truncated = false
  local cols_truncated = false

  for line in file:lines() do
    if line ~= "" then
      local fields = parse_csv_line(line, delim)
      if #fields > total_cols then total_cols = #fields end
      if #fields > max_cols then
        cols_truncated = true
        local kept = {}
        for i = 1, max_cols do kept[i] = fields[i] end
        fields = kept
      end
      if has_header and header_fields == nil then
        header_fields = fields
      else
        total_data_rows = total_data_rows + 1
        if #data_rows < max_rows then
          table.insert(data_rows, fields)
        else
          rows_truncated = true
        end
      end
    end
  end
  file:close()

  local shown_cols = math.min(total_cols, max_cols)
  if not header_fields then
    header_fields = {}
    for i = 1, math.max(shown_cols, 1) do
      header_fields[i] = "Column " .. i
    end
  end

  local lines = {}
  local function emit_row(fields)
    local escaped = {}
    for i = 1, #header_fields do
      table.insert(escaped, escape_cell(fields[i]))
    end
    table.insert(lines, "| " .. table.concat(escaped, " | ") .. " |")
  end
  emit_row(header_fields)
  table.insert(lines, "|" .. string.rep(" --- |", #header_fields))
  for _, row in ipairs(data_rows) do
    emit_row(row)
  end

  if rows_truncated or cols_truncated then
    local shown_rows = #data_rows
    local note = string.format(
      "*(showing %d of %d row%s, %d of %d column%s -- use `rows=all`/`cols=all`, or " ..
      "`rows=N`/`cols=N`, on this `.csv` div to include more)*",
      shown_rows, total_data_rows, total_data_rows == 1 and "" or "s",
      shown_cols, total_cols, total_cols == 1 and "" or "s")
    table.insert(lines, "")
    table.insert(lines, note)
    io.stderr:write("WARN  " .. path .. ": showing " .. shown_rows .. " of " ..
                     total_data_rows .. " row(s), " .. shown_cols .. " of " ..
                     total_cols .. " column(s) -- see the note under the table\n")
  end

  -- Trailing blank line required: confirmed directly (a real generated
  -- table's last row rendered as a stray, unparsed Str/Space paragraph
  -- instead of the table's own last row) that pandoc.read(), called from
  -- inside a Lua filter, needs one to correctly close out a pipe table's
  -- final row -- pandoc's own CLI reading the identical text from a file
  -- does not need this, so this is specifically a pandoc.read()-from-a-
  -- filter quirk, not a general GFM pipe-table requirement.
  local parsed = pandoc.read(table.concat(lines, "\n") .. "\n\n", "gfm")
  return parsed.blocks
end
"""


@contextmanager
def csv_table_filter() -> Iterator[Path]:
    """Materialize CSV_TABLE_LUA_FILTER to a temp file for --lua-filter.

    Same reasoning as table_width_filter(): fixed content, so a plain
    system-tempdir file, not one placed beside the document.
    """
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".lua",
                            prefix="pdfmd-csvtable-", delete=False) as temporary:
        temporary.write(CSV_TABLE_LUA_FILTER)
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


CSV_DIV_RE = re.compile(r"\{[^}\n]*\.csv\b[^}\n]*\}")


def contains_csv_table(md_path: Path) -> bool:
    """Detect a `.csv`-classed fenced Div (see CSV_TABLE_LUA_FILTER)."""
    text = md_path.read_text(encoding="utf-8-sig")
    return bool(CSV_DIV_RE.search(text))


def csv_table_filter_args(sources: Path | list[Path], no_auto: list[str] | None,
                          csv_filter_path: Path) -> list[str]:
    """``--lua-filter`` for CSV_TABLE_LUA_FILTER, only when actually needed.

    Mirrors crossref_filter_args()'s own shape and reasoning: silently a
    no-op when --no-auto csvtable disables it or no source actually uses
    a `.csv` div. Must run BEFORE the table-width filter (the caller is
    responsible for that ordering) so a CSV-generated table gets the same
    width-balancing pass a hand-written one would.
    """
    if auto_disabled(no_auto, "csvtable"):
        return []
    files = sources if isinstance(sources, list) else [sources]
    if not any(contains_csv_table(file) for file in files):
        return []
    return ["--lua-filter", str(csv_filter_path)]


# Engines are tried in this order only when the user did not request one.
# An explicit --engine is never overridden.
PDF_ENGINES = (
    "lualatex", "xelatex", "pdflatex", "latexmk", "tectonic", "typst",
    "weasyprint", "wkhtmltopdf", "pagedjs-cli", "prince", "context",
    "groff", "pdfroff", "soffice",
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
    "14": "soffice", "libreoffice": "soffice", "office": "soffice",
}
LATEX_ENGINES = frozenset({"lualatex", "xelatex", "pdflatex", "latexmk", "tectonic", "context"})
PREAMBLE_FILENAMES = ("preamble.tex", "latex-preamble.tex")

# Pandoc *writer* names (as opposed to LATEX_ENGINES' *engine* names --
# "context" unavoidably appears in both, since it is both) that need a real
# LaTeX preamble (\documentclass, font/geometry setup, a project's own
# preamble.tex) to be a complete, independently compilable document rather
# than a bare Pandoc-LaTeX fragment. Drives the --standalone default and the
# preamble/header-includes/font/margin auto-discovery for --to (or an -o
# file with one of FORMAT_EXTENSION's matching extensions) targeting one of
# these, mirroring what happens on the way to a PDF through the same writer.
TEX_STANDALONE_FORMATS = frozenset({"latex", "beamer", "context"})

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
    "office": ("soffice",),
}


def resolve_soffice() -> str | None:
    """Locate the LibreOffice/soffice binary, beyond a bare PATH lookup.

    A common real-world setup (confirmed on this machine) has `soffice`
    reachable only through an interactive shell alias pointing straight at
    the macOS .app bundle's own binary -- invisible to both which() and
    subprocess (neither one consults shell aliases, only PATH), so a plain
    which("soffice") silently reports it missing even though it works
    fine for the user every day at a terminal prompt. Checked, in order:
    `soffice` on PATH, `libreoffice` on PATH (the usual Linux package
    name -- often a symlink to the same binary), then the standard macOS
    app-bundle path directly, or on Windows the default install folders
    under %ProgramFiles% / %ProgramFiles(x86)%.
    """
    for name in ("soffice", "libreoffice"):
        found = which(name)
        if found:
            return found
    if sys.platform == "darwin":
        mac_path = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if mac_path.exists():
            return str(mac_path)
    if sys.platform == "win32":
        # The Windows installer doesn't add LibreOffice to PATH.
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(variable)
            if base and (Path(base) / "LibreOffice" / "program" / "soffice.exe").exists():
                return str(Path(base) / "LibreOffice" / "program" / "soffice.exe")
    return None


def engine_executable(engine: str) -> str | None:
    """which(), except for "soffice" -- see resolve_soffice()'s docstring.

    Every PDF_ENGINES membership check (installed_engines, select_engines,
    dependency_report) goes through this instead of a bare which() so
    "soffice" is recognized as available under the same real-world
    condition the pipeline will actually invoke it under.
    """
    return resolve_soffice() if engine == "soffice" else which(engine)


def installed_engines() -> list[str]:
    """Return PDF engines that are currently executable, in fallback order."""
    return [engine for engine in PDF_ENGINES if engine_executable(engine)]


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
            installed_in_group = [engine for engine in group if engine_executable(engine)]
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
        if engine_executable(requested):
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
                    metadata_files: list[Path] = (), verbose: bool = False) -> list[str]:
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

    The resolved chain is only ever printed under ``--verbose`` -- same
    convention as every other "AUTO ..." discovery note (see convert_one's
    own note()/flush_summary()) -- as a plain ``ENGINE`` line, not
    ``AUTO ENGINE``: this one restriction can come from either the document
    or its metadata file, so "AUTO" would misattribute a document-level
    setting as auto-discovered when it's an explicit request.
    """
    if cli_engine is not None or target_format != "pdf":
        return engines
    requested = frontmatter_engine(md_path, metadata_files)
    if not requested:
        return engines
    resolved = select_engines(requested, presentation,
                              label=f"pdf-engine setting for {md_path.name}")
    if verbose:
        print(f"ENGINE  {md_path}: " + " -> ".join(resolved))
    return resolved


def dependency_report() -> bool:
    """Print executable availability and return whether conversion can run."""
    pandoc = which("pandoc")
    print(f"{'OK  ' if pandoc else 'MISS'}  pandoc" + (f"  ({pandoc})" if pandoc else ""))
    for number, engine in enumerate(PDF_ENGINES, start=1):
        path = engine_executable(engine)
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


def has_standalone_option(options: list[str]) -> bool:
    """Return whether the caller already explicitly supplied -s/--standalone.

    Also true for ``--template``, since Pandoc treats an explicit template
    as already asking for a standalone document (and passing both is
    harmless but redundant) -- so a caller who wants their own template
    driving a TEX_STANDALONE_FORMATS render isn't fighting pdfmd's own
    ``--standalone`` default.
    """
    return any(option in {"-s", "--standalone"}
               or option == "--template" or option.startswith("--template=")
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
    for folder in accessory_directories(directory):
        for path in folder.glob("*.tex"):
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
        print(f"AUTO TEX   {display_path(preamble)}")
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
def prepared_latex_inputs(paths: list[Path], latex_engine: bool,
                          typst_engine: bool = False) -> Iterator[list[Path]]:
    """Yield temporary, corrected inputs for LaTeX-family renders when
    needed -- or, with `typst_engine` instead, for the Typst engine's own
    unrelated margin-scalar bug (see fix_typst_margin_scalar()). The two
    are mutually exclusive; at most one corrector ever applies to a given
    render, same as `latex_engine` alone before this.
    """
    corrector = (wrap_latex_header_includes if latex_engine
                else fix_typst_margin_scalar if typst_engine else None)
    temporary_paths: list[Path] = []
    prepared: list[Path] = []
    try:
        for path in paths:
            text = path.read_text(encoding="utf-8-sig")
            corrected = corrector(text) if corrector else text
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
    line beats one set in metadata. So the moment ANY ``--include-in-header``
    reaches the command line -- an auto-included preamble, or pdfmd's own
    PDF-metadata stamp header (on by default; see ``--stamp-pdf-metadata``) --
    a ``header-includes`` block in that document's own front matter is
    silently discarded, even if nothing about preambles is otherwise in play.
    Confirmed directly (2026-09-20, CHEM 341 session): a document with its
    own YAML ``header-includes`` and no preamble.tex/latex-preamble.tex beside
    it still lost that block, because the PDF-metadata stamp header alone was
    enough to trigger it. Extracting it here lets the caller re-append it as a
    trailing ``--include-in-header``, after anything else, which is where a
    per-document override belongs -- so every call site that may add ANY
    other ``--include-in-header`` must pass ``active=True`` here too, not just
    the ones adding a preamble.

    Handles both YAML shapes a ``header-includes:`` value can take: a block
    scalar (``header-includes: |`` ... indented lines), the ORIGINAL and
    only shape this function understood before 2026-09-20, and a sequence
    (``header-includes:\\n  - \\usepackage{mhchem}\\n  - ...``) -- the more
    common form in practice, and the one that silently defeated this whole
    safeguard for any document using it: the block-scalar-only regex below
    simply never matched, so `active` calculations based on this function
    looked right while the document's actual header-includes kept vanishing
    anyway. A real YAML parse (PyYAML, already an optional/soft dependency
    elsewhere in this file -- see `frontmatter_pdfmd_options`) handles the
    sequence shape correctly, one raw LaTeX line per list item, joined with
    newlines, matching how Pandoc's own template concatenates such a list.
    Falls back to the original block-scalar-only regex when PyYAML isn't
    installed -- worse than a real parse, but not a new limitation; a
    sequence-style document with no PyYAML available is simply back to the
    pre-2026-09-20 (bugged) behavior for this one shape, same as it always
    was.
    """
    if yaml is not None:
        loose_front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
        if loose_front_matter:
            try:
                data = yaml.safe_load(loose_front_matter.group(1))
            except yaml.YAMLError:
                data = None
            if isinstance(data, dict):
                value = data.get("header-includes")
                if isinstance(value, list):
                    lines_out = [str(item) for item in value if item is not None]
                    return "\n".join(lines_out).strip() or None
                if isinstance(value, str):
                    return value.strip() or None
                return None

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
    directories: list[Path] = accessory_directories(md_path.parent)
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


def strip_lookup_suffix(name: str) -> str:
    """Drop a trailing .md/.markdown/.pdf from a bare-name lookup, and nothing
    else. Path.stem would also eat a dot that is part of the name itself, so
    'prelab5.5' silently resolved to prelab5.md instead of prelab5.5.md."""
    path = Path(name)
    return path.stem if path.suffix.lower() in {".md", ".markdown", ".pdf"} else name


def name_candidates(value: str) -> list[str]:
    value = strip_lookup_suffix(value)
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
    requested = strip_lookup_suffix(value.name)
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


def frontmatter_margin_scalar(md_path: Path, variables: list[str]) -> str | None:
    """Return a document's own bare scalar ``margin:`` value, IF
    translating it into a working ``geometry:margin=...`` for LaTeX-family
    engines is safe -- or None when there's nothing to translate. Same
    scope as pagesize_typo_value() above: front matter and -V variables
    only, not metadata files or preambles.

    ``margin:`` is a real Pandoc variable for the TYPST template only (see
    fix_typst_margin_scalar() below) -- Pandoc's LaTeX template never
    reads it at all, only ``geometry:`` does (a list of "key=value"
    strings that becomes \\usepackage[...]{geometry}). has_geometry()
    already treats a bare ``margin:`` as "a margin setting exists"
    (correctly, so DEFAULT_MARGIN isn't injected on top of it), but
    nothing translated that value into the one variable LaTeX's own
    template actually consumes -- so a document with ONLY
    ``margin: 2.54cm`` and no ``geometry:`` silently kept LaTeX's own much
    wider article-class default margins on every LaTeX-family engine,
    the requested value never taking effect at all. Confirmed directly
    (2026-09-28), alongside the Typst-side bug the same value triggers
    (see fix_typst_margin_scalar()): ``--engine typst`` errored outright
    on it ("unexpected comma"), while every LaTeX-family engine rendered
    fine -- just silently ignoring the requested margin instead of
    erroring, which is arguably the worse of the two failures.

    Returns None when: no ``margin:`` at all; a real ``geometry:`` is set
    anywhere (front matter or -V) -- an explicit geometry always wins,
    untouched; or ``margin:`` is already a YAML mapping/per-side block
    rather than a plain scalar (translating a ``top:``/``bottom:``/
    ``left:``/``right:`` breakdown into ``geometry:`` options is a
    reasonable follow-up, out of scope here -- only the single-value case
    this session's bug report actually hit is handled).
    """
    if any(variable.startswith(("geometry=", "geometry:")) for variable in variables):
        return None
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    block = front_matter.group(1)
    if re.search(r"^geometry\s*:", block, re.MULTILINE):
        return None
    match = re.search(r"^margin\s*:[ \t]*(\S.*?)[ \t]*$", block, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip("'\"")
    return value or None


def pagesize_typo_value(md_path: Path, variables: list[str]) -> str | None:
    """Return a document's own ``pagesize:`` value, IF ``papersize:`` isn't
    already set anywhere Pandoc would see it -- a -V variable or the
    document's own front matter.

    ``pagesize`` is not a Pandoc variable at all (the real one is
    ``papersize:``) -- LaTeX's own \\documentclass options include a
    same-named ``a4paper``/``letterpaper`` *class* option, and it's an easy,
    silent mistake to write ``pagesize: a4`` expecting the same effect
    ``papersize: a4`` gets from Pandoc's own template. Pandoc's metadata
    system doesn't error on an unrecognized key -- it just sits there
    unused -- so a document can carry this typo indefinitely with no
    warning, quietly rendering at whatever the default paper size is (US
    Letter) instead of the one actually intended. Found directly (CHEM 341
    session, 2026-09-20): the task brief for that document already knew
    about this exact trap (`pagesize: a4` producing a Letter PDF) and had to
    document it as a known caveat rather than get it fixed -- worth pdfmd
    catching automatically instead. Only checked when ``papersize`` is
    absent so a document that deliberately sets both (maybe mid-migration)
    is left alone -- its own explicit ``papersize:`` always wins.
    """
    if any(variable.startswith("papersize") for variable in variables):
        return None
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    block = front_matter.group(1)
    if re.search(r"^papersize\s*:", block, re.MULTILINE):
        return None
    match = re.search(r"^pagesize\s*:\s*(.+?)\s*$", block, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip("'\"")
    return value or None


def frontmatter_papersize_value(md_path: Path) -> str | None:
    """Return a document's own ``papersize:`` value straight from its front
    matter (a real Pandoc variable, unlike ``pagesize:`` above) -- used only
    to feed typst_papersize_translation() below, not for the pagesize-typo
    detection this sits next to.
    """
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    match = re.search(r"^papersize\s*:\s*(.+?)\s*$", front_matter.group(1), re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip("'\"")
    return value or None


# Pandoc's own `papersize:` variable is LaTeX-shaped by convention ("letter",
# "legal", "a4", ...matching what a LaTeX \documentclass option expects), and
# Pandoc's LaTeX template maps it accordingly -- but Pandoc's TYPST template
# passes the same string straight through to typst's own `page(paper: ...)`
# set rule, which does NOT accept "letter"/"legal" at all; typst's own names
# are "us-letter"/"us-legal" (most other names, "a4"/"a3"/"a5"/..., already
# match typst's own naming and need no translation -- only these two are
# known to differ). A document with `papersize: letter` compiles fine on
# every LaTeX-family engine and then silently errors (or falls back to
# typst's own default) the moment --to typst is used instead -- raised
# directly (2026-09-20): "works with tex, but not with typst". Only these
# two confirmed aliases are included; extend TYPST_PAPERSIZE_ALIASES if
# another one is found to differ the same way.
TYPST_PAPERSIZE_ALIASES = {
    "letter": "us-letter",
    "legal": "us-legal",
}


def typst_papersize_translation(value: str | None) -> str | None:
    """Return typst's own name for a Pandoc papersize value, or None when
    `value` is falsy or already fine as-is (either it's not one of the
    known-different names, or it's already typst-shaped)."""
    if not value:
        return None
    return TYPST_PAPERSIZE_ALIASES.get(value.strip().casefold())


TYPST_MARGIN_RE = re.compile(r"^(?P<indent>[ \t]*)margin(?P<colon>[ \t]*:[ \t]*)(?P<val>\S.*?)[ \t]*$",
                             re.MULTILINE)


def fix_typst_margin_scalar(text: str) -> str:
    """Rewrite a document's own bare scalar ``margin:`` front-matter value
    into the ``x``/``y`` YAML mapping Pandoc's own TYPST template requires.

    Pandoc's default Typst template renders margin unconditionally as
    ``margin: ($for(margin/pairs)$$margin.key$: $margin.value$,$endfor$)``
    -- it always iterates key/value PAIRS, so a plain scalar (``margin:
    2.54cm``, exactly what every other writer -- including every LaTeX-
    family engine via the geometry:margin=... translation
    frontmatter_margin_scalar() feeds it -- accepts fine) has nothing to
    iterate and comes out as the literal, invalid ``margin: (: ,)``: a
    Typst syntax error ("unexpected comma") instead of a page margin.
    Confirmed directly (2026-09-28): a document with ``margin: 2.54cm``
    and ``pdfmd-options: {engine: typst}`` failed outright with exactly
    that error, while rendering fine (albeit at the WRONG margin --
    see frontmatter_margin_scalar()) on every LaTeX-family engine.

    Only a bare scalar is rewritten -- a ``margin:`` that's already a
    YAML mapping (a ``top:``/``bottom:``/``left:``/``right:`` or
    ``x:``/``y:`` breakdown) needs no fix; Pandoc's ``/pairs`` filter
    already turns that straight into valid Typst key/value pairs. Only
    the document's own front matter is handled, same as
    typst_papersize_translation()'s callers above -- a shared
    --metadata-file setting ``margin:`` as a scalar is a rarer case left
    unfixed, out of scope here.
    """
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return text
    block = front_matter.group(1)
    newline = "\r\n" if "\r\n" in block else "\n"

    def replace(match: re.Match) -> str:
        value = match.group("val").strip().strip("'\"")
        if not value or value.startswith(("{", "[")):
            return match.group(0)
        indent = match.group("indent")
        return f"{indent}margin:{newline}{indent}  x: {value}{newline}{indent}  y: {value}"

    fixed_block = TYPST_MARGIN_RE.sub(replace, block, count=1)
    if fixed_block == block:
        return text
    return text[:front_matter.start(1)] + fixed_block + text[front_matter.end(1):]


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
    text = md_path.read_text(encoding="utf-8-sig")
    return bool(CROSSREF_RE.search(text))


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
    if auto_disabled(no_auto, "crossref") or "pandoc-crossref" in pandoc_options:
        return []
    files = sources if isinstance(sources, list) else [sources]
    if not any(contains_crossref(file) for file in files):
        return []
    if which("pandoc-crossref") is None:
        print(f"WARN  {label}: uses pandoc-crossref syntax (@fig:/@eq:/@tbl:/@sec:/@lst: or a "
              "{#fig:...}-style attribute) but pandoc-crossref isn't installed; the reference/"
              "numbering will not resolve. Install it (e.g. `brew install pandoc-crossref`), "
              "or rewrite without crossref syntax to silence this.", file=sys.stderr)
        return []
    return ["--filter", "pandoc-crossref"]


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
    if md_path.suffix.lower() not in (".md", ".markdown"):
        return None, None
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
    reader = "gfm"
    if has_definition_list(text):
        reader += "+definition_lists"
    if contains_csv_table(md_path):
        # A `.csv` div is Pandoc's fenced_divs syntax (`::: {.csv ...} :::`),
        # which -- unlike Pandoc's own default `markdown` reader, where it's
        # on by default -- gfm doesn't enable at all, so without this a
        # front-matter-less document's `.csv` div is read as literal text
        # instead of a real Div (caught directly: a first real test of this
        # feature rendered the div's own source text verbatim in the PDF,
        # smart-quoted, instead of a table at all).
        reader += "+fenced_divs"
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


# pdfmd-options.citation-engine: "citeproc" (the default -- a document only
# needs this key at all to opt into something else), "natbib", or
# "biblatex". Routes a LaTeX-family PDF target's (or --to latex/beamer/
# context's) bibliography through Pandoc's own --natbib/--biblatex flags
# (native biber/bibtex, handled by the engine's own bibliography tooling)
# instead of --citeproc (which renders citations into the LaTeX Pandoc
# generates directly, using a CSL style, and never touches biber/bibtex at
# all). Meaningless for a non-LaTeX target (HTML/typst/docx/office) --
# silently ignored there, same as e.g. LaTeX-only geometry/monofont
# defaults already are. See convert_via_native_bibliography()'s own
# docstring for the real complication this runs into for a PDF target
# specifically: confirmed empirically that Pandoc's own PDF-making
# pipeline, when it calls a LaTeX engine directly via --pdf-engine=, never
# actually runs bibtex/biber itself (only --pdf-engine=latexmk does, since
# latexmk manages that on its own) -- lualatex/xelatex/pdflatex all leave
# citations undefined with a bare --natbib/--biblatex. Routed around by
# generating a complete standalone .tex via Pandoc first (same as the
# TEX_STANDALONE_FORMATS branch already does for --to latex), then handing
# it to compile_tex_direct()'s own engine+bibtex/biber rerun loop instead
# of letting Pandoc invoke the engine itself.
CITATION_ENGINES = frozenset({"citeproc", "natbib", "biblatex"})


def frontmatter_citation_engine(md_path: Path, metadata_files: list[Path] = ()) -> str | None:
    """Read pdfmd-options.citation-engine -- see the module comment above.

    Document's own front matter wins over a linked metadata file's,
    checked in the same metadata_files order as frontmatter_engine(), same
    precedence rule. No legacy bare-top-level spelling to support here
    (unlike pdf-engine/engine) -- this is a brand new key with no existing
    documents written against an older spelling.
    """
    options = frontmatter_pdfmd_options(md_path)
    value = options.get("citation-engine")
    if value is not None:
        return str(value).casefold()
    for metadata_file in metadata_files:
        data = metadata_file_yaml(metadata_file)
        options = data.get("pdfmd-options")
        value = options.get("citation-engine") if isinstance(options, dict) else None
        if value is not None:
            return str(value).casefold()
    return None


def frontmatter_extra_preambles(md_path: Path) -> list[Path]:
    """Read ``pdfmd-options: preamble: ...`` -- a document naming its own
    LaTeX preamble file(s) explicitly, instead of relying on the fixed
    ``preamble.tex``/``latex-preamble.tex`` auto-discovered names
    (PREAMBLE_FILENAMES) or a project's own conventions elsewhere.

    Accepts a bare string or a YAML list of strings; each path is resolved
    relative to `md_path`'s own directory (not cwd -- a document should be
    runnable from any directory). A path that doesn't exist is a hard
    SystemExit, not a silent skip: the whole point of naming a preamble
    explicitly is that it's required, unlike auto-discovery's own
    best-effort search.

    Merged with (not a replacement for) whatever find_preambles() already
    discovered by name -- see its call sites, all of which now do
    ``find_preambles(...) + frontmatter_extra_preambles(md_path)`` -- and
    appended AFTER them, so an explicit pdfmd-options.preamble can override
    a same-named auto-discovered definition. Reuses the existing "preamble"
    --no-auto KIND at every call site (both calls sit behind the same
    ``not auto_disabled(no_auto, "preamble")`` guard) -- unlike an explicit
    CLI -H, which always wins over --no-auto per this file's own documented
    rule, a pdfmd-options.preamble key is written IN the document, so
    --no-auto preamble (or a bare --no-auto) suppresses it the same as
    auto-discovery. Use an actual -H on the command line instead when a
    preamble truly must survive --no-auto preamble.

    Added 2026-09-20, directly requested alongside a real use case that
    turned out NOT to need it after all (a preamble whose own
    \\setchemfig/\\usetikzlibrary calls need chemfig/tikz loaded first,
    which only \\input from inside a document's own header-includes -- not
    any --include-in-header ordering, explicit-named or auto-discovered
    alike -- guarantees; see midterm_preamble.tex's own header comment for
    that specific case) -- but is still useful in general for a preamble
    with no such ordering dependency, and for naming one under any filename
    rather than only the two PREAMBLE_FILENAMES.
    """
    value = frontmatter_pdfmd_options(md_path).get("preamble")
    if value is None:
        return []
    names = [value] if isinstance(value, str) else (
        [str(item) for item in value] if isinstance(value, list) else [])
    resolved = []
    for name in names:
        path = (md_path.parent / name).resolve()
        if not path.is_file():
            raise SystemExit(f"{md_path}: pdfmd-options.preamble names {name!r}, "
                             f"which doesn't exist at {path}")
        resolved.append(path)
    return resolved


def frontmatter_extra_lua_filters(md_path: Path) -> list[Path]:
    """Read ``pdfmd-options: lua-filter: ...`` -- a document naming its own
    Pandoc Lua filter(s) explicitly, instead of relying on
    find_lua_filters()'s fixed auto-discovery names (``<doc-stem>.lua`` or
    ``nulabreport.lua``).

    Accepts a bare string or a YAML list of strings; each path is resolved
    relative to `md_path`'s own directory (not cwd -- a document should be
    runnable from any directory), same convention as
    frontmatter_extra_preambles. A path that doesn't exist is a hard
    SystemExit, not a silent skip: naming a filter explicitly means it's
    required, unlike auto-discovery's own best-effort search.

    Merged with (not a replacement for) whatever find_lua_filters() already
    auto-discovered -- see this function's one call site in convert_one,
    which appends these AFTER the auto-discovered ones and dedupes by
    resolved path. Both land on the command line after --citeproc (see
    run()'s own comment on that ordering) -- required for a filter, like
    fullcite.lua, that consumes citeproc's resolved bibliography div.

    Reuses the existing "lua" --no-auto KIND, same as
    frontmatter_extra_preambles reuses "preamble": a pdfmd-options.lua-filter
    key is written IN the document, so --no-auto lua (or a bare --no-auto)
    suppresses it the same as auto-discovery.

    Added 2026-09-28 for a real case: an annotated-bibliography.md using a
    citeproc-dependent filter (fullcite.lua) that isn't named after the
    document's own stem, so find_lua_filters() alone never picked it up --
    the document had to name it explicitly instead.
    """
    value = frontmatter_pdfmd_options(md_path).get("lua-filter")
    if value is None:
        return []
    names = [value] if isinstance(value, str) else (
        [str(item) for item in value] if isinstance(value, list) else [])
    resolved = []
    for name in names:
        path = (md_path.parent / name).resolve()
        if not path.is_file():
            raise SystemExit(f"{md_path}: pdfmd-options.lua-filter names {name!r}, "
                             f"which doesn't exist at {path}")
        resolved.append(path)
    return resolved


# --stamp / pdfmd-options.stamp: appends (or updates) a "BUILD NOTES" HTML
# comment at/near the end of a document recording what compiled it and when
# -- a lab-notebook-style provenance note, invisible in the rendered output
# (every writer pdfmd targets drops a raw HTML comment) but visible to
# anyone reading the .md source later. Modeled on a convention already kept
# by hand in real reports (a `<!-- ===... BUILD NOTES ... ===-->` block
# ending in a "Compiled with X vY, pdfmd vZ" line) -- this automates just
# that one line, never touching whatever else the block already holds. Off
# by default. See resolve_stamp_options, build_stamp_line and apply_stamp.
STAMP_MODES = frozenset({"replace", "history"})
STAMP_SCOPES = frozenset({"always", "report", "standalone"})
DEFAULT_STAMP_OPTIONS = {
    "enabled": False,
    "mode": "replace",
    "packages": [],
    "scope": "always",
    "include_output": False,
    # On by default, unlike 'enabled' -- embedding two custom, invisible PDF
    # Info-dictionary keys (see pdf_metadata_snippet) has no visible effect
    # on the rendered page or a normal "Document Properties" panel, and
    # never overwrites a document's real metadata, so there's little to
    # protect a caller from the way 'enabled' (which edits the visible .md
    # source) protects them by staying off until asked. Independent of
    # 'enabled': PDF metadata still needs a LaTeX-family engine and a scope
    # match (see stamp_scope_matches), but happens on every such compile
    # unless --no-stamp-pdf-metadata/pdf_metadata:false turns it off, with
    # or without --stamp/enabled ever being turned on for the .md stamp.
    "pdf_metadata": True,
}


def normalize_stamp_value(value) -> dict:
    """Normalize a pdfmd-options.stamp value into a complete options dict.

    Accepts the same range of shapes --no-auto's own settings do: a bare
    bool (on/off, everything else default), a single package name or list
    of names (shorthand for enabling stamping with just those packages), or
    a full dict of {enabled, mode, packages, scope, include_output,
    pdf_metadata}. A dict with no explicit ``enabled`` key is treated as on
    -- bothering to
    configure packages/mode/scope implies wanting it active; write
    ``enabled: false`` explicitly to keep a shared default off until a
    document (or --stamp on the command line) turns it on.
    """
    options = dict(DEFAULT_STAMP_OPTIONS)
    if isinstance(value, bool):
        options["enabled"] = value
    elif isinstance(value, str):
        options["enabled"] = True
        options["packages"] = [value]
    elif isinstance(value, list):
        options["enabled"] = True
        options["packages"] = [str(item) for item in value]
    elif isinstance(value, dict):
        options["enabled"] = bool(value.get("enabled", True))
        if "mode" in value:
            options["mode"] = str(value["mode"])
        if "packages" in value:
            packages = value["packages"]
            options["packages"] = ([str(item) for item in packages] if isinstance(packages, list)
                                   else [str(packages)])
        if "scope" in value:
            options["scope"] = str(value["scope"])
        include_output = value.get("include_output", value.get("include-output"))
        if include_output is not None:
            options["include_output"] = bool(include_output)
        pdf_metadata = value.get("pdf_metadata", value.get("pdf-metadata"))
        if pdf_metadata is not None:
            options["pdf_metadata"] = bool(pdf_metadata)
    return options


def frontmatter_stamp(md_path: Path, metadata_files: list[Path] = ()) -> dict | None:
    """Cascade a document's own pdfmd-options.stamp, then each linked
    metadata file's, in that order -- same precedence as frontmatter_engine
    (see its docstring): a shared metadata.yaml can turn stamping on for
    every report that finds it, and any one document can still override it
    with its own pdfmd-options.stamp. Returns None (not
    DEFAULT_STAMP_OPTIONS) when nothing sets it at all, so
    resolve_stamp_options can tell "nowhere set" apart from "set to off".
    """
    options = frontmatter_pdfmd_options(md_path)
    if "stamp" in options:
        return normalize_stamp_value(options["stamp"])
    for metadata_file in metadata_files:
        data = metadata_file_yaml(metadata_file)
        nested = data.get("pdfmd-options")
        if isinstance(nested, dict) and "stamp" in nested:
            return normalize_stamp_value(nested["stamp"])
    return None


def resolve_stamp_options(md_path: Path, metadata_files: list[Path], cli_overrides: dict) -> dict:
    """Effective --stamp settings: document/metadata front matter first (see
    frontmatter_stamp), then CLI flags win field-by-field on top of that --
    same "explicit CLI always wins" convention as -e/--engine and -y. Raises
    SystemExit for an unrecognized mode/scope, matching
    effective_no_auto's unknown-KIND check.
    """
    options = frontmatter_stamp(md_path, metadata_files) or dict(DEFAULT_STAMP_OPTIONS)
    options.update(cli_overrides)
    if options["mode"] not in STAMP_MODES:
        raise SystemExit(f"{md_path}: unknown --stamp mode '{options['mode']}'. "
                         f"Valid: {', '.join(sorted(STAMP_MODES))}")
    if options["scope"] not in STAMP_SCOPES:
        raise SystemExit(f"{md_path}: unknown --stamp scope '{options['scope']}'. "
                         f"Valid: {', '.join(sorted(STAMP_SCOPES))}")
    return options


def package_version(name: str) -> str | None:
    """Locate name.sty via kpsewhich and pull the version out of its own
    \\ProvidesPackage{name}[...] line -- the convention this project's own
    packages (nulabreport.sty included) already follow: a date followed by
    free text that itself starts with a bare vX.Y.Z. Returns None silently
    (a --stamp package is best-effort, never a hard requirement) if
    kpsewhich isn't installed, the package isn't found, or its
    ProvidesPackage line has no bare v-prefixed token to extract.
    """
    kpsewhich = which("kpsewhich")
    if not kpsewhich:
        return None
    result = subprocess.run([kpsewhich, f"{name}.sty"], capture_output=True, text=True)
    sty_path = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if result.returncode != 0 or not sty_path:
        return None
    try:
        text = Path(sty_path).read_text(encoding="utf-8-sig")
    except OSError:
        return None
    provides = re.search(rf"\\ProvidesPackage\{{{re.escape(name)}\}}\[([^\]]*)\]", text)
    if not provides:
        return None
    version = re.search(r"\bv\d+(?:\.\d+)*[a-zA-Z]*\b", provides.group(1))
    return version.group(0) if version else None


def package_is_used(name: str, texts: list[str]) -> bool:
    """Return whether \\usepackage/\\RequirePackage{...name...} appears in
    any of the given raw LaTeX texts (a document's preambles and its own
    header-includes) -- so a --stamp-packages entry the document doesn't
    actually load is silently left out of the stamp line, rather than
    reporting a version for a package that played no part in this compile.
    """
    pattern = re.compile(rf"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{{[^}}]*\b{re.escape(name)}\b[^}}]*\}}")
    return any(pattern.search(text) for text in texts)


def stamp_summary(options: dict, texts: list[str], verbose: bool) -> str:
    """Build the 'nulabreport v1.14.7, pdfmd v2.4.0' portion of a stamp
    line: one 'name vVERSION' per options['packages'] entry that's both
    actually loaded (package_is_used) and has a detectable version
    (package_version), in the order given, followed by pdfmd's own version.
    """
    parts = []
    for name in options["packages"]:
        if not package_is_used(name, texts):
            continue
        version = package_version(name)
        if version:
            parts.append(f"{name} {version}")
        elif verbose:
            print(f"WARN  --stamp: {name} is loaded but its version could not be "
                 "determined (kpsewhich missing, package not installed, or no "
                 "\\ProvidesPackage line)", file=sys.stderr)
    parts.append(f"pdfmd v{PDFMD_VERSION}")
    return ", ".join(parts)


def build_stamp_line(options: dict, texts: list[str], output: Path,
                     report_output: Path | None = None, verbose: bool = False) -> str:
    """Compose one stamp line: 'Compiled [as part of `X`/to `X`] with
    PACKAGES, pdfmd vVERSION -- TIMESTAMP'. report_output (this document
    compiled as one chapter of a report/book) always names the shared
    output, since "as part of" is meaningless without it; options
    ['include_output'] opts into naming it for an otherwise plain
    single-file/batch compile too.
    """
    summary = stamp_summary(options, texts, verbose)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if report_output is not None:
        return f"Compiled as part of `{report_output.name}` with {summary} -- {timestamp}"
    if options["include_output"]:
        return f"Compiled to `{output.name}` with {summary} -- {timestamp}"
    return f"Compiled with {summary} -- {timestamp}"


BUILD_NOTES_RE = re.compile(
    r"<!--[ \t]*=+[ \t]*\n"
    r"(?P<indent>[ \t]*)BUILD NOTES[ \t]*\n"
    r"(?P<body>.*?)"
    r"(?P=indent)=+[ \t]*-->",
    re.DOTALL,
)


def stamp_line_pattern(indent: str) -> re.Pattern:
    return re.compile(rf"^{re.escape(indent)}Compiled\b.*?\bpdfmd\s+v[0-9][^\r\n]*$", re.MULTILINE)


def history_heading_pattern(indent: str) -> re.Pattern:
    return re.compile(rf"^{re.escape(indent)}Compile History:[ \t]*\n", re.MULTILINE)


def update_build_notes(text: str, new_line: str, mode: str) -> tuple[str, str | None]:
    """Insert/replace pdfmd's own stamp line inside a document's BUILD NOTES
    comment, wherever that comment sits in the file (found by BUILD_NOTES_RE
    -- not assumed to be the file's last line: a report chapter's own
    comment can end up anywhere once concatenated with others for a book
    build, and even a lone document's notes might not literally be last).
    Everything else inside the comment -- hand-written notes before or
    after the line pdfmd owns -- is left untouched byte-for-byte. Creates a
    fresh comment at the true end of the file if none is found there yet.
    Returns (updated_text, warning) -- warning is a one-line string to
    surface to the caller (never raised/logged here) or None.

    "replace" mode overwrites the current stamp line (the one right under
    "BUILD NOTES") in place; if there is none yet, one is inserted there.
    It never touches a "Compile History:" trailer even if one already
    exists from an earlier history-mode run -- that history is simply
    frozen, not extended, while stamping runs in replace mode, which is
    worth a warning back to the caller since it's easy to not notice.

    "history" mode keeps exactly one live stamp line at the top (right
    under "BUILD NOTES", so the most recent compile is always the first
    thing read) and demotes whatever was previously there into a
    "Compile History:" list of "  - " bullets at the END of the comment,
    just before its closing "===...-->" -- newest-demoted-first, so the
    whole comment reads newest-to-oldest top to bottom. The heading is
    created there the first time a demotion has nowhere to go.
    """
    match = BUILD_NOTES_RE.search(text)
    if not match:
        indent = "     "
        block = f"<!-- {'=' * 60}\n{indent}BUILD NOTES\n\n{indent}{new_line}\n{indent}{'=' * 60} -->\n"
        return text.rstrip("\n") + "\n\n" + block, None

    indent = match.group("indent")
    body = match.group("body")
    stamp_re = stamp_line_pattern(indent)
    current = stamp_re.search(body)
    warning = None

    if mode == "replace":
        history_match = history_heading_pattern(indent).search(body)
        if history_match:
            bullet_count = len(re.findall(rf"^{re.escape(indent)}  - Compiled\b", body, re.MULTILINE))
            warning = (f"--stamp: 'Compile History' already holds {bullet_count} "
                      "entr" + ("y" if bullet_count == 1 else "ies") + " but --stamp-mode is "
                      "'replace' this run -- history stays frozen (not extended) while in "
                      "replace mode; switch back to --stamp-mode history to keep recording it")
        if current:
            new_body = body[:current.start()] + f"{indent}{new_line}" + body[current.end():]
        else:
            new_body = f"{indent}\n{indent}{new_line}\n\n{body}"
        return text[:match.start("body")] + new_body + text[match.end("body"):], warning

    # history mode
    if not current:
        new_body = f"{indent}\n{indent}{new_line}\n\n{body}"
        return text[:match.start("body")] + new_body + text[match.end("body"):], None

    demoted = current.group(0)[len(indent):]
    remainder = body[current.end():]
    if remainder.startswith("\n"):
        remainder = remainder[1:]
    blank_line = re.match(r"^[ \t]*\n", remainder)
    if blank_line:
        remainder = remainder[blank_line.end():]
    # body[:current.start()] is just the leading blank line the original
    # template put between "BUILD NOTES" and the current line -- dropped
    # rather than kept, since the new current line gets that same leading
    # blank fresh, further down; keeping both would double it up.
    body_without_current = remainder

    bullet = f"{indent}  - {demoted}\n"
    history_match = history_heading_pattern(indent).search(body_without_current)
    if history_match:
        insert_at = history_match.end()
        body_without_current = (body_without_current[:insert_at] + bullet
                                + body_without_current[insert_at:])
    else:
        trimmed = body_without_current.rstrip("\n")
        heading_block = f"{indent}Compile History:\n{bullet}"
        body_without_current = f"{trimmed}\n\n{heading_block}" if trimmed else heading_block

    new_body = f"{indent}\n{indent}{new_line}\n\n{body_without_current}"
    return text[:match.start("body")] + new_body + text[match.end("body"):], None


def apply_stamp(md_path: Path, new_line: str, mode: str, verbose: bool) -> None:
    text = md_path.read_text(encoding="utf-8-sig")
    updated, warning = update_build_notes(text, new_line, mode)
    md_path.write_text(updated, encoding="utf-8")
    if warning:
        print(f"WARN  {md_path}: {warning}", file=sys.stderr)
    if verbose:
        print(f"AUTO STAMP  {md_path}: {new_line}")


def gather_stamp_texts(md_path: Path, preamble_files: list[Path]) -> list[str]:
    """Raw LaTeX text stamp_summary checks for \\usepackage{...}: a
    document's discovered preambles plus its own header-includes block.
    """
    texts = [preamble.read_text(encoding="utf-8-sig") for preamble in preamble_files]
    texts.append(document_header_includes(md_path.read_text(encoding="utf-8-sig")) or "")
    return texts


def stamp_scope_matches(options: dict, report_output: Path | None) -> bool:
    """Whether options['scope'] allows stamping in this context -- shared by
    the pre-compile PDF-metadata path and the post-compile .md-stamp path,
    so both always agree on when to fire (see DEFAULT_STAMP_OPTIONS).
    """
    wanted_scope = "report" if report_output is not None else "standalone"
    return options["scope"] in ("always", wanted_scope)


def stamp_after_success(md_path: Path, metadata_files: list[Path], preamble_files: list[Path],
                        cli_overrides: dict, output: Path, verbose: bool,
                        report_output: Path | None = None) -> None:
    """Write/update md_path's BUILD NOTES stamp after a successful compile,
    if --stamp/pdfmd-options.stamp says to for this context.

    report_output being given means md_path is one chapter of a report/book
    compile (main()'s -r/--report path) rather than a standalone/batch
    compile (convert_one) -- options['scope'] decides which context(s)
    actually write a stamp (see DEFAULT_STAMP_OPTIONS/resolve_stamp_options):
    "always" (default), "report"-only, or "standalone"-only.
    """
    options = resolve_stamp_options(md_path, metadata_files, cli_overrides)
    if not stamp_scope_matches(options, report_output):
        return
    texts = gather_stamp_texts(md_path, preamble_files)
    # Independent of options["enabled"] below on purpose -- pdf_metadata is
    # its own always-on-by-default switch (DEFAULT_STAMP_OPTIONS), separate
    # from the .md-source BUILD NOTES stamp that "enabled" actually gates.
    stamp_pdf_metadata_posthoc(output, options, texts, verbose)
    if not options["enabled"]:
        return
    line = build_stamp_line(options, texts, output, report_output, verbose)
    apply_stamp(md_path, line, options["mode"], verbose)


# --backup / pdfmd-options.backup: after a successful compile, copy the
# source into a sibling backup directory. Taken AFTER stamp_after_success on
# purpose, so the snapshot is exactly the file on disk; recompiling an
# unedited document then matches the newest snapshot (see backup_unchanged)
# and writes nothing. Off by default. Added v3.8.0 (2026-09-24); snapshot
# name formats and recognition of hand-made backups added v3.9.0.
#
# Snapshot names come from `format:` -- a preset name from BACKUP_FORMATS
# or a custom template: {name} (report.md), {stem} (report), {ext} (.md),
# plus any strftime code (%Y%m%d-%H%M%S, ...). Every preset is a naming
# convention already in real use in the author's folders (2026-09-24 survey), so
# any folder can keep the style it already has.
BACKUP_FORMATS = {
    # report.md.bak.20260924091500 -- LR2/backup, nulabreport/_superseded
    "compact": "{name}.bak.%Y%m%d%H%M%S",
    # report.md.bak.20260924-091500 -- compact with a date/time separator
    "dashed": "{name}.bak.%Y%m%d-%H%M%S",
    # report_20260924-091500.md -- LR3/backups, LR4-5/backup, ir/webbook;
    # keeps the real extension, so a snapshot opens straight in its app
    "stem": "{stem}_%Y%m%d-%H%M%S{ext}",
    # report.md.20260924-091500.bak -- nulabreport/backups
    "suffix": "{name}.%Y%m%d-%H%M%S.bak",
    # report.md.09-24_09-15-00.bak -- LR4-5/prelab/backups (no year)
    "short": "{name}.%m-%d_%H-%M-%S.bak",
}
DEFAULT_BACKUP_OPTIONS = {
    "enabled": False,
    # Relative to the document's own directory (absolute also accepted).
    # Singular "backup" to match the per-report folders that already exist.
    "dir": "backup",
    # Newest N plain-timestamp snapshots of this one file kept; 0 keeps all.
    # Never counts or deletes tagged ones -- see backup_snapshots().
    "keep": 0,
    "format": "compact",
}
# strftime codes -> what they render as, for recognizing a format's own
# output again (dedupe/pruning). Anything unlisted matches loosely.
_STRFTIME_PATTERNS = {
    "Y": r"\d{4}", "y": r"\d{2}", "m": r"\d{2}", "d": r"\d{2}", "H": r"\d{2}",
    "I": r"\d{2}", "M": r"\d{2}", "S": r"\d{2}", "f": r"\d{6}", "j": r"\d{3}",
    "p": r"[AP]M", "%": "%",
}
# Collision counter a snapshot name gets when its second (or minute, for a
# coarse format) is already taken -- "-2", "-3", ...
_COUNTER = r"(?:-\d+)?"


def backup_template(value: str) -> str:
    """Resolve a `format:` value to a template, validating a custom one."""
    template = BACKUP_FORMATS.get(value, value)
    if "{name}" not in template and "{stem}" not in template:
        raise SystemExit(f"pdfmd-options.backup.format {value!r}: needs {{name}} or {{stem}} "
                         f"(or a preset: {', '.join(BACKUP_FORMATS)}), or every file in the "
                         "folder would share one set of snapshot names")
    if "%" not in template:
        raise SystemExit(f"pdfmd-options.backup.format {value!r}: needs at least one strftime "
                         "code (e.g. %Y%m%d-%H%M%S), or every snapshot gets the same name")
    try:
        template.format(name="x", stem="x", ext="x")
    except (KeyError, IndexError, ValueError) as error:
        raise SystemExit(f"pdfmd-options.backup.format {value!r}: only {{name}}, {{stem}} and "
                         f"{{ext}} are recognized placeholders ({error})")
    return template


def fill_backup_template(template: str, md_path: Path) -> str:
    """Substitute {name}/{stem}/{ext}, leaving strftime codes in place --
    plain replace() rather than str.format so a file name with a literal
    brace can't break it, and any % in the name doubled so strftime keeps
    it literal."""
    for key, value in (("{name}", md_path.name), ("{stem}", md_path.stem), ("{ext}", md_path.suffix)):
        template = template.replace(key, value.replace("%", "%%"))
    return template


def backup_name_regex(template: str, md_path: Path) -> re.Pattern:
    """A regex matching every name `template` can produce for md_path,
    including a collision counter before the extension-like tail."""
    literal = fill_backup_template(template, md_path)
    parts = re.split(r"(%.)", literal)
    body = "".join(_STRFTIME_PATTERNS.get(part[1], r".+?") if part.startswith("%") and len(part) == 2
                   else re.escape(part) for part in parts)
    # Counter goes where backup_target() puts it: before the source's own
    # extension, before a trailing .bak, or at the very end.
    for tail in (re.escape(md_path.suffix), re.escape(".bak")):
        if tail and body.endswith(tail):
            return re.compile(f"^{body[:-len(tail)]}{_COUNTER}{tail}$")
    return re.compile(f"^{body}{_COUNTER}$")


def backup_target(backup_dir: Path, template: str, md_path: Path) -> Path:
    """First free snapshot path for `template` right now."""
    rendered = datetime.now().strftime(fill_backup_template(template, md_path))
    target = backup_dir / rendered
    counter = 2
    while target.exists():
        head, tail = rendered, ""
        for candidate in (md_path.suffix, ".bak"):
            if candidate and rendered.endswith(candidate):
                head, tail = rendered[:-len(candidate)], candidate
                break
        target = backup_dir / f"{head}-{counter}{tail}"
        counter += 1
    return target


# Plain-timestamp names any earlier convention (or any preset) produces for
# one file -- the ones `keep:` may prune. Anything else that still clearly
# belongs to the file (report.md.pre-irstack.20260923-211848.bak,
# chemicals.tex.before-LR1-2, report.md.pre-v1.17.0.bak, ...) is a
# deliberately named milestone: compared against for dedupe, never pruned.
def _plain_backup_patterns(md_path: Path) -> list[re.Pattern]:
    name, stem, ext = map(re.escape, (md_path.name, md_path.stem, md_path.suffix))
    return [re.compile(pattern) for pattern in (
        rf"^{name}\.bak\.\d{{8}}-?\d{{6}}{_COUNTER}$",                  # compact / dashed
        rf"^{stem}_\d{{8}}-\d{{6}}{_COUNTER}{ext}$",                     # stem
        rf"^{name}\.\d{{8}}-\d{{6}}{_COUNTER}\.bak$",                    # suffix
        rf"^{name}\.\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}-\d{{2}}{_COUNTER}\.bak$",  # short
        rf"^{name}\.bak-\d{{8}}[a-z]?$",                                 # pdfmd's own bak-YYYYMMDD[letter]
        rf"^{name}\.\d{{2}}-\d{{2}}\.bak$",                              # prelab5.pdf.18-53.bak
    )]


def backup_sort_key(path: Path) -> tuple:
    """When a snapshot was taken: a full date+time in its name wins
    (20260924-091500 / 20260924091500 / 09-24_09-15-00 with the year from
    mtime), else its mtime. Mixed conventions in one folder still order
    correctly this way. Second element breaks same-second ties."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    # Same-second snapshots (a -2 collision counter) tie on the name; the
    # later one is always a later edit of the source (an unchanged one is
    # never written), so mtime -- copy2 keeps the source's -- breaks it.
    tiebreak = mtime
    full = re.search(r"(?<!\d)(\d{8})-?(\d{6})(?!\d)", path.name)
    if full:
        try:
            return (datetime.strptime(full.group(1) + full.group(2), "%Y%m%d%H%M%S").timestamp(), tiebreak)
        except ValueError:
            pass
    short = re.search(r"(?<!\d)(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})(?!\d)", path.name)
    if short:
        try:
            year = datetime.fromtimestamp(mtime).year
            return (datetime(year, *map(int, short.groups())).timestamp(), tiebreak)
        except ValueError:
            pass
    return (mtime, tiebreak)


def backup_snapshots(backup_dir: Path, md_path: Path, template: str) -> tuple[list[Path], list[Path]]:
    """Every existing snapshot of md_path in backup_dir, in any recognized
    naming form, oldest first -- and the subset `keep:` may prune (plain
    timestamps only; see _plain_backup_patterns)."""
    own = backup_name_regex(template, md_path)
    plain = _plain_backup_patterns(md_path)
    stem_form = re.compile(rf"^{re.escape(md_path.stem)}_\d{{8}}-\d{{6}}.*{re.escape(md_path.suffix)}$")
    every, prunable = [], []
    for path in backup_dir.iterdir():
        if not path.is_file():
            continue
        name = path.name
        is_plain = bool(own.match(name)) or any(pattern.match(name) for pattern in plain)
        if is_plain or name.startswith(md_path.name + ".") or stem_form.match(name):
            every.append(path)
            if is_plain:
                prunable.append(path)
    every.sort(key=backup_sort_key)
    prunable.sort(key=backup_sort_key)
    return every, prunable


def normalize_backup_value(value) -> dict:
    """Normalize a pdfmd-options.backup value: a bare bool, a directory name
    (shorthand for enabling it with that directory), or a full dict of
    {enabled, dir, keep, format}. A dict with no explicit ``enabled`` counts
    as on, same as normalize_stamp_value's rule.
    """
    options = dict(DEFAULT_BACKUP_OPTIONS)
    if isinstance(value, bool):
        options["enabled"] = value
    elif isinstance(value, str):
        options["enabled"] = True
        options["dir"] = value
    elif isinstance(value, dict):
        options["enabled"] = bool(value.get("enabled", True))
        if value.get("dir"):
            options["dir"] = str(value["dir"])
        if value.get("format"):
            options["format"] = str(value["format"])
        if "keep" in value:
            try:
                options["keep"] = max(0, int(value["keep"] or 0))
            except (TypeError, ValueError):
                raise SystemExit(f"pdfmd-options.backup.keep must be a whole number, got {value['keep']!r}")
    return options


def resolve_backup_options(md_path: Path, metadata_files: list[Path], cli_enabled: bool | None,
                           cli_format: str | None = None) -> dict:
    """Document front matter first, then each metadata file in order (same
    cascade as frontmatter_stamp), then --backup/--no-backup and
    --backup-format on top.
    """
    options = None
    own = frontmatter_pdfmd_options(md_path)
    if "backup" in own:
        options = normalize_backup_value(own["backup"])
    else:
        for metadata_file in metadata_files:
            nested = metadata_file_yaml(metadata_file).get("pdfmd-options")
            if isinstance(nested, dict) and "backup" in nested:
                options = normalize_backup_value(nested["backup"])
                break
    options = options or dict(DEFAULT_BACKUP_OPTIONS)
    if cli_enabled is not None:
        options["enabled"] = cli_enabled
    if cli_format:
        options["format"] = cli_format
    return options


# Lines a --stamp writes (the live "Compiled ... pdfmd vX" line, its demoted
# "- Compiled ..." history bullets, and the "Compile History:" heading),
# ignored when deciding whether a source changed since its last snapshot --
# otherwise stamp mode: history, which rewrites a timestamp on every
# compile, would make every compile look like an edit. Found testing
# v3.8.0 against a real LR2 report.
BACKUP_IGNORED_LINE_RE = re.compile(
    r"^[ \t]*(?:(?:- )?Compiled\b.*?\bpdfmd\s+v[0-9][^\r\n]*|Compile History:[ \t]*)\r?\n?",
    re.MULTILINE,
)


def backup_unchanged(previous: Path, current: Path) -> bool:
    """Whether current matches the snapshot previous, apart from --stamp's
    own lines (BACKUP_IGNORED_LINE_RE). Byte comparison for anything that
    isn't UTF-8 text (an office document).
    """
    try:
        old_text = previous.read_text(encoding="utf-8")
        new_text = current.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return filecmp.cmp(previous, current, shallow=False)
    return BACKUP_IGNORED_LINE_RE.sub("", old_text) == BACKUP_IGNORED_LINE_RE.sub("", new_text)


def backup_after_success(md_path: Path, metadata_files: list[Path], cli_enabled: bool | None,
                         verbose: bool, cli_format: str | None = None) -> None:
    """Snapshot md_path into its backup directory if --backup/
    pdfmd-options.backup says to -- skipped when the newest existing
    snapshot, in any recognized naming form (backup_snapshots), is already
    identical ignoring --stamp's own lines; then pruned to ``keep`` if set.
    Best-effort: an OSError warns rather than failing a compile that
    already succeeded.
    """
    options = resolve_backup_options(md_path, metadata_files, cli_enabled, cli_format)
    if not options["enabled"]:
        return
    template = backup_template(options["format"])
    backup_dir = Path(os.path.expanduser(options["dir"]))
    if not backup_dir.is_absolute():
        backup_dir = md_path.parent / backup_dir
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        every, prunable = backup_snapshots(backup_dir, md_path, template)
        if every and backup_unchanged(every[-1], md_path):
            if verbose:
                print(f"AUTO BACKUP  {display_path(md_path)}: unchanged since "
                      f"{display_path(every[-1])}; skipped")
            return
        target = backup_target(backup_dir, template, md_path)
        shutil.copy2(md_path, target)
        print(f"BACKUP  {display_path(target)}")
        prunable.append(target)
        if options["keep"] and len(prunable) > options["keep"]:
            for old in prunable[:-options["keep"]]:
                old.unlink()
                if verbose:
                    print(f"AUTO BACKUP  pruned {display_path(old)} (keep: {options['keep']})")
    except OSError as error:
        print(f"WARN  {display_path(md_path)}: backup failed: {error}", file=sys.stderr)


# PDF Info-dictionary key names pdfmd writes when pdf_metadata is on. Two
# separate keys, not one combined "Compiled with ... -- TIMESTAMP" line like
# the .md stamp's: LuaTeX/XeTeX apply their usual typographic ligatures
# (-- becomes an en dash) to hypersetup's pdfinfo strings same as any other
# typeset text, so a literal "--" separator doesn't survive intact -- kept
# out entirely here rather than fought with escaping.
PDF_INFO_VERSIONS_KEY = "PdfmdVersions"
PDF_INFO_BUILD_DATE_KEY = "PdfmdBuildDate"


def pdf_metadata_snippet(options: dict, texts: list[str], verbose: bool) -> str | None:
    """SUPERSEDED, v3.7.0 (2026-09-21) -- now always returns None.

    Used to return \\AtBeginDocument{...\\hypersetup{pdfinfo={...}}} LaTeX for
    --include-in-header, baking the PdfmdVersions/PdfmdBuildDate keys into
    the PDF Info dictionary from inside the LaTeX compile itself. Replaced
    by stamp_pdf_metadata_posthoc() below, which does the identical thing
    with pypdf AFTER a successful compile instead: confirmed directly (a
    real nulabreport `prelab` document, `\\usepackage[prelab]{nulabreport}`
    loaded via a --metadata-file's own header-includes rather than a
    preamble.tex) that pandoc's own template gives --include-in-header
    content and a metadata file's header-includes THE SAME template slot,
    and --include-in-header simply WINS -- the metadata file's
    header-includes vanished from the preamble entirely the moment this
    function's old --include-in-header snippet was also present, silently
    undoing an entire package load with no error at that point, surfacing
    only later as "Undefined control sequence" the first time the document
    used one of that package's macros. A post-hoc PDF edit sidesteps the
    whole class of --include-in-header/header-includes interaction (this
    one and any similar one not yet found) and, as a real improvement over
    the LaTeX-side version, now also works on every engine, not only
    LATEX_ENGINES (a non-LaTeX target such as weasyprint/typst previously
    had no equivalent mechanism this reached at all -- see this function's
    pre-v3.7.0 docstring history if needed). Left defined (rather than
    deleted) and still called from every site it always was, all of which
    already treat a None return as "no --include-in-header entry needed" --
    the safest way to retire it without touching pdfmd's own multi-engine
    fallback/native-bibliography/report/batch call sites, several of which
    thread pdf_meta_snippet_text through as a plain parameter.
    """
    return None


def stamp_pdf_metadata_posthoc(pdf_path: Path, options: dict, texts: list[str], verbose: bool) -> None:
    """Write PdfmdVersions/PdfmdBuildDate into pdf_path's own PDF Info
    dictionary after a successful compile -- see pdf_metadata_snippet's
    docstring for why this replaced an in-LaTeX \\hypersetup injection.
    Silently does nothing if options['pdf_metadata'] is off, pdf_path isn't
    a real PDF (e.g. a --to other than pdf), or pypdf isn't installed (a
    soft dependency, same convention as this module's own `yaml` import --
    a WARN either way, since unlike PyYAML's front-matter sugar this is an
    always-on-by-default feature quietly not doing its job).
    """
    if not options.get("pdf_metadata"):
        return
    if pypdf is None:
        if verbose:
            print("WARN  --stamp: pdf_metadata is on but pypdf is not installed "
                  "(pip install pypdf) -- skipping the PDF Info-dictionary stamp",
                  file=sys.stderr)
        return
    if pdf_path.suffix.lower() != ".pdf" or not pdf_path.is_file():
        return
    summary = stamp_summary(options, texts, verbose)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # pypdf's own "Annotation sizes differ" message fires on essentially
        # every hyperref-linked document (link-annotation bookkeeping quirk
        # of read-then-rewrite) and is not this function's business to
        # surface -- it changes nothing about whether the metadata write
        # below succeeds. pypdf logs this (and similar notices) through the
        # stdlib `logging` module, not `warnings.warn` -- confirmed directly
        # (grepped pypdf's own source) -- so both need silencing.
        pypdf_logger = logging.getLogger("pypdf")
        previous_level = pypdf_logger.level
        pypdf_logger.setLevel(logging.ERROR)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                reader = pypdf.PdfReader(pdf_path)
                existing = dict(reader.metadata) if reader.metadata else {}
                writer = pypdf.PdfWriter()
                writer.append(reader)
                writer.add_metadata({
                    **existing,
                    f"/{PDF_INFO_VERSIONS_KEY}": summary,
                    f"/{PDF_INFO_BUILD_DATE_KEY}": timestamp,
                })
                with NamedTemporaryFile("wb", suffix=".pdf", delete=False,
                                        dir=pdf_path.parent) as temporary:
                    writer.write(temporary)
                    temporary_path = Path(temporary.name)
        finally:
            pypdf_logger.setLevel(previous_level)
        temporary_path.replace(pdf_path)
    except Exception as error:  # noqa: BLE001 -- best-effort, like package_version()
        print(f"WARN  --stamp: could not write the PDF Info-dictionary stamp "
              f"into {pdf_path} ({error}) -- the compile itself still succeeded",
              file=sys.stderr)


@contextmanager
def pdf_metadata_header_file(snippet: str | None) -> Iterator[Path | None]:
    """Materialize pdf_metadata_snippet's LaTeX to a temp file for
    --include-in-header -- same pattern as table_width_filter's fixed,
    non-document-specific content, so a plain system-tempdir file is fine.
    """
    if not snippet:
        yield None
        return
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".tex",
                            prefix="pdfmd-pdfmeta-", delete=False) as temporary:
        temporary.write(snippet)
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


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
        accessory = directory / ACCESSORY_DIRNAME
        candidates.append(Path.cwd() / path)
        candidates.append(directory / path)
        candidates.append(accessory / path)
        if not path.suffix:
            candidates.extend((Path.cwd() / path.with_suffix(".yaml"),
                               directory / path.with_suffix(".yaml"),
                               accessory / path.with_suffix(".yaml")))
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
    search_dirs = accessory_directories(directory)
    if requested is not None:
        if requested == ["all"]:
            candidates = [item for folder in search_dirs
                          for item in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml"))
                          if item.name.lower() != "defaults.yaml" and yaml_autoinclude(item)]
            return order_metadata(candidates)
        return order_metadata([resolve_yaml(directory, value) for value in requested])
    candidates = [item for folder in search_dirs
                  for item in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml"))
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
    if sys.platform == "win32":
        try:
            os.startfile(path)  # Windows' own "open with default app"
        except OSError as error:
            print(f"WARN  --open: could not open {path}: {error}", file=sys.stderr)
        return
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
    print("CMD  " + " ".join(shlex.quote(display_path(Path(part))) for part in cmd)
          + f"  (cwd={display_path(cwd)})", file=sys.stderr)


def engine_failure_reason(stderr: str) -> str | None:
    """Pull the single most useful line out of a failed engine's stderr.

    Added 2026-09-17: before this, a failed engine only ever produced a bare
    "WARN ... {engine} failed; trying {next}..." with no hint why -- finding
    the actual cause meant rerunning by hand with --engine {engine} --verbose
    to see the raw LaTeX log, which is real friction for a mistake that's
    often one glance at the log away from obvious (an undefined environment,
    a missing package, a stray unescaped character). A LaTeX fatal error
    always starts its own line with '!' (e.g. '! LaTeX Error: ...'); Pandoc's
    own errors are usually 'Error producing PDF.' or 'pandoc: ...'. Preferring
    those over the raw tail keeps the one-line summary meaningful instead of
    a trailing context line like 'l.612 ...' or a blank line. Returns None
    for empty/whitespace-only stderr (nothing useful to show).
    """
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("!"):
            return line
    for line in lines:
        if line.startswith(("Error", "pandoc:", "pandoc.exe:")):
            return line
    return lines[-1] if lines else None


def report_engine_failure(label: str, engine: str, result: subprocess.CompletedProcess,
                          remaining: list[str], debug: bool) -> None:
    """Print why one PDF-engine attempt failed -- always, not just under --verbose.

    Added 2026-09-17 alongside engine_failure_reason() (see its docstring):
    every engine failure now gets at least a one-line reason for free.
    --debug goes further and dumps the engine's full captured stderr right
    here, inline, for when that one-line reason is too compressed to
    actually diagnose from (several stacked LaTeX errors, or a Pandoc-level
    error with no leading '!'/'Error' line at all) -- the previous way to
    see this was rerunning by hand with --engine <name> --verbose, which
    means already suspecting which engine to force before you've seen why
    any of them failed.
    """
    reason = engine_failure_reason(result.stderr)
    hint = f" ({reason})" if reason else ""
    if remaining:
        print(f"WARN  {label}: {engine} failed{hint}; trying {remaining[0]}...", file=sys.stderr)
    else:
        print(f"WARN  {label}: {engine} failed{hint}; no more engines to try. "
              f"Rerun with --engine {engine} --verbose (or --debug) for the full log.",
              file=sys.stderr)
    if debug and result.stderr.strip():
        print(f"----- {label}: {engine} stderr (--debug) -----", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        print("-" * 40, file=sys.stderr)


# Direct .tex compilation (v3.1.0): a real .tex input -- already a complete,
# independently compilable document with its own \documentclass/preamble --
# used to be handed to Pandoc anyway, which reads it with Pandoc's LaTeX
# reader and regenerates it through Pandoc's LaTeX writer before an engine
# ever sees it. That round-trip is lossy for exactly the raw LaTeX a .tex
# input is likely to contain on purpose (chemfig, tikz, custom macros) --
# see CHANGELOG-pdfmd.md v3.1.0. compile_tex_direct() instead runs a LaTeX
# engine straight on the file, handles the rerun-for-cross-references and
# bibtex/biber passes by hand (mirroring what latexmk already does
# internally for the two engines -- latexmk/tectonic -- that manage this
# themselves), and cleans up after itself the way tectonic always has:
# every engine writes into a scratch -output-directory, and only the
# finished PDF is copied back out, so the source directory is never left
# holding .aux/.log/.out/etc. --keep-aux (KEEP_AUX below) turns this off
# and restores the old in-place-with-leftovers behavior, for when a failed
# or suspicious compile needs its .log inspected by hand.
#
# Not attempted for "context": ConTeXt's CLI and markup are unrelated to
# the other five LATEX_ENGINES members, and a hand-written raw .tex file
# targeting it is not a realistic case this needs to cover.
MAX_TEX_DIRECT_PASSES = 5
TEX_RERUN_TRIGGERS = ("Rerun to get", "Please rerun LaTeX", "Rerun LaTeX")
# texmf.cnf's own max_print_line default -- see tex_log_dewrap()'s docstring.
TEX_LOG_WRAP_WIDTH = 79


def tex_wants_rerun(log_text: str) -> bool:
    """Whether a LaTeX engine's own .log is asking for another pass.

    Covers the standard hyperref/natbib/label-tracking messages
    (TEX_RERUN_TRIGGERS) -- the same signal latexmk itself watches for.
    """
    return any(trigger in log_text for trigger in TEX_RERUN_TRIGGERS)


def tex_log_dewrap(text: str, width: int = TEX_LOG_WRAP_WIDTH) -> str:
    """Undo a LaTeX engine's own hard line-wrap in its .log, mid-word,
    at ~max_print_line columns -- confirmed on this machine (kpsewhich
    -var-value=max_print_line) at 79, observed wrapping at 80 in
    practice. Any physical line at or past ``width`` is assumed
    continued verbatim (no space added) on the next; a real short
    line ends a logical line. Needed before any pattern match against
    the log: without it, a single sentence like "Fatal error occurred,
    no output PDF file produced!" is split across two physical lines
    with the break landing mid-word, and naive last-line/regex
    matching returns only the truncated tail (caught the hard way, by
    reading an actual failed compile's captured reason rather than
    trusting a clean synthetic one -- see CHANGELOG-pdfmd.md v3.1.0).
    """
    lines = text.split("\n")
    joined: list[str] = []
    buffer = ""
    for line in lines:
        buffer += line
        if len(line) >= width:
            continue
        joined.append(buffer)
        buffer = ""
    if buffer:
        joined.append(buffer)
    return "\n".join(joined)


def tex_log_failure_reason(log_text: str) -> str | None:
    """Pull the single most useful line out of a failed direct-.tex compile.

    Dewraps first (see tex_log_dewrap), then prefers a classic ``! ...``
    LaTeX error line same as engine_failure_reason(); falls back to a
    ``-file-line-error``-style ``path:line: message`` line (used here
    since it names the offending source line directly), skipping the
    generic ``... Fatal error occurred, no output PDF file produced!``
    trailer every halted run ends with, which names no actual cause.
    """
    lines = [line.strip() for line in tex_log_dewrap(log_text).splitlines() if line.strip()]
    for line in lines:
        if line.startswith("!"):
            return line
    for line in lines:
        match = re.match(r".+:\d+:\s+(.+)", line)
        if match and "Fatal error occurred" not in line:
            return match.group(1)
    return lines[-1] if lines else None


def tex_bibliography_tool(text: str) -> str | None:
    """Detect which bibliography processor a raw .tex document needs, if any.

    biblatex (``\\usepackage{biblatex}``/``\\addbibresource``) is processed
    by biber; the older bibtex/natbib style (bare ``\\bibliography{...}``)
    by bibtex. Returns None for a document with no bibliography at all.
    """
    if re.search(r"\\addbibresource\{|\\usepackage(?:\[[^\]]*\])?\{biblatex\}", text):
        return "biber"
    if re.search(r"\\bibliography\{", text):
        return "bibtex"
    return None


def latex_engine_command(engine: str, tex_path: Path, output_dir: Path) -> list[str] | None:
    """Build one direct-compile pass's command line for ``engine``.

    lualatex/xelatex/pdflatex share an identical CLI shape and are run
    through compile_tex_direct's own manual rerun/bibliography loop.
    latexmk and tectonic already manage multi-pass compilation and
    bibtex/biber internally, so each gets a single wrapped call instead.
    Returns None for anything else (namely "context" -- see the module-
    level comment above compile_tex_direct).
    """
    if engine in {"lualatex", "xelatex", "pdflatex"}:
        return [engine, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
                f"-output-directory={output_dir}", str(tex_path)]
    if engine == "latexmk":
        return ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                f"-output-directory={output_dir}", str(tex_path)]
    if engine == "tectonic":
        return ["tectonic", "-o", str(output_dir), str(tex_path)]
    return None


def run_tex_engine(engine: str, tex_path: Path, output_dir: Path,
                    verbose: bool) -> tuple[bool, str]:
    """Run ``engine`` on ``tex_path`` to completion, output landing in
    ``output_dir``. Returns (success, one-line failure reason -- empty on
    success). Always run with cwd=tex_path.parent, so a raw \\input/
    \\includegraphics/\\bibliography relative path beside the source keeps
    resolving; only *output* is redirected via -output-directory/-o.
    """
    log_path = output_dir / f"{tex_path.stem}.log"

    def log_text() -> str:
        return log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""

    def run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
        log_cmd(cmd, cwd, verbose)
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env)

    cmd = latex_engine_command(engine, tex_path, output_dir)
    if cmd is None:
        return False, f"{engine} is not supported for direct .tex compilation"

    if engine in ("latexmk", "tectonic"):
        # Both already handle reruns and bibtex/biber internally.
        result = run(cmd, tex_path.parent)
        if result.returncode != 0 or not (output_dir / f"{tex_path.stem}.pdf").exists():
            return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""
        return True, ""

    result = run(cmd, tex_path.parent)
    if result.returncode != 0:
        return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""

    bib_tool = tex_bibliography_tool(tex_path.read_text(encoding="utf-8-sig"))
    if bib_tool:
        # Run WITH cwd=output_dir (the .aux/.bcf's own directory), not
        # tex_path.parent: bibtex (and, defensively, biber too) is
        # subject to TeX's own "openout_any" file-writing security
        # policy, which -- at MacTeX's paranoid default -- refuses to
        # write a .bbl/.blg anywhere outside the current directory tree.
        # Pointing bibtex at a scratch -output-directory while running
        # it from the source directory silently tripped exactly that
        # check (caught by actually inspecting the rendered PDF's
        # citation, not just the exit code -- bibtex still printed a
        # "Not writing to ..." warning and returned nonzero, but the
        # compile otherwise looked like it had succeeded). BIBINPUTS
        # points bibtex back at the source directory to find the .bib
        # file, since it has no --input-directory flag of its own.
        bib_env = os.environ.copy()
        bib_env["BIBINPUTS"] = f"{tex_path.parent}{os.pathsep}{bib_env.get('BIBINPUTS', '')}"
        bib_cmd = (["biber", f"--input-directory={tex_path.parent}", tex_path.stem] if bib_tool == "biber"
                   else ["bibtex", tex_path.stem])
        bib_result = run(bib_cmd, output_dir, env=bib_env)
        if bib_result.returncode != 0:
            print(f"WARN  {tex_path}: {bib_tool} reported errors; continuing"
                  + (f" ({bib_result.stderr.strip().splitlines()[-1]})" if bib_result.stderr.strip() else ""),
                  file=sys.stderr)
        result = run(cmd, tex_path.parent)
        if result.returncode != 0:
            return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""

    passes = 1
    while tex_wants_rerun(log_text()) and passes < MAX_TEX_DIRECT_PASSES:
        result = run(cmd, tex_path.parent)
        passes += 1
        if result.returncode != 0:
            return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""
    if verbose:
        print(f"AUTO TEXDIRECT  {tex_path}: {engine}, {passes} pass(es)"
              + (f" + {bib_tool}" if bib_tool else ""))
    return True, ""


def compile_tex_direct(tex_path: Path, output: Path, engines: list[str],
                       keep_aux: bool, verbose: bool, debug: bool) -> tuple[bool, str]:
    """Compile a standalone .tex document directly, without Pandoc.

    See the module-level comment above for why, and this file's docstring
    ("Input formats") for the user-facing summary. ``engines`` is the
    already-resolved fallback chain (from select_engines/resolve_engines);
    only its LATEX_ENGINES members other than "context" are usable here --
    a chain left with none (e.g. a document/metadata pdf-engine restricted
    to the "html" family) is reported as a failure rather than silently
    falling back to the old, lossier Pandoc round-trip.
    """
    tex_engines = [engine for engine in engines if engine in LATEX_ENGINES and engine != "context"]
    if not tex_engines:
        return False, (f"{tex_path}: no LaTeX engine available for direct .tex compilation "
                       "(need one of lualatex/xelatex/pdflatex/latexmk/tectonic)")

    failed_families: set[str] = set()
    last_reason = ""
    for engine_index, engine in enumerate(tex_engines):
        family = ENGINE_FAMILY.get(engine, engine)
        if family in failed_families:
            print(f"SKIP  {tex_path}: {engine} shares the {family} engine with an earlier "
                  f"failure; skipping", file=sys.stderr)
            continue
        scratch = None if keep_aux else Path(mkdtemp(prefix="pdfmd-tex-"))
        output_dir = tex_path.parent if scratch is None else scratch
        try:
            ok, reason = run_tex_engine(engine, tex_path, output_dir, verbose)
            if ok:
                produced = output_dir / f"{tex_path.stem}.pdf"
                output.parent.mkdir(parents=True, exist_ok=True)
                # --keep-aux compiles straight into tex_path.parent, so
                # ``produced`` and ``output`` are the same file whenever
                # no -o/--out redirected the output elsewhere -- shutil
                # refuses to "copy" a file onto itself.
                if produced.resolve() != output.resolve():
                    shutil.copy2(produced, output)
                if verbose:
                    where = "in place (--keep-aux)" if keep_aux else "in a scratch directory, then discarded"
                    print(f"AUTO TEXDIRECT  {tex_path}: compiled with {engine} {where}")
                return True, ""
            last_reason = reason
        finally:
            if scratch is not None:
                shutil.rmtree(scratch, ignore_errors=True)
        failed_families.add(family)
        remaining = [e for e in tex_engines[engine_index + 1:] if ENGINE_FAMILY.get(e, e) not in failed_families]
        fake_result = subprocess.CompletedProcess(args=[engine], returncode=1, stdout="", stderr=last_reason)
        report_engine_failure(str(tex_path), engine, fake_result, remaining, debug)
    return False, last_reason


# Direct office-document conversion, and the "soffice" PDF-engine fallback
# (v-next / Phase 2 of the round documented in v3.1.0's own changelog
# entry): both go through run_soffice_convert(), which shells out to
# headless LibreOffice with a fresh --env:UserInstallation profile per
# call -- concurrent/rapid-fire soffice invocations (batch mode's -j)
# otherwise collide on the shared default profile's lock file and fail
# with "another instance is already running."
#
# .docx/.pptx/.xlsx/.odt/etc. INPUT (convert_office_direct) skips Pandoc
# entirely, the same reasoning as compile_tex_direct for raw .tex: Pandoc
# can read .docx/.odt but round-trips them through its own AST first,
# losing layout Pandoc's writer doesn't reproduce; it can't read .pptx/
# .xlsx/.ppt/.xls at all, so those never reached a PDF through pdfmd
# before this. See module docstring ("Input formats") for the "officedirect"
# --no-auto KIND that opts a .docx/.odt back into the old Pandoc route.
#
# "soffice" as a PDF-engine CANDIDATE (convert_via_soffice_bridge) is a
# different thing: a Markdown (or other Pandoc-readable) SOURCE, tried as
# the very last resort in an unrestricted fallback chain, after every
# tex/typst/html engine has failed or is missing. Pandoc has no native
# "write ODT, then shell out to LibreOffice" --pdf-engine, so this is
# special-cased in convert_one's own fallback loop rather than built as a
# real --pdf-engine=soffice command the way every other candidate is.
OFFICE_INPUT_EXTENSIONS = frozenset({
    ".docx", ".doc", ".odt", ".ott", ".rtf",
    ".pptx", ".ppt", ".odp",
    ".xlsx", ".xls", ".ods",
})


def run_soffice_convert(input_path: Path, output: Path, verbose: bool) -> tuple[bool, str]:
    """Convert one file to PDF via headless LibreOffice, into ``output``.

    Runs entirely in a scratch directory (both the conversion's own
    output and its throwaway --env:UserInstallation profile), deleted
    afterward regardless of outcome -- soffice leaves no equivalent of a
    LaTeX engine's .aux/.log, but the scratch profile itself would
    otherwise accumulate under /tmp across every call.
    """
    binary = resolve_soffice()
    if binary is None:
        return False, "soffice/LibreOffice not found (checked PATH, 'libreoffice', and the standard macOS app bundle)"
    scratch = Path(mkdtemp(prefix="pdfmd-soffice-"))
    try:
        profile_dir = scratch / "profile"
        cmd = [binary, "--headless", "--norestore",
              f"-env:UserInstallation=file://{profile_dir}",
              "--convert-to", "pdf", "--outdir", str(scratch), str(input_path)]
        log_cmd(cmd, input_path.parent, verbose)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=input_path.parent)
        produced = scratch / f"{input_path.stem}.pdf"
        if result.returncode != 0 or not produced.exists():
            reason = result.stderr.strip() or result.stdout.strip() or "soffice failed to produce a PDF"
            return False, reason.splitlines()[-1]
        output.parent.mkdir(parents=True, exist_ok=True)
        if produced.resolve() != output.resolve():
            shutil.copy2(produced, output)
        return True, ""
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def convert_office_direct(input_path: Path, output: Path, verbose: bool, debug: bool) -> tuple[bool, str]:
    """Convert an office document straight to PDF -- no Pandoc involved."""
    ok, reason = run_soffice_convert(input_path, output, verbose)
    if ok:
        if verbose:
            print(f"AUTO OFFICEDIRECT  {input_path}: converted with soffice directly (no Pandoc)")
    else:
        fake_result = subprocess.CompletedProcess(args=["soffice"], returncode=1, stdout="", stderr=reason)
        report_engine_failure(str(input_path), "soffice", fake_result, [], debug)
    return ok, reason


def convert_via_soffice_bridge(md_path: Path, output: Path, effective_from: str | None,
                               metadata_files: list[Path], variables: list[str],
                               pandoc_options: list[str], lua_filters: list[Path],
                               csv_filter: Path, no_auto: list[str] | None,
                               verbose: bool) -> tuple[bool, str]:
    """The "soffice" PDF-engine fallback: Pandoc -> .odt -> headless
    LibreOffice -> PDF. Deliberately skips every LaTeX-only concern
    convert_one's own per-engine run() closure applies for a real engine
    (geometry/mainfont/monofont/preamble/table-width filter) -- none of
    it means anything for an ODT target. Citeproc and a document's own
    auto-discovered Lua filters still apply, same as every other engine.
    """
    scratch = Path(mkdtemp(prefix="pdfmd-soffice-src-"))
    try:
        odt = scratch / f"{md_path.stem}.odt"
        cmd = ["pandoc", str(md_path), "-o", str(odt), "-t", "odt"]
        if effective_from:
            cmd += ["-f", effective_from]
        for metadata in metadata_files:
            cmd += ["--metadata-file", str(metadata)]
        pandoc_cwd = metadata_files[0].parent if metadata_files else md_path.parent
        cmd += resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
        for variable in variables:
            cmd += ["-V", variable]
        cmd += crossref_filter_args(md_path, pandoc_options, no_auto, str(md_path))
        cmd += csv_table_filter_args(md_path, no_auto, csv_filter)
        if contains_citations(md_path) and "--citeproc" not in pandoc_options and not CITEPROC_DISABLED:
            cmd.append("--citeproc")
        # pandoc_options after --citeproc: any --lua-filter/--filter a caller
        # passes through needs resolved citations already in the AST, same
        # invariant as the auto-discovered lua_filters below (see run()'s
        # matching comment in convert_one).
        cmd += pandoc_options
        for lua_filter in lua_filters:
            cmd += ["--lua-filter", str(lua_filter)]
        log_cmd(cmd, pandoc_cwd, verbose)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)
        if result.returncode != 0 or not odt.exists():
            return False, result.stderr.strip() or "pandoc failed to produce an intermediate .odt"
        return run_soffice_convert(odt, output, verbose)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def convert_via_native_bibliography(md_path: Path, output: Path, effective_from: str | None,
                                    metadata_files: list[Path], variables: list[str],
                                    pandoc_options: list[str], lua_filters: list[Path],
                                    preamble_files: list[Path], title_source: Path,
                                    pdf_meta_snippet_text: str | None, citation_engine: str,
                                    presentation: bool, slide_level: int | None, shift_heading: bool,
                                    font: str, document_font: bool, mainfont_auto: bool,
                                    geometry_needed: bool, monofont_needed: bool,
                                    tablewidth_auto: bool, width_filter: Path, csv_filter: Path,
                                    no_auto: list[str] | None, engines: list[str], keep_aux: bool,
                                    verbose: bool, debug: bool) -> tuple[bool, str]:
    """Route a PDF compile's bibliography through Pandoc's own --natbib/
    --biblatex instead of --citeproc, for pdfmd-options.citation-engine.

    Not as simple as adding --natbib/--biblatex next to the usual
    --pdf-engine=<engine> pandoc invocation: confirmed empirically (a real
    document, `pandoc ... --pdf-engine=lualatex --natbib`) that Pandoc's
    own PDF-making pipeline never runs bibtex/biber at all when it invokes
    a LaTeX engine directly this way -- citations come out undefined
    ("Citing ? here.") regardless of engine, EXCEPT --pdf-engine=latexmk,
    since latexmk is the one engine in the chain that manages bibtex/biber
    itself. Rather than restrict this feature to latexmk only, this
    generates a complete standalone .tex via Pandoc first (mirroring
    convert_one's own TEX_STANDALONE_FORMATS branch, just always writing
    to a scratch file instead of the real --to latex output) and hands it
    to compile_tex_direct() -- which already runs exactly the
    rerun-until-stable + automatic bibtex/biber loop this needs, for
    ANY of lualatex/xelatex/pdflatex/latexmk/tectonic, not just latexmk.
    No missing-glyph mainfont retry here, for the same reason
    TEX_STANDALONE_FORMATS doesn't have one either: that needs an actual
    compile's output to react to, and by the time compile_tex_direct runs,
    this function itself is done inspecting anything Pandoc produced.
    """
    # The intermediate .tex has to live NEXT TO md_path, not in an unrelated
    # scratch directory: compile_tex_direct() (and, before that, bibtex/
    # biber) run with cwd=tex_path.parent, so a relative `\bibliography{}`/
    # `\addbibresource{}` -- or any raw \input/\includegraphics -- only
    # resolves if that's the document's own real directory. Caught directly:
    # a first version of this using a throwaway mkdtemp() scratch directory
    # compiled without error but left the citation completely unresolved
    # ("Citing ? here.") because bibtex/biber could never find refs.bib
    # relative to a /tmp path that had nothing to do with the source
    # document -- same class of bug as the openout_any one in v3.1.0,
    # just from the opposite direction (wrong directory, not wrong
    # security policy).
    #
    # NOT dot-prefixed, unlike prepared_latex_inputs()'s own temp files:
    # this one gets compiled directly as a LaTeX jobname (by
    # compile_tex_direct), and a leading dot breaks that outright --
    # confirmed with a standalone repro (`lualatex .hidden.tex`): LaTeX
    # derives its jobname from the input filename up to the FIRST period,
    # which is empty for a dotfile, so it silently ignores
    # -output-directory and tries to write ITS OWN .log next to the
    # source instead, tripping the exact same openout_any=p wall a second,
    # unrelated way. prepared_latex_inputs()'s temp files never hit this
    # because they're only ever Pandoc INPUT (--metadata-file/a title
    # source) -- Pandoc has no concept of "jobname" to derive.
    fd, tex_path_str = mkstemp(suffix=".tex", prefix=f"{md_path.stem}-pdfmd-nativebib-",
                               dir=md_path.parent)
    os.close(fd)
    tex_path = Path(tex_path_str)
    try:
        with prepared_latex_inputs([title_source, *metadata_files], True) as prepared, \
                document_header_file(md_path, bool(preamble_files) or bool(pdf_meta_snippet_text)) as header_file, \
                pdf_metadata_header_file(pdf_meta_snippet_text) as pdf_meta_file:
            source, *prepared_metadata = prepared
            cmd = ["pandoc", str(source), "-o", str(tex_path), "-t", "beamer" if presentation else "latex",
                  "--standalone"]
            if effective_from:
                cmd += ["-f", effective_from]
            for metadata in prepared_metadata:
                cmd += ["--metadata-file", str(metadata)]
            pandoc_cwd = metadata_files[0].parent if metadata_files else md_path.parent
            cmd += resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
            if presentation and slide_level is not None:
                cmd += ["--slide-level=" + str(slide_level)]
            first_font = None if document_font else (font or (preferred_font() if mainfont_auto else None))
            if first_font:
                cmd += ["-V", f"mainfont={first_font}"]
            if geometry_needed:
                cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
            if monofont_needed:
                cmd += ["-V", f"monofont={default_monofont()}"]
            for variable in variables:
                cmd += ["-V", variable]
            if shift_heading:
                cmd += ["--shift-heading-level-by=-1"]
            cmd += pandoc_options
            if preamble_files:
                for preamble_file in preamble_files:
                    cmd += ["--include-in-header", str(preamble_file)]
            if pdf_meta_file is not None:
                cmd += ["--include-in-header", str(pdf_meta_file)]
            # Last, so a document's own header-includes can override anything
            # the shared preamble/pdf-meta files above defined (Pandoc would
            # otherwise drop it entirely; see document_header_file). Added
            # whenever header_file exists, not only when preamble_files is
            # non-empty -- pdf_meta_file alone is enough to trigger the drop
            # this guards against (see document_header_includes()'s own
            # docstring for the 2026-09-20 fix this is part of).
            if header_file is not None:
                cmd += ["--include-in-header", str(header_file)]
            cmd += crossref_filter_args(md_path, pandoc_options, no_auto, str(md_path))
            if "--natbib" not in pandoc_options and "--biblatex" not in pandoc_options:
                cmd.append(f"--{citation_engine}")
            cmd += csv_table_filter_args(md_path, no_auto, csv_filter)
            if tablewidth_auto:
                cmd += ["--lua-filter", str(width_filter)]
            for lua_filter in lua_filters:
                cmd += ["--lua-filter", str(lua_filter)]
            log_cmd(cmd, pandoc_cwd, verbose)
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)
        if result.returncode != 0 or not tex_path.exists():
            return False, result.stderr.strip() or "pandoc failed to produce an intermediate .tex"
        if verbose:
            where = f"kept at {tex_path} (--keep-aux)" if keep_aux else "discarded after compiling"
            print(f"AUTO CITATIONENGINE  {md_path}: routing bibliography through --{citation_engine} "
                  f"instead of --citeproc; intermediate .tex {where}")
        return compile_tex_direct(tex_path, output, engines, keep_aux, verbose, debug)
    finally:
        # Under --keep-aux, leave the intermediate .tex for inspection too --
        # it's the one artifact from THIS function (compile_tex_direct's own
        # --keep-aux already leaves the resulting .aux/.log/.out beside it).
        if not keep_aux:
            tex_path.unlink(missing_ok=True)


def _convert_one(md_path: Path, out_dir: Path | None, presentation: bool, font: str,
                engines: list[str], variables: list[str], slide_level: int | None,
                pandoc_options: list[str],
                metadata_file: Path | list[Path] | None = None,
                output_file: Path | None = None,
                preamble_files: list[Path] | None = None,
                target_format: str = "pdf",
                from_format: str | None = None,
                no_auto: list[str] | None = None,
                verbose: bool = False,
                debug: bool = False,
                stamp_overrides: dict | None = None,
                keep_aux: bool = False) -> tuple[Path, bool, str]:
    stamp_overrides = stamp_overrides or {}
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
    output_extension = FORMAT_EXTENSION.get(target_format, f".{target_format}")
    output = output_file or (
        (out_dir / f"{md_path.stem}{output_extension}") if out_dir else md_path.with_suffix(output_extension)
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    if (target_format == "pdf" and md_path.suffix.lower() == ".tex"
            and (from_format is None or from_format.casefold() in ("latex", "tex"))
            and not auto_disabled(no_auto, "texdirect")):
        # A real .tex file is already a complete document -- compile it
        # directly instead of round-tripping it through Pandoc's LaTeX
        # reader/writer first (see compile_tex_direct()'s own comment).
        # Checked before any of Pandoc's own reader/metadata/lua/font/
        # stamp auto-discovery below runs, since none of it applies here
        # -- --no-auto texdirect (or a bare --from other than latex/tex)
        # opts back into the old Pandoc-mediated route for a document
        # that specifically needs pdfmd's own injection applied to it.
        ok, reason = compile_tex_direct(md_path, output, engines, keep_aux, verbose, debug)
        flush_summary()
        return md_path, ok, reason[-3000:]

    if md_path.suffix.lower() in OFFICE_INPUT_EXTENSIONS:
        # A .docx/.pptx/.xlsx/.odt/etc. source converts straight to PDF
        # via headless soffice -- no Pandoc involved (see the module-level
        # comment above convert_office_direct). Unlike the .tex branch
        # above, there is no working "opt back into Pandoc" route here:
        # every Pandoc-mediated helper below this point (has_mainfont,
        # contains_citations, find_lua_filters, promote_bare_title, ...)
        # unconditionally reads md_path as text, which crashes outright on
        # a binary office document even for .docx/.odt (the two formats
        # Pandoc's reader actually supports) -- caught directly, as a real
        # traceback, testing --no-auto officedirect against a real .docx.
        # Properly supporting that route would mean auditing/guarding
        # every one of those helpers for binary input, out of scope for
        # this phase (and arguably not worth it: direct soffice conversion
        # already preserves the original document's own formatting better
        # than Pandoc's docx/odt reader would). So a non-PDF --to, an
        # explicit --from, or --no-auto officedirect on an office document
        # is a clear error instead of a route that would only crash a few
        # calls later.
        if target_format != "pdf" or from_format is not None or auto_disabled(no_auto, "officedirect"):
            raise SystemExit(
                f"{md_path}: only direct PDF conversion (via soffice) is supported for an "
                f"office document in this version -- a non-PDF --to, --no-auto officedirect, "
                f"and --from all have no working Pandoc-mediated route for {md_path.suffix} "
                "input (see CHANGELOG-pdfmd.md's known-limitation note)."
            )
        ok, reason = convert_office_direct(md_path, output, verbose, debug)
        flush_summary()
        return md_path, ok, reason[-3000:]

    effective_from, reader_reason = (
        (from_format, None) if auto_disabled(no_auto, "reader")
        else resolve_from_format(md_path, from_format, metadata_files)
    )
    if reader_reason:
        note("READER", reader_reason)
    lua_filters = [] if auto_disabled(no_auto, "lua") else find_lua_filters(md_path, metadata_files)
    if not auto_disabled(no_auto, "lua"):
        for extra_filter in frontmatter_extra_lua_filters(md_path):
            if extra_filter not in lua_filters:
                lua_filters.append(extra_filter)
    for lua_filter in lua_filters:
        note("LUA", str(lua_filter))

    # Resolved once, up front, since PDF metadata (unlike the .md BUILD
    # NOTES stamp, written after a successful compile) has to already be
    # baked into the LaTeX source before pandoc/the engine even runs.
    # stamp_after_success() resolves its own copy after the fact -- cheap
    # to redo, and keeps that already-tested path untouched.
    pdf_meta_options = resolve_stamp_options(md_path, metadata_files, stamp_overrides)
    pdf_meta_snippet_text = (
        pdf_metadata_snippet(pdf_meta_options, gather_stamp_texts(md_path, preamble_files or []), verbose)
        if pdf_meta_options["pdf_metadata"] and stamp_scope_matches(pdf_meta_options, None) else None
    )

    with prepared_title_source(md_path, metadata_files, disabled=auto_disabled(no_auto, "title")) \
            as (title_source, title_shifted), \
            table_width_filter() as width_filter, \
            csv_table_filter() as csv_filter:
        if title_shifted:
            note("TITLE", f"{md_path}: promoted leading '# ' heading to Pandoc title metadata")
        shift_heading = title_shifted and not has_shift_heading_option(pandoc_options)

        if target_format != "pdf":
            # No PDF engine here -- but a TEX_STANDALONE_FORMATS writer
            # (latex/beamer/context) is asked for specifically to hand the
            # caller a document THEY compile themselves, so unlike every
            # other non-PDF target it gets the same preamble/font/margin/
            # header-includes treatment as the PDF-via-LaTeX-engine path
            # below -- just without ever running an engine, so there is no
            # missing-glyph retry: a mainfontfallback is set up front
            # instead, since there is no compile output here to inspect for
            # a retry to react to.
            is_tex_target = target_format in TEX_STANDALONE_FORMATS
            document_font = has_mainfont(md_path, variables)
            mainfont_auto = not auto_disabled(no_auto, "mainfont")
            tablewidth_auto = not auto_disabled(no_auto, "tablewidth")
            standalone_auto = (not auto_disabled(no_auto, "standalone")
                               and not has_standalone_option(pandoc_options))
            citation_engine = (None if auto_disabled(no_auto, "citationengine")
                               else frontmatter_citation_engine(md_path, metadata_files))
            if citation_engine is not None and citation_engine not in CITATION_ENGINES:
                raise SystemExit(f"{md_path}: unknown pdfmd-options.citation-engine value "
                                 f"{citation_engine!r}. Valid: {', '.join(sorted(CITATION_ENGINES))}")
            geometry_needed = (not auto_disabled(no_auto, "margin")
                              and not has_geometry(md_path, variables, metadata_files, preamble_files or []))
            monofont_needed = (not auto_disabled(no_auto, "monofont")
                              and has_code_spans(md_path.read_text(encoding="utf-8-sig"))
                              and not has_monofont(md_path, variables))
            if is_tex_target and geometry_needed:
                note("MARGIN", f"{md_path}: no geometry/margin set; "
                              f"using geometry:margin={DEFAULT_MARGIN} on LaTeX-family targets")
            margin_scalar = (None if auto_disabled(no_auto, "margin")
                             else frontmatter_margin_scalar(md_path, variables))
            if is_tex_target and margin_scalar:
                note("MARGIN", f"{md_path}: margin: {margin_scalar} isn't a Pandoc variable "
                              f"LaTeX-family targets read (geometry: is) -- using "
                              f"geometry:margin={margin_scalar}")
            if is_tex_target and monofont_needed:
                note("MONOFONT", f"{md_path}: has code but no monofont set; "
                                f"using {default_monofont()} on LaTeX-family targets")
            pagesize_typo = (None if auto_disabled(no_auto, "papersize")
                             else pagesize_typo_value(md_path, variables))
            if is_tex_target and pagesize_typo:
                note("PAPERSIZE", f"{md_path}: pagesize: {pagesize_typo!r} is not a Pandoc variable "
                                  f"(papersize: is) -- using papersize={pagesize_typo} on LaTeX-family "
                                  "targets. Set papersize: yourself, or --no-auto papersize, to silence "
                                  "this and keep the Letter default")
            with prepared_latex_inputs([title_source, *metadata_files], is_tex_target,
                                       typst_engine=(target_format == "typst")) as prepared, \
                    document_header_file(md_path, (bool(preamble_files) or bool(pdf_meta_snippet_text))
                                         and is_tex_target) as header_file, \
                    pdf_metadata_header_file(pdf_meta_snippet_text if is_tex_target else None) as pdf_meta_file:
                source, *prepared_metadata = prepared
                cmd = ["pandoc", str(source), "-o", str(output), "-t", target_format]
                if is_tex_target and standalone_auto:
                    note("STANDALONE", f"{md_path}: --to {target_format} needs a complete, "
                                       "independently compilable document; adding --standalone")
                    cmd.append("--standalone")
                if effective_from:
                    cmd += ["-f", effective_from]
                for metadata in prepared_metadata:
                    cmd += ["--metadata-file", str(metadata)]
                pandoc_cwd = metadata_files[0].parent if metadata_files else md_path.parent
                cmd += resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
                if is_tex_target:
                    # Only the PDF path's FIRST attempt (PREFERRED_FONT, or an
                    # explicit font/document mainfont) is reproduced here --
                    # its missing-glyph retry needs an actual compile to
                    # detect against, which nothing here performs. No
                    # mainfontfallback either: see PREFERRED_FONT's own
                    # comment above -- Pandoc's mainfontfallback mechanism is
                    # already known to crash lualatex outright in this
                    # environment, which is exactly why the PDF path uses a
                    # detect-then-retry-with-a-different-mainfont approach
                    # instead of that Pandoc mechanism. If the emitted
                    # mainfont turns out to have missing glyphs when this
                    # .tex is compiled by hand, override it with -f/--font
                    # (or edit \\setmainfont directly) the way the PDF path's
                    # retry would have.
                    first_font = None if document_font else (font or (preferred_font() if mainfont_auto else None))
                    if first_font:
                        cmd += ["-V", f"mainfont={first_font}"]
                    if geometry_needed:
                        cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                    elif margin_scalar:
                        cmd += ["-V", f"geometry:margin={margin_scalar}"]
                    if monofont_needed:
                        cmd += ["-V", f"monofont={default_monofont()}"]
                    if pagesize_typo:
                        cmd += ["-V", f"papersize={pagesize_typo}"]
                for variable in variables:
                    cmd += ["-V", variable]
                if target_format == "typst" and not auto_disabled(no_auto, "papersize"):
                    typst_size = typst_papersize_translation(
                        pagesize_typo or next((v.split("=", 1)[1] for v in variables
                                               if v.startswith("papersize=")), None)
                        or frontmatter_papersize_value(md_path))
                    if typst_size:
                        note("PAPERSIZE", f"{md_path}: translating papersize for --to typst "
                                          f"-> {typst_size} (typst doesn't accept Pandoc's own "
                                          "LaTeX-shaped paper names)")
                        cmd += ["-V", f"papersize={typst_size}"]
                if shift_heading:
                    cmd += ["--shift-heading-level-by=-1"]
                if preamble_files and is_tex_target:
                    for preamble_file in preamble_files:
                        cmd += ["--include-in-header", str(preamble_file)]
                if pdf_meta_file is not None:
                    cmd += ["--include-in-header", str(pdf_meta_file)]
                # Last, so a document's own header-includes can override
                # anything the shared preamble/pdf-meta files above defined
                # (Pandoc would otherwise drop it entirely; see
                # document_header_file). Added whenever header_file exists,
                # not only when preamble_files is non-empty -- see
                # document_header_includes()'s own docstring.
                if header_file is not None:
                    cmd += ["--include-in-header", str(header_file)]
                cmd += crossref_filter_args(md_path, pandoc_options, no_auto, str(md_path))
                cmd += csv_table_filter_args(md_path, no_auto, csv_filter)
                if contains_citations(md_path) and "--citeproc" not in pandoc_options and not CITEPROC_DISABLED:
                    if (is_tex_target and citation_engine in ("natbib", "biblatex")
                            and "--natbib" not in pandoc_options and "--biblatex" not in pandoc_options):
                        # No compile-and-rerun concern here the way the PDF path's
                        # convert_via_native_bibliography() has -- this branch never
                        # runs an engine at all, it just hands the caller a .tex to
                        # compile (and resolve its own bibliography in) themselves.
                        cmd.append(f"--{citation_engine}")
                    else:
                        cmd.append("--citeproc")
                # pandoc_options after the citation-engine flag above: a
                # caller-supplied --lua-filter/--filter needs resolved
                # citations already in the AST (same invariant as the
                # auto-discovered lua_filters below).
                cmd += pandoc_options
                if is_tex_target and tablewidth_auto:
                    cmd += ["--lua-filter", str(width_filter)]
                for lua_filter in lua_filters:
                    cmd += ["--lua-filter", str(lua_filter)]
                log_cmd(cmd, pandoc_cwd, verbose)
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)
            if result.returncode == 0:
                stamp_after_success(md_path, metadata_files, preamble_files or [], stamp_overrides, output, verbose)
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
        margin_scalar = (None if auto_disabled(no_auto, "margin")
                         else frontmatter_margin_scalar(md_path, variables))
        if margin_scalar:
            note("MARGIN", f"{md_path}: margin: {margin_scalar} isn't a Pandoc variable "
                          f"LaTeX-family engines read (geometry: is) -- using "
                          f"geometry:margin={margin_scalar}")
        monofont_needed = (not auto_disabled(no_auto, "monofont")
                          and has_code_spans(md_path.read_text(encoding="utf-8-sig"))
                          and not has_monofont(md_path, variables))
        if monofont_needed:
            note("MONOFONT", f"{md_path}: has code but no monofont set; "
                            f"using {default_monofont()} on LaTeX-family engines")
        pagesize_typo = (None if auto_disabled(no_auto, "papersize")
                         else pagesize_typo_value(md_path, variables))
        if pagesize_typo:
            note("PAPERSIZE", f"{md_path}: pagesize: {pagesize_typo!r} is not a Pandoc variable "
                              f"(papersize: is) -- using papersize={pagesize_typo} on LaTeX-family "
                              "engines. Set papersize: yourself, or --no-auto papersize, to silence "
                              "this and keep the Letter default")

        citation_engine = (None if auto_disabled(no_auto, "citationengine")
                           else frontmatter_citation_engine(md_path, metadata_files))
        if citation_engine is not None and citation_engine not in CITATION_ENGINES:
            raise SystemExit(f"{md_path}: unknown pdfmd-options.citation-engine value "
                             f"{citation_engine!r}. Valid: {', '.join(sorted(CITATION_ENGINES))}")
        if citation_engine in ("natbib", "biblatex") and contains_citations(md_path):
            if not any(engine in LATEX_ENGINES for engine in engines):
                print(f"WARN  {md_path}: pdfmd-options.citation-engine: {citation_engine} needs a "
                      "LaTeX-family engine, but none is available in this fallback chain; "
                      "using --citeproc instead.", file=sys.stderr)
            else:
                ok, reason = convert_via_native_bibliography(
                    md_path, output, effective_from, metadata_files, variables, pandoc_options,
                    lua_filters, preamble_files or [], title_source, pdf_meta_snippet_text,
                    citation_engine, presentation, slide_level, shift_heading, font, document_font,
                    mainfont_auto, geometry_needed, monofont_needed, tablewidth_auto, width_filter,
                    csv_filter, no_auto, engines, keep_aux, verbose, debug)
                # Pre-existing gap, closed here rather than left (2026-09-21):
                # this branch never called stamp_after_success at all, so a
                # citation-engine: natbib/biblatex document got neither the
                # .md BUILD NOTES stamp nor a PDF-metadata one -- every other
                # success path in this function does call it.
                if ok:
                    stamp_after_success(md_path, metadata_files, preamble_files or [],
                                        stamp_overrides, output, verbose)
                flush_summary()
                return md_path, ok, reason[-3000:]

        result = None
        failed_families: set[str] = set()
        for engine_index, engine in enumerate(engines):
            family = ENGINE_FAMILY.get(engine, engine)
            if family in failed_families:
                print(f"SKIP  {md_path}: {engine} shares the {family} engine with an earlier "
                      f"failure; skipping", file=sys.stderr)
                continue
            if engine == "soffice":
                # Not a real Pandoc --pdf-engine -- see convert_via_soffice_bridge's
                # own docstring for why this is special-cased here instead.
                ok, reason = convert_via_soffice_bridge(md_path, output, effective_from, metadata_files,
                                                        variables, pandoc_options, lua_filters, csv_filter,
                                                        no_auto, verbose)
                result = subprocess.CompletedProcess(args=["soffice"], returncode=0 if ok else 1,
                                                     stdout="", stderr="" if ok else reason)
                if ok:
                    if verbose:
                        print(f"AUTO SOFFICE  {md_path}: rendered via Pandoc -> .odt -> soffice "
                              "(last-resort fallback)")
                    break
                failed_families.add(family)
                remaining = [e for e in engines[engine_index + 1:] if ENGINE_FAMILY.get(e, e) not in failed_families]
                report_engine_failure(str(md_path), engine, result, remaining, debug)
                continue
            with prepared_latex_inputs([title_source, *metadata_files], engine in LATEX_ENGINES,
                                       typst_engine=(engine == "typst")) as prepared, \
                    document_header_file(md_path, (bool(preamble_files) or bool(pdf_meta_snippet_text))
                                         and engine in LATEX_ENGINES) as header_file, \
                    pdf_metadata_header_file(pdf_meta_snippet_text if engine in LATEX_ENGINES else None) as pdf_meta_file:
                source, *prepared_metadata = prepared

                def run(selected_font: str | None, fallback: bool = False):
                    cmd = ["pandoc", str(source), "-o", str(output), "--pdf-engine=" + engine]
                    if effective_from:
                        cmd += ["-f", effective_from]
                    for metadata in prepared_metadata:
                        cmd += ["--metadata-file", str(metadata)]
                    pandoc_cwd = metadata_files[0].parent if metadata_files else md_path.parent
                    cmd += resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
                    if presentation:
                        cmd += ["-t", "beamer"]
                        if slide_level is not None:
                            cmd += ["--slide-level=" + str(slide_level)]
                    if selected_font:
                        cmd += ["-V", f"mainfont={selected_font}"]
                    if fallback and not any(variable.startswith("mainfontfallback=") for variable in variables):
                        cmd += ["-V", f"mainfontfallback={fallback_font()}"]
                    if geometry_needed and engine in LATEX_ENGINES:
                        cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                    elif margin_scalar and engine in LATEX_ENGINES:
                        cmd += ["-V", f"geometry:margin={margin_scalar}"]
                    if monofont_needed and engine in LATEX_ENGINES:
                        cmd += ["-V", f"monofont={default_monofont()}"]
                    if pagesize_typo and engine in LATEX_ENGINES:
                        cmd += ["-V", f"papersize={pagesize_typo}"]
                    for variable in variables:
                        cmd += ["-V", variable]
                    if engine == "typst" and not auto_disabled(no_auto, "papersize"):
                        typst_size = typst_papersize_translation(
                            pagesize_typo or next((v.split("=", 1)[1] for v in variables
                                                   if v.startswith("papersize=")), None)
                            or frontmatter_papersize_value(md_path))
                        if typst_size:
                            note("PAPERSIZE", f"{md_path}: translating papersize for the typst "
                                              f"engine -> {typst_size} (typst doesn't accept "
                                              "Pandoc's own LaTeX-shaped paper names)")
                            cmd += ["-V", f"papersize={typst_size}"]
                    if shift_heading:
                        cmd += ["--shift-heading-level-by=-1"]
                    if preamble_files and engine in LATEX_ENGINES:
                        for preamble_file in preamble_files:
                            cmd += ["--include-in-header", str(preamble_file)]
                    if pdf_meta_file is not None:
                        cmd += ["--include-in-header", str(pdf_meta_file)]
                    # Last, so a document's own header-includes can override
                    # anything the shared preamble/pdf-meta files above
                    # defined (Pandoc would otherwise drop it entirely; see
                    # document_header_file). Added whenever header_file
                    # exists, not only when preamble_files is non-empty --
                    # see document_header_includes()'s own docstring.
                    if header_file is not None:
                        cmd += ["--include-in-header", str(header_file)]
                    cmd += crossref_filter_args(md_path, pandoc_options, no_auto, str(md_path))
                    if contains_citations(md_path) and "--citeproc" not in pandoc_options and not CITEPROC_DISABLED:
                        cmd.append("--citeproc")
                    # pandoc_options after --citeproc, same reason as below: a
                    # caller-supplied --lua-filter/--filter needs resolved
                    # citations already in the AST. (This used to sit before
                    # the --citeproc append above, which silently broke any
                    # citeproc-dependent filter passed via extra CLI args --
                    # e.g. `--lua-filter=some.lua` landed ahead of --citeproc
                    # on the actual pandoc command line. Confirmed via
                    # --verbose CMD output before this fix.)
                    cmd += pandoc_options
                    # Lua filters go last: pandoc applies --citeproc and filters in
                    # command-line order, and a filter that renders cell contents to
                    # LaTeX needs the citations already resolved. csv-table has to
                    # come before table-width so a CSV-generated table gets the same
                    # width-balancing pass a hand-written one would.
                    cmd += csv_table_filter_args(md_path, no_auto, csv_filter)
                    if tablewidth_auto and engine in LATEX_ENGINES:
                        cmd += ["--lua-filter", str(width_filter)]
                    for lua_filter in lua_filters:
                        cmd += ["--lua-filter", str(lua_filter)]
                    log_cmd(cmd, pandoc_cwd, verbose)
                    return subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd,
                                          env=tex_search_env(md_path.parent, pandoc_cwd))

                first_font = None if document_font else (font or (preferred_font() if mainfont_auto else None))
                # fallback=False, not fallback=document_font: Pandoc's own
                # mainfontfallback mechanism is the one PREFERRED_FONT's
                # comment (and the is_tex_target path's own comment above)
                # already document as crashing lualatex outright in this
                # environment -- that's exactly why a document with its own
                # mainfont gets no swap-retry (nothing to safely swap to)
                # AND, as of 2026-09-20, no auto mainfontfallback either. A
                # document that wants one can still set mainfontfallback:
                # itself in its own front matter (or a linked metadata file)
                # -- that routes through Pandoc's normal metadata merge, not
                # this -V injection, so it never hits the crash. Confirmed
                # directly: a document with mainfont: set of its own crashed
                # lualatex on this line's old `fallback=document_font` even
                # though nothing was actually missing a glyph yet.
                result = run(first_font, fallback=False)
                combined_output = result.stdout + result.stderr
                if (mainfont_auto and not explicit_font and result.returncode == 0
                        and missing_glyph_warning(combined_output)):
                    result = run(font or fallback_font())
            if result.returncode == 0:
                break
            failed_families.add(family)
            remaining = [e for e in engines[engine_index + 1:] if ENGINE_FAMILY.get(e, e) not in failed_families]
            report_engine_failure(str(md_path), engine, result, remaining, debug)
        assert result is not None
        if result.returncode == 0:
            stamp_after_success(md_path, metadata_files, preamble_files or [], stamp_overrides, output, verbose)
        flush_summary()
        return md_path, result.returncode == 0, result.stderr[-3000:]


def convert_one(md_path: Path, out_dir: Path | None, presentation: bool, font: str,
                engines: list[str], variables: list[str], slide_level: int | None,
                pandoc_options: list[str],
                metadata_file: Path | list[Path] | None = None,
                output_file: Path | None = None,
                preamble_files: list[Path] | None = None,
                target_format: str = "pdf",
                from_format: str | None = None,
                no_auto: list[str] | None = None,
                verbose: bool = False,
                debug: bool = False,
                stamp_overrides: dict | None = None,
                keep_aux: bool = False,
                backup: bool | None = None,
                backup_format: str | None = None) -> tuple[Path, bool, str]:
    """_convert_one, plus the --backup snapshot on success -- wrapped here
    rather than threaded into each of _convert_one's own success returns
    (Pandoc, natbib/biblatex, direct .tex, office), so every one of them
    gets it, including any added later.
    """
    result = _convert_one(md_path, out_dir, presentation, font, engines, variables, slide_level,
                          pandoc_options, metadata_file, output_file, preamble_files,
                          target_format=target_format, from_format=from_format, no_auto=no_auto,
                          verbose=verbose, debug=debug, stamp_overrides=stamp_overrides,
                          keep_aux=keep_aux)
    if result[1]:
        metadata_files = (metadata_file if isinstance(metadata_file, list)
                          else ([metadata_file] if metadata_file else []))
        backup_after_success(md_path, metadata_files, backup, verbose, backup_format)
    return result


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
                        help="PDF engine, family (tex/html/typst/office), numeric shortcut, or alias; run "
                             "--check-dependencies to see engine choices. 'soffice' (family 'office') is "
                             "a last-resort fallback for Markdown/Pandoc input -- Pandoc -> .odt -> "
                             "headless LibreOffice -- tried only after every tex/typst/html engine has "
                             "failed or is missing in the unrestricted chain, or on request. Meaningless "
                             "(and ignored) when "
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
                             "standalone (the --to latex/beamer/context --standalone default), "
                             "metadata/yaml (auto-discovered --metadata-file), preamble/tex "
                             "(auto-included LaTeX preambles), lua (auto-included Lua filters), "
                             "files (metadata+preamble+lua together), texdirect (the direct-.tex-"
                             "compile path -- see 'Input formats' in the module docstring; disabling "
                             "it routes .tex input back through Pandoc the pre-v3.1.0 way), "
                             "officedirect (the direct office-document-to-PDF path, same section -- "
                             "disabling it on a .docx/.odt is an error in this version, not a route "
                             "back through Pandoc), crossref (the auto-detected --filter pandoc-crossref "
                             "for @fig:/@eq:/@tbl:/@sec:/@lst: syntax), citationengine (a document's own "
                             "pdfmd-options.citation-engine setting -- see 'Output formats' in the module "
                             "docstring; disabling this KIND always means plain --citeproc), csvtable "
                             "(the .csv-div table inclusion -- see 'CSV/TSV table inclusion' in the module "
                             "docstring), papersize (a document's own pagesize: front-matter key, "
                             "auto-translated to Pandoc's real papersize: variable since pagesize: alone "
                             "silently does nothing -- disabling this KIND leaves that typo uncorrected, "
                             "same as before this existed). An "
                             "explicit -y/-H/-f/-V/--from always wins over --no-auto metadata/preamble "
                             "regardless of this flag -- --no-auto only stops pdfmd from filling in or "
                             "discovering what's otherwise unset. Same KIND names work in a document's "
                             "own pdfmd-options.no-auto front matter (see the module docstring)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show each AUTO decision's full explanation as it happens. Default is "
                             "a single condensed 'AUTO: KIND KIND ...' line per document (naming "
                             "only the reader/title/margin/mainfont/monofont/lua kinds that actually "
                             "fired) so a normal run stays quiet; AUTO YAML/TEX/ENGINE/MD are "
                             "unaffected by this flag and always print in full, since they're rarer "
                             "and already name a specific file/engine rather than a generic default")
    parser.add_argument("--no-citeproc", action="store_true",
                        help="don't add --citeproc automatically when the document uses @citation "
                             "syntax (by default pdfmd adds it, so citations and the bibliography "
                             "render without any flag)")
    parser.add_argument("--full-paths", action="store_true",
                        help="print full/absolute paths in AUTO YAML/TEX/MD lines and (with -v) the "
                             "CMD line, instead of the default -- relative to the current directory, "
                             "falling back to absolute only for a path that isn't under it (a system "
                             "temp file, e.g.). The default reads fine from a shallow directory but "
                             "gets hard to read fast from a deep one; --full-paths is the escape hatch "
                             "for a copy-pasteable absolute path, or when cwd itself is ambiguous in a "
                             "script's own log. -v/--verbose (or --debug) already implies this -- more "
                             "detail is the point of asking for it -- so --full-paths on its own is "
                             "only needed to get full paths WITHOUT the rest of --verbose's output")
    parser.add_argument("--debug", action="store_true",
                        help="on ANY PDF-engine failure -- even one a later engine in the fallback "
                             "chain recovers from -- print the engine's full captured stderr inline, "
                             "not just the one-line reason every failure now shows by default (see "
                             "'WARN ... failed (...)' -- that short reason needs no flag at all). "
                             "Implies --verbose. Use this instead of guessing which engine to force "
                             "with --engine when a document's rendered output doesn't match what the "
                             "Markdown predicts and the short reason alone isn't enough to tell why")
    parser.add_argument("--open", action="store_true",
                        help="open the finished file (via macOS 'open', Linux 'xdg-open' or Windows' default app) once "
                             "conversion succeeds. Applies to single-file and report/book mode, "
                             "each of which produce exactly one output; ignored in batch mode "
                             "(-b), which would otherwise pop open every file in the directory")
    parser.add_argument("--keep-aux", action="store_true",
                        help="for a direct .tex compile (see 'Input formats' in the module "
                             "docstring), keep .aux/.log/.out/etc. beside the source instead of "
                             "the v3.1.0-default scratch-directory cleanup that leaves only the "
                             "PDF -- use this to inspect a failing or suspicious compile's own "
                             ".log by hand. No effect on a Markdown (Pandoc-mediated) input")
    parser.add_argument("-w", "--watch", action="store_true",
                        help="recompile automatically whenever the source file, or anything in its "
                             "own directory/metadata subfolder, changes on disk -- polling, not a "
                             "filesystem-events library, so it can miss a change made and reverted "
                             "within one poll interval (WATCH_INTERVAL, 1 second). Single-file mode "
                             "only, not -b/--batch or -r/--report. Compiles once immediately, then "
                             "again on each detected change, until Ctrl+C")
    stamp_enable = parser.add_mutually_exclusive_group()
    stamp_enable.add_argument("--stamp", action="store_true", default=None,
                              help="on a successful compile, append/update a 'BUILD NOTES' HTML "
                                   "comment near the end of the .md source recording what compiled "
                                   "it and when -- invisible in the rendered output, visible in the "
                                   "source. Off by default; also settable (and this is where a "
                                   "shared default belongs) via pdfmd-options.stamp in a document's "
                                   "own front matter or a --metadata-file, which this always "
                                   "overrides when given. See --stamp-mode/--stamp-packages/"
                                   "--stamp-scope/--stamp-output for the rest of its settings")
    stamp_enable.add_argument("--no-stamp", action="store_true", default=None,
                              help="force stamping off for this run, overriding pdfmd-options.stamp "
                                   "even if a document or metadata file turns it on")
    parser.add_argument("--stamp-mode", choices=sorted(STAMP_MODES), default=None,
                        help="'replace' (default): overwrite the current stamp line in place. "
                             "'history': keep one live stamp line at the top (right under BUILD "
                             "NOTES) and demote the previous one into a 'Compile History:' list at "
                             "the end of the comment, newest-demoted-first -- both leave any other "
                             "hand-written notes in the block untouched. Switching back to 'replace' "
                             "later freezes rather than deletes an existing history list (warns)")
    parser.add_argument("--stamp-packages", nargs="+", default=None, metavar="PKG",
                        help="LaTeX package name(s) (e.g. nulabreport) whose version to include in "
                             "the stamp line, found via 'kpsewhich PKG.sty' and that file's own "
                             "\\ProvidesPackage line. A named package is silently left out of the "
                             "line if it isn't actually \\usepackage'd by this document's preambles/ "
                             "header-includes, or if its version can't be determined this way. "
                             "Default: none -- the stamp line then names only pdfmd's own version")
    parser.add_argument("--stamp-scope", choices=sorted(STAMP_SCOPES), default=None,
                        help="when stamping actually happens: 'always' (default) -- every successful "
                             "compile, standalone/batch or as part of a report/book; 'report' -- only "
                             "when this document is compiled as one chapter of a -r/--report build, "
                             "not on its own; 'standalone' -- the opposite, only outside -r/--report")
    stamp_output = parser.add_mutually_exclusive_group()
    stamp_output.add_argument("--stamp-output", action="store_true", default=None,
                              help="name the rendered output file in a standalone/batch stamp line "
                                   "('Compiled to `report.pdf` with ...') -- a report/book chapter's "
                                   "stamp always names the shared output ('...as part of `book.pdf`') "
                                   "regardless of this flag")
    stamp_output.add_argument("--no-stamp-output", action="store_true", default=None,
                              help="never name the output file in a standalone/batch stamp line, "
                                   "even if pdfmd-options.stamp.include_output turned it on")
    stamp_pdf = parser.add_mutually_exclusive_group()
    stamp_pdf.add_argument("--stamp-pdf-metadata", action="store_true", default=None,
                           help="force PDF-metadata embedding on (it's already on by default -- see "
                                "--no-stamp-pdf-metadata); only useful to override a document/"
                                "metadata file that set pdf_metadata: false")
    stamp_pdf.add_argument("--no-stamp-pdf-metadata", action="store_true", default=None,
                           help="on by default, independently of --stamp/pdfmd-options.stamp.enabled "
                                "(which only gates the .md BUILD NOTES comment): embeds the same "
                                "package/pdfmd version info as two custom PDF Info-dictionary keys "
                                "(PdfmdVersions, PdfmdBuildDate) on every LaTeX-engine compile -- "
                                "inspectable with exiftool/pdfinfo, invisible on the rendered page "
                                "and in a normal 'Document Properties' panel, and additive (never "
                                "overwrites pdftitle/pdfauthor/etc., a document's own or Pandoc's). "
                                "This flag turns it off; --stamp-pdf-metadata forces it back on over "
                                "a document/metadata file that disabled it. No effect on a non-LaTeX "
                                "PDF engine (weasyprint, typst, ...), which has no equivalent "
                                "mechanism this reaches")
    backup_enable = parser.add_mutually_exclusive_group()
    backup_enable.add_argument("--backup", action="store_true", default=None,
                               help="after a successful compile, copy the source to "
                                    "backup/<name>.bak.YYYYMMDDHHMMSS beside it (skipped when the "
                                    "newest backup is already identical). Off by default; also "
                                    "settable via pdfmd-options.backup in a document's own front "
                                    "matter or a --metadata-file (with dir:/keep: there), which this "
                                    "overrides when given")
    backup_enable.add_argument("--no-backup", action="store_false", dest="backup", default=None,
                               help="force backups off for this run, overriding pdfmd-options.backup")
    parser.add_argument("--backup-format", default=None, metavar="FORMAT",
                        help="snapshot name for this run: a preset (compact: report.md.bak."
                             "20260924091500 [default], dashed: report.md.bak.20260924-091500, stem: "
                             "report_20260924-091500.md, suffix: report.md.20260924-091500.bak, short: "
                             "report.md.09-24_09-15-00.bak) or a template using {name}/{stem}/{ext} "
                             "plus strftime codes. Overrides pdfmd-options.backup.format")
    return parser


WATCH_INTERVAL = 1.0


def watch_signature(source: Path) -> float:
    """Max mtime across ``source``'s own directory and its ``metadata/``
    subfolder (if present) -- the same two locations pdfmd's own metadata/
    preamble/Lua-filter auto-discovery already searches
    (accessory_directories()), reused as a cheap, dependency-free,
    non-recursive proxy for "has anything --watch should react to
    changed". Non-recursive is deliberate: an unbounded directory tree
    scan polled every WATCH_INTERVAL seconds would be a real cost in a
    large project directory, for no real benefit -- pdfmd's own auto-
    discovery never looks any deeper than these two directories either.
    """
    latest = 0.0
    for directory in accessory_directories(source.parent):
        for path in directory.glob("*"):
            if path.is_file():
                try:
                    latest = max(latest, path.stat().st_mtime)
                except OSError:
                    continue
    return latest


def run_watch(source: Path, argv: list[str]) -> None:
    """Recompile ``source`` immediately, then again on each later change.

    Deliberately a thin wrapper that re-execs the whole, already-tested
    CLI as a fresh subprocess (the original argv, minus -w/--watch) on
    every recompile, rather than threading a rebuild loop through main()'s
    own batch/report/single-file branching -- disproportionate
    engineering for a feature expected to see light use (a convenience
    feature the author expects to use rarely). Polling a directory's own file mtimes (watch_signature(), not a
    filesystem-events library like watchdog) keeps this dependency-free,
    matching every other part of pdfmd. The signature is re-snapshotted
    AFTER each recompile, not just before, so the compile's own output
    file (and a --stamp write back into the source itself) never falsely
    re-triggers another immediate recompile.
    """
    rerun_argv = [arg for arg in argv if arg not in ("-w", "--watch")]
    script = str(Path(__file__).resolve())
    print(f"WATCH  {source}: watching {source.parent} for changes (Ctrl+C to stop)")
    try:
        while True:
            subprocess.run([sys.executable, script, *rerun_argv])
            signature = watch_signature(source)
            while watch_signature(source) == signature:
                time.sleep(WATCH_INTERVAL)
            print(f"WATCH  change detected, recompiling {source}...")
    except KeyboardInterrupt:
        print("\nWATCH  stopped")


def main() -> None:
    args, pandoc_options = build_parser().parse_known_args()
    if args.debug:
        args.verbose = True
    global SHOW_FULL_PATHS
    # -v/--verbose already means "more detail than the quiet default," and a
    # full path is exactly that kind of detail -- so --verbose (or --debug,
    # which implies it just above) turns this on too, not just --full-paths
    # on its own.
    SHOW_FULL_PATHS = args.full_paths or args.verbose
    global CITEPROC_DISABLED
    CITEPROC_DISABLED = args.no_citeproc
    if args.check_dependencies:
        raise SystemExit(0 if dependency_report() else 1)
    if not which("pandoc"):
        raise SystemExit("Pandoc was not found on PATH. Install it -- macOS: `brew install pandoc`; "
                         "Debian/Ubuntu: `sudo apt install pandoc`; others: https://pandoc.org/installing.html "
                         "-- then run `pdfmd --check-dependencies`.")
    paths = args.path or [Path.cwd()]
    variables = DEFAULT_VARS + args.variable
    stamp_overrides: dict = {}
    if args.stamp:
        stamp_overrides["enabled"] = True
    if args.no_stamp:
        stamp_overrides["enabled"] = False
    if args.stamp_mode:
        stamp_overrides["mode"] = args.stamp_mode
    if args.stamp_packages:
        stamp_overrides["packages"] = args.stamp_packages
    if args.stamp_scope:
        stamp_overrides["scope"] = args.stamp_scope
    if args.stamp_output:
        stamp_overrides["include_output"] = True
    if args.no_stamp_output:
        stamp_overrides["include_output"] = False
    if args.stamp_pdf_metadata:
        stamp_overrides["pdf_metadata"] = True
    if args.no_stamp_pdf_metadata:
        stamp_overrides["pdf_metadata"] = False
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
        print(f"AUTO MD    {display_path(paths[0])}")
    if args.watch:
        if args.batch or args.report:
            raise SystemExit("-w/--watch only supports single-file mode, not -b/--batch or -r/--report")
        if len(paths) != 1:
            raise SystemExit("-w/--watch accepts one Markdown name or path")
        try:
            watch_source = find_markdown(paths[0])
        except FileNotFoundError as error:
            raise SystemExit(str(error))
        run_watch(watch_source, sys.argv[1:])
        return
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
        engines = resolve_engines(files[0], args.engine, engines, args.presentation, target_format, metadata_files, args.verbose)
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
        report_resource_path = resource_path_option(files[0].parent, pandoc_cwd, metadata_files)

        with table_width_filter() as width_filter, csv_table_filter() as csv_filter:
            if target_format != "pdf":
                # See convert_one's matching comment: a TEX_STANDALONE_FORMATS
                # writer here still gets --standalone plus the same
                # preamble/font/margin/header-includes treatment as the PDF
                # report path below (all decided from files[0] only, same as
                # report_no_auto/report_from/documentclass above), just
                # without an engine ever actually running.
                is_tex_target = target_format in TEX_STANDALONE_FORMATS
                report_preambles = ([] if not is_tex_target or auto_disabled(report_no_auto, "preamble")
                                    else find_preambles(files[0].parent, files[0].stem, pandoc_options)
                                    + frontmatter_extra_preambles(files[0]))
                if report_preambles:
                    announce_preambles(report_preambles)
                stamp_preambles = report_preambles
                report_pdf_meta_options = resolve_stamp_options(files[0], metadata_files, stamp_overrides)
                report_pdf_meta_snippet_text = (
                    pdf_metadata_snippet(report_pdf_meta_options,
                                         gather_stamp_texts(files[0], stamp_preambles), args.verbose)
                    if (report_pdf_meta_options["pdf_metadata"] and is_tex_target
                        and stamp_scope_matches(report_pdf_meta_options, output)) else None
                )
                report_document_font = is_tex_target and has_mainfont(files[0], variables)
                report_mainfont_auto = is_tex_target and not auto_disabled(report_no_auto, "mainfont")
                report_standalone_auto = (is_tex_target and not auto_disabled(report_no_auto, "standalone")
                                          and not has_standalone_option(pandoc_options))
                report_geometry_needed = (is_tex_target and not auto_disabled(report_no_auto, "margin")
                                          and not has_geometry(files[0], variables, metadata_files, report_preambles))
                if report_geometry_needed:
                    report_note("MARGIN", "REPORT: no geometry/margin set; "
                                         f"using geometry:margin={DEFAULT_MARGIN} on LaTeX-family targets")
                report_margin_scalar = (None if auto_disabled(report_no_auto, "margin")
                                        else frontmatter_margin_scalar(files[0], variables))
                if is_tex_target and report_margin_scalar:
                    report_note("MARGIN", f"REPORT: margin: {report_margin_scalar} isn't a Pandoc "
                                         "variable LaTeX-family targets read (geometry: is) -- using "
                                         f"geometry:margin={report_margin_scalar}")
                report_monofont_needed = (is_tex_target and not auto_disabled(report_no_auto, "monofont")
                                          and any(has_code_spans(file.read_text(encoding="utf-8-sig")) for file in files)
                                          and not has_monofont(files[0], variables))
                if report_monofont_needed:
                    report_note("MONOFONT", "REPORT: has code but no monofont set; "
                                           f"using {default_monofont()} on LaTeX-family targets")
                with prepared_latex_inputs([*files, *metadata_files], is_tex_target,
                                           typst_engine=(target_format == "typst")) as prepared, \
                        document_header_file(files[0], (bool(report_preambles) or bool(report_pdf_meta_snippet_text))
                                             and is_tex_target) as report_header_file, \
                        pdf_metadata_header_file(report_pdf_meta_snippet_text) as report_pdf_meta_file:
                    prepared_files = prepared[:len(files)]
                    prepared_metadata = prepared[len(files):]
                    cmd = ["pandoc", *map(str, prepared_files), "-o", str(output), "-t", target_format]
                    if is_tex_target and report_standalone_auto:
                        report_note("STANDALONE", f"REPORT: --to {target_format} needs a complete, "
                                                  "independently compilable document; adding --standalone")
                        cmd.append("--standalone")
                    if report_from:
                        cmd += ["-f", report_from]
                    if metadata is not AUTO_METADATA_DISABLED:
                        for metadata_file in prepared_metadata:
                            cmd += ["--metadata-file", str(metadata_file)]
                    cmd += report_resource_path
                    if is_tex_target:
                        # See convert_one's matching comment: no
                        # mainfontfallback here -- it's the Pandoc mechanism
                        # PREFERRED_FONT's own comment already documents as
                        # crashing lualatex outright in this environment.
                        report_first_font = None if report_document_font else (
                            args.font or (preferred_font() if report_mainfont_auto else None))
                        if report_first_font:
                            cmd += ["-V", f"mainfont={report_first_font}"]
                        if report_geometry_needed:
                            cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                        elif report_margin_scalar:
                            cmd += ["-V", f"geometry:margin={report_margin_scalar}"]
                        if report_monofont_needed:
                            cmd += ["-V", f"monofont={default_monofont()}"]
                    for variable in variables:
                        cmd += ["-V", variable]
                    if report_preambles and is_tex_target:
                        for preamble in report_preambles:
                            cmd += ["--include-in-header", str(preamble)]
                    if report_pdf_meta_file is not None:
                        cmd += ["--include-in-header", str(report_pdf_meta_file)]
                    # Last -- see convert_one's matching comment; report_header_file
                    # is added whenever it exists, not only when report_preambles
                    # is non-empty (report_pdf_meta_file alone can trigger the drop
                    # this guards against).
                    if report_header_file is not None:
                        cmd += ["--include-in-header", str(report_header_file)]
                    cmd += crossref_filter_args(files, pandoc_options, report_no_auto, "REPORT")
                    cmd += csv_table_filter_args(files, report_no_auto, csv_filter)
                    if (any(contains_citations(file) for file in files)
                            and "--citeproc" not in pandoc_options
                            and not CITEPROC_DISABLED):
                        cmd.append("--citeproc")
                    # pandoc_options after --citeproc: see convert_one's
                    # matching comment.
                    cmd += pandoc_options
                    if is_tex_target and not auto_disabled(report_no_auto, "tablewidth"):
                        cmd += ["--lua-filter", str(width_filter)]
                    log_cmd(cmd, pandoc_cwd, args.verbose)
                    result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)
            else:
                preambles = ([] if auto_disabled(report_no_auto, "preamble")
                            else find_preambles(files[0].parent, files[0].stem, pandoc_options)
                            + frontmatter_extra_preambles(files[0]))
                announce_preambles(preambles)
                stamp_preambles = preambles
                report_pdf_meta_options = resolve_stamp_options(files[0], metadata_files, stamp_overrides)
                report_pdf_meta_snippet_text = (
                    pdf_metadata_snippet(report_pdf_meta_options,
                                         gather_stamp_texts(files[0], stamp_preambles), args.verbose)
                    if (report_pdf_meta_options["pdf_metadata"]
                        and stamp_scope_matches(report_pdf_meta_options, output)) else None
                )
                report_tablewidth_auto = not auto_disabled(report_no_auto, "tablewidth")
                geometry_needed = (not auto_disabled(report_no_auto, "margin")
                                  and not has_geometry(files[0], variables, metadata_files, preambles))
                if geometry_needed:
                    report_note("MARGIN", "REPORT: no geometry/margin set; "
                                         f"using geometry:margin={DEFAULT_MARGIN} on LaTeX-family engines")
                margin_scalar = (None if auto_disabled(report_no_auto, "margin")
                                 else frontmatter_margin_scalar(files[0], variables))
                if margin_scalar:
                    report_note("MARGIN", f"REPORT: margin: {margin_scalar} isn't a Pandoc variable "
                                         "LaTeX-family engines read (geometry: is) -- using "
                                         f"geometry:margin={margin_scalar}")
                monofont_needed = (not auto_disabled(report_no_auto, "monofont")
                                  and any(has_code_spans(file.read_text(encoding="utf-8-sig")) for file in files)
                                  and not has_monofont(files[0], variables))
                if monofont_needed:
                    report_note("MONOFONT", "REPORT: has code but no monofont set; "
                                           f"using {default_monofont()} on LaTeX-family engines")
                # Reports need one Pandoc invocation, so retry each usable engine here.
                #
                # KNOWN GAP (2026-09-20, not yet fixed): this PDF-target branch never
                # calls document_header_file() at all, unlike its is_tex_target sibling
                # above and every convert_one call site -- so files[0]'s own YAML
                # header-includes can still be silently dropped here whenever
                # report_pdf_meta_file (or a report_preambles entry) triggers Pandoc's
                # --include-in-header/header-includes collision (see
                # document_header_includes()'s docstring for the mechanism). Left
                # unfixed rather than patched blind: CLAUDE.md's own process note
                # requires verifying a pdfmd command-building fix through the full
                # pipeline, and this session had no report/book-mode document to
                # verify against. Next report-mode session: add the same
                # document_header_file(files[0], ...) wiring the block above and
                # every convert_one call site now use, then verify with an actual
                # -r/--report build of a file that has its own header-includes.
                result = None
                failed_families: set[str] = set()
                for engine_index, engine in enumerate(engines):
                    family = ENGINE_FAMILY.get(engine, engine)
                    if family in failed_families:
                        print(f"SKIP  REPORT: {engine} shares the {family} engine with an earlier "
                              f"failure; skipping", file=sys.stderr)
                        continue
                    with prepared_latex_inputs([*files, *metadata_files], engine in LATEX_ENGINES,
                                               typst_engine=(engine == "typst")) as prepared, \
                            pdf_metadata_header_file(
                                report_pdf_meta_snippet_text if engine in LATEX_ENGINES else None
                            ) as report_pdf_meta_file:
                        prepared_files = prepared[:len(files)]
                        prepared_metadata = prepared[len(files):]
                        cmd = ["pandoc", *map(str, prepared_files), "-o", str(output), "--pdf-engine=" + engine]
                        if report_from:
                            cmd += ["-f", report_from]
                        if metadata is not AUTO_METADATA_DISABLED:
                            for metadata_file in prepared_metadata:
                                cmd += ["--metadata-file", str(metadata_file)]
                        cmd += report_resource_path
                        if geometry_needed and engine in LATEX_ENGINES:
                            cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                        elif margin_scalar and engine in LATEX_ENGINES:
                            cmd += ["-V", f"geometry:margin={margin_scalar}"]
                        if monofont_needed and engine in LATEX_ENGINES:
                            cmd += ["-V", f"monofont={default_monofont()}"]
                        for variable in variables:
                            cmd += ["-V", variable]
                        if preambles and engine in LATEX_ENGINES:
                            for preamble in preambles:
                                cmd += ["--include-in-header", str(preamble)]
                        if report_pdf_meta_file is not None:
                            cmd += ["--include-in-header", str(report_pdf_meta_file)]
                        cmd += crossref_filter_args(files, pandoc_options, report_no_auto, "REPORT")
                        cmd += csv_table_filter_args(files, report_no_auto, csv_filter)
                        if (any(contains_citations(file) for file in files)
                                and "--citeproc" not in pandoc_options
                                and not CITEPROC_DISABLED):
                            cmd.append("--citeproc")
                        # pandoc_options after --citeproc: see convert_one's
                        # matching comment.
                        cmd += pandoc_options
                        if report_tablewidth_auto and engine in LATEX_ENGINES:
                            cmd += ["--lua-filter", str(width_filter)]
                        log_cmd(cmd, pandoc_cwd, args.verbose)
                        result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd,
                                                env=tex_search_env(files[0].parent, pandoc_cwd))
                    if result.returncode == 0:
                        break
                    failed_families.add(family)
                    remaining = [e for e in engines[engine_index + 1:] if ENGINE_FAMILY.get(e, e) not in failed_families]
                    report_engine_failure("REPORT", engine, result, remaining, args.debug)
        assert result is not None
        if result.returncode == 0:
            for file in files:
                stamp_after_success(file, metadata_files, stamp_preambles, stamp_overrides,
                                    output, args.verbose, report_output=output)
                backup_after_success(file, metadata_files, args.backup, args.verbose, args.backup_format)
        for file in files:
            if not has_chapter_field(file):
                print(f"[WARNING] unnumbered Markdown included: {display_path(file)}")
            print(f"OK    {display_path(file)}")
        for file in excluded:
            print(f"SKIP  {display_path(file)}")
        if metadata is not AUTO_METADATA_DISABLED:
            for metadata_file in metadata_files:
                label = "AUTO YAML" if args.metadata_file is None else "YAML"
                print(f"{label}  {display_path(metadata_file)}")
        if not args.verbose and report_auto_summary:
            kinds = " ".join(dict.fromkeys(report_auto_summary))
            print(f"AUTO: {kinds}. Use --verbose to see in full")
        print(f"{'OK  ' if result.returncode == 0 else 'FAIL'}  REPORT  {display_path(output)}")
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
                    print(f"AUTO YAML  {display_path(path)}")
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
            if (target_format not in {"pdf", *TEX_STANDALONE_FORMATS}
                    or auto_disabled(effective_no_auto(file, args.no_auto), "preamble")):
                return []
            preambles = find_preambles(file.parent, file.stem, pandoc_options) + frontmatter_extra_preambles(file)
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
            return metadata, resolve_engines(file, args.engine, engines, args.presentation, target_format, metadata_files, args.verbose)
        def work(file):
            metadata, file_engines = file_metadata_and_engines(file)
            return convert_one(file, output, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, preamble_files=preamble_for(file), target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format)
        results = []
        if jobs > 1:
            with ProcessPoolExecutor(max_workers=jobs) as executor:
                futures = []
                for file in files:
                    metadata, file_engines = file_metadata_and_engines(file)
                    futures.append(executor.submit(convert_one, file, output, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, None, preamble_for(file), target_format, args.from_format, args.no_auto, args.verbose, args.debug, stamp_overrides, args.keep_aux, args.backup, args.backup_format))
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
            if results[0][1]:
                # Front matter only: Quarto has its own metadata system, so no
                # metadata.yaml is looked up for a .qmd (see convert_qmd).
                backup_after_success(source, [], args.backup, args.verbose, args.backup_format)
        elif source.suffix.lower() in OFFICE_INPUT_EXTENSIONS:
            # A binary office document (.docx/.pptx/.xlsx/.odt/etc.) has no
            # YAML front matter, documentclass, or LaTeX preamble to go
            # looking for -- frontmatter_value()/metadata_for() below both
            # read the file as text, which crashes outright on a zip-based
            # binary format (caught testing this Phase's own new feature: a
            # real .docx/.pptx crashed here immediately, unrelated to
            # convert_one, before this branch existed). convert_one's own
            # OFFICE_INPUT_EXTENSIONS branch handles the actual conversion
            # -- including raising a clear error for --to/--from/--no-auto
            # officedirect combinations that have no working route, rather
            # than reaching this branch's own only-slightly-later crash.
            if args.presentation:
                raise SystemExit("-p/--presentation isn't supported for an office-document input")
            # No resolve_engines() call: it would read the file as text
            # looking for a pdf-engine front-matter key, which an office
            # document never has and can't be read as (same crash as
            # above) -- engines (from select_engines(args.engine, ...) at
            # the top of main()) is used as-is.
            results = [convert_one(source, out_dir, args.presentation, args.font, engines, variables, args.slide_level, pandoc_options, None, output_file, [], target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format)]
        else:
            document_class = (frontmatter_value(source, "documentclass")
                              or frontmatter_value(source, "class"))
            try:
                metadata = metadata_for(source, document_class=document_class)
            except (FileNotFoundError, ValueError) as error:
                raise SystemExit(str(error))
            preambles = []
            if (target_format in {"pdf", *TEX_STANDALONE_FORMATS}
                    and not auto_disabled(effective_no_auto(source, args.no_auto), "preamble")):
                preambles = find_preambles(source.parent, source.stem, pandoc_options) + frontmatter_extra_preambles(source)
                announce_preambles(preambles)
            engine_metadata_files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
            file_engines = resolve_engines(source, args.engine, engines, args.presentation, target_format, engine_metadata_files, args.verbose)
            results = [convert_one(source, out_dir, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, output_file, preambles, target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format)]
        if args.open and results[0][1]:
            open_file(output)
    failures = [result for result in results if not result[1]]
    for source, ok, error in results:
        print(f"{'OK  ' if ok else 'FAIL'}  {display_path(source)}")
        if error:
            print(error)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
