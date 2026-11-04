import Cocoa

final class AppDelegate: NSObject, NSApplicationDelegate {
    var launchedWithFiles = false

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
        NSApp.activate(ignoringOtherApps: true)
        PopController.shared.settingsChanged()   // the menu-bar icon and the shortcut, when the setting says so
        NotificationCenter.default.addObserver(forName: Settings.changed, object: nil, queue: .main) { _ in PopController.shared.settingsChanged() }
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

    @objc func showPreferences(_ sender: Any?) { PreferencesController.shared.show() }

    private func buildMenus() {
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
        add(file, "Open…", "openDocument:", "o")
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
        let pop = add(window, "Equation Popup", "toggleWindow", "e", [.command, .option])   // opens it, and closes it when it is the open one
        pop.target = PopController.shared
        NSApp.windowsMenu = window
    }
}
