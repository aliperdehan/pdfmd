# pdfmd reference

Convert Markdown documents to PDF (or other formats) with Pandoc.


## Examples

```
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
```

## Input formats

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
`\documentclass`...`\begin{document}`...`\end{document}`), so instead
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
(`\bibliography{...}`/`\addbibresource{...}` triggers a bibtex/biber
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

## Older Pandoc, and no network (v3.25.11)

The oldest Pandoc pdfmd is tested with is PANDOC_MIN, 3.1.3 (the claude.ai sandbox's); the suite runs against it, with
a few tests skipped for what an older Pandoc lacks (PANDOC_FEATURES: Word equation tables, caption attributes).
Typst pictures work with it since v3.27.10-11: pdfmd gives Typst PDF builds --root=/ (unless an explicit root is
passed through --pdf-engine-opt), and pdfmd_lua/typst.lua
makes a picture's relative path absolute (that Pandoc runs Typst in its own working folder). The first compile with
an older Pandoc warns once (per version, a marker in the config folder), and --doctor lists what the one installed
does without. The Lua filters work without pandoc.Caption, pandoc.TableBody and
pandoc.log (Pandoc 3.2); a pandoc-crossref built for another Pandoc than the running one is not run (it would leave
?? for the numbers) and a WARN says which release to get. scripts/build_zipapp.py makes dist/pdfmd.pyz, pdfmd and
its packages with bundled pure-Python YAML and pypdf in one file for a machine with no network (it unpacks itself once into
~/.cache/pdfmd/pyz/), and a folder of wheels does the same with pip's --no-index --find-links.

## Packages a document's commands need (v3.27.16; auto kind `texpackages`)

A LaTeX build of a document that uses \ce/\cee/\cf (mhchem) or \SI/\si/\num/\qty/\unit (siunitx) without
loading the package stopped with "Undefined control sequence". tex_package_args adds a guarded load, after
everything else in the preamble: nothing when the package is loaded already (a house package's options win), when
the command is defined some other way, or when the package is not installed. It is a header file, last.

## Header files and header-includes (v3.27.18)

Pandoc puts --include-in-header files and `header-includes:` in one template variable, and the command line wins:
any header file pdfmd adds (the code-wrapping one for a document with code, graphicx for a raw \includegraphics,
the fonts header, preamble.tex, the packages above) dropped the document's own `header-includes` or, without
them, a metadata file's, and the first command from them stopped LaTeX. keep_header_includes runs on the finished
command and puts back what Pandoc would have kept: the document's own (the last input's, when there are several),
else the last metadata file's in Pandoc's order, as a header file of its own. A metadata file's go first (after
the code-wrapping header), where a shared preamble goes; the document's own last but for the packages header. An
--include-in-header or `-M header-includes` of your own replaces them, as in Pandoc.

## Inline calculator (v3.30.4, names and `::: calc` v3.30.6, {subs} v3.30.8)

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
unless they carry an {ans}; both fence spellings work with or without YAML front matter and in every writer. `code`{=calc} is `code`{=}. In a `::: calc` div the paragraphs
that hold a calculation line have no first-line indent and its prose keeps the document's (`calc: {noindent: lines}`, the
default since 3.33.18; true takes it off every paragraph of the div, false gives the whole div the document's own; an `indent=`
on the div, or a nested `::: indent` / `::: noindent` div, wins). Added by
`calc_filter_args()` only for a document that has such a span or div. The settings are
`pdfmd-options: {calc: {enabled, digits: 4sf|2dp, round: even|away, subs, typeset: true|display, noindent, space, align}}` (`calc: off` is the short form), --calc /
--no-calc, --calc-digits, --calc-round, --calc-subs / --no-calc-subs, --calc-typeset [inline|display] / --no-calc-typeset, --calc-typeset-upright, --calc-typeset-italic, --calc-noindent [lines|all] / --no-calc-noindent, --calc-space, --calc-align or --setup; round() sends an exact half to the
even digit (R, Python) unless away. Needs Pandoc (the built-in renderer shows the source as written). README "Calculations inside the text";
docs/recipes.md 1.11. Partial builds replay the skipped parts' defining calc statements as hidden content at their real
positions, including gaps in `report#20+40`. Each selected part sees the same nearest definition above, else first below,
as the full build; document-level constants retain their place before the text. `seed-calc: off` disables that context.
A part's own leading front matter remains discarded.

