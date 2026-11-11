import Cocoa
import WebKit

/// `pdfmdedit --smoke-web`: the web studio window (never shown on screen) with the page of `lib/pdfmd_web` in a real WKWebView, which is Safari's
/// engine and so the engine the page has to look right in. Checks that the page starts and tells the window its state, that each native
/// command reaches the page (save, new tab, render, close tab, undo), that the window's title and unsaved dot follow, that the menu's selectors
/// find this window through the responder chain, that closing with unsaved changes asks, that the page's confirm() is answered (it is
/// silently "no" without a delegate), and the page's own 46-check self-test inside WebKit.
enum WebSmoke {
    static func spin(_ s: Double) { RunLoop.current.run(until: Date().addingTimeInterval(s)) }

    static func js(_ c: WebStudioController, _ code: String) -> Any? {
        var value: Any?
        var done = false
        c.web.evaluateJavaScript(code) { r, _ in value = r; done = true }
        _ = PDFSmoke.wait(5) { done }
        return value
    }

    /// `pdfmdedit --web-screenshot PATH [--dark]`: the page as WebKit draws it, written as a PNG without showing anything on screen.
    static func screenshot(_ args: [String]) {
        NSApplication.shared.setActivationPolicy(.accessory)
        guard let i = args.firstIndex(of: "--web-screenshot"), i + 1 < args.count else { exit(2) }
        NSApp.appearance = NSAppearance(named: args.contains("--dark") ? .darkAqua : .aqua)
        WebStudioController.unthrottled = true
        let c = WebStudioController.open()
        _ = PDFSmoke.wait(15) { c.loaded && ((c.state["tabs"] as? Int) ?? 0) > 0 }
        spin(1.5)
        var done = false
        c.web.takeSnapshot(with: nil) { image, _ in
            if let tiff = image?.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                try? png.write(to: URL(fileURLWithPath: args[i + 1]))
            }
            done = true
        }
        _ = PDFSmoke.wait(10) { done }
        exit(done ? 0 : 1)
    }

    /// A link of the live view (a studio on the real folder `dir`, on `parts/10-intro.md`): a file of the project opens in a tab and the
    /// page stays with its unsaved edits; a link to nothing, or a script leaving the page, does not replace it.
    static func links(_ live: WebStudioController, _ dir: URL, _ check: (String, Bool, String) -> Void) {
        func click(_ href: String) { _ = js(live, "(() => { const a = document.createElement('a'); a.href = \(JSONEncoder.quoted(href)); document.querySelector('#live').append(a); a.click(); a.remove(); })(); 0") }
        _ = js(live, "window.__app.editor.replaceSelection('Unsaved before the link. ', false); 0")
        _ = PDFSmoke.wait(5) { (live.state["dirty"] as? Bool) == true }
        let page = js(live, "location.href") as? String
        click("report.md")
        check("a link to a file of the project opens it in a tab of the page", PDFSmoke.wait(5) { (live.state["cur"] as? String) == "report.md" }, "\(live.state["cur"] ?? "")")
        check("... and the page stays, with its unsaved edits", js(live, "location.href") as? String == page && (live.state["dirty"] as? Bool) == true, (js(live, "location.href") as? String) ?? "nil")
        click("missing.md")
        spin(0.5)
        check("a link to a file that is not there leaves the page alone", js(live, "location.href") as? String == page && live.loaded, (js(live, "location.href") as? String) ?? "nil")
        live.dialogAnswer = false
        _ = js(live, "location.href = '/elsewhere'; 0")
        spin(0.5)
        check("a script leaving the page asks while something is unsaved (and can say no)", js(live, "location.href") as? String == page, (js(live, "location.href") as? String) ?? "nil")
        live.dialogAnswer = nil
        check("a link of a file in parts/ is tried beside it first", WebStudioController.projectFile(for: URL(string: "http://127.0.0.1:1/10-intro.md")!, folder: dir, current: "parts/10-intro.md") == "parts/10-intro.md", "")
        check("... then from the top of the folder", WebStudioController.projectFile(for: URL(string: "http://127.0.0.1:1/report.md")!, folder: dir, current: "parts/10-intro.md") == "report.md", "")
        check("... and nothing outside the folder is a file of the project", WebStudioController.projectFile(for: URL(string: "http://127.0.0.1:1/../../etc/hosts")!, folder: dir, current: nil) == nil, "")
    }

    static func run() {
        NSApplication.shared.setActivationPolicy(.accessory)
        var failures = 0
        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            print("\(ok ? "ok  " : "FAIL") \(name) \(detail)")
            if !ok { failures += 1 }
        }
        guard let root = WebStudioController.webRoot() else { print("FAIL no web root"); exit(1) }
        check("the page is found", FileManager.default.fileExists(atPath: root.appendingPathComponent("index.html").path), root.path.replacingOccurrences(of: NSHomeDirectory(), with: "~"))

        WebStudioController.unthrottled = true
        let c = WebStudioController.open()
        let state = { (c.state["tabs"] as? Int) ?? 0 }
        check("the page loads and reports its state", PDFSmoke.wait(15) { c.loaded && state() > 0 }, "\(c.state)")
        _ = PDFSmoke.wait(5) { (c.state["cur"] as? String) != nil }
        check("the title is the file and the project", c.window?.title.contains(" — ") == true, c.window?.title ?? "")
        check("it opens with one tab, nothing unsaved", state() == 1 && (c.state["dirty"] as? Bool) == false, "\(c.state)")
        check("the page knows it is in the app", js(c, "window.NATIVE !== null && document.documentElement.classList.contains('native')") as? Bool == true)
        check("the browser-tab layout is not offered", js(c, "getComputedStyle(document.querySelector('[data-layout=tab]')).display") as? String == "none")

        // timers: a hidden WKWebView is throttled by WebKit to one wake-up a second, which would make every wait in a test wrong
        var hops = -1.0
        c.web.callAsyncJavaScript("const t0 = performance.now(); for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 0)); return performance.now() - t0;", arguments: [:], in: nil, in: .page) { r in
            if case .success(let v) = r { hops = (v as? Double) ?? -2 }
        }
        _ = PDFSmoke.wait(30) { hops >= 0 }
        print("  20 chained timers took \(Int(hops)) ms; visible=\(c.window?.isVisible ?? false) occluded=\(!(c.window?.occlusionState.contains(.visible) ?? false)) active=\(NSApp.isActive)")

        // the commands
        c.newTab(nil)
        check("new tab: a second tab with an untitled file", PDFSmoke.wait(5) { state() == 2 } && (c.state["cur"] as? String)?.hasPrefix("untitled") == true, "\(c.state)")
        c.newTab(nil)
        check("new tab again: the next free name", PDFSmoke.wait(5) { state() == 3 } && (c.state["cur"] as? String) == "untitled-2.md", "\(c.state["cur"] ?? "")")
        _ = js(c, "window.__app.editor.replaceSelection('Typed text with **bold**.', false); 0")
        check("an edit shows the unsaved dot in the window", PDFSmoke.wait(5) { c.window?.isDocumentEdited == true }, "\(c.state["dirty"] ?? "")")

        // closing asks; the page's confirm() is answered by the window
        c.dialogAnswer = false
        check("closing the window with unsaved changes asks (and can say no)", c.windowShouldClose(c.window!) == false)
        c.dialogAnswer = true
        check("... and can say yes", c.windowShouldClose(c.window!) == true)
        // quitting asks too (the studio is no NSDocument, so the document controller's review does not see it); the page is asked, not
        // the state it posted last
        var quit: Bool?
        c.quitAnswer = .cancel
        WebStudioController.reviewBeforeQuit { quit = $0 }
        check("quitting with unsaved changes asks, and Cancel keeps the app", PDFSmoke.wait(5) { quit != nil } && quit == false, "\(quit.map(String.init) ?? "nil")")
        c.quitAnswer = .discard; quit = nil
        WebStudioController.reviewBeforeQuit { quit = $0 }
        check("... Don't Save lets it quit", PDFSmoke.wait(5) { quit != nil } && quit == true, "\(quit.map(String.init) ?? "nil")")
        var asked: Bool?
        c.state["dirty"] = false   // as if the page's last message were a key press late
        c.askDirty { asked = $0 }
        check("... and the page itself says what is unsaved", PDFSmoke.wait(5) { asked != nil } && asked == true, "\(asked.map(String.init) ?? "nil")")
        c.quitAnswer = nil
        c.dialogAnswer = false
        _ = js(c, "window.appCommand('closeTab'); 0"); spin(0.3)
        check("a tab with changes stays when the page's confirm() is answered no", state() == 3, "\(state()) tabs")
        c.dialogAnswer = true
        _ = js(c, "window.appCommand('closeTab'); 0")
        check("... and closes when it is answered yes", PDFSmoke.wait(5) { state() == 2 }, "\(state()) tabs")
        c.dialogAnswer = nil

        // save by the page's logic
        _ = js(c, "window.appCommand('previousTab'); 0"); spin(0.2)
        _ = js(c, "window.__app.editor.replaceSelection(' more', false); 0")
        check("previous tab moves to the first file", (c.state["cur"] as? String) != nil && PDFSmoke.wait(5) { c.window?.isDocumentEdited == true })
        c.saveDocument(nil)
        check("save: the unsaved dot goes (file and the other tab)", PDFSmoke.wait(5) { c.window?.isDocumentEdited == false } || (c.state["dirty"] as? Bool) == false, "\(c.state["dirty"] ?? "")")

        // command-1 and command-2 of the menu reach the page's tabs (the window's own selectTabNumber, found before the app's)
        let first = (c.state["cur"] as? String) ?? ""
        let numbered = { (n: Int) -> NSMenuItem in let i = NSMenuItem(title: "Tab \(n)", action: nil, keyEquivalent: String(n)); i.tag = n; return i }
        c.selectTabNumber(numbered(2))
        check("command-2 in the studio picks the second tab", PDFSmoke.wait(5) { (c.state["cur"] as? String).map { $0 != first && $0.hasPrefix("untitled") } == true }, "\(c.state["cur"] ?? "")")
        c.selectTabNumber(numbered(8))
        spin(0.3)
        check("command-8 with two tabs does nothing", (c.state["cur"] as? String)?.hasPrefix("untitled") == true, "\(c.state["cur"] ?? "")")
        c.selectTabNumber(numbered(1))
        check("command-1 in the studio picks the first tab", PDFSmoke.wait(5) { (c.state["cur"] as? String) == first }, "\(c.state["cur"] ?? "")")
        check("the studio answers the tab-number action before the app does", c.responds(to: Selector(("selectTabNumber:"))))

        // render: the live view is made again, whatever the render mode
        _ = js(c, "window.api.lastRender = null; window.__app.editor.replaceSelection('\\n\\nA new paragraph.', false); 0")
        c.reloadFile(nil)
        check("render: the live view is rendered at once", PDFSmoke.wait(5) { (js(c, "document.querySelector('#live').textContent.includes('A new paragraph') ") as? Bool) == true })

        // the responder chain from the page up: the menu's actions find the window controller before the application's own
        for sel in ["newTab:", "reloadFile:", "saveDocument:"] {
            var r: NSResponder? = c.web
            while let x = r, !x.responds(to: Selector(sel)) { r = x.nextResponder }
            check("the menu's \(sel) reaches the web window", (r as AnyObject?) === c, "\(String(describing: r))")
        }
        let reload = NSMenuItem(title: "Reload", action: #selector(WebStudioController.reloadFile(_:)), keyEquivalent: "r")
        _ = c.validateMenuItem(reload)
        check("Reload is called Render Preview here", reload.title == "Render Preview", reload.title)
        let find = NSMenuItem(title: "Find Next", action: #selector(NSResponder.performTextFinderAction(_:)), keyEquivalent: "g"); find.tag = 2
        check("Find Next is off, Find… is on", c.validateMenuItem(find) == false)
        find.tag = 1
        check("... Find… is on", c.validateMenuItem(find))

        // links to the web go to the browser, not into the window
        check("the page's own files stay in the window", js(c, "location.protocol") as? String == "file:")

        c.window?.close()
        check("the window is released when closed", PDFSmoke.wait(2) { !WebStudioController.all.contains { $0 === c } })

        // the real folder: the app starts `pdfmd --serve` (the pdfmd the login shell finds), the page loads from it and works on the files
        let fm = FileManager.default
        let dir = fm.temporaryDirectory.appendingPathComponent("colophon-smoke-\(getpid())")
        try? fm.createDirectory(at: dir.appendingPathComponent("parts"), withIntermediateDirectories: true)
        try? "# Real project\n\nHello from the disk.\n".write(to: dir.appendingPathComponent("report.md"), atomically: true, encoding: .utf8)
        try? "# Intro part\n\nText of the part.\n".write(to: dir.appendingPathComponent("parts/10-intro.md"), atomically: true, encoding: .utf8)
        defer { try? fm.removeItem(at: dir) }
        let live = WebStudioController.open(folder: dir, file: "parts/10-intro.md")
        let started = PDFSmoke.wait(Settings.number("studioServerTimeout") + 15) { live.loaded && (live.state["cur"] as? String) != nil || live.failure != nil }
        check("the studio starts pdfmd --serve for a folder and loads its page", started && live.failure == nil && live.pageURL?.scheme == "http", live.failure ?? live.pageURL?.host ?? "")
        check("it opens on the file that was asked for", (live.state["cur"] as? String) == "parts/10-intro.md", "\(live.state["cur"] ?? "")")
        check("the page is live, on the folder", js(live, "window.__app.project.name") as? String == dir.lastPathComponent && js(live, "location.protocol") as? String == "http:", "\(js(live, "window.__app.project.name") ?? "")")
        check("the editor holds the file's real text", (js(live, "window.__app.editor.getText()") as? String)?.contains("Text of the part.") == true)
        check("the window knows the file it is on", live.currentFileURL?.lastPathComponent == "10-intro.md")
        _ = js(live, "window.__app.editor.replaceSelection('Edited in the app. ', false); 0")
        live.saveDocument(nil)
        let wrote = PDFSmoke.wait(8) { (try? String(contentsOf: dir.appendingPathComponent("parts/10-intro.md")))?.contains("Edited in the app.") == true }
        check("save writes the file on the disk, through the core", wrote)
        // a file another program rewrites while the studio is open: the page shows it again when the window is entered
        try? "# Intro part\n\nRewritten by another program.\n".write(to: dir.appendingPathComponent("parts/10-intro.md"), atomically: true, encoding: .utf8)
        live.windowDidBecomeKey(Notification(name: NSWindow.didBecomeKeyNotification))
        check("the page shows a file again that another program rewrote", PDFSmoke.wait(8) { (js(live, "window.__app.editor.getText()") as? String)?.contains("Rewritten by another program.") == true })
        WebSmoke.links(live, dir, check)
        // the mode switch's hand-over: the text of an unsaved new file arrives as a new unsaved tab, and the page saves it when asked
        var adopted: Bool?
        live.adopt(text: "Text from the plain editor.\n") { adopted = $0 }
        check("the text of an unsaved file is taken over as a new tab", PDFSmoke.wait(8) { adopted != nil } && adopted == true && (live.state["cur"] as? String)?.hasPrefix("untitled") == true, "\(live.state["cur"] ?? "")")
        check("... and it shows as unsaved", PDFSmoke.wait(5) { (live.state["dirty"] as? Bool) == true })
        var saved: Bool?
        live.saveCurrent { saved = $0 }
        _ = PDFSmoke.wait(8) { saved != nil }
        let untitled = (live.state["cur"] as? String).map { dir.appendingPathComponent($0) }
        check("the page saves it when the window leaves (the file is on the disk with the text)", saved == true && untitled.flatMap { try? String(contentsOf: $0) } == "Text from the plain editor.\n", untitled?.lastPathComponent ?? "nil")
        // quitting with Save writes every tab that has changes, then lets the app quit
        _ = js(live, "window.appOpen('report.md').then(() => window.__app.editor.replaceSelection('Saved at the quit. ', false)); 0")
        _ = PDFSmoke.wait(5) { (live.state["dirty"] as? Bool) == true }
        var quitSaved: Bool?
        live.quitAnswer = .save
        WebStudioController.reviewBeforeQuit { quitSaved = $0 }
        _ = PDFSmoke.wait(8) { quitSaved != nil }
        check("quitting with Save writes the changes and lets the app quit", quitSaved == true && (try? String(contentsOf: dir.appendingPathComponent("report.md")))?.contains("Saved at the quit.") == true, "\(quitSaved.map(String.init) ?? "nil")")
        live.quitAnswer = nil
        let same = WebStudioController.open(folder: dir)
        check("the same folder again brings the same window forward", same === live)
        let pid = live.server?.lastPid
        live.window?.close()
        check("closing the window stops the server", pid != nil && PDFSmoke.wait(5) { kill(pid!, 0) != 0 }, "pid \(pid.map(String.init) ?? "nil")")

        // the page's own self-test, in WebKit
        let t = WebStudioController.open(hash: "selftest-slow4")
        _ = PDFSmoke.wait(60) { (js(t, "document.title") as? String).map { $0 == "OK" || $0 == "FAILED" } ?? false }
        let report = (js(t, "(document.querySelector('#selftest')||{}).textContent||''") as? String) ?? ""
        let fails = report.components(separatedBy: "\n").filter { $0.hasPrefix("FAIL") }
        if report.isEmpty { print("  no report; title: \((js(t, "document.title") as? String) ?? "")  errors: \((js(t, "(window.__errors||[]).join(' | ')") as? String) ?? "")  body: \((js(t, "document.body.innerText.slice(0,200)") as? String) ?? "")") }
        for f in fails { print(f) }
        if !fails.isEmpty {   // what the page shows, for the failure
            print("  live view ends: \((js(t, "document.querySelector('#live').textContent.slice(-120)") as? String) ?? "")")
            print("  banner: \((js(t, "document.querySelector('#liveBanner').textContent") as? String) ?? "")  mode: \((js(t, "document.querySelector('#renderMode').value") as? String) ?? "")")
            print("  tabs: \((js(t, "[...document.querySelectorAll('.tab')].map(x=>x.textContent).join('|')") as? String) ?? "")  side: \((js(t, "document.querySelector('#side').textContent.slice(0,200)") as? String) ?? "")")
        }
        check("the page's self-test passes in WebKit", report.contains("SELFTEST OK"), report.components(separatedBy: "\n").last(where: { $0.hasPrefix("SELFTEST") }) ?? "no report")
        t.window?.close()

        print(failures == 0 ? "web smoke: all ok" : "web smoke: \(failures) FAILED")
        exit(failures == 0 ? 0 : 1)
    }
}
