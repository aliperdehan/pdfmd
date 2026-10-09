# Changelog — pdfmd.py

Newest first. Versions follow semver loosely: a **major** bump changes
behavior in a way that could surprise an existing user (a default flips, a
flag's meaning changes), a **minor** bump adds a capability, a **patch**
bump fixes a bug without changing what any flag does.

The version string lives in one place, `pdfmd.py`, right after the module
docstring:

```python
PDFMD_VERSION = "2.0.0"
```

`pdfmd --version` prints it. Bump it there and add an entry here in the
same edit.

<!--
## Why this starts at 2.0.0, not 1.0.0

`pdfmd.py` began as a one-line `pandoc file.md -o file.pdf` wrapper and was
revised many times since — across ChatGPT, ChatGPT Codex, Claude Chat,
Cowork, and Claude Code sessions — with no version marker or changelog kept
at any point. `backups/pdfmd.py.bak-*` has snapshots from a handful of
points in that history, but not from the ChatGPT/Codex/Cowork era at all,
so reconstructing an honest "v1.x" changelog from what's actually on disk
isn't possible — only a partial, misleadingly-precise-looking one. Decided
2026-09-16 (the author): start real changelog tracking now, at 2.0.0, rather than
fabricate the gap. If the full history ever matters, it would need pulling
the actual chat transcripts from each of those tools, not guessing from
diffs between inconsistent backup snapshots.

**Update, 2026-10-05:** an approximate outline of the earlier history has
since been reconstructed, at the very end of this file (see "Before 2.0.0 —
reconstructed history"), from the saved Codex transcripts and the surviving
backup snapshots. It is explicitly NOT reliable: its 1.x numbers are
invented, snapshot-based entries cover windows of days rather than single
changes, and anything done in unsaved sessions (other ChatGPT chats,
claude.ai, Cowork) is missing. Real tracking still begins at 2.0.0.
-->

---

## v3.24.23 — 2026-10-09

Pre-edit state: commit `c54ad1c` (v3.24.22).

### Fixed

- **A preamble in the front matter was drawn as a picture in Word files.** `header-includes: | \usepackage{tikz}` is
  LaTeX for the preamble, but Pandoc's filters walk the metadata too, so the Word filter treated the block as content,
  tried to draw it ("can be used only in preamble"), warned, and listed it in `--check-docx`. The filter now takes
  LaTeX out of `header-includes`, `include-before` and `include-after` before it looks at the document (the Word, ODF,
  HTML and Typst writers do not use it).
- **`office: {latex: images}` did the same as `auto`.** It is now what `--setup` says: formulas, `\ce`, `\si`/`\SI`/`\num`
  and equation environments are drawn by LaTeX as pictures (vector with a PNG fallback) instead of being made native;
  `auto` (the default) still makes them native where it can, `off` is Pandoc's own behaviour.

---

## v3.24.22 — 2026-10-09

Pre-edit state: commit `7cd78d5` (v3.24.21).

### Fixed

- **A `.typst` file was read as Markdown.** Pandoc knows `.typ` but not `.typst`, and an extension it does not know
  means Markdown, so the PDF held the Typst source as text. `.typ` and `.typst` now always give `-f typst` (with an
  `AUTO READER` line for `.typst`, and a Pandoc without the Typst reader fails by name instead of printing the source).
- **The Markdown-only helpers ran on any file.** The scan for `@key` citations (which added `--citeproc`, so a Typst
  `@label` became a citation and printed as `[label]`), the one for pandoc-crossref's syntax and the promotion of a
  leading `# Title` now look at Markdown (`.md`, `.markdown`, `.mdown`, `.mkd`, `.txt`) only.
- **`--to md` failed** ("Unknown output format 'md'"). `--to` takes the names of the files as `default-output:` does:
  `md`, `tex`, `typ`, `txt`, `htm`.

---

## v3.24.21 — 2026-10-09

Pre-edit state: commit `73818f4` (v3.24.20).

### Fixed

- **Parts mode and `doc#section` work with every engine.** The soffice route (`-e soffice`, and the last resort when
  every other engine fails) refused a split document or a section ("the soffice last-resort fallback doesn't support
  parts mode or sections"); the built-in renderers (no Pandoc) refused them too. The soffice route now takes what every
  other engine takes (the document cut down to its sections, the parts joined after it, the partial-build mark), and
  is also given the same corrected inputs as `--to docx` (an embedded preamble is dropped). The built-in renderers
  read the same text as one Markdown file: the parts joined after the document, a heading inside a part cut out of it.
- The built-in renderers no longer list pdfmd's own `pdfmd-assembled`/`pdfmd-partial` marks as "front-matter keys not used".

---

## v3.24.20 — 2026-10-09

Pre-edit state: commit `5900c3b` (v3.24.19).

### Fixed

- **Tables narrower than the page sat at the left margin in the LibreOffice route.** pdfmd's table styles say
  `centre`, but LibreOffice ignores a table style's alignment (Word honours it), so `pdfmd -e soffice` and anything
  else drawn by LibreOffice showed Table 4, 5, 6 and the like flush left while LaTeX centres them. The alignment is now
  written into each table of pdfmd's own styles in the `.docx` itself, after every Word build (the soffice route's
  intermediate file included). A table that already says where it sits, a template's own table style and a house
  style's form table are left alone.

---

## v3.24.19 — 2026-10-08

Pre-edit state: commit `faabca0` (v3.24.18).

### Fixed

- **`AUTO YAML` printed the long path for a symlinked metadata file.** The short (relative) form of a path was worked out
  from the file after following its symlink, so `metadata/metadata.yaml` linking to a shared house-style file outside the
  folder fell back to the absolute path. The folder is resolved, the link itself is not: it is shown where it sits
  (`metadata/metadata.yaml`). The same goes for every other AUTO/CMD line (`--full-paths` still prints absolute paths).

---

## v3.24.18 — 2026-10-08

Pre-edit state: commit `19d7d03` (v3.24.17).

### Fixed

- **`::: {.csv ...}` cells were read as GFM only**, so `H~2~O`, `$x^2$`, `\ce{...}` and `[@key]` in a CSV stayed literal. They are
  read as Pandoc Markdown now (`reader="gfm"` for the old behaviour).
- **A `: Caption` after the block printed as a paragraph**: the caption syntax belongs to a table the reader has already
  seen, and the table was made later by the filter. The filter takes the `: Caption {#tbl:id}` (or `Table: Caption`) paragraph
  after the block as the table's caption and identifier. Moved ahead of pandoc-crossref, the csv filter's tables are numbered and
  referenced like any other (`@tbl:id`); the house convention (`\label{...}` in the caption, `\cref`) works as for a pipe table.
- **A relative `file=` was looked for in the folder of the metadata file** (where Pandoc runs), so a report with `metadata/`
  lost its tables; it is tried beside the document and along the resource path too.

### Added

- **`caption="..."` and `#tbl:id` among the attributes of the block**, instead of a line after it (Markdown allowed in the text).

---

## v3.24.17 — 2026-10-08

Pre-edit state: commit `8233fac` (v3.24.16), which failed its CI run and was never published.

### Fixed

- A `--setup` test that builds an HTML page ran on the CI jobs that have no Pandoc: it is skipped without one.

---

## v3.24.16 — 2026-10-08

Pre-edit state: commit `8c646c7` (v3.24.15).

### Fixed

- `H$_2$O`, `CCl$_4$`, `Fe$^{3+}$` (math that is only a script, its base being the text outside the dollars) came out as an empty box
  before the subscript: it is a real subscript or superscript now.

---

## v3.24.15 — 2026-10-08

Pre-edit state: commit `539f38d` (v3.24.14).

### Added

- **`pdfmd FILE --check-docx`**: what a Word build would make native (formulas, other LaTeX pieces) and what it would draw as
  pictures, each named by the environment or macro behind it, without drawing or writing anything (the first pass of the build
  only).

### Fixed

- A table that was still a picture: `\setcounter{table}{1}\chemicals{...}` (a house filter puts the counter in front) and
  `\chemicals{...}%` newline `{caption}` (a `%` ending a line, which TeX joins) were not recognised as the profile's
  `\chemicals`. A leading `\setcounter` now sets the filter's own counter before the command, and a `%` at a line end joins
  the lines in every raw block.
- A package's shared `chemicals.tex` (found only through TeX's own search path) is found by the filter too (`kpsewhich`, as
  a last resort).
- `PdfmdGrid` tables (the chemicals table, a `tablestyle: grid` table) are centred like the booktabs ones.
- `\ce{C=O}`, `\ce{CH=CH}` (double bond) and `\ce{HC#CH}` (triple) are native text, not pictures.

---

## v3.24.14 — 2026-10-08

Pre-edit state: commit `bd4ba95` (v3.24.13).

### Changed

- **The soffice route goes through the Word file.** `pdfmd -e soffice` (and the last-resort fallback) went Pandoc -> `.odt` ->
  LibreOffice, which lost the cover and tables of a house style and, on a nulabreport report, most of the text. It now writes
  the same `.docx` as `-o x.docx` (template, native equations and tables, pictures for what only LaTeX draws) and has
  LibreOffice turn that into the PDF; with `-e soffice` named explicitly the reference numbers come from LaTeX's own
  `.aux` like a `.docx` build, in the fallback chain they are counted (LaTeX is what failed).
- **`pick:` in a package's office yaml.** A package whose own macros choose its colour scheme says where to read the choice
  (`pick: {default, default-by-option, from-preamble: REGEX, variants}`): the last match in the preamble or the document's
  header-includes names the variant, whose `replace`/`media`/... are merged in, so the Word file follows the PDF
  (nulabreport's `\LabScheme{word|black|gold}` instead of "every course but genchem is black").
- **`--setup` covers what the config can say.** The config file's `options:` is now honoured for the `stamp`, `backup`, `unicode`,
  `header`, `footer`, `bookmarks` and `attach-links` too (it was only read for part of them), and a `metadata.yaml` beside
  `config.yaml` is global metadata, found last, so lowest in priority, whenever metadata is found automatically. The menu lists
  all of these (metadata, citations, output, PDF finishing, the source file, cache, input) and takes text and numbers as
  well as choices.

---

## v3.24.13 — 2026-10-08

Pre-edit state: commit `106b74f` (v3.24.12).

### Added

- **`--text-to-markdown [auto|force|paragraphs]`**: a `.txt` input is read as Markdown through batchocr 1.2.5 (headings,
  lists, tables and paragraphs guessed from how the text is typed; the letters and digits never change; a garbled text gets
  paragraphs only). `-o x.md` is the conversion alone; otherwise `notes.md` is written beside the text (never over an existing
  file) and the build goes on from it. Off unless asked; also `options: {text-to-markdown: ...}` in the config and a
  setting in `pdfmd --setup`.

---

## v3.24.12 — 2026-10-08

Pre-edit state: commit `bce6ad3` (v3.24.10); v3.24.11 above landed in the same commit.

### Added

- **`pdfmd --setup [plain|fancy]`**: change the global defaults from a menu instead of editing `config.yaml`. The default
  screen is a numbered list (no dependency); `pdfmd --install tui` adds prompt_toolkit for a full-screen one
  (`--setup fancy`, or `setup-ui: fancy` in the config; "This setup screen" is itself a setting, and a missing
  prompt_toolkit falls back to the list with a note). Settings: what to do about characters a font lacks or none draws, fonts
  for other scripts, romanization packs, the PDF engine, the default output format, LaTeX and reference numbers in Word
  files, the cache, and which automatic behaviours are off. The file is rewritten without comments (the old one is kept as
  `.bak`). New package `pdfmd_setup`; `--install tui` / `pip install "pdfmd-cli[tui]"`.
- **`no-auto` in the config file** (`options: {no-auto: [margin, monofont]}`) switches those automatic behaviours off for every
  document, merged with the command line's and the document's; `--setup` writes it.
- A one-time `TIP` about `--setup` after the first successful build in an interactive terminal with no config file; never in
  a pipe, in CI or from the Python API (`PDFMD_NO_PROMPT=1` silences it). `--doctor` reports which setup screens exist.

---

## v3.24.11 — 2026-10-08

Pre-edit state: commit `bce6ad3` (v3.24.10).

### Added

- **A Python API**: `pdfmd.convert_file(source, to, outputfile, ...)` and `pdfmd.convert_text(text, to, format, ...)`,
  `pdfmd.PdfmdError`, `pdfmd.pdfmd_version()`. Each call runs the command-line tool as a subprocess (the way `pypandoc` runs
  Pandoc), so a document builds as `pdfmd` builds it and the caller's process is untouched; the source is neither stamped nor
  backed up unless asked. Text outputs come back as `str`, binary ones as `bytes`; any format Pandoc reads can be the input.

---

## v3.24.10 — 2026-10-08

Pre-edit state: commit `7718a2b` (v3.24.9). A package's own table recipe: the chemicals table is native.

### Added

- **A profile can build tables and read the document's files.** The helpers of an office profile now include
  `read_file(name)` (a file of the document's folders: its own, the metadata and preamble folders, as `\input` finds
  them), `number_caption(table, "table")` (the "Table 3." number LaTeX gave), `warn(text)`, and `inlines`/`blocks` now
  carry the filter's own math, `\ce`/`\si` and profile commands through (a LaTeX string of a package's data becomes
  finished Word inlines). nulabreport's profile uses them for `\chemicals{...}{caption}`: its library
  (`\DeclareChemical` of `chemicals.tex`), the house column widths, per-call `key[form]` lines and the caption below.
- A `PdfmdGrid` (ruled all round, tight padding) and a `PdfmdSmall` (80% of the text, a `\footnotesize` table) style in
  every reference document, beside the `PdfmdBooktabs` of 3.24.8. A table cell's custom style must sit on a `Para`
  (Pandoc ignores it on a `Plain`).

### Fixed

- A signed number in math (`$-4$`, `$\sim 825$`, `$>500$`) is text with a real minus sign, not a small equation of its own
  (in a table cell it was a larger, different-looking figure).
- `\allowbreak` in text is not a picture; a `%` at the end of a line in an `\input` file joins it to the next, as TeX does
  (`\chemicals{...}%` over `{caption}`).

---

## v3.24.9 — 2026-10-08

Pre-edit state: commit `c84ece9` (v3.24.8). A package says in its own file what pdfmd cannot know.

### Added

- **`<package>-pdfmd.yaml`**, beside a LaTeX package's `.sty` (or in a `pdfmd/` folder there; found from the preamble's
  `\usepackage` like the Word files). `latex-keys:` maps front-matter keys to the macros they fill
  (`\renewcommand{\Macro}{value}` after the preamble) and an optional `office:` section holds the package's Word/ODT defaults,
  under `<package>-office.yaml` (which may now also sit in `pdfmd/`, as `-office.lua` and `-reference.docx` may). nulabreport
  ships its own (`experiment`, `group`, `course`, `section`, `instructor`, `performed`, `unknown(s)`).
- The package lookup is one `kpsewhich` call for all `\usepackage`d names instead of one each.

### Changed

- `DOCUMENT_LATEX_KEYS` (those nulabreport keys, hard-coded in pdfmd) stays as the fallback for a nulabreport without the
  file, now with a note: the keys of a package's own file are added to it and win. Documents of a package without
  the file build exactly as before; the LaTeX of a nulabreport report is byte-identical with and without it.

---

## v3.24.8 — 2026-10-08

Pre-edit state: commit `5559552` (v3.24.7). The second reading of the Word builds.

### Fixed

- **A block picture sat at the left of its box.** A block fragment (an `\includegraphics` with `width=0.7\linewidth`, a
  spectrum) was typeset in a text-wide box and cropped to that box, so a narrower picture carried empty space on its
  right and, centred as a whole, looked shifted left. Block fragments are now cropped to what they draw on both sides
  (vertically still to the box); the pictures of earlier builds are drawn again (the cache key carries a version).
- **Tables were pictures.** A house filter that rewrites Pandoc tables into raw LaTeX leaves nothing for Word, so the
  table was drawn as a picture; with the filter guarded to LaTeX output (nulabreport v1.27.2) they are Pandoc tables and
  come out native and editable. A table that gives no column widths (a pipe table of short lines) is sized to its text,
  as a LaTeX `tabular` would be, instead of equal columns that broke words in two ("Paracetam-ol"); a `PdfmdBooktabs`
  table style (rules above, below and under the header row) is part of every reference document.
- **A `replace` key with markup in it** (`<w:color .../>`) is now XML for XML, not escaped text, so a header or footer
  colour can be changed (the page number on a black box turned black on black).

---

## v3.24.7 — 2026-10-08

Pre-edit state: commit `095f2e5` (v3.24.6). What reading the six Word builds page by page showed.

### Fixed

