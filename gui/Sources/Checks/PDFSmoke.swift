import Cocoa
import PDFKit

/// The resident memory of this process, in MB.
func residentMB() -> Double {
    var info = mach_task_basic_info()
    var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
    let result = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count) }
    }
    return result == KERN_SUCCESS ? Double(info.resident_size) / 1_048_576 : -1
}

/// `pdfmdedit --smoke-pdf FILE`: opens a copy of FILE (at least three pages) through the real document path, without showing
/// a window, and checks the viewer: page and zoom, the file rewritten in place, replaced atomically and caught half written
/// (the page, the place on it and the zoom must survive; the old document stays while the file is incomplete), search, the
/// zoom limits, the thumbnails setting. A scratch settings domain is used, never the app's own.
/// `pdfmdedit --bench-pdf FILE`: opens FILE with PDFKit and times it (open, first page, a page rendered at three zooms).
enum PDFSmoke {
    static func spin(_ seconds: Double) { RunLoop.current.run(until: Date().addingTimeInterval(seconds)) }

    /// Runs the loop until `condition` holds or `timeout` seconds pass.
    @discardableResult
    static func wait(_ timeout: Double, _ condition: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(timeout)
        while !condition() && Date() < end { spin(0.02) }
        return condition()
    }

    static func open(_ url: URL) -> PDFViewerDocument? {
        var result: PDFViewerDocument?
        var done = false
        NSDocumentController.shared.openDocument(withContentsOf: url, display: false) { doc, _, error in
            result = doc as? PDFViewerDocument
            if let error { print("open error: \(error)") }
            done = true
        }
        while !done { spin(0.05) }
        if let doc = result, doc.windowControllers.isEmpty { doc.makeWindowControllers() }
        return result
    }

    static func run(_ path: String) {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let domain = "io.github.aliperdehan.pdfmdedit.smokepdf"
        UserDefaults.standard.removePersistentDomain(forName: domain)
        Settings.store = UserDefaults(suiteName: domain)!
        Settings.store.set(150, forKey: "pdfReloadDebounceMs")
        Settings.store.set(60, forKey: "pdfReloadRetries")
        defer { UserDefaults.standard.removePersistentDomain(forName: domain) }

        var failures = 0
        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            print("\(ok ? "ok  " : "FAIL") \(name) \(detail)")
            if !ok { failures += 1 }
        }
        let fm = FileManager.default
        let dir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("pdfmdedit-smoke-pdf-\(getpid())")
        try! fm.createDirectory(at: dir, withIntermediateDirectories: true)
        let doc1 = dir.appendingPathComponent("doc.pdf"), shorter = dir.appendingPathComponent("shorter.pdf"), staging = dir.appendingPathComponent("staging.pdf")
        defer { for u in [doc1, shorter, staging] { try? fm.removeItem(at: u) }; try? fm.removeItem(at: dir) }
        let fullBytes = try! Data(contentsOf: URL(fileURLWithPath: path))
        try! fullBytes.write(to: doc1)
        guard let source = PDFDocument(url: doc1), source.pageCount >= 3 else { print("FAIL the file needs at least 3 pages"); exit(1) }
        let pages = source.pageCount
        let cut = PDFDocument(url: doc1)!
        cut.removePage(at: pages - 1)
        cut.write(to: shorter)
        let shortBytes = try! Data(contentsOf: shorter)
        check("the shorter test file ends with %%EOF", pdfLooksComplete(shorter))

