#!/usr/bin/env python3
"""Convert Markdown documents to PDF (or other formats) with Pandoc.

Examples:
    pdfmd report
    pdfmd slides -p
    pdfmd /path/to/report.md -d
    pdfmd Downloads -b -f "DejaVu Serif"
    pdfmd Downloads -b --recursive
    pdfmd book -r -o book.pdf
    pdfmd report#methods            (parts mode: build one part)
    pdfmd animp                     (a unique start of a name or title works, with a WARN)
    pdfmd doc#onlyapart             (just the section "Only a Part"; also in parts mode)
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

No Pandoc, or no PDF engine (v3.20.0):
    pdfmd still turns a Markdown file into a plain PDF, with a pure-Python
    renderer: inkmd, vendored in pdfmd_inkmd/ (stdlib only, offline,
    deterministic), or md2pdf (PyPI `pymd2pdf`, ReportLab; footnotes,
    bookmarks, math) when installed -- `pdfmd --install math` / `pip install
    "pdfmd-cli[math]"`, and `--install emoji` for inkmd's colour emoji font.
    It is picked automatically only when no Pandoc route exists (a failing
    Pandoc build never falls back to it); -e inkmd / -e md2pdf / -e native or a
    `pdf-engine:` setting asks for it. Every input is read as GitHub-flavoured
    Markdown: Pandoc-only syntax is converted or stripped with one WARN per
    kind, title/author/date become a title block and the PDF's own metadata,
    other front-matter keys are listed as unused. Not available there: filters,
    preambles, citations, slides, parts/report mode, non-Markdown input.
    See normalise_gfm() and the "native tier" section.

Finding a document by name:
    `pdfmd report` looks for report.md. When no file has exactly that name
    (an existing path, a wildcard, any case, and the Latin spelling of a
    Cyrillic name all still come first, silently), pdfmd goes on looking at
    what a document is called inside, in this order, and the first step with
    a hit decides:
        1. an alias: `pdfmd-options: {alias: doc1}` (one name or a list; a
           bare `pdfmd-title: doc1` is accepted too) -- so `pdfmd doc1` builds
           that document whatever its file is called;
        2. the file name, then 3. the title (`title:`, or a `% title` line),
           ignoring case, spaces, `_ - . :`, accents and script, so
           `pdfmd animportantdocument` or `pdfmd an_important_document` finds
           "An Important Document.md" and `pdfmd glyukoza` a document titled
           "Глюкоза";
        4. the same with looser spelling (c/k/q, i/y/j, v/w, sh/ş/ш, ё/е, the
           Kazakh қ = q = k, ү/ұ/у = u, ы/і = i, ...): `pdfmd glukoza`;
        5. the START of an alias, file name or title (`pdfmd animp`,
           `pdfmd glucose`), at least 3 characters, then the start of a word
           inside one (`pdfmd body` for "Glucose in our body").
    Steps 1-3 print an `AUTO MD` line; every guess after them is a `WARN` that
    says what it matched. A name that fits two documents equally well is an
    error listing both, never a pick. `--no-auto lookup` turns all of this
    off (a command line switch only -- the document is not found yet when its
    own `pdfmd-options` could say so). Single-file lookup only: -b and -r are
    unaffected.

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

HTML output and a default format (v3.19.4):
    `pdfmd-options: {default-output: FORMAT}` is the format a document builds
    to when the command line names none (no --to, no -o with a recognized
    extension, no --stop-at, no -p): any Pandoc writer name (or pdf; tex, md,
    txt, typ, htm are accepted shortcuts). It is read from the document, else
    its metadata files (a shared metadata.yaml sets it for every document that
    finds it, any one can still override it), per document in -b batch mode and
    from the first file in -r report mode. A missing PDF engine is an error
    only for a document that really builds a PDF.

    `pdfmd-options: {html: {...}}` shapes an HTML build, and does nothing
    unless set -- pdfmd's HTML output stays the fragment it was:

        pdfmd-options:
          html:
            self-contained: true   # one file, everything inlined
            standalone: true       # a full page, resources left linked
            math: mathml           # mathml | mathjax | katex | webtex | plain
            css: style.css         # a name or a list, relative to the document

    `self-contained` is `--standalone --embed-resources` (`--self-contained`
    on a Pandoc older than 2.19), and then math defaults to MathML, the one
    kind that needs no network (mathjax/katex/webtex fetch their scripts when
    the file is built; pdfmd passes the method as `--math-method=` on Pandoc
    3.11 and later, `--html-math-method=` on the range before, and the short
    `--mathml`/`--katex`/... flags before that, whichever `pandoc --help`
    lists); a page with no title gets the file name as its
    <title>. --self-contained / --no-self-contained on the command line win
    over the document. An assembled file's embedded LaTeX preamble is left out
    of every non-LaTeX build. Not done for HTML: PDF metadata stamping and the
    engine fallback chain (they are PDF/LaTeX only), and a BUILD NOTES comment
    in the source stays in the HTML as a comment, as before.

Stopping early (--stop-at, v3.19.0):
    A build is a pipeline -- the document's parts are joined into ONE
    Markdown text, Pandoc turns that into a standalone .tex, a LaTeX engine
    turns the .tex into the PDF -- and `--stop-at STAGE` ends it after a
    stage, everything else running as normal (discovery, parts mode,
    sections, report/book, batch):

        pdfmd report --stop-at markdown     -> report.assembled.md
        pdfmd report --assemble-only        (same thing)
        pdfmd report -o out.assembled.md    (the suffix means it too)
        pdfmd report --stop-at tex          -> report.tex  (== --to latex)

    `markdown` writes the text Pandoc would have been given: the scaffold
    followed by its parts (each part's own leading front matter dropped, as
    in a normal build), or, for -r/--report, the chapters in report order.
    Nothing else of the build is applied -- no discovered metadata, preamble
    or filter (they stay beside the original), no engine, no BUILD NOTES
    stamp, no backup. The file is marked `pdfmd-assembled: true` (a key in
    its front matter, or a trailing `<!-- pdfmd-assembled: true -->` where
    there is no front matter to put it in, so how the text reads never
    changes): in parts mode such a file is never taken for a scaffold, and
    -b/-r with --stop-at markdown skip it instead of assembling it again.
    Fed back to pdfmd it builds the same `.tex` the original did (checked
    byte for byte on a parts report, a report/book and a single file). It
    never overwrites one of the files it is made from. `tex` is --to latex
    (beamer with -p); the PDF stage is the default. Not with -p/-w for
    markdown, nor for .qmd/.tex/office inputs.

    --embed-metadata [KIND ...] (v3.19.1) folds what pdfmd discovers beside
    the document into the assembled file, so it no longer needs them beside it
    (what the text points at -- images, files a preamble `\\input`s, data --
    is not embedded, and a NOTE names those it sees, bibliography and CSL files
    included when that kind is off; keep them where the document finds them,
    relative to the assembled file's folder): `metadata` (the metadata YAML files, merged the way Pandoc
    merges them -- a later file over an earlier one, the document over both,
    per top-level key -- with the document's front matter, into one block;
    `pdfmd-options` merged by pdfmd's own cascade, a file's `no-auto`/
    `parts` not carried), `preamble` (the preamble file(s), at the head of
    `header-includes`), `lua` (the Lua filters, see --lua-mode), `bibliography`
    (the bibliography and CSL files the metadata names, v3.19.7 -- a CSL style
    is also looked for in Pandoc's own user data folder, csl/, and a file not
    found anywhere is a warning saying so: each in a
    `{=pdfmd}` block too, with the path the metadata gives it -- a `../x.bib`
    or absolute name is rewritten to the embedded file's own; at build time
    they are written to a temporary folder searched after everything else, by
    Pandoc's citeproc (--resource-path) and by BibTeX/Biber (BIBINPUTS), so a
    file beside the document still wins; data, so no trust is asked); none
    named means all four. `--lua-mode embed` (default) puts each filter whole in
    a fenced raw block at the very bottom of the file --

        ````{=pdfmd}
        type: lua-filter
        name: report.lua
        sha256: ...

        <the filter's source>
        ````

    (the fence is longer than any run of backticks inside; Pandoc ignores a
    raw block of a format it doesn't know, and the BUILD NOTES stamp skips
    the blocks and writes its comment above them); `ref` writes only the
    filter's path into `pdfmd-options.lua-filter` (a missing file is a
    warning and the build goes on); `apply` (v3.19.2) runs the filters now,
    Markdown to Markdown through Pandoc, so the text already has their effect
    (listed under `pdfmd-options.applied-lua`) -- approximate: Pandoc
    re-writes the text (explicit heading ids, table/footnote layout), a
    filter's change to the metadata and one that needs citeproc first are not
    reproduced, and a filter that mentions FORMAT (it would see `markdown`,
    not the real build's format) or fails is embedded instead; `off` carries
    none. The kinds embedded
    are listed in the file's `pdfmd-options: no-auto`, so the discovery that
    would find them again stays off. A Lua filter can run any command, so
    an embedded one runs only if this machine's pdfmd wrote it (its SHA-256
    is in `<cache>/pdfmd/embedded-trust.txt`); a file from elsewhere, or one
    whose filter was edited, has the filter skipped with a warning (the
    build still completes) unless --trust-embedded. Not carried: the
    defaults pdfmd derives per machine (fonts, margins), re-derived on
    build, and -V/command-line options. A document with no front matter and
    a bare leading `# Title` keeps its preamble out of the file (a new
    front-matter block would stop the title being promoted), with a
    warning. YAML is re-written by PyYAML (YAML 1.1 rules, comments lost: an
    ambiguous scalar like `007` comes back as `7`). A report/book build
    applies no discovered Lua filter, so none is embedded there.

    Naming files and choosing what to embed from the document itself (v3.19.3),
    in `pdfmd-options` -- the same names work flat or grouped under `metadata:`
    (a name or a list; paths are relative to the document):

        pdfmd-options:
          yaml: [base.yaml, extra.yaml]   # metadata files, like -y; `metadata: base.yaml` too
          preamble: my-preamble.tex       # (already existed)
          lua-filter: my.lua              # (already existed)
          metadata:                       # the same three, grouped
            yaml: [base.yaml]
            preamble: my-preamble.tex
            lua-filter: my.lua
          embed:                          # what --assemble-only embeds, without the flag
            metadata: true                # true | false   (each kind is on unless said otherwise)
            preamble: true
            bibliography: true
            lua: embed                    # embed | ref | apply | off  (true = embed, false = off)

    `embed: true` means all four kinds; `embed: [metadata, lua]` names kinds;
    `embed: false` none. The document's own `embed` wins over its metadata
    files' (first to name it), and the command line over both: --embed-metadata
    KIND.. names the kinds, --lua-mode the filter mode, --no-embed-metadata
    turns it off for the run. An assembled file also records which source each
    front-matter key came from (`pdfmd-options.origin`: the document's own, and
    per metadata file), and the line count and hash of each preamble file, so
    --unpack can split them again. The names that were embedded (and `embed:`)
    are dropped from the assembled file's own `pdfmd-options`.

    `NAME.unpacked/`, the folder --unpack writes, is an accessory folder for
    NAME.md, searched like `metadata/`: its metadata YAML files (all of them,
    in name order -- unpacking numbers them when there are several, and nothing
    else is guessed at), its preambles (every .tex in it) and every .lua in it
    are used for that document. `--unpack --slim` rewrites the assembled file
    without what it unpacked (embedded filters, the preamble, and -- where the
    origin is recorded -- the keys that came from metadata files), leaving the
    document's own and its `NAME.unpacked/`: the original layout, rebuilt by the
    discovery.

    --unpack FILE [-o DIR] (v3.19.2) writes what an assembled file embeds back
    out as files, into FILE.unpacked/ (or DIR): each embedded Lua filter (its
    hash checked against the one recorded when it was written, and whether
    this machine's pdfmd knows it), `preamble.tex` (the part of
    `header-includes` before the preamble marker) and `metadata.yaml` (the
    merged front matter -- it can no longer tell the discovered files from
    the document's own). Never overwrites (it stops, writing nothing, if a
    file is already there) and never edits FILE (except with --slim); exit
    status 1 if a hash does not match. With the recorded origin, the metadata
    comes back as the files it was made from (`01-metadata.yaml`, ...).

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

A long document in parts (parts mode):
    A document too long to edit comfortably as one file can be a scaffold
    (`report.md`: front matter only) plus a `parts/` or `sections/` folder
    of ordinary Markdown files, each starting with its own heading:

        report.md
        parts/10-introduction.md  20-methods.md  30-discussion.md

    Turn it on once, in a shared metadata.yaml (or the scaffold's front
    matter), so the content files carry no typesetting at all:

        pdfmd-options:
          parts: auto

    `auto` makes a document a scaffold only if one of those folders exists
    beside it, so every other document is untouched; `parts: <folder>` names
    another folder, `parts: false` opts one document out, and --no-auto
    parts does it for one run. `pdfmd report` then joins the scaffold and the
    parts in filename order (digit runs compare as numbers; a subfolder is a
    part made of several files; names starting with `.` or `_` and backup
    folders are skipped) into ONE Pandoc run, exactly as if they were one
    file: labels, citations and numbering work across parts, and the output
    is byte-for-byte the LaTeX the single file would have produced. Paths
    stay relative to the scaffold's folder, whichever part they are written
    in. A leading YAML block or `% title` block in a part is removed before
    Pandoc sees it (Pandoc would otherwise let a later file's `title:`
    replace the document's).

    Build part of it with --section NAME (a part's file name, with or
    without its numeric prefix, a folder, or its number; several joined with
    `+` or `,`, or repeated), the `pdfmd report#NAME` shorthand
    (`report#discussion+appendix`), or by naming a part file:
    `pdfmd parts/20-methods.md`. Whatever the order typed, the parts build in
    report order and each at most once (`purpose+intro` is just the intro
    folder); the output is named in that order. A name that matches parts in
    two different top-level folders is an error (`discussion/yield` names it
    exactly, `a+b` joins two on purpose). Any depth works: cut the document
    finer (`--split-depth 2`) and a subsection is a part of its own, built
    without its parent heading. A partial build keeps the scaffold's title
    page and settings, is written as `report.NAME.pdf` beside the scaffold
    (never over `report.pdf`), writes no BUILD NOTES stamp, and sets
    `pdfmd-partial: true` in the document metadata so a Lua filter can adapt;
    references to parts left out print as ??. --list-parts shows the order.
    Not supported: natbib/biblatex citation engines, the soffice fallback.

    A name that is no part's is looked up as a heading inside the parts
    (below), so `report#sampling` builds the Sampling section of whichever
    part has one, and a name starting with `#` (`report##sampling`) means a
    heading from the start. Naming a part whole beats naming a section of it.

One section of any document (`pdfmd doc#NAME`):
    Without parts mode, `pdfmd doc#onlyapart` builds just the section whose
    heading is "Only a Part": from that heading to the next heading of the same
    or a higher level (its subsections come with it). Headings are written
    either way -- `## Title` or a line underlined with `===`/`---` -- and are
    named like files are found (see "Finding a document by name"): case,
    spaces, `_`, accents and script do not matter (`onlyapart`, `only_a_part`,
    `Only a Part`), a unique start works with a WARN (`doc#only`), and so does
    the heading's own `{#id}` (`doc#sec:methods`). Beyond that:
        doc##name        a level-2 heading (the number of # is the level)
        doc#parent/name  a heading under another (`doc#results/yield`)
        doc#a+b, a,b     several, built in document order, each once
        #name            no document name: the folder's only Markdown file
    A name that fits two headings equally well is an error that lists both.
    Anything that carries a Pandoc `{#label}` can be named too, not only a
    heading: a figure (`doc#fig:setup`), an equation (`$$..$$ {#eq:energy}`), a
    table (its `: caption {#tbl:values}` line, written above or below it), a
    fenced `::: {#note}` div, a `{#lst:code}` code block, a `[span]{#id}`, or a
    paragraph or list with one in it. Such an element is built alone, with the
    document's front matter (title page included) but without the text before
    the first heading; the output is `doc.fig-setup.pdf`. A figure inside a
    section also answers to `doc#section/fig:setup`. Its number restarts at 1
    (`pandoc-crossref` numbers what it is given).
    `--list-parts` prints every heading and `{#id}` a document can be cut at,
    and `--section NAME` is the same as `#NAME`. The build is a partial one, as
    in parts mode: the document's front matter, settings and the text before
    its first heading are kept, the output is `doc.NAME.pdf` (never over
    `doc.pdf`), no BUILD NOTES stamp is written and `pdfmd-partial: true` is set.
    A leading `# Title` that pdfmd promotes to the document title is not a
    section. Heading, figure and table numbers restart and references to other
    sections print as ??. Needs Pandoc (not the built-in renderers or the
    soffice fallback); `--no-auto lookup` leaves only the exact name, ignoring
    case and spaces. Setext headings are recognised here but `--split` still
    cuts at `# ` lines only.

The cache (`pdfmd-options: {cache: {aux: true}}`, or --cache):
    Pandoc normally makes a .tex in a throwaway folder, runs the engine two
    or three times, and deletes everything, so every build starts with no
    cross-reference file and needs a second pass just to learn the numbers.
    With the cache on, pdfmd has Pandoc write the very same standalone .tex
    (what `--to latex` makes) into a per-document folder under the user's
    cache directory (~/.cache/pdfmd, $XDG_CACHE_HOME, %LOCALAPPDATA%) and
    runs the engine itself, rerunning only while the log asks for it (the
    rule latexmk uses). LaTeX's .aux survives between builds, so a document
    whose numbers did not move settles in ONE pass: a 29-page report went
    from 80 s to 28 s, byte-identical text. A failed build wipes that
    document's LaTeX files and retries once from clean, so a bad cache can
    never trap you; deleting the folder is always safe. Off unless asked for.
    --no-cache overrides the setting for one build.

    In parts mode the cache also lets a part built alone see the rest: its
    labels (\\ref/\\cref to a table in a part left out) are taken from the last
    full build's .aux instead of printing ??, and at the start of every
    selected part LaTeX's counters (section, figure, table, equation,
    footnote, reaction) jump to what they were there in that build, so
    `report#discussion+appendix` shows "V. DISCUSSION" and "VIII. APPENDIX"
    as the full report does. Each part of a cache build starts with a raw
    `\\pdfmdpart{key}` line that records or restores the counters. The numbers
    are those of the LAST full build: stale if figures or tables were added
    or moved there since (pdfmd says so). A part's own labels are never
    overridden.

    What the cache does NOT do: it never skips a build or reuses a rendered
    page. Pandoc runs and LaTeX typesets the whole document, from the current
    sources, package and Lua filter, every time; only LaTeX's own cross-
    reference files carry over. A change to the package, the preamble or the
    text therefore shows in the very next build (and LaTeX asks for the extra
    pass itself if a number moved). Build with --no-cache, or `pdfmd DOC
    --clear-cache` first, when verifying a change to the package itself.

    Plot cache (`cache: {plots: true}`, --cache-plots; nulabreport >= 1.26.0,
    LuaLaTeX): nulabreport's whole plot pictures are stored as PDFs under the
    cache folder after the build that first typesets them, and the next build
    includes them at their exact size instead of drawing them again -- the
    expensive part of a report full of spectra. A plot not stored yet is
    simply typeset inline, so a build never depends on this having worked.
    Staleness is closed off three ways: the folder is keyed by a hash of
    nulabreport.sty, the document's whole preamble and the engine version (any
    change starts a new folder; old ones are pruned); each entry records the
    files its standalone job really read (LaTeX's -recorder) and is dropped
    when one changes, so editing a CSV redraws exactly the plots that use it;
    and the entry's key covers the call, its arguments, the layout it read
    and the colours set by the call's own keys. On a real 29-page report:
    80 s plain, 28 s with the aux cache, 15 s with both; pages identical to
    the uncached build to 0.05 bp in every word. `pdfmd --clear-cache` deletes
    the folder (a document's, or everything), always safe.

    The cache route is also what makes `citation-engine: natbib`/`biblatex`
    work with parts (the Pandoc-run bibliography path takes one input file);
    it runs bibtex/biber between passes. Limits: it does not retry a
    document that needs the DejaVu glyph fallback (name `mainfont:`), and
    natbib/biblatex still can't express a table caption's citation through
    a Lua filter that rebuilds captions (nulabreport.lua does).

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
    inclusion under "CSV/TSV table inclusion" above), lookup (finding a
    document by alias, title, the start of its name or a looser spelling --
    see "Finding a document by name"; CLI only). An explicit
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
PDFMD_VERSION = "3.21.2"
import argparse
import csv
import filecmp
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import tarfile
import urllib.request
import zipfile
from collections import namedtuple
from pathlib import PurePosixPath
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
# `NAME.unpacked/`, the folder --unpack writes beside NAME.md: an accessory
# folder for that one document, searched like `metadata/` is (see
# accessory_directories). Every .lua in it applies -- the folder is made by
# pdfmd for this document alone, unlike a shared folder where only fixed
# names are trusted (find_lua_filters).
UNPACKED_SUFFIX = ".unpacked"

# --no-auto KIND values, and its "font" shorthand for both font kinds at
# once. See build_parser()'s --no-auto help text for what each kind does.
NO_AUTO_KINDS = frozenset({
    "reader", "title", "margin", "mainfont", "monofont", "font", "tablewidth",
    "metadata", "yaml", "preamble", "tex", "lua", "files", "standalone",
    "texdirect", "officedirect", "crossref", "citationengine", "csvtable",
    "papersize", "parts", "lookup",
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


def accessory_directories(directory: Path, stem: str | None = None) -> list[Path]:
    """Return `directory`, plus its ACCESSORY_DIRNAME subdirectory if present,
    plus (given the document's ``stem``) the ``STEM.unpacked`` folder
    --unpack writes (see unpacked_directory()).

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
    found = [directory, accessory] if accessory.is_dir() else [directory]
    if stem:
        unpacked = directory / f"{stem}{UNPACKED_SUFFIX}"
        if unpacked.is_dir():
            found.append(unpacked)
    return found


# Folders holding files an assembled document embeds (its bibliography and CSL
# blocks, extracted for the length of one build) or that --unpack wrote for it:
# searched after everything else, so they only decide a lookup that would
# otherwise fail. Set by embedded_resources(); read by resource_path_option()
# (Pandoc's citeproc) and tex_search_env() (BibTeX/Biber, via BIBINPUTS).
EMBEDDED_RESOURCE_DIRS: list[Path] = []


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
    extra += [directory for directory in EMBEDDED_RESOURCE_DIRS if directory not in extra]
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
    if document_directory == pandoc_cwd and not EMBEDDED_RESOURCE_DIRS:
        return None
    env = os.environ.copy()
    if document_directory != pandoc_cwd:
        env["TEXINPUTS"] = f"{document_directory}{os.pathsep}{env.get('TEXINPUTS', '')}"
    if EMBEDDED_RESOURCE_DIRS:
        # (a trailing separator keeps the default search path after these)
        env["BIBINPUTS"] = (os.pathsep.join(str(item) for item in EMBEDDED_RESOURCE_DIRS)
                            + os.pathsep + env.get("BIBINPUTS", ""))
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
        # An assembled file with no front matter keeps its kinds in the
        # comment form of its marker (see ASSEMBLED_COMMENT_RE).
        if md_path.suffix.lower() in (".md", ".markdown"):
            try:
                found = ASSEMBLED_COMMENT_RE.search(
                    mask_embedded_blocks(md_path.read_text(encoding="utf-8-sig")))
            except (OSError, UnicodeDecodeError):
                found = None
            if found and found.group("kinds"):
                return found.group("kinds").split(",")
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


def has_embedded_preamble(md_path: Path) -> bool:
    """Whether an assembled file carries its preamble inside `header-includes`
    (--embed-metadata preamble). The front-matter macros a preamble expects
    (DOCUMENT_LATEX_KEYS) are only emitted when a preamble exists, and one
    embedded there counts as one."""
    kinds = frontmatter_pdfmd_options(md_path).get("embedded")
    return isinstance(kinds, list) and "preamble" in kinds


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
    text = EMBED_BLOCK_RE.sub("", md_path.read_text(encoding="utf-8-sig"))
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
        native = native_request(requested, presentation, label)
        if native is not None:
            return native
        if not which("pandoc"):
            raise SystemExit(PANDOC_MISSING)
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

    candidates = installed_engines() if which("pandoc") else []
    if presentation:
        # Pandoc's Beamer writer requires a TeX-family engine.
        candidates = [engine for engine in candidates if engine in LATEX_ENGINES]
    if candidates:
        return candidates
    if not presentation and available_native_engines():
        # No Pandoc route at all: the native tier (see the section below
        # dependency_report). Never reached while any Pandoc engine exists.
        return available_native_engines()

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
    print("Native renderers (no Pandoc needed; plainer output, Markdown only):")
    print(f"{'OK  ' if inkmd_vendored() else 'MISS'}  inkmd  (built in; no math, footnotes become endnotes)")
    if sys.version_info < (3, 11):
        print("MISS  md2pdf  (needs Python 3.11 or newer)")
    else:
        print(f"{'OK  ' if md2pdf_available() else 'MISS'}  md2pdf  (footnotes, bookmarks, math"
              + ("" if md2pdf_available() else "; pdfmd --install math") + ")")
    print(f"{'OK  ' if matplotlib_available() else 'MISS'}  matplotlib  (offline math in md2pdf"
          + ("" if matplotlib_available() else "; pdfmd --install math") + ")")
    font = inkmd_emoji_font()
    print(f"{'OK  ' if font else 'MISS'}  colour emoji font for inkmd"
          + (f"  ({font})" if font else "  (pdfmd --install emoji)"))
    pandoc_route = bool(pandoc and installed_engines())
    managed = managed_tool_directories()
    if managed:
        print("Installed by pdfmd (used when nothing else is on PATH): "
              + ", ".join(str(folder) for folder in managed))
    if pandoc_route:
        print("Mode: Pandoc and PDF engines (the native renderers are used only on request: -e inkmd / -e md2pdf).")
    elif available_native_engines():
        why = "Pandoc is installed but no PDF engine is" if pandoc else "no Pandoc"
        print(f"Mode: native only -- {why}; plain Markdown-to-PDF still works. "
              f"For the full pipeline install Pandoc and Typst: {pandoc_install_hint()}")
    return pandoc_route or bool(available_native_engines())


# -- the native tier ---------------------------------------------------------
#
# Added v3.20.0. On a machine with no Pandoc, or with Pandoc but no PDF
# engine, pdfmd used to stop with an install message. It can now still turn a
# Markdown file into a PDF with a pure-Python renderer, so a fresh `pip
# install pdfmd-cli` is useful on its own:
#
#   inkmd   vendored in pdfmd_inkmd/ (see its VENDORED.md); stdlib only,
#           offline, deterministic. No math, no PDF bookmarks, front matter
#           is not read -- this module turns the title/author into a title
#           block and the PDF Info dictionary itself.
#   md2pdf  the PyPI package `pymd2pdf` (ReportLab + mistletoe), installed by
#           `pip install "pdfmd-cli[math]"` / `pdfmd --install math`. Adds
#           footnotes, bookmarks and (with matplotlib) offline LaTeX math.
#
# Both read GitHub-flavoured Markdown, not Pandoc's. normalise_gfm() therefore
# treats every input as GFM: it keeps what they can render, converts what it
# can (page breaks, footnotes) and strips what they cannot (heading/image
# attributes, fenced divs, raw LaTeX), with one warning per kind of change.
# Pandoc, filters, preambles, citations, parts and report mode are NOT
# available here; the output is deliberately plain ("for anything more, use
# Pandoc and Typst or TeX"). The tier is chosen automatically only when no
# Pandoc route exists; `-e inkmd` / `-e md2pdf` / `pdf-engine: inkmd` request
# it explicitly, and a Pandoc build that fails never silently falls back to it.
NATIVE_ENGINES = ("md2pdf", "inkmd")
NATIVE_ALIASES = {"ink": "inkmd", "reportlab": "md2pdf", "pymd2pdf": "md2pdf"}
NATIVE_SOURCE_SUFFIXES = frozenset({".md", ".markdown", ".mdown", ".mkd"})
NATIVE_READERS = frozenset({"markdown", "md", "gfm", "commonmark", "commonmark_x", "markdown_strict"})
# `pdfmd --install KIND` / `pdfmd-cli[KIND]`; the version ranges match the
# vendored inkmd and the md2pdf this code was written against.
INSTALL_SPECS = {
    "emoji": ["inkmd>=0.5,<0.6"],
    "math": ["pymd2pdf>=0.6,<0.7", "matplotlib"],
    "pandoc": ["pypandoc_binary"],
}
# Kinds that are not pip packages (see install_typst), and the one that is both.
INSTALL_KINDS = ("pandoc", "typst", "full", "math", "emoji")
INSTALL_SIZES = {"emoji": "about 11 MB", "math": "about 150 MB", "pandoc": "about 35 MB download",
                 "typst": "about 15 MB download", "full": "about 50 MB download"}
# Front-matter keys the native renderers act on; every other key is reported.
NATIVE_META_KEYS = frozenset({"title", "subtitle", "author", "date", "subject", "keywords",
                              "papersize", "fontsize"})
PANDOC_MISSING = ("Pandoc was not found on PATH. Install it with `pdfmd --install pandoc` (no admin rights; "
                  "`pdfmd --install full` adds Typst for PDF output), or -- macOS: `brew install pandoc`; "
                  "Debian/Ubuntu: `sudo apt install pandoc`; others: https://pandoc.org/installing.html "
                  "-- then run `pdfmd --check-dependencies`.")
# What this run could not render natively, by kind -> count; read by
# offer_native_upgrade() once the build is done.
NATIVE_LOST: dict[str, int] = {}


def pandoc_missing_message() -> str:
    return PANDOC_MISSING


def inkmd_vendored() -> bool:
    """Whether the vendored inkmd (pdfmd_inkmd/) ships next to this file."""
    return importlib.util.find_spec("pdfmd_inkmd") is not None


def md2pdf_available() -> bool:
    """pymd2pdf (not the unrelated WeasyPrint-based `md2pdf`) is installed."""
    if sys.version_info < (3, 11):
        return False
    try:
        importlib.metadata.version("pymd2pdf")
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def matplotlib_available() -> bool:
    return importlib.util.find_spec("matplotlib") is not None


def inkmd_emoji_font() -> Path | None:
    """The colour-emoji font of a separately installed `inkmd` (the [emoji] extra)."""
    try:
        spec = importlib.util.find_spec("inkmd")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    font = Path(spec.origin).parent / "assets" / "emoji" / "NotoColorEmoji.ttf"
    return font if font.is_file() else None


def native_available(engine: str) -> bool:
    return inkmd_vendored() if engine == "inkmd" else md2pdf_available()


def available_native_engines() -> list[str]:
    return [engine for engine in NATIVE_ENGINES if native_available(engine)]


def native_request(requested: str, presentation: bool, label: str) -> list[str] | None:
    """The native engine(s) a -e/--engine or `pdf-engine` value names, or None
    if it names something else. Raises if the named renderer is not installed."""
    name = requested.casefold()
    if name == "native":
        engines = available_native_engines()
    else:
        name = NATIVE_ALIASES.get(name, name)
        if name not in NATIVE_ENGINES:
            return None
        engines = [name] if native_available(name) else []
        if not engines:
            hint = ("needs Python 3.11 or newer" if name == "md2pdf" and sys.version_info < (3, 11)
                    else 'install it with `pdfmd --install math` (or pip install "pdfmd-cli[math]")')
            raise SystemExit(f"{label} requested {name}, which is not available: {hint}.")
    if presentation:
        raise SystemExit(f"{label} requested a native renderer, which cannot make Beamer slides "
                         "(-p/--presentation): Pandoc's Beamer writer and a LaTeX engine are required.")
    if not engines:
        raise SystemExit(f"{label} requested the native renderers, but none is available.")
    return engines


def native_possible(args: argparse.Namespace) -> bool:
    """Whether this invocation could be served without Pandoc: a plain
    Markdown-to-PDF run, none of the modes that are Pandoc all the way down."""
    if (args.presentation or args.report or args.split or args.clear_cache or args.list_parts
            or args.unpack or args.slim or args.assemble_only or args.stop_at or args.watch
            or args.embed_metadata is not None):
        return False
    chosen = args.to.casefold() if args.to else (
        format_from_output(args.out) if args.out and not args.batch else None)
    return chosen in (None, "pdf")


def native_note(engine: str, message: str, source: Path | None = None) -> None:
    where = f"{display_path(source)}: " if source is not None else ""
    print(f"WARN  native ({engine}): {where}{message}", file=sys.stderr)


def native_lose(kind: str, count: int = 1) -> None:
    NATIVE_LOST[kind] = NATIVE_LOST.get(kind, 0) + count


FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*(.*)$")
DIV_FENCE_RE = re.compile(r"^\s*:{3,}(?:\s.*)?$")
HEADING_ATTR_RE = re.compile(r"^(#{1,6}\s+.*?)\s*\{(?:[#.][^{}\n]*|[A-Za-z][\w-]*=[^{}\n]*)\}\s*$")
IMAGE_ATTR_RE = re.compile(r"(!\[[^\]\n]*\]\([^)\n]*\))\{[^{}\n]*\}")
PAGE_BREAK_RE = re.compile(r"^\s*\\(?:newpage|pagebreak|clearpage)(?:\{\})?\s*$")
TEX_BEGIN_RE = re.compile(r"^\s*\\begin\{([A-Za-z]+\*?)\}")
TEX_COMMAND_LINE_RE = re.compile(r"^\s*\\[A-Za-z]+\*?(?:\[[^\]\n]*\])*(?:\{[^{}\n]*\})*\s*$")
TEX_MATH_ENVIRONMENTS = frozenset({"equation", "equation*", "align", "align*", "gather", "gather*",
                                   "multline", "multline*", "eqnarray", "eqnarray*", "displaymath"})
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+\1")
CITATION_RE = re.compile(r"\[-?@[^\]\n]+\]")
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?=\S)[^$\n]+?(?<=\S)\$(?!\d)")
INLINE_MATH_CAPTURE_RE = re.compile(r"(?<![\\$])\$(?=\S)([^$\n]+?)(?<=\S)\$(?!\d)")
DISPLAY_IN_TEXT_RE = re.compile(r"\$\$(.+?)\$\$")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
PAGE_BREAK_COMMENT_RE = re.compile(r"^\s*<!--\s*(?:page-?break|new-?page)\s*-->\s*$", re.IGNORECASE)
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:\s?(.*)$")
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F1E6-\U0001F1FF]")
PAGE_BREAK_MARKUP = {"inkmd": '<div style="page-break-after: always"></div>', "md2pdf": "\\pagebreak"}
PAPER_SIZES = {"a3", "a4", "a5", "letter", "legal", "tabloid"}