- **Pictures were indented like body text** (a picture's paragraph inherited the first-line indent): the `Figure` and
  `Captioned Figure` styles are centred with no indent in every reference document, and pdfmd's own picture
  paragraphs use a centred, unindented `PdfmdCentered` style.
- **`105\,^\circ\text{C}` showed an empty box** before the degree sign (a superscript with nothing before it, here the thin
  space, is a placeholder in Word and LibreOffice): such a degree sign is text.
- **A long display ran off the page.** LaTeX (or the house style) sets it on several lines; Word's equation cannot wrap. A
  display wider than the line (estimated in characters, fractions counted as their wider part) is cut at its top-level
  equals signs into the rows of an aligned block, each row after the first starting with "="; an equation of its own
  `\\`/`&` or `\begin` is left as the author wrote it.
- **`\input{tex/table-x}` was always a picture.** What the file holds now decides (a booktabs `tabular` is a native
  table; whole-line comments are dropped with their line break, as a blank line would end a paragraph inside a tikz
  option list); a file that cannot be read is drawn as before.

### Added

- `office: {media: {word/media/image1.png: logo.png}}` replaces a picture of the template (paths relative to the
  package folder for a package's yaml). nulabreport uses it with `replace` to give every course but genchem the
  black logo and page-number box its PDF has.

---

## v3.24.6 — 2026-10-08

Pre-edit state: commit `574f398` (v3.24.5).

### Changed

- The "Compiled with ..." line pdfmd writes into BUILD NOTES says the format when it is not a PDF:
  "Compiled to docx with nulabreport v1.27.0, pdfmd v3.24.6 -- TIMESTAMP" (a PDF's, and `--to latex`'s, stay as they were;
  `stamp: {include-output: true}` still names the file).

---

## v3.24.5 — 2026-10-08

Pre-edit state: commit `e957078` (v3.24.4).

### Fixed

- The PDF build for a document's reference numbers and the `--to latex` run for its fragments' preamble are pdfmd runs of
  their own: each added a "Compiled with pdfmd" line to the source's BUILD NOTES and might take a snapshot. They run with
  `--no-stamp --no-backup` now; only the build the user asked for writes its note.

---

## v3.24.4 — 2026-10-08

Pre-edit state: commit `8a83d39` (v3.24.3). The other outputs, and what building every CHEM212L/CHEM220L report
to `.docx` showed.

### Added

- **The soffice fallback** (Pandoc -> .odt -> LibreOffice -> PDF) goes through the same reference document and filter:
  papersize, geometry and fonts are kept (it printed Letter in LibreOffice's defaults), equations are numbered, what is
  LaTeX is made native or drawn. No PDF build for numbers there (LaTeX is what failed).
- **Typst and WeasyPrint runs** go through the filter when a LaTeX engine failed before them, or the document says
  `office: {latex: auto}`; the first run lists the fragments as Typst/HTML source instead of building a PDF. HTML,
  Typst and EPUB-like outputs use it only on request.

### Fixed

- Pandoc's LaTeX reader forgets an unknown command and keeps its arguments as text (`\chemicals{a}{b}` became the
  text "b"): a raw block is read only when every command in it is one the reader knows (`\ce`, `\si`, `\cref`... count
  as known: they are translated afterwards), otherwise it is drawn. The two runs of the filter decide this alike.
- A lone `height=` or `width=` on a picture the reader put in a table cell was ignored by the docx writer (three
  TLC plates came out a page wide each); both are now given, the missing one from the picture's proportions.
- A macro that makes a float (a spectrum comparison) failed inside the fragment box ("Not in outer par mode"):
  `figure` and `table` do not float there. A fragment error shows the real LaTeX message (`-file-line-error` form).
- A picture's border: fragments are drawn with 10 bp of room and trimmed back (see 3.24.3); a house style's
  furniture is switched off in them.

### Verified

- All six lab reports of CHEM212L (LR1-2 draft, LR3, LR4-5) and CHEM220L (LR1, LR2, LR2 plain) built to `.docx`
  with the department's template: 3 to 41 LaTeX pictures each, no fragment lost, text 91-98 % the PDF's, page counts
  within a few pages (the PDFs' full-page spectra and wide tables set differently in Word); read page by page
  through LibreOffice.

---

## v3.24.3 — 2026-10-08

Pre-edit state: commit `3fae4a4` (v3.24.2). A house style's own Word template and macros, and what building
real lab reports showed.

### Added

- **Style aliases** (`office: {styles: {Heading1: LRH1, BodyText: LRNormal, Table: TableGrid}}`): Pandoc's styles take the look of
  the template's own differently named ones (a source based on its target only adds its settings, any other
  replaces the look; a Pandoc style the template lacks is made, under the name Pandoc looks it up by).
  **`office: {replace: {FROM: TO}}`** rewrites text in the template's headers and footers;
  **`office: {title-page: true}`** adds `titlePg` (the first page has no header or footer).
- **Packages ship Word support**: beside a local LaTeX package's `.sty` (or in an `office/` folder there):
  `<package>-reference.docx|dotx`, `<package>-office.lua`, `<package>-office.yaml` (defaults for `office:`, with
  `by-option:` for what `\usepackage[opt]{package}` adds); found through `kpsewhich` from the preamble's
  `\usepackage` lines. The document's own `office:` still wins key by key.
- The profile can read the preamble (`helpers.preamble()`), the metadata (`helpers.meta()`), draw a fragment
  (`helpers.fragment`) and rewrite the whole document (`pandoc = function(doc, helpers)`); `PdfmdCentered` style.
- **Fragments**: drawn with a 10 bp border that is trimmed again (an inline one to exactly its box, a block to its box
  and all it draws, through Ghostscript's bbox and pypdf: a picture can reach past its own bounding box); a house style's
  header, footer and furniture are switched off so they cannot land in the crop (the university logo came out
  with a ghost of the running header).
- `\[ ... \]` displays (a house filter wraps `$$...$$` so) are converted like any math; math and macros inside what
  Pandoc's LaTeX reader returned are translated too (they were seen by no filter again).

### Verified

- A real lab report (title page, headers, equations, a chemicals table, figures) built to `.docx` with the
  department's template: cover, logo header, page-number footer with the course's wording, Roman headings,
  numbered equations and cross-references all as in the PDF; checked page by page through LibreOffice.

---

## v3.24.2 — 2026-10-08

Pre-edit state: commit `11431ae` (v3.24.1). What cannot be native is drawn by LaTeX and embedded; a house
style's macros can be declared.

### Added

- **Fragments drawn by LaTeX** (`pdfmd_office/fragments.py`, `docx_post.py`): the filter runs twice. The first run
  lists what it could not make native (unknown raw blocks and inline commands, math Pandoc's converter rejects,
  display environments it cannot convert, the body of a `figure`/`table` it cannot read) and pdfmd compiles
  them in the document's own preamble (taken from a `--to latex` run of the same document, so fonts,
  packages, house macros and the script fallback are the PDF's), one fragment to a `preview` page, all at once
  and, on an error, halved until the fragment that breaks is alone (one engine, no retries; `\newlabel`s of the
  real build are loaded, `\setcounter` restores a captioned float's number). Each page becomes an SVG
  (pdftocairo, glyphs as outlines) and a 300 dpi transparent PNG, with the box's depth. Cached under
  `~/.cache/pdfmd/office/<hash of preamble, engine and labels>/` by content.
- The second run puts them in: a `.docx` gets the PNG as the picture, then **docx_post** adds the SVG as
  Word's `svgBlip` extension beside it (Word 2016+ draws the vector, LibreOffice and older readers the PNG),
  lowers an inline picture by its depth (`w:position`) so it sits on the baseline, scales a picture wider than
  the text to the text width, and clears the marker. `.odt` gets the SVG directly.
- **PDF and EPS pictures** (`\includegraphics{x.pdf}`, `![](x.pdf)`) are converted to SVG and PNG
  (pdftocairo; EPS through epstopdf or Ghostscript), again when the file is newer than its cache entry.
- A `figure`/`table` whose body Pandoc's LaTeX reader would silently drop (tikz, pgfplots, `\input`, any environment
  it does not know) keeps its **caption as text** with its number ("Figure 3. ...") and its body drawn as a
  picture; the reader is only trusted with environments it knows.
- **Profiles**: `office.lua`, `<name>-office.lua`, `nulabreport-office.lua` (beside the document, in `metadata/`, beside
  its metadata files or in `~/.config/pdfmd/`) or `office: {profile: FILE}` tell pdfmd what a house style's own
  macros mean in a Word file: `ignore = {...}`, `commands = {name = function(args, raw, helpers, as_block)}`
  (text, blocks such as a native table, or `{}`), `pandoc = function(doc, helpers)` for the whole document.
  `--no-auto officeprofile`.
- Captions, figures and tables get a Word look of the LaTeX one (centred, italic, 0.9x) in pdfmd's styles.
- `tests/test_office_latex.py`: profile, vector picture with baseline, caching, a failing fragment, PDF picture,
  captioned tikz figure.

### Fixed

- Pandoc's LaTeX reader returns a `figure` with an empty body (no raw block left to notice) when it meets tikz;
  such figures were rendered as a bare caption.
- Reference-number lookups, fragments and the preamble run use `pdfmd` as a subprocess with the same
  `-V`, metadata files and `--no-auto` kinds (`office_pdfmd_command`).

---

## v3.24.1 — 2026-10-08

Pre-edit state: commit `0f9d82e` (v3.24.0). LaTeX the document uses becomes native in Word/ODT output
(tiers 1-3 and numbers; images for what is left follow).

Found by building a lab report to `.docx`: every `\begin{equation}` with `\ce` was dropped, `\ce` and `\si`
stayed literal, references and figures vanished. nulabreport's own filter (unguarded `FixDisplaySpacing`)
also turns display math into LaTeX raw blocks a Word writer drops.

### Added

- **`pdfmd_office/office.lua`**, a Pandoc Lua filter run last for `.docx`/`.odt` (`office: {latex: auto|off}`,
  `--no-auto officelatex`): math Pandoc can convert is kept (checked through the MathML writer, silently);
  **mhchem** `\ce{...}` (species, coefficients, charges, subscripts, states, bonds, hydrates, arrows with
  labels) and **siunitx** `\si \SI \qty \unit \num` (prefixes, powers, `\per`) are translated, in math
  (`\text{...}` runs, so Word and LibreOffice both set them upright) and in text (real subscripts and
  superscripts); `\xoverline`; **display environments** (`equation`, `align`, `gather`, `reaction`...,
  also behind a house filter's `\par\nointerlineskip` wrapper) become a Word equation in a borderless
  three-cell table with the number at the right; raw `figure`/`tabular`/lists/`\emph`... go through Pandoc's
  LaTeX reader; `\newpage` is a page break; `\vspace` and friends are dropped.
- **Numbers from LaTeX**: `\ref \eqref \cref \Cref \autoref \pageref` and the "Figure N. " / "Table N. "
  before captions use `\newlabel`s read from the `.aux` of one PDF build made in the cache (reused while the
  sources are older; `office: {labels: off}` counts instead), cleveref names and the "Equation (1)" form,
  list and pair wording ("Equations (1) and (2)"), the caption separator from `labelsep=`, `\crefname`s and
  `capitalize` read from the preamble and the local packages it loads. A reference with no label is `??`.
  A reference to a single label is a link to it.
- What cannot be made native is counted and named once per run (`-v` lists up to 20): `WARN ... LaTeX the Word
  output could not express: 1 block, 2 inline`.
- `pdfmd_office/labels.py`, `tests/test_office_latex.py`; the reference document gets a `PdfmdEquation` table style.

### Fixed

- nulabreport.lua's `FixDisplaySpacing` was not guarded by the output format (fixed in nulabreport; pdfmd
  runs its filter after the others and reads the wrapped block too, so older copies work).

---

## v3.24.0 — 2026-10-08

Pre-edit state: commit `8beeb9e` (v3.23.23). Word and OpenDocument output follows the document: the
first part of the office-export line (the rest, LaTeX the document cannot express natively, comes in
the 3.24.x patches).

Found by building a lab report (`papersize: a4`, `geometry:`, STIX Two Text) to `.docx`: Pandoc
writes a Letter page in its default fonts and ignores every one of those keys.

### Added

- **`pdfmd_office/`**: `papersize`, `pagesize`, `classoption` (a4paper, landscape...), `geometry:` (every
  spelling: list, comma string, mapping, `margin=`, `top=`/`hmargin=`/`paperwidth=`...), `margin:`,
  `fontsize`, `mainfont`, `sansfont`, `monofont`, `CJKmainfont`, `linestretch`, `lang` and `indent` are
  written into a copy of the reference document before Pandoc runs (page size, margins and orientation
  into the last section, fonts and sizes into `styles.xml`, theme fonts replaced, every other size
  scaled with `fontsize`, `lang` into the defaults, first-line indent into Body Text). `.docx` by
  text edits that keep a Word template's namespaces intact and elements in schema order; `.odt`
  likewise on `styles.xml`.
- **Fonts Word has**: a `.docx` carries font names, so STIX Two Text and its kind map to Times New
  Roman, Helvetica Neue and kind to Arial, JetBrains Mono and kind to Consolas, with an `AUTO OFFICE`
  note; `office: {fonts: exact}` keeps the names. An unknown font is kept, with a note.
- **pdfmd's own Word look** when nothing else says otherwise: black bold headings sized like a LaTeX
  article (1.2x, 1x), a centred title block, booktabs-style table rules, Times New Roman and Consolas
  (`office: {style: plain}` or `--no-auto officestyle` leaves Pandoc's styles).
- **Reference documents are found**, only for `.docx`/`.odt`/`.pptx` output: `office: {reference-doc: F}`,
  `<name>-reference.<ext>`, `reference.<ext>` (`.dotx`/`.ott`/`.potx` too) beside the document, in its
  `metadata/` folder or beside its metadata files, then `~/.config/pdfmd/`. A template keeps its own page
  and fonts; the `office:` block changes just the keys it names. A document's own output is never taken
  as its template. Pandoc's `--reference-doc` is left alone. `--no-auto officeref`.
- **`pdfmd --init-reference [docx|odt|pptx]`** writes `reference.<ext>` (Pandoc's styles with pdfmd's
  look) into the folder, never over an existing one.
- Single files, `-r` reports and `-b` batches all go through it. README section "Word and OpenDocument
  output"; `tests/test_office.py` (units, XML well-formedness and order, discovery, and a LibreOffice
  render that checks the page size).

### Verified

- A 27-document matrix through Pandoc and LibreOffice (A4, Letter, Legal, A5, B5, landscape, every
  geometry/margin spelling, `-V` variables, font sizes, fonts, ODT): page size and margins come out as
  asked, fonts as mapped.

---

## v3.23.23 — 2026-10-08

Pre-edit state: commit `80e8a0a` (v3.23.22). Documentation only.

### Added

- `docs/recipes.md`: "how do I..." answers (scripts and fonts, finding documents by a name in another
  script, scanned PDFs to Markdown, a PDF that carries its source, a folder's house style, books and
  reports, other formats, fast rebuilds, debugging, completion), linked from the README's Reference.

---

## v3.23.22 — 2026-10-08

Pre-edit state: commit `d0afddc` (v3.23.21). Found while making the README's script screenshot: with
Apple Color Emoji a skin tone, a joined emoji and a flag came out as a plain emoji or as boxes, though
3.23.15 said they resolve.

### Fixed

- **Apple Color Emoji sequences**: the font keeps its sequences in AAT tables, but names each glyph
  (`u1F469_u1F52C.3`, `u1F1F0_u1F1FF`, `u0031_u20E3`, `u1F9CE.0.W`); pdfmd reads the `post` table and
  looks a sequence up by that name (the code points without joiners and selectors, a skin tone as
  `.N`, two people `.NN`, a gender sign as `.W`/`.M`). Skin tones, flags, keycaps, tag flags and most
  joined emoji now come out right; a joined emoji the font has no named glyph for (a family of four)
  is reported as undrawn instead of drawn as its first emoji (the Noto path is unchanged).
- `--check-fonts` knew a colour emoji font only if it was Noto; it now counts Apple's, as the build does.

### Added

- `examples/scripts.md` and `docs/scripts.png`, shown in the README's "Other scripts".
- `tests/test_apple_emoji.py`.

---

## v3.23.21 — 2026-10-08

Pre-edit state: commit `202f29b` (v3.23.20).

### Added

- **`pdfmd --completion bash|zsh|fish`** prints a tab-completion script generated from the argument
  parser (flags, their one-line help, the choices of `--stop-at` and the like, the kinds of
  `--install`; fish also completes `fonts:NAME` and `ocr:LANG`; flags that take a file complete
  files). Also registered for `pdfmd-cli`.
- `tests/test_completion.py` (the scripts are syntax-checked in the shells that are there).

---

## v3.23.20 — 2026-10-08

Pre-edit state: commit `25dcb7b` (v3.23.19).

### Added

- **`pdfmd --doctor`**: one report on what pdfmd uses: Pandoc and the PDF engines (and which runs
  first), the Python packages, the default fonts, the fonts pdfmd installed, a colour emoji font, a CJK
  font, the name-lookup packs, batchocr, Tesseract and Poppler, the OCR languages pdfmd holds, the
  config file and the cache; it ends with the command that fixes each missing piece (the same fix is
  listed once). Exit status 0 while a PDF can still be made (the built-in renderer counts).
  `--check-dependencies` and `--check-fonts` are unchanged.
- `tests/test_doctor.py`.

---

## v3.23.19 — 2026-10-08

Pre-edit state: commit `3d169e9` (v3.23.18). OCR languages without a package manager.

### Added

- **`pdfmd --install ocr[:LANG,...]`** lists / fetches Tesseract language files (the `tessdata_fast`
  models, Apache-2.0, 125 languages; `pdfmd_unicode/tessdata.py`, catalog generated by
  `scripts/gen_tessdata_catalog.py` at a pinned commit, every file checked against its git blob
  SHA-1) into `~/.local/share/pdfmd/tessdata` (`%LOCALAPPDATA%\pdfmd\tessdata`), with English and the
  orientation model added so the folder stands on its own. Codes, ISO 639-1 codes and names
  (`ru`, `kazakh`, `zh`, `chi_sim`). `--uninstall ocr:LANG` removes.
- **PDF reading uses it**: `pdfmd scan.pdf --lang rus` runs batchocr with `TESSDATA_PREFIX` at that
  folder when it has every language asked for (English when no `--lang`) and the user has set no
  `TESSDATA_PREFIX`; otherwise Tesseract's own languages are used as before.
- `tests/test_tessdata.py`.

---

## v3.23.18 — 2026-10-08

Pre-edit state: commit `33aae99` (v3.23.17). `--install batchocr` reaches the system programs on
every platform; the README catches up with the 3.23 line.

### Added

- **`pdfmd --install batchocr` offers Tesseract and Poppler** through the system's package manager
  (Homebrew, apt, dnf, pacman, zypper, apk on macOS/Linux; scoop, Chocolatey, winget on Windows): it
  shows the exact command (with `sudo` where the manager needs it and the user is not root) and runs
  it only after a yes on an interactive terminal (`PDFMD_NO_PROMPT=1` or a pipe: printed only). They
  are not bundled: separate programs with their own licences and per-platform builds. OCR languages
  are named per manager, never installed. `--check-dependencies` reports `pdftoppm` too, and the
  hints in it and in the "batchocr not found" message use the manager found instead of a fixed
  macOS/apt/choco line.
- `tests/test_install_ocr.py`.

### Documentation

- README: the Why list now names scripts and emoji, name lookup in any script and PDF reading; the
  Install section has Fedora and Arch lines and says `--install full` needs no root on Linux; the
  PDF-to-Markdown section explains the Tesseract/Poppler step and OCR languages.

---

## v3.23.17 — 2026-10-08

Pre-edit state: commit `a126fa7` (v3.23.16).

### Fixed

- Without fontconfig and without TeX (a typical Windows machine) pdfmd could not tell that a font is
  absent from the system, so a font that exists only in its own fonts folder was named by family and
  failed to load; its own scan of the system font folders answers now (after `fc-list` and
  `luaotfload-tool`).
- The test that compared the generated Unicode script table with fontTools' own copy failed whenever
  fontTools shipped another Unicode version; the table is checked for being well-formed instead
  (`scripts/gen_unicode_scripts.py --check` stays as a development check).

---

## v3.23.16 — 2026-10-08

Pre-edit state: commit `f1110f3` (v3.23.15). Tests only: what the first CI run on Windows and on a
machine without Pandoc showed (nothing of pdfmd itself changed).

### Fixed

- Tests that assumed POSIX paths, `\n` line ends or the XDG folders (Windows uses `%APPDATA%`/
  `%LOCALAPPDATA%`), and two `--assemble-only` tests that need Pandoc now skip without it.

---

## v3.23.15 — 2026-10-08

Pre-edit state: commit `5b25832` (v3.23.14). Emoji pictures: Apple's font, and inside code.

### Added

- **Apple Color Emoji as a picture source** for LaTeX (its `sbix` PNG strikes, largest first, `dupe`
  glyphs followed), used when no Noto Color Emoji is installed. Single emoji, skin tones and most ZWJ
  sequences resolve; flags and keycaps are not found in Apple's font by this reader, so they are
  reported as undrawn (install `pdfmd --install emoji` for those).
- **Emoji in inline code and code blocks** become pictures too. They are referenced by number
  (`\pdfmdemojin{N}`, the path defined in the preamble), because a path cannot be read inside a
  `Verbatim` block. A code block is only rewritten as `Verbatim` when something in it needs work (a digit
  that could begin a keycap does not count).

---

## v3.23.14 — 2026-10-08

Pre-edit state: commit `9e79464` (v3.23.13). The fallback on the natbib/biblatex route.

### Added

- `citation-engine: natbib | biblatex` builds now get the script fallback, the main-font choice and
  managed fonts like every other LaTeX build (the body text only: the bibliography itself is typeset by
  bibtex/biber with the main font). The soffice last-resort fallback is left to LibreOffice's own font
  replacement.

---

## v3.23.13 — 2026-10-08

Pre-edit state: commit `44091c8` (v3.23.12). Code on Typst and WeasyPrint.

### Added

- **Fallback fonts for code on Typst and WeasyPrint**: the characters the code's font lacks (DejaVu
  Sans Mono, Typst's default, or the document's `monofont`; Menlo and friends on WeasyPrint) are set in
  the fallback fonts through Typst's `codefont` list (`-V codefont=...`, which Typst reads glyph by
  glyph) and a CSS `font-family` rule for `code`/`pre`. The main-font choice by script and
  `fallback: document` already applied to every engine (pdfmd's default font, with the `AUTO MAINFONT` note).

---

## v3.23.12 — 2026-10-08

Pre-edit state: commit `4a835b4` (v3.23.11). The cache can live beside the document, and a moved
document finds its cache.

### Added

- **`cache: {location: global | document}`** (`pdfmd-options`, `--cache-location`, the config
  file): `global` (default, unchanged) is `~/.cache/pdfmd`; `document` is `.cache/pdfmd` beside the
  document (self-contained, with `CACHEDIR.TAG` and a `.gitignore`), holding its LaTeX cross-reference
  folder, the plot cache and the emoji pictures. `--clear-cache` clears both places.
- **A moved document finds its cache.** Each cache folder records its document
  (`.pdfmd-source.json`: path, stem, folder name, SHA-256 of the source). A document with no cache
  under its path adopts that of a document whose recorded original no longer exists: same stem and
  same content, or, after an edit, same stem and same folder name when only one such cache is left
  (an `AUTO CACHE` note says so). A copy never takes its original's cache.
- **Plot-cache entries survive a move**: they record the folders they were made in and, when the
  report has moved, their input files are looked for under the new ones (and the entry is re-pointed);
  a changed data file still drops the entry.
- `tests/test_cache_location.py`.

---

## v3.23.11 — 2026-10-08

Pre-edit state: commit `b4bbc31` (v3.23.10). More fonts in the catalog.

### Added

- Catalog (regenerated; every file still pinned): `nastaliq` (Noto Nastaliq Urdu, chosen for text
  in `lang: ur` and the like, the other Arabic-script languages stay in Naskh), `oriya`,
  `mongolian`, `coptic`, `gothic`, `runic`, `canadian`, `tifinagh`, `nko`, `indic-sans` (the
  sans-serif faces of the nine Indic scripts), and `cjk-sans-sc/tc/jp/kr` (Noto Sans CJK subsets,
  regular and bold) with a group `cjk-sans`. `fonts:urdu` installs Naskh and Nastaliq. The group sizes
  in `pdfmd --install fonts` are computed.

---

## v3.23.10 — 2026-10-08

Pre-edit state: commit `2dbf10b` (v3.23.9).

### Added

- **`pdfmd --check-fonts DOC`**: the fonts report without a build: the mode, the main font and why
  it was changed, which scripts (and which code) get which fallback font, emoji, the characters no
  installed font draws and the `--install fonts:...` that would fix it. Exit status 1 when
  something cannot be drawn.

---

## v3.23.9 — 2026-10-08

Pre-edit state: commit `84deaa5` (v3.23.8). Characters in code.

### Added

- **Fallback in code (LaTeX)**: the document's inline code and code blocks are checked against the
  monofont (its own, or JetBrains Mono), and the characters it lacks are set in a fallback font
  (right-to-left runs get their direction), drawn as black boxes (`missing: box`), or counted by
  `missing: error`. A code block that needs one is written as a `fancyvrb` `Verbatim` with
  `commandchars`, so it loses syntax highlighting (blocks with nothing missing are untouched).
  Typst and HTML code are left to their own fallback; math is left to unicode-math.

---

## v3.23.8 — 2026-10-08

Pre-edit state: commit `5ba014b` (v3.23.7).

### Changed

- **`fallback: word` is the default** (no word set half in one font and half in another).
  `fallback: true`/`on`/`yes` mean the default; `false`/`no`/`none` mean `off`.
- **pdfmd's own default main font is chosen by script again**, with an `AUTO MAINFONT` note (shown
  in full with `-v`, as the `AUTO:` summary line otherwise): when no font is named and STIX Two Text
  lacks letters of the script the document is mostly in (Kazakh Cyrillic), a serif that has them
  all is used. A font the document or the command line names is never replaced, except by
  `fallback: document`; `off`, `box` and `error` never choose.

---

## v3.23.7 — 2026-10-08

Pre-edit state: commit `a61741e` (v3.23.6). The fallback is a choice, and by default it
touches only the missing characters.

### Added

- **`fallback: char | word | document | off | box | error`** (`pdfmd-options`, `--fallback`, the
  config file's `options:`; YAML's bare `off`/`no` read as false are understood): `char` is the
  default and sets just the missing characters in another font; `word` sets a whole word in one
  fallback font that draws all of it (a word with nothing missing stays in the main font);
  `document` makes the installed font that draws most of the document the main font, replacing even
  one the document names (`AUTO MAINFONT` says so); `off` is Pandoc's own behaviour (no fonts, no
  emoji pictures, no main-font choice); `box` draws every missing character as a black box (LaTeX
  `\rule`, Typst `#box`, an HTML span); `error` stops the build and lists them.
- **`missing: warn | box | error`** (`--missing`): the same choice for characters no installed font
  draws after the fallback. `box` and `error` as a fallback mode imply it.

### Changed

- **The main font is no longer chosen by script.** 3.23.0 replaced the automatic main font (STIX
  Two Text) by a serif that has all the letters of the document's own script, whatever the mode; a
  document that names its font was never touched, but the default one changed behind the user's back.
  Now only `fallback: document` changes the main font; `char` (default) leaves it and sets the
  missing letters (the Kazakh ә ғ қ ң ө ұ ү һ і in STIX Two Text) in another font.
  `choose_main_font` stays in the package for callers that want it.

---

## v3.23.6 — 2026-10-08

Pre-edit state: commit `0573687` (v3.23.5). A global config file, and the state pdfmd keeps
about the user moved out of the cache.

### Added

- **`~/.config/pdfmd/config.yaml`** (`$XDG_CONFIG_HOME`, `%APPDATA%\pdfmd`; `PDFMD_CONFIG` names
  another file or, empty, none). `options:` = defaults for every document's `pdfmd-options`,
  the lowest source (document, then its metadata files, then the config; the command line
  above all) for the options read through the shared cascade (`default-output`, `parts`,
  `strip-comments`, `embed`, `cache`, `pdf-engine`/`engine`, `citation-engine`, ...);
  `translit:` the lookup's romanization packs (below `--translit` and `PDFMD_TRANSLIT`).
  `--init-config` writes a commented template, `--show-config` reports. A broken file or an
  unknown setting is a WARN, never a failure.

### Changed

- **Persistent decisions left the cache.** The trusted embedded-filter hashes (a security
  allow-list) and the dismissed native-renderer offer were in `~/.cache/pdfmd`, which
  `--clear-cache` (or any cache cleaner) empties; they are now
  `~/.config/pdfmd/trusted-filters.txt` and `native-prompt-dismissed`, moved from the old place
  the first time they are read.
- The test suite points the config and state folders at a temporary one.

---

## v3.23.5 — 2026-10-08

Pre-edit state: commit `2468b07` (v3.23.4).

### Fixed

- Finding a family's regular face without fontconfig (the scan of the font folders used on
  machines without `fc-list`): "Regular" now ranks before "Medium" (a family whose Medium file
  sorted first used to stand for the whole family), and a static font before a variable one.
  Checked on Python 3.9 as well as 3.14.

---

## v3.23.4 — 2026-10-08

Pre-edit state: commit `5a38677` (v3.23.3). Fonts in more places.

### Added

- **A font the document itself names** (`mainfont:`, `sansfont:`, `monofont:`) that exists only
  in pdfmd's fonts folder is loaded by file under LaTeX (`document_font_args`), unless the
  document gives its own `...options:`.
- **Report mode** (`-r`) gets the script fallback, the managed fonts and the main font by script,
  in both its `--to latex` and PDF-engine branches.

---

## v3.23.3 — 2026-10-08

Pre-edit state: commit `bc30b40` (v3.23.2). Finding documents by names in other scripts.

### Added

- **Romanization packs** (`pdfmd_unicode/translit.py`): `--translit PACKS` /
  `PDFMD_TRANSLIT` turns on, per script, the spelling of a name in Latin letters that the
  lookup compares (`pdfmd tyche` finds `Τύχη.md`, `pdfmd unmyeong` `운명.md`,
  `pdfmd mingyun` `命運.md`; headings in `doc#section` too). Own tables, no dependency:
  `greek` (scholarly Latinization: η = e, φ = ph, γκ = nk, ου = ou), `armenian`,
  `georgian`, `hebrew` and `arabic` (consonant skeletons, Persian and Urdu letters),
  `hangul` (Revised Romanization with the usual liaison), `kana` (Hepburn: yoon, small
  vowels, doubled consonants). `han` is pinyin without tones through `pypinyin` (MIT) or
  `anyascii` (ISC), `other` every remaining script through `anyascii`; both are optional
  (`pdfmd --install translit`, `pdfmd-cli[translit]`). `all`, `none`, and `--translit list`.
  Off by default except Cyrillic (Russian, Ukrainian, Belarusian, Kazakh), which stays
  built into `pdfmd.py` exactly as it was; `--translit none` turns that off as well,
  including the exact-name Cyrillic/Latin spellings. Homophones (命運, 銘運) stay ambiguous:
  the existing "fits two documents" error lists them.
- A loose lookup key treats `ph` as `f` (Greek φ is written either way).
- `tests/test_translit.py`.

---

## v3.23.2 — 2026-10-08

Pre-edit state: commit `1505ed8` (v3.23.1). Emoji in lualatex and xelatex.

### Added

- **Emoji as pictures under LaTeX**: the PNG of each emoji is read straight out of a
  colour bitmap font (Noto Color Emoji: the CBDT/CBLC tables, no dependency; the glyph of
  a sequence, a flag, a skin tone, a ZWJ family, a keycap, a tag flag, through the
  font's own GSUB ligatures), kept in `~/.cache/pdfmd/emoji/`, and set by the Lua filter
  as `\pdfmdemoji{...}` (`\includegraphics`, 1.1 em high, raised 0.2 em). Needs the font:
  `pdfmd --install emoji`, or a system Noto Color Emoji; without it the WARN says so.
  A `--to latex` file points at the cached pictures.
- Tests with a synthetic CBDT font written by the test itself.

### Changed

- Cyrillic letters the main font lacks are tried in Noto Serif before PT Serif.
- The ASCII range counts too when a main font lacks it (an explicit `-f` Hebrew-only
  font no longer prints the Latin text as missing glyphs).

---

## v3.23.1 — 2026-10-08

Pre-edit state: commit `28646b0` (v3.23.0). `pdfmd --install fonts`, and the fonts it
fetches used by every engine; emoji and the other scripts on Typst and WeasyPrint.

### Added

- **`pdfmd --install fonts`** lists the fonts pdfmd can fetch (size, state, what for);
  **`--install fonts:NAME[,NAME...]`** fetches them into pdfmd's own folder
  (`~/.local/share/pdfmd/fonts`, `$XDG_DATA_HOME`, `%LOCALAPPDATA%\pdfmd\fonts`), one
  folder per package with its licence beside it, no admin rights, nothing system-wide;
  **`--uninstall fonts:NAME`** removes. Groups `core`, `scripts`, `cjk`, `all`, and
  aliases (`ja`, `zh-tw`, `kazakh`, `persian`...). The catalog
  (`pdfmd_unicode/_catalog.py`, generated by `scripts/gen_font_catalog.py`): STIX Two
  Text and Math, JetBrains Mono, Noto Serif (Latin, Cyrillic with Kazakh, Greek), Amiri
  and Noto Naskh Arabic, Hebrew, Armenian, Georgian, Devanagari, Bengali, Tamil, Telugu,
  Kannada, Malayalam, Gujarati, Gurmukhi, Sinhala, Thai, Lao, Khmer, Myanmar, Tibetan,
  Ethiopic, Syriac, Thaana, Cherokee, symbols, Noto Serif CJK for SC/TC/JP/KR (subset,
  one weight), DejaVu, and Noto Color Emoji. Every file is pinned: by the commit it is
  fetched from and its git blob SHA-1, or by the SHA-256 of the archive it comes out of,
  and refused if it differs. All SIL OFL except DejaVu's own free licence.
- **The fonts are used**: LaTeX loads a font that is only in pdfmd's folder by file name
  and `Path` (`mainfont`/`monofont` options included, so STIX Two Text and JetBrains Mono
  from `--install fonts` become the defaults wherever the machine has none), Typst gets
  `--font-path`, WeasyPrint `@font-face` rules; `font_missing()` knows the folder.
- **The same script runs on Typst and WeasyPrint**: the Lua filter emits `#text(font: ..,
  lang: ..)[..]` for Typst (whose own fallback does not find CJK or Hangul even when the
  fonts are installed) and a `font-family` span for HTML, with the language tag for CJK.
- **Emoji**: told apart from the script fonts (pictographs, regional-indicator flags, and
  symbols such as the heart only with U+FE0F). Typst draws them; WeasyPrint is left to the
  system's emoji font (its handling of Noto Color Emoji's bitmaps is broken: tiny and
  misplaced); LaTeX cannot yet and says so. `--install emoji` now installs the font into
  pdfmd's own folder, where the built-in renderer finds it first (no pip, no `inkmd`
  package needed) and every other engine too.
- When no installed font draws a character the WARN names the package to install
  (`pdfmd --install fonts:cjk-sc`).

### Changed

- A missing-glyph warning that is only about characters no font has (already warned about)
  no longer triggers the retry with DejaVu Serif, which could not help and doubled the time.
- Variation selectors no longer count as letters the main font must have.

---

## v3.23.0 — 2026-10-07

Pre-edit state: commit `b329fc0` (v3.22.9). Script-aware font fallback: the
one-off `header-includes` of a multilingual paper (polyglossia, `ucharclasses`,
a `\newfontfamily` per script, `newunicodechar` rules that swap characters for
look-alikes) done once, properly, for every document.

### Added

- **`pdfmd_unicode/`**, a package beside `pdfmd.py` with no dependencies: the Unicode
  Script property as a generated range table (`scripts/gen_unicode_scripts.py`, from
  fontTools at development time only; `--check` reports drift), a reader of fonts'
  own `name` and `cmap` tables (TrueType/OpenType and collections), the installed
  fonts from fontconfig or a scan of the system font folders plus pdfmd's own folder
  (`~/.local/share/pdfmd/fonts`), and a per-script list of families to try.
- **Fonts for other scripts** (lualatex, xelatex; `AUTO UNICODE`): the characters of
  the document's Markdown, metadata and bibliography files (code excluded) that the
  main font cannot draw are set, run by run, in the first installed font of their
  script's list, by a generated preamble and a Pandoc Lua filter that runs before the
  table-width filter (which renders table cells to LaTeX). Arabic and Hebrew runs get
  a direction, Han characters the Chinese/Japanese/Korean flavour the text or `lang:`
  points to, punctuation and combining marks the font of the text beside them,
  variable fonts (set at their thinnest weight by TeX) are used only when nothing
  else has the glyph. Characters no installed font has are listed in a WARN. The
  fonts that cannot be loaded are dropped and the build retried without them.
  A document with its own script setup (`ucharclasses`, `\newfontfamily`, `xeCJK`,
  `\babelfont`, `CJKmainfont`, `mainfontfallback`) is left alone;
  `pdfmd-options: {unicode: true}` forces it, `--no-auto unicode` disables it.
- **Main font by script** (`AUTO MAINFONT`): when the document is mostly in one
  script and STIX Two Text lacks letters of it (the Kazakh Cyrillic ә ғ қ ң ө ұ ү
  һ і), the first installed serif that has them all (Noto Serif, PT Serif,
  Source Serif 4, DejaVu Serif) becomes the main font, so no word is half one font
  and half another. This replaces most uses of the compile-then-retry with DejaVu Serif,
  which stays as the last resort.
- `tests/test_unicode.py`: synthetic fonts written by the tests themselves, so nothing
  depends on what is installed.

### Verified

- The author's Kazakh/Arabic/Chinese/Greek paper, with its `header-includes` removed:
  47 pages, no missing glyph (it had hundreds), one pass instead of a retry;
  Arabic right-to-left in Amiri, Han in Songti SC, the rest in Noto Serif; with
  its own header-includes it is built as before.

---

## v3.22.9 — 2026-10-07

Pre-edit state: commit `3de8508` (v3.22.8). What mdpdf does, without PyMuPDF; and
`mdpdf` and `inkmd` as command names.

### Added

