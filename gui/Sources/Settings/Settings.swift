import Foundation

let appVersion = "0.3.15"

/// Every number that changes the editor's behaviour is a setting here, never a constant in the code
/// (the repository's "no hardcoded thresholds" rule). They live in the app's UserDefaults, so there are two ways to change one:
/// the Preferences window (⌘,), which is generated from these tables, and the shell, which an agent or a script can use:
///   defaults write io.github.aliperdehan.pdfmdedit highlightMarginLines -int 300
/// `pdfmdedit --settings` lists them. They are not `pdfmd --setup` rows yet (alpha).
enum Settings {
    /// Where the settings are read from and written to: the app's own defaults, or a scratch domain in the tests.
    static var store: UserDefaults = .standard

    /// Posted after a setting changed through `set`/`remove` (the Preferences window); editors re-apply what they can live.
    static let changed = Notification.Name("pdfmdedit.settingsChanged")

    enum Kind {
        case number
        case flag
        case choice([Double])
    }

    struct Item {
        let key: String
        let value: Double
        let label: String
        let help: String
        let tab: String
        var kind: Kind = .number
        var live: Bool = true   // false: only windows opened afterwards use it
    }

    static let items: [Item] = [
        Item(key: "lineNumbers", value: 1, label: "Show line numbers", help: "1 = show the line numbers in the margin", tab: "Editor", kind: .flag),
        Item(key: "lineNumberMinDigits", value: 3, label: "Line numbers: least digits", help: "the margin is at least this many digits wide (it grows with the number of lines)", tab: "Editor"),
        Item(key: "lineNumberSizeDelta", value: 2, label: "Line numbers: points smaller", help: "how many points smaller than the text the line numbers are", tab: "Editor"),
        Item(key: "lineNumberOpacity", value: 45, label: "Line numbers: opacity (%)", help: "how strongly the line numbers show (the caret's line is always at full strength)", tab: "Editor"),
        Item(key: "lineNumberPadding", value: 8, label: "Line numbers: padding (pt)", help: "space left and right of the line numbers", tab: "Editor"),
        Item(key: "statusBar", value: 1, label: "Show status bar", help: "1 = show the status bar at the bottom of the window", tab: "Status bar", kind: .flag),
        Item(key: "statusLines", value: 1, label: "Lines", help: "1 = show the number of lines", tab: "Status bar", kind: .flag),
        Item(key: "statusCharacters", value: 1, label: "Characters", help: "1 = show the number of characters (UTF-16 units: an emoji counts as two)", tab: "Status bar", kind: .flag),
        Item(key: "statusLocation", value: 1, label: "Location", help: "1 = show the caret's offset from the start of the text", tab: "Status bar", kind: .flag),
        Item(key: "statusLine", value: 1, label: "Line", help: "1 = show the caret's line number", tab: "Status bar", kind: .flag),
        Item(key: "statusSize", value: 1, label: "File size", help: "1 = show the size of the file on disk", tab: "Status bar", kind: .flag),
        Item(key: "statusEncoding", value: 1, label: "Encoding", help: "1 = show the text encoding the file was read in", tab: "Status bar", kind: .flag),
        Item(key: "statusLineEnding", value: 1, label: "Line ending", help: "1 = show the line ending of the file (LF, CRLF or CR)", tab: "Status bar", kind: .flag),
        Item(key: "statusDelayMs", value: 250, label: "Pause before counting (ms)", help: "pause after an edit before the lines of a big text are counted again", tab: "Performance"),
        Item(key: "statusSliceChars", value: 1000000, label: "Counting slice (characters)", help: "characters counted per step; a text up to this size is counted at once, a bigger one in steps between key presses", tab: "Performance"),
        Item(key: "fontSize", value: 13, label: "Font size", help: "editor font size in points", tab: "Editor"),
        Item(key: "wrapLines", value: 1, label: "Wrap long lines", help: "1 = wrap long lines, 0 = scroll sideways", tab: "Editor", kind: .flag),
        Item(key: "spellCheck", value: 0, label: "Check spelling while typing", help: "1 = check spelling while typing", tab: "Editor", kind: .flag),
        Item(key: "textKit", value: 2, label: "Text engine", help: "text engine: 2 (system default, fast on huge pastes and jumps) or 1 (older, non-contiguous layout)", tab: "Editor", kind: .choice([2, 1]), live: false),
        Item(key: "themeCanvas", value: 1, label: "Theme sets text and background", help: "1 = the theme also sets the text, background, caret and selection colours; 0 = only the syntax colours", tab: "Colours", kind: .flag),
        Item(key: "highlightMarginLines", value: 150, label: "Coloured lines beyond the screen", help: "lines coloured above and below the visible text", tab: "Performance"),
        Item(key: "highlightDelayMs", value: 120, label: "Pause after typing (ms)", help: "pause after typing before the visible text is recoloured", tab: "Performance"),
        Item(key: "scrollDelayMs", value: 20, label: "Pause after scrolling (ms)", help: "pause after scrolling out of the coloured range before it is recoloured", tab: "Performance"),
        Item(key: "highlightMaxMB", value: 0, label: "Colours off above (MB)", help: "above this size the colours are off (0 = never)", tab: "Performance"),
        Item(key: "toolCacheSeconds", value: 600, label: "Remember the tools found for (s)", help: "how long the pdfmd found on this Mac (and pandoc) is remembered before the shell is asked again; the command line (colophon render) and the app share the answer", tab: "General"),
        Item(key: "quitAfterLastWindow", value: 0, label: "Quit when the last window closes", help: "1 = closing the last window quits the app (the Windows way); 0 = the app stays open and the Dock icon opens a new window (the Mac way). A launch from the command line (pdfmd --editor) always quits, because the command waits for it", tab: "General", kind: .flag),
        Item(key: "htmlOpenAs", value: 0, label: "Open .html files as", help: "0 = the web page (View > Show Source opens the code), 1 = text, in an editor window", tab: "HTML", kind: .choice([0, 1])),
        Item(key: "htmlAutoReload", value: 1, label: "Reload when the file changes", help: "1 = an HTML window shows a rewritten file by itself (same place on the page); 0 = it only says \"file changed\" and waits for View > Reload (command R)", tab: "HTML", kind: .flag),
        Item(key: "htmlReloadDebounceMs", value: 300, label: "Reload pause (ms)", help: "when the HTML file changes on disk it is shown again after it has stayed unchanged for this long", tab: "HTML"),
        Item(key: "htmlCoverMs", value: 150, label: "Keep the old page for (ms)", help: "after a reload the old picture of the page stays on the screen this long after the new one has loaded (0 = at once: the page may blink)", tab: "HTML"),
        Item(key: "htmlZoomStepPercent", value: 10, label: "Zoom step (%)", help: "each Zoom In or Zoom Out changes the size of the page by this many percent", tab: "HTML"),
        Item(key: "startupWindow", value: 0, label: "A new editor window starts as", help: "0 = the plain editor; 1 = the studio: the editor with the preview beside the text (slower to open and to type in: pandoc runs after every pause in the typing)", tab: "Studio", kind: .choice([0, 1])),
        Item(key: "studioPaneMode", value: 0, label: "The preview shows", help: "0 = the HTML page (pandoc, fast, follows the typing); 1 = the PDF of the last build (command R). The pane's switch sets it", tab: "Studio", kind: .choice([0, 1])),
        Item(key: "studioPreviewDelayMs", value: 300, label: "Pause before the preview updates (ms)", help: "the HTML preview is made again after the typing has paused this long", tab: "Studio"),
        Item(key: "studioFollow", value: 1, label: "Preview follows the text", help: "1 = the preview scrolls to the same fraction of the page as the text (the heights differ, so it is near, not exact)", tab: "Studio", kind: .flag),
        Item(key: "studioScrollDelayMs", value: 80, label: "Pause before the preview follows a scroll (ms)", help: "the preview follows the text's scrolling after it has paused this long", tab: "Studio"),
        Item(key: "studioRenderTimeout", value: 20, label: "Stop pandoc after (s)", help: "a preview that takes longer than this is stopped (a filter that hangs); 0 = never", tab: "Studio"),
        Item(key: "studioPaneWidth", value: 520, label: "Preview width (pt)", help: "the width of the preview when it opens; it is set to the width the pane had when it was last hidden", tab: "Studio"),
        Item(key: "studioMinEditorWidth", value: 300, label: "Least width of the text (pt)", help: "the divider cannot be dragged to make the text narrower than this", tab: "Studio"),
        Item(key: "studioMinPaneWidth", value: 200, label: "Least width of the preview (pt)", help: "the divider cannot be dragged to make the preview narrower than this", tab: "Studio"),
        Item(key: "studioServerTimeout", value: 30, label: "Wait for the studio's server (s)", help: "the web studio starts `pdfmd --serve` for its folder and waits this long for it to say where it listens; then it gives up and shows why", tab: "Studio"),
        Item(key: "reloadOnDiskChange", value: 1, label: "Follow a file that another program changes", help: "1 = an editor window shows a file again when another program rewrites it (at once when you have not edited it; when you have, it asks which version to keep); 0 = the window keeps what it has until you revert", tab: "Editor", kind: .flag),
        Item(key: "diskChangeDelayMs", value: 150, label: "Pause before a changed file is read again (ms)", help: "a program that writes a file in several steps is waited for this long, so that it is read once", tab: "Editor"),
        Item(key: "buildTimeout", value: 600, label: "Stop a build after (s)", help: "a build (command R in an editor window) that has not ended after this many seconds is stopped, with everything it started; 0 = never", tab: "Build"),
        Item(key: "buildStopGrace", value: 3, label: "Build stop grace (s)", help: "positive seconds to wait before forcing a stopped build to end, and to drain its output after it ends; also used for tool discovery; invalid values use the default", tab: "Build"),
        Item(key: "buildOpensPDF", value: 1, label: "Open the PDF after a build", help: "1 = a build whose PDF is not open yet opens it in a window (the editor keeps the keyboard); a PDF that is open is always shown again", tab: "Build", kind: .flag),
        Item(key: "buildWhenWatched", value: 0, label: "Build although pdfmd is watching", help: "0 = when a pdfmd --watch (pdfmd -w, or the one that pdfmd --edit --editor starts) is already rebuilding this file on every save, command R only saves; 1 = build as well", tab: "Build", kind: .flag),
        Item(key: "exportReveal", value: 0, label: "Show the exported file in Finder", help: "1 = File > Export As shows the new file in Finder when it is done (Finder then takes the keyboard); 0 = only the window's subtitle says it", tab: "Build", kind: .flag),
        Item(key: "pdfAutoReload", value: 1, label: "Reload when the file changes", help: "1 = a PDF window shows a rewritten file by itself (same page and zoom); 0 = it only says \"file changed\" and waits for View > Reload (command R)", tab: "PDF", kind: .flag),
        Item(key: "pdfThumbnails", value: 1, label: "Show thumbnails", help: "1 = show the page thumbnails in a sidebar", tab: "PDF", kind: .flag),
        Item(key: "pdfSidebarMode", value: 0, label: "Sidebar shows", help: "0 = page thumbnails, 1 = the table of contents (outline)", tab: "PDF", kind: .choice([0, 1])),
        Item(key: "pdfThumbnailWidth", value: 130, label: "Thumbnail width (pt)", help: "width of a page thumbnail in the sidebar when it has not been dragged to another width", tab: "PDF"),
        Item(key: "pdfSidebarWidth", value: 0, label: "Sidebar width (pt)", help: "the width the sidebar was last dragged to; 0 = the width that the thumbnail width gives (double-click the divider, or View > Reset Sidebar Width, sets it to 0)", tab: "PDF"),
        Item(key: "pdfPageSideGutterPt", value: 0, label: "Gap beside the pages (pt)", help: "the dark gap left and right of the pages (PDFKit's own is about 4); 0 puts the page against the sidebar's divider line when it fills the width", tab: "PDF"),
        Item(key: "pdfDividerGrabPt", value: 8, label: "Sidebar divider: grab width (pt)", help: "how wide the strip is that catches the mouse to resize the sidebar (the line drawn stays thin)", tab: "PDF"),
        Item(key: "pdfContentsOpenLevels", value: 2, label: "Contents: levels shown", help: "levels of the table of contents open when a file is opened: 1 = only the top entries, 2 = their children too", tab: "PDF"),
        Item(key: "pdfOpenFit", value: 0, label: "Zoom when a file is opened", help: "0 = fit the page's width, 1 = fit the whole page, 2 = actual size (100%)", tab: "PDF", kind: .choice([0, 1, 2])),
        Item(key: "pdfDisplayMode", value: 1, label: "Page layout", help: "1 = pages one below the other, 0 = one page at a time, 3 = two pages side by side, scrolling, 2 = two pages side by side", tab: "PDF", kind: .choice([1, 0, 3, 2])),
        Item(key: "pdfZoomStepPercent", value: 25, label: "Zoom step (%)", help: "each Zoom In or Zoom Out changes the size by this many percent", tab: "PDF"),
        Item(key: "pdfZoomMinPercent", value: 10, label: "Smallest zoom (%)", help: "the page cannot be shown smaller than this", tab: "PDF"),
        Item(key: "pdfZoomMaxPercent", value: 1600, label: "Largest zoom (%)", help: "the page cannot be shown larger than this", tab: "PDF"),
        Item(key: "pdfInterpolation", value: 1, label: "Picture smoothing", help: "how pictures are scaled: 0 = none (fastest), 1 = low, 2 = high (slowest when zoomed)", tab: "PDF", kind: .choice([1, 0, 2])),
        Item(key: "pdfReloadDebounceMs", value: 400, label: "Reload pause (ms)", help: "when the PDF file changes on disk it is shown again after it has stayed unchanged for this long", tab: "PDF"),
        Item(key: "pdfReloadCoverMs", value: 400, label: "Keep the old pages for (ms)", help: "after a reload the old pages stay on the screen this long while the new ones draw themselves underneath (0 = replace at once: the pages blink)", tab: "PDF"),
        Item(key: "pdfReloadRetries", value: 40, label: "Reload attempts", help: "how many times a file that is still being written is looked at again before it is given up until the next change", tab: "PDF"),
        Item(key: "popMenuBar", value: 0, label: "Keep running in the menu bar", help: "1 = a menu-bar icon and the global shortcut open the equation popup from any app, and Colophon stays running when its last window is closed (a shortcut that another app holds is reported in the icon's menu)", tab: "Popup", kind: .flag),
        Item(key: "popLaunchAtLogin", value: 0, label: "Start at login", help: "1 = Colophon starts when you log in (use it with the menu-bar icon); applies while Colophon runs and at its next launch", tab: "Popup", kind: .flag),
        Item(key: "popNoStartWindow", value: 0, label: "No window at start", help: "1 = with the menu-bar icon on, Colophon starts without opening an untitled editor window (it also never opens one when it was started as a login item, whatever this says)", tab: "Popup", kind: .flag, live: false),
        Item(key: "popLive", value: 1, label: "Render while typing", help: "1 = the popup renders after a pause in the typing; 0 = only with command R or command return (pdfmd documents never render while typing: they take seconds)", tab: "Popup", kind: .flag),
        Item(key: "popHideAfterCopy", value: 1, label: "Hide after copying", help: "1 = the popup closes after command return and gives the focus back to the app you came from", tab: "Popup", kind: .flag),
        Item(key: "popPreviewAbove", value: 1, label: "Preview above the editor", help: "1 = the result is on top, as in LaTeXiT; 0 = below the editor", tab: "Popup", kind: .flag),
        Item(key: "popLineNumbers", value: 1, label: "Line numbers in the popup", help: "1 = a line-number margin in the popup's editors", tab: "Popup", kind: .flag),
        Item(key: "popPreambleShown", value: 0, label: "Show the preamble pane", help: "1 = the popup shows its preamble (and, for pdfmd, its metadata) above the editor", tab: "Popup", kind: .flag),
        Item(key: "popRenderDelayMs", value: 400, label: "Pause before rendering (ms)", help: "the popup renders after the typing has paused this long", tab: "Popup"),
        Item(key: "popPreambleDelayMs", value: 600, label: "Pause after a preamble edit (ms)", help: "the popup renders after an edit of the preamble or the metadata has paused this long", tab: "Popup"),
        Item(key: "popTimeoutS", value: 30, label: "TeX time limit (s)", help: "a TeX run that takes longer is stopped", tab: "Popup"),
        Item(key: "popPdfmdTimeoutS", value: 120, label: "pdfmd time limit (s)", help: "a pdfmd run of the popup that takes longer is stopped", tab: "Popup"),
        Item(key: "popFormatTimeoutS", value: 60, label: "Preamble cache time limit (s)", help: "compiling the preamble into a cached TeX format (pdflatex) is stopped after this long", tab: "Popup"),
        Item(key: "popFormatKeep", value: 6, label: "Cached preambles kept", help: "how many compiled preambles (about 9 MB each) are kept; the oldest go first", tab: "Popup"),
        Item(key: "popBorderPt", value: 2, label: "Border of the snippet (pt)", help: "the border that LaTeX's standalone class leaves around the snippet", tab: "Popup"),
        Item(key: "popMaxWidthCm", value: 16, label: "Widest line (cm)", help: "the width at which the text of a snippet wraps (standalone's varwidth)", tab: "Popup"),
        Item(key: "popCropPadPt", value: 2, label: "Padding after cropping (pt)", help: "what is left around the ink when the page is cropped to it", tab: "Popup"),
        Item(key: "popPdfmdBottomPt", value: 66, label: "pdfmd page number strip (pt)", help: "the strip at the bottom of a pdfmd page that is left out when cropping, because it holds the page number", tab: "Popup"),
        Item(key: "popPngScale", value: 4, label: "PNG pixels per point", help: "the copied PNG is drawn at this scale (4 = 288 dpi)", tab: "Popup"),
        Item(key: "popErrorsListed", value: 30, label: "Errors listed", help: "at most this many errors of a failed run are listed", tab: "Popup"),
        Item(key: "popPdfmdLines", value: 6, label: "pdfmd lines shown as errors", help: "when pdfmd fails, this many of its last lines are listed", tab: "Popup"),
        Item(key: "popWidth", value: 520, label: "Window width (pt)", help: "the width of the popup the first time it opens (after that it opens as you left it)", tab: "Popup", live: false),
        Item(key: "popHeight", value: 520, label: "Window height (pt)", help: "the height of the popup the first time it opens, without the preamble pane", tab: "Popup", live: false),
        Item(key: "popPaneHeight", value: 156, label: "Preamble pane height (pt)", help: "the height of the preamble pane; the window grows by this much when the pane opens", tab: "Popup"),
        Item(key: "popEditorHeight", value: 110, label: "Editor height (pt)", help: "the height of the popup's text editor", tab: "Popup", live: false),
        Item(key: "popPreviewMinHeight", value: 120, label: "Preview minimum height (pt)", help: "the preview never gets smaller than this when the window is made smaller", tab: "Popup", live: false),
        Item(key: "popInkScale", value: 4, label: "Crop measuring scale (px per pt)", help: "the page is drawn at this many pixels per point to find where the ink is; more is more exact and slower", tab: "Popup"),
        Item(key: "popLogLookahead", value: 12, label: "Error line look-ahead (lines)", help: "after a TeX error the line number (l.N) is looked for in this many lines of the log", tab: "Popup"),
        Item(key: "popWarmWaitS", value: 60, label: "colophon eq --warm waits at most (s)", help: "with --warm the command waits for the cached preamble to finish, this long at most", tab: "Popup"),
    ]