# -- math without a typesetter -------------------------------------------------
#
# inkmd cannot typeset math, and md2pdf can only when matplotlib is installed
# (or the network is reachable, for Kroki) and only for what matplotlib's
# mathtext understands. Rather than print `$$...$$` as source, the native tier
# sets such formulas as text: Greek letters and operators as Unicode, x^2 and
# x_i as <sup>/<sub>, variables in italics, \frac{a}{b} as a/b, and display
# math ($$...$$, \begin{aligned}...) as its own centred line(s) -- centred by
# padding with no-break spaces, since neither renderer aligns text blocks.
# It is a readable approximation, not typesetting: `pdfmd --install math` gives
# real formulas.
Chunk = tuple[str, str, float]  # (Markdown/inline-HTML, the text as it prints, size scale)

MATH_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "varpi": "ϖ", "rho": "ρ",
    "varrho": "ϱ", "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ",
    "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ",
    "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
MATH_SYMBOLS = {
    "int": "∫", "iint": "∬", "iiint": "∭", "oint": "∮", "sum": "∑", "prod": "∏", "coprod": "∐",
    "infty": "∞", "partial": "∂", "nabla": "∇", "pm": "±", "mp": "∓", "times": "×", "div": "÷",
    "cdot": "·", "cdots": "⋯", "ldots": "…", "dots": "…", "vdots": "⋮", "ddots": "⋱",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠", "approx": "≈",
    "sim": "∼", "simeq": "≃", "equiv": "≡", "propto": "∝", "cong": "≅", "ll": "≪", "gg": "≫",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "gets": "←", "leftrightarrow": "↔",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔", "implies": "⇒", "iff": "⇔",
    "mapsto": "↦", "uparrow": "↑", "downarrow": "↓", "in": "∈", "notin": "∉", "ni": "∋",
    "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇", "cup": "∪", "cap": "∩",
    "setminus": "∖", "emptyset": "∅", "varnothing": "∅", "forall": "∀", "exists": "∃",
    "neg": "¬", "lnot": "¬", "land": "∧", "wedge": "∧", "lor": "∨", "vee": "∨", "oplus": "⊕",
    "otimes": "⊗", "angle": "∠", "circ": "∘", "bullet": "•", "star": "⋆", "ast": "∗",
    "hbar": "ħ", "ell": "ℓ", "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ", "prime": "′", "dagger": "†",
    "perp": "⊥", "parallel": "∥", "mid": "|", "therefore": "∴", "because": "∵", "degree": "°",
    "langle": "⟨", "rangle": "⟩", "lceil": "⌈", "rceil": "⌉", "lfloor": "⌊", "rfloor": "⌋",
    "lbrace": "{", "rbrace": "}", "vert": "|", "Vert": "‖", "lvert": "|", "rvert": "|",
    "lVert": "‖", "rVert": "‖", "colon": ":", "triangle": "△", "square": "□", "checkmark": "✓",
}
MATH_RELATIONS = frozenset("=<>≤≥≠≈∼≃≡∝≅≪≫→←↔⇒⇐⇔↦∈∉∋⊂⊆⊃⊇⊥∥∴∵")
MATH_BINARY = frozenset("±∓×÷·∪∩∖∧∨⊕⊗∘⋆∗")
MATH_FUNCTIONS = frozenset({
    "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "sinh", "cosh",
    "tanh", "coth", "log", "ln", "lg", "exp", "lim", "limsup", "liminf", "max", "min", "sup",
    "inf", "det", "dim", "ker", "gcd", "arg", "deg", "Pr", "mod", "hom", "tr", "rank",
})
MATH_ACCENTS = {"hat": "\u0302", "widehat": "\u0302", "bar": "\u0304", "overline": "\u0304",
                "vec": "\u20d7", "dot": "\u0307", "ddot": "\u0308", "tilde": "\u0303",
                "widetilde": "\u0303", "check": "\u030c", "acute": "\u0301", "grave": "\u0300"}
MATH_BLACKBOARD = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "ℙ", "H": "ℍ"}
MATH_DROP = frozenset({"left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr",
                       "biggl", "biggr", "displaystyle", "textstyle", "scriptstyle",
                       "scriptscriptstyle", "limits", "nolimits", "nonumber", "notag", "mathstrut",
                       "strut", "protect", "relax"})
MATH_DROP_ARGUMENT = frozenset({"tag", "label", "phantom", "hphantom", "vphantom", "hspace", "vspace",
                                "ref", "eqref"})
MATH_TEXT_COMMANDS = frozenset({"text", "textrm", "textit", "mathrm", "mathit", "mbox", "operatorname",
                                "textnormal", "textsf", "mathsf", "texttt", "mathtt"})
MATH_BOLD_COMMANDS = frozenset({"mathbf", "boldsymbol", "bm", "textbf", "pmb"})
MATH_MATRICES = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "Bmatrix": ("{", "}"),
                 "vmatrix": ("|", "|"), "Vmatrix": ("‖", "‖"), "matrix": ("", ""),
                 "smallmatrix": ("", ""), "array": ("", "")}
MATH_ESCAPES = {"{": "{", "}": "}", "%": "%", "$": "$", "&": "&", "#": "#", "_": "_", "|": "‖",
                " ": " ", ",": " ", ";": " ", ":": " ", "!": "", ">": " ", "\\": "\x00"}
MATH_LINE_BREAK = "\x00"
SUPERSCRIPTS = {**dict(zip("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")), "\u2212": "⁻", "′": "′",
                "∞": "\u221e", **dict(zip("abcdefghjklmoprstuvwxyz", "ᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻ"))}
SUBSCRIPTS = {**dict(zip("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")), "\u2212": "₋",
              **dict(zip("aehijklmnoprstuvx", "ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"))}
MARKDOWN_ESCAPE_RE = re.compile(r"([\\`*_\[\]#|~])")