- **Finishing touches on the built PDF**, with pypdf, so they work with every
  engine, and all off unless asked for: `--bookmarks` (PDF bookmarks from the
  Markdown headings when the engine made none; the headings are found again in the
  PDF's own text, in order, and a contents page is not taken for the chapters),
  `--header` / `--footer "LEFT,MIDDLE,RIGHT"` (a running header and footer; fields
  `{page} {pages} {header} {date} {title}`), `--attach-links` (the local files the
  document links to are attached as `linked/PATH`, with a paperclip in the margin
  beside the link), `--pdf-title/-subject/-author/-keywords` (PDF properties only)
  and `--paper SIZE` (`-V papersize=SIZE`, and the built-in renderers' page too).
  The header/footer text is Helvetica: letters outside Latin-1 are reduced to their
  base letter or `?` (the unicode work can improve that).
- **`mdpdf` command**: mdpdf's own keys (`-o -h -f -t -s -a -k -p` and long names)
  mapped onto the above, with bookmarks and attached links on, wildcards expanded,
  and several inputs combined into one PDF, like mdpdf. mdpdf (MIT) is a small tool
  built on PyMuPDF (AGPL); its ideas are done here and none of its code or
  dependencies is used. If the real `mdpdf` is installed too, the last installed owns
  the command name.
- **`inkmd` command**: `pdfmd -e inkmd` with inkmd's keys (`-o`, `--page-size`,
  `--family`, `--no-autolinks`, `--no-html`, `--allow-unsafe-urls`,
  `--allow-remote-images`, `--emoji-fallback`; the last five are now ordinary pdfmd
  flags for the built-in renderer), any named engine winning. Like inkmd it reads
  standard input when no file is given and writes the PDF to standard output for
  `-o -`, or when there is no `-o` and standard output is not a terminal.

### Changed

- **Attaching keeps the whole document**: `write_pdf_attachments` now clones the
  PDF instead of copying its pages, so the properties, bookmarks and files already
  in it survive an attach (they were dropped).
- The default page size of `mdpdf` and `inkmd` is pdfmd's, not Letter.

---

## v3.22.8 — 2026-10-07

Pre-edit state: commit `a4e2780` (v3.22.7). Python 3.9, and pictures included by
raw LaTeX.

### Added

- **Python 3.9 is supported again** (it was 3.10+): `from __future__ import
  annotations`, and `write_text_lf()` for the one place that used `Path.write_text(newline=)`
  (3.10+). macOS's own `/usr/bin/python3` is 3.9, so `python3 pdfmd.py` works
  there without a newer Python. The whole suite passes on 3.9.6; CI now runs 3.9,
  3.10 and 3.13. (The built-in math renderer, md2pdf, still needs 3.11.)
- **Pictures included by raw LaTeX are recorded and restored from the PDF like
  Markdown ones**: `\includegraphics{...}` in a raw block or the preamble
  (extension optional). One inside a stored `.tex` file is stored by `--bundle`.

### Fixed

- On the PDF route, `-c` (batchocr's `--concat`) was still taken as an
  abbreviation of pdfmd's `-cwd` by Python versions before 3.12 even with
  abbreviations off; the single-dash long options are now removed from that parser.
- `PDFMD_BATCHOCR` is split the Windows way on Windows (a path with backslashes),
  and a report whose chapters sit on different drives falls back to the first
  chapter's folder.

---

## v3.22.7 — 2026-10-07

Pre-edit state: commit `d584d35` (v3.22.6). A PDF given to pdfmd is read, not
built: PDF to Markdown, with all of the reading in batchocr.

### Added

- **PDF input**: `pdfmd paper.pdf` writes `paper.md`; the direction follows the
  files (a `.pdf` input, `-o x.md`, `-o x.txt`, `--to md|txt`). A PDF that carries
  a pdfmd source is restored (`--restore`) instead; `--extract`, `-o FILE` or `--to`
  read its pages. `-o x.pdf`, a target such as `--to html`, contradictory
  `-o`/`--to`, and PDF mixed with Markdown inputs are refused before anything runs.
- **Everything pdfmd does not know goes to batchocr unchanged** (M1ck4's flag
  names: `--ocr`, `--lang`, `--export-images`, `--page-breaks`, `--preview-only`,
  `--stats`, `--no-progress`, `-q`, `--no-color`; and batchocr's own). The flags
  that exist in both are mapped: `-o/--output` (`--output` is new, an alias of
  `--out`), `-t/--to`, `-j`, `-v` (pdfmd's is a switch, batchocr's a counter, so
  `-vv` is passed as two), `--engine` (batchocr's takes `FORMAT=ENGINE`; only such
  a value goes on). Abbreviations are switched off on this route: `-c`
  (batchocr's `--concat`) used to be taken as an abbreviation of pdfmd's `-cwd`.
  Checked for every one of batchocr's 47 options and M1ck4's.
- **`pdfmd --install batchocr`**: `pip install "batchocr[md] @ git+https://github.com/aliperdehan/batchocr.git@v1.2.4"`
  into the Python pdfmd runs from (`PDFMD_BATCHOCR_SPEC` overrides the spec, for a
  checkout), with a note that PyMuPDF is AGPL-3.0 and installed as its own
  package, and the brew/apt command for Tesseract and Poppler if they are missing.
  `PDFMD_BATCHOCR` names a command for a checkout that is not on PATH.
  `--check-dependencies` reports batchocr, Tesseract and Poppler.
- The manifest of an attached source also records when and on what it was made
  (timestamp, platform, TeX Live) beside the pdfmd, pandoc and engine versions.
- README: "PDF to Markdown", with the credit to M1ck4 and the licence note.

### Notes

- batchocr 1.2.4's tags exist only locally until it is pushed; `--install batchocr`
  needs `v1.2.4` on GitHub.

---

## v3.22.6 — 2026-10-07

Pre-edit state: commit `1311d83` (v3.22.5). A PDF that was attached without
`--bundle` still gets its images back: the PDF holds every picture it drew.

### Added

- **`--restore` takes the Markdown's images out of the PDF itself** when they
  were not bundled. The manifest records, for each image, which picture of the
  PDF it is (found by its size and its order among the pictures; a JPEG by its
  bytes, since every engine copies the file's own stream) and restore writes it
  back: a JPEG **byte for byte**; a PNG, GIF or other raster as a PNG of the
  PDF's pixels (grey, palette, RGB at 1-16 bits, and an alpha channel from the
  soft mask), not the original file but the same picture; an **SVG or PDF
  figure as a one-page vector PDF** (`fig.svg` comes back as `fig.pdf`, and the
  restored Markdown now points at `fig.pdf`: restore says so). A picture the PDF
  does not hold is only recorded, as before. Checked by restoring a document
  with RGB, RGBA, grey, palette, JPEG, SVG and PDF figures and building it
  again: every page renders pixel-identical, and the restored PNGs equal the
  originals pixel for pixel. No new dependency (zlib and pypdf).
- **`--bundle` is not needed for images any more**; it stays for data and
  anything the PDF does not draw. A bundle stores the original files and
  extracts nothing.

---

## v3.22.5 — 2026-10-07

Pre-edit state: commit `fb3fd74` (v3.22.4). A bundle that rebuilds on a machine
that has only the PDF, found by restoring a real lab report and building it
with its house style hidden from LaTeX.

### Added

- **A bundle follows what it stores**: a stored `.tex`, `.md`, CSV and the like
  is read for the files it points at, to any depth (a figure's `tex/fig.tex`
  that `\input`s `tex/fig-raw`, which the first version missed: the restored
  report did not compile).
- **Files only the TeX tree finds are stored**: an `\input{chemicals}` that
  resolves through `kpsewhich` to the user's own tree (not the TeX
  distribution's, not the document's folder) is stored and restored beside the
  document (`FILE chemicals.tex (... from a TeX tree)`).
- **`--bundle-packages`, `pdfmd-options.bundle-packages`**: also store the
  packages and classes the preamble loads from that tree, what they `\input`
  and the graphics they name (found by looking every braced word up with a
  graphic's extension: a logo file named in a macro, and a few harmless
  look-alikes). Checked on a real report: restored from the PDF alone and built
  with `TEXMFHOME` pointing at an empty tree, it produced the same PDF text.
- **The manifest records requirements** (`requirements`): the user's own TeX
  files with their `\Provides...` version and hash and whether they were stored,
  the fonts the metadata names, and pdfmd/pandoc/engine versions. `--restore`
  and `--restore --list` print what is missing (`NEEDS package ...: not stored`)
  and attaching says so in a note.
- **`-r/--report` builds carry their source** (`--attach-source`, `--bundle`):
  every chapter keeps its own front matter and its place relative to the
  chapters' common folder; restore says `pdfmd -r DIR` builds it again.
  (A `name#section` build still attaches nothing: it is a throwaway.)

### Notes

- Found while testing, not changed here, cause not found: on the real lab report
  the first build of a source that has no BUILD NOTES block (a restored folder is
  one, since comments go) prints REFERENCES without its "VIII." number, and the
  same source after pdfmd has stamped it has it. The generated `.tex` is identical
  in both (`--stop-at tex`), so it is the compile, not the restore.

---

## v3.22.4 — 2026-10-07

Pre-edit state: commit `b244bf7` (v3.22.3). What the attached source keeps and
cuts: comments per kind of file, only the bibliography entries that are cited,
deflated attachments.

### Added

- **`pdfmd-options.strip-comments` names kinds** (and `--strip-comments-in KINDS`,
  `--keep-comments-in KINDS`): `true`, `false`, a list of kinds, or a per-kind
  mapping. Kinds: `markdown`, `preamble` (LaTeX `%`), `bibliography` (the text
  between a .bib's entries), `csl` (XML comments). A PDF's attached source now
  loses the comments of all of them by default. The LaTeX stripper is careful: a
  `%` that closes a line stays as a bare `%` (it swallows the line break, which
  is meaning), `\%`, `\verb`, `\url`, verbatim/listings/minted environments are
  text, `% !TEX` magic comments stay. YAML metadata loses its `#` comments
  whenever it is embedded (merged and written again) and Lua filters are never
  touched; both are said in the help.
- **The attached bibliography holds only the entries the text cites**, with
  what they `crossref`/`xref`/`xdata`/`related`, `@string` and `@preamble`; the
  keys come from the Markdown (`@key`, `[@a; @b]`), raw `\cite`-family commands,
  the metadata and the preamble, and `nocite: '@*'` / `\nocite{*}` keeps every
  entry. `pdfmd-options.attach-bibliography: all` / `--attach-bibliography all`
  keeps the file whole. `--list` and `--restore` say "2 of 120 entries".
- Restore names every Lua filter it writes (it is code, and pdfmd runs one beside
  a document) and the docs now say so; the earlier sentence that a restored
  filter "runs only if trusted" was true of an embedded filter, not of a file.

### Changed

- Attachments are deflated (a real report's PDF went from 413 KB to 215 KB with
  the same content, mostly the pruned bibliography).
- The manifest's `comments_stripped` is the list of kinds (older PDFs hold a
  plain true/false, which `--restore` still reads), and it records
  `bibliography` and `mode`.

---

## v3.22.3 — 2026-10-07

Pre-edit state: commit `28408c7` (v3.22.2). Packaging and documentation for the
attached source.

### Added

- **The command is also installed as `pdfmd-cli`** (`[project.scripts]`), the
  package's own name: `pdfmd` is also the command of an unrelated, popular
  PDF-to-Markdown tool, and when both are installed the second install silently
  replaces the first one's `pdfmd`. `pdfmd-cli` is never ambiguous. (`mdpdf` was
  considered and left out: it is itself the name of an existing PyPI project and
  would recreate the clash.) A packaging test pins both names.
- README: "The PDF carries its own source" (`--attach-source`, `--bundle`,
  `--restore`, `--strip-comments`).

---

## v3.22.2 — 2026-10-07

Pre-edit state: commit `abab176` (v3.22.1). `--bundle`: the PDF carries the
files its source cannot.

### Added

- **`--bundle [all]`, `--no-bundle`, `pdfmd-options.bundle` (`true` | `all`),
  `pdfmd-options.bundle-max-mb` (default 100)**: besides the source, store the
  images and data the document needs, each as its own PDF attachment named
  `files/PATH` (no archive: any tool lists or extracts a file, and nothing is
  compressed twice). `--bundle` stores what the text and preamble point at; it
  finds them from Markdown images and `<img>`, `file="..."` CSV tables,
  `\includegraphics`, `\input`/`\include`, pgfplots `table` and
  `\pgfplotstableread`, listings, verbatim and included-PDF macros, and, as a
  catch-all, any word that is a relative file name naming a file that exists
  (how data reached through a project's own macro, `\irpanel{ir/x.csv}`, is
  found; a name only in a comment does not count). `--bundle all` stores every
  file in the folder except the output, hidden files and folders, `.aux`/`.log`
  and the like, and backups. It implies `--attach-source`; the Markdown files it
  stores lose their comments like the source does; a file outside the folder is
  named in a note and not stored; the manifest lists every stored file with its
  hash and size.
- **`--restore` puts the files back**, never over an existing one, checking each
  hash (exit 1 on a mismatch), and refusing a path that climbs out of the
  folder. `--list` shows them (`FILE path (size)`).
- Tests (28 in all): referenced and `all` bundles, a comment-only mention not
  counting, off and the size limit, an edited stored file.

### Checked on real documents (copies)

- The parts report of 3.22.1 with `--bundle`: 12 more files (0.4 MB: the IR
  spectra's CSVs, the figures, the TeX the preamble `\input`s) found, none of
  them by a pattern written for this project; the restored folder (27 files) built
  with the PDF's text identical to the original's (0 differing lines of 1231, 15
  pages), where without the bundle it stopped at the first missing CSV. The
  PDF grew from about 0.6 MB to 1.0 MB.
- A single-file report in a 39 MB folder: `--bundle` 14 files, 0.7 MB;
  `--bundle all` 83 files, 38.6 MB (under the limit).

### Not changed / not covered

- Images are stored as the original files, in addition to the copy the PDF
  engine embedded; sharing the two is not attempted. (`--bundle` stores them
  only when asked for.)
- Files the text reaches only through a computed name (a macro building a path
  from pieces) are not found; use `--bundle all`.
- Still not covered: `-r/--report`.

---

## v3.22.1 — 2026-10-07

Pre-edit state: commit `3abf9c1` (v3.22.0). The PDF carries its own source:
`--attach-source` and `--restore`. (Per-file bundles of the whole folder, images
included, come as the next patch release.)

### Added

- **`--attach-source` (alias `--embed-source`), `--no-attach-source`,
  `pdfmd-options.attach-source` (alias `embed-source`)**: after a successful PDF
  build the document's source is attached to the PDF (PDF attachments, listed by
  any viewer): `pdfmd-source.md`, the assembled Markdown with every kind
  embedded (metadata, preamble, Lua filters, bibliography and CSL), comments
  stripped (`strip-comments` defaults to on here; `strip-comments: false` keeps
  them), and `pdfmd-manifest.json`: the document's name, a hash of the source,
  where each embedded file sat relative to the document, each file of a parts
  document (its path, its dropped front matter, where it began), the document's
  own `no-auto`, the `parts` setting, and the images the text points at with
  their hashes (recorded, not stored). Added with `pypdf` after the build, so
  every engine, and the native tier, gets it; a failure leaves the PDF as built
  and says so. Off by default. Not for `name#section` builds, `-r/--report`
  or a non-PDF target (a note says reports are not covered yet).
- **`pdfmd --restore FILE.pdf [-o DIR]`** writes the layout back into
  `FILE.restored/`: `name.md`, `metadata/...`, the preamble, filters,
  bibliography and CSL where they sat, and `parts/...` split by the recorded
  boundaries. It reuses `--unpack --slim` for the embedded kinds. It never
  overwrites (stops, writing nothing, if a file is there), never writes outside
  its folder (a manifest path with `..`, absolute, or a drive letter is
  refused and the file goes to `NAME.unpacked/` or the document's own name),
  exits 1 if the attached text no longer matches its hash, and a restored Lua
  filter is as untrusted as any other (it runs only if this machine's pdfmd
  wrote it, or with `--trust-embedded`). `--list` shows what a PDF carries.
- `make_embed_plan()` (the assembled branch's embed-plan construction, now
  shared), `first_pdfmd_option()`, `option_flag()`.
- Tests: `AttachAndRestore` (single file with metadata and preamble, comments
  kept on request, parts with boundaries and front matter, images recorded, no
  overwrite, a PDF with no source, an edited source, hostile paths, the CLI) on
  blank PDFs, so they need no engine.

### Checked on real documents (copies of two lab reports)

- A parts report (a scaffold, 9 parts, an external metadata/Lua/bibliography set
  behind symlinks): attached, restored to `report.md`, `parts/*.md` (all nine
  byte-identical to the originals less their comments), `metadata/` with the
  metadata, CSL, bibliography and preamble; with the images put back and
  built, the PDF's text is identical to the original build's (0 differing
  lines, 15 pages). A single-file report with a local metadata/preamble/Lua
  set: restored layout builds the same `.tex`.
- The comment stripper took out the long private dictation comments of every
  part, and nothing else.

### Not changed / not covered

- Images and other data the text points at are recorded, not stored. Storing
  them (`--bundle`) is the next release.
- The Lua filter a project shares from outside its folder (not reachable
  through a name in the folder) is restored into `NAME.unpacked/`, which pdfmd
  searches; a symlink to it in `metadata/` is restored as the file itself.
- Restored YAML is re-written (comments lost), like `--unpack`.

---

## v3.22.0 — 2026-10-07

Pre-edit state: commit `58d1202` (v3.21.5 plus a README credit for inkmd). The
first step of attaching a document's source to its PDF (the rest follows as
patch releases of 3.22): the comment stripper that source needs.

### Added

- **`--strip-comments` / `--keep-comments` and `pdfmd-options.strip-comments`**:
  drop every `<!-- -->` comment from the assembled file (`--stop-at markdown`,
  also for a report). Meant for notes to oneself that must not travel (reviewer
  remarks, drafts, the BUILD NOTES block). It reads the Markdown, it does not
  pattern-match it: a comment inside a fenced (backtick or tilde) or indented
  code block or inside an inline code span is text and stays, YAML front matter
  is left alone, a fence-looking line inside a comment does not open a fence, and
  pdfmd's own markers (`<!-- pdfmd-... -->`, `<!-- pagebreak -->`) stay. A
  comment alone on its line takes the line with it, and a blank line that
  leaves doubled goes too; one inside a sentence takes one of the spaces around
  it; a multi-line one is removed whole; an unterminated one is kept as written.
  Off by default for the assembled file. The command line wins over the
  document, then its metadata files (`first_pdfmd_option`).
- `tests/test_attach.py`: the stripper's cases, and the option through the CLI.

### Not changed

- The comment handling the native renderers already have (`strip_html_comments`
  for their own text) is a separate function and untouched.

---

## v3.21.5 — 2026-10-07

Pre-edit state: commit `6fd97b8` (v3.21.4). The labels half of the cache for
sections, as decided after testing 3.21.3 with pandoc-crossref.

### Added

- **A section or element of an ordinary document takes the labels it lacks from
  the last full build, when the cache is on.** `pdfmd doc#results --cache` after
  a cached `pdfmd doc --cache` prints the numbers of the other sections where
  it printed `??`; the build says how many labels it took and from when. It
  reuses parts mode's seed file (a label the section defines itself stays its
  own) and the cache folder the full build already writes its `.aux` to; the
  full build's output is unchanged. pandoc-crossref leaves `\ref{...}` in LaTeX
  output, so its references are seeded the same way.
- The note after a section build says which of the two happened: references
  come from the last full build, or print as `??` (and that a full build with
  the cache on first would fill them in).
- `SectionLabelSeeding` tests (they need Pandoc and LuaLaTeX): after a full
  build no reference in the section's LaTeX log is undefined; without one they
  still are; a section's own label is numbered from its own start.

### Not changed

- Heading, figure, table and equation numbers of a section still restart at
  its first. Carrying them over needs a marker at every heading and element in
  the full build, which changes that build's output; it is left out.
- A section written to the full document's own output name (`-o doc.pdf`) is
  not seeded, since it would overwrite the `.aux` it reads (it already did).

---

## v3.21.4 — 2026-10-07

Pre-edit state: commit `5da17cb` (v3.21.3). Found by running 3.21.3 on a machine
with pandoc-crossref (Pandoc 3.11, crossref 0.3.25).

### Fixed

- **A labelled element directly under a heading no longer swallows the heading.**
  With no blank line between `# Results {#sec:results}` and
  `![Second](b.png){#fig:b}`, the figure's paragraph started on the heading's own
  line, and heading lookup (keyed by line number) let the figure replace the
  heading: `doc#results` built only the heading and the figure, losing its
  subsections, and wrote `doc.fig-b.pdf`. A heading line (and a setext
  underline) now ends a paragraph and never begins one, and lookup is keyed by
  position, so two items that begin on one line stay two items.
- **The note after a partial parts build told the truth about whole parts only.**
  A section or element cut out of a part is not given the full build's numbers
  by the cache (it has no counter marker; only a whole part has one), yet the
  note said it was. A second note now says such a cut is numbered from its own
  start, cache or not.
- `test_exact_stem_and_extension` compared a path with the file name as typed,
  which a case-insensitive filesystem (macOS, Windows) returns unchanged; it
  now compares the files themselves.

### Checked with pandoc-crossref (nothing changed)

- Every section and element build exits 0; crossref never leaves a literal
  `@fig:a` in LaTeX output. Only LaTeX reports `Reference 'fig:a' undefined`
  (printed `??`). In HTML and DOCX crossref itself reports `Undefined
  cross-reference` and prints `¿fig:a?`.
- In LaTeX output crossref writes references as `\ref{fig:a}`, so the last full
  build's `.aux` can fill them in (verified by hand with one LaTeX run); heading,
  figure, table and equation numbers of a cut still restart.
- pdfmd's own note, "references to other sections print as ??", is accurate for
  LaTeX and PDF output.

---

## v3.21.3 — 2026-10-07

Pre-edit state: commit `b52e436` (v3.21.2).

### Fixed

- **`--split` cuts at setext headings too.** A level-1 heading written as a line
  underlined with `===` (and, with `--split-depth 2`, a level-2 one underlined
  with `---`) starts a part like `# Title` does, instead of staying inside the
  part before it. The cut uses the heading scanner of 3.21.1, so a `---` that
  ends a paragraph, a table rule and `#` lines in code or comments are still not
  headings. On documents written with `#` headings only, the cut is identical
  to before (checked against the previous splitter at levels 1 to 3), and
  `--split` still verifies that the parts read back as the identical document
  (Pandoc AST compared).

---

## v3.21.2 — 2026-10-07

Pre-edit state: commit `2e04eee` (v3.21.1). The third step: anything with a
`{#label}`, not only a heading.

### Added

- **`pdfmd doc#fig:setup` builds one labelled element.** Named by its id, with
  the same spelling tolerance as headings: a figure (`![..](..){#fig:x}`), an
  equation (`$$..$$ {#eq:x}`), a table (its `: caption {#tbl:x}` line and the
  table it belongs to, the caption written below or above), a fenced
  `::: {#id}` div (to its closing fence, with whatever is inside), a fenced code
  block with `{#lst:x}`, a `[span]{#id}`, or the paragraph or list holding any
  other id. `doc#section/fig:x` finds one inside a section; a short name
  (`doc#setup`) finds `fig:setup` by its word, with a WARN.
- Built like a section, but a lone element does not bring the text before the
  first heading (a section does, as before), and comes out as
  `doc.fig-setup.pdf`. The document's title page stays: a title may come from a
  shared metadata file, so it cannot be dropped reliably.
- `--list-parts` lists the labelled elements as well, under the heading they
  sit in, with their kind (figure, equation, table, div, code block, paragraph).
- In parts mode the same names work for elements inside the parts.
- Tests build each kind of element to LaTeX and check every block against the
  full document's LaTeX.

### Not changed

- An element's number restarts at 1 and its references to other elements print
  as `??` (as for a section). External links and bare citations have nothing to
  cut out and are not addressable; an internal link names an id, which is.

---

## v3.21.1 — 2026-10-07

Pre-edit state: commit `c3df55a` (v3.21.0 and a changelog tidy). The second of
the three steps; it uses the lookup engine of 3.21.0 for headings.

### Added

- **`pdfmd doc#NAME` builds one section of an ordinary document.** The section
  runs from the heading to the next heading of the same or a higher level
  (subsections included). The build is a partial one, like parts mode's: the
  document's own front matter, settings and the text before its first heading
  are kept, the output is `doc.NAME.pdf` (a Cyrillic or Turkish heading gets a
  Latin file name), nothing is stamped, `pdfmd-partial: true` is set. Checked on
  real builds: every block of a section's LaTeX appears verbatim in the full
  document's LaTeX, also with a bare `# Title` promoted to the title.
- **Headings are named like files are found**: case, spaces, `_`, accents and
  script ignored, then looser spelling, then the start of the text or of a word
  (a WARN says which), and an explicit `{#id}` counts too (`doc#sec:methods`).
  `doc##name` means a level-2 heading (the number of `#` is the level),
  `doc#parent/name` one under another, `doc#a+b` several, and `#name` with no
  document the folder's only Markdown file. Two headings fitting equally well
  is an error that lists both and says how to tell them apart.
- **Setext headings** (a line underlined with `===` or `---`) count as headings
  of level 1 and 2. A `---` under a paragraph's last line, a table rule, `#`
  lines in code blocks or HTML comments and indented code are not headings.
- **`--list-parts` works for any document**: every heading and `{#id}` with its
  lines. In parts mode it also lists the headings inside each part.
- **Parts mode finds headings inside parts**: a name that is no part's builds
  the matching section of whichever part has it (`report#sampling`); a name
  starting with `#` is a heading from the start (`report##sampling`). A part
  named whole beats a section of it. A section of a part is numbered from the
  part's start, not its own (no counter marker is written for it).
- `--no-auto lookup` leaves headings only their exact name (case and spaces
  aside).
- `tests/test_sections.py`: the scanner, the resolver, and the CLI to LaTeX
  checking each section against the full build, ordinary and parts mode.

### Fixed

- With only the soffice fallback available, a parts or section build crashed
  with an `AssertionError`; it now fails with a message that names the cause.

### Not changed

- `--split` still cuts only at `# ` headings. Heading, figure and table numbers
  of a section restart, and references to other sections print as `??`
  (parts mode's own limitation without the cache); the cache does not carry
  numbers over for a non-parts document yet.

---

## v3.21.0 — 2026-10-07

Pre-edit state: commit `9af6dfd` (v3.20.5). First of three steps (3.21.0 to
3.21.2) that let `pdfmd NAME#section` render one section of an ordinary
document and find documents by what they are called inside. This one is the
lookup engine every later step reuses.

### Added

- **A document can be found by its alias, its title, the start of either, or a
  looser spelling**, after every rule that already worked has failed (so
  nothing that resolved before resolves differently; checked against the
  previous release on a folder of awkward names). In order, the first tier
  with a hit decides: `pdfmd-options: {alias: ...}` (a name or a list; a bare
  `pdfmd-title:` also counts), the file name, the title (`title:` or a
  `% title` line), all ignoring case, spaces, `_ - . :` and accents
  (`pdfmd animportantdocument`); then the same with merged letters
  (c/k/q, i/y/j, v/w, sh/ş/ш, ё/е, Kazakh қ=q=k, ү/ұ/у=u, ы/і=i; a `y`/`w` in
  what you type may be either vowel); then the start of an alias, file name or
  title (`pdfmd animp`, at least 3 characters), then the start of a word in
  one. A file name or alias beats a title at each step.
- **Every guess is announced.** An exact match that only differs in case,
  separators or script prints an `AUTO MD` line; everything after it is a
  `WARN` saying what matched. Two documents fitting equally well is an error
  naming both (`LookupAmbiguous`, a `FileNotFoundError`).
- **`--no-auto lookup`** restores the previous lookup exactly. CLI only: a
  document's own `pdfmd-options: no-auto` cannot apply to the lookup that is
  still finding it.
- `tests/test_lookup.py`: the old forms (exact, wildcard, Latin for Cyrillic,
  `Пробный`, dots in names) as a regression guard, plus the new tiers.

### Fixed

- `latin_candidates` had `("oi", "oй")` with a Latin `o` inside the Cyrillic
  replacement, a spelling that could never match a real name.

### Not changed

- `-b/--batch` and `-r/--report` still take names and folders exactly as
  before; nothing there is guessed.
- `pdfmd sub/name` still looks for `name.md` in the current folder first (an
  old quirk, kept); only the new tiers look inside `sub/`.

---

## v3.20.5 — 2026-10-07

Pre-edit state: commit `21ca3fa` (v3.20.4). Three small things from the local
verification of v3.20.3.

### Changed

- **`pdfmd --install typst` now says whether the download was checked.** On
  success it prints `SHA-256 verified (...)`, or a NOTE that no checksum was
  available when GitHub's API could not be reached; before, only the absence was
  ever mentioned, so a verified install looked the same as an unverifiable one.
- **"Pandoc was not found" names `pdfmd --install pandoc`** (and `full`, which adds
  Typst), so `-o file.html`, `-p`, `-e xelatex` and the rest of what still needs
  Pandoc point at the one command that fixes it, as the other hints already did.

### Not changed

- The "pdf_metadata is on but pypdf is not installed" warning on built-in builds
  was the missing `pypdf` dependency of v3.20.0 to v3.20.2, restored in v3.20.3;
  with `pip install pdfmd-cli` it no longer appears.
- Display math printed by the built-in inkmd renderer is centred with
  zero-width spaces between no-break spaces (inkmd has no text alignment), so
  text copied out of such a PDF carries runs of invisible characters.

---

## v3.20.4 — 2026-10-07

Pre-edit state: commit `a8bfbbf` (v3.20.3). Patch bump: a test, no behaviour change.

### Added

- **`tests/test_packaging.py`**: reads `pyproject.toml` itself and fails if
  `pyyaml`/`pypdf` stop being declared (v3.20.0 lost them, and every test still
  passed on a machine that had both installed -- only CI, which installs what is
  declared, noticed); if a `pdfmd --install KIND` has no `pdfmd-cli[KIND]` extra
  naming the same packages; if the vendored `pdfmd_inkmd` package, its fonts or its
  licences would not be shipped; or if the changelog's newest entry is not
  `PDFMD_VERSION`. On Python 3.10, which has no `tomllib`, a small fallback reader
  does the job, and a test checks that it agrees with `tomllib` wherever both exist.
  Shown to fail when the dependency line is deleted.

---

## v3.20.3 — 2026-10-07

Pre-edit state: commit `b152b40` (v3.20.2). Found by the branch's first CI run.

### Fixed

- **`pyproject.toml` had lost `dependencies = ["pyyaml", "pypdf"]`** while the
  built-in renderer was added, so a plain `pip install pdfmd-cli` installed
  neither. Both are optional inside `pdfmd.py`, but without PyYAML the
  `pdfmd-options:` front matter (`parts: auto`, `no-auto`, ...) is ignored and the
  built-in renderer drops a document's `title:`/`author:`; without pypdf the PDF
  Info stamp is skipped. Restored. This is what failed eight tests in the `native`
  job and the `report#methods` step of the `examples` job.
- `test_missing_md2pdf_is_an_error_not_a_silent_downgrade` expected the
  `--install math` hint on Python 3.10, where md2pdf correctly says it needs 3.11.

---

## v3.20.2 — 2026-10-07

Pre-edit state: commit `9a03bfa` (v3.20.1). Found while checking that the
Pandoc route is unchanged by the native tier.

### Fixed

- **The native tier's `CSV_DIV_RE` shadowed the Pandoc route's of the same name**
  (both module-level, the later one wins). `contains_csv_table()` then used a
  line-anchored regex without `MULTILINE`, so a `::: {.csv file=...}` div anywhere
  but the very start of the file was not detected, the CSV filter was not added,
  and the div printed as literal text. The native one is now `CSV_DIV_LINE_RE`;
  a regression test covers the Pandoc-side detection.
- `tests/test_native.py` `EngineSelectionTests` no longer sees a real LibreOffice
  (`resolve_soffice()` finds the macOS app bundle off PATH), which made two tests
  fail on a Mac with LibreOffice installed.

---

## v3.20.1 — 2026-10-07

Pre-edit state: commit `e15ed13` (v3.20.0). Patch bump by the one-time
numbering override above, though it adds a flag value.

### Added

- **`pdfmd --install pandoc | typst | full`**: the missing programs, without admin
  rights and without a package manager.
  - `pandoc` is `pip install pypandoc_binary` into pdfmd's own environment (the
    wheel bundles the real Pandoc executable; about 35 MB, wheels for macOS,
    Linux and Windows). Also `pdfmd-cli[pandoc]`.
  - `typst` downloads Typst's release archive for this machine (Linux and macOS
    `.tar.xz`, Windows `.zip`; x86-64 and ARM) from its GitHub release into
    pdfmd's tools folder (`$XDG_DATA_HOME` or `~/.local/share/pdfmd/bin`;
    `%LOCALAPPDATA%\pdfmd\bin` on Windows), checks the SHA-256 GitHub lists for
    the asset (and refuses a file that does not match; without the API it falls
    back to the `latest/download` link and says no checksum was available),
    extracts only the one executable, and runs `typst --version`. Typst is not on
    PyPI as a program (the `typst` package is Python bindings only), hence the
    download.
  - `full` is both. `math` and `emoji` are unchanged.
- pdfmd appends those folders to `PATH` at start-up, **behind** the user's own:
  a Pandoc or Typst already installed always wins. `--check-dependencies` lists
  the folders in use.
- The offer after a lossy native build now says "install Pandoc and Typst now"
  and does it, instead of printing commands.

### Changed

- The "install Pandoc and Typst" hints name `pdfmd --install full` first, then the
  system package manager.

### Verified here, and not

`--install pandoc` was run against the real PyPI in a clean virtualenv: the
installed Pandoc was found by `--check-dependencies`, built HTML, and left the
PDF to the built-in renderer (no engine). The Typst path is tested with a faked
release (archive types, executable bit, checksum mismatch refused, no-checksum
fallback, `.part` file removed), because the sandbox could not reach GitHub:
**the real download is not verified here**. A new CI job runs
`pdfmd --install full` and a Typst build on Windows, macOS and Linux.

---

## v3.20.0 — 2026-10-07

Pre-edit state: commit `91b6a39` (v3.19.8). Minor bump: a new capability, and
nothing changes for a machine that has Pandoc and a PDF engine.

### Added

