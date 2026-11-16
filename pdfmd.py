#!/usr/bin/env python3
"""Convert Markdown documents to PDF (or other formats) with Pandoc.

Examples:
    pdfmd report
    pdfmd slides -p
    pdfmd /path/to/report.md -d
    pdfmd Downloads -b -f "DejaVu Serif"
    pdfmd Downloads -b --recursive
    pdfmd book -r -o book.pdf
    pdfmd report#methods            (parts mode: build one part; `@` does the same: report@methods)
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

    A `.typ` (Typst) and an `.html` file are the fourth and fifth (v3.25.6; the package pdfmd_direct): they go
    straight to their engine, with no Pandoc between them -- `typst compile` for the first, and for the second
    WeasyPrint, or a browser (Chrome, Chromium, Edge, Brave: headless, printing the page) when the page runs scripts
    or WeasyPrint fails, then wkhtmltopdf, Prince, pagedjs-cli and LibreOffice. Pandoc would read them into its own
    model and write them out again, losing the page size, the styles and the scripts on the way. Like an office
    file, such a document gets none of pdfmd's defaults (metadata.yaml, fonts, margins, the stamp): it is finished.
    `--apply-defaults` (or `pdfmd-options: {apply-defaults: true}` in the config, or --setup) gives it the title,
    author, date, language, main font, font size, paper and margin of its metadata files -- ahead of its own
    settings, so those win -- without Pandoc. `-e` naming an engine of another kind (`-e lualatex`), `--from`,
    a target other than PDF, `--no-auto typstdirect|htmldirect`, or the engine not being installed keeps the old
    route through Pandoc (with a WARN for the last). A `.tex` file that no LaTeX engine can compile is tried through
    Pandoc after the engines fail, with a WARN.

Older Pandoc, and no network (v3.25.11):
    The oldest Pandoc pdfmd is tested with is PANDOC_MIN, 3.1.3 (the claude.ai sandbox's); the suite runs against it, with
    a few tests skipped for what an older Pandoc lacks (PANDOC_FEATURES: Word equation tables, caption attributes).
    Typst pictures work with it since v3.27.10-11: Typst is given --root=/ as a newer Pandoc does, and pdfmd_lua/typst.lua
    makes a picture's relative path absolute (that Pandoc runs Typst in its own working folder). The first compile with
    an older Pandoc warns once (per version, a marker in the config folder), and --doctor lists what the one installed
    does without. The Lua filters work without pandoc.Caption, pandoc.TableBody and
    pandoc.log (Pandoc 3.2); a pandoc-crossref built for another Pandoc than the running one is not run (it would leave
    ?? for the numbers) and a WARN says which release to get. scripts/build_zipapp.py makes dist/pdfmd.pyz, pdfmd and
    its packages with bundled pure-Python YAML and pypdf in one file for a machine with no network (it unpacks itself once into
    ~/.cache/pdfmd/pyz/), and a folder of wheels does the same with pip's --no-index --find-links.

Packages a document's commands need (v3.27.16; auto kind `texpackages`):
    A LaTeX build of a document that uses \\ce/\\cee/\\cf (mhchem) or \\SI/\\si/\\num/\\qty/\\unit (siunitx) without
    loading the package stopped with "Undefined control sequence". tex_package_args adds a guarded load, after
    everything else in the preamble: nothing when the package is loaded already (a house package's options win), when
    the command is defined some other way, or when the package is not installed. It is a header file, last.

Header files and header-includes (v3.27.18):
    Pandoc puts --include-in-header files and `header-includes:` in one template variable, and the command line wins:
    any header file pdfmd adds (the code-wrapping one for a document with code, graphicx for a raw \\includegraphics,
    the fonts header, preamble.tex, the packages above) dropped the document's own `header-includes` or, without
    them, a metadata file's, and the first command from them stopped LaTeX. keep_header_includes runs on the finished
    command and puts back what Pandoc would have kept: the document's own (the last input's, when there are several),
    else the last metadata file's in Pandoc's order, as a header file of its own. A metadata file's go first (after
    the code-wrapping header), where a shared preamble goes; the document's own last but for the packages header. An
    --include-in-header or `-M header-includes` of your own replaces them, as in Pandoc.

Inline calculator (v3.30.4, names and `::: calc` v3.30.6, {subs} v3.30.8):
    inline code followed at once by a bare `{=}` becomes its value: `2026 - 2006`{=} is 20; `C = n / V = {ans:4sf}` inside
    the span prints the text with the value put in and stores C (full precision, found anywhere in the document, parts
    included); `A = 4 - 2` stores and prints nothing; `::: calc` calculates the lines that hold {ans} without backticks.
    pdfmd_lua/calc.lua has its own small parser (+ - * / ^ ** % // %/%, parentheses, |abs|, a trailing % as a label, pi,
    deg, sin cos tan cot sec csc and their inverses, hyperbolics, sind cosd tand asind acosd atand, exp ln log log10 log2
    sqrt cbrt abs sign floor ceil trunc round min max hypot factorial qnorm pnorm qt pt, and sum mean median var sd stdev sem rsd ci
    gstat gcrit of a few numbers) and runs nothing; a `::: {.calc-table names="t*"}` div lists names with their values as a table. What it cannot evaluate keeps its
    text, with one WARN. `<-` assigns like `=`; a second {ans} on a line repeats the value in another format
    (`= {ans:1dp}, so {ans:0dp}`) or calculates a new expression (`so round(n) = {ans:0dp}`); whatever follows the last {ans}
    of a `::: calc` line is copied as it is (`ppm Ca^2+^`); `x = a * b = {subs} = {ans}` prints the expression with the
    names replaced by their values (the digits each was defined with; the computation keeps the full value), and
    `calc: {subs: true}` does that before every {ans} ({nosubs} on a line turns it off). A ```{=calc} block (``` ```{=} ``` is read again
    from the source), a `::: {.calc .hide}` div and `calc: {constants: file.csv}` hold statements, one per line, that print nothing
    unless they carry an {ans}; `code`{=calc} is `code`{=}. In a `::: calc` div the paragraphs
    that hold a calculation line have no first-line indent and its prose keeps the document's (`calc: {noindent: lines}`, the
    default since 3.33.18; true takes it off every paragraph of the div, false gives the whole div the document's own; an `indent=`
    on the div, or a nested `::: indent` / `::: noindent` div, wins). Added by
    `calc_filter_args()` only for a document that has such a span or div. The settings are
    `pdfmd-options: {calc: {enabled, digits: 4sf|2dp, round: even|away, subs, typeset: true|display, noindent, space, align}}` (`calc: off` is the short form), --calc /
    --no-calc, --calc-digits, --calc-round, --calc-subs / --no-calc-subs, --calc-typeset [inline|display] / --no-calc-typeset, --calc-typeset-upright, --calc-typeset-italic, --calc-noindent [lines|all] / --no-calc-noindent, --calc-space, --calc-align or --setup; round() sends an exact half to the
    even digit (R, Python) unless away. Needs Pandoc (the built-in renderer shows the source as written). README "Calculations inside the text";
    docs/recipes.md 1.11.

Paragraph indent for a stretch of text (v3.30.0):
    a fenced div `::: {indent=false}` (also `indent=true`, `indent=2em`; `::: noindent`, `::: {.noindent}`, `.indent`;
    the value may sit in the class word: `::: indent=3in`, `::: .indent=3in`, `::: indent-3in`, `::: {.indent-3in}`, and a
    near miss such as `.indent3in` gets a WARN) sets the first-line indent of the paragraphs inside it and puts the document's own back at the closing `:::`
    (pdfmd_lua/indent.lua, added by `indent_filter_args()` only for a document, or a part, that has such a div): LaTeX
    and Beamer in a `\\begingroup` ... `\\endgroup`, Typst a `first-line-indent` rule, HTML a `text-indent` style; the
    Markdown writers keep the div, the others drop the setting with a NOTE. docs/recipes.md 1.9.

The space between paragraphs (v3.33.58):
    `pdfmd-options.paragraph-spacing` (also the config and pdfmd --setup) or `--paragraph-spacing LENGTH`: what a paragraph
    break adds to the line spacing, a length (pt, mm, cm, in, em), 0 or auto (the default: each engine's own). LaTeX and
    Beamer get `\\setlength{\\parskip}` in a header file, Typst `#set par(spacing: <leading> + X)` (pdfmd_lua/typst.lua); with
    `indent: true` Typst's spacing is its leading, as LaTeX drops parskip then. The HTML engines are not given it
    (pdfmd_paragraph). docs/recipes.md 1.9.

Typst's line spacing (v3.33.73):
    pdfmd_lua/typst.lua puts lines `linestretch` x LaTeX's \\baselineskip for the `fontsize` apart in Typst, in any font
    (`#set text(top-edge: 0.7em, bottom-edge: "baseline")` and `#set par(leading: ...)` at the top of the body); without
    paragraph-spacing or `indent: true` a paragraph break adds Typst's own 0.55em. docs/recipes.md 1.9.

Page breaks (v3.27.13, off unless asked since v3.27.15):
    `pdfmd-options.pagebreak` (true, or a list of families: comment, tex, html, div, typst, word; also the config and
    pdfmd --setup), `--pagebreak [KIND ...]` and `--no-pagebreak` add pdfmd_lua/pagebreak.lua to every Pandoc route,
    before raw.lua. A block that is only a page break, in a chosen family's spelling (the comments
    <!-- pagebreak|page-break|newpage|new-page --> and <!-- pdfmd: pagebreak -->; \\newpage, \\pagebreak[n],
    \\clearpage, \\cleardoublepage; a CSS-break or class="pagebreak" div or hr; an empty `::: pagebreak`; a raw Typst
    #pagebreak(); a raw Word break), becomes the target's own: LaTeX \\newpage{}, Typst #pagebreak(weak: true), a CSS
    break div for HTML/EPUB/WeasyPrint, a Word break, an OpenDocument paragraph in the Pagebreak style (added to the
    reference pdfmd builds, pdfmd_office/odt.py), ConTeXt \\page, ms .bp, a form feed in text, <!-- pagebreak --> in
    GitHub Markdown. A spelling in the target's own language stays as written; slides drop it with a NOTE. Without
    the option every writer keeps only its own spelling, as before. The built-in renderer always read the comment and
    TeX spellings itself (PAGE_BREAK_RE, PAGE_BREAK_COMMENT_RE); tests/test_pagebreak.py holds the one list both are
    checked against.

Math in WeasyPrint (v3.27.12, v3.28.11, v3.28.46):
    WeasyPrint does not draw MathML, Pandoc's default HTML math: each formula printed twice as flat text. For
    `-e weasyprint` pdfmd gives Pandoc --math-method=plain (unless the command line chooses the math) and
    pdfmd_lua/weasyprint.lua says once that the math is text. A direct .html page with MathML goes to a browser first.
    With KaTeX (`pdfmd --install math:katex`: KaTeX's files, pinned and checked, and node's own release when there is
    no node) the filter typesets the math instead: one node call (pdfmd_lua/katex.cjs) gives each formula as KaTeX's
    HTML, the page links KaTeX's stylesheet and fonts, and WeasyPrint prints it as a browser does; a formula KaTeX
    cannot read stays text, with one WARN. `--math-method=...` on the command line keeps Pandoc's math.
    With MathJax 4 too (`pdfmd --install math:mathjax`: the npm packages, pinned and checked, and the STIX Two math font)
    MathJax is asked first (pdfmd_lua/mathjax.cjs: CHTML and its stylesheet, with a few rules that undo WeasyPrint's
    misplacing of stacked glyph boxes), KaTeX takes the formulas it cannot read, and the rest stays text.
    `--no-auto mathjax` leaves the math to KaTeX.

Tables in an HTML engine's PDF (v3.28.3):
    Pandoc's own page style is for a screen: a table is a full-width block that scrolls sideways, and a word may
    break anywhere. On paper Calibre cut a caption off at the width of a narrow table and WeasyPrint set it a syllable
    a line. While that style is in (no --css of your own), a table is a table again, at its natural width and
    centred as LaTeX sets it; Calibre's caption is up to 4in wide as in LaTeX. WeasyPrint has no max-content width:
    its caption is as wide as the table, which is at least 4in, and breaks between words. A numbered equation (the
    LaTeX filter's three-cell table) spans the line with its number at the margin, without a table's rules.
    WeasyPrint's rules go into `header-includes`, so an --include-in-header of your own replaces them, as it
    replaces the document's.

A file's properties (v3.28.5):
    A Word, OpenDocument or PowerPoint file carries none of pdfmd's own settings among its custom properties (Pandoc
    writes every metadata key it does not know there, and pdfmd hands its filters folders of this machine that way:
    `pdfmd-office-path`, `pdfmd-raw-cache`), and a Word or PowerPoint picture's description names a file of pdfmd's
    cache, the temporary folder or the home folder by its name alone. When a house style's cover takes the title and
    authors out of the metadata (nulabreport), the file's properties keep them: a Calibre, WeasyPrint, Typst (0.12 and
    later) or LibreOffice PDF's Title and Author, a Word or OpenDocument file's Title and Author.
    A title or authors with LaTeX in them (`\\emph{trans}`) keep its words in every PDF's Title and Author, a LaTeX
    engine's included (v3.28.6: Pandoc leaves raw LaTeX out of `title-meta`, hyperref's pdftitle).

Links Typst would stop on (v3.27.11):
    LaTeX and HTML only warn about a link to an anchor the document does not have; Typst stops the build. For Typst (a
    PDF or a .typ file) pdfmd_lua/typst.lua runs last and makes such a link its text, with one WARN naming the anchors.
    Pandoc's Typst writer labels headings, divs, spans, figures and tables; a link to another element's id is text too.

Images LaTeX cannot read (v3.25.7; the package pdfmd_images):
    LaTeX reads PDF, PNG and JPEG, not SVG. In a LaTeX build pdfmd converts each SVG a document names -- a Markdown
    image, a raw `\\includegraphics{a.svg}` or `\\includesvg{a}` -- once, with the first converter found (rsvg-convert,
    Inkscape, cairosvg, svglib, LibreOffice), keeps the PDF in ~/.cache/pdfmd/images by the file's content, and the
    Lua filter pdfmd_lua/images.lua puts it where the document wrote the SVG. A Markdown SVG is left to Pandoc when
    rsvg-convert is installed (Pandoc converts it itself). A raw `\\includegraphics` also gets graphicx, which Pandoc
    only loads for a Markdown image (a PNG in one failed with "undefined control sequence"). Without any converter
    there is one WARN naming the file and what to install. A remote image (http/https) in a Markdown image is fetched
    once into ~/.cache/pdfmd/images/remote (PNG, JPEG, SVG, PDF; seven days; an older copy is kept if the fetch
    fails), which is what makes it work with a Pandoc built without HTTP support (Homebrew's is) and for an SVG badge;
    with no network there is one WARN and Pandoc leaves the description. `--no-auto svg` and `--no-auto remoteimages`
    turn the two off.

No Pandoc, or no PDF engine (v3.20.0):
    pdfmd still turns a Markdown file into a plain PDF, with a pure-Python
    renderer: inkmd, vendored in pdfmd_inkmd/ (stdlib only, offline,
    deterministic), or md2pdf (PyPI `pymd2pdf`, ReportLab; footnotes,
    bookmarks, math) when installed -- `pdfmd --install math` / `pip install
    "pdfmd-cli[math]"`, and `--install emoji` for the colour emoji font.
    It is picked automatically only when no Pandoc route exists (a failing
    Pandoc build never falls back to it); -e inkmd / -e md2pdf / -e native or a
    `pdf-engine:` setting asks for it. Every input is read as GitHub-flavoured
    Markdown: Pandoc-only syntax is converted or stripped with one WARN per
    kind, title/author/date become a title block and the PDF's own metadata,
    other front-matter keys are listed as unused. Not available there: filters,
    preambles, citations, slides, parts/report mode, non-Markdown input.
    See normalise_gfm() in lib/pdfmd_native and the "native tier" section of pdfmd.py.

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
    says what it matched. Cyrillic (Russian, Ukrainian, Belarusian, Kazakh)
    is always understood; other scripts are romanized only by the packs
    --translit / PDFMD_TRANSLIT turns on (greek armenian georgian hebrew arabic
    hangul kana built in; han and other through pypinyin/anyascii, `pdfmd
    --install translit`): `pdfmd --translit greek tyche` finds "Τύχη.md".
    A name that fits two documents equally well is an
    error listing both, never a pick. `--no-auto lookup` turns all of this
    off (a command line switch only -- the document is not found yet when its
    own `pdfmd-options` could say so). Single-file lookup only: -b and -r are
    unaffected.

    Bare `pdfmd` (no name) in a folder with several Markdown files used to stop with a
    list; since v3.32.9 it chooses (an `AUTO MD` line says what it beat and why). A
    document's own `priority:` (at the root of the front matter or in `pdfmd-options`)
    is a number (higher wins), `draft` or `0` (loses to every other document), `final`
    (above every number; `final final`, `FINAL!!!` and `final67` are further degrees),
    `never` or a negative number (not in the list), or nothing (`none`, `null`, `nil`).
    A file name says the same when its siblings are there: `report.final.md`,
    `report.rewritten.md` and `report_v3.md` beat `report.md`, `report_draft.md` and
    `report.old.md` lose to it; names settle which VERSION of a document, `priority`
    which DOCUMENT, and a `priority` written in any member of such a family switches the
    names off for it. Equal tops: the newest file is built, with a WARN naming them all.
    An exact name (`pdfmd report`) always wins; `--no-auto priority` brings the old list
    back. The rules are pdfmd_ranking (pure). The words and their order are settings
    (v3.32.10): classes of words on a ladder, `names: family|folder|off`, `by: [priority,
    newest]`, in a `ranking.yaml` (`.pdfmd/` of the folder or any folder above it, or
    beside the config file), in `pdfmd-options: {ranking: ...}` of a document, a metadata
    file, the folder settings or the config; the nearest to the documents wins.
    `--newest` builds the newest file of the folder; `--all` counts the `never`
    documents too. A `priority: never` (v3.32.11) leaves a document out of what a
    folder gives -b, -r and --view as well; a named document is always built.
    `pdfmd --which` (v3.32.12) says what a bare `pdfmd` would build and why, with the
    rules and the files they came from, and builds nothing; `--which NAME` says which
    file a name finds.

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

    Calibre (v3.28.0) is an engine when named: `-e calibre` (or `ebook-convert`, or `pdf-engine: calibre`); with no engine
    named (v3.29.1) it, and the browsers (headless Chrome, Chromium, Edge, Brave), are last resorts after the numbered
    engines and before LibreOffice (automatic_engines).
    Pandoc writes one standalone HTML page (MathML, pictures inlined, the
    same filters, citations and fonts as WeasyPrint gets) and Calibre's
    `ebook-convert` prints it; Calibre draws the math with its own MathJax.
    Its page is the document's (papersize, geometry, margin, classoption and
    lang, read as for a Word file; else Letter and 1in like LaTeX), 12pt
    unless `fontsize:` says otherwise, page numbers at the foot, bookmarks
    from the headings. What the document says in LaTeX goes through the
    filter of the Word route (made native, or drawn by LaTeX as a picture,
    references numbered by a LaTeX build per `office: {labels}`), as for
    LibreOffice. Found on PATH, in calibre.app or in Program Files\\Calibre2.
    Calibre as a writer (v3.29.0): `-o book.azw3` / `--to azw3` (azw3, mobi, kepub, lit, lrf, pdb, rb, snb, tcr, pmlz, htmlz,
    txtz: the twelve only Calibre writes) has Pandoc write an EPUB 3 in a scratch folder and `ebook-convert` make the ebook
    from it; epub, docx, rtf, txt and fb2 go the same way only with `-e calibre` on the command line. One document at a
    time. LibreOffice writes `.doc` and, by default, `.odt` (rtf, txt, epub with `-e soffice` first) from Pandoc's Word file.
    A browser is an engine too (v3.29.0): `-e edge|chrome|chromium|brave|browser` has it print the HTML page headless.
    The math: a target that can show pictures gets each formula drawn by LaTeX (the Word route's `latex: images`; the
    EPUB's MathML is not drawn by a Kindle or a Kobo), a plain-text one gets the formulas as text with one WARN
    (pdfmd_lua/ebook.lua); epub and htmlz keep MathML.

    An ebook as input (v3.29.1): `pdfmd book.epub` (or .mobi, .azw3, .kepub ...) reads the book as Markdown in a scratch folder
    (Pandoc for an EPUB; Calibre's ebook-convert to an EPUB first for the others) and builds it as any file is, to
    `book.pdf` beside the book; `-o book.md` keeps the Markdown.

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
    Modern for most prose); if that run reports missing glyphs, the WHOLE
    document is rebuilt with DejaVu Serif instead, which has near-total
    coverage of the arrows/comparison-operator/Greek symbols that plain
    Unicode notes tend to use in running text. A WARN line says so, naming
    the font, the code points and the new font (`STIX Two Text lacks U+2265;
    rebuilt in DejaVu Serif (set mainfont: to keep your own)`). That retry is
    for what the per-word fallback below cannot see: it reads literal
    characters, so a TeX command set in text mode (`\\geq` from a `$...$` that
    Pandoc did not take for math) only shows up as a missing-glyph line of
    the build. -f/--font, or the document's own `mainfont:`, always wins
    outright over both and is never retried.

    A `$...$` whose closing `$` is directly followed by a digit (`$\\geq$3`,
    `$\\pm$10`) is not math to Pandoc (it keeps "costs $5 and $10" as text);
    pdfmd says so before the build, WARN `file:line`, and what to write
    instead (`$\\geq 3$`). It is the usual cause of the retry above.

Text in other scripts (v3.23.0, lualatex/xelatex):
    No main font draws everything a multilingual document says. pdfmd reads
    the character tables of the installed fonts (pdfmd_unicode/, no
    dependency), finds the characters of the text -- Markdown, metadata and
    bibliography files, code excluded -- that the main font cannot draw, and
    sets each run of them in the first installed font of its script's list
    (Arabic and Hebrew right-to-left, Han in the Chinese, Japanese or Korean
    flavour the text or its `lang:` points to, symbols and punctuation in the
    font of the text beside them). How much changes is `pdfmd-options: {fallback: MODE}`
    (--fallback, the config file): word (default: the whole word in one
    fallback font, so no word mixes two fonts), char (just those characters),
    document (the installed font that draws most of the document becomes the
    main font), off (nothing: Pandoc's own behaviour; false is the same), box (no
    fallback, a black box per missing character) or error (no fallback, the
    build stops). A font the document names is only replaced in document mode;
    pdfmd's own default (STIX Two Text) is replaced, with an AUTO MAINFONT note,
    by a serif with the letters when the document is mostly in a script it lacks
    (Kazakh Cyrillic). `missing: warn | box | error` is what happens to
    characters no installed font draws.
    Characters no installed font has are listed in
    a WARN, never silently dropped or replaced. A document that sets up its
    own scripts (ucharclasses, \\newfontfamily, xeCJK, \\babelfont,
    CJKmainfont, mainfontfallback) is left to itself unless
    `pdfmd-options: {unicode: true}`; `--no-auto unicode` turns it all off.
    Fonts a build cannot load are dropped and the build retried without them.
    Code is checked against the monofont the same way: Typst gets the missing
    characters' fonts as its `codefont` list, WeasyPrint as a CSS font stack; under
    LaTeX inline code and
    code blocks get their own missing characters set in a fallback font (a code
    block that needs one becomes a fancyvrb Verbatim, losing its syntax
    highlighting); math is left to unicode-math.
    Emoji under lualatex/xelatex, which cannot draw colour fonts, become
    pictures: the PNG of each emoji sequence (flags, skin tones, ZWJ families,
    keycaps, found through the font's own ligatures) is read out of the colour
    emoji font (`--install emoji`, or a system Noto Color Emoji) into pdfmd's
    cache and included at text height.
    Typst gets the same runs as `#text(font: ...)` (it does no per-script
    fallback of its own that finds CJK) and WeasyPrint styled spans. The
    fonts: `pdfmd --install fonts` lists what pdfmd can fetch (STIX Two,
    JetBrains Mono, Noto and Amiri for most scripts, CJK, DejaVu, colour emoji),
    `--install fonts:arabic,cjk-sc` (groups core, scripts, cjk, all; aliases
    such as ja, kazakh) fetches into ~/.local/share/pdfmd/fonts, every file
    checked against a checksum pinned in pdfmd; `--uninstall fonts:NAME`
    removes. Those fonts are found by every engine: LaTeX gets them by file and
    Path, Typst by --font-path, WeasyPrint by @font-face.

    Word and OpenDocument output (--to docx|odt, or -o x.docx): Pandoc builds the file from a
    reference document; pdfmd writes the document's papersize/geometry/margin/classoption,
    mainfont/sansfont/monofont/CJKmainfont/fontsize/linestretch/lang/indent and its own house
    look into a copy of it (pdfmd_office/). A reference.docx/.dotx (.odt/.ott, .pptx/.potx) beside
    the document, in metadata/, named by `pdfmd-options: {office: {reference-doc: F}}` or in the
    config folder is used instead of Pandoc's default and only the `office:` block changes it;
    `--init-reference` writes one; `--no-auto officeref|officestyle`. Fonts Word does not ship are
    mapped to Times New Roman/Arial/Consolas (`office: {fonts: exact}` keeps them).
    A Lua filter (pdfmd_office/office.lua, `office: {latex: auto|off}`, `--no-auto officelatex`) makes
    LaTeX native in those outputs: mhchem \\ce and siunitx \\si/\\SI/\\num as text and Word math,
    equation environments as Word equations with numbers, raw figure/tabular via Pandoc's LaTeX reader,
    \\ref/\\cref/captions numbered from the .aux of a PDF build made once in the cache
    (`office: {labels: off}` counts instead). What remains (tikz, chemfig, unknown macros, rejected math,
    PDF/EPS pictures) is compiled in the document's own preamble (fragments.py: one fragment per page via
    `preview`, cropped, SVG + 300 dpi PNG with the depth for baseline alignment, cached by content under
    ~/.cache/pdfmd/office/) between two runs of the filter, and a .docx is finished by docx_post.py (SVG
    beside the PNG, baseline, width). A house style's macros are declared in `office.lua` / `<name>-office.lua`
    (`office: {profile: F}`, `--no-auto officeprofile`): ignore = {...}, commands = {name = function(args)...},
    pandoc = function(doc).

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

    `pdfmd-options: {html: {...}}` shapes an HTML build; without a full
    page setting, pdfmd's HTML output stays a fragment:

        pdfmd-options:
          html:
            self-contained: true   # one file, everything inlined
            standalone: true       # a full page, resources left linked
            math: mathml           # mathml | mathjax | katex | webtex | plain
            css: style.css         # a name or a list, relative to the document

    `self-contained` is `--standalone --embed-resources` (`--self-contained`
    on a Pandoc older than 2.19); HTML maths defaults to MathML, including fragments, the one
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
    `parts` not carried), `hst` (the document's NAME.hst history file, v3.25.8), `preamble` (the preamble file(s), at the head of
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
    is in `~/.config/pdfmd/trusted-filters.txt`); a file from elsewhere, or one
    whose filter was edited, has the filter skipped with a warning (the
    build still completes) unless --trust-embedded. Not carried: the
    defaults pdfmd derives per machine (fonts, margins), re-derived on
    build, and -V/command-line options. A document with no front matter and
    a bare leading `# Title` keeps its preamble out of the file (a new
    front-matter block would stop the title being promoted), with a
    warning. YAML is re-written by PyYAML (bundled fallback; YAML 1.1 rules, comments lost: an
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

    --strip-comments / --keep-comments, `pdfmd-options: {strip-comments: true}`
    (v3.22.0) drop every `<!-- -->` comment from the assembled file (and, from
    the next releases, from the source attached to a PDF), for notes to oneself
    that should not travel: reviewer remarks, drafts, the BUILD NOTES block. A
    comment inside a fenced or indented code block or an inline code span is
    text and stays, YAML front matter is not touched, and pdfmd's own markers
    stay (`<!-- pdfmd-... -->`, `<!-- pagebreak -->`). A comment alone on its
    line takes the line (and a blank line it leaves doubled) with it; one in a
    sentence takes one of the spaces around it. The command line wins over the
    document, then its metadata files.
    (v3.22.4) The option names the kinds of source: `true`, `false`, a list
    (`[preamble, bibliography]`: just those), or a mapping per kind
    (`{markdown: false}`: the rest follow the default, which is all of them for
    an attached source and none for --assemble-only). Kinds: markdown, preamble
    (LaTeX `%`: a `%` closing a line stays bare, since it swallows the break;
    `\\verb`, `\\url`, verbatim environments and `% !TEX` lines are text),
    bibliography (the text between a .bib's entries), csl (XML comments),
    metadata (YAML `#` comments and the file's own quoting and layout: the merged
    text cannot hold them, so the attachment stores each metadata file and the
    document's front matter as written and --restore writes them back byte for
    byte; v3.25.13). --strip-comments-in KINDS / --keep-comments-in KINDS do the
    same per run. Lua filters are never touched. The data files of `.csv`
    blocks are stored with every attached source (small, and the text needs them).

    --attach-source / --no-attach-source, `pdfmd-options: {attach-source: true}`
    (alias `embed-source`) (v3.22.1): after a PDF build, attach the document's
    whole source to the PDF -- the assembled Markdown with every kind embedded
    (so it builds the same anywhere), comments stripped unless strip-comments
    says otherwise, as `pdfmd-source.md`, beside `pdfmd-manifest.json`, which
    records the original layout: the file names and where each sat, where each
    part of a parts document began and the front matter its part had, the
    images the text points at (recorded with their hashes, not stored), the
    document's own no-auto. Any viewer lists them as the PDF's attachments.
    The attached bibliography holds only the entries the text cites (and those
    they cross-reference; every entry if the document has `nocite: '@*'`), so a
    shared .bib of hundreds of entries does not travel whole: `pdfmd-options.
    attach-bibliography: all` / --attach-bibliography all keeps the file as it is.
    The same setting prunes the bibliography --assemble-only and --merge embed (v3.33.57).
    Attachments are deflated. (v3.22.4)
    Off by default: the source holds everything its author wrote. A -r/--report
    build attaches its chapters (each keeping its own front matter) with the
    folder layout relative to their common folder (v3.22.5); not for a section
    build (name#section) or a non-PDF target.
    --restore FILE.pdf [-o DIR] (v3.22.1) writes the layout back into
    FILE.restored/ (or DIR): name.md, metadata/, a preamble, filters, the
    bibliography, parts/ ... -- --unpack --slim does the splitting of what was
    embedded, the manifest the placing. Never overwrites (stops, writing nothing,
    if a file is there), never writes outside the folder (a path with `..`, an
    absolute or a drive path is refused). A restored Lua filter is a file beside the
    document like any other, so a build runs it: restore says so and names it
    (building from the attached file itself, `pdfmd-source.md`, still runs an
    embedded filter only if this machine's pdfmd wrote it, as always). Exit status 1 if the attached
    text no longer matches its recorded hash. The YAML is the re-written one
    (comments lost, as --unpack says), the text is the original's less its
    comments, and the restored folder builds the same `.tex` the original did;
    data the text points at is not in the PDF and has to be put back beside it
    (or stored, see --bundle). --list shows what the PDF carries and writes
    nothing.
    (v3.22.6) The images the Markdown points at need no bundle: the PDF holds
    every picture it drew, and the manifest records which is which (by size and
    order; a JPEG by its bytes). Restore takes them out: a JPEG byte for byte, a
    PNG or other raster as a PNG of the PDF's pixels (alpha kept, the file is
    not the original's), an SVG or PDF figure as a one-page vector PDF -- a
    restored `fig.svg` is `fig.pdf`, and the restored Markdown points at it
    (restore says so). A picture the PDF does not hold (TikZ, pgfplots) is only
    recorded. Raw LaTeX `\\includegraphics{...}` in the Markdown or the preamble counts
    like a Markdown image (v3.22.8); one in a stored .tex file is stored with --bundle.
    (v3.28.13) The global metadata file (pdfmd --setup) is the building machine's, not
    the document's: the source layers it lowest, as a build does, and --restore and
    --unpack leave it out with one line naming its keys. A metadata file from outside
    the document's folder comes back in outside/, with the -y list that layers it.

    (v3.28.15) A PDF with its source attached also carries, without any bundle setting,
    the files the text reads and never the images: `bundle: sources`, the new default
    (the LaTeX files it \\inputs, the data its macros read, listings; the PDF itself
    holds the pictures and --restore takes them out of it, those only an \\input'ed
    .tex draws included), so a restored report builds again. `bundle: false` /
    --no-bundle keeps the source alone; `true` adds the image files; a Markdown output
    (--keep-source) is not given the default. --restore and --unpack count what they
    write by folder, and --verbose lists each file (--restore --list always does).

    (v3.28.16) A build's decisions are three lines: FOUND (the metadata, preamble, filter and
    parts picked up), DEFAULTS (the global metadata, margin, fonts and packages applied because
    nothing said otherwise) and `AUTO: KINDS` (the rest), each cut at 110 characters;
    --verbose prints each with its reason (AUTO YAML, AUTO TEX ...). See AutoLog.

    --bundle [sources|all] / --no-bundle, `pdfmd-options: {bundle: sources | true | all | false}` (v3.22.2)
    store, beside the source, the files it cannot carry, each as its own
    attachment (`files/PATH`; no archive, so any tool lists or extracts one):
    `--bundle` the images and data the text and the preamble point at -- found
    from Markdown images, `<img>`, `file="..."` CSV tables, \\includegraphics,
    \\input, pgfplots tables, listings, and any word that is a relative file name
    naming a file that exists (so data reached by a project's own macros is found
    too); `--bundle all` every file in the document's folder except the output,
    hidden files and folders, .aux/.log and the like, and backups. It implies
    --attach-source; the Markdown files stored this way lose their comments like
    the source does. A file outside the document's folder is named in a note and
    not stored. `pdfmd-options.bundle-max-mb` (default 100) caps the total: over
    it only the source is attached, with a warning. --restore writes the files
    back, never over an existing one, checking each hash. With it a restored
    folder builds the same PDF text as the original (checked on a parts report).
    (v3.22.5) A stored text file is read in turn for the files it points at (a
    figure's .tex that \\inputs its raw data), and an `\\input` that only the
    machine's TeX tree finds (`kpsewhich`, outside the TeX distribution: a
    compound library installed beside a house style) is stored and restored
    beside the document. `--bundle-packages` / `pdfmd-options.bundle-packages`
    also stores the packages and classes a preamble loads from that tree and the
    graphics they name, so a machine without the house style builds the same;
    without it they are recorded (name, version) and restore says what is
    missing. The manifest also records the fonts the metadata names and what
    made the PDF (pdfmd, pandoc, the engine). Data a macro builds the name of
    (`data\\i.csv` in a loop) cannot be found: `--bundle all` is the fallback.

PDF in, Markdown out (v3.22.7): a PDF given to pdfmd is read, not built. The
direction follows the files: a `.pdf` input, `-o x.md`, `--to md`. `pdfmd
paper.pdf` writes paper.md beside it (`--to txt` / `-o x.txt` for plain text;
`-o DIR` puts DIR/paper.md). A PDF that carries its own pdfmd source (see
--attach-source) is restored instead -- the exact thing that was written; ask
for its pages with --extract, or by naming an output file (`-o x.md`) or --to.
All of the reading is batchocr's (text layer or OCR, reading order, headings,
tables): pdfmd finds it (`$PDFMD_BATCHOCR`, `batchocr` on PATH, or the module in
this Python), checks it is 1.2.4 or newer, and passes it the PDF with every flag
pdfmd does not know itself, unchanged -- `--ocr`, `--lang`, `--export-images`,
`--page-breaks`, `--preview-only`, `--keep-headers`, `--stats`, `-q`, `-c`, ...
(the names of M1ck4's pdfmd, whose PDF-to-Markdown batchocr vendors, MIT). Flags
pdfmd owns are mapped: `-o/--output`, `-t/--to`, `-j`, `-v` (a switch here, counted
for batchocr: `-vv` is two), `--engine` (only a `FORMAT=ENGINE` value goes on).
Abbreviations are off on this route, so no flag is swallowed by a longer pdfmd
one. Mixed PDF and Markdown inputs, `-o x.pdf` and a target pdfmd cannot read a
PDF as (html, docx, ...) are refused. The exit status is batchocr's.
`pdfmd --install batchocr` pip-installs `batchocr[md]` (PyMuPDF, AGPL-3.0, as its own
package, never bundled) from the tagged GitHub release into the Python pdfmd runs
from; `--check-dependencies` reports batchocr, Tesseract and Poppler. `--install batchocr` also
offers Tesseract and Poppler through the system's package manager, and `--install ocr:rus,kaz`
fetches Tesseract language files (pinned `tessdata_fast`, pdfmd_unicode/tessdata.py) into
~/.local/share/pdfmd/tessdata, which PDF reading hands to Tesseract (TESSDATA_PREFIX) when it
has every language `--lang` names and the user set no TESSDATA_PREFIX.

Finishing touches on the built PDF (v3.22.9, ideas from mdpdf), all with pypdf, so
they work with every engine and are off unless asked for: --bookmarks adds PDF
bookmarks from the Markdown headings when the engine made none (headings are
found again in the PDF's own text, in order; a contents page is not mistaken for
the chapters); --header/--footer "LEFT,MIDDLE,RIGHT" print a running header and
footer in Helvetica, with {page} {pages} {header} (the current top-level heading;
{heading} is the same) {date} {title} (a comma inside a field is written \\,;
characters Helvetica cannot draw are reduced to their base letter or `?`);
--attach-links attaches the local files the document links to
(`linked/PATH`) with a paperclip in the margin beside the link; --pdf-title,
--pdf-subject, --pdf-author and --pdf-keywords set the PDF's properties without
touching the document; --paper SIZE is `-V papersize=SIZE` and also sets the
built-in renderers' page. The built-in renderer's own options are flags too:
--family helvetica|times, --no-autolinks, --no-html, --allow-unsafe-urls,
--allow-remote-images, --emoji-fallback name|drop. Two more commands answer to
the keys of the tools these came from: `mdpdf` (mdpdf's -o -h -f -t -s -a -k -p
and long names, with bookmarks and attached links on, several inputs combined into
one PDF) and `inkmd` (inkmd's -o, --page-size and the flags above, `-e inkmd`
unless an engine is named; it reads standard input when no file is given and writes
the PDF to standard output for `-o -`, or when standard output is not a terminal
and no -o is given). Their page-size default is pdfmd's own, not Letter. `batchmd`
is `pdfmd -b` on one folder, the current one when none is named.

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
    pdfmd_lua/csv_table.lua; v3.24.18: cells are Pandoc Markdown (`reader="gfm"` for
    plain GFM), a `: Caption {#tbl:id}` or `Table: Caption` paragraph right after
    the block, or `caption="..."` among its attributes, is the table's caption,
    and a relative `file=` is found beside the document, not only in Pandoc's
    working folder). Delimiter is auto-detected (v3.27.5: the one of , ; tab |
    that splits the first 20 records evenly, parsed as CSV, the extension's own -- tab for .tsv,
    else comma -- on a tie; a WARN when it is not the extension's), or set
    with a `delimiter="..."` attribute or `csv: {delimiter: ...}`; a cut table
    keeps its first and last rows and columns with a row/column of an ellipsis
    between them (`cut="head"` / `csv: {cut: head}`: the first ones only);
    the first row is treated as a header
    unless `header="false"`. Capped at 10 rows and 7 columns by default (for every
    table: --csv-rows/--csv-cols, `pdfmd-options: {csv: {rows, cols, header, reader}}`
    or --setup, v3.27.2) --
    `rows`/`cols` attributes override either (a number, or `all` for no
    cap) -- so an accidentally-huge CSV doesn't produce a many-page table
    nobody intended; a truncated table gets both a one-line `WARN` (naming
    how many of how many rows/columns were kept) and a note printed
    directly under the table itself, in the rendered output, not just on
    the compiling terminal. A `.csv` div with neither `file=` nor data, or one
    naming a file that can't be opened, gets a `WARN` and is left empty
    rather than failing the whole compile. Inline data may sit in the bare
    `::: csv` (no braces; `file=` and `align=` need them); `pdfmd-options: {csv: off}` (the short
    form of `csv: {enabled: false}`), --no-csv or --setup leaves every `.csv` div as written, a
    plain div with its text, and no WARN (--csv, PDFMD_CSV for -j workers; a mapping such as
    `csv: {rows: 30}` keeps the tables on).

    v3.25.1: the data may be written inside the div, in a fenced code block
    (read verbatim: nothing in it is Markdown) or as plain lines; `file=` wins
    when both are there. The delimiter is a character or its name (`comma`,
    `semicolon`, `tab`, `pipe`, `space`, `colon`), else the extension's, else
    guessed from the first line (, ; tab |). Alignment: `align="lcr"` or
    `align="left,center,right"`, or a second row of `---`, `:--`, `:-:`, `--:` (a
    separator row, as in a pipe table; the attribute wins; `separator="none"`
    keeps such a row as data). `widths="5,1,1"` are relative column widths, kept
    as given (a separator row's unequal dashes are widths too, counted as Pandoc
    counts them). Quoted fields may hold line breaks. The native tier (no Pandoc)
    reads the same forms except `widths=`. Works for any output format
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

Code blocks (v3.25.3; pdfmd_lua/code.lua, LaTeX engines):
    Long code lines wrap at the margin (fvextra's breaklines, breaking anywhere when there is no space; a block with
    no language, which Pandoc makes `verbatim`, becomes a fancyvrb `Verbatim` so it wraps too) instead of running
    past it; a TeX without fvextra still builds, without the wrapping. `--no-code-wrap`, `pdfmd-options: {code-wrap:
    false}` or `--no-auto codewrap` turn it off, `{wrap=false}` does for one block. Lines can be numbered: Pandoc's
    own `{.numberLines startFrom=10}` for a block, `--line-numbers [STEP]` / `pdfmd-options: {line-numbers: true,
    line-number-step: 5}` / --setup for all of them (`{.noNumberLines}` exempts one), `step=5` and `numbersep=8pt` for
    one block. Typst, WeasyPrint and HTML wrap code by themselves. (The header that loads fvextra,
    pdfmd_lua/code_wrap.tex, goes in with --include-in-header, and only for a document that has code: a header
    set from the Lua filter is lost whenever pdfmd passes its own, since Pandoc lets --include-in-header win
    over `header-includes`. Inline code is not wrapped.)

Tables to CSV and back (v3.25.2; the package pdfmd_tables):
    `pdfmd --extract-tables doc.md` rewrites the document so that each table -- pipe, simple, multiline or grid;
    not the ones inside code -- is a `.csv` block reading `tables/<name>.csv` (`--tables-dir`; `--tables-inline`
    writes the data inside the block instead), with the caption as `caption="..."` (a caption with quotes stays a
    `: caption` line under the block), the alignments as `align="lcr"`, the widths the document chose as `widths=`
    (only a pipe table with a line over Pandoc's 72 columns has any; a grid table's are percentages of the line),
    `rows=all`/`cols=all` when the table is over the 10 x 7 cap and `separator=none` when its first data row is
    all dashes. The files are named from the captions, else `table1`, `table2`... by position (`--table-names a,b,c`
    names them all; the count must match, or it is an error); a file that exists with other content is never
    overwritten. Before anything is written Pandoc reads the old and the new document (the CSV filter applied) and
    the two must give the same tables; the old document is copied to the backup folder first (see below). Tables
    Pandoc cannot write as CSV (several lines of block content in a cell, spans, no header row) are left with the
    reason. `pdfmd --expand-tables doc.md` is the reverse: every `.csv` block, all its rows, becomes a pipe table
    with `caption=` under it as a `: caption` line; the CSV files stay where they are. `--dry-run` shows the diff
    and writes nothing. A document in parts has every part done.

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
    without its numeric prefix, a folder, or its number, or a range of numbers `45-60`; several joined with
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
    sections print as ??, unless the cache is on (below) and the document was
    built whole before: then they are filled in from that build. Needs Pandoc (not the built-in renderers or the
    soffice fallback); `--no-auto lookup` leaves only the exact name, ignoring
    case and spaces. `--split` cuts at the same headings, setext ones included.

The global config file (v3.23.6):
    ~/.config/pdfmd/config.yaml ($XDG_CONFIG_HOME, %APPDATA%\\pdfmd; PDFMD_CONFIG
    names another file, an empty value none). `options:` holds `pdfmd-options`
    defaults for every document -- the lowest source, below the document's own
    block and its metadata files, below the command line; `translit:` the
    romanization packs of the lookup (below --translit and PDFMD_TRANSLIT).
    --init-config writes a commented template, --show-config says what is set.
    `pdfmd --setup` edits it from a menu (v3.23.6; v3.27.0: every flag and every
    pdfmd-options key is either one of its rows or in its list of what it leaves
    out on purpose, with the reason -- `o` shows that list; pdfmd_setup/inventory.py
    is the table, and a test keeps it complete). `disabled:` (v3.27.8; setup's d)
    switches whole --help topics off: hidden from help, completion and setup,
    refused on the command line unless --disabled is given.
    What pdfmd itself remembers (trusted-filters.txt, the dismissed native-renderer
    offer) lives beside it, not in the cache that --clear-cache empties.

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

    Cross-references of a part built alone (v3.26.0; `pdfmd-options: {seed-labels: ...}`, --seed-labels):
    a part (`report#methods`) or a section (`doc#results`) is typeset without the rest, and its references to the
    rest used to print `??` unless the cache held a full build's .aux. Now, for LaTeX engines, pdfmd has Pandoc write
    the LaTeX of the WHOLE document once more (no images, no engine; about a second), pdfmd_labels reads which
    headings, captions, equations and labels it holds, and LaTeX replays them at the start of the part (counting
    done by LaTeX, so the document's number style and cleveref apply; a part's own numbers continue from the parts
    before it). Order: the part's own labels, the last full build's .aux (exact; cache on), the scan. Approximate for
    whatever the document defines itself; \\pageref stays `??`. auto (default) | aux | scan | draft | off.

    Flat Markdown (v3.26.3; `--to gfm`, `pdfmd-options: {gfm: {scripts, math, title}}`, --gfm-scripts, --gfm-math):
    plain GitHub-flavoured Markdown that any viewer shows as it is. The build is the one of any other target
    (includes, parts, `.csv` tables, pandoc-crossref, citeproc, the raw option's `md` family, the document's filters);
    pdfmd_lua/flat.lua runs last and writes the title block, captions as `**Table 1.** text`, Unicode sub/superscripts,
    GitHub anchors, section numbers in the headings, and counts what no Markdown can carry. The output is
    `<name>.gfm.md` beside its source; `--to gfm+raw` is Pandoc's own gfm writer. A Markdown writer never replaces its
    own source. `--keep-source [packed|readable]` ends a Markdown output with its source in one HTML comment
    (v3.26.4; pdfmd_flat/keep.py), `pdfmd --restore FILE.md` writes it back. `--to txt` (v3.26.7; also `-o x.txt`) is the
    same build written by Pandoc's plain writer: the title and the headings underlined, `text <url>` for a link,
    `[Figure 1. Caption]` for a figure, no raw piece left; `--to plain` is Pandoc's own plain writer. `--to ascii` and
    `--to ascii:FORMAT` (v3.26.8; pdfmd_flat/asciify.py, pdfmd_lua/ascii.lua; `-o x.ascii.txt`, --ascii-missing) build a
    text format with no byte above 127: the words are mapped before the writer, the written file once more.

    The closing line names the engine that made a PDF (v3.26.10): `OK    report.md  (lualatex)`, or
    `(typst; lualatex, xelatex failed)` when the build fell back. `--strict` (or `pdfmd-options: {strict: true}`;
    `--no-strict` overrides) turns a build that printed a WARN line, or about which Pandoc warned (a missing image or
    citation, a LaTeX undefined reference), into a failed file: the output is kept, the exit code is 1.

    The closing line says how long the build took (v3.31.4): `OK    report.md > report.pdf  in 3:07  (lualatex)`, also for
    a file that failed. `--verbose` adds a TIME line for every step. `build-time: on|off` (`--build-time` / `--no-build-time`)
    and `time-format: auto|clock|seconds|words|TEMPLATE` (`--time-format`; tokens {d} {h} {hh} {m} {mm} {s} {ss} {s1} {s2}
    {ms}) are `pdfmd-options` keys and `--setup` rows; the history file records the seconds as `took=`.

    Every build leaves a record (v3.31.5): a plain-text file in the cache (`cache: location`: ~/.cache/pdfmd/builds/, or
    .cache/pdfmd/builds/ beside the document) with the command line, the settings and versions, every command run, what pdfmd
    printed whatever --verbose said, what the engines answered, the steps and their times. A build that failed prints
    `full record: PATH`; `pdfmd --last-build FILE [--failed]` shows the newest. `build-log: on|failed|off` (--build-log MODE),
    `build-log-keep` (5; the newest failed record stays besides) and `build-log-max-size` (KB, 512) are `pdfmd-options` keys
    and `--setup` rows. The home folder is written as `~` in the file.

    A Lua filter pdfmd finds by itself is noted (v3.26.11): a NOTE the first time this machine runs it and the first
    time after it changed; it runs either way, and nothing prompts. `--trust-lua FOLDER|FILE` marks what is yours;
    only `--strict` skips a new or edited filter outside a trusted folder.

    `pdfmd FILE --check` (v3.26.15) reads a Markdown document (a scaffold and its parts as one) and reports, without
    building, a missing image or csv file, a link or #anchor to nowhere, a duplicate {#id}, an undefined @fig:x or
    \\ref, a citation the bibliography lacks, a footnote without text, a skipped heading level, a fence or comment
    never closed, front matter that does not parse. The reading is in the pdfmd_check package; the exit code is 1 on an
    error (a warning too with `--strict`); `--check-ignore`, `pdfmd-options.check-ignore` and
    `<!-- pdfmd-check: ignore CODE -->` turn checks off.

    A fenced ```mermaid, ```d2 or ```dot block (v3.26.16) is drawn by mmdc, d2 or dot when installed and replaced by the
    picture in the format the output takes (pdfmd_lua/diagram.lua); `--no-auto diagrams` leaves the code. A tool run may take
    `diagram-timeout` seconds (v3.32.1; default 120, 0 = draw nothing, negative = no limit): pdfmd_lua/limited_run.py stops a
    run that takes longer with the processes it started, and the diagram stays as code with a warning.

    `pdfmd-options: {slide-notes: off | show | only}` (v3.32.2) makes a `-p` deck show its `::: notes` blocks (Beamer's
    `show notes` / `show only notes`, as a header, so the deck's own `classoption` is kept; `off` is the default).

    A fenced ```smiles block, ```{.smiles caption="..."} or `::: smiles` div (v3.31.42) is a chemical structure written as text:
    one SMILES per line (a name after it is written under it), or a molfile, SD file, Tripos mol2 or InChI, or `file="x.mol"`
    beside the document. It is drawn with RDKit (pdfmd_smiles; one call per document, pictures kept by content, engine and
    settings) as a PDF for LaTeX, an SVG for HTML and Typst, a PNG for Word and OpenDocument (`office-format: svg` for SVG), an
    SVG beside flat Markdown, a figure when it has a caption (`{#fig:id}` works with pandoc-crossref). The settings are
    `pdfmd-options.smiles` (engine, format, office-format, palette, cell-width, cell-height, per-row, bond-length, dpi), each also an
    attribute of the block; `--no-auto smiles` leaves the blocks as code. Chemfig and Indigo as engines are to follow.

    `pdfmd --init [TEMPLATE] [NAME]` (v3.26.17) starts a document from a template (pdfmd_templates: article, report, notes,
    slides, book, and your own in the config folder's templates/); nothing that exists is overwritten.

    Size budgets (v3.26.18): `--max-asset-mb` / `--max-output-mb` (or `pdfmd-options: {max-asset-mb, max-output-mb}`) make a
    build warn about an image, or an output, over the budget; `--check` lists the images (asset-large). Off unless set.

    Where it lives (v3.23.12): `cache: {location: global | document}`, --cache-location,
    the config file's `options:`. global (default) is ~/.cache/pdfmd; each folder
    records its document (.pdfmd-source.json: path, stem, folder name, SHA-256),
    and a document with no cache under its path takes over a cache whose recorded
    original is gone (a move): same stem and same content, else same stem and the
    same folder name when only one fits; a copy never takes the original's. document
    is a `.cache/pdfmd` folder beside the document (CACHEDIR.TAG, .gitignore) that
    travels with it. Plot-cache entries record the folders they were made in and
    are re-pointed at the new ones after a move. --clear-cache clears both.
    `pdfmd --cache-info` (v3.33.74, lib/pdfmd_cache/manage.py) shows each part's size and the stale part (a
    document cache or build records whose recorded document is gone); `--clear-cache builds|documents|stale|all`
    clears one part, never following a link; `--doctor` notes a cache over `cache.max-mb` (config, default 1000).

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

    A section or element of an ordinary document (`pdfmd doc#NAME`) gets the
    labels half of this: with the cache on and the whole document built before,
    its `\\ref`s to the rest of the document read the last full build's numbers
    instead of printing ??. Its own headings, figures, tables and equations
    are still numbered from its first (there is no counter marker in a document
    that is not in parts mode), and a label the section defines itself is its
    own. pandoc-crossref leaves `\\ref{..}` in LaTeX output, which is what makes
    this work; for HTML or DOCX it reports undefined cross-references itself.
    Nothing is read when the section is written over the full document's own
    output name (`-o doc.pdf`).

    What the cache does NOT do: it never skips a build or reuses a rendered
    page. Pandoc runs and LaTeX typesets the whole document, from the current
    sources, package and Lua filter, every time; only LaTeX's own cross-
    reference files carry over. A change to the package, the preamble or the
    text therefore shows in the very next build (and LaTeX asks for the extra
    pass itself if a number moved). Build with --no-cache, or `pdfmd DOC
    --clear-cache` first, when verifying a change to the package itself.

    Picture cache (`cache: {plots: true}`, --cache-plots; LuaLaTeX; a package opts in by mentioning `pdfmdCacheDir`
    in its style file, the protocol is described above CACHE_HANDSHAKE; nulabreport >= 1.26.0 is the first): the
    package's whole pictures (plots, chemical schemes) are stored as PDFs in the
    document's cache folder after the build that first typesets them, and the
    next build (a part built alone too, unless its preamble differs by more
    than the title) includes them at their exact size
    instead of drawing them again -- the expensive part of a report full of
    spectra. A plot not stored yet is simply typeset inline, so a build never
    depends on this having worked. Staleness is closed off three ways: the
    folder is keyed by a hash of nulabreport.sty, the document's whole
    preamble, the engine version and TeX Live's package database (any change,
    a `tlmgr update` too, starts a new folder; old ones are pruned); each
    entry records the files its standalone job really read (LaTeX's
    -recorder) under the report's folders and the user's own TeX trees, with
    their SHA-1, and is dropped when one changes, so editing a CSV redraws
    exactly the plots that use it; and the entry's key covers the call, its
    arguments, the layout it read and the colours set by the call's own keys.
    On a real 29-page report: 98 s plain, 55 s with the aux cache, 35-45 s
    with both; pages identical to the uncached build to 0.05 bp in every
    word. `pdfmd --clear-cache` deletes the folder (a document's, or
    everything), always safe.

    The cache route is also what makes `citation-engine: natbib`/`biblatex`
    work with parts (the Pandoc-run bibliography path takes one input file);
    it runs bibtex/biber between passes. Limits: it does not retry a
    document that needs the DejaVu glyph fallback (name `mainfont:`), and
    natbib/biblatex still can't express a table caption's citation through
    a Lua filter that rebuilds captions (nulabreport.lua does).

Pipe-table column widths (v3.25.0): a `---|---` separator says nothing about the columns, so a table whose
    lines run long is laid out by pdfmd_lua/table_width.lua -- the widths that give the fewest lines within the text
    width, each column at least as wide as its longest word -- and a table that fits is left at its natural width.
    Unequal dashes (`--|-----`) are a choice and kept, but only under Pandoc's own Markdown reader (front matter, or a
    linked metadata file): the `gfm` reader of a plain file gives the dashes no width. Pandoc counts colons as dashes.
    v3.31.0: a chosen column too narrow for its longest word (a word of up to 16 characters) is widened to it and the
    other columns give up the room (`column-word-floor: off` for a table where breaking a word is meant).
    A cell more than `column-outlier` (2) times longer than the next one in its column, at least 30 characters, in a
    column of four rows or more, does not size its column: it wraps and the others keep their room (0 switches it off).
    `pdfmd-options: {column-widths: keep}` (or the same in the config, or --setup; `table-widths` is the older name) leaves every table as written;
    `force` ignores the dashes and balances every table. A table's own `{widths=force word-floor=off}` after its
    caption wins. `--no-auto tablewidth` switches the filter off. LaTeX engines only: the other writers take Pandoc's
    widths as given.

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
    section for why), typstdirect and htmldirect (the same for a .typ and an
    .html file: off, they go through Pandoc), svg and remoteimages (see "Images LaTeX cannot read" above), pdfimages (PDF images in HTML builds become SVG), diagrams (fenced mermaid/d2/dot blocks drawn by mmdc/d2/dot), smiles (smiles blocks drawn as chemical structures), crossref (the auto-detected `--filter pandoc-
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
    files to `--include-in-header`, read through every option layer relative
    to the file naming them; added to whatever
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
    three keys require YAML support and a document that already has a `---`
    block; silently ignored (not an error) if the YAML installation is broken.

The history file (v3.25.8; the package pdfmd_history). In `pdfmd-options` the setting is `stamp:`, and `history:` is an alias for it (v3.30.24; where
    both give a field, `stamp` wins):
    `--stamp-store file` (or `pdfmd-options: {stamp: {store: file}}`) writes each compile to NAME.hst, in the
    document's backup folder (see Backups), instead of into the document's BUILD NOTES: the document is not edited by
    a build. `both` does both. A .hst is one entry per line, newest first -- `WHEN | KIND | TEXT | key=value ...`,
    KIND being compiled, restored, partial or note, the key=value words holding the hash of the source at that moment (`sha`) and
    the output (`out`) -- so two files join with `cat`, diff cleanly, and `--merge-history A.hst B.hst [-o OUT]` keeps
    every entry once. `--history-to-file FILE` moves the whole BUILD NOTES block(s) pdfmd owns (the "Compiled ..." line, the "Compile
    History:" list, and any text written by hand inside, as one `note` entry with `block=1`) into the .hst, and
    `--history-to-notes FILE` builds the block again from it;
    both back the document up first, `--dry-run` only shows. A document may carry several BUILD NOTES blocks (the
    author's, an AI agent's): pdfmd writes into the one that already holds its lines, else the only block there is
    (the hand-kept convention it automates), else -- several, none its own -- into a block of its own; everything else
    in any block is left as it is, and a block with a line `pdfmd: ignore` is never touched. The .hst is the
    `hst` embed kind: `--embed-metadata` folds it into the assembled file (`type: hst`), `--unpack` writes it out,
    `--attach-source` stores it in the PDF and `--restore` puts it back beside the backups.
    A build of some parts or sections (`pdfmd @60`) writes no BUILD NOTES line; `--stamp-partial` (or `stamp: {partial: true}`,
    off by default, `--no-stamp-partial` over a document that set it) makes it leave a `partial` entry in the .hst (store file
    or both): the parts it built (`parts=`), those whose text differs from the last entry that saw them (`changed=`), and those
    no entry has seen (`new=`); a full build in parts mode records every part's hash (`shas=`) to compare with.

The hybrid PDF and single files that carry their data (v3.25.10):
    `--hybrid` (or `pdfmd-options: {hybrid: true}`, or --setup) makes the PDF a LibreOffice "hybrid PDF": it carries an
    OpenDocument copy of the document as an attachment named Original.odt (.odp, .ods), described as "Embedded original
    document of this PDF file", and LibreOffice then opens the PDF as that editable document, not the pages in Draw
    (checked: LibreOffice goes by the attachment, not by what the pages show, so any engine's PDF can carry one). An
    Office file is converted by LibreOffice (.docx to .odt, .pptx to .odp, .xlsx to .ods; an ODF file is taken as it is);
    anything else is built to .odt by pdfmd itself with the same metadata, so what LibreOffice shows is the Word-route
    rendering of the source, not the LaTeX pages. `pdfmd --restore FILE.pdf` writes the ODF file back (with the source
    too, when `--attach-source` was also on). `--embed-metadata files` (or `all`, or `embed: {files: true}`) adds the
    `files` kind to an assembled file: the images, CSV data and included files the text and preamble point at, as
    `type: file` blocks (text as it is, anything else base64), written to a scratch folder for a build and searched like
    the document's own folder (resource path, TEXINPUTS), and written back byte for byte by `--unpack`. It is not in the
    default kinds because it can be big (`pdfmd-options.bundle-max-mb`, 100 by default, caps it).

Versions: --history, --history-diff, --history-restore, --init-backups (v3.25.9):
    `pdfmd --history FILE` lists the versions of a file, newest first, as one numbered list: its backups -- in the
    configured folder and in every folder of the spellings pdfmd and its author have used beside it (`.backups`,
    `backup`, `backups`, `.backup`, `_backups`), whichever naming form each file has (`report.md.bak.20261003110005`,
    `report_20261003-110005.md`, `report.md.20261003-110005.bak`, ...) -- the git commits that changed it (the
    repository may be above the document's folder), and the compiles and restores recorded in its .hst or BUILD NOTES that
    no backup holds. A backup shows what was compiled when it was taken (read from its own BUILD NOTES, else matched by
    hash in the .hst). The newest 15 are shown; --history-all lists the rest. In a terminal the list is navigable
    (a number: what differs, `d N`: the diff, `r N`: restore, `a`: all, `q`). `--history-diff REF` prints the diff
    between the file and a version; `--history-restore REF` puts it back. REF is a number of the list, a backup's
    timestamp (any prefix: 20261003), a file name, a commit hash (4 digits or more), `latest`, or `previous` (the newest
    version that is not the file as it is). A restore first backs the file up (the state it was in is never lost),
    keeps the BUILD NOTES and history of the file as it is (an old version has the notes of its own day), and adds a
    "Restored version ID (NAME) -- WHEN" entry to the history -- the .hst when the document keeps one, else its
    BUILD NOTES -- unless `pdfmd-options: {stamp: {restored-note: false}}` or --no-restored-note says not to, or the
    document has never been stamped. --dry-run shows the difference without writing.
    `pdfmd --init-backups FILE` (v3.25.9) sets `backup` and `stamp: {store: file}` in the file's front matter (or its
    metadata.yaml) after an `# AUTO GENERATED` comment, without touching what is there, makes the folder (--backup-folder
    DIR, default .backups), backs the file up once and starts its .hst. A document with neither front matter nor a
    metadata file is not given one (that would change how pdfmd reads it); `--init-backups --global` sets the same in
    the config for every document.

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
    `.backups/` beside it (v3.25.2: a hidden folder; an existing `backup/`, `backups/` or
    `.backup/` is kept using; the first time, a note says where the copies are). Runs after the BUILD NOTES stamp, and writes
    nothing when the newest existing snapshot already matches (ignoring the
    stamp's own lines). --no-backup forces it off for one run. Same front-
    matter/metadata-file cascade as `stamp:` above, as a bare `true`/
    `false`, a directory name, or the full form:

        ---
        pdfmd-options:
          backup:
            dir: backup      # relative to the document; default `.backups`
            format: dashed   # see below; default `compact`
            keep: 30         # newest N plain snapshots; 0 = none, negative = all (the default)
            pdfs: 5          # newest N built PDFs; 0 = none (the default), negative = all (v3.32.42)
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

    The built PDF is kept too (v3.32.42): a rebuilt source cannot give an old PDF back, because pdfmd, a package or a kit may
    have changed since. After each successful PDF build the file is copied into the same folder as `report_20260924-091500.pdf`
    (the stamp of the source copy of that run, so the two pair up; a collision gets `-2`), unless the newest copy is the very
    same file. `pdfs: N` sets how many: the newest N; `0` none (the default: off unless asked for); a negative number every
    one. (`keep:` counts the source copies the same way; before v3.32.43 its 0 meant all.) A partial build's PDF
    (`report.results.pdf`) is kept under its own name. A PDF with another name (`report_submitted_...pdf`) is a milestone: never
    counted, never removed. `--setup` has the row ("Built PDFs kept per document").

Kits (--kit, --kits, --install kit:SOURCE; v3.31.34 on):
    A kit is a folder with a `.kit` (or `NAME.kit`) file that packs a pipeline: a LaTeX class or package, its Lua filter,
    default metadata, a citation style. `--kit NAME[:MODE]` or `pdfmd-options: {kit: ...}` chooses one; its folder is on
    TEXINPUTS (for Tectonic, -Zsearch-path, v3.32.6), so nothing is installed into TeX. `pdfmd --install kit:owner/repo`
    fetches the kits of any repository (v3.32.7; nothing in it is run), `--kits` lists them. A kit may switch off pdfmd's own
    margin, font or table-width defaults with `no-auto:` (v3.32.8), and a kind of universal markup with `markup-off:`
    (v3.33.68). The README's Kits section is the full description.
"""
from __future__ import annotations

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

PDFMD_VERSION = "3.33.252"
import argparse
import atexit  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 18)
import contextlib  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 17)
import hashlib
import io  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 17)
import importlib.util
import json  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 17)
import platform
import urllib.parse  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 12)
import struct
import zipfile  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 17)
from collections import namedtuple
from pathlib import PurePosixPath
import functools
from functools import lru_cache
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time  # noqa: F401 -- read as pdfmd.time by tests/test_install_calibre.py

if sys.version_info < (3, 9):
    raise SystemExit(f"pdfmd needs Python 3.9 or newer (this is {sys.version.split()[0]}). "
                     "Install it with `pipx install pdfmd-cli`, "
                     "which picks a suitable Python, or run pdfmd.py with a newer python3.")
import unicodedata  # noqa: F401 -- retain start-up modules and the module attribute
import warnings
import inspect  # noqa: F401 -- read as core.inspect by lib/pdfmd_bridge/odt.py and as pdfmd.inspect by tests
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from shutil import which
import tempfile
from tempfile import NamedTemporaryFile, mkdtemp
from textwrap import dedent
from typing import Callable, Iterator


# A checkout keeps the pdfmd_* packages in lib/ beside this file; an installed copy has them in site-packages and a zipapp at
# its root, where there is no lib/ to add. Resolved, so the symlink ~/dev/python-projects/pdfmd.py finds the real lib/.
try:
    _checkout_lib = Path(__file__).resolve().parent / "lib"
    if _checkout_lib.is_dir() and str(_checkout_lib) not in sys.path:
        sys.path.insert(0, str(_checkout_lib))
except (OSError, RuntimeError):
    pass

# pdfmd.py needs its packages from 3.33 on (the author, 2026-11-09): a copy without lib/ stops here and says why.
if importlib.util.find_spec("pdfmd_comments") is None:
    raise SystemExit("pdfmd: this pdfmd.py has no lib/ folder beside it, and the pdfmd_* packages it needs are not "
                     "installed; keep pdfmd.py together with its lib/ folder, or install pdfmd: pipx install pdfmd-cli")

from pdfmd_base import (BUILD, atomic_write_bytes, atomic_write_pdf, atomic_write_text, natural_key, noted,  # noqa: E402, F401 -- atomic_write_bytes and split_command are read by tests and lib/
                        own_python_folder, read_text_best_effort, read_text_or_none, record_note, sha1_file, sha256_text,
                        split_command, timed, vprint, write_text_lf)

# behind the Python's own packages, before the optional ones below are imported
try:
    if own_python_folder().is_dir() and str(own_python_folder()) not in sys.path:
        sys.path.append(str(own_python_folder()))
except (OSError, RuntimeError):          # a home that cannot be read, or none at all (a sandbox): nothing installed there
    pass

try:
    from pdfmd_yaml_support import yaml
except ImportError:
    yaml = None

def lazy_import(name: str):
    """The module `name`, loaded when it is first used, or None when it is not installed. pypdf alone took about half of
    every start (v3.32.55), and most runs never touch a PDF's insides. A loader that cannot load lazily (zipimport before
    Python 3.10) loads it now."""
    if name in sys.modules:
        return sys.modules[name]
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec is None or spec.loader is None:
        return None
    try:
        loader = importlib.util.LazyLoader(spec.loader)
    except TypeError:
        try:
            return importlib.import_module(name)
        except ImportError:
            return None
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


pypdf = lazy_import("pypdf")


# -- The packages split out of this file (SPLIT.md, entry 3fi) --------------------
# Each one reads pdfmd's own helpers and state as `core.X` when it runs and never imports pdfmd: run as a script this file
# is `__main__`, and a second import would be a second copy with its own state. `core` is lib/pdfmd_base's one object for
# every package, bound to this module below. The names below are re-exported, so `pdfmd.x` keeps working for the code that
# stays here, the tests and lib/.
def load_package(name: str):
    """The module `name` (a package or one module of it), imported now; its `core` is this module (lib/pdfmd_base)."""
    return importlib.import_module(name)


def deferred(module: str, name: str):
    """A stand-in for the function `name` of `module`, a package that pdfmd.py does not load at start (SPLIT.md, step 6):
    the first call loads it, and every call goes to the real function. pdfmd.py's own calls keep their bare names."""
    def stand_in(*args, **kwargs):
        return getattr(load_package(module), name)(*args, **kwargs)
    stand_in.__name__ = stand_in.__qualname__ = name
    stand_in.__doc__ = f"`{module}.{name}`, loaded on its first call."
    return stand_in


# The names table: name -> the module that serves `pdfmd.NAME` (a name that code here calls bare has a stand-in instead).
# Filled below by `names("pdfmd_x.role", "a b c")` lines (pdfmd_base.names_into, 3.33.189) and `DEFERRED_NAMES.update(...)`.
DEFERRED_NAMES: dict[str, str] = {}


def __getattr__(name: str):
    """`pdfmd.X` for a name in DEFERRED_NAMES (PEP 562): the package's own object, its module loaded on the first read.
    It is kept in this module's globals, so a later read is a plain lookup and never comes here again."""
    if name in DEFERRED_NAMES:
        value = globals()[name] = getattr(load_package(DEFERRED_NAMES[name]), name)
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


import pdfmd_base  # noqa: E402
pdfmd_base.bind(sys.modules[__name__])      # every package's `core`, before any of them is imported; the first binding wins
names = pdfmd_base.names_into(DEFERRED_NAMES)   # the names table's lines: names("pdfmd_x.role", "a b c")
from pdfmd_comments import (CommentPolicy, comment_kind_set, parse_comment_policy,  # noqa: E402, F401 -- the strip_*_comments are read by lib/ and tests, comment_kind_set by lib/pdfmd_run
                            strip_markdown_comments, strip_tex_comments, strip_xml_comments)
from pdfmd_templates import init_command  # noqa: E402, F401 -- read by lib/pdfmd_run
from pdfmd_watch import pinned_watch_argv, run_watch  # noqa: E402, F401 -- read by lib/pdfmd_run, pinned_watch_argv by tests too

from pdfmd_hybrid import attach_hybrid, hybrid_after_success, resolve_hybrid  # noqa: E402, F401 -- attach_hybrid is read by tests/test_embedding.py

from pdfmd_polish import (HF_FIELDS, fill_hf_field, hf_text, locate_headings, markdown_headings,  # noqa: E402, F401 -- read by tests
                          parse_hf_template, polish_pdf)
from pdfmd_pdfimages import (encode_png, extract_pdf_images, file_picture_size, match_images_to_pdf,  # noqa: E402, F401 -- encode_png, file_picture_size and samples_to_png are read by tests
                             rewrite_image_paths, rewrite_tex_image_paths, samples_to_png)
from pdfmd_compat import (batchmd_main, batchmd_translate, inkmd_main, inkmd_translate,  # noqa: E402, F401 -- the *_main are console entry points (pyproject.toml), the *_translate are read by tests
                          md2pdf_main, md2pdf_translate, mdpdf_main, mdpdf_translate, pan_tec_main, pan_tec_translate)
import pdfmd_view  # noqa: E402
from pdfmd_view import (pager_command, run_pager, stdin_build, terminal_view,  # noqa: E402, F401 -- run_pager, view_pager_setting and view_sources are read by tests, stdin_build and terminal_view by lib/pdfmd_run
                        view_pager_setting, view_sources)

from pdfmd_lookup import (LOOKUP_FIELD_WORDS, LOOKUP_TIERS, LookupAmbiguous, cyrillic_candidates,  # noqa: E402, F401 -- LookupAmbiguous, lookup_fields, lookup_key, rank_lookup, document_priority, priority_enabled and source_markdown are read by tests or lib/
                          document_priority, find_wildcard_markdown, latin_candidates, lookup_fields, lookup_key,
                          priority_enabled, rank_lookup, source_markdown, strip_lookup_suffix)

import pdfmd_routing  # noqa: E402, F401 -- no longer read here: lib/pdfmd_run, its one reader, imports it itself
from pdfmd_routing import (BATCHOCR_TAG, EBOOK_INPUT_EXTENSIONS, batchocr_spec, find_batchocr,  # noqa: E402, F401 -- BATCHOCR_TAG, EBOOK_INPUT_EXTENSIONS, batchocr_spec, install_ocr_tools and tessdata_environment are read by tests, the route_*_input by lib/
                           install_ocr_tools, route_ebook_input, route_pdf_input, route_text_input, tessdata_environment)

import pdfmd_bridge  # noqa: E402, F401 -- tests read pdfmd.pdfmd_bridge
from pdfmd_bridge import (CALIBRE_TABLE_CSS, PANDOC_TABLE_STYLE_RE, browser_page_css, calibre_html_command,  # noqa: E402, F401 -- CALIBRE_TABLE_CSS and PANDOC_TABLE_STYLE_RE are read by tests, run_calibre_convert and run_soffice_convert are patched or read by tests and lib/, start_soffice_job by lib/pdfmd_run and tests
                          calibre_page_options, convert_office_direct, convert_via_soffice_bridge, prince_author_options,
                          run_browser_print, run_calibre, run_calibre_convert, run_soffice_convert, start_soffice_job)
from pdfmd_restore import (RESTORE_CHAIN, check_source_command, layout_from_source, restore_attachments,  # noqa: E402, F401 -- RESTORE_CHAIN, layout_from_source, restore_attachments, restore_attachments_in_place and restore_chain are read by tests, restore_target_name by tests and lib/, check_source_command, restore_from_markdown and restore_from_pdf by lib/ (the last by tests too)
                           restore_attachments_in_place, restore_chain, restore_from_markdown, restore_from_pdf,
                           restore_target_name)
from pdfmd_parts import (ATX_HEADING_RE, Heading, NoPartMatches, ScaffoldPlan, SectionPlan, chapter_order,  # noqa: E402, F401 -- ATX_HEADING_RE, Heading, NoPartMatches, collect_parts, find_heading, heading_parts, outermost_headings, parts_directory, plan_sections, scan_headings, scan_items, select_parts, split_into_parts, split_top_level_sections and wrap_runs are read by tests or lib/
                         collect_parts, find_heading, heading_parts, outermost_headings, parts_directory, plan_scaffold,
                         plan_sections, scaffold_inputs, scan_headings, scan_items, section_source, select_parts,
                         split_into_parts, split_top_level_sections, wrap_part, wrap_runs)
from pdfmd_doctor import (DEEP_SAMPLE, PANDOC_FEATURES, completion_options, completion_script, deep_checks,  # noqa: E402, F401 -- DEEP_SAMPLE, PANDOC_FEATURES, completion_options, deep_checks, foreign_commands, pandoc_limits and tool_note are read by tests, completion_script and doctor_report by lib/pdfmd_run and tests
                          doctor_report, foreign_commands, pandoc_limits, tool_note)
import pdfmd_cache  # noqa: E402, F401 -- read as pdfmd.pdfmd_cache by tests
from pdfmd_cache import (TEMPORARY_PLACES, adopt_moved_cache, cache_directory, cache_location, cache_root,  # noqa: E402, F401 -- TEMPORARY_PLACES and cache_location are read by tests or lib/; adopt_moved_cache is named in a docstring only
                         document_cache_root, folder_is_writable, source_fingerprint, temporary_place)
import pdfmd_install  # noqa: E402
from pdfmd_install import (GRAPHVIZ_COMMANDS, GRAPHVIZ_SHA256, GRAPHVIZ_VERSION, INSTALL_SPECS, MATHJAX_FONT_SIZES,  # noqa: E402, F401 -- all but install_extra, install_kind and uninstall_kind are read or patched by tests; install_kind and uninstall_kind are lib/pdfmd_args's type= for --install and --uninstall
                           MATHJAX_SOURCE_SHA256, TECTONIC_REPOSITORY, calibre_asset_pattern, calibre_package_manager,
                           calibre_release_asset, d2_asset_name, detach_disk_image, download_file, extract_executable,
                           github_latest_release, github_release_asset, install_calibre, install_d2, install_extra, install_kind,
                           install_mathjax_files, install_tectonic, install_typst, node_asset_name, release_asset_matching,
                           safe_unpack_tar, tectonic_asset_pattern, typst_asset_name, uninstall_kind, unpack_graphviz, unpack_katex)
from pdfmd_tex import (MAX_TEX_DIRECT_PASSES, PLOT_CTX_PLAIN, PLOT_CTX_TWICE, compile_tex_direct,  # noqa: E402, F401 -- MAX_TEX_DIRECT_PASSES is named in the docstring only; PLOT_CTX_PLAIN, PLOT_CTX_TWICE, latex_engine_command, plot_recorded_inputs and run_tex_engine are read by tests or lib/
                       document_latex_definitions, engine_failure_reason, is_latex_preamble, latex_engine_command,
                       package_latex_keys, pandoc_refused_command, plot_preamble, plot_recorded_inputs, render_plot_requests,
                       run_tex_engine, tex_failure_cause, tex_tree_stamp, wrap_latex_header_includes)
from pdfmd_attach import (ATTACH_FORMAT_PLAIN, add_deflated_attachment, attach_source_after_success,  # noqa: E402, F401 -- all but attach_source_after_success, bundle_files, keep_source_after_success and referenced_images are read by tests or lib/
                          attached_bundle_mode, block_places, bundle_files, drop_blocks, drop_duplicate_blocks, find_in_tex_tree,
                          graphic_names_in, held_comments_note, inline_blocks, inline_candidates, keep_source_after_success,
                          layout_path, read_pdf_attachments, referenced_images, source_attachments, tex_distribution_roots,
                          write_pdf_attachments)
from pdfmd_assemble import (EmbedPlan, assemble_markdown_text, embedded_resources, filter_bibliography,  # noqa: E402, F401 -- filter_bibliography, remember_trusted, render_embedded_block, render_embedded_file, trust_store_path, unpack_assembled and used_citation_keys are read by tests or lib/
                            parse_embedded_blocks, remember_trusted, render_embedded_block, render_embedded_file,
                            trust_store_path, trusted_hashes, unpack_assembled, used_citation_keys, write_assembled_markdown)
import pdfmd_native  # noqa: E402, F401 -- read as pdfmd.pdfmd_native by tests
from pdfmd_native import (CALIBRE_MARKDOWN_EXTENSIONS, CSV_DIV_LINE_RE, PAGE_BREAK_COMMENT_RE, PAGE_BREAK_RE, PAPER_SIZES,  # noqa: E402, F401 -- all but MathText and convert_native are read by tests
                          MathText, author_names, convert_native, csv_div_table, csv_guess_delimiter, csv_keep,
                          ignored_front_matter_keys, inline_math, native_font_size, native_landscape, native_order, native_page,
                          native_paper, mapped_author, normalise_gfm, author_names_in_place)
from pdfmd_args import build_parser  # noqa: E402, F401 -- read by tests and lib/

# Moves into packages that are not loaded at start (SPLIT.md, step 6): stand-ins that load the module on the first call.
paragraph_spacing_latex_args = deferred("pdfmd_paragraph", "latex_args")
paragraph_spacing_typst_args = deferred("pdfmd_paragraph", "typst_args")
paragraph_spacing_command_line = deferred("pdfmd_paragraph", "apply_cli")
fullcite_pre_args, fullcite_old_spelling = (deferred("pdfmd_fullcite", name) for name in ("fullcite_pre_args", "fullcite_old_spelling"))
chain_plan_build = deferred("pdfmd_chain", "plan_build")
chain_stopped = deferred("pdfmd_chain", "stopped")
chain_engine_failed = deferred("pdfmd_chain", "engine_failed")
ansi_width_argument = deferred("pdfmd_ansi.cli", "ansi_width_argument")      # move 5 (v3.33.6)
ansi_columns = deferred("pdfmd_ansi.cli", "ansi_columns")
ansi_finish = deferred("pdfmd_ansi.cli", "ansi_finish")
ansi_without_pandoc = deferred("pdfmd_ansi.cli", "ansi_without_pandoc")
cache_command = deferred("pdfmd_cache.manage", "cache_command")                 # v3.33.74: --cache-info, --clear-cache WHAT
clear_cache = deferred("pdfmd_cache.manage", "clear_cache")
remove_cache_paths = deferred("pdfmd_cache.manage", "remove_all")
cache_size_note = deferred("pdfmd_cache.manage", "size_note")
serve_live_filters = deferred("pdfmd_serve.commands", "serve_live_filters")     # move 6 (v3.33.7); read by tests/test_serve.py
serve_command = deferred("pdfmd_serve.commands", "serve_command")
api_command = deferred("pdfmd_serve.commands", "api_command")
pandoc_extensions = deferred("pdfmd_flat.build", "pandoc_extensions")           # move 7 (v3.33.8); read by tests
flat_settings = deferred("pdfmd_flat.build", "flat_settings")
flat_writer = deferred("pdfmd_flat.build", "flat_writer")
flat_filter_args = deferred("pdfmd_flat.build", "flat_filter_args")
split_ascii_target = deferred("pdfmd_flat.build", "split_ascii_target")
ascii_missing = deferred("pdfmd_flat.build", "ascii_missing")
ascii_filter_args = deferred("pdfmd_flat.build", "ascii_filter_args")
ascii_finish = deferred("pdfmd_flat.build", "ascii_finish")
DEFERRED_NAMES.update(_PANDOC_EXTENSIONS="pdfmd_flat.build")                      # tests patch it with mock.patch.dict
document_file = deferred("pdfmd_docs.reader", "document_file")                  # move 8 (v3.33.9); read by tests
document_headings = deferred("pdfmd_docs.reader", "document_headings")
document_section = deferred("pdfmd_docs.reader", "document_section")
search_documents = deferred("pdfmd_docs.reader", "search_documents")
render_document = deferred("pdfmd_docs.reader", "render_document")
doc_command = deferred("pdfmd_docs.reader", "doc_command")
DEFERRED_NAMES.update(DOCUMENTS="pdfmd_docs.reader")                              # read by tests/test_doc.py and test_packaging.py
css_scope = deferred("pdfmd_css.latex", "css_scope")                            # move 9 (v3.33.10)
css_additions = deferred("pdfmd_css.latex", "css_additions")                    # read by lib/pdfmd_report too
css_heading_latex = deferred("pdfmd_css.latex", "css_heading_latex")            # read by tests
css_heading_args = deferred("pdfmd_css.latex", "css_heading_args")
picture_target = deferred("pdfmd_crop.targets", "picture_target")                # move 10 (v3.33.11)
multi_target_command = deferred("pdfmd_crop.targets", "multi_target_command")
picture_command = deferred("pdfmd_crop.targets", "picture_command")
vault_root = deferred("pdfmd_obsidian.vault", "vault_root")                    # move 11 (v3.33.12); read by tests
single_newline_mode = deferred("pdfmd_obsidian.vault", "single_newline_mode")
find_embedded_image = deferred("pdfmd_obsidian.vault", "find_embedded_image")
embed_source = deferred("pdfmd_obsidian.vault", "embed_source")
embed_filter_args = deferred("pdfmd_obsidian.vault", "embed_filter_args")
figure_filter_args = deferred("pdfmd_obsidian.vault", "figure_filter_args")
DEFERRED_NAMES.update(_VAULT_ROOTS="pdfmd_obsidian.vault", _EMBED_INDEX="pdfmd_obsidian.vault")   # tests empty them with .clear()
check_command = deferred("pdfmd_check.command", "check_command")                # move 16 (v3.33.17)
ranking_layers = deferred("pdfmd_ranking.choice", "ranking_layers")             # move 17 (v3.33.19); read by lib/pdfmd_serve too
ranking_clashes = deferred("pdfmd_ranking.choice", "ranking_clashes")
bare_ranking = deferred("pdfmd_ranking.choice", "bare_ranking")
priority_candidates = deferred("pdfmd_ranking.choice", "priority_candidates")
which_command = deferred("pdfmd_ranking.choice", "which_command")
user_path_command = deferred("pdfmd_setup.command", "user_path_command")           # move 19 (v3.33.21)
maybe_hint_setup = deferred("pdfmd_setup.command", "maybe_hint_setup")
setup_command = deferred("pdfmd_setup.command", "setup_command")                 # read by tests/test_atomic.py
flag_names = deferred("pdfmd_setup.command", "flag_names")                       # read by tests/test_setup.py
package_places = deferred("pdfmd_kits.locate", "package_places")                         # move 20 (v3.33.22)
kpsewhich_locate = deferred("pdfmd_kits.locate", "kpsewhich_locate")  # read by tests
read_package_helper = deferred("pdfmd_kits.locate", "read_package_helper")  # read by tests
kit_package_folders = deferred("pdfmd_kits.locate", "kit_package_folders")  # tests patch it with mock.patch.object
kits_report = deferred("pdfmd_kits.locate", "kits_report")
kit_header_insert = deferred("pdfmd_kits.locate", "kit_header_insert")
kit_header_settle = deferred("pdfmd_kits.locate", "kit_header_settle")
kit_cache_tex = deferred("pdfmd_kits.locate", "kit_cache_tex")
kit_header_resolve = deferred("pdfmd_kits.locate", "kit_header_resolve")
kit_carried_files = deferred("pdfmd_kits.locate", "kit_carried_files")
markup_header_pieces = deferred("pdfmd_tex.markup", "markup_header_pieces")       # v3.33.67
typst_template_args = deferred("pdfmd_lua.typst", "template_args")
kit_markup_off = deferred("pdfmd_kits.markup", "kit_markup_off")                   # v3.33.68
begin_timer = deferred("pdfmd_buildinfo.build", "begin_timer")                  # move 21 (v3.33.23); read by lib/pdfmd_report too
attach_time = deferred("pdfmd_buildinfo.build", "attach_time")                  # read by lib/pdfmd_report too
time_breakdown = deferred("pdfmd_buildinfo.build", "time_breakdown")            # read by lib/pdfmd_report too
last_build_command = deferred("pdfmd_buildinfo.build", "last_build_command")
csv_defaults = deferred("pdfmd_tables.command", "csv_defaults")                 # move 22 (v3.33.24); read by tests
csv_table_filter_args = deferred("pdfmd_tables.command", "csv_table_filter_args")  # read by tests
table_keep_metadata = deferred("pdfmd_tables.command", "table_keep_metadata")
tables_command = deferred("pdfmd_tables.command", "tables_command")
DEFERRED_NAMES.update(FOLDER_SETTINGS="pdfmd_ranking.choice")                     # named in a docstring only; kept as a re-export
office_package_folders = deferred("pdfmd_office.build", "office_package_folders")  # move 25 (v3.33.27)
office_defaults_sources = deferred("pdfmd_office.build", "office_defaults_sources")
find_office_profile = deferred("pdfmd_office.build", "find_office_profile")
find_reference_doc = deferred("pdfmd_office.build", "find_reference_doc")
OfficeArguments = deferred("pdfmd_office.build", "OfficeArguments")             # a class there; pdfmd.py only calls it
office_finish = deferred("pdfmd_office.build", "office_finish")                 # read by lib/pdfmd_report too
run_office_pandoc = deferred("pdfmd_office.build", "run_office_pandoc")         # read by lib/pdfmd_report too
check_docx_command = deferred("pdfmd_office.build", "check_docx_command")
init_reference = deferred("pdfmd_office.build", "init_reference")
backup_after_success = deferred("pdfmd_history.backups", "backup_after_success")                  # move 26 (v3.33.28)
backup_directory = deferred("pdfmd_history.backups", "backup_directory")
backup_pdf_after_success = deferred("pdfmd_history.backups", "backup_pdf_after_success")
backup_snapshots = deferred("pdfmd_history.backups", "backup_snapshots")
backup_summary = deferred("pdfmd_history.backups", "backup_summary")
backup_template = deferred("pdfmd_history.backups", "backup_template")
document_versions = deferred("pdfmd_history.backups", "document_versions")
entries_to_notes = deferred("pdfmd_history.backups", "entries_to_notes")
fill_backup_template = deferred("pdfmd_history.backups", "fill_backup_template")
history_command = deferred("pdfmd_history.backups", "history_command")
history_interactive = deferred("pdfmd_history.backups", "history_interactive")
history_view_command = deferred("pdfmd_history.backups", "history_view_command")
init_backups_command = deferred("pdfmd_history.backups", "init_backups_command")
notes_to_entries = deferred("pdfmd_history.backups", "notes_to_entries")
version_differs = deferred("pdfmd_history.backups", "version_differs")
version_text = deferred("pdfmd_history.backups", "version_text")
font_missing = deferred("pdfmd_unicode.fonts_choice", "font_missing")                # move 31 (v3.33.34); read by lib/pdfmd_doctor too
system_font_missing = deferred("pdfmd_unicode.fonts_choice", "system_font_missing")  # tests patch it with mock.patch.object
default_monofont = deferred("pdfmd_unicode.fonts_choice", "default_monofont")        # read by lib/pdfmd_report too
fallback_font = deferred("pdfmd_unicode.fonts_choice", "fallback_font")
preferred_font = deferred("pdfmd_unicode.fonts_choice", "preferred_font")            # tests replace it
font_args = deferred("pdfmd_unicode.fonts_choice", "font_args")                      # read by lib/pdfmd_report too
unicode_forced = deferred("pdfmd_unicode.fonts_choice", "unicode_forced")            # read by tests/test_setup.py
managed_fonts_css = deferred("pdfmd_unicode.fonts_choice", "managed_fonts_css")      # read by lib/pdfmd_report too
check_fonts = deferred("pdfmd_unicode.fonts_choice", "check_fonts")
script_fallback = deferred("pdfmd_unicode.fonts_choice", "script_fallback")          # read by lib/pdfmd_report too
# a function, but pdfmd.py never calls it and tests call its .cache_clear(), which a stand-in does not have
DEFERRED_NAMES.update(installed_font_families="pdfmd_unicode.fonts_choice")
names("pdfmd_edit.command", "put_outside_blocks source_carried source_lost")
names("pdfmd_run", "DISABLED_OK_ENV command_line_parser")
names("pdfmd_fullcite", "fullcite_post_args fullcite_command_line")
names("pdfmd_bibliography", "bibliography_indent_args bibliography_indent_command_line")
names("pdfmd_direct.route", "direct_route convert_direct convert_qmd")
names("pdfmd_build", "PREFERRED_FONT DEFAULT_MONOFONT DEFAULT_VARS WEASYPRINT_CSS_NOISE run_engine_command "
                     "_convert_one_core finish_build set_soffice_limit convert_one make_embed_plan")
names("pdfmd_cite", "CITATION_ENGINES frontmatter_citation_engine CA_BUNDLES open_url document_csl fetch_csl remote_csl "
                    "csl_args parse_bibliography convert_via_native_bibliography")
names("pdfmd_labels.seed", "PARTS_MARKER_DEFS DRAFT_SKIP_COMMANDS DRAFT_SKIP_SPANS package_draft_skips draft_skip_text "
                           "label_without_page seed_labels_file part_key seed_labels_mode SEED_CALC_MODES seed_calc_mode "
                           "parts_range_text build_calc_seed calc_marked_inputs label_scan_wanted select_wanted "
                           "build_label_scan")
names("pdfmd_cache.settings", "CACHE_DEFAULTS NOTED_PLACES provide_writable_places metadata_cwd pandoc_working_directory "
                              "CACHE_LOCATIONS CACHE_MANIFEST LOCAL_CACHE_DIRNAME prepare_cache_root write_cache_manifest "
                              "cache_settings")
names("pdfmd_tex.failure", "TEX_PROBES probe_tex_cause SHOWN_LOCATIONS source_line_for latex_error_location "
                           "report_engine_failure tex_argument")
names("pdfmd_build.results", "timing_module time_label record_engine Built engine_label built_name _WarningTee "
                             "warning_capture resolve_strict resolve_budget check_asset_budget _NONMATH_DOLLARS "
                             "nonmath_dollars check_nonmath_dollars check_output_budget strict_message")
names("pdfmd_reader", "_MARKDOWN_FEATURES contains_citations contains_crossref crossref_built_for SUFFIX_READERS "
                      "MARKDOWN_LIKE_SUFFIXES resolve_from_format flavour_reader reader_needs promote_bare_title "
                      "prepared_title_source")
names("pdfmd_filters", "has_code_block code_filter_args SVG_WARNED image_filter_args PAGEBREAK_KINDS pagebreak_value "
                       "pagebreak_kinds slide_notes_mode slide_notes_args cover_filter_args cover_header_args "
                       "pagebreak_filter_args LINEBREAK_KINDS LINEBREAK_RE linebreak_value md_macro_in md_macro_on "
                       "INDENT_DIV_RE indent_filter_args title_filter_args raw_filter_args document_filter_args "
                       "DIAGRAM_TIMEOUT diagram_timeout_from diagram_timeout_for DIAGRAM_TOOLS RELATIVE_IMAGE_RE "
                       "select_filter_args chem_filter_args typst_filter_args")
names("pdfmd_flavours.markup", "FLAVOUR_PRESETS FLAVOUR_WORDS MARKUP_KINDS markup_value show_comments_on _FLAVOUR_TOLD UNCLOSED_WORDS "
                               "unclosed_comment_mode flavour_setting flavour_of flavour_default obsidian_source "
                               "markup_kinds markup_filter_args MARKUP_HIGHLIGHT_HEADER MARKUP_LANDSCAPE_HEADER "
                               "MARKUP_HEADERS markup_header_args")
names("pdfmd_tex.plots", "CACHE_HANDSHAKE picture_cache_styles cache_aliases user_tex_trees plot_key_text "
                         "plot_cache_directory prune_plot_directories validate_plot_entries read_plot_requests")
names("pdfmd_install.manage", "translit_report kits_install_directory uninstall_kit uninstall_fonts tessdata_directory "
                              "install_ocr_languages reset_font_caches setup_module")
names("pdfmd_page", "has_geometry frontmatter_margin_geometry_options pagesize_typo_value frontmatter_papersize_value "
                    "typst_papersize_translation paper_kind paper_variables has_monofont")
names("pdfmd_office.route", "OFFICE_REFERENCE_EXTENSIONS OFFICE_OPTION_KEYS effective_metadata office_options "
                            "office_pdfmd_command office_label_data office_reference CHEM_COMMANDS MATH_ONLY_LATEX_RE "
                            "latex_failed latex_dropped office_fallback_wanted")
names("pdfmd_bridge.goals", "OFFICE_INPUT_EXTENSIONS CALIBRE_OPTIONS CALIBRE_CSS CALIBRE_SHARED_FORMATS "
                            "CALIBRE_MATH_PICTURES CALIBRE_MATH_TEXT EBOOK_MATH ebook_filter_args math_pictures_possible "
                            "SOFFICE_ONLY_FORMATS SOFFICE_SHARED_FORMATS soffice_asked_first soffice_goal "
                            "calibre_asked_first calibre_goal start_calibre_job finish_convert_job")
names("pdfmd_output", "PICTURE_ONLY PICTURE_FORMATS ASSEMBLED_FORMAT ASSEMBLED_SUFFIX FORMAT_EXTENSION "
                      "CALIBRE_ONLY_FORMATS EXTENSION_FORMAT output_extension_for rewrite_wanted rewrite_template "
                      "numbered_output default_output_path BOPEN_HELP parse_bopen bopen_indices report_common_folder")
names("pdfmd_filters.lua", "package_lua_names find_lua_filters check_lua_filters trust_lua PDFMD_LUA_WARNED")
names("pdfmd_lookup.find", "announce_lookup CYRILLIC_STRICT CYRILLIC_LOOSE LATIN_EXTRA set_translit _LOOKUP_ANNOUNCED choose_markdown "
                           "find_markdown")
names("pdfmd_unicode.document", "unicode_module managed_index managed_face template_has_variable mathfont_args "
                                "document_font_args font_index strip_code_text unicode_source_text own_script_setup "
                                "fallback_settings mainfont_choice name_candidates has_mainfont has_font_setting "
                                "has_code_spans UNICODE_UNCOVERED UNICODE_CODE_FONTS missing_glyph_warning "
                                "missing_glyph_codes retry_font_note")
names("pdfmd_parts", "PARTS_DIR_ALIASES PARTIAL_METADATA parts_setting REPORT_BUILD split_section_requests "
                     "scaffold_metadata_files LEADING_FRONT_MATTER_RE strip_part_front_matter print_parts DIV_FENCE_RE "
                     "print_headings")
document_font_setting = deferred("pdfmd_unicode.document", "document_font_setting")
fonts_directory = deferred("pdfmd_unicode.document", "fonts_directory")
skip_never = deferred("pdfmd_lookup.find", "skip_never")
lua_filter_file = deferred("pdfmd_filters.lua", "lua_filter_file")
pdfmd_lua_missing = deferred("pdfmd_filters.lua", "pdfmd_lua_missing")
format_from_output = deferred("pdfmd_output", "format_from_output")
office_module = deferred("pdfmd_office.route", "office_module")
fix_typst_margin = deferred("pdfmd_page", "fix_typst_margin")
paper_words = deferred("pdfmd_page", "paper_words")
resolve_raw = deferred("pdfmd_filters", "resolve_raw")
crossref_filter_args = deferred("pdfmd_reader", "crossref_filter_args")
safe_stem = deferred("pdfmd_labels.seed", "safe_stem")
_convert_one = deferred("pdfmd_build", "_convert_one")
run_main = deferred("pdfmd_run", "run_main")
edit_command = deferred("pdfmd_edit.command", "edit_command")
gather_stamp_texts = deferred("pdfmd_edit.command", "gather_stamp_texts")
init_vscode_command = deferred("pdfmd_edit.command", "init_vscode_command")
part_digests = deferred("pdfmd_edit.command", "part_digests")
stamp_scope_matches = deferred("pdfmd_edit.command", "stamp_scope_matches")

# DEFAULT_FONT, MONOFONT_STAND_INS, SERIF_STAND_INS and installed_font_families to preferred_font: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)

DEFAULT_MARGIN = "1in"
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
# v3.31.41 (entry 3ea): how a path is written in a message. `auto`: relative to the working folder (up to PATH_UP `..` steps above
# it), else `~/...` under the home folder, else absolute; `relative`: the same without `~`; `home`: `~/...` under the home
# folder, else absolute; `full`: absolute. --path-style / --path-up, `options: {path-style, path-up}` of the config and of a folder's
# settings (pdfmd --setup). -v/--verbose gives `full` unless --path-style is given.
PATH_STYLES = ("auto", "relative", "home", "full")
PATH_STYLE = "auto"
PATH_UP = 2
# Set from --no-citeproc in main(). A real pdfmd flag rather than a string
# looked for in the passthrough Pandoc options: Pandoc itself has no
# --no-citeproc, so leaving it in that list made Pandoc reject the whole
# command (fixed v3.10.0).
CITEPROC_DISABLED = False


DISPLAY_ALIAS: dict[Path, Path] = {}


def path_style_settings(requested: str | None, requested_up: int | None = None, document: Path | None = None,
                        verbose: bool = False) -> tuple[str, int]:
    """(style, steps up) of this run: --path-style / --path-up, else `options.path-style` / `options.path-up` (the config, then the
    folder settings above ``document``, the nearest winning), else `auto` and 2. ``verbose`` (-v, --debug) makes the style `full`
    unless --path-style was given: the detail asked for is the whole path."""
    options = config_options(document)
    style = requested or ("full" if verbose else str(options.get("path-style") or "auto").strip().casefold())
    if style not in PATH_STYLES:
        raise SystemExit(f"unknown path-style {style!r}. Valid: {', '.join(PATH_STYLES)}")
    up = requested_up if requested_up is not None else options.get("path-up", PATH_UP)
    try:
        up = int(up)
    except (TypeError, ValueError):
        up = -1
    if up < 0:
        raise SystemExit(f"path-up must be a whole number of folders (0 or more), not {up if requested_up is not None else options.get('path-up')!r}")
    return style, up


def display_path(path: Path, up: int | None = None) -> str:
    """Format `path` for a user-facing AUTO/CMD message.

    Relative to the current working directory by default (SHOW_FULL_PATHS
    False, the default -- see --full-paths), which is what a caller
    actually invoking pdfmd from a project directory wants to read; falls
    back to the absolute path when `path` isn't under cwd at all (a system
    temp file, e.g.) since a relative path can't reach it, or when
    SHOW_FULL_PATHS is True (--full-paths, for a copy-pasteable absolute
    path -- e.g. to hand to another tool, or when cwd itself is ambiguous
    in a script's own log). Since v3.31.41 a folder above the working folder is written with `..` (up to PATH_UP steps, or ``up``)
    and a path under the home folder as ``~/...``, per PATH_STYLE.
    """
    if DISPLAY_ALIAS:                             # an ebook's Markdown in a scratch folder is shown as the book (v3.29.1)
        try:
            path = DISPLAY_ALIAS.get(path) or DISPLAY_ALIAS.get(path.resolve()) or path
        except OSError:
            pass
    if SHOW_FULL_PATHS or PATH_STYLE == "full":
        return str(path)
    # The folder is resolved, the file itself is not: a symlink (`metadata/metadata.yaml` pointing at
    # a shared house-style file) is shown where it sits, not where it leads. The working folder is resolved too:
    # on Windows it can be in 8.3 short form (`RUNNER~1`) while the file's resolves to the long one.
    try:
        here = Path.cwd().resolve()
    except OSError:
        here = Path.cwd()
    try:
        located = path.parent.resolve() / path.name
    except OSError:
        return str(path)
    candidates = [located]
    try:
        candidates.append(path.resolve())
    except OSError:
        pass
    if PATH_STYLE != "home":
        for candidate in candidates:
            try:
                return str(candidate.relative_to(here))
            except ValueError:
                pass
        for candidate in candidates:
            try:
                relative = os.path.relpath(candidate, here)
            except ValueError:                        # another drive on Windows
                continue
            ups = 0
            for part in Path(relative).parts:
                if part != "..":
                    break
                ups += 1
            if ups <= (PATH_UP if up is None else up):
                return relative
    if PATH_STYLE != "relative":
        try:
            home = Path.home().resolve()
        except (OSError, RuntimeError):
            home = None
        if home is not None:
            for candidate in candidates:
                try:
                    return os.path.join("~", *candidate.relative_to(home).parts)
                except ValueError:
                    pass
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
    "papersize", "parts", "lookup", "unicode", "officeref", "officestyle", "officelatex", "officeprofile",
    "codewrap", "typstdirect", "htmldirect", "svg", "remoteimages", "pdfimages", "diagrams", "texpackages",
    "smiles", "draftpictures", "remotecsl", "mathfont", "css", "mathjax", "kit", "kpsewhich",
    "priority", "bib",
})
NO_AUTO_ALIASES = {
    "font": frozenset({"mainfont", "monofont", "mathfont"}),
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
# --strip-comments / --keep-comments (None: the document's pdfmd-options decide).
STRIP_COMMENTS_CLI: bool | None = None


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
    for metadata in metadata_files or []:                      # a kit's own folder (its csl and bibliography are found by name),
        folder = KIT_METADATA.get(metadata)                    # a folder layer's and the global metadata's: they do not move the cwd
        if folder is None and (is_folder_metadata(metadata) or is_global_metadata(metadata) or deferred("pdfmd_metadata", "is_parent_metadata")(metadata)):
            folder = metadata.parent
        if folder is not None and folder not in extra and folder != pandoc_cwd:
            extra.append(folder)
    extra += [directory for directory in EMBEDDED_RESOURCE_DIRS if directory not in extra]
    if document_directory == pandoc_cwd and not extra:
        return []
    entries = ([str(document_directory)] if document_directory != pandoc_cwd else []) + ["."]
    return ["--resource-path", os.pathsep.join(entries + [str(d) for d in extra])]


def kit_search_folders(document: Path | None) -> list[str]:
    """The TeX search path entries of the kits chosen for ``document``: each kit's folder (its package, the library it `\\input`s)
    and, `//` recursive, the folders its `carry:` names (a logo found by its bare name). The kit's whole folder is not searched
    recursively: it may hold a repository's worth of data. They come after the default path, so an installed copy is the same file
    or stays where it was."""
    if document is None or yaml is None:
        return []
    found: list[str] = []
    for item in active_kits(document, None, None):
        found.append(str(item.kit.folder))
        found += [f"{item.kit.folder / entry.rstrip('/')}//" for entry in item.kit.carry
                  if (item.kit.folder / entry.rstrip("/")).is_dir()]
    return list(dict.fromkeys(found))


TECTONIC_SEARCH_ENV = "PDFMD_TECTONIC_SEARCH"        # tex_search_env -> run_tex_engine: the folders below, joined with os.pathsep


def tectonic_search_folders(document: Path | None) -> list[str]:
    """The folders of the chosen kits as Tectonic wants them. Tectonic reads no TEXINPUTS: a file is found in its own bundle unless
    `-Z search-path=DIR` names the folder, and that option takes one folder, not a tree. Without it the class a kit ships is never
    loaded: Tectonic builds, and says nothing, with the copy in its bundle. So the kit's folder and every folder under the entries
    that kit_search_folders gives as a tree (`carry:`, the `//` ones) are listed one by one; a hidden folder is left out."""
    folders: list[str] = []
    for entry in kit_search_folders(document):
        tree = entry.endswith("//")
        top = Path(entry[:-2] if tree else entry)
        folders.append(str(top))
        if tree:
            folders += [str(path) for path in sorted(top.rglob("*"))
                        if path.is_dir() and not any(part.startswith(".") for part in path.relative_to(top).parts)]
    return list(dict.fromkeys(folders))


def tex_search_env(document_directory: Path, pandoc_cwd: Path, document: Path | None = None) -> dict[str, str] | None:
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
    kit_dirs = kit_search_folders(document)
    if document_directory == pandoc_cwd and not EMBEDDED_RESOURCE_DIRS and not kit_dirs:
        return None
    env = os.environ.copy()
    if document_directory != pandoc_cwd:
        env["TEXINPUTS"] = f"{document_directory}{os.pathsep}{env.get('TEXINPUTS', '')}"
    if EMBEDDED_RESOURCE_DIRS:
        # (a trailing separator keeps the default search path after these)
        env["BIBINPUTS"] = (os.pathsep.join(str(item) for item in EMBEDDED_RESOURCE_DIRS)
                            + os.pathsep + env.get("BIBINPUTS", ""))
        env["TEXINPUTS"] = (((env.get("TEXINPUTS") or ".").rstrip(os.pathsep)) + os.pathsep
                            + os.pathsep.join(str(item) for item in EMBEDDED_RESOURCE_DIRS) + os.pathsep)
    if kit_dirs:                                              # a kit works from its folder, with no install into the TeX tree
        for name in ("TEXINPUTS", "BIBINPUTS"):
            env[name] = (((env.get(name) or ".").rstrip(os.pathsep)) + os.pathsep + os.pathsep.join(kit_dirs) + os.pathsep)
        env[TECTONIC_SEARCH_ENV] = os.pathsep.join(tectonic_search_folders(document))
    return env


def frontmatter_pdfmd_options(md_path: Path) -> dict:
    """Parse a document's own ``pdfmd-options:`` front-matter block.

    A real YAML parse (not the regex sniffing the rest of this script uses
    for single scalar keys) because this block can be an arbitrarily
    nested mapping -- ``no-auto: [monofont, margin]`` and
    ``no-auto: true`` both have to parse correctly, not just be detected.
    Returns {} if there's no front matter, no ``pdfmd-options`` key, the
    front matter doesn't parse as YAML, or YAML support is unavailable --
    document-level pdfmd-options are optional sugar, not a hard dependency
    of the rest of the script. Also {} for a binary office document
    (OFFICE_INPUT_EXTENSIONS) without even trying to read it as text --
    caught via a real crash (UnicodeDecodeError) the first time an actual
    .docx/.pptx was fed through pdfmd for this round's own office-direct
    feature: effective_no_auto()/resolve_engines() call this
    unconditionally for every input, .tex and now office documents
    included, on the way to either one's own direct (non-Pandoc) branch.
    """
    if yaml is None or md_path.suffix.lower() in sys.modules[__name__].OFFICE_INPUT_EXTENSIONS:
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
    return load_package("pdfmd_args.options").from_mapping(data, md_path)


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
    return no_auto_from_value(value)


def no_auto_from_value(value) -> list[str] | None:
    """A `no-auto` setting in any of its shapes (document, config file): True/"all" -> [] (everything off),
    a kind name, or a list of kinds; None when nothing is switched off."""
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
    (--embed-metadata preamble). The front-matter macros a package expects
    (package_latex_keys) are only emitted when a preamble exists, and one
    embedded there counts as one."""
    kinds = frontmatter_pdfmd_options(md_path).get("embedded")
    return isinstance(kinds, list) and "preamble" in kinds


# -- The automatic kinds are three-state (v3.29.30) ---------------------------------------------------------------------
# Each kind of NO_AUTO_KINDS is `on`, `off` (pdfmd does none of it, and ignores a file the document names for it: what `--no-auto`
# always meant) or `explicit-only` (it looks for nothing, but uses what the document names: a Lua filter, a preamble, a metadata
# file; only the kinds that have a file to name). A layer says it with `no-auto:` (a list: off; true: everything off) and/or
# `auto: {lua: explicit-only, margin: on}` (an `auto` entry wins over `no-auto` in the same layer). The layers, strongest first:
# the command line (`--no-auto`, which only switches off), the document's `pdfmd-options`, the folders' `.pdfmd/config.yaml` (the
# nearest first), the global config; the first layer that names a kind decides it (before 3.29.30 the layers were added up and a
# kind switched off anywhere stayed off). A metadata file's own `no-auto` is still not read: it would have to be read before
# pdfmd knows whether metadata files are read at all. What the layers give is, as ever, a list of kinds that are off, with
# `explicit:KIND` entries for the explicit-only ones (`[]`: everything off, `None`: nothing).
EXPLICIT_PREFIX = "explicit:"
EXPLICIT_KINDS = frozenset({"lua", "preamble", "tex", "metadata", "yaml", "files", "bib"})
AUTO_STATES = {"on": "on", "true": "on", "yes": "on", "off": "off", "false": "off", "no": "off",
               "explicit-only": "explicit", "explicit": "explicit", "named": "explicit"}


def auto_expand(kind: str) -> set[str]:
    return set(NO_AUTO_ALIASES.get(kind, {kind}))


def discovery_disabled(no_auto: list[str] | None, kind: str) -> bool:
    """Whether pdfmd may not LOOK for files of this kind: off (auto_disabled), or explicit-only. What the document names is
    asked of auto_disabled alone."""
    if auto_disabled(no_auto, kind):
        return True
    for item in no_auto or ():
        if item.startswith(EXPLICIT_PREFIX) and kind in auto_expand(item[len(EXPLICIT_PREFIX):]):
            return True
    return False


CODE_KINDS = frozenset({"lua", "preamble"})


def folder_auto_safe(options: dict, where: str) -> dict:
    """A folder's `auto:` without the `on` of a kind that finds code (lua, preamble, and the aliases files and tex that cover them):
    a folder you did not write must not run what you switched off in your config or your document. Off and explicit-only,
    which only tighten, stay."""
    mapping = options.get("auto")
    if not isinstance(mapping, dict):
        return options
    kept = {}
    for kind, value in mapping.items():
        if (AUTO_STATES.get(str(value).strip().casefold()) == "on" and str(kind) in NO_AUTO_KINDS
                and auto_expand(str(kind)) & CODE_KINDS):
            if f"{where}:{kind}" not in FOLDER_WARNED:
                FOLDER_WARNED.add(f"{where}:{kind}")
                print(f"WARN  {where}: auto: {kind}: on cannot be set by a folder (it finds code); ignored", file=sys.stderr)
            continue
        kept[kind] = value
    return {**options, "auto": kept}


def auto_layer(options: dict, where) -> tuple[bool, dict[str, str]]:
    """(whether the layer switches everything off, {kind: "on" | "off" | "explicit"}) as one layer of options says it."""
    everything, states = False, {}
    listed = no_auto_from_value(options.get("no-auto"))
    if listed == []:
        everything = True
    for item in listed or ():
        if item.startswith(EXPLICIT_PREFIX):
            name, state = item[len(EXPLICIT_PREFIX):], "explicit"
        else:
            name, state = item, "off"
        if name not in NO_AUTO_KINDS:
            raise SystemExit(f"{where}: unknown pdfmd-options.no-auto kind(s): {name}. Valid: {', '.join(sorted(NO_AUTO_KINDS))}")
        if state == "explicit" and name not in EXPLICIT_KINDS:
            raise SystemExit(f"{where}: {item}: explicit-only is for {', '.join(sorted(EXPLICIT_KINDS))}")
        for member in auto_expand(name):
            states[member] = state
    mapping = options.get("auto")
    if mapping is not None:
        if not isinstance(mapping, dict):
            raise SystemExit(f"{where}: pdfmd-options.auto must be a mapping of kinds to on, explicit-only or off, not {mapping!r}")
        for kind, value in mapping.items():
            name, state = str(kind), AUTO_STATES.get(str(value).strip().casefold())
            if name not in NO_AUTO_KINDS:
                raise SystemExit(f"{where}: unknown pdfmd-options.auto kind {name}. Valid: {', '.join(sorted(NO_AUTO_KINDS))}")
            if state is None:
                raise SystemExit(f"{where}: pdfmd-options.auto.{name} is {value!r}: on, explicit-only or off")
            if state == "explicit" and name not in EXPLICIT_KINDS:
                raise SystemExit(f"{where}: pdfmd-options.auto.{name}: explicit-only is for {', '.join(sorted(EXPLICIT_KINDS))}: "
                                 f"{name} has no file a document could name")
            for member in auto_expand(name):
                states[member] = state
    return everything, states


AUTO_STRICTNESS = {"on": 0, "explicit": 1, "off": 2}


def auto_states(layers: list[tuple[object, dict]]) -> tuple[dict[str, str], bool]:
    """({kind: state} the layers decide, strongest first, and whether a layer switched everything off): a kind is decided by the
    first layer that names it, and a layer that switches everything off decides every kind no stronger layer named."""
    decided: dict[str, str] = {}
    blanket = False
    for where, options in layers:
        everything, states = auto_layer(options, where)
        if not blanket:
            for kind, state in states.items():
                decided.setdefault(kind, state)
            blanket = everything
    return decided, blanket


def resolve_auto(layers: list[tuple[object, dict]], folders: int = 0) -> list[str] | None:
    """The kinds that are off (and `explicit:KIND` for the explicit-only ones) after the layers, strongest first. ``folders`` is
    how many of the layers after the first two (command line, document) are folders': for what finds code (CODE_KINDS) a folder
    only ever tightens: the state is the strictest of the layers that are not a folder's and of every folder's, unless the command
    line or the document says it."""
    decided, blanket = auto_states(layers)
    if folders:
        strong, strong_blanket = auto_states(layers[:2])
        without, without_blanket = auto_states([*layers[:2], *layers[2 + folders:]])
        for kind in CODE_KINDS:
            if kind in strong or strong_blanket:
                continue
            states = [without.get(kind, "off" if without_blanket else "on")]
            for layer in layers[2:2 + folders]:
                named, everything = auto_states([layer])
                states.append(named.get(kind, "off" if everything else "on"))
            decided[kind] = max(states, key=AUTO_STRICTNESS.get)
    if blanket:
        for kind in NO_AUTO_KINDS - NO_AUTO_ALIASES.keys():
            decided.setdefault(kind, "off")
        if all(state == "off" for state in decided.values()):
            return []
    off = sorted(kind for kind, state in decided.items() if state == "off")
    explicit = sorted(EXPLICIT_PREFIX + kind for kind, state in decided.items() if state == "explicit")
    return [*off, *explicit] or None


def effective_no_auto(md_path: Path, cli_no_auto: list[str] | None, kit_kinds: list[str] | None = None) -> list[str] | None:
    """What is switched off for a document, from the layers described above. The one place this logic lives -- both
    convert_one and main()'s pre-discovery gating (metadata/preamble auto-discovery happens before convert_one is even
    called) need the same answer for the same file. ``kit_kinds`` (v3.32.8) are what the chosen kits' `no-auto:` switch off: a
    layer under the command line, the document and the folders and above the config, where a kit's own metadata sits. Only
    the callers that know the kit pass it (the kit is chosen from these very layers, so the first answer cannot include it)."""
    own = dict(frontmatter_pdfmd_options(md_path))
    if "no-auto" not in own:
        assembled = frontmatter_no_auto(md_path)             # an assembled file keeps its kinds in the comment form of its marker
        if assembled is not None:
            own["no-auto"] = assembled or True
    layers: list[tuple[object, dict]] = []
    if cli_no_auto is not None:
        layers.append((md_path, {"no-auto": cli_no_auto or True}))
    layers.append((md_path, own))
    if cli_no_auto is None:
        layers.insert(0, (md_path, {}))                  # the command line's place is always the first
    above = [(folder, folder_auto_safe(options, folder)) for folder, options in folder_layers(md_path)]
    layers.extend(above)
    if kit_kinds:
        layers.append(("kit", {"no-auto": list(kit_kinds)}))
    layers.append(("config", config_options()))
    return resolve_auto(layers, len(above))


def kit_no_auto_kinds(md_path: Path, metadata_files: list[Path] | None, no_auto: list[str] | None) -> list[str]:
    """The pdfmd defaults the chosen kits switch off with `no-auto:` (v3.32.8), for effective_no_auto's ``kit_kinds``."""
    kinds: list[str] = []
    for item in active_kits(md_path, metadata_files, no_auto):
        for kind in item.kit.no_auto:
            if kind not in kinds:
                kinds.append(kind)
    if kinds and VERBOSE_OUTPUT:
        print(f"AUTO KIT  switches off {', '.join(kinds)} (no-auto in the kit)")
    return kinds


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
TABLE_WIDTH_LUA_FILTER = "table_width"   # pdfmd_lua/table_width.lua

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
CSV_TABLE_LUA_FILTER = "csv_table"   # pdfmd_lua/csv_table.lua


def width_filter_args(width_filter: Path) -> list[str]:
    """``--lua-filter`` for the table-width filter, with the global column settings of the config or `--setup` handed
    to it (`column-widths`, `column-word-floor`, `column-count-raw-tex`, and the numbers `column-outlier`,
    `column-outlier-rows`, `column-outlier-length`, `column-word-floor-limit`); a document's own `pdfmd-options` reaches
    it through the metadata and wins. `table-widths` and `table-word-floor` are the older names, still read."""
    args = ["--lua-filter", str(width_filter)]
    options = config_options()
    words = (("column-widths", "table-widths", ("auto", "keep", "force")),
             ("column-word-floor", "table-word-floor", ("on", "off", "true", "false")),
             ("column-count-raw-tex", None, ("on", "off", "true", "false")))
    for key, older, allowed in words:
        value = options.get(key)
        if value is None and older:
            value = options.get(older)
        if isinstance(value, bool):
            value = "on" if value else "off"
        if isinstance(value, str) and value.strip().casefold() in allowed:
            args += ["-M", f"pdfmd-{key}={value.strip().casefold()}"]
    for key in ("column-outlier", "column-outlier-rows", "column-outlier-length", "column-word-floor-limit"):
        number = options.get(key)
        if isinstance(number, str) and number.strip().casefold() in ("off", "false"):
            number = 0
        elif isinstance(number, str) and number.strip().replace(".", "", 1).isdigit():
            number = float(number) if "." in number else int(number)
        if isinstance(number, (int, float)) and not isinstance(number, bool) and number >= 0:
            args += ["-M", f"pdfmd-{key}={number}"]
    return args


CODE_CLI: dict = {}                       # --line-numbers and friends, filled in by main()


def hoist_code_header(cmd: list[str]) -> None:
    """Put the code-wrapping header (code_wrap.tex) before every other --include-in-header of ``cmd``. fvextra loads lineno,
    which patches the display-math environments; a class or package that patches them too (nulabreport's preamble) must
    come after it to patch on top, not before it to be patched over (\\begin{linenomath} ended by \\end{equation*})."""
    positions = [index for index, item in enumerate(cmd[:-1]) if item == "--include-in-header"]
    mine = [index for index in positions if cmd[index + 1].endswith("code_wrap.tex")]
    if not mine or mine[0] == positions[0]:
        return
    pair = cmd[mine[0]:mine[0] + 2]
    del cmd[mine[0]:mine[0] + 2]
    cmd[positions[0]:positions[0]] = pair


def header_includes_latex(value) -> str | None:
    """A `header-includes:` value as the LaTeX it holds: list items one per line, through raw_latex_only."""
    items = value if isinstance(value, list) else [value]
    lines = [raw_latex_only(str(item)).strip() for item in items if item is not None]
    return "\n".join(line for line in lines if line).strip() or None


def pandoc_header_includes(sources: list[Path], metadata_files: list[Path]) -> tuple[str, str] | None:
    """The `header-includes` Pandoc keeps when the command line has no --include-in-header, as (LaTeX, where):
    "document" for the last source that has its own (they beat every metadata file), else "metadata" for the last
    metadata file in Pandoc's order that has them (checked on Pandoc 3.12 and 3.1.3). None when nothing has any."""
    for source in reversed(sources):
        text = document_header_includes(read_text_best_effort(Path(source)))
        if text:
            return text, "document"
    for path in reversed(pandoc_metadata_order(metadata_files)):
        data = metadata_file_yaml(path) or front_matter_dict(read_text_best_effort(path))
        if "header-includes" in data:
            text = header_includes_latex(data["header-includes"])
            return (text, "metadata") if text else None
    return None


def keep_header_includes(cmd: list[str], sources: list[Path], metadata_files: list[Path], pandoc_options: list[str],
                         header_file: Path | None = None) -> None:
    """The finished command's header files: a chosen kit's preamble goes in first (it is a header file, so the document's own
    `header-includes` need giving back too), then `_keep_header_includes`, then what the kit and the user's own LaTeX say
    twice is settled (kit_header_resolve)."""
    document = sources[0] if sources else None
    inserted = kit_header_insert(cmd, document, metadata_files)
    _keep_header_includes(cmd, sources, metadata_files, pandoc_options, header_file)
    if inserted:
        kit_header_resolve(cmd, document, metadata_files, pandoc_options)


def _keep_header_includes(cmd: list[str], sources: list[Path], metadata_files: list[Path], pandoc_options: list[str],
                          header_file: Path | None = None) -> None:
    """Give back the `header-includes` pdfmd's own --include-in-header files took away (v3.27.18). Pandoc puts those
    files and `header-includes:` in one template variable and the command line wins, so the code-wrapping header of a
    document with code, graphicx for a raw \\includegraphics, the fonts header, a preamble.tex or the packages header
    each dropped the document's own `header-includes` or, without them, a metadata file's (a house package loaded
    there: nulabreport's prelab-metadata.yaml). Run last, on the finished command: when pdfmd added a header file and
    the caller none, what Pandoc would have kept goes back in, as a header file of its own. A metadata file's go where
    a shared preamble goes, before the other headers (after code_wrap.tex, which must come first); the document's own
    last but for the packages header, which must see them (document_header_file has them already when it is there).
    An --include-in-header or an `-M header-includes` of the caller's own replaces them, as in Pandoc."""
    positions = [index for index, item in enumerate(cmd[:-1]) if item == "--include-in-header"]
    if not positions or has_header_include_option(pandoc_options) \
            or any("header-includes" in option for option in pandoc_options):
        return
    kept = pandoc_header_includes(sources, metadata_files)
    if kept is None or (kept[1] == "document" and header_file is not None):
        return
    text, where = kept
    path = cache_root() / "tex" / f"header-includes-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"% pdfmd: the {where} header-includes the header files below would drop\n{text}\n",
                            encoding="utf-8")
    except OSError:
        return
    packages = cache_root() / "tex"
    if where == "metadata":
        at = next((index for index in positions if not cmd[index + 1].endswith("code_wrap.tex")
                   and not Path(cmd[index + 1]).name.startswith(KIT_HEADER_PREFIX)), len(cmd))
    else:
        at = next((index for index in positions if Path(cmd[index + 1]).parent == packages
                   and Path(cmd[index + 1]).name.startswith("packages-")), len(cmd))
    cmd[at:at] = ["--include-in-header", str(path)]


HEADER_FILTER_OPTIONS = ("--lua-filter", "--filter", "-L", "--citeproc", "-C")      # where the first filter runs


def build_is_latex(cmd: list[str]) -> bool:
    """Whether the Pandoc command writes LaTeX: a LaTeX PDF engine (ConTeXt has its own template), or `-t latex` / `beamer`."""
    for index, item in enumerate(cmd):
        if item.startswith("--pdf-engine="):
            return item.split("=", 1)[1] in LATEX_ENGINES - {"context"}
        target = (cmd[index + 1] if item in ("-t", "--to", "-w", "--write") and index + 1 < len(cmd)
                  else item.split("=", 1)[1] if item.startswith(("--to=", "--write=")) else None)
        if target is not None:
            return target.split("+", 1)[0].split("-", 1)[0] in ("latex", "beamer")
    return False


def pandoc_filter_paths(cmd: list[str]) -> list[str]:
    """The files of the Lua and JSON filters of a Pandoc command, in order."""
    found = []
    for index, item in enumerate(cmd):
        if item in ("--lua-filter", "--filter", "-L") and index + 1 < len(cmd):
            found.append(cmd[index + 1])
        elif item.startswith(("--lua-filter=", "--filter=")):
            found.append(item.split("=", 1)[1])
    return found


def headers_as_metadata(cmd: list[str]) -> list[str]:
    """``cmd`` with its --include-in-header files given to Pandoc as `header-includes` instead (v3.32.30), or ``cmd`` itself.
    Pandoc puts the files and `header-includes` in one template variable and the files win, so a LaTeX build with any
    header file of pdfmd's lost what a Lua filter had put into `header-includes`: a kit's front-matter commands
    (apa7's \\authorsnames made \\maketitle stop in a partial build, which passes the labels of the whole document as
    header files; the same would have happened to a document with code). Only for a LaTeX build that has a filter of
    somebody else's (a kit's, the document's own): header_snap.lua records `header-includes` before the filters,
    header_merge.lua, last, makes it the files (-M pdfmd-header-file-N=PATH, in order) plus whatever the filters added."""
    positions = header_argument_positions(cmd)
    if not positions or not build_is_latex(cmd):
        return cmd
    try:
        import pdfmd_lua
        snap, merge = pdfmd_lua.path("header_snap"), pdfmd_lua.path("header_merge")
    except ImportError:
        return cmd
    if snap is None or merge is None:
        return cmd
    own = pdfmd_lua.FILTERS.resolve()
    foreign = any(Path(name).resolve().parent != own for name in pandoc_filter_paths(cmd))
    if not foreign:
        return cmd
    files: list[str] = []
    drop: set[int] = set()
    for index, equals in positions:
        files.append(cmd[index].split("=", 1)[1] if equals else cmd[index])
        drop.update({index} if equals else {index - 1, index})
    rest = [item for index, item in enumerate(cmd) if index not in drop]
    first = next((index for index, item in enumerate(rest)
                  if item in HEADER_FILTER_OPTIONS or item.startswith(("--lua-filter=", "--filter="))), len(rest))
    result = [*rest[:first], "--lua-filter", str(snap), *rest[first:]]
    for number, name in enumerate(files, 1):
        result += ["-M", f"pdfmd-header-file-{number}={name}"]
    return [*result, "--lua-filter", str(merge)]


@contextmanager
def csv_table_filter() -> Iterator[Path]:
    """pdfmd_lua/csv_table.lua, for --lua-filter."""
    with lua_filter_file(CSV_TABLE_LUA_FILTER, "pdfmd-csvtable-") as path:
        yield path


# `::: {.csv ...}`, or the bare `::: csv` for inline data (`file=` and `align=` need the braces; `::: csvfile` and
# `::: csv-x` are other classes)
CSV_DIV_RE = re.compile(r"""\{(?:[^}"\n]|"(?:[^"\\\n]|\\.)*")*\.csv\b|^[ \t]*:{3,}[ \t]*csv[ \t]*$""", re.MULTILINE)


def contains_csv_table(md_path: Path) -> bool:
    """Detect a `.csv`-classed fenced Div (see CSV_TABLE_LUA_FILTER)."""
    text = EMBED_BLOCK_RE.sub("", md_path.read_text(encoding="utf-8-sig"))
    return bool(CSV_DIV_RE.search(text))


# The cap of a `.csv` table, for every table of a document (v3.27.2): --csv-rows / --csv-cols (reaching -j workers as
# PDFMD_CSV_ROWS / PDFMD_CSV_COLS, as --strict does), else `pdfmd-options: {csv: {rows, cols, header, reader}}` (the
# document, its metadata files, the config: field by field), else 10 rows x 7 columns, a header row and Pandoc's
# Markdown in the cells. A div's own rows= / cols= / header= / reader= still win for that one table.
CSV_DEFAULTS = {"rows": 10, "cols": 7, "header": True, "reader": "markdown", "delimiter": "auto", "cut": "ends", "note": "short"}
# CSV_CUTS: lib/pdfmd_tables/command.py (v3.33.24)
CSV_ENV = {"rows": "PDFMD_CSV_ROWS", "cols": "PDFMD_CSV_COLS"}
# The note under a table that was cut (v3.30.22): `short` states the fact only ("showing the first 7 and the last 3 of 11 rows", only
# for what was cut), `full` adds the advice that used to stand in every PDF, `off` leaves it out (the `...` row still marks the cut).
# The advice is in the WARN on stderr, once per table, whatever the note says. --csv-note (PDFMD_CSV_NOTE for -j workers), else
# `pdfmd-options: {csv: {note: off}}`, else short; a div's own note= wins for that table.
CSV_NOTES = ("short", "off", "full")
CSV_NOTE_ENV = "PDFMD_CSV_NOTE"


def csv_note_mode(value) -> str | None:
    """A note mode from a command line, an option or a div attribute: short, off or full (YAML reads a bare `off` as False and
    `on` as True, so those count too); None when it is none of them."""
    if value is True:
        return "short"
    if value is False:
        return "off"
    text = str(value).strip().casefold()
    text = {"on": "short", "true": "short", "false": "off", "no": "off", "yes": "short", "none": "off"}.get(text, text)
    return text if text in CSV_NOTES else None


# csv_note_argument: lib/pdfmd_args (v3.33.40)


# csv_cut_advice: lib/pdfmd_native (v3.33.39)


def csv_count(value) -> int | str | None:
    """A rows/cols cap: a positive whole number or "all"; None when it is neither."""
    text = str(value).strip().casefold()
    if text == "all":
        return "all"
    return int(text) if text.isdigit() and int(text) > 0 else None


# csv_count_argument: lib/pdfmd_args (v3.33.40)


# `csv: off` switches the `.csv` div off for a document, the way `calc: off` does the calculator: the Lua filter is not
# added and the div stays as written (a plain div with its text), with no WARN. `pdfmd-options: {csv: off}` is the short form of
# `{csv: {enabled: false}}`, and a mapping (`csv: {rows: 30}`) leaves the tables on. --csv / --no-csv for a run (reaching -j
# workers as PDFMD_CSV); the command line wins over the options.
CSV_ENABLED_ENV = "PDFMD_CSV"


def csv_enabled_option(md_path: Path | None, metadata_files: list[Path] = ()):
    """`pdfmd-options.csv.enabled`; `csv: off` alone means `enabled: off`. None when nothing says."""
    value = first_pdfmd_option(md_path, list(metadata_files), "csv") if md_path is not None else None
    if isinstance(value, dict):
        return value.get("enabled")
    return value


def csv_is_off(md_path: Path | None, metadata_files: list[Path] = ()) -> bool:
    value = os.environ.get(CSV_ENABLED_ENV)
    if value is None:
        value = csv_enabled_option(md_path, metadata_files)
    if value is None:
        return False
    flag = option_flag(value)
    if flag is None:
        where = display_path(md_path) if md_path is not None else "csv"
        raise SystemExit(f"{where}: pdfmd-options.csv.enabled must be true or false, not {value!r}")
    return not flag


# csv_defaults: lib/pdfmd_tables/command.py (v3.33.24)


# `tablekeep` for a Lua filter (v3.30.2): nulabreport.lua keeps a Markdown table of up to that many body rows on one page.
# --table-keep N (reaching -j workers as PDFMD_TABLE_KEEP), else `pdfmd-options: {table-keep: N}` (the document, its
# metadata files, the config: first one wins), else nothing, and the metadata's own `tablekeep:` or the filter's default
# stands. N reaches Pandoc as -M, which wins over a metadata file; 0 means "let every table break".
TABLE_KEEP_ENV = "PDFMD_TABLE_KEEP"


def table_keep_count(value) -> int | None:
    """A table-keep row count: a whole number, 0 included; None when it is not one."""
    text = str(value).strip()
    return int(text) if text.isdigit() else None


# table_keep_argument: lib/pdfmd_args (v3.33.40)


# table_keep_metadata: lib/pdfmd_tables/command.py (v3.33.24)


# spreadsheet_args and csv_table_filter_args: lib/pdfmd_tables/command.py (v3.33.24)


# --raw / --no-raw / --raw-for FAMILY=SYNTAXES (filled in by main()); `pdfmd-options.raw` is the document's way.
RAW_CLI: dict = {"all": False, "off": False, "for": []}


PAGEBREAK_CLI: dict = {"kinds": None, "off": False}


# Universal markup (v3.29.13, off unless asked, a kind at a time): spellings Markdown dialects share but Pandoc does not know,
# carried into every writer by pdfmd_lua/markup.lua. `pdfmd-options.markup` (document, metadata files, config: true / all, false,
# or a list of kinds), `--markup [KIND ...]` (bare: all) and `--no-markup` for a run.
MARKUP_CLI: dict = {"kinds": None, "off": False}


SHOW_COMMENTS_CLI: dict = {"on": None}


# The flavour of a Markdown file (v3.32.20, entry 3ee; one setting with `reader:` since v3.32.22): `pdfmd-options.flavour` (also spelt
# `flavor` or `reader`; document, metadata files, folders, config) or `--flavour`. A preset word (`pdfmd_flavours.PRESETS`: obsidian,
# pdfmd, pandoc, gfm, commonmark) names a row of reading choices; `auto` (the default) is `obsidian` inside an Obsidian vault, a
# folder with `.obsidian/` above the document, and `pdfmd` elsewhere. Any other value is a Pandoc reader spec (`markdown`,
# `gfm+smart`), which is `--from` for that document with the flavour left on `auto`.
try:
    import pdfmd_flavours  # noqa: F401 -- preserve the pre-move start-up module set
except ImportError:
    pass
FLAVOUR_CLI: dict = {"name": None}
UNCLOSED_CLI: dict = {"mode": None}


# `vault_app_setting`, `single_newline_mode`, `vault_root`, `embed_settings`, `find_embedded_image`, `embed_source` and
# `embed_filter_args` (with the embed and newline word lists and the two folder caches) live in `pdfmd_obsidian.vault`
# (v3.33.12); the stand-ins are in the binding block above.


# Table captions typed by hand (v3.31.46, entry 3dy): `**Table 1: Results**` next to a table becomes the table's caption.
# pdfmd-options: table-captions: note (the default: nothing changes, one NOTE says how many lines would have been captions),
# on, off; table-caption-label: strip (default) | keep; table-caption-words: extra label words (the dictionary of
# pdfmd_tables/captions.py follows `lang:`); table-caption-need-label: on (default) | off (any bold line is a caption);
# table-caption-colon-words: a number, 0 (default) off: a gfm `: Results` of at most
# that many words is a caption too.
TABLE_CAPTION_MODES = ("note", "on", "off")
TABLE_CAPTION_LABELS = ("strip", "keep")
TABLE_CAPTION_NEED = ("on", "off")


def table_caption_settings(md_path: Path, metadata_files: list[Path]) -> dict:
    """The table-caption options as they stand (documented above), checked: a word that is not one of the choices stops the build."""
    def switch(value, name, choices, default):
        if value is None:
            return default
        word = {True: "on", False: "off"}.get(value, str(value).strip().casefold())
        if word not in choices:
            raise SystemExit(f"pdfmd-options {name}: {value!r} is not one of {', '.join(choices)}")
        return word
    mode = switch(first_pdfmd_option(md_path, metadata_files, "table-captions"), "table-captions", TABLE_CAPTION_MODES, "note")
    label = switch(first_pdfmd_option(md_path, metadata_files, "table-caption-label"), "table-caption-label", TABLE_CAPTION_LABELS, "strip")
    need = switch(first_pdfmd_option(md_path, metadata_files, "table-caption-need-label"), "table-caption-need-label", TABLE_CAPTION_NEED, "on")
    colon = first_pdfmd_option(md_path, metadata_files, "table-caption-colon-words")
    try:
        colon_words = 0 if colon in (None, False) else int(colon)
    except (TypeError, ValueError):
        colon_words = -1
    if colon_words < 0:
        raise SystemExit(f"pdfmd-options table-caption-colon-words: {colon!r} must be a whole number of words (0 is off)")
    extra = first_pdfmd_option(md_path, metadata_files, "table-caption-words")
    extra = [part for part in re.split(r"[,;]", extra)] if isinstance(extra, str) else list(extra or [])
    return {"mode": mode, "label": label, "need": need, "colon": colon_words, "extra": [str(word) for word in extra]}


def table_caption_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter table_caption.lua`` with its settings (`-M pdfmd-table-captions=...`), for a document that has a line
    which could be a caption; nothing for `off`, and nothing for a document without such a line (the filter would only look)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []
    settings = table_caption_settings(files[0], metadata_files)
    if settings["mode"] == "off":
        return []
    try:
        from pdfmd_tables.captions import label_words
    except ImportError:
        return []
    words = label_words(document_font_setting("lang", files, metadata_files, []), settings["extra"])
    start = r"^[ \t]*\*\*[ \t]*(?:" + "|".join(re.escape(word) for word in words) + ")"
    if settings["need"] == "off":
        start = r"^[ \t]*\*\*\S"
    if settings["colon"] > 0:
        start = "(?:" + start + r")|(?:^: \S)"
    pattern = re.compile(start, re.MULTILINE | re.IGNORECASE)
    if not any(pattern.search(EMBED_BLOCK_RE.sub("", read_text_best_effort(file))) for file in files):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("table_caption")
    if shipped is None:
        return []
    return ["-M", "pdfmd-table-captions=" + settings["mode"], "-M", "pdfmd-table-caption-label=" + settings["label"],
            "-M", "pdfmd-table-caption-need-label=" + settings["need"],
            "-M", f"pdfmd-table-caption-colon-words={settings['colon']}", "-M", "pdfmd-table-caption-words=" + ",".join(words),
            "--lua-filter", str(shipped)]


LINEBREAK_CLI: dict = {"kinds": None, "off": False}


# Cell tags of pipe tables: one cell's alignment (v3.31.52, entry 3el) and merged cells (v3.32.31, entry 3fa). A cell may carry a tag
# (`<c>`, `&mc&`, `&<<&`, `<merge-up, top>`, a bare `<<` or `^^`) anywhere in it; lib/pdfmd_tables/celltags.py (a pre-pass on a temporary
# copy) reads every spelling and writes one canonical raw tag, and pdfmd_lua/cellalign.lua makes the spans and the alignment from it (the
# filter goes in after the table-width filter). pdfmd-options: cell-align: on (the default) | off, which switches every cell tag off;
# table-tag-brackets: which spellings are read (a list of angle, amp, brace, guillemet; default angle, amp).
CELL_TAG_KINDS = ("angle", "amp", "brace", "guillemet")
CELL_TAG_DEFAULT_KINDS = ("angle", "amp")


def cell_align_on(md_path: Path, metadata_files: list[Path]) -> bool:
    """The `cell-align` option: on unless the document, a metadata file or the config says off (anything else stops the build)."""
    value = first_pdfmd_option(md_path, metadata_files, "cell-align")
    if value is None:
        return True
    word = {True: "on", False: "off"}.get(value, str(value).strip().casefold())
    if word not in ("on", "off"):
        raise SystemExit(f"pdfmd-options cell-align: {value!r} is not one of on, off")
    return word == "on"


def cell_tag_kinds(md_path: Path, metadata_files: list[Path]) -> tuple[str, ...]:
    """The `table-tag-brackets` option: the spellings of a cell tag that are read (a list, or words split by commas or spaces)."""
    value = first_pdfmd_option(md_path, metadata_files, "table-tag-brackets")
    if value is None:
        return CELL_TAG_DEFAULT_KINDS
    words = [str(item) for item in value] if isinstance(value, list) else re.split(r"[,\s]+", str(value))
    kinds = tuple(dict.fromkeys(word.strip().casefold() for word in words if word.strip()))
    for kind in kinds:
        if kind not in CELL_TAG_KINDS:
            raise SystemExit(f"pdfmd-options table-tag-brackets: {kind!r} is not one of {', '.join(CELL_TAG_KINDS)}")
    return kinds


CELL_ALIGN_WORDS = {"l": "l", "left": "l", "r": "r", "right": "r", "c": "c", "center": "c", "centre": "c"}
CELL_VALIGN_WORDS = {"t": "t", "top": "t", "m": "m", "middle": "m", "b": "b", "bottom": "b"}


def table_defaults(md_path: Path, metadata_files: list[Path]) -> dict[str, str]:
    """The `table-align` (left, right, centre) and `table-valign` (top, middle, bottom) options: the alignment every cell has when
    nothing more specific says (its tag, row, column or the table's own `{align=}`); {} for neither. A word that is not one of them
    stops the build. Either one set makes every table of the document go through cellalign.lua (a vertical one through tabularray)."""
    found: dict[str, str] = {}
    for option, words, key in (("table-align", CELL_ALIGN_WORDS, "h"), ("table-valign", CELL_VALIGN_WORDS, "v")):
        value = first_pdfmd_option(md_path, metadata_files, option)
        if value in (None, "", False):
            continue
        word = str(value).strip().casefold()
        if word not in words:
            raise SystemExit(f"pdfmd-options {option}: {value!r} is not one of {', '.join(sorted(set(words)))}")
        found[key] = words[word]
    return found


def cell_tags_text(text: str, md_path: Path, metadata_files: list[Path], label: str) -> str:
    """``text`` with the cell tags of its pipe tables written as canonical tags (a WARN for each thing that could not be done)."""
    if "|" not in text or not cell_align_on(md_path, list(metadata_files)):
        return text
    try:
        from pdfmd_tables.celltags import normalise
    except ImportError:
        return text
    result = normalise(text, cell_tag_kinds(md_path, list(metadata_files)))
    for note in result.notes:
        print(f"WARN  cell-tags: {label}, line {note.line}: {note.message}")
    return result.text


@functools.lru_cache(maxsize=1)
def tabularray_available() -> bool:
    """Whether LaTeX has the `tabularray` package, which draws a cell's vertical alignment (found with kpsewhich)."""
    kpsewhich = shutil.which("kpsewhich")
    if not kpsewhich:
        return False
    try:
        found = subprocess.run([kpsewhich, "tabularray.sty"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(found.strip())


def cell_tag_counts(sources: Path | list[Path], metadata_files: list[Path]) -> tuple[int, int]:
    """(cells with a tag or tables with settings, those LaTeX draws only with tabularray: a vertical alignment, a width, a height) in the
    pipe tables of the sources; (0, 0) when `cell-align` is off."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or not cell_align_on(files[0], metadata_files):
        return 0, 0
    try:
        from pdfmd_tables.celltags import normalise
    except ImportError:
        return 0, 0
    kinds = cell_tag_kinds(files[0], metadata_files)
    found = [normalise(EMBED_BLOCK_RE.sub("", read_text_best_effort(file)), kinds) for file in files]
    return sum(result.cells for result in found), sum(result.tblr for result in found)


TABLAY_NOTED: set[str] = set()


def cellalign_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter cellalign.lua`` for a document with a cell tag in a pipe table, unless `cell-align` is off. Vertical
    alignment is drawn in LaTeX with tabularray; without it the filter is told (`-M pdfmd-tblr=off`) and says so once."""
    files = sources if isinstance(sources, list) else [sources]
    tagged, vertical = cell_tag_counts(files, metadata_files)
    defaults = table_defaults(files[0], metadata_files) if files and cell_align_on(files[0], metadata_files) else {}
    if not tagged and not defaults:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("cellalign")
    if shipped is None:
        return []
    arguments = ["--lua-filter", str(shipped)]
    for key, option in (("h", "pdfmd-table-align"), ("v", "pdfmd-table-valign")):
        if key in defaults:
            arguments = ["-M", f"{option}={defaults[key]}"] + arguments
    if (vertical or "v" in defaults) and not tabularray_available():
        arguments = ["-M", "pdfmd-tblr=off"] + arguments
        label = display_path(files[0])
        if label not in TABLAY_NOTED:
            TABLAY_NOTED.add(label)
            print(f"NOTE  cell-tags: {label}: a table has a vertical alignment, a width or a height, which LaTeX draws with its "
                  "`tabularray` package; it was not found (kpsewhich), so LaTeX ignores these except percentage widths. HTML is unaffected.")
    return arguments


def tblr_header_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """`--include-in-header` with tabularray for a LaTeX build of a document with a vertical alignment in a cell, or [] (a filter's
    `header-includes` is dropped by every header file of pdfmd's, so the package goes in a file of its own)."""
    files = sources if isinstance(sources, list) else [sources]
    _, vertical = cell_tag_counts(files, metadata_files)
    if files and cell_align_on(files[0], metadata_files) and "v" in table_defaults(files[0], metadata_files):
        vertical += 1
    if not vertical or not tabularray_available():
        return []
    text = ("% pdfmd: vertical alignment of table cells (cell tags, entry 3fa)\n\\usepackage{tabularray}\n\\UseTblrLibrary{booktabs}\n"
            "% a long table repeats its header on every page, as Pandoc's own tables do, without tabularray's continuation texts\n"
            "\\DeclareTblrTemplate{contfoot-text}{pdfmd}{}\n\\SetTblrTemplate{contfoot-text}{pdfmd}\n"
            "\\DeclareTblrTemplate{conthead-text}{pdfmd}{}\n\\SetTblrTemplate{conthead-text}{pdfmd}\n")
    header = cache_root() / "tex" / f"packages-tblr-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not header.is_file():
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(header)]


# An inline calculator (v3.30.6): inline code followed at once by a bare `{=}` is replaced by its value, `2026 - 2006`{=} -> 20,
# evaluated by pdfmd_lua/calc.lua's own small parser (nothing is run). `C = n / V = {ans:4sf}` inside the span prints the
# text with the value put in and keeps C; a `::: calc` div does that for its lines without the backticks. The filter goes in only
# for a document that has such a span or div. The settings live under `pdfmd-options: {calc: {enabled, digits, round, subs, noindent, space, align, constants, export}}` (the
# document, its metadata files, the config; `calc: off` alone is the short form of `enabled: false`), and on the command line
# --calc / --no-calc, --calc-digits 4sf, --calc-round away, --calc-subs, --calc-typeset, --calc-noindent, --calc-space, --calc-align, --calc-constants, --calc-export (reaching -j workers as PDFMD_CALC,
# PDFMD_CALC_DIGITS, PDFMD_CALC_ROUND, PDFMD_CALC_SUBS, PDFMD_CALC_TYPESET, PDFMD_CALC_NOINDENT, PDFMD_CALC_SPACE, PDFMD_CALC_ALIGN, PDFMD_CALC_CONSTANTS, PDFMD_CALC_EXPORT). digits: how many figures a value shows (4sf: four significant figures, 2dp: two decimal places); unset
# prints as R does. round: how round() settles an exact half, to even (R and Python, the default) or away from zero.
CALC_DIV_RE = re.compile(r"^[ \t]*:{3,}[ \t]*(?:calc\b|\{[^}\n]*\.calc\b)", re.MULTILINE)
CALC_SPAN_RE = re.compile(r"`\{=(?:\d+[a-z]{2}|calc)?\}|^[ \t]*:{3,}[ \t]*(?:calc\b|\{[^}\n]*\.calc\b)"
                         r"|^[ \t]*(?:`{3,}|~{3,})[ \t]*\{=(?:calc)?\}[ \t]*$", re.MULTILINE)
CALC_ENV = "PDFMD_CALC"
CALC_DIGITS_ENV = "PDFMD_CALC_DIGITS"
CALC_ROUND_ENV = "PDFMD_CALC_ROUND"
CALC_SUBS_ENV = "PDFMD_CALC_SUBS"
CALC_TYPESET_ENV = "PDFMD_CALC_TYPESET"
CALC_TYPESET_STYLE_ENVS = {"upright": "PDFMD_CALC_TYPESET_UPRIGHT", "italic": "PDFMD_CALC_TYPESET_ITALIC"}
CALC_TYPESET_PIECE_RE = re.compile(r"^[A-Za-z]+$")
CALC_NOINDENT_ENV = "PDFMD_CALC_NOINDENT"
CALC_SPACE_ENV = "PDFMD_CALC_SPACE"
CALC_ALIGN_ENV = "PDFMD_CALC_ALIGN"
CALC_SPACE_DEFAULT = "0.75em"
CALC_SPACE_RE = re.compile(r"^(?:\d+\.?\d*|\.\d+)(?:pt|mm|cm|in|em)$")
CALC_ALIGNS = ("left", "center")
CALC_TYPESETS = ("off", "inline", "display")
CALC_CONSTANTS_ENV = "PDFMD_CALC_CONSTANTS"
CALC_EXPORT_ENV = "PDFMD_CALC_EXPORT"
CALC_DUMP: Path | None = None               # where this build's calc.lua writes its names, when the document exports them (set around one build)
CALC_SEED: Path | None = None              # the names of the parts before a part built alone (build_calc_seed; set around one build)
CALC_BELOW: Path | None = None             # the first definitions in the parts after it (3.31.44; the same)
CALC_ROUNDS = ("even", "away")
CALC_DIGITS_RE = re.compile(r"(\d+)\s*(sf|dp)", re.IGNORECASE)


def calc_option(md_path: Path, metadata_files: list[Path], field: str):
    """`pdfmd-options.calc.<field>`; `calc: off` alone means `enabled: off`."""
    value = first_pdfmd_option(md_path, list(metadata_files), "calc")
    if isinstance(value, dict):
        return value.get(field)
    return value if field == "enabled" else None


def calc_is_off(md_path: Path, metadata_files: list[Path]) -> bool:
    value = os.environ.get(CALC_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "enabled")
    if value is None:
        return False
    flag = option_flag(value)
    if flag is None:
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.enabled must be true or false, not {value!r}")
    return not flag


def calc_round_mode(md_path: Path, metadata_files: list[Path]) -> str:
    value = os.environ.get(CALC_ROUND_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "round")
    mode = str(value).strip().lower() if value is not None else "even"
    if mode not in CALC_ROUNDS:
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.round must be even or away, not {value!r}")
    return mode


def calc_subs_on(md_path: Path, metadata_files: list[Path]) -> bool:
    """`calc: {subs: true}`: every {ans} is preceded by the expression with its names replaced by their values."""
    value = os.environ.get(CALC_SUBS_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "subs")
    if value is None:
        return False
    flag = option_flag(value)
    if flag is None:
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.subs must be true or false, not {value!r}")
    return flag


def calc_typeset_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """`calc: {typeset: ...}`: "off" (the default; the calculator prints the plain text it was written in), "inline" (true; each
    calculation a line of inline maths, its label and unit text) or "display" (a centred display formula per `::: calc` line,
    the label and the unit inside it as \\text)."""
    value = os.environ.get(CALC_TYPESET_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "typeset")
    if value is None:
        return "off"
    word = str(value).strip().lower()
    if word in CALC_TYPESETS:
        return word
    flag = option_flag(value)
    if flag is None:
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.typeset must be true, false or display, not {value!r}")
    return "inline" if flag else "off"


def calc_typeset_styles(md_path: Path, metadata_files: list[Path]) -> dict[str, list[str]]:
    """`calc: {typeset-upright: [V, k], typeset-italic: [el, DNA]}`: pieces of a name that a typeset calculation sets upright or italic
    against the default (a one-letter piece italic, a longer one upright). A piece is the letters of a name's base or one word after an
    underscore (`V_el` has V and el); a list or a comma/space separated string. Returns {"upright": [...], "italic": [...]}."""
    found: dict[str, list[str]] = {}
    for style, env in CALC_TYPESET_STYLE_ENVS.items():
        value = os.environ.get(env)
        if value is None:
            value = calc_option(md_path, metadata_files, "typeset-" + style)
        if value is None or value is False:
            found[style] = []
            continue
        words = [str(item) for item in value] if isinstance(value, list) else [value if isinstance(value, str) else str(value)]
        pieces = [piece for word in words for piece in re.split(r"[,\s]+", word.strip()) if piece]
        if [piece.casefold() for piece in pieces] == ["none"] or [piece.casefold() for piece in pieces] == ["off"]:
            pieces = []
        for piece in pieces:
            if not CALC_TYPESET_PIECE_RE.match(piece):
                raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.typeset-{style}: {piece!r} is not a piece of a name. "
                                 f"Give the letters of a base or of one word after an underscore (V, el, DNA), not V_el or A260")
        found[style] = list(dict.fromkeys(pieces))
    both = [piece for piece in found["upright"] if piece in found["italic"]]
    if both:
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.typeset-upright and typeset-italic both list {', '.join(both)}")
    return found


def calc_noindent_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """`calc: {noindent: ...}`: "lines" (the default, 3.33.18; a `::: calc` div's calculation lines have no first-line indent, its
    prose keeps the document's), "all" (true, all: no paragraph of the div is indented, 3.30.9) or "off" (false: the document's
    indent everywhere)."""
    value = os.environ.get(CALC_NOINDENT_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "noindent")
    if value is None:
        return "lines"
    word = str(value).strip().lower()
    if word in ("lines", "all"):
        return word
    flag = option_flag(value)
    if flag is None:
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.noindent must be lines, true (all) or false, not {value!r}")
    return "all" if flag else "off"


def calc_space(md_path: Path, metadata_files: list[Path]) -> str | None:
    """`calc: {space: 0.75em}`: the room above and below a `::: calc` div (pt, mm, cm, in or em), 0.75em unless set; off, false or 0 gives none."""
    value = os.environ.get(CALC_SPACE_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "space")
    if value is None or value is True:
        return CALC_SPACE_DEFAULT
    text = str(value).strip().lower().replace(" ", "")
    if value is False or text in ("", "off", "none", "false", "no", "0", "0.0"):
        return None
    if text in ("on", "true", "yes"):
        return CALC_SPACE_DEFAULT
    if not CALC_SPACE_RE.match(text):
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.space must be a length such as 0.75em or 6pt "
                         f"(pt, mm, cm, in, em), or off, not {value!r}")
    return text


def calc_align(md_path: Path, metadata_files: list[Path]) -> str:
    """`calc: {align: center}` centres the lines of a `::: calc` div; left (the default) leaves them flush left."""
    value = os.environ.get(CALC_ALIGN_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "align")
    text = str(value).strip().lower() if value is not None else "left"
    if text not in CALC_ALIGNS:
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.align must be left or center, not {value!r}")
    return text


def calc_constants_file(md_path: Path, metadata_files: list[Path]) -> Path | None:
    """`calc: {constants: FILE}`: the file, looked for beside the document, beside each metadata file, then in the cwd."""
    value = os.environ.get(CALC_CONSTANTS_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "constants")
    if value is None or str(value).strip().casefold() in ("", "none", "off"):
        return None
    name = Path(os.path.expanduser(str(value).strip()))
    candidates = [name] if name.is_absolute() else [md_path.parent / name, *(m.parent / name for m in metadata_files), Path.cwd() / name]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.constants: no file {str(value)!r} (looked beside the document "
                     f"and its metadata files)")


def calc_export_file(md_path: Path, metadata_files: list[Path]) -> Path | None:
    """`calc: {export: FILE}` / --calc-export: the CSV the build writes with the calculator's names (the mirror of
    `constants`), a relative name beside the document. None when nothing asks for one."""
    value = os.environ.get(CALC_EXPORT_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "export")
    if value is None or str(value).strip().casefold() in ("", "none", "off", "false"):
        return None
    name = Path(os.path.expanduser(str(value).strip()))
    return name if name.is_absolute() else md_path.parent / name


def write_calc_export(dump: str, target: Path) -> int:
    """`name,value,digits` from the text of calc.lua's dump (name TAB value TAB digits, value at %.17g), sorted by name, written
    atomically: the format `calc_constants_statements()` reads back, so the file is a constants file as it is. A value that is not a
    finite number has no form a constants file could hold and is left out. The number of names written (0: no file)."""
    rows = []
    for line in dump.splitlines():
        fields = line.split("\t")
        if len(fields) < 2 or not fields[0] or fields[1] in ("nan", "inf", "-inf"):
            continue
        rows.append((fields[0], fields[1], fields[2] if len(fields) > 2 else ""))
    if not rows:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, "name,value,digits\n" + "".join(f"{name},{value},{digits}\n" for name, value, digits in sorted(rows)),
                      newline="\n")
    return len(rows)


def calc_constants_statements(path: Path) -> list[str]:
    """The lines `name = value` (or `name = value = {ans:4sf}` with a digits column) of a constants file: columns
    name,value[,digits[,note]], comma, semicolon or tab separated, an optional header row, # lines and blank lines skipped."""
    import csv
    lines = [line for line in read_text_best_effort(path).splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        return []
    head = lines[0]
    delimiter = "\t" if head.count("\t") else ";" if head.count(";") > head.count(",") else ","
    statements = []
    for row in csv.reader(lines, delimiter=delimiter):
        cells = [cell.strip() for cell in row]
        if not cells or not any(cells):
            continue
        if cells[0].casefold() == "name":
            continue
        if len(cells) < 2 or not cells[0] or not cells[1]:
            raise SystemExit(f"{display_path(path)}: a constant needs a name and a value (name,value[,digits[,note]]): {','.join(cells)!r}")
        statement = f"{cells[0]} = {cells[1]}"
        if len(cells) > 2 and cells[2]:
            digits = calc_digits_value(cells[2])
            if digits is None:
                raise SystemExit(f"{display_path(path)}: the digits of {cells[0]} must be like 4sf or 2dp, not {cells[2]!r}")
            statement += " = {ans:" + digits + "}"
        statements.append(statement)
    return statements


def calc_digits_value(value) -> str | None:
    """``4sf`` / ``2dp`` from what was written (None when it is no format)."""
    found = CALC_DIGITS_RE.fullmatch(str(value).strip())
    if not found:
        return None
    count, kind = int(found.group(1)), found.group(2).lower()
    if (kind == "sf" and not 1 <= count <= 15) or (kind == "dp" and count > 15):
        return None
    return f"{count}{kind}"


def calc_digits_mode(md_path: Path, metadata_files: list[Path]) -> str | None:
    value = os.environ.get(CALC_DIGITS_ENV)
    if value is None:
        value = calc_option(md_path, metadata_files, "digits")
    if value is None or str(value).strip().casefold() in ("", "none", "auto"):
        return None
    found = calc_digits_value(value)
    if found is None:
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.calc.digits must be like 4sf (four significant figures) "
                         f"or 2dp (two decimal places), not {value!r}")
    return found


# calc_round_argument and calc_digits_argument: lib/pdfmd_args (v3.33.40)


# -- Appending to a metadata value (v3.31.40, entry 3du point 20) ---------------------------------------------------------
# A key written `author+:` adds to the value the layers below hold; `pdfmd-options: {metadata-append: [author]}` makes the
# document's own `author:` add to it as well. The layers, lowest first: the global metadata file, a kit's defaults, the
# folders' `.pdfmd/metadata.yaml` (farthest first), the document folder's metadata files, the document's own front matter.
# Pandoc cannot do it (the front matter beats every metadata file), so pdfmd merges, hands the finished values over under
# `pdfmd-merged` and pdfmd_lua/metadata_append.lua, run before every other filter, puts them in place.
METADATA_APPEND_KEY = "metadata-append"
METADATA_APPEND_BLOCKED = ("header-includes", "pdfmd-options")          # lifted into header files by pdfmd itself


def metadata_plus_key(key) -> bool:
    return isinstance(key, str) and len(key) > 1 and key.endswith("+")


def metadata_append_keys(md_path: Path | None, metadata_files: list[Path]) -> set[str]:
    """The keys whose document value appends (`pdfmd-options.metadata-append`: a name or a list of names); empty: replace."""
    value = first_pdfmd_option(md_path, list(metadata_files), METADATA_APPEND_KEY) if md_path is not None else None
    if value is None or value is False:
        return set()
    where = display_path(md_path)
    if not isinstance(value, (str, list, tuple)):
        raise SystemExit(f"{where}: pdfmd-options.{METADATA_APPEND_KEY} must be a key name or a list of them, not {value!r}")
    keys = {part.strip() for item in ([value] if isinstance(value, str) else value) for part in str(item).split(",") if part.strip()}
    for key in sorted(keys & set(METADATA_APPEND_BLOCKED)):
        raise SystemExit(f"{where}: pdfmd-options.{METADATA_APPEND_KEY} cannot name `{key}` (pdfmd lifts it into header files itself)")
    return keys


def metadata_joined(key: str, below, value, where: str) -> list:
    """What ``key`` holds after ``value`` is appended to ``below``: a list (a single value counts as a one-item list)."""
    for part in (below, value):
        if isinstance(part, dict):
            raise SystemExit(f"{where}: `{key}` holds a mapping, which cannot be appended to (only a value or a list can)")
    return [*([] if below is None else below if isinstance(below, list) else [below]),
            *([] if value is None else value if isinstance(value, list) else [value])]


def merge_metadata_layers(layers: list[tuple[dict, bool]], append_keys: set[str], where: str) -> dict:
    """The final value of every key an append touched, from ``layers`` (lowest first; the flag says the layer is the document's).
    In one layer `key:` is taken first and `key+:` appended after it. {} when nothing appends."""
    held: dict = {}
    touched: list[str] = []
    for mapping, is_document in layers:
        for key, value in mapping.items():
            if metadata_plus_key(key):
                continue
            if is_document and key in append_keys and key in held:
                held[key] = metadata_joined(key, held[key], value, where)
                touched.append(key)
            else:
                held[key] = value
        for key, value in mapping.items():
            if not metadata_plus_key(key):
                continue
            base = key[:-1]
            if base in METADATA_APPEND_BLOCKED:
                raise SystemExit(f"{where}: `{key}` is not supported (pdfmd lifts `{base}` into header files itself)")
            held[base] = metadata_joined(base, held.get(base), value, where)
            touched.append(base)
    return {key: held[key] for key in dict.fromkeys(touched)}


def metadata_layers(sources: list[Path], metadata_files: list[Path]) -> list[tuple[dict, bool]]:
    """The metadata a build reads, as layers, lowest first (see the comment above): the files in the order Pandoc gets them, then
    the front matter of each source."""
    layers: list[tuple[dict, bool]] = []
    for path in pandoc_metadata_order(list(metadata_files)):
        data = metadata_file_yaml(path)
        data.pop("pdfmd-options", None)
        layers.append((data, False))
    for source in sources:
        layers.append((front_matter_dict(read_text_best_effort(source)), True))
    return layers


def metadata_append_args(sources: Path | list[Path], metadata_files: list[Path], pandoc_options=(), no_auto=None) -> list[str]:
    """The metadata file with the finished values and ``--lua-filter metadata_append.lua``, only when some key appends; [] otherwise
    (every other build is untouched). Goes before every other filter."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or yaml is None:
        return []
    append = metadata_append_keys(files[0], metadata_files)
    layers = metadata_layers(files, metadata_files)
    merged = load_package("pdfmd_args").merged_cli_metadata(sys.modules[__name__], layers, append, display_path(files[0]), pandoc_options)
    merged.update(deferred("pdfmd_bibliography.sources", "merge_sources")(files, metadata_files, pandoc_options, no_auto))
    if not merged:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("metadata_append")
    if shipped is None:
        return []
    text = yaml.safe_dump({"pdfmd-merged": merged}, allow_unicode=True, sort_keys=False, width=1_000_000)
    target = cache_root() / "metadata" / f"{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.yaml"
    try:
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--metadata-file", str(target), "--lua-filter", str(shipped)]


def calc_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter calc.lua`` when a source has a `{=}` span or a `::: calc` div and `calc` is not off."""
    files = sources if isinstance(sources, list) else [sources]
    if not any(CALC_SPAN_RE.search(EMBED_BLOCK_RE.sub("", read_text_best_effort(file))) for file in files):
        return []
    if calc_is_off(files[0], metadata_files):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("calc")
    if shipped is None:
        return []
    arguments = ["-M", "pdfmd-calc-round=" + calc_round_mode(files[0], metadata_files)]
    digits = calc_digits_mode(files[0], metadata_files)
    if digits:
        arguments += ["-M", "pdfmd-calc-digits=" + digits]
    if calc_subs_on(files[0], metadata_files):
        arguments += ["-M", "pdfmd-calc-subs=true"]
    typeset = calc_typeset_mode(files[0], metadata_files)
    if typeset != "off":
        arguments += ["-M", "pdfmd-calc-typeset=" + typeset]
        for style, pieces in calc_typeset_styles(files[0], metadata_files).items():
            if pieces:
                arguments += ["-M", f"pdfmd-calc-typeset-{style}=" + ",".join(pieces)]
    noindent = calc_noindent_mode(files[0], metadata_files)
    if noindent != "off":
        arguments += ["-M", "pdfmd-calc-noindent=" + ("true" if noindent == "all" else noindent)]
    space = calc_space(files[0], metadata_files)
    if space:
        arguments += ["-M", "pdfmd-calc-space=" + space]
    if calc_align(files[0], metadata_files) == "center":
        arguments += ["-M", "pdfmd-calc-align=center"]
    constants = calc_constants_file(files[0], metadata_files)
    if constants is not None:
        arguments += ["-M", "pdfmd-calc-constants=" + "\n".join(calc_constants_statements(constants))]
    if CALC_SEED is not None and not BUILD.get("scanning"):
        arguments += ["-M", "pdfmd-calc-seed=" + str(CALC_SEED)]
    if CALC_BELOW is not None and not BUILD.get("scanning"):
        arguments += ["-M", "pdfmd-calc-below=" + str(CALC_BELOW)]
    if CALC_DUMP is not None and not BUILD.get("scanning"):
        arguments += ["-V", "pdfmd-calc-dump=" + str(CALC_DUMP)]
    return arguments + ["--lua-filter", str(shipped)]


# LaTeX packages a document's own commands need (v3.27.16, auto kind `texpackages`): `\ce{H2O}` without mhchem, or
# `\SI{3}{\metre}` without siunitx, stopped every LaTeX engine ("Undefined control sequence"). When a source uses one,
# the preamble gets a guarded load, last: nothing when the package is loaded already (nulabreport's own options win, no
# option clash), when the command is defined some other way, or when the package is not installed (the old error).
TEX_PACKAGE_USES = (
    ("mhchem", "[version=4]", "ce", re.compile(r"\\(?:ce|cee|cf)\s*\{")),
    ("siunitx", "", "SI", re.compile(r"\\(?:SI|si|num|qty|unit|ang|SIrange|numrange|qtyrange)\s*\{")),
)


def tex_package_args(sources: Path | list[Path], no_auto: list[str] | None, note=None) -> list[str]:
    """The arguments that give a LaTeX build the packages its commands need (TEX_PACKAGE_USES), or []: a header file,
    last (keep_header_includes puts back the header-includes it would drop, before it; v3.27.16 appended it to them
    with a filter instead, which a later header file of pdfmd's own undid)."""
    if auto_disabled(no_auto, "texpackages"):
        return []
    texts = []
    for file in sources if isinstance(sources, list) else [sources]:
        try:
            texts.append(Path(file).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError):
            continue
    wanted = [(name, options, macro) for name, options, macro, pattern in TEX_PACKAGE_USES
              if any(pattern.search(text) for text in texts)]
    if not wanted:
        return []
    lines = ["% pdfmd: packages the document's commands need, unless already there (--no-auto texpackages)",
             "\\makeatletter"]
    for name, options, macro in wanted:
        lines.append(f"\\@ifpackageloaded{{{name}}}{{}}{{\\ifdefined\\{macro}\\else"
                     f"\\IfFileExists{{{name}.sty}}{{\\usepackage{options}{{{name}}}}}{{}}\\fi}}")
    lines.append("\\makeatother")
    text = "\n".join(lines) + "\n"
    path = cache_root() / "tex" / f"packages-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    except OSError:
        return []
    if note is not None:
        note("TEXPACKAGES", "loads " + ", ".join(name for name, _, _ in wanted) + " unless the preamble does "
             "(the document uses " + ", ".join(f"\\{macro}" for _, _, macro in wanted) + ")")
    return ["--include-in-header", str(path)]


# -- Flat Markdown: --to gfm (v3.26.3) ----------------------------------------------
# `--to gfm` is plain GitHub-flavoured Markdown, nothing a viewer has to know about Pandoc (see pdfmd_flat and
# pdfmd_lua/flat.lua); `--to gfm+raw` is Pandoc's own gfm writer. --gfm-scripts / --gfm-math fill GFM_CLI in main();
# `pdfmd-options.gfm` is the document's way ({scripts: unicode|html|drop|ascii, math: dollars|fenced, title: true}).
GFM_CLI: dict = {"scripts": None, "math": None, "title": None}
# _PANDOC_EXTENSIONS, pandoc_extensions, flat_settings, flat_writer and flat_filter_args: lib/pdfmd_flat/build.py (v3.33.8)
# -- ASCII text: --to ascii (v3.26.8) -----------------------------------------------
# `--to ascii` (txt) and `--to ascii:FORMAT` (gfm, markdown, commonmark, rst, org, asciidoc ...) build that format with
# no character above 127 in it: pdfmd_lua/ascii.lua maps the words before the writer sees them (pdfmd_flat/asciify.py, run
# once as `pdfmd.py --ascii-stdio`), and the written file is mapped once more for what the writer made itself. The default
# name is `<name>.ascii.txt` (`.ascii.gfm.md`, `.ascii.md`), which `-o` recognises as the target again.
ASCII_CLI: dict = {"on": False, "missing": None}
ASCII_FORMATS = frozenset({"txt", "gfm", "gfm+raw", "markdown", "commonmark", "commonmark_x", "markdown_strict", "plain",
                           "rst", "org", "asciidoc"})
# split_ascii_target, ascii_missing, ascii_filter_args and ascii_finish: lib/pdfmd_flat/build.py (v3.33.8)


# -- A styled terminal reader: --to ansi and --view (v3.30.3) ---------------------------------------------------------
# `--to ansi` writes the document with ANSI styling for a terminal: bold, italic, code (coloured by language), links, lists,
# quotes, box-drawn tables (a cell may span columns and rows), display math stacked where it has fractions, roots or sums, all
# wrapped to the terminal's width. pdfmd_ansi/ draws it from Pandoc's JSON AST (`-t json`), so the metadata
# files, filters, citations, \ce and the other steps of a build apply as they do for any output; with no Pandoc, the
# built-in parser's tree stands in. `--view` is `-o -` plus a pager (see terminal_view). The width, the colour choice and
# OSC 8 links reach the builds (which may be child processes) as the environment variables below.
ANSI_WIDTH_ENV, ANSI_COLOR_ENV, ANSI_LINKS_ENV = "PDFMD_ANSI_WIDTH", "PDFMD_ANSI_COLOR", "PDFMD_ANSI_LINKS"
ANSI_FALLBACK_WIDTH = 120                                  # no terminal and no --width
# (the --view reader: its child arguments, stdin and sources, the pager and terminal_view moved to lib/pdfmd_view, v3.33.16)
# ansi_width_argument, ansi_columns, ansi_colour_on, ansi_math, ansi_document_text, ansi_finish and ansi_without_pandoc: lib/pdfmd_ansi/cli.py (v3.33.6)


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
    "ebook-convert": "calibre",
    "google-chrome": "chrome", "msedge": "edge", "microsoft-edge": "edge", "brave-browser": "brave",
}
# Engines with no number of their own (-e calibre, pdf-engine: calibre; v3.29.1: the browsers too): last resorts of the
# automatic chain (automatic_engines), not part of the numbered one above, and with no number of their own (the numbers are PDF_ENGINES' order in --check-dependencies).
EXPLICIT_ENGINES = ("calibre",)
# A browser prints a Markdown document too (v3.29.1; `-e edge`, `-e chrome`, `-e chromium`, `-e brave`, or the family word
# `-e browser`): Pandoc writes one self-contained HTML page (MathML, which a browser draws itself) and the browser, headless,
# prints it with the page the document asks for. Only when named, like Calibre; `.html` files already went to a browser
# first when they have scripts or MathML (pdfmd_direct).
BROWSER_ENGINES = ("chrome", "chromium", "edge", "brave")
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
    "browser": BROWSER_ENGINES,
}


# The tools pdfmd runs that Windows installers leave off PATH: tool -> (the `options:` key of the config that names it,
# its programs, its folders below an install root, other roots as (variable, folder below it), whether its folder goes on
# PATH for pdfmd's own runs). The folders are a file-system fact about those installers, not a behaviour threshold; a `*`
# matches a version in a folder name (poppler's builds). soffice stays off PATH: its folder holds a python.exe and DLLs of its own.
FOUND_TOOLS = {
    "tesseract": ("tesseract-path", ("tesseract",), ("Tesseract-OCR",), (), True),
    "soffice": ("soffice-path", ("soffice", "libreoffice"), ("LibreOffice/program",), (), False),
    "dot": ("dot-path", ("dot",), ("Graphviz/bin", "Graphviz*/bin"), (), True),
    "mmdc": ("mmdc-path", ("mmdc",), (), (("APPDATA", "npm"),), True),
    "poppler": ("poppler-path", ("pdftotext", "pdftoppm"), ("poppler*/Library/bin", "poppler*/bin"), (), True),
    "calibre": (None, ("ebook-convert",), ("Calibre2",), (), False),
    "pandoc": ("pandoc-path", ("pandoc",), ("Pandoc",), (("LOCALAPPDATA", "Pandoc"),), True),
    "typst": ("typst-path", ("typst",), (), (("LOCALAPPDATA", "Microsoft/WinGet/Links"),
                                              ("LOCALAPPDATA", "Microsoft/WinGet/Packages/Typst.Typst_*/typst-*")), True),
    "chrome": ("chrome-path", ("chrome",), ("Google/Chrome/Application",), (), False),      # by PDFMD_BROWSER, see use_found_tools()
}
WINDOWS_INSTALL_ROOTS = (("ProgramFiles", ""), ("ProgramW6432", ""), ("ProgramFiles(x86)", ""), ("LOCALAPPDATA", "Programs"))
TOOLS_FOUND: dict[str, tuple[str, str]] = {}      # tool -> (file, "key" | "probe") for what use_found_tools() found off PATH
TOOL_WARNED: set[str] = set()


def tool_program(folder: Path, program: str) -> Path | None:
    """The file of ``program`` in ``folder`` (with the extensions Windows runs a program by there)."""
    for suffix in ((".exe", ".cmd", ".bat", ".com") if sys.platform == "win32" else ("",)):
        if (folder / (program + suffix)).is_file():
            return folder / (program + suffix)
    return None


def app_path_file(program: str) -> Path | None:
    """The file the Windows registry (``App Paths``) gives for ``program.exe``, or None. PDFMD_NO_APP_PATHS=1 skips it; that
    switch is for the tests (a test that hides a tool must not find it through the registry), not a setting."""
    if sys.platform != "win32" or os.environ.get("PDFMD_NO_APP_PATHS"):
        return None
    try:
        import winreg
    except ImportError:
        return None
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{program}.exe") as key:
                value = winreg.QueryValueEx(key, "")[0]
        except OSError:
            continue
        file = Path(os.path.expandvars(str(value).strip().strip('"')))
        if file.is_file():
            return file
    return None


def locate_tool(name: str) -> tuple[str | None, str]:
    """(the tool's file, how it was found) for a tool of FOUND_TOOLS: ``"key"`` (the config's ``options.<tool>-path``, a file or a
    folder; a folder only for poppler), ``"path"`` (PATH), ``"probe"`` (the usual Windows install folders, then the registry's
    App Paths), or (None, ""). A key that names nothing is said once and passed over."""
    key, programs, folders, roots, _ = FOUND_TOOLS[name]
    named = config_options().get(key) if key else None
    if isinstance(named, str) and named.strip():
        place = Path(os.path.expandvars(named.strip())).expanduser()
        found = (next((tool_program(place, program) for program in programs if tool_program(place, program)), None)
                 if place.is_dir() else place if place.is_file() and name != "poppler" else None)
        if found:
            return str(found), "key"
        if f"{key}:{named}" not in TOOL_WARNED:
            TOOL_WARNED.add(f"{key}:{named}")
            print(f"WARN  config: options.{key} ({named}) holds no {programs[0]}; looking on PATH and in the usual folders",
                  file=sys.stderr)
    for program in programs:
        found = which(program)
        if found:
            return found, "path"
    if sys.platform == "win32":
        places = [Path(os.environ[variable]) / below for variable, below in WINDOWS_INSTALL_ROOTS if os.environ.get(variable)]
        for root in places:
            for pattern in folders:
                for folder in sorted(root.glob(pattern), reverse=True):
                    for program in programs:
                        if tool_program(folder, program):
                            return str(tool_program(folder, program)), "probe"
        for variable, below in roots:
            for folder in sorted(Path(os.environ[variable]).glob(below), reverse=True) if os.environ.get(variable) else []:
                for program in programs:
                    if tool_program(folder, program):
                        return str(tool_program(folder, program)), "probe"
        for program in programs:
            if app_path_file(program):
                return str(app_path_file(program)), "probe"
    return None, ""


def use_found_tools() -> None:
    """A tool that is installed but not on PATH (a Windows installer often leaves it off) is used all the same: its folder goes
    on PATH for pdfmd's own runs and the programs and filters it starts, in front when the config names it, behind otherwise.
    ``--doctor`` says where it was found."""
    for name, (_, _, _, _, on_path) in FOUND_TOOLS.items():
        file, how = locate_tool(name)
        if how not in ("key", "probe"):
            continue
        TOOLS_FOUND[name] = (file, how)
        if name == "chrome" and how == "key":
            os.environ.setdefault("PDFMD_BROWSER", file)       # the browser engines already read this for Chrome
        entries = os.environ.get("PATH", "").split(os.pathsep)
        folder = str(Path(file).parent)
        if on_path and folder not in entries:
            order = [folder, *entries] if how == "key" else [*entries, folder]
            os.environ["PATH"] = os.pathsep.join(entry for entry in order if entry)


# tool_note: lib/pdfmd_doctor/__init__.py (v3.33.31)


SOFFICE_TIMEOUT = 300.0          # seconds a LibreOffice run may take when nothing says otherwise: the `soffice-timeout` setting's default
SOFFICE_TIMEOUT_NOW: float | None = None        # what the document being built says (set by convert_one); None: the config's


def soffice_timeout_from(value) -> float:
    """The `soffice-timeout` setting as seconds: 0 = LibreOffice is never run, a negative number = no limit, not set or
    not a number = SOFFICE_TIMEOUT."""
    number = option_flag_number(value)
    return SOFFICE_TIMEOUT if number is None else number


def soffice_limit() -> float:
    """Seconds one LibreOffice run may take (0: never run it; negative: no limit)."""
    return SOFFICE_TIMEOUT_NOW if SOFFICE_TIMEOUT_NOW is not None else soffice_timeout_from(config_options().get("soffice-timeout"))


def run_soffice(command: list[str], **options) -> subprocess.CompletedProcess:
    """subprocess.run for a LibreOffice command under the `soffice-timeout` limit: output captured as text, and when the
    time is up the whole process tree is stopped (the launcher starts the real program as a child) and the result is a
    failed run whose stderr names the setting. `cwd` is the only option passed on."""
    limit = soffice_limit()
    if limit == 0:
        return subprocess.CompletedProcess(command, 1, "", "LibreOffice is turned off by the setting `soffice-timeout: 0`")
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                               cwd=options.get("cwd"), **flags)
    try:
        out, err = process.communicate(timeout=None if limit < 0 else limit)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
        process.communicate()
        return subprocess.CompletedProcess(command, 124, "", f"LibreOffice did not finish in {limit:g} s and was stopped "
                                           "(the setting `soffice-timeout`: seconds, 0 = never run it, -1 = no limit)")
    return subprocess.CompletedProcess(command, process.returncode, out, err)


def tool_folders_off_path() -> list[tuple[str, str]]:
    """(folder, why) for each folder of a tool pdfmd found off PATH that `pdfmd --user-path add` may put on the user PATH: the
    tools whose folder holds only their own programs (not LibreOffice or Chrome, whose folders hold others) and a TeX install."""
    found: dict[str, str] = {}
    for name, (file, _) in TOOLS_FOUND.items():
        if FOUND_TOOLS[name][4]:
            found.setdefault(str(Path(file).parent), f"{name} found there")
    if TEX_FOUND_AT is not None:
        found.setdefault(str(TEX_FOUND_AT), "TeX found there")
    return list(found.items())


# user_path_hint: lib/pdfmd_doctor/__init__.py (v3.33.31)


# user_path_command and setup_actions: lib/pdfmd_setup/command.py (v3.33.21)


def resolve_soffice() -> str | None:
    """Locate the LibreOffice/soffice binary, beyond a bare PATH lookup.

    A common real-world setup (confirmed on this machine) has `soffice`
    reachable only through an interactive shell alias pointing straight at
    the macOS .app bundle's own binary -- invisible to both which() and
    subprocess (neither one consults shell aliases, only PATH), so a plain
    which("soffice") silently reports it missing even though it works
    fine for the user every day at a terminal prompt. Checked, in order:
    `options.soffice-path` of the config, `soffice` on PATH, `libreoffice` on
    PATH (the usual Linux package name -- often a symlink to the same binary),
    then the standard macOS app-bundle path directly, or on Windows the usual
    install folders and the registry's App Paths (see locate_tool()).
    """
    if soffice_limit() == 0:                 # `soffice-timeout: 0`: LibreOffice is turned off, whatever is installed
        return None
    found = locate_tool("soffice")[0]
    if found:
        return found
    if sys.platform == "darwin":
        mac_path = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if mac_path.exists():
            return str(mac_path)
    return None


def calibre_own_folders() -> list[Path]:
    """The Calibre folders `pdfmd --install calibre` unpacked (data_root()/calibre/<version>), newest first."""
    try:
        found = [folder for folder in (data_root() / "calibre").iterdir() if folder.is_dir()]
    except OSError:
        return []
    return sorted(found, key=lambda folder: tuple(int(part) for part in re.findall(r"\d+", folder.name)), reverse=True)


def resolve_calibre() -> str | None:
    """Calibre's `ebook-convert`: on PATH (Linux packages, Homebrew's cask), else where the installers put it
    without touching PATH (the macOS app bundle, `%ProgramFiles%\\Calibre2` on Windows). `PDFMD_CALIBRE` names the file
    instead, or an empty value says there is none (the tests of the no-Pandoc tier use it)."""
    if "PDFMD_CALIBRE" in os.environ:
        named = os.environ["PDFMD_CALIBRE"]
        return named if named and Path(named).is_file() else None
    found = which("ebook-convert")
    if found:
        return found
    places: list[Path] = [folder / "ebook-convert" for folder in calibre_own_folders()]      # `pdfmd --install calibre` (Linux)
    if sys.platform == "darwin":
        places += [Path(folder) / "calibre.app" / "Contents" / "MacOS" / "ebook-convert"
                   for folder in ("/Applications", Path.home() / "Applications")]
    found = next((str(place) for place in places if place.is_file()), None)
    if found is None and sys.platform == "win32":
        found = locate_tool("calibre")[0]
    return found


def engine_executable(engine: str) -> str | None:
    """which(), except for "soffice" -- see resolve_soffice()'s docstring -- and "calibre" (its `ebook-convert`).

    Every PDF_ENGINES membership check (installed_engines, select_engines,
    dependency_report) goes through this instead of a bare which() so
    "soffice" is recognized as available under the same real-world
    condition the pipeline will actually invoke it under.
    """
    if engine == "calibre":
        return resolve_calibre()
    if engine in BROWSER_ENGINES:
        try:
            import pdfmd_direct as direct
        except ImportError:
            return None
        return direct.find_browser(engine, which)
    return resolve_soffice() if engine == "soffice" else which(engine)


def installed_engines() -> list[str]:
    """Return PDF engines that are currently executable, in fallback order."""
    return [engine for engine in PDF_ENGINES if engine_executable(engine)]


def automatic_engines() -> list[str]:
    """The chain of a build that names no engine (v3.29.1): the installed numbered engines in their order, and where those
    all failed or are missing, the browsers (headless Chrome, Chromium, Edge, Brave) and Calibre, ahead of LibreOffice, whose
    page is the least like the document's. They are last resorts: LaTeX, Typst and WeasyPrint still go first. `-e pandoc`
    is every engine Pandoc drives and never these (a list of your own names them)."""
    engines = installed_engines()
    extras = [engine for engine in (*BROWSER_ENGINES, "calibre") if engine_executable(engine)]
    if "soffice" in engines:
        position = engines.index("soffice")
        return [*engines[:position], *extras, *engines[position:]]
    return [*engines, *extras]


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
    if requested and "," in requested:
        return engine_chain(requested, presentation, label)
    if requested and not re.search(r"[\\/]", requested) and requested.casefold().endswith(".exe"):
        requested = requested[:-4]          # `-e lualatex.exe`: the name Windows shows for the engine
    if requested and requested.casefold() == "pandoc":
        candidates = installed_engines() if which("pandoc") else []
        if presentation:
            candidates = [engine for engine in candidates if engine in LATEX_ENGINES]
        if not candidates:
            raise SystemExit(f"{label} named pandoc (every engine Pandoc drives), but none is installed. "
                             "Run --check-dependencies for a status report.")
        return candidates
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
            too_old = pdfmd_install.typst_too_old() if "typst" in installed_in_group else None
            if too_old:                                # too old counts as missing (v3.33.62)
                installed_in_group.remove("typst")
                if not installed_in_group:
                    raise SystemExit(too_old)
            if not installed_in_group:
                raise SystemExit(
                    f"{label} restricted to the '{family}' engine family, but none of "
                    + ", ".join(group) + " is installed on PATH. Install one, or pass a bare "
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
            if requested == "typst" and pdfmd_install.typst_too_old():
                raise SystemExit(pdfmd_install.typst_too_old())
            return [requested]
        if requested == "calibre":
            raise SystemExit(f"{label} requested Calibre, but its ebook-convert was not found (on PATH, in "
                             "calibre.app or in Calibre2 under Program Files). Install Calibre: `pdfmd --install calibre`, "
                             "`brew install --cask calibre`, `winget install calibre.calibre`, your package manager, or "
                             "calibre-ebook.com.")
        raise SystemExit(
            f"Requested PDF engine '{requested}' was not found on PATH. "
            "Install it or choose one listed by --check-dependencies."
        )

    candidates = automatic_engines() if which("pandoc") else []
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


def engine_chain(requested: str, presentation: bool, label: str) -> list[str]:
    """``-e typst,calibre,lualatex`` (v3.28.42): the engines to try, in the order written. A word is an engine, an alias,
    a family (tex, html, typst: its installed members in their usual order) or `pandoc` (every engine Pandoc drives).
    Named means named: nothing outside the list is tried. A word whose engine is not installed is passed over with a
    note when another one of the list is; the build stops only when none is."""
    chain: list[str] = []
    missing: list[str] = []
    for word in (item.strip() for item in requested.split(",")):
        if not word:
            continue
        try:
            found = select_engines(word, presentation, label)
        except SystemExit as error:
            missing.append(f"{word}: {str(error).splitlines()[0]}")
            continue
        chain += [engine for engine in found if engine not in chain]
    if not chain:
        raise SystemExit(f"{label} names {requested}, and none of it can run:\n  " + "\n  ".join(missing))
    for line in missing:
        print(f"NOTE  {label}: {line}; the next in the list is tried", file=sys.stderr)
    return chain


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
    vprint(verbose, f"ENGINE  {md_path}: " + " -> ".join(resolved))
    return resolved


def dependency_report() -> bool:
    """Print executable availability and return whether conversion can run."""
    pandoc = which("pandoc")
    print(f"{'OK  ' if pandoc else 'MISS'}  pandoc" + (f"  ({pandoc})" if pandoc else ""))
    for number, engine in enumerate(PDF_ENGINES, start=1):
        path = engine_executable(engine)
        print(f"{'OK  ' if path else 'MISS'}  {number}. {engine}" + (f"  ({path})" if path else ""))
    for engine in EXPLICIT_ENGINES:
        path = engine_executable(engine)
        print(f"{'OK  ' if path else 'MISS'}  {engine} (only when named: -e {engine})" + (f"  ({path})" if path else ""))
    quarto = which("quarto")
    print(f"{'OK  ' if quarto else 'MISS'}  quarto (only needed for .qmd files)"
         + (f"  ({quarto})" if quarto else ""))
    if which("weasyprint"):
        jax = mathjax_runtime()
        print(f"{'OK  ' if jax else 'MISS'}  MathJax (math in WeasyPrint's PDFs"
              + (f": {jax[1].name}, fonts {', '.join(mathjax_fonts(jax[1]))}, node {jax[0]})" if jax
                 else "; pdfmd --install math:mathjax)"))
        runtime = katex_runtime()
        print(f"{'OK  ' if runtime else 'MISS'}  KaTeX (math in WeasyPrint's PDFs"
              + (f": {runtime[1].name}, node {runtime[0]})" if runtime else "; pdfmd --install math:katex)"))
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
    print("Smaller PDFs (lossless, the first one installed shrinks every PDF; see --shrink):")
    for row in load_package("pdfmd_shrink").check_rows():
        print(row)
    print("Reading PDFs (PDF to Markdown, through batchocr):")
    reader = find_batchocr()
    reader_version = batchocr_version(reader) if reader else None
    print(f"{'OK  ' if reader_version and reader_version >= BATCHOCR_MIN else 'MISS'}  batchocr"
          + (f"  ({'.'.join(map(str, reader_version))})" if reader_version else "  (pdfmd --install batchocr)"))
    for tool in ("tesseract", "pdftotext", "pdftoppm"):
        path = which(tool)
        print(f"{'OK  ' if path else 'MISS'}  {tool}" + (f"  ({path})" if path else f"  ({tesseract_install_hint()})"))
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
# With no Pandoc, and Calibre installed (v3.29.1), Calibre reads the Markdown itself (its Python-Markdown reader: tables,
# footnotes, fenced code, lists) and prints it: before the rough renderers below, which stay its fallback. It has no math
# (formulas are text, as in inkmd) and none of Pandoc's syntax; what it cannot honour is reported as for the others.
NATIVE_ENGINES = ("calibre", "md2pdf", "inkmd")
NATIVE_ALIASES = {"ink": "inkmd", "reportlab": "md2pdf", "pymd2pdf": "md2pdf", "ebook-convert": "calibre"}
# NATIVE_SOURCE_SUFFIXES and NATIVE_READERS: lib/pdfmd_native (v3.33.39)
# INSTALL_SPECS: lib/pdfmd_install/__init__.py (v3.33.35)
# Kinds that are not pip packages (see install_typst), and the one that is both.
INSTALL_KINDS = ("pandoc", "typst", "full", "core", "cortex", "math", "diagram", "calibre", "emoji", "batchocr", "fonts", "translit", "ocr", "tui", "kit")
INSTALL_SIZES = {"kit": "the repository you name", "tui": "about 1 MB", "translit": "about 3 MB", "ocr": "see `pdfmd --install ocr`", "fonts": "see `pdfmd --install fonts`", "emoji": "about 11 MB", "math": "about 150 MB", "pandoc": "about 35 MB download",
                 "typst": "about 15 MB download", "full": "about 50 MB download",
                 "diagram": "about 20 MB: D2 17 MB, Graphviz 2 MB",
                 "calibre": "190 to 360 MB download", "core": "Pandoc 35 MB and Tectonic 10 to 22 MB download",
                 "cortex": "Pandoc 35 MB and Tectonic 10 to 22 MB download",
                 "batchocr": "about 40 MB with PyMuPDF"}
# NATIVE_META_KEYS (with its comment): lib/pdfmd_native (v3.33.39)
# The oldest Pandoc pdfmd is tested with: 3.1.3, which is what the claude.ai sandbox has (the suite runs against it). An
# older one may still work; the first compile with it says so once. What an older-than-latest one does without:
PANDOC_MIN = (3, 1, 3)
# PANDOC_FEATURES and pandoc_limits: lib/pdfmd_doctor/__init__.py (v3.33.31)


def warn_old_pandoc() -> None:
    """The first compile with a Pandoc older than PANDOC_MIN says so, once for that version on this machine."""
    version = pandoc_version()
    if version == (0,) or version >= PANDOC_MIN:
        return
    shown = ".".join(map(str, version))
    path = config_root() / f"notice-pandoc-{shown}"
    if os.environ.get("PDFMD_NO_PROMPT") or path.exists():
        return
    print(f"WARN  Pandoc {shown} is older than {'.'.join(map(str, PANDOC_MIN))}, the oldest pdfmd is tested with; "
          "it may work, and a newer one (`pdfmd --install pandoc`) is the first thing to try if something looks wrong. "
          "This is said once.", file=sys.stderr)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("shown\n", encoding="utf-8")
    except OSError:
        pass


PANDOC_MISSING = ("Pandoc was not found on PATH. Install it with `pdfmd --install pandoc` (no admin rights; "
                  "`pdfmd --install full` adds Typst for PDF output), or -- macOS: `brew install pandoc`; "
                  "Debian/Ubuntu: `sudo apt install pandoc`; others: https://pandoc.org/installing.html "
                  "-- then run `pdfmd --check-dependencies`.")
# What this run could not render natively, by kind -> count; read by
# offer_native_upgrade() once the build is done.
NATIVE_LOST: dict[str, int] = {}


def inkmd_vendored() -> bool:
    """Whether the vendored inkmd (pdfmd_inkmd/) ships next to this file."""
    return importlib.util.find_spec("pdfmd_inkmd") is not None


def md2pdf_available() -> bool:
    """pymd2pdf (not the unrelated WeasyPrint-based `md2pdf`) is installed."""
    import importlib.metadata  # here, not at the top: only this needs it (start-up time, v3.32.55)
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
    """The colour-emoji font: pdfmd's own (`pdfmd --install emoji`), else that of a
    separately installed `inkmd` (the [emoji] extra)."""
    own = fonts_directory() / "emoji" / "NotoColorEmoji.ttf"
    if own.is_file():
        return own
    try:
        spec = importlib.util.find_spec("inkmd")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    font = Path(spec.origin).parent / "assets" / "emoji" / "NotoColorEmoji.ttf"
    return font if font.is_file() else None


def is_native_engine(engine: str) -> bool:
    """Whether ``engine`` is one of the Pandoc-less renderers in this run: Calibre's own name is one only with no Pandoc (with
    Pandoc, `-e calibre` is the HTML route)."""
    return engine in NATIVE_ENGINES and (engine != "calibre" or not which("pandoc"))


def native_available(engine: str) -> bool:
    if engine == "calibre":
        return not which("pandoc") and resolve_calibre() is not None      # with Pandoc, -e calibre is the HTML route
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
        if name not in NATIVE_ENGINES or (name == "calibre" and which("pandoc")):
            return None
        engines = [name] if native_available(name) else []
        if not engines:
            hint = ("needs Python 3.11 or newer" if name == "md2pdf" and sys.version_info < (3, 11)
                    else "Calibre's ebook-convert was not found" if name == "calibre"
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
    return chosen in (None, "pdf", "ansi")           # ansi: the built-in parser draws it (v3.30.3)


# native_note, native_lose and the patterns the native tier rewrites with (HEADING_ATTR_RE to PAPER_SIZES): lib/pdfmd_native (v3.33.39)


# the comment on math without a typesetter: lib/pdfmd_native (v3.33.39)
Chunk = tuple[str, str, float]  # (Markdown/inline-HTML, the text as it prints, size scale)

# MATH_GREEK, MATH_SYMBOLS and the other tables of the math converter up to MATH_ESCAPES: lib/pdfmd_native (v3.33.39)
MATH_LINE_BREAK = "\x00"
# SUPERSCRIPTS, SUBSCRIPTS, MARKDOWN_ESCAPE_RE, escape_markup and MathText: lib/pdfmd_native (v3.33.39)


def math_lines(expression: str, html: bool = True) -> list[list[Chunk]]:
    """One list of chunks per displayed line (an `aligned` block has several)."""
    lines: list[list[Chunk]] = [[]]
    for chunk in MathText(expression, html).sequence():
        if chunk[0] == MATH_LINE_BREAK:
            lines.append([])
        else:
            lines[-1].append(chunk)
    return [line for line in lines if "".join(piece for _, piece, _ in line).strip()] or [[]]


# chunks_markup and chunks_width: lib/pdfmd_native (v3.33.39)


def _millimetres(width: float, height: float) -> tuple[float, float]:
    return (round(width * 72 / 25.4, 2), round(height * 72 / 25.4, 2))


# Every paper the built-in renderers can set, portrait, in points (ISO sizes from their millimetres). inkmd knows the names in
# PAPER_SIZES; the rest reach it as a (width, height) pair. md2pdf takes the names ReportLab has (a0-a10, b0-b10, c0-c10, letter,
# legal, elevenseventeen), so the ones it lacks (executive, folio, tabloid) get a NOTE there and its own default.
NATIVE_PAPER_POINTS = {
    "a0": _millimetres(841, 1189), "a1": _millimetres(594, 841), "a2": _millimetres(420, 594), "a3": (841.89, 1190.55),
    "a4": (595.28, 841.89), "a5": (419.53, 595.28), "a6": _millimetres(105, 148),
    "b4": _millimetres(250, 353), "b5": _millimetres(176, 250), "b6": _millimetres(125, 176),
    "c4": _millimetres(229, 324), "c5": _millimetres(162, 229),
    "letter": (612.0, 792.0), "legal": (612.0, 1008.0), "tabloid": (792.0, 1224.0),
    "executive": (522.0, 756.0), "folio": (612.0, 936.0),
}
PAPER_NAME_ALIASES = {"us-letter": "letter", "usletter": "letter", "us-legal": "legal", "uslegal": "legal"}
PAGE_WIDTHS = {name: points[0] for name, points in NATIVE_PAPER_POINTS.items()}
# NO_BREAK_SPACE, centred_math, inline_math, stacked_math, MATHTEXT_REWRITES (with its comment), mathtext_form and NativeSource: lib/pdfmd_native (v3.33.39)


def scalar_text(value) -> str:
    """A front-matter value as one line of plain text ('' when absent)."""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return " ".join(str(value).split())


# author_names: lib/pdfmd_native (v3.33.39)


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


# CSV_DIV_LINE_RE, DIV_CLOSE_RE and DIV_ATTRIBUTE_RE: lib/pdfmd_native (v3.33.39)


CSV_DELIMITER_NAMES = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|", "space": " ", "colon": ":"}
# CSV_ALIGNMENTS, CSV_SEPARATOR_CELL_RE, csv_extension_delimiter and csv_guess_delimiter: lib/pdfmd_native (v3.33.39)


CSV_DELIMITER_WORDS = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe", " ": "space", ":": "colon"}


# csv_keep to describe_native_changes (the .csv div table, normalise_gfm, the paper, inkmd, md2pdf and Calibre's Markdown reader, convert_native): lib/pdfmd_native (v3.33.39)


def native_run_note(engines: list[str]) -> None:
    """Printed once when the native tier was chosen automatically."""
    reason = "Pandoc was not found" if not which("pandoc") else "no PDF engine was found"
    what = ("Calibre's Markdown reader (no math, none of Pandoc's syntax)" if engines and engines[0] == "calibre"
            else "the built-in renderer")
    print(f"NOTE  {reason}: building with {what} ({' / '.join(engines)}). "
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


# -- The global config file (v3.23.6) ------------------------------------------------
# ~/.config/pdfmd/config.yaml (`$XDG_CONFIG_HOME`, `%APPDATA%\pdfmd` on Windows; PDFMD_CONFIG names
# another file, or an empty value none): the user's own defaults, kept where `--clear-cache` and a
# cleaned ~/.cache cannot take them. Its `options:` block holds `pdfmd-options` defaults that apply
# to every document, below anything the document or its metadata files say; `translit:` is the
# romanization packs of the lookup (below --translit and PDFMD_TRANSLIT). The decisions pdfmd itself
# remembers for the user (filters it trusts, a dismissed offer) live in the same folder.
CONFIG_FILENAME = "config.yaml"
CONFIG_KEYS = ("translit", "options", "setup-ui", "disabled", "kits")
CONFIG_TEMPLATE = """# pdfmd's global config. Everything is optional; delete a line to get the built-in default back.
# Precedence: command line > the document's `pdfmd-options:` > its metadata files > this file.

# Romanization packs for finding a document by a name typed in Latin letters
# (greek armenian georgian hebrew arabic hangul kana han other; Cyrillic is always on).
# translit: [greek, hangul]

# Defaults for the `pdfmd-options:` of every document.
options:
  # What to do about characters the main font cannot draw:
  #   char      set just those characters in another installed font
  #   word      set the whole word in another font, so no word mixes fonts (default); it sees literal
  #             characters only: a missing glyph that comes from a TeX command (`\\geq` in text mode) still
  #             rebuilds the whole document in DejaVu Serif, with a WARN naming the font and the code points
  #   document  use the one installed font that draws most of the document as the main font
  #   off       nothing: what Pandoc and TeX do without pdfmd (missing glyphs vanish or print boxes)
  #   box       no fallback; each missing character is drawn as a black box
  #   error     no fallback; the build fails, listing the missing characters
  # fallback: word
  # What to do about characters no installed font draws (after the fallback): warn, box or error.
  # missing: warn
  # pdf-engine: lualatex
  # cache: {aux: true, location: global}   # location: global (~/.cache/pdfmd) or document (.cache/pdfmd beside it)
"""


def config_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "pdfmd"


def config_path() -> Path | None:
    override = os.environ.get("PDFMD_CONFIG")
    if override is not None:
        return Path(override).expanduser() if override.strip() else None
    return config_root() / CONFIG_FILENAME


@lru_cache(maxsize=None)
def load_config() -> dict:
    """The config file as a dict ({} when there is none, or it cannot be read: with a WARN)."""
    path = config_path()
    if path is None or yaml is None or not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        print(f"WARN  config {path}: cannot be read ({error}); ignoring it", file=sys.stderr)
        return {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        print(f"WARN  config {path}: expected a mapping of settings; ignoring it", file=sys.stderr)
        return {}
    unknown = sorted(str(key) for key in set(data) - set(CONFIG_KEYS))
    if unknown:
        print(f"WARN  config {path}: unknown setting{'s' if len(unknown) > 1 else ''} "
              f"{', '.join(unknown)} (known: {', '.join(CONFIG_KEYS)}); `options:` holds pdfmd-options",
              file=sys.stderr)
    return data


def merge_options(base: dict, layer: dict) -> dict:
    """``layer`` over ``base``: a mapping on both sides is merged field by field, anything else is the layer's."""
    merged = dict(base)
    for key, value in layer.items():
        merged[key] = merge_options(merged[key], value) if isinstance(value, dict) and isinstance(merged.get(key), dict) else value
    return merged


FOLDER_CODE_KEYS = (("office", "profile"),)         # a Lua file that runs in the Word route: a folder cannot name one


def folder_options_safe(path: str, options: dict) -> dict:
    """A folder layer's options without what names code (FOLDER_CODE_KEYS), said once."""
    for outer, inner in FOLDER_CODE_KEYS:
        if isinstance(options.get(outer), dict) and inner in options[outer]:
            if f"{path}:{outer}.{inner}" not in FOLDER_WARNED:
                FOLDER_WARNED.add(f"{path}:{outer}.{inner}")
                print(f"WARN  {path}: {outer}.{inner} names code and cannot be set by a folder; ignored", file=sys.stderr)
            options = {**options, outer: {key: value for key, value in options[outer].items() if key != inner}}
    return options


def config_options(md_path: Path | None = None) -> dict:
    """`options:` of the config file: defaults for every document's ``pdfmd-options``. With a document, the `options:` of the
    folder settings above it lie over them (v3.29.29; the nearest folder wins)."""
    options = load_config().get("options")
    options = options if isinstance(options, dict) else {}
    if md_path is None:
        return options
    try:
        layers = folder_layer_files(str(Path(md_path).resolve().parent))
    except OSError:
        return options
    for path, folder_options in reversed(layers):
        options = merge_options(options, folder_options_safe(path, folder_options))
    return options


# folder_size, DEEP_SAMPLE, deep_checks, foreign_commands, doctor_report, completion_options and completion_script: lib/pdfmd_doctor/__init__.py (v3.33.31)


# -- Word / OpenDocument output (pdfmd_office/) -----------------------------------------
# `-o x.docx`, `--to docx|odt`: Pandoc builds the file from a *reference document* (styles, page
# setup, headers and footers). pdfmd finds the user's own (a `reference.docx`/`.dotx`, `<name>-reference.*`
# beside the document or in its metadata/ folder, `office: {reference-doc: ...}`, the config folder, or
# Pandoc's --reference-doc) and writes the document's page size, margins, fonts, size, language and
# pdfmd's house look into a copy of it. See pdfmd_office/.


# package_places, kpsewhich_locate, read_package_helper and kit_package_folders: lib/pdfmd_kits/locate.py (v3.33.22)


KPSEWHICH_FOLDERS: dict[tuple, Path | None] = {}   # (package, the variables that steer TeX's search) -> its folder


def installed_package_folder(package: str) -> Path | None:
    """The folder of the installed `<package>.sty` that kpsewhich finds (through a symlink to its real folder), or None;
    one kpsewhich call per package and search path. Asked from an empty folder: from the document's own, TeX would answer
    with the lone copy this is looked up for."""
    key = (package, *(os.environ.get(name) for name in ("TEXINPUTS", "TEXMFHOME", "TEXMFLOCAL", "TEXMF")))
    if key not in KPSEWHICH_FOLDERS:
        with tempfile.TemporaryDirectory(prefix="pdfmd-kpse-") as empty:
            located = kpsewhich_locate([package + ".sty"], empty).get(package + ".sty")
        KPSEWHICH_FOLDERS[key] = located.resolve().parent if located else None
    return KPSEWHICH_FOLDERS[key]


# -- Kits: find one (entry 3du, C1) ------------------------------------------------------------------------------------
# A kit is a folder with a `.kit` file (pdfmd_kits has the format and the search). Search is not selection: nothing here
# runs for a document that selects no kit, and a document that only says `\usepackage{nulabreport}` is not switched to the
# kit. The places, in order: a kits/ folder beside the document or above it, the config's `kits:` (a folder that is a kit,
# or one that holds kits; a mapping {path:, aliases: {MODE: [names]}} adds mode names without editing the kit), a kits/ folder
# beside the config file, then the folder of `NAME.sty` that kpsewhich finds (the cached answer first: one stat). `--no-auto
# kit` takes the searching off (the config's `kits:` stays: the user named those), `--no-auto kpsewhich` the TeX tree only.
KIT_CACHE_FILE = "kits.json"


def configured_kits() -> list[tuple[Path, dict]]:
    """(folder, {mode: [aliases]}) of each `kits:` entry of the config; a relative path is read from the config's folder."""
    raw = load_config().get("kits")
    if raw is None:
        return []
    config = config_path()
    found: list[tuple[Path, dict]] = []
    for entry in (raw if isinstance(raw, list) else [raw]):
        aliases: dict = {}
        if isinstance(entry, dict):
            aliases = entry.get("aliases") or {}
            entry = entry.get("path")
            if not isinstance(aliases, dict):
                print(f"WARN  config {config}: `aliases:` of a kits: entry must be a mapping of mode -> names; ignored",
                      file=sys.stderr)
                aliases = {}
        if not isinstance(entry, str) or not entry.strip():
            print(f"WARN  config {config}: an entry of `kits:` is a path (or a mapping with `path:`); skipped", file=sys.stderr)
            continue
        path = Path(os.path.expandvars(entry)).expanduser()
        if not path.is_absolute() and config is not None:
            path = config.parent / path
        found.append((path, aliases))
    return found


def kit_locations(base: Path | None = None, no_auto: list[str] | None = None, project: bool = True) -> list:
    """The folders a kit is searched in (pdfmd_kits.Location), in order."""
    from pdfmd_kits import Location
    base = (base or Path.cwd()).resolve()
    searching = not auto_disabled(no_auto, "kit")
    places = []
    if searching and project:
        places += [Location("a kits/ folder above the document", folder / "kits")
                   for folder in (base, *base.parents) if (folder / "kits").is_dir()]
    places += [Location("kits: in the config", path, aliases) for path, aliases in configured_kits() if path.is_dir()]
    config = config_path()
    if searching and config is not None and (config.parent / "kits").is_dir():
        places.append(Location("the kits/ folder beside the config file", config.parent / "kits"))
    return places


def kit_path_like(text: str) -> bool:
    """A kit reference that is a path, not a name: it has a separator or starts with `~` or `.`."""
    return "/" in text or "\\" in text or text.startswith(("~", "."))


def find_kit(reference: str, base: Path | None = None, no_auto: list[str] | None = None, named_only: bool = False):
    """pdfmd_kits.Found for a kit named by ``reference`` (a name, or a path to its folder or `.kit` file); raises
    pdfmd_kits.KitError when there is none, naming where it looked and the nearest names."""
    from pdfmd_kits import Found, KitError, find, list_kits
    from pdfmd_kits.discovery import kit_files
    base = (base or Path.cwd()).resolve()
    reference = str(reference).strip()
    if named_only and kit_path_like(reference):
        raise KitError(f"`{reference}` is a path, and a folder's `kit:` names a kit (a folder's options cannot name code); "
                       "register the kit under `kits:` of the config file, or select it by path in the document")
    if kit_path_like(reference):
        path = Path(os.path.expandvars(reference)).expanduser()
        path = Path(os.path.normpath(path if path.is_absolute() else base / path))
        files = [path] if path.is_file() else kit_files(path) if path.is_dir() else []
        if len(files) != 1:
            raise KitError(f"no kit at {display_path(path)}: a kit is a folder with a `.kit` file in it"
                           + (f" (it holds {len(files)})" if len(files) > 1 else ""))
        found = Found(files[0], "a path")
    else:
        searching = not auto_disabled(no_auto, "kit")
        lookup = installed_package_folder if searching and not auto_disabled(no_auto, "kpsewhich") else None
        locations = kit_locations(base, no_auto, project=not named_only)
        found = find(reference, locations, lookup, kit_cache() if lookup else None)
        if found is None:
            from difflib import get_close_matches
            from pdfmd_kits import normalise
            from pdfmd_kits.discovery import _declared_name
            known = {normalise(_declared_name(item.path) or item.path.parent.name): _declared_name(item.path) or item.path.parent.name
                     for item in list_kits(locations)}
            near = [known[key] for key in get_close_matches(normalise(reference), list(known), n=3, cutoff=0.6)]
            looked = [location.source for location in locations] + (["the TeX tree (kpsewhich)"] if lookup else [])
            raise KitError(f"no kit called `{reference}` (looked in: {', '.join(looked) or 'nowhere: --no-auto kit'})"
                           + (f"; did you mean {', '.join(near)}?" if near else "")
                           + "; a kit is a folder with a `.kit` file: name its folder in `kits:` of the config, or give its path")
    if VERBOSE_OUTPUT:
        print(f"AUTO KIT  {reference}: {display_path(found.path)} ({found.source}{', cached' if found.cached else ''})")
    return found


def kit_cache():
    from pdfmd_kits import Cache
    return Cache(cache_root() / KIT_CACHE_FILE)


# kit_install_record and kits_report: lib/pdfmd_kits/locate.py (v3.33.22)


# -- Kits: choose them (entry 3du, C2) -------------------------------------------------------------------------------------
# `pdfmd-options: {kit: ...}` in the config (global), the global metadata or a preset (preset), a folder's `.pdfmd/` files
# (folder; by NAME only), a document's own metadata and front matter (document); `--kit` above them all. pdfmd_kits.selection
# has the grammar and the stacking. A selected kit supplies, in this order: its defaults as metadata files between the global
# metadata and the folders' own (so a folder tunes the kit and the document wins), the folder of its package for the helper
# lookup, its Lua filters, and its folder on Pandoc's resource path. The preamble it writes is C3.
KIT_CLI: list | None = None                     # --kit, parsed (None: not given; [OFF]: bare --kit / none)
KIT_STACK_CLI = None                            # --kit-stack, as given
KIT_METADATA: dict[Path, Path] = {}             # a metadata file a kit supplies -> that kit's folder
ACTIVE_KITS: dict[tuple, list] = {}             # the kits of one document in one run (the choice does not change mid-build)


class ActiveKit:
    """A kit chosen for a document: the loaded kit, its mode (or None), where it was found, and the selection behind it."""

    def __init__(self, kit, mode, found, selection):
        self.kit, self.mode, self.found, self.selection = kit, mode, found, selection

    def describe(self) -> str:
        return (f"{self.kit.name} {self.kit.version}".rstrip() + (f" mode {self.mode.name}" if self.mode else "")
                + f" (chosen in the {self.selection.layer or 'command line'})")


def set_kit_cli(values, stack_value) -> None:
    """--kit (repeatable; bare = no kit) and --kit-stack, read once at the start of a run."""
    global KIT_CLI, KIT_STACK_CLI
    KIT_CLI, KIT_STACK_CLI = None, None
    ACTIVE_KITS.clear()
    if values is None and stack_value is None:
        return                                                  # no kit asked for: the kit code is not even imported
    from pdfmd_kits import selection
    if values is not None:
        KIT_CLI = []
        for value in values:
            try:
                KIT_CLI += selection.parse(value, "command line") if value else [selection.OFF]
            except selection.SelectionError as error:
                raise SystemExit(f"--kit {value}: {error}")
    if stack_value is not None:
        try:
            selection.parse_stack_setting(stack_value)
        except selection.SelectionError as error:
            raise SystemExit(f"--kit-stack: {error}")
        KIT_STACK_CLI = stack_value


def kit_layer_selections(md_path: Path, metadata_files: list[Path]) -> dict[str, list]:
    """The `kit:` choices of each layer, parsed: {layer: [Selection]} (see pdfmd_kits.selection.LAYERS)."""
    layers: dict[str, list] = {name: [] for name in ("global", "preset", "folder", "document")}

    def add(layer: str, options, where: str) -> None:
        if isinstance(options, dict) and "kit" in options:
            from pdfmd_kits import selection
            try:
                layers[layer] += selection.parse(options["kit"], layer)
            except selection.SelectionError as error:
                raise SystemExit(f"{where}: kit: {error}")

    add("global", config_options(), "the config file")
    others = [path for path in metadata_files if path not in KIT_METADATA and not is_folder_metadata(path)]
    for path in others:
        if is_global_metadata(path):
            add("preset", metadata_file_yaml(path).get("pdfmd-options"), str(path))
    for directory, data, metadata in reversed(folder_walk(str(md_path.resolve().parent))):
        if data is not None:
            add("folder", data.get("options"), str(directory / "config.yaml"))
        if metadata is not None:
            add("folder", metadata_file_yaml(metadata).get("pdfmd-options"), str(metadata))
    for path in pandoc_metadata_order(others):
        if not is_global_metadata(path):
            add("document", metadata_file_yaml(path).get("pdfmd-options"), str(path))
    add("document", frontmatter_pdfmd_options(md_path), str(md_path))
    return layers


def active_kits(md_path: Path | None, metadata_files: list[Path] | None = None, no_auto: list[str] | None = None) -> list:
    """The kits chosen for this document (ActiveKit, in stack order); [] when nothing selects one. Search is not selection:
    a document that merely loads a kit's package gets none. Costs nothing for a document no layer gives a `kit:`."""
    if md_path is None or yaml is None:
        return []
    # of --no-auto only the searching of kits matters here (find_kit): a kit's own `no-auto:` changes the list a build uses
    # afterwards, and must not make the same choice be made, and warned about, twice
    key = (str(md_path.resolve()), (auto_disabled(no_auto, "kit"), auto_disabled(no_auto, "kpsewhich")),
           len(KIT_CLI) if KIT_CLI is not None else -1)
    if key in ACTIVE_KITS:
        return ACTIVE_KITS[key]
    ACTIVE_KITS[key] = []
    try:
        return _active_kits(md_path, metadata_files, no_auto, key)
    except BaseException:
        ACTIVE_KITS.pop(key, None)
        raise


def _active_kits(md_path: Path, metadata_files: list[Path] | None, no_auto: list[str] | None, key: tuple) -> list:
    if metadata_files is None:
        try:
            found = find_metadata(md_path.parent, None, document_stem=md_path.stem, document=md_path, kits=False)
        except (OSError, ValueError, SystemExit):
            found = None
        metadata_files = [] if found is None or found is AUTO_METADATA_DISABLED else (found if isinstance(found, list) else [found])
    layers = kit_layer_selections(md_path, list(metadata_files))
    if not any(layers.values()) and KIT_CLI is None:
        return ACTIVE_KITS[key]
    from pdfmd_kits import KitError, load_kit, resolve_mode, selection
    try:
        setting = selection.parse_stack_setting(
            KIT_STACK_CLI if KIT_STACK_CLI is not None else first_pdfmd_option(
                md_path, [path for path in metadata_files if path not in KIT_METADATA], "kit-stack"))
    except selection.SelectionError as error:
        raise SystemExit(str(error))
    resolved = []
    for choice in selection.combine(layers, KIT_CLI, setting):
        try:
            found = find_kit(choice.ref, md_path.parent, no_auto, named_only=choice.layer == "folder")
            kit = load_kit(found.path, found.aliases)
            mode = resolve_mode(kit, choice.mode)
        except KitError as error:
            raise SystemExit(f"{md_path.name}: kit `{choice.ref}` (chosen in the {choice.layer}): {error}")
        for warning in kit.warnings:
            print(f"WARN  {warning}", file=sys.stderr)
        resolved.append(ActiveKit(kit, mode, found, choice))
        if VERBOSE_OUTPUT and choice.layer == "command line":        # a KIT line with its file and how to read about it (v3.33.72)
            line = selection.command_line_line(resolved[-1].describe(), kit.name, display_path(kit.path))
            if line:
                print(line)
        elif VERBOSE_OUTPUT:
            print(f"AUTO KIT  {resolved[-1].describe()}")
    ACTIVE_KITS[key] = resolved
    return resolved


def kit_overlay(kit, label: str, mapping: dict) -> Path | None:
    """The kit's inline default metadata as a metadata file in the cache folder (named by its content, written once)."""
    if not mapping or yaml is None:
        return None
    text = yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False)
    from pdfmd_kits import normalise
    path = cache_root() / "kit-metadata" / f"{normalise(kit.name)}-{label}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}.yaml"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, path)
    except OSError as error:
        print(f"WARN  kit {kit.name}: cannot write its default metadata to {path} ({error.strerror or error}); left out", file=sys.stderr)
        return None
    return path


def kit_metadata_files(kits: list) -> list[Path]:
    """The metadata files the kits supply, lowest first: for each kit its defaults, its inline metadata, its mode's defaults, its
    mode's metadata. Each is remembered in KIT_METADATA with the kit's folder."""
    files: list[Path] = []
    for item in kits:
        kit, mode = item.kit, item.mode
        parts = [*kit.defaults, kit_overlay(kit, "kit", kit.metadata),
                 *(mode.defaults if mode else ()), kit_overlay(kit, "mode", mode.metadata if mode else {})]
        for path in parts:
            if path is not None and path not in files:
                KIT_METADATA[path] = kit.folder
                files.append(path)
    return files


# -- Kits: the preamble they write (entry 3du, C3) ----------------------------------------------------------------------
# The kit's lines are one header file, first of all (after the code-wrapping header); the user's own LaTeX follows. What the kit
# and the user's text say twice is settled in copies in the cache folder, never in the user's files: pdfmd_kits.preamble has the
# four outcomes. Ids: KIT-SAME and KIT-MERGE are shown with --verbose, KIT-YIELD is a WARN.
KIT_HEADER_PREFIX = "pdfmd-kit-"


def kit_preamble_kits(document: Path | None, metadata_files: list[Path] | None) -> list:
    return [item for item in active_kits(document, metadata_files, None)
            if item.kit.package or item.kit.latex or (item.mode is not None and item.mode.latex)]


def kit_writes_preamble(document: Path | None, metadata_files: list[Path] | None) -> bool:
    return bool(document is not None and kit_preamble_kits(document, metadata_files))


def header_argument_positions(cmd: list[str]) -> list[tuple[int, bool]]:
    """(index of the file, whether it is the `--include-in-header=FILE` form) of each header file of ``cmd``."""
    found = []
    for index, item in enumerate(cmd):
        if item in ("-H", "--include-in-header") and index + 1 < len(cmd):
            found.append((index + 1, False))
        elif item.startswith("--include-in-header="):
            found.append((index, True))
    return found


# kit_header_insert: lib/pdfmd_kits/locate.py (v3.33.22)


def kit_explicit_sources(document: Path, paths: list[Path], pandoc_options: list[str],
                         metadata_files: list[Path] = ()) -> list[bool]:
    """For each of ``paths`` (header files of a build): whether it was asked for (`-H`, a named `preamble:`), not found by
    discovery. A found one yields to the kit where they contradict; an explicit one stops the build."""
    auto = {path.resolve() for path in ([] if has_header_include_option(pandoc_options) else
                                        find_preambles(document.parent, document.stem, []))}
    named = {path.resolve() for path in frontmatter_extra_preambles(document, metadata_files)}
    flags = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        flags.append(resolved not in auto or resolved in named)
    return flags


# kit_header_settle, kit_cache_tex and kit_header_resolve: lib/pdfmd_kits/locate.py (v3.33.22)


def kit_embedded_preambles(document: Path, metadata_files: list[Path], preamble_files: list[Path] | None) -> list[Path]:
    """The preamble files an assembled or attached source embeds: when a kit writes part of the preamble, the kit's header file
    first and then the found preambles as the build read them (what the kit writes twice settled in them), so a rebuild that
    has no kit gets the same LaTeX in the same order. ``preamble_files`` unchanged when no kit writes a preamble."""
    files = list(preamble_files or [])
    if any(path.name.startswith(KIT_HEADER_PREFIX) for path in files):
        return files
    kits = kit_preamble_kits(document, metadata_files)
    if not kits:
        return files
    explicit = kit_explicit_sources(document, files, [], metadata_files)
    body, texts, _ = kit_header_settle(document, kits, [(path, display_path(path), flag) for path, flag in zip(files, explicit)])
    settled = [kit_cache_tex(f"kit-{path.stem}-", text, 12) if text != read_text_best_effort(path) else path
               for path, text in zip(files, texts)]
    return [kit_cache_tex(KIT_HEADER_PREFIX, body, 16), *settled]


# folder_options_in_force: lib/pdfmd_attach (v3.33.37)


# kit_carried_files: lib/pdfmd_kits/locate.py (v3.33.22)


def package_helper(folder: Path, package: str, no_auto: list[str] | None = None, document: Path | None = None) -> tuple[dict, Path] | None:
    """What a package tells pdfmd about itself: `<package>-pdfmd.yaml` beside its `.sty`, else the same file
    (or a plain `pdfmd.yaml`) in a `pdfmd/` folder there; (its mapping, its path) or None. Keys: `latex-keys:`
    (front-matter key -> the macro it fills), `office:` (defaults of a Word/ODT build, as `<package>-office.yaml`), `lua:` (Lua
    filters besides `<package>.lua`), `draft-skip:` (`commands:`, `spans:` a draft pass need not draw) and `picture-cache:`
    (the names the package uses for the picture cache's protocol).

    The `.sty` that wins may be a lone copy beside the document (TeX's own order), which carries no helper file, and its
    `latex-keys:` would be lost without a word (v3.31.29): the same file is then looked for beside the `.sty` of a selected
    kit, then of the installed copy kpsewhich finds; the path returned is the one that gave it. `--no-auto kit` and
    `--no-auto kpsewhich` (bare `--no-auto` too) take those places off."""
    found = read_package_helper(folder, package)
    if found or yaml is None:
        return found
    others: list[Path] = [] if auto_disabled(no_auto, "kit") else kit_package_folders(package, document)
    if not auto_disabled(no_auto, "kpsewhich"):
        installed = installed_package_folder(package)
        if installed:
            others.append(installed)
    for other in others:
        if other != folder.resolve():
            found = read_package_helper(other, package)
            if found:
                return found
    return None


# office_package_folders: lib/pdfmd_office/build.py (v3.33.27)


def header_includes_texts(md_path: Path, metadata_files: list[Path]) -> list[str]:
    """The LaTeX a document gets from `header-includes:` -- its own front matter's and its metadata files' (a package may
    be loaded there instead of in a preamble file: a pre-lab's metadata does that)."""
    texts: list[str] = []

    def collect(value) -> None:
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    for item in metadata_files:
        collect(metadata_file_yaml(item).get("header-includes"))
    try:
        own = document_header_includes(md_path.read_text(encoding="utf-8-sig"))
    except OSError:
        own = None
    if own:
        texts.append(own)
    return texts


def office_packages(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None = None
                    ) -> list[tuple[Path, str, list[str]]]:
    """(folder, package name) of each LaTeX package the document's preamble loads that is not part of the TeX
    distribution: a package may ship its Word support beside its .sty (`<name>-office.lua`,
    `<name>-office.yaml`, `<name>-reference.dotx`), found here."""
    chosen = [(item.kit.folder, item.kit.package, list(item.mode.options) if item.mode else [])
              for item in active_kits(md_path, metadata_files, None) if item.kit.package]
    if discovery_disabled(no_auto, "preamble"):
        return chosen
    texts = []
    for item in find_preambles(md_path.parent, md_path.stem, []):
        try:
            texts.append(item.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    texts += header_includes_texts(md_path, metadata_files)
    loaded: list[tuple[str, list[str]]] = []
    for match in re.finditer(r"\\(?:usepackage|RequirePackage)(?:\[([^\]]*)\])?\{([^}]+)\}", "\n".join(texts)):
        options = [part.strip() for part in (match.group(1) or "").split(",") if part.strip()]
        loaded += [(part.strip(), options) for part in match.group(2).split(",") if part.strip()]
    located = kpsewhich_locate(sorted({package + ".sty" for package, _ in loaded}))
    # beside the document first, as TeX itself looks (a restored source carries its package there)
    here = [md_path.parent, *(item.parent for item in metadata_files), md_path.parent / ACCESSORY_DIRNAME]
    found: list[tuple[Path, str, list[str]]] = []
    for package, options in loaded:
        path = next((folder / f"{package}.sty" for folder in here if (folder / f"{package}.sty").is_file()),
                    located.get(package + ".sty"))
        if path and "texmf-dist" not in str(path) and "/texlive/" not in str(path):
            folder = path.resolve().parent
            if not any(item[0] == folder and item[1] == package for item in found):
                found.append((folder, package, options))
    for entry in chosen:                                       # a kit loads its package itself; a copy the preamble resolved stands
        if not any(item[1] == entry[1] for item in found):
            found.append(entry)
    return found


# office_defaults_sources: lib/pdfmd_office/build.py (v3.33.27)


# find_office_profile and find_reference_doc: lib/pdfmd_office/build.py (v3.33.27)


# OfficeArguments, office_properties and office_finish: lib/pdfmd_office/build.py (v3.33.27)


# run_office_pandoc, build_office_pandoc, describe_fragment, print_office_check and check_docx_command: lib/pdfmd_office/build.py (v3.33.27)


# `picture_target`, `picture_build`, `picture_sources`, `picture_page_folder`, `picture_targets`, `picture_one`,
# `multi_target_command` and `picture_command` (with `PICTURE_OPTIONS` and `TARGET_ONLY_OPTIONS`) live in
# `pdfmd_crop.targets` (v3.33.11); the stand-ins are in the binding block above.


# (the --check discovery and command moved to lib/pdfmd_check/command.py, v3.33.17; `check_command` is a stand-in in the binding block)


# office_render_fragments, office_convert_asset and init_reference: lib/pdfmd_office/build.py (v3.33.27)


def config_report(init: bool = False, document: Path | None = None, no_auto=None, metadata_request=None) -> bool:
    """--show-config / --init-config."""
    path = config_path()
    if path is None:
        print("The config file is switched off (PDFMD_CONFIG is empty).")
        return deferred("pdfmd_metadata", "metadata_sources")(document, no_auto, metadata_request) if not init else True
    if init:
        if path.exists():
            print(f"{path} exists already; left alone.")
        else:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(path, CONFIG_TEMPLATE)
            except OSError as error:
                print(f"Could not write {path}: {error}", file=sys.stderr)
                return False
            print(f"Wrote {path} (every setting is commented out; edit it).")
        return True
    print(f"config file: {path} ({'present' if path.is_file() else 'not there: pdfmd --init-config writes one'})")
    data = load_config()
    for key in CONFIG_KEYS:
        if key in data:
            print(f"  {key}: {data[key]}")
    if config_root().is_dir():
        print(f"state kept beside it: {config_root()}")
    return deferred("pdfmd_metadata", "metadata_sources")(document, no_auto, metadata_request)


def migrate_state(old: Path, new: Path) -> None:
    """Move a file pdfmd used to keep in the cache folder (where cleaning it loses it) to ``new``."""
    try:
        if not new.exists() and old.is_file():
            new.parent.mkdir(parents=True, exist_ok=True)
            new.write_bytes(old.read_bytes())
            old.unlink()
    except OSError:
        pass


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
    use_tex_install()
    use_found_tools()


TEX_ENGINE_NAMES = ("lualatex", "xelatex", "pdflatex", "latexmk")
TEX_FOUND_AT: Path | None = None             # the TeX folder use_tex_install() put on PATH, for --doctor and --verbose


def tex_install_patterns(system: str | None = None, environ: dict | None = None) -> list[str]:
    """Where TeX Live and MiKTeX put their programs when the installer did not (or could not) add them to PATH:
    glob patterns, the year of a TeX Live (`bin/windows`, `bin/x86_64-linux`) matched by `*`, newest first once sorted."""
    system = (system or platform.system()).lower()
    environ = os.environ if environ is None else environ
    patterns: list[str] = []
    if system == "windows":
        drive = environ.get("SystemDrive", "C:")
        program_files = [environ.get(name) for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
        for root in dict.fromkeys([f"{drive}\\texlive", *(f"{base}\\texlive" for base in program_files if base),
                                   str(Path(environ.get("USERPROFILE", "~")).expanduser() / "texlive")]):
            patterns.append(str(Path(root) / "*" / "bin" / "*"))
        miktex = [str(Path(environ["LOCALAPPDATA"]) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64")] \
            if environ.get("LOCALAPPDATA") else []
        patterns += miktex + [str(Path(base) / "MiKTeX*" / "miktex" / "bin" / "x64") for base in program_files if base]
    else:
        patterns += ["/usr/local/texlive/*/bin/*", str(Path("~/texlive").expanduser() / "*" / "bin" / "*"),
                     "/Library/TeX/texbin", "/usr/texbin"]
    return patterns


def find_tex_directory(patterns: list[str]) -> Path | None:
    """The first (newest year first) folder among the glob patterns that holds a TeX engine program."""
    import glob
    found: list[Path] = []
    for pattern in patterns:
        found += [Path(match) for match in glob.glob(pattern) if Path(match).is_dir()]
    for folder in sorted(found, key=lambda path: str(path), reverse=True):
        if any((folder / (name + suffix)).is_file() for name in TEX_ENGINE_NAMES for suffix in ("", ".exe")):
            return folder
    return None


def use_tex_install() -> None:
    """A TeX that is installed but not on PATH (TeX Live's installer on Windows can leave it off, a shell started before
    the install does not have it yet) is used all the same: its folder goes behind PATH, for pdfmd's own runs.
    `PDFMD_TEX_BIN` names a folder for an install in an unusual place. Nothing is done when a TeX engine is on PATH."""
    global TEX_FOUND_AT
    if any(shutil.which(name) for name in TEX_ENGINE_NAMES):
        return
    chosen = os.environ.get("PDFMD_TEX_BIN", "").strip()
    folder = find_tex_directory([chosen]) if chosen else None
    folder = folder or find_tex_directory(tex_install_patterns())
    if folder is None:
        return
    TEX_FOUND_AT = folder
    os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), str(folder)]).strip(os.pathsep)


# TYPST_REPOSITORY, TYPST_TARGETS, typst_asset_name, github_release_asset, download_file, extract_executable and
# install_typst: lib/pdfmd_install/__init__.py (v3.33.35)


# -- KaTeX: math WeasyPrint can print (v3.28.11) ------------------------------------------------------------------------
# WeasyPrint does not draw MathML. KaTeX, run with node before WeasyPrint, writes each formula as HTML set in its own
# fonts, which WeasyPrint prints as a browser does (pdfmd_lua/weasyprint.lua runs pdfmd_lua/katex.cjs). `pdfmd --install
# math:katex` puts this release's files in data_root()/katex/<version> (the npm package, checked against the SHA-256
# below: the script, the stylesheet, the fonts, mhchem, the licence) and, when there is no node on PATH, node's own
# release for this machine into pdfmd's tools folder, as for Typst.
KATEX_VERSION = "0.18.9"
KATEX_PACKAGE = f"https://registry.npmjs.org/katex/-/katex-{KATEX_VERSION}.tgz"
# KATEX_SHA256, KATEX_KEPT, NODE_DIST and NODE_TARGETS: lib/pdfmd_install/__init__.py (v3.33.35)


def katex_folder() -> Path | None:
    """The KaTeX files pdfmd installed: this release's, else the newest other one there (an older pdfmd's)."""
    root = data_root() / "katex"

    def complete(folder: Path) -> bool:
        return (folder / "katex.min.js").is_file() and (folder / "katex.min.css").is_file()

    if complete(root / KATEX_VERSION):
        return root / KATEX_VERSION
    try:
        found = [folder for folder in root.iterdir() if complete(folder)]
    except OSError:
        return None
    return max(found, key=lambda folder: tuple(int(part) for part in re.findall(r"\d+", folder.name)), default=None)


def katex_runtime() -> tuple[str, Path] | None:
    """(node, the KaTeX folder) when math in a WeasyPrint PDF can be typeset, else None."""
    folder = katex_folder()
    node = which("node") if folder is not None else None
    return (node, folder) if node else None


# node_install_hint, node_asset_name, install_node, unpack_katex, katex_works and install_katex: lib/pdfmd_install/__init__.py (v3.33.35)


# -- MathJax for WeasyPrint (v3.28.46) ---------------------------------------------------------------------------------
# MathJax 4 typesets the math of a WeasyPrint PDF first, KaTeX takes the formulas it cannot read, and what neither reads
# stays text. `pdfmd --install math:mathjax` puts this release's files in data_root()/mathjax/<version>/node_modules/@mathjax
# (the npm packages below, each checked against its SHA-256 pinned here: the bundle's TeX input and CHTML output, and the
# STIX Two math font, which goes with pdfmd's default body font), and node as for KaTeX. pdfmd_lua/mathjax.cjs renders;
# Apache-2.0. Only STIX Two is offered: MathJax's New Computer Modern, TeX Gyre Termes, TeX Gyre Pagella and DejaVu fonts
# were measured too (the margin that undoes WeasyPrint's misplacing is the font's ascent-descent excess plus 0.03em in
# each, as in STIX Two), but a tall delimiter built from pieces (`\left[` over three rows) came out broken in WeasyPrint,
# so they wait for a fix of that. A font is one entry in each of the three tables below.
MATHJAX_VERSION = "4.1.3"
MATHJAX_FONT_SHA256 = {"stix2": "664c8c40d739a231016cd6108cb6401166151772913e82b802bdd4b64812acf5"}
MATHJAX_DEFAULT_FONT = "stix2"
# the text font -> the MathJax math font that goes with it (a body that is not here gets STIX Two's, sized to its x-height)
MATHJAX_FONT_FOR = {"stix two text": "stix2"}
# MATHJAX_REGISTRY, MATHJAX_SOURCE_SHA256, MATHJAX_FONT_SIZES, MATHJAX_BUNDLE_KEPT, MATHJAX_BUNDLE_FOLDERS, MATHJAX_BUNDLE_INPUT and
# mathjax_package_url: lib/pdfmd_install/__init__.py (v3.33.35)


def mathjax_font_package(font: str) -> str:
    return f"mathjax-{font}-font"


def mathjax_folder() -> Path | None:
    """The MathJax files pdfmd installed: this release's, else the newest other one there (an older pdfmd's)."""
    root = data_root() / "mathjax"

    def complete(folder: Path) -> bool:
        return (folder / "node_modules" / "@mathjax" / "src" / "bundle" / "node-main.cjs").is_file() and bool(
            mathjax_fonts(folder))

    if complete(root / MATHJAX_VERSION):
        return root / MATHJAX_VERSION
    try:
        found = [folder for folder in root.iterdir() if complete(folder)]
    except OSError:
        return None
    return max(found, key=lambda folder: tuple(int(part) for part in re.findall(r"\d+", folder.name)), default=None)


def mathjax_fonts(folder: Path) -> list[str]:
    """The math fonts installed in a MathJax folder, in the order MATHJAX_FONT_SHA256 lists them."""
    modules = folder / "node_modules" / "@mathjax"
    return [font for font in MATHJAX_FONT_SHA256 if (modules / mathjax_font_package(font) / "chtml.js").is_file()]


def mathjax_runtime() -> tuple[str, Path] | None:
    """(node, the MathJax folder) when math in a WeasyPrint PDF can be typeset by MathJax, else None."""
    folder = mathjax_folder()
    node = which("node") if folder is not None else None
    return (node, folder) if node else None


def mathjax_font_for(body_font: str | None, installed: list[str]) -> tuple[str, bool] | None:
    """(the MathJax font to use, whether it is the one that goes with the body font): the table's font for the body when
    it is installed, else STIX Two's (the widest fit for a serif body), else the first one there; None with none."""
    wanted = MATHJAX_FONT_FOR.get((body_font or "").casefold())
    if wanted in installed:
        return wanted, True
    if MATHJAX_DEFAULT_FONT in installed:
        return MATHJAX_DEFAULT_FONT, False
    return (installed[0], False) if installed else None


# unpack_npm, mathjax_keeps_source, mathjax_keeps_font, install_mathjax_files, mathjax_works, ensure_node and install_mathjax;
# the installers of D2 and Graphviz, Calibre and Tectonic, with their banner comments: lib/pdfmd_install/__init__.py (v3.33.35)


# install_kind, uninstall_kind, KIT_SOURCES_DEFAULT and kit_install_settings: lib/pdfmd_install/__init__.py (v3.33.35)


# install_kits: lib/pdfmd_install/__init__.py (v3.33.35)


# install_fonts: lib/pdfmd_install/__init__.py (v3.33.35)


# tessdata_environment: lib/pdfmd_routing/__init__.py (v3.33.25)


# install_extra: lib/pdfmd_install/__init__.py (v3.33.35)


# setup_hint_state, maybe_hint_setup, flag_topics and flag_names: lib/pdfmd_setup/command.py (v3.33.21)


SETUP_HEADER = ("# pdfmd's global config, written by `pdfmd --setup` (edit it by hand, or run that again).\n"
                "# Precedence: command line > the document's `pdfmd-options:` > its metadata files > this file.\n")


# FOLDER_HEADER, FOLDER_METADATA_HEADER and METADATA_HEADER, setup_sources and setup_command: lib/pdfmd_setup/command.py (v3.33.21)


# -- pdfmd --doc (v3.29.26): the documents of this version, offline ----------------------------------------------------
# The build copies README.md, recipes.md, agents.md and CHANGELOG.md into the pdfmd_docs package (setup.py), so an installed pdfmd
# has the documents of its own version; in a checkout they are the originals. `pdfmd --doc` lists them, `--doc NAME` shows one
# (the Markdown when the output is not a terminal or with --print, else a web page it opens), `--doc NAME SECTION` a part of
# one (a number counts the `##` headings), `--doc search WORD` finds the headings and lines that have the word, `--path` says
# where the file is.
# DOCUMENTS, DOC_URL, document_file, document_headings, document_section, search_documents, render_document and doc_command: lib/pdfmd_docs/reader.py (v3.33.9)


FENCE_LINE_RE = re.compile(r"\s*(`{3,}|~{3,})(.*)$")


def fence_after(fence: str, line: str) -> str:
    """The code fence that is open after `line` (its run of backticks or tildes, "" for none), given `fence` open before it. As
    in CommonMark: a backtick fence does not open on a line whose text after the run holds a backtick (``` ```` ```{=calc} ```` line``
    is a paragraph), and a fence closes only on a run of the same character, at least as long, with nothing after it."""
    found = FENCE_LINE_RE.match(line)
    if not found:
        return fence
    run, rest = found.groups()
    if not fence:
        return "" if run[0] == "`" and "`" in rest else run
    return "" if run[0] == fence[0] and len(run) >= len(fence) and not rest.strip() else fence


def native_prompt_state() -> Path:
    path = config_root() / "native-prompt-dismissed"
    migrate_state(cache_root() / "native-prompt-dismissed", path)
    return path


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
    """Return whether the caller already explicitly supplied Pandoc's -H option (also attached: -Hmine.tex)."""
    return any(option in {"-H", "--include-in-header"}
               or option.startswith(("--include-in-header=", "-H"))
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


# is_latex_preamble and top_level_tikzpicture: lib/pdfmd_tex (v3.33.36)


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


def document_preambles(md_path: Path, pandoc_options: list[str], no_auto: list[str] | None,
                       metadata_files: list[Path] = ()) -> list[Path]:
    """The preambles of a document: the ones found beside it (not for off or explicit-only) and the ones it names (not for off)."""
    found = [] if discovery_disabled(no_auto, "preamble") else find_preambles(md_path.parent, md_path.stem, pandoc_options)
    named = [] if auto_disabled(no_auto, "preamble") else frontmatter_extra_preambles(md_path, metadata_files)
    return deferred("pdfmd_metadata", "with_parent_preambles")(found, md_path, pandoc_options, no_auto, metadata_files) + named


class AutoLog:
    """What pdfmd decided for the build in hand, shown in three lines (v3.28.16) rather than one a decision.

    ``FOUND`` is what it picked up from the folder (metadata files, a preamble, a Lua filter, the parts),
    ``DEFAULTS`` what it applied because nothing said otherwise (the global metadata of ``pdfmd --setup``, the
    margin, the fonts, the packages it adds), and ``AUTO: KINDS`` the decisions that have no short form. A line is
    cut at ``WIDTH`` characters ("+N more (--verbose)"): the screen is not for the catalogue. ``--verbose`` prints
    each decision with its reason, as it happens, as before. In a batch a line equal to the one before it is not
    printed again."""

    WIDTH = 110                          # the width of a line when the output is not a terminal
    HEADINGS = ("FOUND", "DEFAULTS")
    # A decision that is one of a kind per build (the later one replaces the earlier); the others are listed each
    ONE_OF = frozenset({"PARTS", "MARGIN", "MAINFONT", "MATHFONT", "MONOFONT"})
    # The order a line lists its items in, whichever was found first: the files, then the parts; the global
    # metadata, then margin, fonts, packages
    RANK = {"YAML": 0, "TEX": 1, "LUA": 2, "PARTS": 3, "GLOBAL": 0, "MARGIN": 1, "MAINFONT": 2, "MATHFONT": 2.5, "MONOFONT": 3,
            "TEXPACKAGES": 4, "TITLE": 5, "TABLEWIDTH": 6, "SETTINGS": 0.5}

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], tuple[int, str]] = {}
        self.other: list[str] = []
        self.shown: dict[str, str] = {}
        self.dedupe = False
        self.quiet = False

    def snapshot(self) -> tuple[dict, list, dict]:
        return dict(self.items), list(self.other), dict(self.shown)

    def restore(self, saved: tuple[dict, list, dict]) -> None:
        self.items, self.other, self.shown = dict(saved[0]), list(saved[1]), dict(saved[2])

    def reset(self, dedupe: bool = False) -> None:
        self.items.clear()
        self.other.clear()
        self.shown.clear()
        self.dedupe = dedupe

    @staticmethod
    def classify(kind: str, detail: str) -> tuple[str, str] | None:
        """(heading, short text) of a decision that has a short form, from the words it was announced with."""
        if kind == "PARTS":
            found = re.search(r"(\d+) (more file|part)s?\b", detail)
            return (("FOUND", f"{found.group(1)} {found.group(2)}{'s' if found.group(1) != '1' else ''}") if found else None)
        if kind == "LUA":
            return "FOUND", Path(detail).name or detail
        if kind == "MARGIN":
            found = re.search(r"no geometry/margin set; using geometry:margin=(\S+)", detail)
            return ("DEFAULTS", f"margin {found.group(1)}") if found else None
        if kind == "MAINFONT":
            found = (re.search(r"no mainfont set; using (.+)$", detail)
                     or re.search(r": (.+?) instead of ", detail))
            return ("DEFAULTS", f"font {found.group(1)}") if found else None
        if kind == "MATHFONT":
            found = re.search(r"no mathfont set; using (.+?) to go with ", detail)
            return ("DEFAULTS", f"math in {found.group(1)}") if found else None
        if kind == "MONOFONT":
            found = re.search(r"no monofont set; using (.+?) on ", detail)
            return ("DEFAULTS", f"code in {found.group(1)}") if found else None
        if kind == "TEXPACKAGES":
            found = re.match(r"loads (.+?) unless the preamble does", detail)
            return ("DEFAULTS", f"packages {found.group(1)}") if found else None
        if kind == "TITLE":
            return "DEFAULTS", "title from heading"
        if kind == "TABLEWIDTH":
            found = re.search(r"(\d+) wide tables?", detail)
            count = int(found.group(1)) if found else 1
            return "DEFAULTS", f"balanced {count} wide table{'s' if count != 1 else ''}"
        return None

    def record(self, kind: str, detail: str, verbose: bool, heading: str | None = None,
               short: str | None = None) -> None:
        """One decision: printed at once with ``verbose``, else kept for ``flush``."""
        if verbose:
            print(f"AUTO {kind}  {detail}")
            return
        record_note(f"AUTO {kind}  {detail}")           # the record has it whatever --verbose said
        if heading is None:
            found = self.classify(kind, detail)
            heading, short = found if found else (None, None)
        if heading is None:
            if kind not in self.other:
                self.other.append(kind)
            return
        self.items[(heading, kind if kind in self.ONE_OF else short)] = (self.RANK.get(kind, 9), short)

    @staticmethod
    def file_line(kind: str, path: Path) -> str:
        """The AUTO line of a file pdfmd picked up."""
        if kind == "YAML" and is_global_metadata(path):
            return (f"AUTO {kind}  {display_path(path)}  "
                    + ("(the global metadata of pdfmd --setup)" if preset_name(path) == "default"
                       else f"(the preset {preset_name(path)} of pdfmd --setup)"))
        return f"AUTO {kind}  {display_path(path)}"

    def record_file(self, kind: str, path: Path, verbose: bool) -> None:
        """A file pdfmd picked up (AUTO YAML / AUTO TEX): FOUND, but the global metadata is a default."""
        line = self.file_line(kind, path)
        if verbose:
            print(line)
            return
        record_note(line)
        if kind == "YAML" and is_global_metadata(path):
            self.items[("DEFAULTS", "global")] = (self.RANK["GLOBAL"], "global metadata" if preset_name(path) == "default"
                                                  else f"preset {preset_name(path)}")
        else:
            self.items[("FOUND", f"{kind} {path}")] = (self.RANK[kind], display_path(path))

    def width(self) -> int:
        """The line width: the terminal's own when stdout is one (v3.28.18), else ``WIDTH``."""
        try:
            if sys.stdout.isatty():
                return max(60, shutil.get_terminal_size((self.WIDTH, 24)).columns)
        except (OSError, ValueError, AttributeError):
            pass
        return self.WIDTH

    @staticmethod
    def grouped(parts: list[str]) -> list[str]:
        """``metadata/a.yaml``, ``metadata/b.tex`` -> ``metadata: a.yaml + b.tex`` (v3.28.18): files that share a folder
        are listed under it once, in the place of the first. A folder with one file keeps its path."""
        folders: dict[str, list[str]] = {}
        for part in parts:
            if re.search(r"[/\\]", part):
                folder, name = re.split(r"[/\\](?=[^/\\]*$)", part)
                folders.setdefault(folder, []).append(name)
        done: set[str] = set()
        result: list[str] = []
        for part in parts:
            if re.search(r"[/\\]", part):
                folder, _ = re.split(r"[/\\](?=[^/\\]*$)", part)
                if len(folders[folder]) > 1:
                    if folder not in done:
                        done.add(folder)
                        result.append(f"{folder}: " + " + ".join(folders[folder]))
                    continue
            result.append(part)
        return result

    def fit(self, heading: str, parts: list[str]) -> str:
        prefix = f"{heading:<10}"
        line = prefix + ", ".join(parts)
        width = self.width()
        if len(line) <= width:
            return line
        for count in range(len(parts) - 1, 0, -1):
            cut = prefix + ", ".join(parts[:count]) + f", +{len(parts) - count} more (--verbose)"
            if len(cut) <= width:
                return cut
        return prefix + parts[0] + f", +{len(parts) - 1} more (--verbose)"

    def flush(self) -> None:
        """Print what was recorded since the last flush, FOUND, DEFAULTS, then the decisions without a short form."""
        if self.quiet:
            self.items.clear()
            self.other.clear()
            return
        for heading in self.HEADINGS:
            parts = [text for _, text in sorted((value for (group, _), value in self.items.items() if group == heading),
                                                key=lambda value: value[0])]
            if parts:
                if heading == "FOUND" and str(config_options().get("found-style", "group")).strip().casefold() != "path":
                    parts = self.grouped(parts)
                line = self.fit(heading, parts)
                if not (self.dedupe and self.shown.get(heading) == line):
                    print(line)
                self.shown[heading] = line
        if self.other:
            line = f"AUTO: {' '.join(self.other)}. Use --verbose to see in full"
            if not (self.dedupe and self.shown.get("AUTO") == line):
                print(line)
            self.shown["AUTO"] = line
        self.items.clear()
        self.other.clear()


AUTO_LOG = AutoLog()


def announce_preambles(preambles: list[Path]) -> None:
    for preamble in preambles:
        AUTO_LOG.record_file("TEX", preamble, VERBOSE_OUTPUT)
    if len(preambles) > 1:
        print("WARN  Multiple preambles discovered; later files may override earlier definitions.",
              file=sys.stderr)


# wrap_latex_header_includes: lib/pdfmd_tex (v3.33.36)


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


RAW_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*\{=([\w+-]+)\}[ \t]*\n(.*?)\n[ \t]*\1[ \t]*$",
                          re.DOTALL | re.MULTILINE)
RAW_INLINE_RE = re.compile(r"`([^`\n]+)`\{=([\w+-]+)\}")


def raw_latex_only(text: str) -> str:
    """What LaTeX gets of a `header-includes:` item written with Pandoc's raw attribute (v3.27.19): a ```{=latex} block
    or `...`{=latex} span without its fence, a block or span for another format (html, typst ...) dropped, as Pandoc's
    LaTeX writer does. A header file pdfmd builds from the item would otherwise hand LaTeX the backticks."""
    def keep(match: re.Match, body: int, form: int) -> str:
        return match.group(body) if match.group(form).lower() in ("latex", "tex") else ""
    text = RAW_FENCE_RE.sub(lambda match: keep(match, 3, 2), text)
    return RAW_INLINE_RE.sub(lambda match: keep(match, 1, 2), text)


def document_header_includes(text: str) -> str | None:
    """Return the LaTeX in a document's own ``header-includes:`` block (raw_latex_only of each item).

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
    anyway. A real YAML parse (installed PyYAML or the bundled fallback;
    see `frontmatter_pdfmd_options`) handles the
    sequence shape correctly, one raw LaTeX line per list item, joined with
    newlines, matching how Pandoc's own template concatenates such a list.
    Falls back to the original block-scalar-only regex when PyYAML isn't
    available -- worse than a real parse, but not a new limitation; a
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
                    lines_out = [raw_latex_only(str(item)).strip() for item in value if item is not None]
                    return "\n".join(line for line in lines_out if line).strip() or None
                if isinstance(value, str):
                    return raw_latex_only(value).strip() or None
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
        block = raw_latex_only(dedent("".join(lines[start:index]))).strip()
        return block or None
    return None


# package_latex_keys (with the comment above it) and document_latex_definitions: lib/pdfmd_tex (v3.33.36)


@contextmanager
def document_header_file(md_path: Path, active: bool, metadata_files: list[Path] | None = None,
                         no_auto: list[str] | None = None) -> Iterator[Path | None]:
    """Yield a temporary .tex holding the document's own preamble additions."""
    if not active and kit_writes_preamble(md_path, metadata_files):
        active = True                                    # the kit's header file would drop the document's own header-includes
    if not active:
        yield None
        return
    try:
        definitions = document_latex_definitions(md_path, metadata_files, no_auto)
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



# -- Discovered Lua filters: noticed, not blocked (v3.26.11) -----------------------------------------------------


@contextmanager
def table_width_filter() -> Iterator[Path]:
    """pdfmd_lua/table_width.lua, for --lua-filter. The filter appends a line to PDFMD_TABLEWIDTH_LOG for every table
    it resizes; tablewidth_note() reads that back (v3.28.18)."""
    log = Path(tempfile.gettempdir()) / f"pdfmd-tablewidth-{os.getpid()}.log"
    log.unlink(missing_ok=True)
    os.environ["PDFMD_TABLEWIDTH_LOG"] = str(log)
    with lua_filter_file(TABLE_WIDTH_LUA_FILTER, "pdfmd-tablewidth-") as path:
        yield path


def tablewidth_note(md_path, note) -> None:
    """Say that the table-width filter resized tables in the build just made, once (AUTO TABLEWIDTH), and forget it."""
    name = os.environ.get("PDFMD_TABLEWIDTH_LOG")
    if not name:
        return
    log = Path(name)
    try:
        seen = set(log.read_text(encoding="utf-8").split())
        log.unlink(missing_ok=True)
    except OSError:
        return
    count = sum(1 for mark in seen if not mark.endswith("w"))
    widened = sum(1 for mark in seen if mark.endswith("w"))
    if count:
        note("TABLEWIDTH", f"{md_path}: {count} wide table{'s' if count != 1 else ''} had no column widths (or "
                           "`column-widths: force` is set); pdfmd balanced the columns (--no-auto tablewidth stops it)")
    if widened:
        note("TABLEWIDTH", f"{md_path}: {widened} table{'s' if widened != 1 else ''} had a column too narrow for its "
                           "longest word; pdfmd widened it and took the room from the others (`column-widths: keep` "
                           "leaves the widths as written)")


# -- Script-aware font fallback (v3.23.0) ----------------------------------------
# The main font cannot draw everything a multilingual document says (STIX Two Text
# has no Kazakh Cyrillic, no Arabic, no Han). pdfmd_unicode finds what is missing
# by reading the fonts' own character tables, picks an installed font per script,
# and this turns the result into a preamble plus a Lua filter that sets each run
# of such text in its font. LaTeX engines that load fonts by name (lualatex,
# xelatex) only; HTML and Typst do their own per-character fallback, and
# pdfmd_unicode is optional (the module simply is not there in a lone pdfmd.py).
# A document that has set up its own scripts (ucharclasses, \newfontfamily, xeCJK,
# \babelfont, a font fallback variable) keeps its own way: --no-auto unicode
# switches this off, and `pdfmd-options: {unicode: true}` forces it on regardless.
# CODE_FONTS_TYPST, CODE_FONTS_HTML, EMOJI_FAMILIES and UNICODE_ENGINES: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)
_FONT_INDEX = None


_MANAGED_INDEX = None


# font_args: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)


# unicode_code_text: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)


# unicode_forced: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)


FALLBACK_CLI: str | None = None
MISSING_CLI: str | None = None


# managed_fonts_css, check_fonts, describe_code_points and script_fallback: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)


# latin_candidates, cyrillic_candidates, strip_lookup_suffix, find_wildcard_markdown, lookup_key, lookup_query_keys, LookupAmbiguous,
# lookup_field_matches, rank_lookup, lookup_fields, priority_enabled, source_markdown and document_priority, with LOOKUP_MIN_PREFIX,
# LOOKUP_HEAD_BYTES, LOOKUP_TIERS, LOOKUP_FIELD_WORDS and GENERATED_MARKDOWN_ENDINGS: lib/pdfmd_lookup/__init__.py (v3.33.20)


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


# Romanization packs beyond Cyrillic (see pdfmd_unicode/translit.py): none unless asked for with
# --translit / PDFMD_TRANSLIT. Cyrillic is built in and on, unless `--translit none` says otherwise.
TRANSLIT_PACKS: frozenset[str] = frozenset()
TRANSLIT_CYRILLIC = True


# HEADING_FIELD_WORDS: lib/pdfmd_parts/__init__.py (v3.33.30)


# --- Which document bare `pdfmd` builds (v3.32.9, entry 3eu) ---------------------------------------------------------------
#
# Bare `pdfmd` (and `pdfmd '#section'`) in a folder with several Markdown files used to stop with a list. Now the documents are
# ranked (pdfmd_ranking has the rules, pure): a document's own `priority:` (a number, or a word such as `draft`, `final`, `never`),
# the names of its siblings (`report.final.md` over `report.md` over `report_draft.md`) and, for equal tops, the newest file. An
# exact name (`pdfmd report`) is untouched: it is the override. `--no-auto priority` brings the old list-and-stop back.

NO_AUTO_CLI: list[str] | None = None    # --no-auto as given (set in main): the command line's layer of priority_enabled()

# ranking_inherit_off, read_ranking_file, ranking_of_options, ranking_for_document, ranking_layers, ranking_clashes, bare_ranking,
# priority_candidates and which_command, with RANKING_FILE and RANKING_DOCUMENT_KEYS: lib/pdfmd_ranking/choice.py (v3.33.19)


# serve_main_document, serve_discovered, serve_live_filters, serve_core, serve_command and api_command: lib/pdfmd_serve/commands.py (v3.33.7)


def has_yaml_frontmatter(text: str) -> bool:
    """Whether Pandoc's Markdown reader finds a YAML metadata block at the top of ``text`` (v3.32.4: it used to be only
    "the first line is ``---``", so a file that opens with a thematic break counted).

    Pandoc's rule, measured with 3.13: blank lines may come first; then a line of three dashes (trailing spaces allowed)
    followed by a NON-BLANK line, and a later line of ``---`` or ``...`` that closes it. ``---`` straight after ``---``
    is an empty block, which counts (the documented way to ask for Pandoc's reader). ``---`` then a blank line is a
    horizontal rule, and so is an opening line that nothing closes."""
    lines = text.lstrip("﻿").splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start + 1 >= len(lines) or lines[start].rstrip() != "---" or not lines[start + 1].strip():
        return False
    return any(line.rstrip() in ("---", "...") for line in lines[start + 1:])


# Text tables Pandoc does not read as tables (v3.31.47-52, entry 3el): ASCII tables without the inner `+` of a grid table
# (what chat models write for "a plain-text table", lazy forms too), box-drawing tables, psql and MySQL console output,
# Org-mode tables (`|---+---|`) and `|` lines with no separator row.
# pdfmd_tables/ascii.py turns them into pipe tables, in memory (a temporary copy, the file is never touched). pdfmd-options: table-ascii: repair (the default, one WARN per table) | note (leave
# it, say so) | off.
TABLE_ASCII_MODES = ("repair", "note", "off")
ORG_CAPTION_RE = re.compile(r"^ {0,3}#\+CAPTION(?:\[[^\]]*\])?:", re.MULTILINE | re.IGNORECASE)


def table_ascii_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """The `table-ascii` option (documented above), checked: a word that is not one of the choices stops the build."""
    value = first_pdfmd_option(md_path, metadata_files, "table-ascii")
    if value is None:
        return "repair"
    word = {True: "repair", False: "off"}.get(value, str(value).strip().casefold())
    if word not in TABLE_ASCII_MODES:
        raise SystemExit(f"pdfmd-options table-ascii: {value!r} is not one of {', '.join(TABLE_ASCII_MODES)}")
    return word


def repair_ascii_text(text: str, mode: str, label: str) -> str:
    """``text`` with its ASCII tables turned into pipe tables (mode `repair`), or unchanged with a NOTE for each (`note`);
    ``label`` names the file in the messages. Nothing to say, and nothing done, when there is no such table."""
    if mode == "off":
        return text
    try:
        from pdfmd_tables.ascii import repair_ascii_tables
    except ImportError:
        return text
    fixed, repairs = repair_ascii_tables(text)
    for repair in repairs:
        if repair.kind == "extras":          # a pipe table that was fine: only the `#+` lines around it were dealt with
            if mode != "note":
                for problem in repair.problems:
                    print(f"WARN  table-ascii: {label}, line {repair.line}: {problem}")
            continue
        shape = f"{repair.columns} columns, {repair.rows} row{'s' if repair.rows != 1 else ''}"
        if mode == "note":
            print(f"NOTE  table-ascii: {label}, line {repair.line}: {repair.what} ({shape}) that Pandoc does not read as a "
                  "table; pdfmd-options: table-ascii: repair rewrites it as a pipe table, off ends this note")
            continue
        print(f"WARN  table-ascii: {label}, line {repair.line}: {repair.what} was read as a pipe table ({shape}); "
              "pdfmd-options: table-ascii: off keeps it as written")
        for problem in repair.problems:
            print(f"WARN  table-ascii: {label}, line {repair.line}: {problem}")
    return text if mode == "note" else fixed


def frontmatter_value(md_path: Path, key: str) -> str | None:
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    match = re.search(rf"^{re.escape(key)}\s*:\s*(.*?)\s*$", front_matter.group(1), re.MULTILINE)
    return match.group(1).strip().strip("'\"") if match else None


def metadata_file_yaml(path: Path) -> dict:
    """Parse a --metadata-file's own YAML content as a plain dict.

    A --metadata-file accepts bare YAML or a front-matter fence ending
    in ``---`` or ``...``, as Pandoc does. Returns {} on a parse
    error, a non-mapping top level, or no PyYAML -- same permissiveness as
    frontmatter_pdfmd_options, since a metadata file's pdfmd-only settings
    are optional sugar, never a hard dependency.
    """
    LEADING_FRONT_MATTER_RE = sys.modules[__name__].LEADING_FRONT_MATTER_RE
    if yaml is None:
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig")
        data = front_matter_dict(text) if LEADING_FRONT_MATTER_RE.match(text) else yaml.safe_load(text)
    except (yaml.YAMLError, OSError):
        return {}
    return load_package("pdfmd_args.options").metadata_mapping(data, path)


def frontmatter_engine(md_path: Path, metadata_files: list[Path] = ()) -> str | None:
    """Read the effective default PDF engine: the document's own front
    matter first, then each linked --metadata-file's own (the later file first, see
    metadata_files_by_priority)
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
    nested-then-bare check, in metadata_files_by_priority's order (v3.27.22; it
    was find_metadata's own order, so the first file won); this deliberately does NOT extend to `no-auto` -- no-auto
    decides whether metadata auto-discovery runs at all, so it cannot also
    depend on the metadata file that discovery itself would find.
    """
    def words(value) -> str:
        return ",".join(str(item) for item in value) if isinstance(value, (list, tuple)) else str(value)

    options = frontmatter_pdfmd_options(md_path)
    value = options.get("pdf-engine") or options.get("engine")
    if value is not None:
        return words(value)
    own = load_package("pdfmd_args.options").legacy_engine(md_path, options)
    if own is not None:
        return own.strip("[]")
    for metadata_file in metadata_files_by_priority(metadata_files):
        data = metadata_file_yaml(metadata_file)
        options = data.get("pdfmd-options")
        value = (options.get("pdf-engine") or options.get("engine")) if isinstance(options, dict) else None
        if value is None:
            top = load_package("pdfmd_args.options").legacy_engine(data, options or {})
            value = words(top) if top is not None else None
        if value is not None:
            return words(value)
    configured = config_options(md_path)
    value = configured.get("pdf-engine") or configured.get("engine")
    return words(value) if value is not None else None


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


def frontmatter_extra_preambles(md_path: Path, metadata_files: list[Path] = ()) -> list[Path]:
    """Named preambles through every option layer, relative to the file naming each one.
    Added after discovery; --no-auto preamble suppresses them, unlike CLI -H.
    """
    return deferred("pdfmd_assemble.named", "files")(md_path, metadata_files, "preamble")


def frontmatter_extra_lua_filters(md_path: Path, metadata_files: list[Path] = ()) -> list[Path]:
    """Named Lua filters through every option layer; --no-auto lua suppresses them.
    The build applies check_lua_filters to these together with discovered filters.
    """
    return deferred("pdfmd_assemble.named", "files")(md_path, metadata_files, "lua-filter")


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
STAMP_STORES = frozenset({"notes", "file", "both"})
DEFAULT_STAMP_OPTIONS = {
    "enabled": False,
    "mode": "replace",
    # Where a compile is written: the document's BUILD NOTES block (notes, the default), a NAME.hst file beside the
    # backups that leaves the document alone (file), or both.
    "store": "notes",
    # `pdfmd --history-restore` leaves a "Restored ..." entry in the history; false for a document that must not.
    "restored_note": True,
    # A build of some parts or sections only (`pdfmd @60`) is not the report, so it writes no BUILD NOTES line; with this on
    # it leaves a "partial" entry in the NAME.hst (store: file or both) naming the parts it built and those that changed.
    "partial": False,
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


def stamp_fields(value, implied_on: bool = True) -> dict:
    """The fields a pdfmd-options.stamp value sets (no defaults filled in).

    Accepts the same range of shapes --no-auto's own settings do: a bare
    bool (on/off, everything else default), a single package name or list
    of names (shorthand for enabling stamping with just those packages), or
    a full dict of {enabled, mode, packages, scope, include_output,
    pdf_metadata}. A dict with no explicit ``enabled`` key is treated as on
    -- bothering to
    configure packages/mode/scope implies wanting it active; write
    ``enabled: false`` explicitly to keep a shared default off until a
    document (or --stamp on the command line) turns it on. Not in the config
    file (``implied_on`` False, v3.27.1): there `pdfmd --setup` writes each
    detail as its own row, and only the "enabled" row switches stamping on.
    """
    options: dict = {}
    if isinstance(value, bool):
        options["enabled"] = value
    elif isinstance(value, str):
        options["enabled"] = True
        options["packages"] = [value]
    elif isinstance(value, list):
        options["enabled"] = True
        options["packages"] = [str(item) for item in value]
    elif isinstance(value, dict):
        if "enabled" in value or implied_on:
            options["enabled"] = bool(value.get("enabled", True))
        if "mode" in value:
            options["mode"] = str(value["mode"])
        if "store" in value:
            options["store"] = str(value["store"])
        restored_note = value.get("restored_note", value.get("restored-note"))
        if restored_note is not None:
            options["restored_note"] = bool(restored_note)
        if value.get("partial") is not None:
            options["partial"] = bool(value["partial"])
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
    metadata file's (the later first) -- same precedence as frontmatter_engine
    (see its docstring): a shared metadata.yaml can turn stamping on for
    every report that finds it, and any one document can still override it
    with its own pdfmd-options.stamp. Returns None (not
    DEFAULT_STAMP_OPTIONS) when nothing sets it at all, so
    resolve_stamp_options can tell "nowhere set" apart from "set to off".
    """
    # v3.27.1: field by field, the first place to set a field winning (a document's `stamp: true` keeps a shared
    # metadata.yaml's `store: file`); it used to be the whole value of the first place.
    merged: dict = {}
    found = False
    for where, options in option_sources(md_path, metadata_files):
        for name in ("stamp", "history"):       # `history` is the same setting under the name people look for (3.30.24)
            if name in options:
                found = True
                for key, value in stamp_fields(options[name], implied_on=not is_setup_layer(where)).items():
                    merged.setdefault(key, value)
    return {**DEFAULT_STAMP_OPTIONS, **merged} if found else None


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
    if options["store"] not in STAMP_STORES:
        raise SystemExit(f"{md_path}: unknown --stamp-store '{options['store']}'. "
                         f"Valid: {', '.join(sorted(STAMP_STORES))}")
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
    result = run_probe([kpsewhich, f"{name}.sty"])
    if result is None:
        return None
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
        else:
            vprint(verbose, f"WARN  --stamp: {name} is loaded but its version could not be "
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
    if output.suffix and output.suffix.lower() not in (".pdf", ".tex"):
        # a build to another format says so: "Compiled to docx with ..."
        return f"Compiled to {output.suffix.lower().lstrip('.')} with {summary} -- {timestamp}"
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


IGNORE_MARK_RE = re.compile(r"(?mi)^[ \t]*pdfmd:[ \t]*(?:ignore|skip|hands[ -]off)[ \t]*$")


def is_pdfmd_notes(body: str, indent: str) -> bool:
    """A BUILD NOTES block pdfmd has written into: it holds its stamp line or its "Compile History:" list."""
    return bool(stamp_line_pattern(indent).search(body) or history_heading_pattern(indent).search(body))


def build_notes_blocks(text: str) -> list[re.Match]:
    """Every BUILD NOTES comment of the document (not the text of an embedded file)."""
    return list(BUILD_NOTES_RE.finditer(mask_embedded_blocks(text)))


def pdfmd_build_notes(text: str) -> re.Match | None:
    """The BUILD NOTES block pdfmd writes into, or None when it has to make one. A document may carry several (the
    author's, an AI agent's, a section's own): pdfmd uses the one it has written into before; failing that, the
    only one there is (the convention it automates, kept by hand in real reports); failing that -- several, none
    pdfmd's -- none, so that it starts its own and leaves the others as they are. A block with a line
    `pdfmd: ignore` in it is never touched."""
    blocks = [match for match in build_notes_blocks(text) if not IGNORE_MARK_RE.search(match.group("body"))]
    for match in blocks:
        if is_pdfmd_notes(match.group("body"), match.group("indent")):
            return match
    every = build_notes_blocks(text)
    return blocks[0] if len(every) == 1 and blocks else None


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
    match = pdfmd_build_notes(text)
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

    new_body = load_package("pdfmd_history.stamping").demote(body, current, indent, new_line)
    return text[:match.start("body")] + new_body + text[match.end("body"):], None


def apply_stamp(md_path: Path, new_line: str, mode: str, verbose: bool) -> None:
    text = md_path.read_text(encoding="utf-8-sig")
    updated, warning = update_build_notes(text, new_line, mode)
    atomic_write_text(md_path, updated)
    if warning:
        print(f"WARN  {md_path}: {warning}", file=sys.stderr)
    vprint(verbose, f"AUTO STAMP  {md_path}: {new_line}")


HISTORY_TIME_RE = re.compile(r"^(?P<text>.*?)\s+--\s+(?P<when>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*$")


# -- How long a build took (v3.31.4) --------------------------------------------------------------------------------
# A timer starts with every build (BUILD["timer"]); the steps that matter carry @timed(...). The closing line says
# `OK    report.md > report.pdf  in 3:07  (lualatex)`; --verbose adds a TIME line per step. `build-time: on|off` and
# `time-format: auto|clock|seconds|words|TEMPLATE` (pdfmd-options, --setup, --build-time / --no-build-time, --time-format);
# the package pdfmd_buildinfo writes the durations. The command line reaches -j workers as PDFMD_BUILD_TIME / PDFMD_TIME_FORMAT.
BUILD_TIME_CLI: bool | None = None
TIME_FORMAT_CLI: str | None = None


# begin_timer: lib/pdfmd_buildinfo/build.py (v3.33.23)


# resolve_build_time and attach_time: lib/pdfmd_buildinfo/build.py (v3.33.23)


# time_breakdown: lib/pdfmd_buildinfo/build.py (v3.33.23)


# -- The record of a build (v3.31.5) ---------------------------------------------------------------------------------
# Every build writes what happened to a plain-text file in the cache (`cache: location`, global or beside the document):
# the command line, the settings that decided, every command run, everything pdfmd printed (whatever --verbose said), what
# the engines said, the steps and their times. A failed build prints where it is; `pdfmd --last-build FILE [--failed]` shows
# it. The newest `build-log-keep` records stay, and the newest failed one whatever its age. `build-log: on|failed|off`,
# `build-log-keep`, `build-log-max-size` (KB); the command line `--build-log MODE` reaches -j workers as PDFMD_BUILD_LOG.
# It holds the console text, the CMD lines, the engines' output and the lines that only --verbose prints (v3.31.6: those
# sites call vprint(), the first step of `emit`; WARN/NOTE/ERROR still print directly, and the console shows them anyway).
BUILD_LOG_CLI: str | None = None
# BUILD_LOG_MODES: lib/pdfmd_args (v3.33.40)
# BUILD_LOG_KEEP, BUILD_LOG_KILOBYTES and record_module: lib/pdfmd_buildinfo/build.py (v3.33.23)


# _RecordTee, build_log_mode_word, resolve_build_log, build_record_folders and BuildRecorder: lib/pdfmd_buildinfo/build.py (v3.33.23)


def under_home(path: Path) -> str:
    """``path`` with the home folder written as ``~`` (a record path is printed, and pasted into reports)."""
    text, home = str(path), str(Path.home())
    return "~" + text[len(home):] if text == home or text.startswith(home + os.sep) else text


def failure_text(error: BaseException) -> str:
    if isinstance(error, SystemExit):
        return str(error.code) if isinstance(error.code, str) else f"exit {error.code}"
    if isinstance(error, KeyboardInterrupt):
        return "interrupted"
    return f"{type(error).__name__}: {error}"


# last_build_command: lib/pdfmd_buildinfo/build.py (v3.33.23)


def history_module():
    """pdfmd_history, or None in a lone pdfmd.py."""
    try:
        import pdfmd_history
        return pdfmd_history
    except ImportError:
        return None


def note_entry(line: str, meta: tuple = ()):
    """The .hst entry of a "Compiled ... -- WHEN" or "Restored ... -- WHEN" line of BUILD NOTES (a bullet's dash is
    allowed), or None."""
    history = history_module()
    found = HISTORY_TIME_RE.match(line.strip().removeprefix("- ").strip())
    if history is None or not found:
        return None
    for word, kind in (("Compiled", "compiled"), ("Restored", "restored")):
        if found.group("text").startswith(word):
            return history.Entry(found.group("when"), kind, found.group("text")[len(word):].strip(), meta)
    return None


compile_entry = note_entry


# entry_line: lib/pdfmd_history/backups.py (v3.33.28)


def history_file(md_path: Path, metadata_files: list[Path] = (), existing: bool = False) -> Path:
    """Where md_path's NAME.hst is: in its backup folder (see backup_directory), or -- reading only -- in the
    NAME.unpacked/ folder --unpack made, when there is none in the backup folder."""
    options = resolve_backup_options(md_path, list(metadata_files), None)
    path = backup_directory(md_path, options) / f"{md_path.stem}.hst"
    if existing and not path.is_file():
        folder = md_path.with_name(f"{md_path.stem}{UNPACKED_SUFFIX}")
        found = [item for item in sorted(folder.glob("*.hst"))] if folder.is_dir() else []
        if (folder / path.name).is_file():
            return folder / path.name
        if len(found) == 1:
            return found[0]
    return path


def record_history(md_path: Path, metadata_files: list[Path], line: str, output: Path, verbose: bool) -> bool:
    """Add a compile to NAME.hst; False when this pdfmd cannot (no pdfmd_history package)."""
    history = history_module()
    entry = compile_entry(line)
    if history is None or entry is None:
        return history is not None
    try:
        digest = sha256_text(normalized_source(md_path.read_text(encoding="utf-8-sig")))[:12]
    except (OSError, UnicodeDecodeError):
        digest = ""
    where = history.git.state(md_path)
    parts = part_digests([Path(item) for item in BUILD["sources"][1:]], BUILD.get("root"))     # so a later partial entry can say what changed
    entry = history.Entry(entry.when, entry.kind, entry.text, tuple(item for item in (
        ("sha", digest), ("out", output.name), ("git", (where[0] + ("+" if where[1] else "")) if where else ""),
        ("took", f"{BUILD['timer'].elapsed():.1f}" if BUILD.get("timer") is not None else ""),
        ("shas", ",".join(f"{name}:{part}" for name, part in parts if part))) if item[1]))
    path = history_file(md_path, metadata_files)
    try:
        history.add_entry(path, entry, md_path.name)
    except OSError as error:
        print(f"WARN  {display_path(md_path)}: cannot write {display_path(path)} ({error.strerror or error})", file=sys.stderr)
        return True
    backup_notice(path.parent, resolve_backup_options(md_path, list(metadata_files), None))
    vprint(verbose, f"AUTO HISTORY  {display_path(path)}: {entry.when} compiled")
    return True


# notes_to_entries and entries_to_notes: lib/pdfmd_history/backups.py (v3.33.28)


# HISTORY_SHOWN, backup_folders, document_versions, version_text, version_differs, restore_version, history_documents and linked_metadata: lib/pdfmd_history/backups.py (v3.33.28)


# history_view_command, history_act, history_interactive, init_backups_command and history_command: lib/pdfmd_history/backups.py (v3.33.28)


def partial_names(info: dict, md_path: Path, output: Path) -> list[tuple[str, str]]:
    """(name, digest) of what a partial build is made of: each part (its path under the parts folder, no `.md`), or the one
    cut of a plain document, named by what the output's name adds to the document's (`report.only-a-part.pdf`)."""
    names = part_digests(info["parts"], info["root"])
    if info["cut"] is not None:
        stem = output.stem
        label = stem[len(md_path.stem) + 1:] if stem.startswith(md_path.stem + ".") else stem
        names.append((re.sub(r"\s+", "_", label), sha256_text(normalized_source(info["cut"]))[:8]))
    return names


def record_partial_history(md_path: Path, metadata_files: list[Path], preamble_files: list[Path],
                           cli_overrides: dict, output: Path, verbose: bool) -> None:
    """The "partial" entry of a build of some parts or sections (`stamp: {partial: true}`, the history in a NAME.hst)."""
    options = resolve_stamp_options(md_path, metadata_files, cli_overrides)
    if not (options["enabled"] and options["partial"] and options["store"] in ("file", "both")
            and stamp_scope_matches(options, None)):
        return
    history = history_module()
    info = BUILD.get("partial")
    if history is None or info is None:
        return
    names = partial_names(info, md_path, output)
    if not names:
        return
    path = history_file(md_path, metadata_files)
    earlier, _ = history.read_file(path)
    known: dict[str, str] = {}          # the digest each part had the last time an entry saw it
    for entry in sorted(earlier, key=lambda item: item.when):
        for word in entry.meta_dict().get("shas", "").split(","):
            name, _, digest = word.rpartition(":")
            if name and digest:
                known[name] = digest
    changed = [name for name, digest in names if name in known and known[name] != digest]
    new = [name for name, _ in names if name not in known]      # no entry has seen it yet: there is nothing to compare with
    texts = gather_stamp_texts(md_path, preamble_files)
    tail = compile_entry(build_stamp_line(options, texts, output, None, verbose))
    if tail is None:
        return
    shown = ", ".join(name for name, _ in names)
    what = "parts" if len(names) != 1 or info["cut"] is None else "section"
    news = f"; first seen: {', '.join(new)}" if new else ""
    text = (f"{what} {shown}; " + (f"changed: {', '.join(changed)}" if changed else "nothing changed") + news
            + f"; {tail.text}")
    where = history.git.state(md_path)
    meta = (("parts", ",".join(name for name, _ in names)), ("changed", ",".join(changed)), ("new", ",".join(new)),
            ("shas", ",".join(f"{name}:{digest}" for name, digest in names if digest)), ("out", output.name),
            ("git", (where[0] + ("+" if where[1] else "")) if where else ""))
    entry = history.Entry(tail.when, "partial", text, tuple(item for item in meta if item[1]))
    try:
        history.add_entry(path, entry, md_path.name)
    except OSError as error:
        print(f"WARN  {display_path(md_path)}: cannot write {display_path(path)} ({error.strerror or error})", file=sys.stderr)
        return
    vprint(verbose, f"AUTO HISTORY  {display_path(path)}: {entry.when} partial ({shown})")


@timed(lambda args, kwargs: None if args[1] else "stamp and history")    # `skip`: the cache route's .tex, no step
def stamp_build(partial: bool, skip: bool, md_path: Path, *args, **kwargs) -> None:
    """stamp_after_success for a finished build. A partial parts-mode build isn't the report, so it writes no BUILD NOTES
    stamp into the source (it would claim the report was built) -- but its PDF still says what made it (Creator,
    PdfmdVersions, PdfmdBuildDate, and PdfmdPartial naming the parts). `skip`: an intermediate stage (the cache route's
    .tex), which the final stage stamps."""
    REPORT_BUILD = sys.modules[__name__].REPORT_BUILD
    if skip:
        return
    if REPORT_BUILD.get("files"):
        # a report built through convert_one(): every chapter is stamped as a chapter of the report, as the report's own loop did
        for chapter in REPORT_BUILD["files"]:
            stamp_after_success(chapter, *args, **kwargs, pdf_only=partial, report_output=args[3])
        return
    stamp_after_success(md_path, *args, **kwargs, pdf_only=partial)
    if partial and BUILD.get("partial") is not None and len(args) >= 5:
        # `stamp: {partial: true}`: a "partial" entry in the NAME.hst (the source is not stamped, the history says what was built)
        record_partial_history(md_path, *args[:5])


def stamp_after_success(md_path: Path, metadata_files: list[Path], preamble_files: list[Path],
                        cli_overrides: dict, output: Path, verbose: bool,
                        report_output: Path | None = None, pdf_only: bool = False) -> None:
    """Write/update md_path's BUILD NOTES stamp after a successful compile,
    if --stamp/pdfmd-options.stamp says to for this context.

    report_output being given means md_path is one chapter of a report/book
    compile (main()'s -r/--report path) rather than a standalone/batch
    compile (convert_one) -- options['scope'] decides which context(s)
    actually write a stamp (see DEFAULT_STAMP_OPTIONS/resolve_stamp_options):
    "always" (default), "report"-only, or "standalone"-only.

    pdf_only (a partial build): the PDF's own provenance is written, the source's BUILD NOTES are not.
    """
    options = resolve_stamp_options(md_path, metadata_files, cli_overrides)
    if not stamp_scope_matches(options, report_output):
        return
    texts = gather_stamp_texts(md_path, preamble_files)
    # Independent of options["enabled"] below on purpose -- pdf_metadata is
    # its own always-on-by-default switch (DEFAULT_STAMP_OPTIONS), separate
    # from the .md-source BUILD NOTES stamp that "enabled" actually gates.
    stamp_pdf_metadata_posthoc(output, options, texts, verbose, partial_parts=partial_parts_label(md_path, output) if pdf_only else "")
    if pdf_only or not options["enabled"]:
        return
    line = build_stamp_line(options, texts, output, report_output, verbose)
    store = options["store"]
    if store in ("file", "both") and not record_history(md_path, metadata_files, line, output, verbose):
        store = "notes"                                   # no pdfmd_history here: the document keeps it, as before
    if store in ("notes", "both"):
        apply_stamp(md_path, line, options["mode"], verbose)


# --backup / pdfmd-options.backup: after a successful compile, copy the
# source into a sibling backup directory. Taken AFTER stamp_after_success on
# purpose, so the snapshot is exactly the file on disk; recompiling an
# unedited document then matches the newest snapshot (see backup_unchanged)
# and writes nothing. Off by default. Added v3.8.0 (2026-09-24); snapshot
# name formats and recognition of hand-made backups added v3.9.0.
#
# BACKUP_FORMATS: lib/pdfmd_history/backups.py (v3.33.28)
DEFAULT_BACKUP_OPTIONS = {
    "enabled": False,
    # Relative to the document's own directory (absolute also accepted). Empty is the default
    # place, see backup_directory(): ".backups", or a folder of the older spellings that is already there.
    "dir": "",
    # Newest N plain-timestamp snapshots of this one file kept; 0 keeps none (no copy is made, nothing already there is
    # deleted); a negative number keeps every one (the default; v3.32.43: 0 used to mean all, now it means what it says).
    # Never counts or deletes tagged ones -- see backup_snapshots().
    "keep": -1,
    "format": "compact",
    # The built PDFs kept beside the sources (v3.32.42): the newest n; 0 keeps none (the default: a build keeps what it always
    # kept, the source); a negative number keeps every one. Same meaning as `keep`.
    "pdfs": 0,
}
# _STRFTIME_PATTERNS and _COUNTER: lib/pdfmd_history/backups.py (v3.33.28)


DEFAULT_BACKUP_DIR = ".backups"
# LEGACY_BACKUP_DIRS and backup_directory: lib/pdfmd_history/backups.py (v3.33.28)


def notice_once(name: str, text: str) -> None:
    """Say `text` the first time only (a marker file in pdfmd's config folder); never in a pipe or from the API."""
    path = config_root() / f"notice-{name}"
    if os.environ.get("PDFMD_NO_PROMPT") or path.exists():
        return
    print(text)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("shown\n", encoding="utf-8")
    except OSError:
        pass


def backup_notice(backup_dir: Path, options: dict) -> None:
    """The first time a backup lands in the default hidden folder, say where it is."""
    if not options.get("dir") and backup_dir.name == DEFAULT_BACKUP_DIR:
        notice_once("backup-folder", f"NOTE  backups go to {DEFAULT_BACKUP_DIR}/ beside the document by default. It is a "
                    "hidden folder (ls -a shows it), so don't worry if you don't see it; "
                    "`pdfmd --setup` or `pdfmd-options: {backup: {dir: ...}}` changes the place.")


# backup_template, fill_backup_template and backup_name_regex: lib/pdfmd_history/backups.py (v3.33.28)


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


# _plain_backup_patterns: lib/pdfmd_history/backups.py (v3.33.28)


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


# backup_snapshots: lib/pdfmd_history/backups.py (v3.33.28)


def backup_fields(value, implied_on: bool = True) -> dict:
    """The fields a pdfmd-options.backup value sets: a bare bool, a directory name
    (shorthand for enabling it with that directory), or a full dict of
    {enabled, dir, keep, format}. A dict with no explicit ``enabled`` counts
    as on, same as stamp_fields' rule, except in the config file (``implied_on`` False).
    """
    options: dict = {}
    if isinstance(value, bool):
        options["enabled"] = value
    elif isinstance(value, str):
        options["enabled"] = True
        options["dir"] = value
    elif isinstance(value, dict):
        if "enabled" in value or implied_on:
            options["enabled"] = bool(value.get("enabled", True))
        if value.get("dir"):
            options["dir"] = str(value["dir"])
        if value.get("format"):
            options["format"] = str(value["format"])
        for name in ("keep", "pdfs"):
            if value.get(name) is not None:                      # an empty `keep:` is no setting (it was "all" before v3.32.43, too)
                options[name] = backup_count(name, value[name])
    return options


def backup_count(name: str, given) -> int:
    """How many copies `backup: {keep}` (sources) or `{pdfs}` (built PDFs) keeps: a whole number, the newest N; 0 none; negative
    every one (v3.32.43: the two share this meaning). The words all/none/off/true/false are taken too."""
    words = {"all": -1, "none": 0, "off": 0, "true": -1, "false": 0}
    word = str(given).strip().lower()
    try:
        return words[word] if word in words else int(given)
    except (TypeError, ValueError):
        raise SystemExit(f"pdfmd-options.backup.{name} must be a whole number (negative: all, 0: none) or all/none, got {given!r}")


def resolve_backup_options(md_path: Path, metadata_files: list[Path], cli_enabled: bool | None,
                           cli_format: str | None = None) -> dict:
    """Document front matter first, then each metadata file in order (same
    cascade as frontmatter_stamp), then --backup/--no-backup and
    --backup-format on top.
    """
    merged: dict = {}
    for where, own in option_sources(md_path, metadata_files):       # field by field since v3.27.1
        for name in ("backup", "backups"):                           # both spellings (v3.32.43); `backup` first where both are set
            if name in own:
                for key, value in backup_fields(own[name], implied_on=not is_setup_layer(where)).items():
                    merged.setdefault(key, value)
    options = {**DEFAULT_BACKUP_OPTIONS, **merged}
    if cli_enabled is not None:
        options["enabled"] = cli_enabled
    if cli_format:
        options["format"] = cli_format
    return options


# BACKUP_IGNORED_LINE_RE, backup_unchanged, backup_after_success, backup_pdf_pattern, backup_pdf_after_success and backup_summary: lib/pdfmd_history/backups.py (v3.33.28)


def backup_before_edit(md_path: Path, metadata_files: list[Path] | None = None) -> Path | None:
    """A snapshot of md_path before pdfmd rewrites it (`--extract-tables`...): in the backup folder, named by the
    configured format, whether or not backups are switched on for compiles. The path, or None if it failed."""
    options = resolve_backup_options(md_path, metadata_files or [], None)
    backup_dir = backup_directory(md_path, options)
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_notice(backup_dir, options)
        target = backup_target(backup_dir, backup_template(options["format"]), md_path)
        shutil.copy2(md_path, target)
        return target
    except OSError as error:
        print(f"WARN  {display_path(md_path)}: backup failed: {error}", file=sys.stderr)
        return None


# --- --extract-tables / --expand-tables (the work is in pdfmd_tables) -------------------------------------------

# tables_command: lib/pdfmd_tables/command.py (v3.33.24)


# PDF Info-dictionary key names pdfmd writes when pdf_metadata is on. Two
# separate keys, not one combined "Compiled with ... -- TIMESTAMP" line like
# the .md stamp's: LuaTeX/XeTeX apply their usual typographic ligatures
# (-- becomes an en dash) to hypersetup's pdfinfo strings same as any other
# typeset text, so a literal "--" separator doesn't survive intact -- kept
# out entirely here rather than fought with escaping.
PDF_INFO_VERSIONS_KEY = "PdfmdVersions"
PDF_INFO_BUILD_DATE_KEY = "PdfmdBuildDate"
PDF_INFO_PARTIAL_KEY = "PdfmdPartial"


def partial_parts_label(scaffold: Path, output: Path) -> str:
    """The parts a partial build holds, as the output file names them (`report.introduction+procedure.pdf` ->
    `introduction+procedure`); the output's own stem when it does not start with the scaffold's."""
    prefix = scaffold.stem + "."
    return output.stem[len(prefix):] if output.stem.startswith(prefix) and len(output.stem) > len(prefix) else output.stem


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


def stamp_pdf_metadata_posthoc(pdf_path: Path, options: dict, texts: list[str], verbose: bool, partial_parts: str = "") -> None:
    """Write PdfmdVersions/PdfmdBuildDate into pdf_path's own PDF Info
    dictionary after a successful compile -- see pdf_metadata_snippet's
    docstring for why this replaced an in-LaTeX \\hypersetup injection.
    Silently does nothing if options['pdf_metadata'] is off, pdf_path isn't
    a real PDF (e.g. a --to other than pdf), or pypdf isn't installed (a
    soft dependency, same convention as this module's own `yaml` import --
    a WARN either way, since unlike PyYAML's front-matter sugar this is an
    always-on-by-default feature quietly not doing its job). ``partial_parts``: the parts a partial build holds, recorded as
    PdfmdPartial so the PDF says it is not the whole report.
    """
    if not options.get("pdf_metadata"):
        return
    if pypdf is None:
        vprint(verbose, "WARN  --stamp: pdf_metadata is on but pypdf is not installed "
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
                # clone_from, not append(): append() drops the whole outline of a PDF whose bookmarks are typed
                # `/Type /Outlines` (Calibre 9.16 writes them so), and a Calibre PDF's bookmarks are its headings
                writer = deferred("pdfmd_polish.info", "clone_pdf")(reader)
                deferred("pdfmd_polish.info", "add_metadata")(writer, {
                    **existing,
                    f"/{PDF_INFO_VERSIONS_KEY}": summary,
                    f"/{PDF_INFO_BUILD_DATE_KEY}": timestamp,
                    **({f"/{PDF_INFO_PARTIAL_KEY}": partial_parts} if partial_parts else {}),
                })
                atomic_write_pdf(writer, pdf_path)
        finally:
            pypdf_logger.setLevel(previous_level)
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


def is_package_helper_yaml(path: Path) -> bool:
    """`<package>-pdfmd.yaml` and `<package>-office.yaml`: what a LaTeX package tells pdfmd (package_helper), not metadata.
    A source restored with its package has them beside the document (v3.28.38)."""
    return path.name.lower().endswith(("-pdfmd.yaml", "-pdfmd.yml", "-office.yaml", "-office.yml"))


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


def global_metadata_file() -> Path | None:
    """`metadata.yaml` beside the config file (`pdfmd --setup` writes it): metadata every document gets, below
    anything its own folder's metadata says. None when absent or the config is switched off."""
    config = config_path()
    candidate = None if config is None else config.with_name("metadata.yaml")
    return candidate if candidate is not None and candidate.is_file() else None


# -- Presets: other global metadata files to choose from (v3.28.19) ------------------------------------------------
# `presets/NAME.yaml` beside the config file is a global metadata file like `metadata.yaml` (which is the preset
# `default`): `--preset lab`, `pdfmd-options: {preset: lab}` (or lab.yaml; a path works too) takes it instead,
# `--preset none` / `--no-global-metadata` / `pdfmd-options: {global-metadata: false}` takes none. The command line
# wins, then the document's own pdfmd-options, its metadata files', then the config file's `options`.
PRESET_CLI: str | None = None                  # --preset (set in main)
GLOBAL_METADATA_CLI: bool | None = None        # --global-metadata / --no-global-metadata (set in main)
PRESET_OFF = ("none", "off", "false", "no")
PRESET_DEFAULT = ("default", "on", "true", "yes")


def presets_dir() -> Path | None:
    config = config_path()
    return None if config is None else config.with_name("presets")


def list_presets() -> list[Path]:
    folder = presets_dir()
    return sorted((item for item in folder.glob("*.y*ml") if item.suffix in (".yaml", ".yml")),
                  key=lambda item: item.name.casefold()) if folder is not None and folder.is_dir() else []


def preset_name(path: Path) -> str:
    return "default" if path.parent != presets_dir() else path.stem


def is_global_metadata(path) -> bool:
    """Whether ``path`` is pdfmd's global metadata (`metadata.yaml` beside the config file) or one of its presets."""
    config = config_path()
    if config is None or path is None:
        return False
    folder = Path(os.path.abspath(config.parent))
    where = Path(os.path.abspath(path))
    return ((where.parent == folder and where.name == "metadata.yaml")
            or (where.parent == folder / "presets" and where.suffix in (".yaml", ".yml")))


def preset_file(value: str, base: Path | None = None) -> Path | None:
    """The file a preset value names: `default`, a name in presets/ (with or without .yaml), or a path (relative to
    ``base``, the document's folder, else to the working folder). Stops with the names there are for one that is none."""
    name = str(value).strip()
    if name.casefold() in PRESET_DEFAULT:
        return global_metadata_file()
    folder = presets_dir()
    if folder is not None and not re.search(r"[/\\]", name) and not name.startswith("~"):
        for candidate in (name, f"{name}.yaml", f"{name}.yml"):
            if (folder / candidate).is_file():
                return folder / candidate
    else:
        path = Path(name).expanduser()
        for candidate in ([path] if path.is_absolute() else [(base or Path.cwd()) / path, Path.cwd() / path]):
            if candidate.is_file():
                return Path(os.path.abspath(candidate))
    known = ", ".join(preset_name(item) for item in list_presets()) or "none yet"
    raise SystemExit(f"unknown preset {name!r} (the presets/ folder beside the config file has: {known}; "
                     "`none` takes no global metadata; pdfmd --presets lists them)")


def presets_report(path: Path | None = None) -> bool:
    """`--presets [DOCUMENT]`: the global metadata files there are, and which one a build here would use."""
    config = config_path()
    if config is None:
        print("The config file is switched off (PDFMD_CONFIG is empty): there is no global metadata.")
        return False
    default = global_metadata_file()
    rows = [("default", default, "metadata.yaml" if default else "metadata.yaml (not there yet: pdfmd --setup writes it)")]
    rows += [(preset_name(item), item, f"presets/{item.name}") for item in list_presets()]
    document = Path(path) if path is not None and Path(path).is_file() else None
    try:
        local = find_local_metadata((document.parent if document else Path.cwd()).resolve(), None,
                                    document_stem=document.stem if document else None)
        local = [] if local is AUTO_METADATA_DISABLED or local is None else (local if isinstance(local, list) else [local])
        used = chosen_global_metadata(document, local)
    except (SystemExit, FileNotFoundError, ValueError) as error:
        print(f"WARN  {error}", file=sys.stderr)
        used = None
    for name, file, where in rows:
        keys = [("options" if key == "pdfmd-options" else key) for key in metadata_file_yaml(file)] if file else []
        shown = ", ".join(keys[:6]) + (f" +{len(keys) - 6}" if len(keys) > 6 else "")
        print(f"{'*' if used is not None and file is not None and file == used else ' '} {name:<14} {where}"
              + (f"  ({shown})" if shown else ""))
    print("  (* is the one a build here would use; none marked: no global metadata)" if used is None
          else "  (* is the one a build here would use)")
    return True


def chosen_global_metadata(document: Path | None, local_files: list[Path]) -> Path | None:
    """The global metadata file this document gets: None when it gets none. See the section above for the order."""
    def decide(preset, enabled):
        if enabled is False or (preset is not None and str(preset).strip().casefold() in PRESET_OFF):
            return False
        if preset is not None and str(preset).strip() and str(preset).strip().casefold() not in PRESET_DEFAULT:
            return preset_file(preset, document.parent if document is not None else None)
        return True if (preset is not None or enabled is not None) else None
    chosen = decide(PRESET_CLI, GLOBAL_METADATA_CLI)
    if chosen is None:
        try:
            if document is not None:
                preset = first_pdfmd_option(document, local_files, "preset")
                enabled = first_pdfmd_option(document, local_files, "global-metadata")
            else:
                preset, enabled = config_options().get("preset"), config_options().get("global-metadata")
        except (OSError, UnicodeDecodeError):            # a document that is not there (yet): the config alone decides
            preset, enabled = config_options().get("preset"), config_options().get("global-metadata")
        if isinstance(enabled, str):
            enabled = False if enabled.strip().casefold() in PRESET_OFF else True if enabled.strip().casefold() in PRESET_DEFAULT else None
        chosen = decide(preset, enabled if isinstance(enabled, bool) else None)
    if chosen is False:
        return None
    return chosen if isinstance(chosen, Path) else global_metadata_file()


METADATA_PRECEDENCE_CLI: str | None = None    # --metadata-precedence (set in main)
METADATA_PRECEDENCES = ("later", "first")


def metadata_precedence() -> str:
    """Which of two metadata files wins a key both set (v3.27.22): `later` (the default, as Pandoc takes them) or
    `first`. From --metadata-precedence, else the config's `options.metadata-precedence` (pdfmd --setup). Not from a
    document or a metadata file: it decides how those are layered."""
    value = METADATA_PRECEDENCE_CLI
    if value is None:
        value = config_options().get("metadata-precedence")
    if value is None:
        return "later"
    mode = str(value).strip().casefold()
    if mode not in METADATA_PRECEDENCES:
        raise SystemExit(f"unknown metadata-precedence value {value!r}. Valid: {', '.join(METADATA_PRECEDENCES)}")
    return mode


def pandoc_metadata_order(metadata_files: list[Path]) -> list[Path]:
    """The metadata files in the order Pandoc gets them: the global metadata file first. Pandoc prefers a later
    --metadata-file, and the global file is the lowest in priority (v3.27.17; it came last and so beat the
    folder's own metadata.yaml). With `--metadata-precedence first` the others go in reverse, so that the first wins
    in Pandoc too (v3.27.22). The list itself keeps the global file last (Pandoc runs in the folder of its first
    entry); what pdfmd reads out of the files itself follows this order too (metadata_files_by_priority)."""
    extra = next((path for path in metadata_files if is_global_metadata(path)), None)
    supplied = [path for path in metadata_files if path != extra and path in KIT_METADATA]            # a kit's defaults, in its order
    folders = [path for path in metadata_files if path != extra and path not in KIT_METADATA and is_folder_metadata(path)]       # nearest first
    parents, local = deferred("pdfmd_metadata", "parent_metadata_order")(metadata_files, extra)
    if len(local) > 1 and metadata_precedence() == "first":
        local.reverse()
    return [*([extra] if extra is not None else []), *supplied, *reversed(folders), *parents, *local]


def metadata_files_by_priority(metadata_files) -> list[Path]:
    """The metadata files, the one that wins first, for what pdfmd reads out of them itself (`pdfmd-options`, `margin`,
    the engine): the later file, as Pandoc takes it, then the earlier, the global metadata file (pdfmd --setup) last.
    Until v3.27.22 the first file won for pdfmd's keys while the later won for Pandoc's (a document-named YAML overrode
    metadata.yaml's margins but not its pdfmd-options)."""
    return list(reversed(pandoc_metadata_order(list(metadata_files))))


def find_metadata(directory: Path, requested: list[str] | None, report: bool = False,
                  document_class: str | None = None,
                  document_stem: str | None = None, document: Path | None = None,
                  discover: bool = True, kits: bool = True) -> Path | list[Path] | object | None:
    """Choose metadata files (see find_local_metadata), with the folders' and the global metadata file last when the files were
    found automatically (not named with -y). The global one is the lowest in priority: pandoc_metadata_order gives it to Pandoc
    first. ``discover=False`` (explicit-only) looks for no file beside the document but keeps the folders' and the global ones.
    The defaults of the kits chosen for the document (``kits``; entry 3du) come between the global file and the folders'."""
    found = find_local_metadata(directory, requested, report, document_class, document_stem) if discover else None
    extra, folders = None, []
    if requested is None and found is not AUTO_METADATA_DISABLED:
        extra = chosen_global_metadata(document, [found] if isinstance(found, Path) else list(found or []))
        folders = folder_metadata_files(str(directory.resolve()))          # the folders' own, between the files and the global
        found = deferred("pdfmd_metadata", "with_metadata_parents")(found, directory, document, report, document_class, document_stem, discover, folders, extra)
    supplied: list[Path] = []
    if kits and document is not None and found is not AUTO_METADATA_DISABLED:
        here = [*(found if isinstance(found, list) else [found] if found is not None else []), *folders,
                *([extra] if extra is not None else [])]
        supplied = kit_metadata_files(active_kits(document, here))
    if (extra is None and not folders and not supplied) or found is AUTO_METADATA_DISABLED:
        return found
    listed = [*(found if isinstance(found, list) else [found] if found is not None else []), *folders, *supplied,
              *([extra] if extra is not None else [])]
    return listed[0] if len(listed) == 1 else listed


def find_local_metadata(directory: Path, requested: list[str] | None, report: bool = False,
                        document_class: str | None = None,
                        document_stem: str | None = None, search_dirs: list[Path] | None = None) -> Path | list[Path] | object | None:
    """Choose metadata files, supporting explicit stacks and automatic discovery."""
    if requested == []:
        return AUTO_METADATA_DISABLED
    if search_dirs is None and requested is None and document_stem:
        unpacked = directory / f"{document_stem}{UNPACKED_SUFFIX}"
        unpacked_yaml = (sorted([*unpacked.glob("*.yaml"), *unpacked.glob("*.yml")],
                                key=lambda item: natural_key(item.name)) if unpacked.is_dir() else [])
        if unpacked_yaml:
            # The folder --unpack made for this document holds ITS metadata,
            # in the order it was merged in: nothing else is guessed at.
            return order_metadata(unpacked_yaml)
    search_dirs = accessory_directories(directory, document_stem) if search_dirs is None else search_dirs
    if requested is not None:
        if requested == ["all"]:
            candidates = [item for folder in search_dirs
                          for item in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml"))
                          if item.name.lower() != "defaults.yaml" and not is_package_helper_yaml(item)
                          and yaml_autoinclude(item)]
            return order_metadata(candidates)
        return order_metadata([resolve_yaml(directory, value) for value in requested])
    candidates = [item for folder in search_dirs
                  for item in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml"))
                  if item.name.lower() != "defaults.yaml" and not is_package_helper_yaml(item)
                          and yaml_autoinclude(item)]
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


# chapter_order: lib/pdfmd_parts/__init__.py (v3.33.30)


def excluded_by_cli(md_path: Path, exclusions: list[str]) -> bool:
    candidates = {md_path.name.casefold(), md_path.stem.casefold(), str(md_path).casefold()}
    for exclusion in exclusions:
        value = Path(exclusion)
        names = {value.name.casefold(), value.stem.casefold(), str(value).casefold()}
        if candidates & names:
            return True
    return False


def report_sources(paths: list[Path], exclusions: list[str], exclude_unnumbered: bool = False,
                   recursive: bool = False, include_never: bool = False) -> tuple[list[Path], list[Path]]:
    # .resolve() for the same reason as find_markdown(): a relative directory
    # plus a file in a subdirectory would otherwise make Pandoc's cwd and its
    # source-file arguments both relative, and doubling up into a bad path.
    files = []
    for path in paths:
        if path.is_dir():
            files.extend(skip_never([file.resolve() for file in
                                     (path.rglob("*.md") if recursive else path.glob("*.md"))], include_never))
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
# PARTIAL_KEY: lib/pdfmd_assemble (v3.33.38)
# PARTS_SKIP_DIRS: lib/pdfmd_parts/__init__.py (v3.33.30)


# parts_directory: lib/pdfmd_parts/__init__.py (v3.33.30)


# collect_parts to select_parts_and_sections: lib/pdfmd_parts/__init__.py (v3.33.30)


# The sections of parts that a parts-mode build takes only a piece of (see
# ScaffoldPlan.cuts), consulted by scaffold_inputs() wherever it runs -- the cache
# route calls the build again, and this is what lets both see the same cuts.
PART_CUTS: dict[Path, list[Heading]] = {}


# ScaffoldPlan, warn_shared_parts_folder: lib/pdfmd_parts/__init__.py (v3.33.30)


# plan_scaffold: lib/pdfmd_parts/__init__.py (v3.33.30)


# PART_FENCE, wrap_part, wrap_runs: lib/pdfmd_parts/__init__.py (v3.33.30)


KATEX_X_HEIGHT = 0.442       # KaTeX_Main's x-height per em (v3.28.25: the size that matches a body font's is its x-height / this)


def sfnt_x_height(path: Path, index: int = 0) -> float | None:
    """A font file's x-height as a fraction of its em (OS/2 sxHeight / head unitsPerEm), None when the file has none."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        base = 0
        if data[:4] == b"ttcf":
            base = struct.unpack(">I", data[12 + 4 * index:16 + 4 * index])[0]
        tables = {}
        count = struct.unpack(">H", data[base + 4:base + 6])[0]
        for number in range(count):
            at = base + 12 + 16 * number
            tables[data[at:at + 4]] = struct.unpack(">II", data[at + 8:at + 16])[0]
        units = struct.unpack(">H", data[tables[b"head"] + 18:tables[b"head"] + 20])[0]
        os2 = tables[b"OS/2"]
        version = struct.unpack(">H", data[os2:os2 + 2])[0]
        height = struct.unpack(">h", data[os2 + 86:os2 + 88])[0] if version >= 2 else 0
    except (struct.error, KeyError, IndexError):
        return None
    return height / units if height > 0 and units > 0 else None


def body_x_height(family: str | None) -> float | None:
    """The x-height (a fraction of the em) of an installed body font, found with fontconfig; None when the font is not
    installed or its file records none."""
    fc_match = which("fc-match")
    if not family or not fc_match:
        return None
    try:
        done = subprocess.run([fc_match, "-f", "%{family}\n%{file}\n%{index}", family], capture_output=True,
                              encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (done.stdout or "").splitlines()
    if done.returncode != 0 or len(lines) < 3 or family.casefold() not in lines[0].casefold():
        return None                                  # fontconfig answered with another font: the family is not installed
    return sfnt_x_height(Path(lines[1]), int(lines[2]) if lines[2].isdigit() else 0)


@lru_cache(maxsize=None)
def katex_scale(family: str | None) -> float | None:
    """The `font-size` (in em of the body) that gives KaTeX's formulas the body font's x-height: x-height / 0.442 (STIX Two
    Text 1.07, Noto Serif 1.21, Times 1.01, Georgia 1.09, Libertinus 0.97), kept within 0.85 and 1.4; None when the font is
    not known or has no x-height recorded (KaTeX keeps its own 1.21em)."""
    height = body_x_height(family)
    if height is None:
        return None
    return round(min(1.4, max(0.85, height / KATEX_X_HEIGHT)), 2)


def weasyprint_math_args(engine: str, pandoc_options: list[str], body_font: str | None = None,
                         no_auto: list[str] | None = None) -> list[str]:
    """For WeasyPrint (v3.27.12), which does not draw MathML (Pandoc's default HTML math printed each formula twice as
    flat text): Pandoc's plain math, simple formulas in Unicode and the others as TeX, unless the command line chooses
    the math; and pdfmd_lua/weasyprint.lua, which says once that the math is text and (v3.28.3) keeps a table's
    caption whole. With node and MathJax (v3.28.46, `pdfmd --install math:mathjax`) the filter typesets the math with
    it, in the font that goes with the body font; with KaTeX (v3.28.11, `pdfmd --install math:katex`) it typesets what
    MathJax cannot read, or all of it when MathJax is not there (or `--no-auto mathjax`): the variables name their
    folders and node. Last of the filters, after the LaTeX filter's \\ce in math."""
    if engine != "weasyprint":
        return []
    chosen = any(item.startswith(HTML_MATH_OPTIONS) for item in pandoc_options)
    out = [] if chosen else html_math_args("plain")
    try:
        import pdfmd_lua
    except ImportError:
        return out
    shipped = pdfmd_lua.path("weasyprint")
    if shipped is None:
        return out
    runtime = None if chosen or not (pdfmd_lua.FILTERS / "katex.cjs").is_file() else katex_runtime()
    if runtime is not None:
        node, folder = runtime
        out += ["-V", f"pdfmd-katex={folder}", "-V", f"pdfmd-katex-url={folder.as_uri()}",
                "-V", f"pdfmd-katex-node={node}"]
        scale = katex_scale(body_font)
        if scale is not None:
            out += ["-V", f"pdfmd-katex-scale={scale}"]
    jax = (None if chosen or auto_disabled(no_auto, "mathjax") or not (pdfmd_lua.FILTERS / "mathjax.cjs").is_file()
           else mathjax_runtime())
    if jax is not None:
        node, folder = jax
        font = mathjax_font_for(body_font, mathjax_fonts(folder))
        if font is not None:
            out += ["-V", f"pdfmd-mathjax={folder}", "-V", f"pdfmd-mathjax-font={font[0]}",
                    "-V", f"pdfmd-mathjax-node={node}"]
            height = None if font[1] else body_x_height(body_font)
            if height is not None:
                out += ["-V", f"pdfmd-body-xheight={round(height, 4)}"]          # the size match, for a body the font is not made for
    return out + ["--lua-filter", str(shipped)]


# scaffold_inputs: lib/pdfmd_parts/__init__.py (v3.33.30)


def ascii_table_transform(md_path: Path, metadata_files: list[Path], parts: list[Path]) -> "Callable[[str, Path], str] | None":
    """The ``transform`` of scaffold_inputs() that repairs the ASCII tables of a part (the document's own setting), or None."""
    if not parts:
        return None
    mode = table_ascii_mode(md_path, list(metadata_files))

    def transform(text: str, part: Path) -> str:
        if mode != "off":
            text = repair_ascii_text(text, mode, display_path(part))
        return cell_tags_text(text, md_path, metadata_files, display_path(part))
    return transform


# split_top_level_sections, slug_of and the section code (the banner `Rendering one section of an ordinary document`, ATX_HEADING_RE to scan_headings): lib/pdfmd_parts/__init__.py (v3.33.30)


# ATTRIBUTE_ID_RE to plan_sections: lib/pdfmd_parts/__init__.py (v3.33.30)


# split_into_parts: lib/pdfmd_parts/__init__.py (v3.33.30)



# -- HTML output and default-output (v3.19.4) --------------------------------
# `pdfmd-options: {default-output: html}`: the format a document builds to when
# the command line names none (no --to, no -o with a recognized extension, no
# --stop-at, no -p). `pdfmd-options: {html: {...}}` shapes an HTML build:
#   self-contained: true   one file with everything inlined (--embed-resources
#                          --standalone; pdfmd's HTML output is otherwise a
#                          fragment); maths defaults to MathML in fragments too,
#                          the one kind that needs no network
#   standalone: true       a full page, resources left linked
#   math: mathml|mathjax|katex|webtex|plain
#   css: file.css | [..]   --css, relative to the document
HTML_TARGETS = frozenset({"html", "html4", "html5"})
DEFAULT_OUTPUT_ALIASES = {"tex": "latex", "txt": "txt", "text": "txt", "md": "markdown", "htm": "html",
                          "typ": "typst", "markdown": "markdown", "jpeg": "jpg", "tif": "tiff"}
# The math method, in whichever spelling the installed Pandoc has -- three
# generations: `--math-method=X` (3.11, which deprecates the others and warns),
# `--html-math-method=X` (a middle range of 3.x), and the short flags
# `--mathml`/`--mathjax`/... (older, 3.1 among them, which does not know the
# long forms at all). Found out from `pandoc --help`, never from a guessed
# version number.
HTML_MATH_METHODS = ("mathml", "mathjax", "katex", "webtex", "plain", "gladtex")
HTML_MATH_OPTIONS = ("--math-method", "--html-math-method", "--mathml", "--mathjax", "--katex", "--webtex", "--gladtex",
                     "--latexmathml")       # on the command line, any of these chooses the math itself
HTML_MATH_SHORT_FLAGS = {"mathml": "--mathml", "mathjax": "--mathjax", "katex": "--katex",
                         "webtex": "--webtex", "gladtex": "--gladtex"}   # "plain" is the default: no flag
_PANDOC_HELP: str | None = None


def pandoc_has_option(option: str) -> bool:
    """Whether the installed Pandoc lists ``option`` in its --help, as a whole
    option name (`--math-method` is not found inside `--html-math-method`)."""
    global _PANDOC_HELP
    if _PANDOC_HELP is None:
        done = run_probe(["pandoc", "--help"])
        _PANDOC_HELP = done.stdout if done else ""
    return bool(re.search(r"(?<![\w-])" + re.escape(option) + r"(?![\w-])", _PANDOC_HELP))


def html_math_args(method: str) -> list[str]:
    for option in ("--math-method", "--html-math-method"):
        if pandoc_has_option(option):
            return [f"{option}={method}"]
    flag = HTML_MATH_SHORT_FLAGS.get(method)
    return [flag] if flag else []


def cascaded_option(md_path: Path, metadata_files: list[Path], key: str):
    """``pdfmd-options.<key>``: the document's own, else its metadata files' in order, else the config's (None if none
    sets it); a mapping merged field by field (see first_pdfmd_option)."""
    return first_pdfmd_option(md_path, metadata_files, key)


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
    if name == "ascii" or name.startswith("ascii:"):
        raise SystemExit(f"{display_path(md_path)}: pdfmd-options.default-output cannot be '{name}'; ASCII output is "
                         "asked for on the command line (--to ascii) or by the output's name (-o x.ascii.txt)")
    ASSEMBLED_FORMAT = sys.modules[__name__].ASSEMBLED_FORMAT
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
        done = run_probe(["pandoc", "--version"])
        for line in (done.stdout if done else "").splitlines():
            if line.lower().startswith("user data directory:"):
                _PANDOC_DATA_DIR = Path(line.split(":", 1)[1].strip())
    return _PANDOC_DATA_DIR or None


# -- A citation style named by its URL (v3.27.27) -----------------------------------------------------------------
# `csl: https://.../ieee.csl` needs the network and Pandoc's HTTP support, which a Homebrew Pandoc can lack ("pandoc
# was compiled without HTTP support"). pdfmd fetches the style itself, once, into its cache (re-fetched after 30 days)
# and hands Pandoc the file. Without the network it takes the copy it fetched before, however old; else a style of
# the same file name in Pandoc's own csl/ folder, with a WARN; else `csl-fallback: default` (the default) builds with
# Pandoc's default style, with a WARN, and `csl-fallback: error` stops. `--no-auto remotecsl` leaves the URL to Pandoc.


_PANDOC_VERSION: tuple[int, ...] | None = None


def pandoc_version() -> tuple[int, ...]:
    global _PANDOC_VERSION
    if _PANDOC_VERSION is None:
        try:
            done = run_probe(["pandoc", "--version"])
            first = done.stdout.splitlines()[0]                                  # (no answer: an AttributeError, below)
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
    HTML_TARGETS), with MathML unless the user chooses a method."""
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
    out += deferred("pdfmd_bridge.html_math", "arguments")(settings, pandoc_options, md_path, metadata_files)
    css = settings.get("css")
    for name in ([css] if isinstance(css, str) else css if isinstance(css, list) else []):
        out += ["--css", str((md_path.parent / str(name)).resolve())]
    if standalone and not any(item.startswith(("--metadata=pagetitle", "-Mpagetitle")) for item in pandoc_options):
        if not (frontmatter_value(md_path, "title") or frontmatter_value(md_path, "pagetitle")
                or any(metadata_file_yaml(item).get("title") or metadata_file_yaml(item).get("pagetitle")
                       for item in metadata_files)):
            out += ["--metadata", f"pagetitle={md_path.stem}"]
    return out


# -- Style sheets (v3.28.41) -------------------------------------------------------------------------------------
# A style sheet for the writers that read CSS (HTML, EPUB, the HTML engines' PDF: WeasyPrint and the rest, Calibre) is found
# beside the document as `<name>.css` or `pdfmd.css`, named by `css:` in the front matter or a metadata file (Pandoc's own
# key), by `pdfmd-options: {css: FILE | [..]}`, or given as `--css FILE`; the later ones come after the earlier ones in the
# page, as in CSS. With `css-scope: all` (`--css-scope all`) the part of it that means something to the other writers is
# read as well (`pdfmd_css`): the paper and its margins (`@page`), the body's font, size, line spacing and indent, the colour
# of links and the font of code become the Pandoc variables LaTeX, Typst and the rest take, below what the document, its
# metadata and the command line set. `--no-auto css` turns the search for `<name>.css` and `pdfmd.css` off.
CSS_CLI: list[str] = []                  # --css FILE (repeatable)
CSS_SCOPE_CLI: str | None = None         # --css-scope
CSS_SCOPES = ("html", "all")


# `css_scope`, `css_names`, `css_sources`, `css_additions`, `css_heading_latex` and `css_heading_args` (with the `CSS_HEADING_*`
# and `CSS_COLOURS` tables) live in `pdfmd_css.latex` (v3.33.10); the stand-ins are in the binding block above.


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
# STOP_STAGES: lib/pdfmd_args (v3.33.40)
# A top-level front-matter key (an HTML comment where there is no front matter
# to put it in) written into every assembled file. A file that carries it is
# already the finished text of a build: parts mode never treats
# it as a scaffold (it would join the parts a second time), and batch/report
# assembly skips it instead of assembling an assembly.
ASSEMBLED_KEY = "pdfmd-assembled"
ASSEMBLED_KEY_RE = re.compile(r"^pdfmd-assembled:[ \t]*(?:true|yes|on)[ \t]*$", re.IGNORECASE | re.MULTILINE)
# ASSEMBLED_COMMENT: lib/pdfmd_assemble (v3.33.38)
# `<!-- pdfmd-assembled: true; no-auto: lua,preamble -->`: the comment form of
# the marker can carry the no-auto kinds that the front-matter form keeps in
# `pdfmd-options` (see embed_into_text).
ASSEMBLED_COMMENT_RE = re.compile(
    r"^<!-- pdfmd-assembled: true(?:; no-auto: (?P<kinds>[a-z:,]+))? -->[ \t]*$", re.MULTILINE)


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


# mark_assembled: lib/pdfmd_assemble (v3.33.38)


# -- Comments: lib/pdfmd_comments (v3.22.0, v3.22.4) ---------------------------
# Stripping `<!-- -->`, LaTeX `%` and CSL comments, and the strip-comments policy, live in pdfmd_comments. It reads
# the three names below as core.X. FENCE_RE (a code fence: its run of backticks or tildes, and the rest) also serves
# the native converter's line scan.
FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<rest>.*)$")
COMMENT_KINDS = ("markdown", "preamble", "bibliography", "csl", "metadata")
# --strip-comments-in / --keep-comments-in (kind sets); --strip-comments / --keep-comments is STRIP_COMMENTS_CLI.
STRIP_KINDS_CLI: frozenset[str] = frozenset()
KEEP_KINDS_CLI: frozenset[str] = frozenset()


# BIB_LINK_RE, BIB_SUFFIXES, PANDOC_CITE_RE and LATEX_CITE_RE: lib/pdfmd_assemble (v3.33.38)


# used_citation_keys, filter_bibliography, assemble_markdown_text and write_assembled_markdown: lib/pdfmd_assemble (v3.33.38)


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
EMBED_KINDS = ("metadata", "preamble", "lua", "bibliography", "hst")
# `csl` (v3.28.36) is not in the default either: a citation style is 10-90 KB (apa.csl is 86 KB, 2000 lines) and the global
# metadata sets one for every document; `--embed-metadata csl`, `--attach-csl` or `pdfmd-options: {embed: {csl: true}}` carry it.
# `files` (v3.25.10) is not in the default: it can be big. `--embed-metadata files` or `all` asks for it: the images, CSV
# data and included files the text and the preamble point at, as `type: file` blocks (text as it is, anything else as base64).
EMBED_OPTIONAL = ("files", "csl")
EMBED_ALL = EMBED_KINDS + EMBED_OPTIONAL
# A LaTeX comment line closing the embedded preamble inside `header-includes`:
# document_header_file puts the front-matter macro definitions there, after
# the preamble that defines them and before the document's own additions,
# the order a normal build gives them.
PREAMBLE_END_MARK = "% pdfmd: end of embedded preamble"
LUA_MODES = ("embed", "ref", "apply", "off")
EMBED_BLOCK_RE = re.compile(
    r"^(?P<fence>`{3,})\{=pdfmd\}[ \t]*\n(?P<body>.*?)\n(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL)
# FILE_ONLY_OPTION_KEYS (with its comment): lib/pdfmd_assemble (v3.33.38)


# What the command line asks of --embed-metadata: `kinds` None = not named
# (the document's own `pdfmd-options.embed` decides), `lua_mode` None likewise,
# `off` = --no-embed-metadata.
EmbedRequest = namedtuple("EmbedRequest", "kinds lua_mode off")


def option_flag(value) -> bool | None:
    """A pdfmd-options value read as on/off; None when it says neither."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"true", "yes", "on"}:
        return True
    if text in {"false", "no", "off"}:
        return False
    return None


# -- Folder settings (v3.29.10) -----------------------------------------------------------------------------------------
# `.pdfmd/config.yaml` in the document's folder or any folder above it: the same `options:` as the global config, for what is
# under that folder. Nearest first; a layer that says `inherit: false` ends the walk upward; they sit between the document's
# metadata files and the global config (the author's layer order). Only `options:` is read from a folder: `translit`, `setup-ui`
# and `disabled` are this machine's and are ignored there, with a WARN. A folder's options cannot name code: the keys that
# name a Lua filter or a preamble (`lua-filter`, `preamble`) are read from the document's own front matter only, and the
# engine is chosen from pdfmd's list. A file owned by another user (a shared /tmp) is not read. Paths in a folder's options
# (`css: house.css`) are relative to the document, as everywhere, not to the folder file.
# FOLDER_SETTINGS = ".pdfmd/config.yaml": lib/pdfmd_ranking/choice.py (v3.33.19)
FOLDER_WARNED: set[str] = set()


FOLDER_DIR = ".pdfmd"
FOLDER_METADATA = ".pdfmd/metadata.yaml"
MACHINE_KEYS = ("translit", "setup-ui", "disabled")


def folder_file_data(path: Path):
    """The mapping a folder's settings file holds ({} when it is empty), None when there is no such file, or it cannot be
    used: belongs to another user, cannot be read, is not a mapping (each said once, with a WARN)."""
    try:
        if not path.is_file():
            return None
        if hasattr(os, "getuid") and path.stat().st_uid not in (os.getuid(), 0):
            if str(path) not in FOLDER_WARNED:
                FOLDER_WARNED.add(str(path))
                print(f"WARN  {path}: belongs to another user; not read", file=sys.stderr)
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        print(f"WARN  {path}: cannot be read ({error}); ignoring it", file=sys.stderr)
        return None
    if data is None:
        return {}
    if not isinstance(data, dict):
        print(f"WARN  {path}: expected a mapping of settings; ignoring it", file=sys.stderr)
        return None
    return data


@lru_cache(maxsize=None)
def folder_walk(folder: str) -> tuple[tuple[Path, dict | None, Path | None], ...]:
    """((the .pdfmd folder, the mapping of its config.yaml or None, its metadata.yaml or None) ...) from `folder` up, nearest
    first, for each folder that has one of the two files; a config that says `inherit: false` ends the walk (v3.29.29: the
    metadata.yaml of a folder is a layer too)."""
    if yaml is None:
        return ()
    found: list[tuple[Path, dict | None, Path | None]] = []
    here = Path(folder)
    for candidate in (here, *here.parents):
        directory = candidate / FOLDER_DIR
        data = folder_file_data(directory / "config.yaml")
        metadata = directory / "metadata.yaml"
        if folder_file_data(metadata) is None:
            metadata = None
        if data is None and metadata is None:
            continue
        if data is not None:
            machine = sorted(str(key) for key in data if key in MACHINE_KEYS)
            if machine and str(directory / "config.yaml") not in FOLDER_WARNED:
                FOLDER_WARNED.add(str(directory / "config.yaml"))
                print(f"WARN  {directory / 'config.yaml'}: {', '.join(machine)} {'is' if len(machine) == 1 else 'are'} for this "
                      "machine and cannot be set by a folder; ignored", file=sys.stderr)
        found.append((directory, data, metadata))
        if data is not None and str(data.get("inherit", True)).strip().casefold() in ("false", "no", "off", "0"):
            break
    return tuple(found)


def folder_layer_files(folder: str) -> tuple[tuple[str, dict], ...]:
    """((path, options) ...) of the folder layers from `folder` up, nearest first (see FOLDER_SETTINGS)."""
    result = []
    for directory, data, _ in folder_walk(folder):
        if data is not None:
            options = data.get("options")
            result.append((str(directory / "config.yaml"), options if isinstance(options, dict) else {}))
    return tuple(result)


def folder_metadata_files(folder: str) -> list[Path]:
    """The `.pdfmd/metadata.yaml` files of the folder layers from `folder` up, nearest first."""
    return [metadata for _, _, metadata in folder_walk(folder) if metadata is not None]


def is_folder_metadata(path) -> bool:
    return Path(path).name == "metadata.yaml" and Path(path).parent.name == FOLDER_DIR


def is_setup_layer(where: str) -> bool:
    """Whether an option source is a setup (the global config or a folder's) and not a document or its metadata: a mapping
    there without `enabled` stays off."""
    return where == "config" or where.startswith("folder ")


def folder_layers(md_path: Path) -> list[tuple[str, dict]]:
    """The folder layers of a document as (where, options) for option_sources, nearest first."""
    try:
        start = str(md_path.resolve().parent)
    except OSError:
        return []
    return [(f"folder {display_path(Path(path))}", options) for path, options in folder_layer_files(start)]


def option_sources(md_path: Path, metadata_files: list[Path], with_config: bool = True) -> list[tuple[str, dict]]:
    """Where a pdfmd-options key is read, the first one winning: the document's own front matter, its metadata files
    (the later first, as Pandoc takes them: metadata_files_by_priority, v3.27.22), then the config file (pdfmd --setup). Each as (where, mapping); `where` is "document", the metadata file's
    name, or "config"."""
    sources = [("document", frontmatter_pdfmd_options(md_path))]
    for metadata_file in metadata_files_by_priority(metadata_files):
        found = metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append((metadata_file.name, found if isinstance(found, dict) else {}))
    if with_config:
        sources.extend(folder_layers(md_path))
        sources.append(("config", config_options()))              # this one is the global config alone: the folders' are above it
    return sources


def first_pdfmd_option(md_path: Path, metadata_files: list[Path], *names: str, with_config: bool = True):
    """The value of the first of ``names`` that the document's own pdfmd-options, then its metadata files' (the later
    first, metadata_files_by_priority), then the config file's set; None if none does. A mapping is merged field by field with the mappings set below it
    (the first place to set a field wins, v3.27.1), down to a place that sets the key to something else."""
    found: list[dict] = []
    for _, options in option_sources(md_path, metadata_files, with_config):
        for name in names:
            if name in options:
                value = options[name]
                if not isinstance(value, dict):
                    return merge_option_dicts(found) if found else value
                found.append(value)
                break
    return merge_option_dicts(found) if found else None


def resolve_strip_comments(md_path: Path, metadata_files: list[Path], default: bool = False) -> frozenset[str]:
    """The kinds of source whose comments are stripped (see COMMENT_KINDS): the command
    line (--strip-comments / --keep-comments, then --strip-comments-in / --keep-comments-in),
    else `pdfmd-options.strip-comments`, else ``default`` for every kind."""
    if STRIP_COMMENTS_CLI is not None:
        policy = CommentPolicy(STRIP_COMMENTS_CLI)
    else:
        policy = parse_comment_policy(first_pdfmd_option(md_path, metadata_files, "strip-comments"), default)
    return policy.adjusted(STRIP_KINDS_CLI, KEEP_KINDS_CLI).kinds()


def parse_embed_option(value) -> tuple[frozenset[str], str | None] | None:
    """``pdfmd-options.embed``: ``true`` (all four kinds), ``false``, a list
    of kinds, or a mapping -- ``metadata``/``preamble`` as true/false (each on
    unless said otherwise), ``lua`` as a --lua-mode (or true = embed, false =
    off). Returns (kinds, lua mode or None), or None when it asks for nothing."""
    if value is None or value is False:
        return None
    text = str(value).strip().casefold()
    if text == "all":
        return frozenset(EMBED_ALL), None
    if value is True or text in {"true", "yes", "on"}:
        return frozenset(EMBED_KINDS), None
    if text in {"false", "no", "off", "none"}:
        return None
    if isinstance(value, list):
        return frozenset(str(item) for item in value if str(item) in EMBED_ALL), None
    if isinstance(value, dict):
        kinds = {kind for kind in ("metadata", "preamble", "bibliography", "hst")
                 if value.get(kind, True) not in (False, "false", "no", "off")}
        for optional in EMBED_OPTIONAL:
            if value.get(optional) not in (None, False, "false", "no", "off"):
                kinds.add(optional)
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
    for metadata_file in metadata_files_by_priority(metadata_files):
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


# EmbedPlan: lib/pdfmd_assemble (v3.33.38)


def normalized_source(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n") + "\n"


def mask_embedded_blocks(text: str) -> str:
    """``text`` with every embedded block's characters blanked (newlines and
    length kept, so positions still line up): what the BUILD NOTES and
    marker searches look at, so a Lua filter's own text never matches them.
    """
    return EMBED_BLOCK_RE.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)


# render_embedded_block: lib/pdfmd_assemble (v3.33.38)


def is_crlf_text(data: bytes) -> bool:
    """Whether every line end of ``data`` is CRLF and no other CR is in it: a file a block can hold as text (with
    `eol: crlf`) and give back byte for byte."""
    plain = data.replace(b"\r\n", b"")
    return b"\r" not in plain and b"\n" not in plain and data.count(b"\r\n") > 0


# render_embedded_file: lib/pdfmd_assemble (v3.33.38)


# -- The attached source holds its text files, editable (v3.28.39) ------------------------------------------
# After the text: the .tex files it reads (\input), then the CSV and other data, then what was always at the end (filters,
# history, bibliography, citation style), each as a `type: file` block with its path from the document's folder. A block
# can say `also:` (more paths with the same content: two symlinks to one chemicals.tex are one block). The text carries
# `<!-- pdfmd-at: ... -->` comments that say on which line of this very file each one is: one index after the front matter
# and one before each block that names a file (`file="x.csv"`, `\input{x}`). They are rewritten whenever the source is
# written and taken out wherever it is read (strip_location_markers), so a line number never outlives an edit.
# INLINE_SUFFIXES, INLINE_LIMIT and INLINE_ORDER: lib/pdfmd_attach (v3.33.37)
LOCATION_MARK = "pdfmd-at:"
LOCATION_LINE_RE = re.compile(r"^<!-- pdfmd-at: [^\n]*-->[ \t]*\n(?:[ \t]*\n)?", re.MULTILINE)
LOCATION_INDEX_RE = re.compile(r"^<!-- pdfmd-at: index\n.*?\n-->[ \t]*\n(?:[ \t]*\n)?", re.MULTILINE | re.DOTALL)
BLOCK_TYPES = ("file", "lua-filter", "hst", "bibliography", "csl")


def strip_location_markers(text: str) -> str:
    """``text`` without the `<!-- pdfmd-at: ... -->` comments (and the one blank line each brought): the source as it was
    before they were put in. Not inside a fenced block."""
    return LOCATION_LINE_RE.sub("", LOCATION_INDEX_RE.sub("", text))


def first_block_start(text: str) -> int:
    """Where the trailing `{=pdfmd}` blocks (a file, a filter, the history, a bibliography, a style) begin in an assembled
    text: the offset of the first one of those types, len(text) when there is none."""
    for match in EMBED_BLOCK_RE.finditer(text):
        head = match.group("body").partition("\n\n")[0]
        if re.search(r"^type:[ \t]*(?:" + "|".join(BLOCK_TYPES) + r")[ \t]*$", head, re.MULTILINE):
            return match.start()
    return len(text)


# block_places, drop_blocks and drop_duplicate_blocks: lib/pdfmd_attach (v3.33.37)


def outside_folder(name: str) -> bool:
    """Whether a stored path climbs out of the document's folder (`../schemes/x.tex`)."""
    return name.split("/")[0] == ".."


def block_relative_path(name: str) -> str:
    """A path for writing a `type: file` block under a folder that is not the document's (--unpack, the build's own
    folder): the path as it is, with each `..` as `__up__` (as the attachment names do); an absolute one by its name."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or not path.parts:
        return path.name or "file"
    return "/".join("__up__" if part == ".." else part for part in path.parts)


# inline_candidates and inline_blocks: lib/pdfmd_attach (v3.33.37)


def embedded_lines(text: str) -> dict[str, int]:
    """{path or name: the line on which its `{=pdfmd}` block opens (1-based)} for the blocks of ``text``, and `front matter`
    and `preamble` for the front matter's own parts."""
    found: dict[str, int] = {}
    front = re.match(r"^---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
    if front:
        found["front matter"] = 1
        header = re.search(r"^header-includes:", front.group(1), re.MULTILINE)
        if header:
            found["preamble"] = text.count("\n", 0, front.start(1)) + front.group(1).count("\n", 0, header.start()) + 1
    for match in EMBED_BLOCK_RE.finditer(text):
        head = match.group("body").partition("\n\n")[0]
        fields = {key.strip(): value.strip() for key, _, value in (line.partition(":") for line in head.splitlines())}
        if fields.get("type") in BLOCK_TYPES:
            found[fields.get("path") or fields.get("name") or fields["type"]] = text.count("\n", 0, match.start()) + 1
    return found


def reference_names(line: str, names: list[str]) -> list[str]:
    """Which of ``names`` (paths of embedded files) a line of the text points at: `file="x.csv"`, `\\input{x}`."""
    hits: list[str] = []
    for found in re.findall(r"""\bfile\s*=\s*["']([^"']+)["']""", line) + re.findall(
            r"\\(?:input|include|InputIfFileExists)\s*\{([^{}]+)\}", line):
        for name in names:
            if found == name or name in (found + ".tex", found + ".csv") or name.endswith("/" + found):
                if name not in hits:
                    hits.append(name)
    return hits


def with_location_markers(text: str) -> str:
    """``text`` with the `pdfmd-at` comments: an index after the front matter, a line before each block of the text that
    names an embedded file. Their line numbers are those of the text as returned (settled by repeating: the comments
    themselves move what is below them, though never by a different amount)."""
    clean = strip_location_markers(text)
    split = first_block_start(clean)
    body_part, blocks_part = clean[:split], clean[split:]
    front = re.match(r"^---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|$)", body_part, re.DOTALL)
    names = [name for name in embedded_lines(clean) if name not in ("front matter", "preamble")]
    if not names and not (front and "header-includes:" in front.group(0)):
        return clean
    # which block of the body points at which file, and where that block starts (a fence, a div, a paragraph)
    lines = body_part.splitlines(keepends=True)
    starts: dict[int, list[str]] = {}
    fence: tuple[str, int] | None = None
    first = body_part[:front.end()].count("\n") if front else 0
    paragraph = None
    for index in range(first, len(lines)):
        line = lines[index]
        opener = re.match(r"^(`{3,}|~{3,})", line)
        if fence is None and opener:
            fence = (opener.group(1), index)
        elif fence is not None and line.startswith(fence[0]) and line.strip() == fence[0]:
            fence = None
            continue
        if not line.strip():
            paragraph = None
        elif paragraph is None:
            paragraph = index
        if line[:1] in " \t>" or not line.strip():
            continue
        hits = reference_names(line, names)
        if hits:
            start = fence[1] if fence is not None else paragraph if paragraph is not None else index
            for name in hits:
                if name not in starts.setdefault(start, []):
                    starts[start].append(name)
    listing = ["front matter", *(["preamble"] if "preamble" in embedded_lines(clean) else []), *names]
    numbers: dict[str, int] = {}
    result = clean
    for _ in range(4):
        out = []
        for index, line in enumerate(lines):
            for name in starts.get(index, []):
                out.append(f"<!-- {LOCATION_MARK} {name} @ line {numbers.get(name, 0)} -->\n\n")
            out.append(line)
        marked = "".join(out)
        entries = "".join(f"{name:<40} line {numbers.get(name, 0)}\n" for name in listing)
        index_text = f"<!-- {LOCATION_MARK} index\n{entries}-->\n\n"
        cut = front.end() if front else 0          # the markers are all after the front matter: it is still the first characters
        result = marked[:cut] + index_text + marked[cut:] + blocks_part
        found = embedded_lines(result)
        fresh = {name: found[name] for name in listing if name in found}
        if fresh == numbers:
            break
        numbers = fresh
    return result


# safe_relative_path, parse_embedded_blocks, and the trust store (its comment, trust_store_path, trusted_hashes and
# remember_trusted): lib/pdfmd_assemble (v3.33.38)


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
            write_text_lf(target, block["source"])
            paths.append(target)
            print(f"AUTO LUA  {display_path(md_path)}: embedded filter {label}")
        yield paths
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# split_preamble_parts, unpack_assembled and slim_assembled: lib/pdfmd_assemble (v3.33.38)


_RESOURCE_OWNER: Path | None = None


# embedded_resources (_RESOURCE_OWNER, the state it keeps, stays here): lib/pdfmd_assemble (v3.33.38)


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


# literal_block: lib/pdfmd_assemble (v3.33.38)


def header_includes_text(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item is not None)
    return "" if value is None else str(value)


# strip_embedded_option_names, relative_filter_path, lua_checks_format, apply_lua_filters and embed_into_text:
# lib/pdfmd_assemble (v3.33.38)


REWRITE_CLI: bool | None = None


# --bopen SPEC (v3.28.20): which of a batch's finished files are opened. A spec is a comma list of selectors, each with
# any whole number N from 1: fN the first N, lN the last N, flN the first half and the last half (the first gets the odd
# one: fl15 = 8 + 7), eN every Nth (the Nth, the 2Nth ...), all (or no spec). The files chosen by any selector open, once
# each, in the order the batch lists them.


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


def cmd_part(text: str, quote: bool = True) -> str:
    """One word of the CMD line. The line is a command to run again, so a path is never written with `..` (it would mean
    something else from another folder): under the working folder it is relative, under the home folder ``~/...`` (v3.31.41,
    entry 3ea; the shell expands the tilde, so it stays outside the quotes), else absolute, per `path-style`. Words that are
    not absolute paths are untouched."""
    if not os.path.isabs(text):
        return shlex.quote(text) if quote else text
    shown = display_path(Path(text), up=0)
    if shown == "~" or shown.startswith(("~/", "~\\")):
        rest = shown[2:].replace(os.sep, "/")
        return "~" if shown == "~" else "~/" + (shlex.quote(rest) if quote else rest)
    return shlex.quote(shown) if quote else shown


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
    line = "CMD  " + " ".join(cmd_part(str(part)) for part in cmd) + f"  (cwd={cmd_part(str(cwd), quote=False)})"
    if not verbose:
        record_note(line)             # the record has it whatever --verbose said
        return
    print(line, file=sys.stderr)


# engine_failure_reason, TEX_CAUSES, TEX_PACKAGES and tex_failure_cause: lib/pdfmd_tex (v3.33.36)
# TEX_PROBE_DOCUMENT, TEX_PROBES, probe_tex_cause, SHOWN_LOCATIONS, LATEX_CONTEXT_RE, source_line_for, latex_error_location and
# report_engine_failure: lib/pdfmd_tex/failure.py (v3.33.237)


# Direct .tex compilation (v3.1.0): the comment, its constants and the functions above tex_argument: lib/pdfmd_tex (v3.33.36)
# tex_argument: lib/pdfmd_tex/failure.py (v3.33.237)


# latex_engine_command and run_tex_engine: lib/pdfmd_tex (v3.33.36)


LAST_SEEDED = 0   # labels a partial cache build took from the last full build


# cache_root: lib/pdfmd_cache/__init__.py (v3.33.33)


# -- Probes: a version or a capability asked of a program ----------------------------------------------------------------
# `pandoc --version`, `kpsewhich`, `typst --version` ... answer at once; a hung one (a broken install, a network drive, a tool
# waiting on a prompt) must not hang pdfmd. A probe gets PROBE_TIMEOUT seconds, and one that does not answer counts as "not
# available" (a verbose line says so). Never used for a command that builds something (Pandoc, a LaTeX engine, a converter):
# those take as long as the document needs.
PROBE_TIMEOUT = 10


def run_probe(command: list, **options) -> "subprocess.CompletedProcess | None":
    """``subprocess.run`` of a probe: output captured as text, PROBE_TIMEOUT s. None when the program cannot be started or does
    not answer in time. The text is read as UTF-8 (what kpsewhich, Pandoc and fc-list write), a byte that is not UTF-8
    replaced: left to `text=True` alone, Windows would decode with the console's code page (issue 13)."""
    options.setdefault("capture_output", True)
    options.setdefault("text", True)
    options.setdefault("encoding", "utf-8")
    options.setdefault("errors", "replace")
    try:
        return subprocess.run(command, timeout=PROBE_TIMEOUT, **options)
    except subprocess.TimeoutExpired:
        if VERBOSE_OUTPUT:
            asked = " ".join(Path(str(command[0])).name if index == 0 else str(word) for index, word in enumerate(command[:3]))
            print(f"AUTO PROBE  {asked}: no answer in {PROBE_TIMEOUT} s; counted as not available")
        return None
    except OSError:
        return None


# TEMPORARY_PLACES, folder_is_writable and temporary_place: lib/pdfmd_cache/__init__.py (v3.33.33)


# CACHE_LOCATION_NAMES: lib/pdfmd_cache/__init__.py (v3.33.33)
CACHE_LOCATION_CLI: str | None = None     # --cache-location (set in main)


# cache_location and document_cache_root: lib/pdfmd_cache/__init__.py (v3.33.33)


# source_fingerprint: lib/pdfmd_cache/__init__.py (v3.33.33)


# adopt_moved_cache and cache_directory: lib/pdfmd_cache/__init__.py (v3.33.33)


# -- Which engine built the file, and --strict (v3.26.10) --------------------------------------------------------
# The closing line names the engine that made a PDF (`OK    report.md  (lualatex)`) and, when an earlier one was tried
# and failed, which (`(typst; lualatex failed)`): a build that quietly fell back used to look the same as one that did
# not. `--strict` (or `pdfmd-options: {strict: true}`) turns a build that printed any WARN line, or that Pandoc warned
# about, into a failed file (its output is kept; the exit code is 1), for scripts and CI.
STRICT_CLI: bool | None = None             # --strict / --no-strict (set in main)
ENGINE_CLI: str | None = None              # -e as given ("" a bare -e), for lib/pdfmd_chain's pinned engine (set in main)
ENGINE_FALLBACK_CLI: str | None = None     # --engine-fallback MODE (lib/pdfmd_chain; set in main)


# -- Size budgets: --max-asset-mb, --max-output-mb (v3.26.18) -----------------------------------------------------
# A picture of 30 MB or a PDF that no mail server takes is found out late. With a budget set (the command line, else
# `pdfmd-options: {max-asset-mb: 5, max-output-mb: 20}`), a build says which image is over it before it starts and
# which file is over after it, as WARN lines (so --strict fails them); `--check` reports the images (asset-large).
# The command line reaches -j workers as PDFMD_MAX_ASSET_MB / PDFMD_MAX_OUTPUT_MB, as --strict does.


# -- A `$...$` that is not math: the closing `$` is followed by a digit (v3.32.48) ----------------------------------
# Pandoc reads `$...$` as math only when the closing `$` has no space before it and no digit after it (so that
# "costs $5 or $10" stays text). `$\geq$3` and `$\pm$10` are therefore text, with the dollars printed (the gfm
# reader) or the dollars printed and the command run in text mode (Pandoc's Markdown), and nothing says so; in
# a LaTeX build the text-mode `\geq` then lacks a glyph in the main font. The leftover is found in the AST
# the reader gave, where a failed `$...$` is plain Str / raw TeX and a real one is Math.


# -- The cross-references of a part built alone, counted from the sources (v3.26.0; see pdfmd_labels) --------------
# `pdfmd-options: {seed-labels: auto|aux|scan|draft|off}` / --seed-labels. A partial build (a part, or a section of an
# ordinary document) used to know the labels of the rest only from the last full build's .aux (cache on). The scan
# does not need that build: Pandoc writes the LaTeX of the WHOLE document once more (no images, no engine), pdfmd_labels
# reads which headings, captions, equations and labels it holds, and LaTeX replays those at the start of the part, so
# the document's own number style applies. The .aux, when there is one, still comes first.
SEED_LABELS_CLI: str | None = None         # --seed-labels (set in main)
LAST_SCANNED = 0                           # labels the last build took from the scan (for the closing NOTE)
LAST_EXACT = False                         # ... and whether they came from a draft pass
LAST_SKIPPED = 0                           # ... and how many it left out (after a caption it could not count)
LAST_WHOLE = False                         # the last build numbered the whole document and kept the part (select.lua)


# pdfmd_labels_modes: lib/pdfmd_args (v3.33.40)


SEED_CALC_CLI: str | None = None           # --seed-calc (set in main)


# -- Plot cache (pdfmd-options: {cache: {plots: true}}, --cache-plots) --------
# A package's picture macros (nulabreport >= 1.26.0, section 15b, was the first) look each whole
# picture up by a key; on a hit they include the PDF stored here at the
# stored size, on a miss they typeset as always and log the call to
# <jobname>.pdfmdreq. After the build pdfmd renders those logged calls, each in
# a small standalone job that loads the SAME preamble the document used (cut
# from the generated .tex) and ships the picture out as a page of exactly its
# size, ready for the next build. The finished PDF never depends on this having
# worked: a miss is an ordinary inline plot.
#
# What stops it going stale, since a stale plot would be worse than a slow one:
#   * the directory is keyed by a hash of everything the picture can depend on
#     apart from its own arguments -- the packages' style files, the
#     document's whole preamble (fonts, settings, preamble.tex, header-includes),
#     the engine's version, when TeX Live's packages last changed (its package
#     database, rewritten by every `tlmgr update`), and this cache's format -- so a
#     changed package or setting simply lands in a new directory, and the old one
#     is pruned;
#   * every entry records the files its standalone job actually read (LaTeX's
#     own recorder, not a guess at argument names) under the report's folders and
#     the user's own TeX trees (TEXMFHOME, TEXMFLOCAL: a package's vendored files),
#     with their SHA-1, and is dropped before the next build if any of them
#     changed or vanished -- a CSV edit shows up;
#   * the key includes the picture's arguments and the layout it read (text
#     height/width, font size), so a different call or a different page
#     geometry is a different entry.
# The directories live in the document's own cache folder (v3.27.28; they were
# shared by every document, and the three newest were kept, so building three
# other reports threw a report's plots away). What pdfmd itself adds to one build's
# preamble (a part's label replay, which names a temporary file, and the counter
# markers) is left out of the preamble the plots are keyed by and drawn with, and the
# key leaves out the title, which a part does not typeset (plot_key_text), so a part
# built alone uses the full build's plots instead of a directory of its own. A part
# whose preamble really differs (Pandoc writes the citation commands only for a part
# that cites, table packages only for one with tables) keeps a directory of its own,
# drawn once and reused at its next build: eight are kept per document.
# PLOT_CTX_TWICE, PLOT_CTX_MARGIN and PLOT_CTX_PLAIN: lib/pdfmd_tex (v3.33.36)
CACHE_PLOTS_CLI: bool | None = None   # --cache-plots (set in main)


def kpsewhich_path(name: str) -> Path | None:
    kpsewhich = which("kpsewhich")
    if not kpsewhich:
        return None
    done = run_probe([kpsewhich, name])
    found = done.stdout.strip().splitlines() if done else []
    return Path(found[0]) if found else None


@lru_cache(maxsize=None)
def engine_version_line(engine: str) -> str:
    program = engine
    if engine == "soffice":                    # found beyond PATH too; on Windows soffice.exe is the window launcher, which does not
        program = engine_executable("soffice") or engine      # answer --version and leaves soffice.bin running: soffice.com does
        if os.name == "nt" and Path(program).suffix.lower() == ".exe" and Path(program).with_suffix(".com").is_file():
            program = str(Path(program).with_suffix(".com"))
    done = run_probe([program, "--version"])
    out = done.stdout if done else ""
    return out.splitlines()[0] if out else ""


def typst_version() -> tuple[int, ...]:
    """The version of the `typst` on PATH, (0,) when there is none or it says something else."""
    found = re.search(r"(\d+(?:\.\d+)+)", engine_version_line("typst"))
    return tuple(int(part) for part in found.group(1).split(".")) if found else (0,)


# tex_tree_stamp: lib/pdfmd_tex (v3.33.36)


# plot_preamble: lib/pdfmd_tex (v3.33.36)


# plot_recorded_inputs, render_plot_requests, AUX_CLEAN_SUFFIXES and compile_tex_direct: lib/pdfmd_tex (v3.33.36)


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


# run_soffice_convert, convert_office_direct and convert_via_soffice_bridge: lib/pdfmd_bridge/__init__.py (v3.33.26)


# PANDOC_TABLE_STYLE_RE, CALIBRE_TABLE_CSS, calibre_html_command, calibre_page_options and run_calibre: lib/pdfmd_bridge/__init__.py (v3.33.26)


# start_soffice_job: lib/pdfmd_bridge/__init__.py (v3.33.26)


# run_calibre_convert, browser_page_css and run_browser_print: lib/pdfmd_bridge/__init__.py (v3.33.26)


# -- Source attached to the PDF (v3.22.1) ---------------------------------------
# `pdfmd-options: {attach-source: true}` (alias `embed-source`), --attach-source:
# after a successful PDF build, the document's whole source -- the assembled
# Markdown of --assemble-only with every kind embedded, the same file that
# builds the same PDF anywhere -- is attached to the PDF as a file attachment
# (PDF's own /EmbeddedFiles, listed by any viewer), beside a small manifest that
# records the original layout (file names and where they sat, a part's
# boundaries and its dropped front matter, the images the text points at).
# `pdfmd --restore FILE.pdf` writes the layout back. Comments are stripped from
# the attached copy unless strip-comments says otherwise (they are notes to
# oneself; a PDF travels). Engine-independent (pypdf, after the build), and
# nothing is attached unless asked for: the source holds everything the author
# wrote, comments and drafts included.
# The manifest's `format`: 1 = the layout of v3.22 to v3.28.37 (files as attachments); 2 = v3.28.38 and later (the chain of
# folders, text files as blocks of the source with line markers, `eol: crlf`, `..` files). A pdfmd that reads up to 1 refuses a
# 2 with "upgrade pdfmd" instead of restoring half of it; this one reads both. 3 = v3.31.36: the manifest holds `layers`, the
# options of the folder settings the build used, restored to `.pdfmd/config.yaml`; a pdfmd that does not know them would
# restore a report that builds differently. It is written ONLY for a source that has layers: every other manifest stays 2,
# so a PDF is not refused by an older pdfmd for nothing.
ATTACH_FORMAT = 3
# ATTACH_FORMAT_PLAIN: lib/pdfmd_attach (v3.33.37)
ATTACH_MANIFEST = "pdfmd-manifest.json"
ATTACH_SOURCE = "pdfmd-source.md"
ATTACH_KEYS = ("attach-source", "embed-source")
ATTACH_CLI: bool | None = None
# --bundle [all] / --no-bundle: None (the document decides), "off", "referenced", "all".
BUNDLE_CLI: str | None = None
BUNDLE_MAX_MB = 100
# --verbose: --restore and --unpack list every file instead of counting them by folder (v3.28.15)
VERBOSE_OUTPUT = False
# --attach-bibliography used|all (None: the document's pdfmd-options decide).
BIB_ATTACH_CLI: str | None = None
CSL_ATTACH_CLI: bool | None = None    # --attach-csl / --no-attach-csl
# --bundle-packages / --no-bundle-packages (None: the document decides).
BUNDLE_PACKAGES_CLI: bool | None = None
EXTRA_PREFIX = "files/"
RESTORED_SUFFIX = ".restored"
# GLOBAL_LAYOUT_PATH (with its comment) and RAW_REFERENCE_RES: lib/pdfmd_attach (v3.33.37)
BUNDLE_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", "venv", "env"})
# BUNDLE_SKIP_SUFFIXES, PATH_TOKEN_RE, REFERENCE_EXTENSIONS and SCANNED_SUFFIXES, with their comments: lib/pdfmd_attach (v3.33.37)
IMAGE_REF_RE = re.compile(
    r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)|<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"']",
    re.IGNORECASE)


def resolve_attach(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether the PDF built from ``md_path`` carries its source: the command
    line, else `pdfmd-options.attach-source` (or `embed-source`)."""
    if resolve_bundle(md_path, metadata_files):
        return ATTACH_CLI is not False           # a bundle is a source plus files; --no-attach-source still wins
    if ATTACH_CLI is not None:
        return ATTACH_CLI
    return bool(option_flag(first_pdfmd_option(md_path, metadata_files, *ATTACH_KEYS)))


def option_flag_number(value) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def resolve_bundle(md_path: Path, metadata_files: list[Path]) -> str | None:
    """``None`` (no bundle), "sources" (the files the text reads: LaTeX inputs and data, never images),
    "referenced" (those and the images) or "all" (everything in the document's folder worth keeping):
    the command line, else `pdfmd-options.bundle` (sources / true / all / false)."""
    if BUNDLE_CLI is not None:
        return None if BUNDLE_CLI == "off" else BUNDLE_CLI
    value = first_pdfmd_option(md_path, metadata_files, "bundle")
    word = str(value).strip().casefold()
    if word in ("all", "sources", "referenced"):
        return word
    if word == "source":
        return "sources"
    return "referenced" if option_flag(value) else None


# attached_bundle_mode: lib/pdfmd_attach (v3.33.37)


def extra_key(path: str) -> str:
    """The attachment name of a stored file: `../schemes/x.tex` is `files/__up__/schemes/x.tex` (a viewer that saves an
    attachment by its name must not climb out of its folder)."""
    return EXTRA_PREFIX + "/".join("__up__" if part == ".." else part for part in path.split("/"))


def relative_posix(base: Path, path: Path) -> str:
    # not resolve(): a symlinked metadata file is recorded where it sits, not where it points
    return Path(os.path.relpath(os.path.abspath(path), os.path.abspath(base))).as_posix()


# layout_path and referenced_images: lib/pdfmd_attach (v3.33.37)


# The comment on the user's own TeX tree, PACKAGE_RE, CLASS_RE, TEX_INPUT_RE and PROVIDES_RE: lib/pdfmd_attach (v3.33.37)
GRAPHIC_RE = re.compile(r"\\includegraphics\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
# GRAPHIC_SUFFIXES, BUNDLE_IMAGE_SUFFIXES (with its comment), TEX_SOURCE_SUFFIXES and TEX_TREE_SCAN_LIMIT: lib/pdfmd_attach (v3.33.37)


# tex_distribution_roots, GRAPHIC_ARGUMENT_RE, MACRO_VALUE_RE and graphic_names_in to bundle_reach: lib/pdfmd_attach (v3.33.37)


def drop_calc_export(md_path: Path, sources: list[Path], metadata_files: list[Path], found: list[Path], outside: list) -> None:
    """The file `calc: {export: FILE}` writes is an output: it does not go with the source (v3.30.22), though its name stands in the
    front matter and the file is there. It stays when it is also read: it is the constants file, or the body of the document
    names it (a `.csv` div reading last time's results)."""
    LEADING_FRONT_MATTER_RE = sys.modules[__name__].LEADING_FRONT_MATTER_RE
    target = calc_export_file(md_path, metadata_files)
    if target is None:
        return
    target = Path(os.path.abspath(target))
    try:
        constants = calc_constants_file(md_path, metadata_files)
    except SystemExit:
        constants = None
    if constants is not None and Path(os.path.abspath(constants)) == target:
        return
    for source in sources:
        if target.name in LEADING_FRONT_MATTER_RE.sub("", read_text_best_effort(source), count=1):
            return
    found[:] = [item for item in found if Path(os.path.abspath(item)) != target]
    outside[:] = [item for item in outside if Path(os.path.abspath(str(item))) != target]


def add_calc_constants(md_path: Path, metadata_files: list[Path], base: Path, represented: set[Path],
                       found: list[Path], outside: list[str]) -> None:
    """The calculator's constants file (`calc: {constants: FILE}`) goes with the source like the history file (v3.30.12): a name
    in a metadata file is no path the text mentions, so the scan for referenced files would not find it."""
    try:
        constants = calc_constants_file(md_path, metadata_files)
    except SystemExit:
        return
    if constants is None:
        return
    constants = Path(os.path.abspath(constants))
    if constants in found or constants in represented:
        return
    (found if constants.is_relative_to(base) else outside).append(constants if constants.is_relative_to(base) else str(constants))


# bundle_files, attachment_manifest and attached_source: lib/pdfmd_attach (v3.33.37)


def comments_note(manifest: dict) -> str:
    """'comments stripped (markdown, preamble)' / 'comments kept' from a manifest
    (format 1 once held a plain true/false: all of the Markdown's)."""
    stripped = manifest.get("comments_stripped")
    if isinstance(stripped, list):
        return f"comments stripped from {', '.join(stripped)}" if stripped else "comments kept"
    return "comments stripped" if stripped else "comments kept"


# resolve_bibliography_pruning, resolve_csl_attach, add_deflated_attachment, write_pdf_attachments and read_pdf_attachments: lib/pdfmd_attach (v3.33.37)


# FONT_KEYS and resolve_bundle_packages: lib/pdfmd_attach (v3.33.37)


def front_matter_dict(text: str) -> dict:
    LEADING_FRONT_MATTER_RE = sys.modules[__name__].LEADING_FRONT_MATTER_RE
    front = LEADING_FRONT_MATTER_RE.match(text)
    if not front or yaml is None:
        return {}
    try:
        loaded = yaml.safe_load(front.group("yaml"))
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


# attachment_requirements: lib/pdfmd_attach (v3.33.37)


def requirement_lines(manifest: dict) -> list[str]:
    """What a rebuild needs that the PDF does not carry, one line a kind (packages, graphics), then the fonts
    and (--verbose) what made the PDF."""
    needs = manifest.get("requirements") or {}
    lines = []
    missing: dict[str, list[str]] = {}
    for item in needs.get("tex") or []:
        if not item.get("stored"):
            version = f" ({item['version']})" if item.get("version") else ""
            missing.setdefault(item["kind"], []).append(f"{item['name']}{version}")
    for kind, names in missing.items():
        lines.append(f"NEEDS     {kind}{'s' if len(names) != 1 else ''} {', '.join(names)}: from the author's own TeX "
                     "tree, not stored (install it, or build with bundle-packages)")
    for kit in manifest.get("kits") or []:
        lines.append(f"KIT       {kit['name']}" + (f" {kit['version']}" if kit.get("version") else "")
                     + (f" (mode {kit['mode']})" if kit.get("mode") else "")
                     + (f": its {len(kit['carried'])} parts are stored" if kit.get("carried") else "")
                     + "; what it wrote is in the source (`kit: none` says so), so a rebuild needs no kit")
    layers = (manifest.get("layers") or {}).get("options")
    if layers:
        lines.append(f"FOLDER    settings the build used: {', '.join(str(key) for key in layers)}"
                     f"; written to {FOLDER_DIR}/config.yaml of the restored folder")
    if needs.get("fonts"):
        lines.append(f"NEEDS     fonts: {', '.join(needs['fonts'])}")
    made = [f"pdfmd {needs['pdfmd']}" if needs.get("pdfmd") else "", f"pandoc {needs['pandoc']}" if needs.get("pandoc") else "",
            needs.get("producer") or "", needs.get("texlive") or "", needs.get("platform") or "",
            needs.get("created") or ""]
    if any(made):
        lines.append(f"MADE WITH {', '.join(item for item in made if item)}")
    return lines


# folder_counts: lib/pdfmd_restore/__init__.py (v3.33.29)


# csv_block_files, source_attachments and attach_source_after_success: lib/pdfmd_attach (v3.33.37)


# -- Markdown that carries its source (v3.26.4) -----------------------------------
# `--keep-source [packed|readable]`, `pdfmd-options: {keep-source: true|packed|readable}`: a Markdown output (--to gfm,
# gfm+raw, markdown, commonmark ...) ends with one HTML comment holding the same entries --attach-source puts into a PDF
# (see pdfmd_flat/keep.py for the encodings and why nothing in the source can close the comment). `pdfmd --restore
# FILE.md` writes them back into FILE.restored/. A whole build only (not a part or a section), like --attach-source.
KEEP_SOURCE_CLI: str | bool | None = None
MARKDOWN_TARGETS = frozenset({"gfm", "gfm+raw", "markdown", "commonmark", "commonmark_x", "markdown_strict"})


def resolve_keep_source(md_path: Path, metadata_files: list[Path]) -> str | None:
    """"packed", "readable" or None: the command line, else `pdfmd-options.keep-source`."""
    value = KEEP_SOURCE_CLI if KEEP_SOURCE_CLI is not None else first_pdfmd_option(md_path, metadata_files, "keep-source")
    if value in (None, False) or str(value).strip().casefold() in ("", "false", "no", "off", "0"):
        return None
    name = str(value).strip().casefold()
    if value is True or name in ("true", "yes", "on", "1"):
        return "packed"
    if name not in ("packed", "readable"):
        raise SystemExit(f"keep-source {value!r}: choose packed (the default), readable, or false")
    return name


# keep_source_after_success: lib/pdfmd_attach (v3.33.37)


# -- The images the PDF itself carries (v3.22.6) --------------------------------
# A plain attach (no --bundle) does not store the images the text points at, but the PDF
# holds every one it drew. The manifest records, for each, which picture of the PDF is
# it, and --restore takes it out again: a JPEG is the very same bytes (every engine
# embeds the file's own stream), a PNG or other raster comes back as a PNG of the
# pixels the PDF holds (the picture is the same; the file is not byte-identical, and an
# alpha channel is kept), an SVG or PDF figure as a one-page PDF of the vector drawing
# (a restored `fig.svg` is `fig.pdf`, and the restored Markdown points at it). A picture
# is found by its size and its order in the PDF, a JPEG by its bytes; a figure drawn by
# something other than an image or a form (TikZ, pgfplots) was never a file.
# (the PNG helpers, the picture search and extraction and the image-path rewriting moved to lib/pdfmd_pdfimages, v3.33.14)


# restored_image_paths: lib/pdfmd_restore/__init__.py (v3.33.29)


# -- PDF in, Markdown out (v3.22.7) ---------------------------------------------
# A PDF given to pdfmd is read, not built: the direction follows the files (a .pdf input,
# `-o x.md`, `--to md`). If the PDF carries a pdfmd source it is restored (see --restore),
# the exact thing that was written; otherwise the pages are read by batchocr, which owns
# all of the PDF-to-Markdown work (text layer or OCR, reading order, headings, tables)
# and which pdfmd only finds, checks the version of, and hands the PDF and every flag
# pdfmd does not know itself -- as unknown flags go to Pandoc when a PDF is built.
# BATCHOCR_REPOSITORY and BATCHOCR_TAG: lib/pdfmd_routing/__init__.py (v3.33.25)
BATCHOCR_MIN = (1, 2, 4)
# BATCHOCR_TEXT_MIN, PDF_READ_FORMATS, batchocr_spec and find_batchocr: lib/pdfmd_routing/__init__.py (v3.33.25)


def batchocr_version(command: list[str]) -> tuple[int, ...] | None:
    try:
        text = subprocess.run([*command, "--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=60).stdout
        return tuple(int(part) for part in re.search(r"(\d+(?:\.\d+)+)", text).group(1).split("."))
    except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
        return None


# What batchocr needs from the system for scanned pages: Tesseract (OCR) and Poppler (pdftotext,
# pdftoppm). They are programs with their own licences and per-platform builds, so pdfmd never
# bundles them; it asks the system's package manager (`pdfmd --install batchocr`).
# manager -> (install command, {tool: packages}, how to add OCR languages)
OCR_PACKAGE_MANAGERS = {
    "brew": (["brew", "install"], {"tesseract": ["tesseract"], "poppler": ["poppler"]},
             "brew install tesseract-lang"),
    "apt-get": (["apt-get", "install", "-y"], {"tesseract": ["tesseract-ocr"], "poppler": ["poppler-utils"]},
                "apt-get install tesseract-ocr-rus  (tesseract-ocr-LANGUAGE)"),
    "dnf": (["dnf", "install", "-y"], {"tesseract": ["tesseract"], "poppler": ["poppler-utils"]},
            "dnf install tesseract-langpack-rus  (tesseract-langpack-LANGUAGE)"),
    "pacman": (["pacman", "-S", "--needed", "--noconfirm"],
               {"tesseract": ["tesseract", "tesseract-data-eng"], "poppler": ["poppler"]},
               "pacman -S tesseract-data-rus  (tesseract-data-LANGUAGE)"),
    "zypper": (["zypper", "install", "-y"], {"tesseract": ["tesseract-ocr"], "poppler": ["poppler-tools"]},
               "zypper install tesseract-ocr-traineddata-russian"),
    "apk": (["apk", "add"], {"tesseract": ["tesseract-ocr"], "poppler": ["poppler-utils"]},
            "apk add tesseract-ocr-data-rus  (tesseract-ocr-data-LANGUAGE)"),
    "scoop": (["scoop", "install"], {"tesseract": ["tesseract"], "poppler": ["poppler"]},
              "scoop install tesseract-languages"),
    "choco": (["choco", "install", "-y"], {"tesseract": ["tesseract"], "poppler": ["poppler"]},
              "download LANGUAGE.traineddata from github.com/tesseract-ocr/tessdata_fast into Tesseract's tessdata folder"),
    "winget": (["winget", "install", "-e", "--id"], {"tesseract": ["UB-Mannheim.TesseractOCR"], "poppler": []},
               "the installer offers languages; Poppler is not in winget (use scoop or choco)"),
}


def system_package_manager() -> str | None:
    """The first package manager of OCR_PACKAGE_MANAGERS this system has."""
    order = {"darwin": ("brew",), "win32": ("scoop", "choco", "winget")}.get(
        sys.platform, ("apt-get", "dnf", "pacman", "zypper", "apk", "brew"))
    return next((name for name in order if which(name)), None)


def ocr_install_command(manager: str, tools: tuple[str, ...] = ("tesseract", "poppler")) -> list[str]:
    """The command that installs `tools` with `manager` (sudo in front where the system wants it)."""
    command, packages, _ = OCR_PACKAGE_MANAGERS[manager]
    names = [name for tool in tools for name in packages[tool]]
    needs_root = (manager in ("apt-get", "dnf", "pacman", "zypper", "apk") and hasattr(os, "geteuid")
                  and os.geteuid() != 0 and which("sudo"))
    return (["sudo"] if needs_root else []) + command + names


def tesseract_install_hint() -> str:
    manager = system_package_manager()
    if manager:
        return shlex.join(ocr_install_command(manager))
    return {"darwin": "brew install tesseract poppler",
            "win32": "scoop install tesseract poppler (or choco install tesseract poppler)"}.get(
        sys.platform, "sudo apt install tesseract-ocr poppler-utils (or your package manager's equivalents)")


# install_ocr_tools, batchocr_missing_message and pdf_read_target: lib/pdfmd_routing/__init__.py (v3.33.25)


# An ebook as input (v3.29.1). Pandoc reads an EPUB but not a MOBI, an AZW3, a KEPUB, a LIT, an LRF ...; Calibre turns those
# into an EPUB, and Pandoc turns the EPUB into Markdown (with its pictures) in a scratch folder: the document is then built as
# any Markdown file is, to the PDF (or the format) named, beside the book. (An EPUB goes straight to Pandoc.) The Markdown
# is the editable form: `pdfmd book.mobi -o book.md` keeps it. DRM-protected books and ebooks that are only pictures
# (comics, scans: no text for Pandoc to read) are not handled.
# EBOOK_INPUT_EXTENSIONS and route_ebook_input: lib/pdfmd_routing/__init__.py (v3.33.25)


PDF_TO_STDOUT_CLI = False        # set by `-o -` on PDF inputs (v3.30.39)


# route_pdf_input, text_to_markdown_mode and route_text_input: lib/pdfmd_routing/__init__.py (v3.33.25)


# RESTORE_CHAIN, restore_chain and the rest of the restore code (restore_target_name to layout_from_source): lib/pdfmd_restore/__init__.py (v3.33.29)


# --- Finishing the built PDF: bookmarks, running header/footer, linked files ----------------
# Ideas from mdpdf (MIT, github.com/normanlorrain/mdpdf): a small Markdown-to-PDF tool whose own
# renderer needs PyMuPDF (AGPL), which pdfmd does not use. The ideas are done here on the finished
# PDF with pypdf, so they work with every engine: headings become PDF bookmarks (when the engine
# made none), a "left,middle,right" template prints a running header and footer, and local files
# the document links to are attached to the PDF with a paperclip in the margin beside the link. All of it is
# off unless asked for (`--bookmarks`, `--header`, `--footer`, `--attach-links`, `--pdf-title` ...),
# except under the `mdpdf` command, which asks for bookmarks and attachments like mdpdf does.

POLISH_CLI: dict = {}                       # filled in by main() from the command line
PAPER_CLI: str | None = None                # --paper, also used by the native renderers
INKMD_CLI: dict = {}                        # inkmd's own compile options, from the command line


# `parse_hf_template`, `fill_hf_field`, `markdown_headings`, `search_form`, `locate_headings`, `outline_entries`, `hf_text`,
# `hf_overlay`, `local_file_of_link`, `polish_wanted` and `polish_pdf` (with `HF_FIELDS`, `HF_FONT`, `HF_SIZE`, `HF_MARGIN` and
# `LINKED_FILE_LIMIT`) live in `pdfmd_polish` (v3.33.13); the re-exports are in the binding block above.


# (the `mdpdf`, `md2pdf`, `inkmd`, `batchmd` and `pan-tec` command translations moved to lib/pdfmd_compat, v3.33.15; their *_main entry points are re-exported in the binding block)


# The hybrid PDF (v3.25.10): lib/pdfmd_hybrid (its explanation is there). These two stay: main() rebinds the first,
# the attachment readers above read the second.
HYBRID_CLI: bool | None = None
HYBRID_MIME = {"odt": "application/vnd.oasis.opendocument.text", "odp": "application/vnd.oasis.opendocument.presentation",
               "ods": "application/vnd.oasis.opendocument.spreadsheet"}


# build_parser: lib/pdfmd_args (v3.33.40)


WATCH_INTERVAL = 1.0


# What main() keeps in module globals from the command line: every *_CLI name, and these. -j workers are fresh processes
# (macOS and Windows spawn them, they do not fork), so they get a copy of it (v3.27.3); before that, --line-numbers,
# --fallback, --raw, --keep-source ... did not reach a document built by a worker. tests/test_jobs.py checks that every
# `core.NAME = ...` of run_main (lib/pdfmd_run) is covered.
WORKER_GLOBALS = ("SHOW_FULL_PATHS", "PATH_STYLE", "PATH_UP", "CITEPROC_DISABLED", "FUZZY_LOOKUP", "PART_CUTS", "VERBOSE_OUTPUT")


def worker_state() -> dict:
    return {name: value for name, value in globals().items()
            if (name.endswith("_CLI") or name in WORKER_GLOBALS) and not callable(value)}


def restore_worker_state(state: dict) -> None:
    globals().update(state)
    pdfmd_view.tolerant_streams()
    AUTO_LOG.quiet = True      # the parent prints what a batch found; a worker's summary would repeat per file (v3.28.16)


# Whole features switched off (v3.27.8): `disabled: [history, tables]` in config.yaml (pdfmd --setup, d) names topics of
# pdfmd_help.TOPICS; their options leave --help, completion and the setup screen, and the command line refuses them
# unless --disabled is given. What a document's own pdfmd-options asks for still applies: a document from someone
# else builds the same.
DISABLED_WARNED = False


def main() -> None:
    """The command: Ctrl-C ends it with one line and the usual exit status 130, not a traceback (v3.30.14). Pandoc and the
    engines are in the same terminal group and get the signal too; the temporary folders are removed on the way out."""
    pdfmd_view.tolerant_streams()      # a character the console's code page lacks prints as `?`, never a traceback
    try:
        run_main()
    except KeyboardInterrupt:
        try:
            sys.stderr.write("\nInterrupted (Ctrl-C).\n")
            sys.stderr.flush()
        except OSError:
            pass
        raise SystemExit(130) from None


# ---------------------------------------------------------------------------
# Python API: `import pdfmd; pdfmd.convert_file("report.md", "docx")`
#
# Every call runs the command-line tool as a subprocess (what pypandoc does with Pandoc): the CLI keeps its
# module-level state to itself, a failure cannot take the caller down, and what you get is what `pdfmd`
# would have made. Nothing is written into the source unless asked (`stamp=True`, `backup=True`).

__all__ = ["PdfmdError", "convert_file", "convert_text", "pdfmd_version"]

API_EXTENSIONS = {"pdf": "pdf", "docx": "docx", "odt": "odt", "pptx": "pptx", "epub": "epub", "html": "html",
                  "html5": "html", "latex": "tex", "tex": "tex", "typst": "typ", "markdown": "md", "md": "md",
                  "plain": "txt", "txt": "txt", "rtf": "rtf", "beamer": "pdf"}
API_TEXT_OUTPUTS = {"html", "html5", "latex", "tex", "typst", "markdown", "md", "plain", "txt", "rtf"}


class PdfmdError(RuntimeError):
    """A conversion that failed: `returncode`, and what pdfmd printed (`stdout`, `stderr`)."""

    def __init__(self, message: str, returncode: int = 1, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def pdfmd_version() -> str:
    return PDFMD_VERSION


def _api_command(source: Path, to: str | None, output: Path, extra_args, metadata, variables, stamp: bool,
                 backup: bool) -> list[str]:
    command = [sys.executable, str(Path(__file__).resolve()), str(source), "-o", str(output.resolve()), "--rewrite"]
    if to and to.lower() not in ("pdf", output.suffix.lstrip(".").lower()):
        command += ["--to", to]
    if not stamp:
        command.append("--no-stamp")
    if not backup:
        command.append("--no-backup")
    if metadata:
        command += ["-y", *map(str, metadata)]
    for key, value in (variables or {}).items():
        command += ["-V", f"{key}={value}"]
    return command + [str(item) for item in extra_args]


def _api_run(command: list[str], cwd: Path | None, timeout: float | None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise PdfmdError(f"pdfmd timed out after {timeout} s", 124) from error


def convert_file(source, to: str | None = None, outputfile=None, *, extra_args=(), metadata=(), variables=None,
                 stamp: bool = False, backup: bool = False, check: bool = True, cwd=None,
                 timeout: float | None = None) -> Path:
    """Convert `source` (Markdown, or any format Pandoc reads) and return the output's path.

    `to` is the target format (`pdf`, `docx`, `odt`, `html`, `latex`, `typst`...; default: from `outputfile`'s
    suffix, else PDF). `outputfile` defaults to the source's name with the format's extension. `metadata` lists
    metadata files, `variables` is a dict of Pandoc variables, `extra_args` anything else the command line takes
    (`["--engine", "typst", "--no-auto", "preamble"]`). Raises `PdfmdError` when the build fails (`check=False`
    returns the path anyway if the file exists)."""
    path = Path(source)
    if not path.exists():
        raise PdfmdError(f"{path} does not exist", 2)
    if outputfile is not None:
        output = Path(outputfile)
    else:
        extension = API_EXTENSIONS.get((to or "pdf").lower(), (to or "pdf").lower())
        output = path.with_suffix("." + extension)
    done = _api_run(_api_command(path, to, output, extra_args, metadata, variables, stamp, backup),
                    Path(cwd) if cwd else None, timeout)
    if check and (done.returncode != 0 or not output.is_file()):
        detail = (done.stderr.strip() or done.stdout.strip()).splitlines()
        raise PdfmdError(f"pdfmd failed ({done.returncode}): {detail[-1] if detail else 'no output'}",
                         done.returncode or 1, done.stdout, done.stderr)
    return output


def convert_text(source: str, to: str = "pdf", format: str = "md", *, extra_args=(), metadata=(), variables=None,
                 outputfile=None, check: bool = True, cwd=None, timeout: float | None = None):
    """Convert text held in memory. Returns the result as `str` for a text format (html, latex, typst, markdown,
    plain) and as `bytes` for the others (pdf, docx, odt, pptx, epub); with `outputfile` the file is kept and
    its path returned. `format` is the input's format by its usual extension (`md`, `rst`, `org`, `tex`...)."""
    with tempfile.TemporaryDirectory(prefix="pdfmd-api-") as directory:
        folder = Path(directory)
        suffix = "." + {"markdown": "md", "latex": "tex", "plain": "txt"}.get(format.lower(), format.lower().lstrip("."))
        path = folder / f"document{suffix}"
        path.write_text(source, encoding="utf-8")
        extension = API_EXTENSIONS.get(to.lower(), to.lower())
        target = Path(outputfile) if outputfile is not None else folder / f"document.{extension}"
        convert_file(path, to, target, extra_args=extra_args, metadata=metadata, variables=variables, check=check,
                     cwd=cwd or folder, timeout=timeout)
        if outputfile is not None:
            return target
        if not target.is_file():
            return "" if to.lower() in API_TEXT_OUTPUTS else b""
        return target.read_text(encoding="utf-8") if to.lower() in API_TEXT_OUTPUTS else target.read_bytes()


if __name__ == "__main__":
    main()