## Lists of figures and tables

Pandoc metadata `lof: true` and `lot: true` requests lists of captioned figures and tables.
LaTeX prints captions with page numbers; add `toc: true` for reliable pdfLaTeX passes with Pandoc 3.13.
Pandoc 3.13's Word writer inserts fields to update in Word; 3.1.3 inserts none. Neither tested Typst
writer prints these lists. See docs/recipes.md 3.5 for a recipe and the writer limitations.

## A byline without a title

With Pandoc's default LaTeX, Typst and HTML templates, author/date are not printed without a title.
pdfmd emits one NOTE: “author/date not printed: no title (add `title:`)”.
Word, ODT and EPUB print them anyway. Custom templates, defaults files, kits and project filters are not diagnosed.

## Paragraph indent for a stretch of text (v3.30.0)

a fenced div `::: {indent=false}` (also `indent=true`, `indent=2em`; `::: noindent`, `::: {.noindent}`, `.indent`;
the value may sit in the class word: `::: indent=3in`, `::: .indent=3in`, `::: indent-3in`, `::: {.indent-3in}`, and a
near miss such as `.indent3in` gets a WARN) sets the first-line indent of the paragraphs inside it and puts the document's own back at the closing `:::`
(pdfmd_lua/indent.lua, added by `indent_filter_args()` only for a document, or a part, that has such a div): LaTeX
and Beamer in a `\begingroup` ... `\endgroup`, Typst a `first-line-indent` rule, HTML a `text-indent` style; the
Markdown writers keep the div, the others drop the setting with a NOTE. docs/recipes.md 1.9.

## The space between paragraphs (v3.33.58)

`pdfmd-options.paragraph-spacing` (also the config and pdfmd --setup) or `--paragraph-spacing LENGTH`: what a paragraph
break adds to the line spacing, a length (pt, mm, cm, in, em), 0 or auto (the default: each engine's own). LaTeX and
Beamer get `\setlength{\parskip}` in a header file, Typst `#set par(spacing: <leading> + X)` (pdfmd_lua/typst.lua); with
`indent: true` Typst's spacing is its leading, as LaTeX drops parskip then. The HTML engines are not given it
(pdfmd_paragraph). docs/recipes.md 1.9.

## Hidden content

Plain `::: hide` / `::: {.hide}` divs and `[text]{.hide}` spans are removed after pdfmd's filters
read them, for every writer and the native tier. HTML drops the content from the file. Calc names defined inside remain
available outside (calculations require Pandoc). A referenced hidden label produces one WARN naming it, for links,
Pandoc cross-references and LaTeX reference commands. `--show-hidden`, `pdfmd-options.show-hidden` and its `--setup` row
print plain hidden content as ordinary content (default off), while `::: {.calc .hide}` and `.calc .hidden` remain
calc's silent statement forms. Plain `.hidden` divs and spans are left alone because Quarto uses them for math macros (for example,
`$$ \def\RR{{\bf R}} $$` inside `::: {.hidden}`). The source attachment retains the original blocks and spans and
warns that the hidden content travels in it,
with `--strip-comments-in hidden` as the remedy. No warning with `show-hidden` on or the `hidden` kind stripped.

## Typst's line spacing (v3.33.73)

`pdfmd-options.typst-line-spacing: latex | pandoc` (also metadata files, folder settings, config and `--setup`) selects
LaTeX's line pitch (`latex`, the unchanged default) or Pandoc's own Typst spacing (`pandoc`, opt-in). With `pandoc`, pdfmd
adds no text-edge, leading or paragraph-spacing rules; the template controls them.

In the default `latex` mode, pdfmd_lua/typst.lua puts lines `linestretch` x LaTeX's \baselineskip for the `fontsize` apart in Typst, in any font
(`#set text(top-edge: 0.7em, bottom-edge: "baseline")` and `#set par(leading: ...)` at the top of the body); without
paragraph-spacing or `indent: true` a paragraph break adds Typst's own 0.55em. A CSL bibliography's `entry-spacing`
adds that many line pitches between entries, including fractions such as 2.5 and 0.5; zero adds no extra line.
Without that attribute, paragraph spacing is kept. docs/recipes.md 1.9.

