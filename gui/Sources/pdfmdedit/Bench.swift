import Cocoa

/// Headless benchmark: `pdfmdedit --bench [--mb N | --file F] [--keys N] [--paste-mb N] [--no-highlight] [--tk 1|2]`.
/// The window is never shown (activation policy "prohibited": no Dock icon, no focus). "Paint" is
/// `cacheDisplay` into a bitmap: the text view lays out and draws the visible area, like a screen refresh
/// without the compositor. The numbers compare variants with each other; they are not a CotEditor measurement.
enum Bench {
    static func now() -> UInt64 { DispatchTime.now().uptimeNanoseconds }
    static func ms(since t: UInt64) -> Double { Double(now() - t) / 1e6 }

    static func option(_ name: String, _ args: [String]) -> String? {
        guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
        return args[i + 1]
    }

    /// Deterministic Markdown of about `mb` megabytes: headings, lists, prose, code fences, math, links.
    static func generate(mb: Double) -> String {
        var out = ""
        out.reserveCapacity(Int(mb * 1_000_000) + 4096)
        out += "---\ntitle: Benchmark\nauthor: nobody\n---\n\n"
        var seed: UInt64 = 12345
        func next() -> Int { seed = seed &* 6364136223846793005 &+ 1442695040888963407; return Int(seed >> 33) }
        let words = ["alpha", "beta", "gamma", "delta", "spectrum", "peak", "solvent", "yield", "mixture", "reaction",
                     "table", "figure", "sample", "mass", "mole", "buffer", "titration", "[link](http://x.org)", "`code`", "**bold**", "$x^2$"]
        var section = 0
        while Double(out.utf8.count) < mb * 1_000_000 {
            section += 1
            out += "## Section \(section)\n\n"
            for _ in 0..<(3 + next() % 4) {
                var line = ""
                for _ in 0..<(14 + next() % 30) { line += words[next() % words.count] + " " }
                out += line + "\n\n"
            }
            out += "- first item \(section)\n- second item\n  - nested **item**\n\n"
            out += "```python\nfor i in range(\(section)):\n    print(i)  # not a heading\n```\n\n"
            out += "> a quote with $E=mc^2$ in it\n\n"
        }
        return out
    }

    struct Stats {
        var values: [Double] = []
        mutating func add(_ v: Double) { values.append(v) }
        var line: String {
            guard !values.isEmpty else { return "-" }
            let s = values.sorted()
            func q(_ p: Double) -> Double { s[min(s.count - 1, Int(Double(s.count) * p))] }
            return String(format: "median %.2f  p95 %.2f  max %.2f ms  (n=%d)", q(0.5), q(0.95), s.last!, s.count)
        }
    }

    static func paint(_ parts: EditorParts) {
        let rep = parts.scroll.bitmapImageRepForCachingDisplay(in: parts.scroll.bounds)!
        parts.scroll.cacheDisplay(in: parts.scroll.bounds, to: rep)
    }

    /// What AppKit redraws after a key press: the caret's line (a band three lines high), not the whole window.
    static func paintCaretBand(_ parts: EditorParts) {
        let tv = parts.textView
        guard let window = tv.window else { paint(parts); return }
        let screenRect = tv.firstRect(forCharacterRange: tv.selectedRange(), actualRange: nil)
        let inWindow = window.convertFromScreen(screenRect)
        var band = parts.scroll.convert(inWindow, from: nil)
        band = NSRect(x: 0, y: band.minY - band.height, width: parts.scroll.bounds.width, height: band.height * 3)
        band = band.intersection(parts.scroll.bounds)
        guard !band.isEmpty, let rep = parts.scroll.bitmapImageRepForCachingDisplay(in: band) else { paint(parts); return }
        parts.scroll.cacheDisplay(in: band, to: rep)
    }

    static func peakRSSMB() -> Double {
        var u = rusage(); getrusage(RUSAGE_SELF, &u)
        return Double(u.ru_maxrss) / 1_048_576
    }