- **A built-in fallback, so `pip install pdfmd-cli` works on a bare machine.**
  With no Pandoc, or Pandoc but no PDF engine, pdfmd used to stop with an install
  message. It now builds a plain PDF from a Markdown file with a pure-Python
  renderer, says so (`NOTE  Pandoc was not found: building with the built-in
  renderer ...`), and prints one `WARN  native (...)` line per kind of thing it
  could not honour. Two renderers:
  - **inkmd 0.5.0**, vendored in `pdfmd_inkmd/` (MIT; about 1.8 MB, standard
    library only, offline, byte-deterministic). It is a generated copy: the
    package is renamed so it cannot clash with a separately installed `inkmd`, its
    CLI files are dropped, and its 10 MB colour-emoji font is left out (emoji
    print as `[rocket]`-style labels). `scripts/vendor_inkmd.py` regenerates it
    from the PyPI wheel (checked against PyPI's SHA-256), and `--check` reports
    any drift; `pdfmd_inkmd/VENDORED.md` records the version and hash.
  - **md2pdf** (PyPI `pymd2pdf` 0.6, ReportLab; Python 3.11+), when installed.
    Footnotes, bookmarks, highlighted code, and (with matplotlib) offline math.
  Neither is Pandoc: no LaTeX, preambles, filters, citations, slides, parts or
  report mode, and Markdown input only; `.tex`, `.rst`, `--to html` and the rest
  still say Pandoc is needed.
- **Every input is read as GitHub-flavoured Markdown** (`normalise_gfm()`). Fenced
  code is never touched. `\newpage`/`\pagebreak`/`\clearpage` and
  `<!-- pagebreak -->` become a page break; every other `<!-- comment -->`
  (one line or several) is dropped, since neither renderer is trusted to; footnotes stay
  footnotes for md2pdf and become numbered endnotes for inkmd; heading and image
  attributes (`{#id .class}`, `{width=50%}`), `:::` fenced-div markers (content
  kept) and raw LaTeX (`{=latex}` blocks, command-only lines, non-math
  environments) are removed; citations stay as written; a `::: {.csv file="..."}`
  div becomes the same table the Pandoc filter builds (delimiter, `header=`,
  `rows=`/`cols=`, the 10 x 7 cap and its note). The front matter's
  title/author/date become a title block and the PDF's own Title/Author
  (`papersize` and `fontsize` are honoured too); other keys are listed as not
  used.
- **Math without a typesetter.** inkmd cannot typeset math, and md2pdf only what
  matplotlib's mathtext reads, so formulas are set as text: Greek letters and
  operators as Unicode, `x^2`/`x_i` as super/subscripts (Unicode ones for md2pdf,
  which ignores `<sup>`), variables in italics, `\frac{a}{b}` as `a/b`,
  `\sqrt`, accents, `\mathbb`, `\mathbf`, cases and matrices in a rough linear
  form. `$...$` is inline in the sentence; `$$...$$` (single or multi-line) and
  `\begin{equation|align|gather|multline}` are display math, set as their own
  centred lines (an `aligned`/`align` block stacks its rows). Centring is
  approximate: inkmd has no text alignment, so the line is padded using Helvetica
  metrics, with zero-width spaces between the no-break spaces because inkmd
  collapses a run of whitespace. md2pdf with matplotlib keeps the formulas
  mathtext reads (typeset, centred, rewriting `\tfrac`, `\frac13`, `\displaystyle`,
  `\tag`, `\le`/`\ge`, ... first) and sets only the rest as text; without
  matplotlib it is left alone (it would need the network). Dollar signs that are
  not math (`$5 and $6`) are written as `&#36;` for md2pdf, which read them as a
  formula (and printed a `\$` escape as it was).
- **md2pdf printed a local path.** It prepends a hidden `<!-- SOURCE_FILE: /full/path
  -->` marker and, when a paragraph follows it directly (a document that does not
  start with a heading), printed that marker, path included, into the PDF. Such a
  document now starts with an empty paragraph (`&nbsp;`) so the marker stays a
  block of its own.
- **`-e inkmd`, `-e md2pdf`, `-e native`** (and `pdf-engine:` in `pdfmd-options`)
  ask for it explicitly. It is chosen automatically only when no Pandoc route
  exists: an explicit request for a Pandoc engine or family without Pandoc is an
  error, never a silent downgrade, and a failing Pandoc build never falls back to
  it. With both renderers, md2pdf takes documents with footnotes, math (when
  matplotlib is there) or a title; inkmd takes the rest, and either is the
  other's fallback if it raises.
- **`pdfmd --install math|emoji`** and the extras **`pdfmd-cli[math]`** (md2pdf and
  matplotlib, about 150 MB) and **`pdfmd-cli[emoji]`** (the stock `inkmd` wheel,
  whose emoji font the vendored copy is pointed at, about 11 MB).
- **An offer after a lossy native build**, on an interactive terminal only (not in
  CI or a pipe, not with `PDFMD_NO_PROMPT` set): install md2pdf with math, the
  emoji font, show how to install Pandoc and Typst, or "continue and don't ask
  again" (remembered in pdfmd's cache folder).
- `--check-dependencies` lists the native renderers and prints which mode applies;
  it now exits 0 when only the native route exists.
- `tests/` (`python3 -m unittest discover -s tests`): the vendored copy, the
  normaliser, engine selection with and without Pandoc, and real `pdfmd` runs
  with nothing on PATH. `PDFMD_GOLDEN=1` compares inkmd's output with
  `tests/golden/` after a re-vendor. CI runs them on Windows, macOS and Linux,
  once without Pandoc installed; a weekly workflow checks for new inkmd and
  pymd2pdf releases and tests the newest pymd2pdf.

### Changed

- `select_engines()` falls back to the native tier instead of exiting when there
  is no Pandoc route (and never for slides), and `main()`'s Pandoc check is now
  skipped for a plain Markdown-to-PDF run. Every other mode (`--to`, `-p`, `-r`,
  `--split`, `--unpack`, `--stop-at`, `-w`, ...) still needs Pandoc and says so
  as before.
- `pyproject.toml` packages `pdfmd_inkmd` beside `pdfmd.py` (and its two licence
  files). A bare copy of `pdfmd.py` without that folder behaves as before.

### Verified here, and not

Checked in a clean virtualenv built from this tree, with only Python on PATH: a
`pip install .`, a build with inkmd (with and without the `[emoji]` font, the
page images looked at), a build with md2pdf after `pdfmd --install math`
(footnote, title, author, typeset and text-fallback formulas, prices, comments),
the interactive offer through a pseudo-terminal (each choice, and "don't ask
again" holding), the unit tests on Python 3.11, 3.12 and 3.13 (with and without
md2pdf and matplotlib), and inkmd's byte-identical output across those three.
Not checked: Windows and macOS, the `pip install` choices of the offer, md2pdf's
emoji and Kroki fetches (the sandbox had no route to them), and anything with
real Pandoc reports.

---

## v3.19.8 — 2026-10-07

Pre-edit state: commit `fb357d6` (v3.19.7). Patch bump by the one-time
numbering override above. From the author's re-test of v3.19.7 on real reports
with Pandoc 3.11.

### Fixed

- **The math-method flag, third time right.** v3.19.7's check for
  `--html-math-method` was wrong for Pandoc 3.11, which renamed the option to
  `--math-method` (and warns `Deprecated: --mathml. Use --math-method=mathml
  instead.`): the check failed and pdfmd fell back to the short flag, so the
  warning stayed. pdfmd now tries `--math-method`, then `--html-math-method`,
  then the short flags, taking the first the installed Pandoc lists in `--help`,
  matched as a whole option name (`--math-method` is a substring of
  `--html-math-method`, which a plain substring test would have taken for it).
  Checked against stand-in help texts for each of the four cases (3.11, the
  middle range, both listed, short flags only) and the real Pandoc 3.1.3; the
  3.11 spelling itself is from the author's report, not seen here.
- **A CSL style kept in Pandoc's user data folder was not embedded** (and, for
  any file not found, nothing said why). A `csl:` is now also looked up in
  Pandoc's `csl/` data folder (from the `User data directory:` line of
  `pandoc --version`), and a bibliography or CSL file found nowhere prints a
  `WARN  not embedded: ... (not found ...)` instead of only appearing in the
  NOTE. Checked with a style that existed only in that folder: embedded, then
  deleted from the machine, and the embedded file still built with a `.tex`
  identical to the original build's.

### Changed

- Assembling with anything embedded now also prints, once, that data a macro in
  the text reads (the CSV tables a report's plots take, images in raw LaTeX) is
  never embedded and cannot be detected; it stays beside the document. (The
  author's report: the real report's plots read CSV files from four folders,
  without which its PDF would not build.)

---

## v3.19.7 — 2026-10-07

Pre-edit state: commit `477e2bc` (v3.19.6). Patch bump by the one-time
numbering override above. From the author's test of v3.19.6 on real reports.

### Added

- **`--embed-metadata bibliography`: bibliography and CSL files embedded**, the
  way Lua filters are. The `bibliography:` and `csl:` files the merged metadata
  names go into `{=pdfmd}` blocks (`type: bibliography` / `type: csl`, with the
  `path:` the metadata gives them and a hash). A name that is absolute or climbs
  out with `..` cannot be written back as it is, so the embedded file's
  metadata then names it by its own safe path. At build time the blocks are
  written to a temporary folder at that path, for the length of the build, and
  the folder is searched after everything else -- by Pandoc's citeproc
  (`--resource-path`) and by BibTeX/Biber (`BIBINPUTS`; the cache route's
  compile step included) -- so a file beside the document still wins, and
  nothing embedded changes a lookup that already worked. They are data, so no
  trust is asked, unlike filters. It is a fourth kind: on in a bare
  `--embed-metadata`, switchable as `--embed-metadata metadata preamble` or
  `pdfmd-options: {embed: {bibliography: false}}`. With it off (or a file
  missing, or not UTF-8 text) the `NOTE  not embedded:` line still names them.
  An embedded file with its bibliography now builds alone in an empty folder
  (checked: byte-identical `.tex`, with citations resolved).
- `--unpack` writes the bibliography/CSL files back (at their paths, hash
  checked) and `--unpack --slim` removes the blocks; the slimmed file finds them
  in its `NAME.unpacked/` folder, which is now also searched for them.

### Fixed

- **`--self-contained` warned on Pandoc 3.11** (`[WARNING] Deprecated: ...`):
  pdfmd passed `--mathml`, which Pandoc 3.11 deprecates in favour of
  `--html-math-method=mathml`. pdfmd now uses the long form where the installed
  Pandoc lists it in `--help`, and the short flag (`--mathml`, `--mathjax`,
  `--katex`, `--webtex`, `--gladtex`) otherwise -- Pandoc 3.1 does not know
  `--html-math-method` at all, which a first version of this fix got wrong and
  a test on Pandoc 3.1.3 caught. (The `html: {math: ...}` option uses the same.)

### Checked

- Fixture with a metadata-owned `bibliography: refs/test.bib` and `csl:` in a
  subfolder and citations: embedded copy alone in an empty folder, `.tex`
  identical to the original build's (citations resolved); the same through
  `--unpack --slim` and the unpacked folder; absolute and `../` names rewritten
  and identical; `embed: {bibliography: false}` and `--embed-metadata metadata`
  leave them out, say so, and fail to build alone as expected; the math method
  against Pandoc 3.1.3 (short flag) and, by stubbing the capability, the long
  form; BIBINPUTS and the
  resource path carry the extracted folder. All earlier comparisons pass, also
  under Python 3.11 (the project's minimum), which now runs the stand-in-engine
  cache test as well.
- Not checked: BibTeX/Biber itself finding an embedded `.bib` for
  `citation-engine: natbib|biblatex` (no LaTeX here); only the search path is.

---

## v3.19.6 — 2026-10-07

Pre-edit state: commit `38008e1` (v3.19.5). Patch bump by the one-time
numbering override above. Everything here comes from a test of the branch on the
author's machine with real nulabreport reports and LaTeX engines (every
normal-build `.tex` and PDF text identical to main's; embedding round trips
identical).

### Fixed

- **The cache route dropped an embedded Lua filter** (`pdfmd-options: {cache:
  {aux: true}}` or `plots`, on an assembled file). `_convert_one` handed the
  cache route the document's already-merged `no-auto`, which for an assembled file
  lists `lua`; the Markdown-to-`.tex` pass inside re-reads the document's own
  `no-auto` itself and then hid the embedded filter, silently (a real 29-page
  report came out 28 pages). It now passes the command line's `--no-auto` only,
  as that inner pass expects. Found on the real report; reproduced here with a
  stand-in LaTeX engine: the `.tex` handed to the engine had no filter output
  before the fix, and has it after. A normal document with the same cache option
  is unaffected.
- **`--unpack` then `--unpack --slim` on the same file** stopped on "already
  holds". Files already there with exactly the content that would be written
  are now left as they are (and counted); a file that differs still stops the
  run, writing nothing.

### Changed

- **Corrected a too broad claim.** An embedded file does not "build the same
  alone, in any folder": metadata, preamble and filters travel, but what the
  text points at -- `bibliography:`/`csl:` files, images, files a preamble
  `\input`s or `\includegraphics`, data -- does not. The docs now say so, and
  assembling with `--embed-metadata` prints a `NOTE  not embedded: ...` naming
  those it can see (a bibliography or CSL key, `\input`/`\includegraphics` in
  the preamble, images in the text). `--lua-mode ref` paths are relative to the
  output file's folder, so the layout must be kept.

### Reported by the test, left as is

- `pdfmd src.md -o src.md --to markdown` overwrites its own source; true on main
  as well (not a regression). Only `--assemble-only` guards against it.
- `--cache` / `--cache-plots` on the command line do not travel to an assembled
  file (the `cache:` settings in `pdfmd-options` do); noted in v3.19.5.

---

## v3.19.5 — 2026-10-07

Pre-edit state: commit `952d6d8` (v3.19.4). Patch bump by the one-time
numbering override above.

### Fixed

- **An assembled partial build carries `pdfmd-partial`.** A partial parts-mode
  build (`report#methods`, `--section`) tells Pandoc `-M pdfmd-partial=true` on
  the command line, which a Lua filter such as nulabreport's reads to degrade
  gracefully when the Appendix is not there. The assembled file of such a build
  (`--assemble-only`, with or without `--embed-metadata`) did not carry it, so
  building the file later ran the filter as if for the whole report. It is now
  written into the front matter (`pdfmd-partial: true`, next to the assembled
  marker); a partial scaffold with no front matter at all cannot hold it, and
  says so. Found by tracing what a normal build passes to Pandoc outside the
  text.

### Checked

- A probe filter that reports whether it sees `pdfmd-partial`: normal partial
  build "partial", normal full build "full", the embedded copy of the partial
  build built alone "partial", with a `.tex` byte-identical to the normal
  partial build's. Earlier comparisons unchanged.

### Known limits, for the record (what an assembled file does not carry)

- Command-line options of the original run: `-V`, `--from`, passthrough Pandoc
  options, `--cache`/`--cache-plots` (the cache settings in `pdfmd-options` do
  travel), `-e`. Re-give them when building the assembled file.
- The label seeding and part counters of a partial build with the cache on
  (they come from the last full build of the scaffold, which the assembled file
  is no longer).

---

## v3.19.4 — 2026-10-06

Pre-edit state: commit `437596c` (v3.19.3). Patch bump by the one-time
numbering override above; this closes the assemble/embed series.

### Added

- **`pdfmd-options: {default-output: FORMAT}`**: the format a document builds
  to when the command line names none (no `--to`, no `-o` extension, no
  `--stop-at`, no `-p`). Any Pandoc writer name or `pdf` (`tex`, `md`, `txt`,
  `typ`, `htm` as shortcuts). Document first, then its metadata files (so a
  shared `metadata.yaml` can set it for every document that finds it); per
  document in `-b`, the first file in `-r`. A missing PDF engine is now an
  error only for a document that actually builds a PDF (a machine with no
  engine can build `default-output: html` documents); an explicit `-e` that is
  not installed still fails as before.
- **HTML options, `pdfmd-options: {html: {...}}`**, Quarto-style:
  `self-contained: true` (`--standalone --embed-resources`; `--self-contained`
  before Pandoc 2.19; MathML for math by default since it needs no network; a
  page with no title gets the file name as `<title>`), `standalone: true` (a
  full page, resources linked), `math:` (mathml, mathjax, katex, webtex,
  plain), `css:` (a name or a list, relative to the document).
  `--self-contained` / `--no-self-contained` on the command line win over the
  document (a Pandoc `--self-contained` passed through before now means this,
  which is what Pandoc meant by it). Nothing changes for HTML output unless one
  of these is set: it is still the fragment it was.
- An assembled file's **embedded LaTeX preamble stays out of every non-LaTeX
  build** (HTML, docx, typst, ...), where Pandoc would have printed it into the
  output; the HTML of an embedded copy equals the original's.

### Checked

- Self-contained from the document's option and from the flag: one file, image
  inlined as a data URI, CSS inlined, `<math>` for the maths, `<title>` set; a
  plain `-o x.html` and the fragment are unchanged. `default-output` from a
  document, from a shared metadata file (report mode), mixed in `-b -j 2`
  (html, typst and pdf side by side); beaten by `-o x.pdf`, `--to latex`;
  needs no PDF engine for an HTML document. The PDF path was exercised only
  through the Pandoc -> ODT -> LibreOffice fallback in the session that wrote
  this (LibreOffice was installed, no LaTeX engine); CI builds with Typst. All
  earlier comparisons and the normal-build baselines are unchanged.

### Known limits

- No PDF metadata stamping or engine chain for HTML (they are LaTeX/PDF only),
  and a BUILD NOTES comment stays in the HTML source as a comment, as it did.
- `math: mathjax|katex|webtex` fetch their scripts when the file is built, so
  they need network access with `self-contained`.

---

## v3.19.3 — 2026-10-06

Pre-edit state: commit `11f1c97` (v3.19.2). Patch bump by the one-time
numbering override above.

### Added

- **`NAME.unpacked/` is discovered.** The folder `--unpack` writes is an
  accessory folder for the document NAME.md, searched like `metadata/`: all of
  its metadata YAML files (in name order, as the only metadata for that
  document), every `.tex` in it as a preamble, every `.lua` in it as a filter
  (the folder is made by pdfmd for that document alone, so the usual "only
  fixed names" rule is not needed). `--watch` follows it.
- **Origin of the merged keys, recorded.** An embedded file writes
  `pdfmd-options.origin`: which keys came from the document and from each
  metadata file, and the line count and hash of each preamble file. `--unpack`
  uses it to write the metadata back as the files it came from
  (`01-metadata.yaml`, `02-report.yaml`, ...) and the preamble as its original
  files; a file without the record, or a preamble edited since, still unpacks
  as one merged `metadata.yaml` / one `preamble.tex`, as before.
- **`--unpack --slim`**: after writing the files, rewrites the assembled file
  without them (embedded filters, preamble, and the metadata files' keys where
  the origin is recorded), leaving the document's own front matter and its
  `NAME.unpacked/` -- the original layout, which the discovery then builds
  exactly like the embedded file (checked: byte-identical `.tex`).
- **`pdfmd-options` file names**: `yaml:` (or `metadata:` with a name/list)
  names metadata files, like `-y` but written in the document; the existing
  `preamble:` and `lua-filter:` still work, and all three can be grouped under
  `metadata:` (`metadata: {yaml: .., preamble: .., lua-filter: ..}`; `lua:` is
  accepted for `lua-filter:` there). Flat and grouped add up. Paths are
  relative to the document. `--no-auto metadata`/`preamble`/`lua` suppress them
  as they do the other document-written options; an explicit `-y` wins.
- **`pdfmd-options.embed`**: what `--assemble-only` embeds without the flag --
  `true` (all three), `false`, a list of kinds, or a mapping (`metadata`,
  `preamble` true/false, each on unless said otherwise; `lua`: embed|ref|apply
  |off, true = embed, false = off). The document's own value wins over its
  metadata files' (so a shared `metadata.yaml` can turn it on for every
  report), the command line over both: `--embed-metadata KIND ..`,
  `--lua-mode` (its default is now "the option, else embed"), and the new
  `--no-embed-metadata`. Resolved per document in batch mode.
- An embedded file drops the names it embedded (and `embed:`) from its own
  `pdfmd-options`, which would point into the original folder.

### Fixed

- A metadata file given with a path relative to the current folder in a
  subfolder (`-y cfg/x.yaml`, or the new `yaml:` key) made Pandoc, which runs
  inside that file's own folder, look for `cfg/cfg/x.yaml`. `resolve_yaml` now
  returns an absolute path (symlinks not resolved).

### Checked

- Slim + unpacked folder, embedded copy alone, and the original build give the
  same `.tex` for the fixture with two metadata files, a preamble, a filter and
  the document's own `header-includes`; editing an unpacked preamble changes the
  next build. Flat and grouped file names build the same; a document naming its
  files in a subfolder builds, and its embedded copy alone is identical.
  `embed:` as `true`, a mapping, a list, `false`, from a shared metadata file,
  and the CLI overrides behave as described. All earlier comparisons and the
  normal-build baselines are unchanged.
- Not checked: PDF compilation (no LaTeX engine in this session).

---

## v3.19.2 — 2026-10-06

Pre-edit state: commit `0434c8c` (v3.19.1). Patch bump by the one-time
numbering override above.

### Added

- **`--lua-mode apply`**: the filters run during assembly, Markdown to Markdown
  through Pandoc (`--wrap=preserve`, the reader pdfmd would pick), so the text
  already has their effect; they are listed under `pdfmd-options.applied-lua`
  and discovery of them stays off. Approximate by nature: Pandoc re-writes the
  text (explicit heading ids, table and footnote layout), a filter's change to
  the metadata and a filter that needs citeproc first are not reproduced. A
  filter that mentions `FORMAT` (it would see `markdown` here) is embedded
  instead, with a note; so is any filter when Pandoc fails on them.
- **`--unpack FILE [-o DIR]`**: writes an assembled file's embedded Lua filters,
  `preamble.tex` (the part of `header-includes` before the preamble marker) and
  `metadata.yaml` (the merged front matter) back out, into `FILE.unpacked/` by
  default. Checks each filter against the SHA-256 recorded when it was written
  and says whether this machine's pdfmd knows it; exit status 1 on a mismatch.
  Never overwrites (stops without writing anything) and never edits the file.

### Fixed

- An embedded `{=pdfmd}` block's backtick fence counted as "this document has
  code" (and its text could trip the citation, cross-reference, CSV-table and
  definition-list checks), so an embedded copy could gain a monofont line the
  original did not have. These checks now ignore embedded blocks. (Found by the
  round-trip comparison on a document with no code.)

### Checked

- `apply`, `embed` and `ref` copies of a fixture with a Header filter give a
  `.tex` byte-identical to the original build's (`off` differs by design); a
  filter that checks `FORMAT` is embedded instead and its copy is identical;
  a filter with a Lua syntax error falls back to embedding with a warning.
  `--unpack` round trip (filter byte-identical to the original, preamble and
  metadata written, a second run refused, an edited filter flagged). The v3.19.0
  and v3.19.1 comparisons and the normal-build baselines are unchanged.
- Not checked: PDF compilation (no LaTeX engine in this session).

---

## v3.19.1 — 2026-10-06

Pre-edit state: commit `1086cfe` (v3.19.0). Patch bump by the one-time
numbering override above.

### Added

- **`--embed-metadata [KIND ...]`** (with `--stop-at markdown`): the assembled
  file also carries what pdfmd discovers beside the document, so it builds the
  same alone, in any folder. Kinds: `metadata` (the YAML files merged as Pandoc
  merges them -- later file over earlier, document over both, per top-level key,
  checked against Pandoc 3.1.3 -- with the document's front matter, into ONE
  block; `pdfmd-options` merged by pdfmd's own cascade; a file's `no-auto` and
  `parts` are not carried), `preamble` (the preamble file(s) at the head of
  `header-includes`, a literal block), `lua` (the Lua filters). None named =
  all three. The kinds embedded are written into the file's own
  `pdfmd-options: no-auto` (and `embedded`), or into the comment form of the
  marker (`<!-- pdfmd-assembled: true; no-auto: lua -->`) where there is no
  front matter, so the discovery that would find them again stays off.
- **`--lua-mode embed|ref|off`** (default `embed`). `embed`: each filter whole,
  in a fenced `{=pdfmd}` raw block at the very bottom (the fence is longer than
  any backtick run inside; Pandoc ignores raw blocks of unknown formats); `ref`:
  the filter's path in `pdfmd-options.lua-filter`, relative to the output, a
  missing one a warning rather than an error; `off`: none. (`apply` comes in a
  later step.)
- **Embedded filters run only if trusted.** A Lua filter can run any command.
  pdfmd records the SHA-256 of each filter it embeds in
  `<cache>/pdfmd/embedded-trust.txt`; at build time an embedded filter runs only
  if its own text hashes to one of those, else it is skipped with a warning (the
  build completes) unless `--trust-embedded`. A hash stored in the file itself
  cannot prove where it came from, so it is not what is trusted. A CLI
  `--no-auto lua` skips embedded filters too.
- The assembled file is always read with Pandoc's own markdown (never `gfm`,
  which would print a `{=pdfmd}` block as code).

### Changed

- The BUILD NOTES stamp ignores embedded blocks when it looks for its comment
  (a filter's text can contain the words) and, when it has to create the
  comment, writes it above them, so they stay the last thing in the file.
- Front-matter macros (`experiment:` and the like) are emitted after an embedded
  preamble, as after a discovered one (a marker line in `header-includes`
  records where the preamble ends; it never reaches the `.tex`).

### Checked

- Embedded file -> `--to latex` is byte-identical to the original build's
  `.tex`, also when the file is copied alone into an empty folder (so the
  filter can only come from its block), for: a parts report with a metadata
  file, a preamble, a Lua filter and its own `header-includes`; a report/book
  with metadata and preamble; unicode/quoted/nested YAML; a document without
  front matter (with metadata, and with only a filter). Untrusted, edited and
  `--trust-embedded` filters, `--lua-mode ref` (and a missing file), `off`,
  selected kinds, the stamp, and `-b -j 2` behave as described. Normal builds and
  v3.19.0's plain assembly are unchanged against the earlier baselines.
- Not checked: PDF compilation (no LaTeX engine in this session).

### Known limits

- YAML goes through PyYAML (YAML 1.1 rules, comments lost): an ambiguous scalar
  such as `007` is written back as `7`.
- A document with no front matter and a bare leading `# Title` keeps its
  preamble out of the file (a new front-matter block would stop the title being
  promoted); a warning says so.
- A report/book build applies no discovered Lua filter, so none is embedded.
- The embedded preamble sits in `header-includes`, which a non-LaTeX target
  (HTML) would also see; that is for the HTML step.

---

## v3.19.0 — 2026-10-06

Pre-edit state: commit `26eb3ed` (after v3.18.0).

**Version numbering, a one-time override (the author, 2026-10-06):** the
"assemble / embed" feature series bumps the minor version once (this
release) and then only the patch number per step (v3.19.1, v3.19.2, ...),
instead of a minor bump each, to keep the version count down. The usual
rule above resumes afterwards.

### Added

- **`--stop-at markdown|tex|pdf`, and `--assemble-only`** (= `--stop-at
  markdown`). The build runs as normal and ends after the named stage.
  `markdown` writes the assembled Markdown, `NAME.assembled.md`: the scaffold
  and its parts joined into one text (a part's leading front matter dropped,
  as the real build does), or the chapters of a `-r` report/book; `-o` may
  name it, and an `-o` ending `.assembled.md` implies the stage. It carries
  no discovered metadata, preamble or filter yet, runs no engine, writes no
  stamp and makes no backup, and refuses to overwrite one of its own sources.
  `tex` is `--to latex` (`beamer` with `-p`). Combinations that contradict
  each other (`--to`, `-p`/`-w` with `markdown`, `--assemble-only --stop-at
  tex`, a non-Markdown input) are an error.
- **The `pdfmd-assembled: true` marker.** Written into the file's front
  matter, or, for a document with none, as a trailing `<!-- pdfmd-assembled:
  true -->` (a new front-matter block would stop a leading `# Title` being
  promoted to the title, so it is never created). Parts mode ignores a marked
  file (it would join the parts a second time, and `parts: auto` would
  otherwise take it for another scaffold beside `parts/`), and `-b`/`-r` with
  `--stop-at markdown` skip such files.

### Checked

- Assembled file fed back to pdfmd, `--to latex`: byte-identical `.tex` to
  the original build for a parts report, a report/book (`-r`), a single
  document with a bare `# Title`, and a `% title` block document. Normal
  `--to latex` output of the examples is unchanged.
- Not checked here: PDF compilation (no LaTeX engine in the cloud session
  that wrote this); nothing in this release touches that path.

---

## v3.18.0 — 2026-10-04

Pre-edit state: commit `50d46d4` (v3.17.0).

### Added

- **The plot cache: `pdfmd-options: {cache: {plots: true}}` / `--cache-plots`**
  (needs nulabreport >= 1.26.0 and LuaLaTeX; skipped with a note otherwise).
  Defines `\LabPlotCacheDir` in the generated `.tex`; the package then
  includes a stored PDF for each whole plot picture it has seen and logs the
  ones it hasn't to `<jobname>.plotreq`. After a successful build pdfmd
  renders those in parallel, each in a standalone job that loads the same
  preamble (cut from the generated `.tex`) and ships the picture out as a
  page of exactly its size, for the next build. A failure to render costs
  nothing but the speed-up. Staleness: the folder is keyed by a hash of
  `nulabreport.sty`, the preamble and the engine version; every entry records
  the user files its job read (`-recorder`, not a guess at argument names)
  and is dropped before the next build if one changed; an entry is committed
  by renaming its `.dim` last, so an interrupted render leaves nothing that
  could be half-used. Measured on a real 29-page report: 80 s plain, 28 s
  with `cache.aux`, 15 s with both; the cached build's words match the plain
  build's to 0.05 bp (0 of 12,312), and CSV edits, a patched package and a
  `trace color`/`overlay colors` that only the call's own keys set were each
  checked to give the right picture.
- **`--clear-cache`**: removes a document's cache folder (or all of it with
  no document). Always safe.

