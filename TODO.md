# TODO

What is planned and not done. History lives in `CHANGELOG.md`; this file is only the
open work. Rules: one line per item, finished items are deleted in the commit that
finishes them (the changelog keeps the record), nothing here is a promise.

The number in brackets, `[3dc]`, is the entry in the maintainer's working notes that
holds the agreed details (design, decisions, measured facts). Items marked **decide**
wait for an answer before any code.

## Decide first

- [ ] **decide** the bare-pipe trigger for plain `pdfmd` (stdin cannot be probed reliably) [3cd]
- [ ] **decide** `table-keep` in pdfmd itself, for any document, not only through a filter [3cf]

## Features, agreed

- [ ] `\md{...}`: Markdown (citations, emphasis, math, cross-references) inside raw LaTeX; a pdfmd Lua pass plus an identity `.sty` [3dc]
- [ ] Citation key aliases, resolved before citeproc [3bo]
- [ ] Mixed-format parts: docx, tex, odt, html parts inside a `parts: auto` build [3cl]
- [ ] Settings layers: folder layers carried in attach/bundle/embed (needs `ATTACH_FORMAT` 3), a per-install layer that wins over the user config, `--json` for `--show-config` and `--doctor` [3bh]
- [ ] Word `keep`; markup (centre, highlight, landscape) in OpenDocument; markup in the native tier [3bh, 3ay]
- [ ] CSS: headings in Word and Typst; MathJax for the non-STIX fonts (tall brackets) [3am, 3ao]
- [ ] Calculator: `.qmd` spellings and the `all` mode, native tier, typeset output, constants file included from the body, check mode, significant-figure tracking [3bw, 3cu, 3cw]
- [ ] `--to ansi`: stacked math (levels b and c) [3ci]
- [ ] `table-keep` limits: grid tables, height-based rule, the Pandoc floor for caption attributes [3cf]
- [ ] Quarto islands and streams, the trust model, `pdfmd --install quarto`, then the tiers [3bs, 3bt, 3bn]
- [ ] Older audit leftovers, each to verify first: raw `<img>` in LaTeX builds, `\texttt` wrapping, unreachable remote SVG, a dialect-change warning, `--doctor` hint at `--deep` [Audit]

## Other tools' command lines

Answer the keys of the other `pdfmd`, `mdpdf` and `md2pdf` tools under their own command names, check their behaviour, take
what pdfmd lacks. Plain `pdfmd` keeps its own meanings (`-p` is slides, `-s`, `-h`...); a PDF read as Markdown is
batchocr's, so what is listed for it lands in batchocr. Never delegate to a copy of another tool. The quick ones first; the rest
is low priority. [3di]

- [ ] batchocr (PDF to Markdown): `--pages 1,3,5-8` (PyPI `pdfmd`'s `-p`), standard input `-` and URL inputs (Rust `pdfmd`), `--extract-images DIR` as a spelling of `--export-images`, a folder as input (npm `pdfmd -i DIR -o DIR`)
- [ ] `md2pdf` leftovers: `pdfmd --install math` installs `pymd2pdf`, whose own `md2pdf` script then replaces pdfmd's in the same folder (restore it after the install)
- [ ] `--security basic|default|strict` as one switch over the HTML, remote-file and script switches (markdown-convert)
- [ ] **decide** long keys of the other personas (`--stylesheet`, `--border`, `--orientation`, `--format`, `--as-html`...) accepted by plain `pdfmd` when no downstream program (Pandoc, Calibre, batchocr) has the key; short and clashing keys (`-h`, `-s`, `-c`, `-e`, `--css`, `--header`) stay persona-only; a test compares the table against `pandoc --help` [3di]
- [ ] Take over, each checked first: Jinja context from the front matter for `.md.j2` (jmaupetit), `.page-break` and a custom page-break marker (`md-to-pdf`, mdPDFinator `-n`), `--document-title` and `--body-class` for the HTML route, emoji shortcodes (`:thumbsup:`), theme files and `--dump-theme` (Go `mdpdf`), `[TOC]` and `!!!` admonitions (markdown-convert)

## Before 4.0

- [ ] Pandoc + TeX tests on Windows and macOS (Linux only today) [3db]
- [ ] Tag a batchocr release (the remote ends at v1.2.4, the checkout is 1.2.6) and move `BATCHOCR_TAG`: `--install batchocr` gives a version that cannot read `.txt` [3di]
- [ ] **Documentation programme**: a reference generated from the code's own registries, an example for every feature built and checked in CI, a new README, `docs/recipes.md` retired into it; hosted from the repo and bundled for `pdfmd --doc`; every feature page says the version it appeared in, the versions of its fixes and the latest version it was tested on, with a re-test pass against rot, an entry with its tests required of every new feature, a page per version, and the pages rendered by pdfmd itself; every confusion point found while writing gets a fix or an accepted spelling and a test, on every route and fallback (the paper bug of 3.30.42 was found only by trying other engines) [3dg]
- [ ] `pdfmd.py` split into the `pdfmd_cli` namespace, one event log [3bh]
- [ ] 4.0

## Investigate first, no commitment

- [ ] reveal.js route, pptx slides, Quarto's slide formats [3bu, 3bv]
- [ ] Features that may leave pdfmd for their own repositories (rebuilding a docx source from a PDF, `html2qmd`) [3dg, 3bn]

## In other repositories

- [ ] inkmd: a quote right after a list is read as a paragraph; fix upstream, re-vendor [3ci]
- [ ] nulabreport: grid tables cannot be kept whole (`labtabular`) [3cf]