def escape_markup(text: str) -> str:
    """Make literal text safe inside Markdown plus inline HTML."""
    return MARKDOWN_ESCAPE_RE.sub(r"\\\1", text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class MathText:
    """LaTeX math -> readable inline text (see the comment above)."""

    def __init__(self, source: str, html: bool = True):
        self.s = source.strip()
        self.i = 0
        self.bold = False
        self.html = html  # <sup>/<sub> tags (inkmd); else Unicode super/subscripts (md2pdf)
        self.environments: list[str] = []

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def skip_space(self) -> None:
        while self.peek() in (" ", "\t", "\n", "\r") and self.peek():
            self.i += 1

    def raw_group(self) -> str:
        """The text of a {...} group (nesting respected), cursor after it."""
        self.skip_space()
        if self.peek() != "{":
            char = self.peek()
            self.i += 1 if char else 0
            return char
        depth, start = 0, self.i + 1
        while self.i < len(self.s):
            if self.s[self.i] == "\\":
                self.i += 2
                continue
            if self.s[self.i] == "{":
                depth += 1
            elif self.s[self.i] == "}":
                depth -= 1
                if depth == 0:
                    self.i += 1
                    return self.s[start:self.i - 1]
            self.i += 1
        return self.s[start:]

    def argument(self) -> list[Chunk]:
        self.skip_space()
        char = self.peek()
        if char == "{":
            inner = MathText(self.raw_group())
            inner.bold, inner.environments = self.bold, self.environments
            return inner.sequence()
        if char == "\\":
            self.i += 1
            return self.command()
        if char:
            self.i += 1
            return self.atom(char)
        return []

    def atom(self, char: str) -> list[Chunk]:
        if char.isalpha():
            return self.letters(char)
        return [(escape_markup(char), char, 1.0)]

    def letters(self, first: str) -> list[Chunk]:
        run = first
        while self.peek().isascii() and self.peek().isalpha():
            run += self.peek()
            self.i += 1
        if not run.isascii():
            return [(run, run, 1.0)]
        return [(run, run, 1.0)] if self.bold else [(f"*{run}*", run, 1.0)]

    def scaled(self, chunks: list[Chunk], factor: float) -> list[Chunk]:
        """A sub/superscript's chunks: smaller, and with no spaces around operators."""
        result = []
        for markup, plain, scale in chunks:
            if len(plain) >= 3 and plain.startswith(" ") and plain.endswith(" ") and markup.startswith(" "):
                markup, plain = markup.strip(), plain.strip()
            result.append((markup, plain, scale * factor))
        return result

    def script(self, kind: str, argument: list[Chunk]) -> Chunk:
        """A super/subscript as Unicode where every character has one, else ^(...) / _(...)."""
        plain = "".join(piece for _, piece, _ in argument).replace(" ", "")
        table = SUPERSCRIPTS if kind == "^" else SUBSCRIPTS
        if plain and all(char in table for char in plain):
            mapped = "".join(table[char] for char in plain)
            return (mapped, mapped, 0.7)
        text = f"{kind}({plain})"
        return (escape_markup(text), text, 1.0)

    def operator(self, out: list[Chunk], symbol: str, spaced: bool = True) -> None:
        last = next((piece[-1] for _, piece, _ in reversed(out) if piece.strip()), "")
        unary = not last or last in "([{,;:±∓+−×·/" or last in MATH_RELATIONS
        if not spaced or (unary and symbol in "+−±∓"):
            out.append(("\\+" if symbol == "+" else escape_markup(symbol), symbol, 1.0))
        else:
            out.append((f" {escape_markup(symbol)} ", f" {symbol} ", 1.0))

    def sequence(self) -> list[Chunk]:
        out: list[Chunk] = []
        while self.i < len(self.s):
            char = self.s[self.i]
            if char in " \t\n\r{}":
                self.i += 1
                continue
            self.i += 1
            if char == "\\":
                out.extend(self.command(out))
            elif char in "^_":
                argument = self.argument()
                if self.html:
                    tag = "sup" if char == "^" else "sub"
                    out.append((f"<{tag}>", "", 1.0))
                    out.extend(self.scaled(argument, 0.7))
                    out.append((f"</{tag}>", "", 1.0))
                else:
                    out.append(self.script(char, argument))
            elif char == "&":
                matrix = self.environments and self.environments[-1] in MATH_MATRICES
                out.append((", ", ", ", 1.0) if matrix else (" ", " ", 1.0))
            elif char == "'":
                out.append(("′", "′", 1.0))
            elif char in "=<>":
                self.operator(out, char)
            elif char == "+":
                self.operator(out, "+")
            elif char == "-":
                self.operator(out, "\u2212")
            elif char.isdigit():
                run = char
                while self.peek().isdigit() or (self.peek() == "." and self.s[self.i + 1:self.i + 2].isdigit()):
                    run += self.peek()
                    self.i += 1
                out.append((run, run, 1.0))
            elif char.isalpha():
                out.extend(self.letters(char))
            elif char == ",":
                out.append((", ", ", ", 1.0))
            else:
                out.append((escape_markup(char), char, 1.0))
        return out

    def command(self, out: list[Chunk] | None = None) -> list[Chunk]:
        """The chunks for the control sequence whose backslash was just consumed."""
        out = out if out is not None else []
        char = self.peek()
        if not char:
            return []
        if not char.isalpha():
            self.i += 1
            if char == "\\":
                if self.environments and self.environments[-1] in MATH_MATRICES:
                    return [("; ", "; ", 1.0)]
                return [(MATH_LINE_BREAK, MATH_LINE_BREAK, 1.0)]
            text = MATH_ESCAPES.get(char, char)
            return [(escape_markup(text), text, 1.0)] if text else []
        start = self.i
        while self.peek().isalpha():
            self.i += 1
        name = self.s[start:self.i]
        if name in MATH_GREEK or name in MATH_SYMBOLS:
            symbol = MATH_GREEK.get(name) or MATH_SYMBOLS[name]
            if symbol in MATH_RELATIONS:
                result: list[Chunk] = []
                self.operator(result, symbol)
                return result
            if symbol in MATH_BINARY:
                result = []
                self.operator(result, symbol)
                return result
            return [(escape_markup(symbol), symbol, 1.0)]
        if name in MATH_FUNCTIONS:
            following = self.s[self.i:].lstrip()[:1]
            tail = "" if following in ("", "(", "^", "_", "[", "|") else " "
            return [(name + tail, name + tail, 1.0)]
        if name in MATH_DROP:
            if name in ("left", "right") and self.peek() == ".":
                self.i += 1
            return []
        if name in MATH_DROP_ARGUMENT:
            self.raw_group()
            return []
        if name in ("frac", "dfrac", "tfrac", "cfrac", "binom"):
            numerator, denominator = self.argument(), self.argument()
            return self.fraction(numerator, denominator, name == "binom")
        if name == "sqrt":
            self.skip_space()
            degree: list[Chunk] = []
            if self.peek() == "[":
                end = self.s.find("]", self.i)
                degree = MathText(self.s[self.i + 1:end if end >= 0 else len(self.s)]).sequence()
                self.i = end + 1 if end >= 0 else len(self.s)
            radicand = self.argument()
            plain = "".join(piece for _, piece, _ in radicand)
            core = radicand if (len(plain) <= 2 and plain.isalnum()) else (
                [("(", "(", 1.0)] + radicand + [(")", ")", 1.0)])
            prefix = ([("<sup>", "", 1.0)] + self.scaled(degree, 0.7) + [("</sup>", "", 1.0)]) if degree else []
            return prefix + [("√", "√", 1.0)] + core
        if name in MATH_TEXT_COMMANDS:
            text = self.raw_group()
            return [(escape_markup(text), text, 1.0)]
        if name in MATH_BOLD_COMMANDS:
            previous, self.bold = self.bold, True
            inner = self.argument()
            self.bold = previous
            markup = "".join(piece for piece, _, _ in inner)
            plain = "".join(piece for _, piece, _ in inner)
            return [(f"**{markup}**", plain, 1.0)] if markup.strip() else []
        if name == "mathbb":
            text = self.raw_group().strip()
            mapped = "".join(MATH_BLACKBOARD.get(letter, letter) for letter in text)
            return [(escape_markup(mapped), mapped, 1.0)]
        if name in MATH_ACCENTS:
            inner = self.argument()
            plain = "".join(piece for _, piece, _ in inner)
            if len(plain) == 1 and plain.isalpha():
                mark = MATH_ACCENTS[name]
                return [(f"*{plain}{mark}*" if not self.bold else plain + mark, plain + mark, 1.0)]
            return inner
        if name == "begin":
            environment = self.raw_group().strip()
            self.environments.append(environment)
            opening = MATH_MATRICES.get(environment, ("", ""))[0]
            if environment == "cases":
                opening = "{"
            if environment == "array":
                self.skip_space()
                if self.peek() == "{":
                    self.raw_group()
            return [(escape_markup(opening), opening, 1.0)] if opening else []
        if name == "end":
            environment = self.raw_group().strip()
            if self.environments:
                self.environments.pop()
            closing = MATH_MATRICES.get(environment, ("", ""))[1]
            return [(escape_markup(closing), closing, 1.0)] if closing else []
        if name in ("quad", "qquad", "enspace", "thinspace", "medspace", "thickspace"):
            spaces = "    " if name == "qquad" else "  " if name == "quad" else " "
            return [(spaces, spaces, 1.0)]
        # Anything else: keep its name, so nothing silently vanishes.
        self.skip_space()
        if self.peek() == "{":
            return self.argument()
        return [(escape_markup(name), name, 1.0)]

    def fraction(self, numerator: list[Chunk], denominator: list[Chunk], binomial: bool) -> list[Chunk]:
        def simple(chunks: list[Chunk]) -> bool:
            plain = "".join(piece for _, piece, _ in chunks).strip()
            return len(plain) <= 3 and bool(plain) and not any(c in plain for c in " +−=<>")

        if binomial:
            return [("(", "(", 1.0), *numerator, (" ", " ", 1.0), *denominator, (")", ")", 1.0)]
        def wrapped(chunks: list[Chunk]) -> list[Chunk]:
            return chunks if simple(chunks) else [("(", "(", 1.0), *chunks, (")", ")", 1.0)]

        return [*wrapped(numerator), ("/", "/", 1.0), *wrapped(denominator)]


def math_lines(expression: str, html: bool = True) -> list[list[Chunk]]:
    """One list of chunks per displayed line (an `aligned` block has several)."""
    lines: list[list[Chunk]] = [[]]
    for chunk in MathText(expression, html).sequence():
        if chunk[0] == MATH_LINE_BREAK:
            lines.append([])
        else:
            lines[-1].append(chunk)
    return [line for line in lines if "".join(piece for _, piece, _ in line).strip()] or [[]]


def chunks_markup(chunks: list[Chunk]) -> str:
    """The chunks as one string; a zero-width space keeps `*a*` and `**b**` from fusing."""
    pieces: list[str] = []
    for markup, _, _ in chunks:
        if pieces and pieces[-1].endswith("*") and markup.startswith("*"):
            pieces.append("\u200b")
        pieces.append(markup)
    return re.sub(r" {2,}", " ", "".join(pieces)).strip()


def chunks_width(chunks: list[Chunk], size: float) -> float:
    """Approximate printed width in points: Helvetica metrics where the character
    exists there, 0.62 em otherwise (Greek, operators)."""
    try:
        from pdfmd_inkmd.fonts import text_width
    except ImportError:  # pragma: no cover -- the vendored copy is missing
        text_width = None
    total = 0.0
    for _, plain, scale in chunks:
        for char in plain:
            try:
                char.encode("cp1252")
                width = text_width(char, "Helvetica", size) if text_width else 0.5 * size
            except UnicodeEncodeError:
                width = 0.62 * size
            total += width * scale
    return total


PAGE_WIDTHS = {"a3": 841.89, "a4": 595.28, "a5": 419.53, "letter": 612.0, "legal": 612.0, "tabloid": 792.0}
NO_BREAK_SPACE = "\u00a0"


def centred_math(expression: str, page: str, size: float, margin: float = 72.0) -> str:
    """A display formula as Markdown for one centred block (one or more lines)."""
    available = PAGE_WIDTHS.get(page, PAGE_WIDTHS["a4"]) - 2 * margin
    rows = []
    for chunks in math_lines(expression):
        padding = max(0.0, (available - chunks_width(chunks, size)) / 2)
        count = int(padding / (0.278 * size))
        # inkmd collapses a run of whitespace, no-break spaces included, to one
        # space and trims it at the start of a paragraph; zero-width spaces
        # (which it does not treat as whitespace) in between keep every one.
        rows.append("\u200b" + (NO_BREAK_SPACE + "\u200b") * count + chunks_markup(chunks))
    return "\\\n".join(rows)


def inline_math(expression: str, html: bool = True) -> str:
    return "; ".join(chunks_markup(chunks) for chunks in math_lines(expression, html))


def stacked_math(expression: str, html: bool = True) -> str:
    """A display formula's lines, one under another (hard line breaks), uncentred."""
    return "\\\n".join(chunks_markup(chunks) for chunks in math_lines(expression, html))


# What matplotlib's mathtext (md2pdf's offline math) cannot read, and what to
# write instead.
MATHTEXT_REWRITES = (
    (re.compile(r"\\[td]frac(?![A-Za-z])"), r"\\frac"),
    (re.compile(r"\\frac\s*([0-9A-Za-z])\s*([0-9A-Za-z])(?![0-9A-Za-z{])"), r"\\frac{\1}{\2}"),
    (re.compile(r"\\(?:displaystyle|textstyle|scriptstyle|nonumber|notag|limits|nolimits)(?![A-Za-z])\s*"), ""),
    (re.compile(r"\\(?:tag|label)\*?\{[^{}]*\}"), ""),
    (re.compile(r"\\le(?![A-Za-z])"), r"\\leq"),
    (re.compile(r"\\ge(?![A-Za-z])"), r"\\geq"),
    (re.compile(r"\\[lr]Vert(?![A-Za-z])"), r"\\|"),
)


def mathtext_form(expression: str) -> str | None:
    """The expression rewritten for matplotlib's mathtext if it can read it, else None."""
    for pattern, replacement in MATHTEXT_REWRITES:
        expression = pattern.sub(replacement, expression)
    try:
        from matplotlib import mathtext
        mathtext.MathTextParser("path").parse(f"${expression.strip()}$")
    except Exception:  # noqa: BLE001 -- any parse failure means "set it as text"
        return None
    return expression.strip()


class NativeSource:
    """A document, normalised for a native renderer."""

    def __init__(self, text: str, metadata: dict, has_footnotes: bool, math: int, emoji: bool):
        self.text = text
        self.metadata = metadata
        self.has_footnotes = has_footnotes
        self.math = math
        self.emoji = emoji


def scalar_text(value) -> str:
    """A front-matter value as one line of plain text ('' when absent)."""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return " ".join(str(value).split())


def author_names(value) -> list[str]:
    if isinstance(value, dict):
        value = value.get("name")
    if isinstance(value, list):
        return [name for item in value for name in author_names(item)]
    text = scalar_text(value)
    return [text] if text else []


def split_front_matter(text: str) -> tuple[dict, str]:
    """(front-matter mapping, body). {} when there is none or it will not parse."""
    match = re.match(r"^---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if not match:
        return {}, text
    body = text[match.end():]
    if yaml is None:
        return {}, body
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}, body
    return (data if isinstance(data, dict) else {}), body


CSV_DIV_LINE_RE = re.compile(r"^\s*:{3,}\s*\{([^}]*\.csv\b[^}]*)\}\s*$")
DIV_CLOSE_RE = re.compile(r"^\s*:{3,}\s*$")
DIV_ATTRIBUTE_RE = re.compile(r"""([\w-]+)=(?:"([^"]*)"|'([^']*)'|(\S+))""")


def csv_div_table(attributes: str, base_dir: Path, source: Path | None) -> list[str]:
    """The Markdown pipe table for a `::: {.csv file="data.csv"}` div, the way
    CSV_TABLE_LUA_FILTER builds it for Pandoc: delimiter from the extension or
    `delimiter=`, first row the header unless `header="false"`, capped at
    10 rows x 7 columns unless `rows=`/`cols=` (or `all`) say otherwise."""
    options = {name: next(value for value in groups if value is not None)
               for name, *groups in ((m.group(1), m.group(2), m.group(3), m.group(4))
                                     for m in DIV_ATTRIBUTE_RE.finditer(attributes))}
    name = options.get("file")
    if not name:
        native_note("csv", ".csv div has no file= attribute; left empty", source)
        return []
    path = (base_dir / name)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        native_note("csv", f"could not open '{name}'; left empty", source)
        return []

    def limit(key: str, default: int) -> float:
        value = options.get(key, "")
        if not value:
            return default
        if value.lower() == "all":
            return float("inf")
        return int(value) if value.isdigit() else default

    delimiter = options.get("delimiter") or ("\t" if name.lower().endswith(".tsv") else ",")
    max_rows, max_columns = limit("rows", 10), limit("cols", 7)
    has_header = options.get("header") != "false"
    rows = [row for row in csv.reader(text.splitlines(), delimiter=delimiter) if row]
    total_columns = max((len(row) for row in rows), default=0)
    shown_columns = int(min(total_columns, max_columns))
    rows = [row[:shown_columns] for row in rows]
    header = rows.pop(0) if has_header and rows else [f"Column {n}" for n in range(1, max(shown_columns, 1) + 1)]
    shown = rows[:int(min(len(rows), max_rows))]

    def cell(value: str | None) -> str:
        return (value or "").replace("\r", "").replace("\n", " ").replace("|", "\\|")

    lines = ["| " + " | ".join(cell(header[n] if n < len(header) else "") for n in range(len(header))) + " |",
             "|" + " --- |" * len(header)]
    for row in shown:
        lines.append("| " + " | ".join(cell(row[n] if n < len(row) else "") for n in range(len(header))) + " |")
    if len(shown) < len(rows) or shown_columns < total_columns:
        plural = lambda number: "" if number == 1 else "s"  # noqa: E731
        lines += ["", f"*(showing {len(shown)} of {len(rows)} row{plural(len(rows))}, {shown_columns} of "
                      f"{total_columns} column{plural(total_columns)} -- use `rows=all`/`cols=all`, or "
                      "`rows=N`/`cols=N`, on this `.csv` div to include more)*"]
    return lines


def strip_html_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    """Remove <!-- ... --> from one line (outside code spans); a comment left
    open at the end of the line carries over to the next one."""
    pieces: list[str] = []
    position = 0
    spans = [(match.start(), match.end()) for match in CODE_SPAN_RE.finditer(line)]
    spans.append((len(line), len(line)))
    for start, end in spans:
        segment = line[position:start]
        if in_comment:
            close = segment.find("-->")
            if close < 0:
                segment = ""
            else:
                segment, in_comment = segment[close + 3:], False
        segment = HTML_COMMENT_RE.sub("", segment)
        open_at = segment.find("<!--")
        if open_at >= 0:
            segment, in_comment = segment[:open_at], True
        pieces.append(segment)
        pieces.append(line[start:end])
        position = end
    return "".join(pieces), in_comment


def convert_math_items(items: list[tuple[str, bool]], engine: str, page: str,
                       size: float) -> tuple[list[tuple[str, bool]], int]:
    """Set formulas md2pdf cannot typeset (and, for inkmd, every formula) as text.

    inkmd: every formula becomes text, display math a centred block. md2pdf with
    matplotlib: formulas mathtext can read are kept (rewritten where a known
    LaTeX spelling needs it), the rest become text. md2pdf without matplotlib:
    untouched (it needs the network for them). Returns (items, formulas set as text).
    """
    typeset = engine == "md2pdf"
    if typeset and not matplotlib_available():
        return items, 0
    converted = 0
    out: list[tuple[str, bool]] = []

    def inline(expression: str) -> str:
        nonlocal converted
        if typeset:
            form = mathtext_form(expression)
            if form is not None:
                return f"${form}$"
        converted += 1
        return inline_math(expression, html=not typeset)

    index = 0
    while index < len(items):
        line, code = items[index]
        stripped = line.strip()
        display_block = stripped.startswith("$$") and (
            stripped.count("$$") == 1 or (stripped.endswith("$$") and stripped.count("$$") == 2))
        if code or not display_block:
            if not code:
                parts = []
                position = 0
                for span in CODE_SPAN_RE.finditer(line):
                    parts.append(("text", line[position:span.start()]))
                    parts.append(("code", span.group(0)))
                    position = span.end()
                parts.append(("text", line[position:]))
                line = "".join(
                    INLINE_MATH_CAPTURE_RE.sub(lambda m: inline(m.group(1)),
                                               DISPLAY_IN_TEXT_RE.sub(lambda m: inline(m.group(1)), text))
                    if kind == "text" else text for kind, text in parts)
            out.append((line, code))
            index += 1
            continue
        end = index
        expression = None
        if len(stripped) > 4 and stripped.endswith("$$"):
            expression = stripped[2:-2]
        else:
            collected = [stripped[2:]]
            end = index + 1
            while end < len(items) and end - index < 200 and not items[end][1]:
                current = items[end][0].strip()
                if current.endswith("$$"):
                    collected.append(current[:-2])
                    expression = "\n".join(collected)
                    break
                collected.append(current)
                end += 1
        if expression is None or not expression.strip():
            out.append((line, code))
            index += 1
            continue
        form = mathtext_form(expression) if typeset else None
        if form is not None:
            out.extend([("", False), ("$$", False), (form, False), ("$$", False), ("", False)])
        else:
            converted += 1
            block = stacked_math(expression, html=False) if typeset else centred_math(expression, page, size)
            out.extend([("", False), (block, False), ("", False)])
        index = end + 1
    return out, converted


def protect_dollars(items: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    """Write the dollar signs that are not math (prices) as &#36;, so md2pdf, which
    reads "$5 and $6" as a formula (and prints a backslash escape as it is), leaves them alone. Math follows Pandoc's rule:
    `$` opens only before a non-space and closes only after one, not before a digit."""
    protected: list[tuple[str, bool]] = []
    for line, code in items:
        if code or line.strip() == "$$" or "$" not in line:
            protected.append((line, code))
            continue
        pieces, position = [], 0
        for span in CODE_SPAN_RE.finditer(line):
            pieces.append((line[position:span.start()], True))
            pieces.append((span.group(0), False))
            position = span.end()
        pieces.append((line[position:], True))
        rebuilt = []
        for text, is_text in pieces:
            if is_text:
                masked: list[str] = []

                def keep(match: re.Match) -> str:
                    masked.append(match.group(0))
                    return f"\x00{len(masked) - 1}\x00"

                text = INLINE_MATH_CAPTURE_RE.sub(keep, DISPLAY_IN_TEXT_RE.sub(keep, text))
                text = re.sub(r"(?<!\\)\$", "&#36;", text)
                text = re.sub(r"\x00(\d+)\x00", lambda match: masked[int(match.group(1))], text)
            rebuilt.append(text)
        protected.append(("".join(rebuilt), code))
    return protected


def normalise_gfm(text: str, engine: str, metadata_files: list[Path] = (), base_dir: Path | None = None,
                  source_path: Path | None = None) -> tuple[NativeSource, dict[str, int]]:
    """Reduce a Pandoc-flavoured Markdown file to what ``engine`` can render.

    Returns the source plus a count of what was dropped or converted, by kind.
    Fenced code is never touched. The kinds: ``attributes``, ``divs``,
    ``latex`` (raw LaTeX removed), ``math`` (formulas found), ``math_text``
    (formulas set as plain text, see convert_math_items), ``citations`` (left
    as written), ``footnotes`` (turned into endnotes). HTML comments are
    dropped silently (a ``<!-- pagebreak -->`` comment becomes a page break).
    """
    front, body = split_front_matter(text.lstrip("﻿"))
    metadata: dict = {}
    for path in metadata_files:
        metadata.update(metadata_file_yaml(path))
    metadata.update(front)

    counts: dict[str, int] = {}

    def count(kind: str, amount: int = 1) -> None:
        counts[kind] = counts.get(kind, 0) + amount

    items: list[tuple[str, bool]] = []  # (line, inside fenced code)
    fence: tuple[str, int] | None = None
    raw_block = False
    skip_environment: str | None = None
    math_environment: str | None = None
    in_comment = False
    in_display = False
    skip_csv_div = False
    for line in body.splitlines():
        match = FENCE_RE.match(line)
        if fence is not None:
            closes = match and match.group(1)[0] == fence[0] and len(match.group(1)) >= fence[1] \
                and not match.group(2).strip()
            if closes:
                fence = None
                if not raw_block:
                    items.append((line, True))
                raw_block = False
            elif not raw_block:
                items.append((line, True))
            continue
        if match:
            info = match.group(2).strip()
            fence = (match.group(1)[0], len(match.group(1)))
            raw_block = bool(re.match(r"^\{=(?:latex|tex|typst|context)\}$", info))
            if raw_block:
                count("latex")
            else:
                items.append((line, True))
            continue
        if in_display:
            # Inside $$ ... $$: the formula's own \begin{aligned} etc. are not raw LaTeX.
            items.append((line, False))
            in_display = not line.strip().endswith("$$")
            continue
        opener = line.strip()
        if opener.startswith("$$") and opener.count("$$") == 1:
            in_display = True
            items.append((line, False))
            continue
        if not in_comment and PAGE_BREAK_COMMENT_RE.match(line):
            items.append((PAGE_BREAK_MARKUP[engine], False))
            continue
        before_comments = line
        line, in_comment = strip_html_comments(line, in_comment)
        if line != before_comments and not line.strip():
            continue
        if math_environment is not None:
            if re.match(rf"^\s*\\end\{{{re.escape(math_environment)}\}}", line):
                math_environment = None
                items.append(("$$", False))
            else:
                items.append((line, False))
            continue
        if skip_environment is not None:
            if re.match(rf"^\s*\\end\{{{re.escape(skip_environment)}\}}", line):
                skip_environment = None
            continue
        begin = TEX_BEGIN_RE.match(line)
        if begin and begin.group(1) in TEX_MATH_ENVIRONMENTS:
            # \begin{equation}/align/...: a display formula, handled like $$...$$.
            name = re.escape(begin.group(1))
            single = re.match(rf"^\s*\\begin\{{{name}\}}(.*)\\end\{{{name}\}}\s*$", line)
            if single:
                items.append((f"$${single.group(1).strip()}$$", False))
            else:
                math_environment = begin.group(1)
                items.append(("$$", False))
                rest = re.sub(rf"^\s*\\begin\{{{name}\}}", "", line).strip()
                if rest:
                    items.append((rest, False))
            continue
        if begin and begin.group(1) not in TEX_MATH_ENVIRONMENTS:
            skip_environment = begin.group(1)
            count("latex")
            continue
        if PAGE_BREAK_RE.match(line):
            items.append((PAGE_BREAK_MARKUP[engine], False))
            continue
        if TEX_COMMAND_LINE_RE.match(line):
            count("latex")
            continue
        if skip_csv_div:
            skip_csv_div = not DIV_CLOSE_RE.match(line)
            continue
        csv_div = CSV_DIV_LINE_RE.match(line)
        if csv_div:
            table = csv_div_table(csv_div.group(1), base_dir or Path.cwd(), source_path)
            items.extend([("", False), *[(row, False) for row in table], ("", False)])
            skip_csv_div = True
            count("csv")
            continue
        if DIV_FENCE_RE.match(line):
            count("divs")
            continue
        stripped = HEADING_ATTR_RE.sub(r"\1", line)
        stripped = IMAGE_ATTR_RE.sub(r"\1", stripped)
        if stripped != line:
            count("attributes")
        items.append((stripped, False))

    # Footnotes: md2pdf renders them itself; inkmd gets numbered endnotes.
    has_footnotes = any(FOOTNOTE_DEF_RE.match(line) and not code for line, code in items)
    endnotes: list[str] = []
    if has_footnotes and engine == "inkmd":
        definitions: dict[str, str] = {}
        kept: list[tuple[str, bool]] = []
        index = 0
        while index < len(items):
            line, code = items[index]
            definition = None if code else FOOTNOTE_DEF_RE.match(line)
            if definition is None:
                kept.append((line, code))
                index += 1
                continue
            note = [definition.group(2)]
            index += 1
            while index < len(items) and not items[index][1] and (
                    items[index][0].startswith(("    ", "\t"))
                    or (not items[index][0].strip() and index + 1 < len(items)
                        and items[index + 1][0].startswith(("    ", "\t")))):
                note.append(items[index][0].strip())
                index += 1
            definitions[definition.group(1)] = " ".join(part for part in note if part)
        numbers: dict[str, int] = {}

        def reference(match: re.Match) -> str:
            label = match.group(1)
            if label not in definitions:
                return match.group(0)
            if label not in numbers:
                numbers[label] = len(numbers) + 1
                endnotes.append(definitions[label])
            return f"<sup>{numbers[label]}</sup>"

        items = [(line if code else FOOTNOTE_REF_RE.sub(reference, line), code) for line, code in kept]
        count("footnotes", len(endnotes))

    lines = [line for line, _ in items]
    math = display = 0
    citations = 0
    emoji = False
    for line, code in items:
        if code:
            continue
        plain = CODE_SPAN_RE.sub("", line)
        math += len(INLINE_MATH_RE.findall(plain))
        if plain.strip() == "$$":
            display += 1
        else:
            display += 2 * (plain.count("$$") // 2)
        citations += len(CITATION_RE.findall(plain))
        emoji = emoji or bool(EMOJI_RE.search(plain))
    math += display // 2
    if math:
        count("math", math)
    if citations:
        count("citations", citations)

    formulas_as_text = 0
    if math:
        items, formulas_as_text = convert_math_items(items, engine, native_paper(metadata),
                                                     native_font_size(metadata) or 12.0)
        lines = [line for line, _ in items]
        if formulas_as_text:
            count("math_text", formulas_as_text)
    if engine == "md2pdf":
        items = protect_dollars(items)
        lines = [line for line, _ in items]
    block = title_block(metadata, lines)
    notes_text = ""
    if endnotes:
        notes_text = "\n\n---\n\n**Notes**\n\n" + "\n".join(f"{n}. {note}" for n, note in enumerate(endnotes, 1)) + "\n"
    front_text = ""
    if engine == "md2pdf" and yaml is not None:
        wanted = {key: scalar_text(metadata.get(key)) for key in ("title", "subject", "keywords", "date")
                  if scalar_text(metadata.get(key))}
        names = author_names(metadata.get("author"))
        if names:
            wanted["author"] = ", ".join(names)
        if wanted:
            front_text = "---\n" + yaml.safe_dump(wanted, allow_unicode=True, sort_keys=False) + "---\n\n"
    # md2pdf prepends a hidden "<!-- SOURCE_FILE: <path> -->" marker to the text
    # and, when a paragraph follows it directly, prints it (path included) into
    # the PDF; a heading after it is fine. So a document that does not start with
    # a heading gets an empty paragraph first (a comment of our own would print).
    first = next((line.strip() for line in [*block.splitlines(), *lines] if line.strip()), "#")
    guard = "&nbsp;\n\n" if engine == "md2pdf" and not first.startswith("#") else ""
    result = front_text + guard + block + "\n".join(lines).strip("\n") + notes_text
    return NativeSource(result.rstrip("\n") + "\n", metadata, has_footnotes, math, emoji), counts


def title_block(metadata: dict, body_lines: list[str]) -> str:
    """The title/author/date block Pandoc would typeset, as Markdown."""
    title = scalar_text(metadata.get("title"))
    if not title:
        return ""
    first = next((line.strip() for line in body_lines if line.strip()), "")
    if first == f"# {title}":
        return ""
    parts = [f"# {title}"]
    subtitle = scalar_text(metadata.get("subtitle"))
    if subtitle:
        parts.append(f"*{subtitle}*")
    byline = " — ".join(part for part in (", ".join(author_names(metadata.get("author"))),
                                              scalar_text(metadata.get("date"))) if part)
    if byline:
        parts.append(f"*{byline}*")
    return "\n\n".join(parts) + "\n\n"


def ignored_front_matter_keys(metadata: dict) -> list[str]:
    return sorted(str(key) for key in metadata if str(key) not in NATIVE_META_KEYS)


def native_paper(metadata: dict) -> str:
    value = scalar_text(metadata.get("papersize")).casefold().replace("paper", "")
    return value if value in PAPER_SIZES else "a4"


def native_font_size(metadata: dict) -> float | None:
    match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:pt)?$", scalar_text(metadata.get("fontsize")))
    return float(match.group(1)) if match else None


def native_order(engines: list[str], source: NativeSource) -> list[str]:
    """Which of the available native renderers to try, best first.

    md2pdf when the document has footnotes, math it can typeset, or a
    title/author to record; inkmd otherwise (and as the fallback if the first
    choice fails)."""
    if len(engines) == 1:
        return list(engines)
    wants_md2pdf = (source.has_footnotes or bool(source.math) or bool(scalar_text(source.metadata.get("title")))
                    or bool(author_names(source.metadata.get("author"))))
    if source.math and not matplotlib_available():
        wants_md2pdf = False  # md2pdf would need the network (Kroki) for each formula
    first = "md2pdf" if wants_md2pdf and "md2pdf" in engines else "inkmd"
    return [first, *[engine for engine in engines if engine != first]]


def load_inkmd():
    """The vendored inkmd, pointed at the emoji font of an installed `inkmd` if any."""
    import pdfmd_inkmd
    font = inkmd_emoji_font()
    if font is not None and hasattr(pdfmd_inkmd.emoji, "_BUNDLED_FONT"):
        pdfmd_inkmd.emoji._BUNDLED_FONT = str(font)
        cache_clear = getattr(pdfmd_inkmd.emoji._load_font, "cache_clear", None)
        if cache_clear:
            cache_clear()
    return pdfmd_inkmd


def set_pdf_info(pdf_path: Path, metadata: dict, verbose: bool, creator: str = "") -> None:
    """Record title/author/subject/keywords (and the renderer as /Creator) in the
    PDF Info dictionary, best effort. stamp_pdf_metadata_posthoc() then appends
    "via pdfmd-cli" to the creator."""
    info = {"/Creator": creator,
            "/Title": scalar_text(metadata.get("title")),
            "/Author": ", ".join(author_names(metadata.get("author"))),
            "/Subject": scalar_text(metadata.get("subject")),
            "/Keywords": scalar_text(metadata.get("keywords"))}
    info = {key: value for key, value in info.items() if value}
    if not info or pypdf is None:
        return
    try:
        reader = pypdf.PdfReader(pdf_path)
        writer = pypdf.PdfWriter()
        writer.append(reader)
        writer.add_metadata({**(dict(reader.metadata) if reader.metadata else {}), **info})
        with NamedTemporaryFile("wb", suffix=".pdf", delete=False, dir=pdf_path.parent) as temporary:
            writer.write(temporary)
            temporary_path = Path(temporary.name)
        temporary_path.replace(pdf_path)
    except Exception as error:  # noqa: BLE001 -- the PDF itself is already fine
        if verbose:
            print(f"WARN  native: could not write the PDF title/author ({error})", file=sys.stderr)


@contextmanager
def captured_logs(name: str) -> Iterator[list[str]]:
    """Collect a library's WARNING+ log records instead of letting them print."""
    messages: list[str] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger(name)
    handler = Collector(level=logging.WARNING)
    previous = (logger.level, logger.propagate)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        yield messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous[0])
        logger.propagate = previous[1]


def report_messages(engine: str, messages: list[str], source: Path) -> None:
    """Print each distinct renderer warning once, with a repeat count."""
    seen: dict[str, int] = {}
    for message in messages:
        first_line = (message.splitlines() or [""])[0][:300]
        seen[first_line] = seen.get(first_line, 0) + 1
    for message, times in seen.items():
        native_note(engine, message + (f" (x{times})" if times > 1 else ""), source)


def render_native(engine: str, md_path: Path, source: NativeSource, output: Path, verbose: bool) -> list[str]:
    """Render one normalised document with one native engine, or raise.
    Returns the renderer's own warnings, for the caller to report."""
    if engine == "inkmd":
        ink = load_inkmd()
        options: dict = {"page_size": native_paper(source.metadata), "base_dir": md_path.resolve().parent}
        size = native_font_size(source.metadata)
        if size:
            options["font_size"] = size
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            data = ink.compile(source.text, **options)
        output.write_bytes(data)
        set_pdf_info(output, source.metadata, verbose, creator="inkmd")
        return [str(item.message) for item in caught]
    import md2pdf
    try:
        config = md2pdf.Config(input_file=str(md_path), output_file=str(output),
                               page_size=native_paper(source.metadata).upper())
    except Exception:  # an unknown paper name falls back to the default
        config = md2pdf.Config(input_file=str(md_path), output_file=str(output))
    with captured_logs("md2pdf") as messages:
        md2pdf.Pipeline(config).run(source.text)
    set_pdf_info(output, {}, verbose, creator="md2pdf (ReportLab)")
    return messages


def convert_native(md_path: Path, output: Path, engines: list[str], metadata_files: list[Path],
                   from_format: str | None, verbose: bool, debug: bool) -> tuple[bool, str]:
    """Markdown -> PDF with the native renderers; (ok, reason)."""
    if md_path.suffix.lower() not in NATIVE_SOURCE_SUFFIXES or (
            from_format is not None and from_format.casefold().split("+")[0] not in NATIVE_READERS):
        raise SystemExit(f"{md_path}: the native renderers read Markdown only; this input needs Pandoc "
                         "(and a LaTeX/Typst/HTML engine, or soffice) -- see `pdfmd --check-dependencies`.")
    text = md_path.read_text(encoding="utf-8-sig")
    attempts: list[str] = []
    prepared: dict[str, tuple[NativeSource, dict[str, int]]] = {}
    for engine in engines:
        prepared[engine] = normalise_gfm(text, engine, metadata_files, md_path.resolve().parent, md_path)
    order = native_order(engines, prepared[engines[0]][0])
    for position, engine in enumerate(order):
        source, counts = prepared[engine]
        try:
            messages = render_native(engine, md_path, source, output, verbose)
        except Exception as error:  # noqa: BLE001 -- try the next renderer, report them all
            if debug:
                import traceback
                traceback.print_exc()
            attempts.append(f"{engine}: {error}")
            if position + 1 < len(order):
                native_note(engine, f"failed ({error}); trying {order[position + 1]}", md_path)
            continue
        print(f"NATIVE  {display_path(md_path)} via {engine}")
        report_messages(engine, messages, md_path)
        describe_native_changes(engine, md_path, source, counts)
        return True, ""
    return False, "native renderers failed:\n  " + "\n  ".join(attempts)


def describe_native_changes(engine: str, md_path: Path, source: NativeSource, counts: dict[str, int]) -> None:
    """One warning per kind of thing the native renderer could not honour."""
    def say(message: str) -> None:
        native_note(engine, message, md_path)

    if counts.get("latex"):
        say(f"{counts['latex']} raw LaTeX block/line(s) removed")
        native_lose("latex", counts["latex"])
    if counts.get("divs"):
        say(f"{counts['divs']} Pandoc fenced-div marker(s) removed (their content is kept)")
    if counts.get("attributes"):
        say(f"{counts['attributes']} heading/image attribute block(s) removed")
    if counts.get("citations"):
        say(f"{counts['citations']} citation(s) left as written (no citation processing without Pandoc)")
        native_lose("citations", counts["citations"])
    if counts.get("footnotes") and engine == "inkmd":
        say(f"{counts['footnotes']} footnote(s) turned into numbered notes at the end")
    if counts.get("math_text"):
        if engine == "inkmd":
            say(f"{counts['math_text']} math expression(s) set as plain text (Unicode, sub/superscripts, "
                "display math centred); inkmd cannot typeset math -- `pdfmd --install math` does")
        else:
            say(f"{counts['math_text']} formula(e) matplotlib cannot read set as plain text")
        native_lose("math", counts["math_text"])
    elif counts.get("math") and engine == "md2pdf" and not matplotlib_available():
        say(f"{counts['math']} math expression(s) need matplotlib or network access (Kroki) -- "
            "`pdfmd --install math` installs matplotlib")
        native_lose("math", counts["math"])
    if source.emoji and engine == "inkmd" and inkmd_emoji_font() is None:
        say("emoji shown as [name] labels (`pdfmd --install emoji` adds the colour emoji font)")
        native_lose("emoji")
    ignored = ignored_front_matter_keys(source.metadata)
    if ignored:
        shown = ", ".join(ignored[:8]) + (", ..." if len(ignored) > 8 else "")
        say(f"front-matter keys not used: {shown}")
        native_lose("keys", len(ignored))


def native_run_note(engines: list[str]) -> None:
    """Printed once when the native tier was chosen automatically."""
    reason = "Pandoc was not found" if not which("pandoc") else "no PDF engine was found"
    print(f"NOTE  {reason}: building with the built-in renderer ({' / '.join(engines)}). "
          "The output is plain -- no LaTeX, preambles, filters or citation processing. "
          "Pandoc plus Typst or TeX gives the full result: `pdfmd --install full`, or "
          "`pdfmd --check-dependencies`.")


def system_install_hint() -> str:
    """How to install Pandoc and Typst with the system's own package manager."""
    if sys.platform == "darwin":
        return "brew install pandoc typst"
    if sys.platform == "win32":
        return "winget install JohnMacFarlane.Pandoc Typst.Typst"
    return ("sudo apt install pandoc (or your package manager), plus Typst from "
            "https://github.com/typst/typst/releases")


def pandoc_install_hint() -> str:
    """How to get Pandoc and Typst: pdfmd's own installer first, then the system way."""
    return f"`pdfmd --install full` (no admin rights needed), or {system_install_hint()}"


def data_root() -> Path:
    """Where pdfmd keeps tools it installs itself (a sibling of cache_root())."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "pdfmd"


def tools_directory() -> Path:
    return data_root() / "bin"


def bundled_pandoc_directory() -> Path | None:
    """The folder of the Pandoc that `pip install pypandoc_binary` brings, if any."""
    try:
        spec = importlib.util.find_spec("pypandoc")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    folder = Path(spec.origin).parent / "files"
    return folder if any((folder / name).is_file() for name in ("pandoc", "pandoc.exe")) else None


def managed_tool_directories() -> list[Path]:
    return [folder for folder in (tools_directory(), bundled_pandoc_directory())
            if folder is not None and folder.is_dir()]


def use_managed_tools() -> None:
    """Make the tools `pdfmd --install` put in place findable, behind whatever the
    user has on PATH (a system Pandoc or Typst always wins over ours)."""
    entries = os.environ.get("PATH", "").split(os.pathsep)
    extra = [str(folder) for folder in managed_tool_directories() if str(folder) not in entries]
    if extra:
        os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), *extra]).strip(os.pathsep)


TYPST_REPOSITORY = "typst/typst"
TYPST_TARGETS = {
    ("linux", "x86_64"): "x86_64-unknown-linux-musl", ("linux", "aarch64"): "aarch64-unknown-linux-musl",
    ("darwin", "x86_64"): "x86_64-apple-darwin", ("darwin", "aarch64"): "aarch64-apple-darwin",
    ("windows", "x86_64"): "x86_64-pc-windows-msvc", ("windows", "aarch64"): "aarch64-pc-windows-msvc",
}


def typst_asset_name(system: str | None = None, machine: str | None = None) -> str | None:
    """The file name of Typst's release archive for this machine, or None."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    target = TYPST_TARGETS.get((system, machine))
    if target is None:
        return None
    return f"typst-{target}.zip" if system == "windows" else f"typst-{target}.tar.xz"


def github_release_asset(repository: str, name: str) -> tuple[str, str | None]:
    """(download URL, SHA-256 or None) of a release asset of the latest release.
    GitHub lists a digest for each asset; without the API (offline, rate limit)
    the stable `latest/download` link is used and nothing can be checked."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"pdfmd/{PDFMD_VERSION}"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        request = urllib.request.Request(f"https://api.github.com/repos/{repository}/releases/latest",
                                         headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)
        for asset in release["assets"]:
            if asset["name"] == name:
                digest = str(asset.get("digest") or "")
                return asset["browser_download_url"], (digest.split(":", 1)[1] if digest.startswith("sha256:") else None)
    except (OSError, ValueError, KeyError):
        pass
    return f"https://github.com/{repository}/releases/latest/download/{name}", None


def download_file(url: str, destination: Path, sha256: str | None) -> None:
    """Download url to destination, refusing a file whose SHA-256 is not the expected one."""
    request = urllib.request.Request(url, headers={"User-Agent": f"pdfmd/{PDFMD_VERSION}"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
        for chunk in iter(lambda: response.read(1 << 20), b""):
            digest.update(chunk)
            handle.write(chunk)
    if sha256 and digest.hexdigest() != sha256.lower():
        destination.unlink(missing_ok=True)
        raise OSError(f"SHA-256 mismatch for {url}: expected {sha256}, got {digest.hexdigest()}")


def extract_executable(archive: Path, wanted: str, destination: Path) -> Path:
    """Write the one file called ``wanted`` out of a .zip / .tar.xz into ``destination``."""
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            member = next((name for name in bundle.namelist() if PurePosixPath(name).name == wanted), None)
            data = bundle.read(member) if member else None
    else:
        with tarfile.open(archive) as bundle:
            found = next((item for item in bundle.getmembers()
                          if item.isfile() and PurePosixPath(item.name).name == wanted), None)
            data = bundle.extractfile(found).read() if found else None
    if data is None:
        raise OSError(f"{wanted} is not in {archive.name}")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / wanted
    temporary = target.with_name(target.name + ".part")
    temporary.write_bytes(data)
    temporary.chmod(0o755)
    temporary.replace(target)
    return target


def install_typst() -> bool:
    """Download Typst's release binary for this machine into tools_directory()."""
    name = typst_asset_name()
    if name is None:
        print(f"No Typst release is listed for {platform.system()} {platform.machine()}; "
              f"see https://github.com/{TYPST_REPOSITORY}/releases", file=sys.stderr)
        return False
    url, sha256 = github_release_asset(TYPST_REPOSITORY, name)
    print(f"INSTALL  typst ({INSTALL_SIZES['typst']}): {url}")
    executable = "typst.exe" if name.endswith(".zip") else "typst"
    try:
        with NamedTemporaryFile(suffix=Path(name).suffix if name.endswith(".zip") else ".tar.xz",
                                delete=False) as temporary:
            archive = Path(temporary.name)
        try:
            download_file(url, archive, sha256)
            print(f"SHA-256 verified ({sha256[:12]}..., as listed by GitHub for this release)" if sha256
                  else "NOTE  no checksum was available for this download, so it could not be verified")
            target = extract_executable(archive, executable, tools_directory())
        finally:
            archive.unlink(missing_ok=True)
    except (OSError, tarfile.TarError, zipfile.BadZipFile, ImportError) as error:
        print(f"Could not install Typst ({error}). Install it yourself: {system_install_hint()}",
              file=sys.stderr)
        return False
    use_managed_tools()
    version = subprocess.run([str(target), "--version"], capture_output=True, text=True)
    if version.returncode != 0:
        print(f"Typst was downloaded to {target} but does not run here: {version.stderr.strip()}",
              file=sys.stderr)
        return False
    print(f"Installed {version.stdout.strip()} in {tools_directory()} "
          "(used when no other Typst is on PATH; delete the file to remove it).")
    return True


def install_extra(kind: str) -> bool:
    """Install an optional piece: pip packages into the Python environment pdfmd runs
    from (math, emoji, pandoc), or Typst's own binary into pdfmd's tools folder."""
    if kind == "full":
        return install_extra("pandoc") and install_extra("typst")
    if kind == "typst":
        return install_typst()
    if kind == "math" and sys.version_info < (3, 11):
        print("pymd2pdf needs Python 3.11 or newer; this is "
              f"{sys.version.split()[0]}. Install pdfmd with a newer Python (pipx install pdfmd-cli).",
              file=sys.stderr)
        return False
    command = [sys.executable, "-m", "pip", "install", *INSTALL_SPECS[kind]]
    print(f"INSTALL  {kind} ({INSTALL_SIZES[kind]}): " + " ".join(shlex.quote(part) for part in command))
    try:
        completed = subprocess.run(command)
    except OSError as error:
        print(f"Could not run pip ({error}).", file=sys.stderr)
        return False
    if completed.returncode != 0:
        print(f'pip failed. Install by hand: pip install "pdfmd-cli[{kind}]"', file=sys.stderr)
        return False
    if kind == "pandoc":
        importlib.invalidate_caches()
        use_managed_tools()
        found = which("pandoc")
        print(f"Installed Pandoc ({found or 'not found on PATH yet'}); "
              "used when no other Pandoc is on PATH.")
    return True


def native_prompt_state() -> Path:
    return cache_root() / "native-prompt-dismissed"


def offer_native_upgrade() -> None:
    """After an automatic native build that lost something, offer the upgrades.

    Interactive terminals only (never in CI, a pipe, or with PDFMD_NO_PROMPT
    set), and never again once the user has chosen to continue as is.
    """
    if (not NATIVE_LOST or os.environ.get("PDFMD_NO_PROMPT") or not sys.stdin.isatty()
            or not sys.stdout.isatty() or native_prompt_state().exists()):
        return
    lost = ", ".join(f"{kind} ({count})" for kind, count in sorted(NATIVE_LOST.items()))
    options: list[tuple[str, str]] = []
    if "math" in NATIVE_LOST and sys.version_info >= (3, 11) \
            and not (md2pdf_available() and matplotlib_available()):
        options.append(("math", f"install md2pdf with math now ({INSTALL_SIZES['math']})"))
    if "emoji" in NATIVE_LOST and inkmd_emoji_font() is None:
        options.append(("emoji", f"install the colour emoji font ({INSTALL_SIZES['emoji']})"))
    if not (which("pandoc") and installed_engines()):
        options.append(("full", f"install Pandoc and Typst now ({INSTALL_SIZES['full']}, into pdfmd's own "
                                "folders, no admin rights) for the full-quality route"))
    options.append(("never", "continue as is and don't ask again"))
    print(f"\nThe native renderer could not render: {lost}.")
    for number, (_, label) in enumerate(options, 1):
        print(f"  {number}) {label}")
    try:
        answer = input("Choose [Enter = continue this time]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not answer.isdigit() or not 1 <= int(answer) <= len(options):
        return
    choice = options[int(answer) - 1][0]
    if choice in INSTALL_KINDS:
        if install_extra(choice):
            print("Installed. Run pdfmd again to use it.")
    else:
        try:
            native_prompt_state().parent.mkdir(parents=True, exist_ok=True)
            native_prompt_state().write_text("dismissed\n", encoding="utf-8")
        except OSError:
            pass


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
    for folder in accessory_directories(directory, document_stem):
        for path in folder.glob("*.tex"):
            name = path.name.casefold()
            if folder.name.endswith(UNPACKED_SUFFIX):
                candidates.append(path)  # a folder --unpack made: every preamble in it is this document's
                continue
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
                          typst_engine: bool = False, doc_count: int = 1,
                          drop_embedded_preamble: bool = False) -> Iterator[list[Path]]:
    """Yield temporary, corrected inputs for LaTeX-family renders when
    needed -- or, with `typst_engine` instead, to make a margin setting
    written for the OTHER engine family reach Typst's own template (see
    fix_typst_margin()). The two are mutually exclusive; at most one
    corrector ever applies to a given render, same as `latex_engine` alone
    before this.

    `paths[:doc_count]` are the main document(s) being rendered -- a
    single `title_source` everywhere except report/book mode, where every
    chapter file counts (``doc_count=len(files)``, passed explicitly by
    those two call sites; every other call site keeps the default of 1).
    Every path after that is a linked --metadata-file, which Pandoc
    accepts EITHER fenced (``---``/``...``-delimited, same as a
    document's own front matter) OR completely bare (no delimiters at
    all -- see the Pandoc manual's own "metadata file" section).
    fix_typst_margin() is told which is which (`is_metadata`) so it can
    safely treat a bare metadata file as pure YAML, while a bare MAIN
    DOCUMENT (no delimiters at all) is definitely markdown body text,
    never YAML, and is always left alone regardless.
    """
    temporary_paths: list[Path] = []
    prepared: list[Path] = []
    try:
        for index, path in enumerate(paths):
            original = text = path.read_text(encoding="utf-8-sig")
            if drop_embedded_preamble and index < doc_count:
                # A target that is not LaTeX-family gets no embedded LaTeX preamble.
                text = strip_embedded_preamble(text)
            if latex_engine:
                corrected = wrap_latex_header_includes(text)
            elif typst_engine:
                corrected = fix_typst_margin(text, is_metadata=(index >= doc_count))
            else:
                corrected = text
            if corrected == original:
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
        definitions = document_latex_definitions(md_path)
        includes = document_header_includes(md_path.read_text(encoding="utf-8-sig")) or ""
        if PREAMBLE_END_MARK in includes:
            # An embedded preamble (see EMBED_KINDS): definitions go after it.
            head, _, tail = includes.partition(PREAMBLE_END_MARK)
            parts = [head.rstrip("\n"), definitions, tail.lstrip("\n")]
        else:
            parts = [definitions, includes]
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
    directories: list[Path] = accessory_directories(md_path.parent, md_path.stem)
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
    unpacked = md_path.parent / f"{md_path.stem}{UNPACKED_SUFFIX}"
    if unpacked.is_dir():
        for candidate in sorted(unpacked.glob("*.lua"), key=lambda item: natural_key(item.name)):
            if candidate.resolve() not in seen:
                seen.add(candidate.resolve())
                found.append(candidate.resolve())
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
        ("yu", "ю"), ("ya", "я"), ("ai", "ай"), ("oi", "ой"), ("oy", "ой"),
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


# --- Finding a document by something other than its exact file name (v3.21.0) -
#
# find_markdown() keeps its exact rules first (an existing path, a wildcard, a
# case-insensitive stem, the Latin/Cyrillic spellings of it, "Пробный <name>").
# Only when all of those fail does it fall through to the tiers below, which
# compare *keys* instead of names, so `animportantdocument` finds
# "An Important Document.md", `glyukoza` finds a document titled "Глюкоза", and
# `animp` (announced with a WARN) finds the first of those by its start.
#
# A key keeps letters and digits only (case, spaces, `_`, `-`, `.`, `:` and
# every other separator are gone, and so are accents) and writes Cyrillic in
# Latin letters. It comes in two strengths: STRICT is a plain transliteration
# (Latin ş = Cyrillic ш = "sh"), LOOSE also merges letters people swap when they
# type a name in the other script (c/k/q, i/y/j, v/w, ё/е, ...).

FUZZY_LOOKUP = True        # main() clears it for --no-auto lookup
LOOKUP_MIN_PREFIX = 3      # a shorter start is too likely to be an accident
LOOKUP_SCAN_LIMIT = 500    # Markdown files whose front matter is read
LOOKUP_HEAD_BYTES = 65536

# Russian, Ukrainian, Belarusian and Kazakh Cyrillic. Kazakh қ = q, ғ = g,
# ң = n, ә = a, ө = o, ұ and ү = u, һ = h, і = i.
CYRILLIC_STRICT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "є": "ye", "і": "i", "ї": "yi", "ґ": "g", "ў": "u",
    "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h",
}
# The loose key starts from the same transliteration, with ё read as е; the
# Latin letters it produces are then merged (see lookup_key).
CYRILLIC_LOOSE = {**CYRILLIC_STRICT, "ё": "e"}
# Latin letters NFKD cannot take apart, spelt the way the Cyrillic sound is.
LATIN_EXTRA = {"ş": "sh", "š": "sh", "ç": "ch", "č": "ch", "ž": "zh", "ğ": "g", "ı": "i",
               "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "đ": "d", "ł": "l"}


@lru_cache(maxsize=None)
def lookup_key(text: str, loose: bool = False, y: str = "i", w: str = "v") -> str:
    """The comparison key of a name, title or heading (see the block comment
    above). A loose key then merges what people swap when typing a name in the
    other script or on a keyboard without the letter: sh/sch/shch/ş/ш/щ = s,
    zh/ž/ж = z, ch/ç/ч = k, kh/х = h, c/q/k/қ = k, j/y = i (nothing before a
    vowel: ю = yu = u), w/v = v, x = ks, and a doubled letter is one. ``y``/``w`` choose what a Latin y or w stands
    for: у is written y in some Kazakh Latin spellings and w in others, so a
    query tries both (lookup_query_keys) where a stored name has no choice."""
    text = unicodedata.normalize("NFKC", text).casefold()
    table = CYRILLIC_LOOSE if loose else CYRILLIC_STRICT
    text = "".join(table.get(letter, LATIN_EXTRA.get(letter, letter)) for letter in text)
    letters = "".join(letter for letter in unicodedata.normalize("NFKD", text) if letter.isalnum())
    if not loose:
        return letters
    for digraph, merged in (("shch", "s"), ("sch", "s"), ("sh", "s"), ("zh", "z"), ("ch", "k"), ("kh", "h")):
        letters = letters.replace(digraph, merged)
    letters = re.sub(r"[yj](?=[aeiou])", "", letters)   # ю/я/ё/є: yu, ya, yo, ye ~ u, a, o, e
    letters = letters.translate(str.maketrans({"c": "k", "q": "k", "j": "i", "x": "ks", "y": y, "w": w}))
    return re.sub(r"(.)\1+", r"\1", letters)


def lookup_query_keys(query: str) -> tuple[str, set[str]]:
    """(strict key, every loose key) of what the user typed."""
    loose = {lookup_key(query, True, y, w) for y in ("i", "u") for w in ("v", "u")}
    return lookup_key(query), loose


class LookupAmbiguous(FileNotFoundError):
    """A name that fits several documents equally well. A FileNotFoundError so
    every caller that already handles a missing document handles this; callers
    that would swallow it as "no document" catch this one first."""


# (strength, fields compared, how) in order of preference: the first tier with
# a hit decides, two hits in it are an error. A file name or an alias is
# preferred to a title at every step, and exact to a start to a word. The same
# tiers rank headings (an explicit {#id} counts as an alias, the heading text as
# the name), so `doc#onlyapart` and `pdfmd onlyapart` agree about spelling.
LOOKUP_TIERS = (
    ("strict", ("alias",), "exact"),
    ("strict", ("stem",), "exact"),
    ("strict", ("title",), "exact"),
    ("loose", ("alias",), "exact"),
    ("loose", ("stem",), "exact"),
    ("loose", ("title",), "exact"),
    ("strict", ("alias", "stem"), "start"),
    ("strict", ("title",), "start"),
    ("loose", ("alias", "stem"), "start"),
    ("loose", ("title",), "start"),
    ("strict", ("alias", "stem", "title"), "word"),
    ("loose", ("alias", "stem", "title"), "word"),
)
LOOKUP_FIELD_WORDS = {"alias": "alias", "stem": "file name", "title": "title"}
HEADING_FIELD_WORDS = {"alias": "{#id}", "stem": "heading text"}


def lookup_wording(tier: tuple, words: dict) -> str | None:
    """What to say a guessed match matched on; None for an exact one that only
    differs in case, separators and script (strict exact tiers)."""
    strength, fields, how = tier
    if strength == "strict" and how == "exact":
        return None
    names = " or ".join(words[field] for field in fields if field in words)
    phrase = {"exact": f"spelt differently from its {names}", "start": f"the start of its {names}",
              "word": f"the start of a word in its {names}"}[how]
    return phrase + (", spelt differently" if strength == "loose" and how != "exact" else "")


def lookup_field_matches(strength: str, how: str, queries: tuple[str, set[str]], text: str) -> bool:
    loose = strength == "loose"
    wanted = queries[1] if loose else {queries[0]}
    if how == "exact":
        return lookup_key(text, loose) in wanted
    wanted = {key for key in wanted if len(key) >= LOOKUP_MIN_PREFIX}
    if not wanted:
        return False
    if how == "start":
        return lookup_key(text, loose).startswith(tuple(wanted))
    words = re.split(r"[\W_]+", text)
    return any(lookup_key(" ".join(words[index:]), loose).startswith(tuple(wanted))
               for index in range(1, len(words)))


def rank_lookup(query: str, entries: list[tuple], describe=None, words: dict = LOOKUP_FIELD_WORDS,
                tiers: tuple = LOOKUP_TIERS):
    """Choose among ``entries`` -- (key, [(field, text)]) with field one of
    alias/stem/title -- by LOOKUP_TIERS. Returns (key, tier, field, text), or
    None; raises LookupAmbiguous when the best tier holds several entries.
    ``describe`` names an entry's key in that error (default: a file path)."""
    describe = describe or display_path
    queries = lookup_query_keys(query)
    if not queries[0]:
        return None
    for tier in tiers:
        strength, fields, how = tier
        hits: dict = {}
        for key, texts in entries:
            for field, text in texts:
                if field in fields and key not in hits and lookup_field_matches(strength, how, queries, text):
                    hits[key] = (field, text)
        if len(hits) == 1:
            key, (field, text) = next(iter(hits.items()))
            return key, tier, field, text
        if hits:
            names = ", ".join(f"{describe(key)} ({words[field]} '{text}')"
                              for key, (field, text) in sorted(hits.items()))
            raise LookupAmbiguous(f"'{query}' fits several equally well: {names}. "
                                  "Name one of them more exactly.")
    return None


def lookup_fields(path: Path) -> list[tuple[str, str]]:
    """What a document can be found by: its file name, its title (front matter
    `title:`, or a `% title` line) and its aliases (`pdfmd-options: {alias: ...}`,
    one name or a list; a bare top-level `pdfmd-title:` is accepted too)."""
    fields = [("stem", path.stem)]
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
            head = handle.read(LOOKUP_HEAD_BYTES)
    except OSError:
        return fields
    title: object = None
    aliases: list = []
    front = re.match(r"^---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", head, re.DOTALL)
    if front:
        data = None
        if yaml is not None:
            try:
                data = yaml.safe_load(front.group(1))
            except yaml.YAMLError:
                data = None
        if isinstance(data, dict):
            title = data.get("title")
            options = data.get("pdfmd-options")
            options = options if isinstance(options, dict) else {}
            for value in (options.get("alias"), options.get("aliases"), data.get("pdfmd-title")):
                aliases += value if isinstance(value, list) else [value]
        else:
            for key in ("title", "pdfmd-title"):
                found = re.search(rf"^{key}\s*:\s*(.+?)\s*$", front.group(1), re.MULTILINE)
                if found:
                    value = found.group(1).strip("'\"")
                    if key == "title":
                        title = value
                    else:
                        aliases.append(value)
    elif head.startswith("% "):
        title = head.split("\n", 1)[0][2:]
    if isinstance(title, (str, int, float)) and not isinstance(title, bool) and str(title).strip():
        fields.append(("title", str(title).strip()))
    fields += [("alias", str(alias).strip()) for alias in aliases
               if isinstance(alias, (str, int, float)) and not isinstance(alias, bool) and str(alias).strip()]
    return fields


def lookup_entries(directory: Path, recursive: bool) -> list[tuple[Path, list[tuple[str, str]]]]:
    folders = [directory] + ([item for item in directory.rglob("*") if item.is_dir()] if recursive else [])
    files = sorted(file for folder in folders for file in folder.glob("*.md")
                   if not file.name.startswith(".") and file.is_file())
    return [(file, lookup_fields(file)) for file in files[:LOOKUP_SCAN_LIMIT]]


_LOOKUP_ANNOUNCED: set[tuple[str, str]] = set()


def announce_lookup(query: str, shown: str, tier: tuple, field: str, text: str,
                    words: dict = LOOKUP_FIELD_WORDS, subject: str = "file name") -> None:
    """Say, once per run, that something was found by other than its exact
    name: a plain AUTO line when only case, separators and script differ, a
    WARN for anything that guessed (a start, a word, a looser spelling)."""
    if (query, shown) in _LOOKUP_ANNOUNCED:
        return
    _LOOKUP_ANNOUNCED.add((query, shown))
    what = "file name" if field == "stem" and subject == "file name" else f"{words[field]} '{text}'"
    wording = lookup_wording(tier, words)
    if wording is None:
        # Naming a heading without its exact case or spaces is the normal way to
        # ask for one; only a file name found that way is worth a line.
        if subject == "file name":
            print(f"AUTO MD    {shown}  ('{query}' = its {what}, ignoring case, spaces and punctuation)")
        return
    print(f"WARN  '{query}' is not a {subject}; using {shown} ({wording}: {what}). "
          "Name it exactly, or pass --no-auto lookup, to stop pdfmd guessing.", file=sys.stderr)


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
    if FUZZY_LOOKUP and requested and not value.is_dir():
        fuzzy_directory = value.parent if value.parent.is_dir() and str(value.parent) != "." else Path.cwd()
        found = rank_lookup(requested, lookup_entries(fuzzy_directory, recursive))
        if found:
            announce_lookup(requested, display_path(found[0]), *found[1:])
            return found[0].resolve()
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


# Shared by frontmatter_margin_geometry_options() and fix_typst_margin()
# below to translate a margin setting written for ONE engine family into
# the variable the OTHER one actually reads -- geometry: (LaTeX) and
# margin: (Typst) each mean nothing at all to the other's template, so a
# document written/tested against one engine silently loses its margin
# the moment it's rendered through the other (has_geometry() already
# stops pdfmd's own DEFAULT_MARGIN from stepping on either, which is
# correct, but does nothing to make the document's OWN setting reach the
# engine that can't read it natively). Both directions normalize through
# one canonical shape: a {top, bottom, left, right} dict of raw dimension
# strings, physical sides only -- Typst's binding-aware `inside`/`outside`
# and `rest` have no LaTeX equivalent at all, so a `margin:` mapping using
# any of those three is left completely alone rather than guessed at.
MARGIN_SIDE_ALIASES = {
    "x": ("left", "right"),
    "y": ("top", "bottom"),
    "top": ("top",),
    "bottom": ("bottom",),
    "left": ("left",),
    "right": ("right",),
}

# geometry package option names -- includes the older t/b/l/r-margin
# spellings alongside the more common ones actually seen in practice.
GEOMETRY_SIDE_ALIASES = {
    "margin": ("top", "bottom", "left", "right"),
    "hmargin": ("left", "right"),
    "vmargin": ("top", "bottom"),
    "top": ("top",), "tmargin": ("top",),
    "bottom": ("bottom",), "bmargin": ("bottom",),
    "left": ("left",), "lmargin": ("left",),
    "right": ("right",), "rmargin": ("right",),
}


def parse_margin_sides(value) -> dict[str, str] | None:
    """Normalize a parsed (via PyYAML) Typst-shaped ``margin:`` value into
    a ``{top, bottom, left, right}`` dict of raw dimension strings -- or
    None when `value` is a scalar-shaped None/absent, or a mapping that
    uses ``inside``/``outside``/``rest`` (Typst's own binding-aware
    margins, with no LaTeX equivalent) or any other key this doesn't
    recognize, or isn't a scalar or mapping at all.

    A scalar (already the case fix_typst_margin() itself exists to
    correct on the Typst side) is uniform on all four sides.
    """
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        side_value = str(value)
        return {"top": side_value, "bottom": side_value, "left": side_value, "right": side_value}
    if not isinstance(value, dict):
        return None
    sides: dict[str, str] = {}
    for key, side_value in value.items():
        aliases = MARGIN_SIDE_ALIASES.get(str(key).strip().casefold())
        if not aliases:
            return None
        for side in aliases:
            sides[side] = str(side_value)
    return sides or None


def parse_geometry_sides(value) -> dict[str, str] | None:
    """Normalize a parsed (via PyYAML) ``geometry:`` value -- a bare
    "key=val" scalar, a comma-joined "key=val,key=val" scalar, or a YAML
    list of such strings, the three shapes Pandoc's own LaTeX template
    accepts -- into a ``{top, bottom, left, right}`` dict of raw dimension
    strings, or None when it contains anything this can't safely
    interpret: an option with no ``key=`` at all, or a key that isn't
    about a margin (``includehead``, ``showframe``, ...) -- the geometry
    package has many options that aren't page margins, and guessing wrong
    on those would be worse than leaving Typst's own defaults in place.
    """
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        items = value
    else:
        return None
    sides: dict[str, str] = {}
    for item in items:
        for part in item.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                return None
            key, _, side_value = part.partition("=")
            aliases = GEOMETRY_SIDE_ALIASES.get(key.strip().casefold())
            if not aliases:
                return None
            for side in aliases:
                sides[side] = side_value.strip()
    return sides or None


def sides_to_geometry_options(sides: dict[str, str]) -> list[str]:
    """Format a {top,bottom,left,right} dict as the geometry: option list
    Pandoc's LaTeX template expects -- collapsed to one ``margin=...``
    when all four sides given are equal, one option per side otherwise
    (only the sides actually present -- a mapping that only set ``x:``
    leaves top/bottom to LaTeX's own default, same as it would for Typst).
    """
    if len(sides) == 4 and len(set(sides.values())) == 1:
        return [f"margin={next(iter(sides.values()))}"]
    return [f"{side}={sides[side]}" for side in ("top", "bottom", "left", "right") if side in sides]


def frontmatter_margin_geometry_options(md_path: Path, variables: list[str],
                                        metadata_files: list[Path] = ()) -> list[str] | None:
    """Return the geometry: option list a document's own (or a linked
    --metadata-file's) ``margin:`` value translates to for LaTeX-family
    engines -- or None when there's nothing to translate.

    ``margin:`` is a real Pandoc variable for the TYPST template only (see
    fix_typst_margin() below) -- Pandoc's LaTeX template never reads it at
    all, only ``geometry:`` does. has_geometry() already treats a bare
    ``margin:`` (in the document's own front matter OR a metadata file --
    it checks both) as "a margin setting exists" (correctly, so
    DEFAULT_MARGIN isn't injected on top of it), but nothing translated
    that value into the one variable LaTeX's own template actually
    consumes -- so a document with ONLY ``margin: 2.54cm`` (or a
    ``top:``/``bottom:``/``left:``/``right:``/``x:``/``y:`` breakdown) and
    no ``geometry:`` silently kept LaTeX's own much wider article-class
    default margins on every LaTeX-family engine, the requested value
    never taking effect at all -- confirmed directly (2026-09-28) alongside
    the Typst-side bug the scalar case triggers (see fix_typst_margin()).

    Same precedence pdf-engine resolution uses (see
    frontmatter_pdfmd_options()'s callers): the document's own front
    matter is checked first; if it sets no ``margin:`` at all, each
    linked --metadata-file is checked next, in order, so a shared
    metadata.yaml can set ``margin:`` once for every document that finds
    it -- leaving it out entirely, the way this function's own first
    version did, meant a document with margin ONLY in a shared metadata
    file lost it silently on both engine families at once, worse than the
    bug this function exists to fix. A real ``geometry:`` anywhere -- the
    document's own front matter, any metadata file, or -V -- always wins,
    untouched, checked before any ``margin:`` in any source, same as
    has_geometry().

    Returns None when: no ``margin:`` in any source; a real ``geometry:``
    is set anywhere; PyYAML isn't installed (falls back to the
    scalar-only regex this function used before parse_margin_sides()
    existed, since a real parse is needed for the mapping case -- checked
    per source, same order); or every ``margin:`` found uses Typst's
    ``inside``/``outside``/``rest`` keys, which have no LaTeX equivalent
    (see parse_margin_sides()).
    """
    if any(variable.startswith(("geometry=", "geometry:")) for variable in variables):
        return None
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    blocks = [front_matter.group(1)] if front_matter else []
    for metadata_file in metadata_files:
        meta_text = metadata_file.read_text(encoding="utf-8-sig")
        # A --metadata-file may be fenced (---...---, same as front matter)
        # or completely bare -- Pandoc accepts either. yaml.safe_load()
        # chokes on the fenced shape as-is (a second "---" reads as a
        # second YAML document, "expected a single document in the
        # stream"), so unwrap it the same way md_path's own front matter
        # is, and only fall back to the raw text when it isn't fenced.
        meta_front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", meta_text, re.DOTALL)
        blocks.append(meta_front_matter.group(1) if meta_front_matter else meta_text)
    if any(re.search(r"^geometry\s*:", block, re.MULTILINE) for block in blocks):
        return None
    for block in blocks:
        if yaml is None:
            match = re.search(r"^margin\s*:[ \t]*(\S.*?)[ \t]*$", block, re.MULTILINE)
            if not match:
                continue
            value = match.group(1).strip().strip("'\"")
            return [f"margin={value}"] if value else None
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict) or "margin" not in data:
            continue
        sides = parse_margin_sides(data["margin"])
        return sides_to_geometry_options(sides) if sides else None
    return None


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


