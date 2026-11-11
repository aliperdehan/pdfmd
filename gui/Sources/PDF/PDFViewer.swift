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

/// What identifies a version of a file: its modification time, size and inode. Reading a file changes none of them, but it does
/// change the access time, and macOS reports that to the document as "the file changed" (every reload read the file, and so
/// started the next reload: a loop that rebuilt the view every 1.5 s and undid every scroll).
struct FileStamp: Equatable {
    let seconds: Int, nanoseconds: Int, size: Int64, inode: UInt64
    init?(_ url: URL) {
        var st = stat()
        guard stat(url.path, &st) == 0 else { return nil }
        seconds = st.st_mtimespec.tv_sec; nanoseconds = st.st_mtimespec.tv_nsec; size = Int64(st.st_size); inode = UInt64(st.st_ino)
    }
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
    /// The version of the file that is on the screen.
    private var shown: FileStamp?

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
        shown = FileStamp(url)   // before the read: a write that lands during it is a change to be seen next
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
        if Trace.on, let url = fileURL {
            let attrs = try? FileManager.default.attributesOfItem(atPath: url.path)
            let used = getxattr(url.path, "com.apple.lastuseddate#PS", nil, 0, 0, 0) > 0
            var buf = [UInt8](repeating: 0, count: 16); let got = getxattr(url.path, "com.apple.lastuseddate#PS", &buf, 16, 0, 0)
            Trace.log("presentedItemDidChange: mtime \((attrs?[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0), size \(attrs?[.size] ?? 0), lastuseddate xattr \(used ? buf.prefix(max(0, got)).map { String(format: "%02x", $0) }.joined() : "none")")
        }
        DispatchQueue.main.async { [weak self] in self?.fileChanged() }
    }

    /// The file on disk is not the one on the screen (only meaningful while the automatic reload is off).
    private(set) var changedOnDisk = false

    func fileChanged() {
        if let url = fileURL, let now = FileStamp(url), now == shown { return }   // only the access time moved
        guard Settings.flag("pdfAutoReload") else {   // manual: say so in the window and wait for Reload
            changedOnDisk = true
            controller?.fileStateChanged()
            return
        }
        tries = 0
        schedule()
    }

    /// Reload now (View > Reload, or the automatic reload switched back on while the file was newer): the same page and zoom.
    func reloadNow() {
        reloadWork?.cancel()
        tries = 0
        reload()
    }

    /// After a build that wrote the file: show it again unless it is on the screen already (the automatic reload may have been quicker).
    func reloadIfChanged() {
        if let url = fileURL, let now = FileStamp(url), now == shown, !changedOnDisk { return }
        reloadNow()
    }

    private func schedule() {
        reloadWork?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.reload() }
        reloadWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(max(0, Settings.int("pdfReloadDebounceMs"))), execute: work)
    }

    private func reload() {
        guard let url = fileURL else { return }
        let stamp = FileStamp(url)
        if pdfLooksComplete(url), let d = PDFDocument(url: url), d.pageCount > 0 {
            shown = stamp
            pdf = d
            changedOnDisk = false
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

/// The colour behind the pages, the thumbnails, the contents and the divider's slot. One explicit colour for all of them: the
/// system's under-page colour came out in two different greys in different views (a lighter stripe at the divider).
enum Desk {
    static let color = NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(srgbRed: 27 / 255, green: 28 / 255, blue: 29 / 255, alpha: 1)
            : NSColor(srgbRed: 0.58, green: 0.58, blue: 0.60, alpha: 1)
    }
}

/// The split view with a divider that is easy to catch: the slot is `grab` points wide (a setting), painted like the sidebar, with a
/// hairline on its page side, exactly where the sidebar ends and the pages begin. A double click on it asks for the default width.
final class SidebarSplit: NSSplitView {
    var onDefaultWidth: (() -> Void)?
    var grab: CGFloat = 8 {
        didSet { if oldValue != grab { adjustSubviews(); needsDisplay = true } }
    }
    override var dividerThickness: CGFloat { grab }
    override func drawDivider(in rect: NSRect) {
        Desk.color.setFill()
        rect.fill()
        dividerColor.setFill()
        NSRect(x: rect.maxX - 1, y: rect.minY, width: 1, height: rect.height).fill()
    }
    override func mouseDown(with event: NSEvent) {
        let x = convert(event.locationInWindow, from: nil).x
        if event.clickCount == 2, let first = arrangedSubviews.first, x >= first.frame.maxX, x <= first.frame.maxX + dividerThickness {
            onDefaultWidth?()
            return
        }
        super.mouseDown(with: event)
    }
}

/// The window: thumbnails on the left, the pages on the right, the toolbar (sidebar, zoom, fit, search) above, and the page
/// and zoom in the subtitle.
final class PDFWindowController: NSWindowController, NSToolbarDelegate, NSSplitViewDelegate, PDFDocumentDelegate, NSMenuItemValidation {
    private(set) var pdfView = PDFView()
    private let pages = NSView()   // holds the PDFView (two of them for a moment during a reload)
    private(set) var thumbs = PDFThumbnailView()
    private let side = NSView()
    private let modes = NSSegmentedControl()   // Pages | Contents, at the top of the sidebar
    private let body = NSView()                // under it: the thumbnails or the contents
    let contents = PDFContentsView()
    private let split = SidebarSplit()
    private static let thumbnailMargin: CGFloat = 36   // what the thumbnail view keeps around a thumbnail: the sidebar is this much wider
    private var lastRemembered = 0
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
        window.tabbingIdentifier = AppDelegate.tabGroup
        window.setFrameAutosaveName("pdfmdedit.pdfwindow")
        super.init(window: window)
        shouldCascadeWindows = true

        side.autoresizingMask = [.height]
        setUpSidebar()
        thumbs.pdfView = pdfView
        thumbs.maximumNumberOfColumns = 1
        thumbs.allowsDragging = false
        thumbs.translatesAutoresizingMaskIntoConstraints = false
        pinThumbs(thumbs)

        pin(pdfView)

        split.frame = window.contentLayoutRect
        split.autoresizingMask = [.width, .height]
        split.isVertical = true
        split.dividerStyle = .thin
        split.grab = CGFloat(max(1, Settings.number("pdfDividerGrabPt")))
        split.onDefaultWidth = { [weak self] in self?.resetSidebarWidth(nil) }
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
        if Trace.on {
            Trace.watchStalls()
            pdfView.postsFrameChangedNotifications = true
            nc.addObserver(forName: NSView.frameDidChangeNotification, object: pdfView, queue: .main) { [weak self] _ in
                Trace.log("pdfView frame \(self?.pdfView.frame ?? .zero)")
            }
            if let clip = pdfView.documentView?.enclosingScrollView?.contentView {
                clip.postsBoundsChangedNotifications = true
                nc.addObserver(forName: NSView.boundsDidChangeNotification, object: clip, queue: .main) { _ in
                    Trace.log("scrolled: clip y \(Int(clip.bounds.origin.y))")
                }
            }
            nc.addObserver(forName: NSWindow.didBecomeKeyNotification, object: window, queue: .main) { _ in Trace.log("window became key") }
        }
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
        if Settings.flag("pdfAutoReload"), let doc = document as? PDFViewerDocument, doc.changedOnDisk { doc.reloadNow() }   // switched back on: catch up
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

    private func setUpSidebar() {
        modes.segmentCount = 2
        modes.trackingMode = .selectOne
        modes.segmentDistribution = .fillEqually
        modes.controlSize = .small
        for (i, (symbol, tip)) in [("square.grid.2x2", "Thumbnails"), ("list.bullet.indent", "Table of Contents")].enumerated() {
            modes.setImage(NSImage(systemSymbolName: symbol, accessibilityDescription: tip), forSegment: i)
            modes.setToolTip(tip, forSegment: i)
        }
        modes.target = self
        modes.action = #selector(modeChanged(_:))
        for v in [modes, body] {
            v.translatesAutoresizingMaskIntoConstraints = false
            side.addSubview(v)
        }
        NSLayoutConstraint.activate([
            modes.topAnchor.constraint(equalTo: side.topAnchor, constant: 6),
            modes.leadingAnchor.constraint(equalTo: side.leadingAnchor, constant: 8),
            modes.trailingAnchor.constraint(equalTo: side.trailingAnchor, constant: -8),
            body.topAnchor.constraint(equalTo: modes.bottomAnchor, constant: 6),
            body.leadingAnchor.constraint(equalTo: side.leadingAnchor), body.trailingAnchor.constraint(equalTo: side.trailingAnchor),
            body.bottomAnchor.constraint(equalTo: side.bottomAnchor),
        ])
        contents.view.translatesAutoresizingMaskIntoConstraints = false
        body.addSubview(contents.view)
        NSLayoutConstraint.activate([
            contents.view.leadingAnchor.constraint(equalTo: body.leadingAnchor), contents.view.trailingAnchor.constraint(equalTo: body.trailingAnchor),
            contents.view.topAnchor.constraint(equalTo: body.topAnchor), contents.view.bottomAnchor.constraint(equalTo: body.bottomAnchor),
        ])
        contents.onGo = { [weak self] destination in self?.pdfView.go(to: destination) }
    }

    @objc private func modeChanged(_ sender: NSSegmentedControl) {
        Settings.set("pdfSidebarMode", sender.selectedSegment)
    }

    private func pinThumbs(_ view: PDFThumbnailView, below other: NSView? = nil) {
        view.translatesAutoresizingMaskIntoConstraints = false
        if let other { body.addSubview(view, positioned: .below, relativeTo: other) } else if view.superview == nil { body.addSubview(view) }
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: body.leadingAnchor), view.trailingAnchor.constraint(equalTo: body.trailingAnchor),
            view.topAnchor.constraint(equalTo: body.topAnchor), view.bottomAnchor.constraint(equalTo: body.bottomAnchor),
        ])
    }

    private func configure(_ view: PDFView) {
        view.displaysPageBreaks = true
        view.backgroundColor = Desk.color
        let gutter = CGFloat(max(0, Settings.number("pdfPageSideGutterPt")))   // PDFKit's own gap left and right of the pages, which kept the divider off the page
        let m = view.pageBreakMargins
        view.pageBreakMargins = NSEdgeInsets(top: m.top, left: gutter, bottom: m.bottom, right: gutter)
        view.displayMode = PDFDisplayMode(rawValue: Settings.int("pdfDisplayMode")) ?? .singlePageContinuous
        view.interpolationQuality = PDFInterpolationQuality(rawValue: Settings.int("pdfInterpolation")) ?? .low
        view.minScaleFactor = CGFloat(Settings.number("pdfZoomMinPercent")) / 100
        view.maxScaleFactor = CGFloat(Settings.number("pdfZoomMaxPercent")) / 100
    }

    /// The sidebar's width: the one last dragged to, or the one the thumbnail width setting gives (the sidebar is as wide as a
    /// thumbnail plus the margins the thumbnail view keeps around it).
    private var sidebarWidthWanted: CGFloat {
        let dragged = Settings.number("pdfSidebarWidth")
        if dragged > 0 { return CGFloat(max(Double(Self.thumbnailMargin) + 40, dragged)) }
        return CGFloat(max(40, Settings.number("pdfThumbnailWidth"))) + Self.thumbnailMargin
    }

    private func applySettings() {
        configure(pdfView)
        let sidebarWidth = sidebarWidthWanted
        let width = max(40, sidebarWidth - Self.thumbnailMargin)
        thumbs.thumbnailSize = CGSize(width: width, height: (width * 1.4).rounded())
        thumbs.backgroundColor = Desk.color
        let show = Settings.flag("pdfThumbnails")
        let mode = Settings.int("pdfSidebarMode") == 1 ? 1 : 0
        modes.selectedSegment = mode
        thumbs.isHidden = mode == 1
        contents.view.isHidden = mode == 0
        contents.isActive = show && mode == 1
        split.grab = CGFloat(max(1, Settings.number("pdfDividerGrabPt")))
        let wasHidden = side.isHidden
        side.isHidden = !show
        // Hidden means out of the split view: a hidden pane left the page area where it was (an empty strip) and its divider drawn across the pages
        let attached = split.arrangedSubviews.contains(side)
        if !show, attached {
            split.removeArrangedSubview(side)
            side.removeFromSuperview()
        } else if show, !attached {
            split.insertArrangedSubview(side, at: 0)
            split.setHoldingPriority(.defaultHigh, forSubviewAt: 0)
        }
        if show {
            // the sidebar is as wide as a thumbnail plus the margins the thumbnail view keeps around it
            if wasHidden || abs(side.frame.width - sidebarWidth) > 1 { split.setPosition(sidebarWidth, ofDividerAt: 0) }
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
            freshThumbs.isHidden = oldThumbs.isHidden
            pinThumbs(freshThumbs, below: oldThumbs)
            side.layoutSubtreeIfNeeded()
            thumbs = freshThumbs
            leavingThumbs = oldThumbs
            if hadFocus { window?.makeFirstResponder(fresh) }
            leaving = old
        }
        if let previous = old.document, previous !== doc {
            previous.cancelFindString()
            previous.delegate = nil
        }
        let view = pdfView
        doc.delegate = self
        view.document = doc
        contents.use(doc, keepOpen: keepingPlace, levels: Settings.int("pdfContentsOpenLevels"))
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

    /// The file changed on disk and was not reloaded, or it was reloaded now: the subtitle says which.
    func fileStateChanged() { placeChanged() }

    @objc private func placeChanged() {
        guard let window, let doc = pdfView.document else { return }
        if Trace.on {
            let clip = pdfView.documentView?.enclosingScrollView?.contentView
            Trace.log("place: page \(pdfView.currentPage.map { doc.index(for: $0) + 1 } ?? -1), zoom \(String(format: "%.3f", pdfView.scaleFactor)), autoScales \(pdfView.autoScales), view \(Int(pdfView.bounds.width))x\(Int(pdfView.bounds.height)), clip y \(Int(clip?.bounds.origin.y ?? -1)), doc height \(Int(pdfView.documentView?.frame.height ?? -1))")
        }
        var parts: [String] = []
        if let page = pdfView.currentPage {
            parts.append("Page \(doc.index(for: page) + 1) of \(doc.pageCount)")
            contents.reveal(page: doc.index(for: page))
        }
        parts.append("\(Int((pdfView.scaleFactor * 100).rounded()))%")
        if (document as? PDFViewerDocument)?.changedOnDisk == true { parts.append("file changed, ⌘R to reload") }
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

    @objc func reloadFile(_ sender: Any?) { (document as? PDFViewerDocument)?.reloadNow() }

    @objc func toggleAutoReload(_ sender: Any?) {
        Settings.set("pdfAutoReload", Settings.flag("pdfAutoReload") ? 0 : 1)   // every PDF window follows (settingsChanged)
    }

    @objc func showPages(_ sender: Any?) { showSidebar(mode: 0) }
    @objc func showContents(_ sender: Any?) { showSidebar(mode: 1) }

    private func showSidebar(mode: Int) {
        Settings.set("pdfSidebarMode", mode)
        Settings.set("pdfThumbnails", 1)
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
            guard searching, let current = pdfView.document, !instance.pages.isEmpty,
                  instance.pages.allSatisfy({ $0.document === current }) else { return }
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
            guard searching, let source = notification.object as? PDFDocument, source === pdfView.document else { return }
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
        case Self.sidebarID: return button("sidebar.left", "Sidebar", #selector(toggleThumbnails(_:)))
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

    /// The thumbnails follow the sidebar's width (a wider sidebar made only more empty space); the width the author drags to is
    /// remembered as the thumbnail width setting once the drag has stopped.
    func splitViewDidResizeSubviews(_ notification: Notification) {
        guard !side.isHidden, side.frame.width > 0 else { return }
        let w = max(40, side.frame.width - Self.thumbnailMargin).rounded()
        guard abs(thumbs.thumbnailSize.width - w) > 0.5 else { return }
        thumbs.thumbnailSize = CGSize(width: w, height: (w * 1.4).rounded())
        NSObject.cancelPreviousPerformRequests(withTarget: self, selector: #selector(rememberWidth), object: nil)
        perform(#selector(rememberWidth), with: nil, afterDelay: 0.4)
    }

    @objc private func rememberWidth() {
        guard !side.isHidden else { return }
        let w = Int(side.frame.width.rounded())
        let standard = Int((CGFloat(max(40, Settings.number("pdfThumbnailWidth"))) + Self.thumbnailMargin).rounded())
        let wanted = w == standard ? 0 : w   // dragged back to the default: nothing to remember
        if wanted != Int(Settings.number("pdfSidebarWidth")) { Settings.set("pdfSidebarWidth", wanted) }
    }

    /// Back to the width the thumbnail width setting gives; the width that was dragged to is forgotten (in every PDF window).
    @objc func resetSidebarWidth(_ sender: Any?) {
        Settings.set("pdfSidebarWidth", 0)
        if !side.isHidden { split.setPosition(sidebarWidthWanted, ofDividerAt: 0) }
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        switch item.action {
        case #selector(toggleThumbnails(_:)):
            item.title = Settings.flag("pdfThumbnails") ? "Hide Sidebar" : "Show Sidebar"
        case #selector(toggleAutoReload(_:)):
            item.state = Settings.flag("pdfAutoReload") ? .on : .off
        case #selector(reloadFile(_:)):
            item.title = "Reload"
        case #selector(fitPage(_:)):
            item.title = "Zoom to Fit"   // command-9 is "Last Tab" in the other windows (the same menu item)
        case #selector(resetSidebarWidth(_:)):
            return Settings.flag("pdfThumbnails")
        case #selector(showPages(_:)):
            item.state = Settings.flag("pdfThumbnails") && Settings.int("pdfSidebarMode") != 1 ? .on : .off
        case #selector(showContents(_:)):
            item.state = Settings.flag("pdfThumbnails") && Settings.int("pdfSidebarMode") == 1 ? .on : .off
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
