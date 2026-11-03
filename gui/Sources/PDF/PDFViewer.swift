import Cocoa
import PDFKit

/// True for a file that is a PDF: by its name, or by the `%PDF-` the file starts with (a file without the extension).
func isPDFFile(_ url: URL) -> Bool {
    if url.pathExtension.lowercased() == "pdf" { return true }
    guard let h = try? FileHandle(forReadingFrom: url) else { return false }
    defer { try? h.close() }
    return (try? h.read(upToCount: 5)) == Data("%PDF-".utf8)
}

/// A PDF that is finished: the file ends with `%%EOF` (the PDF format allows up to 1024 bytes after it, the same limit
/// every reader uses). A file that a build is still writing does not, so it is not read yet.
func pdfLooksComplete(_ url: URL) -> Bool {
    guard let h = try? FileHandle(forReadingFrom: url) else { return false }
    defer { try? h.close() }
    guard let size = try? h.seekToEnd(), size >= 8 else { return false }
    let tail = min(size, 1024)
    try? h.seek(toOffset: size - tail)
    guard let data = try? h.read(upToCount: Int(tail)) else { return false }
    return data.range(of: Data("%%EOF".utf8)) != nil
}

/// A PDF window's document. Read-only for now (the notes come next). The file is watched: when something rebuilds it (pdfmd,
/// LaTeX, a copy) the new file replaces the shown one, on the same page, at the same place and at the same zoom.
@objc(PDFViewerDocument)
final class PDFViewerDocument: NSDocument {
    var pdf: PDFDocument?
    var controller: PDFWindowController?
    /// How many times the file was read again after a change (the smoke test counts).
    private(set) var reloads = 0
    private var reloadWork: DispatchWorkItem?
    private var tries = 0

    override class var autosavesInPlace: Bool { false }
    override class var readableTypes: [String] { ["PDF document"] }
    override class var writableTypes: [String] { [] }
    override class func canConcurrentlyReadDocuments(ofType typeName: String) -> Bool { false }

    override func makeWindowControllers() {
        let c = PDFWindowController(document: self)
        addWindowController(c)
        controller = c
    }

    override func read(from url: URL, ofType typeName: String) throws {
        guard let d = PDFDocument(url: url), d.pageCount > 0 else { throw NSError(domain: NSCocoaErrorDomain, code: NSFileReadCorruptFileError) }
        pdf = d
    }

    override func validateUserInterfaceItem(_ item: NSValidatedUserInterfaceItem) -> Bool {
        let readOnly = [#selector(NSDocument.save(_:)), #selector(NSDocument.saveAs(_:)), #selector(NSDocument.revertToSaved(_:))]
        if let action = item.action, readOnly.contains(action) { return false }
        return super.validateUserInterfaceItem(item)
    }

    // MARK: reload on change

    /// Something wrote the file. NSDocument would revert an unedited document by itself and show an error for a half-written
    /// file, so this replaces that: wait until the writing has paused, and read the file only when it is finished.
    override func presentedItemDidChange() {
        DispatchQueue.main.async { [weak self] in self?.fileChanged() }
    }

    func fileChanged() {
        tries = 0
        schedule()
    }

    private func schedule() {
        reloadWork?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.reload() }
        reloadWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(max(0, Settings.int("pdfReloadDebounceMs"))), execute: work)
    }

    private func reload() {
        guard let url = fileURL else { return }
        if pdfLooksComplete(url), let d = PDFDocument(url: url), d.pageCount > 0 {
            pdf = d
            reloads += 1
            controller?.replace(d)
            return
        }
        tries += 1   // half written (or being replaced): keep the old one on the screen and look again
        if tries <= Settings.int("pdfReloadRetries") { schedule() }
    }

    override func close() {
        reloadWork?.cancel()
        super.close()
    }
}

/// The window: thumbnails on the left, the pages on the right, the toolbar (sidebar, zoom, fit, search) above, and the page
/// and zoom in the subtitle.
final class PDFWindowController: NSWindowController, NSToolbarDelegate, NSSplitViewDelegate, PDFDocumentDelegate, NSMenuItemValidation {
    private(set) var pdfView = PDFView()
    private let pages = NSView()   // holds the PDFView (two of them for a moment during a reload)
    private(set) var thumbs = PDFThumbnailView()
    private let side = NSView()
    private let split = NSSplitView()
    private var searchItem: NSSearchToolbarItem?
    private(set) var matches: [PDFSelection] = []
    private var matchIndex = -1
    private var lastQuery = ""
    private var searching = false
    private var lastHighlight = Date.distantPast