def sides_to_typst_margin_yaml(sides: dict[str, str], indent: str, newline: str) -> str:
    """Format a {top,bottom,left,right} dict as the YAML ``margin:``
    mapping Pandoc's Typst template needs -- collapsed to ``x:``/``y:``
    when all four sides given are equal, one line per side otherwise
    (only the sides actually present, in a fixed top/bottom/left/right
    order for a stable, readable rewrite)."""
    if len(sides) == 4 and len(set(sides.values())) == 1:
        value = next(iter(sides.values()))
        return f"{indent}margin:{newline}{indent}  x: {value}{newline}{indent}  y: {value}"
    lines = [f"{indent}margin:"]
    lines += [f"{indent}  {side}: {sides[side]}" for side in ("top", "bottom", "left", "right")
             if side in sides]
    return newline.join(lines)


def fix_typst_margin(text: str, is_metadata: bool = False) -> str:
    """Make a document's or linked --metadata-file's own page-margin
    setting reach Pandoc's Typst template, whichever engine family it was
    actually written for.

    Two distinct problems, both from the same root cause -- ``margin:``
    is a real Pandoc variable for the TYPST template only, and
    ``geometry:`` for the LATEX template only, neither reads the other's
    key at all:

    1. A bare scalar ``margin:`` (``margin: 2.54cm``) is rewritten into
       the ``x:``/``y:`` mapping Typst's template requires -- it always
       renders margin as ``($for(margin/pairs)$...$endfor$)``, iterating
       key/value PAIRS a scalar has none of, so it comes out as the
       literal, invalid ``margin: (: ,)``: a Typst syntax error
       ("unexpected comma") instead of a page margin. Confirmed directly
       (2026-09-28): a document with ``margin: 2.54cm`` and
       ``pdfmd-options: {engine: typst}`` failed outright with exactly
       that error, while rendering fine (albeit at the WRONG margin --
       see frontmatter_margin_geometry_options()) on every LaTeX-family
       engine.

    2. A document with ONLY a ``geometry:`` (no ``margin:`` at all) --
       written for and tested against a LaTeX-family engine -- reaches
       Typst with no margin variable set at all: Typst's template never
       reads ``geometry:``, so it silently falls back to its own built-in
       default (1.25in) instead of erroring, the same "wrong margin, no
       warning" failure frontmatter_margin_geometry_options() fixes in the
       other direction. Parsed via parse_geometry_sides() and added as a
       new ``margin:`` mapping -- ``geometry:`` itself is left in place;
       it's inert for Typst, not harmful.

    Neither fix touches a ``margin:`` that's already a YAML mapping --
    Pandoc's ``/pairs`` filter already turns that straight into valid
    Typst key/value pairs, and it may use Typst's own ``inside``/
    ``outside``/``rest`` keys, which parse_margin_sides() can't safely
    reinterpret but Typst's own template needs no help with anyway.

    `is_metadata` marks a linked --metadata-file (passed by
    prepared_latex_inputs() using its own `doc_count`), which Pandoc
    accepts EITHER fenced (front-matter-shaped, handled the same as a
    document below) OR completely bare -- no ``---``/``...`` delimiters
    at all, just the YAML directly. A bare MAIN document (`is_metadata`
    False) is always left alone instead: with no front matter at all,
    that's markdown BODY text, never YAML, and must never be parsed as
    such.
    """
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if front_matter:
        block = front_matter.group(1)
        prefix = text[:front_matter.start(1)]
        suffix = text[front_matter.end(1):]
    elif is_metadata:
        block = text
        prefix = ""
        suffix = ""
    else:
        return text
    newline = "\r\n" if "\r\n" in block else "\n"

    if yaml is not None:
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            data = None
        if isinstance(data, dict) and "margin" not in data and "geometry" in data:
            sides = parse_geometry_sides(data["geometry"])
            if not sides:
                return text
            insertion = sides_to_typst_margin_yaml(sides, "", newline) + newline
            return prefix + insertion + block + suffix
        if isinstance(data, dict) and isinstance(data.get("margin"), dict):
            return text  # already a mapping -- Typst's template handles it as-is

    def replace(match: re.Match) -> str:
        value = match.group("val").strip().strip("'\"")
        if not value or value.startswith(("{", "[")):
            return match.group(0)
        indent = match.group("indent")
        return f"{indent}margin:{newline}{indent}  x: {value}{newline}{indent}  y: {value}"

    fixed_block = TYPST_MARGIN_RE.sub(replace, block, count=1)
    if fixed_block == block:
        return text
    return prefix + fixed_block + suffix


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
    text = EMBED_BLOCK_RE.sub("", text)  # an embedded block's own fence is not code
    return "`" in text or bool(re.search(r"(?m)^\s{0,3}~~~", text))


def missing_glyph_warning(output: str) -> bool:
    return bool(re.search(
        r"missing character|Missing character|Unicode character .* not set|font .* not found",
        output,
    ))


def contains_citations(md_path: Path) -> bool:
    """Detect bracketed, bare, and suppress-citation Pandoc syntax."""
    text = EMBED_BLOCK_RE.sub("", md_path.read_text(encoding="utf-8-sig"))
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
    text = EMBED_BLOCK_RE.sub("", md_path.read_text(encoding="utf-8-sig"))
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
    return bool(re.search(r"(?m)^:[ \t]", EMBED_BLOCK_RE.sub("", text)))


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
    if EMBED_BLOCK_RE.search(text) and is_assembled_text(text):
        # Embedded `{=pdfmd}` blocks need Pandoc's own markdown: gfm would
        # print them as code blocks.
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


def option_names(options: dict, kind: str) -> list[str]:
    """File names a ``pdfmd-options`` block gives for ``kind`` -- ``yaml``
    (metadata files), ``preamble`` or ``lua-filter`` -- written flat or
    grouped under ``metadata:``::

        pdfmd-options:
          yaml: [a.yaml]          # also `metadata: a.yaml` (a name or a list)
          preamble: p.tex
          lua-filter: f.lua
          metadata:               # the same, grouped
            yaml: [a.yaml]
            preamble: p.tex
            lua-filter: f.lua     # (`lua:` is accepted too)

    Both spellings add up; a name given twice counts once."""
    names: list[str] = []

    def add(value) -> None:
        for item in ([value] if isinstance(value, str) else value if isinstance(value, list) else []):
            if str(item) not in names:
                names.append(str(item))

    add(options.get(kind))
    grouped = options.get("metadata")
    if isinstance(grouped, dict):
        keys = {"yaml": ("yaml", "metadata"), "preamble": ("preamble",),
                "lua-filter": ("lua-filter", "lua")}[kind]
        for key in keys:
            add(grouped.get(key))
    elif kind == "yaml":
        add(grouped)
    return names


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
    names = option_names(frontmatter_pdfmd_options(md_path), "preamble")
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
    names = option_names(frontmatter_pdfmd_options(md_path), "lua-filter")
    resolved = []
    for name in names:
        path = (md_path.parent / name).resolve()
        if not path.is_file():
            if is_assembled_document(md_path):
                # --lua-mode ref: the file names the filter, the filter may
                # not be where it was; build without it rather than stop.
                print(f"WARN  {display_path(md_path)}: the Lua filter it names, {name!r}, was not found "
                      f"at {path}; building without it", file=sys.stderr)
                continue
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
    match = BUILD_NOTES_RE.search(mask_embedded_blocks(text))
    if not match:
        indent = "     "
        block = f"<!-- {'=' * 60}\n{indent}BUILD NOTES\n\n{indent}{new_line}\n{indent}{'=' * 60} -->\n"
        embedded = EMBED_BLOCK_RE.search(text)
        if embedded:
            # Embedded filters stay the last thing in the file.
            return (text[:embedded.start()].rstrip("\n") + "\n\n" + block + "\n"
                    + text[embedded.start():]), None
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


def stamp_unless_partial(partial: bool, *args, **kwargs) -> None:
    """stamp_after_success, except for a partial parts-mode build: that isn't
    the report, so it shouldn't write a provenance note claiming it is."""
    if not partial:
        stamp_after_success(*args, **kwargs)


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
                # Credit pdfmd in /Creator, appended in pandoc's own
                # "<tool> via <wrapper>" order ("LaTeX via pandoc" -> "LaTeX
                # via pandoc via pdfmd-cli"; "Typst 0.15.1" -> "Typst 0.15.1
                # via pdfmd-cli"). Named by its PyPI distribution name so it
                # is searchable; the version is already in PdfmdVersions.
                # Idempotent (a re-stamp doesn't append twice).
                creator = str(existing.get("/Creator") or "").strip()
                if not creator.endswith("pdfmd-cli"):
                    existing["/Creator"] = f"{creator} via pdfmd-cli" if creator else "pdfmd-cli"
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
            # Absolute: Pandoc runs inside the first metadata file's own
            # folder (pandoc_cwd), where a path relative to ours (`-y
            # cfg/x.yaml`) would no longer lead anywhere.
            return Path(os.path.abspath(candidate))
    raise FileNotFoundError(f"Metadata file not found: {value}")


def find_metadata(directory: Path, requested: list[str] | None, report: bool = False,
                  document_class: str | None = None,
                  document_stem: str | None = None) -> Path | list[Path] | object | None:
    """Choose metadata files, supporting explicit stacks and automatic discovery."""
    if requested == []:
        return AUTO_METADATA_DISABLED
    search_dirs = accessory_directories(directory, document_stem)
    if requested is None and document_stem:
        unpacked = directory / f"{document_stem}{UNPACKED_SUFFIX}"
        unpacked_yaml = (sorted([*unpacked.glob("*.yaml"), *unpacked.glob("*.yml")],
                                key=lambda item: natural_key(item.name)) if unpacked.is_dir() else [])
        if unpacked_yaml:
            # The folder --unpack made for this document holds ITS metadata,
            # in the order it was merged in: nothing else is guessed at.
            return order_metadata(unpacked_yaml)
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


# -- Parts (split-file) mode ------------------------------------------------
# A long article-style document (a lab report) kept as one scaffold file --
# front matter only, e.g. report.md -- plus a folder of parts beside it
# (parts/ or sections/), each part a plain Markdown file that starts with its
# own heading. The feature is OFF unless a `pdfmd-options: {parts: auto}` (or
# `parts: <folder>`) is set, in the document's own front matter or -- the
# intended place, so the content files carry no typesetting -- in a linked
# metadata.yaml. With `auto`, a document is a scaffold only if one of
# PARTS_DIR_ALIASES exists beside it, so every other document builds exactly
# as before. A build joins the scaffold and every part in filename order
# (numeric runs compare as numbers: 2-x before 10-y) into one Pandoc run --
# the same single invocation -r/--report makes -- so labels, citations and
# numbering behave as in one file. Paths inside parts stay relative to the
# scaffold's folder (pandoc_cwd and TEXINPUTS already point there), so
# splitting a monolith is a pure cut-and-paste.
PARTS_DIR_ALIASES = ("parts", "sections")
# Handed to Pandoc on a partial build, so a Lua filter that assumes the whole
# document (nulabreport's `moved` blocks need the Appendix) can degrade
# instead of failing: `pdfmd-partial` is true in the document's metadata.
PARTIAL_METADATA = ["-M", "pdfmd-partial=true"]
PARTIAL_KEY = "pdfmd-partial"
PARTS_SKIP_DIRS = frozenset({"backup", "backups"})
PARTS_ON = {"true", "yes", "on", "auto"}
PARTS_OFF = {"false", "no", "off", "none"}


def parts_setting(md_path: Path, metadata_files: list[Path]) -> str | None:
    """The effective ``pdfmd-options.parts`` value: None (off), "auto", or a
    folder name. The document's own front matter wins over the metadata
    files, in find_metadata's order -- same precedence as frontmatter_engine.
    An assembled file (--stop-at markdown) is never a scaffold: it already
    holds the parts.
    """
    if is_assembled_document(md_path):
        return None
    sources = [frontmatter_pdfmd_options(md_path)]
    for metadata_file in metadata_files:
        options = metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append(options if isinstance(options, dict) else {})
    for options in sources:
        if "parts" not in options:
            continue
        value = options["parts"]
        text = str(value).strip().casefold()
        if value is False or text in PARTS_OFF:
            return None
        if value is True or text in PARTS_ON:
            return "auto"
        return str(value).strip()
    return None


def parts_directory(scaffold: Path, setting: str) -> Path | None:
    if setting == "auto":
        for name in PARTS_DIR_ALIASES:
            if (scaffold.parent / name).is_dir():
                return (scaffold.parent / name).resolve()
        return None
    directory = scaffold.parent / setting
    if not directory.is_dir():
        raise SystemExit(f"{display_path(scaffold)}: pdfmd-options.parts names '{setting}', "
                         f"but {display_path(directory)} is not a folder")
    return directory.resolve()


def natural_key(name: str) -> list:
    """Sort key where digit runs compare as numbers (2-x < 10-y)."""
    return [int(piece) if index % 2 else piece.casefold()
            for index, piece in enumerate(re.split(r"(\d+)", name))]


def collect_parts(directory: Path) -> list[Path]:
    """Every part under ``directory`` in document order. Subfolders are
    walked (a folder is a part made of several files); names starting with
    ``.`` or ``_`` are skipped, so ``_scratch.md`` is a place to park notes
    and pdfmd's own hidden temp files never count; so are backup folders.
    """
    found: list[Path] = []
    for entry in sorted(directory.iterdir(), key=lambda item: natural_key(item.name)):
        if entry.name.startswith((".", "_")):
            continue
        if entry.is_dir():
            if entry.name.casefold() not in PARTS_SKIP_DIRS:
                found.extend(collect_parts(entry))
        elif entry.suffix.lower() == ".md":
            found.append(entry.resolve())
    return found


def part_slug(component: str) -> str:
    """'10-introduction' -> 'introduction' (a leading number and separator
    are ordering, not naming)."""
    return re.sub(r"^\d+[-_. ]*", "", component) or component


def part_keys(relative: Path) -> tuple[set[str], set[str]]:
    """(exact keys, slug keys) a --section request may use for this part:
    the file, each folder above it, with or without the numeric prefix, and
    a top-level component's bare number.
    """
    components = list(relative.parts)
    components[-1] = Path(components[-1]).stem
    exact: set[str] = set()
    slugs: set[str] = set()
    for depth in range(len(components)):
        chain = components[:depth + 1]
        exact.add("/".join(chain).casefold())
        exact.add(chain[-1].casefold())
        slug_chain = [part_slug(item) for item in chain]
        slugs.add("/".join(slug_chain).casefold())
        slugs.add(slug_chain[-1].casefold())
        number = re.match(r"\d+", chain[-1])
        if number and depth == 0:
            exact.update({number.group(0), number.group(0).lstrip("0") or "0"})
    return exact, slugs


# A heading of a Markdown body (scan_headings): `line` is 0-based and of its text,
# `end` the line its section ends before.
Heading = namedtuple("Heading", "line level text ids end")   # line: 0-based, of the heading's text


class NoPartMatches(SystemExit):
    """A --section name that is no part's name (it may still be a heading inside one)."""


class NoHeadingMatches(SystemExit):
    """A --section name that is no heading's name."""


def select_parts(parts: list[Path], directory: Path, requests: list[str]) -> list[Path]:
    """The parts matching any request, in document order. A request matches
    a file name, its name without the numeric prefix, a folder (all parts
    inside), or a top-level number; failing an exact match, a unique prefix
    of a name. Unknown or ambiguous requests are an error that lists the
    choices -- a typo must never silently build the wrong section.
    """
    keyed = {part: part_keys(part.relative_to(directory)) for part in parts}
    chosen: set[Path] = set()
    for request in requests:
        wanted = request.strip().casefold().removesuffix(".md")
        if not wanted:
            continue
        hits = [part for part, (exact, slugs) in keyed.items() if wanted in exact or wanted in slugs]
        if not hits:
            hits = [part for part, (_, slugs) in keyed.items()
                    if any(slug.startswith(wanted) for slug in slugs)]
        # One name must not quietly mean two unrelated sections (`yield` in
        # both Calculations and Discussion): join them yourself with a+b, or
        # spell the folder out (`discussion/yield`).
        groups = {part.relative_to(directory).parts[0] for part in hits}
        if len(groups) > 1:
            raise SystemExit(f"--section '{request}' is ambiguous: it matches parts in "
                             + ", ".join(sorted(groups))
                             + ". Name the folder too (e.g. 'folder/name'), or join with +")
        if not hits:
            tops = dict.fromkeys(part.relative_to(directory).parts[0] for part in parts)
            available = ", ".join(
                f"{part_slug(Path(top).stem)} ({(re.match(r'[0-9]+', top) or [''])[0] or '-'})"
                for top in tops)
            raise NoPartMatches(f"--section '{request}' matches no part. Available: {available}")
        chosen.update(hits)
    return [part for part in parts if part in chosen]


def select_parts_and_sections(parts: list[Path], directory: Path,
                              requests: list[str]) -> tuple[list[Path], dict[Path, list[Heading]]]:
    """select_parts, and then a heading inside a part for every name that is no
    part's: `report#sampling` builds the Sampling section of whichever part has
    it. A name starting with `#` (`report##sampling`) means a heading from the
    start, never a part. Returns the parts to build, in order, and for those
    that only a section of is wanted, the sections (lines of the part's text
    without its front matter). Naming a part whole beats naming a section."""
    chosen: set[Path] = set()
    heading_requests: list[tuple[str, NoPartMatches | None]] = []
    for request in requests:
        if request.strip().startswith("#"):
            heading_requests.append((request, None))
            continue
        try:
            chosen.update(select_parts(parts, directory, [request]))
        except NoPartMatches as error:
            heading_requests.append((request, error))
    cuts: dict[Path, list[Heading]] = {}
    if heading_requests:
        headings: list[Heading] = []
        spans: list[tuple[int, Path, int]] = []      # (offset, part, lines): where each part sits in `headings`' numbering
        offset = 0
        for part in parts:
            lines = strip_part_front_matter(part.read_text(encoding="utf-8-sig")).split("\n")
            headings += [heading._replace(line=heading.line + offset, end=heading.end + offset)
                         for heading in scan_items(lines)]
            spans.append((offset, part, len(lines)))
            offset += len(lines) + 1

        def home(heading: Heading) -> tuple[int, Path]:
            return next((start, part) for start, part, count in reversed(spans) if heading.line >= start)

        def describe(heading: Heading) -> str:
            start, part = home(heading)
            return (f"{part.relative_to(directory)}, "
                    + describe_heading(heading._replace(line=heading.line - start)))

        for request, part_error in heading_requests:
            try:
                heading = find_heading(headings, request, describe)
            except NoHeadingMatches as error:
                raise SystemExit(f"{part_error}\n(and no heading named like that: {error})"
                                 if part_error else str(error))
            start, part = home(heading)
            cuts.setdefault(part, []).append(heading._replace(line=heading.line - start, end=heading.end - start))
        cuts = {part: outermost_headings(found) for part, found in cuts.items() if part not in chosen}
    chosen.update(cuts)
    return [part for part in parts if part in chosen], cuts


# The sections of parts that a parts-mode build takes only a piece of (see
# ScaffoldPlan.cuts), consulted by scaffold_inputs() wherever it runs -- the cache
# route calls the build again, and this is what lets both see the same cuts.
PART_CUTS: dict[Path, list[Heading]] = {}


class ScaffoldPlan:
    """What a parts-mode build consists of."""

    def __init__(self, scaffold: Path, directory: Path, parts: list[Path],
                 selected: list[Path] | None, metadata_files: list[Path],
                 cuts: dict[Path, list[Heading]] | None = None):
        self.scaffold = scaffold
        self.directory = directory
        self.parts = parts
        self.selected = selected          # None = the full report
        self.metadata_files = metadata_files
        self.cuts = cuts or {}            # selected parts built only in these sections (see PART_CUTS)

    @property
    def files(self) -> list[Path]:
        return [self.scaffold, *(self.parts if self.selected is None else self.selected)]

    @property
    def output_stem(self) -> str:
        if self.selected is None:
            return self.scaffold.stem
        # A whole top-level folder is named by the folder, not its files.
        labels: list[str] = []
        for part in self.selected:
            if part in self.cuts:
                for heading in self.cuts[part]:
                    label = item_label(heading)
                    if label not in labels:
                        labels.append(label)
                continue
            top = part.relative_to(self.directory).parts[0]
            siblings = [other for other in self.parts
                        if other.relative_to(self.directory).parts[0] == top]
            whole = len(siblings) > 1 and all(other in self.selected for other in siblings)
            label = part_slug(Path(top).stem if whole or len(part.relative_to(self.directory).parts) == 1
                              else part.with_suffix("").name)
            if label not in labels:
                labels.append(label)
        return f"{self.scaffold.stem}.{'+'.join(labels)}"


def warn_shared_parts_folder(scaffold: Path, directory: Path, setting: str) -> None:
    """With `parts: auto`, EVERY Markdown file beside a parts/ folder counts as
    its scaffold. That is right for the usual folder (one report.md), and
    surprising when a notes.md or draft sits there too: say so once, rather
    than silently building the same parts into both.
    """
    if setting != "auto":
        return
    others = [item.name for item in sorted(scaffold.parent.glob("*.md"))
              if item != scaffold and not item.name.startswith(".")
              and parts_setting(item, scaffold_metadata_files(item, None)) == "auto"]
    if others:
        print(f"WARN  {display_path(scaffold)}: {display_path(directory)} also sits beside "
              f"{', '.join(others)}, which `parts: auto` builds from it too; put "
              "`pdfmd-options: {parts: false}` in the files that are not the report",
              file=sys.stderr)


def split_section_requests(raw: list[str]) -> list[str]:
    """`a,b` and `a+b` both mean "a and b" (`pdfmd report#discussion+appendix`)."""
    return [piece.strip() for item in raw for piece in re.split(r"[,+]", item) if piece.strip()]


def scaffold_metadata_files(document: Path, requested: list[str] | None) -> list[Path]:
    if requested is None:
        requested = option_names(frontmatter_pdfmd_options(document), "yaml") or None
    try:
        found = find_metadata(document.parent.resolve(), requested, document_stem=document.stem)
    except (FileNotFoundError, ValueError):
        return []
    if found is None or found is AUTO_METADATA_DISABLED:
        return []
    return found if isinstance(found, list) else [found]


def plan_scaffold(source: Path, sections: list[str], cli_no_auto: list[str] | None,
                  requested_metadata: list[str] | None) -> ScaffoldPlan | None:
    """Decide whether ``source`` is a scaffold, or a part of one, and what to
    build; None means an ordinary document. ``source`` may be the scaffold
    itself, or any file inside its parts folder -- found by walking up to a
    folder whose scaffold names this one, so a part builds with the same
    metadata, paths and bibliography as the full report. A part given by path
    is built alone even if parts-mode skips it (an ``_underscore`` draft).
    """
    if source.suffix.lower() != ".md" or auto_disabled(effective_no_auto(source, cli_no_auto), "parts"):
        return None
    mfiles = scaffold_metadata_files(source, requested_metadata)
    setting = parts_setting(source, mfiles)
    directory = parts_directory(source, setting) if setting else None
    if directory is not None:
        parts = collect_parts(directory)
        if not parts:
            raise SystemExit(f"{display_path(directory)} has no Markdown parts")
        selected, cuts = select_parts_and_sections(parts, directory, sections) if sections else (None, {})
        warn_shared_parts_folder(source, directory, setting)
        return ScaffoldPlan(source, directory, parts, selected, mfiles, cuts)
    for ancestor in list(source.parents)[:4]:
        root = ancestor.parent
        if root == ancestor:
            break
        for candidate in sorted(root.glob("*.md")):
            candidate_meta = scaffold_metadata_files(candidate, requested_metadata)
            candidate_setting = parts_setting(candidate, candidate_meta)
            candidate_dir = parts_directory(candidate, candidate_setting) if candidate_setting else None
            if candidate_dir is not None and candidate_dir == ancestor.resolve():
                parts = collect_parts(candidate_dir)
                warn_shared_parts_folder(candidate, candidate_dir, candidate_setting)
                more, cuts = select_parts_and_sections(parts, candidate_dir, sections) if sections else ([], {})
                chosen = {source, *more}
                selected = sorted(chosen, key=lambda part: parts.index(part) if part in parts else len(parts))
                return ScaffoldPlan(candidate, candidate_dir, parts, selected, candidate_meta,
                                    {part: found for part, found in cuts.items() if part != source})
    return None


LEADING_FRONT_MATTER_RE = re.compile(r"^---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|$)", re.DOTALL)


def strip_part_front_matter(text: str) -> str:
    """Remove a leading YAML block or ``% title`` block from a part. Pandoc
    merges every later file's YAML into the document's metadata and the LATER
    value wins (checked: a part's `title:` replaced the scaffold's), and a
    `% ...` title block is only recognised at the very start of the first
    file -- elsewhere it prints as a paragraph. Parts carry no metadata.
    """
    stripped = LEADING_FRONT_MATTER_RE.sub("", text, count=1)
    lines = stripped.split("\n")
    count = 0
    while count < len(lines) and lines[count].startswith("%"):
        count += 1
        while count < len(lines) and lines[count].startswith((" ", "\t")) and lines[count].strip():
            count += 1
    return "\n".join(lines[count:]) if count else stripped


