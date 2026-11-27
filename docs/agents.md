# pdfmd for an agent

(For agents developing pdfmd itself, the process is AGENTS.md at the root of the repository.)

A short guide for a program or an AI assistant that runs `pdfmd`. The same text is in the README, the recipes and
`pdfmd --help all`; this is the part you need first. `pdfmd --doc` lists the documents that came with your version.

For a build, `-qq` (`--chatter=result`) shows its final OK line. `-qqq` (`--chatter=off`) keeps errors on stderr
and preserves the exit status. Use `-q` to show warnings as well.
When reading a PDF, all three flags pass one `-q` to batchocr, which shows only errors and warnings.
Use `--log FILE` to append the full diagnostics to a file while keeping the console quiet.
Use `--summary` to count unmuted warnings, notes and errors after the last build result, including in a batch.
`--fix-tables` preserves code fences inside lists and raw HTML div blocks under GFM.
`--mute ID[,ID]` accepts named warnings under `--strict`.
Use `pdfmd-options.flavour-overrides` to adjust a named flavour. For example, `{comments: false}` keeps `%%` comments in the text.
Use `[text]{.caps}`, `[text]{.wavy}` and `[text]{.dotted}` for uppercase prose and styled underlines. The `spans` markup kind enables them.

## The commands that matter

```sh
pdfmd report.md                     # Markdown to report.pdf beside it; the closing line names the engine
pdfmd report.md -o out.pdf          # a name; the suffix picks the format (.docx .odt .epub .html .tex .azw3 ...)
pdfmd report.md --to docx           # the format by name
pdfmd -b a.md notes/                # separate builds from files and folders; each folder supplies *.md
pdfmd a.md b.md                     # several paths imply -b; -r still merges them
pdfmd *                            # deduplicate inputs and skip non-inputs and verified outputs from build records
pdfmd report.md -e typst            # a PDF engine by name (or a list: -e typst,lualatex)
pdfmd report.md --kit apa7         # build with a kit (a house style); `pdfmd --kits apa7` describes it, builds nothing
pdfmd --install diagram:resvg        # SVG to PNG tool, GitHub SHA-256 checked, in pdfmd’s tools folder
pdfmd --doctor                      # tools, shared SVG image/diagram converter chain, found converters and fixes
pdfmd --doctor --deep               # also builds a small page with every engine: "installed" is not "works"
pdfmd --doctor --json               # versioned checks and tool discovery
pdfmd --show-config --json          # configured values and origins
pdfmd --merge report.md             # assemble discovered parts, skipping priority: never unless named or --all
pdfmd report.md --check             # what would go wrong, without building (links, images, labels, citations ...)
pdfmd report.md --verbose           # the exact Pandoc command and every automatic decision, with its reason
pdfmd report.md --stop-at tex       # stop at the .tex Pandoc made, to read what LaTeX will see
pdfmd --install full                # also core, core:typst: Pandoc, Typst and fonts:core (about 58 MB)
pdfmd --install core:tex            # also cortex: Pandoc, Tectonic and fonts:core (about 53 to 65 MB)
pdfmd --restore report.pdf          # a PDF that carries its own source: write the folder back (never over a file)
pdfmd --check-source report.pdf     # does this PDF carry its source? (reads the attachment list only)
```

Batch selection uses resolved paths and fails if nothing buildable remains. Explicit files can use Pandoc input
formats; special single-file routes such as PDF-to-Markdown, Quarto and non-Pandoc ebooks are excluded. Name those alone.
Use `-o DIR` for batch output; a filename is refused, as are single-document options such as `--watch` and `--section`.
With two paths, a skipped PDF beside a selected input adds `to name the output, use -o NAME.pdf`.

Typst uses LaTeX’s line pitch by default. `pdfmd-options: {typst-line-spacing: pandoc}` (also `--setup`) keeps
Pandoc’s own Typst spacing without pdfmd’s line rules.

LaTeX and Typst fit tall figures to the page body and warn when they shrink the images. Captions keep their size.
Use `pdfmd-options: {figure-fit: off}` for the document or `{fit=off}` on a figure image to keep its original size.
`--check` can use a temporary PDF to report `figure-too-tall` and say how the build handles each oversized figure.

With `--no-citeproc`, native Typst omits an uncited bibliography and its heading unless `nocite` or
`full-bibliography: true` requests uncited entries. Cited lists keep Typst's automatic title; `reference-section-title`
names the citeproc list.

