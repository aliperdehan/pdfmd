# The web UI (`lib/pdfmd_web/`)

A prototype of the window that `pdfmd --serve` will show in any browser and that the Mac app will frame with native panels (queue entry 3do, Colophon 0.3.0).
It is **UI only**: every piece of data comes through `js/api.js`, and every editor through `js/editor.js`, so the core (S1-S3) and the native editor can be put
behind them later without touching the page. The page holds no pdfmd logic: what you can do here is a pdfmd command (the Export dialog shows it).

Open `index.html` in a browser, or `python3 -m http.server -d lib/pdfmd_web` and go to the URL it prints. No build step, no network, no node to use it.

**Two sources of data, chosen once by `js/api.js`.** Served by `pdfmd --serve FOLDER` (open the printed URL) the page works on the real folder: the
project tree, the files (a save sends the `mtime` it read and is refused with 409 when the file changed on disk), the outline and the live view
through `/api/...`. Opened from disk, in the Mac app's window, or with `#selftest` in the URL, it runs on `fixtures/fixtures.js` (the demo project).
Everything else (history, checks, build, settings values, the export table) is still fixtures in either mode: those endpoints come in later slices.
The placeholder `APP` stands for the product name (undecided).

## What is in it
- **Overleaf's layout, free**: a rail (Files and outline, Search, Checks, History, Settings), tabs of open files, a toolbar (undo, heading level, **B**, *I*, code,
  link, list, table, **Ω** symbols, an Insert menu with the extra syntax: comment, code block, `:::` div, `::: calc`, image, math, footnote, citation),
  a Live / PDF / Log pane, Build with an engine dropdown, Export As with the nested menu (the same table as the Mac app, from `colophon export --list --json`),
  five layouts (split, editor only, preview only, preview in a browser tab, focus), a resizable splitter, light and dark from the system.
- **The live view** (render modes auto / instant / watch / manual, their numbers are settings): headings, text, lists and tables render while you type, and an
  unfinished `**bold` is closed for display (dimmed). A selection in the source marks its block in the preview; a block under the pointer marks its lines in the source.
  Only the demo's own text is rendered by pandoc (CommonMark with source positions); an edited text goes through a small stand-in renderer (`api.js`).
- **Settings** drawn from the schema (126 rows from the Mac app's table, plus the live view's), validated by a schema-driven validator; rows whose `platforms`
  lack `browser` are hidden (the stored value is kept). **History**: two lanes (git edits with a coloured diff, builds). **Checks**: sample.
- **Toggles, not repeats**: a template pressed again takes itself out (B, I, code, link, comment, math, footnote, citation, code block wrap and unwrap the selection; a table,
  div, calc block or image inserted twice at one place is inserted once). The Ω picker inserts the LaTeX equivalent (`$\alpha$`, plain ASCII, the default) or the Unicode
  character: a switch in the picker and the setting `symbolInsert`.
- **A render costs what changed**: the live view keeps every block that an edit did not touch (pandoc's own HTML, found again by the source text of the block) and renders
  only the edited ones; an unfinished `**bold`, `*italic`, `` `code ``, `$math` or `<!-- comment` is closed for display.
- **The editor is switchable**: CodeMirror 6 (vendored, MIT, `vendor/cm/`, 537 KB, 188 KB gzipped) or a plain text box, behind one contract.

## What is real and what is a stand-in
Real: the export table, the settings schema, the pandoc render of the demo, `fixtures/report.pdf` (made by pdfmd). Stand-in (marked "sample"): the build run, the history,
the checks, the live render of an edited text. Not here: files on disk, git, click in the PDF to the source (later), math and citations in the live view of an edited text.

## Files
- `index.html`, `css/app.css` (one theme from CSS variables, hairlines drawn once), `js/app.js`, `js/api.js`, `js/editor.js`
- `demo/`: the demo project (nobody's own documents). `tools/make_fixtures.py` writes `fixtures/fixtures.js` from it and from `colophon` and `pandoc`
  (`python3 tools/make_fixtures.py`); `fixtures/report.pdf` is `pdfmd report.md -t pdf -e typst -o ../fixtures/report.pdf` run in `demo/`.
- `vendor/cm/`: `entry.js` (the CodeMirror implementation of the editor contract), `package.json` (exact versions), `build.sh` (needs node, only to rebuild
  `codemirror.js`), `LICENSES.txt`.
- `js/selftest.js`: open `index.html#selftest`; it drives the page like a person and writes `ok` / `FAIL` lines into `#selftest`. Headless:
  `Edge --headless=new --virtual-time-budget=20000 --dump-dom 'file://.../index.html#selftest'` (53 checks).

## Findings that the core (S1) must answer
- Pandoc's source positions exist only for the `commonmark` and `gfm` readers, **not** for pdfmd's own `markdown` reader, and then without citations: the live view
  of a document with `[@key]` shows the key as typed. Blocks only: a list item has no position, and a list's end position runs on to the next block.
- `pdfmd --check-dependencies` does not list browsers (they look available when they are not).
