import Cocoa
import WebKit

/// The web studio window: the page of `lib/pdfmd_web` (the project UI that will also run in a browser, served by `pdfmd --serve`) in a WKWebView,
/// with the Mac around it. The native side owns the menu bar and every shortcut, so command R renders instead of reloading the page, command T
/// makes a tab of the project and command S saves by the page's logic: each menu action of this window is sent to the page as a command
/// (`window.appCommand(name)`), and the page tells the window its state (title, unsaved dot) through the message handler `colophon`.
/// Today the page runs on fixtures (a demo project); the core arrives with `pdfmd --serve`.
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

    convenience init(hash: String = "") {
        let config = WKWebViewConfiguration()
        let user = WKUserContentController()
        config.userContentController = user
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
        if let root = WebStudioController.webRoot() {
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

    // MARK: page -> window

    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let m = message.body as? [String: Any] else { return }
        messages.append(m)
        if m["type"] as? String == "state" {
            state = m
            let project = (m["project"] as? String) ?? "", cur = (m["cur"] as? String) ?? ""
            window?.title = cur.isEmpty ? (project.isEmpty ? "Colophon Web Studio" : project) : "\(cur) — \(project)"
            window?.isDocumentEdited = (m["dirty"] as? Bool) ?? false
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { loaded = true }

    /// Links to the web open in the browser; the page's own files stay in the window.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, action.navigationType == .linkActivated, url.scheme == "http" || url.scheme == "https" || url.scheme == "mailto" {
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
    @objc func showSource(_ sender: Any?) { command("layoutEditor") }
    @objc func togglePreview(_ sender: Any?) { command("layoutSplit") }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        switch item.action {
        case #selector(reloadFile(_:)): item.title = "Render Preview"
        case #selector(saveDocument(_:)): item.title = "Save"
        case #selector(newTab(_:)): item.title = "New Tab"
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
