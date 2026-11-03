import Cocoa

struct EditorParts {
    let scroll: NSScrollView
    let textView: NSTextView
    let highlighter: Highlighter?
}

/// One editor: an NSTextView on an explicit TextKit 1 stack (storage, layout manager, container), because
/// TextKit 1 has non-contiguous layout (only the lines near the screen are laid out) and layout-manager
/// temporary attributes; TextKit 2 (the system default, setting `textKit`) lays out only the viewport and
/// takes the colours as rendering attributes. The colouring supports both; the benchmark compares them.
func makeEditor(frame: NSRect, highlight: Bool, textKit2: Bool = Settings.int("textKit") == 2) -> EditorParts {
    let font = NSFont.monospacedSystemFont(ofSize: CGFloat(Settings.number("fontSize")), weight: .regular)
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
    tv.textColor = .textColor
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
        if let s = String(data: data, encoding: .utf8) {
            text = s; encoding = .utf8
        } else if let s = String(data: data, encoding: .isoLatin1) {
            text = s; encoding = .isoLatin1
        } else {
            throw NSError(domain: NSCocoaErrorDomain, code: NSFileReadInapplicableStringEncodingError)
        }
        controller?.load(text)   // a revert: the window exists already
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

final class EditorWindowController: NSWindowController {
    private(set) var parts: EditorParts!

    init(document: EditorDocument) {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 700),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("pdfmdedit.window")
        super.init(window: window)
        shouldCascadeWindows = true
        parts = makeEditor(frame: window.contentLayoutRect, highlight: true)
        window.contentView = parts.scroll
        window.initialFirstResponder = parts.textView
        load(document.text)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    func load(_ text: String) {
        parts.textView.string = text
        parts.textView.setSelectedRange(NSRange(location: 0, length: 0))
        parts.textView.undoManager?.removeAllActions()
        parts.highlighter?.highlightNow()
    }

    func currentString() -> String { parts.textView.textStorage?.string ?? "" }

    override func showWindow(_ sender: Any?) {
        super.showWindow(sender)
        window?.makeFirstResponder(parts.textView)
    }

    @objc func toggleWrap(_ sender: Any?) {
        let now = Settings.flag("wrapLines")
        UserDefaults.standard.set(now ? 0 : 1, forKey: "wrapLines")
        setWrap(!now, parts.textView, parts.scroll)
    }
}

/// Opens anything the author points it at, not only the types the Info.plist names.
final class DocController: NSDocumentController {
    override var defaultType: String? { "Markdown and text" }
    override func typeForContents(of url: URL) throws -> String { "Markdown and text" }
    override func documentClass(forType typeName: String) -> AnyClass? { EditorDocument.self }
    override func runModalOpenPanel(_ openPanel: NSOpenPanel, forTypes types: [String]?) -> Int {
        super.runModalOpenPanel(openPanel, forTypes: nil)
    }
}
