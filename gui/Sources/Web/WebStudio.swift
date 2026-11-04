import Cocoa
import WebKit

/// The web studio window: the page of `lib/pdfmd_web` (the project UI that will also run in a browser, served by `pdfmd --serve`) in a WKWebView,
/// with the Mac around it. The native side owns the menu bar and every shortcut, so command R renders instead of reloading the page, command T
/// makes a tab of the project and command S saves by the page's logic: each menu action of this window is sent to the page as a command
/// (`window.appCommand(name)`), and the page tells the window its state (title, unsaved dot) through the message handler `colophon`.
/// With a folder the page runs on the real project: the app starts `pdfmd --serve FOLDER` (`StudioServer`) and loads the page from it. Without a
/// folder it runs on fixtures (a demo project, and what the self-tests use).
final class WebStudioController: NSWindowController, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate {
    static var all: [WebStudioController] = []
    /// Set by the smoke test only: private WebKit switches that keep the timers of a hidden page running at their pace.
    static var unthrottled = false

    /// The folder with `index.html`: the app's `Resources/web`; when running from a build folder (`--web-root PATH`, or the source tree next
    /// to `Package.swift`) the checkout's `lib/pdfmd_web`.
    static func webRoot() -> URL? {
        let args = CommandLine.arguments
        if let i = args.firstIndex(of: "--web-root"), i + 1 < args.count { return URL(fileURLWithPath: (args[i + 1] as NSString).expandingTildeInPath) }
        if let r = Bundle.main.resourceURL?.appendingPathComponent("web").absoluteURL, FileManager.default.fileExists(atPath: r.appendingPathComponent("index.html").path) { return r }
        var dir = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath().deletingLastPathComponent()
        for _ in 0..<6 {
            for sub in ["lib/pdfmd_web/index.html", "web/index.html"] {
                let c = dir.appendingPathComponent(sub)
                if FileManager.default.fileExists(atPath: c.path) { return c.deletingLastPathComponent() }
            }
            dir = dir.deletingLastPathComponent()
        }
        return nil
    }

    let web: WKWebView
    var loaded = false
    /// What the page last told: the project, the file, the number of tabs and whether anything is unsaved.
    var state: [String: Any] = [:]
    /// Every message the page posted (the smoke test reads them).
    var messages: [[String: Any]] = []
    /// What the page said through the window's own dialogs (the smoke test answers them without a sheet).
    var dialogAnswer: Bool?

    /// The project folder whose `pdfmd --serve` this window shows; nil for the demo.
    var folder: URL?
    var server: StudioServer?
    /// Why the server did not start (shown in the window; the smoke test reads it).
    var failure: String?
    /// The URL the page was loaded from, once the server has answered.
    var pageURL: URL?

    /// The file the page is on (its current tab), if the window has a folder.
    var currentFileURL: URL? {
        guard let folder, let cur = state["cur"] as? String, !cur.isEmpty else { return nil }
        return folder.appendingPathComponent(cur)
    }

    convenience init(hash: String = "", folder: URL? = nil, file: String? = nil, serveCommand: String? = nil) {
        let config = WKWebViewConfiguration()
        let user = WKUserContentController()
        config.userContentController = user
        if folder != nil { config.websiteDataStore = .nonPersistent() }   // each server has its own token, and cookies do not tell ports apart
        if WebStudioController.unthrottled {   // the smoke test's window is never on screen: WebKit would wake its timers once a second
            for key in ["_setHiddenPageDOMTimerThrottlingEnabled:", "_setPageVisibilityBasedProcessSuppressionEnabled:"] {
                let off = key.contains("Throttling") ? "hiddenPageDOMTimerThrottlingEnabled" : "pageVisibilityBasedProcessSuppressionEnabled"
                if config.preferences.responds(to: NSSelectorFromString(key)) { config.preferences.setValue(false, forKey: off) }
            }
        }
        let web = WKWebView(frame: .zero, configuration: config)
        self.init(web: web)
        user.add(WeakHandler(self), name: "colophon")
        web.navigationDelegate = self
        web.uiDelegate = self
        if let folder {
            self.folder = folder
            web.loadHTMLString("<body style='font:15px -apple-system;padding:2em;color:gray'>Starting <code>pdfmd --serve</code> for \(Self.escaped(folder.lastPathComponent))…</body>", baseURL: nil)
            startServer(file: file, command: serveCommand)
        } else if let root = WebStudioController.webRoot() {
            var url = root.appendingPathComponent("index.html").absoluteURL
            if !hash.isEmpty, let u = URL(string: url.absoluteString + "#" + hash) { url = u }
            web.loadFileURL(url, allowingReadAccessTo: root)
        } else {
            web.loadHTMLString("<body style='font:15px -apple-system;padding:2em'><h2>The web studio's page was not found</h2><p>Expected <code>Resources/web/index.html</code> in the app (or run with <code>--web-root PATH</code>).</p>", baseURL: nil)
        }
    }

