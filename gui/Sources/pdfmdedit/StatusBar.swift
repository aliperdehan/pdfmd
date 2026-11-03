import Cocoa

/// The numbers of the status bar, worked out so that a huge file never makes a key press wait: the cheap ones (characters,
/// caret location) are read at once; the number of lines and the caret's line are counted in slices of `statusSliceChars`
/// characters, one slice per run-loop turn (a key press gets in between), after a pause of `statusDelayMs` when the text is
/// bigger than one slice. The caret's line is counted from an anchor (a position and its line number) that stays valid while
/// edits happen at or after it, so typing and moving the caret never count from the top again.
final class TextStats {
    private(set) var lines: Int?          // nil until counted
    private(set) var caretLine: Int?
    private(set) var length = 0
    private(set) var location = 0
    var onChange: (() -> Void)?

    private weak var tv: NSTextView?
    private var anchor = (loc: 0, line: 1)
    private var generation = 0
    private var pending: DispatchWorkItem?
    var lineBreak: unichar = 10   // 13 for a file with old Mac (CR) line endings

    init(_ tv: NSTextView) {
        self.tv = tv
        if let storage = tv.textStorage {
            NotificationCenter.default.addObserver(self, selector: #selector(edited(_:)), name: NSTextStorage.didProcessEditingNotification, object: storage)
        }
        NotificationCenter.default.addObserver(self, selector: #selector(moved), name: NSTextView.didChangeSelectionNotification, object: tv)
    }

    deinit { NotificationCenter.default.removeObserver(self) }

    /// Everything is new (a file was loaded or reverted).
    func reset() {
        anchor = (0, 1)
        lines = nil
        caretLine = nil
        update()
    }

    @objc private func edited(_ note: Notification) {
        guard let storage = note.object as? NSTextStorage, storage.editedMask.contains(.editedCharacters) else { return }
        if storage.editedRange.location < anchor.loc { anchor = (0, 1) }
        lines = nil
        update()
    }

    @objc private func moved() { update() }

    private func update() {
        guard let tv, let storage = tv.textStorage else { return }
        generation += 1
        pending?.cancel()
        length = storage.length
        location = tv.selectedRange().location
        onChange?()
        let slice = max(1000, Settings.int("statusSliceChars"))
        if length <= slice {
            count()
        } else {
            let item = DispatchWorkItem { [weak self] in self?.count() }
            pending = item
            DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(max(0, Settings.int("statusDelayMs"))), execute: item)
        }
    }

    /// The caret's line from the anchor, then (when the text changed) the number of lines from the caret on.
    private func count() {
        guard let tv, let storage = tv.textStorage else { return }
        let ns = storage.mutableString
        let gen = generation
        let caret = min(tv.selectedRange().location, ns.length)
        let from = min(anchor.loc, ns.length)
        let towards = { (a: Int, b: Int, done: @escaping (Int) -> Void) in
            self.newlines(in: NSRange(location: min(a, b), length: abs(b - a)), of: ns, generation: gen, done: done)
        }
        towards(from, caret) { [weak self] n in
            guard let self else { return }
            self.anchor = (caret, caret >= from ? self.anchor.line + n : self.anchor.line - n)
            self.caretLine = self.anchor.line
            self.onChange?()
            guard self.lines == nil else { return }
            self.newlines(in: NSRange(location: caret, length: ns.length - caret), of: ns, generation: gen) { rest in
                self.lines = self.anchor.line + rest
                self.onChange?()
            }
        }
    }

    /// Counts the line breaks in a range, a slice at a time; a newer edit (another generation) drops the count.
    private func newlines(in range: NSRange, of ns: NSString, generation gen: Int, done: @escaping (Int) -> Void) {
        let slice = max(1000, Settings.int("statusSliceChars"))
        var buffer = [unichar](repeating: 0, count: min(slice, max(range.length, 1)))
        var position = range.location, total = 0
        func step() {
            guard gen == self.generation else { return }
            let n = min(slice, NSMaxRange(range) - position)
            if n > 0 {
                ns.getCharacters(&buffer, range: NSRange(location: position, length: n))
                let lb = lineBreak
                var found = 0
                for i in 0..<n where buffer[i] == lb { found += 1 }
                total += found
                position += n
            }
            if position >= NSMaxRange(range) { done(total) } else { DispatchQueue.main.async(execute: step) }
        }
        step()
    }
}

/// CotEditor's status bar: counts on the left, size, encoding and line ending on the right. Every element is a setting.
final class StatusBar: NSView {
    static let items = ["statusLines", "statusCharacters", "statusLocation", "statusLine", "statusSize", "statusEncoding", "statusLineEnding"]

