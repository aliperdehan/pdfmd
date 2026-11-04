import Foundation

let appVersion = "0.2.6"

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
        Item(key: "quitAfterLastWindow", value: 0, label: "Quit when the last window closes", help: "1 = closing the last window quits the app (the Windows way); 0 = the app stays open and the Dock icon opens a new window (the Mac way). A launch from the command line (pdfmd --editor) always quits, because the command waits for it", tab: "General", kind: .flag),
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
        Item(key: "frontMatterScanChars", value: 20000, label: "Front matter scan (characters)", help: "how far from the top the closing --- of a YAML front matter is looked for", tab: "Performance"),
    ]

    enum TextKind {
        case free
        case themes
        case fonts
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
        Text(key: "fontName", value: "JetBrains Mono", label: "Font", help: "editor font: a font family (monospaced fonts are listed by --fonts); if it is not installed the system monospaced font is used", tab: "Editor", kind: .fonts),
        Text(key: "theme", value: "Anura", label: "Theme (light appearance)", help: "colour theme in a light appearance: the name of a .cottheme file (CotEditor's format), see --themes", tab: "Colours", kind: .themes),
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
