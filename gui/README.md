# pdfmd Edit (alpha, `gui/`)

A native macOS text editor for Markdown and other plain-text sources: the first piece of the planned pdfmd GUI.
It is a separate program in this repository, written in Swift with AppKit; **nothing in it ships in the PyPI
package** (`pip install pdfmd-cli` is unchanged), and it contains no pdfmd logic. Needs only the Command Line
Tools (no Xcode), macOS 13 or newer.

Goal of this alpha: typing, pasting and scrolling that stay instant on very large files, to decide whether the
GUI is worth pursuing. There is no preview pane and no Quick Look extension yet.

## Build and try

    cd gui
    ./build.sh              # swift build + build/pdfmdedit.app (ad-hoc signed); nothing is launched
    ./build.sh --install    # also copies the app to ~/Applications
    build/pdfmdedit.app/Contents/MacOS/pdfmdedit FILE.md   # blocks until its windows are closed

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
  changeable. No line numbers in the margin yet; no preview; no pdfmd build.

## Settings

**The Settings window (⌘,)** has four tabs (the window is sized to the tab shown): Editor (font, size, wrapping, spelling, text engine), Status bar (which elements show), Colours (the two themes,
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
    build/pdfmdedit.app/Contents/MacOS/pdfmdedit --smoke FILE.md [--set textKit=1]

`--bench` prints open, jump, typing, paste and scrolling times for a generated (or `--file`) document. "Paint"
means `cacheDisplay` into a bitmap; typing repaints the caret line only, like a screen refresh after a key press.
The numbers compare variants with each other and are not a measurement of any other editor. `--smoke` opens the
file through the real document path, edits and scrolls it and checks the bytes and that the colours stay on
screen; `--smoke-save DIR` makes files of several kinds in DIR and saves each to disk. `--gen MB PATH` writes the
benchmark's document so that it can be opened by hand. A silent fall back from TextKit 2 to TextKit 1 is reported
on stderr and at the end of `--bench`.

## Known limits

- A code fence is closed by the next fence line of either kind (parity), not by a matching one.
- Inline colour rules work within one line. The colour pass runs on the main thread, bounded by the margin.
- Opening or pasting a very large text scans it once for fence lines (about half a second per 50 MB).