Typst calls immediately followed by literal `(` or `[` are escaped for older Pandoc writers,
including calls introduced by citeproc (an italic volume followed by an issue). Writers that already
escape them keep their output unchanged. A Pandoc whose Typst writer wraps a long heading over several
source lines (3.1.3) gets `--wrap=none`, so the heading cannot spill into the following paragraph; Typst wraps it on the page.

## Page breaks (v3.27.13, off unless asked since v3.27.15)

`pdfmd-options.pagebreak` (true, or a list of families: comment, tex, html, div, typst, word; also the config and
pdfmd --setup), `--pagebreak [KIND ...]` and `--no-pagebreak` add pdfmd_lua/pagebreak.lua to every Pandoc route,
before raw.lua. A block that is only a page break, in a chosen family's spelling (the comments
<!-- pagebreak|page-break|newpage|new-page --> and <!-- pdfmd: pagebreak -->; \newpage, \pagebreak[n],
\clearpage, \cleardoublepage; a CSS-break or class="pagebreak" div or hr; an empty `::: pagebreak`; a raw Typst
#pagebreak(); a raw Word break), becomes the target's own: LaTeX \newpage{}, Typst #pagebreak(weak: true), a CSS
break div for HTML/EPUB/WeasyPrint, a Word break, an OpenDocument paragraph in the Pagebreak style (added to the
reference pdfmd builds, pdfmd_office/odt.py), ConTeXt \page, ms .bp, a form feed in text, <!-- pagebreak --> in
GitHub Markdown. A spelling in the target's own language stays as written; slides drop it with a NOTE. Without
the option every writer keeps only its own spelling, as before. The built-in renderer always read the comment and
TeX spellings itself (PAGE_BREAK_RE, PAGE_BREAK_COMMENT_RE); tests/test_pagebreak.py holds the one list both are
checked against.

## Math in WeasyPrint (v3.27.12, v3.28.11, v3.28.46)

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

## Tables in an HTML engine's PDF (v3.28.3)

Pandoc's own page style is for a screen: a table is a full-width block that scrolls sideways, and a word may
break anywhere. On paper Calibre cut a caption off at the width of a narrow table and WeasyPrint set it a syllable
a line. While that style is in (no --css of your own), a table is a table again, at its natural width and
centred as LaTeX sets it; Calibre's caption is up to 4in wide as in LaTeX. WeasyPrint has no max-content width:
its caption is as wide as the table, which is at least 4in, and breaks between words. A numbered equation (the
LaTeX filter's three-cell table) spans the line with its number at the margin, without a table's rules.
WeasyPrint's rules go into `header-includes`, so an --include-in-header of your own replaces them, as it
replaces the document's.

## A file's properties (v3.28.5)

A Word, OpenDocument or PowerPoint file carries none of pdfmd's own settings among its custom properties (Pandoc
writes every metadata key it does not know there, and pdfmd hands its filters folders of this machine that way:
`pdfmd-office-path`, `pdfmd-raw-cache`), and a Word or PowerPoint picture's description names a file of pdfmd's
cache, the temporary folder or the home folder by its name alone. When a house style's cover takes the title and
authors out of the metadata (nulabreport), the file's properties keep them: a Calibre, WeasyPrint, Typst (0.12 and
later) or LibreOffice PDF's Title and Author, a Word or OpenDocument file's Title and Author.
A title or authors with LaTeX in them (`\emph{trans}`) keep its words in every PDF's Title and Author, a LaTeX
engine's included (v3.28.6: Pandoc leaves raw LaTeX out of `title-meta`, hyperref's pdftitle).

## Links Typst would stop on (v3.27.11)

LaTeX and HTML only warn about a link to an anchor the document does not have; Typst stops the build. For Typst (a
PDF or a .typ file) pdfmd_lua/typst.lua runs last and makes such a link its text, with one WARN naming the anchors.
Pandoc's Typst writer labels headings, divs, spans, figures and tables; a link to another element's id is text too.

