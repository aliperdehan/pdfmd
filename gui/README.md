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
- No line numbers yet (counting lines in a 50 MB file is not free); no preview; no pdfmd build.

## Settings

Every number that changes behaviour is a setting (UserDefaults), none is a constant in the code:

    pdfmdedit --settings
    defaults write io.github.aliperdehan.pdfmdedit highlightMarginLines -int 300

They are app settings, not `pdfmd --setup` rows yet. `textKit` chooses the text engine (2 = system default,
1 = older); `wrapLines`, `fontSize`, `spellCheck`, the colouring delays and margin are the others.

## Colours

The colours are named roles with a soft built-in pair for the light and the dark appearance; `pdfmdedit --settings`
lists them. Replace one in the same way as a setting (read at start-up):

    defaults write io.github.aliperdehan.pdfmdedit color.heading -string "#3B5F99,#8AA9D6"

`"#RRGGBB"` alone is used in both appearances; a wrong value is ignored. A whole-theme file is not built yet.

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