    static func run(_ args: [String]) {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let tk2 = (option("--tk", args) ?? String(Settings.int("textKit"))) == "2"
        let highlight = !args.contains("--no-highlight")
        let keys = Int(option("--keys", args) ?? "") ?? 300
        let pasteMB = Double(option("--paste-mb", args) ?? "") ?? 5

        let text: String
        if let f = option("--file", args) {
            text = (try? String(contentsOfFile: f, encoding: .utf8)) ?? ""
            if text.isEmpty { print("cannot read \(f)"); exit(1) }
        } else {
            text = generate(mb: Double(option("--mb", args) ?? "") ?? 10)
        }
        let bytes = text.utf8.count
        let lines = text.utf8.reduce(0) { $0 + ($1 == 0x0A ? 1 : 0) }

        let frame = NSRect(x: 0, y: 0, width: 1100, height: 800)
        let window = NSWindow(contentRect: frame, styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let parts = makeEditor(frame: frame, highlight: highlight, textKit2: tk2)
        window.contentView = parts.scroll
        let tv = parts.textView
        let variant = (tk2 ? "TextKit 2" : "TextKit 1, non-contiguous layout") + (highlight ? ", colours on" : ", colours off")

        print("variant : \(variant)")
        print(String(format: "text    : %.1f MB, %d lines", Double(bytes) / 1e6, lines))

        var t = now()
        tv.string = text
        let tSet = ms(since: t)
        t = now(); paint(parts); let tFirst = ms(since: t)
        t = now(); parts.highlighter?.highlightNow(); let tHigh = ms(since: t)
        print(String(format: "open    : set text %.1f ms, first layout+paint %.1f ms, first colour pass %.1f ms", tSet, tFirst, tHigh))

        func jump(to fraction: Double, _ label: String) {
            let n = (tv.string as NSString).length
            let loc = Int(Double(n) * fraction)
            let line = (tv.string as NSString).lineRange(for: NSRange(location: min(loc, n - 1), length: 0))
            let t0 = now()
            tv.setSelectedRange(NSRange(location: line.location, length: 0))
            tv.scrollRangeToVisible(NSRange(location: line.location, length: 0))
            paint(parts)
            let tScroll = ms(since: t0)
            let t1 = now(); parts.highlighter?.highlightNow(); let tCol = ms(since: t1)
            print(String(format: "jump    : %-8s layout+paint %.1f ms, colour pass %.1f ms", (label as NSString).utf8String!, tScroll, tCol))
        }
        jump(to: 0.5, "middle")
        jump(to: 0.99, "end")
        jump(to: 0.5, "middle")

        // typing: one character at the caret, then layout + paint, like a key press followed by a screen refresh
        var keyStats = Stats(), highStats = Stats()
        for k in 0..<keys {
            let t0 = now()
            tv.insertText(k % 7 == 6 ? "\n" : "x", replacementRange: NSRange(location: NSNotFound, length: 0))
            paintCaretBand(parts)
            keyStats.add(ms(since: t0))
            if k % 10 == 9 {   // the debounced colour pass, run explicitly so that it is timed
                let t1 = now(); parts.highlighter?.highlightNow(); highStats.add(ms(since: t1))
            }
        }
        print("typing  : \(keyStats.line)   [insert + repaint of the caret line]")
        if highlight { print("colours : pass after typing: \(highStats.line)") }

        // a big paste at the caret
        let chunk = generate(mb: pasteMB)
        let t2 = now()
        tv.insertText(chunk, replacementRange: NSRange(location: NSNotFound, length: 0))
        let tIns = ms(since: t2)
        paint(parts)
        let tPaste = ms(since: t2)
        let t3 = now(); parts.highlighter?.highlightNow(); let tPasteHigh = ms(since: t3)
        print(String(format: "paste   : %.0f MB: insert %.1f ms, insert+paint %.1f ms, colour pass %.1f ms", pasteMB, tIns, tPaste, tPasteHigh))

        // typing again after the paste
        var afterStats = Stats()
        for _ in 0..<min(keys, 100) {
            let t0 = now()
            tv.insertText("y", replacementRange: NSRange(location: NSNotFound, length: 0))
            paintCaretBand(parts)
            afterStats.add(ms(since: t0))
        }
        print("typing after paste: \(afterStats.line)")

        // scrolling through the document in screen-sized steps
        var scrollStats = Stats()
        let clip = parts.scroll.contentView
        var y: CGFloat = 0
        for _ in 0..<60 {
            let t0 = now()
            clip.scroll(to: NSPoint(x: 0, y: y))
            parts.scroll.reflectScrolledClipView(clip)
            paint(parts)
            scrollStats.add(ms(since: t0))
            y += 700
        }
        print("scrolling (60 screens): \(scrollStats.line)")
        print(String(format: "peak memory: %.0f MB", peakRSSMB()))
        let engineNow = tv.textLayoutManager != nil ? 2 : 1
        print("text engine at the end: \(engineNow)" + (engineNow == (tk2 ? 2 : 1) ? "" : "   <-- FELL BACK, the numbers above are not for the engine asked for"))
    }
}

/// `pdfmdedit --smoke FILE`: opens FILE through the real document path (NSDocumentController, window controller)
/// without ever showing a window (it asserts so), edits it, scrolls it, and checks that the colours stay on screen and the bytes saved are right.
/// `pdfmdedit --smoke-save DIR`: real saves to disk of files with different extensions and encodings (the files are created in DIR).
enum Smoke {
    static func spin(_ seconds: Double) { RunLoop.current.run(until: Date().addingTimeInterval(seconds)) }

