# Colophon (alpha, `gui/`)

**Colophon, the pdfmd workbench** (named on 2026-11-04; a colophon is the note at the end of a book about how it was made): a native macOS
text editor for Markdown and other plain-text sources, and a PDF viewer, the first piece of the planned pdfmd GUI. Its executable, the
SwiftPM target and the bundle id keep the older name `pdfmdedit` (so settings, file associations and window positions stay).
The About box names the pdfmd it works with: the newest one the login shell knows (the terminal's alias and every `pdfmd` on its PATH)
unless the setting `pdfmdCommand` names one.
It is a separate program in this repository, written in Swift with AppKit; **nothing in it ships in the PyPI
package** (`pip install pdfmd-cli` is unchanged), and it contains no pdfmd logic. Needs only the Command Line
Tools (no Xcode), macOS 13 or newer.

Goal of this alpha: typing, pasting and scrolling that stay instant on very large files, to decide whether the
GUI is worth pursuing. There is no preview pane and no Quick Look extension yet. Since 0.2.0 the same app also opens PDFs in a
viewer window of their own (below); the editor and the viewer are not yet wired together (no build button).

## Build and try

    cd gui
    ./build.sh              # swift build + build.noindex/Colophon.app (ad-hoc signed); nothing is launched
    ./build.sh --install    # also copies the app to ~/Applications
    build.noindex/Colophon.app/Contents/MacOS/pdfmdedit FILE.md   # blocks until its windows are closed

`pdfmd --editor` should be able to point at that last command (the process lives until its windows close);
this is **not tested yet** in this alpha.

## What it does

- Opens any file (the Open panel is not limited to known types); UTF-8, falling back to Latin-1; saves in the
  encoding it read. Tested without a window: real saves of `.tex`, `.hst`, `.yaml.bak`, a file without extension and a
  Latin-1 file. It is an `NSDocument` app, so autosave in place, versions, Revert, Open Recent and the Find bar
  come with it, but those were **not exercised** by a person yet.
- Colours Markdown (headings, lists, quotes, emphasis, links, code spans and fences, `$math$`, comments) and a
  YAML front matter. The colours cover the visible lines plus a margin and are kept out of the text storage,
  so colouring never delays a key press.
- A status bar like CotEditor's (Lines, Characters, Location, Line; file size, encoding, line ending), every element a setting. The
  counts of a big text are made in slices between key presses (a 50 MB file: nothing waits), the caret's line from an anchor that
  typing does not invalidate. "Characters" counts UTF-16 units (an emoji is two); the encoding and line ending are shown, not yet
  changeable. No preview; no pdfmd build.
- Line numbers in the margin (View > Hide/Show Line Numbers, ⌥⌘N; setting `lineNumbers`): only the visible lines are numbered, a wrapped line once,
  the caret's line at full strength. The number of the first visible line is counted from an anchor kept between draws, so
  scrolling and typing never count from the top again. Width, size, opacity and padding are settings (`lineNumber*`).

- A PDF viewer (0.2.0), opened by File > Open, by `pdfmdedit FILE.pdf` and by Open With (the app is only an "Alternate" handler of
  PDFs, so Preview keeps its place): PDFKit, pages one below the other, a sidebar (⌥⌘T shows or hides it) with the page thumbnails (⌥⌘2) or the table of contents (⌥⌘3, the PDF's outline as a tree that follows the page being read; a segmented control at its top does the same), a divider that is easy to catch (`pdfDividerGrabPt`), that resizes the thumbnails with it and that a double click (or View > Reset Sidebar Width) sets back to the default width, a file that changes on disk is shown again by itself (View > Reload Automatically turns that off: the window then says "file changed" and View > Reload, ⌘R, does it), zoom (⌘= ⌘- ⌘0, ⌘9 fit page,
  ⌥⌘9 fit width), Go to Page (⌥⌘G), Find (⌘F, ⌘G, ⇧⌘G; Enter in the field runs the search, Enter again goes to the next match;
  matches are marked in the pages), the page and zoom in the window's subtitle. **A changed file is shown again by itself**
  (a build, a copy, an atomic replacement): after the file has stayed unchanged for `pdfReloadDebounceMs`, and only when it ends
  with `%%EOF` (a half-written file is skipped and looked at again), on the same page, at the same place and zoom; the old pages stay
  on screen (a second PDFView, a second thumbnail view) until the new ones have drawn themselves, because a PDFView that is given
  a new document blinks. Read-only: no notes yet (marker, pen, eraser, text blocks are the next step). Settings: the PDF tab.

- **The equation popup** (0.2.12; it was the separate app eqpop, absorbed): a floating window that renders a LaTeX snippet (display or
  inline math, chemistry with `mhchem`, text) or a Markdown snippet (through pdfmd) to a tightly cropped vector PDF, shows it, and
  copies it as PDF and PNG with ⌘↩ (or drag it out, or Save as PDF, PNG or SVG). Window > Equation Popup (⌥⌘E) opens it. The preamble
  is a plain file (`~/Library/Application Support/pdfmdedit/popup/preamble.tex`, copied once from eqpop's folder if there is one, never
  overwritten); a failed run shows a table of every error (double-click jumps to the line) and a Log. `pdflatex` renders from a cached,
  compiled preamble. With the setting **`popMenuBar`** on, Colophon keeps running in the menu bar (an `f(x)` icon, a global shortcut,
  `popHotkey`, ⌥⇧T by default; **quit a still-running eqpop first**: it holds the same shortcut, and macOS lets both apps register it, so neither tells you about the clash) and stays alive when its last window is closed; with
  it off, which is the default, there is no icon and no shortcut. Every choice is a setting on the Popup tab (and so a
  `colophon settings set` away), including the delays, time limits and the crop numbers that eqpop had written into its code.
  `colophon eq SNIPPET OUT.pdf [--inline|--text] [--engine E] [--png F] [--svg F]` renders without a window.

- **Tabs** (0.2.15): File > New Tab (⌘T) opens a new empty document as a tab of the window you are in; ⌘N is still a new window and nothing becomes a tab by itself
  (macOS's "Prefer tabs when opening documents" still applies). The Window menu has Show Tab Bar, Merge All Windows, Move Tab to New Window and the tab switchers. Command-1 to command-8 select tab 1 to 8 (Window > Select Tab; in the web studio window, the page's tabs). Command-9 is one menu item that changes its name with the window: Zoom to Fit in a PDF window, Last Tab in the others (AppKit gives a key to the first item that has it and does nothing when that one is off, so two items could not share it). Control-command-S (Window > Switch to Studio / Switch to Plain Text; the key is the setting `keySwitchMode`, General) REPLACES the window: an editor with a saved file is saved and becomes the studio of its project (the folder of the file, the folder above it for a file of `parts/`); an unsaved new file hands its text over as a new tab of the studio's project; from the studio the page saves its file, which opens in an editor window while the studio closes. A new document is called `Untitled` and saved as `Untitled.md` (the save panel selects the name, not the extension); both are settings (Editor: `newFileName`, `newFileExtension`). An editor window also follows a file that another program rewrites (`reloadOnDiskChange`): at once when unedited, by asking which version to keep when edited.
- **Web studio window** (File ▸ Open Folder in Studio…, ⇧⌘O; Window ▸ Switch to Studio; File ▸ New Studio Demo Window, ⇧⌘N, and `--web` at launch run the demo on fixtures): the page of `../lib/pdfmd_web/` (the Overleaf-like window, behind two contracts: data and editor; see `web/README.md`) in a WKWebView. For a folder the app starts `pdfmd --serve FOLDER` (the pdfmd that builds use, found the same way; `studioServerTimeout` is how long it waits) and loads the page from it, so the studio works on the real files through pdfmd's JSON core; closing the window or quitting stops the server. The page's own preferences (layout, render mode) are kept per address, and the port changes every time, so they start fresh. The Mac owns the shortcuts and the menu bar: ⌘R renders the live view (the page is not reloaded), ⌘T makes a new tab of the project, ⌘S saves by the page's logic, ⇧⌘F searches, ⌘W closes the window and asks first when something is unsaved; the title and the unsaved dot follow the page. `--smoke-web` tests it in real WebKit (a real folder through `pdfmd --serve`, and the page's own self-test), `--web-screenshot PATH [--dark]` draws it to a PNG without showing a window.
- **Export As** (0.2.14): File > Export As writes the document in another format through pdfmd: **Markdown (standalone)** (`--merge`: the parts, the
  metadata, the preamble, the pictures in one file that builds anywhere), **PDF** (Auto, or an engine: LaTeX > lualatex, xelatex, pdflatex, latexmk,
  tectonic; Typst; HTML > WeasyPrint, wkhtmltopdf, Paged.js, Prince, Chrome, Chromium, Edge, Brave; Others > LibreOffice, Calibre, ConTeXt,
  groff, the built-in inkmd, md2pdf), **Word**, **HTML**, **Cropped** (PDF, SVG, PNG: every page cut to its ink), and **Others** (documents, slides, e-books, web, plain text and Markdown, markup, XML and
  data, pictures: every format pdfmd writes). An engine that `pdfmd --check-dependencies` reports missing is greyed. The document is saved first (pdfmd
  needs its folder), a Save panel asks where, the window's subtitle says how it went, a failure opens the build log. Your "pdfmd options for a build"
  are used too, except a `-t` or `-o` of yours. An export never lands in the preview pane and never opens a viewer. `colophon export FILE FORMAT
  [--engine E] [-o OUT]` does the same without the window, `colophon export --list [--json]` shows the table; setting `exportReveal` shows the new
  file in Finder.

