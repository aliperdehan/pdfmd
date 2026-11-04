import Cocoa

struct EditorParts {
    let scroll: NSScrollView
    let textView: NSTextView
    let highlighter: Highlighter?
}

/// The editor font: the `fontName` family at `fontSize`; the system monospaced font when that family is not installed.
func editorFont() -> NSFont {
    let size = CGFloat(Settings.number("fontSize"))
    let name = Settings.string("fontName")
    if let f = NSFontManager.shared.font(withFamily: name, traits: [], weight: 5, size: size), f.familyName == name { return f }
    if let f = NSFont(name: name, size: size) { return f }
    return NSFont.monospacedSystemFont(ofSize: size, weight: .regular)
}

/// Installed font families that are monospaced, for `--fonts`.
func monospacedFamilies() -> [String] {
    NSFontManager.shared.availableFontFamilies.filter { family in
        NSFontManager.shared.font(withFamily: family, traits: [], weight: 5, size: 13)?.isFixedPitch ?? false
    }
}

/// One editor: an NSTextView on an explicit TextKit 1 stack (storage, layout manager, container), because
/// TextKit 1 has non-contiguous layout (only the lines near the screen are laid out) and layout-manager
/// temporary attributes; TextKit 2 (the system default, setting `textKit`) lays out only the viewport and
/// takes the colours as rendering attributes. The colouring supports both; the benchmark compares them.
func makeEditor(frame: NSRect, highlight: Bool, textKit2: Bool = Settings.int("textKit") == 2) -> EditorParts {
    let font = editorFont()
    let scroll: NSScrollView
    let tv: NSTextView
    if textKit2 {
        scroll = NSTextView.scrollableTextView()
        tv = scroll.documentView as! NSTextView
        scroll.frame = frame
    } else {
        let storage = NSTextStorage()
        let layout = NSLayoutManager()
        layout.allowsNonContiguousLayout = true
        storage.addLayoutManager(layout)
        let container = NSTextContainer(size: NSSize(width: frame.width, height: CGFloat.greatestFiniteMagnitude))
        layout.addTextContainer(container)
        tv = NSTextView(frame: NSRect(origin: .zero, size: frame.size), textContainer: container)
        scroll = NSScrollView(frame: frame)
        scroll.documentView = tv
        scroll.hasVerticalScroller = true
        tv.minSize = NSSize(width: 0, height: frame.height)
        tv.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        tv.isVerticallyResizable = true
        tv.autoresizingMask = [.width]
    }
    scroll.autoresizingMask = [.width, .height]
    scroll.borderType = .noBorder

    tv.isRichText = false
    tv.importsGraphics = false
    tv.allowsUndo = true
    tv.usesFindBar = true
    tv.isIncrementalSearchingEnabled = true
    tv.font = font
    applyCanvas(tv, scroll)
    tv.textContainerInset = NSSize(width: 10, height: 8)
    tv.isAutomaticQuoteSubstitutionEnabled = false
    tv.isAutomaticDashSubstitutionEnabled = false
    tv.isAutomaticTextReplacementEnabled = false
    tv.isAutomaticSpellingCorrectionEnabled = false
    tv.isAutomaticLinkDetectionEnabled = false
    tv.isAutomaticDataDetectionEnabled = false
    tv.smartInsertDeleteEnabled = false
    tv.isContinuousSpellCheckingEnabled = Settings.flag("spellCheck")
    tv.isGrammarCheckingEnabled = false
    setWrap(Settings.flag("wrapLines"), tv, scroll)

    if textKit2 {   // anything that touches `layoutManager` silently switches the view to TextKit 1: say so
        NotificationCenter.default.addObserver(forName: NSTextView.willSwitchToNSLayoutManagerNotification, object: tv, queue: nil) { _ in
            FileHandle.standardError.write(Data("pdfmdedit: the text view fell back to TextKit 1\n".utf8))
        }
    }
    let highlighter = highlight ? Highlighter(tv) : nil
    return EditorParts(scroll: scroll, textView: tv, highlighter: highlighter)
}

