# pdfmd

[![Test](https://github.com/aliperdehan/pdfmd/actions/workflows/publish.yml/badge.svg)](https://github.com/aliperdehan/pdfmd/actions/workflows/publish.yml) [![PyPI](https://img.shields.io/pypi/v/pdfmd-cli)](https://pypi.org/project/pdfmd-cli/)

**One command from Markdown to a good-looking PDF.** `pdfmd` wraps
[Pandoc](https://pandoc.org) and fills in everything you would otherwise
have to remember: sensible fonts and margins, the right Markdown dialect,
your project's metadata/preamble/filter files, and a fallback chain across
every PDF engine you have installed. The same document also builds to a
Word or OpenDocument file that follows its page setup, fonts and LaTeX (see
[Word and OpenDocument output](#word-and-opendocument-output)).

```console
$ pdfmd lecture
AUTO: READER TITLE MARGIN MONOFONT. Use --verbose to see in full
OK    lecture.md
```

<p align="center">
  <img src="https://raw.githubusercontent.com/aliperdehan/pdfmd/main/docs/lecture.png" width="560" alt="lecture.md rendered to PDF">
</p>

That PDF came from [`examples/lecture.md`](https://github.com/aliperdehan/pdfmd/blob/main/examples/lecture.md), a plain
Markdown file with no front matter and no configuration. Plain `pandoc
lecture.md -o lecture.pdf` doesn't even get that far: its default engine,
`pdflatex`, stops at the `Δ` on line 5 with an error. With a Unicode engine
it would build, but with wide default margins, and with the `# Title`
line as an ordinary section heading instead of a title.

## Why

Pandoc can do nearly anything, but its defaults assume you'll pass the right
flags every time. In practice that means one of two things: a long command
you copy from an old shell history, or a Makefile in every folder. `pdfmd`
turns that knowledge into defaults:

- **It decides per document, not globally.** A file with no YAML front
  matter is treated as ordinary GitHub-flavoured Markdown. A file that has
  front matter is assumed to be written for Pandoc and is left alone.
- **It finds your project files.** A `metadata.yaml`, `preamble.tex` or
  `<name>.lua` beside the document (or in a `metadata/` folder next to it)
  is picked up automatically, so every document in a folder shares one
  house style without any flags.
- **It doesn't give up on the first engine.** If `lualatex` fails or isn't
  installed, it tries the next engine, then the next, and tells you why each
  one failed.
- **It writes real Word files.** `pdfmd report -o report.docx` reads the front matter the PDF reads (paper size,
  margins, fonts, line spacing) and writes it into the file's page setup and styles, so the Word file is laid out the
  way the PDF is. With LaTeX installed, what only LaTeX can say in the document comes along: `\ce{...}` chemistry,
  `\SI{...}{...}` units and equations become native, editable Word text and equations; a house style's own macros can be
  given a Word recipe; what is left (tikz, chemfig, math Pandoc cannot convert) is drawn by LaTeX in the document's
  own preamble and embedded as vector pictures. `pdfmd-options: {office: {latex: auto|images|off}}`, `--no-auto
  officelatex` and `pdfmd --setup` switch it (see [Word and OpenDocument output](#word-and-opendocument-output)).
- **It handles every script and emoji.** Text the main font cannot draw (Arabic,
  Hebrew, Chinese, Japanese, Korean, Greek, Cyrillic with Kazakh letters, Indic and
  more) is set run by run in an installed font for its script, emoji become colour
  pictures, and `pdfmd --install fonts` fetches missing fonts without admin rights
  (see [Other scripts](#other-scripts)).
- **It finds documents by name, in any script.** `pdfmd glyukoza` opens
  `Глюкоза.md`; with `--translit` packs, `pdfmd tyche` finds `Τύχη.md` and
  `pdfmd mingyun` finds `命運.md`.
- **It reads PDFs too.** `pdfmd paper.pdf` restores a PDF's own embedded source or
  OCRs the pages to Markdown (see [PDF to Markdown](#pdf-to-markdown)).
- **It shows what it did.** Every automatic decision prints an `AUTO` line,
  `-v` shows the exact Pandoc command, and every default can be switched off.

## Install

```sh
pipx install pdfmd-cli
```

That puts a `pdfmd` command on your PATH, with its Python dependencies, in
its own isolated environment. The same with uv:

```sh
uv tool install pdfmd-cli        # install; update with: uv tool upgrade pdfmd-cli
uvx --from pdfmd-cli pdfmd file.md   # or run once without installing
```

On macOS, Homebrew installs it together with Pandoc and Typst, so nothing else
is needed for a first PDF:

```sh
brew install aliperdehan/tap/pdfmd
```

To update later, run `pipx upgrade pdfmd-cli`. (The package is named
`pdfmd-cli` because `pdfmd` on PyPI is an unrelated PDF-to-Markdown tool.
The command is still `pdfmd`. For the latest unreleased code, use `pipx
install git+https://github.com/aliperdehan/pdfmd`.)

For the full pipeline, `pdfmd` drives programs that pip can't install, so you
also need (without them it still makes a plain PDF; see
[No Pandoc?](#no-pandoc-the-built-in-fallback) below). The quickest way, with no
admin rights, is `pdfmd --install full`, which puts Pandoc and Typst in pdfmd's own
folders; the system installers below do the same job:

- **[Pandoc](https://pandoc.org/installing.html)**
- **at least one PDF engine**. [Typst](https://typst.app) is the quickest
  start; a TeX distribution (MacTeX, TeX Live) gives the best results and
  is what you need for LaTeX packages and math-heavy documents.

```sh
brew install pipx pandoc typst              # macOS, the quick start
brew install --cask mactex-no-gui           # optional: full LaTeX (large)
```

```sh
sudo apt install pipx pandoc texlive-xetex  # Debian/Ubuntu
sudo dnf install pipx pandoc texlive-xetex  # Fedora (add Typst with `pdfmd --install typst`)
sudo pacman -S python-pipx pandoc-cli typst texlive   # Arch
```

On any Linux, `pdfmd --install full` (Pandoc and Typst) needs no package manager and no root.

```powershell
py -m pip install --user pipx; py -m pipx ensurepath          # Windows
winget install --id JohnMacFarlane.Pandoc; winget install --id Typst.Typst
```

Every push is tested on Windows, macOS and Linux (Pandoc + Typst: single
files, CSV tables, a book, HTML output); see the
[Test and publish workflow](https://github.com/aliperdehan/pdfmd/actions/workflows/publish.yml).
LaTeX engines aren't part of that automated test on Windows yet.

Optional extras: [Quarto](https://quarto.org) for `.qmd` files,
`pandoc-crossref` for `@fig:`/`@tbl:` references, and LibreOffice for
Office files.

<details>
<summary>Without pipx</summary>

`pdfmd.py` needs Python 3.9+ and runs straight from a clone, with the folders beside it
(`pdfmd_inkmd/` for the no-Pandoc fallback, `pdfmd_office/`, `pdfmd_setup/`, `pdfmd_unicode/`). It also runs
directly, and `pyyaml`/`pypdf` are optional (features that need them are
skipped with a warning):

```sh
git clone https://github.com/aliperdehan/pdfmd.git ~/pdfmd
echo 'alias pdfmd="python3 ~/pdfmd/pdfmd.py"' >> ~/.zshrc   # or ~/.bashrc
```

macOS's built-in `/usr/bin/python3` is 3.9, which is too old; pdfmd says
so and exits.
</details>

Check what `pdfmd` can find on your system:

```console
$ pdfmd --check-dependencies
OK    pandoc  (/opt/homebrew/bin/pandoc)
OK    1. lualatex  (/Library/TeX/texbin/lualatex)
OK    2. xelatex  (/Library/TeX/texbin/xelatex)
OK    3. pdflatex  (/Library/TeX/texbin/pdflatex)
OK    4. latexmk  (/Library/TeX/texbin/latexmk)
OK    5. tectonic  (/opt/homebrew/bin/tectonic)
OK    6. typst  (/opt/homebrew/bin/typst)
OK    7. weasyprint  (/opt/homebrew/bin/weasyprint)
MISS  8. wkhtmltopdf
...
OK    14. soffice  (/Applications/LibreOffice.app/Contents/MacOS/soffice)
OK    quarto (only needed for .qmd files)  (/usr/local/bin/quarto)
```

The numbers are the fallback order, and also shortcuts: `-e 6` means
`-e typst`.

For everything at once, `pdfmd --doctor` is one page on the Markdown-to-PDF tools, fonts
and emoji, PDF reading (batchocr, Tesseract, Poppler, OCR languages), your config file and
the cache, ending with the command that fixes each missing piece:

```console
$ pdfmd --doctor
...
Reading PDFs (PDF to Markdown):
OK    batchocr 1.2.5
MISS  tesseract: not found
MISS  poppler: not found

1 thing(s) to fix:
  1. tesseract (scanned PDFs) and poppler (scanned PDFs)
       brew install tesseract poppler
```

### Tab completion

`pdfmd --completion bash|zsh|fish` prints a completion script, generated from the command
line itself so it never goes out of date:

```sh
pdfmd --completion zsh > ~/.zfunc/_pdfmd                              # ~/.zfunc in $fpath, then compinit
pdfmd --completion bash > ~/.local/share/bash-completion/completions/pdfmd
pdfmd --completion fish > ~/.config/fish/completions/pdfmd.fish
```

### No Pandoc? The built-in fallback

On a machine with no Pandoc, or Pandoc but no PDF engine, `pdfmd` does not
stop: it builds a plain PDF with a pure-Python renderer that `pip` installed
with it, and says so.

```console
$ pdfmd notes.md
NOTE  Pandoc was not found: building with the built-in renderer (inkmd). The output is plain ...
NATIVE  notes.md via inkmd
WARN  native (inkmd): notes.md: 2 math expression(s) set as plain text (Unicode, sub/superscripts, display math centred); ...
OK    notes.md
```

- **[inkmd](https://github.com/eagredev/inkmd)**, written by Dylan Moir (MIT
  licence), is built in (a copy is vendored in `pdfmd_inkmd/`, about 2 MB,
  standard library only, works offline, same input gives the same bytes). It reads
  GitHub-flavoured Markdown: headings, emphasis, lists, task lists, tables,
  code blocks, quotes, links, images, and PNG/JPEG. It cannot typeset math,
  so formulas are set as readable text instead: Greek letters and operators
  as Unicode, `x^2` and `x_i` as super/subscripts, `\frac{a}{b}` as `a/b`,
  and display math (`$$...$$`, `\begin{equation}`, `aligned`) as its own
  centred lines. No bookmarks, no page numbers.
- **md2pdf** ([pymd2pdf](https://pypi.org/project/pymd2pdf/), ReportLab based) is
  used when installed, for documents with footnotes, math or a title:
  `pdfmd --install math` (same as `pip install "pdfmd-cli[math]"`; about
  150 MB, Python 3.11+, installs matplotlib so formulas render offline, centred,
  as real math; the few matplotlib cannot read are set as text like inkmd's).
  Footnotes, bookmarks and syntax-highlighted code come with it.
- `pdfmd --install emoji` (about 11 MB; `pdfmd-cli[emoji]` is the pip way for the
  built-in renderer only) puts the colour emoji font in pdfmd's own fonts folder,
  where the built-in renderer and every engine that can draw colour emoji
  (Typst) find it; without it emoji print as `[rocket]`-style labels in the
  built-in renderer.
- `pdfmd --install full` leaves the fallback behind: it installs **Pandoc** (the
  real binary from PyPI's `pypandoc_binary`, about 35 MB, also `--install pandoc`
  / `pdfmd-cli[pandoc]`) and **Typst** (Typst's own release from GitHub, about
  15 MB, also `--install typst`, checked against the SHA-256 GitHub lists) into
  pdfmd's own folders (`~/.local/share/pdfmd/bin`, `%LOCALAPPDATA%\pdfmd\bin`),
  with no admin rights. A Pandoc or Typst already on your PATH always wins; to
  remove them, `pip uninstall pypandoc_binary` and delete the `typst` file.

Every input is treated as GitHub-flavoured Markdown. Pandoc-only syntax is
converted where possible (`\newpage` and `<!-- pagebreak -->` become a page
break, footnotes become endnotes for inkmd, `$` prices are not mistaken for math)
and removed otherwise (heading and image attributes, `:::` divs, raw LaTeX,
`<!-- comments -->`), with one warning per kind. CSV tables
(`::: {.csv file="data.csv"}`) work as they do with Pandoc. The title, author and date in the
front matter become a title block and the PDF's own title and author; other
front-matter keys (`documentclass`, `header-includes`, `pdfmd-options`) are
listed as not used. There are no filters, preambles, citations, slides, parts or
report mode, and only Markdown input: for any of those, `pdfmd --install full`
(or `brew install pandoc typst`, `winget install JohnMacFarlane.Pandoc Typst.Typst`).

The built-in renderer is chosen automatically only when there is no Pandoc
route; a Pandoc build that fails never falls back to it. Ask for it with
`-e inkmd`, `-e md2pdf` or `-e native`, or `pdf-engine: inkmd` in `pdfmd-options`.
When it runs on a terminal and had to leave something out, `pdfmd` offers the
upgrades above (set `PDFMD_NO_PROMPT=1` to silence that; choosing "don't ask
again" remembers it).

## Usage

Every command below can be run from inside [`examples/`](https://github.com/aliperdehan/pdfmd/tree/main/examples/).

### One document

```sh
pdfmd lecture                 # finds lecture.md, writes lecture.pdf beside it
pdfmd lecture.md --open       # ...and opens it when done
pdfmd ~/notes/lecture.md -d   # write the PDF into the current directory instead
pdfmd lecture -w              # watch: rebuild on every save, until Ctrl+C
```

A bare name is looked up as `<name>.md`. The name can contain dots:
`pdfmd notes-v1.2` builds `notes-v1.2.md`.

If no file has exactly that name, pdfmd also looks at what each document is
called inside: its title, and any `pdfmd-options: {alias: ...}`. Case, spaces,
`_`, `-`, accents and script don't matter (`pdfmd animportantdocument` finds
`An Important Document.md`; `pdfmd glyukoza` finds a document titled
`Глюкоза`), and a unique *start* of a name or title works too, with a warning
saying what it matched (`pdfmd animp`, `pdfmd glucose`). A name that fits two
documents is an error, never a guess; `--no-auto lookup` switches the guessing
off. An exact file name always wins.

**Names in other scripts.** Russian, Ukrainian, Belarusian and Kazakh Cyrillic are
always understood. Other scripts are off until you ask, one pack per script, so
nobody carries tables they don't use: `--translit greek,hangul` (or
`PDFMD_TRANSLIT=greek,hangul`) makes `pdfmd tyche` find `Τύχη.md` and
`pdfmd unmyeong` find `운명.md`. Built in: `greek`, `armenian`, `georgian`,
`hebrew`, `arabic` (consonants only, as the scripts write them), `hangul`
(Revised Romanization) and `kana` (Hepburn). `han` gives pinyin without tones
(`pdfmd mingyun` finds `命運.md`) and `other` covers every remaining script;
they use [pypinyin](https://pypi.org/project/pypinyin/) (MIT) and
[anyascii](https://pypi.org/project/anyascii/) (ISC), installed with
`pdfmd --install translit` (`pip install "pdfmd-cli[translit]"`; about 3 MB).
`--translit all` turns every pack on, `--translit none` even Cyrillic off,
`--translit list` shows what is ready. These are for *finding* a name: plain
letters, no tones, vowels left out where the script leaves them out. Names that
romanize alike (homophones) are listed as ambiguous, never picked between. The
same spelling rules find a section by its heading (`doc#tyche`).

### One section

`pdfmd doc#onlyapart` builds just the section whose heading is "Only a Part"
(down to the next heading of the same or a higher level), written as
`doc.only-a-part.pdf` beside the document. Headings are named the way files
are: case, spaces and spelling don't matter, a unique start works (with a
warning), and so does a `{#label}`. `doc##yield` asks for a level-2 heading,
`doc#results/yield` for one under another, `doc#a+b` for several, and
`pdfmd '#yield'` uses the folder's only Markdown file. `pdfmd doc --list-parts`
shows what can be named. In a document split into parts the same names work
for headings inside the parts.

Anything with a `{#label}` can be named too: `pdfmd doc#fig:setup` builds just
that figure, `doc#eq:energy` that equation, and likewise a table, a fenced div,
a code block or a span (the figure's number restarts at 1).

### Other output formats

The format is taken from `-o`'s extension, or given explicitly with `--to`:

```sh
pdfmd lecture -o lecture.html
pdfmd lecture -o lecture.docx
pdfmd lecture --to typst -o lecture.typ
pdfmd lecture -o lecture.tex      # a complete, compilable .tex, not a fragment
```

### Word and OpenDocument output

Plain Pandoc ignores `papersize`, `geometry`, `mainfont` and `fontsize` when it writes `.docx`
or `.odt`: you get a Letter page in the default fonts. pdfmd writes them into the *reference
document* Pandoc builds the file from, so the page and the text follow the same front matter as the PDF:

| Front matter | In the Word file |
|---|---|
| `papersize: a4` (also `letter`, `legal`, `a5`, `b5`..., `classoption: [a4paper, landscape]`) | page size and orientation |
| `geometry:` (a list, `margin=2cm`, `top=1in,left=...`, `paperwidth=...`) or `margin:` | page margins |
| `mainfont`, `sansfont`, `monofont`, `CJKmainfont`, `fontsize`, `linestretch`, `lang`, `indent` | body, heading and code fonts, sizes, line spacing, language, first-line indent |

A `.docx` carries font *names*, not fonts, and the person opening it has Times New Roman, not
STIX Two Text. So well-known fonts Word does not ship are mapped to the closest one it does (STIX
Two Text, Libertinus, Latin Modern to Times New Roman; Helvetica Neue, Inter to Arial; JetBrains
Mono, Menlo, Fira Code to Consolas), with an `AUTO OFFICE` note; `office: {fonts: exact}` keeps
your names. Without any of these keys pdfmd's own look applies: black bold headings sized like a LaTeX
article, a centred title block, booktabs-style table rules, Times New Roman and Consolas.

**Your own template.** A reference document decides the page and fonts itself, and pdfmd then
changes only what the document's `office:` block names. It is found, in order, as
`office: {reference-doc: FILE}`, `<name>-reference.docx` or `reference.docx` (`.dotx` works too,
`.odt`/`.ott` for ODT, `.pptx`/`.potx` for slides) beside the document, in its `metadata/` folder or
beside its metadata files, and finally in `~/.config/pdfmd/`. Pandoc's own `--reference-doc` is left
alone. Only builds whose output is `.docx`/`.odt`/`.pptx` look for one. `pdfmd --init-reference`
writes `reference.docx` (also `odt`, `pptx`): Pandoc's styles with pdfmd's look, to restyle in Word.

A template keeps its own style names. `office: {styles: {Heading1: LRH1, BodyText: LRNormal, Table: TableGrid}}`
makes the Heading 1, Body Text and table Pandoc writes look like the template's own `LR H1`, `LR Normal` and
`Table Grid` (a missing Pandoc style is created from the source); `office: {replace: {NULAB-KICKER: "Course
wording"}}` rewrites text in the template's headers and footers; `office: {title-page: true}` gives the first
page a page of its own, without header or footer.

**A LaTeX package can tell pdfmd about itself.** Beside a package's `.sty` (or in an `office/` or `pdfmd/` folder there)
pdfmd looks for `<package>-pdfmd.yaml`, and for its Word support: `<package>-reference.docx`/`.dotx`,
`<package>-office.lua` (the profile above) and `<package>-office.yaml` (the `office:` defaults, with `by-option:`
entries for what an option of `\usepackage[opt]{package}` adds). A document that loads the package gets all of it with
no setting of its own, and a package without these files behaves exactly as before.

`<package>-pdfmd.yaml` holds `latex-keys:`, the front-matter keys the package's macros are filled from
(`experiment: LabExperiment` turns `experiment: Titration` into `\renewcommand{\LabExperiment}{Titration}` after the
preamble), and an optional `office:` section, the same as `<package>-office.yaml`, for a package that wants one file:

```yaml
latex-keys:
  experiment: LabExperiment
  group: LabGroup
office:
  reference-doc: house.dotx
```

```yaml
pdfmd-options:
  office:
    reference-doc: ../templates/house.dotx   # or leave it to be found
    papersize: a4                            # change just this on top of the template
    fonts: exact                             # keep STIX Two Text and friends as named
    style: plain                             # no pdfmd look (headings, title block, table rules)
```

`--no-auto officeref` turns the search off, `--no-auto officestyle` leaves Pandoc's default alone.

**LaTeX in the document.** Pandoc turns `$x^2$` into a Word equation and drops everything else of
LaTeX. For `.docx` and `.odt` pdfmd adds a filter that makes it native where it can:

- `\ce{Ag+(aq) + Cl-(aq) -> AgCl(s)}` (mhchem) and `\si{\gram\per\mole}`, `\SI{5}{\milli\liter}`,
  `\num{1.5e-3}` (siunitx) become formatted text with real subscripts, charges and units, and, inside
  math, Word equation pieces;
- `\begin{equation}`, `align`, `reaction`... become Word equations with their number at the right;
- raw `figure`, `tabular`, lists, `\emph`, `\newpage`... are read by Pandoc's own LaTeX reader;
- `\ref`, `\eqref`, `\cref`, `\Cref`, `\pageref` and the "Figure 3." in front of a caption use the numbers
  LaTeX itself gave (pdfmd builds the PDF once, in its cache, and reads the `.aux`; reused while the sources
  are older), with the caption separator (`labelsep=`) and `\crefname`s of your preamble;
- **what is left is drawn by LaTeX**: tikz, chemfig, a house style's own macros, math Pandoc cannot convert are compiled in
  *your document's own preamble* (the same fonts, packages and macros as the PDF, one fragment to a page), and the
  pages go into the Word file as vector pictures: an SVG with a 300 dpi PNG fallback (Word 2016 and later draw the SVG,
  LibreOffice and older readers the PNG). An inline fragment sits on the text's baseline, a wide one is scaled to the
  text width, a figure's caption stays text with its number. `\includegraphics{plot.pdf}` and `![](plot.pdf)` (Word cannot
  show a PDF) are converted the same way. Pictures are cached by content, so a rebuild draws only what changed
  (`pdfmd --clear-cache` empties it). A fragment that will not compile is named in a warning and left out; the rest of
  the document is built. Needs `pdftocairo` (Poppler) and a LaTeX engine; without them the fragments are reported only.
- **a house style's own macros** can be told to pdfmd: `office.lua` (or `<name>-office.lua`) beside the document, in its
  `metadata/` folder or in `~/.config/pdfmd/`, or `office: {profile: FILE}`, is a small Lua file:
  `return {ignore = {"\\LabCaptionBegin"}, commands = {prelab = function(args) return {pandoc.Strong{pandoc.Str("[pre-lab " .. args[1] .. "]")}} end}}`
  says which macros to drop and what the others mean in a Word file (a command may return text, or blocks such as a
  native table); an optional `pandoc = function(doc, helpers)` hook may restructure the whole document. The helpers
  include `inlines(tex)`/`blocks(tex)` (LaTeX read with the filter's own math, `\ce` and `\si` applied),
  `read_file(name)` (a file the document's `\input` would find), `number_caption(table, "table")`, `labels()`,
  `preamble()`, `meta()`, `warn(text)`; a profile can thus build a house table from the package's own data, as nulabreport
  does for `\chemicals`.
- what cannot be done at all is named in a warning (`-v` lists it).

`pdfmd report.md --check-docx` says what a Word build would make native and what it would draw as pictures, naming the
environment or macro behind each (`the tikzpicture environment`, `the macro \irspectrum`), without drawing or writing anything: a
quick way to see what is left to give a recipe (see the profile below).

`pdfmd-options: {office: {latex: auto}}` is the default; `latex: images` draws everything LaTeX says as a picture
(formulas, `\ce` and units too, instead of making them native); `latex: off` or `--no-auto officelatex` skips all of it
(Pandoc's own behaviour). `office: {labels: off}` skips the PDF build (numbers are then counted).

The same filter serves the other outputs when LaTeX is the problem: **the soffice fallback** (the Word file above, then LibreOffice: `pdfmd -e soffice report.md` is the `.docx` as LibreOffice draws it) now
keeps the page size, margins and fonts, shows equations and draws what LaTeX can; a **Typst or WeasyPrint run after LaTeX
failed** gets what the document says in LaTeX as native text or pictures instead of nothing; and HTML, Typst and
WeasyPrint builds do it on request (`pdfmd-options: {office: {latex: auto}}`).

### Stopping part-way

`--stop-at` ends the build after a stage; everything before it runs as normal:

```sh
pdfmd report --stop-at markdown   # report.assembled.md: the parts joined into one file
pdfmd report --assemble-only      # the same, shorter
pdfmd report --stop-at tex        # the standalone .tex a LaTeX engine would get (= --to latex)
```

The assembled file holds just the document text (and is marked
`pdfmd-assembled: true`), so pdfmd never joins its parts a second time.

By default it holds just the text. `--embed-metadata` also folds in what pdfmd
finds beside the document (metadata, preamble, Lua filters, and the
bibliography and CSL files the metadata names), so the file no longer needs
them beside it. What the text points at otherwise (images, files a preamble
`\input`s) is not embedded: keep it where the document finds it, relative to
the assembled file.

```sh
pdfmd report --assemble-only --embed-metadata                  # metadata.yaml, preamble.tex, Lua filters, .bib/.csl
pdfmd report --assemble-only --embed-metadata metadata preamble   # only those
pdfmd report --assemble-only --embed-metadata --lua-mode ref   # name the filter instead of copying it
```

An embedded Lua filter sits in a `{=pdfmd}` block at the end of the file. A
Lua filter can run any command, so one only runs if this machine's pdfmd
embedded it (otherwise it is skipped with a warning, unless you pass
`--trust-embedded`).

`--lua-mode apply` runs the filters at assembly time instead, so the text
already has their effect (approximate: Pandoc re-writes the text, and a filter
that looks at `FORMAT` is embedded instead). `--unpack` goes the other way:

```sh
pdfmd report.assembled.md --unpack     # filters, preamble and metadata back into report.assembled.unpacked/
```

`pdfmd` finds `report.assembled.unpacked/` beside `report.assembled.md` by
itself (its metadata, preambles and Lua filters), and `--unpack --slim` strips
the unpacked parts out of the assembled file, leaving the lean document plus
that folder.

A document can name its own files and set what to embed, in `pdfmd-options`:

```yaml
pdfmd-options:
  yaml: [base.yaml]        # metadata files (like -y); also `metadata:`, or grouped:
  metadata:
    preamble: my-preamble.tex
    lua-filter: my.lua
  embed: {lua: ref}        # what --assemble-only embeds without the flag
```

Plain HTML output is a fragment. For a finished page, or one file with
everything (images, CSS) inlined, ask for it, on the command line or in the
document:

```sh
pdfmd lecture -o lecture.html --self-contained
```

```yaml
pdfmd-options:
  default-output: html     # build to HTML when no format is given
  html: {self-contained: true, css: style.css}
```

### The PDF carries its own source

A PDF can hold the document it was built from, so the file you send is also the
file you can edit again. Ask for it, on the command line or in the document:

```sh
pdfmd report --attach-source     # the source goes into report.pdf as an attachment
pdfmd report --bundle            # ... and the data and files its LaTeX reads
pdfmd --restore report.pdf       # write the folder back into report.restored/
```

```yaml
pdfmd-options:
  attach-source: true            # alias: embed-source
  bundle: true                   # or `all`: the whole folder, not just what the text points at
  bundle-packages: true          # also your own LaTeX packages (see below)
  strip-comments: true           # the default for the attached copy; see "Comments"
  attach-bibliography: used      # or `all`
```

Put these in the shared metadata file and every document that finds it carries
its source. The attachment is the assembled Markdown with the metadata,
preamble, Lua filters, bibliography and CSL style folded in (the file
`--assemble-only --embed-metadata` writes), plus a manifest of the original
layout, so `--restore` gives back `report.md`, `metadata/`, `parts/` and the rest
where they were, each as a standalone file (a symlinked metadata file or
bibliography comes back as a copy). Any PDF viewer lists the attachments, and
`pdfmd --restore report.pdf --list` shows them and what a rebuild needs. A
restored folder builds the same document: checked on lab reports with a house
style, a compound library, a shared bibliography and parts.

- **Images come out of the PDF itself.** The PDF holds every picture it drew, so
  a plain attach needs no bundle for them: a JPEG comes back byte for byte, a PNG
  as the same pixels (alpha kept), and an SVG or PDF figure as a vector PDF
  (`fig.svg` becomes `fig.pdf`, and the restored Markdown follows).
- **`--bundle` is for what the PDF does not draw:** CSV data, LaTeX included
  with `\input`, listings. They are stored as separate attachments (`files/...`),
  found from the text, the preamble and, in turn, from the files found; also
  those only your own TeX tree resolves (`\input{library}` from `texmf-home`).
  `--bundle all` takes the whole folder except output and housekeeping. Over
  100 MB (`bundle-max-mb`) only the source is attached. Data whose file name a
  macro builds cannot be found: use `all`.
- **Your own LaTeX packages** (a house style in `texmf-home`) are recorded with
  their version, and `--restore` tells you what is missing; `--bundle-packages`
  stores them too (with what they `\input` and the graphics they name).
  The TeX distribution's own packages, fonts and Pandoc are not carried.
- **Comments.** Notes to yourself do not travel: the attached source loses its
  `<!-- -->` comments, the LaTeX preamble's `%` comments, the text between a
  `.bib`'s entries and a CSL file's XML comments. Choose per kind:
  `strip-comments: [preamble, bibliography]` or `{markdown: false}`
  (`--strip-comments-in`, `--keep-comments-in`). Code blocks, `\verb`, `\url` and
  verbatim environments are never touched, and a `%` that closes a line keeps a
  bare `%`, because it swallows the line break. YAML metadata is merged and
  written again, so its `#` comments are always gone.
- **Only the bibliography entries you cite** are attached (and what they
  cross-reference), not a shared file of hundreds; `attach-bibliography: all`
  keeps it whole, and `nocite: '@*'` keeps every entry.
- **It is opt-in, and it is everything you wrote.** An attached source includes
  what the author would not send in an email; check `--list` before sharing.
- `--restore` never overwrites a file and never writes outside its folder. A
  restored Lua filter is code that pdfmd runs beside the document, so restore
  names it: read it first if the PDF is not from you.
- `-r/--report` builds attach their chapters too. A section build (`doc#section`)
  attaches nothing.

### PDF to Markdown

The direction follows the files you give it:

```sh
pdfmd paper.pdf                  # -> paper.md, beside it
pdfmd paper.pdf -o notes/p.md    # an exact file; -o notes/ puts notes/paper.md
pdfmd paper.pdf --to txt         # plain text
pdfmd scan.pdf --lang eng+rus --ocr tesseract --export-images
```

A PDF that carries its own pdfmd source (above) is restored instead; `--extract`
(or naming an output file) reads its pages. Everything else is read by
[batchocr](https://github.com/aliperdehan/batchocr): the text layer in reading
order, OCR for scanned pages, headings, lists, tables, running headers removed,
`<!-- Page N -->` markers (`--no-page-markers`, `--page-breaks`, `--keep-headers`).
pdfmd only routes: any flag it does not know goes to batchocr unchanged, so the
options of [M1ck4's pdfmd](https://github.com/M1ck4/pdfmd) (`--ocr`, `--lang`,
`--export-images`, `--page-breaks`, `--preview-only`, `--stats`, `-q`, `--output`)
work as they did. Install the reader once:

```sh
pdfmd --install batchocr         # pip install batchocr[md] from its GitHub release,
                                 # then offers the system programs below
```

Scanned pages also need **Tesseract** (OCR) and **Poppler** (`pdftotext`, `pdftoppm`).
Those are separate programs with their own builds for every platform, so pdfmd does not
bundle them; `--install batchocr` finds your package manager (Homebrew, apt, dnf, pacman,
zypper, apk, scoop, Chocolatey or winget), shows the exact command and, on an interactive
terminal, runs it if you say yes (`PDFMD_NO_PROMPT=1` only prints it). By hand:

```sh
brew install tesseract poppler                       # macOS (and Linuxbrew)
sudo apt install tesseract-ocr poppler-utils         # Debian/Ubuntu; dnf: tesseract poppler-utils
scoop install tesseract poppler                      # Windows (or choco install ...)
```

OCR languages are packs of their own. `pdfmd --install ocr` lists the Tesseract languages
pdfmd can fetch, and `pdfmd --install ocr:rus,kaz` (or `ru`, `kazakh`, `zh`, `ja`...) downloads
them into pdfmd's own folder, with no admin rights and each file checked against a checksum
pinned in pdfmd (the compact `tessdata_fast` models, Apache-2.0; English and the orientation
model come along). `pdfmd scan.pdf --lang rus` then uses that folder whenever it has every
language you asked for, and Tesseract's own languages otherwise (a `TESSDATA_PREFIX` you set
always wins). `pdfmd --uninstall ocr:rus` removes one. The package managers have them too:
`brew install tesseract-lang`, `apt install tesseract-ocr-rus`, `dnf install
tesseract-langpack-rus`. `pdfmd --check-dependencies` reports batchocr, Tesseract and Poppler.

Credits and licences: batchocr's Markdown structure stages are M1ck4's
(MIT; that project is archived) and are vendored inside batchocr with their
licence. PyMuPDF, which they use, is AGPL-3.0: it is installed as its own
package by batchocr's `md` extra and is never part of pdfmd. The command name
`pdfmd` is also used by that project and by an unrelated PyPI package of the same
name; this one installs as `pdfmd-cli` (and `pdfmd`), so if two are installed use
`pdfmd-cli` to be sure which one runs.

### Bookmarks, header and footer, linked files

Ideas from [mdpdf](https://github.com/normanlorrain/mdpdf) (MIT), done on the
finished PDF with pypdf, so they work with every engine. All off unless you ask:

```sh
pdfmd report.md --bookmarks                    # PDF bookmarks from the headings, if the engine made none
pdfmd report.md --header "{title},,{date}" --footer ",Page {page} of {pages},{header}"
pdfmd report.md --attach-links                 # the local files the text links to travel inside the PDF
pdfmd report.md --pdf-author "A. Writer" --pdf-keywords "kinetics, rate"  --paper letter
```

A template is `left,middle,right`; `{page} {pages} {header} {date} {title}` are
filled in per page (`{header}` is the current top-level heading; write `\,` for a
comma inside a field). The text is Helvetica, so letters outside Latin-1 become
their base letter or `?`. `--attach-links` stores each linked file as
`linked/PATH` and puts a paperclip in the margin beside the link.

### Use it from Python

```python
import pdfmd

pdfmd.convert_file("report.md", "docx")                      # -> Path("report.docx")
pdfmd.convert_file("report.md", "pdf", "out/report.pdf", variables={"geometry": "margin=2cm"},
                   extra_args=["--engine", "typst"])
html = pdfmd.convert_text("# Hi\n\nSome *text*.\n", "html")   # str for text formats, bytes for pdf/docx/odt/pptx/epub
rst = pdfmd.convert_text(open("notes.rst").read(), "docx", format="rst")
```

Each call runs the command-line tool (as `pypandoc` runs Pandoc), so a document builds exactly as `pdfmd` would build it,
with all the auto-discovery of the document's folder, and nothing in the caller's process is touched. The source is not
stamped or backed up unless you ask (`stamp=True`, `backup=True`). A failure raises `pdfmd.PdfmdError` (with
`returncode`, `stdout` and `stderr`); `check=False` returns the path anyway. `metadata=` takes metadata files,
`variables=` a dict of Pandoc variables, `extra_args=` anything else the command line takes, `cwd=` the folder it runs
in and `timeout=` seconds.

### Other command names: `mdpdf` and `inkmd`

pdfmd also installs `mdpdf` and `inkmd` commands that take those tools' own keys
and do what they did, with pdfmd behind them:

```sh
mdpdf -o out.pdf -f ",,{page}" -a "Name" -p A4 chapter1.md chapter2.md
inkmd notes.md -o notes.pdf --page-size a4 --family times
cat notes.md | inkmd > notes.pdf            # standard input and output, like inkmd
inkmd notes.md -e lualatex                   # naming another engine uses it instead
```

`mdpdf` turns bookmarks and attached links on and combines several inputs into one
PDF. `inkmd` is `pdfmd -e inkmd`; like inkmd it writes the PDF to standard output
when you give `-o -`, or no `-o` while output is piped (at a terminal it writes
`notes.pdf` beside the file instead). The default page is pdfmd's, not Letter: pass
`-p letter` / `--page-size letter`. If the original `mdpdf` or `inkmd` package is
installed too, whichever was installed last owns the command name; both accept the
original's keys.

### Slides

```sh
pdfmd slides -p                   # Beamer slides; each heading starts a slide
```

<p align="center">
  <img src="https://raw.githubusercontent.com/aliperdehan/pdfmd/main/docs/slides.png" width="380" alt="A Beamer slide from examples/slides.md">
</p>

### A whole folder

```console
$ pdfmd notes -b
AUTO: READER TITLE MARGIN MONOFONT. Use --verbose to see in full
AUTO: MARGIN. Use --verbose to see in full
AUTO: MARGIN. Use --verbose to see in full
OK    notes/lecture.md
OK    notes/week1.md
OK    notes/week2.md
```

`-b` converts every `.md` in the folder into its own PDF, in parallel
(`-j N` sets the number of workers). Add `--recursive` to include
subfolders, and `-o DIR` to collect the PDFs somewhere else.

### A book or report from several files

```console
$ pdfmd book -r -o book.pdf
OK    book/01-intro.md
OK    book/02-methods.md
AUTO: MARGIN. Use --verbose to see in full
OK    REPORT  book.pdf
```

`-r` (also spelled `--report` or `--book`) joins every `.md` in the folder
into a single PDF, in the order of each file's `chapter:` front-matter
field. See [`examples/book/`](https://github.com/aliperdehan/pdfmd/tree/main/examples/book/). `-i FILE` leaves one file
out, and `--exclude-unnumbered` skips files without a `chapter:`.

### One long document in several files

For an article-style document that has grown too long to edit as one file
(and unlike `-r`, one that should read as a single document, not a
sequence of chapters), keep a *scaffold* with the front matter, and the
text in a `parts/` folder beside it, one file per section, each starting with
its own heading:

```
report.md                    front matter only (title, author, ...)
parts/10-introduction.md
parts/20-methods.md
parts/30-discussion.md
```

Switch it on once, in a `metadata.yaml` shared by your documents, so the
content files carry no typesetting:

```yaml
pdfmd-options:
  parts: auto        # a document is a scaffold only if parts/ or sections/ exists
```

```console
$ pdfmd report                  # the whole document, report.pdf
$ pdfmd report#methods          # just that part, report.methods.pdf
$ pdfmd report#discussion+appendix      # several: always in report order
$ pdfmd parts/20-methods.md     # same as report#methods
$ pdfmd report --list-parts
$ pdfmd old-report.md --split new-folder   # cut an existing single file into parts
$ pdfmd old-report.md --split new-folder --split-depth 2   # ...and subsections too
```

The parts are joined in filename order into one Pandoc run, so the result is
identical to the same text in a single file: labels, citations and numbering
work across parts, and paths are written relative to the scaffold's folder
whichever part they are in. A part rebuilt alone is much faster to compile
but cannot see the others, so references to them print as `??`. See
[`examples/parts/`](https://github.com/aliperdehan/pdfmd/tree/main/examples/parts/).

#### Faster rebuilds: the cache

```yaml
pdfmd-options:
  cache: {aux: true}      # or: pdfmd report --cache
```

keeps LaTeX's cross-reference files between builds (in `~/.cache/pdfmd`), so
an unchanged document is typeset once instead of two or three times, and a
part built on its own shows the real numbers of the parts left out (taken
from the last full build) instead of `??`. It never skips a build: Pandoc and
LaTeX still process the whole document from the current sources and package
every time, so a change shows in the next build. `cache: {plots: true}` (or
`--cache-plots`, with nulabreport >= 1.26.0) additionally stores each plot as a
PDF and reuses it until the package, the preamble, the engine or the plot's
data file changes. Off by default; `--no-cache` for one build; `pdfmd --clear-cache`
(or deleting the folder) is always safe.

**Where the cache lives.** By default in `~/.cache/pdfmd`, one folder per document.
Folders get moved (a lab report from Downloads into OneDrive), and a cache keyed by
the old path would be lost: so each cache folder records which document it is, and a
document with no cache under its new path takes over the one of the same document
that has lost its original: the same content (SHA-256), or, if you edited it before
moving it, the same name in a folder of the same name, when only one fits. A copy
(the original still there) never takes the original's cache, and plot entries find
their data files again under the new folders. Or keep the cache with the document:

```yaml
pdfmd-options:
  cache: {aux: true, location: document}   # or: --cache-location document
```

puts it in a `.cache/pdfmd` folder beside the document (with a `CACHEDIR.TAG`, so
backup tools skip it, and a `.gitignore`), which travels with the folder. It is
yours to choose per document, in the config file for everything, or with
`--cache-location`. `--clear-cache` clears both places. (The colour-emoji pictures
LaTeX uses are in the same cache.)

### Tables straight from a CSV file

```markdown
Measured values:

::: {.csv file="data.csv"}
:::
```

<p align="center">
  <img src="https://raw.githubusercontent.com/aliperdehan/pdfmd/main/docs/results.png" width="480" alt="A CSV file rendered as a table">
</p>

Or write the data in the document itself, in a code block so that nothing in it is read as Markdown:

````markdown
::: {.csv align="lrr"}
```
Compound,Mass (g),Price
Water,18.015,1.20
"Ethanol, dry",46.07,3.45
```
:::

: Masses and prices {#tbl:m}
````

- Cells are read as Pandoc Markdown (`H~2~O`, `$x^2$`, `\ce{...}`, `[@key]`); `reader="gfm"` makes them plain GFM.
- A caption is the line after the block (`: Caption {#tbl:id}`, or `Table: Caption`), or `caption="Caption"` inside the
  braces, with the identifier as `#tbl:id` there too. A caption in the attributes wins over a line after the block.
- A relative `file=` is found beside the document (and along the resource path), wherever Pandoc runs. With both
  `file=` and data inside the block, the file is used.
- The delimiter is `delimiter=";"` or its name (`semicolon`, `tab`, `pipe`, `space`, `colon`, `comma`); without one it
  comes from the extension (`.tsv` means tab) or from the first line (whichever of `,` `;` tab `|` it holds most of).
- Columns are aligned with `align="lcr"` (or `align="left,center,right"`), or by a second row in the data made of
  `---`, `:--`, `:-:`, `--:` as in a pipe table; `align=` wins. If such a row is really data, say `separator="none"`.
  `widths="5,1,1"` sets relative widths, and a second row with unequal dashes does too. Without either, pdfmd picks
  widths that suit the contents.
- The first row is the header unless you add `header="false"`.
- Large files are capped at 10 rows × 7 columns, so a huge CSV can't
  silently fill 40 pages. `rows=all` or `cols=20` raise the cap. When a
  table is cut, the PDF itself shows a note saying so.

This works for every output format.

#### Turning tables into CSV blocks, and back

```
pdfmd --extract-tables report.md      # every table becomes a .csv block reading tables/<name>.csv
pdfmd --expand-tables report.md       # and back to ordinary tables
```

`--extract-tables` rewrites the document in place, after copying the old one to the backup folder, and says so. Pipe,
simple, multiline and grid tables are all read (the ones inside code blocks are not tables). The files are named after
the captions (`Masses and prices` gives `tables/masses-and-prices.csv`), or `table1`, `table2` by position;
`--table-names a,b,c` names them, and a list that does not match the number of tables is an error that changes nothing.
The caption, the alignment and the widths the document chose stay as attributes of the block, and before anything is
written Pandoc reads the old and the new document and the tables must come out the same. A table Pandoc cannot write
as CSV (a list inside a cell, a cell spanning rows, no header row) is left as it is, with the reason; so is every
`.csv` block already in the document, and if the check fails the whole document is left untouched and the command exits
with an error. A document with no front matter is built as `gfm`, which reads pipe tables only, so only those are
touched there. `--tables-inline` puts the data
inside the document (in a fenced block) instead of in files, `--tables-dir DIR` picks the folder, and `--dry-run` shows
the change without making it. `--expand-tables` is the reverse, every row included.

### Code: wrapping and line numbers

With a LaTeX engine a long line of code wraps at the margin instead of running off the page (a long path or option list
breaks where the line is full), and `{wrap=false}` on one block, `--no-code-wrap` or `code-wrap: false` in
`pdfmd-options` lets it run on. Line numbers are off until you ask for them:

````markdown
``` {.python .numberLines startFrom=10}
def f(x):
    return x * 2
```
````

`--line-numbers` (or `pdfmd-options: {line-numbers: true}`, or the setting in `pdfmd --setup`) numbers every code block,
`--line-numbers 5` numbers every fifth line, `{.noNumberLines}` leaves one block out, and `step=5` and `numbersep=8pt`
adjust a single block.

### Images: SVG and remote ones

LaTeX reads PDF, PNG and JPEG, not SVG. In a LaTeX build pdfmd converts each SVG the document names, once, with
whatever is installed (`rsvg-convert`, Inkscape, `cairosvg`, `svglib`, or LibreOffice, which most machines have), keeps
the PDF by the file's content, and uses it where the document wrote the SVG: a Markdown image, a raw
`\includegraphics{figure.svg}`, a raw `\includesvg{figure}`. A raw `\includegraphics` also gets `graphicx` loaded,
which Pandoc only does for a Markdown image (a PNG in one used to stop the build with "undefined control sequence").
A Markdown image from the web is fetched once and kept for a week, so the build does not need the network again, an SVG
badge works, and a Pandoc built without HTTP support (Homebrew's is) no longer drops it; with no network there is one
warning and the image's description stays. `--no-auto svg` and `--no-auto remoteimages` turn the two off, and
`pdfmd --doctor` says which converter will be used.

### Not just Markdown

```sh
pdfmd paper.tex          # compiled directly with a LaTeX engine: reruns until
                         # references settle, runs bibtex/biber, and leaves
                         # no .aux/.log clutter (--keep-aux keeps them)
pdfmd minutes.docx       # Word/PowerPoint/Excel/ODF: converted by LibreOffice
pdfmd analysis.qmd       # handed to Quarto, so code chunks actually run
pdfmd page.html          # built by WeasyPrint, or a browser if the page runs scripts: no Pandoc
pdfmd note.typ           # compiled by Typst itself: the page setup in the file is kept
pdfmd notes.rst          # anything else Pandoc can read (give the extension)
```

A finished `.typ` or `.html` file goes straight to its own engine, because Pandoc would read it into its own model
and write it out again, and the page size, the styles and the scripts would not survive the trip. For a page that is
WeasyPrint first (it is quiet and needs no browser); a page with `<script>` goes to Chrome, Chromium, Edge or Brave
(headless, printing the page), as does one WeasyPrint cannot draw, and wkhtmltopdf, Prince, pagedjs-cli and LibreOffice
come after. `-e edge` (or `weasyprint`, `chromium`...) picks one. As with an Office file, such a document gets none of
pdfmd's defaults, since it is finished; `--apply-defaults` (also in `pdfmd --setup`) gives it the title, author, date,
language, font, font size, paper and margin of its `metadata.yaml`, ahead of its own settings so those win. A `.tex`
file that no LaTeX engine can compile is tried through Pandoc, with a warning.

The reader comes from the file's extension, as in Pandoc, and a bare name is looked up as `<name>.md`, so give the
extension for anything else. The automatic decisions about Markdown (`READER`, `TITLE`, `citeproc`, `crossref` below)
apply to Markdown files only.

**A plain-text file as Markdown (opt-in).** `pdfmd notes.txt --text-to-markdown` reads a `.txt` file the way a person typed it
and guesses its structure: headings (capitals, `1.2 Title`, `====` underlines), bullet and numbered lists, tables from
columns separated by runs of spaces, indented blocks as code, hard-wrapped lines joined into paragraphs. The words never
change (the letters and digits of the result are the input's), and a text that measures as garbled (symbol soup, OCR
noise, replacement characters) gets paragraphs only, with the rule that fired printed. `MODE` is `auto` (default),
`force` (guess even in a garbled text) or `paragraphs`. It needs batchocr 1.2.5 (`pdfmd --install batchocr`), writes `notes.md`
beside the text (never over a file that is there) and builds from it; with `-o x.md` the conversion is all it does.
Off unless asked: `--text-to-markdown`, or `options: {text-to-markdown: auto}` in the config file (or `pdfmd --setup`).

## What it does automatically

Most of these print an `AUTO` line, and each can be switched off individually.

| `AUTO` kind | When | What happens |
|---|---|---|
| `READER` | a Markdown file with no YAML front matter | reads the file as GitHub-flavoured Markdown (content-sized table columns, relaxed blank-line rules) |
| `TITLE` | a Markdown file with no front matter, first line is `# Title` | that heading becomes the document title, and the remaining headings move up one level |
| `MARGIN` | no margin or geometry set anywhere | 1-inch margins instead of LaTeX's wide defaults |
| `MAINFONT` | no `mainfont:` and no `-f` | STIX Two Text (Times New Roman if it isn't installed), or a serif that has the letters when the document is mostly in a script STIX Two Text lacks (Kazakh Cyrillic, say); retried with DejaVu Serif if a glyph is still missing. A font you name is never changed except by `fallback: document` |
| `UNICODE` | text the main font cannot draw (Arabic, Han, Greek with accents, rare symbols...) | sets each run in an installed font for its script (see *Other scripts*), instead of printing boxes |
| `MONOFONT` | the document contains code | JetBrains Mono for code (Menlo or another installed monospace font if it isn't installed) |
| `tablewidth` | a pipe table with plain `---` separators and long lines | picks the column widths that give the fewest lines within the text width (a column never narrower than its longest word), and gives a table that fits its natural width back; unequal dashes (`--|-----`) are kept, and `table-widths: keep` in `pdfmd-options` leaves every table as written |
| `svg`, `remoteimages` | an SVG, or an image from the web, in a LaTeX build | the SVG is converted to a PDF (once), the remote image is fetched and kept (`--no-auto svg`, `--no-auto remoteimages`) |
| `typstdirect`, `htmldirect` | a `.typ` or `.html` file | built by Typst / WeasyPrint or a browser, not through Pandoc (`--no-auto typstdirect` for the old route) |
| `codewrap` | code blocks in a LaTeX build | long lines wrap at the margin (`--no-code-wrap` or `--no-auto codewrap` for the old behaviour) |
| `YAML` / `TEX` / `LUA` | project files found | attaches `metadata.yaml`, `preamble.tex`, `<name>.lua` (see below) |
| `citeproc` | `@key` / `[@key, p. 90]` citations (as Pandoc reads them: `@key` in a code span or an e-mail address is none) | adds `--citeproc`, so citations and the reference list render from your `bibliography:` without any flag (`--no-citeproc` turns it off) |
| `crossref` | `@fig:`/`@tbl:` references or `{#fig:...}` labels | adds the `pandoc-crossref` filter, ahead of citeproc |
| `papersize` | `pagesize: a4` (a common typo) | converts it to Pandoc's real `papersize:` |

`-v` explains each decision and prints the exact command it runs:

```console
$ pdfmd lecture -v
CMD  pandoc lecture.md -o lecture.pdf --pdf-engine=lualatex -f gfm -V 'mainfont=STIX Two Text' -V geometry:margin=1in -V 'monofont=JetBrains Mono' --shift-heading-level-by=-1 --lua-filter .../pdfmd-tablewidth.lua
CMD  pandoc lecture.md -o lecture.pdf --pdf-engine=lualatex -f gfm -V 'mainfont=DejaVu Serif' ...
AUTO READER  lecture.md: no YAML front matter; reading as gfm
AUTO TITLE  lecture.md: promoted leading '# ' heading to Pandoc title metadata
AUTO MARGIN  lecture.md: no geometry/margin set; using geometry:margin=1in on LaTeX-family engines
AUTO MONOFONT  lecture.md: has code but no monofont set; using JetBrains Mono on LaTeX-family engines
OK    lecture.md
```

The second `CMD` line is the font fallback at work: STIX Two Text was
missing a glyph, so the document was rebuilt with DejaVu Serif. (Temporary
file paths are shortened here.)

**When a PDF doesn't look the way the Markdown suggests, run `-v` first.**
The cause is usually one of these automatic decisions, and `-v` names it.

### Other scripts

<p align="center">
  <img src="https://raw.githubusercontent.com/aliperdehan/pdfmd/main/docs/scripts.png" width="560" alt="examples/scripts.md: Kazakh, Greek, Arabic, Hebrew, Chinese, Japanese, Korean and Hindi text, and emoji, in one PDF">
</p>

(That is [`examples/scripts.md`](https://github.com/aliperdehan/pdfmd/blob/main/examples/scripts.md), built with no configuration.)

A document that mixes scripts needs more than one font. With lualatex or
xelatex, `pdfmd` reads the character tables of your installed fonts, finds
the characters the main font cannot draw and sets each run of them in a font
that can: Arabic and Hebrew right to left, Chinese/Japanese/Korean in the
flavour the text (kana, hangul) or `lang:` points to, punctuation and marks in
the font of the text beside them. Characters that no installed font has are
named in a warning, never dropped or swapped for something else. `-v` shows
which font each script got.

**How much changes is up to you** (`pdfmd-options: {fallback: MODE}`, `--fallback MODE`,
or the config file's `options:`):

| `fallback:` | What happens to a character the main font lacks |
|---|---|
| `word` (default) | the whole word goes in one fallback font that draws all of it, so no word mixes two fonts; your main font stays for every other word, even if the document names `DejaVu Serif` |
| `char` | just that character is set in another installed font |
| `document` | the installed font that draws most of the document replaces the main font (the old retry-with-DejaVu idea, chosen by coverage) |
| `off` (or `false`) | nothing: what Pandoc and TeX do without pdfmd (a missing glyph vanishes or prints a box, and they warn) |
| `box` | no fallback; each missing character is drawn as a black box, so it cannot be overlooked |
| `error` | no fallback; the build stops, naming the missing characters |

`pdfmd --check-fonts doc.md` shows what would happen without building: the main font (and
why it was changed, if it was), which scripts get which fallback font, the characters no
installed font draws and the `--install fonts:...` that would fix it; it exits 1 when
something can't be drawn.

Code is held to the same standard: a character the monofont lacks (an arrow, a CJK
comment) in inline code or a code block is set in a fallback font under LaTeX (a code
block that needs one is typeset as plain verbatim, without syntax highlighting), and
through Typst's `codefont` list or a CSS font stack on Typst and WeasyPrint. Math is
left to its own font.

`missing: warn | box | error` (`--missing`) says what happens to a character that *no* installed
font draws, after the fallback (`box` and `error` as a fallback mode imply it). `char`,
`word` and `document` also turn emoji into pictures under LaTeX; `off`, `box` and
`error` leave them alone.

Emoji are set as pictures with lualatex and xelatex (which cannot draw colour
fonts): each emoji, flag, skin tone, family or keycap is looked up in the colour
emoji font (`pdfmd --install emoji`, a system Noto Color Emoji, or else Apple Color Emoji on
a Mac), its picture taken out of the font file and included at the height of the text, in
inline code and code blocks too. Apple's font is read through its glyph names (the same
way for single emoji, skin tones, flags, keycaps and the joined emoji it has a glyph for,
such as a woman scientist); the few it composes in tables pdfmd does not read (a family of
four, say) are reported as undrawable (install Noto for those). The pictures
are kept in pdfmd's cache folder; a `.tex` written with `--to latex` points
there.

The same fallback works with Typst (`-e typst`: `#text(font: ...)` runs, and
the fonts folder handed to Typst) and WeasyPrint (styled spans). WeasyPrint draws
Noto Color Emoji's bitmaps badly, so emoji are left to the system's own emoji font
there; Typst draws them well.

**Getting fonts.** Anything installed on the machine is used. For the rest,
`pdfmd --install fonts` lists what pdfmd can fetch and
`pdfmd --install fonts:arabic,cjk-sc` (or `fonts:core`, `fonts:scripts`,
`fonts:all`; also `fonts:ja`, `fonts:kazakh`...) fetches it into pdfmd's own
folder (`~/.local/share/pdfmd/fonts`, `%LOCALAPPDATA%\pdfmd\fonts`; no admin
rights, nothing system-wide). Every file is checked against a checksum pinned in
pdfmd before it is kept, and each package keeps its licence beside it (all SIL OFL,
except DejaVu's own free licence). The list: STIX Two (pdfmd's default main font),
JetBrains Mono (its default code font), Noto Serif, Amiri and Noto Naskh Arabic,
Hebrew, Armenian, Georgian, the Indic and Southeast Asian scripts, Syriac,
Thaana, Cherokee, Oriya, Mongolian, Coptic, Gothic, Runic, Tifinagh, N'Ko,
Canadian syllabics, Urdu Nastaliq (used for `lang: ur`), sans-serif Indic faces,
symbols, Noto Serif for Chinese (simplified/traditional), Japanese and Korean (one
weight each, bold is synthesised) and the Noto Sans CJK ones (`cjk-sans`), DejaVu,
and colour emoji. When a document needs a script no installed font has, the warning names
the package to install. `pdfmd --uninstall fonts:NAME` removes some.

It stays out of the way of a document that has set up its own fonts per
script (`ucharclasses`, `\newfontfamily`, `xeCJK`, `\babelfont`,
`CJKmainfont`, `mainfontfallback`): `pdfmd-options: {unicode: true}` adds
pdfmd's anyway, and `--no-auto unicode` turns it off.

### Switching defaults off

```sh
pdfmd lecture --no-auto                  # everything off: close to plain pandoc
pdfmd lecture --no-auto margin mainfont  # only these (kinds: reader title margin mainfont monofont tablewidth
                                           #  unicode lookup yaml tex lua ...; `pdfmd --help` lists them)
```

### Passing options to Pandoc

Any option `pdfmd` doesn't recognise is passed straight to Pandoc:

```sh
pdfmd lecture --toc --number-sections
pdfmd lecture -V fontsize=12pt
```

### Settings inside the document

Or put settings in the document itself, so nobody has to remember the flag:

```yaml
---
title: Lab report
pdfmd-options:
  no-auto: [margin, monofont]
  pdf-engine: tex        # only TeX engines; never fall back to HTML ones
---
```

`pdf-engine:` takes an engine name (`lualatex`, `typst`, ...) or a family:
`tex`, `typst`, `html` or `office`. A family limits the fallback chain to
that kind of engine. For example, a document full of chemical structures
can require TeX, and a plain memo can skip the slow LaTeX run. `-e` on the
command line always wins, and a bare `-e` means "try every engine".

### Your own defaults: the config file

`pdfmd --init-config` writes a commented `~/.config/pdfmd/config.yaml`
(`$XDG_CONFIG_HOME`; `%APPDATA%\pdfmd` on Windows), `pdfmd --show-config` says
where it is and what it sets. Its `options:` block takes the same keys as a
document's `pdfmd-options:` and applies to every document, below anything the
document or its metadata files say (the command line beats all of them);
`translit:` is the romanization packs of the name lookup. `PDFMD_CONFIG=other.yaml`
uses another file, `PDFMD_CONFIG=` (empty) none.

```yaml
translit: [greek, hangul]
options:
  fallback: word
  pdf-engine: lualatex
```

**`pdfmd --setup`** changes the same defaults from a menu, without editing the files: a numbered list (nothing to
install, works over ssh), each setting with its choices and what they mean. It covers what a document would otherwise
say in `pdfmd-options:` or its front matter, for every document:

- *global metadata* (a `metadata.yaml` beside the config file, below anything a document's own folder says): author, language,
  paper size, font size, page geometry, main and code font, line spacing, coloured links, table of contents, and for
  citations the bibliography file, the CSL style and linked citations;
- characters a font lacks or none draws, fonts for other scripts, romanization packs;
- the citation engine, the PDF engine, the default output format, HTML (one file, math method), LaTeX and reference
  numbers in Word files;
- PDF finishing (header, footer, bookmarks, attached links) and the source file (the "Compiled with..." stamp, backups,
  comment stripping, attaching the source and its files to the PDF);
- the cache, reading `.txt` as Markdown, and which of pdfmd's automatic behaviours (`--no-auto` kinds) are off.

Choosing 0 (for a text, `-`) gives a setting its built-in default back; `s` saves, `q` quits. The files are rewritten without your
comments (the old one is kept as `.bak`). The same keys can be written by hand under `options:` of `config.yaml`. A
full-screen version is optional: `pdfmd --install tui` (prompt_toolkit, about 1 MB), then `pdfmd --setup fancy`, or set
"This setup screen" to fancy to make it the one `pdfmd --setup` opens. The first time pdfmd finishes a build in a terminal
with no config file yet, it prints one `TIP` line about `--setup` (never in a pipe, in CI, or from the Python API;
`PDFMD_NO_PROMPT=1` silences it).

The decisions pdfmd remembers for you (the Lua filters it trusts, an offer you
dismissed) live in the same folder, not in `~/.cache/pdfmd`, so cleaning the cache
(`--clear-cache`) cannot lose them; files from an older version are moved there
the first time they are needed.

## Project files

`pdfmd` looks next to the document, and in a `metadata/` folder beside it,
for:

| File | Used as |
|---|---|
| `metadata.yaml` | shared Pandoc metadata (fonts, bibliography, CSL, ...) |
| `<name>.yaml` | per-document metadata, layered on top of `metadata.yaml` |
| `report.yaml` / `book.yaml` | metadata for `-r` builds |
| `preamble.tex`, `latex-preamble.tex`, `<name>-preamble.tex`, `preamble-*.tex` | LaTeX added to the header, generic files first |
| `<name>.lua` | a Pandoc Lua filter for that document |

**Only these names are picked up automatically.** An unrelated `.lua` or
`.tex` file lying in the folder never changes a render. When several YAML
files could apply and none is clearly meant, `pdfmd` stops and asks you to
choose with `-y FILE`, rather than guessing. `-y` alone turns discovery
off.

With a `metadata/` folder, a report's own folder can hold nothing but
`report.md` and `report.pdf`. Relative paths inside the metadata (such as
`bibliography: refs.bib`) resolve from `metadata/`, and image paths in the
document still resolve from the document's own folder.

One shared metadata file can also be **symlinked** into many folders. A
relative `bibliography: refs.bib` inside it then finds the `refs.bib`
next to the file's real copy, so you never need an absolute path.

## Build stamps, history and snapshots

All are off by default.

- **`--stamp`** keeps a `BUILD NOTES` HTML comment at the end of the `.md`
  up to date. It records when the document was compiled and with which
  `pdfmd` version, plus the versions of any LaTeX packages you name with
  `--stamp-packages`. The comment is invisible in the PDF. `--stamp-mode history` also keeps a list of past compiles.
- **`--backup`** saves a timestamped copy of the source into `.backups/` (a hidden folder; an existing `backup/` is kept
  using, and pdfmd says where the first copy went)
  after every successful build. A copy is skipped when nothing changed,
  and `keep: 30` limits how many are kept.

Both can be turned on for a whole folder from `metadata.yaml`:

```yaml
pdfmd-options:
  stamp: true
  backup: { dir: .backups, keep: 30 }
```

**History in a file instead of in the document.** `--stamp-store file` (or `stamp: {store: file}`) writes each compile
to `NAME.hst` in the backup folder, and the document itself is not edited by a build. The file is one line per entry,
newest first, so it reads in any editor, two of them join with `cat`, and `pdfmd --merge-history a.hst b.hst -o all.hst`
keeps every entry once:

```
# pdfmd history of report.md -- one entry per line, newest first: WHEN | KIND | TEXT [| key=value ...]
2026-10-09 11:22:01 | compiled | with nulabreport v1.27.7, pdfmd v3.25.7 | sha=3fa91c0d4b21 out=report.pdf
```

`pdfmd --history-to-file report.md` moves what pdfmd wrote in the document's `BUILD NOTES` into that file, and
`--history-to-notes` moves it back (both back the document up first, `--dry-run` shows). A document may carry several
`BUILD NOTES` blocks (yours, an AI agent's): pdfmd writes only into the one that already holds its own lines, or the
only one there is, or starts one of its own when there are several and none is its; the rest is never touched, and a
line `pdfmd: ignore` in a block keeps pdfmd out of it. The file travels with the document: `--embed-metadata` folds it
in (`hst`), `--unpack` writes it out, and `--attach-source` stores it in the PDF for `--restore`.

Separately, when `pypdf` is installed, every PDF built by `pdfmd` gets two
hidden metadata keys, `PdfmdVersions` and `PdfmdBuildDate`, which you can
read with `pdfinfo -meta`. Turn this off with `--no-stamp-pdf-metadata`.

## Reference

- [`docs/recipes.md`](https://github.com/aliperdehan/pdfmd/blob/main/docs/recipes.md) has short "how do I..." answers: a paper in several scripts, a scanned PDF to Markdown, a folder with a house style, a book from many files.
- `pdfmd --help` lists every flag.
- The docstring at the top of [`pdfmd.py`](https://github.com/aliperdehan/pdfmd/blob/main/pdfmd.py) is the full reference
  for each behaviour and its edge cases.
- [`CHANGELOG.md`](https://github.com/aliperdehan/pdfmd/blob/main/CHANGELOG.md) records what changed in each version and
  why.

## License

[MIT](https://github.com/aliperdehan/pdfmd/blob/main/LICENSE)