## Images LaTeX cannot read (v3.25.7; the package pdfmd_images)

LaTeX reads PDF, PNG and JPEG, not SVG. In a LaTeX build pdfmd converts each SVG a document names -- a Markdown
image, a raw `\includegraphics{a.svg}` or `\includesvg{a}` -- once, with the first working converter (rsvg-convert,
Inkscape, cairosvg, svglib, LibreOffice, Typst, resvg), keeps the PDF (a PNG from resvg) in ~/.cache/pdfmd/images by the file's content, and the
Lua filter pdfmd_lua/images.lua puts it where the document wrote the SVG. A cached PDF is reused immediately;
a cached PNG fallback is reused only after the currently available vector converters fail (or none is installed). A Markdown SVG is left to Pandoc when
rsvg-convert is installed (Pandoc converts it itself). A raw `\includegraphics` also gets graphicx, which Pandoc
only loads for a Markdown image (a PNG in one failed with "undefined control sequence"). Word builds use the
same chain for PNG, leaving Pandoc’s own conversion in place when rsvg-convert is installed. Without any
converter there is one WARN naming the file and what to install. A remote image (http/https) in a Markdown image is fetched
once into ~/.cache/pdfmd/images/remote (PNG, JPEG, SVG, PDF; seven days; an older copy is kept if the fetch
fails), which is what makes it work with a Pandoc built without HTTP support (Homebrew's is) and for an SVG badge;
with no network there is one WARN and Pandoc leaves the description. `--no-auto svg` and `--no-auto remoteimages`
turn the two off.

## No Pandoc, or no PDF engine (v3.20.0)

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
See normalise_gfm() in lib/pdfmd_native and the native renderer in lib/pdfmd_engines/native.py.

`--install core` (also `core:typst`, `full`) installs Pandoc and Typst: 35 MB and 15 MB download,
about 50 MB together. `--install core:tex` (also `cortex`) installs Pandoc and Tectonic: 35 MB and
10 to 22 MB download. Tectonic fetches the TeX files a document needs on first use and then caches them.

## Finding a document by name

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

## Output formats

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
LibreOffice. Found on PATH, in calibre.app or in Program Files\Calibre2.
`pdfmd --install calibre` defaults to the available package manager, including without a terminal or with
`PDFMD_NO_PROMPT=1`; if none is available, it uses the SHA-256-checked GitHub download. One line names the method.
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
--metadata-file, or a raw ``\usepackage{geometry}``/``\geometry{...}``
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
characters, so a TeX command set in text mode (`\geq` from a `$...$` that
Pandoc did not take for math) only shows up as a missing-glyph line of
the build. -f/--font, or the document's own `mainfont:`, always wins
outright over both and is never retried.

A `$...$` whose closing `$` is directly followed by a digit (`$\geq$3`,
`$\pm$10`) is not math to Pandoc (it keeps "costs $5 and $10" as text);
pdfmd says so before the build, WARN `file:line`, and what to write
instead (`$\geq 3$`). It is the usual cause of the retry above.

## Text in other scripts (v3.23.0, lualatex/xelatex/tectonic)

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
own scripts (ucharclasses, \newfontfamily, xeCJK, \babelfont,
CJKmainfont, mainfontfallback) is left to itself unless
`pdfmd-options: {unicode: true}`; `--no-auto unicode` turns it all off.
Fonts a build cannot load are dropped and the build retried without them.
Code is checked against the monofont the same way: Typst gets the missing
characters' fonts as its `codefont` list, WeasyPrint as a CSS font stack; under
LaTeX inline code and
code blocks get their own missing characters set in a fallback font (a code
block that needs one becomes a fancyvrb Verbatim, losing its syntax
highlighting); math is left to unicode-math.
Emoji under lualatex/xelatex/tectonic, which cannot draw colour fonts directly, become
pictures: the PNG of each emoji sequence (flags, skin tones, ZWJ families,
keycaps, found through the font's own ligatures) is read out of the colour
emoji font (`--install emoji`, or a system Noto Color Emoji) into pdfmd's
cache and included at text height. XeLaTeX and Tectonic warn with the emoji and engine name when
no extractable picture is available, suggesting Typst or the native renderer (`--engine md2pdf`).
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
LaTeX native in those outputs: mhchem \ce and siunitx \si/\SI/\num as text and Word math,
equation environments as Word equations with numbers, raw figure/tabular via Pandoc's LaTeX reader,
\ref/\cref/captions numbered from the .aux of a PDF build made once in the cache
(`office: {labels: off}` counts instead). What remains (tikz, chemfig, unknown macros, rejected math,
PDF/EPS pictures) is compiled in the document's own preamble (fragments.py: one fragment per page via
`preview`, cropped, SVG + 300 dpi PNG with the depth for baseline alignment, cached by content under
~/.cache/pdfmd/office/) between two runs of the filter, and a .docx is finished by docx_post.py (SVG
beside the PNG, baseline, width). A house style's macros are declared in `office.lua` / `<name>-office.lua`
(`office: {profile: F}`, `--no-auto officeprofile`): ignore = {...}, commands = {name = function(args)...},
pandoc = function(doc).
The office replace mapping may use metadata in its values:
`office: {replace: {NULAB-KICKER: "$course$ $term$"}}`. Word XML parts (headers and footers included) and
OpenDocument content/styles use the built document's metadata, including an office profile's changes;
effective metadata supplies other writer variables. `$$` gives a literal dollar; missing/empty fields give
empty text, spaces collapse to one and ends are trimmed in values containing dollars. Values without dollars
keep their literal text and spacing. Metadata text is XML-escaped.

Targeting `latex`, `beamer`, or `context` (--to, or an -o/--out file
ending `.tex`) produces a complete, standalone document -- the same
`\documentclass`...`\begin{document}`...`\end{document}` a direct PDF
render goes through, not a bare Pandoc-LaTeX fragment that only compiles
once pasted into a preamble of its own -- so the same margin/mainfont/
monofont defaults above apply, and a project's own discovered preamble
(PREAMBLE_FILENAMES beside the document, e.g. `preamble.tex`) and
`header-includes`/`pdfmd-options` front matter are included the same way
they would be for a PDF made through that same writer, via
`--include-in-header`. `--no-auto standalone` (or `pdfmd-options:
no-auto: [standalone]`) turns off just the `--standalone` addition, for
the fragment-only behavior other non-PDF targets still have by default
-- e.g. a `.tex` meant to be `\input`/`\include`d into another
document, not compiled on its own. One thing this can't reproduce: the
PDF path's missing-glyph detect-and-retry between `mainfont: STIX Two
Text` and `mainfont: DejaVu Serif` needs an actual compile to check
against, which nothing here performs, so the emitted document keeps
whichever of the two it tried first (PREFERRED_FONT, unless the document
or -f/--font already names one) -- override it by hand with -f/--font or
by editing the emitted `\setmainfont` line if that turns out to be the
wrong one for a particular document's glyphs.

## HTML output and a default format (v3.19.4)

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

```
pdfmd-options:
  html:
    self-contained: true   # one file, everything inlined
    standalone: true       # a full page, resources left linked
    math: mathml           # mathml | mathjax | katex | webtex | plain
    css: style.css         # a name or a list, relative to the document
```

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

## Stopping early (--stop-at, v3.19.0)

A build is a pipeline -- the document's parts are joined into ONE
Markdown text, Pandoc turns that into a standalone .tex, a LaTeX engine
turns the .tex into the PDF -- and `--stop-at STAGE` ends it after a
stage, everything else running as normal (discovery, parts mode,
sections, report/book, batch):

```
pdfmd report --stop-at markdown     -> report.assembled.md
pdfmd report --assemble-only        (same thing)
pdfmd report -o out.assembled.md    (the suffix means it too)
pdfmd report --stop-at tex          -> report.tex  (== --to latex)
```

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
(what the text points at -- images, files a preamble `\input`s, data --
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

`````
````{=pdfmd}
type: lua-filter
name: report.lua
sha256: ...

<the filter's source>
````
`````

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

```
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
```

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
`\verb`, `\url`, verbatim environments and `% !TEX` lines are text),
bibliography (the text between a .bib's entries), csl (XML comments),
metadata (YAML `#` comments and the file's own quoting and layout: the merged
text cannot hold them, so the attachment stores each metadata file and the
document's front matter as written and --restore writes them back byte for
byte; v3.25.13). --strip-comments-in KINDS / --keep-comments-in KINDS do the
same per run. The additional kind `hidden` (alias `hide`) removes plain hide divs and spans from the assembled or attached
copy, keeping calc-hide statement blocks. It is off by default, including with `strip-comments: true` and
`--strip-comments`: name it explicitly (`[markdown, hidden]`, `{hidden: true}`, `--strip-comments-in hidden`);
`--keep-comments-in hidden` keeps it. The existing setup row offers hidden alone or Markdown plus hidden.
If stripped definitions supply calculator names used outside the hidden content, one NOTE names the names the restored
source will not define. Lua filters are never touched. The data files of `.csv`
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
recorded. Raw LaTeX `\includegraphics{...}` in the Markdown or the preamble counts
like a Markdown image (v3.22.8); one in a stored .tex file is stored with --bundle.
(v3.28.13) The global metadata file (pdfmd --setup) is the building machine's, not
the document's: the source layers it lowest, as a build does, and --restore and
--unpack leave it out with one line naming its keys. A metadata file from outside
the document's folder comes back in outside/, with the -y list that layers it.