## Source layout

`gui/Sources/` is one SwiftPM target (`pdfmdedit`), grouped by area: `App/` (main, menus), `Editor/` (the editor window, colouring,
line numbers, status bar), `PDF/` (the viewer), `Settings/` (the settings table, the Settings window, themes and palette),
`Pop/` (the equation popup), `Checks/` (the benchmark and the smoke tests).

## Settings

**The command line, `colophon`.** The app's own program started without a window; `build.sh --install` prints the one line that links it
into a folder on the PATH (`ln -s ~/Applications/Colophon.app/Contents/Resources/colophon ~/.local/bin/colophon`). In the manner of `quarto VERB`:
`colophon render ARGS` is `pdfmd ARGS`, `restore ARGS` is `pdfmd --restore ARGS`, `install WHAT` is `pdfmd --install WHAT`, `pandoc ARGS` is
the pandoc the preview uses (all hand the arguments over unchanged, in the terminal's own environment, and exit with the tool's status; the pdfmd is
the newest found, or the `pdfmdCommand` setting, remembered for `toolCacheSeconds` in a file so that a new process does not ask the shell
again); `check [--json]` lists the versions and places of Colophon, pdfmd, pandoc, the TeX engines and typst; `open [-w] FILE...` (also plain
`colophon FILE`); `help`, `version`. **Everything the Settings window sets can be set from here**, for scripts and for an agent that is told
"set my font to Courier": `colophon settings list [TAB|WORD] [--json]`, `get KEY`, `set KEY VALUE [KEY VALUE ...]` (all or nothing; values are
checked, a font or a theme is accepted in any case and stored by its real name, a wrong name suggests the right one), `reset KEY... | --all`, `fonts`,
`themes`. A running Colophon applies the change at once. `COLOPHON_DOMAIN` points the command at another settings domain (the tests).
All menu shortcuts are fixed in the code for now (65 rows in `App.swift`); user-set shortcuts and presets are planned.