- The Obsidian and pdfmd flavours hide `%%comments%%` in documents, chapters and parts. Section selection and citation
  detection ignore the comments. Use `--show-comments` to display them in the output.

Use `--no-page-numbers` to suppress a writer's running page numbers for one build, or set
`pdfmd-options: {page-numbers: off}` in the document. Cropping Markdown already suppresses them.
Use `--page-numbers` when a cropped result should keep them.

## Reading what pdfmd says

- Every line begins with a word: `OK`, `FAIL`, `WARN`, `NOTE`, `NATIVE`, `FOUND`, `DEFAULTS`, `AUTO`. A document built is
  `OK    report.md > report.pdf  (lualatex)`; the engine that made it is in the brackets, and engines that failed
  first are named after it (`(typst; lualatex failed)`).
- The exit code is `0` when every file was built and `1` when any failed (the others in a batch are still built). With
  `--strict` a build that printed a warning (an engine that failed and was replaced, a missing glyph, a Pandoc
  `[WARNING]`) counts as failed too: the output is kept, the exit code is `1`. `--check` exits `1` on an error.
- Control character repairs for Pandoc produce one warning per source, with original line numbers and code points.
  The repair leaves the source file untouched and counts towards `--strict`.
- When an engine fails, the next one is tried only where `engine-fallback` lets it. The default, `auto`, stops a
  build whose PDF already exists at an error in the document (exit `1`, the existing PDF left as it was; the closing line says
  `engine-fallback auto stopped the build`) and goes on only past an engine that cannot run here; a new PDF gets the whole
  chain. `--engine-fallback on` tries the next engine after an engine failure. Confirmed Pandoc input errors stop
  the build in every mode.
- `FOUND` lists the files pdfmd picked up beside the document (a metadata file, a preamble, a Lua filter, the folder
  settings); `DEFAULTS` what it applied because nothing said otherwise. If the output is not what the source alone
  predicts, read these first, or run `--verbose`.
- Do not parse the text for a version or a path. `pdfmd --version` prints the version; `--full-paths` makes every path
  absolute.

## Running without a person

- `PDFMD_NO_PROMPT=1` stops every question and every offer (an install, the setup hint). An explicitly requested
  `--install calibre` takes the default package manager if available, otherwise the SHA-256-checked GitHub download.
  On macOS, a downloaded Calibre disk image that stays attached produces a WARN with the manual detach command.
- An empty or unset `PDFMD_CONFIG` uses the usual user config.
  `PDFMD_CONFIG=file.yaml` names another, and `PDFMD_CONFIG=off` or `none` skips the user file. `sys.prefix/etc/pdfmd/config.yaml`
  is the per-install config and wins over the user file. A `.pdfmd/` folder in the document's folder or above it still applies (it is a
  project's own setting; `--verbose` lists it as `AUTO SETTINGS`, the closing `FOUND` line as `.pdfmd`).
  Kits: the config's `kits:` entries and the `kits/` folder beside the config are off too; a `kits/` folder in the
  document's folder or above it still applies (`--no-auto kit` turns that off).
- The output goes beside the document, or where `-o` says; pdfmd also keeps a cache (`~/.cache/pdfmd`) and a data folder
  for what `--install` fetches (`~/.local/share/pdfmd`). `pdfmd --clear-cache` empties the cache and is always safe; `pdfmd --cache-info` shows its parts, `pdfmd --clear-cache stale` clears what belongs to documents that are gone.
  `--no-backup` forces backups of replaced files off for a run.
- A Lua filter, a preamble or a metadata file beside the document is used without being named (a new or edited Lua
  filter is said in a `NOTE`; `--strict` does not run one that is new). `--no-auto` turns the discovery off, one kind
  of it with `--no-auto lua` (or `preamble`, `yaml`, `margin` ...).

Inline code in LaTeX builds can break after path and URL punctuation only to avoid overflowing the margin,
without a printed hyphen. Headings keep unsplit code for PDF bookmarks. `--no-code-wrap`, `pdfmd-options: {code-wrap: false}` or `--no-auto codewrap` turns off
wrapping for both inline code and code blocks; `{wrap=false}` applies to one block.