(v3.28.15) A PDF with its source attached also carries, without any bundle setting,
the files the text reads and never the images: `bundle: sources`, the new default
(the LaTeX files it \inputs, the data its macros read, listings; the PDF itself
holds the pictures and --restore takes them out of it, those only an \input'ed
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
from Markdown images, `<img>`, `file="..."` CSV tables, \includegraphics,
\input, pgfplots tables, listings, and any word that is a relative file name
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
figure's .tex that \inputs its raw data), and an `\input` that only the
machine's TeX tree finds (`kpsewhich`, outside the TeX distribution: a
compound library installed beside a house style) is stored and restored
beside the document. `--bundle-packages` / `pdfmd-options.bundle-packages`
also stores the packages and classes a preamble loads from that tree and the
graphics they name, so a machine without the house style builds the same;
without it they are recorded (name, version) and restore says what is
missing. The manifest also records the fonts the metadata names and what
made the PDF (pdfmd, pandoc, the engine). Data a macro builds the name of
(`data\i.csv` in a loop) cannot be found: `--bundle all` is the fallback.

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
{heading} is the same) {date} {title} (a comma inside a field is written \,;
characters Helvetica cannot draw are reduced to their base letter or `?`);
--attach-links attaches the local files the document links to
(`linked/PATH`) with a paperclip in the margin beside the link; --pdf-title,
--pdf-subject, --pdf-author and --pdf-keywords set the PDF's properties without
touching the document; --paper SIZE is `-V papersize=SIZE` and also sets the
## built-in renderers' page. The built-in renderer's own options are flags too

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
itself runs in, so a preamble's own raw LaTeX `\input{...}` and a
metadata.yaml's own relative `bibliography:`/`csl:` paths can live in that
same `metadata/` folder and still resolve -- pdfmd adds `--resource-path`
pointing back at the document's own directory in that case, so the
document's own relative image paths keep resolving too.
With `--no-citeproc`, native Typst omits the bibliography block and heading when there are no citations, unless
`nocite` or `full-bibliography: true` explicitly requests uncited entries. Cited lists keep Typst's automatic title
("Bibliography" in English); `reference-section-title` names the citeproc list. Bibliography and CSL names are resolved
through that resource path and written literally. The PDF build's `--root=/` also reaches bibliography files from parent
layers and cached copies holding clash winners. Citeproc and LaTeX's natbib/biblatex paths keep their existing behaviour. A standalone `--to typst`
export keeps absolute resource names; compile it with `typst compile --root=/ file.typ file.pdf`. Direct `.typ` inputs
keep Typst's own project root.

