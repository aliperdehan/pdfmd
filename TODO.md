# TODO

What is planned and not done. History lives in `CHANGELOG.md`; this file is only the
open work. Rules: one line per item, finished items are deleted in the commit that
finishes them (the changelog keeps the record), nothing here is a promise.

The number in brackets, `[3dc]`, is the entry in the maintainer's working notes that
holds the agreed details (design, decisions, measured facts). Items marked **decide**
wait for an answer before any code.

## Decide first

- [ ] **decide** `table-keep` in pdfmd itself, for any document, not only through a filter [3cf]
- [ ] **decide** images in `--view` through the kitty graphics protocol (Ghostty, kitty, WezTerm), also display math; the pager conflict is open [3dm]
- [ ] **decide** a Pandoc memory cap: a `pdfmd-options` key and `--setup` row passing `+RTS -M<n> -RTS`; default off or on, and the value [3en]
- [ ] **later** PlantUML as a diagram language next to mermaid, d2 and dot: not now (author, 2026-11-02: no second Java for it); pick up if asked [3en]
- [ ] Build record: LaTeX package versions and the TeX Live year, .qmd, direct and report builds [3dn]

## Features, agreed

- [ ] Logo: a README header (a `<picture>` with absolute raw URLs, light and dark wordmark) and the social preview uploaded in the repository settings, before the next push [3ew]
- [ ] BUG, silent wrong numbers: parts built together that are not next to each other (`report#20+40`) read what the parts between them define as defined above both (calc names); fix with a slot per gap or hidden gap blocks, first a WARN [3eg]
- [ ] `\md{...}`: nulabreport's macros taking `\md{}`; native tier; text-level pre-passes (table-ascii, includes, embed blocks) inside the macro, unchecked [3dc]
- [ ] Citation key aliases, resolved before citeproc [3bo]
- [ ] Mixed-format parts: docx, tex, odt, html parts inside a `parts: auto` build [3cl]
- [ ] Settings layers: a per-install layer that wins over the user config, `--json` for `--show-config` and `--doctor` [3bh]
- [ ] Word `keep`; markup (centre, highlight, landscape) in OpenDocument; markup in the native tier [3bh, 3ay]
- [ ] CSS: headings in Word and Typst; MathJax for the non-STIX fonts (tall brackets) [3am, 3ao]
- [ ] Calculator: `.qmd` spellings and the `all` mode, native tier, constants file included from the body, check mode, significant-figure tracking [3bw, 3cu]
- [ ] Calculator typeset styling: Greek names (upright/italic), styling one occurrence of a piece in a line (the in-name `V_[x]s`), spaces inside the `{upright:..}` marker [3cw]
- [ ] `--to ansi`: stacked math (levels b and c) [3ci]
- [ ] `table-keep` limits: grid tables, height-based rule, the Pandoc floor for caption attributes [3cf]
- [ ] Quarto islands and streams, the trust model, `pdfmd --install quarto`, then the tiers [3bs, 3bt, 3bn]
- [ ] Check that `lof` / `lot` (lists of figures and tables) work through pdfmd; then a recipe [3en, 3dg]
- [ ] Pandoc-gap audit: the user guide's "does not" sentences and closed won't-fix requests, each marked done / worth doing / refused; before the Eisvogel line [3dk]
- [ ] Eisvogel LaTeX template: a bundled pinned copy with its licence, `--install eisvogel` for the latest, a `template` key; LaTeX only [3dk]
- [ ] Discover more project files without a flag: `template.<ext>` or `<name>.<ext>` per output format, `templates/`, CSL, CSS; templates are an auto kind and an attach-source kind (off by default) [3dl]
- [ ] `column-word-ceil` (on by default; a column is never wider than its longest cell by more than `column-ceil-margin`, 25% of the line) [3dl]
- [ ] `table-keep` by height: keep a short table whole when it is under `table-keep-height` of a page (default 25%), plus orphan control; mechanics unspiked [3dl]
- [ ] Fetch templates (pandoc-templates.org index, `owner/repo`, URL) and CSL styles by name or link, cached; generalises the Eisvogel line [3dl]
- [ ] Install source: pdfmd records how it was installed; `pdfmd --upgrade`; `--version` says when a newer release exists [3dk]
- [ ] Older audit leftovers, each to verify first: raw `<img>` in LaTeX builds, `\texttt` wrapping, unreachable remote SVG, a dialect-change warning, `--doctor` hint at `--deep` [Audit]

## Tables line, one feature line (3.31.0, full suite) [3dj]

