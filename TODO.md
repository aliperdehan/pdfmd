# TODO

What is planned and not done. History lives in `CHANGELOG.md`; this file is only the
open work. Rules: one line per item, finished items are deleted in the commit that
finishes them (the changelog keeps the record), nothing here is a promise.

The number in brackets, `[3dc]`, is the entry in the maintainer's working notes that
holds the agreed details (design, decisions, measured facts). Items marked **decide**
wait for an answer before any code.

## The queue, paused after the 3.33.191 release (2026-11-12): resume in this order

- [ ] 5b. After wave 5: excerpts (source tracking: `[@key#N]` markers, `excerpts.json`, pagecite), pdfmd first, then Colophon's Source pane; spec approved [3fq 3fr 3fs D79 D80 Q74]
- [ ] 5c. Then the Obsidian flavour and its community plugins (the sections below), before Colophon: plugin support may be wanted before committing fully to it [3ee 3er D85]
- [ ] 6. Colophon by hand (`--smoke-web`, Cmd-Q with an unsaved tab, `gui.yml` on main), the review's list below in its order, then the GUI decisions and build [D59 D60 D81]
- [ ] Colophon on Windows: finish the trial shell of PR #38 on a Windows machine with a stronger model; fix the trailers of its last two commits (Beam 1.0) before landing [D119]

## Decide first

- [ ] **decide** the list: text shorthands such as `+/-` -> ±, beside the `--`/`---` dashes; opt-in, never inside code or maths [D44 N144]
- [ ] **later** PlantUML as a diagram language next to mermaid, d2 and dot: not now (author, 2026-11-02: no second Java for it); pick up if asked [3en]
- [ ] Build record: LaTeX package versions and the TeX Live year, .qmd, direct and report builds [3dn]

## Features, agreed

- [ ] Multi-path builds (3.33.140): replace the guesses (non-inputs, earlier outputs, same-output clashes) with a record of what pdfmd wrote, with the build record [3fi D33 3dn D84]
- [ ] Images and display math in `--view` through the kitty graphics protocol, after the queue: first a spike of Unicode placeholders in Ghostty (they survive the pager), else no pager when images are drawn [3dm D84]
- [ ] `\md{...}`: nulabreport's macros taking `\md{}`; native tier; text-level pre-passes (table-ascii, includes, embed blocks) inside the macro, unchecked [3dc]
- [ ] Mixed-format parts: docx, tex, odt, html parts inside a `parts: auto` build [3cl]
- [ ] CSS: MathJax for the non-STIX fonts (tall brackets) [3am, 3ao]
- [ ] Hiding, properly: definitions inside a `hide` block keep working (TeX macros and other uses, as calc lines do), Quarto's `.hidden` macros handled, and possibly `hide` and `hidden` unified again [D98]
- [ ] Calculator: `.qmd` spellings and the `all` mode, native tier, constants file included from the body, check mode, significant-figure tracking [3bw, 3cu]
- [ ] Calculator typeset styling: Greek names (upright/italic) and styling one occurrence of a piece in a line (the in-name `V_[x]s`) [3cw]
- [ ] `--to ansi`: stacked math (levels b and c) [3ci]
- [ ] `table-keep` limits: grid tables, height-based rule, the Pandoc floor for caption attributes [3cf]
- [ ] Quarto islands and streams, the trust model, `pdfmd --install quarto`, then the tiers [3bs, 3bt, 3bn]
- [ ] Agent-friendly pdfmd, low priority (when there is spare time): stale PDF after a failed build, `--explain CODE`, `--help agent`, a `--json` result shared with `--api` and `--doctor --json`, `--profile agent` (no guessing, no fallback, per-code `--strict`, tiny output), `--fix`, raw TeX and front matter under `--security`, a tool schema or MCP front-end last; exit code 3 for "degraded" is the author's call [3ff, 3fk]
- [ ] Pandoc-gap audit: the user guide's "does not" sentences and closed won't-fix requests, each marked done / worth doing / refused; before the Eisvogel line [3dk]
- [ ] Eisvogel LaTeX template: a bundled pinned copy with its licence, `--install eisvogel` for the latest, a `template` key; LaTeX only [3dk]
- [ ] Discover more project files without a flag: `template.<ext>` or `<name>.<ext>` per output format, `templates/`, CSL, CSS; templates are an auto kind and an attach-source kind (off by default) [3dl]
- [ ] `table-keep` by height: keep a short table whole when it is under `table-keep-height` of a page (default 25%), plus orphan control; mechanics unspiked [3dl]
- [ ] Fetch templates (pandoc-templates.org index, `owner/repo`, URL) and CSL styles by name or link, cached; generalises the Eisvogel line [3dl]
- [ ] Install source: pdfmd records how it was installed; `pdfmd --upgrade`; `--version` says when a newer release exists [3dk]
- [ ] Term-paper gaps: --check codes attr-stray, emphasis-empty, repeated heading text, heading-only section/part, uncited keys (info), opt-in en-GB spelling; the "parts also sits beside" WARN for files without front matter ("not merged"); LaTeX errors name the part and line; engine-independent errors stop the fallback chain; a --restore help line [N123]

