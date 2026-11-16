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

PDFMD_VERSION = "3.33.268"
import argparse  # noqa: F401 -- preserve startup and the public module attribute
import atexit  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 18)
import contextlib  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 17)
import hashlib  # noqa: F401 -- retain start-up modules and the module attribute
import io  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 17)
import importlib.util
import json  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 17)
import platform
import urllib.parse  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 12)
import struct  # noqa: F401 -- retain start-up modules and the module attribute
import zipfile  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 17)
from collections import namedtuple  # noqa: F401 -- retain start-up modules and the module attribute
from pathlib import PurePosixPath  # noqa: F401 -- retain start-up modules and the module attribute
import functools  # noqa: F401 -- retain start-up modules and the module attribute
from functools import lru_cache
import logging  # noqa: F401 -- retain start-up modules and the module attribute
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
import warnings  # noqa: F401 -- retain start-up modules and the module attribute
import inspect  # noqa: F401 -- read as core.inspect by lib/pdfmd_bridge/odt.py and as pdfmd.inspect by tests
from contextlib import contextmanager  # noqa: F401 -- retain start-up modules and the module attribute
from datetime import datetime  # noqa: F401 -- retain start-up modules and the module attribute
from decimal import Decimal  # noqa: F401 -- retain start-up modules and the module attribute
from pathlib import Path
from shutil import which
import tempfile
from tempfile import NamedTemporaryFile, mkdtemp  # noqa: F401 -- retain module attributes
from textwrap import dedent  # noqa: F401 -- retain startup and module attribute
from typing import Callable, Iterator  # noqa: F401 -- retain the Callable module attribute


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
import pdfmd_install  # noqa: E402, F401 -- preserve startup and the public module attribute
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
names("pdfmd_stamp", "STAMP_MODES STAMP_SCOPES STAMP_STORES DEFAULT_STAMP_OPTIONS stamp_fields frontmatter_stamp "
                     "resolve_stamp_options stamp_summary stamp_line_pattern history_heading_pattern IGNORE_MARK_RE "
                     "is_pdfmd_notes build_notes_blocks pdfmd_build_notes update_build_notes apply_stamp stamp_build "
                     "stamp_after_success partial_parts_label pdf_metadata_snippet stamp_pdf_metadata_posthoc "
                     "pdf_metadata_header_file")
names("pdfmd_history.record", "history_module note_entry compile_entry history_file record_history DEFAULT_BACKUP_OPTIONS "
                              "DEFAULT_BACKUP_DIR backup_notice backup_target backup_sort_key resolve_backup_options "
                              "backup_before_edit")
names("pdfmd_attach.options", "ATTACH_FORMAT ATTACH_MANIFEST ATTACH_SOURCE BUNDLE_MAX_MB EXTRA_PREFIX RESTORED_SUFFIX "
                              "BUNDLE_SKIP_DIRS IMAGE_REF_RE resolve_attach resolve_bundle extra_key relative_posix "
                              "GRAPHIC_RE drop_calc_export add_calc_constants comments_note requirement_lines "
                              "MARKDOWN_TARGETS resolve_keep_source")
names("pdfmd_tables.settings", "width_filter_args csv_table_filter CSV_DIV_RE contains_csv_table CSV_DEFAULTS CSV_ENV "
                               "CSV_NOTE_ENV csv_note_mode csv_count CSV_ENABLED_ENV csv_is_off TABLE_KEEP_ENV "
                               "table_keep_count table_caption_args tabularray_available TABLAY_NOTED cellalign_args "
                               "tblr_header_args CSV_DELIMITER_NAMES CSV_DELIMITER_WORDS table_width_filter "
                               "tablewidth_note ORG_CAPTION_RE")
names("pdfmd_html", "KATEX_VERSION KATEX_PACKAGE katex_folder MATHJAX_VERSION MATHJAX_FONT_SHA256 MATHJAX_DEFAULT_FONT "
                    "MATHJAX_FONT_FOR mathjax_font_package mathjax_folder mathjax_font_for sfnt_x_height body_x_height "
                    "katex_scale weasyprint_math_args ascii_table_transform HTML_TARGETS DEFAULT_OUTPUT_ALIASES "
                    "HTML_MATH_METHODS HTML_MATH_OPTIONS pandoc_has_option html_math_args cascaded_option "
                    "default_output_format html_settings html_pandoc_args")
