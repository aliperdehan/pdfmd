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
def write_text_lf(path: Path, text: str) -> None:
    """``path.write_text(text, encoding="utf-8", newline="\\n")``, which Python 3.9 lacks the `newline` of; all or nothing
    (atomic_write_text)."""
    atomic_write_text(path, text, newline="\n")


PDFMD_VERSION = "3.33.205"
import argparse
import atexit
import contextlib
import hashlib
import io
import importlib.util
import json
import platform
import urllib.parse
import struct
import zipfile
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
import time

if sys.version_info < (3, 9):
    raise SystemExit(f"pdfmd needs Python 3.9 or newer (this is {sys.version.split()[0]}). "
                     "Install it with `pipx install pdfmd-cli`, "
                     "which picks a suitable Python, or run pdfmd.py with a newer python3.")
import unicodedata
import warnings
import inspect
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from shutil import which
import tempfile
from tempfile import NamedTemporaryFile, mkdtemp, mkstemp
from textwrap import dedent
from typing import Callable, Iterator


# -- Writing a file in place: through a temporary file in the same folder and os.replace() -------------------------
# A file pdfmd rewrites (the document's BUILD NOTES, the config, the metadata, a restored source, a PDF it finishes) is written
# whole to `.NAME.<pid>.<random>.part` beside it and then renamed over it: a crash, a full disk or ^C half-way leaves the old
# file as it was (and the temporary file is removed). A symlink is written through, as write_text() does (the link stays); the
# mode of the file it replaces is kept; text is written as write_text() would (newline=None: the platform's, "\n" for
# write_text_lf). Not used for scratch files in a temporary folder, nor for a cache that is only ever replaced whole.
@contextmanager
def atomic_file(path: Path) -> Iterator[Path]:
    """The path of a temporary file beside ``path`` to write into; on leaving the block it is renamed over ``path``, or removed
    when the block raised (``path`` is then untouched)."""
    path = Path(path)
    target = Path(os.path.realpath(path)) if path.is_symlink() else path
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{os.urandom(4).hex()}.part")
    try:
        yield temporary
        try:
            shutil.copymode(target, temporary)
        except OSError:
            pass                                          # a new file: the umask's mode, as the open() gave it
        os.replace(temporary, target)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8", newline: str | None = None) -> None:
    """``Path.write_text(text, encoding=...)`` (``newline`` as open() takes it), all or nothing."""
    with atomic_file(path) as temporary:
        with open(temporary, "x", encoding=encoding, newline=newline) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """``Path.write_bytes(data)``, all or nothing."""
    with atomic_file(path) as temporary:
        with open(temporary, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())


def atomic_write_pdf(writer, path: Path) -> None:
    """A pypdf writer's document over ``path``, all or nothing."""
    with atomic_file(path) as temporary:
        with open(temporary, "xb") as handle:
            writer.write(handle)
            handle.flush()
            os.fsync(handle.fileno())


def own_python_folder() -> Path:
    """Where `pdfmd --install` puts Python packages when the Python it runs from is managed by the system (PEP 668:
    Homebrew, Debian), one folder per Python version, beside pdfmd's other tools (data_root())."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "pdfmd" / "python" / f"{sys.version_info[0]}.{sys.version_info[1]}"


# A checkout keeps the pdfmd_* packages in lib/ beside this file; an installed copy has them in site-packages and a zipapp at
# its root, where there is no lib/ to add. Resolved, so the symlink ~/dev/python-projects/pdfmd.py finds the real lib/.
try:
    _checkout_lib = Path(__file__).resolve().parent / "lib"
    if _checkout_lib.is_dir() and str(_checkout_lib) not in sys.path:
        sys.path.insert(0, str(_checkout_lib))
except (OSError, RuntimeError):
    pass

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


# pdfmd.py needs its packages from 3.33 on (the author, 2026-11-09): a copy without lib/ stops here and says why.
if importlib.util.find_spec("pdfmd_comments") is None:
    raise SystemExit("pdfmd: this pdfmd.py has no lib/ folder beside it, and the pdfmd_* packages it needs are not "
                     "installed; keep pdfmd.py together with its lib/ folder, or install pdfmd: pipx install pdfmd-cli")

import pdfmd_base  # noqa: E402
pdfmd_base.bind(sys.modules[__name__])      # every package's `core`, before any of them is imported; the first binding wins
names = pdfmd_base.names_into(DEFERRED_NAMES)   # the names table's lines: names("pdfmd_x.role", "a b c")
from pdfmd_comments import (CommentPolicy, comment_kind_set, parse_comment_policy,  # noqa: E402, F401 -- the strip_*_comments are read by lib/ and tests
                            strip_markdown_comments, strip_tex_comments, strip_xml_comments)
from pdfmd_templates import init_command  # noqa: E402
from pdfmd_watch import pinned_watch_argv, run_watch  # noqa: E402

from pdfmd_hybrid import attach_hybrid, hybrid_after_success, resolve_hybrid  # noqa: E402, F401 -- attach_hybrid is read by tests/test_embedding.py

from pdfmd_polish import (HF_FIELDS, fill_hf_field, hf_text, locate_headings, markdown_headings,  # noqa: E402, F401 -- read by tests
                          parse_hf_template, polish_pdf)
from pdfmd_pdfimages import (encode_png, extract_pdf_images, file_picture_size, match_images_to_pdf,  # noqa: E402, F401 -- encode_png, file_picture_size and samples_to_png are read by tests
                             rewrite_image_paths, rewrite_tex_image_paths, samples_to_png)
from pdfmd_compat import (batchmd_main, batchmd_translate, inkmd_main, inkmd_translate,  # noqa: E402, F401 -- the *_main are console entry points (pyproject.toml), the *_translate are read by tests
                          md2pdf_main, md2pdf_translate, mdpdf_main, mdpdf_translate, pan_tec_main, pan_tec_translate)
import pdfmd_view  # noqa: E402
from pdfmd_view import (pager_command, run_pager, stdin_build, terminal_view,  # noqa: E402, F401 -- run_pager, view_pager_setting and view_sources are read by tests
                        view_pager_setting, view_sources)

from pdfmd_lookup import (LOOKUP_FIELD_WORDS, LOOKUP_TIERS, LookupAmbiguous, cyrillic_candidates,  # noqa: E402, F401 -- lookup_fields, lookup_key, rank_lookup, document_priority, priority_enabled and source_markdown are read by tests or lib/
                          document_priority, find_wildcard_markdown, latin_candidates, lookup_fields, lookup_key,
                          priority_enabled, rank_lookup, source_markdown, strip_lookup_suffix)

import pdfmd_routing  # noqa: E402
from pdfmd_routing import (BATCHOCR_TAG, EBOOK_INPUT_EXTENSIONS, batchocr_spec, find_batchocr,  # noqa: E402, F401 -- BATCHOCR_TAG, EBOOK_INPUT_EXTENSIONS, batchocr_spec, install_ocr_tools and tessdata_environment are read by tests
                           install_ocr_tools, route_ebook_input, route_pdf_input, route_text_input, tessdata_environment)

import pdfmd_bridge  # noqa: E402, F401 -- tests read pdfmd.pdfmd_bridge
from pdfmd_bridge import (CALIBRE_TABLE_CSS, PANDOC_TABLE_STYLE_RE, browser_page_css, calibre_html_command,  # noqa: E402, F401 -- CALIBRE_TABLE_CSS and PANDOC_TABLE_STYLE_RE are read by tests, run_calibre_convert and run_soffice_convert are patched or read by tests and lib/
                          calibre_page_options, convert_office_direct, convert_via_soffice_bridge, prince_author_options,
                          run_browser_print, run_calibre, run_calibre_convert, run_soffice_convert, start_soffice_job)
from pdfmd_restore import (RESTORE_CHAIN, check_source_command, layout_from_source, restore_attachments,  # noqa: E402, F401 -- RESTORE_CHAIN, layout_from_source, restore_attachments, restore_attachments_in_place and restore_chain are read by tests
                           restore_attachments_in_place, restore_chain, restore_from_markdown, restore_from_pdf,
                           restore_target_name)
from pdfmd_parts import (ATX_HEADING_RE, Heading, NoPartMatches, ScaffoldPlan, SectionPlan, chapter_order,  # noqa: E402, F401 -- ATX_HEADING_RE, Heading, NoPartMatches, collect_parts, find_heading, heading_parts, outermost_headings, parts_directory, scan_headings, scan_items, select_parts, split_top_level_sections and wrap_runs are read by tests or lib/
                         collect_parts, find_heading, heading_parts, outermost_headings, parts_directory, plan_scaffold,
                         plan_sections, scaffold_inputs, scan_headings, scan_items, section_source, select_parts,
                         split_into_parts, split_top_level_sections, wrap_part, wrap_runs)
from pdfmd_doctor import (DEEP_SAMPLE, PANDOC_FEATURES, completion_options, completion_script, deep_checks,  # noqa: E402, F401 -- DEEP_SAMPLE, PANDOC_FEATURES, completion_options, deep_checks, foreign_commands, pandoc_limits and tool_note are read by tests
                          doctor_report, foreign_commands, pandoc_limits, tool_note)
import pdfmd_cache  # noqa: E402
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
from pdfmd_attach import (ATTACH_FORMAT_PLAIN, add_deflated_attachment, attach_source_after_success,  # noqa: E402, F401 -- all but attach_source_after_success, bundle_files, keep_source_after_success, read_pdf_attachments and referenced_images are read by tests or lib/
                          attached_bundle_mode, block_places, bundle_files, drop_blocks, drop_duplicate_blocks, find_in_tex_tree,
                          graphic_names_in, held_comments_note, inline_blocks, inline_candidates, keep_source_after_success,
                          layout_path, read_pdf_attachments, referenced_images, source_attachments, tex_distribution_roots,
                          write_pdf_attachments)
from pdfmd_assemble import (EmbedPlan, assemble_markdown_text, embedded_resources, filter_bibliography,  # noqa: E402, F401 -- filter_bibliography, remember_trusted, render_embedded_block, render_embedded_file, trust_store_path and used_citation_keys are read by tests or lib/
                            parse_embedded_blocks, remember_trusted, render_embedded_block, render_embedded_file,
                            trust_store_path, trusted_hashes, unpack_assembled, used_citation_keys, write_assembled_markdown)
import pdfmd_native  # noqa: E402
from pdfmd_native import (CALIBRE_MARKDOWN_EXTENSIONS, CSV_DIV_LINE_RE, PAGE_BREAK_COMMENT_RE, PAGE_BREAK_RE, PAPER_SIZES,  # noqa: E402, F401 -- all but MathText and convert_native are read by tests
                          MathText, author_names, convert_native, csv_div_table, csv_guess_delimiter, csv_keep,
                          ignored_front_matter_keys, inline_math, native_font_size, native_landscape, native_order, native_page,
                          native_paper, mapped_author, normalise_gfm, author_names_in_place)
from pdfmd_args import build_parser  # noqa: E402

# Moves into packages that are not loaded at start (SPLIT.md, step 6): stand-ins that load the module on the first call.
paragraph_spacing_latex_args = deferred("pdfmd_paragraph", "latex_args")
paragraph_spacing_typst_args = deferred("pdfmd_paragraph", "typst_args")
paragraph_spacing_command_line = deferred("pdfmd_paragraph", "apply_cli")
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

PREAMBLE = r"\setcounter{MaxMatrixCols}{20}"
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
# DEFAULT_FONT, MONOFONT_STAND_INS, SERIF_STAND_INS and installed_font_families to preferred_font: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)

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
    "priority",
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
        if folder is None and (is_folder_metadata(metadata) or is_global_metadata(metadata)):
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
EXPLICIT_KINDS = frozenset({"lua", "preamble", "tex", "metadata", "yaml", "files"})
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


CODE_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(?![`~])[ \t]*(.*)$")          # indented too: in a list item
INDENTED_CODE_RE = re.compile(r"^(?: {4}|\t)\S")
LIST_CONTEXT_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)]|#\.|[A-Za-z][.)])\s|^(?: {2,}|\t)")


def has_code_block(text: str) -> bool:
    """Whether Pandoc would see a code block in ``text``: a fenced block that is not a raw ``{=latex}`` one, or an
    indented one after a blank line that does not go on with a list item. The front matter is not looked at: its
    indented YAML (a `references:` list) is not code (v3.27.21; it gave five proposals with no code the code header)."""
    _, body = split_front_matter(text)
    fence = None                                     # the fence of the raw block we are in
    blank, context = True, ""                        # whether the last line was blank; the last line that was not
    for line in body.splitlines():
        if fence:
            if re.match(r"^[ \t]*%s{%d,}[ \t]*$" % (re.escape(fence[0]), len(fence)), line):
                fence = None
            continue
        match = CODE_FENCE_RE.match(line)
        if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):     # ```x``` is inline code
            if not match.group(2).strip().startswith("{="):
                return True
            fence = match.group(1)
            continue
        if INDENTED_CODE_RE.match(line) and blank and not LIST_CONTEXT_RE.match(context):
            return True
        blank = not line.strip()
        if not blank:
            context = line
    return False


def code_filter_args(no_auto: list[str] | None, sources: list[Path], metadata_files=()) -> list[str]:
    """What a LaTeX build needs for code blocks (pdfmd_lua/code.lua; wrapping and optional line numbers): the filter
    and, when the document has code and wrapping is not off, the header that loads fvextra. The settings of the
    command line and the global config reach the filter as metadata; a document's own `pdfmd-options` through the
    document. Nothing for `--no-auto codewrap`, a document without code, or a lone pdfmd.py."""
    if auto_disabled(no_auto, "codewrap"):
        return []
    try:
        import pdfmd_lua
        shipped, header = pdfmd_lua.path("code"), pdfmd_lua.FILTERS / "code_wrap.tex"
    except ImportError:
        pdfmd_lua_missing()
        return []
    if shipped is None or not any(has_code_block(read_text_best_effort(source)) for source in sources):
        return []
    settings = {}
    for key in ("code-wrap", "line-numbers", "line-number-step"):
        for where in (CODE_CLI, *(options for _, options in option_sources(sources[0], metadata_files))):
            if where.get(key) is not None:
                settings[key] = where[key]
                break
    args = ["--lua-filter", str(shipped)]
    for key, value in settings.items():
        args += ["-M", f"pdfmd-{key}={str(value).lower() if isinstance(value, bool) else value}"]
    if str(settings.get("code-wrap", True)).lower() != "false" and header.is_file():
        args += ["--include-in-header", str(header), "-M", "pdfmd-code-header=1"]
    return args


SVG_WARNED: set[str] = set()


def image_filter_args(no_auto: list[str] | None, sources: list[Path]) -> list[str]:
    """What a LaTeX build needs for images LaTeX cannot read (pdfmd_images; pdfmd_lua/images.lua): each SVG the
    documents name is converted once to a PDF (kept by content in the cache) and the filter puts the PDF where the
    document wrote the SVG, in a raw `\\includegraphics{a.svg}` or `\\includesvg{a}` and in a Markdown image when Pandoc
    has no rsvg-convert to do it itself. A raw `\\includegraphics` also gets graphicx, which Pandoc only loads for a
    Markdown image. Nothing for `--no-auto svg`, a document without such images, or a lone pdfmd.py."""
    if auto_disabled(no_auto, "svg"):
        return []
    try:
        import pdfmd_images
        import pdfmd_lua
        shipped, graphicx = pdfmd_lua.path("images"), pdfmd_lua.FILTERS / "graphicx.tex"
    except ImportError:
        return []
    if shipped is None:
        return []
    pandoc_converts = bool(which("rsvg-convert"))
    fetch_remote = not auto_disabled(no_auto, "remoteimages")
    offline = False
    mapping: dict[str, str] = {}
    raw_graphics = False

    def to_pdf(file: Path, source: Path, written: str) -> str | None:
        pdf, why = pdfmd_images.convert_svg(file, cache_root() / "images", which, resolve_soffice, run_soffice)
        if pdf is None and str(file) not in SVG_WARNED:
            SVG_WARNED.add(str(file))
            print(f"WARN  {display_path(source)}: {written} is an SVG and LaTeX cannot read it; {why}", file=sys.stderr)
        return str(pdf) if pdf is not None else None

    for source in sources:
        for reference in pdfmd_images.find_references(read_text_best_effort(source)):
            raw_graphics = raw_graphics or reference.kind != "markdown"
            if reference.path in mapping:
                continue
            if reference.remote:
                if not (fetch_remote and reference.kind == "markdown" and reference.path.lower().startswith(("http://", "https://"))) \
                        or offline:
                    continue
                local, why, down = pdfmd_images.fetch_remote(reference.path, cache_root() / "images" / "remote")
                if local is None:
                    if down:
                        offline = True
                        print(f"WARN  {display_path(source)}: no network, so remote images ({reference.path} and the "
                              "others) cannot be fetched; Pandoc will leave their descriptions instead", file=sys.stderr)
                    elif reference.path not in SVG_WARNED:
                        SVG_WARNED.add(reference.path)
                        print(f"WARN  {display_path(source)}: {reference.path} could not be fetched ({why})", file=sys.stderr)
                    continue
                if local.suffix == ".svg":
                    converted = to_pdf(local, source, reference.path)
                    if converted:
                        mapping[reference.path] = converted
                else:
                    mapping[reference.path] = str(local)
                continue
            if not reference.is_svg or (reference.kind == "markdown" and pandoc_converts):
                continue
            written = reference.path if reference.path.lower().endswith(".svg") else reference.path + ".svg"
            file = source.parent / urllib.parse.unquote(written)
            if not file.is_file():
                continue
            converted = to_pdf(file, source, reference.path)
            if converted:
                mapping[reference.path] = converted
    args: list[str] = []
    if mapping:
        mapping = {name: Path(path).as_posix() for name, path in mapping.items()}      # LaTeX reads a backslash as a command
        digest = hashlib.sha1(json.dumps(mapping, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        map_file = cache_root() / "images" / "maps" / f"{digest}.yaml"
        if not map_file.is_file():
            map_file.parent.mkdir(parents=True, exist_ok=True)
            map_file.write_text("pdfmd-image-map: " + json.dumps(mapping, ensure_ascii=False) + "\n", encoding="utf-8")
        args += ["--lua-filter", str(shipped), "--metadata-file", str(map_file)]
    if raw_graphics and graphicx.is_file():
        args += ["--include-in-header", str(graphicx)]
    return args


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


def read_text_best_effort(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


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
PDF_IMAGE_RE = re.compile(r"""!\[[^\]]*\]\([^)\s]*\.pdf(?:[?#][^)\s]*)?(?:\s+(?:"[^"]*"|'[^']*'))?\)|<img\b[^>]*\bsrc\s*=\s*["'][^"']*\.pdf[?#"']""",
                          re.IGNORECASE)


def resolve_raw(md_path: Path, metadata_files: list[Path], flat: bool = False) -> dict[str, list[str]] | None:
    """The raw-syntax table of this build (see pdfmd_raw), or None: `--no-raw`, else the command line, else the
    document's `pdfmd-options.raw`. A flat Markdown build (`--to gfm`) takes every syntax unless `raw: {md: ...}` says
    otherwise: the pieces are carried over, since the output has no HTML or LaTeX of its own to keep them in."""
    if RAW_CLI["off"]:
        return None
    try:
        import pdfmd_raw
        table = pdfmd_raw.parse(True if RAW_CLI["all"] else first_pdfmd_option(md_path, metadata_files, "raw"))
        for spec in RAW_CLI["for"]:
            family, _, listing = spec.partition("=")
            table = pdfmd_raw.merge(table, family, pdfmd_raw.syntaxes(listing))
        if flat:
            table = {**(table or {})}
            table.setdefault("md", list(pdfmd_raw.SYNTAXES))
    except ImportError:
        return None
    except ValueError as error:
        print(f"WARN  raw: {error}; the raw option was ignored", file=sys.stderr)
        return None
    return table


# Page breaks carried into every format (v3.27.15, off unless asked; 3.27.13 had it on): the spelling families
# pdfmd_lua/pagebreak.lua makes every output's own. `pdfmd-options.pagebreak` (document, metadata files, config:
# true / all, false, or a list of families), `--pagebreak [KIND ...]` (bare: all) and `--no-pagebreak` for a run.
PAGEBREAK_KINDS = ("comment", "tex", "html", "div", "typst", "word")
PAGEBREAK_CLI: dict = {"kinds": None, "off": False}


def pagebreak_value(value) -> list[str]:
    """The families a `pagebreak` value names, in PAGEBREAK_KINDS order: true or `all` every one, false none, a list
    (or a comma-separated string) those."""
    if value is None or value is False:
        return []
    if value is True:
        return list(PAGEBREAK_KINDS)
    items = value if isinstance(value, list) else str(value).replace(",", " ").split()
    words = [str(item).strip().casefold() for item in items if str(item).strip()]
    if any(word in ("all", "true", "yes", "on") for word in words):
        return list(PAGEBREAK_KINDS)
    unknown = [word for word in words if word not in PAGEBREAK_KINDS and word not in ("false", "no", "off", "none")]
    if unknown:
        print(f"WARN  pagebreak: {', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not a page-break family "
              f"({', '.join(PAGEBREAK_KINDS)}, or all)", file=sys.stderr)
    return [kind for kind in PAGEBREAK_KINDS if kind in words]


def pagebreak_kinds(md_path: Path, metadata_files: list[Path]) -> list[str]:
    """The page-break families this build carries into every format: the command line's, else pdfmd-options'."""
    if PAGEBREAK_CLI["off"]:
        return []
    if PAGEBREAK_CLI["kinds"] is not None:
        return pagebreak_value(PAGEBREAK_CLI["kinds"] or True)
    value = first_pdfmd_option(md_path, metadata_files, "pagebreak")
    return pagebreak_value(flavour_default(md_path, metadata_files, "pagebreak") if value is None else value)


# Universal markup (v3.29.13, off unless asked, a kind at a time): spellings Markdown dialects share but Pandoc does not know,
# carried into every writer by pdfmd_lua/markup.lua. `pdfmd-options.markup` (document, metadata files, config: true / all, false,
# or a list of kinds), `--markup [KIND ...]` (bare: all) and `--no-markup` for a run.
MARKUP_KINDS = ("callouts", "toc", "center", "highlight", "underline", "keep", "landscape", "appendix", "space")
MARKUP_CLI: dict = {"kinds": None, "off": False}


def markup_value(value) -> list[str]:
    """The kinds a `markup` value names, in MARKUP_KINDS order: true or `all` every one, false none, a list (or a
    comma-separated string) those."""
    if value is None or value is False:
        return []
    if value is True:
        return list(MARKUP_KINDS)
    items = value if isinstance(value, list) else str(value).replace(",", " ").split()
    words = [str(item).strip().casefold() for item in items if str(item).strip()]
    if any(word in ("all", "true", "yes", "on") for word in words):
        return list(MARKUP_KINDS)
    unknown = [word for word in words if word not in MARKUP_KINDS and word not in ("false", "no", "off", "none")]
    if unknown:
        print(f"WARN  markup: {', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not a kind of universal markup "
              f"({', '.join(MARKUP_KINDS)}, or all)", file=sys.stderr)
    return [kind for kind in MARKUP_KINDS if kind in words]


SHOW_COMMENTS_CLI: dict = {"on": None}


def show_comments_on(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether the <!-- comments --> of the text are shown in the output (v3.29.21): `--show-comments` / `--no-show-comments`,
    else `pdfmd-options.show-comments`. Off by default, and not one of the `markup: true` kinds."""
    if SHOW_COMMENTS_CLI["on"] is not None:
        return bool(SHOW_COMMENTS_CLI["on"])
    value = first_pdfmd_option(md_path, metadata_files, "show-comments")
    return value is True or str(value).strip().casefold() in ("true", "yes", "on", "1")


# The flavour of a Markdown file (v3.32.20, entry 3ee; one setting with `reader:` since v3.32.22): `pdfmd-options.flavour` (also spelt
# `flavor` or `reader`; document, metadata files, folders, config) or `--flavour`. A preset word (`pdfmd_flavours.PRESETS`: obsidian,
# pdfmd, pandoc, gfm, commonmark) names a row of reading choices; `auto` (the default) is `obsidian` inside an Obsidian vault, a
# folder with `.obsidian/` above the document, and `pdfmd` elsewhere. Any other value is a Pandoc reader spec (`markdown`,
# `gfm+smart`), which is `--from` for that document with the flavour left on `auto`.
try:
    from pdfmd_flavours import PRESETS as FLAVOUR_PRESETS, WORDS as FLAVOUR_WORDS
except ImportError:      # a copy of pdfmd.py without its packages: strict Pandoc and nothing else
    FLAVOUR_PRESETS, FLAVOUR_WORDS = {}, ("auto",)
FLAVOUR_CLI: dict = {"name": None}
_FLAVOUR_TOLD: set[str] = set()
UNCLOSED_WORDS = ("hide", "keep")
UNCLOSED_CLI: dict = {"mode": None}


def unclosed_comment_mode(md_path: Path, metadata_files=()) -> str:
    """What a `%%` with no closing `%%` does (v3.32.21): `hide` (Obsidian's way: the rest of the note is the comment) or `keep` (it
    stays text). `--unclosed-comment`, else `pdfmd-options.unclosed-comment`, else the flavour's own (`hide` for obsidian, `keep`
    for pdfmd: outside a vault a lone `%%` may be TeX). Another word is told once and the flavour's is used."""
    preset = FLAVOUR_PRESETS.get(flavour_of(md_path, metadata_files))
    default = preset.unclosed if preset else "keep"
    value = UNCLOSED_CLI["mode"]
    if value is None:
        value = first_pdfmd_option(md_path, list(metadata_files), "unclosed-comment")
    name = default if value is None else str(value).strip().casefold()
    if name in UNCLOSED_WORDS:
        return name
    if name and name not in _FLAVOUR_TOLD:
        _FLAVOUR_TOLD.add(name)
        print(f"NOTE  unclosed-comment: {name} is not one of {', '.join(UNCLOSED_WORDS)}; using {default}", file=sys.stderr)
    return default


def flavour_setting(md_path: Path, metadata_files=()) -> tuple[str, str | None]:
    """The flavour setting of a file, as (preset, reader spec): the command line, else `pdfmd-options.flavour` / `flavor` / `reader`.
    A preset word (any case) is the preset, with no spec; `auto` or nothing is obsidian inside a vault and pdfmd elsewhere; any
    other value is a Pandoc reader spec (`gfm+smart`): the flavour is auto's and the spec is the reader."""
    value = FLAVOUR_CLI["name"]
    if value is None:
        value = first_pdfmd_option(md_path, list(metadata_files), "flavour", "flavor", "reader")
    text = "" if value is None else str(value).strip()
    word = text.casefold()
    if word in FLAVOUR_PRESETS:
        return word, None
    auto = "obsidian" if vault_root(md_path) is not None else "pdfmd"
    return auto, (None if word in ("", "auto") else text)


def flavour_of(md_path: Path, metadata_files=()) -> str:
    """The flavour this file is read in: `obsidian`, `pdfmd`, `pandoc`, `gfm` or `commonmark` (see flavour_setting)."""
    return flavour_setting(md_path, metadata_files)[0]


def flavour_default(md_path: Path, metadata_files, column: str) -> str:
    """What the flavour switches on without a setting (v3.32.24): its `markup` or `pagebreak` column (see pdfmd_flavours), for a
    Markdown file only; empty for any other input and for `pandoc`, `gfm` and `commonmark`."""
    if md_path.suffix.lower() not in (".md", ".markdown"):
        return ""
    preset = FLAVOUR_PRESETS.get(flavour_of(md_path, metadata_files))
    return getattr(preset, column, "") if preset else ""


def obsidian_source(text: str, md_path: Path, metadata_files=(), show: bool | None = None) -> str:
    """``text`` as Pandoc should read it in the flavour's own syntax: %%comments%% hidden (obsidian, pdfmd), or (``show``, by default
    `show-comments`) turned into HTML comments the writers draw as Comment boxes; then each `![[picture|300]]` written as a Markdown
    image (see embed_source). Unchanged when the flavour has neither or the text has none of them. A `%%` that never closes is told
    once (see unclosed_comment_mode for what becomes of it)."""
    preset = FLAVOUR_PRESETS.get(flavour_of(md_path, metadata_files)) if ("%%" in text or "[[" in text) else None
    if preset is None:
        return text
    if preset.comments and "%%" in text:
        text = hidden_comments(text, md_path, metadata_files, show)
    if preset.embeds and "![[" in text:
        text = embed_source(text, md_path, metadata_files)
    if preset.wikilinks and "[[" in text:
        try:
            from pdfmd_obsidian import wikilinks_as_text
            text = wikilinks_as_text(text).text
        except ImportError:
            pass
    return text


def hidden_comments(text: str, md_path: Path, metadata_files=(), show: bool | None = None) -> str:
    """``text`` without its %%comments%% (v3.32.20), or with them as HTML comments when they are to be shown."""
    try:
        from pdfmd_obsidian import hide_comments
    except ImportError:
        print("WARN  the pdfmd_obsidian package is missing; %%comments%% are left as they are", file=sys.stderr)
        return text
    mode = unclosed_comment_mode(md_path, metadata_files)
    result = hide_comments(text, show_comments_on(md_path, list(metadata_files)) if show is None else show, mode)
    for line in result.unclosed:
        told = f"{md_path}:{line}"
        if told not in _FLAVOUR_TOLD:
            _FLAVOUR_TOLD.add(told)
            rest = len(text.splitlines()) - line + 1
            what = (f"the rest of the note ({rest} line{'s' if rest != 1 else ''}) is hidden, as Obsidian hides it; "
                    "pdfmd-options: unclosed-comment: keep leaves it as text" if mode == "hide"
                    else "it is kept as text; pdfmd-options: unclosed-comment: hide hides the rest, as Obsidian does")
            print(f"WARN  {display_path(md_path)}, line {line}: a `%%` with no closing `%%`: {what}", file=sys.stderr)
    return result.text


# `vault_app_setting`, `single_newline_mode`, `vault_root`, `embed_settings`, `find_embedded_image`, `embed_source` and
# `embed_filter_args` (with the embed and newline word lists and the two folder caches) live in `pdfmd_obsidian.vault`
# (v3.33.12); the stand-ins are in the binding block above.


def markup_kinds(md_path: Path, metadata_files: list[Path]) -> list[str]:
    """The kinds of universal markup this build carries: the command line's, else pdfmd-options' (less a chosen kit's
    `markup-off:`, pdfmd_kits.markup); with the comments (`comments`, which no list names) when they are to be shown."""
    kinds: list[str] = []
    if not MARKUP_CLI["off"]:
        if MARKUP_CLI["kinds"] is not None:
            kinds = markup_value(MARKUP_CLI["kinds"] or True)
        else:
            value = first_pdfmd_option(md_path, metadata_files, "markup")
            kinds = markup_value(flavour_default(md_path, metadata_files, "markup") if value is None else value)
            if kinds and active_kits(md_path, metadata_files, None):
                kinds = kit_markup_off(md_path, metadata_files, kinds)        # a kit's `markup-off:` (v3.33.68)
    if show_comments_on(md_path, metadata_files):
        kinds.append("comments")
    return kinds


def markup_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter markup.lua`` with the kinds that take part (`-M pdfmd-markup=callouts`), when any."""
    files = sources if isinstance(sources, list) else [sources]
    fit = embed_filter_args(sources, metadata_files) + figure_filter_args(sources, metadata_files)   # before markup.lua, so a markup filter stays the last argument
    kinds = markup_kinds(files[0], metadata_files) if files else []
    if not kinds:
        return fit
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return fit
    shipped = pdfmd_lua.path("markup")
    return fit + (["-M", "pdfmd-markup=" + ",".join(kinds), "--lua-filter", str(shipped)] if shipped is not None else [])


MARKUP_CALLOUT_HEADER = r"""% pdfmd: the box of a callout (pdfmd-options: markup: callouts)
\makeatletter
\@ifpackageloaded{xcolor}{}{\usepackage{xcolor}}
\makeatother
\definecolor{pdfmd-note}{HTML}{0969DA}
\definecolor{pdfmd-tip}{HTML}{1A7F37}
\definecolor{pdfmd-important}{HTML}{8250DF}
\definecolor{pdfmd-warning}{HTML}{9A6700}
\definecolor{pdfmd-caution}{HTML}{CF222E}
\definecolor{pdfmd-comment}{HTML}{6E7781}
\IfFileExists{tcolorbox.sty}{\def\pdfmdhastcolorbox{1}}{}
\ifdefined\pdfmdhastcolorbox
  \usepackage{tcolorbox}\tcbuselibrary{breakable}
  \newtcolorbox{pdfmdcallout}[1]{breakable, colback=#1!6!white, colframe=#1, boxrule=0pt, leftrule=2.5pt, arc=0pt,
    left=8pt, right=8pt, top=5pt, bottom=5pt}
\else
  \newenvironment{pdfmdcallout}[1]{\par\medskip\begin{quote}}{\end{quote}\medskip}
\fi
"""


MARKUP_HIGHLIGHT_HEADER = r"""% pdfmd: highlighted text (pdfmd-options: markup: highlight)
\makeatletter
\@ifpackageloaded{xcolor}{}{\usepackage{xcolor}}
\makeatother
\definecolor{pdfmd-mark}{HTML}{FFF3A3}
% under LuaTeX Pandoc's template loads lua-ul (with soul's \ul) for an underline; the same load here, with its own \highLight, keeps the two apart
% lua-ul's \highLight colours through luacolor, which Pandoc's template loads only for ~~struck~~ text: both are needed, else soul
\ifdefined\directlua
  \IfFileExists{lua-ul.sty}{\IfFileExists{luacolor.sty}{\def\pdfmdhasluaul{1}}{}}{}
\fi
\IfFileExists{soul.sty}{\def\pdfmdhassoul{1}}{}
\ifdefined\pdfmdhasluaul
  \usepackage{luacolor}
  \usepackage[soul]{lua-ul}
  \newcommand{\pdfmdhl}[1]{\highLight[pdfmd-mark]{#1}}
\else\ifdefined\pdfmdhassoul
  \usepackage{soul}
  \sethlcolor{pdfmd-mark}
  \newcommand{\pdfmdhl}[1]{\hl{#1}}
\else
  \newcommand{\pdfmdhl}[1]{#1}
\fi\fi
"""

MARKUP_LANDSCAPE_HEADER = r"""% pdfmd: landscape pages (pdfmd-options: markup: landscape)
\IfFileExists{pdflscape.sty}{\def\pdfmdhaslscape{1}}{}
\ifdefined\pdfmdhaslscape
  \usepackage{pdflscape}
\else
  \IfFileExists{lscape.sty}{\usepackage{lscape}}{\newenvironment{landscape}{}{}}
\fi
"""

# the LaTeX definitions each kind of markup needs (the kinds not here need none)
MARKUP_HEADERS = {"callouts": MARKUP_CALLOUT_HEADER, "comments": MARKUP_CALLOUT_HEADER, "highlight": MARKUP_HIGHLIGHT_HEADER,
                  "landscape": MARKUP_LANDSCAPE_HEADER}


def markup_header_args(sources: Path | list[Path], metadata_files: list[Path], before: list[str] | None = None) -> list[str]:
    """`--include-in-header` for a LaTeX build's universal markup: the pdfmdcallout environment, \\pdfmdhl ... in ONE header file
    of pdfmd's own (a filter's `header-includes` is dropped by every other header file of pdfmd's), or []. ``before`` is the
    Pandoc command so far: after a kit's or the user's own LaTeX the header keeps what that defined (v3.33.67,
    pdfmd_tex.markup)."""
    files = sources if isinstance(sources, list) else [sources]
    kinds = markup_kinds(files[0], metadata_files) if files else []
    pieces = markup_header_pieces(files[0], metadata_files, kinds, before) if kinds else []     # the box is one piece
    if not pieces:
        return []
    text = "\n".join(pieces)
    header = cache_root() / "tex" / f"packages-markup-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not header.is_file():
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(header)]


# Speaker notes in a Beamer deck (v3.32.2): `::: notes` blocks are dropped from the PDF unless Beamer is asked to show them.
# `pdfmd-options: {slide-notes: off | show | only}`: `show` puts each slide's notes on a page after it, `only` makes the PDF
# the notes pages alone. It is a header, not `-V classoption=notes=...`: that variable replaces the deck's own `classoption`
# (an `aspectratio=169` was lost, measured on 3.32.0).
SLIDE_NOTES_HEADERS = {"show": "\\setbeameroption{show notes}\n", "only": "\\setbeameroption{show only notes}\n"}


def slide_notes_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """The `slide-notes` option as off, show or only (a bad word stops the build, like `md-macro`)."""
    value = first_pdfmd_option(md_path, metadata_files, "slide-notes")
    if value is None or value is False:
        return "off"
    word = str(value).strip().casefold()
    if word in ("", "off", "no", "false", "0", "none"):
        return "off"
    if word in ("show", "only"):
        return word
    if value is True or word in ("on", "yes", "true", "1"):
        return "show"
    raise SystemExit(f"pdfmd-options slide-notes: {value!r} is not one of off, show, only")


def slide_notes_args(sources: Path | list[Path], metadata_files: list[Path], beamer: bool) -> list[str]:
    """`--include-in-header` that makes a Beamer deck show its speaker notes (`slide-notes`), or []: other builds ignore the setting."""
    files = sources if isinstance(sources, list) else [sources]
    if not beamer or not files:
        return []
    mode = slide_notes_mode(files[0], metadata_files)
    if mode == "off":
        return []
    text = "% pdfmd: speaker notes in the deck (pdfmd-options slide-notes)\n" + SLIDE_NOTES_HEADERS[mode]
    header = cache_root() / "tex" / f"slide-notes-{mode}.tex"
    try:
        if not header.is_file() or header.read_text(encoding="utf-8") != text:
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(header)]


def cover_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """`pdfmd-options: {cover: true | PICTURE}` (v3.29.9) as pdfmd_lua/cover.lua and its metadata, or []: `true` is the title
    block on a page of its own, a picture (relative to the document) is the first page, or the cover of an EPUB."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []
    value = first_pdfmd_option(files[0], metadata_files, "cover")
    if value is None or value is False or str(value).strip().casefold() in ("", "false", "no", "off", "0", "none"):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("cover")
    if shipped is None:
        return []
    args = ["--lua-filter", str(shipped)]
    if value is True or str(value).strip().casefold() in ("true", "yes", "on", "1", "title"):
        metadata = effective_metadata(files[0], metadata_files, [])
        klass = str(metadata.get("documentclass") or "article").strip()
        args = ["-M", "pdfmd-cover=title", "-M", "pdfmd-cover-latex=" + ("1" if klass in ("article", "report", "book", "scrartcl", "scrreprt", "scrbook") else "0"), *args]
        return args
    picture = (files[0].parent / str(value).strip()).resolve()
    if not picture.is_file():
        print(f"WARN  {display_path(files[0])}: cover: {value} was not found beside the document; no cover is made", file=sys.stderr)
        return []
    return ["-M", "pdfmd-cover=image", "-M", f"pdfmd-cover-image={picture}", *args]


def cover_header_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """`--include-in-header` for a LaTeX build's picture cover (`cover: picture.png`): the picture on the first page, before
    \\maketitle. A header file of pdfmd's own, last, like the packages: a filter's `header-includes` would be dropped by
    every other one of pdfmd's (the code header, the packages, a house preamble), which only a document's own survive."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []
    value = first_pdfmd_option(files[0], metadata_files, "cover")
    if value is None or value is True or str(value).strip().casefold() in (
            "", "false", "no", "off", "0", "none", "true", "yes", "on", "1", "title"):
        return []
    picture = (files[0].parent / str(value).strip()).resolve()
    if not picture.is_file():
        return []                      # cover_filter_args says so
    path_text = picture.as_posix()
    text = ("% pdfmd: the cover picture (pdfmd-options: cover)\n\\usepackage{graphicx}\n\\AtBeginDocument{\\thispagestyle{empty}"
            "\\noindent\\includegraphics[width=\\linewidth,height=\\textheight,keepaspectratio]{" + path_text + "}\\clearpage}\n")
    header = cache_root() / "tex" / f"packages-cover-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not header.is_file():
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(header)]


def pagebreak_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter pagebreak.lua`` with the families it takes part in (`-M pdfmd-pagebreak=comment,tex`), when any:
    each such spelling of a page break becomes the target format's own. Before raw.lua, which would otherwise draw or
    drop a raw TeX `\\newpage`."""
    files = sources if isinstance(sources, list) else [sources]
    kinds = pagebreak_kinds(files[0], metadata_files) if files else []
    if not kinds:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("pagebreak")
    return ["-M", "pdfmd-pagebreak=" + ",".join(kinds), "--lua-filter", str(shipped)] if shipped is not None else []


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


# One line break for every writer (v3.31.49, entry 3el; the idea of pagebreak.lua): each writer takes its own spelling of a line
# break and drops the others ("one<br>two" printed "onetwo" in LaTeX), and a table cell cannot hold a `\\par`.
# pdfmd_lua/linebreak.lua reads the spellings of a family and gives the target its own (one already in its language stays as
# written). Families: html (`<br>`, `<br/>`, `<br />`), tex (a raw `\newline`, `\linebreak`), typst (`#linebreak()`), word (a raw
# break run), context (`\crlf`). Like pagebreak, with a different default: `pdfmd-options.linebreak` (document, metadata files,
# config) is `auto` when not set (every family, inside table cells only), `true` / `all` (every family, everywhere), a list of
# families (those, everywhere) or `false`; `--linebreak [KIND ...]` (bare: all) and `--no-linebreak` for a run.
LINEBREAK_KINDS = ("html", "tex", "typst", "word", "context")
LINEBREAK_CLI: dict = {"kinds": None, "off": False}
LINEBREAK_RE = re.compile(r"<br\s*/?>|\\(?:newline|linebreak|crlf)|#linebreak\(\)|<w:br\s*/>", re.IGNORECASE)


def linebreak_value(value) -> tuple[str, list[str]]:
    """What a `linebreak` value asks for, as (where, families): where is `cells` or `all`, families in LINEBREAK_KINDS order.
    Not set or `auto`: every family in table cells; true or `all`: every family everywhere; false: none; a list (or a
    comma-separated string): those families, everywhere."""
    if value is None:
        return "cells", list(LINEBREAK_KINDS)
    if value is False:
        return "cells", []
    if value is True:
        return "all", list(LINEBREAK_KINDS)
    items = value if isinstance(value, list) else str(value).replace(",", " ").split()
    words = [str(item).strip().casefold() for item in items if str(item).strip()]
    if not words or words == ["auto"]:
        return "cells", list(LINEBREAK_KINDS)
    if any(word in ("all", "true", "yes", "on") for word in words):
        return "all", list(LINEBREAK_KINDS)
    unknown = [word for word in words if word not in LINEBREAK_KINDS and word not in ("auto", "false", "no", "off", "none")]
    if unknown:
        print(f"WARN  linebreak: {', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not a line-break family "
              f"({', '.join(LINEBREAK_KINDS)}, all, or auto)", file=sys.stderr)
    return "all", [kind for kind in LINEBREAK_KINDS if kind in words]


def linebreak_settings(md_path: Path, metadata_files: list[Path]) -> tuple[str, list[str]]:
    """(where, families) for this build: the command line's, else pdfmd-options' (see linebreak_value)."""
    if LINEBREAK_CLI["off"]:
        return "cells", []
    if LINEBREAK_CLI["kinds"] is not None:
        return linebreak_value(LINEBREAK_CLI["kinds"] or True)
    return linebreak_value(first_pdfmd_option(md_path, metadata_files, "linebreak"))


def linebreak_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter linebreak.lua`` (`-M pdfmd-linebreak=html,tex`, `-M pdfmd-linebreak-where=cells|all`) for a document that
    has a line-break spelling in it; nothing when no family takes part, and nothing for a document without a spelling (the
    filter would only look)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []
    where, kinds = linebreak_settings(files[0], metadata_files)
    if not kinds or not any(LINEBREAK_RE.search(EMBED_BLOCK_RE.sub("", read_text_best_effort(file))) for file in files):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("linebreak")
    return (["-M", "pdfmd-linebreak=" + ",".join(kinds), "-M", "pdfmd-linebreak-where=" + where, "--lua-filter", str(shipped)]
            if shipped is not None else [])


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


# Markdown inside raw LaTeX (v3.32.0, entry 3dc): `\md{...}` and `\begin{md}...\end{md}`. pdfmd_lua/md_macro.lua reads the argument as
# Markdown, so citations, cross-references and math stay in the one document; the filter goes in before every other one (before
# pandoc-crossref and --citeproc). pdfmd-options: md-macro: on (the default) | off. Only for a document that has a macro, and not
# one that defines `\md` itself.
MD_MACRO_RE = re.compile(r"\\md(?![A-Za-z])[ \t]*\{|\\begin\{md\}")
MD_MACRO_OWN_RE = re.compile(
    r"\\(?:re|provide)?newcommand\*?[ \t]*\{?[ \t]*\\md(?![A-Za-z])|\\(?:def|let|gdef|edef)[ \t]*\\md(?![A-Za-z])"
    r"|\\Declare(?:Robust)?Command\*?[ \t]*\{?[ \t]*\\md(?![A-Za-z])|\\(?:re)?newenvironment\*?[ \t]*\{md\}")
MD_MACRO_CODE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$|`[^`\n]*`", re.MULTILINE | re.DOTALL)


def md_macro_in(text: str) -> bool:
    """Whether the text uses `\\md{...}` or `\\begin{md}` outside code, and does not define `\\md` itself."""
    bare = MD_MACRO_CODE_RE.sub("", text)
    return bool(MD_MACRO_RE.search(bare)) and not MD_MACRO_OWN_RE.search(bare)


def md_macro_on(md_path: Path, metadata_files: list[Path]) -> bool:
    """The `md-macro` option: on unless the document, a metadata file or the config says off (anything else stops the build)."""
    value = first_pdfmd_option(md_path, metadata_files, "md-macro")
    if value is None:
        return True
    word = {True: "on", False: "off"}.get(value, str(value).strip().casefold())
    if word not in ("on", "off"):
        raise SystemExit(f"pdfmd-options md-macro: {value!r} is not one of on, off")
    return word == "on"


def md_macro_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter md_macro.lua`` for a document with an `\\md{...}` or `\\begin{md}`, unless `md-macro` is off or the document
    defines `\\md` itself (then its own definition stands)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or not md_macro_on(files[0], metadata_files):
        return []
    if not any(MD_MACRO_RE.search(MD_MACRO_CODE_RE.sub("", read_text_best_effort(file))) for file in files):
        return []
    if not any(md_macro_in(read_text_best_effort(file)) for file in files):
        print(f"NOTE  {files[0]}: \\md is defined by the document itself, so pdfmd does not read Markdown inside it "
              "(`md-macro: off` silences this)", file=sys.stderr)
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("md_macro")
    return ["--lua-filter", str(shipped)] if shipped is not None else []


# A fenced div that sets the paragraph indent for its stretch of text (v3.30.0): `::: {indent=false}`, `{indent=2em}`,
# `::: noindent`, `::: {.noindent}`, `::: indent`, and the class-word spellings of a value, `::: indent=3in`, `::: .indent=3in`,
# `::: indent-3in`, `::: {.indent-3in}`, `::: {.indent=3in}`. pdfmd_lua/indent.lua does it for the target format and puts the
# document's own indent back at the closing `:::`; the filter goes in only for a document that has such a div. The expression
# also lets a near miss through (`.indent3in`, `.noindent=2em`) so that the filter can say it is none of them; a class that only
# starts with the word (`.indented`, `.indentation`) does not.
_INDENT_WORD = r"(?:no)?indent(?:\b|(?=\d)|(?=(?:rem|em|ex|pt|cm|mm|in|bp|pc|px)\b))"
INDENT_DIV_RE = re.compile(r"""^[ \t]*:{3,}[ \t]*(?:\{(?:[^}"\n]|"(?:[^"\\\n]|\\.)*")*(?:\.""" + _INDENT_WORD + r"""|\bindent[ \t]*=)"""
                           r"""|\.?""" + _INDENT_WORD + r"""[^\s{}]*[ \t]*$)""", re.MULTILINE)


def contains_indent_div(md_path: Path) -> bool:
    text = EMBED_BLOCK_RE.sub("", read_text_best_effort(md_path))
    return bool(INDENT_DIV_RE.search(text))


def calc_div_wants_indent_filter(files: list[Path], metadata_files: list[Path]) -> bool:
    if not files or not any(CALC_DIV_RE.search(EMBED_BLOCK_RE.sub("", read_text_best_effort(file))) for file in files):
        return False
    return not calc_is_off(files[0], metadata_files) and calc_noindent_mode(files[0], metadata_files) != "off"


def indent_filter_args(sources: Path | list[Path], metadata_files: list[Path] = ()) -> list[str]:
    """``--lua-filter indent.lua`` when a source has an `indent=` / `.noindent` div (see INDENT_DIV_RE), or a `::: calc` div
    while calc gives its divs no indent (the default; calc.lua sets `indent=false` on them, this filter acts on it)."""
    files = sources if isinstance(sources, list) else [sources]
    if not any(contains_indent_div(file) for file in files) and not calc_div_wants_indent_filter(files, metadata_files):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("indent")
    return ["--lua-filter", str(shipped)] if shipped is not None else []


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


def metadata_append_args(sources: Path | list[Path], metadata_files: list[Path], pandoc_options=()) -> list[str]:
    """The metadata file with the finished values and ``--lua-filter metadata_append.lua``, only when some key appends; [] otherwise
    (every other build is untouched). Goes before every other filter."""
    files = sources if isinstance(sources, list) else [sources]
    if not files or yaml is None:
        return []
    append = metadata_append_keys(files[0], metadata_files)
    layers = metadata_layers(files, metadata_files)
    merged = load_package("pdfmd_args").merged_cli_metadata(sys.modules[__name__], layers, append, display_path(files[0]), pandoc_options)
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


def title_filter_args(sources: Path | list[Path], metadata_files: list[Path], pandoc_options: list[str] | None = None,
                      no_auto: list[str] | None = None) -> list[str]:
    """``--lua-filter title_meta.lua`` when the title or the authors have LaTeX in them (v3.28.6): Pandoc's own
    `title-meta`, the PDF's Title, leaves raw LaTeX out ("Reduction of -Cinnamaldehyde" for `\\emph{trans}`); and when an
    author is a mapping (`mapped_author`, v3.33.56), which Pandoc's `author-meta`, the PDF's Author, leaves out. Before the
    document's own filters, so that one which takes the title out and keeps `title-meta` finds it set. With
    `-M pdfmd-author-names=true` when the filter may also write such an author's name in its place in LaTeX's and HTML's
    title block (author_names_in_place, v3.33.69)."""
    files = sources if isinstance(sources, list) else [sources]
    if not files:
        return []

    def text(value) -> str:
        if isinstance(value, dict):
            return " ".join(text(item) for item in value.values())
        if isinstance(value, list):
            return " ".join(text(item) for item in value)
        return "" if value is None else str(value)

    metadata = effective_metadata(files[0], metadata_files, [])
    if not any("\\" in text(metadata.get(key)) for key in ("title", "author")) and not mapped_author(metadata.get("author")):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("title_meta")
    if shipped is None:
        return []
    in_place = author_names_in_place(files[0], metadata_files, metadata.get("author"), pandoc_options, no_auto)
    return [*(["-M", "pdfmd-author-names=true"] if in_place else []), "--lua-filter", str(shipped)]


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


def raw_filter_args(sources: Path | list[Path], no_auto: list[str] | None, metadata_files: list[Path],
                    flat_pictures: Path | None = None, preamble: list[Path] | None = None,
                    flat_text: bool = False) -> list[str]:
    """The filters of pdfmd_lua for non-Markdown pieces: raw.lua when `raw` asks for it (any writer), pdf_images.lua
    when a document names a PDF image (it acts for HTML writers only: a browser cannot show a PDF). Both read the
    picture cache folder and the table from one metadata file written here."""
    try:
        import pdfmd_lua
        raw_filter, pdf_filter = pdfmd_lua.path("raw"), pdfmd_lua.path("pdf_images")
    except ImportError:
        pdfmd_lua_missing()
        return []
    files = sources if isinstance(sources, list) else [sources]
    table = (resolve_raw(files[0], metadata_files, flat=flat_pictures is not None or flat_text)
             if raw_filter is not None and files else None)
    pdf_images = (pdf_filter is not None and not auto_disabled(no_auto, "pdfimages")
                  and any(PDF_IMAGE_RE.search(read_text_best_effort(file)) for file in files))
    diagram_filter = pdfmd_lua.path("diagram")
    diagrams = (diagram_filter is not None and not auto_disabled(no_auto, "diagrams")
                and any(DIAGRAM_BLOCK_RE.search(read_text_best_effort(file)) for file in files))
    smiles_filter = pdfmd_lua.path("smiles")
    smiles = (smiles_filter is not None and not auto_disabled(no_auto, "smiles")
              and any(SMILES_BLOCK_RE.search(read_text_best_effort(file)) for file in files))
    if table is None and not pdf_images and not diagrams and not smiles:
        return []
    folder = cache_root() / "raw"
    # Pandoc reads a string in a metadata file as Markdown, where a backslash escapes: a Windows path keeps forward slashes
    config: dict = {"pdfmd-raw-cache": (folder / "pictures").as_posix()}
    if flat_pictures is not None:       # flat Markdown: the pictures it needs sit beside the output, linked by a relative path
        config = {"pdfmd-raw-cache": flat_pictures.as_posix(), "pdfmd-raw-rel": flat_pictures.name,
                  "pdfmd-raw-work": (folder / "pictures").as_posix()}       # the SVGs go beside the output, the drawn PDFs stay in the cache
    if preamble:            # a LaTeX picture is drawn with the document's own preamble
        config["pdfmd-raw-preamble"] = [Path(item).as_posix() for item in preamble]
    if table is not None:
        config["pdfmd-raw"] = table
    if diagrams:
        config["pdfmd-diagram-tools"] = [tool for tool, _, _ in DIAGRAM_TOOLS if which(tool)]
        seconds = diagram_timeout_for(files[0], metadata_files)
        if seconds == 0:
            config["pdfmd-diagram-off"] = True
        elif seconds > 0:       # a negative number: no limit, so no runner either
            runner = Path(pdfmd_lua.FILTERS) / "limited_run.py"
            if sys.executable and runner.is_file():
                config["pdfmd-diagram-timeout"] = seconds
                config["pdfmd-diagram-python"] = Path(sys.executable).as_posix()
                config["pdfmd-diagram-runner"] = runner.as_posix()
            else:       # a copy of pdfmd without its runner, or a Python that cannot say where it is: the tools run as before
                print("NOTE  diagram-timeout is not applied: pdfmd_lua/limited_run.py or the Python interpreter was not found",
                      file=sys.stderr)
    if smiles:
        config.update(smiles_config(files[0], metadata_files))
    digest = hashlib.sha1(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    map_file = folder / "maps" / f"{digest}.yaml"
    if not map_file.is_file():
        map_file.parent.mkdir(parents=True, exist_ok=True)
        map_file.write_text(json.dumps(config, ensure_ascii=False) + "\n", encoding="utf-8")
    args = ["--metadata-file", str(map_file)]
    if table is not None:
        args += ["--lua-filter", str(raw_filter)]
    if pdf_images:
        args += ["--lua-filter", str(pdf_filter)]
    if diagrams:
        args += ["--lua-filter", str(diagram_filter)]
    if smiles:
        args += ["--lua-filter", str(smiles_filter)]
    return args


def document_filter_args(inputs: Path | list[Path], md_path: Path | list[Path], metadata_files: list[Path], no_auto: list[str] | None,
                         csv_filter: Path, pandoc_options: list[str], crossref_sources: Path | list[Path] | None = None,
                         flat_pictures: Path | None = None, preamble: list[Path] | None = None, flat_text: bool = False,
                         cellalign_early: bool = False, label: str | None = None) -> list[str]:
    """The filters pdfmd puts on what a document SAYS (its own syntax: the metadata that appends, `\\md{}`, calc, the CSV tables, page
    breaks, indent, callouts and the other markup, table captions, line breaks, the title, the cover, raw pieces and diagrams, the
    cross-references), in the order they run. Every build writes this one list, whatever the writer is, and so does the live view of
    `--serve` (entry 3do): a syntax added here shows in both, and the live view needs no list of its own.

    `inputs` are the files whose text is searched for the syntax (the document, or all the files of a joined build), `md_path` the
    document itself (a report's files, for report mode); `cellalign_early` puts the cell filter here (the office route), where the
    others put it after the writer's own. `label` names the document in a message (report mode: `REPORT`); `md_path` by default."""
    args = metadata_append_args(inputs, metadata_files, pandoc_options)
    args += md_macro_args(inputs, metadata_files)
    args += calc_filter_args(inputs, metadata_files)
    args += csv_table_filter_args(inputs, no_auto, csv_filter, metadata_files)
    args += pagebreak_filter_args(md_path, metadata_files)
    args += indent_filter_args(inputs, metadata_files)
    args += markup_filter_args(md_path, metadata_files)
    args += table_caption_args(inputs, metadata_files)
    args += linebreak_args(inputs, metadata_files)
    if cellalign_early:
        args += cellalign_args(md_path, metadata_files)
    args += title_filter_args(md_path, metadata_files, pandoc_options, no_auto)
    args += cover_filter_args(md_path, metadata_files)
    args += raw_filter_args(inputs, no_auto, metadata_files, flat_pictures=flat_pictures, preamble=preamble, flat_text=flat_text)
    args += crossref_filter_args(crossref_sources or inputs, pandoc_options, no_auto, label or str(md_path))
    return args


# A structure written as text (pdfmd_lua/smiles.lua finds it, pdfmd_smiles draws it): ```smiles, ```{.smiles caption="..."}, ::: smiles
SMILES_BLOCK_RE = re.compile(r"(?mi)^[ \t]*(?:`{3,}|~{3,}|:{3,})[ \t]*\{?[ \t]*\.?smiles\b")


def smiles_config(md_path: Path, metadata_files: list[Path]) -> dict:
    """The metadata smiles.lua reads: the resolved `pdfmd-options.smiles` (document, metadata files, config; the first place to set
    a field wins), the interpreter that has RDKit (pdfmd's own) and the folder of the drawing step."""
    try:
        import pdfmd_smiles
    except ImportError:
        return {}
    try:
        settings = pdfmd_smiles.resolve(cascaded_option(md_path, metadata_files, "smiles"))
    except pdfmd_smiles.SmilesError as error:
        raise SystemExit(f"{display_path(md_path)}: {error}")
    return {"pdfmd-smiles": {key: str(value) for key, value in settings.items()},
            "pdfmd-smiles-python": Path(sys.executable).as_posix(),
            "pdfmd-smiles-dir": Path(pdfmd_smiles.__file__).resolve().parent.as_posix()}


# A fenced block written in a diagram language (pdfmd_lua/diagram.lua draws it): ```mermaid, ```{.d2 caption="..."}, ```dot
DIAGRAM_BLOCK_RE = re.compile(r"(?mi)^[ \t]*(?:`{3,}|~{3,})[ \t]*\{?[ \t]*\.?(?:mermaid|d2|dot|graphviz)\b")
DIAGRAM_TIMEOUT = 120.0         # seconds one diagram tool run may take when nothing says otherwise: the `diagram-timeout` setting's default


def diagram_timeout_from(value) -> float:
    """The `diagram-timeout` setting as seconds: 0 = no diagram is drawn, a negative number = no limit, not set or not a
    number = DIAGRAM_TIMEOUT."""
    number = option_flag_number(value)
    return DIAGRAM_TIMEOUT if number is None else number


def diagram_timeout_for(md_path: Path, metadata_files: list[Path]) -> float:
    """The `diagram-timeout` of the document about to be built: its `pdfmd-options`, its metadata files', the config's."""
    value = (first_pdfmd_option(md_path, metadata_files, "diagram-timeout") if md_path.suffix.lower() in (".md", ".markdown")
             else config_options().get("diagram-timeout"))
    return diagram_timeout_from(value)


DIAGRAM_TOOLS = (("dot", "Graphviz", "brew install graphviz  |  apt install graphviz  |  pdfmd --install diagram:dot"),
                 ("d2", "D2", "brew install d2  |  pdfmd --install diagram:d2  |  https://d2lang.com/tour/install"),
                 ("mmdc", "Mermaid", "npm install -g @mermaid-js/mermaid-cli"))


RELATIVE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((?!https?:|data:|/|<)[^)\s]+\)")


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


def split_command(text: str) -> list[str]:
    """A command line typed by a person (`$PAGER`, `--editor`) as words. POSIX rules eat the backslashes of a Windows path
    (`C:\\Tools\\less.exe` -> `C:Toolsless.exe`), so on Windows the backslashes stay and only the quotes around a word go."""
    if os.name != "nt":
        return shlex.split(text)
    return [word[1:-1] if len(word) > 1 and word[0] == word[-1] and word[0] in "\"'" else word
            for word in shlex.split(text, posix=False)]


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
OFFICE_REFERENCE_EXTENSIONS = {"docx": ("docx", "dotx"), "odt": ("odt", "ott"), "pptx": ("pptx", "potx")}
OFFICE_OPTION_KEYS = ("reference-doc", "fonts", "latex", "style", "styles", "labels", "profile", "replace", "title-page", "media", "papersize", "geometry", "margin",
                      "fontsize", "mainfont", "sansfont", "monofont", "CJKmainfont", "linestretch", "lang", "indent")


def office_module():
    try:
        import pdfmd_office
    except ImportError:
        return None
    return pdfmd_office


def effective_metadata(md_path: Path, metadata_files: list[Path], variables: list[str]) -> dict:
    """The metadata Pandoc sees for a document, as plain data: -V variables over the document's front
    matter over its metadata files (the later file wins, as in Pandoc, in pandoc_metadata_order)."""
    merged: dict = {}
    for path in pandoc_metadata_order(metadata_files):
        merged.update(metadata_file_yaml(path))
    if md_path.suffix.lower() in (".md", ".markdown", ".txt", ""):
        try:
            front = front_matter_dict(md_path.read_text(encoding="utf-8-sig"))
            if "pagesize" in front and "papersize" not in front:
                front = {**front, "papersize": front["pagesize"]}         # the typo pdfmd reads as papersize (pagesize_typo_value)
            merged.update(front)
        except (OSError, UnicodeDecodeError):
            pass
    from_variables: dict = {}
    for variable in variables:
        match = re.match(r"^([^:=]+)[:=](.*)$", variable)
        key, value = (match.group(1), match.group(2)) if match else (variable, "true")
        from_variables.setdefault(key, []).append(value)
    for key, values in from_variables.items():
        if key == "papersize" and len(values) == 1 and paper_words(values[0])[1] and not paper_words(values[0])[0]:
            before = scalar_text(merged.get("papersize"))              # `--paper landscape`: the size stays what it was
            merged[key] = f"{before},{values[0]}" if before else values[0]
            continue
        merged[key] = values[0] if len(values) == 1 and key != "geometry" else values
    return merged


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


def pick_variant(pick: dict, chosen: list[str], md_path: Path, no_auto: list[str] | None) -> dict | None:
    """The variant of a package's `pick:` block that the document selects, as a mapping to merge into its
    office options. `pick: {default: black, default-by-option: {genchem: word}, from-preamble: REGEX, variants:
    {word: {...}, black: {...}}}`: the name starts as the default (of the last package option that has
    one), and the last match of the regex in the preamble (or the document's header-includes) takes over, the
    first capture group that matched being the name; a package whose own macros pick its colour scheme says
    where to read it, and the Word file follows."""
    name = pick.get("default")
    by_option = pick.get("default-by-option")
    if isinstance(by_option, dict):
        for option in chosen:
            if option in by_option:
                name = by_option[option]
    pattern = pick.get("from-preamble")
    if isinstance(pattern, str):
        texts = []
        for item in (find_preambles(md_path.parent, md_path.stem, []) if not discovery_disabled(no_auto, "preamble") else []):
            try:
                texts.append(item.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        try:
            texts.append(document_header_includes(md_path.read_text(encoding="utf-8-sig")) or "")
        except (OSError, UnicodeDecodeError):
            pass
        try:
            for match in re.finditer(pattern, "\n".join(texts)):
                found = next((group for group in match.groups() if group), None)
                if found:
                    name = found
        except re.error:
            pass
    variants = pick.get("variants")
    if isinstance(variants, dict) and isinstance(variants.get(name), dict):
        return variants[name]
    return None


def office_options(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None = None) -> dict:
    """`pdfmd-options: {office: ...}` as the document, its metadata files and the config file give it, over the
    defaults of a package that ships them (`<name>-office.yaml`, or the `office:` of `<name>-pdfmd.yaml`); the
    document wins key by key."""
    value = first_pdfmd_option(md_path, metadata_files, "office", with_config=False)
    options = dict(value) if isinstance(value, dict) else {}
    for folder, package, chosen in reversed(office_packages(md_path, metadata_files, no_auto)):
        for data, candidate in office_defaults_sources(folder, package, no_auto):
            # `by-option:` holds what an option of \usepackage[...] adds (orgchem: footer wording...)
            variants = data.pop("by-option", None)
            if isinstance(variants, dict):
                for option in chosen:
                    extra = variants.get(option)
                    if isinstance(extra, dict):
                        for extra_key, extra_value in extra.items():
                            data[extra_key] = ({**data.get(extra_key, {}), **extra_value}
                                               if isinstance(extra_value, dict) and isinstance(data.get(extra_key), dict)
                                               else extra_value)
            pick = data.pop("pick", None)
            if isinstance(pick, dict):
                extra = pick_variant(pick, chosen, md_path, no_auto)
                for extra_key, extra_value in (extra or {}).items():
                    data[extra_key] = ({**data.get(extra_key, {}), **extra_value}
                                       if isinstance(extra_value, dict) and isinstance(data.get(extra_key), dict)
                                       else extra_value)
            options = {**data, **options}
            # a package's relative reference-doc / profile paths are relative to its folder
            for key in ("reference-doc", "profile"):
                if isinstance(data.get(key), str) and key not in (value or {}):
                    options[key] = str((candidate.parent / data[key]).resolve())
            if isinstance(options.get("media"), dict) and "media" not in (value or {}):
                options["media"] = {name: str((candidate.parent / file).resolve())
                                    for name, file in options["media"].items()}
    # the config file (pdfmd --setup) is below a house style's own defaults (v3.27.9): a global reference-doc must not
    # replace the department template nulabreport ships; the document and its metadata files are above both
    configured = config_options(md_path).get("office")
    if isinstance(configured, dict):
        options = {**configured, **options}
    return options


# find_office_profile and find_reference_doc: lib/pdfmd_office/build.py (v3.33.27)


OFFICE_LABEL_COMMANDS = re.compile(r"\\(?:ref|cref|Cref|eqref|autoref|pageref|labelcref|label)\s*\{"
                                   r"|\\begin\{(?:equation|align|gather|multline|eqnarray|reaction|figure|table)")


def office_pdfmd_command(md_path: Path, metadata_files: list[Path], variables: list[str],
                         no_auto: list[str] | None, *options: str) -> list[str]:
    """This pdfmd run again, as a subprocess, for the same document with other options (a PDF build for its
    labels, a `--to latex` run for its preamble)."""
    # --no-stamp/--no-backup: only the build the user asked for writes a note into the source and a snapshot
    command = [sys.executable, str(Path(__file__).resolve()), str(md_path), *options, "--no-stamp", "--no-backup", "--rewrite",
               "--no-auto", *(no_auto or ["officeref"])]
    for variable in variables:
        command += ["-V", variable]
    if metadata_files:
        command += ["-y", *map(str, metadata_files)]
    return command


def office_label_data(md_path: Path, metadata_files: list[Path], variables: list[str],
                      no_auto: list[str] | None, note, scratch: Path, mode: str) -> Path | None:
    """The numbers LaTeX gave this document's labels (an .aux from a real PDF build, reused while it is
    newer than the sources), with the caption separator and reference names its preamble sets, written
    as JSON for the Lua filter. None when the document has nothing to refer to or the build fails."""
    module = office_module()
    if module is None or md_path.suffix.lower() not in (".md", ".markdown", ".txt", ""):
        return None
    try:
        text = md_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    # a split document refers to its labels from its parts: they are read, and watched for changes, with it
    parts: list[Path] = []
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            plan = plan_scaffold(md_path, [], no_auto, None)
        parts = [part for part in plan.parts if part != md_path] if plan is not None else []
        for part in parts:
            text += "\n" + part.read_text(encoding="utf-8-sig")
    except (SystemExit, OSError, UnicodeDecodeError):
        parts = []
    preambles = find_preambles(md_path.parent, md_path.stem, []) if not discovery_disabled(no_auto, "preamble") else []
    texts = []
    for item in preambles:
        try:
            texts.append(item.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    names = [package.strip() for name in dict.fromkeys(re.findall(r"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{([^}]+)\}",
                                                                 "\n".join(texts))) for package in name.split(",")]
    for path in kpsewhich_locate([package + ".sty" for package in names if package]).values():
        if "texmf-dist" not in str(path) and "/texlive/" not in str(path):
            try:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    data = {"captionsep": module.caption_separator(texts),
            "crefcap": bool(re.search(r"cleveref[^\n]*|\\usepackage\[[^\]]*\]\{cleveref\}", "\n".join(texts)) and
                            re.search(r"\[[^\]]*capitali[sz]e[^\]]*\]\{cleveref\}", "\n".join(texts)) is not None),
            "crefnames": {key: list(value) for key, value in module.cref_names(texts).items()}, "labels": {}}
    wanted = OFFICE_LABEL_COMMANDS.search(text) is not None and mode != "off"
    if wanted:
        base = cache_directory(md_path, document_cache_root(md_path, metadata_files))
        aux = base / f"{safe_stem(md_path.stem)}.aux"
        sources = [md_path, *parts, *metadata_files, *preambles]
        newest = max((item.stat().st_mtime for item in sources if item.is_file()), default=0)
        if not (aux.is_file() and aux.stat().st_mtime >= newest):
            load_package("pdfmd_office.build").build_reference_numbers(
                md_path, metadata_files, variables, no_auto, note, scratch)
        if aux.is_file():
            data["labels"] = module.parse_aux(aux.read_text(encoding="utf-8", errors="replace"))
            (scratch / "labels.aux").write_text(
                module.labels_only(aux.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    path = scratch / "labels.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# OfficeArguments, office_properties and office_finish: lib/pdfmd_office/build.py (v3.33.27)


@contextmanager
def office_reference(md_path: Path, metadata_files: list[Path], variables: list[str], target: str, output: Path,
                     pandoc_options: list[str], no_auto: list[str] | None, note,
                     labels: str | None = None, force_filter: bool = False) -> Iterator[list[str]]:
    """Pandoc arguments for a docx/odt/pptx build: `--reference-doc FILE` (the user's own reference
    document, or Pandoc's default, with the document's page setup, fonts and pdfmd's look written in)
    and, with `office: {latex: auto}`, the filter that makes LaTeX native (OfficeArguments)."""
    with tempfile.TemporaryDirectory(prefix="pdfmd-office-filter-") as scratch, \
            office_reference_document(md_path, metadata_files, variables, target, output, pandoc_options,
                                      no_auto, note) as reference_arguments:
        arguments = OfficeArguments(reference_arguments)
        arguments.scratch = Path(scratch)
        arguments.context = {"md_path": md_path, "metadata_files": metadata_files, "variables": variables,
                             "no_auto": no_auto, "target": target, "note": note, "output": output}
        module = office_module()
        options = office_options(md_path, metadata_files, no_auto)
        latex = str(options.get("latex", "auto" if target in ("docx", "odt") else "")).casefold()
        ebook = target == "epub" and EBOOK_MATH.get("mode") == "images"      # v3.29.1: an ebook's math drawn as pictures
        if ebook:
            latex, labels = "images", "off"
        if not latex and target in ("typst", "html") and raw_takes(md_path, metadata_files, target, "tex"):
            latex = "auto"                  # the raw option has this output take LaTeX: the route that draws what it can
        # Word and ODF always; Typst and HTML files only when the document asks (`office: {latex: auto}`); a Typst,
        # WeasyPrint or Calibre PDF when office_fallback_wanted says so (force_filter)
        wanted = target in ("docx", "odt") or force_filter or latex in ("auto", "images")
        if (module is not None and (target in ("docx", "odt", "typst", "html") or ebook) and wanted
                and latex not in ("off", "false", "no")
                and not auto_disabled(no_auto, "officelatex")):
            arguments.report = Path(scratch) / "report.json"
            labels = office_label_data(md_path, metadata_files, variables, no_auto, note, Path(scratch),
                                       labels or str(options.get("labels", "auto")).casefold())
            profile = None if auto_disabled(no_auto, "officeprofile") else find_office_profile(
                md_path, metadata_files, options, office_package_folders(md_path, metadata_files, no_auto))
            if profile is not None:
                note("OFFICE", f"{md_path}: profile {display_path(profile)}")
            arguments.filter_arguments = ["-M", f"pdfmd-office-latex={'images' if latex == 'images' else 'auto'}",
                                          "-M", f"pdfmd-office-report={arguments.report}"]
            if target == "typst" and typst_version() >= (0, 12):
                # a title a house style's cover took out goes back into the PDF's properties by a `set document` in
                # the body, which Typst takes there from 0.12 on (before, only at the very start: the build would stop)
                arguments.filter_arguments += ["-M", "pdfmd-office-typst-document=true"]
            if labels is not None:
                arguments.filter_arguments += ["-M", f"pdfmd-office-labels={labels}"]
            # where a file the document pulls in (\input, a package's chemicals.tex) may be: its own folder, the
            # metadata and preamble folders, as the PDF build finds them
            places = [md_path.parent, *accessory_directories(md_path.parent, md_path.stem),
                      *(item.parent for item in metadata_files),
                      *(item.parent for item in (find_preambles(md_path.parent, md_path.stem, [])
                                                  if not discovery_disabled(no_auto, "preamble") else []))]
            arguments.filter_arguments += ["-M", "pdfmd-office-path=" + os.pathsep.join(
                dict.fromkeys(str(Path(item).resolve()) for item in places))]
            if profile is not None:
                arguments.filter_arguments += ["-M", f"pdfmd-office-profile={profile}"]
            # the document's preamble: a profile reads its options, the converter of \ce and siunitx its \sisetup
            # and the house packages it loads (v3.28.9: before, it was passed only with a profile)
            parts = []
            for item in (find_preambles(md_path.parent, md_path.stem, [])
                         if not discovery_disabled(no_auto, "preamble") else []):
                try:
                    parts.append(item.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
            if parts:
                preamble_copy = Path(scratch) / "preamble.txt"
                preamble_copy.write_text("\n".join(parts), encoding="utf-8")
                arguments.filter_arguments += ["-M", f"pdfmd-office-preamble={preamble_copy}"]
            # pdfmd_chem runs in this Python (the one with pdfmd's packages), not whatever python3 is first on PATH
            arguments.filter_arguments += ["-M", f"pdfmd-office-python={sys.executable}"]
            # its answers, kept between the two runs of the filter (the collect run's for the render run)
            arguments.filter_arguments += ["-M", f"pdfmd-office-chem-cache={Path(scratch) / 'chem.json'}"]
            # last: other filters (a house style's own) have shaped the document by then
            arguments.filter_arguments += ["--lua-filter", str(Path(module.__file__).parent / "office.lua")]
            if ebook:
                arguments.filter_arguments += ebook_filter_args()
        yield arguments


@contextmanager
def office_reference_document(md_path: Path, metadata_files: list[Path], variables: list[str], target: str,
                              output: Path, pandoc_options: list[str], no_auto: list[str] | None,
                              note) -> Iterator[list[str]]:
    if (target not in OFFICE_REFERENCE_EXTENSIONS
            or any(item == "--reference-doc" or item.startswith("--reference-doc=") for item in pandoc_options)):
        yield []
        return
    module = office_module()
    options = office_options(md_path, metadata_files, no_auto)
    found = (None, "") if auto_disabled(no_auto, "officeref") else find_reference_doc(
        md_path, metadata_files, target, output, options, office_package_folders(md_path, metadata_files, no_auto))
    reference, origin = found
    if module is None or target == "pptx":
        yield ["--reference-doc", str(reference)] if reference else []
        if reference:
            note("OFFICE", f"{md_path}: reference document {origin}")
        return
    styled = not auto_disabled(no_auto, "officestyle") and str(options.get("style", "")).casefold() != "none"
    policy = "exact" if str(options.get("fonts", "")).casefold() == "exact" else "safe"
    explicit = {key: value for key, value in options.items() if key in OFFICE_OPTION_KEYS}
    if reference is not None:
        # a template decides its own page and fonts; only what `office:` names changes it
        spec = module.spec_from_metadata({}, explicit, policy)
        house = False
    elif styled:
        spec = module.spec_from_metadata(effective_metadata(md_path, metadata_files, variables), explicit, policy)
        house = str(options.get("style", "house")).casefold() != "plain"
    else:
        yield []
        return
    if reference is None and house:
        # pdfmd's PDF defaults are STIX Two Text and JetBrains Mono: what Word has closest to them
        spec.main = spec.main or "Times New Roman"
        spec.mono = spec.mono or "Consolas"
    if reference is not None and spec.empty() and target != "docx":
        note("OFFICE", f"{md_path}: reference document {origin}")
        yield ["--reference-doc", str(reference)]
        return
    media = options.get("media")
    if isinstance(media, dict):
        for zip_path, file in media.items():
            try:
                spec.media[str(zip_path)] = Path(str(file)).read_bytes()
            except OSError as error:
                print(f"WARN  {md_path}: office.media {file}: {error}", file=sys.stderr)
    try:
        base = reference.read_bytes() if reference else module.default_reference(target)
        data = module.patch_reference(target, base, spec, house)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"WARN  {md_path}: could not prepare the {target} reference document ({error}); "
              "Pandoc's default is used", file=sys.stderr)
        yield []
        return
    for text in spec.notes:
        note("OFFICE", f"{md_path}: font {text}")
    shown = []
    if spec.paper or spec.landscape:
        width, height = spec.page_size()
        shown.append(f"page {width / 1440:.2f} x {height / 1440:.2f} in")
    if spec.margins:
        shown.append("margins " + "/".join(f"{spec.margins.get(side, 0) / 1440:.2f}" for side in
                                           ("top", "right", "bottom", "left")) + " in")
    if spec.main or spec.size:
        shown.append(", ".join(filter(None, [spec.main, f"{spec.size:g} pt" if spec.size else None])))
    note("OFFICE", f"{md_path}: {target} " + ("from " + origin + "; " if reference else "from Pandoc's default; ")
         + ("; ".join(shown) if shown else "pdfmd's styles"))
    with tempfile.TemporaryDirectory(prefix="pdfmd-office-") as folder:
        path = Path(folder) / f"reference.{target}"
        path.write_bytes(data)
        yield ["--reference-doc", str(path)]


def raw_takes(md_path: Path, metadata_files: list[Path], family: str, syntax: str) -> bool:
    """Whether the `raw` option has output family `family` take the raw `syntax` (see pdfmd_raw)."""
    table = resolve_raw(md_path, metadata_files)
    return bool(table and syntax in table.get(family, []))


# LaTeX a Typst or HTML writer drops: a raw ```{=latex} block, a command in the text (Pandoc reads `\ce{H2O}` as raw
# LaTeX), and chemistry or units in math (texmath knows no \ce or \SI: Pandoc prints the TeX). Front matter and code
# are not looked at.
RAW_TEX_FENCE_RE = re.compile(r"(?m)^[ \t]*(?:`{3,}|~{3,})[ \t]*\{=(?:latex|tex)\}")
TEXT_COMMAND_RE = re.compile(r"\\[A-Za-z@]+")
MATH_SPAN_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.DOTALL)
# mhchem's and siunitx's commands pdfmd_chem converts (v3.28.10: one list; pdfmd_lua/chem_client.lua's NAMES and
# pdfmd_chem/batch.py's are the same, tests/test_chem.py)
CHEM_COMMANDS = ("ce", "cee", "cf", "pu", "num", "numlist", "numrange", "numproduct", "si", "unit", "SI", "qty",
                 "SIlist", "qtylist", "SIrange", "qtyrange", "ang")
MATH_ONLY_LATEX_RE = re.compile(r"\\(?:" + "|".join(CHEM_COMMANDS) + r")(?![A-Za-z])")


def latex_failed(failed_families: set) -> bool:
    """Whether a LaTeX engine failed earlier in this chain. The loop records an engine by its TeX family (luatex, xetex,
    pdftex: ENGINE_FAMILY); the check looked for engine names, so it never held and a Typst or WeasyPrint run after
    LaTeX failed did not get the LaTeX filter (v3.24.x to v3.28.1)."""
    latex_families = {ENGINE_FAMILY.get(engine, engine) for engine in LATEX_ENGINES}
    return any(name in latex_families or name in LATEX_ENGINES for name in failed_families)


def latex_dropped(paths: list[Path]) -> bool:
    """Whether the documents say something in LaTeX that a Typst or HTML writer would drop (see TEXT_COMMAND_RE)."""
    for path in paths:
        _, body = split_front_matter(read_text_best_effort(path))
        if RAW_TEX_FENCE_RE.search(body):
            return True
        body = strip_code_text(body)
        if any(MATH_ONLY_LATEX_RE.search(math) for math in MATH_SPAN_RE.findall(body)):
            return True
        if TEXT_COMMAND_RE.search(MATH_SPAN_RE.sub("", body)):
            return True
    return False


def office_fallback_wanted(md_path: Path, metadata_files: list[Path], failed_families: set,
                           family: str = "", sources: list[Path] | tuple = ()) -> bool:
    """Whether a Typst/WeasyPrint run should go through the LaTeX filter: a LaTeX engine has failed already, or the
    document says `office: {latex: auto}` for it, or its `raw` option has this family (`typst`, `html`) take LaTeX.
    With no `raw` setting for the family, whenever the document (`sources`, its parts too) has LaTeX the writer would
    drop (v3.28.2: a named `-e typst` or `-e weasyprint` printed "Water is and" for "Water is \\ce{H2O} and", and
    left out every tikzpicture, without a word)."""
    if latex_failed(failed_families):
        return True
    if str(office_options(md_path, metadata_files).get("latex", "")).casefold() in ("auto", "images"):
        return True
    if not family:
        return False
    table = resolve_raw(md_path, metadata_files)
    if table and family in table:
        return "tex" in table[family]
    return latex_dropped(list(sources) or [md_path])


# run_office_pandoc, build_office_pandoc, describe_fragment, print_office_check and check_docx_command: lib/pdfmd_office/build.py (v3.33.27)


PICTURE_ONLY = ("png", "jpg", "tiff", "eps", "ps", "svg")   # the targets only this command writes
PICTURE_FORMATS = ("pdf", *PICTURE_ONLY)


# `picture_target`, `picture_build`, `picture_sources`, `picture_page_folder`, `picture_targets`, `picture_one`,
# `multi_target_command` and `picture_command` (with `PICTURE_OPTIONS` and `TARGET_ONLY_OPTIONS`) live in
# `pdfmd_crop.targets` (v3.33.11); the stand-ins are in the binding block above.


# (the --check discovery and command moved to lib/pdfmd_check/command.py, v3.33.17; `check_command` is a stand-in in the binding block)


# office_render_fragments, office_convert_asset and init_reference: lib/pdfmd_office/build.py (v3.33.27)


def config_report(init: bool = False) -> bool:
    """--show-config / --init-config."""
    path = config_path()
    if path is None:
        print("The config file is switched off (PDFMD_CONFIG is empty).")
        return True
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
    return True


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


def translit_report() -> bool:
    """`--translit list`: the packs, which are on, which could work."""
    module = unicode_module()
    print("Romanization packs (names in other scripts, found by typing them in Latin letters):")
    print("  cyrillic   always on: Russian, Ukrainian, Belarusian, Kazakh (built in)")
    if module is None:
        print("  the other packs are part of the pdfmd_unicode package, which is not installed here")
        return False
    for pack in module.translit.PACKS:
        state = ("on" if pack in TRANSLIT_PACKS else "ready" if module.translit.available(pack)
                 else "needs " + module.translit.needs(pack))
        scripts = ", ".join(sorted(module.SCRIPT_NAMES.get(code, code)
                                   for code in module.translit.PACK_SCRIPTS.get(pack, ()))) or "all the rest"
        print(f"  {pack:<10} {state:<44} {scripts}")
    print("Turn them on with --translit greek,hangul (or all), or PDFMD_TRANSLIT=greek,hangul.")
    return True


# install_kind, uninstall_kind, KIT_SOURCES_DEFAULT and kit_install_settings: lib/pdfmd_install/__init__.py (v3.33.35)


def kits_install_directory() -> Path | None:
    """The folder pdfmd installs kits into: `kits/` beside the config file, which kit discovery reads already."""
    config = config_path()
    return None if config is None else config.parent / "kits"


# install_kits: lib/pdfmd_install/__init__.py (v3.33.35)


def uninstall_kit(name: str) -> bool:
    """`pdfmd --uninstall kit:NAME`: remove a kit that `--install kit` put in the kits folder (never one placed there by hand)."""
    from pdfmd_kits import install as kit_installer
    target = kits_install_directory()
    if target is None:
        print("ERROR  PDFMD_CONFIG is empty: there is no config folder", file=sys.stderr)
        return False
    try:
        folder = kit_installer.uninstall(name, target)
    except kit_installer.InstallError as error:
        print(f"ERROR  {error}", file=sys.stderr)
        return False
    print(f"REMOVED  {display_path(folder)}")
    return True


# install_fonts: lib/pdfmd_install/__init__.py (v3.33.35)


def uninstall_fonts(names: str) -> bool:
    module = unicode_module()
    if module is None:
        return False
    from pdfmd_unicode import install as installer
    try:
        keys = installer.resolve(names.split(",")) if names.strip() else []
    except installer.UnknownPackage as error:
        print(f"No font package or group called {error.args[0]!r}.", file=sys.stderr)
        return False
    if not keys:
        print("Name what to remove: pdfmd --uninstall fonts:arabic,cjk-sc", file=sys.stderr)
        return False
    installer.uninstall(keys, fonts_directory())
    reset_font_caches()
    return True


def tessdata_directory() -> Path:
    """Where pdfmd keeps the Tesseract language files `pdfmd --install ocr:LANG` fetches."""
    return data_root() / "tessdata"


def install_ocr_languages(names: str, remove: bool = False) -> bool:
    """`pdfmd --install ocr[:LANG,...]` / `--uninstall ocr:LANG`: list the languages, or fetch them
    (pdfmd_unicode/tessdata.py)."""
    if unicode_module() is None:
        print("The OCR language installer is part of the pdfmd_unicode package, which is not installed "
              "beside this file (pip install pdfmd-cli).", file=sys.stderr)
        return False
    from pdfmd_unicode import tessdata
    if not names.strip():
        if remove:
            print("Name what to remove: pdfmd --uninstall ocr:rus,kaz", file=sys.stderr)
            return False
        print(tessdata.table(tessdata_directory()))
        return True
    try:
        codes = tessdata.resolve(names.split(","))
    except tessdata.UnknownLanguage as error:
        print(f"No Tesseract language called {error.args[0]!r}. `pdfmd --install ocr` lists them.", file=sys.stderr)
        return False
    if remove:
        tessdata.uninstall(codes, tessdata_directory())
        return True
    failed = tessdata.install(codes, tessdata_directory())
    done = [code for code in codes if code not in failed]
    if done:
        print(f"Installed {', '.join(done)} in {tessdata_directory()}; `pdfmd scan.pdf --lang {'+'.join(done)}` "
              "uses them (remove with `pdfmd --uninstall ocr:LANG`).")
    return not failed


# tessdata_environment: lib/pdfmd_routing/__init__.py (v3.33.25)


def reset_font_caches() -> None:
    global _FONT_INDEX, _MANAGED_INDEX
    _FONT_INDEX = _MANAGED_INDEX = None
    # the cached functions are in pdfmd_unicode.fonts_choice (v3.33.34), whose stand-ins here have no cache_clear;
    # before that module is loaded nothing is cached
    fonts = sys.modules.get("pdfmd_unicode.fonts_choice")
    for name in ("font_missing", "system_font_missing", "default_monofont", "fallback_font", "preferred_font"):
        clear = getattr(getattr(fonts, name, None), "cache_clear", None)
        if clear:
            clear()


# install_extra: lib/pdfmd_install/__init__.py (v3.33.35)


def setup_module():
    try:
        import pdfmd_setup
    except ImportError:
        return None
    return pdfmd_setup


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
    return found + named


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



def package_lua_names(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None = None) -> list[str]:
    """The Lua filters a document's LaTeX packages bring: `<package>.lua` for each local package its preamble loads, and what
    the package's `<package>-pdfmd.yaml` lists under `lua:` (v3.28.37; before, one package's name was written in pdfmd)."""
    names: list[str] = []
    for folder, package, _ in office_packages(md_path, metadata_files, None):
        listed = [f"{package}.lua"]
        helper = package_helper(folder, package, no_auto, md_path)
        extra = helper[0].get("lua") if helper else None
        listed += [str(item) for item in ([extra] if isinstance(extra, str) else extra if isinstance(extra, list) else [])]
        names += [name for name in listed if name not in names and "/" not in name and "\\" not in name]
    return names


def find_lua_filters(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None = None) -> list[Path]:
    """Find Pandoc Lua filters that belong to a document, without guessing.

    Only these names are auto-applied: a filter matching the document's own stem
    (report.md -> report.lua) and the Lua filters of the LaTeX packages it loads
    (package_lua_names: `<package>.lua`), beside the document or its metadata. Anything
    else has to be passed explicitly, so an unrelated .lua file sitting in a folder can
    never silently change a render.
    """
    directories: list[Path] = accessory_directories(md_path.parent, md_path.stem)
    directories += [metadata.parent for metadata in metadata_files]
    wanted = (f"{md_path.stem}.lua", *package_lua_names(md_path, metadata_files, no_auto))
    found: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        for name in wanted:
            candidate = (directory / name).resolve()
            if candidate.is_file() and candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
    for item in active_kits(md_path, metadata_files, None):         # the Lua filters a chosen kit names
        for candidate in (path.resolve() for path in item.kit.lua):
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


# -- Discovered Lua filters: noticed, not blocked (v3.26.11) -----------------------------------------------------
# A Lua filter can run any command, and pdfmd runs `<name>.lua` and a loaded package's `<package>.lua` beside a document (and the files
# a document names in `pdfmd-options.lua-filter`) without being asked. So the first build with a filter pdfmd has not run
# before prints a NOTE, and so does the first build after the file changed (path and SHA-256 are kept in
# ~/.config/pdfmd/known-lua.txt); the filter still runs, so a filter you edit every day never gets in the way, and
# there is never a prompt (CI, `-j`, `-w` and the Python API have no one to ask). `pdfmd --trust-lua FOLDER` marks a
# folder you work in: nothing in it is noted again. Only `--strict` skips a new or edited filter outside such a folder
# (with a WARN). This does not protect the FIRST run of a folder you have just downloaded: read its .lua first.
def lua_known_path() -> Path:
    return config_root() / "known-lua.txt"


def lua_folders_path() -> Path:
    return config_root() / "trusted-lua-folders.txt"


def lua_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def known_lua() -> dict[str, str]:
    """{resolved path: SHA-256 it last ran with}; a later line for a path replaces an earlier one."""
    known: dict[str, str] = {}
    try:
        for line in lua_known_path().read_text(encoding="utf-8").splitlines():
            digest, _, name = line.strip().partition(" ")
            if digest and name:
                known[name] = digest
    except OSError:
        pass
    return known


def remember_lua(entries: list[tuple[str, str]]) -> None:
    if not entries:
        return
    try:
        lua_known_path().parent.mkdir(parents=True, exist_ok=True)
        with lua_known_path().open("a", encoding="utf-8") as handle:
            for digest, name in entries:
                handle.write(f"{digest} {name}\n")
    except OSError:
        pass


def trusted_lua_folders() -> list[Path]:
    try:
        return [Path(line.strip()) for line in lua_folders_path().read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")]
    except OSError:
        return []


def check_lua_filters(md_path: Path, filters: list[Path], strict: bool) -> list[Path]:
    """The filters that run: all of them, with a NOTE for each one new here or edited since it last ran; with
    ``strict`` a new or edited one outside a trusted folder is skipped, with a WARN."""
    if not filters:
        return filters
    known, folders = known_lua(), trusted_lua_folders()
    keep: list[Path] = []
    fresh: list[tuple[str, str]] = []
    for path in filters:
        key = str(path.resolve())
        digest = lua_digest(path)
        if digest is None or known.get(key) == digest or any(path.resolve().is_relative_to(folder) for folder in folders):
            keep.append(path)
            continue
        what = "is new here" if key not in known else "has changed since it last ran here"
        advice = ("A Lua filter can run any command: read it, or mark a folder you work in with "
                  "`pdfmd --trust-lua FOLDER` to stop this note")
        if strict:
            print(f"WARN  {display_path(md_path)}: the Lua filter {path.name} {what} and was not run (--strict). {advice}",
                  file=sys.stderr)
            continue
        print(f"NOTE  {display_path(md_path)}: the Lua filter {path.name} {what}; it runs. {advice}")
        keep.append(path)
        fresh.append((digest, key))
    remember_lua(fresh)
    return keep


def trust_lua(paths: list[Path]) -> bool:
    """--trust-lua PATH...: a folder is trusted for good, a file as it is now. True when every path was found."""
    complete = True
    for path in paths:
        path = path.expanduser().resolve()
        if path.is_dir():
            if path not in trusted_lua_folders():
                lua_folders_path().parent.mkdir(parents=True, exist_ok=True)
                with lua_folders_path().open("a", encoding="utf-8") as handle:
                    handle.write(f"{path}\n")
            print(f"OK    Lua filters under {display_path(path)} run without a note")
        elif path.is_file() and lua_digest(path):
            remember_lua([(lua_digest(path), str(path))])
            print(f"OK    {display_path(path)} is trusted as it is now (an edit is noted again; trust its folder to stop that)")
        else:
            print(f"FAIL  {display_path(path)}: no such file or folder", file=sys.stderr)
            complete = False
    return complete


PDFMD_LUA_WARNED: set[str] = set()


def pdfmd_lua_missing(name: str = "") -> None:
    """One WARN per run: pdfmd's own Lua filters (the package pdfmd_lua, or one file of it) are not there, so what they do is
    skipped. A lone copy of pdfmd.py has no pdfmd_lua; so does a checkout with the folder deleted."""
    key = name or "package"
    if key in PDFMD_LUA_WARNED:
        return
    PDFMD_LUA_WARNED.add(key)
    what = (f"pdfmd_lua/{name}.lua is missing from the pdfmd_lua package" if name
            else "the pdfmd_lua package is not installed beside pdfmd.py")
    print(f"WARN  lua: {what}, so pdfmd's own Lua filters do nothing in this run (tables sized by content, CSV tables, "
          "calculations, indents, page breaks, markup ...). Install pdfmd-cli (`pipx install pdfmd-cli`) or keep the pdfmd_* "
          "folders of the repository beside pdfmd.py", file=sys.stderr)


@contextmanager
def lua_filter_file(name: str, prefix: str) -> Iterator[Path]:
    """The path of pdfmd's own Lua filter `name` (pdfmd_lua/NAME.lua) for --lua-filter.

    Without the pdfmd_lua package (a lone copy of this script), or without that file, a filter that does nothing is
    written to a temporary file instead, so the callers need no special case -- and one WARN per run says that the filters
    are missing (pdfmd_lua_missing).
    """
    shipped = None
    try:
        import pdfmd_lua
        shipped = pdfmd_lua.path(name)
    except ImportError:
        pdfmd_lua_missing()
    else:
        if shipped is None:
            pdfmd_lua_missing(name)
    if shipped is not None:
        yield shipped
        return
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".lua", prefix=prefix, delete=False) as temporary:
        temporary.write("return {}\n")
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


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
OWN_SCRIPT_SETUP_RE = re.compile(r"ucharclasses|\\newfontfamily|\\babelfont|xeCJK|luatexja|CJKutf8|\\setCJK"
                                 r"|add_fallback|\\setTransition|\\setmainfontfallback")
OWN_SCRIPT_VARIABLES = ("CJKmainfont", "CJKsansfont", "CJKmonofont", "mainfontfallback")
BIBLIOGRAPHY_TEXT_SUFFIXES = (".bib", ".bibtex", ".json", ".yaml", ".yml", ".ris", ".csl")
_FONT_INDEX = None


def unicode_module():
    """pdfmd_unicode, or None where it is not installed beside this file."""
    try:
        import pdfmd_unicode
    except ImportError:
        return None
    return pdfmd_unicode


def fonts_directory() -> Path:
    """Where pdfmd keeps the fonts `pdfmd --install fonts` fetches."""
    return data_root() / "fonts"


_MANAGED_INDEX = None


def managed_index():
    """Only the fonts in pdfmd's own folder (cheap: no system scan)."""
    global _MANAGED_INDEX
    if _MANAGED_INDEX is None:
        module = unicode_module()
        _MANAGED_INDEX = module.FontIndex(fonts_directory(), use_system=False) if module else False
    return _MANAGED_INDEX or None


def managed_face(family: str):
    index = managed_index()
    face = index.regular(family) if index is not None else None
    return face if face is not None and face.managed else None


# font_args: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)


# The math font that goes with a text font (v3.28.24). unicode-math sets formulas in Latin Modern Math (Typst: New
# Computer Modern Math) unless told otherwise, so a document in STIX Two Text had formulas that did not match its body. A
# row is (the text font pdfmd chooses, the math fonts that go with it: the first one installed is used; several spellings
# of one family, as fontconfig and Typst name them).
MATH_COMPANIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("STIX Two Text", ("STIX Two Math",)),
    ("DejaVu Serif", ("DejaVu Math TeX Gyre",)),
    ("Libertinus Serif", ("Libertinus Math",)),
    ("New Computer Modern", ("New Computer Modern Math", "NewComputerModern Math")),
    ("TeX Gyre Termes", ("TeX Gyre Termes Math",)),
    ("TeX Gyre Pagella", ("TeX Gyre Pagella Math",)),
)
_TEMPLATE_VARIABLES: dict[tuple[str, str], bool] = {}


def template_has_variable(writer: str, variable: str) -> bool:
    """Whether Pandoc's default template for ``writer`` reads ``$variable$`` (Pandoc 3.1.3's Typst one has no mathfont)."""
    key = (writer, variable)
    if key not in _TEMPLATE_VARIABLES:
        try:
            done = subprocess.run(["pandoc", "-D", writer], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
            _TEMPLATE_VARIABLES[key] = done.returncode == 0 and f"$if({variable})$" in done.stdout
        except (OSError, subprocess.SubprocessError):
            _TEMPLATE_VARIABLES[key] = False
    return _TEMPLATE_VARIABLES[key]


def math_companion(main_font: str) -> str | None:
    """The installed math font that goes with ``main_font``, None when there is none (or the font is not in the table)."""
    for text_font, candidates in MATH_COMPANIONS:
        if text_font.casefold() == main_font.casefold():
            return next((name for name in candidates if not system_font_missing(name)), None)
    return None


def mathfont_args(main_font: str | None, md_path: Path, metadata_files: list[Path], variables: list[str],
                  cli_font: str | None, no_auto: list[str] | None, engine: str | None, note=None) -> list[str]:
    """`-V mathfont=<companion>` when pdfmd chose the main font itself (no -f, no mainfont: or mathfont: in the document or
    its metadata files), the companion math font is installed, and the engine can use it (lualatex, xelatex, tectonic, Typst
    with a Pandoc whose template knows mathfont; not pdfLaTeX; ``engine`` None is a LaTeX file that any engine builds)."""
    if (not main_font or cli_font or auto_disabled(no_auto, "mathfont")
            or has_mainfont(md_path, variables, metadata_files) or has_font_setting("mathfont", md_path, variables, metadata_files)):
        return []
    if engine is not None and engine not in ("lualatex", "xelatex", "tectonic", "typst"):
        return []
    companion = math_companion(main_font)
    if companion is None or (engine == "typst" and not template_has_variable("typst", "mathfont")):
        return []
    if note:
        note("MATHFONT", f"{md_path}: no mathfont set; using {companion} to go with {main_font}")
    return ["-V", f"mathfont={companion}"]


def document_font_args(md_paths: list[Path], metadata_files: list[Path], variables: list[str]) -> list[str]:
    """`-V` arguments for the fonts a document itself names (mainfont/sansfont/monofont) that
    exist only in pdfmd's own fonts folder, so LaTeX can load them by file."""
    args: list[str] = []
    for kind in ("mainfont", "sansfont", "monofont"):
        if any(variable.startswith(f"{kind}options=") for variable in variables):
            continue
        family = document_font_setting(kind, md_paths, metadata_files, variables)
        if family and managed_face(family) is not None and system_font_missing(family):
            args += font_args(kind, family)
    return args


def font_index():
    """The installed fonts (and pdfmd's own), read once per run."""
    global _FONT_INDEX
    if _FONT_INDEX is None:
        module = unicode_module()
        _FONT_INDEX = module.FontIndex(fonts_directory()) if module else False
    return _FONT_INDEX or None


def strip_code_text(text: str) -> str:
    """Markdown without its fenced and inline code (set in the monofont, not a fallback's)."""
    text = re.sub(r"(?ms)^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", "", text)
    return re.sub(r"`[^`\n]*`", "", text)


def unicode_source_text(md_paths: list[Path], metadata_files: list[Path]) -> str:
    """All the text a document will print: its Markdown, metadata and bibliography files."""
    pieces: list[str] = []
    seen: set[Path] = set()

    def read(path: Path, code: bool = False) -> str:
        try:
            if path.resolve() in seen or not path.is_file():
                return ""
            seen.add(path.resolve())
            data = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return ""
        return data if code else strip_code_text(data)

    for path in [*md_paths, *metadata_files]:
        text = read(path)
        pieces.append(text)
        front = front_matter_dict(text) if path.suffix.lower() in (".md", ".markdown", ".txt", "") \
            else metadata_file_yaml(path)
        wanted = front.get("bibliography") if isinstance(front, dict) else None
        for name in (wanted if isinstance(wanted, list) else [wanted] if wanted else []):
            candidate = Path(str(name))
            for folder in (path.parent, Path.cwd()):
                found = candidate if candidate.is_absolute() else folder / candidate
                if found.suffix.lower() in BIBLIOGRAPHY_TEXT_SUFFIXES and found.is_file():
                    pieces.append(read(found, code=True))
                    break
    return "\n".join(pieces)


def document_font_setting(key: str, md_paths: list[Path], metadata_files: list[Path],
                          variables: list[str]) -> str | None:
    """A Pandoc variable as the document sets it: -V, then its front matter, then metadata files."""
    for variable in variables:
        if variable.startswith(f"{key}="):
            return variable.split("=", 1)[1] or None
    for path in [*md_paths[:1], *metadata_files_by_priority(metadata_files)]:
        try:
            data = (front_matter_dict(path.read_text(encoding="utf-8-sig"))
                    if path.suffix.lower() in (".md", ".markdown", ".txt", "") else metadata_file_yaml(path))
        except (OSError, UnicodeDecodeError):
            continue
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return None


# unicode_code_text: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)


def own_script_setup(md_paths: list[Path], preamble_files: list[Path], variables: list[str],
                     metadata_files: list[Path]) -> bool:
    """Whether the document already sets up its own fonts per script."""
    if any(variable.split("=", 1)[0] in OWN_SCRIPT_VARIABLES for variable in variables):
        return True
    if any(document_font_setting(key, md_paths, metadata_files, []) for key in OWN_SCRIPT_VARIABLES):
        return True
    texts = [item.read_text(encoding="utf-8-sig", errors="replace") for item in preamble_files if item.is_file()]
    texts += [document_header_includes(item.read_text(encoding="utf-8-sig", errors="replace")) or ""
              for item in md_paths if item.suffix.lower() in (".md", ".markdown", ".txt")]
    return any(OWN_SCRIPT_SETUP_RE.search(text) for text in texts)


# unicode_forced: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)


# What to do about characters the main font cannot draw (`pdfmd-options: {fallback: ..., missing: ...}`,
# --fallback / --missing, the config file's `options:`). See CONFIG_TEMPLATE for the meaning of each.
FALLBACK_MODES = ("char", "word", "document", "off", "box", "error")
MISSING_MODES = ("warn", "box", "error")
FALLBACK_NAMES = {"character": "char", "per-character": "char", "run": "char", "words": "word",
                  "per-word": "word", "whole": "document", "whole-document": "document", "doc": "document",
                  "none": "off", "no": "off", "false": "off", "true": "word", "on": "word", "yes": "word",
                  "black-box": "box", "err": "error", "fail": "error"}
FALLBACK_CLI: str | None = None
MISSING_CLI: str | None = None


def normalise_mode(value, allowed: tuple[str, ...], aliases: dict[str, str], label: str, source: str) -> str | None:
    if value is None:
        return None
    if value is False:      # YAML reads a bare `off` or `no` as false
        text = "off"
    elif value is True:
        text = "on"
    else:
        text = str(value).strip().casefold()
    text = aliases.get(text, text)
    if text not in allowed:
        raise SystemExit(f"{source}: {label} {value!r} is not one of {', '.join(allowed)}")
    return text


def fallback_settings(md_path: Path, metadata_files: list[Path]) -> tuple[str, str]:
    """(fallback mode, missing mode): the command line, else the document, its metadata files, the
    config file, else word / warn. `box` and `error` as a fallback mode mean no fallback and that
    treatment of every missing character."""
    where = f"{md_path}: pdfmd-options"
    mode = normalise_mode(FALLBACK_CLI, FALLBACK_MODES, FALLBACK_NAMES, "--fallback", "pdfmd") or normalise_mode(
        first_pdfmd_option(md_path, metadata_files, "fallback"), FALLBACK_MODES, FALLBACK_NAMES,
        "fallback", where) or "word"
    missing = normalise_mode(MISSING_CLI, MISSING_MODES, FALLBACK_NAMES, "--missing", "pdfmd") or normalise_mode(
        first_pdfmd_option(md_path, metadata_files, "missing"), MISSING_MODES, FALLBACK_NAMES,
        "missing", where) or "warn"
    if mode in ("box", "error"):
        missing = mode
    return mode, missing


def mainfont_choice(md_paths: list[Path], metadata_files: list[Path], variables: list[str],
                    cli_font: str | None, document_font: bool, mainfont_auto: bool,
                    no_auto: list[str] | None, note=None) -> str | None:
    """The main font to pass to Pandoc (None: leave the document's own). A font the document or the
    command line names is never changed for a few missing characters -- that is the fallback's job --
    except in `fallback: document` mode, where the installed font that draws most of the document
    replaces it. pdfmd's own default (no font named) is changed, with an AUTO MAINFONT note, when it
    lacks letters of the script the document is mostly written in (STIX Two Text has no Kazakh
    Cyrillic), so the text is not set half in one font and half in another."""
    explicit = cli_font or (document_font_setting("mainfont", md_paths, metadata_files, variables)
                            if document_font else None)
    if explicit:
        base = explicit
    elif mainfont_auto:
        base = preferred_font()
    else:
        return None
    module, index = unicode_module(), font_index()
    if (module is not None and index is not None and not auto_disabled(no_auto, "unicode")
            and not own_script_setup(md_paths, [], variables, metadata_files)):
        mode = fallback_settings(md_paths[0], metadata_files)[0]
        text = unicode_source_text(md_paths, metadata_files) if mode in ("document", "char", "word") else ""
        if mode == "document":
            chosen = module.choose_document_font(text, base, index)
            reason = "fallback: document"
        elif mode in ("char", "word") and not explicit:
            chosen = module.choose_main_font(text, base, index)
            reason = "it lacks letters of the document's own script"
        else:
            chosen = base
        if chosen != base:
            if note:
                note("MAINFONT", f"{md_paths[0]}: {chosen} instead of {base} ({reason}; "
                                 f"name a font with mainfont: to keep your own)")
            return chosen
    if cli_font:
        return cli_font
    if not document_font and note:
        # pdfmd's own default, named like every other default it applies (v3.28.14; it was silent)
        note("MAINFONT", f"{md_paths[0]}: no mainfont set; using {base}")
    return None if document_font else base


# managed_fonts_css, check_fonts, describe_code_points and script_fallback: lib/pdfmd_unicode/fonts_choice.py (v3.33.34)


# latin_candidates, cyrillic_candidates, strip_lookup_suffix, find_wildcard_markdown, lookup_key, lookup_query_keys, LookupAmbiguous,
# lookup_field_matches, rank_lookup, lookup_fields, priority_enabled, source_markdown and document_priority, with LOOKUP_MIN_PREFIX,
# LOOKUP_HEAD_BYTES, LOOKUP_TIERS, LOOKUP_FIELD_WORDS and GENERATED_MARKDOWN_ENDINGS: lib/pdfmd_lookup/__init__.py (v3.33.20)


def name_candidates(value: str) -> list[str]:
    value = strip_lookup_suffix(value)
    candidates = [value]
    if not TRANSLIT_CYRILLIC:  # --translit none
        return candidates
    if re.search("[А-Яа-яЁё]", value):
        candidates += cyrillic_candidates(value)
    else:
        candidates += latin_candidates(value)
    candidates = list(dict.fromkeys(candidates))
    return candidates + [f"Пробный {item}" for item in candidates]


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
LOOKUP_SCAN_LIMIT = 500    # Markdown files whose front matter is read

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


# Romanization packs beyond Cyrillic (see pdfmd_unicode/translit.py): none unless asked for with
# --translit / PDFMD_TRANSLIT. Cyrillic is built in and on, unless `--translit none` says otherwise.
TRANSLIT_PACKS: frozenset[str] = frozenset()
TRANSLIT_CYRILLIC = True


def set_translit(spec: str | None) -> list[str]:
    """Choose the romanization packs from a --translit / PDFMD_TRANSLIT value: names separated by
    commas or spaces, `all`, or `none` (Cyrillic off too). Returns problems to report."""
    global TRANSLIT_PACKS, TRANSLIT_CYRILLIC
    problems: list[str] = []
    packs: set[str] = set()
    TRANSLIT_CYRILLIC = True
    module = unicode_module()
    known = module.translit.PACKS if module else ()
    for word in re.split(r"[,\s]+", (spec or "").strip().casefold()):
        if not word:
            continue
        if word == "none":
            packs.clear()
            TRANSLIT_CYRILLIC = False
        elif word == "all":
            packs.update(known)
        elif word == "cyrillic":
            TRANSLIT_CYRILLIC = True
        elif word in known:
            packs.add(word)
        else:
            problems.append(f"unknown romanization pack {word!r}; choose from cyrillic (always on), "
                            f"{', '.join(known) or 'none installed'}, all, none")
    for pack in sorted(packs):
        if not module.translit.available(pack):
            problems.append(f"the {pack} pack needs a library: {module.translit.needs(pack)} "
                            "(pdfmd --install translit)")
            packs.discard(pack)
    TRANSLIT_PACKS = frozenset(packs)
    lookup_key.cache_clear()
    return problems


# HEADING_FIELD_WORDS: lib/pdfmd_parts/__init__.py (v3.33.30)


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


def skip_never(files: list[Path], include_never: bool = False) -> list[Path]:
    """``files`` without the documents that say `priority: never` (or another word of a class with `exclude`), which are named in
    one NOTE: what `-b`, `-r` and the viewer list from a folder. ``include_never`` (`--all`) keeps them, and so does
    `--no-auto priority`. A document named on the command line is never dropped: the callers pass only what a folder gave them."""
    if include_never:
        return files
    from pdfmd_ranking import MISSING
    by_folder: dict[Path, list[Path]] = {}
    for file in files:
        by_folder.setdefault(file.parent, []).append(file)
    dropped: list[Path] = []
    for folder_files in by_folder.values():
        if not priority_enabled(folder_files[0].parent):
            continue
        values = {file: document_priority(file) for file in folder_files}
        if all(value is MISSING for value, _ in values.values()):
            continue
        try:
            ranking = bare_ranking(folder_files)
        except Exception as error:
            print(f"WARN  ranking: {error}; every document of {display_path(folder_files[0].parent)} is kept", file=sys.stderr)
            continue
        for file, (value, _) in values.items():
            if value is not MISSING and ranking.read(value).kind == "excluded":
                dropped.append(file)
    if dropped:
        print(f"NOTE  left out (priority: never): {', '.join(display_path(file) for file in dropped)}  (--all builds them too)")
    return [file for file in files if file not in dropped]


def choose_markdown(files: list[Path], newest: bool = False, include_never: bool = False) -> Path:
    """The one of several Markdown files of a folder that bare `pdfmd` builds; says so (an AUTO MD line, WARNs), or stops with
    the reason (SystemExit) when equal documents cannot be told apart. ``newest`` (`--newest`): by modification time alone;
    ``include_never`` (`--all`): the documents that say `never` take part as if they had said nothing."""
    from pdfmd_ranking import RankingError, choose
    candidates = priority_candidates(files)
    try:
        ranking = bare_ranking(files)
    except RankingError as error:
        raise SystemExit(f"ranking: {error}")
    choice = choose(candidates, ranking, by=["newest"] if newest else None, show=display_path, include_excluded=include_never)
    for line in [f"WARN  ranking: {text}" for text in ranking.warnings] + choice.warnings:
        print(line, file=sys.stderr)
    if choice.error or choice.winner is None:
        raise SystemExit(choice.error or "No Markdown file could be chosen.")
    beaten = choice.beaten(display_path)
    print(f"AUTO MD    {display_path(choice.winner)}" + (f"  (over {beaten})" if beaten else ""))
    return choice.winner


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


def has_mainfont(md_path: Path, variables: list[str], metadata_files=()) -> bool:
    return has_font_setting("mainfont", md_path, variables, metadata_files)


def has_font_setting(key: str, md_path: Path, variables: list[str], metadata_files=()) -> bool:
    """Whether the document names this font itself: with -V, in its front matter, or in a metadata file it gets
    (the folder's metadata.yaml, the global one of pdfmd --setup). Until v3.28.14 only the first two counted, so
    pdfmd's own default (`-V mainfont=STIX Two Text`, `-V monofont=JetBrains Mono`) overrode a metadata file's."""
    if any(variable.startswith(f"{key}=") for variable in variables):
        return True
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = LEADING_FRONT_MATTER_RE.match(text)
    if front_matter and re.search(rf"^{key}\s*:", front_matter.group(1), re.MULTILINE):
        return True
    return any(metadata_file_yaml(path).get(key) not in (None, "") for path in metadata_files)


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
    front_matter = LEADING_FRONT_MATTER_RE.match(text)
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
    is set anywhere; YAML support is unavailable (falls back to the
    scalar-only regex this function used before parse_margin_sides()
    existed, since a real parse is needed for the mapping case -- checked
    per source, same order); or every ``margin:`` found uses Typst's
    ``inside``/``outside``/``rest`` keys, which have no LaTeX equivalent
    (see parse_margin_sides()).
    """
    if any(variable.startswith(("geometry=", "geometry:")) for variable in variables):
        return None
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = LEADING_FRONT_MATTER_RE.match(text)
    blocks = [front_matter.group(1)] if front_matter else []
    for metadata_file in metadata_files_by_priority(metadata_files):
        meta_text = metadata_file.read_text(encoding="utf-8-sig")
        # A --metadata-file may be fenced (---...---, same as front matter)
        # or completely bare -- Pandoc accepts either. yaml.safe_load()
        # chokes on the fenced shape as-is (a second "---" reads as a
        # second YAML document, "expected a single document in the
        # stream"), so unwrap it the same way md_path's own front matter
        # is, and only fall back to the raw text when it isn't fenced.
        meta_front_matter = LEADING_FRONT_MATTER_RE.match(meta_text)
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


def paper_kind(engine: str | None, no_auto: list[str] | None) -> str | None:
    """The kind of paper handling (paper_variables) for an engine or output: LaTeX ones, Typst, WeasyPrint."""
    if auto_disabled(no_auto, "papersize"):
        return None
    return "tex" if engine in LATEX_ENGINES - {"context"} | {"tex"} else engine if engine in ("typst", "weasyprint") else None


PAPER_ORIENTATIONS = ("landscape", "portrait")
LATEX_CLASS_PAPERS = frozenset({"a4", "a5", "b5", "letter", "legal", "executive"})      # the paper options of a LaTeX class
TYPST_PAPER_NAMES = {"letter": "us-letter", "legal": "us-legal", "tabloid": "us-tabloid", "ledger": "us-ledger",
                     "executive": "us-executive", "folio": "us-foolscap-folio"}


def paper_words(value) -> tuple[str, str]:
    """`a4,landscape` -> (`a4`, `landscape`): the size and the orientation of a `papersize:` value, "" for each that is not
    there. The size is lower case, without a trailing `paper` (`a4paper`) and with `us-letter` as `letter`."""
    size, orientation = "", ""
    for word in re.split(r"[,\s]+", scalar_text(value)):
        name = word.casefold()
        if name in PAPER_ORIENTATIONS:
            orientation = name
        elif name:
            name = PAPER_NAME_ALIASES.get(name, name)
            size = size or (name[:-5] if name.endswith("paper") and len(name) > 5 else name)
    return size, orientation


def paper_variables(md_path: Path, metadata_files: list[Path], variables: list[str], pagesize_typo: str | None,
                    kind: str | None) -> tuple[list[str], str | None]:
    """(variables, pagesize_typo) with the paper of the document settled for one kind of output (v3.30.42): "tex" (a LaTeX
    engine), "typst" or "weasyprint"; any other kind is returned as it came. Pandoc's `papersize` is a LaTeX class option, so
    `a4,landscape` printed `[a4,landscapepaper]` (a Letter page, silently), `a4paper` printed `a4paperpaper`, `a3` is no
    class option, and Typst and WeasyPrint did not read it: pdfmd gives each engine its own spelling. The paper of
    `--paper`, `-V papersize=` or the front matter, its orientation word, and `landscape` in `geometry:` or
    `classoption:` all reach the page. A single `-V papersize=` is left alone when it is already right."""
    if kind not in ("tex", "typst", "weasyprint"):
        return variables, pagesize_typo
    given = [item.split("=", 1)[1] for item in variables if item.startswith("papersize=")]
    merged = effective_metadata(md_path, metadata_files, variables)
    raw = given[-1] if given else (pagesize_typo or scalar_text(merged.get("papersize")))
    size, orientation = paper_words(raw)
    module = office_module()
    landscape = orientation == "landscape"
    if not orientation and module is not None:
        landscape = module.spec_from_metadata(merged, None, "exact").landscape
    rest = [item for item in variables if not item.startswith("papersize=")]
    if kind == "tex":
        extra: list[str] = []
        paper = size
        if size not in LATEX_CLASS_PAPERS and re.fullmatch(r"[abc][0-6]", size):
            paper = ""                                       # `a3`: geometry has it, the class does not
            extra.append(f"geometry:{size}paper")
        if orientation == "landscape":
            extra.append("geometry:landscape")
        if len(given) <= 1 and paper == raw and not extra:
            return variables, pagesize_typo
        if not raw:
            return variables, pagesize_typo
        return rest + ([f"papersize={paper}"] if paper or not given else []) + extra, None
    if kind == "typst":
        if not raw and not landscape:
            return variables, pagesize_typo
        name = TYPST_PAPER_NAMES.get(size) or (f"iso-{size}" if re.fullmatch(r"[bc][0-8]", size) else size)
        return rest + ([f"papersize={name}"] if name else []) + (["pdfmd-page-flipped=true"] if landscape else []), None
    points = NATIVE_PAPER_POINTS.get(size)
    if points is None and not landscape:
        return variables, pagesize_typo
    if points is None:
        css = "landscape"
    else:
        width, height = (points[1], points[0]) if landscape else points
        css = f"{width:g}pt {height:g}pt"
    return rest + [f"pdfmd-page={css}"], pagesize_typo


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
    front_matter = LEADING_FRONT_MATTER_RE.match(text)
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


def has_monofont(md_path: Path, variables: list[str], metadata_files=()) -> bool:
    return has_font_setting("monofont", md_path, variables, metadata_files)


# Raw content (v3.28.17): ```{=latex} ... ``` and `x`{=html}, in any format, is not code -- Pandoc hands it to the
# writer as it is, and `{=pdfmd}` blocks are the same shape. A plain ```{pdfmd} fence (no `=`) is ordinary code.
# The fence is any run of three or more backticks (or tildes) -- a longer one lets the block hold shorter ones -- and
# the closing line is a run of at least as many.
CODE_RAW_FENCE_RE = re.compile(r"^[ \t]*(?P<fence>(?P<c>[`~])(?P=c){2,})[ \t]*\{=[^}\n]*\}[ \t]*\n.*?\n[ \t]*(?P=fence)(?P=c)*[ \t]*$",
                          re.MULTILINE | re.DOTALL)
CODE_RAW_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1\{=[^}\s]+\}", re.DOTALL)


def has_code_spans(text: str) -> bool:
    """Detect inline code or fenced code blocks -- the only things Pandoc's
    LaTeX writer actually sets in the monofont. A bare backtick covers both
    (a fence is just 3+ backticks), plus the rarer ``~~~`` fence style; raw
    blocks and spans (`{=latex}`, `{=html}`, `{=typst}`, `{=pdfmd}` ...) are not code.
    """
    text = CODE_RAW_SPAN_RE.sub("", CODE_RAW_FENCE_RE.sub("", EMBED_BLOCK_RE.sub("", text)))
    return "`" in text or bool(re.search(r"(?m)^\s{0,3}~~~", text))


# Characters no installed font draws (script_fallback has already warned about them): a
# missing-glyph warning that is only about those is not a reason to retry with another font.
UNICODE_UNCOVERED: set[int] = set()
# The families code needs for the characters its monofont lacks, for Typst's `codefont` list and
# WeasyPrint's CSS (script_fallback sets it; LaTeX gets them through its Lua filter instead).
UNICODE_CODE_FONTS: list[str] = []


MISSING_GLYPH_LINE_RE = re.compile(r"missing character|Missing character|Unicode character .* not set|font .* not found")


def missing_glyph_warning(output: str) -> bool:
    for line in output.splitlines():
        if not MISSING_GLYPH_LINE_RE.search(line):
            continue
        codes = {int(code, 16) for code in re.findall(r"U\+([0-9A-Fa-f]{4,6})", line)}
        if not codes or not codes <= UNICODE_UNCOVERED:
            return True
    return False


def missing_glyph_codes(output: str) -> list[int]:
    """The code points a build's missing-glyph lines name (LuaLaTeX and XeLaTeX print `There is no ≥ (U+2265) in font`),
    in order; characters no installed font draws are left out (script_fallback has warned about them). A count of the lines
    is no count of the uses: LuaLaTeX prints each missing character three times."""
    codes: dict[int, None] = {}
    for line in output.splitlines():
        if MISSING_GLYPH_LINE_RE.search(line):
            for code in re.findall(r"U\+([0-9A-Fa-f]{4,6})", line):
                if int(code, 16) not in UNICODE_UNCOVERED:
                    codes[int(code, 16)] = None
    return sorted(codes)


def retry_font_note(md_path: Path, tried: str, instead: str, codes: list[int]) -> str:
    """The WARN line for the missing-glyph retry that rebuilds the whole document in another font."""
    lacks = (f"lacks {', '.join(f'U+{code:04X}' for code in codes)}" if codes
             else "lacked glyphs the build did not name (--verbose shows the log)")
    return (f"WARN  {display_path(md_path)}: {tried} {lacks}; rebuilt in {instead} "
            "(set mainfont: to keep your own)")


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
    pandoc = which("pandoc")
    if pandoc:
        try:
            text = EMBED_BLOCK_RE.sub("", obsidian_source(md_path.read_text(encoding="utf-8-sig"), md_path, show=False))
            command = [pandoc, "-f", "markdown", "-t", "json"]
            if md_macro_in(text):
                # the Markdown inside `\md{...}` is part of the document: a citation there needs --citeproc
                import pdfmd_lua
                shipped = pdfmd_lua.path("md_macro")
                if shipped is not None:
                    command += ["--lua-filter", str(shipped)]
            done = subprocess.run(command, input=text, capture_output=True,
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
    if features is not None:
        return features[0]
    text = EMBED_BLOCK_RE.sub("", obsidian_source(md_path.read_text(encoding="utf-8-sig"), md_path, show=False))
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
    text = EMBED_BLOCK_RE.sub("", md_path.read_text(encoding="utf-8-sig"))
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
    executable = which("pandoc-crossref")
    built, running = crossref_built_for(executable), pandoc_version()
    if built and running != (0,) and built[:2] != running[:2]:
        # pandoc-crossref "is not supported" through another Pandoc: it runs, and leaves ?? where the numbers go
        print(f"WARN  {label}: uses pandoc-crossref syntax, but the installed pandoc-crossref was built for Pandoc "
              f"{'.'.join(map(str, built))} and this is Pandoc {'.'.join(map(str, running))}; it would put ?? "
              "where the numbers go, so it was not run. Install the pandoc-crossref release made for this Pandoc "
              "(github.com/lierdakil/pandoc-crossref/releases), or a Pandoc to match.", file=sys.stderr)
        return []
    return ["--filter", "pandoc-crossref"]


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
    if FLAVOUR_PRESETS and single_newline_mode(md_path, metadata_files) == "hard" and "hard_line_breaks" not in (reader or ""):
        reader = f"{reader or 'markdown'}+hard_line_breaks"          # a single newline is a line break (v3.32.27)
    return reader, note


def flavour_reader(md_path: Path, metadata_files: list[Path] = ()) -> tuple[str | None, str | None]:
    """The reader a Markdown file's flavour gives (resolve_from_format adds the single newline): (reader or None for Pandoc's own, note)."""
    name, spec = flavour_setting(md_path, metadata_files)
    if spec:
        return spec, None                 # `pdfmd-options: {flavour: gfm+smart}` (or `reader:`; document, metadata file, config): --from, per document
    preset = FLAVOUR_PRESETS.get(name)
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
    text = obsidian_source(md_path.read_text(encoding="utf-8-sig"), md_path, metadata_files, show=False)   # hidden text decides nothing
    if has_yaml_frontmatter(text) or has_percent_title_block(text):
        return None, None
    if EMBED_BLOCK_RE.search(text) and is_assembled_text(text):
        # Embedded `{=pdfmd}` blocks need Pandoc's own markdown: gfm would
        # print them as code blocks.
        return None, None
    # The global metadata (`pdfmd --setup`, and its presets) is the machine's, not the document's: it says nothing about
    # which dialect this file was written in, and on a machine that has one it made every file read as Pandoc's Markdown
    # (v3.32.4). What it sets still applies: Pandoc reads a metadata file with its own Markdown, whatever the reader.
    linked_files = [metadata_file for metadata_file in metadata_files if not is_global_metadata(metadata_file)]
    if linked_files:
        names = ", ".join(metadata_file.name for metadata_file in linked_files)
        return None, (f"{md_path}: no YAML front matter, but {names} is linked; "
                      "keeping the default markdown reader instead of gfm")
    if contains_citations(md_path):
        return None, (f"{md_path}: no YAML front matter, but it uses @citation syntax "
                      "gfm can't parse; keeping the default markdown reader")
    if ORG_CAPTION_RE.search(text) and table_ascii_mode(md_path, list(metadata_files)) == "repair":
        return None, (f"{md_path}: no YAML front matter, but it has Org `#+CAPTION:` lines, which become table captions "
                      "that only Pandoc's markdown reader reads; keeping the default markdown reader instead of gfm")
    if md_macro_in(text) and md_macro_on(md_path, list(metadata_files)):
        return None, (f"{md_path}: no YAML front matter, but it has `\\md{{...}}` (Markdown inside raw LaTeX), which only Pandoc's "
                      "markdown reader keeps as raw LaTeX for pdfmd to read; keeping the default markdown reader instead of gfm")
    needs = reader_needs(text)
    pandoc_only = [name for name, extension in needs if extension is None]
    if pandoc_only:
        return None, (f"{md_path}: no YAML front matter, but it uses {', '.join(pandoc_only)}, which gfm cannot read; "
                      "keeping the default markdown reader")
    names = [name for name, _ in needs]
    extensions = [extension for _, extension in needs]
    if contains_csv_table(md_path):
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
            text = obsidian_source(text, md_path, metadata_files)
            text = repair_ascii_text(text, table_ascii_mode(md_path, list(metadata_files)), display_path(md_path))
            text = cell_tags_text(text, md_path, metadata_files, display_path(md_path))
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
    text = obsidian_source(original, md_path, metadata_files)      # an Obsidian note's %%comments%% go first: a hidden heading is no title
    corrected, shifted = text, False
    if not disabled:
        corrected, shifted = promote_bare_title(text, has_external_metadata=bool(metadata_files))
    repaired = repair_ascii_text(corrected, table_ascii_mode(md_path, list(metadata_files)), display_path(md_path))
    repaired = cell_tags_text(repaired, md_path, metadata_files, display_path(md_path))
    chapter = (REPORT_BUILD.get("chapters") or {}).get(md_path)
    if chapter is not None:
        # a report's first file: its title leaves the front matter and becomes a chapter heading (pdfmd_report.titles)
        import pdfmd_report.titles as report_titles
        repaired = report_titles.apply(sys.modules[__name__], repaired, chapter)
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
    if yaml is None:
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig")
        data = front_matter_dict(text) if LEADING_FRONT_MATTER_RE.match(text) else yaml.safe_load(text)
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


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
    own = frontmatter_value(md_path, "pdf-engine") or frontmatter_value(md_path, "engine")
    if own is not None:
        return own.strip("[]")
    for metadata_file in metadata_files_by_priority(metadata_files):
        data = metadata_file_yaml(metadata_file)
        options = data.get("pdfmd-options")
        value = (options.get("pdf-engine") or options.get("engine")) if isinstance(options, dict) else None
        if value is None:
            top = data.get("pdf-engine") or data.get("engine")
            value = words(top) if top is not None else None
        if value is not None:
            return words(value)
    configured = config_options(md_path)
    value = configured.get("pdf-engine") or configured.get("engine")
    return words(value) if value is not None else None


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
    for metadata_file in metadata_files_by_priority(metadata_files):
        data = metadata_file_yaml(metadata_file)
        options = data.get("pdfmd-options")
        value = options.get("citation-engine") if isinstance(options, dict) else None
        if value is not None:
            return str(value).casefold()
    value = config_options(md_path).get("citation-engine")
    return str(value).casefold() if value is not None else None


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


def timing_module():
    """pdfmd_buildinfo.timing, or None in a lone pdfmd.py (no time is shown then)."""
    try:
        from pdfmd_buildinfo import timing
        return timing
    except ImportError:
        return None


# begin_timer: lib/pdfmd_buildinfo/build.py (v3.33.23); `timed` below stays here, 15 definitions apply it at import


def timed(name):
    """Decorator: the call is a step of the build's timer. ``name`` is the step's name, or a function of (args, kwargs) that
    gives it, or None for a call that does no work of its own (it is then not a step)."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            timer = BUILD.get("timer")
            step = name(args, kwargs) if callable(name) and timer is not None else name
            if timer is None or step is None:
                return function(*args, **kwargs)
            with timer.step(step):
                return function(*args, **kwargs)
        return wrapper
    return decorate


# resolve_build_time and attach_time: lib/pdfmd_buildinfo/build.py (v3.33.23)


def time_label(result) -> str:
    """`  in 3:07` for the closing line; nothing when the time is off."""
    text = getattr(result, "time_text", "")
    return f"  in {text}" if text else ""


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


def record_note(text: str) -> None:
    """Add lines to the record of the build that is running (nothing when there is none)."""
    lines = BUILD.get("record")
    if lines is not None and text:
        lines.extend(text.rstrip("\n").split("\n"))


def vprint(shown: bool, *args, **kwargs) -> None:
    """print() for a line that only --verbose shows: on the console when ``shown``, and always in the record of the build
    (the first step of `emit`: the sites that print under --verbose go through here, the chatter ladder turns it into
    emit(level, id, text))."""
    if shown:
        print(*args, **kwargs)
    else:
        record_note(str(kwargs.get("sep", " ")).join(str(item) for item in args))


def noted(label, engine: bool = False):
    """Decorator: what a subprocess answered (exit code, stderr, stdout) goes into the record of the build; with
    ``engine``, the label also joins the engines the build tried."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            result = function(*args, **kwargs)
            if isinstance(result, subprocess.CompletedProcess):
                name = label(args, kwargs) if callable(label) else label
                if engine and name not in BUILD["tried"]:
                    BUILD["tried"].append(name)
                record_note(f"----- {name}: exit {result.returncode} -----")
                for stream, text in (("stderr", result.stderr), ("stdout", result.stdout)):
                    if isinstance(text, str) and text.strip():
                        record_note(f"[{stream}]\n{text.strip()}")
            return result
        return wrapper
    return decorate


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


VSCODE_TASKS = """{
  // Written by `pdfmd --init-vscode`. Run with Terminal > Run Build Task (Cmd/Ctrl+Shift+B).
  "version": "2.0.0",
  "tasks": [
    {
      "label": "pdfmd: build",
      "type": "shell",
      "command": "pdfmd",
      "args": ["${file}"],
      "group": {"kind": "build", "isDefault": true},
      "presentation": {"reveal": "silent", "panel": "shared"},
      "problemMatcher": []
    },
    {
      "label": "pdfmd: build and open",
      "type": "shell",
      "command": "pdfmd",
      "args": ["${file}", "--open"],
      "group": "build",
      "presentation": {"reveal": "silent", "panel": "shared"},
      "problemMatcher": []
    },
    {
      "label": "pdfmd: watch",
      "type": "shell",
      "command": "pdfmd",
      "args": ["-w", "${file}"],
      "isBackground": true,
      "group": "build",
      "problemMatcher": []
    },
    {
      "label": "pdfmd: check",
      "type": "shell",
      "command": "pdfmd",
      "args": ["--check", "${file}"],
      "presentation": {"reveal": "never", "panel": "shared"},
      "problemMatcher": {
        "owner": "pdfmd-check",
        "fileLocation": ["relative", "${workspaceFolder}"],
        "pattern": {"regexp": "^(.+?):(\\\\d+): (error|warning): (.*)$", "file": 1, "line": 2, "severity": 3, "message": 4}
      }
    },
    {
      "label": "pdfmd: extract tables",
      "type": "shell",
      "command": "pdfmd",
      "args": ["--extract-tables", "${file}"],
      "problemMatcher": []
    }
  ]
}
"""


def init_vscode_command(args) -> int:
    """`pdfmd --init-vscode`: a .vscode/tasks.json with pdfmd tasks, in the current folder; never overwrites one."""
    target = Path.cwd() / ".vscode" / "tasks.json"
    if target.exists():
        print(f"NOTE  {display_path(target)} exists; nothing was written. The tasks to add:\n{VSCODE_TASKS}")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, VSCODE_TASKS)
    print(f"WROTE  {display_path(target)}: tasks pdfmd: build, build and open, watch, extract tables "
          "(Terminal > Run Build Task). For commands, history and more, install the extension from the repository's vscode/ folder.")
    return 0


def editor_command(args) -> list[str] | None:
    """The external editor of `--editor CMD` (or `options.editor`), as a command; None for the built-in one."""
    value = args.editor if args.editor is not None else config_options().get("editor")
    if value is None or not str(value).strip():
        return None
    try:
        return split_command(str(value))
    except ValueError as error:
        raise SystemExit(f"--editor {value!r}: {error}")


def tree_stamp(folder: Path, ignore: set[Path]) -> dict[str, float]:
    """The modification times of the files under ``folder`` (what a watch compares), leaving ``ignore`` out."""
    stamp: dict[str, float] = {}
    for item in folder.rglob("*"):
        try:
            # a hidden file or folder (.backups, .cache) is what a build writes beside the source, not an edit
            if item.is_file() and item not in ignore and not any(part.startswith(".") for part in item.relative_to(folder).parts):
                stamp[str(item)] = item.stat().st_mtime_ns
        except (OSError, ValueError):
            pass
    return stamp


def deliver_edited_pdf(built: Path, pdf: Path) -> Path:
    """Put the rebuilt PDF in place of ``pdf``, keeping the old one in `.backups/` beside it; the new file is written
    beside it first and renamed over it, so a failure leaves the old PDF as it was. Returns the backup."""
    folder = pdf.parent / ".backups"
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / f"{pdf.stem}.{datetime.now().strftime('%Y%m%d-%H%M%S')}{pdf.suffix}"
    shutil.copy2(pdf, backup)
    staged = pdf.with_name(f".{pdf.name}.edit.tmp")
    shutil.copy2(built, staged)
    os.replace(staged, pdf)
    return backup


def edit_pdf_command(args, pdf: Path, passed: list[str]) -> int:
    """`pdfmd --edit FILE.pdf` (v3.28.23): a PDF that carries its source, edited and rebuilt in place. The source is
    restored into a temporary folder; the built-in editor (Ctrl-B builds there) or the `--editor CMD` you name (the
    folder is watched, and rebuilt on every save) works on it; when you leave, the PDF is replaced by the rebuilt one
    (the old one goes to `.backups/`), carrying the source again. The options of the original build are the ones the
    document and its metadata files record; the command-line ones are the ones you give now. A document is edited as the one
    file its source is (v3.28.40: the metadata, preamble, text files, bibliography and style inside it); a -r book as its chapters."""
    if pypdf is None:
        print("ERROR  --edit on a PDF needs pypdf (pip install pypdf).", file=sys.stderr)
        return 1
    pdf = pdf.resolve()
    try:
        attachments = read_pdf_attachments(pdf)
    except Exception as error:  # noqa: BLE001
        print(f"ERROR  {display_path(pdf)}: not readable as a PDF ({error})", file=sys.stderr)
        return 1
    if ATTACH_MANIFEST not in attachments:
        print(f"ERROR  {display_path(pdf)} carries no pdfmd source, so there is nothing to edit "
              "(pdfmd --check-source says which PDFs do; build with --attach-source)", file=sys.stderr)
        return 1
    external = editor_command(args)
    if external is None:
        try:
            import pdfmd_edit
        except ImportError:
            print("ERROR  --edit needs the pdfmd_edit package (a full install of pdfmd-cli).", file=sys.stderr)
            return 1
        if not pdfmd_edit.available():
            print("ERROR  --edit needs prompt_toolkit (pdfmd --install tui), or name an editor: --editor \"code --wait\"",
                  file=sys.stderr)
            return 1
    work = Path(tempfile.mkdtemp(prefix="pdfmd-edit-"))
    try:
        folder = work / "source"
        manifest = json.loads(attachments[ATTACH_MANIFEST].decode("utf-8"))
        single = manifest.get("mode") != "report"
        # one document: the source as the ONE file it is (metadata, preamble, text files, bibliography and style inside it);
        # a report is its chapters, edited as files (v3.28.40)
        if restore_from_pdf(pdf, folder, single=single) != 0:
            return 1
        if single:
            unknown = [block["name"] for block in parse_embedded_blocks(attachments[manifest.get("source", ATTACH_SOURCE)]
                                                                         .decode("utf-8"))
                       if block["type"] == "lua-filter" and block["sha256"] not in trusted_hashes()]
            if unknown and "--trust-embedded" not in passed:
                print(f"NOTE  the source embeds the Lua filter {', '.join(unknown)}, which this machine's pdfmd has not "
                      "written: a build skips it unless you add --trust-embedded (read it first)")
        chapters: list[Path] = []
        with restore_chain(manifest):
            main_where = restore_target_name(str(manifest.get("name") or ""))
            chapter_where = [restore_target_name(str(chunk.get("path") or "")) for chunk in manifest.get("chunks") or []]
        if manifest.get("mode") == "report":
            # a -r report is its chapters, in the order it was built: edit and rebuild them all as a report
            # (v3.28.31; before, the first chunk was built alone and replaced the whole book)
            for where in chapter_where:
                if where is not None and (folder / where).is_file():
                    chapters.append(folder / where)
            if not chapters:
                print("ERROR  the restored folder has none of the report's chapters.", file=sys.stderr)
                return 1
            document = chapters[0]
            made = work / pdf.name
        else:
            document = folder / (main_where or PurePosixPath(""))
            if not document.is_file():
                found = sorted(folder.rglob("*.md"))
                if not found:
                    print("ERROR  the restored folder has no Markdown file to edit.", file=sys.stderr)
                    return 1
                document = found[0]
            made = document.with_suffix(".pdf")
        edited = chapters or [document]
        state = {"built": None, "ok": False}

        def digest() -> str:
            return hashlib.sha256(b"\0".join(item.read_bytes() for item in edited)).hexdigest()

        original = digest()

        def build(path: Path):
            if single:
                put_outside_blocks(document, folder, manifest)
            command = ([sys.executable, str(Path(__file__).resolve()), *passed, "-r", *map(str, chapters),
                        "--attach-source", "--rewrite", "-o", str(made)] if chapters else
                       [sys.executable, str(Path(__file__).resolve()), *passed, "--attach-source", "--rewrite", str(path)])
            done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  cwd=path.parent)
            state["built"], state["ok"] = digest(), done.returncode == 0 and made.exists()
            return state["ok"], (done.stdout + done.stderr).strip(), made if state["ok"] else None

        if external is None:
            import pdfmd_edit
            if len(chapters) > 1:
                print(f"NOTE  a report of {len(chapters)} chapters: the built-in editor opens the first, "
                      f"{chapters[0].name}; --editor CMD opens them all ({', '.join(item.name for item in chapters[1:])})")
            pdfmd_edit.run(document, build=build, opener=open_file)
        else:
            print(f"EDIT      {shlex.join(external)} {' '.join(item.name for item in edited)}   (the folder is watched: "
                  "every save rebuilds; Ctrl+C, or quitting the editor, finishes)")
            process = subprocess.Popen([*external, *map(str, edited)])
            started = time.monotonic()
            seen = tree_stamp(folder, {made})
            try:
                while True:
                    time.sleep(WATCH_INTERVAL)
                    if process.poll() is not None and time.monotonic() - started > 3:
                        break                                    # the editor ended (one that hands over at once keeps us here)
                    if tree_stamp(folder, {made}) != seen:
                        ok, said, _ = build(document)
                        seen = tree_stamp(folder, {made})            # what the build itself wrote is not a new edit
                        print(f"{'BUILT' if ok else 'FAILED':<9} {made.name}" + ("" if ok else "\n" + said[-600:]))
            except KeyboardInterrupt:
                print()
        if digest() == original:
            print("No change: the PDF is as it was.")
            return 0
        if state["built"] != digest():
            ok, said, _ = build(document)                         # edited after the last build
            if not ok:
                print(f"ERROR  the last version does not build; {display_path(pdf)} is as it was.\n{said[-800:]}",
                      file=sys.stderr)
                return 1
        elif not state["ok"]:
            print(f"ERROR  the last build failed; {display_path(pdf)} is as it was.", file=sys.stderr)
            return 1
        lost = source_lost(attachments, made)
        if lost is not None and not lost.startswith("lost:"):
            print(f"ERROR  {lost}; {display_path(pdf)} is as it was.", file=sys.stderr)
            return 1
        if lost:
            print(f"WARN  the rebuilt PDF no longer carries {lost[5:].strip()} (nothing in the text points at "
                  f"{'it' if ',' not in lost else 'them'} now?)", file=sys.stderr)
        if sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get("PDFMD_NO_PROMPT"):
            try:
                answer = input(f"Replace {pdf.name} with the rebuilt one (the old one goes to .backups/)? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer in ("n", "no"):
                kept = pdf.with_name(f"{pdf.stem}.edited{pdf.suffix}")
                shutil.copy2(made, kept)
                print(f"SAVED     {kept.name}  ({pdf.name} was not changed)")
                return 0
        backup = deliver_edited_pdf(made, pdf)
        print(f"REPLACED  {pdf.name}  (rebuilt with its source; the old one: {display_path(backup)})")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def put_outside_blocks(document: Path, folder: Path, manifest: dict) -> list[str]:
    """For --edit of a single file: write the text files the source holds for folders above the document's
    (`../schemes/x.tex`) where the document reads them, in the edit's own folder, from what the file says now. A build reads
    them from there (a TeX search does not look above the working folder), so an edit of the block is the edit of the file."""
    try:
        text = document.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    written: list[str] = []
    with restore_chain(manifest):
        for block in parse_embedded_blocks(strip_location_markers(text)):
            if block["type"] != "file":
                continue
            data = block["bytes"] if block.get("bytes") is not None else block["source"].encode("utf-8")
            for place in [block["path"] or block["name"], *block.get("also", [])]:
                where = restore_target_name(place) if outside_folder(place) else None
                if where is None:
                    continue
                target = folder / where
                if not target.is_file() or target.read_bytes() != data:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_bytes(target, data)
                    written.append(place)
    return written


def source_carried(attachments: dict[str, bytes]) -> set[str]:
    """What a PDF's attached source carries, by name: its files (attachments and the text files held as blocks of its text)
    and the embedded data blocks (bibliography, style, filters, history)."""
    manifest = json.loads(attachments[ATTACH_MANIFEST].decode("utf-8"))
    names = {name[len(EXTRA_PREFIX):] for name in attachments if name.startswith(EXTRA_PREFIX)}
    names |= {item["path"] for item in manifest.get("extras") or [] if item.get("inline")}
    text = attachments.get(manifest.get("source", ATTACH_SOURCE), b"").decode("utf-8", errors="replace")
    names |= {block["path"] or block["name"] for block in parse_embedded_blocks(text) if block["type"] != "file"}
    return {name.replace("__up__", "..") for name in names}


def source_lost(before: dict[str, bytes], rebuilt: Path) -> str | None:
    """None when the rebuilt PDF carries its source and everything the old one carried; "lost: a, b" for what it no
    longer carries; else the reason it carries no source."""
    try:
        after = read_pdf_attachments(rebuilt)
    except Exception as error:  # noqa: BLE001
        return f"the rebuilt PDF cannot be read ({error})"
    if ATTACH_MANIFEST not in after or ATTACH_SOURCE not in after:
        return "the rebuilt PDF does not carry its source"
    lost = sorted(source_carried(before) - source_carried(after))
    return f"lost: {', '.join(lost[:6])}{' and %d more' % (len(lost) - 6) if len(lost) > 6 else ''}" if lost else None


def edit_command(args) -> int:
    """`pdfmd --edit [FILE]`: the small full-screen editor (pdfmd_edit), building with the options given beside it.
    With a PDF that carries its source, or with `--editor CMD`, see edit_pdf_command / the watch below."""
    given = {str(item) for item in args.path or []}
    passed = [item for item in sys.argv[1:] if item != "--edit" and item not in given]
    if args.editor is not None:
        passed = [item for index, item in enumerate(passed) if item != "--editor" and item != args.editor
                  and not item.startswith("--editor=")]
    if len(args.path or []) == 1 and args.path[0].suffix.lower() == ".pdf":
        return edit_pdf_command(args, args.path[0], passed)
    external = editor_command(args)
    try:
        import pdfmd_edit
    except ImportError:
        print("ERROR  --edit needs the pdfmd_edit package (a full install of pdfmd-cli).", file=sys.stderr)
        return 1
    if external is None and not pdfmd_edit.available():
        print("ERROR  --edit needs prompt_toolkit: run `pdfmd --install tui`.", file=sys.stderr)
        return 1
    if len(args.path or []) > 1:
        print("ERROR  --edit opens one file.", file=sys.stderr)
        return 1
    target = (args.path or [Path.cwd()])[0]
    try:
        document = find_markdown(target)
    except FileNotFoundError as error:
        if target.suffix.lower() in (".md", ".markdown") and not target.is_dir():
            document = target.resolve()                 # a new file, made when it is first saved
        else:
            print(f"ERROR  {error}", file=sys.stderr)
            return 1

    def build(path: Path):
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), *passed, "--rewrite", str(path)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=path.parent)
        made = path.with_suffix(".pdf")
        return done.returncode == 0, (done.stdout + done.stderr).strip(), made if done.returncode == 0 and made.exists() else None

    if external is not None:
        # an editor of your own on a Markdown file: pdfmd -w beside it (rebuild on every save) until it is closed
        process = subprocess.Popen([*external, str(document)])
        watcher = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *passed, "--watch", str(document)],
                                   cwd=document.parent)
        try:
            while True:
                time.sleep(WATCH_INTERVAL)
                if process.poll() is not None and watcher.poll() is None:
                    time.sleep(3)
                    if process.poll() is not None:
                        break
                if watcher.poll() is not None:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            watcher.terminate()
        return 0
    return pdfmd_edit.run(document, build=build, opener=open_file)


# history_view_command, history_act, history_interactive, init_backups_command and history_command: lib/pdfmd_history/backups.py (v3.33.28)


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


def part_digests(parts: list[Path], root: Path | None) -> list[tuple[str, str]]:
    """(name, digest) of each part of a document in parts: its path under the parts folder without `.md`, spaces as `_`
    (a .hst word has none), and the first 8 characters of the hash of its text -- what the history compares."""
    found: list[tuple[str, str]] = []
    for part in parts:
        try:
            label = str(part.relative_to(root)) if root else part.name
        except ValueError:
            label = part.name
        try:
            digest = sha256_text(normalized_source(part.read_text(encoding="utf-8-sig")))[:8]
        except (OSError, UnicodeDecodeError):
            digest = ""
        found.append((re.sub(r"\s+", "_", label.removesuffix(".md")), digest))
    return found


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
    local = [path for path in metadata_files if path != extra and path not in KIT_METADATA and not is_folder_metadata(path)]
    if len(local) > 1 and metadata_precedence() == "first":
        local.reverse()
    return [*([extra] if extra is not None else []), *supplied, *reversed(folders), *local]


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
PARTS_DIR_ALIASES = ("parts", "sections")
# Handed to Pandoc on a partial build, so a Lua filter that assumes the whole
# document (nulabreport's `moved` blocks need the Appendix) can degrade
# instead of failing: `pdfmd-partial` is true in the document's metadata.
PARTIAL_METADATA = ["-M", "pdfmd-partial=true"]
# PARTIAL_KEY: lib/pdfmd_assemble (v3.33.38)
# PARTS_SKIP_DIRS: lib/pdfmd_parts/__init__.py (v3.33.30)
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
    for metadata_file in metadata_files_by_priority(metadata_files):
        options = metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append(options if isinstance(options, dict) else {})
    sources.append(config_options(md_path))
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


# parts_directory: lib/pdfmd_parts/__init__.py (v3.33.30)


def natural_key(name: str) -> list:
    """Sort key where digit runs compare as numbers (2-x < 10-y)."""
    return [int(piece) if index % 2 else piece.casefold()
            for index, piece in enumerate(re.split(r"(\d+)", name))]


# collect_parts to select_parts_and_sections: lib/pdfmd_parts/__init__.py (v3.33.30)


# The sections of parts that a parts-mode build takes only a piece of (see
# ScaffoldPlan.cuts), consulted by scaffold_inputs() wherever it runs -- the cache
# route calls the build again, and this is what lets both see the same cuts.
PART_CUTS: dict[Path, list[Heading]] = {}

# A report built through convert_one() (pdfmd_report, v3.32.14): the files it is made of, what is done to each one's title
# (`chapters`: pdfmd_report.titles.Chapter), and the folder its attached source is named from. Set by the report for the
# length of the build; scaffold_inputs() reads the chapters, stamp_build() the files, convert_one() the folder.
REPORT_BUILD: dict = {}


# ScaffoldPlan, warn_shared_parts_folder: lib/pdfmd_parts/__init__.py (v3.33.30)


def split_section_requests(raw: list[str]) -> list[str]:
    """`a,b` and `a+b` both mean "a and b" (`pdfmd report#discussion+appendix`)."""
    return [piece.strip() for item in raw for piece in re.split(r"[,+]", item) if piece.strip()]


def scaffold_metadata_files(document: Path, requested: list[str] | None) -> list[Path]:
    if requested is None:
        requested = option_names(frontmatter_pdfmd_options(document), "yaml") or None
    try:
        found = find_metadata(document.parent.resolve(), requested, document_stem=document.stem, document=document)
    except (FileNotFoundError, ValueError):
        return []
    if found is None or found is AUTO_METADATA_DISABLED:
        return []
    return found if isinstance(found, list) else [found]


# plan_scaffold: lib/pdfmd_parts/__init__.py (v3.33.30)


LEADING_FRONT_MATTER_RE = re.compile(r"^---[ \t]*\r?\n(?P<yaml>.*?)\n(?:---|\.\.\.)[ \t]*\r?(?:\n|$)", re.DOTALL)


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


# PART_FENCE, wrap_part, wrap_runs: lib/pdfmd_parts/__init__.py (v3.33.30)


def select_filter_args(selection) -> list[str]:
    """``--lua-filter select.lua`` when the inputs are wrapped in part divs (see ``wrap_part``)."""
    if selection is None or selection is False:
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("select")
    return ["--lua-filter", str(shipped)] if shipped is not None else []


def chem_filter_args(sources: list[Path], metadata_files: list[Path], preamble_files: list[Path], writer: str,
                     office_filter: bool, no_auto: list[str] | None) -> list[str]:
    """``--lua-filter chem.lua`` (v3.28.10) for an output whose writer drops raw LaTeX and that the LaTeX filter does not
    run for (an HTML, EPUB, Markdown, text or .typ file, a PowerPoint deck), when a source has a \\ce, \\pu or siunitx
    command: they become text with sub- and superscripts, or converted math. Not for LaTeX, nor Word and OpenDocument
    (the LaTeX filter's own), nor with `office: {latex: off}`."""
    if (office_filter or writer in ("latex", "beamer", "context", "docx", "odt", "opendocument", "json", "native")
            or auto_disabled(no_auto, "officelatex")
            or str(office_options(sources[0], metadata_files, no_auto).get("latex", "")).casefold() in ("off", "false", "no")):
        return []
    if not any(MATH_ONLY_LATEX_RE.search(strip_code_text(split_front_matter(read_text_best_effort(source))[1]))
               for source in sources):
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("chem")
    if shipped is None:
        return []
    args = ["-M", f"pdfmd-chem-python={sys.executable}"]
    if preamble_files:
        args += ["-M", "pdfmd-chem-preamble=" + os.pathsep.join(str(item) for item in preamble_files)]
    return args + ["--lua-filter", str(shipped)]


def typst_filter_args(writer: str, command: list[str] | None = None, directory: Path | None = None) -> list[str]:
    """``--lua-filter typst.lua`` for Typst (v3.27.11): a link to an anchor the document does not have becomes its
    text with one WARN, where Typst would stop the build; with a Pandoc before 3.2, a picture's relative path is made
    absolute. Last, after citeproc and the document's own filters."""
    if writer != "typst":
        return []
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("typst")
    return typst_template_args(writer, command or [], directory) + ["--lua-filter", str(shipped)] if shipped is not None else []


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

# split_top_level_sections, slug_of and the section code (the banner `Rendering one section of an ordinary document`, ATX_HEADING_RE to scan_headings): lib/pdfmd_parts/__init__.py (v3.33.30)


DIV_FENCE_RE = re.compile(r" {0,3}(:{3,})(.*)$")
# ATTRIBUTE_ID_RE to plan_sections: lib/pdfmd_parts/__init__.py (v3.33.30)


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

CSL_FALLBACKS = ("default", "error")
CSL_FETCH_DAYS = 30
CA_BUNDLES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt")


def open_url(request, timeout: float):
    """urllib's urlopen, and once more with the system's CA bundle (else certifi's) when this Python has no certificates
    of its own: a python.org Python on macOS has none until its "Install Certificates" step runs, and every https fetch
    failed with CERTIFICATE_VERIFY_FAILED (v3.27.27; found fetching a csl: style)."""
    import ssl, urllib.error, urllib.request  # here, not at the top: only this needs it (start-up time, v3.32.55)
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as error:
        if not isinstance(getattr(error, "reason", None), ssl.SSLCertVerificationError):
            raise
        cafile = next((path for path in CA_BUNDLES if os.path.isfile(path)), None)
        if cafile is None:
            try:
                import certifi
                cafile = certifi.where()
            except ImportError:
                raise error from None
        return urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context(cafile=cafile))


def document_csl(sources: list[Path], metadata_files: list[Path]) -> str | None:
    """The `csl:` Pandoc takes from the files: the last source's front matter, else the winning metadata file's."""
    for source in reversed(sources):
        value = front_matter_dict(read_text_best_effort(Path(source))).get("csl")
        if isinstance(value, str) and value.strip():
            return value.strip()
    for path in metadata_files_by_priority(metadata_files):
        value = metadata_file_yaml(path).get("csl")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def csl_fallback(md_path: Path, metadata_files: list[Path]) -> str:
    """`pdfmd-options.csl-fallback`: default (Pandoc's default style, with a WARN) or error."""
    value = first_pdfmd_option(md_path, metadata_files, "csl-fallback")
    mode = str(value).strip().casefold() if value is not None else "default"
    if mode not in CSL_FALLBACKS:
        raise SystemExit(f"{md_path}: unknown csl-fallback value {value!r}. Valid: {', '.join(CSL_FALLBACKS)}")
    return mode


def fetch_csl(url: str) -> tuple[str | None, str]:
    """(the style's text, "") or (None, why)."""
    import urllib.error, urllib.request  # here, not at the top: only this needs it (start-up time, v3.32.55)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": f"pdfmd/{PDFMD_VERSION}"})
        with open_url(request, 20) as response:
            data = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        error.close()
        return None, f"{error.code} {error.reason}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        return None, str(getattr(error, "reason", error)) or type(error).__name__
    text = data.decode("utf-8", errors="replace")
    if "<style" not in text[:4000]:
        return None, "what it sent is not a CSL style"
    return text, ""


def remote_csl(url: str, md_path: Path, metadata_files: list[Path]) -> Path | None:
    """The local file for a `csl:` URL (see above); None leaves the URL to Pandoc."""
    name = Path(urllib.parse.urlparse(url).path).name or "style.csl"
    name = name if name.lower().endswith(".csl") else name + ".csl"
    folder = cache_root() / "csl"
    cached = folder / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}-{name}"
    if cached.is_file() and time.time() - cached.stat().st_mtime < CSL_FETCH_DAYS * 86400:
        return cached
    text, why = fetch_csl(url)
    if text is not None:
        folder.mkdir(parents=True, exist_ok=True)
        atomic_write_text(cached, text)
        print(f"AUTO CSL   {url} -> {display_path(cached)}")
        return cached
    if cached.is_file():
        when = time.strftime("%Y-%m-%d", time.localtime(cached.stat().st_mtime))
        print(f"NOTE  {display_path(md_path)}: {url} could not be fetched ({why}); using the copy fetched on {when}")
        return cached
    data_dir = pandoc_user_data_dir()
    own = next((place / name for place in ((data_dir / "csl", data_dir) if data_dir else ()) if (place / name).is_file()),
               None)
    if own is not None:
        print(f"WARN  {display_path(md_path)}: {url} could not be fetched ({why}); using Pandoc's own "
              f"{display_path(own)} instead", file=sys.stderr)
        return own
    if csl_fallback(md_path, metadata_files) == "error":
        raise SystemExit(f"{display_path(md_path)}: the citation style {url} could not be fetched ({why}), and Pandoc's "
                         f"csl/ folder has no {name} (pdfmd-options: {{csl-fallback: error}})")
    default = folder / "pandoc-default.csl"
    if not default.is_file():
        try:
            done = subprocess.run(["pandoc", "--print-default-data-file", "default.csl"], capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=60)
        except (OSError, subprocess.SubprocessError):
            done = None
        if done is None or done.returncode != 0 or "<style" not in done.stdout:
            return None
        folder.mkdir(parents=True, exist_ok=True)
        atomic_write_text(default, done.stdout)
    print(f"WARN  {display_path(md_path)}: {url} could not be fetched ({why}) and Pandoc's csl/ folder has no {name}; "
          "the citations use Pandoc's default style (Chicago author-date). pdfmd-options: {csl-fallback: error} stops "
          "instead", file=sys.stderr)
    return default


def csl_args(sources: list[Path], metadata_files: list[Path], pandoc_options: list[str],
             no_auto: list[str] | None) -> list[str]:
    """`--csl FILE` for a `csl:` URL in the front matter or a metadata file (see remote_csl); nothing for a local style,
    one the command line names (--csl, -M csl=...), or `--no-auto remotecsl`."""
    if auto_disabled(no_auto, "remotecsl"):
        return []
    for index, option in enumerate(pandoc_options):
        following = pandoc_options[index + 1] if index + 1 < len(pandoc_options) else ""
        if (option == "--csl" or option.startswith("--csl=")
                or (option in ("-M", "--metadata") and following.startswith(("csl=", "csl:")))
                or option.startswith(("-Mcsl=", "-Mcsl:", "--metadata=csl=", "--metadata=csl:"))):
            return []
    value = document_csl([Path(source) for source in sources], metadata_files)
    if not value or not value.lower().startswith(("http://", "https://")):
        return []
    local = remote_csl(value, Path(sources[0]), metadata_files)
    return ["--csl", str(local)] if local is not None else []


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
ASSEMBLED_FORMAT = "assembled"
ASSEMBLED_SUFFIX = ".assembled.md"
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


BIB_ENTRY_START_RE = re.compile(r"^[ \t]*@[ \t]*([A-Za-z]+)[ \t]*([{(])", re.MULTILINE)
# BIB_LINK_RE, BIB_SUFFIXES, PANDOC_CITE_RE and LATEX_CITE_RE: lib/pdfmd_assemble (v3.33.38)


def bib_entry_end(text: str, opener_index: int) -> int | None:
    """The index just past the entry whose opening `{` or `(` is at ``opener_index``, or None."""
    opener = text[opener_index]
    closer = "}" if opener == "{" else ")"
    depth = 0
    position = opener_index
    while position < len(text):
        char = text[position]
        if char == "\\":
            position += 2
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return position + 1
        position += 1
    return None


def parse_bibliography(text: str) -> tuple[list[dict], str]:
    """The entries of a BibTeX/BibLaTeX file -- {kind, key, text, gap} with ``gap`` the
    text between the previous entry and this one -- and the text after the last."""
    items: list[dict] = []
    position = previous = 0
    while True:
        match = BIB_ENTRY_START_RE.search(text, position)
        if match is None:
            break
        end = bib_entry_end(text, match.end() - 1)
        if end is None:
            position = match.end()
            continue
        kind = match.group(1).lower()
        key = (text[match.end():end - 1].split(",", 1)[0].strip() if kind not in ("string", "preamble", "comment")
               else None)
        start = text.index("@", match.start())
        items.append({"kind": kind, "key": key, "text": text[start:end], "gap": text[previous:start]})
        previous = position = end
    return items, text[previous:]


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


# Conventional file extension for a Pandoc writer/target format, used to name
# an output file when the caller didn't give one an explicit suffix. Formats
# missing here fall back to ".<format>" -- a reasonable guess, since Pandoc's
# own format names are usually also their file extension.
FORMAT_EXTENSION = {
    "pdf": ".pdf", "png": ".png", "svg": ".svg", "jpg": ".jpg", "tiff": ".tiff", "eps": ".eps", "ps": ".ps",
    "html": ".html", "html4": ".html", "html5": ".html", "chunkedhtml": ".html",
    "latex": ".tex", "beamer": ".tex", "context": ".tex",
    "typst": ".typ",
    "plain": ".txt", "txt": ".txt", "ansi": ".ansi",
    "markdown": ".md", "gfm": ".md", "gfm+raw": ".md", "commonmark": ".md", "commonmark_x": ".md",
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
# the targets only Calibre writes (v3.29.0; see calibre_goal): `-o book.azw3` names one
CALIBRE_ONLY_FORMATS = ("azw3", "mobi", "kepub", "lit", "lrf", "pdb", "rb", "snb", "tcr", "pmlz", "htmlz", "txtz")
EXTENSION_FORMAT = {
    ".html": "html", ".htm": "html",
    ".tex": "latex",
    ".typ": "typst",
    ".txt": "txt", ".ansi": "ansi",
    ".md": "markdown", ".markdown": "markdown",
    ".docx": "docx", ".odt": "odt", ".pptx": "pptx",
    ".epub": "epub", ".rst": "rst", ".org": "org", ".rtf": "rtf", ".adoc": "asciidoc",
    ".json": "json", ".pdf": "pdf", ".png": "png", ".svg": "svg", ".jpg": "jpg", ".jpeg": "jpg", ".tif": "tiff", ".tiff": "tiff", ".eps": "eps", ".ps": "ps",
    **{"." + name: name for name in CALIBRE_ONLY_FORMATS},
    ".doc": "doc",                                                    # LibreOffice writes it (v3.29.1; see soffice_goal)
}


# Two-part endings that name a target the plain suffix would not: `-o notes.gfm.md` is `--to gfm` (the name
# `output_extension_for` gives a flat Markdown made from a .md file), where `-o notes.md` alone is Pandoc's Markdown.
COMPOUND_EXTENSION_FORMAT = {".gfm.md": "gfm"}


def format_from_output(path: Path | None) -> str | None:
    """Recognize a target format from an explicit output filename's suffix. An `.ascii` before the ending
    (`notes.ascii.txt`, `notes.ascii.gfm.md`, `notes.ascii.rst`) asks for that format with no byte above 127: `ascii`
    for text, else `ascii:FORMAT`."""
    if path is None or not path.suffix:
        return None
    name = path.name.lower()
    parts = name.split(".")
    for index in range(1, len(parts) - 1):
        if parts[index] == "ascii":
            base = format_from_output(Path("x." + ".".join(parts[index + 1:])))
            if base is None or base == "ascii" or base.startswith("ascii:"):
                return None
            return "ascii" if base == "txt" else f"ascii:{base}"
    for ending in sorted(COMPOUND_EXTENSION_FORMAT, key=len, reverse=True):
        if name.endswith(ending) and len(name) > len(ending):
            return COMPOUND_EXTENSION_FORMAT[ending]
    return EXTENSION_FORMAT.get(path.suffix.lower())


def output_extension_for(target_format: str, source: Path | None = None) -> str:
    """The suffix an output gets by default. Flat Markdown (`gfm`, `gfm+raw`) made from a `.md` file is `.gfm.md`: beside
    its source, never over it."""
    if target_format in ("gfm", "gfm+raw") and source is not None and source.suffix.lower() == ".md":
        extension = ".gfm.md"
    else:
        extension = FORMAT_EXTENSION.get(target_format, f".{target_format}")
    if ASCII_CLI["on"] and target_format in ASCII_FORMATS:       # --to ascii: another name, so the Unicode file stays
        extension = ".ascii" + extension
    return extension


REWRITE_CLI: bool | None = None
REWRITE_NAME = "{stem} ({n}){ext}"


def rewrite_wanted(md_path: Path, metadata_files: list[Path]) -> bool:
    """--rewrite/--no-rewrite, else `pdfmd-options: {rewrite: ...}` (the document, its folder, the config), else on."""
    if REWRITE_CLI is not None:
        return REWRITE_CLI
    try:
        value = first_pdfmd_option(md_path, metadata_files, "rewrite")
    except Exception:
        return True
    return True if value is None else str(value).strip().casefold() not in ("false", "no", "off", "0")


def rewrite_template(md_path: Path, metadata_files: list[Path]) -> str:
    """`rewrite-name`: the numbered copy's name; it must have {n} and no folder, else the default with a WARN."""
    try:
        value = first_pdfmd_option(md_path, metadata_files, "rewrite-name", "rewrite_name")
    except Exception:
        value = None
    if value in (None, ""):
        return REWRITE_NAME
    template = str(value)
    if "{n}" not in template or re.search(r"[\\/]", template):
        print(f"WARN  rewrite-name '{template}' needs {{n}} and no folder; using {REWRITE_NAME}", file=sys.stderr)
        return REWRITE_NAME
    return template


def numbered_output(output: Path, template: str = REWRITE_NAME) -> Path:
    """``output`` when nothing is there, else the first free numbered name (`report (1).pdf`)."""
    if not output.exists():
        return output
    today = datetime.now().strftime("%Y%m%d")
    for number in range(1, 1000):
        name = (template.replace("{stem}", output.stem).replace("{ext}", output.suffix)
                .replace("{date}", today).replace("{n}", str(number)))
        candidate = output.with_name(name)
        if not candidate.exists():
            return candidate
    raise SystemExit(f"{display_path(output)} and the 999 numbered copies of it exist; remove some or name the output with -o")


def default_output_path(path: Path, target_format: str) -> Path:
    """Add the extension implied by target_format when the caller omitted one."""
    if path.suffix:
        return path
    return path.with_suffix(FORMAT_EXTENSION.get(target_format, f".{target_format}"))


# --bopen SPEC (v3.28.20): which of a batch's finished files are opened. A spec is a comma list of selectors, each with
# any whole number N from 1: fN the first N, lN the last N, flN the first half and the last half (the first gets the odd
# one: fl15 = 8 + 7), eN every Nth (the Nth, the 2Nth ...), all (or no spec). The files chosen by any selector open, once
# each, in the order the batch lists them.
BOPEN_RE = re.compile(r"^(?:(?P<all>all|a)|(?P<kind>fl|f|l|e|s)(?P<n>[0-9]+))$", re.IGNORECASE)
BOPEN_HELP = "all, fN (first N), lN (last N), flN (first half and last half), eN (the Nth, 2Nth ...), sN (the 1st, then every Nth: 1st, N+1th ...); joined by commas: f2,l3"


def parse_bopen(spec: str) -> list[tuple[str, int]]:
    """The selectors of a --bopen spec as (kind, N); kind is all, f, l, fl, e or s. Stops with the grammar when it is not one."""
    selectors: list[tuple[str, int]] = []
    for word in re.split(r"[,;]", re.sub(r"\s+", "", str(spec))):
        if not word:
            continue
        found = BOPEN_RE.match(word)
        if not found or (found.group("n") is not None and int(found.group("n")) < 1):
            raise SystemExit(f"--bopen {spec!r}: {word!r} is not a selector. A spec is {BOPEN_HELP}")
        selectors.append(("all", 0) if found.group("all") else (found.group("kind").lower(), int(found.group("n"))))
    if not selectors:
        raise SystemExit(f"--bopen {spec!r}: empty. A spec is {BOPEN_HELP}")
    return selectors


def bopen_indices(spec: str, count: int) -> list[int]:
    """The positions (0-based, in order) of ``count`` files that ``spec`` selects."""
    chosen: set[int] = set()
    for kind, number in parse_bopen(spec):
        if kind == "all":
            chosen.update(range(count))
        elif kind == "f":
            chosen.update(range(min(number, count)))
        elif kind == "l":
            chosen.update(range(max(0, count - number), count))
        elif kind == "fl":
            first = (number + 1) // 2
            chosen.update(range(min(first, count)))
            chosen.update(range(max(0, count - (number - first)), count))
        elif kind == "s":
            chosen.update(range(0, count, number))                    # Python's [::N]: the first, then every Nth
        else:
            chosen.update(range(number - 1, count, number))           # e: the Nth, the 2Nth ...
    return sorted(chosen)


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


TEX_PROBE_DOCUMENT = "\\documentclass{article}\\usepackage{fontspec}\\begin{document}x\\end{document}\n"
TEX_PROBES: dict[str, tuple[str, str] | None] = {}


def probe_tex_cause(engine: str, timeout: int = 120) -> tuple[str, str] | None:
    """Pandoc reports a LuaTeX run that cannot start its font loader only as `Fatal error occurred, no output PDF file
    produced`; the cause (an unwritable cache, a corrupt font database) is in the engine's own console. Run a one-line page
    with the same engine, in the same environment, and read that. Asked once per engine in a run; None when it cannot tell."""
    if engine not in TEX_PROBES:
        TEX_PROBES[engine] = None
        executable = which(engine) if engine == "lualatex" else None
        if executable:
            with tempfile.TemporaryDirectory(prefix="pdfmd-texprobe-") as scratch:
                folder = Path(scratch)
                (folder / "probe.tex").write_text(TEX_PROBE_DOCUMENT, encoding="utf-8")
                try:
                    done = subprocess.run([executable, "-interaction=nonstopmode", "-halt-on-error", "probe.tex"], cwd=folder,
                                          capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                                          stdin=subprocess.DEVNULL)
                    text = done.stdout + done.stderr
                except (OSError, subprocess.TimeoutExpired):
                    text = ""
                log = folder / "probe.log"
                if log.is_file():
                    text += "\n" + log.read_text(encoding="utf-8", errors="replace")
            TEX_PROBES[engine] = tex_failure_cause(text)
    return TEX_PROBES[engine]


SHOWN_LOCATIONS: set[tuple[str, str]] = set()
LATEX_CONTEXT_RE = re.compile(r"(?m)^l\.(\d+) (.+)$")


def source_line_for(text: str, context: str) -> int | None:
    """The line of ``text`` (a Markdown source) that ``context`` (the words LaTeX printed up to its error) came from.
    The generated LaTeX is wrapped and escaped differently, so the match is on the words with whitespace collapsed,
    first the whole context, then its last 30 characters, then the last command in it."""
    collapsed: list[str] = []
    starts: list[tuple[int, int]] = []
    size = 0
    for number, line in enumerate(text.splitlines(), 1):
        piece = re.sub(r"\s+", " ", line.strip())
        if piece:
            starts.append((size, number))
            collapsed.append(piece)
            size += len(piece) + 1
    haystack = " ".join(collapsed)
    context = re.sub(r"\s+", " ", context.strip())
    command = re.search(r"(\\[A-Za-z@]+)\s*$", context)
    for needle in (context, context[-30:], command.group(1) if command else ""):
        if len(needle) < 4:
            continue
        found = haystack.find(needle)
        if found >= 0:
            return [number for start, number in starts if start <= found][-1]
    return None


def latex_error_location(label: str, stderr: str) -> str | None:
    """`near line 9 of doc.md: Second has \\badmacro` for a LaTeX error whose context is in the Markdown ``label``
    names (Pandoc prints `l.67 Second has \\badmacro`, a line of the LaTeX it wrote, which nobody sees)."""
    path = Path(label)
    found = LATEX_CONTEXT_RE.search(stderr or "")
    if not found or path.suffix.lower() not in (".md", ".markdown") or not path.is_file():
        return None
    try:
        number = source_line_for(path.read_text(encoding="utf-8-sig"), found.group(2))
    except (OSError, UnicodeDecodeError):
        return None
    if number is None:
        return None
    return f"near line {number} of {display_path(path)}: {found.group(2).strip()[:100]}"


def report_engine_failure(label: str, engine: str, result: subprocess.CompletedProcess,
                          remaining: list[str], debug: bool, stopped: str | None = None) -> None:
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
    if stopped:                     # engine-fallback stops the chain here (lib/pdfmd_chain)
        print(f"WARN  {label}: {engine} failed{hint}; {stopped}", file=sys.stderr)
        where = latex_error_location(label, result.stderr)
        if where and (label, where) not in SHOWN_LOCATIONS:
            SHOWN_LOCATIONS.add((label, where))
            print(f"      {where}", file=sys.stderr)
    elif remaining:
        print(f"WARN  {label}: {engine} failed{hint}; trying {remaining[0]}...", file=sys.stderr)
        where = latex_error_location(label, result.stderr)
        if where and (label, where) not in SHOWN_LOCATIONS:       # the next LaTeX engine fails in the same place: once
            SHOWN_LOCATIONS.add((label, where))
            print(f"      {where}", file=sys.stderr)
    else:
        print(f"WARN  {label}: {engine} failed{hint}; no more engines to try. "
              f"Rerun with --engine {engine} --verbose (or --debug) for the full log.",
              file=sys.stderr)
        where = latex_error_location(label, result.stderr)
        if where and (label, where) not in SHOWN_LOCATIONS:
            SHOWN_LOCATIONS.add((label, where))
            print(f"      {where}", file=sys.stderr)
    known = tex_failure_cause(result.stderr)
    if known is None and engine == "lualatex" and "Fatal error occurred" in result.stderr:
        known = probe_tex_cause(engine)                                  # the cause is in the console, not in Pandoc's text
    if known and (label, known[0]) not in SHOWN_LOCATIONS:             # once per document, not once per engine
        SHOWN_LOCATIONS.add((label, known[0]))
        print(f"      cause: {known[0]}; {known[1]}", file=sys.stderr)
    if debug and result.stderr.strip():
        print(f"----- {label}: {engine} stderr (--debug) -----", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        print("-" * 40, file=sys.stderr)


# Direct .tex compilation (v3.1.0): the comment, its constants and the functions above tex_argument: lib/pdfmd_tex (v3.33.36)


def tex_argument(path) -> str:
    """A path as it goes on a TeX engine's command line. The engine reads that line as TeX, where `~` is an active
    character: on Windows, a temporary folder under its short name (`C:\\Users\\RUNNER~1\\AppData\\Local\\Temp`, what
    the CI runner and any long user name give) made MiKTeX's LuaLaTeX look for no file at all (`texput.log`). The long
    name has no `~`; elsewhere the path is unchanged."""
    return str(Path(path).resolve()) if os.name == "nt" else str(path)


# latex_engine_command and run_tex_engine: lib/pdfmd_tex (v3.33.36)


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


# -- A home that cannot be written (a sandbox, a read-only container) ------------------------------------------------------------
# pdfmd keeps a cache (cache_root()), LuaTeX keeps its font names in the TeX user tree (TEXMFVAR, under the home), Pandoc and the
# tools it starts may write in their working folder. When one of those places cannot be written the build goes on with a
# temporary folder in its place, removed when the run ends, and says so once (a NOTE): the first run in such a place is slower
# (the cache starts empty, LuaTeX indexes the fonts again), nothing else differs.
NOTED_PLACES: set[str] = set()


# TEMPORARY_PLACES, folder_is_writable and temporary_place: lib/pdfmd_cache/__init__.py (v3.33.33)


def note_place_once(key: str, message: str) -> None:
    if key not in NOTED_PLACES:
        NOTED_PLACES.add(key)
        print(f"NOTE  {message}", file=sys.stderr)


def tex_user_tree_writable() -> bool:
    """Whether LuaTeX and friends can keep their caches: TEXMFVAR if it is set, else a TeX user tree in the home
    (~/.texlive2023, ~/Library/texlive/2023) that exists and can be written, else the home itself."""
    if os.environ.get("TEXMFVAR"):
        return folder_is_writable(Path(os.environ["TEXMFVAR"].split(os.pathsep)[0]))
    try:
        home = Path.home()
    except RuntimeError:
        return False
    for pattern in (".texlive*/texmf-var", "Library/texlive/*/texmf-var"):
        if any(folder_is_writable(found) for found in home.glob(pattern)):
            return True
    return folder_is_writable(home)


def provide_writable_places() -> None:
    """Redirect what cannot be written to a temporary folder (see above); called once, at the start of main()."""
    cache = cache_root()
    redirected: list[str] = []
    if not folder_is_writable(cache):
        folder = temporary_place("cache")
        variable = "LOCALAPPDATA" if sys.platform == "win32" else "XDG_CACHE_HOME"
        os.environ[variable] = str(folder)               # cache_root() and the tools pdfmd starts (fontconfig, Typst ...) follow
        redirected.append(f"the cache folder {display_path(cache)}")
    if (not tex_user_tree_writable()
            and any(which(name) for name in ("lualatex", "xelatex", "pdflatex", "latexmk", "tectonic"))):
        folder = temporary_place("texmf")
        for name, variable in (("texmf-var", "TEXMFVAR"), ("texmf-config", "TEXMFCONFIG")):
            (folder / name).mkdir(parents=True, exist_ok=True)         # (an engine that does not make its own cache folder needs it there)
            os.environ[variable] = str(folder / name)
        redirected.append("the TeX user tree (font names, formats)")
    if redirected:
        note_place_once("places", f"{' and '.join(redirected)} cannot be written (a read-only home?): this run uses a temporary "
                                  "folder instead, removed when it ends; the first build is slower and nothing else differs")


def metadata_cwd(metadata_files: list[Path] | None, default: Path) -> Path:
    """The folder Pandoc (and so the TeX engine) runs in: that of the first metadata file placed FOR the document -- beside it, in
    its `metadata/` folder, or named with -y -- else ``default`` (the document's). A file a kit supplies, a folder's
    `.pdfmd/metadata.yaml` and the global metadata of `pdfmd --setup` belong to no document's folder: a relative path in raw
    LaTeX (a pgfplots table, `../ir/x.csv`) must stay relative to the document (v3.31.33). Their own folders go on the resource
    path instead (resource_path_option), so a `bibliography:` or `csl:` written beside them is still found."""
    for path in metadata_files or []:
        if path not in KIT_METADATA and not is_folder_metadata(path) and not is_global_metadata(path):
            return path.parent
    return default


def pandoc_working_directory(folder: Path) -> Path:
    """The folder Pandoc runs in: ``folder`` (the document's, so its relative paths resolve), or when that cannot be written
    a temporary one with the document's folder on --resource-path and TEXINPUTS (resource_path_option, tex_search_env)."""
    if folder_is_writable(folder):
        return folder
    note_place_once(f"cwd:{folder}", f"{display_path(folder)} cannot be written: Pandoc runs in a temporary folder, with "
                                     "the document's folder searched for what it names")
    return temporary_place("pandoc")


CACHE_LOCATIONS = ("global", "document")
# CACHE_LOCATION_NAMES: lib/pdfmd_cache/__init__.py (v3.33.33)
CACHE_LOCATION_CLI: str | None = None     # --cache-location (set in main)
CACHE_MANIFEST = ".pdfmd-source.json"
LOCAL_CACHE_DIRNAME = Path(".cache") / "pdfmd"


# cache_location and document_cache_root: lib/pdfmd_cache/__init__.py (v3.33.33)


def prepare_cache_root(root: Path) -> None:
    """Mark a cache folder as one: CACHEDIR.TAG (backup tools skip it) and, for a `.cache/pdfmd`
    beside a document, a .gitignore so the cache is not committed."""
    try:
        root.mkdir(parents=True, exist_ok=True)
        tag = root / "CACHEDIR.TAG"
        if not tag.exists():
            tag.write_text("Signature: 8a477f597d28d172789f06886806bc55\n"
                           "# This is a cache directory made by pdfmd (safe to delete).\n", encoding="utf-8")
        if root.parent.name == ".cache" and not (root.parent / ".gitignore").exists():
            (root.parent / ".gitignore").write_text("*\n", encoding="utf-8")
    except OSError:
        pass


# source_fingerprint: lib/pdfmd_cache/__init__.py (v3.33.33)


def write_cache_manifest(folder: Path, source: Path) -> None:
    """Record whose cache a folder is, so a moved document can find it again (see adopt_moved_cache)."""
    import json
    try:
        (folder / CACHE_MANIFEST).write_text(json.dumps({
            "path": str(source.resolve()), "stem": source.stem, "folder": source.resolve().parent.name,
            "sha256": source_fingerprint(source)}), encoding="utf-8")
    except OSError:
        pass


# adopt_moved_cache and cache_directory: lib/pdfmd_cache/__init__.py (v3.33.33)


def cache_settings(md_path: Path, metadata_files: list[Path], cli: bool | None) -> dict:
    """Effective ``pdfmd-options: {cache: {aux, plots}}``: the document's own
    front matter first, then each linked metadata file, then --cache/--no-cache
    (--cache turns aux on, --no-cache turns everything off)."""
    settings = dict(CACHE_DEFAULTS)
    chosen: set = set()
    sources = [frontmatter_pdfmd_options(md_path)]
    for metadata_file in metadata_files_by_priority(metadata_files):
        options = metadata_file_yaml(metadata_file).get("pdfmd-options")
        sources.append(options if isinstance(options, dict) else {})
    sources.append(config_options(md_path))
    for options in sources:
        if "cache" not in options:
            continue
        value = options["cache"]
        if isinstance(value, bool):
            value = {"aux": value}
        if isinstance(value, dict):
            for key in settings:
                if key in value and key not in chosen:      # the first place to set a field wins (v3.27.1)
                    chosen.add(key)
                    settings[key] = bool(value[key])
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
DRAFT_FLAGS = {"lualatex": "-draftmode", "pdflatex": "-draftmode", "xelatex": "-no-pdf"}   # a pass without output
# The draft pass only counts, so it does not draw (v3.27.23): a tikzpicture (pgfplots inside it too), \chemfig, a chemfig
# \schemestart...\schemestop and an image cost most of a nulabreport report's pass and step no counter (a figure's
# \caption is outside its picture). A picture is skipped up to its literal \end{tikzpicture}; the commands DRAFT_SKIP_COMMANDS
# (one argument after any optional ones) and the spans DRAFT_SKIP_SPANS (a start macro up to its stop macro) are dropped, and a
# package may add its own in `<package>-pdfmd.yaml` (`draft-skip:` with `commands:` and `spans:`). When that \end is hidden
# in a macro, the skip meets \end{<the environment around the picture>} or \end{document} first: it says so in the log,
# and build_label_scan runs the pass again with the pictures (draft_skip_problem). Needs LaTeX 2020-10 (\AddToHook).
DRAFT_SKIP_COMMANDS = ("chemfig",)
DRAFT_SKIP_SPANS = {"schemestart": "schemestop"}
DRAFT_SKIP_PICTURES = r"""% pdfmd: a pass that only counts the numbers, so the pictures are not drawn
\makeatletter
\ifdefined\AddToHook
\def\pdfmd@picenv{tikzpicture}\def\pdfmd@docenv{document}\let\pdfmd@outerenv\@empty
\AddToHook{env/tikzpicture/before}{\let\pdfmd@outerenv\@currenvir}
\long\def\pdfmd@skippic#1\end#2{\def\pdfmd@arg{#2}\let\pdfmd@next\pdfmd@skippic
  \ifx\pdfmd@arg\pdfmd@picenv\let\pdfmd@next\pdfmd@skippicdone\fi
  \ifx\pdfmd@arg\pdfmd@outerenv\let\pdfmd@next\pdfmd@skipfailed\fi
  \ifx\pdfmd@arg\pdfmd@docenv\let\pdfmd@next\pdfmd@skipfailed\fi
  \pdfmd@next}
\def\pdfmd@skippicdone{\end{tikzpicture}}
\def\pdfmd@skipfailed{\typeout{PDFMD-DRAFT-SKIP-FAILED}\end{tikzpicture}\expandafter\end\expandafter{\pdfmd@arg}}
\def\pdfmd@tikz{\ifx\@currenvir\pdfmd@picenv\let\endtikzpicture\relax\expandafter\pdfmd@skippic
  \else\let\endtikzpicture\pdfmd@endtikzpicture\expandafter\pdfmd@tikzpicture\fi}
\def\pdfmd@chemfig{\@ifstar\pdfmd@cf\pdfmd@cf}
\def\pdfmd@cf{\@ifnextchar[\pdfmd@cfopt\pdfmd@cfarg}
\def\pdfmd@cfopt[#1]{\@ifnextchar[\pdfmd@cfopt\pdfmd@cfarg}
\long\def\pdfmd@cfarg#1{}
@@SPANS@@\AtBeginDocument{%
  \@ifundefined{tikzpicture}{}{\let\pdfmd@tikzpicture\tikzpicture\let\pdfmd@endtikzpicture\endtikzpicture
    \let\tikzpicture\pdfmd@tikz}%
@@HOOKS@@  \@ifundefined{Gin@setfile}{}{\setkeys{Gin}{draft}}}
\fi
\makeatother
"""
PART_COUNTER_RE = re.compile(r"^\\pdfmd@part\{([^{}]*)\}\{([^{}]*)\}\s*$")
SEED_LABEL_RE = re.compile(r"^\\newlabel\{([^{}]*)\}(\{.*\})\s*$")


def package_draft_skips(md_path: Path, metadata_files: list[Path],
                        no_auto: list[str] | None = None) -> tuple[list[str], dict[str, str]]:
    """(commands, spans) the draft pass need not draw: DRAFT_SKIP_COMMANDS and DRAFT_SKIP_SPANS and what the packages the
    document loads add in their `<package>-pdfmd.yaml` (`draft-skip:`); names are letters only."""
    commands = list(DRAFT_SKIP_COMMANDS)
    spans = dict(DRAFT_SKIP_SPANS)
    for folder, package, _ in office_packages(md_path, metadata_files, None):
        helper = package_helper(folder, package, no_auto, md_path)
        wanted = helper[0].get("draft-skip") if helper else None
        if not isinstance(wanted, dict):
            continue
        for name in wanted.get("commands") or []:
            if isinstance(name, str) and re.fullmatch(r"[A-Za-z]+", name) and name not in commands:
                commands.append(name)
        for start, stop in (wanted.get("spans") or {}).items() if isinstance(wanted.get("spans"), dict) else ():
            if re.fullmatch(r"[A-Za-z]+", str(start)) and re.fullmatch(r"[A-Za-z]+", str(stop)):
                spans.setdefault(str(start), str(stop))
    return commands, spans


def draft_skip_text(commands, spans) -> str:
    """DRAFT_SKIP_PICTURES for these commands and spans."""
    definitions = "".join(f"\\long\\def\\pdfmd@span@{start}#1\\{stop}{{}}\n" for start, stop in spans.items())
    hooks = "".join(f"  \\@ifundefined{{{name}}}{{}}{{\\let\\{name}\\pdfmd@chemfig}}%\n" for name in commands)
    hooks += "".join(f"  \\@ifundefined{{{start}}}{{}}{{\\let\\{start}\\pdfmd@span@{start}}}%\n" for start in spans)
    return DRAFT_SKIP_PICTURES.replace("@@SPANS@@", definitions).replace("@@HOOKS@@", hooks)


def draft_skip_problem(log: Path, aux: Path, text: str) -> str | None:
    """Why a draft pass that skipped the pictures (DRAFT_SKIP_PICTURES) cannot be trusted, or None: a skip that met
    another environment's end first, a LaTeX error about the skip or a picture, or a label of the document's body that
    the pass did not define (the skip swallowed it). Ordinary errors of the document do not count: the pass with the
    pictures would have them too."""
    try:
        log_text = log.read_text(encoding="utf-8", errors="replace")
        aux_text = aux.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "it left no .aux"
    if "PDFMD-DRAFT-SKIP-FAILED" in log_text:
        return "a picture ends inside a macro"
    for block in re.findall(r"^!.*(?:\n.*){0,3}", log_text, re.MULTILINE):
        if "pdfmd@" in block or "tikzpicture" in block:
            return block.splitlines()[0].lstrip("! ").strip()
    defined = set(re.findall(r"^\\newlabel\{([^{}]*)\}", aux_text, re.MULTILINE))
    body = text[text.find("\\begin{document}"):]
    missing = sorted(set(re.findall(r"\\label\{([^{}]*)\}", body)) - defined)
    if missing:
        return f"{len(missing)} labels went missing ({missing[0]})"
    return None


def label_without_page(value: str) -> str:
    """A \\newlabel value with its page number left out (``??``): a pass that skipped the pictures has the right numbers
    but not the right pages. ``{{3}{12}{..}{..}{}}`` has the page second; so does cleveref's
    ``{{[table][3][]3}{[1][12][]12}{}{}{}}``, whose page group keeps its form (``[1][0][]??``) for \\cpageref."""
    groups, depth, start = [], 0, None
    inner = value[1:-1] if value.startswith("{") and value.endswith("}") else value
    for index, character in enumerate(inner):
        if character == "{":
            if depth == 0:
                start = index
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0 and start is not None:
                groups.append(inner[start:index + 1])
    if len(groups) < 2:
        return value
    groups[1] = "{[1][0][]??}" if groups[0].startswith("{[") else "{??}"
    return "{" + "".join(groups) + "}"


def seed_labels_file(full_aux: Path, target: Path, pages: bool = True) -> int:
    """Write ``target`` (a .tex fragment) that defines every label of the last
    full build's .aux that a partial build does not define itself, and, per
    part, the counter values at its start (\\pdfmd@st@key, run by
    \\pdfmdpart), so a part's own numbers continue from the full report's
    instead of restarting at 1. Returns the number of labels; 0 writes
    nothing. Defining only the undefined is what keeps a part's own labels
    authoritative. ``pages=False`` leaves the labels' page numbers out
    (``??``), for a draft pass that skipped the pictures.
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
            value = match.group(2) if pages else label_without_page(match.group(2))
            seeded.append(f"\\pdfmd@seed{{{match.group(1)}}}{value}")
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


# -- Which engine built the file, and --strict (v3.26.10) --------------------------------------------------------
# The closing line names the engine that made a PDF (`OK    report.md  (lualatex)`) and, when an earlier one was tried
# and failed, which (`(typst; lualatex failed)`): a build that quietly fell back used to look the same as one that did
# not. `--strict` (or `pdfmd-options: {strict: true}`) turns a build that printed any WARN line, or that Pandoc warned
# about, into a failed file (its output is kept; the exit code is 1), for scripts and CI.
STRICT_CLI: bool | None = None             # --strict / --no-strict (set in main)
ENGINE_CLI: str | None = None              # -e as given ("" a bare -e), for lib/pdfmd_chain's pinned engine (set in main)
ENGINE_FALLBACK_CLI: str | None = None     # --engine-fallback MODE (lib/pdfmd_chain; set in main)
BUILD: dict = {"engine": None, "failed": [], "output": None, "sources": [], "partial": None, "root": None, "timer": None, "record": None, "tried": [], "chain": None}     # what built the file convert_one is working on


def record_engine(engine: str, failed: list[str] | tuple[str, ...] = ()) -> None:
    """Note the engine that succeeded and the engines that were tried and failed before it."""
    BUILD["engine"], BUILD["failed"] = engine, [name for name in failed if name != engine]


class Built(tuple):
    """convert_one's `(path, ok, message)`, carrying the engine too (a tuple subclass: three-way unpacking and pickling
    through a process pool both keep working)."""

    def __new__(cls, items, engine: str | None = None, failed=(), output=None):
        self = super().__new__(cls, items)
        self.engine, self.failed, self.output = engine, list(failed), output
        self.seconds, self.time_text, self.time_style, self.steps = None, "", "auto", []     # see attach_time
        self.record_path = None                                                       # see BuildRecorder
        self.stopped = ""                                       # engine-fallback stopped the chain (lib/pdfmd_chain)
        return self


def engine_label(result) -> str:
    """`  (lualatex)` or `  (typst; lualatex failed)` for the closing line; nothing when no engine was involved."""
    engine = getattr(result, "engine", None)
    if not result[1] and getattr(result, "stopped", ""):
        return f"  ({result.stopped})"
    if not engine or not result[1]:
        return ""
    failed = getattr(result, "failed", [])
    return f"  ({engine}" + (f"; {', '.join(failed)} failed" if failed else "") + ")"


def ok_delimiter() -> str:
    """What stands between the source and the file in `OK    report.md > report.pdf` (`options.ok-delimiter`)."""
    value = config_options().get("ok-delimiter")
    return ">" if value is None or not str(value).strip() else str(value).strip()


def built_name(result) -> str:
    """` > report.pdf` for the closing line: the file a successful build wrote, by its name when it sits beside the
    source, else by its path; nothing when the build wrote no one file."""
    output = getattr(result, "output", None)
    if output is None or not result[1]:
        return ""
    try:
        beside = Path(output).parent.resolve() == Path(result[0]).parent.resolve()
    except OSError:
        beside = False
    return f" {ok_delimiter()} {Path(output).name if beside else display_path(Path(output))}"


WARNING_LINE_RE = re.compile(r"^\s*(?:WARN\b|\[WARNING\])")


class _WarningTee:
    """A text stream that passes everything on and remembers the lines that are warnings."""

    def __init__(self, stream, lines: list[str]):
        self._stream, self._lines, self._partial = stream, lines, ""

    def write(self, text):
        self._partial += text
        *complete, self._partial = self._partial.split("\n")
        self._lines.extend(line.strip() for line in complete if WARNING_LINE_RE.match(line))
        return self._stream.write(text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


@contextmanager
def warning_capture() -> Iterator[list[str]]:
    """Yield the list that fills with each WARN / [WARNING] line printed meanwhile (stdout and stderr)."""
    lines: list[str] = []
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _WarningTee(out, lines), _WarningTee(err, lines)
    try:
        yield lines
    finally:
        sys.stdout, sys.stderr = out, err


def resolve_strict(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether warnings fail ``md_path``'s build: --strict / --no-strict, else `pdfmd-options.strict`."""
    if STRICT_CLI is None and os.environ.get("PDFMD_STRICT") in ("0", "1"):
        return os.environ["PDFMD_STRICT"] == "1"       # a -j worker is a fresh process: main hands the flag down
    if STRICT_CLI is not None:
        return STRICT_CLI
    if md_path.suffix.lower() not in (".md", ".markdown"):
        return False
    return bool(option_flag(first_pdfmd_option(md_path, metadata_files, "strict")))


# -- Size budgets: --max-asset-mb, --max-output-mb (v3.26.18) -----------------------------------------------------
# A picture of 30 MB or a PDF that no mail server takes is found out late. With a budget set (the command line, else
# `pdfmd-options: {max-asset-mb: 5, max-output-mb: 20}`), a build says which image is over it before it starts and
# which file is over after it, as WARN lines (so --strict fails them); `--check` reports the images (asset-large).
# The command line reaches -j workers as PDFMD_MAX_ASSET_MB / PDFMD_MAX_OUTPUT_MB, as --strict does.

def resolve_budget(md_path: Path, metadata_files: list[Path]) -> tuple[float | None, float | None]:
    """(MB for one image or data file, MB for the output), None for no budget; 0 on the command line turns it off."""
    found = []
    for variable, key in (("PDFMD_MAX_ASSET_MB", "max-asset-mb"), ("PDFMD_MAX_OUTPUT_MB", "max-output-mb")):
        value = option_flag_number(os.environ.get(variable))
        if value is None and md_path.suffix.lower() in (".md", ".markdown"):
            value = option_flag_number(first_pdfmd_option(md_path, metadata_files, key))
        found.append(value if value and value > 0 else None)
    return found[0], found[1]


def size_text(size: int) -> str:
    return f"{size / 1048576:.1f} MB"


def check_asset_budget(sources: list[Path], md_path: Path, metadata_files: list[Path]) -> None:
    """WARN for each image the sources point at that is over the asset budget (before the build)."""
    limit, _ = resolve_budget(md_path, metadata_files)
    if limit is None or BUILD.get("scanning"):          # the label scan builds the same document again: say it once
        return
    seen: set[Path] = set()
    for source in sources:
        for image in referenced_images(read_text_best_effort(source), source.parent):
            if image in seen:
                continue
            seen.add(image)
            try:
                size = image.stat().st_size
            except OSError:
                continue
            if size > limit * 1048576:
                print(f"WARN  {display_path(md_path)}: {display_path(image)} is {size_text(size)}, over the "
                      f"{limit:g} MB asset budget (--max-asset-mb, pdfmd-options.max-asset-mb)", file=sys.stderr)


# -- A `$...$` that is not math: the closing `$` is followed by a digit (v3.32.48) ----------------------------------
# Pandoc reads `$...$` as math only when the closing `$` has no space before it and no digit after it (so that
# "costs $5 or $10" stays text). `$\geq$3` and `$\pm$10` are therefore text, with the dollars printed (the gfm
# reader) or the dollars printed and the command run in text mode (Pandoc's Markdown), and nothing says so; in
# a LaTeX build the text-mode `\geq` then lacks a glyph in the main font. The leftover is found in the AST
# the reader gave, where a failed `$...$` is plain Str / raw TeX and a real one is Math.
NONMATH_DOLLAR_RE = re.compile(r"(?<![\\$])\$(?=[^\s$])([^$]*?)(?<=\S)\$(?=\d)(\d+(?:[.,]\d+)?)")
# a text between two dollars that looks like math: a TeX command, a script or brace, or a single letter; "$5/$10" is no math
MATH_LOOKING_RE = re.compile(r"\\[A-Za-z]+|[\^_{}]|^[A-Za-z]$")
NONMATH_DOLLAR_READERS = ("markdown", "gfm", "commonmark_x")
# the source-text scan that decides whether Pandoc is asked at all: any `$` + text + `$` + digit (a span may run over lines; the
# AST has the last word, so this only has to find every candidate, and "costs $5 and $10" is none: a space comes before the 2nd $)
NONMATH_DOLLAR_CANDIDATE_RE = re.compile(r"(?<![\\$])\$(?=[^\s$])([^$]*)(?<=\S)\$\d")
_NONMATH_DOLLARS: dict[tuple, list[tuple[int, str, str]]] = {}


def inline_text_runs(document) -> Iterator[str]:
    """The text of each stretch of plain words and raw TeX in a Pandoc JSON document (math, code and any
    formatting end a stretch): where a `$...$` that Pandoc did not take for math is still to be seen."""
    stack = [document]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
            if not any(isinstance(item, dict) and item.get("t") in ("Str", "RawInline") for item in node):
                continue
            run: list[str] = []
            for item in node:
                kind = item.get("t") if isinstance(item, dict) else None
                content = item.get("c") if isinstance(item, dict) else None
                if kind == "Str" and isinstance(content, str):
                    run.append(content)
                elif kind in ("Space", "SoftBreak"):
                    run.append(" ")
                elif (kind == "RawInline" and isinstance(content, list) and len(content) == 2
                        and content[0] in ("tex", "latex")):
                    run.append(content[1])
                else:
                    if run:
                        yield "".join(run)
                    run = []
            if run:
                yield "".join(run)


def nonmath_dollars(md_path: Path, reader: str | None) -> list[tuple[int, str, str]]:
    """(line, the text as written, the way to write it) for each `$...$` of a Markdown file that Pandoc reads
    as text because the closing `$` is followed by a digit. Empty when Pandoc is not there or the reader has no
    dollar math; a `$` the author escaped, or a price, is not one."""
    base = (reader or "markdown").split("+")[0].split("-")[0]
    if base not in NONMATH_DOLLAR_READERS or "-tex_math_dollars" in (reader or ""):
        return []
    pandoc = which("pandoc")
    try:
        stat = md_path.stat()
        key = (str(md_path), stat.st_mtime_ns, stat.st_size, reader)
    except OSError:
        return []
    if key in _NONMATH_DOLLARS:
        return _NONMATH_DOLLARS[key]
    found: list[tuple[int, str, str]] = []
    if pandoc:
        try:
            raw = md_path.read_text(encoding="utf-8-sig")
            if not any(MATH_LOOKING_RE.search(candidate.group(1)) for candidate in NONMATH_DOLLAR_CANDIDATE_RE.finditer(strip_code_text(raw))):
                _NONMATH_DOLLARS[key] = found                   # nothing that could be one: no Pandoc pass for it
                return found
            text = EMBED_BLOCK_RE.sub("", obsidian_source(raw, md_path, show=False))
            done = subprocess.run([pandoc, "-f", reader or "markdown", "-t", "json"], input=text, capture_output=True,
                                  text=True, encoding="utf-8", timeout=120)
            if done.returncode == 0:
                seen: set[str] = set()
                prose = strip_code_text(raw)
                runs = list(inline_text_runs(json.loads(done.stdout)))
                for run in runs:
                    for match in NONMATH_DOLLAR_RE.finditer(run):
                        inner = match.group(1)
                        if not MATH_LOOKING_RE.search(inner) or match.group(0) in seen:
                            continue
                        seen.add(match.group(0))
                        # where it stands in the file, as written: a soft break is any white space, and an escaped `$` does not match
                        words = [re.escape(word) for word in match.group(0).split(" ")]
                        written = [position.start() for position in re.finditer(r"(?<!\\)" + r"\s+".join(words), prose)]
                        # the same text with a dollar escaped (`\$\geq\$3`) is the same text to the reader: when those copies account
                        # for every one it gave, the unescaped ones were read as math (Pandoc 3.1.3's gfm reader has no digit rule)
                        any_way = len(re.findall(r"\s+".join(word.replace(r"\$", r"\\?\$") for word in words), prose))
                        if sum(text.count(match.group(0)) for text in runs) <= any_way - len(written):
                            continue
                        for line in sorted({prose.count("\n", 0, start) + 1 for start in written}):
                            found.append((line, match.group(0), f"${inner} {match.group(2)}$"))
        except (OSError, ValueError, subprocess.SubprocessError, UnicodeDecodeError):
            found = []
    found.sort()
    _NONMATH_DOLLARS[key] = found
    return found


def check_nonmath_dollars(sources: list[Path], cli_from: str | None, metadata_files: list[Path], fixed_reader: bool) -> None:
    """WARN `file:line` for each `$...$` the sources write as math that Pandoc reads as text (before the build)."""
    if BUILD.get("scanning"):                           # the label scan builds the same document again: say it once
        return
    for source in sources:
        if source.suffix.lower() not in (".md", ".markdown"):
            continue
        reader = cli_from if fixed_reader else resolve_from_format(source, cli_from, metadata_files)[0]   # --no-auto reader: no pick of pdfmd's
        for line, written, instead in nonmath_dollars(source, reader):
            print(f"WARN  {display_path(source)}:{line}: `{written}` is not math (Pandoc needs the closing $ not "
                  f"followed by a digit); write {instead}", file=sys.stderr)


@timed("size budget")
def check_output_budget(output: Path | None, sources: list[Path], md_path: Path, metadata_files: list[Path]) -> None:
    """WARN when the output is over the output budget, with the largest images behind it."""
    _, limit = resolve_budget(md_path, metadata_files)
    if limit is None or output is None:
        return
    try:
        size = output.stat().st_size
    except OSError:
        return
    if size <= limit * 1048576:
        return
    images = {}
    for source in sources:
        for image in referenced_images(read_text_best_effort(source), source.parent):
            try:
                images[image] = image.stat().st_size
            except OSError:
                pass
    biggest = sorted(images.items(), key=lambda item: -item[1])[:3]
    behind = ("; the largest images: " + ", ".join(f"{display_path(path)} {size_text(value)}" for path, value in biggest)) \
        if biggest and biggest[0][1] > 1048576 else ""
    print(f"WARN  {display_path(md_path)}: {display_path(output)} is {size_text(size)}, over the {limit:g} MB output budget "
          f"(--max-output-mb, pdfmd-options.max-output-mb){behind}", file=sys.stderr)


def strict_message(lines: list[str]) -> str:
    unique = list(dict.fromkeys(lines))
    shown = "\n".join(f"  {line[:220]}" for line in unique[:5])
    more = f"\n  ... and {len(unique) - 5} more" if len(unique) > 5 else ""
    return (f"--strict: the build printed {len(unique)} warning{'s' if len(unique) != 1 else ''}, so it counts as "
            f"failed (the output was written):\n{shown}{more}")


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
REF_USE_RE = re.compile(r"\\(?:auto|eq|page|name|vpage|[cCvV])?ref\*?\s*\{|(?<![\w@])@(?:sec|fig|tbl|eq|lst):")


# pdfmd_labels_modes: lib/pdfmd_args (v3.33.40)


def seed_labels_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """auto (default) | aux | scan | draft | off, from --seed-labels, else `pdfmd-options.seed-labels`."""
    try:
        import pdfmd_labels
    except ImportError:
        return "off"
    value = SEED_LABELS_CLI
    if value is None:
        sources = [frontmatter_pdfmd_options(md_path)]
        for metadata_file in metadata_files_by_priority(metadata_files):
            options = metadata_file_yaml(metadata_file).get("pdfmd-options")
            sources.append(options if isinstance(options, dict) else {})
        sources.append(config_options(md_path))
        for options in sources:
            if "seed-labels" in options:
                value = options["seed-labels"]
                break
    if value is None:
        return "auto"
    mode = {True: "auto", False: "off"}.get(value) if isinstance(value, bool) else str(value).strip().lower()
    if mode not in pdfmd_labels.MODES:
        raise SystemExit(f"{md_path}: unknown seed-labels value {value!r}. Valid: {', '.join(pdfmd_labels.MODES)}")
    return mode


SEED_CALC_MODES = ("auto", "scan", "off")
SEED_CALC_CLI: str | None = None           # --seed-calc (set in main)


def seed_calc_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """auto (default, same as scan) | scan | off, from --seed-calc, else `pdfmd-options.seed-calc`."""
    value = SEED_CALC_CLI
    if value is None:
        value = first_pdfmd_option(md_path, metadata_files, "seed-calc")
    if value is None:
        return "auto"
    mode = {True: "auto", False: "off"}.get(value) if isinstance(value, bool) else str(value).strip().lower()
    if mode not in SEED_CALC_MODES:
        raise SystemExit(f"{display_path(md_path)}: unknown seed-calc value {value!r}. Valid: {', '.join(SEED_CALC_MODES)}")
    return mode


def parts_range_text(parts: list[Path]) -> str:
    """`parts 10-50` for the NOTE of a build that took names from them (their numeric prefixes, else their stems)."""
    if not parts:
        return ""
    if len(parts) == 1:
        number = parts[0].stem.split("-")[0]
        return f"part {number if number.isdigit() else parts[0].stem}"
    numbers = [part.stem.split("-")[0] for part in (parts[0], parts[-1])]
    return ("parts " + "-".join(numbers)) if all(number.isdigit() for number in numbers) \
        else f"parts {parts[0].stem} to {parts[-1].stem}"


@timed("calc seed")
def build_calc_seed(md_path: Path, metadata_files: list[Path], selected: list[Path], inputs: list[Path],
                    scratch: Path, from_format: str | None, verbose: bool) -> tuple[Path | None, int, Path | None, int]:
    """The names a part built alone needs from the rest of the document (v3.30.19 for the parts above it, v3.31.44 for the parts
    below it; `pdfmd-options: {seed-calc: auto|scan|off}`). Pandoc reads ``inputs`` (the whole document in order, with a
    `pdfmd-calc-mark-in` / `-out` paragraph around each part built, see ``calc_marked_inputs``) with only calc.lua, to nowhere;
    calc.lua writes, at full precision and with its digits, each name's last definition above the part and its first definition
    below it, each evaluated in its own place in the whole document, and the build reads the two files back: the first as
    definitions above the document, the second as definitions after it, so a name counts from there only when nothing above or
    inside the part defines it (the full build's rule: the nearest definition above, else the first below). Nothing is stored
    between builds, so nothing can be stale.
    (the names above and how many, the names below and how many); a file is None when it has no names or cannot be made: the
    build goes on without."""
    nothing = (None, 0, None, 0)
    arguments = calc_filter_args(selected, metadata_files)       # [] when calc is off or the part holds no span or div
    if not arguments:
        return nothing
    if not any(CALC_SPAN_RE.search(EMBED_BLOCK_RE.sub("", read_text_best_effort(file)))
               for file in inputs if not file.name.startswith("pdfmd-calc-mark-") and file not in selected[1:]):
        return nothing
    halves = scratch / "calc-halves.tsv"
    cmd = ["pandoc", *(str(file.resolve()) for file in inputs), *(["-f", from_format] if from_format else []),
           "-t", "native", "-o", str(scratch / "calc-names.native"), *arguments, "-V", "pdfmd-calc-halves=" + str(halves)]
    cwd = pandoc_working_directory(md_path.parent)
    log_cmd(cmd, cwd, verbose)
    started = time.time()
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    except OSError as error:
        vprint(verbose, f"CALC      the names of the parts left out could not be evaluated ({error})")
        return nothing
    if done.returncode != 0 or not halves.is_file():
        vprint(verbose, "CALC      the names of the parts left out could not be evaluated; the build goes on without them")
        return nothing
    lines = {"A": [], "B": []}
    for line in halves.read_text(encoding="utf-8", errors="replace").splitlines():
        kind, _, rest = line.partition("\t")
        if kind in lines and rest.strip():
            lines[kind].append(rest)
    files = []
    for kind, name in (("A", "calc-names.tsv"), ("B", "calc-names-below.tsv")):
        if lines[kind]:
            path = scratch / name
            path.write_text("\n".join(lines[kind]) + "\n", encoding="utf-8")
            files.append((path, len(lines[kind])))
        else:
            files.append((None, 0))
    vprint(verbose, f"CALC      {files[0][1]} names above and {files[1][1]} below the part evaluated in {time.time() - started:.1f} s")
    return files[0][0], files[0][1], files[1][0], files[1][1]


def calc_marked_inputs(scaffold: Path, parts: list[Path], built: list[Path], scratch: Path) -> list[Path]:
    """The whole document for the names-only pass of ``build_calc_seed``: the scaffold, then every part in order, a one-word
    paragraph before and after each part that is built (calc.lua notes where the built parts stand)."""
    mark_in, mark_out = scratch / "pdfmd-calc-mark-in.md", scratch / "pdfmd-calc-mark-out.md"
    mark_in.write_text("pdfmd-calc-mark-in\n", encoding="utf-8")
    mark_out.write_text("pdfmd-calc-mark-out\n", encoding="utf-8")
    inputs = [scaffold]
    for part in parts:
        inputs += [mark_in, part, mark_out] if part in built else [part]
    return inputs


class LabelScan:
    """The header files that make a partial build know the labels of the whole document (see above)."""

    def __init__(self, headers: list[Path], labels: int, steps: int, markers: bool, exact: bool = False,
                 skipped: int = 0):
        self.headers, self.labels, self.steps, self.skipped = headers, labels, steps, skipped
        self.exact = exact             # the numbers come from a LaTeX pass over the whole document (draft), not a count
        self.markers = markers         # whether the headers define \pdfmdpart (PARTS_MARKER_DEFS) too


def label_scan_wanted(mode: str, target_format: str, engines: list[str], presentation: bool, md_path: Path,
                      partial: bool, parts_mode: bool, texts: list[str]) -> bool:
    """Whether a build should take its missing labels from a scan: a partial build for a LaTeX engine; a part of a
    split document always (its numbers continue from the parts before it), a section of an ordinary document only when
    its text refers to something."""
    if mode not in ("auto", "scan", "draft") or not partial or presentation or md_path.suffix.lower() != ".md":
        return False
    if target_format != "pdf":                  # a .tex handed to the user stays the plain LaTeX of the part
        return False
    if not any(engine in LATEX_ENGINES and engine not in ("context", "latexmk", "tectonic")
                                          for engine in engines):
        return False
    return parts_mode or any(REF_USE_RE.search(text) for text in texts)


def select_wanted(mode: str, target_format: str, engines: list[str], presentation: bool, md_path: Path) -> bool:
    """Whether a partial build for a writer other than LaTeX numbers the whole document and keeps the part: HTML, Word,
    OpenDocument, Typst, EPUB, and PDF through an engine that is not LaTeX or a built-in renderer."""
    if mode not in ("auto", "scan", "draft") or presentation or md_path.suffix.lower() != ".md":
        return False
    if target_format in TEX_STANDALONE_FORMATS or target_format == ASSEMBLED_FORMAT:
        return False
    if target_format == "pdf":
        return not any(engine in LATEX_ENGINES or is_native_engine(engine) for engine in engines)
    return True


@timed("label scan")
def build_label_scan(md_path: Path, scratch: Path, font: str, engines: list[str], variables: list[str],
                     slide_level: int | None, pandoc_options: list[str], metadata_file, preamble_files,
                     from_format: str | None, no_auto: list[str] | None, stamp_overrides: dict,
                     trust_embedded: bool, all_parts: list[Path], parts_root: Path | None,
                     verbose: bool, draft: bool = False) -> "LabelScan | None":
    """Pandoc's LaTeX of the whole document, scanned (and, with ``draft``, run through the LaTeX engine once without
    output, whose .aux then gives the exact numbers). None when it cannot be made (the build goes on without)."""
    import pdfmd_labels
    started = time.time()
    tex_path = scratch / "labels-scan.tex"
    defs = scratch / "labels-defs.tex"
    markers = bool(all_parts and parts_root is not None)
    if markers:
        defs.write_text(PARTS_MARKER_DEFS, encoding="utf-8")
    draft_engine = next((engine for engine in engines if engine in DRAFT_FLAGS), None) if draft else None
    if draft and draft_engine is None:
        vprint(verbose, "LABELS    no engine here can run a draft pass (lualatex, xelatex, pdflatex); the scan alone is used")
    cheap = ["svg", "remoteimages", "pdfimages"]
    scan_no_auto = no_auto if (no_auto is not None and not no_auto) else [*(no_auto or []), *cheap]
    saved_build = dict(BUILD)
    saved_log = AUTO_LOG.snapshot()
    BUILD["scanning"] = True
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            built = _convert_one(md_path, None, False, font, engines, variables, slide_level, pandoc_options,
                                 metadata_file, tex_path,
                                 [*(preamble_files or []), *([defs] if markers and draft_engine else [])],
                                 target_format="latex",
                                 from_format=from_format, no_auto=scan_no_auto, verbose=False, debug=False,
                                 stamp_overrides=stamp_overrides, keep_aux=False, extra_inputs=list(all_parts) or None,
                                 partial=False, cache_cli=False, skip_stamp=True, parts_root=parts_root,
                                 part_markers=bool(all_parts and parts_root), trust_embedded=trust_embedded)
    except (SystemExit, Exception) as error:  # noqa: BLE001 -- the scan is a convenience; the build must not die of it
        vprint(verbose, f"LABELS    the whole-document scan failed ({error}); references to parts left out stay ??")
        return None
    finally:
        BUILD.clear()
        BUILD.update(saved_build)                  # what the scan recorded (its scratch .tex) is not the build's
        AUTO_LOG.restore(saved_log)                # its summary went to nowhere and must not take the build's FOUND items
    if not built[1] or not tex_path.is_file():
        vprint(verbose, "LABELS    the whole-document scan failed; references to parts left out stay ??")
        return None
    result = pdfmd_labels.scan(tex_path.read_text(encoding="utf-8", errors="replace"))
    if not result.labels and not result.parts():
        return None
    seed = scratch / "labels-seed.tex"
    seed.write_text(pdfmd_labels.render(result), encoding="utf-8")
    vprint(verbose, f"LABELS    scanned the whole document in {time.time() - started:.1f} s: {result.labels} labels, "
          f"{result.steps} numbered items, {result.parts()} parts"
          + (f"; {result.skipped} labels left out (after a caption in an environment it does not know)"
             if result.skipped else ""))
    headers = [seed]
    exact = False
    if draft_engine is not None:
        metadata_list = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
        pandoc_cwd = pandoc_working_directory(metadata_cwd(metadata_list, md_path.parent))
        began = time.time()
        command = [draft_engine, DRAFT_FLAGS[draft_engine], "-interaction=nonstopmode", "-output-directory",
                   tex_argument(scratch), tex_argument(tex_path)]
        whole = tex_path.read_text(encoding="utf-8", errors="replace")
        quick = not auto_disabled(no_auto, "draftpictures") and whole.count("\\begin{document}") == 1

        last_run: dict = {}

        def draft_pass(text: str) -> None:
            tex_path.write_text(text, encoding="utf-8")
            try:
                last_run["done"] = subprocess.run(command, cwd=pandoc_cwd,
                                                  env={**os.environ, **(tex_search_env(md_path.parent, pandoc_cwd, md_path) or {})},
                                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
            except (OSError, subprocess.SubprocessError) as error:
                vprint(verbose, f"LABELS    the draft pass could not run ({error}); the scan alone is used")

        if quick:
            draft_pass(whole.replace("\\begin{document}",
                                     draft_skip_text(*package_draft_skips(md_path, metadata_list, no_auto)) + "\\begin{document}"))
            problem = draft_skip_problem(scratch / "labels-scan.log", scratch / "labels-scan.aux", whole)
            if problem:
                vprint(verbose, f"LABELS    the draft pass without the pictures cannot be trusted ({problem}); "
                      "running it with them")
                quick = False
                draft_pass(whole)
        else:
            draft_pass(whole)
        aux_seed = scratch / "labels-aux-seed.tex"
        found = seed_labels_file(scratch / "labels-scan.aux", aux_seed, pages=not quick)
        if found:
            hook = scratch / "labels-aux-hook.tex"
            hook.write_text("\\AtBeginDocument{\\InputIfFileExists{\"%s\"}{}{}}\n" % aux_seed.as_posix(), encoding="utf-8")
            headers.insert(0, hook)
            exact = True
            vprint(verbose, f"LABELS    draft pass over the whole document{' (pictures not drawn, page numbers ??)' if quick else ''}: "
                  f"{found} labels in {time.time() - began:.1f} s")
        else:
            vprint(verbose, "LABELS    the draft pass left no .aux; the scan alone is used")
            done = last_run.get("done")
            if done is not None:
                tail = " | ".join(line.strip() for line in (done.stdout + done.stderr).splitlines()[-4:] if line.strip())
                vprint(verbose, f"LABELS    {draft_engine} exited {done.returncode}: {tail[:300]}")
    if markers:
        headers.insert(0, defs)
    return LabelScan(headers, result.labels, result.steps, markers, exact, result.skipped)


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
PLOT_CACHE_FORMAT = "2"
PLOT_REQUEST_SEP = "@@|@@"
# The protocol between pdfmd and a LaTeX package that caches its pictures (v3.28.34; nothing in pdfmd names a package).
# A package opts in by mentioning `pdfmdCacheDir` in its style file. Then:
#   * pdfmd writes `\def\pdfmdCacheDir{<folder>/}\def\pdfmdCacheVersion{3}` before the document; the package looks a picture up
#     by its own key as `<folder>/<key>.pdf` with its size in `<folder>/<key>.dim`, and on a miss typesets inline and
#     appends `<key>@@|@@<macro>@@|@@<arguments>@@|@@<context>` as a line to `<job>.pdfmdreq`;
#   * after the build pdfmd runs each request in a standalone job with the same preamble, `\pdfmdCacheRender` defined (no
#     lookup then): the context, then `\setbox0\hbox{<macro><arguments>}`, the page is that box; its size goes to the .dim
#     file as `\gdef\pdfmdCacheWd`, `Ht` and `Dp` (a macro name each, in points);
#   * the context may carry two markers: PLOT_CTX_PLAIN splits it into a part read under expl3's catcodes and a part read with
#     the ordinary ones (settings with spaces in their names); PLOT_CTX_TWICE asks for two runs (a picture whose arrows
#     point at its own nodes: TikZ's remember picture needs the second run).
# A package that began before the protocol had neutral names says its own in `<package>-pdfmd.yaml` beside its style file
# (`picture-cache:` with `dir`, `render`, `requests` (a file suffix) and `wd`, `ht`, `dp`: macro names): they are defined
# and read as well (v3.28.37; until then the first package's names were a table here), and the helper counts as the
# handshake too.
CACHE_HANDSHAKE = "pdfmdCacheDir"
CACHE_ALIAS_KEYS = ("dir", "render", "requests", "wd", "ht", "dp")
# PLOT_CTX_TWICE, PLOT_CTX_MARGIN and PLOT_CTX_PLAIN: lib/pdfmd_tex (v3.33.36)
PLOT_CACHE_KEEP_DIRS = 8     # per document: the whole report, a few parts, a package changed and changed back
CACHE_PLOTS_CLI: bool | None = None   # --cache-plots (set in main)


PACKAGE_LOAD_RE = re.compile(r"\\(?:usepackage|RequirePackage|documentclass)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")


def picture_cache_styles(preamble: str) -> list[tuple[str, str, dict[str, str]]]:
    """(name, text, aliases) of the style files the preamble loads that take part in the picture cache protocol (they
    mention CACHE_HANDSHAKE, or their package helper has a `picture-cache:` mapping, the aliases), found by reading the
    packages it names: no package is named here."""
    found: list[tuple[str, str, dict[str, str]]] = []
    for names in PACKAGE_LOAD_RE.findall(re.sub(r"(?m)(?<!\\)%.*$", "", preamble)):
        for name in (item.strip() for item in names.split(",")):
            if not name or name in {item[0] for item in found}:
                continue
            path = kpsewhich_path(name if name.endswith((".sty", ".cls")) else name + ".sty")
            text = read_text_or_none(path)
            if text is None:
                continue
            helper = package_helper(path.resolve().parent, path.stem)      # as office_packages: through a symlink
            wanted = helper[0].get("picture-cache") if helper else None
            aliases = {key: str(value) for key, value in wanted.items()
                       if key in CACHE_ALIAS_KEYS and re.fullmatch(r"\.?[A-Za-z@.]+", str(value))} \
                if isinstance(wanted, dict) else {}
            if CACHE_HANDSHAKE in text or aliases:
                found.append((name, text, aliases))
    return found


def cache_aliases(styles: list[tuple[str, str, dict[str, str]]]) -> dict[str, list[str]]:
    """{protocol name: the aliases the participating packages gave it}."""
    merged: dict[str, list[str]] = {key: [] for key in CACHE_ALIAS_KEYS}
    for _, _, aliases in styles:
        for key, value in aliases.items():
            if value not in merged[key]:
                merged[key].append(value)
    return merged


def kpsewhich_path(name: str) -> Path | None:
    kpsewhich = which("kpsewhich")
    if not kpsewhich:
        return None
    done = run_probe([kpsewhich, name])
    found = done.stdout.strip().splitlines() if done else []
    return Path(found[0]) if found else None


def read_text_or_none(path: Path | None) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path else None
    except OSError:
        return None


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


def sha1_file(path: Path) -> str | None:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return None


# tex_tree_stamp: lib/pdfmd_tex (v3.33.36)


@lru_cache(maxsize=None)
def user_tex_trees() -> tuple[Path, ...]:
    """The user's own TeX trees (TEXMFHOME, TEXMFLOCAL). A plot job reads files there that
    TeX Live's package database does not cover: nulabreport's vendored chemfig, its
    chemicals.tex."""
    kpsewhich = which("kpsewhich")
    if not kpsewhich:
        return ()
    trees: list[Path] = []
    for variable in ("TEXMFHOME", "TEXMFLOCAL"):
        done = run_probe([kpsewhich, "-var-value", variable])
        value = done.stdout if done else ""
        for item in re.split(r"[,;{}]", value.strip()):      # a {a,b} list, rarely
            item = item.strip().lstrip("!")
            if item and Path(item).expanduser().is_dir():
                tree = Path(os.path.abspath(Path(item).expanduser()))
                if tree not in trees:
                    trees.append(tree)
    return tuple(trees)


# plot_preamble: lib/pdfmd_tex (v3.33.36)


PLOT_KEY_TITLE_RE = re.compile(r"\\title\{|pdftitle=\{")


def plot_key_text(preamble: str) -> str:
    """The preamble as the plot directory's key reads it: without the title (`\\title{...}`,
    hyperref's `pdftitle={...}`) and with every run of white space one space. A part built
    alone has the same settings as the whole document but not its title: nulabreport's
    filter drops the title page of a part (`pdfmd-partial`), and Pandoc wraps the PDF
    title's line differently. Neither draws anything in a plot."""
    kept, position = [], 0
    for match in PLOT_KEY_TITLE_RE.finditer(preamble):
        if match.start() < position:
            continue
        kept.append(preamble[position:match.start()])
        depth, end = 1, match.end()
        while end < len(preamble) and depth:
            if preamble[end - 1] != "\\":
                depth += {"{": 1, "}": -1}.get(preamble[end], 0)
            end += 1
        position = end + 1 if preamble[end:end + 1] == "," else end
    kept.append(preamble[position:])
    return " ".join("".join(kept).split())


def plot_cache_directory(preamble: str, sty_text: str, engine: str, root: Path | None = None) -> Path:
    digest = hashlib.sha1("\0".join([PLOT_CACHE_FORMAT, plot_key_text(preamble), sty_text, engine_version_line(engine),
                                     tex_tree_stamp()]).encode("utf-8")).hexdigest()[:12]
    return (root or cache_root()) / f"plots-{digest}"


def prune_plot_directories(keep: Path) -> None:
    """Keep the newest few plot directories; an older environment (a package or
    preamble from before a change) is never read again."""
    others = sorted((d for d in keep.parent.glob("plots-*") if d.is_dir() and d != keep),
                    key=lambda d: d.stat().st_mtime, reverse=True)
    for stale in others[PLOT_CACHE_KEEP_DIRS - 1:]:
        shutil.rmtree(stale, ignore_errors=True)


def validate_plot_entries(plot_dir: Path, verbose: bool, roots: list[Path] | None = None) -> int:
    """Drop every entry whose recorded input files changed or vanished. Entries record the folders
    they were made in: when the document has moved, the inputs are looked for in the same places
    under the new folders (and the entry keeps working)."""
    import json
    dropped = 0
    current = [str(root) for root in roots] if roots else None
    digests: dict[str, str | None] = {}        # every entry lists the package's own files: hash each once

    def digest_of(name: str) -> str | None:
        if name not in digests:
            digests[name] = sha1_file(Path(name))
        return digests[name]

    for deps_file in plot_dir.glob("*.deps"):
        key = deps_file.stem
        try:
            deps = json.loads(deps_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            deps = None
        moved = False
        if isinstance(deps, dict):
            recorded = deps.pop("__roots__", None)
            if current and recorded and recorded != current:
                remapped = {}
                for name, digest in deps.items():
                    for old, new in zip(recorded, current):
                        if name.startswith(old + os.sep):
                            name = new + name[len(old):]
                            break
                    remapped[name] = digest
                deps, moved = remapped, True
        if deps is None or any(digest_of(name) != digest for name, digest in deps.items()):
            for suffix in (".deps", ".dim", ".pdf"):
                (plot_dir / f"{key}{suffix}").unlink(missing_ok=True)
            dropped += 1
            vprint(verbose, f"AUTO CACHE  plot {key[:8]}: an input changed; dropped")
        elif moved:
            try:
                deps_file.write_text(json.dumps({**deps, "__roots__": current}), encoding="utf-8")
            except OSError:
                pass
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
OFFICE_INPUT_EXTENSIONS = frozenset({
    ".docx", ".doc", ".odt", ".ott", ".rtf",
    ".pptx", ".ppt", ".odp",
    ".xlsx", ".xls", ".ods",
})


# run_soffice_convert, convert_office_direct and convert_via_soffice_bridge: lib/pdfmd_bridge/__init__.py (v3.33.26)


# "calibre" as a PDF engine (`-e calibre`, `pdf-engine: calibre`; never part of the automatic chain): Pandoc
# writes ONE standalone HTML file (MathML, pictures inlined) and Calibre's ebook-convert prints it. Not an EPUB:
# Pandoc splits an EPUB at every top-level heading (--split-level takes 1 to 6, no "never") and Calibre starts
# each of those files on a new page. Calibre draws MathML with its own MathJax. Its defaults suit e-books and
# are turned off for a document: font sizes rescaled to its output profile (text came out about twice the
# document's fontsize; without one, 15pt), 5pt of its own inside the page margins, a page break before every
# h1/h2 and before "Chapter"/"Section" headings, and PDF bookmarks made from the document's links; the
# bookmarks are its headings instead (the title left out).
CALIBRE_OPTIONS = ("--disable-font-rescaling", "--pdf-default-font-size", "16",   # 12pt, a browser's (WeasyPrint's)
                   "--margin-left", "0", "--margin-right", "0", "--margin-top", "0", "--margin-bottom", "0",
                   "--max-levels", "0", "--page-breaks-before", "/",
                   "--chapter", "/", "--chapter-mark", "none", "--max-toc-links", "0",
                   "--level1-toc", "//h:h1[not(contains(concat(' ', normalize-space(@class), ' '), ' title '))]",
                   "--level2-toc", "//h:h2", "--level3-toc", "//h:h3", "--pdf-page-numbers")
# Pandoc's HTML page is for a screen: a 36em column with 50px of padding (on paper the margins are the page's) and
# near-black text on an off-white page, which Calibre prints as a grey tint (it does not apply `@media print`)
CALIBRE_CSS = ("html { color-scheme: light; color: black; background-color: white; }\n"
               "body { max-width: none; margin: 0; padding: 0; background-color: transparent; }\n")
# PANDOC_TABLE_STYLE_RE, CALIBRE_TABLE_CSS, calibre_html_command, calibre_page_options and run_calibre: lib/pdfmd_bridge/__init__.py (v3.33.26)


# Calibre as a WRITER (v3.29.0). `pdfmd book.md -o book.azw3` (or `--to azw3`) makes the ebook Calibre makes from the
# document: Pandoc writes an EPUB 3 into a scratch folder (chapters, contents, metadata, the math as MathML), and
# ebook-convert turns that into the target. Twelve targets only Calibre writes; five more (epub, docx, rtf, txt, fb2) Pandoc
# writes itself, so they go through Calibre only when `-e calibre` is on the command line (a `pdf-engine: calibre` is a PDF
# setting). Every one was round-tripped through ebook-convert 9.14 to text (heading, words, list and table survive). Before
# v3.29.0 `-o book.azw3` wrote a PDF under that name. One document at a time: not `-b`, not `-r`.
CALIBRE_SHARED_FORMATS = ("epub", "docx", "rtf", "txt", "fb2")
CALIBRE_TARGET_ALIASES = {"plain": "txt", "epub2": "epub", "epub3": "epub"}
# What becomes of the math (v3.29.1). The EPUB Pandoc writes has MathML, which a Kindle or a Kobo does not draw and a
# MOBI, a Palm or an RTF file has no place for: a target with pictures gets each formula drawn by LaTeX as a picture (the
# route of a Word file, `latex: images`), the plain-text ones the formulas as text with a WARN; epub and htmlz keep MathML.
CALIBRE_MATH_PICTURES = ("azw3", "mobi", "kepub", "lit", "lrf", "docx")
CALIBRE_MATH_TEXT = ("pdb", "rb", "snb", "tcr", "pmlz", "txtz", "rtf", "txt", "fb2")
EBOOK_MATH: dict = {"mode": None}            # while a Calibre job runs: "images" (see office_reference) or "text" (+ goal, why)


def ebook_filter_args() -> list[str]:
    """`--lua-filter ebook.lua` for the EPUB of a Calibre job (pdfmd_lua/ebook.lua): the pictures' titles that name this
    machine's cache are dropped; in "text" mode each formula becomes text and a WARN says so once."""
    try:
        import pdfmd_lua
    except ImportError:
        pdfmd_lua_missing()
        return []
    shipped = pdfmd_lua.path("ebook")
    if shipped is None:
        return []
    args: list[str] = []
    if EBOOK_MATH.get("mode") == "text":
        args += ["-M", f"pdfmd-ebook={EBOOK_MATH.get('goal', 'the ebook')}", "-M", "pdfmd-ebook-math=text"]
        if EBOOK_MATH.get("why"):
            args += ["-M", f"pdfmd-ebook-why={EBOOK_MATH['why']}"]
    return args + ["--lua-filter", str(shipped)]


def math_pictures_possible() -> str | None:
    """None when LaTeX can draw formulas as pictures (a LaTeX engine and Poppler's pdftocairo), else why not."""
    module = office_module()
    if module is None:
        return "pdfmd_office is not installed"
    if not module.fragments.tools_available():
        return "drawing them needs pdftocairo (Poppler)"
    if not [engine for engine in installed_engines() if engine in ("lualatex", "xelatex", "pdflatex")]:
        return "there is no LaTeX engine (lualatex, xelatex or pdflatex)"
    return None


# LibreOffice as a writer (v3.29.1): `-o letter.doc` (Word 97, which Pandoc does not write) is made from the Word file Pandoc
# writes, by headless LibreOffice; rtf, txt and epub go the same way only with `-e soffice` first on the command line.
# OpenDocument's default Word route is selected per document in pdfmd_bridge/odt.py (DECISION 50).
SOFFICE_ONLY_FORMATS = ("doc",)
SOFFICE_SHARED_FORMATS = ("rtf", "odt", "txt", "epub")


def soffice_asked_first(requested: str | None) -> bool:
    """Whether the command line's `-e` puts LibreOffice first (`-e soffice`, `-e libreoffice`, `-e office,typst`)."""
    first = (requested or "").split(",")[0].strip().casefold()
    return bool(first) and ENGINE_ALIASES.get(first, first) == "soffice"


def soffice_goal(requested: str | None, target_format: str) -> str | None:
    """The format LibreOffice is to write for this target (`doc`, `rtf` ...), None when the build is not its. `doc` is always
    its; rtf, odt, txt and epub when `-e` names LibreOffice first; any other target with `-e soffice` is an error that names
    what it writes (PDF is the engine's own business)."""
    name = CALIBRE_TARGET_ALIASES.get(target_format.casefold(), target_format.casefold())
    if name in SOFFICE_ONLY_FORMATS:
        return name
    if target_format == "pdf" or not soffice_asked_first(requested):
        return None
    if name in SOFFICE_SHARED_FORMATS:
        return name
    raise SystemExit(f"-e soffice writes PDF, {', '.join(SOFFICE_SHARED_FORMATS)} and {', '.join(SOFFICE_ONLY_FORMATS)}, "
                     f"not {target_format}")


def calibre_asked_first(requested: str | None) -> bool:
    """Whether the command line's `-e` puts Calibre first (`-e calibre`, `-e ebook-convert,typst`)."""
    first = (requested or "").split(",")[0].strip().casefold()
    return bool(first) and ENGINE_ALIASES.get(first, first) == "calibre"


def calibre_goal(requested: str | None, target_format: str) -> str | None:
    """The format Calibre is to write for this target (`azw3`, `docx` ...), None when the build is not Calibre's. A target
    only Calibre writes is always its; one Pandoc writes too is Calibre's when `-e` names Calibre first; any other target
    with `-e calibre` is an error that names what Calibre writes."""
    name = CALIBRE_TARGET_ALIASES.get(target_format.casefold(), target_format.casefold())
    if name in CALIBRE_ONLY_FORMATS:
        return name
    if target_format == "pdf" or not calibre_asked_first(requested):
        return None
    if name in CALIBRE_SHARED_FORMATS:
        return name
    raise SystemExit(f"-e calibre writes PDF, {', '.join(CALIBRE_SHARED_FORMATS)} and {', '.join(CALIBRE_ONLY_FORMATS)}, "
                     f"not {target_format}")


def start_calibre_job(args, goal: str, target_format: str, pandoc_options: list[str] | None = None) -> dict:
    """What a Calibre target needs before the build: the checks, a scratch folder, and `args` pointed at the EPUB 3 that
    Pandoc writes there (the build then runs as for any EPUB). Returns the job for finish_calibre_job."""
    if args.batch or args.report or args.presentation:
        raise SystemExit(f"{goal} is made through Calibre one document at a time: not with "
                         f"{'-b' if args.batch else '-r' if args.report else '-p'} (yet)")
    if resolve_calibre() is None:
        raise SystemExit(f"{target_format} is written by Calibre's ebook-convert, which was not found (on PATH, in calibre.app "
                         "or in Calibre2 under Program Files). Install Calibre: `pdfmd --install calibre`, `brew install --cask calibre`, "
                         "`winget install calibre.calibre`, your package manager, or calibre-ebook.com.")
    if goal in CALIBRE_SHARED_FORMATS and goal != "epub":
        print(f"NOTE  -e calibre: {goal} is made by Calibre from an EPUB; without -e calibre Pandoc writes it from the "
              "document itself, with more of its own features (styles, tables, footnotes)", file=sys.stderr)
    scratch = Path(mkdtemp(prefix="pdfmd-calibre-target-"))
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    EBOOK_MATH.clear()
    EBOOK_MATH["mode"] = None
    if not any(item.startswith(HTML_MATH_OPTIONS) for item in pandoc_options or []):       # a math option of yours is kept
        why = math_pictures_possible() or "" if goal in CALIBRE_MATH_PICTURES else ""
        if goal in CALIBRE_MATH_PICTURES and not why:
            EBOOK_MATH["mode"] = "images"
        elif goal in CALIBRE_MATH_TEXT or why:
            EBOOK_MATH.update({"mode": "text", "goal": goal, "why": why})
        elif pandoc_options is not None:
            pandoc_options += html_math_args("mathml")       # kept as MathML (Pandoc 3.1 writes an EPUB's math as plain text)
    job = {"tool": "calibre", "goal": goal, "final": args.out, "scratch": scratch, "open": args.open}
    args.to, args.out, args.engine, args.open = "epub", scratch / "document.epub", None, False
    return job


# start_soffice_job: lib/pdfmd_bridge/__init__.py (v3.33.26)


def finish_convert_job(job: dict, results: list, verbose: bool) -> list:
    """The file: the converter (Calibre's ebook-convert of the EPUB, or LibreOffice of the Word file) run on what the build
    wrote, into the file asked for (named after the document beside it when `-o` gave none; a folder given gets that
    name in it). The result list for the closing line."""
    source, ok, error = results[0]
    if not ok:
        return results
    final = load_package("pdfmd_routing.output").job_target(job["final"], Path(source), job["goal"])
    tool = job.get("tool", "calibre")
    if tool == "soffice":
        worked, why = run_soffice_convert(job["scratch"] / job["intermediate"], final, verbose, job["goal"])
        if not worked:
            return [Built((source, False, f"soffice failed: {why}"), "soffice")]
    else:
        done = run_calibre_convert(job["scratch"] / "document.epub", final, verbose)
        if done.returncode != 0:
            return [Built((source, False, done.stderr), "calibre")]
    if job["open"]:
        open_file(final)
    return [Built((source, True, error), tool, output=final)]          # what Pandoc and its filters said stays


# run_calibre_convert, browser_page_css and run_browser_print: lib/pdfmd_bridge/__init__.py (v3.33.26)


# WeasyPrint's CSS parser names each property and media query it ignores. Pandoc's page style and KaTeX's stylesheet
# are written for browsers, so a good build printed a screenful of them (v3.28.11); --verbose still shows them.
WEASYPRINT_CSS_NOISE = re.compile(r"(?m)^WARNING: (?:Ignored `[^`\n]*` at \d+:\d+, (?:unknown property|invalid value)\."
                                  r"|Expected a media type, got .*|Invalid media type .* rule was ignored at \d+:\d+\.)"
                                  r"[ \t]*(?:\n|$)")


@timed(lambda args, kwargs: "pandoc + " + str(kwargs["engine"] if "engine" in kwargs else args[1]))
@noted(lambda args, kwargs: str(kwargs["engine"] if "engine" in kwargs else args[1]), engine=True)
def run_engine_command(cmd: list[str], engine: str, output: Path, run_pandoc, page_options,
                       verbose: bool) -> subprocess.CompletedProcess:
    """Run one engine's Pandoc command: `run_pandoc(command, target)` as it is, or for "calibre" into an HTML
    page that ebook-convert then prints (`page_options()` gives its paper, margins and language). Pandoc's own
    warnings are kept in the result; WeasyPrint's about the CSS it ignores only with --verbose."""
    with calibre_html_command(cmd, engine) as (command, html):
        result = run_pandoc(command, html or output)
        if engine == "weasyprint" and result.returncode == 0 and not verbose and result.stderr:
            result = subprocess.CompletedProcess(result.args, 0, result.stdout,
                                                 WEASYPRINT_CSS_NOISE.sub("", result.stderr))
        if html is None or result.returncode != 0:
            return result
        printed = (run_browser_print(html, output, engine, page_options(), verbose) if engine in BROWSER_ENGINES
                   else run_calibre(html, output, page_options(), verbose))
        return subprocess.CompletedProcess(printed.args, printed.returncode, result.stdout,
                                           (result.stderr or "") + printed.stderr)


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
    def note(kind: str, detail: str) -> None:
        vprint(verbose, f"AUTO {kind}  {detail}")

    nativebib_font = mainfont_choice([md_path], metadata_files, variables, font or None, document_font,
                                     mainfont_auto, no_auto, note)
    fd, tex_path_str = mkstemp(suffix=".tex", prefix=f"{md_path.stem}-pdfmd-nativebib-",
                               dir=md_path.parent)
    os.close(fd)
    tex_path = Path(tex_path_str)
    try:
        with prepared_latex_inputs([title_source, *pandoc_metadata_order(metadata_files)], True) as prepared, \
                document_header_file(md_path, bool(preamble_files) or has_embedded_preamble(md_path) or bool(pdf_meta_snippet_text),
                                         metadata_files, no_auto) as header_file, \
                pdf_metadata_header_file(pdf_meta_snippet_text) as pdf_meta_file, \
                script_fallback([md_path], metadata_files, variables, preamble_files, nativebib_font, None,
                                no_auto, note) as (fonts_header, fonts_filter):
            source, *prepared_metadata = prepared
            cmd = ["pandoc", str(source), "-o", str(tex_path), "-t", "beamer" if presentation else "latex",
                  "--standalone"]
            if effective_from:
                cmd += ["-f", effective_from]
            for metadata in prepared_metadata:
                cmd += ["--metadata-file", str(metadata)]
            pandoc_cwd = pandoc_working_directory(metadata_cwd(metadata_files, md_path.parent))
            cmd += resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
            if presentation and slide_level is not None:
                cmd += ["--slide-level=" + str(slide_level)]
            first_font = nativebib_font
            if first_font:
                cmd += font_args("mainfont", first_font)
                cmd += mathfont_args(first_font, md_path, metadata_files, variables, font or None, no_auto, None, note)
            else:
                cmd += document_font_args([md_path], metadata_files, variables)
            if geometry_needed:
                cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
            if monofont_needed:
                cmd += font_args("monofont", default_monofont())
            for variable in paper_variables(md_path, metadata_files, variables, None, paper_kind("tex", no_auto))[0]:
                cmd += ["-V", variable]
            if shift_heading:
                cmd += ["--shift-heading-level-by=-1"]
            cmd += pandoc_options
            cmd += paragraph_spacing_latex_args(md_path, metadata_files)
            if preamble_files:
                for preamble_file in preamble_files:
                    cmd += ["--include-in-header", str(preamble_file)]
            if pdf_meta_file is not None:
                cmd += ["--include-in-header", str(pdf_meta_file)]
            if fonts_header is not None:
                cmd += ["--include-in-header", str(fonts_header)]
            # Last, so a document's own header-includes can override anything
            # the shared preamble/pdf-meta files above defined (Pandoc would
            # otherwise drop it entirely; see document_header_file). Added
            # whenever header_file exists, not only when preamble_files is
            # non-empty -- pdf_meta_file alone is enough to trigger the drop
            # this guards against (see document_header_includes()'s own
            # docstring for the 2026-09-20 fix this is part of).
            if header_file is not None:
                cmd += ["--include-in-header", str(header_file)]
            cmd += document_filter_args(md_path, md_path, metadata_files, no_auto, csv_filter, pandoc_options)
            if "--natbib" not in pandoc_options and "--biblatex" not in pandoc_options:
                cmd.append(f"--{citation_engine}")
            if fonts_filter is not None:
                cmd += ["--lua-filter", str(fonts_filter)]
            if tablewidth_auto:
                cmd += width_filter_args(width_filter)
            cmd += cellalign_args(md_path, metadata_files)
            cmd += tblr_header_args(md_path, metadata_files)
            cmd += code_filter_args(no_auto, [md_path, title_source], metadata_files) + image_filter_args(no_auto, [md_path, title_source])
            hoist_code_header(cmd)
            cmd += markup_header_args(md_path, metadata_files, cmd)
            keep_header_includes(cmd, [md_path], metadata_files, pandoc_options, header_file)
            for lua_filter in lua_filters:
                cmd += ["--lua-filter", str(lua_filter)]
            cmd = headers_as_metadata(cmd)
            log_cmd(cmd, pandoc_cwd, verbose)
            result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=pandoc_cwd)
        if result.returncode != 0 or not tex_path.exists():
            return False, result.stderr.strip() or "pandoc failed to produce an intermediate .tex"
        where = f"kept at {tex_path} (--keep-aux)" if keep_aux else "discarded after compiling"
        vprint(verbose, f"AUTO CITATIONENGINE  {md_path}: routing bibliography through --{citation_engine} "
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
        if kwargs.get("target_format") == "odt":
            return deferred("pdfmd_bridge.odt", "convert")(_convert_one_core, md_path, *args, **kwargs)
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
                source_override: tuple[str, bool] | None = None,
                label_scan: "LabelScan | None" = None,
                selection: "set[Path] | bool | None" = None) -> tuple[Path, bool, str]:
    # selection: the inputs are ALL the parts (a set: those to keep) or the whole document (True), each wrapped in a part
    # div, and select.lua drops the rest after pandoc-crossref has numbered everything (see wrap_part).
    # label_scan: the headers that replay the whole document's labels (see build_label_scan).
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
    if partial:      # for the history (stamp_build): which parts this build is made of, or the text of the sections
        chosen = ([item for item in parts_inputs if item in selection]
                  if isinstance(selection, (set, frozenset)) and parts_inputs else parts_inputs)
        BUILD["partial"] = {"parts": [Path(item) for item in chosen], "root": parts_root,
                            "cut": source_override[0] if source_override is not None else None}
    noted: set[tuple[str, str]] = set()

    def note(kind: str, detail: str) -> None:
        if (kind, detail) in noted:          # the same decision, made again for the next engine
            return
        noted.add((kind, detail))
        AUTO_LOG.record(kind, detail, verbose)

    # the style sheets of the document (v3.28.41): linked for an HTML-family build, read for settings with css-scope: all
    css_meta = [metadata_file] if isinstance(metadata_file, Path) else list(metadata_file or [])
    for layer_path, _ in folder_layer_files(str(md_path.resolve().parent)):        # the folder settings in force (v3.29.10)
        AUTO_LOG.record_file("SETTINGS", Path(layer_path), verbose)
    html_family = (target_format in HTML_TARGETS or target_format.startswith("epub")
                   or (target_format == "pdf" and any(item in ENGINE_GROUPS["html"] or item == "calibre" or item in BROWSER_ENGINES for item in engines)))
    css_options, css_variables = css_additions(md_path, css_meta, variables, no_auto, html_family, note)
    if css_options or css_variables:
        pandoc_options = [*pandoc_options, *css_options]
        variables = [*variables, *css_variables]

    def flush_summary() -> None:
        tablewidth_note(md_path, note)
        if not verbose:
            AUTO_LOG.flush()

    metadata_files = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
    cli_no_auto = no_auto
    no_auto = effective_no_auto(md_path, no_auto)
    kit_kinds = kit_no_auto_kinds(md_path, metadata_files, no_auto)
    if kit_kinds:
        no_auto = effective_no_auto(md_path, cli_no_auto, kit_kinds)
    output_extension = output_extension_for(target_format, md_path)
    output = output_file or (
        (out_dir / f"{md_path.stem}{output_extension}") if out_dir else md_path.with_suffix(output_extension)
    )
    BUILD["output"], BUILD["sources"] = output, [md_path, *parts_inputs]
    if parts_inputs:
        BUILD["root"] = parts_root
    if md_path.suffix.lower() in MARKDOWN_LIKE_SUFFIXES:
        check_asset_budget(BUILD["sources"], md_path, metadata_files)
        check_nonmath_dollars(BUILD["sources"], from_format, metadata_files, auto_disabled(no_auto, "reader"))
    for source_file in (md_path, *parts_inputs):
        try:
            clash = output.exists() and source_file.exists() and output.samefile(source_file)
        except OSError:
            clash = False
        if clash:
            raise SystemExit(f"{display_path(output)} is the source itself; the {target_format} output would replace it. "
                             "Give another name with -o, or another folder.")
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
        plan = make_embed_plan(md_path, metadata_files, preamble_files, no_auto, embed)
        ok, reason = write_assembled_markdown([md_path, *parts_inputs], output, bool(parts_inputs), plan, partial,
                                              resolve_strip_comments(md_path, metadata_files))
        flush_summary()
        return md_path, ok, reason

    if (target_format == "pdf" and engines and md_path.suffix.lower() not in OFFICE_INPUT_EXTENSIONS
            and not all(is_native_engine(engine) for engine in engines)):
        engines = chain_plan_build(md_path, metadata_files, engines, output, verbose)     # engine-fallback (v3.33.71)
    native_engines = [engine for engine in engines if is_native_engine(engine)]
    if target_format == "pdf" and native_engines:
        # The native tier (see the section after dependency_report()): no
        # Pandoc, no engine, none of the discovery below applies to it.
        native_source, temporaries = md_path, []
        if parts_inputs or source_override is not None:
            # The renderers read one Markdown file: the parts are joined after the document and a section is
            # the document cut down to it, the same text Pandoc would be given (see assemble_markdown_text)
            first = md_path
            if source_override is not None:
                with NamedTemporaryFile("w", encoding="utf-8", suffix=md_path.suffix, prefix=f".{md_path.stem}.pdfmd-section-",
                                        dir=md_path.parent, delete=False) as handle:
                    handle.write(source_override[0])
                first = Path(handle.name)
                temporaries.append(first)
            with scaffold_inputs([first, *parts_inputs], bool(parts_inputs)) as scaffold_files, \
                    NamedTemporaryFile("w", encoding="utf-8", suffix=md_path.suffix, prefix=f".{md_path.stem}.pdfmd-native-",
                                       dir=md_path.parent, delete=False) as handle:
                handle.write(assemble_markdown_text(scaffold_files, False, None, partial, False))
            native_source = Path(handle.name)
            temporaries.append(native_source)
            if parts_inputs:
                note("PARTS", f"{md_path}: {len(parts_inputs)} part{'s' if len(parts_inputs) != 1 else ''} "
                              f"joined after it" + (" (partial build)" if partial else ""))
        try:
            ok, reason = convert_native(native_source, output, native_engines, metadata_files, from_format, verbose, debug)
        finally:
            for temporary in temporaries:
                temporary.unlink(missing_ok=True)
        if ok:
            stamp_build(partial, skip_stamp, md_path, metadata_files, preamble_files or [],
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
        if ok or not which("pandoc") or chain_stopped():
            flush_summary()
            return md_path, ok, reason[-3000:]
        # No LaTeX engine got it through (or none is installed): Pandoc can still read the file and any engine can
        # draw what it reads -- less faithful than the source, so said out loud, and the LaTeX message stays above.
        print(f"WARN  {display_path(md_path)}: direct compilation failed ({reason.strip().splitlines()[-1][:160] if reason.strip() else 'no reason given'}); "
              "trying it through Pandoc, which rewrites the LaTeX and may change its look", file=sys.stderr)

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
        if ok:
            record_engine("soffice")
        flush_summary()
        return md_path, ok, reason[-3000:]

    if target_format == "ansi" and not which("pandoc") and not parts_inputs:
        ok, reason = ansi_without_pandoc(md_path, output)        # the built-in parser stands in (v3.30.3)
        flush_summary()
        return md_path, ok, reason[-3000:]
    if not which("pandoc"):
        raise SystemExit(PANDOC_MISSING)
    warn_old_pandoc()

    effective_from, reader_reason = (
        (from_format, None) if auto_disabled(no_auto, "reader")
        else resolve_from_format(md_path, from_format, metadata_files)
    )
    if reader_reason:
        note("READER", reader_reason)
    lua_filters = [] if discovery_disabled(no_auto, "lua") else find_lua_filters(md_path, metadata_files, no_auto)
    if not auto_disabled(no_auto, "lua"):
        for extra_filter in frontmatter_extra_lua_filters(md_path, metadata_files):
            if extra_filter not in lua_filters:
                lua_filters.append(extra_filter)
    lua_filters = check_lua_filters(md_path, lua_filters, resolve_strict(md_path, metadata_files))
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
                                     trust_embedded=trust_embedded, source_override=source_override,
                                     label_scan=label_scan)
    if label_scan is not None:
        # the ordinary route: the replay goes in with the other LaTeX headers (the engine loop passes them to the LaTeX engines only)
        preamble_files = [*(preamble_files or []), *label_scan.headers]
        part_markers = part_markers or bool(parts_inputs and label_scan.markers)

    ascii_on = ASCII_CLI["on"] and target_format in ASCII_FORMATS     # --to ascii: no character above 127
    flat_markdown = target_format == "gfm"             # flat Markdown: pictures beside the output, relative links, one line a paragraph
    flat_target = flat_markdown or target_format == "txt"        # and flat text, which shares the pipeline (not those extras)
    flat = flat_settings(md_path, metadata_files, target_format) if flat_target else None
    with prepared_title_source(md_path, metadata_files, disabled=auto_disabled(no_auto, "title") or flat_target or target_format == "ansi",
                               override=source_override) \
            as (title_source, title_shifted), \
            embedded_lua_filters(md_path, not auto_disabled(cli_no_auto, "lua"), trust_embedded) \
            as embedded_filters, \
            table_width_filter() as width_filter, \
            csv_table_filter() as csv_filter, \
            scaffold_inputs([md_path, *parts_inputs], bool(parts_inputs),
                            {part: part_key(part, parts_root) for part in parts_inputs}
                            if part_markers and parts_root else None,
                            selection if isinstance(selection, (set, frozenset)) else None,
                            ascii_table_transform(md_path, metadata_files, parts_inputs)) as scaffold_files:
        part_files = scaffold_files[1:]
        lua_filters = [*lua_filters, *embedded_filters]
        all_inputs = [md_path, *parts_inputs] if parts_inputs else None
        any_citations = any(contains_citations(item) for item in [md_path, *parts_inputs])
        any_code_spans = any(has_code_spans(item.read_text(encoding="utf-8-sig"))
                             for item in [md_path, *parts_inputs])
        if parts_inputs:
            shown = len(selection) if isinstance(selection, (set, frozenset)) else len(parts_inputs)
            unit = "more file" if REPORT_BUILD.get("files") else "part"
            note("PARTS", f"{md_path}: {shown} {unit}{'s' if shown != 1 else ''} "
                          f"joined after it" + (" (partial build; numbered with the whole document)"
                                                if isinstance(selection, (set, frozenset)) else
                                                " (partial build)" if partial else ""))
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
            document_font = has_mainfont(md_path, variables, metadata_files)
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
                              and not has_monofont(md_path, variables, metadata_files))
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
            variables, pagesize_typo = paper_variables(md_path, metadata_files, variables, pagesize_typo,
                                                      paper_kind("tex" if target_format in ("latex", "beamer") else target_format, no_auto))
            tex_first_font = (None if not is_tex_target else
                              mainfont_choice([md_path, *parts_inputs], metadata_files, variables, font,
                                              document_font, mainfont_auto, no_auto, note))
            with prepared_latex_inputs([title_source, *pandoc_metadata_order(metadata_files)], is_tex_target,
                                       typst_engine=(target_format == "typst"),
                                       drop_embedded_preamble=not is_tex_target) as prepared, \
                    document_header_file(md_path, (bool(preamble_files) or has_embedded_preamble(md_path) or bool(pdf_meta_snippet_text))
                                         and is_tex_target, metadata_files, no_auto) as header_file, \
                    pdf_metadata_header_file(pdf_meta_snippet_text if is_tex_target else None) as pdf_meta_file, \
                    (script_fallback([md_path, *parts_inputs], metadata_files, variables, preamble_files or [],
                                     tex_first_font, None, no_auto, note)
                     if target_format in ("latex", "beamer") else contextlib.nullcontext((None, None))) \
                    as (fonts_header, fonts_filter), \
                    office_reference(md_path, metadata_files, variables, target_format, output, pandoc_options,
                                     no_auto, note) as office_arguments:
                source, *prepared_metadata = prepared
                writer = flat_writer(target_format, flat) if target_format in ("gfm", "gfm+raw", "txt") else target_format
                ansi_scratch = tempfile.TemporaryDirectory(prefix="pdfmd-ansi-") if target_format == "ansi" else None
                ansi_json = Path(ansi_scratch.name) / "document.json" if ansi_scratch is not None else None
                if ansi_json is not None:
                    writer = "json"                              # pdfmd_ansi draws Pandoc's AST (v3.30.3)
                cmd = ["pandoc", str(source), *map(str, part_files), "-o", str(ansi_json or output), "-t", writer]
                if flat_markdown and not any(option.startswith("--wrap") for option in pandoc_options):
                    cmd.append("--wrap=none")      # a paragraph is one line: a viewer wraps it, a diff shows what changed
                if (flat_markdown and output.parent.resolve() != md_path.parent.resolve()
                        and any(RELATIVE_IMAGE_RE.search(read_text_best_effort(item)) for item in [md_path, *parts_inputs])):
                    note("FLAT", f"{md_path}: the images keep the paths the document wrote, relative to ITS folder; the "
                                 f"output is in {display_path(output.parent)}, so those links point from there "
                                 "(put the output beside the images, or copy them)")
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
                cmd += table_keep_metadata(md_path, metadata_files)
                pandoc_cwd = pandoc_working_directory(metadata_cwd(metadata_files, md_path.parent))
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
                    first_font = tex_first_font
                    if first_font:
                        cmd += font_args("mainfont", first_font)
                        cmd += mathfont_args(first_font, md_path, metadata_files, variables, font or None, no_auto, None, note)
                    else:
                        cmd += document_font_args([md_path, *parts_inputs], metadata_files, variables)
                    if geometry_needed:
                        cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                    elif margin_options:
                        for margin_option in margin_options:
                            cmd += ["-V", f"geometry:{margin_option}"]
                    if monofont_needed:
                        cmd += font_args("monofont", default_monofont())
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
                if fonts_header is not None:
                    cmd += ["--include-in-header", str(fonts_header)]
                # Last, so a document's own header-includes can override
                # anything the shared preamble/pdf-meta files above defined
                # (Pandoc would otherwise drop it entirely; see
                # document_header_file). Added whenever header_file exists,
                # not only when preamble_files is non-empty -- see
                # document_header_includes()'s own docstring.
                if header_file is not None:
                    cmd += ["--include-in-header", str(header_file)]
                cmd += document_filter_args(all_inputs or md_path, md_path, metadata_files, no_auto, csv_filter, pandoc_options,
                                            flat_pictures=output.parent / f"{output.stem}_files" if flat_markdown else None,
                                            preamble=list(preamble_files or []) if flat_markdown else None,
                                            flat_text=target_format == "txt")
                cmd += select_filter_args(selection)
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
                if "--citeproc" in cmd or "--citeproc" in pandoc_options:
                    cmd += csl_args([md_path], metadata_files, pandoc_options, no_auto)
                # pandoc_options after the citation-engine flag above: a
                # caller-supplied --lua-filter/--filter needs resolved
                # citations already in the AST (same invariant as the
                # auto-discovered lua_filters below).
                if target_format in HTML_TARGETS:
                    cmd += html_pandoc_args(md_path, metadata_files, pandoc_options, self_contained, note)
                cmd += office_arguments
                cmd += pandoc_options
                if is_tex_target:
                    cmd += tex_package_args([md_path, *parts_inputs], no_auto, note)
                    cmd += paragraph_spacing_latex_args([md_path, *parts_inputs], metadata_files)
                    cmd += css_heading_args([md_path, *parts_inputs], css_meta, variables, no_auto, note)
                    cmd += cover_header_args([md_path, *parts_inputs], css_meta)
                    cmd += markup_header_args([md_path, *parts_inputs], css_meta, cmd)
                    cmd += slide_notes_args([md_path, *parts_inputs], metadata_files, target_format == "beamer")
                if fonts_filter is not None:
                    cmd += ["--lua-filter", str(fonts_filter)]  # before table-width: it renders cells to LaTeX
                if is_tex_target and tablewidth_auto:
                    cmd += width_filter_args(width_filter)
                cmd += cellalign_args([md_path, *parts_inputs], metadata_files)
                if is_tex_target:
                    cmd += tblr_header_args([md_path, *parts_inputs], metadata_files)
                    cmd += code_filter_args(no_auto, [md_path, *parts_inputs], metadata_files) + image_filter_args(no_auto, [md_path, *parts_inputs])
                    hoist_code_header(cmd)
                    keep_header_includes(cmd, [md_path], metadata_files, pandoc_options, header_file)
                for lua_filter in lua_filters:
                    cmd += ["--lua-filter", str(lua_filter)]
                cmd += office_arguments.filter_arguments
                cmd += chem_filter_args(list(all_inputs or [md_path]), metadata_files,
                                        list(preamble_files or ([] if discovery_disabled(no_auto, "preamble")
                                                                else find_preambles(md_path.parent, md_path.stem, []))),
                                        target_format, bool(office_arguments.filter_arguments), no_auto)
                cmd += paragraph_spacing_typst_args(md_path, metadata_files, target_format)
                cmd += typst_filter_args(target_format, cmd, pandoc_cwd)
                if target_format == "epub" and EBOOK_MATH.get("mode") == "text":
                    cmd += ebook_filter_args()                          # a Calibre ebook with no math: after \ce is converted
                if flat_target:
                    cmd += flat_filter_args(flat, target_format)       # last: it sees what every other filter made
                ascii_scratch = tempfile.TemporaryDirectory(prefix="pdfmd-ascii-") if ascii_on else None
                try:
                    ascii_missing_mode = ascii_missing(md_path, metadata_files) if ascii_on else None
                    if ascii_scratch is not None:
                        cmd += ascii_filter_args(Path(ascii_scratch.name), ascii_missing_mode,
                                                 smart=target_format in ("markdown", "commonmark_x", "txt", "plain"))     # after those
                    if office_arguments.filter_arguments:
                        result = run_office_pandoc(cmd, output, office_arguments, pandoc_cwd, verbose, debug)
                    else:
                        cmd = headers_as_metadata(cmd)
                        log_cmd(cmd, pandoc_cwd, verbose)
                        result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=pandoc_cwd,
                                                env=tex_search_env(md_path.parent, pandoc_cwd, md_path) if flat_markdown else None)
                    ascii_problem = (ascii_finish(output, Path(ascii_scratch.name), ascii_missing_mode, md_path)
                                     if ascii_scratch is not None and result.returncode == 0 else None)
                    if ansi_json is not None and result.returncode == 0:
                        ascii_problem = ansi_finish(ansi_json, output, md_path, verbose)
                finally:
                    if ascii_scratch is not None:
                        ascii_scratch.cleanup()
                    if ansi_scratch is not None:
                        ansi_scratch.cleanup()
                office_finish(office_arguments, md_path, verbose)
            if result.returncode == 0 and not ascii_problem:
                stamp_build(partial, skip_stamp, md_path, metadata_files, preamble_files or [], stamp_overrides, output, verbose)
            flush_summary()
            return md_path, result.returncode == 0 and not ascii_problem, ascii_problem or result.stderr[-3000:]

        document_font = has_mainfont(md_path, variables, metadata_files)
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
                          and not has_monofont(md_path, variables, metadata_files))
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
                    stamp_build(partial, skip_stamp, md_path, metadata_files, preamble_files or [],
                                        stamp_overrides, output, verbose)
                flush_summary()
                return md_path, ok, reason[-3000:]

        result = None
        failed_families: set[str] = set()
        failed_engines: list[str] = []
        for engine_index, engine in enumerate(engines):
            family = ENGINE_FAMILY.get(engine, engine)
            if family in failed_families:
                print(f"SKIP  {md_path}: {engine} shares the {family} engine with an earlier "
                      f"failure; skipping", file=sys.stderr)
                continue
            if engine == "typst" and pdfmd_install.typst_too_old():         # an automatic chain gets here (v3.33.62)
                print(f"SKIP  {md_path}: {pdfmd_install.typst_too_old()}", file=sys.stderr)
                continue
            if engine == "soffice":
                # Not a real Pandoc --pdf-engine -- see convert_via_soffice_bridge's
                # own docstring for why this is special-cased here instead.
                ok, reason = convert_via_soffice_bridge(md_path, output, effective_from, metadata_files,
                                                        variables, pandoc_options, lua_filters, csv_filter,
                                                        no_auto, verbose,
                                                        labels="auto" if engines == ["soffice"] else "off",
                                                        title_source=title_source, part_files=part_files,
                                                        partial=partial, selection=selection)
                result = subprocess.CompletedProcess(args=["soffice"], returncode=0 if ok else 1,
                                                     stdout="", stderr="" if ok else reason)
                if ok:
                    vprint(verbose, f"AUTO SOFFICE  {md_path}: rendered via Pandoc -> .docx -> soffice "
                          "(last-resort fallback)")
                    record_engine(engine, failed_engines)
                    break
                failed_families.add(family)
                failed_engines.append(engine)
                remaining = [e for e in engines[engine_index + 1:] if ENGINE_FAMILY.get(e, e) not in failed_families]
                report_engine_failure(str(md_path), engine, result, remaining, debug)
                continue
            with prepared_latex_inputs([title_source, *pandoc_metadata_order(metadata_files)], engine in LATEX_ENGINES,
                                       typst_engine=(engine == "typst")) as prepared, \
                    document_header_file(md_path, (bool(preamble_files) or has_embedded_preamble(md_path) or bool(pdf_meta_snippet_text))
                                         and engine in LATEX_ENGINES, metadata_files, no_auto) as header_file, \
                    pdf_metadata_header_file(pdf_meta_snippet_text if engine in LATEX_ENGINES else None) as pdf_meta_file:
                source, *prepared_metadata = prepared

                def run(selected_font: str | None, fallback: bool = False, plain: bool = False):
                    with script_fallback([md_path, *parts_inputs], metadata_files, variables, preamble_files or [],
                                         selected_font, engine,
                                         no_auto if not plain or no_auto == [] else [*(no_auto or []), "unicode"],
                                         note) as (fonts_header, fonts_filter), \
                            managed_fonts_css(engine) as fonts_css:
                        return run_command(selected_font, fallback, fonts_header or fonts_css, fonts_filter)

                def run_command(selected_font: str | None, fallback: bool, fonts_header, fonts_filter):
                    cmd = ["pandoc", str(source), *map(str, part_files), "-o", str(output), "--pdf-engine=" + engine]
                    if engine == "typst" and managed_index() is not None and managed_index().faces:
                        cmd.append(f"--pdf-engine-opt=--font-path={fonts_directory()}")
                    if engine == "tectonic":                      # it reads no TEXINPUTS: the kits' folders by its own option
                        cmd += [f"--pdf-engine-opt=-Zsearch-path={folder}" for folder in tectonic_search_folders(md_path)]
                    if engine == "prince":                        # it names only the page's first author (v3.33.66)
                        cmd += prince_author_options(md_path, metadata_files, variables)
                    if engine == "typst" and (0,) < pandoc_version() < (3, 2) and not any(
                            "--root" in option for option in pandoc_options):
                        # an older Pandoc runs typst with its root at the document, where an absolute picture path
                        # (pdfmd's drawn diagrams, in the cache) is looked for under it; a newer one gives Typst /
                        cmd.append("--pdf-engine-opt=--root=/")
                    if effective_from:
                        cmd += ["-f", effective_from]
                    for metadata in prepared_metadata:
                        cmd += ["--metadata-file", str(metadata)]
                    if partial:
                        cmd += PARTIAL_METADATA
                    cmd += table_keep_metadata(md_path, metadata_files)
                    pandoc_cwd = pandoc_working_directory(metadata_cwd(metadata_files, md_path.parent))
                    cmd += resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
                    if presentation:
                        cmd += ["-t", "beamer"]
                        if slide_level is not None:
                            cmd += ["--slide-level=" + str(slide_level)]
                    if engine == "typst" and UNICODE_CODE_FONTS and not any(
                            variable.startswith("codefont=") for variable in variables):
                        for family in UNICODE_CODE_FONTS:
                            cmd += ["-V", f"codefont={family}"]
                    if selected_font:
                        cmd += font_args("mainfont", selected_font, engine in LATEX_ENGINES)
                        cmd += mathfont_args(selected_font, md_path, metadata_files, variables, font or None, no_auto,
                                             engine, note)
                    elif engine in LATEX_ENGINES:
                        cmd += document_font_args([md_path, *parts_inputs], metadata_files, variables)
                    if fallback and not any(variable.startswith("mainfontfallback=") for variable in variables):
                        cmd += ["-V", f"mainfontfallback={fallback_font()}"]
                    if geometry_needed and engine in LATEX_ENGINES:
                        cmd += ["-V", f"geometry:margin={DEFAULT_MARGIN}"]
                    elif margin_options and engine in LATEX_ENGINES:
                        for margin_option in margin_options:
                            cmd += ["-V", f"geometry:{margin_option}"]
                    if monofont_needed and engine in LATEX_ENGINES:
                        cmd += font_args("monofont", default_monofont())
                    page_variables, page_typo = paper_variables(md_path, metadata_files, variables, pagesize_typo,
                                                                paper_kind(engine, no_auto))
                    if page_typo and engine in LATEX_ENGINES:
                        cmd += ["-V", f"papersize={page_typo}"]
                    for variable in page_variables:
                        cmd += ["-V", variable]
                    if engine == "typst" and not auto_disabled(no_auto, "papersize"):
                        typst_size = typst_papersize_translation(
                            page_typo or next((v.split("=", 1)[1] for v in page_variables
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
                    if fonts_header is not None:
                        cmd += ["--include-in-header", str(fonts_header)]
                    # Last, so a document's own header-includes can override
                    # anything the shared preamble/pdf-meta files above
                    # defined (Pandoc would otherwise drop it entirely; see
                    # document_header_file). Added whenever header_file
                    # exists, not only when preamble_files is non-empty --
                    # see document_header_includes()'s own docstring.
                    if header_file is not None:
                        cmd += ["--include-in-header", str(header_file)]
                    cmd += document_filter_args(all_inputs or md_path, md_path, metadata_files, no_auto, csv_filter, pandoc_options)
                    cmd += select_filter_args(selection)
                    if any_citations and "--citeproc" not in pandoc_options and not CITEPROC_DISABLED:
                        cmd.append("--citeproc")
                    if "--citeproc" in cmd or "--citeproc" in pandoc_options:
                        cmd += csl_args([md_path], metadata_files, pandoc_options, no_auto)
                    # pandoc_options after --citeproc, same reason as below: a
                    # caller-supplied --lua-filter/--filter needs resolved
                    # citations already in the AST. (This used to sit before
                    # the --citeproc append above, which silently broke any
                    # citeproc-dependent filter passed via extra CLI args --
                    # e.g. `--lua-filter=some.lua` landed ahead of --citeproc
                    # on the actual pandoc command line. Confirmed via
                    # --verbose CMD output before this fix.)
                    cmd += pandoc_options
                    if engine in LATEX_ENGINES:
                        cmd += tex_package_args([md_path, *parts_inputs], no_auto, note)
                        cmd += paragraph_spacing_latex_args([md_path, *parts_inputs], metadata_files)
                        cmd += css_heading_args([md_path, *parts_inputs], css_meta, variables, no_auto, note)
                        cmd += cover_header_args([md_path, *parts_inputs], css_meta)
                        cmd += markup_header_args([md_path, *parts_inputs], css_meta, cmd)
                        cmd += slide_notes_args([md_path, *parts_inputs], metadata_files, bool(presentation))
                    # Lua filters go last: pandoc applies --citeproc and filters in
                    # command-line order, and a filter that renders cell contents to
                    # LaTeX needs the citations already resolved. csv-table has to
                    # come before table-width so a CSV-generated table gets the same
                    # width-balancing pass a hand-written one would.
                    if fonts_filter is not None:
                        cmd += ["--lua-filter", str(fonts_filter)]  # before table-width: it renders cells to LaTeX
                    if tablewidth_auto and engine in LATEX_ENGINES:
                        cmd += width_filter_args(width_filter)
                    cmd += cellalign_args([md_path, *parts_inputs], metadata_files)
                    if engine in LATEX_ENGINES:
                        cmd += tblr_header_args([md_path, *parts_inputs], metadata_files)
                        cmd += code_filter_args(no_auto, [md_path, *parts_inputs], metadata_files) + image_filter_args(no_auto, [md_path, *parts_inputs])
                        hoist_code_header(cmd)
                        keep_header_includes(cmd, [md_path], metadata_files, pandoc_options, header_file)
                    for lua_filter in lua_filters:
                        cmd += ["--lua-filter", str(lua_filter)]
                    # last of all, after the LaTeX filter below too: a reference it makes to a figure Typst has no
                    # label for is a link Typst would stop on; WeasyPrint's math is typeset once its \ce is converted
                    cmd += paragraph_spacing_typst_args(md_path, metadata_files, engine)
                    last_filters = typst_filter_args(engine, cmd, pandoc_cwd) + weasyprint_math_args(
                        engine, pandoc_options,
                        selected_font or document_font_setting("mainfont", [md_path, *parts_inputs], metadata_files, variables),
                        no_auto)
                    page_options = lambda: (browser_page_css(md_path, metadata_files, variables) if engine in BROWSER_ENGINES
                                            else calibre_page_options(md_path, metadata_files, variables))
                    if engine == "calibre" or engine in BROWSER_ENGINES or (engine in ("typst", "weasyprint") and office_fallback_wanted(
                            md_path, metadata_files, failed_families, "typst" if engine == "typst" else "html",
                            [md_path, *parts_inputs])):
                        # LaTeX failed, or the document has LaTeX this writer would drop (Calibre always, like
                        # LibreOffice): it becomes native or a picture instead of nothing. References take LaTeX's
                        # numbers as in a Word file (`office: {labels}`), unless LaTeX is what failed.
                        with office_reference(md_path, metadata_files, variables, "typst" if engine == "typst" else "html",
                                              output, pandoc_options, no_auto, note,
                                              labels="off" if latex_failed(failed_families) else None,
                                              force_filter=True) as office_arguments:
                            if office_arguments.filter_arguments:
                                cmd += office_arguments.filter_arguments + last_filters
                                answer = run_engine_command(
                                    cmd, engine, output,
                                    lambda command, target: run_office_pandoc(command, target, office_arguments,
                                                                              pandoc_cwd, verbose),
                                    page_options, verbose)
                                office_finish(office_arguments, md_path, verbose)
                                return answer
                    cmd += last_filters

                    def run_pandoc(command: list[str], target: Path):
                        command = headers_as_metadata(command)
                        log_cmd(command, pandoc_cwd, verbose)
                        return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", cwd=pandoc_cwd,
                                              env=tex_search_env(md_path.parent, pandoc_cwd, md_path))
                    return run_engine_command(cmd, engine, output, run_pandoc, page_options, verbose)

                first_font = mainfont_choice([md_path, *parts_inputs], metadata_files, variables, font,
                                             document_font, mainfont_auto, no_auto, note)
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
                if result.returncode != 0 and "pdfmdf" in result.stdout + result.stderr:
                    # a font pdfmd picked for another script would not load: build without them
                    print(f"WARN  {md_path}: the fonts pdfmd chose for other scripts failed under {engine}; "
                          "building without them (--verbose shows which)", file=sys.stderr)
                    result = run(first_font, fallback=False, plain=True)
                combined_output = result.stdout + result.stderr
                if (mainfont_auto and not explicit_font and result.returncode == 0
                        and missing_glyph_warning(combined_output)):
                    retry_font = font or fallback_font()
                    print(retry_font_note(md_path, first_font or PREFERRED_FONT, retry_font,
                                          missing_glyph_codes(combined_output)), file=sys.stderr)
                    result = run(retry_font)
            if result.returncode == 0:
                record_engine(engine, failed_engines)
                break
            failed_families.add(family)
            failed_engines.append(engine)
            if pandoc_refused_command(result):      # an option Pandoc does not take: every engine would fail on it (v3.33.44)
                break
            remaining = [e for e in engines[engine_index + 1:] if ENGINE_FAMILY.get(e, e) not in failed_families]
            if chain_engine_failed(str(md_path), engine, result, remaining, debug):     # engine-fallback stops here
                break
        if result is None:
            # Every engine was skipped: each shares an engine with one that failed already.
            return md_path, False, ("no PDF engine could build this. Install a LaTeX or Typst engine "
                                    "(pdfmd --install typst) or use --to html")
        if result.returncode == 0:
            stamp_build(partial, skip_stamp, md_path, metadata_files, preamble_files or [], stamp_overrides, output, verbose)
        flush_summary()
        return md_path, result.returncode == 0, result.stderr[-3000:]


def finish_build(result, seen: list[str], md_path: Path, metadata_files: list[Path]) -> "Built":
    """Attach the engine that built the file and apply --strict: a build that printed a warning (or about which Pandoc
    warned) fails, its output kept."""
    problems = list(seen)
    if result[1] and len(result) > 2 and isinstance(result[2], str):
        known = {line.strip() for line in problems}
        problems += [line for line in re.findall(r"(?m)^(?:\[WARNING\]|WARN\b).*$", result[2]) if line.strip() not in known]
    if result[1] and problems and resolve_strict(md_path, metadata_files):
        result = (result[0], False, strict_message(problems))
    built = Built(result, BUILD["engine"], BUILD["failed"], BUILD["output"])
    built.stopped = chain_stopped()
    return attach_time(built, md_path, metadata_files)


def set_soffice_limit(md_path: Path, metadata_files: list[Path]) -> None:
    """The `soffice-timeout` of the document about to be built: its `pdfmd-options`, its metadata files', the config's."""
    global SOFFICE_TIMEOUT_NOW
    value = (first_pdfmd_option(md_path, metadata_files, "soffice-timeout") if md_path.suffix.lower() in (".md", ".markdown")
             else config_options().get("soffice-timeout"))
    SOFFICE_TIMEOUT_NOW = soffice_timeout_from(value)


def convert_one(md_path: Path, *args, **kwargs) -> "Built":
    """_convert_one_recorded, with the engine that built the file and --strict (see the section above)."""
    BUILD["engine"], BUILD["failed"], BUILD["output"], BUILD["sources"], BUILD["partial"], BUILD["root"] = None, [], None, [], None, None
    begin_timer()
    BUILD["tried"], BUILD["chain"] = [], None
    bound = inspect.signature(_convert_one_recorded).bind(md_path, *args, **kwargs).arguments
    given = bound.get("metadata_file")
    metadata_files = given if isinstance(given, list) else ([given] if given else [])
    set_soffice_limit(md_path, metadata_files)
    recorder = load_package("pdfmd_buildinfo.build").BuildRecorder.start(md_path, metadata_files)
    try:
        with warning_capture() as seen:
            pdfmd_cache.check_location(md_path, metadata_files, bound.get("cache_cli"))
            pdfmd_native.warn_nameless_authors(md_path, metadata_files)
            result = _convert_one_recorded(md_path, *args, **kwargs)
            if result[1]:
                check_output_budget(BUILD["output"], BUILD["sources"] or [md_path], md_path, metadata_files)
        built = finish_build(result, seen, md_path, metadata_files)
    except BaseException as error:
        where = recorder.finish(None, failure_text(error)) if recorder else None
        if where:
            print(f"      full record: {under_home(where)}", file=sys.stderr)
        raise
    if recorder:
        built.record_path = recorder.finish(built)
    return built


def make_embed_plan(md_path: Path, metadata_files: list[Path], preamble_files: list[Path] | None,
                    no_auto: list[str] | None, request: "EmbedRequest | None") -> "EmbedPlan | None":
    """What --embed-metadata folds into ``md_path``'s assembled text, or None."""
    resolved = resolve_embed(md_path, metadata_files, request)
    if resolved is None:
        return None
    kinds, lua_mode = resolved
    discovered_lua = ([] if (discovery_disabled(no_auto, "lua") or "lua" not in kinds)
                      else find_lua_filters(md_path, metadata_files, no_auto))
    if not auto_disabled(no_auto, "lua") and "lua" in kinds:
        for extra_filter in frontmatter_extra_lua_filters(md_path, metadata_files):
            if extra_filter not in discovered_lua:
                discovered_lua.append(extra_filter)
    plan = EmbedPlan(kinds, lua_mode, list(metadata_files), kit_embedded_preambles(md_path, metadata_files, preamble_files), discovered_lua)
    kits_here = active_kits(md_path, metadata_files, no_auto)
    # What a kit brought (defaults, preamble, Lua filter) is now in the source: a rebuild must not choose the kit again, where it
    # would be found twice over (the stored copies and the kit's), or not found at all. `kit: none` in the source's own
    # pdfmd-options replaces every `kit:` below it; only a part left out of the embedding keeps the kit chosen.
    plan.kit_none = bool(kits_here) and {"metadata", "preamble"} <= kinds and (
        not any(item.kit.lua for item in kits_here) or ("lua" in kinds and lua_mode in ("embed", "apply")))
    if "hst" in kinds:
        found = history_file(md_path, metadata_files, existing=True)
        plan.hst_file = found if found.is_file() else None
    return plan


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


def report_common_folder(files: list[Path]) -> Path:
    """The folder a report's chapters are laid out relative to (the first chapter's, when they
    share no folder, as on different Windows drives)."""
    try:
        return Path(os.path.commonpath([str(item.parent.resolve()) for item in files]))
    except ValueError:
        return files[0].parent.resolve()


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
POLISH_INFO_KEYS = {"title": "/Title", "subject": "/Subject", "author": "/Author", "keywords": "/Keywords"}


# `parse_hf_template`, `fill_hf_field`, `markdown_headings`, `search_form`, `locate_headings`, `outline_entries`, `hf_text`,
# `hf_overlay`, `local_file_of_link`, `polish_wanted` and `polish_pdf` (with `HF_FIELDS`, `HF_FONT`, `HF_SIZE`, `HF_MARGIN` and
# `LINKED_FILE_LIMIT`) live in `pdfmd_polish` (v3.33.13); the re-exports are in the binding block above.


# (the `mdpdf`, `md2pdf`, `inkmd`, `batchmd` and `pan-tec` command translations moved to lib/pdfmd_compat, v3.33.15; their *_main entry points are re-exported in the binding block)


def _convert_one_recorded(md_path: Path, out_dir: Path | None, presentation: bool, font: str,
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
                source_override: tuple[str, bool] | None = None,
                all_parts: list[Path] | None = None,
                full_override: str | None = None,
                calc_text_override: str | None = None, output_resolved: bool = False) -> tuple[Path, bool, str]:
    """_convert_one, plus the --backup snapshot on success -- wrapped here
    rather than threaded into each of _convert_one's own success returns
    (Pandoc, natbib/biblatex, direct .tex, office), so every one of them
    gets it, including any added later.
    """
    global LAST_SCANNED, LAST_EXACT, LAST_WHOLE, LAST_SKIPPED, CALC_SEED, CALC_BELOW, CALC_DUMP
    LAST_SCANNED, LAST_EXACT, LAST_WHOLE, LAST_SKIPPED = 0, False, False, 0
    metadata_list = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
    scratch = None
    label_scan = None
    selection = None
    pandoc_inputs = extra_inputs
    if partial or source_override is not None:
        seed_mode = seed_labels_mode(md_path, metadata_list)
        if label_scan_wanted(seed_mode, target_format, engines, presentation, md_path, True, parts_root is not None,
                             [source_override[0]] if source_override is not None else []):
            scratch = tempfile.TemporaryDirectory(prefix="pdfmd-labels-")
            label_scan = build_label_scan(md_path, Path(scratch.name), font, engines, variables, slide_level,
                                          pandoc_options, metadata_file, preamble_files, from_format, no_auto,
                                          stamp_overrides or {}, trust_embedded, list(all_parts or []), parts_root,
                                          verbose, draft=(seed_mode == "draft"))
            LAST_SCANNED = label_scan.labels if label_scan is not None else 0
            LAST_EXACT = bool(label_scan is not None and label_scan.exact)
            LAST_SKIPPED = label_scan.skipped if label_scan is not None else 0
        elif select_wanted(seed_mode, target_format, engines, presentation, md_path):
            # HTML, Word, OpenDocument, Typst: no LaTeX to seed. Number the whole document, then keep the part(s) asked for.
            if parts_root is not None and all_parts and extra_inputs:
                selection = set(extra_inputs)
                pandoc_inputs = list(all_parts)
                LAST_WHOLE = True
            elif source_override is not None and full_override is not None:
                selection = True
                source_override = (full_override, source_override[1])
                LAST_WHOLE = True
    calc_scratch = None
    calc_names = calc_below_names = 0
    calc_from = calc_below_from = ""
    if (partial or source_override is not None) and selection is None and not presentation:
        # The names the calculator needs from the rest of the document (a `mean_A`{=2dp} of part 60, defined in part 50, or the
        # `y` that part 20 prints, defined in part 30): the nearest definition above, else the first below, as in the full build.
        before = []
        after = []
        if all_parts and extra_inputs:
            built = [all_parts.index(part) for part in extra_inputs if part in all_parts]
            before = [part for part in all_parts[:max(built)] if part not in extra_inputs] if built else []
            after = [part for part in all_parts[max(built) + 1:] if part not in extra_inputs] if built else []
            calc_from = parts_range_text(before)
            calc_below_from = parts_range_text(after)
        calc_wanted = bool(before) or bool(after) or bool(calc_text_override and calc_text_override.strip())
        if calc_wanted and seed_calc_mode(md_path, metadata_list) != "off":
            calc_scratch = tempfile.TemporaryDirectory(prefix="pdfmd-calc-")
            if calc_text_override is None:
                inputs = calc_marked_inputs(md_path, all_parts or [], list(extra_inputs or []), Path(calc_scratch.name))
            else:
                text_whole = Path(calc_scratch.name) / "whole.md"
                text_whole.write_text(calc_text_override, encoding="utf-8")
                inputs = [text_whole]
                calc_from, calc_below_from = "the sections above it", "the sections below it"
            seed_file, calc_names, below_file, calc_below_names = build_calc_seed(
                md_path, metadata_list, [md_path, *(extra_inputs or [])], inputs, Path(calc_scratch.name), from_format, verbose)
            CALC_SEED, CALC_BELOW = seed_file, below_file
    export_target = calc_export_file(md_path, metadata_list) if target_format != ASSEMBLED_FORMAT else None
    export_scratch = None
    if export_target is not None:
        if (partial or source_override is not None) and selection is None and CALC_SEED is None:
            print(f"NOTE  calc: {display_path(export_target)} is not written for a part built alone with no names from the parts "
                  "above it (seed-calc is off, or nothing stands above it)", file=sys.stderr)
            export_target = None
        else:
            export_scratch = tempfile.TemporaryDirectory(prefix="pdfmd-calc-export-")
            CALC_DUMP = Path(export_scratch.name) / "names.tsv"
    if not output_resolved:
        planned = output_file or load_package("pdfmd_routing.output").planned(md_path, out_dir, target_format)
        output_file = load_package("pdfmd_routing.output").protected(md_path, planned, target_format, metadata_list)
    try:
        result = _convert_one(md_path, out_dir, presentation, font, engines, variables, slide_level,
                              pandoc_options, metadata_file, output_file, preamble_files,
                              target_format=target_format, from_format=from_format, no_auto=no_auto,
                              verbose=verbose, debug=debug, stamp_overrides=stamp_overrides,
                              keep_aux=keep_aux, extra_inputs=pandoc_inputs, partial=partial,
                              cache_cli=cache_cli, full_scaffold=(md_path if extra_inputs else None),
                              parts_root=parts_root, embed=embed, trust_embedded=trust_embedded,
                              self_contained=self_contained, source_override=source_override,
                              label_scan=label_scan, selection=selection)
    finally:
        CALC_SEED = CALC_BELOW = None
        dump_text = ""
        if CALC_DUMP is not None and CALC_DUMP.is_file():
            dump_text = CALC_DUMP.read_text(encoding="utf-8", errors="replace")
        CALC_DUMP = None
        if export_scratch is not None:
            export_scratch.cleanup()
        if scratch is not None:
            scratch.cleanup()
        if calc_scratch is not None:
            calc_scratch.cleanup()
    if result[1] and export_target is not None and dump_text:
        try:
            written = write_calc_export(dump_text, export_target)
        except OSError as error:
            print(f"WARN  calc: could not write {display_path(export_target)} ({error})", file=sys.stderr)
        else:
            if written:
                print(f"CALC  {written} name{'s' if written != 1 else ''} written to {display_path(export_target)}")
    if result[1] and (calc_names or calc_below_names):
        taken = []
        if calc_names:
            taken.append(f"{calc_names} names taken from {calc_from}")
        if calc_below_names:
            taken.append(f"{calc_below_names} " + ("from" if taken else "names taken from") + f" {calc_below_from} (defined below)")
        print(f"NOTE  calc: {', '.join(taken)} (evaluated, not typeset)")
    if result[1] and target_format != ASSEMBLED_FORMAT:
        metadata_files = (metadata_file if isinstance(metadata_file, list)
                          else ([metadata_file] if metadata_file else []))
        saved: list[Path] = []
        for backed_up in [md_path, *(extra_inputs or [])]:
            backup_after_success(backed_up, metadata_files, backup, verbose, backup_format, collect=saved)
        if saved:
            print(backup_summary(md_path, saved))
            if len(saved) > 1:
                for target in saved:
                    vprint(verbose, f"  BACKUP  {display_path(target)}")
        if target_format == "pdf":
            made_pdf = output_file or ((out_dir / f"{md_path.stem}.pdf") if out_dir else md_path.with_suffix(".pdf"))
            backup_pdf_after_success(md_path, made_pdf, metadata_files, backup,
                                     verbose, datetime.fromtimestamp(backup_sort_key(saved[0])[0]) if saved else None)
        if target_format == "pdf" and source_override is None and not partial:
            polish_pdf(output_file or ((out_dir / f"{md_path.stem}.pdf") if out_dir else md_path.with_suffix(".pdf")),
                       [md_path, *(extra_inputs or [])], verbose)
        if (target_format == "pdf" and source_override is None and not partial and not presentation
                and resolve_hybrid(md_path, metadata_files)):
            hybrid_after_success(md_path, output_file or ((out_dir / f"{md_path.stem}.pdf") if out_dir
                                                           else md_path.with_suffix(".pdf")),
                                 metadata_files, variables, effective_no_auto(md_path, no_auto), verbose)
        if (target_format == "pdf" and source_override is None and not partial
                and md_path.suffix.lower() in (".md", ".markdown")
                and resolve_attach(md_path, metadata_files)):
            produced = output_file or ((out_dir / f"{md_path.stem}.pdf") if out_dir
                                       else md_path.with_suffix(".pdf"))
            attach_source_after_success(md_path, produced, list(extra_inputs or []), metadata_files,
                                        preamble_files, effective_no_auto(md_path, no_auto), verbose,
                                        report=bool(REPORT_BUILD), base=REPORT_BUILD.get("base"))
        if (target_format in MARKDOWN_TARGETS and source_override is None and not partial
                and md_path.suffix.lower() in (".md", ".markdown")):
            keep_mode = resolve_keep_source(md_path, metadata_files)
            if keep_mode:
                suffix = output_extension_for(target_format, md_path)
                produced = output_file or ((out_dir / f"{md_path.stem}{suffix}") if out_dir
                                           else md_path.with_suffix(suffix))
                keep_source_after_success(md_path, produced, list(extra_inputs or []), metadata_files,
                                          preamble_files, effective_no_auto(md_path, no_auto), keep_mode, verbose,
                                          ascii_only=ASCII_CLI["on"] and target_format in ASCII_FORMATS,
                                          pandoc_options=pandoc_options)
    return result


# The hybrid PDF (v3.25.10): lib/pdfmd_hybrid (its explanation is there). These two stay: main() rebinds the first,
# the attachment readers above read the second.
HYBRID_CLI: bool | None = None
HYBRID_MIME = {"odt": "application/vnd.oasis.opendocument.text", "odp": "application/vnd.oasis.opendocument.presentation",
               "ods": "application/vnd.oasis.opendocument.spreadsheet"}


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
                      source_override: tuple[str, bool] | None = None,
                      label_scan: "LabelScan | None" = None) -> tuple[Path, bool, str]:
    """Build a PDF the cache way: Pandoc writes the .tex, pdfmd compiles it.
    See the comment above CACHE_DEFAULTS. ``persistent`` False (the natbib +
    parts case without the cache switched on) uses a scratch folder instead
    and discards it.
    """
    metadata_files = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
    cache_base = document_cache_root(full_scaffold or md_path, metadata_files)
    if persistent:
        prepare_cache_root(cache_base)
        base = cache_directory(full_scaffold or md_path, cache_base, note)
    else:
        base = Path(mkdtemp(prefix="pdfmd-cache-"))
    base.mkdir(parents=True, exist_ok=True)
    if persistent:
        write_cache_manifest(base, full_scaffold or md_path)
    stem = safe_stem(output.stem)
    tex_path = base / f"{stem}.tex"
    headers = list(preamble_files or [])
    own_headers: list[str] = []      # what pdfmd adds to this build only: left out of the plots' preamble
    seeded = 0
    global LAST_SEEDED
    LAST_SEEDED = 0
    seed_mode = seed_labels_mode(md_path, metadata_files)
    if persistent and parts_inputs and parts_root is not None and not (label_scan and label_scan.markers):
        defs = base / f"{stem}.pdfmd-defs.tex"
        defs.write_text(PARTS_MARKER_DEFS, encoding="utf-8")
        headers.append(defs)
        own_headers.append(PARTS_MARKER_DEFS)
    # A partial build takes its missing labels from the last full build's .aux: the
    # report's, in parts mode, or the document's own for one section or element of an
    # ordinary document (source_override), which has no parts and so no counter markers.
    seed_from = full_scaffold if parts_root is not None else (md_path if source_override is not None else None)
    if (persistent and partial and seed_from is not None and stem != safe_stem(seed_from.stem)
            and seed_mode in ("auto", "aux", "draft") and not (label_scan is not None and label_scan.exact)):
        # (Not when the build is named like the full one: it would overwrite the .aux it reads.)
        full_aux = base / f"{safe_stem(seed_from.stem)}.aux"
        seed = base / f"{stem}.seed.tex"
        seed.unlink(missing_ok=True)
        seeded = seed_labels_file(full_aux, seed)
        if seeded:
            LAST_SEEDED = seeded
            hook = base / f"{stem}.seed-hook.tex"
            hook.write_text("\\AtBeginDocument{\\InputIfFileExists{\"%s\"}{}{}}\n" % seed.as_posix(), encoding="utf-8")
            headers.append(hook)
            own_headers.append(hook.read_text(encoding="utf-8"))
            when = datetime.fromtimestamp(full_aux.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            note("CACHE", f"{md_path}: {seeded} labels from the last full build ({when}) fill in "
                          + ("references to the rest of the document" if source_override is not None
                             else "references to parts left out"))
    if label_scan is not None:
        headers.extend(label_scan.headers)          # after the .aux seed: what the last full build knew wins
        own_headers.extend(header.read_text(encoding="utf-8", errors="replace") for header in label_scan.headers)
        if label_scan.exact:
            note("LABELS", f"{md_path}: labels from a draft pass over the whole document (exact), the scan fills in the rest")
        else:
            note("LABELS", f"{md_path}: {label_scan.labels} labels counted from the sources fill in what the "
                           f"{'last full build does not know' if seeded else 'references to parts left out need'} "
                           "(approximate: a macro the document defines itself is not counted)")
    try:
        stage_build = (BUILD["output"], list(BUILD["sources"]))      # the PDF this build is for (v3.30.1)
        built = _convert_one(md_path, out_dir, False, font, engines, variables, slide_level,
                             pandoc_options, metadata_file, tex_path, headers, target_format="latex",
                             from_format=from_format, no_auto=no_auto, verbose=verbose, debug=debug,
                             stamp_overrides=stamp_overrides, keep_aux=keep_aux,
                             extra_inputs=parts_inputs, partial=partial, cache_cli=False,
                             skip_stamp=True, parts_root=parts_root,
                             part_markers=bool((persistent or (label_scan is not None and label_scan.markers))
                                               and parts_inputs),
                             trust_embedded=trust_embedded, source_override=source_override)
        BUILD["output"], BUILD["sources"] = stage_build[0], stage_build[1]   # the .tex stage recorded its own file
        if not built[1]:
            return built
        pandoc_cwd = pandoc_working_directory(metadata_cwd(metadata_files, md_path.parent))
        tex_env = tex_search_env(md_path.parent, pandoc_cwd, md_path)
        plot_dir = None
        aliases: dict[str, list[str]] = {}
        preamble_text = ""
        if plots:
            tex_text = tex_path.read_text(encoding="utf-8")
            preamble_text = plot_preamble(tex_text.split("\\begin{document}")[0], own_headers)
            styles = picture_cache_styles(preamble_text)
            sty_text = "\0".join(f"{name}\0{text}" for name, text, _ in styles)
            aliases = cache_aliases(styles)
            # the document's own cache folder: the aux cache's, or the one it would use when it is off
            plot_home = base if persistent else cache_directory(full_scaffold or md_path, cache_base, note)
            roots = [Path(os.path.abspath(pandoc_cwd)), Path(os.path.abspath(md_path.parent)), *user_tex_trees()]
            if engines[0] != "lualatex":
                note("CACHE", "plots: only LuaLaTeX is supported; plot cache skipped")
            elif not styles:
                note("CACHE", "plots: no package the document loads takes part in the picture cache "
                              "(its style file mentions pdfmdCacheDir); skipped")
            elif " " in str(plot_home):
                note("CACHE", "plots: the cache folder's path has a space; plot cache skipped")
            else:
                if not persistent:
                    prepare_cache_root(cache_base)
                    plot_home.mkdir(parents=True, exist_ok=True)
                    write_cache_manifest(plot_home, full_scaffold or md_path)
                plot_dir = plot_cache_directory(preamble_text, sty_text, "lualatex", plot_home)
                plot_dir.mkdir(parents=True, exist_ok=True)
                os.utime(plot_dir)
                prune_plot_directories(plot_dir)
                validate_plot_entries(plot_dir, verbose, roots)
                tex_path.write_text("\\def\\pdfmdCacheDir{%s/}\\def\\pdfmdCacheVersion{3}\n" % plot_dir.as_posix()
                                    + "".join("\\def\\%s{%s/}\n" % (name, plot_dir.as_posix())
                                              for name in aliases.get("dir", [])) + tex_text,
                                    encoding="utf-8")
        ok, reason = compile_tex_direct(tex_path, output, engines, keep_aux, verbose, debug,
                                        aux_dir=base, cwd=pandoc_cwd, env=tex_env)
        if ok and plot_dir is not None:
            requests = {}
            for suffix in (*aliases.get("requests", []), ".pdfmdreq"):
                requests.update(read_plot_requests(base / f"{stem}{suffix}"))
            if requests:
                started = time.time()
                done, failed = render_plot_requests(requests, plot_dir, preamble_text, "lualatex",
                                                    pandoc_cwd, tex_env, roots, verbose, aliases)
                if done or failed:
                    print(f"PLOTS  stored {done} plot{'s' if done != 1 else ''} for the next build "
                          f"({time.time() - started:.0f} s)" + (f"; {failed} failed (typeset inline, "
                          "nothing lost)" if failed else ""))
        if ok:
            stamp_build(partial, False, md_path, metadata_files, preamble_files or [], stamp_overrides,
                                 output, verbose)
        flush_summary()
        return md_path, ok, reason[-3000:]
    finally:
        if not persistent:
            shutil.rmtree(base, ignore_errors=True)


DIRECT_SUFFIXES = {".typ": "typst", ".typst": "typst", ".html": "html", ".htm": "html", ".xhtml": "html"}
DIRECT_READERS = {"typst": ("typst",), "html": ("html", "html5")}


def direct_route(path: Path, target_format: str, from_format: str | None, no_auto: list[str] | None,
                 engine_request: str | None, announce: bool = True) -> str | None:
    """`typst` or `html` when this input is finished enough to go straight to its engine (a `.typ` to Typst, an
    `.html` to WeasyPrint or a browser), else None: the Pandoc route, which is also what is left when the tool for
    the direct one is not installed. `--no-auto typstdirect|htmldirect`, an explicit `--from`, a target other than
    PDF, or an `-e` naming an engine of another kind all keep the Pandoc route."""
    kind = DIRECT_SUFFIXES.get(path.suffix.lower())
    if kind is None or target_format != "pdf" or auto_disabled(no_auto, kind + "direct"):
        return None
    if from_format is not None and from_format.casefold().split("+")[0] not in DIRECT_READERS[kind]:
        return None
    try:
        import pdfmd_direct as direct
    except ImportError:
        return None
    if kind == "typst":
        if not direct.typst_accepts_request(engine_request):
            return None
        if not engine_executable("typst"):
            if announce:
                print(f"WARN  {display_path(path)}: Typst is not installed, so this goes through Pandoc's Typst "
                      "reader, which loses what Pandoc's model cannot hold (`pdfmd --install typst`)", file=sys.stderr)
            return None
        return kind
    if not direct.html_accepts_request(engine_request):
        return None
    text = read_text_best_effort(path)
    if not direct.html_attempts(text, engine_request, which, resolve_soffice):
        if announce:
            print(f"WARN  {display_path(path)}: no HTML engine or browser found for a direct build "
                  "(WeasyPrint, Chrome, Edge...); going through Pandoc", file=sys.stderr)
        return None
    return kind


def direct_defaults(source: Path, metadata_request: list[str] | None) -> dict:
    """The settings `--apply-defaults` gives a direct document: those of the metadata files found for it."""
    import pdfmd_direct.defaults as defaults
    found = find_metadata(source.parent.resolve(), metadata_request, document_stem=source.stem, document=source)
    files = [] if found is AUTO_METADATA_DISABLED or found is None else (found if isinstance(found, list) else [found])
    return defaults.collect([metadata_file_yaml(item) for item in files])


def convert_direct(kind: str, source: Path, output: Path, engine_request: str | None,
                   verbose: bool, debug: bool, apply_defaults: bool = False,
                   metadata_request: list[str] | None = None) -> tuple[Path, bool, str]:
    """Build a `.typ` or `.html` file with its own engine; none of Pandoc's discovery (metadata, preambles, filters,
    fonts, margins, the stamp) applies, since none of it goes through Pandoc."""
    import pdfmd_direct as direct
    import pdfmd_direct.defaults as defaults
    given = direct_defaults(source, metadata_request) if apply_defaults else {}
    text = read_text_best_effort(source)
    prelude = defaults.typst_prelude(given, text) if kind == "typst" and given else ""
    changed = defaults.apply_to_html(given, text) if kind == "html" and given else text
    copy: Path | None = None
    if (prelude or changed != text) and given:
        # beside the original, so what it refers to by a relative path is found; removed afterwards
        copy = source.with_name(f".{source.stem}.pdfmd-defaults{source.suffix}")
        copy.write_text(prelude + text if kind == "typst" else changed, encoding="utf-8")
        vprint(verbose, f"AUTO APPLYDEFAULTS  {display_path(source)}: " + ", ".join(sorted(given)))
    try:
        return _convert_direct(kind, source, copy or source, output, engine_request, verbose, debug, direct,
                               prelude.count("\n"), text)
    finally:
        if copy is not None:
            copy.unlink(missing_ok=True)


def _convert_direct(kind: str, source: Path, built: Path, output: Path, engine_request: str | None,
                    verbose: bool, debug: bool, direct, offset: int, text: str) -> tuple[Path, bool, str]:
    if kind == "typst":
        fonts = fonts_directory() if managed_index() is not None and managed_index().faces else None
        ok, reason = direct.compile_typst(engine_executable("typst"), built, output,
                                          str(fonts) if fonts else None, lambda command, cwd: log_cmd(command, cwd, verbose))
        if built != source:             # the message names the copy and counts the added lines: say it as the file is
            reason = re.sub(re.escape(built.name) + r":(\d+)", lambda found: f"{source.name}:{max(1, int(found.group(1)) - offset)}", reason)
            reason = reason.replace(built.name, source.name)
            reason = re.sub(r"(?m)^(\s*)(\d+)( │)", lambda found: f"{found.group(1)}{max(1, int(found.group(2)) - offset)}{found.group(3)}", reason)
        if ok:
            record_engine("typst")
        if ok:
            vprint(verbose, f"AUTO TYPSTDIRECT  {display_path(source)}: compiled with Typst directly (no Pandoc)")
        else:
            print(f"WARN  {display_path(source)}: typst failed", file=sys.stderr)
        return source, ok, reason
    order = direct.html_attempts(text, engine_request, which, resolve_soffice)
    browser = any(name in dict(order) for name in direct.BROWSER_NAMES)
    advice = (" (a browser would: -e chrome, edge or chromium)" if browser
              else "; no browser was found (Chrome, Chromium, Edge, Brave)")
    if order and order[0][0] == "weasyprint" and direct.has_scripts(text):
        print(f"WARN  {display_path(source)}: the page has scripts and WeasyPrint does not run them, so what they draw "
              "is missing" + advice, file=sys.stderr)
    if order and order[0][0] == "weasyprint" and direct.has_mathml(text):
        print(f"WARN  {display_path(source)}: the page has MathML and WeasyPrint does not draw it, so its formulas "
              "print as flat text" + advice, file=sys.stderr)

    def failed(name: str, reason: str, remaining: list[str]) -> None:
        fake = subprocess.CompletedProcess(args=[name], returncode=1, stdout="", stderr=reason)
        report_engine_failure(display_path(source), name, fake, remaining, debug)

    ok, reason, used = direct.render_html(built, output, order, soffice_convert=lambda src, out: run_soffice_convert(src, out, verbose),
                                          on_failure=failed, log=lambda command, cwd: log_cmd(command, cwd, verbose))
    if ok and used:
        record_engine(str(used))
    if ok:
        vprint(verbose, f"AUTO HTMLDIRECT  {display_path(source)}: {used} (no Pandoc)")
    return source, ok, reason


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
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=source.parent)
    rendered = source.parent / output.name
    if result.returncode == 0 and rendered.exists() and rendered.resolve() != output.resolve():
        rendered.replace(output)
    if result.returncode == 0:
        record_engine("quarto")
    return source, result.returncode == 0, (result.stdout + result.stderr)[-3000:]


# build_parser: lib/pdfmd_args (v3.33.40)


WATCH_INTERVAL = 1.0


# What main() keeps in module globals from the command line: every *_CLI name, and these. -j workers are fresh processes
# (macOS and Windows spawn them, they do not fork), so they get a copy of it (v3.27.3); before that, --line-numbers,
# --fallback, --raw, --keep-source ... did not reach a document built by a worker. tests/test_jobs.py checks that every
# `global` main() sets is covered.
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


def disabled_topics() -> list[str]:
    global DISABLED_WARNED
    value = load_config().get("disabled")
    names = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    names = [str(name).strip().casefold() for name in names]
    try:
        from pdfmd_help import CORE, DISABLEABLE
    except ImportError:
        return []
    wrong = [name for name in names if name not in DISABLEABLE]
    if wrong and not DISABLED_WARNED:
        DISABLED_WARNED = True
        print(f"WARN  config {config_path()}: disabled: {', '.join(wrong)} "
              f"{'is not a feature that can be switched off' if len(wrong) == 1 else 'are not features that can be switched off'}"
              f" (can: {', '.join(DISABLEABLE)}; {', '.join(CORE)} stay on)", file=sys.stderr)
    return [name for name in names if name in DISABLEABLE]


DISABLED_OK_ENV = "PDFMD_ALLOW_DISABLED"     # set by a run that passed the check, for pdfmd's own child processes


def command_line_parser(argv: list[str] | None = None) -> tuple[argparse.ArgumentParser, list[argparse.Action]]:
    """The parser for this run, with the options of switched-off features hidden unless --disabled is on it (or this
    is pdfmd's own child process: the Word route, --doctor --deep, --watch ... pass --no-stamp and the like)."""
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    if "--disabled" in argv or os.environ.get(DISABLED_OK_ENV):
        return parser, []
    try:
        from pdfmd_help import hide
    except ImportError:
        return parser, []
    return parser, hide(parser, disabled_topics())


def refuse_disabled(args: argparse.Namespace, hidden: list[argparse.Action],
                    parser: argparse.ArgumentParser | None = None) -> None:
    """Stop when the command line used an option of a switched-off feature without --disabled. "Used" is a value that
    differs from what the parser gives with no options at all (two flags sharing a dest, --strip-comments and
    --keep-comments, have different defaults of their own); a dest a visible option shares is never refused."""
    if not hidden:
        return
    from_help = __import__("pdfmd_help")
    baseline = vars((parser or build_parser()).parse_known_args([])[0])
    visible = {action.dest for action in (parser or build_parser())._actions if action not in hidden}
    for action in hidden:
        if action.dest not in visible and getattr(args, action.dest, None) != baseline.get(action.dest):
            name = next((item for item in action.option_strings if item.startswith("--")), action.option_strings[0])
            topics = " and ".join(sorted(from_help.topics_of(action)))
            raise SystemExit(f"{name}: the {topics} features are switched off (`pdfmd --setup`, d). Run it once with "
                             f"`pdfmd --disabled {name} ...`, or switch them back on.")


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


def run_main() -> None:
    parser, hidden = command_line_parser()
    args, pandoc_options = parser.parse_known_args(load_package("pdfmd_args").normalise_metadata_options(sys.argv[1:]))
    refuse_disabled(args, hidden, parser)
    if args.bopen is not None:
        try:
            parse_bopen(args.bopen)
        except SystemExit:
            if not Path(args.bopen).exists():
                raise
            args.path = [Path(args.bopen), *(args.path or [])]       # `--bopen notes`: the folder, not a spec
            args.bopen = "all"
        if not args.batch:
            args.open = True
    if hidden or args.disabled:
        os.environ[DISABLED_OK_ENV] = "1"          # pdfmd's own child processes are not refused again
    if args.ascii_stdio:       # pdfmd_lua/ascii.lua's helper: text in, ASCII text out (see pdfmd_flat/asciify.py)
        from pdfmd_flat import asciify
        raise SystemExit(asciify.serve(*args.ascii_stdio))
    if args.trust_lua:
        raise SystemExit(0 if trust_lua(args.trust_lua) else 1)
    if args.path and all(path.suffix.lower() == ".pdf" for path in args.path):
        # Reading a PDF: the unknown flags are batchocr's, and an abbreviation must not
        # swallow one (`-c` is batchocr's --concat and an abbreviation of pdfmd's -cwd).
        reader_parser = build_parser()
        reader_parser.allow_abbrev = False
        for flag in [flag for flag in reader_parser._option_string_actions if len(flag) > 2 and flag[1] != "-"]:
            del reader_parser._option_string_actions[flag]     # `-cwd`: older argparse still abbreviates it
        args, pandoc_options = reader_parser.parse_known_args()
    use_managed_tools()
    provide_writable_places()
    if args.merge:
        # --merge (v3.27.6): one Markdown file that builds alone, = --assemble-only --embed-metadata all
        if args.no_embed_metadata:
            raise SystemExit("--merge embeds everything; it contradicts --no-embed-metadata")
        args.assemble_only = True
        if args.embed_metadata is None:
            args.embed_metadata = ["all"]
    if args.debug:
        args.verbose = True
    args.to_many = None
    if args.to and "," in args.to:
        # `--to png,pdf`: several picture formats from one build (see picture_command)
        wanted = []
        for name in args.to.split(","):
            name = name.strip().casefold().lstrip(".")
            name = DEFAULT_OUTPUT_ALIASES.get(name, name)
            if name and name not in wanted:
                wanted.append(name)
        args.to_many, args.to = wanted, wanted[0]
    if args.to:
        # `--to md`, `--to tex`, `--to typ`: the names of the files, as `default-output:` takes them
        args.to = args.to.strip().casefold().lstrip(".")
        args.to, ascii_asked = split_ascii_target(args.to)
        ASCII_CLI["on"] = ascii_asked
        args.to = DEFAULT_OUTPUT_ALIASES.get(args.to, args.to)
    if args.view:
        if args.to and args.to != "ansi":
            raise SystemExit(f"--view shows the styled terminal text (--to ansi); it cannot be combined with --to {args.to}")
        args.to = "ansi"
        if args.out is not None and str(args.out) != "-":
            args.view = False                         # -o FILE saves it: no pager, nothing shown (one meaning per flag)
    if args.color:
        os.environ[ANSI_COLOR_ENV] = args.color
    if args.width:
        os.environ[ANSI_WIDTH_ENV] = str(args.width)
    if (args.out is not None and str(args.out) == "-" and not args.view and args.path
            and all(path.suffix.lower() == ".pdf" for path in args.path)):
        global PDF_TO_STDOUT_CLI
        args.out, PDF_TO_STDOUT_CLI = None, True     # `pdfmd x.pdf -o -`: the Markdown on standard output (M1ck4's pdfmd pipes so)
    if args.view or (args.out is not None and str(args.out) == "-"):
        raise SystemExit(terminal_view(args))
    if args.path and [str(path) for path in args.path] == ["-"]:
        stdin_build(args)
    global SHOW_FULL_PATHS, STRIP_COMMENTS_CLI, ATTACH_CLI, BUNDLE_CLI, STRIP_KINDS_CLI, KEEP_KINDS_CLI, KEEP_SOURCE_CLI
    global BIB_ATTACH_CLI, CSL_ATTACH_CLI, BUNDLE_PACKAGES_CLI, HYBRID_CLI, CSS_SCOPE_CLI, REWRITE_CLI
    set_kit_cli(args.kit, args.kit_stack)
    REWRITE_CLI = True if args.watch else args.rewrite       # a watch rebuilds the same file on every save
    BUNDLE_PACKAGES_CLI = args.bundle_packages
    STRIP_COMMENTS_CLI = args.strip_comments
    STRIP_KINDS_CLI = comment_kind_set(args.strip_comments_in)
    KEEP_KINDS_CLI = comment_kind_set(args.keep_comments_in)
    BIB_ATTACH_CLI = args.attach_bibliography
    CSL_ATTACH_CLI = args.attach_csl
    CSS_CLI[:] = args.css
    CSS_SCOPE_CLI = args.css_scope
    ATTACH_CLI = args.attach_source
    KEEP_SOURCE_CLI = args.keep_source
    HYBRID_CLI = args.hybrid
    BUNDLE_CLI = args.bundle
    global VERBOSE_OUTPUT
    VERBOSE_OUTPUT = bool(args.verbose)
    AUTO_LOG.reset(dedupe=bool(args.batch) or len(args.path or []) > 1)
    global PAPER_CLI
    PAPER_CLI = args.paper
    INKMD_CLI.clear()
    for flag, key, value in (("family", "family", args.family), ("no_autolinks", "autolinks", False),
                             ("no_html", "html", False), ("allow_unsafe_urls", "safe", False),
                             ("allow_remote_images", "allow_remote_images", True),
                             ("emoji_fallback", "emoji_fallback", args.emoji_fallback)):
        if getattr(args, flag) not in (None, False):
            INKMD_CLI[key] = value
    CODE_CLI.clear()
    if args.line_numbers:
        CODE_CLI["line-numbers"] = True
        if args.line_numbers.isdigit() and int(args.line_numbers) > 1:
            CODE_CLI["line-number-step"] = int(args.line_numbers)
    if args.no_code_wrap:
        CODE_CLI["code-wrap"] = False
    POLISH_CLI.clear()
    configured = config_options()          # the config file's defaults (pdfmd --setup); the command line wins
    POLISH_CLI.update(header=args.header or configured.get("header") or None,
                      footer=args.footer or configured.get("footer") or None,
                      bookmarks=args.bookmarks or bool(configured.get("bookmarks")),
                      attach_links=args.attach_links or bool(configured.get("attach-links")),
                      info={POLISH_INFO_KEYS[name]: getattr(args, f"pdf_{name}")
                            for name in POLISH_INFO_KEYS if getattr(args, f"pdf_{name}")})
    if args.restore is not None:
        restorer = (restore_from_markdown if args.restore.suffix.lower() in (".md", ".markdown")
                    else restore_from_pdf)
        raise SystemExit(restorer(args.restore, args.out.resolve() if args.out else None, args.list_only))
    # -v/--verbose (or --debug) writes full paths, as it always did; otherwise the style is a setting (entry 3ea): --path-style,
    # then the folder settings above the first document, then the config (the folder settings are read at the first input only:
    # the style is one for the whole run).
    global PATH_STYLE, PATH_UP
    SHOW_FULL_PATHS = args.full_paths
    first_input = next(iter(args.path or []), None)
    if first_input is not None and Path(first_input).is_dir():
        first_input = Path(first_input) / "x.md"
    PATH_STYLE, PATH_UP = path_style_settings(args.path_style, args.path_up, first_input, args.verbose)
    global CITEPROC_DISABLED, CACHE_PLOTS_CLI, FUZZY_LOOKUP, SEED_LABELS_CLI, SEED_CALC_CLI, METADATA_PRECEDENCE_CLI, NO_AUTO_CLI
    global PRESET_CLI, GLOBAL_METADATA_CLI
    CITEPROC_DISABLED = args.no_citeproc
    # A CLI switch only: the document's own `pdfmd-options: no-auto` cannot
    # turn off the lookup that is still busy finding that document.
    FUZZY_LOOKUP = not auto_disabled(args.no_auto, "lookup")
    NO_AUTO_CLI = args.no_auto
    global FALLBACK_CLI, MISSING_CLI, STRICT_CLI, ENGINE_CLI, ENGINE_FALLBACK_CLI
    FALLBACK_CLI, MISSING_CLI, STRICT_CLI = args.fallback, args.missing, args.strict
    ENGINE_CLI, ENGINE_FALLBACK_CLI = args.engine, args.engine_fallback
    if args.strict is not None:
        os.environ["PDFMD_STRICT"] = "1" if args.strict else "0"
    global BUILD_TIME_CLI, TIME_FORMAT_CLI, BUILD_LOG_CLI
    BUILD_TIME_CLI, TIME_FORMAT_CLI, BUILD_LOG_CLI = args.build_time, args.time_format, args.build_log
    if args.build_log:
        os.environ["PDFMD_BUILD_LOG"] = args.build_log
    os.environ.setdefault("PDFMD_COMMAND_LINE", shlex.join(sys.argv[1:]))
    if args.build_time is not None:
        os.environ["PDFMD_BUILD_TIME"] = "1" if args.build_time else "0"
    if args.time_format:
        timing = timing_module()
        problem = timing.check_style(args.time_format) if timing else None
        if problem:
            raise SystemExit(f"--time-format: {problem}")
        os.environ["PDFMD_TIME_FORMAT"] = args.time_format
    for value, variable in ((args.csv_rows, CSV_ENV["rows"]), (args.csv_cols, CSV_ENV["cols"]), (args.csv_note, CSV_NOTE_ENV)):
        if value is not None:
            os.environ[variable] = str(value)
    if args.csv is not None:
        os.environ[CSV_ENABLED_ENV] = "on" if args.csv else "off"
    if args.calc is not None:
        os.environ[CALC_ENV] = "on" if args.calc else "off"
    if args.calc_digits is not None:
        os.environ[CALC_DIGITS_ENV] = args.calc_digits
    if args.calc_round is not None:
        os.environ[CALC_ROUND_ENV] = args.calc_round
    if args.calc_subs is not None:
        os.environ[CALC_SUBS_ENV] = "true" if args.calc_subs else "false"
    if args.calc_typeset is not None:
        os.environ[CALC_TYPESET_ENV] = args.calc_typeset
    for style, env in CALC_TYPESET_STYLE_ENVS.items():
        if getattr(args, "calc_typeset_" + style) is not None:
            os.environ[env] = getattr(args, "calc_typeset_" + style)
    if args.calc_noindent is not None:
        os.environ[CALC_NOINDENT_ENV] = args.calc_noindent
    if args.calc_space is not None:
        os.environ[CALC_SPACE_ENV] = args.calc_space
    if args.paragraph_spacing is not None:
        paragraph_spacing_command_line(args.paragraph_spacing)
    if args.calc_align is not None:
        os.environ[CALC_ALIGN_ENV] = args.calc_align
    if args.calc_constants is not None:
        os.environ[CALC_CONSTANTS_ENV] = args.calc_constants
    if args.calc_export is not None:
        os.environ[CALC_EXPORT_ENV] = args.calc_export
    if args.table_keep is not None:
        os.environ[TABLE_KEEP_ENV] = str(args.table_keep)
    for value, variable in ((args.max_asset_mb, "PDFMD_MAX_ASSET_MB"), (args.max_output_mb, "PDFMD_MAX_OUTPUT_MB")):
        if value is not None:
            os.environ[variable] = str(value)
    configured = load_config().get("translit")
    if isinstance(configured, list):
        configured = ",".join(str(item) for item in configured)
    if args.translit is not None:
        translit = args.translit
    elif os.environ.get("PDFMD_TRANSLIT") is not None:
        translit = os.environ["PDFMD_TRANSLIT"]
    else:
        translit = configured
    if translit and translit.strip().casefold() == "list":
        raise SystemExit(0 if translit_report() else 1)
    for problem in set_translit(translit):
        print(f"WARN  --translit: {problem}", file=sys.stderr)
    CACHE_PLOTS_CLI = args.cache_plots or None
    SEED_LABELS_CLI = args.seed_labels
    SEED_CALC_CLI = args.seed_calc
    METADATA_PRECEDENCE_CLI = args.metadata_precedence
    PRESET_CLI, GLOBAL_METADATA_CLI = args.preset, args.global_metadata
    global CACHE_LOCATION_CLI
    CACHE_LOCATION_CLI = args.cache_location
    RAW_CLI.update({"all": args.raw, "off": args.no_raw, "for": list(args.raw_for or [])})
    PAGEBREAK_CLI.update({"kinds": args.pagebreak, "off": args.no_pagebreak})
    LINEBREAK_CLI.update({"kinds": args.linebreak, "off": args.no_linebreak})
    MARKUP_CLI.update({"kinds": args.markup, "off": args.no_markup})
    SHOW_COMMENTS_CLI["on"] = args.show_comments
    FLAVOUR_CLI["name"] = args.flavour
    UNCLOSED_CLI["mode"] = args.unclosed_comment
    GFM_CLI.update({"scripts": args.gfm_scripts, "math": args.gfm_math})
    ASCII_CLI["missing"] = args.ascii_missing
    if args.serve is not None:
        raise SystemExit(serve_command(args))
    if args.api is not None:
        raise SystemExit(api_command(list(args.api)))
    if args.init_reference:
        raise SystemExit(0 if init_reference(args.init_reference) else 1)
    if args.completion:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(newline="\n")          # CRLF in a shell script breaks it in Git Bash and WSL
        sys.stdout.write(completion_script(args.completion))
        raise SystemExit(0)
    if args.user_path or args.add_to_path is not None or args.remove_from_path or args.show_user_path:
        raise SystemExit(user_path_command(args))
    if args.deep and not args.doctor:
        raise SystemExit("--deep goes with --doctor: pdfmd --doctor --deep")
    if args.doctor:
        raise SystemExit(0 if doctor_report(deep=args.deep) else 1)
    if args.cache_info or isinstance(args.clear_cache, str):
        status = cache_command(args)                        # --cache-info, --clear-cache WHAT (pdfmd_cache.manage)
        if status is not None:
            raise SystemExit(status)
    if (args.crop_pad is not None or args.crop_ignore_bottom is not None or args.crop_page is not None) and not args.crop:
        raise SystemExit("--crop-pad, --crop-ignore-bottom and --crop-page go with --crop: pdfmd --crop formula.pdf --crop-pad 1")
    if (args.image_dpi is not None or args.image_quality is not None) and not (args.crop or args.to_many or picture_target(args) in PICTURE_ONLY):
        raise SystemExit("--image-dpi and --image-quality go with --to png, jpg, tiff, eps, ps or svg")
    if args.to_many:
        raise SystemExit(multi_target_command(args))
    if args.crop or picture_target(args) in PICTURE_ONLY:
        raise SystemExit(picture_command(args))
    if args.check_docx:
        raise SystemExit(check_docx_command(args, pandoc_options))
    if args.init is not None:
        raise SystemExit(init_command(args))
    if args.check_ignore and not args.check:
        raise SystemExit("--check-ignore goes with --check: pdfmd --check --check-ignore heading-jump")
    if args.check:
        raise SystemExit(check_command(args))
    if args.check_dependencies:
        raise SystemExit(0 if dependency_report() else 1)
    if args.extract_tables or args.expand_tables or args.extract_inline_csv:
        raise SystemExit(tables_command(args))
    if args.failed and not args.last_build:
        raise SystemExit("--failed goes with --last-build: pdfmd --last-build --failed FILE")
    if args.last_build:
        raise SystemExit(last_build_command(args))
    if args.history or args.history_diff or args.history_restore:
        if args.history_diff and args.history_restore:
            raise SystemExit("--history-diff and --history-restore are different things; pick one.")
        raise SystemExit(history_view_command(args))
    if args.init_backups:
        raise SystemExit(init_backups_command(args))
    if args.history_to_file or args.history_to_notes or args.merge_history:
        if args.history_to_file and args.history_to_notes:
            raise SystemExit("--history-to-file and --history-to-notes are opposites; pick one.")
        raise SystemExit(history_command(args))
    if args.check_fonts:
        ok = True
        for target in (args.path or [Path.cwd()]):
            try:
                document = find_markdown(target)
            except FileNotFoundError as error:
                raise SystemExit(str(error))
            ok = check_fonts(document, args.no_auto, list(args.variable or [])) and ok
        raise SystemExit(0 if ok else 1)
    if args.edit:
        raise SystemExit(edit_command(args))
    if args.init_vscode:
        raise SystemExit(init_vscode_command(args))
    if args.show_config or args.init_config:
        raise SystemExit(0 if config_report(init=args.init_config) else 1)
    if args.presets:
        raise SystemExit(0 if presets_report(args.path[0] if args.path else None) else 1)
    if args.kits is not None:
        raise SystemExit(0 if kits_report(list(args.kits), args.no_auto) else 1)
    if args.which is not None:
        raise SystemExit(0 if which_command(list(args.which), args) else 1)
    if args.check_source:
        raise SystemExit(0 if check_source_command(list(args.path or []), args.recursive) else 1)
    if args.doc is not None:
        raise SystemExit(doc_command(args.doc, args.doc_print, args.doc_path))
    if args.doc_print or args.doc_path:
        raise SystemExit("--print and --path go with --doc: pdfmd --doc readme --print")
    if args.setup is not None:
        raise SystemExit(0 if setup_command(args.setup) else 1)
    if args.install:
        raise SystemExit(0 if install_extra(args.install, bool(getattr(args, "yes", False))) else 1)
    if args.uninstall:
        if args.uninstall.startswith("kit"):
            raise SystemExit(0 if uninstall_kit(args.uninstall.partition(":")[2]) else 1)
        if args.uninstall.startswith("ocr"):
            raise SystemExit(0 if install_ocr_languages(args.uninstall.partition(":")[2], remove=True) else 1)
        raise SystemExit(0 if uninstall_fonts(args.uninstall.partition(":")[2]) else 1)
    if args.batch or (not args.report and len(args.path or []) > 1):
        from pdfmd_batch import prepare_inputs
        prepare_inputs(sys.modules[__name__], args)
    else:
        routed = route_pdf_input(args, pandoc_options)
        if routed is not None:
            raise SystemExit(routed)
        routed = route_text_input(args, pandoc_options)
        if routed is not None:
            raise SystemExit(routed)
        route_ebook_input(args)
    if not pdfmd_routing.quarto_input(args) and not which("pandoc") and not native_possible(args):
        raise SystemExit(PANDOC_MISSING)
    paths = args.path or [Path.cwd()]
    if args.clear_cache:
        if args.path:
            try:
                document = find_markdown(paths[0])
            except FileNotFoundError as error:
                raise SystemExit(str(error))
            plan = plan_scaffold(document, [], args.no_auto, args.metadata_file)
            source = plan.scaffold if plan else document
            local = source.resolve().parent / LOCAL_CACHE_DIRNAME
            status = remove_cache_paths([cache_directory(source), cache_directory(source, local)], [cache_root(), local])
        else:
            status = clear_cache("all")                     # the cache folder and ./.cache/pdfmd (v3.33.74: with sizes)
        if status:
            raise SystemExit(status)
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
    if args.paper and not any(variable.startswith("papersize") for variable in args.variable):
        variables = variables + [f"papersize={args.paper}"]
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
    if args.stamp_store:
        stamp_overrides["store"] = args.stamp_store
    if args.stamp_output:
        stamp_overrides["include_output"] = True
    if args.no_stamp_output:
        stamp_overrides["include_output"] = False
    if args.stamp_partial:
        stamp_overrides["partial"] = True
    if args.no_stamp_partial:
        stamp_overrides["partial"] = False
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
        unknown_kinds = sorted(set(args.embed_metadata) - {*EMBED_ALL, "all"})
        if unknown_kinds:
            raise SystemExit(f"Unknown --embed-metadata kind(s): {', '.join(unknown_kinds)}. "
                             f"Valid: {', '.join(EMBED_ALL)}, all")
        if stop_at != "markdown":
            raise SystemExit("--embed-metadata applies to --stop-at markdown (--assemble-only) only")
        wanted = (set(EMBED_KINDS) if not args.embed_metadata
                  else set(EMBED_ALL) if "all" in args.embed_metadata else set(args.embed_metadata))
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
    target_format, ascii_named = split_ascii_target(target_format)      # `-o notes.ascii.txt`
    ASCII_CLI["on"] = ASCII_CLI["on"] or ascii_named
    if stop_at == "markdown":
        target_format = ASSEMBLED_FORMAT
    elif stop_at == "tex":
        target_format = "beamer" if args.presentation else "latex"
    if args.presentation and target_format != "pdf" and stop_at != "tex":
        raise SystemExit("-p/--presentation always produces a PDF (via Beamer); "
                         "it can't be combined with --to/-o for another format")
    convert_job = None
    if stop_at is None:
        goal = calibre_goal(args.engine, target_format)
        if goal:
            if args.engine is not None and not calibre_asked_first(args.engine):
                print(f"WARN  --engine is ignored for --to {target_format}: Calibre writes it", file=sys.stderr)
            convert_job = start_calibre_job(args, goal, target_format, pandoc_options)
            target_format = "epub"
        else:
            goal = soffice_goal(args.engine, target_format)
            if goal:
                if args.engine is not None and not soffice_asked_first(args.engine):
                    print(f"WARN  --engine is ignored for --to {target_format}: LibreOffice writes it", file=sys.stderr)
                convert_job = start_soffice_job(args, goal, target_format)
                target_format = "docx"
    if (args.engine is not None and target_format != "pdf" and stop_at != "markdown"
            and not (target_format == "odt" and args.engine.strip().casefold() == "pandoc")):
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
                   and all(is_native_engine(engine) for engine in engines))
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

    newest_used: list[bool] = []

    def only_markdown_in(directory: Path) -> Path:
        """The one Markdown file of a folder (what `pdfmd` and `pdfmd '#section'` mean)."""
        markdown_files = sorted(directory.glob("*.md"), key=lambda path: path.name.casefold())
        if not markdown_files:
            hint = ""
            try:
                if not sys.stdin.isatty():
                    hint = " To build Markdown piped in, name it: `pdfmd -` reads standard input."
            except (AttributeError, ValueError, OSError):
                pass
            raise SystemExit("No Markdown files found in the current directory." + hint)
        picking = len(markdown_files) > 1 and (args.newest or priority_enabled(directory))
        if picking:
            markdown_files = source_markdown(markdown_files)
        if len(markdown_files) > 1:
            if picking:
                newest_used.append(True)
                return choose_markdown(markdown_files, args.newest, args.include_never)
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
    # `@` says the same as `#` (`pdfmd report@intro`, `doc@@yield`): an interactive bash and some other shells take a `#`
    # for the start of a comment and never pass it on.
    if len(paths) == 1 and re.search(r"[#@]", str(paths[0])) and not paths[0].exists():
        # The whole string, not .name: a section path (`doc#results/yield`) has a slash.
        base, separator, suffix = re.split(r"([#@])", str(paths[0]), maxsplit=1)
        if os.sep != "/":
            suffix = suffix.replace(os.sep, "/")        # Path turned `doc#results/yield` into `doc#results\\yield` on Windows
        if base and not base.endswith(("/", os.sep)):
            paths = [Path(base)]
        else:
            paths = [only_markdown_in(Path(base) if base else Path.cwd())]
        # `doc#name` asks for `name`; `doc##name` for `##name`, a level-2 heading.
        section_requests += split_section_requests(["#" + suffix.replace("@", "#", 1) if suffix.startswith(("#", "@")) else suffix])
    if args.newest and not newest_used:
        print("WARN  --newest picks among the Markdown files of a folder for a bare `pdfmd` (or `pdfmd '#section'`); "
              "it does nothing with a named file, -b or -r", file=sys.stderr)
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
        run_watch(watch_source, pinned_watch_argv(sys.argv[1:], args.path, paths[0]), args, default_target, scaffold_plan, section_plan)
        return
    if args.report:
        from pdfmd_report import run as run_report
        return run_report(sys.modules[__name__], args=args, default_target=default_target, embed_request=embed_request,
                          engines=engines, need_engines=need_engines, pandoc_options=pandoc_options, paths=paths,
                          stamp_overrides=stamp_overrides, target_format=target_format, variables=variables)
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
            file_no_auto = effective_no_auto(file, args.no_auto)
            requested = ([] if args.metadata_file is None
                        and auto_disabled(file_no_auto, "metadata")
                        else args.metadata_file)
            if requested is None:
                # pdfmd-options.yaml / .metadata: the document names its own
                # metadata files (like -y, but written in the document).
                requested = option_names(frontmatter_pdfmd_options(file), "yaml") or None
            metadata_by_dir[cache_key] = find_metadata(directory, requested,
                                                        document_class=document_class,
                                                        document_stem=file.stem, document=file,
                                                        discover=not (requested is None and discovery_disabled(file_no_auto, "metadata")))
            discovered = metadata_by_dir[cache_key]
            if args.metadata_file is None and discovered is not None and discovered is not AUTO_METADATA_DISABLED:
                paths = discovered if isinstance(discovered, list) else [discovered]
                for path in paths:
                    AUTO_LOG.record_file("YAML", path, args.verbose)
        value = metadata_by_dir[cache_key]
        return None if value is AUTO_METADATA_DISABLED else value
    if args.batch:
        from pdfmd_batch import run as run_batch
        results = run_batch(sys.modules[__name__], args=args, embed_request=embed_request, embeds_preamble=embeds_preamble,
                            engines=engines, metadata_for=metadata_for, need_engines=need_engines,
                            pandoc_options=pandoc_options, paths=paths, stamp_overrides=stamp_overrides,
                            target_explicit=target_explicit, target_format=target_format, variables=variables)
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
        direct_kind = (direct_route(source, target_format, args.from_format, args.no_auto, args.engine)
                       if scaffold_plan is None and section_plan is None and not args.presentation else None)
        if direct_kind is None:
            need_engines(target_format)
        output_extension = output_extension_for(target_format, source)
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
        output = output_file = load_package("pdfmd_routing.output").single(source, output, convert_job, target_format, metadata_for)
        if source.suffix.lower() == ".qmd":
            if args.presentation:
                raise SystemExit("-p/--presentation isn't supported for .qmd -- set the "
                                 "format in the document's own Quarto front matter instead")
            BUILD["engine"], BUILD["failed"] = None, []
            begin_timer()
            with warning_capture() as seen:
                built = convert_qmd(source, output, target_format, variables, pandoc_options)
            results = [finish_build(built, seen, source, [])]
            if results[0][1]:
                # Front matter only: Quarto has its own metadata system, so no
                # metadata.yaml is looked up for a .qmd (see convert_qmd).
                backup_after_success(source, [], args.backup, args.verbose, args.backup_format)
        elif direct_kind is not None:
            BUILD["engine"], BUILD["failed"] = None, []
            begin_timer()
            with warning_capture() as seen:
                built = convert_direct(direct_kind, source, output, args.engine, args.verbose, args.debug,
                                       apply_defaults=(config_options().get("apply-defaults", False) if args.apply_defaults is None
                                                       else args.apply_defaults) not in (False, "false", "False", 0, ""),
                                       metadata_request=args.metadata_file)
            results = [finish_build(built, seen, source, [])]
            if results[0][1]:
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
            results = [convert_one(source, out_dir, args.presentation, args.font, engines, variables, args.slide_level, pandoc_options, None, output_file, [], target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format, output_resolved=True)]
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
            engine_metadata_files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
            preambles = []
            if target_format in {"pdf", *TEX_STANDALONE_FORMATS} or embeds_preamble(source):
                preambles = document_preambles(source, pandoc_options, effective_no_auto(source, args.no_auto), engine_metadata_files)
                announce_preambles(preambles)
            file_engines = resolve_engines(source, args.engine, engines, args.presentation, target_format, engine_metadata_files, args.verbose)
            results = [convert_one(source, out_dir, args.presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, output_file, preambles, target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format,
                                   extra_inputs=(scaffold_plan.files[1:] if scaffold_plan is not None else None),
                                   all_parts=(scaffold_plan.parts if scaffold_plan is not None else None),
                                   cache_cli=args.cache, embed=embed_request, trust_embedded=args.trust_embedded,
                                   self_contained=args.self_contained,
                                   parts_root=(scaffold_plan.directory if scaffold_plan is not None else None),
                                   partial=((scaffold_plan is not None and scaffold_plan.selected is not None)
                                            or section_plan is not None),
                                   source_override=((section_plan.text, section_plan.shifted)
                                                    if section_plan is not None else None),
                                   full_override=(section_plan.full_text if section_plan is not None else None),
                                   calc_text_override=(section_plan.calc_text if section_plan is not None else None), output_resolved=True)]
            if section_plan is not None and results[0][1] and target_format != ASSEMBLED_FORMAT:
                if LAST_WHOLE:
                    print("NOTE  section build: the whole document was numbered and this section kept, so its "
                          "numbers and the references to the rest are the full document's (a reference written "
                          "as raw LaTeX \\ref is not resolved outside LaTeX; use @sec:/@fig: with pandoc-crossref)")
                elif LAST_SEEDED:
                    print("NOTE  section build: references to other sections come from the last full build "
                          "(cache); they are stale if you have since changed the document. This section's "
                          "own heading, figure, table and equation numbers restart at its first one")
                elif LAST_SCANNED and LAST_EXACT:
                    print(f"NOTE  section build: references to other sections ({LAST_SCANNED} labels) come from a draft "
                          "pass over the whole document, so they are exact. This section's own heading, figure, "
                          "table and equation numbers restart at its first one")
                elif LAST_SCANNED:
                    print(f"NOTE  section build: references to other sections ({LAST_SCANNED} labels) are counted "
                          "from the document's sources: approximate where it defines its own macros; a full build "
                          "with the cache on (--cache) first makes them exact. This section's own heading, "
                          "figure, table and equation numbers restart at its first one")
                else:
                    print("NOTE  section build: references to other sections print as ??, and heading, "
                          "figure and table numbers restart from this section's own first one (with the "
                          "cache on -- pdfmd-options: {cache: {aux: true}}, or --cache -- a full build "
                          "first lets later section builds fill the references in)")
            if (scaffold_plan is not None and scaffold_plan.selected is not None and results[0][1]
                    and target_format != ASSEMBLED_FORMAT):
                if LAST_WHOLE:
                    print("NOTE  partial build: the whole document was numbered and these parts kept, so their "
                          "numbers and the references to the rest are the full document's (a reference written "
                          "as raw LaTeX \\ref is not resolved outside LaTeX; use @sec:/@fig: with pandoc-crossref)")
                elif LAST_SEEDED:
                    print("NOTE  partial build: numbers of parts left out come from the last full build "
                          "(--cache); they are stale if you have since added or moved a figure or table there"
                          + (f" (and {LAST_SCANNED} labels counted from the sources fill in what it lacks)"
                             if LAST_SCANNED else ""))
                elif LAST_SCANNED and LAST_EXACT:
                    print(f"NOTE  partial build: numbers of parts left out ({LAST_SCANNED} labels) come from a draft "
                          "pass over the whole document, so they are exact")
                elif LAST_SCANNED:
                    print(f"NOTE  partial build: numbers of parts left out are counted from the sources "
                          f"({LAST_SCANNED} labels); approximate where the document defines its own macros -- "
                          "a full build with the cache on (--cache) makes them exact")
                else:
                    print("NOTE  partial build: references to parts left out print as ??, and figure/"
                          "table numbers restart from this build's own first one (pdfmd-options: "
                          "{cache: {aux: true}} carries them over from the last full build)")
                if scaffold_plan.cuts:
                    print("NOTE  a section or element cut out of a part is numbered from its own start, "
                          "cache or not: its heading, figure, table and equation numbers restart there "
                          "(only whole parts get their numbers from the last full build)")
            if (LAST_SKIPPED and not (LAST_EXACT or LAST_SEEDED or LAST_WHOLE) and results[0][1]
                    and target_format != ASSEMBLED_FORMAT
                    and (section_plan is not None or (scaffold_plan is not None and scaffold_plan.selected is not None))):
                print(f"NOTE  {LAST_SKIPPED} label{'' if LAST_SKIPPED == 1 else 's'} came after a caption in an "
                      "environment pdfmd does not know, so a reference to one outside this build prints ?? rather "
                      "than the number of the heading before it (--seed-labels draft counts them exactly)")
        if args.open and results[0][1]:
            open_file(output)
    if convert_job is not None:
        results = finish_convert_job(convert_job, results, args.verbose)
    failures = [result for result in results if not result[1]]
    for result in results:
        source, ok, error = result
        print(f"{'OK  ' if ok else 'FAIL'}  {display_path(source)}{built_name(result)}{time_label(result)}{engine_label(result)}")
        if args.verbose:
            for line in time_breakdown(result):
                print(line)
        if error:
            print(error)
        if getattr(result, "record_path", None) and (args.verbose or not ok):
            print(f"{'      full record: ' if not ok else 'RECORD  '}{under_home(result.record_path)}")
    if args.batch and args.bopen is not None:
        built = [Path(result.output) for result in results
                 if result[1] and getattr(result, "output", None) is not None and Path(result.output).is_file()]
        picked = [built[index] for index in bopen_indices(args.bopen, len(built))]
        for path in picked:
            open_file(path)
        if picked:
            print(f"OPENED  {len(picked)} of {len(built)} ({args.bopen}): " + ", ".join(path.name for path in picked[:6])
                  + (f", +{len(picked) - 6} more" if len(picked) > 6 else ""))
    if native_auto and not failures:
        offer_native_upgrade()
    if not failures:
        maybe_hint_setup()
    if failures:
        raise SystemExit(1)


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