    static func open(_ url: URL) -> EditorDocument? {
        var result: EditorDocument?
        var done = false
        // display: false, and the window controller is made by hand and never shown: display: true put real windows on
        // the author's screen (an app with the "prohibited" policy cannot be activated, so they could not be closed).
        NSDocumentController.shared.openDocument(withContentsOf: url, display: false) { doc, _, error in
            result = doc as? EditorDocument
            if let error { print("open error: \(error)") }
            done = true
        }
        while !done { spin(0.05) }
        if let doc = result, doc.windowControllers.isEmpty { doc.makeWindowControllers() }
        return result
    }

    /// Pixels that are neither the background, nor the plain text, nor an anti-aliased blend of the two: the syntax colours.
    /// (A saturation threshold cannot do it: a light theme has dark, nearly grey syntax colours on a pale background.)
    /// The distance is measured from the straight line in RGB between the background and the text colour, in 0...255 units.
    static let notTextDistance = 28.0

    static func colouredPixels(_ scroll: NSScrollView) -> Int {
        guard let rep = scroll.bitmapImageRepForCachingDisplay(in: scroll.bounds) else { return -1 }
        scroll.cacheDisplay(in: scroll.bounds, to: rep)
        func rgb(_ c: NSColor) -> [Double] {
            var out: [Double] = [0, 0, 0]
            scroll.effectiveAppearance.performAsCurrentDrawingAppearance {
                if let d = c.usingColorSpace(.deviceRGB) { out = [d.redComponent * 255, d.greenComponent * 255, d.blueComponent * 255] }
            }
            return out
        }
        let bg = rgb(Palette.background), fg = rgb(Palette.text)
        let axis = zip(fg, bg).map { $0 - $1 }
        let axisLen2 = axis.reduce(0) { $0 + $1 * $1 }
        var n = 0
        for y in 0..<rep.pixelsHigh { for x in 0..<rep.pixelsWide {
            guard let c = rep.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
            let p = [c.redComponent * 255, c.greenComponent * 255, c.blueComponent * 255]
            let rel = zip(p, bg).map { $0 - $1 }
            let t = axisLen2 > 0 ? max(0, min(1, zip(rel, axis).reduce(0) { $0 + $1.0 * $1.1 } / axisLen2)) : 0
            let dist = (0..<3).reduce(0.0) { $0 + pow(rel[$1] - t * axis[$1], 2) }.squareRoot()
            if dist > notTextDistance { n += 1 }
        } }
        return n
    }

    static func scroll(_ parts: EditorParts, to y: CGFloat) {
        parts.scroll.contentView.scroll(to: NSPoint(x: 0, y: y))
        parts.scroll.reflectScrolledClipView(parts.scroll.contentView)
        spin(Double(Settings.int("scrollDelayMs") + Settings.int("highlightDelayMs")) / 1000 + 0.2)   // the debounced colour pass runs
    }

    static func run(_ path: String) {
        NSApplication.shared.setActivationPolicy(.prohibited)
        if let i = CommandLine.arguments.firstIndex(of: "--appearance"), i + 1 < CommandLine.arguments.count {
            NSApplication.shared.appearance = NSAppearance(named: CommandLine.arguments[i + 1] == "dark" ? .darkAqua : .aqua)
        }
        let started = Bench.now()
        let url = URL(fileURLWithPath: path)
        guard let doc = open(url), let controller = doc.controller else { print("FAIL open"); exit(1) }
        let parts = controller.parts!
        let engine = parts.textView.textLayoutManager != nil ? 2 : 1
        print(String(format: "open document + window + first colours: %.0f ms (after the app object exists; process start not included)", Bench.ms(since: started)))
        print("appearance \(NSApplication.shared.effectiveAppearance.name.rawValue), theme \(Palette.lightTheme?.name ?? "none") / \(Palette.darkTheme?.name ?? "none")")
        print("window visible: \(controller.window?.isVisible ?? false)  (must be false: a smoke test never shows a window)")
        if controller.window?.isVisible == true { print("FAIL a window was shown"); exit(1) }
        print("text engine \(engine), window controllers \(doc.windowControllers.count), title \(controller.window?.title ?? "-")")
        parts.scroll.frame = NSRect(x: 0, y: 0, width: 900, height: 700)
        parts.highlighter?.highlightNow()
        var failures = 0
        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            print("\(ok ? "ok  " : "FAIL") \(name) \(detail)")
            if !ok { failures += 1 }
        }

