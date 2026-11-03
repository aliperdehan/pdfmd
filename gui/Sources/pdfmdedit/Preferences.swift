import Cocoa

/// The Settings window (⌘,). Nothing in it is written by hand: the Editor and Performance tabs, the theme popups and the
/// colour rows are generated from the tables in `Settings` and `Palette`, so a setting added there appears here and the
/// shell (`defaults write`, `--settings`) and the window cannot drift apart. A change is written at once (no OK button)
/// and applied to the open windows.
final class PreferencesController: NSWindowController {
    static let shared = PreferencesController()

    static let tabs = ["Editor", "Colours", "Performance"]

    /// Every control by name, for refreshing it and for the smoke test: a setting's key, `category.<role>`,
    /// `color.<role>.light`, `color.<role>.dark`, `reset.<role>`, `restore.<tab>`.
    private(set) var controls: [String: NSControl] = [:]

    init() {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 780, height: 620),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Settings"
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("pdfmdedit.settings")
        super.init(window: window)
        let tabView = NSTabView(frame: window.contentLayoutRect)
        tabView.autoresizingMask = [.width, .height]
        for name in PreferencesController.tabs {
            let item = NSTabViewItem(identifier: name)
            item.label = name
            item.view = page(name)
            tabView.addTabViewItem(item)
        }
        window.contentView = tabView
        refresh()
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    func show() {
        window?.center()
        showWindow(nil)
        window?.makeKeyAndOrderFront(nil)
    }

    // MARK: building

    private func name(_ s: String) -> NSUserInterfaceItemIdentifier { NSUserInterfaceItemIdentifier(s) }

    private func note(_ text: String) -> NSTextField {
        let l = NSTextField(wrappingLabelWithString: text)
        l.font = .systemFont(ofSize: 11)
        l.textColor = .secondaryLabelColor
        l.preferredMaxLayoutWidth = 330
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
                       + "`pdfmdedit --settings` lists the keys; a change here applies to the open windows at once.")
        shell.preferredMaxLayoutWidth = 700

        let stack = NSStackView(views: tab == "Colours" ? [grid, rolesGrid(), shell, restore] : [grid, shell, restore])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 16
        let view = NSView()
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: view.topAnchor, constant: 18),
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 18),
        ])
        return view
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
        case .fonts:
            control = NSPopUpButton(frame: .zero, pullsDown: false)
        }
        register(control, text.key, tip: "\(text.help)  [\(text.key)]")
        return [NSTextField(labelWithString: text.label), control, note(text.help)]
    }

    private func rolesGrid() -> NSView {
        var rows: [[NSView]] = [[note("Role"), note("Takes the colour of"), note("Light"), note("Dark"), NSTextField(labelWithString: "")]]
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
            register(reset, "reset." + role.key)
            reset.controlSize = .small
            rows.append([NSTextField(labelWithString: "\(role.key)  —  \(role.help)"), category, light, dark, reset])
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
        if Settings.texts.contains(where: { $0.key == id }) {
            let value = (sender as? NSPopUpButton)?.titleOfSelectedItem ?? (sender as? NSTextField)?.stringValue ?? ""
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
