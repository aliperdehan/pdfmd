import Cocoa
import Carbon.HIToolbox

/// A global shortcut as the `popHotkey` setting writes it: `⌥⇧T`, or in words `option+shift+t`. It must hold Control, Option or Command.
struct PopShortcut: Equatable {
    var code: UInt32
    var mods: UInt32
    var label: String

    static let standard = PopShortcut.parse("⌥⇧T")!

    /// The keys that can be named: letters, digits, the punctuation of a US keyboard, Space and F1 to F12 (virtual key codes).
    static let keys: [String: UInt32] = [
        "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05, "Z": 0x06, "X": 0x07, "C": 0x08, "V": 0x09, "B": 0x0B,
        "Q": 0x0C, "W": 0x0D, "E": 0x0E, "R": 0x0F, "Y": 0x10, "T": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16,
        "5": 0x17, "=": 0x18, "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E, "O": 0x1F, "U": 0x20, "[": 0x21,
        "I": 0x22, "P": 0x23, "L": 0x25, "J": 0x26, "'": 0x27, "K": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B, "/": 0x2C, "N": 0x2D,
        "M": 0x2E, ".": 0x2F, "Space": 0x31,
        "F1": 0x7A, "F2": 0x78, "F3": 0x63, "F4": 0x76, "F5": 0x60, "F6": 0x61, "F7": 0x62, "F8": 0x64, "F9": 0x65, "F10": 0x6D,
        "F11": 0x67, "F12": 0x6F,
    ]

    private static let words: [String: UInt32] = [
        "control": UInt32(controlKey), "ctrl": UInt32(controlKey), "option": UInt32(optionKey), "opt": UInt32(optionKey),
        "alt": UInt32(optionKey), "shift": UInt32(shiftKey), "command": UInt32(cmdKey), "cmd": UInt32(cmdKey),
    ]
    private static let symbols: [Character: UInt32] = [
        "⌃": UInt32(controlKey), "⌥": UInt32(optionKey), "⇧": UInt32(shiftKey), "⌘": UInt32(cmdKey),
    ]

    /// The canonical label: modifiers in the order ⌃⌥⇧⌘, then the key.
    static func label(mods: UInt32, key: String) -> String {
        var s = ""
        if mods & UInt32(controlKey) != 0 { s += "⌃" }
        if mods & UInt32(optionKey) != 0 { s += "⌥" }
        if mods & UInt32(shiftKey) != 0 { s += "⇧" }
        if mods & UInt32(cmdKey) != 0 { s += "⌘" }
        return s + key
    }

    /// `⌥⇧T`, `option+shift+t`, `ctrl-opt-space`, `⌘⌥F5`... nil if it has no key, an unknown word, or none of Control, Option, Command.
    static func parse(_ text: String) -> PopShortcut? {
        var mods: UInt32 = 0
        var key: String?
        var rest = text.trimmingCharacters(in: .whitespaces)
        while let first = rest.first, let m = symbols[first] { mods |= m; rest.removeFirst() }   // symbols run together: ⌥⇧T
        for part in rest.split(whereSeparator: { "+- ".contains($0) }).map(String.init) {
            if let m = words[part.lowercased()] { mods |= m; continue }
            if key != nil { return nil }
            key = part.count == 1 ? part.uppercased() : (part.lowercased() == "space" ? "Space" : part.uppercased())
        }
        if rest.hasSuffix("-") || rest == "-" { key = key ?? "-" }   // the minus key itself, `option+-` splits to nothing
        guard let k = key, let code = keys[k], mods & UInt32(controlKey | optionKey | cmdKey) != 0 else { return nil }
        return PopShortcut(code: code, mods: mods, label: label(mods: mods, key: k))
    }

    /// The shortcut a key press makes (for the dialog that asks for a new one).
    static func from(_ e: NSEvent) -> PopShortcut? {
        let f = e.modifierFlags.intersection(.deviceIndependentFlagsMask)
        var mods: UInt32 = 0
        if f.contains(.control) { mods |= UInt32(controlKey) }
        if f.contains(.option) { mods |= UInt32(optionKey) }
        if f.contains(.shift) { mods |= UInt32(shiftKey) }
        if f.contains(.command) { mods |= UInt32(cmdKey) }
        guard mods & UInt32(controlKey | optionKey | cmdKey) != 0,
              let name = keys.first(where: { $0.value == UInt32(e.keyCode) })?.key else { return nil }
        return PopShortcut(code: UInt32(e.keyCode), mods: mods, label: label(mods: mods, key: name))
    }

    /// The shortcut in the setting; nil for `none` (and for a text that does not parse: the setting is only ever written parsed).
    static func current() -> PopShortcut? {
        let text = Settings.string("popHotkey")
        if text.lowercased() == "none" { return nil }
        return parse(text) ?? .standard
    }
}

extension PopShortcut {
    /// The shortcut as a menu item has it: the key's character (a letter in lower case, F1 to F12 as the function-key characters) and the modifiers.
    var menuKey: String {
        let name = PopShortcut.keys.first { $0.value == code }?.key ?? ""
        if name == "Space" { return " " }
        if name.count > 1, name.hasPrefix("F"), let n = Int(name.dropFirst()), (1...12).contains(n) { return String(UnicodeScalar(NSF1FunctionKey + n - 1)!) }
        return name.lowercased()
    }
    var menuMask: NSEvent.ModifierFlags {
        var m: NSEvent.ModifierFlags = []
        if mods & UInt32(controlKey) != 0 { m.insert(.control) }
        if mods & UInt32(optionKey) != 0 { m.insert(.option) }
        if mods & UInt32(shiftKey) != 0 { m.insert(.shift) }
        if mods & UInt32(cmdKey) != 0 { m.insert(.command) }
        return m
    }
}

/// A global hotkey through Carbon, which needs no privacy permission.
final class PopHotKey {
    static var action: (() -> Void)?
    private var ref: EventHotKeyRef?
    private var installed = false
    private(set) var failure: OSStatus?

    /// True when the shortcut is registered. A refusal is kept in `failure` for the menu to show; nothing is put on the screen.
    func register(_ s: PopShortcut) -> Bool {
        unregister()
        if !installed {
            var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
            InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in PopHotKey.action?(); return noErr }, 1, &spec, nil, nil)
            installed = true
        }
        let id = EventHotKeyID(signature: OSType(0x434F4C31), id: 1)   // "COL1"
        let status = RegisterEventHotKey(s.code, s.mods, id, GetApplicationEventTarget(), 0, &ref)
        failure = status == noErr ? nil : status
        return status == noErr
    }

    func unregister() {
        if let r = ref { UnregisterEventHotKey(r); ref = nil }
        failure = nil
    }
}

/// The field of the "change shortcut" dialog: the next key combination pressed becomes the shortcut.
final class PopShortcutCatcher: NSView {
    var captured: PopShortcut?
    let field = NSTextField(labelWithString: "press the new shortcut…")
    override var acceptsFirstResponder: Bool { true }
    override init(frame: NSRect) {
        super.init(frame: frame)
        field.frame = bounds
        field.alignment = .center
        field.font = .systemFont(ofSize: 22, weight: .medium)
        addSubview(field)
    }
    required init?(coder: NSCoder) { fatalError() }
    private func take(_ e: NSEvent) -> Bool {
        guard let s = PopShortcut.from(e) else { NSSound.beep(); return true }
        captured = s
        field.stringValue = s.label
        return true
    }
    override func keyDown(with event: NSEvent) { _ = take(event) }
    override func performKeyEquivalent(with event: NSEvent) -> Bool { take(event) }
}