names("pdfmd_routing", "BATCHOCR_MIN OCR_PACKAGE_MANAGERS system_package_manager ocr_install_command")
names("pdfmd_tex.inputs", "EMBEDDED_RESOURCE_DIRS resource_path_option kit_search_folders TECTONIC_SEARCH_ENV "
                          "tectonic_search_folders tex_search_env hoist_code_header pandoc_header_includes "
                          "keep_header_includes headers_as_metadata tex_package_args has_shift_heading_option "
                          "has_standalone_option document_preambles announce_preambles prepared_latex_inputs "
                          "raw_latex_only document_header_file")
names("pdfmd_kitset", "installed_package_folder configured_kits kit_locations find_kit kit_cache KIT_METADATA ACTIVE_KITS "
                      "set_kit_cli KIT_HEADER_PREFIX kit_preamble_kits kit_writes_preamble header_argument_positions "
                      "kit_explicit_sources kit_embedded_preambles package_helper office_packages")
names("pdfmd_metadata", "AUTO_METADATA_DISABLED METADATA_APPEND_KEY metadata_plus_key metadata_append_keys "
                        "merge_metadata_layers metadata_append_args calc_filter_args global_metadata_file PRESET_OFF "
                        "PRESET_DEFAULT presets_report METADATA_PRECEDENCES metadata_precedence pandoc_metadata_order "
                        "find_metadata find_local_metadata chapter_value has_chapter_field report_sources")
names("pdfmd_calc", "CALC_DIV_RE CALC_SPAN_RE CALC_ENV CALC_DIGITS_ENV CALC_ROUND_ENV CALC_SUBS_ENV CALC_TYPESET_ENV "
                    "CALC_TYPESET_STYLE_ENVS CALC_NOINDENT_ENV CALC_SPACE_ENV CALC_ALIGN_ENV CALC_ALIGNS "
                    "CALC_CONSTANTS_ENV CALC_EXPORT_ENV CALC_ROUNDS calc_is_off calc_round_mode calc_subs_on "
                    "calc_typeset_mode calc_typeset_styles calc_noindent_mode calc_space calc_align calc_constants_file "
                    "calc_export_file write_calc_export calc_constants_statements calc_digits_value calc_digits_mode")
names("pdfmd_config.auto", "ACCESSORY_DIRNAME UNPACKED_SUFFIX NO_AUTO_KINDS NO_AUTO_ALIASES auto_disabled "
                           "accessory_directories discovery_disabled folder_auto_safe resolve_auto effective_no_auto "
                           "kit_no_auto_kinds")
names("pdfmd_assemble.embed", "_EmbedDumper")
names("pdfmd_assemble.embed", "strip_embedded_preamble ASSEMBLED_KEY ASSEMBLED_COMMENT_RE is_assembled_text "
                              "is_assembled_document EMBED_KINDS EMBED_ALL PREAMBLE_END_MARK LUA_MODES EMBED_BLOCK_RE "
                              "EmbedRequest parse_embed_option resolve_embed normalized_source is_crlf_text "
                              "strip_location_markers first_block_start outside_folder block_relative_path embedded_lines "
                              "with_location_markers embedded_lua_filters header_includes_text")
names("pdfmd_engines", "PDF_ENGINES ENGINE_ALIASES BROWSER_ENGINES LATEX_ENGINES PREAMBLE_FILENAMES "
                       "TEX_STANDALONE_FORMATS ENGINE_FAMILY ENGINE_GROUPS automatic_engines select_engines "
                       "resolve_engines dependency_report frontmatter_engine")
names("pdfmd_engines.native", "INSTALL_KINDS INSTALL_SIZES PANDOC_MIN warn_old_pandoc PANDOC_MISSING inkmd_vendored "
                              "md2pdf_available matplotlib_available inkmd_emoji_font is_native_engine native_available "
                              "available_native_engines native_request native_possible native_run_note "
                              "system_install_hint pandoc_install_hint offer_native_upgrade")