- [ ] Widths outside LaTeX: Typst, HTML, Word, ODT get Pandoc's equal thirds; give "no opinion" tables back to the engine; absolute widths (`3cm`) of the attribute line are drawn in LaTeX only (HTML has percentages) [3fa]
- [ ] Cell tags: vertical alignment and heights in Typst, Word and ODT; an exact row height (tabularray's `ht` is a minimum); `j` (justify) [3fa]
- [ ] Cell tags: a table rebuilt as `longtblr` is raw LaTeX to later filters (`table-keep`, `labtabular`, Beamer untested); the native tier and grid tables read no tags [3fa]
- [ ] nulabreport: its table writer ignores `row_span` (a covered cell is missing, the row shifts) and forces a spanned cell to centre; emit `\multirow` (loaded) and keep the cell's alignment, in all three writers, plus a smoke-test case (nulabreport repository) [3fa]
- [ ] Chatter ladder: `--chatter`, `-q`, `--mute ID`, `--log`, `--summary`; one `emit`; per document and in `--setup`
- [ ] Revise the thin features of this line (table pre-pass kinds, line breaks, table captions, `<c>` cells, Org extras) against unusual input users will try, while the documentation programme writes them up [3el, 3dg]
- [ ] Table pre-pass: dash look-alikes, `+` and `=` separators, `table-colons`, `table-repair` modes, "not a table" warning, `--fix-tables`
- [ ] Character budget from paper, margins and font size, not 95
- [ ] CSV `widths`: repair a wrong count, `*` for a free column, never drop data
- [ ] Row legibility for long-cell tables: `table-style` (rules, zebra, spacing)
- [ ] Reader: Pandoc's Markdown for a plain file that uses grid or simple tables
- [ ] Width modes beyond auto/keep/force: combinations, more per-table spellings (per-column widths are in the attribute line, 3.32.33) [3dl]
- [ ] A true width estimator for math, raw HTML and typography instead of character counts; then delete the raw-TeX kludge (`column-count-raw-tex`) [3dl]
- [ ] Cache the balanced widths per table by content hash [3dl]

## Kits, carried inside 3.31 (no minor of its own); a report without a `metadata/` folder; started [3du]

- [ ] nulabreport side (its maintenance is done): its `.kit`, course codes as mode aliases, starters without `metadata/` (which stays supported), a course-level `.pdfmd/` in `220/` and `LR9-10`, the manual updated; real builds of copies of 220/LR6 and LR9-10; smoke test
- [ ] Kits, later: `settings:` and a kit `options:` list; a Pandoc-template kit after the 3dk spike; a first-use trust prompt for fetched kits; `requires:` for a clear missing-package error; Typst, HTML, Word parts (kits 0.2); `--kit new|check|pack` [3du, 3dg, 3et]
- [ ] nulabreport at three levels (bare `.sty`, a pandoc defaults file plus the Lua filter mapping the front-matter keys, a pdfmd kit); no custom `.latex`; spike first (does `-H` replace a filter's `header-includes`?), then bare-pandoc and bare-`.sty` lanes in its smoke test [3dw, 3dk, 3du]

## Pictures and crop, carried inside 3.31 [3dv]

- [ ] The post-build step: crop, layout and pictures read `pdfmd-options` at every level (front matter, metadata files, folder layers, config, `--setup` rows, command line) and work on the real output PDF; replaces 3.31.21's re-run of pdfmd in a scratch folder; `default-output` takes a list
- [ ] Layouts `long` (pages stacked into one tall page, any engine; a seamless tall page via Typst `height: auto`, LaTeX to 16383 pt) and `grid` (fewest columns*width + rows*height), with gap and background, with and without `--crop`
- [ ] Tools: a fallback chain for the ink box, PNG, SVG (gs, mutool, pdftocairo, pdftoppm, sips, pypdfium2), a tool-path setting, `--doctor` lines; `--install` and `--doctor` bring them from pip, brew, winget (Ghostscript on Windows: `gswin64c`, the installer)
- [ ] A page-numbers setting (`pdfmd-options: {page-numbers: off}`, a flag and a `--setup` row), written per engine without replacing the document's `header-includes` (LaTeX `\pagestyle{empty}`, Typst `numbering: none`, the built-in renderer, Word); `--crop` of a Markdown source then builds without them
- [ ] `--image-background`; webp (Pillow, pypdfium2 or ImageMagick); `--to pdf,docx` for formats that are not pictures (a loop of runs)
- [ ] docx and odt with `--crop`: a lean page of the cropped size, or a document holding the cropped vector or PNG (`lib/pdfmd_office/fragments.py` has the pieces)
- [ ] The equation popup (Colophon `Pop/`, once eqpop) calls `pdfmd --crop` when it can; its own AppKit crop stays as the fallback

## Chemical structures, carried inside 3.31 [smiles] [3ec]

- [ ] `smiles` blocks (fenced and `::: smiles`; SMILES or molfile, `file=`, one molecule per line, `name=`): RDKit pictures and chemfig (mol2chemfig, compiled once and cached), `engine=auto`, `cache: {smiles}` (off by default), settings under `pdfmd-options.smiles`; then inline `smiles`, `engine=indigo` [3ec]

## Distribution inside this repository, carried inside 3.31 [3ed]

- [ ] Obsidian plugin (plain JS, `manifest.json` at the root, bare-version release from publish.yml, `pdfmd --install obsidian`); VS Code extension published from publish.yml if a token exists [3ed]

## Obsidian flavour, 3.32.x patches (no minor bump yet) [3ee]

- [ ] Working `[[wikilinks]]`: `[[#Heading]]` as a link to the heading, `[[Note]]` as a cross-reference between the parts of one build or a link to the note's built file; today they are only written as their text (3.32.26) [3ee]
- [ ] Gaps of `%%comments%%` (3.32.20): report/book chapters, split-document parts, the section and heading scanners, indented code blocks, a `flavour` set only in a metadata file for the citation scan [3ee]
- [ ] The rest of Obsidian's syntax: note embeds (`![[note#Heading]]`, `#^block`), links between notes, tags, block ids, properties, foldable and custom callouts, extra task statuses [3ee]
- [ ] Every part of a flavour adjustable: presets are tables a user overrides piece by piece or defines their own ("frankenstein") [3ex]
- [ ] Other flavours as `flavour` values, one at a time after Obsidian: MyST, MkDocs/pymdown, CriticMarkup, Logseq/Roam, Quarto extras, MultiMarkdown, Djot [3eo]
- [ ] British and American spellings of every key, flag and value (colour/color, centre/center, grey/gray, flavour/flavor...): scan, one alias table, a completeness test; docs and help print British, commands British first (`--colour`, `centre`), American accepted as naturally [3ep]
- [ ] Spans `.caps`, `.wavy`, `.dotted`... in every writer, then the shorthand (`++x++`, `!!x!!`, `??x??`) as opt-in `markup` kinds; CriticMarkup and abbreviations later [3eq]
- [ ] **decide** A control character in a source (U+0000-U+001F): one note naming the line and skip the engines that cannot read it, instead of three failed engines and Typst after 1.5 min; look at the Typst route's inline-math warnings [3es]
- [ ] Community plugins: a vault report from `.obsidian/community-plugins.json`, adapters for plain-text plugin formats, rendering through Obsidian for the rest (never headless: the CLI needs the running app); unknown stays as code with one note; **decide** the other tiers [3er]

## Other tools' command lines

Answer the keys of the other `pdfmd`, `mdpdf` and `md2pdf` tools under their own command names, check their behaviour, take
what pdfmd lacks. Plain `pdfmd` keeps its own meanings (`-p` is slides, `-s`, `-h`...); a PDF read as Markdown is
batchocr's, so what is listed for it lands in batchocr. Never delegate to a copy of another tool. The quick ones first; the rest
is low priority. [3di]

- [ ] batchocr (PDF to Markdown): `--pages 1,3,5-8` (PyPI `pdfmd`'s `-p`), standard input `-` and URL inputs (Rust `pdfmd`), `--extract-images DIR` as a spelling of `--export-images`, a folder as input (npm `pdfmd -i DIR -o DIR`)
- [ ] `md2pdf` leftovers: `pdfmd --install math` installs `pymd2pdf`, whose own `md2pdf` script then replaces pdfmd's in the same folder (restore it after the install)
- [ ] `--security basic|default|strict` as one switch over the HTML, remote-file and script switches (markdown-convert); with a wkhtmltopdf / untrusted-input warning in the docs and `--doctor` [3di, 3en]
- [ ] Long keys of the other personas (approved) (`--stylesheet`, `--border`, `--orientation`, `--format`, `--as-html`...) accepted by plain `pdfmd` when no downstream program (Pandoc, Calibre, batchocr) has the key; short and clashing keys (`-h`, `-s`, `-c`, `-e`, `--css`, `--header`) stay persona-only; a test compares the table against `pandoc --help` [3di]
- [ ] Take over, each checked first: Jinja context from the front matter for `.md.j2` (jmaupetit), `.page-break` and a custom page-break marker (`md-to-pdf`, mdPDFinator `-n`), `--document-title` and `--body-class` for the HTML route, emoji shortcodes (`:thumbsup:`), theme files and `--dump-theme` (Go `mdpdf`), `[TOC]` and `!!!` admonitions (markdown-convert)

## Before 4.0

- [ ] Pandoc + TeX tests on Windows and macOS (Linux only today) [3db]
- [ ] Windows test session on a second machine: fork + pull requests, the Mac session merges and bumps the version [3dp]
- [ ] Tool paths per document and on the command line: the `tesseract-path`, `soffice-path` ... keys also as `pdfmd-options` and flags, so one document can pin another version of a tool [3dt]
- [ ] Windows guide (16 sections): the Windows session adds it to the repo as a docs file; wire it into `pdfmd --doc` with the documentation programme [3dg, 3dp]
- [ ] Tag a batchocr release (the remote ends at v1.2.4, the checkout is 1.2.6) and move `BATCHOCR_TAG`: `--install batchocr` gives a version that cannot read `.txt` [3di]
- [ ] **Documentation programme**: a reference generated from the code's own registries, an example for every feature built and checked in CI, a new README, `docs/recipes.md` retired into it; hosted from the repo (GitHub Pages, indexable) and bundled for `pdfmd --doc`; a layered README tested by a beginner on a clean machine; agent surfaces (task table, `--help` as JSON, `llms.txt` hosted); an audit of ambiguous names (one meaning per word, a test for collisions and aliases); feature pages carry the version added, fixed and last tested [3dg]
- [ ] `pdfmd.py` split into the `pdfmd_cli` namespace, one event log [3bh]
- [ ] Lean install: a core distribution plus extras (`pdfmd-cli` stays the full default); optional packages survive their absence with one message; a CI leg for the core only [3dx]
- [ ] `--install full|core|cortex` also fetch the default fonts (`fonts:core`: STIX Two, JetBrains Mono, Noto Serif, symbols; about 8 MB), sizes table updated [3ei]
- [ ] Bare `--install` prints the table of every kind (size, source, target, removal) instead of usage; bare `diagram` lists, `diagram:d2|dot` installs [3ei]
- [ ] Docs: a table of every install kind (pip or download, size, `--uninstall`, `--check-dependencies`), decided together with the lean install [3ei, 3dg, 3dx]
- [ ] 4.0

## Investigate first, no commitment

- [ ] pdfmd-gui: an Overleaf-like project view; one local web UI plus thin native wrappers, a client of the CLI, never obligatory; its foundation (emit, `--json`, the split, the generated reference) ships in 3.x before 4.0 [3do]
- [ ] pdfmd-gui window shell, open: native wrapper vs an optional chromium window (`--install chromium`, a `--setup` row to toggle); no Node needed [3do]
- [ ] Colophon web UI and JSON core (`pdfmd --serve`, `--api`, settings as a JSON schema checked by each client, panels around the native editor, a live HTML view with render modes); the design is answered (CodeMirror 6, per-client validators, panels, `platforms`); a UI prototype from fixtures comes first, then S1-S6; Tauri postponed [3do]
- [ ] Colophon: a Format popup in the Save As panel, so the export is noticed (an Export panel stays proposed) [3do]
- [ ] Colophon: one History panel, two lanes (git for edits: log, diff, restore; `.hst` and the build record for builds); a setting that offers `git init`, also into a NEW folder, never silently; a proper diff view [3do]
- [ ] Source jump: a click in the render opens the source line (SyncTeX, Typst's `typst-ide` jump, our own block map for other engines); later [3do]
- [ ] Colophon: check that a login launch opens no untitled window (only a real login shows it); a non-activating equation popup (showing it may lift every editor window) [3do]
- [ ] A `.calc` file kind: `::: {.calc file=NAME.calc}` imports it as it is and it works with the document like any calc block; a syntax map in Colophon, carried by `--merge` and `--check` [3ez]
- [ ] More input kinds in Colophon: HTML documents with a render, and Pandoc's plain-text readers (rst, org, textile ...) by extension, `--from` or a YAML key [3do]
- [ ] reveal.js route, pptx slides, Quarto's slide formats [3bu, 3bv]
- [ ] docx output and raw LaTeX multicols: nulabreport 1.29.1 writes tables between a raw `\begin{multicols}` and `\end{multicols}` as plain `tabular`; check what the docx (office) path does with those raw fences and the tables inside, since it parses raw LaTeX too
- [ ] Features that may leave pdfmd for their own repositories (rebuilding a docx source from a PDF, `html2qmd`) [3dg, 3bn]

## In other repositories

- [ ] inkmd: a quote right after a list is read as a paragraph; fix upstream, re-vendor [3ci]
- [ ] nulabreport: grid tables cannot be kept whole (`labtabular`) [3cf]
- [ ] nulabreport: `smiles: true` inside its `cache: {aux, plots}` in the three metadata files, +0.0.1, once the chemfig cache exists (approved) [3ec]
