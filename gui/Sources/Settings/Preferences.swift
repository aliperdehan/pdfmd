import Cocoa

/// The Settings window (⌘,). Nothing in it is written by hand: the Editor and Performance tabs, the theme popups and the
/// colour rows are generated from the tables in `Settings` and `Palette`, so a setting added there appears here and the
/// shell (`defaults write`, `--settings`) and the window cannot drift apart. A change is written at once (no OK button)
/// and applied to the open windows.
final class PreferencesController: NSWindowController, NSTabViewDelegate {
    static let shared = PreferencesController()

    static let tabs = ["General", "Editor", "Status bar", "PDF", "HTML", "Studio", "Build", "Popup", "Colours", "Performance"]

    /// Every control by name, for refreshing it and for the smoke test: a setting's key, `category.<role>`,
    /// `color.<role>.light`, `color.<role>.dark`, `reset.<role>`, `restore.<tab>`.
    private(set) var controls: [String: NSControl] = [:]

    /// The size each tab needs, so the window follows the tab that is shown (CotEditor's Settings window does the same).
    private var stacks: [String: NSStackView] = [:]
    private var pages: [String: NSView] = [:]
    private let margin: CGFloat = 18
    private let tabView = NSTabView()

    init() {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 400, height: 300),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Settings"
        window.isReleasedWhenClosed = false
        super.init(window: window)
        tabView.frame = window.contentLayoutRect
        tabView.autoresizingMask = [.width, .height]
        tabView.delegate = self
        for name in PreferencesController.tabs {
            let item = NSTabViewItem(identifier: name)
            item.label = name
            item.view = page(name)
            tabView.addTabViewItem(item)
        }
        window.contentView = tabView
        refresh()
        fit(tabView.selectedTabViewItem)
    }

    func tabView(_ tabView: NSTabView, didSelect tabViewItem: NSTabViewItem?) { fit(tabViewItem) }

    /// Sizes the window to the shown tab, keeping its top-left corner.
    private func fit(_ item: NSTabViewItem?) {
        guard let window, let id = item?.identifier as? String, let stack = stacks[id] else { return }
        // measured now, not when the page was built: the popups only have their widths once they are filled
        let need = stack.fittingSize
        let size = NSSize(width: need.width + 2 * margin, height: need.height + 2 * margin)
        let chrome = NSSize(width: tabView.frame.width - tabView.contentRect.width, height: tabView.frame.height - tabView.contentRect.height)
        pages[id]?.frame = NSRect(origin: .zero, size: size)   // the scroll view's document: as tall as the page needs
        var frame = window.frameRect(forContentRect: NSRect(origin: .zero, size: NSSize(width: size.width + chrome.width, height: size.height + chrome.height)))
        // never taller than the screen that the window is on: what does not fit scrolls
        let room = (window.screen ?? NSScreen.main)?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        frame.size.height = min(frame.height, room.height)
        frame.origin = NSPoint(x: window.frame.minX, y: window.frame.maxY - frame.height)
        if frame.minY < room.minY { frame.origin.y = room.minY }   // lifted off the Dock
        if frame.maxY > room.maxY { frame.origin.y = room.maxY - frame.height }
        window.setFrame(frame, display: true, animate: window.isVisible)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    /// Shows the tab of that name (false: there is none). The window follows its size.
    @discardableResult func select(tab: String) -> Bool {
        guard let item = tabView.tabViewItems.first(where: { ($0.identifier as? String) == tab }) else { return false }
        tabView.selectTabViewItem(item)
        fit(item)
        return true
    }

    /// Opens the window, on the tab named (one of `tabs`) or on the one that was last shown. The app is brought forward too: a menu-bar
    /// icon's item is used while another app is in front and no Colophon window exists, and an inactive app's window opens hidden behind.
    func show(tab: String? = nil) {
        if let tab { select(tab: tab) }
        window?.center()
        showWindow(nil)
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    // MARK: building

    private func name(_ s: String) -> NSUserInterfaceItemIdentifier { NSUserInterfaceItemIdentifier(s) }

    /// A small grey wrapping label of a fixed width (a fixed width, so that the window can be sized to its content).
    private func note(_ text: String, width: CGFloat = 250) -> NSTextField {
        let l = NSTextField(wrappingLabelWithString: text)
        l.font = .systemFont(ofSize: 11)
        l.textColor = .secondaryLabelColor
        l.preferredMaxLayoutWidth = width
        l.widthAnchor.constraint(equalToConstant: width).isActive = true
        return l
    }

    private func heading(_ text: String) -> NSTextField {
        let l = NSTextField(labelWithString: text)
        l.font = .systemFont(ofSize: 11)
        l.textColor = .secondaryLabelColor
        return l
    }

    private func register(_ c: NSControl, _ key: String, tip: String? = nil) {
        c.identifier = name(key)
        c.target = self
        c.action = #selector(controlChanged(_:))
        c.toolTip = tip
        controls[key] = c
    }

    private func page(_ tab: String) -> NSView {
        var rows: [[NSView]] = []
        for text in Settings.texts where text.tab == tab { rows.append(row(text)) }
        for item in Settings.items where item.tab == tab { rows.append(row(item)) }

        let grid = NSGridView(views: rows)
        grid.columnSpacing = 14
        grid.rowSpacing = 10
        if grid.numberOfColumns > 0 { grid.column(at: 0).xPlacement = .trailing }
        for r in 0..<grid.numberOfRows { grid.row(at: r).yPlacement = .center }

        let restore = NSButton(title: "Restore defaults", target: self, action: #selector(controlChanged(_:)))
        register(restore, "restore." + tab)
        let shell = note("Every setting is also a command: defaults write io.github.aliperdehan.pdfmdedit <key> <value>. "
                       + "`pdfmdedit --settings` lists the keys; a change here applies to the open windows at once.", width: 520)

        let stack = NSStackView(views: tab == "Colours" ? [grid, rolesGrid(), shell, restore] : [grid, shell, restore])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 16
        stacks[tab] = stack
        let view = PreferencesPage()
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: view.topAnchor, constant: margin),
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: margin),
        ])
        // a page taller than the screen scrolls: the window is cut to the screen in `fit`, the page is the scroll view's document
        let scroll = NSScrollView()
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.borderType = .noBorder
        scroll.documentView = view
        pages[tab] = view
        return scroll
    }

    private func row(_ item: Settings.Item) -> [NSView] {
        let tip = "\(item.help)  [\(item.key)]"
        let control: NSControl
        switch item.kind {
        case .flag:
            control = NSButton(checkboxWithTitle: "", target: nil, action: nil)
        case .number:
            let f = NSTextField(string: "")
            f.widthAnchor.constraint(equalToConstant: 90).isActive = true
            control = f
        case .choice(let values):
            let p = NSPopUpButton(frame: .zero, pullsDown: false)
            p.addItems(withTitles: values.map { v in "\(Int(v))" + (v == item.value ? " (default)" : "") })
            control = p
        }
        register(control, item.key, tip: tip)
        return [NSTextField(labelWithString: item.label), control, note(item.help + (item.live ? "" : " (applies to windows opened afterwards)"))]
    }

    private func row(_ text: Settings.Text) -> [NSView] {
        let control: NSControl
        switch text.kind {
        case .free:
            control = NSTextField(string: "")
        case .themes:
            control = NSPopUpButton(frame: .zero, pullsDown: false)
        case .fonts, .options:
            control = NSPopUpButton(frame: .zero, pullsDown: false)
        case .hotkey:
            control = NSTextField(string: "")
        }
        register(control, text.key, tip: "\(text.help)  [\(text.key)]")
        return [NSTextField(labelWithString: text.label), control, note(text.help)]
    }

    private func rolesGrid() -> NSView {
        var rows: [[NSView]] = [[heading("Role"), heading("Takes the colour of"), heading("Light"), heading("Dark"), NSTextField(labelWithString: "")]]
        for role in Palette.roles {
            let category = NSPopUpButton(frame: .zero, pullsDown: false)
            category.addItems(withTitles: Theme.categoryNames + ["text"])
            register(category, "category." + role.key, tip: "which theme category colours this role; `text` switches the colouring of the role off  [category.\(role.key)]")
            let light = NSColorWell(frame: NSRect(x: 0, y: 0, width: 44, height: 24))
            let dark = NSColorWell(frame: NSRect(x: 0, y: 0, width: 44, height: 24))
            for w in [light, dark] { w.widthAnchor.constraint(equalToConstant: 44).isActive = true; w.heightAnchor.constraint(equalToConstant: 24).isActive = true }
            register(light, "color.\(role.key).light", tip: "this role's colour in a light appearance  [color.\(role.key)]")
            register(dark, "color.\(role.key).dark", tip: "this role's colour in a dark appearance  [color.\(role.key)]")
            let reset = NSButton(title: "Reset", target: nil, action: nil)
            register(reset, "reset." + role.key, tip: "back to the theme's colour for \(role.key)")
            reset.controlSize = .small
            let label = NSTextField(labelWithString: role.key)
            label.toolTip = role.help
            rows.append([label, category, light, dark, reset])
        }
        let grid = NSGridView(views: rows)
        grid.columnSpacing = 12
        grid.rowSpacing = 6
        for r in 0..<grid.numberOfRows { grid.row(at: r).yPlacement = .center }
        return grid
    }

    // MARK: showing the current values

    /// Shows what is stored (or the default) in every control; called at the start and after a reset.
    func refresh() {
        for item in Settings.items {
            guard let c = controls[item.key] else { continue }
            let v = Settings.number(item.key)
            switch item.kind {
            case .flag: (c as? NSButton)?.state = v != 0 ? .on : .off
            case .number: (c as? NSTextField)?.stringValue = v == v.rounded() ? "\(Int(v))" : "\(v)"
            case .choice(let values): (c as? NSPopUpButton)?.selectItem(at: values.firstIndex(of: v) ?? 0)
            }
        }
        for text in Settings.texts {
            guard let c = controls[text.key] else { continue }
            let now = Settings.string(text.key)
            switch text.kind {
            case .free: (c as? NSTextField)?.stringValue = now
            case .themes: fill(c as? NSPopUpButton, Theme.available(), select: now)
            case .fonts: fill(c as? NSPopUpButton, monospacedFamilies(), select: now)
            case .options(let names): fill(c as? NSPopUpButton, names, select: now)
            case .hotkey: (c as? NSTextField)?.stringValue = now
            }
        }
        refreshRoles()
    }

    private func fill(_ popup: NSPopUpButton?, _ names: [String], select now: String) {
        guard let popup else { return }
        popup.removeAllItems()
        popup.addItems(withTitles: names.contains(now) ? names : [now] + names)   // a value that is not on disk is still shown
        popup.selectItem(withTitle: now)
    }

    private func refreshRoles() {
        for role in Palette.roles {
            (controls["category." + role.key] as? NSPopUpButton)?.selectItem(withTitle: Palette.category(of: role))
            (controls["color.\(role.key).light"] as? NSColorWell)?.color = Palette.resolved(role.key, dark: false)
            (controls["color.\(role.key).dark"] as? NSColorWell)?.color = Palette.resolved(role.key, dark: true)
        }
    }

    // MARK: changes

    @objc func controlChanged(_ sender: NSControl) {
        guard let id = sender.identifier?.rawValue else { return }
        if id.hasPrefix("restore.") { restore(String(id.dropFirst(8))); return }
        if id.hasPrefix("reset.") {
            let role = String(id.dropFirst(6))
            Settings.remove(["color." + role, "category." + role])
            refreshRoles()
            return
        }
        if id.hasPrefix("category.") {
            let role = Palette.roles.first { $0.key == String(id.dropFirst(9)) }!
            let chosen = (sender as? NSPopUpButton)?.titleOfSelectedItem ?? role.category
            Settings.remove(["color." + role.key])   // a colour of its own would hide the category
            Settings.set(id, chosen == role.category ? nil : chosen)
            refreshRoles()
            return
        }
        if id.hasPrefix("color.") {
            let parts = id.split(separator: ".").map(String.init)   // color, role, light|dark
            guard parts.count == 3, let light = controls["color.\(parts[1]).light"] as? NSColorWell,
                  let dark = controls["color.\(parts[1]).dark"] as? NSColorWell else { return }
            Settings.set("color." + parts[1], "\(Palette.hex(light.color)),\(Palette.hex(dark.color))")
            return
        }
        if let item = Settings.items.first(where: { $0.key == id }) {
            switch item.kind {
            case .flag: Settings.set(id, (sender as? NSButton)?.state == .on ? 1 : 0)
            case .number:
                let text = (sender as? NSTextField)?.stringValue ?? ""
                if let v = Double(text.trimmingCharacters(in: .whitespaces)), v >= 0 { Settings.set(id, v) } else { refresh() }   // a wrong entry goes back to what is stored
            case .choice(let values):
                Settings.set(id, values[(sender as? NSPopUpButton)?.indexOfSelectedItem ?? 0])
            }
            return
        }
        if let text = Settings.texts.first(where: { $0.key == id }) {
            var value = (sender as? NSPopUpButton)?.titleOfSelectedItem ?? (sender as? NSTextField)?.stringValue ?? ""
            if case .hotkey = text.kind, !value.isEmpty {   // a shortcut is stored in its written-out form, or not at all
                if value.lowercased() == "none" { value = "none" }
                else if let shortcut = PopShortcut.parse(value) { value = shortcut.label }
                else { NSSound.beep(); refresh(); return }   // a wrong entry goes back to what is stored
            }
            Settings.set(id, value.isEmpty ? nil : value)
            if id.hasPrefix("theme") { refreshRoles() }
        }
    }

    /// Back to the defaults for everything on one tab.
    private func restore(_ tab: String) {
        var keys = Settings.items.filter { $0.tab == tab }.map(\.key) + Settings.texts.filter { $0.tab == tab }.map(\.key)
        if tab == "Colours" { keys += Palette.roles.flatMap { ["color." + $0.key, "category." + $0.key] } }
        Settings.remove(keys)
        refresh()
    }
}

/// A page of the Settings window: flipped, so that it starts at the top of its scroll view.
final class PreferencesPage: NSView {
    override var isFlipped: Bool { true }
}