installed_engines = deferred("pdfmd_engines", "installed_engines")
mask_embedded_blocks = deferred("pdfmd_assemble.embed", "mask_embedded_blocks")
is_global_metadata = deferred("pdfmd_metadata", "is_global_metadata")
metadata_files_by_priority = deferred("pdfmd_metadata", "metadata_files_by_priority")
preset_name = deferred("pdfmd_metadata", "preset_name")
active_kits = deferred("pdfmd_kitset", "active_kits")
kit_metadata_files = deferred("pdfmd_kitset", "kit_metadata_files")
document_header_includes = deferred("pdfmd_tex.inputs", "document_header_includes")
find_preambles = deferred("pdfmd_tex.inputs", "find_preambles")
frontmatter_pdfmd_options = deferred("pdfmd_tex.inputs", "frontmatter_pdfmd_options")
has_header_include_option = deferred("pdfmd_tex.inputs", "has_header_include_option")
batchocr_version = deferred("pdfmd_routing", "batchocr_version")
tesseract_install_hint = deferred("pdfmd_routing", "tesseract_install_hint")
katex_runtime = deferred("pdfmd_html", "katex_runtime")
mathjax_fonts = deferred("pdfmd_html", "mathjax_fonts")
mathjax_runtime = deferred("pdfmd_html", "mathjax_runtime")
cell_tags_text = deferred("pdfmd_tables.settings", "cell_tags_text")
repair_ascii_text = deferred("pdfmd_tables.settings", "repair_ascii_text")
table_ascii_mode = deferred("pdfmd_tables.settings", "table_ascii_mode")
is_package_helper_yaml = deferred("pdfmd_stamp", "is_package_helper_yaml")
yaml_autoinclude = deferred("pdfmd_stamp", "yaml_autoinclude")
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


# --strip-comments / --keep-comments (None: the document's pdfmd-options decide).
STRIP_COMMENTS_CLI: bool | None = None


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
                ASSEMBLED_COMMENT_RE = sys.modules[__name__].ASSEMBLED_COMMENT_RE
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

CODE_CLI: dict = {}                       # --line-numbers and friends, filled in by main()


# CSV_CUTS: lib/pdfmd_tables/command.py (v3.33.24)

# csv_note_argument: lib/pdfmd_args (v3.33.40)


# csv_cut_advice: lib/pdfmd_native (v3.33.39)


# csv_count_argument: lib/pdfmd_args (v3.33.40)


# csv_defaults: lib/pdfmd_tables/command.py (v3.33.24)


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


LINEBREAK_CLI: dict = {"kinds": None, "off": False}


# An inline calculator (v3.30.6): inline code followed at once by a bare `{=}` is replaced by its value, `2026 - 2006`{=} -> 20,
# evaluated by pdfmd_lua/calc.lua's own small parser (nothing is run). `C = n / V = {ans:4sf}` inside the span prints the
# text with the value put in and keeps C; a `::: calc` div does that for its lines without the backticks. The filter goes in only
# for a document that has such a span or div. The settings live under `pdfmd-options: {calc: {enabled, digits, round, subs, noindent, space, align, constants, export}}` (the
# document, its metadata files, the config; `calc: off` alone is the short form of `enabled: false`), and on the command line
# --calc / --no-calc, --calc-digits 4sf, --calc-round away, --calc-subs, --calc-typeset, --calc-noindent, --calc-space, --calc-align, --calc-constants, --calc-export (reaching -j workers as PDFMD_CALC,
# PDFMD_CALC_DIGITS, PDFMD_CALC_ROUND, PDFMD_CALC_SUBS, PDFMD_CALC_TYPESET, PDFMD_CALC_NOINDENT, PDFMD_CALC_SPACE, PDFMD_CALC_ALIGN, PDFMD_CALC_CONSTANTS, PDFMD_CALC_EXPORT). digits: how many figures a value shows (4sf: four significant figures, 2dp: two decimal places); unset
# prints as R does. round: how round() settles an exact half, to even (R and Python, the default) or away from zero.
CALC_DUMP: Path | None = None               # where this build's calc.lua writes its names, when the document exports them (set around one build)
CALC_SEED: Path | None = None              # the names of the parts before a part built alone (build_calc_seed; set around one build)
CALC_BELOW: Path | None = None             # the first definitions in the parts after it (3.31.44; the same)


# calc_round_argument and calc_digits_argument: lib/pdfmd_args (v3.33.40)


# -- Appending to a metadata value (v3.31.40, entry 3du point 20) ---------------------------------------------------------
# A key written `author+:` adds to the value the layers below hold; `pdfmd-options: {metadata-append: [author]}` makes the
# document's own `author:` add to it as well. The layers, lowest first: the global metadata file, a kit's defaults, the
# folders' `.pdfmd/metadata.yaml` (farthest first), the document folder's metadata files, the document's own front matter.
# Pandoc cannot do it (the front matter beats every metadata file), so pdfmd merges, hands the finished values over under
# `pdfmd-merged` and pdfmd_lua/metadata_append.lua, run before every other filter, puts them in place.


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
    if engine in sys.modules[__name__].BROWSER_ENGINES:
        try:
            import pdfmd_direct as direct
        except ImportError:
            return None
        return direct.find_browser(engine, which)
    return resolve_soffice() if engine == "soffice" else which(engine)


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