    enum TextKind {
        case free
        case themes
        case fonts
        case options([String])   // one of these words
        case hotkey              // a keyboard shortcut: ⌥⇧T, option+shift+t, or none
    }

    struct Text {
        let key: String
        let value: String
        let label: String
        let help: String
        let tab: String
        var kind: TextKind = .free
    }

    static let texts: [Text] = [
        Text(key: "pdfmdCommand", value: "", label: "pdfmd command", help: "the command that runs pdfmd, as typed in a shell (for example python3 ~/dev/py/pdfmd/pdfmd.py); empty = the newest pdfmd that the shell knows (the terminal's alias and every pdfmd on its PATH). The About box shows which one is used", tab: "General"),
        Text(key: "keySwitchMode", value: "⌃⌘S", label: "Shortcut: plain text ⇄ studio", help: "the menu shortcut (Window > Switch to Studio / Switch to Plain Text) that goes from the editor windows to the web studio and back: symbols (⌃⌘S) or words (ctrl+cmd+s), with Control, Option or Command; none = no shortcut. A key that another menu item uses is refused", tab: "General", kind: .hotkey),
        Text(key: "buildArguments", value: "", label: "pdfmd options for a build", help: "words added to the pdfmd command that command R runs, as typed in a shell (for example --engine typst, or -t html to build something else; the file is added last). File > Export As uses them too, without any -t or -o of yours (it writes its own). Empty = pdfmd's own defaults, including the folder's pdfmd --setup", tab: "Build"),
        Text(key: "pandocCommand", value: "", label: "pandoc for the preview", help: "the path of the pandoc that makes the HTML preview; empty = the first pandoc on the login shell's PATH", tab: "Studio"),
        Text(key: "htmlPreviewArguments", value: "", label: "pandoc options for the preview", help: "words added to the pandoc command of the preview, as typed in a shell (for example --citeproc --number-sections, or --lua-filter ~/x.lua); the page is made from the text of the window, in its folder", tab: "Studio"),
        Text(key: "htmlPreviewCSS", value: "", label: "Style sheet for the preview", help: "the path of a .css file that is added to the preview's own style (empty = none)", tab: "Studio"),
        Text(key: "newFileName", value: "Untitled", label: "Name of a new document", help: "what a new, unsaved document is called (its window's title, and the name the save panel proposes: a second one is “name 2”). Empty = Untitled", tab: "Editor"),
        Text(key: "newFileExtension", value: "md", label: "Extension of a new document", help: "the extension a new document gets when it is saved, with or without the dot (md, txt, tex ...); the save panel shows it after the name, with the name selected so typing replaces the name only. A name typed with another extension keeps it. none = no extension; empty = md", tab: "Editor"),
        Text(key: "fontName", value: "JetBrains Mono", label: "Font", help: "editor font: a font family (monospaced fonts are listed by --fonts); if it is not installed the system monospaced font is used", tab: "Editor", kind: .fonts),
        Text(key: "theme", value: "Anura", label: "Theme (light appearance)", help: "colour theme in a light appearance: the name of a .cottheme file (CotEditor's format), see --themes", tab: "Colours", kind: .themes),
        Text(key: "popHotkey", value: "⌥⇧T", label: "Shortcut", help: "the global shortcut that opens the popup while Colophon keeps running in the menu bar: symbols (⌥⇧T) or words (option+shift+t), with Control, Option or Command; none = no shortcut", tab: "Popup", kind: .hotkey),
        Text(key: "popMode", value: "display", label: "Snippet is", help: "what a LaTeX snippet is set as: display (display math), inline (inline math) or text (LaTeX text)", tab: "Popup", kind: .options(["display", "inline", "text"])),
        Text(key: "popEngine", value: "pdflatex", label: "Engine", help: "pdflatex, lualatex or xelatex for LaTeX snippets; pdfmd for a Markdown snippet (math, tables, anything pdfmd builds)", tab: "Popup", kind: .options(["pdflatex", "lualatex", "xelatex", "pdfmd"])),
        Text(key: "popPdfmdEngine", value: "auto", label: "pdfmd's engine", help: "pdfmd's own -e for the pdfmd engine: auto leaves the choice to pdfmd (typst takes about a second, pdflatex four, lualatex ten)", tab: "Popup", kind: .options(["auto", "tex", "lualatex", "pdflatex", "xelatex", "typst", "html"])),
        Text(key: "pdfFindColor", value: "#FFEB3B", label: "Colour of the found text", help: "the colour (#RRGGBB) that the matches of a search are marked with in a PDF", tab: "PDF"),
        Text(key: "themeDark", value: "Anura (Dark)", label: "Theme (dark appearance)", help: "colour theme in a dark appearance", tab: "Colours", kind: .themes),
    ]