### Fixed

- The cache's `NOTE` text and `--help` now say what is cached and what is not
  (only LaTeX's cross-reference files; every build still typesets from the
  current package, filter and text).

---

## v3.17.0 — 2026-10-04

Pre-edit state: commit `f6498b3` (v3.16.0).

### Added

- **The cache: `pdfmd-options: {cache: {aux: true}}` / `--cache` /
  `--no-cache`.** Pandoc writes the standalone `.tex` (the path `--to latex`
  already takes), and pdfmd compiles it itself in a per-document folder under
  `~/.cache/pdfmd` (`$XDG_CACHE_HOME`, `%LOCALAPPDATA%`), using the existing
  direct-`.tex` runner (`compile_tex_direct`, now with `aux_dir`, `cwd`, `env`):
  rerun only while the log asks, bibtex/biber between passes. LaTeX's `.aux`
  persists, so an unchanged document settles in one pass. Measured on a real
  29-page report: 80 s cold, 28 s warm; the PDF text is identical to the
  Pandoc-run build's. A failed engine run wipes that document's LaTeX files
  and retries once clean. Off by default.
- **Parts mode + cache: a part built alone no longer prints `??`.** Labels
  from the last full build's `.aux` are defined (only where the part does not
  define them itself), and each selected part starts with a `\pdfmdpart{key}`
  raw line that restores LaTeX's counters to their values at that point of
  the full build (`pdfmd@st@key`), so `report#discussion+appendix` is
  numbered "V." and "VIII." as in the full report, not "I." and "II.".
  Verified on a real report and a demo; the NOTE says the numbers are the last
  full build's.
- **`citation-engine: natbib`/`biblatex` with parts**, via the same route
  (it was an error): bibtex/biber run between passes.

---

## v3.16.0 — 2026-10-04

Pre-edit state: commit `63cc7a7` (v3.15.1).

### Added

- **Parts mode: one long document as a scaffold plus a folder of parts.**
  With `pdfmd-options: {parts: auto}` (in a shared `metadata.yaml`, so the
  content files stay free of typesetting; or in the document's own front
  matter), a document with a `parts/` or `sections/` folder beside it is
  built from the scaffold and every `.md` under that folder, in natural
  filename order, in one Pandoc run. Off unless asked for, and with `auto`
  only for a document that actually has the folder, so nothing existing
  changes. Verified on a real 1,800-line lab report cut into nine parts:
  the Pandoc AST, the generated LaTeX and the PDF text are identical to the
  single file's. See the module docstring ("A long document in parts").
  - `--section NAME` / `--only`, `pdfmd report#NAME`, or a part's own path
    build just those parts (`report.NAME.pdf`, no stamp, `pdfmd-partial:
    true` in the metadata for filters). Typos are an error listing the
    choices, never a silent wrong build. `-s` is Pandoc's `--standalone`,
    so there is no short flag.
  - `--list-parts` prints the build order.
  - `+` joins sections (`report#discussion+appendix`), as does `,`. Parts
    always build in report order, once each, and the file is named in that
    order. A name matching parts in two top-level folders is an error, not a
    quiet union (`discussion/yield` names one exactly).
  - `--split-depth N` also cuts at `## `/`### ` headings, each cut section
    becoming a folder (its first file holds the heading), so a subsection
    can be built alone; slugs are cut at a word boundary.
  - `--split DIR` cuts a single-file document at its `# ` headings into a
    scaffold plus `parts/` in a NEW folder (the source is never touched; the
    other files it uses are symlinked in so the result builds as it
    stands), fence- and comment-aware (a `# ---` line in a code block is
    not a heading), then compares the Pandoc AST of the parts against the
    original and reports whether they read back identically. Verified on
    two real lab reports.
  - A leading YAML or `% title` block in a part is stripped before Pandoc:
    Pandoc merges later files' YAML and the **later value wins** (checked),
    so a stray `title:` in a part would have replaced the document's.
  - `--no-auto parts`, `parts: false`, `parts: <folder>`.
  - `-w/--watch` follows the parts folder.
  - `--backup` snapshots each part as well as the scaffold.
  - Built through `convert_one` (new `extra_inputs`, `partial` arguments),
    not the `-r/--report` branch, which is a separate, older code path that
    skips much of what single-file builds do (Lua filter discovery, among
    other things); that is why the output matches a single file exactly.

---

## v3.15.1 — 2026-09-30

Pre-edit state: commit `10c09f8` (v3.15.0).

### Fixed

- **PDFs now name pdfmd in their `/Creator` field** instead of only the
  underlying tool (`LaTeX via pandoc`, `Typst 0.x`, ...), which made a
  pdfmd-built PDF indistinguishable from a bare `pandoc` run. The existing
  post-compile PDF Info stamp (`stamp_pdf_metadata_posthoc()`, so every
  engine, gated by the same `pdf_metadata` switch) now appends it in
  pandoc's own order: `LaTeX via pandoc via pdfmd-cli`. Uses the PyPI
  distribution name so it is searchable; the version is already in the
  `PdfmdVersions` key. Idempotent; an absent Creator becomes `pdfmd-cli`.

---

## v3.15.0 — 2026-09-29

Pre-edit state: commit `dd52035` (v3.14.0). v3.14.0's `margin:`/`geometry:`
translation was front-matter-only, same scope `papersize:` translation
already accepted — but for a *translation* (as opposed to a same-document
default), that scope limit means a document with its margin set ONLY in a
shared `--metadata-file` loses it silently on the engine that can't read
that key natively, same failure this feature exists to fix, just moved
one level out. Found immediately after v3.14.0, checking that exact case.

### Fixed

- **`frontmatter_margin_geometry_options()` and `fix_typst_margin()` now
  also translate a `margin:`/`geometry:` set only in a linked
  `--metadata-file`**, not just the document's own front matter. Same
  precedence `pdf-engine`/`no-auto` resolution already uses (see
  `frontmatter_pdfmd_options()`'s callers): the document's own front
  matter is checked first, and only if it sets no `margin:` at all are
  the linked metadata files checked next, in order — so a shared
  `metadata.yaml` can set `margin:` once for every document that finds
  it, exactly the kind of file `nulabreport`-style pipelines already use
  for shared defaults. A real `geometry:` anywhere — front matter, any
  metadata file, or `-V` — still always wins, untouched, checked before
  any `margin:` in any source (same as `has_geometry()`).

  On the Typst side, `prepared_latex_inputs()` now takes `doc_count`
  (defaulting to 1, the existing behavior everywhere except report/book
  mode, which passes `len(files)`) to correctly tell every path after the
  main document(s) apart from the main document(s) themselves — a
  linked `--metadata-file`, which Pandoc accepts EITHER fenced
  (`---`/`...`-delimited, same as front matter) OR completely bare (no
  delimiters at all). `fix_typst_margin()` takes a new `is_metadata` flag
  for this: a bare *metadata file* is now read as pure YAML directly; a
  bare *main document* (no front matter at all) is always left alone —
  that's markdown body text, never YAML, and must never be parsed as
  such regardless of `is_metadata`. Confirmed directly: a *fenced*
  metadata file's mapping `margin:` was still silently missed even with
  this fix half-applied, because `yaml.safe_load()` chokes on a second
  `---` as "expected a single document in the stream" — front matter is
  now unwrapped from a metadata file's own text the same way it already
  is from the document's, before parsing either.

---

## v3.14.0 — 2026-09-29

Pre-edit state: commit `9466c31` (v3.13.0). v3.13.0 only translated a bare
scalar `margin:` — found immediately after, while checking whether a
document written for one engine family and later rendered through the
other would round-trip cleanly in the two directions v3.13.0 didn't cover:
a `margin:` that's already a per-side mapping (silently ignored on
LaTeX-family engines, same as the scalar case before v3.13.0), and a
`geometry:`-only document (silently ignored on Typst — no error, just the
wrong margin, since Typst's template never reads `geometry:` at all).

### Changed

- **`frontmatter_margin_scalar()` → `frontmatter_margin_geometry_options()`**,
  and **`fix_typst_margin_scalar()` → `fix_typst_margin()`**: both now
  handle a `margin:`/`geometry:` value of any shape Pandoc itself accepts,
  not just a bare scalar, via two new shared normalizers,
  `parse_margin_sides()` and `parse_geometry_sides()`, each returning a
  canonical `{top, bottom, left, right}` dict (or None when nothing safe to
  translate). Both now use `yaml.safe_load()` on the front-matter block
  (PyYAML — already an optional soft dependency here, see
  `frontmatter_pdfmd_options()`) instead of `frontmatter_margin_scalar()`'s
  old scalar-only regex, which is kept as the fallback when PyYAML isn't
  installed.

### Fixed

- **A `margin:` per-side mapping (`top:`/`bottom:`/`left:`/`right:`, or
  Typst's `x:`/`y:` shorthand) was silently ignored on every LaTeX-family
  engine**, same failure v3.13.0 fixed for a bare scalar but explicitly
  left this case out of scope for. `frontmatter_margin_geometry_options()`
  now expands `x:`/`y:` into paired sides and emits one `geometry:<side>=
  <value>` option per side actually given (or a single `margin=<value>`
  when all four are equal) — one `-V geometry:...` per option, at the same
  four call sites as before. A mapping using Typst's `inside:`/`outside:`/
  `rest:` (binding-aware, no LaTeX equivalent at all) is left untouched,
  same as v3.13.0 already left a non-scalar `margin:` untouched.

- **A document with ONLY `geometry:` set (no `margin:` at all) — written
  for and tested against a LaTeX-family engine — silently fell back to
  Typst's own default margin (1.25in) the moment `--engine typst` ran it**,
  no error, just the wrong margin: Typst's template never reads
  `geometry:` at all. `fix_typst_margin()` now parses `geometry:` the same
  way (a bare `"key=val"` scalar, a comma-joined `"key=val,key=val"`
  scalar, or a YAML list of either) via `parse_geometry_sides()`, and adds
  a new `margin:` mapping translated from it — `geometry:` itself is left
  in the front matter untouched (inert for Typst, not harmful). A
  `geometry:` option this can't safely interpret as a margin (anything
  with no `key=`, or a key that isn't a recognized margin/side name, e.g.
  `showframe`) leaves the document untouched rather than guessing.

---

## v3.13.0 — 2026-09-28

Pre-edit state: commit `c31a35b` (v3.12.0). Found and fixed while rendering
a bibliography document with `margin: 2.54cm` in its front matter and
`pdfmd-options: {engine: typst}`.

### Fixed

- **A document's own `margin:` value was silently ignored on every
  LaTeX-family engine, and crashed outright on the Typst engine.**
  `margin:` is a real Pandoc variable for the Typst template only —
  Pandoc's LaTeX template never reads it, only `geometry:` does (a list of
  "key=value" strings that becomes `\usepackage[...]{geometry}`).
  `has_geometry()` already treated a bare `margin:` as "a margin setting
  exists" (correctly, so `DEFAULT_MARGIN` wasn't injected on top of it),
  but nothing translated that value into the variable LaTeX's own template
  actually consumes — so `margin: 2.54cm` with no `geometry:` compiled
  fine on every LaTeX-family engine while silently keeping LaTeX's own
  much wider article-class default margins, the requested value never
  taking effect. New `frontmatter_margin_scalar()` detects this case
  (front matter/`-V` only, same scope as `pagesize_typo_value()`) and
  translates it into `-V geometry:margin=<value>` at all four call sites
  that already handle `DEFAULT_MARGIN` injection (`_convert_one`'s
  non-PDF-target and PDF-engine-loop branches, and both of report mode's
  matching branches). An explicit `geometry:` anywhere, or a `margin:`
  that's already a YAML mapping/per-side block, is left untouched.

- **`--engine typst` (or `pdfmd-options: {engine: typst}`) failed with
  `error: unexpected comma` on any document whose `margin:` was a plain
  scalar** (`margin: 2.54cm`, `margin: 1in`, ...) — exactly the value every
  other writer, including the LaTeX translation above, accepts. Pandoc's
  own default Typst template renders margin unconditionally as `margin:
  ($for(margin/pairs)$$margin.key$: $margin.value$,$endfor$)`: it always
  iterates key/value pairs, so a scalar has nothing to iterate and comes
  out as the literal, invalid `margin: (: ,)`. New
  `fix_typst_margin_scalar()` rewrites a bare scalar `margin:` in the
  document's own front matter into the `x:`/`y:` YAML mapping the template
  actually needs, applied through a generalized `prepared_latex_inputs()`
  (now also takes `typst_engine=`, mutually exclusive with `latex_engine=`)
  the same way LaTeX header-includes get corrected — a temporary, sibling
  copy of the input, cleaned up after the render. A `margin:` that's
  already a mapping (a `top:`/`bottom:`/`left:`/`right:` or `x:`/`y:`
  breakdown) needs no fix and is left alone.

  Report mode gets both fixes at its two matching call sites too. Only the
  document's own front matter is handled in either fix, not a shared
  `--metadata-file` setting `margin:` as a scalar — same scope limit
  `typst_papersize_translation()`'s callers already accept for `papersize:`
  — and only the plain-scalar case, not translating an existing per-side
  `margin:` breakdown into `geometry:` options for LaTeX, which is a
  reasonable follow-up left out of scope here.

---

## v3.12.0 — 2026-09-28