## Reader selection for a Markdown source

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

## CSV/TSV table inclusion

A fenced Div with class `csv` --

```
::: {.csv file="data.csv"}
:::
```

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

## Code blocks (v3.25.3; pdfmd_lua/code.lua, LaTeX engines)

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

## Tables to CSV and back (v3.25.2; the package pdfmd_tables)

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

## A long document in parts (parts mode)

A document too long to edit comfortably as one file can be a scaffold
(`report.md`: front matter only) plus a `parts/` or `sections/` folder
of ordinary Markdown files, each starting with its own heading:

```
report.md
parts/10-introduction.md  20-methods.md  30-discussion.md
```

Turn it on once, in a shared metadata.yaml (or the scaffold's front
matter), so the content files carry no typesetting at all:

```
pdfmd-options:
  parts: auto
```

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

## One section of any document (`pdfmd doc#NAME`)

Without parts mode, `pdfmd doc#onlyapart` builds just the section whose
heading is "Only a Part": from that heading to the next heading of the same
or a higher level (its subsections come with it). Headings are written
either way -- `## Title` or a line underlined with `===`/`---` -- and are
named like files are found (see "Finding a document by name"): case,
spaces, `_`, accents and script do not matter (`onlyapart`, `only_a_part`,
`Only a Part`), a unique start works with a WARN (`doc#only`), and so does
the heading's own `{#id}` (`doc#sec:methods`). Beyond that:
```
doc##name        a level-2 heading (the number of # is the level)
doc#parent/name  a heading under another (`doc#results/yield`)
doc#a+b, a,b     several, built in document order, each once
#name            no document name: the folder's only Markdown file
```

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

## The global config file (v3.23.6)

~/.config/pdfmd/config.yaml ($XDG_CONFIG_HOME, %APPDATA%\pdfmd; PDFMD_CONFIG
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

## The cache (`pdfmd-options: {cache: {aux: true}}`, or --cache)

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
whatever the document defines itself; \pageref stays `??`. auto (default) | aux | scan | draft | off.

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
\ref, a citation the bibliography lacks, a footnote without text, a skipped heading level, a fence or comment
never closed, front matter that does not parse. The reading is in the pdfmd_check package; the exit code is 1 on an
error (a warning too with `--strict`); `--check-ignore`, `pdfmd-options.check-ignore` and
`<!-- pdfmd-check: ignore CODE -->` turn checks off.

`pdfmd --install diagram` fetches D2, Graphviz and resvg; `--install diagram:resvg` fetches only resvg
(about 3 MB). Its release executable for this OS/architecture is checked against GitHub’s SHA-256
and kept in pdfmd’s tools folder; delete that executable to remove it (as for D2).

A fenced ```mermaid, ```d2 or ```dot block (v3.26.16) is drawn by mmdc, d2 or dot when installed and replaced by the
picture in the format the output takes (pdfmd_lua/diagram.lua); `--no-auto diagrams` leaves the code.
D2 and SVG-only Graphviz use the same converter chain as SVG images for PDF/PNG (LaTeX/Word/OpenDocument):
rsvg-convert, Inkscape, cairosvg, svglib, LibreOffice, Typst, resvg, in that order, falling through on failure.
Typst makes a vector PDF for LaTeX on a page the SVG’s own size with no margin, or PNG for Word. It uses
pdfmd’s fonts folder, a root containing the SVG, and the Typst on PATH (else the managed tools folder).
resvg makes PNG for either target when earlier converters are missing or fail. `image-dpi` in `pdfmd-options`,
`--image-dpi N` or `--setup` controls raster SVG conversion and Graphviz PNGs (192 by default, preserving
existing output); exported pages keep their default 300. It also participates in raster cache keys.
A missing converter leaves the diagram as code with a warning naming the conversion, Typst and resvg among
the choices; an installed converter’s failure is reported separately. `--doctor` lists the chain and all
converters found. Existing rsvg-convert/Inkscape output is unchanged at the default resolution.
Each warning uses that diagram's own error, never another tool's success message. A tool run may take
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
HTML output has no cache: a bad location warns even when `--cache` or metadata requests caching.
The same location words work in metadata, config and `--cache-location`: global (also root, user, home, central),
document (also local, folder, here, doc, self-contained). Case and surrounding spaces are ignored.