    static func number(_ key: String) -> Double {
        if let n = store.object(forKey: key) as? NSNumber { return n.doubleValue }
        return items.first { $0.key == key }!.value
    }

    static func int(_ key: String) -> Int { Int(number(key)) }
    static func flag(_ key: String) -> Bool { number(key) != 0 }

    static func string(_ key: String) -> String {
        if let s = store.string(forKey: key), !s.isEmpty { return s }
        return texts.first { $0.key == key }!.value
    }

    /// Writes a setting (a number, a string or nil to remove it), re-reads the theme and tells the open editors.
    static func set(_ key: String, _ value: Any?) {
        if let value { store.set(value, forKey: key) } else { store.removeObject(forKey: key) }
        Palette.reload()
        NotificationCenter.default.post(name: changed, object: nil)
    }

    static func remove(_ keys: [String]) {
        for k in keys { store.removeObject(forKey: k) }
        Palette.reload()
        NotificationCenter.default.post(name: changed, object: nil)
    }

    static func listing() -> String {
        let pad = { (s: String) in s.padding(toLength: 22, withPad: " ", startingAt: 0) }
        let numbers = items.map { item -> String in
            let now = number(item.key)
            return "\(pad(item.key)) \(Int(item.value))\(now == item.value ? "" : "  (now \(now))")  \(item.help)"
        }
        let words = texts.map { t -> String in
            let now = string(t.key)
            return "\(pad(t.key)) \(t.value)\(now == t.value ? "" : "  (now \(now))")  \(t.help)"
        }
        return (numbers + words).joined(separator: "\n")
    }
}