**HTML files** (`.html`, `.htm`, `.xhtml`) open as the page, in a window of their own (WebKit), and are watched like a PDF: a rewritten file
is loaded again on the same place of the page, once (View > Reload Automatically, `htmlAutoReload`, turns that off: the window says "file
changed" and ⌘R loads it), with the old picture of the page kept on screen until the new one is there. The toolbar has zoom, Show Source
(⌥⌘U: the same file as text, in an editor window; an `.svg` file opens here too, drawn by WebKit, with scripts off) and a search field (⌘F, ⌘G, ⇧⌘G). A link to another file opens it in Colophon, a web link
in the browser. `htmlOpenAs` = 1 opens `.html` as text instead.

**The studio (first sketch): the preview pane.** View > Show Preview (⌥⌘P) puts a pane beside the text of an editor window. A switch at its
top chooses HTML or PDF (View > Preview as HTML / PDF). *HTML* is made by pandoc run directly on the text in the window, saved or not
(about 0.15 s for a page; `pdfmd -t html` takes 3 s and a PDF 20 s), after the typing has paused (`studioPreviewDelayMs`), and it scrolls to the same
fraction of the page as the text (`studioFollow`). It is a preview: pandoc's own Markdown, not pdfmd's defaults, filters or fonts (`htmlPreviewArguments`
adds pandoc words, `htmlPreviewCSS` a style sheet); math is MathML, scripts in the text do not run, pictures beside the document load. A pandoc
error shows in the pane's status line and the old page stays. *PDF* shows the last build: ⌘R builds, and while the pane is open the PDF appears in it
instead of a window of its own. `startupWindow` = 1 (Settings > Studio) opens every new editor window as a studio; the plain editor stays the default,
because the studio costs a pandoc run after every pause in the typing.

**Build (⌘R in an editor window).** View > Build PDF saves the file (an untitled one asks where) and runs pdfmd on it, the newest one
that the login shell knows (or the `pdfmdCommand` setting), in the file's folder and in a login shell, so pandoc and the TeX tools are found
from a Dock launch too. The result is in the window's subtitle ("Building…", "Built a.pdf in 18.7 s", "Build failed"); a failure opens the log
(View > Show Build Log, ⌥⌘R, also holds the output of the last build). The PDF is found from pdfmd's own `OK  a.md > a.pdf` line; an open
window of it is shown again once, otherwise it is opened (`buildOpensPDF`) and the keyboard stays in the editor. ⌘R during a build queues one
more build. When a `pdfmd --watch` is already rebuilding the file on every save (`pdfmd -w`, or the one `pdfmd --edit --editor` starts), ⌘R only saves
(`buildWhenWatched` builds anyway). A build is stopped, with everything it started, after `buildTimeout` seconds. In a PDF window the same key
reloads the file.

**The Settings window (⌘,)** has nine tabs (the window is sized to the tab shown): General (quit when the last window closes, the pdfmd command), Editor (font, size, wrapping, spelling, text engine), Status bar (which elements show), PDF (thumbnails, layout, zoom, reload), HTML (open as page or as text, reload, zoom step), Studio (the preview pane), Build (⌘R: extra pdfmd words, time limit, opening the PDF, a watcher already running), Colours (the two themes,
whether the theme sets the background, and for each colouring role the category it takes its colour from plus its light and
dark colour, with a Reset) and Performance (the colouring delays and limits). It is generated from the tables in
`Settings.swift` and `Palette.swift`, so it cannot drift from the shell: a change is stored at once, applied to the open
windows (all but the text engine), and every setting stays a `defaults write` command for scripts and agents. "Restore
defaults" clears one tab's keys.


Every number that changes behaviour is a setting (UserDefaults), none is a constant in the code:

    pdfmdedit --settings
    defaults write io.github.aliperdehan.pdfmdedit highlightMarginLines -int 300

They are app settings, not `pdfmd --setup` rows yet. `textKit` chooses the text engine (2 = system default,
1 = older); `wrapLines`, `fontSize`, `spellCheck`, the colouring delays and margin are the others.

## Colours and themes

Themes are CotEditor's `.cottheme` files (plain JSON): the editor reads them as they are, so CotEditor's themes and any
theme made for it work here. `Themes/` holds copies of CotEditor's thirteen built-in themes (Apache 2.0, see
`Themes/NOTICE.md`); the editor also looks in `~/Library/Application Support/pdfmdedit/Themes`, in CotEditor's own
folder and in CotEditor.app, so nothing needs CotEditor installed. `pdfmdedit --themes` lists them.

    defaults write io.github.aliperdehan.pdfmdedit theme -string Dendrobates
    defaults write io.github.aliperdehan.pdfmdedit themeDark -string "Dendrobates (Dark)"