Pre-edit state: commit `17025b7` (v3.11.2). Found and fixed while wiring a
citeproc-dependent Lua filter (one that pulls a single formatted reference
out of citeproc's resolved bibliography div) into a real document.

### Added

- **`pdfmd-options: lua-filter: ...`** front-matter key
  (`frontmatter_extra_lua_filters()`), for a filter that isn't named after
  the document's own stem and so `find_lua_filters()`'s fixed
  auto-discovery (`<stem>.lua` / `nulabreport.lua`) never picks it up.
  Accepts a bare string or a YAML list, resolved relative to the document's
  own directory, merged with (not replacing) whatever auto-discovery
  already found, and deduped by resolved path. Same conventions as
  `pdfmd-options: preamble:` (`frontmatter_extra_preambles()`): a hard
  `SystemExit` if a named file doesn't exist, and suppressed the same as
  auto-discovery by `--no-auto lua` / a bare `--no-auto`.

### Fixed

- **Extra CLI args (`pandoc_options`, from `parse_known_args()`) landed on
  the Pandoc command line *before* `--citeproc`**, in every PDF-rendering
  code path (the direct `run()` closure, the standalone-tex-target branch,
  the soffice-bridge fallback, and both report-mode branches). Harmless for
  most passthrough flags, but silently broke any `--lua-filter`/`--filter`
  passed this way that depends on citeproc's resolved output — e.g. one
  reading citeproc's `id="refs"` / `id="ref-<citekey>"` bibliography div,
  which never existed yet when the filter ran. `pdfmd`'s own
  auto-discovered Lua filters were never affected (already correctly
  ordered after `--citeproc`) — only filters supplied via extra CLI args or
  (before this version existed) with no auto-discovery route at all.
  `cmd += pandoc_options` now happens after the `--citeproc` append in each
  of those five spots (left `convert_via_native_bibliography` — the
  `citation-engine: natbib`/`biblatex` path — untouched: it never produces
  citeproc's bibliography div, so this ordering doesn't apply there).
  Verified with `--verbose` that the built command now reads `--citeproc
  --lua-filter=...` instead of the reverse, and that a real citeproc-
  dependent filter resolves correctly through the full `pdfmd` pipeline
  (not just a synthetic Pandoc-only repro) — plus a regression check that
  an ordinary citation-free document, and `--no-auto lua` suppression of
  the new front-matter key, both still behave unchanged.

---

## v3.11.2 — 2026-09-26

Pre-edit state: commit `452e83d` (v3.11.1). Windows fixes found by reading
the code. Not yet run on Windows; the macOS/Linux behavior is unchanged.

### Fixed

- **`BIBINPUTS` joined paths with a hard-coded `:`** for a direct `.tex`
  compile with a bibliography. That's wrong on Windows, where the separator
  is `;` and the `:` in a drive letter (`C:\`) splits the path. It now uses
  `os.pathsep`, like `TEXINPUTS` and `--resource-path` already did.
  Re-verified on macOS: a direct `.tex` with `\bibliography{refs}` still
  resolves its citation.
- **`--open` did nothing on Windows** (it only knew `open`/`xdg-open`). It
  now uses `os.startfile`, Windows' "open with the default app".
- **LibreOffice wasn't found on Windows** unless it was on PATH, which the
  Windows installer doesn't do. `resolve_soffice()` now also checks
  `%ProgramFiles%` and `%ProgramFiles(x86)%\LibreOffice\program\soffice.exe`.

The two Windows-only branches were checked by running `open_file()` and
`resolve_soffice()` with `sys.platform` patched to `win32` (`os.startfile`
called; a fake `%ProgramFiles%` install found).

---

## v3.11.1 — 2026-09-26

Pre-edit state: commit `2d64619` (v3.11.0). First version published to PyPI.

### Added

- **Published to PyPI as `pdfmd-cli`**, so the install is `pipx install
  pdfmd-cli`. `.github/workflows/publish.yml` builds and uploads on every
  pushed `v*` tag, through PyPI trusted publishing (no stored token) and
  the repo's `pypi` environment. It refuses a tag that doesn't match
  `PDFMD_VERSION`.

### Changed

- The Python-too-old error and the README now show `pipx install
  pdfmd-cli`. README links and images are now absolute URLs, so they also
  work on the PyPI project page.

---

## v3.11.0 — 2026-09-26

Pre-edit state: commit `bcafe7f` (v3.10.0).

### Added

- **A symlinked metadata file finds files beside its real copy.** When a
  discovered or `-y` metadata file is a symlink, its target's real
  directory is appended to `--resource-path` (`resource_path_option()`),
  so a relative `bibliography:` in one shared metadata file resolves from
  every folder the file is symlinked into. That used to need an absolute
  path, because Pandoc runs in the symlink's folder. The directory is
  appended LAST, so it only decides a lookup that would otherwise fail.
  Without symlinked metadata the command line is byte-for-byte unchanged
  (no `--resource-path` is added).

  Motivated by nulabreport's `prelab-metadata.yaml`, which is symlinked
  into each prelab folder and hard-coded
  `bibliography: /Users/<name>/.../nulab.bib`. Verified on real
  prelabs (`prelab4`, `prelab5`, `prelab5.5`, all of which cite): old
  pdfmd with the absolute path and new pdfmd with `bibliography: nulab.bib`
  give pixel-identical PDFs (6/6, 4/4 and 2/2 pages), and the reference
  list renders. Also verified for typst and lualatex in single-file mode
  and for `-r` report mode, and that a non-symlinked metadata folder
  still gets no `--resource-path` at all.

---

## v3.10.0 — 2026-09-26

First change made under "commit before editing": the pre-edit state is
commit `a4724b5` (v3.9.2).

### Added

- **Installable with `pipx install git+https://github.com/aliperdehan/pdfmd`**
  (or `uv tool install`), which puts a `pdfmd` command on PATH. The new
  `pyproject.toml` names the distribution `pdfmd-cli`, because `pdfmd` on
  PyPI is an unrelated PDF-to-Markdown tool. The version is read from
  `PDFMD_VERSION`. `pyyaml` and `pypdf` are regular dependencies of the
  installed package, so `pdfmd-options:` and PDF metadata stamping work
  out of the box. Running `pdfmd.py` directly is unchanged, and both
  libraries stay optional there.
- **A clear error on Python older than 3.10**, instead of a `TypeError`
  from the first `list[str] | None` annotation. macOS's own
  `/usr/bin/python3` is 3.9.
- **Install instructions in the "Pandoc was not found" error.**

### Fixed

- **`--no-citeproc` broke the build instead of turning citeproc off.** It
  was only ever looked for among the options passed through to Pandoc,
  and then passed on to Pandoc, which has no such flag ("Unknown option
  --no-citeproc"). It's now a real pdfmd flag (listed in `--help`) that
  sets `CITEPROC_DISABLED`, and all five call sites that add `--citeproc`
  automatically check it. Verified in single-file, batch and report mode.
- **Missing default fonts made every LaTeX engine fail.** JetBrains Mono
  (code), and DejaVu Serif (the missing-glyph retry) on macOS, usually
  aren't installed on a fresh machine. `fontspec` then errored under
  lualatex and xelatex, pdflatex failed on Unicode, and the document
  silently fell through to typst or an HTML engine. pdfmd now checks
  whether a default font is installed (`fc-list`, else `luaotfload-tool`;
  with neither, it assumes the font is present, as before) and substitutes
  an installed one with a one-line `WARN`:
  - code: Menlo, DejaVu Sans Mono, Liberation Mono or Courier New;
  - the glyph retry: Times New Roman, Liberation Serif or Georgia. All
    three cover the ≥/Δ/· that STIX Two Text lacks.

  Each lookup runs at most once per run, and only when a document
  actually needs that default. Verified on a simulated fresh Mac (fonts
  renamed to nonexistent ones), with and without `fc-list`: that used to
  end on typst, and now builds with lualatex, Menlo and Times New Roman,
  with every glyph present. With the fonts installed, nothing changes:
  nulabreport's `LR_sample.md` built through v3.9.2 and v3.10.0 gives
  pixel-identical pages (4/4) with identical fonts.

### Changed

- README: install section rewritten around pipx; documents automatic
  `--citeproc` (and `--no-citeproc`) and the passing of unknown options
  through to Pandoc.

---

## v3.9.2 — 2026-09-25

Backup references: `backups/pdfmd.py.bak-20260925a` and `-20260926a` (in
the old `~/dev/python-projects/backups/`, like every backup reference
below). This is the last version with a backup file; from here on each
change is a git commit instead, and entries cite the commit.

### Changed

- **Moved to its own folder, `~/dev/py/pdfmd/`, to be published as a git
  repository.** `~/dev/python-projects/pdfmd.py` is now a symlink to the
  new location, so every existing alias and documented command keeps
  working unchanged. This file was renamed from `CHANGELOG-pdfmd.md` to
  `CHANGELOG.md` (an old-name symlink remains in `python-projects`).
  Backups made before this version stay in `~/dev/python-projects/backups/`.
- **Process: "commit before editing" replaces manual backups.** The
  header comment in `pdfmd.py` and `CLAUDE.md` now say so.
- **Licensed under MIT** (`LICENSE`).
- **Comments and changelog only, no behavior change:** the author's
  first name and absolute home-directory paths were replaced with "the
  author" and `~/` paths ahead of publishing, verbatim chat quotes were
  paraphrased, the docstring's example file names were made generic
  (`pdfmd report`, `pdfmd slides -p`), and the header comment now
  points at `CHANGELOG.md` / `CLAUDE.md` next to the script.

### Added

- **`README.md`**, with usage examples and real output, plus runnable
  sources in `examples/` (lecture notes, a CSV table, Beamer slides, a
  two-chapter book) and cropped page previews in `docs/`, rendered from
  those examples.

---

## v3.9.1 — 2026-09-24

Backup reference: `backups/pdfmd.py.bak-20260924c`.

### Fixed

- **A bare name containing a dot built the wrong file.** `pdfmd prelab5.5`
  compiled `prelab5.md` → `prelab5.pdf` and reported `OK prelab5.md`, never
  touching `prelab5.5.md`. `find_markdown()` and `name_candidates()` both ran
  `Path(...).stem` unconditionally, so the `.5` was taken for an extension
  and stripped. When a sibling with the shorter name existed, the wrong
  document was built (and its PDF overwritten) with no error. Both now go
  through a new `strip_lookup_suffix()`, which only drops `.md`,
  `.markdown` or `.pdf` (case-insensitive). `pdfmd prelab5.5` now resolves
  to `prelab5.5.md`; `prelab5` still resolves to `prelab5.md`. A name that
  is already an existing file, and wildcard patterns, return before this
  lookup and are unchanged.

---

## v3.9.0 — 2026-09-24

Backup reference: `backups/pdfmd.py.bak-20260924b`.

### Added

- **`pdfmd-options.backup.format` / `--backup-format`: choose how snapshots
  are named.** Presets cover every convention found in a survey of the
  real backup folders (LR2/backup, LR3/backups, LR4-5/backup and prelab/
  backups, ir/webbook/backups, nulabreport/backups and _superseded):
  `compact` (`report.md.bak.20260924091500`, still the default, so
  v3.8.0 behavior is unchanged), `dashed` (`report.md.bak.20260924-091500`),
  `stem` (`report_20260924-091500.md`), `suffix`
  (`report.md.20260924-091500.bak`), `short`
  (`report.md.09-24_09-15-00.bak`). A custom template also works: `{name}`
  `{stem}` `{ext}` plus strftime codes. It is validated, so a template
  without `{name}`/`{stem}` or without any strftime code is refused, since
  every snapshot or every file would then collide. A same-second clash gets
  `-2`, `-3`, ... before the extension (or before `.bak`).
- **Every existing naming form is recognized as a snapshot of its file**,
  whatever `format:` is currently set to. That covers the dedupe check,
  ordering (date parsed from the name, else mtime) and `keep:` pruning.
  Changing format therefore never makes old snapshots invisible.
  Recognition was dry-run against those real folders: every hand-made
  backup was attributed to the right source, and unrelated files (`test.tex`,
  `chat.md`, `.dotx` templates) were ignored.

### Changed

- `keep:` now prunes only **plain-timestamp** snapshots. A tagged name
  (`nulabreport.sty.pre-irstack.20260923-211848.bak`,
  `chemicals.tex.before-LR1-2`, `prelab5.md.09-21_18-27-50.pre-migration.bak`)
  is a deliberate milestone, never deleted and not counted toward `keep`.
  v3.8.0 only ever matched its own compact names, so it could not have
  pruned these either. This makes that guarantee explicit now that other
  forms are recognized.

---

## v3.8.0 — 2026-09-24

Backup reference: `backups/pdfmd.py.bak-20260924a`.

### Added

- **Automatic source backups on compile: `--backup` / `--no-backup` and
  `pdfmd-options: backup:`.** After a successful compile, the source is
  copied to `backup/<name>.bak.YYYYMMDDHHMMSS` beside it. That is the
  naming already used by hand in report folders (`LR2/backup/
  report.md.bak.20260923212449`, ...), so manual and automatic snapshots
  sort together. Front matter / metadata-file cascade is the same as
  `stamp:` (document wins, then each metadata file in order, then the CLI).
  Accepts `true`/`false`, a directory name, or `{enabled, dir, keep}`.
  `keep: N` prunes to the newest N snapshots of that one file, and only
  ever touches files matching `<name>.bak.<14 digits>[-n]`.
- The snapshot is taken **after** the BUILD NOTES stamp and skipped when
  the newest existing snapshot matches, ignoring the stamp's own lines (the
  live `Compiled ... pdfmd vX` line, its `- Compiled ...` history bullets,
  and the `Compile History:` heading). Recompiling unedited source (or a
  `--watch` recompile triggered by something else in the folder) therefore
  doesn't pile up copies. The line filter is needed because `stamp: {mode:
  history}` rewrites a timestamp on every compile, so a plain byte
  comparison never matched. That was caught on the first real run against
  `LR2/report.md`. Binary (office) sources fall back to a byte comparison. A backup failure (OSError) only warns and
  never fails a compile that already succeeded.
- Implemented as a thin `convert_one` wrapper around the old body (now
  `_convert_one`), so every success path gets it (Pandoc, natbib/biblatex
  direct compile, direct `.tex`, office). This avoids adding a call at
  each return. Report mode backs up each chapter after its stamp. `.qmd`
  reads only its own front matter (no metadata.yaml, same as the rest of
  the Quarto path).
- `--watch` is unaffected: `watch_signature()` is non-recursive and never
  sees `backup/`.

---

## v3.7.1 — 2026-09-23

Backup reference: `backups/pdfmd.py.bak-20260923a`. Found and fixed live
while building `LR4-5/report.md`, which has a `metadata/` subfolder (see
`accessory_directories()`).

### Fixed

- **A `metadata/` subfolder broke every raw-LaTeX relative-path reference
  in a document, not just Pandoc-resolved images.** When pdfmd
  auto-discovers a metadata file inside `metadata/`, it runs Pandoc with
  `cwd=metadata/` instead of the document's own directory
  (`resource_path_option()`'s own `pandoc_cwd` parameter), and compensates
  with `--resource-path`. But `--resource-path` only helps Pandoc's own
  image resolution — a real `Image` AST node from Markdown `![]()` syntax.
  Per pandoc's own manual, it "will not cause image paths to be rewritten
  in other cases (e.g., when pandoc is generating LaTeX)." A raw
  `\includegraphics{...}` in the document's own hand-written LaTeX, or a
  package macro that reads a relative-path data file (confirmed directly:
  nulabreport's `\irspectrum`/`\irspectrumcompare`, which hand a relative
  CSV path to pgfplots' own table-reading code), is resolved entirely by
  the TeX engine's own kpathsea search relative to `pandoc_cwd` — broken
  the moment that differs from the document's own directory, which is
  exactly what a `metadata/` subfolder does. Reproduced directly on
  `LR4-5/report.md`: lualatex failed first on
  `tlc/contour/plate-1_contour.png` (a raw `\includegraphics`), and again
  — after a report-local `\graphicspath` workaround fixed that one — on
  `ir/own-15.09/plain/aldehyde_plain.csv` (an `\irspectrumcompare` pgfplots
  table read), the same underlying cause surfacing through two unrelated
  macros. Fixed generally, not per-macro: new `tex_search_env()` sets
  `TEXINPUTS` (the one mechanism kpathsea honors for every one of these
  lookups at once) to include the document's own directory, passed via
  `env=` to both `--pdf-engine=`-invoking `subprocess.run()` calls
  (single-file/batch mode's `run()`, and report mode's engine loop). A
  no-op — `env=None`, subprocess inherits the parent environment exactly
  as before — whenever `pandoc_cwd == document_directory`, the common case
  with no `metadata/` subfolder or out-of-tree `-y` in play, mirroring
  `resource_path_option()`'s own condition exactly.

## v3.7.0 — 2026-09-21

Backup reference: `backups/pdfmd.py.bak-20260921a`. Found and fixed live
while migrating a `nulabreport` pre-lab document onto a shared
`--metadata-file` (`nulabreport/prelab-metadata.yaml`) in place of a
per-document `preamble.tex` — see that project's own `docs/CHANGELOG.md`
v1.15.0 entry and `LR4-5/prelab/backups/findings.md` for the document side.

### Changed

- **PDF-metadata stamping (`PdfmdVersions`/`PdfmdBuildDate`, on by default —
  see `--stamp-pdf-metadata`) is now a post-hoc edit of the finished PDF via
  the optional `pypdf` dependency, not LaTeX baked in before the engine
  runs.** Two real reasons, not a refactor for its own sake:
  1. **It silently broke a document's own package loads.** The old approach
     added a small `\hypersetup{pdfinfo=...}` snippet via a second
     `--include-in-header` file. Confirmed directly: pandoc's default LaTeX
     template gives `--include-in-header` and a metadata file's own
     `header-includes:` key THE SAME template slot, and `--include-in-header`
     wins outright rather than merging — so any `--metadata-file` that set
     `header-includes:` (not the `.md` document's own front matter, which
     `document_header_file()`/`wrap_latex_header_includes()` already
     protects) had its entire header-includes silently discarded the moment
     PDF-metadata stamping was also on, with no error at that point —
     surfacing only later as a confusing "Undefined control sequence" the
     first time the document used a macro from whatever it just lost.
  2. **It only ever worked on `LATEX_ENGINES`.** A non-LaTeX PDF engine
     (weasyprint, typst, soffice, ...) had no equivalent injection point
     this reached at all, so `pdf_metadata: true` silently did nothing
     there. A post-hoc edit of the produced PDF works identically regardless
     of which engine made it.
  - `pdf_metadata_snippet()` is left in place (now always returns `None`)
    rather than removed, since several call sites across the engine-
    fallback/native-bibliography/report/batch paths already thread its
    return value through as a plain parameter and already treat `None` as
    "no extra `--include-in-header` entry" — this retires the mechanism
    without touching any of that surrounding control flow. The real
    implementation is the new `stamp_pdf_metadata_posthoc()`, called from
    inside `stamp_after_success()` (now independent of `options["enabled"]`,
    which only ever gated the separate `.md`-source BUILD NOTES stamp).
  - Silently skipped, with a `WARN` under `--verbose`, if `pypdf` isn't
    installed — same soft-dependency convention this file already uses for
    `PyYAML`.

### Fixed

- **`citation-engine: natbib`/`biblatex` never called `stamp_after_success`
  at all** (`convert_via_native_bibliography`'s own call site in
  `convert_one`) — neither the `.md` BUILD NOTES stamp nor a PDF-metadata
  one ever fired for a document using this option, unlike every other
  success path in the same function. Found while verifying the change
  above through the full `pdfmd` pipeline (not just a synthetic `pandoc`/
  engine invocation, per this file's own process note); fixed by calling
  `stamp_after_success()` there too, on success, matching the other paths.

### Known gap, not fixed here

- Report/book mode's PDF-target branch (`main()`, the block whose own
  2026-09-20 comment already flags this) still never calls
  `document_header_file()`, so `files[0]`'s own front-matter
  `header-includes:` can still collide with `--include-in-header` from a
  report preamble the same way PDF-metadata used to — this change removes
  PDF-metadata as one trigger of that collision, but a report preamble
  itself can still cause it. Left as previously flagged: no report/book-mode
  document was available this session to verify a fix against.

## v3.6.0 — 2026-09-20

Backup reference: `backups/pdfmd.py.bak-20260920b`. Same CHEM 341 session as
v3.5.1 just below, requests raised directly while watching that build's own
output.

### Added

- **`--full-paths`** (default off): AUTO YAML/TEX/MD, the OK/FAIL/SKIP/
  `[WARNING] unnumbered Markdown` status lines, and (with `-v`) the CMD line
  now print a path relative to the current directory by default, falling
  back to the absolute path only when it isn't under cwd at all (a system
  temp file, e.g.). `-v`/`--verbose` (and `--debug`, which already implies
  it) turns full paths back on too -- more detail is the point of asking for
  verbose -- so `--full-paths` on its own is really for getting full paths
  WITHOUT the rest of `--verbose`'s output. Raised directly: the previous
  always-full-path default is fine from a shallow directory (Downloads) but
  genuinely hard to read from a deep one -- the concrete example was a path
  under `.../Library/CloudStorage/OneDrive-.../Documents/Fall26/CHEM341/
  guides/M1`. New `display_path()` helper; applied at every AUTO YAML/TEX/MD
  and status-line call site plus `log_cmd()`, but NOT the `MARGIN`/
  `MONOFONT`/`PAPERSIZE`/etc. `note()` detail strings (those still embed
  `{md_path}` in full) -- narrower scope than a complete sweep, chosen to
  match what was actually asked for ("auto md, auto yaml, auto tex") rather
  than guess at a larger one under time pressure; a `note()`-detail pass is
  a reasonable follow-up if the same complaint comes up there too.
- **`pagesize:` -> `papersize:` auto-correction** (`pagesize_typo_value()`,
  new `papersize` `--no-auto`/`pdfmd-options.no-auto` KIND): a document that
  sets `pagesize:` (not a real Pandoc variable -- `papersize:` is) and no
  `papersize:` of its own now gets `-V papersize=<value>` added
  automatically on LaTeX-family targets, with a `PAPERSIZE` AUTO note
  explaining the substitution. Raised directly: the CHEM 341 document this
  session was built around already had `pagesize: a4` in its own front
  matter and a task brief that KNEW it silently produced a Letter PDF
  instead -- documented as an accepted caveat rather than fixed, because
  nothing was catching it (that document has since been fixed by hand --
  `papersize: a4` directly -- once this made the gap obvious). Wired into
  `convert_one`'s two PDF-and-`-t`-latex-target branches, the same two
  places `geometry_needed`/`DEFAULT_MARGIN` already live -- NOT into
  `convert_via_native_bibliography` or either report-mode branch (same
  scoping call as the v3.5.1 fixes below: unverified paths left alone
  rather than patched blind).
- **`papersize:` translation for the typst engine** (`typst_papersize_translation()`,
  `TYPST_PAPERSIZE_ALIASES`, reuses the `papersize` KIND above): Pandoc's
  `papersize:` variable is LaTeX-shaped by convention ("letter", "legal",
  "a4", ...) and Pandoc's typst template passes that string straight through
  to typst's own `page(paper: ...)` rule, which does not accept "letter" or
  "legal" at all (typst's own names are "us-letter"/"us-legal"; most other
  names, "a4" included, already match and need no translation). Raised
  directly: letter and legal paper sizes worked with TeX engines but not
  with typst.
  Confirmed as a hard failure, not just a wrong default: `papersize: letter`
  through `--pdf-engine=typst` errored outright before this fix (typst
  rejects the unrecognized paper name), and produced a correct 612x792pt
  Letter PDF after it. Only the two confirmed-different names are aliased;
  extend `TYPST_PAPERSIZE_ALIASES` if another is found to differ the same
  way. Applies whether the size came from the document's own `papersize:`,
  a `-V papersize=`, or this session's own `pagesize:` auto-correction above
  -- wired into the same two `convert_one` branches, gated on `--to typst`/
  `engine == "typst"` respectively.
- **`pdfmd-options: preamble: ...`** (`frontmatter_extra_preambles()`): a
  document can now name its own LaTeX preamble file(s) explicitly -- a bare
  string or a YAML list, resolved relative to the document's own directory
  -- instead of relying on the fixed `preamble.tex`/`latex-preamble.tex`
  auto-discovered names. Merged with (appended after, so it can override)
  whatever `PREAMBLE_FILENAMES` auto-discovery already finds, and gated by
  the same `--no-auto preamble` as auto-discovery (an explicit CLI `-H`
  remains the one thing that survives even that). A path that doesn't exist
  is a hard `SystemExit`, not a silent skip. Wired into all four
  `find_preambles()` call sites (single-file, batch, report x2). Directly
  requested (`is it worth it?`) alongside a real use case that, on
  inspection, turned out NOT to need it after all -- see
  `frontmatter_extra_preambles()`'s own docstring for why (a preamble whose
  own `\setchemfig`/`\usetikzlibrary` calls need chemfig/tikz loaded first
  can only get that from `\input` inside a document's own header-includes,
  not from any `--include-in-header` ordering, named or auto-discovered
  alike) -- but the capability is still useful in general, and is what that
  document would reach for if it didn't have this specific ordering need.
  `metadata`/`filter` equivalents were asked about in the same breath but
  NOT implemented this round -- metadata-file discovery is more deeply
  woven into per-directory caching and `-y`/CLI-arg interplay than preamble
  discovery is, and deserves its own careful pass rather than a rushed
  version bolted on under the same time budget as everything else here.

### Verified

`--full-paths`: confirmed default (relative) and `--full-paths`/`-v`
(absolute) output on a real `pdfmd Midterm_guide.md ...` run against the
same CHEM 341 document. `pagesize`/`papersize` auto-correction: confirmed
against a synthetic `pagesize: a4` document (`pdfinfo` reporting `595.276 x
841.89 pts (A4)` by default, `612 x 792 pts (letter)` under `--no-auto
papersize`) -- not re-tested against the CHEM 341 document itself, which no
longer needs it (fixed by hand at the source instead once this made the gap
visible). typst translation: confirmed against a synthetic `papersize:
letter` document targeting `--pdf-engine=typst` (hard failure before the
fix, correct 612x792pt PDF after it). `pdfmd-options.preamble`: confirmed
end-to-end against a synthetic document (a `\newcommand` in a separately-
named preamble file, invoked in the body, rendering correctly in the output
PDF) -- the normal case, `--no-auto preamble` correctly suppressing it
(`\mygreeting` came back undefined, as expected), and a nonexistent named
file raising the intended `SystemExit` with a clear message. Only
single-file mode was run against a real `pdfmd` invocation; batch and
report mode use the identical `find_preambles(...) +
frontmatter_extra_preambles(...)` pattern at their own call sites but were
not separately exercised.

## v3.5.1 — 2026-09-20

Backup reference: `backups/pdfmd.py.bak-20260920a`. Found while building a
real document (a CHEM 341 study guide with its own `mainfont:`/
`header-includes:` front matter) end-to-end through `pdfmd`, not a synthetic
test -- both bugs below needed a document that both sets its own font AND
has its own YAML `header-includes` to surface, and only on the actual
direct-to-PDF path (`--stamp-pdf-metadata` is on by default there).

### Fixed

- **A document's own YAML `header-includes:` block silently vanished from
  ANY PDF build**, whenever `--stamp-pdf-metadata` was on (the default) --
  even with no preamble.tex/latex-preamble.tex auto-discovery involved at
  all. Root cause: Pandoc feeds every `--include-in-header` file into the
  same `header-includes` template slot as the document's own metadata, and
  a command-line-set variable silently replaces the metadata one rather than
  merging with it. `document_header_file()`/`document_header_includes()`
  already existed specifically to work around this -- by re-materializing
  the document's own header-includes into a trailing `--include-in-header`
  of pdfmd's own -- but all three call sites only turned it on when
  `preamble_files` was non-empty, not when the (unconditional-by-default)
  PDF-metadata stamp header was the thing about to trigger the bug. Fixed by
  turning the safeguard on whenever EITHER source will add an
  `--include-in-header` (`convert_via_native_bibliography`,
  `convert_one`'s `-t`/`-o` non-PDF-target branch, and its direct-PDF `run()`
  closure -- all three had the same gap). `document_header_includes()`'s own
  docstring updated to say so plainly, since it undersold the trigger before.
- **`-V mainfontfallback=<font>` crashed lualatex outright on the very
  first PDF attempt** for any document that sets its own `mainfont:` --
  before a single glyph was even confirmed missing. Cause: `run(first_font,
  fallback=document_font)` in `convert_one`'s direct-PDF path added Pandoc's
  own `mainfontfallback` mechanism whenever `document_font` was true, which
  is exactly backwards from the rest of the file's own stated design:
  `PREFERRED_FONT`'s docstring, and a comment on the `-t latex` non-PDF
  path right above this one, both already explain that Pandoc's
  `mainfontfallback` is known to crash lualatex in this environment, which
  is supposedly why pdfmd uses its own detect-then-retry-with-a-different-
  mainfont approach instead of ever touching it -- except this one call site
  still did, for exactly the one case (document already has its own
  mainfont) where the safe swap-retry can't apply either, so nothing ever
  covered it. Fixed to `fallback=False` unconditionally: a document that
  wants a fallback font can still set `mainfontfallback:` itself in its own
  front matter (or a linked metadata file), which reaches Pandoc through the
  normal metadata merge, not this `-V` injection, so it doesn't hit the
  crash.

### Verified

Both confirmed via the FULL `pdfmd` pipeline (not just the Pandoc/LaTeX
commands it constructs), per this file's own process note above: a real
document (`mainfont: "STIX Two Text"`, its own `header-includes:` with
`\usepackage{mhchem}` etc.) built clean end-to-end with `--stamp-pdf-metadata`
left at its default (on) -- header-includes survived in the rendered PDF's
own LaTeX, and no lualatex crash on the first pass. Not re-tested against a
document using `mainfont_auto`'s own STIX Two Text -> DejaVu Serif swap-retry
path (that path's `fallback` was already `False` before this fix and is
untouched by it), or against `-r`/`--report` mode's own separate font-
selection code (unaffected -- report mode doesn't call this `run()` closure).

## v3.5.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one used for the
whole of this session's work).

Two more items from later in the same conversation, requested together:
watch mode (a convenience feature, expected to see light use) and CSV/TSV table inclusion (one of the ideas raised
alongside the rejected `\input`-style raw-text inclusion syntax).

### Added

- **`-w`/`--watch`**: recompiles once immediately, then again on each
  later change to the source file's own directory or its `metadata/`
  subfolder (`watch_signature()` -- polls file mtimes, non-recursive,
  same two locations `accessory_directories()` already searches; no new
  dependency). Deliberately a thin wrapper (`run_watch()`) that re-execs
  the whole CLI as a fresh subprocess on each recompile (the original
  argv, minus `-w`/`--watch`) rather than threading a rebuild loop
  through `main()`'s own batch/report/single-file branching --
  disproportionate engineering for a feature expected to see light use.
  Single-file mode only; combining it with `-b`/`-r` is a clear error.
  Signature is re-snapshotted AFTER each recompile, not just before, so
  the compile's own output file (or a `--stamp` write back into the
  source) never falsely re-triggers another immediate recompile.
- **CSV/TSV table inclusion**: a fenced Div with class `csv` (`::: {.csv
  file="data.csv"} :::`) is replaced with an actual table read from that
  file (`CSV_TABLE_LUA_FILTER`, `contains_csv_table()`,
  `csv_table_filter_args()`). Capped at 10 rows/7 columns by default
  (`rows`/`cols` attributes override either, including `all`), per the
  request's own suggested numbers, with a truncated table getting both a
  `WARN` and a note printed directly under the table in the rendered
  output itself. Delimiter auto-detected from the extension
  (`.tsv`/comma otherwise) or set via `delimiter=`; `header="false"` for
  a header-less CSV. A Div, deliberately, not a new raw-text sigil/key
  scanned over the Markdown source before Pandoc sees it -- the same
  `\input`-style inclusion idea raised in the same conversation was
  passed over for exactly the risk this avoids (firing inside a fenced
  code block containing a literal syntax example): Pandoc has already
  told code blocks apart from real content by the time a Lua filter's
  `Div()` callback fires, so this can't happen at the AST level the way
  it could with a raw-text approach. Works for any output format (not
  LaTeX-specific, unlike the table-width filter) -- single-file, batch,
  report mode, and the v3.2.0 soffice PDF-engine bridge all support it.
  `csvtable` added to the `--no-auto`/`pdfmd-options.no-auto` KIND set.
  Builds the table via `pandoc.read()` on a hand-assembled GFM pipe-table
  string rather than constructing `pandoc.Table`'s AST nodes directly --
  reuses Pandoc's own already-correct pipe-table parser instead of this
  filter needing to get every field of `TableHead`/`TableBody`/`Cell`/
  `ColSpec` right by hand, and guarantees the result is indistinguishable
  from a hand-written table, including to `TABLE_WIDTH_LUA_FILTER`
  re-balancing it afterward (ordered to run first, for exactly that
  reason).

### Fixed (found building the CSV feature's own tests, before release)

- **A `.csv` div in a front-matter-less document rendered as literal,
  smart-quoted source text** (`::: {.csv file="small.csv"} :::`) instead
  of being recognized as a Div at all: `resolve_from_format()` bumps a
  front-matter-less document to the `gfm` reader (see its own docstring),
  which -- unlike Pandoc's default `markdown` reader, where it's on by
  default -- does not enable `fenced_divs` at all. Fixed by adding
  `+fenced_divs` onto `gfm` specifically when `contains_csv_table()`
  detects the document needs it, mirroring the existing
  `+definition_lists` pattern right above it.
- **A real Lua runtime error**, once the Div was actually being
  recognized: `"bad argument #2 to 'insert' (number expected, got
  string)"`. Cause: `string.gsub` returns TWO values (the result string,
  and a count of substitutions), and `escape_cell()`'s bare `return
  text:gsub("|", "\\|")` leaked both -- as the LAST argument to a later
  `table.insert(escaped, escape_cell(...))` call, ALL of a Lua function's
  return values get spliced in as separate arguments, so this silently
  became the 3-argument `table.insert(list, pos, value)` form, with the
  escaped string misread as `pos`. Fixed by wrapping the return in
  parens (`return (text:gsub(...))`), which truncates to one value.
- **The table's own last data row rendered as a stray, unparsed
  paragraph** ("| Bob | 25 | Boston |" as literal text) instead of the
  table's actual last row, even after both bugs above were fixed.
  Isolated with a minimal standalone repro: `pandoc.read(text, "gfm")`,
  called from inside a Lua filter, needs an explicit trailing blank line
  to correctly close out a pipe table's final row -- the IDENTICAL text
  read by Pandoc's own CLI (`pandoc -f gfm`) from a file does not need
  this, so it's specifically a `pandoc.read()`-from-a-filter quirk, not a
  general GFM pipe-table requirement. Fixed by appending `"\n\n"` before
  calling `pandoc.read()`.

### Verified

Through the actual `pdfmd` CLI: `-w`/`--watch` compiled a real document
immediately, then correctly recompiled after the source was edited a
second time (confirmed by reading the regenerated PDF's text each time);
`-b`/`-r` combined with `-w` confirmed to raise the documented clear
error. CSV inclusion: a real 2-row CSV with a quoted, comma-containing
field ("New York, NY") rendered correctly as a proper table (confirmed by
reading the PDF's text, not just a successful exit code -- this is
exactly the test that caught both Lua bugs above); a 20-row/9-column CSV
correctly truncated to 10/7 with the WARN and in-document note, then
correctly included in full with `rows=all cols=all`, then correctly
limited to exactly 1 row/2 columns with `rows=1 cols=2`; a `.tsv` file
auto-detected via extension; `--no-auto csvtable` confirmed to drop the
filter and leave the div inert; a `.csv` div naming a nonexistent file
confirmed to `WARN` and leave it empty rather than failing the compile;
report mode confirmed to support CSV inclusion too. Regression: a plain
`.md`, a direct `.tex`, and a direct `.docx` were all re-run after every
change in this round and confirmed unaffected.

---

## v3.4.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one used for the
whole of this session's work -- v3.1.0 through this release were all
developed back-to-back in one sitting, no real-world use of any
intermediate version in between).

The last of the items from the original round started in v3.1.0: citation
engine routing (`citeproc` vs. native `biblatex`/`natbib`), decided
("opt-in via pdfmd-options") in the very first planning round for this
whole session but never assigned to a numbered phase alongside the other
three -- built now as a follow-up once flagged.

### Added

- **`pdfmd-options.citation-engine: natbib`/`biblatex`** routes a LaTeX-
  family PDF target's (or `--to latex`/`beamer`/`context`'s) bibliography
  through Pandoc's own `--natbib`/`--biblatex` flags instead of
  `--citeproc` -- native biber/bibtex processing via the engine's own
  bibliography tooling, using the document's existing `bibliography:`
  field, rather than citations rendered directly into the generated LaTeX
  via a CSL style. Default stays `citeproc` -- a document only needs this
  key at all to opt into something else, per the original decision.
  `frontmatter_citation_engine()` reads it with the same document-then-
  metadata-file precedence as `frontmatter_engine()`; an unknown value
  raises a clear `SystemExit` naming the three valid ones.
- **`convert_via_native_bibliography()`** does the actual work for a PDF
  target, and it is NOT as simple as adding `--natbib`/`--biblatex` next
  to the usual `--pdf-engine=<engine>` invocation. Confirmed empirically,
  before writing any of this: a real document compiled with `pandoc ...
  --pdf-engine=lualatex --natbib` came out with citations completely
  undefined ("Citing ? here.") -- Pandoc's own PDF-making pipeline never
  runs bibtex/biber at all when it calls a LaTeX engine directly this way,
  *regardless* of engine, except `--pdf-engine=latexmk` (latexmk manages
  that itself). Rather than restrict this feature to latexmk only, it
  generates a complete standalone `.tex` via Pandoc first (mirroring
  `convert_one`'s own `TEX_STANDALONE_FORMATS` branch), then hands it to
  v3.1.0's `compile_tex_direct()` -- which already runs exactly the
  rerun-until-stable + automatic bibtex/biber loop this needs, for ANY of
  lualatex/xelatex/pdflatex/latexmk/tectonic, reusing that work directly
  rather than duplicating it.
- For the non-PDF `--to latex`/`beamer`/`context` branch, the equivalent
  substitution (`--natbib`/`--biblatex` instead of `--citeproc`) needed no
  bridge at all -- that branch never runs an engine itself, it just hands
  the caller a `.tex` to compile (and resolve its own bibliography in)
  themselves.
- **`citationengine`** added to the `--no-auto`/`pdfmd-options.no-auto`
  KIND set. Meaningless (silently ignored) for any non-LaTeX target --
  HTML, typst, docx, an office document, or the v3.2.0 soffice PDF-engine
  fallback -- same as e.g. LaTeX-only geometry/monofont defaults already
  are; a document that sets it but resolves to a fallback chain with no
  LaTeX-family engine available at all gets one clear `WARN` and falls
  back to `--citeproc` rather than silently ignoring the setting or
  hard-failing.

### Fixed (found building this feature's own tests, before release)

- **A first version of `convert_via_native_bibliography()` generated its
  intermediate `.tex` into a throwaway `mkdtemp()` scratch directory --
  compiled without any reported error, but left the citation completely
  unresolved** ("Citing ? here.") because bibtex/biber run with
  `cwd=tex_path.parent` (same as `compile_tex_direct()` always has), and a
  `/tmp` scratch directory has no relationship to the document's own
  `refs.bib`. Same underlying class of bug as v3.1.0's `openout_any`
  fix, just from the opposite direction (wrong directory entirely, not a
  security policy blocking the right one). Fixed by generating the
  intermediate `.tex` directly beside `md_path` instead (`mkstemp(dir=
  md_path.parent, ...)`, cleaned up in a `finally` unless `--keep-aux`),
  so a relative `\bibliography{}`/`\addbibresource{}` resolves the same
  way it would for a real, hand-written `.tex` in that directory.
- **The fix above then hit a second, unrelated bug of its own**: the
  first attempt named that temp file with a leading dot
  (`.natbib.pdfmd-nativebib-xxxx.tex`), matching the convention
  `prepared_latex_inputs()` already uses for ITS OWN temp files -- except
  those are only ever Pandoc *input* (a `--metadata-file`/title source),
  never something a LaTeX engine compiles directly as its own jobname.
  Confirmed with a standalone repro (`lualatex .hidden.tex`): a LaTeX
  engine derives its jobname from the input filename up to the FIRST
  period, which is empty for a dotfile, so it silently ignores
  `-output-directory` and tries to write its own `.log` next to the
  source instead -- tripping the exact same `openout_any=p` wall a
  second, unrelated way. Fixed by dropping the leading dot from this
  specific temp filename (`{stem}-pdfmd-nativebib-xxxx.tex`, not
  `.{stem}.pdfmd-nativebib-xxxx.tex`).

### Verified

Through the actual `pdfmd` CLI: a real document with `pdfmd-options:
{citation-engine: natbib}` and one with `citation-engine: biblatex` both
compiled correctly, confirmed by reading the rendered PDF's text -- natbib
produced "Einstein [1905]" (natbib's own bracket-year style), biblatex
produced "Einstein [1]" with a numbered reference list entry, both
visibly different from citeproc's "Einstein (1905)" default, confirming
each engine's own real bibliography backend actually ran (not just that
compilation succeeded). A plain document with no `citation-engine` key set
confirmed unaffected (`--citeproc`, unchanged). `--keep-aux` combined with
`citation-engine: natbib` confirmed to leave the intermediate `.tex` AND
its own `.aux`/`.log` behind for inspection, correctly named and readable.
An unknown `citation-engine` value confirmed to raise a clear error. A
document requesting `natbib` while restricted to `--engine html`
confirmed to print the clear `WARN` and fall back to `--citeproc`
successfully rather than failing outright. Regression: a plain `.md`, a
direct `.tex`, a direct `.docx`, and a crossref-using `--to latex` output
were all re-run after every change in this round and confirmed unaffected.
No leftover files in any test directory after any of the above.

---

## v3.3.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one used for the
whole of this session's work -- v3.1.0 through this release were all
developed back-to-back in one sitting, no real-world use of any
intermediate version in between).

Phase 3 of the round started in v3.1.0 (see that entry for the full list
and the phasing rationale): pandoc-crossref auto-detection, and a math-
aware fix for the table-width Lua filter. Both were among the specific
items suggested (by another AI, per the author) at the start of this round.

### Added

- **pandoc-crossref auto-detection**: a document using `@fig:`/`@eq:`/
  `@tbl:`/`@sec:`/`@lst:` reference syntax, or a `{#fig:...}`-style
  numbered-element attribute, now automatically gets `--filter pandoc-
  crossref` (`contains_crossref()`, `crossref_filter_args()`) -- added
  BEFORE `--citeproc` in the command array in every one of the five
  places pandoc-crossref could apply (both single-file/batch `convert_one`
  PDF paths, the non-PDF `TEX_STANDALONE_FORMATS` branch, the v3.2.0
  soffice bridge, and both of report/book mode's own inline command-
  builders), since pandoc-crossref has to resolve/number references
  before citeproc runs or citeproc treats the leftovers as unresolvable
  bibliography keys. That ordering bug was real and already live before
  this fix: `contains_citations()`'s generic `@key` regex already matches
  `@fig:setup` too (a colon is a valid citation-key character), so a
  crossref-only document was already getting `--citeproc` added --
  confirmed directly (see "Verified" below) that citeproc alone reports
  `citation fig:setup not found`/`citation tbl:results not found` for
  exactly this reason. A document that needs crossref but doesn't have
  the `pandoc-crossref` binary installed gets one clear `WARN` instead of
  silently shipping unresolved references into the rendered output.
  `crossref` added to the `--no-auto`/`pdfmd-options.no-auto` KIND set.
- **Math-aware table-width Lua filter**: `TABLE_WIDTH_LUA_FILTER`'s
  `cell_length()` used to measure a `Math` inline via
  `pandoc.utils.stringify()`, which returns its raw LaTeX SOURCE (e.g.
  `\frac{1.0 \times 10^{-14}}{[OH^-]}`, 34 characters) rather than
  anything close to its typeset width -- exactly the chemistry-table
  scenario (Ksp calculations, uncertainty propagation) flagged in the
  original suggestion. Fixed with `math_overcount()`, which walks each
  cell's content for `Math` nodes and discounts each one's raw source
  length by a flat `MATH_LENGTH_DIVISOR = 3` before it factors into the
  column's natural-width estimate -- a rough heuristic, like every other
  measurement this filter already makes (see its own long Python-side
  comment), not a real LaTeX-width calculation, which nothing at Lua-
  filter time has the means to do.

### Verified

Through the actual `pdfmd` CLI and real Pandoc invocations, not synthetic
assertions: a document mixing `@fig:`/`@tbl:` crossref syntax, an
attribute-defined figure/table, AND a genuine `@einstein` bibliography
citation all resolved correctly in one compile (`pdftotext` showed
"Figure 1"/"Table 1"/"fig. 1"/"tbl. 1" numbering from pandoc-crossref
alongside a properly formatted "Einstein (1905)" citation and reference-
list entry from citeproc -- both filters firing correctly in the same
run, in the right order); `--no-auto crossref` confirmed to drop the
filter from the command line; a plain citation-only document (no crossref
syntax) confirmed to never get the filter added at all; pandoc-crossref
temporarily moved aside (`mv` its real binary, restored immediately after)
to confirm the missing-binary WARN fires, and that citeproc alone then
visibly mishandles the crossref keys exactly as described above -- direct
evidence the bug this fixes was real, not hypothetical. For the table
filter: extracted both the OLD (pre-fix, from `backups/
pdfmd.py.bak-20260919c`) and NEW filter to real `.lua` files and ran both
through actual `pandoc --lua-filter` on the same synthetic math-heavy
table, comparing the emitted LaTeX `\real{...}` column-width fractions
directly -- old gave the math column 19.15% (inflated by its 34-character
raw source) and the genuinely long prose column only 73.23%; new gives
them 7.80%/84.55%, correctly reflecting where the real width need is.
Then compiled the same table through the full `pdfmd` pipeline to a real
PDF (not just Pandoc's intermediate LaTeX) to confirm it still renders
correctly end to end. Regression, per CLAUDE.md's own explicit "test both
directions" instruction from the original 2026-09-16 table-width fix: a
plain short table (old and new both correctly return nil/natural-width,
no `\real{...}` at all) and a deliberately-overflowing table with NO math
in it (old and new produce byte-identical fractions, 7.59%/92.41%,
confirming zero behavior change for any table that never touches a Math
node) were both re-run against both filter versions side by side.

---

## v3.2.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one v3.1.0/v3.1.1
used -- v3.1.0, v3.1.1, and this release were all developed back-to-back
in one sitting, no real-world use of the intermediate versions in between).

Phase 2 of the round started in v3.1.0 (see that entry for the full list
and the phasing rationale). This phase: a soffice/LibreOffice fallback in
the PDF-engine chain, and direct office-document-to-PDF conversion.

### Added

- **soffice as a last-resort PDF-engine fallback** for Markdown/Pandoc
  input: `-e/--engine soffice` (alias `office`/`libreoffice`, numeric
  `14`), or left to the unrestricted chain, where it is tried only after
  every tex/typst/html engine has failed or is missing
  (`convert_via_soffice_bridge()`). Not a real Pandoc `--pdf-engine` --
  Pandoc has no native "write ODT, then shell out to LibreOffice" engine
  -- so this is special-cased directly in `convert_one`'s own fallback
  loop: Pandoc renders an intermediate `.odt`, then headless soffice
  converts that to PDF. Citeproc and a document's own auto-discovered Lua
  filters still apply; LaTeX-only concerns (geometry/mainfont/monofont/
  preamble/table-width filter) don't, since none of them mean anything
  for an ODT target. New `ENGINE_GROUPS["office"]` family keyword for
  `-e office`/a document's `pdf-engine: office` front-matter restriction.
- **Direct office-document-to-PDF conversion**: a `.docx`/`.doc`/`.odt`/
  `.ott`/`.rtf`/`.pptx`/`.ppt`/`.odp`/`.xlsx`/`.xls`/`.ods` input targeting
  PDF converts straight through headless soffice (`convert_office_direct()`
  / `run_soffice_convert()`), no Pandoc involved -- requested directly,
  to stop having to type out `soffice --headless --convert-to pdf <path>`
  by hand. Every soffice invocation (both
  this and the fallback above) gets its own scratch
  `-env:UserInstallation` profile, since concurrent/rapid-fire calls
  (batch mode's `-j`) otherwise collide on the shared default profile's
  lock and fail with "another instance is already running."
- **`resolve_soffice()`/`engine_executable()`**: `soffice` is reachable on
  this machine (and plausibly others) only through an interactive shell
  alias pointing straight at the macOS `.app` bundle's own binary --
  invisible to `which()`/`subprocess`, neither of which consults shell
  aliases. Caught immediately (`--check-dependencies` reported soffice as
  MISS despite it working fine at a real terminal prompt) before this
  round's own feature could even be tested. `engine_executable()` (used
  everywhere `PDF_ENGINES` membership is checked: `installed_engines`,
  `select_engines`, `dependency_report`) checks `soffice`/`libreoffice` on
  PATH, then the standard macOS app-bundle path directly, before
  reporting an engine missing.
- **`officedirect`** added to the `--no-auto`/`pdfmd-options.no-auto` KIND
  set -- see "Known limitation" below for what disabling it actually does
  (not what the equivalent `texdirect` kind does for `.tex`).

### Changed

- **A `.docx`/`.odt` input targeting PDF now converts via soffice by
  default instead of the old Pandoc-mediated route** -- a default
  behavior change for anyone already running `pdfmd report.docx` today
  (flagged per CLAUDE.md's semver rule, same as v3.1.0's `.tex` change).
  Pandoc's own docx/odt reader can produce a PDF too, but loses the
  original document's layout going through Pandoc's AST and LaTeX writer;
  soffice preserves it directly. `.pptx`/`.ppt`/`.xlsx`/`.xls`/`.odp`/etc.
  have no Pandoc reader at all and could never reach a PDF through pdfmd
  before this version -- pure addition for those, not a flip.

### Fixed (found wiring up this phase's own new feature, before release)

- **`pdfmd source.docx` and `pdfmd source.pptx` both crashed outright**
  the first time this phase's own new feature was tested against a real
  office file, well before reaching any of the new soffice code: `main()`
  unconditionally calls `frontmatter_value()`/`metadata_for()` on every
  single-file input looking for a `documentclass`/`class` front-matter
  key, and both read the file as UTF-8 text -- fatal on a zip-based
  binary format. This bug predates this phase entirely (feeding pdfmd a
  `.docx` would have hit the exact same crash before any of this round's
  changes existed, just apparently never actually tried); fixed here
  since it sits directly in the path of the feature this phase adds, not
  filed as a separate known-issue the way v3.1.0 did for the unrelated
  `resolve_from_format` bug. Fixed with a new early dispatch branch in
  `main()` (mirroring the existing `.qmd` special case) that routes an
  `OFFICE_INPUT_EXTENSIONS` file straight to `convert_one` without any of
  that Markdown-oriented front-matter/preamble discovery.
- **The same crash recurred one level deeper**: `effective_no_auto()` and
  `resolve_engines()` both call `frontmatter_pdfmd_options()`
  unconditionally too (looking for a document's own `no-auto`/`pdf-engine`
  front-matter settings), which has the identical text-read-on-binary-
  file problem -- reached even after the `main()` fix above, and also
  reachable for a `.tex` file (though rarely hit in practice there, since
  most `.tex` input now goes through v3.1.0's own direct-compile branch
  first). Fixed at the source instead of patching each caller:
  `frontmatter_pdfmd_options()` now returns `{}` immediately for anything
  in `OFFICE_INPUT_EXTENSIONS`, without attempting to read it.
- **`--no-auto officedirect` (and a non-PDF `--to`, or an explicit
  `--from`) on an office document crashed too**, one call further into
  `convert_one`'s generic Pandoc-oriented machinery (`has_mainfont`,
  `contains_citations`, `find_lua_filters`, `promote_bare_title`, ... --
  all assume text input). Unlike `.tex`'s `texdirect`, there is no
  supported way to make this route actually work without auditing every
  one of those helpers for binary-safety, judged out of scope for this
  phase (see "Known limitation" below) -- so instead of leaving a
  flag that reliably crashes a few calls later, these combinations now
  raise one clear `SystemExit` explaining that only direct PDF conversion
  is supported for an office document in this version.