Pagecite is off by default: `--pagecite auto` or `pdfmd-options: {pagecite: auto}`
lets `[p. 5]` after a citation refer to that paragraph’s last source. Modes are
`off`, `auto`, `style` (a real citation), `page` (page words in the CSL brackets),
`drop`; `bare`/`full` mean `page`/`style`. `pagecite-terms` defaults to `[p., pp.]`;
set it under `pdfmd-options` or in `--setup` (as for `pagecite`). It needs the
`pagecite` markup kind; `--no-auto pagecite` disables it. Escaped markers, code
and links stay literal. The native tier leaves markers as written and lists
`pagecite` in its markup warning.

`pdfmd --excerpts ACTION` manages local source records: `list`, `show ID`,
`add`, `edit ID`, `remove ID`, `sources`, `where ID`, `export`, `detach`, `check`,
`reanchor KEY`, `renumber`, `rekey OLD NEW` and `import FILE.pdf --key KEY`. It consumes the
rest of the command line; each action accepts `--json` and `--in PATH` (document
or folder). Exit codes: 0 success, 1 problems/file failure, 2 usage. JSON failures
answer `{error}`. `list` prints a compact table of record fields with long values
shortened to fit the terminal (80 columns in a pipe). Use `list --json` for the
complete records. `add --key glass --page 41 --text "Invented evidence."` prints
an id and canonical forms `[@x:ID]` and `[@KEY#ID]`; `add --remark "Check this inference."` needs no source.
`remove --detach` rewrites citations before deletion. `remove --force` leaves
markers in place. `list --problems` filters to records with warnings or errors.
`sources add KEY FILE --pages '[[2,"41"]]'` records a source;
`sources match [DIR]` proposes matches (`--apply` only for unambiguous exact
evidence). PDF reading needs optional pypdf. `export [-o FILE]` is a private
Markdown review sheet containing passages and notes.

Register the PDF before calling `--excerpts import FILE.pdf --key KEY`.
Saved text markup and area annotations become excerpt records. On macOS,
import also reads Skim's archived notes attribute. If the archive is missing
or unreadable, import lists each plain-text note with its heading and text as
“not imported: no position”. Use `--dry-run --json` to preview the records
without writing them or reserving their IDs. JSON returns an array of records,
or an object with `records` and `not-imported` arrays when plain-text notes
are listed. A report containing only those notes exits 0.

`--check` verifies excerpt markers, source keys, locators and quotations
without opening source PDFs. `--excerpts check --json` also checks PDF hashes
and bounds and reports unused records. Quotation and overlap checks default to
3 and 6 words respectively. Set `excerpt-quote-min-words` and
`excerpt-overlap-words` under `pdfmd-options` or in `--setup`. An overlap
threshold of 0 turns overlap checking off. `reanchor` uses Poppler
`pdftotext`. Ambiguous anchors and duplicate identifiers need review.

For local API access, start `--serve FOLDER` and send the printed token as
`Authorization: Bearer TOKEN`. `GET /api/excerpts` returns `record`,
`locations` and `problems`. `GET /api/excerpts/check` returns `problems`.
Use `POST /api/excerpts` to add record fields and `PUT /api/excerpts?id=ID`
to update them. To delete a cited record, send `DELETE /api/excerpts?id=ID`
with `{"detach":true}` or `{"force":true}`. Register a source with
`POST /api/excerpts/sources` and a JSON object with `key`, `file` and
optional `pages`. The file must be inside the project.
`GET /api/source?key=KEY` returns the registered primary PDF, with single byte
ranges supported over HTTP. From the project folder, `--api METHOD PATH [JSON]`
uses the same handlers and writes a successful source response as PDF bytes.
The top-level `api` field in a JSON answer is the API version.

`pdfmd-options.excerpts` names the record file relative to the file setting it;
`off` disables discovery. Otherwise it is the nearest `excerpts.json` beside the
document, in `metadata/`, then parent/folder layers. Records keep unknown fields,
use monotonically increasing ids and are written atomically under a lock.
`where` reads either `:` or `#` in both forms and reports
canonical markers. Set `pdfmd-options.excerpt-prefix` in any settings layer or
through `--setup` (default `x`). Use letters, digits, hyphens or underscores.
The cross-reference prefixes `fig`, `tbl`, `eq`, `sec` and `lst` are reserved.
Builds in the pdfmd and Obsidian flavours resolve markers against the record
file before citation processing. Real bibliography keys take precedence.
Set `pdfmd-options.excerpt-page-terms` (default `[p., pp.]`) to change generated
locators. `excerpt-repeat: page` uses a literal locator after the same source
in a paragraph when pagecite selects its page form. The default is `full`.
Use `--no-auto excerpts` to disable resolution. Run
`pdfmd --excerpts detach --all draft.md` or specify IDs before the Markdown
files to write plain citations. Source exports and default attachments do this
automatically. An explicit PDF bundle keeps comments, excerpt markers and the
record, which travels in a separate attachment. Use `--strip-comments` with
the bundle to strip comments and excerpts, including any PDFs in the sweep
that carry excerpt records. In a plain attachment, `--keep-comments-in excerpts`
or `--attach-source private` keeps the markers and record. An explicit strip
setting for excerpts overrides the private shortcut. Build text and metadata
use citation fields alone.