    init(document: PDFViewerDocument) {
        let screenHeight = NSScreen.main?.visibleFrame.height ?? 900   // a window taller than the screen runs under the Dock
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 980, height: min(900, screenHeight - 90)),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("pdfmdedit.pdfwindow")
        super.init(window: window)
        shouldCascadeWindows = true

        side.autoresizingMask = [.height]
        thumbs.pdfView = pdfView
        thumbs.maximumNumberOfColumns = 1
        thumbs.allowsDragging = false
        thumbs.translatesAutoresizingMaskIntoConstraints = false
        side.addSubview(thumbs)
        pinThumbs(thumbs)

        pin(pdfView)

        split.frame = window.contentLayoutRect
        split.autoresizingMask = [.width, .height]
        split.isVertical = true
        split.dividerStyle = .thin
        split.delegate = self
        split.addArrangedSubview(side)
        split.addArrangedSubview(pages)
        split.setHoldingPriority(.defaultHigh, forSubviewAt: 0)
        window.contentView = split

        let toolbar = NSToolbar(identifier: "pdfmdedit.pdf")
        toolbar.delegate = self
        toolbar.displayMode = .iconOnly
        window.toolbar = toolbar

        applySettings()
        replace(document.pdf!, keepingPlace: false)
        let nc = NotificationCenter.default
        nc.addObserver(self, selector: #selector(placeChanged), name: .PDFViewPageChanged, object: nil)   // from whichever PDFView is current
        nc.addObserver(self, selector: #selector(placeChanged), name: .PDFViewScaleChanged, object: nil)
        nc.addObserver(self, selector: #selector(settingsChanged), name: Settings.changed, object: nil)
        placeChanged()
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    deinit { NotificationCenter.default.removeObserver(self) }

    override func showWindow(_ sender: Any?) {
        super.showWindow(sender)
        window?.makeFirstResponder(pdfView)
    }

    // MARK: settings

    @objc func settingsChanged() {
        applySettings()
        placeChanged()
    }

    /// At the very top of the document the view shows the margin above the first page, a place PDFKit's `go(to:)` cannot reach (it
    /// stops at the page's edge): the rest is scrolled by hand, in whichever direction brings the destination closer.
    private func scrollIntoMargin(_ view: PDFView, wantedY: CGFloat) {
        guard let scroll = view.documentView?.enclosingScrollView, let got = view.currentDestination?.point.y, wantedY > got + 0.5 else { return }
        let clip = scroll.contentView
        let start = clip.bounds.origin
        let pixels = (wantedY - got) * view.scaleFactor
        for direction in [CGFloat(-1), 1] {
            clip.scroll(to: NSPoint(x: start.x, y: start.y + direction * pixels))
            scroll.reflectScrolledClipView(clip)
            if let now = view.currentDestination?.point.y, abs(now - wantedY) < abs(got - wantedY) - 0.25 { return }
        }
        clip.scroll(to: start)
        scroll.reflectScrolledClipView(clip)
    }

    /// Puts a PDFView into the container, filling it (constraints: the container has no size yet when the first one is added).
    private func pin(_ view: PDFView, below other: NSView? = nil) {
        view.translatesAutoresizingMaskIntoConstraints = false
        if let other { pages.addSubview(view, positioned: .below, relativeTo: other) } else { pages.addSubview(view) }
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: pages.leadingAnchor), view.trailingAnchor.constraint(equalTo: pages.trailingAnchor),
            view.topAnchor.constraint(equalTo: pages.topAnchor), view.bottomAnchor.constraint(equalTo: pages.bottomAnchor),
        ])
    }