    private let left = NSTextField(labelWithString: "")
    private let right = NSTextField(labelWithString: "")
    private let rule = NSBox()
    private let numbers = NumberFormatter()
    private var stats: TextStats?
    var encodingName = "Unicode (UTF-8)"
    var lineEndingName = "LF"
    var fileURL: URL?

    override init(frame: NSRect) {
        super.init(frame: frame)
        numbers.numberStyle = .decimal
        rule.boxType = .separator
        for f in [left, right] {
            f.font = .monospacedDigitSystemFont(ofSize: 11, weight: .regular)
            f.lineBreakMode = .byTruncatingTail
            addSubview(f)
        }
        right.alignment = .right
        addSubview(rule)
        autoresizingMask = [.width]
        applyColours()
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    func attach(_ stats: TextStats) {
        self.stats = stats
        stats.onChange = { [weak self] in self?.refresh() }
        refresh()
    }

    override func layout() {
        super.layout()
        let h = bounds.height
        rule.frame = NSRect(x: 0, y: h - 1, width: bounds.width, height: 1)
        let text: CGFloat = 15
        let y = (h - 1 - text) / 2
        let rightWidth = min(bounds.width / 2, max(right.attributedStringValue.size().width + 4, 0))
        right.frame = NSRect(x: bounds.width - rightWidth - 12, y: y, width: rightWidth, height: text)
        left.frame = NSRect(x: 12, y: y, width: max(0, bounds.width - rightWidth - 36), height: text)
    }

    static var height: CGFloat { 22 }

    /// What the two labels say (the smoke test reads it).
    var texts: (left: String, right: String) { (left.stringValue, right.stringValue) }

    func applyColours() {
        let ink = Palette.text.withAlphaComponent(0.6)
        left.textColor = ink
        right.textColor = ink
        wantsLayer = true
        layer?.backgroundColor = Palette.background.cgColor
    }

    private func number(_ n: Int?) -> String { n.map { numbers.string(from: NSNumber(value: $0)) ?? "\($0)" } ?? "…" }

    func refresh() {
        guard let stats else { return }
        var leftParts: [String] = []
        if Settings.flag("statusLines") { leftParts.append("Lines: " + number(stats.lines)) }
        if Settings.flag("statusCharacters") { leftParts.append("Characters: " + number(stats.length)) }
        if Settings.flag("statusLocation") { leftParts.append("Location: " + number(stats.location)) }
        if Settings.flag("statusLine") { leftParts.append("Line: " + number(stats.caretLine)) }
        var rightParts: [String] = []
        if Settings.flag("statusSize"), let url = fileURL,
           let size = (try? FileManager.default.attributesOfItem(atPath: url.path))?[.size] as? Int64 {
            rightParts.append(ByteCountFormatter.string(fromByteCount: size, countStyle: .file))
        }
        if Settings.flag("statusEncoding") { rightParts.append(encodingName) }
        if Settings.flag("statusLineEnding") { rightParts.append(lineEndingName) }
        left.stringValue = leftParts.joined(separator: "   ")
        right.stringValue = rightParts.joined(separator: "   ")
        needsLayout = true
    }
}

func encodingDisplayName(_ e: String.Encoding) -> String {
    switch e {
    case .utf8: return "Unicode (UTF-8)"
    case .isoLatin1: return "Western (ISO Latin 1)"
    default: return String.localizedName(of: e)
    }
}

/// The line ending a file uses: the first line break decides (an empty file or one without a break is LF).
func detectLineEnding(_ data: Data) -> (name: String, unit: unichar) {
    guard let i = data.firstIndex(where: { $0 == 10 || $0 == 13 }) else { return ("LF", 10) }
    if data[i] == 10 { return ("LF", 10) }
    return (data.index(after: i) < data.endIndex && data[data.index(after: i)] == 10) ? ("CRLF", 10) : ("CR", 13)
}
