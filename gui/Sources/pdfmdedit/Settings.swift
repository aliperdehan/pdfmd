import Foundation

let appVersion = "0.1.1"

/// Every number that changes the editor's behaviour is a setting here, never a constant in the code
/// (the repository's "no hardcoded thresholds" rule). They are read from the app's UserDefaults:
///   defaults write io.github.aliperdehan.pdfmdedit highlightMarginLines -int 300
/// `pdfmdedit --settings` lists them. They are not `pdfmd --setup` rows yet (alpha).
enum Settings {
    struct Item {
        let key: String
        let value: Double
        let help: String
    }

    static let items: [Item] = [
        Item(key: "highlightMarginLines", value: 150, help: "lines coloured above and below the visible text"),
        Item(key: "highlightDelayMs", value: 120, help: "pause after typing before the visible text is recoloured"),
        Item(key: "scrollDelayMs", value: 20, help: "pause after scrolling out of the coloured range before it is recoloured"),
        Item(key: "highlightMaxMB", value: 0, help: "above this size the colours are off (0 = never)"),
        Item(key: "frontMatterScanChars", value: 20000, help: "how far from the top the closing --- of a YAML front matter is looked for"),
        Item(key: "textKit", value: 2, help: "text engine: 2 (system default, fast on huge pastes and jumps) or 1 (older, non-contiguous layout)"),
        Item(key: "fontSize", value: 13, help: "editor font size in points"),
        Item(key: "wrapLines", value: 1, help: "1 = wrap long lines, 0 = scroll sideways"),
        Item(key: "spellCheck", value: 0, help: "1 = check spelling while typing"),
    ]

    static func number(_ key: String) -> Double {
        if let n = UserDefaults.standard.object(forKey: key) as? NSNumber { return n.doubleValue }
        return items.first { $0.key == key }!.value
    }

    static func int(_ key: String) -> Int { Int(number(key)) }
    static func flag(_ key: String) -> Bool { number(key) != 0 }

    static func listing() -> String {
        items.map { item in
            let now = number(item.key)
            let mark = now == item.value ? "" : "  (now \(now))"
            return "\(item.key.padding(toLength: 22, withPad: " ", startingAt: 0)) \(Int(item.value))\(mark)  \(item.help)"
        }.joined(separator: "\n")
    }
}
