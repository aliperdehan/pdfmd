import Cocoa
import WebKit

/// `pdfmdedit --smoke-html`: an HTML file opened through the real document path, in a window that is never shown. Checks the document
/// type (and the setting that opens `.html` as text), that the page loads, that a rewritten file is shown again by itself on the
/// same place of the page (and once), the manual mode, find, zoom and Show Source.
enum HTMLSmoke {
    static func spin(_ s: Double) { RunLoop.current.run(until: Date().addingTimeInterval(s)) }

    static func page(_ title: String, marker: String) -> String {
        var body = "<h1 id='top'>\(title)</h1><p>marker \(marker)</p><p><a href='#end'>to the end</a></p>"
        for i in 1...120 { body += "<p>Paragraph \(i): the quick brown fox jumps over the lazy dog, again and again.</p>" }
        body += "<h2 id='end'>The end needle</h2>"
        return "<!doctype html><html><head><meta charset='utf-8'><title>\(title)</title></head><body>\(body)</body></html>"
    }

    static func open(_ url: URL) -> HTMLViewerDocument? {
        var result: HTMLViewerDocument?
        var done = false
        NSDocumentController.shared.openDocument(withContentsOf: url, display: false) { doc, _, error in
            result = doc as? HTMLViewerDocument
            if let error { print("open error: \(error)") }
            done = true
        }
        while !done { spin(0.05) }
        if let doc = result, doc.windowControllers.isEmpty { doc.makeWindowControllers() }
        return result
    }

    static func js(_ page: HTMLPageView, _ code: String) -> Any? {
        var value: Any?
        var done = false
        page.web.evaluateJavaScript(code) { r, _ in value = r; done = true }
        _ = PDFSmoke.wait(5) { done }
        return value
    }

    static func run() {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let domain = "io.github.aliperdehan.pdfmdedit.smokehtml"
        UserDefaults.standard.removePersistentDomain(forName: domain)
        Settings.store = UserDefaults(suiteName: domain)!
        Settings.store.set(100, forKey: "htmlReloadDebounceMs")
        defer { UserDefaults.standard.removePersistentDomain(forName: domain) }

        var failures = 0
        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            print("\(ok ? "ok  " : "FAIL") \(name) \(detail)")
            if !ok { failures += 1 }
        }
        let fm = FileManager.default
        let dir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("pdfmdedit-smoke-html-\(getpid())")
        try! fm.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: dir) }
        let file = dir.appendingPathComponent("page one.html")
        try! page("First", marker: "ALPHA").write(to: file, atomically: true, encoding: .utf8)

        check("an .html file is an HTML document", (try? DocController().typeForContents(of: file)) == "HTML document")
        Settings.store.set(1, forKey: "htmlOpenAs")
        check("the setting opens it as text", (try? DocController().typeForContents(of: file)) == "Markdown and text")
        Settings.store.removeObject(forKey: "htmlOpenAs")

        guard let doc = open(file), let c = doc.controller else { print("FAIL open"); exit(1) }
        check("the document is an HTMLViewerDocument", doc.fileType == "HTML document", doc.fileType ?? "nil")
        check("the window was not shown", c.window?.isVisible == false)
        let page = c.page
        check("the page loaded", PDFSmoke.wait(15) { page.loads >= 1 }, "loads \(page.loads)")
        check("it shows the file's text", (js(page, "document.body.innerText.indexOf('marker ALPHA') >= 0") as? Bool) == true)

        // a rewritten file: shown again, on the same place, once
        _ = js(page, "window.scrollTo(0, 1500)")
        spin(0.2)
        let y0 = (js(page, "window.scrollY") as? Double) ?? -1
        check("the page scrolled", y0 > 1000, "y \(y0)")
        let loads0 = page.loads, reloads0 = doc.reloads
        try! HTMLSmoke.page("First", marker: "BETA").write(to: file, atomically: true, encoding: .utf8)
        check("a rewritten file is loaded again", PDFSmoke.wait(15) { page.loads > loads0 }, "loads \(loads0) -> \(page.loads)")
        spin(0.5)
        check("it shows the new text", (js(page, "document.body.innerText.indexOf('marker BETA') >= 0") as? Bool) == true)
        let y1 = (js(page, "window.scrollY") as? Double) ?? -1
        check("on the same place of the page", abs(y1 - y0) < 2, "y \(y0) -> \(y1)")
        check("read again exactly once", doc.reloads == reloads0 + 1 && page.loads == loads0 + 1, "reloads \(doc.reloads - reloads0), loads \(page.loads - loads0)")
        spin(0.8)
        check("nothing loops afterwards", page.loads == loads0 + 1, "loads \(page.loads - loads0)")

        // the manual mode
        Settings.store.set(0, forKey: "htmlAutoReload")
        let loads1 = page.loads
        try! HTMLSmoke.page("First", marker: "GAMMA").write(to: file, atomically: true, encoding: .utf8)
        check("manual: the window says the file changed", PDFSmoke.wait(6) { doc.changedOnDisk } && c.window?.subtitle.contains("file changed") == true, c.window?.subtitle ?? "")
        spin(0.5)
        check("manual: the page is not loaded again", page.loads == loads1)
        c.reloadFile(nil)
        check("manual: Reload loads it", PDFSmoke.wait(15) { page.loads > loads1 } && !doc.changedOnDisk && c.window?.subtitle == "")
        spin(0.4)
        check("manual: it shows the new text", (js(page, "document.body.innerText.indexOf('marker GAMMA') >= 0") as? Bool) == true)
        Settings.store.removeObject(forKey: "htmlAutoReload")

        // find and zoom
        var found: Bool?
        page.find("needle") { found = $0 }
        check("find finds a word", PDFSmoke.wait(5) { found != nil } && found == true)
        found = nil
        page.find("zzzzzz") { found = $0 }
        check("find says when there is none", PDFSmoke.wait(5) { found != nil } && found == false)
        c.zoomIn(nil)
        check("zoom in by the step", abs(page.zoom - 1.1) < 0.001, "\(page.zoom)")
        c.zoomOut(nil); c.zoomOut(nil)
        check("zoom out by the step", abs(page.zoom - 0.9) < 0.001, "\(page.zoom)")
        c.actualSize(nil)
        check("actual size", page.zoom == 1)

        // an anchor link of the page stays on the page
        _ = js(page, "window.scrollTo(0, 0)")
        _ = js(page, "document.querySelector(\"a[href='#end']\").click()")
        spin(0.5)
        let y2 = (js(page, "window.scrollY") as? Double) ?? -1
        check("an anchor link scrolls the page", y2 > 1000, "y \(y2)")
        check("and the page is still this file", page.web.url?.lastPathComponent == "page%20one.html" || page.web.url?.lastPathComponent == "page one.html", page.web.url?.absoluteString ?? "nil")

        // the source
        let before = NSDocumentController.shared.documents.count
        c.openSource(display: false)
        let editor = NSDocumentController.shared.documents.compactMap { $0 as? EditorDocument }.first
        check("Show Source opens the file as text", NSDocumentController.shared.documents.count == before + 1 && editor?.controller?.currentString().contains("marker GAMMA") == true)
        editor?.close()
        doc.close()
        print(failures == 0 ? "HTML SMOKE OK" : "HTML SMOKE FAILED (\(failures))")
        exit(failures == 0 ? 0 : 1)
    }
}
