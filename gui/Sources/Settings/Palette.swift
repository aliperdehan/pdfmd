import Cocoa

/// The colours of the colouring, by ROLE. A role is what the editor recognises (a heading, a link, math...); a theme
/// colours CATEGORIES (CotEditor's ten: types, commands, keywords...); each role says which category it takes its colour from.
/// For a role the colour is, first found wins:
///   1. `color.<role>` in the app's UserDefaults ("#RRGGBB" or "#LIGHT,#DARK"),
///   2. the colour the theme gives to the role's category (`category.<role>` in UserDefaults replaces the category;
///      the word `text` means "the theme's plain text colour", which switches that colouring off),
///   3. the soft built-in pair below, used only when no theme file is found.
/// The theme for a light appearance is the `theme` setting, for a dark one `themeDark`. Read when the app starts.
///   defaults write io.github.aliperdehan.pdfmdedit theme -string Dendrobates
///   defaults write io.github.aliperdehan.pdfmdedit category.math -string text
enum Palette {
    struct Role {
        let key: String
        let category: String
        let light: String
        let dark: String
        let help: String
    }

    // Categories follow CotEditor's own Markdown and YAML syntaxes (headings = types, **bold** = commands, list markers and
    // quotes = keywords, link text = values, link targets = characters, code = strings, YAML keys = keywords), so a CotEditor
    // theme looks the same here. Math has no CotEditor colour; it takes `numbers` (CotEditor uses it for images).
    static let roles: [Role] = [
        Role(key: "heading", category: "types", light: "#3B5F99", dark: "#8AA9D6", help: "# headings"),
        Role(key: "key", category: "keywords", light: "#3B5F99", dark: "#8AA9D6", help: "keys of a YAML front matter"),
        Role(key: "list", category: "keywords", light: "#A0693A", dark: "#C9A27A", help: "list markers"),
        Role(key: "emphasis", category: "commands", light: "#7C5A96", dark: "#B49CC8", help: "**bold**"),
        Role(key: "link", category: "values", light: "#3F7F86", dark: "#86B5BA", help: "[text] of a link"),
        Role(key: "url", category: "characters", light: "#5B7F52", dark: "#9FBA93", help: "(target) of a link"),
        Role(key: "math", category: "numbers", light: "#A05A72", dark: "#CF99AB", help: "$math$"),
        Role(key: "code", category: "strings", light: "#5B7F52", dark: "#9FBA93", help: "`code spans`"),
        Role(key: "fence", category: "strings", light: "#5B7F52", dark: "#9FBA93", help: "fenced code blocks"),
        Role(key: "comment", category: "comments", light: "#8C8C8C", dark: "#8E8E93", help: "<!-- comments --> and # comments in YAML"),
        Role(key: "quote", category: "keywords", light: "#8C8C8C", dark: "#8E8E93", help: "> quote markers"),
    ]

    static func parse(_ hex: String) -> NSColor? { Theme.parseHex(hex) }

    private(set) static var lightTheme = Theme.load(named: Settings.string("theme"))
    private(set) static var darkTheme = Theme.load(named: Settings.string("themeDark")) ?? lightTheme

    /// Reads the theme settings again and forgets the colours worked out from them (after a setting changed).
    static func reload() {
        cache = [:]
        lightTheme = Theme.load(named: Settings.string("theme"))
        darkTheme = Theme.load(named: Settings.string("themeDark")) ?? lightTheme
    }

    /// The colour a role has in one appearance, for the Preferences window.
    static func resolved(_ key: String, dark: Bool) -> NSColor {
        var out = NSColor.textColor
        NSAppearance(named: dark ? .darkAqua : .aqua)!.performAsCurrentDrawingAppearance {
            out = color(key).usingColorSpace(.sRGB) ?? .textColor
        }
        return out
    }

    static func hex(_ c: NSColor) -> String {
        let d = c.usingColorSpace(.sRGB) ?? c
        return String(format: "#%02X%02X%02X", Int(round(d.redComponent * 255)), Int(round(d.greenComponent * 255)), Int(round(d.blueComponent * 255)))
    }

    private static func dynamic(_ light: NSColor, _ dark: NSColor) -> NSColor {
        NSColor(name: nil) { appearance in appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light }
    }

    private static func themed(_ pick: (Theme) -> NSColor?, fallback: NSColor) -> NSColor {
        let light = lightTheme.flatMap(pick), dark = darkTheme.flatMap(pick)
        return (light == nil && dark == nil) ? fallback : dynamic(light ?? dark ?? fallback, dark ?? light ?? fallback)
    }

    fileprivate static var cache: [String: NSColor] = [:]

    /// What colours the role is taken from after the user's `category.<role>` setting.
    static func category(of role: Role) -> String {
        if let c = Settings.store.string(forKey: "category." + role.key), c == "text" || Theme.categoryNames.contains(c) { return c }
        return role.category
    }

    static func color(_ key: String) -> NSColor {
        if let c = cache[key] { return c }
        let role = roles.first { $0.key == key }!
        let builtIn = dynamic(parse(role.light)!, parse(role.dark)!)
        var result = themed({ $0.categories[category(of: role)] ?? ($0.text) }, fallback: builtIn)
        if category(of: role) == "text" { result = text }
        if let spec = Settings.store.string(forKey: "color." + key) {
            let parts = spec.split(separator: ",").map(String.init)
            if let first = parts.first.flatMap(parse) { result = dynamic(first, parts.count > 1 ? (parse(parts[1]) ?? first) : first) }
        }
        cache[key] = result
        return result
    }

    // The canvas: plain text, background, caret, selection. With `themeCanvas` = 0, or with no theme, the system's.
    private static var canvas: Bool { Settings.flag("themeCanvas") }
    static var text: NSColor { canvas ? themed({ $0.text }, fallback: .textColor) : .textColor }
    static var background: NSColor { canvas ? themed({ $0.background }, fallback: .textBackgroundColor) : .textBackgroundColor }
    static var insertionPoint: NSColor { canvas ? themed({ $0.insertionPoint }, fallback: .textColor) : .textColor }
    static var selection: NSColor? {
        guard canvas, lightTheme?.selection != nil || darkTheme?.selection != nil else { return nil }
        return themed({ $0.selection }, fallback: .selectedTextBackgroundColor)
    }

    static func listing() -> String {
        var lines = ["theme files found: " + (Theme.available().joined(separator: ", ")),
                     "theme in use: light \(lightTheme?.name ?? "none (built-in soft colours)"), dark \(darkTheme?.name ?? "none (built-in soft colours)")"]
        for r in roles {
            let own = Settings.store.string(forKey: "color." + r.key)
            let cat = category(of: r)
            lines.append("color.\(r.key.padding(toLength: 9, withPad: " ", startingAt: 0)) from \(cat.padding(toLength: 10, withPad: " ", startingAt: 0))" +
                         " built-in \(r.light),\(r.dark)\(own.map { "  (now \($0))" } ?? "")  \(r.help)")
        }
        return lines.joined(separator: "\n")
    }
}
