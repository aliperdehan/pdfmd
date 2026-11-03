import Cocoa

/// A colour theme in CotEditor's `.cottheme` format (a JSON file; CotEditor's built-in themes are Apache 2.0, a copy is bundled
/// in `Themes/` with their licence). The file names a colour for each of ten syntax categories and for the text, the
/// background, the caret and the selection; a key may say `"usesSystemSetting": true`, which means "the system's colour".
struct Theme {
    static let categoryNames = ["attributes", "characters", "commands", "comments", "keywords", "numbers", "strings", "types", "values", "variables"]

    let name: String
    let categories: [String: NSColor]
    let text: NSColor
    let background: NSColor
    let insertionPoint: NSColor?   // nil = the system's
    let selection: NSColor?

    /// "#RRGGBB" or "#RRGGBBAA" (the theme files use the second form for the line highlight).
    static func parseHex(_ hex: String) -> NSColor? {
        let h = hex.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "#", with: "")
        guard h.count == 6 || h.count == 8, let v = UInt64(h, radix: 16) else { return nil }
        let rgb = h.count == 8 ? v >> 8 : v
        let alpha = h.count == 8 ? CGFloat(v & 255) / 255 : 1
        return NSColor(srgbRed: CGFloat((rgb >> 16) & 255) / 255, green: CGFloat((rgb >> 8) & 255) / 255, blue: CGFloat(rgb & 255) / 255, alpha: alpha)
    }

    /// Where themes are looked for, in this order: the editor's own folder, CotEditor's folder (so a theme the author made there
    /// works as it is), the copies bundled with the app, and CotEditor.app itself when it is installed.
    static var folders: [URL] {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        var list = [support.appendingPathComponent("pdfmdedit/Themes"), support.appendingPathComponent("CotEditor/Themes")]
        if let res = Bundle.main.resourceURL { list.append(res.appendingPathComponent("Themes")) }
        list.append(URL(fileURLWithPath: "/Applications/CotEditor.app/Contents/Resources/Themes"))
        return list
    }

    static func file(named name: String) -> URL? {
        for dir in folders {
            let url = dir.appendingPathComponent(name + ".cottheme")
            if FileManager.default.fileExists(atPath: url.path) { return url }
        }
        return nil
    }

    static func available() -> [String] {
        var names = Set<String>()
        for dir in folders {
            for url in (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? [] where url.pathExtension == "cottheme" {
                names.insert(url.deletingPathExtension().lastPathComponent)
            }
        }
        return names.sorted()
    }

    static func load(named name: String) -> Theme? {
        guard let url = file(named: name), let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        func entry(_ key: String) -> (color: NSColor?, system: Bool) {
            let e = json[key] as? [String: Any]
            return ((e?["color"] as? String).flatMap(parseHex), (e?["usesSystemSetting"] as? Bool) ?? false)
        }
        var categories: [String: NSColor] = [:]
        for c in categoryNames { if let col = entry(c).color { categories[c] = col } }
        guard let text = entry("text").color, let background = entry("background").color else { return nil }
        let caret = entry("insertionPoint"), selection = entry("selection")
        return Theme(name: name, categories: categories, text: text, background: background,
                     insertionPoint: caret.system ? nil : caret.color, selection: selection.system ? nil : selection.color)
    }
}
