import Cocoa
import PDFKit
import WebKit

/// `pdfmdedit --smoke-studio`: the editor window with the preview pane (never shown), against the real pandoc. Checks that the page is made
/// from the text in the window and not from the file (an unsaved edit shows), that typing is coalesced, that math, a picture beside the
/// document and an `#anchor` link work, that a script in the text does not run, that a pandoc error is said and the old page stays, the
/// switch to the PDF of a build, following the scrolling of the text, hiding the pane, and the setting that starts every window as a studio.
enum StudioSmoke {
    static func spin(_ s: Double) { RunLoop.current.run(until: Date().addingTimeInterval(s)) }

    static func js(_ page: HTMLPageView, _ code: String) -> Any? {
        var value: Any?
        var done = false
        page.web.evaluateJavaScript(code) { r, _ in value = r; done = true }
        _ = PDFSmoke.wait(5) { done }
        return value
    }

    static func run() {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let domain = "io.github.aliperdehan.pdfmdedit.smokestudio"
        UserDefaults.standard.removePersistentDomain(forName: domain)
        Settings.store = UserDefaults(suiteName: domain)!
        Settings.store.set(120, forKey: "studioPreviewDelayMs")
        Settings.store.set(60, forKey: "studioScrollDelayMs")
        defer { UserDefaults.standard.removePersistentDomain(forName: domain) }

        var failures = 0
        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            print("\(ok ? "ok  " : "FAIL") \(name) \(detail)")
            if !ok { failures += 1 }
        }
        let fm = FileManager.default
        let dir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("pdfmdedit-smoke-studio-\(getpid())")
        try! fm.createDirectory(at: dir.appendingPathComponent("figs"), withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: dir) }

        // a picture beside the document, found through a relative path
        let image = NSImage(size: NSSize(width: 40, height: 30), flipped: false) { r in NSColor.red.setFill(); r.fill(); return true }
        let tiff = image.tiffRepresentation!
        try! NSBitmapImageRep(data: tiff)!.representation(using: .png, properties: [:])!.write(to: dir.appendingPathComponent("figs/pic.png"))
        var text = "# Studio test\n\nOn disk only: ON-DISK-TEXT\n\n![a picture](figs/pic.png)\n\nMath: $x^2 + y^2 = z^2$\n\n[jump to the end](#the-end)\n\n"
        text += "<script>document.body.setAttribute('data-ran', '1')</script>\n\n"
        for i in 1...150 { text += "Paragraph \(i): the quick brown fox jumps over the lazy dog, again and again.\n\n" }
        text += "## The end\n\nlast words\n"
        let md = dir.appendingPathComponent("studio doc.md")
        try! text.write(to: md, atomically: true, encoding: .utf8)

        check("pandoc is found", PdfmdTool.pandoc() != nil, PdfmdTool.pandoc() ?? "nil")
        check("shellWords: quotes and backslashes", shellWords("--a 'b c' \"d e\" f\\ g ~") == ["--a", "b c", "d e", "f g", NSHomeDirectory()], "\(shellWords("--a 'b c' \"d e\" f\\ g ~"))")

        guard let doc = Smoke.open(md), let c = doc.controller else { print("FAIL open"); exit(1) }
        let s = c.studio
        check("the window starts without a pane", !s.isShown)
        let plainContent = c.window?.contentView
        s.show(growWindow: false)
        check("the pane is shown", s.isShown && c.window?.contentView is NSSplitView)
        guard let pane = s.pane else { print("FAIL no pane"); exit(1) }
        func page() -> HTMLPageView { pane.html }
        check("the first page is made", PDFSmoke.wait(20) { s.renders >= 1 && page().loads >= 1 }, "renders \(s.renders) loads \(page().loads) \(s.lastOutput?.error ?? "")")
        print(String(format: "   first render %.2f s", s.lastOutput?.seconds ?? -1))
        check("the page has the heading", (js(page(), "document.querySelector('h1') && document.querySelector('h1').innerText") as? String) == "Studio test")
        check("a script in the text did not run", (js(page(), "document.body.getAttribute('data-ran')") is NSNull) || js(page(), "document.body.getAttribute('data-ran')") == nil)
        check("math became MathML", (js(page(), "document.querySelector('math') !== null") as? Bool) == true)
        check("a picture beside the document loads", PDFSmoke.wait(10) { (js(page(), "document.images.length > 0 && document.images[0].naturalWidth") as? Double ?? 0) > 0 }, "\(js(page(), "document.images.length > 0 ? document.images[0].src : 'none'") ?? "nil")")

        // the text in the window, not the file
        let tv = c.parts.textView
        let r0 = s.renders
        tv.insertText("UNSAVED-WORD\n\n", replacementRange: NSRange(location: 0, length: 0))
        check("the edit is not saved", ((try? String(contentsOf: md, encoding: .utf8)) ?? "").contains("UNSAVED-WORD") == false)
        check("the preview shows an unsaved edit", PDFSmoke.wait(15) { s.renders > r0 && page().loads > 1 })
        spin(0.4)
        check("the page has it", (js(page(), "document.body.innerText.indexOf('UNSAVED-WORD') >= 0") as? Bool) == true)
        print(String(format: "   a later render %.2f s (pandoc found and cached already), warnings: %@", s.lastOutput?.seconds ?? -1, s.lastOutput?.error.isEmpty == false ? "yes" : "none"))
        check("the render is quick once pandoc is found", (s.lastOutput?.seconds ?? 9) < 1.0)
        check("and makes no warning", s.lastOutput?.error.isEmpty == true, s.lastOutput?.error ?? "")

        // a burst of typing is one or two renders, not ten
        let r1 = s.renders
        for ch in "abcdefgh" { tv.insertText(String(ch), replacementRange: NSRange(location: 0, length: 0)); spin(0.02) }
        _ = PDFSmoke.wait(15) { s.renders > r1 && !(s.pane == nil) }
        spin(1.0)
        check("a burst of 8 key presses makes at most 2 renders", s.renders - r1 >= 1 && s.renders - r1 <= 2, "renders \(s.renders - r1)")

        // an anchor link stays on the page
        _ = js(page(), "window.scrollTo(0, 0)")
        _ = js(page(), "document.querySelector(\"a[href$='#the-end']\").click()")
        spin(0.6)
        check("an anchor link scrolls the preview", ((js(page(), "window.scrollY") as? Double) ?? 0) > 1000)
        check("and it is still the same page", page().web.url?.pathExtension == "html" && page().web.url?.path.contains("/preview/") == true, page().web.url?.absoluteString ?? "nil")

        // following the text's scrolling
        _ = js(page(), "window.scrollTo(0, 0)")
        spin(0.2)
        let scroll = c.parts.scroll
        let room = scroll.documentView!.frame.height - scroll.contentView.bounds.height
        scroll.contentView.scroll(to: NSPoint(x: 0, y: room * 0.5))
        scroll.reflectScrolledClipView(scroll.contentView)
        spin(0.6)
        let total = (js(page(), "document.documentElement.scrollHeight - window.innerHeight") as? Double) ?? 1
        let y = (js(page(), "window.scrollY") as? Double) ?? -1
        check("the preview follows the text to the middle", abs(y / max(1, total) - 0.5) < 0.1, String(format: "%.2f of the page", y / max(1, total)))

        // an error is said, the old page stays
        Settings.store.set("--no-such-option", forKey: "htmlPreviewArguments")
        let r2 = s.renders
        tv.insertText("x", replacementRange: NSRange(location: 0, length: 0))
        check("a pandoc error is reported", PDFSmoke.wait(15) { s.renders > r2 } && s.lastOutput?.file == nil && s.lastOutput?.error.isEmpty == false, s.lastOutput?.error ?? "")
        check("the status line says error", pane.status.stringValue.hasPrefix("error"), pane.status.stringValue)
        check("the old page is still there", (js(page(), "document.body.innerText.indexOf('UNSAVED-WORD') >= 0") as? Bool) == true)
        Settings.store.removeObject(forKey: "htmlPreviewArguments")
        let r3 = s.renders
        tv.insertText("y", replacementRange: NSRange(location: 0, length: 0))
        check("it recovers when the option is gone", PDFSmoke.wait(15) { s.renders > r3 } && s.lastOutput?.file != nil)

        // the PDF of a build
        let pdfFile = dir.appendingPathComponent("studio doc.pdf")
        let pdf = PDFDocument()
        for _ in 0..<3 { pdf.insert(PDFPage(image: NSImage(size: NSSize(width: 200, height: 260), flipped: false) { r in NSColor.white.setFill(); r.fill(); return true })!, at: pdf.pageCount) }
        pdf.write(to: pdfFile)
        s.showBuilt(pdfFile)
        check("a build's PDF is shown in the pane", pane.pdf.document?.pageCount == 3 && !pane.pdf.isHidden && pane.html.isHidden && s.showsPDF)
        let r4 = s.renders
        tv.insertText("z", replacementRange: NSRange(location: 0, length: 0))
        spin(0.8)
        check("no rendering while the PDF is shown", s.renders == r4)
        s.setMode(pdf: false)
        check("back to the HTML page", !pane.html.isHidden && pane.pdf.isHidden && !s.showsPDF)
        check("and it renders the typing it missed", PDFSmoke.wait(15) { s.renders > r4 })

        // hiding
        s.hide()
        check("hidden: the plain editor is back", !s.isShown && c.window?.contentView === plainContent)

        // every window a studio
        Settings.store.set(1, forKey: "startupWindow")
        let second = dir.appendingPathComponent("second.md")
        try! "# Second\n".write(to: second, atomically: true, encoding: .utf8)
        guard let doc2 = Smoke.open(second), let c2 = doc2.controller else { print("FAIL open 2"); exit(1) }
        check("startupWindow = 1 opens the studio", c2.studio.isShown)
        check("and it renders", PDFSmoke.wait(20) { c2.studio.renders >= 1 && c2.studio.pane?.html.loads ?? 0 >= 1 })
        c2.studio.hide()

        doc2.close(); doc.close()
        print(failures == 0 ? "STUDIO SMOKE OK" : "STUDIO SMOKE FAILED (\(failures))")
        exit(failures == 0 ? 0 : 1)
    }
}
