import Cocoa
import WebKit

/// True for a file that is a web page, by its name.
func isHTMLFile(_ url: URL) -> Bool { ["html", "htm", "xhtml"].contains(url.pathExtension.lowercased()) }

/// A web page in a view: one `WKWebView` that can be loaded again without a blink and without losing the place on the page. The old
/// picture of the page stays on top of the view while the new one loads (a web view is blank in between), and the scroll position is
/// put back when it has loaded. Used by the HTML window and by the editor's preview pane.
final class HTMLPageView: NSView, WKNavigationDelegate {
    let web: WKWebView
    private let cover = NSImageView()
    private var place: (x: Double, y: Double)?
    private var generation = 0
    /// How many loads have finished (the self-test waits for it).
    private(set) var loads = 0
    private(set) var url: URL?
    private var readAccess: URL?
    /// A link to a file on this Mac (not the page itself): the owner decides (the window opens it in the app).
    var onFileLink: ((URL) -> Void)?
    /// The folder that relative links of the page are relative to, when the page is a copy elsewhere (the preview): `#anchor` links
    /// then resolve against it and are taken over here, as the page is not that file.
    var linkBase: URL?

    init(javaScript: Bool) {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = javaScript
        web = WKWebView(frame: .zero, configuration: config)
        super.init(frame: .zero)
        web.navigationDelegate = self
        web.underPageBackgroundColor = Desk.color
        web.autoresizingMask = [.width, .height]
        web.frame = bounds
        addSubview(web)
        cover.imageScaling = .scaleNone
        cover.imageAlignment = .alignTopLeft
        cover.autoresizingMask = [.width, .height]
        cover.frame = bounds
        cover.isHidden = true
        addSubview(cover)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    /// Shows a file; `readAccess` is the folder the page may read from (pictures, style sheets).
    func load(_ file: URL, readAccess folder: URL) {
        url = file
        readAccess = folder
        place = nil
        generation += 1
        web.loadFileURL(file, allowingReadAccessTo: folder)
    }

    /// The same file again, on the same place of the page.
    func reload() {
        guard let file = url, let folder = readAccess else { return }
        generation += 1
        let mine = generation
        web.evaluateJavaScript("[window.scrollX, window.scrollY]") { [weak self] result, _ in
            guard let self, mine == self.generation else { return }
            if let p = result as? [Double], p.count == 2 { self.place = (p[0], p[1]) }
            let finish = { [weak self] in
                guard let self, mine == self.generation else { return }
                self.web.loadFileURL(file, allowingReadAccessTo: folder)
            }
            self.web.takeSnapshot(with: nil) { [weak self] image, _ in
                if let self, let image, mine == self.generation { self.cover.image = image; self.cover.isHidden = false }
                finish()
            }
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loads += 1
        let uncover = { [weak self] in
            DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(max(0, Settings.int("htmlCoverMs")))) { self?.cover.isHidden = true; self?.cover.image = nil }
        }
        if let p = place {
            place = nil
            webView.evaluateJavaScript("window.scrollTo(\(p.x), \(p.y))") { _, _ in uncover() }
        } else {
            uncover()
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { cover.isHidden = true }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { cover.isHidden = true }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard action.navigationType == .linkActivated, let target = action.request.url else { decisionHandler(.allow); return }
        if target.isFileURL {
            var bare = target
            let fragment = target.fragment
            if fragment != nil, var parts = URLComponents(url: target, resolvingAgainstBaseURL: false) { parts.fragment = nil; bare = parts.url ?? target }
            let here = url?.standardizedFileURL.path
            let base = linkBase?.standardizedFileURL.path
            let barePath = bare.standardizedFileURL.path
            if let fragment, barePath == here || barePath == base || barePath + "/" == base {
                // an anchor of this very page (in the preview the page's own address is a copy, so the link points at the folder)
                let id = fragment.removingPercentEncoding ?? fragment
                let quoted = id.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'")
                webView.evaluateJavaScript("(document.getElementById('\(quoted)') || document.getElementsByName('\(quoted)')[0] || {scrollIntoView(){}}).scrollIntoView()", completionHandler: nil)
                decisionHandler(.cancel)
                return
            }
            if barePath == here { decisionHandler(.allow); return }
            onFileLink?(bare)
            decisionHandler(.cancel)
        } else {
            NSWorkspace.shared.open(target)   // a web link goes to the browser
            decisionHandler(.cancel)
        }
    }

    // MARK: find and zoom

    func find(_ query: String, backwards: Bool = false, completion: ((Bool) -> Void)? = nil) {
        guard !query.isEmpty else { completion?(false); return }
        let config = WKFindConfiguration()
        config.backwards = backwards
        config.wraps = true
        config.caseSensitive = false
        web.find(query, configuration: config) { completion?($0.matchFound) }
    }

    var zoom: Double {
        get { Double(web.pageZoom) }
        set { web.pageZoom = CGFloat(min(max(newValue, 0.25), 5)) }
    }
}

/// The document behind an HTML window: a file that is shown, never changed. It is watched like a PDF: when something writes it (pdfmd -t html,
/// a build, a copy) the page is loaded again on the same place; View > Reload Automatically turns that off.
@objc(HTMLViewerDocument)
final class HTMLViewerDocument: NSDocument {
    var controller: HTMLWindowController?
    private(set) var reloads = 0
    private(set) var changedOnDisk = false
    private var shown: FileStamp?
    private var reloadWork: DispatchWorkItem?

    override class var autosavesInPlace: Bool { false }
    override class var readableTypes: [String] { ["HTML document"] }
    override class var writableTypes: [String] { [] }
    override class func canConcurrentlyReadDocuments(ofType typeName: String) -> Bool { false }

    override func makeWindowControllers() {
        let c = HTMLWindowController(document: self)
        addWindowController(c)
        controller = c
    }

    override func read(from url: URL, ofType typeName: String) throws {
        guard FileManager.default.isReadableFile(atPath: url.path) else { throw NSError(domain: NSCocoaErrorDomain, code: NSFileReadNoPermissionError) }
        shown = FileStamp(url)   // the web view reads the file itself
    }

    override func validateUserInterfaceItem(_ item: NSValidatedUserInterfaceItem) -> Bool {
        let readOnly = [#selector(NSDocument.save(_:)), #selector(NSDocument.saveAs(_:)), #selector(NSDocument.revertToSaved(_:))]
        if let action = item.action, readOnly.contains(action) { return false }
        return super.validateUserInterfaceItem(item)
    }

    override func presentedItemDidChange() {
        DispatchQueue.main.async { [weak self] in self?.fileChanged() }
    }

    func fileChanged() {
        if let url = fileURL, let now = FileStamp(url), now == shown { return }   // only the access time moved
        guard Settings.flag("htmlAutoReload") else {
            changedOnDisk = true
            controller?.fileStateChanged()
            return
        }
        reloadWork?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.reload() }
        reloadWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(max(0, Settings.int("htmlReloadDebounceMs"))), execute: work)
    }

    func reloadNow() {
        reloadWork?.cancel()
        reload()
    }

    func reloadIfChanged() {
        if let url = fileURL, let now = FileStamp(url), now == shown, !changedOnDisk { return }
        reloadNow()
    }

    private func reload() {
        guard let url = fileURL else { return }
        shown = FileStamp(url)
        changedOnDisk = false
        reloads += 1
        controller?.page.reload()
        controller?.fileStateChanged()
    }

    override func close() {
        reloadWork?.cancel()
        super.close()
    }
}

final class HTMLWindowController: NSWindowController, NSToolbarDelegate, NSMenuItemValidation {
    let page = HTMLPageView(javaScript: true)
    private var searchItem: NSSearchToolbarItem?
    private var lastQuery = ""