# NATIVE_SOURCE_SUFFIXES and NATIVE_READERS: lib/pdfmd_native (v3.33.39)
# INSTALL_SPECS: lib/pdfmd_install/__init__.py (v3.33.35)
# NATIVE_META_KEYS (with its comment): lib/pdfmd_native (v3.33.39)
# PANDOC_FEATURES and pandoc_limits: lib/pdfmd_doctor/__init__.py (v3.33.31)


# What this run could not render natively, by kind -> count; read by
# offer_native_upgrade() once the build is done.
NATIVE_LOST: dict[str, int] = {}


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


# CSV_ALIGNMENTS, CSV_SEPARATOR_CELL_RE, csv_extension_delimiter and csv_guess_delimiter: lib/pdfmd_native (v3.33.39)


# csv_keep to describe_native_changes (the .csv div table, normalise_gfm, the paper, inkmd, md2pdf and Calibre's Markdown reader, convert_native): lib/pdfmd_native (v3.33.39)


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


# -- Kits: find one (entry 3du, C1) ------------------------------------------------------------------------------------
# A kit is a folder with a `.kit` file (pdfmd_kits has the format and the search). Search is not selection: nothing here
# runs for a document that selects no kit, and a document that only says `\usepackage{nulabreport}` is not switched to the
# kit. The places, in order: a kits/ folder beside the document or above it, the config's `kits:` (a folder that is a kit,
# or one that holds kits; a mapping {path:, aliases: {MODE: [names]}} adds mode names without editing the kit), a kits/ folder
# beside the config file, then the folder of `NAME.sty` that kpsewhich finds (the cached answer first: one stat). `--no-auto
# kit` takes the searching off (the config's `kits:` stays: the user named those), `--no-auto kpsewhich` the TeX tree only.


# kit_install_record and kits_report: lib/pdfmd_kits/locate.py (v3.33.22)


# -- Kits: choose them (entry 3du, C2) -------------------------------------------------------------------------------------
# `pdfmd-options: {kit: ...}` in the config (global), the global metadata or a preset (preset), a folder's `.pdfmd/` files
# (folder; by NAME only), a document's own metadata and front matter (document); `--kit` above them all. pdfmd_kits.selection
# has the grammar and the stacking. A selected kit supplies, in this order: its defaults as metadata files between the global
# metadata and the folders' own (so a folder tunes the kit and the document wins), the folder of its package for the helper
# lookup, its Lua filters, and its folder on Pandoc's resource path. The preamble it writes is C3.
KIT_CLI: list | None = None                     # --kit, parsed (None: not given; [OFF]: bare --kit / none)
KIT_STACK_CLI = None                            # --kit-stack, as given


# -- Kits: the preamble they write (entry 3du, C3) ----------------------------------------------------------------------
# The kit's lines are one header file, first of all (after the code-wrapping header); the user's own LaTeX follows. What the kit
# and the user's text say twice is settled in copies in the cache folder, never in the user's files: pdfmd_kits.preamble has the
# four outcomes. Ids: KIT-SAME and KIT-MERGE are shown with --verbose, KIT-YIELD is a WARN.


# kit_header_insert: lib/pdfmd_kits/locate.py (v3.33.22)


# kit_header_settle, kit_cache_tex and kit_header_resolve: lib/pdfmd_kits/locate.py (v3.33.22)


# folder_options_in_force: lib/pdfmd_attach (v3.33.37)


# kit_carried_files: lib/pdfmd_kits/locate.py (v3.33.22)


# office_package_folders: lib/pdfmd_office/build.py (v3.33.27)


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
# KATEX_SHA256, KATEX_KEPT, NODE_DIST and NODE_TARGETS: lib/pdfmd_install/__init__.py (v3.33.35)


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
# MATHJAX_REGISTRY, MATHJAX_SOURCE_SHA256, MATHJAX_FONT_SIZES, MATHJAX_BUNDLE_KEPT, MATHJAX_BUNDLE_FOLDERS, MATHJAX_BUNDLE_INPUT and
# mathjax_package_url: lib/pdfmd_install/__init__.py (v3.33.35)


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


