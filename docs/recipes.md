# pdfmd recipes

Short answers to "how do I...", each with the commands and the README section that explains them.
Every command works from the folder that holds the file; `pdfmd --doctor` shows what is installed.

## A paper in several scripts

Kazakh, Arabic, Chinese, Greek and emoji in one document need no `header-includes`: pdfmd reads your
installed fonts and sets each run in a font that has it.

```sh
pdfmd paper                         # builds paper.pdf; -v says which font each script got
pdfmd --check-fonts paper.md        # what would be used, and what no installed font can draw
pdfmd --install fonts:cjk-sc,arabic # fetch a missing font (no admin rights); fonts:core, fonts:all
pdfmd --install emoji               # colour emoji pictures, where no system font has them
```

Choose how a missing character is handled in the front matter, the config file or on the command
line: `pdfmd-options: {fallback: word}` (default), `char`, `document`, `box`, `error`, or
`--fallback box` to see every gap. Set `lang: ja` (or `zh`, `ko`) so Han characters get the right
flavour. See [Other scripts](../README.md#other-scripts).

## Find a document by a name in another script

```sh
pdfmd glyukoza                      # finds Глюкоза.md (Cyrillic is always understood)
pdfmd --translit greek,hangul tyche # finds Τύχη.md
PDFMD_TRANSLIT=all pdfmd mingyun    # finds 命運.md (--install translit for Chinese and the rest)
pdfmd 'notes#tyche'                 # a section of notes.md, by its heading
```

To make it permanent put `translit: [greek, hangul]` in `~/.config/pdfmd/config.yaml`
(`pdfmd --init-config` writes a commented one).

## Turn a scanned PDF into Markdown

```sh
pdfmd --install batchocr            # the reader, then offers Tesseract and Poppler for your system
pdfmd --install ocr:rus,kaz         # OCR languages into pdfmd's own folder (list: pdfmd --install ocr)
pdfmd scan.pdf --lang rus+eng       # -> scan.md, with <!-- Page N --> markers
pdfmd scan.pdf --ocr tesseract --export-images
```

A PDF that pdfmd itself made with `--attach-source` is restored to its original files instead of
read back through OCR. See [PDF to Markdown](../README.md#pdf-to-markdown).

## Send a PDF that carries its source

```sh
pdfmd report --attach-source        # the Markdown goes into the PDF as an attachment
pdfmd report --bundle               # ... and the data files and images it uses
pdfmd --restore report.pdf          # on the other side: report.restored/ with everything
```

## A house style for a whole folder

Put these beside your documents and every one of them picks them up (add `-v` to see which):

```text
metadata.yaml   # fonts, margins, bibliography, CSL (in the folder or a metadata/ folder)
preamble.tex    # LaTeX packages and macros
report.lua      # a Pandoc Lua filter named after the document (<name>.lua)
```

Anything a document or the command line sets wins over them. See
[What it does automatically](../README.md#what-it-does-automatically) and *Project files*.

## A book or a report from several files

```sh
pdfmd chapters/ -r                  # every .md in the folder, in order, as one PDF
pdfmd chapters/ -r -i appendix      # leave one out
pdfmd report --list-parts           # parts mode: what can be built alone
pdfmd report#results                # just one section or part
pdfmd report --assemble-only        # report.assembled.md: the parts joined, to inspect
```

## Slides, HTML, Word, Typst

```sh
pdfmd slides -p                     # Beamer; each heading starts a slide
pdfmd lecture -o lecture.html --self-contained
pdfmd lecture -o lecture.docx
pdfmd lecture --to typst -o lecture.typ
```

## Keep a build fast while writing

```sh
pdfmd lecture -w                    # rebuild on every save
pdfmd lecture --cache               # reuse LaTeX's cross-reference files between builds
pdfmd lecture --cache-location document   # keep that cache beside the document
```

## Something looks wrong

```sh
pdfmd --doctor                      # tools, fonts, OCR, config and cache, and the fix for each gap
pdfmd lecture -v                    # every automatic decision and the exact Pandoc command
pdfmd lecture --no-auto             # switch every default off: close to plain pandoc
pdfmd --clear-cache                 # start over
```

## Tab completion

```sh
pdfmd --completion zsh > ~/.zfunc/_pdfmd     # bash and fish too; see the README
```