### Verified

Through the actual `pdfmd` CLI: a real `.docx` and a real `.pptx`
(generated via `pandoc source.md -o source.docx`/`-t pptx`, then fed back
into `pdfmd`) both converted correctly, confirmed by extracting and
reading the rendered PDF's text, not just checking for a successful exit
code -- `.pptx` specifically confirms a format Pandoc cannot read at all
now reaches a PDF; `--engine soffice` forced directly on a `.md` source
(the fallback-bridge path, not the direct-input path) also verified by
reading its rendered text; `--no-auto officedirect`, a non-PDF `--to` on
an office file, and an explicit `--from` all confirmed to fail with the
new clear error instead of a traceback; `--check-dependencies` confirmed
`soffice` now reports OK via `engine_executable()` instead of MISS; and,
for regression, a plain `.md` document (still routes through Pandoc with
`--pdf-engine=lualatex`, unchanged) and a `.tex` document (still uses
v3.1.0's direct-compile path, unchanged) -- both re-run after every
change in this round, confirming the new per-engine-loop `soffice`
branch and the two office-input branches don't touch either existing
path. No leftover scratch directories after any of the above.

### Known limitation

Unlike `.tex`'s `texdirect`, disabling `officedirect` does **not** route
a `.docx`/`.odt` back through the old Pandoc-mediated path -- it raises a
clear error instead (see "Fixed" above for why: that route crashes deeper
in, in code this phase didn't audit for binary-safety, and arguably isn't
worth making work at all, since it would only produce a worse-formatted
PDF than direct soffice conversion already does). If a genuine need for
Pandoc-mediated `.docx`/`.odt` conversion ever comes up, that would be its
own follow-up, auditing `has_mainfont`/`contains_citations`/
`find_lua_filters`/`promote_bare_title`/etc. for binary input rather than
just the two front-matter functions this phase fixed.

---

## v3.1.1 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one v3.1.0 used --
developed back-to-back in the same sitting, no real-world use of v3.1.0 in
between).

### Fixed

- **The "known issue" flagged in v3.1.0's own changelog entry, fixed the
  same day it was found**: `resolve_from_format()` decided the Pandoc
  reader purely from front-matter/metadata-file presence, never from the
  file's own extension, so any non-Markdown Pandoc input (`.tex`, `.html`,
  `.rst`, ...) with no YAML front matter of its own was silently read as
  `gfm` instead of Pandoc inferring the right reader from its extension --
  live for a `.tex` file specifically via `--to` a non-PDF target or
  `--no-auto texdirect` (the direct-.tex-compile path added in v3.1.0
  doesn't go through this function at all, so most `.tex` input no longer
  hits it in practice, but both escape hatches still do). Fixed by
  returning early (no override) for anything other than a real
  `.md`/`.markdown` suffix -- the gfm heuristic is specifically about
  ordinary GitHub-Flavored-Markdown authoring conventions and was never
  meant to apply to another format's own file. Pre-existing bug, unrelated
  to v3.1.0's own changes; not a default flip for any document this was
  ever working correctly for (a `.md`/`.markdown` file's behavior is
  unchanged), hence a patch bump rather than another major one.

---

## v3.1.0 — 2026-09-19

Backup taken before this round: `backups/pdfmd.py.bak-20260919c`.

**Versioning note (the author's call, this session only):** this entry and the
two after it (v3.1.1, v3.2.0) were originally released as v4.0.0, v4.0.1,
and v5.0.0 -- each bump to the leading digit exactly per the semver rule
above (a default behavior change), since a real `.tex`/`.docx` input
changing how it's processed by default is precisely what that rule calls
major. The author's own judgment, after the fact: none of the three actually
break the script's core functionality (the Markdown/Pandoc pipeline this
script exists for is untouched by all three), so the leading digit stays
capped at 3 for this round and these three are renumbered as minor/patch
bumps instead. The semver rule itself is unchanged for future entries --
this is a one-time relabeling of this round only, not a standing
exception. Any "flagged here per CLAUDE.md's own semver rule"-type
language below describing these as major bumps is accordingly stale;
left as-is/see this note rather than rewritten line-by-line.

Phase 1 of a larger round of changes the author asked for (direct .tex compilation
with rerun detection and tectonic-style cleanup; a soffice/LibreOffice
fallback and direct office-to-PDF conversion; pandoc-crossref auto-
detection and a math-aware table-width filter; watch mode) -- scoped and
phased per the author's own call, one backup+changelog+verify cycle per phase
rather than one large patch, specifically so a regression in one phase
doesn't get tangled up with an unrelated one. This is phase 1 only; the
rest follow in later versions.

### Changed

- **A real `.tex` input targeting PDF is now compiled directly with a
  LaTeX engine, instead of being handed to Pandoc first** -- a default
  behavior change for every existing `pdfmd notes.tex` invocation, flagged
  here per CLAUDE.md's own semver rule even though raw `.tex` input is a
  much rarer case than the Markdown pipeline this script exists for.
  Previously, `.tex` input was read by Pandoc's own LaTeX reader and
  regenerated through Pandoc's LaTeX writer before an engine ever saw it --
  a lossy round-trip for exactly the kind of hand-written raw LaTeX (chemfig,
  tikz, custom macros) a `.tex` file is likely to contain on purpose. The
  new path (`compile_tex_direct()`, `run_tex_engine()`) skips Pandoc
  entirely: the `-e/--engine` fallback chain still applies, restricted to
  its LaTeX-family members (lualatex, xelatex, pdflatex, latexmk, tectonic
  -- not context, whose CLI/markup are unrelated to the other five).
  `--no-auto texdirect`, or an explicit `--from` other than `latex`/`tex`,
  opts back into the old Pandoc-mediated route for a document that
  specifically needs pdfmd's own font/margin/metadata/stamp injection
  applied to raw LaTeX; a non-PDF `--to` target was never affected (Pandoc
  is still the only way to get `.tex` into another format).

### Added

- **Automatic multi-pass compilation**: lualatex/xelatex/pdflatex are
  rerun (up to `MAX_TEX_DIRECT_PASSES` = 5 times) whenever the engine's own
  `.log` asks for another pass -- the same "Rerun to get..."/"Label(s) may
  have changed" signal latexmk itself watches for (`tex_wants_rerun()`),
  covering both a forward cross-reference (verified against a real
  `\ref` used before its `\label`: correctly took 2 passes, 1 on a
  second run where the label was already resolved) and, more generally,
  anything else that only settles after a previous pass's output feeds
  back in (this is also what would make a chemfig diagram's arrow
  angles/positions converge, per the author's own question when asking for this
  feature -- not separately tested here, no such diagram on hand, but the
  mechanism is the same generic log-driven rerun loop, not anything
  specific to bibliographies).
- **Automatic bibtex/biber**: `tex_bibliography_tool()` detects
  `\addbibresource{`/`\usepackage{biblatex}` (biber) vs. bare
  `\bibliography{` (bibtex/natbib) in the source and runs the matching
  tool once between engine passes, no flag needed. latexmk/tectonic
  already manage this (and their own reruns) internally and are each
  given a single wrapped call instead of pdfmd's own loop.
- **Scratch-directory cleanup, on by default, mimicking tectonic**: every
  engine pass writes into a fresh `-output-directory`/`-o` scratch
  directory; only the finished PDF is copied back out, and the scratch
  directory is deleted (even on failure -- verified no leftover
  `pdfmd-tex-*` directories after a synthetic 3-engine failure chain).
  The source directory is never touched, so a pre-existing `.aux`/`.log`
  from a previous manual/`--keep-aux` compile is left alone rather than
  swept up -- verified directly (a stale `.aux`/`.log`/`.out` set from an
  earlier `--keep-aux` run survived an unrelated later default-mode
  compile in the same directory untouched).
- **`--keep-aux`** turns the above off: compiles in place (no
  `-output-directory` at all) and leaves every `.aux`/`.log`/`.out`/etc.
  beside the source, for inspecting a failing or suspicious compile's own
  `.log` by hand -- restores the exact pre-v3.1.0-for-.tex behavior.
- **`texdirect`** added to the `--no-auto`/`pdfmd-options.no-auto` KIND set.

### Fixed (caught during this round's own verification, before release)

- **bibtex silently failed to resolve citations** (`Citing [?]` instead of
  `Citing [Einstein, 1905]`) the first time this was tested against a real
  `natbib`/`\bibliography{}` document -- exactly the kind of thing CLAUDE.md
  warns a synthetic/isolated check won't catch; this was only caught by
  reading the actual rendered PDF's text, not just checking bibtex's exit
  code or trusting a clean compile log. Cause: bibtex was run from the
  source directory but pointed at a target path inside the scratch
  `-output-directory`, which MacTeX's default `openout_any=p` (paranoid)
  security policy silently refuses to write outside of -- bibtex printed
  its own "Not writing to ... (openout_any = p; no extended check)"
  warning and returned nonzero, but the compile still "succeeded" with an
  unresolved citation. Fixed by running bibtex with `cwd` set to the
  scratch directory itself (satisfying the policy trivially) and
  `BIBINPUTS` pointing back at the source directory so it can still find
  the `.bib` file (bibtex has no `--input-directory` flag the way biber
  does). Re-verified against the same document: citation now resolves
  correctly. biber was unaffected (its own `--input-directory` sidesteps
  this) and needed no fix.
- **A failed direct-.tex compile's one-line reason was silently truncated
  mid-word** (e.g. "ed, no output PDF file produced!" instead of "...Fatal
  error occurred, no output PDF file produced!") -- caught the same way,
  by reading an actual failure's printed reason rather than trusting that
  a WARN line was produced at all. Two compounding causes: (1) `-file-
  line-error` (added for its own sake, to name the offending source line)
  changes LaTeX's error format from a leading `! ...` to `path:line:
  ...`, which the existing `engine_failure_reason()` helper (built only
  ever seeing Pandoc's own unwrapped stderr) doesn't recognize; (2)
  LaTeX's `.log` hard-wraps every physical line at `max_print_line`
  (confirmed 79 on this machine via `kpsewhich -var-value=max_print_line`,
  observed wrapping in practice at 80) with no word-boundary awareness,
  splitting exactly the tail-end summary line mid-word. Fixed with two new,
  direct-.tex-specific helpers instead of changing the shared
  `engine_failure_reason()` (which still works correctly for its original
  Pandoc-stderr callers and had no reason to change): `tex_log_dewrap()`
  rejoins physical log lines wrapped at/past that width before anything
  else inspects the text, and `tex_log_failure_reason()` prefers a `!
  ...` line, then a `path:line: ...` line (skipping the generic "Fatal
  error occurred..." trailer every halted run ends with, which names no
  actual cause), then falls back to the last non-blank line. Re-verified
  against the same synthetic `\thisisnotarealcommand` failure: reason now
  reads exactly "Undefined control sequence."
- **`shutil.copy2` crashed with `SameFileError`** under `--keep-aux` when
  no `-o`/`--out` redirected the output elsewhere: the engine already
  writes its PDF straight to the same path pdfmd would otherwise "copy"
  it to, since `--keep-aux` uses no `-output-directory` at all. Fixed by
  skipping the copy when the produced file and the target output already
  resolve to the same path.

### Verified

Per CLAUDE.md's "verify through the full pipeline, not a synthetic test"
rule -- all through the actual `pdfmd` CLI, not by hand-invoking Pandoc/
LaTeX/bibtex directly: a real forward-cross-reference document (2-pass
rerun, then 1-pass on a stable second compile); a `natbib`/bibtex
document and a `biblatex`/biber document (both citations confirmed
resolved by reading the rendered PDF's text, not just the exit code); a
deliberately broken document exhausting all five direct-compile engines
in order with correct family-skip behavior (lualatex/xelatex/pdflatex
fail together as expected, latexmk correctly skipped as sharing pdflatex's
pdftex family, tectonic correctly skipped as sharing xelatex's xetex
family) and no leftover scratch directories afterward; `latexmk` and
`tectonic` each run directly as the sole engine; `--keep-aux` (aux files
left in place, correct PDF) immediately followed by a default-mode compile
in the same directory (stale aux files from the `--keep-aux` run left
untouched, confirming cleanup only ever touches pdfmd's own scratch
directory); a `.tex` input targeting `--to html` and a `.tex` input with
`--no-auto texdirect` (both correctly still routed through Pandoc, per
this version's own documented escape hatches); and, for regression, a
plain `.md` document with a table and a bare title (identical Pandoc
command line and AUTO decisions as before this round, confirming the new
`.tex`-only branch -- gated strictly on file extension -- doesn't touch
the Markdown/Pandoc path at all).

### Known issue, found during this verification, not fixed here

`resolve_from_format()` (pre-existing, untouched by this round) decides
the Pandoc reader purely from front-matter/metadata-file presence, never
from the file's own extension -- so a `.tex` file routed through the old
Pandoc-mediated path (via `--to html`, or `--no-auto texdirect`) with no
YAML front matter of its own is read as `gfm`, not `latex`, unless
`--from` is given explicitly. Surfaced by this round's own edge-case
testing (`--to html`/`--no-auto texdirect` on a `.tex` file are both rare
paths that this version newly exercises more than before), not something
this round introduced or is in scope to fix -- noted here so it isn't
lost, in case a `.tex`-to-non-PDF or `--no-auto texdirect` user hits it.

---

## v3.0.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919b` (taken before v2.6.0 AND
this release both -- they were developed back-to-back in one sitting with
no real-world use of v2.6.0 in between, so there is no clean pre-v3.0.0-
only snapshot; rolling back to this one undoes both releases together).

### Added

- **`--stamp-pdf-metadata` embeds the same package/pdfmd version info
  directly into the rendered PDF's own Info dictionary**, as two custom
  keys (`PdfmdVersions`, `PdfmdBuildDate`) -- prompted by the author asking
  whether pdfmd's PDFs carry any metadata at all (checked with
  `pdfinfo`/`exiftool` against a real report: yes -- Title/Author from
  document metadata, Creator "LaTeX via pandoc", Producer the engine's own
  signature, Subject/Keywords empty by default) and whether pdfmd could
  insert its own version there as well. Implemented as a second, additive
  `\hypersetup{pdfinfo={...}}` call -- merges with Pandoc's own rather
  than overwriting pdftitle/pdfauthor/etc., so a document's real metadata
  is never touched. Invisible on the rendered page and in a normal
  "Document Properties" panel; readable with `exiftool`/`pdfinfo -meta`.
  LaTeX-family engines only -- a non-LaTeX PDF engine (weasyprint, typst,
  ...) has no equivalent mechanism this reaches, so it's silently skipped
  there. Verified against a real compile with `exiftool`: both custom
  keys present, Author/Title/Creator/Producer all unchanged.
- **Independent of `enabled`/the .md BUILD NOTES stamp**, per the author's direct
  follow-up asking for the .md and PDF stamps to be controllable
  separately (e.g. PDF on, .md off): `options['pdf_metadata']` is its own switch, checked on
  its own at each call site, not gated behind `options['enabled']` the
  way it was in the first cut of this feature (a real bug caught before
  release -- `--stamp-pdf-metadata` alone did nothing without `--stamp`
  too, verified and fixed). `--stamp` with PDF metadata off,
  `--stamp-pdf-metadata`/`pdf_metadata: true` with the .md stamp off, or
  both together, are all valid combinations now, confirmed with a 4-way
  test matrix.

### Changed

- **`pdf_metadata` now defaults to ON, unlike `enabled`** -- a deliberate
  default flip, the author's own call (the PDF stamp is harmless compared
  with the .md one): embedding two invisible,
  additive Info-dictionary keys has no visible effect on the rendered
  page or a normal "Document Properties" panel, unlike `enabled` (which
  edits the visible .md source and rightly stays off until asked). This
  means **every LaTeX-engine PDF pdfmd produces, across every pipeline
  that uses this script**, now carries a `PdfmdVersions`/`PdfmdBuildDate`
  Info entry unless `--no-stamp-pdf-metadata`/`pdfmd-options.stamp.
  pdf_metadata: false` turns it off -- flagged here explicitly because a
  default flip is exactly the kind of change CLAUDE.md's own semver
  section calls out as major, even though `pdf_metadata` itself only
  existed for a few hours before this flip and nothing has depended on
  the old default yet.

### Fixed

- **`pdf_metadata_snippet`'s `\ifdefined\hypersetup` guard never actually
  fired for a document with no LaTeX-loaded package of its own** (i.e.
  the exact bare-document case the new default-on behavior now hits
  constantly): generating the real `.tex` Pandoc produces showed
  `--include-in-header` content lands in the preamble BEFORE
  `\usepackage{bookmark}` (which is what actually loads hyperref
  indirectly -- there is no literal `\usepackage{hyperref}` line to be
  after), so `\hypersetup` was undefined at the point the guard checked
  it, and the whole block silently no-opped. It happened to work in
  every nulabreport-based test only because nulabreport.sty's own
  `--include-in-header`'d preamble loads hyperref itself, earlier in the
  same `-H` file list. Fixed by wrapping the whole call in
  `\AtBeginDocument{...}`, which defers it until every package is loaded
  regardless of `--include-in-header` ordering; the `\ifdefined` guard
  stays as cheap extra insurance, no longer load-bearing. Re-verified
  against the original failing bare-document case, all four
  enabled/pdf_metadata combinations, and a real nulabreport report/book
  build.
- **`--stamp-mode history`'s v2.6.0 redesign (see below) also gained a
  helper refactor here**: `gather_stamp_texts()`/`stamp_scope_matches()`
  extracted out of `stamp_after_success()` so the new pre-compile
  PDF-metadata path and the existing post-compile .md-stamp path share
  one implementation instead of two copies that could drift.

## v2.6.0 — 2026-09-19

Backup taken before this round: `backups/pdfmd.py.bak-20260919b`.

### Changed

- **`--stamp-mode history` restructured into a "Compile History:" trailer,
  same day it shipped.** The original v2.5.0 shape kept every past stamp
  line stacked at the TOP of the block, so each successive compile pushed
  a report's own hand-written BUILD NOTES (compound-library additions,
  values to recheck, etc.) one more line further from "BUILD NOTES" --
  clutter the author flagged immediately on trying it for real. `history` mode
  now keeps exactly ONE live stamp line at the top (so the latest compile
  is still always the first thing read) and demotes whatever was
  previously there into a `Compile History:` list of `  - ` bullets at the
  END of the comment, just before its closing `===...-->`,
  newest-demoted-first -- hand-written notes in between stay exactly where
  they are, at a fixed position, regardless of how many compiles happen.
  `update_build_notes()` now returns `(text, warning)`; `replace` mode
  never touches an existing history list (by design -- that log is meant
  to survive a mode switch), but now prints a WARN via `apply_stamp()`
  when one exists and has entries, since silently freezing a history a
  document was actively building was flagged as a real footgun by the author:
  switching to `replace` should only replace the last entry and leave
  every earlier entry below it untouched.
  Verified against a synthetic multi-step history-then-replace sequence
  and a real copy of LR1's report.md.
- **`~/dev/tex/nulabreport/metadata.yaml`** (the shared
  file symlinked into every course folder) now sets
  `pdfmd-options: stamp: {packages: [nulabreport], mode: history}`, so
  every report that finds it gets stamped automatically -- no per-report
  `--stamp` needed. `pdf-engine: tex` (already there) is untouched; `stamp:`
  was added as a sibling key under the same `pdfmd-options:` mapping.

## v2.5.0 — 2026-09-19

Backup taken before this round: `backups/pdfmd.py.bak-20260919a`.

### Added