    private func pinThumbs(_ view: PDFThumbnailView, below other: NSView? = nil) {
        view.translatesAutoresizingMaskIntoConstraints = false
        if let other { side.addSubview(view, positioned: .below, relativeTo: other) } else if view.superview == nil { side.addSubview(view) }
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: side.leadingAnchor), view.trailingAnchor.constraint(equalTo: side.trailingAnchor),
            view.topAnchor.constraint(equalTo: side.topAnchor), view.bottomAnchor.constraint(equalTo: side.bottomAnchor),
        ])
    }

    private func configure(_ view: PDFView) {
        view.displaysPageBreaks = true
        view.backgroundColor = .underPageBackgroundColor
        view.displayMode = PDFDisplayMode(rawValue: Settings.int("pdfDisplayMode")) ?? .singlePageContinuous
        view.interpolationQuality = PDFInterpolationQuality(rawValue: Settings.int("pdfInterpolation")) ?? .low
        view.minScaleFactor = CGFloat(Settings.number("pdfZoomMinPercent")) / 100
        view.maxScaleFactor = CGFloat(Settings.number("pdfZoomMaxPercent")) / 100
    }

    private func applySettings() {
        configure(pdfView)
        let width = CGFloat(max(40, Settings.number("pdfThumbnailWidth")))
        thumbs.thumbnailSize = CGSize(width: width, height: (width * 1.4).rounded())
        let show = Settings.flag("pdfThumbnails")
        let wasHidden = side.isHidden
        side.isHidden = !show
        if show {
            // the sidebar is as wide as a thumbnail plus the margins the thumbnail view keeps around it
            let wanted = width + 36
            if wasHidden || abs(side.frame.width - wanted) > 40 { split.setPosition(wanted, ofDividerAt: 0) }
        }
    }

    /// PDFView forgets its zoom limits when it is given a document, so they are set again then.
    private func applyZoomLimits() {
        pdfView.minScaleFactor = CGFloat(Settings.number("pdfZoomMinPercent")) / 100
        pdfView.maxScaleFactor = CGFloat(Settings.number("pdfZoomMaxPercent")) / 100
    }

    /// The first fit when a file is opened: the page's width, the whole page, or the page's real size.
    private func applyOpenFit() {
        switch Settings.int("pdfOpenFit") {
        case 1: fitPage(nil)
        case 2: actualSize(nil)
        default: fitWidth(nil)
        }
    }

    // MARK: the document

    /// Shows a document. On a reload (`keepingPlace`) the page, the point on it and the zoom stay, and the old pages stay on the
    /// screen until the new ones have drawn themselves: a PDFView that is given a new document drops every page and draws them
    /// again one by one (a blink, and a snapshot of a PDFView comes out white), so the new document goes into a second PDFView
    /// under the first, and the first is taken away `pdfReloadCoverMs` later.
    func replace(_ doc: PDFDocument, keepingPlace: Bool = true) {
        let old = pdfView
        var pageIndex = 0
        var point = CGPoint.zero
        if keepingPlace, let oldDoc = old.document, let page = old.currentPage {
            pageIndex = oldDoc.index(for: page)
            point = old.currentDestination?.point ?? .zero
        }
        let scale = old.scaleFactor, auto = old.autoScales
        let overlap = Settings.int("pdfReloadCoverMs")
        var leaving: PDFView?
        var leavingThumbs: PDFThumbnailView?
        if keepingPlace, overlap > 0, window?.isVisible == true, old.document != nil {
            let hadFocus = window?.firstResponder === old
            let fresh = PDFView()
            configure(fresh)
            pin(fresh, below: old)
            pages.layoutSubtreeIfNeeded()
            pdfView = fresh
            // the thumbnails too: re-pointing a thumbnail view redraws every thumbnail (they blink), so a second one is made
            let oldThumbs = thumbs
            let freshThumbs = PDFThumbnailView()
            freshThumbs.pdfView = fresh
            freshThumbs.maximumNumberOfColumns = oldThumbs.maximumNumberOfColumns
            freshThumbs.allowsDragging = oldThumbs.allowsDragging
            freshThumbs.thumbnailSize = oldThumbs.thumbnailSize
            pinThumbs(freshThumbs, below: oldThumbs)
            side.layoutSubtreeIfNeeded()
            thumbs = freshThumbs
            leavingThumbs = oldThumbs
            if hadFocus { window?.makeFirstResponder(fresh) }
            leaving = old
        }
        let view = pdfView
        doc.delegate = self
        view.document = doc
        applyZoomLimits()
        if keepingPlace {
            // The exact zoom first, the place next, and only then "fit to the width" again: PDFView works out a fitted zoom
            // after the document is set, and a place set before that moves when it lands (the view kept scrolling).
            view.autoScales = false
            view.scaleFactor = scale
            view.layoutDocumentView()
            if let page = doc.page(at: min(pageIndex, doc.pageCount - 1)) {
                // `go` puts the point a few points off (the margin around a page): look where it landed and correct once
                view.go(to: PDFDestination(page: page, at: point))
                if let got = view.currentDestination?.point, abs(got.y - point.y) < 40 {
                    view.go(to: PDFDestination(page: page, at: CGPoint(x: 2 * point.x - got.x, y: 2 * point.y - got.y)))
                }
                scrollIntoMargin(view, wantedY: point.y)
            }
            if auto { view.autoScales = true }
            if !lastQuery.isEmpty { search(lastQuery, jump: false) }   // the matches belonged to the old file
        } else {
            applyOpenFit()
        }
        if let leaving {
            DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(overlap)) {
                leaving.removeFromSuperview()
                leaving.document = nil
                leavingThumbs?.removeFromSuperview()
            }
        }
        placeChanged()
    }

    @objc private func placeChanged() {
        guard let window, let doc = pdfView.document else { return }
        var parts: [String] = []
        if let page = pdfView.currentPage { parts.append("Page \(doc.index(for: page) + 1) of \(doc.pageCount)") }
        parts.append("\(Int((pdfView.scaleFactor * 100).rounded()))%")
        if !lastQuery.isEmpty {
            if searching { parts.append("searching… \(matches.count)") }
            else if matches.isEmpty { parts.append("not found") }
            else { parts.append("match \(matchIndex + 1) of \(matches.count)") }
        }
        window.subtitle = parts.joined(separator: "  ·  ")
    }

    // MARK: zoom and pages

    private func setScale(_ scale: CGFloat) {
        pdfView.autoScales = false
        pdfView.scaleFactor = min(max(scale, pdfView.minScaleFactor), pdfView.maxScaleFactor)
    }

    private var zoomStep: CGFloat { 1 + CGFloat(max(1, Settings.number("pdfZoomStepPercent"))) / 100 }

    @objc func zoomIn(_ sender: Any?) { setScale(pdfView.scaleFactor * zoomStep) }
    @objc func zoomOut(_ sender: Any?) { setScale(pdfView.scaleFactor / zoomStep) }
    @objc func actualSize(_ sender: Any?) { setScale(1) }

    /// The area a page may take: the view without the margins around the pages.
    private func available() -> CGSize {
        let size = pdfView.documentView?.enclosingScrollView?.contentSize ?? pdfView.bounds.size
        let m = pdfView.pageBreakMargins
        return CGSize(width: max(1, size.width - m.left - m.right), height: max(1, size.height - m.top - m.bottom))
    }

    private func currentPageSize() -> CGSize? {
        guard let page = pdfView.currentPage ?? pdfView.document?.page(at: 0) else { return nil }
        let b = page.bounds(for: pdfView.displayBox)
        return page.rotation % 180 == 0 ? b.size : CGSize(width: b.height, height: b.width)
    }

    @objc func fitWidth(_ sender: Any?) {
        pdfView.autoScales = true   // follows the window when it is resized
    }

    @objc func fitPage(_ sender: Any?) {
        guard let p = currentPageSize(), p.width > 0, p.height > 0 else { return }
        let a = available()
        setScale(min(a.width / p.width, a.height / p.height))
    }

    @objc func toggleThumbnails(_ sender: Any?) {
        Settings.set("pdfThumbnails", Settings.flag("pdfThumbnails") ? 0 : 1)   // every PDF window follows (settingsChanged)
    }

    @objc func goToPage(_ sender: Any?) {
        guard let window, let doc = pdfView.document else { return }
        let alert = NSAlert()
        alert.messageText = "Go to Page"
        alert.informativeText = "1 to \(doc.pageCount)"
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 120, height: 22))
        if let page = pdfView.currentPage { field.stringValue = String(doc.index(for: page) + 1) }
        alert.accessoryView = field
        alert.addButton(withTitle: "Go")
        alert.addButton(withTitle: "Cancel")
        alert.window.initialFirstResponder = field
        alert.beginSheetModal(for: window) { [weak self] response in
            guard response == .alertFirstButtonReturn, let n = Int(field.stringValue.trimmingCharacters(in: .whitespaces)) else { return }
            self?.go(toPage: n)
        }
    }

    func go(toPage n: Int) {
        guard let doc = pdfView.document, let page = doc.page(at: min(max(n, 1), doc.pageCount) - 1) else { return }
        pdfView.go(to: page)
    }

    // MARK: find

    /// The Edit menu's Find items (`performTextFinderAction:` and its tags, as NSTextView takes them): PDFView ignores them.
    @objc override func performTextFinderAction(_ sender: Any?) {
        guard let tag = (sender as? NSMenuItem)?.tag else { return }
        switch tag {
        case 1: searchItem?.beginSearchInteraction()
        case 2: step(1)
        case 3: step(-1)
        case 7:
            if let s = pdfView.currentSelection?.string, !s.isEmpty { searchItem?.searchField.stringValue = s; search(s, jump: true) }
        default: break
        }
    }

    @objc private func searchEntered(_ field: NSSearchField) {
        let q = field.stringValue
        if q.isEmpty { clearSearch() }
        else if q == lastQuery, !matches.isEmpty { step(1) }
        else { search(q, jump: true) }
    }

    func search(_ query: String, jump: Bool) {
        guard let doc = pdfView.document else { return }
        doc.cancelFindString()
        matches = []
        matchIndex = -1
        lastQuery = query
        jumpToFirst = jump
        pdfView.highlightedSelections = nil
        searching = true
        doc.delegate = self
        doc.beginFindString(query, withOptions: .caseInsensitive)
        placeChanged()
    }

    private var jumpToFirst = true

    func clearSearch() {
        pdfView.document?.cancelFindString()
        matches = []
        matchIndex = -1
        lastQuery = ""
        searching = false
        pdfView.highlightedSelections = nil
        pdfView.clearSelection()
        placeChanged()
    }

    func step(_ delta: Int) {
        guard !matches.isEmpty else { return }
        select((matchIndex + delta + matches.count) % matches.count)
    }

    private func select(_ i: Int) {
        matchIndex = i
        let m = matches[i]
        pdfView.setCurrentSelection(m, animate: true)
        pdfView.go(to: m)
        placeChanged()
    }

    func didMatchString(_ instance: PDFSelection) {
        let handle = { [self] in
            guard searching else { return }
            instance.color = Palette.parse(Settings.string("pdfFindColor")) ?? .systemYellow
            matches.append(instance)
            if matches.count == 1, jumpToFirst { select(0) }
            if Date().timeIntervalSince(lastHighlight) > 0.25 {
                lastHighlight = Date()
                pdfView.highlightedSelections = matches
                placeChanged()
            }
        }
        if Thread.isMainThread { handle() } else { DispatchQueue.main.async(execute: handle) }
    }

    func documentDidEndDocumentFind(_ notification: Notification) {
        let handle = { [self] in
            searching = false
            pdfView.highlightedSelections = matches
            placeChanged()
        }
        if Thread.isMainThread { handle() } else { DispatchQueue.main.async(execute: handle) }
    }

    // MARK: toolbar

    private static let sidebarID = NSToolbarItem.Identifier("pdf.sidebar")
    private static let zoomOutID = NSToolbarItem.Identifier("pdf.zoomOut")
    private static let zoomInID = NSToolbarItem.Identifier("pdf.zoomIn")
    private static let fitID = NSToolbarItem.Identifier("pdf.fit")
    private static let searchID = NSToolbarItem.Identifier("pdf.search")

    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [Self.sidebarID, Self.zoomOutID, Self.zoomInID, Self.fitID, .flexibleSpace, Self.searchID]
    }

    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        toolbarDefaultItemIdentifiers(toolbar)
    }

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
        case Self.sidebarID: return button("sidebar.left", "Thumbnails", #selector(toggleThumbnails(_:)))
        case Self.zoomOutID: return button("minus.magnifyingglass", "Zoom Out", #selector(zoomOut(_:)))
        case Self.zoomInID: return button("plus.magnifyingglass", "Zoom In", #selector(zoomIn(_:)))
        case Self.fitID: return button("arrow.up.left.and.arrow.down.right", "Fit Width", #selector(fitWidth(_:)))
        case Self.searchID:
            let item = NSSearchToolbarItem(itemIdentifier: id)
            item.searchField.target = self
            item.searchField.action = #selector(searchEntered(_:))
            item.searchField.placeholderString = "Find in document"
            item.searchField.sendsWholeSearchString = true
            item.resignsFirstResponderWithCancel = true
            searchItem = item
            return item
        default: return nil
        }
    }

    // MARK: split view and menus

    func splitView(_ splitView: NSSplitView, canCollapseSubview subview: NSView) -> Bool { subview === side }
    func splitView(_ splitView: NSSplitView, constrainMinCoordinate proposed: CGFloat, ofSubviewAt index: Int) -> CGFloat { max(proposed, 90) }
    func splitView(_ splitView: NSSplitView, constrainMaxCoordinate proposed: CGFloat, ofSubviewAt index: Int) -> CGFloat { min(proposed, splitView.bounds.width / 2) }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        switch item.action {
        case #selector(toggleThumbnails(_:)):
            item.title = Settings.flag("pdfThumbnails") ? "Hide Thumbnails" : "Show Thumbnails"
        case #selector(zoomIn(_:)):
            return pdfView.scaleFactor < pdfView.maxScaleFactor - 0.0001
        case #selector(zoomOut(_:)):
            return pdfView.scaleFactor > pdfView.minScaleFactor + 0.0001
        case #selector(performTextFinderAction(_:)):
            return item.tag == 1 || item.tag == 7 || !matches.isEmpty
        default: break
        }
        return true
    }
}
