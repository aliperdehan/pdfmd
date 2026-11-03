import Cocoa

/// The colours of the Markdown colouring, by role. Every role has a soft built-in pair (light and dark appearance)
/// and can be replaced in the app's UserDefaults, like the numeric settings:
///   defaults write io.github.aliperdehan.pdfmdedit color.heading -string "#2F5D9E,#7AA2D8"
/// "#RRGGBB" alone is used in both appearances. A wrong value is ignored. Read when the app starts.
enum Palette {
    struct Role {
        let key: String
        let light: String
        let dark: String
        let help: String
    }

    static let roles: [Role] = [
        Role(key: "heading", light: "#3B5F99", dark: "#8AA9D6", help: "# headings"),
        Role(key: "key", light: "#3B5F99", dark: "#8AA9D6", help: "keys of a YAML front matter"),
        Role(key: "list", light: "#A0693A", dark: "#C9A27A", help: "list markers"),
        Role(key: "emphasis", light: "#7C5A96", dark: "#B49CC8", help: "**bold**"),
        Role(key: "link", light: "#3F7F86", dark: "#86B5BA", help: "[text](url)"),
        Role(key: "math", light: "#A05A72", dark: "#CF99AB", help: "$math$"),
        Role(key: "code", light: "#5B7F52", dark: "#9FBA93", help: "`code` and fenced code blocks"),
        Role(key: "comment", light: "#8C8C8C", dark: "#8E8E93", help: "<!-- comments --> and # comments in YAML"),
        Role(key: "quote", light: "#8C8C8C", dark: "#8E8E93", help: "> quote markers"),
    ]

    private static func parse(_ hex: String) -> NSColor? {
        let h = hex.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "#", with: "")
        guard h.count == 6, let v = UInt32(h, radix: 16) else { return nil }
        return NSColor(srgbRed: CGFloat((v >> 16) & 255) / 255, green: CGFloat((v >> 8) & 255) / 255, blue: CGFloat(v & 255) / 255, alpha: 1)
    }

    static func color(_ key: String) -> NSColor {
        let role = roles.first { $0.key == key }!
        var light = parse(role.light)!, dark = parse(role.dark)!
        if let spec = UserDefaults.standard.string(forKey: "color." + key) {
            let parts = spec.split(separator: ",").map(String.init)
            if let first = parts.first.flatMap(parse) {
                light = first
                dark = parts.count > 1 ? (parse(parts[1]) ?? first) : first
            }
        }
        return NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
        }
    }

    static func listing() -> String {
        roles.map { r in
            let spec = UserDefaults.standard.string(forKey: "color." + r.key)
            return "color.\(r.key.padding(toLength: 17, withPad: " ", startingAt: 0)) \(r.light),\(r.dark)\(spec.map { "  (now \($0))" } ?? "")  \(r.help)"
        }.joined(separator: "\n")
    }
}