        let started = Date()
        guard let doc = open(doc1), let c = doc.controller else { print("FAIL open"); exit(1) }
        print(String(format: "open document + window: %.0f ms, %d pages, %.0f MB resident", Date().timeIntervalSince(started) * 1000, pages, residentMB()))
        check("type is PDF document", doc.fileType == "PDF document", doc.fileType ?? "nil")
        check("the window was not shown", c.window?.isVisible == false)
        c.window?.setContentSize(NSSize(width: 1000, height: 800))
        c.window?.contentView?.layoutSubtreeIfNeeded()
        var view: PDFView { c.pdfView }   // a reload puts the new document in a new PDFView
        check("page count", view.document?.pageCount == pages)
        check("subtitle names page and zoom", (c.window?.subtitle ?? "").hasPrefix("Page 1 of \(pages)"), c.window?.subtitle ?? "")
        check("opened fitted to the width (autoScales)", view.autoScales)
        check("Save is disabled for a read-only document", !doc.validateUserInterfaceItem(NSMenuItem(title: "", action: #selector(NSDocument.save(_:)), keyEquivalent: "")))

        // reading the file moves its access time and macOS then reports "changed": that must not reload (it looped, every 1.5 s)
        do {
            let n = doc.reloads
            _ = try? Data(contentsOf: doc1)
            doc.presentedItemDidChange(); spin(0.1)
            doc.presentedItemDidChange()
            spin(Double(Settings.int("pdfReloadDebounceMs")) / 1000 + 0.5)
            check("a change of the access time alone does not reload", doc.reloads == n, "reloads \(doc.reloads) was \(n)")
        }

        // zoom: steps, limits, actual size
        c.actualSize(nil)
        check("actual size is 100%", abs(view.scaleFactor - 1) < 0.001 && !view.autoScales, String(format: "%.3f", view.scaleFactor))
        c.zoomIn(nil)
        check("zoom in by the step", abs(view.scaleFactor - 1.25) < 0.001, String(format: "%.3f", view.scaleFactor))
        c.zoomOut(nil); c.zoomOut(nil)
        check("zoom out by the step", abs(view.scaleFactor - 0.8) < 0.001, String(format: "%.3f", view.scaleFactor))
        for _ in 0..<60 { c.zoomIn(nil) }
        check("zoom stops at the largest", abs(view.scaleFactor - CGFloat(Settings.number("pdfZoomMaxPercent")) / 100) < 0.001, String(format: "%.2f", view.scaleFactor))
        check("Zoom In is disabled there", !c.validateMenuItem(NSMenuItem(title: "", action: #selector(PDFWindowController.zoomIn(_:)), keyEquivalent: "")))
        for _ in 0..<60 { c.zoomOut(nil) }
        check("zoom stops at the smallest", abs(view.scaleFactor - CGFloat(Settings.number("pdfZoomMinPercent")) / 100) < 0.001, String(format: "%.2f", view.scaleFactor))
        c.fitPage(nil)
        check("fit page", view.scaleFactor > 0.1 && !view.autoScales, String(format: "%.3f", view.scaleFactor))
        c.fitWidth(nil)
        check("fit width follows the window (autoScales)", view.autoScales)

        // a file fitted to the width (how every file opens), in the middle of a page: a reload of the same file must not move it
        do {
            c.fitWidth(nil)
            if let p5 = view.document?.page(at: 4) { view.go(to: PDFDestination(page: p5, at: CGPoint(x: 20, y: 250))) }
            spin(0.3)
            let page0 = view.currentPage.flatMap { view.document?.index(for: $0) } ?? -1
            let point0 = view.currentDestination?.point ?? .zero
            let zoom0 = view.scaleFactor
            for round in 1...3 {   // three rebuilds in a row: a drift would add up
                let h0 = try! FileHandle(forWritingTo: doc1)
                try! h0.truncate(atOffset: 0); try! h0.write(contentsOf: fullBytes); try! h0.close()
                wait(6) { doc.reloads >= round }
                spin(0.4)
            }
            let page1 = view.currentPage.flatMap { view.document?.index(for: $0) } ?? -1
            let point1 = view.currentDestination?.point ?? .zero
            check("fitted to the width: same page after 3 reloads", page1 == page0, "page \(page1) was \(page0), reloads \(doc.reloads)")
            check("fitted to the width: same place after 3 reloads", abs(point1.y - point0.y) < 3 && abs(point1.x - point0.x) < 3, "\(point1) was \(point0)")
            check("fitted to the width: still fitted, same zoom", view.autoScales && abs(view.scaleFactor - zoom0) < 0.001, "\(view.scaleFactor) was \(zoom0)")
        }

        // the very top of the document (the margin above page 1): `go(to:)` cannot reach it, the viewer scrolls the rest by hand
        do {
            view.go(to: PDFDestination(page: view.document!.page(at: 0)!, at: CGPoint(x: 0, y: 1_000_000)))
            if let scroll = view.documentView?.enclosingScrollView {
                let clip = scroll.contentView
                clip.scroll(to: NSPoint(x: clip.bounds.origin.x, y: clip.documentRect.minY - clip.contentInsets.top))
                scroll.reflectScrolledClipView(clip)
            }
            spin(0.3)
            let top0 = view.currentDestination?.point ?? .zero
            let n = doc.reloads
            let h0 = try! FileHandle(forWritingTo: doc1)
            try! h0.truncate(atOffset: 0); try! h0.write(contentsOf: fullBytes); try! h0.close()
            wait(6) { doc.reloads > n }
            spin(0.4)
            let top1 = view.currentDestination?.point ?? .zero
            check("the very top of page 1: same place after a reload", abs(top1.y - top0.y) < 1 && abs(top1.x - top0.x) < 2, "\(top1) was \(top0)")
        }

        // the place that must survive a reload: page 3, zoom 125%, the point on the page
        c.actualSize(nil); c.zoomIn(nil)
        c.go(toPage: 3)
        spin(0.2)
        // somewhere in the middle of the page (at a page's very top PDFKit cannot place the point in the margin above the page,
        // so it can differ by those few points after a reload)
        if let p3 = view.document?.page(at: 2) {
            view.go(to: PDFDestination(page: p3, at: CGPoint(x: 20, y: 300)))
            spin(0.2)
        }
        func place() -> (page: Int, scale: CGFloat, point: CGPoint) {
            let d = view.currentDestination
            let page = view.currentPage.flatMap { view.document?.index(for: $0) } ?? -1
            return (page, view.scaleFactor, d?.point ?? .zero)
        }
        let before = place()
        check("went to page 3", before.page == 2, "page index \(before.page), point \(before.point)")

        func sameplace(_ name: String, expectPages: Int) {
            let now = place()
            check("\(name): the new file is shown", view.document?.pageCount == expectPages, "\(view.document?.pageCount ?? -1) pages")
            check("\(name): same page", now.page == before.page, "\(now.page)")
            check("\(name): same zoom", abs(now.scale - before.scale) < 0.001, String(format: "%.3f", now.scale))
            check("\(name): same place on the page", abs(now.point.x - before.point.x) < 2 && abs(now.point.y - before.point.y) < 2, "\(now.point) was \(before.point)")
        }

        // (a) written in place, like `cp`
        let h = try! FileHandle(forWritingTo: doc1)
        try! h.truncate(atOffset: 0); try! h.write(contentsOf: shortBytes); try! h.close()
        let a = wait(6) { doc.reloads >= 1 && view.document?.pageCount == pages - 1 }
        check("in-place rewrite is noticed", a, "reloads \(doc.reloads)")
        sameplace("in place", expectPages: pages - 1)

        // (b) replaced atomically, like `mv` or a build that writes a temporary file first
        try! fullBytes.write(to: staging)
        rename(staging.path, doc1.path)
        let b = wait(6) { view.document?.pageCount == pages }
        check("atomic replacement is noticed", b, "reloads \(doc.reloads)")
        sameplace("atomic", expectPages: pages)

        // (c) half written: the old document stays on the screen; the finished file replaces it
        let reloadsBefore = doc.reloads
        let h2 = try! FileHandle(forWritingTo: doc1)
        try! h2.truncate(atOffset: 0); try! h2.write(contentsOf: shortBytes.prefix(shortBytes.count / 2)); try! h2.synchronize()
        spin(1.2)
        check("a half-written file is not shown", doc.reloads == reloadsBefore && view.document?.pageCount == pages, "reloads \(doc.reloads), pages \(view.document?.pageCount ?? -1)")
        try! h2.write(contentsOf: shortBytes.suffix(from: shortBytes.count / 2)); try! h2.close()
        let cDone = wait(6) { view.document?.pageCount == pages - 1 }
        check("the finished file is then shown", cDone, "reloads \(doc.reloads)")
        sameplace("after the half write", expectPages: pages - 1)

        // (c2) the automatic reload switched off: the file is noticed, not shown, until View > Reload
        Settings.set("pdfAutoReload", 0)
        spin(0.2)
        let manualBefore = doc.reloads
        let hm = try! FileHandle(forWritingTo: doc1)
        try! hm.truncate(atOffset: 0); try! hm.write(contentsOf: fullBytes); try! hm.close()
        spin(Double(Settings.int("pdfReloadDebounceMs")) / 1000 + 1.0)
        check("manual: a changed file is not reloaded by itself", doc.reloads == manualBefore && view.document?.pageCount == pages - 1, "reloads \(doc.reloads), pages \(view.document?.pageCount ?? -1)")
        check("manual: the window says the file changed", doc.changedOnDisk && (c.window?.subtitle.contains("file changed") ?? false), c.window?.subtitle ?? "")
        c.reloadFile(nil)
        let manualDone = wait(6) { view.document?.pageCount == pages }
        check("manual: Reload shows the new file", manualDone && !doc.changedOnDisk && !(c.window?.subtitle.contains("file changed") ?? true), "pages \(view.document?.pageCount ?? -1), \(c.window?.subtitle ?? "")")
        sameplace("after a manual reload", expectPages: pages)
        // changed again while manual, then the automatic reload is switched back on: it catches up by itself
        let hn = try! FileHandle(forWritingTo: doc1)
        try! hn.truncate(atOffset: 0); try! hn.write(contentsOf: shortBytes); try! hn.close()
        let stale = wait(6) { doc.changedOnDisk }   // the system's notice can come late
        Settings.set("pdfAutoReload", 1)
        let caught = wait(6) { view.document?.pageCount == pages - 1 }
        check("switching the automatic reload on catches up", stale && caught && !doc.changedOnDisk, "stale \(stale), pages \(view.document?.pageCount ?? -1)")

        // the red button: the app stays (the Mac way) unless the setting says quit, and a command-line launch always quits
        do {
            let delegate = AppDelegate()
            check("the app stays after the last window by default", !delegate.applicationShouldTerminateAfterLastWindowClosed(NSApp))
            Settings.set("quitAfterLastWindow", 1)
            check("the setting makes it quit", delegate.applicationShouldTerminateAfterLastWindowClosed(NSApp))
            Settings.set("quitAfterLastWindow", 0)
            delegate.launchedWithFiles = true
            check("a command-line launch quits whatever the setting", delegate.applicationShouldTerminateAfterLastWindowClosed(NSApp))
        }

        // (d) search
        let sample = (view.document?.page(at: 0)?.string ?? "").split(whereSeparator: { !$0.isLetter }).first { $0.count >= 4 }.map(String.init)
        if let word = sample {
            c.search(word, jump: true)
            let found = wait(10) { !c.matches.isEmpty }
            check("search finds '\(word)'", found, "\(c.matches.count) so far")
            wait(10) { (c.window?.subtitle ?? "").contains("match") }
            check("every match contains the word", c.matches.allSatisfy { ($0.string ?? "").localizedCaseInsensitiveContains(word) })
            check("subtitle shows the match", (c.window?.subtitle ?? "").contains("match 1 of \(c.matches.count)"), c.window?.subtitle ?? "")
            c.step(1)
            check("next match moves on (or wraps with one match)", (c.window?.subtitle ?? "").contains("match \(c.matches.count > 1 ? 2 : 1) of"), c.window?.subtitle ?? "")
            c.clearSearch()
            check("clearing the search removes the highlights", view.highlightedSelections == nil && c.matches.isEmpty)
        } else {
            print("skip search: no word on the first page")
        }

        // (e) the thumbnails setting
        let sidebar = c.thumbs.superview?.superview   // the thumbnails sit in the sidebar's body, under the mode control
        check("thumbnails shown by default", sidebar?.isHidden == false)
        Settings.set("pdfThumbnails", 0)
        check("thumbnails hidden by the setting", sidebar?.isHidden == true)
        spin(0.2)
        // hidden is not enough: the pages must take the room (an empty dark strip stayed where the thumbnails were)
        let pagesLeft = c.pdfView.superview?.frame.minX ?? -1
        check("hidden thumbnails leave no empty strip", pagesLeft >= 0 && pagesLeft <= 2, "pages start at x \(pagesLeft)")
        Settings.set("pdfThumbnails", 1)
        check("thumbnails shown again", sidebar?.isHidden == false)
        spin(0.2)
        check("shown thumbnails make room again", (c.pdfView.superview?.frame.minX ?? 0) > 50, "pages start at x \(c.pdfView.superview?.frame.minX ?? -1)")

        // (f) the sidebar: the divider is easy to catch and the thumbnails follow it; the contents mode shows the outline
        if let split = c.window?.contentView as? NSSplitView {
            check("the divider's grab width is the setting", abs(split.dividerThickness - CGFloat(Settings.number("pdfDividerGrabPt"))) < 0.01, "\(split.dividerThickness)")
            split.setPosition(250, ofDividerAt: 0)
            spin(0.7)
            check("the thumbnails follow the divider", abs(c.thumbs.thumbnailSize.width - (250 - 36)) < 1.5, "thumbnail width \(c.thumbs.thumbnailSize.width)")
            check("the dragged width is remembered, the thumbnail width setting is left alone", abs(Settings.number("pdfSidebarWidth") - 250) < 1.5 && Settings.number("pdfThumbnailWidth") == 130, "sidebar \(Settings.number("pdfSidebarWidth")), thumbnail setting \(Settings.number("pdfThumbnailWidth"))")
            c.resetSidebarWidth(nil)
            spin(0.7)
            check("the sidebar width can be reset", abs(split.arrangedSubviews[0].frame.width - 166) < 1.5 && Settings.number("pdfSidebarWidth") == 0 && abs(c.thumbs.thumbnailSize.width - 130) < 1.5, "sidebar \(split.arrangedSubviews[0].frame.width), thumbnails \(c.thumbs.thumbnailSize.width)")
            Settings.set("pdfSidebarMode", 1)
            spin(0.3)
            check("contents mode hides the thumbnails and shows the outline", c.thumbs.isHidden && !c.contents.view.isHidden)
            if c.contents.rowCount > 0 {
                c.go(toPage: 30)
                spin(0.8)
                let at = c.contents.selectedPage
                check("the entry of the page being read is selected", at != nil && at! <= 29, "entry starts on page index \(at.map(String.init) ?? "none")")
                c.go(toPage: 3)
                spin(0.8)
                let before = c.contents.selectedPage
                check("it follows when the page changes", before != nil && before! <= 2 && before! != at, "now \(before.map(String.init) ?? "none")")
                let row = min(5, c.contents.rowCount - 1)
                c.contents.go(row: row)
                spin(0.5)
                let shown = c.pdfView.currentPage.flatMap { c.pdfView.document?.index(for: $0) }
                let wanted = c.contents.page(ofRow: row)
                check("a click on an entry goes to its page", shown != nil && wanted != nil && abs(shown! - wanted!) <= 1, "showing \(shown.map(String.init) ?? "none"), the entry is on \(wanted.map(String.init) ?? "none")")
            } else {
                print("skip contents checks: this PDF has no outline")
            }
            Settings.set("pdfSidebarMode", 0)
            spin(0.2)
            check("thumbnails again after contents mode", !c.thumbs.isHidden && c.contents.view.isHidden)
        }
        Settings.set("pdfDisplayMode", 0)
        check("page layout setting applied live", view.displayMode == .singlePage)

        doc.close()
        print(String(format: "%.0f MB resident at the end", residentMB()))
        print(failures == 0 ? "PDF SMOKE OK" : "PDF SMOKE FAILED (\(failures))")
        exit(failures == 0 ? 0 : 1)
    }

    static func bench(_ path: String) {
        let url = URL(fileURLWithPath: path)
        let size = ((try? fm_size(url)) ?? 0)
        print(String(format: "%@  %.1f MB on disk, %.0f MB resident before", url.lastPathComponent, Double(size) / 1_048_576, residentMB()))
        let t0 = Date()
        guard let doc = PDFDocument(url: url) else { print("FAIL cannot open"); exit(1) }
        print(String(format: "PDFDocument(url:) %.0f ms, %d pages", Date().timeIntervalSince(t0) * 1000, doc.pageCount))
        let mid = doc.page(at: doc.pageCount / 2)!
        for zoom in [1.0, 4.0, 16.0] {
            let b = mid.bounds(for: .cropBox)
            let t = Date()
            let image = mid.thumbnail(of: CGSize(width: min(8000, b.width * zoom), height: min(8000, b.height * zoom)), for: .cropBox)
            print(String(format: "render the middle page at %.0fx: %.0f ms (%.0fx%.0f px)", zoom, Date().timeIntervalSince(t) * 1000, image.size.width, image.size.height))
        }
        print(String(format: "%.0f MB resident after", residentMB()))
    }

    private static func fm_size(_ url: URL) throws -> Int {
        (try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) ?? 0
    }
}