@contextmanager
def scaffold_inputs(files: list[Path], active: bool,
                    markers: dict[Path, str] | None = None) -> Iterator[list[Path]]:
    """Yield the files to hand Pandoc: the scaffold as is, each part with its
    front matter removed (a hidden temp copy beside it, deleted afterwards;
    a part with nothing to remove is passed through untouched). ``markers``
    maps a part to its key: that part then starts with a raw
    ``\\pdfmdpart{key}`` line (see PARTS_MARKER_DEFS), which records LaTeX's
    counters at that point in the .aux.
    """
    if not active:
        yield list(files)
        return
    temporary: list[Path] = []
    prepared = [files[0]]
    try:
        for part in files[1:]:
            text = part.read_text(encoding="utf-8-sig")
            cleaned = strip_part_front_matter(text)
            if part in PART_CUTS:
                # Only some sections of this part (a `#name` that is no part's
                # name): no counter marker -- it would restore the counters of
                # the part's start, not of the section's.
                lines = cleaned.split("\n")
                cleaned = "\n\n".join("\n".join(lines[heading.line:heading.end]).rstrip("\n")
                                       for heading in PART_CUTS[part]) + "\n"
            elif markers and part in markers:
                cleaned = "```{=latex}\n\\pdfmdpart{%s}\n```\n\n%s" % (markers[part], cleaned)
            if cleaned == text:
                prepared.append(part)
                continue
            with NamedTemporaryFile("w", encoding="utf-8", suffix=".md",
                                    prefix=f".{part.stem}.pdfmd-part-", dir=part.parent,
                                    delete=False) as handle:
                handle.write(cleaned)
                temporary.append(Path(handle.name))
            prepared.append(temporary[-1])
        yield prepared
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def print_parts(plan: ScaffoldPlan) -> None:
    print(f"SCAFFOLD  {display_path(plan.scaffold)}")
    for part in plan.parts:
        text = part.read_text(encoding="utf-8-sig")
        body = strip_part_front_matter(text)
        heading = next((line.strip() for line in body.splitlines() if re.match(r"#{1,6}\s", line)), "")
        mark = "*" if plan.selected is not None and part in plan.selected else " "
        print(f"  {mark} {str(part.relative_to(plan.directory)):<36} {len(text.splitlines()):>5} lines  {heading}")
        depth = 0
        for inner in scan_items(body.split("\n"))[1:]:
            depth = inner.level or depth
            ids = " ".join(f"{{#{identifier}}}" for identifier in inner.ids)
            if inner.level:
                print(f"      {'  ' * (inner.level - 1)}{'#' * inner.level} {inner.text}{'  ' + ids if ids else ''}")
            else:
                print(f"      {'  ' * depth}{ids}  [{inner.text}]")

def split_top_level_sections(body: str, level: int = 1) -> list[list[str]]:
    """Cut Markdown at its ATX headings of exactly `level` (1 = `# `). Element
    0 is whatever comes before the first one (often a comment block). A `# `
    line inside a fenced code block (a Python comment) or an HTML comment is
    not a heading.
    """
    heading = re.compile("#{%d} \\S" % level)
    sections: list[list[str]] = [[]]
    fence: str | None = None
    comment = False
    for line in body.split("\n"):
        stripped = line.strip()
        if not comment:
            marker = re.match(r"(`{3,}|~{3,})", stripped)
            if fence is None and marker:
                fence = marker.group(1)[0] * 3
            elif fence is not None and stripped.startswith(fence):
                fence = None
        if fence is None and not comment and heading.match(line):
            sections.append([])
        sections[-1].append(line)
        if fence is None:
            position = 0
            while True:
                if not comment:
                    found = line.find("<!--", position)
                    if found < 0:
                        break
                    comment, position = True, found + 4
                else:
                    found = line.find("-->", position)
                    if found < 0:
                        break
                    comment, position = False, found + 3
    return sections


def slug_of(heading_line: str) -> str:
    title = re.sub(r"\{#[^}]*\}", "", heading_line.lstrip("# "))
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")
    if len(slug) > 30:   # cut at a word boundary, not mid-word
        slug = slug[:30].rsplit("-", 1)[0] if "-" in slug[:30] else slug[:30]
    return slug or "part"



# --- Rendering one section of an ordinary document: `pdfmd doc#methods` -------
#
# A document that is not in parts mode has no parts to name, so a section is cut
# out of the text: a heading, and everything up to the next heading of the same
# or a higher level (its subsections included). The cut document is the
# document's own front matter, the text before its first heading, and the
# chosen sections, built as a partial build (see ScaffoldPlan): title page and
# settings kept, written as `doc.NAME.pdf`, no BUILD NOTES stamp,
# `pdfmd-partial: true`. A section is named the way a file is (lookup_key and
# LOOKUP_TIERS: `onlyapart`, `only_a_part` and `Only a Part` are one name), by
# its `{#id}` too, one level down with `/` (`results/yield`), and a leading run
# of `#` restricts it to that heading level (`doc##yield`).

ATX_HEADING_RE = re.compile(r" {0,3}(#{1,6})[ \t]+(.*?)[ \t]*$")
SETEXT_UNDERLINE_RE = re.compile(r" {0,3}(=+|-+)[ \t]*$")
HEADING_ATTRIBUTES_RE = re.compile(
    r"^(?:\s*(?:#[^\s{}]+|\.[^\s{}]+|[\w:-]+=(?:\"[^\"]*\"|'[^']*'|[^\s{}]+)|-))+\s*$")


def heading_parts(raw: str) -> tuple[str, list[str]]:
    """(plain text, explicit ids) of a heading's text as written: the closing
    ``#``s and a trailing ``{#id .class}`` block removed, links and spans
    reduced to their text."""
    text = re.sub(r"[ \t]+#+$", "", raw.strip())
    ids: list[str] = []
    match = re.search(r"\s+\{([^{}]*)\}\s*$", text)     # `[span]{.c}` is not the heading's own
    if match and HEADING_ATTRIBUTES_RE.match(match.group(1)):
        ids = re.findall(r"(?:^|\s)#([^\s{}]+)", match.group(1))
        text = re.sub(r"[ \t]+#+$", "", text[:match.start()].strip())
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\{[^}]*\}", r"\1", text)
    return text.strip(), ids


def scan_headings(lines: list[str]) -> list[Heading]:
    """Every heading of a Markdown body, ATX (``## Title``) and setext (a line
    underlined with ``===`` or ``---``) alike, in order, each with the line it
    ends before: the next heading of the same or a higher level, or the end.
    A ``#`` line inside a fenced code block or an HTML comment is not one, and
    a setext heading needs a blank line (or the start) before its text, so a
    paragraph's last line, a table rule and a ``---`` rule are left alone."""
    found: list[tuple[int, int, str]] = []
    fence: str | None = None
    comment = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        was_comment = comment
        if not comment:
            marker = re.match(r"(`{3,}|~{3,})", stripped)
            if fence is None and marker:
                fence = marker.group(1)[0] * 3
            elif fence is not None and stripped.startswith(fence):
                fence = None
        if fence is None and not was_comment:
            atx = ATX_HEADING_RE.match(line)
            if atx:
                found.append((index, len(atx.group(1)), atx.group(2)))
            elif (stripped and index + 1 < len(lines) and (index == 0 or not lines[index - 1].strip())
                  and SETEXT_UNDERLINE_RE.match(lines[index + 1])
                  and not SETEXT_UNDERLINE_RE.match(line) and "<!--" not in line
                  and not line.startswith(("    ", "\t", ">", "- ", "* ", "+ ", "|"))):
                found.append((index, 1 if lines[index + 1].lstrip().startswith("=") else 2, line))
        if fence is None:
            position = 0
            while True:
                if not comment:
                    at = line.find("<!--", position)
                    if at < 0:
                        break
                    comment, position = True, at + 4
                else:
                    at = line.find("-->", position)
                    if at < 0:
                        break
                    comment, position = False, at + 3
    headings = []
    for number, (index, level, raw) in enumerate(found):
        text, ids = heading_parts(raw)
        end = next((later for later, later_level, _ in found[number + 1:] if later_level <= level), len(lines))
        headings.append(Heading(index, level, text, tuple(ids), end))
    return headings


DIV_FENCE_RE = re.compile(r" {0,3}(:{3,})(.*)$")
ATTRIBUTE_ID_RE = re.compile(r"\{[^{}]*?#([^\s{}]+)[^{}]*\}")
TABLE_LINE_RE = re.compile(r"\s*(?:[|+].*|[-=+| :]{3,})$")


def block_ids(text: str) -> list[str]:
    return ATTRIBUTE_ID_RE.findall(text)


def scan_labelled_blocks(lines: list[str], headings: list[Heading]) -> list[Heading]:
    """The elements of a Markdown body that carry a ``{#id}`` and are not
    headings, as Heading(level=0): a fenced div (``::: {#id}``, to its closing
    fence), a fenced code block (``{#lst:x}`` on the fence), a table (the
    ``: caption {#tbl:x}`` line and the table it belongs to), and any other
    paragraph with an id in it -- a figure ``![..](..){#fig:x}``, an equation
    ``$$..$$ {#eq:x}``, a ``[span]{#id}``. A paragraph is a run of lines up to
    a blank one, so a labelled list item is its whole list. ``text`` names the
    kind; ``end`` is exclusive."""
    taken = {heading.line for heading in headings}
    taken |= {heading.line + 1 for heading in headings
              if heading.line + 1 < len(lines) and SETEXT_UNDERLINE_RE.match(lines[heading.line + 1])
              and not ATX_HEADING_RE.match(lines[heading.line])}
    found: list[Heading] = []
    chunks: list[list] = []                      # [start, end, ids] of text runs
    divs: list[tuple[int, int, list[str]]] = []  # open fenced divs
    run_start: int | None = None
    index = 0

    def close_run(end: int) -> None:
        nonlocal run_start
        if run_start is not None:
            ids = [identifier for line_no in range(run_start, end) if line_no not in taken
                   for identifier in block_ids(lines[line_no])]
            chunks.append([run_start, end, ids])
            run_start = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if fence:
            close_run(index)
            end = next((later + 1 for later in range(index + 1, len(lines))
                        if lines[later].strip().startswith(fence.group(1)[0] * 3)), len(lines))
            ids = block_ids(line)
            if ids:
                found.append(Heading(index, 0, "code block", tuple(ids), end))
            index = end
            continue
        if stripped.startswith("<!--") and "-->" not in stripped:
            close_run(index)
            index = next((later + 1 for later in range(index + 1, len(lines)) if "-->" in lines[later]), len(lines))
            continue
        div = DIV_FENCE_RE.match(line)
        if div:
            close_run(index)
            if div.group(2).strip():
                divs.append((index, len(div.group(1)), block_ids(div.group(2))))
            elif divs:
                start, _, ids = divs.pop()
                if ids:
                    found.append(Heading(start, 0, "div", tuple(ids), index + 1))
            index += 1
            continue
        if not stripped:
            close_run(index)
        elif run_start is None:
            run_start = index
        index += 1
    close_run(len(lines))
    for position, (start, end, ids) in enumerate(chunks):
        if not ids:
            continue
        kind = "equation" if "$$" in "".join(lines[start:end]) else (
            "figure" if lines[start].lstrip().startswith("![") else "paragraph")
        first = lines[start].lstrip()
        if first.startswith((": ", "Table:")):
            # A table caption: the table is the run before it, or, for a caption written
            # above the table, the run after it.
            before = chunks[position - 1] if position else None
            after = chunks[position + 1] if position + 1 < len(chunks) else None
            if before and TABLE_LINE_RE.match(lines[before[0]]):
                start, kind = before[0], "table"
            elif after and TABLE_LINE_RE.match(lines[after[0]]):
                end, kind = after[1], "table"
        found.append(Heading(start, 0, kind, tuple(ids), end))
    return sorted(found, key=lambda item: (item.line, item.end))


def scan_items(lines: list[str]) -> list[Heading]:
    """Everything `#name` can name in a body: its headings (level 1-6) and its
    labelled elements (level 0), in order."""
    headings = scan_headings(lines)
    return sorted(headings + scan_labelled_blocks(lines, headings), key=lambda item: (item.line, item.level == 0))


def parse_section_request(request: str) -> tuple[int | None, list[str]]:
    """``##yield`` -> (2, ["yield"]); ``results/yield`` -> (None, ["results", "yield"])."""
    match = re.match(r"\s*(#*)(.*)$", request)
    return (len(match.group(1)) or None), [name.strip() for name in match.group(2).split("/") if name.strip()]


def describe_heading(heading: Heading) -> str:
    if not heading.level:
        return f"line {heading.line + 1}: {heading.text} {{#{heading.ids[0]}}}"
    return f"line {heading.line + 1}: {'#' * heading.level} {heading.text}"


def item_label(item: Heading) -> str:
    """The file-name label of a section or element."""
    return section_label(item.text if item.level else item.ids[0])


def find_heading(headings: list[Heading], request: str, describe=None) -> Heading:
    """The one heading ``request`` names. Unknown or ambiguous names are an
    error that lists the choices: a typo must never silently build the wrong
    section."""
    describe = describe or describe_heading
    level, names = parse_section_request(request)
    if not names:
        raise SystemExit(f"--section '{request}' names no heading")
    by_line = {heading.line: heading for heading in headings}
    tiers = LOOKUP_TIERS if FUZZY_LOOKUP else LOOKUP_TIERS[:3]
    pool = headings
    for position, name in enumerate(names):
        last = position == len(names) - 1
        candidates = [heading for heading in pool if not last or level is None or heading.level == level]
        entries = [(heading.line, [("alias", identifier) for identifier in heading.ids]
                    + ([("stem", heading.text)] if heading.level else [])) for heading in candidates]
        try:
            found = rank_lookup(name, entries, lambda line: describe(by_line[line]),
                                HEADING_FIELD_WORDS, tiers)
        except LookupAmbiguous as error:
            raise SystemExit(f"--section '{request}': {error} Add `#`s for its level, or `parent/name`.")
        if not found:
            choices = "; ".join((f"{'#' * heading.level} {heading.text}" if heading.level else f"{{#{heading.ids[0]}}}")
                                for heading in candidates[:12])
            raise NoHeadingMatches(f"--section '{request}' matches no heading"
                             + (f" at level {level}" if last and level else "")
                             + (f" under '{pool_owner.text}'" if position else "")
                             + f". Headings: {choices or 'none'}" + (" ..." if len(candidates) > 12 else ""))
        heading = by_line[found[0]]
        announce_lookup(name, describe(heading), *found[1:], words=HEADING_FIELD_WORDS, subject="heading or element")
        pool_owner = heading
        pool = [other for other in headings if heading.line < other.line < heading.end]
    return heading


def outermost_headings(chosen: list[Heading]) -> list[Heading]:
    """In document order, without any heading already inside another one chosen."""
    ordered = sorted(set(chosen), key=lambda heading: heading.line)
    kept: list[Heading] = []
    for heading in ordered:
        if not kept or heading.line >= kept[-1].end:
            kept.append(heading)
    return kept


def section_label(text: str) -> str:
    """A file-name label for a heading, Cyrillic and Turkish letters written in Latin."""
    return slug_of("".join(CYRILLIC_STRICT.get(letter, LATIN_EXTRA.get(letter, letter))
                           for letter in text.casefold()))



class SectionPlan:
    """A plain document cut down to some of its sections (see above)."""

    def __init__(self, source: Path, text: str, shifted: bool, selected: list[Heading]):
        self.source = source
        self.text = text            # the document pdfmd hands Pandoc instead of the file
        self.shifted = shifted      # the document's leading `# Title` became its title
        self.selected = selected

    @property
    def output_stem(self) -> str:
        labels = list(dict.fromkeys(item_label(item) for item in self.selected))
        return f"{self.source.stem}.{'+'.join(labels)}"


def section_source(source: Path, cli_no_auto: list[str] | None,
                   requested_metadata: list[str] | None) -> tuple[str, list[str], bool]:
    """(front matter, body lines, shifted) of ``source`` as pdfmd would give it
    to Pandoc: the same bare-`# Title` promotion first, so headings are cut
    from the text that is actually built."""
    raw = source.read_text(encoding="utf-8-sig")
    if auto_disabled(effective_no_auto(source, cli_no_auto), "title"):
        promoted, shifted = raw, False
    else:
        promoted, shifted = promote_bare_title(
            raw, has_external_metadata=bool(scaffold_metadata_files(source, requested_metadata)))
    front = LEADING_FRONT_MATTER_RE.match(promoted)
    end = front.end() if front else 0
    return promoted[:end], promoted[end:].split("\n"), shifted


def plan_sections(source: Path, requests: list[str], cli_no_auto: list[str] | None,
                  requested_metadata: list[str] | None) -> SectionPlan:
    head, lines, shifted = section_source(source, cli_no_auto, requested_metadata)
    items = scan_items(lines)
    if not items:
        raise SystemExit(f"{display_path(source)} has no headings or {{#labels}} to take a section of"
                         + (" (its first `# Title` became the document's title)" if shifted else ""))
    selected = outermost_headings([find_heading(items, request) for request in requests])
    # The text before the first heading (an abstract, a \tableofcontents) comes
    # with a section, as in parts mode, but not with a lone figure or equation.
    first_heading = next((item.line for item in items if item.level), len(lines))
    with_lead = any(item.level for item in selected)
    lead = "\n".join(lines[:first_heading]).strip("\n") if with_lead else ""
    blocks = ([lead] if lead else []) + ["\n".join(lines[item.line:item.end]).rstrip("\n")
                                         for item in selected if not (lead and item.end <= first_heading)]
    return SectionPlan(source, head + "\n\n".join(blocks) + "\n", shifted, selected)


def print_headings(source: Path, cli_no_auto: list[str] | None, requested_metadata: list[str] | None) -> None:
    """--list-parts for a document that is not in parts mode: what `#` can name."""
    _, lines, _ = section_source(source, cli_no_auto, requested_metadata)
    print(f"DOCUMENT  {display_path(source)}")
    depth = 0
    for item in scan_items(lines):
        depth = item.level or depth
        ids = " ".join(f"{{#{identifier}}}" for identifier in item.ids)
        if item.level:
            print(f"  {'  ' * (item.level - 1)}{'#' * item.level} {item.text}{'  ' + ids if ids else ''}"
                  f"  (lines {item.line + 1}-{item.end})")
        else:
            print(f"  {'  ' * depth}{ids}  [{item.text}]  (lines {item.line + 1}-{item.end})")


def split_into_parts(source: Path, destination: Path, depth: int = 1) -> int:
    """Turn a single-file document into a scaffold plus parts in a NEW folder
    (never in place), and link everything else the document refers to, so the
    result builds as it stands. Returns 0 if the Pandoc AST of the parts
    equals the original's, 1 if not (the cut is then wrong; nothing is
    claimed). The source is not modified.
    """
    text = source.read_text(encoding="utf-8-sig")
    front = re.match(r"^---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if not front:
        raise SystemExit(f"{source}: --split needs YAML front matter (it becomes the scaffold)")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"{destination} exists and is not empty; --split writes to a new folder")
    sections = split_top_level_sections(text[front.end():])
    if len(sections) < 2:
        raise SystemExit(f"{source}: no level-1 ('# ') headings to split at")
    parts_dir = destination / "parts"
    parts_dir.mkdir(parents=True)
    lead = "\n".join(sections[0]).strip("\n")
    scaffold = destination / f"{source.stem}.md"
    scaffold.write_text(text[:front.end()] + (("\n" + lead + "\n") if lead else ""), encoding="utf-8")
    written: list[Path] = []

    def emit(section: list[str], directory: Path, number: int, level: int) -> None:
        """One file per section; with depth left, a folder whose first file
        holds the heading and the text before its first subheading and whose
        other files are the subsections (selecting the folder selects all)."""
        slug = slug_of(section[0])
        pieces = split_top_level_sections("\n".join(section), level + 1) if level < depth else [section]
        if len(pieces) < 2:
            part = directory / f"{number * 10:02d}-{slug}.md"
            part.write_text("\n".join(section).rstrip("\n") + "\n", encoding="utf-8")
            written.append(part)
            return
        folder = directory / f"{number * 10:02d}-{slug}"
        folder.mkdir()
        lead = folder / f"00-{slug}.md"
        lead.write_text("\n".join(pieces[0]).rstrip("\n") + "\n", encoding="utf-8")
        written.append(lead)
        for index, piece in enumerate(pieces[1:], 1):
            emit(piece, folder, index, level + 1)

    for number, section in enumerate(sections[1:], 1):
        emit(section, parts_dir, number, 1)
    skip = {source.name.casefold()}
    for entry in sorted(source.parent.iterdir()):
        if (entry.name.startswith(".") or entry.name.casefold() in skip or entry.name.casefold() in PARTS_SKIP_DIRS
                or entry.suffix.lower() in {".pdf", ".md"} or (destination / entry.name).exists()
                or entry.resolve() in (destination, *destination.parents)):
            continue
        (destination / entry.name).symlink_to(os.path.relpath(entry.absolute(), destination),
                                               target_is_directory=entry.is_dir())
    original = subprocess.run(["pandoc", str(source), "-t", "native"], capture_output=True, text=True)
    split = subprocess.run(["pandoc", str(scaffold), *map(str, written), "-t", "native"],
                           capture_output=True, text=True)
    print(f"SPLIT  {display_path(source)} -> {display_path(scaffold)} + {len(written)} parts in "
          f"{display_path(parts_dir)}")
    if original.returncode == 0 and original.stdout == split.stdout:
        print("OK     the parts read back as the identical document (Pandoc AST compared)")
        if not parts_setting(scaffold, scaffold_metadata_files(scaffold, None)):
            print("NOTE   parts mode is off for this document: add `pdfmd-options: {parts: auto}` "
                  "to its metadata.yaml (or the scaffold's front matter) to build from the parts")
        return 0
    print("FAIL   the parts do NOT read back as the original; do not use this split", file=sys.stderr)
    return 1



# -- HTML output and default-output (v3.19.4) --------------------------------
# `pdfmd-options: {default-output: html}`: the format a document builds to when
# the command line names none (no --to, no -o with a recognized extension, no
# --stop-at, no -p). `pdfmd-options: {html: {...}}` shapes an HTML build:
#   self-contained: true   one file with everything inlined (--embed-resources
#                          --standalone; pdfmd's HTML output is otherwise a
#                          fragment, unchanged); math defaults to MathML then,
#                          the one kind that needs no network
#   standalone: true       a full page, resources left linked
#   math: mathml|mathjax|katex|webtex|plain
#   css: file.css | [..]   --css, relative to the document
HTML_TARGETS = frozenset({"html", "html4", "html5"})
DEFAULT_OUTPUT_ALIASES = {"tex": "latex", "txt": "plain", "md": "markdown", "htm": "html",
                          "typ": "typst", "markdown": "markdown"}
# The math method, in whichever spelling the installed Pandoc has -- three
# generations: `--math-method=X` (3.11, which deprecates the others and warns),
# `--html-math-method=X` (a middle range of 3.x), and the short flags
# `--mathml`/`--mathjax`/... (older, 3.1 among them, which does not know the
# long forms at all). Found out from `pandoc --help`, never from a guessed
# version number.
HTML_MATH_METHODS = ("mathml", "mathjax", "katex", "webtex", "plain", "gladtex")
HTML_MATH_SHORT_FLAGS = {"mathml": "--mathml", "mathjax": "--mathjax", "katex": "--katex",
                         "webtex": "--webtex", "gladtex": "--gladtex"}   # "plain" is the default: no flag
_PANDOC_HELP: str | None = None


def pandoc_has_option(option: str) -> bool:
    """Whether the installed Pandoc lists ``option`` in its --help, as a whole
    option name (`--math-method` is not found inside `--html-math-method`)."""
    global _PANDOC_HELP
    if _PANDOC_HELP is None:
        try:
            _PANDOC_HELP = subprocess.run(["pandoc", "--help"], capture_output=True, text=True).stdout
        except OSError:
            _PANDOC_HELP = ""
    return bool(re.search(r"(?<![\w-])" + re.escape(option) + r"(?![\w-])", _PANDOC_HELP))


def html_math_args(method: str) -> list[str]:
    for option in ("--math-method", "--html-math-method"):
        if pandoc_has_option(option):
            return [f"{option}={method}"]
    flag = HTML_MATH_SHORT_FLAGS.get(method)
    return [flag] if flag else []


def cascaded_option(md_path: Path, metadata_files: list[Path], key: str):
    """The first ``pdfmd-options.<key>`` found: the document's own, else its
    metadata files' in order (None if none sets it)."""
    sources = [frontmatter_pdfmd_options(md_path)]
    for metadata_file in metadata_files:
        found = metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append(found if isinstance(found, dict) else {})
    for options in sources:
        if key in options:
            return options[key]
    return None


def default_output_format(md_path: Path, metadata_files: list[Path]) -> str | None:
    """``pdfmd-options.default-output`` (a Pandoc writer name, or pdf), None
    if unset. Only Markdown documents have one."""
    if md_path.suffix.lower() not in (".md", ".markdown"):
        return None
    value = cascaded_option(md_path, metadata_files, "default-output")
    if not isinstance(value, str) or not value.strip():
        return None
    name = value.strip().casefold().lstrip(".")
    name = DEFAULT_OUTPUT_ALIASES.get(name, name)
    if name == ASSEMBLED_FORMAT:
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.default-output cannot be "
                         f"'{ASSEMBLED_FORMAT}'; use --stop-at markdown")
    return name


_PANDOC_DATA_DIR: Path | None | bool = False


def pandoc_user_data_dir() -> Path | None:
    """Pandoc's user data directory (where it also looks for a `csl:` style, in
    its `csl/` subfolder), from the "User data directory:" line of
    `pandoc --version`; None if there is none."""
    global _PANDOC_DATA_DIR
    if _PANDOC_DATA_DIR is False:
        _PANDOC_DATA_DIR = None
        try:
            for line in subprocess.run(["pandoc", "--version"], capture_output=True, text=True).stdout.splitlines():
                if line.lower().startswith("user data directory:"):
                    _PANDOC_DATA_DIR = Path(line.split(":", 1)[1].strip())
        except OSError:
            pass
    return _PANDOC_DATA_DIR or None


_PANDOC_VERSION: tuple[int, ...] | None = None


