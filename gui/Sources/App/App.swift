import Cocoa

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuItemValidation {
    var launchedWithFiles = false

    /// The windows of documents (editor, PDF, HTML) that can sit together as tabs of one window. Tabs are never forced: a new document opens
    /// in a window of its own (command N) unless the system's "Prefer tabs" says otherwise; command T makes a new document in a tab.
    static let tabGroup = NSWindow.TabbingIdentifier("io.github.aliperdehan.pdfmdedit.documents")

    /// The window command T adds a tab to: the key window if it is a document's, else the main window, else none.
    func tabHost() -> NSWindow? {
        for w in [NSApp.keyWindow, NSApp.mainWindow] { if let w, w.tabbingIdentifier == AppDelegate.tabGroup { return w } }
        return nil
    }

    @objc func newTab(_ sender: Any?) { _ = AppDelegate.newTab(next: tabHost(), show: true) }

    /// A new empty document as a tab of `host`; without a host, a window as command N makes it. Returns the new window.
    @discardableResult
    static func newTab(next host: NSWindow?, show: Bool) -> NSWindow? {
        guard let host else { NSDocumentController.shared.newDocument(nil); return nil }
        guard let doc = try? NSDocumentController.shared.openUntitledDocumentAndDisplay(false) else { return nil }
        if doc.windowControllers.isEmpty { doc.makeWindowControllers() }
        guard let window = doc.windowControllers.first?.window else { return nil }
        host.addTabbedWindow(window, ordered: .above)
        if show { window.makeKeyAndOrderFront(nil) }
        return window
    }

    func applicationWillFinishLaunching(_ note: Notification) {
        NSAppleEventManager.shared().setEventHandler(self, andSelector: #selector(handleURL(_:reply:)),
                                                     forEventClass: AEEventClass(kInternetEventClass), andEventID: AEEventID(kAEGetURL))
    }

    func applicationDidFinishLaunching(_ note: Notification) {
        buildMenus()
        LiveSettings.install(domain: Bundle.main.bundleIdentifier ?? "io.github.aliperdehan.pdfmdedit")
        let paths = CommandLine.arguments.dropFirst().filter { !$0.hasPrefix("-") && FileManager.default.fileExists(atPath: $0) }
        launchedWithFiles = !paths.isEmpty
        for p in paths {
            NSDocumentController.shared.openDocument(withContentsOf: URL(fileURLWithPath: p), display: true) { _, _, error in
                if let error { NSApp.presentError(error) }
            }
        }
        if CommandLine.arguments.contains("--web") { WebStudioController.open() }   // the web studio at launch (a Mac window around lib/pdfmd_web)
        NSApp.activate(ignoringOtherApps: true)
        PopController.shared.settingsChanged()   // the menu-bar icon and the shortcut, when the setting says so
        NotificationCenter.default.addObserver(forName: Settings.changed, object: nil, queue: .main) { [weak self] _ in
            PopController.shared.settingsChanged(); self?.applySwitchShortcut()
        }
        DispatchQueue.global(qos: .utility).async { _ = PdfmdTool.cachedResolve(); _ = PdfmdTool.pandoc() }   // so that the About box and the preview have their answer
    }

    // A command-line launch with a file (pdfmd's --editor) always quits with its last window: the command that started it waits for
    // that. Otherwise the setting decides: off (the Mac way) keeps the app, and the Dock icon opens a new window.
    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool {
        launchedWithFiles || (Settings.flag("quitAfterLastWindow") && !Settings.flag("popMenuBar"))   // the menu-bar icon keeps the app
    }

    func applicationShouldHandleReopen(_ app: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { NSDocumentController.shared.newDocument(nil) }
        return false
    }
    /// An untitled editor window opens at a plain launch. Not when files were given, and not when Colophon is only there for the menu-bar
    /// icon: started as a login item (the launch event says so), or always when `popNoStartWindow` is on.
    func applicationShouldOpenUntitledFile(_ app: NSApplication) -> Bool {
        guard !launchedWithFiles && CommandLine.arguments.count < 2 else { return false }
        if Settings.flag("popMenuBar") && (Settings.flag("popNoStartWindow") || launchedAsLoginItem()) { return false }
        return true
    }

    /// Whether the launch event that started the app says "a login item" (best effort: it can only be seen at a real login).
    func launchedAsLoginItem() -> Bool {
        guard let event = NSAppleEventManager.shared().currentAppleEvent else { return false }
        return event.paramDescriptor(forKeyword: AEKeyword(keyAEPropData))?.enumCodeValue == OSType(keyAELaunchedAsLogInItem)
    }

    /// The standard About panel with the app's own words: what it is, how early it is, and the pdfmd it works with: one line, and a "more"
    /// link that opens the details (asked of the shell off the main thread, so the panel opens a moment later).
    @objc func showAbout(_ sender: Any?) {
        DispatchQueue.global().async {
            let head = PdfmdTool.aboutHead()
            DispatchQueue.main.async {
                let style = NSMutableParagraphStyle()
                style.alignment = .center
                let credits = NSMutableAttributedString(string: "the pdfmd workbench\n\n", attributes: [
                    .font: NSFont.boldSystemFont(ofSize: 12), .paragraphStyle: style, .foregroundColor: NSColor.labelColor])
                let small: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 11), .paragraphStyle: style, .foregroundColor: NSColor.secondaryLabelColor]
                credits.append(NSAttributedString(string: head + "  ", attributes: small))
                var link = small
                link[.link] = URL(string: "colophon://pdfmd")!
                link[.foregroundColor] = NSColor.linkColor
                credits.append(NSAttributedString(string: "more…", attributes: link))
                NSApp.orderFrontStandardAboutPanel(options: [
                    .applicationName: "Colophon",
                    .applicationVersion: "\(appVersion) (early alpha)",
                    .version: "",
                    .credits: credits,
                ])
                NSApp.activate(ignoringOtherApps: true)
            }
        }
    }

    private var versionsPanel: NSPanel?

    /// The details behind the About box's "more": which pdfmd is used, why, and every other one found.
    @objc func showPdfmdVersions(_ sender: Any?) {
        DispatchQueue.global().async {
            let text = PdfmdTool.detailLines().joined(separator: "\n")
            DispatchQueue.main.async {
                let panel = self.versionsPanel ?? NSPanel(contentRect: NSRect(x: 0, y: 0, width: 520, height: 200),
                                                         styleMask: [.titled, .closable, .utilityWindow], backing: .buffered, defer: true)
                panel.isReleasedWhenClosed = false
                panel.title = "pdfmd"
                let field = NSTextField(wrappingLabelWithString: text)
                field.isSelectable = true
                field.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
                field.frame = NSRect(x: 16, y: 14, width: 488, height: 0)
                let fit = field.sizeThatFits(NSSize(width: 488, height: 10_000))
                field.frame = NSRect(x: 16, y: 14, width: 488, height: ceil(fit.height))
                panel.setContentSize(NSSize(width: 520, height: ceil(fit.height) + 28))
                panel.contentView = NSView(frame: NSRect(x: 0, y: 0, width: 520, height: ceil(fit.height) + 28))
                panel.contentView?.addSubview(field)
                self.versionsPanel = panel
                panel.center()
                panel.makeKeyAndOrderFront(nil)
            }
        }
    }

    /// `colophon://pdfmd` (the About box's "more").
    @objc func handleURL(_ event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) {
        guard let text = event.paramDescriptor(forKeyword: AEKeyword(keyDirectObject))?.stringValue, let url = URL(string: text) else { return }
        if url.host == "pdfmd" { showPdfmdVersions(nil) }
    }

    @objc func openWebStudio(_ sender: Any?) { WebStudioController.open() }

    /// Command-1 to command-8: the nth tab of `window`'s tab group (the window's own order, left to right). False when there is no such tab.
    @discardableResult
    static func selectTab(_ n: Int, in window: NSWindow?) -> Bool {
        guard let window, let tabs = window.tabbedWindows, n >= 1, n <= tabs.count else { return false }
        window.tabGroup?.selectedWindow = tabs[n - 1]
        tabs[n - 1].makeKeyAndOrderFront(nil)
        return true
    }

    /// The menu's command-1 to command-8 for the document windows; the web studio window has its own `selectTabNumber` (its tabs are the page's).
    @objc func selectTabNumber(_ sender: NSMenuItem) { AppDelegate.selectTab(sender.tag, in: NSApp.keyWindow) }

    /// The window that was in use last and is not the web studio: a document's (editor, PDF or HTML), the frontmost first.
    static func lastDocumentWindow() -> NSWindow? {
        NSApp.orderedWindows.first { $0.windowController?.document != nil && !($0.windowController is WebStudioController) && ($0.isVisible || $0.tabbingIdentifier == tabGroup) }
    }

    /// The mode switch (its key is the setting `keySwitchMode`): the window is REPLACED, not just another one raised.
    /// Plain text -> studio: the editor's file is saved and opened in the studio of its project (the file's folder, the one above for a file
    /// of `parts/`), and the editor window closes. An unsaved new file has no folder: its text becomes a new unsaved tab of the studio's project
    /// (the folder the studio was last on, else one the author picks), and the editor closes once the page has taken the text.
    /// Studio -> plain text: the page saves the file it is on, which opens in an editor window, and the studio window closes.
    /// A PDF or HTML window is not converted: it only gets the studio of its folder beside it.
    @objc func switchMode(_ sender: Any?) {
        if let studio = NSApp.keyWindow?.windowController as? WebStudioController { backToPlain(from: studio); return }
        guard let doc = NSApp.keyWindow?.windowController?.document as? NSDocument else {
            if let folder = rememberedStudioFolder() ?? pickStudioFolder() { WebStudioController.open(folder: folder) }
            return
        }
        guard let editor = doc as? EditorDocument else {
            if let url = doc.fileURL { openStudio(near: url, markdown: false) }
            return
        }
        if let url = editor.fileURL {
            if editor.isDocumentEdited {
                editor.save(withDelegate: self, didSave: #selector(savedForStudio(_:didSave:contextInfo:)), contextInfo: nil)
            } else {
                openStudio(near: url, markdown: true)
                editor.close()
            }
        } else {
            moveUntitledToStudio(editor)
        }
    }

    @objc func savedForStudio(_ doc: NSDocument, didSave: Bool, contextInfo: UnsafeMutableRawPointer?) {
        guard didSave, let url = doc.fileURL else { return }
        openStudio(near: url, markdown: true)
        doc.close()
    }

    /// The text of an unsaved new file goes to the studio as a new tab; the editor window closes when the page has it.
    private func moveUntitledToStudio(_ doc: EditorDocument) {
        let text = doc.controller?.currentString() ?? doc.text
        guard let folder = rememberedStudioFolder() ?? pickStudioFolder() else { return }
        let studio = WebStudioController.open(folder: folder)
        if text.isEmpty { doc.updateChangeCount(.changeCleared); doc.close(); return }
        studio.adopt(text: text) { ok in
            if ok { doc.updateChangeCount(.changeCleared); doc.close() }
            else { let a = NSAlert(); a.messageText = "The studio did not take the text over."; a.informativeText = "It stays in the editor window."; a.runModal() }
        }
    }

    /// Back from the studio: the page saves its file, the file opens in an editor window, the studio closes (it asks first when another
    /// tab of it has changes that are not saved).
    private func backToPlain(from studio: WebStudioController) {
        guard let url = studio.currentFileURL, FileManager.default.fileExists(atPath: url.path) else {
            if let w = AppDelegate.lastDocumentWindow() { w.makeKeyAndOrderFront(nil) } else { NSDocumentController.shared.newDocument(nil) }
            studio.window?.performClose(nil)
            return
        }
        studio.saveCurrent { saved in
            guard saved else { let a = NSAlert(); a.messageText = "The file could not be saved."; a.informativeText = "The studio stays open."; a.runModal(); return }
            NSDocumentController.shared.openDocument(withContentsOf: url, display: true) { _, _, error in
                if let error { NSApp.presentError(error); return }
                studio.window?.performClose(nil)
            }
        }
    }

    private func rememberedStudioFolder() -> URL? {
        guard let last = Settings.store.string(forKey: "studioLastFolder"), FileManager.default.fileExists(atPath: last) else { return nil }
        return URL(fileURLWithPath: last)
    }

    /// The studio of the project that `file` belongs to, on that file when it is one the page can edit.
    func openStudio(near file: URL, markdown: Bool) {
        let folder = StudioServer.projectFolder(of: file)
        let relative = file.standardizedFileURL.path.replacingOccurrences(of: folder.standardizedFileURL.path + "/", with: "")
        WebStudioController.open(folder: folder, file: markdown ? relative : nil)
    }

    /// The folder panel of File > Open Folder in Studio…; nil when it is cancelled.
    func pickStudioFolder() -> URL? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        panel.prompt = "Open"; panel.message = "The folder of the project (the one with report.md in it)"
        if let last = Settings.store.string(forKey: "studioLastFolder") { panel.directoryURL = URL(fileURLWithPath: last) }
        return panel.runModal() == .OK ? panel.url : nil
    }

    @objc func openStudioFolder(_ sender: Any?) {
        if let url = pickStudioFolder() { WebStudioController.open(folder: url) }
    }

    /// Quitting asks about the studio windows' changes that are not saved (the documents' own were asked about before this is called).
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !WebStudioController.all.isEmpty else { return .terminateNow }
        WebStudioController.reviewBeforeQuit { sender.reply(toApplicationShouldTerminate: $0) }
        return .terminateLater
    }

    func applicationWillTerminate(_ note: Notification) {
        for c in WebStudioController.all { c.server?.stop() }
    }

    /// Command-9 is ONE menu item (View > Zoom to Fit, action `fitPage:`): AppKit gives a key to the first item that has it, and does nothing
    /// when that one is off, so two items with the key cannot share it. The PDF window answers `fitPage:` first and the item says "Zoom to
    /// Fit"; in every other window nothing does, the application delegate does, and the item says "Last Tab" (the studio window answers it
    /// itself, with its own tabs).
    @objc func fitPage(_ sender: Any?) { selectLastTab(nil) }

    /// The last tab of the key window's tab group (also Window > Select Tab > Last Tab, which has no key of its own).
    @objc func selectLastTab(_ sender: Any?) { AppDelegate.selectTab(NSApp.keyWindow?.tabbedWindows?.count ?? 0, in: NSApp.keyWindow) }

    /// The menu item for the mode switch (its key is the setting `keySwitchMode`).
    weak var switchItem: NSMenuItem?

    /// The titles of the menu items that carry command-9 (for the self-test).
    func mainMenu9() -> [String] {
        func walk(_ m: NSMenu) -> [String] { m.items.flatMap { ($0.keyEquivalent == "9" && $0.keyEquivalentModifierMask.intersection(.deviceIndependentFlagsMask) == .command ? [$0.title] : []) + ($0.submenu.map(walk) ?? []) } }
        return NSApp.mainMenu.map(walk) ?? []
    }

    /// Puts the setting's shortcut on the menu item. A key that another item of the menu already has is not taken (the item then has none).
    func applySwitchShortcut() {
        guard let item = switchItem else { return }
        let text = Settings.string("keySwitchMode")
        guard text.lowercased() != "none", let s = PopShortcut.parse(text), AppDelegate.menuConflict(s, besides: item) == nil else {
            item.keyEquivalent = ""; return
        }
        item.keyEquivalent = s.menuKey
        item.keyEquivalentModifierMask = s.menuMask
    }

    /// The title of the menu item that already has this shortcut, if any (looked for in every menu of the menu bar, besides `skip`).
    static func menuConflict(_ s: PopShortcut, besides skip: NSMenuItem?) -> String? {
        func search(_ menu: NSMenu) -> String? {
            for item in menu.items where item !== skip {
                if !item.keyEquivalent.isEmpty, item.keyEquivalent == s.menuKey, item.keyEquivalentModifierMask.intersection(.deviceIndependentFlagsMask) == s.menuMask { return item.title }
                if let sub = item.submenu, let found = search(sub) { return found }
            }
            return nil
        }
        return NSApp.mainMenu.flatMap(search)
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        if item.action == #selector(switchMode(_:)) {
            item.title = NSApp.keyWindow?.windowController is WebStudioController ? "Switch to Plain Text" : "Switch to Studio"
        }
        if item.action == #selector(fitPage(_:)) {
            item.title = "Last Tab"
            return (NSApp.keyWindow?.tabbedWindows?.count ?? 0) > 1
        }
        if item.action == #selector(selectLastTab(_:)) { return (NSApp.keyWindow?.tabbedWindows?.count ?? 0) > 1 }
        return true
    }
    @objc func showPreferences(_ sender: Any?) { PreferencesController.shared.show() }

    func buildMenus() {
        let main = NSMenu()
        NSApp.mainMenu = main

        func menu(_ title: String) -> NSMenu {
            let item = NSMenuItem(); main.addItem(item)
            let m = NSMenu(title: title); item.submenu = m
            return m
        }
        @discardableResult
        func add(_ m: NSMenu, _ title: String, _ action: String?, _ key: String = "", _ mods: NSEvent.ModifierFlags = .command, tag: Int = 0) -> NSMenuItem {
            let item = NSMenuItem(title: title, action: action.map { Selector(($0)) }, keyEquivalent: key)
            item.keyEquivalentModifierMask = mods
            item.tag = tag
            m.addItem(item)
            return item
        }

        let app = menu("Colophon")
        add(app, "About Colophon", "showAbout:")
        app.addItem(.separator())
        add(app, "Settings…", "showPreferences:", ",")
        app.addItem(.separator())
        add(app, "Hide Colophon", "hide:", "h")
        add(app, "Hide Others", "hideOtherApplications:", "h", [.command, .option])
        app.addItem(.separator())
        add(app, "Quit Colophon", "terminate:", "q")

        let file = menu("File")
        add(file, "New", "newDocument:", "n")
        add(file, "New Tab", "newTab:", "t")
        add(file, "Open…", "openDocument:", "o")
        add(file, "Open Folder in Studio…", "openStudioFolder:", "o", [.command, .shift])
        add(file, "New Studio Demo Window", "openWebStudio:", "n", [.command, .shift])
        let recent = NSMenuItem(title: "Open Recent", action: nil, keyEquivalent: "")
        let recentMenu = NSMenu(title: "Open Recent")
        recentMenu.addItem(NSMenuItem(title: "Clear Menu", action: Selector(("clearRecentDocuments:")), keyEquivalent: ""))
        recent.submenu = recentMenu
        file.addItem(recent)
        file.addItem(.separator())
        add(file, "Close", "performClose:", "w")
        add(file, "Save", "saveDocument:", "s")
        add(file, "Save As…", "saveDocumentAs:", "s", [.command, .shift])
        add(file, "Revert to Saved", "revertDocumentToSaved:")
        file.addItem(.separator())
        let export = NSMenuItem(title: "Export As", action: nil, keyEquivalent: "")
        export.submenu = ExportTable.makeMenu()
        file.addItem(export)

        let edit = menu("Edit")
        add(edit, "Undo", "undo:", "z")
        add(edit, "Redo", "redo:", "z", [.command, .shift])
        edit.addItem(.separator())
        add(edit, "Cut", "cut:", "x")
        add(edit, "Copy", "copy:", "c")
        add(edit, "Paste", "paste:", "v")
        add(edit, "Select All", "selectAll:", "a")
        edit.addItem(.separator())
        add(edit, "Find…", "performTextFinderAction:", "f", tag: 1)
        add(edit, "Find Next", "performTextFinderAction:", "g", tag: 2)
        add(edit, "Find Previous", "performTextFinderAction:", "g", [.command, .shift], tag: 3)
        add(edit, "Use Selection for Find", "performTextFinderAction:", "e", tag: 7)
        add(edit, "Jump to Selection", "centerSelectionInVisibleArea:", "j")

        let view = menu("View")
        add(view, "Wrap Lines", "toggleWrap:", "l", [.command, .option])
        add(view, "Hide Line Numbers", "toggleLineNumbers:", "n", [.command, .option])
        add(view, "Hide Status Bar", "toggleStatusBar:", "/", [.command, .option])
        view.addItem(.separator())
        add(view, "Hide Sidebar", "toggleThumbnails:", "t", [.command, .option])
        add(view, "Thumbnails", "showPages:", "2", [.command, .option])
        add(view, "Table of Contents", "showContents:", "3", [.command, .option])
        add(view, "Reset Sidebar Width", "resetSidebarWidth:", "")
        add(view, "Show Source", "showSource:", "u", [.command, .option])
        add(view, "Reload", "reloadFile:", "r")   // "Build PDF" in an editor window (the window's validation renames it)
        add(view, "Show Build Log", "showBuildLog:", "r", [.command, .option])
        add(view, "Show Preview", "togglePreview:", "p", [.command, .option])
        add(view, "Preview as HTML", "previewAsHTML:")
        add(view, "Preview as PDF", "previewAsPDF:")
        add(view, "Reload Automatically", "toggleAutoReload:")
        view.addItem(.separator())
        add(view, "Zoom In", "zoomIn:", "=")
        add(view, "Zoom Out", "zoomOut:", "-")
        add(view, "Actual Size", "actualSize:", "0")
        add(view, "Zoom to Fit", "fitPage:", "9")
        add(view, "Fit Width", "fitWidth:", "9", [.command, .option])
        add(view, "Go to Page…", "goToPage:", "g", [.command, .option])
        add(view, "Next Page", "goToNextPage:", String(UnicodeScalar(NSDownArrowFunctionKey)!), [.command, .option])
        add(view, "Previous Page", "goToPreviousPage:", String(UnicodeScalar(NSUpArrowFunctionKey)!), [.command, .option])

        let window = menu("Window")
        add(window, "Minimize", "performMiniaturize:", "m")
        add(window, "Zoom", "performZoom:")
        window.addItem(.separator())
        add(window, "Show Tab Bar", "toggleTabBar:")
        add(window, "Show All Tabs", "toggleTabOverview:")
        add(window, "Merge All Windows", "mergeAllWindows:")
        add(window, "Move Tab to New Window", "moveTabToNewWindow:")
        add(window, "Show Next Tab", "selectNextTab:", "\t", .control)
        add(window, "Show Previous Tab", "selectPreviousTab:", "\t", [.control, .shift])
        let tabs = NSMenuItem(title: "Select Tab", action: nil, keyEquivalent: "")
        let tabsMenu = NSMenu(title: "Select Tab")
        for n in 1...8 {
            let item = NSMenuItem(title: "Tab \(n)", action: Selector(("selectTabNumber:")), keyEquivalent: String(n))
            item.tag = n
            item.keyEquivalentModifierMask = .command
            tabsMenu.addItem(item)
        }
        tabsMenu.addItem(NSMenuItem(title: "Last Tab", action: Selector(("selectLastTab:")), keyEquivalent: ""))   // its key, command-9, is View > Zoom to Fit's (see fitPage)
        tabs.submenu = tabsMenu
        window.addItem(tabs)
        window.addItem(.separator())
        switchItem = add(window, "Switch to Studio", "switchMode:")   // its title follows the key window (validateMenuItem), its key is a setting
        applySwitchShortcut()
        window.addItem(.separator())
        let pop = add(window, "Equation Popup", "toggleWindow", "e", [.command, .option])   // opens it, and closes it when it is the open one
        pop.target = PopController.shared
        NSApp.windowsMenu = window
    }
}