Print a document's YAML front matter with `pdfmd-options.properties.show`.
Use `true` for ordinary properties, `all` to include internal fields, or a
list for specific keys. Slides read this setting from their own front matter.

## When a build fails

In the Obsidian flavour, wikilinks can target local headings, other parts of the build or a note's same-format output.
A missing note produces a warning and leaves the display text.
Use `[[#^id]]` or `[[Note#^id]]` to link to a paragraph ending in `^id`. Inline tags stay visible and Obsidian's YAML
properties remain available as metadata.
Obsidian callouts with `-` or `+` after the type fold in HTML and print open. Extra task statuses keep the
status character. `--no-markup` leaves the callout and task syntax as written.

Use `pdfmd-options: {dialect-detect: deep}` for GFM-style blocks that follow prose in documents with front matter,
or for a leading Hugo-style TOML metadata block. The default `basic` warns about TOML and keeps it in the body.

With `.hst` history enabled, a change of the automatic Pandoc reader prints one WARN naming the old and new readers
and the reason when known. Successful full builds record the reader; first builds and legacy entries are silent.
An explicit `--from` or `pdfmd-options: {reader: ...}` suppresses this warning.
Use `--from md` to read Markdown from a file with any extension.
A .tex fragment can be compiled with a discovered project preamble or
with Pandoc's own `-H FILE`, which pdfmd passes on.

Use `--crop` or `pdfmd-options: {crop: true}` to crop the PDF of a build
to its ink. The default is off. `--no-crop` overrides a saved setting.
Use `default-output: [pdf, png]` in `pdfmd-options` to save both from
one build. Set `crop-pad`, `crop-ignore-bottom`, `crop-page`, `image-dpi`,
`image-quality` and `page-folder` in `pdfmd-options` or through `--setup`.
The matching command-line flags override these defaults.
Use `--doctor` to see which optional PDF crop and picture converters are available.
For an existing PDF, use `--mute crop-empty-page,crop-already-pdf` to hide notes about blank pages and PDFs left as they are.
Use `--to webp` for compressed pictures with alpha, or
`--image-background '#ffffff'` for an opaque background.
Use `--crop --to docx` or `--crop --to odt` to place cropped PDF pages in an
Office document. Each page is a picture at its cropped size. Use
`--no-crop` when the document needs editable text.

A trailing numbered list of web sources and matching markers such as
`[1]` or `[1, 3]` become Pandoc citations in the pdfmd and Obsidian flavours.
Use `--to md` to export citable source with `references:` front matter. Set
`pdfmd-options: {numbered-references: off}` to preserve the input syntax.
`numbered-references: on` enables this in the pandoc, gfm and commonmark flavours.
`--check` reports `numbered-references-off` when the full shape matches
and the setting is off.
With a citeproc bibliography, numbered web sources retain their own list,
labels and links.

Set `pdfmd-options.lua-filter-before-citeproc` to run a trusted Lua filter before citations are resolved. The list is empty by default and follows the same layers and relative paths as `lua-filter`.

Set `pdfmd-options: {citation-aliases: {short: existing-key}}` to have
citeproc resolve `[@short]` to an existing bibliography entry. A collision
keeps the real key, and a missing target leaves the citation unresolved.
Both warn.

1. `pdfmd --doctor` says which engines exist. A missing one is not an error of the document.
2. `pdfmd report.md --verbose` shows the command. Run it by hand to see the engine's own message.
3. A LaTeX error names the file and the line in the source (`FAIL ... line 12`); `--debug` keeps the log.
4. `pdfmd report.md --check` finds a missing image, a broken link and an undefined reference without an engine.
5. With no Pandoc at all pdfmd still writes a plain PDF with its built-in renderer (`NATIVE`) and says what it left out.

