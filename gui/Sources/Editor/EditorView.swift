import Cocoa
import UniformTypeIdentifiers

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
    /// The file is not valid UTF-8: it is shown (as Latin-1, the one reading that never fails) read-only and never saved back, as a
    /// save would silently turn a UTF-16 or Shift-JIS file into Latin-1. Reading other encodings is a later step.
    private(set) var notUTF8 = false
    private var toldNotUTF8 = false
    /// For the self-test: the error of the last failed reload, which is otherwise shown in an alert.
    static var quietErrors = false
    private(set) var lastReloadError: Error?
    var lineEnding: (name: String, unit: unichar) = ("LF", 10)
    var controller: EditorWindowController?

    override class var autosavesInPlace: Bool { true }

    // MARK: a file that another program changes

    /// For the self-test: answers the question of an edited window without a sheet (true = load the file on disk, false = keep mine).
    static var diskChoice: Bool?
    private var watcher: DiskWatcher?
    private var asking = false

    override var fileURL: URL? {
        didSet {
            guard fileURL != oldValue else { return }
            controller?.parts.highlighter?.use(fileName: fileURL?.lastPathComponent)      // a new name (Save As) can mean another syntax
            watcher?.stop(); watcher = nil
            if let url = fileURL, Settings.flag("reloadOnDiskChange") { watcher = DiskWatcher(url: url) { [weak self] in self?.diskChanged() } }
        }
    }

    /// NSFilePresenter: another program changed the file. NSDocument's own answer is not called (CotEditor does the same, and so do the PDF
    /// and HTML viewers here): it reverts an unedited document by itself, which raced the DiskWatcher's reload when `reloadOnDiskChange`
    /// is on and went against the setting when it is off ("the window keeps what it has until you revert").
    override func presentedItemDidChange() {}

    /// The file was written by someone. Our own save is no change (the same bytes); an unedited window loads the new text with its caret where it
    /// was; an edited one asks which version to keep.
    func diskChanged() {
        guard Settings.flag("reloadOnDiskChange"), let url = fileURL, !asking, let disk = try? Data(contentsOf: url) else { return }
        let mine = (try? data(ofType: "Markdown and text")) ?? Data()
        if disk == mine { fileModificationDate = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? fileModificationDate; return }
        if !isDocumentEdited { loadFromDisk(url); return }
        let choose = { [weak self] (loadIt: Bool) in
            guard let self else { return }
            self.asking = false
            if loadIt { self.updateChangeCount(.changeCleared); self.loadFromDisk(url) }
            else { self.fileModificationDate = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? self.fileModificationDate }   // kept: no second question at the save
        }
        asking = true
        if let answer = EditorDocument.diskChoice { choose(answer); return }
        let alert = NSAlert()
        alert.messageText = "“\(url.lastPathComponent)” was changed by another program."
        alert.informativeText = "This window has changes that are not saved. Keep yours (the file on disk is replaced when you save), or load the file on disk (your changes are lost)."
        alert.addButton(withTitle: "Keep Mine"); alert.addButton(withTitle: "Load the File on Disk")
        if let window = controller?.window { alert.beginSheetModal(for: window) { choose($0 == .alertSecondButtonReturn) } }
        else { choose(alert.runModal() == .alertSecondButtonReturn) }
    }

    /// Loads the file on disk into the window (the caret stays where it was). A reload that fails says why and leaves the window as it was.
    func loadFromDisk(_ url: URL) {
        let caret = controller?.parts.textView.selectedRange().location ?? 0
        do {
            try revert(toContentsOf: url, ofType: fileType ?? "Markdown and text")
            lastReloadError = nil
        } catch {
            lastReloadError = error
            if !EditorDocument.quietErrors {
                if let window = controller?.window { presentError(error, modalFor: window, delegate: nil, didPresent: nil, contextInfo: nil) }
                else { presentError(error) }
            }
            return
        }
        if let tv = controller?.parts.textView { tv.setSelectedRange(NSRange(location: min(caret, (tv.string as NSString).length), length: 0)) }
        tellNotUTF8()
    }

    override class var readableTypes: [String] { ["Markdown and text"] }
    override class var writableTypes: [String] { ["Markdown and text"] }
    override class func canConcurrentlyReadDocuments(ofType typeName: String) -> Bool { false }

    override func makeWindowControllers() {
        let c = EditorWindowController(document: self)
        addWindowController(c)
        controller = c
    }

    /// Closing an empty new document never asks whether to keep it, whatever the change count says.
    override func canClose(withDelegate delegate: Any, shouldClose shouldCloseSelector: Selector?, contextInfo: UnsafeMutableRawPointer?) {
        if fileURL == nil, isDocumentEdited, (controller?.currentString() ?? text).isEmpty { updateChangeCount(.changeCleared) }
        super.canClose(withDelegate: delegate, shouldClose: shouldCloseSelector, contextInfo: contextInfo)
    }

    override func read(from data: Data, ofType typeName: String) throws {
        lineEnding = detectLineEnding(data)
        if let s = String(data: data, encoding: .utf8) {
            text = s; encoding = .utf8; notUTF8 = false
        } else if let s = String(data: data, encoding: .isoLatin1) {
            text = s; encoding = .isoLatin1; notUTF8 = true
        } else {
            throw NSError(domain: NSCocoaErrorDomain, code: NSFileReadInapplicableStringEncodingError)
        }
        controller?.load(text, document: self)   // a revert: the window exists already
    }

    override func showWindows() {
        super.showWindows()
        tellNotUTF8()
    }

    /// Says once, in a sheet on the window, that the file is shown read-only because it is not UTF-8.
    private func tellNotUTF8() {
        guard notUTF8, !toldNotUTF8, let window = controller?.window, window.isVisible else { return }
        toldNotUTF8 = true
        let a = NSAlert()
        a.messageText = "“\(displayName ?? "This file")” is not UTF-8 text."
        a.informativeText = "It is shown read-only, read as Latin-1, so that a save cannot turn it into another encoding without a word. Other encodings are not read yet."
        a.beginSheetModal(for: window, completionHandler: nil)
    }

    /// A file that is not UTF-8 is never written back (no menu item reaches this for it; this is the last word).
    static let notUTF8Error = NSError(domain: NSCocoaErrorDomain, code: NSFileWriteInapplicableStringEncodingError, userInfo: [
        NSLocalizedDescriptionKey: "This file is not UTF-8 text, so it is open read-only and is not saved.",
        NSLocalizedRecoverySuggestionErrorKey: "Copy the text into a new document to keep a UTF-8 version of it."])

    override func validateUserInterfaceItem(_ item: NSValidatedUserInterfaceItem) -> Bool {
        let saving = [#selector(NSDocument.save(_:)), #selector(NSDocument.saveAs(_:)), #selector(NSDocument.saveTo(_:))]
        if notUTF8, let action = item.action, saving.contains(action) { return false }
        return super.validateUserInterfaceItem(item)
    }

    override func save(to url: URL, ofType typeName: String, for saveOperation: NSDocument.SaveOperationType, completionHandler: @escaping (Error?) -> Void) {
        if notUTF8 { completionHandler(EditorDocument.notUTF8Error); return }
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
        fileURL?.pathExtension.isEmpty == false ? fileURL!.pathExtension : Self.stubExtension()
    }

    // MARK: the name of a new document

    /// The name a new, unsaved document has (its window's title and the save panel's proposal): the setting `newFileName`.
    static func stubName() -> String {
        let name = Settings.string("newFileName").trimmingCharacters(in: .whitespacesAndNewlines)
        return name.isEmpty ? "Untitled" : name
    }

    /// The extension it gets when it is saved (`newFileExtension`, with or without the dot; the word none = no extension, the name is saved as typed;
    /// an empty setting is the default, md, like every text setting).
    static func stubExtension() -> String {
        let ext = Settings.string("newFileExtension").trimmingCharacters(in: CharacterSet(charactersIn: ". \t\n"))
        return ext.lowercased() == "none" ? "" : ext
    }

    /// "Untitled" and "Untitled 2" of the system, with the stub name in place of the first word.
    override var displayName: String! {
        get {
            let name: String = super.displayName
            guard fileURL == nil, name.hasPrefix("Untitled") else { return name }
            return Self.stubName() + name.dropFirst("Untitled".count)
        }
        set { super.displayName = newValue }
    }

    /// The save panel of a new document proposes `Untitled.md` with the extension showing, which the panel selects without (typing replaces
    /// `Untitled` and keeps `.md`); a name typed without an extension gets it, one typed with another (`.txt`) keeps its own.
    override func prepareSavePanel(_ panel: NSSavePanel) -> Bool {
        guard super.prepareSavePanel(panel) else { return false }
        guard fileURL == nil else { return true }
        let ext = Self.stubExtension()
        panel.allowsOtherFileTypes = true
        panel.isExtensionHidden = false
        panel.canSelectHiddenExtension = false
        if let type = ext.isEmpty ? nil : UTType(filenameExtension: ext) { panel.allowedContentTypes = [type] } else { panel.allowedContentTypes = [] }
        let base: String = displayName
        panel.nameFieldStringValue = ext.isEmpty ? base : base + "." + ext
        return true
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
    let exporter = ExportController()
    let studio = StudioController()

    init(document: EditorDocument) {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 700),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("pdfmdedit.window")
        window.tabbingIdentifier = AppDelegate.tabGroup   // File > New Tab (command T) and Window > Merge All Windows put these together
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
        parts.highlighter?.use(fileName: document.fileURL?.lastPathComponent)
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
        exporter.owner = self
        studio.owner = self
        NotificationCenter.default.addObserver(forName: NSText.didChangeNotification, object: parts.textView, queue: .main) { [weak self] _ in
            self?.builder.textEdited()
            self?.exporter.textEdited()
        }
        if Settings.int("startupWindow") == 1 { studio.show(growWindow: false) }
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
        statusBar.encodingName = encodingDisplayName(document.encoding) + (document.notUTF8 ? ", read-only" : "")
        statusBar.lineEndingName = document.lineEnding.name
        statusBar.fileURL = document.fileURL
        stats.lineBreak = document.lineEnding.unit
        parts.textView.isEditable = !document.notUTF8   // not UTF-8: read-only (a revert can change that either way)
        parts.textView.string = text
        stats.reset()
        ruler.reset()
        parts.textView.setSelectedRange(NSRange(location: 0, length: 0))
        parts.textView.undoManager?.removeAllActions()
        parts.highlighter?.use(fileName: document.fileURL?.lastPathComponent)
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
    /// File > Export As: the item carries the id of a row of `ExportTable`.
    @objc func exportAs(_ sender: Any?) {
        guard let id = (sender as? NSMenuItem)?.representedObject as? String, let format = ExportTable.format(id) else { return }
        exporter.start(format)
    }
    @objc func togglePreview(_ sender: Any?) { studio.toggle() }
    @objc func previewAsHTML(_ sender: Any?) { studio.setMode(pdf: false) }
    @objc func previewAsPDF(_ sender: Any?) { studio.setMode(pdf: true) }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        if item.action == #selector(reloadFile(_:)) { item.title = "Build PDF" }
        if item.action == #selector(showBuildLog(_:)) { return builder.hasLog }
        if item.action == #selector(exportAs(_:)) {
            ExportAvailability.ensureLoaded()
            guard let format = ExportTable.format(item.representedObject as? String ?? "") else { return false }
            if let engine = format.engine, ExportAvailability.missing.contains(engine) { return false }
            return !exporter.running
        }
        if item.action == #selector(togglePreview(_:)) { item.title = studio.isShown ? "Hide Preview" : "Show Preview" }
        if item.action == #selector(previewAsHTML(_:)) { item.state = studio.isShown && !studio.showsPDF ? .on : .off; return studio.isShown }
        if item.action == #selector(previewAsPDF(_:)) { item.state = studio.isShown && studio.showsPDF ? .on : .off; return studio.isShown }
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
    override func typeForContents(of url: URL) throws -> String {
        if isPDFFile(url) { return "PDF document" }
        if isHTMLFile(url), Settings.int("htmlOpenAs") != 1 { return "HTML document" }
        return "Markdown and text"
    }
    override func documentClass(forType typeName: String) -> AnyClass? {
        switch typeName {
        case "PDF document": return PDFViewerDocument.self
        case "HTML document": return HTMLViewerDocument.self
        default: return EditorDocument.self
        }
    }
    override func runModalOpenPanel(_ openPanel: NSOpenPanel, forTypes types: [String]?) -> Int {
        super.runModalOpenPanel(openPanel, forTypes: nil)
    }
}