def pandoc_version() -> tuple[int, ...]:
    global _PANDOC_VERSION
    if _PANDOC_VERSION is None:
        try:
            first = subprocess.run(["pandoc", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
            _PANDOC_VERSION = tuple(int(part) for part in re.search(r"(\d+(?:\.\d+)+)", first).group(1).split("."))
        except (OSError, IndexError, AttributeError, ValueError):
            _PANDOC_VERSION = (0,)
    return _PANDOC_VERSION


def html_settings(md_path: Path, metadata_files: list[Path]) -> dict:
    value = cascaded_option(md_path, metadata_files, "html")
    return value if isinstance(value, dict) else {}


def html_pandoc_args(md_path: Path, metadata_files: list[Path], pandoc_options: list[str],
                     cli_self_contained: bool | None, note) -> list[str]:
    """The Pandoc arguments an HTML target adds (see the comment above
    HTML_TARGETS); nothing at all unless something asks for it, so a plain
    `pdfmd x -o x.html` is exactly what it was."""
    settings = html_settings(md_path, metadata_files)
    truthy = lambda value: value is True or str(value).casefold() in {"true", "yes", "on"}
    self_contained = (cli_self_contained if cli_self_contained is not None
                      else truthy(settings.get("self-contained", False)))
    standalone = self_contained or truthy(settings.get("standalone", False))
    out: list[str] = []
    if standalone and not has_standalone_option(pandoc_options):
        out.append("--standalone")
    if self_contained and "--embed-resources" not in pandoc_options and "--self-contained" not in pandoc_options:
        out.append("--embed-resources" if pandoc_version() >= (2, 19) else "--self-contained")
        note("HTML", f"{md_path}: self-contained: one file, resources inlined")
    elif standalone:
        note("HTML", f"{md_path}: a full page (--standalone)")
    math = str(settings.get("math", "")).casefold()
    has_math_option = any(item.startswith(("--math-method", "--html-math-method", "--mathml", "--mathjax",
                                           "--katex", "--webtex", "--gladtex", "--latexmathml"))
                          for item in pandoc_options)
    if not has_math_option and math in HTML_MATH_METHODS:
        out += html_math_args(math)
    elif not has_math_option and math in ("", "auto") and self_contained:
        out += html_math_args("mathml")  # the one kind of math that needs no network
    css = settings.get("css")
    for name in ([css] if isinstance(css, str) else css if isinstance(css, list) else []):
        out += ["--css", str((md_path.parent / str(name)).resolve())]
    if standalone and not any(item.startswith(("--metadata=pagetitle", "-Mpagetitle")) for item in pandoc_options):
        if not (frontmatter_value(md_path, "title") or frontmatter_value(md_path, "pagetitle")
                or any(metadata_file_yaml(item).get("title") or metadata_file_yaml(item).get("pagetitle")
                       for item in metadata_files)):
            out += ["--metadata", f"pagetitle={md_path.stem}"]
    return out


def strip_embedded_preamble(text: str) -> str:
    """``text`` without the LaTeX preamble an assembled file embeds at the
    head of its `header-includes` (everything up to PREAMBLE_END_MARK): for a
    target that is not LaTeX-family, where Pandoc would put it in the output
    as text (an HTML <head>). The document's own header-includes stay."""
    front = re.match(r"^(---[ \t]*\n)(.*?)(\n(?:---|\.\.\.)[ \t]*(?:\n|$))", text, re.DOTALL)
    if not front or PREAMBLE_END_MARK not in front.group(2):
        return text
    block = re.search(r"(?m)^header-includes: \|\n((?:  .*\n|[ \t]*\n)*)", front.group(2) + "\n")
    if not block:
        return text
    lines = block.group(1).split("\n")
    mark = f"  {PREAMBLE_END_MARK}"
    if mark not in lines:
        return text
    rest = "\n".join(lines[lines.index(mark) + 1:]).strip("\n")
    replacement = f"header-includes: |\n{rest}\n" if rest.strip() else ""
    yaml_text = front.group(2) + "\n"
    yaml_text = yaml_text[:block.start()] + replacement + yaml_text[block.end():]
    return front.group(1) + yaml_text.rstrip("\n") + front.group(3) + text[front.end():]


# -- Stop-at stages (--stop-at markdown|tex|pdf) -----------------------------
# The build is a pipeline: the document's parts are joined into ONE Markdown
# text, Pandoc turns that into a standalone .tex, a LaTeX engine turns the
# .tex into a PDF. --stop-at ends it early, after the named stage. `tex` is
# simply `--to latex` (`beamer` with -p); `markdown` is pdfmd's own stage,
# handled here: the text Pandoc would be given, written out as one file.
# ASSEMBLED_FORMAT is the internal pseudo target-format that carries it
# through the same code paths as a real one (output naming, batch, report).
STOP_STAGES = ("markdown", "tex", "pdf")
ASSEMBLED_FORMAT = "assembled"
ASSEMBLED_SUFFIX = ".assembled.md"
# A top-level front-matter key (an HTML comment where there is no front matter
# to put it in) written into every assembled file. A file that carries it is
# already the finished text of a build: parts mode never treats
# it as a scaffold (it would join the parts a second time), and batch/report
# assembly skips it instead of assembling an assembly.
ASSEMBLED_KEY = "pdfmd-assembled"
ASSEMBLED_KEY_RE = re.compile(r"^pdfmd-assembled:[ \t]*(?:true|yes|on)[ \t]*$", re.IGNORECASE | re.MULTILINE)
ASSEMBLED_COMMENT = "<!-- pdfmd-assembled: true -->"
# `<!-- pdfmd-assembled: true; no-auto: lua,preamble -->`: the comment form of
# the marker can carry the no-auto kinds that the front-matter form keeps in
# `pdfmd-options` (see embed_into_text).
ASSEMBLED_COMMENT_RE = re.compile(
    r"^<!-- pdfmd-assembled: true(?:; no-auto: (?P<kinds>[a-z,]+))? -->[ \t]*$", re.MULTILINE)


def is_assembled_text(text: str) -> bool:
    front_matter = re.match(r"^---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if front_matter and ASSEMBLED_KEY_RE.search(front_matter.group(1)):
        return True
    return bool(ASSEMBLED_COMMENT_RE.search(mask_embedded_blocks(text)))


def is_assembled_document(path: Path) -> bool:
    """Whether ``path`` is an assembled file written by --stop-at markdown."""
    if path.suffix.lower() not in (".md", ".markdown"):
        return False
    try:
        return is_assembled_text(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        return False


def mark_assembled(text: str, no_auto: list[str] | None = None, partial: bool = False) -> str:
    """Mark ``text`` as assembled: ASSEMBLED_KEY in its front matter if it
    has a block, else an HTML comment at the end. Never a NEW front-matter
    block: that would change how the document reads -- Pandoc's own `% title`
    block stops being one behind it, and a leading `# Title` heading is only
    promoted to the title (promote_bare_title) in a document with no front
    matter at all.
    """
    if re.match(r"^---[ \t]*\n", text):
        # A partial build (`report#methods`) tells Pandoc `-M pdfmd-partial=true`
        # on the command line; the assembled file has to carry it itself.
        marks = f"{ASSEMBLED_KEY}: true\n" + (f"{PARTIAL_KEY}: true\n" if partial else "")
        return re.sub(r"^---[ \t]*\n", f"---\n{marks}", text, count=1)
    if partial:
        print(f"WARN  a partial build with no front matter cannot record {PARTIAL_KEY}; a filter "
              "that reads it will not see it when the assembled file is built", file=sys.stderr)
    comment = (ASSEMBLED_COMMENT if not no_auto else
               f"<!-- pdfmd-assembled: true; no-auto: {','.join(no_auto)} -->")
    return text.rstrip("\n") + f"\n\n{comment}\n"


def assemble_markdown_text(sources: list[Path], drop_later_front_matter: bool,
                           plan: "EmbedPlan | None" = None, partial: bool = False) -> str:
    """The Markdown Pandoc is given for ``sources``, as ONE text: the first
    file as it is, every later one after it. In parts mode a part's own
    leading front matter is dropped first, exactly as scaffold_inputs() does
    before Pandoc sees it; a report/book chapter keeps its own, since there
    Pandoc reads it too.
    """
    chunks = []
    for index, source in enumerate(sources):
        text = source.read_text(encoding="utf-8-sig")
        if index and drop_later_front_matter:
            text = strip_part_front_matter(text)
        chunks.append(text.rstrip("\n") + "\n")
    joined = "\n".join(chunks)
    if plan is not None:
        return embed_into_text(joined, sources[0], plan, partial)
    return mark_assembled(joined, partial=partial)


def write_assembled_markdown(sources: list[Path], output: Path,
                             drop_later_front_matter: bool,
                             plan: "EmbedPlan | None" = None,
                             partial: bool = False) -> tuple[bool, str]:
    """Write the --stop-at markdown stage. Never over one of its own sources:
    `-o report.md` would otherwise replace the very file it was built from.
    """
    resolved = {source.resolve() for source in sources}
    if output.resolve() in resolved:
        return False, (f"{display_path(output)} is one of the files being assembled; "
                       f"pick another name (the default is NAME{ASSEMBLED_SUFFIX})")
    output.parent.mkdir(parents=True, exist_ok=True)
    if plan is not None:
        plan.output = output
    text = assemble_markdown_text(sources, drop_later_front_matter, plan, partial)
    output.write_text(text, encoding="utf-8", newline="\n")
    print(f"ASSEMBLED  {display_path(output)}  ({len(sources)} file{'s' if len(sources) != 1 else ''}, "
          f"{len(text.splitlines())} lines)")
    return True, ""


# -- Embedding (--embed-metadata, v3.19.1) -----------------------------------
# An assembled file normally holds just the text; the metadata YAML, LaTeX
# preamble and Lua filters pdfmd discovers beside the original stay there.
# --embed-metadata folds them into the file, so it builds the same without
# them:
#   * metadata: the discovered YAML files, merged the way Pandoc merges them
#     (a later file replaces an earlier one, the document replaces both, per
#     top-level key), with the document's own front matter, into ONE block;
#     `pdfmd-options` is merged by pdfmd's own rule instead (the document,
#     then the files in order; the first to name a key wins, mappings
#     field by field), and a file's `no-auto`/`parts` are not carried;
#   * preamble: the preamble file(s) as raw LaTeX at the head of the
#     document's `header-includes` (a literal block, the one shape
#     wrap_latex_header_includes and document_header_includes both read);
#   * lua: each filter as a fenced `{=pdfmd}` raw block at the very bottom
#     (Pandoc ignores raw blocks of formats it does not know, so even a
#     reader that never extracts them prints nothing), or, with --lua-mode
#     ref, as a path in `pdfmd-options.lua-filter`.
# The kinds embedded are listed in the file's own `pdfmd-options: no-auto`, so
# the discovery that would find them a second time stays off.
EMBED_KINDS = ("metadata", "preamble", "lua", "bibliography")
# A LaTeX comment line closing the embedded preamble inside `header-includes`:
# document_header_file puts the front-matter macro definitions there, after
# the preamble that defines them and before the document's own additions,
# the order a normal build gives them.
PREAMBLE_END_MARK = "% pdfmd: end of embedded preamble"
LUA_MODES = ("embed", "ref", "apply", "off")
EMBED_BLOCK_RE = re.compile(
    r"^(?P<fence>`{3,})\{=pdfmd\}[ \t]*\n(?P<body>.*?)\n(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL)
# Never carried from a metadata file into the document: they are read from the
# document's own front matter only (effective_no_auto, parts_setting).
FILE_ONLY_OPTION_KEYS = frozenset({"no-auto", "parts"})


# What the command line asks of --embed-metadata: `kinds` None = not named
# (the document's own `pdfmd-options.embed` decides), `lua_mode` None likewise,
# `off` = --no-embed-metadata.
EmbedRequest = namedtuple("EmbedRequest", "kinds lua_mode off")


def parse_embed_option(value) -> tuple[frozenset[str], str | None] | None:
    """``pdfmd-options.embed``: ``true`` (all four kinds), ``false``, a list
    of kinds, or a mapping -- ``metadata``/``preamble`` as true/false (each on
    unless said otherwise), ``lua`` as a --lua-mode (or true = embed, false =
    off). Returns (kinds, lua mode or None), or None when it asks for nothing."""
    if value is None or value is False:
        return None
    text = str(value).strip().casefold()
    if value is True or text in {"true", "yes", "on", "all"}:
        return frozenset(EMBED_KINDS), None
    if text in {"false", "no", "off", "none"}:
        return None
    if isinstance(value, list):
        return frozenset(str(item) for item in value if str(item) in EMBED_KINDS), None
    if isinstance(value, dict):
        kinds = {kind for kind in ("metadata", "preamble", "bibliography")
                 if value.get(kind, True) not in (False, "false", "no", "off")}
        lua = value.get("lua", True)
        mode = None
        if lua is False or str(lua).casefold() in {"false", "no", "off"}:
            mode = "off"
        elif isinstance(lua, str) and lua in LUA_MODES:
            mode = lua
        kinds.add("lua")
        return frozenset(kinds), mode
    return None


def resolve_embed(md_path: Path, metadata_files: list[Path],
                  request: "EmbedRequest | None") -> tuple[frozenset[str], str] | None:
    """What to embed for ``md_path`` (kinds, lua mode), or None: the command
    line first (--embed-metadata KIND.., --lua-mode, --no-embed-metadata),
    else the document's `pdfmd-options.embed` (then its metadata files',
    in order -- the first to name it wins), else the defaults (all four
    kinds, lua embedded) when --embed-metadata was given bare."""
    if request is None or request.off:
        return None
    wanted = None
    option_mode = None
    sources = [frontmatter_pdfmd_options(md_path)]
    for metadata_file in metadata_files:
        found = metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append(found if isinstance(found, dict) else {})
    for options in sources:
        if "embed" in options:
            wanted = parse_embed_option(options["embed"])
            if wanted is not None:
                option_mode = wanted[1]
            break
    if request.kinds is not None:
        kinds = request.kinds
    elif wanted is not None:
        kinds = wanted[0]
    else:
        return None
    return kinds, request.lua_mode or option_mode or "embed"


class EmbedPlan:
    """What --embed-metadata folds into one assembled file."""

    def __init__(self, kinds: frozenset[str], lua_mode: str, metadata_files: list[Path],
                 preamble_files: list[Path], lua_filters: list[Path]):
        self.kinds = kinds
        self.lua_mode = lua_mode
        self.metadata_files = metadata_files
        self.preamble_files = preamble_files
        self.lua_filters = lua_filters
        self.output: Path | None = None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized_source(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n") + "\n"


def mask_embedded_blocks(text: str) -> str:
    """``text`` with every embedded block's characters blanked (newlines and
    length kept, so positions still line up): what the BUILD NOTES and
    marker searches look at, so a Lua filter's own text never matches them.
    """
    return EMBED_BLOCK_RE.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)


def render_embedded_block(kind: str, name: str, source: str, path: str | None = None) -> str:
    """One embedded file as a fenced `{=pdfmd}` block. ``path`` (bibliography
    and CSL files) is the name the document's metadata gives the file, which
    is where it is written back to when the block is extracted."""
    source = normalized_source(source)
    longest = max((len(run) for run in re.findall(r"`+", source)), default=0)
    fence = "`" * max(3, longest + 1)
    name = re.sub(r"[\r\n]", " ", name)
    clean_path = re.sub(r"[\r\n]", " ", path) if path else ""
    where = f"path: {clean_path}\n" if path else ""
    return (f"{fence}{{=pdfmd}}\ntype: {kind}\nname: {name}\n{where}sha256: {sha256_text(source)}\n\n"
            f"{source.rstrip(chr(10))}\n{fence}\n")


def safe_relative_path(name: str) -> str:
    """A relative path for writing an embedded file back: as the metadata
    names it, unless that is absolute or climbs out (then just the file name)."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return path.name or "file"
    return str(path)


def parse_embedded_blocks(text: str) -> list[dict]:
    blocks = []
    for match in EMBED_BLOCK_RE.finditer(text):
        head, separator, rest = match.group("body").partition("\n\n")
        if not separator:
            continue
        fields = {}
        for line in head.splitlines():
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        source = rest + "\n"
        blocks.append({"type": fields.get("type", ""), "name": fields.get("name") or "filter.lua",
                       "path": fields.get("path"),
                       "declared": fields.get("sha256"), "source": source,
                       "sha256": sha256_text(source)})
    return blocks


# What this machine's pdfmd has itself written: the SHA-256 of each embedded
# filter, one per line. A block whose own text hashes to one of these is the
# text pdfmd wrote here (not edited since, not from another machine), so it is
# run; any other embedded filter is code from elsewhere -- a Lua filter can
# run any command -- and is skipped, with a warning, unless --trust-embedded.
def trust_store_path() -> Path:
    return cache_root() / "embedded-trust.txt"


def trusted_hashes() -> set[str]:
    try:
        return {line.split()[0] for line in
                trust_store_path().read_text(encoding="utf-8").splitlines() if line.strip()}
    except OSError:
        return set()


def remember_trusted(entries: list[tuple[str, str]]) -> None:
    known = trusted_hashes()
    fresh = [(digest, name) for digest, name in entries if digest not in known]
    if not fresh:
        return
    try:
        trust_store_path().parent.mkdir(parents=True, exist_ok=True)
        with trust_store_path().open("a", encoding="utf-8") as handle:
            for digest, name in fresh:
                handle.write(f"{digest} {name}\n")
    except OSError:
        pass


@contextmanager
def embedded_lua_filters(md_path: Path, allowed: bool, trust_all: bool) -> Iterator[list[Path]]:
    """Yield temp files for the Lua filters embedded in ``md_path`` (see the
    comment above EMBED_KINDS) that may run; the files are removed afterwards.
    ``allowed`` False (a CLI --no-auto lua) yields none.
    """
    if not allowed or md_path.suffix.lower() not in (".md", ".markdown"):
        yield []
        return
    try:
        blocks = [block for block in parse_embedded_blocks(md_path.read_text(encoding="utf-8-sig"))
                  if block["type"] == "lua-filter"]
    except (OSError, UnicodeDecodeError):
        blocks = []
    if not blocks:
        yield []
        return
    known = trusted_hashes()
    folder = Path(mkdtemp(prefix="pdfmd-embedded-"))
    try:
        paths: list[Path] = []
        for index, block in enumerate(blocks, 1):
            label = Path(block["name"]).name or "filter.lua"
            if not (trust_all or block["sha256"] in known):
                print(f"WARN  {display_path(md_path)}: the embedded Lua filter '{label}' was not run: "
                      "it was not written by this pdfmd (or was edited since), and a Lua filter can "
                      "run any command. Read it, then use --trust-embedded to run it", file=sys.stderr)
                continue
            target = folder / f"{index:02d}-{label}"
            target.write_text(block["source"], encoding="utf-8", newline="\n")
            paths.append(target)
            print(f"AUTO LUA  {display_path(md_path)}: embedded filter {label}")
        yield paths
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def split_preamble_parts(preamble_text: str, record: list) -> list[tuple[str, str]] | None:
    """Cut the embedded preamble back into the files it was made from, by the
    line counts recorded in `origin.preamble`; None if the text no longer
    matches their hashes (it was edited), so the caller keeps it whole."""
    lines = preamble_text.strip("\n").split("\n")
    pieces = []
    for item in record:
        count = item.get("lines") if isinstance(item, dict) else None
        if not isinstance(count, int) or count > len(lines):
            return None
        part = "\n".join(lines[:count])
        lines = lines[count:]
        if sha256_text(part) != item.get("sha256"):
            return None
        pieces.append((str(item.get("name") or "preamble.tex"), part + "\n"))
    return pieces if not any(line.strip() for line in lines) else None


def unpack_assembled(path: Path, out_dir: Path | None, slim: bool = False) -> int:
    """--unpack: write what an assembled file embeds back out as files, and
    check each embedded filter's hash. Never overwrites. With ``slim`` it
    then rewrites the file itself without what was unpacked -- the original
    layout, a lean document plus its ``NAME.unpacked/`` folder, which pdfmd
    discovers again (see accessory_directories). Returns the exit status: 1
    if a filter does not match its recorded hash (edited since pdfmd wrote
    it) or nothing could be unpacked."""
    text = path.read_text(encoding="utf-8-sig")
    if not is_assembled_text(text):
        raise SystemExit(f"{display_path(path)} is not an assembled file (no {ASSEMBLED_KEY} marker)")
    default_target = path.with_name(f"{path.stem}{UNPACKED_SUFFIX}")
    target = out_dir or default_target
    files: dict[str, str] = {}
    notes: list[str] = []
    mismatch = False
    known = trusted_hashes()
    taken: set[str] = set()

    def unique(name: str) -> str:
        candidate, number = name, 1
        while candidate in taken:
            number += 1
            original = PurePosixPath(name)
            candidate = str(original.with_name(f"{original.stem}-{number}{original.suffix}"))
        taken.add(candidate)
        return candidate

    all_blocks = parse_embedded_blocks(text)
    blocks = [block for block in all_blocks if block["type"] == "lua-filter"]
    data_blocks = [block for block in all_blocks if block["type"] in ("bibliography", "csl")]
    for block in data_blocks:
        name = unique(safe_relative_path(block["path"] or block["name"]))
        files[name] = block["source"]
        if block["declared"] == block["sha256"]:
            state = "hash matches what was written"
        else:
            mismatch = True
            state = "HASH MISMATCH: edited since it was written" if block["declared"] else "no hash recorded"
        label = "CSL" if block["type"] == "csl" else "BIBLIO"
        notes.append(f"{label:<10}{name}  ({state})")
    for block in blocks:
        name = unique(Path(block["name"]).name or "filter.lua")
        files[name] = block["source"]
        if block["declared"] == block["sha256"]:
            state = "hash matches what was written"
        else:
            mismatch = True
            state = ("HASH MISMATCH: edited since it was written" if block["declared"]
                     else "no hash recorded")
        trust = ("known to this machine's pdfmd" if block["sha256"] in known
                 else "NOT known to this machine's pdfmd (needs --trust-embedded to run)")
        notes.append(f"LUA       {name}  ({state}; {trust})")
    front = re.match(r"^---[ \t]*\n(?P<yaml>.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    data: dict | None = None
    options: dict = {}
    embedded: list = []
    origin = None
    kept_header = ""
    preamble_unpacked = metadata_unpacked = False
    if front and yaml is not None:
        try:
            loaded = yaml.safe_load(front.group("yaml"))
        except yaml.YAMLError:
            loaded = None
        if isinstance(loaded, dict):
            data = loaded
    if data is not None:
        data.pop(ASSEMBLED_KEY, None)
        header = header_includes_text(data.get("header-includes"))
        raw_options = data.get("pdfmd-options")
        options = raw_options if isinstance(raw_options, dict) else {}
        embedded = options.get("embedded") or []
        origin = options.get("origin") if isinstance(options.get("origin"), dict) else None
        preamble_text, marker, own_header = header.partition(PREAMBLE_END_MARK)
        kept_header = own_header.strip("\n") if marker else header
        if marker and preamble_text.strip():
            pieces = split_preamble_parts(preamble_text, (origin or {}).get("preamble") or [])
            if pieces is None:
                pieces = [("preamble.tex", preamble_text.strip("\n") + "\n")]
                detail = "kept whole: no usable record of the files it was made from"
            else:
                detail = "the part of header-includes before the preamble marker"
            for name, part in pieces:
                files[unique(name)] = part
                notes.append(f"PREAMBLE  {name}  ({detail})")
            preamble_unpacked = True
        if "metadata" in embedded:
            if origin and isinstance(origin.get("files"), dict) and origin["files"]:
                labels = list(origin["files"])
                for index, label in enumerate(labels, 1):
                    piece: dict = {}
                    sub_options: dict = {}
                    for key in origin["files"][label]:
                        if key.startswith("pdfmd-options."):
                            sub = key.split(".", 1)[1]
                            if sub in options:
                                sub_options[sub] = options[sub]
                        elif key == "header-includes":
                            if kept_header:
                                piece[key] = kept_header
                        elif key in data:
                            piece[key] = data[key]
                    if sub_options:
                        piece["pdfmd-options"] = sub_options
                    name = unique(f"{index:02d}-{label}" if len(labels) > 1 else label)
                    files[name] = yaml.dump(piece, Dumper=_EmbedDumper, sort_keys=False,
                                            allow_unicode=True, default_flow_style=False, width=10**6)
                    notes.append(f"METADATA  {name}  (the keys that came from {label})")
            else:
                rest = {key: value for key, value in data.items()
                        if key not in ("header-includes", "pdfmd-options", PARTIAL_KEY)}
                files[unique("metadata.yaml")] = yaml.dump(
                    rest, Dumper=_EmbedDumper, sort_keys=False, allow_unicode=True,
                    default_flow_style=False, width=10**6)
                notes.append("METADATA  metadata.yaml  (the merged front matter: this file records no "
                             "origin of its keys, so it can't be told from the document's own)")
            metadata_unpacked = bool(origin and origin.get("files"))
    if not files:
        print(f"NOTHING   {display_path(path)} embeds nothing to unpack")
        return 1
    def same_on_disk(name: str) -> bool:
        try:
            return (target / name).read_text(encoding="utf-8") == files[name]
        except (OSError, UnicodeDecodeError):
            return False

    # A file that is already there with exactly this content is not in the way
    # (so `--unpack` followed by `--unpack --slim` works); a different one is.
    clashes = [name for name in files if (target / name).exists() and not same_on_disk(name)]
    if clashes:
        raise SystemExit(f"{display_path(target)} already holds {', '.join(clashes)}, different from "
                         "what the file embeds; nothing was written (remove them, or give another -o folder)")
    target.mkdir(parents=True, exist_ok=True)
    fresh = [name for name in files if not (target / name).exists()]
    for name in fresh:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_text(files[name], encoding="utf-8", newline="\n")
    for note in notes:
        print(note)
    kept = len(files) - len(fresh)
    print(f"UNPACKED  {len(fresh)} file{'s' if len(fresh) != 1 else ''} into {display_path(target)}"
          + (f" ({kept} already there, identical)" if kept else ""))
    if slim:
        if target.resolve() != default_target.resolve():
            print(f"WARN  --slim: pdfmd finds {default_target.name}/ beside the document by itself; "
                  f"{display_path(target)} it will not, unless you move it there", file=sys.stderr)
        slim_assembled(path, text, front, data, options, kept_header, blocks,
                       preamble_unpacked, metadata_unpacked, origin, bool(data_blocks))
    return 1 if mismatch else 0


def slim_assembled(path: Path, text: str, front, data: dict | None, options: dict, kept_header: str,
                   blocks: list, preamble_unpacked: bool, metadata_unpacked: bool, origin,
                   bibliography_unpacked: bool = False) -> None:
    """Rewrite ``path`` without what --unpack just wrote out (the embedded
    filter blocks, the preamble in header-includes, the keys that came from
    metadata files -- the last only where the file records their origin).
    What is left is the document's own: with its `NAME.unpacked/` folder, the
    original layout."""
    body = text[front.end():] if front else text
    body = EMBED_BLOCK_RE.sub("", body).rstrip("\n") + "\n"
    removed = []
    if data is None:
        # No front matter: only the comment-form marker carries the kinds.
        body = ASSEMBLED_COMMENT_RE.sub(ASSEMBLED_COMMENT, body)
        path.write_text(body, encoding="utf-8", newline="\n")
        print(f"SLIMMED   {display_path(path)}  (embedded files removed)")
        return
    data = dict(data)
    options = dict(options)
    if metadata_unpacked and origin:
        for keys in origin["files"].values():
            for key in keys:
                if key.startswith("pdfmd-options."):
                    options.pop(key.split(".", 1)[1], None)
                else:
                    data.pop(key, None)
        removed.append("metadata")
    if preamble_unpacked:
        removed.append("preamble")
    # What stays in header-includes: the document's own part (all of it when
    # no preamble was embedded), unless a metadata file owned the key.
    if metadata_unpacked and origin and "header-includes" in sum(origin["files"].values(), []):
        kept_header = ""
    if blocks:
        removed.append("lua")
    if bibliography_unpacked:
        removed.append("bibliography")
    gone = [kind for kind in removed if kind in (options.get("embedded") or [])]
    if isinstance(options.get("no-auto"), list):
        options["no-auto"] = [kind for kind in options["no-auto"] if kind not in gone]
        if not options["no-auto"]:
            del options["no-auto"]
    if "embedded" in options:
        options["embedded"] = [kind for kind in options["embedded"] if kind not in gone]
        if not options["embedded"]:
            del options["embedded"]
    if metadata_unpacked:
        options.pop("origin", None)
    elif isinstance(options.get("origin"), dict):
        options["origin"].pop("preamble", None)
        if not options["origin"].get("files") and not options["origin"].get("document"):
            del options["origin"]
    data.pop("pdfmd-options", None)
    out = {ASSEMBLED_KEY: True, **{k: v for k, v in data.items() if k != "header-includes"}}
    if options:
        out["pdfmd-options"] = options
    dumped = yaml.dump(out, Dumper=_EmbedDumper, sort_keys=False, allow_unicode=True,
                       default_flow_style=False, width=10**6)
    head = "---\n" + dumped + (literal_block("header-includes", kept_header) if kept_header else "") + "---\n\n"
    path.write_text(head + body.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"SLIMMED   {display_path(path)}  (removed: {', '.join(removed) or 'nothing'})")


_RESOURCE_OWNER: Path | None = None


@contextmanager
def embedded_resources(md_path: Path) -> Iterator[None]:
    """For the length of a build of ``md_path``: write the document's embedded
    bibliography/CSL blocks into a temporary folder at the path its metadata
    names them by, and register that folder (and the document's
    ``NAME.unpacked/``, if there is one) in EMBEDDED_RESOURCE_DIRS. A nested
    call for the same document (the cache route re-enters the converter) is a
    no-op. These are data, not code, so -- unlike filters -- no trust is asked."""
    global _RESOURCE_OWNER
    if _RESOURCE_OWNER == md_path or md_path.suffix.lower() not in (".md", ".markdown"):
        yield
        return
    folder: Path | None = None
    added: list[Path] = []
    try:
        blocks = [block for block in parse_embedded_blocks(md_path.read_text(encoding="utf-8-sig"))
                  if block["type"] in ("bibliography", "csl")]
    except (OSError, UnicodeDecodeError):
        blocks = []
    if blocks:
        folder = Path(mkdtemp(prefix="pdfmd-resources-"))
        for block in blocks:
            target = folder / safe_relative_path(block["path"] or block["name"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(block["source"], encoding="utf-8", newline="\n")
        added.append(folder)
    unpacked = md_path.parent / f"{md_path.stem}{UNPACKED_SUFFIX}"
    if unpacked.is_dir():
        added.append(unpacked.resolve())
    if not added:
        yield
        return
    _RESOURCE_OWNER = md_path
    EMBEDDED_RESOURCE_DIRS.extend(added)
    try:
        yield
    finally:
        for item in added:
            if item in EMBEDDED_RESOURCE_DIRS:
                EMBEDDED_RESOURCE_DIRS.remove(item)
        _RESOURCE_OWNER = None
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)


def merge_option_dicts(sources: list[dict]) -> dict:
    """Merge ``pdfmd-options`` mappings; an earlier one wins, mappings are
    merged field by field (the cascade pdfmd's own readers apply)."""
    merged: dict = {}
    for source in sources:
        for key, value in source.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = merge_option_dicts([merged[key], value])
    return merged


class _EmbedDumper(yaml.SafeDumper if yaml is not None else object):
    pass


if yaml is not None:
    _EmbedDumper.add_representer(
        str, lambda dumper, value: dumper.represent_scalar(
            "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None))


def literal_block(key: str, text: str) -> str:
    """``key: |`` and the text indented under it, written by hand: PyYAML will
    not emit a literal block for text with trailing spaces, and pdfmd's
    header-includes readers want exactly this shape."""
    lines = text.replace("\r\n", "\n").strip("\n").split("\n")
    return f"{key}: |\n" + "".join(f"  {line}\n" if line.strip() else "\n" for line in lines)


def header_includes_text(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item is not None)
    return "" if value is None else str(value)


def strip_embedded_option_names(options: dict, kinds: frozenset[str], lua_mode: str) -> None:
    """Drop from ``options`` the file names (see option_names) of the kinds
    now embedded: they point into the original folder, and the content is
    in the file. Also `embed`, the instruction that asked for this."""
    options.pop("embed", None)
    grouped = options.get("metadata")
    if "metadata" in kinds:
        options.pop("yaml", None)
        if isinstance(grouped, dict):
            grouped.pop("yaml", None)
            grouped.pop("metadata", None)
        else:
            options.pop("metadata", None)
    if "preamble" in kinds:
        options.pop("preamble", None)
        if isinstance(grouped, dict):
            grouped.pop("preamble", None)
    if "lua" in kinds and lua_mode != "off":
        options.pop("lua-filter", None)
        if isinstance(grouped, dict):
            grouped.pop("lua-filter", None)
            grouped.pop("lua", None)
    if isinstance(grouped, dict) and not grouped:
        del options["metadata"]


def relative_filter_path(target: Path, output: Path | None) -> str:
    if output is None:
        return str(target)
    try:
        return Path(os.path.relpath(target, output.resolve().parent)).as_posix()
    except ValueError:
        return target.as_posix()


def lua_checks_format(path: Path) -> bool:
    """Whether a Lua filter looks at Pandoc's FORMAT. In the Markdown-to-
    Markdown pass --lua-mode apply runs, FORMAT is `markdown`, not what the
    real build's would be (latex, ...), so such a filter would behave
    differently there; it is embedded instead and runs in the real build."""
    try:
        return bool(re.search(r"\bFORMAT\b", path.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeDecodeError):
        return True


def apply_lua_filters(front_text: str, body: str, filters: list[Path], first: Path,
                      metadata_files: list[Path]) -> str | None:
    """Run ``filters`` over the document, Markdown in and Markdown out, and
    return the new body; None if Pandoc fails (the caller then embeds them
    instead). Only the body comes back: Pandoc's Markdown writer without
    --standalone drops the metadata, which the caller writes itself -- so a
    filter's change to the metadata, and a citation it needs resolved first
    (no --citeproc here), are not reproduced. Pandoc re-writes the text
    (tables, footnotes and line breaks may come out formatted differently).
    """
    folder = Path(mkdtemp(prefix="pdfmd-apply-"))
    try:
        source = folder / "input.md"
        source.write_text(front_text + body, encoding="utf-8", newline="\n")
        reader = resolve_from_format(source, None, metadata_files)[0] or "markdown"
        cmd = ["pandoc", str(source), "-f", reader, "-t", reader, "--wrap=preserve"]
        for metadata_file in metadata_files:
            cmd += ["--metadata-file", str(metadata_file)]
        for lua_filter in filters:
            cmd += ["--lua-filter", str(lua_filter)]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=first.parent)
        if result.returncode != 0:
            print(f"WARN  --lua-mode apply: Pandoc failed ({result.stderr.strip().splitlines()[-1:] or ['?']}); "
                  "the filters are embedded instead", file=sys.stderr)
            return None
        return result.stdout
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def embed_into_text(text: str, first: Path, plan: EmbedPlan, partial: bool = False) -> str:
    """Fold what ``plan`` names into the joined assembled ``text`` (see the
    comment above EMBED_KINDS); ``first`` is the document whose own front
    matter is merged (the scaffold, or a report's first chapter)."""
    if yaml is None:
        raise SystemExit("--embed-metadata needs PyYAML (pip install pyyaml)")
    kinds = plan.kinds
    front = re.match(r"^---[ \t]*\n(?P<yaml>.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    body = text[front.end():] if front else text
    document: dict = {}
    if front:
        try:
            loaded = yaml.safe_load(front.group("yaml"))
        except yaml.YAMLError as error:
            raise SystemExit(f"{display_path(first)}: its front matter does not parse as YAML "
                             f"({str(error).splitlines()[0]}); --embed-metadata cannot merge into it")
        document = loaded if isinstance(loaded, dict) else {}
    to_embed: list[Path] = list(plan.lua_filters) if plan.lua_mode == "embed" else []
    applied: list[Path] = []
    gated: list[Path] = []
    if "lua" in kinds and plan.lua_filters and plan.lua_mode == "apply":
        runnable = [item for item in plan.lua_filters if not lua_checks_format(item)]
        gated = [item for item in plan.lua_filters if item not in runnable]
        to_embed = list(gated)
        if runnable:
            new_body = apply_lua_filters(text[:front.end()] if front else "", body, runnable, first,
                                         plan.metadata_files if "metadata" in kinds else [])
            if new_body is None:
                to_embed = list(plan.lua_filters)
                gated = []
            else:
                applied = runnable
                body = new_body
                text = (text[:front.end()] if front else "") + body
    left_out = []
    if ("preamble" in kinds and plan.preamble_files and not front and not plan.metadata_files
            and promote_bare_title(text, False)[1]):
        # A new front-matter block would stop the leading `# Title` being
        # promoted to the document's title (see promote_bare_title).
        print(f"WARN  {display_path(first)}: has no front matter and starts with a bare '# Title'; "
              "embedding a preamble would change how that reads, so it was left out. Give the "
              "document front matter (a `title:`) to embed it", file=sys.stderr)
        kinds = kinds - {"preamble"}
        left_out.append("preamble " + ", ".join(item.name for item in plan.preamble_files) + " (left out)")
    no_auto = [kind for kind in EMBED_KINDS
               if kind in kinds and kind != "bibliography"  # nothing discovers a bibliography: it is named
               and not (kind == "lua" and plan.lua_mode in ("ref", "off"))]
    if plan.lua_mode == "off":
        no_auto = [kind for kind in no_auto if kind != "lua"]
    blocks = ""
    lua_refs: list[str] = []
    entries: list[tuple[str, str]] = []
    if "lua" in kinds and plan.lua_filters:
        for lua_filter in to_embed:
            source = lua_filter.read_text(encoding="utf-8-sig")
            blocks += "\n" + render_embedded_block("lua-filter", lua_filter.name, source)
            entries.append((sha256_text(normalized_source(source)), lua_filter.name))
        if plan.lua_mode == "ref":
            lua_refs = [relative_filter_path(item, plan.output) for item in plan.lua_filters]
    # ---- metadata: files lowest, the document over them
    merged: dict = {}
    file_options: list[dict] = []
    # Which source each key finally came from ("document", or a metadata
    # file's name): written to `pdfmd-options.origin`, so --unpack can split
    # the merged front matter back into the files it was made from.
    owner: dict[str, str] = {}
    labels: list[str] = []
    option_labels: list[str] = []
    if "metadata" in kinds:
        for metadata_file in plan.metadata_files:
            label = metadata_file.name
            while label in labels:
                label = f"{metadata_file.parent.name}-{label}"
            labels.append(label)
            data = metadata_file_yaml(metadata_file)
            options = data.pop("pdfmd-options", None)
            if isinstance(options, dict):
                file_options.append({key: value for key, value in options.items()
                                     if key not in FILE_ONLY_OPTION_KEYS})
                option_labels.append(label)
            for key in data:
                owner[key] = label
            merged.update(data)
    document = dict(document)
    document_options = document.pop("pdfmd-options", None)
    for key in document:
        owner[key] = "document"
    merged.update(document)
    option_owner: dict[str, str] = {}
    for label, source in [("document", document_options if isinstance(document_options, dict) else {}),
                          *zip(option_labels, file_options)]:
        for key in source:
            option_owner.setdefault(key, label)
    options = merge_option_dicts([document_options if isinstance(document_options, dict) else {},
                                  *file_options])
    # ---- bibliography and CSL files the metadata names: data, embedded as blocks
    references: list[tuple[str, str]] = []
    for key in ("bibliography", "csl"):
        value = merged.get(key)
        for name in ([value] if isinstance(value, str) else
                     [str(item) for item in value] if isinstance(value, list) else []):
            if "://" not in name and (key, name) not in references:
                references.append((key, name))
    bib_embedded: list[str] = []
    bib_problems: list[str] = []
    renamed: dict[str, str] = {}
    if "bibliography" in kinds and references:
        search: list[Path] = []
        for directory in ([plan.metadata_files[0].parent] if plan.metadata_files else []) + [
                first.parent, *(item.parent for item in plan.metadata_files),
                first.parent / ACCESSORY_DIRNAME, first.parent / f"{first.stem}{UNPACKED_SUFFIX}", Path.cwd()]:
            if directory not in search:
                search.append(directory)
        data_dir = pandoc_user_data_dir()
        for key, name in references:
            reference = Path(name)
            # A CSL style is also looked up in Pandoc's own user data folder (csl/).
            where = search + ([data_dir / "csl", data_dir] if key == "csl" and data_dir else [])
            found = reference if reference.is_absolute() and reference.is_file() else next(
                ((directory / reference) for directory in where if (directory / reference).is_file()), None)
            if found is None:
                bib_problems.append(f"{name} (not found in the document's folders"
                                    + (" or Pandoc's csl/ folder" if key == "csl" else "") + ")")
                continue
            try:
                source = found.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                bib_problems.append(f"{name} (not UTF-8 text)")
                continue
            safe = safe_relative_path(name)
            blocks += "\n" + render_embedded_block("csl" if key == "csl" else "bibliography",
                                                   found.name, source, path=safe)
            bib_embedded.append(name)
            if safe != name:
                # An absolute or `../` name cannot be written back as it is: the
                # metadata then names the embedded file by its safe path.
                renamed[name] = safe
    for key in ("bibliography", "csl"):
        value = merged.get(key)
        if renamed and isinstance(value, str):
            merged[key] = renamed.get(value, value)
        elif renamed and isinstance(value, list):
            merged[key] = [renamed.get(str(item), item) for item in value]
    strip_embedded_option_names(options, kinds, plan.lua_mode)
    if lua_refs:
        options["lua-filter"] = lua_refs
    if labels and "metadata" in kinds:
        origin: dict = {"document": [], "files": {label: [] for label in labels}}
        for key, label in owner.items():
            (origin["document"] if label == "document" else origin["files"][label]).append(key)
        for key, label in option_owner.items():
            # Bookkeeping keys, and the ones this file replaces with its own
            # embedded copy, are not part of any source.
            if (key in ("embedded", "origin", "applied-lua", "embed")
                    or (key in ("yaml", "metadata") and "metadata" in kinds)
                    or (key == "preamble" and "preamble" in kinds)
                    or (key == "lua-filter" and "lua" in kinds)):
                continue
            (origin["document"] if label == "document" else origin["files"][label]).append(f"pdfmd-options.{key}")
        options["origin"] = origin
    embedded_now = [kind for kind in EMBED_KINDS if kind in kinds and not (
        (kind == "lua" and plan.lua_mode in ("ref", "off")) or (kind == "preamble" and not plan.preamble_files)
        or (kind == "bibliography" and not bib_embedded))]
    if embedded_now:
        options["embedded"] = embedded_now
    if applied:
        options["applied-lua"] = [item.name for item in applied]
    if no_auto:
        existing = options.get("no-auto")
        if existing is True or (isinstance(existing, str) and existing.casefold() in {"true", "yes", "on", "all"}):
            pass  # everything is already off
        else:
            current = ([] if existing is None or existing is False else
                       [existing] if isinstance(existing, str) else [str(item) for item in existing])
            options["no-auto"] = [*current, *(kind for kind in no_auto if kind not in current)]
    # ---- preamble: raw LaTeX at the head of header-includes
    header_parts = []
    if "preamble" in kinds:
        header_parts += [item.read_text(encoding="utf-8-sig") for item in plan.preamble_files]
        if plan.preamble_files:
            preamble_record = [{"name": item.name, "lines": len(part.strip("\n").split("\n")),
                                "sha256": sha256_text(part.strip("\n"))}
                               for item, part in zip(plan.preamble_files, header_parts)
                               if part.strip()]
            options.setdefault("origin", {})["preamble"] = preamble_record
    own_header = header_includes_text(merged.pop("header-includes", None))
    if own_header:
        header_parts.append(own_header)
    if "preamble" in kinds and plan.preamble_files:
        header_parts.insert(len(plan.preamble_files), PREAMBLE_END_MARK)
    header_text = "\n".join(part.strip("\n") for part in header_parts if part.strip())
    # Nothing but the two bookkeeping keys to say, and no front matter to put
    # them in: the comment form of the marker carries it instead, so the
    # document does not gain a front-matter block (see mark_assembled).
    if front or merged or header_text or (set(options) - {"embedded", "no-auto", "applied-lua"}):
        out: dict = {ASSEMBLED_KEY: True}
        if partial:
            out[PARTIAL_KEY] = True
        out.update(merged)
        if options:
            out["pdfmd-options"] = options
        dumped = yaml.dump(out, Dumper=_EmbedDumper, sort_keys=False, allow_unicode=True,
                           default_flow_style=False, width=10**6)
        head = "---\n" + dumped + (literal_block("header-includes", header_text) if header_text else "") + "---\n\n"
        result = head + body.lstrip("\n").rstrip("\n") + "\n"
    else:
        result = mark_assembled(text, no_auto, partial)
    if entries:
        remember_trusted(entries)
    if blocks:
        result = result.rstrip("\n") + "\n" + blocks
    summary = []
    if "metadata" in kinds and plan.metadata_files:
        summary.append("metadata " + ", ".join(item.name for item in plan.metadata_files))
    if "preamble" in kinds and plan.preamble_files:
        summary.append("preamble " + ", ".join(item.name for item in plan.preamble_files))
    if "lua" in kinds and plan.lua_filters and plan.lua_mode != "off":
        if plan.lua_mode == "apply":
            if applied:
                summary.append("lua (applied) " + ", ".join(item.name for item in applied))
            if to_embed:
                reason = "checks FORMAT" if gated else "apply failed"
                summary.append(f"lua (embedded instead: {reason}) " + ", ".join(item.name for item in to_embed))
        else:
            summary.append(f"lua ({plan.lua_mode}) " + ", ".join(item.name for item in plan.lua_filters))
    if bib_embedded:
        summary.append("bibliography " + ", ".join(bib_embedded))
    for problem in bib_problems:
        print(f"WARN  not embedded: {problem}", file=sys.stderr)
    summary += left_out
    print("EMBEDDED  " + ("; ".join(summary) if summary else "nothing was found to embed"))
    # What the text points at is not embedded: say which of it the file still needs.
    outside: list[str] = []
    for key in ("bibliography", "csl"):
        names = [name for kind, name in references if kind == key and name not in bib_embedded]
        if names:
            outside.append(f"{key} {', '.join(names)}")
    if re.search(r"\\(?:input|include|includegraphics)\b", header_text):
        outside.append("files the preamble reads (\\input, \\includegraphics)")
    if re.search(r"!\[[^\]\n]*\]\(", body):
        outside.append("the images in the text")
    if outside:
        print("NOTE  not embedded: " + "; ".join(outside) + " -- keep them where the document "
              "finds them (relative to the assembled file's folder)")
    if summary:
        print("NOTE  never embedded, and not detected: data a macro in the text reads (CSV tables "
              "for plots, images in raw LaTeX) -- they stay beside the document")
    return result


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
    # Not a Pandoc writer: pdfmd's own "stop after assembling" stage (--stop-at
    # markdown / --assemble-only). See write_assembled_markdown().
    ASSEMBLED_FORMAT: ASSEMBLED_SUFFIX,
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
                    verbose: bool, cwd: Path | None = None,
                    env: dict | None = None) -> tuple[bool, str]:
    """Run ``engine`` on ``tex_path`` to completion, output landing in
    ``output_dir``. Returns (success, one-line failure reason -- empty on
    success). Always run with cwd=tex_path.parent, so a raw \\input/
    \\includegraphics/\\bibliography relative path beside the source keeps
    resolving; only *output* is redirected via -output-directory/-o. ``cwd``
    and ``env`` override that for a .tex generated elsewhere from Markdown
    (the cache route): cwd is then Pandoc's own working directory and env
    carries TEXINPUTS, exactly as the Pandoc-run engine would have had.
    """
    work_dir = cwd or tex_path.parent
    log_path = output_dir / f"{tex_path.stem}.log"

    def log_text() -> str:
        return log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""

    def run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
        log_cmd(cmd, cwd, verbose)
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env)

    engine_env = env
    cmd = latex_engine_command(engine, tex_path, output_dir)
    if cmd is None:
        return False, f"{engine} is not supported for direct .tex compilation"

    if engine in ("latexmk", "tectonic"):
        # Both already handle reruns and bibtex/biber internally.
        result = run(cmd, work_dir, env=engine_env)
        if result.returncode != 0 or not (output_dir / f"{tex_path.stem}.pdf").exists():
            return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""
        return True, ""

    result = run(cmd, work_dir, env=engine_env)
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
        bib_env = (engine_env or os.environ).copy()
        bib_env["BIBINPUTS"] = f"{work_dir}{os.pathsep}{tex_path.parent}{os.pathsep}{bib_env.get('BIBINPUTS', '')}"
        bib_cmd = (["biber", f"--input-directory={work_dir}", tex_path.stem] if bib_tool == "biber"
                   else ["bibtex", tex_path.stem])
        bib_result = run(bib_cmd, output_dir, env=bib_env)
        if bib_result.returncode != 0:
            print(f"WARN  {tex_path}: {bib_tool} reported errors; continuing"
                  + (f" ({bib_result.stderr.strip().splitlines()[-1]})" if bib_result.stderr.strip() else ""),
                  file=sys.stderr)
        result = run(cmd, work_dir, env=engine_env)
        if result.returncode != 0:
            return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""

    passes = 1
    while tex_wants_rerun(log_text()) and passes < MAX_TEX_DIRECT_PASSES:
        result = run(cmd, work_dir, env=engine_env)
        passes += 1
        if result.returncode != 0:
            return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""
    if verbose:
        print(f"AUTO TEXDIRECT  {tex_path}: {engine}, {passes} pass(es)"
              + (f" + {bib_tool}" if bib_tool else ""))
    return True, ""


# -- The cache route (pdfmd-options: {cache: {aux: true}}) -------------------
# Normally Pandoc writes a .tex into a throwaway directory, runs the engine
# there two or three times, and deletes everything, so every build starts from
# zero: LaTeX's cross-reference files do not exist yet, the first pass can
# only print ?? and ask for another. With cache.aux the same .tex (the very one
# Pandoc would have made: --to latex, standalone) is written into a per-
# document folder under the user's cache directory and compiled there by
# pdfmd's own engine runner (compile_tex_direct), which reruns only while the
# log asks for it -- latexmk's rule. The folder, and LaTeX's .aux inside it,
# survive between builds, so an unchanged document settles in ONE pass, and a
# part of a split document built alone can read the labels the last full build
# left (seed_labels_file), instead of printing ??. Nothing is trusted: a failed
# build wipes that document's LaTeX files and retries from clean, and the final
# PDF is always the product of a pass whose log asked for no further rerun.
CACHE_DEFAULTS = {"aux": False, "plots": False}
LAST_SEEDED = 0   # labels a partial cache build took from the last full build


def cache_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "pdfmd"


def cache_directory(source: Path) -> Path:
    """One folder per document, keyed by its absolute path (two reports both
    called report.md must not share an .aux)."""
    digest = hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:10]
    return cache_root() / f"{digest}-{source.stem}"


def cache_settings(md_path: Path, metadata_files: list[Path], cli: bool | None) -> dict:
    """Effective ``pdfmd-options: {cache: {aux, plots}}``: the document's own
    front matter first, then each linked metadata file, then --cache/--no-cache
    (--cache turns aux on, --no-cache turns everything off)."""
    settings = dict(CACHE_DEFAULTS)
    sources = [frontmatter_pdfmd_options(md_path)]
    for metadata_file in metadata_files:
        options = metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append(options if isinstance(options, dict) else {})
    for options in sources:
        if "cache" not in options:
            continue
        value = options["cache"]
        if isinstance(value, bool):
            value = {"aux": value}
        if isinstance(value, dict):
            for key in settings:
                if key in value:
                    settings[key] = bool(value[key])
        break
    if cli is True:
        settings["aux"] = True
    elif cli is False:
        settings = {key: False for key in settings}
    if CACHE_PLOTS_CLI and cli is not False:
        settings["plots"] = True
    return settings


# LaTeX side of the counter seeding: \pdfmdpart{key}, at the start of each part
# of a cache build, writes the counters' values into the .aux as
# \pdfmd@part{key}{section=2,figure=1,...} (\pdfmd@part is a no-op when the
# .aux is read back) and, if a partial build's seed file defined
# \pdfmd@st@key, runs it: the counters jump to what they were at that point
# of the last full build -- at EVERY selected part, so Discussion+Appendix
# keeps the Appendix's own number. Expandable throughout (\ifcsname), so it is safe inside
# \write, and counters a document does not have are skipped.
PARTS_MARKER_DEFS = r"""\makeatletter
\providecommand\pdfmd@part[2]{}
\newcommand\pdfmd@c[1]{\ifcsname c@#1\endcsname #1=\number\csname c@#1\endcsname,\fi}
\newcommand\pdfmdpart[1]{\immediate\write\@auxout{\string\pdfmd@part{#1}{%
  \pdfmd@c{section}\pdfmd@c{subsection}\pdfmd@c{subsubsection}\pdfmd@c{figure}%
  \pdfmd@c{table}\pdfmd@c{equation}\pdfmd@c{footnote}\pdfmd@c{reaction}\pdfmd@c{scheme}}}%
  \ifcsname pdfmd@st@#1\endcsname\csname pdfmd@st@#1\endcsname\fi}
\makeatother
"""
PART_COUNTER_RE = re.compile(r"^\\pdfmd@part\{([^{}]*)\}\{([^{}]*)\}\s*$")
SEED_LABEL_RE = re.compile(r"^\\newlabel\{([^{}]*)\}(\{.*\})\s*$")


def seed_labels_file(full_aux: Path, target: Path) -> int:
    """Write ``target`` (a .tex fragment) that defines every label of the last
    full build's .aux that a partial build does not define itself, and, per
    part, the counter values at its start (\\pdfmd@st@key, run by
    \\pdfmdpart), so a part's own numbers continue from the full report's
    instead of restarting at 1. Returns the number of labels; 0 writes
    nothing. Defining only the undefined is what keeps a part's own labels
    authoritative.
    """
    try:
        lines = full_aux.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    seeded = []
    counters = []
    for line in lines:
        match = SEED_LABEL_RE.match(line)
        if match:
            seeded.append(f"\\pdfmd@seed{{{match.group(1)}}}{match.group(2)}")
            continue
        match = PART_COUNTER_RE.match(line)
        if match:
            sets = []
            for item in match.group(2).split(","):
                name, _, value = item.partition("=")
                if name.isalpha() and value.lstrip("-").isdigit():
                    sets.append(f"\\ifcsname c@{name}\\endcsname\\setcounter{{{name}}}{{{value}}}\\fi")
            counters.append(f"\\expandafter\\gdef\\csname pdfmd@st@{match.group(1)}\\endcsname{{{''.join(sets)}}}")
    if not seeded and not counters:
        return 0
    target.write_text(
        "\\makeatletter\n"
        "\\providecommand\\pdfmd@seed[2]{\\@ifundefined{r@#1}{\\expandafter\\gdef\\csname r@#1\\endcsname{#2}}{}}\n"
        + "\n".join(seeded + counters) + "\n\\makeatother\n", encoding="utf-8")
    return len(seeded)


def part_key(part: Path, parts_root: Path | None) -> str:
    """The name a part is recorded under in the .aux: its path under the parts
    folder, reduced to characters that are safe inside a TeX argument."""
    relative = part.relative_to(parts_root).as_posix() if parts_root else part.name
    return re.sub(r"[^A-Za-z0-9./_+-]", "-", relative)


def safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]", "-", name)


# -- Plot cache (pdfmd-options: {cache: {plots: true}}, --cache-plots) --------
# nulabreport's plot macros (nulabreport >= 1.26.0, section 15b) look each whole
# plot picture up by a key; on a hit they include the PDF stored here at the
# stored size, on a miss they typeset as always and log the call to
# <jobname>.plotreq. After the build pdfmd renders those logged calls, each in
# a small standalone job that loads the SAME preamble the document used (cut
# from the generated .tex) and ships the picture out as a page of exactly its
# size, ready for the next build. The finished PDF never depends on this having
# worked: a miss is an ordinary inline plot.
#
# What stops it going stale, since a stale plot would be worse than a slow one:
#   * the directory is keyed by a hash of everything the picture can depend on
#     apart from its own arguments -- the package (nulabreport.sty), the
#     document's whole preamble (fonts, settings, preamble.tex, header-includes),
#     the engine's version, and this cache's format -- so a changed package or
#     setting simply lands in a new directory, and the old one is pruned;
#   * every entry records the files its standalone job actually read (LaTeX's
#     own recorder, not a guess at argument names) and is dropped before the
#     next build if any of them changed or vanished -- a CSV edit shows up;
#   * the key includes the picture's arguments and the layout it read (text
#     height/width, font size), so a different call or a different page
#     geometry is a different entry.
PLOT_CACHE_FORMAT = "1"
PLOT_REQUEST_SEP = "@@|@@"
PLOT_CACHE_KEEP_DIRS = 3
CACHE_PLOTS_CLI: bool | None = None   # --cache-plots (set in main)


def kpsewhich_text(name: str) -> str | None:
    kpsewhich = which("kpsewhich")
    if not kpsewhich:
        return None
    found = subprocess.run([kpsewhich, name], capture_output=True, text=True).stdout.strip().splitlines()
    if not found:
        return None
    try:
        return Path(found[0]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


@lru_cache(maxsize=None)
def engine_version_line(engine: str) -> str:
    try:
        out = subprocess.run([engine, "--version"], capture_output=True, text=True).stdout
    except OSError:
        return ""
    return out.splitlines()[0] if out else ""


def sha1_file(path: Path) -> str | None:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return None


def plot_cache_directory(preamble: str, sty_text: str, engine: str) -> Path:
    digest = hashlib.sha1("\0".join([PLOT_CACHE_FORMAT, preamble, sty_text,
                                     engine_version_line(engine)]).encode("utf-8")).hexdigest()[:12]
    return cache_root() / f"plots-{digest}"


def prune_plot_directories(keep: Path) -> None:
    """Keep the newest few plot directories; an older environment (a package or
    preamble from before a change) is never read again."""
    others = sorted((d for d in cache_root().glob("plots-*") if d.is_dir() and d != keep),
                    key=lambda d: d.stat().st_mtime, reverse=True)
    for stale in others[PLOT_CACHE_KEEP_DIRS - 1:]:
        shutil.rmtree(stale, ignore_errors=True)


def validate_plot_entries(plot_dir: Path, verbose: bool) -> int:
    """Drop every entry whose recorded input files changed or vanished."""
    import json
    dropped = 0
    for deps_file in plot_dir.glob("*.deps"):
        key = deps_file.stem
        try:
            deps = json.loads(deps_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            deps = None
        if deps is None or any(sha1_file(Path(name)) != digest for name, digest in deps.items()):
            for suffix in (".deps", ".dim", ".pdf"):
                (plot_dir / f"{key}{suffix}").unlink(missing_ok=True)
            dropped += 1
            if verbose:
                print(f"AUTO CACHE  plot {key[:8]}: an input changed; dropped")
    return dropped


def read_plot_requests(path: Path) -> dict[str, tuple[str, str, str]]:
    requests: dict[str, tuple[str, str, str]] = {}
    if not path.exists():
        return requests
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(PLOT_REQUEST_SEP)
        if len(parts) == 4 and re.fullmatch(r"[0-9a-f]{32}", parts[0]):
            requests[parts[0]] = (parts[1], parts[2], parts[3])
    return requests


def plot_recorded_inputs(fls: Path, roots: list[Path]) -> dict[str, str]:
    """The user's own files a standalone plot job read (LaTeX -recorder), with
    their content hashes -- anything under the report's folders, nothing from
    the TeX tree."""
    found: dict[str, str] = {}
    try:
        lines = fls.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return found
    base = roots[0]
    for line in lines:
        if not line.startswith("INPUT "):
            continue
        candidate = Path(os.path.abspath(base / line[6:].strip()))
        if candidate.suffix in (".aux", ".fls") or not candidate.is_file():
            continue
        if any(str(candidate).startswith(str(root) + os.sep) for root in roots):
            digest = sha1_file(candidate)
            if digest:
                found[str(candidate)] = digest
    return found


def render_plot_requests(requests: dict[str, tuple[str, str, str]], plot_dir: Path, preamble: str,
                         engine: str, cwd: Path, env: dict | None, roots: list[Path],
                         verbose: bool) -> tuple[int, int]:
    """Render each request not already stored; returns (rendered, failed)."""
    import json
    from concurrent.futures import ThreadPoolExecutor
    todo = {key: value for key, value in requests.items()
            if not (plot_dir / f"{key}.dim").exists()}
    if not todo:
        return 0, 0

    def render(item) -> bool:
        key, (macro, args, ctx) = item
        job = plot_dir / f"r-{key}.tex"
        dim = plot_dir / f"r-{key}.dim"      # renamed to {key}.dim LAST: the commit marker
        job.write_text(
            "\\def\\LabPlotRender{}\n" + preamble + "\\begin{document}\\makeatletter\n"
            "\\pagestyle{empty}\n\\ExplSyntaxOn\n" + ctx + "\n\\ExplSyntaxOff\n"
            "\\setbox\\z@\\hbox{" + macro + args + "}\n"
            "\\newwrite\\dimf\\immediate\\openout\\dimf=" + dim.name + "\n"
            "\\immediate\\write\\dimf{\\string\\gdef\\string\\Lab@pc@wd{\\the\\wd\\z@}"
            "\\string\\gdef\\string\\Lab@pc@ht{\\the\\ht\\z@}"
            "\\string\\gdef\\string\\Lab@pc@dp{\\the\\dp\\z@}}\n"
            "\\immediate\\closeout\\dimf\n"
            "\\pagewidth=\\wd\\z@ \\pageheight=\\dimexpr\\ht\\z@+\\dp\\z@\\relax\n"
            "\\hoffset=-1in \\voffset=-1in\n"
            "\\ClearShipoutPictureBG\\ClearShipoutPictureFG\n"
            "\\shipout\\hbox{\\box\\z@}\n\\end{document}\n", encoding="utf-8")
        cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", "-recorder",
               f"-output-directory={plot_dir}", str(job)]
        log_cmd(cmd, cwd, verbose)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env)
        produced = plot_dir / f"r-{key}.pdf"
        ok = result.returncode == 0 and produced.exists() and dim.exists()
        if ok:
            produced.replace(plot_dir / f"{key}.pdf")
            (plot_dir / f"{key}.deps").write_text(
                json.dumps(plot_recorded_inputs(plot_dir / f"r-{key}.fls", roots)), encoding="utf-8")
            dim.replace(plot_dir / f"{key}.dim")
        else:
            for suffix in (".dim", ".pdf", ".deps"):
                (plot_dir / f"{key}{suffix}").unlink(missing_ok=True)
            if verbose:
                print(f"AUTO CACHE  plot {key[:8]} failed to render: "
                      + (tex_log_failure_reason(result.stdout) or result.stdout[-300:].strip()))
        for leftover in plot_dir.glob(f"r-{key}.*"):
            leftover.unlink(missing_ok=True)
        return ok

    workers = max(1, min(4, os.cpu_count() or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(render, todo.items()))
    return sum(results), len(results) - sum(results)


AUX_CLEAN_SUFFIXES = (".aux", ".toc", ".out", ".lof", ".lot", ".bbl", ".blg", ".bcf", ".run.xml",
                      ".fls", ".fdb_latexmk", ".log", ".pdf")


def compile_tex_direct(tex_path: Path, output: Path, engines: list[str],
                       keep_aux: bool, verbose: bool, debug: bool,
                       aux_dir: Path | None = None, cwd: Path | None = None,
                       env: dict | None = None) -> tuple[bool, str]:
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
        # aux_dir: a persistent directory (the cache route) -- LaTeX's own
        # .aux/.toc/.out survive between builds, so an unchanged document
        # settles in one pass instead of two or three. Never discarded here.
        scratch = None if (keep_aux or aux_dir) else Path(mkdtemp(prefix="pdfmd-tex-"))
        output_dir = aux_dir if aux_dir else (tex_path.parent if scratch is None else scratch)
        try:
            ok, reason = run_tex_engine(engine, tex_path, output_dir, verbose, cwd=cwd, env=env)
            if not ok and aux_dir:
                # A poisoned cache (a half-written .aux from an interrupted or
                # failed build) must never trap the user: wipe LaTeX's own
                # files for this document and retry once from scratch.
                for leftover in output_dir.glob(f"{tex_path.stem}.*"):
                    if leftover.name.endswith(AUX_CLEAN_SUFFIXES):
                        leftover.unlink(missing_ok=True)
                if verbose:
                    print(f"AUTO CACHE  {tex_path.stem}: first attempt failed; retrying with a clean aux")
                ok, reason = run_tex_engine(engine, tex_path, output_dir, verbose, cwd=cwd, env=env)
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
                    where = ("in place (--keep-aux)" if keep_aux else
                             f"in the cache {output_dir}" if aux_dir else "in a scratch directory, then discarded")
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
                document_header_file(md_path, bool(preamble_files) or has_embedded_preamble(md_path) or bool(pdf_meta_snippet_text)) as header_file, \
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


def _convert_one(md_path: Path, *args, **kwargs):
    """_convert_one_core, with the document's embedded bibliography files
    (and its NAME.unpacked/ folder) findable for the whole build -- the cache
    route's compile step included, which runs after the Markdown-to-.tex pass."""
    with embedded_resources(md_path):
        return _convert_one_core(md_path, *args, **kwargs)


def _convert_one_core(md_path: Path, out_dir: Path | None, presentation: bool, font: str,
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
                extra_inputs: list[Path] | None = None,
                partial: bool = False,
                cache_cli: bool | None = None,
                skip_stamp: bool = False,
                full_scaffold: Path | None = None,
                parts_root: Path | None = None,
                part_markers: bool = False,
                embed: "EmbedRequest | None" = None,
                trust_embedded: bool = False,
                self_contained: bool | None = None,
                source_override: tuple[str, bool] | None = None) -> tuple[Path, bool, str]:
    # source_override: (text, shifted) of the document cut down to some of its
    # sections -- see SectionPlan. Always a partial build.
    # self_contained: --self-contained/--no-self-contained (None = the document's).
    # embed: the EmbedRequest of --embed-metadata, for the assembled stage.
    # trust_embedded: --trust-embedded (see embedded_lua_filters).
    # cache_cli: --cache/--no-cache. skip_stamp: the cache route's .tex stage,
    # whose stamp is written once, after the PDF exists. full_scaffold: the
    # scaffold a partial build's labels may be seeded from (see below).
    # extra_inputs: parts-mode parts, joined to md_path (the scaffold) in one
    # Pandoc run -- see plan_scaffold(). partial: only some of them, so this
    # isn't the report itself and writes no BUILD NOTES stamp.
    stamp_overrides = stamp_overrides or {}
    parts_inputs = list(extra_inputs or [])
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
    cli_no_auto = no_auto
    no_auto = effective_no_auto(md_path, no_auto)
    output_extension = FORMAT_EXTENSION.get(target_format, f".{target_format}")
    output = output_file or (
        (out_dir / f"{md_path.stem}{output_extension}") if out_dir else md_path.with_suffix(output_extension)
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    if source_override is not None and target_format == ASSEMBLED_FORMAT:
        raise SystemExit(f"{md_path}: --stop-at markdown writes the whole document; it cannot be "
                         "combined with name#section")
    if target_format == ASSEMBLED_FORMAT:
        # --stop-at markdown: write the text Pandoc would have been given and
        # stop. Before every other branch -- no engine, reader, filter, font
        # or stamp decision below applies to it.
        if parts_inputs:
            note("PARTS", f"{md_path}: {len(parts_inputs)} part{'s' if len(parts_inputs) != 1 else ''} "
                          f"joined after it" + (" (partial build)" if partial else ""))
        plan = None
        resolved_embed = resolve_embed(md_path, metadata_files, embed)
        if resolved_embed is not None:
            kinds, lua_mode = resolved_embed
            discovered_lua = [] if (auto_disabled(no_auto, "lua") or "lua" not in kinds) else find_lua_filters(md_path, metadata_files)
            if not auto_disabled(no_auto, "lua") and "lua" in kinds:
                for extra_filter in frontmatter_extra_lua_filters(md_path):
                    if extra_filter not in discovered_lua:
                        discovered_lua.append(extra_filter)
            plan = EmbedPlan(kinds, lua_mode, list(metadata_files), list(preamble_files or []),
                             discovered_lua)
        ok, reason = write_assembled_markdown([md_path, *parts_inputs], output, bool(parts_inputs), plan, partial)
        flush_summary()
        return md_path, ok, reason

    native_engines = [engine for engine in engines if engine in NATIVE_ENGINES]
    if target_format == "pdf" and native_engines:
        # The native tier (see the section after dependency_report()): no
        # Pandoc, no engine, none of the discovery below applies to it.
        if parts_inputs:
            raise SystemExit(f"{md_path}: parts mode needs Pandoc; the native renderers build one document")
        if source_override is not None:
            raise SystemExit(f"{md_path}: building one section needs Pandoc; the native renderers "
                             "build the whole document (pdfmd --install pandoc)")
        ok, reason = convert_native(md_path, output, native_engines, metadata_files, from_format, verbose, debug)
        if ok:
            stamp_unless_partial(partial or skip_stamp, md_path, metadata_files, preamble_files or [],
                                 stamp_overrides, output, verbose)
        flush_summary()
        return md_path, ok, reason[-3000:]

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

    if not which("pandoc"):
        raise SystemExit(PANDOC_MISSING)

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

    # -- the cache route (see CACHE_DEFAULTS): Markdown -> .tex by the very
    # same code that serves `--to latex`, then pdfmd's own engine runner in
    # a persistent per-document folder. Also taken, regardless of the cache
    # setting, by a parts-mode build that asks for natbib/biblatex: the
    # Pandoc-run bibliography path cannot take several input files, and the
    # runner already knows how to drive bibtex/biber.
    if target_format == "pdf" and not presentation and md_path.suffix.lower() == ".md":
        cache = cache_settings(md_path, metadata_files, cache_cli)
        native_bibliography = (not auto_disabled(no_auto, "citationengine")
                               and frontmatter_citation_engine(md_path, metadata_files) in ("natbib", "biblatex"))
        tex_engines = [engine for engine in engines if engine in LATEX_ENGINES and engine not in ("context", "latexmk", "tectonic")]
        if (cache["aux"] or cache["plots"] or (parts_inputs and native_bibliography)) and tex_engines:
            # cli_no_auto, not the merged no_auto: the Markdown-to-.tex pass inside
            # re-reads the document's own `pdfmd-options.no-auto` itself, and an
            # assembled file lists `lua` there, which would hide its embedded
            # filters from that pass (they are not subject to it: see
            # embedded_lua_filters).
            return convert_via_cache(md_path, out_dir, font, tex_engines, variables, slide_level,
                                     pandoc_options, metadata_file, output, preamble_files, from_format,
                                     cli_no_auto, verbose, debug, stamp_overrides, keep_aux, parts_inputs,
                                     partial, bool(cache["aux"]), full_scaffold, parts_root, note,
                                     flush_summary, plots=bool(cache["plots"]),
                                     trust_embedded=trust_embedded, source_override=source_override)

    with prepared_title_source(md_path, metadata_files, disabled=auto_disabled(no_auto, "title"),
                               override=source_override) \
            as (title_source, title_shifted), \
            embedded_lua_filters(md_path, not auto_disabled(cli_no_auto, "lua"), trust_embedded) \
            as embedded_filters, \
            table_width_filter() as width_filter, \
            csv_table_filter() as csv_filter, \
            scaffold_inputs([md_path, *parts_inputs], bool(parts_inputs),
                            {part: part_key(part, parts_root) for part in parts_inputs}
                            if part_markers and parts_root else None) as scaffold_files:
        part_files = scaffold_files[1:]
        lua_filters = [*lua_filters, *embedded_filters]
        all_inputs = [md_path, *parts_inputs] if parts_inputs else None
        any_citations = any(contains_citations(item) for item in [md_path, *parts_inputs])
        any_code_spans = any(has_code_spans(item.read_text(encoding="utf-8-sig"))
                             for item in [md_path, *parts_inputs])
        if parts_inputs:
            note("PARTS", f"{md_path}: {len(parts_inputs)} part{'s' if len(parts_inputs) != 1 else ''} "
                          f"joined after it" + (" (partial build)" if partial else ""))
            if (target_format == "pdf"
                    and frontmatter_citation_engine(md_path, metadata_files) in ("natbib", "biblatex")
                    and not auto_disabled(no_auto, "citationengine")):
                # Reached only if the cache route above declined (no usable
                # LaTeX engine in the chain): the Pandoc-run bibliography path
                # takes one input file.
                raise SystemExit(f"{md_path}: natbib/biblatex with parts needs a LaTeX engine "
                                 "(lualatex/xelatex/pdflatex); use citeproc otherwise")
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
                              and any_code_spans
                              and not has_monofont(md_path, variables))
            if is_tex_target and geometry_needed:
                note("MARGIN", f"{md_path}: no geometry/margin set; "
                              f"using geometry:margin={DEFAULT_MARGIN} on LaTeX-family targets")
            margin_options = (None if auto_disabled(no_auto, "margin")
                              else frontmatter_margin_geometry_options(md_path, variables, metadata_files))
            if is_tex_target and margin_options:
                note("MARGIN", f"{md_path}: margin: isn't a Pandoc variable LaTeX-family targets "
                              f"read (geometry: is) -- using geometry:{','.join(margin_options)}")
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
                                       typst_engine=(target_format == "typst"),
                                       drop_embedded_preamble=not is_tex_target) as prepared, \
                    document_header_file(md_path, (bool(preamble_files) or has_embedded_preamble(md_path) or bool(pdf_meta_snippet_text))
                                         and is_tex_target) as header_file, \
                    pdf_metadata_header_file(pdf_meta_snippet_text if is_tex_target else None) as pdf_meta_file:
                source, *prepared_metadata = prepared
                cmd = ["pandoc", str(source), *map(str, part_files), "-o", str(output), "-t", target_format]
                if is_tex_target and standalone_auto:
                    note("STANDALONE", f"{md_path}: --to {target_format} needs a complete, "
                                       "independently compilable document; adding --standalone")
                    cmd.append("--standalone")
                if effective_from:
                    cmd += ["-f", effective_from]
                for metadata in prepared_metadata:
                    cmd += ["--metadata-file", str(metadata)]
                if partial:
                    cmd += PARTIAL_METADATA
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
                    elif margin_options:
                        for margin_option in margin_options:
                            cmd += ["-V", f"geometry:{margin_option}"]
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
                cmd += crossref_filter_args(all_inputs or md_path, pandoc_options, no_auto, str(md_path))
                cmd += csv_table_filter_args(all_inputs or md_path, no_auto, csv_filter)
                if any_citations and "--citeproc" not in pandoc_options and not CITEPROC_DISABLED:
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
                if target_format in HTML_TARGETS:
                    cmd += html_pandoc_args(md_path, metadata_files, pandoc_options, self_contained, note)
                cmd += pandoc_options
                if is_tex_target and tablewidth_auto:
                    cmd += ["--lua-filter", str(width_filter)]
                for lua_filter in lua_filters:
                    cmd += ["--lua-filter", str(lua_filter)]
                log_cmd(cmd, pandoc_cwd, verbose)
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)
            if result.returncode == 0:
                stamp_unless_partial(partial or skip_stamp, md_path, metadata_files, preamble_files or [], stamp_overrides, output, verbose)
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
        margin_options = (None if auto_disabled(no_auto, "margin")
                         else frontmatter_margin_geometry_options(md_path, variables, metadata_files))
        if margin_options:
            note("MARGIN", f"{md_path}: margin: isn't a Pandoc variable LaTeX-family engines "
                          f"read (geometry: is) -- using geometry:{','.join(margin_options)}")
        monofont_needed = (not auto_disabled(no_auto, "monofont")
                          and any_code_spans
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
                    stamp_unless_partial(partial or skip_stamp, md_path, metadata_files, preamble_files or [],
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
            if engine == "soffice" and (parts_inputs or source_override is not None):
                print(f"SKIP  {md_path}: the soffice last-resort fallback doesn't support parts mode or sections",
                      file=sys.stderr)
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
                    document_header_file(md_path, (bool(preamble_files) or has_embedded_preamble(md_path) or bool(pdf_meta_snippet_text))
                                         and engine in LATEX_ENGINES) as header_file, \
                    pdf_metadata_header_file(pdf_meta_snippet_text if engine in LATEX_ENGINES else None) as pdf_meta_file:
                source, *prepared_metadata = prepared

                def run(selected_font: str | None, fallback: bool = False):
                    cmd = ["pandoc", str(source), *map(str, part_files), "-o", str(output), "--pdf-engine=" + engine]
                    if effective_from:
                        cmd += ["-f", effective_from]
                    for metadata in prepared_metadata:
                        cmd += ["--metadata-file", str(metadata)]
                    if partial:
                        cmd += PARTIAL_METADATA
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
                    elif margin_options and engine in LATEX_ENGINES:
                        for margin_option in margin_options:
                            cmd += ["-V", f"geometry:{margin_option}"]
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
                    cmd += crossref_filter_args(all_inputs or md_path, pandoc_options, no_auto, str(md_path))
                    if any_citations and "--citeproc" not in pandoc_options and not CITEPROC_DISABLED:
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
                    cmd += csv_table_filter_args(all_inputs or md_path, no_auto, csv_filter)
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
        if result is None:
            # Every engine was skipped (the soffice fallback cannot build parts or sections).
            return md_path, False, ("no PDF engine could build this: the soffice fallback cannot build "
                                    "parts or sections. Install a LaTeX or Typst engine "
                                    "(pdfmd --install typst) or use --to html")
        if result.returncode == 0:
            stamp_unless_partial(partial or skip_stamp, md_path, metadata_files, preamble_files or [], stamp_overrides, output, verbose)
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
                backup_format: str | None = None,
                extra_inputs: list[Path] | None = None,
                partial: bool = False,
                cache_cli: bool | None = None,
                parts_root: Path | None = None,
                embed: "EmbedRequest | None" = None,
                trust_embedded: bool = False,
                self_contained: bool | None = None,
                source_override: tuple[str, bool] | None = None) -> tuple[Path, bool, str]:
    """_convert_one, plus the --backup snapshot on success -- wrapped here
    rather than threaded into each of _convert_one's own success returns
    (Pandoc, natbib/biblatex, direct .tex, office), so every one of them
    gets it, including any added later.
    """
    result = _convert_one(md_path, out_dir, presentation, font, engines, variables, slide_level,
                          pandoc_options, metadata_file, output_file, preamble_files,
                          target_format=target_format, from_format=from_format, no_auto=no_auto,
                          verbose=verbose, debug=debug, stamp_overrides=stamp_overrides,
                          keep_aux=keep_aux, extra_inputs=extra_inputs, partial=partial,
                          cache_cli=cache_cli, full_scaffold=(md_path if extra_inputs else None),
                          parts_root=parts_root, embed=embed, trust_embedded=trust_embedded,
                          self_contained=self_contained, source_override=source_override)
    if result[1] and target_format != ASSEMBLED_FORMAT:
        metadata_files = (metadata_file if isinstance(metadata_file, list)
                          else ([metadata_file] if metadata_file else []))
        for backed_up in [md_path, *(extra_inputs or [])]:
            backup_after_success(backed_up, metadata_files, backup, verbose, backup_format)
    return result


def convert_via_cache(md_path: Path, out_dir: Path | None, font: str, engines: list[str],
                      variables: list[str], slide_level: int | None, pandoc_options: list[str],
                      metadata_file: Path | list[Path] | None, output: Path,
                      preamble_files: list[Path] | None, from_format: str | None,
                      no_auto: list[str] | None, verbose: bool, debug: bool,
                      stamp_overrides: dict, keep_aux: bool, parts_inputs: list[Path],
                      partial: bool, persistent: bool, full_scaffold: Path | None,
                      parts_root: Path | None, note, flush_summary,
                      plots: bool = False,
                      trust_embedded: bool = False,
                      source_override: tuple[str, bool] | None = None) -> tuple[Path, bool, str]:
    """Build a PDF the cache way: Pandoc writes the .tex, pdfmd compiles it.
    See the comment above CACHE_DEFAULTS. ``persistent`` False (the natbib +
    parts case without the cache switched on) uses a scratch folder instead
    and discards it.
    """
    metadata_files = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
    base = cache_directory(full_scaffold or md_path) if persistent else Path(mkdtemp(prefix="pdfmd-cache-"))
    base.mkdir(parents=True, exist_ok=True)
    stem = safe_stem(output.stem)
    tex_path = base / f"{stem}.tex"
    headers = list(preamble_files or [])
    seeded = 0
    global LAST_SEEDED
    LAST_SEEDED = 0
    if persistent and parts_inputs and parts_root is not None:
        defs = base / f"{stem}.pdfmd-defs.tex"
        defs.write_text(PARTS_MARKER_DEFS, encoding="utf-8")
        headers.append(defs)
    if persistent and partial and full_scaffold is not None and parts_root is not None:
        full_aux = base / f"{safe_stem(full_scaffold.stem)}.aux"
        seed = base / f"{stem}.seed.tex"
        seed.unlink(missing_ok=True)
        seeded = seed_labels_file(full_aux, seed)
        if seeded:
            LAST_SEEDED = seeded
            hook = base / f"{stem}.seed-hook.tex"
            hook.write_text("\\AtBeginDocument{\\InputIfFileExists{\"%s\"}{}{}}\n" % seed.as_posix(), encoding="utf-8")
            headers.append(hook)
            when = datetime.fromtimestamp(full_aux.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            note("CACHE", f"{md_path}: {seeded} labels from the last full build ({when}) fill in "
                          "references to parts left out")
    try:
        built = _convert_one(md_path, out_dir, False, font, engines, variables, slide_level,
                             pandoc_options, metadata_file, tex_path, headers, target_format="latex",
                             from_format=from_format, no_auto=no_auto, verbose=verbose, debug=debug,
                             stamp_overrides=stamp_overrides, keep_aux=keep_aux,
                             extra_inputs=parts_inputs, partial=partial, cache_cli=False,
                             skip_stamp=True, parts_root=parts_root,
                             part_markers=bool(persistent and parts_inputs),
                             trust_embedded=trust_embedded, source_override=source_override)
        if not built[1]:
            return built
        pandoc_cwd = metadata_files[0].parent if metadata_files else md_path.parent
        tex_env = tex_search_env(md_path.parent, pandoc_cwd)
        plot_dir = None
        preamble_text = ""
        if plots:
            tex_text = tex_path.read_text(encoding="utf-8")
            preamble_text = tex_text.split("\\begin{document}")[0]
            sty_text = kpsewhich_text("nulabreport.sty") or ""
            if engines[0] != "lualatex":
                note("CACHE", "plots: only LuaLaTeX is supported; plot cache skipped")
            elif "LabPlotCacheDir" not in sty_text:
                note("CACHE", "plots: this nulabreport.sty has no plot cache (needs v1.26.0); skipped")
            elif " " in str(cache_root()):
                note("CACHE", "plots: the cache folder's path has a space; plot cache skipped")
            else:
                plot_dir = plot_cache_directory(preamble_text, sty_text, "lualatex")
                plot_dir.mkdir(parents=True, exist_ok=True)
                os.utime(plot_dir)
                prune_plot_directories(plot_dir)
                validate_plot_entries(plot_dir, verbose)
                tex_path.write_text("\\def\\LabPlotCacheDir{%s/}\n" % plot_dir.as_posix() + tex_text,
                                    encoding="utf-8")
        ok, reason = compile_tex_direct(tex_path, output, engines, keep_aux, verbose, debug,
                                        aux_dir=base, cwd=pandoc_cwd, env=tex_env)
        if ok and plot_dir is not None:
            requests = read_plot_requests(base / f"{stem}.plotreq")
            if requests:
                started = time.time()
                roots = [Path(os.path.abspath(pandoc_cwd)), Path(os.path.abspath(md_path.parent))]
                done, failed = render_plot_requests(requests, plot_dir, preamble_text, "lualatex",
                                                    pandoc_cwd, tex_env, roots, verbose)
                if done or failed:
                    print(f"PLOTS  stored {done} plot{'s' if done != 1 else ''} for the next build "
                          f"({time.time() - started:.0f} s)" + (f"; {failed} failed (typeset inline, "
                          "nothing lost)" if failed else ""))
        if ok:
            stamp_unless_partial(partial, md_path, metadata_files, preamble_files or [], stamp_overrides,
                                 output, verbose)
        flush_summary()
        return md_path, ok, reason[-3000:]
    finally:
        if not persistent:
            shutil.rmtree(base, ignore_errors=True)


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
    parser.add_argument("--stop-at", choices=STOP_STAGES, default=None, metavar="STAGE",
                        help="stop the build early, after STAGE: 'markdown' -- the assembled Markdown "
                             "(the parts joined into one file, NAME.assembled.md); 'tex' -- the "
                             "standalone .tex a LaTeX engine would get (same as --to latex, or "
                             "beamer with -p); 'pdf' -- the whole build (default). An -o ending "
                             f"{ASSEMBLED_SUFFIX} also means 'markdown'")
    parser.add_argument("--assemble-only", action="store_true",
                        help="shorthand for --stop-at markdown")
    parser.add_argument("--embed-metadata", nargs="*", default=None, metavar="KIND",
                        help="with --stop-at markdown: fold what pdfmd discovers beside the document "
                             "into the assembled file, so it builds the same without them. KIND is "
                             "metadata (the YAML files, merged with the front matter), preamble (the "
                             "LaTeX preamble, into header-includes), lua (the Lua filters, see "
                             "--lua-mode) or bibliography (the bibliography and CSL files the metadata "
                             "names); none given means all four")
    parser.add_argument("--no-embed-metadata", action="store_true",
                        help="turn off embedding for this run, even where a document's "
                             "pdfmd-options.embed asks for it")
    parser.add_argument("--lua-mode", choices=LUA_MODES, default=None,
                        help="how --embed-metadata carries Lua filters (default: the document's "
                             "pdfmd-options.embed.lua, else embed): 'embed' -- the whole "
                             "filter in a {=pdfmd} block at the end of the file; 'ref' -- only its "
                             "path (a missing one is a warning, and the build goes on); 'apply' -- run "
                             "now, Markdown to Markdown, so the text already has their effect (a "
                             "filter that checks FORMAT is embedded instead); 'off' -- not carried")
    parser.add_argument("--self-contained", dest="self_contained", action="store_true", default=None,
                        help="for an HTML target: one file with everything inlined (images, CSS; "
                             "--standalone --embed-resources, MathML for math). A document sets it "
                             "with `pdfmd-options: {html: {self-contained: true}}`")
    parser.add_argument("--no-self-contained", dest="self_contained", action="store_false",
                        help="for an HTML target: not self-contained, even where the document says so")
    parser.add_argument("--unpack", action="store_true",
                        help="write what an assembled file embeds (Lua filters, preamble, merged "
                             "metadata) back out as files into NAME.unpacked/ (or -o DIR), checking "
                             "each filter's hash; never overwrites, never edits the file")
    parser.add_argument("--slim", action="store_true",
                        help="with --unpack: after writing the files, rewrite the assembled file "
                             "without what was unpacked, leaving the document plus its NAME.unpacked/ "
                             "folder, which pdfmd discovers by itself")
    parser.add_argument("--trust-embedded", action="store_true",
                        help="run Lua filters embedded in a document even if this pdfmd did not "
                             "write them (a filter can run any command; by default only ones this "
                             "machine's pdfmd embedded itself run)")
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
    parser.add_argument("--install", choices=INSTALL_KINDS, metavar="KIND",
                        help="install an optional piece for pdfmd to use: 'pandoc' (the real Pandoc from "
                             "PyPI's pypandoc_binary, about 35 MB), 'typst' (Typst's release binary from "
                             "GitHub, into pdfmd's own tools folder), 'full' (both: a complete Markdown-to-PDF "
                             "setup with no admin rights), 'math' (md2pdf with offline math, about 150 MB, "
                             "Python 3.11+) or 'emoji' (colour emoji font for the built-in inkmd renderer, "
                             "about 11 MB). pandoc/math/emoji equal `pip install \"pdfmd-cli[KIND]\"`. "
                             "A Pandoc or Typst already on PATH always wins over the installed ones")
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
    parser.add_argument("--section", "--only", action="append", default=[], metavar="NAME",
                        dest="section",
                        help="build just these sections: in a parts-mode document (pdfmd-options: "
                             "{parts: auto}) parts named by file, by file without its numeric prefix, by "
                             "folder, or by number; in any Markdown document headings, named by their text "
                             "(case, spaces and spelling are forgiving) or {#id}: `name`, `##name` for a "
                             "level-2 heading, `parent/name`; repeat the flag or join with + or , (a+b). "
                             "`pdfmd report#intro` is shorthand for `pdfmd report --section intro`, and "
                             "so is naming a part's own path. (No short flag: -s is Pandoc's --standalone.)")
    parser.add_argument("--cache", dest="cache", action="store_true", default=None,
                        help="keep LaTeX's .aux files between builds in pdfmd's cache folder, so an "
                             "unchanged document settles in one engine pass and a part of a split "
                             "document built alone can reference the last full build's numbers "
                             "(pdfmd-options: {cache: {aux: true}} does this by default)")
    parser.add_argument("--cache-plots", action="store_true",
                        help="also cache nulabreport's plots (needs nulabreport >= 1.26.0, LuaLaTeX): each "
                             "plot is stored as a PDF after the build that first typesets it and reused by "
                             "the next, until the package, the preamble, the engine or the plot's data "
                             "file changes (pdfmd-options: {cache: {plots: true}} does this by default)")
    parser.add_argument("--clear-cache", action="store_true",
                        help="delete pdfmd's cache folder for the given document (or all of it, with no "
                             "document), then exit; always safe")
    parser.add_argument("--no-cache", dest="cache", action="store_false",
                        help="turn the cache off for this build, whatever pdfmd-options says")
    parser.add_argument("--split", type=Path, metavar="DIR",
                        help="cut a single-file document at its '# ' headings into a scaffold plus "
                             "parts/ in a new folder DIR (the source is untouched; other files it "
                             "uses are symlinked in), and check that the parts read back as the "
                             "identical document. See 'A long document in parts' in the docs")
    parser.add_argument("--split-depth", type=int, default=1, metavar="N",
                        help="with --split: also cut at '## ' (N=2), '### ' (N=3) headings, each "
                             "cut section becoming a folder of parts, so that a subsection can be "
                             "built alone. Default 1: top-level sections only")
    parser.add_argument("--list-parts", action="store_true",
                        help="print what `--section`/`name#section` can name and exit: a parts-mode "
                             "document's parts in build order, or any other Markdown document's "
                             "headings and {#ids} with their lines")
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
                             "files (metadata+preamble+lua together), lookup (finding a document by "
                             "its title, alias, the start of its name or a looser spelling), texdirect (the direct-.tex-"
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
    for directory in accessory_directories(source.parent, source.stem):
        for path in directory.glob("*"):
            if path.is_file():
                try:
                    latest = max(latest, path.stat().st_mtime)
                except OSError:
                    continue
    # A parts-mode document's parts live one level down (and deeper): watch
    # those too. Only the conventional folder names -- a custom
    # `parts: <folder>` is not followed, to keep this scan cheap and bounded.
    for name in PARTS_DIR_ALIASES:
        directory = source.parent / name
        if directory.is_dir():
            for path in directory.rglob("*.md"):
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
    use_managed_tools()
    if args.debug:
        args.verbose = True
    global SHOW_FULL_PATHS
    # -v/--verbose already means "more detail than the quiet default," and a
    # full path is exactly that kind of detail -- so --verbose (or --debug,
    # which implies it just above) turns this on too, not just --full-paths
    # on its own.
    SHOW_FULL_PATHS = args.full_paths or args.verbose
    global CITEPROC_DISABLED, CACHE_PLOTS_CLI, FUZZY_LOOKUP
    CITEPROC_DISABLED = args.no_citeproc
    # A CLI switch only: the document's own `pdfmd-options: no-auto` cannot
    # turn off the lookup that is still busy finding that document.
    FUZZY_LOOKUP = not auto_disabled(args.no_auto, "lookup")
    CACHE_PLOTS_CLI = args.cache_plots or None
    if args.check_dependencies:
        raise SystemExit(0 if dependency_report() else 1)
    if args.install:
        raise SystemExit(0 if install_extra(args.install) else 1)
    if not which("pandoc") and not native_possible(args):
        raise SystemExit(PANDOC_MISSING)
    paths = args.path or [Path.cwd()]
    if args.clear_cache:
        targets = []
        if args.path:
            try:
                document = find_markdown(paths[0])
            except FileNotFoundError as error:
                raise SystemExit(str(error))
            plan = plan_scaffold(document, [], args.no_auto, args.metadata_file)
            targets = [cache_directory(plan.scaffold if plan else document)]
        else:
            targets = [cache_root()]
        for target in targets:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                print(f"CLEARED  {target}")
            else:
                print(f"NOTHING  {target} does not exist")
        return
    if args.slim and not args.unpack:
        raise SystemExit("--slim goes with --unpack")
    if args.unpack:
        if len(paths) != 1 or not args.path:
            raise SystemExit("--unpack takes one assembled Markdown file")
        try:
            raise SystemExit(unpack_assembled(find_markdown(paths[0]), args.out.resolve() if args.out else None,
                                              slim=args.slim))
        except FileNotFoundError as error:
            raise SystemExit(str(error))
    if args.split:
        if len(paths) != 1:
            raise SystemExit("--split takes one Markdown file")
        try:
            raise SystemExit(split_into_parts(find_markdown(paths[0]), args.split.resolve(), max(1, args.split_depth)))
        except FileNotFoundError as error:
            raise SystemExit(str(error))
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

    # Stop-at stage (see STOP_STAGES). --assemble-only is --stop-at markdown;
    # so is an -o ending .assembled.md (single-file/report only, like every
    # -o extension below). The stage then fixes the target format: `tex` is
    # --to latex (beamer with -p), `markdown` is the internal assembled one.
    stop_at = args.stop_at
    if args.assemble_only:
        if stop_at not in (None, "markdown"):
            raise SystemExit(f"--assemble-only means --stop-at markdown; it conflicts with --stop-at {stop_at}")
        stop_at = "markdown"
    if (stop_at is None and args.out and not args.batch
            and args.out.name.casefold().endswith(ASSEMBLED_SUFFIX)):
        stop_at = "markdown"
    embed_request = None
    if args.no_embed_metadata and args.embed_metadata is not None:
        raise SystemExit("--embed-metadata and --no-embed-metadata contradict each other")
    if args.lua_mode is not None and args.embed_metadata is None and stop_at != "markdown":
        raise SystemExit("--lua-mode applies to --stop-at markdown (--assemble-only) only")
    if args.embed_metadata is not None:
        unknown_kinds = sorted(set(args.embed_metadata) - {*EMBED_KINDS, "all"})
        if unknown_kinds:
            raise SystemExit(f"Unknown --embed-metadata kind(s): {', '.join(unknown_kinds)}. "
                             f"Valid: {', '.join(EMBED_KINDS)}")
        if stop_at != "markdown":
            raise SystemExit("--embed-metadata applies to --stop-at markdown (--assemble-only) only")
        wanted = (set(EMBED_KINDS) if not args.embed_metadata or "all" in args.embed_metadata
                  else set(args.embed_metadata))
        embed_request = EmbedRequest(frozenset(wanted), args.lua_mode, False)
    elif stop_at == "markdown":
        # No kinds named: each document's own pdfmd-options.embed decides.
        embed_request = EmbedRequest(None, args.lua_mode, args.no_embed_metadata)
    if stop_at in ("markdown", "tex"):
        if args.to:
            raise SystemExit(f"--stop-at {stop_at} fixes the output format; drop --to {args.to}")
        out_format = format_from_output(args.out) if args.out and not args.batch else None
        if stop_at == "tex" and out_format not in (None, "latex"):
            raise SystemExit(f"--stop-at tex writes a .tex file; -o {args.out} names another format")
        if stop_at == "markdown" and out_format not in (None, "markdown"):
            raise SystemExit(f"--stop-at markdown writes Markdown; -o {args.out} names another format")
        if stop_at == "markdown" and (args.presentation or args.watch):
            raise SystemExit("--stop-at markdown can't be combined with -p/--presentation or -w/--watch")
        if stop_at == "markdown" and args.engine is not None:
            print("WARN  --engine is ignored for --stop-at markdown: no engine is involved",
                  file=sys.stderr)

    # Target format: explicit --to wins; otherwise a recognized -o/--out
    # extension implies it (single-file/report only -- batch's -o is a
    # directory, so it only responds to --to); default is pdf.
    target_format = (
        (args.to.casefold() if args.to else None)
        or (format_from_output(args.out) if args.out and not args.batch else None)
        or "pdf"
    )
    if stop_at == "markdown":
        target_format = ASSEMBLED_FORMAT
    elif stop_at == "tex":
        target_format = "beamer" if args.presentation else "latex"
    if args.presentation and target_format != "pdf" and stop_at != "tex":
        raise SystemExit("-p/--presentation always produces a PDF (via Beamer); "
                         "it can't be combined with --to/-o for another format")
    if args.engine is not None and target_format != "pdf" and stop_at != "markdown":
        print(f"WARN  --engine is ignored for "
              f"{'--stop-at tex' if stop_at == 'tex' else f'--to {target_format}'}: "
              "no PDF engine is involved", file=sys.stderr)
    # Explicit: the command line named a format (or a stage), so a document's
    # pdfmd-options.default-output does not apply.
    target_explicit = (stop_at is not None or bool(args.to) or args.presentation
                       or bool(format_from_output(args.out) if args.out and not args.batch else None))
    engines: list[str] = []
    engines_error: SystemExit | None = None
    if target_format == "pdf":
        try:
            engines = select_engines(args.engine, args.presentation)
        except SystemExit as error:
            if target_explicit:
                raise
            # A document's default-output may not be PDF: only fail if one is.
            engines_error = error
    native_auto = (bool(engines) and not args.engine
                   and all(engine in NATIVE_ENGINES for engine in engines))
    if native_auto:
        native_run_note(engines)

    def need_engines(format_name: str) -> None:
        if format_name == "pdf" and engines_error is not None:
            raise engines_error

    def default_target(document: Path, metadata_files: list[Path]) -> str:
        """target_format, or the document's own default-output (never over an explicit one)."""
        if target_explicit:
            return target_format
        chosen = default_output_format(document, metadata_files)
        if chosen and chosen != target_format:
            print(f"AUTO OUTPUT  {display_path(document)}: default-output {chosen} (pdfmd-options)")
        return chosen or target_format

    def only_markdown_in(directory: Path) -> Path:
        """The one Markdown file of a folder (what `pdfmd` and `pdfmd '#section'` mean)."""
        markdown_files = sorted(directory.glob("*.md"), key=lambda path: path.name.casefold())
        if not markdown_files:
            raise SystemExit("No Markdown files found in the current directory.")
        if len(markdown_files) > 1:
            names = ", ".join(path.name for path in markdown_files)
            raise SystemExit(
                f"Multiple Markdown files found: {names}\n"
                "Specify one file, use -b to convert all separately, or use -r to combine them."
            )
        print(f"AUTO MD    {display_path(markdown_files[0])}")
        return markdown_files[0]

    if not args.path and not args.batch and not args.report:
        paths = [only_markdown_in(Path.cwd())]
    # `pdfmd report#intro` is shorthand for --section: a part in parts mode,
    # any heading (or {#id}) otherwise. A literal path with a '#' in its name
    # wins, so nothing that already worked changes meaning. `doc##name` asks
    # for a level-2 heading (see find_heading); `#name` alone, with no
    # document, means the folder's only Markdown file.
    section_requests = split_section_requests(args.section)
    if len(paths) == 1 and "#" in str(paths[0]) and not paths[0].exists():
        # The whole string, not .name: a section path (`doc#results/yield`) has a slash.
        base, _, suffix = str(paths[0]).partition("#")
        if base and not base.endswith(("/", os.sep)):
            paths = [Path(base)]
        else:
            paths = [only_markdown_in(Path(base) if base else Path.cwd())]
        # `doc#name` asks for `name`; `doc##name` for `##name`, a level-2 heading.
        section_requests += split_section_requests(["#" + suffix if suffix.startswith("#") else suffix])
    scaffold_plan = None
    section_plan = None
    plan_source = None
    single_document = not args.batch and not args.report and not args.presentation and len(paths) == 1
    if single_document:
        try:
            plan_source = find_markdown(paths[0])
        except LookupAmbiguous as error:
            raise SystemExit(str(error))
        except FileNotFoundError as error:
            if section_requests or args.list_parts:
                raise SystemExit(str(error))
            plan_source = None
        if plan_source is not None:
            scaffold_plan = plan_scaffold(plan_source, section_requests, args.no_auto, args.metadata_file)
    if scaffold_plan is None and (section_requests or args.list_parts):
        if not single_document:
            raise SystemExit("--section, --list-parts and 'name#section' take one document, "
                             "not -b/--batch, -r/--report or -p/--presentation")
        if plan_source.suffix.lower() != ".md":
            raise SystemExit(f"{plan_source}: sections can only be taken from a Markdown (.md) document")
        if args.list_parts:
            print_headings(plan_source, args.no_auto, args.metadata_file)
            return
        section_plan = plan_sections(plan_source, section_requests, args.no_auto, args.metadata_file)
    if scaffold_plan is not None and args.list_parts:
        print_parts(scaffold_plan)
        return
    if scaffold_plan is not None:
        PART_CUTS.update(scaffold_plan.cuts)
    if args.watch:
        if args.batch or args.report:
            raise SystemExit("-w/--watch only supports single-file mode, not -b/--batch or -r/--report")
        if len(paths) != 1:
            raise SystemExit("-w/--watch accepts one Markdown name or path")
        if scaffold_plan is not None:
            watch_source = scaffold_plan.scaffold
        else:
            try:
                watch_source = find_markdown(paths[0])
            except FileNotFoundError as error:
                raise SystemExit(str(error))
        run_watch(watch_source, sys.argv[1:])
        return
    if args.report:
        files, excluded = report_sources(paths, args.ignore, args.exclude_unnumbered, args.recursive)
        if target_format == ASSEMBLED_FORMAT:
            files = [file for file in files if not is_assembled_document(file)]
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
            if metadata_request is None:
                metadata_request = option_names(frontmatter_pdfmd_options(files[0]), "yaml") or None
            metadata = find_metadata(metadata_directory.resolve(), metadata_request, report=True,
                                     document_class=document_class, document_stem=files[0].stem)
        except (FileNotFoundError, ValueError) as error:
            raise SystemExit(str(error))
        metadata_files = ([] if metadata is AUTO_METADATA_DISABLED else
                          (metadata if isinstance(metadata, list) else ([metadata] if metadata else [])))
        target_format = default_target(files[0], metadata_files)
        need_engines(target_format)
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
        if target_format == ASSEMBLED_FORMAT:
            # --stop-at markdown: the chapters, as one Markdown text, in the
            # order Pandoc would read them. Nothing else of the build runs.
            report_plan = None
            report_embed = resolve_embed(files[0], metadata_files, embed_request)
            if report_embed is not None:
                kinds, lua_mode = report_embed
                report_plan = EmbedPlan(
                    kinds, lua_mode, list(metadata_files),
                    ([] if "preamble" not in kinds or auto_disabled(report_no_auto, "preamble")
                     else find_preambles(files[0].parent, files[0].stem, pandoc_options)
                     + frontmatter_extra_preambles(files[0])),
                    [])  # a report build applies no discovered Lua filter
                if "lua" in kinds:
                    print("NOTE  a report/book build applies no discovered Lua filter, so none is embedded")
            ok, reason = write_assembled_markdown(files, output, False, report_plan)
            if not ok:
                raise SystemExit(reason)
            for file in files:
                if not has_chapter_field(file):
                    print(f"[WARNING] unnumbered Markdown included: {display_path(file)}")
                print(f"OK    {display_path(file)}")
            for file in excluded:
                print(f"SKIP  {display_path(file)}")
            print(f"OK    REPORT  {display_path(output)}")
            if args.open:
                open_file(output)
            return
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
                report_margin_options = (None if auto_disabled(report_no_auto, "margin")
                                         else frontmatter_margin_geometry_options(files[0], variables,
                                                                                  metadata_files))
                if is_tex_target and report_margin_options:
                    report_note("MARGIN", "REPORT: margin: isn't a Pandoc variable LaTeX-family "
                                         "targets read (geometry: is) -- using "
                                         f"geometry:{','.join(report_margin_options)}")
                report_monofont_needed = (is_tex_target and not auto_disabled(report_no_auto, "monofont")
                                          and any(has_code_spans(file.read_text(encoding="utf-8-sig")) for file in files)
                                          and not has_monofont(files[0], variables))
                if report_monofont_needed:
                    report_note("MONOFONT", "REPORT: has code but no monofont set; "
                                           f"using {default_monofont()} on LaTeX-family targets")
                with prepared_latex_inputs([*files, *metadata_files], is_tex_target,
                                           typst_engine=(target_format == "typst"),
                                           doc_count=len(files),
                                           drop_embedded_preamble=not is_tex_target) as prepared, \
                        document_header_file(files[0], (bool(report_preambles) or has_embedded_preamble(files[0]) or bool(report_pdf_meta_snippet_text))
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
                        elif report_margin_options:
                            for margin_option in report_margin_options:
                                cmd += ["-V", f"geometry:{margin_option}"]
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
                    if target_format in HTML_TARGETS:
                        cmd += html_pandoc_args(files[0], metadata_files, pandoc_options,
                                                args.self_contained, report_note)
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
                margin_options = (None if auto_disabled(report_no_auto, "margin")
                                 else frontmatter_margin_geometry_options(files[0], variables, metadata_files))
                if margin_options:
                    report_note("MARGIN", "REPORT: margin: isn't a Pandoc variable LaTeX-family "
                                         "engines read (geometry: is) -- using "
                                         f"geometry:{','.join(margin_options)}")
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
                                               typst_engine=(engine == "typst"),
                                               doc_count=len(files)) as prepared, \
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
                        elif margin_options and engine in LATEX_ENGINES:
                            for margin_option in margin_options:
                                cmd += ["-V", f"geometry:{margin_option}"]
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
    def embeds_preamble(file) -> bool:
        """Whether the assembled stage folds `file`'s preamble in (so it has to be found)."""
        if target_format != ASSEMBLED_FORMAT or embed_request is None:
            return False
        try:
            found = metadata_for(file)
        except (FileNotFoundError, ValueError):
            return False
        chosen = resolve_embed(file, found if isinstance(found, list) else ([found] if found else []),
                               embed_request)
        return chosen is not None and "preamble" in chosen[0]

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
            if requested is None:
                # pdfmd-options.yaml / .metadata: the document names its own
                # metadata files (like -y, but written in the document).
                requested = option_names(frontmatter_pdfmd_options(file), "yaml") or None
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
        if target_format == ASSEMBLED_FORMAT:
            # Not an assembly of an assembly: a file written by an earlier run
            # (NAME.assembled.md) would otherwise come out as NAME.assembled.assembled.md.
            files = [file for file in files if not is_assembled_document(file)]
        output = Path.cwd() if args.destination_cwd else (args.out.resolve() if args.out else None)
        if output:
            output.mkdir(parents=True, exist_ok=True)
        jobs = max(1, args.jobs)
        batch_target = target_format

        def file_target(file):
            """This file's target: the command line's, else its own default-output."""
            if target_explicit or file.suffix.lower() not in (".md", ".markdown"):
                return batch_target
            found = metadata_for(file)
            chosen = default_output_format(file, found if isinstance(found, list) else ([found] if found else []))
            return chosen or batch_target

        def preamble_for(file):
            if (not (file_target(file) in {"pdf", *TEX_STANDALONE_FORMATS} or embeds_preamble(file))
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
            return metadata, resolve_engines(file, args.engine, engines, args.presentation, file_target(file), metadata_files, args.verbose)
        def work(file):
            need_engines(file_target(file))
            metadata, file_engines = file_metadata_and_engines(file)
            return convert_one(file, output, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, preamble_files=preamble_for(file), target_format=file_target(file), from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format, embed=embed_request, trust_embedded=args.trust_embedded, self_contained=args.self_contained)
        results = []
        if jobs > 1:
            with ProcessPoolExecutor(max_workers=jobs) as executor:
                futures = []
                for file in files:
                    need_engines(file_target(file))
                    metadata, file_engines = file_metadata_and_engines(file)
                    futures.append(executor.submit(convert_one, file, output, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, None, preamble_for(file), file_target(file), args.from_format, args.no_auto, args.verbose, args.debug, stamp_overrides, args.keep_aux, args.backup, args.backup_format, embed=embed_request, trust_embedded=args.trust_embedded, self_contained=args.self_contained))
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
        if target_format == ASSEMBLED_FORMAT:
            if source.suffix.lower() not in (".md", ".markdown"):
                raise SystemExit(f"{source}: --stop-at markdown assembles Markdown files only")
            if is_assembled_document(source):
                raise SystemExit(f"{display_path(source)} is already an assembled file "
                                 f"({ASSEMBLED_KEY}: true); there is nothing left to assemble")
        # A parts-mode build is the scaffold plus its parts: it takes the
        # scaffold's own name and folder, and a partial build carries the
        # section names in its file name so it never replaces the full report.
        output_stem = source.stem
        if scaffold_plan is not None:
            source = scaffold_plan.scaffold
            output_stem = scaffold_plan.output_stem
        elif section_plan is not None:
            output_stem = section_plan.output_stem
        target_format = default_target(source, scaffold_metadata_files(source, args.metadata_file))
        need_engines(target_format)
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
            output_file = Path.cwd() / f"{output_stem}{output_extension}"
        output = output_file or ((out_dir / f"{output_stem}{output_extension}") if out_dir
                                 else source.with_name(f"{output_stem}{output_extension}"))
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
            if scaffold_plan is not None or section_plan is not None:
                # _convert_one derives the output name from the document's own
                # stem; a partial build's differs, so hand over the final path.
                output_file = output
            document_class = (frontmatter_value(source, "documentclass")
                              or frontmatter_value(source, "class"))
            try:
                metadata = metadata_for(source, document_class=document_class)
            except (FileNotFoundError, ValueError) as error:
                raise SystemExit(str(error))
            preambles = []
            if ((target_format in {"pdf", *TEX_STANDALONE_FORMATS} or embeds_preamble(source))
                    and not auto_disabled(effective_no_auto(source, args.no_auto), "preamble")):
                preambles = find_preambles(source.parent, source.stem, pandoc_options) + frontmatter_extra_preambles(source)
                announce_preambles(preambles)
            engine_metadata_files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
            file_engines = resolve_engines(source, args.engine, engines, args.presentation, target_format, engine_metadata_files, args.verbose)
            results = [convert_one(source, out_dir, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, output_file, preambles, target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format,
                                   extra_inputs=(scaffold_plan.files[1:] if scaffold_plan is not None else None),
                                   cache_cli=args.cache, embed=embed_request, trust_embedded=args.trust_embedded,
                                   self_contained=args.self_contained,
                                   parts_root=(scaffold_plan.directory if scaffold_plan is not None else None),
                                   partial=((scaffold_plan is not None and scaffold_plan.selected is not None)
                                            or section_plan is not None),
                                   source_override=((section_plan.text, section_plan.shifted)
                                                    if section_plan is not None else None))]
            if section_plan is not None and results[0][1] and target_format != ASSEMBLED_FORMAT:
                print("NOTE  section build: references to other sections print as ??, and heading, "
                      "figure and table numbers restart from this section's own first one")
            if (scaffold_plan is not None and scaffold_plan.selected is not None and results[0][1]
                    and target_format != ASSEMBLED_FORMAT):
                if LAST_SEEDED:
                    print("NOTE  partial build: numbers of parts left out come from the last full build "
                          "(--cache); they are stale if you have since added or moved a figure or table there")
                else:
                    print("NOTE  partial build: references to parts left out print as ??, and figure/"
                          "table numbers restart from this build's own first one (pdfmd-options: "
                          "{cache: {aux: true}} carries them over from the last full build)")
        if args.open and results[0][1]:
            open_file(output)
    failures = [result for result in results if not result[1]]
    for source, ok, error in results:
        print(f"{'OK  ' if ok else 'FAIL'}  {display_path(source)}")
        if error:
            print(error)
    if native_auto and not failures:
        offer_native_upgrade()
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