`pdfmd --cache-info` (v3.33.74, lib/pdfmd_cache/manage.py) shows each part's size and the stale part (a
document cache or build records whose recorded document is gone); `--clear-cache builds|documents|stale|all`
clears one part, never following a link; `--doctor` notes a cache over `cache.max-mb` (config, default 1000).

In parts mode the cache also lets a part built alone see the rest: its
labels (\ref/\cref to a table in a part left out) are taken from the last
full build's .aux instead of printing ??, and at the start of every
selected part LaTeX's counters (section, figure, table, equation,
footnote, reaction) jump to what they were there in that build, so
`report#discussion+appendix` shows "V. DISCUSSION" and "VIII. APPENDIX"
as the full report does. Each part of a cache build starts with a raw
`\pdfmdpart{key}` line that records or restores the counters. The numbers
are those of the LAST full build: stale if figures or tables were added
or moved there since (pdfmd says so). A part's own labels are never
overridden.

A section or element of an ordinary document (`pdfmd doc#NAME`) gets the
labels half of this: with the cache on and the whole document built before,
its `\ref`s to the rest of the document read the last full build's numbers
instead of printing ??. Its own headings, figures, tables and equations
are still numbered from its first (there is no counter marker in a document
that is not in parts mode), and a label the section defines itself is its
own. pandoc-crossref leaves `\ref{..}` in LaTeX output, which is what makes
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

