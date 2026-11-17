# pdfmd for an agent

(For agents developing pdfmd itself, the process is AGENTS.md at the root of the repository.)

A short guide for a program or an AI assistant that runs `pdfmd`. The same text is in the README, the recipes and
`pdfmd --help all`; this is the part you need first. `pdfmd --doc` lists the documents that came with your version.

## The commands that matter

```sh
pdfmd report.md                     # Markdown to report.pdf beside it; the closing line names the engine
pdfmd report.md -o out.pdf          # a name; the suffix picks the format (.docx .odt .epub .html .tex .azw3 ...)
pdfmd report.md --to docx           # the format by name
pdfmd -b a.md notes/                # separate builds from files and folders; each folder supplies *.md
pdfmd a.md b.md                     # several paths imply -b; -r still merges them
pdfmd *                            # skip non-inputs (including PDFs and pictures) in one NOTE; deduplicate inputs
pdfmd report.md -e typst            # a PDF engine by name (or a list: -e typst,lualatex)
pdfmd report.md --kit apa7         # build with a kit (a house style); `pdfmd --kits apa7` describes it, builds nothing
pdfmd --install diagram:resvg        # SVG to PNG tool, GitHub SHA-256 checked, in pdfmd’s tools folder
pdfmd --doctor                      # tools, shared SVG image/diagram converter chain, found converters and fixes
pdfmd --doctor --deep               # also builds a small page with every engine: "installed" is not "works"
pdfmd report.md --check             # what would go wrong, without building (links, images, labels, citations ...)
pdfmd report.md --verbose           # the exact Pandoc command and every automatic decision, with its reason
pdfmd report.md --stop-at tex       # stop at the .tex Pandoc made, to read what LaTeX will see
pdfmd --install full                # also core, core:typst: Pandoc 35 MB and Typst 15 MB download
pdfmd --install core:tex            # also cortex: Pandoc 35 MB and Tectonic 10 to 22 MB download
pdfmd --restore report.pdf          # a PDF that carries its own source: write the folder back (never over a file)
pdfmd --check-source report.pdf     # does this PDF carry its source? (reads the attachment list only)
```

Batch selection uses resolved paths and fails if nothing buildable remains. Explicit files can use Pandoc input
formats; special single-file routes such as PDF-to-Markdown, Quarto and non-Pandoc ebooks are excluded. Name those alone.
Use `-o DIR` for batch output; a filename is refused, as are single-document options such as `--watch` and `--section`.
With two paths, a skipped PDF beside a selected input adds `to name the output, use -o NAME.pdf`.

Typst uses LaTeX’s line pitch by default. `pdfmd-options: {typst-line-spacing: pandoc}` (also `--setup`) keeps
Pandoc’s own Typst spacing without pdfmd’s line rules.

With `--no-citeproc`, native Typst omits an uncited bibliography and its heading unless `nocite` or
`full-bibliography: true` requests uncited entries. Cited lists keep Typst's automatic title; `reference-section-title`
names the citeproc list.

## Reading what pdfmd says

- Every line begins with a word: `OK`, `FAIL`, `WARN`, `NOTE`, `NATIVE`, `FOUND`, `DEFAULTS`, `AUTO`. A document built is
  `OK    report.md > report.pdf  (lualatex)`; the engine that made it is in the brackets, and engines that failed
  first are named after it (`(typst; lualatex failed)`).
- The exit code is `0` when every file was built and `1` when any failed (the others in a batch are still built). With
  `--strict` a build that printed a warning (an engine that failed and was replaced, a missing glyph, a Pandoc
  `[WARNING]`) counts as failed too: the output is kept, the exit code is `1`. `--check` exits `1` on an error.
- When an engine fails, the next one is tried only where `engine-fallback` lets it. The default, `auto`, stops a
  build whose PDF already exists at an error in the document (exit `1`, the existing PDF left as it was; the closing line says
  `engine-fallback auto stopped the build`) and goes on only past an engine that cannot run here; a new PDF gets the whole
  chain. `--engine-fallback on` is the old behaviour, `missing` and `off` are stricter.
- `FOUND` lists the files pdfmd picked up beside the document (a metadata file, a preamble, a Lua filter, the folder
  settings); `DEFAULTS` what it applied because nothing said otherwise. If the output is not what the source alone
  predicts, read these first, or run `--verbose`.
- Do not parse the text for a version or a path. `pdfmd --version` prints the version; `--full-paths` makes every path
  absolute.

## Running without a person

- `PDFMD_NO_PROMPT=1` stops every question and every offer (an install, the setup hint). An explicitly requested
  `--install calibre` takes the default package manager if available, otherwise the SHA-256-checked GitHub download.
- `PDFMD_CONFIG=` (empty) ignores the user's config file, so a run does not depend on this machine's settings;
  `PDFMD_CONFIG=file.yaml` names another. A `.pdfmd/` folder in the document's folder or above it still applies (it is a
  project's own setting; `--verbose` lists it as `AUTO SETTINGS`, the closing `FOUND` line as `.pdfmd`).
  Kits: the config's `kits:` entries and the `kits/` folder beside the config are off too; a `kits/` folder in the
  document's folder or above it still applies (`--no-auto kit` turns that off).
- The output goes beside the document, or where `-o` says; pdfmd also keeps a cache (`~/.cache/pdfmd`) and a data folder
  for what `--install` fetches (`~/.local/share/pdfmd`). `pdfmd --clear-cache` empties the cache and is always safe; `pdfmd --cache-info` shows its parts, `pdfmd --clear-cache stale` clears what belongs to documents that are gone.
  `--no-backup` forces backups of replaced files off for a run.
- A Lua filter, a preamble or a metadata file beside the document is used without being named (a new or edited Lua
  filter is said in a `NOTE`; `--strict` does not run one that is new). `--no-auto` turns the discovery off, one kind
  of it with `--no-auto lua` (or `preamble`, `yaml`, `margin` ...).

## When a build fails

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
| a self-contained, restorable PDF | `--attach-source` (off unless asked, or `attach-source: true` in `pdfmd-options:`): the source goes into the PDF; `--restore` writes it back |
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