- **New `--stamp` (and `pdfmd-options: stamp:`) feature automates a
  build-provenance note the author was already keeping by hand.** Real reports
  (LR1, LR3) already end in a `<!-- ===... BUILD NOTES ...=== -->` HTML
  comment -- invisible in the rendered PDF, visible in the .md source --
  whose one load-bearing line reads "Compiled with nulabreport vX.Y.Z,
  pdfmd vA.B.C", updated by hand after each real compile, sometimes with
  other freeform notes (compound-library additions, TODOs, values to
  recheck) written around it. `--stamp` automates just that one line --
  now with a timestamp appended -- and never touches anything else already
  in the block:
  - `resolve_stamp_options()`/`frontmatter_stamp()` cascade a document's
    own `pdfmd-options.stamp`, then each linked metadata file's, same
    precedence as `pdf-engine` (see `frontmatter_engine`) -- a shared
    `metadata.yaml` can turn stamping on for every report that finds it.
    CLI flags (`--stamp`/`--no-stamp`, `--stamp-mode`, `--stamp-packages`,
    `--stamp-scope`, `--stamp-output`/`--no-stamp-output`) win field by
    field on top of that.
  - `--stamp-mode replace` (default) overwrites the previous stamp line in
    place; `history` never overwrites -- each run inserts a new line above
    the previous ones, directly under "BUILD NOTES", so the newest entry
    always reads first (the author's spec: newest entry directly below
    BUILD NOTES).
  - `--stamp-packages nulabreport` includes a package's version via
    `kpsewhich <name>.sty` + that file's own `\ProvidesPackage` line --
    matching `nulabreport.sty`'s real `\ProvidesPackage{nulabreport}
    [2026/09/18 v1.14.7 ...]` line exactly. A named package is silently
    left out of the line if this document doesn't actually `\usepackage`
    it, or no version could be determined -- never a hard failure.
  - `--stamp-scope` (`always`/`report`/`standalone`) answers the author's own
    follow-up question: a document can ask to be stamped only when
    compiled as a whole report/book, not on its own, or the reverse.
    `--stamp-output` names the rendered file even outside report mode; a
    report/book chapter's stamp always names the shared output ("Compiled
    as part of `book.pdf` with ..."), regardless of this flag, and gets
    written into every chapter file that's part of that report, not just
    the first.
  - `BUILD_NOTES_RE`/`update_build_notes()` locate the comment anywhere in
    the file (not assumed to be the last line -- a report chapter's own
    comment can end up mid-file once concatenated with others, per the author's
    own concern), and only ever touch the single recognized stamp line
    inside it, identified by pattern (a line starting "Compiled" that
    mentions "pdfmd vX") rather than by any new, differently-styled marker
    -- so it reads as a natural extension of what the author already writes by
    hand, not a second, redundant-looking line next to it. Verified
    against real copies of LR1's and LR3's `report.md` (the latter's
    multi-paragraph hand-written notes below the stamp line came back
    byte-for-byte unchanged, confirmed by diff) and a from-scratch
    document with no BUILD NOTES block at all.

## v2.4.0 — 2026-09-18

Backup taken before this round: `backups/pdfmd.py.bak-20260918a`.

### Added

- **Auto-discovered metadata YAML, preambles, and Lua filters can now live in
  a `metadata/` subfolder instead of directly beside the document.** Raised
  by the author: a report's own top-level folder currently holds nothing but a
  symlinked `metadata.yaml`/`nulab.bib`/`nulabreport.lua`, a copied-and-edited
  `preamble.tex`, and sometimes a symlinked `chemicals.tex` -- entirely
  because pdfmd only ever looked beside the document, which leaves a folder
  that's supposed to hold just a report's `.md` source and rendered PDF
  cluttered with files an outsider has no reason to recognize. Every
  filename-based auto-discovery function (`find_metadata`'s YAML glob,
  `preamble_candidates`'s `.tex` glob, `find_lua_filters`, and `-y`'s bare-name
  `resolve_yaml` lookup) now also searches a `metadata/` subdirectory beside
  the document, via a new shared `accessory_directories()` helper -- nothing
  needs to opt in, and a pipeline with no `metadata/` folder sees no change
  at all. Pandoc's own working directory for a render already follows
  wherever the first discovered metadata file lives (`pandoc_cwd =
  metadata_files[0].parent`, pre-existing, originally there for an explicit
  `-y` pointing at a shared directory elsewhere) -- so once `metadata.yaml`
  moves into `metadata/`, a preamble's raw LaTeX `\input{chemicals}` and a
  `metadata.yaml`'s own relative `bibliography:`/`csl:` keys keep resolving
  for free, as long as `chemicals.tex`/`nulab.bib`/`nu-labreport.csl` move
  into that same `metadata/` folder alongside it.
- **New `resource_path_option()` guards a document's own relative paths
  (e.g. an image) against that same `pandoc_cwd` shift.** Before this
  change, `pandoc_cwd` always happened to equal the document's own
  directory in every pipeline that kept its metadata beside the document --
  so nothing exercised the gap. The moment metadata moves into
  `metadata/`, `pandoc_cwd` moves with it, and a document's own relative
  image path would otherwise silently resolve against `metadata/` instead
  of the document's actual directory. pdfmd now adds `--resource-path
  <document dir>:.` to the Pandoc command whenever `pandoc_cwd` differs
  from the document's own directory -- a no-op, with zero command-line
  change, for every pipeline where the two already coincide.

## v2.3.0 — 2026-09-17

Backup taken before this round: `backups/pdfmd.py.bak-20260917a`.

### Added

- **Every failed PDF-engine attempt now prints a one-line reason, with no
  flag needed** — found debugging a `testref` (SOC203) reference sheet
  whose `\begin{multicols}{2}...\end{multicols}` two-column function index
  failed on every engine (missing `\usepackage{multicol}`, then a second,
  subtler bug: Pandoc's Markdown reader treats a bare `\begin{ENV}...
  \end{ENV}` paragraph as one opaque raw-LaTeX block and stops parsing
  Markdown inside it, so the index's backtick code spans and underscores
  were passed to LaTeX literally instead of becoming `\texttt{}`). Bare
  `pdfmd file.md` gave only `WARN ... {engine} failed; trying {next}...`
  with no hint why — finding the actual cause meant already guessing which
  engine to force via `--engine {name} --verbose` to see the raw LaTeX log.
  New `engine_failure_reason()` pulls the single most useful line out of a
  failed attempt's stderr (a LaTeX fatal error's own `!`-prefixed line if
  there is one, else a `Error`/`pandoc:`-prefixed line, else the last
  non-empty line) and a new shared `report_engine_failure()` prints it on
  EVERY `WARN`, including — new — the final engine's failure, which
  previously printed nothing at all beyond the eventual bare `FAIL <path>`.
  Both the single-file/batch engine loop (`convert_one`) and report/book
  mode's separate inline loop now go through this one function instead of
  each having their own bare `WARN` print.
- **New `--debug` flag** for when the one-line reason above still isn't
  enough (several stacked LaTeX errors, or a Pandoc-level error with no
  leading `!`/`Error` line at all): dumps the failed engine's FULL captured
  stderr inline, at the point of failure, for every engine that fails —
  even one a later engine in the fallback chain goes on to recover from —
  instead of only the final one. Implies `--verbose`. Threaded through
  every `convert_one` call site, including the positional
  `ProcessPoolExecutor.submit` call in parallel batch mode (`-j`), and
  through report/book mode's own inline engine loop via `args.debug`
  directly (that loop was never refactored into `convert_one`).
- **A pointer comment for future editors** (human or AI) was added right
  above `PDFMD_VERSION` in `pdfmd.py` itself, naming this project's
  `CLAUDE.md` and its backup-before-editing / changelog-in-the-same-edit
  requirement explicitly — found worth adding after noticing an editor can
  reach `pdfmd.py` directly (e.g. asked to fix a specific compile failure)
  without ever having opened this directory's `CLAUDE.md` first.

### Verified

- Reran the `testref` reference sheet that surfaced this through the real
  fallback chain (no `--engine` override): `lualatex` still fails for the
  pre-existing, unrelated `mainfontfallback`/lualatex crash documented at
  `PREFERRED_FONT`'s own comment, and the new `WARN` line surfaced ITS
  reason too (previously silent), before `xelatex` picked it up and
  produced a correct PDF.
- A synthetic deliberately-broken `\begin{multicols}` document confirmed:
  (1) no flags — the undefined-environment reason shows on the very first
  `WARN`, and a NEW final-failure `WARN` (with the same reason plus a
  `--verbose`/`--debug` hint) appears right before `FAIL`, where past
  versions printed nothing between the last engine's silent failure and
  `FAIL`; (2) `--debug` with an unrestricted chain — every attempted
  engine's full stderr prints inline as each one fails in turn, not only
  the last.
- A normal, successful compile (a working document, default flags) was
  confirmed unchanged: no new output at all, since `report_engine_failure`
  is only ever reached on a non-zero return code.

## v2.2.0 — 2026-09-17

Backup taken before this round: `~/dev/tex/nulabreport/_superseded/
pdfmd.py.pre-standalonetex.20260917-131249.bak`.

### Fixed

- **`--to latex`/`beamer`/`context` (or `-o file.tex`) produced a bare
  Pandoc-LaTeX fragment, not a document that compiles on its own** — the author hit
  this running `pdfmd -o test.tex` on a lab report: the `.tex` had no
  `\documentclass`/`\begin{document}`/`\end{document}`, no `--standalone`,
  and (since preamble/header-includes discovery was gated on `target_format
  == "pdf"`) none of the project's own `preamble.tex` (its `nulabreport`
  package load, course/instructor front-matter, `\input{chemicals}`) or the
  margin/mainfont/monofont defaults a PDF render of the same source would
  have gotten — none of it compiled. Fixed by giving `latex`/`beamer`/
  `context` targets (new `TEX_STANDALONE_FORMATS`) the same preamble/
  header-includes/margin/monofont/mainfont treatment as the PDF-via-
  LaTeX-engine path, plus `--standalone`, in `convert_one` (single-file and
  batch modes) and the report/book mode's non-PDF branch alike; a new
  `--no-auto standalone` (also settable via `pdfmd-options: no-auto:
  [standalone]`) turns just the `--standalone` addition back off, for a
  `.tex` that's deliberately meant to be `\input`/`\include`d into another
  document rather than compiled on its own. One thing this deliberately
  does NOT reproduce: the PDF path's missing-glyph detect-and-retry between
  `STIX Two Text` and `DejaVu Serif` needs an actual compile to check
  against, which nothing here performs, so the emitted document keeps
  whichever font it tried first; a first attempt at closing that gap with
  Pandoc's own `mainfontfallback` variable was reverted after it reproduced
  PREFERRED_FONT's already-documented crash under lualatex in this
  environment (confirmed with a real `lualatex` compile of the generated
  `.tex` — `luaotfload | resolve : sequence of 3 lookups yielded nothing
  appropriate` immediately followed by a fatal `attempt to index a nil
  value` in `luaotfload-fallback.lua`), so it isn't attempted at all here,
  same as the PDF path's own reasoning for avoiding it. Verified end to end
  on the report that surfaced this: the generated `.tex` now compiles
  cleanly with `lualatex` (two passes, for cross-references) to a PDF whose
  `pdftotext` output is byte-identical to, and whose page count (39) matches,
  a PDF made by running `pdfmd` directly on the same Markdown source.

## v2.1.1 — 2026-09-17

Backup taken before this round: `~/dev/tex/nulabreport/_superseded/
pdfmd.py.pre-enginequiet.20260917-001806.bak`.

### Fixed

- **v2.1.0's `AUTO ENGINE  <path>: chain` line printed unconditionally,
  every run, regardless of `-v`/`--verbose`** — the one auto-discovery
  message in the whole script that bypassed the established
  note()/flush_summary() convention (every other "AUTO ..." line is either
  shown in full under `--verbose` or folded into one `AUTO: KINDS. Use
  --verbose to see in full` summary otherwise). Caught immediately on real
  use (the author, building a report normally with no `-v`). Fixed two ways at
  once: `resolve_engines()` takes a new `verbose: bool = False` parameter
  and only prints when it's true (all four call sites in `main()` now pass
  `args.verbose` through); and the label itself changed from `AUTO ENGINE`
  to plain `ENGINE`, since as of v2.1.0 this restriction can come from
  either a document's own front matter (an explicit per-document request,
  not really "auto") or its linked metadata file (genuinely a default,
  closer to "auto") -- one shared "AUTO" prefix no longer described both
  sources accurately. No silent summary line was added for the
  non-verbose case (unlike the note()-based messages) -- this one is
  either fully shown or fully hidden, since the caller already knows
  whether it asked for a restriction at all.

---

## v2.1.0 — 2026-09-17

Backup taken before this round: `~/dev/tex/nulabreport/_superseded/
pdfmd.py.pre-unknownskey.20260916-235642.bak` (before the DOCUMENT_LATEX_KEYS
change) and `pdfmd.py.pre-metadataengine.20260917-000621.bak` (before the
engine-resolution change) — kept in the `nulabreport` package's own
`_superseded/` since that's the session that prompted both, not this
project's own `backups/`.

### Added

- **`pdf-engine`/`engine` (and `pdfmd-options` generally, for that one key)
  now also falls through to a document's linked `--metadata-file` YAML, not
  only the document's own front matter.** Found while verifying a
  `nulabreport` course's shared `metadata.yaml` (symlinked into every course
  folder) after the author added `pdfmd-options:\n  pdf-engine: tex` to it, expecting
  every report in that course to restrict fallback to the LaTeX family by
  default: `resolve_engines()`/`frontmatter_engine()` only ever inspected the
  source `.md`'s own front matter, so the setting was silently inert — no
  `AUTO ENGINE` line, and the ordinary unrestricted fallback ran regardless.
  Confirmed with `-v`: the same `pdf-engine: tex` line in the report's own
  front matter DID restrict the chain (`lualatex -> xelatex -> pdflatex ->
  latexmk -> tectonic`, no html/typst); the identical line in `metadata.yaml`
  alone did nothing. Fixed by teaching `frontmatter_engine()` a second,
  lower-priority source: after checking the document's own `pdfmd-options`
  and bare top-level `pdf-engine`/`engine`, it now checks each of the
  document's already-resolved `metadata_files` in turn (new
  `metadata_file_yaml()` — a metadata file has no `---`/`...` fence to find
  first, unlike a document's front matter; the whole file already IS the
  mapping). `resolve_engines()` takes a new optional `metadata_files`
  parameter to carry this through; all four call sites in `main()`
  (single-file, batch serial, batch parallel via `ProcessPoolExecutor`, and
  report/book mode) now compute or reorder-to-reuse each file's metadata
  before resolving its engines, instead of after. A document's own front
  matter still wins when both are set — this is a course-wide *default*, not
  an override. Deliberately does **not** extend to `no-auto`: `no-auto`
  decides whether metadata auto-discovery runs at all, so it can't also
  depend on the metadata file that same discovery would find, without a
  circular dependency. Verified end-to-end (not just by reading the code)
  across all three of single-file, `-b` batch, and `-r` report mode, each
  with `-v`, each showing the `AUTO ENGINE` restriction now firing from
  `metadata.yaml` alone with no per-report front matter needed — and a
  sanity check that an explicit CLI `-e` still overrides it, unchanged.
- **`DOCUMENT_LATEX_KEYS` gained `unknown` and `unknowns`** (both map to the
  same `\LabUnknown`) for `nulabreport`'s `titlepage` layout's new optional
  unknown-sample field — see that package's own `docs/CHANGELOG.md` v1.14.0
  (the field itself) and v1.14.2 (the `Unknown:`/`Unknowns:` singular/plural
  label switch, and the `unknowns` alias added here). Verified end-to-end
  through `pdfmd` itself, not a hand-rolled `\renewcommand`: `unknown: 3` and
  `unknowns: "1, 2"` both build and render correctly.

---

## v2.0.0 — 2026-09-16

Baseline entry: versioning and changelog tracking begin here (see above).
Both fixes below were found and fixed in the same session that established
this file, discovered while debugging an unrelated `nulabreport` LaTeX
package issue (see that project's own `docs/CHANGELOG.md` v1.13.3 for the
report-side half of the story) — a short, all-numeric table was rendering
stretched across the full page width for no visible reason, and it took
real effort to figure out the actual cause was in `pdfmd.py`, not the LaTeX
package being built.

### Fixed

- **`TABLE_WIDTH_LUA_FILTER` (the auto-applied Lua filter that assigns
  column widths to a plain pipe table pandoc parsed with no explicit
  widths) fired on EVERY such table, not only ones that risked actually
  overflowing the page.** Intent was always "rescue a table whose unwrapped
  content would run past the margin" (see the filter's own long comment) —
  a short, all-numeric table with no wrapping risk at all got exactly the
  same treatment, forcibly rebalanced and stretched to the full page width,
  fighting any downstream Lua filter (e.g. a house-style package's own
  table macro) that deliberately sizes such a table to its natural content
  width instead. Root-caused by testing the SAME generated `.tex` two ways:
  compiling it directly with `lualatex` gave the correct, natural-width
  table; running the full `pdfmd` pipeline on the same source gave a
  stretched one — isolating the discrepancy to `pdfmd`'s own pandoc
  invocation (specifically, the extra `--lua-filter` it inserts before any
  user-supplied one) rather than the LaTeX side. Fixed by adding a real,
  if approximate, overflow check: estimate the table's total natural width
  from the same per-column longest-cell character count the filter already
  computes for its proportions, and skip rewriting the table entirely
  (leaving its `nil` widths untouched) when that estimate already fits a
  reasonable one-line budget (`CHAR_BUDGET`, ~95 characters, sized for this
  script's typical 12pt/1in-margin default document shape — an estimate,
  not a real width measurement, since a Lua filter runs before Pandoc or
  LaTeX ever measures a real font). Verified three ways: the previously
  -broken short table now renders at its natural width; a deliberately
  wide, genuinely-overflowing table still gets rescued (wraps within the
  page, doesn't overflow) exactly as before; a small generic 2-column table
  with no house-style package involved also now renders compact and
  centred instead of stretched.
- **`--verbose` never showed the actual Pandoc command being run** — only
  pdfmd's own "AUTO ..." decisions (which font/metadata/preamble/lua-filter
  it auto-discovered), never the resulting command line, which `--lua-filter`
  order, or what a discovered file actually resolved to. This is exactly
  the information that would have made the table-width bug above far
  faster to find. Added `log_cmd()`, called under `--verbose` right before
  every `subprocess.run` that invokes Pandoc (or Quarto's CLI is not yet
  covered — see below), printing the full command line via `shlex.quote` so
  a copy-pasted line is directly re-runnable.

### Known gaps, not fixed here

- `log_cmd()` is wired into every Pandoc-invoking `subprocess.run` call
  (single-file, batch, and report/book modes) but NOT into
  `convert_qmd`'s Quarto invocation, which doesn't currently take a
  `verbose` parameter at all. Low priority (`.qmd` is a narrow, separately
  -documented path) but worth doing in the same pass if `convert_qmd` is
  next touched for something else.
- `CHAR_BUDGET`'s ~95-character estimate is a single constant, not aware of
  a document's own `fontsize`/`geometry` front matter. Fine for this
  script's own typical use so far; revisit if a document with an unusual
  page shape trips the same "wrongly rebalanced" or "wrongly left alone"
  symptom in the other direction.

---

# Before 2.0.0 — reconstructed history (NOT reliable)

> **Read this first.** Nothing below was recorded at the time. It was
> rebuilt on 2026-10-05, after the fact, from two incomplete sources, and
> it should be read as an approximate outline, not a record:
>
> - **[chat]** — the author's saved transcripts of a few ChatGPT Codex
>   sessions (28 Jul – 1 Sep). They give real dates and real intent, but
>   cover only some of the edits: other sessions (other ChatGPT chats,
>   claude.ai, Cowork) were never saved, and the author does not remember
>   or could not find whether the script was also edited by other AIs
>   before then. The transcripts carry day and month but no year; 2026 is
>   assumed (it is the only reading consistent with the snapshots).
> - **[snapshot]** — differences between the surviving
>   `~/dev/python-projects/backups/pdfmd.py.bak-*` files (1 Sep, 7 Sep and
>   two on 16 Sep). Their dates are file modification times, and anything
>   that was added and removed (or changed twice) between two snapshots is
>   invisible. Every snapshot entry therefore covers a *window* of days,
>   and the order of its items inside that window is unknown.
> - **[recollection]** — the first script (v0.1.0), which the author found
>   again afterwards; only its code and the rough age of its chat are known.
>
> The version numbers 1.0.0–1.9.0 are invented here to give the outline a
> shape; they never existed in the script, and `PDFMD_VERSION` has only
> ever been 2.0.0 or later. Where an entry says "undated" or "by the
> snapshot of ...", the feature is known to exist by then but when and how
> it was introduced is not known. The script was also not born as
> `pdfmd.py`: it grew out of an earlier `batchmd.py` (a Markdown batch
> converter) whose own history is not known at all (apart from its first version, v0.1.0, at the end of
> this file).
>
> Further, the transcripts mention edits made to individual Markdown
> documents rather than to the script (fixing a `header-includes:`
> preamble, replacing unsupported IPA macros, wiring up a bibliography);
> those are not script changes and are left out.

---

## v1.9.0 — 2026-09-16 (snapshot window: 11:18 → 21:12)

[snapshot] Between `pdfmd.py.bak-20260916-113000` and
`pdfmd.py.bak-20260916-tablewidth-preedit` — the latter is the exact
pre-edit state of v2.0.0.

### Added

- **`-v` / `--verbose`, and a quiet default.** Each "AUTO ..." decision
  (reader, title, margin, mainfont, monofont, lua) used to print its own
  line on every run; now one condensed `AUTO: KIND KIND ...` line per
  document is printed, and `--verbose` restores the full explanations.
  (`AUTO YAML`/`TEX`/`ENGINE`/`MD` still print in full.)
- **`--open`**: open the finished file with `open` (macOS) or `xdg-open`
  (Linux) after a successful single-file or report build; ignored in batch.
- **`--no-auto` grew four kinds** beyond the document-default ones:
  `metadata`/`yaml`, `preamble`/`tex`, `lua` and `files` (all three), so
  pdfmd's file auto-discovery can be switched off too. An explicit
  `-y`/`-H` still wins. The decision is made once, in a new
  `effective_no_auto()`, because discovery runs before `convert_one()`.
- **`pdfmd-options:` becomes the home for pdfmd-only front-matter keys.**
  `pdf-engine:`/`engine:` can now be nested under it; the bare top-level
  spelling keeps working.

### Fixed

- A document whose first line is a Pandoc `% title` block was switched to
  the `gfm` reader, which does not parse it, leaving the `%` lines as
  literal text; it is now treated like a document with YAML front matter.

---

## v1.8.0 — 2026-09-07 → 2026-09-16 (snapshot window)

[snapshot] Between `pdfmd.py.bak-20260907a` (7 Sep, 22:18) and
`pdfmd.py.bak-20260916-113000` (16 Sep, 11:18). The script roughly
doubled in size here (877 → 1,834 lines), and the module docstring grew
from a few usage examples into the long feature description. This is the most
under-resolved stretch of the whole history: it is certainly several
sessions' work squeezed into one entry.

### Added

- **Other output formats and input formats.** `--to FORMAT` (any Pandoc
  writer), `--from FORMAT`, and a recognised extension on `-o`
  (`-o notes.html`) pick a non-PDF target; the PDF engine is then neither
  needed nor checked. Any Pandoc-readable input works when given with its
  real extension. `.qmd` is handed to the `quarto` CLI instead of Pandoc
  (`--check-dependencies` lists it). (Note: in 2026-08 the author had
  decided *against* claiming `-t` for "typst" so as not to collide with
  Pandoc's own `-t`; `-t` was claimed later, here, as Pandoc's `--to`.)
- **Engine families and per-document engines.** `ENGINE_FAMILY` makes the
  fallback chain skip engines that share a TeX implementation with one
  that just failed; `ENGINE_GROUPS` (`tex`, `html`, `typst`) lets `-e` or
  a `pdf-engine:` front-matter key restrict the chain to one paradigm. A
  bare `-e` means the full unrestricted chain and overrides the document.
- **A reader choice for Markdown.** A document with no YAML front matter
  and no linked metadata file is read as `gfm` (content-sized pipe-table
  columns, tolerant of GitHub-style spacing), with `+definition_lists`
  re-enabled when needed and the plain `markdown` reader kept for `@cite`
  documents. A leading bare `# Title` is promoted to real title metadata
  and the headings shifted up a level.
- **`TABLE_WIDTH_LUA_FILTER`**, the auto-applied filter that assigns
  proportional widths to width-less pipe tables so a long cell wraps
  instead of running past the margin. (Its over-eager firing is what
  v2.0.0 fixes.)
- **Typographic defaults on LaTeX engines:** `geometry:margin=1in` when
  the document, a metadata file or a preamble sets no margin (with a check
  against loading `geometry` twice); `JetBrains Mono` as the monofont when
  the document has code and no `monofont:`.
- **`--no-auto [KIND ...]`** and the `pdfmd-options: {no-auto: ...}`
  front-matter block (needs PyYAML) to switch those defaults off.

### Changed

- **Font strategy.** The 1 Sep script already passed `mainfontfallback`
  (and retried with DejaVu Serif on a missing-glyph warning). This stretch
  tried Pandoc's per-glyph fallback and dropped it (it silently does
  nothing under XeLaTeX and crashes LuaLaTeX here); the default is now
  `STIX Two Text` first, retried once with `DejaVu Serif` if glyphs are
  reported missing. `-f`/`mainfont:` still win outright.

### Fixed

- A document given by a relative path with a subdirectory (`sub/a.md`) was
  looked up twice-nested once Pandoc's working directory was changed to
  the document's folder; paths are now resolved to absolute ones.

---

## v1.7.0 — 2026-09-02 → 2026-09-07 (snapshot window)

[snapshot] Between `pdfmd.py.bak-20260902` (identical to `-20260901`) and
`pdfmd.py.bak-20260907a`.

### Added

- **More engines and short names.** `latexmk`, `tectonic`, `pagedjs-cli`
  and `groff` joined the list (13 in all); `-e` accepts the number shown
  by `--check-dependencies` or a short alias (`lua`, `xe`, `pdf`, `mk`,
  `tect`, `weasy`, `wkhtml`, `pagedjs`, `roff`).
- **A document's own `header-includes:` survives an auto-included
  preamble.** Pandoc feeds `-H` files into the same variable, so a
  preamble beside the document used to silently discard the document's own
  block; pdfmd now re-appends it as a last `--include-in-header`, so a
  per-document override works.
- **Front-matter keys passed on to the preamble.** `experiment`, `group`,
  `course`, `section`, `instructor` and `performed` become
  `\renewcommand{\Lab...}{...}` lines after the preambles (for the
  `nulabreport` title page).
- **Auto-applied Lua filters** — only `<stem>.lua` and `nulabreport.lua`
  beside the document or its metadata file, announced as `AUTO LUA`;
  applied last, after `--citeproc`.
- **Bare `pdfmd`** with no argument converts the single `.md` file in the
  current directory (`AUTO MD`), and refuses with a list if there are
  several.

---

## v1.6.0 — 2026-09-01

[chat] Codex session, 17:08. (Present in the 1 Sep snapshot.)

### Added

- **Preamble discovery by the document's name.** For `review.md`:
  `review.yaml`/`review.yml` (layered over `metadata.yaml`) and the TeX
  preambles `preamble.tex`, `latex-preamble.tex`, `preamble-*.tex`,
  `review.tex`, `review_preamble.tex` and `review-preamble.tex`. Several
  safe preambles are all included, generic first and document-specific
  last, and a warning notes that later ones may override earlier ones.
  Complete documents and standalone TikZ files stay rejected.

---

## v1.5.0 — 2026-09-01

[chat] Codex session, 16:38–16:43.

### Added

- **Auto-discovery of a LaTeX preamble** (`preamble.tex`,
  `latex-preamble.tex`) beside the document, passed as
  `--include-in-header`. A file containing `\documentclass`,
  `\begin{document}`, `\end{document}` or `\begin{tikzpicture}` is never
  taken; an explicit `-H` is never duplicated; non-LaTeX engines never
  receive it.
- **Transparent discovery.** Auto-found files are printed as
  `AUTO YAML <path>` and `AUTO TEX <path>`; explicit `-y`/`-H` files are
  not labelled as automatic.

---

## v1.4.0 — 2026-08-30

[chat] Codex session, 15:00.

### Added

- **Wildcard names:** `pdfmd '*scrutiny'` matches Markdown stems with
  `fnmatch` (the `.md` is still implied). More than one match lists the
  candidates and stops instead of guessing. (Quote the pattern, or the
  shell expands it first.)

---

## v1.3.0 — 2026-08-29

[chat] Codex session, 22:10–22:18.

### Added

- **`--check-dependencies`** reports Pandoc and each supported PDF engine.
  Pip packaging was advised to be a separate `pyproject.toml`, with the
  engines checked but never installed by the script (done, much later, in
  3.10.0).
- **An engine fallback chain.** With no `-e`, installed engines are tried
  in order — LuaLaTeX, XeLaTeX, pdfLaTeX, Typst, WeasyPrint, wkhtmltopdf,
  Prince, ConTeXt, pdfroff — and the next one is tried when one fails,
  announced as `WARN  <file>: lualatex failed; trying xelatex...`. An
  explicit `-e` is respected; Beamer (`-p`) is limited to TeX-family
  engines.
- **Automatic `{=latex}` wrapping of `header-includes: |`** for LaTeX
  engines, in Markdown and metadata YAML, in single-file and report mode.
  A `%` comment or preamble command inside a YAML literal block was parsed
  as Markdown (`%` → `\%`), so the preamble broke with "Missing
  \begin{document}"; the source file itself is never modified (a
  temporary copy is compiled).

### Fixed

- A bug in the exclusion options of report mode (unspecified in the
  transcript).

---

## v1.2.1 — 2026-08-26

[chat] Codex session, 18:06–18:09.

### Fixed

- **`--citeproc` was not enabled automatically for bare citations.** The
  detector only looked for `[@key]`; it now also recognises `@key` and
  `-@key`, while skipping e-mail addresses. (The first attempt to apply
  the fix failed on a write-permission restriction in that session and
  was redone on request.)

---

## v1.2.0 — undated, between 2026-07-28 and 2026-08-29

[snapshot, inferred] Not described by any saved transcript; present in the
1 Sep snapshot, and implied by chat remarks (an "existing `--report`
exclusion-option bug" on 29 Aug; "the script already automatically
searches for yaml files" on 1 Sep).

### Added

- **Report/book mode** (`-r`/`--report`/`--book`, `--recursive`): all
  Markdown files in a folder combined into one PDF, ordered by a
  `chapter:` front-matter field; `-i`/`--exclude` and
  `--exclude-unnumbered` to leave files out.
- **Metadata YAML:** `-y`/`--metadata-file` (a stack, `all`, or a bare `-y`
  to disable discovery), automatic discovery of `metadata.yaml` and a
  document-named YAML, `yamlorder:` and `autoinclude: false` inside the
  YAML files, and `defaults.yaml` always skipped.
- **Mainfont handling:** fall back to DejaVu Serif when a build reports a
  missing glyph, unless the user or the document chose a font.

---

## v1.1.1 — 2026-08-08

[chat] Codex session, 18:10.

### Fixed

- A regression from the previous change: adding a `-cwd` spelling of the
  destination flag left `args.destination_cwd` undefined, so
  `pdfmd name -p` crashed with an `AttributeError`. `-d`, `-cwd`, `--cwd`
  and `--destination-cwd` now all set the same destination.

---

## v1.1.0 — 2026-07-31

[chat] Codex session, 21:11.

### Added

- **`-d` / `--destination-cwd`**: keep the document's filename but write
  the PDF into the current working directory instead of beside the source
  (for previewing a file given by full path before saving it for good).

---

## v1.0.1 — 2026-07-28

[chat] Codex session, 16:18–16:19 (outcome not confirmed in the
transcript, but the 1 Sep snapshot normalises names to NFC).

### Fixed

- A Cyrillic name was not found because the file name used a decomposed
  character (e.g. `и` + combining breve) while the generated candidate
  used the composed `й`; matching now normalises both sides.

---

## v1.0.0 — 2026-07-28

[chat] Codex session, 16:01–16:06. The first version called `pdfmd`:
`batchmd.py` extended and renamed.

### Added

- **Name resolution** from a bare, Latin-spelled name: the exact name
  first, then transliterated Cyrillic variants, then each with the
  `Пробный ` prefix used for slide decks (`pdfmd Name` finds `Name.md`,
  its Cyrillic spellings, or `Пробный <Name>.md`), and the PDF takes the
  name of the file that was found. Zero or several matches is an error.
- **Presentation mode** `-p` (Beamer via XeLaTeX, `--slide-level`),
  **batch mode** `-b` over a directory with `-j` parallel jobs and `-o`
  output directory, and passthrough of `-e` (engine; LuaLaTeX by default),
  `-f` (font), `-V` (Pandoc variables, e.g. geometry) and any other
  Pandoc option.

---

## v0.1.0 — about early July 2026 (exact date unknown)

[recollection] The very first code, called `batchmd`. The number is invented here
like the others: it never existed in the script. It was generated by Gemini; the
last message of that chat is about three months before this entry was written, and
the author's own memory that it began as a one-line `pandoc file.md -o file.pdf`
was wrong.

### Added

- A script of about twenty lines: `pypandoc` converts every `*.md` in one fixed
  folder (`~/Downloads/files`) to a PDF beside it, with the Tectonic engine,
  `geometry:margin=1.5cm` and `mainfont=DejaVu Serif`. It prints
  `Converting NAME.md to NAME.pdf...` for each file, reports a failed file and
  goes on, and ends with `Batch conversion completed!`. Margin and font were
  already two of the defaults pdfmd still has.