    init(document: HTMLViewerDocument) {
        let screenHeight = NSScreen.main?.visibleFrame.height ?? 900
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: min(860, screenHeight - 90)),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("pdfmdedit.htmlwindow")
        super.init(window: window)
        shouldCascadeWindows = true
        page.frame = window.contentLayoutRect
        page.autoresizingMask = [.width, .height]
        window.contentView = page
        page.onFileLink = { url in
            NSDocumentController.shared.openDocument(withContentsOf: url, display: true) { _, _, error in
                if let error { NSApp.presentError(error) }
            }
        }
        let toolbar = NSToolbar(identifier: "pdfmdedit.html")
        toolbar.delegate = self
        toolbar.displayMode = .iconOnly
        window.toolbar = toolbar
        if let url = document.fileURL { page.load(url, readAccess: url.deletingLastPathComponent()) }
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    private var htmlDocument: HTMLViewerDocument? { document as? HTMLViewerDocument }

    func fileStateChanged() {
        window?.subtitle = htmlDocument?.changedOnDisk == true ? "file changed, ⌘R to reload" : ""
    }

    // MARK: actions

    @objc func reloadFile(_ sender: Any?) { htmlDocument?.reloadNow() }

    @objc func toggleAutoReload(_ sender: Any?) {
        Settings.set("htmlAutoReload", Settings.flag("htmlAutoReload") ? 0 : 1)
        if Settings.flag("htmlAutoReload"), htmlDocument?.changedOnDisk == true { htmlDocument?.reloadNow() }
    }