## Choosing, in one line each

| to get | use |
|---|---|
| the best PDF of a Markdown file | `pdfmd file.md` (Pandoc and a LaTeX or Typst engine) |
| a Word, OpenDocument or e-book file | `-o file.docx`, `.odt`, `.epub`, `.azw3` (Calibre writes the Kindle formats) |
| the Markdown of a PDF, a Word file or an e-book | `pdfmd file.pdf`, `file.docx`, `book.epub` |
| a self-contained, restorable PDF | `--attach-source` (off unless asked, or `attach-source: true` in `pdfmd-options:`) puts the source into the PDF. `--restore` writes it back. `--bundle` and `--attach-source private` carry local excerpt passages and notes by default. |
| what is wrong with this machine | `pdfmd --doctor --deep` |

For a template's running head, `pdfmd-options: {office: {replace: {KICKER: "$course$ $term$"}}}` reads
metadata from the built Word/OpenDocument file, including office profile changes. `$$` is a dollar;
missing/empty values disappear and spaces collapse with ends trimmed. Literal values without dollars keep
their spacing; metadata text is XML-escaped.

SVG images and D2/SVG-only dot diagrams share the converter chain: rsvg-convert, Inkscape, cairosvg, svglib,
LibreOffice, Typst, resvg. Typst makes vector PDF for LaTeX or PNG for Word using pdfmd’s fonts; resvg is the PNG
fallback. The first working converter wins. `pdfmd-options: {image-dpi: 192}`, `--image-dpi N` and `--setup` set
raster SVG resolution (default 192; exported pages still default to 300). `--no-auto svg` and
`--no-auto diagrams` disable the corresponding conversion.

With the default LaTeX, Typst or HTML template, give a `title:` if `author:` or `date:` should print; pdfmd notes their omission without one. Word, ODT and EPUB print the byline without a title.

To cap Pandoc's heap, set `pdfmd-options: {pandoc-memory: 512m}` (or `2g`; whole k/m/g units). Unset or null means off. On heap overflow, raise or unset `pandoc-memory`; PDF engines have separate memory use.

Use `--strip-comments` or `pdfmd-options: {strip-comments: true}` to remove HTML comments from the build itself as well as assembled/attached source. Code examples and pdfmd marker comments survive. This also removes comments before `--show-comments` draws them.

Document `indent:` (front matter or pdfmd-options) accepts lengths such as 0.5in, 3em and 1cm in LaTeX, Typst, Word and HTML. True keeps each writer's standard indent (LaTeX the class's own, Typst 1.5em, Word 0.25in, HTML none); false/unset keeps defaults. Invalid lengths stop the build; indent divs still override a stretch.

`pdfmd-options.bibliography-line-spacing` (also in `--setup`) defaults to `off`, keeping each writer's spacing,
including native Word spacing and HTML's `data-line-spacing`. Use `style` to apply CSL line spacing to the reference list,
or a positive factor (`1` for single spacing) to override it in LaTeX, Typst, Word and HTML.
`pdfmd-options.csl` takes a path or `{file: apa.csl, spacing: style}`. For the file, `--csl` wins over the alias,
then root `csl:`. For spacing, `bibliography-line-spacing` wins over `csl.spacing`. Conflicting values produce a WARN.

The default LaTeX table-width count estimates the line capacity from the paper, margins and type size.
Typst, HTML, Word and ODT use default sizing for a pipe table with equal separators.
`pdfmd-options: {column-widths: keep}` preserves the widths Pandoc read.
`pdfmd-options: {table-chars: 95}` sets the fallback when those inputs cannot be resolved. A table caption
can carry `{table-chars=120}` (recent Pandoc), and a CSV div can carry `table-chars=120`.
For LaTeX tables with wrapping cells, opt in to more space between rows with
`pdfmd-options: {table-style: spaced, table-row-spacing: 1.4}`.
Table width estimation: `pdfmd-options: {column-estimate: measure}` opts in to measured cell and unbreakable word widths
for LaTeX and Typst PDF builds with their selected engine, including the word breaks in inline code. `--setup` offers the key,
and a table caption can carry `{column-estimate=measure}` (recent Pandoc). Exports use count with a NOTE.
Measurement failures use count with a WARN that names the cause. See the reference for caching and character limits.