`theme` is used in a light appearance, `themeDark` in a dark one (default Anura and Anura (Dark)). A theme also sets the
text, background, caret and selection colours (`themeCanvas` = 0 keeps the system's).

A theme colours ten categories; the editor's colouring works in named ROLES, and each role takes the colour of one
category, listed by `pdfmdedit --settings` (the choice follows CotEditor's own Markdown and YAML syntaxes: headings
`types`, bold `commands`, list markers and quotes `keywords`, link text `values`, link targets `characters`, code
`strings`). **Math has no CotEditor colour; here it takes `numbers`.** Change one role without touching the theme:

    defaults write io.github.aliperdehan.pdfmdedit category.math -string text      # `text` = no colour for math
    defaults write io.github.aliperdehan.pdfmdedit color.heading -string "#3B5F99,#8AA9D6"

`"#RRGGBB"` alone is used in both appearances; a wrong value is ignored. Read at start-up. With no theme file found
the soft built-in colours are used. `--set key=value` on the command line applies to that run only.

`pdfmdedit --smoke-prefs FILE [--png DIR]` builds the window without showing it (asserted), drives every kind of control
through its action in a scratch settings domain (never the real one) and checks what was stored and what the open
editor did; `--png` also draws each tab into DIR.

## Benchmark and smoke test (no window is ever shown: the smoke tests assert it)

    .build/release/pdfmdedit --bench --mb 50 --paste-mb 20 [--tk 1|2] [--no-highlight]
    build.noindex/Colophon.app/Contents/MacOS/pdfmdedit --smoke FILE.md [--set textKit=1]

`--bench` prints open, jump, typing, paste and scrolling times for a generated (or `--file`) document. "Paint"
means `cacheDisplay` into a bitmap; typing repaints the caret line only, like a screen refresh after a key press.
The numbers compare variants with each other and are not a measurement of any other editor. `--smoke` opens the
file through the real document path, edits and scrolls it and checks the bytes and that the colours stay on
screen; `--smoke-save DIR` makes files of several kinds in DIR and saves each to disk. `--gen MB PATH` writes the
benchmark's document so that it can be opened by hand. `--smoke-build FILE.md [--real]` runs ⌘R in an editor window against a stand-in for pdfmd (save first, a file name with quotes, the PDF found and shown once, a queued second build, a failure's log, a timeout that kills the whole tree, a running `pdfmd --watch`); `--real` also builds with the installed pdfmd (run it under `env -i HOME=$HOME PATH=/usr/bin:/bin` to see what a Dock launch has). `--smoke-cli` runs the command line as a program on a scratch settings domain (settings list/get/set/reset and their checks, a running app told at once, render/restore/install/pandoc handing over unchanged, check). `--smoke-studio` drives the preview pane against the real pandoc (unsaved text, a burst of typing, math, a picture, an anchor, a script that must not run, an error, the PDF, following the scroll, the startup setting); `--live-studio FILE.md [FILE.pdf]` does it in a real window and saves screenshots (`PDFLIVE_SHOT=PREFIX`). `--smoke-syntax` runs `lib/pdfmd_web/syntax/cases.json` (the cases the Python test and the page run too) through the editor's own colouring pass. `--smoke-html` opens an HTML file through the real path and checks the load, the reload on the same place (once), the manual mode, find, zoom, anchors and Show Source. `--smoke-pdf FILE.pdf` (at least 3 pages) opens a copy of the PDF through the real
document path without a window and checks zoom and its limits, the same place after the file is rewritten in place, replaced atomically and
caught half-written, search, and the PDF settings; `--smoke-tabs` checks that ⌘T makes a tab and not a window; `--smoke-export` checks the Export As table and menu (every row reachable; every Pandoc writer offered or named with the reason it is not), the words of your own options that must not reach an export, an editor window exporting against a stand-in for pdfmd, and `colophon export` with the pdfmd that is installed; `--smoke-pop` checks the equation popup headless (the wrapper and error parser, the shortcut words, the settings, the copy from an eqpop folder, real pdflatex and pdfmd renders, the window built and never shown, the keys, a private pasteboard, `colophon eq` as a subprocess); `--pop-screenshot OUT.png [--source TEXT] [--appearance light|dark] [--below] [--preamble]` draws the popup **off screen** (use this, not a live window, to look at it). `--bench-pdf FILE.pdf` times PDFKit's open and a page rendered at 1x, 4x and 16x and
prints the resident memory. `--live-pdf FILE [thumb|scroll|zoom|hide|contents|all]` does what a hand does (thumbnail clicks, wheel flicks, zooms, the
sidebar toggle) in a real window that never takes focus and prints the page and the longest main-thread stall per step. With `PDFLIVE_SHOT=PATH` the `hide` step also saves a screenshot of the window (for what no view dump shows). `PDFMDEDIT_TRACE=1`
(environment) writes a timestamped trace of place changes, file-change notifications and main-thread stalls to `/tmp/pdfmdedit-trace.log`; start the
app with `open -n --env PDFMDEDIT_TRACE=1 -a "$PWD/build.noindex/Colophon.app" FILE`. A silent fall back from TextKit 2 to TextKit 1 is reported
on stderr and at the end of `--bench`.

## Known limits

- A code fence is closed by the next fence line of either kind (parity), not by a matching one.
- Inline colour rules work within one line. The colour pass runs on the main thread, bounded by the margin.
- Opening or pasting a very large text scans it once for fence lines (about half a second per 50 MB).
