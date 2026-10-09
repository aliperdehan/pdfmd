# pdfmd recipes

The README says what pdfmd is; this is how to get things done with it. Each recipe is a problem, the commands, what
they do, and where the README explains more. Every command works from the folder that holds the file;
`pdfmd --doctor` shows what is installed, `pdfmd --help` is one short page and `pdfmd --help all` the whole list of
options (`pdfmd --help tables`, `source`, `history`, `output`, `modes`, `raw`, `fonts`, `setup`, `debug` one subject at a time).

**Contents**

1. [The basics](#1-the-basics): one document, the name, formats, opening, watching
2. [A project with a house style](#2-a-project-with-a-house-style): metadata, preamble, filters, defaults
3. [Long documents](#3-long-documents): a folder of chapters, one document in parts, sections, splitting
4. [Tables](#4-tables): CSV tables, extracting, choosing, ignoring
5. [Code, images and pieces that are not Markdown](#5-code-images-and-pieces-that-are-not-markdown)
6. [Other inputs](#6-other-inputs): LaTeX, Word, HTML, Typst, Quarto, text, PDF
7. [Other outputs](#7-other-outputs): Word, OpenDocument, HTML, Typst, slides, the editable PDF
8. [The PDF that carries its source](#8-the-pdf-that-carries-its-source)
9. [History, backups and build notes](#9-history-backups-and-build-notes)
10. [Fonts, scripts and emoji](#10-fonts-scripts-and-emoji)
11. [Finishing a PDF](#11-finishing-a-pdf): bookmarks, headers, metadata, attachments
12. [Speed](#12-speed): the cache, watching, parallel builds
13. [The tools around it](#13-the-tools-around-it): editor, VS Code, completion, setup, the config file
14. [When something looks wrong](#14-when-something-looks-wrong)
15. [Option reference by task](#15-option-reference-by-task)

---

## 1. The basics

### 1.1 Build the document of this folder

```sh
cd ~/notes/lecture        # a folder with one Markdown file in it
pdfmd                     # finds it, finds its metadata, preamble and filters, writes lecture.pdf beside it
```

With a single `.md` in the folder you never need the name. With several it stops and says so: name one
(`pdfmd lecture`), convert all separately (`-b`) or join them (`-r`).

### 1.2 Name a document loosely

```sh
pdfmd lecture             # lecture.md  (the .md is optional)
pdfmd lect                # a unique start of a name or title works, with a warning saying what it matched
pdfmd glyukoza            # finds Глюкоза.md: case, spaces, accents and script do not matter
pdfmd ~/notes/lecture.md -d      # build it, but put the PDF in the current folder (-d)
pdfmd --no-auto lookup lect      # exact names only
```

A name that fits two documents is an error, never a guess. Names in other scripts: see [10.4](#104-find-a-document-by-a-name-in-another-script).

### 1.3 Another format

The format comes from the extension of `-o`, or from `-t`:

```sh
pdfmd lecture -o lecture.docx
pdfmd lecture -o lecture.odt
pdfmd lecture -o lecture.html --self-contained       # one file, images and CSS inside
pdfmd lecture -t typst -o lecture.typ
pdfmd lecture -o lecture.tex                         # a complete .tex you can compile yourself
pdfmd lecture -o lecture.epub
pdfmd slides -p                                      # Beamer slides: each heading starts a slide
```

To make HTML the default for a document or a folder: `pdfmd-options: {default-output: html}`.

### 1.4 Choose the PDF engine

```sh
pdfmd lecture -e lualatex       # one engine; a failure is an error, not a fallback
pdfmd lecture -e typst
pdfmd lecture -e tex            # a family: only TeX engines, in order (lualatex, xelatex, pdflatex ...)
pdfmd lecture -e html           # only weasyprint, wkhtmltopdf, pagedjs-cli, prince
pdfmd lecture -e                # a bare -e: every installed engine, whatever the document asks
pdfmd --check-dependencies      # what is installed
```

Without `-e` pdfmd tries the engines in order and tells you why each one that failed did. A document can pin one:
`pdfmd-options: {pdf-engine: lualatex}` (a name or a family); the command line always wins.
`-e soffice` builds the Word file and lets LibreOffice make the PDF.

### 1.5 Open it, watch it

```sh
pdfmd lecture --open            # open the result when done
pdfmd lecture -w                # rebuild whenever the source (or its metadata) changes, until Ctrl-C
```

### 1.6 One section only

```sh
pdfmd lecture#results           # just the section "Results", written as lecture.results.pdf
pdfmd lecture##yield            # a level-2 heading;  lecture#results/yield: one under another
pdfmd lecture#results+methods   # several, always in document order
pdfmd lecture --list-parts      # what can be named
pdfmd lecture#fig:setup         # anything with a {#label}: a figure, an equation, a table
```

Heading names are matched like file names: case, spaces and spelling do not matter and a unique start works.

### 1.7 Pass options to Pandoc

Whatever pdfmd does not know goes to Pandoc unchanged:

```sh
pdfmd lecture --toc --number-sections
pdfmd lecture -V fontsize=12pt -V colorlinks=true
pdfmd lecture --citeproc --bibliography refs.bib
```

---

## 2. A project with a house style

pdfmd looks beside the document, and in a `metadata/` folder beside it, for **only** these names:

| File | Used as |
|---|---|
| `metadata.yaml` | shared Pandoc metadata (fonts, bibliography, CSL ...) |
| `<name>.yaml` | per-document metadata, on top of `metadata.yaml` |
| `report.yaml`, `book.yaml` | metadata of `-r` builds |
| `preamble.tex`, `latex-preamble.tex`, `<name>-preamble.tex`, `preamble-*.tex` | LaTeX added to the header |
| `<name>.lua` | a Pandoc Lua filter for that document |

An unrelated `.tex` or `.lua` lying in the folder never changes a render. `-v` says which files were taken;
`-y FILE` names a metadata file explicitly (a bare `-y` turns discovery off).

A Lua filter can run any command, so the first build with a `<name>.lua` pdfmd has not run before, and the first build
after you edit it, print one `NOTE` (the filter still runs; nothing ever prompts). `pdfmd --trust-lua FOLDER` marks the
folder you work in, and nothing under it is noted again; `--strict` skips a new or edited filter outside such a folder.
Read a downloaded folder's `.lua` before its first build: this is a notice, not a lock.

### 2.1 One style for a whole course folder

```text
labreports/
  metadata/
    metadata.yaml       # a symlink to your shared one works: a relative bibliography is found beside the real file
    preamble.tex
  LR1/report.md
  LR2/report.md
```

or the same files directly in each report's folder. Put everything that should be the same in `metadata.yaml`
(fonts, margins, bibliography, CSL, `pdfmd-options`) and the documents carry only their text. What a document or the
command line says wins over the shared file.

### 2.2 Settings inside the document

```yaml
---
title: Lab report
pdfmd-options:
  pdf-engine: tex           # only TeX engines; never fall back to HTML ones
  no-auto: [margin, monofont]
  stamp: true
---
```

`pdfmd-options` takes the same keys in a document, in a metadata file and in the config file's `options:` block
(see [13.5](#135-your-own-defaults)); the document wins, then its metadata files, then the config file.

### 2.3 Switch the automatic behaviour off

```sh
pdfmd lecture --no-auto                     # everything off: close to plain pandoc
pdfmd lecture --no-auto margin mainfont     # just these
pdfmd lecture -v                            # shows each AUTO decision with its reason, and the Pandoc command
```

Kinds: `reader title margin mainfont monofont tablewidth unicode lookup yaml tex lua crossref citationengine
csvtable codewrap svg remoteimages pdfimages typstdirect htmldirect officeref officestyle officelatex ...`
(`pdfmd --help debug`).

### 2.4 Citations

```yaml
---
bibliography: refs.bib
csl: ieee.csl
---
```

`[@key]` and `@key` citations switch on `--citeproc` by themselves, and `@fig:`/`@tbl:` references the `pandoc-crossref`
filter, when it is installed. `--no-citeproc` stops the first for a run.

### 2.5 A LaTeX package that tells pdfmd about itself

Beside a package's `.sty`, a `<package>-pdfmd.yaml` maps front-matter keys to macros (`latex-keys:`) and can carry the
package's Word support (reference document, `<package>-office.lua`, `<package>-office.yaml`). A document that loads
the package gets all of it with no setting of its own. See *Word and OpenDocument output* in the README.

---

## 3. Long documents

### 3.1 A folder of chapters as one PDF

```sh
pdfmd book -r -o book.pdf          # every .md in the folder, in the order of their `chapter:` fields
pdfmd book -r -i appendix          # leave one out
pdfmd book -r --exclude-unnumbered # skip files without a chapter:
pdfmd notes -b                     # or: every file its own PDF, in parallel (-j N workers)
pdfmd notes -b --recursive -o out/ # include subfolders; collect the PDFs in out/
```

### 3.2 One document in parts

For an article that grew too long to edit as one file: a scaffold with the front matter, the text in `parts/`.

```text
report.md                 front matter only (title, author ...)
parts/10-introduction.md
parts/20-methods.md
parts/30-discussion.md
```

```yaml
# metadata.yaml, shared by your documents: a document is a scaffold only if parts/ or sections/ exists
pdfmd-options:
  parts: auto
```

```sh
pdfmd report                          # the whole document
pdfmd report#methods                  # one part, report.methods.pdf
pdfmd parts/20-methods.md             # the same
pdfmd report#discussion+appendix      # several
pdfmd report --list-parts
```

The parts are joined into one Pandoc run, so the result is the same as the text in one file: labels, citations and numbers
work across parts and paths are written relative to the scaffold's folder. A part built alone still shows the numbers of
the others: pdfmd has Pandoc write the LaTeX of the whole document once more (about a second), reads which headings,
captions, equations and labels it holds, and LaTeX replays them at the start of the part, so a reference to another
section, figure, table or equation (`\ref`, `\cref`, `[@fig:a]`) prints its number in the document's own style and the
part's own numbers continue from the parts before it. It is approximate for whatever the document defines itself (a
macro that opens a figure): that label stays `??`, and the build says so. The cache's `.aux` from the last full build is
exact and wins when there is one ([12.1](#121-faster-rebuilds)). `--seed-labels auto|aux|scan|draft|off` or
For HTML, EPUB, Word, OpenDocument, Typst and PDF through a non-LaTeX engine the whole document is numbered by
pandoc-crossref and only the part you asked for is kept, so its numbers are the whole document's and `[@sec:x]` to the
rest resolves (raw LaTeX `\ref` does not outside LaTeX). `pdfmd-options: {seed-labels: scan}` picks the source; `draft` runs LaTeX once over the whole document without output
(exact, about half a compile's cost each time); `off` gives the `??` back.

### 3.3 Cut a single file into parts, or join parts back

```sh
pdfmd old-report.md --split new-folder                     # one file per level-1 heading
pdfmd old-report.md --split new-folder --split-depth 2     # ... and per level-2 heading
pdfmd report --assemble-only                               # report.assembled.md: the parts joined, to read or send
```

### 3.4 Look at what pdfmd builds from

```sh
pdfmd report --stop-at markdown          # the assembled Markdown (= --assemble-only)
pdfmd report --stop-at tex               # the .tex a LaTeX engine would get (= -t latex)
pdfmd report --assemble-only --embed-metadata        # one file that carries metadata, preamble, filters, .bib, .csl
pdfmd report.assembled.md --unpack                   # ... and the way back, into report.assembled.unpacked/
pdfmd report.assembled.md --unpack --slim            # strip what was unpacked from the file
```

An embedded Lua filter only runs if this machine's pdfmd embedded it (a filter can run any command);
`--trust-embedded` overrides.

---

## 4. Tables

### 4.1 A table from a CSV file

````markdown
::: {.csv file="tables/results.csv" caption="Results {#tbl:results}" align="lcr" widths="30%,40%,30%"}
:::

::: {.csv}
```
Quantity,Value
Mass,0.18
```
:::
````

The data comes from `file=` or from inside the block (with both, the file is used); the delimiter is guessed
(`delimiter=";"` or `semicolon`, `tab` ...); `align="lcr"` and `widths` are optional; the first row is the header unless
`header="false"`. A large file is capped at 10 rows by 7 columns, and the PDF says so: `rows=all` or `cols=20` raise the
cap. Cells are Pandoc Markdown (`H~2~O`, `$x^2$`, `\ce{...}`, `[@key]`). A caption is `caption="..."` in the braces or the
line `: Caption {#tbl:id}` after the block. This works for every output format. A table whose lines run long gets its
columns sized by content automatically (`--no-auto tablewidth` to stop).

### 4.2 Turn the tables you already have into CSV files

```sh
pdfmd --extract-tables report.md                   # every convertible table -> tables/<name>.csv + a .csv block
pdfmd --extract-tables report.md --dry-run         # show the change, write nothing
pdfmd --extract-tables report.md --table-numbers 2,4-5      # only these tables, by position (1 is the first)
pdfmd --extract-tables report.md --table-numbers 2 --table-names ir-bands   # and name that one
pdfmd --extract-tables report.md --tables-dir data           # another folder
pdfmd --extract-tables report.md --tables-inline             # data inside the block, no files
pdfmd --extract-inline-csv report.md                         # move the data of inline .csv blocks to files too
pdfmd --expand-tables report.md                              # the reverse: every .csv block becomes a pipe table
```

The file is backed up first, and before anything is written Pandoc reads the old and the new document: the tables must
come out the same, or nothing is changed. A table Pandoc cannot write as CSV (a list inside a cell, spanning cells, no
header) stays as it is, with the reason. Names come from the captions, else `table1`, `table2`; in a document in parts
they go to the report's `tables/` folder and an unnamed table is named after its part (`discussion-table1.csv`).
Name one part to do one part: `pdfmd --extract-tables parts/50-discussion.md --table-names ir-bands`.

### 4.3 Keep one table out of it

```markdown
<!-- pdfmd: ignore -->
| a | b |
|---|---|
| 1 | 2 |
: This one stays Markdown
```

The comment goes on the line above a table or `.csv` block, or under its caption. It survives comment stripping.

### 4.4 Wide tables

A pipe table with plain `---` separators gets the column widths that give the fewest lines within the text width.
Unequal dashes (`|:--|----------|`) are your choice and are kept; equal dashes with long rows count as "not chosen".

---

## 5. Code, images and pieces that are not Markdown

### 5.1 Code blocks

Long lines wrap at the margin in a LaTeX build; line numbers are off unless asked.

```sh
pdfmd lecture --line-numbers          # number every line;  --line-numbers 5: every 5th
pdfmd lecture --no-code-wrap          # let long lines run on
```

Per block: `{.numberLines startFrom=10 step=5}`, `{.noNumberLines}`, `{wrap=false}`. A highlighting theme is Pandoc's
(`--highlight-style=tango`).

### 5.2 Images

```markdown
![A scheme](schemes/rxn.svg){width=8cm}
![From the web](https://example.org/figure.png)
![A drawing](plots/fig.pdf)
```

- an **SVG** in a LaTeX build is converted to a PDF once (rsvg-convert, inkscape, cairosvg, svglib or LibreOffice,
  whichever is installed) and kept in the cache; `--no-auto svg` stops it;
- an image from the **web** is fetched once and kept for 7 days (`--no-auto remoteimages`); offline you get one warning and
  Pandoc's description text;
- a **PDF image in an HTML build** (a web page, an EPUB, a PDF through WeasyPrint) becomes an SVG (poppler's
  `pdftocairo`, `mutool`, `pdf2svg` or `inkscape`), so it stays vector; `--no-auto pdfimages` stops it;
- a raw `\includegraphics` also gets `graphicx` in a LaTeX build.

### 5.3 Raw HTML, LaTeX, Typst and Word inside Markdown

Pandoc keeps raw pieces written in the format it writes and silently drops the others. Tell pdfmd which syntaxes take
part in which output family and the foreign ones are carried over:

```yaml
pdfmd-options:
  raw:
    tex:    [tex, html, typst]     # LaTeX builds
    typst:  [typst, html, tex]     # Typst builds
    html:   [html, tex, typst]     # HTML, EPUB, PDF through weasyprint (-e html)
    office: [office, html]         # Word and OpenDocument, PDF through soffice
```

```sh
pdfmd report --raw                          # everything for every family
pdfmd report --raw-for html=tex,typst       # one family, from the command line (repeatable)
pdfmd report --no-raw                       # off for this run
```

- **HTML** is read into the target's own elements: `<img>`, `<table>`, `<b>...</b>`, `<div>` around Markdown, even when
  the opening and the closing tag are separate pieces.
- **LaTeX**: in Word builds, and in HTML and Typst builds that take it, pdfmd's LaTeX route makes `\ce{}`, `\SI{}{}` and
  equations native and draws what is left (tikz, chemfig, a house style's macros) in your preamble as vector pictures
  (needs a `preamble.tex` that loads the packages, a LaTeX engine and poppler's `pdftocairo`).
- **Typst** is drawn by `typst compile` as a cropped vector picture (PDF; SVG for HTML).
- A **LaTeX picture** Pandoc's reader cannot read (`tikzpicture`, `circuitikz`, `pgfpicture`, `forest`, `\chemfig`) is drawn with
  the `standalone` class after your preamble and `header-includes`, for HTML, Typst and flat Markdown (`--to gfm`) builds;
  one that does not compile is reported with LaTeX's first error and left out.
- A syntax a family does not list is dropped, its own included; a family not mentioned is left to Pandoc. `raw: all`,
  a list, or a mapping with a `default:` key are accepted.

More in the README: [HTML, LaTeX, Typst and Word pieces inside Markdown](../README.md#html-latex-typst-and-word-pieces-inside-markdown).

---

## 6. Other inputs

```sh
pdfmd paper.tex                 # a LaTeX engine directly: reruns until references settle, bibtex/biber, no clutter (--keep-aux keeps)
pdfmd minutes.docx              # Word, PowerPoint, Excel, ODF: converted by LibreOffice
pdfmd analysis.qmd              # handed to Quarto, so code chunks run
pdfmd page.html                 # WeasyPrint, or a browser if the page runs scripts: no Pandoc, the page's own CSS is kept
pdfmd note.typ                  # Typst itself: the page setup in the file is kept
pdfmd notes.rst                 # anything Pandoc reads (give the extension)
pdfmd notes.txt                 # plain text; --text-to-markdown guesses headings, lists and tables
```

A finished `.typ` or `.html` is not rewritten through Pandoc, so it gets none of pdfmd's defaults;
`pdfmd page.html --apply-defaults` gives it the title, author, language, font, paper and margins of its `metadata.yaml`
ahead of its own settings (also in `--setup`). `--no-auto typstdirect htmldirect` is the old route through Pandoc.

### 6.1 A PDF back to Markdown

```sh
pdfmd paper.pdf                         # -> paper.md: the text layer in reading order, OCR for scanned pages
pdfmd scan.pdf --lang eng+rus --ocr tesseract --export-images
pdfmd paper.pdf --to txt                # plain text
pdfmd --install batchocr                # the reader, once; then Tesseract and Poppler for scanned pages
pdfmd --install ocr:rus,kaz             # OCR languages into pdfmd's own folder, no admin rights
```

A PDF that carries its own pdfmd source is restored instead ([8](#8-the-pdf-that-carries-its-source)); `--extract`
reads its pages anyway.

---

## 7. Other outputs

### 7.1 Word and OpenDocument that follow the PDF's page setup

```sh
pdfmd report -o report.docx             # papersize, margins, fonts, line spacing from the front matter
pdfmd report -o report.odt
pdfmd report.md --check-docx            # what becomes native, what is drawn as a picture, what is left out
pdfmd --init-reference                  # reference.docx with pdfmd's look, to restyle in Word (also odt, pptx)
```

```yaml
pdfmd-options:
  office:
    reference-doc: ../templates/house.dotx     # your template; pdfmd then changes only what is named here
    papersize: a4
    fonts: exact                               # keep STIX Two Text and friends as named (otherwise mapped to Times New Roman ...)
    style: plain                               # no pdfmd look
    styles: {Heading1: LRH1, BodyText: LRNormal}
    latex: auto                                # auto (Word default), images (draw everything), off
```

LaTeX in a Word build: `\ce`, `\si`, `\SI`, `\num`, equations, `\ref`/`\cref` numbers (from a PDF build's `.aux`), tikz and
chemfig as pictures. A house style's own macros can be given a Word recipe in `office.lua`. The README has the details.

### 7.2 A PDF that LibreOffice opens as an editable document

```sh
pdfmd report --hybrid                   # the PDF carries report.md as Original.odt; LibreOffice opens it as that document
pdfmd report --hybrid --attach-source   # ... and the Markdown source as well
```

The `.odt` is the Word route's rendering of the same Markdown, so what you edit in LibreOffice is the same document in
a different layout engine. `pdfmd-options: {hybrid: true}` or `--setup` makes it the default.

### 7.3 HTML

```sh
pdfmd lecture -o lecture.html --self-contained
```

```yaml
pdfmd-options:
  html: {self-contained: true, css: style.css, math: mathjax}      # math: mathml (default), mathjax, katex, webtex
```

### 7.4 Typst and slides

```sh
pdfmd lecture -t typst -o lecture.typ ; typst compile lecture.typ
pdfmd slides -p --slide-level 2          # Beamer; level 2 headings start slides
```

### 7.5 Plain Markdown that any viewer shows

```sh
pdfmd report --to gfm                 # report.gfm.md: title, numbers, captions, citations, tables, all in plain Markdown
pdfmd report --to gfm --gfm-scripts ascii -o report.txt.md      # H_2O, x^2, CO_3^(2-) for a viewer with no Unicode scripts
pdfmd report -o report.gfm.md        # the name alone asks for it (a plain -o report.md is Pandoc's Markdown)
pdfmd report --to gfm+raw             # Pandoc's own gfm writer (HTML left in) instead
```

`::: {.csv}` tables, included files, parts, raw HTML and LaTeX (`<b>x</b>`, `\textbf{x}`), citations and the
bibliography are all processed; a Typst piece or a PDF figure becomes an SVG in `report.gfm_files/`. The output sits beside
the source under another name; a Markdown writer never replaces its own source (`pdfmd doc.md --to markdown` stops with an
error unless `-o` names another file). Settings: `pdfmd-options: {gfm: {scripts: unicode, math: dollars, title: true}}`.

`--keep-source` ends the file with its whole source in an HTML comment, `--restore FILE.md` writes it back, so the flat
copy can go to a reader and the original is not lost: `pdfmd report --to gfm --keep-source`, then `pdfmd --restore
report.gfm.md` makes `report.gfm.restored/` with `report.md`, the parts and the CSV data (details in the README).

The same build as text, for an e-mail, a chat or a terminal: `pdfmd report --to txt` (or `-o report.txt`) writes the title
and headings underlined, `Table 1. caption` above a table, `[Figure 1. caption]` for a figure, `words <https://link>` for a
link, and Unicode `H₂O`; `--columns=100` changes the wrapping. `--to plain` is Pandoc's own plain writer (no title, no
links).

And with not a byte above 127 (a terminal, an old mail gateway): `pdfmd report --to ascii` writes `report.ascii.txt`
(`Cafe`, `"quotes"`, `H_2O`, `x^2`, `5 degC`, `alpha`, `Privet`); `--to ascii:gfm` does it for flat Markdown, and
`-o report.ascii.txt` asks for the same by its name (so do `.ascii.gfm.md`, `.ascii.md`, `.ascii.rst`, `.ascii.org`, `.ascii.adoc`). A character nothing can spell is named in a `WARN` and written as `?`;
`--ascii-missing escape` writes `\u65e5`, `drop` nothing, `fail` stops before writing. `pdfmd --install translit` adds
Chinese and the other scripts.

---

## 8. The PDF that carries its source

```sh
pdfmd report --attach-source          # the merged source goes into report.pdf as an attachment
pdfmd report --bundle                 # ... and the data/files its LaTeX reads
pdfmd report --bundle all             # ... the whole folder except output and housekeeping
pdfmd --restore report.pdf --list     # what the PDF carries and what a rebuild needs; writes nothing
pdfmd --restore report.pdf            # report.restored/ with the layout back: report.md, metadata/, parts/, tables/ ...
pdfmd --restore report.pdf -o ~/work/again
```

```yaml
pdfmd-options:
  attach-source: true
  strip-comments: false               # a full copy: comments and the YAML files' own text come back byte for byte
  attach-bibliography: used           # or all
  bundle: true                        # or all; bundle-max-mb: 100
  bundle-packages: true               # your own LaTeX packages too
```

What the attachment is: the assembled Markdown with metadata, preamble, filters, the cited bibliography entries and CSL
folded in, a manifest of the original layout, the data files of `.csv` blocks, and the build history file. Images come out
of the PDF itself (a JPEG byte for byte, others as the same pixels, an SVG or PDF figure as a vector PDF), so a plain
attach needs no bundle for them. `--bundle` is for what the PDF does not draw (CSV data, `\input` files, listings).

- **Comments.** By default notes to yourself do not travel. `strip-comments: false`, or per kind
  (`[preamble, bibliography]`, `{markdown: false}`, `--keep-comments-in metadata`) keeps them; with the `metadata`
  kind kept the restored YAML files and front matter are the original text.
- **Safety.** `--restore` never overwrites and never writes outside its folder. A restored Lua filter is code: read it first.
- **A report for a lab course:** put `attach-source: true` and `strip-comments: false` in the shared `metadata.yaml`;
  every PDF is then also a complete, editable copy of the report minus the photographs.

---

## 9. History, backups and build notes

### 9.1 Backups on every build

```sh
pdfmd report --backup                          # a copy in .backups/ after each successful build (skipped if unchanged)
pdfmd report --backup-format dashed            # report.md.bak.20261009-151826 (compact, dashed, stem, suffix, short, or a template)
pdfmd --init-backups report.md                 # backups + a history file for this document
pdfmd --init-backups report.md --backup-folder ~/backups/reports
pdfmd --init-backups report.md --global        # for every document
```

```yaml
pdfmd-options:
  backup: {dir: .backups, format: dashed, keep: 30}
```

### 9.2 Look back, compare, restore

```sh
pdfmd --history report.md              # backups (any folder, any naming), git commits, recorded compiles: newest first
pdfmd --history report.md --history-all
pdfmd --history-diff 3 report.md       # what differs from version 3 (number, timestamp start, file name, commit, latest, previous)
pdfmd --history-restore previous report.md        # backs the file up first, keeps the build notes, adds a "Restored" entry
pdfmd --history-restore 20261003 report.md --dry-run
```

In a terminal `--history` is navigable: a number shows what differs, `d 3` the diff, `r 3` restores.

### 9.3 Build notes: in the document or in a file

```sh
pdfmd report --stamp                         # a BUILD NOTES comment at the end of the .md
pdfmd report --stamp --stamp-mode history    # ... with the list of past compiles
pdfmd report --stamp-packages nulabreport    # name a LaTeX package's version
pdfmd report --stamp-store file              # the compile goes to .backups/report.hst; the document is not edited
pdfmd --history-to-file report.md            # move the whole pdfmd BUILD NOTES block into the .hst file
pdfmd --history-to-notes report.md           # and back
pdfmd --merge-history a.hst b.hst -o all.hst # join two history files, every entry once
```

A document may carry several BUILD NOTES blocks (yours, an AI agent's): pdfmd writes only into the one that holds its own
lines, and a line `pdfmd: ignore` in a block keeps it out. Every PDF also gets two hidden Info keys
(`PdfmdVersions`, `PdfmdBuildDate`; `--no-stamp-pdf-metadata` turns that off).

---

## 10. Fonts, scripts and emoji

### 10.1 A paper in several scripts

```sh
pdfmd paper                         # -v says which font each script got
pdfmd --check-fonts paper.md        # what would be used, and which characters no installed font draws
pdfmd --install fonts:cjk-sc,arabic # fetch a missing font (no admin rights); fonts:core, fonts:all
pdfmd --install emoji               # colour emoji pictures where no system font has them
```

Set `lang: ja` (or `zh`, `ko`) so Han characters get the right flavour. Choose what happens to a character the main
font lacks: `--fallback char` (default: just those characters in another font), `word`, `document` (the font that draws
most of the document becomes the main font), `box`, `off`, `error`; `--missing warn|box|error` for characters no font draws.
Per document: `pdfmd-options: {fallback: word}`.

### 10.2 Choose fonts

```yaml
mainfont: "STIX Two Text"
monofont: "JetBrains Mono"
mathfont: "STIX Two Math"
fontsize: 12pt
```

STIX Two Text and JetBrains Mono are the defaults when installed (a serif that has the letters when the document is mostly
in a script they lack). `-f FONT` sets a font to fall back to.

### 10.3 Transliteration for names

```sh
pdfmd --translit greek,hangul tyche      # finds Τύχη.md
PDFMD_TRANSLIT=all pdfmd mingyun         # finds 命運.md (pdfmd --install translit for Chinese and the rest)
pdfmd --translit list                    # what is ready
```

### 10.4 Find a document by a name in another script

Cyrillic (Russian, Ukrainian, Belarusian, Kazakh) is always understood: `pdfmd glyukoza` opens `Глюкоза.md`. The
same spelling rules find a section by its heading (`pdfmd 'notes#tyche'`). To make packs permanent put
`translit: [greek, hangul]` in the config file.

---

## 11. Finishing a PDF

All off unless asked, done on the finished PDF with pypdf, so they work with every engine.

```sh
pdfmd report --bookmarks                       # bookmarks from the headings, if the engine made none
pdfmd report --header "{title},,{date}" --footer ",Page {page} of {pages},{header}"
pdfmd report --attach-links                    # the local files the text links to travel inside the PDF
pdfmd report --pdf-title "Kinetics" --pdf-author "A. Writer" --pdf-keywords "rate, order" --pdf-subject "Lab 3"
pdfmd report --paper letter
```

A template is `left,middle,right`; `{page} {pages} {header} {date} {title}` are filled per page; `\,` is a literal comma.

---

## 12. Speed

### 12.1 Faster rebuilds

```sh
pdfmd report --cache                  # keep LaTeX's .aux between builds: an unchanged document is typeset once, not 2-3 times
pdfmd report --cache-plots            # also nulabreport's plots as PDFs (nulabreport >= 1.26.0, LuaLaTeX)
pdfmd report --cache-location document          # keep the cache beside the document (.cache/pdfmd)
pdfmd report --no-cache               # off for one build
pdfmd report --clear-cache            # delete this document's cache;  pdfmd --clear-cache: all of it
```

It never skips a build. With the cache a part built alone (`report#methods`) shows the real numbers of the parts left
out, exact where the scan of 3.3 is approximate. Per document: `pdfmd-options: {cache: {aux: true, plots: true, location: document}}`.

### 12.2 Parallel and watching

```sh
pdfmd notes -b -j 8        # eight workers
pdfmd report -w            # rebuild on every save
```

---

## 13. The tools around it

### 13.1 A small editor in the terminal (alpha)

```sh
pdfmd --install tui         # once: prompt_toolkit
pdfmd --edit lecture        # Ctrl-S save, Ctrl-B save and build, Ctrl-P open the PDF, Ctrl-W find, Ctrl-G line, Ctrl-X exit, F1 keys
pdfmd --edit lecture -e lualatex       # options given beside it are used for the build
```

### 13.2 VS Code

```sh
pdfmd --init-vscode         # .vscode/tasks.json: build, build and open, watch, extract tables (Cmd/Ctrl+Shift+B)
```

The `vscode/` folder of the repository is an extension over the same command line (build, build as ..., extract tables,
history, restore source of a PDF); see its README.

### 13.3 Tab completion

```sh
pdfmd --completion zsh > ~/.zfunc/_pdfmd        # bash and fish too; generated from the real command line
```

### 13.4 Install what is missing

```sh
pdfmd --doctor                       # one report: tools, fonts, OCR, config, cache, and the command that fixes each gap
pdfmd --install full                 # Pandoc and Typst into pdfmd's own folders, no admin rights
pdfmd --install pandoc|typst|math|emoji|fonts|translit|ocr|batchocr|tui
pdfmd --uninstall fonts:NAME         # or ocr:LANG
```

No Pandoc at all? pdfmd falls back to a built-in renderer (the vendored inkmd); `pdfmd --install math` and `emoji` make it better.
An old Pandoc (3.1.3 or later) works; pdfmd says once what it does without.

### 13.5 Your own defaults

```sh
pdfmd --setup               # a numbered menu: every default pdfmd has, with its choices; s saves, q quits
pdfmd --setup fancy         # the full-screen version (pdfmd --install tui)
pdfmd --init-config         # a commented ~/.config/pdfmd/config.yaml
pdfmd --show-config         # where it is and what it sets
```

The config file's `options:` block takes the same keys as a document's `pdfmd-options:` and applies to every document, below
what the document or its metadata files say. `PDFMD_CONFIG=other.yaml` uses another file, `PDFMD_CONFIG=` none.

### 13.6 From Python

```python
import pdfmd

pdfmd.convert_file("report.md", "docx")                         # -> Path("report.docx")
pdfmd.convert_file("report.md", "pdf", "out/report.pdf", extra_args=["--engine", "typst"])
html = pdfmd.convert_text("# Hi\n\nSome *text*.\n", "html")     # a str; bytes for pdf/docx/odt/pptx/epub
```

Each call runs the command-line tool, so a document builds exactly as `pdfmd` would build it; a failure raises
`pdfmd.PdfmdError`.

---

## 14. When something looks wrong

1. **`pdfmd doc -v`.** It prints every automatic decision with its reason and the exact Pandoc command. A PDF that does
   not look like the Markdown suggests is very often one of these decisions (a discovered metadata file, an auto-added
   preamble, the table-width filter).
2. **`pdfmd doc --no-auto`** switches every automatic behaviour off: close to plain Pandoc. If that fixes it, narrow it
   down: `--no-auto margin`, `--no-auto tablewidth` ...
3. **`pdfmd doc --debug`** prints the full output of every engine that failed, even one a later engine recovered from.
4. **`pdfmd --doctor`** says what is missing and how to install it.
5. **`pdfmd doc --stop-at tex`** (or `--assemble-only`) shows what is handed to the engine.
6. **`pdfmd --clear-cache`** starts over.
7. **A table or section will not be found?** `pdfmd doc --list-parts`.
8. **Which engine built it?** The closing line names it: `OK    doc.md  (typst; lualatex failed)` means LaTeX failed
   and Typst made the file. `pdfmd doc --strict` turns that, and any other warning (an image or citation that was not
   found, an undefined reference), into a failed build with exit code 1, for a script or CI; the output is kept.
9. **A build changed after an update?** `pdfmd --history doc.md` and `--history-diff` compare the source; the
   CHANGELOG lists what each version changed.

| Symptom | Likely cause | Try |
|---|---|---|
| a raw `<img>` or `\ce` vanished | the output family does not take that syntax | `--raw` ([5.3](#53-raw-html-latex-typst-and-word-inside-markdown)) |
| a PDF figure missing from HTML | no `pdftocairo`/`mutool`/`pdf2svg`/`inkscape` | install poppler |
| `??` in a part built alone | a label the scan cannot count (the document's own macro), `\pageref`, or `--seed-labels off` | `--cache`, then one full build; `--seed-labels draft` |
| `--extract-tables` refuses | Pandoc would read the tables differently after the change | read the reason it prints; `<!-- pdfmd: ignore -->` that table |
| boxes instead of letters | no installed font draws them | `pdfmd --check-fonts doc.md`, `pdfmd --install fonts` |
| LaTeX fails, Typst output differs | an engine failed and the chain went on (the closing line names it) | `-v`, `--debug`, `--strict`, or pin the engine |

---

## 15. Option reference by task

| I want to ... | Options |
|---|---|
| choose the output | `-o FILE`, `-t FORMAT`, `-d`, `--self-contained`, `-p` (slides), `--open` |
| choose the engine | `-e ENGINE\|FAMILY`, `pdfmd-options.pdf-engine` |
| build many files | `-b`, `-r`, `-i`, `--exclude-unnumbered`, `--recursive`, `-j`, `--section`, `--split`, `--list-parts` |
| stop part-way | `--stop-at markdown\|tex`, `--assemble-only`, `--embed-metadata`, `--unpack`, `--slim` |
| carry the source | `--attach-source`, `--bundle`, `--bundle-packages`, `--restore`, `--list`, `--strip-comments`, `--keep-comments`, `--strip-comments-in`, `--keep-comments-in`, `--attach-bibliography` |
| editable PDF | `--hybrid` |
| tables | `--extract-tables`, `--expand-tables`, `--extract-inline-csv`, `--table-numbers`, `--table-names`, `--tables-dir`, `--tables-inline`, `--dry-run` |
| code | `--line-numbers`, `--no-code-wrap` |
| raw pieces | `--raw`, `--no-raw`, `--raw-for` |
| history | `--history`, `--history-all`, `--history-diff`, `--history-restore`, `--no-restored-note`, `--init-backups`, `--backup-folder`, `--global`, `--stamp`, `--stamp-mode`, `--stamp-store`, `--history-to-file`, `--history-to-notes`, `--merge-history`, `--backup`, `--backup-format` |
| fonts and scripts | `-f`, `--fallback`, `--missing`, `--check-fonts`, `--translit`, `--emoji-fallback` |
| PDF finishing | `--bookmarks`, `--header`, `--footer`, `--attach-links`, `--pdf-title`, `--pdf-author`, `--pdf-subject`, `--pdf-keywords`, `--paper` |
| cache | `--cache`, `--cache-location`, `--cache-plots`, `--no-cache`, `--clear-cache` |
| Word / direct builds | `--check-docx`, `--init-reference`, `--apply-defaults` |
| tools | `--edit`, `--init-vscode`, `--completion`, `--setup`, `--init-config`, `--show-config`, `--install`, `--uninstall`, `--doctor`, `--check-dependencies` |
| debugging | `-v`, `--debug`, `--no-auto`, `--full-paths`, `--keep-aux` |

`pdfmd --help all` is the authoritative list; `pdfmd --help TOPIC` shows one group of it.