/// The theme's text, background, caret and selection colours (the system's when `themeCanvas` is 0 or no theme is found).
func applyCanvas(_ tv: NSTextView, _ scroll: NSScrollView) {
    tv.textColor = Palette.text
    tv.backgroundColor = Palette.background
    tv.drawsBackground = true
    tv.insertionPointColor = Palette.insertionPoint
    tv.selectedTextAttributes = [.backgroundColor: Palette.selection ?? .selectedTextBackgroundColor]
    scroll.backgroundColor = Palette.background
    scroll.drawsBackground = true
}

func setWrap(_ wrap: Bool, _ tv: NSTextView, _ scroll: NSScrollView) {
    guard let container = tv.textContainer else { return }
    scroll.hasHorizontalScroller = !wrap
    tv.isHorizontallyResizable = !wrap
    container.widthTracksTextView = wrap
    if wrap {
        container.size = NSSize(width: scroll.contentSize.width, height: CGFloat.greatestFiniteMagnitude)
        tv.autoresizingMask = [.width]
    } else {
        container.size = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        tv.autoresizingMask = []
    }
}

// MARK: document and window

@objc(EditorDocument)
final class EditorDocument: NSDocument {
    var text = ""
    var encoding: String.Encoding = .utf8
    var lineEnding: (name: String, unit: unichar) = ("LF", 10)
    var controller: EditorWindowController?

    override class var autosavesInPlace: Bool { true }
    override class var readableTypes: [String] { ["Markdown and text"] }
    override class var writableTypes: [String] { ["Markdown and text"] }
    override class func canConcurrentlyReadDocuments(ofType typeName: String) -> Bool { false }

    override func makeWindowControllers() {
        let c = EditorWindowController(document: self)
        addWindowController(c)
        controller = c
    }

    override func read(from data: Data, ofType typeName: String) throws {
        lineEnding = detectLineEnding(data)
        if let s = String(data: data, encoding: .utf8) {
            text = s; encoding = .utf8
        } else if let s = String(data: data, encoding: .isoLatin1) {
            text = s; encoding = .isoLatin1
        } else {
            throw NSError(domain: NSCocoaErrorDomain, code: NSFileReadInapplicableStringEncodingError)
        }
        controller?.load(text, document: self)   // a revert: the window exists already
    }

    override func save(to url: URL, ofType typeName: String, for saveOperation: NSDocument.SaveOperationType, completionHandler: @escaping (Error?) -> Void) {
        super.save(to: url, ofType: typeName, for: saveOperation) { [weak self] error in
            completionHandler(error)
            self?.controller?.statusBar.refresh()   // the size on disk changed
        }
    }

    override func data(ofType typeName: String) throws -> Data {
        let s = controller?.currentString() ?? text
        guard let d = s.data(using: encoding) else { throw NSError(domain: NSCocoaErrorDomain, code: NSFileWriteInapplicableStringEncodingError) }
        return d
    }

    override func fileNameExtension(forType typeName: String, saveOperation: NSDocument.SaveOperationType) -> String? {
        fileURL?.pathExtension.isEmpty == false ? fileURL!.pathExtension : "md"
    }
}

/// The window's content: the editor above, the status bar below (a height of 0 when it is hidden).
final class EditorContent: NSView {
    var editor: NSView!
    var bar: StatusBar!

    func place() {
        let h = bar.isHidden ? 0 : StatusBar.height
        bar.frame = NSRect(x: 0, y: 0, width: bounds.width, height: h)
        editor.frame = NSRect(x: 0, y: h, width: bounds.width, height: max(0, bounds.height - h))
    }

    override func resizeSubviews(withOldSize oldSize: NSSize) {
        super.resizeSubviews(withOldSize: oldSize)
        place()
    }
}

final class EditorWindowController: NSWindowController, NSMenuItemValidation {
    private(set) var parts: EditorParts!
    private(set) var statusBar: StatusBar!
    private(set) var stats: TextStats!
    private(set) var content: EditorContent!
    private(set) var ruler: LineNumberRuler!
    let builder = BuildController()