## Suppressing pdfmd's own defaults, and the `pdfmd-options:` front-matter block

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

```
---
pdfmd-options:
  no-auto: [monofont, margin]
  pdf-engine: lualatex
---
```

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

## The hybrid PDF and single files that carry their data (v3.25.10)

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

## Versions: --history, --history-diff, --history-restore, --init-backups (v3.25.9)

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

## Build-provenance stamping (--stamp)

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
NAME.sty` and that file's own `\ProvidesPackage` line -- a named
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
all); and the old \hypersetup-injection approach (a second
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

```
---
pdfmd-options:
  stamp:
    packages: [nulabreport]
    mode: history
    scope: report
---
```

An explicit --stamp/--no-stamp/--stamp-mode/--stamp-packages/
--stamp-scope/--stamp-output on the command line always wins over
front matter, field by field.

## Automatic source backups (--backup, v3.8.0; formats v3.9.0)

Off by default. After every successful compile (single-file, batch,
report/book chapter, .qmd, direct .tex, office), copies the source into
`.backups/` beside it (v3.25.2: a hidden folder; an existing `backup/`, `backups/` or
`.backup/` is kept using; the first time, a note says where the copies are). Runs after the BUILD NOTES stamp, and writes
nothing when the newest existing snapshot already matches (ignoring the
stamp's own lines). --no-backup forces it off for one run. Same front-
matter/metadata-file cascade as `stamp:` above, as a bare `true`/
`false`, a directory name, or the full form:

```
---
pdfmd-options:
  backup:
    dir: backup      # relative to the document; default `.backups`
    format: dashed   # see below; default `compact`
    keep: 30         # newest N plain snapshots; 0 = none, negative = all (the default)
    pdfs: 5          # newest N built PDFs; 0 = none (the default), negative = all (v3.32.42)
---
```

`format:` (or --backup-format for one run) is a preset or a template:

```
compact  report.md.bak.20260924091500      (default)
dashed   report.md.bak.20260924-091500
stem     report_20260924-091500.md         (opens in its own app)
suffix   report.md.20260924-091500.bak
short    report.md.09-24_09-15-00.bak
custom   any mix of {name} {stem} {ext} and strftime codes,
         e.g. "{stem}-v%Y%m%d-%H%M%S{ext}"
```

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

## Kits (--kit, --kits, --install kit:SOURCE; v3.31.34 on)

A kit is a folder with a `.kit` (or `NAME.kit`) file that packs a pipeline: a LaTeX class or package, its Lua filter,
default metadata, a citation style. `--kit NAME[:MODE]` or `pdfmd-options: {kit: ...}` chooses one; its folder is on
TEXINPUTS (for Tectonic, -Zsearch-path, v3.32.6), so nothing is installed into TeX. `pdfmd --install kit:owner/repo`
fetches the kits of any repository (v3.32.7; nothing in it is run), `--kits` lists them. A kit may switch off pdfmd's own
margin, font or table-width defaults with `no-auto:` (v3.32.8), and a kind of universal markup with `markup-off:`
(v3.33.68). The README's Kits section is the full description.
