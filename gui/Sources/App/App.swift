import Cocoa

final class AppDelegate: NSObject, NSApplicationDelegate {
    var launchedWithFiles = false

    func applicationDidFinishLaunching(_ note: Notification) {
        buildMenus()
        let paths = CommandLine.arguments.dropFirst().filter { !$0.hasPrefix("-") && FileManager.default.fileExists(atPath: $0) }
        launchedWithFiles = !paths.isEmpty
        for p in paths {
            NSDocumentController.shared.openDocument(withContentsOf: URL(fileURLWithPath: p), display: true) { _, _, error in
                if let error { NSApp.presentError(error) }
            }
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    // A command-line launch with a file (pdfmd's --editor) stays alive until its windows are closed.
    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }
    func applicationShouldOpenUntitledFile(_ app: NSApplication) -> Bool { !launchedWithFiles && CommandLine.arguments.count < 2 }

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

        let app = menu("pdfmdedit")
        add(app, "About pdfmd Edit", "orderFrontStandardAboutPanel:")
        app.addItem(.separator())
        add(app, "Settings…", "showPreferences:", ",")
        app.addItem(.separator())
        add(app, "Hide pdfmd Edit", "hide:", "h")
        add(app, "Hide Others", "hideOtherApplications:", "h", [.command, .option])
        app.addItem(.separator())
        add(app, "Quit pdfmd Edit", "terminate:", "q")

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
        NSApp.windowsMenu = window
    }
}