# is_latex_preamble and top_level_tikzpicture: lib/pdfmd_tex (v3.33.36)


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


# wrap_latex_header_includes: lib/pdfmd_tex (v3.33.36)


# package_latex_keys (with the comment above it) and document_latex_definitions: lib/pdfmd_tex (v3.33.36)


# -- Discovered Lua filters: noticed, not blocked (v3.26.11) -----------------------------------------------------


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


# entry_line: lib/pdfmd_history/backups.py (v3.33.28)


# notes_to_entries and entries_to_notes: lib/pdfmd_history/backups.py (v3.33.28)


# HISTORY_SHOWN, backup_folders, document_versions, version_text, version_differs, restore_version, history_documents and linked_metadata: lib/pdfmd_history/backups.py (v3.33.28)


# history_view_command, history_act, history_interactive, init_backups_command and history_command: lib/pdfmd_history/backups.py (v3.33.28)


# --backup / pdfmd-options.backup: after a successful compile, copy the
# source into a sibling backup directory. Taken AFTER stamp_after_success on
# purpose, so the snapshot is exactly the file on disk; recompiling an
# unedited document then matches the newest snapshot (see backup_unchanged)
# and writes nothing. Off by default. Added v3.8.0 (2026-09-24); snapshot
# name formats and recognition of hand-made backups added v3.9.0.
#
# BACKUP_FORMATS: lib/pdfmd_history/backups.py (v3.33.28)


# _STRFTIME_PATTERNS and _COUNTER: lib/pdfmd_history/backups.py (v3.33.28)


# LEGACY_BACKUP_DIRS and backup_directory: lib/pdfmd_history/backups.py (v3.33.28)


# backup_template, fill_backup_template and backup_name_regex: lib/pdfmd_history/backups.py (v3.33.28)


# _plain_backup_patterns: lib/pdfmd_history/backups.py (v3.33.28)


# backup_snapshots: lib/pdfmd_history/backups.py (v3.33.28)


# BACKUP_IGNORED_LINE_RE, backup_unchanged, backup_after_success, backup_pdf_pattern, backup_pdf_after_success and backup_summary: lib/pdfmd_history/backups.py (v3.33.28)


# --- --extract-tables / --expand-tables (the work is in pdfmd_tables) -------------------------------------------

# tables_command: lib/pdfmd_tables/command.py (v3.33.24)


# -- Presets: other global metadata files to choose from (v3.28.19) ------------------------------------------------
# `presets/NAME.yaml` beside the config file is a global metadata file like `metadata.yaml` (which is the preset
# `default`): `--preset lab`, `pdfmd-options: {preset: lab}` (or lab.yaml; a path works too) takes it instead,
# `--preset none` / `--no-global-metadata` / `pdfmd-options: {global-metadata: false}` takes none. The command line
# wins, then the document's own pdfmd-options, its metadata files', then the config file's `options`.
PRESET_CLI: str | None = None                  # --preset (set in main)
GLOBAL_METADATA_CLI: bool | None = None        # --global-metadata / --no-global-metadata (set in main)


METADATA_PRECEDENCE_CLI: str | None = None    # --metadata-precedence (set in main)


# chapter_order: lib/pdfmd_parts/__init__.py (v3.33.30)


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


# scaffold_inputs: lib/pdfmd_parts/__init__.py (v3.33.30)


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
_PANDOC_HELP: str | None = None


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


# -- Stop-at stages (--stop-at markdown|tex|pdf) -----------------------------
# The build is a pipeline: the document's parts are joined into ONE Markdown
# text, Pandoc turns that into a standalone .tex, a LaTeX engine turns the
# .tex into a PDF. --stop-at ends it early, after the named stage. `tex` is
# simply `--to latex` (`beamer` with -p); `markdown` is pdfmd's own stage,
# handled here: the text Pandoc would be given, written out as one file.
# ASSEMBLED_FORMAT is the internal pseudo target-format that carries it
# through the same code paths as a real one (output naming, batch, report).
# STOP_STAGES: lib/pdfmd_args (v3.33.40)
# ASSEMBLED_COMMENT: lib/pdfmd_assemble (v3.33.38)


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
# FILE_ONLY_OPTION_KEYS (with its comment): lib/pdfmd_assemble (v3.33.38)


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


# EmbedPlan: lib/pdfmd_assemble (v3.33.38)


