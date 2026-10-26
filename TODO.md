# TODO

What is planned and not done. History lives in `CHANGELOG.md`; this file is only the
open work. Rules: one line per item, finished items are deleted in the commit that
finishes them (the changelog keeps the record), nothing here is a promise.

The number in brackets, `[3dc]`, is the entry in the maintainer's working notes that
holds the agreed details (design, decisions, measured facts). Items marked **decide**
wait for an answer before any code.

## Next: small and concrete

- [ ] After a failed TeX run, name the causes that reach pdfmd only as "Fatal error occurred" (unwritable cache, corrupt luaotfload database) with a one-page probe [3dd]
- [ ] `pdfmd -`: build Markdown read from standard input as an ordinary build [3cd]
- [ ] Indent div (`::: {indent=false}`) in docx and odt: a paragraph style, not a note [3ca]

## Decide first

- [ ] **decide** `--no-rewrite`: numbered sibling instead of overwriting; name template, parts, `-o`, watch [3ce]
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
- [ ] `table-keep` limits: grid tables, height-based rule, `.csv` tables, Pandoc floor [3cf]
- [ ] Quarto islands and streams, the trust model, `pdfmd --install quarto`, then the tiers [3bs, 3bt, 3bn]
- [ ] Older audit leftovers, each to verify first: raw `<img>` in LaTeX builds, `\texttt` wrapping, unreachable remote SVG, a dialect-change warning, `--doctor` hint at `--deep` [Audit]

## Before 4.0

- [ ] Pandoc + TeX tests on Windows and macOS (Linux only today) [3db]
- [ ] **Documentation programme**: a reference generated from the code's own registries, an example for every feature built and checked in CI, a new README, `docs/recipes.md` retired into it; hosted from the repo and bundled for `pdfmd --doc` [3dg]
- [ ] `pdfmd.py` split into the `pdfmd_cli` namespace, one event log [3bh]
- [ ] 4.0

## Investigate first, no commitment

- [ ] reveal.js route, pptx slides, Quarto's slide formats [3bu, 3bv]
- [ ] Features that may leave pdfmd for their own repositories (rebuilding a docx source from a PDF, `html2qmd`) [3dg, 3bn]

## In other repositories

- [ ] inkmd: a quote right after a list is read as a paragraph; fix upstream, re-vendor [3ci]
- [ ] nulabreport: grid tables cannot be kept whole (`labtabular`) [3cf]