    init(document: EditorDocument) {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 700),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("pdfmdedit.window")
        super.init(window: window)
        shouldCascadeWindows = true
        content = EditorContent(frame: window.contentLayoutRect)
        parts = makeEditor(frame: content.bounds, highlight: true)
        statusBar = StatusBar(frame: .zero)
        stats = TextStats(parts.textView)
        statusBar.attach(stats)
        ruler = LineNumberRuler(scroll: parts.scroll, textView: parts.textView, stats: stats)
        parts.scroll.verticalRulerView = ruler
        parts.scroll.hasVerticalRuler = true
        statusBar.fileURL = document.fileURL
        content.editor = parts.scroll
        content.bar = statusBar
        content.addSubview(parts.scroll)
        content.addSubview(statusBar)
        window.contentView = content
        window.initialFirstResponder = parts.textView
        showStatusBar()
        showLineNumbers()
        load(document.text, document: document)
        NotificationCenter.default.addObserver(self, selector: #selector(settingsChanged), name: Settings.changed, object: nil)
        builder.owner = self
        NotificationCenter.default.addObserver(forName: NSText.didChangeNotification, object: parts.textView, queue: .main) { [weak self] _ in
            self?.builder.textEdited()
        }
    }

    deinit { NotificationCenter.default.removeObserver(self) }

    /// A setting was changed in the Preferences window: apply what can be applied to this open window (the text engine cannot).
    @objc func settingsChanged() {
        let tv = parts.textView
        let font = editorFont()
        if tv.font != font { tv.font = font }
        applyCanvas(tv, parts.scroll)
        setWrap(Settings.flag("wrapLines"), tv, parts.scroll)
        tv.isContinuousSpellCheckingEnabled = Settings.flag("spellCheck")
        statusBar.applyColours()
        showStatusBar()
        showLineNumbers()
        parts.highlighter?.highlightNow()
        tv.needsDisplay = true
    }

    private func showLineNumbers() {
        parts.scroll.rulersVisible = Settings.flag("lineNumbers")
        ruler.applySettings()
    }

    private func showStatusBar() {
        statusBar.isHidden = !Settings.flag("statusBar")
        statusBar.refresh()
        content.place()
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    func load(_ text: String, document: EditorDocument) {
        statusBar.encodingName = encodingDisplayName(document.encoding)
        statusBar.lineEndingName = document.lineEnding.name
        statusBar.fileURL = document.fileURL
        stats.lineBreak = document.lineEnding.unit
        parts.textView.string = text
        stats.reset()
        ruler.reset()
        parts.textView.setSelectedRange(NSRange(location: 0, length: 0))
        parts.textView.undoManager?.removeAllActions()
        parts.highlighter?.highlightNow()
    }

    func currentString() -> String { parts.textView.textStorage?.string ?? "" }

    override func showWindow(_ sender: Any?) {
        super.showWindow(sender)
        window?.makeFirstResponder(parts.textView)
    }

    @objc func toggleLineNumbers(_ sender: Any?) {
        Settings.set("lineNumbers", Settings.flag("lineNumbers") ? 0 : 1)
    }

    @objc func toggleStatusBar(_ sender: Any?) {
        Settings.set("statusBar", Settings.flag("statusBar") ? 0 : 1)
    }

    /// Command R in an editor window: save, run pdfmd, show the PDF (in a PDF window the same menu item reloads the file).
    @objc func reloadFile(_ sender: Any?) { builder.request() }
    @objc func showBuildLog(_ sender: Any?) { builder.showLog() }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        if item.action == #selector(reloadFile(_:)) { item.title = "Build PDF" }
        if item.action == #selector(showBuildLog(_:)) { return builder.hasLog }
        if item.action == #selector(toggleLineNumbers(_:)) { item.title = Settings.flag("lineNumbers") ? "Hide Line Numbers" : "Show Line Numbers" }
        if item.action == #selector(toggleStatusBar(_:)) { item.title = Settings.flag("statusBar") ? "Hide Status Bar" : "Show Status Bar" }
        return true
    }

    @objc func toggleWrap(_ sender: Any?) {
        Settings.set("wrapLines", Settings.flag("wrapLines") ? 0 : 1)   // every open window follows (settingsChanged)
    }
}

/// Opens anything the author points it at, not only the types the Info.plist names.
final class DocController: NSDocumentController {
    override var defaultType: String? { "Markdown and text" }
    override func typeForContents(of url: URL) throws -> String { isPDFFile(url) ? "PDF document" : "Markdown and text" }
    override func documentClass(forType typeName: String) -> AnyClass? { typeName == "PDF document" ? PDFViewerDocument.self : EditorDocument.self }
    override func runModalOpenPanel(_ openPanel: NSOpenPanel, forTypes types: [String]?) -> Int {
        super.runModalOpenPanel(openPanel, forTypes: nil)
    }
}