    @objc func zoomIn(_ sender: Any?) { page.zoom += Settings.number("htmlZoomStepPercent") / 100 }
    @objc func zoomOut(_ sender: Any?) { page.zoom -= Settings.number("htmlZoomStepPercent") / 100 }
    @objc func actualSize(_ sender: Any?) { page.zoom = 1 }

    /// Opens the same file as text, in an editor window (the document's own window stays).
    @objc func showSource(_ sender: Any?) { openSource(display: true) }

    func openSource(display: Bool) {
        guard let url = htmlDocument?.fileURL else { return }
        do {
            let source = try EditorDocument(contentsOf: url, ofType: "Markdown and text")
            NSDocumentController.shared.addDocument(source)
            source.makeWindowControllers()
            if display { source.showWindows() }
        } catch { NSApp.presentError(error) }
    }

    @objc override func performTextFinderAction(_ sender: Any?) {
        guard let tag = (sender as? NSMenuItem)?.tag else { return }
        switch tag {
        case 1: searchItem?.beginSearchInteraction()
        case 2: if !lastQuery.isEmpty { page.find(lastQuery) }
        case 3: if !lastQuery.isEmpty { page.find(lastQuery, backwards: true) }
        default: break
        }
    }

    @objc private func searchEntered(_ field: NSSearchField) {
        lastQuery = field.stringValue
        page.find(lastQuery) { found in if !found, !field.stringValue.isEmpty { NSSound.beep() } }
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        switch item.action {
        case #selector(reloadFile(_:)): item.title = "Reload"
        case #selector(toggleAutoReload(_:)): item.state = Settings.flag("htmlAutoReload") ? .on : .off
        case #selector(performTextFinderAction(_:)): return item.tag >= 1 && item.tag <= 3
        default: break
        }
        return true
    }

    // MARK: toolbar

    private static let zoomOutID = NSToolbarItem.Identifier("html.zoomOut")
    private static let zoomInID = NSToolbarItem.Identifier("html.zoomIn")
    private static let sourceID = NSToolbarItem.Identifier("html.source")
    private static let searchID = NSToolbarItem.Identifier("html.search")

    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [Self.zoomOutID, Self.zoomInID, Self.sourceID, .flexibleSpace, Self.searchID]
    }

    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] { toolbarDefaultItemIdentifiers(toolbar) }

    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier id: NSToolbarItem.Identifier, willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        func button(_ symbol: String, _ label: String, _ action: Selector) -> NSToolbarItem {
            let item = NSToolbarItem(itemIdentifier: id)
            item.label = label
            item.toolTip = label
            item.image = NSImage(systemSymbolName: symbol, accessibilityDescription: label)
            item.target = self
            item.action = action
            return item
        }
        switch id {
        case Self.zoomOutID: return button("minus.magnifyingglass", "Zoom Out", #selector(zoomOut(_:)))
        case Self.zoomInID: return button("plus.magnifyingglass", "Zoom In", #selector(zoomIn(_:)))
        case Self.sourceID: return button("chevron.left.forwardslash.chevron.right", "Show Source", #selector(showSource(_:)))
        case Self.searchID:
            let item = NSSearchToolbarItem(itemIdentifier: id)
            item.searchField.target = self
            item.searchField.action = #selector(searchEntered(_:))
            item.searchField.placeholderString = "Find in page"
            item.searchField.sendsWholeSearchString = true
            item.resignsFirstResponderWithCancel = true
            searchItem = item
            return item
        default: return nil
        }
    }
}