## Tables line, one feature line (3.31.0, full suite) [3dj]

- [ ] Widths outside LaTeX: Typst, HTML, Word, ODT get Pandoc's equal thirds; give "no opinion" tables back to the engine; absolute widths (`3cm`) of the attribute line are drawn in LaTeX only (HTML has percentages) [3fa]
- [ ] Cell tags: vertical alignment and heights in Typst, Word and ODT; an exact row height (tabularray's `ht` is a minimum); `j` (justify) [3fa]
- [ ] Cell tags: a table rebuilt as `longtblr` is raw LaTeX to later filters (`table-keep`, `labtabular`, Beamer untested); the native tier and grid tables read no tags [3fa]
- [ ] Revise the thin features of this line (line breaks, table captions, `<c>` cells, Org extras) against unusual input users will try, while the documentation programme writes them up [3el, 3dg]
- [ ] Character budget from paper, margins and font size, not 95
- [ ] Row legibility for long-cell tables: `table-style` (rules, zebra, spacing)
- [ ] Width modes beyond auto/keep/force: combinations, more per-table spellings (per-column widths are in the attribute line, 3.32.33) [3dl]
- [ ] Measured column widths beyond LaTeX and Typst (`column-estimate: measure`, 3.33.332-333): Word/ODT through LibreOffice, then measure as the default (4.0 at the earliest) and the raw-TeX kludge (`column-count-raw-tex`) retired [3dl 3ge]

## Kits, carried inside 3.31 (no minor of its own); a report without a `metadata/` folder; started [3du]

- [ ] Kits, later: `settings:` and a kit `options:` list; a Pandoc-template kit after the 3dk spike; a first-use trust prompt for fetched kits; `requires:` for a clear missing-package error; Typst, HTML, Word parts (kits 0.2); `--kit new|check|pack` [3du, 3dg, 3et]

## Pictures and crop, carried inside 3.31 [3dv]

- [ ] The post-build step: crop, layout and pictures read `pdfmd-options` at every level (front matter, metadata files, folder layers, config, `--setup` rows, command line) and work on the real output PDF; replaces 3.31.21's re-run of pdfmd in a scratch folder; `default-output` takes a list
- [ ] Layouts `long` (pages stacked into one tall page, any engine; a seamless tall page via Typst `height: auto`, LaTeX to 16383 pt) and `grid` (fewest columns*width + rows*height), with gap and background, with and without `--crop`
- [ ] Tools: a fallback chain for the ink box, PNG, SVG (gs, mutool, pdftocairo, pdftoppm, sips, pypdfium2), a tool-path setting, `--doctor` lines; `--install` and `--doctor` bring them from pip, brew, winget (Ghostscript on Windows: `gswin64c`, the installer)
- [ ] `--image-background`; webp (Pillow, pypdfium2 or ImageMagick); `--to pdf,docx` for formats that are not pictures (a loop of runs)
- [ ] docx and odt with `--crop`: a lean page of the cropped size, or a document holding the cropped vector or PNG (`lib/pdfmd_office/fragments.py` has the pieces)
- [ ] The equation popup (Colophon `Pop/`, once eqpop) calls `pdfmd --crop` when it can; its own AppKit crop stays as the fallback

## Chemical structures, carried inside 3.31 [smiles] [3ec]

- [ ] `smiles` blocks (fenced and `::: smiles`; SMILES or molfile, `file=`, one molecule per line, `name=`): RDKit pictures and chemfig (mol2chemfig, compiled once and cached), `engine=auto`, `cache: {smiles}` (off by default), settings under `pdfmd-options.smiles`; then inline `smiles`, `engine=indigo` [3ec]

## Distribution inside this repository, carried inside 3.31 [3ed]

- [ ] Obsidian plugin (plain JS, `manifest.json` at the root, bare-version release from publish.yml, `pdfmd --install obsidian`); VS Code extension published from publish.yml if a token exists [3ed]

## Making the main `pdfmd.py` main code more manageable [3fi]

- [ ] Runtime: lazy heavy imports (pypdf alone is about half of every start), a probe cache, fewer engine re-runs; no Rust/Go rewrite [3fj]
- [ ] After the whole queue: pytest + pytest-xdist as an optional development extra (CI stays on unittest); `scripts/test_parallel.py` stays the runner unless it keeps failing in the waves [3fi D62]

## Obsidian flavour, 3.32.x patches (no minor bump yet) [3ee]

- [ ] The rest of Obsidian's syntax: note embeds (`![[note#Heading]]`, `#^block`), links between notes, tags, block ids, properties, foldable and custom callouts, extra task statuses [3ee]
- [ ] Let users define their own named flavour presets [3ex N144]
- [ ] Other flavours as `flavour` values, one at a time after Obsidian: MyST, MkDocs/pymdown, CriticMarkup, Logseq/Roam, Quarto extras, MultiMarkdown, Djot [3eo]
- [ ] Spans `.caps`, `.wavy`, `.dotted`... in every writer, then the shorthand (`++x++`, `!!x!!`, `??x??`) as opt-in `markup` kinds; CriticMarkup and abbreviations later [3eq]
- [ ] Typst route: inline-maths WARNs on a source that the LaTeX engines build (seen with the control-character note) [3es D85]
- [ ] Community plugins: a vault report from `.obsidian/community-plugins.json`, adapters for plain-text plugin formats, rendering through Obsidian for the rest (never headless: the CLI needs the running app); unknown stays as code with one note; the other tiers settled when built [3er D85]

## Other tools' command lines

Answer the keys of the other `pdfmd`, `mdpdf` and `md2pdf` tools under their own command names, check their behaviour, take
what pdfmd lacks. Plain `pdfmd` keeps its own meanings (`-p` is slides, `-s`, `-h`...); a PDF read as Markdown is
batchocr's, so what is listed for it lands in batchocr. Never delegate to a copy of another tool. The quick ones first; the rest
is low priority. [3di]

- [ ] `--security`: one common policy that every renderer enforces (HTML, remote files, scripts, raw TeX), default today's behaviour; a wkhtmltopdf / untrusted-input warning in the docs and `--doctor` [D126 3di 3en]
- [ ] Take over, each checked first: Jinja context from the front matter for `.md.j2` (jmaupetit), `.page-break` and a custom page-break marker (`md-to-pdf`, mdPDFinator `-n`), `--document-title` and `--body-class` for the HTML route, emoji shortcodes (`:thumbsup:`), theme files and `--dump-theme` (Go `mdpdf`), `[TOC]` and `!!!` admonitions (markdown-convert)

## Before 4.0

- [ ] Coloured links on by default in LaTeX and Typst, with the other default flips; the `colorlinks` setup row is the opt-in until then [3fl D84]
- [ ] Pandoc + TeX tests on Windows and macOS (Linux only today) [3db]
- [ ] Tool paths per document and on the command line: the `tesseract-path`, `soffice-path` ... keys also as `pdfmd-options` and flags, so one document can pin another version of a tool [3dt]
- [ ] Windows guide (16 sections): the Windows session adds it to the repo as a docs file; wire it into `pdfmd --doc` with the documentation programme [3dg, 3dp]
- [ ] **Documentation programme**: a reference generated from the code's own registries, an example for every feature built and checked in CI, a new README, `docs/recipes.md` retired into it; hosted from the repo (GitHub Pages, indexable) and bundled for `pdfmd --doc`; a layered README tested by a beginner on a clean machine; agent surfaces (task table, `--help` as JSON, `llms.txt` hosted); an audit of ambiguous names (one meaning per word, a test for collisions and aliases); feature pages carry the version added, fixed and last tested [3dg]
- [ ] One event log for every route; the split itself is done [3fi] [3bh]
- [ ] Lean install: extras that survive their absence with one message and a CI leg for the core only; a separate core distribution (`pdfmd-cli` staying the full default) only if that leg shows a real saving [3dx N144]
- [ ] `--install full|core|cortex` also fetch the default fonts (`fonts:core`: STIX Two, JetBrains Mono, Noto Serif, symbols; about 8 MB), sizes table updated [3ei]
- [ ] Docs: a table of every install kind (pip or download, size, `--uninstall`, `--check-dependencies`), decided together with the lean install [3ei, 3dg, 3dx]
- [ ] The pre-4.0 pass (code review, edge cases, documentation) reads pdfmd as an agent would, not only as a human: exit codes, output size, non-TTY, name guessing, untrusted documents; then tested with the author's local models on real tasks [3ff, 3dg]
- [ ] 4.0
- [ ] Zenodo: CITATION.cff; at 4.0 one GitHub Release for v4.0.0 published by hand, then the concept-DOI badge [D128]

## Colophon after the review of 2026-11-16, agreed, in this order [3fu 3fw D81]

- [ ] The editor takes its own autosave (and a file that is only touched) for another program's change: a false "changed by another program" sheet while typing; compare the disk with what the document last read or wrote; a self-test that types across an autosave [3fu B1, 3fw H4]
- [ ] `--smoke-prefs` hangs on its own "Invalid setting" alert since 0.3.20; the self-tests' output line-buffered; `gui.yml` has never run [3fu B12]
- [ ] Silent file damage: a UTF-8 BOM dropped at the first save; a save through a symlink to a file fails; a CRLF pair split by the caret (a lone CR written); two spaces becoming ". ", after a look in a window [3fw H1 H2 H3 L2]
- [ ] The installed app can be older than the checkout (0.3.0 vs 0.3.24): the About box says so [3fu B2 N144]
- [ ] Typing parity with CotEditor: a line-height setting (1.3, the same for every line), wrapped lines indented, tab width and spaces for Tab, Return keeps the indent, Shift Left/Right, Go to Line, font size keys; then the status bar (selection counts, words, graphemes); a TextKit 2 spike first [3fu B, 3fw D]
- [ ] Find and Replace with regular expressions (Find All, Replace All) [3fu B]
- [ ] A Help menu (its search field finds every command), a View menu per window kind, the missing Mac staples [3fu C]
- [ ] Robustness: self-tests never write the real settings; the mode switch closes the editor only once the studio is up; pdfmd discovery behind marker lines; a `pdfmd --serve` that died is noticed and started again [3fu B3-B6]
- [ ] PDF viewer: Back and Forward after a link, page-layout commands, Print [3fu C]
- [ ] Web studio: no second menu row in the Mac window, the toolbar's wrap, one icon set, a title block; a tab whose file changed gets Keep Mine / Load from Disk; outside changes seen without a focus change [3fu C, B14]
- [ ] `pdfmd --serve`: the cookie named after the port (two projects in one browser overwrite each other's token); the token checked before a body is read; a file with any CRLF becomes all-CRLF at a save [3fu B9]
- [ ] The rest: the preview pane's width on a small screen, the preview cache never cleaned, repeated line numbers with a stray CR, Save As forcing an extension, a second window exactly over the first, the scroll place after a reload [3fu, 3fw]
- [ ] Colophon beside CotEditor on a real screen: the same file in both windows at one size, a picture of each state (and the PDF window beside Skim); with it the checks that need a window (the studio's line-number gutter, the Settings tabs, the status bar in dark mode) [3fu G, 3fw, 3fh]
- [ ] Any folder opens as a project: an empty one offers its first file, a tie lets the author pick the main document; a generic folder-panel hint [D129]
- [ ] PDF viewer: Skim's background (the system under-page colour, resolved once per appearance), a colour setting; the sidebar collapses when dragged past its minimum; Horizontal Continuous [D129]

## Investigate first, no commitment

- [ ] Engine speed: XeLaTeX built a document ~4.7x faster than LuaLaTeX in an outside review; measure warm (font cache), then decide whether pdfmd prefers a faster engine that built a comparable document before [3fk]
- [ ] pdfmd-gui: an Overleaf-like project view; one local web UI plus thin native wrappers, a client of the CLI, never obligatory; its foundation (emit, `--json`, the split, the generated reference) ships in 3.x before 4.0 [3do]
- [ ] pdfmd-gui window shell, open: native wrapper vs an optional chromium window (`--install chromium`, a `--setup` row to toggle); no Node needed [3do]
- [ ] Colophon web UI and JSON core, slice 1 built (3.32.36); left: builds with job events, checks and formats, settings schema and values, history, `/api/raw`, search; Tauri postponed [3do]
- [ ] Colophon: a Format popup in the Save As panel, so the export is noticed (an Export panel stays proposed) [3do]
- [ ] Colophon: one History panel, two lanes (git for edits: log, diff, restore; `.hst` and the build record for builds); a setting that offers `git init`, also into a NEW folder, never silently; a proper diff view; and the cure for `.backups/` bloat: git for the text, the newest N PDFs loose and older ones in one solid archive per document (never in the text repository) ; read-only git and build lanes first [3do N144]
- [ ] Colophon: the live view reads CommonMark, a build reads Pandoc's Markdown, so citations, `: caption` lines and `\cref` show as typed; route (a) a line-preserving text pre-pass (caption to bold, citeproc text per cluster), route (b) a second reader aligned by block; postponed [3do]
- [ ] Colophon and pdfmd: language runners (R, Python): a settings table extension to command and mode (one-shot `Rscript`/`python3`, or a file sent to a live session), after the terminal window; plugins only if the table is not enough [3do]
- [ ] Colophon: one JSON syntax table for the page and the native editor; raw TeX/HTML and fenced languages inside Markdown, `calc` and `hst` syntaxes, kits, BibTeX, TeX, CSV [3do]
- [ ] Colophon: previews of CSV (an HTML table), `.hst` (entries) and kits; YAML as a diagram maybe [3do]
- [ ] Colophon: a Finder icon per file type (today one icon for all) [3do]
- [ ] Colophon: an inspector sidebar (document, outline, warnings), a syntax popup, a split editor with an outline popup in each pane [3do]
- [ ] Colophon: the PDF viewer's own annotations (PDFKit); better than Skim's, which the author finds poor [3do]
- [ ] Source jump: a click in the render opens the source line (SyncTeX, Typst's `typst-ide` jump, our own block map for other engines); later [3do]
- [ ] Colophon: check that a login launch opens no untitled window (only a real login shows it); a non-activating equation popup (showing it may lift every editor window) [3do]
- [ ] A `.calc` file kind: `::: {.calc file=NAME.calc}` imports it as it is and it works with the document like any calc block; a syntax map in Colophon, carried by `--merge` and `--check` [3ez]
- [ ] More input kinds in Colophon: HTML documents with a render, and Pandoc's plain-text readers (rst, org, textile ...) by extension, `--from` or a YAML key [3do]
- [ ] The `pdfmd` flavour as the accept-everything one: it turns on the usually-off togglers of the Obsidian, Pandoc and GFM flavours, plus rst constructs (and other plain-text markups, if useful) as one more toggler (flag, `pdfmd-options` key, `--setup`; off elsewhere, on in `pdfmd`); audit first [3fh, 3ex]
- [ ] Colophon: a syntax chooser button like CotEditor's, reading CotEditor's syntax files and the JSON table [3fh, 3do]
- [ ] Colophon: two full-screen plain-text windows side by side; check what happens when the left one minimises (CotEditor has a bug there) [3fh]
- [ ] Colophon plain-text mode: the status bar stays white while the window is dark [3fh]
- [ ] reveal.js route, pptx slides, Quarto's slide formats [3bu, 3bv]
- [ ] docx output and raw LaTeX multicols: nulabreport 1.29.1 writes tables between a raw `\begin{multicols}` and `\end{multicols}` as plain `tabular`; check what the docx (office) path does with those raw fences and the tables inside, since it parses raw LaTeX too
- [ ] Features that may leave pdfmd for their own repositories (rebuilding a docx source from a PDF, `html2qmd`) [3dg, 3bn]
- [ ] Investigate headless wordcraft/gridcraft/deckcraft beside or instead of LibreOffice; if wordcraft converts headlessly, an engine in the fallback chain [N123]

## In other repositories

- [ ] inkmd: a quote right after a list is read as a paragraph; fix upstream, re-vendor [3ci]
