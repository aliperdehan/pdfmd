# pdfmd for an agent

A short guide for a program or an AI assistant that runs `pdfmd`. The same text is in the README, the recipes and
`pdfmd --help all`; this is the part you need first. `pdfmd --doc` lists the documents that came with your version.

## The ten commands that matter

```sh
pdfmd report.md                     # Markdown to report.pdf beside it; the closing line names the engine
pdfmd report.md -o out.pdf          # a name; the suffix picks the format (.docx .odt .epub .html .tex .azw3 ...)
pdfmd report.md --to docx           # the format by name
pdfmd report.md -e typst            # a PDF engine by name (or a list: -e typst,lualatex)
pdfmd --doctor                      # what is installed and what is missing, with the command that fixes each
pdfmd --doctor --deep               # also builds a small page with every engine: "installed" is not "works"
pdfmd report.md --check             # what would go wrong, without building (links, images, labels, citations ...)
pdfmd report.md --verbose           # the exact Pandoc command and every automatic decision, with its reason
pdfmd report.md --stop-at tex       # stop at the .tex Pandoc made, to read what LaTeX will see
pdfmd --install full                # Pandoc and Typst into pdfmd's own folder, no admin rights
pdfmd --restore report.pdf          # a PDF that carries its own source: write the folder back (never over a file)
pdfmd --check-source report.pdf     # does this PDF carry its source? (reads the attachment list only)
```

## Reading what pdfmd says

- Every line begins with a word: `OK`, `FAIL`, `WARN`, `NOTE`, `NATIVE`, `FOUND`, `DEFAULTS`, `AUTO`. A document built is
  `OK    report.md > report.pdf  (lualatex)`; the engine that made it is in the brackets, and engines that failed
  first are named after it (`(typst; lualatex failed)`).
- The exit code is `0` when every file was built and `1` when any failed (the others in a batch are still built). With
  `--strict` a build that printed a warning (an engine that failed and was replaced, a missing glyph, a Pandoc
  `[WARNING]`) counts as failed too: the output is kept, the exit code is `1`. `--check` exits `1` on an error.
- `FOUND` lists the files pdfmd picked up beside the document (a metadata file, a preamble, a Lua filter, the folder
  settings); `DEFAULTS` what it applied because nothing said otherwise. If the output is not what the source alone
  predicts, read these first, or run `--verbose`.
- Do not parse the text for a version or a path. `pdfmd --version` prints the version; `--full-paths` makes every path
  absolute.

## Running without a person

- `PDFMD_NO_PROMPT=1` stops every question and every offer (an install, the setup hint).
- `PDFMD_CONFIG=` (empty) ignores the user's config file, so a run does not depend on this machine's settings;
  `PDFMD_CONFIG=file.yaml` names another.
- The output goes beside the document, or where `-o` says; pdfmd also keeps a cache (`~/.cache/pdfmd`) and a data folder
  for what `--install` fetches (`~/.local/share/pdfmd`). `pdfmd --clear-cache` empties the cache and is always safe.
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
| a self-contained, restorable PDF | the default: the source is attached; `--restore` writes it back |
| what is wrong with this machine | `pdfmd --doctor --deep` |
