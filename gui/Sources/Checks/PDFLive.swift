import Cocoa
import PDFKit

/// `pdfmdedit --live-pdf FILE [scenario]`: opens FILE in a real, shown window (never activated: the author's focus stays where it is)
/// and does what a hand does, in the app's own process: clicks a thumbnail, scrolls fast, zooms. While it runs a timer measures how long
/// the main thread was blocked (a frozen window shows as one long gap), and the page the view shows is sampled, so a runaway scroll is a
/// number and not a feeling. Prints one line per step.
enum PDFLive {
    static var gaps: [Double] = []
    static var last = Date()

    static func spin(_ s: Double) { PDFSmoke.spin(s) }

    static func pageIndex(_ c: PDFWindowController) -> Int {
        guard let p = c.pdfView.currentPage, let d = c.pdfView.document else { return -1 }
        return d.index(for: p)
    }

    static func maxGap() -> Double { let m = gaps.max() ?? 0; gaps = []; return m }

    static func click(_ view: NSView, at p: NSPoint) {
        guard let w = view.window else { return }
        let inWindow = view.convert(p, to: nil)
        let hit = w.contentView?.hitTest(w.contentView!.convert(inWindow, from: nil))
        print("   click at window \(inWindow): hit \(hit.map { String(describing: type(of: $0)) } ?? "nothing"), key window \(w.isKeyWindow), app active \(NSApp.isActive)")
        for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
            if let e = NSEvent.mouseEvent(with: type, location: inWindow, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                                          windowNumber: w.windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: 1) {
                w.sendEvent(e)
            }
        }
    }

    static func run(_ args: [String]) {
        guard let i = args.firstIndex(of: "--live-pdf"), i + 1 < args.count else { exit(2) }
        let url = URL(fileURLWithPath: args[i + 1])
        NSApplication.shared.setActivationPolicy(.accessory)
        guard let doc = PDFSmoke.open(url), let c = doc.controller, let window = c.window else { print("FAIL open"); exit(1) }
        window.setFrameOrigin(NSPoint(x: 40, y: 60))
        doc.showWindows()
        window.orderFrontRegardless()
        if args.contains("--key") { NSApp.activate(ignoringOtherApps: true); window.makeKeyAndOrderFront(nil) }
        spin(1.0)
        // a timer that only fires when the main thread is free: the gaps between its ticks are the stalls
        let t = Timer(timeInterval: 0.01, repeats: true) { _ in
            let now = Date(); gaps.append(now.timeIntervalSince(last) * 1000); last = now
        }
        RunLoop.current.add(t, forMode: .common)
        last = Date(); _ = maxGap()
        let n = c.pdfView.document?.pageCount ?? 0
        print("window id \(window.windowNumber), \(n) pages, page \(pageIndex(c) + 1), zoom \(Int(c.pdfView.scaleFactor * 100))%, autoScales \(c.pdfView.autoScales)")

        let steps = args.last.flatMap { ["thumb", "scroll", "zoom", "hide", "contents", "all"].contains($0) ? $0 : nil } ?? "all"

        if steps == "thumb" || steps == "all" {
            let th = c.thumbs
            print("thumbnail view \(th.frame), thumbnail size \(th.thumbnailSize)")
            func dump(_ v: NSView, _ d: Int) { print(String(repeating: "  ", count: d) + "\(type(of: v)) \(v.frame) flipped \(v.isFlipped)"); if d < 4 { for s in v.subviews.prefix(4) { dump(s, d + 1) } } }
            dump(th, 0)
            func find(_ v: NSView) -> NSView? { if v is NSCollectionView { return v }; for s in v.subviews { if let f = find(s) { return f } }; return nil }
            guard let items = find(th) else { print("no collection view"); exit(1) }
            let slot = items.bounds.height / CGFloat(max(1, n))
            for target in [2, 4, 1] {   // the 3rd, 5th and 2nd thumbnail
                let before = pageIndex(c)
                click(items, at: NSPoint(x: items.bounds.midX, y: (CGFloat(target) + 0.5) * slot))   // flipped: y grows downwards
                var trail: [Int] = []
                for _ in 0..<30 { spin(0.1); trail.append(pageIndex(c) + 1) }
                print("click on thumbnail \(target + 1) (page \(before + 1) before): pages seen every 100 ms: \(trail)  longest stall \(Int(maxGap())) ms")
            }
        }
        if steps == "hide" {
            func frames(_ label: String) {
                guard let sp = window.contentView as? NSSplitView else { print("no split"); return }
                print("\(label): " + sp.arrangedSubviews.map { "\(type(of: $0)) \(Int($0.frame.minX))..\(Int($0.frame.maxX)) hidden \($0.isHidden)" }.joined(separator: " | ") + "  divider \(sp.isSubviewCollapsed(sp.arrangedSubviews[0]) ? "collapsed" : "open"), pdfView \(c.pdfView.frame)")
            }
            frames("shown")
            Settings.set("pdfThumbnails", 0); spin(0.5); frames("hidden")
            if let sp = window.contentView as? NSSplitView {
                print("   divider thickness \(sp.dividerThickness), colour \(sp.dividerColor), content \(sp.frame), window \(window.frame.size)")
                func walk(_ v: NSView, _ d: Int) {
                    let r = v.convert(v.bounds, to: nil)
                    print(String(repeating: " ", count: d * 2) + "\(type(of: v)) x \(Int(r.minX))..\(Int(r.maxX)) y \(Int(r.minY))..\(Int(r.maxY)) hidden \(v.isHidden)")
                    if d < 5 { for s in v.subviews { walk(s, d + 1) } }
                }
                walk(window.contentView!.superview ?? sp, 0)
            }
            Settings.set("pdfThumbnails", 1); spin(0.5); frames("shown again")
            if let out = ProcessInfo.processInfo.environment["PDFLIVE_SHOT"] {   // a screenshot of the real window, for an artefact that no view dump shows
                Settings.set("pdfThumbnails", 0); spin(0.8)
                let p = Process(); p.launchPath = "/usr/sbin/screencapture"; p.arguments = ["-x", "-o", "-l", String(window.windowNumber), out]
                try? p.run(); p.waitUntilExit(); print("screenshot \(out) status \(p.terminationStatus)")
            }
            Settings.set("pdfThumbnails", 0); spin(0.5); frames("hidden again")
        }
        if steps == "contents" {
            func shot(_ name: String) {
                guard let out = ProcessInfo.processInfo.environment["PDFLIVE_SHOT"] else { return }
                let p = Process(); p.launchPath = "/usr/sbin/screencapture"; p.arguments = ["-x", "-o", "-l", String(window.windowNumber), out + name]
                try? p.run(); p.waitUntilExit()
            }
            _ = maxGap()
            let t0 = Date()
            Settings.set("pdfSidebarMode", 1)
            spin(0.3)
            print("contents mode: \(c.contents.rowCount) rows after \(Int(Date().timeIntervalSince(t0) * 1000)) ms (0.3 s of it waiting), longest stall \(Int(maxGap())) ms")
            for page in [1, 1200, 3000] where page <= n {
                let t = Date(); c.go(toPage: page); spin(0.7)
                print("page \(page): selected entry on page index \(c.contents.selectedPage.map(String.init) ?? "none"), longest stall \(Int(maxGap())) ms")
                _ = t; shot("-contents-\(page).png")
            }
            let t1 = Date(); c.contents.go(row: min(40, max(0, c.contents.rowCount - 1))); spin(0.4)
            print("click on row 40: now page \(pageIndex(c) + 1), entry is on index \(c.contents.page(ofRow: 40).map(String.init) ?? "none"), \(Int(Date().timeIntervalSince(t1) * 1000)) ms, longest stall \(Int(maxGap())) ms")
        }
        if steps == "scroll" || steps == "all" {
            guard let scroll = c.pdfView.documentView?.enclosingScrollView else { print("no scroll view"); exit(1) }
            let clip = scroll.contentView
            let view = c.pdfView
            // real wheel events, posted to this process only (never to whatever the author is typing in)
            let rect = view.convert(view.bounds, to: nil)
            let onScreen = window.convertToScreen(rect)
            let screenH = NSScreen.screens[0].frame.height
            let at = CGPoint(x: onScreen.midX, y: screenH - onScreen.midY)   // CGEvent coordinates start at the top left
            func flick(_ lines: Int32) {
                if let e = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1, wheel1: lines, wheel2: 0, wheel3: 0) {
                    e.location = at
                    if let ns = NSEvent(cgEvent: e) { view.scrollWheel(with: ns) }
                }
            }
            for _ in 0..<5 { flick(-10); spin(0.02) }
            spin(0.5); _ = maxGap()
            print("   after 5 small flicks: y \(Int(clip.bounds.origin.y)), page \(pageIndex(c) + 1)")
            var trail: [(Int, Int)] = []
            for k in 0..<150 {   // 150 wheel flicks of 60 px, 16 ms apart
                flick(60)
                spin(0.016)
                if k % 10 == 9 { trail.append((pageIndex(c) + 1, Int(maxGap()))) }
            }
            print("fast scroll, page and longest stall per 10 flicks: \(trail)")
            spin(2); print("2 s later: page \(pageIndex(c) + 1), longest stall \(Int(maxGap())) ms")
        }
        if steps == "zoom" || steps == "all" {
            for (name, action) in [("zoom in", { c.zoomIn(nil) }), ("zoom in", { c.zoomIn(nil) }), ("zoom out", { c.zoomOut(nil) }),
                                   ("actual size", { c.actualSize(nil) }), ("fit width", { c.fitWidth(nil) }), ("fit page", { c.fitPage(nil) })] as [(String, () -> Void)] {
                _ = maxGap()
                action()
                spin(0.5)
                print("\(name): zoom \(Int(c.pdfView.scaleFactor * 100))%, autoScales \(c.pdfView.autoScales), page \(pageIndex(c) + 1), longest stall \(Int(maxGap())) ms")
            }
        }
        print("rss \(Int(residentMB())) MB")
        exit(0)
    }
}