        let original = try! Data(contentsOf: url)
        let first = colouredPixels(parts.scroll)
        check("colours on screen after load", first > 0, "(\(first) px)")
        check("round trip identical", (try! doc.data(ofType: "Markdown and text")) == original)

        // (a) an edit, then the debounced pass, then a repaint
        parts.textView.insertText("\n\n# New heading\n\n", replacementRange: NSRange(location: 0, length: 0))
        spin(Double(Settings.int("highlightDelayMs")) / 1000 + 0.3)
        let afterEdit = colouredPixels(parts.scroll)
        check("colours after an edit", afterEdit * 10 >= first * 7, "(\(afterEdit) px, was \(first); the insert pushes some lines off the screen)")
        check("document marked edited", doc.isDocumentEdited)
        doc.undoManager?.undo(); spin(0.1)
        check("undo restores the bytes", (try! doc.data(ofType: "Markdown and text")) == original)
        spin(Double(Settings.int("highlightDelayMs")) / 1000 + 0.3)
        let afterUndo = colouredPixels(parts.scroll)
        check("colours after undo", abs(afterUndo - first) <= first / 20, "(\(afterUndo) px, was \(first))")

        // (b) scroll within the coloured margin and back, then far away and back
        let height = parts.textView.frame.height
        if height > 4000 {
            scroll(parts, to: 1500); let near = colouredPixels(parts.scroll)
            scroll(parts, to: 0); let back = colouredPixels(parts.scroll)
            check("colours after scrolling a little and back", near > 0 && abs(back - first) <= first / 20, "(there \(near) px, back \(back) px, was \(first))")
            scroll(parts, to: height * 0.6); let far = colouredPixels(parts.scroll)
            check("colours far from the top", far > 0, "(\(far) px)")
            scroll(parts, to: 0); let home = colouredPixels(parts.scroll)
            check("colours back at the top", abs(home - first) <= first / 20, "(\(home) px, was \(first))")
        } else {
            print("skip scrolling checks: the document is only \(Int(height)) pt tall (use a larger file)")
        }
        check("still the same text engine", (parts.textView.textLayoutManager != nil ? 2 : 1) == engine)
        print(failures == 0 ? "SMOKE OK" : "SMOKE FAILED (\(failures))")
        exit(failures == 0 ? 0 : 1)
    }

    static func save(_ dir: String) {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let base = URL(fileURLWithPath: dir)
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        let utf8Text = "# Zażółć gęślą\n\nplain ünïcode text\n"
        // name, original bytes, expected bytes after inserting "EDIT " at the top
        let cases: [(String, Data, Data)] = [
            ("a.tex", utf8Text.data(using: .utf8)!, ("EDIT " + utf8Text).data(using: .utf8)!),
            ("b.hst", utf8Text.data(using: .utf8)!, ("EDIT " + utf8Text).data(using: .utf8)!),
            ("c_noext", utf8Text.data(using: .utf8)!, ("EDIT " + utf8Text).data(using: .utf8)!),
            ("d.md", "café ünï\n".data(using: .isoLatin1)!, "EDIT café ünï\n".data(using: .isoLatin1)!),
            ("e.yaml.bak", "key: value\n".data(using: .utf8)!, "EDIT key: value\n".data(using: .utf8)!),
        ]
        var failures = 0
        for (name, original, expected) in cases {
            let url = base.appendingPathComponent(name)
            try! original.write(to: url)
            guard let doc = open(url), let controller = doc.controller else { print("FAIL \(name): did not open"); failures += 1; continue }
            controller.parts.textView.insertText("EDIT ", replacementRange: NSRange(location: 0, length: 0))
            spin(0.2)
            var err: Error?
            var done = false
            doc.save(to: url, ofType: "Markdown and text", for: .saveOperation) { e in err = e; done = true }
            while !done { spin(0.05) }
            let onDisk = (try? Data(contentsOf: url)) ?? Data()
            let ok = err == nil && onDisk == expected
            print("\(ok ? "ok  " : "FAIL") save \(name) (\(doc.fileType ?? "no type"), \(doc.encoding == .utf8 ? "utf-8" : "latin-1")) \(err.map { "error: \($0)" } ?? "") edited-after-save: \(doc.isDocumentEdited)")
            if !ok { failures += 1 }
            doc.close()
        }
        print(failures == 0 ? "SAVE OK" : "SAVE FAILED (\(failures))")
        exit(failures == 0 ? 0 : 1)
    }
}