    private init(web: WKWebView) {
        self.web = web
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 840), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: true)
        window.title = "Colophon Web Studio"
        window.tabbingMode = .disallowed        // its tabs are the project's, inside the page; the system's tab bar is for documents
        window.isReleasedWhenClosed = false
        window.contentView = web
        window.center()
        window.setFrameAutosaveName("WebStudio")
        super.init(window: window)
        window.delegate = self
        WebStudioController.all.append(self)
    }

    required init?(coder: NSCoder) { fatalError() }

    @discardableResult
    static func open(hash: String = "") -> WebStudioController {
        let c = WebStudioController(hash: hash)
        c.showWindow(nil)
        c.window?.makeKeyAndOrderFront(nil)
        return c
    }

    /// The studio of a project folder: the window that already shows it (brought forward, and on `file` when one is given), else a new one.
    @discardableResult
    static func open(folder: URL, file: String? = nil, serveCommand: String? = nil) -> WebStudioController {
        let same = folder.standardizedFileURL
        if let c = all.first(where: { $0.folder?.standardizedFileURL == same }) {
            c.showWindow(nil); c.window?.makeKeyAndOrderFront(nil)
            if let file { c.openInPage(file) }
            return c
        }
        let c = WebStudioController(folder: folder, file: file, serveCommand: serveCommand)
        c.showWindow(nil)
        c.window?.makeKeyAndOrderFront(nil)
        Settings.store.set(folder.path, forKey: "studioLastFolder")
        return c
    }

    private static func escaped(_ s: String) -> String {
        s.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
    }

    private func startServer(file: String?, command: String?) {
        guard let folder else { return }
        let s = StudioServer(folder: folder)
        server = s
        s.start(commandOverride: command) { [weak self] result in
            guard let self else { s.stop(); return }
            switch result {
            case .success(let url):
                var page = url
                if let file, var c = URLComponents(url: url, resolvingAgainstBaseURL: false) {
                    c.queryItems = (c.queryItems ?? []) + [URLQueryItem(name: "open", value: file)]
                    page = c.url ?? url
                }
                self.pageURL = page
                self.web.load(URLRequest(url: page))
            case .failure(let f):
                self.failure = f.message
                self.web.loadHTMLString("<body style='font:15px -apple-system;padding:2em'><h2>The studio could not start</h2><p>\(Self.escaped(folder.path))</p><pre style='white-space:pre-wrap'>\(Self.escaped(f.message))</pre>", baseURL: nil)
            }
        }
    }

    /// Text waiting for a page that has not started yet (an unsaved new file of the editor).
    private var pendingAdopt: (text: String, done: (Bool) -> Void)?

    /// Hands the text of an unsaved new file to the page as a new unsaved tab; `done(true)` once the page has it.
    func adopt(text: String, done: @escaping (Bool) -> Void) {
        if (state["cur"] as? String)?.isEmpty == false { sendAdopt(text, done) } else { pendingAdopt = (text, done) }
    }

    private func sendAdopt(_ text: String, _ done: @escaping (Bool) -> Void) {
        web.callAsyncJavaScript("return await window.appAdopt(text)", arguments: ["text": text], in: nil, in: .page) { r in
            if case .success(let v) = r { done((v as? Bool) == true) } else { done(false) }
        }
    }

    /// The page saves the file it is on; `done(true)` when nothing of it is unsaved afterwards. What the page still holds unsaved (other tabs)
    /// is put in `state` at once, so that closing the window asks about the right thing.
    func saveCurrent(_ done: @escaping (Bool) -> Void) {
        web.callAsyncJavaScript("return await window.appSave()", arguments: [:], in: nil, in: .page) { [weak self] r in
            if case .success(let v) = r, let o = v as? [String: Any] {
                self?.state["dirty"] = (o["dirty"] as? Bool) ?? true
                done((o["saved"] as? Bool) == true)
            } else { done(false) }
        }
    }

    /// Opens a file of the project in a tab of the page that is running.
    func openInPage(_ path: String) {
        web.evaluateJavaScript("window.appOpen && window.appOpen(\(JSONEncoder.quoted(path)))", completionHandler: nil)
    }

    // MARK: page -> window

    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let m = message.body as? [String: Any] else { return }
        messages.append(m)
        if m["type"] as? String == "state" {
            state = m
            let project = (m["project"] as? String) ?? "", cur = (m["cur"] as? String) ?? ""
            window?.title = cur.isEmpty ? (project.isEmpty ? "Colophon Web Studio" : project) : "\(cur) — \(project)"
            window?.isDocumentEdited = (m["dirty"] as? Bool) ?? false
            if !cur.isEmpty, let p = pendingAdopt { pendingAdopt = nil; sendAdopt(p.text, p.done) }
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { loaded = true }

    /// Coming back to the window (or to the app): the page looks at the files on disk, which another program may have changed meanwhile.
    func windowDidBecomeKey(_ notification: Notification) { if folder != nil { command("checkDisk") } }

    /// Links to the web open in the browser; the page's own files stay in the window.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, action.navigationType == .linkActivated, url.scheme == "http" || url.scheme == "https" || url.scheme == "mailto",
           url.host != "127.0.0.1" {   // the studio's own server stays in the window
            NSWorkspace.shared.open(url); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }

    // The page's alert, confirm and prompt (without these WKWebView answers "no" and says nothing).
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        if dialogAnswer == nil { let a = NSAlert(); a.messageText = message; a.runModal() }
        completionHandler()
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        if let answer = dialogAnswer { completionHandler(answer); return }
        let a = NSAlert(); a.messageText = message
        a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        completionHandler(a.runModal() == .alertFirstButtonReturn)
    }
    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = NSAlert(); a.messageText = prompt
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24)); field.stringValue = defaultText ?? ""
        a.accessoryView = field; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        completionHandler(a.runModal() == .alertFirstButtonReturn ? field.stringValue : nil)
    }

    // MARK: window -> page

    /// Runs one of the page's commands (see `COMMANDS` in `js/app.js`).
    func command(_ name: String) {
        web.evaluateJavaScript("window.appCommand && window.appCommand(\(JSONEncoder.quoted(name)))", completionHandler: nil)
    }

    // The menu bar's actions, found through the responder chain while this window is the key one. The same selectors belong to the document
    // windows; here they are the page's commands.
    @objc func saveDocument(_ sender: Any?) { command("save") }
    @objc func reloadFile(_ sender: Any?) { command("render") }
    @objc func newTab(_ sender: Any?) { command("newTab") }
    @objc override func performTextFinderAction(_ sender: Any?) { if (sender as? NSMenuItem)?.tag ?? 1 == 1 { command("find") } }   // Find…; the page has no find next
    @objc func undo(_ sender: Any?) { command("undo") }
    @objc func redo(_ sender: Any?) { command("redo") }
    @objc func selectNextTab(_ sender: Any?) { command("nextTab") }
    @objc func selectPreviousTab(_ sender: Any?) { command("previousTab") }
    /// Command-1 to command-8 while the studio is the key window: the page's own tabs (the menu item's tag is the number).
    @objc func selectTabNumber(_ sender: NSMenuItem) { command("tab\(sender.tag)") }
    /// Command-9 while the studio is the key window: the page's last tab.
    @objc func selectLastTab(_ sender: Any?) { command("tabLast") }
    @objc func fitPage(_ sender: Any?) { command("tabLast") }   // the View menu's command-9 item: "Zoom to Fit" in a PDF window, "Last Tab" elsewhere
    @objc func showSource(_ sender: Any?) { command("layoutEditor") }
    @objc func togglePreview(_ sender: Any?) { command("layoutSplit") }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        switch item.action {
        case #selector(reloadFile(_:)): item.title = "Render Preview"
        case #selector(saveDocument(_:)): item.title = "Save"
        case #selector(newTab(_:)): item.title = "New Tab"
        case #selector(fitPage(_:)): item.title = "Last Tab"
        case #selector(performTextFinderAction(_:)): return item.tag == 1
        default: break
        }
        return true
    }

    /// Closing the window with unsaved changes asks first (the page would lose them without a word).
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        guard (state["dirty"] as? Bool) == true else { return true }
        if let answer = dialogAnswer { return answer }
        let a = NSAlert()
        a.messageText = "This project has changes that are not saved."
        a.informativeText = "Closing the window discards them."
        a.addButton(withTitle: "Cancel"); a.addButton(withTitle: "Discard Changes")
        return a.runModal() == .alertSecondButtonReturn
    }

    func windowWillClose(_ notification: Notification) {
        WebStudioController.all.removeAll { $0 === self }
        server?.stop()
        web.configuration.userContentController.removeScriptMessageHandler(forName: "colophon")
    }
}

/// The message handler holds its target weakly (WKUserContentController keeps its handlers for good, and the window owns the web view).
final class WeakHandler: NSObject, WKScriptMessageHandler {
    weak var target: WKScriptMessageHandler?
    init(_ t: WKScriptMessageHandler) { target = t }
    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage) { target?.userContentController(ucc, didReceive: message) }
}

extension JSONEncoder {
    /// A string as a JavaScript literal.
    static func quoted(_ s: String) -> String {
        guard let d = try? JSONSerialization.data(withJSONObject: [s], options: []), let t = String(data: d, encoding: .utf8) else { return "\"\"" }
        return String(t.dropFirst().dropLast())
    }
}