# render_embedded_block: lib/pdfmd_assemble (v3.33.38)


# -- The attached source holds its text files, editable (v3.28.39) ------------------------------------------
# After the text: the .tex files it reads (\input), then the CSV and other data, then what was always at the end (filters,
# history, bibliography, citation style), each as a `type: file` block with its path from the document's folder. A block
# can say `also:` (more paths with the same content: two symlinks to one chemicals.tex are one block). The text carries
# `<!-- pdfmd-at: ... -->` comments that say on which line of this very file each one is: one index after the front matter
# and one before each block that names a file (`file="x.csv"`, `\input{x}`). They are rewritten whenever the source is
# written and taken out wherever it is read (strip_location_markers), so a line number never outlives an edit.
# INLINE_SUFFIXES, INLINE_LIMIT and INLINE_ORDER: lib/pdfmd_attach (v3.33.37)


# render_embedded_file: lib/pdfmd_assemble (v3.33.38)


# block_places, drop_blocks and drop_duplicate_blocks: lib/pdfmd_attach (v3.33.37)


# inline_candidates and inline_blocks: lib/pdfmd_attach (v3.33.37)


# safe_relative_path, parse_embedded_blocks, and the trust store (its comment, trust_store_path, trusted_hashes and
# remember_trusted): lib/pdfmd_assemble (v3.33.38)


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


# literal_block: lib/pdfmd_assemble (v3.33.38)


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
# ATTACH_FORMAT_PLAIN: lib/pdfmd_attach (v3.33.37)
ATTACH_CLI: bool | None = None
# --bundle [all] / --no-bundle: None (the document decides), "off", "referenced", "all".
BUNDLE_CLI: str | None = None
# --verbose: --restore and --unpack list every file instead of counting them by folder (v3.28.15)
VERBOSE_OUTPUT = False
# --attach-bibliography used|all (None: the document's pdfmd-options decide).
BIB_ATTACH_CLI: str | None = None
CSL_ATTACH_CLI: bool | None = None    # --attach-csl / --no-attach-csl
# --bundle-packages / --no-bundle-packages (None: the document decides).
BUNDLE_PACKAGES_CLI: bool | None = None


def option_flag_number(value) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


# GLOBAL_LAYOUT_PATH (with its comment) and RAW_REFERENCE_RES: lib/pdfmd_attach (v3.33.37)
# BUNDLE_SKIP_SUFFIXES, PATH_TOKEN_RE, REFERENCE_EXTENSIONS and SCANNED_SUFFIXES, with their comments: lib/pdfmd_attach (v3.33.37)

# attached_bundle_mode: lib/pdfmd_attach (v3.33.37)


# layout_path and referenced_images: lib/pdfmd_attach (v3.33.37)


# The comment on the user's own TeX tree, PACKAGE_RE, CLASS_RE, TEX_INPUT_RE and PROVIDES_RE: lib/pdfmd_attach (v3.33.37)
# GRAPHIC_SUFFIXES, BUNDLE_IMAGE_SUFFIXES (with its comment), TEX_SOURCE_SUFFIXES and TEX_TREE_SCAN_LIMIT: lib/pdfmd_attach (v3.33.37)


# tex_distribution_roots, GRAPHIC_ARGUMENT_RE, MACRO_VALUE_RE and graphic_names_in to bundle_reach: lib/pdfmd_attach (v3.33.37)


# bundle_files, attachment_manifest and attached_source: lib/pdfmd_attach (v3.33.37)


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


# folder_counts: lib/pdfmd_restore/__init__.py (v3.33.29)


# csv_block_files, source_attachments and attach_source_after_success: lib/pdfmd_attach (v3.33.37)


# -- Markdown that carries its source (v3.26.4) -----------------------------------
# `--keep-source [packed|readable]`, `pdfmd-options: {keep-source: true|packed|readable}`: a Markdown output (--to gfm,
# gfm+raw, markdown, commonmark ...) ends with one HTML comment holding the same entries --attach-source puts into a PDF
# (see pdfmd_flat/keep.py for the encodings and why nothing in the source can close the comment). `pdfmd --restore
# FILE.md` writes them back into FILE.restored/. A whole build only (not a part or a section), like --attach-source.
KEEP_SOURCE_CLI: str | bool | None = None


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
# BATCHOCR_TEXT_MIN, PDF_READ_FORMATS, batchocr_spec and find_batchocr: lib/pdfmd_routing/__init__.py (v3.33.25)


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
